#!/usr/bin/env python3
"""Run fixed-seed Artisan vs Prime parity benchmark and emit report artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _safe_rate(num: float | int, den: float | int) -> float | None:
    if den <= 0:
        return None
    return float(num) / float(den)


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def _latest_match(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def _run_command(cmd: list[str], cwd: Path) -> dict[str, Any]:
    started = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "duration_seconds": time.monotonic() - started,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-20:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-20:]),
    }


def _extract_artisan_metrics(output_dir: Path) -> dict[str, Any]:
    workflow_result_path = _latest_match(output_dir, "workflow-result*.json")
    workflow_result = _load_json(workflow_result_path) if workflow_result_path else None
    report_path = output_dir / "workflow-execution-report.json"
    report = _load_json(report_path)

    task_count = None
    review_pass_rate = None
    failed_task_rate = None
    truncation_incidence = None
    if report:
        task_count = report.get("task_count")
        review_summary = report.get("review_summary", {})
        passed = review_summary.get("total_passed", 0)
        failed = review_summary.get("total_failed", 0)
        review_pass_rate = _safe_rate(passed, passed + failed)
        failed_task_rate = _safe_rate(report.get("tasks_failed", 0), task_count or 0)
        trunc_summary = report.get("truncation_summary", {})
        truncation_incidence = _safe_rate(
            trunc_summary.get("tasks_flagged", 0),
            task_count or 0,
        )

    design_agreement_rate = None
    handoff_path_candidates = [
        output_dir / "design-handoff.json",
        output_dir / "design_handoff.json",
    ]
    handoff = None
    for candidate in handoff_path_candidates:
        handoff = _load_json(candidate)
        if handoff:
            break
    if handoff:
        design_results = handoff.get("design_results", {})
        evaluated = 0
        agreed = 0
        for entry in design_results.values():
            if not isinstance(entry, dict):
                continue
            status = entry.get("status")
            if status in ("dry_run_skipped", "env_blocked"):
                continue
            evaluated += 1
            if entry.get("agreed"):
                agreed += 1
        design_agreement_rate = _safe_rate(agreed, evaluated)

    return {
        "workflow_result_path": str(workflow_result_path) if workflow_result_path else None,
        "report_path": str(report_path) if report else None,
        "status": workflow_result.get("status") if workflow_result else None,
        "task_count": task_count,
        "review_pass_rate": review_pass_rate,
        "failed_task_rate": failed_task_rate,
        "design_agreement_rate": design_agreement_rate,
        "truncation_incidence": truncation_incidence,
    }


def _extract_prime_metrics(output_dir: Path) -> dict[str, Any]:
    prime_result_path = _latest_match(output_dir, "prime-result*.json")
    prime_result = _load_json(prime_result_path) if prime_result_path else None

    if not prime_result:
        return {
            "workflow_result_path": None,
            "status": None,
            "task_count": None,
            "review_pass_rate": None,
            "failed_task_rate": None,
            "design_agreement_rate": None,
            "truncation_incidence": None,
        }

    processed = int(prime_result.get("processed", 0) or 0)
    succeeded = int(prime_result.get("succeeded", 0) or 0)
    failed = int(prime_result.get("failed", 0) or 0)
    # Prime workflow exposes end-state counters; treat succeeded/processed as
    # pass-rate proxy for parity tracking in this harness.
    review_pass_rate = _safe_rate(succeeded, processed)
    failed_task_rate = _safe_rate(failed, processed)

    return {
        "workflow_result_path": str(prime_result_path),
        "status": "success" if prime_result.get("success") else "failed",
        "task_count": processed,
        "review_pass_rate": review_pass_rate,
        "failed_task_rate": failed_task_rate,
        "design_agreement_rate": None,
        "truncation_incidence": None,
    }


def _mean(values: list[float | None]) -> float | None:
    filtered = [v for v in values if v is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _build_markdown_report(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Prime-Parity Benchmark Report")
    lines.append("")
    lines.append(f"- Suite ID: `{payload['suite_id']}`")
    lines.append(f"- Suite Version: `{payload['suite_version']}`")
    lines.append(f"- Generated At (UTC): `{payload['generated_at']}`")
    lines.append("")
    lines.append("## Per-Seed Comparison")
    lines.append("")
    lines.append("| Seed | Complexity | A Review Pass | P Review Pass | Delta | A Failed Rate | P Failed Rate | Delta | A Design Agree | P Design Agree | Delta | A Truncation | P Truncation | Delta |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in payload["rows"]:
        lines.append(
            "| {seed} | {complexity} | {a_rp} | {p_rp} | {d_rp} | {a_fr} | {p_fr} | {d_fr} | {a_da} | {p_da} | {d_da} | {a_ti} | {p_ti} | {d_ti} |".format(
                seed=row["seed_id"],
                complexity=row["complexity"],
                a_rp=_fmt_rate(row["artisan"]["review_pass_rate"]),
                p_rp=_fmt_rate(row["prime"]["review_pass_rate"]),
                d_rp=_fmt_rate(row["delta"]["review_pass_rate"]),
                a_fr=_fmt_rate(row["artisan"]["failed_task_rate"]),
                p_fr=_fmt_rate(row["prime"]["failed_task_rate"]),
                d_fr=_fmt_rate(row["delta"]["failed_task_rate"]),
                a_da=_fmt_rate(row["artisan"]["design_agreement_rate"]),
                p_da=_fmt_rate(row["prime"]["design_agreement_rate"]),
                d_da=_fmt_rate(row["delta"]["design_agreement_rate"]),
                a_ti=_fmt_rate(row["artisan"]["truncation_incidence"]),
                p_ti=_fmt_rate(row["prime"]["truncation_incidence"]),
                d_ti=_fmt_rate(row["delta"]["truncation_incidence"]),
            )
        )
    lines.append("")
    lines.append("## Aggregate Summary")
    lines.append("")
    agg = payload["aggregate"]
    lines.append(f"- Artisan average review pass rate: `{_fmt_rate(agg['artisan_avg_review_pass'])}`")
    lines.append(f"- Prime average review pass rate: `{_fmt_rate(agg['prime_avg_review_pass'])}`")
    lines.append(f"- Artisan average failed-task rate: `{_fmt_rate(agg['artisan_avg_failed_rate'])}`")
    lines.append(f"- Prime average failed-task rate: `{_fmt_rate(agg['prime_avg_failed_rate'])}`")
    lines.append(f"- Artisan average design agreement rate: `{_fmt_rate(agg['artisan_avg_design_agreement'])}`")
    lines.append(f"- Prime average design agreement rate: `{_fmt_rate(agg['prime_avg_design_agreement'])}`")
    lines.append(f"- Artisan average truncation incidence: `{_fmt_rate(agg['artisan_avg_truncation'])}`")
    lines.append(f"- Prime average truncation incidence: `{_fmt_rate(agg['prime_avg_truncation'])}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run fixed-seed Prime vs Artisan parity benchmark.",
    )
    parser.add_argument(
        "--suite",
        default="scripts/benchmarks/prime_parity_seed_suite.json",
        help="Path to fixed-seed suite JSON.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for benchmark artifacts (default: out/prime-parity-benchmark-<timestamp>).",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute workflows before summarizing results.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    suite_path = (repo_root / args.suite).resolve() if not Path(args.suite).is_absolute() else Path(args.suite)
    suite = _load_json(suite_path)
    if not suite:
        print(f"Failed to load suite JSON: {suite_path}", file=sys.stderr)
        return 2

    out_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else (repo_root / "out" / f"prime-parity-benchmark-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    run_logs: list[dict[str, Any]] = []
    for seed in suite.get("seeds", []):
        seed_id = seed["id"]
        complexity = seed.get("complexity", "unknown")
        project_root = (repo_root / seed.get("project_root", ".")).resolve()
        artisan_seed = (repo_root / seed["artisan_seed"]).resolve()
        prime_seed = (repo_root / seed.get("prime_seed", seed["artisan_seed"])).resolve()
        seed_out = out_dir / seed_id
        artisan_out = seed_out / "artisan"
        prime_out = seed_out / "prime"
        artisan_out.mkdir(parents=True, exist_ok=True)
        prime_out.mkdir(parents=True, exist_ok=True)

        if args.run:
            artisan_cmd = [
                "python3",
                "scripts/run_artisan_workflow.py",
                "--seed",
                str(artisan_seed),
                "--project-root",
                str(project_root),
                "--output-dir",
                str(artisan_out),
            ]
            prime_cmd = [
                "python3",
                "scripts/run_prime_workflow.py",
                "--seed",
                str(prime_seed),
                "--project-root",
                str(project_root),
                "--output-dir",
                str(prime_out),
            ]
            if seed.get("artisan_task_filter"):
                artisan_cmd += ["--task-filter", ",".join(seed["artisan_task_filter"])]
            if seed.get("prime_task_filter"):
                prime_cmd += ["--task-filter", ",".join(seed["prime_task_filter"])]

            run_logs.append({"seed_id": seed_id, "route": "artisan", **_run_command(artisan_cmd, repo_root)})
            run_logs.append({"seed_id": seed_id, "route": "prime", **_run_command(prime_cmd, repo_root)})

        artisan_metrics = _extract_artisan_metrics(artisan_out)
        prime_metrics = _extract_prime_metrics(prime_out)
        row = {
            "seed_id": seed_id,
            "complexity": complexity,
            "artisan": artisan_metrics,
            "prime": prime_metrics,
            "delta": {
                "review_pass_rate": _delta(
                    artisan_metrics["review_pass_rate"],
                    prime_metrics["review_pass_rate"],
                ),
                "failed_task_rate": _delta(
                    artisan_metrics["failed_task_rate"],
                    prime_metrics["failed_task_rate"],
                ),
                "design_agreement_rate": _delta(
                    artisan_metrics["design_agreement_rate"],
                    prime_metrics["design_agreement_rate"],
                ),
                "truncation_incidence": _delta(
                    artisan_metrics["truncation_incidence"],
                    prime_metrics["truncation_incidence"],
                ),
            },
        }
        rows.append(row)

    aggregate = {
        "artisan_avg_review_pass": _mean([r["artisan"]["review_pass_rate"] for r in rows]),
        "prime_avg_review_pass": _mean([r["prime"]["review_pass_rate"] for r in rows]),
        "artisan_avg_failed_rate": _mean([r["artisan"]["failed_task_rate"] for r in rows]),
        "prime_avg_failed_rate": _mean([r["prime"]["failed_task_rate"] for r in rows]),
        "artisan_avg_design_agreement": _mean([r["artisan"]["design_agreement_rate"] for r in rows]),
        "prime_avg_design_agreement": _mean([r["prime"]["design_agreement_rate"] for r in rows]),
        "artisan_avg_truncation": _mean([r["artisan"]["truncation_incidence"] for r in rows]),
        "prime_avg_truncation": _mean([r["prime"]["truncation_incidence"] for r in rows]),
    }

    payload = {
        "suite_id": suite.get("suite_id", "unknown"),
        "suite_version": suite.get("suite_version", "unknown"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed_count": len(rows),
        "rows": rows,
        "aggregate": aggregate,
        "run_logs": run_logs,
    }

    json_path = out_dir / "prime-parity-benchmark.json"
    md_path = out_dir / "prime-parity-benchmark.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_build_markdown_report(payload), encoding="utf-8")

    print(f"Wrote benchmark JSON: {json_path}")
    print(f"Wrote benchmark report: {md_path}")
    if args.run and any(log["returncode"] != 0 for log in run_logs):
        print("One or more workflow runs failed; see run_logs in benchmark JSON.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
