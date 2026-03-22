"""SQL parameterization repair step for C# (REQ-KZ-CS-400).

Rewrites string-interpolated SQL queries in Npgsql code to use
parameterized queries with ``cmd.Parameters.AddWithValue()``.

Targets the most common LLM-generated anti-pattern::

    BAD:  $"SELECT ... WHERE userId='{userId}'"
    GOOD: "SELECT ... WHERE userId=@userId"
          cmd.Parameters.AddWithValue("@userId", userId);

Only fires for .cs files. Runs after ``csharp_convention_fix`` and
before ``csharp_syntax_validate`` in the C# repair route.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# Match string-interpolated SQL with quoted variables:
#   $"... WHERE col='{variable}' ..."
#   $"... VALUES ('{var1}', '{var2}', {var3}) ..."
_INTERPOLATED_QUOTED_VAR = re.compile(
    r"""'\{(\w+)\}'""",  # '{varName}'
)
_INTERPOLATED_BARE_VAR = re.compile(
    r"""\{(\w+)\}""",  # {varName} without quotes (for numeric cols)
)

# Match the full interpolated string assignment:
#   cmd.CommandText = $"SELECT ..."
#   selectCmd.CommandText = $"INSERT ..."
_CMD_TEXT_ASSIGNMENT = re.compile(
    r"""^(\s*\w+\.CommandText\s*=\s*)(\$".*";)""",
    re.MULTILINE,
)

# Match multi-line concatenated assignments:
#   cmd.CommandText =
#       $"SELECT ..." +
#       $"WHERE ...";
_CMD_TEXT_MULTILINE = re.compile(
    r"""^(\s*\w+\.CommandText\s*=\s*\n(?:\s*\$?"[^"]*"\s*\+?\s*\n?)+\s*\$?"[^"]*";)""",
    re.MULTILINE,
)


class SqlParameterizeStep:
    """Rewrite interpolated SQL to parameterized queries in C# (Npgsql)."""

    name: str = "sql_parameterize"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if file_path.suffix.lower() != ".cs":
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Only process files that have interpolated SQL patterns
        if '$"' not in code or not any(
            kw in code.upper()
            for kw in ("SELECT ", "INSERT ", "DELETE ", "UPDATE ")
        ):
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        result, count = _parameterize_sql(code)
        return RepairStepResult(
            step_name=self.name,
            modified=count > 0,
            code=result,
            metrics={"queries_parameterized": count},
        )


def _parameterize_sql(code: str) -> tuple[str, int]:
    """Rewrite interpolated SQL statements to parameterized form.

    Returns (modified_code, count_of_rewrites).
    """
    lines = code.splitlines(keepends=True)
    result_lines: list[str] = []
    count = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # Detect SQL assignment via CommandText or CreateCommand($"...")
        _is_sql_site = (
            ".CommandText" in line
            or ("CreateCommand(" in line and ("$\"" in line or line.strip().endswith("(")))
        )
        if _is_sql_site:
            # Collect the full statement (may span multiple lines via + or =\n)
            stmt_lines = [line]
            j = i + 1
            # Keep collecting until we hit a line ending with ;
            last_stripped = line.strip()
            while j < len(lines) and not last_stripped.endswith(";"):
                stmt_lines.append(lines[j])
                last_stripped = lines[j].strip()
                j += 1

            full_stmt = "".join(stmt_lines)

            # Only process if there's string interpolation with SQL
            if '$"' in full_stmt:
                # Extract interpolated variables
                vars_found = _INTERPOLATED_QUOTED_VAR.findall(full_stmt)
                bare_vars = _INTERPOLATED_BARE_VAR.findall(full_stmt)

                # Deduplicate while preserving order.
                # Skip: underscore-prefixed (_tableName), table-name-like vars
                # (tableName, table_name, TableName) — these are identifiers,
                # not user input, and can't be parameterized in SQL.
                _TABLE_NAME_PATTERNS = {"tablename", "table_name", "schemaname", "schema_name"}
                seen: set[str] = set()
                all_vars: list[str] = []
                for v in vars_found + bare_vars:
                    if (
                        v not in seen
                        and not v.startswith("_")
                        and v.lower() not in _TABLE_NAME_PATTERNS
                    ):
                        seen.add(v)
                        all_vars.append(v)

                if all_vars:
                    # Rewrite: replace '{var}' with @var and {var} with @var
                    new_stmt = full_stmt
                    for var in all_vars:
                        new_stmt = new_stmt.replace(f"'{{{var}}}'", f"@{var}")
                        new_stmt = new_stmt.replace(f"{{{var}}}", f"@{var}")

                    # Remove $" only if no remaining interpolations
                    # (table names like {tableName} may still need interpolation)
                    if "{" not in new_stmt.split("=", 1)[-1]:
                        new_stmt = new_stmt.replace('$"', '"')

                    result_lines.append(new_stmt)

                    # Determine the cmd variable name
                    cmd_var_match = (
                        re.match(r'\s*(\w+)\.CommandText', full_stmt)
                        or re.search(r'var\s+(\w+)\s*=\s*\w+\.CreateCommand', full_stmt)
                        or re.search(r'using\s+var\s+(\w+)\s*=', full_stmt)
                        or re.search(r'using\s*\(\s*var\s+(\w+)\s*=', full_stmt)
                    )
                    cmd_var = cmd_var_match.group(1) if cmd_var_match else "cmd"

                    # Insert Parameters.AddWithValue lines after the statement
                    indent = re.match(r"(\s*)", line).group(1)
                    for var in all_vars:
                        param_line = (
                            f'{indent}{cmd_var}.Parameters.AddWithValue("@{var}", {var});\n'
                        )
                        result_lines.append(param_line)

                    count += 1
                    i = j
                    continue

            # No interpolation — emit original lines
            result_lines.extend(stmt_lines)
            i = j
            continue

        result_lines.append(line)
        i += 1

    return "".join(result_lines), count
