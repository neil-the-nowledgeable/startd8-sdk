"""FR-IMP-1: the ``from_json`` import owned-kind — the deterministic inverse of ``render_export``.

``app/export.py`` projects rows → a lossless JSON payload (``to_json``, ``default=str``). This module
emits ``app/import.py``: ``from_json(text, session, *, strict=True)`` parses that payload back into
rows and **upserts** them, honoring the FR-IMP-2 identity key per entity, never clobbering a confirmed
row or the human-owned provenance field, and coercing the ``default=str``-lossy scalar types
(DateTime/Decimal/…) back to their declared Python types.

Two inputs → two-hash drift (schema + ``imports.yaml``), the ``forms``/``pages`` precedent. The
identity/provenance per entity come from ``imports.yaml`` (:mod:`imports_manifest`); entities with no
declared import spec default to **id** upsert (a faithful round-trip of the export, which carries
``id``). Gate discipline mirrors FR-PE-6: structured :class:`ImportResult` + ``strict`` (whole-file
atomic, default) vs ``--allow-lossy`` (per-row savepoint, skip+report bad rows).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..frontend_codegen.schema_renderer import composite_type_names, schema_sha256
from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema
from ._headers import header_imports
from .imports_manifest import ImportSpec, parse_imports

IMPORT_KINDS = frozenset({"python-import"})

# Prisma scalar → coercion tag for the generated ``_coerce`` (only non-str-native types need it;
# ``to_json`` stringifies datetime/Decimal via ``default=str``, and int/float/bool may arrive as
# strings from a hand-edited payload, so we coerce them defensively too).
_COERCE_TAG = {
    "Int": "int",
    "BigInt": "int",
    "Float": "float",
    "Decimal": "decimal",
    "Boolean": "bool",
    "DateTime": "datetime",
}

_SERVER_PK = "id"


def _model_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    composites = composite_type_names(schema_text)
    return [n for n in schema.models if n not in composites]


def _fk_parents(schema: PrismaSchema, name: str) -> List[str]:
    """Models *name* holds a foreign key TO (the side carrying ``@relation(fields: …)``)."""
    model = schema.model(name)
    if model is None:
        return []
    parents: List[str] = []
    for f in model.fields:
        if not schema.is_relation_field(f):
            continue
        # the FK-holding side declares `@relation(fields: [...], references: [...])`
        if any("fields:" in a for a in f.attributes) and f.type in schema.models:
            if f.type not in parents:
                parents.append(f.type)
    return parents


def _import_order(schema: PrismaSchema, names: List[str]) -> List[str]:
    """Topological order — a parent is imported before any child that holds an FK to it.

    Deterministic (Kahn's algorithm over schema-ordered nodes). A cycle (mutually-referential FKs)
    falls back to schema order for the remaining nodes — import still runs; FK inserts in a cycle
    are the caller's data problem, surfaced as per-row errors, not a generation failure.
    """
    deps: Dict[str, set] = {n: set(p for p in _fk_parents(schema, n) if p in names) for n in names}
    order: List[str] = []
    placed = set()
    # iterate in schema order repeatedly, placing any node whose deps are all placed (stable).
    progress = True
    while progress and len(order) < len(names):
        progress = False
        for n in names:
            if n in placed:
                continue
            if deps[n] <= placed:
                order.append(n)
                placed.add(n)
                progress = True
    for n in names:  # cycle remainder — append in schema order
        if n not in placed:
            order.append(n)
    return order


def _coerce_map(schema: PrismaSchema, names: List[str]) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for n in names:
        tags = {
            f.name: _COERCE_TAG[f.type]
            for f in schema.scalar_fields(n)
            if f.type in _COERCE_TAG
        }
        if tags:
            out[n] = dict(sorted(tags.items()))
    return out


def _identity_map(
    names: List[str], specs: Dict[str, ImportSpec]
) -> Tuple[Dict[str, dict], Dict[str, Optional[str]]]:
    """``(identity_descriptor_by_entity, provenance_by_entity)`` baked into the generated module."""
    identity: Dict[str, dict] = {}
    provenance: Dict[str, Optional[str]] = {}
    for n in names:
        spec = specs.get(n)
        if spec is not None:
            key = spec.identity
            if key.kind == "source":
                identity[n] = {"kind": "source", "provenance": key.provenance}
            elif key.kind == "id":
                identity[n] = {"kind": "id", "fields": ["id"]}
            elif key.kind in ("field", "composite", "name"):
                identity[n] = {"kind": key.kind, "fields": list(key.fields)}
            else:  # none
                identity[n] = {"kind": "none", "fields": []}
            provenance[n] = spec.provenance
        else:
            identity[n] = {"kind": "id", "fields": ["id"]}  # default: faithful round-trip by PK
            provenance[n] = None
    return identity, provenance


def _py(obj) -> str:
    """Deterministic single-line Python literal (sorted dict keys, stable across runs)."""
    if isinstance(obj, dict):
        return "{" + ", ".join(f"{_py(k)}: {_py(v)}" for k, v in sorted(obj.items())) + "}"
    if isinstance(obj, list):
        return "[" + ", ".join(_py(v) for v in obj) + "]"
    return repr(obj)


def render_import(
    schema_text: str,
    imports_text: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> str:
    """Render ``app/import.py`` — ``from_json`` upsert importer (FR-IMP-1).

    *imports_text* (``imports.yaml``) refines the per-entity identity/provenance; absent ⇒ every
    entity defaults to id-upsert. The file is still emitted (a full payload can be imported even with
    no manifest) — the manifest only tunes identity, provenance protection, and the surface (Phase 4).
    """
    schema = parse_prisma_schema(schema_text)
    names = _model_names(schema, schema_text)
    schema_sha = schema_sha256(schema_text)
    imports_sha = schema_sha256(imports_text or "")

    specs = {s.entity: s for s in parse_imports(imports_text, known_entities=frozenset(names))}
    identity, provenance = _identity_map(names, specs)
    coerce = _coerce_map(schema, names)
    order = _import_order(schema, names)

    header = header_imports(source_file, schema_sha, imports_sha, "python-import")
    body = _BODY_TEMPLATE.format(
        import_order=_py(order),
        identity=_py(identity),
        provenance=_py(provenance),
        coerce=_py(coerce),
    )
    return header + "\n\n" + body


# The runtime is fixed-shape; only the four baked constants vary by contract. Kept as a module-level
# template so the generated bytes are stable and the logic is reviewable in one place.
_BODY_TEMPLATE = '''from __future__ import annotations

import json
from dataclasses import dataclass, field as _field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.export import ENTITY_ORDER, FIELDS
from app import tables

# Parent-before-child FK order (Kahn over the schema FKs); identity/provenance/coercion are baked
# from the schema + imports.yaml (FR-IMP-1/2).
IMPORT_ORDER: List[str] = {import_order}
_IDENTITY: Dict[str, Dict[str, Any]] = {identity}
_PROVENANCE: Dict[str, Optional[str]] = {provenance}
_COERCE: Dict[str, Dict[str, str]] = {coerce}

# Never set from a payload on UPDATE — preserving the PK and (separately) the human-owned provenance
# field is the import-unique non-clobber rule (FR-IMP-5). On INSERT the payload's values are honored.
_PK = "id"


@dataclass
class ImportResult:
    """Structured outcome (the FR-PE-6 fail-loud posture, import-side)."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = _field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (
            f"created={{self.created}} updated={{self.updated}} "
            f"skipped={{self.skipped}} errors={{len(self.errors)}}"
        )


def _coerce(entity: str, name: str, value: Any) -> Any:
    """Coerce a ``default=str``-stringified value back to its declared type (DateTime/Decimal/…)."""
    tag = _COERCE.get(entity, {{}}).get(name)
    if value is None or tag is None:
        return value
    try:
        if tag == "int":
            return int(value)
        if tag == "float":
            return float(value)
        if tag == "bool":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {{"true", "1", "yes"}}
        if tag == "datetime":
            return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if tag == "decimal":
            return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError(f"field {{name!r}}: cannot coerce {{value!r}} to {{tag}} ({{exc}})") from exc
    return value


def _row_fields(entity: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """The writable, type-coerced columns of *row* (export's FIELDS = the schema scalars)."""
    if not isinstance(row, dict):
        raise ValueError("row is not a JSON object")
    allowed = FIELDS.get(entity, [])
    return {{f: _coerce(entity, f, row[f]) for f in allowed if f in row}}


def _find_existing(session: Session, entity: str, model: Any, fields: Dict[str, Any]):
    """The row this payload row upserts onto, per the entity's identity key — or None (insert)."""
    ident = _IDENTITY.get(entity, {{"kind": "id", "fields": [_PK]}})
    kind = ident["kind"]
    if kind == "none":
        return None
    if kind == "source":
        col = ident["provenance"]
        val = fields.get(col)
        if val is None or not hasattr(model, col):
            return None
        return session.exec(select(model).where(getattr(model, col) == val)).first()
    keys = ident.get("fields") or [_PK]
    conds = []
    for k in keys:
        if k not in fields or not hasattr(model, k):
            return None  # can't key on a column the payload/model lacks → treat as insert
        conds.append(getattr(model, k) == fields[k])
    stmt = select(model)
    for c in conds:
        stmt = stmt.where(c)
    return session.exec(stmt).first()


def _import_row(session: Session, entity: str, model: Any, row: Dict[str, Any]) -> str:
    """Upsert one row; returns 'created' | 'updated' | 'skipped'. Raises on a bad row."""
    fields = _row_fields(entity, row)
    existing = _find_existing(session, entity, model, fields)
    prov = _PROVENANCE.get(entity)
    if existing is not None:
        if getattr(existing, "confirmed", False):
            return "skipped"  # never clobber a user-confirmed row (FR-8 parity)
        for k, v in fields.items():
            if k == _PK or k == prov:
                continue  # preserve the PK and the human-owned provenance field (FR-IMP-5)
            if hasattr(existing, k):
                setattr(existing, k, v)
        session.add(existing)
        session.flush()
        return "updated"
    obj = model(**{{k: v for k, v in fields.items() if hasattr(model, k)}})
    session.add(obj)
    session.flush()  # surface constraint errors here so the savepoint can isolate them
    return "created"


def from_json(text: str, session: Session, *, strict: bool = True) -> ImportResult:
    """Import a lossless export payload (the ``to_json`` inverse). Upserts by each entity's identity.

    ``strict`` (default) — whole-file atomic: one outer transaction; the first bad row rolls back
    EVERYTHING and returns the error; nothing is persisted. ``strict=False`` (``--allow-lossy``) —
    per-row savepoint: a bad row is skipped and reported, good rows commit. Either way the structured
    :class:`ImportResult` names every failure (FR-PE-6 fail-loud, import-side)."""
    result = ImportResult()
    try:
        payload = json.loads(text)
    except (ValueError, TypeError) as exc:
        result.errors.append(f"invalid JSON: {{exc}}")
        return result
    if not isinstance(payload, dict):
        result.errors.append("payload must be a JSON object of entity -> [rows]")
        return result

    for entity in IMPORT_ORDER:
        model = getattr(tables, entity, None)
        rows = payload.get(entity) or []
        if model is None or not isinstance(rows, list):
            continue
        for i, row in enumerate(rows):
            if strict:
                # No per-row savepoint: a single outer transaction so session.rollback() undoes
                # the whole file (a *released* savepoint survives a later rollback — SQLAlchemy).
                try:
                    outcome = _import_row(session, entity, model, row)
                    setattr(result, outcome, getattr(result, outcome) + 1)
                except Exception as exc:  # noqa: BLE001
                    session.rollback()
                    result.created = result.updated = result.skipped = 0  # nothing persisted
                    result.errors.append(f"{{entity}}[{{i}}]: {{exc}} (rolled back — strict)")
                    return result
            else:
                sp = session.begin_nested()  # isolate the row so one bad row can't abort the batch
                try:
                    outcome = _import_row(session, entity, model, row)
                    sp.commit()
                    setattr(result, outcome, getattr(result, outcome) + 1)
                except Exception as exc:  # noqa: BLE001 — one bad row, captured not raised
                    sp.rollback()
                    result.errors.append(f"{{entity}}[{{i}}]: {{exc}}")
    session.commit()
    return result


__all__ = ["ImportResult", "from_json"]
'''
