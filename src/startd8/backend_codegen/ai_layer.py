"""AI-layer generator (M-C) — deterministically assemble the AI *glue* from a manifest.

The mechanical-assembly thesis (FR-MA-1..6): the AI-service wrapper, the per-pass harness, the AI
router, and the composition entrypoint are **fixed-shape given the contract + a small manifest** —
so they are owned/$0/generated, never LLM-authored. The model authors only the per-pass **prompt**
file. This kills the run-021..026 glue-bug class (wrong imports, double-prefix routers, decorative
calls, wrong entities) by construction: the generator emits imports from its own symbol table.

Inputs: the ``.prisma`` schema + ``ai_passes.yaml`` (the passes manifest, FR-MA-5) +
``human_inputs.yaml`` (the field-authorship policy, C-4 — drives the edge-schema projection).

Generated artifacts (all carry the three-hash AI header):
- ``app/ai/service.py``      — B2 thin wrapper over the SDK provider abstraction (sync, C-1).
- ``app/ai/edge_schemas.py`` — AI tool-input schemas = entity scalars minus human-authored fields.
- ``app/ai/<pass>.py``       — per-pass harness (read → call_ai_service → validate → persist).
- ``app/ai/routes.py``       — one ``APIRouter(prefix="/ai")``; one route per pass; ``Depends(get_session)``.
- ``app/server.py``          — composition entrypoint: mounts ``app.main:app`` + the AI router.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import yaml

from ..frontend_codegen.schema_renderer import schema_sha256
from ..languages.prisma_parser import parse_prisma_schema
from ._headers import header_ai_layer

# Prisma scalar -> a *builtin* Python type for the edge schema (AI tool input). Non-builtins and
# unknowns collapse to ``str`` so generated edge schemas stay dependency-free (just pydantic).
_EDGE_PY = {"String": "str", "Int": "int", "BigInt": "int", "Float": "float", "Boolean": "bool"}

# Server-managed fields the *harness*/DB own — never AI-authored, so they are kept out of the edge
# (tool-input) schema regardless of human_inputs. `source`/`confirmed` are set by the harness;
# `ownerId` and the `createdAt`/`updatedAt` timestamps come from the table's column defaults. (`id`
# is dropped separately via `f.is_id`.) Emitting the timestamps here made them REQUIRED `str` edge
# fields, and `_persist` forwarded those strings into the SQLModel datetime columns → commit crashed
# with "SQLite DateTime type only accepts Python datetime and date objects".
_PROVENANCE_OMIT = {"source", "confirmed", "ownerId", "createdAt", "updatedAt"}

# AI artifact kinds (registered into drift._AI_KINDS). Per-pass modules share the `ai-pass` kind
# and carry the pass name in the `startd8-entity` header slot for re-render dispatch.
AI_KINDS = ("ai-service", "ai-edge-schemas", "ai-pass", "ai-router", "ai-server")


# --------------------------------------------------------------------------- #
# Manifest models + strict parse (FR-MA-5 / C-4)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AiPass:
    name: str
    output_entities: Tuple[str, ...]
    route_path: str
    prompt: str
    input_entities: Tuple[str, ...] = ()
    request_field: str = "text"

    @property
    def module(self) -> str:
        return _ident(self.name)


@dataclass(frozen=True)
class HumanInputs:
    human_only_fields: frozenset  # {(Entity, field)}


_PASS_KEYS = {"name", "output_entities", "route_path", "prompt", "input_entities", "request_field"}
_HUMAN_FIELD_KEYS = {"target", "authored_by", "default", "test_default", "type"}
_HUMAN_TOP_KEYS = {"config", "fields"}


def _ident(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    return s if s and not s[0].isdigit() else f"p_{s}"


def _snake(name: str) -> str:
    """CamelCase/PascalCase → snake_case (``ValueProp`` → ``value_prop``); snake passes through."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    return s.lower()


def _pascal(name: str) -> str:
    """snake_case → PascalCase (``suggest_caps`` → ``SuggestCaps``)."""
    return "".join(part[:1].upper() + part[1:] for part in _ident(name).split("_") if part)


def _plural_field(entity: str) -> str:
    """A stable list-field name for an entity (``Capability`` → ``capabilities``)."""
    snake = _snake(entity)
    return snake[:-1] + "ies" if snake.endswith("y") else snake + "s"


def parse_ai_passes(text: str) -> Tuple[AiPass, ...]:
    """Parse + **strictly** validate ``ai_passes.yaml`` (FR-MA-5: malformed → loud failure)."""
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict) or "passes" not in data:
        raise ValueError("ai_passes.yaml must be a mapping with a top-level `passes:` list")
    passes: List[AiPass] = []
    for i, entry in enumerate(data["passes"] or []):
        if not isinstance(entry, dict):
            raise ValueError(f"ai_passes.yaml: pass #{i} must be a mapping")
        unknown = set(entry) - _PASS_KEYS
        if unknown:
            raise ValueError(f"ai_passes.yaml: pass #{i} has unknown keys {sorted(unknown)}")
        for req in ("name", "output_entities", "route_path", "prompt"):
            if not entry.get(req):
                raise ValueError(f"ai_passes.yaml: pass #{i} missing required `{req}`")
        route = str(entry["route_path"])
        if not route.startswith("/"):
            raise ValueError(f"ai_passes.yaml: route_path must start with '/': {route!r}")
        passes.append(
            AiPass(
                name=str(entry["name"]),
                output_entities=tuple(entry["output_entities"]),
                route_path=route,
                prompt=str(entry["prompt"]),
                input_entities=tuple(entry.get("input_entities", ())),
                request_field=str(entry.get("request_field", "text")),
            )
        )
    if not passes:
        raise ValueError("ai_passes.yaml declares no passes")
    names = [p.name for p in passes]
    if len(set(names)) != len(names):
        raise ValueError(f"ai_passes.yaml has duplicate pass names: {names}")
    return tuple(passes)


def parse_human_inputs(text: Optional[str]) -> HumanInputs:
    """Parse ``human_inputs.yaml`` (C-4). Absent/empty → no human-only fields. Strict on keys."""
    if not text:
        return HumanInputs(human_only_fields=frozenset())
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("human_inputs.yaml must be a mapping")
    unknown = set(data) - _HUMAN_TOP_KEYS
    if unknown:
        raise ValueError(f"human_inputs.yaml has unknown top-level keys {sorted(unknown)}")
    human: set = set()
    for i, entry in enumerate(data.get("fields") or []):
        if not isinstance(entry, dict) or "target" not in entry:
            raise ValueError(f"human_inputs.yaml: fields[{i}] needs a `target` (Entity.field)")
        bad = set(entry) - _HUMAN_FIELD_KEYS
        if bad:
            raise ValueError(f"human_inputs.yaml: fields[{i}] unknown keys {sorted(bad)}")
        if str(entry.get("authored_by", "human")) != "human":
            continue
        target = str(entry["target"])
        if "." not in target:
            raise ValueError(f"human_inputs.yaml: target must be `Entity.field`, got {target!r}")
        ent, _, fld = target.partition(".")
        human.add((ent, fld))
    return HumanInputs(human_only_fields=frozenset(human))


# --------------------------------------------------------------------------- #
# Renderers (each emits the three-hash AI header)
# --------------------------------------------------------------------------- #

# Default agent spec baked into the generated app's service.py when no
# ``--ai-agent-spec`` is given (surface 3 / MODEL_CONFIG). The generated file
# self-describes its spec in the header (``# ai-agent-spec:``) so drift can
# re-render it byte-identically (see drift._check_ai_drift).
_DEFAULT_AI_AGENT_SPEC = "anthropic:claude-opus-4-8"


def _hashes(schema_text: str, manifest_text: str, human_text: Optional[str]) -> Tuple[str, str, str]:
    return (
        schema_sha256(schema_text),
        schema_sha256(manifest_text),
        schema_sha256(human_text or ""),
    )


def render_server(schema_text, manifest_text, human_text, source_file="prisma/schema.prisma") -> str:
    """``app/server.py`` — composition entrypoint (FR-MA-4): mount owned app + AI router only."""
    s, p, h = _hashes(schema_text, manifest_text, human_text)
    header = header_ai_layer(source_file, s, p, h, "ai-server")
    body = (
        "from __future__ import annotations\n\n"
        "from app.main import app\n"
        "from app.ai.routes import ai_router\n\n"
        "app.include_router(ai_router)\n\n"
        '__all__ = ["app"]\n'
    )
    return header + "\n\n" + body


def render_ai_service(
    schema_text, manifest_text, human_text, source_file="prisma/schema.prisma",
    ai_agent_spec: Optional[str] = None,
) -> str:
    """``app/ai/service.py`` — B2 thin wrapper over the SDK provider abstraction (FR-MA-1, C-1/C-2/C-3).

    ``ai_agent_spec`` (surface 3 / MODEL_CONFIG) is baked into ``DEFAULT_AGENT_SPEC`` so the
    generated app calls that provider by default. It is also recorded in the header
    (``# ai-agent-spec:``) so drift re-renders the file byte-identically with the same spec.
    """
    spec = ai_agent_spec or _DEFAULT_AI_AGENT_SPEC
    s, p, h = _hashes(schema_text, manifest_text, human_text)
    header = header_ai_layer(source_file, s, p, h, "ai-service") + f"\n# ai-agent-spec: {spec}"
    body = '''from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from startd8.utils.agent_resolution import resolve_agent_spec

from app.db import get_session  # noqa: F401 — the sync session contract (C-1)
from app.tables import AiCall  # the SQLModel table (models.py only has AiCallSchema) — C-3

logger = logging.getLogger(__name__)

# Per-provider tool-use ceiling (C-2). 8192 stays under anthropic's >10-min streaming guard.
PROVIDER_LIMITS = {"anthropic": 8192}
DEFAULT_AGENT_SPEC = "__AI_AGENT_SPEC__"


def call_ai_service(
    pass_name: str,
    prompt: str,
    output_schema: type[BaseModel],
    session: Session,
    *,
    agent_spec: str = DEFAULT_AGENT_SPEC,
) -> BaseModel:
    """Single Claude entry point. Delegates tool-use/retry/tokens to the SDK (B2); logs one AiCall."""
    provider = agent_spec.split(":", 1)[0]
    max_tokens = PROVIDER_LIMITS.get(provider, 8192)
    agent = resolve_agent_spec(agent_spec)
    value, raw = agent.generate_structured(prompt, output_schema, max_tokens=max_tokens)
    _log_ai_call(session, pass_name, raw)
    return value


def _log_ai_call(session: Session, pass_name: str, raw: Any) -> None:
    """Persist one AiCall row per call; defensive about which columns the table actually has."""
    try:
        usage = getattr(raw, "token_usage", None)
        candidates = {
            "purpose": pass_name,
            "pass_name": pass_name,
            "input_tokens": getattr(usage, "input", None),
            "output_tokens": getattr(usage, "output", None),
            "cost_usd": getattr(usage, "cost_estimate", None) if usage else None,
        }
        kwargs = {k: v for k, v in candidates.items() if hasattr(AiCall, k) and v is not None}
        session.add(AiCall(**kwargs))
        session.flush()
    except Exception:  # logging must never break the pass
        logger.warning("AiCall logging failed for pass=%s", pass_name, exc_info=False)


__all__ = ["call_ai_service", "PROVIDER_LIMITS", "DEFAULT_AGENT_SPEC"]
'''
    body = body.replace("__AI_AGENT_SPEC__", spec)
    return header + "\n\n" + body


def render_edge_schemas(schema_text, manifest_text, human_text, source_file="prisma/schema.prisma") -> str:
    """``app/ai/edge_schemas.py`` — AI tool-input schemas: entity scalars minus human-authored fields (C-4)."""
    s, p, h = _hashes(schema_text, manifest_text, human_text)
    schema = parse_prisma_schema(schema_text)
    passes = parse_ai_passes(manifest_text)
    human = parse_human_inputs(human_text)
    header = header_ai_layer(source_file, s, p, h, "ai-edge-schemas")

    entities: List[str] = []
    for ps in passes:
        for e in ps.output_entities:
            if e not in entities:
                entities.append(e)

    blocks: List[str] = []
    registry: List[str] = []
    for ent in entities:
        fields = []
        for f in schema.scalar_fields(ent):
            if (
                f.is_id
                or f.name in _PROVENANCE_OMIT
                or (ent, f.name) in human.human_only_fields
            ):
                continue  # drop PKs, provenance, and human-authored fields (FR-6: no Metric.value)
            py = _EDGE_PY.get(f.type, "str")
            if f.is_optional:
                fields.append(f"    {f.name}: Optional[{py}] = None")
            else:
                fields.append(f"    {f.name}: {py}")
        if not fields:
            fields.append("    pass")
        omitted = sorted(fld for (e, fld) in human.human_only_fields if e == ent)
        note = f"  # human-only omitted: {', '.join(omitted)}" if omitted else ""
        blocks.append(
            f"class {ent}Edge(BaseModel):\n"
            f'    """AI tool-input for {ent} — human-authored fields omitted (C-4).{note}"""\n'
            + "\n".join(fields)
        )
        registry.append(f"    {ent!r}: {ent}Edge,")

    body = (
        "from __future__ import annotations\n\n"
        "from typing import Optional  # noqa: F401\n\n"
        "from pydantic import BaseModel\n\n\n"
        + "\n\n\n".join(blocks)
        + "\n\n\nEDGE_SCHEMAS = {\n"
        + "\n".join(registry)
        + "\n}\n"
    )
    return header + "\n\n" + body


# Shared owned helpers emitted into every harness (plain strings — literal braces, no f-escaping).
_SUMMARY_HELPER = '''def _summary(obj: Any) -> dict[str, Any]:
    """A row's content columns (drop ids/provenance/timestamps) for the prompt context."""
    skip = {"id", "ownerId", "source", "confirmed", "createdAt", "updatedAt"}
    cols = obj.__table__.columns.keys()
    return {c: getattr(obj, c) for c in cols if c not in skip and getattr(obj, c) is not None}
'''

_PERSIST_HELPER = '''def _persist(session: Session, model: Any, edge_obj: Any) -> int:
    """Persist one edge object as an owned row (source=ai, confirmed=false); dedup by name. 0/1."""
    data = edge_obj.model_dump(exclude_none=True)
    # Server-managed columns are never AI-authored: the harness sets source/confirmed and the table
    # defaults supply id/ownerId/timestamps. Dropping them here keeps str timestamps out of datetime
    # columns even if an edge schema ever carries them (belt-and-suspenders to _PROVENANCE_OMIT).
    _server_managed = {"id", "ownerId", "source", "confirmed", "createdAt", "updatedAt"}
    fields = {k: v for k, v in data.items() if hasattr(model, k) and k not in _server_managed}
    name = fields.get("name")
    if name and hasattr(model, "name"):
        if session.exec(select(model).where(model.name == name)).first() is not None:
            return 0
    row = model(**fields)
    if hasattr(row, "source"):
        row.source = "ai"
    if hasattr(row, "confirmed"):
        row.confirmed = False
    session.add(row)
    session.flush()  # surface constraint errors here so the caller's savepoint can isolate them
    return 1
'''


def render_ai_pass(
    schema_text, manifest_text, human_text, source_file="prisma/schema.prisma", pass_name: str = ""
) -> str:
    """``app/ai/<pass>.py`` — the per-pass harness (FR-MA-2), in one of two owned shapes:

    - **read mode** (``input_entities`` declared) — ``def <name>(session)``: read confirmed input
      rows, build the prompt context, call the AI for a multi-output result, persist each output
      entity's rows ``source:"ai",confirmed:false`` with name-based idempotent dedup.
    - **text mode** (no ``input_entities``) — ``def <name>(text, session)``: free-text → single output.
    """
    s, p, h = _hashes(schema_text, manifest_text, human_text)
    ps = {q.name: q for q in parse_ai_passes(manifest_text)}.get(pass_name)
    if ps is None:
        raise ValueError(f"no such pass in manifest: {pass_name!r}")
    header = header_ai_layer(source_file, s, p, h, "ai-pass").replace(
        "# startd8-artifact: ai-pass",
        f"# startd8-artifact: ai-pass\n# startd8-entity: {ps.name}",
    )
    body = _render_pass_read(ps) if ps.input_entities else _render_pass_text(ps)
    return header + "\n\n" + body


def _render_pass_text(ps: AiPass) -> str:
    out = ps.output_entities[0]
    lines = [
        "from __future__ import annotations",
        "",
        "import logging",
        "from pathlib import Path",
        "from typing import Any",
        "",
        "from sqlmodel import Session, select",
        "",
        "from app.ai.service import call_ai_service",
        f"from app.ai.edge_schemas import {out}Edge",
        f"from app.tables import {out}",
        "",
        "logger = logging.getLogger(__name__)",
        "",
        "# The LLM-authored prompt (FR-MA-6); the harness around it is owned.",
        f"_PROMPT_PATH = Path(__file__).parent / {ps.prompt!r}",
        "",
        "",
        f"def {ps.module}({ps.request_field}: str, session: Session) -> dict[str, Any]:",
        f'    """Free-text → a {out} (source=ai, confirmed=false), name-deduped."""',
        '    prompt = _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.is_file() else ""',
        f'    full_prompt = (prompt + "\\n\\n" + {ps.request_field}).strip()',
        f"    result = call_ai_service({ps.name!r}, full_prompt, {out}Edge, session)",
        "    created = 0",
        "    try:",
        f"        with session.begin_nested():  # isolate the row (M1)",
        f"            created = _persist(session, {out}, result)",
        "    except Exception as exc:  # noqa: BLE001",
        f'        logger.warning("skipping {out} row: %s", exc)',
        "    session.commit()",
        f'    return {{"created": {{{out!r}: created}}}}',
        "",
        "",
        _PERSIST_HELPER,
        "",
        f"__all__ = [{ps.module!r}]",
        "",
    ]
    return "\n".join(lines)


def _render_pass_read(ps: AiPass) -> str:
    outputs = list(dict.fromkeys(ps.output_entities))
    inputs = list(dict.fromkeys(ps.input_entities))
    result_cls = f"{_pascal(ps.name)}Result"
    edge_imports = ", ".join(f"{e}Edge" for e in outputs)
    tables = ", ".join(sorted(set(outputs) | set(inputs)))
    read_pairs = ", ".join(f"({e}, {e!r})" for e in inputs)
    persist_pairs = ", ".join(f"({_plural_field(e)!r}, {e})" for e in outputs)
    result_fields = [
        f"    {_plural_field(e)}: list[{e}Edge] = Field(default_factory=list)" for e in outputs
    ]
    lines = [
        "from __future__ import annotations",
        "",
        "import json",
        "import logging",
        "from pathlib import Path",
        "from typing import Any",
        "",
        "from pydantic import BaseModel, Field",
        "from sqlmodel import Session, select",
        "",
        "from app.ai.service import call_ai_service",
        f"from app.ai.edge_schemas import {edge_imports}",
        f"from app.tables import {tables}",
        "",
        "logger = logging.getLogger(__name__)",
        "",
        "# The LLM-authored prompt (FR-MA-6); the harness around it is owned.",
        f"_PROMPT_PATH = Path(__file__).parent / {ps.prompt!r}",
        "# Cap rows fed into the prompt so a large dataset can't blow up context/cost (H2).",
        "_MAX_INPUT_ROWS = 200",
        "",
        "",
        f"class {result_cls}(BaseModel):",
        f'    """Structured tool output for the {ps.name} pass."""',
        *result_fields,
        "",
        "",
        f"def {ps.module}(session: Session) -> dict[str, Any]:",
        f'    """Read confirmed {", ".join(inputs)} → propose {", ".join(outputs)} '
        '(source=ai, confirmed=false)."""',
        "    context: dict[str, Any] = {}",
        f"    for model, label in [{read_pairs}]:",
        "        rows = session.exec(",
        "            select(model).where(model.confirmed.is_(True)).limit(_MAX_INPUT_ROWS)",
        "        ).all()",
        "        context[label] = [_summary(r) for r in rows]",
        '    prompt = _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.is_file() else ""',
        '    full_prompt = prompt + "\\n\\n## Input data\\n" + json.dumps(context, default=str, indent=2)',
        f"    result = call_ai_service({ps.name!r}, full_prompt, {result_cls}, session)",
        "    created: dict[str, int] = {}",
        f"    for field, model in [{persist_pairs}]:",
        "        n = 0",
        "        for item in getattr(result, field, None) or []:",
        "            try:",
        "                with session.begin_nested():  # isolate each row — one bad row can't abort the batch (M1)",
        "                    n += _persist(session, model, item)",
        "            except Exception as exc:  # noqa: BLE001 — skip the offending row, keep going",
        '                logger.warning("skipping %s row: %s", model.__name__, exc)',
        "        created[model.__name__] = n",
        "    session.commit()",
        '    return {"created": created}',
        "",
        "",
        _SUMMARY_HELPER,
        "",
        _PERSIST_HELPER,
        "",
        f"__all__ = [{ps.module!r}]",
        "",
    ]
    return "\n".join(lines)


def render_ai_routes(schema_text, manifest_text, human_text, source_file="prisma/schema.prisma") -> str:
    """``app/ai/routes.py`` — one APIRouter(prefix='/ai'); one route per pass (FR-MA-3)."""
    s, p, h = _hashes(schema_text, manifest_text, human_text)
    passes = parse_ai_passes(manifest_text)
    header = header_ai_layer(source_file, s, p, h, "ai-router")
    has_text = any(not ps.input_entities for ps in passes)

    imports = "\n".join(f"from app.ai.{ps.module} import {ps.module}" for ps in passes)
    routes: List[str] = []
    for ps in passes:
        if ps.input_entities:  # read mode — body-less POST, reads confirmed inputs
            routes.append(
                f"@ai_router.post({ps.route_path!r})\n"
                f"def post_{ps.module}(session: Session = Depends(get_session)) -> dict[str, Any]:\n"
                f'    """Run the {ps.name} pass (reads confirmed inputs)."""\n'
                f"    return {ps.module}(session)"
            )
        else:  # text mode — free-text body
            routes.append(
                f"@ai_router.post({ps.route_path!r})\n"
                f"def post_{ps.module}(\n"
                f"    body: _Request,\n"
                f"    session: Session = Depends(get_session),\n"
                f") -> dict[str, Any]:\n"
                f'    """Run the {ps.name} pass."""\n'
                f"    return {ps.module}(body.{ps.request_field}, session)"
            )
    exports = ["ai_router"] + (["_Request"] if has_text else []) + [
        f"post_{ps.module}" for ps in passes
    ]
    head = (
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        "from fastapi import APIRouter, Depends\n"
        + ("from pydantic import BaseModel\n" if has_text else "")
        + "from sqlmodel import Session\n\n"
        "from app.db import get_session\n"
        + imports
        + "\n\n"
        'ai_router = APIRouter(prefix="/ai", tags=["ai"])\n\n\n'
    )
    if has_text:
        head += (
            "class _Request(BaseModel):\n"
            '    """Free-text input for a text-mode AI pass."""\n\n'
            '    text: str = ""\n\n\n'
        )
    body = head + "\n\n\n".join(routes) + "\n\n\n__all__ = " + repr(exports) + "\n"
    return header + "\n\n" + body


# --------------------------------------------------------------------------- #
# Layout + assembly
# --------------------------------------------------------------------------- #

def ai_layout(manifest_text: str) -> Dict[str, str]:
    """All AI-layer output paths for the given manifest (kind/entity → path is implicit)."""
    passes = parse_ai_passes(manifest_text)
    layout = {
        "app/ai/service.py": "ai-service",
        "app/ai/edge_schemas.py": "ai-edge-schemas",
        "app/ai/routes.py": "ai-router",
        "app/server.py": "ai-server",
    }
    for ps in passes:
        layout[f"app/ai/{ps.module}.py"] = "ai-pass"
    return layout


def render_ai_layer(
    schema_text: str,
    manifest_text: str,
    human_text: Optional[str],
    source_file: str = "prisma/schema.prisma",
    ai_agent_spec: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """Every AI-layer artifact as ``(path, text)``. Empty ``app/ai/__init__.py`` marker included.

    ``ai_agent_spec`` (surface 3 / MODEL_CONFIG) is baked into the generated service's
    ``DEFAULT_AGENT_SPEC``; ``None`` keeps the catalog default.
    """
    passes = parse_ai_passes(manifest_text)  # fail loud on a malformed manifest before emitting
    out: List[Tuple[str, str]] = [("app/ai/__init__.py", "")]
    out.append(("app/ai/service.py", render_ai_service(
        schema_text, manifest_text, human_text, source_file, ai_agent_spec=ai_agent_spec)))
    out.append(("app/ai/edge_schemas.py", render_edge_schemas(schema_text, manifest_text, human_text, source_file)))
    for ps in passes:
        out.append(
            (
                f"app/ai/{ps.module}.py",
                render_ai_pass(schema_text, manifest_text, human_text, source_file, ps.name),
            )
        )
    out.append(("app/ai/routes.py", render_ai_routes(schema_text, manifest_text, human_text, source_file)))
    out.append(("app/server.py", render_server(schema_text, manifest_text, human_text, source_file)))
    return out
