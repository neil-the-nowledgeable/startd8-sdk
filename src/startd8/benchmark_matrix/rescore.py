"""Post-hoc, $0 re-scoring of a completed benchmark run (NEXT_STEPS #2).

The scoring layer (compile gate, structural composite, lint) evolves *after* a run
has executed — e.g. the Node `node --check` fallback (commit 0d1bae37) landed hours
after the round-1 run finished, so that run scored every nodejs cell as *degraded*
even though the gate now fires cleanly on the generated `.js` files.

Re-running the matrix would cost real LLM money to regenerate identical artifacts.
Instead, this module re-scores the **already-generated** files sitting in each cell's
sandbox directory: re-run the compile gate / composite on disk, recompute the FR-17
aggregate, and rebuild the FR-15 leaderboard. No model is invoked — $0.

It only re-scores cells with ``status == ok`` (cells that actually produced a file);
infra-failed / budget-skipped / timed-out cells carry no artifact to re-score and are
left untouched. The model's *structural* score is taken as fixed (the disk artifact is
unchanged); only the compile/lint terms are recomputed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .aggregate import DEFAULT_PASS_THRESHOLD, aggregate_cells, build_matrix_markdown
from .runner import (
    STATUS_OK,
    CellResult,
    resolve_generated_file,
    sandbox_dir_name,
)
from .sandbox import SandboxConfig
from .scoring import score_file

# Files written by run_ob_benchmark.py into a run directory.
CELLS_FILE = "cells.json"
AGGREGATE_FILE = "aggregate.json"
LEADERBOARD_FILE = "leaderboard.md"
RUN_SPEC_FILE = "run-spec.json"
SANDBOXES_DIR = "sandboxes"


@dataclass
class CellRescore:
    """What changed (or didn't) for one cell."""
    cell_id: str
    service: str
    model: str
    old_quality: Optional[float]
    new_quality: Optional[float]
    old_compile_ok: Optional[bool]
    new_compile_ok: Optional[bool]
    old_degraded: bool
    new_degraded: bool
    note: str = ""

    @property
    def changed(self) -> bool:
        return (
            self.old_quality != self.new_quality
            or self.old_compile_ok != self.new_compile_ok
            or self.old_degraded != self.new_degraded
        )


@dataclass
class RescoreReport:
    run_dir: Path
    spec_name: str
    spec_hash: str
    cells_total: int
    cells_rescored: int          # had status==ok AND a generated file located
    cells_no_artifact: int       # status==ok but no generated file found (left as-is)
    cells_not_ok: int            # not status==ok — nothing to re-score
    cells: List[CellResult]      # updated in place
    aggregate: Dict
    leaderboard_md: str
    rescores: List[CellRescore] = field(default_factory=list)
    written: bool = False

    @property
    def changes(self) -> List[CellRescore]:
        return [r for r in self.rescores if r.changed]


def _read_spec_meta(run_dir: Path, cells: List[CellResult]) -> tuple[str, str]:
    """(spec_name, spec_hash) for the leaderboard header — from run-spec.json,
    falling back to the spec-hash prefix embedded in cell_id."""
    spec_path = run_dir / RUN_SPEC_FILE
    name, spec_hash = "benchmark", ""
    if spec_path.exists():
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            name = spec.get("name") or name
            spec_hash = spec.get("spec_hash") or ""
        except (ValueError, OSError):
            pass
    if not spec_hash and cells:
        # cell_id == "<spec_hash[:12]>:<service>:<model>:r<rep>"
        spec_hash = cells[0].cell_id.split(":", 1)[0]
    return name, spec_hash


def rescore_run(
    run_dir,
    seeds_dir,
    *,
    cfg: Optional[SandboxConfig] = None,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    run_lint: bool = True,
    write: bool = False,
    backup: bool = True,
) -> RescoreReport:
    """Re-score every ``ok`` cell of a completed run against the current scoring layer.

    Args:
        run_dir: a benchmark run directory (holds cells.json + sandboxes/).
        seeds_dir: the OB seeds dir — used to resolve each service's primary file.
        cfg: sandbox config for the compile gate (defaults to a safe config).
        pass_threshold: FR-17 pass threshold for re-aggregation.
        run_lint: also run the optional lint term (matches the live runner default).
        write: persist the updated cells.json / aggregate.json / leaderboard.md.
        backup: when writing, copy each original to ``<name>.bak`` first (once).

    Returns a :class:`RescoreReport`. Pure read unless ``write=True``.
    """
    from ..languages import LanguageRegistry, resolve_language

    run_dir = Path(run_dir)
    seeds_dir = Path(seeds_dir)
    cells_path = run_dir / CELLS_FILE
    if not cells_path.exists():
        raise FileNotFoundError(f"no {CELLS_FILE} in {run_dir}")

    raw = json.loads(cells_path.read_text(encoding="utf-8"))
    cells = [CellResult.from_dict(d) for d in raw]
    LanguageRegistry.discover()

    rescores: List[CellRescore] = []
    rescored = no_artifact = not_ok = 0

    for c in cells:
        if c.status != STATUS_OK:
            not_ok += 1
            continue
        # Resolve the cell's workdir with its FULL coordinate — leverage (K2) and lead/drafter (K3)
        # are part of sandbox_dir_name, so omitting them would miss on-cell / off-diagonal sandboxes
        # and silently degrade them on re-score (the R3-S4 / R6-S4 round-trip requirement).
        sandbox = run_dir / SANDBOXES_DIR / sandbox_dir_name(
            c.service, c.model, c.repetition,
            leverage=getattr(c, "leverage", "off"),
            lead=getattr(c, "lead", None), drafter=getattr(c, "drafter", None))
        gen = resolve_generated_file(seeds_dir, sandbox, c.service)
        if gen is None:
            no_artifact += 1
            rescores.append(CellRescore(
                cell_id=c.cell_id, service=c.service, model=c.model,
                old_quality=c.quality, new_quality=c.quality,
                old_compile_ok=c.compile_ok, new_compile_ok=c.compile_ok,
                old_degraded=c.degraded, new_degraded=c.degraded,
                note="generated file not found in sandbox — left unchanged",
            ))
            continue

        structural = c.structural_quality if c.structural_quality is not None else c.quality
        profile = resolve_language([str(gen)])
        comp = score_file(gen, profile, cfg=cfg, structural=structural, run_lint=run_lint)

        rec = CellRescore(
            cell_id=c.cell_id, service=c.service, model=c.model,
            old_quality=c.quality, new_quality=comp.value,
            old_compile_ok=c.compile_ok, new_compile_ok=comp.compile_ok,
            old_degraded=c.degraded, new_degraded=comp.degraded,
            note=comp.note,
        )
        c.quality = comp.value
        c.compile_ok = comp.compile_ok
        c.degraded = comp.degraded
        rescored += 1
        rescores.append(rec)

    spec_name, spec_hash = _read_spec_meta(run_dir, cells)
    agg = aggregate_cells(cells, pass_threshold)
    leaderboard = build_matrix_markdown(spec_name, spec_hash, agg)

    report = RescoreReport(
        run_dir=run_dir, spec_name=spec_name, spec_hash=spec_hash,
        cells_total=len(cells), cells_rescored=rescored,
        cells_no_artifact=no_artifact, cells_not_ok=not_ok,
        cells=cells, aggregate=agg, leaderboard_md=leaderboard, rescores=rescores,
    )

    if write:
        _persist(run_dir, cells, agg, leaderboard, backup=backup)
        report.written = True
    return report


def _persist(run_dir: Path, cells: List[CellResult], agg: Dict, leaderboard: str,
             *, backup: bool) -> None:
    payloads = {
        CELLS_FILE: json.dumps([c.to_dict() for c in cells], indent=2),
        AGGREGATE_FILE: json.dumps(agg, indent=2),
        LEADERBOARD_FILE: leaderboard,
    }
    for name, text in payloads.items():
        target = run_dir / name
        if backup and target.exists():
            bak = target.with_suffix(target.suffix + ".bak")
            if not bak.exists():  # preserve the *original* pre-rescore copy, never clobber
                bak.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        target.write_text(text, encoding="utf-8")
