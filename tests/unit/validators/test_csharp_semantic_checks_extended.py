"""Tests for the 4 new C# semantic checks added in Phase CS1."""

import pytest

from startd8.validators.csharp_semantic_checks import (
    _check_empty_catch_blocks,
    _check_missing_access_modifiers,
    _check_missing_async_await,
    _check_wildcard_usings,
    run_csharp_semantic_checks,
)


class TestCheckEmptyCatchBlocks:
    def test_empty_catch_detected(self):
        source = "try { Foo(); } catch (Exception e) {}"
        issues = _check_empty_catch_blocks(source)
        assert len(issues) >= 1
        assert issues[0].check == "empty_catch_block"

    def test_catch_with_body_no_issue(self):
        source = "try { Foo(); } catch (Exception e) { _logger.LogError(e); }"
        issues = _check_empty_catch_blocks(source)
        assert len(issues) == 0

    def test_catch_without_type_detected(self):
        source = "try { Foo(); } catch {}"
        issues = _check_empty_catch_blocks(source)
        assert len(issues) >= 1

    def test_comment_line_skipped(self):
        source = "// try { Foo(); } catch (Exception e) {}"
        issues = _check_empty_catch_blocks(source)
        assert len(issues) == 0


class TestCheckMissingAsyncAwait:
    def test_async_without_await(self):
        source = (
            "public async Task ProcessAsync() {\n"
            "    DoWork();\n"
            "}\n"
        )
        issues = _check_missing_async_await(source)
        assert len(issues) == 1
        assert issues[0].check == "missing_async_await"

    def test_async_with_await_no_issue(self):
        source = (
            "public async Task ProcessAsync() {\n"
            "    await DoWorkAsync();\n"
            "}\n"
        )
        issues = _check_missing_async_await(source)
        assert len(issues) == 0

    def test_non_async_method_no_issue(self):
        source = (
            "public void Process() {\n"
            "    DoWork();\n"
            "}\n"
        )
        issues = _check_missing_async_await(source)
        assert len(issues) == 0

    def test_comment_line_skipped(self):
        source = "// public async Task ProcessAsync() { }"
        issues = _check_missing_async_await(source)
        assert len(issues) == 0


class TestCheckMissingAccessModifiers:
    def test_class_without_modifier(self):
        source = "class MyService {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 1
        assert issues[0].check == "missing_access_modifier"

    def test_public_class_no_issue(self):
        source = "public class MyService {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 0

    def test_internal_class_no_issue(self):
        source = "internal class MyService {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 0

    def test_partial_class_without_modifier(self):
        source = "partial class MyService {"
        issues = _check_missing_access_modifiers(source)
        assert len(issues) == 1


class TestCheckWildcardUsings:
    def test_global_using_static_detected(self):
        source = "global using static System.Math;"
        issues = _check_wildcard_usings(source)
        assert len(issues) == 1
        assert issues[0].check == "global_using_static"

    def test_normal_using_no_issue(self):
        source = "using System;\nusing System.Collections.Generic;"
        issues = _check_wildcard_usings(source)
        assert len(issues) == 0

    def test_global_using_no_static_no_issue(self):
        source = "global using System;"
        issues = _check_wildcard_usings(source)
        assert len(issues) == 0


class TestNewChecksWiredIntoOrchestrator:
    def test_empty_catch_in_orchestrator(self):
        source = "try { Foo(); } catch (Exception e) {}"
        issues = run_csharp_semantic_checks(source)
        checks = {i.check for i in issues}
        assert "empty_catch_block" in checks

    def test_class_without_modifier_in_orchestrator(self):
        source = "class MyService { }"
        issues = run_csharp_semantic_checks(source)
        checks = {i.check for i in issues}
        assert "missing_access_modifier" in checks
