"""Tests for Go disk validators in forward_manifest_validator.py."""

from startd8.forward_manifest_validator import (
    _validate_go_file,
    DiskComplianceResult,
)


VALID_GO = """\
package main

import "fmt"

func main() {
    fmt.Println("hello")
}
"""

NO_PACKAGE_GO = """\
import "fmt"

func main() {
    fmt.Println("hello")
}
"""

UNBALANCED_GO = """\
package main

func main() {
    fmt.Println("hello")
"""


class TestValidateGoFile:

    def _make_result(self):
        return DiskComplianceResult(file_path="main.go")

    def test_valid_go(self):
        result = _validate_go_file(VALID_GO, self._make_result())
        assert result.error is None or result.error == ""
        assert result.contract_compliance >= 0.7

    def test_missing_package_hard_error(self):
        """Missing package declaration is a hard error (ast_valid=False)."""
        result = _validate_go_file(NO_PACKAGE_GO, self._make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert "package" in (result.error or "").lower()

    def test_unbalanced_braces(self):
        result = _validate_go_file(UNBALANCED_GO, self._make_result())
        assert result.ast_valid is False
        assert "brace" in (result.error or "").lower()

    def test_empty_file_rejected(self):
        result = _validate_go_file("", self._make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0

    def test_semantic_issues_populated(self):
        """Go semantic checks (e.g., fmt.Println in service) populate semantic_issues."""
        source = (
            "package server\n\n"
            'import "fmt"\n\n'
            'func handle() { fmt.Println("debug") }\n'
        )
        result = _validate_go_file(source, self._make_result())
        cats = [i.get("category") for i in result.semantic_issues]
        assert "fmt_println_in_service" in cats

    def test_stub_counting(self):
        """Go stubs (panic) are counted."""
        source = (
            "package server\n\n"
            "func Handle() {\n"
            '    panic("not implemented")\n'
            "}\n"
        )
        result = _validate_go_file(source, self._make_result())
        assert result.stubs_remaining >= 1
