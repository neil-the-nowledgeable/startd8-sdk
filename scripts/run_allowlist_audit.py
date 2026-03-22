#!/usr/bin/env python3
"""Standalone allowlist audit — reads archived runs and detects stale entries.

Usage:
    python3 scripts/run_allowlist_audit.py \
        --output-dir .cap-dev-pipe/pipeline-output/my-project/run-005/plan-ingestion
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SDK_SRC = _SCRIPT_DIR.parent / "src"
if _SDK_SRC.is_dir():
    sys.path.insert(0, str(_SDK_SRC))

from startd8.security_prime.allowlist_audit import detect_stale_entries, render_allowlist_audit


def _load_archived_allowlist_metrics(output_dir: Path) -> list[dict]:
    """Load allowlist metrics from archived run dirs via kaizen-index.json."""
    index_path = output_dir / "kaizen-index.json"
    if not index_path.is_file():
        return []

    try:
        index = json.loads(index_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    metrics_list = []
    for entry in index.get("runs", []):
        run_dir = output_dir / entry.get("relative_path", "")
        gate_path = run_dir / "security-gate-metrics.json"
        if not gate_path.is_file():
            continue
        try:
            data = json.loads(gate_path.read_text())
            if "allowlist" in data:
                metrics_list.append(data["allowlist"])
        except (json.JSONDecodeError, OSError):
            continue

    return metrics_list


def main() -> None:
    parser = argparse.ArgumentParser(description="Security allowlist audit")
    parser.add_argument(
        "--output-dir", required=True, type=Path,
        help="Run output directory containing kaizen-index.json",
    )
    args = parser.parse_args()

    # Load current run's gate metrics
    current_gate = args.output_dir / "security-gate-metrics.json"
    if not current_gate.is_file():
        print("No security-gate-metrics.json found.")
        return

    try:
        data = json.loads(current_gate.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Failed to load gate metrics: {exc}")
        return

    current_allowlist = data.get("allowlist", {})
    if not current_allowlist:
        print("No allowlist section in gate metrics.")
        return

    archived = _load_archived_allowlist_metrics(args.output_dir)
    stale = detect_stale_entries(current_allowlist, archived)
    audit = render_allowlist_audit(current_allowlist, stale)
    print(audit)


if __name__ == "__main__":
    main()
