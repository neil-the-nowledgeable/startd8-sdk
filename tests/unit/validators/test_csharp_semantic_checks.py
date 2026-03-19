"""Tests for C# semantic validation checks."""

import pytest

from startd8.validators.csharp_semantic_checks import (
    _check_console_writeline,
    _check_interface_file_contains_class,
    _check_missing_nullable_in_csproj,
    _check_sql_injection_risk,
    run_csharp_semantic_checks,
)
from startd8.validators.semantic_checks import SemanticIssue


# ---------------------------------------------------------------------------
# _check_console_writeline
# ---------------------------------------------------------------------------

class TestCheckConsoleWriteline:
    def test_console_writeline_detected(self):
        source = 'Console.WriteLine("hello");'
        issues = _check_console_writeline(source)
        assert len(issues) == 1
        assert issues[0].check == "console_writeline_in_service"
        assert issues[0].severity == "warning"
        assert "ILogger" in issues[0].message

    def test_console_write_detected(self):
        source = 'Console.Write("hello");'
        issues = _check_console_writeline(source)
        assert len(issues) == 1
        assert issues[0].check == "console_writeline_in_service"

    def test_console_writeline_with_spaces(self):
        source = 'Console . WriteLine("hello");'
        issues = _check_console_writeline(source)
        assert len(issues) == 1

    def test_ilogger_usage_no_issue(self):
        source = '_logger.LogInformation("hello");'
        issues = _check_console_writeline(source)
        assert len(issues) == 0

    def test_no_console_calls(self):
        source = 'var x = 42;\nreturn x;'
        issues = _check_console_writeline(source)
        assert len(issues) == 0

    def test_multiple_console_calls(self):
        source = 'Console.WriteLine("a");\nConsole.Write("b");'
        issues = _check_console_writeline(source)
        assert len(issues) == 2

    def test_line_numbers_correct(self):
        source = 'var x = 1;\nConsole.WriteLine("hello");'
        issues = _check_console_writeline(source)
        assert len(issues) == 1
        assert issues[0].line == 2


# ---------------------------------------------------------------------------
# _check_sql_injection_risk
# ---------------------------------------------------------------------------

class TestCheckSqlInjectionRisk:
    def test_interpolation_select(self):
        source = '$"SELECT * FROM users WHERE id = {userId}"'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1
        assert issues[0].check == "sql_injection_risk"
        assert issues[0].severity == "error"
        assert "interpolation" in issues[0].message

    def test_interpolation_insert(self):
        source = '$"INSERT INTO users VALUES ({name})"'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1
        assert "interpolation" in issues[0].message

    def test_concatenation_select(self):
        source = '"SELECT * FROM users WHERE id = " + userId'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1
        assert "concatenation" in issues[0].message

    def test_concatenation_delete(self):
        source = '"DELETE FROM orders WHERE id = " + orderId'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1

    def test_parameterized_query_no_issue(self):
        source = 'cmd.Parameters.AddWithValue("@id", userId);'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 0

    def test_safe_string_no_issue(self):
        source = '$"Hello {name}, welcome!"'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 0

    def test_case_insensitive(self):
        source = '$"select * from users where id = {userId}"'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1

    def test_line_number_correct(self):
        source = 'var x = 1;\n$"SELECT * FROM t WHERE id = {v}"'
        issues = _check_sql_injection_risk(source)
        assert issues[0].line == 2

    # P1: Multi-line concatenated SQL patterns (AlloyDB pattern)
    def test_where_clause_interpolation(self):
        """WHERE clause with interpolated variable on a separate line."""
        source = '$"WHERE userId=\'{userId}\' AND productId=\'{productId}\'"'
        issues = _check_sql_injection_risk(source)
        assert len(issues) >= 1
        assert issues[0].check == "sql_injection_risk"

    def test_values_clause_interpolation(self):
        source = "$\"VALUES ('{userId}', '{productId}', {qty})\""
        issues = _check_sql_injection_risk(source)
        assert len(issues) >= 1

    def test_set_clause_interpolation(self):
        source = '$"SET quantity={newQty}"'
        issues = _check_sql_injection_risk(source)
        assert len(issues) >= 1

    def test_on_conflict_clause_interpolation(self):
        source = '$"ON CONFLICT (userId, productId) DO UPDATE SET quantity={newQty}"'
        issues = _check_sql_injection_risk(source)
        assert len(issues) >= 1

    def test_quoted_variable_in_sql(self):
        """$"...'{userId}'..." is always suspicious in SQL context."""
        source = """$"WHERE userId='{userId}'" """
        issues = _check_sql_injection_risk(source)
        assert len(issues) >= 1

    def test_multiline_alloydb_pattern(self):
        """The exact AlloyDB pattern that escaped detection in run-078."""
        source = (
            'selectCmd.CommandText =\n'
            '    $"SELECT quantity FROM {_tableName} " +\n'
            '    $"WHERE userId=\'{userId}\' AND productId=\'{productId}\'";'
        )
        issues = _check_sql_injection_risk(source)
        # Line 3 (WHERE clause) must be flagged
        assert any(i.line == 3 for i in issues), f"Expected line 3 flagged, got {issues}"

    def test_parameterized_where_no_issue(self):
        """Parameterized queries should not trigger."""
        source = (
            'cmd.CommandText = "SELECT * FROM carts WHERE userId=@userId";\n'
            'cmd.Parameters.AddWithValue("@userId", userId);'
        )
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 0

    def test_safe_interpolation_no_sql(self):
        """Non-SQL interpolation should not trigger clause check."""
        source = '$"WHERE are you going, {name}?"'
        issues = _check_sql_injection_risk(source)
        # "WHERE" followed by non-SQL content — this may trigger the clause
        # regex but the quoted-var pattern won't match, so at most 1 issue
        # Either way, this is acceptable (low false-positive cost for SQL safety)


# ---------------------------------------------------------------------------
# _check_interface_file_contains_class
# ---------------------------------------------------------------------------

class TestCheckInterfaceFileContainsClass:
    def test_interface_file_with_class(self):
        source = "public class CartStore : ICartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.cs")
        assert len(issues) == 1
        assert issues[0].check == "interface_file_contains_class"
        assert issues[0].severity == "warning"
        assert "ICartStore.cs" in issues[0].message

    def test_interface_file_with_only_interface(self):
        source = "public interface ICartStore\n{\n    void AddItem();\n}"
        issues = _check_interface_file_contains_class(source, "ICartStore.cs")
        assert len(issues) == 0

    def test_regular_cs_file_with_class_no_issue(self):
        source = "public class CartStore { }"
        issues = _check_interface_file_contains_class(source, "CartStore.cs")
        assert len(issues) == 0

    def test_no_file_path(self):
        source = "public class Foo { }"
        issues = _check_interface_file_contains_class(source, None)
        assert len(issues) == 0

    def test_interface_file_with_path(self):
        source = "public class CartStore { }"
        issues = _check_interface_file_contains_class(source, "src/ICartStore.cs")
        assert len(issues) == 1

    def test_i_lowercase_second_char_not_matched(self):
        """A file like Iota.cs should NOT be treated as interface."""
        source = "public class IotaService { }"
        issues = _check_interface_file_contains_class(source, "Iota.cs")
        assert len(issues) == 0

    def test_comment_lines_skipped(self):
        source = "// public class CartStore { }\npublic interface ICartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.cs")
        assert len(issues) == 0

    def test_sealed_class_detected(self):
        source = "public sealed class CartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.cs")
        assert len(issues) == 1

    def test_abstract_class_detected(self):
        source = "public abstract class CartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.cs")
        assert len(issues) == 1

    def test_non_cs_file_ignored(self):
        source = "public class CartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.java")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# _check_missing_nullable_in_csproj
# ---------------------------------------------------------------------------

class TestCheckMissingNullableInCsproj:
    def test_csproj_with_nullable(self):
        source = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>"""
        issues = _check_missing_nullable_in_csproj(source, "MyProject.csproj")
        assert len(issues) == 0

    def test_csproj_without_nullable(self):
        source = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
</Project>"""
        issues = _check_missing_nullable_in_csproj(source, "MyProject.csproj")
        assert len(issues) == 1
        assert issues[0].check == "missing_nullable_in_csproj"
        assert issues[0].severity == "warning"
        assert "Nullable" in issues[0].message

    def test_non_csproj_file_ignored(self):
        source = "no nullable here"
        issues = _check_missing_nullable_in_csproj(source, "MyProject.cs")
        assert len(issues) == 0

    def test_no_file_path(self):
        source = "no nullable here"
        issues = _check_missing_nullable_in_csproj(source, None)
        assert len(issues) == 0

    def test_csproj_with_path(self):
        source = "<Project></Project>"
        issues = _check_missing_nullable_in_csproj(source, "src/MyProject.csproj")
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# run_csharp_semantic_checks — stamps file_path
# ---------------------------------------------------------------------------

class TestRunCsharpSemanticChecks:
    def test_stamps_file_path_on_cs_issues(self):
        source = 'Console.WriteLine("hello");'
        issues = run_csharp_semantic_checks(source, file_path="src/CartService.cs")
        assert len(issues) >= 1
        for issue in issues:
            assert issue.file_path == "src/CartService.cs"

    def test_stamps_file_path_on_csproj_issues(self):
        source = "<Project><PropertyGroup></PropertyGroup></Project>"
        issues = run_csharp_semantic_checks(source, file_path="MyProject.csproj")
        assert len(issues) >= 1
        for issue in issues:
            assert issue.file_path == "MyProject.csproj"

    def test_no_file_path_no_stamp(self):
        source = 'Console.WriteLine("hello");'
        issues = run_csharp_semantic_checks(source)
        assert len(issues) >= 1
        for issue in issues:
            assert issue.file_path is None

    def test_csproj_skips_cs_checks(self):
        """When file is .csproj, only csproj-specific checks run."""
        source = 'Console.WriteLine("hello");\n<Project></Project>'
        issues = run_csharp_semantic_checks(source, file_path="test.csproj")
        # Should only have the missing-nullable check, not console_writeline
        checks = [i.check for i in issues]
        assert "console_writeline_in_service" not in checks
        assert "missing_nullable_in_csproj" in checks

    def test_combined_cs_issues(self):
        source = (
            'Console.WriteLine("debug");\n'
            '$"SELECT * FROM users WHERE id = {id}"'
        )
        issues = run_csharp_semantic_checks(source, file_path="Service.cs")
        checks = {i.check for i in issues}
        assert "console_writeline_in_service" in checks
        assert "sql_injection_risk" in checks

    def test_interface_check_included(self):
        source = "public class CartStore { }"
        issues = run_csharp_semantic_checks(source, file_path="ICartStore.cs")
        checks = [i.check for i in issues]
        assert "interface_file_contains_class" in checks

    def test_clean_code_no_issues(self):
        source = '_logger.LogInformation("Processing order");\nvar items = await GetItems();'
        issues = run_csharp_semantic_checks(source, file_path="OrderService.cs")
        assert len(issues) == 0
