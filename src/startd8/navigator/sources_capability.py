"""Capability-index YAML → Nodes (startd8.sdk.capabilities.yaml).

Adapted from ContextCore ``navigator/sources.py``; prefers SDK ``wont`` field
(CL-13) and falls back to ``anti_patterns``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .models import Node, NodeEvidence, default_confidence, derive_status
from .git_lives import prefer_git_ref
from .view_definition import (
    CAPABILITY_DEFINITION,
    DEFINITION_REGISTRY,
    resolve,
    to_render_profile,
)

DEFAULT_CAPABILITY_INDEX = Path("docs/capability-index/startd8.sdk.capabilities.yaml")
_ROUTE_STATES = {
    "sdk_emitted",
    "owned_elsewhere",
    "declared_unimplemented",
    "external_convention",
}

# FR-5: the capability-index domain is a thin ``CAPABILITY_DEFINITION`` delta over the SAME base as the
# requirements domain (the cross-domain reuse proof), PROJECTED to the existing RenderProfile. Byte-for-
# byte equal to the former standalone literal — no "Your app" bleed, renderers unchanged.
CAPABILITY_PROFILE = to_render_profile(resolve(CAPABILITY_DEFINITION, DEFINITION_REGISTRY))


def default_capability_index_path() -> Path:
    """Prefer CWD docs/, else repo root relative to this package."""
    cwd = Path.cwd() / DEFAULT_CAPABILITY_INDEX
    if cwd.is_file():
        return cwd
    repo = Path(__file__).resolve().parents[3]
    return repo / DEFAULT_CAPABILITY_INDEX


def _as_tuple(value: Any) -> tuple:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    text = str(value).strip()
    return (text,) if text else ()


def _wont(cap: Dict[str, Any]) -> tuple:
    if cap.get("wont") is not None:
        return _as_tuple(cap.get("wont"))
    return _as_tuple(cap.get("anti_patterns"))


def _description_text(cap: Dict[str, Any]) -> str:
    desc = cap.get("description")
    if isinstance(desc, dict):
        for key in ("developer", "human", "agent"):
            if desc.get(key):
                return str(desc[key]).strip()
    if isinstance(desc, str) and desc.strip():
        return desc.strip()
    return str(cap.get("summary", "")).strip()


def _orientation_from_audiences(audiences: tuple) -> str:
    has_human = any(a in ("human", "gtm", "workflow_developer", "developer") for a in audiences)
    has_system = any(a in ("agent", "system", "ai_agent") for a in audiences)
    if has_human and has_system:
        return "bridge"
    if has_human:
        return "human"
    if has_system:
        return "system"
    return ""


def _route_state(cap: Dict[str, Any], has_code_evidence: bool) -> str:
    authored = str(cap.get("route_state", "")).strip()
    if authored in _ROUTE_STATES:
        return authored
    return "sdk_emitted" if has_code_evidence else "declared_unimplemented"


def node_from_capability(cap: Dict[str, Any], *, repo: Optional[Path] = None) -> Node:
    evidence_raw = cap.get("evidence") or []
    repo_root = Path(repo) if repo else Path.cwd()
    lives = tuple(
        NodeEvidence(
            type=str(e.get("type", "")),
            ref=prefer_git_ref(str(e.get("ref", "")), repo=repo_root),
            note=str(e.get("description", "") or e.get("note", "")),
        )
        for e in evidence_raw
        if isinstance(e, dict)
    )
    has_code = any(ev.type == "code" for ev in lives)
    maturity = str(cap.get("maturity", ""))
    audiences = _as_tuple(cap.get("audiences"))

    confidence = cap.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    if confidence is None:
        confidence = default_confidence(lives)

    ships_when = str(cap.get("ships_when", "") or "").strip()
    if not ships_when and not has_code:
        intent = cap.get("intent") or {}
        if isinstance(intent, dict):
            ships_when = str(intent.get("current", "")).strip()

    status = derive_status(has_code_evidence=has_code, maturity=maturity)
    return Node(
        key=str(cap.get("capability_id", "")),
        does=str(cap.get("summary", "")).strip() or _description_text(cap),
        status=status,
        wont=_wont(cap),
        lives=lives,
        ships_when=ships_when,
        confidence=confidence,
        triggers=_as_tuple(cap.get("triggers")),
        child_keys=_as_tuple(cap.get("dependencies")) + _as_tuple(cap.get("cross_references")),
        category=str(cap.get("category", "")),
        orientation=_orientation_from_audiences(audiences),
        route_state=_route_state(cap, has_code),
        attributes={
            "maturity": maturity,
            "description": _description_text(cap),
            "kind": "capability",
            # Display status = NODE status (built/thin/spec) — not app planned/… mapping.
            "status_key": status,
        },
    )


def nodes_from_capability_index(path: Optional[Path] = None) -> List[Node]:
    path = Path(path) if path else default_capability_index_path()
    if not path.exists():
        raise FileNotFoundError(f"Capability index not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in capability index {path}: {exc}") from exc
    caps = data.get("capabilities") or []
    # Prefer repo root that owns the YAML (…/docs/capability-index → parents[2]).
    repo = path.resolve().parents[2] if len(path.resolve().parents) >= 2 else Path.cwd()
    return [
        node_from_capability(c, repo=repo)
        for c in caps
        if isinstance(c, dict) and c.get("capability_id")
    ]
