"""
Quality Scorer - Main Orchestration for Evaluation System

Provides the QualityScorer class that coordinates rule-based and
LLM-based evaluation strategies to produce comprehensive quality scores.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .dimensions import DimensionScore, ScoringDimension
from .judges import LLMJudge
from .rules import RuleBasedScorer
from .tasks import Task


@dataclass
class QualityScorerConfig:
    """
    Configuration for the QualityScorer.

    Attributes:
        use_rules: Whether to use rule-based scoring
        use_llm_judge: Whether to use LLM-based scoring
        dimensions: List of dimensions to evaluate
        dimension_weights: Custom weights for aggregating dimension scores
        judge_agent: BaseAgent to use for LLM judging (required if use_llm_judge=True)
    """
    use_rules: bool = True
    use_llm_judge: bool = False
    dimensions: List[ScoringDimension] = field(
        default_factory=lambda: list(ScoringDimension)
    )
    dimension_weights: Dict[ScoringDimension, float] = field(default_factory=dict)
    judge_agent: Optional[Any] = None  # BaseAgent type

    def __post_init__(self):
        """Validate configuration."""
        if self.use_llm_judge and self.judge_agent is None:
            raise ValueError("judge_agent is required when use_llm_judge=True")

        # Validate weights are in valid range
        for dimension, weight in self.dimension_weights.items():
            if not 0.0 <= weight <= 1.0:
                raise ValueError(
                    f"Weight for {dimension} must be between 0.0 and 1.0, got {weight}"
                )


@dataclass
class QualityScore:
    """
    Result of quality scoring for a response.

    Attributes:
        overall: Aggregated overall score (0.0-1.0)
        dimensions: Individual scores for each dimension
        method: Scoring method used ("rules", "llm_judge", "hybrid")
        timestamp: When the scoring was performed
    """
    overall: float
    dimensions: Dict[ScoringDimension, DimensionScore]
    method: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Validate overall score range."""
        if not 0.0 <= self.overall <= 1.0:
            raise ValueError(f"Overall score must be between 0.0 and 1.0, got {self.overall}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "overall": self.overall,
            "method": self.method,
            "timestamp": self.timestamp.isoformat(),
            "dimensions": {
                dim.value: {
                    "score": score.score,
                    "confidence": score.confidence,
                    "explanation": score.explanation,
                    "details": score.details,
                }
                for dim, score in self.dimensions.items()
            },
        }

    @property
    def average_confidence(self) -> float:
        """Calculate average confidence across dimensions."""
        if not self.dimensions:
            return 0.0
        return sum(s.confidence for s in self.dimensions.values()) / len(self.dimensions)


class QualityScorer:
    """
    Main quality scorer that orchestrates evaluation strategies.

    Supports three modes:
    - Rules only: Fast, deterministic scoring using pattern matching
    - LLM judge only: Semantic evaluation using an LLM
    - Hybrid: Combines rule-based and LLM-based scoring

    Example:
        >>> # Rule-based only (fast, no API calls)
        >>> scorer = QualityScorer()
        >>> score = scorer.score_sync(response, task)

        >>> # With LLM judge
        >>> from startd8.agents import ClaudeAgent
        >>> agent = ClaudeAgent(name="judge", model="claude-sonnet-4-6")
        >>> config = QualityScorerConfig(use_llm_judge=True, judge_agent=agent)
        >>> scorer = QualityScorer(config)
        >>> score = await scorer.score(response, task)

        >>> # Hybrid mode
        >>> config = QualityScorerConfig(
        ...     use_rules=True,
        ...     use_llm_judge=True,
        ...     judge_agent=agent
        ... )
        >>> scorer = QualityScorer(config)
        >>> score = await scorer.score(response, task)
    """

    # Default weights for dimensions (equal weighting)
    DEFAULT_WEIGHTS: Dict[ScoringDimension, float] = {
        ScoringDimension.CORRECTNESS: 0.30,
        ScoringDimension.COMPLETENESS: 0.25,
        ScoringDimension.CODE_QUALITY: 0.20,
        ScoringDimension.EFFICIENCY: 0.15,
        ScoringDimension.SECURITY: 0.10,
    }

    def __init__(self, config: Optional[QualityScorerConfig] = None):
        """
        Initialize the quality scorer.

        Args:
            config: Scorer configuration (defaults to rules-only)
        """
        self.config = config or QualityScorerConfig()

        # Initialize scorers based on config
        self._rule_scorer: Optional[RuleBasedScorer] = None
        self._llm_judge: Optional[LLMJudge] = None

        if self.config.use_rules:
            self._rule_scorer = RuleBasedScorer()

        if self.config.use_llm_judge:
            self._llm_judge = LLMJudge(
                agent=self.config.judge_agent,
                dimensions=self.config.dimensions,
            )

    async def score(
        self,
        response: str,
        task: Task,
        reference: Optional[str] = None,
    ) -> QualityScore:
        """
        Score a response using configured strategies.

        Args:
            response: Response text to evaluate
            task: Task definition
            reference: Optional reference solution for comparison

        Returns:
            QualityScore with overall and dimension scores
        """
        rule_scores: Dict[ScoringDimension, DimensionScore] = {}
        llm_scores: Dict[ScoringDimension, DimensionScore] = {}

        # Get rule-based scores
        if self._rule_scorer:
            rule_scores = self._rule_scorer.score_response(response, task)

        # Get LLM-based scores
        if self._llm_judge:
            llm_score_list = await self._llm_judge.evaluate(response, task, reference)
            llm_scores = {s.dimension: s for s in llm_score_list}

        # Combine scores based on method
        final_scores = self._combine_scores(rule_scores, llm_scores)

        # Calculate overall score
        overall = self._aggregate_scores(list(final_scores.values()))

        # Determine method
        method = self._determine_method()

        return QualityScore(
            overall=overall,
            dimensions=final_scores,
            method=method,
        )

    def score_sync(
        self,
        response: str,
        task: Task,
        reference: Optional[str] = None,
    ) -> QualityScore:
        """
        Synchronous version of score().

        Args:
            response: Response text to evaluate
            task: Task definition
            reference: Optional reference solution

        Returns:
            QualityScore with overall and dimension scores
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(self.score(response, task, reference))

        # Running inside an existing event loop
        import concurrent.futures
        import contextvars

        ctx = contextvars.copy_context()

        def _runner() -> QualityScore:
            return asyncio.run(self.score(response, task, reference))

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(ctx.run, _runner)
            return future.result()

    def _combine_scores(
        self,
        rule_scores: Dict[ScoringDimension, DimensionScore],
        llm_scores: Dict[ScoringDimension, DimensionScore],
    ) -> Dict[ScoringDimension, DimensionScore]:
        """
        Combine rule-based and LLM-based scores.

        In hybrid mode, uses confidence-weighted averaging.

        Args:
            rule_scores: Scores from rule-based evaluation
            llm_scores: Scores from LLM-based evaluation

        Returns:
            Combined dimension scores
        """
        # If only one source, return it
        if not llm_scores:
            return rule_scores
        if not rule_scores:
            return llm_scores

        # Hybrid: combine using confidence-weighted average
        combined: Dict[ScoringDimension, DimensionScore] = {}

        all_dimensions = set(rule_scores.keys()) | set(llm_scores.keys())

        for dimension in all_dimensions:
            rule_score = rule_scores.get(dimension)
            llm_score = llm_scores.get(dimension)

            if rule_score and llm_score:
                # Weighted average based on confidence
                total_conf = rule_score.confidence + llm_score.confidence
                if total_conf > 0:
                    weighted_score = (
                        rule_score.score * rule_score.confidence +
                        llm_score.score * llm_score.confidence
                    ) / total_conf
                    combined_confidence = (rule_score.confidence + llm_score.confidence) / 2
                else:
                    weighted_score = (rule_score.score + llm_score.score) / 2
                    combined_confidence = 0.5

                combined[dimension] = DimensionScore(
                    dimension=dimension,
                    score=weighted_score,
                    confidence=combined_confidence,
                    explanation=f"Hybrid: {rule_score.explanation} | {llm_score.explanation}",
                    details={
                        "rule_score": rule_score.score,
                        "rule_confidence": rule_score.confidence,
                        "llm_score": llm_score.score,
                        "llm_confidence": llm_score.confidence,
                    },
                )
            elif rule_score:
                combined[dimension] = rule_score
            elif llm_score:
                combined[dimension] = llm_score

        return combined

    def _aggregate_scores(self, dimension_scores: List[DimensionScore]) -> float:
        """
        Calculate weighted average of dimension scores.

        Uses configured weights or defaults to equal weighting.

        Args:
            dimension_scores: List of dimension scores to aggregate

        Returns:
            Aggregated overall score (0.0-1.0)
        """
        if not dimension_scores:
            return 0.0

        # Get weights (use configured or defaults)
        weights = self.config.dimension_weights or self.DEFAULT_WEIGHTS

        total_weight = 0.0
        weighted_sum = 0.0

        for score in dimension_scores:
            weight = weights.get(score.dimension, 1.0 / len(ScoringDimension))
            weighted_sum += score.score * weight
            total_weight += weight

        if total_weight == 0:
            return sum(s.score for s in dimension_scores) / len(dimension_scores)

        return weighted_sum / total_weight

    def _determine_method(self) -> str:
        """Determine the scoring method string based on configuration."""
        if self.config.use_rules and self.config.use_llm_judge:
            return "hybrid"
        elif self.config.use_llm_judge:
            return "llm_judge"
        else:
            return "rules"
