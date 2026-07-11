"""M1 — Live extraction-state service + the canonical view-model.

This is the keystone of the kickoff experience: a **read-only**, ``$0`` fold over the
manifest-extraction ``ExtractionResult`` into a typed, serializable state that both surfaces
render identically.

Design decisions carried in from the requirements/CRP (do not re-litigate):

* **Single serializer / one derivation point (R1-S7, R1-F8).** ``FieldState.to_dict()`` is the
  ONE place the per-field view-model — including the derived *attention* and *ambiguity* labels —
  is computed. The web (M4) and TUI (M5) are both pure functions of this output, so FR-3 parity is
  testable against a single oracle rather than two renderers.
* **Real status vocabulary only (FR-6).** The extraction grammar emits exactly
  ``extracted / defaulted / not_extracted`` (``manifest_extraction.Status``). There is **no
  ``ambiguous`` status**; "ambiguity" is a derived UI sub-label over the free-text ``reason`` on a
  ``not_extracted`` record. We classify ``reason`` into a closed set of recognized patterns plus a
  catch-all (``Ambiguity.OTHER``) — see :func:`classify_ambiguity`.
* **No broadened read (R3-S4 / R3-F7).** The source inventory reports only over
  ``result.source_docs`` — exactly the docs handed to ``extract_manifests`` — so transparency never
  becomes a new read path.
* **``defaulted`` is provenance-critical (FR-NEW-5).** It is a first-class, distinctly-rendered
  attention class; a defaulted value is an estimate that must never read as author-confirmed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from ..manifest_extraction import extract_manifests
from ..manifest_extraction.models import ExtractionRecord, ExtractionResult, Status

# The CLI checker's marker for an SDK-backlog gap (a `not_extracted` the SDK cannot yet emit,
# never an author error). Mirrors ``cli_kickoff._GENERATOR_GAP_MARKER`` — kept in sync by the
# round-trip nature of the grammar; both read the same ``reason`` text.
_GENERATOR_GAP_MARKER = "generator-gap"


class Attention:
    """Derived per-field UI class — the single signal both surfaces badge on.

    A *projection* of the raw extraction status into what the author should DO:
        OK       — extracted; nothing to do.
        REVIEW   — defaulted; a value the grammar filled in, needs human confirmation (FR-NEW-5).
        BLOCKED  — not_extracted and author-actionable; the grammar saw something it could not take.
        BACKLOG  — not_extracted but an SDK generator-gap; not the author's fault, not gating.
    """

    OK = "ok"
    REVIEW = "review"
    BLOCKED = "blocked"
    BACKLOG = "backlog"


class Ambiguity:
    """Closed set of derived ambiguity sub-labels for a BLOCKED field (over free-text ``reason``).

    ``reason`` strings are not a closed grammar vocabulary, so this classifier recognizes a fixed
    set of patterns and falls through to ``OTHER`` — the catch-all is explicit, not silent.
    """

    NONE = "none"                       # not a blocked field
    UNRESOLVED_REFERENCE = "unresolved_reference"   # names an entity/field that isn't declared
    OUT_OF_GRAMMAR = "out_of_grammar"   # phrase/verb/kind outside the closed vocabulary
    MALFORMED_BLOCK = "malformed_block"  # structural: missing table/field-row/required line
    INVALID_VALUE = "invalid_value"     # wrong type / value outside an allowed set
    DUPLICATE = "duplicate"             # collides with an earlier declaration
    OTHER = "other"                     # recognized as blocked, reason not in the patterns above


# Ordered (first match wins) — grounded in the actual ``reason=`` strings the extractors emit
# (manifest_extraction/{entities,extractors}.py). Patterns are substrings/regexes, case-insensitive.
_AMBIGUITY_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (Ambiguity.DUPLICATE, re.compile(r"\bduplicate\b|first wins", re.I)),
    (
        Ambiguity.UNRESOLVED_REFERENCE,
        re.compile(
            r"not declared|unresolvable|resolves to no|names no declared|dangling target"
            r"|does not reference|neither a category word nor a declared|no .*join model",
            re.I,
        ),
    ),
    (
        Ambiguity.OUT_OF_GRAMMAR,
        re.compile(
            r"outside the .*(vocabulary|grammar)|outside the published|matches neither"
            r"|not a registered|without '?x to y'?|unknown .*(group|key|control-id)"
            r"|only `?not-applicable`?|is never split-parsed",
            re.I,
        ),
    ),
    (
        Ambiguity.MALFORMED_BLOCK,
        re.compile(
            r"has no table|has no field table|no field table|no pipe-separated"
            r"|line \(required\)|row missing|has no .*line|no field table",
            re.I,
        ),
    ),
    (Ambiguity.INVALID_VALUE, re.compile(r"must be a boolean|got .*!r|value .*outside", re.I)),
)


def classify_ambiguity(record: ExtractionRecord) -> str:
    """The single derivation point for the 'ambiguous' UI sub-label (R1-F8 / R1-S7).

    Returns an :class:`Ambiguity` member. ``NONE`` for anything that is not an author-actionable
    ``not_extracted`` (extracted/defaulted/backlog fields are never "ambiguous").
    """
    if record.status != Status.NOT_EXTRACTED:
        return Ambiguity.NONE
    reason = record.reason or ""
    if _GENERATOR_GAP_MARKER in reason:
        return Ambiguity.NONE  # backlog, not an author-facing ambiguity
    for label, pattern in _AMBIGUITY_PATTERNS:
        if pattern.search(reason):
            return label
    return Ambiguity.OTHER


def _attention_for(record: ExtractionRecord) -> str:
    if record.status == Status.EXTRACTED:
        return Attention.OK
    if record.status == Status.DEFAULTED:
        return Attention.REVIEW
    # not_extracted
    if _GENERATOR_GAP_MARKER in (record.reason or ""):
        return Attention.BACKLOG
    return Attention.BLOCKED


@dataclass(frozen=True)
class FieldState:
    """One field's canonical, render-ready state — the unit both surfaces consume.

    Derived from exactly one :class:`ExtractionRecord`. The ``attention`` and ``ambiguity`` labels
    are computed here once; renderers never re-derive them (parity guarantee).
    """

    manifest: str
    value_path: str
    status: str                       # raw Status.* (extracted/defaulted/not_extracted)
    attention: str                    # derived Attention.*
    ambiguity: str                    # derived Ambiguity.*
    value: Optional[str] = None
    reason: Optional[str] = None
    source_doc: Optional[str] = None
    source_heading: Tuple[str, ...] = ()
    source_row: Optional[int] = None

    @property
    def identity(self) -> Tuple[str, str]:
        return (self.manifest, self.value_path)

    @classmethod
    def from_record(cls, record: ExtractionRecord) -> "FieldState":
        src = record.source
        return cls(
            manifest=record.manifest,
            value_path=record.value_path,
            status=record.status,
            attention=_attention_for(record),
            ambiguity=classify_ambiguity(record),
            value=record.value,
            reason=record.reason,
            source_doc=src.doc if src else None,
            source_heading=tuple(src.heading_path) if src else (),
            source_row=src.row_index if src else None,
        )

    def to_dict(self) -> dict:
        """The canonical serialization. Both M4 and M5 render *only* from this (R1-S7)."""
        d: Dict[str, object] = {
            "manifest": self.manifest,
            "value_path": self.value_path,
            "status": self.status,
            "attention": self.attention,
            "ambiguity": self.ambiguity,
        }
        if self.value is not None:
            d["value"] = self.value
        if self.reason is not None:
            d["reason"] = self.reason
        if self.source_doc is not None:
            src: Dict[str, object] = {"doc": self.source_doc}
            if self.source_heading:
                src["heading_path"] = list(self.source_heading)
            if self.source_row is not None:
                src["row_index"] = self.source_row
            d["source"] = src
        return d


def field_states(result: ExtractionResult) -> List[FieldState]:
    """Fold an ``ExtractionResult`` into per-field state, sorted by identity (byte-stable order)."""
    return [FieldState.from_record(r) for r in result.sorted_records()]


@dataclass(frozen=True)
class SourceInventory:
    """What the extraction pass actually looked at (R3-S4) — bounded to ``result.source_docs``.

    No broadened read (R3-F7): every doc here was already handed to ``extract_manifests``.
    """

    docs_inspected: Tuple[str, ...]                 # every doc label passed in (sorted)
    docs_with_records: Tuple[str, ...]              # docs that produced >=1 sourced record
    ignored_docs: Tuple[str, ...]                   # inspected but produced no sourced record
    record_counts_by_doc: Mapping[str, int]         # doc -> # of records traced to it

    def to_dict(self) -> dict:
        return {
            "docs_inspected": list(self.docs_inspected),
            "docs_with_records": list(self.docs_with_records),
            "ignored_docs": list(self.ignored_docs),
            "record_counts_by_doc": dict(sorted(self.record_counts_by_doc.items())),
        }


def source_inventory(result: ExtractionResult) -> SourceInventory:
    """Build the source inventory purely from the extraction result (no extra reads)."""
    inspected = tuple(sorted(result.source_docs))
    counts: Dict[str, int] = {doc: 0 for doc in inspected}
    for r in result.records:
        if r.source and r.source.doc:
            counts[r.source.doc] = counts.get(r.source.doc, 0) + 1
    with_records = tuple(sorted(doc for doc, n in counts.items() if n > 0))
    ignored = tuple(sorted(doc for doc in inspected if counts.get(doc, 0) == 0))
    return SourceInventory(
        docs_inspected=inspected,
        docs_with_records=with_records,
        ignored_docs=ignored,
        record_counts_by_doc=counts,
    )


@dataclass(frozen=True)
class KickoffState:
    """The full canonical state snapshot — the single object the UIs serialize and parity-test.

    ``M3`` (step config) and ``M2`` (readiness) layer on top; this M1 core carries the field-level
    extraction state, the source inventory, and the status counts.
    """

    fields: Tuple[FieldState, ...]
    inventory: SourceInventory
    grammar_version: str
    contract_diff: Tuple[str, ...] = ()

    @property
    def counts(self) -> Dict[str, int]:
        out = {Status.EXTRACTED: 0, Status.DEFAULTED: 0, Status.NOT_EXTRACTED: 0}
        for f in self.fields:
            out[f.status] = out.get(f.status, 0) + 1
        return out

    @property
    def attention_counts(self) -> Dict[str, int]:
        out = {Attention.OK: 0, Attention.REVIEW: 0, Attention.BLOCKED: 0, Attention.BACKLOG: 0}
        for f in self.fields:
            out[f.attention] = out.get(f.attention, 0) + 1
        return out

    def blocked_fields(self) -> List[FieldState]:
        """Author-actionable gaps (FR-6) — the worklist, in byte-stable identity order.

        Sorted defensively so the next-action ranking is deterministic for parity (R2-S3)
        regardless of how the state was assembled.
        """
        return sorted(
            (f for f in self.fields if f.attention == Attention.BLOCKED),
            key=lambda f: f.identity,
        )

    def to_dict(self) -> dict:
        """Canonical snapshot. Deterministic + byte-stable for a given extraction result."""
        return {
            "grammar_version": self.grammar_version,
            "counts": self.counts,
            "attention_counts": self.attention_counts,
            "inventory": self.inventory.to_dict(),
            "fields": [f.to_dict() for f in self.fields],
            "contract_diff": list(self.contract_diff),
        }


def build_kickoff_state(
    docs: Mapping[str, str],
    *,
    live_schema_text: Optional[str] = None,
) -> KickoffState:
    """Run manifest extraction (``$0``, no LLM) and fold it into the canonical state.

    Pure function of *docs* (+ optional live contract). Re-run freely per capture (FR-5 / OQ-5:
    extraction is synchronous and free, so no caching is needed for correctness).
    """
    result = extract_manifests(docs, live_schema_text=live_schema_text)
    return KickoffState(
        fields=tuple(field_states(result)),
        inventory=source_inventory(result),
        grammar_version=result.grammar_version,
        contract_diff=tuple(result.contract_diff),
    )


def resolve_kickoff_state(project_root: str | Path) -> KickoffState:
    """Derive the canonical :class:`KickoffState` for a project from its on-disk kickoff docs.

    The ONE home for the ``load_kickoff_docs`` → ``build_kickoff_state(…, live_schema_text=…)``
    derivation every surface needs (cockpit oracle, web, chat, portal). Previously this three-line
    incantation was re-typed per surface; a caller that dropped ``live_schema_text=`` silently got a
    degraded state. Accepts ``str`` or ``Path`` (both underlying loaders do). ``$0``, pure per docs.
    """
    from .docs import live_schema_text, load_kickoff_docs

    docs = load_kickoff_docs(project_root)
    state = build_kickoff_state(docs, live_schema_text=live_schema_text(project_root))
    # Fold the value-input / confirmed.yaml layout (assess's model) so the ONE oracle also reflects
    # value-input-driven projects (instantiated packages / the benchmark portal), which the markdown
    # extraction above is blind to. Union by value_path IDENTITY — value-input fields fill only the
    # identities the markdown path didn't already produce (FR-3), so a markdown project is byte-identical
    # (no value-inputs ⇒ nothing added; FR-4). Best-effort: never breaks the markdown path.
    try:
        from dataclasses import replace

        from .value_inputs import value_input_field_states

        existing = {f.value_path for f in state.fields}
        extra = tuple(
            f for f in value_input_field_states(project_root) if f.value_path not in existing
        )
        if extra:
            return replace(state, fields=state.fields + extra)
    except Exception:  # pragma: no cover - value-input coverage is additive, never load-bearing
        pass
    return state
