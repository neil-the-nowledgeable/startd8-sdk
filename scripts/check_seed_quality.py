#!/usr/bin/env python3
"""Kaizen seed quality gate check for cap-dev-pipe integration.

Reads ``_ingestion_quality`` from an artisan context seed file and checks
the seed quality score against a configurable threshold.

Exit codes:
    0 — quality OK (score >= threshold)
    1 — quality below threshold (prints warning details)
    2 — file not found or unreadable

Usage::

    python3 scripts/check_seed_quality.py artisan-context-seed.json
    python3 scripts/check_seed_quality.py artisan-context-seed.json --threshold 0.7
    python3 scripts/check_seed_quality.py artisan-context-seed.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def check_seed_quality(
    seed_path: Path,
    threshold: float = 0.5,
) -> tuple[bool, float, List[str]]:
    """Check seed quality score against threshold.

    Returns:
        (passes, score, warnings)
    """
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    quality: Dict[str, Any] = data.get("_ingestion_quality", {})
    score = float(quality.get("seed_quality_score", 1.0))
    warnings = quality.get("field_coverage_warnings", [])
    return score >= threshold, score, warnings


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check artisan context seed quality score",
    )
    parser.add_argument(
        "seed_file", type=Path,
        help="Path to artisan-context-seed.json",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.5,
        help="Minimum acceptable seed quality score (default: 0.5)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args(argv)

    if not args.seed_file.is_file():
        print(f"Error: {args.seed_file} not found", file=sys.stderr)
        return 2

    try:
        passes, score, warnings = check_seed_quality(args.seed_file, args.threshold)
    except (OSError, json.JSONDecodeError, TypeError) as err:
        print(f"Error reading seed: {err}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "passes": passes,
            "score": score,
            "threshold": args.threshold,
            "warnings": warnings,
        }, indent=2))
    else:
        status = "OK" if passes else "WARN"
        print(f"{status}|{score:.2f}|{';'.join(warnings)}")

    return 0 if passes else 1


if __name__ == "__main__":
    sys.exit(main())
