"""Tests for F-6 — symbol-level import validation + referenced-template assets.

Validator-gate asks from VALIDATION_AND_MANIFEST_DERIVATION.md §8 F-6
(evidence: P3_RUN_009_POSTMORTEM.md §1, P3_RUN_010_QUALITY_EVAL.md §3 D1/D4):
a generated module that cannot import scored PASS twice because nothing
symbol-level ever checked its from-imports, and referenced templates were
never covered by cross-file contracts.
"""

from __future__ import annotations

import ast
import sys
import textwrap

import pytest

from startd8.forward_manifest_validator import validate_disk_compliance
from startd8.validators.import_symbol_checks import (
    check_import_symbols,
    check_template_references,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path, rel_path, content):
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(content), encoding="utf-8")
    return rel_path


def _phantoms(source, file_path, project_root):
    tree = ast.parse(textwrap.dedent(source))
    return check_import_symbols(tree, file_path, project_root)


def _by_category(issues, category):
    return [i for i in issues if i.get("category") == category]


# ---------------------------------------------------------------------------
# Phantom symbols — local (project-tree) modules
# ---------------------------------------------------------------------------


class TestLocalPhantomSymbols:
    def test_existing_symbol_in_local_module_passes(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/tables.py", "class Capability:\n    pass\n")
        rel = _write(
            tmp_path, "app/wizard.py", "from app.tables import Capability\n"
        )
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_missing_symbol_in_local_module_flagged(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/tables.py", "class Capability:\n    pass\n")
        rel = _write(
            tmp_path, "app/wizard.py", "from app.tables import Sorcery\n"
        )
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert len(issues) == 1
        issue = issues[0]
        assert issue["category"] == "phantom_symbol"
        assert issue["severity"] == "error"
        assert "Sorcery" in issue["message"]
        assert issue["symbol"] == "app.tables.Sorcery"

    def test_sibling_rooted_import_resolves(self, tmp_path):
        # `from tables import X` where tables.py is a sibling of the file
        _write(tmp_path, "app/tables.py", "X = 1\n")
        rel = _write(tmp_path, "app/wizard.py", "from tables import X\n")
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_relative_import_resolves(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/tables.py", "def helper():\n    pass\n")
        rel = _write(tmp_path, "app/wizard.py", "from .tables import helper\n")
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_relative_import_phantom_flagged(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/tables.py", "def helper():\n    pass\n")
        rel = _write(tmp_path, "app/wizard.py", "from .tables import phantom\n")
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert len(issues) == 1
        assert issues[0]["symbol"] == ".tables.phantom"

    def test_submodule_fallback_from_package(self, tmp_path):
        # `from app import tables` is valid even when __init__ never binds it
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/tables.py", "X = 1\n")
        rel = _write(tmp_path, "main.py", "from app import tables\n")
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_missing_submodule_from_package_flagged(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/tables.py", "X = 1\n")
        rel = _write(tmp_path, "main.py", "from app import sorcery\n")
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert len(issues) == 1
        assert issues[0]["category"] == "phantom_symbol"


class TestDynamicAndUnverifiableModulesSkipped:
    def test_star_import_target_module_skipped(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/lazy.py", "from os.path import *\n")
        rel = _write(tmp_path, "app/wizard.py", "from app.lazy import whatever\n")
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_module_getattr_target_skipped(self, tmp_path):
        _write(
            tmp_path, "app/lazy.py",
            "def __getattr__(name):\n    return 42\n",
        )
        rel = _write(tmp_path, "app/wizard.py", "from lazy import anything\n")
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_uninstalled_package_makes_no_claims(self, tmp_path):
        # Module-level resolvability is L1's job; symbol check stays silent.
        rel = _write(
            tmp_path, "app/wizard.py",
            "from definitely_not_installed_xyz.mod import Thing\n",
        )
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_star_import_statement_itself_skipped(self, tmp_path):
        _write(tmp_path, "app/tables.py", "X = 1\n")
        rel = _write(tmp_path, "app/wizard.py", "from tables import *\n")
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []


class TestBindingSurfaceForms:
    def test_all_list_counts_as_binding(self, tmp_path):
        # __all__ may name symbols that are set dynamically elsewhere
        _write(
            tmp_path, "app/mod.py",
            '__all__ = ["dynamic_name"]\n',
        )
        rel = _write(tmp_path, "app/wizard.py", "from mod import dynamic_name\n")
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_reexport_and_conditional_bindings_count(self, tmp_path):
        _write(
            tmp_path, "app/mod.py",
            """\
            try:
                from json import dumps as fast_dumps
            except ImportError:
                fast_dumps = None
            if True:
                FLAG = 1
            a, b = 1, 2
            """,
        )
        rel = _write(
            tmp_path, "app/wizard.py",
            "from mod import fast_dumps, FLAG, a, b\n",
        )
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []


# ---------------------------------------------------------------------------
# Phantom symbols — installed packages (the RUN-009/010 starlette class)
# ---------------------------------------------------------------------------


class TestInstalledPackagePhantoms:
    @pytest.fixture()
    def fake_site(self, tmp_path_factory, monkeypatch):
        """A fake installed package on sys.path (deterministic stand-in
        for the third-party branch — no starlette dependency needed)."""
        site = tmp_path_factory.mktemp("fakesite")
        pkg = site / "fakeweb"
        (pkg / "responses").mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        # fakeweb/responses.py mirrors starlette.responses' shape
        (pkg / "responses" / "__init__.py").write_text(
            "class HTMLResponse:\n    pass\n\nclass JSONResponse:\n    pass\n",
            encoding="utf-8",
        )
        (pkg / "templating.py").write_text(
            "class Jinja2Templates:\n    pass\n", encoding="utf-8",
        )
        monkeypatch.syspath_prepend(str(site))
        importlib_invalidate()
        return site

    def test_phantom_symbol_in_installed_package_flagged(
        self, tmp_path, fake_site
    ):
        # The RUN-009/RUN-010 D1 shape: module exists, symbol does not.
        rel = _write(
            tmp_path, "app/wizard.py",
            "from fakeweb.responses import TemplateResponse\n",
        )
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert len(issues) == 1
        assert issues[0]["category"] == "phantom_symbol"
        assert "TemplateResponse" in issues[0]["message"]

    def test_real_symbol_in_installed_package_passes(self, tmp_path, fake_site):
        rel = _write(
            tmp_path, "app/wizard.py",
            "from fakeweb.responses import HTMLResponse\n"
            "from fakeweb.templating import Jinja2Templates\n",
        )
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_run009_starlette_template_response_repro(self, tmp_path):
        """The literal RUN-009/RUN-010 line, against real starlette when present."""
        pytest.importorskip("starlette")
        rel = _write(
            tmp_path, "app/wizard.py",
            "from starlette.responses import TemplateResponse\n",
        )
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        phantom = _by_category(issues, "phantom_symbol")
        assert len(phantom) == 1
        assert "TemplateResponse" in phantom[0]["message"]

    def test_stdlib_from_import_passes(self, tmp_path):
        rel = _write(
            tmp_path, "app/wizard.py",
            "from pathlib import Path\nfrom dataclasses import dataclass\n",
        )
        issues = _phantoms(
            (tmp_path / rel).read_text(), str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []


def importlib_invalidate():
    import importlib

    importlib.invalidate_caches()
    # Drop any cached find_spec failures for the fake package
    sys.modules.pop("fakeweb", None)


# ---------------------------------------------------------------------------
# Referenced template assets (F-6.2)
# ---------------------------------------------------------------------------


WIZARD_WITH_TEMPLATES = """\
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def render(request, step):
    return templates.TemplateResponse(f"wizard/{step}.html", {"request": request})


def done(request):
    return templates.TemplateResponse("wizard/done.html", {"request": request})
"""


class TestTemplateReferences:
    def test_missing_constant_template_flagged(self, tmp_path):
        _write(tmp_path, "app/templates/base.html", "<html></html>")
        rel = _write(tmp_path, "app/wizard.py", WIZARD_WITH_TEMPLATES)
        tree = ast.parse((tmp_path / rel).read_text())
        issues = check_template_references(
            tree, str(tmp_path / rel), str(tmp_path)
        )
        cats = _by_category(issues, "missing_template_asset")
        # wizard/done.html missing + wizard/ dir missing for the f-string
        assert len(cats) == 2
        symbols = {i["symbol"] for i in cats}
        assert "wizard/done.html" in symbols
        assert "wizard/" in symbols

    def test_existing_templates_pass(self, tmp_path):
        _write(tmp_path, "app/templates/wizard/step.html", "x")
        _write(tmp_path, "app/templates/wizard/done.html", "x")
        rel = _write(tmp_path, "app/wizard.py", WIZARD_WITH_TEMPLATES)
        tree = ast.parse((tmp_path / rel).read_text())
        issues = check_template_references(
            tree, str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_no_template_root_makes_no_claims(self, tmp_path):
        rel = _write(
            tmp_path, "app/wizard.py",
            "def f(t):\n    return t.TemplateResponse('a.html', {})\n",
        )
        tree = ast.parse((tmp_path / rel).read_text())
        issues = check_template_references(
            tree, str(tmp_path / rel), str(tmp_path)
        )
        assert issues == []

    def test_request_first_starlette_signature(self, tmp_path):
        _write(tmp_path, "templates/home.html", "x")
        rel = _write(
            tmp_path, "app/views.py",
            "def f(templates, request):\n"
            "    templates.TemplateResponse(request, 'home.html')\n"
            "    return templates.TemplateResponse(request, 'gone.html')\n",
        )
        tree = ast.parse((tmp_path / rel).read_text())
        issues = check_template_references(
            tree, str(tmp_path / rel), str(tmp_path)
        )
        assert len(issues) == 1
        assert issues[0]["symbol"] == "gone.html"

    def test_get_template_and_render_template_covered(self, tmp_path):
        _write(tmp_path, "templates/real.html", "x")
        rel = _write(
            tmp_path, "app/views.py",
            "def f(env):\n"
            "    env.get_template('real.html')\n"
            "    env.get_template('fake.html')\n",
        )
        tree = ast.parse((tmp_path / rel).read_text())
        issues = check_template_references(
            tree, str(tmp_path / rel), str(tmp_path)
        )
        assert len(issues) == 1
        assert issues[0]["symbol"] == "fake.html"


# ---------------------------------------------------------------------------
# Wiring — validate_disk_compliance picks both checks up (L12/L13)
# ---------------------------------------------------------------------------


class TestDiskComplianceWiring:
    def test_phantom_symbol_reaches_semantic_issues(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/tables.py", "class Capability:\n    pass\n")
        rel = _write(
            tmp_path, "app/wizard.py",
            "from app.tables import Sorcery\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        phantom = _by_category(result.semantic_issues, "phantom_symbol")
        assert len(phantom) == 1
        assert phantom[0]["severity"] == "error"

    def test_missing_template_reaches_semantic_issues(self, tmp_path):
        _write(tmp_path, "app/templates/base.html", "<html></html>")
        rel = _write(tmp_path, "app/wizard.py", WIZARD_WITH_TEMPLATES)
        result = validate_disk_compliance(rel, str(tmp_path))
        missing = _by_category(result.semantic_issues, "missing_template_asset")
        assert len(missing) == 2

    def test_clean_file_unaffected(self, tmp_path):
        _write(tmp_path, "app/tables.py", "class Capability:\n    pass\n")
        rel = _write(
            tmp_path, "app/wizard.py",
            "from tables import Capability\n\n"
            "def make():\n    return Capability()\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _by_category(result.semantic_issues, "phantom_symbol") == []
        assert _by_category(result.semantic_issues, "missing_template_asset") == []


# ---------------------------------------------------------------------------
# Postmortem posture — phantom_symbol is verdict-critical (loud downgrade)
# ---------------------------------------------------------------------------


class TestPostmortemPosture:
    def test_phantom_symbol_is_critical_category(self):
        from startd8.contractors.prime_postmortem import (
            _CRITICAL_SEMANTIC_CATEGORIES,
        )

        assert "phantom_symbol" in _CRITICAL_SEMANTIC_CATEGORIES

    def test_kaizen_suggestion_mappings_exist(self):
        from startd8.contractors.prime_postmortem import (
            CAUSE_TO_SUGGESTION,
            _SEMANTIC_CATEGORY_TO_SUGGESTION,
        )

        assert (
            _SEMANTIC_CATEGORY_TO_SUGGESTION["phantom_symbol"]
            in CAUSE_TO_SUGGESTION
        )
        assert (
            _SEMANTIC_CATEGORY_TO_SUGGESTION["missing_template_asset"]
            in CAUSE_TO_SUGGESTION
        )
