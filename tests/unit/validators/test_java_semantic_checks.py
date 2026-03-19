"""Tests for Java semantic validation checks."""

import pytest

from startd8.validators.java_semantic_checks import (
    _check_interface_file_contains_class,
    _check_sql_injection_risk,
    _check_system_out,
    run_java_semantic_checks,
)
from startd8.validators.semantic_checks import SemanticIssue


# ---------------------------------------------------------------------------
# _check_system_out
# ---------------------------------------------------------------------------

class TestCheckSystemOut:
    def test_system_out_println_in_service(self):
        source = 'System.out.println("processing order");'
        issues = _check_system_out(source)
        assert len(issues) == 1
        assert issues[0].check == "system_out_in_service"
        assert issues[0].severity == "warning"
        assert "SLF4J" in issues[0].message

    def test_system_err_println_in_service(self):
        source = 'System.err.println("error occurred");'
        issues = _check_system_out(source)
        assert len(issues) == 1
        assert issues[0].check == "system_out_in_service"

    def test_system_out_print_in_service(self):
        source = 'System.out.print("partial");'
        issues = _check_system_out(source)
        assert len(issues) == 1

    def test_system_out_in_main_class_no_issue(self):
        source = (
            'public class App {\n'
            '    public static void main(String[] args) {\n'
            '        System.out.println("started");\n'
            '    }\n'
            '}'
        )
        issues = _check_system_out(source)
        assert len(issues) == 0

    def test_slf4j_usage_no_issue(self):
        source = 'logger.info("Processing order {}", orderId);'
        issues = _check_system_out(source)
        assert len(issues) == 0

    def test_no_print_calls(self):
        source = 'var x = new CartService();\nreturn x.getItems();'
        issues = _check_system_out(source)
        assert len(issues) == 0

    def test_multiple_system_out_calls(self):
        source = (
            'System.out.println("a");\n'
            'System.err.println("b");\n'
            'System.out.print("c");'
        )
        issues = _check_system_out(source)
        assert len(issues) == 3

    def test_line_numbers_correct(self):
        source = 'var x = 1;\nSystem.out.println("hello");'
        issues = _check_system_out(source)
        assert len(issues) == 1
        assert issues[0].line == 2

    def test_system_out_with_spaces(self):
        source = 'System . out . println("hello");'
        issues = _check_system_out(source)
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# _check_sql_injection_risk
# ---------------------------------------------------------------------------

class TestCheckSqlInjectionRisk:
    def test_concatenation_select(self):
        source = '"SELECT * FROM users WHERE id = " + userId'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1
        assert issues[0].check == "sql_injection_risk"
        assert issues[0].severity == "error"
        assert "concatenation" in issues[0].message

    def test_concatenation_delete(self):
        source = '"DELETE FROM orders WHERE id = " + orderId'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1

    def test_string_format_select(self):
        source = 'String.format("SELECT * FROM users WHERE id = %s", userId)'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1
        assert "String.format" in issues[0].message

    def test_string_format_insert(self):
        source = 'String.format("INSERT INTO users VALUES (%s, %s)", name, email)'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1

    def test_prepared_statement_no_issue(self):
        source = (
            'PreparedStatement ps = conn.prepareStatement(\n'
            '    "SELECT * FROM users WHERE id = ?");\n'
            'ps.setInt(1, userId);'
        )
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 0

    def test_safe_string_no_issue(self):
        source = '"Hello " + name + "!"'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 0

    def test_comment_lines_skipped(self):
        source = '// "SELECT * FROM users WHERE id = " + userId'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 0

    def test_block_comment_skipped(self):
        source = '/* "SELECT * FROM users WHERE id = " + userId */'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 0

    def test_case_insensitive(self):
        source = '"select * from users where id = " + userId'
        issues = _check_sql_injection_risk(source)
        assert len(issues) == 1

    def test_line_number_correct(self):
        source = 'var x = 1;\n"SELECT * FROM t WHERE id = " + v'
        issues = _check_sql_injection_risk(source)
        assert issues[0].line == 2


# ---------------------------------------------------------------------------
# _check_interface_file_contains_class
# ---------------------------------------------------------------------------

class TestCheckInterfaceFileContainsClass:
    def test_cart_store_interface_java_with_class(self):
        source = "public class CartStoreImpl implements CartStoreInterface { }"
        issues = _check_interface_file_contains_class(source, "CartStoreInterface.java")
        assert len(issues) == 1
        assert issues[0].check == "interface_file_contains_class"
        assert issues[0].severity == "warning"
        assert "CartStoreInterface.java" in issues[0].message

    def test_icart_store_java_with_class(self):
        source = "public class CartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.java")
        assert len(issues) == 1
        assert "ICartStore.java" in issues[0].message

    def test_interface_file_with_only_interface(self):
        source = "public interface CartStoreInterface {\n    void addItem();\n}"
        issues = _check_interface_file_contains_class(source, "CartStoreInterface.java")
        assert len(issues) == 0

    def test_regular_java_file_with_class_no_issue(self):
        source = "public class CartStore { }"
        issues = _check_interface_file_contains_class(source, "CartStore.java")
        assert len(issues) == 0

    def test_no_file_path(self):
        source = "public class Foo { }"
        issues = _check_interface_file_contains_class(source, None)
        assert len(issues) == 0

    def test_interface_file_with_directory_path(self):
        source = "public class CartStore { }"
        issues = _check_interface_file_contains_class(source, "src/main/java/ICartStore.java")
        assert len(issues) == 1

    def test_comment_lines_skipped(self):
        source = "// public class CartStore { }\npublic interface ICartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.java")
        assert len(issues) == 0

    def test_abstract_class_detected(self):
        source = "public abstract class CartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.java")
        assert len(issues) == 1

    def test_final_class_detected(self):
        source = "public final class CartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.java")
        assert len(issues) == 1

    def test_non_java_file_ignored(self):
        source = "public class CartStore { }"
        issues = _check_interface_file_contains_class(source, "ICartStore.cs")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# run_java_semantic_checks — stamps file_path
# ---------------------------------------------------------------------------

class TestRunJavaSemanticChecks:
    def test_stamps_file_path(self):
        source = 'System.out.println("hello");'
        issues = run_java_semantic_checks(source, file_path="src/CartService.java")
        assert len(issues) >= 1
        for issue in issues:
            assert issue.file_path == "src/CartService.java"

    def test_no_file_path_no_stamp(self):
        source = 'System.out.println("hello");'
        issues = run_java_semantic_checks(source)
        assert len(issues) >= 1
        for issue in issues:
            assert issue.file_path is None

    def test_combined_issues(self):
        source = (
            'System.out.println("debug");\n'
            '"SELECT * FROM users WHERE id = " + id'
        )
        issues = run_java_semantic_checks(source, file_path="Service.java")
        checks = {i.check for i in issues}
        assert "system_out_in_service" in checks
        assert "sql_injection_risk" in checks

    def test_interface_check_included(self):
        source = "public class CartStore { }"
        issues = run_java_semantic_checks(source, file_path="ICartStore.java")
        checks = [i.check for i in issues]
        assert "interface_file_contains_class" in checks

    def test_clean_code_no_issues(self):
        source = 'logger.info("Processing order");\nvar items = getItems();'
        issues = run_java_semantic_checks(source, file_path="OrderService.java")
        assert len(issues) == 0

    def test_main_class_system_out_allowed(self):
        source = (
            'public class App {\n'
            '    public static void main(String[] args) {\n'
            '        System.out.println("started");\n'
            '    }\n'
            '}'
        )
        issues = run_java_semantic_checks(source, file_path="App.java")
        assert len(issues) == 0
