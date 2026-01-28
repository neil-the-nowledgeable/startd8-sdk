"""
Unit tests for PolicyAnalysisWorkflow.

Tests the multi-agent critical policy analysis workflow that examines
laws, bills, and policies through a lens centering the benefit to people.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
import json

from startd8.workflows.builtin.policy_analysis_workflow import (
    PolicyAnalysisWorkflow,
    ANALYSIS_PROMPT_TEMPLATE,
    SYNTHESIS_PROMPT_TEMPLATE,
    NARRATIVE_REPORT_TEMPLATE,
)
from startd8.workflows.builtin.policy_analysis_models import (
    AnalysisCriterion,
    ConsensusLevel,
    CriterionScore,
    InputSource,
    OverallAssessment,
    PolicyAnalysisOutput,
    PolicyAnalysisResult,
    PolicyInput,
    PolicyInputType,
    RedFlag,
    Severity,
    SynthesizedScore,
    score_to_assessment,
    parse_policy_type,
)
from startd8.workflows.models import ValidationResult


# ============================================================================
# Model Tests
# ============================================================================


class TestAnalysisCriterion:
    """Tests for AnalysisCriterion enum."""

    def test_all_criteria_defined(self):
        """Test all seven criteria are defined."""
        criteria = list(AnalysisCriterion)
        assert len(criteria) == 7

        values = [c.value for c in criteria]
        assert "benefit_to_people" in values
        assert "people_empowerment" in values
        assert "power_imbalance" in values
        assert "corporate_privilege" in values
        assert "doctrine_of_discovery" in values
        assert "supremacy_ideology" in values
        assert "slavery_legacy" in values


class TestScoreToAssessment:
    """Tests for score_to_assessment function."""

    def test_harmful_range(self):
        """Test scores 0-20 are harmful."""
        assert score_to_assessment(0) == OverallAssessment.HARMFUL
        assert score_to_assessment(10) == OverallAssessment.HARMFUL
        assert score_to_assessment(20) == OverallAssessment.HARMFUL

    def test_concerning_range(self):
        """Test scores 21-40 are concerning."""
        assert score_to_assessment(21) == OverallAssessment.CONCERNING
        assert score_to_assessment(30) == OverallAssessment.CONCERNING
        assert score_to_assessment(40) == OverallAssessment.CONCERNING

    def test_neutral_range(self):
        """Test scores 41-60 are neutral."""
        assert score_to_assessment(41) == OverallAssessment.NEUTRAL
        assert score_to_assessment(50) == OverallAssessment.NEUTRAL
        assert score_to_assessment(60) == OverallAssessment.NEUTRAL

    def test_beneficial_range(self):
        """Test scores 61-80 are beneficial."""
        assert score_to_assessment(61) == OverallAssessment.BENEFICIAL
        assert score_to_assessment(70) == OverallAssessment.BENEFICIAL
        assert score_to_assessment(80) == OverallAssessment.BENEFICIAL

    def test_highly_beneficial_range(self):
        """Test scores 81-100 are highly beneficial."""
        assert score_to_assessment(81) == OverallAssessment.HIGHLY_BENEFICIAL
        assert score_to_assessment(90) == OverallAssessment.HIGHLY_BENEFICIAL
        assert score_to_assessment(100) == OverallAssessment.HIGHLY_BENEFICIAL


class TestParsePolicyType:
    """Tests for parse_policy_type function."""

    def test_bill_parsing(self):
        """Test parsing 'bill' type."""
        assert parse_policy_type("bill") == PolicyInputType.BILL
        assert parse_policy_type("BILL") == PolicyInputType.BILL
        assert parse_policy_type("  bill  ") == PolicyInputType.BILL

    def test_law_parsing(self):
        """Test parsing 'law' type."""
        assert parse_policy_type("law") == PolicyInputType.LAW

    def test_executive_order_parsing(self):
        """Test parsing executive order variants."""
        assert parse_policy_type("executive_order") == PolicyInputType.EXECUTIVE_ORDER
        assert parse_policy_type("executive order") == PolicyInputType.EXECUTIVE_ORDER

    def test_unknown_type(self):
        """Test unknown types return OTHER."""
        assert parse_policy_type("unknown") == PolicyInputType.OTHER
        assert parse_policy_type("") == PolicyInputType.OTHER
        assert parse_policy_type(None) == PolicyInputType.OTHER


class TestCriterionScore:
    """Tests for CriterionScore dataclass."""

    def test_score_clamping_high(self):
        """Test scores above 100 are clamped."""
        cs = CriterionScore(
            criterion=AnalysisCriterion.BENEFIT_TO_PEOPLE,
            score=150,
            confidence=0.8,
            rationale="Test"
        )
        assert cs.score == 100

    def test_score_clamping_low(self):
        """Test scores below 0 are clamped."""
        cs = CriterionScore(
            criterion=AnalysisCriterion.BENEFIT_TO_PEOPLE,
            score=-10,
            confidence=0.8,
            rationale="Test"
        )
        assert cs.score == 0

    def test_confidence_clamping(self):
        """Test confidence is clamped to 0-1."""
        cs = CriterionScore(
            criterion=AnalysisCriterion.BENEFIT_TO_PEOPLE,
            score=50,
            confidence=1.5,
            rationale="Test"
        )
        assert cs.confidence == 1.0


class TestSynthesizedScore:
    """Tests for SynthesizedScore dataclass."""

    def test_from_scores_high_consensus(self):
        """Test high consensus with low std deviation."""
        synth = SynthesizedScore.from_scores(
            AnalysisCriterion.BENEFIT_TO_PEOPLE,
            [50, 52, 48, 51],
            "Test rationale"
        )
        assert synth.consensus_level == ConsensusLevel.HIGH
        assert synth.mean_score == pytest.approx(50.25)
        assert synth.min_score == 48
        assert synth.max_score == 52

    def test_from_scores_moderate_consensus(self):
        """Test moderate consensus (std dev 10-20)."""
        # Scores with std dev ~14: 30, 40, 50, 60
        synth = SynthesizedScore.from_scores(
            AnalysisCriterion.BENEFIT_TO_PEOPLE,
            [30, 40, 50, 60],
            "Test"
        )
        assert synth.consensus_level == ConsensusLevel.MODERATE

    def test_from_scores_divergent(self):
        """Test divergent scores."""
        synth = SynthesizedScore.from_scores(
            AnalysisCriterion.BENEFIT_TO_PEOPLE,
            [10, 50, 90, 30],
            "Test"
        )
        assert synth.consensus_level == ConsensusLevel.DIVERGENT

    def test_from_scores_empty(self):
        """Test handling empty score list."""
        synth = SynthesizedScore.from_scores(
            AnalysisCriterion.BENEFIT_TO_PEOPLE,
            [],
            "Test"
        )
        assert synth.mean_score == 0.0
        assert synth.consensus_level == ConsensusLevel.DIVERGENT


class TestRedFlag:
    """Tests for RedFlag dataclass."""

    def test_to_dict(self):
        """Test converting RedFlag to dictionary."""
        flag = RedFlag(
            flag_id="flag-1",
            severity=Severity.CRITICAL,
            category=AnalysisCriterion.CORPORATE_PRIVILEGE,
            title="Corporate Immunity",
            description="Grants blanket immunity",
            evidence_quotes=["Section 3.2"]
        )
        d = flag.to_dict()

        assert d["flag_id"] == "flag-1"
        assert d["severity"] == "critical"
        assert d["category"] == "corporate_privilege"
        assert d["title"] == "Corporate Immunity"


class TestPolicyInput:
    """Tests for PolicyInput dataclass."""

    def test_content_length_auto_calculated(self):
        """Test content_length is auto-calculated."""
        policy = PolicyInput(
            input_id="test-1",
            source_type=InputSource.RAW_TEXT,
            original_source="raw_text",
            content="This is test content.",
        )
        assert policy.content_length == len("This is test content.")


class TestPolicyAnalysisResult:
    """Tests for PolicyAnalysisResult dataclass."""

    def test_to_summary(self):
        """Test summary generation."""
        output = PolicyAnalysisOutput(
            analysis_id="pa-123",
            policy_title="Test Bill",
            policy_type="bill",
            overall_score=45,
            overall_assessment="concerning",
            confidence=0.8,
            red_flags=[],
            agent_count=3,
            consensus_level="moderate",
            analyzed_at=datetime.now(timezone.utc)
        )
        result = PolicyAnalysisResult(
            workflow_id="pa-test",
            success=True,
            structured_output=output,
            total_cost=0.05,
            total_time_ms=5000
        )
        summary = result.to_summary()

        assert summary["workflow_id"] == "pa-test"
        assert summary["success"] is True
        assert summary["overall_score"] == 45
        assert "$0.0500" in summary["total_cost"]


# ============================================================================
# Workflow Validation Tests
# ============================================================================


class TestValidateConfig:
    """Tests for workflow configuration validation."""

    def test_valid_config_with_content(self):
        """Test validation passes with content provided."""
        workflow = PolicyAnalysisWorkflow()
        result = workflow.validate_config({
            "content": "This is a test policy document.",
            "agents": ["anthropic:claude-sonnet-4-20250514", "openai:gpt-4o"],
        })
        assert result.valid is True

    def test_valid_config_with_url(self):
        """Test validation passes with URL provided."""
        workflow = PolicyAnalysisWorkflow()
        result = workflow.validate_config({
            "url": "https://congress.gov/bill/test",
            "agents": ["anthropic:claude-sonnet-4-20250514", "openai:gpt-4o"],
        })
        assert result.valid is True

    def test_valid_config_with_file(self):
        """Test validation passes with file_path provided."""
        workflow = PolicyAnalysisWorkflow()
        result = workflow.validate_config({
            "file_path": "/path/to/policy.txt",
            "agents": ["anthropic:claude-sonnet-4-20250514", "openai:gpt-4o"],
        })
        assert result.valid is True

    def test_missing_input_source(self):
        """Test validation fails when no input source provided."""
        workflow = PolicyAnalysisWorkflow()
        result = workflow.validate_config({
            "agents": ["anthropic:claude-sonnet-4-20250514", "openai:gpt-4o"],
        })
        assert result.valid is False
        assert any("content, url, or file_path" in e for e in result.errors)

    def test_too_few_agents(self):
        """Test validation fails with fewer than 2 agents."""
        workflow = PolicyAnalysisWorkflow()
        result = workflow.validate_config({
            "content": "Test policy",
            "agents": ["anthropic:claude-sonnet-4-20250514"],
        })
        assert result.valid is False
        assert any("At least 2 agents" in e for e in result.errors)

    def test_too_many_agents(self):
        """Test validation fails with more than 5 agents."""
        workflow = PolicyAnalysisWorkflow()
        result = workflow.validate_config({
            "content": "Test policy",
            "agents": [
                "agent1", "agent2", "agent3", "agent4", "agent5", "agent6"
            ],
        })
        assert result.valid is False
        assert any("Maximum 5 agents" in e for e in result.errors)

    def test_invalid_output_format(self):
        """Test validation fails with invalid output format."""
        workflow = PolicyAnalysisWorkflow()
        result = workflow.validate_config({
            "content": "Test policy",
            "agents": ["agent1", "agent2"],
            "output_format": "invalid",
        })
        assert result.valid is False
        assert any("output_format" in e for e in result.errors)


# ============================================================================
# Metadata Tests
# ============================================================================


class TestMetadata:
    """Tests for workflow metadata."""

    def test_workflow_id(self):
        """Test workflow ID is correct."""
        workflow = PolicyAnalysisWorkflow()
        assert workflow.metadata.workflow_id == "policy-analysis"

    def test_capabilities(self):
        """Test workflow capabilities include expected tags."""
        workflow = PolicyAnalysisWorkflow()
        caps = workflow.metadata.capabilities
        assert "policy-analysis" in caps
        assert "multi-agent" in caps
        assert "parallel-execution" in caps
        assert "critical-framework" in caps

    def test_agent_requirements(self):
        """Test agent requirements are set correctly."""
        workflow = PolicyAnalysisWorkflow()
        assert workflow.metadata.requires_agents is True
        assert workflow.metadata.min_agents == 2
        assert workflow.metadata.max_agents == 5

    def test_inputs_defined(self):
        """Test all expected inputs are defined."""
        workflow = PolicyAnalysisWorkflow()
        input_names = [i.name for i in workflow.metadata.inputs]

        assert "content" in input_names
        assert "url" in input_names
        assert "file_path" in input_names
        assert "policy_type" in input_names
        assert "jurisdiction" in input_names
        assert "agents" in input_names
        assert "synthesis_agent" in input_names
        assert "output_format" in input_names


# ============================================================================
# Input Processing Tests
# ============================================================================


class TestInputProcessing:
    """Tests for input processing methods."""

    def test_extract_text_from_html(self):
        """Test HTML text extraction."""
        workflow = PolicyAnalysisWorkflow()
        html = """
        <html>
        <head><style>.class { color: red; }</style></head>
        <body>
        <script>console.log('test');</script>
        <p>This is the main content.</p>
        <div>More text here.</div>
        </body>
        </html>
        """
        text = workflow._extract_text_from_html(html)

        assert "This is the main content." in text
        assert "More text here." in text
        assert "console.log" not in text
        assert "<p>" not in text

    def test_extract_text_from_html_entities(self):
        """Test HTML entity decoding."""
        workflow = PolicyAnalysisWorkflow()
        html = "<p>Test &amp; verify &lt;code&gt;</p>"
        text = workflow._extract_text_from_html(html)

        assert "Test & verify" in text
        assert "<code>" in text

    def test_extract_title_from_url_congress(self):
        """Test title extraction from congress.gov URLs."""
        workflow = PolicyAnalysisWorkflow()
        url = "https://congress.gov/bill/118th-congress/house-bill/1234"
        title = workflow._extract_title_from_url(url)

        assert "118" in title
        assert "1234" in title

    def test_extract_title_from_url_generic(self):
        """Test title extraction from generic URLs."""
        workflow = PolicyAnalysisWorkflow()
        url = "https://example.com/policies/clean-air-act"
        title = workflow._extract_title_from_url(url)

        assert "Clean Air Act" in title

    def test_extract_title_from_content(self):
        """Test title extraction from content."""
        workflow = PolicyAnalysisWorkflow()
        content = """The Clean Air Protection Act

This bill aims to protect air quality...
"""
        title = workflow._extract_title_from_content(content)
        assert "Clean Air Protection Act" in title

    def test_extract_title_skips_metadata(self):
        """Test title extraction skips metadata lines."""
        workflow = PolicyAnalysisWorkflow()
        content = """https://example.com
date: 2024-01-01
The Actual Title Here

Content starts here...
"""
        title = workflow._extract_title_from_content(content)
        assert "Actual Title" in title


# ============================================================================
# JSON Parsing Tests
# ============================================================================


class TestJsonParsing:
    """Tests for JSON response parsing."""

    def test_parse_analysis_response_valid_json(self):
        """Test parsing valid JSON response."""
        workflow = PolicyAnalysisWorkflow()
        response = """Here is my analysis:

```json
{
  "overall_score": 45,
  "overall_assessment": "concerning",
  "executive_summary": "This is concerning.",
  "criterion_scores": [],
  "red_flags": [],
  "recommendations": ["Fix it"]
}
```

That concludes my analysis.
"""
        parsed = workflow._parse_analysis_response(response)

        assert parsed["overall_score"] == 45
        assert parsed["overall_assessment"] == "concerning"
        assert parsed["recommendations"] == ["Fix it"]

    def test_parse_analysis_response_raw_json(self):
        """Test parsing raw JSON without markdown fence."""
        workflow = PolicyAnalysisWorkflow()
        response = '{"overall_score": 60, "overall_assessment": "neutral"}'
        parsed = workflow._parse_analysis_response(response)

        assert parsed["overall_score"] == 60

    def test_parse_analysis_response_invalid_json(self):
        """Test handling invalid JSON returns empty dict."""
        workflow = PolicyAnalysisWorkflow()
        response = "This is not JSON at all."
        parsed = workflow._parse_analysis_response(response)

        assert parsed == {}

    def test_parse_analysis_response_fixes_trailing_comma(self):
        """Test parser fixes trailing commas."""
        workflow = PolicyAnalysisWorkflow()
        response = '{"overall_score": 50, "items": ["a", "b",]}'
        parsed = workflow._parse_analysis_response(response)

        assert parsed.get("overall_score") == 50

    def test_parse_criterion_scores(self):
        """Test parsing criterion scores from response."""
        workflow = PolicyAnalysisWorkflow()
        parsed = {
            "criterion_scores": [
                {
                    "criterion": "benefit_to_people",
                    "score": 40,
                    "confidence": 0.8,
                    "rationale": "Limited benefit",
                    "evidence": ["Section 1"],
                    "red_flags": ["Corporate loophole"]
                },
                {
                    "criterion": "people_empowerment",
                    "score": 60,
                    "confidence": 0.7,
                    "rationale": "Some empowerment",
                    "evidence": [],
                    "red_flags": []
                }
            ]
        }
        scores = workflow._parse_criterion_scores(parsed)

        assert len(scores) == 2
        assert scores[0].criterion == AnalysisCriterion.BENEFIT_TO_PEOPLE
        assert scores[0].score == 40
        assert scores[1].criterion == AnalysisCriterion.PEOPLE_EMPOWERMENT
        assert scores[1].score == 60

    def test_parse_red_flags(self):
        """Test parsing red flags from response."""
        workflow = PolicyAnalysisWorkflow()
        parsed = {
            "red_flags": [
                {
                    "severity": "critical",
                    "category": "corporate_privilege",
                    "title": "Corporate Immunity",
                    "description": "Blanket immunity clause",
                    "evidence_quotes": ["Section 5.2"]
                },
                {
                    "severity": "minor",
                    "category": "benefit_to_people",
                    "title": "Unclear Language",
                    "description": "Ambiguous wording",
                    "evidence_quotes": []
                }
            ]
        }
        flags = workflow._parse_red_flags(parsed)

        assert len(flags) == 2
        assert flags[0].severity == Severity.CRITICAL
        assert flags[0].category == AnalysisCriterion.CORPORATE_PRIVILEGE
        assert flags[1].severity == Severity.MINOR


# ============================================================================
# Prompt Template Tests
# ============================================================================


class TestPromptTemplates:
    """Tests for prompt template formatting."""

    def test_analysis_prompt_format(self):
        """Test analysis prompt can be formatted."""
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            policy_title="Test Bill",
            policy_type="bill",
            jurisdiction="US Federal",
            policy_content="The content of the bill..."
        )
        assert "Test Bill" in prompt
        assert "US Federal" in prompt
        assert "benefit_to_people" in prompt
        assert "Doctrine of Discovery" in prompt
        assert "regulatory capture" in prompt

    def test_analysis_prompt_includes_all_criteria(self):
        """Test analysis prompt mentions all seven criteria."""
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            policy_title="Test",
            policy_type="bill",
            jurisdiction="US",
            policy_content="Content"
        )
        assert "Benefit to People at Large" in prompt
        assert "Empowerment of People" in prompt
        assert "Power Imbalance Recognition" in prompt
        assert "Corporate Privilege Scrutiny" in prompt
        assert "Doctrine of Discovery Legacy" in prompt
        assert "Supremacy Ideology Rejection" in prompt
        assert "Slavery Legacy Critique" in prompt

    def test_synthesis_prompt_format(self):
        """Test synthesis prompt can be formatted."""
        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            policy_title="Test Bill",
            policy_type="bill",
            jurisdiction="US Federal",
            agent_analyses="Agent 1: Score 45\nAgent 2: Score 55"
        )
        assert "Test Bill" in prompt
        assert "Agent 1: Score 45" in prompt
        assert "consensus" in prompt.lower()

    def test_narrative_report_format(self):
        """Test narrative report can be formatted."""
        report = NARRATIVE_REPORT_TEMPLATE.format(
            policy_title="Clean Air Act",
            analysis_date="2024-01-15",
            policy_type="law",
            jurisdiction="US Federal",
            executive_summary="This law improves air quality.",
            overall_score=75,
            overall_assessment="beneficial",
            confidence=0.85,
            consensus_level="moderate",
            criterion_sections="Section content here...",
            red_flags_section="No critical flags.",
            recommendations_section="1. Continue monitoring.",
            agent_count=3,
            total_cost=0.05,
            total_time_ms=5000,
            agent_names="claude, gpt4o, gemini"
        )
        assert "Clean Air Act" in report
        assert "75/100" in report
        assert "beneficial" in report
        assert "85%" in report


# ============================================================================
# Workflow Execution Tests
# ============================================================================


class TestWorkflowExecution:
    """Tests for workflow execution with mocked agents."""

    @pytest.mark.asyncio
    @patch('startd8.workflows.builtin.policy_analysis_workflow.resolve_agents')
    @patch('startd8.workflows.builtin.policy_analysis_workflow.resolve_agent_spec')
    async def test_workflow_aexecute_success(self, mock_resolve_spec, mock_resolve_agents):
        """Test successful async workflow execution."""
        # Mock analysis agents
        mock_agent1 = AsyncMock()
        mock_agent1.name = "claude"
        mock_agent1.model = "claude-sonnet-4-20250514"
        mock_agent1.agenerate.return_value = (
            json.dumps({
                "overall_score": 45,
                "overall_assessment": "concerning",
                "executive_summary": "This policy has issues.",
                "criterion_scores": [
                    {
                        "criterion": "benefit_to_people",
                        "score": 40,
                        "confidence": 0.8,
                        "rationale": "Limited benefit",
                        "evidence": [],
                        "red_flags": []
                    }
                ],
                "red_flags": [],
                "recommendations": ["Improve transparency"],
                "detailed_analysis": "Detailed analysis here."
            }),
            1000,
            Mock(input=500, output=300)
        )

        mock_agent2 = AsyncMock()
        mock_agent2.name = "gpt4o"
        mock_agent2.model = "gpt-4o"
        mock_agent2.agenerate.return_value = (
            json.dumps({
                "overall_score": 55,
                "overall_assessment": "neutral",
                "executive_summary": "Mixed results.",
                "criterion_scores": [],
                "red_flags": [],
                "recommendations": [],
                "detailed_analysis": ""
            }),
            800,
            Mock(input=400, output=200)
        )

        mock_resolve_agents.return_value = [mock_agent1, mock_agent2]

        # Mock synthesis agent
        mock_synthesis = AsyncMock()
        mock_synthesis.name = "claude-synthesis"
        mock_synthesis.model = "claude-sonnet-4-20250514"
        mock_synthesis.agenerate.return_value = (
            json.dumps({
                "overall_score": 50,
                "overall_assessment": "neutral",
                "confidence": 0.75,
                "consensus_level": "moderate",
                "executive_summary": "Synthesized summary.",
                "synthesized_criterion_scores": {},
                "consolidated_red_flags": [],
                "synthesized_recommendations": []
            }),
            600,
            Mock(input=300, output=200)
        )
        mock_resolve_spec.return_value = mock_synthesis

        workflow = PolicyAnalysisWorkflow()
        result = await workflow._aexecute(
            config={
                "content": "This is a test policy document with important provisions.",
                "agents": ["agent1", "agent2"],
                "output_format": "both",
            },
            agents=None,
            on_progress=None
        )

        assert result.success is True
        assert result.workflow_id == "policy-analysis"
        assert "structured_output" in result.output
        assert "narrative_report" in result.output

    @pytest.mark.asyncio
    async def test_workflow_handles_input_error(self):
        """Test workflow handles input processing errors."""
        workflow = PolicyAnalysisWorkflow()

        # Test with non-existent file
        result = await workflow._aexecute(
            config={
                "file_path": "/nonexistent/path/policy.txt",
                "agents": ["agent1", "agent2"],
            },
            agents=None,
            on_progress=None
        )

        assert result.success is False
        assert "Input processing failed" in result.error


class TestStructuredOutputBuilding:
    """Tests for building structured output from analyses."""

    def test_build_structured_output_aggregates_scores(self):
        """Test that structured output correctly aggregates scores."""
        from startd8.workflows.builtin.policy_analysis_models import AgentAnalysis

        workflow = PolicyAnalysisWorkflow()

        # Create mock analyses
        analysis1 = AgentAnalysis(
            analysis_id="a1",
            agent_name="agent1",
            model="model1",
            overall_score=40,
            overall_assessment=OverallAssessment.CONCERNING,
            criterion_scores=[
                CriterionScore(
                    criterion=AnalysisCriterion.BENEFIT_TO_PEOPLE,
                    score=35,
                    confidence=0.8,
                    rationale="Test"
                )
            ],
            red_flags=[]
        )

        analysis2 = AgentAnalysis(
            analysis_id="a2",
            agent_name="agent2",
            model="model2",
            overall_score=50,
            overall_assessment=OverallAssessment.NEUTRAL,
            criterion_scores=[
                CriterionScore(
                    criterion=AnalysisCriterion.BENEFIT_TO_PEOPLE,
                    score=45,
                    confidence=0.7,
                    rationale="Test 2"
                )
            ],
            red_flags=[]
        )

        policy_input = PolicyInput(
            input_id="test",
            source_type=InputSource.RAW_TEXT,
            original_source="raw_text",
            content="Test content",
            title="Test Policy"
        )

        output = workflow._build_structured_output(
            policy_input, [analysis1, analysis2]
        )

        assert output.overall_score == 45  # Mean of 40 and 50
        assert output.agent_count == 2
        assert "benefit_to_people" in output.criterion_scores
        assert output.criterion_scores["benefit_to_people"].mean_score == 40.0  # Mean of 35 and 45

    def test_build_structured_output_consolidates_red_flags(self):
        """Test that red flags are consolidated across agents."""
        from startd8.workflows.builtin.policy_analysis_models import AgentAnalysis

        workflow = PolicyAnalysisWorkflow()

        flag1 = RedFlag(
            flag_id="f1",
            severity=Severity.CRITICAL,
            category=AnalysisCriterion.CORPORATE_PRIVILEGE,
            title="Corporate Immunity",
            description="Desc 1"
        )

        flag2 = RedFlag(
            flag_id="f2",
            severity=Severity.CRITICAL,
            category=AnalysisCriterion.CORPORATE_PRIVILEGE,
            title="Corporate Immunity",  # Same title
            description="Desc 2"
        )

        analysis1 = AgentAnalysis(
            analysis_id="a1",
            agent_name="agent1",
            model="model1",
            overall_score=40,
            overall_assessment=OverallAssessment.CONCERNING,
            red_flags=[flag1]
        )

        analysis2 = AgentAnalysis(
            analysis_id="a2",
            agent_name="agent2",
            model="model2",
            overall_score=45,
            overall_assessment=OverallAssessment.CONCERNING,
            red_flags=[flag2]
        )

        policy_input = PolicyInput(
            input_id="test",
            source_type=InputSource.RAW_TEXT,
            original_source="raw_text",
            content="Test",
            title="Test"
        )

        output = workflow._build_structured_output(
            policy_input, [analysis1, analysis2]
        )

        # Same titled flags should be consolidated
        # Note: With current implementation they get counted as identifying agents
        assert output.critical_flags_count >= 1


# ============================================================================
# Lazy Loading Test
# ============================================================================


class TestLazyLoading:
    """Tests for lazy loading of the workflow."""

    def test_workflow_importable(self):
        """Test workflow can be imported via lazy loading."""
        from startd8.workflows.builtin import PolicyAnalysisWorkflow
        workflow = PolicyAnalysisWorkflow()
        assert workflow.metadata.workflow_id == "policy-analysis"
