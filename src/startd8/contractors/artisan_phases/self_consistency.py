"""
Semantic self-consistency validators for generated code (AR-143 through AR-147).

These validators detect production-blocking defects that external linters miss:
placeholder literals, undeclared imports, proto field mismatches, protocol
fidelity violations, and Dockerfile coherence issues.

Three validators follow the subprocess signature used by ``rules_validators.py``::

    (code: str, enrichment) -> list[dict]

Two follow an in-process signature for cross-file checks::

    (code: str, file_path: str, service_metadata: dict | None) -> list[dict]
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bREPLACE_WITH_\w+", re.IGNORECASE),
    re.compile(r"\bYOUR_\w+_HERE\b", re.IGNORECASE),
    re.compile(r"\bCHANGE_ME\b", re.IGNORECASE),
    re.compile(r"\bPLACEHOLDER\b", re.IGNORECASE),
    re.compile(r"\bNotImplementedError\b"),
    re.compile(r"\bXXX\b"),
    re.compile(r"\bHACK\b"),
    re.compile(r"\binsert[_\s]+\w+[_\s]+here\b", re.IGNORECASE),
]

# Common import-name → PyPI-package mappings for AR-143.
_IMPORT_TO_PACKAGE: dict[str, str] = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "yaml": "PyYAML",
    "grpc": "grpcio",
    "google.protobuf": "protobuf",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "attr": "attrs",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "jose": "python-jose",
    "jwt": "PyJWT",
    "magic": "python-magic",
    "gi": "PyGObject",
    "serial": "pyserial",
}

_BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
    ".whl", ".egg", ".zip", ".tar", ".gz",
})

_GRPC_INDICATORS: list[re.Pattern[str]] = [
    re.compile(r"\bgrpc\b"),
    re.compile(r"\b\w+_pb2\b"),
    re.compile(r"\b\w+_pb2_grpc\b"),
    re.compile(r"\binsecure_channel\b"),
    re.compile(r"\bsecure_channel\b"),
    re.compile(r"\badd_\w+Servicer_to_server\b"),
    re.compile(r"\bServicer\b"),
]

_HTTP_INDICATORS: list[re.Pattern[str]] = [
    re.compile(r"\brequests\.\w+"),
    re.compile(r"\bhttpx\.\w+"),
    re.compile(r"\baiohttp\b"),
    re.compile(r"\bFlask\b"),
    re.compile(r"\bFastAPI\b"),
    re.compile(r"\bDjango\b"),
    re.compile(r"\bapp\.route\b"),
    re.compile(r"\b@app\.\w+\b"),
    re.compile(r"\bHTTPException\b"),
    re.compile(r"\burllib\b"),
]

_PROTO_FIELD_RE = re.compile(
    r"^\s*(?:repeated\s+|optional\s+|required\s+)?\w+\s+(\w+)\s*=\s*\d+",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_number(code: str, pos: int) -> int:
    """Return the 1-based line number for a character offset in *code*."""
    return code[:pos].count("\n") + 1


def _is_binary_extension(path_str: str) -> bool:
    """Return True if *path_str* has a binary extension we should skip."""
    return Path(path_str).suffix.lower() in _BINARY_EXTENSIONS


def _read_requirements_from_cwd(cwd: str | None) -> set[str] | None:
    """Read package names from ``requirements.txt`` in *cwd*.

    Returns a normalized set of package names (lowercased, hyphens → underscores),
    or ``None`` if the file is absent or unreadable.
    """
    if not cwd:
        return None
    req_path = Path(cwd) / "requirements.txt"
    if not req_path.exists():
        return None
    try:
        names: set[str] = set()
        for line in req_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Strip version specifiers
            for sep in (">=", "<=", "==", "!=", "~=", ">", "<", "[", ";"):
                if sep in line:
                    line = line[:line.index(sep)]
                    break
            pkg = line.strip().lower().replace("-", "_")
            if pkg:
                names.add(pkg)
        return names if names else None
    except OSError:
        return None


def _collect_proto_fields(project_root: Path | None) -> set[str]:
    """Collect field names from all ``.proto`` files under *project_root*."""
    if project_root is None or not project_root.is_dir():
        return set()
    fields: set[str] = set()
    try:
        for proto_file in project_root.rglob("*.proto"):
            try:
                content = proto_file.read_text(encoding="utf-8")
                for m in _PROTO_FIELD_RE.finditer(content):
                    fields.add(m.group(1))
            except OSError:
                continue
    except OSError:
        pass
    return fields


def _looks_like_proto_access(name: str) -> bool:
    """Return True if *name* looks like a protobuf field accessor.

    Heuristic: names ending in common protobuf suffixes or using
    snake_case that matches typical proto field patterns.
    """
    return bool(name and "_" in name and name == name.lower())


# ---------------------------------------------------------------------------
# AR-146: Placeholder Detection (subprocess signature)
# ---------------------------------------------------------------------------

def validate_placeholder_detection(code: str, enrichment: Any) -> list[dict[str, Any]]:
    """Scan for placeholder literals that should not ship to production.

    Detects TODO, FIXME, REPLACE_WITH_*, YOUR_*_HERE, CHANGE_ME,
    PLACEHOLDER, NotImplementedError, XXX, HACK, and similar markers.
    """
    issues: list[dict[str, Any]] = []
    for pattern in _PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(code):
            issues.append({
                "validator": "placeholder_detection",
                "message": f"Placeholder found: {match.group()!r}",
                "line": _line_number(code, match.start()),
                "confidence": 0.9,
            })
    return issues


# ---------------------------------------------------------------------------
# AR-143: Import Dependency Validation (subprocess signature)
# ---------------------------------------------------------------------------

def validate_import_dependency(code: str, enrichment: Any) -> list[dict[str, Any]]:
    """Check that imported packages are declared in requirements.

    Uses ``ast.parse()`` to extract imports, then cross-references against
    ``requirements.txt`` (from ``enrichment.cwd`` or the current directory),
    the ``_IMPORT_TO_PACKAGE`` mapping, and ``sys.stdlib_module_names``.
    """
    issues: list[dict[str, Any]] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    # Collect available packages from requirements
    cwd = getattr(enrichment, "cwd", None)
    declared_packages = _read_requirements_from_cwd(cwd)
    if declared_packages is None:
        # No requirements.txt → cannot validate
        return issues

    # Build set of stdlib modules
    stdlib: set[str] = set()
    if hasattr(sys, "stdlib_module_names"):
        stdlib = sys.stdlib_module_names  # type: ignore[assignment]

    # Also check enrichment constraints for "Only import from:" lists
    importable_from_constraint: set[str] | None = None
    for constraint in getattr(enrichment, "prompt_constraints", []):
        if isinstance(constraint, str) and constraint.startswith("Only import from:"):
            names_str = constraint.split(":", 1)[1].strip()
            importable_from_constraint = {n.strip() for n in names_str.split(",") if n.strip()}
            break

    for node in ast.walk(tree):
        top_level: str | None = None
        lineno: int = 0

        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".")[0]
                lineno = node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module and (not node.level or node.level == 0):
                top_level = node.module.split(".")[0]
                lineno = node.lineno

        if top_level is None:
            continue

        # Skip stdlib
        if top_level in stdlib:
            continue

        # Check if package is declared (with import-to-package mapping)
        pkg_name = _IMPORT_TO_PACKAGE.get(top_level, top_level)
        normalized = pkg_name.lower().replace("-", "_")

        is_declared = normalized in declared_packages

        # Also check if importable from constraint allows it
        if not is_declared and importable_from_constraint is not None:
            is_declared = top_level in importable_from_constraint

        if not is_declared:
            issues.append({
                "validator": "import_dependency",
                "message": (
                    f"Import '{top_level}' (package '{pkg_name}') "
                    f"not found in requirements.txt"
                ),
                "line": lineno,
                "confidence": 0.85,
            })

    return issues


# ---------------------------------------------------------------------------
# AR-145: Proto Field Reference Validation (subprocess signature)
# ---------------------------------------------------------------------------

def validate_proto_field_references(code: str, enrichment: Any) -> list[dict[str, Any]]:
    """Detect singular/plural mismatches between .proto fields and code.

    Collects field names from ``.proto`` files under the project root,
    then scans AST attribute accesses for near-misses (e.g. ``item`` vs
    ``items``, ``product_id`` vs ``product_ids``).
    """
    issues: list[dict[str, Any]] = []

    cwd = getattr(enrichment, "cwd", None)
    project_root = Path(cwd) if cwd else None
    proto_fields = _collect_proto_fields(project_root)
    if not proto_fields:
        return issues

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    # Build plural/singular variants for matching
    field_variants: dict[str, str] = {}
    for field in proto_fields:
        # singular→plural and plural→singular
        if field.endswith("s"):
            field_variants[field[:-1]] = field  # items → item maps to items
        else:
            field_variants[field + "s"] = field  # item → items maps to item

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and _looks_like_proto_access(node.attr):
            attr = node.attr
            # Check if this is a near-miss: the attribute isn't a proto field
            # but a plural/singular variant is
            if attr not in proto_fields and attr in field_variants:
                correct_field = field_variants[attr]
                issues.append({
                    "validator": "proto_field_references",
                    "message": (
                        f"Possible proto field mismatch: used '.{attr}' "
                        f"but proto defines '{correct_field}'"
                    ),
                    "line": node.lineno,
                    "confidence": 0.7,
                })

    return issues


# ---------------------------------------------------------------------------
# AR-144: Protocol Fidelity (in-process signature)
# ---------------------------------------------------------------------------

def validate_protocol_fidelity(
    code: str,
    file_path: str,
    service_metadata: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Cross-reference transport indicators in code against declared protocol.

    Detects mismatches like HTTP client usage in a gRPC-declared service
    (DEV-001) or gRPC imports in an HTTP-declared service (DEV-004).
    """
    issues: list[dict[str, Any]] = []
    if not service_metadata:
        return issues

    transport = service_metadata.get("transport_protocol", "").lower()
    if not transport:
        return issues

    has_grpc = any(p.search(code) for p in _GRPC_INDICATORS)
    has_http = any(p.search(code) for p in _HTTP_INDICATORS)

    if transport == "grpc" and has_http and not has_grpc:
        # HTTP patterns in a gRPC-declared service (DEV-001 pattern)
        for pattern in _HTTP_INDICATORS:
            for match in pattern.finditer(code):
                issues.append({
                    "validator": "protocol_fidelity",
                    "message": (
                        f"HTTP indicator '{match.group()}' found in "
                        f"gRPC-declared service"
                    ),
                    "line": _line_number(code, match.start()),
                    "file": file_path,
                    "confidence": 0.9,
                })
                break  # One issue per pattern is enough
    elif transport == "http" and has_grpc and not has_http:
        # gRPC patterns in an HTTP-declared service
        for pattern in _GRPC_INDICATORS:
            for match in pattern.finditer(code):
                issues.append({
                    "validator": "protocol_fidelity",
                    "message": (
                        f"gRPC indicator '{match.group()}' found in "
                        f"HTTP-declared service"
                    ),
                    "line": _line_number(code, match.start()),
                    "file": file_path,
                    "confidence": 0.9,
                })
                break

    return issues


# ---------------------------------------------------------------------------
# AR-147: Dockerfile Coherence (in-process signature)
# ---------------------------------------------------------------------------

_DOCKERFILE_FROM_RE = re.compile(r"^\s*FROM\s+(\S+)", re.MULTILINE | re.IGNORECASE)
_DOCKERFILE_HEALTHCHECK_RE = re.compile(
    r"^\s*HEALTHCHECK\s+.*?(?:CMD|cmd)\s+(.*)",
    re.MULTILINE | re.IGNORECASE,
)


def validate_dockerfile_coherence(
    code: str,
    file_path: str,
    service_metadata: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Validate Dockerfile base images and healthchecks against service metadata.

    Detects mismatches like gRPC health probes in a Flask service (DEV-004)
    or missing HEALTHCHECK for production Dockerfiles.
    """
    issues: list[dict[str, Any]] = []

    # Only run on Dockerfile-like files
    fname = Path(file_path).name
    if not (fname.startswith("Dockerfile") or fname == "dockerfile"):
        return issues

    transport = ""
    if service_metadata:
        transport = service_metadata.get("transport_protocol", "").lower()

    # Check FROM base image
    from_match = _DOCKERFILE_FROM_RE.search(code)
    if from_match and transport:
        base_image = from_match.group(1).lower()
        # gRPC services shouldn't typically use Flask/Django base images
        if transport == "grpc" and any(
            kw in base_image for kw in ("flask", "django", "uvicorn", "gunicorn")
        ):
            issues.append({
                "validator": "dockerfile_coherence",
                "message": (
                    f"Base image '{from_match.group(1)}' suggests HTTP framework "
                    f"but service declares gRPC transport"
                ),
                "line": _line_number(code, from_match.start()),
                "file": file_path,
                "confidence": 0.8,
            })

    # Check HEALTHCHECK command
    hc_match = _DOCKERFILE_HEALTHCHECK_RE.search(code)
    if hc_match and transport:
        hc_cmd = hc_match.group(1).lower()
        if transport == "grpc" and ("curl" in hc_cmd or "wget" in hc_cmd):
            # gRPC services should use grpc_health_probe, not HTTP probes
            issues.append({
                "validator": "dockerfile_coherence",
                "message": (
                    "HEALTHCHECK uses HTTP probe (curl/wget) "
                    "but service declares gRPC transport — "
                    "consider grpc_health_probe"
                ),
                "line": _line_number(code, hc_match.start()),
                "file": file_path,
                "confidence": 0.85,
            })
        elif transport == "http" and "grpc_health_probe" in hc_cmd:
            # HTTP services shouldn't use gRPC health probes
            issues.append({
                "validator": "dockerfile_coherence",
                "message": (
                    "HEALTHCHECK uses grpc_health_probe "
                    "but service declares HTTP transport"
                ),
                "line": _line_number(code, hc_match.start()),
                "file": file_path,
                "confidence": 0.85,
            })

    return issues
