"""Thin Check forwarder for a prime delivery ledger (CEP-B4).

Forwards ``--req`` / ``--dossier`` / ``--repo`` (+ optional ``--out`` /
``--forward-manifest`` / ``--strict``) to
``dev-os/scripts/reconcile_lives_evidence.py``. No reconcile logic lives here.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def find_reconcile_script() -> Path:
    """Locate the twin-sync reconciler without forking it."""
    env = os.environ.get("DEV_OS_ROOT")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env) / "scripts" / "reconcile_lives_evidence.py")
    here = Path(__file__).resolve()
    # startd8-sdk/src/startd8/contractors → …/Documents/dev/startd8-sdk → sibling dev-os
    for parent in here.parents:
        sibling = parent.parent / "dev-os" / "scripts" / "reconcile_lives_evidence.py"
        candidates.append(sibling)
        nested = parent / "dev-os" / "scripts" / "reconcile_lives_evidence.py"
        candidates.append(nested)
    # Common absolute home used in this corpus
    candidates.append(
        Path.home() / "Documents" / "dev" / "dev-os" / "scripts" / "reconcile_lives_evidence.py"
    )
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    raise FileNotFoundError(
        "reconcile_lives_evidence.py not found; set DEV_OS_ROOT to the dev-os checkout"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Forward prime delivery Check to reconcile_lives_evidence.py (cite-only)."
    )
    parser.add_argument("--req", type=Path, required=True)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--forward-manifest", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    script = find_reconcile_script()
    cmd = [
        sys.executable,
        str(script),
        "--req",
        str(args.req),
        "--dossier",
        str(args.dossier),
        "--repo",
        str(args.repo),
    ]
    if args.out is not None:
        cmd.extend(["--out", str(args.out)])
    if args.forward_manifest is not None:
        cmd.extend(["--forward-manifest", str(args.forward_manifest)])
    if args.strict:
        cmd.append("--strict")
    print(f"cite: {script}", file=sys.stderr)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
