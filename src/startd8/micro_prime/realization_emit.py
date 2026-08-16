"""Emit realization-provenance records for the LLM (interpreter) generation path (REQ-19 FR-2).

When MicroPrime / the contractors generate an element with a model, the produced file is an ``llm``-regime
record carrying ``provenance.model`` (+ optional ``strategy``/``cost``) and the generation's own confidence.
Imports the navigator's realization **contract** (the firewall direction); the navigator normalizes + joins
these records, never importing this module.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from startd8.navigator.realization_contract import make_record


def llm_record(
    file: str,
    *,
    model: str,
    confidence: float = 1.0,
    strategy: Optional[str] = None,
    cost: Optional[float] = None,
) -> Dict[str, Any]:
    """One conforming ``llm``-regime record for a model-generated file, carrying ``provenance.model``
    (required — an llm record without a model is not traceable) and optional ``strategy``/``cost``.
    ``confidence`` is the generation's own certainty (a repaired/uncertain gen may pass a lower value,
    which the navigator seam then gates)."""
    if not model or not str(model).strip():
        from startd8.navigator.realization_contract import RealizationContractError
        raise RealizationContractError(f"llm record for {file!r} requires a provenance.model")
    return make_record(file, "llm", confidence, model=str(model), strategy=strategy, cost=cost)
