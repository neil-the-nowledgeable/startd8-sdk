"""§2.1 Entities pass — entity blocks + the closed relationship grammar (CRP R1).

Runs FIRST (extraction-ordering constraint): downstream extractors need the derived join
models (views ``Shows:`` fks, completeness category words) and the field notes
(``ONLY HUMANS ENTER THIS`` → human_inputs).

Pilot posture (FR-WPI-8): **DIFF mode** — no Prisma writer exists; the doc-derived graph is
compared against the live contract and reported, never emitted. Greenfield DRAFT mode is P7.

Closed grammar implemented (contract v0.2):
- plain types: text/long text → String; number → Int; decimal → Float; date, date+time →
  DateTime; yes/no → Boolean; ``choice of: a|b|c`` → enum (one field per row; slash-rows flag)
- relationship verbs: **has one / has many / belongs to / links to many / links X to Y**;
  symmetric ``links to many`` restatements dedup to ONE join model named by first-declaration
  order; the 3-entity form joins (X, Y) with the subject contributing no FK
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema
from .grammar import Section, md_tables, plural_candidates, strip_annotations
from .models import ExtractionRecord, SourceRef, Status

# Plain-type vocabulary → Prisma scalar (contract §2.1, CRP-decided Int/Float split).
PLAIN_TYPES: Dict[str, str] = {
    "text": "String",
    "long text": "String",
    "number": "Int",
    "decimal": "Float",
    "date": "DateTime",
    "date+time": "DateTime",
    "yes/no": "Boolean",
}

_CHOICE_RE = re.compile(r"^choice of:\s*(.+)$", re.IGNORECASE)
_HUMAN_ONLY_RE = re.compile(r"ONLY HUMANS ENTER", re.IGNORECASE)
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _lower_camel(name: str) -> str:
    return name[0].lower() + name[1:] if name else name


@dataclass(frozen=True)
class DocField:
    name: str
    plain_type: str
    prisma_type: Optional[str]      # None when the plain type is outside the vocabulary
    required: bool
    notes: str
    human_only: bool
    row_index: int


@dataclass(frozen=True)
class DocEntity:
    name: str
    fields: Tuple[DocField, ...]
    heading_path: Tuple[str, ...]


@dataclass(frozen=True)
class JoinModel:
    """An M2M join derived from the relationship grammar."""

    name: str                        # e.g. "CapabilityOutcome" (first-declaration order)
    left: str
    right: str

    @property
    def fk_left(self) -> str:
        return f"{_lower_camel(self.left)}Id"

    @property
    def fk_right(self) -> str:
        return f"{_lower_camel(self.right)}Id"


@dataclass
class EntityGraph:
    """Everything downstream extractors need from the §2.1 pass."""

    entities: Dict[str, DocEntity] = field(default_factory=dict)
    joins: List[JoinModel] = field(default_factory=list)
    fk_parents: Dict[str, List[str]] = field(default_factory=dict)  # child -> [parent,...]

    @property
    def join_names(self) -> List[str]:
        return [j.name for j in self.joins]

    def all_model_names(self) -> List[str]:
        return list(self.entities) + self.join_names

    def join_between(self, a: str, b: str) -> Optional[JoinModel]:
        for j in self.joins:
            if {j.left, j.right} == {a, b}:
                return j
        return None

    def resolve_entity(self, surface: str) -> Optional[str]:
        """Resolve a (possibly plural / spaced) surface form to a declared entity name."""
        squashed = re.sub(r"[^a-zA-Z]", "", surface)
        by_lower = {e.lower(): e for e in self.entities}
        for cand in plural_candidates(squashed):
            hit = by_lower.get(cand.lower())
            if hit:
                return hit
        return None


def extract_entities(
    doc_label: str,
    entity_sections: List[Section],
    records: List[ExtractionRecord],
) -> EntityGraph:
    """Parse the ### blocks under ## Entities into the graph; record per-value traceability."""
    graph = EntityGraph()
    relationship_lines: List[Tuple[str, str, Tuple[str, ...]]] = []  # (subject, text, path)

    for sec in entity_sections:
        name = sec.title
        tables = md_tables(sec.body)
        if not tables:
            records.append(ExtractionRecord(
                "schema.prisma", f"/models/{name}", Status.NOT_EXTRACTED,
                source=SourceRef(doc_label, sec.heading_path),
                reason="entity block has no field table",
            ))
            continue
        fields: List[DocField] = []
        for i, row in enumerate(tables[0].dicts()):
            fname = strip_annotations(row.get("field", ""))
            ftype = strip_annotations(row.get("type", "")).lower()
            req = strip_annotations(row.get("required", "")).lower() == "yes"
            notes = row.get("notes", "")
            if not fname:
                continue
            if "/" in fname:
                records.append(ExtractionRecord(
                    "schema.prisma", f"/models/{name}/fields/{fname}", Status.NOT_EXTRACTED,
                    source=SourceRef(doc_label, sec.heading_path, row_index=i),
                    reason="one-field-per-row: slash-row is never split-parsed",
                ))
                continue
            prisma_type: Optional[str] = PLAIN_TYPES.get(ftype)
            choice = _CHOICE_RE.match(ftype)
            if choice:
                prisma_type = f"{name}{fname[0].upper()}{fname[1:]}"  # enum type name
            if prisma_type is None:
                records.append(ExtractionRecord(
                    "schema.prisma", f"/models/{name}/fields/{fname}", Status.NOT_EXTRACTED,
                    source=SourceRef(doc_label, sec.heading_path, row_index=i),
                    reason=f"type {ftype!r} outside the plain-type vocabulary",
                ))
            fields.append(DocField(
                name=fname, plain_type=ftype, prisma_type=prisma_type,
                required=req, notes=notes,
                human_only=bool(_HUMAN_ONLY_RE.search(notes)),
                row_index=i,
            ))
        graph.entities[name] = DocEntity(name, tuple(fields), sec.heading_path)
        records.append(ExtractionRecord(
            "schema.prisma", f"/models/{name}", Status.EXTRACTED,
            value=f"{len(fields)} fields",
            source=SourceRef(doc_label, sec.heading_path),
        ))
        # Relationship sentences: the "Relationships:" paragraph (may wrap lines).
        rel_text = _relationship_paragraph(sec.body)
        if rel_text:
            relationship_lines.append((name, rel_text, sec.heading_path))

    # Second pass — relationships need the full entity set for surface-form resolution.
    for subject, text, path in relationship_lines:
        _parse_relationships(doc_label, subject, text, path, graph, records)
    return graph


def _relationship_paragraph(body: str) -> str:
    """The text of the ``Relationships:`` paragraph, joined across wrapped lines."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("Relationships:"):
            collected = [line.split(":", 1)[1]]
            for cont in lines[i + 1:]:
                if not cont.strip() or cont.strip().startswith(("|", "#", "-")):
                    break
                collected.append(cont)
            return " ".join(s.strip() for s in collected)
    return ""


_VERB_3FORM = re.compile(
    r"links\s+(?P<x>\w+)\s+to\s+(?P<y>\w+)", re.IGNORECASE
)
_VERB_RE = re.compile(
    r"\b(?P<subj>[A-Z]\w+)\b\s+(?P<verb>links to many|has many|has one|belongs to|links)\s+"
    r"(?P<rest>.+)$",
    re.IGNORECASE,
)


def _parse_relationships(
    doc_label: str,
    block_subject: str,
    text: str,
    heading_path: Tuple[str, ...],
    graph: EntityGraph,
    records: List[ExtractionRecord],
) -> None:
    plain = _BOLD_RE.sub(r"\1", text)  # the verbs arrive bolded — strip markers first
    for raw_sentence in re.split(r"[;.]", plain):
        sentence = re.sub(r"^\s*(a|an)\s+", "", raw_sentence.strip(), flags=re.IGNORECASE)
        if not sentence:
            continue
        src = SourceRef(doc_label, heading_path, line=raw_sentence.strip())
        m = _VERB_RE.match(sentence)
        if not m:
            records.append(ExtractionRecord(
                "schema.prisma", f"/relationships/{block_subject}", Status.NOT_EXTRACTED,
                source=src, reason=f"sentence outside the closed verb grammar: {sentence[:80]!r}",
            ))
            continue
        subj = graph.resolve_entity(m.group("subj")) or m.group("subj")
        verb = m.group("verb").lower()
        # Articles appear in object position too ("belongs to a Profile") — strip before resolving.
        rest = re.sub(r"^(?:a|an|the)\s+", "", m.group("rest").strip(), flags=re.IGNORECASE)

        if verb == "links":
            # 3-entity form: "links X to Y" — subject contributes no FK; join(X, Y).
            m3 = _VERB_3FORM.search(f"links {rest}")
            if not m3:
                records.append(ExtractionRecord(
                    "schema.prisma", f"/relationships/{block_subject}", Status.NOT_EXTRACTED,
                    source=src, reason=f"'links' without 'X to Y' form: {sentence[:80]!r}",
                ))
                continue
            x = graph.resolve_entity(m3.group("x"))
            y = graph.resolve_entity(m3.group("y"))
            if not x or not y:
                records.append(ExtractionRecord(
                    "schema.prisma", f"/relationships/{block_subject}", Status.NOT_EXTRACTED,
                    source=src,
                    reason=f"unresolvable entity in 'links X to Y': {m3.group('x')!r}/{m3.group('y')!r}",
                ))
                continue
            _add_join(graph, x, y, src, records)
        elif verb == "links to many":
            obj = graph.resolve_entity(rest.split()[0] if rest else "")
            if not obj:
                records.append(ExtractionRecord(
                    "schema.prisma", f"/relationships/{subj}", Status.NOT_EXTRACTED,
                    source=src, reason=f"unresolvable object entity: {rest[:40]!r}",
                ))
                continue
            _add_join(graph, subj, obj, src, records)  # symmetric restatements dedup inside
        elif verb in ("has many", "has one"):
            obj = graph.resolve_entity(rest.split()[0] if rest else "")
            if not obj:
                records.append(ExtractionRecord(
                    "schema.prisma", f"/relationships/{subj}", Status.NOT_EXTRACTED,
                    source=src, reason=f"unresolvable object entity: {rest[:40]!r}",
                ))
                continue
            graph.fk_parents.setdefault(obj, [])
            if subj not in graph.fk_parents[obj]:
                graph.fk_parents[obj].append(subj)
            records.append(ExtractionRecord(
                "schema.prisma", f"/relationships/{subj}-{verb.replace(' ', '_')}-{obj}",
                Status.EXTRACTED, value=f"{obj}.{_lower_camel(subj)}Id", source=src,
            ))
        elif verb == "belongs to":
            obj = graph.resolve_entity(rest.split()[0] if rest else "")
            if not obj:
                records.append(ExtractionRecord(
                    "schema.prisma", f"/relationships/{subj}", Status.NOT_EXTRACTED,
                    source=src, reason=f"unresolvable parent entity: {rest[:40]!r}",
                ))
                continue
            graph.fk_parents.setdefault(subj, [])
            if obj not in graph.fk_parents[subj]:
                graph.fk_parents[subj].append(obj)
            records.append(ExtractionRecord(
                "schema.prisma", f"/relationships/{subj}-belongs_to-{obj}",
                Status.EXTRACTED, value=f"{subj}.{_lower_camel(obj)}Id", source=src,
            ))


def _add_join(
    graph: EntityGraph, a: str, b: str, src: SourceRef, records: List[ExtractionRecord]
) -> None:
    existing = graph.join_between(a, b)
    if existing:
        # Symmetric restatement — dedup to the first-declared join (one report row only).
        return
    join = JoinModel(name=f"{a}{b}", left=a, right=b)
    graph.joins.append(join)
    records.append(ExtractionRecord(
        "schema.prisma", f"/joins/{join.name}", Status.EXTRACTED,
        value=f"join({a}, {b}) — {join.fk_left}/{join.fk_right}", source=src,
    ))


# --------------------------------------------------------------------------- #
# DIFF mode (FR-WPI-8): doc-derived graph vs the live contract
# --------------------------------------------------------------------------- #

def diff_against_live(graph: EntityGraph, live_schema_text: str) -> List[str]:
    """Drift report: declared entity tables vs the live ``schema.prisma`` (the strtd8 pilot
    path). Returns human-readable drift lines; empty = clean."""
    live: PrismaSchema = parse_prisma_schema(live_schema_text)
    out: List[str] = []
    doc_names = set(graph.entities) | set(graph.join_names)
    live_names = set(live.models)
    for missing in sorted(doc_names - live_names):
        out.append(f"declared in docs, absent from live contract: {missing}")
    for extra in sorted(live_names - doc_names):
        out.append(f"in live contract, not declared in docs: {extra}")
    for name, ent in sorted(graph.entities.items()):
        model = live.model(name)
        if model is None:
            continue
        live_fields = model.field_names
        for f in ent.fields:
            if f.prisma_type is None:
                continue  # already flagged not_extracted (unknown type) — don't double-report
            if f.name not in live_fields:
                out.append(f"{name}.{f.name}: declared in docs, absent from live contract")
    return out
