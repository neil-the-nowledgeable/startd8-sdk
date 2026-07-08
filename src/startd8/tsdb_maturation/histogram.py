"""M7 — Histogram → stats table (FR-13).

A **distinct inference path** from the gauge/measure path: a native OTel/Prometheus histogram is
exposed as three series families — ``<base>_bucket{le=…}`` (cumulative counts), ``<base>_sum``, and
``<base>_count`` — which this module materializes into a **percentile/stats table** (one row per
identity, columns: identity labels + ``count``/``sum``/``mean``/``p50``/``p90``/``p95``/``p99``).

Sequenced last and isolated so it can be dropped without unshipping the core.

**Scope boundary** (the tighter contract the R1 review asked for):

* **Percentiles** — a fixed, documented default set ``(0.5, 0.9, 0.95, 0.99)``; configurable.
* **Bucket boundaries** — the ``le`` label values are the cumulative upper bounds; ``+Inf`` is the
  overflow bucket. Standard Prometheus ``histogram_quantile`` linear interpolation within a bucket.
* **``le`` handling** — ``le`` is **consumed** to compute percentiles, never a table column. The
  table identity is the **non-``le``** label set.
* **Assumption** — cumulative buckets (Prometheus convention); a non-monotonic bucket set is
  tolerated by clamping (counts are treated as non-decreasing).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from startd8.logging_config import get_logger
from startd8.manifest_extraction.entities import DocEntity, DocField, EntityGraph
from startd8.manifest_extraction.prisma_emitter import render_prisma_schema

from .infer import (
    OBSERVED_AT_FIELD,
    InferenceError,
    InferenceResult,
    _default_entity_name,
    assert_graph_invariants,
    infer_identity,
    infer_scalar_type,
    rename_if_reserved,
)
from .reader import Series

logger = get_logger(__name__)

DEFAULT_PERCENTILES: tuple[float, ...] = (0.5, 0.9, 0.95, 0.99)

_BUCKET_SUFFIX = "_bucket"
_SUM_SUFFIX = "_sum"
_COUNT_SUFFIX = "_count"


class HistogramError(InferenceError):
    """A histogram family could not be detected or its buckets are unusable."""


@dataclass(frozen=True)
class HistogramFamily:
    """The three metric names that make up one native histogram."""

    base: str

    @property
    def bucket_metric(self) -> str:
        return self.base + _BUCKET_SUFFIX

    @property
    def sum_metric(self) -> str:
        return self.base + _SUM_SUFFIX

    @property
    def count_metric(self) -> str:
        return self.base + _COUNT_SUFFIX


def detect_histogram_family(names: Sequence[str]) -> Optional[HistogramFamily]:
    """Detect a ``<base>_bucket`` + ``<base>_sum`` + ``<base>_count`` triple in ``names``.

    Returns the family for the first base that has all three members, else ``None``.
    """
    present = set(names)
    bases = [n[: -len(_BUCKET_SUFFIX)] for n in names if n.endswith(_BUCKET_SUFFIX)]
    for base in bases:
        if base + _SUM_SUFFIX in present and base + _COUNT_SUFFIX in present:
            return HistogramFamily(base=base)
    return None


def _pct_column(q: float) -> str:
    """``0.95`` → ``p95``; ``0.999`` → ``p999`` (column name for a percentile)."""
    s = ("%g" % (q * 100)).replace(".", "_")
    return "p" + s


def histogram_quantile(q: float, buckets: Sequence[tuple[float, float]]) -> float:
    """Prometheus ``histogram_quantile`` over cumulative buckets ``[(le, cumulative_count), …]``.

    ``buckets`` need not be pre-sorted; a ``+Inf`` overflow bucket (``le == inf``) SHOULD be present
    (it carries the total). Returns ``nan`` for an empty/zero histogram; clamps ``q`` outside [0,1].
    """
    if not buckets:
        return math.nan
    pts = sorted(((float(le), float(c)) for le, c in buckets), key=lambda x: x[0])
    # Enforce monotonic non-decreasing cumulative counts (tolerate minor scrape skew).
    mono: list[tuple[float, float]] = []
    running = 0.0
    for le, c in pts:
        running = max(running, c)
        mono.append((le, running))
    total = mono[-1][1]
    if total <= 0:
        return math.nan
    if q <= 0:
        return mono[0][0]
    if q >= 1:
        # the largest finite bound (Prometheus returns the second-to-last upper bound for q==1)
        finite = [le for le, _ in mono if not math.isinf(le)]
        return finite[-1] if finite else mono[-1][0]

    rank = q * total
    b = 0
    while b < len(mono) and mono[b][1] < rank:
        b += 1
    if b >= len(mono):
        b = len(mono) - 1
    # In the +Inf overflow bucket → return the largest finite bound.
    if math.isinf(mono[b][0]):
        finite = [le for le, _ in mono if not math.isinf(le)]
        return finite[-1] if finite else mono[b][0]

    lower_bound = 0.0 if b == 0 else mono[b - 1][0]
    lower_count = 0.0 if b == 0 else mono[b - 1][1]
    upper_bound = mono[b][0]
    upper_count = mono[b][1]
    span = upper_count - lower_count
    if span <= 0:
        return upper_bound
    return lower_bound + (upper_bound - lower_bound) * ((rank - lower_count) / span)


@dataclass(frozen=True)
class HistogramStatsRow:
    """One identity's computed statistics."""

    labels: Mapping[str, str]      # the non-`le` identity labels
    count: int
    sum: Decimal
    quantiles: Mapping[float, float]

    @property
    def mean(self) -> Decimal:
        return self.sum / Decimal(self.count) if self.count else Decimal(0)


def _le_of(series: Series) -> Optional[float]:
    le = series.labels.get("le")
    if le is None:
        return None
    if le in ("+Inf", "Inf", "inf"):
        return math.inf
    try:
        return float(le)
    except ValueError:
        return None


def _identity_labels(labels: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """The hashable non-``le`` label set that identifies one histogram."""
    return tuple(sorted((k, v) for k, v in labels.items() if k != "le"))


def compute_histogram_stats(
    bucket_series: Sequence[Series],
    sum_series: Sequence[Series],
    count_series: Sequence[Series],
    *,
    percentiles: Sequence[float] = DEFAULT_PERCENTILES,
) -> list[HistogramStatsRow]:
    """Compute per-identity stats from the three histogram families (FR-13)."""
    # Group bucket series by identity (non-le labels) → sorted (le, cumulative) list.
    buckets_by_id: dict[tuple, list[tuple[float, float]]] = {}
    labels_by_id: dict[tuple, dict] = {}
    for s in bucket_series:
        le = _le_of(s)
        if le is None:
            continue
        ident = _identity_labels(s.labels)
        buckets_by_id.setdefault(ident, []).append((le, s.value))
        labels_by_id.setdefault(ident, {k: v for k, v in s.labels.items() if k != "le"})

    sum_by_id = {_identity_labels(s.labels): s.value for s in sum_series}
    count_by_id = {_identity_labels(s.labels): s.value for s in count_series}

    rows: list[HistogramStatsRow] = []
    for ident, buckets in buckets_by_id.items():
        total = count_by_id.get(ident)
        if total is None:
            total = max((c for _, c in buckets), default=0.0)
        quantiles = {q: histogram_quantile(q, buckets) for q in percentiles}
        rows.append(
            HistogramStatsRow(
                labels=labels_by_id[ident],
                count=int(total),
                sum=Decimal(str(sum_by_id.get(ident, 0))),
                quantiles=quantiles,
            )
        )
    return rows


def infer_histogram_schema(
    family: HistogramFamily,
    stats_rows: Sequence[HistogramStatsRow],
    *,
    entity_name: Optional[str] = None,
    identity: Optional[Sequence[str]] = None,
    percentiles: Sequence[float] = DEFAULT_PERCENTILES,
) -> InferenceResult:
    """Build the stats-table schema (a distinct inference path) and render it via the real emitter.

    Columns: the non-``le`` identity labels (typed by value) + ``count`` (Int) + ``sum``/``mean``/
    each ``pNN`` (Decimal) + ``observedAt``. Identity = the inferred/declared non-``le`` label key.
    Returns an :class:`InferenceResult` so it plugs into the gate/imports machinery; ``measure_field``
    is set to ``count`` (histograms use a dedicated payload builder, not the single-measure path).
    """
    if not stats_rows:
        raise HistogramError(f"no stats rows for histogram {family.base!r}")
    entity = entity_name or _default_entity_name(family.base)
    reserved = _reserved()

    label_keys = sorted({k for row in stats_rows for k in row.labels})
    if not label_keys:
        raise HistogramError(f"histogram {family.base!r} has no non-`le` labels to key on")

    col_type = {
        c: infer_scalar_type([row.labels.get(c) for row in stats_rows if c in row.labels])
        for c in label_keys
    }
    colmap = {c: rename_if_reserved(c, reserved) for c in label_keys}

    fields: list[DocField] = []
    for i, c in enumerate(label_keys):
        fields.append(DocField(name=colmap[c], plain_type=col_type[c], prisma_type=col_type[c],
                               required=True, notes="", human_only=False, row_index=i))
    # stat columns
    stat_cols = [("count", "Int"), ("sum", "Decimal"), ("mean", "Decimal")]
    stat_cols += [(_pct_column(q), "Decimal") for q in percentiles]
    idx = len(label_keys)
    for name, typ in stat_cols:
        fields.append(DocField(name=name, plain_type=typ, prisma_type=typ,
                               required=True, notes="", human_only=False, row_index=idx))
        idx += 1
    fields.append(DocField(name=OBSERVED_AT_FIELD, plain_type="DateTime", prisma_type="DateTime",
                           required=True, notes="", human_only=False, row_index=idx))

    graph = EntityGraph()
    graph.entities[entity] = DocEntity(name=entity, fields=tuple(fields), heading_path=())

    # Identity over the non-le labels (declared wins; else inferred from the stats rows).
    records = [dict(row.labels) for row in stats_rows]
    if identity:
        id_labels = list(identity)
    else:
        id_labels = infer_identity(records, label_keys)
    id_fields = tuple(colmap[c] for c in id_labels)
    graph.uniques[entity] = [id_fields]

    result = render_prisma_schema(graph)
    assert_graph_invariants(graph, entity, result)
    logger.info("inferred histogram stats table %s: %d labels, %d percentiles",
                entity, len(label_keys), len(percentiles))
    return InferenceResult(
        entity=entity, graph=graph, schema=result,
        identity_labels=tuple(id_labels), identity_fields=id_fields,
        colmap=colmap, measure_field="count",
    )


def histogram_payload(
    family: HistogramFamily,
    stats_rows: Sequence[HistogramStatsRow],
    result: InferenceResult,
    *,
    percentiles: Sequence[float] = DEFAULT_PERCENTILES,
    observed_at: str = "1970-01-01T00:00:00Z",
) -> dict:
    """Build the ``from_json`` payload for a histogram stats table (its own path, not build_payload)."""
    rows = []
    for row in stats_rows:
        out: dict = {}
        for raw, emitted in result.colmap.items():
            if raw in row.labels:
                out[emitted] = row.labels[raw]
        out["count"] = row.count
        out["sum"] = format(row.sum, "f")
        out["mean"] = format(row.mean, "f")
        for q in percentiles:
            out[_pct_column(q)] = _fmt_quantile(row.quantiles.get(q))
        out[OBSERVED_AT_FIELD] = observed_at
        rows.append(out)
    return {result.entity: rows}


def _fmt_quantile(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "0"
    return format(Decimal(str(v)), "f")


def _reserved() -> frozenset:
    from startd8.manifest_extraction.prisma_emitter import reserved_field_names

    return frozenset(reserved_field_names())


# Re-exported for callers that only need the detection + column naming.
__all__ = [
    "DEFAULT_PERCENTILES",
    "HistogramError",
    "HistogramFamily",
    "HistogramStatsRow",
    "compute_histogram_stats",
    "detect_histogram_family",
    "histogram_payload",
    "histogram_quantile",
    "infer_histogram_schema",
]
