"""
Tests for Gemini SAFETY filter handling (Fix 2, Fix 3, Rec 4, Rec 5).

Covers:
- GeminiSafetyFilterError raised on SAFETY finish_reason
- safety_settings passthrough in GeminiAgent
- Workflow SAFETY retry with reduced context
- Workflow skip-and-continue on repeated SAFETY blocks
- Diagnostic logging on SAFETY triggers
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest

from startd8.exceptions import GeminiSafetyFilterError, APIError
from startd8.models import TokenUsage


# ---------------------------------------------------------------------------
# Exception class tests
# ---------------------------------------------------------------------------

class TestGeminiSafetyFilterError:
    """Test GeminiSafetyFilterError exception class."""

    def test_is_subclass_of_api_error(self):
        err = GeminiSafetyFilterError("blocked")
        assert isinstance(err, APIError)

    def test_default_provider_is_gemini(self):
        err = GeminiSafetyFilterError("blocked")
        assert err.provider == "gemini"

    def test_stores_prompt_tokens(self):
        err = GeminiSafetyFilterError("blocked", prompt_tokens=500)
        assert err.prompt_tokens == 500

    def test_stores_safety_ratings(self):
        ratings = [{"category": "DANGEROUS_CONTENT", "blocked": True}]
        err = GeminiSafetyFilterError("blocked", safety_ratings=ratings)
        assert err.safety_ratings == ratings

    def test_safety_ratings_default_empty(self):
        err = GeminiSafetyFilterError("blocked")
        assert err.safety_ratings == []


# ---------------------------------------------------------------------------
# GeminiAgent SAFETY handling tests (mocked — no google-genai needed)
# ---------------------------------------------------------------------------

class TestGeminiAgentSafetyHandling:
    """Test that GeminiAgent raises GeminiSafetyFilterError on SAFETY finish_reason."""

    def _make_mock_response(self, text=None, finish_reason="STOP"):
        """Build a mock Gemini API response object."""
        candidate = MagicMock()
        candidate.finish_reason = MagicMock()
        candidate.finish_reason.name = finish_reason
        candidate.safety_ratings = []

        response = MagicMock()
        response.candidates = [candidate]
        response.text = text

        if text is None:
            # response.text raises on empty in real API; simulate with property
            type(response).text = property(lambda self: None)

        usage = MagicMock()
        usage.prompt_token_count = 100
        usage.candidates_token_count = 50
        usage.total_token_count = 150
        response.usage_metadata = usage

        return response

    @patch("startd8.agents.gemini._GEMINI_AVAILABLE", True)
    @patch("startd8.agents.gemini.genai")
    @patch("startd8.agents.gemini.genai_types")
    def test_safety_finish_reason_raises_safety_error(self, mock_types, mock_genai):
        """SAFETY finish_reason should raise GeminiSafetyFilterError, not RuntimeError."""
        from startd8.agents.gemini import GeminiAgent

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        safety_response = self._make_mock_response(text=None, finish_reason="SAFETY")
        mock_client.models.generate_content.return_value = safety_response

        agent = GeminiAgent.__new__(GeminiAgent)
        agent.name = "gemini-test"
        agent.model = "gemini-2.5-pro"
        agent.client = mock_client
        agent.model_name = "gemini-2.5-pro"
        agent.max_tokens = 8192
        agent.temperature = 0.7
        agent.retry_config = None
        agent.safety_settings = None
        agent.system_prompt = None
        agent.cost_tracker = None
        agent.budget_manager = None

        import asyncio
        with pytest.raises(GeminiSafetyFilterError) as exc_info:
            asyncio.run(agent.agenerate("test prompt"))

        assert "safety filter blocked" in str(exc_info.value).lower()
        assert exc_info.value.prompt_tokens is not None

    @patch("startd8.agents.gemini._GEMINI_AVAILABLE", True)
    @patch("startd8.agents.gemini.genai")
    @patch("startd8.agents.gemini.genai_types")
    def test_non_safety_empty_response_still_raises_runtime_error(self, mock_types, mock_genai):
        """Non-SAFETY empty responses should still raise RuntimeError."""
        from startd8.agents.gemini import GeminiAgent

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        recitation_response = self._make_mock_response(text=None, finish_reason="RECITATION")
        mock_client.models.generate_content.return_value = recitation_response

        agent = GeminiAgent.__new__(GeminiAgent)
        agent.name = "gemini-test"
        agent.model = "gemini-2.5-pro"
        agent.client = mock_client
        agent.model_name = "gemini-2.5-pro"
        agent.max_tokens = 8192
        agent.temperature = 0.7
        agent.retry_config = None
        agent.safety_settings = None
        agent.system_prompt = None
        agent.cost_tracker = None
        agent.budget_manager = None

        import asyncio
        with pytest.raises(RuntimeError, match="RECITATION"):
            asyncio.run(agent.agenerate("test prompt"))

    @patch("startd8.agents.gemini._GEMINI_AVAILABLE", True)
    @patch("startd8.agents.gemini.genai")
    @patch("startd8.agents.gemini.genai_types")
    def test_safety_error_includes_safety_ratings(self, mock_types, mock_genai):
        """GeminiSafetyFilterError should capture safety_ratings from the response."""
        from startd8.agents.gemini import GeminiAgent

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        # Build response with safety ratings
        rating = MagicMock()
        rating.category = "HARM_CATEGORY_DANGEROUS_CONTENT"
        rating.probability = "HIGH"
        rating.blocked = True

        candidate = MagicMock()
        candidate.finish_reason = MagicMock()
        candidate.finish_reason.name = "SAFETY"
        candidate.safety_ratings = [rating]

        response = MagicMock()
        response.candidates = [candidate]
        type(response).text = property(lambda self: None)
        response.usage_metadata = None

        mock_client.models.generate_content.return_value = response

        agent = GeminiAgent.__new__(GeminiAgent)
        agent.name = "gemini-test"
        agent.model = "gemini-2.5-pro"
        agent.client = mock_client
        agent.model_name = "gemini-2.5-pro"
        agent.max_tokens = 8192
        agent.temperature = 0.7
        agent.retry_config = None
        agent.safety_settings = None
        agent.system_prompt = None
        agent.cost_tracker = None
        agent.budget_manager = None

        import asyncio
        with pytest.raises(GeminiSafetyFilterError) as exc_info:
            asyncio.run(agent.agenerate("test"))

        assert len(exc_info.value.safety_ratings) == 1
        assert exc_info.value.safety_ratings[0]["category"] == "HARM_CATEGORY_DANGEROUS_CONTENT"


# ---------------------------------------------------------------------------
# safety_settings passthrough tests
# ---------------------------------------------------------------------------

class TestGeminiAgentSafetySettings:
    """Test safety_settings passthrough to GenerateContentConfig."""

    @patch("startd8.agents.gemini._GEMINI_AVAILABLE", True)
    @patch("startd8.agents.gemini.genai")
    @patch("startd8.agents.gemini.genai_types")
    def test_safety_settings_passed_to_config(self, mock_types, mock_genai):
        """safety_settings should be forwarded to GenerateContentConfig."""
        from startd8.agents.gemini import GeminiAgent

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        # Build a successful response
        candidate = MagicMock()
        candidate.finish_reason = MagicMock()
        candidate.finish_reason.name = "STOP"
        candidate.safety_ratings = []

        response = MagicMock()
        response.candidates = [candidate]
        response.text = "review output"
        usage = MagicMock()
        usage.prompt_token_count = 100
        usage.candidates_token_count = 50
        usage.total_token_count = 150
        response.usage_metadata = usage

        mock_client.models.generate_content.return_value = response

        settings = [
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        agent = GeminiAgent.__new__(GeminiAgent)
        agent.name = "gemini-test"
        agent.model = "gemini-2.5-pro"
        agent.client = mock_client
        agent.model_name = "gemini-2.5-pro"
        agent.max_tokens = 8192
        agent.temperature = 0.7
        agent.retry_config = None
        agent.safety_settings = settings
        agent.system_prompt = None
        agent.cost_tracker = None
        agent.budget_manager = None

        import asyncio
        asyncio.run(agent.agenerate("test prompt"))

        # Verify GenerateContentConfig was called with safety_settings
        config_call = mock_types.GenerateContentConfig.call_args
        assert config_call.kwargs.get("safety_settings") == settings

    @patch("startd8.agents.gemini._GEMINI_AVAILABLE", True)
    @patch("startd8.agents.gemini.genai")
    @patch("startd8.agents.gemini.genai_types")
    def test_no_safety_settings_when_none(self, mock_types, mock_genai):
        """When safety_settings is None, should not be in GenerateContentConfig kwargs."""
        from startd8.agents.gemini import GeminiAgent

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        candidate = MagicMock()
        candidate.finish_reason = MagicMock()
        candidate.finish_reason.name = "STOP"
        response = MagicMock()
        response.candidates = [candidate]
        response.text = "output"
        usage = MagicMock()
        usage.prompt_token_count = 10
        usage.candidates_token_count = 5
        usage.total_token_count = 15
        response.usage_metadata = usage
        mock_client.models.generate_content.return_value = response

        agent = GeminiAgent.__new__(GeminiAgent)
        agent.name = "gemini-test"
        agent.model = "gemini-2.5-pro"
        agent.client = mock_client
        agent.model_name = "gemini-2.5-pro"
        agent.max_tokens = 8192
        agent.temperature = 0.7
        agent.retry_config = None
        agent.safety_settings = None
        agent.system_prompt = None
        agent.cost_tracker = None
        agent.budget_manager = None

        import asyncio
        asyncio.run(agent.agenerate("test"))

        config_call = mock_types.GenerateContentConfig.call_args
        assert "safety_settings" not in config_call.kwargs


# ---------------------------------------------------------------------------
# Workflow SAFETY retry tests
# ---------------------------------------------------------------------------

class TestArchitecturalReviewSafetyRetry:
    """Test workflow-level SAFETY retry and skip logic."""

    def _make_valid_snippet(self, round_number):
        """Create a valid review snippet that passes _validate_snippet."""
        return f"""#### Review Round R{round_number}

- **Reviewer**: test-agent (test-model)
- **Date**: 2026-02-09 00:00:00 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{round_number}-S1 | Architecture | high | Test suggestion | Test rationale | Section 1 | Manual review |
"""

    def _make_mock_agent(self, name="gemini-test", model="gemini-2.5-pro", is_gemini=True):
        """Create a mock agent with correct module path for _is_gemini_agent."""
        agent = MagicMock()
        agent.name = name
        agent.model = model
        agent.safety_settings = None
        if is_gemini:
            agent.__class__.__module__ = "startd8.agents.gemini"
        else:
            agent.__class__.__module__ = "startd8.agents.claude"
        return agent

    def test_safety_retry_with_reduced_context_succeeds(self, tmp_path):
        """When first call hits SAFETY but reduced-context retry succeeds."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="gemini-2.5-pro")

        agent = self._make_mock_agent()
        # First call raises SAFETY, second succeeds
        agent.generate.side_effect = [
            GeminiSafetyFilterError("blocked", prompt_tokens=100),
            (snippet, 500, token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_triage": False},
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        assert result.output["rounds_appended"] == 1
        assert agent.generate.call_count == 2

    def test_safety_retry_exhausted_skips_reviewer(self, tmp_path):
        """When all SAFETY retries fail, skip reviewer and continue."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        agent = self._make_mock_agent()
        # All calls raise SAFETY
        agent.generate.side_effect = GeminiSafetyFilterError("blocked", prompt_tokens=100)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent],
            on_progress=None,
        )

        # Should not succeed (no rounds appended) but should not crash
        assert result.success is False
        assert result.output["rounds_appended"] == 0
        # Step should record the skip
        assert len(result.steps) == 1
        assert "skipped" in result.steps[0].error.lower()

    def test_safety_skip_continues_to_next_reviewer(self, tmp_path):
        """After skipping a SAFETY-blocked reviewer, the next reviewer should still run."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet_r2 = self._make_valid_snippet(2)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="claude-opus")

        gemini_agent = self._make_mock_agent(name="gemini", model="gemini-2.5-pro", is_gemini=True)
        gemini_agent.generate.side_effect = GeminiSafetyFilterError("blocked")

        claude_agent = self._make_mock_agent(name="claude", model="claude-opus", is_gemini=False)
        claude_agent.generate.return_value = (snippet_r2, 800, token_usage)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[gemini_agent, claude_agent],
            on_progress=None,
        )

        # Gemini skipped, Claude succeeded → partial success
        assert result.output["rounds_appended"] == 1
        # The second step (Claude) should have succeeded
        assert any(s.error is None for s in result.steps)

    def test_reduced_prompt_has_no_context_content(self, tmp_path):
        """The retry prompt should drop context_content."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        context_dir = tmp_path / "context"
        context_dir.mkdir()
        (context_dir / "lessons.md").write_text("# Lessons\n\nImportant lesson here.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="gemini-2.5-pro")

        agent = self._make_mock_agent()
        # First call (with context) hits SAFETY, second (without context) succeeds
        agent.generate.side_effect = [
            GeminiSafetyFilterError("blocked", prompt_tokens=500),
            (snippet, 500, token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "context_files": [str(context_dir)],
            },
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        # Verify the second (retry) prompt does NOT contain the context content
        retry_prompt = agent.generate.call_args_list[1][0][0]
        assert "Important lesson here" not in retry_prompt

    def test_relaxed_safety_settings_applied_on_second_retry(self, tmp_path):
        """On second SAFETY retry, relaxed settings are applied during the call then restored."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
            RELAXED_SAFETY_SETTINGS,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="gemini-2.5-pro")

        # Track what safety_settings were active when generate() was called
        settings_during_calls = []

        agent = self._make_mock_agent()
        original_side_effects = [
            GeminiSafetyFilterError("blocked"),
            GeminiSafetyFilterError("blocked again"),
            (snippet, 500, token_usage),
        ]
        call_idx = 0

        def _capture_and_dispatch(prompt):
            nonlocal call_idx
            settings_during_calls.append(agent.safety_settings)
            effect = original_side_effects[call_idx]
            call_idx += 1
            if isinstance(effect, Exception):
                raise effect
            return effect

        agent.generate = _capture_and_dispatch

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        # Third call (the successful one) should have had RELAXED settings active
        assert settings_during_calls[2] == RELAXED_SAFETY_SETTINGS
        # After completion, original settings should be restored
        assert agent.safety_settings is None

    def test_gemini_safety_settings_from_config(self, tmp_path):
        """gemini_safety_settings config should be applied to Gemini agents before execution."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="gemini-2.5-pro")

        custom_settings = [
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        agent = self._make_mock_agent()
        agent.generate.return_value = (snippet, 500, token_usage)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "gemini_safety_settings": custom_settings,
            },
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        # Config-provided settings should have been applied before generation
        # (They may be overridden by retry logic, but should be set initially)


# ---------------------------------------------------------------------------
# Diagnostic logging tests
# ---------------------------------------------------------------------------

class TestSafetyDiagnosticLogging:
    """Test that SAFETY triggers produce diagnostic log output."""

    @patch("startd8.agents.gemini._GEMINI_AVAILABLE", True)
    @patch("startd8.agents.gemini.genai")
    @patch("startd8.agents.gemini.genai_types")
    def test_safety_triggers_warning_log(self, mock_types, mock_genai, caplog):
        """SAFETY filter should produce a WARNING log with diagnostics."""
        from startd8.agents.gemini import GeminiAgent

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        candidate = MagicMock()
        candidate.finish_reason = MagicMock()
        candidate.finish_reason.name = "SAFETY"
        candidate.safety_ratings = []

        response = MagicMock()
        response.candidates = [candidate]
        type(response).text = property(lambda self: None)
        response.usage_metadata = None

        mock_client.models.generate_content.return_value = response

        agent = GeminiAgent.__new__(GeminiAgent)
        agent.name = "gemini-test"
        agent.model = "gemini-2.5-pro"
        agent.client = mock_client
        agent.model_name = "gemini-2.5-pro"
        agent.max_tokens = 8192
        agent.temperature = 0.7
        agent.retry_config = None
        agent.safety_settings = None
        agent.system_prompt = None
        agent.cost_tracker = None
        agent.budget_manager = None

        import asyncio
        with caplog.at_level(logging.WARNING, logger="startd8.agents.gemini"):
            with pytest.raises(GeminiSafetyFilterError):
                asyncio.run(agent.agenerate("test prompt"))

        assert any("SAFETY filter triggered" in r.message for r in caplog.records)

    @patch("startd8.agents.gemini._GEMINI_AVAILABLE", True)
    @patch("startd8.agents.gemini.genai")
    @patch("startd8.agents.gemini.genai_types")
    def test_safety_triggers_debug_log_with_prompt_sample(self, mock_types, mock_genai, caplog):
        """SAFETY filter should produce a DEBUG log with prompt sample."""
        from startd8.agents.gemini import GeminiAgent

        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        candidate = MagicMock()
        candidate.finish_reason = MagicMock()
        candidate.finish_reason.name = "SAFETY"
        candidate.safety_ratings = []

        response = MagicMock()
        response.candidates = [candidate]
        type(response).text = property(lambda self: None)
        response.usage_metadata = None

        mock_client.models.generate_content.return_value = response

        agent = GeminiAgent.__new__(GeminiAgent)
        agent.name = "gemini-test"
        agent.model = "gemini-2.5-pro"
        agent.client = mock_client
        agent.model_name = "gemini-2.5-pro"
        agent.max_tokens = 8192
        agent.temperature = 0.7
        agent.retry_config = None
        agent.safety_settings = None
        agent.system_prompt = None
        agent.cost_tracker = None
        agent.budget_manager = None

        import asyncio
        with caplog.at_level(logging.DEBUG, logger="startd8.agents.gemini"):
            with pytest.raises(GeminiSafetyFilterError):
                asyncio.run(
                    agent.agenerate("this is a unique test prompt for debugging")
                )

        debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("SAFETY-blocked prompt sample" in m for m in debug_msgs)


# ---------------------------------------------------------------------------
# Code-fence stripping tests
# ---------------------------------------------------------------------------

class TestStripCodeFences:
    """Test _strip_code_fences helper."""

    def test_strip_markdown_fence(self):
        from startd8.workflows.builtin.architectural_review_log_workflow import _strip_code_fences
        text = "```markdown\n#### Review Round R1\nContent here\n```"
        result = _strip_code_fences(text)
        assert result == "#### Review Round R1\nContent here"

    def test_strip_md_fence(self):
        from startd8.workflows.builtin.architectural_review_log_workflow import _strip_code_fences
        text = "```md\n#### Review Round R1\n```"
        result = _strip_code_fences(text)
        assert result == "#### Review Round R1"

    def test_strip_bare_fence(self):
        from startd8.workflows.builtin.architectural_review_log_workflow import _strip_code_fences
        text = "```\n#### Review Round R1\nContent\n```"
        result = _strip_code_fences(text)
        assert result == "#### Review Round R1\nContent"

    def test_no_fence_passthrough(self):
        from startd8.workflows.builtin.architectural_review_log_workflow import _strip_code_fences
        text = "#### Review Round R1\nContent"
        result = _strip_code_fences(text)
        assert result == text

    def test_case_insensitive_fence(self):
        from startd8.workflows.builtin.architectural_review_log_workflow import _strip_code_fences
        text = "```Markdown\n#### Review Round R1\n```"
        result = _strip_code_fences(text)
        assert result == "#### Review Round R1"


# ---------------------------------------------------------------------------
# Validation failure handling tests
# ---------------------------------------------------------------------------

class TestValidationFailureHandling:
    """Test validation failure retry, continue-not-break, and logging."""

    def _make_valid_snippet(self, round_number):
        return f"""#### Review Round R{round_number}

- **Reviewer**: test-agent (test-model)
- **Date**: 2026-02-09 00:00:00 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{round_number}-S1 | Architecture | high | Test suggestion | Test rationale | Section 1 | Manual review |
"""

    def _make_invalid_snippet(self, round_number):
        """Snippet missing a core column (Rationale) to trigger validation failure."""
        return f"""#### Review Round R{round_number}

- **Reviewer**: test-agent (test-model)
- **Date**: 2026-02-09 00:00:00 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion |
| ---- | ---- | ---- | ---- |
| R{round_number}-S1 | Architecture | high | Test |
"""

    def _make_mock_agent(self, name="gemini-test", model="gemini-2.5-pro", is_gemini=True):
        agent = MagicMock()
        agent.name = name
        agent.model = model
        agent.safety_settings = None
        if is_gemini:
            agent.__class__.__module__ = "startd8.agents.gemini"
        else:
            agent.__class__.__module__ = "startd8.agents.claude"
        return agent

    def test_validation_failure_retries_once(self, tmp_path):
        """Validation failure should trigger one retry with targeted re-prompt."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        invalid_snippet = self._make_invalid_snippet(1)
        valid_snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="gemini-2.5-pro")

        agent = self._make_mock_agent()
        # First call returns invalid, retry returns valid
        agent.generate.side_effect = [
            (invalid_snippet, 500, token_usage),
            (valid_snippet, 300, token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_triage": False},
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        assert result.output["rounds_appended"] == 1
        assert agent.generate.call_count == 2
        # Retry prompt should contain validation error
        retry_prompt = agent.generate.call_args_list[1][0][0]
        assert "failed validation" in retry_prompt
        assert "Table header mismatch" in retry_prompt

    def test_validation_failure_after_retry_continues(self, tmp_path):
        """If retry also fails validation, skip reviewer (continue, not break)."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        invalid_snippet = self._make_invalid_snippet(1)
        valid_snippet_r2 = self._make_valid_snippet(2)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        gemini_agent = self._make_mock_agent(name="gemini", model="gemini-2.5-pro", is_gemini=True)
        # Both calls return invalid
        gemini_agent.generate.side_effect = [
            (invalid_snippet, 500, token_usage),
            (invalid_snippet, 300, token_usage),
        ]

        claude_agent = self._make_mock_agent(name="claude", model="claude-opus", is_gemini=False)
        claude_agent.generate.return_value = (valid_snippet_r2, 800, token_usage)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[gemini_agent, claude_agent],
            on_progress=None,
        )

        # Gemini skipped (validation failed twice), Claude succeeded
        assert result.output["rounds_appended"] == 1
        assert any(s.error is None for s in result.steps)  # Claude step succeeded
        assert any("Invalid snippet after retry" in (s.error or "") for s in result.steps)

    def test_validation_failure_logs_warning(self, tmp_path, caplog):
        """Validation failure should produce a WARNING log."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        invalid_snippet = self._make_invalid_snippet(1)
        valid_snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="gemini-2.5-pro")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (invalid_snippet, 500, token_usage),
            (valid_snippet, 300, token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        with caplog.at_level(logging.WARNING, logger="startd8.workflows.builtin.architectural_review_log_workflow"):
            result = workflow._execute(
                config={"document_path": str(doc_path)},
                agents=[agent],
                on_progress=None,
            )

        assert result.success is True
        assert any("Validation failed for R1" in r.message for r in caplog.records)

    def test_code_fence_stripped_before_validation(self, tmp_path):
        """Response wrapped in code fences should still pass validation."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        valid_snippet = self._make_valid_snippet(1)
        fenced_snippet = f"```markdown\n{valid_snippet}```"
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="gemini-2.5-pro")

        agent = self._make_mock_agent()
        agent.generate.return_value = (fenced_snippet, 500, token_usage)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_triage": False},
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        assert result.output["rounds_appended"] == 1
        # Should only need one call (fence stripped, no retry needed)
        assert agent.generate.call_count == 1

    def test_retry_prompt_includes_format_requirements(self, tmp_path):
        """Retry prompt should include column names and enum values."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
            REQUIRED_COLUMNS,
            ALLOWED_AREAS,
            ALLOWED_SEVERITIES,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        invalid_snippet = self._make_invalid_snippet(1)
        valid_snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="gemini-2.5-pro")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (invalid_snippet, 500, token_usage),
            (valid_snippet, 300, token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent],
            on_progress=None,
        )

        retry_prompt = agent.generate.call_args_list[1][0][0]
        # Should include column names
        for col in REQUIRED_COLUMNS:
            assert col in retry_prompt
        # Should include allowed areas and severities
        for area in ALLOWED_AREAS:
            assert area in retry_prompt
        for sev in ALLOWED_SEVERITIES:
            assert sev in retry_prompt

    def test_retry_api_error_continues(self, tmp_path):
        """If the retry API call itself fails, skip reviewer and continue."""
        from startd8.workflows.builtin.architectural_review_log_workflow import (
            ArchitecturalReviewLogWorkflow,
        )

        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        invalid_snippet = self._make_invalid_snippet(1)
        valid_snippet_r2 = self._make_valid_snippet(2)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        gemini_agent = self._make_mock_agent(name="gemini", model="gemini-2.5-pro", is_gemini=True)
        gemini_agent.generate.side_effect = [
            (invalid_snippet, 500, token_usage),
            RuntimeError("API error on retry"),
        ]

        claude_agent = self._make_mock_agent(name="claude", model="claude-opus", is_gemini=False)
        claude_agent.generate.return_value = (valid_snippet_r2, 800, token_usage)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[gemini_agent, claude_agent],
            on_progress=None,
        )

        # Gemini skipped (retry errored), Claude succeeded
        assert result.output["rounds_appended"] == 1
        assert any("Validation retry failed" in (s.error or "") for s in result.steps)
