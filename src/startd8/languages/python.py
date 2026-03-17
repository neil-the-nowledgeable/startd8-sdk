"""PythonLanguageProfile — extracts all Python-specific logic into a profile.

Registered as the default language profile.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


class PythonLanguageProfile:
    """Language profile for Python code generation."""

    @property
    def language_id(self) -> str:
        return "python"

    @property
    def display_name(self) -> str:
        return "Python"

    @property
    def source_extensions(self) -> List[str]:
        return [".py"]

    @property
    def build_file_patterns(self) -> List[str]:
        return ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"]

    @property
    def syntax_check_command(self) -> Optional[List[str]]:
        return ["python3", "-m", "py_compile", "{file}"]

    @property
    def lint_command(self) -> Optional[List[str]]:
        return [
            "python3", "-m", "ruff", "check", "{file}",
            "--select=E7,E9,F", "--output-format=concise",
        ]

    @property
    def test_command(self) -> Optional[List[str]]:
        return ["python3", "-m", "pytest", "-v", "--tb=short", "-q"]

    @property
    def framework_imports(self) -> Dict[str, dict]:
        # Re-export from the existing framework_imports module
        from ..implementation_engine.framework_imports import FRAMEWORK_IMPORTS
        return dict(FRAMEWORK_IMPORTS)

    @property
    def package_alias_map(self) -> Dict[str, str]:
        from ..implementation_engine.package_aliases import _PYPI_TO_IMPORT
        return dict(_PYPI_TO_IMPORT)

    @property
    def cleanup_patterns(self) -> List[str]:
        return ["__pycache__", "*.pyc", ".pytest_cache", ".mypy_cache"]

    @property
    def blast_radius_extensions(self) -> List[str]:
        return [".py"]

    @property
    def import_pattern_template(self) -> str:
        return "import {module}|from {module}"

    @property
    def system_prompt_role(self) -> str:
        return "an expert Python engineer"

    @property
    def coding_standards(self) -> str:
        return (
            "Ruff: no single-letter vars l/O/I; define helpers before use; "
            "stdlib-only imports unless listed."
        )

    @property
    def merge_strategy_preference(self) -> str:
        return "ast"

    @property
    def repair_enabled(self) -> bool:
        return True

    @property
    def docker_base_image(self) -> str:
        return "python:3.12-slim"

    @property
    def docker_runtime_image(self) -> str:
        return "python:3.12-slim"

    def supports_extension(self, ext: str) -> bool:
        return ext.lower() in (".py", ".pyw")

    def get_import_patterns(self, module_stem: str) -> List[str]:
        return [
            f"import {module_stem}",
            f"from {module_stem} import",
            f"from {module_stem}",
        ]

    @property
    def stub_patterns(self) -> List[str]:
        # Python uses AST-based stub detection, not text patterns
        return []

    @property
    def function_start_pattern(self) -> Optional[str]:
        # Python uses AST-based stub detection
        return None

    def get_stdlib_prefixes(self) -> Sequence[str]:
        # Canonical Python stdlib set (from checkpoint.py)
        return _PYTHON_STDLIB_PREFIXES

    def post_generation_cleanup(self, files: List[Path], project_root: Path) -> List[str]:
        # Python cleanup is handled inline by ruff auto-fix in checkpoint/engine.
        # No separate post-generation step needed.
        return []

    def validate_syntax(self, code: str) -> tuple[bool, str]:
        """Validate Python syntax via ast.parse()."""
        import ast
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, str(e)

    def generate_dependency_file(
        self,
        project_root: Path,
        service_name: str,
        module_path: str,
        dependencies: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        # Python uses requirements_generator.py for requirements.txt.
        # Not implemented here — existing pipeline handles it.
        return None


# Extracted from IntegrationCheckpoint._STDLIB_PREFIXES
_PYTHON_STDLIB_PREFIXES: tuple[str, ...] = (
    "abc", "argparse", "ast", "asyncio", "base64", "bisect",
    "calendar", "collections", "concurrent", "configparser",
    "contextlib", "copy", "csv", "ctypes", "dataclasses",
    "datetime", "decimal", "difflib", "email", "enum",
    "errno", "fcntl", "fileinput", "fnmatch", "fractions",
    "ftplib", "functools", "getpass", "glob", "gzip",
    "hashlib", "heapq", "hmac", "html", "http",
    "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "linecache", "locale", "logging",
    "lzma", "math", "mimetypes", "multiprocessing", "numbers",
    "operator", "os", "pathlib", "pickle", "pkgutil",
    "platform", "pprint", "queue", "random", "re",
    "shlex", "shutil", "signal", "site", "socket",
    "sqlite3", "ssl", "stat", "statistics", "string",
    "struct", "subprocess", "sys", "sysconfig", "tempfile",
    "textwrap", "threading", "time", "timeit", "token",
    "tokenize", "traceback", "types", "typing", "typing_extensions",
    "unittest", "urllib", "uuid", "venv", "warnings",
    "weakref", "xml", "xmlrpc", "zipfile", "zipimport", "zlib",
    "builtins", "_thread", "__future__",
)
