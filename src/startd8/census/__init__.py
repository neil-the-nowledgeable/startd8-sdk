"""Determinism-gap census — the code-side twin of the CRP recurring-themes census.

Instruments the LLM-driven polyglot construction path (Prime + ``micro_prime`` + ``repair``) with a
PASSIVE, OPT-IN observation hook: each LLM-call and each repair-intervention becomes a census finding
tagged by **finding-class × language × element-kind**, registered as a data-only ``startd8-census``
``RuleCatalog`` producer and rendered through the universal ``coverage_map.findings_sarif`` sink. The
aggregator derives a per-language determinism-% scoreboard from ``navigator/realization.py``'s seam and
ranks *where the LLM is load-bearing per language* as the metabolization ratchet's input.

Additive · advisory · reuse-only. The hook is OBSERVE-ONLY (records; never alters generation) and is
BYTE-IDENTICAL when disabled — the collector defaults to absent (the empty-default-is-the-guard
principle), so a census-off run threads no observations and changes nothing.

See ``docs/design/deterministic-generation/REQ-determinism-gap-census.md``.
"""

from __future__ import annotations

from .hook import (
    CensusCollector,
    CensusObservation,
    FindingClass,
    get_collector,
    record_intervention,
    set_collector,
)
from .report import CensusReport, LanguageLoad, build_report, render_sarif
from .scoreboard import LaneScore, build_scoreboard

__all__ = [
    "CensusCollector",
    "CensusObservation",
    "FindingClass",
    "get_collector",
    "record_intervention",
    "set_collector",
    "LaneScore",
    "build_scoreboard",
    "CensusReport",
    "LanguageLoad",
    "build_report",
    "render_sarif",
]
