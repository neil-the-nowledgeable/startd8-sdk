"""M-WV0 — the wireframe-visual view-model composer (FR-WV-2/3/5/9).

``compose(plan)`` is a pure, deterministic function of the ``WireframePlan`` producing a JSON-safe
view-model: the inverted-pyramid summary band (reusing ``footer_lines`` — FR-WV-2), the section outline
mapped 1:1 to ``plan.sections`` (FR-WV-3), the authored per-section narration (reusing ``describe`` /
``describe_summary`` — FR-WV-5), and a structured form field-skeleton parsed from each form item's
``detail`` prose (FR-WV-9). Nothing is regenerated (Mottainai) and nothing is fabricated: an
unparseable ``detail`` yields ``mockup=None`` and the raw ``detail`` is preserved for the renderer.

The M-WV1 HTML shell embeds this view-model as escape-first JSON; the M-WV2/M-WV3 client renderers draw
the outline and the lo-fi mockups from it. No LLM (Hitsuzen).
"""
from __future__ import annotations

import re
from typing import Optional

from ..wireframe.delivery_roles import effective_voice, label_for, lens_for
from ..wireframe.describe import describe, describe_summary
from ..wireframe.plan import WireframePlan
from ..wireframe.profile import RenderProfile
from ..wireframe.render import SCHEMA_VERSION, WIREFRAME_META, footer_lines

# REQ-04: the audience × fluency data-layer lenses live in one shared module now (node_lenses.py) so
# every renderer inherits them without forking. compose delegates — no copy remains here (Kagami / FR-5).
from .node_lenses import (  # noqa: F401  (re-exported names read by the template/tests)
    GAP_STATUSES,
    HONEST_SKIP_ROUTES,
    _display_label,
    _is_gap_item,
    apply_section_lenses,
    has_jargon,
)

# AR-3: which form fields are drawn as a multi-line text area (vs a single-line box). This was a regex
# living inside the HTML renderer; lifting it into the composer makes the mockup view-model self-sufficient
# — any surface (a live app, the portal) can draw the same sketch from ``--view-json`` without re-deriving
# it. SINGLE SOURCE for the heuristic (the template reads ``mockup.multiline``, it no longer guesses).
_MULTILINE_RE = re.compile(r"summary|description|notes|body|content|bio|context", re.IGNORECASE)


def _multiline_fields(shown: list) -> list:
    """The subset of *shown* form fields that render as a text area (long-form free text)."""
    return [f for f in shown if _MULTILINE_RE.search(f)]


def parse_form_detail(detail: str) -> Optional[dict]:
    """Parse a forms-section item ``detail`` into a structured field skeleton (FR-WV-9).

    Matches the exact string ``plan._forms_section`` emits::

        fields: a, b, c [| omitted — server-managed: x, y[; owned: z]] [| help: n/m[, intro]] [| on_create: T]

    Returns ``{"shown", "omitted": {"server_managed", "owned"}, "help", "on_create"}`` — or ``None`` when
    ``detail`` is not a forms field-list. Degrade-never-fabricate: on anything unexpected the caller keeps
    the raw ``detail`` rather than inventing fields.
    """
    if not detail.startswith("fields:"):
        return None
    shown: list[str] = []
    omitted = {"server_managed": [], "owned": []}
    help_text: Optional[str] = None
    on_create: Optional[str] = None

    for seg in (s.strip() for s in detail.split(" | ")):
        if seg.startswith("fields:"):
            body = seg[len("fields:"):].strip()
            shown = [] if body == "(none)" else [f.strip() for f in body.split(",") if f.strip()]
        elif seg.startswith("omitted"):
            # `omitted — <bits>` (em dash); tolerate a hyphen too. Bits joined by "; ".
            body = seg.split("—", 1)[-1] if "—" in seg else seg.split("-", 1)[-1]
            for grp in body.split(";"):
                grp = grp.strip()
                if grp.startswith("server-managed:"):
                    omitted["server_managed"] = _csv(grp[len("server-managed:"):])
                elif grp.startswith("owned:"):
                    omitted["owned"] = _csv(grp[len("owned:"):])
        elif seg.startswith("help:"):
            help_text = seg[len("help:"):].strip()
        elif seg.startswith("on_create:"):
            on_create = seg[len("on_create:"):].strip()

    return {"shown": shown, "omitted": omitted, "help": help_text, "on_create": on_create}


def _csv(text: str) -> list[str]:
    return [f.strip() for f in text.split(",") if f.strip()]


def _form_entity(label: str) -> str:
    """"Profile create/edit form" -> "Profile" (degrade to the raw label if the suffix is absent)."""
    for suffix in (" create/edit form", " form"):
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label


def _entity_columns(plan: WireframePlan) -> dict:
    """LH-1: each entity's user-facing columns, harvested from the forms section (fields already parsed
    from schema.prisma) — so a list mockup can show REAL columns, not a generic skeleton. Keyed by entity."""
    cols: dict[str, list] = {}
    for s in plan.sections:
        if s.key == "forms":
            for it in s.items:
                parsed = parse_form_detail(it.detail)
                if parsed is not None:
                    cols[_form_entity(it.label)] = parsed["shown"]
    return cols


def _item_view(section_key: str, item, role: str = "architect", entity_cols: Optional[dict] = None) -> dict:
    """One outline item + its mockup view-model where the composer can structure it (forms + lists)."""
    mockup = None
    if section_key == "forms":
        parsed = parse_form_detail(item.detail)
        if parsed is not None:
            # AR-3: carry the multi-line-field marker as data so any renderer draws the same sketch.
            mockup = {"kind": "form", "entity": _form_entity(item.label),
                      "multiline": _multiline_fields(parsed["shown"]), **parsed}
    elif section_key == "entities" and entity_cols and entity_cols.get(item.label):  # LH-1: list mockup
        mockup = {"kind": "list", "entity": item.label, "columns": entity_cols[item.label]}
    view = {
        "label": _display_label(item.label, role),  # user-data names kept; structural labels plain-ified
        "status": item.status,
        "detail": item.detail,
        "paths": list(item.paths),
        "mockup": mockup,
        # R1-F7: an item whose label is infrastructure jargon is hidden from the end_user render.
        "technical": has_jargon(item.label),
    }
    # FR-2 / R1-F2: optional Node grounding — omit when empty so app-path JSON keyset is unchanged.
    key = getattr(item, "key", "") or ""
    if key:
        view["key"] = key
    lives = getattr(item, "lives", ()) or ()
    if lives:
        view["lives"] = [
            {"type": ev.type, "ref": ev.ref, **({"note": ev.note} if getattr(ev, "note", "") else {})}
            for ev in lives
        ]
    confidence = getattr(item, "confidence", None)
    if confidence is not None:
        view["confidence"] = confidence
    ships_when = getattr(item, "ships_when", "") or ""
    if ships_when:
        view["ships_when"] = ships_when
    was = getattr(item, "was", ()) or ()
    if was:
        view["was"] = list(was)
    route_state = getattr(item, "route_state", "") or ""
    if route_state:
        view["route_state"] = route_state
    prompts = getattr(item, "approve_prompts", ()) or ()
    if prompts:
        view["approve_prompts"] = list(prompts)
    meta = getattr(item, "meta", "") or ""
    if meta:
        view["meta"] = meta
    return view


def _app_name(plan: WireframePlan) -> str:
    """The app's own name for the end-user masthead (R2-F1: never the filesystem path). Reads the
    scaffold `app:` item; falls back to the project folder name (a plain word, not an absolute path)."""
    for s in plan.sections:
        if s.key == "scaffold":
            for it in s.items:
                if it.label.lower().startswith("app:"):
                    name = it.label.split(":", 1)[1].strip()
                    if name:
                        return name
    base = str(plan.project_root).rstrip("/").rsplit("/", 1)[-1]
    return base or "your app"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _plain_shape(shape: dict) -> str:
    """A jargon-free restatement of the shape counts for the end-user band (FR-AUD gap-3, deterministic)."""
    from ..wireframe.shape_dialect import is_app_cascade_shape

    if not is_app_cascade_shape(shape):
        parts = []
        if "nodes" in shape:
            parts.append(_plural(int(shape.get("nodes") or 0), "node"))
        if "sections" in shape:
            parts.append(_plural(int(shape.get("sections") or 0), "section"))
        return " · ".join(parts) if parts else "No nodes yet."
    return " · ".join((
        _plural(shape.get("entities", 0), "thing") + " tracked",
        _plural(shape.get("pages", 0), "screen"),
        _plural(shape.get("views", 0), "combined view"),
        _plural(shape.get("ai_passes", 0), "automatic helper"),
    ))


def _plain_status(counts: dict) -> str:
    """A jargon-free health line: reassure when clean, name the gaps in plain words when not."""
    if sum(v for v in counts.values() if isinstance(v, int)) == 0:
        # R1-F6: an empty plan must NOT read "nothing missing or broken" — that is false reassurance
        # to a first-time author (FR-AUD-C4). Say it's empty instead.
        return "Nothing's been set up yet — this project still looks empty."
    # Node-domain statuses (requirements / capability navigator).
    if any(
        k in counts
        for k in ("grounded", "spec", "unknown", "awaiting", "excluded", "built", "thin", "deprecated")
    ):
        issues = []
        if counts.get("unknown"):
            issues.append(_plural(counts["unknown"], "requirement") + " without Lives")
        if counts.get("awaiting"):
            issues.append(_plural(counts["awaiting"], "requirement") + " awaiting a decision")
        if counts.get("spec"):
            issues.append(_plural(counts["spec"], "item") + " still in spec")
        if counts.get("thin"):
            issues.append(_plural(counts["thin"], "capability") + " still thin")
        if counts.get("deprecated"):
            issues.append(_plural(counts["deprecated"], "capability") + " deprecated")
        if not issues:
            g = counts.get("grounded", 0) or counts.get("built", 0)
            noun = "requirement" if counts.get("grounded") else "capability"
            return f"{_plural(g, noun)} ready — nothing missing or broken."
        return "Worth a look: " + "; ".join(issues) + "."
    issues = []
    if counts.get("not_defined"):
        issues.append(_plural(counts["not_defined"], "part") + " not set up yet")
    if counts.get("placeholder"):
        issues.append(_plural(counts["placeholder"], "part") + " still rough")
    if counts.get("invalid"):
        issues.append(_plural(counts["invalid"], "part") + " to fix")
    if not issues:
        return "Everything's planned — nothing missing or broken."
    return "Worth a look: " + "; ".join(issues) + "."


def _plain_ready(readiness: dict) -> str:
    """A jargon-free 'can it be built?' line for the end-user band (deterministic)."""
    blocked = [k for k, v in readiness.items() if v != "ready"]
    if not blocked:
        return "Yes — everything's ready to build."
    return "Not yet — a few things need finishing first."


def _plain_content(cov) -> str:
    """A jargon-free reading of the content-authoring rollup for the end-user band (deterministic)."""
    overall = cov.overall
    if overall.total == 0:
        return "No text to write yet."
    pct = round(overall.ratio * 100)
    if pct >= 100:
        return "All the words are written."
    return f"About {pct}% of the words are written — the rest is still yours to write before launch."


def compose(
    plan: WireframePlan,
    *,
    role: str = "architect",
    fluency: str = "intermediate",
    profile: Optional[RenderProfile] = None,
) -> dict:
    """Pure, deterministic, JSON-safe view-model for the wireframe-visual preview (FR-WV-6).

    ``role``/``fluency`` select the audience variant of the narration (FR-AUD); they change ONLY the
    wording — the shape, items, statuses, and mockups are identical across audiences (FR-AUD-4). The
    default ``("architect", "intermediate")`` resolves to base narration, byte-identical.

    ``profile`` (a non-app consumer's RenderProfile) makes the APEX narration profile-driven: the
    summary meta/why/do come from the profile instead of the app-authored ``WIREFRAME_META`` /
    ``describe_summary`` — the single seam that keeps app-build framing off a Node consumer. ``None``
    (the app path) uses the built-in narration, byte-identical.

    EC-4: a delivery-role *kit* (e.g. ``pm``, ``backend-dev``) renders as its declared base voice — the
    ``voice`` (plain/technical) drives the display/reorder decisions below, so a plain-base kit gets the
    plain layout and a technical kit the technical one, while ``describe`` overlays any kit-specific text."""
    voice = effective_voice(role)  # EC-4: the voice this role RENDERS as (end_user | architect)
    counts, shape_line, content, readiness = footer_lines(plan)
    summary_narr = describe_summary(plan, role=role, fluency=fluency) or {}
    entity_cols = _entity_columns(plan)  # LH-1: real columns for list mockups (from the parsed forms)

    sections = []
    for s in plan.sections:
        narr = describe(s, plan, role=role, fluency=fluency)  # audience-keyed; None if unnarrated
        item_views = [_item_view(s.key, it, voice, entity_cols) for it in s.items]
        # Aggregate APPROVE? prompts for the section sign-off export (Phase 2).
        approve_prompts: list[str] = []
        for it in s.items:
            for q in getattr(it, "approve_prompts", ()) or ():
                if q and q not in approve_prompts:
                    approve_prompts.append(q)
        sec_view = {
            "key": s.key,
            "title": (narr.get("title") if narr else None) or s.title,  # FR-AUD title override, else data
            "status": s.status,
            "consequence": s.consequence,
            "narration": narr,
            "items": item_views,
            # R1-F1: the computed floor under NEED — items the plan itself flags as not-yet-provided
            # (not_defined / placeholder / invalid). Authored `need` prose layers on top; this ensures
            # a real gap is never silently under-reported by relying on authored text alone.
            "need_items": [_display_label(it.label, voice) for it in s.items if _is_gap_item(it)],
        }
        if approve_prompts:
            sec_view["approve_prompts"] = approve_prompts
        sections.append(sec_view)

    # REQ-04: the end-user section ordering lens is owned by node_lenses now (presentation only —
    # FR-AUD-4); compose delegates so any renderer gets the same order from one place.
    sections = apply_section_lenses(sections, voice=voice)

    # QW-3: the consolidated "before launch" to-do — every plan-flagged gap across sections, in one list.
    todos = [{"section": sec["title"], "item": it} for sec in sections for it in sec["need_items"]]

    # REQ-18 FR-4: the summary-altitude determinism-% line, appended to the apex meta ONLY when the node
    # corpus declares realization regimes — a graph with no regime data (requirements/capability) appends
    # nothing, so the render is byte-identical (FR-7). Labeled `declared` until REQ-19 (b) grounds it.
    from startd8.navigator.realization import format_determinism_line

    summary_meta = (list(profile.summary_meta) if profile is not None
                    else summary_narr.get("meta") or (list(WIREFRAME_META) if role == "architect" else []))
    _det_line = (format_determinism_line(dict(plan.realization), grounded=plan.realization_grounded)
                 if plan.realization else None)
    if _det_line is not None:
        summary_meta = list(summary_meta) + [_det_line]

    return {
        "project_root": plan.project_root,  # provenance in the embed only — NOT rendered to end_user (R2-F1)
        "app_name": _app_name(plan),        # the app's own name for the masthead
        "schema_version": SCHEMA_VERSION,
        # FR-AUD / EC-4: which role this view-model speaks for, the voice it renders as (plain/technical),
        # and — for a delivery-role kit — its focus lens + label (shown as a banner; "" for a base voice).
        "audience": {"role": role, "fluency": fluency, "voice": voice,
                     "lens": lens_for(role), "label": label_for(role)},
        "todos": todos,                     # QW-3 roll-up (rendered as a banner for end_user)
        "summary": {
            # The inverted-pyramid band — same text the terminal footer renders (FR-WV-2), plus the
            # structured figures behind it (for badges) and the authored meaning (FR-WV-5 / FR-DL-12).
            # Architect tool-meta (WIREFRAME_META = process framing) is NEVER shown to the end_user (R2-F1);
            # the end_user gets a benefit-first, actionable intro instead (headline/lead/steps, FR-AUD-C4/R2-F2).
            # Apex narration seam: a profiled (non-app) consumer supplies its own; else the app default.
            "meta": summary_meta,   # REQ-18 FR-4: base apex meta (+ the determinism line when regime data present)
            "headline": summary_narr.get("headline", ""),
            "lead": summary_narr.get("lead", ""),
            "steps": summary_narr.get("steps", []),
            "closing": summary_narr.get("closing", ""),
            "counts": counts,
            "shape": shape_line,
            "content": content,
            "readiness": readiness,
            "shape_data": dict(plan.shape),
            "status_counts": dict(plan.status_counts),
            "content_completeness": plan.content_coverage.as_dict(),
            "plain_shape": _plain_shape(plan.shape),    # jargon-free band values for end_user (gap-3)
            "plain_status": _plain_status(plan.status_counts),
            "plain_content": _plain_content(plan.content_coverage),
            "plain_ready": _plain_ready(plan.readiness),
            "why": profile.why if profile is not None else summary_narr.get("why", ""),
            "do": profile.do if profile is not None else summary_narr.get("do", ""),
        },
        "sections": sections,
    }
