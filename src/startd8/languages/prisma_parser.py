"""Prisma schema (`.prisma`) parser — RUN-008 remediation FR-6.

Parses a Prisma schema into a structured model so downstream checks can reason
about entities, fields, types, and uniqueness **without** a Node/Prisma toolchain
present. Two consumers:

- **FR-5 fallback** — when ``prisma generate`` + ``tsc`` are unavailable, the
  unique-key set here lets the validator flag invalid ``findUnique``/``upsert``
  ``where`` clauses (e.g. RUN-008's ``where: { ownerId }`` on a non-``@unique``
  column — only ``id`` is unique on ``Profile``).
- **FR-7 (Prisma↔Zod symmetry)** — the field-name/type set here is compared
  against the Zod ``z.object`` extraction. The RUN-008 spike proved ``tsc``
  cannot see this divergence (excess-property checks are suppressed for
  ``{ ...parsed.data }`` spreads), so this parser is the *only* surface that
  catches ``summary``/``bio``, ``yearsExp``/``yearsOfExperience``, and the
  invented ``profileId`` FK.

This is a pragmatic structural parser (block + field tokenization), not a full
Prisma grammar. It handles the constructs that appear in generated schemas:
``datasource``/``generator``/``model``/``enum``/``type`` blocks, ``?``/``[]``
field modifiers, field attributes (``@id``/``@unique``/``@default``/
``@relation``/``@updatedAt``), and block attributes (``@@id``/``@@unique``/
``@@index``). Line comments (``//``, ``///``) are stripped quote-aware.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# Prisma scalar types (everything else is an enum, a composite ``type``, or a
# relation to another model). https://www.prisma.io/docs/orm/reference/prisma-schema-reference
PRISMA_SCALARS: frozenset[str] = frozenset(
    {"String", "Boolean", "Int", "BigInt", "Float", "Decimal", "DateTime", "Json", "Bytes"}
)

_HEADER_RE = re.compile(r"(model|enum|type|datasource|generator)\s+(\w+)\s*\{")
# Field types in Prisma are always PascalCase (scalars, enums, model/type names),
# so requiring an uppercase-initial type token rejects stray prose lines while
# still matching every real declaration (keeps the parser lenient, not gullible).
_FIELD_RE = re.compile(r"^(?P<name>\w+)\s+(?P<type>[A-Z]\w*(?:\[\]|\?)?)\s*(?P<rest>.*)$")
_PROVIDER_RE = re.compile(r'provider\s*=\s*"([^"]*)"')
_BRACKET_LIST_RE = re.compile(r"\[([^\]]*)\]")


@dataclass(frozen=True)
class PrismaField:
    """A single field declaration inside a ``model`` (or composite ``type``)."""

    name: str
    type: str  # base type, modifiers stripped (e.g. "String", "Int", "ProofPoint")
    is_optional: bool  # trailing ``?``
    is_list: bool  # trailing ``[]``
    attributes: Tuple[str, ...]  # raw attribute tokens, e.g. ("@id", "@default(cuid())")

    @property
    def is_id(self) -> bool:
        return any(a == "@id" or a.startswith("@id(") for a in self.attributes)

    @property
    def is_unique(self) -> bool:
        return any(a == "@unique" or a.startswith("@unique(") for a in self.attributes)

    @property
    def has_relation_attr(self) -> bool:
        return any(a == "@relation" or a.startswith("@relation(") for a in self.attributes)


@dataclass(frozen=True)
class PrismaModel:
    """A ``model`` (or composite ``type``) block."""

    name: str
    fields: Tuple[PrismaField, ...]
    block_attributes: Tuple[str, ...]  # raw ``@@`` tokens (e.g. "@@unique([a, b])")

    def field(self, name: str) -> Optional[PrismaField]:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    @property
    def field_names(self) -> frozenset[str]:
        return frozenset(f.name for f in self.fields)

    @property
    def single_column_unique_keys(self) -> frozenset[str]:
        """Field names usable as a standalone ``findUnique``/``upsert`` ``where`` key.

        A column is uniquely-queryable iff it is ``@id`` or ``@unique``. Compound
        keys (``@@id``/``@@unique``) are *not* included here — they require the
        composite key object, see :attr:`compound_unique_keys`.
        """
        return frozenset(f.name for f in self.fields if f.is_id or f.is_unique)

    @property
    def compound_unique_keys(self) -> Tuple[Tuple[str, ...], ...]:
        """Compound keys from ``@@id([...])`` / ``@@unique([...])`` block attributes."""
        out: list[Tuple[str, ...]] = []
        for attr in self.block_attributes:
            if attr.startswith("@@unique") or attr.startswith("@@id"):
                m = _BRACKET_LIST_RE.search(attr)
                if m:
                    cols = tuple(c.strip() for c in m.group(1).split(",") if c.strip())
                    if cols:
                        out.append(cols)
        return tuple(out)


@dataclass(frozen=True)
class PrismaSchema:
    """A parsed Prisma schema."""

    models: Dict[str, PrismaModel]
    enums: Dict[str, Tuple[str, ...]]
    datasource_provider: Optional[str]
    generator_provider: Optional[str]

    def model(self, name: str) -> Optional[PrismaModel]:
        return self.models.get(name)

    def is_scalar_type(self, type_name: str) -> bool:
        """True if *type_name* is a Prisma scalar or a declared enum (not a relation)."""
        return type_name in PRISMA_SCALARS or type_name in self.enums

    def is_relation_field(self, field: PrismaField) -> bool:
        """True if *field* links to another model (object relation), not a scalar/enum."""
        if field.has_relation_attr:
            return True
        return field.type in self.models

    def scalar_fields(self, model_name: str) -> Tuple[PrismaField, ...]:
        """Scalar (non-relation) fields of a model — the surface FR-7 compares to Zod."""
        m = self.models.get(model_name)
        if m is None:
            return ()
        return tuple(f for f in m.fields if not self.is_relation_field(f))


def _strip_comments(text: str) -> str:
    """Remove ``//`` line comments, preserving ``//`` that appears inside strings."""
    out: list[str] = []
    for line in text.splitlines():
        res: list[str] = []
        in_str = False
        quote = ""
        i = 0
        n = len(line)
        while i < n:
            c = line[i]
            if in_str:
                res.append(c)
                if c == quote and (i == 0 or line[i - 1] != "\\"):
                    in_str = False
                i += 1
                continue
            if c in ('"', "'"):
                in_str = True
                quote = c
                res.append(c)
                i += 1
                continue
            if c == "/" and i + 1 < n and line[i + 1] == "/":
                break  # rest of line is a comment
            res.append(c)
            i += 1
        out.append("".join(res))
    return "\n".join(out)


def _iter_blocks(text: str):
    """Yield ``(kind, name, body)`` for each top-level block via brace matching."""
    n = len(text)
    pos = 0
    while True:
        m = _HEADER_RE.search(text, pos)
        if not m:
            return
        kind, name = m.group(1), m.group(2)
        depth = 0
        j = m.end() - 1  # index of the opening '{'
        while j < n:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = text[m.end() : j]
        yield kind, name, body
        pos = j + 1


def _split_attributes(rest: str) -> Tuple[str, ...]:
    """Split a field's trailing attribute string into ``@``-prefixed tokens.

    Paren-aware so ``@relation(fields: [a], references: [b])`` stays one token
    and ``@id @default(cuid())`` splits into two.
    """
    tokens: list[str] = []
    i = 0
    n = len(rest)
    while i < n:
        if rest[i] == "@":
            j = i + 1
            depth = 0
            while j < n:
                c = rest[j]
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                elif c.isspace() and depth == 0:
                    break
                j += 1
            tokens.append(rest[i:j].strip())
            i = j
        else:
            i += 1
    return tuple(t for t in tokens if t)


def _parse_field(line: str) -> Optional[PrismaField]:
    m = _FIELD_RE.match(line.strip())
    if not m:
        return None
    raw_type = m.group("type")
    is_list = raw_type.endswith("[]")
    if is_list:
        raw_type = raw_type[:-2]
    is_optional = raw_type.endswith("?")
    if is_optional:
        raw_type = raw_type[:-1]
    return PrismaField(
        name=m.group("name"),
        type=raw_type,
        is_optional=is_optional,
        is_list=is_list,
        attributes=_split_attributes(m.group("rest")),
    )


def _parse_model_body(body: str) -> Tuple[Tuple[PrismaField, ...], Tuple[str, ...]]:
    fields: list[PrismaField] = []
    block_attrs: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("@@"):
            block_attrs.append(line)
            continue
        fld = _parse_field(line)
        if fld is not None:
            fields.append(fld)
    return tuple(fields), tuple(block_attrs)


def _parse_enum_body(body: str) -> Tuple[str, ...]:
    values: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("@@") or line.startswith("@"):
            continue
        # enum value is a bare identifier (optionally with a @map attribute)
        m = re.match(r"^(\w+)", line)
        if m:
            values.append(m.group(1))
    return tuple(values)


def parse_prisma_schema(text: str) -> PrismaSchema:
    """Parse Prisma schema *text* into a :class:`PrismaSchema`.

    Lenient by design: unparseable lines are skipped rather than raising, so a
    partially-malformed schema still yields whatever structure is recoverable
    (the validator decides what to do with gaps). Returns an empty schema for
    empty/blank input.
    """
    scrubbed = _strip_comments(text or "")
    models: Dict[str, PrismaModel] = {}
    enums: Dict[str, Tuple[str, ...]] = {}
    datasource_provider: Optional[str] = None
    generator_provider: Optional[str] = None

    for kind, name, body in _iter_blocks(scrubbed):
        if kind in ("model", "type"):
            fields, block_attrs = _parse_model_body(body)
            models[name] = PrismaModel(name=name, fields=fields, block_attributes=block_attrs)
        elif kind == "enum":
            enums[name] = _parse_enum_body(body)
        elif kind == "datasource":
            pm = _PROVIDER_RE.search(body)
            if pm:
                datasource_provider = pm.group(1)
        elif kind == "generator":
            pm = _PROVIDER_RE.search(body)
            if pm and generator_provider is None:
                generator_provider = pm.group(1)

    return PrismaSchema(
        models=models,
        enums=enums,
        datasource_provider=datasource_provider,
        generator_provider=generator_provider,
    )
