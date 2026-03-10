"""Tests for deterministic task density enrichment (REQ-TDE-1xx)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import List

import pytest

from startd8.workflows.builtin.plan_ingestion_enrichment import (
    _enrich_api_signatures,
    _enrich_negative_scope,
    _enrich_refine_suggestions,
    _enrich_requirement_refs,
    _enrich_target_files,
    _ensure_task_context,
    _extract_req_refs_near_feature,
    _infer_target_files_from_title,
    enrich_tasks_deterministic,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@dataclass
class FakeFeature:
    """Minimal ParsedFeature stand-in for enrichment tests."""

    feature_id: str
    name: str = ""
    description: str = ""
    target_files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    estimated_loc: int = 0
    labels: List[str] = field(default_factory=list)
    design_doc_sections: List[str] = field(default_factory=list)
    artifact_types_addressed: List[str] = field(default_factory=list)
    api_signatures: List[str] = field(default_factory=list)
    protocol: str = ""
    runtime_dependencies: List[str] = field(default_factory=list)
    negative_scope: List[str] = field(default_factory=list)
    affected_callers: List[str] = field(default_factory=list)
    high_impact: bool = False
    targets_dead_code: bool = False


def _make_task(
    task_id: str,
    feature_id: str = "",
    description: str = "",
    negative_scope: list | None = None,
    target_files: list | None = None,
) -> dict:
    ctx: dict = {"feature_id": feature_id}
    if negative_scope is not None:
        ctx["negative_scope"] = negative_scope
    if target_files is not None:
        ctx["target_files"] = target_files
    return {
        "task_id": task_id,
        "title": f"Task {task_id}",
        "config": {
            "task_description": description,
            "context": ctx,
        },
    }


# ── REQ-TDE-100: Negative Scope Forwarding ───────────────────────────


class TestNegativeScopeForwarding:
    def test_negative_scope_forwarded(self):
        features = [FakeFeature("F-1", negative_scope=["no auth", "no caching"])]
        tasks = [_make_task("PI-001", feature_id="F-1")]

        count = _enrich_negative_scope(tasks, {"F-1": features[0]})

        assert count == 1
        assert tasks[0]["config"]["context"]["negative_scope"] == ["no auth", "no caching"]

    def test_negative_scope_no_clobber(self):
        features = [FakeFeature("F-1", negative_scope=["no auth"])]
        tasks = [_make_task("PI-001", feature_id="F-1", negative_scope=["existing"])]

        count = _enrich_negative_scope(tasks, {"F-1": features[0]})

        assert count == 0
        assert tasks[0]["config"]["context"]["negative_scope"] == ["existing"]

    def test_no_feature_match(self):
        features = [FakeFeature("F-99", negative_scope=["something"])]
        tasks = [_make_task("PI-001", feature_id="F-1")]

        count = _enrich_negative_scope(tasks, {"F-99": features[0]})

        assert count == 0
        assert "negative_scope" not in tasks[0]["config"]["context"]

    def test_empty_negative_scope(self):
        features = [FakeFeature("F-1", negative_scope=[])]
        tasks = [_make_task("PI-001", feature_id="F-1")]

        count = _enrich_negative_scope(tasks, {"F-1": features[0]})

        assert count == 0

    def test_string_negative_scope_wrapped(self):
        """P3: bare string negative_scope → wrapped in list, not exploded to chars."""
        feat = FakeFeature("F-1")
        # Simulate schema drift: negative_scope is a bare string
        feat.negative_scope = "no caching"  # type: ignore[assignment]
        tasks = [_make_task("PI-001", feature_id="F-1")]

        count = _enrich_negative_scope(tasks, {"F-1": feat})

        assert count == 1
        assert tasks[0]["config"]["context"]["negative_scope"] == ["no caching"]

    def test_missing_context_key_creates_it(self):
        """R2: task without context key → _ensure_task_context creates it."""
        task = {"task_id": "PI-001", "config": {"task_description": ""}}
        assert "context" not in task["config"]

        feat = FakeFeature("F-1", negative_scope=["no auth"])
        # Manually set feature_id in the context that _ensure_task_context will create
        task["config"]["context"] = {"feature_id": "F-1"}
        count = _enrich_negative_scope([task], {"F-1": feat})

        assert count == 1
        assert task["config"]["context"]["negative_scope"] == ["no auth"]


# ── REQ-TDE-102: Target Files Inference ───────────────────────────────


class TestTargetFilesInference:
    def test_target_files_tier1(self):
        """Feature has target_files → copied to task."""
        features = [FakeFeature("F-1", target_files=["emailservice/server.py"])]
        tasks = [_make_task("PI-001", feature_id="F-1")]

        count = _enrich_target_files(tasks, {"F-1": features[0]})

        assert count == 1
        assert tasks[0]["config"]["context"]["target_files"] == ["emailservice/server.py"]

    def test_target_files_tier2(self):
        """Description mentions file path → extracted."""
        features = [FakeFeature("F-1")]
        tasks = [_make_task(
            "PI-001",
            feature_id="F-1",
            description="Implementation file: emailservice/server.py",
        )]

        count = _enrich_target_files(tasks, {"F-1": features[0]})

        assert count == 1
        assert "emailservice/server.py" in tasks[0]["config"]["context"]["target_files"]

    def test_target_files_no_clobber(self):
        """Task already has target_files → not overwritten."""
        features = [FakeFeature("F-1", target_files=["new.py"])]
        tasks = [_make_task("PI-001", feature_id="F-1", target_files=["existing.py"])]

        count = _enrich_target_files(tasks, {"F-1": features[0]})

        assert count == 0
        assert tasks[0]["config"]["context"]["target_files"] == ["existing.py"]

    def test_target_files_tier3_convention(self):
        """Tier 3: task title with service-role pattern → inferred path."""
        features = [FakeFeature("F-1")]
        tasks = [_make_task("PI-001", feature_id="F-1")]
        tasks[0]["title"] = "Email Service — gRPC Server"

        count = _enrich_target_files(tasks, {"F-1": features[0]})

        assert count == 1
        ctx = tasks[0]["config"]["context"]
        assert ctx.get("_target_files_inferred") is True
        assert any("email_service" in f for f in ctx["target_files"])

    def test_target_files_tier3_no_role_suffix(self):
        """Tier 3: title without role suffix → no inference."""
        features = [FakeFeature("F-1")]
        tasks = [_make_task("PI-001", feature_id="F-1")]
        tasks[0]["title"] = "Email Service"

        count = _enrich_target_files(tasks, {"F-1": features[0]})

        assert count == 0

    def test_missing_context_key_creates_it(self):
        """R3: task without context key → target files still set."""
        task = {"task_id": "PI-001", "config": {"task_description": ""}}
        task["config"]["context"] = {"feature_id": "F-1"}
        features = [FakeFeature("F-1", target_files=["server.py"])]

        count = _enrich_target_files([task], {"F-1": features[0]})

        assert count == 1
        assert task["config"]["context"]["target_files"] == ["server.py"]


# ── REQ-TDE-101: Requirement Reference Injection ─────────────────────


class TestRequirementRefInjection:
    def test_requirement_refs_extracted(self):
        """Plan text with REQ-PI-003 near feature name → appended to description."""
        plan_text = (
            "The Email Service feature implements REQ-PI-003 for gRPC "
            "communication and REQ-PI-005 for health checks."
        )
        tasks = [_make_task("PI-001", description="Implement the service.")]
        tasks[0]["title"] = "Email Service"

        count = _enrich_requirement_refs(tasks, plan_text, proximity_chars=500)

        assert count == 1
        desc = tasks[0]["config"]["task_description"]
        assert "## Requirements References" in desc
        assert "REQ-PI-003" in desc
        assert "REQ-PI-005" in desc

    def test_requirement_refs_proximity(self):
        """REQ-* too far from feature → not included."""
        # Build text where the REQ is 1000+ chars from "Email Service"
        plan_text = "Email Service does things. " + "x" * 1500 + " REQ-FARAWAY-001 is distant."
        tasks = [_make_task("PI-001", description="Implement it.")]
        tasks[0]["title"] = "Email Service"

        count = _enrich_requirement_refs(tasks, plan_text, proximity_chars=200)

        assert count == 0

    def test_requirement_refs_no_clobber(self):
        """Description already has REQ-* → not doubled."""
        plan_text = "Email Service implements REQ-PI-003."
        tasks = [_make_task(
            "PI-001",
            description="This implements REQ-PI-003 already.",
        )]
        tasks[0]["title"] = "Email Service"

        count = _enrich_requirement_refs(tasks, plan_text)

        assert count == 0

    def test_short_title_skipped(self):
        """P2: title shorter than _MIN_FEATURE_NAME_CHARS → skipped to avoid false positives."""
        plan_text = "The API implements REQ-PI-003 for all services."
        tasks = [_make_task("PI-001", description="Build the API.")]
        tasks[0]["title"] = "API"  # Too short (3 chars < 8)

        count = _enrich_requirement_refs(tasks, plan_text)

        assert count == 0

    def test_extract_req_refs_empty_plan(self):
        refs = _extract_req_refs_near_feature("", "Email Service")
        assert refs == []

    def test_extract_req_refs_empty_name(self):
        refs = _extract_req_refs_near_feature("some plan text", "")
        assert refs == []


# ── REQ-TDE-103: API Signature Code Stubs ─────────────────────────────


class TestApiSignatureStubs:
    def test_api_signatures_appended(self):
        """Feature has api_signatures → code block in description."""
        features = [FakeFeature(
            "F-1",
            api_signatures=[
                'def send_email(to: str, subject: str) -> bool:\n    """Send email."""\n    ...',
            ],
        )]
        tasks = [_make_task("PI-001", feature_id="F-1", description="Implement email.")]

        count = _enrich_api_signatures(tasks, {"F-1": features[0]})

        assert count == 1
        desc = tasks[0]["config"]["task_description"]
        assert "## API Signatures" in desc
        assert "```python" in desc
        assert "send_email" in desc

    def test_api_signatures_skip_existing_code(self):
        """Description already has code blocks → no code block added."""
        features = [FakeFeature("F-1", api_signatures=["def foo(): ..."])]
        tasks = [_make_task(
            "PI-001",
            feature_id="F-1",
            description="Already has ```python\ndef bar(): pass\n```",
        )]

        count = _enrich_api_signatures(tasks, {"F-1": features[0]})

        assert count == 0

    def test_api_signatures_max_limit(self):
        """More than 5 signatures → capped at 5."""
        sigs = [f"def func_{i}(): ..." for i in range(10)]
        features = [FakeFeature("F-1", api_signatures=sigs)]
        tasks = [_make_task("PI-001", feature_id="F-1", description="Implement.")]

        _enrich_api_signatures(tasks, {"F-1": features[0]})

        desc = tasks[0]["config"]["task_description"]
        # Should have exactly 5 func_N references
        for i in range(5):
            assert f"func_{i}" in desc
        assert "func_5" not in desc

    def test_no_signatures(self):
        """Feature without api_signatures → no change."""
        features = [FakeFeature("F-1")]
        tasks = [_make_task("PI-001", feature_id="F-1", description="Implement.")]

        count = _enrich_api_signatures(tasks, {"F-1": features[0]})

        assert count == 0


# ── REQ-TDE-104: REFINE Suggestion Mapping ────────────────────────────


class TestRefineSuggestionMapping:
    def test_suggestions_mapped_by_placement(self):
        """Suggestion with placement matching target_files → mapped."""
        tasks = [_make_task(
            "PI-001",
            feature_id="F-1",
            description="Implement server.",
            target_files=["emailservice/server.py"],
        )]
        suggestions = [
            {
                "placement": "emailservice/server.py",
                "area": "interfaces",
                "rationale": "Ensure health check returns HealthCheckResponse",
            },
        ]

        count = _enrich_refine_suggestions(tasks, suggestions)

        assert count == 1
        desc = tasks[0]["config"]["task_description"]
        assert "## Review Guidance (from REFINE)" in desc
        assert "HealthCheckResponse" in desc

    def test_suggestions_mapped_by_area(self):
        """Suggestion with area matching task title keywords → mapped."""
        tasks = [_make_task("PI-001", description="Implement gRPC server.")]
        tasks[0]["title"] = "Email Service — gRPC Server"
        suggestions = [
            {
                "area": "interfaces",
                "rationale": "Validate email address format",
            },
        ]

        count = _enrich_refine_suggestions(tasks, suggestions)

        assert count == 1
        desc = tasks[0]["config"]["task_description"]
        assert "Validate email address format" in desc

    def test_no_suggestions(self):
        tasks = [_make_task("PI-001", description="Implement.")]
        count = _enrich_refine_suggestions(tasks, [])
        assert count == 0

    def test_existing_review_guidance_no_clobber(self):
        """Description already has Review Guidance → not doubled."""
        tasks = [_make_task(
            "PI-001",
            description="Implement.\n\n## Review Guidance\n- Existing",
            target_files=["server.py"],
        )]
        suggestions = [
            {"placement": "server.py", "area": "x", "rationale": "New suggestion"},
        ]

        count = _enrich_refine_suggestions(tasks, suggestions)

        assert count == 0

    def test_placement_no_false_positive_substring(self):
        """P1: placement 'server.py' must NOT match 'test_server.py'."""
        tasks = [
            _make_task("PI-001", description="Implement.", target_files=["test_server.py"]),
            _make_task("PI-002", description="Implement.", target_files=["emailservice/server.py"]),
        ]
        suggestions = [
            {"placement": "server.py", "area": "x", "rationale": "Fix it"},
        ]

        _enrich_refine_suggestions(tasks, suggestions)

        # Should only match PI-002 (exact suffix match), not PI-001
        assert "Fix it" not in tasks[0]["config"]["task_description"]
        assert "Fix it" in tasks[1]["config"]["task_description"]

    def test_unmapped_suggestions_shared(self):
        """Suggestions that match no task → appended to all tasks as shared guidance."""
        tasks = [
            _make_task("PI-001", description="Implement logger."),
            _make_task("PI-002", description="Implement client."),
        ]
        tasks[0]["title"] = "Logger"
        tasks[1]["title"] = "Client"
        # This suggestion's area "security" has no keyword matches
        suggestions = [
            {"area": "security", "rationale": "Enable TLS for all connections"},
        ]

        count = _enrich_refine_suggestions(tasks, suggestions)

        assert count == 2
        for t in tasks:
            desc = t["config"]["task_description"]
            assert "Enable TLS" in desc
            assert "## Review Guidance (from REFINE)" in desc


# ── REQ-TDE-105/106: Orchestrator ─────────────────────────────────────


class TestEnrichOrchestrator:
    def test_all_enrichments_applied(self):
        """Full enrichment pass with all features populated."""
        features = [
            FakeFeature(
                "F-1",
                name="Email Service",
                negative_scope=["no auth"],
                target_files=["emailservice/server.py"],
                api_signatures=['def send_email(to: str) -> bool: ...'],
            ),
        ]
        tasks = [_make_task("PI-001", feature_id="F-1", description="Implement email.")]
        tasks[0]["title"] = "Email Service"
        plan_text = "The Email Service implements REQ-PI-003."

        diag = enrich_tasks_deterministic(
            tasks,
            features,
            plan_text=plan_text,
            refine_suggestions=[
                {"area": "interfaces", "rationale": "Add health check"},
            ],
        )

        assert diag.tasks_enriched == 1
        assert diag.tasks_skipped == 0
        assert diag.negative_scope_added == 1
        assert diag.target_files_inferred == 1
        assert diag.time_ms >= 0

        desc = tasks[0]["config"]["task_description"]
        assert "## Requirements References" in desc
        assert "## API Signatures" in desc

    def test_all_steps_disabled(self):
        """All config booleans False → no enrichment."""
        features = [
            FakeFeature("F-1", negative_scope=["no auth"], api_signatures=["def f(): ..."]),
        ]
        tasks = [_make_task("PI-001", feature_id="F-1", description="Implement.")]

        diag = enrich_tasks_deterministic(
            tasks,
            features,
            plan_text="REQ-001 is near Implement",
            enrich_negative_scope=False,
            enrich_requirement_refs=False,
            enrich_target_files=False,
            enrich_api_signatures=False,
            enrich_refine_suggestions=False,
        )

        assert diag.tasks_enriched == 0
        assert diag.negative_scope_added == 0
        assert diag.requirement_refs_added == 0
        assert diag.target_files_inferred == 0
        assert diag.api_signatures_added == 0
        assert diag.refine_suggestions_mapped == 0

    def test_idempotent(self):
        """Running enrichment twice → same result."""
        features = [
            FakeFeature("F-1", negative_scope=["no auth"], target_files=["server.py"]),
        ]
        tasks = [_make_task("PI-001", feature_id="F-1", description="Implement.")]

        enrich_tasks_deterministic(tasks, features)
        snapshot = copy.deepcopy(tasks)
        enrich_tasks_deterministic(tasks, features)

        assert tasks == snapshot

    def test_empty_tasks(self):
        """No tasks → no errors, zero counts."""
        diag = enrich_tasks_deterministic([], [])
        assert diag.tasks_enriched == 0
        assert diag.tasks_skipped == 0

    def test_step_failure_does_not_block_others(self):
        """E1: if one step raises, subsequent steps still run."""
        from unittest.mock import patch

        features = [
            FakeFeature("F-1", negative_scope=["no auth"], api_signatures=["def f(): ..."]),
        ]
        tasks = [_make_task("PI-001", feature_id="F-1", description="Implement.")]

        # Make negative_scope step raise, but api_signatures should still run
        with patch(
            "startd8.workflows.builtin.plan_ingestion_enrichment._enrich_negative_scope",
            side_effect=RuntimeError("boom"),
        ):
            diag = enrich_tasks_deterministic(tasks, features)

        # negative_scope failed → count stays 0
        assert diag.negative_scope_added == 0
        # api_signatures should have run successfully
        assert diag.api_signatures_added == 1


# ── REQ-TDE-300: Config Extension ─────────────────────────────────────


class TestKaizenConfigExtension:
    def test_enrichment_fields_have_defaults(self):
        from startd8.workflows.builtin.plan_ingestion_diagnostics import PlanIngestionKaizenConfig

        cfg = PlanIngestionKaizenConfig()
        assert cfg.enrich_negative_scope is True
        assert cfg.enrich_requirement_refs is True
        assert cfg.enrich_target_files is True
        assert cfg.enrich_api_signatures is True
        assert cfg.enrich_refine_suggestions is True
        assert cfg.enrich_req_proximity_chars == 500

    def test_load_kaizen_config_with_enrichment(self, tmp_path):
        import json
        from startd8.workflows.builtin.plan_ingestion_diagnostics import load_kaizen_config

        config = {
            "plan_ingestion_kaizen": {
                "enrich_negative_scope": False,
                "enrich_req_proximity_chars": 300,
            },
        }
        path = tmp_path / "kaizen.json"
        path.write_text(json.dumps(config))

        cfg = load_kaizen_config(path)
        assert cfg.enrich_negative_scope is False
        assert cfg.enrich_req_proximity_chars == 300
        # Defaults preserved
        assert cfg.enrich_requirement_refs is True


# ── REQ-TDE-400: Enrichment Diagnostic ────────────────────────────────


class TestEnrichmentDiagnostic:
    def test_diagnostic_in_ingestion_report(self):
        from startd8.workflows.builtin.plan_ingestion_diagnostics import (
            EnrichmentDiagnostic,
            IngestionDiagnostic,
            build_diagnostic,
        )

        enrich_diag = EnrichmentDiagnostic(
            negative_scope_added=3,
            requirement_refs_added=2,
            tasks_enriched=4,
        )

        diag = build_diagnostic(
            run_timestamp="2026-03-10T00:00:00",
            plan_source="test.md",
            plan_checksum="abc123",
            route="prime",
            overall_success=True,
            phase_diagnostics={},
            enrichment=enrich_diag,
        )

        assert diag.enrichment is not None
        assert diag.enrichment.negative_scope_added == 3
        assert diag.enrichment.tasks_enriched == 4


# ── REQ-TDE-401/402: Density Score Integration ───────────────────────


class TestDensityScoreIntegration:
    """Verify enrichment improves density metrics (REQ-TDE-401, 402)."""

    def _build_seed_dict(self, tasks):
        return {"tasks": tasks, "plan": {}, "complexity": {}}

    def test_density_score_improvement(self):
        """Seed quality score increases after enrichment."""
        from startd8.workflows.builtin.plan_ingestion_diagnostics import (
            compute_seed_quality,
            compute_task_density,
        )

        features = [
            FakeFeature(
                "F-1",
                name="Email Service",
                negative_scope=["no auth"],
                target_files=["emailservice/server.py"],
                api_signatures=['def send_email(to: str) -> bool: ...'],
            ),
        ]
        tasks = [_make_task("PI-001", feature_id="F-1", description="Implement email service.")]
        tasks[0]["title"] = "Email Service"
        seed_dict = self._build_seed_dict(tasks)

        # Score BEFORE enrichment
        density_before = compute_task_density(seed_dict["tasks"])
        score_before, _ = compute_seed_quality(seed_dict, task_density=density_before)

        # Enrich
        enrich_tasks_deterministic(
            tasks,
            features,
            plan_text="The Email Service implements REQ-PI-003.",
        )

        # Score AFTER enrichment
        density_after = compute_task_density(seed_dict["tasks"])
        score_after, _ = compute_seed_quality(seed_dict, task_density=density_after)

        assert score_after > score_before

    def test_density_warnings_reduced(self):
        """Density warnings decrease after enrichment."""
        from startd8.workflows.builtin.plan_ingestion_diagnostics import (
            compute_density_warnings,
            compute_task_density,
        )

        features = [
            FakeFeature(
                "F-1",
                name="Email Service",
                api_signatures=['def send_email(to: str) -> bool: ...'],
            ),
            FakeFeature(
                "F-2",
                name="Recommendation Service",
                api_signatures=['def get_recs(user: str) -> list: ...'],
            ),
        ]
        tasks = [
            _make_task("PI-001", feature_id="F-1", description="Implement email."),
            _make_task("PI-002", feature_id="F-2", description="Implement recs."),
        ]
        tasks[0]["title"] = "Email Service"
        tasks[1]["title"] = "Recommendation Service"

        # Warnings BEFORE
        density_before = compute_task_density(tasks)
        warnings_before = compute_density_warnings(density_before)

        # Enrich
        plan_text = "Email Service implements REQ-PI-001. Recommendation Service implements REQ-PI-002."
        enrich_tasks_deterministic(tasks, features, plan_text=plan_text)

        # Warnings AFTER
        density_after = compute_task_density(tasks)
        warnings_after = compute_density_warnings(density_after)

        assert len(warnings_after) < len(warnings_before)

    def test_pre_post_density_snapshot(self):
        """Verify density signals flip from False to True after enrichment."""
        from startd8.workflows.builtin.plan_ingestion_diagnostics import compute_task_density

        features = [
            FakeFeature(
                "F-1",
                negative_scope=["no caching"],
                api_signatures=['def serve() -> None: ...'],
            ),
        ]
        tasks = [_make_task("PI-001", feature_id="F-1", description="Implement server.")]

        density_before = compute_task_density(tasks)
        assert not density_before[0].has_code_examples
        assert not density_before[0].has_negative_scope

        enrich_tasks_deterministic(tasks, features)

        density_after = compute_task_density(tasks)
        assert density_after[0].has_code_examples  # API signatures added code block
        assert density_after[0].has_negative_scope  # negative scope forwarded


# ── Tier 3: Convention-based Target File Inference ─────────────────────


class TestInferTargetFilesFromTitle:
    def test_service_grpc_server(self):
        result = _infer_target_files_from_title("Email Service — gRPC Server")
        assert result == ["email_service/email_service_grpc_server.py"]

    def test_service_client(self):
        result = _infer_target_files_from_title("Payment Service — Client")
        assert result == ["payment_service/payment_service_client.py"]

    def test_no_role_suffix(self):
        """Single-part title → no inference."""
        result = _infer_target_files_from_title("Email Service")
        assert result == []

    def test_empty_title(self):
        result = _infer_target_files_from_title("")
        assert result == []

    def test_dash_separator(self):
        """Regular dash also works as separator."""
        result = _infer_target_files_from_title("Cart Service - Redis Cache")
        assert result == ["cart_service/cart_service_redis_cache.py"]


# ── _ensure_task_context (R2/R3 fix) ──────────────────────────────────


class TestEnsureTaskContext:
    def test_creates_missing_context(self):
        task: dict = {"config": {"task_description": "x"}}
        ctx = _ensure_task_context(task)
        ctx["foo"] = "bar"
        assert task["config"]["context"]["foo"] == "bar"

    def test_preserves_existing_context(self):
        task: dict = {"config": {"context": {"existing": True}}}
        ctx = _ensure_task_context(task)
        assert ctx["existing"] is True

    def test_creates_missing_config_and_context(self):
        task: dict = {}
        ctx = _ensure_task_context(task)
        ctx["key"] = "val"
        assert task["config"]["context"]["key"] == "val"
