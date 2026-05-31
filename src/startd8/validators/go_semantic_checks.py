"""Go semantic validation — regex-based checks for generated Go code.

No external tool dependency.  Six checks:
1. Unchecked errors (err returned but not checked)
2. Duplicate function names in same file
3. fmt.Println in non-main packages (should use structured logging)
4. Wildcard dot-imports (import . "pkg")
5. Python contamination (cross-language fingerprints)
6. Package/directory name mismatch
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..languages._validation_utils import GO_CONTAMINATION_FINGERPRINTS
from .semantic_checks import SemanticIssue, _basename, _is_comment_line, _stamp_file_path

# Pattern: function call with err return that's not checked
_ERR_ASSIGN_RE = re.compile(
    r'^\s*(?:\w+\s*,\s*)?err\s*(?::=|=)\s*\S+',
)
_ERR_CHECK_RE = re.compile(
    r'if\s+err\s*!=\s*nil',
)

# Pattern: func declaration — captures optional receiver type and function name.
# Go methods like ``func (p PlaceOrderPayload) Validate()`` are distinct from
# top-level functions and from methods on other receiver types.
_FUNC_DECL_RE = re.compile(
    r'^\s*func\s+(?:\(\s*\w+\s+\*?(?P<receiver>\w+)\s*\)\s+)?(?P<name>\w+)\s*\(',
)

# Pattern: fmt.Println/Printf/Print
_FMT_PRINT_RE = re.compile(
    r'\bfmt\s*\.\s*(?:Print|Println|Printf)\s*\(',
)

# Pattern: package declaration
_PACKAGE_RE = re.compile(r'^\s*package\s+(\w+)')

# Pattern: dot-import
_DOT_IMPORT_RE = re.compile(
    r'^\s*(?:import\s+)?\.\s+"[^"]+"',
)

def _check_unchecked_errors(source: str) -> List[SemanticIssue]:
    """Flag error values that are assigned but not checked.

    Detects patterns where ``err`` is assigned but the next non-blank
    line doesn't contain ``if err != nil``.
    """
    issues: List[SemanticIssue] = []
    lines = source.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        if _ERR_ASSIGN_RE.match(stripped):
            # Look ahead for err check within next 3 lines
            found_check = False
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j].strip()
                if next_line == "" or next_line.startswith("//"):
                    continue
                if _ERR_CHECK_RE.search(next_line):
                    found_check = True
                    break
                # Any other non-blank line means err was not checked
                break
            if not found_check:
                issues.append(SemanticIssue(
                    check="unchecked_error",
                    severity="warning",
                    message=(
                        "Error value `err` assigned but not checked — "
                        "add `if err != nil` handling"
                    ),
                    line=i + 1,
                ))
    return issues


def _check_duplicate_function_names(source: str) -> List[SemanticIssue]:
    """Flag duplicate function declarations in the same file.

    Methods on different receiver types (e.g., ``func (a Foo) Validate()``
    and ``func (b Bar) Validate()``) are NOT duplicates in Go — they are
    distinct method sets.  Only functions with the same (receiver, name)
    pair are flagged.
    """
    issues: List[SemanticIssue] = []
    # Key: (receiver_type_or_empty, func_name) → first line number
    seen: dict[tuple[str, str], int] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        m = _FUNC_DECL_RE.match(stripped)
        if m:
            receiver = m.group("receiver") or ""
            name = m.group("name")
            key = (receiver, name)
            if key in seen:
                if receiver:
                    label = f"({receiver}).{name}"
                else:
                    label = name
                issues.append(SemanticIssue(
                    check="duplicate_function",
                    severity="warning",
                    message=(
                        f"Duplicate function `{label}` "
                        f"(first at line {seen[key]}, again at line {i})"
                    ),
                    line=i,
                ))
            else:
                seen[key] = i
    return issues


def _check_fmt_println_in_service(source: str) -> List[SemanticIssue]:
    """Flag fmt.Println/Printf in non-main packages (should use structured logging)."""
    issues: List[SemanticIssue] = []
    # Determine package name
    pkg_match = _PACKAGE_RE.search(source)
    if pkg_match and pkg_match.group(1) == "main":
        return []  # main package can use fmt.Println

    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        if _FMT_PRINT_RE.search(stripped):
            issues.append(SemanticIssue(
                check="fmt_println_in_service",
                severity="warning",
                message=(
                    "fmt.Print*/Println in non-main package — "
                    "use structured logging (logrus, zap, slog) instead"
                ),
                line=i,
            ))
    return issues


def _check_dot_imports(source: str) -> List[SemanticIssue]:
    """Flag dot-imports (import . "pkg") which pollute the namespace."""
    issues: List[SemanticIssue] = []
    in_import_block = False
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        if stripped == "import (":
            in_import_block = True
            continue
        if in_import_block and stripped == ")":
            in_import_block = False
            continue
        if in_import_block and _DOT_IMPORT_RE.match(stripped):
            issues.append(SemanticIssue(
                check="dot_import",
                severity="warning",
                message="Dot-import pollutes namespace — use explicit import",
                line=i,
            ))
        elif not in_import_block and re.match(r'^\s*import\s+\.\s+"', stripped):
            issues.append(SemanticIssue(
                check="dot_import",
                severity="warning",
                message="Dot-import pollutes namespace — use explicit import",
                line=i,
            ))
    return issues


def _check_python_contamination(source: str) -> List[SemanticIssue]:
    """Flag Python fingerprints in Go source files (REQ-KZ-GO-201).

    Uses line-level scanning with context awareness (REQ-KZ-GO-402b):
    - Skips lines inside backtick-delimited raw string literals.
    - Skips matches after ``//`` on the same line.
    - Tracks ``/* ... */`` block comment state.
    - Reports ALL matching fingerprints (REQ-KZ-GO-402a item 3).
    """
    issues: List[SemanticIssue] = []
    seen: set[str] = set()
    in_raw_string = False
    in_block_comment = False

    for i, line in enumerate(source.splitlines(), start=1):
        # Track block comment state
        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
                # Fall through to check code after */ on this line
                line = line[line.index("*/") + 2:]
            else:
                continue
        if "/*" in line:
            if "*/" in line:
                # Single-line block comment — remove it, check remainder
                start = line.index("/*")
                end = line.index("*/") + 2
                line = line[:start] + line[end:]
            else:
                in_block_comment = True
                # Check code before /* on this line
                line = line[:line.index("/*")]

        # Track backtick raw string state (toggle per backtick)
        backtick_count = line.count("`")
        if in_raw_string:
            if backtick_count % 2 == 1:
                in_raw_string = False
            continue
        if backtick_count % 2 == 1:
            in_raw_string = True
            # Still check the part before the backtick
            check_line = line[:line.index("`")]
        else:
            check_line = line

        # Strip inline comments for matching
        comment_pos = check_line.find("//")
        check_text = check_line[:comment_pos] if comment_pos >= 0 else check_line
        stripped = check_text.strip()
        if not stripped:
            continue

        for fp in GO_CONTAMINATION_FINGERPRINTS:
            if fp in stripped and fp not in seen:
                seen.add(fp)
                issues.append(SemanticIssue(
                    check="python_contamination",
                    severity="error",
                    message=f"Python fingerprint `{fp.strip()}` in Go file — file is non-functional",
                    line=i,
                ))
    return issues


def _check_package_filepath_alignment(
    source: str,
    file_path: Optional[str],
) -> List[SemanticIssue]:
    """Flag package declarations that don't match the directory name.

    Go convention: the package name matches the directory name
    (e.g., file at ``cmd/server/main.go`` has ``package main``,
    file at ``internal/store/redis.go`` has ``package store``).
    """
    if not file_path or not file_path.endswith(".go"):
        return []

    pkg_match = _PACKAGE_RE.search(source)
    if not pkg_match:
        return []

    actual_pkg = pkg_match.group(1)

    # "package main" is required for Go executables regardless of directory name.
    # Only library packages must match their directory name.
    if actual_pkg == "main":
        return []

    from pathlib import PurePosixPath
    parent_dir = PurePosixPath(file_path).parent.name
    if not parent_dir or parent_dir == ".":
        return []

    # Go package should match directory name (except _test suffix)
    expected_pkg = parent_dir.replace("-", "")  # hyphens stripped in Go packages
    if actual_pkg == expected_pkg or actual_pkg == expected_pkg + "_test":
        return []

    return [SemanticIssue(
        check="package_dir_mismatch",
        severity="warning",
        message=(
            f"Package `{actual_pkg}` does not match directory name "
            f"`{parent_dir}` — Go convention requires package name to match directory"
        ),
    )]


# Go version sanity bounds. There is deliberately NO hard upper bound: a go.mod
# targeting a release NEWER than this validator must never be flagged as an
# error, or every freshly-generated module false-fails as new Go ships (audit
# F4 — the old fixed range (1,18,1,24) hard-errored on the released go 1.25).
# We only *warn* on implausible versions (predating modules, or absurdly high —
# a likely LLM hallucination like `go 1.99` / `go 2.5`).
_GO_VERSION_MIN_MINOR = 11        # `go` directive + modules since Go 1.11
_GO_VERSION_SANITY_MAX_MINOR = 60  # generous soft ceiling to catch hallucinations


def _go_version_issue(
    major: int, minor: int, line: int, *, what: str,
) -> "Optional[SemanticIssue]":
    """Return a *warning* SemanticIssue for an implausible Go version, else None.

    Never returns an ``error`` — a version merely newer than this validator is
    valid. Go is currently major 1 (Go 2 is unreleased); we accept any
    ``1.x`` with ``x >= _GO_VERSION_MIN_MINOR`` up to a generous soft ceiling.
    """
    if major == 1 and _GO_VERSION_MIN_MINOR <= minor <= _GO_VERSION_SANITY_MAX_MINOR:
        return None
    if major < 1 or (major == 1 and minor < _GO_VERSION_MIN_MINOR):
        reason = "predates Go modules (1.11)"
    else:
        reason = "is implausibly high — verify it is a released Go version"
    return SemanticIssue(
        check="invalid_go_version",
        severity="warning",
        message=f"{what} `{major}.{minor}` {reason}",
        line=line,
    )


_GO_DIRECTIVE_RE = re.compile(r'^\s*go\s+(\d+)\.(\d+)')
_TOOLCHAIN_RE = re.compile(r'^\s*toolchain\s+go(\d+)\.(\d+)')
_MODULE_RE = re.compile(r'^\s*module\s+\S+')


def _check_go_mod_validity(source: str) -> List[SemanticIssue]:
    """Validate go.mod structure and Go version range (REQ-KZ-GO-102).

    Checks:
    - ``module`` directive is present.
    - ``go <version>`` directive is present and within known valid range.
    - ``toolchain`` directive version (if present) is within known range.
    - No Python contamination artifacts.
    """
    issues: List[SemanticIssue] = []
    lines = source.splitlines()

    has_module = False
    has_go_directive = False

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        if _MODULE_RE.match(stripped):
            has_module = True

        go_m = _GO_DIRECTIVE_RE.match(stripped)
        if go_m:
            has_go_directive = True
            major, minor = int(go_m.group(1)), int(go_m.group(2))
            ver_issue = _go_version_issue(major, minor, i, what="Go version")
            if ver_issue is not None:
                issues.append(ver_issue)

        tc_m = _TOOLCHAIN_RE.match(stripped)
        if tc_m:
            major, minor = int(tc_m.group(1)), int(tc_m.group(2))
            ver_issue = _go_version_issue(major, minor, i, what="Toolchain version go")
            if ver_issue is not None:
                issues.append(ver_issue)

    if not has_module:
        issues.append(SemanticIssue(
            check="invalid_go_mod",
            severity="error",
            message="go.mod missing `module` directive",
            line=1,
        ))

    if not has_go_directive:
        issues.append(SemanticIssue(
            check="invalid_go_mod",
            severity="error",
            message="go.mod missing `go <version>` directive",
            line=1,
        ))

    # Check contamination in go.mod (same fingerprints as .go files)
    for fp in GO_CONTAMINATION_FINGERPRINTS:
        if fp in source:
            issues.append(SemanticIssue(
                check="python_contamination",
                severity="error",
                message=f"Python fingerprint `{fp.strip()}` in go.mod — file is non-functional",
            ))
            break  # One contamination finding is sufficient for go.mod

    return issues


def _check_dockerfile_go_version(source: str) -> List[SemanticIssue]:
    """Validate Go version in Dockerfile FROM directives.

    Flags ``golang:X.Y`` base images where X.Y is outside the known valid range.
    """
    issues: List[SemanticIssue] = []
    docker_go_re = re.compile(r'golang:(\d+)\.(\d+)')

    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.upper().startswith("FROM"):
            continue
        m = docker_go_re.search(stripped)
        if m:
            major, minor = int(m.group(1)), int(m.group(2))
            ver_issue = _go_version_issue(
                major, minor, i, what="Dockerfile Go image version",
            )
            if ver_issue is not None:
                issues.append(ver_issue)
    return issues


def run_go_semantic_checks(
    source: str,
    file_path: Optional[str] = None,
) -> List[SemanticIssue]:
    """Run all Go semantic checks on source code.

    Dispatches to file-type-specific checks based on ``file_path``:
    - ``go.mod`` → :func:`_check_go_mod_validity`
    - ``Dockerfile*`` → :func:`_check_dockerfile_go_version`
    - ``*.go`` or unknown → full Go source checks

    Args:
        source: Go source code string.
        file_path: Optional file path for context-sensitive checks.

    Returns:
        List of SemanticIssue objects.
    """
    issues: List[SemanticIssue] = []

    # Dispatch to file-type-specific checks
    fname = ""
    if file_path:
        from pathlib import PurePosixPath
        fname = PurePosixPath(file_path).name

    if fname == "go.mod":
        issues.extend(_check_go_mod_validity(source))
        return _stamp_file_path(issues, file_path)

    if fname.startswith("Dockerfile"):
        issues.extend(_check_dockerfile_go_version(source))
        issues.extend(_check_python_contamination(source))
        return _stamp_file_path(issues, file_path)

    # Standard Go source file checks
    issues.extend(_check_python_contamination(source))
    issues.extend(_check_unchecked_errors(source))
    issues.extend(_check_duplicate_function_names(source))
    issues.extend(_check_fmt_println_in_service(source))
    issues.extend(_check_dot_imports(source))
    issues.extend(_check_package_filepath_alignment(source, file_path))

    return _stamp_file_path(issues, file_path)


def check_go_version_consistency(
    go_mod_source: str,
    dockerfile_source: str,
    *,
    go_mod_path: str = "go.mod",
    dockerfile_path: str = "Dockerfile",
) -> List[SemanticIssue]:
    """Cross-check Go version between go.mod and Dockerfile.

    Verifies that the ``go X.Y`` directive in go.mod matches the
    ``golang:X.Y`` base image in the Dockerfile.  Returns issues
    when the versions disagree.

    This is a service-level check — call it when both files are
    available for the same service.
    """
    issues: List[SemanticIssue] = []

    # Extract go.mod version
    mod_version = None
    for line in go_mod_source.splitlines():
        m = _GO_DIRECTIVE_RE.match(line.strip())
        if m:
            mod_version = f"{m.group(1)}.{m.group(2)}"
            break

    # Extract Dockerfile golang version
    docker_go_re = re.compile(r'golang:(\d+\.\d+)')
    docker_version = None
    for line in dockerfile_source.splitlines():
        if line.strip().upper().startswith("FROM"):
            m = docker_go_re.search(line)
            if m:
                docker_version = m.group(1)
                break

    if mod_version and docker_version and mod_version != docker_version:
        issues.append(SemanticIssue(
            check="go_version_mismatch",
            severity="warning",
            message=(
                f"Go version mismatch: go.mod has `go {mod_version}` but "
                f"Dockerfile uses `golang:{docker_version}` — these should match"
            ),
            file_path=go_mod_path,
        ))

    return issues
