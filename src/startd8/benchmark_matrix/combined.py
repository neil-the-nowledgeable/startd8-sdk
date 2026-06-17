"""Cross-run cell merge for the combined scoreboard (M1 — CS-1/2/3/4/5/6/16).

`merge_runs(run_dirs)` loads the per-cell results from several benchmark run directories and resolves
them into **one canonical cell set** — the input to the combined scorecard renderer (M3). It enforces
the method-parity gate (CS-5/6) and a deterministic supersedence rule (CS-3), and records per-cell
provenance (CS-2) so every consolidated number traces to the run + cell it came from.

**Priority order matters.** `run_dirs` are passed most-canonical first. The first dir is the *anchor*:
its scoring-method signature defines the mergeable group (runs with a different signature are excluded —
so a naive calibration board drops out of a shadow+expose merge), and it wins supersedence ties.

**Supersedence (CS-3), per cell key `(service, model, repetition)`:**
  1. a cell with a real score (`status == "ok"`) outranks any scoreless cell (`infra_fail` /
     `deps_missing` / `failed` / `timeout`) — this is how a re-run's `ok` OpenAI cell replaces the
     original run's `infra_fail` one;
  2. ties break by **caller priority** (earlier dir wins) — explicit and deterministic, so a
     fairness-reclassified run beats its as-run source simply by being listed first.

Tolerant of heterogeneous/partial inputs (CS-16): missing/ malformed cells degrade to a logged skip.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from .method import MethodSignature, method_signature
from .runner import CellResult

CELLS_FILE = "cells.json"
CELLS_BAK = "cells.json.bak"

CellKey = Tuple[str, str, int]


def _status_rank(status: str) -> int:
    """Scored cells outrank scoreless ones; among scoreless, caller priority decides (not status)."""
    return 1 if status == "ok" else 0


def _cell_key(c: CellResult) -> CellKey:
    # CS-4: the discrete fields are authoritative — never parse cell_id (its spec-hash prefix differs
    # per run, so cell_id is NOT a stable cross-run key).
    return (c.service, c.model, c.repetition)


@dataclass(frozen=True)
class CellCandidate:
    run: str
    priority: int           # caller order index (lower = higher priority)
    cell: CellResult


@dataclass
class CellProvenance:
    """Why a particular cell won its key (CS-2/CS-11)."""
    cell_key: CellKey
    winner_run: str
    winner_cell_id: str
    winner_status: str
    reason: str
    losers: List[Tuple[str, str, str]] = field(default_factory=list)  # (run, cell_id, status)


@dataclass
class RunInfo:
    run: str
    signature: MethodSignature
    cells_file: str         # "cells.json" | "cells.json.bak"
    n_cells: int
    included: bool
    reason: str             # anchor / method match / excluded: …


@dataclass
class MergeResult:
    cells: List[CellResult]
    provenance: Dict[CellKey, CellProvenance]
    runs: List[RunInfo]
    anchor_method: str
    anchor_parity: tuple
    warnings: List[str] = field(default_factory=list)

    @property
    def included_runs(self) -> List[RunInfo]:
        return [r for r in self.runs if r.included]

    @property
    def excluded_runs(self) -> List[RunInfo]:
        return [r for r in self.runs if not r.included]


def _load_cells(run_dir: Path, *, prefer_bak: bool = False) -> Tuple[List[CellResult], str]:
    name = CELLS_BAK if (prefer_bak and (run_dir / CELLS_BAK).exists()) else CELLS_FILE
    try:
        raw = json.loads((run_dir / name).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - CS-16: a missing/malformed cells file is a degrade
        return [], name
    out: List[CellResult] = []
    for d in raw if isinstance(raw, list) else []:
        try:
            out.append(CellResult.from_dict(d))
        except Exception:  # noqa: BLE001 - one bad cell shouldn't sink the merge
            continue
    return out, name


def merge_runs(run_dirs, *, prefer_bak: bool = False, prealigned=None) -> MergeResult:
    """Merge cells across ``run_dirs`` (priority order, anchor first) into one canonical set.

    Returns a :class:`MergeResult` with the merged cells, per-cell provenance, per-run inclusion
    decisions, and any warnings. Never raises on a malformed/partial input dir (CS-16).

    ``prealigned`` (optional ``{run_name: List[CellResult]}``) supplies method-aligned cells for a run
    from the M2 alignment step (CS-15): such a run is included with those cells **regardless of its
    on-disk signature** (alignment already brought it to the target method), bypassing the parity gate
    for it only. Runs not in ``prealigned`` follow the normal parity gate below.
    """
    dirs = [Path(d) for d in run_dirs]
    prealigned = prealigned or {}
    if not dirs:
        return MergeResult([], {}, [], "unknown", ("unknown", None, None), ["no run dirs given"])

    sigs = [method_signature(d) for d in dirs]
    anchor_sig = sigs[0]
    anchor = anchor_sig.parity_key
    warnings: List[str] = []
    if anchor_sig.scoring_method in ("naive", "unknown"):
        warnings.append(
            f"anchor run '{dirs[0].name}' has scoring_method={anchor_sig.scoring_method!r} — "
            "list the canonical scored run first?"
        )

    runs: List[RunInfo] = []
    candidates: Dict[CellKey, List[CellCandidate]] = {}
    for prio, (d, sig) in enumerate(zip(dirs, sigs)):
        if d.name in prealigned:  # CS-15: alignment supplied method-aligned cells → include, bypass gate
            cells = prealigned[d.name]
            reason = "anchor (aligned)" if prio == 0 else "aligned"
            for c in cells:
                candidates.setdefault(_cell_key(c), []).append(CellCandidate(d.name, prio, c))
            runs.append(RunInfo(d.name, sig, "<aligned:in-memory>", len(cells), True, reason))
            continue
        included = sig.parity_key == anchor
        if included:
            cells, cfile = _load_cells(d, prefer_bak=prefer_bak)
            reason = "anchor" if prio == 0 else "method match"
            for c in cells:
                candidates.setdefault(_cell_key(c), []).append(CellCandidate(d.name, prio, c))
        else:
            cells, cfile = [], CELLS_FILE
            reason = f"excluded: method {sig.scoring_method} != anchor {anchor_sig.scoring_method}"
        runs.append(RunInfo(d.name, sig, cfile, len(cells), included, reason))

    merged: List[CellResult] = []
    prov: Dict[CellKey, CellProvenance] = {}
    for key, cands in candidates.items():
        ranked = sorted(cands, key=lambda x: (-_status_rank(x.cell.status), x.priority))
        win = ranked[0]
        if len(ranked) == 1:
            reason = "sole source"
        elif _status_rank(win.cell.status) > _status_rank(ranked[1].cell.status):
            reason = f"status {win.cell.status} > {ranked[1].cell.status}"
        else:
            reason = f"caller priority (run #{win.priority}: {win.run})"
        merged.append(win.cell)
        prov[key] = CellProvenance(
            cell_key=key, winner_run=win.run, winner_cell_id=win.cell.cell_id,
            winner_status=win.cell.status, reason=reason,
            losers=[(c.run, c.cell.cell_id, c.cell.status) for c in ranked[1:]],
        )

    return MergeResult(merged, prov, runs, anchor_sig.scoring_method, anchor, warnings)
