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
from dataclasses import dataclass
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
    # Stakeholder Panel roster (FR-1/FR-3). Authoring surface only in M0; the live panel that
    # queries these personas ships later. Manifest key auto-derives to "stakeholders".
    ("inputs/stakeholders.yaml", "docs/kickoff/inputs/stakeholders.yaml"),
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

# FR-CDA-3: posture → the DEFAULT deployment.mode it implies. A default seed, NEVER a force: the
# app.yaml's declared `deployment.mode` (derived later from the data model) always wins; a mismatch
# is an ADVISORY, never an error. Mode and posture stay independent declared fields (deployment-mode
# OQ-5). A production *desktop/CLI* tool legitimately running `installed` is a named non-conflict.
_POSTURE_DEPLOYMENT_MODE = {
    "prototype": "installed",
    "production": "deployed",
}


def _deployment_default(project_root: Path, posture: str) -> Dict[str, Any]:
    """Resolve the posture's deployment-mode default + any advisory (FR-CDA-3, the 3-step policy).

    (1) read a declared `deployment.mode` from an existing app.yaml (if any); (2) the posture seeds a
    default when unset; (3) a declared mode that disagrees with the posture mapping is KEPT, with an
    advisory (never an error). Read-only, $0; degrades to "no declared mode" on any parse failure.
    """
    implied = _POSTURE_DEPLOYMENT_MODE[posture]
    declared: Optional[str] = None
    try:
        from startd8.scaffold_codegen.deploy_readiness import find_app_yaml
        from startd8.scaffold_codegen.manifest import parse_app_manifest

        app_yaml = find_app_yaml(project_root)
        if app_yaml is not None:
            declared = parse_app_manifest(app_yaml.read_text(encoding="utf-8")).deployment_mode
    except Exception:
        declared = None  # no readable/declared mode → the default simply applies

    out: Dict[str, Any] = {"posture": posture, "implied_mode": implied, "declared_mode": declared}
    if declared is None:
        out["effective_mode"] = implied
        out["source"] = "seeded-from-posture"
    else:
        out["effective_mode"] = declared  # declared always wins
        out["source"] = "declared"
        if declared != implied:
            if posture == "production" and declared == "installed":
                out["advisory"] = (
                    "production posture with `deployment.mode: installed` — legitimate for a "
                    "desktop/CLI tool; keeping the declared mode (not a conflict).")
            else:
                out["advisory"] = (
                    f"posture '{posture}' implies `deployment.mode: {implied}` but app.yaml declares "
                    f"'{declared}' — keeping the declared value (advisory, not an error).")
    return out


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

    # FR-CDA-3: surface the posture's deployment-mode default (+ advisory on any declared conflict).
    deployment_default = _deployment_default(root, posture)
    if deployment_default.get("advisory"):
        warnings.append(deployment_default["advisory"])

    return {
        "schema_version": SCHEMA_VERSION,
        "action": "instantiate-kickoff",
        "project_root": str(root),
        "posture": posture,
        "with_authoring": with_authoring,
        "writes": writes,
        "warnings": warnings,
        "deployment_default": deployment_default,
    }


# --------------------------------------------------------------------------- #
# Template manifest — the read-only download surface (Welcome Mat 2.0, FR-WM2-1..4).
#
# The download set is the SAME inventory `build_instantiate_plan` writes (`_KICKOFF_FILES` +
# `_AUTHORING_FILES`) — derived here, never re-listed, so the two consumers can never drift (P-E).
# Files are addressed by a closed `key` slug (never a caller path → no traversal, NR-3).
# --------------------------------------------------------------------------- #

# group label → the (template_rel, dest) list it covers. The single source of truth.
_TEMPLATE_GROUPS: List[tuple] = [
    ("package", _KICKOFF_FILES),
    ("authoring", _AUTHORING_FILES),
]


@dataclass(frozen=True)
class TemplateEntry:
    """One downloadable kickoff template, keyed by a closed slug (FR-WM2-1/2/4)."""

    key: str            # closed-vocabulary slug, e.g. "kickoff-intro" (never a path)
    template_rel: str   # source under `concierge_templates/` (the `_load_template` arg)
    dest: str           # where instantiate would write it (`docs/kickoff/…`) — also the zip member path
    group: str          # "package" | "authoring"
    label: str          # human label for the index


def is_safe_template_dest(dest: str) -> bool:
    """A manifest `dest` must be a safe **relative** path (zip-slip guard, R3-S6): no leading slash,
    no `..` / empty segment, no backslash. Validated at accessor build time, not at serve time."""
    if not dest or dest.startswith("/") or "\\" in dest:
        return False
    return all(seg not in ("", "..") for seg in dest.split("/"))


def _template_key(dest: str) -> str:
    """A stable, single-segment slug from the destination basename (no slashes ⇒ no path converter)."""
    base = dest.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return stem.lower().replace("_", "-")


def _template_label(dest: str) -> str:
    base = dest.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return stem.replace("_", " ").replace("-", " ").strip().title()


def kickoff_template_manifest() -> List[TemplateEntry]:
    """The complete downloadable set, derived from the instantiate inventory (FR-WM2-4/11/16).

    Raises ``ConciergeWriteError`` on a duplicate key or an unsafe ``dest`` — a CI/bijection guard
    that fires before any route can serve a bad row (FR-WM2-16).
    """
    entries: List[TemplateEntry] = []
    seen: Dict[str, str] = {}
    for group, files in _TEMPLATE_GROUPS:
        for template_rel, dest in files:
            if not is_safe_template_dest(dest):
                raise ConciergeWriteError(f"unsafe template dest (zip-slip guard): {dest!r}")
            key = _template_key(dest)
            if key in seen:
                raise ConciergeWriteError(
                    f"duplicate template key {key!r} (from {dest!r} and {seen[key]!r})"
                )
            seen[key] = dest
            entries.append(TemplateEntry(
                key=key, template_rel=template_rel, dest=dest, group=group,
                label=_template_label(dest),
            ))
    return entries


def get_template_entry(key: str) -> Optional[TemplateEntry]:
    """Exact-match lookup against the closed key set (an unknown/encoded key ⇒ ``None`` ⇒ 404)."""
    return next((e for e in kickoff_template_manifest() if e.key == key), None)


def render_template_content(entry: TemplateEntry, posture: str = "prototype") -> str:
    """The exact bytes `instantiate` would write for *entry* at *posture* — the SAME content path
    (`_render_input` for inputs, `_load_template` otherwise), so download ≡ instantiate (FR-WM2-4)."""
    if posture not in VALID_POSTURES:
        raise ConciergeWriteError(f"posture must be one of {VALID_POSTURES}, got {posture!r}")
    if entry.template_rel.startswith("inputs/"):
        return _render_input(entry.template_rel, posture)
    return _load_template(entry.template_rel)


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


def compute_drift(plan: Dict[str, Any], project_root) -> Dict[str, Any]:
    """FR-C15 idempotency/drift verdict. **CLI-only — reads existing files** (never wired to MCP,
    so the FR-C3a disclosure bound is not crossed: the human-run CLI reads at its own privilege).

    Per template file (``new`` writes): ``matches`` (== template) / ``diverged`` (exists, differs)
    / ``absent``. Verdict: ``drifted`` if any diverged; ``partial`` if any absent and none
    diverged; ``complete`` if all match.
    """
    root = Path(project_root).expanduser()
    files: List[Dict[str, str]] = []
    diverged = absent = 0
    for w in plan.get("writes", []):
        if w.get("action") != ACTION_NEW:
            continue
        target = root / w["path"]
        if not target.exists():
            state = "absent"; absent += 1
        elif target.read_text(encoding="utf-8") == (w.get("content") or ""):
            state = "matches"
        else:
            state = "diverged"; diverged += 1
        files.append({"path": w["path"], "state": state})
    verdict = "drifted" if diverged else ("partial" if absent else "complete")
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "instantiate-kickoff",
        "mode": "check",
        "project_root": str(root),
        "verdict": verdict,
        "diverged": diverged,
        "absent": absent,
        "files": files,
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
