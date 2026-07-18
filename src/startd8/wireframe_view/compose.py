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

from typing import Optional

from ..wireframe.describe import describe, describe_summary
from ..wireframe.plan import WireframePlan
from ..wireframe.render import SCHEMA_VERSION, WIREFRAME_META, footer_lines


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
    }


def compose(plan: WireframePlan) -> dict:
    """Pure, deterministic, JSON-safe view-model for the wireframe-visual preview (FR-WV-6)."""
    counts, shape_line, content, readiness = footer_lines(plan)
    summary_narr = describe_summary(plan) or {}

    sections = [
        {
            "key": s.key,
            "title": s.title,
            "status": s.status,
            "consequence": s.consequence,
            "narration": describe(s, plan),  # {key, what, why, do, next} or None (unnarrated section)
            "items": [_item_view(s.key, it) for it in s.items],
        }
        for s in plan.sections
    ]

    return {
        "project_root": plan.project_root,
        "schema_version": SCHEMA_VERSION,
        "summary": {
            # The inverted-pyramid band — same text the terminal footer renders (FR-WV-2), plus the
            # structured figures behind it (for badges) and the authored meaning (FR-WV-5 / FR-DL-12).
            "meta": list(WIREFRAME_META),  # tool-level what/why/how (FR-SV-13), single-sourced
            "counts": counts,
            "shape": shape_line,
            "content": content,
            "readiness": readiness,
            "shape_data": dict(plan.shape),
            "status_counts": dict(plan.status_counts),
            "content_completeness": plan.content_coverage.as_dict(),
            "why": summary_narr.get("why", ""),
            "do": summary_narr.get("do", ""),
        },
        "sections": sections,
    }
