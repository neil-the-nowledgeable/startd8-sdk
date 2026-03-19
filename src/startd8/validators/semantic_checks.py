"""Semantic validation layer — deterministic AST checks for generated code.

Catches "correct but wrong" code that is structurally valid but
semantically broken.  No LLM calls — pure AST analysis.

Four checks:
1. Duplicate ``if __name__ == "__main__"`` guards
2. Duplicate function/class definitions at module level
3. Bare ``except: pass`` (swallows all exceptions silently)
4. Phantom dependencies (imports outside ``try/except ImportError``)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set


@dataclass(frozen=True)
class SemanticIssue:
    """A single semantic issue found by deterministic AST analysis."""

    check: str  # e.g. "duplicate_main_guard", "bare_except_pass"
    severity: str  # "warning" or "error"
    message: str
    line: Optional[int] = None
    file_path: Optional[str] = None


def check_duplicate_main_guards(tree: ast.AST) -> List[SemanticIssue]:
    """Flag files with more than one ``if __name__ == "__main__"`` guard."""
    issues: List[SemanticIssue] = []
    count = 0
    lines: List[int] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If):
            if _is_main_guard(node):
                count += 1
                lines.append(node.lineno)
    if count > 1:
        issues.append(SemanticIssue(
            check="duplicate_main_guard",
            severity="warning",
            message=f"Multiple if __name__ == '__main__' guards found (lines {lines})",
            line=lines[1] if len(lines) > 1 else None,
        ))
    return issues


def check_duplicate_definitions(tree: ast.AST) -> List[SemanticIssue]:
    """Flag duplicate function/class names at module level only.

    Does not flag class-level methods (method overloading is valid).
    """
    issues: List[SemanticIssue] = []
    seen: dict[str, int] = {}  # name -> first line
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            if name in seen:
                issues.append(SemanticIssue(
                    check="duplicate_definition",
                    severity="warning",
                    message=(
                        f"Duplicate module-level definition '{name}' "
                        f"(first at line {seen[name]}, again at line {node.lineno})"
                    ),
                    line=node.lineno,
                ))
            else:
                seen[name] = node.lineno
    return issues


def check_bare_except_pass(tree: ast.AST) -> List[SemanticIssue]:
    """Flag bare ``except: pass`` blocks that silently swallow all exceptions.

    Only flags bare ``except:`` (no exception type) with ``pass`` body.
    Does NOT flag ``except Exception:`` or handlers with real logic.
    """
    issues: List[SemanticIssue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            # bare except: type is None
            if node.type is not None:
                continue
            # Check if body is just ``pass``
            if (
                len(node.body) == 1
                and isinstance(node.body[0], ast.Pass)
            ):
                issues.append(SemanticIssue(
                    check="bare_except_pass",
                    severity="warning",
                    message="Bare 'except: pass' silently swallows all exceptions",
                    line=node.lineno,
                ))
    return issues


def check_phantom_dependencies(
    tree: ast.AST,
    known_packages: Optional[Set[str]] = None,
) -> List[SemanticIssue]:
    """Flag imports that reference packages not in the known set.

    Skips imports inside ``try/except ImportError`` blocks.

    Args:
        tree: Parsed AST.
        known_packages: Optional set of allowed top-level package names.
            If None, this check is skipped (returns empty list).
    """
    if known_packages is None:
        return []

    issues: List[SemanticIssue] = []

    # Collect import nodes that are inside try/except ImportError blocks
    guarded_lines: Set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            has_import_error_handler = any(
                _is_import_error_handler(h) for h in node.handlers
            )
            if has_import_error_handler:
                for stmt in node.body:
                    guarded_lines.add(stmt.lineno)

    # Check all imports
    for node in ast.walk(tree):
        if not hasattr(node, "lineno") or node.lineno in guarded_lines:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in known_packages and not _is_stdlib(top):
                    issues.append(SemanticIssue(
                        check="phantom_dependency",
                        severity="warning",
                        message=f"Import '{alias.name}' — package '{top}' not in known dependencies",
                        line=node.lineno,
                    ))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top not in known_packages and not _is_stdlib(top):
                    issues.append(SemanticIssue(
                        check="phantom_dependency",
                        severity="warning",
                        message=f"Import from '{node.module}' — package '{top}' not in known dependencies",
                        line=node.lineno,
                    ))
    return issues


def run_semantic_checks(
    source: str,
    known_packages: Optional[Set[str]] = None,
    file_path: Optional[str] = None,
) -> List[SemanticIssue]:
    """Run all semantic checks on Python source code.

    Args:
        source: Python source code string.
        known_packages: Optional set of known dependency packages for phantom check.
        file_path: Optional file path for issue attribution.

    Returns:
        List of SemanticIssue objects (empty if source is not valid Python).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    issues: List[SemanticIssue] = []
    issues.extend(check_duplicate_main_guards(tree))
    issues.extend(check_duplicate_definitions(tree))
    issues.extend(check_bare_except_pass(tree))
    issues.extend(check_phantom_dependencies(tree, known_packages))

    return _stamp_file_path(issues, file_path)


# ---------------------------------------------------------------------------
# Helpers — shared across Python/C#/Java semantic check modules
# ---------------------------------------------------------------------------


def _stamp_file_path(
    issues: List[SemanticIssue],
    file_path: Optional[str],
) -> List[SemanticIssue]:
    """Stamp ``file_path`` onto every issue if provided."""
    if not file_path:
        return issues
    return [
        SemanticIssue(
            check=i.check,
            severity=i.severity,
            message=i.message,
            line=i.line,
            file_path=file_path,
        )
        for i in issues
    ]


def _basename(file_path: str) -> str:
    """Extract the filename from a path, handling both ``/`` and ``\\``."""
    name = file_path.rsplit("/", 1)[-1]
    return name.rsplit("\\", 1)[-1]


def _is_main_guard(node: ast.If) -> bool:
    """Check if an If node is ``if __name__ == "__main__"``."""
    test = node.test
    if isinstance(test, ast.Compare):
        if (
            len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
        ):
            left = test.left
            right = test.comparators[0]
            if isinstance(left, ast.Name) and left.id == "__name__":
                if isinstance(right, ast.Constant) and right.value == "__main__":
                    return True
            if isinstance(right, ast.Name) and right.id == "__name__":
                if isinstance(left, ast.Constant) and left.value == "__main__":
                    return True
    return False


def _is_import_error_handler(handler: ast.ExceptHandler) -> bool:
    """Check if an except handler catches ImportError."""
    if handler.type is None:
        return True  # bare except catches everything including ImportError
    if isinstance(handler.type, ast.Name):
        return handler.type.id in ("ImportError", "ModuleNotFoundError")
    if isinstance(handler.type, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id in ("ImportError", "ModuleNotFoundError")
            for elt in handler.type.elts
        )
    return False


# Minimal stdlib set — enough for false-positive mitigation
_STDLIB_MODULES = frozenset({
    "abc", "ast", "asyncio", "base64", "bisect", "builtins",
    "calendar", "cgi", "cmath", "codecs", "collections", "colorsys",
    "concurrent", "configparser", "contextlib", "copy", "csv", "ctypes",
    "dataclasses", "datetime", "decimal", "difflib", "dis",
    "email", "encodings", "enum", "errno",
    "filecmp", "fileinput", "fnmatch", "fractions", "ftplib", "functools",
    "gc", "getpass", "gettext", "glob", "gzip",
    "hashlib", "heapq", "hmac", "html", "http",
    "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword",
    "linecache", "locale", "logging", "lzma",
    "mailbox", "math", "mimetypes", "mmap", "multiprocessing",
    "numbers",
    "operator", "os", "pathlib", "pdb", "pickle", "pkgutil",
    "platform", "plistlib", "posixpath", "pprint", "profile",
    "queue",
    "random", "re", "readline", "reprlib", "resource",
    "sched", "secrets", "select", "shelve", "shlex", "shutil",
    "signal", "site", "smtplib", "socket", "socketserver",
    "sqlite3", "ssl", "stat", "statistics", "string",
    "struct", "subprocess", "sys", "syslog",
    "tarfile", "tempfile", "textwrap", "threading", "time",
    "timeit", "token", "tokenize", "tomllib", "trace", "traceback",
    "tracemalloc", "turtle", "types", "typing",
    "unicodedata", "unittest", "urllib", "uuid",
    "venv",
    "warnings", "wave", "weakref",
    "xml", "xmlrpc",
    "zipfile", "zipimport", "zlib",
    # Common underscore modules
    "_thread", "__future__",
})


def _is_stdlib(module_name: str) -> bool:
    """Check if a top-level module name is a known stdlib module."""
    return module_name in _STDLIB_MODULES
