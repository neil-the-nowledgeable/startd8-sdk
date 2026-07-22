"""
Build DashboardSpec dicts for onboarding portal dashboards (REQ-OBP-100).

Produces a declarative spec consumable by DashboardCreatorWorkflow — the same
pipeline used for all /dbrd-cr8r dashboards.  Deterministic ($0.00, no LLM).

See docs/design/onboarding-portal/ONBOARDING_PORTAL_GRAFANA_PLAN.md
"""

import logging
from typing import Any, Dict, List, Optional

try:
    from startd8.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persona → section gating
# ---------------------------------------------------------------------------

# Personas aligned with ContextCore personalization.py AudienceType +
# harbor tour profiles (team-lead, platform-engineer, ai-developer).
# See docs/design/onboarding-portal/ONBOARDING_PORTAL_GRAFANA_PLAN.md §4a.

_PERSONA_SECTIONS: Dict[str, set] = {
    # Platform Engineer: "Infrastructure That Understands Business Value"
    # Cares about: alert precision, SLO accuracy, context completeness
    "operator": {
        "overview", "services", "objectives", "alerts", "dashboards",
        "communication", "security", "quality", "provenance",
    },
    # AI Developer / Engineer: "Agents That Remember"
    # Cares about: service topology, dashboards for debugging, provenance
    "engineer": {
        "overview", "services", "communication", "dashboards", "provenance",
    },
    # Team Lead / Manager: "Status Updates That Write Themselves"
    # Cares about: project health, objectives, quality trends, time recovery
    "manager": {
        "overview", "objectives", "quality", "health", "provenance",
    },
    # Executive: Business impact summaries only
    # Cares about: project criticality, objectives, quality score
    "executive": {
        "overview", "objectives", "quality",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_portal_spec(
    business: Any,
    services: List[Any],
    report: Any,
    metadata: Dict[str, Any],
    *,
    persona: str = "operator",
    profile: Any = None,
) -> Dict[str, Any]:
    """Build a DashboardSpec dict for the onboarding portal.

    ``profile`` (optional ``PersonaProfile``): when given, its ``sections``/``value`` drive the portal
    (declarative path, A1); when ``None``, falls back to the hardcoded ``_PERSONA_SECTIONS``/
    ``_PERSONA_VALUE`` for ``persona`` (no regression for existing callers).

    Args:
        business: BusinessContext from artifact_generator.
        services: List[ServiceHints] — already filtered (no phantoms).
        report: GenerationReport with artifacts from alerts/dashboards/SLOs.
        metadata: Raw onboarding-metadata.json dict.
        persona: Portal variant — "operator", "engineer", or "manager".

    Returns:
        Dict consumable by DashboardCreatorWorkflow (DashboardSpec shape).
    """
    sections = profile.sections if profile is not None else _PERSONA_SECTIONS.get(
        persona, _PERSONA_SECTIONS["operator"]
    )
    project_id = business.project_id or "unknown"
    uid_suffix = f"-{persona}" if persona != "operator" else ""
    # UID follows cc-{pack}-{slug} convention for DashboardCreatorWorkflow compatibility
    uid_project = project_id.lower().replace("_", "-")

    panels: List[Dict[str, Any]] = []

    if "overview" in sections:
        panels.extend(_build_project_overview_panels(business, report))
        panels.extend(_build_persona_value_panel(persona, profile.value if profile is not None else None))

    # --- Benchmark Analyst analytical sections (A3); static markdown tables from metadata["aggregate"] ---
    if "scoring-methodology" in sections:
        panels.extend(_build_scoring_methodology_panels(metadata))
    if "leaderboard" in sections:
        panels.extend(_build_leaderboard_panels(metadata))
    if "quality-distribution" in sections:
        panels.extend(_build_quality_distribution_panels(metadata))
    if "exclusions" in sections:
        panels.extend(_build_exclusions_panels(metadata))
    if "service-discrimination" in sections:
        panels.extend(_build_service_discrimination_panels(metadata))
    if "deeper-analysis" in sections:
        panels.extend(_build_deeper_analysis_panels(metadata))

    if "services" in sections:
        panels.extend(_build_service_inventory_panels(services, report))
        # QW-1: coverage gaps right after the inventory — "here are your services, and the
        # ones observability couldn't fully cover." Self-gating: no gaps ⇒ no panel.
        panels.extend(_build_coverage_gap_panels(report))

    if "objectives" in sections:
        panels.extend(_build_objectives_panels(metadata))

    if "alerts" in sections:
        panels.extend(_build_alert_inventory_panels(report))

    if "dashboards" in sections:
        panels.extend(_build_dashboard_links_panels(report))

    if "communication" in sections:
        panels.extend(_build_communication_graph_panels(metadata))

    if "quality" in sections:
        panels.extend(_build_quality_panels(report, metadata, business))

    if "security" in sections:
        panels.extend(_build_security_panels(metadata))

    if "health" in sections:
        panels.extend(_build_artifact_health_panels(report))

    if "provenance" in sections:
        panels.extend(_build_provenance_panels(report, metadata))

    if not panels:
        # Safety: always produce at least one panel
        panels.append({
            "type": "text",
            "title": "Onboarding Portal",
            "options": {"content": "_No sections available for this persona._"},
        })

    # Dashboard links to each service's generated dashboard
    links = _build_dashboard_links_list(services)

    return {
        "title": f"{project_id} — Onboarding Portal"
                 + (f" ({persona.title()})" if persona != "operator" else ""),
        "uid": f"cc-portal-{uid_project}{uid_suffix}",
        "description": (
            f"Auto-generated onboarding portal for {project_id}. "
            f"Persona: {persona}. "
            f"Generated at {report.generated_at}."
        ),
        "tags": ["portal", "onboarding", project_id, persona],
        "panels": panels,
        "variables": [
            # Prometheus datasource variable — required by stat/gauge panels
            # and satisfies DashboardCreatorWorkflow's templating validation
            {"type": "prometheusDatasource", "name": "datasource", "label": "Data Source"},
        ],
        "links": links,
    }


def build_all_portal_specs(
    business: Any,
    services: List[Any],
    report: Any,
    metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build portal specs for all resolved personas (hardcoded defaults + manifest ``personas[]``, A1)."""
    from .persona_config import load_personas

    profiles = load_personas(metadata.get("personas"))
    return [
        build_portal_spec(business, services, report, metadata, persona=pid, profile=prof)
        for pid, prof in profiles.items()
    ]


# ---------------------------------------------------------------------------
# Section builders — each returns List[panel_dict] or []
# ---------------------------------------------------------------------------


# Pain points and value propositions per persona.
# Source: wayfinder-demo-retail/demo/persona-views/*.md
_PERSONA_VALUE: Dict[str, Dict[str, str]] = {
    "operator": {
        "title": "Platform Engineer / SRE",
        "pain": "$247K/yr",
        "headline": "Infrastructure That Understands Business Value",
        "content": (
            "**The problem:** Incidents arrive without context — no owner, no "
            "criticality, no runbook link. 15-minute MTTA delay at $10K/hr "
            "downtime cost.\n\n"
            "**What this portal provides:**\n"
            "- Alert inventory with severity and thresholds derived from requirements\n"
            "- Service communication graph for dependency analysis\n"
            "- Dashboard links for every service — one click to operational metrics\n"
            "- Quality scores showing artifact generation health"
        ),
    },
    "engineer": {
        "title": "Developer / AI Engineer",
        "pain": "$475K/yr",
        "headline": "Agents That Remember",
        "content": (
            "**The problem:** Redundant status updates across 3 tools. AI agents "
            "re-discover context every session instead of persisting learnings.\n\n"
            "**What this portal provides:**\n"
            "- Service inventory with protocol, language, and database detection\n"
            "- Communication graph for understanding service topology\n"
            "- Dashboard links for debugging and tracing\n"
            "- Run provenance for generation audit trail"
        ),
    },
    "manager": {
        "title": "Team Lead / Project Manager",
        "pain": "$117K–$258K/yr",
        "headline": "Status Updates That Write Themselves",
        "content": (
            "**The problem:** Weekly status compilation from manual chasing. "
            "Portfolio assembly from 5 separate tools.\n\n"
            "**What this portal provides:**\n"
            "- Project objectives with measurable targets\n"
            "- Artifact quality gauge — are we generating healthy observability?\n"
            "- Artifact health stats (generated / errored / skipped)\n"
            "- Run provenance for accountability"
        ),
    },
    "executive": {
        "title": "Executive",
        "pain": "$1.3M/yr aggregate",
        "headline": "Business Impact at a Glance",
        "content": (
            "**The problem:** No single view of project health, SLO targets, "
            "or observability quality across the portfolio.\n\n"
            "**What this portal provides:**\n"
            "- Project overview with criticality and ownership\n"
            "- Objectives with availability and latency targets\n"
            "- Composite quality score across all generated artifacts"
        ),
    },
}


def _build_persona_value_panel(persona: str, info: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Build persona-specific value proposition panel (``info`` overrides the hardcoded default)."""
    info = info or _PERSONA_VALUE.get(persona)
    if not info:
        return []

    content = (
        f"### {info['headline']}\n"
        f"*{info['title']}* — estimated pain: **{info['pain']}** (enterprise)\n\n"
        f"{info['content']}"
    )
    return [_text_panel("Why This Portal", content, "Project Overview")]


def _build_project_overview_panels(
    business: Any, report: Any,
) -> List[Dict[str, Any]]:
    """REQ-OBP-100: Project Overview section."""
    criticality = getattr(business, "criticality", "unknown")
    owner = getattr(business, "owner", None) or "—"
    project_name = getattr(business, "project_name", None) or ""
    project_id = business.project_id or "unknown"

    lines = [
        f"# {project_name or project_id}",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Project ID** | `{project_id}` |",
        f"| **Criticality** | {_badge(criticality)} |",
        f"| **Owner** | {owner} |",
        f"| **Generated** | {report.generated_at} |",
    ]
    if project_name and project_name != project_id:
        lines.insert(4, f"| **Name** | {project_name} |")

    return [_text_panel("Project Overview", "\n".join(lines), "Project Overview")]


def _build_service_inventory_panels(
    services: List[Any], report: Any,
) -> List[Dict[str, Any]]:
    """REQ-OBP-100: Service Inventory section with table + stat panels."""
    if not services:
        return [_text_panel("Service Inventory", "_No services detected._", "Service Inventory")]

    # Markdown table of services
    header = "| Service | Protocol | Language | Metrics | Databases |"
    sep = "|---------|----------|----------|---------|-----------|"
    rows = []
    for svc in services:
        lang = getattr(svc, "language", None) or "—"
        dbs = ", ".join(getattr(svc, "detected_databases", [])) or "—"
        metric_count = len(getattr(svc, "convention_metrics", []))
        rows.append(
            f"| `{svc.service_id}` | {_badge(svc.transport)} "
            f"| {lang} | {metric_count} | {dbs} |"
        )

    table_content = "\n".join([header, sep] + rows)
    generated = sum(1 for a in report.artifacts if a.status == "generated")

    return [
        _text_panel("Service Inventory", table_content, "Service Inventory"),
        _stat_panel("Services", f"vector({len(services)})", "Service Inventory"),
        _stat_panel("Artifacts Generated", f"vector({generated})", "Service Inventory"),
    ]


def _build_objectives_panels(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """REQ-OBP-105c: Objectives from onboarding metadata (plan-level intent)."""
    objectives = metadata.get("objectives")
    if not objectives:
        return []

    header = "| Objective | Metric | Target | Unit |"
    sep = "|-----------|--------|--------|------|"
    rows = []
    for obj in objectives:
        desc = obj.get("description", "—")
        metric = obj.get("metricKey", "—")
        target = obj.get("target", "—")
        unit = obj.get("unit", "")
        rows.append(f"| {desc} | `{metric}` | {target} | {unit} |")

    return [_text_panel("Project Objectives", "\n".join([header, sep] + rows), "Objectives")]


def _build_coverage_gap_panels(report: Any) -> List[Dict[str, Any]]:
    """QW-1 / #226 FR-9 (+#230/#231/#233): surface the coverage GAPS a human would
    otherwise have to grep out of ``observability-manifest.yaml`` — services observed by
    nothing, recognized-but-ungrounded workload kinds (with a kind-specific next step),
    and FRs whose metric is absent. Returns ``[]`` when there are no gaps, so a fully
    covered project renders byte-identically to before this panel existed.
    """
    cov = getattr(report, "fr_coverage", None) or {}
    ungrounded = cov.get("ungrounded_kinds") or []
    empty = cov.get("empty_services") or []
    unfulfilled = cov.get("unfulfilled") or []
    if not (ungrounded or empty or unfulfilled):
        return []

    header = "| Service / FR | Gap | Next step |"
    sep = "|--------------|-----|-----------|"
    rows: List[str] = []
    ungrounded_svcs = {u.get("service") for u in ungrounded}

    for u in ungrounded:
        # LH-1: fold the ∅ symptom into the ungrounded (cause) row — one story, not two.
        gap = f"ungrounded kind `{u.get('kind')}`"
        if u.get("observed_by_nothing"):
            gap += " · observed by nothing"
        sugg = "/".join(u.get("suggested_signals") or []) or "run_success/freshness"
        rows.append(f"| `{u.get('service')}` | {gap} | declare a `{sugg}` FR + target |")

    for svc in empty:
        if svc in ungrounded_svcs:
            continue  # already told as the ungrounded story (LH-1) — don't double-list
        rows.append(
            f"| `{svc}` | observed by nothing | declare a functional[] FR, "
            "or add a request transport |"
        )

    for uf in unfulfilled:
        fid = uf.get("id", "?")
        sk = uf.get("signal_kind", "?")
        rows.append(f"| FR `{fid}` | declared `{sk}`, metric absent | emit/label the series |")

    return [_text_panel("Coverage Gaps", "\n".join([header, sep] + rows), "Coverage")]


def _build_alert_inventory_panels(report: Any) -> List[Dict[str, Any]]:
    """REQ-OBP-100: Alert Inventory from generated alert artifacts."""
    alert_artifacts = [
        a for a in report.artifacts
        if a.artifact_type == "alert_rule" and a.status == "generated"
    ]
    if not alert_artifacts:
        return []

    header = "| Service | Alert | Severity | Duration |"
    sep = "|---------|-------|----------|----------|"
    rows = []

    for artifact in alert_artifacts:
        rules = _extract_alert_rules(artifact.content)
        for rule in rules:
            rows.append(
                f"| `{artifact.service_id}` "
                f"| {rule['alert']} "
                f"| {_badge(rule.get('severity', 'unknown'))} "
                f"| {rule.get('for', '—')} |"
            )

    if not rows:
        return []

    return [_text_panel("Alert Inventory", "\n".join([header, sep] + rows), "Alert Inventory")]


def _build_dashboard_links_panels(report: Any) -> List[Dict[str, Any]]:
    """REQ-OBP-100: Dashboard Links panel with links to generated dashboard specs."""
    dashboard_artifacts = [
        a for a in report.artifacts
        if a.artifact_type == "dashboard_spec" and a.status == "generated"
    ]
    if not dashboard_artifacts:
        return []

    header = "| Service | Dashboard |"
    sep = "|---------|-----------|"
    rows = []
    for artifact in dashboard_artifacts:
        uid = f"cc-obs-{artifact.service_id}"
        rows.append(
            f"| `{artifact.service_id}` "
            f"| [Open Dashboard](/d/{uid}/) |"
        )

    return [_text_panel("Dashboard Links", "\n".join([header, sep] + rows), "Dashboard Links")]


def _build_communication_graph_panels(
    metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """REQ-OBP-102e: Service communication graph as HTML table."""
    graph = metadata.get("service_communication_graph", {})
    services_graph = graph.get("services", {})

    # Check if any edges exist
    has_edges = any(
        svc_data.get("calls_to") or svc_data.get("called_by")
        for svc_data in services_graph.values()
    )

    if not services_graph or not has_edges:
        return [_text_panel(
            "Service Communication",
            "_No inter-service dependencies detected._",
            "Communication Graph",
        )]

    header = "| Service | Calls To | Called By |"
    sep = "|---------|----------|-----------|"
    rows = []
    for svc_id, svc_data in sorted(services_graph.items()):
        calls_to = ", ".join(f"`{t}`" for t in svc_data.get("calls_to", [])) or "—"
        called_by = ", ".join(f"`{t}`" for t in svc_data.get("called_by", [])) or "—"
        rows.append(f"| `{svc_id}` | {calls_to} | {called_by} |")

    return [_text_panel("Service Communication", "\n".join([header, sep] + rows), "Communication Graph")]


def _build_quality_panels(
    report: Any, metadata: Dict[str, Any], business: Any = None,
) -> List[Dict[str, Any]]:
    """REQ-OBP-104: Quality metrics from observability-manifest quality_summary.

    ``business.quality_thresholds`` (declarative) overrides the gauge bands; defaults to 0.6/0.8.
    """
    _qt = (getattr(business, "quality_thresholds", None) or {"warning": 0.6, "healthy": 0.8})
    # Try quality from report artifacts first. Only artifacts with an actual
    # `score` count — functional-SLO artifacts carry a scoreless coverage dict
    # ({emitted_fr_ids, unfulfilled}, #226 FR-5), which would otherwise KeyError
    # on the a.quality["score"] subscripts below (#254).
    scored = [a for a in report.artifacts if a.quality and "score" in a.quality]
    if not scored:
        return [_text_panel(
            "Quality Metrics",
            "_Quality metrics unavailable (run postmortem to generate)._",
            "Quality",
        )]

    # Compute per-type averages
    by_type: Dict[str, List[float]] = {}
    for a in scored:
        by_type.setdefault(a.artifact_type, []).append(a.quality["score"])

    all_scores = [a.quality["score"] for a in scored]
    composite = sum(all_scores) / len(all_scores) if all_scores else 0.0
    total_issues = sum(len(a.quality.get("issues", [])) for a in scored)
    total_repairs = sum(len(a.quality.get("repairs_applied", [])) for a in scored)

    # Quality breakdown table
    header = "| Artifact Type | Avg Score | Count |"
    sep = "|---------------|-----------|-------|"
    rows = []
    for atype, scores in sorted(by_type.items()):
        avg = sum(scores) / len(scores)
        rows.append(f"| {atype} | {avg:.0%} | {len(scores)} |")
    rows.append(f"| **Composite** | **{composite:.0%}** | **{len(scored)}** |")

    if total_issues or total_repairs:
        rows.append("")
        rows.append(f"Issues found: **{total_issues}** · Repairs applied: **{total_repairs}**")

    return [
        {
            "type": "gauge",
            "title": "Artifact Quality",
            "expr": f"vector({composite:.4f})",
            "unit": "percentunit",
            "thresholds": [
                {"value": None, "color": "red"},
                {"value": _qt["warning"], "color": "yellow"},
                {"value": _qt["healthy"], "color": "green"},
            ],
            "group": "Quality",
        },
        _text_panel("Quality Breakdown", "\n".join([header, sep] + rows), "Quality"),
    ]


def _build_security_panels(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """REQ-OBP-100: Security posture from kaizen-metrics.json security section."""
    # Security data may come from kaizen_metrics in metadata or a dedicated field
    security = metadata.get("security", {})
    if not security:
        kaizen = metadata.get("kaizen_metrics", {})
        security = kaizen.get("security", {})

    if not security:
        return []

    lines = [
        "| Check | Result |",
        "|-------|--------|",
    ]

    score = security.get("aggregate_score")
    if score is not None:
        lines.append(f"| **Aggregate Score** | {score:.0%} |")

    for key in ("injection_blocked", "credential_blocked", "lifecycle_blocked",
                "pattern_violations"):
        val = security.get(key)
        if val is not None:
            label = key.replace("_", " ").title()
            lines.append(f"| {label} | {val} |")

    # Only return if we have data beyond the header
    if len(lines) <= 2:
        return []

    return [_text_panel("Security Posture", "\n".join(lines), "Security")]


def _build_artifact_health_panels(report: Any) -> List[Dict[str, Any]]:
    """Artifact health summary — stat panels for manager persona."""
    generated = sum(1 for a in report.artifacts if a.status == "generated")
    errored = sum(1 for a in report.artifacts if a.status == "error")
    skipped = sum(1 for a in report.artifacts if a.status == "skipped")

    panels: List[Dict[str, Any]] = [
        _stat_panel("Generated", f"vector({generated})", "Artifact Health",
                    thresholds=[{"value": None, "color": "green"}]),
    ]
    if errored:
        panels.append(_stat_panel(
            "Errored", f"vector({errored})", "Artifact Health",
            thresholds=[{"value": None, "color": "red"}],
        ))
    if skipped:
        panels.append(_stat_panel(
            "Skipped", f"vector({skipped})", "Artifact Health",
            thresholds=[{"value": None, "color": "yellow"}],
        ))
    return panels


def _build_provenance_panels(
    report: Any, metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """REQ-OBP-100: Run provenance section."""
    generated = sum(1 for a in report.artifacts if a.status == "generated")
    errored = sum(1 for a in report.artifacts if a.status == "error")

    lines = [
        "| Field | Value |",
        "|-------|-------|",
        f"| **Generated At** | {report.generated_at} |",
        f"| **Project ID** | `{report.project_id or '—'}` |",
        f"| **Services Processed** | {report.services_processed} |",
        f"| **Artifacts Generated** | {generated} |",
    ]
    if errored:
        lines.append(f"| **Artifacts Errored** | {errored} |")

    # Include pipeline version if available in metadata
    pipeline_version = metadata.get("pipeline_version")
    if pipeline_version:
        lines.append(f"| **Pipeline Version** | `{pipeline_version}` |")

    return [_text_panel("Run Provenance", "\n".join(lines), "Provenance")]


# ---------------------------------------------------------------------------
# Dashboard-level links
# ---------------------------------------------------------------------------


def _build_dashboard_links_list(services: List[Any]) -> List[Dict[str, Any]]:
    """Build dashboard-level links for service dashboards (REQ-OBP-102f)."""
    links: List[Dict[str, Any]] = []
    for svc in services:
        links.append({
            "title": f"{svc.service_id} Dashboard",
            "url": f"/d/cc-obs-{svc.service_id}/",
            "icon": "external link",
            "targetBlank": False,
            "type": "link",
            "includeVars": True,
            "keepTime": True,
        })
    return links


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fixup_portal_json(dashboard: Dict[str, Any]) -> Dict[str, Any]:
    """Post-process compiled portal dashboard JSON.

    Fixes text panels to full-width (w=24) since the Jsonnet panels.text()
    constructor defaults to w=12 and auto_layout uses the same default.
    """
    for panel in dashboard.get("panels", []):
        if panel.get("type") == "text":
            gp = panel.get("gridPos", {})
            gp["w"] = 24
            gp["x"] = 0
            panel["gridPos"] = gp
    return dashboard


def _badge(value: str) -> str:
    """Render a value as a markdown-friendly badge."""
    return f"**{value.upper()}**" if value else "—"


def _text_panel(title: str, content: str, group: str, height: int = 8) -> Dict[str, Any]:
    """Create a full-width text panel.

    No gridPos — auto_layout() positions relative to parent row.
    Full-width (w=24) is applied via post-processing in _fixup_portal_json().
    """
    return {
        "type": "text",
        "title": title,
        "options": {"content": content},
        "group": group,
    }


def _stat_panel(
    title: str, expr: str, group: str, unit: str = "short",
    thresholds: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create a stat panel sized for portal layout.

    No gridPos — let auto_layout() position after sibling text panels.
    """
    panel: Dict[str, Any] = {
        "type": "stat",
        "title": title,
        "expr": expr,
        "unit": unit,
        "group": group,
    }
    if thresholds:
        panel["thresholds"] = thresholds
    return panel


def _extract_alert_rules(content: str) -> List[Dict[str, Any]]:
    """Extract alert rule metadata from YAML artifact content.

    Returns a list of dicts with 'alert', 'severity', 'for' keys.
    Tolerates missing or malformed content gracefully.
    """
    if not content:
        return []
    try:
        import yaml

        data = yaml.safe_load(content)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []

    rules: List[Dict[str, Any]] = []
    # PrometheusRule CRD format: spec.groups[].rules[]
    # Artifact generator format: groups[].rules[] (no spec wrapper)
    groups = data.get("spec", {}).get("groups", []) or data.get("groups", [])
    if groups:
        for group in groups:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    rules.append({
                        "alert": rule["alert"],
                        "severity": rule.get("labels", {}).get("severity", "unknown"),
                        "for": rule.get("for", "—"),
                    })
        return rules

    # Flat rules list (simpler format from artifact generator)
    flat_rules = data.get("rules", [])
    if isinstance(flat_rules, list):
        for rule in flat_rules:
            if isinstance(rule, dict) and "alert" in rule:
                rules.append({
                    "alert": rule["alert"],
                    "severity": rule.get("labels", {}).get("severity", "unknown"),
                    "for": rule.get("for", "—"),
                })

    return rules


# ---------------------------------------------------------------------------
# Benchmark Analyst analytical sections (A3) — static markdown tables from a run's aggregate.json.
# Threaded in via metadata["aggregate"] (aggregate.json) and metadata["scoring"] (run-spec.json).
# ---------------------------------------------------------------------------

def _q(v: Any) -> str:
    return "—" if v is None else f"{float(v):.3f}"


def _usd(v: Any) -> str:
    return "—" if v is None else f"${float(v):.4f}"


def _agg(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return metadata.get("aggregate") or {}


def _build_scoring_methodology_panels(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    scoring = metadata.get("scoring") or {}
    formula = scoring.get("scoring_formula", "compile_gate + compute_disk_quality_score(0.4/0.2/0.2/0.2)")
    pass_thr = _agg(metadata).get("pass_threshold", 0.5)
    content = (
        "**Composite quality** = compile gate (PASS/FAIL) gating a structural score, where structural = "
        "contract 0.4 + imports 0.2 + stubs 0.2 + semantic 0.2.\n\n"
        f"- **Formula (this run):** `{formula}`\n"
        f"- **Pass threshold:** {pass_thr}\n"
        "- **Composite vs structural:** composite is gated (compile-fail → floor); structural is the raw "
        "disk-quality score. Read both — high structural with a compile-fail is not a pass.\n"
        "- **Exclusions:** infra/integrity cells are NOT model failures (see Exclusions)."
    )
    return [_text_panel("Scoring Methodology", content, "Scoring Methodology")]


def _build_leaderboard_panels(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_model = _agg(metadata).get("by_model") or {}
    if not by_model:
        return [_text_panel("Leaderboard", "_No run data — generate against a finished run dir._", "Leaderboard")]
    rows = []
    for model, m in by_model.items():
        q, iqr, cost = m.get("quality_median"), m.get("quality_iqr"), m.get("cost_total_usd")
        cpq = (cost / q) if (cost and q) else None
        rows.append((q or 0, cost or 0, model, q, iqr, m.get("pass_rate"), cost, cpq))
    rows.sort(key=lambda r: (-r[0], r[1]))  # quality desc, then cost asc
    header = "| Model | Quality (median ± IQR) | Pass rate | Cost (USD) | Cost / quality |"
    sep = "|-------|------------------------|-----------|------------|----------------|"
    body = [
        f"| `{model}` | {_q(q)} ± {_q(iqr)} | {_q(pr)} | {_usd(cost)} | {_usd(cpq)} |"
        for _, _, model, q, iqr, pr, cost, cpq in rows
    ]
    note = "\n\n_Composite quality saturates (~1.0) → **cost-per-quality** is the differentiator._"
    return [_text_panel("Leaderboard", "\n".join([header, sep] + body) + note, "Leaderboard")]


def _build_quality_distribution_panels(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    agg = _agg(metadata)
    overall, by_model = agg.get("overall") or {}, agg.get("by_model") or {}
    if not overall:
        return [_text_panel("Quality Distribution", "_No run data._", "Quality Distribution")]
    lines = [
        f"**Overall:** median {_q(overall.get('quality_median'))} ± IQR {_q(overall.get('quality_iqr'))} · "
        f"pass-rate {_q(overall.get('pass_rate'))} · catastrophic {overall.get('catastrophic_count', 0)} · "
        f"N={overall.get('n_scored', 0)}/{overall.get('n', 0)}",
        "",
        "| Model | Median | IQR (reliability) | N scored |",
        "|-------|--------|-------------------|----------|",
    ]
    for model, m in sorted(by_model.items(), key=lambda kv: -(kv[1].get("quality_iqr") or 0)):
        flag = " ⚠️ high variance" if (m.get("quality_iqr") or 0) > 0.1 else ""
        lines.append(f"| `{model}` | {_q(m.get('quality_median'))} | {_q(m.get('quality_iqr'))}{flag} | {m.get('n_scored', 0)} |")
    lines.append("\n_High IQR = low reliability; low N = low confidence._")
    return [_text_panel("Quality Distribution", "\n".join(lines), "Quality Distribution")]


def _build_exclusions_panels(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    agg = _agg(metadata)
    overall, by_model = agg.get("overall") or {}, agg.get("by_model") or {}
    lines = [
        f"**{overall.get('infra_fail_count', 0)} cells excluded as infra/integrity** (NOT model failures). "
        "A dead key / 429 quota / sandbox void must not tank a model's score.\n",
        "| Model | infra_fail (excluded) | catastrophic |",
        "|-------|-----------------------|--------------|",
    ]
    for model, m in by_model.items():
        if (m.get("infra_fail_count") or 0) or (m.get("catastrophic_count") or 0):
            lines.append(f"| `{model}` | {m.get('infra_fail_count', 0)} | {m.get('catastrophic_count', 0)} |")
    if len(lines) == 3:
        lines.append("| _(none this run)_ | 0 | 0 |")
    return [_text_panel("Exclusions", "\n".join(lines), "Exclusions")]


def _build_service_discrimination_panels(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_service = _agg(metadata).get("by_service") or {}
    if not by_service:
        return [_text_panel("Service Discrimination", "_No run data._", "Service Discrimination")]
    rows = sorted(by_service.items(), key=lambda kv: (kv[1].get("quality_median") or 1.0))
    lines = [
        "Services that **separate** the models surface first (lowest median / highest IQR).\n",
        "| Service | Median quality | IQR |",
        "|---------|----------------|-----|",
    ]
    for svc, s in rows:
        lines.append(f"| `{svc}` | {_q(s.get('quality_median'))} | {_q(s.get('quality_iqr'))} |")
    lines.append("\n_The lowest-quality / highest-IQR service is the discriminator (often checkoutservice)._")
    return [_text_panel("Service Discrimination", "\n".join(lines), "Service Discrimination")]


def _build_deeper_analysis_panels(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    content = (
        "Levers for going deeper than the leaderboard:\n"
        "- **Re-score replay** — re-run scoring from saved artifacts without re-spending (parent FR-37).\n"
        "- **Weight sensitivity** — perturb the 0.4/0.2/0.2/0.2 weights ±0.1; does the top-3 order hold? (FR-11)\n"
        "- **Blind human-validation** — score↔human correlation on a small blind sample (FR-52).\n"
        "- **Contamination probe** — rename-perturbation + verbatim tells; memorization vs capability (FR-47).\n"
        "- **Raw data** — `cells.json` (per-cell quality/compile/cost/sandbox), the tracking spans, the join contract."
    )
    return [_text_panel("Deeper Analysis", content, "Deeper Analysis")]
