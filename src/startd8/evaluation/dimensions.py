"""
Scoring Dimension Definitions for Evaluation System

Defines the dimensions used to evaluate LLM responses and the data structures
for representing scores across those dimensions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ScoringDimension(str, Enum):
    """
    Dimensions for evaluating LLM response quality.

    Each dimension represents a different aspect of response quality
    that can be measured and scored independently.
    """
    CORRECTNESS = "correctness"      # Does it solve the problem?
    COMPLETENESS = "completeness"    # Are all requirements addressed?
    CODE_QUALITY = "code_quality"    # Style, readability, best practices
    EFFICIENCY = "efficiency"        # Algorithm complexity, performance
    SECURITY = "security"            # No vulnerabilities introduced


@dataclass
class DimensionScore:
    """
    Score for a single evaluation dimension.

    Represents the result of evaluating a response on one dimension,
    including the score, confidence level, explanation, and optional
    detailed breakdown.

    Attributes:
        dimension: The dimension being scored
        score: Score value between 0.0 and 1.0
        confidence: Confidence level in the score (0.0 to 1.0)
        explanation: Human-readable explanation of the score
        details: Optional dictionary with additional scoring details

    Example:
        >>> score = DimensionScore(
        ...     dimension=ScoringDimension.CORRECTNESS,
        ...     score=0.85,
        ...     confidence=0.9,
        ...     explanation="Solution correctly implements the algorithm"
        ... )
    """
    dimension: ScoringDimension
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    explanation: str
    details: Optional[Dict[str, Any]] = field(default=None)

    def __post_init__(self):
        """Validate score and confidence ranges."""
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {self.score}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        if not self.explanation:
            raise ValueError("Explanation cannot be empty")
