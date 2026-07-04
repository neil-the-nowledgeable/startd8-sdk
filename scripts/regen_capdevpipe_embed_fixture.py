#!/usr/bin/env python3
"""Regenerate the curated cap-dev-pipe embed golden fixture from embed-manifest.yaml (FR-16).

When the canonical ``full`` profile legitimately changes, the golden-fixture test
(``tests/unit/capdevpipe/test_embed_set.py``) fails loudly. This helper resolves the live
manifest and diffs it against the frozen ``GOLDEN_*`` sets in the test module.

Usage::

    python3 scripts/regen_capdevpipe_embed_fixture.py [--source /path/to/cap-dev-pipe]

This does not edit any file — it only reports. Update the ``GOLDEN_*`` constants in the
test module by hand from the printed sets so the diff is explicit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from startd8.capdevpipe_embed_manifest import DEFAULT_EMBED_PROFILE, resolve_embed_inventory
    from startd8.capdevpipe_installer import DEFAULT_SOURCE
except ImportError:  # pragma: no cover - dev convenience when not pip-installed
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from startd8.capdevpipe_embed_manifest import DEFAULT_EMBED_PROFILE, resolve_embed_inventory
    from startd8.capdevpipe_installer import DEFAULT_SOURCE

# Import golden sets from the test module (single frozen source for drift comparison).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.unit.capdevpipe.test_embed_set import (  # noqa: E402
    GOLDEN_ALIASES,
    GOLDEN_COPY_FILES,
    GOLDEN_PACKAGES,
    GOLDEN_RESOURCE_TREES,
    GOLDEN_SCRIPTS,
)


def _print_set(name: str, values: set[str]) -> None:
    print(f"{name} = {{")
    for item in sorted(values):
        print(f'    "{item}",')
    print("}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"cap-dev-pipe checkout (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_EMBED_PROFILE,
        help=f"embed profile to resolve (default: {DEFAULT_EMBED_PROFILE})",
    )
    args = parser.parse_args()

    manifest_path = args.source / "embed-manifest.yaml"
    if not manifest_path.is_file():
        print(
            f"ERROR: {manifest_path} not found — is --source a cap-dev-pipe checkout?",
            file=sys.stderr,
        )
        return 2

    inv = resolve_embed_inventory(args.source, args.profile)
    live_scripts = set(inv.scripts)
    live_aliases = set(inv.python_aliases)
    live_trees = set(inv.resource_trees)
    live_packages = set(inv.packages)
    live_copy = set(inv.copy_files)

    print(
        f"# Resolved profile {args.profile!r} from {manifest_path} "
        f"({len(live_scripts)} scripts, {len(live_aliases)} aliases):"
    )
    _print_set("GOLDEN_SCRIPTS", live_scripts)
    print()
    _print_set("GOLDEN_ALIASES", live_aliases)
    print()
    _print_set("GOLDEN_RESOURCE_TREES", live_trees)
    print()
    _print_set("GOLDEN_PACKAGES", live_packages)
    print()
    _print_set("GOLDEN_COPY_FILES", live_copy)
    print()

    drift = (
        live_scripts != GOLDEN_SCRIPTS
        or live_aliases != GOLDEN_ALIASES
        or live_trees != GOLDEN_RESOURCE_TREES
        or live_packages != GOLDEN_PACKAGES
        or live_copy != GOLDEN_COPY_FILES
    )
    if not drift:
        print("OK: test golden sets already match the resolved manifest profile.")
        return 0

    print("DRIFT detected vs tests/unit/capdevpipe/test_embed_set.py golden sets:")
    for label, live, golden in (
        ("scripts", live_scripts, GOLDEN_SCRIPTS),
        ("aliases", live_aliases, GOLDEN_ALIASES),
        ("resource_trees", live_trees, GOLDEN_RESOURCE_TREES),
        ("packages", live_packages, GOLDEN_PACKAGES),
        ("copy_files", live_copy, GOLDEN_COPY_FILES),
    ):
        added = live - golden
        removed = golden - live
        if added or removed:
            print(f"  {label}:")
            if added:
                print(f"    + added:   {sorted(added)}")
            if removed:
                print(f"    - removed: {sorted(removed)}")
    print()
    print("Update GOLDEN_* in tests/unit/capdevpipe/test_embed_set.py, then review the PR diff.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
