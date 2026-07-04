"""FR-16 acyclicity gate for the context_seed refactor.

Automates the invariant the phases/ extraction established, so it cannot silently
regress: (a) core imports cleanly in a fresh interpreter, (b) 0 module-level
``__getattr__`` shims in the package, (c) no ``phases/*`` or ``handler_support``
module imports ``context_seed.core``. A green functional suite alone does not prove
this — the lazy shim could be re-added and tests would still pass.

See docs/design/context-seed-refactor/ (REQUIREMENTS FR-16, PLAN v2.1 Ordering step 6).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[3] / "src/startd8/contractors/context_seed"


def test_core_imports_in_fresh_interpreter() -> None:
    """core must import with no circular-import failure in a clean process."""
    res = subprocess.run(
        [sys.executable, "-c", "import startd8.contractors.context_seed.core"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[3]),
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
    )
    assert res.returncode == 0, f"fresh import of core failed:\n{res.stderr}"


def test_no_getattr_shims_in_package() -> None:
    """No module-level __getattr__ anywhere in context_seed (the deleted shim)."""
    offenders = [
        p.relative_to(PKG_ROOT).as_posix()
        for p in PKG_ROOT.rglob("*.py")
        if "def __getattr__" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"module-level __getattr__ shim(s) re-introduced: {offenders}"


def test_phases_and_leaf_do_not_import_core() -> None:
    """phases/* and handler_support are leaves below core, never importing it."""
    targets = list((PKG_ROOT / "phases").glob("*.py")) + [PKG_ROOT / "handler_support.py"]
    offenders = [
        p.relative_to(PKG_ROOT).as_posix()
        for p in targets
        if "context_seed.core" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"phase/leaf module imports core (dependency inversion): {offenders}"
