"""§2.1 Entities pass — entity blocks + the closed relationship grammar (CRP R1).

Runs FIRST (extraction-ordering constraint): downstream extractors need the derived join
models (views ``Shows:`` fks, completeness category words) and the field notes
(``ONLY HUMANS ENTER THIS`` → human_inputs).

FR-WPI-8: both modes now exist. **DIFF mode** (``diff_against_live``) compares the doc-derived graph
against the live contract; **DRAFT mode** (``prisma_emitter.render_prisma_schema`` + the FR-PE-6/7
gate/promotion) *emits* ``schema.prisma`` from the graph. The §2.1 grammar below feeds both.

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
# FR-PE-9: a `enum: <Name>` Type-cell reference to a named enum declared under `## Enums`.
# Matched against the RAW (un-lowercased) cell so the enum name's case survives (entities.py
# lowercases the cell for plain-type / `choice of:` matching, which would destroy the name).
_ENUM_REF_RE = re.compile(r"^enum:\s*(\w+)$", re.IGNORECASE)
_HUMAN_ONLY_RE = re.compile(r"ONLY HUMANS ENTER", re.IGNORECASE)
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
# FR-PE-5(a): a `default: <value>` clause in the Notes cell → @default(<value>).
# G1: the value is a BOUNDED token — stop at `,` `;` `|` AND `(` so a trailing parenthetical
# (e.g. `default: draft (FR-RM-2)`) is not swallowed greedily into the default.
_DEFAULT_RE = re.compile(r"\bdefault:\s*([^,;|(]+)", re.IGNORECASE)


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
    default: Optional[str] = None    # FR-PE-5(a): a `default: X` Notes convention → @default(X)
    is_list: bool = False            # G3: `list of text` → String[] (Column(JSON) downstream)
    # FR-PE-10: the values of an inline `choice of: a|b|c` (was discarded). When set, the emitter
    # synthesizes a `<Entity><Field>` enum block from them. None for plain/named-enum fields.
    enum_values: Optional[Tuple[str, ...]] = None


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
    # FR-PE-8: named enums declared under `## Enums` (name -> ordered values), shared by N fields.
    enums: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    # FR-PE-13: custom reverse-relation names from an `as <name>` clause, keyed (parent, child).
    # Absent ⇒ the emitter falls back to the plural-of-child convention.
    reverse_names: Dict[Tuple[str, str], str] = field(default_factory=dict)
    # FR-PE-5 grammar gaps (slice 3):
    loose_refs: Dict[str, List[str]] = field(default_factory=dict)  # child -> [parent,...] (no FK)
    # G2: loose refs declared optional via `references <Y> (optional)` → emit `String?`. Keyed
    # (child, parent); absent ⇒ required `String` (today's default).
    optional_loose_refs: set = field(default_factory=set)
    indexes: Dict[str, List[Tuple[str, ...]]] = field(default_factory=dict)   # entity -> [@@index]
    uniques: Dict[str, List[Tuple[str, ...]]] = field(default_factory=dict)   # entity -> [@@unique]

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


def extract_enums(
    doc_label: str,
    enum_sections: List[Section],
    records: List[ExtractionRecord],
) -> Dict[str, Tuple[str, ...]]:
    """FR-PE-8: parse the ``### Enum: <Name>`` blocks under ``## Enums`` into name → ordered values.

    Each block's value set is the first non-empty body line, pipe-separated (the same delimiter as
    the inline ``choice of:`` form). The enum name keeps its declared case (used verbatim as the
    Prisma enum type). A block with no parseable values is recorded ``not_extracted``.
    """
    out: Dict[str, Tuple[str, ...]] = {}
    for sec in enum_sections:
        m = re.match(r"^Enum:\s*(\w+)$", sec.title, re.IGNORECASE)
        if not m:
            continue
        name = m.group(1)
        values: Tuple[str, ...] = ()
        for line in sec.body.splitlines():
            stripped = strip_annotations(line)
            if stripped:
                values = tuple(v.strip() for v in stripped.split("|") if v.strip())
                break
        if not values:
            records.append(ExtractionRecord(
                "schema.prisma", f"/enums/{name}", Status.NOT_EXTRACTED,
                source=SourceRef(doc_label, sec.heading_path),
                reason="enum block has no pipe-separated value line",
            ))
            continue
        out[name] = values
        records.append(ExtractionRecord(
            "schema.prisma", f"/enums/{name}", Status.EXTRACTED,
            value=f"{len(values)} values", source=SourceRef(doc_label, sec.heading_path),
        ))
    return out


def extract_entities(
    doc_label: str,
    entity_sections: List[Section],
    records: List[ExtractionRecord],
    known_enums: frozenset = frozenset(),
) -> EntityGraph:
    """Parse the ### blocks under ## Entities into the graph; record per-value traceability.

    *known_enums* — names declared under ``## Enums`` (FR-PE-8), so an ``enum: <Name>`` field
    reference (FR-PE-9) can be validated in this pass. An undeclared reference is ``not_extracted``.
    """
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
            raw_ftype = strip_annotations(row.get("type", ""))   # case preserved for enum refs
            ftype = raw_ftype.lower()                            # lowercased for plain/choice match
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
            enum_values: Optional[Tuple[str, ...]] = None
            is_list = False
            notext_reason = f"type {ftype!r} outside the plain-type vocabulary"
            enum_ref = _ENUM_REF_RE.match(raw_ftype)             # FR-PE-9: named-enum reference
            choice = _CHOICE_RE.match(raw_ftype)                 # FR-PE-10: inline one-off enum
            if ftype in ("list of text", "list of long text"):  # G3: list-of-string → String[]
                prisma_type = "String"
                is_list = True
            elif enum_ref:
                ename = enum_ref.group(1)
                if ename in known_enums:
                    prisma_type = ename                          # share the declared named enum
                else:
                    prisma_type = None
                    notext_reason = f"enum-undeclared: {ename!r} not declared under ## Enums"
            elif choice:
                prisma_type = f"{name}{fname[0].upper()}{fname[1:]}"  # synthesized enum type name
                enum_values = tuple(v.strip() for v in choice.group(1).split("|") if v.strip())
            if prisma_type is None:
                records.append(ExtractionRecord(
                    "schema.prisma", f"/models/{name}/fields/{fname}", Status.NOT_EXTRACTED,
                    source=SourceRef(doc_label, sec.heading_path, row_index=i),
                    reason=notext_reason,
                ))
            dm = _DEFAULT_RE.search(notes)
            fields.append(DocField(
                name=fname, plain_type=ftype, prisma_type=prisma_type,
                required=req, notes=notes,
                human_only=bool(_HUMAN_ONLY_RE.search(notes)),
                row_index=i,
                default=dm.group(1).strip() if dm else None,
                enum_values=enum_values,
                is_list=is_list,
            ))
        graph.entities[name] = DocEntity(name, tuple(fields), sec.heading_path)
        _parse_index_lines(name, sec.body, graph)  # FR-PE-5(b): Indexes:/Unique: per-entity lines
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


def _parse_index_lines(entity: str, body: str, graph: EntityGraph) -> None:
    """FR-PE-5(b): per-entity ``Indexes:`` / ``Unique:`` lines → @@index / compound @@unique.

    ``Indexes: jobDescriptionId; jobDescriptionId, kind`` → two indexes (semicolon-separated specs,
    each a comma-separated column list). ``Unique: a, b, c`` → one compound unique.
    """
    for line in body.splitlines():
        s = line.strip()
        for label, dst in (("Indexes:", graph.indexes), ("Unique:", graph.uniques)):
            if s.lower().startswith(label.lower()):
                specs = [
                    tuple(c.strip() for c in grp.split(",") if c.strip())
                    for grp in s[len(label):].split(";")
                ]
                specs = [c for c in specs if c]
                if specs:
                    dst.setdefault(entity, []).extend(specs)


def _relationship_paragraph(body: str) -> str:
    """The text of the ``Relationships:`` paragraph(s), joined across wrapped lines.

    Multiple ``Relationships:`` lines are each collected (prefix stripped) — a SECOND such line is a
    new declaration, not a continuation of the first (which would silently swallow it, dropping the
    relationship; the workaround was to ``;``-join them onto one line)."""
    collected: List[str] = []
    in_block = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("Relationships:"):
            collected.append(line.split(":", 1)[1])     # new declaration line — strip the prefix
            in_block = True
        elif in_block:
            if not s or s.startswith(("|", "#", "-")):
                in_block = False                          # the block ends; later lines may re-open it
            else:
                collected.append(line)                    # wrapped continuation of the current line
    return " ".join(s.strip() for s in collected)


_VERB_3FORM = re.compile(
    r"links\s+(?P<x>\w+)\s+to\s+(?P<y>\w+)", re.IGNORECASE
)
# FR-PE-13: an optional trailing `as <name>` clause naming the reverse-relation list field.
_AS_RE = re.compile(r"\bas\s+(?P<name>\w+)\s*$", re.IGNORECASE)


def _split_as_clause(rest: str) -> Tuple[str, Optional[str]]:
    """Strip a trailing ``as <name>`` from a relationship object phrase; return (rest, name)."""
    m = _AS_RE.search(rest)
    if not m:
        return rest, None
    return rest[: m.start()].strip(), m.group("name")
_VERB_RE = re.compile(
    r"\b(?P<subj>[A-Z]\w+)\b\s+"
    r"(?P<verb>links to many|has many|has one|belongs to|references|links)\s+"
    r"(?P<rest>.+)$",
    re.IGNORECASE,
)


def _resolve_object(
    graph: EntityGraph, rest: str, records: List[ExtractionRecord], subj: str,
    src: SourceRef, noun: str,
) -> Optional[str]:
    """Resolve a relationship sentence's object entity (the first word of *rest*); record a
    ``not_extracted`` and return ``None`` if it doesn't resolve (M3 — shared by the verb branches)."""
    obj = graph.resolve_entity(rest.split()[0] if rest else "")
    if not obj:
        records.append(ExtractionRecord(
            "schema.prisma", f"/relationships/{subj}", Status.NOT_EXTRACTED,
            source=src, reason=f"unresolvable {noun}: {rest[:40]!r}",
        ))
    return obj


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
        # L1: a subject that doesn't resolve to a declared entity is a typo, not a phantom entity —
        # flag it (the old `or m.group("subj")` fallback silently dropped the relationship).
        subj = graph.resolve_entity(m.group("subj"))
        if subj is None:
            records.append(ExtractionRecord(
                "schema.prisma", f"/relationships/{block_subject}", Status.NOT_EXTRACTED,
                source=src, reason=f"unresolvable relationship subject: {m.group('subj')!r}",
            ))
            continue
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
            rest, rev_name = _split_as_clause(rest)   # L2: `as <name>` works on joins too, not just FK
            obj = _resolve_object(graph, rest, records, subj, src, "object entity")
            if not obj:
                continue
            _add_join(graph, subj, obj, src, records)  # symmetric restatements dedup inside
            if rev_name:                               # name subj's reverse-list to obj (via the join)
                graph.reverse_names[(subj, obj)] = rev_name
        elif verb in ("has many", "has one"):
            rest, rev_name = _split_as_clause(rest)   # FR-PE-13: optional `as <name>`
            obj = _resolve_object(graph, rest, records, subj, src, "object entity")
            if not obj:
                continue
            graph.fk_parents.setdefault(obj, [])
            if subj not in graph.fk_parents[obj]:
                graph.fk_parents[obj].append(subj)
            if rev_name:                              # parent=subj, child=obj
                graph.reverse_names[(subj, obj)] = rev_name
            records.append(ExtractionRecord(
                "schema.prisma", f"/relationships/{subj}-{verb.replace(' ', '_')}-{obj}",
                Status.EXTRACTED, value=f"{obj}.{_lower_camel(subj)}Id", source=src,
            ))
        elif verb == "belongs to":
            rest, rev_name = _split_as_clause(rest)   # FR-PE-13: optional `as <name>`
            obj = _resolve_object(graph, rest, records, subj, src, "parent entity")
            if not obj:
                continue
            graph.fk_parents.setdefault(subj, [])
            if obj not in graph.fk_parents[subj]:
                graph.fk_parents[subj].append(obj)
            if rev_name:                              # parent=obj, child=subj
                graph.reverse_names[(obj, subj)] = rev_name
            records.append(ExtractionRecord(
                "schema.prisma", f"/relationships/{subj}-belongs_to-{obj}",
                Status.EXTRACTED, value=f"{subj}.{_lower_camel(obj)}Id", source=src,
            ))
        elif verb == "references":
            # FR-PE-5(c) / OQ-PE-3: a LOOSE reference — a `<parent>Id` scalar with NO @relation and
            # no reverse list (the polymorphic / cross-aggregate link the live contract uses).
            obj = _resolve_object(graph, rest, records, subj, src, "referenced entity")
            if not obj:
                continue
            graph.loose_refs.setdefault(subj, [])
            if obj not in graph.loose_refs[subj]:
                graph.loose_refs[subj].append(obj)
            if re.search(r"\boptional\b", rest, re.IGNORECASE):   # G2: `references Y (optional)` → String?
                graph.optional_loose_refs.add((subj, obj))
            opt = " optional" if (subj, obj) in graph.optional_loose_refs else ""
            records.append(ExtractionRecord(
                "schema.prisma", f"/relationships/{subj}-references-{obj}",
                Status.EXTRACTED,
                value=f"{subj}.{_lower_camel(obj)}Id (loose, no FK{opt})", source=src,
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
