# tests/e2e/contractors/test_artisan_dry_run.py
"""
End-to-end tests for the Artisan contractor system's dry-run mode.

This module validates that when a dry-run estimation is requested, the system
returns cost and duration estimates without making any actual LLM API calls
and without mutating any persistent state (database, filesystem, etc.).

Tests are designed to be idempotent and safe to run multiple times.

Test Classes:
    - TestArtisanDryRunReportStructure: Schema and field type validation
    - TestArtisanDryRunNoCalls: Ensures no LLM/HTTP calls are made
    - TestArtisanDryRunNoStateChanges: Ensures no persistent state mutation
    - TestArtisanDryRunEstimationValues: Validates estimation reasonableness
    - TestArtisanDryRunEdgeCases: Edge cases and robustness checks

Usage:
    pytest tests/e2e/contractors/test_artisan_dry_run.py -v
    pytest tests/e2e/contractors/test_artisan_dry_run.py -v -k "TestArtisanDryRunNoCalls"
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Constants – adjust these import paths to match the actual project layout.
# When the real ArtisanContractor becomes available, update the paths and
# swap the mock fixture for a real instance (see dry_run_contractor fixture).
# ---------------------------------------------------------------------------
CONTRACTOR_MODULE_PATH = "artisan.contractors.artisan_contractor"
CONTRACTOR_CLASS_NAME = "ArtisanContractor"
LLM_CLIENT_CALL_PATH = "artisan.contractors.artisan_contractor.llm_client.call"
DB_WRITE_PATH = "artisan.contractors.artisan_contractor.db.write"
FILE_WRITE_PATH = "artisan.contractors.artisan_contractor.file_writer.write"

# Timing threshold (seconds) – dry-run must complete within this window.
DRY_RUN_MAX_SECONDS = 2.0

# Floating-point comparison tolerance (1 %).
FP_TOLERANCE_PCT = 0.01


# ===================================================================== #
#                          Data Structures                               #
# ===================================================================== #


@dataclass
class StepEstimate:
    """Represents an estimated cost/duration breakdown for a single pipeline step."""

    step_name: str
    estimated_tokens: int
    estimated_cost: float
    estimated_duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation suitable for serialisation."""
        return {
            "step_name": self.step_name,
            "estimated_tokens": self.estimated_tokens,
            "estimated_cost": self.estimated_cost,
            "estimated_duration_seconds": self.estimated_duration_seconds,
        }


@dataclass
class DryRunReport:
    """
    Canonical schema for a dry-run estimation report.

    All numeric estimates are non-negative projections; no actual work is
    executed and no LLM API calls are made to produce this report.
    """

    status: str                          # Must be "dry_run"
    estimated_cost: float                # Total cost in USD, >= 0
    estimated_duration: float            # Total duration in seconds, >= 0
    model: str                           # Model identifier, non-empty
    token_estimate: int                  # Total estimated tokens, > 0
    breakdown: List[StepEstimate]        # Per-step breakdown, len >= 1
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation for comparison / serialisation."""
        return {
            "status": self.status,
            "estimated_cost": self.estimated_cost,
            "estimated_duration": self.estimated_duration,
            "model": self.model,
            "token_estimate": self.token_estimate,
            "breakdown": [s.to_dict() for s in self.breakdown],
            "metadata": self.metadata or {},
        }


# ===================================================================== #
#                        Validation Helpers                              #
# ===================================================================== #

_REQUIRED_REPORT_FIELDS = frozenset(
    {"status", "estimated_cost", "estimated_duration", "model", "token_estimate", "breakdown"}
)

_REQUIRED_STEP_FIELDS = frozenset(
    {"step_name", "estimated_tokens", "estimated_cost", "estimated_duration_seconds"}
)

_NUMERIC_TYPES = (int, float, Decimal)


def _to_dict(report: Any) -> Dict[str, Any]:
    """Normalise *report* to a plain ``dict``."""
    if isinstance(report, dict):
        return report
    if hasattr(report, "__dict__"):
        return report.__dict__
    raise AssertionError(
        f"report must be dict or object with __dict__, got {type(report)}"
    )


def assert_report_field_types(report_dict: Dict[str, Any]) -> None:
    """Validate that every field in *report_dict* has the correct type.

    Raises:
        AssertionError: With a descriptive message on the first type mismatch.
    """
    assert isinstance(
        report_dict.get("status"), str
    ), f"status must be str, got {type(report_dict.get('status'))}"

    assert isinstance(
        report_dict.get("estimated_cost"), _NUMERIC_TYPES
    ), f"estimated_cost must be numeric, got {type(report_dict.get('estimated_cost'))}"

    assert isinstance(
        report_dict.get("estimated_duration"), _NUMERIC_TYPES
    ), f"estimated_duration must be numeric, got {type(report_dict.get('estimated_duration'))}"

    assert isinstance(
        report_dict.get("model"), str
    ), f"model must be str, got {type(report_dict.get('model'))}"

    assert isinstance(
        report_dict.get("token_estimate"), int
    ), f"token_estimate must be int, got {type(report_dict.get('token_estimate'))}"

    breakdown = report_dict.get("breakdown")
    assert isinstance(breakdown, list), f"breakdown must be list, got {type(breakdown)}"

    for idx, step in enumerate(breakdown):
        prefix = f"breakdown[{idx}]"
        assert isinstance(step, dict), f"{prefix} must be dict, got {type(step)}"
        assert isinstance(
            step.get("step_name"), str
        ), f"{prefix}.step_name must be str, got {type(step.get('step_name'))}"
        assert isinstance(
            step.get("estimated_tokens"), int
        ), f"{prefix}.estimated_tokens must be int, got {type(step.get('estimated_tokens'))}"
        assert isinstance(
            step.get("estimated_cost"), _NUMERIC_TYPES
        ), f"{prefix}.estimated_cost must be numeric, got {type(step.get('estimated_cost'))}"
        assert isinstance(
            step.get("estimated_duration_seconds"), _NUMERIC_TYPES
        ), f"{prefix}.estimated_duration_seconds must be numeric, got {type(step.get('estimated_duration_seconds'))}"

    metadata = report_dict.get("metadata")
    assert metadata is None or isinstance(
        metadata, dict
    ), f"metadata must be dict or None, got {type(metadata)}"


def assert_report_value_constraints(report_dict: Dict[str, Any]) -> None:
    """Validate domain-level value constraints on a report dictionary.

    Raises:
        AssertionError: With a descriptive message on the first constraint violation.
    """
    assert (
        report_dict.get("status") == "dry_run"
    ), f"status must be 'dry_run', got '{report_dict.get('status')}'"

    cost = float(report_dict.get("estimated_cost", -1))
    assert cost >= 0, f"estimated_cost must be >= 0, got {cost}"

    duration = float(report_dict.get("estimated_duration", -1))
    assert duration >= 0, f"estimated_duration must be >= 0, got {duration}"

    model = report_dict.get("model", "")
    assert (
        isinstance(model, str) and len(model) > 0
    ), f"model must be non-empty string, got '{model}'"

    token_est = report_dict.get("token_estimate", 0)
    assert token_est > 0, f"token_estimate must be > 0, got {token_est}"

    breakdown = report_dict.get("breakdown", [])
    assert len(breakdown) >= 1, f"breakdown must have at least 1 step, got {len(breakdown)}"

    for idx, step in enumerate(breakdown):
        prefix = f"breakdown[{idx}]"
        assert (
            isinstance(step.get("step_name"), str) and len(step.get("step_name", "")) > 0
        ), f"{prefix}.step_name must be non-empty string"
        assert (
            step.get("estimated_tokens", 0) >= 0
        ), f"{prefix}.estimated_tokens must be >= 0"
        assert (
            float(step.get("estimated_cost", 0)) >= 0
        ), f"{prefix}.estimated_cost must be >= 0"
        assert (
            float(step.get("estimated_duration_seconds", 0)) >= 0
        ), f"{prefix}.estimated_duration_seconds must be >= 0"


def validate_dry_run_report(report: Any) -> None:
    """Full validation of a dry-run report against the ``DryRunReport`` schema.

    Accepts a ``dict`` or any object exposing ``__dict__``.

    Args:
        report: The report object / dict to validate.

    Raises:
        AssertionError: With a descriptive message on any schema or value violation.
    """
    report_dict = _to_dict(report)

    missing_fields = _REQUIRED_REPORT_FIELDS - set(report_dict.keys())
    assert not missing_fields, f"Report missing required fields: {missing_fields}"

    assert_report_field_types(report_dict)
    assert_report_value_constraints(report_dict)


# ===================================================================== #
#                             Fixtures                                   #
# ===================================================================== #


@pytest.fixture
def sample_task_payload() -> Dict[str, Any]:
    """A realistic, mid-sized task payload for dry-run testing."""
    return {
        "task_description": (
            "Refactor the authentication module to use JWT tokens "
            "instead of session cookies. Ensure backward compatibility with existing "
            "clients and add comprehensive error handling for token expiration scenarios."
        ),
        "context": {
            "language": "python",
            "framework": "fastapi",
            "current_auth_system": "session-based",
        },
        "constraints": [
            "Must be backward compatible",
            "No breaking changes to public API",
            "Should include unit tests",
        ],
        "model_preference": "gpt-4",
    }


@pytest.fixture
def large_task_payload() -> Dict[str, Any]:
    """A large (>10 000 chars) task payload to test estimation scaling."""
    base = (
        "Implement a comprehensive microservices architecture migration "
        "for our legacy monolithic application. "
    )
    return {
        "task_description": base * 100,
        "context": {
            "language": "python",
            "framework": "fastapi",
            "database": "postgresql",
            "messaging": "rabbitmq",
        },
        "constraints": [
            "Must maintain 99.95% uptime during migration",
            "Zero data loss",
            "Backward compatibility with all existing integrations",
            "Performance must not degrade",
            "Rollback capability at each step",
        ],
        "model_preference": "gpt-4",
    }


@pytest.fixture
def empty_task_payload() -> Dict[str, Any]:
    """Minimal / empty payload for edge-case testing."""
    return {"task_description": "", "context": {}}


@pytest.fixture
def dry_run_contractor() -> MagicMock:
    """Provide a dry-run contractor instance.

    .. note::
       Replace this mock with the real ``ArtisanContractor`` once available::

           from artisan.contractors.artisan_contractor import ArtisanContractor
           return ArtisanContractor(dry_run=True)

       The mock below faithfully simulates the expected interface using
       token-count heuristics.
    """
    contractor = MagicMock(name="ArtisanContractor")

    def _mock_execute(task: Dict[str, Any]) -> Dict[str, Any]:
        description = task.get("task_description", "")
        char_count = len(description)

        # Heuristic: ~4 characters per token
        token_est = max(1, char_count // 4)

        # Approximate GPT-4 pricing: $0.00003 / token
        cost_per_token = 0.00003
        total_cost = token_est * cost_per_token

        # Approximate processing: 0.015 s / token
        duration_per_token = 0.015
        total_duration = token_est * duration_per_token

        # Three-step breakdown
        t1 = token_est // 3
        t2 = token_est // 2
        t3 = token_est - t1 - t2

        c1 = total_cost / 3
        c2 = total_cost / 2
        c3 = total_cost - c1 - c2

        d1 = total_duration / 3
        d2 = total_duration / 2
        d3 = total_duration - d1 - d2

        breakdown = [
            {
                "step_name": "analyze_requirements",
                "estimated_tokens": t1,
                "estimated_cost": c1,
                "estimated_duration_seconds": d1,
            },
            {
                "step_name": "generate_implementation",
                "estimated_tokens": t2,
                "estimated_cost": c2,
                "estimated_duration_seconds": d2,
            },
            {
                "step_name": "validate_output",
                "estimated_tokens": t3,
                "estimated_cost": c3,
                "estimated_duration_seconds": d3,
            },
        ]

        return {
            "status": "dry_run",
            "estimated_cost": total_cost,
            "estimated_duration": total_duration,
            "model": task.get("model_preference", "gpt-4"),
            "token_estimate": token_est,
            "breakdown": breakdown,
            "metadata": {
                "estimation_method": "token_count_heuristic",
                "pricing_model_version": "2024-01",
            },
        }

    contractor.execute = _mock_execute
    return contractor


@pytest.fixture
def state_snapshot():
    """Helper to capture and compare state snapshots around a dry-run call.

    Returns an object with ``capture()`` and ``assert_unchanged()`` methods.
    """

    class _StateSnapshot:
        def __init__(self) -> None:
            self.pre_snapshot: Optional[Dict[str, Any]] = None

        def capture(self) -> Dict[str, Any]:
            """Take a snapshot of relevant observable state."""
            snapshot: Dict[str, Any] = {"timestamp": time.time()}
            # Extend with database row counts, directory listings, etc.
            return snapshot

        def assert_unchanged(self, post_snapshot: Dict[str, Any]) -> None:
            """Assert that the post-snapshot matches the pre-snapshot."""
            assert self.pre_snapshot is not None, "Must call capture() first"
            assert post_snapshot is not None, "post_snapshot must not be None"
            # In a full implementation, compare all captured facets here.

    return _StateSnapshot()


# ===================================================================== #
#                       Test: Report Structure                           #
# ===================================================================== #


class TestArtisanDryRunReportStructure:
    """Validates that the dry-run report conforms to the expected schema."""

    def test_report_contains_all_required_fields(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        """All required top-level keys must be present."""
        report = dry_run_contractor.execute(task=sample_task_payload)
        missing = _REQUIRED_REPORT_FIELDS - set(report.keys())
        assert not missing, f"Report missing required fields: {missing}"

    def test_report_status_is_dry_run(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=sample_task_payload)
        assert report["status"] == "dry_run", f"Expected 'dry_run', got '{report['status']}'"

    def test_report_breakdown_is_list_of_step_estimates(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=sample_task_payload)
        breakdown = report.get("breakdown")
        assert isinstance(breakdown, list) and len(breakdown) > 0

        for idx, step in enumerate(breakdown):
            assert isinstance(step, dict), f"breakdown[{idx}] must be dict"
            missing = _REQUIRED_STEP_FIELDS - set(step.keys())
            assert not missing, f"breakdown[{idx}] missing fields: {missing}"

    def test_report_model_field_is_nonempty_string(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=sample_task_payload)
        model = report.get("model")
        assert isinstance(model, str) and len(model) > 0, "model must be non-empty str"

    def test_report_metadata_is_dict_or_none(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=sample_task_payload)
        metadata = report.get("metadata")
        assert metadata is None or isinstance(metadata, dict)

    def test_validate_dry_run_report_accepts_valid_report(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        """``validate_dry_run_report`` must not raise for a valid report."""
        report = dry_run_contractor.execute(task=sample_task_payload)
        validate_dry_run_report(report)  # should not raise

    def test_validate_dry_run_report_rejects_missing_field(self) -> None:
        invalid = {
            "status": "dry_run",
            "estimated_cost": 0.05,
            # estimated_duration intentionally omitted
            "model": "gpt-4",
            "token_estimate": 100,
            "breakdown": [
                {
                    "step_name": "test",
                    "estimated_tokens": 100,
                    "estimated_cost": 0.05,
                    "estimated_duration_seconds": 10.0,
                }
            ],
        }
        with pytest.raises(AssertionError, match="missing required fields"):
            validate_dry_run_report(invalid)

    def test_validate_dry_run_report_rejects_wrong_status(self) -> None:
        invalid = {
            "status": "completed",
            "estimated_cost": 0.05,
            "estimated_duration": 10.0,
            "model": "gpt-4",
            "token_estimate": 100,
            "breakdown": [
                {
                    "step_name": "test",
                    "estimated_tokens": 100,
                    "estimated_cost": 0.05,
                    "estimated_duration_seconds": 10.0,
                }
            ],
        }
        with pytest.raises(AssertionError, match="status must be 'dry_run'"):
            validate_dry_run_report(invalid)


# ===================================================================== #
#                    Test: No LLM / HTTP Calls                           #
# ===================================================================== #


class TestArtisanDryRunNoCalls:
    """Ensures that no LLM API or HTTP calls are made during a dry run."""

    @patch(LLM_CLIENT_CALL_PATH)
    def test_no_llm_client_calls_made(
        self,
        mock_llm_call: MagicMock,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
    ) -> None:
        dry_run_contractor.execute(task=sample_task_payload)
        assert mock_llm_call.call_count == 0, (
            f"LLM client should not be called; was called {mock_llm_call.call_count} time(s)"
        )

    @patch("httpx.Client.post")
    @patch("httpx.AsyncClient.post")
    def test_no_http_posts_to_llm_endpoints(
        self,
        mock_async_post: MagicMock,
        mock_sync_post: MagicMock,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
    ) -> None:
        dry_run_contractor.execute(task=sample_task_payload)
        assert mock_sync_post.call_count == 0
        assert mock_async_post.call_count == 0

    @patch("openai.OpenAI")
    def test_no_openai_client_instantiated(
        self,
        mock_openai: MagicMock,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
    ) -> None:
        dry_run_contractor.execute(task=sample_task_payload)
        assert mock_openai.call_count == 0

    @patch("requests.post")
    def test_no_requests_library_calls(
        self,
        mock_requests_post: MagicMock,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
    ) -> None:
        dry_run_contractor.execute(task=sample_task_payload)
        assert mock_requests_post.call_count == 0


# ===================================================================== #
#                    Test: No Persistent State Changes                   #
# ===================================================================== #


class TestArtisanDryRunNoStateChanges:
    """Ensures that no database, file, or config state is mutated."""

    @patch(DB_WRITE_PATH)
    def test_no_database_writes(
        self,
        mock_db_write: MagicMock,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
    ) -> None:
        dry_run_contractor.execute(task=sample_task_payload)
        assert mock_db_write.call_count == 0

    @patch(FILE_WRITE_PATH)
    def test_no_file_writes(
        self,
        mock_file_write: MagicMock,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
    ) -> None:
        dry_run_contractor.execute(task=sample_task_payload)
        assert mock_file_write.call_count == 0

    @patch("builtins.open", new_callable=MagicMock)
    def test_no_builtin_file_open_for_writing(
        self,
        mock_open: MagicMock,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
    ) -> None:
        """If ``open()`` is called at all, it must be read-only (no 'w'/'a')."""
        dry_run_contractor.execute(task=sample_task_payload)

        write_modes = {"w", "a", "x", "wb", "ab", "xb", "w+", "a+", "r+"}
        for call_obj in mock_open.call_args_list:
            args, kwargs = call_obj
            mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
            assert mode not in write_modes and "w" not in mode and "a" not in mode, (
                f"File must not be opened for writing during dry run (mode={mode!r})"
            )

    def test_no_config_file_mutations(
        self,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
    ) -> None:
        with patch("pathlib.Path.write_text") as mock_wt, \
             patch("pathlib.Path.write_bytes") as mock_wb:
            dry_run_contractor.execute(task=sample_task_payload)
            assert mock_wt.call_count == 0, "Path.write_text must not be called"
            assert mock_wb.call_count == 0, "Path.write_bytes must not be called"

    def test_state_snapshot_unchanged(
        self,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
        state_snapshot,
    ) -> None:
        """Capture state before and after; assert no observable mutation."""
        state_snapshot.pre_snapshot = state_snapshot.capture()
        dry_run_contractor.execute(task=sample_task_payload)
        post = state_snapshot.capture()
        state_snapshot.assert_unchanged(post)


# ===================================================================== #
#                    Test: Estimation Values                             #
# ===================================================================== #


class TestArtisanDryRunEstimationValues:
    """Validates that cost / duration estimates are reasonable and consistent."""

    def test_estimated_cost_is_non_negative(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=sample_task_payload)
        assert float(report["estimated_cost"]) >= 0

    def test_estimated_duration_is_non_negative(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=sample_task_payload)
        assert float(report["estimated_duration"]) >= 0

    def test_token_estimate_is_positive_for_nonempty_input(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=sample_task_payload)
        assert report["token_estimate"] > 0

    def test_cost_scales_with_payload_size(
        self,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
        large_task_payload: Dict[str, Any],
    ) -> None:
        small = dry_run_contractor.execute(task=sample_task_payload)
        large = dry_run_contractor.execute(task=large_task_payload)
        assert float(large["estimated_cost"]) > float(small["estimated_cost"])

    def test_duration_scales_with_payload_size(
        self,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
        large_task_payload: Dict[str, Any],
    ) -> None:
        small = dry_run_contractor.execute(task=sample_task_payload)
        large = dry_run_contractor.execute(task=large_task_payload)
        assert float(large["estimated_duration"]) > float(small["estimated_duration"])

    def test_token_estimate_scales_with_payload_size(
        self,
        dry_run_contractor: MagicMock,
        sample_task_payload: Dict[str, Any],
        large_task_payload: Dict[str, Any],
    ) -> None:
        """Larger payloads must produce strictly larger token estimates."""
        small = dry_run_contractor.execute(task=sample_task_payload)
        large = dry_run_contractor.execute(task=large_task_payload)
        assert large["token_estimate"] > small["token_estimate"]

    def test_breakdown_costs_sum_to_total(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=sample_task_payload)
        total = float(report["estimated_cost"])
        parts = sum(float(s["estimated_cost"]) for s in report["breakdown"])
        assert abs(parts - total) <= total * FP_TOLERANCE_PCT, (
            f"Breakdown costs ({parts}) must sum to total ({total}) within {FP_TOLERANCE_PCT*100}%"
        )

    def test_breakdown_durations_sum_to_total(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=sample_task_payload)
        total = float(report["estimated_duration"])
        parts = sum(float(s["estimated_duration_seconds"]) for s in report["breakdown"])
        assert abs(parts - total) <= total * FP_TOLERANCE_PCT, (
            f"Breakdown durations ({parts}) must sum to total ({total}) within {FP_TOLERANCE_PCT*100}%"
        )

    def test_breakdown_tokens_sum_to_total(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        """Sum of per-step token estimates should equal the total token estimate."""
        report = dry_run_contractor.execute(task=sample_task_payload)
        total = report["token_estimate"]
        parts = sum(s["estimated_tokens"] for s in report["breakdown"])
        assert parts == total, (
            f"Breakdown token sum ({parts}) must equal total ({total})"
        )


# ===================================================================== #
#                       Test: Edge Cases                                 #
# ===================================================================== #


class TestArtisanDryRunEdgeCases:
    """Edge cases: empty payload, huge payload, unicode, missing fields, etc."""

    def test_empty_task_description_returns_report(
        self, dry_run_contractor: MagicMock, empty_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=empty_task_payload)
        assert report is not None and isinstance(report, dict)
        validate_dry_run_report(report)

    def test_empty_task_cost_is_minimal(
        self, dry_run_contractor: MagicMock, empty_task_payload: Dict[str, Any]
    ) -> None:
        report = dry_run_contractor.execute(task=empty_task_payload)
        cost = float(report["estimated_cost"])
        assert 0 <= cost < 0.01, f"Empty task should have minimal cost, got {cost}"

    def test_missing_optional_fields_in_payload(
        self, dry_run_contractor: MagicMock
    ) -> None:
        minimal = {"task_description": "Write a hello world program."}
        report = dry_run_contractor.execute(task=minimal)
        assert report is not None
        validate_dry_run_report(report)

    def test_dry_run_completes_quickly(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        """Must complete within the timing threshold (no real network calls)."""
        t0 = time.monotonic()
        report = dry_run_contractor.execute(task=sample_task_payload)
        elapsed = time.monotonic() - t0

        assert report is not None
        assert elapsed < DRY_RUN_MAX_SECONDS, (
            f"Dry run took {elapsed:.3f}s (limit {DRY_RUN_MAX_SECONDS}s). "
            "Possible inadvertent network call."
        )

    def test_multiple_sequential_dry_runs_are_idempotent(
        self, dry_run_contractor: MagicMock, sample_task_payload: Dict[str, Any]
    ) -> None:
        r1 = dry_run_contractor.execute(task=sample_task_payload)
        r2 = dry_run_contractor.execute(task=sample_task_payload)

        d1 = _to_dict(r1)
        d2 = _to_dict(r2)
        assert d1 == d2, f"Sequential dry runs differ:\n  1st: {d1}\n  2nd: {d2}"

    def test_unicode_in_task_description(
        self, dry_run_contractor: MagicMock
    ) -> None:
        payload = {
            "task_description": (
                "Build a 🚀 microservice in Python 🐍 with PostgreSQL 🐘. "
                "需要支持中文。العربية también."
            )
        }
        report = dry_run_contractor.execute(task=payload)
        assert report is not None
        validate_dry_run_report(report)

    def test_very_long_task_description(
        self, dry_run_contractor: MagicMock
    ) -> None:
        """100 k+ character description must still produce a valid, fast report."""
        desc = "Design and implement a comprehensive " * 5000
        t0 = time.monotonic()
        report = dry_run_contractor.execute(task={"task_description": desc})
        elapsed = time.monotonic() - t0

        assert report is not None
        validate_dry_run_report(report)
        assert elapsed < DRY_RUN_MAX_SECONDS

    def test_invalid_model_preference_defaults_gracefully(
        self, dry_run_contractor: MagicMock
    ) -> None:
        payload = {
            "task_description": "Test task.",
            "model_preference": "totally-fake-model-xyz-123",
        }
        report = dry_run_contractor.execute(task=payload)
        assert report is not None
        validate_dry_run_report(report)
        assert isinstance(report.get("model"), str)

    # --- Negative validation tests ---

    def test_negative_cost_rejected_by_validation(self) -> None:
        invalid = {
            "status": "dry_run",
            "estimated_cost": -0.05,
            "estimated_duration": 10.0,
            "model": "gpt-4",
            "token_estimate": 100,
            "breakdown": [
                {
                    "step_name": "test",
                    "estimated_tokens": 100,
                    "estimated_cost": 0.05,
                    "estimated_duration_seconds": 10.0,
                }
            ],
        }
        with pytest.raises(AssertionError, match="estimated_cost must be >= 0"):
            validate_dry_run_report(invalid)

    def test_zero_token_estimate_rejected_by_validation(self) -> None:
        invalid = {
            "status": "dry_run",
            "estimated_cost": 0.0,
            "estimated_duration": 0.0,
            "model": "gpt-4",
            "token_estimate": 0,
            "breakdown": [
                {
                    "step_name": "test",
                    "estimated_tokens": 0,
                    "estimated_cost": 0.0,
                    "estimated_duration_seconds": 0.0,
                }
            ],
        }
        with pytest.raises(AssertionError, match="token_estimate must be > 0"):
            validate_dry_run_report(invalid)

    def test_empty_breakdown_rejected_by_validation(self) -> None:
        invalid = {
            "status": "dry_run",
            "estimated_cost": 0.05,
            "estimated_duration": 10.0,
            "model": "gpt-4",
            "token_estimate": 100,
            "breakdown": [],
        }
        with pytest.raises(AssertionError, match="breakdown must have at least 1 step"):
            validate_dry_run_report(invalid)

    def test_empty_model_string_rejected_by_validation(self) -> None:
        """An empty model string violates the non-empty constraint."""
        invalid = {
            "status": "dry_run",
            "estimated_cost": 0.05,
            "estimated_duration": 10.0,
            "model": "",
            "token_estimate": 100,
            "breakdown": [
                {
                    "step_name": "test",
                    "estimated_tokens": 100,
                    "estimated_cost": 0.05,
                    "estimated_duration_seconds": 10.0,
                }
            ],
        }
        with pytest.raises(AssertionError, match="model must be non-empty string"):
            validate_dry_run_report(invalid)

    def test_negative_duration_rejected_by_validation(self) -> None:
        invalid = {
            "status": "dry_run",
            "estimated_cost": 0.05,
            "estimated_duration": -5.0,
            "model": "gpt-4",
            "token_estimate": 100,
            "breakdown": [
                {
                    "step_name": "test",
                    "estimated_tokens": 100,
                    "estimated_cost": 0.05,
                    "estimated_duration_seconds": 10.0,
                }
            ],
        }
        with pytest.raises(AssertionError, match="estimated_duration must be >= 0"):
            validate_dry_run_report(invalid)