"""Tests for Node.js semantic validation checks (Phase N1)."""

import pytest

from startd8.validators.nodejs_semantic_checks import (
    _check_console_log_in_service,
    _check_duplicate_requires,
    _check_python_contamination,
    _check_unhandled_promises,
    _check_var_usage,
    run_nodejs_semantic_checks,
)
from startd8.validators.semantic_checks import SemanticIssue


class TestCheckConsoleLogInService:
    def test_console_log_in_module(self):
        source = 'console.log("processing order");'
        issues = _check_console_log_in_service(source, "orderService.js")
        assert len(issues) == 1
        assert issues[0].check == "console_log_in_service"

    def test_console_log_in_entry_no_issue(self):
        source = 'console.log("starting server");'
        issues = _check_console_log_in_service(source, "index.js")
        assert len(issues) == 0

    def test_console_log_in_server_no_issue(self):
        source = 'console.log("starting");'
        issues = _check_console_log_in_service(source, "server.js")
        assert len(issues) == 0

    def test_console_warn_detected(self):
        source = 'console.warn("warning");'
        issues = _check_console_log_in_service(source, "utils.js")
        assert len(issues) == 1

    def test_console_error_detected(self):
        source = 'console.error("error");'
        issues = _check_console_log_in_service(source, "handler.js")
        assert len(issues) == 1

    def test_no_console_no_issue(self):
        source = 'logger.info("processing");'
        issues = _check_console_log_in_service(source, "service.js")
        assert len(issues) == 0

    def test_comment_skipped(self):
        source = '// console.log("debug");'
        issues = _check_console_log_in_service(source, "service.js")
        assert len(issues) == 0


class TestCheckVarUsage:
    def test_var_detected(self):
        source = "var x = 42;"
        issues = _check_var_usage(source)
        assert len(issues) == 1
        assert issues[0].check == "var_usage"

    def test_const_no_issue(self):
        source = "const x = 42;"
        issues = _check_var_usage(source)
        assert len(issues) == 0

    def test_let_no_issue(self):
        source = "let x = 42;"
        issues = _check_var_usage(source)
        assert len(issues) == 0

    def test_comment_skipped(self):
        source = "// var x = 42;"
        issues = _check_var_usage(source)
        assert len(issues) == 0

    def test_multiple_vars(self):
        source = "var x = 1;\nvar y = 2;"
        issues = _check_var_usage(source)
        assert len(issues) == 2


class TestCheckDuplicateRequires:
    def test_duplicate_require_detected(self):
        source = (
            "const express = require('express');\n"
            "const app = require('express');\n"
        )
        issues = _check_duplicate_requires(source)
        assert len(issues) == 1
        assert issues[0].check == "duplicate_require"
        assert "express" in issues[0].message

    def test_unique_requires_no_issue(self):
        source = (
            "const express = require('express');\n"
            "const path = require('path');\n"
        )
        issues = _check_duplicate_requires(source)
        assert len(issues) == 0

    def test_duplicate_import_detected(self):
        source = (
            "import express from 'express';\n"
            "import { Router } from 'express';\n"
        )
        issues = _check_duplicate_requires(source)
        assert len(issues) == 1

    def test_comment_skipped(self):
        source = (
            "// const express = require('express');\n"
            "const express = require('express');\n"
        )
        issues = _check_duplicate_requires(source)
        assert len(issues) == 0


class TestCheckUnhandledPromises:
    def test_unhandled_save(self):
        source = "db.save(record);"
        issues = _check_unhandled_promises(source)
        assert len(issues) == 1
        assert issues[0].check == "unhandled_promise"

    def test_awaited_save_no_issue(self):
        source = "await db.save(record);"
        issues = _check_unhandled_promises(source)
        assert len(issues) == 0

    def test_catch_no_issue(self):
        source = "db.save(record).catch(err => log(err));"
        issues = _check_unhandled_promises(source)
        assert len(issues) == 0

    def test_non_async_function_no_issue(self):
        source = "list.push(item);"
        issues = _check_unhandled_promises(source)
        assert len(issues) == 0


class TestCheckPythonContamination:
    """Tests for _check_python_contamination, including QW-1 self. false positive fix."""

    def test_detects_from_future(self):
        source = "from __future__ import annotations\nconst x = 1;\n"
        issues = _check_python_contamination(source)
        assert len(issues) == 1
        assert issues[0].check == "python_contamination"

    def test_detects_def_at_line_start(self):
        source = "def main():\n  pass\n"
        issues = _check_python_contamination(source)
        assert len(issues) == 1

    def test_detects_self_at_statement_level(self):
        source = "self.name = 'test'\nconst x = 1;\n"
        issues = _check_python_contamination(source)
        assert len(issues) == 1

    def test_self_in_string_no_false_positive(self):
        """QW-1 regression: 'yourself.' in a string must not trigger contamination."""
        source = 'console.log("help yourself.");\n'
        issues = _check_python_contamination(source)
        assert len(issues) == 0

    def test_self_in_method_call_no_false_positive(self):
        """self. inside a string argument should not trigger."""
        source = 'const msg = "Express yourself freely";\n'
        issues = _check_python_contamination(source)
        assert len(issues) == 0

    def test_import_os_at_line_start(self):
        source = "import os\nconst x = 1;\n"
        issues = _check_python_contamination(source)
        assert len(issues) == 1

    def test_python_shebang(self):
        source = "#!/usr/bin/env python3\nconst x = 1;\n"
        issues = _check_python_contamination(source)
        assert len(issues) == 1

    def test_clean_js_no_issues(self):
        source = "const express = require('express');\nconst app = express();\n"
        issues = _check_python_contamination(source)
        assert len(issues) == 0

    def test_comment_with_def_no_issue(self):
        source = "// def main() — Python version\nconst x = 1;\n"
        issues = _check_python_contamination(source)
        assert len(issues) == 0


class TestRunNodejsSemanticChecks:
    def test_stamps_file_path(self):
        source = 'console.log("debug");'
        issues = run_nodejs_semantic_checks(source, file_path="handler.js")
        assert len(issues) >= 1
        for issue in issues:
            assert issue.file_path == "handler.js"

    def test_combined_issues(self):
        source = (
            'var x = 42;\n'
            'console.log("debug");\n'
        )
        issues = run_nodejs_semantic_checks(source, file_path="service.js")
        checks = {i.check for i in issues}
        assert "var_usage" in checks
        assert "console_log_in_service" in checks

    def test_clean_code_no_issues(self):
        source = (
            "const express = require('express');\n"
            "const app = express();\n"
            "module.exports = app;\n"
        )
        issues = run_nodejs_semantic_checks(source, file_path="app.js")
        assert len(issues) == 0


# ── FR-N4: detector breadth parity (duplicate def, empty catch, sql injection) ──

from startd8.validators.nodejs_semantic_checks import (  # noqa: E402
    _check_duplicate_definitions,
    _check_empty_catch_blocks,
    _check_sql_injection_risk,
)


class TestDuplicateDefinitions:
    def test_duplicate_function_flagged(self):
        src = "function handler() {}\nfunction handler() {}\n"
        issues = _check_duplicate_definitions(src)
        assert any(i.check == "duplicate_definition" and "handler" in i.message for i in issues)

    def test_duplicate_const_flagged(self):
        src = "const grpc = require('x')\nconst grpc = require('x')\n"
        issues = _check_duplicate_definitions(src)
        assert len(issues) == 1

    def test_distinct_names_clean(self):
        src = "function a() {}\nclass B {}\nconst c = 1\n"
        assert _check_duplicate_definitions(src) == []


class TestEmptyCatch:
    def test_empty_catch_flagged(self):
        issues = _check_empty_catch_blocks("try { risky() } catch (e) {}\n")
        assert len(issues) == 1 and issues[0].check == "empty_catch_block"

    def test_nonempty_catch_clean(self):
        assert _check_empty_catch_blocks("try { x() } catch (e) { log(e) }\n") == []


class TestSqlInjection:
    def test_concat_sql_flagged(self):
        src = 'const q = "SELECT * FROM users WHERE id=" + userId\n'
        issues = _check_sql_injection_risk(src)
        assert len(issues) == 1 and issues[0].severity == "error"

    def test_template_sql_flagged(self):
        src = 'const q = `SELECT * FROM t WHERE id=${userId}`\n'
        assert len(_check_sql_injection_risk(src)) == 1

    def test_parameterized_clean(self):
        src = 'const q = "SELECT * FROM users WHERE id = ?"\ndb.query(q, [userId])\n'
        assert _check_sql_injection_risk(src) == []


class TestRunIncludesNewChecks:
    def test_run_emits_new_categories(self):
        src = (
            "function f() {}\nfunction f() {}\n"
            "try { x() } catch (e) {}\n"
            'const q = "DELETE FROM t WHERE id=" + id\n'
        )
        cats = {i.check for i in run_nodejs_semantic_checks(src, "svc.js")}
        assert {"duplicate_definition", "empty_catch_block", "sql_injection_risk"} <= cats
