"""Dockerfile structural validator (REQ-MP-322).

Validates Dockerfile content against known directive set and
best-practice rules from docker-file-assembly-via-python.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from startd8.logging_config import get_logger

logger = get_logger(__name__)


KNOWN_DIRECTIVES = frozenset({
    "FROM", "RUN", "CMD", "ENTRYPOINT", "COPY", "ADD", "WORKDIR",
    "ENV", "EXPOSE", "VOLUME", "USER", "ARG", "LABEL", "HEALTHCHECK",
    "SHELL", "STOPSIGNAL", "ONBUILD",
})

_PARSER_DIRECTIVE_PATTERN = re.compile(r"^#\s*(syntax|escape)\s*=")

_SECRET_PATTERN = re.compile(
    r"(?i)(password|secret|token|api_key|private_key|auth)\s*=\s*\S+"
)


@dataclass(frozen=True)
class DockerfileValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    directives_found: list[str] = field(default_factory=list)
    stage_count: int = 0


def validate_dockerfile(content: str) -> DockerfileValidationResult:
    """Validate Dockerfile content.

    Returns a result with:
    - valid: True if no errors (warnings and advisories don't affect validity)
    - errors: Structural problems (DV-001 through DV-005)
    - warnings: Structural issues at warning severity
    - advisories: Best-practice recommendations (DV-BP-001 through DV-BP-011)
    """
    errors: list[str] = []
    warnings: list[str] = []
    advisories: list[str] = []
    directives_found: list[str] = []

    _check_structural_rules(content, errors, warnings, directives_found)
    stage_count = directives_found.count("FROM")

    if not errors:
        _check_best_practices(content, directives_found, advisories)

    valid = len(errors) == 0

    return DockerfileValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        advisories=advisories,
        directives_found=directives_found,
        stage_count=stage_count,
    )


# ── Structural rules (DV-001 through DV-005) ────────────────────────


def _check_structural_rules(
    content: str,
    errors: list[str],
    warnings: list[str],
    directives_found: list[str],
) -> None:
    lines = content.splitlines()

    # DV-003: No empty Dockerfile
    non_blank = [line for line in lines if line.strip()]
    non_comment = [line for line in non_blank if not line.strip().startswith("#")]
    if not non_comment:
        errors.append("DV-003: Dockerfile is empty (no directive lines)")
        return

    # DV-005: Parser directives must appear before any directive or blank line
    _check_parser_directives(lines, warnings)

    # Parse directives, tracking continuation lines
    in_continuation = False
    found_from = False

    for line in lines:
        stripped = line.strip()

        # Skip blank lines and comments
        if not stripped:
            in_continuation = False
            continue
        if stripped.startswith("#"):
            continue

        # Continuation from previous line
        if in_continuation:
            in_continuation = stripped.endswith("\\")
            continue

        # R1-S5: Degenerate continuation — line is only a backslash
        if stripped == "\\":
            in_continuation = True
            continue

        # This is a directive line
        first_word = stripped.split()[0].upper()

        # Skip flag-only lines (shouldn't appear outside continuation, but be safe)
        if first_word.startswith("--"):
            continue

        if first_word in KNOWN_DIRECTIVES:
            directives_found.append(first_word)
            if first_word == "FROM":
                found_from = True
        else:
            # DV-002: Unknown directive
            warnings.append(f"DV-002: Unknown directive '{first_word}'")

        in_continuation = stripped.endswith("\\")

    # DV-001: Must have at least one FROM
    if not found_from:
        errors.append("DV-001: No FROM directive found")


def _check_parser_directives(lines: list[str], warnings: list[str]) -> None:
    """DV-005: Parser directives must be at the very top."""
    found_non_parser = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Blank line ends parser directive region
            found_non_parser = True
            continue
        if stripped.startswith("#"):
            if _PARSER_DIRECTIVE_PATTERN.match(stripped):
                if found_non_parser:
                    warnings.append(
                        "DV-005: Parser directive after non-parser content — "
                        "will be ignored by Docker"
                    )
            # Regular comments don't end the region
            continue
        # Non-comment, non-blank → end of parser directive region
        found_non_parser = True


# ── Best-practice advisory rules (DV-BP-001 through DV-BP-011) ──────


def _check_best_practices(
    content: str,
    directives_found: list[str],
    advisories: list[str],
) -> None:
    lines = content.splitlines()

    # DV-BP-001: Pinned base image version
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            # R1-S10: Skip flags (--platform=..., --network=...)
            image_parts = [p for p in parts[1:] if not p.startswith("--")]
            image_ref = image_parts[0] if image_parts else ""
            # Skip AS alias
            if image_ref.upper() == "AS":
                continue
            if image_ref and (":" not in image_ref or image_ref.endswith(":latest")):
                if image_ref.lower() not in ("scratch",):
                    advisories.append(
                        f"DV-BP-001: FROM '{image_ref}' should use a pinned version tag"
                    )

    # DV-BP-002: Non-root USER
    if "USER" not in directives_found:
        advisories.append("DV-BP-002: No USER directive — container runs as root")

    # DV-BP-003: COPY over ADD
    if "ADD" in directives_found:
        advisories.append(
            "DV-BP-003: Prefer COPY over ADD unless archive extraction is needed"
        )

    # DV-BP-004: Exec form CMD/ENTRYPOINT
    for line in lines:
        stripped = line.strip()
        for directive in ("CMD ", "ENTRYPOINT "):
            if stripped.upper().startswith(directive):
                rest = stripped[len(directive):].strip()
                if rest and not rest.startswith("["):
                    advisories.append(
                        f"DV-BP-004: {directive.strip()} uses shell form — "
                        "prefer exec form [\"binary\", \"arg\"] for proper signal handling"
                    )

    # DV-BP-005: Deps before source
    _check_layer_ordering(lines, advisories)

    # DV-BP-006: Combined apt-get
    _check_apt_get_combined(lines, advisories)

    # DV-BP-007: Multi-stage for production
    if directives_found.count("FROM") < 2:
        advisories.append(
            "DV-BP-007: Single-stage build — consider multi-stage for production"
        )

    # DV-BP-008: HEALTHCHECK
    if "HEALTHCHECK" not in directives_found:
        advisories.append("DV-BP-008: No HEALTHCHECK directive")

    # DV-BP-009: LABEL metadata
    if "LABEL" not in directives_found:
        advisories.append("DV-BP-009: No LABEL metadata")

    # DV-BP-010: Alpine warning for Python
    for line in lines:
        stripped = line.strip()
        if (
            stripped.upper().startswith("FROM ")
            and "python" in stripped.lower()
            and "alpine" in stripped.lower()
        ):
            advisories.append(
                "DV-BP-010: Python + Alpine may break C-extension wheels — prefer -slim"
            )

    # DV-BP-011: No plaintext secrets in ENV (R1-S8)
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("ENV ") and _SECRET_PATTERN.search(stripped):
            advisories.append(
                "DV-BP-011: ENV may contain a plaintext secret — "
                "use runtime env vars or Docker secrets instead"
            )


    # DV-BP-012: Cross-stage base image version consistency
    _check_stage_version_consistency(lines, advisories)


def _extract_image_version(image_ref: str) -> tuple[str, str]:
    """Extract (image_family, major_version) from a FROM image reference.

    Examples:
        'eclipse-temurin:24.0.2_12-jdk-noble@sha256:...' → ('eclipse-temurin', '24')
        'golang:1.25-alpine' → ('golang', '1')
        'python:3.12-slim' → ('python', '3')
        'mcr.microsoft.com/dotnet/sdk:10.0' → ('dotnet/sdk', '10')
    """
    import re as _re

    # Strip digest
    ref = image_ref.split("@")[0]
    # Split image:tag
    if ":" in ref:
        image, tag = ref.rsplit(":", 1)
    else:
        return ref, ""
    # Normalize image family (strip registry prefix for comparison)
    family = image.split("/")[-1] if "/" in image else image
    # For .NET, use last two segments (dotnet/sdk, dotnet/runtime-deps)
    if "dotnet" in image or "microsoft" in image:
        parts = image.split("/")
        family = "/".join(parts[-2:]) if len(parts) >= 2 else family
    # Extract major version from tag (first numeric segment)
    m = _re.match(r"(\d+)", tag)
    major = m.group(1) if m else ""
    return family, major


def _check_stage_version_consistency(
    lines: list[str], advisories: list[str],
) -> None:
    """DV-BP-012: Warn if builder and runtime stages use incompatible major versions.

    Detects cases like JDK 24 (builder) → JRE 25 (runtime) where bytecode
    compiled on one version may not run on another.
    """
    stages: list[tuple[str, str]] = []  # (family, major_version)
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            image_parts = [p for p in parts[1:] if not p.startswith("--")]
            image_ref = image_parts[0] if image_parts else ""
            if image_ref.upper() == "AS" or image_ref.lower() == "scratch":
                continue
            family, major = _extract_image_version(image_ref)
            if family and major:
                stages.append((family, major))

    if len(stages) < 2:
        return

    # Compare major versions across stages with compatible families
    # e.g., temurin:24-jdk and temurin:25-jre share "temurin" family
    builder = stages[0]
    for runtime in stages[1:]:
        # Check if families are related (same base name, ignoring
        # jdk/jre/sdk/runtime suffixes)
        b_base = builder[0].split("-")[0].lower()
        r_base = runtime[0].split("-")[0].lower()
        if b_base == r_base and builder[1] != runtime[1]:
            advisories.append(
                f"DV-BP-012: Cross-stage version mismatch — "
                f"builder uses major version {builder[1]} "
                f"but runtime uses {runtime[1]} (risk: bytecode/ABI incompatibility)"
            )
            break


def _check_layer_ordering(lines: list[str], advisories: list[str]) -> None:
    """DV-BP-005: Check that dependency files are copied before source."""
    saw_requirements_copy = False
    for line in lines:
        stripped = line.strip()
        if not stripped.upper().startswith("COPY "):
            continue
        rest = stripped[5:].strip()
        # COPY requirements.txt . / COPY go.mod .
        if any(
            dep_file in rest
            for dep_file in ("requirements.txt", "go.mod", "go.sum", "package.json")
        ):
            saw_requirements_copy = True
        elif saw_requirements_copy and rest.startswith(". "):
            # COPY . . after requirements — good ordering
            pass
        elif not saw_requirements_copy and rest.startswith(". "):
            advisories.append(
                "DV-BP-005: COPY . before dependency file copy — "
                "breaks Docker layer caching"
            )
            break


def _check_apt_get_combined(lines: list[str], advisories: list[str]) -> None:
    """DV-BP-006: apt-get update and install should be in the same RUN."""
    update_line = None
    install_line = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "apt-get update" in stripped:
            update_line = i
        if "apt-get install" in stripped:
            install_line = i

    if update_line is not None and install_line is not None:
        # Check if they're in different RUN directives
        # Simple heuristic: if there's a non-continuation line between them, flag it
        if update_line != install_line:
            # Check if the lines are part of the same RUN (via continuation)
            all_continuation = True
            for j in range(update_line, install_line):
                if not lines[j].rstrip().endswith("\\") and j != install_line:
                    all_continuation = False
                    break
            if not all_continuation:
                advisories.append(
                    "DV-BP-006: apt-get update and install in separate RUN "
                    "commands — combine to avoid stale cache"
                )
