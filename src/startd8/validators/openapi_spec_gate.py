"""OpenAPI spec validation gate for generated static contracts (OpenAPI Role 1, M2 / FR-6).

Validates the ``OPENAPI_SPEC`` dict materialized in ``app/openapi_contract.py``. Absent
``openapi-spec-validator`` ⇒ ``unavailable`` ⇒ **non-pass** (never a silent PASS) — the same
loud-degradation rule as ``boot_smoke`` and ``python_toolchain``.
"""

from __future__ import annotations

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


def extract_openapi_spec_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Load ``OPENAPI_SPEC`` from generated contract module text without importing ``app``."""
    try:
        head = text.split("def route_paths", 1)[0]
        ns: dict = {}
        exec(compile(head, "<openapi_contract>", "exec"), ns)  # noqa: S102
        spec = ns.get("OPENAPI_SPEC")
        return spec if isinstance(spec, dict) else None
    except Exception as exc:
        logger.debug("openapi-spec-gate: could not extract OPENAPI_SPEC: %s", exc)
        return None


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
