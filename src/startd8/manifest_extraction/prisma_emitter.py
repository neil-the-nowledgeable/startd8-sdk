"""§2.1 Prisma emitter (DRAFT mode) — render an :class:`EntityGraph` back out as ``schema.prisma``.

The DRAFT half of FR-WPI-8: the *writer* that makes ``schema.prisma`` a **derived** artifact
(the DIFF half is ``entities.diff_against_live``). What it emits:

- **Models** (FR-PE-1/2/3): one ``model`` per entity + per join, the verbatim datasource/generator
  header, the six bookkeeping fields on every model, and relationships by convention from
  ``graph.joins`` + ``graph.fk_parents`` (join FK scalars + ``@relation(onDelete: Cascade)`` +
  compound ``@@unique``; reverse-relation lists; ``belongs to``/``has`` parent FKs; ``as <name>``
  reverse-name overrides, FR-PE-13).
- **Grammar gaps** (FR-PE-5): non-bookkeeping ``@default`` (G1, String quoted); explicit ``@@index``
  / compound ``@@unique`` (column-validated, H3); loose ``references`` scalars (G2 optional variant).
- **Enums** (FR-PE-8/10/11): ``## Enums`` named enums + inline ``choice of:``, emitted as ``enum``
  blocks and parity-checked.
- **Scalar lists** (G3): ``list of text`` → ``String[]`` (a SDK ``Column(JSON)`` convention —
  surfaced as a warning since it is not valid Prisma on the SQLite datasource).

**Gate & fail-loud discipline.** ``render_prisma_schema`` returns ``errors`` (structural: duplicate
field / pluralization collision / bad ``@@index`` column — these block), ``unrenderable`` (a
declared field the contract can't express — dropped, blocks ``--promote`` unless ``--allow-lossy``),
``warnings`` (advisory, never block), and ``field_names``/``enum_names`` (the round-trip oracle —
``emit_schema_draft`` verifies models AND enums AND fields survive re-parse, not just model names).
Nothing is ever emitted wrong: the bad construct is suppressed and the gate refuses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import re

from ..backend_codegen._headers import header_emitted_contract
from ..frontend_codegen.schema_renderer import schema_sha256
from ..languages.prisma_parser import PrismaField, PrismaModel, parse_prisma_schema
from .entities import DocEntity, EntityGraph, JoinModel, _lower_camel

# The datasource/generator block — verbatim from the live strtd8 contract (FR-PE-1). SQLite, the
# locked target (no native JSON/enum reliance); url from the DATABASE_URL env var.
_PRISMA_PREAMBLE = (
    "generator client {\n"
    '  provider = "prisma-client-js"\n'
    "}\n\n"
    "datasource db {\n"
    '  provider = "sqlite"\n'
    '  url      = env("DATABASE_URL")\n'
    "}"
)

# The six implicit bookkeeping fields (FR-PE-2) — never sourced from the doc tables, identical on
# every model. Order + attributes match the live contract exactly.
_BOOKKEEPING: Tuple[Tuple[str, str], ...] = (
    ("id", "String   @id @default(cuid())"),
    ("ownerId", "String   @default(\"local\")"),
    ("source", "String   @default(\"user\")"),
    ("confirmed", "Boolean  @default(true)"),
    ("createdAt", "DateTime @default(now())"),
    ("updatedAt", "DateTime @updatedAt"),
)


def reserved_field_names() -> Tuple[str, ...]:
    """The implicit bookkeeping field names the emitter injects on every model.

    A **public, supported accessor** (R1-S7) over the private ``_BOOKKEEPING`` set —
    ``id/ownerId/source/confirmed/createdAt/updatedAt``. Inference-side collision guards
    (TSDB maturation FR-11) read this instead of importing the private constant, so the guard
    has a stable contract and cannot silently break if the bookkeeping set is refactored. A
    contract test pins this accessor to the emitter's actual injection set.
    """
    return tuple(name for name, _ in _BOOKKEEPING)


@dataclass(frozen=True)
class UnrenderableField:
    """A field flagged out (type outside the plain-type vocabulary) — never emitted wrong."""

    entity: str
    field: str
    reason: str


@dataclass(frozen=True)
class PrismaSchemaResult:
    text: str
    schema_sha256: str
    models_rendered: int
    unrenderable: Tuple[UnrenderableField, ...]
    warnings: Tuple[str, ...] = ()    # OQ-PE-7: advisory (e.g. enum default not a member) — never blocks
    errors: Tuple[str, ...] = ()      # structural fail-loud (duplicate field, bad @@index column) — block
    field_names: Dict[str, Tuple[str, ...]] = field(default_factory=dict)  # per-model emitted fields
    enum_names: Tuple[str, ...] = ()  # emitted enum block names (the round-trip oracle, C2)


def _emit_field(
    lines: List[str], seen: List[str], errors: List[str], model: str, name: str, body: str
) -> None:
    """Append a field line + record its name (the field-level round-trip oracle, C2).

    A duplicate name is a structural error (a relationship/plural collision) — recorded and the
    duplicate suppressed, never an invalid duplicate-field schema (H1, populated at the High level).
    """
    if name in seen:
        errors.append(
            f"{model}.{name}: duplicate field (relationship/pluralization collision); suppressed"
        )
        return
    seen.append(name)
    lines.append(_field_line(name, body))


def _quote_string_default(value: str) -> str:
    """Quote a ``String`` ``@default`` (Prisma rejects a bare word), escaping ``\\`` and ``"`` so a
    default containing a quote/backslash stays valid (M5)."""
    inner = value.strip().strip('"').strip("'")
    inner = inner.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + inner + '"'


def _emit_block_attrs(
    model: str, lines: List[str], seen: List[str], errors: List[str], graph: "EntityGraph"
) -> None:
    """Emit ``@@unique`` / ``@@index`` (FR-PE-5b), FAILING LOUDLY (H3) on a column that is not a
    declared field on the model — a typo would otherwise emit a schema invalid at ``prisma validate``
    that the lenient round-trip wouldn't catch. The offending constraint is suppressed."""
    declared = set(seen)
    for kind, specs in (("@@unique", graph.uniques.get(model, [])),
                        ("@@index", graph.indexes.get(model, []))):
        for cols in specs:
            missing = [c for c in cols if c not in declared]
            if missing:
                errors.append(
                    f"{model}: {kind} references undeclared column(s) {sorted(missing)} "
                    "(typo?); constraint suppressed"
                )
                continue
            lines.append(f"  {kind}([{', '.join(cols)}])")


_SIBILANT_SUFFIXES = ("s", "ss", "x", "z", "ch", "sh")


def _plural(name: str) -> str:
    """A reverse-relation list field name: lowerCamel plural with English edge cases (H1).

    sibilant ending (``-s``/``-ss``/``-x``/``-z``/``-ch``/``-sh``) → ``+es``; a **consonant**+``-y``
    → ``-ies``; a **vowel**+``-y`` → ``+s``; otherwise ``+s``. (``Address`` → ``addresses``,
    ``Box`` → ``boxes``, ``Match`` → ``matches``, ``Day`` → ``days``, ``Capability`` →
    ``capabilities``.) A residual same-name collision on one model is caught by ``_emit_field``.
    """
    base = _lower_camel(name)
    low = base.lower()
    if low.endswith(_SIBILANT_SUFFIXES):
        return base + "es"
    if low.endswith("y") and len(base) >= 2 and base[-2].lower() not in "aeiou":
        return base[:-1] + "ies"
    return base + "s"


def _relation_attr(fk: str) -> str:
    return f"@relation(fields: [{fk}], references: [id], onDelete: Cascade)"


def _field_line(name: str, body: str) -> str:
    return f"  {name} {body}"


def _model_block(name: str, lines: List[str]) -> str:
    return f"model {name} {{\n" + "\n".join(lines) + "\n}"


def _enum_block(name: str, values: Tuple[str, ...]) -> str:
    return f"enum {name} {{\n" + "\n".join(f"  {v}" for v in values) + "\n}"


def _collect_enum_blocks(
    graph: EntityGraph, unrenderable: List[UnrenderableField]
) -> Tuple[List[str], Tuple[str, ...]]:
    """FR-PE-10: render every enum block — named enums (``graph.enums``) and per-field inline
    ``choice of:`` enums (``DocField.enum_values``) — before the model blocks, in stable order.
    Returns ``(blocks, emitted_enum_names)``; the names feed the C2 round-trip oracle.

    A synthesized ``<Entity><Field>`` name colliding with a declared ``## Enums`` name is flagged
    (OQ-PE-8), never silently merged.
    """
    blocks: List[str] = []
    names: List[str] = []
    for name in sorted(graph.enums):                       # named enums: alpha, stable
        blocks.append(_enum_block(name, graph.enums[name]))
        names.append(name)
    for ent_name, ent in graph.entities.items():           # per-field: entity/field decl order
        for f in ent.fields:
            if f.enum_values is None or f.prisma_type is None:
                continue
            if f.prisma_type in graph.enums:
                unrenderable.append(UnrenderableField(
                    ent_name, f.name,
                    f"enum-name-collision: synthesized {f.prisma_type!r} clashes with a named enum",
                ))
                continue
            blocks.append(_enum_block(f.prisma_type, f.enum_values))
            names.append(f.prisma_type)
    return blocks, tuple(names)


def _emit_bookkeeping(lines: List[str], seen: List[str], errors: List[str], model: str) -> None:
    """Inject the six bookkeeping fields (FR-PE-2) + the readability gap (M3 — shared by both loops)."""
    for fn, body in _BOOKKEEPING:
        _emit_field(lines, seen, errors, model, fn, body)
    lines.append("")


def _render_entity_model(
    graph: EntityGraph, name: str, ent: DocEntity,
    fk_blocks: Dict[str, List[Tuple[str, str]]], rev_lists: Dict[str, List[Tuple[str, str]]],
    *, unrenderable: List[UnrenderableField], warnings: List[str], errors: List[str],
    list_fields: List[str], field_names: Dict[str, Tuple[str, ...]],
) -> str:
    """Render one entity ``model`` block, populating the shared accumulators (M1 decomposition)."""
    lines: List[str] = []
    seen: List[str] = []
    _emit_bookkeeping(lines, seen, errors, name)
    for f in ent.fields:
        if f.prisma_type is None:
            unrenderable.append(UnrenderableField(name, f.name, "type outside plain-type vocabulary"))
            continue
        if f.is_list:              # G3: list-of-scalar → String[] @default([]) (Column(JSON))
            _emit_field(lines, seen, errors, name, f.name, f"{f.prisma_type}[] @default([])")
            list_fields.append(f"{name}.{f.name}")
            continue
        if f.default is not None:  # FR-PE-5(a): a defaulted scalar is non-optional
            dv = _quote_string_default(f.default) if f.prisma_type == "String" else f.default
            # OQ-PE-7: flag (don't block) an enum default that isn't a value of its enum.
            enum_vals = graph.enums.get(f.prisma_type)
            if enum_vals is None:
                enum_vals = f.enum_values
            if enum_vals is not None and f.default not in enum_vals:
                warnings.append(
                    f"{name}.{f.name}: default {f.default!r} is not a value of enum "
                    f"{f.prisma_type} {list(enum_vals)}"
                )
            _emit_field(lines, seen, errors, name, f.name, f"{f.prisma_type} @default({dv})")
        else:
            opt = "" if f.required else "?"
            _emit_field(lines, seen, errors, name, f.name, f"{f.prisma_type}{opt}")
    for parent in graph.loose_refs.get(name, []):   # FR-PE-5(c): loose ref — scalar, no @relation
        opt = "?" if (name, parent) in graph.optional_loose_refs else ""  # G2: optional variant
        _emit_field(lines, seen, errors, name, f"{_lower_camel(parent)}Id", f"String{opt}")
    for fk, body in fk_blocks.get(name, []):
        _emit_field(lines, seen, errors, name, fk, body)
    for lf, body in rev_lists.get(name, []):
        _emit_field(lines, seen, errors, name, lf, body)
    _emit_block_attrs(name, lines, seen, errors, graph)   # FR-PE-5(b) + H3 column validation
    field_names[name] = tuple(seen)
    return _model_block(name, lines)


def _render_join_model(
    j: JoinModel, *, errors: List[str], field_names: Dict[str, Tuple[str, ...]]
) -> str:
    """Render one M2M join ``model`` block (FR-PE-3): bookkeeping + 2 FK + 2 relation objects +
    compound ``@@unique`` (M1 decomposition)."""
    lines: List[str] = []
    seen: List[str] = []
    _emit_bookkeeping(lines, seen, errors, j.name)
    _emit_field(lines, seen, errors, j.name, j.fk_left, "String")
    _emit_field(lines, seen, errors, j.name, j.fk_right, "String")
    _emit_field(lines, seen, errors, j.name, _lower_camel(j.left),
                f"{j.left} {_relation_attr(j.fk_left)}")
    _emit_field(lines, seen, errors, j.name, _lower_camel(j.right),
                f"{j.right} {_relation_attr(j.fk_right)}")
    lines.append(f"  @@unique([{j.fk_left}, {j.fk_right}])")
    field_names[j.name] = tuple(seen)
    return _model_block(j.name, lines)


def render_prisma_schema(
    graph: EntityGraph, source_file: str = "prisma/schema.prisma"
) -> PrismaSchemaResult:
    """Render ``schema.prisma`` from the doc-derived :class:`EntityGraph` (FR-PE-1/2/3, $0)."""
    unrenderable: List[UnrenderableField] = []
    warnings: List[str] = []
    errors: List[str] = []
    field_names: Dict[str, Tuple[str, ...]] = {}
    list_fields: List[str] = []     # H2: scalar-list fields (String[]) — a SQLite-portability caveat

    # --- precompute relationship-derived members keyed by entity name (FR-PE-3) -----------------
    rev_lists: Dict[str, List[Tuple[str, str]]] = {n: [] for n in graph.entities}
    fk_blocks: Dict[str, List[Tuple[str, str]]] = {n: [] for n in graph.entities}

    # belongs-to / has: child carries `<parent>Id` + a relation object; parent gets a reverse list.
    for child, parents in graph.fk_parents.items():
        for parent in parents:
            fk = f"{_lower_camel(parent)}Id"
            fk_blocks.setdefault(child, []).append((fk, "String"))
            fk_blocks[child].append((_lower_camel(parent), f"{parent} {_relation_attr(fk)}"))
            # FR-PE-13: a custom `as <name>` reverse-relation name wins over the plural convention.
            rev_name = graph.reverse_names.get((parent, child), _plural(child))
            rev_lists.setdefault(parent, []).append((rev_name, f"{child}[]"))

    # M2M join: each side gets a reverse list typed by the join model. L2: an `as <name>` override
    # (graph.reverse_names) wins over the plural convention on either side, like the FK case.
    for j in graph.joins:
        left_name = graph.reverse_names.get((j.left, j.right), _plural(j.right))
        right_name = graph.reverse_names.get((j.right, j.left), _plural(j.left))
        rev_lists.setdefault(j.left, []).append((left_name, f"{j.name}[]"))
        rev_lists.setdefault(j.right, []).append((right_name, f"{j.name}[]"))

    # --- enum blocks (FR-PE-10): named + per-field inline, before the models -------------------
    blocks, enum_names = _collect_enum_blocks(graph, unrenderable)

    # --- models (M1: per-model rendering lives in _render_entity_model / _render_join_model) ----
    for name, ent in graph.entities.items():
        blocks.append(_render_entity_model(
            graph, name, ent, fk_blocks, rev_lists,
            unrenderable=unrenderable, warnings=warnings, errors=errors,
            list_fields=list_fields, field_names=field_names,
        ))
    for j in graph.joins:
        blocks.append(_render_join_model(j, errors=errors, field_names=field_names))

    # H2: scalar lists are a deliberate SDK convention (String[] → Column(JSON) downstream), but
    # they are NOT valid Prisma on the locked SQLite datasource. The SDK pipeline tolerates it (its
    # own lenient parser + renderers), yet `prisma validate` (languages/prisma.py) would reject it —
    # so surface the portability caveat instead of letting it pass silently.
    if list_fields:
        warnings.append(
            f"scalar-list field(s) {list_fields} emit `String[]`, a SDK JSON-column convention that "
            "is NOT valid Prisma on the SQLite datasource (won't pass `prisma validate`)"
        )

    body = _PRISMA_PREAMBLE + "\n\n" + "\n\n".join(blocks) + "\n"
    sha = schema_sha256(body)
    header = header_emitted_contract(source_file, sha)
    text = header + "\n\n" + body
    return PrismaSchemaResult(
        text=text,
        schema_sha256=sha,
        models_rendered=len(graph.entities) + len(graph.joins),
        unrenderable=tuple(unrenderable),
        warnings=tuple(warnings),
        errors=tuple(errors),
        field_names=field_names,
        enum_names=enum_names,
    )


# --------------------------------------------------------------------------- #
# FR-PE-4 — semantic parity diff (the flip-gate oracle). Compares two *parsed*  #
# schemas field-by-field and block-by-block, not just model/field presence.     #
# --------------------------------------------------------------------------- #

def _norm_attr(a: str) -> str:
    """Normalize an attribute for comparison (collapse internal whitespace)."""
    return re.sub(r"\s+", "", a)


def _type_sig(f: PrismaField) -> str:
    """A field's full type signature: base + list + optional (e.g. ``String?``, ``Outcome[]``)."""
    return f"{f.type}{'[]' if f.is_list else ''}{'?' if f.is_optional else ''}"


def _attr_set(f: PrismaField) -> frozenset:
    return frozenset(_norm_attr(a) for a in f.attributes)


def _block_set(m: PrismaModel) -> frozenset:
    return frozenset(_norm_attr(a) for a in m.block_attributes)


def semantic_diff(emitted_text: str, live_text: str) -> List[str]:
    """Semantic-parity drift between an *emitted* schema (left) and the *live* contract (right).

    Per field: base type, optionality, list-ness, and the normalized attribute set
    (``@id``/``@unique``/``@default(…)``/``@relation(…)``/``@updatedAt``). Per model: the block
    attributes (``@@id``/``@@unique``/``@@index``). Every divergence is one stable-keyed line
    (sorted); an empty list is parity. FR-PE-4 / FR-PE-6.
    """
    left = parse_prisma_schema(emitted_text)
    right = parse_prisma_schema(live_text)
    out: List[str] = []

    for missing in sorted(set(left.models) - set(right.models)):
        out.append(f"model {missing}: emitted, absent from live")
    for extra in sorted(set(right.models) - set(left.models)):
        out.append(f"model {extra}: in live, not emitted")

    # FR-PE-11: enum-block parity — presence + ordered value set (the parser exposes both).
    for missing in sorted(set(left.enums) - set(right.enums)):
        out.append(f"enum {missing}: emitted, absent from live")
    for extra in sorted(set(right.enums) - set(left.enums)):
        out.append(f"enum {extra}: in live, not emitted")
    for name in sorted(set(left.enums) & set(right.enums)):
        # L3: compare the value *set* — a reorder of the same values is not a semantic change and
        # must not flag false parity drift (which would needlessly block a flip).
        if set(left.enums[name]) != set(right.enums[name]):
            out.append(
                f"enum {name}: values {sorted(left.enums[name])} (emitted) "
                f"vs {sorted(right.enums[name])} (live)"
            )

    for name in sorted(set(left.models) & set(right.models)):
        lm, rm = left.models[name], right.models[name]
        lf, rf = {f.name: f for f in lm.fields}, {f.name: f for f in rm.fields}
        for fn in sorted(set(lf) - set(rf)):
            out.append(f"{name}.{fn}: emitted, absent from live")
        for fn in sorted(set(rf) - set(lf)):
            out.append(f"{name}.{fn}: in live, not emitted")
        for fn in sorted(set(lf) & set(rf)):
            le, ri = lf[fn], rf[fn]
            if _type_sig(le) != _type_sig(ri):
                out.append(f"{name}.{fn}: type {_type_sig(le)} (emitted) vs {_type_sig(ri)} (live)")
            la, ra = _attr_set(le), _attr_set(ri)
            for a in sorted(la - ra):
                out.append(f"{name}.{fn}: attr {a} emitted, absent from live")
            for a in sorted(ra - la):
                out.append(f"{name}.{fn}: attr {a} in live, not emitted")
        lb, rb = _block_set(lm), _block_set(rm)
        for a in sorted(lb - rb):
            out.append(f"{name}: block-attr {a} emitted, absent from live")
        for a in sorted(rb - lb):
            out.append(f"{name}: block-attr {a} in live, not emitted")
    return out


def parity_against_live(graph: EntityGraph, live_text: str) -> List[str]:
    """Emit *graph* and report its semantic-parity drift against the live contract (FR-PE-6 gate)."""
    return semantic_diff(render_prisma_schema(graph).text, live_text)


# --------------------------------------------------------------------------- #
# FR-PE-6 — round-trip-before-write + whole-schema parity gate.                 #
# FR-PE-7 — run-dir emission + human-gated promotion ratchet.                   #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class EmitGateResult:
    """Outcome of the emit gate. ``ok`` ⇒ safe to promote."""

    ok: bool
    round_trips: bool                 # FR-PE-6/C2: text parses back to the same models + enums + fields
    parity_drift: Tuple[str, ...]     # FR-PE-4 drift vs live (empty ⇒ parity); () when no live given
    models: int
    unrenderable: Tuple[UnrenderableField, ...]
    draft_path: Optional[str]         # where the draft was written (run dir), or None if gate failed
    errors: Tuple[str, ...] = ()      # C1/H1/H3: structural fail-loud (block)
    warnings: Tuple[str, ...] = ()    # H4: advisory (surface, never block)


def emit_schema_draft(
    graph: EntityGraph,
    run_dir: str,
    *,
    live_text: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> EmitGateResult:
    """Emit to the RUN DIR only (never the project tree — FR-PE-7), behind the FR-PE-6 gate.

    Round-trip-before-write: the draft is written only if it parses back to the full model set.
    When *live_text* is given, parity drift is computed (the cutover gate); ``ok`` additionally
    requires zero drift. The promoted contract path is reached only via :func:`promote_schema`.
    """
    res = render_prisma_schema(graph, source_file)
    parsed = parse_prisma_schema(res.text)
    expected = set(graph.entities) | {j.name for j in graph.joins}
    # C2: round-trip is model-set AND enum-set AND per-model field-set — not just model names. A
    # field/enum the lenient parser silently dropped (a malformed line) now fails the gate.
    round_trips = (
        set(parsed.models) == expected
        and set(res.enum_names) <= set(parsed.enums)
        and all(
            parsed.model(m) is not None and set(fns) <= parsed.model(m).field_names
            for m, fns in res.field_names.items()
        )
    )
    drift = tuple(semantic_diff(res.text, live_text)) if live_text is not None else ()

    draft_path: Optional[str] = None
    # FR-PE-6/C1: never write a draft that doesn't round-trip or carries a structural error.
    if round_trips and not res.errors:
        draft = Path(run_dir) / "schema.prisma"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(res.text, encoding="utf-8")
        draft_path = str(draft)

    # C1: `ok` (safe to promote) also requires no structural errors and no DROPPED fields
    # (unrenderable = the author declared a field the contract can't express → not safe to flip).
    ok = (
        round_trips
        and not res.errors
        and not res.unrenderable
        and (live_text is None or not drift)
    )
    return EmitGateResult(
        ok=ok, round_trips=round_trips, parity_drift=drift, models=res.models_rendered,
        unrenderable=res.unrenderable, draft_path=draft_path,
        errors=res.errors, warnings=res.warnings,
    )


def promote_schema(run_dir: str, project_path: str, *, archive: bool = True) -> str:
    """Promote a gated draft to the project contract path (FR-PE-7 — the human-triggered flip).

    Separate, explicit, logged copy: no pipeline stage writes the promoted path. If *archive* and a
    hand-authored contract already exists, it is preserved under ``_superseded-handauthored/`` (the
    precedent the app uses for the YAML manifests) before being overwritten — OQ-PE-4 cutover marker:
    the promoted file carries the ``startd8-artifact: prisma-schema`` header; a hand-authored one does
    not, so "derived vs hand-authored" is decidable from the file itself.
    """
    draft = Path(run_dir) / "schema.prisma"
    if not draft.is_file():
        raise FileNotFoundError(f"no gated draft at {draft} — run emit_schema_draft first")
    target = Path(project_path)
    if archive and target.is_file():
        archive_dir = target.parent / "_superseded-handauthored"
        archived = archive_dir / target.name
        # Archive ONCE: the dir means "the original hand-authored contract", not "whatever was live
        # before the last promote". Re-archiving on every promote churned it (header/reorder-only
        # diffs) — skip if it already exists so subsequent promotes don't touch it.
        if not archived.exists():
            archive_dir.mkdir(parents=True, exist_ok=True)
            archived.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(draft.read_text(encoding="utf-8"), encoding="utf-8")
    return str(target)
