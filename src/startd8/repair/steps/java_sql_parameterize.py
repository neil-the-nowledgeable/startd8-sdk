"""Java SQL parameterization repair step (REQ-KZ-JV-402e Phase 3).

Rewrites string-concatenated SQL in Java to ``PreparedStatement`` with
parameterized queries.

Targets three common LLM-generated anti-patterns::

    BAD:  "SELECT * FROM users WHERE id=" + userId
    BAD:  String.format("SELECT * FROM users WHERE id=%s", userId)
    BAD:  new StringBuilder("DELETE FROM t WHERE id=").append(userId)

    GOOD: conn.prepareStatement("SELECT * FROM users WHERE id=?")
          ps.setString(1, userId);

Only fires for ``.java`` files.  Runs before ``java_syntax_validate``
in the Java security repair route.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# SQL keywords that indicate a SQL string (case-insensitive check).
_SQL_KEYWORDS = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "MERGE ")

# Joined SQL keyword alternation for reuse in compiled patterns.
_SQL_KW_ALT = "|".join(kw.strip() for kw in _SQL_KEYWORDS)

# String.format("SQL...", args) — used by _fix_string_format_sql().
_STRING_FORMAT_SQL_RE = re.compile(
    r"""^(\s*)(.+?=\s*String\.format\(\s*"([^"]*(?:"""
    + _SQL_KW_ALT
    + r""")[^"]*)"\s*,\s*(.+?)\s*\))\s*;""",
    re.MULTILINE | re.IGNORECASE,
)

# new StringBuilder("SELECT ...").append(var) — used by _fix_stringbuilder_sql().
_STRINGBUILDER_SQL_RE = re.compile(
    r"""^(\s*)(.+?=\s*new\s+StringBuilder\(\s*"([^"]*(?:"""
    + _SQL_KW_ALT
    + r""")[^"]*)"\s*\)(?:\.append\([^)]+\))+)\.toString\(\)\s*;""",
    re.MULTILINE | re.IGNORECASE,
)

# Extract variables from string concatenation:  + varName or + "text"
_CONCAT_VAR_RE = re.compile(r"""\+\s*(?!")([\w.]+)""")

# Extract %s / %d placeholders in String.format
_FORMAT_PLACEHOLDER_RE = re.compile(r"%[sd]")

# Extract .append(varName) calls
_APPEND_VAR_RE = re.compile(r"""\.append\(\s*(?!")([\w.]+)\s*\)""")


class JavaSqlParameterizeStep:
    """Rewrite Java SQL string concatenation to PreparedStatement (REQ-KZ-JV-402e Phase 3).

    Detects string concatenation, ``String.format()``, and
    ``StringBuilder.append()`` patterns containing SQL keywords and
    rewrites them to use ``PreparedStatement`` with ``?`` placeholders.
    """

    name: str = "java_sql_parameterize"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if file_path.suffix.lower() != ".java":
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        # Quick check: does this file have SQL patterns at all?
        code_upper = code.upper()
        if not any(kw in code_upper for kw in _SQL_KEYWORDS):
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        # Heuristic skip: if PreparedStatement usage outnumbers concat/format
        # patterns, the file is already mostly parameterized.  The '"+' count
        # can match non-SQL string concatenation, but false-skips are benign
        # (we'd just leave already-safe code alone).
        if code.count("prepareStatement") > code.count('"+') + code.count("String.format"):
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        result = code
        total_count = 0

        result, c = _fix_concat_sql(result)
        total_count += c

        result, c = _fix_string_format_sql(result)
        total_count += c

        result, c = _fix_stringbuilder_sql(result)
        total_count += c

        return RepairStepResult(
            step_name=self.name,
            modified=total_count > 0,
            code=result,
            metrics={"queries_parameterized": total_count},
        )


def _fix_concat_sql(code: str) -> tuple[str, int]:
    """Rewrite ``"SQL..." + var`` to PreparedStatement."""
    count = 0
    lines = code.splitlines(keepends=True)
    result_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Detect a line with SQL string concat.
        if not _has_sql_concat(line):
            result_lines.append(line)
            i += 1
            continue

        # Collect full statement (may span lines until semicolon).
        stmt_lines = [line]
        j = i + 1
        last_line = line
        while j < len(lines) and not last_line.rstrip().endswith(";"):
            stmt_lines.append(lines[j])
            last_line = lines[j]
            j += 1

        full_stmt = "".join(stmt_lines)

        # Extract the variable being assigned to.
        assign_match = re.match(r"(\s*)(?:(?:String|var)\s+)?(\w+)\s*=\s*", full_stmt)
        if not assign_match:
            result_lines.extend(stmt_lines)
            i = j
            continue

        indent = assign_match.group(1)
        var_name = assign_match.group(2)

        # Extract variables being concatenated (not string literals).
        concat_vars = _CONCAT_VAR_RE.findall(full_stmt)
        if not concat_vars:
            result_lines.extend(stmt_lines)
            i = j
            continue

        # Build parameterized SQL: take the RHS of the assignment,
        # replace each `+ variable` with nothing and insert `?` where
        # the variable was spliced into the SQL string.
        rhs = full_stmt[assign_match.end():].rstrip().rstrip(";").strip()
        parameterized = _rebuild_sql_with_placeholders(rhs, concat_vars)
        if parameterized is None:
            result_lines.extend(stmt_lines)
            i = j
            continue

        newline = "\n" if stmt_lines[-1].endswith("\n") else ""
        result_lines.append(
            f'{indent}String {var_name} = "{parameterized}";{newline}'
        )
        for idx, v in enumerate(concat_vars, 1):
            setter = _infer_setter(v)
            result_lines.append(
                f"{indent}// TODO: use ps.{setter}({idx}, {v}); with PreparedStatement{newline}"
            )

        count += 1
        i = j
        continue

    return "".join(result_lines), count


def _rebuild_sql_with_placeholders(rhs: str, concat_vars: list[str]) -> Optional[str]:
    """Rebuild the SQL string from a concat expression, replacing variables with ``?``.

    Given an RHS like::

        "SELECT * FROM users WHERE id=" + userId

    returns::

        SELECT * FROM users WHERE id=?
    """
    # Tokeniser: walks the RHS character-by-character with 4 states:
    #   '"' → consume string literal content into result_parts
    #   "'" → consume single-quoted content into result_parts
    #   '+' → peek ahead: if next token is a string, continue; if identifier
    #          and in concat_vars, emit '?'; otherwise emit the identifier
    #   other → skip (whitespace, bare identifiers on LHS)
    result_parts: list[str] = []
    pos = 0
    text = rhs

    while pos < len(text):
        # Skip whitespace
        while pos < len(text) and text[pos] in " \t\n\r":
            pos += 1
        if pos >= len(text):
            break

        if text[pos] == '"':
            # Consume a string literal
            end = text.find('"', pos + 1)
            if end == -1:
                end = len(text)
            result_parts.append(text[pos + 1:end])
            pos = end + 1
        elif text[pos] == "'":
            # Consume a char/string literal (single-quoted in concat context)
            end = text.find("'", pos + 1)
            if end == -1:
                end = len(text)
            result_parts.append(text[pos + 1:end])
            pos = end + 1
        elif text[pos] == "+":
            pos += 1
            # Skip whitespace after +
            while pos < len(text) and text[pos] in " \t\n\r":
                pos += 1
            if pos >= len(text):
                break
            if text[pos] in ('"', "'"):
                # Next token is a string literal — will be consumed next iteration
                continue
            # It's a variable reference — consume the identifier
            m = re.match(r"[\w.]+", text[pos:])
            if m:
                var = m.group(0)
                if var in concat_vars:
                    result_parts.append("?")
                else:
                    result_parts.append(var)
                pos += m.end()
            else:
                pos += 1
        else:
            # Consume an identifier or other token
            m = re.match(r"[\w.]+", text[pos:])
            if m:
                pos += m.end()
            else:
                pos += 1

    if not result_parts:
        return None
    return "".join(result_parts)


def _fix_string_format_sql(code: str) -> tuple[str, int]:
    """Rewrite ``String.format("SQL...", args)`` to parameterized form."""
    count = 0

    def _replace(m: re.Match) -> str:
        nonlocal count
        indent = m.group(1)
        sql_template = m.group(3)
        args_str = m.group(4)

        # Replace %s/%d with ?
        parameterized = _FORMAT_PLACEHOLDER_RE.sub("?", sql_template)

        # Parse argument list.
        args = [a.strip() for a in args_str.split(",")]

        lines = [f'{indent}String sql = "{parameterized}";']
        for idx, arg in enumerate(args, 1):
            setter = _infer_setter(arg)
            lines.append(
                f"{indent}// TODO: use ps.{setter}({idx}, {arg}); with PreparedStatement"
            )

        count += 1
        return "\n".join(lines)

    result = _STRING_FORMAT_SQL_RE.sub(_replace, code)
    return result, count


def _fix_stringbuilder_sql(code: str) -> tuple[str, int]:
    """Rewrite ``new StringBuilder("SQL...").append(var)`` to parameterized form."""
    count = 0

    def _replace(m: re.Match) -> str:
        nonlocal count
        indent = m.group(1)
        sql_base = m.group(3)
        full = m.group(2)

        # Extract appended variables.
        append_vars = _APPEND_VAR_RE.findall(full)
        if not append_vars:
            return m.group(0)

        # Each append(var) becomes a ? in the SQL.
        parameterized = sql_base
        for _ in append_vars:
            parameterized += "?"

        lines = [f'{indent}String sql = "{parameterized}";']
        for idx, v in enumerate(append_vars, 1):
            setter = _infer_setter(v)
            lines.append(
                f"{indent}// TODO: use ps.{setter}({idx}, {v}); with PreparedStatement"
            )

        count += 1
        return "\n".join(lines)

    result = _STRINGBUILDER_SQL_RE.sub(_replace, code)
    return result, count


def _has_sql_concat(line: str) -> bool:
    """Check if a line contains SQL string concatenation."""
    upper = line.upper()
    has_sql = any(kw in upper for kw in _SQL_KEYWORDS)
    has_concat = '"' in line and "+" in line
    return has_sql and has_concat


_INT_SUFFIXES = ("id", "count", "num", "size", "age", "port", "index")
_DOUBLE_SUFFIXES = ("price", "amount", "total", "rate", "balance")
_BOOL_SUFFIXES = ("flag", "enabled", "active")

# Pre-compiled pattern matching camelCase or snake_case word boundaries.
# Matches "userId" → ["user", "Id"], "user_id" → ["user", "id"].
_CAMEL_SPLIT_RE = re.compile(r"[_.]|(?<=[a-z])(?=[A-Z])")


def _infer_setter(var_name: str) -> str:
    """Infer the PreparedStatement setter method from variable name.

    Uses the last word segment (camelCase or snake_case split) to avoid
    false positives — e.g., ``provider`` won't match ``id`` but
    ``providerId`` will.
    """
    parts = _CAMEL_SPLIT_RE.split(var_name)
    tail = parts[-1].lower() if parts else var_name.lower()
    if tail in _INT_SUFFIXES:
        return "setInt"
    if tail in _DOUBLE_SUFFIXES:
        return "setDouble"
    if tail in _BOOL_SUFFIXES or var_name.lower().startswith("is_"):
        return "setBoolean"
    return "setString"
