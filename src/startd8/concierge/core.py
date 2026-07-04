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
import warnings
from pathlib import Path
from typing import Any, Dict, List

import yaml

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Bump on any breaking change to a result shape (FR-C11).
SCHEMA_VERSION = 1

# v1 read-only actions (spike). Write/derive actions are declared but not yet handled.
READ_ACTIONS = ("survey", "assess")
# Write actions return a PREVIEW (WritePlan) from handle_concierge_tool; the CLI is the only path
# that applies it (OQ-7). handle_concierge_tool never writes — it builds the plan.
# M0b rename: `instantiate-kickoff`→`instantiate` (the old value stays dispatchable via
# _ACTION_ALIASES for one release, FR-10).
WRITE_ACTIONS = ("instantiate", "log-friction")
# `derive` returns a PREVIEW (candidate contract + report) or a drift report from
# handle_concierge_tool; the CLI is the only path that writes the contract (OQ-7).
# M0b rename: `derive-contract`→`derive` (old value aliased for one release).
DERIVE_ACTIONS = ("derive",)
DEFERRED_ACTIONS = ()

# FR-10 alias window: the old MCP `ConciergeInput.action` enum values (and any scripted caller that
# keys on the action string) keep dispatching for one release, mapped to their canonical name with a
# DeprecationWarning. Remove this map when the alias window closes.
_ACTION_ALIASES = {
    "instantiate-kickoff": "instantiate",
    "derive-contract": "derive",
}

# The four kickoff input *value* domains — the YAML files under ``docs/kickoff/inputs/``. This is the
# single source of truth shared by concierge assessment (below), project-init shape triage, and the
# red-carpet advisor, so "which inputs count" cannot drift across them. ``stakeholders`` is
# deliberately NOT in this set: it carries a different shape/status set and each consumer handles it
# as a dedicated special case (do not fold it in). The 3-domain stakeholder-authoring set in
# ``stakeholder_panel.input_domains`` is a *different* concept (it excludes ``observability``).
KICKOFF_INPUT_DOMAINS = ("business-targets", "observability", "conventions", "build-preferences")

# --- next-command map (FR-5) -------------------------------------------------------------------
# `assess` names what is missing AND emits the exact next command to move forward (the handoff
# surface). Ported from the retiring Red Carpet advisor (`red_carpet_advisor.py:63-73,348-358`) —
# the ~40-60-LOC command map ONLY, never the ranked playbook (which re-imports the retired metaphor).
#
# CRITICAL (M0 rename): every emitted command MUST resolve in the post-M0 CLI registry. The old
# advisor pointed app/manifest/form/flow gaps at `startd8 kickoff red-carpet --agent`, but after M0
# the metaphor group moved to `kickoff-legacy`, so a bare `startd8 kickoff red-carpet` no longer
# resolves. These constants therefore target the CURRENT kernel surface:
#   * schema/data-model/contract → `startd8 generate contract --promote` (`cli_generate.py:734`)
#   * page/view/screen           → `startd8 screens suggest`            (`cli_screens.py:63`)
#   * app/manifest/form/flow     → `startd8 kickoff instantiate`        (scaffolds the input package)
CMD_GENERATE_CONTRACT_PROMOTE = "startd8 generate contract --promote"
CMD_SCREENS_SUGGEST = "startd8 screens suggest"
CMD_KICKOFF_INSTANTIATE = "startd8 kickoff instantiate"

# The headline next-command when the cascade is not yet ready but no blocker names a more specific
# step — surface the assess report itself as the canonical read-only next move.
CMD_KICKOFF_ASSESS = "startd8 kickoff assess"


def _blocker_command(section: str) -> str | None:
    """Map a cascade-blocker section title → the exact CLI command that advances it (FR-5).

    Re-targeted for the post-M0 kernel surface (see the constants above): no emitted command
    references a `startd8 kickoff <metaphor>` path that moved to `kickoff-legacy`.
    """
    s = section.lower()
    if any(k in s for k in ("schema", "data model", "contract")):
        return CMD_GENERATE_CONTRACT_PROMOTE
    # The "screens" gap (pages/views) routes to the Manifest Suggester — the guided way to decide
    # *which* screens the product needs.
    if any(k in s for k in ("page", "view", "screen")):
        return CMD_SCREENS_SUGGEST
    # Broader app/manifest/form/flow gaps route to `instantiate`, which scaffolds the honest starter
    # input-file package (app.yaml, manifests, forms, flows) at human privilege.
    if any(k in s for k in ("app", "manifest", "form", "flow")):
        return CMD_KICKOFF_INSTANTIATE
    return None

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

    cascade = _assess_cascade(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "assess",
        "project_root": str(root),
        "kickoff_inputs": _assess_kickoff_inputs(root),
        "cascade": cascade,
        # FR-5: the handoff surface — the single exact next command to move forward (may be None
        # when the cascade is fully ready). Per-blocker commands live under cascade.blockers.
        "next_command": _headline_next_command(cascade),
        "deployment": _assess_deployment(root),
    }


def _assess_deployment(root: Path) -> Dict[str, Any]:
    """FR-CDA-1: the deployment-readiness block — declared posture + coherence verdict + readiness.

    Single source (R1-F2): the verdict + `unbound_bindings` come from the SAME in-process
    `evaluate_deploy_coherence` the subprocess Keiyaku wraps — never a second reader of the contract.
    Secret-safe (R1-S9): surfaces only names/counts/status, never secret VALUES from the manifest or
    infra-contract. Degrades gracefully (never crashes assess) on any missing dependency.
    """
    try:
        from startd8.scaffold_codegen.deploy_readiness import (
            evaluate_deploy_coherence,
            find_app_yaml,
        )
        from startd8.scaffold_codegen.manifest import parse_app_manifest
    except ImportError as exc:  # pragma: no cover - defensive, ships with the SDK
        return {"status": "unavailable", "error": str(exc)}

    app_yaml = find_app_yaml(root)
    if app_yaml is None:
        return {"status": "not-declared", "readiness": "not-declared", "reason": "no app.yaml"}

    try:
        manifest = parse_app_manifest(app_yaml.read_text(encoding="utf-8"))
    except Exception as exc:  # malformed app.yaml → fail-closed hard, mirrors the gate
        return {"status": "invalid", "readiness": "unknown", "verdict": "hard",
                "reason": f"app.yaml unparseable (fail-closed): {exc}"}

    # Single source (R1-F2): verdict + unbound + staleness-aware readiness all come from the SAME
    # `evaluate_deploy_coherence` the subprocess wraps — no second reader, no re-derived staleness.
    payload, _exit = evaluate_deploy_coherence(root)

    return {
        "status": "ok",
        "mode": manifest.deployment_mode,
        "deploy": {  # posture — names/flags only, never secret values (R1-S9)
            "target_cloud": manifest.deploy_target_cloud,
            "secrets_backend": manifest.deploy_secrets_backend,
            "trust_gateway": manifest.deploy_trust_gateway,
        },
        "environments": list(manifest.deploy_environments),
        "readiness": payload.get("readiness"),
        "unbound_bindings": payload.get("unbound_bindings"),
        "verdict": payload.get("verdict"),
        "findings": [  # code/severity/message only — no secret values
            {"code": f.get("code"), "severity": f.get("severity"), "message": f.get("message")}
            for f in payload.get("findings", [])
        ],
    }


def _assess_kickoff_inputs(root: Path) -> Dict[str, Any]:
    """Per kickoff input domain: present? and its declared provenance (honest, not graded)."""
    inputs_dir = root / "docs" / "kickoff" / "inputs"
    out: Dict[str, Any] = {"inputs_dir": _rel(inputs_dir, root), "domains": {}}
    for domain in KICKOFF_INPUT_DOMAINS:
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

    # FR-5: each blocker carries the exact next command that advances it (or None where none exists).
    blockers = [
        {
            "section": s.title,
            "status": s.status,
            "consequence": s.consequence,
            "next_command": _blocker_command(s.title),
        }
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


def _headline_next_command(cascade: Dict[str, Any]) -> str | None:
    """FR-5: the single most-actionable next command for the whole assess report.

    The first blocker that names a command wins (blockers are already leverage-ordered by the
    wireframe machinery); if the cascade could not resolve its inputs, point at `assess` itself so
    the human re-runs after fixing the assembly inputs; if everything is ready, no command is needed.
    """
    if cascade.get("status") != "ok":
        return CMD_KICKOFF_ASSESS
    for b in cascade.get("blockers") or []:
        if b.get("next_command"):
            return b["next_command"]
    return None


def handle_concierge_tool(action: str, project_root: str | Path, **params: Any) -> Dict[str, Any]:
    """Action dispatch (FR-C1). The single entry the MCP tool and CLI both call.

    Read actions return their report; **write actions return a PREVIEW WritePlan and never touch
    disk** (OQ-7 — only the CLI applies, via ``apply_write_plan``). Deferred actions return a
    structured ``not_implemented`` rather than raising, so a caller discovers scope without a crash.

    FR-10 alias window: an old action name (``instantiate-kickoff``/``derive-contract``) still
    dispatches, mapped to its canonical name with a ``DeprecationWarning``.
    """
    if action in _ACTION_ALIASES:
        canonical = _ACTION_ALIASES[action]
        warnings.warn(
            f"concierge action '{action}' is deprecated; use '{canonical}'. "
            "This alias will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        action = canonical
    if action == "survey":
        return build_survey(project_root)
    if action == "assess":
        return build_assess(project_root)
    if action == "instantiate":
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
    if action == "derive":
        import dataclasses

        from .derive import build_derivation, check_drift

        modules = params.get("modules")
        if not modules:
            raise ConciergeError("derive requires `modules` (Pydantic model import paths)")
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
