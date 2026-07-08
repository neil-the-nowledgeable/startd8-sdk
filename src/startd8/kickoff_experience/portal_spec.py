"""Kickoff portal — deterministic ($0) Grafana DashboardSpec from the canonical KickoffState.

A third kickoff *presentation* surface (alongside the HTMX web UI and the TUI): project the canonical
kickoff state onto a Grafana dashboard. This module is the **spec builder** only — it turns a
:class:`~startd8.kickoff_experience.state.KickoffState` into a ``DashboardSpec`` dict that
``DashboardCreatorWorkflow`` compiles (jsonnet → Grafana JSON). No LLM, no I/O, no hand-authored JSON.

Design (docs/design/kickoff-portal/):
  * **Single source of truth (FR-3):** derives from the same ``KickoffState`` the web/TUI surfaces
    consume — never a re-parse of the input YAML. The per-field *attention* (ok/review/blocked/backlog)
    is the confirmation model.
  * **Option 1 (bake + re-provision):** current state is rendered into the panels at generation time;
    re-run to refresh. No live metric pipeline (that is the deferred M1 emit seam), no endpoint.
  * **Single-source vocabulary:** the per-domain What/Why/Who is *cited* from
    :func:`startd8.concierge.core.explain_input_domain`, not restated here.
  * **Own namespace:** deliberately NOT folded into ``observability/portal_spec_builder.py`` (which
    owns the persona-gated *onboarding* portal) — this is domain-gated and kickoff-specific.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .state import KickoffState

# canonical attention -> (emoji, short label). Attention is derived once in state.py; we never
# re-derive it here (parity guarantee).
_ATTENTION_DISPLAY: Dict[str, Tuple[str, str]] = {
    "ok": ("✅", "confirmed"),
    "review": ("🟡", "review — SDK-defaulted"),
    "blocked": ("🔴", "gap — author action needed"),
    "backlog": ("⚪", "backlog"),
}
# gaps first when listing a manifest's fields
_ATTENTION_SORT: Dict[str, int] = {"blocked": 0, "review": 1, "backlog": 2, "ok": 3}

# the 4 canonical kickoff input domains -> their manifest filename (extraction groups by manifest)
_DOMAIN_MANIFEST: Dict[str, str] = {
    "business-targets": "business-targets.yaml",
    "observability": "observability.yaml",
    "conventions": "conventions.yaml",
    "build-preferences": "build-preferences.yaml",
}
_MANIFEST_DOMAIN: Dict[str, str] = {v: k for k, v in _DOMAIN_MANIFEST.items()}

_VALUE_SNIPPET_LEN = 48


def _value_snippet(value: Any, limit: int = _VALUE_SNIPPET_LEN) -> str:
    s = str(value).replace("\n", " ").replace("|", "\\|")
    return (s[:limit] + "…") if len(s) > limit else s


def _confirmed_ratio(fields: List[Any]) -> float:
    if not fields:
        return 0.0
    return sum(1 for f in fields if f.attention == "ok") / len(fields)


def _manifest_sort_key(manifest: str):
    """Canonical domains first (in declared order), then any other manifests alphabetically."""
    if manifest in _MANIFEST_DOMAIN:
        return (0, list(_DOMAIN_MANIFEST.values()).index(manifest))
    return (1, manifest)


def _overview_panels(state: KickoffState, by_manifest: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    ac = state.attention_counts
    total = len(state.fields) or 1
    ok = ac.get("ok", 0)
    review = ac.get("review", 0)
    blocked = ac.get("blocked", 0)
    ok_ratio = ok / total

    intro = (
        "The **Digital Project Workbook** — the shared, whole-project view of the foundational kickoff "
        "decisions. A dynamic, query-based evolution of Brooks' workbook (_The Mythical Man-Month_), "
        "which was static (paper/microfiche); this one is generated from live project state. State is "
        "the canonical `KickoffState` (the same `$0` extraction the web UI and TUI use) — projected into "
        "these panels. Re-run `startd8 kickoff portal` to refresh.\n\n"
        "| Confirmation | Meaning |\n|---|---|\n"
        "| ✅ confirmed | extracted from your authoring docs |\n"
        "| 🟡 review | SDK-defaulted — worth a look |\n"
        "| 🔴 gap | not extracted — **author action needed** |\n\n"
        f"**{ok}/{total} fields confirmed** · {review} to review · **{blocked} gaps** "
        f"· grammar `{state.grammar_version}`.\n\n"
        "_Current state only; the confirmation burndown over time arrives with the metric emit seam._"
    )

    panels: List[Dict[str, Any]] = [
        {"type": "text", "title": "Digital Project Workbook", "options": {"content": intro}, "group": "Overview"},
        {
            "type": "gauge", "title": "Fields Confirmed", "expr": f"vector({ok_ratio:.4f})",
            "unit": "percentunit",
            "thresholds": [
                {"value": None, "color": "red"},
                {"value": 0.75, "color": "yellow"},
                {"value": 0.95, "color": "green"},
            ],
            "group": "Overview",
        },
        {
            "type": "stat", "title": "Open Gaps (author action)", "expr": f"vector({blocked})",
            "unit": "short",
            "thresholds": [{"value": None, "color": "green"}, {"value": 1, "color": "red"}],
            "group": "Overview",
        },
    ]
    for slug, manifest in _DOMAIN_MANIFEST.items():
        fields = by_manifest.get(manifest)
        if not fields:
            continue
        panels.append({
            "type": "stat", "title": f"{slug} · confirmed",
            "expr": f"vector({_confirmed_ratio(fields):.4f})", "unit": "percentunit",
            "thresholds": [
                {"value": None, "color": "red"},
                {"value": 0.75, "color": "yellow"},
                {"value": 0.95, "color": "green"},
            ],
            "group": "Overview",
        })
    return panels


def _manifest_section(manifest: str, fields: List[Any]) -> Dict[str, Any]:
    ordered = sorted(fields, key=lambda f: (_ATTENTION_SORT.get(f.attention, 9), f.value_path))
    slug = _MANIFEST_DOMAIN.get(manifest)
    lines: List[str] = []
    if slug:
        # cite the canonical What/Why/Who — single-source vocabulary (lazy import avoids any cycle)
        from startd8.concierge.core import explain_input_domain

        ex = explain_input_domain(slug)
        title = ex["label"]
        lines += [f"### {ex['label']} — _{ex['question']}_", "", f"**Who:** {ex['who']}", ""]
    else:
        title = manifest.replace(".yaml", "")
        lines += [f"### {title}", ""]

    lines += ["| Field | State | Value |", "|---|---|---|"]
    for f in ordered:
        emoji, label = _ATTENTION_DISPLAY.get(f.attention, ("", f.attention))
        value = _value_snippet(f.value) if f.value is not None else "_—_"
        lines.append(f"| `{f.value_path}` | {emoji} {label} | {value} |")

    return {
        "type": "text",
        "title": f"{title} ({manifest})",
        "options": {"content": "\n".join(lines)},
        "group": title,
    }


def build_kickoff_portal_spec(state: KickoffState, project: str) -> Dict[str, Any]:
    """Build a ``DashboardSpec`` dict for the kickoff portal from the canonical state.

    Pure function — deterministic in *(state, project)*, no I/O. The returned dict is the input to
    ``DashboardCreatorWorkflow.run({"spec": spec, ...})``.
    """
    by_manifest: Dict[str, List[Any]] = {}
    for f in state.fields:
        by_manifest.setdefault(f.manifest, []).append(f)

    panels: List[Dict[str, Any]] = _overview_panels(state, by_manifest)
    for manifest in sorted(by_manifest, key=_manifest_sort_key):
        panels.append(_manifest_section(manifest, by_manifest[manifest]))

    uid_project = project.lower().replace("_", "-").replace(" ", "-")
    return {
        "title": f"{project} — Digital Project Workbook",
        "uid": f"cc-portal-kickoff-{uid_project}",
        "description": (
            f"Digital Project Workbook for {project} — canonical KickoffState projected to Grafana "
            f"($0, deterministic; dynamic/query-based). Re-run `startd8 kickoff portal` to refresh."
        ),
        "tags": ["portal", "kickoff", "workbook", project],
        "panels": panels,
        # prometheusDatasource var: required by the stat/gauge panels + the workflow's templating check
        "variables": [{"type": "prometheusDatasource", "name": "datasource", "label": "Data Source"}],
        "links": [],
    }
