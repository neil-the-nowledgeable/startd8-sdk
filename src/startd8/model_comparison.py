"""Prime Contractor multi-model comparison — reusable core.

Runs the SAME seed (requirements + plan) through PrimeContractorWorkflow once per model, each in
a fully isolated working-tree copy + output dir, SERIALLY, then scores each run from the artifacts
the workflow already produces and emits a ranked capability+cost report.

This module holds the reusable logic; it is invoked by both the `startd8 compare-models` CLI command
and the `scripts/run_prime_model_comparison.py` standalone wrapper.

Design: docs/design/PRIME_MODEL_COMPARISON_REQUIREMENTS.md (v0.2) +
        docs/design/PRIME_MODEL_COMPARISON_PLAN.md (v1.0).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# Repo root of the SDK (…/src/startd8/model_comparison.py -> parents[2]); used to locate
# scripts/run_prime_workflow.py and as the subprocess cwd regardless of caller cwd.
SDK_ROOT = Path(__file__).resolve().parents[2]
PRIME_WORKFLOW_SCRIPT = SDK_ROOT / "scripts" / "run_prime_workflow.py"

# Paths never copied into a per-model sandbox: heavy dirs, plus run-specific state that would
# otherwise make a fresh run resume/skip (e.g. .prime_contractor_state.json marks features done).
SANDBOX_IGNORE = shutil.ignore_patterns(
    ".git",
    ".venv",
    "venv",
    ".startd8",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "build",
    "dist",
    "*.egg-info",
    ".tox",
    ".prime_contractor_state.json",
    ".next",
    "test-results",
    ".DS_Store",
)


# --------------------------------------------------------------------------- helpers


def slug(model_spec: str) -> str:
    """`anthropic:claude-opus-4-8` -> `anthropic-claude-opus-4-8` (filesystem-safe)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model_spec).strip("-")


def _load_json(path: Optional[Path]) -> Optional[dict[str, Any]]:
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _latest_match(directory: Path, pattern: str) -> Optional[Path]:
    matches = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return float(num) / float(den)


def _mean(values: list[Optional[float]]) -> Optional[float]:
    filtered = [v for v in values if v is not None]
    return sum(filtered) / len(filtered) if filtered else None


def _fmt(value: Optional[float], places: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{places}f}"


# --------------------------------------------------------------------------- sandbox (S2)


def _ignore_factory(source_root: Path, batch_root: Optional[Path]):
    """copytree ignore that also excludes the batch output dir when it lives inside the
    source tree (H1) — otherwise each sandbox would recursively copy prior runs' outputs.
    """
    src = source_root.resolve()
    excluded_top: Optional[str] = None
    if batch_root is not None:
        br = batch_root.resolve()
        if br != src and src in br.parents:
            excluded_top = br.relative_to(src).parts[0]

    def _ignore(dirpath: str, names: list[str]) -> set[str]:
        ignored = set(SANDBOX_IGNORE(dirpath, names))
        if excluded_top and Path(dirpath).resolve() == src:
            ignored.add(excluded_top)
        return ignored

    return _ignore


def materialize_sandbox(
    source_root: Path, workdir: Path, isolation: str, batch_root: Optional[Path] = None
) -> None:
    """Create an independent project-root copy for one model run (FR-1).

    ``copy`` mode includes uncommitted/dirty files and excludes heavy dirs (and the batch
    output dir if nested — H1). ``worktree`` mode checks out **HEAD only** (a git worktree),
    so uncommitted changes in the source are NOT included — use ``copy`` to capture a dirty tree.
    """
    workdir.parent.mkdir(parents=True, exist_ok=True)
    if isolation == "worktree":
        subprocess.run(
            [
                "git",
                "-C",
                str(source_root),
                "worktree",
                "add",
                "--detach",
                str(workdir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    else:  # copy
        shutil.copytree(
            source_root,
            workdir,
            ignore=_ignore_factory(source_root, batch_root),
            dirs_exist_ok=False,
        )


# --------------------------------------------------------------------------- invocation (S3)


def build_command(
    seed: Path,
    workdir: Path,
    output: Path,
    model: str,
    cost_budget: Optional[float],
    repair_mode: str = "apply",
    expose_defects: bool = False,
    lead_agent: Optional[str] = None,
    drafter_agent: Optional[str] = None,
) -> list[str]:
    """Per-model prime workflow command with the model pinned (FR-5/6/7/8).

    ``repair_mode`` / ``expose_defects`` (FR-B5) thread the quality-observability flags into the
    cell so a matrix run can drive shadow + expose; both default-off (identical to today).

    K3 (FR-K3-1): ``lead_agent``/``drafter_agent`` allow distinct roles. Both default to ``model``
    when omitted, so the **diagonal** path emits a list **byte-for-byte identical** to today (R6-S2).
    """
    lead = lead_agent or model
    drafter = drafter_agent or model
    cmd = [
        "python3",
        str(PRIME_WORKFLOW_SCRIPT),
        "--seed",
        str(seed),  # FR-5: same seed, never mutated
        "--project-root",
        str(workdir),  # FR-1: isolated copy
        "--output-dir",
        str(output),
        "--lead-agent",
        lead,  # FR-7: pin both generation paths (K3: lead may differ from drafter)
        "--drafter-agent",
        drafter,
        "--force-regenerate",  # FR-8: no Mottainai reuse
    ]
    # Intentionally NOT passing --complexity-routing / --micro-prime (off by default).
    if cost_budget is not None:
        cmd += ["--cost-budget", str(cost_budget)]
    if repair_mode and repair_mode != "apply":
        cmd += ["--repair-mode", repair_mode]  # FR-B5: shadow observer
    if expose_defects:
        cmd += ["--expose-defects"]  # FR-B5: defect ledger + no advisory downgrade
    return cmd


def run_command(
    cmd: list[str], cwd: Path, timeout: Optional[float] = None,
    on_output: Optional[Callable[[str, str], None]] = None,
) -> dict[str, Any]:
    """Run one model's workflow. A timeout marks the run failed but never wedges the batch (M1)."""
    started = time.monotonic()
    start_ts = datetime.now(timezone.utc)
    if on_output is None:
        try:
            proc = subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=timeout,
            )
            returncode, stdout, stderr, timed_out = proc.returncode, proc.stdout, proc.stderr, False
        except subprocess.TimeoutExpired as e:
            returncode, timed_out = 124, True
            stdout = e.stdout or "" if isinstance(e.stdout, str) else ""
            stderr = (e.stderr or "" if isinstance(e.stderr, str) else "") + f"\n[timed out after {timeout}s]"
    else:
        events: queue.Queue[tuple[str, Optional[str]]] = queue.Queue()
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, bufsize=1)

        def drain(stream_name: str, stream: Any) -> None:
            try:
                for line in iter(stream.readline, ""):
                    events.put((stream_name, line.rstrip("\n")))
            finally:
                events.put((stream_name, None))

        threads = [threading.Thread(target=drain, args=("stdout", proc.stdout), daemon=True),
                   threading.Thread(target=drain, args=("stderr", proc.stderr), daemon=True)]
        for thread in threads:
            thread.start()
        tails = {"stdout": [], "stderr": []}
        closed: set[str] = set()
        timed_out = False
        while len(closed) < 2:
            if timeout is not None and time.monotonic() - started > timeout and proc.poll() is None:
                proc.kill()
                timed_out = True
            try:
                stream_name, line = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                closed.add(stream_name)
                continue
            tails[stream_name].append(line)
            tails[stream_name] = tails[stream_name][-20:]
            on_output(stream_name, line)
        returncode = 124 if timed_out else proc.wait()
        stdout, stderr = "\n".join(tails["stdout"]), "\n".join(tails["stderr"])
        if timed_out:
            stderr += f"\n[timed out after {timeout}s]"
    return {
        "command": cmd,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": time.monotonic() - started,
        "start_ts": start_ts,
        "end_ts": datetime.now(timezone.utc),
        "stdout_tail": "\n".join(stdout.splitlines()[-20:]),
        "stderr_tail": "\n".join(stderr.splitlines()[-20:]),
    }


# --------------------------------------------------------------------------- extraction (S4)


def extract_metrics(output_dir: Path) -> dict[str, Any]:
    """Capability metrics from existing artifacts (FR-9/10). Missing fields -> None."""
    prime_result = _load_json(_latest_match(output_dir, "prime-result*.json")) or {}
    postmortem = _load_json(output_dir / "prime-postmortem-report.json") or {}

    processed = int(prime_result.get("processed", 0) or 0)
    succeeded = int(prime_result.get("succeeded", 0) or 0)
    failed = int(prime_result.get("failed", 0) or 0)

    # Cross-file integrity gate (capability signal present even when no postmortem is emitted).
    gate = prime_result.get("cross_file_gate") or {}
    gate_failures = gate.get("cross_file_failures") or []

    # disk_quality / assembly_delta only exist if the postmortem step ran (optional).
    features = postmortem.get("features", []) or []
    mean_disk = _mean([f.get("disk_quality_score") for f in features])
    semantic_errors = sum(int(f.get("semantic_error_count", 0) or 0) for f in features)

    # Cost: prime-result.json carries the authoritative per-run total (total_cost_usd);
    # the postmortem cost_summary and the DB time-window are fallbacks (S5).
    total_cost = prime_result.get("total_cost_usd")
    cost_source = "prime_result" if total_cost is not None else None
    if total_cost is None:
        total_cost = (postmortem.get("cost_summary") or {}).get("total_usd")
        cost_source = "postmortem" if total_cost is not None else None

    return {
        "status": "success" if prime_result.get("success") else "failed",
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "completion_rate": _safe_div(succeeded, processed),
        "gate_verdict": gate.get("verdict"),
        "gate_score": gate.get("score"),
        "gate_failures": len(gate_failures),
        "mean_disk_quality_score": mean_disk,
        "aggregate_score": postmortem.get("aggregate_score"),
        "avg_assembly_delta": postmortem.get("avg_assembly_delta"),
        "semantic_error_count": semantic_errors,
        "input_tokens": prime_result.get("total_input_tokens"),
        "output_tokens": prime_result.get("total_output_tokens"),
        # FR-SPEED-2: pure model API time (seconds), None when the run didn't capture it (degrade-honest).
        "model_time_s": (lambda ms: ms / 1000.0 if isinstance(ms, (int, float)) else None)(
            prime_result.get("total_model_time_ms")),
        "total_cost": total_cost,
        "cost_source": cost_source,
        "cost_per_succeeded_feature": _safe_div(total_cost, succeeded),
        "artifacts_found": bool(prime_result or postmortem),
    }


def check_spine_in_sync(
    workdir: Path, log: Callable[[str], None] = print
) -> Optional[dict[str, Any]]:
    """Determinism-boundary signal: after a model's run, re-run the $0 deterministic backend
    generator in ``--check`` mode to confirm the model did NOT edit an OWNED (spine) file.

    ``startd8 generate backend --check`` exits 0=in_sync, 1=drift, 2=error. A model that drifts
    the deterministically-generated spine is a capability red flag (it should only add integration
    glue, never rewrite the generated skeleton). Returns ``None`` for non-backend-codegen targets
    (no ``prisma/schema.prisma``), so it is a no-op when the comparison isn't building such an app.

    Salvaged from the (otherwise superseded) e2e-model-comparison-harness; main's ``extract_metrics``
    carries no determinism signal.
    """
    schema = workdir / "prisma" / "schema.prisma"
    if not schema.is_file():
        return None
    rec = run_command(
        ["startd8", "generate", "backend", "--schema", str(schema), "--out", str(workdir), "--check"],
        workdir,
        timeout=300,
    )
    status = {0: "in_sync", 1: "drift", 2: "error"}.get(rec["returncode"], "unknown")
    log(f"  [spine] generate backend --check → {status}")
    return {
        "spine_in_sync": rec["returncode"] == 0,
        "spine_check_status": status,
        "spine_check_detail": ((rec.get("stdout_tail") or "") + (rec.get("stderr_tail") or ""))[-300:],
    }


def cost_from_db(start_ts: datetime, end_ts: datetime) -> Optional[float]:
    """Fallback cost attribution: time-window query of the shared cost DB (FR-12/S5)."""
    try:
        from startd8.costs.store import CostStore

        store = CostStore(Path("~/.startd8/costs.db"))
        records = store.query(start=start_ts, end=end_ts)
        return sum(r.total_cost for r in records) if records else None
    except Exception:
        return None


# --------------------------------------------------------------------------- ranking + report (S6)


def rank_models(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank by capability then cost. Quality = mean disk_quality_score when the postmortem ran,
    else the cross-file gate outcome (fewer failures, higher gate score). Tie-break: cheaper.
    """

    def key(r: dict[str, Any]):
        m = r["metrics"]
        disk = m.get("mean_disk_quality_score")
        gate_score = m.get("gate_score")
        gate_failures = m.get("gate_failures")
        cpsf = m.get("cost_per_succeeded_feature")
        return (
            # Primary: disk quality when available (missing sorts last).
            -(disk if disk is not None else float("-inf")),
            # Secondary: fewer cross-file gate failures is better (missing sorts last).
            gate_failures if gate_failures is not None else float("inf"),
            # Tertiary: higher gate score is better.
            -(gate_score if gate_score is not None else float("-inf")),
            # Quaternary: cheaper per succeeded feature.
            cpsf if cpsf is not None else float("inf"),
        )

    return sorted(results, key=key)


_METRIC_ROWS = [
    ("Status", "status", None),
    ("Processed", "processed", 0),
    ("Succeeded", "succeeded", 0),
    ("Failed", "failed", 0),
    ("Completion rate", "completion_rate", 4),
    ("Cross-file gate", "gate_verdict", None),
    ("Gate score", "gate_score", 4),
    ("Gate failures", "gate_failures", 0),
    ("Mean disk quality", "mean_disk_quality_score", 4),
    ("Semantic errors", "semantic_error_count", 0),
    ("Spine in-sync (determinism)", "spine_check_status", None),
    ("Input tokens", "input_tokens", 0),
    ("Output tokens", "output_tokens", 0),
    ("Total cost ($)", "total_cost", 6),
    ("$/succeeded feature", "cost_per_succeeded_feature", 6),
]


def build_markdown(payload: dict[str, Any]) -> str:
    ranked = payload["ranked"]
    models = [r["model"] for r in ranked]
    lines = [
        "# Prime Contractor Multi-Model Comparison",
        "",
        f"- Batch ID: `{payload['batch_id']}`",
        f"- Generated (UTC): `{payload['generated_at']}`",
        f"- Seed: `{payload['seed']}`",
        f"- Models: {len(models)} | Execution: serial",
        "",
        "> **Single-run, indicative — not statistical.** LLM sampling makes one run per model "
        "noisy; treat rankings as directional. (Repeat-sampling is deferred; see OQ-9.)",
        "",
        "## Comparison (ranked left → right, best first)",
        "",
        "| Metric | " + " | ".join(models) + " |",
        "|---|" + "|".join(["---:"] * len(models)) + "|",
    ]
    for label, field, places in _METRIC_ROWS:
        cells = []
        for r in ranked:
            v = r["metrics"].get(field)
            if places is None or places == 0:
                cells.append(str(v) if v is not None else "N/A")
            else:
                cells.append(_fmt(v, places))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "## Verdict", ""]
    winner = ranked[0]
    wm = winner["metrics"]
    gate = wm.get("gate_verdict")
    gate_str = (
        f"gate {gate} ({wm.get('gate_failures')} failure(s), score {_fmt(wm.get('gate_score'))})"
        if gate is not None
        else f"disk quality {_fmt(wm.get('mean_disk_quality_score'))}"
    )
    lines.append(
        f"**Recommended: `{winner['model']}`** — "
        f"{wm.get('succeeded')}/{wm.get('processed')} features, {gate_str}, "
        f"${_fmt(wm.get('total_cost'), 4)} total "
        f"(${_fmt(wm.get('cost_per_succeeded_feature'), 4)}/succeeded feature)."
    )
    incomplete = [r["model"] for r in ranked if not r["metrics"].get("artifacts_found")]
    if incomplete:
        lines += [
            "",
            f"> ⚠️ Incomplete (no artifacts / crashed): {', '.join(incomplete)}",
        ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- validation + orchestration


def validate_inputs(
    models: list[str],
    seed: Path,
    source_root: Path,
    batch_root: Optional[Path],
    dry_run: bool,
) -> Optional[str]:
    """Return an error message if inputs are invalid, else None."""
    if len(models) < 2:
        return "provide >=2 distinct models."
    if not dry_run and not seed.is_file():
        return f"seed not found: {seed}"
    if batch_root is not None and batch_root.resolve() == source_root.resolve():
        return "batch root must not equal source root."
    return None


def run_comparison(
    *,
    seed: Path,
    source_root: Path,
    models: list[str],
    batch_root: Optional[Path] = None,
    cost_budget: Optional[float] = None,
    per_run_timeout: Optional[float] = None,
    isolation: str = "copy",
    dry_run: bool = False,
    deploy_after: bool = False,
    log: Callable[[str], None] = print,
) -> Optional[dict[str, Any]]:
    """Run the serial multi-model comparison. Returns the report payload (None for dry-run).

    Inputs are assumed validated (see ``validate_inputs``). Writes comparison-report.{md,json}
    to ``batch_root`` on a real run.

    ``deploy_after`` (default ``False`` — opt-in only): after the comparison report is written,
    run the deploy harness over the same batch root (``startd8 deploy batch``), producing
    ``deploy-report.{json,md}`` joined to the comparison by verbatim model id. Off by default
    because it creates throwaway venvs, pip-installs each app, and boots untrusted generated code.
    """
    models = list(dict.fromkeys(models))  # de-dupe, preserve order
    seed = seed.resolve()
    source_root = source_root.resolve()
    batch_id = (
        f"model-comparison-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    batch_root = batch_root.resolve() if batch_root else (Path.cwd() / "out" / batch_id)

    log(
        f"Batch: {batch_id}\nSeed: {seed}\nModels ({len(models)}): {', '.join(models)}\n"
        f"Isolation: {isolation} | Batch root: {batch_root}\n"
    )

    if dry_run:
        for model in models:
            wd = batch_root / slug(model) / "workdir"
            out = batch_root / slug(model) / "output"
            log(f"--- {model} ---")
            log(f"  sandbox: {wd}  (copy of {source_root})")
            log(f"  output : {out}")
            log(
                "  cmd    : "
                + " ".join(build_command(seed, wd, out, model, cost_budget))
            )
        return None

    results: list[dict[str, Any]] = []
    run_logs: list[dict[str, Any]] = []
    for model in models:  # FR-4: strictly serial
        workdir = batch_root / slug(model) / "workdir"
        output = batch_root / slug(model) / "output"
        # M2: fail this model fast (don't silently error) if its sandbox already exists.
        if workdir.exists() and any(workdir.iterdir()):
            msg = f"sandbox already exists and is non-empty: {workdir} (use a fresh batch root)"
            log(f"  {msg}")
            results.append(
                {"model": model, "metrics": extract_metrics(output), "error": msg}
            )
            continue
        output.mkdir(parents=True, exist_ok=True)
        # Drop a verbatim-model sidecar so the deploy harness joins by the true model id, not the
        # lossy directory slug (deploy_harness FR-12 / CRP R1-F6).
        (batch_root / slug(model) / ".model").write_text(model, encoding="utf-8")
        log(f"=== [{model}] materializing sandbox ({isolation}) ===")
        try:
            materialize_sandbox(source_root, workdir, isolation, batch_root=batch_root)
        except (
            Exception
        ) as e:  # noqa: BLE001 — one bad sandbox must not kill the batch (FR-3)
            log(f"  sandbox failed: {e}")
            results.append(
                {"model": model, "metrics": extract_metrics(output), "error": str(e)}
            )
            continue

        log(f"=== [{model}] running prime contractor ===")
        rec = run_command(
            build_command(seed, workdir, output, model, cost_budget),
            SDK_ROOT,
            timeout=per_run_timeout,
        )
        rec["model"] = model
        run_logs.append(rec)
        log(
            f"  exit={rec['returncode']}  {rec['duration_seconds']:.1f}s"
            + ("  [TIMED OUT]" if rec["timed_out"] else "")
        )

        metrics = extract_metrics(output)
        if metrics["total_cost"] is None:  # S5 fallback
            db_cost = cost_from_db(rec["start_ts"], rec["end_ts"])
            if db_cost is not None:
                metrics["total_cost"] = db_cost
                metrics["cost_source"] = "cost_db_window"
                metrics["cost_per_succeeded_feature"] = _safe_div(
                    db_cost, metrics["succeeded"]
                )
        # Determinism-boundary signal: did the model drift the $0-generated spine? (no-op
        # for non-backend-codegen targets — returns None when there's no prisma/schema.prisma)
        metrics.update(check_spine_in_sync(workdir, log) or {})
        results.append(
            {"model": model, "metrics": metrics, "returncode": rec["returncode"]}
        )

    ranked = rank_models(results)
    payload = {
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": str(seed),
        "source_root": str(source_root),
        "isolation": isolation,
        "ranked": ranked,
        "run_logs": [
            {
                k: (v.isoformat() if isinstance(v, datetime) else v)
                for k, v in rec.items()
            }
            for rec in run_logs
        ],
    }
    batch_root.mkdir(parents=True, exist_ok=True)
    (batch_root / "comparison-report.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    md = build_markdown(payload)
    (batch_root / "comparison-report.md").write_text(md, encoding="utf-8")
    log("\n" + md)
    log(f"Report: {batch_root / 'comparison-report.md'}")

    if deploy_after:
        _deploy_after(batch_root, log)
    return payload


def _deploy_after(batch_root: Path, log: Callable[[str], None]) -> None:
    """Opt-in: run the deploy harness over the just-written batch (UNTRUSTED code — see flag doc)."""
    log("\n=== deploy harness (deploy_after=True) ===")
    try:
        from startd8.deploy_harness import deploy_batch

        report = deploy_batch(batch_root, join=True)
    except (
        Exception
    ) as exc:  # noqa: BLE001 — never let deploy failure mask the comparison result
        log(f"  deploy harness failed (non-fatal): {exc}")
        return
    ru = report.get("rollup", {}).get("passed", {})
    log(
        f"  deployed {report.get('app_count', 0)} app(s) — "
        f"boot:{ru.get('boot', 0)} health:{ru.get('health', 0)} smoke:{ru.get('smoke', 0)} passed"
    )
    log(f"  Deploy report: {batch_root / 'deploy-report.md'}")
