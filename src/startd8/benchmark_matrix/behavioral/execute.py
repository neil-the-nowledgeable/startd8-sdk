"""Run a service's behavioral suite for one matrix cell (M-T2.4 wiring, $0 — no LLM).

Orchestrates the M-T2.1 sandbox + M-T2.2 serve resolution + M-T2.3 suite into a single call the
runner uses: resolve how to launch the generated service, host it under ``run_service_sandboxed``,
run the SDK-authored ground-truth suite against it, and return coverage + provenance. Any
environment failure (no launcher, never-ready, sandbox violation, connect error) returns
``degraded`` so the caller folds a degraded term (FR-32), never a 0.

Default-off in the runner — turning it on is the paymentservice pilot (M-T2.4, gated on spend).
"""
from __future__ import annotations

import re
import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..sandbox import SandboxConfig, run_service_sandboxed
from .ad_suite import run_ad_suite
from .charge_suite import run_charge_suite
from .currency_suite import run_currency_suite
from .contract import resolve_serve_command
from .shipping_suite import run_shipping_suite

# service name -> behavioral suite (the SDK-authored client). P1+P2 curated stateless set.
_SUITES: Dict[str, Callable[[int], object]] = {
    "paymentservice": run_charge_suite,
    "currencyservice": run_currency_suite,
    "shippingservice": run_shipping_suite,
    "adservice": run_ad_suite,
}

_NODE_RUNTIME = Path(__file__).parent / "node_runtime"
_PROTO = Path(__file__).parent / "demo.proto"

# FR-T2-PROTO: conventional locations a generated server loads its proto from. The pilot saw models
# use root, protos/, proto/, and pb/ — provision the proto at all of them so the model's choice
# doesn't decide whether the cell runs. (Path-pinning via the startup contract is OQ-T2-6.)
_PROTO_DEST_SUBDIRS = ("", "protos", "proto", "pb", "lib/proto")


def prepare_node_workdir(workdir: Path, target_files: Optional[List[str]] = None) -> bool:
    """Materialize the vendored offline runtime closure + proto into a Node cell workdir (FR-T2-DEPS).

    Copies ``node_runtime/node_modules`` (the full closure: gRPC + pino + uuid — FR-T2-DEPS) and
    ``demo.proto`` at every conventional location (FR-T2-PROTO) so a model-generated Node server can
    start with no network regardless of where it loads the proto. ``target_files`` adds the
    **service-relative** locations (next to the generated server + its ``proto/`` subdir) — the pilot
    showed models also load it from ``src/<service>/demo.proto``. Returns False when the runtime
    hasn't been vendored yet (run ``node_runtime/vendor.sh`` first) → caller degrades (FR-T2-DEPS2)."""
    src_nm = _NODE_RUNTIME / "node_modules"
    if not src_nm.is_dir():
        return False
    workdir = Path(workdir)
    dst_nm = workdir / "node_modules"
    if not dst_nm.exists():
        shutil.copytree(src_nm, dst_nm)
    if _PROTO.exists():
        subdirs = list(_PROTO_DEST_SUBDIRS)
        for tf in target_files or []:           # service-relative: src/<service>/ and src/<service>/proto/
            parent = Path(tf).parent
            if str(parent) not in (".", ""):
                subdirs += [str(parent), str(parent / "proto")]
        for sub in dict.fromkeys(subdirs):       # de-dupe, preserve order
            dest = workdir / sub if sub else workdir
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(_PROTO, dest / "demo.proto")
    return True


@dataclass
class BehavioralResult:
    has_suite: bool                       # a behavioral suite exists for this service at all
    functional: Optional[float] = None    # coverage [0,1] when the suite produced a score; else None
    degraded: bool = False                # suite exists but couldn't run (env outcome, FR-32)
    provenance: Dict = field(default_factory=dict)  # FR-T2-PROV


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_behavioral_cell(
    seed: dict,
    workdir: Path,
    service: str,
    target_files: List[str],
    *,
    cfg: Optional[SandboxConfig] = None,
    port: Optional[int] = None,
) -> BehavioralResult:
    """Execute ``service``'s behavioral suite against the generated code in ``workdir``.

    Returns a :class:`BehavioralResult`. ``has_suite=False`` → this service has no suite yet (the
    caller leaves the composite unchanged). ``degraded=True`` → a suite exists but the service
    couldn't be launched/reached (degrade the functional term, don't score 0).
    """
    suite_fn = _SUITES.get(service)
    if suite_fn is None:
        return BehavioralResult(has_suite=False, provenance={"reason": "no behavioral suite for service"})

    port = port or _free_port()
    serve = resolve_serve_command(seed, target_files, port)
    if serve is None:
        return BehavioralResult(has_suite=True, degraded=True,
                                provenance={"reason": "no serve command (no contract / unknown language)"})
    argv, extra_env = serve

    # Provision the cell's deps at PREPARE time (before the egress-denied run), per language (P1).
    # Node uses the offline vendored closure (safest); others install securely (FR-P1-SEC-1..5).
    if argv and argv[0] == "node":
        if not prepare_node_workdir(Path(workdir), target_files):
            return BehavioralResult(has_suite=True, degraded=True,
                                    provenance={"reason": "node runtime not vendored — run node_runtime/vendor.sh"})
    else:
        from .provision import provision_workdir
        lang = ((seed or {}).get("service_metadata", {}).get("language")
                or (seed or {}).get("language"))
        pr = provision_workdir(Path(workdir), lang, target_files)
        if not pr.ok:
            return BehavioralResult(has_suite=True, degraded=True,
                                    provenance={"reason": pr.degraded_reason,
                                                "provision_language": pr.language})

    sr = run_service_sandboxed(argv, Path(workdir), port, suite_fn, cfg=cfg, extra_env=extra_env)
    prov: Dict = {"ready": sr.ready, "isolation_level": sr.isolation_level,
                  "network_isolated": sr.network_isolated, "violation": sr.violation,
                  "server_stderr_tail": (sr.server_stderr or "")[-400:]}
    if not sr.ready or sr.violation is not None:
        # FR-T2-DEPS2 / FR-T2-PROV: name WHY it couldn't start so a provisioning gap is diagnosable
        # (a missing module / proto path) rather than an opaque "never ready".
        stderr = sr.server_stderr or ""
        mod = re.search(r"Cannot find module '([^']+)'", stderr)
        if mod:
            prov["missing_module"] = mod.group(1)
        proto = re.search(r"([\w./-]*demo\.proto)", stderr)
        if proto:
            prov["attempted_proto_path"] = proto.group(1)
        return BehavioralResult(has_suite=True, degraded=True, provenance=prov)

    suite_res = sr.client_outcome
    if suite_res is None or getattr(suite_res, "connect_error", ""):
        prov["connect_error"] = getattr(suite_res, "connect_error", "no suite result")
        return BehavioralResult(has_suite=True, degraded=True, provenance=prov)

    prov["suite"] = suite_res.to_dict()
    return BehavioralResult(has_suite=True, functional=suite_res.coverage, degraded=False, provenance=prov)
