"""Extraction record/result models (FR-WPI-3 identity + canonical form).

Value identity = ``(manifest filename, canonical value-path)`` — JSON-pointer style, e.g.
``views.yaml#/views/2/route``. Source locators are structured (``{doc, heading_path,
row_index}``), never free prose. Reports sort by identity key and are byte-stable across
identical-input runs (CRP R1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Pinned to the authoring contract version these grammars implement (FR-WPI-11c: the
# vocabularies are corpus-versioned; bump together with KICKOFF_AUTHORING_CONTRACT.md).
GRAMMAR_VERSION = "authoring-contract-v0.2"


class Status:
    EXTRACTED = "extracted"
    NOT_EXTRACTED = "not_extracted"
    DEFAULTED = "defaulted"


@dataclass(frozen=True)
class SourceRef:
    """Structured source locator (FR-WPI-3): where in the kickoff docs a value came from."""

    doc: str                                  # doc label/path as supplied to extract_manifests
    heading_path: Tuple[str, ...] = ()        # e.g. ("Entities", "ProofPoint")
    row_index: Optional[int] = None           # table row (0-based, excluding header) when tabular
    line: Optional[str] = None                # the matched sentence/line, when not tabular


@dataclass(frozen=True)
class ExtractionRecord:
    """One per-value traceability row (the report currency)."""

    manifest: str                             # e.g. "pages.yaml" / "schema.prisma"
    value_path: str                           # canonical, e.g. "/pages/0/slug"
    status: str                               # Status.*
    value: Optional[str] = None
    source: Optional[SourceRef] = None
    reason: Optional[str] = None              # for not_extracted/defaulted

    @property
    def identity(self) -> Tuple[str, str]:
        return (self.manifest, self.value_path)


class RoundTripError(RuntimeError):
    """FR-WPI-4: an emitted manifest failed its generator parser — a BUG, not a report flag."""


@dataclass
class ExtractionResult:
    """Everything one extraction pass produced."""

    manifests: Dict[str, str] = field(default_factory=dict)   # filename -> emitted text
    records: List[ExtractionRecord] = field(default_factory=list)
    contract_diff: List[str] = field(default_factory=list)    # DIFF mode (FR-WPI-8): doc vs live contract
    source_docs: Dict[str, str] = field(default_factory=dict)  # doc label -> sha256 (FR-WPI-7 linkage)
    grammar_version: str = GRAMMAR_VERSION

    def sorted_records(self) -> List[ExtractionRecord]:
        return sorted(self.records, key=lambda r: r.identity)

    def by_status(self, status: str) -> List[ExtractionRecord]:
        return [r for r in self.records if r.status == status]
