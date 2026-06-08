"""Provenance-vocabulary validation against the Prisma contract (F-7).

Closes the RUN-010 D2 class — the *quietest* defect of the campaign: the
generated wizard wrote ``ownerId='default_owner'`` and ``source='wizard'``,
literals invented outside the contract's declared domains (``local``;
``user|ai``).  Everything "works", and every row the wizard creates is
silently invisible to every ``ownerId == 'local'`` filter in the app.

The contract already knows the domains:

- **Prisma enums** (``PrismaSchema.enums``) — a field typed by an enum has a
  closed value set.
- **Provenance ``String`` fields with a literal ``@default("...")``** — for
  the curated provenance field-name vocabulary (``ownerId``, ``source``, …)
  the default *is* the domain (RUN-010's ``ownerId String @default("local")``).
  Arbitrary ``String @default`` fields are NOT treated this way (a
  ``title String @default("Untitled")`` legitimately takes any value).

False-positive containment (per the F-7 ask): only string **literals** are
checked, and only in two precise positions —

1. keyword arguments in a **constructor call of a model the schema declares**
   (``Capability(source='wizard')``), matched per-model; and
2. **attribute assignments** (``obj.source = 'wizard'``), matched against the
   *union* of every declared domain for that field name across models (a
   literal outside the union is wrong no matter which model ``obj`` is).

Bare-name assignments (``source = 'wizard'`` — a local variable), dict keys,
and non-literal values are never flagged.

Emitted issues use the standard semantic-issue dict shape with category
``provenance_vocabulary`` (severity ``error``) and name the field, the
literal, and the allowed set.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

from startd8.languages.prisma_parser import PrismaSchema, parse_prisma_schema

__all__ = [
    "build_field_domains",
    "check_contract_vocabulary",
    "discover_prisma_schema",
]

# Field names that carry provenance/ownership vocabulary.  For these (and
# ONLY these) a String field's literal @default declares its domain.
_PROVENANCE_FIELD_NAMES: FrozenSet[str] = frozenset({
    "ownerId", "owner_id",
    "source",
    "provenance",
    "origin",
    "createdBy", "created_by",
})

_DEFAULT_STR_RE = re.compile(r'@default\(\s*"([^"]*)"\s*\)')

# (path, mtime_ns) → parsed schema cache
_SCHEMA_CACHE: Dict[Tuple[str, int], PrismaSchema] = {}


# ---------------------------------------------------------------------------
# Domain extraction from the contract
# ---------------------------------------------------------------------------


def build_field_domains(
    schema: PrismaSchema,
) -> Dict[str, Dict[str, Tuple[FrozenSet[str], str]]]:
    """Map ``model → field → (allowed_values, domain_source)``.

    ``domain_source`` is ``"enum:<EnumName>"`` or ``"@default"`` — used in
    violation messages so the report names where the domain comes from.
    """
    domains: Dict[str, Dict[str, Tuple[FrozenSet[str], str]]] = {}
    for model_name, model in (schema.models or {}).items():
        for fld in model.fields:
            allowed: Optional[FrozenSet[str]] = None
            source = ""
            if fld.type in schema.enums:
                allowed = frozenset(schema.enums[fld.type])
                source = f"enum:{fld.type}"
            elif fld.type == "String" and fld.name in _PROVENANCE_FIELD_NAMES:
                for attr in fld.attributes:
                    m = _DEFAULT_STR_RE.match(attr) or _DEFAULT_STR_RE.search(attr)
                    if m:
                        allowed = frozenset({m.group(1)})
                        source = "@default"
                        break
            if allowed:
                domains.setdefault(model_name, {})[fld.name] = (allowed, source)
    return domains


def _union_domains(
    domains: Dict[str, Dict[str, Tuple[FrozenSet[str], str]]],
) -> Dict[str, Tuple[FrozenSet[str], str]]:
    """Field name → union of allowed values across all models declaring it."""
    union: Dict[str, Tuple[FrozenSet[str], str]] = {}
    for per_model in domains.values():
        for field, (allowed, source) in per_model.items():
            if field in union:
                prev_allowed, prev_source = union[field]
                merged_source = (
                    prev_source if prev_source == source
                    else f"{prev_source}|{source}"
                )
                union[field] = (prev_allowed | allowed, merged_source)
            else:
                union[field] = (allowed, source)
    return union


# ---------------------------------------------------------------------------
# Schema discovery (validation-time)
# ---------------------------------------------------------------------------


def discover_prisma_schema(
    file_path: str, project_root: str,
) -> Optional[PrismaSchema]:
    """Locate and parse the contract's ``.prisma`` schema for *file_path*.

    Walks UP from the generated file's directory to *project_root* (same
    pattern as requirements discovery), checking ``schema.prisma``,
    ``prisma/schema.prisma``, then any ``*.prisma`` in each directory.
    Returns ``None`` when no schema exists (non-contract projects — the
    check is a no-op).  Parsed schemas are cached by (path, mtime).
    """
    root = Path(project_root)
    abs_path = root / file_path  # absolute file_path absorbs the join

    search_dirs: List[Path] = []
    cur = abs_path.parent
    while True:
        search_dirs.append(cur)
        if cur == root or root not in cur.parents:
            break
        cur = cur.parent
    if root not in search_dirs:
        search_dirs.append(root)

    schema_file: Optional[Path] = None
    for d in search_dirs:
        for cand in (d / "schema.prisma", d / "prisma" / "schema.prisma"):
            if cand.is_file():
                schema_file = cand
                break
        if schema_file is None:
            try:
                globbed = sorted(d.glob("*.prisma"))
            except OSError:
                globbed = []
            if globbed:
                schema_file = globbed[0]
        if schema_file is not None:
            break
    if schema_file is None:
        return None

    try:
        key = (str(schema_file), schema_file.stat().st_mtime_ns)
    except OSError:
        return None
    cached = _SCHEMA_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        schema = parse_prisma_schema(schema_file.read_text(encoding="utf-8"))
    except OSError:
        return None
    _SCHEMA_CACHE[key] = schema
    return schema


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def _callee_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _str_literal(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def check_contract_vocabulary(
    tree: ast.AST,
    schema: PrismaSchema,
    file_path: Optional[str] = None,
) -> List[Dict[str, object]]:
    """Scan generated Python for literals outside the contract's domains.

    The RUN-010 shape: ``Capability(source='wizard', ownerId='default_owner')``
    where the contract says ``source ∈ {user, ai}`` and
    ``ownerId String @default("local")``.
    """
    issues: List[Dict[str, object]] = []
    domains = build_field_domains(schema)
    if not domains:
        return issues
    union = _union_domains(domains)

    def _emit(field: str, literal: str, allowed: FrozenSet[str],
              source: str, context: str, line: int) -> None:
        issues.append({
            "category": "provenance_vocabulary",
            "severity": "error",
            "message": (
                f"{context}: field '{field}' assigned literal '{literal}' "
                f"outside the contract's declared domain "
                f"{sorted(allowed)} (from {source}) — rows written with "
                f"invented vocabulary are silently invisible to every "
                f"filter on the declared values"
            ),
            "line": line,
            "symbol": f"{field}={literal!r}",
            "field": field,
            "literal": literal,
            "allowed": sorted(allowed),
        })

    for node in ast.walk(tree):
        # 1. Model constructor keyword arguments — per-model domains.
        if isinstance(node, ast.Call):
            model_name = _callee_name(node.func)
            model_domains = domains.get(model_name)
            if not model_domains:
                continue
            for kw in node.keywords:
                if kw.arg is None or kw.arg not in model_domains:
                    continue
                literal = _str_literal(kw.value)
                if literal is None:
                    continue
                allowed, source = model_domains[kw.arg]
                if literal not in allowed:
                    _emit(
                        kw.arg, literal, allowed, source,
                        f"{model_name}(...)", node.lineno,
                    )

        # 2. Attribute assignments — union domain across models.
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            literal = _str_literal(getattr(node, "value", None)) if node.value else None
            if literal is None:
                continue
            for target in targets:
                if not isinstance(target, ast.Attribute):
                    continue  # bare names are local variables — never flagged
                field = target.attr
                if field not in union:
                    continue
                allowed, source = union[field]
                if literal not in allowed:
                    _emit(
                        field, literal, allowed, source,
                        "attribute assignment", node.lineno,
                    )

    if file_path:
        for issue in issues:
            issue["file"] = file_path
    return issues
