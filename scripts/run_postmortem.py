#!/usr/bin/env python3
"""
Standalone post-mortem evaluation for existing artisan workflow results.

Re-runs the post-mortem evaluator without re-executing the workflow.
Useful for iterating on scoring rules or running LLM judge after an
initial rules-only evaluation.

Usage:
    python3 scripts/run_postmortem.py \\
        --seed out/run-1/artisan-context-seed-enriched.json \\
        --result out/run-1/workflow-result.json \\
        --output-dir out/run-1

    # With LLM judge:
    python3 scripts/run_postmortem.py \\
        --seed out/run-1/artisan-context-seed-enriched.json \\
        --result out/run-1/workflow-result.json \\
        --output-dir out/run-1 \\
        --postmortem-llm anthropic:claude-haiku-4-5-20251001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the SDK is importable (dev mode — installed editable is preferred)
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run post-mortem evaluation on existing artisan workflow results",
    )
    parser.add_argument(
        "--seed", required=True,
        help="Path to the enriched context seed JSON file",
    )
    parser.add_argument(
        "--result", required=True,
        help="Path to the workflow-result JSON file",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Output directory for postmortem reports",
    )
    parser.add_argument(
        "--context", default=None,
        help="Path to a context JSON file with generation_results/test_results/review_results",
    )
    parser.add_argument(
        "--postmortem-llm", default=None,
        help="Agent spec for LLM-as-judge (e.g., anthropic:claude-haiku-4-5-20251001)",
    )
    parser.add_argument(
        "--walkthrough", action="store_true",
        help="Also run walkthrough prompt-quality post-mortem.",
    )
    parser.add_argument(
        "--walkthrough-root", default=None,
        help=(
            "Path to walkthrough prompt directory "
            "(defaults to <project-root>/.startd8/walkthrough)."
        ),
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    import logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from startd8.contractors.postmortem import (  # noqa: E402
        PostMortemEvaluator,
        WalkthroughPromptEvaluator,
    )

    # Load seed
    seed_path = Path(args.seed)
    if not seed_path.exists():
        print(f"ERROR: Seed file not found: {seed_path}", file=sys.stderr)
        return 1

    with open(seed_path, "r", encoding="utf-8") as fh:
        seed_data = json.load(fh)
    seed_tasks = seed_data.get("tasks", [])

    # Load workflow result
    result_path = Path(args.result)
    if not result_path.exists():
        print(f"ERROR: Result file not found: {result_path}", file=sys.stderr)
        return 1

    with open(result_path, "r", encoding="utf-8") as fh:
        workflow_result = json.load(fh)

    # Load optional context
    context: dict = {}
    if args.context:
        ctx_path = Path(args.context)
        if ctx_path.exists():
            with open(ctx_path, "r", encoding="utf-8") as fh:
                context = json.load(fh)

    evaluator = PostMortemEvaluator(
        use_llm_judge=bool(args.postmortem_llm),
        judge_agent_spec=args.postmortem_llm,
    )

    report = evaluator.evaluate(
        seed_tasks=seed_tasks,
        workflow_result=workflow_result,
        context=context,
        output_dir=args.output_dir,
    )

    print(f"\nPost-Mortem Evaluation Complete")
    print(f"  Verdict:  {report.aggregate_verdict} (score: {report.aggregate_score:.2f})")
    print(f"  Tasks:    {report.tasks_evaluated}/{report.total_tasks} evaluated")
    print(f"  Method:   {report.method}")
    if report.lessons:
        print(f"  Lessons:  {len(report.lessons)} extracted")
    print(f"  Output:   {args.output_dir}")

    if args.walkthrough:
        default_root = Path(args.output_dir).resolve().parent / ".startd8" / "walkthrough"
        walkthrough_root = Path(args.walkthrough_root).resolve() if args.walkthrough_root else default_root
        wt_eval = WalkthroughPromptEvaluator()
        wt_report = wt_eval.evaluate(
            seed_tasks=seed_tasks,
            walkthrough_root=str(walkthrough_root),
            workflow_result=workflow_result,
            output_dir=args.output_dir,
        )
        print("\nWalkthrough Prompt Post-Mortem Complete")
        print(
            "  Verdict:  "
            f"{wt_report.aggregate_verdict} (score: {wt_report.aggregate_score:.2f})"
        )
        print(f"  Tasks:    {wt_report.tasks_evaluated}/{wt_report.total_tasks} evaluated")
        print(f"  Root:     {walkthrough_root}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
