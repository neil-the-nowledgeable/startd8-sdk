"""C# semantic validation — regex-based checks for generated C# code.

No external tool dependency (no .NET SDK required).  Eight checks:
1. Console.WriteLine() in service classes (should use ILogger<T>)
2. SQL injection risk via string interpolation
3. Interface file (IFoo.cs) containing class declarations
4. Missing <Nullable>enable</Nullable> in .csproj
5. Empty catch blocks (swallow exceptions silently)
6. Async methods without await expressions
7. Missing explicit access modifiers on class declarations
8. Global using static directives (namespace pollution)

Known limitation: comment skip only catches ``//`` and ``/*`` at line start.
Multi-line ``/* ... */`` blocks and mid-line comments may cause false positives.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .semantic_checks import SemanticIssue, _basename, _is_comment_line, _stamp_file_path

_SQL_KW = r'(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|EXECUTE|TRUNCATE)\b'
_SQL_INTERPOLATION_RE = re.compile(rf'\$"[^"]*\b{_SQL_KW}[^"]*\{{', re.IGNORECASE)
_SQL_CONCAT_RE = re.compile(rf'"[^"]*\b{_SQL_KW}[^"]*"\s*\+', re.IGNORECASE)

# P1 extension: catch WHERE/SET/VALUES clauses with user-input interpolation
# on a *different* line from the SQL keyword (multi-line concatenated SQL).
_SQL_CLAUSE_KW = r'(?:WHERE|SET|VALUES|AND|OR|HAVING|ON\s+CONFLICT)\b'
_SQL_CLAUSE_INTERPOLATION_RE = re.compile(
    rf'\$"[^"]*\b{_SQL_CLAUSE_KW}\s[^"]*\{{', re.IGNORECASE,
)
# Catch $"...'{variable}'..." patterns — quoting user input in SQL is
# a hallmark of injection-vulnerable code (parameterized queries don't quote).
_SQL_QUOTED_VAR_RE = re.compile(
    r"""\$"[^"]*'\{[^}]+\}'[^"]*" """.strip(), re.IGNORECASE,
)

# REQ-KZ-CS-200i: Spanner parameterized query suppression patterns.
# When SpannerParameterCollection or SpannerParameter is used nearby,
# table-name interpolation (static readonly fields) is safe.
_SPANNER_PARAM_RE = re.compile(
    r'SpannerParameterCollection|SpannerParameter|SpannerDbType\.\w+|'
    r'Parameters\.Add\s*\(',
    re.IGNORECASE,
)
# Static readonly or const fields are compile-time constants — safe to interpolate.
_STATIC_CONST_RE = re.compile(
    r'(?:static\s+readonly|const)\s+string\s+\w+\s*=',
)


def _check_console_writeline(source: str) -> List[SemanticIssue]:
    """Flag Console.Write/Console.WriteLine in service classes."""
    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        if re.search(r'\bConsole\s*\.\s*Write(?:Line)?\s*\(', line):
            issues.append(SemanticIssue(
                check="console_writeline_in_service",
                severity="warning",
                message=(
                    f"Console.Write/WriteLine detected — "
                    f"use ILogger<T> via constructor DI instead"
                ),
                line=i,
            ))
    return issues


def _check_sql_injection_risk(source: str) -> List[SemanticIssue]:
    r"""Flag string interpolation or concatenation containing SQL keywords.

    Detects patterns like:
    - $"SELECT ... {variable}"
    - $"INSERT INTO ... {variable}"
    - "DELETE FROM " + variable

    Suppresses when Spanner parameterized query patterns are nearby
    (REQ-KZ-CS-200i) or when the interpolated variable is a static
    readonly / const field (compile-time constant, not user input).
    """
    issues: List[SemanticIssue] = []
    lines = source.splitlines()

    # Pre-scan: does the file use Spanner parameterized queries?
    has_spanner_params = bool(_SPANNER_PARAM_RE.search(source))

    # Pre-scan: collect names of static readonly / const string fields.
    const_names: set[str] = set()
    for raw_line in lines:
        m = _STATIC_CONST_RE.search(raw_line)
        if m:
            # Extract the field name: "static readonly string TableName = ..."
            after = raw_line[m.end():].strip().rstrip(";").strip('"').strip("'")
            name_match = re.search(r'(\w+)\s*=', raw_line[m.start():])
            if name_match:
                const_names.add(name_match.group(1))

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # --- Determine which regex matched ---
        matched_pattern: Optional[str] = None
        if _SQL_INTERPOLATION_RE.search(stripped):
            matched_pattern = "interpolation"
        elif _SQL_CONCAT_RE.search(stripped):
            matched_pattern = "concatenation"
        elif _SQL_CLAUSE_INTERPOLATION_RE.search(stripped):
            matched_pattern = "clause"
        elif _SQL_QUOTED_VAR_RE.search(stripped):
            matched_pattern = "quoted"
        else:
            continue

        # --- REQ-KZ-CS-200i: Spanner parameterized query exemption ---
        if has_spanner_params and matched_pattern in ("interpolation", "clause"):
            # Check ±10 lines for SpannerParameterCollection usage
            context_start = max(0, i - 11)
            context_end = min(len(lines), i + 10)
            context_text = "\n".join(lines[context_start:context_end])
            if _SPANNER_PARAM_RE.search(context_text):
                # Check if ALL interpolated vars are const/static readonly
                interp_vars = re.findall(r'\{(\w+)', stripped)
                if interp_vars and all(v in const_names for v in interp_vars):
                    continue  # All variables are constants — safe
                # Even if not all const, Spanner params nearby means the
                # user-input variables are parameterized — suppress
                if _SPANNER_PARAM_RE.search(context_text):
                    continue

        # Check if all interpolated variables are static readonly / const
        if matched_pattern in ("interpolation", "clause"):
            interp_vars = re.findall(r'\{(\w+)', stripped)
            if interp_vars and all(v in const_names for v in interp_vars):
                continue  # Only constants interpolated — not user input

        # --- Emit finding ---
        if matched_pattern == "interpolation":
            issues.append(SemanticIssue(
                check="sql_injection_risk",
                severity="error",
                message=(
                    "SQL injection risk: string interpolation in SQL query — "
                    "use parameterized queries instead"
                ),
                line=i,
            ))
        elif matched_pattern == "concatenation":
            issues.append(SemanticIssue(
                check="sql_injection_risk",
                severity="error",
                message=(
                    "SQL injection risk: string concatenation in SQL query — "
                    "use parameterized queries instead"
                ),
                line=i,
            ))
        elif matched_pattern == "clause":
            issues.append(SemanticIssue(
                check="sql_injection_risk",
                severity="error",
                message=(
                    "SQL injection risk: interpolated variable in SQL clause — "
                    "use parameterized queries (e.g. cmd.Parameters.AddWithValue)"
                ),
                line=i,
            ))
        elif matched_pattern == "quoted":
            issues.append(SemanticIssue(
                check="sql_injection_risk",
                severity="error",
                message=(
                    "SQL injection risk: quoted interpolated variable in SQL — "
                    "use parameterized queries instead of quoting"
                ),
                line=i,
            ))
    return issues


def _check_interface_file_contains_class(
    source: str,
    file_path: Optional[str],
) -> List[SemanticIssue]:
    """Flag IFoo.cs files that contain class declarations (not just interface)."""
    if not file_path:
        return []

    name = _basename(file_path)
    stem = name.rsplit(".", 1)[0] if "." in name else name

    # Only check files matching IFoo.cs pattern
    if not (
        name.endswith(".cs")
        and stem.startswith("I")
        and len(stem) > 1
        and stem[1].isupper()
    ):
        return []

    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        # Match class declarations (but not within comments)
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        if re.search(
            r'\b(?:public|private|protected|internal)?\s*(?:sealed\s+|abstract\s+|static\s+|partial\s+)*class\s+\w+',
            stripped,
        ):
            issues.append(SemanticIssue(
                check="interface_file_contains_class",
                severity="warning",
                message=(
                    f"Interface file `{name}` contains a class declaration — "
                    f"IFoo.cs should contain ONLY the interface definition. "
                    f"Misplacing the class here can leave the interface undefined "
                    f"for consumers"
                ),
                line=i,
            ))
    return issues


def _check_missing_nullable_in_csproj(
    source: str,
    file_path: Optional[str],
) -> List[SemanticIssue]:
    """Flag .csproj files missing <Nullable>enable</Nullable>."""
    if not file_path:
        return []

    name = _basename(file_path)

    if not name.endswith(".csproj"):
        return []

    if "<Nullable>enable</Nullable>" in source:
        return []

    return [SemanticIssue(
        check="missing_nullable_in_csproj",
        severity="warning",
        message=(
            f"`{name}` is missing `<Nullable>enable</Nullable>` in PropertyGroup"
        ),
    )]


_EMPTY_CATCH_RE = re.compile(
    r'catch\s*(?:\([^)]*\))?\s*\{\s*\}',
)

_ASYNC_METHOD_RE = re.compile(
    r'\basync\s+(?:Task|ValueTask|IAsyncEnumerable)(?:<[^>]+>)?\s+\w+\s*\(',
)

_AWAIT_RE = re.compile(r'\bawait\b')

_CS_ACCESS_MODIFIER_RE = re.compile(r'\b(?:public|private|protected|internal)\b')

_CS_CLASS_NO_MODIFIER_RE = re.compile(
    r'^\s*(?:sealed\s+|abstract\s+|static\s+|partial\s+)*class\s+\w+',
)


def _check_empty_catch_blocks(source: str) -> List[SemanticIssue]:
    """Flag empty catch blocks that swallow exceptions silently."""
    issues: List[SemanticIssue] = []
    lines = source.splitlines()
    cleaned_lines = []
    for line in lines:
        if _is_comment_line(line.strip()):
            cleaned_lines.append("")
        else:
            cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    for m in _EMPTY_CATCH_RE.finditer(cleaned):
        line_num = cleaned[:m.start()].count('\n') + 1
        if not any(iss.line == line_num for iss in issues):
            issues.append(SemanticIssue(
                check="empty_catch_block",
                severity="warning",
                message=(
                    "Empty catch block — exceptions should be logged or re-thrown"
                ),
                line=line_num,
            ))
    return issues


def _check_missing_async_await(source: str) -> List[SemanticIssue]:
    """Flag async methods that don't contain any await expressions."""
    issues: List[SemanticIssue] = []
    lines = source.splitlines()
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        if _ASYNC_METHOD_RE.search(stripped):
            # Look ahead in the method body for an await
            depth = 0
            found_await = False
            started = False
            for j in range(i - 1, len(lines)):
                for ch in lines[j]:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                if started and depth == 0:
                    break
                if _AWAIT_RE.search(lines[j]):
                    found_await = True
                    break
            if not found_await and started:
                issues.append(SemanticIssue(
                    check="missing_async_await",
                    severity="warning",
                    message=(
                        "Async method without `await` — "
                        "consider making synchronous or adding await"
                    ),
                    line=i,
                ))
    return issues


def _check_missing_access_modifiers(source: str) -> List[SemanticIssue]:
    """Flag class declarations missing explicit access modifiers."""
    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        if _CS_CLASS_NO_MODIFIER_RE.match(stripped):
            if not _CS_ACCESS_MODIFIER_RE.search(stripped):
                issues.append(SemanticIssue(
                    check="missing_access_modifier",
                    severity="warning",
                    message="Class declaration missing explicit access modifier",
                    line=i,
                ))
    return issues


def _check_wildcard_usings(source: str) -> List[SemanticIssue]:
    """Flag global using static directives (namespace pollution)."""
    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        if re.match(r'^\s*global\s+using\s+static\b', stripped):
            issues.append(SemanticIssue(
                check="global_using_static",
                severity="warning",
                message="Global using static pollutes namespace — use explicit imports",
                line=i,
            ))
    return issues


def run_csharp_semantic_checks(
    source: str,
    file_path: Optional[str] = None,
) -> List[SemanticIssue]:
    """Run all C# semantic checks on source code.

    Args:
        source: C# source code or .csproj XML content.
        file_path: Optional file path for context-sensitive checks.

    Returns:
        List of SemanticIssue objects.
    """
    issues: List[SemanticIssue] = []

    # .sln wrong-content check: solution file should NOT contain C# code
    if file_path and file_path.endswith(".sln"):
        if "namespace " in source or "using System" in source:
            issues.append(SemanticIssue(
                check="wrong_file_content",
                severity="error",
                message=(
                    "Solution file contains C# code instead of MSBuild solution format. "
                    "Expected: 'Microsoft Visual Studio Solution File, Format Version 12.00'"
                ),
            ))
        return _stamp_file_path(issues, file_path)

    # .csproj check
    if file_path and file_path.endswith(".csproj"):
        issues.extend(_check_missing_nullable_in_csproj(source, file_path))
        return _stamp_file_path(issues, file_path)

    # .cs source checks
    issues.extend(_check_console_writeline(source))
    issues.extend(_check_sql_injection_risk(source))
    issues.extend(_check_interface_file_contains_class(source, file_path))
    issues.extend(_check_empty_catch_blocks(source))
    issues.extend(_check_missing_async_await(source))
    issues.extend(_check_missing_access_modifiers(source))
    issues.extend(_check_wildcard_usings(source))
    issues.extend(_check_namespace_filepath_alignment(source, file_path))
    # P3-1: Block-scoped namespace detection (check exists in semantic_checks.py,
    # wired here so it flows through the C# semantic pipeline)
    from startd8.validators.semantic_checks import check_block_scoped_namespace
    issues.extend(check_block_scoped_namespace(source, file_path or ""))

    return _stamp_file_path(issues, file_path)


def _check_namespace_filepath_alignment(
    source: str,
    file_path: Optional[str],
) -> List[SemanticIssue]:
    """Flag namespace declarations that don't match the expected directory structure (REQ-KZ-CS-200i).

    Compares the parsed namespace from the source code against the expected
    namespace derived from the file path via _derive_namespace(). Catches
    both case mismatches (cartservice.services vs Cartservice.Services)
    and structural mismatches (wrong directory nesting).
    """
    if not file_path or not file_path.endswith(".cs"):
        return []

    # Extract namespace from source
    # Handles both file-scoped (namespace Foo.Bar;) and block-scoped (namespace Foo.Bar {)
    ns_match = re.search(
        r'^\s*namespace\s+([\w.]+)\s*[;{]',
        source,
        re.MULTILINE,
    )
    if not ns_match:
        return []  # No namespace declaration — caught by structural checks elsewhere

    actual_ns = ns_match.group(1)

    # Derive expected namespace from file path
    try:
        from startd8.languages.csharp import _derive_namespace
        expected_ns = _derive_namespace(file_path)
    except ImportError:
        return []

    if not expected_ns:
        return []  # Can't derive — file is at root level

    # Compare (case-sensitive — C# namespaces are case-sensitive)
    if actual_ns == expected_ns:
        return []

    # Determine severity: case-only mismatch is warning, structural is error
    if actual_ns.lower() == expected_ns.lower():
        return [SemanticIssue(
            check="namespace_case_mismatch",
            severity="warning",
            message=(
                f"Namespace case mismatch: declared `{actual_ns}` "
                f"but directory structure implies `{expected_ns}` — "
                f"C# convention requires PascalCase namespaces matching directory structure"
            ),
        )]

    return [SemanticIssue(
        check="namespace_filepath_mismatch",
        severity="warning",
        message=(
            f"Namespace `{actual_ns}` does not match expected "
            f"`{expected_ns}` derived from file path `{file_path}`"
        ),
    )]
