"""Matrix runner — executes a BenchmarkRunSpec over the service x model x repetition grid (M3).

Generalizes the single-seed ``model_comparison.py`` into the full benchmark matrix, with
budget guardrails (FR-33) enforced cell-by-cell. The per-cell executor is INJECTABLE:
the real :class:`SubprocessCellExecutor` drives ``run_prime_workflow.py --benchmark-mode``,
while tests inject a fake to exercise orchestration/budget without LLM spend or subprocesses.

This is the deliberate inversion of the SDK's $0 thesis (FR-1): every cell runs with the
deterministic shortcut cascade OFF, so the LLM does maximal work.
"""
from __future__ import annotations

import json
import os
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
STATUS_DEPS_MISSING = "deps_missing"  # imports a required external dep (gRPC/proto stubs) absent in the offline sandbox — NOT the model's fault; excluded
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
    # Missing/unconfigured credentials — a setup failure ($0, no LLM call), never the model's
    # fault. The provider raises "<Provider> API key required..." wrapped in "Failed to resolve
    # agents: ...". Classify as infra so it's excluded, exactly like a dead-key 401.
    "api key required", "api key is required", "no api key", "missing api key",
    "failed to resolve agents",
)


def is_infra_error(msg: Optional[str]) -> bool:
    """True if an error string indicates an infra/access failure (not a model failure)."""
    if not msg:
        return False
    low = msg.lower()
    return any(marker in low for marker in _INFRA_ERROR_MARKERS)


def _role_slug(agent: str) -> str:
    """Slug an agent spec for a path/id segment — `provider:model` → `provider_model` so no
    stray top-level `:` leaks into `cell_id` (which `rescore` recovers via `split(":",1)[0]`, R6-S9)."""
    return agent.replace(":", "_")


def cell_id(spec_hash: str, cell: MatrixCell) -> str:
    """Stable per-cell identity (FR-38 idempotency-key seed). Segments are **appended** in a fixed
    order — **role first, then leverage** (R6-S1) — and BOTH are omitted for the default (diagonal
    lead==drafter, leverage off), so a default cell stays byte-identical to pre-K3/pre-K2 (FR-1).
    Appending (not prepending) + slugging the role agents (R6-S9) keeps `spec_hash` recoverable via
    `cell_id.split(":",1)[0]` (`rescore._read_spec_meta`)."""
    base = f"{spec_hash[:12]}:{cell.service}:{cell.model}:r{cell.repetition}"
    if not getattr(cell, "is_diagonal", True):  # K3 role segment (off-diagonal only)
        base = f"{base}:lead-{_role_slug(cell.resolved_lead)}_drafter-{_role_slug(cell.resolved_drafter)}"
    leverage = getattr(cell, "leverage", "off")  # K2 leverage segment (on only), AFTER role
    if leverage != "off":
        base = f"{base}:lev-{leverage}"
    tier = getattr(cell, "tier", "baseline")  # difficulty-tier segment (hardened only), AFTER leverage
    return base if tier == "baseline" else f"{base}:tier-{tier}"


def _cell_filename(cell_id: str) -> str:
    """Filesystem-safe filename for a cell id (model/service ids carry ``:`` and ``/``)."""
    return cell_id.replace(":", "_").replace("/", "_") + ".json"


def persist_cell_atomic(cells_dir: Path, cell: "CellResult") -> Path:
    """Durably flush one finished cell to ``cells_dir/<id>.json`` (R3-S1 / R1-F2 / FR-T2-PERSIST).

    Writes to a sibling ``.tmp`` then ``os.replace`` (atomic rename within the dir), so a reader — or
    a re-score after a crash — never sees a half-written cell, and an interruption on a *later* cell
    can't lose cells already written. One file per cell ⇒ no shared-file write race under concurrency.
    Returns the path written. Used as the ``run_matrix(on_cell=...)`` hook by the behavioral pilot."""
    cells_dir = Path(cells_dir)
    cells_dir.mkdir(parents=True, exist_ok=True)
    path = cells_dir / _cell_filename(cell.cell_id)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cell.to_dict(), indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)
    return path


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
    latency_s: Optional[float] = None        # pipeline wall-clock: whole run_prime_workflow subprocess
    model_time_s: Optional[float] = None     # FR-SPEED-2: pure model API time (Σ GenerateResult.time_ms)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    deterministic_skips: int = 0             # K2: leverage-off must be 0 (R1-S4); on-cells record it as data
    integrity_ok: bool = True
    leverage: str = "off"                    # K2 coordinate (FR-K2-1): "off" | "on"
    leverage_source: Optional[str] = None    # K2 (R1-S4): on-path mechanism — "routing"|"micro_prime"|"both"
    lead: Optional[str] = None               # K3 coordinate (FR-K3-1/R6-S4): None ⇒ model (diagonal)
    drafter: Optional[str] = None            # K3 coordinate (FR-K3-1/R6-S4): None ⇒ model (diagonal)
    sandbox_violation: Optional[str] = None  # FR-44: a guardrail tripped scoring this cell
    error: Optional[str] = None
    defect_total: Optional[int] = None       # FR-B3: defects from the expose ledger (None = not run)
    defects_by_category: Optional[Dict[str, int]] = None  # FR-B3: per-category contribution
    functional_coverage: Optional[float] = None  # FR-T2-COMPOSITE: behavioral coverage (None = not run)
    behavioral: Optional[Dict] = None         # FR-T2-PROV: suite results + isolation provenance

    @property
    def tokens_per_sec(self) -> Optional[float]:
        """Pipeline throughput — output tokens over the whole-subprocess wall-clock."""
        if self.output_tokens and self.latency_s and self.latency_s > 0:
            return self.output_tokens / self.latency_s
        return None

    @property
    def model_tokens_per_sec(self) -> Optional[float]:
        """Pure-model throughput (FR-SPEED-2) — output tokens over pure model API time only."""
        if self.output_tokens and self.model_time_s and self.model_time_s > 0:
            return self.output_tokens / self.model_time_s
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tokens_per_sec"] = self.tokens_per_sec
        d["model_tokens_per_sec"] = self.model_tokens_per_sec  # FR-SPEED-2
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
                leverage=getattr(cell, "leverage", "off"),  # K2: keep coord for pairing audit (R2-S4)
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
                 behavioral: bool = False,
                 operator_callback: Optional[Callable[[str, str, MatrixCell], None]] = None):
        self.seeds_dir = Path(seeds_dir)
        self.per_run_timeout_s = per_run_timeout_s
        # Coerce to Path: callers (e.g. the pilot's persistent batch root) may pass a str, and the
        # __call__ body does ``root / sandbox_dir_name(...)`` which requires a Path (FR-T2-PERSIST).
        self.workdir_root = Path(workdir_root) if workdir_root else None
        self.repair_mode = repair_mode          # FR-B5: "apply" | "shadow" | "off"
        self.expose_defects = expose_defects     # FR-B5: persist defect ledger + de-saturate score
        # FR-T2-COMPOSITE: run the behavioral suite (execute the service) and fold in a functional
        # term. Default OFF — turning it on is the paymentservice pilot (spends LLM only via the
        # generation step; the suite itself is $0). Off ⇒ scoring path is byte-identical to today.
        self.behavioral = behavioral
        self.operator_callback = operator_callback

    def __call__(self, cell: MatrixCell, spec: BenchmarkRunSpec, language: str) -> CellResult:
        from ..model_comparison import build_command, extract_metrics, run_command, SDK_ROOT

        cid = cell_id(spec.spec_hash(), cell)
        tier = getattr(cell, "tier", "baseline")
        # Tier-aware seed selection (FR-2/FR-4). Baseline uses seed-<svc>.json; a non-baseline tier
        # uses seed-<svc>-<tier>.json and is FAIL-CLOSED: if the hardened seed is absent we mark the
        # cell INFRA_FAIL rather than silently running the baseline seed under a hardened label (that
        # would corrupt the baseline-vs-hardened comparison — FR-4). Baseline fallback is NEVER applied
        # to a non-baseline tier.
        seed = self.seeds_dir / seed_filename(cell.service, tier)
        if not seed.exists():
            status = STATUS_INFRA_FAIL if tier != "baseline" else STATUS_FAILED
            reason = (f"{tier} seed not found: {seed} (fail-closed — not falling back to baseline)"
                      if tier != "baseline" else f"seed not found: {seed}")
            return CellResult(cell_id=cid, service=cell.service, model=cell.model,
                              language=language, repetition=cell.repetition,
                              status=status, error=reason)

        leverage = getattr(cell, "leverage", "off")
        root = self.workdir_root or Path(tempfile.mkdtemp(prefix="obbench-"))
        workdir = root / sandbox_dir_name(cell.service, cell.model, cell.repetition, leverage,
                                          lead=cell.lead, drafter=cell.drafter, tier=tier)
        workdir.mkdir(parents=True, exist_ok=True)
        output = workdir / ".startd8" / "benchmark-output"

        # K3 (FR-K3-1): distinct lead/drafter for off-diagonal cells; None ⇒ model ⇒ byte-identical
        # diagonal command (R6-S2).
        cmd = build_command(seed, workdir, output, cell.model, spec.per_cell_cap_usd,
                            repair_mode=self.repair_mode, expose_defects=self.expose_defects,
                            lead_agent=cell.lead, drafter_agent=cell.drafter)
        # K2 / S3 (R2-S1): the leverage branch lives HERE (the only place benchmark-mode was appended).
        # off → LLM-maximal (today): disable the deterministic cascade. on → engage SDK scaffolding:
        # omit --benchmark-mode, add routing/micro-prime per spec.leverage_on_config (their combo with
        # benchmark-mode is rejected by run_prime_workflow.py:385 — keeping them apart is the point).
        leverage_source = None
        if leverage == "off":
            cmd.append("--benchmark-mode")  # FR-1/FR-27
        else:
            on_cfg = dict(getattr(spec, "leverage_on_config", {}) or {})
            srcs = []
            if on_cfg.get("routing"):
                cmd.append("--complexity-routing")
                srcs.append("routing")
            if on_cfg.get("micro_prime"):
                cmd.append("--micro-prime")
                srcs.append("micro_prime")
            leverage_source = "both" if len(srcs) == 2 else (srcs[0] if srcs else None)
        if self.operator_callback:
            self.operator_callback("starting model workflow", "generation", cell)

        def _stream(stream: str, line: str) -> None:
            if self.operator_callback:
                self.operator_callback(f"{stream}: {line}", "workflow_output", cell)

        run = run_command(cmd, SDK_ROOT, timeout=self.per_run_timeout_s,
                          on_output=_stream if self.operator_callback else None)
        if self.operator_callback:
            self.operator_callback("model workflow completed", "generation_complete", cell)
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

        # Read provenance (integrity). off-path emits `benchmark_provenance` (gated on
        # --benchmark-mode); on-path omits --benchmark-mode so it emits `leverage_provenance`
        # instead (R3-S1) — without that fallback an on-cell would default det_skips=0 and the
        # skip-intensity column + integrity check would have no input data.
        det_skips, integrity_ok = 0, True
        pr = _load_json(_latest_match(output, "prime-result*.json")) or {}
        prov = pr.get("benchmark_provenance") or pr.get("leverage_provenance") or {}
        if prov:
            det_skips = int(prov.get("deterministic_skip_count", 0) or 0)
            integrity_ok = bool(prov.get("integrity_ok", True))

        # Prefer the structured per-feature error (carries the real API error, e.g. 401/404)
        # over the stderr tail — needed to classify infra failures vs model failures.
        hist = pr.get("history") or []
        hist_err = hist[-1].get("error") if hist else None
        err_text = hist_err or run.get("stderr_tail") or ""

        # K2 status resolution (S3). Integrity gate is FAIL-CLOSED: deterministic skips are a
        # violation for every leverage value EXCEPT the literal "on" (R1-S1 — None/"off"/unknown
        # stay gated). `integrity_ok=false` is ALWAYS a failure, even on-cells (R2-S2: "run corrupt"
        # ≠ "leverage used shortcuts"). On the on-path, skips are expected DATA, so a skip-heavy
        # on-cell that produced a valid artifact must resolve OK rather than fall through to FAILED
        # (R5-S5 — the on-path may not surface metrics.status=="success" the way the off-path does).
        skips_are_violation = det_skips > 0 and leverage != "on"
        produced_artifact = metrics.get("mean_disk_quality_score") is not None

        from .scoring import is_missing_deps_failure  # local import (matches the score_file pattern)

        if run["timed_out"]:
            status = STATUS_TIMEOUT
        elif not integrity_ok or skips_are_violation:
            status = STATUS_INTEGRITY_FAIL
        elif metrics.get("status") == "success":
            status = STATUS_OK
        elif leverage == "on" and produced_artifact and not is_infra_error(err_text):
            status = STATUS_OK  # R5-S5: valid on-cell artifact (+ expected skips) — OK, not FAILED
        elif is_infra_error(err_text):
            status = STATUS_INFRA_FAIL  # auth/access/rate-limit — not the model's fault
        elif is_missing_deps_failure(err_text):
            # gRPC/protobuf/proto-stub import absent in the offline sandbox — Tier-1 fairness analog
            # of the Java/C# missing-dep degrade. Excluded from scoring, not catastrophic.
            status = STATUS_DEPS_MISSING
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
        functional_model_fault = False
        behavioral_prov = None

        # M4 compile gate (FR-11/FR-29/FR-44): only for cells that actually generated.
        # Run the language's syntax/compile check on the generated file inside the sandbox;
        # the composite floors non-compiling output. Failures here are scoring outcomes,
        # never fatal to the harness.
        if status == STATUS_OK:
            if self.operator_callback:
                self.operator_callback("starting compile and behavioral scoring", "compile_scoring", cell)
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
                        if self.operator_callback:
                            self.operator_callback("starting behavioral suite", "behavioral_execution", cell)
                        from ..model_comparison import _load_json
                        from .behavioral.execute import run_behavioral_cell
                        seed_data = _load_json(seed) or {}
                        tfs = ((seed_data.get("tasks") or [{}])[0].get("config", {})
                               .get("context", {}).get("target_files")) or []
                        bres = run_behavioral_cell(seed_data, workdir, cell.service, tfs, tier=tier)
                        if bres.has_suite:
                            functional_coverage = bres.functional
                            functional_degraded = bres.degraded
                            functional_model_fault = getattr(bres, "model_fault", False)
                            behavioral_prov = bres.provenance
                    composite = score_file(gen_file, profile, structural=structural,
                                           functional=functional_coverage,
                                           functional_degraded=functional_degraded,
                                           functional_model_fault=functional_model_fault)
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
            model_time_s=metrics.get("model_time_s"),   # FR-SPEED-2 (pure model API time)
            input_tokens=metrics.get("input_tokens"),
            output_tokens=metrics.get("output_tokens"),
            deterministic_skips=det_skips, integrity_ok=integrity_ok,
            leverage=leverage, leverage_source=leverage_source,
            lead=cell.lead, drafter=cell.drafter,
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


def seed_filename(service: str, tier: str = "baseline") -> str:
    """Seed filename for a (service, tier). MUST stay in lockstep with the filenames
    ``gen_ob_benchmark_seeds.py`` writes: baseline → ``seed-<svc>.json``; a non-baseline tier →
    ``seed-<svc>.<tier>.json`` (dot infix, e.g. ``seed-currencyservice.hardened.json``). Centralized
    so the runner's seed selection and the generator's output can't drift apart (they did once)."""
    return f"seed-{service}.json" if tier == "baseline" else f"seed-{service}.{tier}.json"


def sandbox_dir_name(service: str, model: str, repetition: int, leverage: str = "off",
                     lead: Optional[str] = None, drafter: Optional[str] = None,
                     tier: str = "baseline") -> str:
    """The per-cell sandbox directory name used by :class:`SubprocessCellExecutor`
    (``<service>-<model with ':'→'_'>-r<rep>``). Factored out so the re-scorer can
    locate a cell's generated workdir without re-running it.

    Segments compose in a fixed order — **role, then leverage, then tier** — and all are
    omitted for the default (diagonal lead==drafter, leverage off, tier baseline):
    - K3 (R6-S1): an off-diagonal cell appends ``-lead-<lead>_drafter-<drafter>`` (slugged) so
      ``A→B``, ``B→A`` and the ``A``/``B`` diagonals resolve to **distinct workdirs**.
    - K2 (R5-S2): a non-``"off"`` ``leverage`` appends ``-lev-<state>``.
    - Tier (FR-2): a non-``"baseline"`` ``tier`` appends ``-tier-<state>`` so a service's baseline
      and hardened cells get **distinct workdirs** (and persisted servers don't collide).
    The all-default cell is unsuffixed — byte-identical to pre-tier/pre-K2/pre-K3 dirs (FR-1), so
    rescoring existing runs still resolves."""
    base = f"{service}-{model.replace(':', '_')}-r{repetition}"
    rl, rd = lead or model, drafter or model
    if rl != rd:  # K3 role segment (off-diagonal only), before the leverage segment
        base = f"{base}-lead-{_role_slug(rl)}_drafter-{_role_slug(rd)}"
    if leverage != "off":
        base = f"{base}-lev-{leverage}"
    return base if tier == "baseline" else f"{base}-tier-{tier}"


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
