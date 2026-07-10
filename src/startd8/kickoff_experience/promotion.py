"""Promotion dividend (roadmap Tier E) — a ready-state kickoff becomes a reusable exemplar so new
projects start from a proven setup instead of a blank slate.

The compounding payoff at the end of the oracle-as-API roadmap. Three pieces, all built on data the
single oracle already folds ($0, deterministic):

- **Eligibility** — :func:`promotion_eligibility`: is a project *clean enough* to promote? (ready-state:
  readiness at target, zero blocked fields, zero pending proposals, has inputs). Tier-C's history is
  what makes "clean" answerable.
- **Promote** — :func:`build_exemplar` + :class:`ExemplarRegistry`: capture the project's **settled
  conventions** (the value-path→value pairs that reached `ok`) plus provenance into a portable
  ``startd8.kickoff.exemplar.v1`` record, saved to a cross-project registry.
- **Apply (the dividend)** — :func:`apply_plan` / :func:`emit_to_inbox`: seed a *new* project from an
  exemplar. Crucially this reuses the **vetted VIPP producer path** (:func:`build_proposal` →
  :func:`serialize_buffer`): it emits ``capture`` *proposals* into the target's inbox, so the target
  human reviews with ``kickoff proposals`` and applies through the existing confirm gate. Tier E adds
  **no new write path** and preserves every invariant (CLI-sole-writer, per-target validation,
  provenance, human-confirm). A convention the target can't accept is skipped honestly, never forced.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..logging_config import get_logger

logger = get_logger(__name__)

EXEMPLAR_SCHEMA = "startd8.kickoff.exemplar.v1"
DEFAULT_MIN_READINESS = 100


# --- eligibility --------------------------------------------------------------------------------

@dataclass(frozen=True)
class PromotionEligibility:
    """Whether a project is clean enough to promote, and why not when it isn't."""

    eligible: bool
    readiness_percent: Optional[int]
    reasons: Tuple[str, ...]  # blocking reasons (empty ⇒ eligible)

    def to_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "readiness_percent": self.readiness_percent,
            "reasons": list(self.reasons),
        }


def promotion_eligibility(
    status: Dict[str, Any], *, min_readiness: int = DEFAULT_MIN_READINESS
) -> PromotionEligibility:
    """Evaluate promotability from the oracle ``status`` payload. All reads, never raises."""
    counts = status.get("attention_counts") or {}
    readiness = status.get("readiness_percent")
    field_count = int(status.get("field_count", 0) or 0)
    pending = len(status.get("proposals") or [])
    blocked = int(counts.get("blocked", 0) or 0)

    reasons: List[str] = []
    if field_count == 0:
        reasons.append("no kickoff inputs captured")
    if readiness is None or readiness < min_readiness:
        reasons.append(f"readiness {readiness}% < target {min_readiness}%")
    if blocked > 0:
        reasons.append(f"{blocked} blocked field(s)")
    if pending > 0:
        reasons.append(f"{pending} proposal(s) still pending")
    return PromotionEligibility(not reasons, readiness, tuple(reasons))


# --- exemplar assembly --------------------------------------------------------------------------

def settled_conventions(state: Any) -> List[Dict[str, str]]:
    """The value-path→value pairs that reached ``ok`` — the reusable, proven kickoff decisions.

    Sorted by value_path for byte-stability."""
    out: List[Dict[str, str]] = []
    for f in getattr(state, "fields", ()) or ():
        if str(getattr(f, "attention", "")) == "ok" and getattr(f, "value", None) is not None:
            out.append({"value_path": str(f.value_path), "value": str(f.value)})
    out.sort(key=lambda d: d["value_path"])
    return out


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return s or "project"


def exemplar_id(project_name: str, conventions: List[Dict[str, str]]) -> str:
    """Content-derived id: same project + same settled conventions ⇒ same id (idempotent promote)."""
    payload = json.dumps(conventions, sort_keys=True)
    h = hashlib.sha1(f"{project_name}|{payload}".encode("utf-8")).hexdigest()[:12]
    return f"{_slug(project_name)}-{h}"


def assemble_exemplar(
    status: Dict[str, Any],
    conventions: List[Dict[str, str]],
    decisions: Dict[str, Any],
    *,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Pure exemplar record assembly from already-derived pieces (testable without disk)."""
    root = str(status.get("project_root", ""))
    name = Path(root).name or "project"
    eid = exemplar_id(name, conventions)
    ts = generated_at or datetime.now(timezone.utc).isoformat()
    n = len(conventions)
    readiness = status.get("readiness_percent")
    return {
        "schema": EXEMPLAR_SCHEMA,
        "id": eid,
        "source_project": name,
        "source_project_root": root,
        "generated_at": ts,
        "readiness_percent": readiness,
        "field_count": int(status.get("field_count", 0) or 0),
        "conventions": conventions,
        "convention_count": n,
        "decisions": {
            "adjudicated": decisions.get("adjudicated", 0),
            "counts": decisions.get("counts", {}),
        },
        "summary": f"{name} — {n} convention(s), readiness {readiness}%",
    }


def build_exemplar(project_root: str | Path) -> Dict[str, Any]:
    """Assemble a portable exemplar record from a project's oracle read-model. Read-only, $0."""
    from .agentic_view import build_agentic_view
    from .retrospective import decision_log

    view = build_agentic_view(project_root)
    status = view.to_dict()
    return assemble_exemplar(status, settled_conventions(view.state), decision_log(status))


# --- registry -----------------------------------------------------------------------------------

def exemplars_dir() -> Path:
    """The cross-project exemplar registry dir (``$STARTD8_KICKOFF_EXEMPLARS_DIR`` or ~/.startd8/…)."""
    override = os.environ.get("STARTD8_KICKOFF_EXEMPLARS_DIR")
    return Path(override) if override else (Path.home() / ".startd8" / "kickoff-exemplars")


@dataclass
class ExemplarRegistry:
    """A tiny file-backed registry of promoted kickoff exemplars (one ``<id>.json`` per exemplar)."""

    root: Optional[Path] = None

    def __post_init__(self) -> None:
        self.root = Path(self.root) if self.root is not None else exemplars_dir()

    def _path(self, exemplar_id: str) -> Path:
        return self.root / f"{exemplar_id}.json"

    def save(self, exemplar: Dict[str, Any]) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        p = self._path(exemplar["id"])
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(exemplar, indent=2), encoding="utf-8")
        tmp.replace(p)  # atomic
        return p

    def get(self, exemplar_id: str) -> Optional[Dict[str, Any]]:
        p = self._path(exemplar_id)
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - tolerate a corrupt record
            return None

    def list(self) -> List[Dict[str, Any]]:
        if not self.root.is_dir():
            return []
        out: List[Dict[str, Any]] = []
        for f in sorted(self.root.glob("*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:  # pragma: no cover
                logger.debug("skipping malformed exemplar %s", f.name)
        return out


def promote(
    project_root: str | Path,
    *,
    min_readiness: int = DEFAULT_MIN_READINESS,
    force: bool = False,
    registry: Optional[ExemplarRegistry] = None,
) -> Dict[str, Any]:
    """Gate on eligibility, then capture + save an exemplar. Returns a result dict (never raises)."""
    from .agentic_view import build_agentic_view
    from .retrospective import decision_log

    view = build_agentic_view(project_root)
    status = view.to_dict()
    elig = promotion_eligibility(status, min_readiness=min_readiness)
    if not elig.eligible and not force:
        return {"promoted": False, "eligibility": elig.to_dict()}

    exemplar = assemble_exemplar(status, settled_conventions(view.state), decision_log(status))
    reg = registry or ExemplarRegistry()
    path = reg.save(exemplar)
    return {
        "promoted": True,
        "eligibility": elig.to_dict(),
        "forced": bool(not elig.eligible and force),
        "exemplar": exemplar,
        "path": str(path),
    }


# --- apply (the dividend) — via the vetted VIPP producer path -----------------------------------

def apply_plan(exemplar: Dict[str, Any], target_root: str | Path) -> Dict[str, Any]:
    """Preview which of the exemplar's conventions the TARGET can accept (per-target validation).

    For each convention we run the same :func:`build_proposal` the concierge/producer seams use — so a
    value-path the target's manifest doesn't allow is reported as skipped, never forced. No write."""
    from .proposals import build_proposal

    applicable: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for c in exemplar.get("conventions") or []:
        vp, val = c.get("value_path"), c.get("value")
        try:
            action = build_proposal(
                {"kind": "capture", "value_path": vp, "value": val}, target_root
            )
            applicable.append({"value_path": vp, "value": val, "base_sha": action.base_sha})
        except Exception as exc:  # CaptureError / ConciergeInputError → not applicable to this target
            skipped.append({"value_path": vp, "reason": _err_reason(exc)})
    return {
        "exemplar_id": exemplar.get("id"),
        "target_root": str(target_root),
        "applicable": applicable,
        "skipped": skipped,
        "applicable_count": len(applicable),
        "skipped_count": len(skipped),
    }


def emit_to_inbox(
    exemplar: Dict[str, Any], target_root: str | Path, *, force: bool = False
) -> Dict[str, Any]:
    """Emit the applicable conventions as ``capture`` proposals into the target's VIPP inbox.

    Reuses :func:`build_proposal` + :func:`serialize_buffer` (the vetted producer path): the target
    then reviews with ``kickoff proposals`` and applies through the existing confirm gate. The inbox
    is the only thing written, and only proposals (advisory until confirmed)."""
    from .proposals import ProposalBuffer, build_proposal
    from .vipp_seam import serialize_buffer

    buffer = ProposalBuffer()
    applied: List[str] = []
    skipped: List[Dict[str, Any]] = []
    for c in exemplar.get("conventions") or []:
        vp, val = c.get("value_path"), c.get("value")
        try:
            buffer.add(build_proposal({"kind": "capture", "value_path": vp, "value": val}, target_root))
            applied.append(str(vp))
        except Exception as exc:
            skipped.append({"value_path": vp, "reason": _err_reason(exc)})
    if not applied:
        return {"emitted": False, "seeded": [], "skipped": skipped, "reason": "no applicable conventions"}
    result = serialize_buffer(buffer, target_root, force=force)
    return {
        "emitted": bool(getattr(result, "written", None)),
        "seeded": applied,
        "skipped": skipped,
        "write_skipped": list(getattr(result, "skipped", []) or []),
    }


def _err_reason(exc: Exception) -> str:
    return f"{type(exc).__name__}: {getattr(exc, 'message', None) or exc}"
