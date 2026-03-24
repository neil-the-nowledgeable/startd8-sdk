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
) -> Dict[str, Any]:
    """Build a DashboardSpec dict for the onboarding portal.

    Args:
        business: BusinessContext from artifact_generator.
        services: List[ServiceHints] — already filtered (no phantoms).
        report: GenerationReport with artifacts from alerts/dashboards/SLOs.
        metadata: Raw onboarding-metadata.json dict.
        persona: Portal variant — "operator", "engineer", or "manager".

    Returns:
        Dict consumable by DashboardCreatorWorkflow (DashboardSpec shape).
    """
    sections = _PERSONA_SECTIONS.get(persona, _PERSONA_SECTIONS["operator"])
    project_id = business.project_id or "unknown"
    uid_suffix = f"-{persona}" if persona != "operator" else ""
    # UID follows cc-{pack}-{slug} convention for DashboardCreatorWorkflow compatibility
    uid_project = project_id.lower().replace("_", "-")

    panels: List[Dict[str, Any]] = []

    if "overview" in sections:
        panels.extend(_build_project_overview_panels(business, report))
        panels.extend(_build_persona_value_panel(persona))

    if "services" in sections:
        panels.extend(_build_service_inventory_panels(services, report))

    if "objectives" in sections:
        panels.extend(_build_objectives_panels(metadata))

    if "alerts" in sections:
        panels.extend(_build_alert_inventory_panels(report))

    if "dashboards" in sections:
        panels.extend(_build_dashboard_links_panels(report))

    if "communication" in sections:
        panels.extend(_build_communication_graph_panels(metadata))

    if "quality" in sections:
        panels.extend(_build_quality_panels(report, metadata))

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
    """Build portal specs for all personas."""
    return [
        build_portal_spec(business, services, report, metadata, persona=p)
        for p in _PERSONA_SECTIONS
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


def _build_persona_value_panel(persona: str) -> List[Dict[str, Any]]:
    """Build persona-specific value proposition panel."""
    info = _PERSONA_VALUE.get(persona)
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
        f"| Field | Value |",
        f"|-------|-------|",
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
    report: Any, metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """REQ-OBP-104: Quality metrics from observability-manifest quality_summary."""
    # Try quality from report artifacts first
    scored = [a for a in report.artifacts if a.quality]
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
                {"value": 0.6, "color": "yellow"},
                {"value": 0.8, "color": "green"},
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
