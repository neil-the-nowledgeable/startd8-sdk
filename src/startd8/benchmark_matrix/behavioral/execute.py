"""Run a service's behavioral suite for one matrix cell (M-T2.4 wiring, $0 — no LLM).

Orchestrates the M-T2.1 sandbox + M-T2.2 serve resolution + M-T2.3 suite into a single call the
runner uses: resolve how to launch the generated service, host it under ``run_service_sandboxed``,
run the SDK-authored ground-truth suite against it, and return coverage + provenance. Any
environment failure (no launcher, never-ready, sandbox violation, connect error) returns
``degraded`` so the caller folds a degraded term (FR-32), never a 0.

Default-off in the runner — turning it on is the paymentservice pilot (M-T2.4, gated on spend).
"""
from __future__ import annotations

import os
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
from .contract import StartupContract, resolve_serve_command
from .graphql_pricing_suite import run_graphql_pricing_suite
from .pricing_suite import run_pricing_suite
from .rest_pricing_suite import run_rest_pricing_suite
from .resolved_pricing_suite import run_resolved_pricing_suite
from .shipping_suite import run_shipping_suite

# service name -> behavioral suite (the SDK-authored client). P1+P2 curated stateless set,
# plus the Liferay-derived pricing service variants.
_SUITES: Dict[str, Callable[[int], object]] = {
    "paymentservice": run_charge_suite,
    "currencyservice": run_currency_suite,
    "shippingservice": run_shipping_suite,
    "adservice": run_ad_suite,
    "pricingservice": run_pricing_suite,
    "rest-pricingservice": run_rest_pricing_suite,
    "graphql-pricingservice": run_graphql_pricing_suite,
    "resolvedpriceservice": run_resolved_pricing_suite,
}

_NODE_RUNTIME = Path(__file__).parent / "node_runtime"
_PROTO = Path(__file__).parent / "demo.proto"
_PRICING_PROTO = Path(__file__).parent / "pricing.proto"
_RESOLVED_PRICING_PROTO = Path(__file__).parent / "resolved_pricing.proto"

# FR-14: which proto a service's generated server loads, as (source file, on-disk name). Online
# Boutique services all share demo.proto (the default); the hardened pricingservice ships its own.
# Keying off the service keeps every OB cell's provisioning byte-identical.
_PROTO_BY_SERVICE: Dict[str, tuple] = {
    "pricingservice": (_PRICING_PROTO, "pricing.proto"),
    "resolvedpriceservice": (_RESOLVED_PRICING_PROTO, "pricing.proto"),
}

# FR-T2-PROTO: conventional locations a generated server loads its proto from. The pilot saw models
# use root, protos/, proto/, and pb/ — provision the proto at all of them so the model's choice
# doesn't decide whether the cell runs. (Path-pinning via the startup contract is OQ-T2-6.)
_PROTO_DEST_SUBDIRS = ("", "protos", "proto", "pb", "lib/proto")

# R3-F3 / FR-T2-DEPS2: a missing dependency is a HARNESS provisioning gap (degrade, FR-32) UNLESS the
# module the model reached for is off-contract for the service's wire protocol — e.g. a gRPC-contract
# service that require()s an HTTP/GraphQL server framework. That is a MODEL fault (the model abandoned
# the contract it was given), so the cell is scored real zero behavioral coverage and floored — never
# degraded to a free structural 1.0 that would outrank an honest service which merely failed its RPCs.
# Protocol-appropriate or unknown missing modules (grpc-js / pino / a vendored dep) stay a degrade.
_HTTP_SERVER_FRAMEWORKS = frozenset({
    "express", "fastify", "koa", "@koa/router", "hapi", "@hapi/hapi", "connect", "restify",
    "body-parser", "apollo-server", "@apollo/server", "apollo-server-express", "graphql-yoga",
    "@nestjs/core", "next",
})
_GRPC_PACKAGES = frozenset({"@grpc/grpc-js", "grpc", "@grpc/proto-loader"})


def _package_root(module: str) -> str:
    """Top-level npm package name for a require() specifier (handles ``@scope/name`` and subpaths)."""
    if module.startswith("@"):
        return "/".join(module.split("/")[:2])
    return module.split("/")[0]


def _is_off_contract_dep(module: str, readiness_mode: str) -> bool:
    """True when ``module`` shows the model built the WRONG wire protocol for the startup contract:
    an HTTP/GraphQL server framework on a gRPC (``"tcp"``) contract, or a gRPC package on an HTTP
    contract. Such a service can never satisfy its behavioral suite → model fault (R3-F3): floor it,
    don't degrade. Anything else (a protocol-appropriate or unrecognized dep) stays a harness gap."""
    pkg = _package_root(module)
    if readiness_mode == "http":
        return pkg in _GRPC_PACKAGES
    return pkg in _HTTP_SERVER_FRAMEWORKS


# R2-S2: the harness injects an ephemeral $PORT, but a model may ignore it and hardcode a listen port
# — then the readiness probe on the injected port fails and the cell FALSE-degrades instead of being
# behaviorally scored. We detect this from the generated source and probe the hardcoded port instead.
# Safe by construction: if the source reads the PORT env at all (incl. `process.env.PORT || 8080`),
# the env match wins and we keep the injected port — so a well-behaved model is never overridden.
_PORT_ENV_RE = re.compile(
    r"""(?:process\.env\.PORT\b
        | process\.env\[\s*['"]PORT['"]
        | os\.environ(?:\.get)?\(?\s*\[?\s*['"]PORT['"]
        | os\.getenv\(\s*['"]PORT['"]
        | getenv\(\s*['"]PORT['"]
        | System\.getenv\(\s*['"]PORT['"])""",
    re.IGNORECASE | re.VERBOSE,
)
_BIND_PORT_RES = (
    re.compile(r"""['"`]\s*(?:0\.0\.0\.0|127\.0\.0\.1|localhost|\[?::1?\]?)?\s*:\s*(\d{2,5})\b"""),  # "host:port"
    re.compile(r"""\.listen\(\s*(\d{2,5})\b"""),                                                     # .listen(8080)
    re.compile(r"""\b(?:PORT|port)\s*[:=]\s*(\d{2,5})\b"""),                                          # PORT = 8080
)


def _detect_effective_port(workdir: Path, target_files: List[str], injected_port: int):
    """R2-S2: return ``(port, source)`` for readiness/client. ``source`` is ``"injected"`` (the model
    reads ``$PORT``, or no confident literal was found) or ``"hardcoded:<n>"``. Conservative: any
    ambiguity falls back to the injected port (today's behavior), so this can only rescue cells that
    would otherwise false-degrade — it never demotes a model that honors the injected port."""
    text = ""
    for tf in target_files or []:
        try:
            text += (Path(workdir) / tf).read_text(encoding="utf-8", errors="ignore") + "\n"
        except OSError:
            continue
    if not text or _PORT_ENV_RE.search(text):
        return injected_port, "injected"
    for rx in _BIND_PORT_RES:
        m = rx.search(text)
        if m:
            cand = int(m.group(1))
            if 1 <= cand <= 65535 and cand != injected_port:
                return cand, f"hardcoded:{cand}"
    return injected_port, "injected"


def prepare_node_workdir(
    workdir: Path,
    target_files: Optional[List[str]] = None,
    *,
    proto_src: Path = _PROTO,
    proto_name: str = "demo.proto",
) -> bool:
    """Materialize the vendored offline runtime closure + proto into a Node cell workdir (FR-T2-DEPS).

    Copies ``node_runtime/node_modules`` (the full closure: gRPC + pino + uuid — FR-T2-DEPS) and the
    service's proto at every conventional location (FR-T2-PROTO) so a model-generated Node server can
    start with no network regardless of where it loads the proto. ``target_files`` adds the
    **service-relative** locations (next to the generated server + its ``proto/`` subdir) — the pilot
    showed models also load it from ``src/<service>/<proto>``. ``proto_src``/``proto_name`` default to
    Online Boutique's ``demo.proto`` (FR-14); the pricingservice cell passes its own ``pricing.proto``.
    Returns False when the runtime hasn't been vendored yet (run ``node_runtime/vendor.sh`` first) →
    caller degrades (FR-T2-DEPS2)."""
    src_nm = _NODE_RUNTIME / "node_modules"
    if not src_nm.is_dir():
        return False
    workdir = Path(workdir)
    dst_nm = workdir / "node_modules"
    if not dst_nm.exists():
        # Hardlink the read-only vendored closure instead of byte-copying it per cell (H3): grpc-js +
        # proto-loader is tens of MB / thousands of files, copied into every nodejs cell. Hardlinks are
        # instant and safe (the cell never writes node_modules). Fall back to a real copy cross-device.
        try:
            shutil.copytree(src_nm, dst_nm, copy_function=os.link)
        except OSError:
            shutil.rmtree(dst_nm, ignore_errors=True)
            shutil.copytree(src_nm, dst_nm)
    if proto_src.exists():
        subdirs = list(_PROTO_DEST_SUBDIRS)
        for tf in target_files or []:           # service-relative: src/<service>/ and src/<service>/proto/
            parent = Path(tf).parent
            if str(parent) not in (".", ""):
                subdirs += [str(parent), str(parent / "proto")]
        for sub in dict.fromkeys(subdirs):       # de-dupe, preserve order
            dest = workdir / sub if sub else workdir
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(proto_src, dest / proto_name)
    return True


@dataclass
class BehavioralResult:
    has_suite: bool                       # a behavioral suite exists for this service at all
    functional: Optional[float] = None    # coverage [0,1] when the suite produced a score; else None
    degraded: bool = False                # suite exists but couldn't run (env outcome, FR-32)
    model_fault: bool = False             # R3-F3: launch failed because the model went off-contract
                                          # (wrong wire protocol) → floor, NOT degrade (FR-T2-DEPS2)
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
    tier: str = "baseline",
) -> BehavioralResult:
    """Execute ``service``'s behavioral suite against the generated code in ``workdir``.

    Returns a :class:`BehavioralResult`. ``has_suite=False`` → this service has no suite yet (the
    caller leaves the composite unchanged). ``degraded=True`` → a suite exists but the service
    couldn't be launched/reached (degrade the functional term, don't score 0).

    ``tier`` (FR-2/FR-6/FR-26): when a suite accepts a ``tier`` kwarg, it is bound here so a
    ``"hardened"`` cell runs the suite's hardened **superset** (baseline assertions + the hard ones).
    Suites that don't accept ``tier`` are unaffected — fully backward-compatible.
    """
    suite_fn = _SUITES.get(service)
    if suite_fn is None:
        return BehavioralResult(has_suite=False, provenance={"reason": "no behavioral suite for service"})
    # Bind the difficulty tier into the suite only when the suite opts in (accepts a `tier` kwarg).
    # run_service_sandboxed calls client(port), so tier must be pre-bound here.
    import functools
    import inspect
    if "tier" in inspect.signature(suite_fn).parameters:
        suite_fn = functools.partial(suite_fn, tier=tier)

    port = port or _free_port()
    # R2-S2: if the generated server ignores the injected $PORT and hardcodes a listen port, probe
    # that port instead of false-degrading. Detected from source; injected port wins on any ambiguity.
    port, port_source = _detect_effective_port(Path(workdir), target_files, port)
    serve = resolve_serve_command(seed, target_files, port)
    if serve is None:
        return BehavioralResult(has_suite=True, degraded=True,
                                provenance={"reason": "no serve command (no contract / unknown language)"})
    argv, extra_env = serve
    lang = ((seed or {}).get("service_metadata", {}).get("language") or (seed or {}).get("language"))
    # Readiness mode from the seed's startup contract (FR-5/FR-11): "tcp" (gRPC default) or "http"
    # (REST lane). Drives both provisioning (REST skips the grpc/proto runtime) and the readiness probe.
    contract = StartupContract.from_seed(seed)
    readiness_mode = contract.readiness if contract else "tcp"
    health_path = contract.health_path if contract else "/health"

    # Provision the cell's deps at PREPARE time (before the egress-denied run), per language (P1).
    # Node uses the offline vendored closure (safest); others install securely (FR-P1-SEC-1..5).
    if argv and argv[0] == "node":
        proto_src, proto_name = _PROTO_BY_SERVICE.get(service, (_PROTO, "demo.proto"))
        if not prepare_node_workdir(Path(workdir), target_files,
                                    proto_src=proto_src, proto_name=proto_name):
            return BehavioralResult(has_suite=True, degraded=True,
                                    provenance={"reason": "node runtime not vendored — run node_runtime/vendor.sh"})
    else:
        from .provision import provision_workdir
        pr = provision_workdir(Path(workdir), lang, target_files, grpc=(readiness_mode != "http"))
        if not pr.ok:
            return BehavioralResult(has_suite=True, degraded=True,
                                    provenance={"reason": pr.degraded_reason,
                                                "provision_language": pr.language})

    # Python deps install to <workdir>/.pydeps (provision.py --target). The sandbox scrubs PYTHONPATH,
    # so a launched Python server can't import them unless we re-inject the path via extra_env (which is
    # applied AFTER the scrub). Harmless when .pydeps is absent (stdlib REST cells). Surfaced by the
    # GraphQL e2e (graphql-core in .pydeps); the stdlib REST lane never needed it.
    if lang == "python":
        extra_env = {**(extra_env or {}), "PYTHONPATH": str(Path(workdir) / ".pydeps")}

    # Readiness window (option A): pilots showed servers that are alive but slow to bind on loopback
    # hit the old 15s node cap and degraded as "never became ready". Use 30s for all languages (Go
    # already needed it for binary startup) to recover slow-binding cells; genuine crashes (rc=1) exit
    # immediately and are unaffected.
    readiness = 30.0
    sr = run_service_sandboxed(argv, Path(workdir), port, suite_fn, cfg=cfg, extra_env=extra_env,
                               readiness_timeout_s=readiness,
                               readiness_mode=readiness_mode, health_path=health_path)
    prov: Dict = {"ready": sr.ready, "isolation_level": sr.isolation_level,
                  "network_isolated": sr.network_isolated, "violation": sr.violation,
                  "port_source": port_source,  # R2-S2: "injected" or "hardcoded:<n>"
                  "server_stderr_tail": (sr.server_stderr or "")[-400:]}
    if not sr.ready or sr.violation is not None:
        # FR-T2-DEPS2 / FR-T2-PROV: name WHY it couldn't start so a provisioning gap is diagnosable
        # (a missing module / proto path) rather than an opaque "never ready".
        stderr = sr.server_stderr or ""
        mod = re.search(r"Cannot find module '([^']+)'", stderr)
        if mod:
            missing = mod.group(1)
            prov["missing_module"] = missing
            # R3-F3: an off-contract dep (e.g. `express` on a gRPC service) is a model fault, not a
            # harness provisioning gap — score it real zero coverage + floor, never a degraded 1.0.
            if _is_off_contract_dep(missing, readiness_mode):
                prov["model_fault"] = (
                    f"off-contract dependency '{missing}' for a {readiness_mode}-contract service "
                    "(R3-F3): the model abandoned the wire protocol it was given")
                return BehavioralResult(has_suite=True, functional=0.0, degraded=False,
                                        model_fault=True, provenance=prov)
        proto = re.search(r"([\w./-]*\.proto)", stderr)  # any proto (demo.proto, pricing.proto, …)
        if proto:
            prov["attempted_proto_path"] = proto.group(1)
        return BehavioralResult(has_suite=True, degraded=True, provenance=prov)

    suite_res = sr.client_outcome
    if suite_res is None or getattr(suite_res, "connect_error", ""):
        prov["connect_error"] = getattr(suite_res, "connect_error", "no suite result")
        return BehavioralResult(has_suite=True, degraded=True, provenance=prov)

    prov["suite"] = suite_res.to_dict()
    return BehavioralResult(has_suite=True, functional=suite_res.coverage, degraded=False, provenance=prov)
