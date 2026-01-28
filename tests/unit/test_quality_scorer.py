"""
Unit tests for quality scorer module.

Tests cover:
- DimensionScore validation
- RuleBasedScorer individual checks
- RuleBasedScorer full scoring
- QualityScorer with rules only
- QualityScorer score aggregation
- LLMJudge prompt building (mock agent)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from startd8.evaluation import (
    # Dimensions
    ScoringDimension,
    DimensionScore,
    # Rules
    RuleBasedScorer,
    # Judges
    JudgePromptTemplate,
    LLMJudge,
    # Scorer
    QualityScorer,
    QualityScorerConfig,
    QualityScore,
    # Task types
    Task,
    TaskCategory,
    TaskDifficulty,
    EvaluationCriteria,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_coding_task():
    """Create a sample coding task for testing."""
    return Task(
        id="test-fibonacci",
        name="Fibonacci Implementation",
        description="Implement a function to calculate the nth Fibonacci number.",
        category=TaskCategory.CODING,
        difficulty=TaskDifficulty.MEDIUM,
        prompt_template="Write a Python function to calculate the nth Fibonacci number.",
        evaluation_criteria=[
            EvaluationCriteria(name="correctness", description="Correct output", weight=0.5),
            EvaluationCriteria(name="efficiency", description="Good performance", weight=0.3),
            EvaluationCriteria(name="readability", description="Clean code", weight=0.2),
        ],
        tags=["algorithm", "recursion", "python"],
    )


@pytest.fixture
def sample_design_task():
    """Create a sample design task for testing."""
    return Task(
        id="test-api-design",
        name="REST API Design",
        description="Design a REST API for a todo application.",
        category=TaskCategory.DESIGN,
        difficulty=TaskDifficulty.EASY,
        prompt_template="Design a REST API with endpoints for creating, reading, updating, and deleting todos.",
        evaluation_criteria=[
            EvaluationCriteria(name="completeness", description="All CRUD operations", weight=0.5),
            EvaluationCriteria(name="REST principles", description="Follows REST conventions", weight=0.5),
        ],
        tags=["api", "rest", "design"],
    )


@pytest.fixture
def good_code_response():
    """Sample good code response."""
    return '''Here's an efficient Fibonacci implementation:

```python
def fibonacci(n: int) -> int:
    """
    Calculate the nth Fibonacci number using dynamic programming.

    Time complexity: O(n)
    Space complexity: O(1)
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if n <= 1:
        return n

    prev, curr = 0, 1
    for _ in range(2, n + 1):
        prev, curr = curr, prev + curr
    return curr
```

This implementation uses iteration with O(n) time complexity and O(1) space complexity.
'''


@pytest.fixture
def poor_code_response():
    """Sample poor code response with issues."""
    return '''Here's a basic solution:

```python
def fib(n):
    # TODO: add error handling
    if n <= 1:
        return n
    return fib(n-1) + fib(n-2)
```

This is a simple recursive solution. You might want to add memoization.
'''


@pytest.fixture
def insecure_code_response():
    """Sample response with security issues."""
    return '''Here's a solution that reads config:

```python
import yaml
import os

password = "secret123"  # API password
api_key = "sk-12345"

def load_config(user_input):
    config = yaml.load(open(user_input))
    query = f"SELECT * FROM users WHERE id={user_input}"
    return eval(config['command'])
```
'''


# =============================================================================
# DimensionScore Tests
# =============================================================================


class TestDimensionScore:
    """Test DimensionScore validation."""

    def test_valid_dimension_score(self):
        """Test creating a valid dimension score."""
        score = DimensionScore(
            dimension=ScoringDimension.CORRECTNESS,
            score=0.85,
            confidence=0.9,
            explanation="Solution correctly implements the algorithm",
        )
        assert score.dimension == ScoringDimension.CORRECTNESS
        assert score.score == 0.85
        assert score.confidence == 0.9
        assert "correctly" in score.explanation

    def test_score_with_details(self):
        """Test dimension score with details dictionary."""
        score = DimensionScore(
            dimension=ScoringDimension.CODE_QUALITY,
            score=0.7,
            confidence=0.8,
            explanation="Good code quality overall",
            details={"has_comments": True, "follows_style": True},
        )
        assert score.details is not None
        assert score.details["has_comments"] is True

    def test_score_out_of_range_raises_error(self):
        """Test that scores outside 0-1 range raise errors."""
        with pytest.raises(ValueError, match="Score must be between"):
            DimensionScore(
                dimension=ScoringDimension.CORRECTNESS,
                score=1.5,
                confidence=0.9,
                explanation="Test",
            )

        with pytest.raises(ValueError, match="Score must be between"):
            DimensionScore(
                dimension=ScoringDimension.CORRECTNESS,
                score=-0.1,
                confidence=0.9,
                explanation="Test",
            )

    def test_confidence_out_of_range_raises_error(self):
        """Test that confidence outside 0-1 range raises errors."""
        with pytest.raises(ValueError, match="Confidence must be between"):
            DimensionScore(
                dimension=ScoringDimension.CORRECTNESS,
                score=0.5,
                confidence=1.2,
                explanation="Test",
            )

    def test_empty_explanation_raises_error(self):
        """Test that empty explanation raises error."""
        with pytest.raises(ValueError, match="Explanation cannot be empty"):
            DimensionScore(
                dimension=ScoringDimension.CORRECTNESS,
                score=0.5,
                confidence=0.5,
                explanation="",
            )

    def test_all_dimensions(self):
        """Test all scoring dimensions can be used."""
        for dimension in ScoringDimension:
            score = DimensionScore(
                dimension=dimension,
                score=0.5,
                confidence=0.5,
                explanation=f"Testing {dimension.value}",
            )
            assert score.dimension == dimension


# =============================================================================
# RuleBasedScorer Individual Checks Tests
# =============================================================================


class TestRuleBasedScorerChecks:
    """Test RuleBasedScorer individual check methods."""

    def test_check_syntax_valid_python(self):
        """Test Python syntax validation."""
        scorer = RuleBasedScorer()

        valid_python = """
```python
def hello():
    print("Hello")

class MyClass:
    pass
```
"""
        assert scorer.check_syntax_valid(valid_python, "python") is True

    def test_check_syntax_valid_javascript(self):
        """Test JavaScript syntax validation."""
        scorer = RuleBasedScorer()

        valid_js = """
```javascript
function hello() {
    console.log("Hello");
}
const x = 5;
```
"""
        assert scorer.check_syntax_valid(valid_js, "javascript") is True

    def test_check_syntax_valid_unknown_language(self):
        """Test unknown language falls back to code block detection."""
        scorer = RuleBasedScorer()

        with_code = "```ruby\nputs 'hello'\n```"
        assert scorer.check_syntax_valid(with_code, "ruby") is True

        without_code = "Just plain text"
        assert scorer.check_syntax_valid(without_code, "ruby") is False

    def test_check_has_code_blocks(self):
        """Test code block detection."""
        scorer = RuleBasedScorer()

        with_blocks = "Here is code:\n```python\nprint('hi')\n```"
        assert scorer.check_has_code_blocks(with_blocks) is True

        without_blocks = "Just plain text explanation"
        assert scorer.check_has_code_blocks(without_blocks) is False

        inline_only = "Use `print()` to output"
        assert scorer.check_has_code_blocks(inline_only) is False

    def test_check_minimum_length(self):
        """Test minimum length check."""
        scorer = RuleBasedScorer()

        short = "Hi"
        assert scorer.check_minimum_length(short, 100) is False
        assert scorer.check_minimum_length(short, 2) is True

        long = "x" * 200
        assert scorer.check_minimum_length(long, 100) is True

    def test_check_contains_keywords(self):
        """Test keyword detection."""
        scorer = RuleBasedScorer()

        text = "This solution uses a hash table for O(1) lookup time complexity."

        found = scorer.check_contains_keywords(text, ["hash", "O(1)", "missing"])
        assert "hash" in found
        assert "O(1)" in found
        assert "missing" not in found

    def test_check_no_todo_placeholders(self):
        """Test TODO/placeholder detection."""
        scorer = RuleBasedScorer()

        clean = "This is a complete implementation."
        assert scorer.check_no_todo_placeholders(clean) is True

        with_todo = "This is done. # TODO: add tests"
        assert scorer.check_no_todo_placeholders(with_todo) is False

        with_fixme = "# FIXME: this is broken"
        assert scorer.check_no_todo_placeholders(with_fixme) is False

        with_placeholder = "Add your code here: [placeholder]"
        assert scorer.check_no_todo_placeholders(with_placeholder) is False

    def test_calculate_completeness_score(self):
        """Test completeness score calculation."""
        scorer = RuleBasedScorer()

        # All criteria mentioned
        full = "This solution handles correctness, efficiency, and readability."
        score = scorer.calculate_completeness_score(full, ["correctness", "efficiency", "readability"])
        assert score == 1.0

        # Partial criteria (using exact keywords)
        partial = "This solution demonstrates correctness and readability."
        score = scorer.calculate_completeness_score(partial, ["correctness", "efficiency", "readability"])
        assert 0.6 <= score <= 0.7  # 2/3

        # No criteria
        none = "Here is some code."
        score = scorer.calculate_completeness_score(none, ["correctness", "efficiency", "readability"])
        assert score == 0.0

        # Empty criteria list
        score = scorer.calculate_completeness_score("anything", [])
        assert score == 1.0


# =============================================================================
# RuleBasedScorer Full Scoring Tests
# =============================================================================


class TestRuleBasedScorerFullScoring:
    """Test RuleBasedScorer full response scoring."""

    def test_score_good_response(self, sample_coding_task, good_code_response):
        """Test scoring a good code response."""
        scorer = RuleBasedScorer()
        scores = scorer.score_response(good_code_response, sample_coding_task)

        assert ScoringDimension.CORRECTNESS in scores
        assert ScoringDimension.COMPLETENESS in scores
        assert ScoringDimension.CODE_QUALITY in scores
        assert ScoringDimension.EFFICIENCY in scores
        assert ScoringDimension.SECURITY in scores

        # Good response should score well
        assert scores[ScoringDimension.CORRECTNESS].score >= 0.6
        assert scores[ScoringDimension.CODE_QUALITY].score >= 0.5

    def test_score_poor_response(self, sample_coding_task, poor_code_response):
        """Test scoring a poor code response with TODO."""
        scorer = RuleBasedScorer()
        scores = scorer.score_response(poor_code_response, sample_coding_task)

        # Poor response has TODO placeholder
        correctness = scores[ScoringDimension.CORRECTNESS]
        assert correctness.details["no_placeholders"] is False

    def test_score_insecure_response(self, sample_coding_task, insecure_code_response):
        """Test scoring response with security issues."""
        scorer = RuleBasedScorer()
        scores = scorer.score_response(insecure_code_response, sample_coding_task)

        security = scores[ScoringDimension.SECURITY]
        assert security.score < 1.0  # Should have deductions
        assert len(security.details["issues_found"]) > 0

    def test_score_design_task(self, sample_design_task):
        """Test scoring a design task (non-coding)."""
        scorer = RuleBasedScorer()

        design_response = """
Here's the REST API design for the todo application:

## Endpoints

1. GET /todos - List all todos
2. POST /todos - Create a new todo
3. GET /todos/{id} - Get a specific todo
4. PUT /todos/{id} - Update a todo
5. DELETE /todos/{id} - Delete a todo

Each endpoint follows REST conventions with proper HTTP methods.
"""

        scores = scorer.score_response(design_response, sample_design_task)

        # Code quality should be marked as N/A for design tasks
        code_quality = scores[ScoringDimension.CODE_QUALITY]
        assert code_quality.details["applicable"] is False


# =============================================================================
# QualityScorer Tests
# =============================================================================


class TestQualityScorer:
    """Test QualityScorer orchestration."""

    def test_rules_only_scoring(self, sample_coding_task, good_code_response):
        """Test scoring with rules only."""
        config = QualityScorerConfig(use_rules=True, use_llm_judge=False)
        scorer = QualityScorer(config)

        result = scorer.score_sync(good_code_response, sample_coding_task)

        assert isinstance(result, QualityScore)
        assert result.method == "rules"
        assert 0.0 <= result.overall <= 1.0
        assert len(result.dimensions) > 0

    def test_quality_score_to_dict(self, sample_coding_task, good_code_response):
        """Test QualityScore serialization."""
        scorer = QualityScorer()
        result = scorer.score_sync(good_code_response, sample_coding_task)

        data = result.to_dict()

        assert "overall" in data
        assert "method" in data
        assert "timestamp" in data
        assert "dimensions" in data
        assert isinstance(data["dimensions"], dict)

    def test_quality_score_average_confidence(self, sample_coding_task, good_code_response):
        """Test average confidence calculation."""
        scorer = QualityScorer()
        result = scorer.score_sync(good_code_response, sample_coding_task)

        avg_conf = result.average_confidence
        assert 0.0 <= avg_conf <= 1.0

    def test_default_config(self):
        """Test default configuration."""
        scorer = QualityScorer()

        assert scorer.config.use_rules is True
        assert scorer.config.use_llm_judge is False

    def test_config_validation_llm_without_agent(self):
        """Test config validation requires agent for LLM judge."""
        with pytest.raises(ValueError, match="judge_agent is required"):
            QualityScorerConfig(use_llm_judge=True, judge_agent=None)

    def test_custom_dimension_weights(self, sample_coding_task, good_code_response):
        """Test scoring with custom dimension weights."""
        config = QualityScorerConfig(
            use_rules=True,
            dimension_weights={
                ScoringDimension.CORRECTNESS: 1.0,
                ScoringDimension.COMPLETENESS: 0.0,
                ScoringDimension.CODE_QUALITY: 0.0,
                ScoringDimension.EFFICIENCY: 0.0,
                ScoringDimension.SECURITY: 0.0,
            },
        )
        scorer = QualityScorer(config)

        result = scorer.score_sync(good_code_response, sample_coding_task)

        # With only correctness weighted, overall should be close to correctness score
        correctness_score = result.dimensions[ScoringDimension.CORRECTNESS].score
        assert abs(result.overall - correctness_score) < 0.01


# =============================================================================
# QualityScorer Aggregation Tests
# =============================================================================


class TestQualityScorerAggregation:
    """Test QualityScorer score aggregation."""

    def test_aggregate_with_default_weights(self):
        """Test aggregation with default weights."""
        scorer = QualityScorer()

        dimension_scores = [
            DimensionScore(
                dimension=ScoringDimension.CORRECTNESS,
                score=1.0,
                confidence=0.9,
                explanation="Perfect",
            ),
            DimensionScore(
                dimension=ScoringDimension.COMPLETENESS,
                score=0.8,
                confidence=0.8,
                explanation="Good",
            ),
            DimensionScore(
                dimension=ScoringDimension.CODE_QUALITY,
                score=0.6,
                confidence=0.7,
                explanation="Okay",
            ),
            DimensionScore(
                dimension=ScoringDimension.EFFICIENCY,
                score=0.4,
                confidence=0.6,
                explanation="Poor",
            ),
            DimensionScore(
                dimension=ScoringDimension.SECURITY,
                score=1.0,
                confidence=0.9,
                explanation="Secure",
            ),
        ]

        overall = scorer._aggregate_scores(dimension_scores)

        # Should be weighted average
        # Default: correctness=0.30, completeness=0.25, code_quality=0.20, efficiency=0.15, security=0.10
        expected = (1.0*0.30 + 0.8*0.25 + 0.6*0.20 + 0.4*0.15 + 1.0*0.10)
        assert abs(overall - expected) < 0.01

    def test_aggregate_empty_list(self):
        """Test aggregation with empty list."""
        scorer = QualityScorer()

        overall = scorer._aggregate_scores([])
        assert overall == 0.0


# =============================================================================
# LLMJudge Tests
# =============================================================================


class TestLLMJudge:
    """Test LLMJudge prompt building and parsing."""

    def test_default_templates_exist(self):
        """Test that default templates exist for all dimensions."""
        templates = JudgePromptTemplate.default_templates()

        for dimension in ScoringDimension:
            assert dimension in templates
            template = templates[dimension]
            assert template.dimension == dimension
            assert template.system_prompt
            assert template.evaluation_prompt
            assert template.rubric

    def test_build_judge_prompt(self, sample_coding_task):
        """Test building judge prompt."""
        mock_agent = MagicMock()
        judge = LLMJudge(agent=mock_agent)

        prompt = judge._build_judge_prompt(
            response="def fib(n): return n if n <= 1 else fib(n-1) + fib(n-2)",
            task=sample_coding_task,
            dimension=ScoringDimension.CORRECTNESS,
        )

        assert "CORRECTNESS" in prompt
        assert "Fibonacci" in prompt
        assert "fib" in prompt

    def test_build_judge_prompt_with_reference(self, sample_coding_task):
        """Test building judge prompt with reference solution."""
        mock_agent = MagicMock()
        judge = LLMJudge(agent=mock_agent)

        prompt = judge._build_judge_prompt(
            response="def fib(n): pass",
            task=sample_coding_task,
            dimension=ScoringDimension.CORRECTNESS,
            reference="def fib(n): return n if n <= 1 else fib(n-1) + fib(n-2)",
        )

        assert "Reference Solution" in prompt

    def test_parse_judge_response_json(self):
        """Test parsing well-formed JSON judge response."""
        mock_agent = MagicMock()
        judge = LLMJudge(agent=mock_agent)

        json_response = '''
Based on my evaluation:

{
    "score": 0.85,
    "confidence": 0.9,
    "explanation": "The solution correctly implements Fibonacci.",
    "issues": [],
    "strengths": ["Correct logic", "Good naming"]
}

Overall, good implementation.
'''

        score = judge._parse_judge_response(json_response, ScoringDimension.CORRECTNESS)

        assert score.score == 0.85
        assert score.confidence == 0.9
        assert "correctly" in score.explanation.lower()
        assert score.details is not None

    def test_parse_judge_response_fallback(self):
        """Test parsing unstructured judge response."""
        mock_agent = MagicMock()
        judge = LLMJudge(agent=mock_agent)

        text_response = "This solution scores 7/10. It has some issues but mostly works."

        score = judge._parse_judge_response(text_response, ScoringDimension.CORRECTNESS)

        assert 0.6 <= score.score <= 0.8  # 7/10 normalized
        assert score.confidence == 0.3  # Low confidence for fallback

    def test_extract_score_from_text_formats(self):
        """Test extracting scores from various text formats."""
        mock_agent = MagicMock()
        judge = LLMJudge(agent=mock_agent)

        # Score: X format
        assert abs(judge._extract_score_from_text("Score: 0.8") - 0.8) < 0.01

        # X/10 format
        assert abs(judge._extract_score_from_text("Rating: 8/10") - 0.8) < 0.01

        # X/100 format
        assert abs(judge._extract_score_from_text("Score: 85/100") - 0.85) < 0.01

        # X out of 10 format
        assert abs(judge._extract_score_from_text("I give this 7 out of 10") - 0.7) < 0.01

        # No score found
        assert judge._extract_score_from_text("No score here") == 0.5

    @pytest.mark.asyncio
    async def test_evaluate_with_mock_agent(self, sample_coding_task, good_code_response):
        """Test full evaluation with mock agent."""
        mock_agent = MagicMock()
        mock_agent.agenerate = AsyncMock(return_value=(
            '{"score": 0.9, "confidence": 0.85, "explanation": "Excellent implementation."}',
            100,
            MagicMock(),
        ))

        judge = LLMJudge(
            agent=mock_agent,
            dimensions=[ScoringDimension.CORRECTNESS],
        )

        scores = await judge.evaluate(good_code_response, sample_coding_task)

        assert len(scores) == 1
        assert scores[0].dimension == ScoringDimension.CORRECTNESS
        assert scores[0].score == 0.9
        mock_agent.agenerate.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_handles_errors(self, sample_coding_task):
        """Test evaluation handles agent errors gracefully."""
        mock_agent = MagicMock()
        mock_agent.agenerate = AsyncMock(side_effect=Exception("API Error"))

        judge = LLMJudge(
            agent=mock_agent,
            dimensions=[ScoringDimension.CORRECTNESS],
        )

        scores = await judge.evaluate("test response", sample_coding_task)

        assert len(scores) == 1
        # Should return fallback score on error
        assert scores[0].score == 0.5
        assert scores[0].confidence == 0.1
        assert "failed" in scores[0].explanation.lower()


# =============================================================================
# Integration Tests
# =============================================================================


class TestQualityScorerIntegration:
    """Integration tests for complete scoring workflow."""

    @pytest.mark.asyncio
    async def test_hybrid_scoring_with_mock_agent(self, sample_coding_task, good_code_response):
        """Test hybrid scoring combining rules and LLM judge."""
        mock_agent = MagicMock()
        mock_agent.agenerate = AsyncMock(return_value=(
            '{"score": 0.95, "confidence": 0.9, "explanation": "Excellent."}',
            100,
            MagicMock(),
        ))

        config = QualityScorerConfig(
            use_rules=True,
            use_llm_judge=True,
            dimensions=[ScoringDimension.CORRECTNESS],
            judge_agent=mock_agent,
        )
        scorer = QualityScorer(config)

        result = await scorer.score(good_code_response, sample_coding_task)

        assert result.method == "hybrid"
        # Hybrid should have combined details
        correctness = result.dimensions.get(ScoringDimension.CORRECTNESS)
        assert correctness is not None
        if correctness.details:
            assert "rule_score" in correctness.details or "llm_score" in correctness.details
