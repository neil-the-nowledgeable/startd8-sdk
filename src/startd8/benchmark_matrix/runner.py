"""Matrix runner — executes a BenchmarkRunSpec over the service x model x repetition grid (M3).

Generalizes the single-seed ``model_comparison.py`` into the full benchmark matrix, with
budget guardrails (FR-33) enforced cell-by-cell. The per-cell executor is INJECTABLE:
the real :class:`SubprocessCellExecutor` drives ``run_prime_workflow.py --benchmark-mode``,
while tests inject a fake to exercise orchestration/budget without LLM spend or subprocesses.

This is the deliberate inversion of the SDK's $0 thesis (FR-1): every cell runs with the
deterministic shortcut cascade OFF, so the LLM does maximal work.
"""
from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from .budget import BudgetGuard, estimate_run_cost
from .run_spec import BenchmarkRunSpec, MatrixCell

# Cell lifecycle outcomes (a slice of the FR-38 state machine; full resumability is later).
STATUS_OK = "ok"
STATUS_FAILED = "failed"          # generation failed / no artifacts
STATUS_TIMEOUT = "timeout"
STATUS_INTEGRITY_FAIL = "integrity_fail"  # deterministic shortcut fired (R1-S4) — not LLM-maximal
STATUS_BUDGET_SKIP = "budget_skip"        # cumulative budget exhausted before this cell ran


def cell_id(spec_hash: str, cell: MatrixCell) -> str:
    """Stable per-cell identity (FR-38 idempotency-key seed)."""
    return f"{spec_hash[:12]}:{cell.service}:{cell.model}:r{cell.repetition}"


@dataclass
class CellResult:
    """One (service, model, repetition) outcome."""
    cell_id: str
    service: str
    model: str
    language: str
    repetition: int
    status: str
    quality: Optional[float] = None          # composite/structural score in [0,1]
    cost_usd: Optional[float] = None
    latency_s: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    deterministic_skips: int = 0             # R1-S4: must be 0 for a valid benchmark cell
    integrity_ok: bool = True
    error: Optional[str] = None

    @property
    def tokens_per_sec(self) -> Optional[float]:
        if self.output_tokens and self.latency_s and self.latency_s > 0:
            return self.output_tokens / self.latency_s
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tokens_per_sec"] = self.tokens_per_sec
        return d


class CellExecutor(Protocol):
    """Runs one matrix cell and returns its result. Injectable (real vs fake)."""
    def __call__(self, cell: MatrixCell, spec: BenchmarkRunSpec, language: str) -> CellResult: ...


@dataclass
class MatrixRunResult:
    spec_hash: str
    cells: List[CellResult] = field(default_factory=list)
    total_cost_usd: float = 0.0
    budget_exhausted: bool = False
    skipped_cells: int = 0


def run_matrix(
    spec: BenchmarkRunSpec,
    executor: CellExecutor,
    *,
    languages: Optional[dict] = None,
    on_cell: Optional[Callable[[CellResult], None]] = None,
    preflight: bool = True,
) -> MatrixRunResult:
    """Execute every cell of ``spec`` through ``executor`` under budget control (FR-33).

    Args:
        spec: the immutable run spec (FR-36).
        executor: per-cell runner (real subprocess or test fake).
        languages: service -> language id (from the seeds). Defaults to "unknown".
        on_cell: optional callback after each cell (progress/streaming).
        preflight: run the fail-closed budget preflight before starting (default True).
            Raises BudgetError if unsafe — caller may set False for dry orchestration tests
            with a no-ceiling spec.
    """
    languages = languages or {}
    guard = BudgetGuard(spec)
    if preflight:
        guard.preflight(estimate_run_cost(spec))

    sh = spec.spec_hash()
    result = MatrixRunResult(spec_hash=sh)

    for cell in spec.cells():
        cid = cell_id(sh, cell)
        lang = languages.get(cell.service, "unknown")

        # Cumulative abort (FR-33): once spend has hit the ceiling, skip the rest.
        if guard.would_exceed():
            result.cells.append(CellResult(
                cell_id=cid, service=cell.service, model=cell.model, language=lang,
                repetition=cell.repetition, status=STATUS_BUDGET_SKIP,
                error="cumulative budget exhausted before this cell ran",
            ))
            result.skipped_cells += 1
            result.budget_exhausted = True
            continue

        cr = executor(cell, spec, lang)
        guard.record(cr.cell_id, cr.cost_usd or 0.0)
        result.cells.append(cr)
        result.total_cost_usd = guard.spent_usd
        if on_cell:
            on_cell(cr)

    return result


class SubprocessCellExecutor:
    """Real executor: runs ``run_prime_workflow.py --benchmark-mode`` per cell.

    Each cell generates into a fresh, disposable workdir (the model writes the service
    from scratch — no source project to copy). Reuses the proven model_comparison helpers
    (build_command / run_command / extract_metrics) so the invocation path stays identical
    to the existing comparison harness, plus --benchmark-mode (FR-1) for LLM-maximization.
    """

    def __init__(self, seeds_dir: Path, *, per_run_timeout_s: Optional[float] = 1800.0,
                 workdir_root: Optional[Path] = None):
        self.seeds_dir = Path(seeds_dir)
        self.per_run_timeout_s = per_run_timeout_s
        self.workdir_root = workdir_root

    def __call__(self, cell: MatrixCell, spec: BenchmarkRunSpec, language: str) -> CellResult:
        from ..model_comparison import build_command, extract_metrics, run_command, SDK_ROOT

        cid = cell_id(spec.spec_hash(), cell)
        seed = self.seeds_dir / f"seed-{cell.service}.json"
        if not seed.exists():
            return CellResult(cell_id=cid, service=cell.service, model=cell.model,
                              language=language, repetition=cell.repetition,
                              status=STATUS_FAILED, error=f"seed not found: {seed}")

        root = self.workdir_root or Path(tempfile.mkdtemp(prefix="obbench-"))
        workdir = root / f"{cell.service}-{cell.model.replace(':', '_')}-r{cell.repetition}"
        workdir.mkdir(parents=True, exist_ok=True)
        output = workdir / ".startd8" / "benchmark-output"

        cmd = build_command(seed, workdir, output, cell.model, spec.per_cell_cap_usd)
        cmd.append("--benchmark-mode")  # FR-1/FR-27: disable deterministic cascade
        run = run_command(cmd, SDK_ROOT, timeout=self.per_run_timeout_s)
        metrics = extract_metrics(output)

        from ..model_comparison import _latest_match, _load_json

        # Quality fix (M3 smoke): the postmortem report — source of disk_quality_score —
        # is written to <project_root>/.startd8/, NOT to --output-dir (which holds
        # prime-result.json). extract_metrics only checks output-dir, so quality comes
        # back None. Recover it from the project .startd8 dir when missing.
        if metrics.get("mean_disk_quality_score") is None:
            pm = _load_json(workdir / ".startd8" / "prime-postmortem-report.json") or {}
            dq = [f.get("disk_quality_score") for f in (pm.get("features") or [])
                  if f.get("disk_quality_score") is not None]
            if dq:
                metrics["mean_disk_quality_score"] = sum(dq) / len(dq)

        # Read benchmark provenance (R1-S4 integrity) from prime-result.json.
        det_skips, integrity_ok = 0, True
        pr = _load_json(_latest_match(output, "prime-result*.json")) or {}
        prov = pr.get("benchmark_provenance") or {}
        if prov:
            det_skips = int(prov.get("deterministic_skip_count", 0) or 0)
            integrity_ok = bool(prov.get("integrity_ok", True))

        if run["timed_out"]:
            status = STATUS_TIMEOUT
        elif not integrity_ok or det_skips > 0:
            status = STATUS_INTEGRITY_FAIL
        elif metrics.get("status") == "success":
            status = STATUS_OK
        else:
            status = STATUS_FAILED

        return CellResult(
            cell_id=cid, service=cell.service, model=cell.model, language=language,
            repetition=cell.repetition, status=status,
            quality=metrics.get("mean_disk_quality_score"),
            cost_usd=metrics.get("total_cost"),
            latency_s=run.get("duration_seconds"),
            input_tokens=metrics.get("input_tokens"),
            output_tokens=metrics.get("output_tokens"),
            deterministic_skips=det_skips, integrity_ok=integrity_ok,
            error=None if status == STATUS_OK else (run.get("stderr_tail") or status),
        )
