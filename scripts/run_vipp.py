#!/usr/bin/env python3
# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""VIPP post-serialize shim (VIPP FR-15 cap-dev-pipe / host hook).

Thin wrapper a host surface or cap-dev-pipe step may call after the host serializes its proposal
inbox, gated on ``STARTD8_VIPP_AUTO_NEGOTIATE=1`` (off by default — no surprise spend; the
deterministic negotiation is $0, but auto-running is still opt-in). Always exits 0 so the hook never
blocks the host; the interactive ``startd8 vipp`` CLI carries the non-zero exit codes for automation.
"""

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="VIPP post-serialize negotiation shim")
    parser.add_argument(
        "--project-root", default=".", help="Project root (default: cwd)."
    )
    args = parser.parse_args()

    if os.environ.get("STARTD8_VIPP_AUTO_NEGOTIATE", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return 0  # opt-in only

    try:
        from startd8.kickoff_experience.vipp_seam import inbox_path
        from startd8.vipp import run_vipp_negotiate

        root = Path(args.project_root)
        ip = inbox_path(root)
        if ip.exists():
            run_vipp_negotiate(ip, project_root=root)
    except Exception as exc:  # never block the host on a VIPP hiccup
        sys.stderr.write(f"run_vipp: skipped ({exc})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
