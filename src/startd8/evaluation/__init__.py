"""
Evaluation Module for StartD8 SDK

Provides task corpus management, loading, evaluation capabilities,
and quality scoring for benchmarking LLM agents across various
software development tasks.
"""

from .tasks import (
    # Enums
    Capability,
    TaskCategory,
    TaskDifficulty,
    # Models
    EvaluationCriteria,
    EvaluationRun,
    Task,
    TaskCorpus,
    TaskFilter,
    TaskResult,
    TaskVariable,
)
from .loader import (
    # Constants
    BUILTIN_CORPUS_DIR,
    USER_CORPUS_DIR,
    # Classes
    TaskLoader,
    # Functions
    load_default_corpus,
)
from .dimensions import (
    # Enums
    ScoringDimension,
    # Models
    DimensionScore,
)
from .rules import (
    RuleBasedScorer,
)
from .judges import (
    JudgePromptTemplate,
    LLMJudge,
)
from .scorer import (
    QualityScorer,
    QualityScorerConfig,
    QualityScore,
)

__all__ = [
    # Enums
    "Capability",
    "TaskCategory",
    "TaskDifficulty",
    "ScoringDimension",
    # Models
    "EvaluationCriteria",
    "EvaluationRun",
    "Task",
    "TaskCorpus",
    "TaskFilter",
    "TaskResult",
    "TaskVariable",
    "DimensionScore",
    # Loader
    "BUILTIN_CORPUS_DIR",
    "USER_CORPUS_DIR",
    "TaskLoader",
    "load_default_corpus",
    # Scoring
    "RuleBasedScorer",
    "JudgePromptTemplate",
    "LLMJudge",
    "QualityScorer",
    "QualityScorerConfig",
    "QualityScore",
]
