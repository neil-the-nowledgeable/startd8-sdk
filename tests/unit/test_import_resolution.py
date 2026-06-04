"""Tests for startd8.utils.import_resolution — import classification utilities."""

import ast

import pytest

from startd8.utils.import_resolution import (
    extract_import_modules,
    discover_sibling_modules,
    resolve_import,
    parse_requirements_packages,
)


# ---------------------------------------------------------------------------
# extract_import_modules
# ---------------------------------------------------------------------------


class TestExtractImportModules:
    def test_simple_import(self):
        tree = ast.parse("import os\n")
        result = extract_import_modules(tree)
        assert len(result) == 1
        assert result[0]["module"] == "os"
        assert result[0]["full_path"] == "os"
        assert result[0]["kind"] == "import"

    def test_dotted_import(self):
        tree = ast.parse("import os.path\n")
        result = extract_import_modules(tree)
        assert len(result) == 1
        assert result[0]["module"] == "os"
        assert result[0]["full_path"] == "os.path"

    def test_from_import(self):
        tree = ast.parse("from pathlib import Path\n")
        result = extract_import_modules(tree)
        assert len(result) == 1
        assert result[0]["module"] == "pathlib"
        assert result[0]["full_path"] == "pathlib"
        assert result[0]["kind"] == "from"

    def test_from_dotted_import(self):
        tree = ast.parse("from google.cloud import secretmanager\n")
        result = extract_import_modules(tree)
        assert len(result) == 1
        assert result[0]["module"] == "google"
        assert result[0]["full_path"] == "google.cloud"

    def test_relative_import_skipped(self):
        tree = ast.parse("from . import utils\n")
        result = extract_import_modules(tree)
        assert result == []

    def test_multiple_imports(self):
        tree = ast.parse("import os\nimport sys\nfrom json import dumps\n")
        result = extract_import_modules(tree)
        assert len(result) == 3
        modules = {r["module"] for r in result}
        assert modules == {"os", "sys", "json"}

    def test_line_numbers_preserved(self):
        tree = ast.parse("x = 1\nimport flask\n")
        result = extract_import_modules(tree)
        assert result[0]["line"] == 2


# ---------------------------------------------------------------------------
# discover_sibling_modules
# ---------------------------------------------------------------------------


class TestDiscoverSiblingModules:
    def test_discovers_py_siblings(self, tmp_path):
        (tmp_path / "svc").mkdir()
        (tmp_path / "svc" / "server.py").write_text("", encoding="utf-8")
        (tmp_path / "svc" / "logger.py").write_text("", encoding="utf-8")
        (tmp_path / "svc" / "client.py").write_text("", encoding="utf-8")

        result = discover_sibling_modules("svc/server.py", str(tmp_path))
        # server.py itself is excluded; logger and client are siblings
        assert "logger" in result
        assert "client" in result
        assert "server" not in result

    def test_discovers_directory_packages(self, tmp_path):
        (tmp_path / "svc").mkdir()
        (tmp_path / "svc" / "app.py").write_text("", encoding="utf-8")
        (tmp_path / "svc" / "utils").mkdir()

        result = discover_sibling_modules("svc/app.py", str(tmp_path))
        assert "utils" in result

    def test_empty_on_missing_dir(self, tmp_path):
        result = discover_sibling_modules("nonexistent/app.py", str(tmp_path))
        assert result == set()


# ---------------------------------------------------------------------------
# resolve_import
# ---------------------------------------------------------------------------


class TestResolveImport:
    def test_stdlib(self):
        r = resolve_import("os", sibling_modules=set(), requirements_packages=set())
        assert r == "stdlib"

    def test_stdlib_nested(self):
        r = resolve_import("collections", sibling_modules=set(), requirements_packages=set())
        assert r == "stdlib"

    def test_protobuf_stub(self):
        r = resolve_import("demo_pb2", sibling_modules=set(), requirements_packages=set())
        assert r == "proto"

    def test_protobuf_grpc_stub(self):
        r = resolve_import("demo_pb2_grpc", sibling_modules=set(), requirements_packages=set())
        assert r == "proto"

    def test_local_sibling(self):
        r = resolve_import("logger", sibling_modules={"logger", "utils"}, requirements_packages=set())
        assert r == "local:logger"

    def test_pip_alias_mapped(self):
        # grpc → grpcio via alias map
        r = resolve_import("grpc", sibling_modules=set(), requirements_packages=set())
        assert r == "pip:grpcio"

    def test_pip_from_requirements(self):
        r = resolve_import("flask", sibling_modules=set(), requirements_packages={"flask"})
        assert r == "pip:flask"

    def test_pip_via_requirements_alias(self):
        # pyyaml in requirements → import yaml
        r = resolve_import("yaml", sibling_modules=set(), requirements_packages={"pyyaml"})
        assert r == "pip:pyyaml"

    def test_pip_via_reverse_prefix(self):
        """from google.cloud import secretmanager resolves via reverse prefix.

        requirements.in has google-cloud-secret-manager which maps to
        google.cloud.secretmanager. The import google.cloud is a parent
        namespace prefix of google.cloud.secretmanager.
        """
        r = resolve_import(
            "google.cloud",
            sibling_modules=set(),
            requirements_packages={"google-cloud-secret-manager"},
        )
        assert r == "pip:google-cloud-secret-manager"

    def test_pip_via_alias_prefix_langchain(self):
        """from langchain.schema import HumanMessage resolves via langchain alias.

        langchain is in _PYPI_TO_IMPORT, so import_to_pypi("langchain.schema")
        finds the prefix "langchain" and returns "langchain", triggering the
        alias-mapped path (pypi_name != module_name).
        """
        r = resolve_import(
            "langchain.schema",
            sibling_modules=set(),
            requirements_packages=set(),
        )
        assert r == "pip:langchain"

    def test_unresolvable(self):
        r = resolve_import(
            "alloydbengine", sibling_modules=set(), requirements_packages=set()
        )
        assert r is None

    def test_import_map_match(self):
        im = {"grpc": "pip:grpcio", "demo_pb2": "proto:demo.proto"}
        r = resolve_import("grpc", sibling_modules=set(), requirements_packages=set(), import_map=im)
        assert r == "import_map:pip:grpcio"

    def test_import_map_closed_world_reject(self):
        im = {"grpc": "pip:grpcio"}
        r = resolve_import(
            "alloydbengine", sibling_modules=set(), requirements_packages=set(), import_map=im
        )
        assert r is None

    def test_import_map_top_level_fallback(self):
        """Import map lookup falls back from full_path to top-level."""
        im = {"google": "pip:google-cloud-aiplatform"}
        r = resolve_import(
            "google", sibling_modules=set(), requirements_packages=set(), import_map=im
        )
        assert r == "import_map:pip:google-cloud-aiplatform"


# ---------------------------------------------------------------------------
# parse_requirements_packages
# ---------------------------------------------------------------------------


class TestParseRequirementsPackages:
    def test_simple(self):
        result = parse_requirements_packages("flask\nrequests\n")
        assert result == {"flask", "requests"}

    def test_with_versions(self):
        result = parse_requirements_packages("flask>=2.0\npydantic~=2.0\n")
        assert result == {"flask", "pydantic"}

    def test_comments_and_blanks(self):
        result = parse_requirements_packages("# comment\n\nflask\n")
        assert result == {"flask"}

    def test_pip_flags_skipped(self):
        result = parse_requirements_packages("-e .\n--index-url https://x\nflask\n")
        assert result == {"flask"}

    def test_inline_comment(self):
        result = parse_requirements_packages("flask  # web framework\n")
        assert result == {"flask"}

    def test_extras(self):
        result = parse_requirements_packages("uvicorn[standard]\n")
        assert result == {"uvicorn"}


# --- FR-RI-1 (RUN-038 #1): resolver dependency-surface honesty ----------------------------

class TestFrRi1DependencySurface:
    def test_db_orm_floor_packages_resolve_without_requirements(self):
        # FR-RI-1b: sqlmodel/sqlalchemy resolve even with no declared deps (the floor).
        from startd8.utils.import_resolution import resolve_import, _WELL_KNOWN_PACKAGES

        for pkg in ("sqlmodel", "sqlalchemy", "alembic"):
            assert pkg in _WELL_KNOWN_PACKAGES
            assert resolve_import(
                pkg, sibling_modules=set(), requirements_packages=set()
            ) == f"pip:{pkg}"
        assert resolve_import(
            "sqlalchemy.pool", sibling_modules=set(), requirements_packages=set()
        ) == "pip:sqlalchemy"

    def test_discovery_walks_to_project_root_and_reads_app_reqs_and_pyproject(self, tmp_path):
        # FR-RI-1a: generated files live under generated/app/, manifests at the project root.
        from startd8.forward_manifest_validator import _discover_requirements_packages

        (tmp_path / "requirements-app.txt").write_text("fastapi\ncustom-pkg==1.2\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["typer>=0.9", "rich"]\n'
        )
        gen = tmp_path / "generated" / "app"
        gen.mkdir(parents=True)
        (gen / "x.py").write_text("x = 1\n")

        pkgs = _discover_requirements_packages("generated/app/x.py", str(tmp_path))
        assert {"fastapi", "custom-pkg", "typer", "rich"} <= pkgs
