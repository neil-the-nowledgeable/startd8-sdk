"""OpenAPI spec validation gate for generated static contracts (OpenAPI Role 1, M2 / FR-6).

Validates the ``OPENAPI_SPEC`` dict materialized in ``app/openapi_contract.py``. Absent
``openapi-spec-validator`` ⇒ ``unavailable`` ⇒ **non-pass** (never a silent PASS) — the same
loud-degradation rule as ``boot_smoke`` and ``python_toolchain``.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class OpenApiSpecGateResult:
    """Outcome of validating a generated static OpenAPI document."""

    status: str  # checked | unavailable | error
    ok: bool = False
    message: str = ""
    diagnostics: List[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.status == "unavailable":
            return "unavailable"
        if self.status != "checked":
            return "fail"
        return "pass" if self.ok else "fail"

    @property
    def is_pass(self) -> bool:
        return self.verdict == "pass"


def _openapi_spec_node_value(mod: ast.Module) -> Optional[ast.AST]:
    for node in mod.body:
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "OPENAPI_SPEC":
                return node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "OPENAPI_SPEC":
                    return node.value
    return None


def _literal_from_json_loads(value: ast.AST) -> Optional[Dict[str, Any]]:
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if not (
        isinstance(func, ast.Attribute)
        and func.attr == "loads"
        and isinstance(func.value, ast.Name)
        and func.value.id == "json"
    ):
        return None
    if not value.args:
        return None
    arg = value.args[0]
    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
        return None
    try:
        loaded = json.loads(arg.value)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def extract_openapi_spec_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Load ``OPENAPI_SPEC`` from generated contract module text without importing ``app``.

    Uses AST parsing (same trust model as ``boot_smoke.expected_routes_from_contract``) — no
    ``exec`` of generated code in the gate process.
    """
    try:
        mod = ast.parse(text)
    except SyntaxError as exc:
        logger.debug("openapi-spec-gate: could not parse contract module: %s", exc)
        return None
    value = _openapi_spec_node_value(mod)
    if value is None:
        return None
    spec = _literal_from_json_loads(value)
    if spec is not None:
        return spec
    try:
        literal = ast.literal_eval(value)
    except (ValueError, TypeError) as exc:
        logger.debug("openapi-spec-gate: OPENAPI_SPEC not a literal: %s", exc)
        return None
    return literal if isinstance(literal, dict) else None


def extract_openapi_spec_from_project(project_root: str) -> Optional[Dict[str, Any]]:
    """Read ``app/openapi_contract.py`` and return ``OPENAPI_SPEC``, or ``None``."""
    contract = Path(project_root) / "app" / "openapi_contract.py"
    if not contract.is_file():
        return None
    try:
        return extract_openapi_spec_from_text(contract.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.debug("openapi-spec-gate: could not read %s: %s", contract, exc)
        return None


def validate_openapi_spec_dict(spec: Dict[str, Any]) -> OpenApiSpecGateResult:
    """Validate *spec* with ``openapi-spec-validator`` when installed."""
    try:
        from openapi_spec_validator import validate
    except ImportError as exc:
        return OpenApiSpecGateResult(
            status="unavailable",
            message=f"openapi-spec-validator unavailable: {exc}",
        )
    try:
        validate(spec)
    except Exception as exc:
        return OpenApiSpecGateResult(
            status="checked",
            ok=False,
            message=str(exc),
            diagnostics=[str(exc)],
        )
    return OpenApiSpecGateResult(status="checked", ok=True, message="valid")


def run_openapi_spec_gate(project_root: str) -> OpenApiSpecGateResult:
    """Validate the generated project's static ``OPENAPI_SPEC``."""
    root = Path(project_root)
    if not root.exists():
        return OpenApiSpecGateResult(status="error", message=f"path not found: {root}")
    spec = extract_openapi_spec_from_project(project_root)
    if spec is None:
        return OpenApiSpecGateResult(
            status="error",
            message="app/openapi_contract.py missing or OPENAPI_SPEC not loadable",
        )
    return validate_openapi_spec_dict(spec)
