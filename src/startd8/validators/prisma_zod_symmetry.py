"""Prisma↔Zod symmetry check — RUN-008 remediation FR-7.

The RUN-008 spike proved this is the **only** surface that catches the dominant
cross-file failure class: TypeScript's `tsc` cannot see field/type divergence
between a Prisma `model` and a Zod `z.object` because the routes flow data
through `{ ...parsed.data }` spreads, for which TS suppresses excess-property
checking. So a Zod schema can invent `profileId`, rename `summary`→`bio`, or
type `value` as `number` where Prisma stores `String`, and the project still
compiles. This module compares the two structurally and reports the divergence.

Two parts:
- :func:`extract_zod_objects` — a pragmatic (non-AST) extractor that pulls
  top-level ``z.object({...})`` schemas and their field type-classes from TS.
- :func:`check_prisma_zod_symmetry` — compares each Zod schema against the
  Prisma model it maps to (suffix-normalized name match by default) and returns
  :class:`SymmetryViolation` records.

Entity mapping (OQ-2) defaults to stripping a trailing ``Schema`` from the Zod
variable name (``ProfileSchema`` → ``Profile``); pass ``entity_map`` to override.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema

# z.<base> → normalized type-class
_ZOD_BASE_TO_CLASS: Dict[str, str] = {
    "string": "string",
    "number": "number",
    "bigint": "bigint",
    "boolean": "boolean",
    "date": "date",
    "unknown": "unknown",
    "any": "unknown",
    "object": "object",
    "record": "object",
    "array": "array",
    "tuple": "array",
    "set": "array",
    "enum": "enum",
    "nativeEnum": "enum",
    "literal": "literal",
    "nan": "number",
}

# Prisma scalar → acceptable Zod type-classes
_PRISMA_TO_ZOD: Dict[str, frozenset[str]] = {
    "String": frozenset({"string"}),
    "Boolean": frozenset({"boolean"}),
    "Int": frozenset({"number"}),
    "BigInt": frozenset({"number", "bigint"}),
    "Float": frozenset({"number"}),
    # Decimal accepts both: `z.number()` (numeric) and `z.string()` (money-safe, the
    # deterministic frontend generator's choice — avoids float precision loss in JSON).
    # See REQ deterministic-frontend FR-2 / CRP R2-S1.
    "Decimal": frozenset({"number", "string"}),
    "DateTime": frozenset({"string", "date"}),  # run-008 maps DateTime → z.string().datetime()
    "Json": frozenset({"unknown", "object", "array"}),
    "Bytes": frozenset({"string", "unknown"}),
}

# Concrete Zod classes we are confident enough to flag a type mismatch on.
_CONCRETE_ZOD_CLASSES = frozenset({"string", "number", "boolean", "date"})

_ZOD_OBJECT_RE = re.compile(r"(?:export\s+)?const\s+(?P<name>\w+)\s*=\s*z\s*\.\s*object\s*\(\s*\{")
_KEY_RE = re.compile(r"^(?P<key>\w+)\s*:")
_ZBASE_RE = re.compile(r"z\s*\.\s*(\w+)")


@dataclass(frozen=True)
class ZodField:
    name: str
    type_class: str  # normalized: string/number/boolean/date/unknown/object/array/enum/literal/bigint
    optional: bool
    nullable: bool


@dataclass(frozen=True)
class ZodObjectSchema:
    name: str  # variable name, e.g. "ProfileSchema"
    fields: Tuple[ZodField, ...]

    @property
    def field_names(self) -> frozenset[str]:
        return frozenset(f.name for f in self.fields)

    def field(self, name: str) -> Optional[ZodField]:
        for f in self.fields:
            if f.name == name:
                return f
        return None


@dataclass(frozen=True)
class SymmetryViolation:
    entity: str  # logical entity (Prisma model name)
    zod_schema: str  # Zod variable name
    kind: str  # field_missing_in_prisma | field_type_mismatch | fk_invented | field_missing_in_zod
    field: str
    detail: str
    severity: str  # "error" | "warning"
    source_file: Optional[str] = None  # set by evaluate_cross_file_integrity (the Zod file)


# --------------------------------------------------------------------------- #
# Zod extraction
# --------------------------------------------------------------------------- #

def _strip_ts_comments(text: str) -> str:
    """Strip ``//`` line and ``/* */`` (incl. ``/** */``) block comments, quote-aware."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    quote = ""
    in_line = False
    in_block = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line:
            if c == "\n":
                in_line = False
                out.append(c)
            i += 1
            continue
        if in_block:
            if c == "*" and nxt == "/":
                in_block = False
                i += 2
                continue
            if c == "\n":
                out.append(c)
            i += 1
            continue
        if in_str:
            out.append(c)
            if c == quote and text[i - 1] != "\\":
                in_str = False
            elif c == "`" and quote == "`":
                in_str = False
            i += 1
            continue
        if c in ('"', "'", "`"):
            in_str = True
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "/" and nxt == "/":
            in_line = True
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block = True
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _match_braces(text: str, open_idx: int) -> int:
    """Given index of a ``{``, return index of the matching ``}`` (or len(text))."""
    depth = 0
    n = len(text)
    j = open_idx
    while j < n:
        ch = text[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return n


def _split_top_level(body: str) -> List[str]:
    """Split an object-literal body into top-level ``key: expr`` entries by comma."""
    entries: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in body:
        if ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            entries.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        entries.append("".join(cur))
    return entries


def _classify_zod_expr(expr: str) -> Tuple[str, bool, bool]:
    """Return (type_class, optional, nullable) for a Zod field expression."""
    m = _ZBASE_RE.search(expr)
    base = m.group(1) if m else ""
    type_class = _ZOD_BASE_TO_CLASS.get(base, "unknown")
    nullable = ".nullable(" in expr or ".nullish(" in expr
    optional = ".optional(" in expr or ".nullish(" in expr
    return type_class, optional, nullable


def extract_zod_objects(ts_source: str) -> Dict[str, ZodObjectSchema]:
    """Extract top-level ``const X = z.object({...})`` schemas from TS source."""
    text = _strip_ts_comments(ts_source or "")
    result: Dict[str, ZodObjectSchema] = {}
    for m in _ZOD_OBJECT_RE.finditer(text):
        name = m.group("name")
        brace_idx = text.index("{", m.end() - 1)
        close_idx = _match_braces(text, brace_idx)
        body = text[brace_idx + 1 : close_idx]
        fields: list[ZodField] = []
        for entry in _split_top_level(body):
            entry = entry.strip()
            if not entry:
                continue
            km = _KEY_RE.match(entry)
            if not km:
                continue
            key = km.group("key")
            expr = entry[km.end():]
            type_class, optional, nullable = _classify_zod_expr(expr)
            fields.append(ZodField(name=key, type_class=type_class, optional=optional, nullable=nullable))
        result[name] = ZodObjectSchema(name=name, fields=tuple(fields))
    return result


# --------------------------------------------------------------------------- #
# Symmetry check
# --------------------------------------------------------------------------- #

def default_entity_name(zod_schema_name: str) -> str:
    """``ProfileSchema`` → ``Profile`` (strip a trailing ``Schema``)."""
    if zod_schema_name.endswith("Schema") and len(zod_schema_name) > len("Schema"):
        return zod_schema_name[: -len("Schema")]
    return zod_schema_name


def _prisma_type_compatible(prisma_type: str, zod_class: str, schema: PrismaSchema) -> bool:
    """True if a Prisma scalar type is compatible with a Zod field's type-class."""
    if zod_class == "unknown":
        return True  # z.unknown()/z.any() is permissive — never flag
    if prisma_type in schema.enums:
        return zod_class in ("enum", "string", "literal")
    acceptable = _PRISMA_TO_ZOD.get(prisma_type)
    if acceptable is None:
        return True  # unknown Prisma type (composite/relation) — don't flag
    if zod_class not in _CONCRETE_ZOD_CLASSES:
        return True  # only flag mismatches we're confident about
    return zod_class in acceptable


def check_prisma_zod_symmetry(
    prisma_schema: PrismaSchema,
    zod_schemas: Dict[str, ZodObjectSchema],
    *,
    entity_map: Optional[Dict[str, str]] = None,
) -> List[SymmetryViolation]:
    """Compare each Zod schema against its Prisma model; return divergences.

    High-signal violations (severity ``error``): a Zod scalar field absent from
    the Prisma model (``field_missing_in_prisma``), a Zod ``<entity>Id`` field
    with no matching Prisma FK while ``<Entity>`` is a known model
    (``fk_invented``), and a concrete type mismatch on a shared field
    (``field_type_mismatch``). Lower-signal (``warning``): a required,
    non-defaulted Prisma scalar field missing from the Zod schema
    (``field_missing_in_zod``) — input schemas legitimately omit many columns,
    so this is advisory only.
    """
    entity_map = entity_map or {}
    violations: List[SymmetryViolation] = []

    for zod_name, zod in zod_schemas.items():
        entity = entity_map.get(zod_name, default_entity_name(zod_name))
        model = prisma_schema.model(entity)
        if model is None:
            continue  # no matching Prisma model — nothing to compare

        prisma_scalar = {f.name: f for f in prisma_schema.scalar_fields(entity)}
        prisma_relation_targets = {
            f.type for f in model.fields if prisma_schema.is_relation_field(f)
        }

        # --- Zod → Prisma direction (the run-008 invented-field bug) ---
        for zf in zod.fields:
            # nested object/array Zod fields correspond to relations, not scalars
            if zf.type_class in ("object", "array"):
                continue
            if zf.name in prisma_scalar:
                pf = prisma_scalar[zf.name]
                if not _prisma_type_compatible(pf.type, zf.type_class, prisma_schema):
                    violations.append(SymmetryViolation(
                        entity=entity, zod_schema=zod_name, kind="field_type_mismatch",
                        field=zf.name,
                        detail=(f"Prisma `{pf.type}` vs Zod `{zf.type_class}` for "
                                f"`{entity}.{zf.name}`"),
                        severity="error",
                    ))
                continue
            # field is in Zod but not a Prisma scalar
            fk_match = re.match(r"^(?P<prefix>[a-z]\w*)Id$", zf.name)
            if fk_match:
                target = fk_match.group("prefix")[:1].upper() + fk_match.group("prefix")[1:]
                if target in prisma_schema.models and target not in prisma_relation_targets:
                    violations.append(SymmetryViolation(
                        entity=entity, zod_schema=zod_name, kind="fk_invented",
                        field=zf.name,
                        detail=(f"Zod declares FK `{zf.name}` but Prisma `{entity}` has no "
                                f"`{zf.name}` column and no relation to `{target}`"),
                        severity="error",
                    ))
                    continue
            violations.append(SymmetryViolation(
                entity=entity, zod_schema=zod_name, kind="field_missing_in_prisma",
                field=zf.name,
                detail=f"Zod field `{zf.name}` does not exist on Prisma model `{entity}`",
                severity="error",
            ))

        # --- Prisma → Zod direction (advisory) ---
        zod_names = zod.field_names
        for pf in prisma_schema.scalar_fields(entity):
            if pf.name in zod_names:
                continue
            if pf.is_optional:
                continue
            attrs = " ".join(pf.attributes)
            if "@default" in attrs or pf.is_id or "@updatedAt" in attrs:
                continue  # server-managed / defaulted — legitimately omitted from input
            violations.append(SymmetryViolation(
                entity=entity, zod_schema=zod_name, kind="field_missing_in_zod",
                field=pf.name,
                detail=f"Required Prisma field `{entity}.{pf.name}` is absent from Zod schema",
                severity="warning",
            ))

    return violations


def has_errors(violations: List[SymmetryViolation]) -> bool:
    return any(v.severity == "error" for v in violations)


# --------------------------------------------------------------------------- #
# Batch / cross-file entry point (consumed by the postmortem — FR-10)
# --------------------------------------------------------------------------- #

def scan_prisma_zod_sources(
    sources: Dict[str, str],
) -> Tuple[Optional[PrismaSchema], Dict[str, ZodObjectSchema], Dict[str, str]]:
    """From a ``{path: content}`` map, parse the merged Prisma schema and extract
    Zod objects per ``.ts``/``.tsx`` file.

    Returns ``(prisma_schema_or_None, {zod_name: schema}, {zod_name: source_file})``.
    All ``.prisma`` files are concatenated (a project may split the schema).
    """
    prisma_text = "\n".join(
        content for path, content in sources.items() if path.endswith(".prisma")
    )
    schema = parse_prisma_schema(prisma_text) if prisma_text.strip() else None
    zod_all: Dict[str, ZodObjectSchema] = {}
    owner: Dict[str, str] = {}
    for path, content in sources.items():
        if path.endswith((".ts", ".tsx")):
            for name, obj in extract_zod_objects(content).items():
                zod_all[name] = obj
                owner[name] = path
    return schema, zod_all, owner


def evaluate_cross_file_integrity(
    sources: Dict[str, str],
    *,
    entity_map: Optional[Dict[str, str]] = None,
) -> List[SymmetryViolation]:
    """Run the Prisma↔Zod symmetry check across a generated file set.

    *sources* maps file path → content for the generated batch. Returns the
    symmetry violations with :attr:`SymmetryViolation.source_file` populated
    (the ``.ts`` file declaring the offending Zod schema). Returns an empty list
    when the batch has no Prisma schema or no Zod schemas — so non-TS/Prisma
    batches incur no findings (and no false positives).
    """
    schema, zod_all, owner = scan_prisma_zod_sources(sources)
    if schema is None or not zod_all:
        return []
    findings: List[SymmetryViolation] = []
    for v in check_prisma_zod_symmetry(schema, zod_all, entity_map=entity_map):
        findings.append(dataclasses.replace(v, source_file=owner.get(v.zod_schema)))
    return findings
