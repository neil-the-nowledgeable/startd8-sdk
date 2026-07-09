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


def build_workbook_v2(
    state: Any,
    project: str,
    *,
    audience: Any = None,
    provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the audience-personalized **v2 dynamic** Workbook board (FR-8/FR-9).

    ``audience`` is the resolved ``KickoffAudience`` (from ``resolve_audience_preference(root).value``) —
    it seeds only the variable's ``current`` default. ``provenance`` is the ``load_ledger`` entry map;
    its ``audience-default:*`` shields drive the surface knob + the 🛡️ badge. Pure + deterministic.
    """
    provenance = provenance or {}
    token = _audience_token(audience)
    shielded = {vp for vp, e in provenance.items() if _is_audience_default(e)}

    by_manifest: Dict[str, List[Any]] = {}
    for f in state.fields:
        by_manifest.setdefault(f.manifest, []).append(f)

    elements: Dict[str, Any] = {}
    rows: List[RowsLayoutRow] = []
    counter = {"n": 0}

    def _add(title: str, content: str) -> str:
        counter["n"] += 1
        key = f"panel-{counter['n']}"
        elements[key] = text_panel(counter["n"], title, content)
        return key

    # Disclosure (OQ-6): Beginner plain-language intro + standard intro, conditionally rendered.
    rows.append(
        RowsLayoutRow(
            title="Overview",
            items=[
                GridItem(element=_add("Getting Started", _INTRO_BEGINNER), height=8)
            ],
            conditional=show_when_variable("audience", "beginner"),
        )
    )
    rows.append(
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

        rows.append(
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
            rows.append(
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

    return emit_v2_dashboard(
        name=workbook_v2_uid(project),
        title=f"{project} — Digital Project Workbook (dynamic)",
        description=(
            "Audience-personalized v2 dynamic Workbook — flip the `audience` variable to switch persona "
            "in-browser (no regeneration, no write). Era-2 successor to the classic Workbook."
        ),
        tags=["portal", "kickoff", WORKBOOK_TAG, "dynamic", project],
        variables=[CustomVariable(name="audience", options=_AUDIENCES, current=token)],
        elements=elements,
        layout=RowsLayout(rows=rows),
    )
