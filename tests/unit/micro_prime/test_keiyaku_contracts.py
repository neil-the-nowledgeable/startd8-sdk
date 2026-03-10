"""Tests for Keiyaku boundary contracts (K-6, K-9).

Validates RepairStepOutcome, EscalationRepairOutcome, EscalationHandoff
models and the to_escalation_repair_outcome factory function.
"""

from __future__ import annotations

import json

import pytest

from startd8.micro_prime.models import (
    EscalationHandoff,
    EscalationRepairOutcome,
    EscalationReason,
    RepairStepOutcome,
)
from startd8.micro_prime.repair import (
    RepairResult,
    RepairStepResult,
    to_escalation_repair_outcome,
)


# ═══════════════════════════════════════════════════════════════════════════
# RepairStepOutcome
# ═══════════════════════════════════════════════════════════════════════════


class TestRepairStepOutcome:
    """Unit tests for RepairStepOutcome frozen dataclass."""

    def test_basic_construction(self) -> None:
        step = RepairStepOutcome(
            step="fence_strip",
            modified=True,
            ast_valid_after=True,
            detail="Removed ```python fence",
        )
        assert step.step == "fence_strip"
        assert step.modified is True
        assert step.ast_valid_after is True
        assert step.detail == "Removed ```python fence"

    def test_frozen(self) -> None:
        step = RepairStepOutcome(
            step="indent_normalize", modified=False,
            ast_valid_after=True, detail="no change",
        )
        with pytest.raises(AttributeError):
            step.step = "other"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# EscalationRepairOutcome
# ═══════════════════════════════════════════════════════════════════════════


class TestEscalationRepairOutcome:
    """Unit tests for EscalationRepairOutcome (K-9)."""

    @pytest.fixture()
    def sample_outcome(self) -> EscalationRepairOutcome:
        return EscalationRepairOutcome(
            element_fqn="MyClass.my_method",
            ast_valid_before=False,
            ast_valid_after=True,
            steps=[
                RepairStepOutcome(
                    step="fence_strip", modified=True,
                    ast_valid_after=False, detail="Removed fence",
                ),
                RepairStepOutcome(
                    step="indent_normalize", modified=True,
                    ast_valid_after=True, detail="Re-indented to 4-space",
                ),
                RepairStepOutcome(
                    step="ast_validate", modified=False,
                    ast_valid_after=True, detail="no change",
                ),
            ],
            final_verdict="recovered",
            lines_before=10,
            lines_after=8,
        )

    def test_to_dict_structure(self, sample_outcome: EscalationRepairOutcome) -> None:
        d = sample_outcome.to_dict()
        assert "repair_outcome" in d
        ro = d["repair_outcome"]
        assert ro["element_fqn"] == "MyClass.my_method"
        assert ro["ast_valid_before"] is False
        assert ro["ast_valid_after"] is True
        assert ro["final_verdict"] == "recovered"
        assert ro["lines_before"] == 10
        assert ro["lines_after"] == 8
        assert len(ro["steps"]) == 3

    def test_to_dict_step_fields(self, sample_outcome: EscalationRepairOutcome) -> None:
        steps = sample_outcome.to_dict()["repair_outcome"]["steps"]
        first = steps[0]
        assert first["step"] == "fence_strip"
        assert first["modified"] is True
        assert first["ast_valid_after"] is False
        assert first["detail"] == "Removed fence"

    def test_to_dict_is_json_serializable(self, sample_outcome: EscalationRepairOutcome) -> None:
        d = sample_outcome.to_dict()
        serialized = json.dumps(d)
        roundtrip = json.loads(serialized)
        assert roundtrip == d

    def test_frozen(self, sample_outcome: EscalationRepairOutcome) -> None:
        with pytest.raises(AttributeError):
            sample_outcome.element_fqn = "other"  # type: ignore[misc]

    def test_empty_steps(self) -> None:
        outcome = EscalationRepairOutcome(
            element_fqn="func",
            ast_valid_before=True,
            ast_valid_after=True,
            steps=[],
            final_verdict="unchanged",
            lines_before=5,
            lines_after=5,
        )
        d = outcome.to_dict()
        assert d["repair_outcome"]["steps"] == []


# ═══════════════════════════════════════════════════════════════════════════
# EscalationHandoff
# ═══════════════════════════════════════════════════════════════════════════


class TestEscalationHandoff:
    """Unit tests for EscalationHandoff (K-6)."""

    @pytest.fixture()
    def repair_outcome(self) -> EscalationRepairOutcome:
        return EscalationRepairOutcome(
            element_fqn="MyClass.my_method",
            ast_valid_before=False,
            ast_valid_after=False,
            steps=[
                RepairStepOutcome(
                    step="fence_strip", modified=True,
                    ast_valid_after=False, detail="Removed fence",
                ),
            ],
            final_verdict="failed",
            lines_before=10,
            lines_after=9,
        )

    @pytest.fixture()
    def sample_handoff(self, repair_outcome: EscalationRepairOutcome) -> EscalationHandoff:
        return EscalationHandoff(
            element_fqn="MyClass.my_method",
            original_tier="SIMPLE",
            local_model="ollama:startd8-coder",
            attempt_count=2,
            failure_category=EscalationReason.AST_FAILURE.value,
            failure_message="ast.parse() failed",
            raw_output_lines=10,
            repair=repair_outcome,
            element_signature="(self, x: int) -> str",
            element_kind="METHOD",
            parent_class="MyClass",
        )

    def test_to_dict_structure(self, sample_handoff: EscalationHandoff) -> None:
        d = sample_handoff.to_dict()
        assert "escalation" in d
        esc = d["escalation"]
        assert esc["element_fqn"] == "MyClass.my_method"
        assert esc["original_tier"] == "SIMPLE"
        assert esc["local_model"] == "ollama:startd8-coder"
        assert esc["attempt_count"] == 2
        assert esc["failure"]["category"] == "ast_failure"
        assert esc["failure"]["message"] == "ast.parse() failed"
        assert esc["failure"]["raw_output_lines"] == 10
        assert esc["element_spec"]["signature"] == "(self, x: int) -> str"
        assert esc["element_spec"]["kind"] == "METHOD"
        assert esc["element_spec"]["parent_class"] == "MyClass"

    def test_to_dict_with_repair_steps(self, sample_handoff: EscalationHandoff) -> None:
        d = sample_handoff.to_dict()
        assert "repair_applied" in d["escalation"]
        steps = d["escalation"]["repair_applied"]
        assert len(steps) == 1
        assert steps[0]["step"] == "fence_strip"
        assert steps[0]["modified"] is True

    def test_to_dict_without_repair(self) -> None:
        handoff = EscalationHandoff(
            element_fqn="func",
            original_tier="SIMPLE",
            local_model="ollama:startd8-coder",
            attempt_count=1,
            failure_category=EscalationReason.EMPTY_RESPONSE.value,
            failure_message="Empty response",
            raw_output_lines=0,
            repair=None,
            element_signature="(x: int) -> str",
            element_kind="FUNCTION",
            parent_class=None,
        )
        d = handoff.to_dict()
        assert "repair_applied" not in d["escalation"]

    def test_to_dict_is_json_serializable(self, sample_handoff: EscalationHandoff) -> None:
        d = sample_handoff.to_dict()
        serialized = json.dumps(d)
        roundtrip = json.loads(serialized)
        assert roundtrip == d

    def test_to_prompt_section_contains_json(self, sample_handoff: EscalationHandoff) -> None:
        section = sample_handoff.to_prompt_section()
        assert "## Prior Local Model Attempt (Structured)" in section
        assert "```json" in section
        # Verify the JSON block is valid
        json_start = section.index("```json") + len("```json\n")
        json_end = section.index("```", json_start)
        json_block = section[json_start:json_end].strip()
        parsed = json.loads(json_block)
        assert "escalation" in parsed

    def test_to_prompt_section_contains_summary(self, sample_handoff: EscalationHandoff) -> None:
        section = sample_handoff.to_prompt_section()
        assert "**Summary:**" in section
        assert "ast_failure" in section
        assert "2 attempt(s)" in section
        assert "ollama:startd8-coder" in section

    def test_to_prompt_section_lists_repair_steps(self, sample_handoff: EscalationHandoff) -> None:
        section = sample_handoff.to_prompt_section()
        assert "**Repair steps applied:**" in section
        assert "fence_strip" in section

    def test_to_prompt_section_no_repair_steps_line_when_none_modified(self) -> None:
        repair = EscalationRepairOutcome(
            element_fqn="func",
            ast_valid_before=True,
            ast_valid_after=True,
            steps=[
                RepairStepOutcome(
                    step="ast_validate", modified=False,
                    ast_valid_after=True, detail="no change",
                ),
            ],
            final_verdict="unchanged",
            lines_before=5,
            lines_after=5,
        )
        handoff = EscalationHandoff(
            element_fqn="func",
            original_tier="SIMPLE",
            local_model="ollama:startd8-coder",
            attempt_count=1,
            failure_category=EscalationReason.STRUCTURAL_MISMATCH.value,
            failure_message="Missing return",
            raw_output_lines=5,
            repair=repair,
            element_signature="() -> str",
            element_kind="FUNCTION",
            parent_class=None,
        )
        section = handoff.to_prompt_section()
        assert "**Repair steps applied:**" not in section

    def test_frozen(self, sample_handoff: EscalationHandoff) -> None:
        with pytest.raises(AttributeError):
            sample_handoff.element_fqn = "other"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# to_escalation_repair_outcome factory
# ═══════════════════════════════════════════════════════════════════════════


class TestToEscalationRepairOutcome:
    """Tests for the RepairResult → EscalationRepairOutcome factory."""

    def _make_repair_result(
        self,
        *,
        ast_valid_before: bool = False,
        ast_valid_after: bool = True,
        repair_recovered: bool = True,
        steps_applied: list[str] | None = None,
        step_results: list[RepairStepResult] | None = None,
        code: str = "    return 42\n",
        last_error: str | None = None,
    ) -> RepairResult:
        if step_results is None:
            step_results = [
                RepairStepResult(
                    step_name="fence_strip",
                    modified=True,
                    code="return 42",
                    metrics={"fences_found": 1},
                ),
                RepairStepResult(
                    step_name="ast_validate",
                    modified=False,
                    code="return 42",
                    metrics={"valid": ast_valid_after},
                ),
            ]
        if steps_applied is None:
            steps_applied = ["fence_strip"]
        return RepairResult(
            code=code,
            steps_applied=steps_applied,
            ast_valid=ast_valid_after,
            ast_valid_before=ast_valid_before,
            ast_valid_after=ast_valid_after,
            repair_recovered=repair_recovered,
            metrics={},
            step_results=step_results,
            last_error=last_error,
        )

    def test_basic_conversion(self) -> None:
        raw = "```python\nreturn 42\n```"
        result = self._make_repair_result()
        outcome = to_escalation_repair_outcome("MyClass.method", raw, result)

        assert outcome.element_fqn == "MyClass.method"
        assert outcome.ast_valid_before is False
        assert outcome.ast_valid_after is True
        assert outcome.final_verdict == "recovered"
        assert outcome.lines_before == 3
        assert outcome.lines_after == 1
        assert len(outcome.steps) == 2

    def test_verdict_recovered(self) -> None:
        result = self._make_repair_result(
            ast_valid_before=False, ast_valid_after=True, repair_recovered=True,
        )
        outcome = to_escalation_repair_outcome("func", "bad code", result)
        assert outcome.final_verdict == "recovered"

    def test_verdict_failed(self) -> None:
        result = self._make_repair_result(
            ast_valid_before=False, ast_valid_after=False, repair_recovered=False,
        )
        outcome = to_escalation_repair_outcome("func", "bad code", result)
        assert outcome.final_verdict == "failed"

    def test_verdict_unchanged(self) -> None:
        result = self._make_repair_result(
            ast_valid_before=True,
            ast_valid_after=True,
            repair_recovered=False,
            steps_applied=[],
            step_results=[
                RepairStepResult(
                    step_name="ast_validate", modified=False,
                    code="return 42", metrics={"valid": True},
                ),
            ],
        )
        outcome = to_escalation_repair_outcome("func", "return 42", result)
        assert outcome.final_verdict == "unchanged"

    def test_step_details_include_metrics(self) -> None:
        result = self._make_repair_result(
            step_results=[
                RepairStepResult(
                    step_name="over_generation_trim",
                    modified=True,
                    code="def f(): ...",
                    metrics={"nodes_removed": 3},
                ),
                RepairStepResult(
                    step_name="import_completion",
                    modified=True,
                    code="import os\ndef f(): ...",
                    metrics={"imports_added": 2},
                ),
            ],
        )
        outcome = to_escalation_repair_outcome("func", "code", result)
        assert any("3 node(s)" in s.detail for s in outcome.steps)
        assert any("2 import(s)" in s.detail for s in outcome.steps)

    def test_roundtrip_json(self) -> None:
        """Full round-trip: RepairResult → EscalationRepairOutcome → dict → JSON → parse."""
        raw = "```python\nreturn 42\n```"
        result = self._make_repair_result()
        outcome = to_escalation_repair_outcome("func", raw, result)
        d = outcome.to_dict()
        serialized = json.dumps(d)
        parsed = json.loads(serialized)
        assert parsed["repair_outcome"]["element_fqn"] == "func"
        assert parsed["repair_outcome"]["final_verdict"] == "recovered"
        assert len(parsed["repair_outcome"]["steps"]) == 2

    def test_empty_raw_code(self) -> None:
        result = self._make_repair_result(code="")
        outcome = to_escalation_repair_outcome("func", "", result)
        assert outcome.lines_before == 0
        assert outcome.lines_after == 0

    def test_reverted_step_detail(self) -> None:
        result = self._make_repair_result(
            step_results=[
                RepairStepResult(
                    step_name="indent_normalize",
                    modified=True,
                    code="return 42",
                    metrics={"reverted": True},
                ),
            ],
        )
        outcome = to_escalation_repair_outcome("func", "code", result)
        assert any("reverted" in s.detail for s in outcome.steps)
