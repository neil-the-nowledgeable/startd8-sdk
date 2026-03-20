"""Tests for the 5 new Java semantic checks added in Phase J1."""

import pytest

from startd8.validators.java_semantic_checks import (
    _check_empty_catch_blocks,
    _check_missing_access_modifiers,
    _check_missing_override,
    _check_raw_type_usage,
    _check_wildcard_imports,
    run_java_semantic_checks,
)


# ---------------------------------------------------------------------------
# _check_empty_catch_blocks
# ---------------------------------------------------------------------------

class TestCheckEmptyCatchBlocks:
    def test_empty_catch_detected(self):
        source = "try { foo(); } catch (Exception e) {}"
        issues = _check_empty_catch_blocks(source)
        assert len(issues) >= 1
        assert issues[0].check == "empty_catch_block"
        assert issues[0].severity == "warning"

    def test_catch_with_body_no_issue(self):
        source = "try { foo(); } catch (Exception e) { logger.error(e); }"
        issues = _check_empty_catch_blocks(source)
        assert len(issues) == 0

    def test_comment_line_skipped(self):
        source = "// try { foo(); } catch (Exception e) {}"
        issues = _check_empty_catch_blocks(source)
        assert len(issues) == 0

    def test_block_comment_skipped(self):
        source = "/* catch (Exception e) {} */"
        issues = _check_empty_catch_blocks(source)
        assert len(issues) == 0

    def test_multiple_empty_catches(self):
        source = (
            "try { a(); } catch (IOException e) {}\n"
            "try { b(); } catch (Exception e) {}"
        )
        issues = _check_empty_catch_blocks(source)
        assert len(issues) >= 2


# ---------------------------------------------------------------------------
# _check_raw_type_usage
# ---------------------------------------------------------------------------

class TestCheckRawTypeUsage:
    def test_raw_list_detected(self):
        source = "List items = new ArrayList();"
        issues = _check_raw_type_usage(source)
        assert len(issues) == 1
        assert issues[0].check == "raw_type_usage"
        assert "List" in issues[0].message

    def test_parameterized_list_no_issue(self):
        source = "List<String> items = new ArrayList<>();"
        issues = _check_raw_type_usage(source)
        assert len(issues) == 0

    def test_raw_map_detected(self):
        source = "Map data = new HashMap();"
        issues = _check_raw_type_usage(source)
        assert len(issues) == 1
        assert "Map" in issues[0].message

    def test_raw_set_detected(self):
        source = "Set ids;"
        issues = _check_raw_type_usage(source)
        assert len(issues) == 1

    def test_non_collection_type_no_issue(self):
        source = "String name = \"hello\";"
        issues = _check_raw_type_usage(source)
        assert len(issues) == 0

    def test_comment_line_skipped(self):
        source = "// List items = new ArrayList();"
        issues = _check_raw_type_usage(source)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# _check_missing_override
# ---------------------------------------------------------------------------

class TestCheckMissingOverride:
    def test_tostring_without_override(self):
        source = "    public String toString() { return name; }"
        issues = _check_missing_override(source)
        assert len(issues) == 1
        assert issues[0].check == "missing_override"
        assert "toString" in issues[0].message

    def test_tostring_with_override_no_issue(self):
        source = "    @Override\n    public String toString() { return name; }"
        issues = _check_missing_override(source)
        assert len(issues) == 0

    def test_equals_without_override(self):
        source = "    public boolean equals(Object o) { return true; }"
        issues = _check_missing_override(source)
        assert len(issues) == 1
        assert "equals" in issues[0].message

    def test_hashcode_without_override(self):
        source = "    public int hashCode() { return 42; }"
        issues = _check_missing_override(source)
        assert len(issues) == 1
        assert "hashCode" in issues[0].message

    def test_custom_method_no_issue(self):
        source = "    public void processOrder() { }"
        issues = _check_missing_override(source)
        assert len(issues) == 0

    def test_comment_line_skipped(self):
        source = "    // public String toString() { return name; }"
        issues = _check_missing_override(source)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# _check_missing_access_modifiers
# ---------------------------------------------------------------------------

class TestCheckMissingAccessModifiers:
    def test_class_without_modifier(self):
        source = "class MyService {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 1
        assert issues[0].check == "missing_access_modifier"
        assert "Class" in issues[0].message

    def test_public_class_no_issue(self):
        source = "public class MyService {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 0

    def test_method_without_modifier(self):
        source = "    void processOrder() {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 1
        assert "Method" in issues[0].message

    def test_public_method_no_issue(self):
        source = "    public void processOrder() {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 0

    def test_abstract_class_without_modifier(self):
        source = "abstract class BaseService {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 1

    def test_comment_line_skipped(self):
        source = "// class MyService {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# _check_wildcard_imports
# ---------------------------------------------------------------------------

class TestCheckWildcardImports:
    def test_wildcard_import_detected(self):
        source = "import java.util.*;"
        issues = _check_wildcard_imports(source)
        assert len(issues) == 1
        assert issues[0].check == "wildcard_import"
        assert issues[0].severity == "warning"

    def test_explicit_import_no_issue(self):
        source = "import java.util.List;"
        issues = _check_wildcard_imports(source)
        assert len(issues) == 0

    def test_static_wildcard_not_matched(self):
        # Static wildcards are a different pattern (import static ...)
        source = "import static org.junit.Assert.*;"
        issues = _check_wildcard_imports(source)
        # This should still be caught as it matches the pattern
        assert len(issues) == 1

    def test_comment_line_skipped(self):
        source = "// import java.util.*;"
        issues = _check_wildcard_imports(source)
        assert len(issues) == 0

    def test_multiple_wildcards(self):
        source = "import java.util.*;\nimport java.io.*;"
        issues = _check_wildcard_imports(source)
        assert len(issues) == 2


# ---------------------------------------------------------------------------
# Integration: run_java_semantic_checks includes new checks
# ---------------------------------------------------------------------------

class TestNewChecksWiredIntoOrchestrator:
    def test_empty_catch_in_orchestrator(self):
        source = "try { foo(); } catch (Exception e) {}"
        issues = run_java_semantic_checks(source)
        checks = {i.check for i in issues}
        assert "empty_catch_block" in checks

    def test_wildcard_import_in_orchestrator(self):
        source = "import java.util.*;"
        issues = run_java_semantic_checks(source)
        checks = {i.check for i in issues}
        assert "wildcard_import" in checks

    def test_raw_type_in_orchestrator(self):
        source = "List items = new ArrayList();"
        issues = run_java_semantic_checks(source)
        checks = {i.check for i in issues}
        assert "raw_type_usage" in checks
