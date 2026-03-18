#!/usr/bin/env python3
"""Mine exemplars from existing Prime Contractor runs.

Usage:
    python3 scripts/mine_exemplars.py --scan-dir /path/to/pipeline-output/ [--dry-run] [--stats]

Scans all run directories under --scan-dir for postmortem reports and extracts
exemplars from features scoring >= 1.00.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the project src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from startd8.exemplars.extractor import extract_exemplars_from_run
from startd8.exemplars.registry import ExemplarRegistry


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mine exemplars from existing Prime Contractor runs.",
    )
    parser.add_argument(
        "--scan-dir",
        required=True,
        help="Directory containing run-NNN subdirectories",
    )
    parser.add_argument(
        "--output",
        default="exemplar-registry.json",
        help="Output registry file path (default: exemplar-registry.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be extracted without writing",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print summary statistics",
    )
    parser.add_argument(
        "--project-id",
        default="",
        help="Project ID for the registry",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=1.0,
        help="Minimum requirement_score threshold (default: 1.0)",
    )
    args = parser.parse_args()

    scan_path = Path(args.scan_dir)
    if not scan_path.is_dir():
        print(f"ERROR: {scan_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Load existing registry if present
    output_path = Path(args.output)
    if output_path.is_file() and not args.dry_run:
        registry = ExemplarRegistry.load(output_path)
        print(f"Loaded existing registry: {len(registry)} entries")
    else:
        registry = ExemplarRegistry(project_id=args.project_id)

    # Find run directories (run-NNN pattern or any dir with postmortem)
    run_dirs = sorted(
        d for d in scan_path.iterdir()
        if d.is_dir() and (d / "prime-postmortem-report.json").is_file()
    )

    print(f"Found {len(run_dirs)} runs with postmortem reports")

    total_extracted = 0
    for run_dir in run_dirs:
        if args.dry_run:
            # Peek at postmortem to count passing features
            try:
                report = json.loads(
                    (run_dir / "prime-postmortem-report.json").read_text(encoding="utf-8")
                )
                passing = [
                    f for f in report.get("features", [])
                    if f.get("requirement_score", 0) >= args.min_score
                    and f.get("verdict", "").upper() == "PASS"
                ]
                if passing:
                    print(f"  {run_dir.name}: {len(passing)} passing features")
                    total_extracted += len(passing)
            except (json.JSONDecodeError, OSError) as exc:
                print(f"  {run_dir.name}: ERROR reading postmortem: {exc}")
        else:
            extracted = extract_exemplars_from_run(
                run_dir,
                registry=registry,
                min_requirement_score=args.min_score,
            )
            total_extracted += len(extracted)
            if extracted:
                print(f"  {run_dir.name}: {len(extracted)} exemplars extracted")

    # Auto-promote maturity
    if not args.dry_run and total_extracted > 0:
        promotions = registry.promote_maturity()
        if promotions:
            print(f"\nPromotions: {len(promotions)} entries promoted")
            for p in promotions:
                print(f"  {p['id']}: level {p['old_level']} → {p['new_level']}")

        registry.save(output_path)
        print(f"\nRegistry saved: {output_path} ({len(registry)} total entries)")

    if args.dry_run:
        print(f"\n[DRY RUN] Would extract ~{total_extracted} exemplars")

    if args.stats:
        _print_stats(registry)


def _print_stats(registry: ExemplarRegistry) -> None:
    """Print summary statistics about the registry."""
    if not registry.exemplars:
        print("\nNo exemplars in registry")
        return

    print("\n--- Registry Statistics ---")
    print(f"Total exemplars: {len(registry)}")

    # By fingerprint
    by_fp: dict[str, int] = {}
    by_maturity: dict[int, int] = {}
    by_language: dict[str, int] = {}
    for e in registry.exemplars:
        fp = str(e.fingerprint)
        by_fp[fp] = by_fp.get(fp, 0) + 1
        by_maturity[e.maturity] = by_maturity.get(e.maturity, 0) + 1
        by_language[e.fingerprint.language] = by_language.get(e.fingerprint.language, 0) + 1

    print(f"\nBy maturity level:")
    for level in sorted(by_maturity):
        names = {0: "Candidate", 1: "Validated", 2: "Confirmed", 3: "Invariant", 4: "Template"}
        print(f"  Level {level} ({names.get(level, '?')}): {by_maturity[level]}")

    print(f"\nBy language:")
    for lang, count in sorted(by_language.items(), key=lambda x: -x[1]):
        print(f"  {lang}: {count}")

    print(f"\nBy fingerprint (top 10):")
    for fp, count in sorted(by_fp.items(), key=lambda x: -x[1])[:10]:
        print(f"  {fp}: {count}")


if __name__ == "__main__":
    main()
