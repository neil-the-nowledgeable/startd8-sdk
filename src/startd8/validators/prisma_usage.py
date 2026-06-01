"""Prisma client-usage validation against the schema — RUN-009 Approach-B signatures.

Toolchain-free classifier signatures for the **canonical-schema** failure class
(5 of run-009's 16 cross-file failures):

- **Unknown field at a call site** — `db.<model>.{create,update,where,…}({ … })`
  uses a key that is not a field of the Prisma model (run-009: `inputTokens`/
  `outputTokens` vs `promptTokens`/`responseTokens`; invented `claim`/`category`).
- **Invalid `where` selector** — `findUnique`/`upsert` (and `update`/`delete`)
  `where` must select by an `@unique`/`@id` column or a valid `@@unique`/`@@id`
  compound (run-009: `where: { ownerId }` on a non-unique column; `id_ownerId`
  compound that the model doesn't declare).

Parses the active `prisma/schema.prisma` via :mod:`prisma_parser` and the TS call
sites with a brace-matching scan — no Node/Prisma toolchain required, so it fires
even on an unprovisioned run (the tsc gate, FR-4, covers the same ground only when
provisioned).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema

_TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_CALL_RE = re.compile(
    r"\b(?:db|prisma)\s*\.\s*(?P<model>\w+)\s*\.\s*(?P<method>"
    r"create|createMany|update|updateMany|upsert|findUnique|findUniqueOrThrow|"
    r"findFirst|findFirstOrThrow|delete|deleteMany|count|aggregate|findMany|groupBy)\s*\("
)
_UNIQUE_WHERE_METHODS = frozenset({"findUnique", "findUniqueOrThrow", "upsert", "update", "delete"})
_WHERE_OPERATORS = frozenset({"AND", "OR", "NOT"})
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


@dataclass(frozen=True)
class PrismaUsageViolation:
    """Shape-compatible with the postmortem's cross-file attribution loop."""

    kind: str          # prisma_unknown_field | prisma_where_not_unique | prisma_invalid_compound_key
    source_file: str
    field: str
    detail: str
    severity: str = "error"


def _match_brace(text: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _top_level_keys(body: str) -> List[str]:
    """Identifiers used as `key:` at brace-depth 0 of an object-literal body."""
    keys: List[str] = []
    depth = 0
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c in "{[(":
            depth += 1
            i += 1
        elif c in "}])":
            depth -= 1
            i += 1
        elif c in "\"'`":
            q = c
            i += 1
            while i < n and body[i] != q:
                if body[i] == "\\":
                    i += 1
                i += 1
            i += 1
        elif depth == 0 and (c.isalpha() or c == "_"):
            m = _IDENT_RE.match(body, i)
            ident = m.group(0)
            j = m.end()
            k = j
            while k < n and body[k] in " \t\n\r":
                k += 1
            if k < n and body[k] == ":":
                keys.append(ident)
                i = k + 1
            else:
                i = j
        else:
            i += 1
    return keys


def _sub_object_body(arg_body: str, key: str) -> Optional[str]:
    m = re.search(r"\b" + re.escape(key) + r"\s*:\s*\{", arg_body)
    if not m:
        return None
    open_idx = arg_body.index("{", m.end() - 1)
    close = _match_brace(arg_body, open_idx)
    return arg_body[open_idx + 1:close]


def _load_schema(sources: Dict[str, str], project_root: str) -> Optional[PrismaSchema]:
    text = "\n".join(c for p, c in sources.items() if p.endswith(".prisma"))
    if not text.strip():
        candidate = Path(project_root) / "prisma" / "schema.prisma"
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                return None
    if not text.strip():
        return None
    schema = parse_prisma_schema(text)
    return schema if schema.models else None


def scan_prisma_usage(sources: Dict[str, str], project_root: str) -> List[PrismaUsageViolation]:
    schema = _load_schema(sources, project_root)
    if schema is None:
        return []
    accessor = {name[:1].lower() + name[1:]: name for name in schema.models}

    from .prisma_zod_symmetry import _strip_ts_comments

    out: List[PrismaUsageViolation] = []
    for path, raw in sources.items():
        if not path.endswith(_TS_EXTS):
            continue
        # Strip comments so a `// CRITICAL: ...` note isn't mis-parsed as an
        # object key, and a `/* ... */` block can't unbalance brace matching.
        content = _strip_ts_comments(raw)
        for m in _CALL_RE.finditer(content):
            model_name = accessor.get(m.group("model"))
            model = schema.model(model_name) if model_name else None
            if model is None:
                continue
            method = m.group("method")
            paren = content.find("(", m.end() - 1)
            br = content.find("{", paren)
            if paren == -1 or br == -1 or content[paren + 1:br].strip():
                continue  # arg is not an inline object literal
            arg_body = content[br + 1:_match_brace(content, br)]

            field_names = model.field_names
            compounds = {"_".join(c) for c in model.compound_unique_keys}
            uniques = model.single_column_unique_keys

            # where selector
            where_body = _sub_object_body(arg_body, "where")
            if where_body is not None:
                for key in _top_level_keys(where_body):
                    if key in _WHERE_OPERATORS or key in compounds:
                        continue
                    if key in field_names:
                        if method in _UNIQUE_WHERE_METHODS and key not in uniques:
                            out.append(PrismaUsageViolation(
                                kind="prisma_where_not_unique", source_file=path, field=key,
                                detail=(f"`{path}`: `{model_name}.{method}` selects by `{key}`, "
                                        f"which is not @unique/@id (unique-where required)"),
                            ))
                        continue
                    # not a field, operator, or valid compound
                    if "_" in key and all(p in field_names for p in key.split("_")):
                        out.append(PrismaUsageViolation(
                            kind="prisma_invalid_compound_key", source_file=path, field=key,
                            detail=(f"`{path}`: `{model_name}.{method}` uses compound key `{key}` "
                                    f"but the model declares no matching @@unique/@@id"),
                        ))
                    else:
                        out.append(PrismaUsageViolation(
                            kind="prisma_unknown_field", source_file=path, field=key,
                            detail=f"`{path}`: `{key}` is not a field of Prisma model `{model_name}`",
                        ))

            # data / create / update payloads
            for payload_key in ("data", "create", "update"):
                body = _sub_object_body(arg_body, payload_key)
                if body is None:
                    continue
                for key in _top_level_keys(body):
                    if key not in field_names:
                        out.append(PrismaUsageViolation(
                            kind="prisma_unknown_field", source_file=path, field=key,
                            detail=(f"`{path}`: `{key}` (in `{payload_key}`) is not a field of "
                                    f"Prisma model `{model_name}`"),
                        ))
    # de-dup identical (path, kind, field)
    seen = set()
    deduped: List[PrismaUsageViolation] = []
    for v in out:
        k = (v.source_file, v.kind, v.field)
        if k not in seen:
            seen.add(k)
            deduped.append(v)
    return deduped
