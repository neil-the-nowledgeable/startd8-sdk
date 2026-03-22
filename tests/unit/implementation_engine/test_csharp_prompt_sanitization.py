"""Tests for C# prompt improvement sanitization (REQ-PI-CS-100–400).

Covers:
- _sanitize_csharp_code_examples() — Console.WriteLine → ILogger transforms
- _detect_sql_interpolation_in_examples() — SQL injection risk detection
- _build_security_guidance_section() — detected_databases fallback
"""

from __future__ import annotations

import pytest

from startd8.implementation_engine.spec_builder import (
    _sanitize_csharp_code_examples,
    _detect_sql_interpolation_in_examples,
    _build_security_guidance_section,
)


# ---------------------------------------------------------------------------
# _sanitize_csharp_code_examples (REQ-PI-CS-100)
# ---------------------------------------------------------------------------

class TestSanitizeCSharpCodeExamples:

    def test_console_writeline_transformed(self):
        text = 'Console.WriteLine("Hello")'
        result = _sanitize_csharp_code_examples(text)
        assert '_logger.LogInformation("Hello")' in result
        assert "Console.WriteLine" not in result

    def test_console_error_writeline_transformed(self):
        text = 'Console.Error.WriteLine("Error")'
        result = _sanitize_csharp_code_examples(text)
        assert '_logger.LogError("Error")' in result
        assert "Console.Error.WriteLine" not in result

    def test_text_without_console_unchanged(self):
        text = '_logger.LogInformation("Already correct")\nvar x = 42;'
        result = _sanitize_csharp_code_examples(text)
        assert result == text

    def test_multiple_console_writelines_all_transformed(self):
        text = (
            'Console.WriteLine("First");\n'
            'Console.WriteLine("Second");\n'
            'Console.WriteLine("Third");'
        )
        result = _sanitize_csharp_code_examples(text)
        assert result.count("_logger.LogInformation") == 3
        assert "Console.WriteLine" not in result

    def test_console_error_matched_before_console_writeline(self):
        """Console.Error.WriteLine must be matched BEFORE Console.WriteLine.

        If order were reversed, the regex for Console.WriteLine would match
        Console.Error.WriteLine and produce _logger.LogInformation instead of
        _logger.LogError.
        """
        text = 'Console.Error.WriteLine("Failure")'
        result = _sanitize_csharp_code_examples(text)
        assert "_logger.LogError" in result
        assert "_logger.LogInformation" not in result

    def test_mixed_console_and_error(self):
        text = (
            'Console.Error.WriteLine("err");\n'
            'Console.WriteLine("info");'
        )
        result = _sanitize_csharp_code_examples(text)
        assert '_logger.LogError("err")' in result
        assert '_logger.LogInformation("info")' in result

    def test_console_writeline_with_spaces(self):
        text = 'Console.WriteLine  ("spaced")'
        result = _sanitize_csharp_code_examples(text)
        assert "_logger.LogInformation" in result
        assert "Console.WriteLine" not in result


# ---------------------------------------------------------------------------
# _detect_sql_interpolation_in_examples (REQ-PI-CS-200)
# ---------------------------------------------------------------------------

class TestDetectSqlInterpolation:

    def test_sql_with_interpolation_returns_warning(self):
        text = 'var q = $"SELECT * FROM users WHERE id = {userId}";'
        result = _detect_sql_interpolation_in_examples(text)
        assert "WARNING" in result
        assert "SQL Injection" in result
        assert "SELECT" in result

    def test_sql_without_interpolation_returns_empty(self):
        text = 'var q = "SELECT * FROM users WHERE id = @id";'
        result = _detect_sql_interpolation_in_examples(text)
        assert result == ""

    def test_interpolation_without_sql_returns_empty(self):
        text = 'var msg = $"Hello {name}";'
        result = _detect_sql_interpolation_in_examples(text)
        assert result == ""

    def test_multiple_flagged_lines(self):
        text = (
            'var q1 = $"SELECT * FROM users WHERE id = {id}";\n'
            'var q2 = $"INSERT INTO logs VALUES ({msg})";\n'
            'var q3 = $"DELETE FROM sessions WHERE token = {tok}";'
        )
        result = _detect_sql_interpolation_in_examples(text)
        assert "SELECT" in result
        assert "INSERT" in result
        assert "DELETE" in result

    def test_empty_text_returns_empty(self):
        result = _detect_sql_interpolation_in_examples("")
        assert result == ""

    def test_max_five_flagged_lines(self):
        lines = [
            f'var q{i} = $"SELECT col{i} FROM t WHERE id = {{id}}";'
            for i in range(8)
        ]
        text = "\n".join(lines)
        result = _detect_sql_interpolation_in_examples(text)
        # Should contain at most 5 flagged lines
        assert result.count("  - `") <= 5

    def test_case_insensitive_sql_keywords(self):
        text = 'var q = $"select * from users where id = {id}";'
        result = _detect_sql_interpolation_in_examples(text)
        assert "WARNING" in result


# ---------------------------------------------------------------------------
# _build_security_guidance_section — detected_databases fallback (REQ-PI-CS-201)
# ---------------------------------------------------------------------------

class TestBuildSecurityGuidanceDetectedDatabases:

    def test_postgresql_detected_returns_npgsql_example(self):
        context = {"detected_databases": ["postgresql"]}
        result = _build_security_guidance_section(context)
        assert "Npgsql" in result
        assert "AddWithValue" in result
        assert "detected databases" in result

    def test_spanner_detected_returns_spanner_example(self):
        context = {"detected_databases": ["spanner"]}
        result = _build_security_guidance_section(context)
        assert "SpannerParameterCollection" in result or "SpannerParameter" in result
        assert "Cloud Spanner" in result

    def test_sqlserver_detected_returns_sqlcommand_example(self):
        context = {"detected_databases": ["sqlserver"]}
        result = _build_security_guidance_section(context)
        assert "SQL Server" in result
        assert "AddWithValue" in result

    def test_empty_detected_databases_falls_through(self):
        """Empty detected_databases list should NOT match the fallback."""
        context = {"detected_databases": []}
        result = _build_security_guidance_section(context)
        # With no databases and no task description keywords, should return empty
        # or hit the keyword fallback
        assert "detected databases" not in result

    def test_security_contract_takes_precedence_over_detected_databases(self):
        """When security_contract has client_libraries, detected_databases is ignored."""
        context = {
            "security_contract": {
                "client_libraries": ["Npgsql"],
            },
            "detected_databases": ["spanner"],
        }
        result = _build_security_guidance_section(context)
        # Should use security_contract path (no "detected databases" label)
        assert "detected databases" not in result
        assert "Npgsql" in result

    def test_alloydb_detected_returns_npgsql_example(self):
        context = {"detected_databases": ["alloydb"]}
        result = _build_security_guidance_section(context)
        assert "AlloyDB" in result
        assert "AddWithValue" in result
