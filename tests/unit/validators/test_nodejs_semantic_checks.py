"""Tests for Node.js semantic validation checks (Phase N1)."""

import pytest

from startd8.validators.nodejs_semantic_checks import (
    _check_console_log_in_service,
    _check_duplicate_requires,
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
