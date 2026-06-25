"""Map introspected facts → ``manifest_extraction.EntityGraph`` (derive-contract Step 2).

The deterministic transform (FR-DC-5, verified against navig8). The back half — emitting the
``.prisma`` — is the existing ``render_prisma_schema(graph)`` (Step 3), unchanged: derive-contract
feeds the same IR the markdown path feeds. The mapper is pure and **canonically ordered** (FR-DC-2:
entities in model-definition order, fields in ``model_fields`` order, enums alpha-sorted by the
emitter) so the same models always yield the same graph.

House meta-fields (`id`/`ownerId`/`source`/`confirmed`/`createdAt`/`updatedAt`) are injected by the
emitter's bookkeeping — the mapper never emits them. Relations are expressed via ``fk_parents`` /
``joins`` (the emitter renders the FK scalar + ``@relation`` + reverse list); the mapper does not
emit relation fields directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from startd8.logging_config import get_logger
from startd8.manifest_extraction.entities import (
    DocEntity,
    DocField,
    EntityGraph,
    JoinModel,
    _lower_camel,
)

from .introspect import (
    KIND_DICT,
    KIND_ENUM,
    KIND_LIST_MODEL,
    KIND_LIST_SCALAR,
    KIND_MARKED_JOIN,
    KIND_NESTED_MODEL,
    KIND_SCALAR,
    EntityFact,
    FieldFact,
    IntrospectionResult,
)

logger = get_logger(__name__)

SCHEMA_VERSION = 1

# Python scalar token → Prisma scalar (FR-DC-5). Unknown → unrenderable (the emitter flags it).
_PRISMA_SCALAR = {
    "str": "String", "int": "Int", "bool": "Boolean", "float": "Float",
    "datetime": "DateTime", "date": "DateTime", "time": "DateTime",
    "decimal": "Decimal", "uuid": "String", "bytes": "Bytes", "any": "Json",
}
# Auto-injected by the emitter; a domain field colliding with one of these is flagged.
_HOUSE_FIELDS = {"id", "ownerId", "source", "confirmed", "createdAt", "updatedAt"}


@dataclass
class DerivationReport:
    """The Architect's review surface (FR-DC-7): what was transformed, excluded, and flagged."""

    schema_version: int = SCHEMA_VERSION
    transforms: List[Dict[str, Any]] = field(default_factory=list)
    exclusions: List[Dict[str, Any]] = field(default_factory=list)
    flags: List[Dict[str, Any]] = field(default_factory=list)
    joins: List[str] = field(default_factory=list)


def _join_name(a: str, b: str) -> str:
    left, right = sorted((a, b))
    return f"{left}{right}"


def _add_join(graph: EntityGraph, a: str, b: str, report: DerivationReport) -> None:
    left, right = sorted((a, b))
    if graph.join_between(left, right) is not None:
        return
    name = _join_name(left, right)
    graph.joins.append(JoinModel(name=name, left=left, right=right))
    report.joins.append(name)
    report.transforms.append({"rule": "m2m-join", "left": left, "right": right, "model": name})


def build_entity_graph(result: IntrospectionResult) -> Tuple[EntityGraph, DerivationReport]:
    """Deterministically map *result* → (EntityGraph, DerivationReport)."""
    g = EntityGraph()
    report = DerivationReport(flags=list(result.flags))

    # 1. enums (FR-DC-5 normalization already applied in introspection).
    for ef in result.enums:
        g.enums[ef.name] = ef.normalized
        if ef.needs_normalization:
            report.transforms.append({
                "rule": "enum-hyphen-normalize", "enum": ef.name,
                "from": list(ef.values), "to": list(ef.normalized),
            })

    # 2. relations → fk_parents / joins (the emitter renders FK + @relation + reverse list).
    for ent in result.entities:
        for f in ent.fields:
            if f.kind == KIND_LIST_MODEL and f.ref_model:
                # parent has List[Child] → CHILD carries the FK to this (parent) entity.
                g.fk_parents.setdefault(f.ref_model, []).append(ent.name)
                report.transforms.append({"rule": "1:N", "parent": ent.name, "child": f.ref_model, "via": f.name})
            elif f.kind == KIND_NESTED_MODEL and f.ref_model:
                # this entity holds a single ref → it is the CHILD of the referenced model.
                g.fk_parents.setdefault(ent.name, []).append(f.ref_model)
                report.transforms.append({"rule": "FK", "child": ent.name, "parent": f.ref_model, "via": f.name})
            elif f.kind == KIND_MARKED_JOIN and f.join_target:
                _add_join(g, ent.name, f.join_target, report)

    # 3. entity DocFields + semantic key + uniques.
    for ent in result.entities:
        parents = g.fk_parents.get(ent.name, [])
        parent_fk = f"{_lower_camel(parents[0])}Id" if parents else None
        docfields: List[DocField] = []
        row = 0
        for f in ent.fields:
            if f.kind in (KIND_LIST_MODEL, KIND_NESTED_MODEL, KIND_MARKED_JOIN):
                continue  # rendered from fk_parents/joins
            df = _to_docfield(ent, f, row, g, parent_fk, report)
            if df is not None:
                docfields.append(df)
                row += 1
        g.entities[ent.name] = DocEntity(name=ent.name, fields=tuple(docfields), heading_path=())
        for cname in ent.computed_excluded:
            report.exclusions.append({"entity": ent.name, "field": cname,
                                      "reason": "computed_field/@property — derived, not stored"})

    return g, report


def _to_docfield(
    ent: EntityFact, f: FieldFact, row: int, g: EntityGraph,
    parent_fk: Optional[str], report: DerivationReport,
) -> Optional[DocField]:
    def mk(name: str, plain: str, prisma: Optional[str], required: bool,
           default: Any = None) -> DocField:
        if name in _HOUSE_FIELDS:
            report.flags.append({"entity": ent.name, "field": name,
                                 "reason": f"field name collides with an auto-injected house field {name!r}"})
        return DocField(name=name, plain_type=plain, prisma_type=prisma, required=required,
                        notes="", human_only=False, row_index=row, default=default)

    # explicit `id: str` → <entity>Key + @@unique([parentFk, key]) (FR-DC-4).
    if f.name == "id" and ent.has_explicit_id:
        keyname = f"{_lower_camel(ent.name)}Key"
        if parent_fk:
            g.uniques.setdefault(ent.name, []).append((parent_fk, keyname))
            report.transforms.append({"rule": "semantic-key", "entity": ent.name,
                                      "key": keyname, "unique": [parent_fk, keyname]})
        else:
            report.flags.append({"entity": ent.name, "field": keyname,
                                 "reason": "semantic key has no parent FK — confirm uniqueness scope"})
            report.transforms.append({"rule": "semantic-key", "entity": ent.name, "key": keyname})
        return mk(keyname, "string", "String", True)

    if f.kind == KIND_ENUM:
        default = None
        if f.has_default and isinstance(f.default, str):
            default = f.default.replace("-", "_")  # match the normalized enum values
        elif f.has_default:
            default = f.default
        return mk(f.name, "enum", f.enum_name, f.required, default)

    if f.kind in (KIND_LIST_SCALAR, KIND_DICT):
        return mk(f.name, "json", "Json", required=False)   # Json? (nullable JSON column)

    if f.kind == KIND_SCALAR:
        prisma = _PRISMA_SCALAR.get(f.scalar_token or "")
        if prisma is None:
            report.exclusions.append({"entity": ent.name, "field": f.name,
                                      "reason": f"unmapped scalar token {f.scalar_token!r} → flagged"})
            return mk(f.name, f.scalar_token or "?", None, f.required)  # emitter marks unrenderable
        default = None
        if f.has_default and not f.default_factory and f.default is not None:
            if prisma == "Boolean" and isinstance(f.default, bool):
                default = "true" if f.default else "false"
            else:
                default = str(f.default)
        return mk(f.name, f.scalar_token, prisma, f.required, default)

    # KIND_UNKNOWN
    report.exclusions.append({"entity": ent.name, "field": f.name,
                              "reason": "unmapped annotation → flagged for review"})
    return mk(f.name, "?", None, f.required)
