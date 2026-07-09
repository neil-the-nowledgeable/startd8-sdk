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
from .models import ADVISORY_PREFIX, ExtractionRecord, SourceRef, Status

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
                # F1/F8: a `choice of:` that yields exactly ONE value is suspicious — most often an
                # unescaped `|` split `choice of: a|b|c` across table columns upstream in md_tables,
                # silently truncating the enum to its first value (portal-rebuild F1; `kickoff check`
                # reported "docs conform"). Flag it as advisory (warn; --strict fails). FR-F1e: the
                # raw row is wider than the header when the split happened — that ragged-row evidence
                # distinguishes a truncation from a genuine single-member vocabulary.
                if len(enum_values) == 1:
                    over_wide = len(tables[0].rows[i]) > len(tables[0].headers)
                    why = (
                        "an unescaped `|` split the `choice of:` across table columns "
                        "(escape literal pipes as `\\|`, e.g. `choice of: a\\|b\\|c`)"
                        if over_wide
                        else "a single-member `choice of:` (use a plain type if it is not an enum)"
                    )
                    records.append(ExtractionRecord(
                        "schema.prisma", f"/models/{name}/fields/{fname}", Status.EXTRACTED,
                        value=enum_values[0],
                        source=SourceRef(doc_label, sec.heading_path, row_index=i),
                        reason=(
                            f"{ADVISORY_PREFIX}choice-of-single-value: {name}.{fname} extracted a "
                            f"single enum value {enum_values[0]!r} from a `choice of:` type — "
                            f"likely {why}"
                        ),
                    ))
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
            # F3 (FR-F3-iii, flag-only default landing): `has one` is currently emitted IDENTICALLY
            # to `has many` — a one-to-many with a non-unique child FK (portal-rebuild F3). True
            # one-to-one (singular relation + @unique on the child FK) is gated on the migration-
            # safety precondition (FR-F3-iv) and unresolved forks, so rather than silently emit
            # has-many we FLAG it as advisory: the output is unchanged but the author is told the
            # one-to-one intent is not enforced (the app must treat it as at-most-one).
            if verb == "has one":
                records.append(ExtractionRecord(
                    "schema.prisma", f"/relationships/{subj}-has_one-{obj}#cardinality",
                    Status.EXTRACTED, value=f"{obj}.{_lower_camel(subj)}Id", source=src,
                    reason=(
                        f"{ADVISORY_PREFIX}has-one-unsupported: '{subj} has one {obj}' is emitted as "
                        f"one-to-many ({obj}.{_lower_camel(subj)}Id is NOT @unique) — true one-to-one "
                        f"is not yet enforced. Treat as at-most-one, or add a `Unique:` line on "
                        f"{obj}.{_lower_camel(subj)}Id to enforce it at the DB."
                    ),
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


# --------------------------------------------------------------------------- #
# FR-CFE: build the EntityGraph FROM an authored contract (the reverse of the emitter).
# Contract-first projects author `prisma/schema.prisma` as the single source of truth and have no
# prose `## Entities` section — so the assembly extractors (views/completeness/imports) had nothing
# to resolve references against. This reconstructs the resolution-supporting half of the graph
# (entities/fields/enums/fk_parents/joins) from a parsed schema; `resolve_entity`/`join_between` then
# work identically to a prose-derived graph. Emission-only attributes (loose_refs / reverse_names /
# indexes / uniques) are NOT reconstructed — in contract-first mode the schema already exists, so the
# entities pass runs in DIFF mode and never re-emits.
# --------------------------------------------------------------------------- #

_PRISMA_TO_PLAIN = {
    "String": "text", "Int": "number", "Float": "decimal",
    "DateTime": "date", "Boolean": "yes/no",
}
_DEFAULT_ATTR_RE = re.compile(r"@default\((.*)\)")
_FK_FIELDS_RE = re.compile(r"fields:\s*\[([^\]]+)\]")


def _owns_fk(f) -> bool:
    """True for the FK-OWNING side of a relation (the child): a non-list object relation whose
    ``@relation`` names the scalar FK column(s). The reverse list (``Type[]``) and a bare 1:1 back-ref
    (no ``fields:``) are excluded — only the side that actually holds the foreign key."""
    return (
        f.has_relation_attr and not f.is_list
        and any(a.startswith("@relation(") and "fields:" in a for a in f.attributes)
    )


def _fk_columns(f) -> Tuple[str, ...]:
    for a in f.attributes:
        m = _FK_FIELDS_RE.search(a)
        if m:
            return tuple(c.strip() for c in m.group(1).split(",") if c.strip())
    return ()


def _field_default(f) -> Optional[str]:
    for a in f.attributes:
        m = _DEFAULT_ATTR_RE.match(a)
        if m:
            return m.group(1)
    return None


def graph_from_prisma(schema: PrismaSchema, *, doc_label: str = "<contract>") -> EntityGraph:
    """Reconstruct an :class:`EntityGraph` from a parsed ``schema.prisma`` (FR-CFE-1).

    Classifies each model as an entity or an explicit **M2M join** (exactly two FK-owning relations +
    a compound ``@@unique``/``@@id`` over those FK columns); populates ``entities`` (with ``DocField``s
    for every scalar column), ``enums``, ``fk_parents`` (1:N), and ``joins`` (M2M). Implicit Prisma
    many-to-many (no explicit join model) is out of scope (v1) — such pairs simply won't resolve a
    ``Shows:`` arrow (a flag, never a crash). Project-agnostic (FR-CFE-5)."""
    graph = EntityGraph()
    graph.enums.update(schema.enums)

    # First classify the explicit join tables so they are excluded from `entities` and the FK pass.
    joins: Dict[str, Tuple[str, str]] = {}
    for name, model in schema.models.items():
        owning = [f for f in model.fields if _owns_fk(f)]
        if len(owning) != 2:
            continue
        cols: set = set()
        for f in owning:
            cols.update(_fk_columns(f))
        if len(cols) >= 2 and any(set(ck) == cols for ck in model.compound_unique_keys):
            joins[name] = (owning[0].type, owning[1].type)
    for name, (left, right) in joins.items():
        graph.joins.append(JoinModel(name=name, left=left, right=right))

    for name, model in schema.models.items():
        if name in joins:
            continue
        fields: List[DocField] = []
        for i, f in enumerate(schema.scalar_fields(name)):
            enum_vals = schema.enums.get(f.type)
            fields.append(DocField(
                name=f.name,
                plain_type=_PRISMA_TO_PLAIN.get(f.type, f.type),
                prisma_type=f.type,
                required=not f.is_optional,
                notes="",
                human_only=False,
                row_index=i,
                default=_field_default(f),
                is_list=f.is_list,
                enum_values=enum_vals,
            ))
        graph.entities[name] = DocEntity(
            name=name, fields=tuple(fields), heading_path=(doc_label, name)
        )
        # fk_parents: each FK-owning relation on this (non-join) entity points to its parent.
        for f in model.fields:
            if _owns_fk(f) and f.type in schema.models and f.type not in joins:
                dst = graph.fk_parents.setdefault(name, [])
                if f.type not in dst:
                    dst.append(f.type)
    return graph


def merge_contract_graph(graph: EntityGraph, contract: EntityGraph) -> None:
    """Merge a contract-derived *contract* graph into the (prose-derived) *graph* in place (FR-CFE-2).

    **Prose wins**: an entity/enum/join already present from prose is left untouched, so a prose-only
    project is byte-identical and the contract only FILLS the entities the prose lacks. Additive across
    every resolution attribute (entities, enums, fk_parents, joins)."""
    for name, ent in contract.entities.items():
        graph.entities.setdefault(name, ent)
    for name, vals in contract.enums.items():
        graph.enums.setdefault(name, vals)
    for child, parents in contract.fk_parents.items():
        dst = graph.fk_parents.setdefault(child, [])
        for p in parents:
            if p not in dst:
                dst.append(p)
    for j in contract.joins:
        if graph.join_between(j.left, j.right) is None:
            graph.joins.append(j)
