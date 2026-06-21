"""Pytest hooks for swapping the oracle implementation under test."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ORACLE_DIR = Path(__file__).resolve().parent
AUDIT_ROOT = ORACLE_DIR.parent
MUTANTS_DIR = AUDIT_ROOT / "mutants" / "src"


def pytest_addoption(parser):
    parser.addoption(
        "--oracle-module",
        action="store",
        default="reference_oracle",
        help="Oracle module path or name (default: reference_oracle).",
    )


def _load_module(module_ref: str):
    candidate = Path(module_ref)
    if candidate.suffix == ".py":
        path = candidate.resolve()
        name = path.stem
    elif (MUTANTS_DIR / f"{module_ref}.py").exists():
        path = MUTANTS_DIR / f"{module_ref}.py"
        name = module_ref
    elif (ORACLE_DIR / f"{module_ref}.py").exists():
        path = ORACLE_DIR / f"{module_ref}.py"
        name = module_ref
    else:
        raise ImportError(f"oracle module not found: {module_ref}")

    if str(ORACLE_DIR) not in sys.path:
        sys.path.insert(0, str(ORACLE_DIR))
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load oracle module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pytest_configure(config):
    module_ref = config.getoption("--oracle-module")
    module = _load_module(module_ref)
    if not hasattr(module, "assess_lines"):
        raise RuntimeError(f"{module_ref} does not define assess_lines")
    config._oracle_module = module  # type: ignore[attr-defined]


def get_oracle_module(config):
    return config._oracle_module  # type: ignore[attr-defined]
