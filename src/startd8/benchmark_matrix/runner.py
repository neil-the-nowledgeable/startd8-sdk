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
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol

from .budget import BudgetGuard, estimate_run_cost
from .run_spec import BenchmarkRunSpec, MatrixCell

# Cell lifecycle outcomes (a slice of the FR-38 state machine; full resumability is later).
STATUS_OK = "ok"
STATUS_FAILED = "failed"          # genuine model failure — model produced no/bad artifacts
STATUS_TIMEOUT = "timeout"
STATUS_INTEGRITY_FAIL = "integrity_fail"  # deterministic shortcut fired (R1-S4) — not LLM-maximal
STATUS_BUDGET_SKIP = "budget_skip"        # cumulative budget exhausted before this cell ran
STATUS_INFRA_FAIL = "infra_fail"  # auth/access/rate-limit/connection — NOT the model's fault; excluded
                                  # from quality/pass-rate/catastrophic (like FR-32 toolchain-absent).

# Substrings that mark an infrastructure/access failure rather than a model failure.
# Distinguishing these prevents a dead API key or un-provisioned model from unfairly
# tanking a model's score (the flagships-round1 run conflated a 401 with a $0 model output).
_INFRA_ERROR_MARKERS = (
    "invalid x-api-key", "authentication_error", "401",
    "not_found_error", "not available", "404",
    "permission_denied", "permission denied", "403",
    "rate_limit", "rate limit", "429", "overloaded_error", "overloaded",
    "apiconnectionerror", "connection error", "timed out connecting",
    "insufficient_quota", "quota",
)


def is_infra_error(msg: Optional[str]) -> bool:
    """True if an error string indicates an infra/access failure (not a model failure)."""
    if not msg:
        return False
    low = msg.lower()
    return any(marker in low for marker in _INFRA_ERROR_MARKERS)


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
    quality: Optional[float] = None          # COMPOSITE score in [0,1] (FR-11): structural gated by compile
    structural_quality: Optional[float] = None  # disk-compliance only (pre-M4 signal, kept for transparency)
    compile_ok: Optional[bool] = None        # FR-29 gate; None = toolchain absent (FR-32 degraded)
    degraded: bool = False                   # a scoring term was unavailable (FR-32)
    cost_usd: Optional[float] = None
    latency_s: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    deterministic_skips: int = 0             # R1-S4: must be 0 for a valid benchmark cell
    integrity_ok: bool = True
    sandbox_violation: Optional[str] = None  # FR-44: a guardrail tripped scoring this cell
    error: Optional[str] = None
    defect_total: Optional[int] = None       # FR-B3: defects from the expose ledger (None = not run)
    defects_by_category: Optional[Dict[str, int]] = None  # FR-B3: per-category contribution
    functional_coverage: Optional[float] = None  # FR-T2-COMPOSITE: behavioral coverage (None = not run)
    behavioral: Optional[Dict] = None         # FR-T2-PROV: suite results + isolation provenance

    @property
    def tokens_per_sec(self) -> Optional[float]:
        if self.output_tokens and self.latency_s and self.latency_s > 0:
            return self.output_tokens / self.latency_s
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tokens_per_sec"] = self.tokens_per_sec
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CellResult":
        """Rebuild a CellResult from its serialized form (drops the computed
        ``tokens_per_sec`` and any unknown keys). Used to re-load a prior run's
        cells.json for re-aggregation / re-scoring."""
        fields = {f.name for f in dataclass_fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in fields})


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
                 workdir_root: Optional[Path] = None,
                 repair_mode: str = "apply", expose_defects: bool = False,
                 behavioral: bool = False):
        self.seeds_dir = Path(seeds_dir)
        self.per_run_timeout_s = per_run_timeout_s
        self.workdir_root = workdir_root
        self.repair_mode = repair_mode          # FR-B5: "apply" | "shadow" | "off"
        self.expose_defects = expose_defects     # FR-B5: persist defect ledger + de-saturate score
        # FR-T2-COMPOSITE: run the behavioral suite (execute the service) and fold in a functional
        # term. Default OFF — turning it on is the paymentservice pilot (spends LLM only via the
        # generation step; the suite itself is $0). Off ⇒ scoring path is byte-identical to today.
        self.behavioral = behavioral

    def __call__(self, cell: MatrixCell, spec: BenchmarkRunSpec, language: str) -> CellResult:
        from ..model_comparison import build_command, extract_metrics, run_command, SDK_ROOT

        cid = cell_id(spec.spec_hash(), cell)
        seed = self.seeds_dir / f"seed-{cell.service}.json"
        if not seed.exists():
            return CellResult(cell_id=cid, service=cell.service, model=cell.model,
                              language=language, repetition=cell.repetition,
                              status=STATUS_FAILED, error=f"seed not found: {seed}")

        root = self.workdir_root or Path(tempfile.mkdtemp(prefix="obbench-"))
        workdir = root / sandbox_dir_name(cell.service, cell.model, cell.repetition)
        workdir.mkdir(parents=True, exist_ok=True)
        output = workdir / ".startd8" / "benchmark-output"

        cmd = build_command(seed, workdir, output, cell.model, spec.per_cell_cap_usd,
                            repair_mode=self.repair_mode, expose_defects=self.expose_defects)
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

        # Prefer the structured per-feature error (carries the real API error, e.g. 401/404)
        # over the stderr tail — needed to classify infra failures vs model failures.
        hist = pr.get("history") or []
        hist_err = hist[-1].get("error") if hist else None
        err_text = hist_err or run.get("stderr_tail") or ""

        if run["timed_out"]:
            status = STATUS_TIMEOUT
        elif not integrity_ok or det_skips > 0:
            status = STATUS_INTEGRITY_FAIL
        elif metrics.get("status") == "success":
            status = STATUS_OK
        elif is_infra_error(err_text):
            status = STATUS_INFRA_FAIL  # auth/access/rate-limit — not the model's fault
        else:
            status = STATUS_FAILED

        structural = metrics.get("mean_disk_quality_score")
        quality = structural
        compile_ok = None
        degraded = False
        sandbox_violation = None
        defect_total = None
        defects_by_category = None
        functional_coverage = None
        functional_degraded = False
        behavioral_prov = None

        # M4 compile gate (FR-11/FR-29/FR-44): only for cells that actually generated.
        # Run the language's syntax/compile check on the generated file inside the sandbox;
        # the composite floors non-compiling output. Failures here are scoring outcomes,
        # never fatal to the harness.
        if status == STATUS_OK:
            try:
                gen_file = self._generated_file(workdir, cell.service)
                if gen_file is not None:
                    from ..languages import LanguageRegistry, resolve_language
                    from .scoring import apply_defect_penalty, score_file
                    LanguageRegistry.discover()
                    profile = resolve_language([str(gen_file)])
                    # FR-T2-COMPOSITE: behavioral term (default-off). Execute the service via its
                    # startup contract + run the suite; fold coverage into the composite (the
                    # compile gate inside score_file still floors non-compiling code first).
                    if self.behavioral:
                        from ..model_comparison import _load_json
                        from .behavioral.execute import run_behavioral_cell
                        seed_data = _load_json(seed) or {}
                        tfs = ((seed_data.get("tasks") or [{}])[0].get("config", {})
                               .get("context", {}).get("target_files")) or []
                        bres = run_behavioral_cell(seed_data, workdir, cell.service, tfs)
                        if bres.has_suite:
                            functional_coverage = bres.functional
                            functional_degraded = bres.degraded
                            behavioral_prov = bres.provenance
                    composite = score_file(gen_file, profile, structural=structural,
                                           functional=functional_coverage,
                                           functional_degraded=functional_degraded)
                    # FR-B3: in expose mode, fold the defect ledger into the score so a
                    # parses-but-defective file is pulled off the compile-gate ceiling.
                    if self.expose_defects:
                        ledger = self._aggregate_defect_ledger(workdir)
                        if ledger is not None:
                            composite = apply_defect_penalty(composite, ledger)
                            defect_total = ledger.get("total")
                            defects_by_category = ledger.get("by_category")
                    quality = composite.value
                    compile_ok = composite.compile_ok
                    degraded = composite.degraded
            except Exception as exc:  # noqa: BLE001 — scoring must not crash a run
                sandbox_violation = f"scoring error: {type(exc).__name__}: {exc}"

        return CellResult(
            cell_id=cid, service=cell.service, model=cell.model, language=language,
            repetition=cell.repetition, status=status,
            quality=quality, structural_quality=structural,
            compile_ok=compile_ok, degraded=degraded,
            cost_usd=metrics.get("total_cost"),
            latency_s=run.get("duration_seconds"),
            input_tokens=metrics.get("input_tokens"),
            output_tokens=metrics.get("output_tokens"),
            deterministic_skips=det_skips, integrity_ok=integrity_ok,
            sandbox_violation=sandbox_violation,
            error=None if status == STATUS_OK else (err_text or status),
            defect_total=defect_total, defects_by_category=defects_by_category,
            functional_coverage=functional_coverage, behavioral=behavioral_prov,
        )

    @staticmethod
    def _aggregate_defect_ledger(workdir: Path) -> Optional[Dict]:
        """FR-B3: merge all per-unit defect ledgers in a cell workdir into one
        {total, by_category, by_severity} dict. None when expose wrote no ledger."""
        import json
        led_dir = workdir / ".startd8" / "defect-ledger"
        files = sorted(led_dir.glob("*.json")) if led_dir.is_dir() else []
        if not files:
            return None
        total = 0
        by_cat: Dict[str, int] = {}
        by_sev: Dict[str, int] = {}
        for f in files:
            try:
                d = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            total += int(d.get("total", 0) or 0)
            for k, v in (d.get("by_category") or {}).items():
                by_cat[k] = by_cat.get(k, 0) + int(v)
            for k, v in (d.get("by_severity") or {}).items():
                by_sev[k] = by_sev.get(k, 0) + int(v)
        return {"total": total, "by_category": by_cat, "by_severity": by_sev}

    def _generated_file(self, workdir: Path, service: str) -> Optional[Path]:
        """Resolve the generated service file from the seed's target_files, under workdir."""
        return resolve_generated_file(self.seeds_dir, workdir, service)


def resolve_generated_file(seeds_dir: Path, workdir: Path, service: str) -> Optional[Path]:
    """Resolve a service's primary generated file (the seed's first target_files entry)
    under ``workdir``. Shared by the live runner and the post-hoc re-scorer so both
    locate the same file the model was asked to write."""
    from ..model_comparison import _load_json
    seed = _load_json(Path(seeds_dir) / f"seed-{service}.json") or {}
    tasks = seed.get("tasks") or []
    if not tasks:
        return None
    targets = (tasks[0].get("config", {}).get("context", {}).get("target_files")) or []
    if not targets:
        return None
    cand = Path(workdir) / targets[0]
    return cand if cand.exists() else None


def sandbox_dir_name(service: str, model: str, repetition: int) -> str:
    """The per-cell sandbox directory name used by :class:`SubprocessCellExecutor`
    (``<service>-<model with ':'→'_'>-r<rep>``). Factored out so the re-scorer can
    locate a cell's generated workdir without re-running it."""
    return f"{service}-{model.replace(':', '_')}-r{repetition}"


def reclassify_infra_failures(cells: List[CellResult]) -> int:
    """Upgrade prior-run cells marked STATUS_FAILED whose error is actually infra/access
    (e.g. a 401 from a dead key) to STATUS_INFRA_FAIL, so aggregation excludes them from
    the model's quality/pass-rate/catastrophic. Returns the count reclassified.

    Lets us honestly re-aggregate a run that predates infra classification.
    """
    n = 0
    for c in cells:
        if c.status == STATUS_FAILED and is_infra_error(c.error):
            c.status = STATUS_INFRA_FAIL
            n += 1
    return n
