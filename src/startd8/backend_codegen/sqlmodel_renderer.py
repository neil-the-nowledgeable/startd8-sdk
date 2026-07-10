"""Deterministic Prisma→SQLModel table rendering (Python contract-codegen, Step 2 / FR-2).

Co-projects the same ``.prisma`` contract (the neutral IDL) into **SQLModel table classes** — the
persistence layer — alongside the Step 1 pure-Pydantic ``models.py`` (the API/validation/AI-tool
contract). Both are generated from one schema, so "nothing is hand-typed twice". Reuses the
Step 1 scalar map / import machinery and the stack-neutral ``schema_sha256`` /
``composite_type_names`` helpers.

**OQ-3 (resolved):** the ``class X(SQLModel, table=True)`` is the persistence truth; the API edge
gets typed DTOs generated *alongside* it — ``<Name>Create`` (editable surface, hides ``@default``
server-set fields), ``<Name>Read`` (full view), ``<Name>Update`` (every non-PK field optional, for
partial PATCH). The table class stays unchanged, so the fidelity gate is unaffected.

Scope (all runtime-verified against the real 15-model schema): primary keys — field ``@id`` and
compound ``@@id([...])`` (join models); scalar columns; enum classes (``str, Enum``); list scalars
as JSON columns; the Create/Read/Update DTOs; **FK constraints** (``@relation`` →
``Field(foreign_key="table.col")``); **``Relationship()`` ORM-navigation** with cross-model
``back_populates`` pairing (relation-name disambiguation; self-ref + implicit-M2M are flagged and
skipped); and **Prisma ``@default`` / ``@updatedAt`` translation** (``cuid``/``uuid`` →
``default_factory``, ``now()``/``@updatedAt`` → utcnow factory + ``onupdate``, literals →
``default=``). Reserved SQLAlchemy attribute names (``metadata``/``registry``) fail loud rather than
emit import-crashing code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ..frontend_codegen.schema_renderer import (
    UnrenderableField,
    composite_type_names,
    schema_sha256,
)
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema
from .pydantic_renderer import _PY_SCALAR

_REL_FIELDS_RE = re.compile(r"fields:\s*\[([^\]]*)\]")
_REL_REFS_RE = re.compile(r"references:\s*\[([^\]]*)\]")
_BLOCK_ID_RE = re.compile(r"@@id\(\s*\[([^\]]*)\]")


def _compound_pk_cols(schema: PrismaSchema, model_name: str) -> Set[str]:
    """Column names of a model's compound primary key (``@@id([a, b])``), or an empty set.

    Needed for join models (M2M) whose key is block-level, not a field ``@id`` — without these the
    table has no primary key and SQLAlchemy cannot map it.
    """
    model = schema.model(model_name)
    if model is None:
        return set()
    for a in model.block_attributes:
        m = _BLOCK_ID_RE.search(a)
        if m:
            return {x.strip() for x in m.group(1).split(",") if x.strip()}
    return set()


_BLOCK_UNIQUE_RE = re.compile(r"@@unique\(\s*\[([^\]]*)\]")


def _compound_unique_cols(
    schema: PrismaSchema, model_name: str, pk_cols: Set[str]
) -> List[Tuple[str, ...]]:
    """Column tuples of a model's ``@@unique([a, b])`` block attributes (F3b, model-level).

    Excludes any tuple identical to the model's compound primary key (``@@id``) — a PK is already
    unique, so a matching ``@@unique`` would emit a redundant constraint. Order within each tuple is
    preserved (constraint column order is significant).
    """
    model = schema.model(model_name)
    if model is None:
        return []
    out: List[Tuple[str, ...]] = []
    for a in model.block_attributes:
        m = _BLOCK_UNIQUE_RE.search(a)
        if not m:
            continue
        cols = tuple(x.strip() for x in m.group(1).split(",") if x.strip())
        if cols and set(cols) != pk_cols:
            out.append(cols)
    return out


_DEFAULT_RE = re.compile(r"@default\((.*)\)")
# Attribute names SQLAlchemy's Declarative API reserves on a mapped class.
_RESERVED_ATTRS = frozenset({"metadata", "registry"})


def _default_field_arg(field: PrismaField, needs: Set[str]) -> str:
    """Translate a Prisma ``@default(...)`` / ``@updatedAt`` into a SQLModel ``Field(...)`` arg.

    Returns the kwarg string (e.g. ``default_factory=_gen_id``, ``default="local"``) or ``""`` when
    there is no translatable default. ``cuid()``/``uuid()`` → a uuid-hex generator; ``now()`` /
    ``@updatedAt`` → a tz-aware utcnow factory (``@updatedAt`` also adds SQL ``onupdate``);
    ``autoincrement()`` is left to SQLAlchemy.
    """
    if any(a == "@updatedAt" for a in field.attributes):
        needs.add("utcnow")
        return 'default_factory=_utcnow, sa_column_kwargs={"onupdate": _utcnow}'
    attr = next((a for a in field.attributes if a.startswith("@default(")), "")
    if not attr:
        return ""
    m = _DEFAULT_RE.search(attr)
    if not m:
        return ""
    val = m.group(1).strip()
    if val in ("cuid()", "uuid()"):
        needs.add("genid")
        return "default_factory=_gen_id"
    if val == "now()":
        needs.add("utcnow")
        return "default_factory=_utcnow"
    if val == "autoincrement()":
        return ""  # integer PK auto-increments
    if val.startswith('"') and val.endswith('"'):
        return f"default={val}"  # quoted string literal
    if val in ("true", "false"):
        return f"default={'True' if val == 'true' else 'False'}"
    # F13: `yes`/`no` bareword on a Boolean field is a boolean, NOT a truthy string. Gate on the
    # field type so a `String @default(yes)` (a legit enum member) stays a string. Without this,
    # `active Boolean @default(no)` rendered `Field(default="no")` — `"no"` is truthy, so the field
    # silently defaulted True (portal-rebuild F13: operator-by-default).
    if field.type == "Boolean" and val in ("yes", "no"):
        return f"default={'True' if val == 'yes' else 'False'}"
    if re.fullmatch(r"-?\d+(\.\d+)?", val):
        return f"default={val}"  # numeric literal
    return f'default="{val}"'  # bareword (enum member / token) → string default


def _reserved_name_violations(
    schema: PrismaSchema, model_names: List[str]
) -> List[str]:
    """``Model.field`` for any scalar field whose name is a reserved SQLAlchemy attribute."""
    out: List[str] = []
    for name in model_names:
        for f in schema.scalar_fields(name):
            if f.name in _RESERVED_ATTRS:
                out.append(f"{name}.{f.name}")
    return out


def _fk_map(schema: PrismaSchema, model_name: str) -> Dict[str, str]:
    """Map ``fk_scalar_name -> "<target_table>.<ref_col>"`` from a model's ``@relation`` fields.

    A Prisma relation field (``metric Metric? @relation(fields: [metricId], references: [id])``)
    names the FK scalar (``metricId``), the referenced column (``id``), and — via its type — the
    target model (``Metric`` → table ``metric``, SQLModel's default lowercased tablename). The
    composite (multi-column) FK case is handled by zipping ``fields`` with ``references``.
    """
    out: Dict[str, str] = {}
    model = schema.model(model_name)
    if model is None:
        return out
    for f in model.fields:
        rel = next((a for a in f.attributes if a.startswith("@relation(")), None)
        if not rel:
            continue
        fm = _REL_FIELDS_RE.search(rel)
        rm = _REL_REFS_RE.search(rel)
        if not fm or not rm:
            continue
        fk_fields = [x.strip() for x in fm.group(1).split(",") if x.strip()]
        ref_cols = [x.strip() for x in rm.group(1).split(",") if x.strip()]
        target_table = (
            f.type.lower()
        )  # SQLModel default __tablename__ is the lowercased class name
        for fk, ref in zip(fk_fields, ref_cols):
            out[fk] = f"{target_table}.{ref}"
    return out


_REL_NAME_RE = re.compile(r'@relation\(\s*(?:name:\s*)?"([^"]+)"')


def _relation_attr(field: PrismaField) -> str:
    return next((a for a in field.attributes if a.startswith("@relation(")), "")


def _relation_name(field: PrismaField) -> str:
    m = _REL_NAME_RE.search(_relation_attr(field))
    return m.group(1) if m else ""


def _owns_fk(field: PrismaField) -> bool:
    """True if this relation field owns the FK (its ``@relation`` carries ``fields: [...]``)."""
    return "fields:" in _relation_attr(field)


def _partner_field(schema: PrismaSchema, owner_model: str, field: PrismaField) -> str:
    """The matching relation field name on the target model, or "" if not uniquely pairable.

    Pairs by Prisma relation name when present (disambiguates multiple relations between the same
    two models); otherwise pairs only when exactly one candidate exists. A self-referential same
    field is excluded.
    """
    target = schema.model(field.type)
    if target is None:
        return ""
    rel_name = _relation_name(field)
    cands = [
        p
        for p in target.fields
        if p.type == owner_model
        and not (field.type == owner_model and p.name == field.name)
    ]
    if rel_name:
        named = [p for p in cands if _relation_name(p) == rel_name]
        return named[0].name if len(named) == 1 else ""
    return cands[0].name if len(cands) == 1 else ""


def _relationship_lines(
    schema: PrismaSchema, composites: frozenset, model_name: str, needs: Set[str]
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """SQLModel ``Relationship()`` lines for a model's object-relation fields (with back_populates).

    Returns (lines, skipped) where skipped is ``(field, reason)`` for relations we deliberately do
    not emit (self-referential — needs ``remote_side``; implicit many-to-many — needs a link model).
    """
    model = schema.model(model_name)
    lines: List[str] = []
    skipped: List[Tuple[str, str]] = []
    if model is None:
        return lines, skipped
    for f in model.fields:
        if f.type not in schema.models or f.type in composites:
            continue  # scalar/enum column, not an object relation
        if f.type == model_name:
            skipped.append((f.name, "self-referential relation (needs remote_side)"))
            continue
        partner = _partner_field(schema, model_name, f)
        if f.is_list and partner:
            pf = next(
                (p for p in schema.model(f.type).fields if p.name == partner), None
            )
            if pf is not None and pf.is_list and not _owns_fk(f) and not _owns_fk(pf):
                skipped.append((f.name, "implicit many-to-many (needs link model)"))
                continue
        needs.add("Relationship")
        # Quoted forward refs (this file has no `from __future__ import annotations`): SQLModel
        # resolves these eagerly via the class registry.
        if f.is_list:
            ann = f'list["{f.type}"]'
        elif f.is_optional:
            needs.add("Optional")
            ann = f'Optional["{f.type}"]'
        else:
            ann = f'"{f.type}"'
        bp = f'back_populates="{partner}"' if partner else ""
        lines.append(f"    {f.name}: {ann} = Relationship({bp})")
    return lines, skipped


@dataclass(frozen=True)
class SQLModelRenderResult:
    """The rendered SQLModel-tables file plus provenance, flagged fields, and stats."""

    text: str
    schema_sha256: str
    unrenderable: Tuple[UnrenderableField, ...]
    models_rendered: int = 0
    fields_rendered: int = 0
    enums_rendered: int = 0


def _base_type(
    field: PrismaField, schema: PrismaSchema, needs: Set[str], enums_used: Set[str]
) -> str:
    """Bare column type: a Python scalar, an enum **class name**, or ``Any`` (flagged) if unknown."""
    if field.type in _PY_SCALAR:
        base = _PY_SCALAR[field.type]
        if base in ("Decimal", "datetime", "Any"):
            needs.add(base)
        return base
    if field.type in schema.enums:
        enums_used.add(field.type)
        needs.add("Enum")
        return field.type
    needs.add("Any")
    return "Any"


def _render_table_field(
    field: PrismaField,
    schema: PrismaSchema,
    needs: Set[str],
    enums_used: Set[str],
    fk: str = "",
    is_pk: bool = False,
) -> Tuple[str, bool]:
    """Render one ``    <name>: <ann>[ = ...]`` line. Returns (line, was_unrenderable).

    ``fk`` (``"table.col"``) adds a ``foreign_key=`` constraint; ``is_pk`` marks the column a
    primary key (covers both field ``@id`` and compound ``@@id`` members).
    """
    base = _base_type(field, schema, needs, enums_used)
    unrenderable = base == "Any" and field.type not in ("Json",)

    if field.is_list:
        needs.add("sqlalchemy")
        return (
            f"    {field.name}: list[{base}] = "
            f"Field(default_factory=list, sa_column=Column(JSON))",
            unrenderable,
        )

    # Scalar Json: SQLModel cannot map `Any` to a column, so it needs an explicit JSON column
    # (mirrors the list branch above). Without this the emitted `Optional[Any] = None` raises at
    # import: "typing.Any has no matching SQLAlchemy type" (client-logged friction F-11).
    if field.type == "Json":
        needs.add("sqlalchemy")
        if field.is_optional:
            needs.add("Optional")
            return (
                f"    {field.name}: Optional[{base}] = "
                f"Field(default=None, sa_column=Column(JSON))",
                unrenderable,
            )
        return (
            f"    {field.name}: {base} = Field(sa_column=Column(JSON))",
            unrenderable,
        )

    # Compose Field(...) args from primary-key + foreign-key + a translated Prisma @default.
    default_arg = _default_field_arg(field, needs)
    args: List[str] = []
    if is_pk:
        args.append("primary_key=True")
    if fk:
        args.append(f'foreign_key="{fk}"')
    # F3b: emit a real DB unique constraint for a field-level `@unique`. The parser recognizes it
    # (PrismaField.is_unique) but the renderer previously dropped it, so `email String @unique`
    # produced no `unique=True` — uniqueness was advisory-only (portal-rebuild F3b). A PK is already
    # unique, so skip it there to avoid a redundant constraint.
    if field.is_unique and not is_pk:
        args.append("unique=True")
    if default_arg:
        args.append(default_arg)

    if field.is_optional:
        needs.add("Optional")
        if default_arg:  # the @default provides the default; don't add `default=None`
            return (
                f"    {field.name}: Optional[{base}] = Field({', '.join(args)})",
                unrenderable,
            )
        if args:
            return (
                f"    {field.name}: Optional[{base}] = Field(default=None, {', '.join(args)})",
                unrenderable,
            )
        return f"    {field.name}: Optional[{base}] = None", unrenderable

    if args:
        return f"    {field.name}: {base} = Field({', '.join(args)})", unrenderable
    return f"    {field.name}: {base}", unrenderable


def _server_set(field: PrismaField) -> bool:
    """Server-filled fields (a Prisma ``@default`` / ``@updatedAt``) — hidden from the Create DTO."""
    return any(
        a.startswith("@default") or a.startswith("@updatedAt") or a == "@updatedAt"
        for a in field.attributes
    )


def _dto_field_line(
    field: PrismaField,
    schema: PrismaSchema,
    needs: Set[str],
    enums_used: Set[str],
    *,
    force_optional: bool,
) -> str:
    """One DTO field line — a plain Pydantic annotation (no ``Field()``/``sa_column``: DTOs aren't
    tables). ``force_optional`` makes every field ``Optional[...] = None`` (the Update DTO).
    """
    base = _base_type(field, schema, needs, enums_used)
    ann = f"list[{base}]" if field.is_list else base
    if force_optional or field.is_optional:
        needs.add("Optional")
        return f"    {field.name}: Optional[{ann}] = None"
    return f"    {field.name}: {ann}"


def _dto_block(
    name: str,
    suffix: str,
    fields: List[PrismaField],
    schema: PrismaSchema,
    needs: Set[str],
    enums_used: Set[str],
    *,
    force_optional: bool = False,
) -> str:
    """A non-table SQLModel DTO class (``<Name>Create``/``Read``/``Update``) for the API edge."""
    lines = [f"class {name}{suffix}(SQLModel):"]
    if not fields:
        lines.append("    pass")
        return "\n".join(lines)
    for f in fields:
        lines.append(
            _dto_field_line(f, schema, needs, enums_used, force_optional=force_optional)
        )
    return "\n".join(lines)


def _import_block(needs: Set[str]) -> str:
    """Synthesize the import block: stdlib (datetime, decimal, enum, typing) / third-party
    (sqlalchemy, sqlmodel).

    Note: this file deliberately does **not** use ``from __future__ import annotations`` — SQLModel
    resolves ``Relationship()`` target types eagerly, and deferred (string) annotations make
    SQLAlchemy treat ``list[X]`` as a literal class name. Relationship targets are quoted forward
    refs (``Optional["Metric"]``); scalar annotations resolve at definition time (enum classes are
    emitted above the tables, ``Optional``/``Decimal``/``datetime`` are imported)."""
    groups: List[List[str]] = []

    stdlib: List[str] = []
    if "genid" in needs:
        stdlib.append("import uuid")
    if "utcnow" in needs:
        stdlib.append("from datetime import datetime, timezone")
    elif "datetime" in needs:
        stdlib.append("from datetime import datetime")
    if "Decimal" in needs:
        stdlib.append("from decimal import Decimal")
    if "Enum" in needs:
        stdlib.append("from enum import Enum")
    typing_names = sorted(n for n in ("Any", "Optional") if n in needs)
    if typing_names:
        stdlib.append(f"from typing import {', '.join(typing_names)}")
    if stdlib:
        groups.append(stdlib)

    third: List[str] = []
    sa_names: List[str] = []
    if "sqlalchemy" in needs:
        sa_names += ["JSON", "Column"]  # list-scalar JSON columns
    if "uniqueconstraint" in needs:
        sa_names.append("UniqueConstraint")  # F3b: model-level @@unique
    if sa_names:
        third.append("from sqlalchemy import " + ", ".join(sa_names))
    sm = (
        ["Field", "Relationship", "SQLModel"]
        if "Relationship" in needs
        else ["Field", "SQLModel"]
    )
    third.append("from sqlmodel import " + ", ".join(sm))
    groups.append(third)

    return "\n\n".join("\n".join(g) for g in groups)


def _render_enum_class(name: str, values: Tuple[str, ...]) -> str:
    lines = [f"class {name}(str, Enum):"]
    for v in values:
        lines.append(f'    {v} = "{v}"')
    return "\n".join(lines)


def render_sqlmodel_tables(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    human_inputs_text: Optional[str] = None,
) -> SQLModelRenderResult:
    """Assemble the SQLModel-tables file from a ``.prisma`` schema (FR-2).

    Emits, in **schema source order**: a ``#`` GENERATED header (artifact ``sqlmodel-tables``) with
    the embedded ``schema-sha256``; the synthesized imports; one ``str, Enum`` class per **used**
    enum (declaration order); and per model (composites excluded) a ``class <Model>(SQLModel,
    table=True)`` plus its ``<Model>Create``/``Read``/``Update`` DTOs. List scalars become JSON
    columns; ``@id`` fields become primary keys. Unmappable scalar types are flagged, never raised.
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    composites = composite_type_names(schema_text)
    # F-12: the human_inputs owned-field policy must reach the API write DTOs too, not just the
    # AI edge schema — otherwise the generic PATCH endpoint (via <Name>Update) can still overwrite
    # an attorney-gate/verification-pipeline field. Read DTO keeps them (owned != hidden from view).
    from .ai_layer import parse_human_inputs

    human_only = parse_human_inputs(human_inputs_text).human_only_fields

    needs: Set[str] = set()
    enums_used: Set[str] = set()
    flagged: List[UnrenderableField] = []
    blocks: List[str] = []
    model_names = [n for n in schema.models if n not in composites]

    # Fail loud, never emit import-crashing code: SQLAlchemy reserves a few attribute names.
    violations = _reserved_name_violations(schema, model_names)
    if violations:
        raise ValueError(
            "SQLModel reserved attribute name(s) in the contract — rename the field in the "
            f".prisma schema: {', '.join(violations)}. Reserved by SQLAlchemy's Declarative API: "
            f"{', '.join(sorted(_RESERVED_ATTRS))}."
        )

    for name in model_names:
        scalars = schema.scalar_fields(name)
        fkmap = _fk_map(schema, name)
        pk_cols = _compound_pk_cols(schema, name)
        lines = [f"class {name}(SQLModel, table=True):"]
        for f in scalars:
            line, bad = _render_table_field(
                f,
                schema,
                needs,
                enums_used,
                fk=fkmap.get(f.name, ""),
                is_pk=f.is_id or f.name in pk_cols,
            )
            lines.append(line)
            if bad:
                flagged.append(
                    UnrenderableField(
                        entity=name,
                        field=f.name,
                        prisma_type=f.type,
                        reason="no SQLModel column mapping for Prisma type",
                    )
                )
        rel_lines, rel_skipped = _relationship_lines(schema, composites, name, needs)
        lines.extend(rel_lines)
        for fld, reason in rel_skipped:
            flagged.append(
                UnrenderableField(
                    entity=name, field=fld, prisma_type="relation", reason=reason
                )
            )
        # F3b: model-level `@@unique([...])` → a real composite UniqueConstraint. Field-level
        # `@unique` is handled inline (unique=True); this covers the multi-column case.
        uniq_cols = _compound_unique_cols(schema, name, set(pk_cols))
        if uniq_cols:
            needs.add("uniqueconstraint")
            constraints = ", ".join(
                "UniqueConstraint({}, name={!r})".format(
                    ", ".join(repr(c) for c in cols),
                    "uq_{}_{}".format(name.lower(), "_".join(cols)),
                )
                for cols in uniq_cols
            )
            lines.append(f"    __table_args__ = ({constraints},)")
        if not scalars and not rel_lines and not uniq_cols:
            lines.append("    pass")
        blocks.append("\n".join(lines))

        # API DTOs (OQ-3): Create hides server-set (@default) fields; Read is the full view;
        # Update makes every non-PK field optional (partial PATCH). The table class above stays
        # the persistence truth and is unchanged.
        create_fields = [
            f
            for f in scalars
            if not _server_set(f) and (name, f.name) not in human_only
        ]
        update_fields = [
            f
            for f in scalars
            if not f.is_id and (name, f.name) not in human_only
        ]
        blocks.append(
            _dto_block(name, "Create", create_fields, schema, needs, enums_used)
        )
        blocks.append(
            _dto_block(name, "Read", list(scalars), schema, needs, enums_used)
        )
        blocks.append(
            _dto_block(
                name,
                "Update",
                update_fields,
                schema,
                needs,
                enums_used,
                force_optional=True,
            )
        )

    # Enum classes, in schema declaration order, only those actually used.
    enum_blocks = [
        _render_enum_class(name, vals)
        for name, vals in schema.enums.items()
        if name in enums_used
    ]

    # F-12: tables.py now derives from schema + human_inputs (the owned-field policy drops owned
    # columns from the *Create/*Update DTOs), so it carries a `human-inputs-sha256` header alongside
    # the schema hash — reusing the SAME sha the AI layer stamps (empty/absent policy → canonical
    # empty-input sha, so a project without --human-inputs still round-trips clean).
    from ._headers import header_human_inputs

    header = header_human_inputs(
        source_file, sha, schema_sha256(human_inputs_text or ""), "sqlmodel-tables"
    )
    imports = _import_block(needs)

    # Default-factory helpers (emitted only when a translated @default needs them).
    helpers: List[str] = []
    if "genid" in needs:
        helpers.append("def _gen_id() -> str:\n    return uuid.uuid4().hex")
    if "utcnow" in needs:
        helpers.append(
            "def _utcnow() -> datetime:\n    return datetime.now(timezone.utc)"
        )

    body_blocks = enum_blocks + blocks
    # tail sections (imports / helpers / classes) are separated by two blank lines (PEP 8).
    tail = [imports]
    if helpers:
        tail.append("\n\n\n".join(helpers))
    if body_blocks:
        tail.append("\n\n\n".join(body_blocks))
    text = header + "\n\n" + "\n\n\n".join(tail) + "\n"

    fields_rendered = sum(len(schema.scalar_fields(n)) for n in model_names)
    return SQLModelRenderResult(
        text=text,
        schema_sha256=sha,
        unrenderable=tuple(flagged),
        models_rendered=len(model_names),
        fields_rendered=fields_rendered,
        enums_rendered=len(enum_blocks),
    )
