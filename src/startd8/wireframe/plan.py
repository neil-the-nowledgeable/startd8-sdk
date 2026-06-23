"""WireframePlan derivation (FR-W1..W5, W13, W15) — what WILL the $0 cascade build?

Pure, deterministic, read-only: derives the planned application shape from the assembly input
manifests via the **generators' own parsers** (FR-W3) without invoking the generators or writing
any application files. Artifact paths mirror the renderers' layouts exactly; the FR-W14 golden
cross-check test is the anti-divergence gate for that mirroring.

Status model (FR-W4): ``planned | defaults | placeholder | not_defined | invalid``, with
per-manifest absence semantics, the lenient-Prisma recoverability check (R6-F1), and worst-wins
composition for multi-manifest sections (R6-F3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..backend_codegen.ai_layer import AiPass, parse_ai_passes, parse_human_inputs
from ..backend_codegen.crud_generator import CANONICAL_LAYOUT
from ..backend_codegen.derived import load_completeness_manifest
from ..backend_codegen.forms_manifest import parse_forms
from ..backend_codegen.imports_manifest import parse_imports
from ..backend_codegen.crud_generator import _pk_field
from ..backend_codegen.htmx_generator import _confirm_field, form_fields, writable_fields
from ..backend_codegen.pages_generator import ContentPage, parse_pages
from ..backend_codegen.test_emitter import (
    COMPLETENESS_TESTS_PATH,
    CONTRACT_TESTS_PATH,
    HEALTH_TESTS_PATH,
    OPENAPI_CONTRACT_TESTS_PATH,
    ROUTE_SMOKE_TESTS_PATH,
)
from ..frontend_codegen.schema_renderer import composite_type_names
from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema
from ..logging_config import get_logger
from ..scaffold_codegen.manifest import AppManifest, parse_app_manifest
from ..scaffold_codegen.coherence import evaluate_coherence
from ..view_codegen.manifest import ViewSpec, parse_views
from ..view_codegen.view_prose import parse_view_prose
from .inputs import AssemblyInputs

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Status model (FR-W4)
# --------------------------------------------------------------------------- #

class Status:
    PLANNED = "planned"
    DEFAULTS = "defaults"
    PLACEHOLDER = "placeholder"
    NOT_DEFINED = "not_defined"
    INVALID = "invalid"


# Worst-wins precedence (R6-F3): lower rank = worse.
_PRECEDENCE = {
    Status.INVALID: 0,
    Status.PLACEHOLDER: 1,
    Status.NOT_DEFINED: 2,
    Status.DEFAULTS: 3,
    Status.PLANNED: 4,
}

_ERROR_CAP = 500  # FR-W13 / R5-F2

_SENTINEL = "REPLACE_WITH_"

# Per-manifest absence semantics (FR-W4 table): what an absent file means.
_ABSENT_STATUS = {
    "schema": Status.NOT_DEFINED,
    "app": Status.DEFAULTS,
    "pages": Status.NOT_DEFINED,
    "views": Status.NOT_DEFINED,
    "ai_passes": Status.NOT_DEFINED,
    "human_inputs": Status.DEFAULTS,
    "completeness": Status.DEFAULTS,
    "view_prose": Status.DEFAULTS,   # absent ⇒ raw machine-name view chrome (today's behavior)
    "imports": Status.NOT_DEFINED,   # absent ⇒ no import owned-kind (FR-IMP-3, opt-in)
    "api": Status.NOT_DEFINED,       # absent ⇒ Role 1 schema-only contract (Role 2 opt-in)
    "contexts": Status.NOT_DEFINED,  # absent ⇒ no inter-context consumer clients (Role 3 opt-in)
}

_ABSENT_CONSEQUENCE = {
    "schema": "no contract → no entities, CRUD, forms, or views",
    "app": "default scaffold (app/, SQLite ./data/app.db, Dockerfile on, py3.11)",
    "pages": "no content pages or site nav",
    "views": "no composite views",
    "ai_passes": "no AI service/passes",
    "human_inputs": "only server-managed omissions apply",
    "completeness": "presence-rule fallback scoring",
    "imports": "no bulk-import owned-kind (app/importer.py) or paste/upload surface",
    "api": "schema-only OpenAPI contract (no api.yaml overlay merge)",
    "contexts": "no per-producer inter-context consumer clients",
}


def worst(*statuses: str) -> str:
    """Worst-wins composition (R6-F3)."""
    return min(statuses, key=lambda s: _PRECEDENCE[s])


def _cap_error(message: str) -> Tuple[str, bool]:
    """FR-W13/R5-F2: bound error text; full text goes to debug logs only."""
    if len(message) > _ERROR_CAP:
        return message[:_ERROR_CAP], True
    return message, False


# --------------------------------------------------------------------------- #
# Plan model (FR-W1)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class WireframeItem:
    label: str
    status: str
    detail: str = ""
    paths: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WireframeSection:
    key: str
    title: str
    status: str
    items: Tuple[WireframeItem, ...] = ()
    consequence: str = ""           # FR-W5: app-shape consequence when not `planned`
    error: str = ""                 # capped parser/recoverability error (FR-W13)
    error_truncated: bool = False


@dataclass(frozen=True)
class CoverageStat:
    """Authored-vs-total for one words/content surface (FR-WCI-2). ``total == 0`` ⇒ the surface has
    no items to author (``ratio`` is 1.0 — vacuously complete, never a divide-by-zero)."""

    authored: int = 0
    total: int = 0

    @property
    def ratio(self) -> float:
        return 1.0 if self.total == 0 else self.authored / self.total

    def as_dict(self) -> Dict[str, object]:
        return {"authored": self.authored, "total": self.total, "ratio": round(self.ratio, 4)}


@dataclass(frozen=True)
class ContentCoverageStats:
    """FR-WCI-2: a unified rollup of words/content coverage across the three author→approve surfaces
    the wireframe already tracks per-item — **page bodies**, **view copy**, and **AI prompts**.
    Visibility only (bucket 2/4), never a gate; placeholder/missing content is honestly *un*-authored."""

    page_bodies: CoverageStat = field(default_factory=CoverageStat)
    view_copy: CoverageStat = field(default_factory=CoverageStat)
    ai_prompts: CoverageStat = field(default_factory=CoverageStat)

    @property
    def overall(self) -> CoverageStat:
        return CoverageStat(
            self.page_bodies.authored + self.view_copy.authored + self.ai_prompts.authored,
            self.page_bodies.total + self.view_copy.total + self.ai_prompts.total,
        )

    def as_dict(self) -> Dict[str, object]:
        return {
            "page_bodies": self.page_bodies.as_dict(),
            "view_copy": self.view_copy.as_dict(),
            "ai_prompts": self.ai_prompts.as_dict(),
            "overall": self.overall.as_dict(),
        }


@dataclass(frozen=True)
class WireframePlan:
    project_root: str
    sections: Tuple[WireframeSection, ...]
    input_provenance: Dict[str, Dict[str, Optional[str]]]   # key → {path, resolved_path, source, status_override}
    merge_warnings: Tuple[Dict[str, str], ...]
    shape: Dict[str, int]           # entities / crud_routes / pages / views / ai_passes
    readiness: Dict[str, str]       # generator → "ready" | "blocked(<reason>)"
    status_counts: Dict[str, int] = field(default_factory=dict)
    content_coverage: ContentCoverageStats = field(default_factory=ContentCoverageStats)  # FR-WCI-2

    def section(self, key: str) -> WireframeSection:
        for s in self.sections:
            if s.key == key:
                return s
        raise KeyError(key)

    @property
    def claimed_paths(self) -> Tuple[str, ...]:
        """Every owned artifact path the cascade would emit, per the plan (FR-W14 surface)."""
        out: List[str] = []
        for s in self.sections:
            for item in s.items:
                out.extend(item.paths)
        # Deterministic order, de-duplicated (shared whole-app files claimed once).
        return tuple(sorted(set(out)))


# --------------------------------------------------------------------------- #
# Manifest reading + per-manifest status (FR-W4, FR-W13)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _ManifestState:
    key: str
    status: str
    text: Optional[str] = None      # file content (None when absent/unreadable)
    error: str = ""
    error_truncated: bool = False
    parsed: object = None           # parser output when status is planned/defaults/placeholder


def _read_manifest(inputs: AssemblyInputs, key: str) -> Tuple[Optional[str], Optional[str]]:
    """Read one manifest as UTF-8 (R5-S2). Returns (text, error). Absent → (None, None)."""
    path = inputs.entry(key).resolved_path
    if not path.is_file():
        return None, None
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        return None, "not valid UTF-8"
    except OSError as exc:
        return None, f"unreadable: {exc}"


# Raw block detection for the schema recoverability check (R6-F1). Comments are stripped first
# so a commented-out `// model X {` never counts; the parser treats `model`/`type` blocks alike.
_RAW_MODEL_RE = re.compile(r"^\s*(?:model|type)\s+\w+\s*\{", re.MULTILINE)
_RAW_ENUM_RE = re.compile(r"^\s*enum\s+\w+\s*\{", re.MULTILINE)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")


def _schema_state(text: Optional[str], read_error: Optional[str]) -> _ManifestState:
    """Schema status via the recoverability check (R6-F1) — the parser is lenient, never raises."""
    if read_error:
        msg, trunc = _cap_error(read_error)
        return _ManifestState("schema", Status.INVALID, None, msg, trunc)
    if text is None:
        return _ManifestState("schema", Status.NOT_DEFINED)
    schema = parse_prisma_schema(text)
    scrubbed = _LINE_COMMENT_RE.sub("", text)
    raw_models = len(_RAW_MODEL_RE.findall(scrubbed))
    raw_enums = len(_RAW_ENUM_RE.findall(scrubbed))
    dropped = (raw_models - len(schema.models)) + (raw_enums - len(schema.enums))
    if dropped > 0:
        msg, trunc = _cap_error(
            f"lenient parse dropped {dropped} block(s): "
            f"{raw_models} model/type + {raw_enums} enum declared, "
            f"{len(schema.models)} + {len(schema.enums)} parsed"
        )
        return _ManifestState("schema", Status.INVALID, text, msg, trunc, parsed=schema)
    if not schema.models:
        # Zero models AND nothing dropped (R6-F1 scoping) → scaffolded stub, not corruption.
        return _ManifestState("schema", Status.PLACEHOLDER, text, parsed=schema)
    return _ManifestState("schema", Status.PLANNED, text, parsed=schema)


def _yaml_state(key: str, text: Optional[str], read_error: Optional[str], parse) -> _ManifestState:
    """Status for a strict-parser YAML manifest: absent → per-table default; loud-fail → invalid;
    `REPLACE_WITH_` sentinel → placeholder (FR-W4)."""
    if read_error:
        msg, trunc = _cap_error(read_error)
        return _ManifestState(key, Status.INVALID, None, msg, trunc)
    if text is None:
        return _ManifestState(key, _ABSENT_STATUS[key])
    try:
        parsed = parse(text)
    except Exception as exc:  # strict parsers raise ValueError/yaml errors — degrade, never abort
        logger.debug("wireframe: %s failed its parser", key, exc_info=True)
        msg, trunc = _cap_error(str(exc))
        return _ManifestState(key, Status.INVALID, text, msg, trunc)
    if _SENTINEL in text:
        return _ManifestState(key, Status.PLACEHOLDER, text, parsed=parsed)
    return _ManifestState(key, Status.PLANNED, text, parsed=parsed)


def _completeness_state(text: Optional[str], read_error: Optional[str]) -> _ManifestState:
    """completeness.yaml uses the tolerant loader — present-but-unloadable is `invalid`."""
    if read_error:
        msg, trunc = _cap_error(read_error)
        return _ManifestState("completeness", Status.INVALID, None, msg, trunc)
    if text is None:
        return _ManifestState("completeness", Status.DEFAULTS)
    manifest = load_completeness_manifest(text)
    if manifest is None:
        msg, trunc = _cap_error("completeness.yaml is not a YAML mapping")
        return _ManifestState("completeness", Status.INVALID, text, msg, trunc)
    if _SENTINEL in text:
        return _ManifestState("completeness", Status.PLACEHOLDER, text, parsed=manifest)
    return _ManifestState("completeness", Status.PLANNED, text, parsed=manifest)


def _apply_override(
    state: _ManifestState, override: Optional[str]
) -> Tuple[_ManifestState, Optional[Dict[str, str]]]:
    """FR-W6/R2-F1: parser-derived status wins when the file exists; an override applies when the
    file is absent (inventory declared ahead of authoring).

    Returns ``(state, conflict_warning)`` — a conflict between the override and disk reality is
    surfaced as a warning dict (rendered + JSON via ``merge_warnings``), never only logged.
    """
    if not override:
        return state, None
    file_absent = state.text is None and not state.error
    if not file_absent:
        if override == "absent":
            message = (
                f"inputs declare `{state.key}` absent but the file exists — parser result wins"
            )
            logger.warning("wireframe: %s", message)
            return state, {"key": state.key, "message": message}
        return state, None
    if override == "placeholder":
        return _ManifestState(state.key, Status.PLACEHOLDER), None
    if override == "authored":
        message = f"inputs declare `{state.key}` authored but the file is missing"
        logger.warning("wireframe: %s", message)
        return state, {"key": state.key, "message": message}
    return state, None  # `absent` keeps the absence semantics


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #

def _consequence(state: _ManifestState) -> str:
    if state.status == Status.INVALID:
        return f"invalid {_manifest_name(state.key)} — cascade would fail loud"
    if state.status in (Status.NOT_DEFINED, Status.DEFAULTS):
        return _ABSENT_CONSEQUENCE[state.key]
    if state.status == Status.PLACEHOLDER:
        return f"{_manifest_name(state.key)} is a placeholder — output would be stub-shaped"
    return ""


def _manifest_name(key: str) -> str:
    from .inputs import CONVENTION_PATHS

    return CONVENTION_PATHS[key].rsplit("/", 1)[-1]


def _entity_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    """Concrete models in declaration order — mirrors render_ui's composite-type filter."""
    composites = composite_type_names(schema_text)
    return [n for n in schema.models if n not in composites]


def _scaffold_section(state: _ManifestState) -> WireframeSection:
    if state.status == Status.INVALID:
        return WireframeSection(
            "scaffold", "Scaffold / Container", Status.INVALID,
            consequence=_consequence(state), error=state.error,
            error_truncated=state.error_truncated,
        )
    manifest: AppManifest = state.parsed if state.parsed else parse_app_manifest(None)
    paths = ["pyproject.toml", f"{manifest.package}/logging_config.py", ".env.example"]
    items = [
        WireframeItem(
            f"app: {manifest.name}", state.status,
            detail=f"package={manifest.package}, python={manifest.python_version}",
            paths=("pyproject.toml", f"{manifest.package}/logging_config.py", ".env.example"),
        ),
        WireframeItem(
            "persistence", state.status,
            detail=f"SQLite {manifest.db_path} (WAL), log {manifest.log_file}",
        ),
        WireframeItem(
            "run: local", state.status,
            detail="run.sh — bind " + (
                "127.0.0.1 (loopback)" if manifest.deployment_mode == "installed" else "0.0.0.0"
            ),
            paths=("run.sh",),
        ),
    ]
    paths.append("run.sh")
    if manifest.dockerfile:
        items.append(WireframeItem("container: Dockerfile", state.status, paths=("Dockerfile",)))
        paths.append("Dockerfile")
    else:
        items.append(WireframeItem("container", Status.NOT_DEFINED, detail="dockerfile disabled"))
    if manifest.migrations:
        items.append(
            WireframeItem(
                # FR-MG-1: the scaffold also emits the revision template + versions dir so the
                # generated app can actually produce/apply a migration.
                "migrations: alembic", state.status,
                paths=("alembic.ini", "alembic/env.py", "alembic/script.py.mako",
                       "alembic/versions/.gitkeep"),
            )
        )
    else:
        items.append(WireframeItem("migrations", Status.NOT_DEFINED, detail="disabled"))
    return WireframeSection(
        "scaffold", "Scaffold / Container", state.status, tuple(items),
        consequence=_consequence(state),
    )


def _services_section(
    schema_state: _ManifestState,
    ai_state: _ManifestState,
    contexts_state: Optional[_ManifestState] = None,
) -> WireframeSection:
    # Composition (R6-F3 / R2-S3): schema always contributes; ai_passes contributes its
    # degradation states (invalid/placeholder). Mere absence of the *optional* AI manifest scopes
    # to the AI items per the FR-W4 table ("AI layer not_defined"), not the whole section.
    contributors = [schema_state.status]
    if ai_state.status in (Status.INVALID, Status.PLACEHOLDER):
        contributors.append(ai_state.status)
    status = worst(*contributors)
    worst_state = min(
        (s for s in (schema_state, ai_state) if s.status == status),
        key=lambda s: _PRECEDENCE[s.status],
        default=schema_state,
    )

    items: List[WireframeItem] = []
    if schema_state.status in (Status.PLANNED, Status.PLACEHOLDER):
        # Schema usable → core services planned (placeholder schema ⇒ placeholder services).
        items.append(
            WireframeItem(
                "FastAPI app", schema_state.status,
                detail="JSON CRUD + lifespan",
                paths=(
                    "app/__init__.py",
                    CANONICAL_LAYOUT["fastapi-main"],
                    CANONICAL_LAYOUT["fastapi-db"],
                    CANONICAL_LAYOUT["fastapi-routers"],
                    CANONICAL_LAYOUT["fastapi-health"],
                    CANONICAL_LAYOUT["python-openapi-contract"],
                    "clients/__init__.py",
                    CANONICAL_LAYOUT["python-openapi-client"],
                ),
            )
        )
        items.append(
            WireframeItem(
                "HTMX web mount", schema_state.status,
                paths=(
                    CANONICAL_LAYOUT["fastapi-web"],
                    "app/templates/base.html",
                    "app/templates/_field_error.html",
                ),
            )
        )
        items.append(
            WireframeItem(
                "export endpoints", schema_state.status,
                paths=(CANONICAL_LAYOUT["python-export"],),
            )
        )
        items.append(
            WireframeItem(
                "AI schemas + requirements", schema_state.status,
                paths=(
                    CANONICAL_LAYOUT["python-ai-schemas"],
                    CANONICAL_LAYOUT["python-requirements"],
                    CONTRACT_TESTS_PATH,
                    HEALTH_TESTS_PATH,
                    OPENAPI_CONTRACT_TESTS_PATH,
                    ROUTE_SMOKE_TESTS_PATH,  # rung-5 floor: generated HTTP smoke (F-8)
                ),
            )
        )
        if contexts_state and contexts_state.status == Status.PLANNED and contexts_state.parsed:
            from ..backend_codegen.context_manifest import parse_contexts
            from ..backend_codegen.context_otel_renderer import CONTEXT_OTEL_PATH
            from ..backend_codegen.test_emitter import CROSS_CONTEXT_SMOKE_TESTS_PATH

            if parse_contexts(contexts_state.text):
                items.append(
                    WireframeItem(
                        "Context OTel helper", Status.PLANNED,
                        detail="OQ-5 traced outbound HTTP spans",
                        paths=(CONTEXT_OTEL_PATH,),
                    )
                )
            for ctx in parse_contexts(contexts_state.text):
                items.append(
                    WireframeItem(
                        f"Context client: {ctx.id}", Status.PLANNED,
                        detail=f"routes={ctx.routes}, local={ctx.local}",
                        paths=(f"clients/{ctx.id}_client.py",),
                    )
                )
            if parse_contexts(contexts_state.text):
                items.append(
                    WireframeItem(
                        "Cross-context smoke", Status.PLANNED,
                        detail="FR-6 list+create via generated client",
                        paths=(CROSS_CONTEXT_SMOKE_TESTS_PATH,),
                    )
                )
    if ai_state.status == Status.PLANNED and schema_state.status in (
        Status.PLANNED, Status.PLACEHOLDER
    ):
        passes: Tuple[AiPass, ...] = ai_state.parsed
        items.append(
            WireframeItem(
                "AI service", Status.PLANNED,
                detail=f"{len(passes)} pass(es)",
                paths=(
                    "app/ai/__init__.py", "app/ai/service.py", "app/ai/edge_schemas.py",
                    "app/ai/routes.py", "app/server.py",
                    "tests/test_edge_privacy.py", "tests/test_ai_passes.py",
                    # FR-40 executable guarantees (F-305 moved off the LLM path)
                    "tests/test_keyless_boot.py", "tests/test_cost_logging.py",
                ),
            )
        )
        for p in passes:
            items.append(
                WireframeItem(
                    f"AI pass: {p.name}", Status.PLANNED,
                    detail=f"{p.route_path} → {', '.join(p.output_entities)}",
                    paths=(f"app/ai/{p.module}.py",),
                )
            )
    elif ai_state.status != Status.PLANNED:
        items.append(
            WireframeItem(
                "AI layer", ai_state.status, detail=_consequence(ai_state) or "",
            )
        )
    return WireframeSection(
        "services", "Services", status, tuple(items),
        consequence=_consequence(worst_state),
        error=worst_state.error, error_truncated=worst_state.error_truncated,
    )


def _entities_section(state: _ManifestState) -> WireframeSection:
    # `parsed is None` covers the override-placeholder case (declared ahead of authoring).
    if state.status not in (Status.PLANNED, Status.PLACEHOLDER) or state.parsed is None:
        return WireframeSection(
            "entities", "Entities & CRUD", state.status,
            consequence=_consequence(state), error=state.error,
            error_truncated=state.error_truncated,
        )
    schema: PrismaSchema = state.parsed
    names = _entity_names(schema, state.text or "")
    items = [
        WireframeItem(
            "contract models", state.status,
            detail=f"{len(names)} entities",
            paths=(
                CANONICAL_LAYOUT["pydantic-models"],
                CANONICAL_LAYOUT["sqlmodel-tables"],
                CANONICAL_LAYOUT["python-completeness"],
                COMPLETENESS_TESTS_PATH,
            ),
        )
    ]
    for n in names:
        e = n.lower()
        paths = [
            f"app/templates/{e}/list.html",
            f"app/templates/{e}/_row.html",  # shared row partial (FR-CA-3)
            f"app/templates/{e}/detail.html",
        ]
        detail = "routes: list/get/create/update/delete"
        if _confirm_field(schema, n) is not None and _pk_field(schema, n) is not None:
            # confirmed-bearing entity → confirm toggle (list row + detail block, FR-CA-3/5)
            paths.append(f"app/templates/{e}/_confirm.html")
            detail += " (+confirm)"
        items.append(
            WireframeItem(n, state.status, detail=detail, paths=tuple(paths))
        )
    return WireframeSection(
        "entities", "Entities & CRUD", state.status, tuple(items),
        consequence=_consequence(state),
    )


def _pages_section(state: _ManifestState, *, authoring: bool) -> WireframeSection:
    if state.status not in (Status.PLANNED, Status.PLACEHOLDER) or state.parsed is None:
        return WireframeSection(
            "pages", "Pages & Nav", state.status,
            consequence=_consequence(state), error=state.error,
            error_truncated=state.error_truncated,
        )
    pages, nav_override = state.parsed
    items = [
        WireframeItem(
            "pages router", state.status,
            detail="nav: explicit" if nav_override is not None else "nav: from nav_label",
            paths=("app/pages.py",),
        )
    ]
    for p in pages:
        nav = f", nav={p.nav_label}" if p.nav_label else ""
        items.append(
            WireframeItem(
                f"{p.slug} — {p.title}", state.status,
                detail=f"content: {p.content}{nav}",
                paths=(f"app/templates/pages/{p.name}.html",),
            )
        )
    if authoring:
        items.append(
            WireframeItem(
                "authoring UI", state.status,
                detail="--pages-authoring",
                paths=(
                    "app/pages_io.py", "app/pages_admin.py",
                    "app/templates/pages/_authoring.html",
                ),
            )
        )
    return WireframeSection(
        "pages", "Pages & Nav", state.status, tuple(items), consequence=_consequence(state)
    )


def _forms_section(
    schema_state: _ManifestState,
    human_state: _ManifestState,
    views_text: Optional[str] = None,
) -> WireframeSection:
    status = worst(schema_state.status, human_state.status)
    worst_state = (
        schema_state
        if _PRECEDENCE[schema_state.status] <= _PRECEDENCE[human_state.status]
        else human_state
    )
    if (
        schema_state.status not in (Status.PLANNED, Status.PLACEHOLDER)
        or schema_state.parsed is None
    ):
        return WireframeSection(
            "forms", "Forms", status, consequence=_consequence(worst_state),
            error=worst_state.error, error_truncated=worst_state.error_truncated,
        )
    schema: PrismaSchema = schema_state.parsed
    human_only = (
        human_state.parsed.human_only_fields
        if human_state.status == Status.PLANNED and human_state.parsed is not None
        else frozenset()
    )
    # Per-entity post-create behavior from views.yaml `forms:` (OQ-3). Advisory only — a
    # malformed manifest degrades to defaults here; the Views section reports the invalidity.
    try:
        on_create = parse_forms(views_text)
    except ValueError:
        on_create = {}
    items: List[WireframeItem] = []
    for n in _entity_names(schema, schema_state.text or ""):
        e = n.lower()
        all_fields = form_fields(schema, n)
        writable = writable_fields(schema, n)
        owned = sorted(f.name for f in writable if (n, f.name) in human_only)
        shown = [f.name for f in writable if (n, f.name) not in human_only]
        server_managed = sorted(f.name for f in all_fields if f not in writable)
        detail = f"fields: {', '.join(shown) if shown else '(none)'}"
        omitted_bits = []
        if server_managed:
            omitted_bits.append(f"server-managed: {', '.join(server_managed)}")
        if owned:
            omitted_bits.append(f"owned: {', '.join(owned)}")
        if omitted_bits:
            detail += f" | omitted — {'; '.join(omitted_bits)}"
        if n in on_create:
            detail += f" | on_create: {on_create[n]}"
        paths = [f"app/templates/{e}/form.html"]
        if on_create.get(n) == "confirmation":
            paths.append(f"app/templates/{e}/created.html")
        items.append(
            WireframeItem(
                f"{n} create/edit form", status, detail=detail,
                paths=tuple(paths),
            )
        )
    return WireframeSection(
        "forms", "Forms", status, tuple(items),
        consequence=_consequence(worst_state),
        error=worst_state.error, error_truncated=worst_state.error_truncated,
    )


def _views_section(
    schema_state: _ManifestState, views_state: _ManifestState,
    view_prose_state: Optional[_ManifestState] = None,
) -> WireframeSection:
    status = worst(schema_state.status, views_state.status)
    # FR-WCI-1: which views carry authored copy (title/intro/…) vs. render with raw machine names.
    chromed = (
        set(view_prose_state.parsed)
        if view_prose_state is not None and view_prose_state.parsed else set()
    )
    worst_state = (
        schema_state
        if _PRECEDENCE[schema_state.status] <= _PRECEDENCE[views_state.status]
        else views_state
    )
    if (
        views_state.status not in (Status.PLANNED, Status.PLACEHOLDER)
        or views_state.parsed is None
        or schema_state.status not in (Status.PLANNED, Status.PLACEHOLDER)
        or schema_state.parsed is None
    ):
        return WireframeSection(
            "views", "Composite Views", status, consequence=_consequence(worst_state),
            error=worst_state.error, error_truncated=worst_state.error_truncated,
        )
    specs: Tuple[ViewSpec, ...] = views_state.parsed
    n_chromed = sum(1 for v in specs if v.name in chromed)
    pkg_detail = (
        f"view copy: {n_chromed}/{len(specs)} authored" if specs else None
    )
    items = [
        WireframeItem(
            "views package", status, detail=pkg_detail,
            paths=("app/views/__init__.py", "app/views/routes.py", "tests/test_views.py"),
        )
    ]
    for v in specs:
        # AR-3: a model-scoped export serves raw Markdown/JSON of the whole model — no template.
        model_export = v.kind == "export-package" and v.scope == "model"
        if model_export:
            detail = f"{v.route}/markdown + {v.route}/json (whole model)"
            paths: Tuple[str, ...] = (f"app/views/{v.module}.py",)
        elif not v.root:
            # Route-bound kinds without an entity root (AR-2 computed-panel, AR-4 import-flow).
            detail = v.route + (f" compute={v.compute}" if v.compute else "")
            paths = (
                f"app/views/{v.module}.py",
                f"app/templates/views/{v.module}.html",
            )
        else:
            detail = f"{v.route} root={v.root}" + (
                f", {len(v.panels)} panel(s)" if v.panels else ""
            )
            paths = (
                f"app/views/{v.module}.py",
                f"app/templates/views/{v.module}.html",
            )
        detail += f" · copy: {'authored' if v.name in chromed else 'raw'}"
        items.append(WireframeItem(f"{v.name} ({v.kind})", status, detail=detail, paths=paths))
    return WireframeSection(
        "views", "Composite Views", status, tuple(items), consequence=_consequence(worst_state)
    )


_PROMPT_PATH_RE = re.compile(r"^[\w./-]+\.(md|txt)$")


def _content_section(
    inputs: AssemblyInputs,
    pages_state: _ManifestState,
    ai_state: _ManifestState,
) -> WireframeSection:
    """FR-W15: bucket-2/4 visibility only — never generative, never gated."""
    items: List[WireframeItem] = []
    if pages_state.status in (Status.PLANNED, Status.PLACEHOLDER) and pages_state.parsed:
        pages: Tuple[ContentPage, ...] = pages_state.parsed[0]
        app_dir = inputs.project_root / "app"
        for p in pages:
            md = app_dir / p.content
            if not md.is_file():
                items.append(
                    WireframeItem(
                        f"page body: app/{p.content}", Status.NOT_DEFINED,
                        detail=f"for {p.slug} — no page body at generate time",
                    )
                )
            else:
                try:
                    text = md.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    text = ""
                st = (
                    Status.PLACEHOLDER
                    if (not text.strip() or _SENTINEL in text)
                    else Status.PLANNED
                )
                items.append(WireframeItem(f"page body: app/{p.content}", st, detail=f"for {p.slug}"))
    if ai_state.status == Status.PLANNED and ai_state.parsed:
        for p in ai_state.parsed:
            if _PROMPT_PATH_RE.match(p.prompt):
                prompt_file = inputs.project_root / p.prompt
                if not prompt_file.is_file():
                    items.append(
                        WireframeItem(
                            f"prompt: {p.prompt}", Status.NOT_DEFINED,
                            detail=f"for pass {p.name} — referenced file missing",
                        )
                    )
                else:
                    items.append(
                        WireframeItem(f"prompt: {p.prompt}", Status.PLANNED, detail=f"for pass {p.name}")
                    )
            else:
                items.append(
                    WireframeItem(f"prompt (inline): {p.name}", Status.PLANNED, detail="prose in manifest")
                )
    if not items:
        return WireframeSection(
            "content", "Content Inputs (buckets 2/4 — visibility only)", Status.NOT_DEFINED,
            consequence="no content files referenced by the manifests",
        )
    status = worst(*(i.status for i in items))
    return WireframeSection(
        "content", "Content Inputs (buckets 2/4 — visibility only)", status, tuple(items),
        consequence=(
            "placeholder content is the intended starting state — never gated, honestly scored"
            if status != Status.PLANNED else ""
        ),
    )


def _content_coverage(
    content_section: WireframeSection,
    views_state: _ManifestState,
    view_prose_state: Optional[_ManifestState],
) -> ContentCoverageStats:
    """FR-WCI-2: aggregate the per-item words/content coverage the wireframe already surfaces.

    Page bodies + AI prompts come from the built ``content`` section's items (``PLANNED`` ⇒ authored;
    ``PLACEHOLDER``/``NOT_DEFINED`` ⇒ not authored). View copy is recomputed from the parsed states
    (no extra I/O), keyed by VIEW name to match ``_views_section`` (FR-WCI-1 / R1-S8). Reading the
    already-built section keeps this a pure rollup — one source of truth per surface."""
    pb_total = pb_auth = pr_total = pr_auth = 0
    for it in content_section.items:
        if it.label.startswith("page body:"):
            pb_total += 1
            pb_auth += it.status == Status.PLANNED
        elif it.label.startswith("prompt"):   # "prompt: <path>" or "prompt (inline): <name>"
            pr_total += 1
            pr_auth += it.status == Status.PLANNED

    specs: Tuple[ViewSpec, ...] = (
        views_state.parsed
        if views_state.status in (Status.PLANNED, Status.PLACEHOLDER) and views_state.parsed
        else ()
    )
    chromed = (
        set(view_prose_state.parsed)
        if view_prose_state is not None and view_prose_state.parsed else set()
    )
    vc_total = len(specs)
    vc_auth = sum(1 for v in specs if v.name in chromed)

    return ContentCoverageStats(
        page_bodies=CoverageStat(pb_auth, pb_total),
        view_copy=CoverageStat(vc_auth, vc_total),
        ai_prompts=CoverageStat(pr_auth, pr_total),
    )


def _completeness_section(
    state: _ManifestState, schema_state: _ManifestState
) -> WireframeSection:
    if state.status == Status.INVALID:
        return WireframeSection(
            "completeness", "Completeness", Status.INVALID,
            consequence=_consequence(state), error=state.error,
            error_truncated=state.error_truncated,
        )
    items: List[WireframeItem] = []
    if state.status == Status.PLANNED and isinstance(state.parsed, dict):
        cfg = state.parsed.get("entities") or {}
        excluded = state.parsed.get("exclude") or []
        for ent in sorted(cfg):
            spec = cfg[ent] if isinstance(cfg[ent], dict) else {}
            items.append(
                WireframeItem(
                    f"signal: {ent}", Status.PLANNED,
                    detail=", ".join(f"{k}={v}" for k, v in sorted(spec.items())) or "min_rows=1",
                )
            )
        if excluded:
            items.append(
                WireframeItem("excluded", Status.PLANNED, detail=", ".join(sorted(map(str, excluded))))
            )
    elif state.status == Status.DEFAULTS and schema_state.status == Status.PLANNED:
        # R3-F5: under `defaults`, enumerate the presence-rule fallback signals.
        schema: PrismaSchema = schema_state.parsed
        for n in _entity_names(schema, schema_state.text or ""):
            items.append(
                WireframeItem(f"signal: {n}", Status.DEFAULTS, detail="presence rule (>=1 row)")
            )
    return WireframeSection(
        "completeness", "Completeness", state.status, tuple(items),
        consequence=_consequence(state),
    )


# --------------------------------------------------------------------------- #
# Readiness (R4-F2) + assembly
# --------------------------------------------------------------------------- #

def _readiness(states: Dict[str, _ManifestState]) -> Dict[str, str]:
    def blocked(reason: str) -> str:
        return f"blocked({reason})"

    out: Dict[str, str] = {}
    # scaffold: absent app.yaml still scaffolds (defaults); only an invalid manifest blocks.
    app = states["app"]
    out["scaffold"] = blocked(f"invalid {_manifest_name('app')}") if app.status == Status.INVALID else "ready"

    # backend: needs a real contract; any invalid backend-input manifest fails the generator loud.
    schema = states["schema"]
    if schema.status == Status.INVALID:
        out["backend"] = blocked("invalid schema.prisma")
    elif schema.status == Status.NOT_DEFINED:
        out["backend"] = blocked("missing schema.prisma")
    elif schema.status == Status.PLACEHOLDER:
        out["backend"] = blocked("placeholder schema.prisma (no models)")
    else:
        bad = next(
            (
                k for k in ("pages", "ai_passes", "human_inputs", "completeness")
                if states[k].status == Status.INVALID
            ),
            None,
        )
        out["backend"] = blocked(f"invalid {_manifest_name(bad)}") if bad else "ready"

    views = states["views"]
    if out["backend"] != "ready":
        out["views"] = out["backend"]
    elif views.status == Status.NOT_DEFINED:
        out["views"] = blocked("missing views.yaml")
    elif views.status == Status.INVALID:
        out["views"] = blocked("invalid views.yaml")
    else:
        out["views"] = "ready"
    return out


def _deployment_section(app_state: "_ManifestState") -> WireframeSection:
    """FR-CFG-6 / A8: surface the declared deployment mode, per-dimension posture, and the FR-CFG-5
    coherence findings (advisory here — `generate backend` is the gate). Read-only, $0."""
    manifest = app_state.parsed if app_state.parsed else parse_app_manifest(None)
    deployed = manifest.deployment_mode == "deployed"
    items = [
        WireframeItem("mode", Status.PLANNED, manifest.deployment_mode),
        WireframeItem("persistence", Status.PLANNED,
                      "pooled shared DB via DATABASE_URL" if deployed
                      else "local-first SQLite (WAL, single writer)"),
        WireframeItem("bind", Status.PLANNED,
                      "0.0.0.0 (all interfaces; container)" if deployed
                      else "127.0.0.1 (loopback; local run.sh)"),
        WireframeItem("schema-init", Status.PLANNED,
                      "managed migrations (alembic upgrade head)" if deployed
                      else "create_all on startup"),
        WireframeItem("secrets-default", Status.PLANNED,
                      "external manager expected (e.g. doppler)" if deployed else "local backend"),
        WireframeItem("observability", Status.PLANNED,
                      "centralized OTel expected" if deployed else "local rotating file logs"),
        WireframeItem(
            "identity", Status.PLANNED,
            ("reference auth seam + per-principal row scoping "
             f"(tenant={manifest.tenant_model}.{manifest.tenant_owner_field})"
             if deployed and manifest.has_tenant
             else "reference auth seam (app/auth.py, not production); NOT tenant-isolated"
             if deployed else "single implicit owner (no auth)"),
        ),
    ]
    # M2 emits the auth seam; M3 tenancy (has_tenant) retires the authenticated-but-not-isolated WARN.
    findings = evaluate_coherence(manifest, has_auth_seam=deployed, has_tenant=manifest.has_tenant)
    for f in findings:
        st = Status.INVALID if f.severity == "ERROR" else Status.PLACEHOLDER
        items.append(WireframeItem(f"coherence:{f.code}", st, f"{f.severity}: {f.message}"))
    sec_status = Status.INVALID if any(f.severity == "ERROR" for f in findings) else Status.PLANNED
    consequence = "" if sec_status == Status.PLANNED else (
        "incoherent deployment config — `generate backend` will refuse the build (FR-CFG-5)."
    )
    return WireframeSection(
        key="deployment", title="Deployment mode", status=sec_status,
        items=tuple(items), consequence=consequence,
    )


def build_wireframe_plan(inputs: AssemblyInputs, *, authoring: bool = False) -> WireframePlan:
    """Derive the full :class:`WireframePlan` from resolved inputs (FR-W1..W5, W13, W15)."""
    texts: Dict[str, Tuple[Optional[str], Optional[str]]] = {
        key: _read_manifest(inputs, key) for key in inputs.entries
    }

    schema_state = _schema_state(*texts["schema"])
    states: Dict[str, _ManifestState] = {
        "schema": schema_state,
        "app": _yaml_state("app", *texts["app"], parse_app_manifest),
        "pages": _yaml_state("pages", *texts["pages"], parse_pages),
        "ai_passes": _yaml_state("ai_passes", *texts["ai_passes"], parse_ai_passes),
        "human_inputs": _yaml_state("human_inputs", *texts["human_inputs"], parse_human_inputs),
        "completeness": _completeness_state(*texts["completeness"]),
    }
    # views needs known_entities from the schema (FR-W13: degrade, don't crash, when unusable).
    known = (
        frozenset(schema_state.parsed.models)
        if schema_state.status in (Status.PLANNED, Status.PLACEHOLDER) and schema_state.parsed
        else frozenset()
    )
    states["views"] = _yaml_state(
        "views", *texts["views"], lambda t: parse_views(t, known_entities=known)
    )
    # FR-WCI-1: view copy (the WORDS layer). Keyed by VIEW name (matches `_views_section`'s idents,
    # not model names) so per-view chrome coverage lines up.
    states["view_prose"] = _yaml_state("view_prose", *texts["view_prose"], parse_view_prose)
    # FR-IMP-3: import declarations. Keyed/validated against the schema entities (degrade, don't
    # crash, when the schema is unusable — same posture as views).
    states["imports"] = _yaml_state(
        "imports", *texts["imports"], lambda t: parse_imports(t, known_entities=known)
    )
    # FR (Role 2): api.yaml OpenAPI surface overlay. Catalog key (see _ABSENT_STATUS["api"]); a
    # state is required so the provenance pass (which iterates the full catalog) can look it up.
    from ..backend_codegen.api_overlay_manifest import parse_api_overlay

    states["api"] = _yaml_state("api", *texts["api"], parse_api_overlay)
    from ..backend_codegen.context_manifest import parse_contexts

    states["contexts"] = _yaml_state(
        "contexts", *texts["contexts"], parse_contexts
    )

    # Status overrides from the assembly-inputs YAML (FR-W6/R2-F1). Conflicts between an
    # override and disk reality join merge_warnings — visible in tree + JSON, never only logged.
    warnings: List[Dict[str, str]] = list(inputs.merge_warnings)
    for key, state in list(states.items()):
        states[key], conflict = _apply_override(state, inputs.entry(key).status_override)
        if conflict:
            warnings.append(conflict)
    schema_state = states["schema"]

    content_section = _content_section(inputs, states["pages"], states["ai_passes"])
    sections = (
        _scaffold_section(states["app"]),
        _deployment_section(states["app"]),
        _services_section(schema_state, states["ai_passes"], states.get("contexts")),
        _entities_section(schema_state),
        _pages_section(states["pages"], authoring=authoring),
        _forms_section(schema_state, states["human_inputs"], texts["views"][0]),
        _views_section(schema_state, states["views"], states["view_prose"]),
        content_section,
        _completeness_section(states["completeness"], schema_state),
    )
    # FR-WCI-2: a unified words/content coverage rollup over the three author→approve surfaces.
    content_coverage = _content_coverage(content_section, states["views"], states["view_prose"])

    # Shape summary (R3-F3) — magnitude, not provisioning.
    n_entities = (
        len(_entity_names(schema_state.parsed, schema_state.text or ""))
        if schema_state.status in (Status.PLANNED, Status.PLACEHOLDER) and schema_state.parsed
        else 0
    )
    n_pages = (
        len(states["pages"].parsed[0]) if states["pages"].status in (Status.PLANNED, Status.PLACEHOLDER) and states["pages"].parsed else 0
    )
    n_views = (
        len(states["views"].parsed) if states["views"].status in (Status.PLANNED, Status.PLACEHOLDER) and states["views"].parsed else 0
    )
    n_passes = (
        len(states["ai_passes"].parsed) if states["ai_passes"].status == Status.PLANNED and states["ai_passes"].parsed else 0
    )
    shape = {
        "entities": n_entities,
        "crud_routes": n_entities * 5,  # list/get/create/update/delete per entity
        "pages": n_pages,
        "views": n_views,
        "ai_passes": n_passes,
    }

    counts: Dict[str, int] = {}
    for s in sections:
        counts[s.status] = counts.get(s.status, 0) + 1

    root = inputs.project_root.resolve()

    def _rel(p) -> str:
        try:
            return p.resolve().relative_to(root).as_posix()
        except ValueError:
            return p.as_posix()

    provenance = {
        key: {
            "path": entry.path.as_posix(),
            "resolved_path": _rel(entry.resolved_path),
            "source": entry.source,
            "status_override": entry.status_override,
            "status": states[key].status,
        }
        for key, entry in sorted(inputs.entries.items())
    }

    return WireframePlan(
        project_root=str(root),
        sections=sections,
        input_provenance=provenance,
        merge_warnings=tuple(warnings),
        shape=shape,
        readiness=_readiness(states),
        status_counts=counts,
        content_coverage=content_coverage,
    )
