"""Tests for import_completion repair step — local definition guard.

Validates that import_completion does NOT add ``import foo`` when ``foo``
is a function, class, or variable defined in the same file.  This prevents
the hallucinated-import corruption seen in PI-009 (locustfile.py) where
``import setCurrency``, ``import browseProduct``, etc. were added by the
repair step because function names matched manifest import entries.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from startd8.repair.steps.import_completion import (
    ManifestImportCompletion,
    ErrorDrivenImportCompletion,
    _collect_local_definitions,
)
from startd8.repair.models import (
    ElementContext,
    ImportDiagnostic,
    RepairContext,
)


# ---------------------------------------------------------------------------
# _collect_local_definitions
# ---------------------------------------------------------------------------


class TestCollectLocalDefinitions:
    def test_functions(self):
        tree = ast.parse("def foo():\n    pass\ndef bar():\n    pass\n")
        assert _collect_local_definitions(tree) == {"foo", "bar"}

    def test_classes(self):
        tree = ast.parse("class MyClass:\n    pass\n")
        assert _collect_local_definitions(tree) == {"MyClass"}

    def test_assignments(self):
        tree = ast.parse("x = 1\ny: int = 2\n")
        assert _collect_local_definitions(tree) == {"x", "y"}

    def test_mixed(self):
        tree = ast.parse(
            "GLOBAL = 42\ndef helper():\n    pass\nclass Svc:\n    pass\n"
        )
        assert _collect_local_definitions(tree) == {"GLOBAL", "helper", "Svc"}

    def test_nested_names_now_included(self):
        """FR-RI-2 (RUN-038 #2): names bound in ANY scope are collected, not just module-level.

        Was ``test_nested_not_included`` — the old narrow module-level scope is exactly what let
        ``import_completion`` synthesize ``import <local-var>`` and cause a boot ModuleNotFoundError.
        """
        tree = ast.parse(
            "def outer():\n    def inner():\n        pass\n    inner()\n"
        )
        assert _collect_local_definitions(tree) == {"outer", "inner"}

    def test_function_body_local_excluded_from_import_synthesis(self):
        """The RUN-038 own-goal: a function-body local (`assets`) must never become `import assets`."""
        code = (
            "from sqlmodel import Session, select\n"
            "def export(session: Session):\n"
            "    assets = session.exec(select(X)).all()\n"
            "    for row in assets:\n"
            "        pass\n"
            "    with open('x') as fh:\n"
            "        data = fh.read()\n"
            "    return [a for a in assets if (total := a.value)]\n"
        )
        names = _collect_local_definitions(ast.parse(code))
        assert {"assets", "session", "row", "fh", "data", "a", "total", "export"} <= names

    def test_async_functions(self):
        tree = ast.parse("async def handler():\n    pass\n")
        assert _collect_local_definitions(tree) == {"handler"}


# ---------------------------------------------------------------------------
# ManifestImportCompletion — local definition guard
# ---------------------------------------------------------------------------


class TestManifestImportCompletionLocalGuard:
    """Verifies that ManifestImportCompletion skips imports matching local defs."""

    def _make_import_spec(self, module: str, kind: str = "import", names=None):
        """Create a mock import spec compatible with ManifestImportCompletion."""
        spec = MagicMock()
        spec.module = module
        spec.kind = kind
        spec.names = names or []
        spec.alias = None
        return spec

    def test_skips_import_of_local_function(self):
        """import setCurrency should be skipped when setCurrency is a local def."""
        code = (
            "def setCurrency():\n"
            "    pass\n"
            "\n"
            "def main():\n"
            "    setCurrency()\n"
        )
        imp = self._make_import_spec("setCurrency", kind="import")
        ctx = RepairContext(diagnostics=[])
        elem_ctx = ElementContext(imports=[imp])

        step = ManifestImportCompletion()
        result = step(code, ctx, Path("locustfile.py"), element_context=elem_ctx)

        assert result.modified is False
        assert "import setCurrency" not in result.code

    def test_skips_from_import_of_local_module(self):
        """from browseProduct import X should be skipped when browseProduct is local."""
        code = (
            "def browseProduct(session):\n"
            "    pass\n"
            "\n"
            "browseProduct(None)\n"
        )
        imp = self._make_import_spec(
            "browseProduct", kind="from", names=["browseProduct"],
        )
        ctx = RepairContext(diagnostics=[])
        elem_ctx = ElementContext(imports=[imp])

        step = ManifestImportCompletion()
        result = step(code, ctx, Path("locustfile.py"), element_context=elem_ctx)

        assert result.modified is False

    def test_allows_real_module_import(self):
        """import locust should still be added when locust is not a local def."""
        code = (
            "def my_task():\n"
            "    user = HttpUser()\n"
        )
        imp = self._make_import_spec("locust", kind="from", names=["HttpUser"])
        ctx = RepairContext(diagnostics=[])
        elem_ctx = ElementContext(imports=[imp])

        step = ManifestImportCompletion()
        result = step(code, ctx, Path("locustfile.py"), element_context=elem_ctx)

        assert result.modified is True
        assert "from locust import HttpUser" in result.code

    def test_locustfile_scenario(self):
        """Full locustfile scenario: functions defined + used, should NOT add imports."""
        code = (
            "from locust import HttpUser, task, between\n"
            "\n"
            "def index(self):\n"
            "    self.client.get('/')\n"
            "\n"
            "def setCurrency(self):\n"
            "    self.client.post('/setCurrency')\n"
            "\n"
            "def browseProduct(self):\n"
            "    self.client.get('/product/1')\n"
            "\n"
            "class WebUser(HttpUser):\n"
            "    tasks = [index, setCurrency, browseProduct]\n"
            "    wait_time = between(1, 5)\n"
        )
        # Manifest claims these are importable modules
        imports = [
            self._make_import_spec("index"),
            self._make_import_spec("setCurrency"),
            self._make_import_spec("browseProduct"),
        ]
        ctx = RepairContext(diagnostics=[])
        elem_ctx = ElementContext(imports=imports)

        step = ManifestImportCompletion()
        result = step(code, ctx, Path("locustfile.py"), element_context=elem_ctx)

        assert result.modified is False
        # Verify none of the function names were added as imports
        for name in ("index", "setCurrency", "browseProduct"):
            assert f"import {name}" not in result.code


# ---------------------------------------------------------------------------
# ErrorDrivenImportCompletion — local definition guard
# ---------------------------------------------------------------------------


class TestErrorDrivenImportCompletionLocalGuard:
    def test_skips_local_function_as_missing_import(self):
        """Error-driven path should not add import for locally-defined names."""
        code = (
            "def setCurrency(session):\n"
            "    session.post('/setCurrency')\n"
            "\n"
            "setCurrency(None)\n"
        )
        diag = ImportDiagnostic(
            category="import",
            file="locustfile.py",
            message="undefined name 'setCurrency'",
            module="setCurrency",
            name="",
        )
        ctx = RepairContext(diagnostics=[diag])

        step = ErrorDrivenImportCompletion()
        result = step(code, ctx, Path("locustfile.py"))

        assert result.modified is False
        assert "import setCurrency" not in result.code

    def test_allows_real_missing_import(self):
        """Real missing imports (e.g. json) should still be added."""
        code = (
            "def foo():\n"
            "    return json.dumps({})\n"
        )
        diag = ImportDiagnostic(
            category="import",
            file="mymod.py",
            message="undefined name 'json'",
            module="json",
            name="",
        )
        ctx = RepairContext(diagnostics=[diag])

        step = ErrorDrivenImportCompletion()
        result = step(code, ctx, Path("mymod.py"))

        assert result.modified is True
        assert "import json" in result.code
