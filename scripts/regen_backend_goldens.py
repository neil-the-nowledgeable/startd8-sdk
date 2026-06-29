"""Regenerate the backend_codegen deployment-mode golden trees (FR-22).

The byte-identity guard ``test_deployment_mode_consume::test_golden_tree_byte_identity`` pins a
``{path: sha256}`` map per deployment mode. When a *legitimate* generator change moves those bytes,
run this to re-pin in one reviewable step — then read the resulting ``git diff`` consciously — instead
of hand-editing the sha JSON (the stale-exact-pin pattern that caused several reds).

    python scripts/regen_backend_goldens.py

Uses the SAME ``SCHEMA`` + fixture paths the test imports, so the helper can't drift from the guard.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from startd8.backend_codegen.assembler import render_backend  # noqa: E402
from tests.unit.backend_codegen.test_deployment_mode_consume import (  # noqa: E402
    SCHEMA,
    _FIXTURES,
)


def main() -> None:
    for mode in ("installed", "deployed"):
        tree = dict(render_backend(SCHEMA, deployment_mode=mode))
        actual = {rel: hashlib.sha256(text.encode()).hexdigest() for rel, text in tree.items()}
        path = _FIXTURES / f"{mode}.sha256.json"
        path.write_text(json.dumps(dict(sorted(actual.items())), indent=2) + "\n")
        print(f"regenerated {path.relative_to(_ROOT)} ({len(actual)} files)")
    print("review `git diff` before committing.")


if __name__ == "__main__":
    main()
