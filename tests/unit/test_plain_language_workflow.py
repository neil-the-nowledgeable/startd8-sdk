"""
Unit tests for PlainLanguageWorkflow.

Tests the plain language simplification workflow that transforms
complex content into clear, jargon-free explanations.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
import json

from startd8.workflows.builtin.plain_language_workflow import (
    PlainLanguageWorkflow,
    SIMPLIFY_PROMPT_TEMPLATE,
    SYNTHESIS_PROMPT_TEMPLATE,
)
from startd8.workflows.builtin.plain_language_models import (
    AgentSimplification,
    ContentType,
    JargonTerm,
    KeyPoint,
    PlainLanguageOutput,
    PlainLanguageResult,
    ReadingLevel,
    SimplificationInput,
    SimplificationMode,
    get_reading_level_description,
    parse_content_type,
    parse_reading_level,
)
from startd8.workflows.models import ValidationResult


# ============================================================================
# Model Tests
# ============================================================================


class TestReadingLevel:
    """Tests for ReadingLevel enum."""

    def test_all_levels_defined(self):
        """Test all reading levels are defined."""
        levels = list(ReadingLevel)
        assert len(levels) == 4

        values = [l.value for l in levels]
        assert "elementary" in values
        assert "middle_school" in values
        assert "high_school" in values
        assert "general_public" in values


class TestContentType:
    """Tests for ContentType enum."""

    def test_all_types_defined(self):
        """Test all content types are defined."""
        types = list(ContentType)
        values = [t.value for t in types]

        assert "policy_analysis" in values
        assert "legal_document" in values
        assert "technical_report" in values
        assert "scientific_paper" in values
        assert "general" in values


class TestParseContentType:
    """Tests for parse_content_type function."""

    def test_policy_variants(self):
        """Test parsing policy type variants."""
        assert parse_content_type("policy_analysis") == ContentType.POLICY_ANALYSIS
        assert parse_content_type("policy") == ContentType.POLICY_ANALYSIS
        assert parse_content_type("POLICY") == ContentType.POLICY_ANALYSIS

    def test_legal_variants(self):
        """Test parsing legal type variants."""
        assert parse_content_type("legal_document") == ContentType.LEGAL_DOCUMENT
        assert parse_content_type("legal") == ContentType.LEGAL_DOCUMENT

    def test_unknown_type(self):
        """Test unknown types return GENERAL."""
        assert parse_content_type("unknown") == ContentType.GENERAL
        assert parse_content_type("") == ContentType.GENERAL
        assert parse_content_type(None) == ContentType.GENERAL


class TestParseReadingLevel:
    """Tests for parse_reading_level function."""

    def test_elementary_variants(self):
        """Test parsing elementary level variants."""
        assert parse_reading_level("elementary") == ReadingLevel.ELEMENTARY
        assert parse_reading_level("5th_grade") == ReadingLevel.ELEMENTARY
        assert parse_reading_level("fifth_grade") == ReadingLevel.ELEMENTARY

    def test_middle_school_variants(self):
        """Test parsing middle school level variants."""
        assert parse_reading_level("middle_school") == ReadingLevel.MIDDLE_SCHOOL
        assert parse_reading_level("8th_grade") == ReadingLevel.MIDDLE_SCHOOL

    def test_general_public_variants(self):
        """Test parsing general public level variants."""
        assert parse_reading_level("general_public") == ReadingLevel.GENERAL_PUBLIC
        assert parse_reading_level("general") == ReadingLevel.GENERAL_PUBLIC
        assert parse_reading_level("adult") == ReadingLevel.GENERAL_PUBLIC

    def test_unknown_level(self):
        """Test unknown levels return GENERAL_PUBLIC."""
        assert parse_reading_level("unknown") == ReadingLevel.GENERAL_PUBLIC
        assert parse_reading_level("") == ReadingLevel.GENERAL_PUBLIC
        assert parse_reading_level(None) == ReadingLevel.GENERAL_PUBLIC


class TestGetReadingLevelDescription:
    """Tests for get_reading_level_description function."""

    def test_elementary_description(self):
        """Test elementary level description."""
        desc = get_reading_level_description(ReadingLevel.ELEMENTARY)
        assert "5th grader" in desc
        assert "simple words" in desc

    def test_general_public_description(self):
        """Test general public level description."""
        desc = get_reading_level_description(ReadingLevel.GENERAL_PUBLIC)
        assert "average adult" in desc
        assert "everyday language" in desc


class TestKeyPoint:
    """Tests for KeyPoint dataclass."""

    def test_to_dict(self):
        """Test converting KeyPoint to dictionary."""
        kp = KeyPoint(
            point_number=1,
            original_concept="Complex regulatory framework",
            simplified="Rules that govern how things work",
            importance="critical",
        )
        d = kp.to_dict()

        assert d["point_number"] == 1
        assert d["simplified"] == "Rules that govern how things work"
        assert d["importance"] == "critical"


class TestSimplificationInput:
    """Tests for SimplificationInput dataclass."""

    def test_content_length_auto_calculated(self):
        """Test content_length is auto-calculated."""
        input_content = SimplificationInput(
            input_id="test-1",
            content="This is test content for simplification.",
        )
        assert input_content.content_length == len("This is test content for simplification.")


class TestPlainLanguageOutput:
    """Tests for PlainLanguageOutput Pydantic model."""

    def test_default_values(self):
        """Test default values are set correctly."""
        output = PlainLanguageOutput(
            output_id="test-1",
            one_sentence_summary="Test summary",
            one_paragraph_summary="Test paragraph",
            plain_explanation="Test explanation",
        )
        assert output.agent_count == 1
        assert output.mode == "single_agent"
        assert output.glossary == []


# ============================================================================
# Workflow Validation Tests
# ============================================================================


class TestValidateConfig:
    """Tests for workflow configuration validation."""

    def test_valid_config_minimal(self):
        """Test validation passes with minimal config."""
        workflow = PlainLanguageWorkflow()
        result = workflow.validate_config({
            "content": "Complex technical document content here.",
        })
        assert result.valid is True

    def test_valid_config_with_options(self):
        """Test validation passes with all options."""
        workflow = PlainLanguageWorkflow()
        result = workflow.validate_config({
            "content": "Complex content",
            "title": "Test Document",
            "content_type": "legal",
            "reading_level": "elementary",
            "agent": "anthropic:claude-sonnet-4-20250514",
        })
        assert result.valid is True

    def test_missing_content(self):
        """Test validation fails when content is missing."""
        workflow = PlainLanguageWorkflow()
        result = workflow.validate_config({})
        assert result.valid is False
        assert any("content" in e for e in result.errors)

    def test_empty_content(self):
        """Test validation fails when content is empty."""
        workflow = PlainLanguageWorkflow()
        result = workflow.validate_config({"content": "   "})
        assert result.valid is False

    def test_invalid_reading_level(self):
        """Test validation fails with invalid reading level."""
        workflow = PlainLanguageWorkflow()
        result = workflow.validate_config({
            "content": "Test content",
            "reading_level": "invalid_level",
        })
        assert result.valid is False
        assert any("reading_level" in e for e in result.errors)

    def test_too_many_agents(self):
        """Test validation fails with more than 5 agents."""
        workflow = PlainLanguageWorkflow()
        result = workflow.validate_config({
            "content": "Test content",
            "agents": ["a1", "a2", "a3", "a4", "a5", "a6"],
        })
        assert result.valid is False
        assert any("5 agents" in e for e in result.errors)


# ============================================================================
# Metadata Tests
# ============================================================================


class TestMetadata:
    """Tests for workflow metadata."""

    def test_workflow_id(self):
        """Test workflow ID is correct."""
        workflow = PlainLanguageWorkflow()
        assert workflow.metadata.workflow_id == "plain-language"

    def test_capabilities(self):
        """Test workflow capabilities."""
        workflow = PlainLanguageWorkflow()
        caps = workflow.metadata.capabilities
        assert "simplification" in caps
        assert "plain-language" in caps
        assert "accessibility" in caps

    def test_agent_requirements(self):
        """Test agent requirements allow 1-5 agents."""
        workflow = PlainLanguageWorkflow()
        assert workflow.metadata.requires_agents is True
        assert workflow.metadata.min_agents == 1
        assert workflow.metadata.max_agents == 5

    def test_inputs_defined(self):
        """Test all expected inputs are defined."""
        workflow = PlainLanguageWorkflow()
        input_names = [i.name for i in workflow.metadata.inputs]

        assert "content" in input_names
        assert "title" in input_names
        assert "content_type" in input_names
        assert "reading_level" in input_names
        assert "agent" in input_names
        assert "agents" in input_names


# ============================================================================
# JSON Parsing Tests
# ============================================================================


class TestJsonParsing:
    """Tests for JSON response parsing."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        workflow = PlainLanguageWorkflow()
        response = """
```json
{
  "one_sentence_summary": "This is simple.",
  "one_paragraph_summary": "This is a simple explanation.",
  "key_points": [],
  "plain_explanation": "Here is the full explanation.",
  "bottom_line": "The bottom line is this matters.",
  "who_is_affected": "Everyone",
  "action_items": ["Do this"],
  "glossary": []
}
```
"""
        parsed = workflow._parse_simplification_response(response)

        assert parsed["one_sentence_summary"] == "This is simple."
        assert parsed["bottom_line"] == "The bottom line is this matters."

    def test_parse_raw_json(self):
        """Test parsing raw JSON without markdown fence."""
        workflow = PlainLanguageWorkflow()
        response = '{"one_sentence_summary": "Simple.", "plain_explanation": "Explained."}'
        parsed = workflow._parse_simplification_response(response)

        assert parsed["one_sentence_summary"] == "Simple."

    def test_parse_invalid_json(self):
        """Test handling invalid JSON returns empty dict."""
        workflow = PlainLanguageWorkflow()
        response = "This is not JSON at all."
        parsed = workflow._parse_simplification_response(response)

        assert parsed == {}


# ============================================================================
# Prompt Template Tests
# ============================================================================


class TestPromptTemplates:
    """Tests for prompt template formatting."""

    def test_simplify_prompt_format(self):
        """Test simplify prompt can be formatted."""
        prompt = SIMPLIFY_PROMPT_TEMPLATE.format(
            title="Test Document",
            content_type="legal document",
            content="Complex legal text here...",
            reading_level_description="an average adult with no specialized knowledge",
        )
        assert "Test Document" in prompt
        assert "legal document" in prompt
        assert "average adult" in prompt
        assert "one_sentence_summary" in prompt

    def test_synthesis_prompt_format(self):
        """Test synthesis prompt can be formatted."""
        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            title="Test Document",
            content_type="technical",
            agent_explanations="Agent 1: Simple version...\nAgent 2: Another version...",
        )
        assert "Test Document" in prompt
        assert "Agent 1" in prompt


# ============================================================================
# Workflow Execution Tests
# ============================================================================


class TestWorkflowExecution:
    """Tests for workflow execution with mocked agents."""

    @pytest.mark.asyncio
    @patch('startd8.workflows.builtin.plain_language_workflow.resolve_agent_spec')
    async def test_single_agent_execution(self, mock_resolve):
        """Test single agent workflow execution."""
        mock_agent = AsyncMock()
        mock_agent.name = "claude"
        mock_agent.model = "claude-sonnet-4-20250514"
        mock_agent.agenerate.return_value = (
            json.dumps({
                "one_sentence_summary": "This policy affects everyone.",
                "one_paragraph_summary": "A longer explanation here.",
                "key_points": [
                    {
                        "point_number": 1,
                        "original_concept": "Regulatory framework",
                        "simplified": "Rules",
                        "importance": "critical",
                    }
                ],
                "plain_explanation": "Full explanation in plain language.",
                "bottom_line": "The bottom line is this matters to you.",
                "who_is_affected": "All citizens",
                "action_items": ["Stay informed"],
                "glossary": [
                    {"term": "framework", "definition": "a set of rules", "context": "used here"},
                ],
            }),
            500,
            Mock(input=300, output=200),
        )
        mock_resolve.return_value = mock_agent

        workflow = PlainLanguageWorkflow()
        result = await workflow._aexecute(
            config={
                "content": "Complex technical and legal jargon that needs simplification.",
                "title": "Test Policy",
            },
            agents=None,
            on_progress=None,
        )

        assert result.success is True
        assert result.workflow_id == "plain-language"
        assert result.output["one_sentence"] == "This policy affects everyone."
        assert result.output["mode"] == "single_agent"
        assert len(result.output["key_points"]) == 1

    @pytest.mark.asyncio
    @patch('startd8.workflows.builtin.plain_language_workflow.resolve_agents')
    @patch('startd8.workflows.builtin.plain_language_workflow.resolve_agent_spec')
    async def test_multi_agent_execution(self, mock_resolve_spec, mock_resolve_agents):
        """Test multi-agent workflow execution."""
        # Create two mock agents
        mock_agent1 = AsyncMock()
        mock_agent1.name = "claude"
        mock_agent1.model = "claude-sonnet-4-20250514"
        mock_agent1.agenerate.return_value = (
            json.dumps({
                "one_sentence_summary": "First agent's simple summary.",
                "one_paragraph_summary": "First agent's paragraph.",
                "key_points": [],
                "plain_explanation": "First explanation.",
                "bottom_line": "First bottom line.",
                "who_is_affected": "Everyone",
                "action_items": [],
                "glossary": [],
            }),
            400,
            Mock(input=200, output=150),
        )

        mock_agent2 = AsyncMock()
        mock_agent2.name = "gpt4o"
        mock_agent2.model = "gpt-4o"
        mock_agent2.agenerate.return_value = (
            json.dumps({
                "one_sentence_summary": "Second agent's summary.",
                "one_paragraph_summary": "Second paragraph.",
                "key_points": [],
                "plain_explanation": "Second explanation.",
                "bottom_line": "Second bottom line.",
                "who_is_affected": "All people",
                "action_items": [],
                "glossary": [],
            }),
            350,
            Mock(input=180, output=130),
        )

        mock_resolve_agents.return_value = [mock_agent1, mock_agent2]

        # Mock synthesis agent
        mock_synthesis = AsyncMock()
        mock_synthesis.name = "claude-synthesis"
        mock_synthesis.model = "claude-sonnet-4-20250514"
        mock_synthesis.agenerate.return_value = (
            json.dumps({
                "one_sentence_summary": "Synthesized best summary.",
                "one_paragraph_summary": "Synthesized paragraph.",
                "key_points": [],
                "plain_explanation": "Synthesized explanation.",
                "bottom_line": "Synthesized bottom line.",
                "who_is_affected": "Everyone affected",
                "action_items": ["Take action"],
                "glossary": [],
            }),
            300,
            Mock(input=150, output=120),
        )
        mock_resolve_spec.return_value = mock_synthesis

        workflow = PlainLanguageWorkflow()
        result = await workflow._aexecute(
            config={
                "content": "Complex content needing simplification.",
                "agents": ["agent1", "agent2"],
            },
            agents=None,
            on_progress=None,
        )

        assert result.success is True
        assert result.output["mode"] == "multi_agent"
        assert result.output["agent_count"] == 2


class TestAgentOutputConversion:
    """Tests for converting agent output to final format."""

    def test_agent_output_to_final(self):
        """Test converting AgentSimplification to PlainLanguageOutput."""
        workflow = PlainLanguageWorkflow()

        input_content = SimplificationInput(
            input_id="test",
            content="A" * 1000,  # 1000 chars
            content_type=ContentType.GENERAL,
            title="Test",
        )

        agent_output = AgentSimplification(
            agent_id="a1",
            agent_name="claude",
            model="claude-sonnet-4-20250514",
            one_sentence="Simple sentence.",
            one_paragraph="Simple paragraph.",
            plain_explanation="Simple explanation.",  # ~20 chars
            key_points=[
                KeyPoint(
                    point_number=1,
                    original_concept="Complex",
                    simplified="Simple",
                    importance="critical",
                )
            ],
            jargon_glossary=[
                JargonTerm(term="jargon", definition="technical word", context="here"),
            ],
            bottom_line="Bottom line here.",
            who_affected="Everyone",
            action_items=["Do something"],
        )

        output = workflow._agent_output_to_final(
            input_content,
            agent_output,
            ReadingLevel.GENERAL_PUBLIC,
            SimplificationMode.SINGLE_AGENT,
        )

        assert output.one_sentence_summary == "Simple sentence."
        assert output.mode == "single_agent"
        assert output.agent_count == 1
        assert len(output.key_points) == 1
        assert len(output.glossary) == 1
        assert output.original_length == 1000


# ============================================================================
# Lazy Loading Test
# ============================================================================


class TestLazyLoading:
    """Tests for lazy loading of the workflow."""

    def test_workflow_importable(self):
        """Test workflow can be imported via lazy loading."""
        from startd8.workflows.builtin import PlainLanguageWorkflow
        workflow = PlainLanguageWorkflow()
        assert workflow.metadata.workflow_id == "plain-language"
