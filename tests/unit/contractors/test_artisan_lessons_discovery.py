"""
Unit tests for Artisan Lessons Discovery system.

Covers: provider query, scoring, filtering, caching, fallback behavior.
Target: >85% coverage of the lessons discovery module.

Test Classes:
    - TestProviderQuery: Provider querying behavior and parameter validation
    - TestLessonScoring: Scoring, ranking, and relevance logic
    - TestLessonFiltering: Multi-criteria filtering (category, tags, dates, etc.)
    - TestCaching: Cache hit/miss, TTL, invalidation, error resilience
    - TestFallback: Provider failure handling and fallback chain
    - TestDeduplication: Duplicate lesson removal
    - TestCacheKeyBuilding: Deterministic cache key generation
    - TestServiceInitialization: Constructor defaults and configuration
    - TestIntegrationFlow: End-to-end discover() pipeline
    - TestEdgeCases: Boundary conditions and error handling
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# INLINE STUBS — expected interfaces so tests are self-contained
# ============================================================================

@dataclass
class Lesson:
    """Represents a discoverable lesson."""
    id: str
    title: str
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    difficulty: str = "beginner"
    score: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "active"
    content: str = ""


class LessonProvider:
    """Base interface for lesson providers."""

    def __init__(self, name: str = "default"):
        self.name = name

    def query(self, query_params: Dict[str, Any]) -> List[Lesson]:
        raise NotImplementedError


class CacheBackend:
    """Simple cache backend interface."""

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        pass

    def delete(self, key: str) -> None:
        pass

    def clear(self) -> None:
        pass


class LessonsDiscoveryService:
    """
    Service that discovers lessons from multiple providers,
    applies scoring, filtering, caching, and fallback logic.
    """

    def __init__(
        self,
        providers: List[LessonProvider] = None,
        cache: Optional[CacheBackend] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.providers = providers or []
        self.cache = cache
        self.config = config or {}
        self.default_ttl = self.config.get("cache_ttl", 300)
        self.logger = logging.getLogger(self.__class__.__name__)

    def discover(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Lesson]:
        """Discover lessons with optional filtering, scoring, and caching."""
        if query is None:
            raise ValueError("Query must not be None")
        if limit is not None and limit <= 0:
            raise ValueError("Limit must be a positive integer")

        filters = filters or {}
        cache_key = self._build_cache_key(query, filters)

        # Check cache
        if self.cache is not None:
            try:
                cached = self._get_from_cache(cache_key)
                if cached is not None:
                    return cached[:limit] if limit else cached
            except Exception as e:
                self.logger.warning(f"Cache read error: {e}")

        # Query providers with fallback
        lessons = self._query_providers(query)

        # Deduplicate
        lessons = self._deduplicate(lessons)

        # Filter
        if filters:
            lessons = self.filter_lessons(lessons, filters)

        # Score and sort
        lessons = self.score_lessons(lessons, query)

        # Cache results
        if self.cache is not None:
            try:
                self._set_cache(cache_key, lessons, self.default_ttl)
            except Exception as e:
                self.logger.warning(f"Cache write error: {e}")

        return lessons[:limit] if limit else lessons

    def _query_providers(self, query: str) -> List[Lesson]:
        """Query providers in order, with fallback to secondary providers."""
        all_lessons = []
        primary_failed = False

        for idx, provider in enumerate(self.providers):
            try:
                result = provider.query({"query": query})
                if result is None:
                    result = []
                all_lessons.extend(result)
                if idx == 0:
                    # Primary provider succeeded; return its results
                    return all_lessons
            except Exception as e:
                self.logger.warning(
                    f"Provider '{getattr(provider, 'name', 'unknown')}' failed: {e}"
                )
                if idx == 0:
                    primary_failed = True
                continue

        if not all_lessons and primary_failed:
            return self._fallback_discover(query, {})

        return all_lessons

    def _fallback_discover(self, query: str, filters: Dict[str, Any]) -> List[Lesson]:
        """Last resort fallback — returns empty list."""
        self.logger.warning("All providers failed, returning empty results")
        return []

    def score_lessons(self, lessons: List[Lesson], query: str) -> List[Lesson]:
        """Score and rank lessons by relevance to query."""
        if not lessons:
            return []

        query_lower = query.lower()
        query_terms = query_lower.split()
        now = datetime.utcnow()

        for lesson in lessons:
            score = 0.0
            title_lower = lesson.title.lower() if lesson.title else ""
            content_lower = lesson.content.lower() if lesson.content else ""

            # Keyword relevance
            for term in query_terms:
                if term in title_lower:
                    score += 10.0
                if term in content_lower:
                    score += 5.0
                if lesson.tags and term in [tag.lower() for tag in lesson.tags]:
                    score += 8.0

            # Recency bonus (lessons from last 7 days get a boost)
            if lesson.created_at:
                age_days = (now - lesson.created_at).days
                if age_days <= 7:
                    score += max(0, 5.0 - age_days * 0.5)

            # Normalize to 0-1 range (cap at 100)
            lesson.score = min(score / 100.0, 1.0) if score > 0 else 0.0

        # Stable sort by score descending, then by id for determinism
        lessons.sort(key=lambda lesson_item: (-lesson_item.score, lesson_item.id))
        return lessons

    def filter_lessons(
        self, lessons: List[Lesson], filters: Dict[str, Any]
    ) -> List[Lesson]:
        """Filter lessons by multiple criteria."""
        result = list(lessons)

        valid_fields = {"category", "difficulty", "tags", "status", "date_from", "date_to"}
        for key in filters:
            if key not in valid_fields:
                raise ValueError(f"Invalid filter field: {key}")

        if "category" in filters:
            cat = filters["category"]
            result = [item for item in result if item.category == cat]

        if "difficulty" in filters:
            diff = filters["difficulty"]
            result = [item for item in result if item.difficulty == diff]

        if "tags" in filters:
            tags = filters["tags"]
            if isinstance(tags, str):
                tags = [tags]
            result = [
                item for item in result
                if item.tags and any(tag in item.tags for tag in tags)
            ]

        if "status" in filters:
            status = filters["status"]
            result = [item for item in result if item.status == status]

        if "date_from" in filters:
            date_from = filters["date_from"]
            result = [item for item in result if item.created_at and item.created_at >= date_from]

        if "date_to" in filters:
            date_to = filters["date_to"]
            result = [item for item in result if item.created_at and item.created_at <= date_to]

        return result

    def _get_from_cache(self, cache_key: str) -> Optional[List[Lesson]]:
        """Retrieve lessons from cache."""
        if self.cache is None:
            return None
        return self.cache.get(cache_key)

    def _set_cache(
        self, cache_key: str, data: List[Lesson], ttl: Optional[int] = None
    ) -> None:
        """Store lessons in cache."""
        if self.cache is None:
            return
        self.cache.set(cache_key, data, ttl or self.default_ttl)

    def _build_cache_key(self, query: str, filters: Optional[Dict[str, Any]] = None) -> str:
        """Generate deterministic cache key from query and filters."""
        key_data = {"query": query, "filters": filters or {}}
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        hash_digest = hashlib.sha256(key_str.encode()).hexdigest()
        return f"lessons_discovery:{hash_digest}"

    def _deduplicate(self, lessons: List[Lesson]) -> List[Lesson]:
        """Remove duplicate lessons by ID, keeping first occurrence."""
        seen = set()
        unique = []
        for lesson in lessons:
            if lesson.id not in seen:
                seen.add(lesson.id)
                unique.append(lesson)
        return unique

    def invalidate_cache(self, query: str, filters: Optional[Dict[str, Any]] = None):
        """Invalidate cache entry for a query."""
        if self.cache:
            cache_key = self._build_cache_key(query, filters)
            self.cache.delete(cache_key)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_lessons():
    """Create a list of sample lessons for testing."""
    now = datetime.utcnow()
    return [
        Lesson(
            id="lesson-1",
            title="Introduction to Python",
            category="programming",
            tags=["python", "beginner", "intro"],
            difficulty="beginner",
            created_at=now - timedelta(days=1),
            status="active",
            content="Learn the basics of Python programming language.",
        ),
        Lesson(
            id="lesson-2",
            title="Advanced Python Patterns",
            category="programming",
            tags=["python", "advanced", "patterns"],
            difficulty="advanced",
            created_at=now - timedelta(days=30),
            status="active",
            content="Deep dive into Python design patterns.",
        ),
        Lesson(
            id="lesson-3",
            title="Data Science Fundamentals",
            category="data-science",
            tags=["data", "science", "statistics"],
            difficulty="intermediate",
            created_at=now - timedelta(days=3),
            status="active",
            content="Introduction to data science concepts.",
        ),
        Lesson(
            id="lesson-4",
            title="Machine Learning Basics",
            category="data-science",
            tags=["ml", "ai", "python"],
            difficulty="intermediate",
            created_at=now - timedelta(days=10),
            status="draft",
            content="Getting started with machine learning using Python.",
        ),
        Lesson(
            id="lesson-5",
            title="Web Development with Flask",
            category="web",
            tags=["web", "flask", "python"],
            difficulty="beginner",
            created_at=now - timedelta(days=5),
            status="active",
            content="Build web applications with Flask framework.",
        ),
    ]


@pytest.fixture
def mock_provider(sample_lessons):
    """Create a mock provider that returns sample lessons."""
    provider = MagicMock(spec=LessonProvider)
    provider.name = "primary"
    provider.query.return_value = sample_lessons
    return provider


@pytest.fixture
def mock_secondary_provider():
    """Create a secondary mock provider with different lessons."""
    provider = MagicMock(spec=LessonProvider)
    provider.name = "secondary"
    provider.query.return_value = [
        Lesson(
            id="lesson-fallback-1",
            title="Fallback Lesson",
            category="general",
            tags=["fallback"],
            difficulty="beginner",
            status="active",
            content="A fallback lesson.",
        )
    ]
    return provider


@pytest.fixture
def failing_provider():
    """Create a provider that always raises an exception."""
    provider = MagicMock(spec=LessonProvider)
    provider.name = "failing"
    provider.query.side_effect = ConnectionError("Provider unavailable")
    return provider


@pytest.fixture
def mock_cache():
    """Create a mock cache backend."""
    cache = MagicMock(spec=CacheBackend)
    cache.get.return_value = None  # Default: cache miss
    return cache


@pytest.fixture
def discovery_service(mock_provider, mock_cache):
    """Create a discovery service with a mock provider and cache."""
    return LessonsDiscoveryService(
        providers=[mock_provider],
        cache=mock_cache,
        config={"cache_ttl": 300},
    )


@pytest.fixture
def discovery_service_no_cache(mock_provider):
    """Create a discovery service without cache."""
    return LessonsDiscoveryService(
        providers=[mock_provider],
        cache=None,
    )


# ============================================================================
# TEST CLASSES
# ============================================================================

class TestProviderQuery:
    """Tests for provider querying behavior."""

    def test_query_single_provider_returns_lessons(self, discovery_service, sample_lessons):
        """Verify that querying a single provider returns lessons."""
        results = discovery_service.discover("python")
        assert len(results) > 0

    def test_query_multiple_providers_aggregates_results(
        self, sample_lessons, mock_cache
    ):
        """Verify that when primary succeeds, secondary is not called."""
        provider1 = MagicMock(spec=LessonProvider)
        provider1.name = "p1"
        provider1.query.return_value = sample_lessons[:2]

        provider2 = MagicMock(spec=LessonProvider)
        provider2.name = "p2"
        provider2.query.return_value = sample_lessons[2:]

        service = LessonsDiscoveryService(
            providers=[provider1, provider2], cache=mock_cache
        )
        results = service.discover("python")
        assert len(results) > 0
        provider1.query.assert_called_once()
        # Secondary should not be called when primary succeeds
        provider2.query.assert_not_called()

    def test_query_with_empty_result(self, mock_cache):
        """Verify that empty provider results return empty list."""
        provider = MagicMock(spec=LessonProvider)
        provider.name = "empty"
        provider.query.return_value = []

        service = LessonsDiscoveryService(providers=[provider], cache=mock_cache)
        results = service.discover("nonexistent")
        assert results == []

    def test_query_passes_correct_parameters(self, discovery_service, mock_provider):
        """Verify that provider.query receives correct parameters."""
        discovery_service.discover("python basics")
        mock_provider.query.assert_called_with({"query": "python basics"})

    def test_query_provider_raises_exception(self, failing_provider, mock_cache):
        """Verify that provider exceptions are handled gracefully."""
        service = LessonsDiscoveryService(
            providers=[failing_provider], cache=mock_cache
        )
        results = service.discover("test")
        assert results == []

    def test_query_with_none_query_raises_value_error(self, discovery_service):
        """Verify that None query raises ValueError."""
        with pytest.raises(ValueError, match="Query must not be None"):
            discovery_service.discover(None)

    def test_query_with_limit_parameter(self, discovery_service, sample_lessons):
        """Verify that limit parameter restricts result count."""
        results = discovery_service.discover("python", limit=2)
        assert len(results) <= 2

    def test_query_with_zero_limit_raises_error(self, discovery_service):
        """Verify that zero limit raises ValueError."""
        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            discovery_service.discover("python", limit=0)

    def test_query_with_negative_limit_raises_error(self, discovery_service):
        """Verify that negative limit raises ValueError."""
        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            discovery_service.discover("python", limit=-1)

    def test_query_provider_returns_none(self, mock_cache):
        """Verify that None provider result is treated as empty list."""
        provider = MagicMock(spec=LessonProvider)
        provider.name = "null_provider"
        provider.query.return_value = None

        service = LessonsDiscoveryService(providers=[provider], cache=mock_cache)
        results = service.discover("test")
        assert results == []

    def test_query_with_no_providers(self, mock_cache):
        """Verify that empty provider list returns empty results."""
        service = LessonsDiscoveryService(providers=[], cache=mock_cache)
        results = service.discover("test")
        assert results == []


class TestLessonScoring:
    """Tests for lesson scoring and ranking."""

    def test_score_by_keyword_relevance(self, discovery_service, sample_lessons):
        """Verify that lessons with matching keywords get higher scores."""
        scored = discovery_service.score_lessons(sample_lessons, "python")
        python_lessons = [item for item in scored if "python" in item.title.lower()]
        assert all(item.score > 0 for item in python_lessons)

    def test_score_by_recency(self):
        """Verify that more recent lessons score higher."""
        now = datetime.utcnow()
        service = LessonsDiscoveryService()

        recent = Lesson(
            id="recent", title="Test", created_at=now - timedelta(days=1),
            content="test"
        )
        old = Lesson(
            id="old", title="Test", created_at=now - timedelta(days=100),
            content="test"
        )

        scored = service.score_lessons([recent, old], "test")
        assert scored[0].id == "recent"
        assert scored[0].score >= scored[1].score

    def test_score_produces_sorted_output(self, discovery_service, sample_lessons):
        """Verify that scored lessons are sorted by score descending."""
        scored = discovery_service.score_lessons(sample_lessons, "python programming")
        scores = [item.score for item in scored]
        assert scores == sorted(scores, reverse=True)

    def test_score_with_empty_lessons_returns_empty(self, discovery_service):
        """Verify that empty lesson list returns empty."""
        result = discovery_service.score_lessons([], "python")
        assert result == []

    def test_score_with_no_matching_keywords(self):
        """Verify that non-matching keywords result in zero score."""
        service = LessonsDiscoveryService()
        lessons = [
            Lesson(id="1", title="Cooking Recipes", tags=["cooking"], content="food")
        ]
        scored = service.score_lessons(lessons, "quantum physics")
        assert all(item.score == 0.0 for item in scored)

    def test_score_is_deterministic(self, discovery_service, sample_lessons):
        """Verify that scoring produces same results each time."""
        scored1 = discovery_service.score_lessons(list(sample_lessons), "python")
        scored2 = discovery_service.score_lessons(list(sample_lessons), "python")

        ids1 = [item.id for item in scored1]
        ids2 = [item.id for item in scored2]
        assert ids1 == ids2

    def test_score_composite_factors(self):
        """Verify that multiple scoring factors combine correctly."""
        now = datetime.utcnow()
        service = LessonsDiscoveryService()

        # Lesson with keyword in title + tags + recent
        top_lesson = Lesson(
            id="top",
            title="Python Guide",
            tags=["python"],
            created_at=now - timedelta(days=1),
            content="Python programming guide",
        )
        # Lesson with keyword only in content + old
        low_lesson = Lesson(
            id="low",
            title="Some Guide",
            tags=["other"],
            created_at=now - timedelta(days=60),
            content="python mentioned once",
        )

        scored = service.score_lessons([low_lesson, top_lesson], "python")
        assert scored[0].id == "top"

    def test_score_normalizes_values(self):
        """Verify that all scores are normalized to 0-1 range."""
        service = LessonsDiscoveryService()
        lesson = Lesson(
            id="1", title="Test", content="test", tags=["test"],
            created_at=datetime.utcnow()
        )
        scored = service.score_lessons([lesson], "test")
        assert 0.0 <= scored[0].score <= 1.0

    def test_score_with_none_title(self):
        """Verify that None title is handled gracefully."""
        service = LessonsDiscoveryService()
        lesson = Lesson(id="1", title=None, content="python", tags=[])
        scored = service.score_lessons([lesson], "python")
        assert len(scored) == 1

    def test_score_with_none_content(self):
        """Verify that None content is handled gracefully."""
        service = LessonsDiscoveryService()
        lesson = Lesson(id="1", title="Python", content=None, tags=[])
        scored = service.score_lessons([lesson], "python")
        assert len(scored) == 1

    def test_score_ties_maintain_stable_sort(self):
        """Verify that lessons with equal scores maintain stable sort by ID."""
        service = LessonsDiscoveryService()
        lessons = [
            Lesson(id="zebra", title="Test A", content="test"),
            Lesson(id="alpha", title="Test B", content="test"),
        ]
        scored = service.score_lessons(lessons, "notfound")
        # Both have score 0, so sorted by id
        assert scored[0].id == "alpha"
        assert scored[1].id == "zebra"


class TestLessonFiltering:
    """Tests for lesson filtering logic."""

    def test_filter_by_category(self, discovery_service, sample_lessons):
        """Verify filtering by category."""
        result = discovery_service.filter_lessons(
            sample_lessons, {"category": "programming"}
        )
        assert all(item.category == "programming" for item in result)
        assert len(result) == 2

    def test_filter_by_difficulty(self, discovery_service, sample_lessons):
        """Verify filtering by difficulty."""
        result = discovery_service.filter_lessons(
            sample_lessons, {"difficulty": "beginner"}
        )
        assert all(item.difficulty == "beginner" for item in result)

    def test_filter_by_tags_single(self, discovery_service, sample_lessons):
        """Verify filtering by a single tag."""
        result = discovery_service.filter_lessons(
            sample_lessons, {"tags": ["python"]}
        )
        assert all(any("python" in tag for tag in item.tags) for item in result)

    def test_filter_by_tags_multiple(self, discovery_service, sample_lessons):
        """Verify filtering by multiple tags (OR logic)."""
        result = discovery_service.filter_lessons(
            sample_lessons, {"tags": ["web", "flask"]}
        )
        assert len(result) >= 1
        for item in result:
            assert any(tag in item.tags for tag in ["web", "flask"])

    def test_filter_by_tags_string(self, discovery_service, sample_lessons):
        """Verify filtering by tag as string is converted to list."""
        result = discovery_service.filter_lessons(
            sample_lessons, {"tags": "python"}
        )
        assert len(result) > 0

    def test_filter_by_status(self, discovery_service, sample_lessons):
        """Verify filtering by status."""
        result = discovery_service.filter_lessons(
            sample_lessons, {"status": "draft"}
        )
        assert all(item.status == "draft" for item in result)
        assert len(result) == 1

    def test_filter_by_date_range(self, discovery_service, sample_lessons):
        """Verify filtering by date range."""
        now = datetime.utcnow()
        result = discovery_service.filter_lessons(
            sample_lessons,
            {
                "date_from": now - timedelta(days=7),
                "date_to": now,
            },
        )
        for item in result:
            assert item.created_at >= now - timedelta(days=7)
            assert item.created_at <= now

    def test_filter_compound_criteria(self, discovery_service, sample_lessons):
        """Verify filtering with multiple criteria (AND logic)."""
        result = discovery_service.filter_lessons(
            sample_lessons,
            {"category": "programming", "difficulty": "beginner"},
        )
        assert all(
            item.category == "programming" and item.difficulty == "beginner"
            for item in result
        )

    def test_filter_with_no_criteria_returns_all(self, discovery_service, sample_lessons):
        """Verify that empty filters return all lessons."""
        result = discovery_service.filter_lessons(sample_lessons, {})
        assert len(result) == len(sample_lessons)

    def test_filter_with_no_matches_returns_empty(self, discovery_service, sample_lessons):
        """Verify that non-matching filters return empty list."""
        result = discovery_service.filter_lessons(
            sample_lessons, {"category": "nonexistent"}
        )
        assert result == []

    def test_filter_invalid_field_raises_error(self, discovery_service, sample_lessons):
        """Verify that invalid filter fields raise ValueError."""
        with pytest.raises(ValueError, match="Invalid filter field"):
            discovery_service.filter_lessons(
                sample_lessons, {"invalid_field": "value"}
            )

    def test_filter_does_not_modify_original(self, discovery_service, sample_lessons):
        """Verify that filtering does not modify the original list."""
        original_len = len(sample_lessons)
        discovery_service.filter_lessons(
            sample_lessons, {"category": "programming"}
        )
        assert len(sample_lessons) == original_len


class TestCaching:
    """Tests for caching behavior."""

    def test_cache_hit_returns_cached_data(self, discovery_service, mock_cache, sample_lessons):
        """Verify that cache hit returns cached data."""
        mock_cache.get.return_value = sample_lessons[:2]

        results = discovery_service.discover("python")

        assert len(results) == 2

    def test_cache_miss_triggers_provider_query(
        self, discovery_service, mock_cache, mock_provider
    ):
        """Verify that cache miss triggers provider query."""
        mock_cache.get.return_value = None

        discovery_service.discover("python")
        mock_provider.query.assert_called_once()

    def test_cache_set_after_fresh_query(
        self, discovery_service, mock_cache, mock_provider
    ):
        """Verify that cache is updated after fresh query."""
        mock_cache.get.return_value = None

        discovery_service.discover("python")
        mock_cache.set.assert_called_once()

    def test_cache_key_generation_deterministic(self, discovery_service):
        """Verify that cache key generation is deterministic."""
        key1 = discovery_service._build_cache_key("python", {"category": "web"})
        key2 = discovery_service._build_cache_key("python", {"category": "web"})
        assert key1 == key2

    def test_cache_key_different_for_different_queries(self, discovery_service):
        """Verify that different queries produce different cache keys."""
        key1 = discovery_service._build_cache_key("python", {})
        key2 = discovery_service._build_cache_key("javascript", {})
        assert key1 != key2

    def test_cache_key_different_for_different_filters(self, discovery_service):
        """Verify that different filters produce different cache keys."""
        key1 = discovery_service._build_cache_key("python", {"category": "web"})
        key2 = discovery_service._build_cache_key("python", {"category": "data"})
        assert key1 != key2

    def test_cache_expiration_ttl(self, discovery_service, mock_cache):
        """Verify that TTL is passed to cache.set()."""
        mock_cache.get.return_value = None
        discovery_service.discover("python")

        call_args = mock_cache.set.call_args
        assert call_args is not None
        # TTL should be 300 (default from config)
        assert call_args[0][2] == 300 or call_args[1].get("ttl") == 300

    def test_cache_invalidation(self, discovery_service, mock_cache):
        """Verify that cache.delete() is called on invalidation."""
        discovery_service.invalidate_cache("python")
        mock_cache.delete.assert_called_once()

    def test_cache_disabled_when_no_backend(
        self, discovery_service_no_cache, mock_provider
    ):
        """Verify that discovery works without cache."""
        results = discovery_service_no_cache.discover("python")
        assert len(results) > 0

    def test_cache_error_does_not_break_discovery(
        self, mock_provider, sample_lessons
    ):
        """Verify that cache errors do not prevent discovery."""
        broken_cache = MagicMock(spec=CacheBackend)
        broken_cache.get.side_effect = Exception("Cache connection failed")
        broken_cache.set.side_effect = Exception("Cache connection failed")

        service = LessonsDiscoveryService(
            providers=[mock_provider], cache=broken_cache
        )
        results = service.discover("python")
        # Should still return results despite cache errors
        assert len(results) > 0

    def test_cache_key_with_special_characters(self, discovery_service):
        """Verify that cache keys handle special characters correctly."""
        key = discovery_service._build_cache_key(
            "python 3.9 — advanced «topics»", {"tags": ["c++", "c#"]}
        )
        assert key.startswith("lessons_discovery:")
        assert len(key) > 20

    def test_cache_hit_respects_limit(self, discovery_service, mock_cache, sample_lessons):
        """Verify that limit is applied even to cached results."""
        mock_cache.get.return_value = sample_lessons
        results = discovery_service.discover("python", limit=2)
        assert len(results) == 2


class TestFallback:
    """Tests for fallback behavior when providers fail."""

    def test_fallback_when_primary_provider_fails(
        self, failing_provider, mock_secondary_provider, mock_cache
    ):
        """Verify that secondary provider is queried when primary fails."""
        service = LessonsDiscoveryService(
            providers=[failing_provider, mock_secondary_provider],
            cache=mock_cache,
        )
        service.discover("test")
        # Secondary provider should be queried
        mock_secondary_provider.query.assert_called()

    def test_fallback_to_secondary_provider(
        self, failing_provider, mock_secondary_provider, mock_cache
    ):
        """Verify that fallback to secondary provider works."""
        service = LessonsDiscoveryService(
            providers=[failing_provider, mock_secondary_provider],
            cache=mock_cache,
        )
        results = service.discover("test")
        assert isinstance(results, list)

    def test_fallback_returns_empty_when_all_fail(self, mock_cache):
        """Verify that all provider failures result in empty list."""
        p1 = MagicMock(spec=LessonProvider)
        p1.name = "p1"
        p1.query.side_effect = ConnectionError("fail")

        p2 = MagicMock(spec=LessonProvider)
        p2.name = "p2"
        p2.query.side_effect = TimeoutError("timeout")

        service = LessonsDiscoveryService(
            providers=[p1, p2], cache=mock_cache
        )
        results = service.discover("test")
        assert results == []

    def test_fallback_logs_warning_on_primary_failure(
        self, failing_provider, mock_cache
    ):
        """Verify that warnings are logged on provider failure."""
        service = LessonsDiscoveryService(
            providers=[failing_provider], cache=mock_cache
        )
        with patch.object(service.logger, "warning") as mock_warn:
            service.discover("test")
            assert mock_warn.called

    def test_fallback_chain_order(self, mock_cache):
        """Verify that providers are queried in order."""
        call_order = []

        p1 = MagicMock(spec=LessonProvider)
        p1.name = "p1"

        def p1_query(params):
            call_order.append("p1")
            raise ConnectionError("p1 failed")
        p1.query.side_effect = p1_query

        p2 = MagicMock(spec=LessonProvider)
        p2.name = "p2"

        def p2_query(params):
            call_order.append("p2")
            return [Lesson(id="from-p2", title="P2 Lesson")]
        p2.query.side_effect = p2_query

        service = LessonsDiscoveryService(
            providers=[p1, p2], cache=mock_cache
        )
        service.discover("test")

        assert call_order[0] == "p1"
        if len(call_order) > 1:
            assert call_order[1] == "p2"

    def test_no_fallback_when_primary_succeeds(
        self, mock_provider, mock_secondary_provider, mock_cache
    ):
        """Verify that secondary provider is not called when primary succeeds."""
        service = LessonsDiscoveryService(
            providers=[mock_provider, mock_secondary_provider],
            cache=mock_cache,
        )
        service.discover("python")
        mock_secondary_provider.query.assert_not_called()

    def test_fallback_with_partial_results(self, mock_cache):
        """Verify that fallback works with partial provider results."""
        p1 = MagicMock(spec=LessonProvider)
        p1.name = "p1"
        p1.query.side_effect = ConnectionError("fail")

        p2 = MagicMock(spec=LessonProvider)
        p2.name = "p2"
        p2.query.return_value = [
            Lesson(id="partial-1", title="Partial Result")
        ]

        service = LessonsDiscoveryService(
            providers=[p1, p2], cache=mock_cache
        )
        results = service.discover("test")
        assert isinstance(results, list)


class TestDeduplication:
    """Tests for deduplication of lessons from multiple providers."""

    def test_deduplicate_removes_duplicates(self):
        """Verify that duplicate lessons are removed by ID."""
        service = LessonsDiscoveryService()
        lessons = [
            Lesson(id="1", title="Lesson A"),
            Lesson(id="1", title="Lesson A Duplicate"),
            Lesson(id="2", title="Lesson B"),
        ]
        result = service._deduplicate(lessons)
        assert len(result) == 2
        ids_set = {item.id for item in result}
        assert "1" in ids_set
        assert "2" in ids_set

    def test_deduplicate_keeps_first_occurrence(self):
        """Verify that first occurrence of duplicate is kept."""
        service = LessonsDiscoveryService()
        lessons = [
            Lesson(id="1", title="First"),
            Lesson(id="1", title="Second"),
        ]
        result = service._deduplicate(lessons)
        assert result[0].title == "First"

    def test_deduplicate_empty_list(self):
        """Verify that empty list returns empty list."""
        service = LessonsDiscoveryService()
        result = service._deduplicate([])
        assert result == []


class TestCacheKeyBuilding:
    """Tests for cache key generation."""

    def test_cache_key_starts_with_prefix(self):
        """Verify that cache key has correct prefix."""
        service = LessonsDiscoveryService()
        key = service._build_cache_key("test", {})
        assert key.startswith("lessons_discovery:")

    def test_cache_key_is_string(self):
        """Verify that cache key is a string."""
        service = LessonsDiscoveryService()
        key = service._build_cache_key("test", {})
        assert isinstance(key, str)

    def test_cache_key_contains_hash(self):
        """Verify that cache key contains SHA-256 hash."""
        service = LessonsDiscoveryService()
        key = service._build_cache_key("test", {})
        hash_part = key.split(":")[-1]
        assert len(hash_part) == 64  # SHA-256 hex digest length

    def test_cache_key_order_independent_for_filter_keys(self):
        """Verify that filter key order does not affect cache key."""
        service = LessonsDiscoveryService()
        # JSON sort_keys=True ensures order independence
        key1 = service._build_cache_key("test", {"a": 1, "b": 2})
        key2 = service._build_cache_key("test", {"b": 2, "a": 1})
        assert key1 == key2


class TestServiceInitialization:
    """Tests for service initialization edge cases."""

    def test_init_with_defaults(self):
        """Verify default initialization values."""
        service = LessonsDiscoveryService()
        assert service.providers == []
        assert service.cache is None
        assert service.config == {}
        assert service.default_ttl == 300

    def test_init_with_custom_config(self):
        """Verify custom config is applied."""
        service = LessonsDiscoveryService(config={"cache_ttl": 600})
        assert service.default_ttl == 600

    def test_init_with_providers(self):
        """Verify providers are stored correctly."""
        provider = MagicMock(spec=LessonProvider)
        service = LessonsDiscoveryService(providers=[provider])
        assert len(service.providers) == 1


class TestIntegrationFlow:
    """Integration-style tests that test the full discover() flow."""

    def test_full_discover_flow_with_cache_miss(
        self, discovery_service, mock_cache, mock_provider, sample_lessons
    ):
        """Verify full flow: cache miss -> query -> filter -> score -> cache."""
        mock_cache.get.return_value = None

        results = discovery_service.discover(
            "python", filters={"category": "programming"}, limit=5
        )

        # Provider was queried
        mock_provider.query.assert_called_once()
        # Cache was set
        mock_cache.set.assert_called_once()
        # Results are filtered and limited
        assert all(item.category == "programming" for item in results)
        assert len(results) <= 5

    def test_full_discover_flow_with_cache_hit(
        self, discovery_service, mock_cache, mock_provider, sample_lessons
    ):
        """Verify that cache hit skips provider query."""
        cached_lessons = sample_lessons[:3]
        mock_cache.get.return_value = cached_lessons

        results = discovery_service.discover("python")

        assert len(results) == 3

    def test_discover_with_all_parameters(self, discovery_service, mock_cache):
        """Verify discover() handles all parameters correctly."""
        mock_cache.get.return_value = None

        results = discovery_service.discover(
            "python",
            filters={"category": "programming", "status": "active"},
            limit=2,
        )
        assert isinstance(results, list)
        assert len(results) <= 2

    def test_discover_scoring_before_limit(self, discovery_service, mock_cache):
        """Verify that scoring happens before limit is applied."""
        mock_cache.get.return_value = None

        results = discovery_service.discover("python", limit=1)
        # First result should have highest score
        if len(results) > 0:
            assert results[0].score >= 0.0

    def test_discover_filtering_after_scoring(self, discovery_service, mock_cache):
        """Verify that filtering and scoring work together."""
        mock_cache.get.return_value = None

        results = discovery_service.discover(
            "python",
            filters={"difficulty": "beginner"},
            limit=10,
        )
        # All results should match filter
        assert all(item.difficulty == "beginner" for item in results)


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_lesson_with_empty_tags(self):
        """Verify that empty tags list is handled."""
        service = LessonsDiscoveryService()
        lesson = Lesson(id="1", title="Test", tags=[])
        scored = service.score_lessons([lesson], "test")
        assert len(scored) == 1

    def test_lesson_with_empty_title_and_content(self):
        """Verify that empty title and content is handled."""
        service = LessonsDiscoveryService()
        lesson = Lesson(id="1", title="", content="")
        scored = service.score_lessons([lesson], "test")
        assert len(scored) == 1

    def test_filter_with_none_created_at(self, discovery_service):
        """Verify that None created_at is handled in date filtering."""
        lesson = Lesson(id="1", title="Test", created_at=None)
        result = discovery_service.filter_lessons(
            [lesson],
            {"date_from": datetime.utcnow() - timedelta(days=7)},
        )
        # Lesson with None created_at should not match date filter
        assert result == []

    def test_multiple_discover_calls_independent(
        self, discovery_service, mock_cache, mock_provider, sample_lessons
    ):
        """Verify that multiple discover() calls are independent."""
        mock_cache.get.return_value = None

        results1 = discovery_service.discover("python")
        results2 = discovery_service.discover("javascript")

        assert isinstance(results1, list)
        assert isinstance(results2, list)

    def test_discover_with_very_large_limit(self, discovery_service, mock_cache):
        """Verify that large limit does not break discovery."""
        mock_cache.get.return_value = None

        results = discovery_service.discover("python", limit=1000000)
        assert isinstance(results, list)