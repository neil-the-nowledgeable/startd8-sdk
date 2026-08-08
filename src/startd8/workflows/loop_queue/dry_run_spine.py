"""Rundown spine-walk — emit a dry-run ``dry_run_trace`` across a LoopManifest spine (dev-os REQ-03).

A **Rundown** is the temporal twin of the loop-topology graph: given a dev-os LoopManifest
(``loops/schemas/loop-manifest.schema.json``), walk its ``pieces ∪ gates`` in declaration order and emit
one verdict per node — a describe-only "if this loop ran, this stage would be on the path" pass with **zero
side effects**. The verdicts ride the job's existing ``dry_run_trace`` (contextcore ``DryRunVerdict.to_dict()``
shape), so the contextcore navigator ``traceroute`` source + the dev-os VLD render them unchanged.

**Single-source-vocabulary discipline (the triad guard).** The AUTHORITATIVE ``would_act`` vocabulary + the
GAP sentinel live in contextcore (``contracts.dry_run``); startd8 must NOT import contextcore. This module
reuses the startd8-side GUARDED MIRRORS (``DRY_RUN_WOULD_ACT_VALUES``, ``DRY_RUN_GAP_WHAT_CHANGE``), held in
parity by ``tests/.../test_dry_run_parity.py``. It invents no vocabulary.

**``would_act`` is a control-flow verdict** ("would this stage act on the job"), NOT a build-state — the
navigator maps it to the glanceable glyph (yes→built · no→spec · not-mine→thin · GAP→deprecated):

- a spine piece/gate on the path                       → ``yes``      (it would act)
- a piece marked ``config.optional: true`` (orphan-exempt, off the spine edges) → ``not-mine`` (acknowledged
  pass-through — mirrors the manifest's own R1-F1 orphan exemption)
- a **dangling spine edge** endpoint (an ``edges[].from``/``to`` id with no declared node) → a **GAP**
  (received-but-no-verdict hole, ``received=False``) — the honest open-loop row.

Label provenance (REQ-03 FR-5): each verdict's ``what_change`` sources from the node's ``role`` (the
manifest's intuitive label — ``measure``, ``design-compose``, …), falling back to ``id``; the auto-generator
stays deferred (REQ-03 NR-4). ``inputs``/``outputs`` are the incoming/outgoing edge contracts, so the
navigator's per-node attribute table shows the spine wiring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Union

import yaml

from .models import DRY_RUN_GAP_WHAT_CHANGE, DRY_RUN_WOULD_ACT_VALUES

# The mirrored vocabulary, named for readability (indices match the contextcore enum order).
_WOULD_ACT_YES, _WOULD_ACT_NO, _WOULD_ACT_NOT_MINE = DRY_RUN_WOULD_ACT_VALUES


def _verdict(
    stage_id: str,
    would_act: str,
    what_change: str,
    *,
    inputs: List[str],
    outputs: List[str],
    why: str,
) -> Dict[str, Any]:
    """One ``DryRunVerdict.to_dict()``-shaped record (parity-guarded shape; no contextcore import)."""
    return {
        "stage_id": stage_id,
        "received": True,
        "would_act": would_act,
        "what_change": what_change,
        "inputs": inputs,
        "outputs": outputs,
        "downstream_handoff": None,
        "why": why,
    }


def _gap_verdict(stage_id: str) -> Dict[str, Any]:
    """A GAP hop — an ``edges[]`` endpoint with no declared node. Mirrors ``DryRunVerdict.gap()`` exactly
    (``received=False``, ``would_act='no'``, the guarded sentinel ``what_change``) so ``is_gap()`` detects it."""
    return {
        "stage_id": stage_id,
        "received": False,
        "would_act": _WOULD_ACT_NO,
        "what_change": DRY_RUN_GAP_WHAT_CHANGE,
        "inputs": [],
        "outputs": [],
        "downstream_handoff": None,
        "why": "spine edge references a node that is not declared in pieces ∪ gates (dangling hop)",
    }


def spine_verdicts(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Walk a LoopManifest dict → an ordered list of ``dry_run_trace`` verdict dicts (the Rundown).

    Deterministic: nodes are emitted in declaration order (pieces, then ``gates[]``) — the same node ordering
    as the dev-os topology-of-record renderer (``loops/scripts/render_node_graph.py``: ``nodes = pieces ∪
    gates``), so the temporal Rundown and the spatial graph agree by construction. GAP rows (dangling edge
    endpoints) are appended last, once per missing id, in first-seen order.
    """
    pieces = [p for p in (manifest.get("pieces") or []) if isinstance(p, dict)]
    gates = [g for g in (manifest.get("gates") or []) if isinstance(g, dict)]
    edges = [e for e in (manifest.get("edges") or []) if isinstance(e, dict)]

    # Edge wiring, indexed by node id → the contracts flowing in/out (shown in the navigator attr table).
    incoming: Dict[str, List[str]] = {}
    outgoing: Dict[str, List[str]] = {}
    for e in edges:
        src, dst, contract = e.get("from"), e.get("to"), e.get("contract") or "edge"
        if src and dst:
            outgoing.setdefault(src, []).append(f"{dst}:{contract}")
            incoming.setdefault(dst, []).append(f"{src}:{contract}")

    verdicts: List[Dict[str, Any]] = []
    declared_ids = set()

    for p in pieces:
        node_id = p.get("id")
        if not node_id:
            continue
        declared_ids.add(node_id)
        role = p.get("role") or node_id
        kind = p.get("kind") or "piece"
        optional = bool((p.get("config") or {}).get("optional"))
        if optional:
            would_act = _WOULD_ACT_NOT_MINE
            why = f"dry-run spine: '{role}' is optional (orphan-exempt, off the spine edges) — pass-through"
        else:
            would_act = _WOULD_ACT_YES
            why = f"dry-run spine: '{role}' ({kind}) is on the loop spine and would act"
        verdicts.append(
            _verdict(
                node_id,
                would_act,
                f"{role} ({kind})",
                inputs=incoming.get(node_id, []),
                outputs=outgoing.get(node_id, []),
                why=why,
            )
        )

    for g in gates:
        node_id = g.get("id")
        if not node_id:
            continue
        declared_ids.add(node_id)
        kind = g.get("kind") or "gate"
        verdicts.append(
            _verdict(
                node_id,
                _WOULD_ACT_YES,
                f"{node_id} ({kind})",
                inputs=incoming.get(node_id, []),
                outputs=outgoing.get(node_id, []),
                why=f"dry-run spine: gate '{node_id}' ({kind}) is a spine decision point and would act",
            )
        )

    # Honest GAP detection: any edge endpoint that is not a declared node is a hole in the spine.
    seen_gaps = set()
    for e in edges:
        for endpoint in (e.get("from"), e.get("to")):
            if endpoint and endpoint not in declared_ids and endpoint not in seen_gaps:
                seen_gaps.add(endpoint)
                verdicts.append(_gap_verdict(endpoint))

    return verdicts


def load_manifest(path: Union[str, Path]) -> Dict[str, Any]:
    """Read + parse a LoopManifest YAML. Raises ``FileNotFoundError`` / ``ValueError`` (fail-loud).

    Malformed YAML is normalized to ``ValueError`` (not a raw ``yaml.YAMLError``) so a single
    ``except (FileNotFoundError, ValueError)`` at the caller (the ``wloop rundown`` CLI) covers every
    bad-manifest case with the same clean exit — a raw ``YAMLError`` would otherwise escape as a traceback.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"LoopManifest not found: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ValueError(f"LoopManifest at {p} is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"LoopManifest at {p} did not parse to a mapping (got {type(data).__name__})")
    return data


def spine_verdicts_from_path(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Convenience: ``load_manifest`` → ``spine_verdicts``."""
    return spine_verdicts(load_manifest(path))
