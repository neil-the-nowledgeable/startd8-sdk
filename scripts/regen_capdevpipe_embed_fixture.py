#!/usr/bin/env python3
"""Regenerate the curated cap-dev-pipe embed set from the canonical source (FR-5 / D-10, S9).

The embed set in ``startd8.capdevpipe_installer.EMBED_SCRIPTS`` is a curated subset sourced
from the ``ln -s $CAP_DEV_PIPE/<name>`` block in cap-dev-pipe's ``CLAUDE.md``. When that
canonical list legitimately changes, the golden-fixture test
(``tests/unit/capdevpipe/test_embed_set.py``) fails loudly. This helper parses the live
``CLAUDE.md`` and prints the current canonical list plus a ready-to-paste ``EMBED_SCRIPTS``
tuple, and diffs it against the in-code constant so the change can be reviewed in the PR.

Usage::

    python3 scripts/regen_capdevpipe_embed_fixture.py [--source /path/to/cap-dev-pipe]

This does not edit any file — it only reports. Update ``EMBED_SCRIPTS`` (and the test's
``GOLDEN_SCRIPTS``) by hand from the printed tuple so the diff is explicit.
"""

import argparse
import sys
from pathlib import Path

# Import from the installed package; fall back to the local src/ tree when run in-repo.
try:
    from startd8.capdevpipe_installer import (
        DEFAULT_SOURCE,
        EMBED_SCRIPTS,
        parse_canonical_embed_scripts,
    )
except ImportError:  # pragma: no cover - dev convenience when not pip-installed
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from startd8.capdevpipe_installer import (
        DEFAULT_SOURCE,
        EMBED_SCRIPTS,
        parse_canonical_embed_scripts,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"cap-dev-pipe checkout (default: {DEFAULT_SOURCE})",
    )
    args = parser.parse_args()

    claude_md = args.source / "CLAUDE.md"
    if not claude_md.is_file():
        print(
            f"ERROR: {claude_md} not found — is --source a cap-dev-pipe checkout?",
            file=sys.stderr,
        )
        return 2

    canonical = parse_canonical_embed_scripts(claude_md.read_text(encoding="utf-8"))
    if not canonical:
        print(
            f"ERROR: no `ln -s $CAP_DEV_PIPE/...` block parsed from {claude_md}",
            file=sys.stderr,
        )
        return 2

    current = list(EMBED_SCRIPTS)
    added = [s for s in canonical if s not in current]
    removed = [s for s in current if s not in canonical]

    print(
        f"# Canonical embed scripts parsed from {claude_md} ({len(canonical)} entries):"
    )
    print("EMBED_SCRIPTS = (")
    for name in canonical:
        print(f'    "{name}",')
    print(")")
    print()

    if not added and not removed:
        print(
            "OK: EMBED_SCRIPTS already matches the canonical source. No change needed."
        )
        return 0

    print("DRIFT detected vs startd8.capdevpipe_installer.EMBED_SCRIPTS:")
    if added:
        print(f"  + added upstream (embed these):   {added}")
    if removed:
        print(f"  - removed upstream (drop these):   {removed}")
    print()
    print(
        "Update EMBED_SCRIPTS and tests/unit/capdevpipe/test_embed_set.py:GOLDEN_SCRIPTS,"
    )
    print(
        "then review the diff in the PR. (Underscore aliases are maintained separately.)"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
