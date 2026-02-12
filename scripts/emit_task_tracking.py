#!/usr/bin/env python3
"""
Emit ContextCore task tracking artifacts from an existing artisan-context-seed.json.

Usage:
    python3 scripts/emit_task_tracking.py \
        --seed out/manifest-generate-ingestion/artisan-context-seed.json \
        --project-id wayfinder-manifest-generate \
        --sprint-id sprint-1 \
        --install
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from startd8.workflows.builtin.plan_ingestion_models import (
    ComplexityScore,
    ContractorRoute,
    ParsedFeature,
    ParsedPlan,
    TaskTrackingConfig,
)
from startd8.workflows.builtin.task_tracking_emitter import emit_task_tracking_artifacts


def _load_seed(seed_path: Path) -> dict:
    with open(seed_path, encoding="utf-8") as f:
        return json.load(f)


def _reconstruct_parsed_plan(seed: dict) -> ParsedPlan:
    """Reconstruct ParsedPlan from a context seed dict."""
    plan_data = seed.get("plan", {})
    features = []
    for f in plan_data.get("features", []):
        features.append(ParsedFeature(
            feature_id=f.get("feature_id", ""),
            name=f.get("name", ""),
            description=f.get("description", ""),
            target_files=f.get("target_files", []),
            dependencies=f.get("dependencies", []),
            estimated_loc=f.get("estimated_loc", 0),
            labels=f.get("labels", []),
        ))
    return ParsedPlan(
        title=plan_data.get("title", "Untitled"),
        goals=plan_data.get("goals", []),
        features=features,
        dependency_graph=plan_data.get("dependency_graph", {}),
        mentioned_files=plan_data.get("mentioned_files", []),
    )


def _reconstruct_complexity(seed: dict) -> ComplexityScore:
    """Reconstruct ComplexityScore from a context seed dict."""
    cx = seed.get("complexity", {})
    dims = cx.get("dimensions", {})
    route_str = cx.get("route")
    return ComplexityScore(
        composite=cx.get("composite", 0),
        feature_count=dims.get("feature_count", 0),
        cross_file_deps=dims.get("cross_file_deps", 0),
        api_surface=dims.get("api_surface", 0),
        test_complexity=dims.get("test_complexity", 0),
        integration_depth=dims.get("integration_depth", 0),
        domain_novelty=dims.get("domain_novelty", 0),
        ambiguity=dims.get("ambiguity", 0),
        reasoning=cx.get("reasoning", ""),
        route=ContractorRoute(route_str) if route_str else None,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Emit ContextCore task tracking artifacts from an artisan-context-seed.json",
    )
    parser.add_argument(
        "--seed", required=True, type=Path,
        help="Path to artisan-context-seed.json",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Output directory (default: same as seed file parent)",
    )
    parser.add_argument("--project-id", default=None, help="Project ID override")
    parser.add_argument("--project-name", default=None, help="Project name override")
    parser.add_argument("--sprint-id", default=None, help="Sprint ID")
    parser.add_argument(
        "--install", action="store_true",
        help="Install to ~/.contextcore/state/<project-id>/",
    )
    parser.add_argument(
        "--no-ndjson", action="store_true",
        help="Skip NDJSON event log generation",
    )

    args = parser.parse_args()

    seed_path = args.seed.expanduser().resolve()
    if not seed_path.exists():
        print(f"Error: seed file not found: {seed_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = (args.output_dir or seed_path.parent).expanduser().resolve()

    print(f"Seed:      {seed_path}")
    print(f"Output:    {output_dir}")

    seed = _load_seed(seed_path)
    parsed_plan = _reconstruct_parsed_plan(seed)
    complexity = _reconstruct_complexity(seed)
    tasks = seed.get("tasks", [])

    print(f"Plan:      {parsed_plan.title}")
    print(f"Features:  {len(parsed_plan.features)}")
    print(f"Tasks:     {len(tasks)}")

    tracking_config = TaskTrackingConfig(
        project_id=args.project_id,
        project_name=args.project_name,
        sprint_id=args.sprint_id,
        install_to_contextcore=args.install,
        emit_ndjson_events=not args.no_ndjson,
    )

    result = emit_task_tracking_artifacts(
        parsed_plan, complexity, tasks, tracking_config, output_dir,
    )

    print(f"\nGenerated {result['state_file_count']} state files")
    print(f"  Project:  {result['project_id']}")
    print(f"  Trace:    {result['trace_id']}")
    print(f"  Dir:      {result['tasks_dir']}")
    if result.get("ndjson_path"):
        print(f"  NDJSON:   {result['ndjson_path']}")
    if result.get("installed_to"):
        print(f"  Installed: {result['installed_to']}")


if __name__ == "__main__":
    main()
