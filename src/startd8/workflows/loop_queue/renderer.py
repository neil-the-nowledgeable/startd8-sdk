# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Agent-surface review-template renderer (FR-20).

Produces a **fully substituted**, self-contained markdown bundle on disk that
any VASI surface's agent opens and follows. Two renderers:

1. **Default** — shell out to the ``new-cnvrg-rvw-prmpt`` script (the proven
   Capability-Delivery-Loop generator). Location resolution order:
   ``LoopQueueConfig.renderer_script`` → ``$STARTD8_CRP_RENDERER`` →
   ``~/Documents/dev/cap-dev-pipe/new-cnvrg-rvw-prmpt.sh``.
2. **Project override** — ``agent_template_path`` markdown using safe
   ``{{slot}}`` placeholders only (FR-20.2/20.3). Substitution happens here,
   at render time; any placeholder left unsubstituted fails closed — the
   agent never sees a live slot.

Rendered bundles are cached in the job artifact dir keyed by a content hash of
the ``CrpReviewRequest`` + round + template bytes (FR-14 / Mottainai).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from ...logging_config import get_logger
from .models import (
    CrpReviewRequest,
    LoopQueueBlockedError,
    LoopQueueValidationError,
    ReflectiveRequirementsRequest,
    ResearchRequest,
)

logger = get_logger(__name__)

DEFAULT_RENDERER_SCRIPT = Path(
    "~/Documents/dev/cap-dev-pipe/new-cnvrg-rvw-prmpt.sh"
).expanduser()

_SLOT_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_SINGLE_BRACE_FIELD_RE = re.compile(r"(?<!\{)\{[a-zA-Z_][a-zA-Z0-9_]*\}(?!\})")

DEFAULT_REFLECTIVE_TEMPLATE = """# Reflective Requirements — {{scope}}

You are draining a Workflow Loop Queue `reflective-requirements` job.
Follow the **reflective-requirements** skill process (draft requirements →
plan → reflect planning insights → update requirements + plan). Do **not**
start CRP review or implementation in this drain.

## Write targets (absolute)

| Artifact | Path |
|----------|------|
| Requirements | `{{requirements_path}}` |
| Plan | `{{plan_path}}` |

Create or update both markdown files. Prefer the project's existing
requirements/plan shape when present.

## Done when

1. Both paths exist as non-empty `.md` files.
2. You write `drain-result.json` at the path from the Drain Hand-off with
   `ok: true`, `paths_written` exactly matching those two paths, and
   `round_number: 1`.
3. Chat/UI reply is a short confirmation only (paths + that reflective loop
   finished). Do not paste the full documents into chat.
"""

DEFAULT_RESEARCH_TEMPLATE = """# Research Job — {{scope}}

You are draining a Workflow Loop Queue `research` job. Produce durable
findings from the investigation brief. Do **not** start CRP review or
implementation coding unless the brief's deliverables explicitly require a
small spike (and then keep spikes behind flags / gallery toggles).

## Inputs / outputs (absolute)

| Artifact | Path | Role |
|----------|------|------|
| Brief (read; may update status pointer) | `{{brief_path}}` | Investigation brief — trust **code** over stale prose |
| Findings (write) | `{{findings_path}}` | Ranked shortlist, open-question answers, API/spike notes |

Optional focus: `{{focus_file}}`

## Method

1. Read the brief end-to-end; verify claims against the real codebase.
2. Use a few parallel agents when the brief asks for multi-angle research
   (code inventory, candidate scoring, perf, boundary).
3. Write `{{findings_path}}` covering the brief's expected deliverables
   (ranked shortlist, spikes/status, deferred list, open questions).
4. Optionally update the brief's status line to point at the findings doc.
5. Do not invent a new WLQ recipe from inside this drain.

## Done when

1. `{{findings_path}}` exists as a non-empty `.md` file.
2. You write `drain-result.json` at the path from the Drain Hand-off with
   `ok: true`, `paths_written` containing exactly that findings path, and
   `round_number: 1`.
3. Chat/UI reply is a short confirmation only (paths + that research
   finished). Do not paste the full findings into chat.
"""


def resolve_renderer_script(configured: Optional[Path] = None) -> Path:
    """Resolve the default bundle renderer script path (may not exist yet)."""
    if configured:
        return Path(configured).expanduser()
    env = os.environ.get("STARTD8_CRP_RENDERER")
    if env:
        return Path(env).expanduser()
    return DEFAULT_RENDERER_SCRIPT


def bundle_cache_key(
    request: CrpReviewRequest,
    round_number: int,
    template_bytes: Optional[bytes] = None,
) -> str:
    """FR-14 content hash: intent + round + (optional) template content."""
    h = hashlib.sha256()
    h.update(request.content_hash().encode("ascii"))
    h.update(f":r{round_number}:".encode("ascii"))
    if template_bytes is not None:
        h.update(template_bytes)
    return h.hexdigest()[:12]


def _slot_values(
    request: CrpReviewRequest,
    round_number: int,
    applied_ids: List[str],
    rejected_ids: List[str],
) -> Dict[str, str]:
    """Slots available to ``agent_template_path`` project templates."""
    return {
        "plan_path": request.plan_path or "",
        "requirements_path": request.requirements_path or "",
        "scope": request.scope,
        "round_number": str(round_number),
        "max_rounds": str(request.max_rounds),
        "substantially_addressed_threshold": str(
            request.substantially_addressed_threshold
        ),
        "max_suggestions": str(request.max_suggestions),
        "applied_ids": ", ".join(applied_ids) or "(none)",
        "rejected_ids": ", ".join(rejected_ids) or "(none)",
        "focus_file": request.focus_file or "",
        "source_paths": "\n".join(str(p) for p in request.source_paths),
    }


def _render_slot_template(
    template_text: str,
    slots: Dict[str, str],
    template_path: Path,
) -> str:
    """Substitute ``{{slot}}`` placeholders; fail closed on unknown slots."""
    forbidden = sorted(set(_SINGLE_BRACE_FIELD_RE.findall(template_text)))
    if forbidden:
        raise LoopQueueValidationError(
            f"agent template {template_path} contains forbidden single-brace "
            f"fields {forbidden}; use safe {{{{slot}}}} placeholders"
        )
    unknown = sorted(
        {name for name in _SLOT_RE.findall(template_text) if name not in slots}
    )
    if unknown:
        raise LoopQueueValidationError(
            f"agent template {template_path} uses unknown slots: {unknown}; "
            f"available: {sorted(slots)}"
        )
    return _SLOT_RE.sub(lambda m: slots[m.group(1)], template_text)


def render_bundle(
    request: CrpReviewRequest,
    round_number: int,
    artifact_dir: Path,
    applied_ids: Optional[List[str]] = None,
    rejected_ids: Optional[List[str]] = None,
    renderer_script: Optional[Path] = None,
) -> Path:
    """Render (or reuse from cache) the agent-surface review bundle.

    Returns the absolute path of the bundle markdown (FR-20.1).
    """
    applied_ids = applied_ids or []
    rejected_ids = rejected_ids or []
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    template_bytes: Optional[bytes] = None
    template_path: Optional[Path] = None
    if request.agent_template_path:
        template_path = Path(request.agent_template_path)
        if not template_path.is_file():
            raise LoopQueueBlockedError(
                f"agent_template_path vanished: {template_path}"
            )
        template_bytes = template_path.read_bytes()

    key = bundle_cache_key(request, round_number, template_bytes)
    bundle_path = artifact_dir / f"bundle-r{round_number}-{key}.md"
    if bundle_path.is_file():
        logger.info("Reusing cached WLQ bundle %s (Mottainai/FR-14)", bundle_path)
        return bundle_path

    if template_path is not None:
        assert template_bytes is not None
        slots = _slot_values(request, round_number, applied_ids, rejected_ids)
        rendered = _render_slot_template(
            template_bytes.decode("utf-8"), slots, template_path
        )
        bundle_path.write_text(rendered, encoding="utf-8")
        logger.info("Rendered WLQ bundle from project template: %s", bundle_path)
        return bundle_path

    script = resolve_renderer_script(renderer_script)
    if not script.is_file():
        raise LoopQueueBlockedError(
            f"default bundle renderer script not found: {script} "
            "(set LoopQueueConfig.renderer_script or $STARTD8_CRP_RENDERER, "
            "or provide agent_template_path)"
        )

    cmd: List[str] = [str(script)]
    if request.plan_path:
        cmd += ["--plan", request.plan_path]
    if request.requirements_path:
        cmd += ["--requirements", request.requirements_path]
    cmd += [
        "--rounds",
        str(request.max_rounds),
        "--threshold",
        str(request.substantially_addressed_threshold),
        "--max-suggestions",
        str(request.max_suggestions),
        "--output",
        str(bundle_path),
    ]
    if request.focus_file:
        cmd += ["--focus-file", request.focus_file]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not bundle_path.is_file():
        raise LoopQueueBlockedError(
            f"bundle renderer failed (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    generated = bundle_path.read_text(encoding="utf-8")
    memory = (
        "# WLQ authoritative drain context\n\n"
        f"- **Round to append:** R{round_number}\n"
        f"- **Applied IDs (do not re-propose):** "
        f"{', '.join(applied_ids) or '(none)'}\n"
        f"- **Rejected IDs (do not re-propose):** "
        f"{', '.join(rejected_ids) or '(none)'}\n"
        "- This round number is derived from the source documents. Do not "
        "replace or increment it.\n\n---\n\n"
    )
    bundle_path.write_text(memory + generated, encoding="utf-8")
    logger.info("Rendered WLQ bundle via %s: %s", script.name, bundle_path)
    return bundle_path


def render_reflective_bundle(
    request: ReflectiveRequirementsRequest,
    artifact_dir: Path,
) -> Path:
    """Render the agent-surface reflective-requirements instruction bundle."""
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    template_bytes: Optional[bytes] = None
    template_label = Path("<default-reflective-template>")
    if request.agent_template_path:
        template_path = Path(request.agent_template_path)
        if not template_path.is_file():
            raise LoopQueueBlockedError(
                f"agent_template_path vanished: {template_path}"
            )
        template_bytes = template_path.read_bytes()
        template_label = template_path
        template_text = template_bytes.decode("utf-8")
    else:
        template_text = DEFAULT_REFLECTIVE_TEMPLATE
        template_bytes = template_text.encode("utf-8")

    key = hashlib.sha256(
        request.content_hash().encode("ascii") + b":" + template_bytes
    ).hexdigest()[:12]
    bundle_path = artifact_dir / f"bundle-reflective-{key}.md"
    if bundle_path.is_file():
        logger.info("Reusing cached reflective bundle %s", bundle_path)
        return bundle_path

    slots = {
        "scope": request.scope,
        "requirements_path": str(Path(request.requirements_path).resolve()),
        "plan_path": str(Path(request.plan_path).resolve()),
        "source_paths": "\n".join(str(p.resolve()) for p in request.source_paths),
    }
    rendered = _render_slot_template(template_text, slots, template_label)
    bundle_path.write_text(rendered, encoding="utf-8")
    logger.info("Rendered reflective bundle: %s", bundle_path)
    return bundle_path.resolve()


def render_research_bundle(
    request: ResearchRequest,
    artifact_dir: Path,
) -> Path:
    """Render the agent-surface research instruction bundle."""
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    template_bytes: Optional[bytes] = None
    template_label = Path("<default-research-template>")
    if request.agent_template_path:
        template_path = Path(request.agent_template_path)
        if not template_path.is_file():
            raise LoopQueueBlockedError(
                f"agent_template_path vanished: {template_path}"
            )
        template_bytes = template_path.read_bytes()
        template_label = template_path
        template_text = template_bytes.decode("utf-8")
    else:
        template_text = DEFAULT_RESEARCH_TEMPLATE
        template_bytes = template_text.encode("utf-8")

    key = hashlib.sha256(
        request.content_hash().encode("ascii") + b":" + template_bytes
    ).hexdigest()[:12]
    bundle_path = artifact_dir / f"bundle-research-{key}.md"
    if bundle_path.is_file():
        logger.info("Reusing cached research bundle %s", bundle_path)
        return bundle_path

    slots = {
        "scope": request.scope,
        "brief_path": str(Path(request.brief_path).resolve()),
        "findings_path": str(Path(request.findings_path).resolve()),
        "focus_file": (
            str(Path(request.focus_file).resolve()) if request.focus_file else "(none)"
        ),
        "source_paths": "\n".join(str(p.resolve()) for p in request.source_paths),
    }
    rendered = _render_slot_template(template_text, slots, template_label)
    bundle_path.write_text(rendered, encoding="utf-8")
    logger.info("Rendered research bundle: %s", bundle_path)
    return bundle_path.resolve()
