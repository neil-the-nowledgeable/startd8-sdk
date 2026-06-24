"""Shared Linux network-namespace substrate for the behavioral sandbox (OQ-7 — PROTOTYPE).

WHY THIS EXISTS — the verified macOS-Seatbelt gap (see
``docs/design/round3-full-app/CONTAINMENT_SPIKE.md`` §0). Online Boutique services dial each other
over **gRPC**. Under the Seatbelt ``_wrap_loopback_only`` profile, gRPC outbound to ``127.0.0.1`` is
**DENIED** unless the profile re-opens FULL external egress (``remote ip "*"``). So on macOS there is
NO profile that gives gRPC-loopback-dial-out AND egress-deny simultaneously — it's strictly either/or.
The dial-out cells (checkout, recommendation) and the entire Round 3 inter-service fleet therefore
cannot be both wired-over-loopback AND contained on macOS.

A fresh Linux network namespace fixes this BY CONSTRUCTION:
  - The netns has its OWN isolated loopback (``127.0.0.1``), separate from the host and every other
    netns. Processes that SHARE one netns reach each other over that loopback → gRPC dial-out WORKS.
  - The netns has NO veth/route out → external egress is IMPOSSIBLE. Containment is structural, not a
    filter that can be mis-scoped.

THE CRITICAL ARCHITECTURE (easy to get wrong):
  - The EXISTING ``sandbox.py`` netns path (``unshare -rn <cmd>``) puts EACH command in its OWN netns.
    Two peers launched as separate ``unshare -rn`` commands get TWO isolated loopbacks → they CANNOT
    reach each other, and the host harness cannot reach a service inside an isolated netns over
    ``127.0.0.1``. That per-process model is WRONG for dial-out.
  - Therefore the WHOLE behavioral cell — dependency stubs + service-under-test (SUT) + the gRPC
    scoring CLIENT — must run inside ONE SHARED netns. This module runs a single rootless
    ``unshare -rn`` and hosts a "cell runner" command as its child; that cell runner internally starts
    stubs + SUT and runs the client, all sharing the one netns loopback.
  - ``lo`` in a fresh netns is DOWN. We MUST ``ip link set lo up`` inside the netns BEFORE anything
    binds/connects, or every loopback bind/connect fails.

ROOTLESS: ``unshare -rn`` == ``--user --map-root-user --net`` — maps the caller to root in a new
user+net namespace, so NO real root is needed. The cell runner runs as a child of that one namespace.

STATUS (honest): implemented + UNIT-TESTED on macOS (command construction, JSON protocol round-trip,
teardown, degrade-on-unavailable). The live netns path is validated ONLY via a Linux-gated smoke
(``unshare`` is absent on macOS/Darwin — ``run_cell_in_shared_netns`` degrades to a no-op-skip here,
never a false score). See ``docs/design/round3-full-app/NETNS_SUBSTRATE.md``.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Marker the in-netns cell runner prints around its JSON payload so the host can extract it from a
# stdout stream that may also carry incidental server/log noise. The runner prints exactly:
#   <CELL_RESULT_BEGIN>{...json...}<CELL_RESULT_END>
RESULT_BEGIN = "<CELL_RESULT_BEGIN>"
RESULT_END = "<CELL_RESULT_END>"


@dataclass
class NetnsCellResult:
    """Outcome of running a behavioral cell inside one shared rootless netns.

    ``available`` is False (with ``violation`` set) when the netns substrate is not usable on this
    host (e.g. macOS, or a hardened kernel that forbids user namespaces) — the caller DEGRADES the
    cell, exactly like FR-T2-2, and NEVER scores a substrate-absence as model quality.
    """

    available: bool                       # netns substrate usable on this host + the cell launched
    ready: bool = False                   # the cell runner ran to completion and emitted a payload
    payload: Optional[Dict[str, Any]] = None   # parsed {"coverage": ..., "results": [...]} from stdout
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    isolation_level: str = "none(unavailable)"
    violation: Optional[str] = None       # env outcome (degrade) — NOT model quality
    network_isolated: bool = False        # True only when the cell ran inside the shared netns


def netns_available() -> bool:
    """True iff a rootless shared-netns cell can actually be launched on this host.

    Requires Linux + an ``unshare`` binary that FUNCTIONALLY supports ``-rn`` (``--user --net``).
    ``unshare`` being on PATH is necessary but not sufficient — a hardened kernel can forbid
    unprivileged user namespaces (``kernel.unprivileged_userns_clone=0``), so we probe a trivial
    ``unshare -rn true``. On macOS (Darwin) ``unshare`` is absent → returns False (no-op-skip).
    """
    if not sys.platform.startswith("linux"):
        return False
    if shutil.which("unshare") is None:
        return False
    try:
        # Functional probe: can we actually create a rootless user+net namespace?
        proc = subprocess.run(
            ["unshare", "-rn", "true"],
            capture_output=True, timeout=5.0, check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def build_netns_command(cell_runner_cmd: List[str]) -> List[str]:
    """Build the single rootless ``unshare -rn`` argv that brings ``lo`` UP then runs the cell runner.

    The whole cell runs in ONE namespace: we wrap the cell runner in a ``sh -c`` that first does
    ``ip link set lo up`` (a fresh netns's ``lo`` is DOWN — nothing can bind/connect loopback until
    it is up), then ``exec``s the cell runner so it INHERITS the namespace and replaces the shell
    (so killpg on the group reaps the real cell-runner process, no extra shell layer lingering).

    ``ip`` is expected at ``/sbin/ip`` or on PATH inside the netns; we call it bare (``ip``) so the
    netns's own PATH resolves it. The cell runner command is shell-quoted so multi-arg commands and
    paths survive intact.
    """
    inner = "ip link set lo up && exec " + " ".join(shlex.quote(tok) for tok in cell_runner_cmd)
    return ["unshare", "-rn", "sh", "-c", inner]


def parse_cell_payload(stdout: str) -> Optional[Dict[str, Any]]:
    """Extract the cell runner's JSON payload from its stdout (between the BEGIN/END markers).

    Returns the parsed dict, or None when no well-formed payload is present (cell crashed before
    emitting / emitted malformed JSON). The markers let the runner interleave incidental stdout
    (server logs) without corrupting the result channel — only the marked span is parsed.
    """
    start = stdout.rfind(RESULT_BEGIN)
    if start == -1:
        return None
    start += len(RESULT_BEGIN)
    end = stdout.find(RESULT_END, start)
    if end == -1:
        return None
    blob = stdout[start:end].strip()
    try:
        parsed = json.loads(blob)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def emit_cell_payload(payload: Dict[str, Any]) -> str:
    """Serialize ``payload`` into the marked stdout line the host parser expects.

    The reusable cell-runner contract: a runner that has finished its suite calls this and writes the
    result to stdout (``print(emit_cell_payload(...))``). Kept here so both the producer (in-netns
    runner) and consumer (host parser) share one definition of the boundary protocol.
    """
    return RESULT_BEGIN + json.dumps(payload, separators=(",", ":")) + RESULT_END


def _terminate_group(proc: "subprocess.Popen") -> None:
    """Guaranteed teardown of the whole cell process group: SIGTERM, brief grace, then SIGKILL.

    ``unshare`` is started as its own session leader (``start_new_session=True``), so the namespace,
    the inner shell, the cell runner, and every stub/SUT/client the runner forked share one process
    group — killing the group reaps them all with no orphans (mirrors ``sandbox._terminate_group``).
    """
    if proc.poll() is not None:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.send_signal(sig)
            except (ProcessLookupError, OSError):
                return
        try:
            proc.wait(timeout=3.0)
            return
        except subprocess.TimeoutExpired:
            continue


def run_cell_in_shared_netns(
    cell_runner_cmd: List[str],
    *,
    timeout: float = 120.0,
    cwd: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
    max_output_bytes: int = 256 * 1024,
) -> NetnsCellResult:
    """Run a behavioral "cell runner" inside ONE shared rootless netns and parse its JSON result.

    The cell runner (see the cell-runner contract in this module's docstring and ``CellRunnerSpec``)
    is responsible — once inside the netns — for starting its declared stub servers on free loopback
    ports, injecting their ``*_SERVICE_ADDR`` addresses, launching the SUT, running the scoring
    client over the SHARED netns loopback, and printing ``emit_cell_payload({"coverage", "results"})``
    to stdout. This function only owns the SUBSTRATE: it wraps that command in ``unshare -rn`` with
    ``lo`` brought up, captures + parses the payload, and GUARANTEES teardown of the whole group.

    Honest degradation: if the netns substrate is unavailable (macOS, or a hardened kernel that blocks
    user namespaces), returns ``available=False`` with a clear ``violation`` — the caller degrades the
    cell (FR-T2-2 analog), it is NEVER scored as model quality. This makes the function a no-op-skip on
    the macOS dev host while remaining live on a Linux box/CI.
    """
    started = time.monotonic()

    if not netns_available():
        reason = (
            "netns unavailable on this platform (Darwin/macOS — `unshare` absent)"
            if sys.platform == "darwin"
            else "netns unavailable: `unshare -rn` not functional (kernel may forbid user namespaces)"
        )
        return NetnsCellResult(
            available=False,
            violation=reason,
            isolation_level="none(unavailable)",
            duration_s=time.monotonic() - started,
        )

    run_cmd = build_netns_command(cell_runner_cmd)
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)

    proc: Optional[subprocess.Popen] = None
    out, err = "", ""
    violation: Optional[str] = None
    timed_out = False
    try:
        proc = subprocess.Popen(
            run_cmd, cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,  # own process group → killpg reaps the whole netns cell
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            violation = f"cell wall-clock timeout after {timeout}s"
    except Exception as e:  # noqa: BLE001 — the substrate must never crash the harness
        violation = f"netns launch error: {type(e).__name__}: {e}"
    finally:
        if proc is not None:
            _terminate_group(proc)
            try:
                # Drain any residual output after teardown (best-effort).
                tail_out, tail_err = proc.communicate(timeout=3.0)
                out = (out or "") + (tail_out or "")
                err = (err or "") + (tail_err or "")
            except Exception:  # noqa: BLE001
                out, err = out or "", err or ""

    payload = parse_cell_payload(out or "") if not timed_out else None
    if violation is None and payload is None:
        rc = proc.returncode if proc is not None else None
        violation = f"cell runner emitted no parseable result payload (rc={rc})"

    return NetnsCellResult(
        available=True,
        ready=payload is not None,
        payload=payload,
        returncode=proc.returncode if proc is not None else None,
        stdout=(out or "")[-max_output_bytes:],
        stderr=(err or "")[-max_output_bytes:],
        duration_s=time.monotonic() - started,
        isolation_level="rootless-shared-netns" if violation is None or payload is not None else "shared-netns(failed)",
        violation=violation,
        network_isolated=True,  # the cell ran inside a fresh netns: egress impossible by construction
    )


# --------------------------------------------------------------------------- cell-runner contract
#
# The reusable shape an in-netns cell runner must satisfy. This is a CONTRACT (a spec + a thin
# helper), not a full rewrite of execute.py: any script exec'd under run_cell_in_shared_netns that
# honors it will integrate. The runner, once inside the shared netns, MUST:
#
#   1. Start every declared stub server on a FREE loopback port (bind 127.0.0.1:0).
#   2. Inject each stub's address as its `*_SERVICE_ADDR` env var so the SUT dials it over the
#      shared netns loopback (the SUT and stubs share one 127.0.0.1).
#   3. Launch the SUT (resolve_serve_command) with $PORT on a free loopback port; wait for readiness.
#   4. Run the scoring suite client against the live SUT over 127.0.0.1.
#   5. print(emit_cell_payload({"coverage": <float>, "results": [<dict>, ...], ...})) to stdout, then
#      exit. Incidental stdout (server logs) is fine — only the marked span is parsed.
#
# The runner runs everything IN-PROCESS or as children within the one netns. Egress is impossible
# (no route out); loopback works (lo brought up by the substrate before the runner starts).


@dataclass(frozen=True)
class CellRunnerSpec:
    """Declarative description the substrate hands an in-netns cell runner (the boundary contract).

    Kept minimal + serializable so the host can pass it to the runner (e.g. as a JSON arg or a temp
    file the runner reads). ``stub_env_names`` are the ``*_SERVICE_ADDR`` keys the runner binds and
    injects; ``serve_argv`` / ``serve_env`` come from ``resolve_serve_command``; ``suite`` names the
    behavioral suite the runner imports and calls against the live SUT.
    """

    suite: str                                   # e.g. "checkout" / "recommendation"
    serve_argv: List[str]                        # SUT launch argv ($PORT already substituted by runner)
    serve_env: Dict[str, str] = field(default_factory=dict)
    stub_env_names: List[str] = field(default_factory=list)   # *_SERVICE_ADDR keys the runner binds
    tier: str = "baseline"
    readiness_timeout_s: float = 15.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "suite": self.suite,
                "serve_argv": list(self.serve_argv),
                "serve_env": dict(self.serve_env),
                "stub_env_names": list(self.stub_env_names),
                "tier": self.tier,
                "readiness_timeout_s": self.readiness_timeout_s,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, blob: str) -> "CellRunnerSpec":
        d = json.loads(blob)
        return cls(
            suite=d["suite"],
            serve_argv=list(d["serve_argv"]),
            serve_env=dict(d.get("serve_env", {})),
            stub_env_names=list(d.get("stub_env_names", [])),
            tier=d.get("tier", "baseline"),
            readiness_timeout_s=d.get("readiness_timeout_s", 15.0),
        )
