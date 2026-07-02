"""Concierge core — read-only onboarding survey + readiness assessment ($0, no LLM).

Design constraints (CONCIERGE_MCP_REQUIREMENTS.md):
    * FR-C2/C3 — read-only here; no writes, no cascade/gate. Pure functions of the filesystem.
    * FR-C4 — $0, deterministic. No network, no LLM.
    * FR-C10 — `assess` *wraps* the wireframe machinery (`load_assembly_inputs` /
      `build_wireframe_plan`); it never recomputes provisioning state.
    * FR-C11 — every result is a schema-versioned dict (stable keys), JSON-ready.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Bump on any breaking change to a result shape (FR-C11).
SCHEMA_VERSION = 1

# v1 read-only actions (spike). Write/derive actions are declared but not yet handled.
READ_ACTIONS = ("survey", "assess")
# Write actions return a PREVIEW (WritePlan) from handle_concierge_tool; the CLI is the only path
# that applies it (OQ-7). handle_concierge_tool never writes — it builds the plan.
WRITE_ACTIONS = ("instantiate-kickoff", "log-friction")
# derive-contract returns a PREVIEW (candidate contract + report) or a drift report from
# handle_concierge_tool; the CLI is the only path that writes the contract (OQ-7).
DERIVE_ACTIONS = ("derive-contract",)
DEFERRED_ACTIONS = ()

# --- survey heuristics (all path/name-based; never reads flagged file contents — OQ-8 lean) ---

_REQ_DOC_GLOBS = ("**/*REQUIREMENT*.md", "**/*PRD*.md", "**/*PLAN*.md", "**/*REQUIREMENTS*.md")
# Exact headings the deterministic extraction parser anchors on (F-4 format check).
_EXTRACTION_HEADINGS = ("## Entities", "AI assists", "Owned fields", "Coverage")
_FIXTURE_GLOBS = ("**/*PACKET*.md", "**/seeds/*", "**/*fixture*", "**/TEST_USERS*.md")
# Personal/PII risk flags (F-2) — name/extension only, contents never read.
_PII_NAME_RE = re.compile(
    r"(paystub|payslip|ssn|social.?security|client\d*|offer.?document|exit.?letter|w-?2|1099)",
    re.IGNORECASE,
)
# Directories never worth walking (incl. embedded pipeline scratch — its design docs are
# not the product's requirement docs).
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".startd8", "dist", "build", ".cap-dev-pipe"}


class ConciergeError(RuntimeError):
    """Raised for caller errors (bad project root, unknown action)."""


def _resolve_root(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ConciergeError(f"project_root is not a directory: {root}")
    return root


def _rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def _skipped(p: Path) -> bool:
    """True if *p* lives under a noise dir (incl. embedded pipeline scratch)."""
    return any(part in _SKIP_DIRS for part in p.parts)


def _iter_files(root: Path):
    """Walk *root*, skipping noise dirs. Read-only, bounded by the tree."""
    for p in root.rglob("*"):
        if _skipped(p):
            continue
        yield p


def build_survey(project_root: str | Path) -> Dict[str, Any]:
    """Structured brownfield triage of a project (FR-C5). Read-only, $0.

    Reports: requirement/PRD docs (+ whether they match the extraction format), Pydantic
    model files, test-fixture candidates, and personal/PII-material risk flags. Path/name
    heuristics only — never opens a flagged file.
    """
    root = _resolve_root(project_root)
    logger.info("concierge.survey root=%s", root)

    req_docs: List[Dict[str, Any]] = []
    seen: set[Path] = set()
    for pat in _REQ_DOC_GLOBS:
        for doc in root.glob(pat):
            if doc in seen or not doc.is_file() or _skipped(doc):
                continue
            seen.add(doc)
            req_docs.append({"path": _rel(doc, root), "extraction_format": _matches_extraction_format(doc)})

    model_files: List[str] = []
    fixture_files: List[str] = []
    pii_flags: List[str] = []
    fixture_seen: set[Path] = set()
    for pat in _FIXTURE_GLOBS:
        for f in root.glob(pat):
            if f.is_file() and f not in fixture_seen and not _skipped(f):
                fixture_seen.add(f)
                fixture_files.append(_rel(f, root))

    for p in _iter_files(root):
        if not p.is_file():
            continue
        if _PII_NAME_RE.search(p.name):
            pii_flags.append(_rel(p, root))
        if p.suffix == ".py" and _is_pydantic_module(p):
            model_files.append(_rel(p, root))

    return {
        "schema_version": SCHEMA_VERSION,
        "action": "survey",
        "project_root": str(root),
        "requirement_docs": sorted(req_docs, key=lambda d: d["path"]),
        "model_files": sorted(model_files),
        "fixture_candidates": sorted(fixture_files),
        "pii_risk_flags": sorted(pii_flags),
        "notes": {
            "extraction_format": "docs flagged extraction_format=false need the F-4 reformat path",
            "models": "Pydantic detection is filename/import-based; empty is normal for a carved doc-only root",
            "pii_risk_flags": "name/extension heuristic only — contents are never read (OQ-8)",
            "path_coupling_scan": "deferred — needs a move-target context (FR-C5, not in the read-only spike)",
        },
    }


def _matches_extraction_format(doc: Path) -> bool:
    """True if the doc carries the exact headings the deterministic parser anchors on (F-4).

    Reads only this doc's text (it is a requirement doc the caller pointed us at, not a
    PII-flagged file). Bounded read.
    """
    try:
        text = doc.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return all(h in text for h in _EXTRACTION_HEADINGS)


def _is_pydantic_module(p: Path) -> bool:
    try:
        head = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "BaseModel" in head and "class " in head


def build_assess(project_root: str | Path) -> Dict[str, Any]:
    """Onboarding-readiness report (FR-C6): kickoff-input provenance + the $0-cascade view.

    Wraps the wireframe machinery for the assembly/contract side (FR-C10) — never recomputes
    provisioning state — and scans the kickoff package for input-domain provenance.
    """
    root = _resolve_root(project_root)
    logger.info("concierge.assess root=%s", root)

    return {
        "schema_version": SCHEMA_VERSION,
        "action": "assess",
        "project_root": str(root),
        "kickoff_inputs": _assess_kickoff_inputs(root),
        "cascade": _assess_cascade(root),
    }


def _assess_kickoff_inputs(root: Path) -> Dict[str, Any]:
    """Per kickoff input domain: present? and its declared provenance (honest, not graded)."""
    inputs_dir = root / "docs" / "kickoff" / "inputs"
    domains = ("business-targets", "observability", "conventions", "build-preferences")
    out: Dict[str, Any] = {"inputs_dir": _rel(inputs_dir, root), "domains": {}}
    for domain in domains:
        f = inputs_dir / f"{domain}.yaml"
        if not f.is_file():
            out["domains"][domain] = {"status": "absent"}
            continue
        provenance = None
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            provenance = data.get("provenance_default")
        except (OSError, yaml.YAMLError) as exc:
            out["domains"][domain] = {"status": "invalid", "error": str(exc)}
            continue
        out["domains"][domain] = {"status": "present", "provenance_default": provenance}

    # Stakeholder Panel roster (FR-4): structurally validated, not just present-checked. Also carries
    # the authored-vs-consumable distinction (R2-S5) so an early adopter who authors a roster after
    # M0 is not misled into expecting live-panel behavior that has not shipped yet.
    out["domains"]["stakeholders"] = _assess_stakeholder_roster(inputs_dir)
    return out


def _assess_stakeholder_roster(inputs_dir: Path) -> Dict[str, Any]:
    """Roster readiness (absent/invalid/present) + whether the live panel can consume it yet.

    Local import so a partial checkout without the ``stakeholder_panel`` package degrades to a
    graceful "unavailable" rather than crashing the whole assess (parity with the wireframe import).
    """
    try:
        from startd8.stakeholder_panel import PANEL_CONSUMABLE, assess_roster
    except ImportError:  # pragma: no cover - defensive, package ships with the SDK
        return {"status": "unavailable", "error": "stakeholder_panel package not importable"}

    result = dict(assess_roster(inputs_dir / "stakeholders.yaml"))
    # A validated roster is "authored"; "consumable" tracks whether the live panel exists to query it.
    result["authored"] = result.get("status") == "present"
    result["consumable"] = bool(PANEL_CONSUMABLE)
    if result["authored"] and not result["consumable"]:
        result["note"] = "roster authored; live Stakeholder Panel ships in a later increment"
    return result


def _assess_cascade(root: Path) -> Dict[str, Any]:
    """The $0-cascade readiness view, delegated to the wireframe machinery (FR-C10)."""
    # Import locally so a missing wireframe dep degrades gracefully rather than at import time.
    from startd8.wireframe import (
        AssemblyInputsError,
        build_wireframe_plan,
        load_assembly_inputs,
    )

    # Prefer the project's machine-readable inventory if present; else convention paths.
    inventory = root / "docs" / "ASSEMBLY_INPUTS.yaml"
    yaml_paths = [str(inventory)] if inventory.is_file() else []
    try:
        resolved = load_assembly_inputs(yaml_paths=yaml_paths, overrides={}, project_root=root)
        plan = build_wireframe_plan(resolved)
    except AssemblyInputsError as exc:
        return {"status": "inputs_error", "error": str(exc)}

    blockers = [
        {"section": s.title, "status": s.status, "consequence": s.consequence}
        for s in plan.sections
        if s.status in ("invalid", "not_defined") and s.consequence
    ]
    return {
        "status": "ok",
        "inventory_used": _rel(inventory, root) if yaml_paths else "(convention paths)",
        "shape": plan.shape,
        "status_counts": plan.status_counts,
        "readiness": plan.readiness,
        "blockers": blockers,
    }


def handle_concierge_tool(action: str, project_root: str | Path, **params: Any) -> Dict[str, Any]:
    """Action dispatch (FR-C1). The single entry the MCP tool and CLI both call.

    Read actions return their report; **write actions return a PREVIEW WritePlan and never touch
    disk** (OQ-7 — only the CLI applies, via ``apply_write_plan``). Deferred actions return a
    structured ``not_implemented`` rather than raising, so a caller discovers scope without a crash.
    """
    if action == "survey":
        return build_survey(project_root)
    if action == "assess":
        return build_assess(project_root)
    if action == "instantiate-kickoff":
        from .writes import build_instantiate_plan
        return build_instantiate_plan(
            project_root,
            params.get("posture", "prototype"),
            with_authoring=bool(params.get("with_authoring", False)),
        )
    if action == "log-friction":
        from .writes import ConciergeWriteError, build_friction_entry
        try:
            return build_friction_entry(
                project_root,
                friction=params["friction"],
                what_happened=params["what_happened"],
                implication=params["implication"],
                entry_id=params.get("entry_id"),
                timestamp=params.get("timestamp"),
            )
        except KeyError as e:
            raise ConciergeError(f"log-friction requires field {e}") from None
        except ConciergeWriteError as e:
            raise ConciergeError(str(e)) from None
    if action == "derive-contract":
        import dataclasses

        from .derive import build_derivation, check_drift

        modules = params.get("modules")
        if not modules:
            raise ConciergeError("derive-contract requires `modules` (Pydantic model import paths)")
        pythonpath = params.get("pythonpath") or str(project_root)
        common = dict(project_pythonpath=pythonpath, model_names=params.get("model_names"),
                      exclude_models=params.get("exclude_models"))
        # Preview by default; `check` reads the live contract and returns drift (no write either way).
        if params.get("check"):
            live = params.get("live_schema_text")
            if live is None:
                live_file = Path(params.get("live_schema_path") or (Path(project_root) / "prisma" / "schema.prisma"))
                if not live_file.is_file():
                    raise ConciergeError(f"--check needs a live schema; none at {live_file}")
                live = live_file.read_text(encoding="utf-8")
            return dataclasses.asdict(check_drift(modules, live_schema_text=live, **common))
        return dataclasses.asdict(build_derivation(modules, **common))
    if action in DEFERRED_ACTIONS:
        return {
            "schema_version": SCHEMA_VERSION,
            "action": action,
            "status": "not_implemented",
            "detail": f"'{action}' is deferred.",
        }
    raise ConciergeError(
        f"unknown action '{action}'. Known: {READ_ACTIONS + WRITE_ACTIONS + DERIVE_ACTIONS}."
    )


def handle_concierge_read(action: str, project_root: str | Path, **params: Any) -> Dict[str, Any]:
    """Read-only dispatch floor for the conversational front-end (FR-13, second enforcement layer).

    The agentic Concierge surface routes **every** tool call through here. It hard-rejects any action
    not in ``READ_ACTIONS`` *before* delegating, so the loop can never reach an
    ``instantiate-kickoff``/``log-friction``/``derive-contract`` branch — independent of what tools
    happened to get registered. This is the structural guarantee behind "assist, not operate": the
    registry allow-list (layer 1) protects the prompt; this entry protects the executor.
    """
    if action not in READ_ACTIONS:
        raise ConciergeError(
            f"concierge chat is read-only; action '{action}' is refused (allowed: {READ_ACTIONS})"
        )
    return handle_concierge_tool(action, project_root, **params)
