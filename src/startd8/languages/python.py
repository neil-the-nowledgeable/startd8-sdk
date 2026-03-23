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
        from ..implementation_engine.framework_imports import _PYTHON_FRAMEWORK_IMPORTS
        return dict(_PYTHON_FRAMEWORK_IMPORTS)

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
            "Python coding standards:\n"
            "- PEP 8 naming: snake_case functions/variables, PascalCase classes, UPPER_SNAKE constants.\n"
            "- Type hints on all public function signatures (parameters and return types).\n"
            "- Use specific exception types: `except (ValueError, TypeError):` — "
            "NEVER use bare `except:` or `except: pass`.\n"
            "- Use `from __future__ import annotations` for forward references.\n"
            "- LOGGING: Use `logging.getLogger(__name__)` — "
            "NEVER use `print()` for diagnostic output in library/service code.\n"
            "- IMPORTS: stdlib first, third-party second, local third (isort convention). "
            "No single-letter variable names (l, O, I). Define helpers before use.\n"
            "- Use context managers (`with`) for file I/O and resource management.\n"
            "- Prefer `pathlib.Path` over `os.path` for file operations."
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

    def derive_service_metadata(
        self,
        features: Sequence[Any],
        *,
        onboarding: Optional[Dict[str, Any]] = None,
        api_signatures: Optional[List[str]] = None,
        runtime_dependencies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Python has no language-specific service metadata."""
        return {}

    def build_project_context_section(self, context: Dict[str, Any]) -> str:
        """Python needs no special project context section."""
        return ""

    def strip_dependency_version(self, dep: str) -> str:
        """Strip version pin from a Python dependency string.

        Example: ``'grpcio==1.76.0'`` -> ``'grpcio'``
        """
        for sep in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if sep in dep:
                return dep.split(sep, 1)[0].strip()
        return dep.strip()

    def get_import_syntax_guidance(self) -> str:
        """Return Python import rules for LLM prompts."""
        return (
            "Use ONLY these packages plus Python stdlib. Every non-stdlib symbol you\n"
            "reference MUST have a corresponding import statement at the top of the file.\n"
            "Do NOT import packages not listed above.\n"
        )

    def extract_import_lines(self, source: str) -> list[str]:
        """Extract import statements from Python source (REQ-PE-400).

        Uses AST for precision. Falls back to empty list on parse failure.
        """
        import ast as _ast
        try:
            tree = _ast.parse(source)
        except SyntaxError:
            return []
        imports: list[str] = []
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                try:
                    imports.append(_ast.unparse(node))
                except (AttributeError, ValueError):
                    pass
        return imports

    @property
    def stub_marker_text(self) -> str:
        """Python stub marker for skeleton fill prompts."""
        return "`raise NotImplementedError`"

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
