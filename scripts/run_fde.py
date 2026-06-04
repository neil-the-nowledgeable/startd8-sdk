#!/usr/bin/env python3
# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Forward Deployed Engineer post-run shim (FR-1 / FR-27 cap-dev-pipe hook).

Thin wrapper the cap-dev-pipe scripts may call after the Service Assistant step, gated on
``STARTD8_FDE_AFTER_ASSIST=1`` (off by default — no surprise spend). Always exits 0 so the
post-run hook never blocks the pipeline; the interactive ``startd8 fde`` CLI carries the
non-zero exit codes for automation that wants them.
"""

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Forward Deployed Engineer post-run shim"
    )
    parser.add_argument("--output-dir", required=True, help="Run output dir to explain")
    parser.add_argument(
        "--project-root", default=None, help="Project root for .startd8/fde/"
    )
    parser.add_argument("--sdk-root", default=None, help="SDK root to add to sys.path")
    parser.add_argument("--no-emit", action="store_true", help="Skip EventBus emission")
    args = parser.parse_args()

    if os.environ.get("STARTD8_FDE_AFTER_ASSIST", "0") != "1":
        print("[fde] STARTD8_FDE_AFTER_ASSIST!=1 — skipped (opt-in hook).")
        return 0

    if args.sdk_root:
        sys.path.insert(0, str(Path(args.sdk_root) / "src"))

    try:
        from startd8.fde import run_fde_explain
    except ImportError as exc:
        print(f"[fde] SDK import failed, skipping: {exc}", file=sys.stderr)
        return 0

    try:
        outcome = run_fde_explain(
            Path(args.output_dir),
            project_root=Path(args.project_root) if args.project_root else None,
            emit=not args.no_emit,
        )
    except Exception as exc:  # never block the pipeline
        print(f"[fde] explain failed, skipping: {exc}", file=sys.stderr)
        return 0

    exp = outcome.explanation
    print(
        f"[fde] explained {exp.run_id}: {len(exp.failures)} failure(s) → {outcome.report_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
