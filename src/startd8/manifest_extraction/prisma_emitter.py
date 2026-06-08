"""§2.1 Prisma emitter (DRAFT mode) — render an :class:`EntityGraph` back out as ``schema.prisma``.

The deferred half of FR-WPI-8: the *writer* that makes ``schema.prisma`` a **derived** artifact
(today the doc-derived graph is only DIFF'd against the live contract — see
``entities.diff_against_live``). Slice 1 covers **FR-PE-1/2/3**:

- **FR-PE-1** — one ``model`` block per entity + per join, with the verbatim datasource/generator
  header, in stable declaration order; round-trips through ``parse_prisma_schema``.
- **FR-PE-2** — inject the six implicit bookkeeping fields (never authored in the doc tables) with
  exact attributes, on **every** model (entity *and* join — the live join tables carry them too).
- **FR-PE-3** — relationships by convention from ``graph.joins`` + ``graph.fk_parents``: join
  models (FK scalars + ``@relation(... onDelete: Cascade)`` + compound ``@@unique``), the
  reverse-relation list fields on each side, and ``belongs to`` / ``has`` parent FKs + their
  reverse lists.

Out of slice 1 (FR-PE-5, needs the OQ-PE-1/2/3 grammar decisions): non-bookkeeping ``@default``,
explicit ``@@index`` / compound ``@@unique`` on non-join entities, and the loose-reference (no-FK)
marker. Fields whose ``prisma_type`` is ``None`` (outside the plain-type vocabulary) are flagged,
never emitted wrong (the FR-WPI ``not_extracted`` discipline).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import re

from ..backend_codegen._headers import header_standard
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


def _plural(name: str) -> str:
    """A reverse-relation list field name: lowerCamel plural (``Capability`` → ``capabilities``)."""
    base = _lower_camel(name)
    return base[:-1] + "ies" if base.endswith("y") else base + "s"


def _relation_attr(fk: str) -> str:
    return f"@relation(fields: [{fk}], references: [id], onDelete: Cascade)"


def _field_line(name: str, body: str) -> str:
    return f"  {name} {body}"


def _model_block(name: str, lines: List[str]) -> str:
    return f"model {name} {{\n" + "\n".join(lines) + "\n}"


def render_prisma_schema(
    graph: EntityGraph, source_file: str = "prisma/schema.prisma"
) -> PrismaSchemaResult:
    """Render ``schema.prisma`` from the doc-derived :class:`EntityGraph` (FR-PE-1/2/3, $0)."""
    unrenderable: List[UnrenderableField] = []

    # --- precompute relationship-derived members keyed by entity name (FR-PE-3) -----------------
    rev_lists: Dict[str, List[Tuple[str, str]]] = {n: [] for n in graph.entities}
    fk_blocks: Dict[str, List[Tuple[str, str]]] = {n: [] for n in graph.entities}

    # belongs-to / has: child carries `<parent>Id` + a relation object; parent gets a reverse list.
    for child, parents in graph.fk_parents.items():
        for parent in parents:
            fk = f"{_lower_camel(parent)}Id"
            fk_blocks.setdefault(child, []).append((fk, "String"))
            fk_blocks[child].append((_lower_camel(parent), f"{parent} {_relation_attr(fk)}"))
            rev_lists.setdefault(parent, []).append((_plural(child), f"{child}[]"))

    # M2M join: each side gets a reverse list typed by the join model.
    for j in graph.joins:
        rev_lists.setdefault(j.left, []).append((_plural(j.right), f"{j.name}[]"))
        rev_lists.setdefault(j.right, []).append((_plural(j.left), f"{j.name}[]"))

    blocks: List[str] = []

    # --- entity models -------------------------------------------------------------------------
    for name, ent in graph.entities.items():
        lines = [_field_line(fn, body) for fn, body in _BOOKKEEPING]
        lines.append("")  # readability gap between bookkeeping and domain fields
        for f in ent.fields:
            if f.prisma_type is None:
                unrenderable.append(UnrenderableField(name, f.name, "type outside plain-type vocabulary"))
                continue
            if f.default is not None:  # FR-PE-5(a): a defaulted scalar is non-optional
                lines.append(_field_line(f.name, f"{f.prisma_type} @default({f.default})"))
            else:
                opt = "" if f.required else "?"
                lines.append(_field_line(f.name, f"{f.prisma_type}{opt}"))
        for parent in graph.loose_refs.get(name, []):   # FR-PE-5(c): loose ref — scalar, no @relation
            lines.append(_field_line(f"{_lower_camel(parent)}Id", "String"))
        for fk, body in fk_blocks.get(name, []):
            lines.append(_field_line(fk, body))
        for lf, body in rev_lists.get(name, []):
            lines.append(_field_line(lf, body))
        for cols in graph.uniques.get(name, []):        # FR-PE-5(b): explicit compound @@unique
            lines.append(f"  @@unique([{', '.join(cols)}])")
        for cols in graph.indexes.get(name, []):        # FR-PE-5(b): explicit @@index
            lines.append(f"  @@index([{', '.join(cols)}])")
        blocks.append(_model_block(name, lines))

    # --- join models (FR-PE-3): bookkeeping + two FK + two relation objects + compound @@unique --
    for j in graph.joins:
        lines = [_field_line(fn, body) for fn, body in _BOOKKEEPING]
        lines.append("")
        lines.append(_field_line(j.fk_left, "String"))
        lines.append(_field_line(j.fk_right, "String"))
        lines.append(_field_line(_lower_camel(j.left), f"{j.left} {_relation_attr(j.fk_left)}"))
        lines.append(_field_line(_lower_camel(j.right), f"{j.right} {_relation_attr(j.fk_right)}"))
        lines.append(f"  @@unique([{j.fk_left}, {j.fk_right}])")
        blocks.append(_model_block(j.name, lines))

    body = _PRISMA_PREAMBLE + "\n\n" + "\n\n".join(blocks) + "\n"
    sha = schema_sha256(body)
    header = header_standard(source_file, sha, "prisma-schema")
    text = header + "\n\n" + body
    return PrismaSchemaResult(
        text=text,
        schema_sha256=sha,
        models_rendered=len(graph.entities) + len(graph.joins),
        unrenderable=tuple(unrenderable),
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
    round_trips: bool                 # FR-PE-6: emitted text parses back to the same model set
    parity_drift: Tuple[str, ...]     # FR-PE-4 drift vs live (empty ⇒ parity); () when no live given
    models: int
    unrenderable: Tuple[UnrenderableField, ...]
    draft_path: Optional[str]         # where the draft was written (run dir), or None if gate failed


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
    round_trips = set(parsed.models) == expected
    drift = tuple(semantic_diff(res.text, live_text)) if live_text is not None else ()

    draft_path: Optional[str] = None
    if round_trips:  # FR-PE-6: do not write a draft that doesn't round-trip
        draft = Path(run_dir) / "schema.prisma"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(res.text, encoding="utf-8")
        draft_path = str(draft)

    ok = round_trips and (live_text is None or not drift)
    return EmitGateResult(
        ok=ok, round_trips=round_trips, parity_drift=drift, models=res.models_rendered,
        unrenderable=res.unrenderable, draft_path=draft_path,
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
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / target.name).write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(draft.read_text(encoding="utf-8"), encoding="utf-8")
    return str(target)
