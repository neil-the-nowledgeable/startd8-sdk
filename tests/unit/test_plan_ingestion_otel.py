"""
Tests for OTel instrumentation in PlanIngestionWorkflow.

Verifies span hierarchy, no-op safety, decision events, and attribute setting.
All tests mock BaseAgent.generate() — no real LLM calls.
"""

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PLAN = textwrap.dedent("""\
    # Sample Plan

    ## Goals
    - Build a widget

    ## Features
    ### F-001: Widget core
    Implement the core widget in `src/widget.py`.
""")

PARSE_JSON = json.dumps({
    "title": "Sample Plan",
    "goals": ["Build a widget"],
    "features": [
        {
            "feature_id": "F-001",
            "name": "Widget core",
            "description": "Implement the core widget",
            "target_files": ["src/widget.py"],
            "dependencies": [],
            "estimated_loc": 100,
        },
    ],
    "mentioned_files": ["src/widget.py"],
    "dependency_graph": {},
})

ASSESS_JSON = json.dumps({
    "feature_count": 20,
    "cross_file_deps": 15,
    "api_surface": 10,
    "test_complexity": 25,
    "integration_depth": 20,
    "domain_novelty": 10,
    "ambiguity": 15,
    "composite": 30,
    "reasoning": "Simple plan.",
    "route": "prime",
})

TRANSFORM_MARKDOWN = textwrap.dedent("""\
    # Sample Plan

    ## Overview
    Build a widget.

    ## Architecture
    Simple architecture.
""")


def _make_mock_agent(name="test-agent"):
    agent = MagicMock()
    agent.name = name
    agent.model = "mock-model"
    agent.max_tokens = 4096
    return agent


def _mock_generate_return(response_text, in_tok=100, out_tok=50, cost=0.01):
    token_usage = MagicMock()
    token_usage.input_tokens = in_tok
    token_usage.input = in_tok
    token_usage.output_tokens = out_tok
    token_usage.output = out_tok
    token_usage.cost = cost
    return (response_text, 150, token_usage)


class MockStatusCode:
    """Mock for opentelemetry.trace.StatusCode."""
    OK = "OK"
    ERROR = "ERROR"
    UNSET = "UNSET"


class MockSpan:
    """Test span that records calls for assertion."""

    def __init__(self, name="test-span"):
        self.name = name
        self.attributes = {}
        self.events = []
        self.status = None
        self.status_description = None
        self.exceptions = []
        self._children = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def add_event(self, name, attributes=None):
        self.events.append({"name": name, "attributes": attributes or {}})

    def set_status(self, status, description=None):
        self.status = status
        self.status_description = description

    def record_exception(self, exc):
        self.exceptions.append(exc)

    def is_recording(self):
        return True

    def get_span_context(self):
        return MagicMock()


class MockSpanContext:
    """Context manager wrapper that tracks span lifecycle."""

    def __init__(self, span):
        self._span = span
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self._span

    def __exit__(self, *args):
        self.exited = True


class MockTracer:
    """Test tracer that records all spans created."""

    def __init__(self):
        self.spans = []
        self._span_map = {}

    def start_as_current_span(self, name, **kwargs):
        span = MockSpan(name)
        span.attributes.update(kwargs.get("attributes", {}))
        self.spans.append(span)
        self._span_map[name] = span
        return MockSpanContext(span)

    def get_span(self, name):
        return self._span_map.get(name)

    def span_names(self):
        return [s.name for s in self.spans]


from contextlib import contextmanager

@contextmanager
def _patch_otel(mock_tracer):
    """Patch plan_ingestion_workflow module with mock OTel tracer + StatusCode."""
    from startd8.workflows.builtin import plan_ingestion_workflow as piw

    orig_tracer = piw._tracer
    orig_has_otel = piw._HAS_OTEL
    orig_status_code = piw._StatusCode
    piw._tracer = mock_tracer
    piw._HAS_OTEL = True
    piw._StatusCode = MockStatusCode
    try:
        yield piw
    finally:
        piw._tracer = orig_tracer
        piw._HAS_OTEL = orig_has_otel
        piw._StatusCode = orig_status_code


# ---------------------------------------------------------------------------
# No-op safety tests
# ---------------------------------------------------------------------------

class TestNoOpSafety:
    """Verify pipeline runs when OTel is not available."""

    def test_tracer_fallback_is_noop(self):
        """When OTel unavailable, _tracer is _NoOpTracer."""
        from startd8.contractors.artisan_contractor import _NoOpTracer

        # Even if OTel IS installed in test env, _NoOpTracer should work
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test")
        with span as s:
            s.set_attribute("key", "value")
            s.add_event("event", {"k": "v"})
            s.set_status("OK")
            s.record_exception(ValueError("test"))
            assert not s.is_recording()

    def test_execute_no_otel_no_crash(self, tmp_path):
        """Full pipeline runs when _HAS_OTEL = False (mock agents)."""
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            PlanIngestionWorkflow,
        )

        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        wf = PlanIngestionWorkflow()
        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON),
            _mock_generate_return(ASSESS_JSON),
            _mock_generate_return(TRANSFORM_MARKDOWN),
        ]

        with (
            patch.object(wf, "_resolve_assessor_agent", return_value=agent),
            patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            patch(
                "startd8.workflows.builtin.plan_ingestion_workflow._HAS_OTEL",
                False,
            ),
        ):
            result = wf.run({
                "plan_path": str(plan_file),
                "output_dir": str(tmp_path / "output"),
                "skip_arc_review": True,
            })

        assert result.success, f"Workflow failed: {result.error}"


# ---------------------------------------------------------------------------
# Span hierarchy tests
# ---------------------------------------------------------------------------

class TestSpanHierarchy:
    """Verify span creation and hierarchy using mock tracer."""

    def test_root_span_created(self, tmp_path):
        """workflow.plan-ingestion span exists with workflow.id attribute."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                _mock_generate_return(PARSE_JSON),
                _mock_generate_return(ASSESS_JSON),
                _mock_generate_return(TRANSFORM_MARKDOWN),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                })

        assert result.success, f"Workflow failed: {result.error}"
        assert "workflow.plan-ingestion" in mock_tracer.span_names()
        root = mock_tracer.get_span("workflow.plan-ingestion")
        assert "workflow.id" in root.attributes

    def test_phase_spans_created(self, tmp_path):
        """All 6 ingestion.* phase spans are created."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                _mock_generate_return(PARSE_JSON),
                _mock_generate_return(ASSESS_JSON),
                _mock_generate_return(TRANSFORM_MARKDOWN),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                })

        assert result.success, f"Workflow failed: {result.error}"
        span_names = mock_tracer.span_names()
        for phase in ["preflight", "parse", "assess", "transform", "refine", "emit"]:
            assert f"ingestion.{phase}" in span_names, (
                f"Missing phase span: ingestion.{phase}"
            )

    def test_llm_spans_created(self, tmp_path):
        """llm.plan_ingestion.* spans exist for parse/assess/transform."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                _mock_generate_return(PARSE_JSON),
                _mock_generate_return(ASSESS_JSON),
                _mock_generate_return(TRANSFORM_MARKDOWN),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                })

        assert result.success, f"Workflow failed: {result.error}"
        span_names = mock_tracer.span_names()
        for phase in ["parse", "assess", "transform"]:
            assert f"llm.plan_ingestion.{phase}" in span_names, (
                f"Missing LLM span: llm.plan_ingestion.{phase}"
            )

    def test_io_spans_created(self, tmp_path):
        """io.* spans exist during emit phase."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                _mock_generate_return(PARSE_JSON),
                _mock_generate_return(ASSESS_JSON),
                _mock_generate_return(TRANSFORM_MARKDOWN),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                })

        assert result.success, f"Workflow failed: {result.error}"
        span_names = mock_tracer.span_names()
        io_spans = [n for n in span_names if n.startswith("io.")]
        assert len(io_spans) >= 2, (
            f"Expected at least 2 I/O spans, got {len(io_spans)}: {io_spans}"
        )


# ---------------------------------------------------------------------------
# Decision event tests
# ---------------------------------------------------------------------------

class TestDecisionEvents:
    """Verify decision events are recorded on phase spans."""

    def test_heuristic_fallback_event(self, tmp_path):
        """When parse fails and heuristic succeeds, event recorded on parse span."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                Exception("LLM parse failed"),
                _mock_generate_return(ASSESS_JSON),
                _mock_generate_return(TRANSFORM_MARKDOWN),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                    "enable_heuristic_parse_fallback": True,
                })

        assert result.success, f"Workflow failed: {result.error}"

        parse_span = mock_tracer.get_span("ingestion.parse")
        assert parse_span is not None
        fallback_events = [
            e for e in parse_span.events
            if e["name"] == "decision.heuristic_fallback"
        ]
        assert len(fallback_events) >= 1, (
            f"Expected heuristic_fallback event, got events: {parse_span.events}"
        )
        assert fallback_events[0]["attributes"]["phase"] == "parse"

    def test_quality_gate_fail_event(self, tmp_path):
        """When low_quality_policy=fail, event recorded before returning error."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        parse_json_no_files = json.dumps({
            "title": "Sample Plan",
            "goals": ["Build a widget"],
            "features": [
                {
                    "feature_id": "F-001",
                    "name": "Widget core",
                    "description": "Implement the core widget",
                    "target_files": [],
                    "dependencies": [],
                    "estimated_loc": 100,
                },
            ],
            "mentioned_files": [],
            "dependency_graph": {},
        })

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                _mock_generate_return(parse_json_no_files),
                _mock_generate_return(ASSESS_JSON),
                _mock_generate_return(TRANSFORM_MARKDOWN),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                    "low_quality_policy": "fail",
                    "min_requirements_coverage": 101,
                    "min_artifact_mapping_coverage": 101,
                })

        assert not result.success

        assess_span = mock_tracer.get_span("ingestion.assess")
        if assess_span is not None:
            gate_events = [
                e for e in assess_span.events
                if e["name"] == "decision.quality_gate_failed"
            ]
            assert len(gate_events) >= 1, (
                f"Expected quality_gate_failed event, got: {assess_span.events}"
            )


# ---------------------------------------------------------------------------
# Attribute tests
# ---------------------------------------------------------------------------

class TestSpanAttributes:
    """Verify span attributes are set correctly."""

    def test_root_span_attributes_on_success(self, tmp_path):
        """workflow.route and workflow.total_cost set on root span."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                _mock_generate_return(PARSE_JSON),
                _mock_generate_return(ASSESS_JSON),
                _mock_generate_return(TRANSFORM_MARKDOWN),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                })

        assert result.success, f"Workflow failed: {result.error}"
        root = mock_tracer.get_span("workflow.plan-ingestion")
        assert root is not None
        assert "workflow.route" in root.attributes
        assert "workflow.total_cost" in root.attributes
        assert root.attributes["workflow.route"] in ("prime", "artisan")

    def test_root_span_error_on_failure(self, tmp_path):
        """Exception recorded, status set to ERROR on root span."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()

            with (
                patch.object(
                    wf,
                    "_preflight_export_contract",
                    side_effect=RuntimeError("boom"),
                ),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                })

        assert not result.success
        root = mock_tracer.get_span("workflow.plan-ingestion")
        assert root is not None
        assert len(root.exceptions) > 0
        assert root.status == "ERROR"

    def test_llm_span_attributes(self, tmp_path):
        """llm.response_time_ms, llm.tokens_input, llm.cost_usd set."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                _mock_generate_return(PARSE_JSON, in_tok=200, out_tok=100, cost=0.05),
                _mock_generate_return(ASSESS_JSON),
                _mock_generate_return(TRANSFORM_MARKDOWN),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                })

        assert result.success, f"Workflow failed: {result.error}"
        parse_llm = mock_tracer.get_span("llm.plan_ingestion.parse")
        assert parse_llm is not None
        assert parse_llm.attributes.get("llm.response_time_ms") == 150
        assert parse_llm.attributes.get("llm.tokens_input") == 200
        assert parse_llm.attributes.get("llm.tokens_output") == 100
        assert parse_llm.attributes.get("llm.cost_usd") == 0.05

    def test_phase_span_cost_attribute(self, tmp_path):
        """phase.cost attribute is set on parse span."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                _mock_generate_return(PARSE_JSON, cost=0.03),
                _mock_generate_return(ASSESS_JSON, cost=0.02),
                _mock_generate_return(TRANSFORM_MARKDOWN, cost=0.01),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                })

        assert result.success, f"Workflow failed: {result.error}"
        parse_span = mock_tracer.get_span("ingestion.parse")
        assert parse_span is not None
        assert "phase.cost" in parse_span.attributes
        assert parse_span.attributes["phase.cost"] == 0.03

    def test_state_transition_events(self, tmp_path):
        """state.transition events recorded on root span."""
        mock_tracer = MockTracer()
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        with _patch_otel(mock_tracer) as piw:
            wf = piw.PlanIngestionWorkflow()
            agent = _make_mock_agent()
            agent.generate.side_effect = [
                _mock_generate_return(PARSE_JSON),
                _mock_generate_return(ASSESS_JSON),
                _mock_generate_return(TRANSFORM_MARKDOWN),
            ]

            with (
                patch.object(wf, "_resolve_assessor_agent", return_value=agent),
                patch.object(wf, "_resolve_transformer_agent", return_value=agent),
            ):
                result = wf.run({
                    "plan_path": str(plan_file),
                    "output_dir": str(tmp_path / "output"),
                    "skip_arc_review": True,
                })

        assert result.success, f"Workflow failed: {result.error}"
        root = mock_tracer.get_span("workflow.plan-ingestion")
        assert root is not None
        transition_events = [
            e for e in root.events if e["name"] == "state.transition"
        ]
        phases_seen = {e["attributes"]["phase"] for e in transition_events}
        for phase in ["preflight", "parse", "assess", "transform", "refine", "emit"]:
            assert phase in phases_seen, (
                f"Missing state.transition for {phase}. Seen: {phases_seen}"
            )


# ---------------------------------------------------------------------------
# OTel conventions tests
# ---------------------------------------------------------------------------

class TestOTelConventions:
    """Verify plan-ingestion constants in otel_conventions.py."""

    def test_span_names_importable(self):
        from startd8.otel_conventions import SpanNames

        assert SpanNames.PI_WORKFLOW == "workflow.plan-ingestion"
        assert SpanNames.PI_PHASE_PREFIX == "ingestion."
        assert SpanNames.PI_LLM_PREFIX == "llm.plan_ingestion."
        assert SpanNames.PI_IO_PREFIX == "io."

    def test_attribute_keys_importable(self):
        from startd8.otel_conventions import AttributeKeys

        assert AttributeKeys.PI_HEURISTIC_FALLBACK == "phase.heuristic_fallback"
        assert AttributeKeys.PI_FEATURES_COUNT == "phase.features_count"
        assert AttributeKeys.PI_ROUTE == "phase.route"
        assert AttributeKeys.PI_COMPOSITE_SCORE == "phase.composite_score"
        assert AttributeKeys.PI_ROUNDS_COMPLETED == "phase.rounds_completed"

    def test_event_names_importable(self):
        from startd8.otel_conventions import EventNames

        assert EventNames.PI_HEURISTIC_FALLBACK == "decision.heuristic_fallback"
        assert EventNames.PI_ROUTE_OVERRIDE == "decision.route_override"
        assert EventNames.PI_QUALITY_GATE_FAILED == "decision.quality_gate_failed"
        assert EventNames.PI_STATE_TRANSITION == "state.transition"
