"""Pydantic model introspection → normalized facts (derive-contract Step 1).

Pure, in-process logic (OQ-2: runtime introspection — Pydantic's `model_fields` carries
`is_required`/defaults/computed markers that static AST can't see). Produces an
``IntrospectionResult`` the Step-2 mapper turns into an ``EntityGraph``. **No disk writes, no
network, $0** (FR-DC-2). The security containment that *runs* this against an untrusted target
lives in ``containment.py`` (FR-DC-14); this module is import-safe to call directly on
trusted/in-test models.

Field classification (FR-DC-5, verified against navig8):
    scalar · enum · nested_model (→FK) · list_model (→1:N) · list_scalar (→Json) · dict (→Json)
    · marked_join (FR-DC-12 model-side hint). `@computed_field`/`@property` are dropped (recorded).
    An unmarked ``list[str]`` is `list_scalar` **plus a flag** (could be an M2M join or loose refs
    — FR-DC-8: flag for the human, never silently guess).
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel

from startd8.logging_config import get_logger

logger = get_logger(__name__)

SCHEMA_VERSION = 1

# Field kinds (the Step-2 mapper switches on these).
KIND_SCALAR = "scalar"
KIND_ENUM = "enum"
KIND_NESTED_MODEL = "nested_model"   # → FK
KIND_LIST_MODEL = "list_model"       # → 1:N (parent reverse list + child FK)
KIND_LIST_SCALAR = "list_scalar"     # → Json
KIND_DICT = "dict"                   # → Json
KIND_MARKED_JOIN = "marked_join"     # → M2M join model (FR-DC-12 explicit hint)
KIND_UNKNOWN = "unknown"             # unmapped annotation → flagged

# Python scalar → token (Step 2 maps token → Prisma scalar). Unknown → flagged.
_SCALAR_TOKENS = {
    str: "str", int: "int", bool: "bool", float: "float", bytes: "bytes",
}
_SCALAR_BY_NAME = {  # types we don't want to hard-import at module load
    "datetime": "datetime", "date": "date", "time": "time",
    "Decimal": "decimal", "UUID": "uuid", "Any": "any",
}


class DeriveError(RuntimeError):
    """Base error for derive-contract."""


class DeriveImportError(DeriveError):
    """The target models could not be imported/introspected — fail-closed (FR-DC-14)."""


@dataclass
class FieldFact:
    name: str
    kind: str
    required: bool
    optional: bool = False
    has_default: bool = False
    default: Any = None            # JSON-safe rendering (scalars passthrough, Enum→value)
    default_factory: bool = False
    scalar_token: Optional[str] = None   # kind=scalar / list_scalar element
    enum_name: Optional[str] = None      # kind=enum
    ref_model: Optional[str] = None      # kind=nested_model / list_model
    join_target: Optional[str] = None    # kind=marked_join (FR-DC-12)


@dataclass
class EntityFact:
    name: str
    module: str
    fields: List[FieldFact] = field(default_factory=list)
    has_explicit_id: bool = False        # an explicit `id` field → <entity>Key (FR-DC-4 signal)
    computed_excluded: List[str] = field(default_factory=list)  # @computed_field/@property dropped


@dataclass
class EnumFact:
    name: str
    values: Tuple[str, ...]
    normalized: Tuple[str, ...]          # hyphen→underscore (illegal Prisma identifiers)
    needs_normalization: bool = False


@dataclass
class IntrospectionResult:
    schema_version: int
    entities: List[EntityFact] = field(default_factory=list)
    enums: List[EnumFact] = field(default_factory=list)
    imported_modules: List[str] = field(default_factory=list)   # FR-DC-10 report
    flags: List[Dict[str, str]] = field(default_factory=list)   # FR-DC-8 ambiguities
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntrospectionResult":
        return cls(
            schema_version=data["schema_version"],
            entities=[
                EntityFact(
                    name=e["name"], module=e["module"], has_explicit_id=e["has_explicit_id"],
                    computed_excluded=list(e.get("computed_excluded", [])),
                    fields=[FieldFact(**f) for f in e["fields"]],
                )
                for e in data.get("entities", [])
            ],
            enums=[
                EnumFact(name=en["name"], values=tuple(en["values"]),
                         normalized=tuple(en["normalized"]), needs_normalization=en["needs_normalization"])
                for en in data.get("enums", [])
            ],
            imported_modules=list(data.get("imported_modules", [])),
            flags=list(data.get("flags", [])),
            warnings=list(data.get("warnings", [])),
        )


# ── annotation analysis ──────────────────────────────────────────────────────

def _unwrap_optional(ann: Any) -> Tuple[Any, bool]:
    """Return (inner, is_optional) — strips a single ``... | None`` / ``Optional[...]``."""
    origin = typing.get_origin(ann)
    if origin is typing.Union or origin is getattr(types, "UnionType", ()):
        args = typing.get_args(ann)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0], len(non_none) != len(args)
        return ann, len(non_none) != len(args)  # multi-type union: leave as-is, note optionality
    return ann, False


def _scalar_token(tp: Any) -> Optional[str]:
    if tp in _SCALAR_TOKENS:
        return _SCALAR_TOKENS[tp]
    if tp is Any:
        return "any"
    name = getattr(tp, "__name__", None)
    return _SCALAR_BY_NAME.get(name)


def _is_model(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _is_enum(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, enum.Enum)


def _classify(name: str, inner: Any) -> Tuple[str, Dict[str, Any], Optional[str]]:
    """Return (kind, extra_fields, flag_reason_or_None) for a non-optional annotation."""
    origin = typing.get_origin(inner)
    if origin in (list, set, frozenset, tuple) or inner in (list, set):
        args = typing.get_args(inner)
        elem = args[0] if args else Any
        if _is_model(elem):
            return KIND_LIST_MODEL, {"ref_model": elem.__name__}, None
        tok = _scalar_token(elem)
        flag = None
        if elem is str:
            # list[str] is genuinely ambiguous: loose refs / M2M join / a plain string array.
            flag = "unmarked list[str] → Json by default; could be an M2M join or loose refs — mark to confirm (FR-DC-12)"
        return KIND_LIST_SCALAR, {"scalar_token": tok or "any"}, flag
    if origin in (dict,) or inner is dict:
        return KIND_DICT, {}, None
    if _is_enum(inner):
        return KIND_ENUM, {"enum_name": inner.__name__}, None
    if _is_model(inner):
        return KIND_NESTED_MODEL, {"ref_model": inner.__name__}, None
    tok = _scalar_token(inner)
    if tok is None:
        return KIND_UNKNOWN, {}, f"field '{name}': unmapped annotation {inner!r} → flagged for review"
    return KIND_SCALAR, {"scalar_token": tok}, None


def _join_marker(field_info: Any) -> Optional[str]:
    """FR-DC-12 model-side hint: ``Field(json_schema_extra={'prisma': {'join': 'Target'}})``."""
    extra = getattr(field_info, "json_schema_extra", None)
    if isinstance(extra, dict):
        prisma = extra.get("prisma")
        if isinstance(prisma, dict) and "join" in prisma:
            return str(prisma["join"])
    return None


def _render_default(field_info: Any) -> Tuple[bool, Any, bool]:
    """(has_default, json_safe_default, is_factory)."""
    if getattr(field_info, "default_factory", None) is not None:
        return True, None, True
    default = getattr(field_info, "default", None)
    # Pydantic's "no default" sentinel is PydanticUndefined; is_required() captures it.
    if field_info.is_required():
        return False, None, False
    if isinstance(default, enum.Enum):
        return True, default.value, False
    if isinstance(default, (str, int, float, bool)) or default is None:
        return True, default, False
    return True, repr(default), False


# ── public API ───────────────────────────────────────────────────────────────

def introspect_models(models: List[Type[BaseModel]]) -> IntrospectionResult:
    """Introspect *models* (explicit list) into normalized facts. Pure; no I/O."""
    result = IntrospectionResult(schema_version=SCHEMA_VERSION)
    enum_facts: Dict[str, EnumFact] = {}
    seen_modules: List[str] = []

    for model in models:
        if not _is_model(model):
            result.warnings.append(f"skipped non-BaseModel: {model!r}")
            continue
        mod = getattr(model, "__module__", "")
        if mod not in seen_modules:
            seen_modules.append(mod)
        ent = EntityFact(name=model.__name__, module=mod, has_explicit_id="id" in model.model_fields)
        for fname, finfo in model.model_fields.items():
            inner, is_opt = _unwrap_optional(finfo.annotation)
            join = _join_marker(finfo)
            has_def, default, is_factory = _render_default(finfo)
            if join is not None:
                kind, extra, flag = KIND_MARKED_JOIN, {"join_target": join}, None
            else:
                kind, extra, flag = _classify(fname, inner)
            if flag:
                result.flags.append({"entity": model.__name__, "field": fname, "reason": flag})
            ff = FieldFact(
                name=fname, kind=kind, required=finfo.is_required(), optional=is_opt,
                has_default=has_def, default=default, default_factory=is_factory, **extra,
            )
            ent.fields.append(ff)
            if kind == KIND_ENUM:
                _collect_enum(inner, enum_facts)
        # @computed_field (and bare @property) are not stored columns — record, don't emit.
        for cname in getattr(model, "model_computed_fields", {}):
            ent.computed_excluded.append(cname)
        result.entities.append(ent)

    result.enums = list(enum_facts.values())
    result.imported_modules = seen_modules
    return result


def _collect_enum(enum_cls: Any, into: Dict[str, EnumFact]) -> None:
    if enum_cls.__name__ in into:
        return
    values = tuple(str(e.value) for e in enum_cls)
    normalized = tuple(v.replace("-", "_") for v in values)
    into[enum_cls.__name__] = EnumFact(
        name=enum_cls.__name__, values=values, normalized=normalized,
        needs_normalization=values != normalized,
    )


def resolve_models(module_name: str, only: Optional[List[str]] = None) -> List[Type[BaseModel]]:
    """Import *module_name* and return its **own-defined** BaseModel subclasses (FR-DC-3:
    explicit-only — a model merely imported into the module is excluded by the ``__module__``
    check). ``only`` restricts to the named classes. Raises on import failure (fail-closed)."""
    import importlib

    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 — fail-closed; the caller maps to DeriveImportError
        raise DeriveImportError(f"could not import target module {module_name!r}: {exc}") from exc

    out: List[Type[BaseModel]] = []
    for name, obj in vars(mod).items():
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == module_name        # own-defined, not imported (FR-DC-3)
            and (only is None or name in only)
        ):
            out.append(obj)
    return out
