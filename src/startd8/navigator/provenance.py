"""Chrome provenance — trace each apex/chrome element of a navigator view to its origin.

Kagami audit surface: a rendered view's chrome (eyebrow · headline · summary meta · why · do · status
band · shape band · legend · sections) must each reflect a real source — a RenderProfile field, a
computed aggregate, or the node data — never orphan hand-drawn text. This maps element → origin →
value so the origin audit can flag any chrome that has no source (an orphan the mirror shouldn't show).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..wireframe.plan import WireframePlan
from ..wireframe.profile import RenderProfile
from ..wireframe.shape_dialect import format_shape_line, format_status_counts_line
from .models import Node, NodeStatus


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


def _owning_stage_key(query: str, stages: Sequence[Any]) -> Optional[str]:
    """Resolve a queried artifact path to its owning stage by **longest-prefix** ``sdk_artifact`` match.

    Deterministic when one stage's path is a prefix of another's (the longest wins). Returns the owning
    stage ``key``, or ``None`` when no stage's ``sdk_artifact`` is a prefix of the query (R1-S8).
    """
    q = query.strip().lstrip("./")
    best_key: Optional[str] = None
    best_len = -1
    for st in stages:
        artifact = str(st.sdk_artifact).strip().lstrip("./")
        if q == artifact or q.startswith(artifact.rstrip("/") + "/") or q.startswith(artifact):
            if len(artifact) > best_len:
                best_len = len(artifact)
                best_key = st.key
    return best_key


def pipeline_provenance(
    nodes: Sequence[Node],
    stages: Sequence[Any],
    *,
    query: str,
) -> List[Dict[str, Any]]:
    """Trace a delivered artifact back through the pipeline stages to its originating requirement (FR-6).

    A **sibling** of :func:`chrome_provenance` in the same module (Mottainai — D-4): the row schema is
    ``{element, stage, origin, value, present}`` (adds ``stage``, keeps ``value`` for parity). ``query``
    is an FR id or a file path (D-B — explicit arg). The queried artifact is resolved to its owning stage
    by **longest-prefix** ``sdk_artifact`` match; the walk then follows the DEPENDS-ON edges upstream to
    the requirement, emitting one ordered row per stage passed through (**including SPEC / un-built
    stages** so the trace shows the gap — R1-S10). An artifact owned by **no** stage yields a single
    ``present=False`` row (R1-S8). The stage ordinals of the returned chain are a subsequence of the
    FR-1 ordinals, ending at ``stage:intent`` (the requirement origin).
    """
    stage_by_key = {st.key: st for st in stages}
    node_by_key = {n.key: n for n in nodes}

    owner_key = _owning_stage_key(query, stages)
    if owner_key is None:
        # Unowned artifact → a single not-found row, never an empty chain (R1-S8).
        return [{
            "element": query,
            "stage": None,
            "origin": "no stage owns this artifact (longest-prefix match found none)",
            "value": query,
            "present": False,
        }]

    # Walk upstream along DEPENDS-ON (child_keys) from the owning stage to the requirement (intent).
    ordered: List[str] = []
    seen: set = set()
    cursor: Optional[str] = owner_key
    while cursor is not None and cursor not in seen:
        seen.add(cursor)
        ordered.append(cursor)
        st = stage_by_key.get(cursor)
        # Follow the single upstream dependency edge (the pipeline is a linear spine to intent).
        deps = list(st.child_keys) if st else []
        cursor = deps[0] if deps else None

    # The chain reads requirement → … → artifact; reverse so it walks upstream-to-downstream (intent→owner).
    rows: List[Dict[str, Any]] = []
    for key in reversed(ordered):
        st = stage_by_key[key]
        node = node_by_key.get(key)
        status = node.status if node is not None else NodeStatus.SPEC
        rows.append({
            "element": st.sdk_artifact,
            "stage": key,
            "origin": f"stage {st.ordinal} ({st.compiler_analogue}) — status {status}",
            "value": st.human_form,
            "present": status != NodeStatus.SPEC,
        })
    return rows
