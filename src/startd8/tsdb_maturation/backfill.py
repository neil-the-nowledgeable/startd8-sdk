"""M5 — Backfill payload + key-collapse aggregation (FR-6, FR-8).

Turns a raw specimen into the JSON payload the generated ``from_json`` importer ingests. The
importer already dedups on the inferred identity (M3's ``imports.yaml``) and coerces Decimal/
DateTime for free (``_COERCE``); M5 adds the one genuinely-new piece: **key-collapse aggregation**.

**FR-6 (mandatory, post-identity).** When reduction or a coarser (confirmed/declared) identity
projects *multiple series onto one identity key*, the measure MUST be aggregated at records-build
time. On the SDK path a collision would otherwise be **silent last-writer-wins data loss** (no DB
tripwire) — so this is non-optional.

**R1-F5 — aggregation binds to metric additivity.** Summing is valid only for **additive**
measures (a counter / ``_amount`` / ``_sum`` / ``_total`` / ``_count`` family → ``sum``). A gauge,
ratio, or otherwise non-additive measure is **not** blindly summed — it defaults to ``last`` with a
loud warning (blindly summing a gauge is as wrong as overwriting it). An explicit ``aggregate=``
override always wins. When additivity is unknown, the fail-safe default is **non-additive** (never
silently sum).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional, Sequence

from startd8.logging_config import get_logger

from .infer import OBSERVED_AT_FIELD, InferenceResult
from .specimen import Specimen

logger = get_logger(__name__)

#: Metric-name suffixes whose measures are additive (safe to ``sum`` on collapse). Prometheus
#: counters conventionally end ``_total``; michigan money is ``_amount``; OTel histograms ``_sum``.
_ADDITIVE_SUFFIXES = ("_amount", "_total", "_sum", "_count")


class Additivity(str, Enum):
    ADDITIVE = "additive"          # → sum
    NON_ADDITIVE = "non_additive"  # → last (+ warning); never blindly summed


class AggFunc(str, Enum):
    SUM = "sum"
    LAST = "last"
    AVG = "avg"


def classify_additivity(metric: str) -> Additivity:
    """R1-F5: additive iff the metric name carries an additive suffix; else the fail-safe default."""
    low = metric.lower()
    if any(low.endswith(sfx) for sfx in _ADDITIVE_SUFFIXES):
        return Additivity.ADDITIVE
    return Additivity.NON_ADDITIVE  # fail-safe: unknown → never silently sum


def _default_agg(additivity: Additivity) -> AggFunc:
    return AggFunc.SUM if additivity is Additivity.ADDITIVE else AggFunc.LAST


def _aggregate(values: Sequence[Decimal], func: AggFunc) -> Decimal:
    if func is AggFunc.SUM:
        return sum(values, Decimal(0))
    if func is AggFunc.AVG:
        return sum(values, Decimal(0)) / Decimal(len(values))
    return values[-1]  # LAST


@dataclass(frozen=True)
class BackfillPayload:
    """The importer-ready payload plus provenance about any collapse that happened."""

    payload: dict                      # {entity: [row, ...]} — json-serializable
    warnings: tuple[str, ...] = ()
    rows_in: int = 0
    rows_out: int = 0
    collapsed_groups: int = 0
    agg_func: Optional[AggFunc] = None

    @property
    def collapsed(self) -> bool:
        return self.rows_out < self.rows_in


def _map_row(record: Mapping[str, object], result: InferenceResult) -> dict:
    """Map one raw specimen record → an importer row keyed by EMITTED field names."""
    row: dict = {}
    for raw, emitted in result.colmap.items():
        if raw in record:
            row[emitted] = record[raw]
    row[OBSERVED_AT_FIELD] = record.get("observed_at")
    return row


def build_payload(
    specimen: Specimen,
    result: InferenceResult,
    *,
    metric: str,
    aggregate: Optional[str] = None,
) -> BackfillPayload:
    """Build the ``from_json`` payload from a raw specimen, collapsing identity collisions (FR-6).

    ``aggregate`` — an explicit override (``sum`` / ``last`` / ``avg``) that always wins over the
    additivity-derived default (R1-F5).
    """
    specimen.assert_raw()  # backfill builds from the raw specimen; identity was inferred from it
    additivity = classify_additivity(metric)
    func = AggFunc(aggregate) if aggregate else _default_agg(additivity)

    id_fields = tuple(result.identity_fields)
    measure = result.measure_field

    # Group mapped rows by their identity-key values (the collapse axis).
    groups: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for record in specimen.records:
        row = _map_row(record, result)
        row[measure] = Decimal(str(record.get("value", 0)))
        key = tuple(row.get(f) for f in id_fields)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    rows: list[dict] = []
    warnings: list[str] = []
    collapsed_groups = 0
    for key in order:
        members = groups[key]
        base = dict(members[0])  # non-measure fields from the first member (deterministic)
        if len(members) > 1:
            collapsed_groups += 1
            measures = [m[measure] for m in members]
            agg = _aggregate(measures, func)
            base[measure] = _decimal_to_jsonable(agg)
            if additivity is Additivity.NON_ADDITIVE and func is AggFunc.LAST:
                warnings.append(
                    f"{metric}: {len(members)} series collapsed onto identity {list(key)} but the "
                    f"measure is non-additive — kept `last` (not summed). Pass --aggregate to override."
                )
        else:
            base[measure] = _decimal_to_jsonable(base[measure])
        rows.append(base)

    if collapsed_groups:
        logger.info(
            "FR-6: %d group(s) collapsed for %s via %s (%d→%d rows)",
            collapsed_groups, metric, func.value, len(specimen.records), len(rows),
        )

    return BackfillPayload(
        payload={result.entity: rows},
        warnings=tuple(warnings),
        rows_in=len(specimen.records),
        rows_out=len(rows),
        collapsed_groups=collapsed_groups,
        agg_func=func,
    )


def _decimal_to_jsonable(value: Decimal) -> str:
    """Emit a Decimal measure as a canonical string — the importer's ``_coerce`` decimals it back,
    lossless (a float would risk binary drift on financial values)."""
    return format(value, "f")


def records_to_json(
    specimen: Specimen,
    result: InferenceResult,
    *,
    metric: str,
    aggregate: Optional[str] = None,
) -> tuple[str, BackfillPayload]:
    """Convenience: build the payload and serialize it to the JSON string ``from_json`` accepts."""
    import json

    built = build_payload(specimen, result, metric=metric, aggregate=aggregate)
    return json.dumps(built.payload), built
