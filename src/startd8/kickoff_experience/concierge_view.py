"""M-CM0 — the shared Concierge view-model (the parity oracle for both surfaces).

`build_concierge_view` is the one representation the web (M-CM3) and TUI (M-CM4) both render, so
parity is a property of a single payload (mirrors `state.to_dict()`). It composes existing read-only
machinery — never re-derives readiness (FR-CM-4):

* `survey`     — `concierge.build_survey` (brownfield triage), **memoized** (R1-S6: it walks
  `root.rglob("*")`, an O(repo) cost; a short TTL keeps repeated `GET /concierge` cheap).
* `readiness`  — `ReadinessView.from_assess(build_assess())`, reused.
* `instantiate_offer` — `{needed, package_state, postures}` where `package_state` ∈
  `missing | partial | complete` is **restart-safe** (R5-F1): computed from the instantiate plan's
  per-file stat, so a half-scaffolded package (some files present) reads `partial`, not a boolean
  keyed only to `inputs/`.
* `friction_form` — the field spec (with the length cap).
* `next_action` — a derived CTA both surfaces show (R2-F2).

**Not the MCP surface (R1-F7/S9):** this aggregator carries write-affordance metadata
(`instantiate_offer`, `friction_form`); MCP exposes only the bare `build_survey` shape.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, Tuple

from .concierge_apply import FRICTION_FIELD_MAX

SCHEMA_VERSION = 1

POSTURE_BANNER = (
    "🛈 Concierge — assist, not operate. I survey the project, assess readiness, scaffold a kickoff "
    "package, and log friction. I never run the build or record gates; writes happen only at your "
    "explicit confirmation."
)

PACKAGE_MISSING = "missing"
PACKAGE_PARTIAL = "partial"
PACKAGE_COMPLETE = "complete"

# Survey memo: {root: (monotonic_stamp, survey_dict)}. Cheap TTL guard for repeated GET /concierge.
_SURVEY_TTL_S = 5.0
_SURVEY_CACHE_MAX = 64  # bound entries so a multi-root process can't accumulate stale surveys
_survey_cache: Dict[str, Tuple[float, dict]] = {}


def cached_survey(project_root: str, *, ttl: float = _SURVEY_TTL_S, clock: Callable[[], float] = time.monotonic) -> dict:
    """`build_survey` behind a short TTL memo (R1-S6) — bounds the O(repo) rglob on repeated views."""
    from ..concierge import build_survey

    now = clock()
    hit = _survey_cache.get(project_root)
    if hit is not None and (now - hit[0]) < ttl:
        return hit[1]
    survey = build_survey(project_root)
    if project_root not in _survey_cache and len(_survey_cache) >= _SURVEY_CACHE_MAX:
        _survey_cache.pop(next(iter(_survey_cache)), None)  # evict oldest
    _survey_cache[project_root] = (now, survey)
    return survey


def _package_state(project_root: str) -> str:
    """Restart-safe package detection (R5-F1) from the instantiate plan's per-file stat."""
    from ..concierge.writes import build_instantiate_plan

    plan = build_instantiate_plan(project_root)  # stat-only, no write
    statuses = [w.get("status") for w in plan.get("writes", [])]
    if not statuses:
        return PACKAGE_MISSING
    if all(s == "exists" for s in statuses):
        return PACKAGE_COMPLETE
    if all(s == "new" for s in statuses):
        return PACKAGE_MISSING
    return PACKAGE_PARTIAL


def _next_action(package_state: str, readiness: Optional[dict]) -> Dict[str, str]:
    if package_state == PACKAGE_MISSING:
        return {"kind": "instantiate", "title": "Create the kickoff package",
                "detail": "This project has no kickoff inputs yet — scaffold them to begin."}
    if package_state == PACKAGE_PARTIAL:
        return {"kind": "instantiate", "title": "Complete the kickoff package",
                "detail": "Some kickoff files are missing — re-run instantiate to fill them in."}
    # FR-NU-3: the readiness-blocker CTA via the SHARED formatter (module-qualified so the parity
    # monkeypatch of `ranking.blocker_cta` is effective — CRP R1-S1). `readiness` is a dict here (or
    # None on the build_readiness exception path); `blocker_cta` normalizes both and returns None → the
    # "ready" branch (R1-S6). NOTE: the blocker `detail` is now the consequence|status (was a fixed
    # string) — a user-visible copy change (CRP R1-F3).
    from . import ranking

    cta = ranking.blocker_cta(readiness)
    if cta is not None:
        return cta.to_dict()
    return {"kind": "ready", "title": "Kickoff is build-ready", "detail": "No blocking gaps remain."}


def _friction_form() -> dict:
    return {
        "fields": [
            {"name": "friction", "label": "What friction did you hit?", "required": True,
             "max_length": FRICTION_FIELD_MAX, "widget": "textarea"},
            {"name": "what_happened", "label": "What happened?", "required": True,
             "max_length": FRICTION_FIELD_MAX, "widget": "textarea"},
            {"name": "implication", "label": "Implication for the SDK / role?", "required": True,
             "max_length": FRICTION_FIELD_MAX, "widget": "textarea"},
        ],
    }


def build_concierge_view(
    project_root: str,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    """The shared Concierge payload both surfaces render (read-only, ``$0``)."""
    from .readiness import build_readiness

    root = str(project_root)
    survey = cached_survey(root, clock=clock)
    try:
        readiness = build_readiness(root).to_dict()
    except Exception:
        readiness = None
    package_state = _package_state(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "concierge_view",
        "project_root": root,
        "posture_banner": POSTURE_BANNER,
        "survey": survey,
        "readiness": readiness,
        "instantiate_offer": {
            "needed": package_state != PACKAGE_COMPLETE,
            "package_state": package_state,
            "postures": ["prototype", "production"],
        },
        "friction_form": _friction_form(),
        "next_action": _next_action(package_state, readiness),
    }
