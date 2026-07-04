"""AL-100/AL-101 policy guardrails for contractor logger acquisition."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTRACTORS_ROOT = PROJECT_ROOT / "src/startd8/contractors"

# AL-101 exception allowlist (must match docs/design/artisan/ARTISAN_LOGGING_REQUIREMENTS.md).
ALLOWED_STRING_LOGGER_NAMES: dict[str, set[str]] = {
    "src/startd8/contractors/registry.py": {"startd8.contractors.registry"},
    "src/startd8/contractors/context_seed/core.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/handler_support.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/design_support.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/shared.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/phases/design.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/phases/plan.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/phases/scaffold.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/phases/finalize.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/phases/integrate.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/phases/test_phase.py": {
        "startd8.contractors.context_seed_handlers",
    },
    "src/startd8/contractors/context_seed/phases/review.py": {
        "startd8.contractors.context_seed_handlers",
    },
}


def _iter_contractor_files() -> Iterable[Path]:
    return sorted(CONTRACTORS_ROOT.rglob("*.py"))


def _extract_get_logger_arg(node: ast.Call) -> ast.expr | None:
    if node.args:
        return node.args[0]
    for kw in node.keywords:
        if kw.arg == "name":
            return kw.value
    return None


def _format_violation(path: Path, lineno: int, detail: str) -> str:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    return f"{rel}:{lineno} {detail}"


def test_no_direct_logging_getlogger_calls_in_contractors() -> None:
    violations: list[str] = []

    for path in _iter_contractor_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "getLogger":
                continue
            if not isinstance(node.func.value, ast.Name):
                continue
            if node.func.value.id != "logging":
                continue
            violations.append(
                _format_violation(path, node.lineno, "direct logging.getLogger(...) is forbidden")
            )

    assert not violations, "AL-100 violations found:\n" + "\n".join(sorted(violations))


def test_get_logger_calls_use_dunder_name_or_allowlist() -> None:
    violations: list[str] = []

    for path in _iter_contractor_files():
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        allowed_names = ALLOWED_STRING_LOGGER_NAMES.get(rel, set())

        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "get_logger":
                continue

            arg = _extract_get_logger_arg(node)

            if isinstance(arg, ast.Name) and arg.id == "__name__":
                continue

            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value in allowed_names:
                    continue
                violations.append(
                    _format_violation(
                        path,
                        node.lineno,
                        f'non-allowlisted get_logger(\"{arg.value}\")',
                    )
                )
                continue

            violations.append(
                _format_violation(
                    path,
                    node.lineno,
                    "get_logger(...) must use __name__ or an allowlisted string literal",
                )
            )

    assert not violations, "AL-101 violations found:\n" + "\n".join(sorted(violations))
