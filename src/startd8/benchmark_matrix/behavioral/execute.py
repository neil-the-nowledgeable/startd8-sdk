"""Run a service's behavioral suite for one matrix cell (M-T2.4 wiring, $0 — no LLM).

Orchestrates the M-T2.1 sandbox + M-T2.2 serve resolution + M-T2.3 suite into a single call the
runner uses: resolve how to launch the generated service, host it under ``run_service_sandboxed``,
run the SDK-authored ground-truth suite against it, and return coverage + provenance. Any
environment failure (no launcher, never-ready, sandbox violation, connect error) returns
``degraded`` so the caller folds a degraded term (FR-32), never a 0.

Default-off in the runner — turning it on is the paymentservice pilot (M-T2.4, gated on spend).
"""
from __future__ import annotations

import functools
import os
import re
import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..sandbox import SandboxConfig, run_service_sandboxed
from .ad_suite import run_ad_suite
from .cart_suite import run_cart_suite
from .catalog_suite import PRODUCTS_FILENAME, products_json, run_catalog_suite
from .charge_suite import run_charge_suite
from .checkout_stubs import CheckoutStubHarness, GroundTruth
from .checkout_suite import run_checkout_suite
from .currency_suite import run_currency_suite
from .email_suite import (
    CONFIRMATION_TEMPLATE,
    CONFIRMATION_TEMPLATE_FILENAME,
    run_email_suite,
)
from .contract import StartupContract, resolve_serve_command
from .graphql_pricing_suite import run_graphql_pricing_suite
from .pricing_suite import run_pricing_suite
from .recommendation_stubs import RecommendationDepHarness
from .recommendation_suite import run_recommendation_suite
from .rest_pricing_suite import run_rest_pricing_suite
from .resolved_pricing_suite import run_resolved_pricing_suite
from .shipping_suite import run_shipping_suite

# service name -> behavioral suite (the SDK-authored client). P1+P2 curated stateless set,
# plus the Liferay-derived pricing service variants.
_SUITES: Dict[str, Callable[[int], object]] = {
    "paymentservice": run_charge_suite,
    "cartservice": run_cart_suite,
    "productcatalogservice": run_catalog_suite,
    "currencyservice": run_currency_suite,
    "emailservice": run_email_suite,
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


def provision_catalog_state(workdir: Path, target_files: List[str]) -> List[str]:
    """Materialize the harness-owned ground-truth ``products.json`` into the catalog cell's workdir.

    ProductCatalogService is a stateful-LOCAL leaf: it reads a local catalog file rather than dialing
    a gRPC peer. The harness owns that state (``catalog_suite.products_json()``) so the correct
    ListProducts/GetProduct/SearchProducts responses are fixed BEFORE any model is judged. The Go
    serve command does ``cd src/productcatalogservice && exec ./.bin/server``, so the server's cwd is
    the service dir — we write ``products.json`` THERE (the upstream-OB "next to the binary" reading
    convention) plus the workdir root as a belt-and-suspenders fallback for a server that reads from a
    different cwd. Returns the relative paths written (for provenance)."""
    return _provision_local_asset(workdir, target_files, PRODUCTS_FILENAME, products_json())


def provision_email_template(workdir: Path, target_files: List[str]) -> List[str]:
    """Materialize the harness-owned jinja2 ``confirmation.html`` into the email cell's workdir.

    EmailService is a STATELESS leaf over the wire (Empty response), but the OB convention renders
    the confirmation body from a local jinja2 template. The harness owns that template
    (``email_suite.CONFIRMATION_TEMPLATE``) and provisions it into the launched server's workdir so a
    reference server can render without inventing one — the analogue of catalog's products.json. The
    Python serve command does ``cd src/emailservice && exec python3 <entry>`` (the server's cwd is the
    service dir), so we write the template THERE plus the workdir root as a fallback. Returns the
    relative paths written (for provenance). Harmless no-op for every other service."""
    return _provision_local_asset(workdir, target_files, CONFIRMATION_TEMPLATE_FILENAME,
                                  CONFIRMATION_TEMPLATE)


def _provision_local_asset(workdir: Path, target_files: List[str], filename: str,
                           body: str) -> List[str]:
    """Write a harness-owned ground-truth asset into the service dir (server cwd) + the workdir root."""
    workdir = Path(workdir)
    dests = {Path(".")}  # workdir root (fallback)
    for tf in target_files or []:
        parent = Path(tf).parent
        if str(parent) not in (".", ""):
            dests.add(parent)
    written: List[str] = []
    for rel in dests:
        dest_dir = workdir / rel
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / filename).write_text(body, encoding="utf-8")
        written.append(str(rel / filename))
    return written


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
    runtime_observability: bool = False,
    language: str = "",
) -> BehavioralResult:
    """Execute ``service``'s behavioral suite against the generated code in ``workdir``.

    Returns a :class:`BehavioralResult`. ``has_suite=False`` → this service has no suite yet (the
    caller leaves the composite unchanged). ``degraded=True`` → a suite exists but the service
    couldn't be launched/reached (degrade the functional term, don't score 0).

    ``tier`` (FR-2/FR-6/FR-26): when a suite accepts a ``tier`` kwarg, it is bound here so a
    ``"hardened"`` cell runs the suite's hardened **superset** (baseline assertions + the hard ones).
    Suites that don't accept ``tier`` are unaffected — fully backward-compatible.
    """
    # FR-CO-EXEC: checkoutservice is a 6-way orchestrator; the leaf-suite `client(port)` contract is
    # insufficient (6 dependency stubs must be bound and their `*_SERVICE_ADDR` addresses injected into
    # extra_env BEFORE the SUT launches, then torn down). Route it to the dedicated checkout branch —
    # NOT through `_SUITES` (whose `client(port)` callables have no place to inject stub addresses or
    # snapshot call-counts). This is the single structural divergence from the eight leaf suites.
    if service == "checkoutservice":
        return _run_checkout_cell(seed, workdir, target_files, cfg=cfg, port=port, tier=tier)

    # FR-REC-EXEC: recommendationservice is a 1-dependency mini-orchestrator — it dials productcatalog
    # and returns ids EXCLUDING its input. Like checkout (but with ONE dep), the leaf `client(port)`
    # contract is insufficient: the productcatalog stub must be bound and its `PRODUCT_CATALOG_SERVICE_ADDR`
    # injected BEFORE the SUT launches, then call-counts snapshotted to prove it dialed the catalog.
    if service == "recommendationservice":
        return _run_recommendation_cell(seed, workdir, target_files, cfg=cfg, port=port, tier=tier)

    suite_fn = _SUITES.get(service)
    if suite_fn is None:
        return BehavioralResult(has_suite=False, provenance={"reason": "no behavioral suite for service"})
    # Bind the difficulty tier into the suite only when the suite opts in (accepts a `tier` kwarg).
    # run_service_sandboxed calls client(port), so tier must be pre-bound here.
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
    return _provision_launch_and_score(
        seed, workdir, service, target_files, argv, extra_env, port, suite_fn,
        port_source=port_source, cfg=cfg,
        runtime_observability=runtime_observability, language=language)


def _provision_launch_and_score(
    seed: dict,
    workdir: Path,
    service: str,
    target_files: List[str],
    argv: List[str],
    extra_env: Dict[str, str],
    port: int,
    client: Callable[[int], object],
    *,
    port_source: str = "injected",
    cfg: Optional[SandboxConfig] = None,
    extra_provenance: Optional[Dict] = None,
    runtime_observability: bool = False,
    language: str = "",
) -> BehavioralResult:
    """Shared provision → sandboxed-launch → degrade/model-fault/score core (FR-T2-DEPS/DEPS2).

    Reused by the leaf-suite path and the FR-CO-EXEC checkout branch so both honor identical
    provisioning, readiness, and model-fault-vs-degrade classification. ``argv``/``extra_env`` are the
    already-resolved serve command (the checkout branch has merged ``*_SERVICE_ADDR`` into ``extra_env``
    before calling this); ``client`` is the suite ``client(port)`` to run against the live SUT.
    """
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
    elif lang == "csharp":
        # C# (.NET) lane (FR-X5-DEPS): co-locate demo.proto into the project dir (Grpc.Tools codegens
        # the C# stubs from it at build time — analogue of the Node proto / catalog products.json),
        # then ``dotnet publish`` the service to ``<svc_dir>/.bin/server.dll`` so the _csharp_default
        # launcher (cd <svc_dir> && exec dotnet ./.bin/server.dll) can start it with no compile under
        # the egress-denied sandbox. Publish needs a (cached) NuGet restore — the documented C#-lane
        # network assumption; offline fails closed. Degrade honestly on any env failure (FR-32).
        from .provision import publish_dotnet_service
        proto_src, proto_name = _PROTO_BY_SERVICE.get(service, (_PROTO, "demo.proto"))
        _provision_local_asset(Path(workdir), target_files, proto_name, proto_src.read_text())
        pr = publish_dotnet_service(Path(workdir), target_files)
        if not pr.ok:
            return BehavioralResult(has_suite=True, degraded=True,
                                    provenance={"reason": pr.degraded_reason,
                                                "provision_language": "csharp"})
    else:
        from .provision import provision_workdir
        pr = provision_workdir(Path(workdir), lang, target_files, grpc=(readiness_mode != "http"))
        if not pr.ok:
            return BehavioralResult(has_suite=True, degraded=True,
                                    provenance={"reason": pr.degraded_reason,
                                                "provision_language": pr.language})

    # Stateful-LOCAL leaf state (FR-X5-DEPS): productcatalogservice reads a local products.json. The
    # harness owns the ground-truth catalog and provisions it into the launched server's workdir so the
    # RPC responses are fixed before any model is judged (oracle-first). Done after dep provisioning so
    # the service dir exists; harmless no-op for every other service.
    local_assets: List[str] = []
    local_asset_key = ""
    if service == "productcatalogservice":
        local_assets = provision_catalog_state(Path(workdir), target_files)
        local_asset_key = "catalog_state_files"
    # emailservice is stateless over the wire (Empty response) but renders its confirmation from a
    # local jinja2 template; the harness owns + provisions it (oracle-first), so a reference server
    # never invents a template.
    elif service == "emailservice":
        local_assets = provision_email_template(Path(workdir), target_files)
        local_asset_key = "email_template_files"

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

    def _launch(_argv, _env):
        return run_service_sandboxed(_argv, Path(workdir), port, client, cfg=cfg, extra_env=_env,
                                     readiness_timeout_s=readiness,
                                     readiness_mode=readiness_mode, health_path=health_path)

    # B1 runtime observability (opt-in, guarded, reported-not-scored). Wrap the launch in a
    # span-metrics collector so the service's OWN live telemetry can be bind-checked. Any
    # failure (no collector binary / non-instrumentable language / no telemetry) degrades
    # honestly and NEVER changes the behavioral launch or score.
    runtime_obs = None
    if runtime_observability:
        try:
            from ..observability.metric_descriptor import profile_for_transport
            from ..observability.runtime_fidelity import probe_service_runtime_observability
            _transport = "grpc" if readiness_mode != "http" else "http"
            sr, runtime_obs = probe_service_runtime_observability(
                service_id=service, language=language,
                descriptor=profile_for_transport(_transport), workdir=Path(workdir),
                argv=argv, extra_env=extra_env, run_service=_launch,
            )
        except Exception as exc:  # noqa: BLE001 — an advisory term never breaks the cell
            runtime_obs = {"outcome": "degraded", "coverage": None, "reason": f"probe error: {exc}"}
            sr = _launch(argv, extra_env)
    else:
        sr = _launch(argv, extra_env)

    prov: Dict = {"ready": sr.ready, "isolation_level": sr.isolation_level,
                  "network_isolated": sr.network_isolated, "violation": sr.violation,
                  "port_source": port_source,  # R2-S2: "injected" or "hardcoded:<n>"
                  "server_stderr_tail": (sr.server_stderr or "")[-400:]}
    if runtime_obs is not None:
        prov["runtime_observability"] = runtime_obs
    if local_assets and local_asset_key:
        prov[local_asset_key] = local_assets
    if extra_provenance:
        prov.update(extra_provenance)
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


def _run_checkout_cell(
    seed: dict,
    workdir: Path,
    target_files: List[str],
    *,
    cfg: Optional[SandboxConfig] = None,
    port: Optional[int] = None,
    tier: str = "baseline",
    ground_truth: Optional[GroundTruth] = None,
) -> BehavioralResult:
    """FR-CO-EXEC — the dedicated checkoutservice orchestration branch (the #1-risk step).

    Structurally distinct from the leaf ``client(port)`` path: checkout only behaves correctly when its
    six gRPC dependencies answer, so this branch brings up SDK-authored loopback stubs and runtime-injects
    their ``*_SERVICE_ADDR`` addresses into the SUT's environment **before** it launches, then scores
    per-step coverage from the response + the stubs' call-counters.

    Flow (FR-CO-EXEC a–e):
      (a) read the seed's declared dependency-address env NAMES (``startup.dependency_addr_env``);
      (b) ``harness.start()`` binds the six stubs on free loopback ports → ``addr_map`` ({NAME: addr});
      (c) allocate the SUT's $PORT (after the stubs, B4 port-ordering) + resolve the Go serve command;
      (d) merge ``addr_map`` into ``extra_env`` so the sandboxed Go checkout dials the stubs (FR-CO-10);
      (e) run the SUT under the existing sandbox path; the suite reads ``harness.call_counts`` AFTER
          PlaceOrder returns (passed as a callable so the snapshot is live, FR-CO-8); ``finally`` tears
          down all six stubs (FR-CO-3) — on EVERY path, including launch/readiness/suite exceptions.
    """
    gt = ground_truth or GroundTruth()

    # (a) The seed declares the six dependency-address env NAMES; the harness owns the canonical set.
    # We map the harness's addr_map (keyed by those same NAMES) straight through. If the seed declares a
    # name the harness doesn't bind (a seed/harness drift), it simply won't be injected — surfaced in
    # provenance so it is diagnosable rather than silently wrong.
    contract = StartupContract.from_seed(seed)
    if contract is None:
        # FR-CO-9: without a startup block there is no Go launch + no declared dep-env names → degrade,
        # don't crash (the seed re-author, B1, is the gating prerequisite).
        return BehavioralResult(has_suite=True, degraded=True,
                                provenance={"reason": "checkoutservice seed has no startup block "
                                                      "(FR-CO-9 re-author prerequisite)"})
    declared_names = list((seed or {}).get("startup", {}).get("dependency_addr_env") or [])

    harness = CheckoutStubHarness(gt)
    try:
        # (b) Bind the six stubs FIRST (B4: stubs before the SUT port) → {ENV_NAME: "127.0.0.1:<port>"}.
        addr_map = harness.start()
        # (c) Allocate the SUT port AFTER the stubs are bound (B4 port-ordering minimizes the TOCTOU race
        # window the shipped harness already tolerates), then resolve the Go serve command for it.
        sut_port = port or _free_port()
        serve = resolve_serve_command(seed, target_files, sut_port)
        if serve is None:  # pragma: no cover — guarded by the startup-block check above
            return BehavioralResult(has_suite=True, degraded=True,
                                    provenance={"reason": "no serve command for checkoutservice"})
        argv, extra_env = serve
        # (d) Merge the runtime stub addresses into extra_env BEFORE launch (FR-CO-10). $PORT (from the
        # contract) is already in extra_env; the six *_SERVICE_ADDR values are added here. Injected after
        # the sandbox env-scrub (run_service_sandboxed applies extra_env post-scrub), so they survive.
        injected = dict(addr_map)
        extra_env = {**(extra_env or {}), **injected}
        # Provenance the injected addresses + which declared names were/weren't covered (FR-CO-19).
        missing_names = [n for n in declared_names if n not in addr_map]
        extra_prov = {
            "checkout_injected_addrs": injected,
            "checkout_declared_dep_env": declared_names,
            "checkout_unbound_declared_env": missing_names,
            "suite_kind": "checkout-orchestrator",
        }

        # (e) The suite reads call_counts AFTER PlaceOrder returns — pass the live property as a CALLABLE
        # so the snapshot reflects exactly the deps the SUT dialed during the order (FR-CO-8). A wrong /
        # invented address means the matching stub is never called → count 0 → that step is a real MISS
        # (FR-CO-17), scored as partial coverage, not a degrade.
        client = functools.partial(
            run_checkout_suite, stub_calls=lambda: harness.call_counts, ground_truth=gt)

        result = _provision_launch_and_score(
            seed, workdir, "checkoutservice", target_files, argv, extra_env, sut_port, client,
            port_source="injected", cfg=cfg, extra_provenance=extra_prov)
        # FR-CO-19: record the final dialed-dep call-counts alongside the per-step suite results.
        result.provenance["checkout_call_counts"] = dict(harness.call_counts)
        return result
    finally:
        # FR-CO-3: deterministic, exception-safe teardown of all six stubs on EVERY exit path
        # (SUT-launch exception, readiness timeout, client/suite error, or success). harness.stop() is
        # idempotent and never raises, so no stub server / loopback port is ever leaked.
        harness.stop()


def _run_recommendation_cell(
    seed: dict,
    workdir: Path,
    target_files: List[str],
    *,
    cfg: Optional[SandboxConfig] = None,
    port: Optional[int] = None,
    tier: str = "baseline",
    harness: Optional[RecommendationDepHarness] = None,
) -> BehavioralResult:
    """FR-REC-EXEC — the dedicated recommendationservice branch (a 1-dependency mini-orchestrator).

    Structurally identical to ``_run_checkout_cell`` but with ONE dependency stub (productcatalog):
    recommendation only behaves correctly when its productcatalog peer answers ``ListProducts``, so
    this branch brings up the SDK-authored loopback stub, runtime-injects ``PRODUCT_CATALOG_SERVICE_ADDR``
    into the SUT's environment BEFORE it launches, then scores from the responses + the stub's
    call-counter (proving the catalog was actually dialed, not hardcoded).

    Flow (mirrors checkout a–e, single dep):
      (a) require a startup block (declares the dependency-addr env name + launch);
      (b) ``harness.start()`` binds the productcatalog stub on a free loopback port → ``addr_map``;
      (c) allocate the SUT's $PORT (after the stub) + resolve the serve command;
      (d) merge ``addr_map`` into ``extra_env`` so the sandboxed SUT dials the stub;
      (e) run the SUT under the shared launch/score core; the suite reads ``harness.call_counts``
          AFTER the RPCs return (passed as a callable for a live snapshot); ``finally`` tears the stub
          down on EVERY path.
    """
    contract = StartupContract.from_seed(seed)
    if contract is None:
        # No startup block → no launch + no declared dep-env name → degrade, don't crash.
        return BehavioralResult(has_suite=True, degraded=True,
                                provenance={"reason": "recommendationservice seed has no startup block "
                                                      "(FR-REC re-author prerequisite)"})
    declared_names = list((seed or {}).get("startup", {}).get("dependency_addr_env") or [])

    h = harness or RecommendationDepHarness()
    try:
        # (b) Bind the single productcatalog stub FIRST → {PRODUCT_CATALOG_SERVICE_ADDR: "127.0.0.1:<port>"}.
        addr_map = h.start()
        # (c) Allocate the SUT port AFTER the stub is bound, then resolve the serve command.
        sut_port = port or _free_port()
        serve = resolve_serve_command(seed, target_files, sut_port)
        if serve is None:  # pragma: no cover — guarded by the startup-block check above
            return BehavioralResult(has_suite=True, degraded=True,
                                    provenance={"reason": "no serve command for recommendationservice"})
        argv, extra_env = serve
        # (d) Merge the runtime stub address into extra_env BEFORE launch. Injected after the sandbox
        # env-scrub (run_service_sandboxed applies extra_env post-scrub), so it survives.
        injected = dict(addr_map)
        extra_env = {**(extra_env or {}), **injected}
        missing_names = [n for n in declared_names if n not in addr_map]
        extra_prov = {
            "recommendation_injected_addrs": injected,
            "recommendation_declared_dep_env": declared_names,
            "recommendation_unbound_declared_env": missing_names,
            "suite_kind": "recommendation-orchestrator",
        }

        # (e) The suite reads call_counts AFTER the RPCs return — pass the live property as a CALLABLE so
        # the snapshot reflects whether the SUT dialed productcatalog. A wrong / invented address (or a
        # service returning hardcoded ids) means the stub is never called → count 0 → every case is a
        # real MISS (catalog_dialed gate), scored as coverage, not a degrade.
        client = functools.partial(
            run_recommendation_suite, stub_calls=lambda: h.call_counts,
            ground_truth=h.ground_truth, catalog_ids=h.catalog_ids)

        result = _provision_launch_and_score(
            seed, workdir, "recommendationservice", target_files, argv, extra_env, sut_port, client,
            port_source="injected", cfg=cfg, extra_provenance=extra_prov)
        result.provenance["recommendation_call_counts"] = dict(h.call_counts)
        return result
    finally:
        # Deterministic, exception-safe teardown on EVERY exit path (launch/readiness/suite error or
        # success). stop() is idempotent and never raises, so no stub server / loopback port leaks.
        h.stop()
