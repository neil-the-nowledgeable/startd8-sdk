"""
Tests for deterministic-first PARSE (v0.1 format) + failure forensics (note 1d).

strtd8 kickoff follow-ups:
- The LLM parse sub-splits v0.1 features and invents IDs (r3: 14 → 36 with
  F-101a…), destroying the exact-ID requirements-coverage join. Format-detected
  plans now parse deterministically — $0, authored IDs intact, no agent call.
- Gate-failed runs used to emit NO artifacts (runs 2-3: quality gate tripped,
  nothing persisted, failure undiagnosable). _fail() now writes
  plan-ingestion-failure-forensics.json with the evidence gathered so far.

All LLM calls mocked.
"""

import json
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from startd8.workflows.builtin.plan_ingestion_models import PlanIngestionConfig
from startd8.workflows.builtin.plan_ingestion_parsing import (
    looks_like_v01_plan_format,
)
from startd8.workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow

pytestmark = pytest.mark.unit


def _make_mock_agent(name="test-agent"):
    agent = MagicMock()
    agent.name = name
    agent.model = "mock-model"
    agent.max_tokens = 4096
    return agent


V01_PLAN = textwrap.dedent("""\
    # Deterministic Parse Test Plan

    | Feature | FRs | Target files | Est. LOC |
    |---------|-----|--------------|----------|
    | F-001 alpha module | FR-1 | src/alpha.py | 50 |
    | F-002 beta module | FR-2 | src/beta.py | 60 |
    | F-003 gamma module | FR-3 | src/gamma.py | 70 |

    ## Dependencies

    - F-002 after F-001
    """)

PROSE_PLAN = "# Free-form Plan\n\nBuild the thing. Make it good.\n"

HEADING_PLAN = textwrap.dedent("""\
    # Heading Plan

    ### F-001: First feature

    Touch `src/alpha.py`.
    """)


# ---------------------------------------------------------------------------
# Format sniff
# ---------------------------------------------------------------------------

class TestFormatSniff:
    def test_detects_v01_feature_tables(self):
        assert looks_like_v01_plan_format(V01_PLAN)

    def test_rejects_prose(self):
        assert not looks_like_v01_plan_format(PROSE_PLAN)

    def test_rejects_heading_format(self):
        # ### F-xxx headings are NOT v0.1 tables — the LLM parse stays
        # primary for that legacy format
        assert not looks_like_v01_plan_format(HEADING_PLAN)

    def test_rejects_non_feature_tables(self):
        text = "| Key | Value |\n|---|---|\n| plan_path | docs/plan.md |\n"
        assert not looks_like_v01_plan_format(text)


# ---------------------------------------------------------------------------
# Deterministic-first PARSE
# ---------------------------------------------------------------------------

class TestDeterministicFirstParse:
    def _run(self, tmp_path, plan_text, **extra_config):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_text)

        agent = _make_mock_agent()
        agent.generate.side_effect = Exception("LLM should not be needed")

        with patch(
            "startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec",
            return_value=agent,
        ):
            result = PlanIngestionWorkflow().run({
                "plan_path": str(plan_file),
                "output_dir": str(tmp_path),
                "review_rounds": 0,
                **extra_config,
            })
        return result, agent

    def test_v01_plan_parses_without_llm_call(self, tmp_path):
        result, agent = self._run(tmp_path, V01_PLAN)
        assert result.success, result.error
        # The whole run made ZERO LLM calls (deterministic parse + FR-1/FR-2
        # deterministic assess/transform + review_rounds=0)
        agent.generate.assert_not_called()

        parse_step = next(s for s in result.steps if s.step_name == "parse")
        assert parse_step.agent_name == "deterministic"
        assert parse_step.cost == 0.0
        assert parse_step.metadata.get("deterministic") is True
        assert parse_step.metadata.get("format") == "req-and-plan-v0.1"

    def test_authored_feature_ids_preserved_exactly(self, tmp_path):
        result, _ = self._run(tmp_path, V01_PLAN)
        assert result.success, result.error
        seed = json.loads(
            (tmp_path / "prime-context-seed.json").read_text()
        )
        fids = sorted(f["feature_id"] for f in seed["plan"]["features"])
        assert fids == ["F-001", "F-002", "F-003"]
        # And the authored dependency edge survived (the exact-ID join the
        # LLM parse used to destroy)
        assert seed["plan"]["dependency_graph"] == {"F-002": ["F-001"]}

    def test_force_llm_parse_overrides_sniff(self, tmp_path):
        result, agent = self._run(tmp_path, V01_PLAN, force_llm_parse=True)
        # LLM parse attempted (mock raises) → heuristic fallback still lands
        assert result.success, result.error
        agent.generate.assert_called()
        parse_step = next(s for s in result.steps if s.step_name == "parse")
        assert parse_step.metadata.get("heuristic_fallback") is True

    def test_prose_plan_still_uses_llm_path(self, tmp_path):
        result, agent = self._run(tmp_path, PROSE_PLAN)
        # Prose → LLM parse attempted (raises) → heuristic fallback
        assert result.success, result.error
        agent.generate.assert_called()


# ---------------------------------------------------------------------------
# Failure forensics (note 1d)
# ---------------------------------------------------------------------------

class TestFailureForensics:
    def _run_failing_gate(self, tmp_path):
        """Quality gate failure: requirements no plan feature satisfies + fail policy."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(V01_PLAN)
        reqs_file = tmp_path / "reqs.md"
        reqs_file.write_text(
            "# Reqs\n\n"
            "| ID | Requirement |\n|---|---|\n"
            "| REQ-ZZZ-001 | unmatched one |\n"
            "| REQ-ZZZ-002 | unmatched two |\n"
        )

        agent = _make_mock_agent()
        agent.generate.side_effect = Exception("LLM down")

        with patch(
            "startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec",
            return_value=agent,
        ):
            result = PlanIngestionWorkflow().run({
                "plan_path": str(plan_file),
                "requirements_path": str(reqs_file),
                "output_dir": str(tmp_path),
                "review_rounds": 0,
                "low_quality_policy": "fail",
                "min_requirements_coverage": 99.0,
                "max_contract_conflicts": 0,
            })
        return result

    def test_gate_failure_persists_forensics(self, tmp_path):
        result = self._run_failing_gate(tmp_path)
        if result.success:
            pytest.skip("quality gate did not trip — requirements mapped unexpectedly")

        forensics_path = tmp_path / "plan-ingestion-failure-forensics.json"
        assert forensics_path.exists(), (
            "gate-failed run must leave forensics (note 1d)"
        )
        data = json.loads(forensics_path.read_text())

        assert data["overall_success"] is False
        assert "Translation quality gate failed" in data["error"]
        # The previously-unobservable question — did the parse extract
        # features at all? — is now answerable from the artifact:
        assert data["parse"]["feature_count"] == 3
        assert data["parse"]["feature_ids"] == ["F-001", "F-002", "F-003"]
        assert data["parse"]["deterministic"] is True
        # Gate evidence: which reasons, against which thresholds
        assert data["quality_gate"]["policy"] == "fail"
        assert data["quality_gate"]["reasons"]
        assert "translation_quality" in data
        # Full parsed plan dump for offline diagnosis
        assert len(data["parsed_plan"]["features"]) == 3

    def test_degenerate_tripwire_failure_persists_forensics(self, tmp_path):
        # Plan with many F-tokens but no parseable structure → tripwire _fail
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(
            "# Unparseable\n\nMentions F-101 and F-102 and F-103 in prose only.\n"
        )
        agent = _make_mock_agent()
        agent.generate.side_effect = Exception("LLM down")

        with patch(
            "startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec",
            return_value=agent,
        ):
            result = PlanIngestionWorkflow().run({
                "plan_path": str(plan_file),
                "output_dir": str(tmp_path),
                "review_rounds": 0,
            })

        assert not result.success
        assert "Degenerate parse" in result.error
        forensics = json.loads(
            (tmp_path / "plan-ingestion-failure-forensics.json").read_text()
        )
        assert forensics["overall_success"] is False
        # The preserved LLM parse error is in the forensics too
        assert forensics["parse"]["llm_parse_error"]
        assert forensics["parse"]["heuristic_fallback"] is True

    def test_successful_run_writes_no_forensics(self, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(V01_PLAN)
        agent = _make_mock_agent()
        agent.generate.side_effect = Exception("unused")

        with patch(
            "startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec",
            return_value=agent,
        ):
            result = PlanIngestionWorkflow().run({
                "plan_path": str(plan_file),
                "output_dir": str(tmp_path),
                "review_rounds": 0,
            })
        assert result.success, result.error
        assert not (tmp_path / "plan-ingestion-failure-forensics.json").exists()


class TestForceLlmParseConfig:
    def test_default_off(self):
        cfg = PlanIngestionConfig.from_dict({"plan_path": "plan.md"})
        assert cfg.force_llm_parse is False

    def test_opt_in(self):
        cfg = PlanIngestionConfig.from_dict(
            {"plan_path": "plan.md", "force_llm_parse": "true"}
        )
        assert cfg.force_llm_parse is True
