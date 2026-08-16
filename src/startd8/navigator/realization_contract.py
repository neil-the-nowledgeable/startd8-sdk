"""The realization-provenance contract (REQ-19 FR-1) — the SOLE coupling surface between the construction
pipeline and the navigator.

Construction paths (``backend_codegen`` / ``contractors`` / ``micro_prime``) **emit** these records; the
navigator **consumes** them. The navigator's realization path imports THIS module and *no construction
subsystem* — the modularity firewall (the ``DELIVERY_EVIDENCE_CONTRACT`` pattern). A construction
subsystem may refactor freely so long as it still emits conforming records; a schema change is the sole
reviewed coupling event, guarded by ``test_realization_contract``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

from .models import RealizationRegime

CONTRACT_VERSION = "1.0"


class RealizationContractError(ValueError):
    """A malformed realization-provenance record — named so a bad emit fails loud, never silently."""


@dataclass(frozen=True)
class RealizationProvenance:
    """Optional per-record provenance detail — the LLM path carries ``model``/``strategy``/``cost``; the
    deterministic path carries none (all ``None``)."""

    model: Optional[str] = None
    strategy: Optional[str] = None
    cost: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in
                (("model", self.model), ("strategy", self.strategy), ("cost", self.cost)) if v is not None}


@dataclass(frozen=True)
class RealizationRecord:
    """One construction-provenance record: a file, the regime that produced it, a source confidence in
    ``[0,1]``, and optional provenance detail. The typed contract the navigator depends on."""

    file: str
    regime: str  # deterministic | llm | human
    source_confidence: float
    provenance: RealizationProvenance = field(default_factory=RealizationProvenance)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"file": self.file, "regime": self.regime,
                             "source_confidence": self.source_confidence}
        prov = self.provenance.to_dict()
        if prov:
            d["provenance"] = prov
        return d


def _opt_str(v: Any) -> Optional[str]:
    return None if v is None else str(v)


def parse_record(raw: Mapping[str, Any]) -> RealizationRecord:
    """Validate + build a :class:`RealizationRecord` from a raw emitted dict, raising a **named**
    :class:`RealizationContractError` on any malformed field — the firewall's schema gate."""
    if not isinstance(raw, Mapping):
        raise RealizationContractError(f"record must be a mapping, got {type(raw).__name__}")
    file = raw.get("file")
    if not isinstance(file, str) or not file.strip():
        raise RealizationContractError(f"record 'file' must be a non-empty string, got {file!r}")
    regime = raw.get("regime")
    if regime not in RealizationRegime.DECLARABLE:
        raise RealizationContractError(
            f"record 'regime' must be one of {RealizationRegime.DECLARABLE}, got {regime!r} (file {file!r})")
    sc = raw.get("source_confidence")
    if isinstance(sc, bool) or not isinstance(sc, (int, float)) or not (0.0 <= float(sc) <= 1.0):
        raise RealizationContractError(
            f"record 'source_confidence' must be a number in [0,1], got {sc!r} (file {file!r})")
    prov_raw = raw.get("provenance") or {}
    if not isinstance(prov_raw, Mapping):
        raise RealizationContractError(
            f"record 'provenance' must be a mapping, got {type(prov_raw).__name__} (file {file!r})")
    cost = prov_raw.get("cost")
    if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float))):
        raise RealizationContractError(f"provenance 'cost' must be a number, got {cost!r} (file {file!r})")
    prov = RealizationProvenance(
        model=_opt_str(prov_raw.get("model")),
        strategy=_opt_str(prov_raw.get("strategy")),
        cost=None if cost is None else float(cost),
    )
    return RealizationRecord(file=str(file), regime=str(regime), source_confidence=float(sc), provenance=prov)


def make_record(
    file: str, regime: str, source_confidence: float,
    *, model: Optional[str] = None, strategy: Optional[str] = None, cost: Optional[float] = None,
) -> Dict[str, Any]:
    """Construction-side emit helper (FR-2): build a **validated** conforming record dict. A construction
    path calls this so an out-of-contract emit fails loud at the source, not silently downstream."""
    rec = parse_record({
        "file": file, "regime": regime, "source_confidence": source_confidence,
        "provenance": {"model": model, "strategy": strategy, "cost": cost},
    })
    return rec.to_dict()
