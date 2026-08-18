"""Sandboxed generated-app oracle runner (FR-1).

Given a det-req spec and a generated app root, extract each FR's runnable ``Verify:`` clause via the
**FR-2 parser** (``grammar.parse_spec`` — NOT ``verify_oracle.classify()``, which is verb-gated to
``startd8`` and would return ``assertion`` for a ``pytest``/``probe`` clause, R1-F2) and execute the
runnable ones **inside ``benchmark_matrix.sandbox``**:

  - one-shot (``pytest`` / ``python`` / console-script) → :func:`run_sandboxed` (rc 0 = pass).
  - service (``probe METHOD /path -> STATUS``) → a FIXED loopback httpx call rendered from the
    DATA-ONLY :class:`ProbeSpec` (never code from the clause). When the ORACLE rung supplies a
    ``live_port`` (the app the deploy harness already booted), the probe hits that loopback port
    directly; otherwise the runner boots the app via :func:`run_service_sandboxed`.

A ``SandboxResult``/``ServiceResult`` ``violation`` (env failure: never-ready / launch error /
client raised) maps to :data:`VERDICT_ERROR` (degrade), NEVER the model's ``fail`` — the same
"missing-key is infra_fail, not a catastrophic 0" rule the benchmark matrix encodes. Even a
one-shot that *launched* (no ``violation``) but reports a NON-launch outcome degrades: a command
that could not run (rc 127), or pytest's own env exit codes (interrupted / internal / usage / no
tests collected, or an rc-1 pre-run bootstrap crash where pytest itself is not installed in the app
venv) map to :data:`VERDICT_ERROR`, while a real test failure (pytest rc 1 without a bootstrap
signature) stays :data:`VERDICT_FAIL` (OL-EB-5). A non-runnable FR yields :data:`VERDICT_SKIP`.

This module does NOT import ``verify_oracle.evaluate``/``classify`` (navigator-locked) and never
touches the navigator allow-list (NR-2 / FR-9).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..benchmark_matrix.sandbox import (
    SandboxConfig,
    run_sandboxed,
    run_service_sandboxed,
)
from ..logging_config import get_logger
from . import (
    VERDICT_ERROR,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_SKIP,
    OracleVerdict,
)
from .grammar import (
    KIND_ONESHOT,
    KIND_SERVICE,
    ParsedClause,
    ProbeSpec,
    parse_spec,
)

logger = get_logger("startd8.oracle_loop.runner")

# A conservative default timeout for a one-shot oracle command.
_ONESHOT_TIMEOUT_S = 120.0

# Exit code for "command not found" (POSIX shell / exec convention). For ANY one-shot, rc 127 means
# the command isn't runnable in the app env → env/infra outcome (ERROR), never the model's fail.
_RC_COMMAND_NOT_FOUND = 127

# pytest exit-code semantics (https://docs.pytest.org/en/stable/reference/exit-codes.html):
#   0 = all passed · 1 = tests failed (real model fail) · 2 = interrupted · 3 = internal error
#   4 = usage error · 5 = no tests collected. Codes {2,3,4,5} are harness/env outcomes → ERROR
#   (degrade), NOT the model's catastrophic fail.
_PYTEST_ENV_CODES = frozenset({2, 3, 4, 5})

# Substrings in stderr that mark a pre-run pytest BOOTSTRAP failure (pytest / a plugin / conftest
# could not even launch — e.g. pytest itself is not installed in the app venv). rc 1 accompanied by
# one of these is an env failure, not real test failures → ERROR. This is the OL-EB-5 case: the $0
# dry-run ran `pytest tests/test_health.py` against fixtures/otel-demo/email-py (pytest not in that
# app's requirements) and got rc 1 with a pytest bootstrap traceback — previously mis-scored `fail`.
_PYTEST_BOOTSTRAP_SIGNATURES = (
    "ModuleNotFoundError",
    "ImportError",
    "No module named",
    "_pytest",
)


def _is_pytest_invocation(argv: List[str]) -> bool:
    """True when the one-shot argv runs pytest — either ``pytest …`` or ``python[3] -m pytest …``."""
    if not argv:
        return False
    if argv[0] == "pytest":
        return True
    return argv[0] in ("python", "python3") and "-m" in argv[1:] and "pytest" in argv[1:]


def _classify_oneshot(argv: List[str], returncode: int, stderr: str) -> str:
    """Exit-code-aware verdict for a one-shot that launched (no sandbox ``violation``).

    Splits infra/env failures (→ ERROR, degrade) from real model failures (→ FAIL) so a harness gap
    (a command that cannot launch, pytest not installed, no tests collected) never wrongly triggers a
    regenerate — the same "infra-fail is not the model's catastrophic 0" rule the benchmark matrix
    encodes. ``returncode == 0`` (PASS) is handled by the caller and never reaches here.
    """
    # Command-not-found for ANY one-shot: the command isn't runnable in the env → infra/env.
    if returncode == _RC_COMMAND_NOT_FOUND:
        return VERDICT_ERROR
    if _is_pytest_invocation(argv):
        # pytest's own exit-code semantics: {2,3,4,5} are interrupted/internal/usage/no-tests → env.
        if returncode in _PYTEST_ENV_CODES:
            return VERDICT_ERROR
        if returncode == 1:
            # rc 1 = tests failed — UNLESS stderr shows a pre-run bootstrap crash (pytest couldn't
            # even launch), which is an env failure, not real test failures.
            if any(sig in (stderr or "") for sig in _PYTEST_BOOTSTRAP_SIGNATURES):
                return VERDICT_ERROR
            return VERDICT_FAIL
    # Any other one-shot (or a pytest rc outside the classified set): non-zero → real model fail.
    return VERDICT_FAIL


def _probe_descriptor(p: ProbeSpec) -> str:
    body = f" body={p.body}" if p.body is not None else ""
    return f"{p.method} {p.path}{body} -> {p.expected_status}"


def _resolve_oneshot_cmd(clause: ParsedClause, app_root: Path) -> Optional[List[str]]:
    """Resolve a one-shot clause's argv to a runnable command, or ``None`` if not allow-listed.

    The one-shot allow-list is CLOSED: ``pytest`` / ``python`` run as-is; a bare console-script token
    is runnable ONLY when it resolves to the app's own ``bin/`` entry point (the venv the deploy
    harness built). An unresolved bare token (``rm`` / ``curl`` / ``sh`` — anything that is not a real
    app entry point) returns ``None`` → the runner fails it loud as ``error`` rather than executing an
    arbitrary command on the sandbox PATH. This closes the verb gate to match the FR-2 "closed
    convention" claim (defense-in-depth: the sandbox contains blast radius, AND the allow-list refuses
    non-entry-point verbs) — harvest H1.
    """
    argv = list(clause.command_argv)
    if not argv:
        return None
    if clause.is_console_script:
        candidate = app_root / "bin" / argv[0]
        if candidate.exists():
            return [str(candidate), *argv[1:]]
        # Not a real app entry point → not runnable (do NOT fall through to a bare-PATH exec).
        return None
    return argv


def _make_probe_client(probe: ProbeSpec):
    """Build a FIXED loopback httpx client callback from a DATA-ONLY probe struct.

    The callback contains NO clause-derived code — only the parsed method/path/body/status. It
    returns ``(ok: bool, detail: str)``.
    """

    def _client(port: int):
        import httpx

        url = f"http://127.0.0.1:{port}{probe.path}"
        with httpx.Client(timeout=10.0) as c:
            resp = c.request(probe.method, url, json=probe.body)
        ok = resp.status_code == probe.expected_status
        return (ok, f"status={resp.status_code} expected={probe.expected_status}")

    return _client


def _probe_live(probe: ProbeSpec, live_port: int) -> OracleVerdict:
    """Run a service probe against an ALREADY-booted loopback app (the ORACLE-rung path)."""
    client = _make_probe_client(probe)
    try:
        ok, detail = client(live_port)
    except Exception as exc:  # noqa: BLE001 — a client/env failure degrades, never model fail
        return OracleVerdict(
            fr_id="",
            kind=KIND_SERVICE,
            verdict=VERDICT_ERROR,
            reason=f"probe client error: {type(exc).__name__}: {exc}",
            command_or_probe=_probe_descriptor(probe),
            isolation_level="live-loopback",
        )
    return OracleVerdict(
        fr_id="",
        kind=KIND_SERVICE,
        verdict=VERDICT_PASS if ok else VERDICT_FAIL,
        reason=detail,
        command_or_probe=_probe_descriptor(probe),
        isolation_level="live-loopback",
    )


def _run_oneshot(
    clause: ParsedClause, app_root: Path, cfg: SandboxConfig
) -> OracleVerdict:
    cmd = _resolve_oneshot_cmd(clause, app_root)
    if cmd is None:
        # Unresolved console-script (not pytest/python, no app/bin entry) — fail loud, never exec an
        # arbitrary bare command on the sandbox PATH (harvest H1).
        return OracleVerdict(
            fr_id="",
            kind=KIND_ONESHOT,
            verdict=VERDICT_ERROR,
            reason=f"unresolved console-script {clause.command_argv[0]!r} "
            "(not pytest/python and no app/bin entry) — not run",
            command_or_probe=" ".join(clause.command_argv),
            isolation_level="none",
        )
    local_cfg = SandboxConfig(**{**cfg.__dict__, "wall_timeout_s": max(cfg.wall_timeout_s, _ONESHOT_TIMEOUT_S)})
    result = run_sandboxed(cmd, app_root, local_cfg)
    descriptor = " ".join(cmd)
    if result.violation is not None:
        # Env outcome (timeout / resource kill / launch error) — degrade to error, not fail.
        return OracleVerdict(
            fr_id="",
            kind=KIND_ONESHOT,
            verdict=VERDICT_ERROR,
            reason=f"env: {result.violation}",
            command_or_probe=descriptor,
            isolation_level=result.isolation_level,
        )
    if result.returncode == 0:
        verdict = VERDICT_PASS
        reason = "exit 0"
    else:
        # Exit-code-aware infra-vs-model split (OL-EB-5): a command that cannot launch (rc 127) or a
        # pytest env outcome (interrupted / no-tests / bootstrap crash) DEGRADES to error, not fail.
        verdict = _classify_oneshot(cmd, result.returncode, result.stderr)
        if verdict == VERDICT_ERROR:
            reason = f"env: command could not run ({descriptor}) — exit {result.returncode}"
            if result.stderr:
                reason = f"{reason}: {result.stderr[-400:]}"
        else:
            reason = f"exit {result.returncode}"
            if result.stderr:
                reason = f"{reason}: {result.stderr[-400:]}"
    return OracleVerdict(
        fr_id="",
        kind=KIND_ONESHOT,
        verdict=verdict,
        reason=reason,
        command_or_probe=descriptor,
        isolation_level=result.isolation_level,
    )


def _run_service_boot(
    clause: ParsedClause,
    app_root: Path,
    cfg: SandboxConfig,
    server_cmd: List[str],
    port: int,
    health_path: str,
) -> OracleVerdict:
    """Boot the app and probe it (used when no ``live_port`` is supplied)."""
    probe = clause.probe
    assert probe is not None
    client = _make_probe_client(probe)
    result = run_service_sandboxed(
        server_cmd,
        app_root,
        port,
        client,
        cfg,
        readiness_mode="http",
        health_path=health_path,
    )
    descriptor = _probe_descriptor(probe)
    if result.violation is not None or not result.ready:
        return OracleVerdict(
            fr_id="",
            kind=KIND_SERVICE,
            verdict=VERDICT_ERROR,
            reason=f"env: {result.violation or 'never ready'}",
            command_or_probe=descriptor,
            isolation_level=result.isolation_level,
        )
    ok, detail = result.client_outcome if result.client_outcome else (False, "no outcome")
    return OracleVerdict(
        fr_id="",
        kind=KIND_SERVICE,
        verdict=VERDICT_PASS if ok else VERDICT_FAIL,
        reason=detail,
        command_or_probe=descriptor,
        isolation_level=result.isolation_level,
    )


def run_oracle(
    spec_path: Path | str,
    app_root: Path | str,
    *,
    cfg: Optional[SandboxConfig] = None,
    live_port: Optional[int] = None,
    server_cmd: Optional[List[str]] = None,
    server_port: int = 8099,
    health_path: str = "/health",
) -> List[OracleVerdict]:
    """Run a generated app's runnable ``Verify:`` clauses as an oracle and return per-FR verdicts.

    ``live_port`` — when set (the ORACLE-rung path), service probes hit the already-booted loopback
    app directly; otherwise the runner boots the app via ``server_cmd`` under
    ``run_service_sandboxed``. One-shot clauses always run via ``run_sandboxed`` in ``app_root``.

    Every runnable clause runs through a ``benchmark_matrix.sandbox`` entry; a non-runnable clause
    (``assertion``/``manual``) yields ``skip`` carrying its ``assertion_text`` residue.
    """
    cfg = cfg or SandboxConfig()
    root = Path(app_root)
    clauses = parse_spec(spec_path)
    verdicts: List[OracleVerdict] = []
    for clause in clauses:
        if clause.kind == KIND_ONESHOT:
            v = _run_oneshot(clause, root, cfg)
        elif clause.kind == KIND_SERVICE:
            if live_port is not None:
                v = _probe_live(clause.probe, live_port)
            elif server_cmd is not None:
                v = _run_service_boot(
                    clause, root, cfg, server_cmd, server_port, health_path
                )
            else:
                v = OracleVerdict(
                    fr_id=clause.fr_id,
                    kind=KIND_SERVICE,
                    verdict=VERDICT_ERROR,
                    reason="no live_port or server_cmd to run the probe against",
                    command_or_probe=_probe_descriptor(clause.probe),
                    assertion_text=clause.assertion_text,
                )
                verdicts.append(v)
                continue
        else:
            # assertion / manual → non-runnable residue.
            verdicts.append(
                OracleVerdict(
                    fr_id=clause.fr_id,
                    kind=clause.kind,
                    verdict=VERDICT_SKIP,
                    reason=clause.reason,
                    assertion_text=clause.assertion_text,
                )
            )
            continue
        # Stamp the fr_id + residue onto the runnable verdict (the runners leave fr_id="").
        v = v.model_copy(
            update={"fr_id": clause.fr_id, "assertion_text": clause.assertion_text}
        )
        logger.debug(
            "oracle verdict fr=%s kind=%s verdict=%s isolation=%s",
            v.fr_id,
            v.kind,
            v.verdict,
            v.isolation_level,
            extra={"fr_id": v.fr_id, "verdict": v.verdict},
        )
        verdicts.append(v)
    return verdicts
