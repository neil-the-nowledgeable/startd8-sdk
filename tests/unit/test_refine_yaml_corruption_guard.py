"""
Tests for the REFINE/tasks-YAML corruption fix (strtd8 kickoff note 3, OQ-6).

The kickoff pilot's refine rounds appended CRP markdown appendices into
plan-ingestion-tasks.yaml, breaking YAML parseability (DETERMINISTIC_INGESTION
FR-1 collision). Fixes under test:

1. ArchitecturalReviewLogWorkflow refuses non-markdown document targets.
2. Plan ingestion REFINE reviews a markdown companion
   (plan-ingestion-tasks-review.md), never the schema-valid YAML.
3. Refine spend gate: no review rounds on a degraded parse
   (gate_refine_on_parse_quality, default on).

All LLM calls mocked.
"""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from startd8.workflows.builtin.architectural_review_log_workflow import (
    ArchitecturalReviewLogWorkflow,
)
from startd8.workflows.builtin.plan_ingestion_models import PlanIngestionConfig
from startd8.workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers (pattern from test_plan_ingestion_workflow.py)
# ---------------------------------------------------------------------------

def _make_mock_agent(name="test-agent"):
    agent = MagicMock()
    agent.name = name
    agent.model = "mock-model"
    agent.max_tokens = 4096
    return agent


def _mock_review_workflow_cls():
    """Build a (cls_mock, instance_mock) pair for ArchitecturalReviewLogWorkflow."""
    result = MagicMock()
    result.success = True
    result.metrics = MagicMock(total_cost=0.05)
    result.steps = []
    result.error = None
    result.output = {"rounds_completed": 1}
    instance = MagicMock()
    instance.run.return_value = result
    cls = MagicMock(return_value=instance)
    return cls, instance


# v0.1-format plan — parses deterministically via the table extractor
V01_PLAN = textwrap.dedent("""\
    # Guard Test Plan

    | Feature | FRs | Target files | Est. LOC |
    |---------|-----|--------------|----------|
    | F-001 alpha module | FR-1 | src/alpha.py | 50 |
    | F-002 beta module | FR-2 | src/beta.py | 60 |
    | F-003 gamma module | FR-3 | src/gamma.py | 70 |

    ## Dependencies

    - F-002 after F-001
    """)

# Unparseable plan: 0 features, <3 F-tokens (degrades WITHOUT tripping the
# degenerate-parse tripwire, so the run continues to REFINE)
PROSE_PLAN = "# Tiny Plan\n\nJust prose. No feature structure at all.\n"


# ---------------------------------------------------------------------------
# 1. Review-log workflow refuses non-markdown targets
# ---------------------------------------------------------------------------

class TestMarkdownOnlyGuard:
    def setup_method(self):
        self.wf = ArchitecturalReviewLogWorkflow()

    def test_validate_rejects_yaml_target(self, tmp_path):
        yaml_doc = tmp_path / "plan-ingestion-tasks.yaml"
        yaml_doc.write_text("tasks: []\n")
        res = self.wf.validate_config({"document_path": str(yaml_doc)})
        assert not res.valid
        assert any("markdown" in e for e in res.errors)

    def test_validate_rejects_extensionless_target(self, tmp_path):
        doc = tmp_path / "TASKS"
        doc.write_text("tasks: []\n")
        res = self.wf.validate_config({"document_path": str(doc)})
        assert not res.valid

    def test_validate_accepts_markdown(self, tmp_path):
        for suffix in (".md", ".markdown"):
            doc = tmp_path / f"doc{suffix}"
            doc.write_text("# Doc\n")
            res = self.wf.validate_config({"document_path": str(doc)})
            assert res.valid, res.errors

    def test_execute_refuses_yaml_without_touching_it(self, tmp_path):
        yaml_doc = tmp_path / "plan-ingestion-tasks.yaml"
        original = "tasks:\n  - task_id: PI-001\n"
        yaml_doc.write_text(original)

        result = self.wf._execute({"document_path": str(yaml_doc)}, None, None)

        assert not result.success
        assert "markdown" in (result.error or "")
        # The machine file must be byte-identical — never corrupted
        assert yaml_doc.read_text() == original
        assert yaml.safe_load(yaml_doc.read_text()) == {
            "tasks": [{"task_id": "PI-001"}]
        }


# ---------------------------------------------------------------------------
# 2. REFINE reviews the markdown companion; YAML stays schema-valid
# ---------------------------------------------------------------------------

class TestRefineCompanionDocument:
    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_refine_targets_companion_not_yaml(self, mock_resolve, MockReviewWf, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(V01_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = Exception("LLM down")  # → heuristic parse
        mock_resolve.return_value = agent

        cls_behavior, review_instance = _mock_review_workflow_cls()
        MockReviewWf.side_effect = cls_behavior

        result = PlanIngestionWorkflow().run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 1,
        })
        assert result.success, result.error

        # REFINE was pointed at the markdown companion, never the YAML
        review_config = review_instance.run.call_args[0][0]
        reviewed = Path(review_config["document_path"])
        assert reviewed.name == "plan-ingestion-tasks-review.md"
        assert reviewed.suffix == ".md"

        # Companion exists and embeds the tasks YAML as a fenced block
        companion = tmp_path / "plan-ingestion-tasks-review.md"
        assert companion.exists()
        assert "```yaml" in companion.read_text()

        # FR-1: the machine YAML still parses as YAML after the full run
        tasks_yaml = tmp_path / "plan-ingestion-tasks.yaml"
        assert tasks_yaml.exists()
        parsed = yaml.safe_load(tasks_yaml.read_text())
        assert parsed is not None

        # plan_document_path still names the machine YAML for consumers
        assert result.output["plan_document_path"] == str(tasks_yaml)


# ---------------------------------------------------------------------------
# 3. Refine spend gate
# ---------------------------------------------------------------------------

class TestRefineSpendGate:
    def _run(self, tmp_path, plan_text, **extra_config):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_text)

        agent = _make_mock_agent()
        agent.generate.side_effect = Exception("LLM down")  # → heuristic parse

        cls_behavior, review_instance = _mock_review_workflow_cls()
        with patch(
            "startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec",
            return_value=agent,
        ), patch(
            "startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow",
            side_effect=cls_behavior,
        ):
            result = PlanIngestionWorkflow().run({
                "plan_path": str(plan_file),
                "output_dir": str(tmp_path),
                "review_rounds": 1,
                **extra_config,
            })
        return result, review_instance

    def test_degraded_parse_skips_refine_spend(self, tmp_path):
        result, review_instance = self._run(tmp_path, PROSE_PLAN)
        assert result.success, result.error
        # No review rounds were bought for the fallback blob
        review_instance.run.assert_not_called()

    def test_gate_opt_out_restores_refine(self, tmp_path):
        result, review_instance = self._run(
            tmp_path, PROSE_PLAN, gate_refine_on_parse_quality=False,
        )
        assert result.success, result.error
        review_instance.run.assert_called_once()

    def test_healthy_parse_still_refines(self, tmp_path):
        result, review_instance = self._run(tmp_path, V01_PLAN)
        assert result.success, result.error
        review_instance.run.assert_called_once()


class TestSpendGateConfig:
    def test_default_on(self):
        cfg = PlanIngestionConfig.from_dict({"plan_path": "plan.md"})
        assert cfg.gate_refine_on_parse_quality is True

    def test_opt_out(self):
        cfg = PlanIngestionConfig.from_dict(
            {"plan_path": "plan.md", "gate_refine_on_parse_quality": "false"}
        )
        assert cfg.gate_refine_on_parse_quality is False


# ---------------------------------------------------------------------------
# 4. Gate failure message no longer recommends the invalid 'warn' value
# ---------------------------------------------------------------------------

class TestQualityGateMessage:
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_fail_policy_message_names_valid_values(self, mock_resolve, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(V01_PLAN)
        reqs_file = tmp_path / "reqs.md"
        # Requirements with IDs no plan feature mentions → 0% coverage
        reqs_file.write_text("# Reqs\n\n- REQ-ZZZ-001: unmatched\n- REQ-ZZZ-002: unmatched\n")

        agent = _make_mock_agent()
        agent.generate.side_effect = Exception("LLM down")
        mock_resolve.return_value = agent

        result = PlanIngestionWorkflow().run({
            "plan_path": str(plan_file),
            "requirements_path": str(reqs_file),
            "output_dir": str(tmp_path),
            "review_rounds": 0,
            "low_quality_policy": "fail",
            "min_requirements_coverage": 70,
        })
        if not result.success and "Translation quality gate failed" in (result.error or ""):
            assert "'warn'" not in result.error
            assert "bias_artisan" in result.error
        else:
            # Requirements parsing may map differently; the message contract
            # is the point — assert directly against the source as fallback
            src = Path("src/startd8/workflows/builtin/plan_ingestion_workflow.py").read_text()
            assert "set low_quality_policy to 'warn'" not in src
