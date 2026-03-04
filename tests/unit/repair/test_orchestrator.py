"""Tests for startd8.repair.orchestrator."""

from pathlib import Path

from startd8.repair.config import RepairConfig
from startd8.repair.models import (
    Diagnostic,
    ElementContext,
    ImportDiagnostic,
    RepairContext,
    RepairStepResult,
    SyntaxDiagnostic,
)
from startd8.repair.orchestrator import run_element_repair, run_file_repair
from startd8.repair.steps.fence_strip import FenceStripStep
from startd8.repair.steps.indent_normalize import IndentNormalizeStep
from startd8.repair.steps.ast_validate import AstValidateStep


class TestRunElementRepair:
    def test_delegates_correctly(self):
        """Backward compat: run_element_repair works for micro-prime path."""
        ec = ElementContext(parent_class=None)
        steps = [FenceStripStep(), AstValidateStep()]
        code = "```python\nx = 1\n```"
        repaired, results = run_element_repair(code, ec, steps)
        assert "```" not in repaired
        assert len(results) == 2
        assert results[0].step_name == "fence_strip"
        assert results[0].modified is True

    def test_non_destructive_guard_reverts(self):
        """Step that breaks valid code is reverted."""

        class BreakingStep:
            name = "breaker"

            def __call__(self, code, context, file_path, element_context=None):
                # Same line count, minimal change, but invalid Python
                return RepairStepResult(
                    step_name="breaker",
                    modified=True,
                    code="x = 1\ndef (\ny = 2\na = 4\nb = 5",
                )

        ec = ElementContext()
        steps = [BreakingStep()]
        code = "x = 1\ny = 2\nz = 3\na = 4\nb = 5"  # Valid Python, 5 lines
        repaired, results = run_element_repair(code, ec, steps)
        assert repaired == code  # Reverted
        assert results[0].metrics.get("reverted") is True

    def test_delta_guardrail_skips(self):
        """Step that changes >50% of lines is skipped."""

        class MassiveChangeStep:
            name = "massive"

            def __call__(self, code, context, file_path, element_context=None):
                return RepairStepResult(
                    step_name="massive",
                    modified=True,
                    code="completely\ndifferent\ncontent\nhere",
                )

        ec = ElementContext()
        steps = [MassiveChangeStep()]
        config = RepairConfig(delta_threshold=0.5)
        code = "line1\nline2\nline3\nline4"
        repaired, results = run_element_repair(code, ec, steps, config=config)
        assert repaired == code  # Unchanged
        assert "skipped_delta" in results[0].metrics

    def test_with_parent_class(self):
        ec = ElementContext(parent_class="MyClass")
        steps = [AstValidateStep()]
        code = "def method(self):\n    return 1"
        repaired, results = run_element_repair(code, ec, steps)
        assert results[0].metrics["valid"] is True


class TestRunFileRepair:
    def test_syntax_error_repairs(self):
        files = {Path("a.py"): "```python\nx = 1\n```"}
        diags = [SyntaxDiagnostic(category="syntax", file="a.py", message="err", line=1)]
        config = RepairConfig()
        outcome = run_file_repair(files, diags, config, Path("/project"))
        assert outcome.any_modified is True
        assert Path("a.py") in outcome.repaired_files
        assert "```" not in outcome.repaired_files[Path("a.py")]

    def test_no_repairable_diagnostics(self):
        files = {Path("a.py"): "x = 1"}
        diags = [Diagnostic(category="test", file="a.py", message="test failed")]
        config = RepairConfig()
        outcome = run_file_repair(files, diags, config, Path("/project"))
        assert outcome.any_modified is False
        assert outcome.repaired_files == {}

    def test_route_included_in_outcome(self):
        files = {Path("a.py"): "```python\nx = 1\n```"}
        diags = [SyntaxDiagnostic(category="syntax", file="a.py", message="err", line=1)]
        config = RepairConfig()
        outcome = run_file_repair(files, diags, config, Path("/project"))
        assert outcome.route is not None
        assert "syntax_error" in outcome.route.matched_patterns

    def test_file_results_populated(self):
        files = {Path("a.py"): "x = 1"}
        diags = [SyntaxDiagnostic(category="syntax", file="a.py", message="err", line=1)]
        config = RepairConfig()
        outcome = run_file_repair(files, diags, config, Path("/project"))
        assert len(outcome.file_results) == 1
        assert outcome.file_results[0].file_path == Path("a.py")

    def test_multiple_files(self):
        files = {
            Path("a.py"): "```python\nx = 1\n```",
            Path("b.py"): "y = 2",
        }
        diags = [SyntaxDiagnostic(category="syntax", file="a.py", message="err", line=1)]
        config = RepairConfig()
        outcome = run_file_repair(files, diags, config, Path("/project"))
        assert len(outcome.file_results) == 2
        # a.py should be repaired
        assert outcome.any_modified is True

    def test_import_diagnostic_repair(self):
        # Use enough lines so that adding 2 import lines doesn't exceed 50% delta
        code = "\n".join([
            "x = grpc.channel()",
            "y = 1",
            "z = 2",
            "a = 3",
            "b = 4",
        ])
        files = {Path("t.py"): code}
        diags = [ImportDiagnostic(category="import", file="t.py", message="No module", module="grpc")]
        config = RepairConfig()
        outcome = run_file_repair(files, diags, config, Path("/project"))
        assert outcome.any_modified is True
        assert "import grpc" in outcome.repaired_files[Path("t.py")]
