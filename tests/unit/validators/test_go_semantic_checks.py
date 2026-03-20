"""Tests for Go semantic validation checks."""

import pytest

from startd8.validators.go_semantic_checks import (
    _check_dot_imports,
    _check_duplicate_function_names,
    _check_fmt_println_in_service,
    _check_unchecked_errors,
    run_go_semantic_checks,
)
from startd8.validators.semantic_checks import SemanticIssue


# ---------------------------------------------------------------------------
# _check_unchecked_errors
# ---------------------------------------------------------------------------

class TestCheckUncheckedErrors:
    def test_unchecked_err_detected(self):
        source = (
            "func foo() {\n"
            "    val, err := doSomething()\n"
            "    fmt.Println(val)\n"
            "}"
        )
        issues = _check_unchecked_errors(source)
        assert len(issues) == 1
        assert issues[0].check == "unchecked_error"
        assert issues[0].severity == "warning"

    def test_checked_err_no_issue(self):
        source = (
            "func foo() {\n"
            "    val, err := doSomething()\n"
            "    if err != nil {\n"
            "        return err\n"
            "    }\n"
            "}"
        )
        issues = _check_unchecked_errors(source)
        assert len(issues) == 0

    def test_err_only_assignment(self):
        source = (
            "func foo() {\n"
            "    err := doSomething()\n"
            "    log.Println(err)\n"
            "}"
        )
        issues = _check_unchecked_errors(source)
        assert len(issues) == 1

    def test_comment_line_skipped(self):
        source = "// err := doSomething()"
        issues = _check_unchecked_errors(source)
        assert len(issues) == 0

    def test_err_reassignment(self):
        source = (
            "func foo() {\n"
            "    err = doSomething()\n"
            "    fmt.Println(\"done\")\n"
            "}"
        )
        issues = _check_unchecked_errors(source)
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# _check_duplicate_function_names
# ---------------------------------------------------------------------------

class TestCheckDuplicateFunctionNames:
    def test_duplicate_detected(self):
        source = (
            "func handler(w http.ResponseWriter, r *http.Request) {}\n"
            "func handler(w http.ResponseWriter) {}\n"
        )
        issues = _check_duplicate_function_names(source)
        assert len(issues) == 1
        assert issues[0].check == "duplicate_function"
        assert "handler" in issues[0].message

    def test_unique_functions_no_issue(self):
        source = (
            "func foo() {}\n"
            "func bar() {}\n"
        )
        issues = _check_duplicate_function_names(source)
        assert len(issues) == 0

    def test_method_receiver_not_confused(self):
        source = (
            "func (s *Server) Start() {}\n"
            "func (s *Server) Stop() {}\n"
        )
        issues = _check_duplicate_function_names(source)
        assert len(issues) == 0

    def test_comment_line_skipped(self):
        source = "// func foo() {}\nfunc foo() {}"
        issues = _check_duplicate_function_names(source)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# _check_fmt_println_in_service
# ---------------------------------------------------------------------------

class TestCheckFmtPrintlnInService:
    def test_fmt_println_in_non_main(self):
        source = (
            "package server\n\n"
            'import "fmt"\n\n'
            'func handle() { fmt.Println("debug") }'
        )
        issues = _check_fmt_println_in_service(source)
        assert len(issues) == 1
        assert issues[0].check == "fmt_println_in_service"

    def test_fmt_println_in_main_no_issue(self):
        source = (
            "package main\n\n"
            'import "fmt"\n\n'
            'func main() { fmt.Println("hello") }'
        )
        issues = _check_fmt_println_in_service(source)
        assert len(issues) == 0

    def test_fmt_printf_detected(self):
        source = (
            "package handler\n\n"
            'func process() { fmt.Printf("val=%d", 42) }'
        )
        issues = _check_fmt_println_in_service(source)
        assert len(issues) == 1

    def test_log_usage_no_issue(self):
        source = (
            "package server\n\n"
            'func process() { log.Info("processing") }'
        )
        issues = _check_fmt_println_in_service(source)
        assert len(issues) == 0

    def test_comment_line_skipped(self):
        source = (
            "package server\n"
            '// fmt.Println("debug")\n'
        )
        issues = _check_fmt_println_in_service(source)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# _check_dot_imports
# ---------------------------------------------------------------------------

class TestCheckDotImports:
    def test_dot_import_in_block(self):
        source = (
            "package main\n\n"
            "import (\n"
            '    . "fmt"\n'
            ")\n"
        )
        issues = _check_dot_imports(source)
        assert len(issues) == 1
        assert issues[0].check == "dot_import"

    def test_single_dot_import(self):
        source = (
            "package main\n\n"
            'import . "fmt"\n'
        )
        issues = _check_dot_imports(source)
        assert len(issues) == 1

    def test_normal_import_no_issue(self):
        source = (
            "package main\n\n"
            "import (\n"
            '    "fmt"\n'
            '    "os"\n'
            ")\n"
        )
        issues = _check_dot_imports(source)
        assert len(issues) == 0

    def test_alias_import_no_issue(self):
        source = (
            "package main\n\n"
            "import (\n"
            '    log "github.com/sirupsen/logrus"\n'
            ")\n"
        )
        issues = _check_dot_imports(source)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# run_go_semantic_checks — stamps file_path
# ---------------------------------------------------------------------------

class TestRunGoSemanticChecks:
    def test_stamps_file_path(self):
        source = (
            "package server\n"
            'func foo() { fmt.Println("debug") }'
        )
        issues = run_go_semantic_checks(source, file_path="server.go")
        assert len(issues) >= 1
        for issue in issues:
            assert issue.file_path == "server.go"

    def test_combined_issues(self):
        source = (
            "package handler\n\n"
            "func process() {\n"
            '    err := doWork()\n'
            '    fmt.Println("done")\n'
            "}\n"
        )
        issues = run_go_semantic_checks(source, file_path="handler.go")
        checks = {i.check for i in issues}
        assert "unchecked_error" in checks
        assert "fmt_println_in_service" in checks

    def test_clean_code_no_issues(self):
        source = (
            "package main\n\n"
            "func main() {\n"
            "    val, err := doWork()\n"
            "    if err != nil {\n"
            "        log.Fatal(err)\n"
            "    }\n"
            "    log.Println(val)\n"
            "}\n"
        )
        issues = run_go_semantic_checks(source, file_path="main.go")
        assert len(issues) == 0
