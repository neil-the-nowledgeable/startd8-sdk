"""FR-16 acyclicity gate for the context_seed refactor.

Automates the invariant the phases/ extraction established, so it cannot silently
regress: (a) core imports cleanly in a fresh interpreter, (b) 0 module-level
``__getattr__`` shims in the package, (c) no ``phases/*`` or ``handler_support``
module imports ``context_seed.core``. A green functional suite alone does not prove
this — the lazy shim could be re-added and tests would still pass.

The static checks parse each module with ``ast`` rather than matching source text,
so they do not false-fire on a *class-level* ``__getattr__`` method (a legitimate
pattern) or on the string ``context_seed.core`` appearing in a comment/docstring.

See docs/design/context-seed-refactor/ (REQUIREMENTS FR-16, PLAN v2.1 Ordering step 6).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
PKG_ROOT = SRC_ROOT / "startd8/contractors/context_seed"


def _has_module_level_getattr(tree: ast.Module) -> bool:
    """True iff the module defines a *top-level* ``def __getattr__`` (PEP 562 shim).

    Class-level ``__getattr__`` methods live under a ClassDef and are ignored — only
    ``tree.body`` (module scope) is inspected.
    """
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "__getattr__"
        for node in tree.body
    )


def _imports_core(tree: ast.Module) -> bool:
    """True iff the module imports context_seed.core in any of its absolute forms.

    Catches ``import ...context_seed.core``, ``from ...context_seed.core import X``,
    and ``from ...context_seed import core`` (the submodule-by-name form). The package
    uses absolute imports throughout, so relative forms are not expected; if that style
    changes, extend this to inspect ``node.level``.
    """
    pkg = "startd8.contractors.context_seed"
    core = f"{pkg}.core"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == core for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == core:
                return True
            if node.module == pkg and any(a.name == "core" for a in node.names):
                return True
    return False


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_core_imports_in_fresh_interpreter() -> None:
    """core must import with no circular-import failure in a clean process."""
    env = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}
    res = subprocess.run(
        [sys.executable, "-c", "import startd8.contractors.context_seed.core"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode == 0, f"fresh import of core failed:\n{res.stderr}"


def test_no_getattr_shims_in_package() -> None:
    """No module-level __getattr__ anywhere in context_seed (the deleted design shim)."""
    offenders = [
        p.relative_to(PKG_ROOT).as_posix()
        for p in sorted(PKG_ROOT.rglob("*.py"))
        if _has_module_level_getattr(_parse(p))
    ]
    assert not offenders, f"module-level __getattr__ shim(s) re-introduced: {offenders}"


def test_phases_and_leaf_do_not_import_core() -> None:
    """phases/* and handler_support are leaves below core, never importing it."""
    targets = sorted((PKG_ROOT / "phases").glob("*.py")) + [PKG_ROOT / "handler_support.py"]
    offenders = [
        p.relative_to(PKG_ROOT).as_posix()
        for p in targets
        if _imports_core(_parse(p))
    ]
    assert not offenders, f"phase/leaf module imports core (dependency inversion): {offenders}"
