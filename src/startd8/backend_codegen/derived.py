"""Deterministic derived-artifact emitters (Python contract-codegen, Step 6 / FR-6, FR-7, FR-8).

Three small *pure* emitters, all projected from the ``.prisma`` contract so they fit the shared
drift/$0.00-skip model uniformly (no LLM):

- **FR-7 export** → ``app/export.py``: ``to_json`` (lossless, sorted) + ``to_markdown`` (a
  deterministic layout — one ``# <Entity>`` section per entity in schema order, ``- field: value``
  lines in field order). JSON is the round-trip-faithful format; Markdown is presentation.
- **FR-8 AI tool/IO schemas** → ``app/ai_schemas.py``: re-projects the Step 1 Pydantic models as the
  AI passes' structured-output contract — ``AI_SCHEMAS`` (entity → model class) + ``json_schema()``.
- **FR-6 completeness** → ``app/completeness.py``: ``compute_completeness(present)`` → score +
  priority-ordered nudges.

**OQ-4 (resolved, v1):** completeness signals are *not* derivable from the schema alone (the
``.prisma`` doesn't say "≥3 confirmed ProofPoints"). v1 ships a schema-derived **presence** rule
(each entity with ≥1 row contributes; nudge per absent entity). Domain-weighted thresholds come from
a declared **manifest** — the documented refinement, deferred.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..frontend_codegen.schema_renderer import composite_type_names, schema_sha256
from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema
from ._headers import header_standard as _header  # shared provenance header (one source of truth)


def _model_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    composites = composite_type_names(schema_text)
    return [n for n in schema.models if n not in composites]


def _py_list(items: List[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"


def render_export(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """Render ``app/export.py`` — ``to_json`` (lossless) + ``to_markdown`` (deterministic layout)."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    fields = {n: [f.name for f in schema.scalar_fields(n)] for n in names}

    entities_lit = _py_list(names)
    fields_lit = (
        "{\n" + "".join(f"    {n!r}: {_py_list(fields[n])},\n" for n in names) + "}"
    )

    header = _header(source_file, sha, "python-export")
    body = (
        "from __future__ import annotations\n\n"
        "import json\n"
        "from typing import Any, Dict, List\n\n"
        f"ENTITY_ORDER: List[str] = {entities_lit}\n"
        f"FIELDS: Dict[str, List[str]] = {fields_lit}\n\n\n"
        "def to_json(payload: Dict[str, List[Dict[str, Any]]]) -> str:\n"
        '    """Lossless, stable JSON (sorted keys) — the round-trip-faithful export format."""\n'
        "    return json.dumps(payload, indent=2, sort_keys=True, default=str)\n\n\n"
        "def to_markdown(payload: Dict[str, List[Dict[str, Any]]]) -> str:\n"
        '    """Deterministic Markdown: a section per entity (schema order), field lines in order."""\n'
        "    lines: List[str] = []\n"
        "    for entity in ENTITY_ORDER:\n"
        "        lines.append(f'# {entity}')\n"
        "        for row in payload.get(entity, []):\n"
        "            for field in FIELDS[entity]:\n"
        "                lines.append(f'- {field}: {row.get(field, \"\")}')\n"
        "            lines.append('')\n"
        "    return '\\n'.join(lines)\n"
    )
    return header + "\n\n" + body


def render_ai_schemas(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """Render ``app/ai_schemas.py`` — the AI passes' structured-output contract (FR-8)."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)

    header = _header(source_file, sha, "python-ai-schemas")
    imports = (
        "from __future__ import annotations\n\n"
        "from typing import Any, Dict, Type\n\n"
    )
    if names:
        imports += (
            "from pydantic import BaseModel\n\n"
            "from .models import " + ", ".join(f"{n}Schema" for n in names) + "\n"
        )
    else:
        imports += "from pydantic import BaseModel\n"

    registry = (
        "AI_SCHEMAS: Dict[str, Type[BaseModel]] = {\n"
        + "".join(f"    {n!r}: {n}Schema,\n" for n in names)
        + "}"
    )
    helper = (
        "def json_schema(entity: str) -> Dict[str, Any]:\n"
        '    """The JSON Schema an AI pass targets for structured output of *entity*."""\n'
        "    return AI_SCHEMAS[entity].model_json_schema()\n"
    )
    return header + "\n\n" + imports + "\n\n" + registry + "\n\n\n" + helper


def render_completeness(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    manifest: Optional[Dict[str, Any]] = None,
) -> str:
    """Render ``app/completeness.py`` — score + nudges (FR-6).

    Two modes, by design (OQ-4):
      - **No manifest (default)** → the v1 *presence rule* (score = fraction of entities with >=1
        row; one nudge per absent entity). Byte-identical to the prior output — zero change for
        projects that don't add a manifest.
      - **Domain-weighted manifest** → per-entity ``min_rows`` + ``weight`` thresholds and an
        ``exclude`` set (e.g. drop join tables / ``AiCall``; require >=3 ProofPoints). Score is the
        weighted fraction of *included* entities meeting their threshold; nudges name the threshold.

    The manifest (``completeness.yaml``) shape::

        exclude: [AiCall, ProofPointCapability, ...]
        entities:
          ProofPoint: {min_rows: 3, weight: 2}
          Capability: {min_rows: 2}
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    entities_lit = _py_list(names)
    header = _header(source_file, sha, "python-completeness")

    _preamble = (
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n"
        "from typing import Dict, List\n\n"
        f"ENTITIES: List[str] = {entities_lit}\n\n\n"
        "@dataclass\n"
        "class CompletenessResult:\n"
        "    score: float  # 0.0 .. 1.0\n"
        "    nudges: List[str]  # priority-ordered, schema order\n\n\n"
    )

    if not manifest:
        body = _preamble + (
            "def compute_completeness(present: Dict[str, int]) -> CompletenessResult:\n"
            '    """Presence rule (OQ-4 v1): score = fraction of entities with >=1 row; one nudge per\n'
            "    absent entity. Domain-weighted thresholds (e.g. >=3 ProofPoints) are a manifest\n"
            '    refinement, deferred."""\n'
            "    if not ENTITIES:\n"
            "        return CompletenessResult(score=1.0, nudges=[])\n"
            "    have = [e for e in ENTITIES if present.get(e, 0) > 0]\n"
            "    score = round(len(have) / len(ENTITIES), 4)\n"
            "    nudges = [f'Add at least one {e}.' for e in ENTITIES if present.get(e, 0) == 0]\n"
            "    return CompletenessResult(score=score, nudges=nudges)\n"
        )
        return header + "\n\n" + body

    # --- domain-weighted mode (manifest present) ---
    excluded = sorted(str(e) for e in (manifest.get("exclude") or []))
    cfg_in = manifest.get("entities") or {}
    cfg: Dict[str, Dict[str, float]] = {}
    for ent in names:  # only known schema models; deterministic schema order
        spec = cfg_in.get(ent)
        if not isinstance(spec, dict):
            continue
        entry: Dict[str, float] = {}
        if "min_rows" in spec:
            entry["min_rows"] = int(spec["min_rows"])
        if "weight" in spec:
            entry["weight"] = float(spec["weight"])
        if entry:
            cfg[ent] = entry

    excluded_lit = _py_list(excluded)
    cfg_lit = "{\n" + "".join(
        f"    {ent!r}: {{" + ", ".join(f"{k!r}: {v}" for k, v in sorted(cfg[ent].items())) + "},\n"
        for ent in names if ent in cfg
    ) + "}"

    body = _preamble + (
        f"_EXCLUDED: List[str] = {excluded_lit}\n"
        f"_CONFIG: Dict[str, Dict[str, float]] = {cfg_lit}\n"
        "_DEFAULT_MIN_ROWS = 1\n"
        "_DEFAULT_WEIGHT = 1.0\n\n\n"
        "def compute_completeness(present: Dict[str, int]) -> CompletenessResult:\n"
        '    """Domain-weighted (OQ-4): weighted fraction of INCLUDED entities meeting their\n'
        "    min_rows threshold; one nudge per unmet entity (naming the threshold). Excluded\n"
        '    entities (join tables, system) are out of the denominator."""\n'
        "    included = [e for e in ENTITIES if e not in _EXCLUDED]\n"
        "    if not included:\n"
        "        return CompletenessResult(score=1.0, nudges=[])\n"
        "    total = 0.0\n"
        "    met = 0.0\n"
        "    nudges: List[str] = []\n"
        "    for e in included:\n"
        "        spec = _CONFIG.get(e, {})\n"
        "        min_rows = int(spec.get('min_rows', _DEFAULT_MIN_ROWS))\n"
        "        weight = float(spec.get('weight', _DEFAULT_WEIGHT))\n"
        "        total += weight\n"
        "        if present.get(e, 0) >= min_rows:\n"
        "            met += weight\n"
        "        else:\n"
        "            qty = 'one' if min_rows == 1 else str(min_rows)\n"
        "            nudges.append(f'Add at least {qty} {e}.')\n"
        "    score = round(met / total, 4) if total else 1.0\n"
        "    return CompletenessResult(score=score, nudges=nudges)\n"
    )
    return header + "\n\n" + body


# The generated app's runtime dependencies (this stack is fixed; not schema-derived). Verified by
# the runtime smoke test — python-multipart is required for the HTMX form routes' request.form().
_RUNTIME_REQUIREMENTS: List[str] = [
    "fastapi",
    "sqlmodel",
    "jinja2",
    "python-multipart",  # form parsing for the HTMX routes (request.form())
    "uvicorn[standard]",  # ASGI server
    "httpx",  # TestClient transport for the generated route-smoke suite (F-8)
]


def render_requirements(
    schema_text: str, source_file: str = "prisma/schema.prisma", *, authoring: bool = False,
    ai: bool = False,
) -> str:
    """Render ``requirements.txt`` — the generated app's pinned-by-stack runtime deps.

    A ``#``-comment GENERATED header (pip ignores comment lines) keeps it owned/drift-tracked like
    the rest of the spine, even though the dep set is fixed rather than schema-derived. With
    *authoring* (``--pages-authoring``) the page-authoring routes read/validate ``pages.yaml`` at
    runtime, so ``pyyaml`` is added (NFR-UI-4) — only then; the content-page render itself stays
    dependency-free. With *ai* (``--ai-passes``) the generated ``app/ai/service.py`` resolves LLM
    providers through the SDK at runtime, so ``startd8`` is added — found live on the strtd8
    pilot: the AI layer import-crashed in any venv without it.
    """
    sha = schema_sha256(schema_text)
    # A distinct kind per dep-set, so the (flag-unaware) drift re-render dispatches to the
    # matching variant instead of false-flagging the extra deps as tampering.
    kind = "python-requirements" + ("-authoring" if authoring else "") + ("-ai" if ai else "")
    header = _header(source_file, sha, kind)
    reqs = list(_RUNTIME_REQUIREMENTS)
    if authoring:
        reqs.append("pyyaml  # page-authoring UI reads/validates pages.yaml at runtime")
    if ai:
        reqs.append(
            "startd8  # AI-layer runtime: app/ai/service.py resolves providers via the SDK; "
            "install the provider extra matching DEFAULT_AGENT_SPEC (e.g. startd8[gemini])"
        )
    body = "\n".join(reqs)
    return header + "\n\n" + body + "\n"


def load_completeness_manifest(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse a ``completeness.yaml`` text into the manifest dict (tolerant: None on absent/bad).

    Public (wireframe R6-S2): consumed cross-module by ``startd8.wireframe``. The
    ``_load_completeness_manifest`` alias is retained for existing callers (R4-S3).
    """
    if not text:
        return None
    try:
        import yaml
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# Back-compat private alias (R4-S3).
_load_completeness_manifest = load_completeness_manifest


def render_derived(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    completeness_text: Optional[str] = None,
) -> Tuple[Tuple[str, str], ...]:
    """All derived artifacts as ``(relative_path, text)`` pairs: export, ai_schemas, completeness.

    *completeness_text* (``completeness.yaml``) — when given, completeness.py is rendered with
    domain-weighted thresholds; absent → the flat presence rule (byte-identical to prior output).
    """
    return (
        ("app/export.py", render_export(schema_text, source_file)),
        ("app/ai_schemas.py", render_ai_schemas(schema_text, source_file)),
        ("app/completeness.py", render_completeness(
            schema_text, source_file, manifest=_load_completeness_manifest(completeness_text))),
    )


# Artifact-kind → path, for CANONICAL_LAYOUT extension.
DERIVED_LAYOUT: Dict[str, str] = {
    "python-export": "app/export.py",
    "python-ai-schemas": "app/ai_schemas.py",
    "python-completeness": "app/completeness.py",
    "python-requirements": "requirements.txt",
}
