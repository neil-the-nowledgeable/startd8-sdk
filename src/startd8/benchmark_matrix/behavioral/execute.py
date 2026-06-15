"""Run a service's behavioral suite for one matrix cell (M-T2.4 wiring, $0 — no LLM).

Orchestrates the M-T2.1 sandbox + M-T2.2 serve resolution + M-T2.3 suite into a single call the
runner uses: resolve how to launch the generated service, host it under ``run_service_sandboxed``,
run the SDK-authored ground-truth suite against it, and return coverage + provenance. Any
environment failure (no launcher, never-ready, sandbox violation, connect error) returns
``degraded`` so the caller folds a degraded term (FR-32), never a 0.

Default-off in the runner — turning it on is the paymentservice pilot (M-T2.4, gated on spend).
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..sandbox import SandboxConfig, run_service_sandboxed
from .charge_suite import run_charge_suite
from .contract import resolve_serve_command

# service name -> behavioral suite (the SDK-authored client). Only the paymentservice pilot today.
_SUITES: Dict[str, Callable[[int], object]] = {"paymentservice": run_charge_suite}


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

    sr = run_service_sandboxed(argv, Path(workdir), port, suite_fn, cfg=cfg, extra_env=extra_env)
    prov: Dict = {"ready": sr.ready, "isolation_level": sr.isolation_level,
                  "network_isolated": sr.network_isolated, "violation": sr.violation,
                  "server_stderr_tail": (sr.server_stderr or "")[-400:]}
    if not sr.ready or sr.violation is not None:
        return BehavioralResult(has_suite=True, degraded=True, provenance=prov)

    suite_res = sr.client_outcome
    if suite_res is None or getattr(suite_res, "connect_error", ""):
        prov["connect_error"] = getattr(suite_res, "connect_error", "no suite result")
        return BehavioralResult(has_suite=True, degraded=True, provenance=prov)

    prov["suite"] = suite_res.to_dict()
    return BehavioralResult(has_suite=True, functional=suite_res.coverage, degraded=False, provenance=prov)
