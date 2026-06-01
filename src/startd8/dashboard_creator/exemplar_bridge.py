"""Wire Grafana dashboards into the Proven Exemplar Pipeline (REQ-PEP-300..342).

The PEP core (ConfigFingerprint / ExemplarEntry / ExemplarRegistry / find_best_match)
is artifact-agnostic — it keys on a 4-tuple fingerprint string and a scalar score. This
module supplies the dashboard-specific *edges*: archetype classification + fingerprinting
(300-302), binary scoring (310-312), external bootstrap of the curated corpus (320-322),
and retrieval (340). Per the v0.4 reflection, the maturity ladder and internal mining are
deferred — reference exemplars seed at a single frozen tier and ranking falls back to
curation score.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.exemplars.models import ConfigFingerprint, ExemplarEntry, ExemplarScores
from startd8.exemplars.registry import ExemplarRegistry

# REQ-PEP-301 controlled archetype vocabulary (the corpus clusters).
ARCHETYPES = (
    "kpi_dashboard",
    "observability_dashboard",
    "table_dashboard",
    "geo_dashboard",
    "creative_dashboard",
)

_GEO = {"geomap", "orchestracities-map-panel"}
_CREATIVE = {"canvas", "candlestick", "xychart", "volkovlabs-echarts-panel"}
_KPI = {"stat", "gauge", "bargauge", "barGauge", "barchart", "piechart"}
_O11Y_HINTS = ("slo", "apm", "kubernetes", "k8s", "observability", "o11y", "latency", "rate(")

# REQ-PEP-342: deterministic archetype -> suggested recipe ids (the retrieval "hint").
ARCHETYPE_RECIPES: Dict[str, List[str]] = {
    "kpi_dashboard": ["stat.kpi", "gauge.threshold", "bargauge.lcd", "piechart.composition"],
    "observability_dashboard": ["timeseries.observability", "stat.kpi"],
    "table_dashboard": ["table.aggregation", "table.ranking"],
    "geo_dashboard": [],       # geomap recipes land with the constructor (gap backlog)
    "creative_dashboard": [],
}


def _unwrap(dashboard: Dict[str, Any]) -> Dict[str, Any]:
    """Accept both the raw dashboard model and the /api wrapper {dashboard: {...}}."""
    inner = dashboard.get("dashboard")
    return inner if isinstance(inner, dict) else dashboard


def _walk_panels(panels: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in panels or []:
        if not isinstance(p, dict):
            continue
        out.append(p)
        if p.get("type") == "row" and p.get("panels"):
            out.extend(_walk_panels(p["panels"]))
    return out


def classify_archetype(dashboard: Dict[str, Any]) -> str:
    """REQ-PEP-301: derive the archetype from the primary visualization + domain hints."""
    db = _unwrap(dashboard)
    text = " ".join(db.get("tags") or []).lower() + " " + (db.get("title") or "").lower()
    if any(h in text for h in _O11Y_HINTS):
        return "observability_dashboard"

    counts = Counter(
        p.get("type") for p in _walk_panels(db.get("panels"))
        if p.get("type") not in ("row", "text", None)
    )
    if not counts:
        return "kpi_dashboard"
    primary = counts.most_common(1)[0][0]
    if primary in _GEO:
        return "geo_dashboard"
    if primary in _CREATIVE:
        return "creative_dashboard"
    if primary == "table":
        return "table_dashboard"
    if primary == "timeseries":
        return "observability_dashboard"
    if primary in _KPI:
        return "kpi_dashboard"
    return "kpi_dashboard"


def dashboard_fingerprint(dashboard: Dict[str, Any]) -> ConfigFingerprint:
    """REQ-PEP-300/302: grafana:dashboard:none:<archetype> — never collides with code
    fingerprints (which never use language='grafana')."""
    return ConfigFingerprint(
        language="grafana",
        file_type="dashboard",
        transport="none",
        archetype=classify_archetype(dashboard),
    )


def score_dashboard(dashboard: Dict[str, Any], *, is_reference: bool = False) -> ExemplarScores:
    """REQ-PEP-310/311: BINARY validity score (1.0 / 0.0). External references are 1.0 by
    definition (production-proven); generated dashboards score on structural validity."""
    if is_reference:
        return ExemplarScores(requirement_score=1.0, disk_quality_score=1.0,
                              assembly_delta=0.0, semantic_error_count=0)
    db = _unwrap(dashboard)
    valid = bool(
        db.get("title") and db.get("uid")
        and isinstance(db.get("panels"), list) and db["panels"]
        and db.get("schemaVersion")
    )
    return ExemplarScores(
        requirement_score=1.0 if valid else 0.0,
        disk_quality_score=1.0 if valid else 0.0,
        assembly_delta=0.0,
        semantic_error_count=0 if valid else 1,
    )


# REQ-PEP-321: single frozen reference tier (maturity ladder deferred — R2-F10).
REFERENCE_TIER = 2


def build_reference_entry(path: Path, dashboard: Dict[str, Any]) -> ExemplarEntry:
    """Construct an ExemplarEntry for an externally-seeded reference dashboard."""
    db = _unwrap(dashboard)
    fp = dashboard_fingerprint(dashboard)
    uid = db.get("uid") or path.stem
    panel_types = Counter(p.get("type") for p in _walk_panels(db.get("panels")))
    summary = f"{db.get('title', uid)} | panels: {dict(panel_types)}"
    return ExemplarEntry(
        id=ExemplarEntry.make_id(fp, "grafana-play", uid),
        fingerprint=fp,
        maturity=REFERENCE_TIER,
        source_run_id="grafana-play",
        source_feature_id=uid,
        spec_artifact_path="",
        code_artifact_path=str(path),
        draft_artifact_path="",
        seed_task_digest="",
        scores=score_dashboard(dashboard, is_reference=True),
        agent_specs={"provenance": "external_reference"},
        code_summary=summary[:2000],
        timestamp="",
    )


def seed_reference_exemplars(exemplars_dir: str | Path, registry: ExemplarRegistry) -> int:
    """REQ-PEP-320/322: ingest the curated corpus dashboards as reference exemplars.
    Idempotent (keyed by make_id over fingerprint + uid); returns the number added."""
    exemplars_dir = Path(exemplars_dir)
    added = 0
    for path in sorted(exemplars_dir.glob("*.json")):
        try:
            dashboard = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        registry.add(build_reference_entry(path, dashboard))
        added += 1
    return added


def find_dashboard_exemplar(
    dashboard: Dict[str, Any], registry: ExemplarRegistry
) -> Optional[ExemplarEntry]:
    """REQ-PEP-340: best-ranked reference exemplar for the requested dashboard's
    fingerprint (exact -> partial -> none cascade, reusing the generic registry)."""
    return registry.find_best_match(dashboard_fingerprint(dashboard))


def suggest_recipes(dashboard: Dict[str, Any]) -> List[str]:
    """REQ-PEP-342: the deterministic recipe hint for a dashboard's archetype."""
    return list(ARCHETYPE_RECIPES.get(classify_archetype(dashboard), []))


def apply_recipe_hint(spec, registry: Optional[ExemplarRegistry] = None):
    """REQ-PEP-341: deterministically apply the exemplar recipe hint to a DashboardSpec.

    The hint maps **by panel type**, applies **only to panels the spec left
    un-recipe'd**, is a **no-op for types the exemplar archetype doesn't cover**, and
    leaves explicit spec recipes untouched (R2-S6/S7 — it selects a recipe id, not a
    new precedence layer). If a ``registry`` is given, the hint is gated on a matching
    reference exemplar actually existing (grounding the suggestion in a proven dashboard);
    without one it falls back to the archetype's curated recipes. Returns the same spec
    object unchanged when nothing applies.
    """
    from startd8.dashboard_creator.recipes import RECIPE_REGISTRY

    # Classify from a synthetic dashboard (panel types + title/tags) — same as a compiled one.
    dash = {
        "title": spec.title,
        "tags": list(spec.tags),
        "panels": [{"type": p.type.value} for p in spec.panels],
    }
    if registry is not None and find_dashboard_exemplar(dash, registry) is None:
        return spec

    recipe_ids = suggest_recipes(dash)
    if not recipe_ids:
        return spec

    # First matching recipe per panel type (deterministic — recipe_ids order is fixed).
    type_to_recipe: Dict[Any, str] = {}
    for rid in recipe_ids:
        recipe = RECIPE_REGISTRY.get(rid)
        if recipe is None:
            continue
        for pt in recipe.applies_to:
            type_to_recipe.setdefault(pt, rid)

    new_panels = []
    changed = False
    for panel in spec.panels:
        if panel.recipe is None and panel.type in type_to_recipe:
            new_panels.append(panel.model_copy(update={"recipe": type_to_recipe[panel.type]}))
            changed = True
        else:
            new_panels.append(panel)

    return spec.model_copy(update={"panels": new_panels}) if changed else spec
