"""Chrome provenance — trace each apex/chrome element of a navigator view to its origin.

Kagami audit surface: a rendered view's chrome (eyebrow · headline · summary meta · why · do · status
band · shape band · legend · sections) must each reflect a real source — a RenderProfile field, a
computed aggregate, or the node data — never orphan hand-drawn text. This maps element → origin →
value so the origin audit can flag any chrome that has no source (an orphan the mirror shouldn't show).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from ..wireframe.plan import WireframePlan
from ..wireframe.profile import RenderProfile
from ..wireframe.shape_dialect import format_shape_line, format_status_counts_line
from .models import Node, NodeStatus

# An FR local key (``FR-3``, ``FR-IMP-4``) — distinguishes an FR-id query from a file-path query (R8-EB-4).
_FR_ID_RE = re.compile(r"^FR-[0-9A-Za-z-]+$")


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


def _path_of_ref(ref: str) -> str:
    """Strip a ``git:<sha>:<path>`` evidence ref down to its bare path; other refs pass through."""
    if ref.startswith("git:"):
        parts = ref.split(":", 2)
        return parts[2] if len(parts) == 3 else ref
    return ref


def _fr_file_path(fr_node: Node) -> Optional[str]:
    """A representative code file path for a requirement Node (R8-EB-4): its first ``code`` ``Lives:``
    ref, else its first ``Touches:`` path, else any ``Lives:`` ref. ``None`` when the FR grounds to no
    traceable file — an honest not-found rather than an invented path."""
    for ev in getattr(fr_node, "lives", ()) or ():
        if ev.type == "code":
            return _path_of_ref(ev.ref)
    for tok in (fr_node.attributes.get("touches") or "").split(","):
        tok = tok.strip().strip("`")
        if tok:
            return tok
    for ev in getattr(fr_node, "lives", ()) or ():
        return _path_of_ref(ev.ref)
    return None


def pipeline_provenance(
    nodes: Sequence[Node],
    stages: Sequence[Any],
    *,
    query: str,
    requirement_nodes: Optional[Sequence[Node]] = None,
) -> List[Dict[str, Any]]:
    """Trace a delivered artifact back through the pipeline stages to its originating requirement (FR-6).

    A **sibling** of :func:`chrome_provenance` in the same module (Mottainai — D-4): the row schema is
    ``{element, stage, origin, value, present}`` (adds ``stage``, keeps ``value`` for parity).

    ``query`` is either a **file path** or a bare **FR id** (``FR-3``) — the D-B "FR id or file path"
    contract (R8-EB-4). An FR-id query is resolved against ``requirement_nodes`` (from
    ``nodes_from_requirements``) to the FR's representative code file — its first ``code`` ``Lives:``
    ref, else its first ``Touches:`` path — and the trace runs from there; when known, the FR is named
    on the origin (``stage:intent``) row. An FR-id with no ``requirement_nodes`` given, an unknown FR,
    or an FR that grounds to no file yields the not-found row (honest, never an invented path).

    The (resolved) artifact is resolved to its owning stage by **longest-prefix** ``sdk_artifact`` match;
    the walk then follows the DEPENDS-ON edges upstream to the requirement, emitting one ordered row per
    stage passed through (**including SPEC / un-built stages** so the trace shows the gap — R1-S10). An
    artifact owned by **no** stage yields a single ``present=False`` row (R1-S8). The stage ordinals of
    the returned chain are a subsequence of the FR-1 ordinals, ending at ``stage:intent``.
    """
    stage_by_key = {st.key: st for st in stages}
    node_by_key = {n.key: n for n in nodes}

    # R8-EB-4: an FR-id query resolves to the FR's representative code file before the artifact walk.
    fr_id: Optional[str] = None
    resolved_query = query
    if _FR_ID_RE.match(query.strip()):
        fr_id = query.strip()
        fr_by_key = {n.key: n for n in (requirement_nodes or ())}
        fr_node = fr_by_key.get(fr_id)
        path = _fr_file_path(fr_node) if fr_node is not None else None
        if path is None:
            if requirement_nodes is None:
                reason = f"FR {fr_id}: no requirement corpus provided to resolve an FR-id query"
            elif fr_node is None:
                reason = f"FR {fr_id}: not in the provided requirement corpus"
            else:
                reason = f"FR {fr_id}: grounds to no code Lives:/Touches: path to trace"
            return [{"element": query, "stage": None, "origin": reason, "value": query, "present": False}]
        resolved_query = path

    owner_key = _owning_stage_key(resolved_query, stages)
    if owner_key is None:
        # Unowned artifact → a single not-found row, never an empty chain (R1-S8).
        origin = "no stage owns this artifact (longest-prefix match found none)"
        if fr_id is not None:
            origin = f"FR {fr_id} → {resolved_query}: {origin}"
        return [{
            "element": resolved_query,
            "stage": None,
            "origin": origin,
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
        origin = f"stage {st.ordinal} ({st.compiler_analogue}) — status {status}"
        # Name the originating FR on the requirement-origin (intent) row when resolved from an FR-id.
        if fr_id is not None and key == "stage:intent":
            origin = f"{origin} ← requirement {fr_id} ({resolved_query})"
        rows.append({
            "element": st.sdk_artifact,
            "stage": key,
            "origin": origin,
            "value": st.human_form,
            "present": status != NodeStatus.SPEC,
        })
    return rows
