"""Digital Project Workbook — **v2 dynamic** board (dynamic-dashboards M6, FR-8/FR-9).

The payoff of the dynamic-dashboards capability: the kickoff **audience** lens as a *runtime* Grafana
variable + conditional-rendering rules, so a viewer flips their persona **in-browser** — no regeneration,
no write (FR-9, read-only). One deterministic board carries **all** persona variants; the JSON is
identical regardless of the viewer's audience **except the ``audience`` variable's ``current`` default**
(FR-9 byte-identity).

This is the **Era-2** successor to the classic-schema Era-1 Workbook audience port. It is a *separate,
additive* v2 board (its own UID suffix ``-v2``) built on the shipped v2 emitter — it never touches the
classic ``build_kickoff_portal_spec`` / ``portal_build`` path (R2-F5), so both can coexist.

Self-contained by design (the M6 build decision): it consumes only the audience/provenance primitives
that ship on the branch — ``resolve_audience_preference`` (default Intermediate), ``load_ledger`` +
``_is_audience_default`` (the ``audience-default:*`` shield), ``KickoffState`` — and renders the tiered
intro inline (the two knobs below).

Two knobs, realized as conditional rendering on rows:
- **Disclosure** (OQ-6, intro-first for v1): a Beginner (plain-language) intro shown only when
  ``audience == 'beginner'``, and the standard intro shown for everyone else.
- **Surface** (OQ-5, coarse): a domain's ``audience-default``-shielded fields render in a **separate
  "safe defaults" subsection hidden for Beginner** (only the shielded fields collapse, not the whole
  domain), carrying the 🛡️ badge on the non-Beginner render (the Era-1 badge coexistence contract).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..concierge.audience import DEFAULT_AUDIENCE, KickoffAudience, coerce_audience
from ..concierge.confirmation import _is_audience_default
from ..dashboard_creator.v2 import (
    ConditionalRendering,
    CustomVariable,
    GridItem,
    RowsLayout,
    RowsLayoutRow,
    TabsLayout,
    TabsLayoutTab,
    V2Panel,
    VariableCondition,
    emit_v2_dashboard,
    show_when_variable,
    text_panel,
)
from .portal_spec import (
    WORKBOOK_TAG,
    _ATTENTION_DISPLAY,
    _ATTENTION_SORT,
    _manifest_sort_key,
    _MANIFEST_DOMAIN,
    _value_snippet,
    slugify_project,
)

#: The audience allowlist — a fixed `type: custom` variable, never a query/datasource var (R1-F8).
_AUDIENCES = ["beginner", "intermediate", "advanced"]

#: The audience-default override glyph (the Era-1 badge; kept in sync with the classic Workbook).
_SHIELD_DISPLAY = ("🛡️", "safe default set for you")
_AUDIENCE_DEFAULT_SORT = 3  # sort with/after `ok`, never at a gap's rank 0

# The intro narrative, inline (Era 1 owns the tiered `workbook` experience doc on another branch; M6 is
# self-contained). The Intermediate/Advanced render uses the standard narrative; Beginner the plain one.
_INTRO = (
    "The **Digital Project Workbook** — the shared, whole-project view of the foundational kickoff "
    "decisions. A dynamic, query-based evolution of Brooks' workbook (_The Mythical Man-Month_), "
    "which was static (paper/microfiche); this one is generated from live project state. "
    "Flip the **audience** variable (top of the board) to switch persona in-browser — no regeneration, "
    "no write."
)
_INTRO_BEGINNER = (
    "### Your Project Workbook\n\n"
    "This board is a **live picture of your project's setup** — the handful of foundational decisions "
    "the build needs before it can create your app. Each row is one **input**; the colored marker shows "
    "where it stands. Nothing here is final and you can't break anything — the board just reflects what's "
    "on disk. Use the **audience** selector at the top to switch how much detail you see. Start with the "
    "🔴 gaps."
)


def _audience_token(audience: Any) -> str:
    """The resolved audience token (``beginner``/``intermediate``/``advanced``); default Intermediate."""
    aud = (
        audience if isinstance(audience, KickoffAudience) else coerce_audience(audience)
    )
    return (aud or DEFAULT_AUDIENCE).value


def _hide_for_beginner() -> ConditionalRendering:
    """A show/hide rule that hides a section when ``audience == 'beginner'`` (the surface knob)."""
    return ConditionalRendering(
        visibility="hide",
        items=[VariableCondition(variable="audience", value="beginner")],
    )


def _domain_title(manifest: str) -> str:
    slug = _MANIFEST_DOMAIN.get(manifest)
    if slug:
        try:
            from ..concierge.core import explain_input_domain

            return explain_input_domain(slug)["label"]
        except Exception:  # pragma: no cover - fall back to the manifest name
            pass
    return manifest.replace(".yaml", "")


def _field_table(fields: List[Any], provenance: Dict[str, Any]) -> str:
    """A markdown field table with the per-row attention glyph, or the 🛡️ override for a shielded field."""

    def _rank(f: Any) -> int:
        if _is_audience_default(provenance.get(f.value_path)):
            return _AUDIENCE_DEFAULT_SORT
        return _ATTENTION_SORT.get(f.attention, 9)

    lines = ["| Field | State | Value |", "|---|---|---|"]
    for f in sorted(fields, key=lambda f: (_rank(f), f.value_path)):
        if _is_audience_default(provenance.get(f.value_path)):
            emoji, label = _SHIELD_DISPLAY
        else:
            emoji, label = _ATTENTION_DISPLAY.get(f.attention, ("", f.attention))
        value = _value_snippet(f.value) if f.value is not None else "_—_"
        lines.append(f"| `{f.value_path}` | {emoji} {label} | {value} |")
    return "\n".join(lines)


def _height(fields: List[Any]) -> int:
    return min(24, 4 + len(fields))


def workbook_v2_uid(project: str) -> str:
    """The v2 board's UID — a distinct ``-v2`` suffix so it coexists with the classic Workbook (no clobber)."""
    return f"cc-portal-kickoff-{slugify_project(project)}-v2"


# --------------------------------------------------------------------------- agentic cockpit (M3)

#: How many transcript turns the baked Assistant panel renders inline; the full transcript is served
#: on demand via the FR-6b Loki logs panel (OQ-2 two-tier). Kept small for text-panel readability.
_TRANSCRIPT_TAIL_CAP = 14

#: The Loki datasource uid the FR-6b logs panel binds to (the pre-provisioned Grafana datasource).
_LOKI_DATASOURCE = "loki"


def _logs_panel(pid: int, title: str, logql: str) -> V2Panel:
    """A Loki-datasource ``logs`` panel (FR-6b) — the full-transcript depth surface.

    Additive + graceful-degrade: an empty result (Loki absent / no matching lines) renders an empty
    panel, never an error. The query is static (baked), so it does not vary by audience. Datasource is
    the pre-provisioned ``loki`` uid — NOT a new startd8 endpoint (FR-11 gate uncrossed).
    """
    return V2Panel(
        id=pid,
        title=title,
        viz_config={
            "kind": "logs",
            "spec": {
                "options": {
                    "showTime": True,
                    "showLabels": False,
                    "wrapLogMessage": True,
                    "enableLogDetails": True,
                    "sortOrder": "Ascending",
                    "dedupStrategy": "none",
                },
                "fieldConfig": {"defaults": {}, "overrides": []},
            },
        },
        data={
            "kind": "QueryGroup",
            "spec": {
                "queries": [
                    {
                        "kind": "PanelQuery",
                        "spec": {
                            "refId": "A",
                            "hidden": False,
                            "query": {
                                "kind": "DataQuery",
                                "version": "v0",
                                "group": "loki",
                                "datasource": {"name": _LOKI_DATASOURCE},
                                "spec": {"expr": logql, "queryType": "range"},
                            },
                        },
                    }
                ],
                "transformations": [],
                "queryOptions": {},
            },
        },
    )


def _transcript_logql(session_id: str) -> str:
    """The FR-6b LogQL selector for one session's transcript turns (agrees with the M1 emit fields)."""
    sid = (session_id or "").replace('"', '\\"')
    from .session_snapshot import TRANSCRIPT_LOGGER_NAME

    return f'{{job="startd8", logger="{TRANSCRIPT_LOGGER_NAME}"}} | json | session_id="{sid}"'


_ROLE_LABEL = {"user": "🧑 you", "assistant": "🤖 assistant", "tool": "🔧 tool"}


def _transcript_markdown(snapshot: Any) -> str:
    """Render the capped-tail transcript as markdown (FR-6). The full depth lives in the logs panel."""
    turns = list(snapshot.turns)
    header = (
        f"_{snapshot.disclosure} · {snapshot.cost_line()} · generated {snapshot.generated_at}_\n\n"
    )
    hidden = max(0, len(turns) - _TRANSCRIPT_TAIL_CAP)
    shown = turns[-_TRANSCRIPT_TAIL_CAP:] if hidden else turns
    lines: List[str] = [header]
    if hidden:
        lines.append(f"> … {hidden} earlier turns — see the **Full Transcript** panel below.\n")
    for t in shown:
        label = _ROLE_LABEL.get(t.role, t.role)
        if t.role == "tool":
            name = f" `{t.tool_name}`" if t.tool_name else ""
            lines.append(f"**{label}{name}** — {t.text or '(result)'}")
        else:
            calls = f"  _(→ {', '.join(t.tool_calls)})_" if t.tool_calls else ""
            lines.append(f"**{label}:** {t.text or '_(no text)_'}{calls}")
    return "\n\n".join(lines)


def _md_cell(text: str) -> str:
    """Escape a value for a markdown table cell (pipes/newlines would break the row)."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def _proposals_markdown(view: Any) -> str:
    """Render the pending proposals as a markdown table with per-row copy-safe confirm commands (FR-7)."""
    rows = list(view.proposals)
    lines = [
        "_The kickoff loop only **recommends** — you confirm every write. "
        "This board never acts; copy a command to apply at your own privilege._\n",
        "| Kind | Target | Summary | ID |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {_md_cell(r.kind)} | `{_md_cell(r.target)}` | {_md_cell(r.summary)} | `{_md_cell(r.id)}` |"
        )
    lines.append("\n**Confirm commands** (copy-paste to act on a proposal):\n")
    for r in rows:
        lines.append(f"- `{r.id}` ({r.kind}):\n\n  ```\n  {r.confirm_command}\n  ```")
    return "\n".join(lines)


def _proposals_markdown_simple(view: Any) -> str:
    """A Beginner-simplified Proposals view (OQ-3): the summary + the confirm command as the teaching
    moment — no raw table / ids / targets. Not hidden (confirm is still shown), just gentler."""
    lines = [
        "_The assistant **recommends** these — nothing happens until you confirm. "
        "Copy a command below to apply it yourself._\n",
    ]
    for r in view.proposals:
        lines.append(f"**{_md_cell(r.summary)}**\n\n```\n{r.confirm_command}\n```")
    return "\n".join(lines)


def build_workbook_v2(
    state: Any,
    project: str,
    *,
    audience: Any = None,
    provenance: Optional[Dict[str, Any]] = None,
    view: Any = None,
) -> Dict[str, Any]:
    """Build the audience-personalized **v2 dynamic** agentic-cockpit Workbook board (FR-5/FR-8/FR-9).

    A ``TabsLayout`` cockpit with three read-only tabs: **Status** (the audience-personalized field
    rows — unchanged content), **Assistant** (the FR-1 snapshot transcript + FR-6b Loki depth panel),
    **Proposals** (the pending VIPP inbox + copy-safe confirm commands). ``view`` is the M2
    :class:`~startd8.kickoff_experience.agentic_view.AgenticView` (the snapshot+inbox read-model); when
    absent the Assistant/Proposals tabs render honest empty states (FR-10).

    ``audience`` seeds only the variable's ``current`` default; ``provenance`` drives the shield.
    Pure + deterministic — Status panels are numbered first, so their bytes are byte-identical to the
    pre-refactor board (R1-S4).
    """
    provenance = provenance or {}
    token = _audience_token(audience)
    shielded = {vp for vp, e in provenance.items() if _is_audience_default(e)}

    by_manifest: Dict[str, List[Any]] = {}
    for f in state.fields:
        by_manifest.setdefault(f.manifest, []).append(f)

    elements: Dict[str, Any] = {}
    counter = {"n": 0}

    def _add(title: str, content: str) -> str:
        counter["n"] += 1
        key = f"panel-{counter['n']}"
        elements[key] = text_panel(counter["n"], title, content)
        return key

    def _add_panel(panel: V2Panel) -> str:
        counter["n"] += 1
        panel.id = counter["n"]
        key = f"panel-{counter['n']}"
        elements[key] = panel
        return key

    # --- Status tab: the existing audience-personalized rows (byte-identical content; numbered first) --
    status_rows: List[RowsLayoutRow] = []

    # Disclosure (OQ-6): Beginner plain-language intro + standard intro, conditionally rendered.
    status_rows.append(
        RowsLayoutRow(
            title="Overview",
            items=[
                GridItem(element=_add("Getting Started", _INTRO_BEGINNER), height=8)
            ],
            conditional=show_when_variable("audience", "beginner"),
        )
    )
    status_rows.append(
        RowsLayoutRow(
            title="Overview",
            items=[
                GridItem(element=_add("Digital Project Workbook", _INTRO), height=6)
            ],
            conditional=_hide_for_beginner(),
        )
    )

    # Surface (OQ-5, coarse): per domain, a main panel (non-shielded) + a "safe defaults" subsection
    # (shielded fields) hidden for Beginner.
    for manifest in sorted(by_manifest, key=_manifest_sort_key):
        fields = by_manifest[manifest]
        title = _domain_title(manifest)
        non_shielded = [f for f in fields if f.value_path not in shielded]
        shielded_fields = [f for f in fields if f.value_path in shielded]

        status_rows.append(
            RowsLayoutRow(
                title=title,
                items=[
                    GridItem(
                        element=_add(title, _field_table(non_shielded, provenance)),
                        height=_height(non_shielded),
                    )
                ],
            )
        )
        if shielded_fields:
            status_rows.append(
                RowsLayoutRow(
                    title=f"{title} — set for you",
                    items=[
                        GridItem(
                            element=_add(
                                f"{title} — safe defaults",
                                _field_table(shielded_fields, provenance),
                            ),
                            height=_height(shielded_fields),
                        )
                    ],
                    conditional=_hide_for_beginner(),
                )
            )

    # --- Assistant tab (FR-6/FR-6b + FR-8): capped-tail transcript (all) + Loki depth (hidden Beginner) --
    if view is not None and getattr(view, "has_snapshot", False):
        snap = view.snapshot
        assistant_tab = TabsLayoutTab(
            title="Assistant",
            layout=RowsLayout(
                rows=[
                    RowsLayoutRow(
                        title="Session transcript",
                        items=[
                            GridItem(
                                element=_add("Assistant — session transcript", _transcript_markdown(snap)),
                                height=16,
                            )
                        ],
                    ),
                    # FR-8: the full-depth Loki panel is an advanced surface — hidden for Beginner.
                    RowsLayoutRow(
                        title="Full Transcript",
                        items=[
                            GridItem(
                                element=_add_panel(
                                    _logs_panel(0, "Full Transcript (Loki)", _transcript_logql(snap.session_id))
                                ),
                                height=12,
                            )
                        ],
                        conditional=_hide_for_beginner(),
                    ),
                ]
            ),
        )
    else:
        hint = (
            view.assistant_message()
            if view is not None and view.assistant_message()
            else "No session yet — run `startd8 kickoff chat` to begin."
        )
        assistant_tab = TabsLayoutTab(
            title="Assistant",
            items=[GridItem(element=_add("Assistant", f"_snapshot — not a live agent._\n\n{hint}"), height=6)],
        )

    # --- Proposals tab (FR-7 + FR-8): full table (non-Beginner) + simplified (Beginner) — OQ-3 --------
    if view is not None and getattr(view, "proposals", ()):  # non-empty
        proposals_tab = TabsLayoutTab(
            title="Proposals",
            layout=RowsLayout(
                rows=[
                    RowsLayoutRow(
                        title="Proposals",
                        items=[
                            GridItem(
                                element=_add("Proposals — awaiting confirmation", _proposals_markdown(view)),
                                height=12,
                            )
                        ],
                        conditional=_hide_for_beginner(),
                    ),
                    RowsLayoutRow(
                        title="Recommendations",
                        items=[
                            GridItem(
                                element=_add("Proposals — recommendations", _proposals_markdown_simple(view)),
                                height=10,
                            )
                        ],
                        conditional=show_when_variable("audience", "beginner"),
                    ),
                ]
            ),
        )
    else:
        msg = (
            view.proposals_message()
            if view is not None and view.proposals_message()
            else "No proposals awaiting confirmation."
        )
        proposals_tab = TabsLayoutTab(
            title="Proposals",
            items=[
                GridItem(
                    element=_add(
                        "Proposals — awaiting confirmation",
                        f"_The loop recommends; you confirm. This board never acts._\n\n{msg}",
                    ),
                    height=12,
                )
            ],
        )

    layout = TabsLayout(
        tabs=[
            TabsLayoutTab(title="Status", layout=RowsLayout(rows=status_rows)),
            assistant_tab,
            proposals_tab,
        ]
    )

    return emit_v2_dashboard(
        name=workbook_v2_uid(project),
        title=f"{project} — Digital Project Workbook (dynamic)",
        description=(
            "Audience-personalized v2 dynamic agentic cockpit — Status / Assistant / Proposals tabs "
            "mirror the kickoff agentic session read-only (no live backend). Flip the `audience` "
            "variable to switch persona in-browser (no regeneration, no write)."
        ),
        tags=["portal", "kickoff", WORKBOOK_TAG, "dynamic", project],
        variables=[CustomVariable(name="audience", options=_AUDIENCES, current=token)],
        elements=elements,
        layout=layout,
    )
