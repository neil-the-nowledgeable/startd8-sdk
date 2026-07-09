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

import re
from typing import Any, Dict, List, Tuple

from .state import KickoffState

# --- UID / slug (FR-5) -----------------------------------------------------------------------------
# The Workbook UID is derived 1:1 from the project name by this single named function (the Reference
# Audit pins it). The literal ``index`` slug is RESERVED for the portfolio-index dashboard (FR-11) so a
# project can never collide with it.
WORKBOOK_TAG = "workbook"  # FR-11 contract: every Workbook carries this tag (the index dashlist filters on it)
INDEX_UID = "cc-portal-kickoff-index"
INDEX_TITLE = "Digital Project Workbooks — Index"
RESERVED_INDEX_SLUG = "index"


class WorkbookSlugError(ValueError):
    """A project name cannot be turned into a valid, non-reserved Workbook UID (FR-5)."""


def slugify_project(project: str) -> str:
    """Deterministic slug: lowercase, ``_``/space → ``-``, drop other chars, collapse/trim ``-``."""
    s = (project or "").strip().lower().replace("_", "-").replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    return re.sub(r"-+", "-", s).strip("-")


def workbook_uid(project: str) -> str:
    """Return ``cc-portal-kickoff-{slug}``; raise :class:`WorkbookSlugError` on empty/reserved (FR-5)."""
    slug = slugify_project(project)
    if not slug:
        raise WorkbookSlugError(
            f"project name {project!r} slugifies to empty — cannot form a Workbook UID"
        )
    if slug == RESERVED_INDEX_SLUG:
        raise WorkbookSlugError(
            f"project name {project!r} slugifies to the reserved '{RESERVED_INDEX_SLUG}', which collides "
            f"with the portfolio-index UID {INDEX_UID!r}. Rename the project."
        )
    return f"cc-portal-kickoff-{slug}"


def build_workbook_index_spec() -> Dict[str, Any]:
    """Build the portfolio-index ``DashboardSpec`` (FR-11): a single ``dashlist`` filtered to the
    ``workbook`` tag. Self-updating — Grafana resolves the tag at view time — so it is a singleton
    generated once (idempotent UID) and never regenerated when a new project appears. Deterministic, $0.
    """
    return {
        "title": INDEX_TITLE,
        "uid": INDEX_UID,
        "description": (
            "Portfolio index of every project's Digital Project Workbook. The list is a Grafana "
            f"dashlist filtered to the '{WORKBOOK_TAG}' tag — it stays current automatically as "
            "projects are created ($0, deterministic; no per-project registry)."
        ),
        "tags": ["portal", "kickoff", WORKBOOK_TAG, "index"],
        "panels": [
            {
                "type": "dashlist",
                "title": "Project Workbooks",
                "options": {
                    "tags": [WORKBOOK_TAG],
                    "showHeadings": True,
                    "showSearch": False,
                },
            }
        ],
        "variables": [],
        "links": [],
    }


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

# The audience-default override state (Slice B, FR-5): a machine-shielded default the audience pre-pass
# set *for* a Beginner. A distinct glyph — NOT ``✅`` (which the intro legend + _ATTENTION_DISPLAY["ok"]
# bind to human/extraction confirmation) — so a shielded default never reads as author-confirmed.
_AUDIENCE_DEFAULT_DISPLAY: Tuple[str, str] = ("🛡️", "safe default set for you")
# Sort rank ≥ ``ok`` (never ``blocked``'s 0): a shielded field is resolved-for-you, not a gap, so it must
# not re-sort to the "gaps first" top it was meant to remove (FR-7).
_AUDIENCE_DEFAULT_SORT: int = 3

# the 4 canonical kickoff input domains -> their manifest filename (extraction groups by manifest)
_DOMAIN_MANIFEST: Dict[str, str] = {
    "business-targets": "business-targets.yaml",
    "observability": "observability.yaml",
    "conventions": "conventions.yaml",
    "build-preferences": "build-preferences.yaml",
}
_MANIFEST_DOMAIN: Dict[str, str] = {v: k for k, v in _DOMAIN_MANIFEST.items()}

_VALUE_SNIPPET_LEN = 48


def _md_escape(value: Any) -> str:
    """Escape a short cell value for a Markdown table (no truncation)."""
    return str(value).replace("\n", " ").replace("|", "\\|")


def _value_snippet(value: Any, limit: int = _VALUE_SNIPPET_LEN) -> str:
    s = _md_escape(value)
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


def _workbook_narrative(tier: str) -> str:
    """The Workbook intro narrative at the resolved disclosure tier (Slice A, FR-2/FR-4). Owned by the
    ``workbook`` experience doc; a lazy import avoids an import cycle (same convention as
    ``explain_input_domain`` below). ``tier="light"`` reproduces the pre-audience narrative byte-for-byte;
    ``expanded`` (Beginner) serves the PLAIN rewrite; ``compact`` (Advanced) degrades to ``light``.
    """
    from startd8.concierge.writes import load_experience_doc

    return load_experience_doc("workbook", tier=tier)


def _shielded_value_paths(provenance: Dict[str, Any] | None) -> set:
    """The value_paths shielded by the audience pre-pass (``audience-default:*`` provenance). Fail-open:
    ``None``/empty/malformed ledger → empty set (FR-6). This is the single filtering locus (R1-S6/R2-S5)
    — both the overview count discount and the per-row badge derive shielded-ness from here.
    """
    if not provenance:
        return set()
    from startd8.concierge.confirmation import is_audience_default

    return {vp for vp, entry in provenance.items() if is_audience_default(entry)}


def _rendered_for_note(audience: Any) -> str:
    """OQ-3: a one-line "Rendered for: <audience>" transparency note for a **non-default** audience.
    Structurally gated — returns ``""`` for Intermediate/None so it never perturbs the Intermediate
    byte-identity guarantee (R1-S8). Reads ``audience.value`` (the token), never ``str(audience)``.
    """
    from startd8.concierge.audience import KickoffAudience, coerce_audience

    aud = coerce_audience(audience)
    if aud is None or aud is KickoffAudience.INTERMEDIATE:
        return ""
    return (
        f"\n\n_Rendered for: **{aud.value}** — re-run `startd8 kickoff portal` "
        "if your audience changes._"
    )


def _overview_panels(
    state: KickoffState,
    by_manifest: Dict[str, List[Any]],
    *,
    tier: str = "light",
    audience: Any = None,
    provenance: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    ac = state.attention_counts
    total = len(state.fields) or 1
    ok = ac.get("ok", 0)
    review = ac.get("review", 0)
    blocked = ac.get("blocked", 0)
    ok_ratio = ok / total

    # Slice B (FR-7): discount audience-default-shielded gaps from the two gap-facing figures only.
    # The single filtering locus (Step 5): intersect ledger-shielded value_paths with the *extraction*
    # basis (attention=="blocked") BEFORE subtracting, so a shielded vp absent from state has no effect
    # (no underflow) and the floor is 0.
    shielded = _shielded_value_paths(provenance)
    shielded_gaps = {
        f.value_path
        for f in state.fields
        if f.attention == "blocked" and f.value_path in shielded
    }
    blocked_display = max(0, blocked - len(shielded_gaps))

    # Slice A (FR-2/FR-4): the narrative intro is owned by the workbook experience doc, rendered at the
    # resolved disclosure tier. The legend + status line + trailing note stay code-side (state, not prose).
    # For tier="light" (Intermediate/unset) with no shields and no audience note, this composes
    # byte-identically to the pre-audience inline string (the byte-identity guarantee).
    narrative = _workbook_narrative(tier)
    legend_extra = (
        f"| {_AUDIENCE_DEFAULT_DISPLAY[0]} {_AUDIENCE_DEFAULT_DISPLAY[1]} "
        "| machine-set default you can change |\n"
        if shielded
        else ""
    )
    set_for_you = f" · {len(shielded)} set for you" if shielded else ""
    intro = (
        narrative
        + "\n\n"
        + "| Confirmation | Meaning |\n|---|---|\n"
        + "| ✅ confirmed | extracted from your authoring docs |\n"
        + "| 🟡 review | SDK-defaulted — worth a look |\n"
        + "| 🔴 gap | not extracted — **author action needed** |\n"
        + legend_extra
        + "\n"
        + f"**{ok}/{total} fields confirmed** · {review} to review · **{blocked_display} gaps** "
        + f"· grammar `{state.grammar_version}`."
        + set_for_you
        + "\n\n"
        + "_Current state only; the confirmation burndown over time arrives with the metric emit seam._"
        + _rendered_for_note(audience)
    )

    panels: List[Dict[str, Any]] = [
        {
            "type": "text",
            "title": "Digital Project Workbook",
            "options": {"content": intro},
            "group": "Overview",
        },
        {
            "type": "gauge",
            "title": "Fields Confirmed",
            "expr": f"vector({ok_ratio:.4f})",
            "unit": "percentunit",
            "thresholds": [
                {"value": None, "color": "red"},
                {"value": 0.75, "color": "yellow"},
                {"value": 0.95, "color": "green"},
            ],
            "group": "Overview",
        },
        {
            "type": "stat",
            "title": "Open Gaps (author action)",
            "expr": f"vector({blocked_display})",
            "unit": "short",
            "thresholds": [
                {"value": None, "color": "green"},
                {"value": 1, "color": "red"},
            ],
            "group": "Overview",
        },
    ]
    for slug, manifest in _DOMAIN_MANIFEST.items():
        fields = by_manifest.get(manifest)
        if not fields:
            continue
        panels.append(
            {
                "type": "stat",
                "title": f"{slug} · confirmed",
                "expr": f"vector({_confirmed_ratio(fields):.4f})",
                "unit": "percentunit",
                "thresholds": [
                    {"value": None, "color": "red"},
                    {"value": 0.75, "color": "yellow"},
                    {"value": 0.95, "color": "green"},
                ],
                "group": "Overview",
            }
        )
    return panels


def _manifest_section(
    manifest: str, fields: List[Any], provenance: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    from startd8.concierge.confirmation import is_audience_default

    prov = provenance or {}

    def _row_rank(f: Any) -> int:
        # Slice B (FR-5/R1-S2): a shielded field sorts with/after `ok` (never at blocked's rank 0), so a
        # resolved-for-you default doesn't re-appear in the "gaps first" ordering it was meant to remove.
        if is_audience_default(prov.get(f.value_path)):
            return _AUDIENCE_DEFAULT_SORT
        return _ATTENTION_SORT.get(f.attention, 9)

    ordered = sorted(fields, key=lambda f: (_row_rank(f), f.value_path))
    slug = _MANIFEST_DOMAIN.get(manifest)
    lines: List[str] = []
    if slug:
        # cite the canonical What/Why/Who — single-source vocabulary (lazy import avoids any cycle)
        from startd8.concierge.core import explain_input_domain

        ex = explain_input_domain(slug)
        title = ex["label"]
        lines += [
            f"### {ex['label']} — _{ex['question']}_",
            "",
            f"**Who:** {ex['who']}",
            "",
        ]
    else:
        title = manifest.replace(".yaml", "")
        lines += [f"### {title}", ""]

    lines += ["| Field | State | Value |", "|---|---|---|"]
    for f in ordered:
        # Slice B (FR-5): an audience-default-shielded field renders the 🛡️ override glyph INSTEAD of its
        # extraction attention glyph — a machine-set default reads distinctly from a human/extracted ✅.
        if is_audience_default(prov.get(f.value_path)):
            emoji, label = _AUDIENCE_DEFAULT_DISPLAY
        else:
            emoji, label = _ATTENTION_DISPLAY.get(f.attention, ("", f.attention))
        value = _value_snippet(f.value) if f.value is not None else "_—_"
        lines.append(f"| `{f.value_path}` | {emoji} {label} | {value} |")

    return {
        "type": "text",
        "title": f"{title} ({manifest})",
        "options": {"content": "\n".join(lines)},
        "group": title,
    }


def _latest_run_lines(panel_results: List[Dict[str, Any]]) -> List[str]:
    """Render the latest stakeholder-panel run (answers from the most-recent transcript)."""
    if not panel_results:
        return []
    first = panel_results[0]
    total_cost = sum(float(a.get("cost_usd") or 0.0) for a in panel_results)
    session = _md_escape(first.get("session_id", "?"))
    question = _md_escape(first.get("question", ""))
    created = _md_escape(first.get("created_at", ""))
    lines = [
        "",
        f"**Latest run** — session `{session}` · {created} · {len(panel_results)} answers "
        f"· ~${total_cost:.4f}",
        f"_Question:_ {question}",
        "",
        "> ⚠ **SYNTHETIC & UNRATIFIED** — role-played stand-ins, not real stakeholders. "
        "Confirm with a human before relying on these.",
        "",
        "| Role | Grounding | Answer |",
        "|---|---|---|",
    ]
    for a in panel_results:
        lines.append(
            f"| `{_md_escape(a.get('role_id', ''))}` | {_md_escape(a.get('grounding', ''))} "
            f"| {_value_snippet(a.get('text', ''), 160)} |"
        )
    return lines


def _stakeholders_section(
    roster: Any, panel_results: List[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    """Render the Stakeholders section — the panel's roster + latest run (a key part of the Workbook).

    ``roster`` is a loaded ``Roster`` (duck-typed: ``.personas`` with ``.role_id``/``.display_name``/
    ``.answers_for``) or ``None`` when no roster file exists. ``panel_results`` is the latest run's
    answer dicts (``role_id``/``text``/``grounding``/``cost_usd``/``question``/``session_id``), if any.
    Phase 1/1.5 is display-only ($0); *running* the panel from the dashboard is Phase 2.
    """
    lines = [
        "### Stakeholders",
        "",
        "_The panel of stakeholder personas — a key part of the Workbook._",
        "",
    ]
    personas = list(getattr(roster, "personas", []) or []) if roster is not None else []
    if not personas:
        lines += [
            "**No stakeholder roster yet.** Scaffold one with "
            "`startd8 kickoff instantiate`, then run the panel with "
            "`startd8 kickoff stakeholders ask-all` (paid, synthetic).",
        ]
    else:
        lines += ["| Role | Persona | Answers for |", "|---|---|---|"]
        for p in personas:
            answers_for = ", ".join(getattr(p, "answers_for", []) or []) or "_—_"
            lines.append(
                f"| `{_md_escape(getattr(p, 'role_id', ''))}` "
                f"| {_md_escape(getattr(p, 'display_name', ''))} | {_md_escape(answers_for)} |"
            )
        lines += [
            "",
            f"**{len(personas)} personas.** Run the panel: "
            "`startd8 kickoff stakeholders ask-all` (paid — answers are **SYNTHETIC & UNRATIFIED**, "
            "confirm with a human before relying on them).",
        ]
    lines += _latest_run_lines(panel_results or [])
    return {
        "type": "text",
        "title": "Stakeholders",
        "options": {"content": "\n".join(lines)},
        "group": "Stakeholders",
    }


def _apply_status(pipeline: Dict[str, Any]) -> str:
    inbox = pipeline.get("inbox") or {}
    disp = pipeline.get("dispositions") or {}
    if inbox.get("present"):
        return f"⏳ {inbox.get('count', 0)} proposal(s) in the VIPP inbox — pending negotiate/apply."
    if disp.get("present"):
        return "✅ inbox consumed — dispositions applied (or negotiated & drained)."
    return "—"


def _pipeline_section(pipeline: Dict[str, Any] | None) -> Dict[str, Any]:
    """Render the panel→bridge→VIPP processing funnel (Increment 3 M-display; read-only, $0).

    ``pipeline`` (assembled by the CLI from the 4 stores) has ``staged`` (Recommendation dicts),
    ``inbox`` ({present,count,envelope_seq}), ``dispositions`` ({present,counts,evidence_available,
    items,advisories}). Everything shown is SYNTHETIC & UNRATIFIED; nothing here is authored.
    """
    lines = [
        "### Panel Processing Pipeline",
        "",
        "_How the panel's synthetic suggestions become structured, adjudicated, human-gated field "
        "changes: triage → staged → VIPP inbox → dispositions → apply._",
        "",
    ]
    if not pipeline or not any(
        (
            pipeline.get("staged"),
            (pipeline.get("inbox") or {}).get("present"),
            (pipeline.get("dispositions") or {}).get("present"),
        )
    ):
        lines += [
            "**No pipeline activity yet.** Run the panel, then `startd8 kickoff stakeholders propose "
            "--run` (stage) → `--serialize` (to VIPP) → `startd8 vipp negotiate` → `vipp apply`.",
        ]
        return {
            "type": "text",
            "title": "Panel Processing Pipeline",
            "options": {"content": "\n".join(lines)},
            "group": "Panel Pipeline",
        }

    staged = pipeline.get("staged") or []
    disp = pipeline.get("dispositions") or {}
    n_accepted = sum(1 for r in staged if r.get("disposition") == "accepted")
    inbox_ct = (pipeline.get("inbox") or {}).get("count", 0)
    d_counts = disp.get("counts") or {}
    lines += [
        f"**Funnel:** {len(staged)} staged ({n_accepted} accepted) → {inbox_ct} in inbox → "
        f"{sum(d_counts.values())} dispositioned {dict(d_counts)}",
        "",
        f"**Apply status:** {_apply_status(pipeline)}",
        "",
        "> ⚠ **SYNTHETIC & UNRATIFIED** — staged values are `estimate` provenance (draft starters), "
        "never confirmed field values; ground truth *adjudicates, never originates*.",
        "",
    ]
    if staged:
        lines += [
            "#### Staged recommendations",
            "| Field | Disposition | Grounding | Draft value |",
            "|---|---|---|---|",
        ]
        for r in staged:
            lines.append(
                f"| `{_md_escape(r.get('value_path', ''))}` | {_md_escape(r.get('disposition', 'draft'))} "
                f"| {_md_escape(r.get('grounding', ''))} | {_value_snippet(r.get('recommended_value', ''), 60)} |"
            )
        lines.append("")
    items = disp.get("items") or []
    if items:
        ev = (
            ""
            if disp.get("evidence_available", True)
            else " _(evidence unavailable — degraded/narrative)_"
        )
        lines += [
            f"#### VIPP dispositions{ev}",
            "| Proposal | Decision | Reason |",
            "|---|---|---|",
        ]
        for it in items:
            lines.append(
                f"| `{_md_escape(str(it.get('proposal_id', ''))[:12])}` | {_md_escape(it.get('decision', ''))} "
                f"| {_value_snippet(it.get('reason', ''), 80)} |"
            )
        lines.append("")
    for adv in (
        disp.get("advisories") or []
    ):  # anti-anchoring: show the question next to the advisory
        q = _md_escape(adv.get("question", adv.get("symbol", "")))
        lines += [
            f"> _Panel advisory (SYNTHETIC) re: {q}:_ {_value_snippet(adv.get('advisory', adv.get('text', '')), 160)}"
        ]
    return {
        "type": "text",
        "title": "Panel Processing Pipeline",
        "options": {"content": "\n".join(lines)},
        "group": "Panel Pipeline",
    }


def build_kickoff_portal_spec(
    state: KickoffState,
    project: str,
    *,
    roster: Any = None,
    panel_results: List[Dict[str, Any]] | None = None,
    pipeline: Dict[str, Any] | None = None,
    audience: Any = None,
    tier: str = "light",
    provenance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a ``DashboardSpec`` dict for the kickoff portal from the canonical state.

    Pure function — deterministic in *(state, project, roster, panel_results, audience, tier,
    provenance)*, no I/O. The returned dict is the input to ``DashboardCreatorWorkflow.run(...)``.
    ``roster`` (optional) adds the Stakeholders section; ``panel_results`` (optional) renders the latest
    run's answers.

    Audience personalization (Era 1, classic schema):
    - ``tier`` — the disclosure tier (``light``/``expanded``/``compact``) the overview intro is rendered
      at; the caller resolves it via ``disclosure_tier(audience)``. Defaults to ``light`` = the
      pre-audience narrative, byte-for-byte.
    - ``audience`` — the resolved ``KickoffAudience`` enum (``AudienceResolution.value``); drives the
      optional "Rendered for:" note (non-default audiences only).
    - ``provenance`` — the raw ledger entry map ``{value_path: entry}`` from ``load_ledger`` (entries may
      carry an optional ``audience-default:*`` provenance); drives the 🛡️ badge + honest gap counts.
      Fail-open: ``None``/empty reproduces today's board exactly.
    """
    by_manifest: Dict[str, List[Any]] = {}
    for f in state.fields:
        by_manifest.setdefault(f.manifest, []).append(f)

    panels: List[Dict[str, Any]] = _overview_panels(
        state, by_manifest, tier=tier, audience=audience, provenance=provenance
    )
    for manifest in sorted(by_manifest, key=_manifest_sort_key):
        panels.append(_manifest_section(manifest, by_manifest[manifest], provenance))
    panels.append(_stakeholders_section(roster, panel_results))
    if pipeline is not None:
        panels.append(_pipeline_section(pipeline))

    return {
        "title": f"{project} — Digital Project Workbook",
        "uid": workbook_uid(project),  # FR-5: 1:1 named slug, reserves `index`
        "description": (
            f"Digital Project Workbook for {project} — canonical KickoffState projected to Grafana "
            f"($0, deterministic; dynamic/query-based). Re-run `startd8 kickoff portal` to refresh."
        ),
        # FR-11 contract: WORKBOOK_TAG MUST be present — the portfolio index dashlist filters on it.
        "tags": ["portal", "kickoff", WORKBOOK_TAG, project],
        "panels": panels,
        # prometheusDatasource var: required by the stat/gauge panels + the workflow's templating check
        "variables": [
            {
                "type": "prometheusDatasource",
                "name": "datasource",
                "label": "Data Source",
            }
        ],
        "links": [],
    }
