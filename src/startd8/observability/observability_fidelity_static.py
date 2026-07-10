# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""SPIKE: static observability-fidelity — two-sided binding, zero runtime.

The SDK benchmark scores whether a *generated service's code* works (compile +
behavioral). It does NOT score whether the service's *generated observability*
is correct. This module prototypes a check that does, without any runtime:

* **Emitted set** — the metric names a service's SOURCE CODE actually emits
  (its OTel/Prometheus instrument names, e.g. ``meter.create_counter(
  "app_requests_total")`` in Python, ``promauto.NewCounter(...)`` in Go), plus
  the OTel semantic-convention metrics *implied* by its transport (gRPC server
  instrumentation implies ``rpc_server_duration``, etc.).
* **Referenced set** — the metric names the generated OBSERVABILITY (the PromQL
  in alerts / SLOs / dashboards) REFERENCES.
* **Static fidelity** — do the referenced metrics bind to the emitted set?
  ``coverage = |referenced ∩ emitted| / |referenced|``. A referenced metric
  absent from the emitted set is a *binding failure*: the alert queries a metric
  the service never emits. Caught with **zero runtime**.

This is the fidelity harness's two-sided-binding idea (``validate_promql.py``:
``extract_exprs``, ``diagnose_axes``, ``MetricDescriptor``) applied between two
*generated artifacts* instead of against a live Prometheus.

Design-principle notes carried over from the live harness:

* **Reuse, don't re-parse (Mottainai).** The referenced side reuses the live
  harness's ``extract_exprs`` PromQL walk and its ``strip_threshold`` /
  ``substitute_grafana_macros`` normalizers verbatim. We only add the one thing
  the live harness deliberately does NOT do — pull *bare metric identifiers* out
  of an expr — because live fidelity forwards the descriptor instead of parsing
  PromQL, whereas static fidelity has no descriptor for the *referenced* side.
* **No silent green (Context-Correctness).** An empty referenced set or an empty
  emitted set yields a distinct ``unknown`` verdict, never ``pass``.

────────────────────────────────────────────────────────────────────────────
EMITTED-SIDE HEURISTICS AND THEIR LIMITS (read before trusting a number)
────────────────────────────────────────────────────────────────────────────
Extracting the emitted set from source is the hard, lossy part. This prototype
is *regex + transport-implication*, not a compiler. It is honest about that:

1. **Explicit instrument constructors** (high precision, moderate recall):
   Python  ``meter.create_counter("name")`` / ``create_histogram`` / ``create_
            up_down_counter`` / ``create_observable_*``; ``Counter("name", ...)``
            / ``Histogram`` / ``Gauge`` / ``Summary`` from ``prometheus_client``.
   Go       ``promauto.NewCounter(...  Name: "name" ...)`` and the ``prometheus.
            NewCounter/NewHistogram/...`` families (Name pulled from the struct
            literal); ``Meter.Int64Counter("name")`` / ``Float64Histogram`` OTel.
   Node/TS  ``meter.createCounter('name')`` / ``createHistogram`` /
            ``createObservableGauge``; ``new client.Counter({name:'name'})``
            (prom-client).

2. **Transport-implied OTel semconv metrics** (the load-bearing bit for
   auto-instrumented services, which emit NO explicit constructor at all):
   a gRPC-server service implies ``rpc_server_duration`` (+ the histogram-derived
   ``_count`` / ``_bucket`` / ``_sum`` families); an HTTP-server service implies
   ``http_server_duration`` (+ families). Transport is sniffed from imports /
   framework calls, or passed in explicitly. This mirrors ``metric_descriptor``'s
   ``semconv-http`` / ``semconv-grpc`` profiles.

KNOWN FALSE-NEGATIVE SOURCES (emitted metric missed → spurious binding failure):
   * name built by string concatenation / f-string / constant
     (``PREFIX + "_total"``);
   * instrument created through a thin project-local wrapper we don't recognize;
   * a metric-name *suffix* the PromQL references but the constructor omits
     (Prometheus client counters expose ``<name>_total``; OTel histograms expose
     ``<name>_bucket`` / ``_count`` / ``_sum``) — handled by SUFFIX EXPANSION below,
     but expansion is itself heuristic;
   * a language we don't parse (Java, C#, Rust, …).

KNOWN FALSE-POSITIVE SOURCES (binds when it shouldn't):
   * a metric named in a comment / dead code / test;
   * transport-implied metric assumed present when auto-instrumentation is
     actually disabled.

Treat the output as a **reported-not-scored** signal: a low coverage number is a
strong hint of a real binding gap, but a human/2nd-pass should confirm before it
gates anything. See ``docs/spikes/STATIC_OBSERVABILITY_FIDELITY_SPIKE.md``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

# Reuse the live fidelity harness rather than reinventing extraction (Mottainai).
from .validate_promql import (
    extract_exprs,
    strip_threshold,
    substitute_grafana_macros,
)

logger = logging.getLogger(__name__)


# ───────────────────────── source file discovery ───────────────────────────

#: Extension → language tag for the emitted-side extractors.
_LANG_BY_EXT: Dict[str, str] = {
    ".py": "python",
    ".go": "go",
    ".js": "node",
    ".mjs": "node",
    ".ts": "node",
    ".tsx": "node",
}

#: Directories we never descend into when scanning a service tree.
_SKIP_DIRS = {
    "node_modules", "vendor", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", "site-packages", ".startd8",
}


def _iter_source_files(root: Path) -> Iterable[Tuple[Path, str]]:
    """Yield ``(path, language)`` for every recognized source file under *root*.

    A single file may be passed directly. Directories are walked, skipping the
    vendored / build trees in ``_SKIP_DIRS`` (which otherwise dominate and would
    pull in third-party instrument names that the *service* does not own).
    """
    if root.is_file():
        lang = _LANG_BY_EXT.get(root.suffix)
        if lang:
            yield root, lang
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        lang = _LANG_BY_EXT.get(path.suffix)
        if lang:
            yield path, lang


# ───────────────────────── emitted: explicit constructors ──────────────────

# Each pattern captures the metric NAME as group 1. Kept deliberately narrow so
# they match a literal string argument only (a false name from a variable is a
# known-and-documented false negative, not a silent false positive).

_PY_PATTERNS: Tuple[re.Pattern, ...] = (
    # OTel Python: meter.create_counter("name"), create_histogram, create_gauge,
    # create_up_down_counter, create_observable_{counter,gauge,up_down_counter}.
    re.compile(
        r"""\.create_(?:up_down_counter|counter|histogram|gauge
            |observable_counter|observable_up_down_counter|observable_gauge)
            \s*\(\s*(?:name\s*=\s*)?["']([A-Za-z_][A-Za-z0-9_.]*)["']""",
        re.VERBOSE,
    ),
    # prometheus_client: Counter("name", ...), Histogram, Gauge, Summary.
    re.compile(
        r"""\b(?:Counter|Histogram|Gauge|Summary)\s*\(\s*["']([A-Za-z_:][A-Za-z0-9_:]*)["']""",
    ),
)

_GO_PATTERNS: Tuple[re.Pattern, ...] = (
    # OTel Go: meter.Int64Counter("name"), Float64Histogram("name"), etc. The
    # constructor family is Int64/Float64 × Counter/UpDownCounter/Histogram/
    # ObservableCounter/ObservableGauge/ObservableUpDownCounter/Gauge.
    re.compile(
        r"""\.(?:Int64|Float64)
            (?:UpDownCounter|Counter|Histogram|Gauge
             |ObservableCounter|ObservableUpDownCounter|ObservableGauge)
            \s*\(\s*["`]([A-Za-z_][A-Za-z0-9_.]*)["`]""",
        re.VERBOSE,
    ),
    # prometheus/client_golang: Name: "metric_name" inside a ...Opts struct
    # literal (promauto.NewCounter(prometheus.CounterOpts{Name: "x_total"})).
    re.compile(r"""\bName\s*:\s*["`]([A-Za-z_:][A-Za-z0-9_:]*)["`]"""),
)

_NODE_PATTERNS: Tuple[re.Pattern, ...] = (
    # OTel JS: meter.createCounter('name'), createHistogram, createUpDownCounter,
    # createObservableGauge/Counter/UpDownCounter.
    re.compile(
        r"""\.create(?:UpDownCounter|Counter|Histogram|Gauge
            |ObservableCounter|ObservableUpDownCounter|ObservableGauge)
            \s*\(\s*["'`]([A-Za-z_][A-Za-z0-9_.]*)["'`]""",
        re.VERBOSE,
    ),
    # prom-client: new client.Counter({ name: 'metric_name', ... }).
    re.compile(r"""\bname\s*:\s*["'`]([A-Za-z_:][A-Za-z0-9_:]*)["'`]"""),
)

_PATTERNS_BY_LANG: Dict[str, Tuple[re.Pattern, ...]] = {
    "python": _PY_PATTERNS,
    "go": _GO_PATTERNS,
    "node": _NODE_PATTERNS,
}


# ───────────────────────── emitted: transport implication ──────────────────

# Import / call fingerprints that imply the service is *auto-instrumented* for a
# transport and therefore emits the OTel semconv metric for it, with NO explicit
# constructor in source. This is the crucial path for real Online-Boutique-style
# services, whose RED metrics come entirely from auto-instrumentation.
_GRPC_FINGERPRINTS = (
    "grpc", "grpcio", "grpc.aio", "google.golang.org/grpc",
    "@grpc/grpc-js", "GrpcInstrumentation", "grpc_server",
)
_HTTP_FINGERPRINTS = (
    "flask", "fastapi", "starlette", "django", "aiohttp", "express",
    "net/http", "http.server", "HttpInstrumentation", "FastAPIInstrumentor",
    "FlaskInstrumentor",
)

#: OTel semconv base names implied by transport (see metric_descriptor profiles).
_TRANSPORT_SEMCONV_BASE = {
    "grpc": "rpc_server_duration",
    "http": "http_server_duration",
}


def sniff_transports(text: str) -> Set[str]:
    """Best-effort transport detection from a source blob (``grpc`` / ``http``)."""
    found: Set[str] = set()
    lowered = text.lower()
    if any(fp.lower() in lowered for fp in _GRPC_FINGERPRINTS):
        found.add("grpc")
    if any(fp.lower() in lowered for fp in _HTTP_FINGERPRINTS):
        found.add("http")
    return found


# ───────────────────────── suffix expansion ────────────────────────────────

# OTel histograms and Prometheus counters expose *derived* series whose names the
# PromQL references but the constructor does not spell out. We expand a captured
# base name into the family so binding is judged on the referenced form.
#   OTel histogram  "duration_milliseconds" → _bucket / _count / _sum
#   OTel counter    "rpc_server_duration"   (histogram) → same family
#   Prom counter    "app_requests_total"    → itself (client already suffixed)
_HISTOGRAM_SUFFIXES = ("_bucket", "_count", "_sum")


def _expand_family(name: str) -> Set[str]:
    """Return *name* plus its histogram-derived series names.

    We can't know from a bare name whether an instrument is a counter or a
    histogram, so we conservatively emit BOTH the plain name and the histogram
    family. Over-generating the emitted set here is the safe direction: it can
    only *hide* a real gap (false negative), never *invent* one (false positive) —
    and the report flags any family-only match so a reviewer can see it.
    """
    out = {name}
    for suf in _HISTOGRAM_SUFFIXES:
        out.add(name + suf)
    return out


# ───────────────────────────── public API ──────────────────────────────────


def extract_emitted_metrics(
    service_source: Path,
    *,
    transports: Optional[Iterable[str]] = None,
    expand_families: bool = True,
) -> Set[str]:
    """The metric names a service's SOURCE CODE emits (best-effort, static).

    Scans *service_source* (a file or a directory tree) for explicit instrument
    constructors in Python / Go / Node, and adds the OTel semconv metrics implied
    by any transport it is auto-instrumented for. See the module docstring for
    the full heuristic list and its documented false-positive/negative surface.

    Args:
      service_source: file or directory to scan.
      transports: override transport detection (e.g. ``{"grpc"}``). When ``None``
        transports are sniffed from the source.
      expand_families: also emit histogram-derived (``_bucket`` / ``_count`` /
        ``_sum``) names for every base name. Default on — matches how PromQL
        references histograms.
    """
    root = Path(service_source)
    emitted: Set[str] = set()
    sniffed: Set[str] = set()

    for path, lang in _iter_source_files(root):
        try:
            text = path.read_text(errors="ignore")
        except OSError as e:  # pragma: no cover - unreadable file
            logger.warning("skipping unreadable source %s: %s", path, e)
            continue
        for pat in _PATTERNS_BY_LANG.get(lang, ()):  # explicit constructors
            for m in pat.finditer(text):
                emitted.add(m.group(1))
        sniffed |= sniff_transports(text)

    for t in (set(transports) if transports is not None else sniffed):
        base = _TRANSPORT_SEMCONV_BASE.get(t)
        if base:
            emitted.add(base)

    if expand_families:
        expanded: Set[str] = set()
        for name in emitted:
            expanded |= _expand_family(name)
        emitted = expanded

    return emitted


# A metric identifier at the head of a PromQL selector: a bare name, optionally
# followed by ``{`` (label matcher) or ``(`` (never — that's a function). We pull
# candidates then subtract PromQL keywords / functions.
_METRIC_TOKEN_RE = re.compile(r"[A-Za-z_:][A-Za-z0-9_:]*")

#: PromQL functions / keywords / aggregation ops that are NOT metric names.
_PROMQL_NONMETRICS: Set[str] = {
    # range/instant functions
    "rate", "irate", "increase", "delta", "idelta", "deriv", "predict_linear",
    "histogram_quantile", "quantile_over_time", "avg_over_time", "sum_over_time",
    "min_over_time", "max_over_time", "count_over_time", "stddev_over_time",
    "stdvar_over_time", "last_over_time", "present_over_time", "absent",
    "absent_over_time", "changes", "resets", "clamp", "clamp_max", "clamp_min",
    "abs", "ceil", "floor", "round", "exp", "ln", "log2", "log10", "sqrt",
    "sgn", "vector", "scalar", "time", "timestamp", "label_replace",
    "label_join", "sort", "sort_desc", "day_of_month", "day_of_week",
    "days_in_month", "hour", "minute", "month", "year", "pi", "histogram_sum",
    "histogram_count", "histogram_fraction", "histogram_avg", "holt_winters",
    # aggregation operators
    "sum", "avg", "min", "max", "count", "count_values", "stddev", "stdvar",
    "topk", "bottomk", "quantile", "group",
    # aggregation / vector-match keywords
    "by", "without", "on", "ignoring", "group_left", "group_right", "offset",
    "bool", "and", "or", "unless", "atan2",
    # our substituted-macro replacements (bare durations) never appear as tokens
}


def bare_metrics_from_expr(expr: str) -> Set[str]:
    """Pull bare metric identifiers out of one PromQL expression.

    Normalizes the expr the same way the live replay does — ``strip_threshold``
    (drop the trailing ``> 500.0`` so we don't parse the scalar) and
    ``substitute_grafana_macros`` (resolve ``$__rate_interval`` etc.) — then keeps
    identifiers that (a) are not PromQL functions/keywords, (b) are not immediately
    followed by ``(`` (that's a function call), and (c) are not label keys/values
    (anything inside ``{...}``). This is intentionally the *only* piece we add on
    top of the live harness: live fidelity forwards the descriptor instead of
    parsing referenced PromQL, so it never needed a bare-name puller.
    """
    expr = substitute_grafana_macros(strip_threshold(expr))
    # Blank out label matchers so label keys/values aren't mistaken for metrics.
    cleaned = re.sub(r"\{[^{}]*\}", " ", expr)
    # Blank out range/offset selectors ([5m], [1h], [$__range]) so the duration
    # unit letters (m/h/d/s/w/y) don't leak as one-char "metric" tokens.
    cleaned = re.sub(r"\[[^\[\]]*\]", " ", cleaned)
    # Blank out string literals (quoted) too, defensively.
    without_labels = re.sub(r"""(['"]).*?\1""", " ", cleaned)

    names: Set[str] = set()
    for m in _METRIC_TOKEN_RE.finditer(without_labels):
        token = m.group(0)
        # Skip if immediately followed by "(" → it's a function call.
        after = without_labels[m.end():m.end() + 1]
        if after == "(":
            continue
        if token in _PROMQL_NONMETRICS:
            continue
        # Pure numbers-with-unit like "5m" won't match the token regex (leading
        # digit), so nothing to strip there. Skip bare duration-ish tokens.
        names.add(token)
    return names


def extract_referenced_metrics(artifacts_dir: Path) -> Dict[str, Set[str]]:
    """Metric names REFERENCED by generated PromQL, grouped by service.

    Reuses the live harness's ``extract_exprs`` to walk ``alerts/`` ``slos/``
    ``dashboards/`` (Mottainai — no re-implementation), then pulls bare metric
    identifiers from each expr. Returns ``{service_id: {metric_name, ...}}`` so
    fidelity can be judged per service against that service's emitted set.
    """
    by_service: Dict[str, Set[str]] = {}
    for e in extract_exprs(Path(artifacts_dir)):
        by_service.setdefault(e.service, set()).update(
            bare_metrics_from_expr(e.expr)
        )
    return by_service


def static_fidelity(emitted: Set[str], referenced: Set[str]) -> Dict[str, object]:
    """Two-sided binding verdict for one service.

    ``coverage = |referenced ∩ emitted| / |referenced|``. Unbound metrics are
    those referenced by the observability but absent from the emitted set — each
    one is an alert/SLO/panel that queries a series the service never produces.

    Verdicts (no silent green):
      * ``unknown`` — nothing referenced, or nothing emitted (can't judge).
      * ``pass``    — coverage == 1.0 (every referenced metric binds).
      * ``partial`` — 0 < coverage < 1.0 (some bind, some don't).
      * ``fail``    — coverage == 0.0 (nothing binds).
    """
    bound = referenced & emitted
    unbound = referenced - emitted
    if not referenced or not emitted:
        verdict = "unknown"
        coverage = 0.0
    else:
        coverage = len(bound) / len(referenced)
        if coverage == 1.0:
            verdict = "pass"
        elif coverage == 0.0:
            verdict = "fail"
        else:
            verdict = "partial"
    return {
        "verdict": verdict,
        "coverage": round(coverage, 4),
        "referenced_count": len(referenced),
        "emitted_count": len(emitted),
        "bound": sorted(bound),
        "unbound": sorted(unbound),
    }


# ─────────── emitted: manifest / MetricDescriptor (G2 — the accuracy win) ────


def emitted_from_descriptor(descriptor) -> Set[str]:
    """Metrics the resolved :class:`MetricDescriptor` expects (family-expanded).

    Closes the spike's G2 gap: the span-metrics RED surface (``calls_total`` /
    ``duration_milliseconds*``) is produced by the OTel **collector**, not the service
    source — a pure source scan false-negatives it. But the manifest's ``metricsProfile``
    *declares* that surface, and the descriptor is the SAME resolution the generator ran
    (Mottainai). Folding it into the emitted set makes the check *manifest-aware* — it
    now flags only genuinely-unbindable references, not profile-convention differences.
    """
    out: Set[str] = set()
    for name in (
        getattr(descriptor, "throughput_metric", ""),
        getattr(descriptor, "latency_bucket_metric", ""),
    ):
        if not name:
            continue
        base = name[: -len("_bucket")] if name.endswith("_bucket") else name
        out |= _expand_family(base)
        out.add(name)
    return out


def emitted_from_onboarding(onboarding_metadata: Path) -> Dict[str, Set[str]]:
    """Per-service descriptor-expected metrics, via the generator's own resolution.

    Reuses ``validate_promql.reconstruct_descriptors`` (the exact FR-8 rebuild the live
    harness uses) so the emitted side and the generator agree by construction.
    """
    from .validate_promql import reconstruct_descriptors

    return {
        svc: emitted_from_descriptor(d)
        for svc, d in reconstruct_descriptors(Path(onboarding_metadata)).items()
    }


def score_services(
    *,
    artifacts_dir: Path,
    onboarding_metadata: Optional[Path] = None,
    source_roots: Optional[Dict[str, Path]] = None,
) -> Dict[str, Dict[str, object]]:
    """Per-service static fidelity with a manifest-aware emitted set.

    ``emitted = descriptor-expected (from onboarding) ∪ source-scanned (per service)``.
    Provide ``onboarding_metadata`` (recommended — the accurate, deployment-aware source),
    ``source_roots`` ({service_id: path}), or both. Each per-service result also records
    which emitted sources fed it, so a low score can be triaged as real gap vs. blind spot.
    """
    referenced = extract_referenced_metrics(Path(artifacts_dir))
    desc_emitted = (
        emitted_from_onboarding(Path(onboarding_metadata)) if onboarding_metadata else {}
    )
    source_roots = source_roots or {}

    out: Dict[str, Dict[str, object]] = {}
    for svc, refs in referenced.items():
        emitted: Set[str] = set(desc_emitted.get(svc, set()))
        root = source_roots.get(svc)
        if root is not None:
            emitted |= extract_emitted_metrics(Path(root))
        result = static_fidelity(emitted, refs)
        result["emitted_sources"] = {
            "descriptor": svc in desc_emitted,
            "source_scan": root is not None,
        }
        out[svc] = result
    return out
