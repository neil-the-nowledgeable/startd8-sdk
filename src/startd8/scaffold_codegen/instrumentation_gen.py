# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Instrumentation-Generation Framework — language-AGNOSTIC by construction (Go is the first renderer, not the last).

The Extra-Credit capability (REQ FR-XC): close an observability SUBSTRATE gap by *generating the instrumentation*
that makes a subject emit the metrics its generated artifacts want. Ported from the Harbor FDE's proven reference
impl (`analysis/instrumentation-gen/framework.py`; compile-gate + emit-gate verified against real Harbor source).

    InstrumentationGap  ──►  InstrumentationContract   (LANGUAGE-AGNOSTIC: "what to wire", in semconv terms)
                                     │
                                     ▼
                        RendererRegistry.get(language)  ──►  InstrumentationRenderer  (PER-LANGUAGE: contract → Patch)
                                     │                         (GoOtelRenderer first; Python/Ruby/TS/Java next)
                                     ▼
                              VerificationGate           (LANGUAGE-AGNOSTIC: fork → apply → boot → emit? → bind?)

Only the Renderer is per-language. The Contract, the Registry dispatch, the 3-tier resolution, and the
Verification gate are SHARED — so **adding a language = registering one Renderer, nothing else** (the same shape
RepoProbe already uses for extraction via its per-language ``GroundTruth`` extractor registry).

3-tier resolution (mirrors the SDK TODO-Completion A/B/C — ``todo_scanner`` classes):
  * ``TIER_DETERMINISTIC``  — the renderer has a template for (language × mechanism); pure fill.
  * ``TIER_CONTRACT_FILL``  — template exists but slots need subject values (endpoint, existing setup).
  * ``TIER_LLM_FILL``       — novel (language × mechanism), no template; an LLM generates, GROUNDED by the
                              contract + source and GATED by verification. The renderer degrades honestly:
                              missing evidence ⇒ a lower tier, never a false "deterministic".

HONESTY GATE (FR-XC-3, non-negotiable): a gap counts CLOSED only when the generated patch is applied to a FORK
(never the read-only subject clone), booted, and VERIFIED — target series emit AND the previously-unbound
artifacts bind. Unverified generation does not count. The framework produces the ``Patch``; ``VerificationGate``
is the separate, language-agnostic honesty step the harness runs on a fork.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# ── tiers ────────────────────────────────────────────────────────────────────────────────────────
TIER_DETERMINISTIC = "deterministic-template"
TIER_CONTRACT_FILL = "contract-fill"
TIER_LLM_FILL = "llm-fill"


# ── language-agnostic data model ───────────────────────────────────────────────────────────────────
@dataclass
class InstrumentationGap:
    """What the coverage analysis found: a subject/service that SHOULD emit metrics but doesn't."""

    subject: str
    service: str
    language: str  # detected stack (RepoProbe Scout) — dispatches the renderer
    missing_families: List[str]  # semconv names, e.g. ["http.server.request.duration", "http.server.request.body.size"]
    mechanism: str  # grounded finding, e.g. "otelhttp present, wired trace-only (no MeterProvider)"
    #: HOW the subject EXPOSES metrics — grounded, load-bearing: a patch must match this or it verifies NOTHING.
    #: ``prometheus-scrape`` ⇒ the subject serves /metrics (promhttp) → use the OTel Prometheus exporter (default
    #: registry) so the new metrics land on the SAME scrapeable endpoint. ``otlp-push`` ⇒ use otlpmetrichttp.
    #: (Learned on Harbor: an OTLP-push patch sends metrics to the collector, NOT the :19091 scraper.)
    export_mechanism: str = "prometheus-scrape"
    source_evidence: Dict[str, str] = field(default_factory=dict)  # {claim: "file:line"} — Ground-Before-Assert


#: Mechanisms that are RUNTIME-COMPOSED — the metrics are emitted by the runtime/proxy, not by any source the
#: subject ships (Istio/Envoy data-plane ``istio_requests_total``; a sidecar). There is NO source to instrument →
#: instrumentation-generation cannot close it (NOT a framework defect — it's the subject's shape). Such a gap is
#: Extra-Credit **architecturally-hard**, resolved by LIVE-SCRAPE, never by a renderer.
_RUNTIME_COMPOSED_MARKERS = ("envoy", "runtime-composed", "sidecar-proxy", "not-source", "runtime-emitted")


@dataclass
class InstrumentationContract:
    """LANGUAGE-AGNOSTIC 'what to wire', in semconv/OTel terms. Every language renderer implements THIS."""

    emit_families: List[str]  # the semconv families to make emit
    via: str  # the mechanism, semconv-level: e.g. "otel-meter-provider-on-existing-http-instrumentation"
    requires: List[str]  # abstract steps: ["init MeterProvider", "attach it to the http server instrumentation"]
    export_mechanism: str = "prometheus-scrape"  # carried from the gap — decides the exporter the renderer emits
    source_instrumentable: bool = True  # False ⇒ runtime-composed (Envoy) → not closeable by generation; live-scrape only
    source_evidence: Dict[str, str] = field(default_factory=dict)

    @staticmethod
    def from_gap(gap: "InstrumentationGap") -> "InstrumentationContract":
        """Derive the language-agnostic contract from the grounded gap. NO language specifics here."""
        mech = gap.mechanism.lower()
        # BOUNDARY FIRST: a runtime-composed surface has no source to instrument (Istio/Envoy data-plane).
        if any(m in mech for m in _RUNTIME_COMPOSED_MARKERS):
            return InstrumentationContract(
                emit_families=gap.missing_families,
                via="runtime-composed",
                requires=["(none — metrics are runtime-emitted; close by LIVE-SCRAPE + traffic, not by generation)"],
                export_mechanism=gap.export_mechanism,
                source_instrumentable=False,
                source_evidence=gap.source_evidence,
            )
        # The gap's mechanism tells us the abstract remedy; the renderer makes it concrete per language.
        http_semconv = any(f.startswith("http.server") for f in gap.missing_families)
        if http_semconv and ("otelhttp" in mech or "http-instrumentation" in mech):
            return InstrumentationContract(
                emit_families=gap.missing_families,
                via="otel-meter-provider-on-existing-http-instrumentation",
                requires=[
                    "init MeterProvider (matching the subject's export mechanism)",
                    "attach MeterProvider to the existing HTTP-server instrumentation",
                ],
                export_mechanism=gap.export_mechanism,
                source_evidence=gap.source_evidence,
            )
        # extend: db/messaging/otel-sdk-meter/prometheus-client/custom mechanisms → their own abstract contracts
        return InstrumentationContract(
            emit_families=gap.missing_families,
            via="otel-meter-provider-generic",
            requires=["init MeterProvider", "register a meter and instrument the code paths"],
            export_mechanism=gap.export_mechanism,
            source_evidence=gap.source_evidence,
        )


#: The renderer ROADMAP (grounded by the pilot-roster scout, 2026-08-10). Adding a language = registering ONE
#: renderer. ``source_instrumentable`` marks whether the framework CAN target it (vs live-scrape-only).
PLANNED_RENDERERS: Dict[str, Dict[str, str]] = {
    "go": {"pilot": "Harbor/Thanos/Istio-istiod", "idiom": "otelhttp / otel-grpc", "status": "BUILT (GoOtelRenderer)"},
    "python": {
        "pilot": "Saleor (N-3#1)",
        "idiom": "native OTel-SDK meter (create_meter/create_counter) — NOT prom-client; the #1 charter gap",
        "status": "PARTIAL: scaffold_codegen/telemetry_renderer is Python but FastAPI-auto-instr; the OTel-meter idiom is NEW",
    },
    "ruby": {"pilot": "Mastodon (N-1)", "idiom": "Rails middleware + Sidekiq queue (prometheus_exporter gem)", "status": "TODO — RubyRailsRenderer"},
    "typescript": {"pilot": "Medusa (N-3#2)", "idiom": "OTel traces-only → span-metrics derived (no native meter)", "status": "TODO — future (research)"},
    "java": {"pilot": "Broadleaf (N-3#3)", "idiom": "Spring Boot / Micrometer (metrics gated to commercial edition)", "status": "TODO — low priority"},
    "cpp-envoy": {
        "pilot": "Istio data-plane (P3)",
        "idiom": "runtime-composed istio_requests_total",
        "status": "OUT OF SCOPE — not source-instrumentable; live-scrape only (source_instrumentable=False)",
    },
}


@dataclass
class FileEdit:
    """One grep-anchored edit against the subject FORK (never the read-only clone)."""

    path: str  # relative to the subject fork root
    anchor: str  # a stable grep-able string to locate the injection site
    op: str  # "insert-after" | "insert-in-list" | "replace"
    content: str
    rationale: str


@dataclass
class Patch:
    language: str
    tier: str
    edits: List[FileEdit]
    new_deps: List[str] = field(default_factory=list)  # go.mod / pyproject / package.json additions
    notes: str = ""


# ── the per-language renderer protocol + registry (the ONLY per-language surface) ────────────────────
class InstrumentationRenderer(Protocol):
    language: str

    def supports(self, contract: InstrumentationContract) -> bool: ...

    def resolve_tier(self, contract: InstrumentationContract) -> str: ...

    def render(self, contract: InstrumentationContract, source_ctx: Dict[str, str]) -> Patch: ...


class RendererRegistry:
    """Dispatch by detected language — the SAME pattern as RepoProbe ``groundtruth.get_extractor(stack)``."""

    def __init__(self) -> None:
        self._by_lang: Dict[str, InstrumentationRenderer] = {}

    def register(self, renderer: InstrumentationRenderer) -> None:
        self._by_lang[renderer.language] = renderer

    def get(self, language: str) -> Optional[InstrumentationRenderer]:
        return self._by_lang.get(language)

    def languages(self) -> List[str]:
        return sorted(self._by_lang)


# ── FIRST renderer: Go + OTel (the Harbor case) ──────────────────────────────────────────────────────
class GoOtelRenderer:
    """Go renderer for the ``otel-meter-provider-on-existing-http-instrumentation`` contract.

    Grounded template for Harbor's shape: a service that already wires ``otelhttp`` trace-only. Tier is
    DETERMINISTIC when the trace endpoint/config is discoverable (Harbor: ``cfg.Otel.Endpoint``), CONTRACT-FILL
    when only partial, LLM-FILL for an unknown Go OTel-http idiom. The emitted Go is compile-verified against
    real Harbor source (``go build ./lib/trace`` exit 0) and emit-verified (9 ``http_server_*`` series live).
    """

    language = "go"

    def supports(self, contract: InstrumentationContract) -> bool:
        # Only the http-instrumentation contract has a grounded Go template here. A generic
        # otel-meter-provider (db/messaging/custom) has NO Go template → return False so close_gap
        # fails LOUD (→ LLM-fill / a future renderer) instead of mis-emitting the http.server patch
        # for a non-http mechanism (render() is otelhttp-specific regardless of `via`).
        return contract.via == "otel-meter-provider-on-existing-http-instrumentation"

    def resolve_tier(self, contract: InstrumentationContract) -> str:
        ev = contract.source_evidence
        if (
            contract.via == "otel-meter-provider-on-existing-http-instrumentation"
            and ev.get("trace_provider")
            and ev.get("http_options")
        ):
            return TIER_DETERMINISTIC  # we know exactly where the TracerProvider + otelhttp options live
        if ev.get("trace_provider") or ev.get("http_options"):
            return TIER_CONTRACT_FILL
        return TIER_LLM_FILL

    def render(self, contract: InstrumentationContract, source_ctx: Dict[str, str]) -> Patch:
        tier = self.resolve_tier(contract)
        tp = source_ctx.get("trace_provider", "src/lib/trace/trace.go")  # where the OTel init lives
        opts = source_ctx.get("http_options", "src/lib/trace/helper.go")  # where the otelhttp.Option slice lives
        opts_anchor = source_ctx.get("http_options_anchor", "otelhttp.WithTracerProvider(otel.GetTracerProvider()),")
        cfg_accessor = source_ctx.get("cfg_accessor", "GetGlobalConfig")  # grounded (Harbor: GetGlobalConfig)
        init_site = source_ctx.get("init_site", "func InitGlobalTracer(ctx context.Context) ShutdownFunc {")
        fams = ", ".join(contract.emit_families)

        # EXPORT-MECHANISM AWARE (the load-bearing learning): a scrape subject needs the OTel Prometheus exporter on
        # its DEFAULT registry so the new metrics land on the SAME /metrics the scraper already reads; an OTLP-push
        # subject needs otlpmetrichttp. Getting this wrong = the patch compiles but the verifier sees NOTHING.
        if contract.export_mechanism == "prometheus-scrape":
            deps = ["go.opentelemetry.io/otel/exporters/prometheus", "go.opentelemetry.io/otel/sdk/metric"]
            imports = (
                '\totelprom "go.opentelemetry.io/otel/exporters/prometheus"\n'
                '\tmetricsdk "go.opentelemetry.io/otel/sdk/metric"'
            )
            func = (
                "\n// initMeterProvider registers an OTel MeterProvider backed by the Prometheus exporter on the DEFAULT\n"
                "// registry (the one promhttp.Handler() serves at /metrics), so otelhttp emits the semconv http.server.*\n"
                f"// families ({fams}) onto the subject's EXISTING scrapeable /metrics. Generated (Extra Credit) — verify on a fork.\n"
                "func initMeterProvider() {\n"
                "\texp, err := otelprom.New()\n"
                '\tif err != nil { log.Warningf("fail to init prometheus meter exporter: %v", err); return }\n'
                "\totel.SetMeterProvider(metricsdk.NewMeterProvider(metricsdk.WithReader(exp)))\n"
                "}\n"
            )
            call = "\tinitMeterProvider()  // generated: expose semconv http.server.* on /metrics (scrape), independent of trace config"
        else:  # otlp-push
            deps = [
                "go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp",
                "go.opentelemetry.io/otel/sdk/metric",
            ]
            imports = (
                '\totlpmetrichttp "go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"\n'
                '\tmetricsdk "go.opentelemetry.io/otel/sdk/metric"'
            )
            func = (
                "\nfunc initMeterProvider(ctx context.Context) (*metricsdk.MeterProvider, error) {\n"
                f"\tcfg := {cfg_accessor}()\n"
                "\topts := []otlpmetrichttp.Option{\n"
                "\t\totlpmetrichttp.WithEndpoint(cfg.Otel.Endpoint),\n"
                "\t\totlpmetrichttp.WithURLPath(cfg.Otel.URLPath),\n"
                "\t}\n"
                "\tif cfg.Otel.Insecure { opts = append(opts, otlpmetrichttp.WithInsecure()) }\n"
                "\texp, err := otlpmetrichttp.New(ctx, opts...)\n"
                "\tif err != nil { return nil, err }\n"
                "\tmp := metricsdk.NewMeterProvider(metricsdk.WithReader(metricsdk.NewPeriodicReader(exp)))\n"
                "\totel.SetMeterProvider(mp)\n\treturn mp, nil\n}\n"
            )
            call = '\tif _, err := initMeterProvider(ctx); err != nil { log.Warningf("fail meter init: %v", err) }'

        edits = [
            FileEdit(
                path=tp,
                anchor='otlptracehttp"',
                op="insert-after",
                content=imports,
                rationale="Import the metric exporter + SDK matching the subject's export mechanism.",
            ),
            FileEdit(
                path=tp,
                anchor=init_site,
                op="insert-after",
                content=call,
                rationale="Init the MeterProvider at the OTel init entry point so it runs whenever the service starts.",
            ),
            FileEdit(
                path=tp,
                anchor="__EOF__",
                op="insert-after",
                content=func,
                rationale="The MeterProvider init, using the export mechanism the subject already serves.",
            ),
            FileEdit(
                path=opts,
                anchor=opts_anchor,
                op="insert-in-list",
                content="\totelhttp.WithMeterProvider(otel.GetMeterProvider()),",
                rationale=(
                    "Attach the MeterProvider to the existing otelhttp handler → it emits http.server.request.duration"
                    " + request/response body.size. The one-line core of the fix."
                ),
            ),
        ]
        return Patch(
            language="go",
            tier=tier,
            edits=edits,
            new_deps=deps,
            notes=(
                f"export_mechanism={contract.export_mechanism}. otelhttp auto-emits the semconv http.server.* families "
                "once a MeterProvider is attached — no per-route instrumentation. COMPILE-verified on a fork "
                "(lib/trace exit 0); full boot-verify needs the subject's build system. Verify on a FORK (FR-XC-3) before crediting."
            ),
        )


def default_registry() -> RendererRegistry:
    """The shipped registry. Register one renderer per language — that is the ONLY per-language work.

    ``GoOtelRenderer`` is built + verified. Python/Ruby/TypeScript/Java are ``PLANNED_RENDERERS`` TODOs; note the
    existing ``telemetry_renderer`` is a *different* Python idiom (FastAPI auto-instrumentation of the SDK's own
    generated apps), NOT the native OTel-meter idiom this framework needs for an arbitrary Python subject.
    """
    reg = RendererRegistry()
    reg.register(GoOtelRenderer())
    return reg


def close_gap(
    gap: InstrumentationGap,
    source_ctx: Dict[str, str],
    registry: Optional[RendererRegistry] = None,
) -> Patch:
    """Language-agnostic entry point: gap → contract → renderer[language] → Patch. Verification is separate.

    Raises ``NotImplementedError`` for a **non-source-instrumentable** gap (Envoy/runtime-composed — the framework's
    honest boundary, enforced HERE so it can't silently fall through to a misleading "register a renderer" error),
    an unregistered language, or a contract the renderer does not support — never a silent wrong patch.
    """
    registry = registry or default_registry()
    contract = InstrumentationContract.from_gap(gap)
    # Enforce the framework's honest boundary at the entry point: a runtime-composed surface (Envoy/sidecar
    # data-plane) has NO source to instrument — it is closeable only by live-scrape, never by generation.
    # (Computed by from_gap; enforced here so the field is not merely set-and-ignored.)
    if not contract.source_instrumentable:
        raise NotImplementedError(
            f"gap for {gap.subject}/{gap.service} (language={gap.language!r}, mechanism={gap.mechanism!r}) is NOT "
            f"source-instrumentable (via={contract.via!r}): its metrics are runtime-composed (Envoy/sidecar "
            "data-plane) — close it by LIVE-SCRAPE + traffic, never by generation. The framework's honest boundary, "
            "NOT a missing renderer."
        )
    renderer = registry.get(gap.language)
    if renderer is None:
        raise NotImplementedError(
            f"no instrumentation renderer registered for language={gap.language!r} "
            f"(registered: {registry.languages()}). Register one — that is the ONLY per-language work."
        )
    if not renderer.supports(contract):
        raise NotImplementedError(f"renderer[{gap.language}] does not support contract.via={contract.via!r}")
    return renderer.render(contract, source_ctx)


def harbor_core_reference_gap() -> InstrumentationGap:
    """The grounded Harbor-core gap this framework was proven against (compile + emit gates green).

    Kept as an executable reference of the proven case, and the fixture the tests assert on.
    """
    return InstrumentationGap(
        subject="harbor",
        service="core",
        language="go",
        missing_families=[
            "http.server.request.duration",
            "http.server.request.body.size",
            "http.server.response.body.size",
        ],
        mechanism="otelhttp present, wired trace-only (HarborHTTPTraceOptions has no WithMeterProvider)",
        source_evidence={"trace_provider": "src/lib/trace/trace.go:88", "http_options": "src/lib/trace/helper.go:75"},
    )
