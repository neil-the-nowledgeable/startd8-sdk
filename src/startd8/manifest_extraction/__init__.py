"""Deterministic manifest extraction — kickoff docs (authoring-contract format) → assembly manifests.

The extraction half of the wireframe↓ingestion wiring (FR-WPI-1..4): parses kickoff docs that
conform to ``docs/design/kickoff/KICKOFF_AUTHORING_CONTRACT.md`` (v0.2 grammar) into the
deterministic cascade's input manifests, with per-value traceability (FR-WPI-3) and round-trip
validation through the generators' own parsers (FR-WPI-4). **No LLM anywhere** — values a
formatted document determines are extracted, never generated.

Extraction ordering is a constraint, not a choice (CRP R2): entities/relationships first →
views (``Shows:`` fks derive from the join models) → completeness (category words map to the
derived join-model names).

Public API: :func:`extract_manifests`.
"""

from .models import (
    ExtractionRecord,
    ExtractionResult,
    GRAMMAR_VERSION,
    RoundTripError,
    SourceRef,
    Status,
)
from .extract import extract_manifests
from .report import report_to_json, report_to_markdown

__all__ = [
    "ExtractionRecord",
    "ExtractionResult",
    "GRAMMAR_VERSION",
    "RoundTripError",
    "SourceRef",
    "Status",
    "extract_manifests",
    "report_to_json",
    "report_to_markdown",
]
