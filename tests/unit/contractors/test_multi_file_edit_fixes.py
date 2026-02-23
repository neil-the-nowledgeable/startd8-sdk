"""Tests for multi-file edit pipeline fixes (PCA-607).

Covers 4 fixes:
  Fix 1: raw_response passthrough on DraftResult
  Fix 2: multi_file_directive in integration prompt
  Fix 3: size regression detection in _create_draft
  Fix 4: _derive_target_from_source in IntegrationEngine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Fix 1: DraftResult.raw_response
# ---------------------------------------------------------------------------


class TestDraftResultRawResponse:
    """Fix 1: raw_response field is populated on DraftResult."""

    def test_draft_result_preserves_raw_response(self):
        from startd8.workflows.builtin.lead_contractor_models import DraftResult

        draft = DraftResult(
            draft_id="d-1",
            iteration=1,
            implementation="extracted code only",
            raw_response="```python\nextracted code only\n```\nSome commentary",
        )
        assert draft.raw_response == "```python\nextracted code only\n```\nSome commentary"

    def test_draft_result_raw_response_defaults_empty(self):
        from startd8.workflows.builtin.lead_contractor_models import DraftResult

        draft = DraftResult(draft_id="d-2", iteration=1, implementation="code")
        assert draft.raw_response == ""

    def test_multi_file_split_uses_raw_response(self):
        """Generator should prefer raw_response over final_implementation
        for extract_multi_file_code when raw_response is available."""
        from startd8.contractors.generators.lead_contractor import (
            LeadContractorCodeGenerator,
        )
        from startd8.utils.code_extraction import extract_multi_file_code

        # Simulate: raw response has TWO code blocks, final_implementation has ONE
        raw = (
            "```python\n# src/pkg/__init__.py\nfrom .mod import Foo\n__all__ = ['Foo']\n```\n"
            "```python\n# src/pkg/mod.py\nclass Foo: pass\n```\n"
        )
        final_impl = "from .mod import Foo\n__all__ = ['Foo']"  # only largest block

        target_files = ["src/pkg/__init__.py", "src/pkg/mod.py"]

        # extract_multi_file_code from raw should find both
        from_raw = extract_multi_file_code(raw, target_files)
        from_final = extract_multi_file_code(final_impl, target_files)

        assert len(from_raw) == 2, f"Expected 2 files from raw, got {len(from_raw)}"
        assert len(from_final) < 2, "final_impl should NOT match both files"


# ---------------------------------------------------------------------------
# Fix 2: Integration prompt multi_file_directive
# ---------------------------------------------------------------------------


class TestIntegrationMultiFileDirective:
    """Fix 2: _integrate_final receives multi-file context."""

    def test_build_multi_file_directive_with_existing_files(self):
        from startd8.workflows.builtin.lead_contractor_workflow import (
            LeadContractorWorkflow,
        )

        directive = LeadContractorWorkflow._build_multi_file_directive(
            target_files=["src/a.py", "src/b.py"],
            existing_files={
                "src/a.py": "line1\nline2\nline3\n",
                "src/b.py": "x\ny\n",
            },
        )
        assert "Multi-File Edit Directive" in directive
        assert "`src/a.py`" in directive
        assert "`src/b.py`" in directive
        assert "PRESERVE" in directive

    def test_build_multi_file_directive_empty_for_single_file(self):
        from startd8.workflows.builtin.lead_contractor_workflow import (
            LeadContractorWorkflow,
        )

        directive = LeadContractorWorkflow._build_multi_file_directive(
            target_files=["src/a.py"],
            existing_files={"src/a.py": "content"},
        )
        assert directive == ""

    def test_build_multi_file_directive_empty_without_existing(self):
        from startd8.workflows.builtin.lead_contractor_workflow import (
            LeadContractorWorkflow,
        )

        directive = LeadContractorWorkflow._build_multi_file_directive(
            target_files=["src/a.py", "src/b.py"],
            existing_files=None,
        )
        assert directive == ""

    def test_integration_prompt_has_multi_file_directive(self):
        """The YAML template includes the {multi_file_directive} placeholder."""
        from startd8.workflows.builtin.prompts import get_template

        template = get_template("lead_contractor", "integration")
        assert "{multi_file_directive}" in template


# ---------------------------------------------------------------------------
# Fix 3: Size regression detection in _create_draft
# ---------------------------------------------------------------------------


class TestSizeRegressionDetection:
    """Fix 3: Draft size regression flags was_truncated."""

    def test_size_regression_detected_in_draft(self):
        """1000-line existing file -> 10-line draft => was_truncated=True."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            LeadContractorWorkflow,
        )
        from startd8.workflows.builtin.lead_contractor_models import (
            ImplementationSpec,
        )

        wf = LeadContractorWorkflow()

        # Mock agent that returns a tiny response
        mock_agent = MagicMock()
        mock_token_usage = MagicMock()
        mock_token_usage.input = 100
        mock_token_usage.output = 50
        mock_token_usage.was_truncated = False
        mock_agent.generate.return_value = (
            "```python\nprint('hello')\n```",  # 1 line of code
            100,  # time_ms
            mock_token_usage,
        )
        mock_agent.name = "mock"
        mock_agent.model = "mock-model"

        spec = ImplementationSpec(
            spec_id="s-1",
            task_summary="test",
            requirements=[],
            technical_approach="test",
            acceptance_criteria=[],
        )

        existing_files = {
            "src/big_file.py": "\n".join(f"line {i}" for i in range(1000))
        }

        with patch.object(wf._pricing, "calculate_total_cost", return_value=0.01):
            draft = wf._create_draft(
                drafter_agent=mock_agent,
                spec=spec,
                feedback="",
                iteration=1,
                existing_files=existing_files,
            )

        assert draft.was_truncated is True
        assert draft.truncation_source == "size_regression"

    def test_no_false_positive_for_small_files(self):
        """30-line existing file -> 5-line draft => NOT flagged (below threshold)."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            LeadContractorWorkflow,
        )
        from startd8.workflows.builtin.lead_contractor_models import (
            ImplementationSpec,
        )

        wf = LeadContractorWorkflow()

        mock_agent = MagicMock()
        mock_token_usage = MagicMock()
        mock_token_usage.input = 100
        mock_token_usage.output = 50
        mock_token_usage.was_truncated = False
        mock_agent.generate.return_value = (
            "```python\nprint('hello')\nprint('world')\nprint('test')\nprint('a')\nprint('b')\n```",
            100,
            mock_token_usage,
        )
        mock_agent.name = "mock"
        mock_agent.model = "mock-model"

        spec = ImplementationSpec(
            spec_id="s-2",
            task_summary="test",
            requirements=[],
            technical_approach="test",
            acceptance_criteria=[],
        )

        # 30 lines is below the 50-line threshold for size regression
        existing_files = {
            "src/small_file.py": "\n".join(f"line {i}" for i in range(30))
        }

        with patch.object(wf._pricing, "calculate_total_cost", return_value=0.01):
            draft = wf._create_draft(
                drafter_agent=mock_agent,
                spec=spec,
                feedback="",
                iteration=1,
                existing_files=existing_files,
            )

        # Should NOT be flagged: 30 lines is under the 50-line threshold
        assert draft.truncation_source != "size_regression"


# ---------------------------------------------------------------------------
# Fix 4: IntegrationEngine._derive_target_from_source
# ---------------------------------------------------------------------------


@dataclass
class FakeUnit:
    """Minimal IntegrationUnit for _derive_target_from_source tests."""

    _id: str = "test-unit"
    _name: str = "Test Unit"
    _generated_files: List[str] = field(default_factory=list)
    _target_files: List[str] = field(default_factory=list)
    _context: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def generated_files(self) -> List[str]:
        return self._generated_files

    @property
    def target_files(self) -> List[str]:
        return self._target_files

    @property
    def context(self) -> Dict[str, Any]:
        return self._context


class FakeMergeStrategy:
    """No-op merge strategy for engine construction."""

    def can_merge(self, source: Path, target: Path) -> bool:
        return False

    def merge(self, source: Path, target: Path):
        pass


class TestDeriveTargetFromSource:
    """Fix 4: _derive_target_from_source strips staging prefix."""

    def test_derive_target_preserves_staging_path(self, tmp_path):
        """Source in .startd8/staging/tests/unit/foo.py -> tests/unit/foo.py."""
        from startd8.contractors.integration_engine import IntegrationEngine

        project_root = tmp_path / "myproject"
        project_root.mkdir()

        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=FakeMergeStrategy(),
        )

        # Simulate a source path inside staging directory
        staging_dir = project_root / ".startd8" / "staging" / "tests" / "unit" / "contractors"
        staging_dir.mkdir(parents=True)
        source = staging_dir / "test_foo.py"
        source.write_text("# test content", encoding="utf-8")

        unit = FakeUnit()
        target = engine._derive_target_from_source(source, unit)

        # Should recover "tests/unit/contractors/test_foo.py" relative to project_root
        expected = project_root / "tests" / "unit" / "contractors" / "test_foo.py"
        assert target == expected

    def test_derive_target_fallback_no_hardcoded_src(self, tmp_path):
        """Non-staging source -> project_root / filename (NOT project_root / src / filename)."""
        from startd8.contractors.integration_engine import IntegrationEngine

        project_root = tmp_path / "myproject"
        project_root.mkdir()

        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=FakeMergeStrategy(),
        )

        # A source path that doesn't have staging markers
        source = tmp_path / "random_location" / "my_file.py"
        source.parent.mkdir(parents=True)
        source.write_text("# content", encoding="utf-8")

        unit = FakeUnit()
        target = engine._derive_target_from_source(source, unit)

        # Should fall back to project_root / my_file.py (no 'src/' prefix)
        expected = project_root / "my_file.py"
        assert target == expected

    def test_derive_target_state_directory(self, tmp_path):
        """Source in .startd8/state/src/pkg/mod.py -> src/pkg/mod.py."""
        from startd8.contractors.integration_engine import IntegrationEngine

        project_root = tmp_path / "myproject"
        project_root.mkdir()

        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=FakeMergeStrategy(),
        )

        state_dir = project_root / ".startd8" / "state" / "src" / "pkg"
        state_dir.mkdir(parents=True)
        source = state_dir / "mod.py"
        source.write_text("# module", encoding="utf-8")

        unit = FakeUnit()
        target = engine._derive_target_from_source(source, unit)

        expected = project_root / "src" / "pkg" / "mod.py"
        assert target == expected
