"""Normalize the scattered construction-provenance sources into ONE per-file regime map (REQ-19 FR-3).

The construction pipeline records regime-determining signal in ≥4 scattered places (``micro_prime``
registry model/strategy, ``prime-result``, the ``$0``-skip decisions, the generation-manifest). Rather
than the navigator reaching into each (which would break the firewall), each source is expressed as
**contract records** (FR-1) — emitted at construction time (FR-2) or read from an emitted artifact — and
this normalizer unifies them: one confidence-scored record per file, conflicts resolved deterministically.

Firewall (FR-7 / NR-3): imports only :mod:`realization_contract` + stdlib — never a construction subsystem.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from .realization_contract import RealizationContractError, RealizationRecord, parse_record

# Deterministic conflict tie-break when two sources report the SAME source_confidence for one file: a
# fixed regime priority so normalization is reproducible (never order-dependent). Lower index wins.
_REGIME_PRIORITY = ("human", "llm", "deterministic")


def _rank(rec: RealizationRecord) -> tuple:
    """Sort key for choosing the winning record for a file: higher confidence first, then the fixed
    regime priority (so a tie resolves deterministically, not by input order)."""
    try:
        pri = _REGIME_PRIORITY.index(rec.regime)
    except ValueError:
        pri = len(_REGIME_PRIORITY)
    return (-rec.source_confidence, pri)


def normalize(raw_records: Iterable[Mapping]) -> Dict[str, RealizationRecord]:
    """Unify raw emitted records into one :class:`RealizationRecord` per file (FR-3).

    Each raw record is validated through the contract (a malformed one raises a named
    :class:`RealizationContractError`). When ≥2 records name the same file, the winner is the highest
    ``source_confidence``; ties break on the fixed regime priority — a deterministic resolution, not
    input-order-dependent.
    """
    by_file: Dict[str, List[RealizationRecord]] = {}
    for raw in raw_records:
        rec = parse_record(raw)  # firewall: an out-of-contract record fails loud here
        by_file.setdefault(rec.file, []).append(rec)
    resolved: Dict[str, RealizationRecord] = {}
    for file, recs in by_file.items():
        resolved[file] = sorted(recs, key=_rank)[0]
    return resolved


def load_provenance(path: Path) -> Dict[str, RealizationRecord]:
    """Read an emitted realization-provenance artifact (a JSON list of contract records, or an object with
    a ``"records"`` key) into the normalized per-file map. A missing file yields an empty map (no
    provenance → the declared fallback, byte-identical). Malformed JSON / records fail loud."""
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records") if isinstance(data, Mapping) else data
    if not isinstance(records, list):
        raise RealizationContractError(f"{path}: expected a list of records (or an object with 'records')")
    return normalize(records)
