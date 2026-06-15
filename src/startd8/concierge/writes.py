"""Concierge write-action builders — pure planners for the write path (FR-C3/C3a/C7/C9).

These compute a **WritePlan** (a JSON-serializable descriptor of intended writes) without
mutating disk. They `stat` to classify per-file status but **never read existing consumer-file
content** (FR-C3a — the read-side disclosure bound): the only content in a plan is what the
Concierge would *write* (template- or entry-derived), never a consumer's existing bytes.

The plan is what the MCP tool returns (preview) and what the CLI converts to `PlannedWrite`s for
the safe-writer. Builders never touch disk beyond `stat`; `apply_write_plan` is the only writer.
"""

from __future__ import annotations

import json
import uuid
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

from .safe_write import ACTION_APPEND, ACTION_NEW, PlannedWrite

logger = get_logger(__name__)

SCHEMA_VERSION = 1
FRICTION_LOG = "concierge-friction.jsonl"
VALID_POSTURES = ("prototype", "production")

# Kickoff-package templates → destination under the consuming project (FR-C7).
_KICKOFF_FILES = [
    ("KICKOFF_INTRO_TEMPLATE.md", "docs/kickoff/KICKOFF_INTRO.md"),
    ("KICKOFF_INPUTS_EXPLAINED_TEMPLATE.md", "docs/kickoff/KICKOFF_INPUTS_EXPLAINED.md"),
    ("inputs/business-targets.yaml", "docs/kickoff/inputs/business-targets.yaml"),
    ("inputs/observability.yaml", "docs/kickoff/inputs/observability.yaml"),
    ("inputs/conventions.yaml", "docs/kickoff/inputs/conventions.yaml"),
    ("inputs/build-preferences.yaml", "docs/kickoff/inputs/build-preferences.yaml"),
]
# Optional authoring trio (--with-authoring): templates the team fills in.
_AUTHORING_FILES = [
    ("REQUIREMENTS_TEMPLATE.md", "docs/kickoff/REQUIREMENTS_TEMPLATE.md"),
    ("PLAN_TEMPLATE.md", "docs/kickoff/PLAN_TEMPLATE.md"),
    ("TEST_USERS_TEMPLATE.md", "docs/kickoff/TEST_USERS_TEMPLATE.md"),
    ("HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md", "docs/kickoff/HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md"),
    ("REQUIREMENTS_AND_PLAN_FORMAT.md", "docs/kickoff/REQUIREMENTS_AND_PLAN_FORMAT.md"),
]

# Posture → resolution of the conventions `provenance_default` placeholder (FR-C7).
# prototype: team plays architect, conventions are templated starters; production: architect
# authors/validates (the placeholder stays an honest "authored-pending" marker).
_CONVENTIONS_PLACEHOLDER = "provenance_default: <authored | templated>"
_POSTURE_CONVENTIONS = {
    "prototype": "provenance_default: templated",
    "production": "provenance_default: authored",
}


class ConciergeWriteError(ValueError):
    """Caller error in a write builder (bad posture, missing field)."""


def _load_template(rel: str) -> str:
    """Read a packaged template (works from a wheel via importlib.resources)."""
    root = resources.files("startd8.concierge_templates")
    return (root / rel).read_text(encoding="utf-8")


def _render_input(rel_template: str, posture: str) -> str:
    text = _load_template(rel_template)
    if rel_template.endswith("conventions.yaml") and _CONVENTIONS_PLACEHOLDER in text:
        text = text.replace(_CONVENTIONS_PLACEHOLDER, _POSTURE_CONVENTIONS[posture])
    return text


def _classify(project_root: Path, rel_dest: str) -> str:
    """Per-file status by `stat` only — never reads content (FR-C3a)."""
    target = project_root / rel_dest
    return "exists" if target.exists() else "new"


def build_instantiate_plan(
    project_root,
    posture: str = "prototype",
    *,
    with_authoring: bool = False,
) -> Dict[str, Any]:
    """Plan the kickoff-package projection into *project_root* (FR-C7). Pure; stat-only."""
    if posture not in VALID_POSTURES:
        raise ConciergeWriteError(f"posture must be one of {VALID_POSTURES}, got {posture!r}")
    root = Path(project_root).expanduser()
    files = list(_KICKOFF_FILES) + (list(_AUTHORING_FILES) if with_authoring else [])

    writes: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for template_rel, dest in files:
        if template_rel.startswith("inputs/"):
            content = _render_input(template_rel, posture)
        else:
            content = _load_template(template_rel)
        status = _classify(root, dest)
        writes.append({
            "path": dest,
            "action": ACTION_NEW,
            "status": status,
            "bytes": len(content.encode("utf-8")),
            "content": content,
        })

    if posture == "production":
        warnings.append(
            "production posture: replace the fictional `owners`/contacts block in "
            "observability.yaml before any non-demo use (it ships .test-flagged)."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "action": "instantiate-kickoff",
        "project_root": str(root),
        "posture": posture,
        "with_authoring": with_authoring,
        "writes": writes,
        "warnings": warnings,
    }


def build_friction_entry(
    project_root,
    *,
    friction: str,
    what_happened: str,
    implication: str,
    entry_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Plan one append to the project's `concierge-friction.jsonl` (FR-C9).

    Id is a self-contained ULID-like value (no parse-to-increment, no read of the log — R1-S7).
    `entry_id`/`timestamp` are injectable for deterministic tests; otherwise generated.
    """
    for field_name, value in (("friction", friction), ("what_happened", what_happened), ("implication", implication)):
        if not (value or "").strip():
            raise ConciergeWriteError(f"{field_name} is required and must be non-empty")
    root = Path(project_root).expanduser()
    entry = {
        "id": entry_id or uuid.uuid4().hex,
        "ts": timestamp,  # caller stamps a real time; None is honest "unstamped" until the CLI sets it
        "friction": friction.strip(),
        "what_happened": what_happened.strip(),
        "implication": implication.strip(),
    }
    line = json.dumps(entry, sort_keys=True) + "\n"
    status = _classify(root, FRICTION_LOG)  # exists ⇒ append to it; new ⇒ append creates it
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "log-friction",
        "project_root": str(root),
        "writes": [{
            "path": FRICTION_LOG,
            "action": ACTION_APPEND,
            "status": status,
            "bytes": len(line.encode("utf-8")),
            "append_text": line,
        }],
        "warnings": [],
    }


def to_planned_writes(plan: Dict[str, Any]) -> List[PlannedWrite]:
    """Convert a WritePlan dict (from a builder) into safe-writer `PlannedWrite`s (CLI uses this)."""
    out: List[PlannedWrite] = []
    for w in plan.get("writes", []):
        out.append(PlannedWrite(
            path=w["path"],
            action=w["action"],
            content=w.get("content"),
            append_text=w.get("append_text"),
        ))
    return out
