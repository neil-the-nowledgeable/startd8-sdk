# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Increment 1.1: CRP sdk-workflow executor + dual-renderer contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from startd8.models import TokenUsage
from startd8.workflows.loop_queue import (
    CrpReviewRequest,
    LoopJobStatus,
    LoopQueueConfig,
    LoopQueueValidationError,
    WorkflowLoopJob,
    WorkflowLoopQueue,
    map_crp_request_to_workflow_config,
    resolve_crp_workflow_id,
)
from startd8.workflows.loop_queue.renderer import render_bundle


def _request(plan: Path, requirements: Optional[Path] = None) -> CrpReviewRequest:
    data = {
        "plan_path": str(plan),
        "scope": "Architecture-focused review",
        "max_rounds": 1,
        "substantially_addressed_threshold": 3,
        "max_suggestions": 10,
        "enable_triage": False,
        "enable_apply": False,
    }
    if requirements is not None:
        data["requirements_path"] = str(requirements)
    return CrpReviewRequest.model_validate(data)


def _mock_agent(name: str = "test-agent", model: str = "test-model") -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.model = model
    agent.safety_settings = None
    agent.enable_prompt_caching = False
    agent.__class__.__module__ = "startd8.agents.claude"
    return agent


def _snippet(round_number: int) -> str:
    return (
        f"#### Review Round R{round_number}\n\n"
        f"- **Reviewer**: test-agent (test-model)\n"
        f"- **Date**: 2026-07-25 00:00:00 UTC\n"
        f"- **Scope**: Architecture-focused review\n\n"
        f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
        f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
        f"| R{round_number}-S1 | Architecture | high | Add circuit breakers | "
        f"Critical for resilience | Section 3 | Load testing |\n"
    )


def test_resolve_and_map_single_and_dual(tmp_path: Path):
    plan = tmp_path / "PLAN.md"
    reqs = tmp_path / "REQUIREMENTS.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    reqs.write_text("# Reqs\n", encoding="utf-8")

    dual = _request(plan, reqs)
    assert resolve_crp_workflow_id(dual) == "convergent-review"
    dual_cfg = map_crp_request_to_workflow_config(dual, "convergent-review")
    assert dual_cfg["plan_path"].endswith("PLAN.md")
    assert dual_cfg["requirements_path"].endswith("REQUIREMENTS.md")
    assert "review_template" not in dual_cfg
    assert "agent_template_path" not in dual_cfg

    single = _request(plan)
    assert resolve_crp_workflow_id(single) == "architectural-review-log"
    single_cfg = map_crp_request_to_workflow_config(single, "architectural-review-log")
    assert single_cfg["document_path"].endswith("PLAN.md")
    assert single_cfg["scope"] == "Architecture-focused review"
    assert single_cfg["enable_triage"] is False


def test_one_request_feeds_two_independent_renderers(tmp_path: Path):
    """FR-9 acceptance: one CrpReviewRequest → agent bundle + SDK config."""
    plan = tmp_path / "PLAN.md"
    plan.write_text("# Plan\n\nBody.\n", encoding="utf-8")
    template = tmp_path / "agent.md"
    template.write_text(
        "Round R{{round_number}} for {{plan_path}}\nScope: {{scope}}\n",
        encoding="utf-8",
    )
    request = CrpReviewRequest.model_validate(
        {
            "plan_path": str(plan),
            "scope": "Shared intent",
            "agent_template_path": str(template),
            "enable_triage": False,
            "enable_apply": False,
        }
    )

    bundle = render_bundle(
        request=request,
        round_number=1,
        artifact_dir=tmp_path / "artifacts",
    )
    text = bundle.read_text(encoding="utf-8")
    assert "Round R1" in text
    assert "Shared intent" in text
    assert "{{" not in text

    sdk_cfg = map_crp_request_to_workflow_config(request, "architectural-review-log")
    assert sdk_cfg["document_path"] == str(plan.resolve())
    assert "review_template" not in sdk_cfg
    assert "agent_template_path" not in sdk_cfg

    poisoned = request.model_copy(
        update={"review_template": text + "\nAlso R{n} and {{scope}}\n"}
    )
    with pytest.raises(LoopQueueValidationError, match="agent-surface"):
        map_crp_request_to_workflow_config(poisoned, "architectural-review-log")


def test_sdk_workflow_drain_with_scripted_agent(tmp_path: Path):
    plan = tmp_path / "PLAN.md"
    plan.write_text("# Plan\n\nArchitecture body.\n", encoding="utf-8")
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    job = WorkflowLoopJob(
        job_id="sdk-crp-1",
        loop_id="crp",
        executor="sdk-workflow",
        workflow_id="architectural-review-log",
        config={
            "plan_path": str(plan),
            "scope": "Architecture-focused review",
            "max_rounds": 1,
            "enable_triage": False,
            "enable_apply": False,
        },
    )
    queue.enqueue(job)

    agent = _mock_agent()
    tu = TokenUsage(input=100, output=50, total=150, model_name="test")
    agent.generate.return_value = (_snippet(1), 500, tu)

    result_job = queue.run_next("sdk-crp-1", agents=[agent])
    assert result_job.status is LoopJobStatus.COMPLETED
    assert result_job.rounds_completed() == 1
    assert "#### Review Round R1" in plan.read_text(encoding="utf-8")
    assert (queue.storage.artifact_dir("sdk-crp-1") / "sdk-run-result.json").is_file()


def test_sdk_dry_run_does_not_mutate_doc(tmp_path: Path):
    plan = tmp_path / "PLAN.md"
    original = "# Plan\n\nBody.\n"
    plan.write_text(original, encoding="utf-8")
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    queue.enqueue(
        WorkflowLoopJob(
            job_id="sdk-dry",
            loop_id="crp",
            executor="sdk-workflow",
            workflow_id="architectural-review-log",
            config={
                "plan_path": str(plan),
                "scope": "Dry run",
                "max_rounds": 1,
                "enable_triage": False,
                "enable_apply": False,
            },
        )
    )
    job = queue.run_next("sdk-dry", dry_run=True)
    assert job.status is LoopJobStatus.PENDING
    assert plan.read_text(encoding="utf-8") == original
    result = json.loads(
        (queue.storage.artifact_dir("sdk-dry") / "sdk-run-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["dry_run"] is True
    assert result["success"] is True


def test_enqueue_rejects_convergent_without_dual_paths(tmp_path: Path):
    plan = tmp_path / "PLAN.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="convergent-review"):
        queue.enqueue(
            WorkflowLoopJob(
                job_id="bad-dual",
                loop_id="crp",
                executor="sdk-workflow",
                workflow_id="convergent-review",
                config={
                    "plan_path": str(plan),
                    "scope": "Missing requirements",
                },
            )
        )
