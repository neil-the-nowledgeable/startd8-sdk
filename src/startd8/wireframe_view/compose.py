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

from ..wireframe.describe import describe, describe_summary
from ..wireframe.plan import WireframePlan
from ..wireframe.render import SCHEMA_VERSION, WIREFRAME_META, footer_lines

# FR-AUD-C1 banned register (R1-F7), word-boundary matched so domain names ("identity", "AiCall") don't
# false-trip. A plan item whose LABEL carries this jargon (e.g. "FastAPI app", "export endpoints") is
# infrastructure the non-technical reader shouldn't see — it is flagged `technical` and hidden from the
# end_user render (the datum still rides in the embed for the architect voice). SINGLE SOURCE for the
# ban — the acceptance test imports this same matcher.
_JARGON_RE = re.compile(
    r"\b(?:entit(?:y|ies)|cruds?|schemas?|prisma|manifests?|cascades?|fastapi|"
    r"endpoints?|openapi|htmx|foreign[- ]keys?|ai pass(?:es)?)\b",
    re.IGNORECASE,
)


def has_jargon(text: str) -> bool:
    """True if *text* contains an FR-AUD-C1 banned term (word-boundary). The one ban matcher (R1-F7)."""
    return bool(_JARGON_RE.search(text or ""))


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


def _item_view(section_key: str, item) -> dict:
    """One outline item + its mockup view-model where the composer can structure it (forms today)."""
    mockup = None
    if section_key == "forms":
        parsed = parse_form_detail(item.detail)
        if parsed is not None:
            mockup = {"kind": "form", "entity": _form_entity(item.label), **parsed}
    return {
        "label": item.label,
        "status": item.status,
        "detail": item.detail,
        "paths": list(item.paths),
        "mockup": mockup,
        # R1-F7: an item whose label is infrastructure jargon is hidden from the end_user render.
        "technical": has_jargon(item.label),
    }


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
    return " · ".join((
        _plural(shape.get("entities", 0), "thing") + " tracked",
        _plural(shape.get("pages", 0), "screen"),
        _plural(shape.get("views", 0), "combined view"),
        _plural(shape.get("ai_passes", 0), "automatic helper"),
    ))


# Item statuses that mean "this still needs the author's input" — the computed floor under NEED (R1-F1).
GAP_STATUSES = {"not_defined", "placeholder", "invalid"}


def _plain_status(counts: dict) -> str:
    """A jargon-free health line: reassure when clean, name the gaps in plain words when not."""
    if sum(v for v in counts.values() if isinstance(v, int)) == 0:
        # R1-F6: an empty plan must NOT read "nothing missing or broken" — that is false reassurance
        # to a first-time author (FR-AUD-C4). Say it's empty instead.
        return "Nothing's been set up yet — this project still looks empty."
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
    plan: WireframePlan, *, role: str = "architect", fluency: str = "intermediate"
) -> dict:
    """Pure, deterministic, JSON-safe view-model for the wireframe-visual preview (FR-WV-6).

    ``role``/``fluency`` select the audience variant of the narration (FR-AUD); they change ONLY the
    wording — the shape, items, statuses, and mockups are identical across audiences (FR-AUD-4). The
    default ``("architect", "intermediate")`` resolves to base narration, byte-identical."""
    counts, shape_line, content, readiness = footer_lines(plan)
    summary_narr = describe_summary(plan, role=role, fluency=fluency) or {}

    sections = []
    for s in plan.sections:
        narr = describe(s, plan, role=role, fluency=fluency)  # audience-keyed; None if unnarrated
        sections.append({
            "key": s.key,
            "title": (narr.get("title") if narr else None) or s.title,  # FR-AUD title override, else data
            "status": s.status,
            "consequence": s.consequence,
            "narration": narr,
            "items": [_item_view(s.key, it) for it in s.items],
            # R1-F1: the computed floor under NEED — items the plan itself flags as not-yet-provided
            # (not_defined / placeholder / invalid). Authored `need` prose layers on top; this ensures
            # a real gap is never silently under-reported by relying on authored text alone.
            "need_items": [it.label for it in s.items if it.status in GAP_STATUSES],
        })

    return {
        "project_root": plan.project_root,  # provenance in the embed only — NOT rendered to end_user (R2-F1)
        "app_name": _app_name(plan),        # the app's own name for the masthead
        "schema_version": SCHEMA_VERSION,
        "audience": {"role": role, "fluency": fluency},  # FR-AUD: which voice this view-model speaks
        "summary": {
            # The inverted-pyramid band — same text the terminal footer renders (FR-WV-2), plus the
            # structured figures behind it (for badges) and the authored meaning (FR-WV-5 / FR-DL-12).
            # Architect tool-meta (WIREFRAME_META = process framing) is NEVER shown to the end_user (R2-F1);
            # the end_user gets a benefit-first, actionable intro instead (headline/lead/steps, FR-AUD-C4/R2-F2).
            "meta": summary_narr.get("meta") or (list(WIREFRAME_META) if role == "architect" else []),
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
            "why": summary_narr.get("why", ""),
            "do": summary_narr.get("do", ""),
        },
        "sections": sections,
    }
