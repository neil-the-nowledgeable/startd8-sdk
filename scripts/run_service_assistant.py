#!/usr/bin/env python3
"""Service Assistant post-run shim.

Thin wrapper the cap-dev-pipe scripts call after the post-mortem step. Delegates to
``startd8.service_assistant`` to detect the completed/aborted run, synthesize a triage
report, notify the SDK (EventBus), and write the authoritative triage artifact.

Always exits 0 so the post-run hook never blocks the pipeline (the triage artifact is
the deliverable; failures here are logged, not fatal).

Usage:
    python3 scripts/run_service_assistant.py --output-dir <run-dir> [--run-id ID]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Service Assistant post-run shim")
    parser.add_argument("--output-dir", required=True, help="Run output dir to scan")
    parser.add_argument("--run-id", default=None, help="Explicit run id (else auto-resolved)")
    parser.add_argument("--sdk-root", default=None, help="SDK root to add to sys.path")
    parser.add_argument("--no-emit", action="store_true", help="Skip EventBus emission")
    args = parser.parse_args()

    if args.sdk_root:
        sys.path.insert(0, str(Path(args.sdk_root) / "src"))

    try:
        from startd8.service_assistant import run_service_assistant
    except ImportError as exc:  # pragma: no cover - environment issue
        print(f"[service-assistant] SDK import failed, skipping: {exc}", file=sys.stderr)
        return 0

    try:
        report = run_service_assistant(
            Path(args.output_dir), run_id=args.run_id, emit=not args.no_emit
        )
    except Exception as exc:  # pragma: no cover - never block the pipeline
        print(f"[service-assistant] triage failed, skipping: {exc}", file=sys.stderr)
        return 0

    if report is None:
        print("[service-assistant] nothing new to triage (or already processed)")
    else:
        print(f"[service-assistant] {report.summary.headline}")
        if report.summary.top_recommendation:
            print(f"[service-assistant]   -> {report.summary.top_recommendation}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
