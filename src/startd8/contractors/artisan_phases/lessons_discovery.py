"""
Lessons Learned Discovery Phase for Startd8 Artisan Workflow System.

This module implements a discovery phase that queries historical lessons learned,
scores them by relevance to the current task context, filters by a configurable
threshold, categorizes by workflow phase, and caches results for the workflow duration.

Architecture:
    LessonsProvider (ABC) -> RelevanceScorer -> WorkflowCache -> LessonsDiscovery

All implementation uses Python stdlib only (no external dependencies).

Usage:
    >>> provider = InMemoryLessonsProvider([
    ...     Lesson(id="1", title="Use type hints", description="Always add type hints to Python code",
    ...            tags=["coding", "python"], phase="implementation"),
    ... ])
    >>> discovery = LessonsDiscovery(provider=provider, threshold=0.1)
    >>> result = discovery.discover(workflow_id="wf-001", context="python coding best practices")
    >>> for sl in result.ranked_lessons:
    ...     print(f"{sl.lesson.title}: {sl.relevance_score:.2f} ({sl.assigned_phase.value})")
"""

from __future__ import annotations

import abc
import enum
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import ClassVar, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================


class WorkflowPhase(enum.Enum):
    """Workflow phase enumeration for lesson categorization."""

    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    GENERAL = "general"


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass
class Lesson:
    """Represents a single lesson learned from past workflow executions.

    Attributes:
        id: Unique identifier for the lesson.
        title: Short summary of the lesson.
        description: Detailed description of the lesson content.
        tags: Optional keyword tags for improved matching.
        phase: Optional explicit workflow phase string (e.g. "planning").
        source: Optional source identifier (project name, author, etc.).
        created_at: Optional Unix timestamp of when the lesson was recorded.
    """

    id: str
    title: str
    description: str
    tags: List[str] = field(default_factory=list)
    phase: Optional[str] = None
    source: str = ""
    created_at: Optional[float] = None

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Lesson):
            return NotImplemented
        return self.id == other.id


@dataclass
class ScoredLesson:
    """A lesson annotated with its relevance score and assigned phase.

    Attributes:
        lesson: The underlying Lesson object.
        relevance_score: Computed relevance score in [0.0, 1.0].
        matched_keywords: Context keywords that matched lesson content.
        assigned_phase: Workflow phase determined by categorization logic.
    """

    lesson: Lesson
    relevance_score: float
    matched_keywords: List[str] = field(default_factory=list)
    assigned_phase: WorkflowPhase = WorkflowPhase.GENERAL


@dataclass
class DiscoveryResult:
    """Result of a lessons discovery operation.

    Attributes:
        workflow_id: The workflow that requested discovery.
        context: The task context string used for matching.
        threshold_used: The relevance threshold that was applied.
        total_lessons_queried: Number of unique lessons retrieved from the provider.
        total_lessons_after_filter: Number of lessons that passed the threshold filter.
        lessons_by_phase: Lessons grouped by their assigned WorkflowPhase.
        ranked_lessons: All qualifying lessons sorted by descending relevance score.
        cached: Whether this result was served from cache.
        timestamp: Unix timestamp of when the result was produced.
    """

    workflow_id: str
    context: str
    threshold_used: float
    total_lessons_queried: int
    total_lessons_after_filter: int
    lessons_by_phase: Dict[WorkflowPhase, List[ScoredLesson]] = field(
        default_factory=dict
    )
    ranked_lessons: List[ScoredLesson] = field(default_factory=list)
    cached: bool = False
    timestamp: float = field(default_factory=time.time)


# ============================================================================
# Provider Protocol / Abstract Base
# ============================================================================


class LessonsProvider(abc.ABC):
    """Abstract base class for lesson data providers.

    Implement this to integrate with databases, filesystems, APIs, or any
    other backing store for historical lessons learned.
    """

    @abc.abstractmethod
    def get_lessons(self, context: str = "") -> List[Lesson]:
        """Retrieve available lessons, optionally pre-filtered by *context*.

        Args:
            context: An optional context hint the provider may use for server-side
                     filtering.  Implementations are free to ignore it.

        Returns:
            List of :class:`Lesson` objects.
        """


# ============================================================================
# Default Provider Implementation
# ============================================================================


class InMemoryLessonsProvider(LessonsProvider):
    """In-memory implementation of :class:`LessonsProvider`.

    Suitable for testing, prototyping, and small-scale deployments where
    lessons can be held entirely in memory.
    """

    def __init__(self, lessons: Optional[List[Lesson]] = None) -> None:
        self._lessons: List[Lesson] = list(lessons) if lessons else []

    # -- Mutation helpers -----------------------------------------------------

    def add_lesson(self, lesson: Lesson) -> None:
        """Append a single lesson."""
        self._lessons.append(lesson)

    def add_lessons(self, lessons: List[Lesson]) -> None:
        """Append multiple lessons."""
        self._lessons.extend(lessons)

    # -- Provider interface ---------------------------------------------------

    def get_lessons(self, context: str = "") -> List[Lesson]:
        """Return all stored lessons (context parameter is ignored)."""
        return list(self._lessons)


# ============================================================================
# Relevance Scoring
# ============================================================================


class RelevanceScorer:
    """Computes relevance scores between a task context and candidate lessons.

    Scoring uses a Dice coefficient on tokenised text with additive boosts for
    exact tag matches and phase-keyword overlap.  The resulting score is in
    [0.0, 1.0].
    """

    # Common English stop-words excluded during tokenization.
    STOPWORDS: ClassVar[frozenset] = frozenset(
        {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "it", "as", "be",
            "was", "were", "are", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should", "may",
            "might", "shall", "can", "this", "that", "these", "those", "we",
            "they", "he", "she", "i", "you", "my", "your", "his", "her",
            "its", "our", "their", "not", "no", "if", "then", "else",
            "when", "where", "how", "what", "which", "who", "whom", "all",
            "each", "every", "both", "few", "more", "most", "other", "some",
            "such", "than", "too", "very", "just", "about", "need", "also",
            "up", "out", "so",
        }
    )

    # Phase-specific keywords for phase inference.
    PHASE_KEYWORDS: ClassVar[Dict[WorkflowPhase, Set[str]]] = {
        WorkflowPhase.PLANNING: {
            "plan", "design", "architect", "architecture", "requirement",
            "requirements", "scope", "estimate", "strategy",
        },
        WorkflowPhase.IMPLEMENTATION: {
            "implement", "implementation", "code", "coding", "develop",
            "development", "build", "building", "refactor", "refactoring",
            "integrate", "integration", "feature",
        },
        WorkflowPhase.TESTING: {
            "test", "testing", "qa", "quality", "bug", "regression",
            "validation", "validate", "verify", "verification", "check",
        },
        WorkflowPhase.DEPLOYMENT: {
            "deploy", "deployment", "release", "ci/cd", "cicd", "pipeline",
            "infrastructure", "rollback", "production", "prod", "launch",
        },
    }

    # ------------------------------------------------------------------
    # Tokenization
    # ------------------------------------------------------------------

    @staticmethod
    def tokenize(text: str) -> Set[str]:
        """Tokenize *text* into a set of lower-case words, excluding stop-words.

        Args:
            text: Raw text to tokenize.

        Returns:
            Set of lower-case word tokens with stop-words removed.
        """
        tokens = re.findall(r"\b\w+\b", text.lower())
        return {t for t in tokens if t not in RelevanceScorer.STOPWORDS}

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def compute_score(
        context_tokens: Set[str], lesson: Lesson
    ) -> Tuple[float, List[str]]:
        """Compute relevance between pre-tokenized context and a lesson.

        The base score is the Dice coefficient between the two token sets.
        Additive boosts (capped at 1.0) are applied for:
        * Exact tag overlap with context tokens (+0.10).
        * Shared phase-keyword presence in both context and lesson (+0.05).

        Args:
            context_tokens: Tokenized context keywords.
            lesson: The :class:`Lesson` to score.

        Returns:
            ``(score, matched_keywords)`` where *score* ∈ [0.0, 1.0] and
            *matched_keywords* is a sorted list of overlapping tokens.
        """
        lesson_text = f"{lesson.title} {lesson.description} {' '.join(lesson.tags)}"
        lesson_tokens = RelevanceScorer.tokenize(lesson_text)

        if not context_tokens or not lesson_tokens:
            return 0.0, []

        overlap = context_tokens & lesson_tokens
        matched = sorted(overlap)

        # Dice coefficient
        score = (2.0 * len(overlap)) / (len(context_tokens) + len(lesson_tokens))

        # Boost: exact tag match
        tag_tokens = {tag.lower().strip() for tag in lesson.tags}
        if tag_tokens & context_tokens:
            score = min(score + 0.10, 1.0)

        # Boost: shared phase-keyword presence
        for _phase, keywords in RelevanceScorer.PHASE_KEYWORDS.items():
            if keywords & context_tokens and keywords & lesson_tokens:
                score = min(score + 0.05, 1.0)
                break

        return round(score, 4), matched

    # ------------------------------------------------------------------
    # Phase categorization
    # ------------------------------------------------------------------

    @staticmethod
    def categorize(lesson: Lesson, context_tokens: Set[str]) -> WorkflowPhase:
        """Determine the workflow phase for *lesson*.

        If the lesson carries an explicit ``phase`` field matching a known
        :class:`WorkflowPhase`, that value is used directly.  Otherwise the
        phase is inferred from keyword overlap with lesson content.

        Args:
            lesson: The lesson to categorize.
            context_tokens: Tokenized context (unused in current logic but
                available for future inference heuristics).

        Returns:
            The assigned :class:`WorkflowPhase`.
        """
        # Prefer explicit phase when valid
        if lesson.phase:
            phase_lower = lesson.phase.lower().strip()
            for phase in WorkflowPhase:
                if phase.value == phase_lower:
                    return phase

        # Infer from lesson content
        lesson_text = f"{lesson.title} {lesson.description} {' '.join(lesson.tags)}"
        lesson_tokens = RelevanceScorer.tokenize(lesson_text)

        best_phase = WorkflowPhase.GENERAL
        best_count = 0
        for phase, keywords in RelevanceScorer.PHASE_KEYWORDS.items():
            count = len(keywords & lesson_tokens)
            if count > best_count:
                best_count = count
                best_phase = phase

        return best_phase


# ============================================================================
# Workflow Cache
# ============================================================================


class WorkflowCache:
    """Workflow-scoped cache with TTL-based expiry.

    Each entry is keyed by ``(workflow_id, context)`` and expires after *ttl*
    seconds.

    .. warning::
        This implementation is **not** thread-safe.  Wrap calls with a
        ``threading.RLock`` if used from multiple threads, or subclass and
        override the public methods with appropriate locking.
    """

    def __init__(self, ttl: float = 3600.0) -> None:
        """
        Args:
            ttl: Time-to-live in seconds for cache entries (default: 3600).
        """
        if ttl <= 0:
            raise ValueError(f"Cache TTL must be positive, got {ttl}")
        self._ttl = ttl
        self._store: Dict[str, Tuple[float, DiscoveryResult]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(workflow_id: str, context: str) -> str:
        """Produce a deterministic cache key from workflow ID and context."""
        context_hash = hashlib.sha256(context.encode("utf-8")).hexdigest()[:16]
        return f"{workflow_id}::{context_hash}"

    def _evict_expired(self) -> None:
        """Remove all entries whose TTL has elapsed."""
        now = time.time()
        expired = [
            k for k, (ts, _) in self._store.items() if (now - ts) > self._ttl
        ]
        for k in expired:
            del self._store[k]
        if expired:
            logger.debug("Evicted %d expired cache entries", len(expired))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, workflow_id: str, context: str) -> Optional[DiscoveryResult]:
        """Retrieve a cached result if present and not expired.

        Args:
            workflow_id: Workflow identifier.
            context: Task context string.

        Returns:
            The cached :class:`DiscoveryResult`, or ``None`` on miss / expiry.
        """
        self._evict_expired()
        key = self._make_key(workflow_id, context)

        entry = self._store.get(key)
        if entry is None:
            logger.debug("Cache miss: %s", key)
            return None

        timestamp, result = entry
        age = time.time() - timestamp
        if age > self._ttl:
            logger.debug("Cache expired: %s (age=%.1fs)", key, age)
            del self._store[key]
            return None

        logger.debug("Cache hit: %s (age=%.1fs)", key, age)
        return result

    def put(self, workflow_id: str, context: str, result: DiscoveryResult) -> None:
        """Store a discovery result in the cache.

        Args:
            workflow_id: Workflow identifier.
            context: Task context string.
            result: The :class:`DiscoveryResult` to cache.
        """
        key = self._make_key(workflow_id, context)
        self._store[key] = (time.time(), result)
        logger.debug("Cached result: %s", key)

    def invalidate(self, workflow_id: str) -> int:
        """Remove all cache entries belonging to *workflow_id*.

        Returns:
            Number of entries removed.
        """
        prefix = f"{workflow_id}::"
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        if keys:
            logger.debug("Invalidated %d entries for workflow %s", len(keys), workflow_id)
        return len(keys)

    def clear_all(self) -> None:
        """Drop every entry in the cache."""
        count = len(self._store)
        self._store.clear()
        logger.debug("Cleared all %d cache entries", count)

    @property
    def size(self) -> int:
        """Return the current number of (possibly expired) entries."""
        return len(self._store)


# ============================================================================
# Main Orchestrator
# ============================================================================


class LessonsDiscovery:
    """Main orchestrator for the lessons-learned discovery phase.

    Coordinates the full pipeline:
    1. **Cache check** — return cached result if available.
    2. **Query** — retrieve lessons from the configured :class:`LessonsProvider`.
    3. **Deduplicate** — remove duplicate lesson IDs.
    4. **Score & rank** — compute relevance scores against the task context.
    5. **Filter** — discard lessons below the relevance threshold.
    6. **Categorize** — assign each surviving lesson to a :class:`WorkflowPhase`.
    7. **Cache & return** — store the result and hand it back to the caller.
    """

    DEFAULT_THRESHOLD: ClassVar[float] = 0.50

    def __init__(
        self,
        provider: LessonsProvider,
        threshold: float = DEFAULT_THRESHOLD,
        cache_ttl: float = 3600.0,
        cache: Optional[WorkflowCache] = None,
    ) -> None:
        """
        Args:
            provider: A :class:`LessonsProvider` implementation.
            threshold: Relevance score threshold in [0.0, 1.0] (default: 0.50).
            cache_ttl: Cache time-to-live in seconds (default: 3600).
            cache: Optional pre-built :class:`WorkflowCache`.  A new one is
                   created if not supplied.

        Raises:
            ValueError: If *threshold* is outside [0.0, 1.0].
        """
        self._provider = provider
        self._cache = cache or WorkflowCache(ttl=cache_ttl)
        self._scorer = RelevanceScorer()
        self.threshold = threshold  # uses property setter

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def threshold(self) -> float:
        """Current relevance threshold."""
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"Threshold must be in [0.0, 1.0], got {value}")
        self._threshold = value

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    def discover(
        self,
        workflow_id: str,
        context: str,
        use_cache: bool = True,
    ) -> DiscoveryResult:
        """Execute the lessons-learned discovery pipeline.

        Args:
            workflow_id: Unique workflow identifier.
            context: Task context description to match against lessons.
            use_cache: Check cache before querying the provider (default: True).

        Returns:
            A :class:`DiscoveryResult` containing ranked and categorized lessons.
        """
        # 1. Cache check
        if use_cache:
            cached = self._cache.get(workflow_id, context)
            if cached is not None:
                cached.cached = True
                return cached

        # 2. Query provider
        raw_lessons = self._provider.get_lessons(context=context)
        logger.info("Queried %d lessons from provider", len(raw_lessons))

        # 3. Deduplicate
        seen_ids: Set[str] = set()
        unique_lessons: List[Lesson] = []
        for lesson in raw_lessons:
            if lesson.id not in seen_ids:
                unique_lessons.append(lesson)
                seen_ids.add(lesson.id)

        dedup_count = len(raw_lessons) - len(unique_lessons)
        if dedup_count:
            logger.debug("Deduplicated %d duplicate lessons", dedup_count)

        # 4. Tokenize context once
        context_tokens = self._scorer.tokenize(context)
        logger.debug("Context tokens (%d): %s", len(context_tokens), context_tokens)

        if len(unique_lessons) > 10_000:
            logger.warning(
                "Large lesson set (%d lessons); scoring may be slow",
                len(unique_lessons),
            )

        # 5. Score, filter, categorize
        scored_lessons: List[ScoredLesson] = []
        for lesson in unique_lessons:
            score, matched = self._scorer.compute_score(context_tokens, lesson)
            if score >= self._threshold:
                phase = self._scorer.categorize(lesson, context_tokens)
                scored_lessons.append(
                    ScoredLesson(
                        lesson=lesson,
                        relevance_score=score,
                        matched_keywords=matched,
                        assigned_phase=phase,
                    )
                )

        logger.info(
            "Filtered to %d lessons (threshold=%.2f)",
            len(scored_lessons),
            self._threshold,
        )

        # 6. Rank by descending relevance; stable sort preserves insertion order
        #    for equal scores.
        ranked = sorted(scored_lessons, key=lambda sl: sl.relevance_score, reverse=True)

        # 7. Group by phase (preserve ordering within each group)
        by_phase: Dict[WorkflowPhase, List[ScoredLesson]] = {
            phase: [] for phase in WorkflowPhase
        }
        for sl in ranked:
            by_phase[sl.assigned_phase].append(sl)

        # 8. Build result
        result = DiscoveryResult(
            workflow_id=workflow_id,
            context=context,
            threshold_used=self._threshold,
            total_lessons_queried=len(unique_lessons),
            total_lessons_after_filter=len(ranked),
            lessons_by_phase=by_phase,
            ranked_lessons=ranked,
            cached=False,
        )

        # 9. Cache for workflow duration
        self._cache.put(workflow_id, context, result)

        return result

    # ------------------------------------------------------------------
    # Cache management helpers
    # ------------------------------------------------------------------

    def invalidate_cache(self, workflow_id: str) -> int:
        """Remove all cached results for *workflow_id*.

        Returns:
            Number of cache entries removed.
        """
        count = self._cache.invalidate(workflow_id)
        logger.info("Invalidated %d cache entries for workflow %s", count, workflow_id)
        return count

    def clear_cache(self) -> None:
        """Drop all cached results across all workflows."""
        self._cache.clear_all()
        logger.info("Cleared entire lessons discovery cache")


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    "WorkflowPhase",
    "Lesson",
    "ScoredLesson",
    "DiscoveryResult",
    "LessonsProvider",
    "InMemoryLessonsProvider",
    "RelevanceScorer",
    "WorkflowCache",
    "LessonsDiscovery",
]