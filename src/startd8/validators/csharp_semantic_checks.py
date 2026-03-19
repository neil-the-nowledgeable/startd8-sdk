"""C# semantic validation — regex-based checks for generated C# code.

No external tool dependency (no .NET SDK required).  Four checks:
1. Console.WriteLine() in service classes (should use ILogger<T>)
2. SQL injection risk via string interpolation
3. Interface file (IFoo.cs) containing class declarations
4. Missing <Nullable>enable</Nullable> in .csproj

Known limitation: comment skip only catches ``//`` and ``/*`` at line start.
Multi-line ``/* ... */`` blocks and mid-line comments may cause false positives.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .semantic_checks import SemanticIssue, _basename, _stamp_file_path

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
    """
    issues: List[SemanticIssue] = []

    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        # String interpolation with SQL DML keyword: $"SELECT...{..."
        if _SQL_INTERPOLATION_RE.search(stripped):
            issues.append(SemanticIssue(
                check="sql_injection_risk",
                severity="error",
                message=(
                    "SQL injection risk: string interpolation in SQL query — "
                    "use parameterized queries instead"
                ),
                line=i,
            ))
        # String concatenation with SQL: "SELECT..." + var
        elif _SQL_CONCAT_RE.search(stripped):
            issues.append(SemanticIssue(
                check="sql_injection_risk",
                severity="error",
                message=(
                    "SQL injection risk: string concatenation in SQL query — "
                    "use parameterized queries instead"
                ),
                line=i,
            ))
        # Multi-line SQL: WHERE/SET/VALUES clause with interpolated variable
        elif _SQL_CLAUSE_INTERPOLATION_RE.search(stripped):
            issues.append(SemanticIssue(
                check="sql_injection_risk",
                severity="error",
                message=(
                    "SQL injection risk: interpolated variable in SQL clause — "
                    "use parameterized queries (e.g. cmd.Parameters.AddWithValue)"
                ),
                line=i,
            ))
        # Quoted variable in SQL: $"...'{userId}'..." — always suspicious
        elif _SQL_QUOTED_VAR_RE.search(stripped):
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
        if stripped.startswith("//") or stripped.startswith("/*"):
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
                    f"IFoo.cs should contain ONLY the interface definition"
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

    # .csproj check
    if file_path and file_path.endswith(".csproj"):
        issues.extend(_check_missing_nullable_in_csproj(source, file_path))
        return _stamp_file_path(issues, file_path)

    # .cs source checks
    issues.extend(_check_console_writeline(source))
    issues.extend(_check_sql_injection_risk(source))
    issues.extend(_check_interface_file_contains_class(source, file_path))

    return _stamp_file_path(issues, file_path)
