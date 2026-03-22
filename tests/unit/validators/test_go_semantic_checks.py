"""Tests for Go semantic validation checks."""

import pytest

from startd8.validators.go_semantic_checks import (
    _check_dockerfile_go_version,
    _check_dot_imports,
    _check_duplicate_function_names,
    _check_fmt_println_in_service,
    _check_go_mod_validity,
    _check_package_filepath_alignment,
    _check_python_contamination,
    _check_unchecked_errors,
    check_go_version_consistency,
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


# ---------------------------------------------------------------------------
# _check_duplicate_function_names — receiver-aware dedup
# ---------------------------------------------------------------------------

class TestDuplicateFunctionReceiverAware:
    """Methods on different receiver types are NOT duplicates."""

    def test_same_name_different_receivers_ok(self):
        source = (
            "func (a AddToCartPayload) Validate() error { return nil }\n"
            "func (p PlaceOrderPayload) Validate() error { return nil }\n"
            "func (s SetCurrencyPayload) Validate() error { return nil }\n"
        )
        issues = _check_duplicate_function_names(source)
        assert len(issues) == 0

    def test_same_name_same_receiver_flagged(self):
        source = (
            "func (s *Server) Start() {}\n"
            "func (s *Server) Start() {}\n"
        )
        issues = _check_duplicate_function_names(source)
        assert len(issues) == 1
        assert "(Server).Start" in issues[0].message

    def test_top_level_duplicate_flagged(self):
        source = "func handler() {}\nfunc handler() {}\n"
        issues = _check_duplicate_function_names(source)
        assert len(issues) == 1

    def test_method_and_function_same_name_ok(self):
        """A method Validate() and a top-level Validate() are distinct."""
        source = (
            "func Validate() error { return nil }\n"
            "func (p Payload) Validate() error { return nil }\n"
        )
        issues = _check_duplicate_function_names(source)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# _check_package_filepath_alignment — package main exemption
# ---------------------------------------------------------------------------

class TestPackageMainExemption:
    """package main is valid in any directory."""

    def test_package_main_in_service_dir_ok(self):
        source = "package main\n\nfunc main() {}\n"
        issues = _check_package_filepath_alignment(
            source, "src/shippingservice/main.go"
        )
        assert len(issues) == 0

    def test_package_main_in_frontend_ok(self):
        source = "package main\n\nfunc main() {}\n"
        issues = _check_package_filepath_alignment(
            source, "src/frontend/main.go"
        )
        assert len(issues) == 0

    def test_library_package_mismatch_flagged(self):
        source = "package store\n\nfunc Get() {}\n"
        issues = _check_package_filepath_alignment(
            source, "src/handler/store.go"
        )
        assert len(issues) == 1
        assert "store" in issues[0].message

    def test_library_package_matches_dir_ok(self):
        source = "package store\n\nfunc Get() {}\n"
        issues = _check_package_filepath_alignment(
            source, "internal/store/redis.go"
        )
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# _check_python_contamination — false positive fixes
# ---------------------------------------------------------------------------

class TestContaminationFalsePositiveFixes:
    """print( removed from Go fingerprints — no more fmt.Fprint false positives."""

    def test_fmt_fprint_not_flagged(self):
        source = (
            'package main\n\n'
            'import "fmt"\n\n'
            'func health(w http.ResponseWriter, r *http.Request) {\n'
            '    fmt.Fprint(w, "ok")\n'
            '}\n'
        )
        issues = _check_python_contamination(source)
        assert len(issues) == 0

    def test_fmt_println_not_flagged(self):
        source = 'package main\n\nfunc main() { fmt.Println("hello") }\n'
        issues = _check_python_contamination(source)
        assert len(issues) == 0

    def test_go_builtin_print_not_flagged(self):
        """Go's builtin print() is valid Go, not Python contamination."""
        source = 'package main\n\nfunc main() { print("debug") }\n'
        issues = _check_python_contamination(source)
        assert len(issues) == 0

    def test_real_contamination_still_detected(self):
        source = (
            'package main\n\n'
            'from __future__ import annotations\n'
            'def main():\n'
            '    pass\n'
        )
        issues = _check_python_contamination(source)
        assert len(issues) >= 2  # from __future__, def
        checks = {i.message for i in issues}
        assert any("from __future__" in m for m in checks)
        assert any("def" in m for m in checks)


# ---------------------------------------------------------------------------
# _check_go_mod_validity — version range validation
# ---------------------------------------------------------------------------

class TestGoModValidation:
    def test_valid_go_mod(self):
        source = "module github.com/user/repo\n\ngo 1.23\n"
        issues = _check_go_mod_validity(source)
        assert len(issues) == 0

    def test_future_go_version_flagged(self):
        source = "module github.com/user/repo\n\ngo 1.25\n"
        issues = _check_go_mod_validity(source)
        error_issues = [i for i in issues if i.check == "invalid_go_version"]
        assert len(error_issues) == 1
        assert "1.25" in error_issues[0].message

    def test_future_toolchain_flagged(self):
        source = (
            "module github.com/user/repo\n\n"
            "go 1.25\n"
            "toolchain go1.25.6\n"
        )
        issues = _check_go_mod_validity(source)
        version_issues = [i for i in issues if i.check == "invalid_go_version"]
        assert len(version_issues) == 2  # go directive + toolchain

    def test_missing_module_directive(self):
        source = "go 1.23\n\nrequire (\n\tgithub.com/foo/bar v1.0.0\n)\n"
        issues = _check_go_mod_validity(source)
        mod_issues = [i for i in issues if i.check == "invalid_go_mod"]
        assert len(mod_issues) == 1
        assert "module" in mod_issues[0].message

    def test_missing_go_directive(self):
        source = "module github.com/user/repo\n"
        issues = _check_go_mod_validity(source)
        mod_issues = [i for i in issues if i.check == "invalid_go_mod"]
        assert len(mod_issues) == 1
        assert "go" in mod_issues[0].message

    def test_contaminated_go_mod(self):
        source = "from __future__ import annotations\nmodule foo\ngo 1.23\n"
        issues = _check_go_mod_validity(source)
        contam = [i for i in issues if i.check == "python_contamination"]
        assert len(contam) == 1

    def test_valid_range_boundary(self):
        """Go 1.18 and 1.24 are both within range."""
        for ver in ("1.18", "1.24"):
            source = f"module foo\n\ngo {ver}\n"
            issues = _check_go_mod_validity(source)
            version_issues = [i for i in issues if i.check == "invalid_go_version"]
            assert len(version_issues) == 0, f"go {ver} should be valid"


# ---------------------------------------------------------------------------
# _check_dockerfile_go_version
# ---------------------------------------------------------------------------

class TestDockerfileGoVersion:
    def test_valid_version(self):
        source = "FROM golang:1.23-alpine AS builder\n"
        issues = _check_dockerfile_go_version(source)
        assert len(issues) == 0

    def test_future_version_flagged(self):
        source = "FROM --platform=$BUILDPLATFORM golang:1.25.6-alpine AS builder\n"
        issues = _check_dockerfile_go_version(source)
        assert len(issues) == 1
        assert "1.25" in issues[0].message

    def test_non_go_from_ignored(self):
        source = "FROM gcr.io/distroless/static\n"
        issues = _check_dockerfile_go_version(source)
        assert len(issues) == 0

    def test_multistage_only_builder_checked(self):
        source = (
            "FROM golang:1.23-alpine AS builder\n"
            "RUN go build\n"
            "FROM gcr.io/distroless/static\n"
        )
        issues = _check_dockerfile_go_version(source)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# run_go_semantic_checks — file-type dispatch
# ---------------------------------------------------------------------------

class TestFileTypeDispatch:
    def test_go_mod_dispatches_to_mod_validator(self):
        source = "module foo\n\ngo 1.25\n"
        issues = run_go_semantic_checks(source, file_path="go.mod")
        checks = {i.check for i in issues}
        assert "invalid_go_version" in checks
        # Should NOT run Go source checks
        assert "unchecked_error" not in checks

    def test_dockerfile_dispatches_to_docker_validator(self):
        source = "FROM golang:1.25-alpine AS builder\nRUN go build\n"
        issues = run_go_semantic_checks(source, file_path="Dockerfile")
        checks = {i.check for i in issues}
        assert "invalid_go_version" in checks

    def test_go_file_runs_full_checks(self):
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


# ---------------------------------------------------------------------------
# check_go_version_consistency — cross-file version check
# ---------------------------------------------------------------------------

class TestGoVersionConsistency:
    def test_matching_versions_no_issue(self):
        go_mod = "module foo\n\ngo 1.23\n"
        dockerfile = "FROM golang:1.23-alpine AS builder\n"
        issues = check_go_version_consistency(go_mod, dockerfile)
        assert len(issues) == 0

    def test_mismatched_versions_flagged(self):
        go_mod = "module foo\n\ngo 1.22\n"
        dockerfile = "FROM golang:1.23-alpine AS builder\n"
        issues = check_go_version_consistency(go_mod, dockerfile)
        assert len(issues) == 1
        assert "1.22" in issues[0].message
        assert "1.23" in issues[0].message

    def test_no_go_directive_no_crash(self):
        go_mod = "module foo\n"
        dockerfile = "FROM golang:1.23-alpine AS builder\n"
        issues = check_go_version_consistency(go_mod, dockerfile)
        assert len(issues) == 0

    def test_no_golang_image_no_crash(self):
        go_mod = "module foo\n\ngo 1.23\n"
        dockerfile = "FROM gcr.io/distroless/static\n"
        issues = check_go_version_consistency(go_mod, dockerfile)
        assert len(issues) == 0
