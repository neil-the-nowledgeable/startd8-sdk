"""Drift / staleness checking for the Python contract-codegen path.

The Python sibling of ``frontend_codegen.drift``. The two-stage check is the same operational
idea (R2-S6) — distinguish **stale** (schema changed, file not regenerated; caught cheaply by the
embedded ``schema-sha256``) from **tampered** (schema unchanged, file hand-edited; caught by a full
re-render comparison) — but it is *mirrored, not reused*: a ``.py`` file carries a ``#`` GENERATED
header (not the TS ``//``), and the re-render goes through :func:`render_pydantic_models`. Both are
hardwired in ``frontend_codegen.drift``, so the regexes and renderer differ here.

Exit-code contract: ``0`` in-sync, ``1`` drift (stale/tampered/missing), ``2`` error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from ..frontend_codegen.schema_renderer import schema_sha256

IN_SYNC = 0
DRIFT = 1
ERROR = 2

_HEADER_SHA_RE = re.compile(r"#\s*schema-sha256:\s*([0-9a-f]{64})")
_HEADER_SRC_RE = re.compile(r"#\s*GENERATED from\s+(\S+)")
_HEADER_KIND_RE = re.compile(r"#\s*startd8-artifact:\s*(\S+)")
_HEADER_ENTITY_RE = re.compile(r"#\s*startd8-entity:\s*(\S+)")
# AI-layer artifacts (FR-MA-5) derive from two extra inputs and carry two extra hashes.
_HEADER_PASSES_SHA_RE = re.compile(r"#\s*passes-sha256:\s*([0-9a-f]{64})")
_HEADER_HUMAN_SHA_RE = re.compile(r"#\s*human-inputs-sha256:\s*([0-9a-f]{64})")
_GENERATED_MARKER = "# GENERATED from"

# Artifact kinds whose drift derives from three inputs (schema + ai_passes + human_inputs). Kept in
# sync with ``ai_layer.AI_KINDS`` (literal here to avoid an import cycle at module load).
_AI_KINDS: frozenset = frozenset(
    {"ai-service", "ai-edge-schemas", "ai-pass", "ai-router", "ai-server"}
)


def _renderers() -> Dict[str, Callable[[str, str, Optional[str]], str]]:
    """Map artifact-kind → a ``(schema_text, source_file, entity) -> text`` renderer.

    Imported lazily so this module has no load-order dependency on the renderers. Each backend
    artifact tags its header with ``# startd8-artifact: <kind>`` (and, for per-entity templates,
    ``# startd8-entity: <Name>``) so a single provider/drift path re-renders it with the *right*
    renderer — every backend artifact carries the GENERATED marker, so the kind+entity tags are
    what disambiguate them. ``entity`` is ``None`` for app-wide artifacts.
    """
    from .crud_generator import render_db, render_main, render_routers
    from .derived import (
        render_ai_schemas,
        render_completeness,
        render_export,
        render_requirements,
    )
    from .htmx_generator import (
        render_base_template,
        render_detail_template,
        render_field_error_template,
        render_form_template,
        render_list_template,
        render_web,
    )
    from .pydantic_renderer import render_pydantic_models
    from .sqlmodel_renderer import render_sqlmodel_tables

    return {
        "pydantic-models": lambda s, sf, e: render_pydantic_models(
            s, source_file=sf
        ).text,
        "sqlmodel-tables": lambda s, sf, e: render_sqlmodel_tables(
            s, source_file=sf
        ).text,
        "fastapi-routers": lambda s, sf, e: render_routers(s, sf),
        "fastapi-db": lambda s, sf, e: render_db(s, sf),
        "fastapi-main": lambda s, sf, e: render_main(s, sf),
        "fastapi-web": lambda s, sf, e: render_web(s, sf),
        "htmx-base": lambda s, sf, e: render_base_template(s, sf),
        "htmx-field-error": lambda s, sf, e: render_field_error_template(s, sf),
        "htmx-list": lambda s, sf, e: render_list_template(s, sf, e),
        "htmx-detail": lambda s, sf, e: render_detail_template(s, sf, e),
        "htmx-form": lambda s, sf, e: render_form_template(s, sf, e),
        "python-export": lambda s, sf, e: render_export(s, sf),
        "python-ai-schemas": lambda s, sf, e: render_ai_schemas(s, sf),
        "python-completeness": lambda s, sf, e: render_completeness(s, sf),
        "python-requirements": lambda s, sf, e: render_requirements(s, sf),
    }


def embedded_artifact_kind(ondisk_text: str) -> Optional[str]:
    """The ``startd8-artifact`` kind recorded in a generated file's header, or ``None``."""
    m = _HEADER_KIND_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_entity(ondisk_text: str) -> Optional[str]:
    """The ``startd8-entity`` name recorded in a per-entity template header, or ``None``."""
    m = _HEADER_ENTITY_RE.search(ondisk_text or "")
    return m.group(1) if m else None


@dataclass(frozen=True)
class DriftResult:
    """Outcome of a drift check. ``exit_code`` follows the contract above."""

    status: str  # "in_sync" | "stale" | "tampered" | "missing"
    exit_code: int
    detail: str


def embedded_schema_sha(ondisk_text: str) -> Optional[str]:
    """The ``schema-sha256`` recorded in a generated file's header, or ``None``."""
    m = _HEADER_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_source_file(ondisk_text: str) -> Optional[str]:
    """The ``GENERATED from <source_file>`` label recorded in a generated header, or ``None``."""
    m = _HEADER_SRC_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_passes_sha(ondisk_text: str) -> Optional[str]:
    """The ``passes-sha256`` recorded in an AI-layer file's header, or ``None``."""
    m = _HEADER_PASSES_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_human_sha(ondisk_text: str) -> Optional[str]:
    """The ``human-inputs-sha256`` recorded in an AI-layer file's header, or ``None``."""
    m = _HEADER_HUMAN_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def ai_layer_stale_reason(
    ondisk_text: str,
    *,
    schema_sha: str,
    passes_sha: str,
    human_sha: str,
) -> Optional[str]:
    """For an AI-layer file, return why it is **stale**, or ``None`` if all three inputs match.

    An AI-layer artifact derives from three inputs (schema + ai_passes + human_inputs), so it is
    stale if **any one** of the embedded hashes differs from the current input hash (FR-MA-5). A
    missing embedded hash counts as stale (header was stripped or predates the AI-layer format).
    This is the pure three-hash core; :func:`check_drift` (wired in M-C) calls it for ``_AI_KINDS``.
    """
    checks = (
        ("schema", embedded_schema_sha(ondisk_text), schema_sha),
        ("ai_passes", embedded_passes_sha(ondisk_text), passes_sha),
        ("human_inputs", embedded_human_sha(ondisk_text), human_sha),
    )
    for label, embedded, current in checks:
        if embedded is None:
            return f"missing {label}-sha256 header"
        if embedded != current:
            return (
                f"{label} changed (header {embedded[:12]}… != current {current[:12]}…) — regenerate"
            )
    return None


def is_owned_generated_file(ondisk_text: str) -> bool:
    """True if *ondisk_text* is a file this generator produced (carries the GENERATED header).

    Necessary but **not** sufficient to skip in the pipeline — a stale/hand-edited file also
    carries the header. Pair with :func:`owned_file_in_sync` before treating it as provided.
    """
    text = ondisk_text or ""
    return _GENERATED_MARKER in text and embedded_schema_sha(text) is not None


def owned_file_in_sync(schema_text: str, ondisk_text: str) -> bool:
    """True iff *ondisk_text* is an owned generated file that is **currently in-sync**.

    The safe predicate for the pipeline skip-hook: header presence alone is rejected; the file
    must re-render byte-identically from the current schema. The embedded source-label is
    recovered so the re-render's header line matches (avoiding a false "tampered"). Any doubt →
    ``False`` (the caller falls through to the LLM — a safe failure).
    """
    if not is_owned_generated_file(ondisk_text):
        return False
    source_file = embedded_source_file(ondisk_text) or "prisma/schema.prisma"
    return (
        check_drift(schema_text, ondisk_text, source_file=source_file).status
        == "in_sync"
    )


def _ai_renderers():
    """Map AI artifact-kind → ``(schema, manifest, human, source_file, entity) -> text`` renderer."""
    from .ai_layer import (
        render_ai_pass,
        render_ai_routes,
        render_ai_service,
        render_edge_schemas,
        render_server,
    )

    return {
        "ai-service": lambda s, m, h, sf, e: render_ai_service(s, m, h, sf),
        "ai-edge-schemas": lambda s, m, h, sf, e: render_edge_schemas(s, m, h, sf),
        "ai-pass": lambda s, m, h, sf, e: render_ai_pass(s, m, h, sf, e),
        "ai-router": lambda s, m, h, sf, e: render_ai_routes(s, m, h, sf),
        "ai-server": lambda s, m, h, sf, e: render_server(s, m, h, sf),
    }


def _check_ai_drift(
    schema_text, manifest_text, human_inputs_text, ondisk_text, source_file, kind
) -> DriftResult:
    """Drift for an AI-layer file: stale if any of schema/ai_passes/human_inputs changed (FR-MA-5)."""
    if manifest_text is None:
        return DriftResult(
            "error", ERROR, "AI-layer drift check requires the ai_passes manifest"
        )
    reason = ai_layer_stale_reason(
        ondisk_text,
        schema_sha=schema_sha256(schema_text),
        passes_sha=schema_sha256(manifest_text),
        human_sha=schema_sha256(human_inputs_text or ""),
    )
    if reason is not None:
        status = "tampered" if "missing" in reason else "stale"
        return DriftResult(status, DRIFT, reason)
    renderer = _ai_renderers().get(kind)
    if renderer is None:
        return DriftResult("tampered", DRIFT, f"unknown AI artifact kind ({kind!r})")
    rendered = renderer(
        schema_text, manifest_text, human_inputs_text, source_file, embedded_entity(ondisk_text)
    )
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned AI file was hand-edited (differs from a fresh render of the unchanged inputs)",
        )
    return DriftResult("in_sync", IN_SYNC, "owned AI file matches schema + manifest + human-inputs")


def check_drift(
    schema_text: str,
    ondisk_text: Optional[str],
    *,
    source_file: str = "prisma/schema.prisma",
    manifest_text: Optional[str] = None,
    human_inputs_text: Optional[str] = None,
) -> DriftResult:
    """Compare an on-disk owned file against its source contract(s). No writes.

    ``ondisk_text is None`` means the file is absent (drift — it should exist). Otherwise: a
    missing/old embedded hash means tampered/stale; matching hash with differing bytes means
    tampered; matching hash and bytes means in-sync. AI-layer kinds (``_AI_KINDS``) derive from three
    inputs and are routed to the three-hash check (needs *manifest_text*/*human_inputs_text*).
    """
    if ondisk_text is None:
        return DriftResult("missing", DRIFT, "owned file does not exist on disk")

    kind = embedded_artifact_kind(ondisk_text)
    if kind in _AI_KINDS:
        return _check_ai_drift(
            schema_text, manifest_text, human_inputs_text, ondisk_text, source_file, kind
        )

    current_sha = schema_sha256(schema_text)
    embedded = embedded_schema_sha(ondisk_text)
    if embedded is None:
        return DriftResult(
            "tampered",
            DRIFT,
            "no schema-sha256 header — file was not generated or the header was stripped",
        )
    if embedded != current_sha:
        return DriftResult(
            "stale",
            DRIFT,
            f"schema changed (header {embedded[:12]}… != current {current_sha[:12]}…) "
            f"— regenerate",
        )

    kind = embedded_artifact_kind(ondisk_text)
    renderer = _renderers().get(kind or "")
    if renderer is None:
        return DriftResult(
            "tampered",
            DRIFT,
            f"unknown or missing startd8-artifact kind ({kind!r}) — cannot verify",
        )
    rendered = renderer(schema_text, source_file, embedded_entity(ondisk_text))
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned file was hand-edited (content differs from a fresh render of the "
            "unchanged schema)",
        )
    return DriftResult("in_sync", IN_SYNC, "owned file matches the schema")
