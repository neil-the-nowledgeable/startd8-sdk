"""M1 — Specimen materialization (FR-2, FR-9).

Flattens a :class:`~startd8.tsdb_maturation.reader.ReadResult` into a **durable, raw**
specimen file: one record per series ``{<label>:…, "value": <float>, "observed_at":
<iso8601>}``. The specimen is the input to M2's inference (FR-3/FR-4).

Two load-bearing contracts, both CRP-hardened:

* **Raw only, un-collapsed (R1-F9 / OQ-13).** A specimen built here stores **raw** series —
  ``n_records == len(read_result.series)`` — and is marked ``aggregated=False``. Aggregation
  is deferred to FR-6 (M5), which needs the *inferred* identity. M2's identity inference
  (FR-4) must consume only a raw specimen; :func:`Specimen.assert_raw` is the guard that pins
  the ``specimen → identity → aggregate`` ordering so no cycle can form.
* **Grain honesty (FR-9, §0.1 fail-safe).** Every specimen carries a :class:`Grain` marker.
  A TSDB read is a snapshot/rollup → :attr:`Grain.TSDB_AGGREGATE` (least-trusted); a
  lossless per-event source → :attr:`Grain.IMPORT_SOURCE`. An **unknown/missing grain
  defaults to the least-trusted value** (never ``import_source``): a dropped marker must
  degrade fidelity claims, not inflate them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, Union

from startd8.logging_config import get_logger

from .reader import ReadResult, Series

logger = get_logger(__name__)

# Record keys the flattener owns; a label colliding with one of these would silently shadow
# the measure/timestamp, so it is refused loudly instead (FR-2 record shape).
RESERVED_RECORD_KEYS = ("value", "observed_at")

Record = dict[str, Union[str, float]]


class SpecimenError(RuntimeError):
    """A specimen could not be built or is being misused (e.g. aggregated fed to FR-4)."""


class Grain(str, Enum):
    """Provenance/grain of a specimen's records (FR-9).

    Ordered by *trust*: ``IMPORT_SOURCE`` is faithful per-event source data; ``TSDB_AGGREGATE``
    is a TSDB snapshot/rollup and MUST NOT be presented as faithful per-event data.
    """

    IMPORT_SOURCE = "import_source"
    TSDB_AGGREGATE = "tsdb_aggregate"

    @classmethod
    def coerce(cls, value: object) -> "Grain":
        """Resolve a grain, **defaulting unknown/missing to the least-trusted value**.

        A dropped marker degrades fidelity claims (→ ``TSDB_AGGREGATE``), never inflates them
        (never silently ``IMPORT_SOURCE``). §0.1 fail-safe (issue #115).
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                logger.warning(
                    "unknown grain %r → defaulting to least-trusted %s (FR-9 fail-safe)",
                    value,
                    cls.TSDB_AGGREGATE.value,
                )
        return cls.TSDB_AGGREGATE


def _iso8601(ts: float) -> str:
    """Format a Unix-seconds timestamp as ISO-8601 UTC (``…Z``)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def flatten_series(series: Iterable[Series]) -> list[Record]:
    """Flatten TSDB series into specimen records — one record per series (FR-2).

    Each record is ``{<label>: <str>, …, "value": <float>, "observed_at": <iso8601>}``. A
    label colliding with a reserved record key (``value``/``observed_at``) is refused, since
    it would otherwise silently shadow the measure or timestamp.
    """
    records: list[Record] = []
    for s in series:
        clashing = [k for k in RESERVED_RECORD_KEYS if k in s.labels]
        if clashing:
            raise SpecimenError(
                f"label(s) {clashing} collide with reserved record key(s) "
                f"{list(RESERVED_RECORD_KEYS)}; cannot flatten without shadowing the measure/"
                "timestamp (rename the label upstream or extend the reserved-key handling)"
            )
        record: Record = dict(s.labels)
        record["value"] = s.value
        record["observed_at"] = _iso8601(s.timestamp)
        records.append(record)
    return records


@dataclass(frozen=True)
class Specimen:
    """A durable, materialized specimen — the raw input to inference (FR-2/FR-9)."""

    metric: str
    grain: Grain
    records: tuple[Record, ...]
    lookback: Optional[str] = None
    aggregated: bool = False

    @property
    def n_records(self) -> int:
        return len(self.records)

    # -- construction ------------------------------------------------------ #
    @classmethod
    def from_read_result(
        cls,
        result: ReadResult,
        grain: object = Grain.TSDB_AGGREGATE,
    ) -> "Specimen":
        """Build a raw specimen from an M0 read. TSDB reads default to the least-trusted grain.

        Enforces the raw invariant ``n_records == len(result.series)`` (R1-F9): a TSDB read is
        one-record-per-series by construction, un-collapsed.
        """
        records = flatten_series(result.series)
        specimen = cls(
            metric=result.metric,
            grain=Grain.coerce(grain),
            records=tuple(records),
            lookback=result.lookback,
            aggregated=False,
        )
        if specimen.n_records != len(result.series):  # defensive: the raw invariant must hold
            raise SpecimenError(
                f"raw invariant violated: {specimen.n_records} records != "
                f"{len(result.series)} series"
            )
        return specimen

    @classmethod
    def from_records(
        cls,
        metric: str,
        records: Sequence[Mapping[str, object]],
        grain: object = Grain.IMPORT_SOURCE,
        *,
        aggregated: bool = False,
        lookback: Optional[str] = None,
    ) -> "Specimen":
        """Build a specimen from already-flattened records (FR-9 mode (a): lossless source)."""
        return cls(
            metric=metric,
            grain=Grain.coerce(grain),
            records=tuple(dict(r) for r in records),  # type: ignore[arg-type]
            lookback=lookback,
            aggregated=aggregated,
        )

    # -- FR-4 input guard (R1-F9) ------------------------------------------ #
    def assert_raw(self) -> "Specimen":
        """Guard M2/FR-4's input: identity is inferred from a RAW specimen only.

        Feeding an already-aggregated specimen to identity inference raises, pinning the
        ``specimen → identity → aggregate`` ordering so no cycle (specimen→identity→aggregate→
        specimen) can form. Returns ``self`` for chaining.
        """
        if self.aggregated:
            raise SpecimenError(
                "identity inference (FR-4) requires a RAW specimen (record-per-series, "
                "un-collapsed); this specimen is marked aggregated=True — infer identity "
                "BEFORE aggregating (OQ-13)"
            )
        return self

    # -- label helpers (used by dry-run + M2) ------------------------------ #
    def label_keys(self) -> list[str]:
        """Sorted union of label keys across records (excludes the reserved record keys)."""
        keys: set[str] = set()
        for r in self.records:
            keys.update(k for k in r if k not in RESERVED_RECORD_KEYS)
        return sorted(keys)

    def cardinality(self) -> dict[str, int]:
        """Distinct-value count per label key — the M2/FR-5 reduction signal (high card → top-N)."""
        counts: dict[str, set] = {k: set() for k in self.label_keys()}
        for r in self.records:
            for k, seen in counts.items():
                if k in r:
                    seen.add(r[k])
        return {k: len(v) for k, v in counts.items()}

    # -- persistence ------------------------------------------------------- #
    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "grain": self.grain.value,
            "lookback": self.lookback,
            "aggregated": self.aggregated,
            "n_records": self.n_records,
            "records": [dict(r) for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Specimen":
        records = data.get("records") or []
        return cls(
            metric=str(data.get("metric", "")),
            grain=Grain.coerce(data.get("grain")),
            records=tuple(dict(r) for r in records),  # type: ignore[arg-type]
            lookback=data.get("lookback"),  # type: ignore[arg-type]
            aggregated=bool(data.get("aggregated", False)),
        )


def write_specimen(specimen: Specimen, path: Union[str, Path]) -> Path:
    """Durably write a specimen to JSON (atomic: temp file + ``os.replace``)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(specimen.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp, path)
    logger.debug("wrote specimen: %s (%d records, grain=%s)", path, specimen.n_records, specimen.grain.value)
    return path


def load_specimen(path: Union[str, Path]) -> Specimen:
    """Load a specimen written by :func:`write_specimen` (round-trips ``to_dict``)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Specimen.from_dict(data)


# --------------------------------------------------------------------------- #
# Dry-run summary (FR-2: "reports counts + a sample").                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SpecimenSummary:
    metric: str
    grain: Grain
    n_records: int
    label_keys: tuple[str, ...]
    cardinality: Mapping[str, int]
    sample: Optional[Record]

    def render(self) -> str:
        lines = [
            f"specimen: {self.metric}",
            f"  grain:     {self.grain.value}"
            + ("  (least-trusted — TSDB snapshot, not per-event)"
               if self.grain is Grain.TSDB_AGGREGATE else ""),
            f"  records:   {self.n_records}",
            f"  labels ({len(self.label_keys)}):",
        ]
        for k in self.label_keys:
            lines.append(f"    {k}: {self.cardinality.get(k, 0)} distinct")
        if self.sample is not None:
            lines.append(f"  sample: {json.dumps(self.sample, sort_keys=True)}")
        return "\n".join(lines)


def summarize(specimen: Specimen) -> SpecimenSummary:
    """Build a dry-run summary (counts + per-label cardinality + one sample record)."""
    return SpecimenSummary(
        metric=specimen.metric,
        grain=specimen.grain,
        n_records=specimen.n_records,
        label_keys=tuple(specimen.label_keys()),
        cardinality=specimen.cardinality(),
        sample=dict(specimen.records[0]) if specimen.records else None,
    )
