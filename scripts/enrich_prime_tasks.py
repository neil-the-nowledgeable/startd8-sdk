#!/usr/bin/env python3
"""
Enrich a prime YAML with domain constraints via DomainChecklist.

Usage:
    python3 scripts/enrich_prime_tasks.py \
        --input out/autism-policy-prime/plan-ingestion-tasks.yaml \
        --project-root /path/to/target/project \
        --output out/autism-policy-prime/enriched-prime-tasks.yaml
"""

import argparse
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from startd8.utils.prime_task_enrichment import enrich_prime_yaml


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich prime YAML with domain constraints",
    )
    parser.add_argument(
        "--input", required=True, type=Path,
        help="Path to the source prime YAML",
    )
    parser.add_argument(
        "--project-root", required=True, type=Path,
        help="Project root for domain classification",
    )
    parser.add_argument(
        "--output", required=True, type=Path,
        help="Destination for the enriched YAML",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)
    if not args.project_root.is_dir():
        print(f"ERROR: Project root not a directory: {args.project_root}")
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    report = enrich_prime_yaml(args.input, args.project_root, args.output)

    print(f"\nEnrichment Report:")
    print(f"  Total tasks: {report.total_tasks}")
    print(f"  Enriched:    {report.enriched}")
    print(f"  Skipped:     {report.skipped}")
    print(f"  Failed:      {report.failed}")
    if report.errors:
        print(f"\nErrors:")
        for err in report.errors:
            print(f"  - {err}")
    print(f"\nOutput: {args.output}")


if __name__ == "__main__":
    main()
