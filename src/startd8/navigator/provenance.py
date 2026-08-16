"""Chrome provenance — trace each apex/chrome element of a navigator view to its origin.

Kagami audit surface: a rendered view's chrome (eyebrow · headline · summary meta · why · do · status
band · shape band · legend · sections) must each reflect a real source — a RenderProfile field, a
computed aggregate, or the node data — never orphan hand-drawn text. This maps element → origin →
value so the origin audit can flag any chrome that has no source (an orphan the mirror shouldn't show).
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ..wireframe.plan import WireframePlan
from ..wireframe.profile import RenderProfile
from ..wireframe.shape_dialect import format_shape_line, format_status_counts_line
from .models import Node


def _distinct(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def chrome_provenance(
    nodes: Sequence[Node], plan: WireframePlan, profile: RenderProfile
) -> List[Dict[str, Any]]:
    """Each apex/chrome element → its origin descriptor + rendered value (present flag = has a source)."""
    p = profile
    cats = _distinct((n.category or "uncategorized") for n in nodes)
    keys = [n.key for n in nodes]
    rows = [
        ("eyebrow",      "profile.eyebrow",                                          p.eyebrow),
        ("headline",     "profile.headline",                                         p.headline),
        ("doc_title",    "profile.title",                                            p.title),
        ("summary_meta", "profile.summary_meta (authored in the source module)",     " / ".join(p.summary_meta)),
        ("why",          "profile.why",                                              p.why),
        ("do",           "profile.do",                                               p.do),
        ("status_band",  "computed ← plan.status_counts (per-node provenance/status)", format_status_counts_line(plan.status_counts)),
        ("shape_band",   "computed ← plan.shape",                                    format_shape_line(plan.shape)),
        ("legend",       "profile.statuses[].meaning",                               " · ".join(s.meaning for s in p.statuses)),
        ("section_lead", "profile.section_lead",                                     p.section_lead),
        ("sections",     "grouped ← node.category",                                  ", ".join(cats)),
        ("node_keys",    f"node.key ({len(keys)} nodes from the source)",            ", ".join(keys[:6]) + (" …" if len(keys) > 6 else "")),
    ]
    return [{"element": e, "origin": o, "value": v, "present": bool(str(v).strip())} for e, o, v in rows]
