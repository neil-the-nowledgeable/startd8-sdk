#!/usr/bin/env python3
"""Prime Contractor multi-model comparison harness (v1).

Runs the SAME seed (requirements + plan) through PrimeContractorWorkflow once per model,
each in a fully isolated working-tree copy + output dir, SERIALLY, then scores each run from
the artifacts the workflow already produces and emits a ranked capability+cost report.

Design: docs/design/PRIME_MODEL_COMPARISON_REQUIREMENTS.md (v0.2) +
        docs/design/PRIME_MODEL_COMPARISON_PLAN.md (v1.0).

Model pinning (FR-7): sets --lead-agent AND --drafter-agent to the model under test and does
NOT enable complexity-routing / micro-prime (both opt-in, off by default), so 100% of
generation flows through the pinned model.

Isolation (FR-1): each model gets its own project-root copy because a prime run merges generated
code into project_root and writes resume/cache state there.

Usage:
    python3 scripts/run_prime_model_comparison.py \\
        --seed out/proj/plan-ingestion/prime-context-seed.json \\
        --source-root /path/to/target/project \\
        --model anthropic:claude-opus-4-8 \\
        --model openai:gpt-5.5 \\
        --batch-root out/model-comparison \\
        --cost-budget 5.00
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories never copied into a per-model sandbox (heavy / run-specific state).
SANDBOX_IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "venv", ".startd8", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", "build", "dist", "*.egg-info", ".tox",
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
        # Requires source_root to be a git repo. Detached worktree at HEAD (L2).
        subprocess.run(
            ["git", "-C", str(source_root), "worktree", "add", "--detach", str(workdir)],
            check=True, capture_output=True, text=True,
        )
    else:  # copy
        shutil.copytree(
            source_root, workdir,
            ignore=_ignore_factory(source_root, batch_root), dirs_exist_ok=False,
        )


# --------------------------------------------------------------------------- invocation (S3)

def build_command(
    seed: Path, workdir: Path, output: Path, model: str, cost_budget: Optional[float]
) -> list[str]:
    """Per-model prime workflow command with the model pinned (FR-5/6/7/8)."""
    cmd = [
        "python3", "scripts/run_prime_workflow.py",
        "--seed", str(seed),                  # FR-5: same seed, never mutated
        "--project-root", str(workdir),       # FR-1: isolated copy
        "--output-dir", str(output),
        "--lead-agent", model,                # FR-7: pin both generation paths
        "--drafter-agent", model,
        "--force-regenerate",                 # FR-8: no Mottainai reuse
    ]
    # Intentionally NOT passing --complexity-routing / --micro-prime (off by default).
    if cost_budget is not None:
        cmd += ["--cost-budget", str(cost_budget)]
    return cmd


def run_command(cmd: list[str], cwd: Path, timeout: Optional[float] = None) -> dict[str, Any]:
    """Run one model's workflow. A timeout marks the run failed but never wedges the batch (M1)."""
    started = time.monotonic()
    start_ts = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=timeout
        )
        returncode, stdout, stderr, timed_out = proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as e:
        returncode, timed_out = 124, True
        stdout = e.stdout or "" if isinstance(e.stdout, str) else ""
        stderr = (e.stderr or "" if isinstance(e.stderr, str) else "") + f"\n[timed out after {timeout}s]"
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

    features = postmortem.get("features", []) or []
    disk_scores = [f.get("disk_quality_score") for f in features]
    mean_disk = _mean(disk_scores)
    semantic_errors = sum(int(f.get("semantic_error_count", 0) or 0) for f in features)

    # Cost: prefer the postmortem's own per-run summary; DB time-window is the fallback (S5).
    cost_summary = postmortem.get("cost_summary") or {}
    total_cost = cost_summary.get("total_usd")

    return {
        "status": "success" if prime_result.get("success") else "failed",
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "completion_rate": _safe_div(succeeded, processed),
        "mean_disk_quality_score": mean_disk,
        "aggregate_score": postmortem.get("aggregate_score"),
        "avg_assembly_delta": postmortem.get("avg_assembly_delta"),
        "semantic_error_count": semantic_errors,
        "total_cost": total_cost,
        "cost_source": "postmortem" if total_cost is not None else None,
        "cost_per_succeeded_feature": _safe_div(total_cost, succeeded),
        "artifacts_found": bool(prime_result or postmortem),
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
    """Highest mean disk_quality_score wins; tie-break lowest cost-per-succeeded-feature."""
    def key(r: dict[str, Any]):
        m = r["metrics"]
        disk = m.get("mean_disk_quality_score")
        cpsf = m.get("cost_per_succeeded_feature")
        # Missing disk score sorts last regardless of scale (no assumption that scores are >= 0).
        return (
            -(disk if disk is not None else float("-inf")),
            cpsf if cpsf is not None else float("inf"),
        )
    return sorted(results, key=key)


_METRIC_ROWS = [
    ("Status", "status", None),
    ("Processed", "processed", 0),
    ("Succeeded", "succeeded", 0),
    ("Failed", "failed", 0),
    ("Completion rate", "completion_rate", 4),
    ("Mean disk quality", "mean_disk_quality_score", 4),
    ("Aggregate score", "aggregate_score", 4),
    ("Avg assembly delta", "avg_assembly_delta", 4),
    ("Semantic errors", "semantic_error_count", 0),
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
            if places is None:
                cells.append(str(v) if v is not None else "N/A")
            elif places == 0:
                cells.append(str(v) if v is not None else "N/A")
            else:
                cells.append(_fmt(v, places))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "## Verdict", ""]
    winner = ranked[0]
    wm = winner["metrics"]
    lines.append(
        f"**Recommended: `{winner['model']}`** — mean disk quality "
        f"{_fmt(wm.get('mean_disk_quality_score'))}, "
        f"{wm.get('succeeded')}/{wm.get('processed')} features, "
        f"${_fmt(wm.get('total_cost'), 6)} total "
        f"(${_fmt(wm.get('cost_per_succeeded_feature'), 6)}/succeeded feature)."
    )
    incomplete = [r["model"] for r in ranked if not r["metrics"].get("artifacts_found")]
    if incomplete:
        lines += ["", f"> ⚠️ Incomplete (no artifacts / crashed): {', '.join(incomplete)}"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- main

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prime Contractor multi-model comparison (serial).")
    parser.add_argument("--seed", required=True, help="Shared prime-context-seed.json (same for all models).")
    parser.add_argument("--source-root", default=".", help="Target project root to copy per model.")
    parser.add_argument("--model", action="append", dest="models", default=[],
                        help="Model spec provider:model (repeatable, >=2 required).")
    parser.add_argument("--batch-root", default=None, help="Output root for the batch.")
    parser.add_argument("--cost-budget", type=float, default=None, help="Per-run cost budget (USD).")
    parser.add_argument("--per-run-timeout", type=float, default=None,
                        help="Max seconds per model run; on timeout the run is marked failed and "
                             "the batch continues (default: no timeout).")
    parser.add_argument("--isolation", choices=["copy", "worktree"], default="copy",
                        help="copy = full tree incl. dirty files; worktree = git HEAD only.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan; do not copy or execute.")
    args = parser.parse_args(argv)

    models = list(dict.fromkeys(args.models))  # de-dupe, preserve order
    if len(models) < 2:
        print("ERROR: provide >=2 distinct --model specs.", file=sys.stderr)
        return 2

    seed = Path(args.seed).resolve()
    source_root = Path(args.source_root).resolve()
    if not args.dry_run and not seed.is_file():
        print(f"ERROR: seed not found: {seed}", file=sys.stderr)
        return 2

    batch_id = f"model-comparison-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    batch_root = Path(args.batch_root).resolve() if args.batch_root else (REPO_ROOT / "out" / batch_id)

    # H1: a batch root equal to the source root is degenerate (the copy would consume itself).
    if batch_root == source_root:
        print("ERROR: --batch-root must not equal --source-root.", file=sys.stderr)
        return 2

    print(f"Batch: {batch_id}\nSeed: {seed}\nModels ({len(models)}): {', '.join(models)}\n"
          f"Isolation: {args.isolation} | Batch root: {batch_root}\n")

    if args.dry_run:
        for model in models:
            wd = batch_root / slug(model) / "workdir"
            out = batch_root / slug(model) / "output"
            print(f"--- {model} ---")
            print(f"  sandbox: {wd}  (copy of {source_root})")
            print(f"  output : {out}")
            print("  cmd    : " + " ".join(build_command(seed, wd, out, model, args.cost_budget)))
        return 0

    results: list[dict[str, Any]] = []
    run_logs: list[dict[str, Any]] = []
    for model in models:  # FR-4: strictly serial
        sl = slug(model)
        workdir = batch_root / sl / "workdir"
        output = batch_root / sl / "output"
        # M2: fail this model fast (don't silently error) if its sandbox already exists.
        if workdir.exists() and any(workdir.iterdir()):
            msg = f"sandbox already exists and is non-empty: {workdir} (use a fresh --batch-root)"
            print(f"  {msg}", file=sys.stderr)
            results.append({"model": model, "metrics": extract_metrics(output), "error": msg})
            continue
        output.mkdir(parents=True, exist_ok=True)
        print(f"=== [{model}] materializing sandbox ({args.isolation}) ===")
        try:
            materialize_sandbox(source_root, workdir, args.isolation, batch_root=batch_root)
        except Exception as e:  # noqa: BLE001 — one bad sandbox must not kill the batch (FR-3)
            print(f"  sandbox failed: {e}", file=sys.stderr)
            results.append({"model": model, "metrics": extract_metrics(output), "error": str(e)})
            continue

        print(f"=== [{model}] running prime contractor ===")
        log = run_command(
            build_command(seed, workdir, output, model, args.cost_budget),
            REPO_ROOT, timeout=args.per_run_timeout,
        )
        log["model"] = model
        run_logs.append(log)
        print(f"  exit={log['returncode']}  {log['duration_seconds']:.1f}s")

        metrics = extract_metrics(output)
        if metrics["total_cost"] is None:  # S5 fallback
            db_cost = cost_from_db(log["start_ts"], log["end_ts"])
            if db_cost is not None:
                metrics["total_cost"] = db_cost
                metrics["cost_source"] = "cost_db_window"
                metrics["cost_per_succeeded_feature"] = _safe_div(db_cost, metrics["succeeded"])
        results.append({"model": model, "metrics": metrics, "returncode": log["returncode"]})

    ranked = rank_models(results)
    payload = {
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": str(seed),
        "source_root": str(source_root),
        "isolation": args.isolation,
        "ranked": ranked,
        "run_logs": [{k: (v.isoformat() if isinstance(v, datetime) else v)
                      for k, v in log.items()} for log in run_logs],
    }
    batch_root.mkdir(parents=True, exist_ok=True)
    (batch_root / "comparison-report.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md = build_markdown(payload)
    (batch_root / "comparison-report.md").write_text(md, encoding="utf-8")

    print("\n" + md)
    print(f"Report: {batch_root / 'comparison-report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
