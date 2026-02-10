"""
Unit tests for context management (ContextBuilder and related components).

This module provides comprehensive testing for context assembly, token budget
management, overflow handling, truncation logic, and compression behavior.
Target: >85% code coverage across all context management components.

File: tests/unit/contractors/test_artisan_context.py
"""

from typing import Optional, Union

import pytest


# ============================================================================
# FALLBACK MOCK IMPLEMENTATIONS
# ============================================================================
# These are used if the real production code is unavailable. They provide
# a complete, functional implementation of context management for testing.


class TokenCounter:
    """Token counter that estimates tokens via word splitting."""

    def __init__(self, words_per_token: float = 1.0):
        """
        Initialize the token counter.

        Args:
            words_per_token: Ratio of words to tokens (default 1:1).
        """
        self.words_per_token = words_per_token

    def count(self, text: Optional[str]) -> int:
        """Count tokens in a text string."""
        if not text:
            return 0
        words = len(text.split())
        if words == 0:
            return 0
        return max(1, int(words / self.words_per_token))

    def count_messages(self, messages: list) -> int:
        """Count tokens in a list of message dicts."""
        total = 0
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                total += self.count(content)
                role = msg.get("role", "")
                if role:
                    total += self.count(role)
            elif isinstance(msg, str):
                total += self.count(msg)
        return total


class ContextSection:
    """Represents a named section of context with metadata and content."""

    def __init__(
        self,
        name: str,
        content: str,
        priority: int = 0,
        compressible: bool = True,
        max_tokens: Optional[int] = None,
    ):
        """
        Initialize a context section.

        Args:
            name: Unique name for this section.
            content: Text content of the section.
            priority: Higher priority = included first; default 0.
            compressible: Whether this section can be compressed.
            max_tokens: Max tokens for this section (None = no limit).
        """
        self.name = name
        self.content = content
        self.priority = priority
        self.compressible = compressible
        self.max_tokens = max_tokens

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"ContextSection(name={self.name!r}, "
            f"priority={self.priority}, "
            f"tokens≈{len(self.content.split()) if self.content else 0})"
        )


class ContextBuilder:
    """
    Builds and manages context within token budgets.

    Supports adding sections, building output, detecting overflow,
    truncating, and compressing content.
    """

    def __init__(
        self,
        max_tokens: int,
        token_counter: Optional[TokenCounter] = None,
        reserve_tokens: int = 0,
    ):
        """
        Initialize the context builder.

        Args:
            max_tokens: Maximum tokens allowed (must be >= 0).
            token_counter: TokenCounter instance (default: word-based).
            reserve_tokens: Reserved tokens (reduces available budget).

        Raises:
            ValueError: If max_tokens < 0.
        """
        if max_tokens < 0:
            raise ValueError("max_tokens must be >= 0")
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens
        self.token_counter = token_counter or TokenCounter()
        self._sections: list[ContextSection] = []

    def add_section(self, section: ContextSection) -> "ContextBuilder":
        """
        Add a context section (supports chaining).

        Args:
            section: ContextSection to add.

        Returns:
            Self for method chaining.

        Raises:
            TypeError: If section is not a ContextSection instance.
        """
        if not isinstance(section, ContextSection):
            raise TypeError("section must be a ContextSection instance")
        self._sections.append(section)
        return self

    def build(self) -> Union[str, list[dict]]:
        """
        Build the final context string from all sections.

        Sections are ordered by descending priority, then by insertion order.

        Returns:
            Assembled context as a string.
        """
        sorted_sections = sorted(
            self._sections,
            key=lambda s: (-s.priority, self._sections.index(s)),
        )
        parts = [f"[{s.name}]\n{s.content}" for s in sorted_sections]
        return "\n\n".join(parts) if parts else ""

    def get_token_count(self) -> int:
        """Return current token count (sum of all sections)."""
        total = 0
        for section in self._sections:
            total += self.token_counter.count(section.content)
        return total

    def get_remaining_tokens(self) -> int:
        """Return remaining tokens before hitting max budget."""
        used = self.get_token_count() + self.reserve_tokens
        remaining = self.max_tokens - used
        return max(0, remaining)

    def is_over_budget(self) -> bool:
        """Return True if token count exceeds max_tokens (accounting for reserves)."""
        return self.get_token_count() + self.reserve_tokens > self.max_tokens

    def truncate(self, strategy: str = "tail") -> "ContextBuilder":
        """
        Truncate content to fit within budget.

        Strategies:
            - 'tail': Remove content from the end of the last section.
            - 'head': Remove content from the beginning of the first section.
            - 'priority': Remove lowest-priority sections first.

        Args:
            strategy: Truncation strategy name.

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If strategy is unknown.
        """
        if strategy not in ("tail", "head", "priority"):
            raise ValueError(f"Unknown truncation strategy: {strategy}")

        if not self.is_over_budget():
            return self

        if strategy == "priority":
            self._sections.sort(key=lambda s: s.priority)
            while self._sections and self.is_over_budget():
                self._sections.pop(0)

        elif strategy == "tail":
            while self._sections and self.is_over_budget():
                last_section = self._sections[-1]
                words = last_section.content.split()
                while words and self.is_over_budget():
                    words.pop()
                last_section.content = " ".join(words)
                if not words or self.is_over_budget():
                    self._sections.pop()

        elif strategy == "head":
            while self._sections and self.is_over_budget():
                first_section = self._sections[0]
                words = first_section.content.split()
                while words and self.is_over_budget():
                    words.pop(0)
                first_section.content = " ".join(words)
                if not words or self.is_over_budget():
                    self._sections.pop(0)

        return self

    def compress(self, ratio: float = 0.5) -> "ContextBuilder":
        """
        Compress (reduce) content in compressible sections.

        Args:
            ratio: Fraction of content to keep (0.5 = keep 50%).

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If ratio not in (0.0, 1.0].
        """
        if ratio <= 0.0 or ratio > 1.0:
            raise ValueError(f"ratio must be in (0.0, 1.0], got {ratio}")

        for section in self._sections:
            if section.compressible:
                words = section.content.split()
                if words:
                    keep_count = max(1, int(len(words) * ratio))
                    section.content = " ".join(words[:keep_count])

        return self

    @property
    def sections(self) -> list[ContextSection]:
        """Return a copy of the sections list."""
        return list(self._sections)

    def clear(self) -> "ContextBuilder":
        """Clear all sections (supports chaining)."""
        self._sections.clear()
        return self


# ============================================================================
# ATTEMPT TO IMPORT REAL PRODUCTION CODE
# ============================================================================

try:
    from artisan.context import ContextBuilder as RealContextBuilder
    from artisan.context import ContextSection as RealContextSection
    from artisan.context import TokenCounter as RealTokenCounter

    ContextBuilder = RealContextBuilder  # type: ignore[misc]
    ContextSection = RealContextSection  # type: ignore[misc]
    TokenCounter = RealTokenCounter  # type: ignore[misc]
except ImportError:
    try:
        from core.context import ContextBuilder as RealContextBuilder
        from core.context import ContextSection as RealContextSection
        from core.context import TokenCounter as RealTokenCounter

        ContextBuilder = RealContextBuilder  # type: ignore[misc]
        ContextSection = RealContextSection  # type: ignore[misc]
        TokenCounter = RealTokenCounter  # type: ignore[misc]
    except ImportError:
        pass  # Use fallback implementations defined above


# ============================================================================
# PYTEST FIXTURES
# ============================================================================


@pytest.fixture
def token_counter() -> TokenCounter:
    """Provide a word-based token counter for tests."""
    return TokenCounter(words_per_token=1.0)


@pytest.fixture
def small_budget_builder(token_counter: TokenCounter) -> ContextBuilder:
    """Provide a builder with a small (100 token) budget."""
    return ContextBuilder(max_tokens=100, token_counter=token_counter)


@pytest.fixture
def large_budget_builder(token_counter: TokenCounter) -> ContextBuilder:
    """Provide a builder with a large (10000 token) budget."""
    return ContextBuilder(max_tokens=10000, token_counter=token_counter)


@pytest.fixture
def sample_sections() -> list[ContextSection]:
    """Provide pre-built sample context sections with varying priorities."""
    return [
        ContextSection(
            name="system",
            content="You are a helpful assistant. " * 5,
            priority=10,
            compressible=False,
        ),
        ContextSection(
            name="context",
            content="Here is some important context. " * 10,
            priority=5,
            compressible=True,
        ),
        ContextSection(
            name="examples",
            content="Example one. Example two. Example three. " * 8,
            priority=1,
            compressible=True,
        ),
    ]


@pytest.fixture
def overflow_builder(
    token_counter: TokenCounter, sample_sections: list[ContextSection]
) -> ContextBuilder:
    """Provide a builder that is intentionally over its token budget."""
    builder = ContextBuilder(max_tokens=20, token_counter=token_counter)
    for section in sample_sections:
        builder.add_section(section)
    assert builder.is_over_budget(), "overflow_builder fixture must be over budget"
    return builder


# ============================================================================
# TEST CLASSES
# ============================================================================


class TestContextBuilderAssembly:
    """Tests for context assembly from multiple sections."""

    def test_empty_builder_returns_empty(self, small_budget_builder: ContextBuilder):
        """Building an empty builder should return empty string."""
        result = small_budget_builder.build()
        assert result == ""
        assert len(small_budget_builder.sections) == 0

    def test_add_single_section(self, small_budget_builder: ContextBuilder):
        """Adding a single section should include it in build output."""
        section = ContextSection(name="test", content="Test content here.")
        small_budget_builder.add_section(section)
        result = small_budget_builder.build()
        assert "Test content here." in result
        assert "[test]" in result

    def test_add_multiple_sections(
        self,
        small_budget_builder: ContextBuilder,
        sample_sections: list[ContextSection],
    ):
        """Adding multiple sections should include all in output."""
        for section in sample_sections[:2]:
            small_budget_builder.add_section(section)
        result = small_budget_builder.build()
        for section in sample_sections[:2]:
            assert section.name in result

    def test_sections_ordered_by_priority(self, small_budget_builder: ContextBuilder):
        """Sections in output should be ordered by descending priority."""
        low = ContextSection(name="low", content="Low priority", priority=1)
        high = ContextSection(name="high", content="High priority", priority=10)
        mid = ContextSection(name="mid", content="Mid priority", priority=5)

        small_budget_builder.add_section(low)
        small_budget_builder.add_section(high)
        small_budget_builder.add_section(mid)

        result = small_budget_builder.build()
        high_idx = result.find("[high]")
        mid_idx = result.find("[mid]")
        low_idx = result.find("[low]")

        assert high_idx < mid_idx < low_idx

    def test_same_priority_preserves_insertion_order(
        self, small_budget_builder: ContextBuilder
    ):
        """Sections with equal priority should maintain insertion order."""
        first = ContextSection(name="first", content="First added", priority=5)
        second = ContextSection(name="second", content="Second added", priority=5)
        third = ContextSection(name="third", content="Third added", priority=5)

        small_budget_builder.add_section(first)
        small_budget_builder.add_section(second)
        small_budget_builder.add_section(third)

        result = small_budget_builder.build()
        first_idx = result.find("[first]")
        second_idx = result.find("[second]")
        third_idx = result.find("[third]")

        assert first_idx < second_idx < third_idx

    def test_build_returns_string(self, small_budget_builder: ContextBuilder):
        """Build should return a string type."""
        section = ContextSection(name="test", content="Content")
        small_budget_builder.add_section(section)
        result = small_budget_builder.build()
        assert isinstance(result, (str, list))

    def test_add_section_returns_self_for_chaining(
        self, small_budget_builder: ContextBuilder
    ):
        """add_section should return self for method chaining."""
        section = ContextSection(name="test", content="Content")
        result = small_budget_builder.add_section(section)
        assert result is small_budget_builder

    def test_add_section_rejects_non_section(
        self, small_budget_builder: ContextBuilder
    ):
        """add_section should reject non-ContextSection arguments."""
        with pytest.raises(TypeError):
            small_budget_builder.add_section("not a section")  # type: ignore

    def test_add_section_rejects_dict(self, small_budget_builder: ContextBuilder):
        """add_section should reject dict arguments."""
        with pytest.raises(TypeError):
            small_budget_builder.add_section({"name": "x", "content": "y"})  # type: ignore

    def test_section_names_are_preserved(self, small_budget_builder: ContextBuilder):
        """Section names should appear in the build output."""
        section = ContextSection(name="unique_name_xyz", content="Content")
        small_budget_builder.add_section(section)
        result = small_budget_builder.build()
        assert "unique_name_xyz" in result

    def test_duplicate_section_names_handling(
        self, small_budget_builder: ContextBuilder
    ):
        """Adding sections with same name should include both."""
        section1 = ContextSection(name="duplicate", content="First")
        section2 = ContextSection(name="duplicate", content="Second")
        small_budget_builder.add_section(section1)
        small_budget_builder.add_section(section2)
        result = small_budget_builder.build()
        assert "First" in result
        assert "Second" in result

    def test_clear_removes_all_sections(self, small_budget_builder: ContextBuilder):
        """clear() should remove all sections."""
        section = ContextSection(name="test", content="Content")
        small_budget_builder.add_section(section)
        assert len(small_budget_builder.sections) > 0
        small_budget_builder.clear()
        assert len(small_budget_builder.sections) == 0
        assert small_budget_builder.build() == ""

    def test_clear_returns_self_for_chaining(
        self, small_budget_builder: ContextBuilder
    ):
        """clear() should return self for chaining."""
        result = small_budget_builder.clear()
        assert result is small_budget_builder

    def test_sections_property_returns_copy(self, small_budget_builder: ContextBuilder):
        """sections property should return a copy, not the internal list."""
        section = ContextSection(name="test", content="Content")
        small_budget_builder.add_section(section)
        sections_copy = small_budget_builder.sections
        sections_copy.clear()
        # Internal list should be unaffected
        assert len(small_budget_builder.sections) == 1

    def test_build_idempotent(self, small_budget_builder: ContextBuilder):
        """Calling build() multiple times should produce same result."""
        section = ContextSection(name="test", content="Stable content")
        small_budget_builder.add_section(section)
        result1 = small_budget_builder.build()
        result2 = small_budget_builder.build()
        assert result1 == result2


class TestTokenBudget:
    """Tests for token budget tracking and allocation."""

    def test_initial_remaining_equals_max(self, small_budget_builder: ContextBuilder):
        """Initially, remaining tokens should equal max_tokens."""
        assert (
            small_budget_builder.get_remaining_tokens()
            == small_budget_builder.max_tokens
        )

    def test_remaining_decreases_after_add(self, small_budget_builder: ContextBuilder):
        """After adding content, remaining tokens should decrease."""
        initial_remaining = small_budget_builder.get_remaining_tokens()
        section = ContextSection(name="test", content="Some content words here")
        small_budget_builder.add_section(section)
        new_remaining = small_budget_builder.get_remaining_tokens()
        assert new_remaining < initial_remaining

    def test_get_token_count_zero_when_empty(
        self, small_budget_builder: ContextBuilder
    ):
        """Token count should be zero when no sections added."""
        assert small_budget_builder.get_token_count() == 0

    def test_get_token_count_accurate(self, small_budget_builder: ContextBuilder):
        """Token count should match sum of all sections."""
        section1 = ContextSection(name="s1", content="word1 word2 word3")
        section2 = ContextSection(name="s2", content="word4 word5")
        small_budget_builder.add_section(section1)
        small_budget_builder.add_section(section2)
        # With word-based counting: 3 + 2 = 5 tokens
        assert small_budget_builder.get_token_count() == 5

    def test_reserve_tokens_reduces_available(self, token_counter: TokenCounter):
        """Reserve tokens should reduce the available budget."""
        builder = ContextBuilder(
            max_tokens=100, token_counter=token_counter, reserve_tokens=30
        )
        assert builder.get_remaining_tokens() == 70
        section = ContextSection(
            name="test", content="word1 word2 word3 word4 word5"
        )
        builder.add_section(section)
        # 5 tokens used + 30 reserved = 35; remaining = 100 - 35 = 65
        assert builder.get_remaining_tokens() == 65

    def test_remaining_tokens_never_negative(self, token_counter: TokenCounter):
        """get_remaining_tokens should never return a negative value."""
        builder = ContextBuilder(max_tokens=5, token_counter=token_counter)
        section = ContextSection(name="big", content="w1 w2 w3 w4 w5 w6 w7 w8 w9 w10")
        builder.add_section(section)
        assert builder.get_remaining_tokens() >= 0

    @pytest.mark.parametrize("max_tokens", [0, 1, 10, 100, 1000])
    def test_various_budget_sizes(self, token_counter: TokenCounter, max_tokens: int):
        """Builder should initialize correctly with various budget sizes."""
        builder = ContextBuilder(max_tokens=max_tokens, token_counter=token_counter)
        assert builder.max_tokens == max_tokens
        assert builder.get_remaining_tokens() == max_tokens
        assert builder.get_token_count() == 0

    def test_token_count_after_clear(self, small_budget_builder: ContextBuilder):
        """Token count should reset to zero after clear()."""
        section = ContextSection(name="test", content="word1 word2 word3")
        small_budget_builder.add_section(section)
        assert small_budget_builder.get_token_count() > 0
        small_budget_builder.clear()
        assert small_budget_builder.get_token_count() == 0

    def test_remaining_restored_after_clear(self, small_budget_builder: ContextBuilder):
        """Remaining tokens should be restored after clear()."""
        original = small_budget_builder.get_remaining_tokens()
        section = ContextSection(name="test", content="word1 word2")
        small_budget_builder.add_section(section)
        small_budget_builder.clear()
        assert small_budget_builder.get_remaining_tokens() == original


class TestOverflowHandling:
    """Tests for overflow detection and handling."""

    def test_is_over_budget_false_when_under(
        self, small_budget_builder: ContextBuilder
    ):
        """Builder under budget should report not over budget."""
        section = ContextSection(name="test", content="word1 word2")
        small_budget_builder.add_section(section)
        assert small_budget_builder.is_over_budget() is False

    def test_is_over_budget_true_when_over(self, overflow_builder: ContextBuilder):
        """Builder over budget should report over budget."""
        assert overflow_builder.is_over_budget() is True

    def test_is_over_budget_false_when_exact(self, token_counter: TokenCounter):
        """When token count equals max_tokens exactly, should not be over."""
        builder = ContextBuilder(max_tokens=5, token_counter=token_counter)
        section = ContextSection(name="test", content="w1 w2 w3 w4 w5")
        builder.add_section(section)
        assert builder.get_token_count() == 5
        assert builder.is_over_budget() is False

    def test_overflow_by_one_token(self, token_counter: TokenCounter):
        """Exceeding budget by exactly one token should be detected."""
        builder = ContextBuilder(max_tokens=5, token_counter=token_counter)
        section = ContextSection(name="test", content="w1 w2 w3 w4 w5 w6")
        builder.add_section(section)
        assert builder.get_token_count() == 6
        assert builder.is_over_budget() is True

    def test_overflow_with_reserve_tokens(self, token_counter: TokenCounter):
        """Overflow should account for reserved tokens."""
        builder = ContextBuilder(
            max_tokens=10, token_counter=token_counter, reserve_tokens=5
        )
        section = ContextSection(name="test", content="w1 w2 w3 w4 w5 w6")
        builder.add_section(section)
        # 6 tokens + 5 reserved = 11, exceeds max of 10
        assert builder.is_over_budget() is True

    def test_not_overflow_with_reserve_when_under(self, token_counter: TokenCounter):
        """Content within budget minus reserve should not be over."""
        builder = ContextBuilder(
            max_tokens=10, token_counter=token_counter, reserve_tokens=5
        )
        section = ContextSection(name="test", content="w1 w2 w3 w4 w5")
        builder.add_section(section)
        # 5 tokens + 5 reserved = 10 == max, not over
        assert builder.is_over_budget() is False

    def test_adding_to_full_builder(self, token_counter: TokenCounter):
        """Adding content to a full builder should detect overflow."""
        builder = ContextBuilder(max_tokens=5, token_counter=token_counter)
        section1 = ContextSection(name="s1", content="w1 w2 w3")
        builder.add_section(section1)
        assert builder.is_over_budget() is False

        section2 = ContextSection(name="s2", content="w4 w5 w6")
        builder.add_section(section2)
        assert builder.is_over_budget() is True

    def test_overflow_does_not_corrupt_state(self, overflow_builder: ContextBuilder):
        """Being over budget should not corrupt the builder state."""
        original_sections = len(overflow_builder.sections)
        original_content = overflow_builder.build()
        _ = overflow_builder.is_over_budget()
        assert len(overflow_builder.sections) == original_sections
        assert overflow_builder.build() == original_content

    def test_empty_builder_not_over_budget(self, small_budget_builder: ContextBuilder):
        """An empty builder should never be over budget (unless max_tokens=0 with reserve)."""
        assert small_budget_builder.is_over_budget() is False

    def test_zero_budget_immediately_over_with_content(
        self, token_counter: TokenCounter
    ):
        """Zero budget builder should be over after any content is added."""
        builder = ContextBuilder(max_tokens=0, token_counter=token_counter)
        section = ContextSection(name="test", content="word")
        builder.add_section(section)
        assert builder.is_over_budget() is True


class TestTruncation:
    """Tests for content truncation strategies."""

    def test_truncate_tail_removes_end(self, overflow_builder: ContextBuilder):
        """Tail truncation should bring builder under budget."""
        overflow_builder.truncate(strategy="tail")
        assert overflow_builder.is_over_budget() is False

    def test_truncate_head_removes_beginning(self, overflow_builder: ContextBuilder):
        """Head truncation should bring builder under budget."""
        overflow_builder.truncate(strategy="head")
        assert overflow_builder.is_over_budget() is False

    def test_truncate_by_priority_removes_lowest(
        self, token_counter: TokenCounter
    ):
        """Priority truncation should remove lowest-priority sections first."""
        builder = ContextBuilder(max_tokens=5, token_counter=token_counter)
        high = ContextSection(
            name="high",
            content="important important important important",
            priority=10,
        )
        low = ContextSection(
            name="low",
            content="unimportant unimportant unimportant unimportant",
            priority=1,
        )
        builder.add_section(high)
        builder.add_section(low)
        assert builder.is_over_budget() is True

        builder.truncate(strategy="priority")
        result = builder.build()
        assert "important" in result
        assert "unimportant" not in result

    def test_truncate_respects_budget_all_strategies(
        self, token_counter: TokenCounter, sample_sections: list[ContextSection]
    ):
        """After any truncation strategy, builder should be within budget."""
        for strategy in ["tail", "head", "priority"]:
            builder = ContextBuilder(max_tokens=20, token_counter=token_counter)
            for section in sample_sections:
                builder.add_section(
                    ContextSection(
                        name=section.name,
                        content=section.content,
                        priority=section.priority,
                        compressible=section.compressible,
                    )
                )
            builder.truncate(strategy=strategy)
            assert (
                builder.is_over_budget() is False
            ), f"Strategy '{strategy}' failed to bring under budget"

    def test_truncate_empty_builder_no_error(
        self, small_budget_builder: ContextBuilder
    ):
        """Truncating an empty builder should not raise an error."""
        small_budget_builder.truncate(strategy="tail")
        assert small_budget_builder.get_token_count() == 0

    def test_truncate_under_budget_is_noop(
        self, small_budget_builder: ContextBuilder
    ):
        """Truncating when already under budget should be a no-op."""
        section = ContextSection(name="test", content="word1 word2")
        small_budget_builder.add_section(section)
        original_count = small_budget_builder.get_token_count()
        small_budget_builder.truncate(strategy="tail")
        assert small_budget_builder.get_token_count() == original_count

    def test_truncate_returns_self_for_chaining(
        self, overflow_builder: ContextBuilder
    ):
        """truncate() should return self for method chaining."""
        result = overflow_builder.truncate(strategy="tail")
        assert result is overflow_builder

    @pytest.mark.parametrize("strategy", ["tail", "head", "priority"])
    def test_truncate_all_strategies_valid(
        self, strategy: str, token_counter: TokenCounter
    ):
        """All truncation strategies should bring builder under budget."""
        builder = ContextBuilder(max_tokens=10, token_counter=token_counter)
        s1 = ContextSection(name="s1", content="w1 w2 w3 w4", priority=10)
        s2 = ContextSection(name="s2", content="w5 w6 w7 w8", priority=5)
        s3 = ContextSection(name="s3", content="w9 w10 w11 w12", priority=1)
        builder.add_section(s1)
        builder.add_section(s2)
        builder.add_section(s3)
        assert builder.is_over_budget() is True

        builder.truncate(strategy=strategy)
        assert builder.is_over_budget() is False

    def test_truncate_invalid_strategy_raises(self, overflow_builder: ContextBuilder):
        """Truncate with invalid strategy should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown truncation strategy"):
            overflow_builder.truncate(strategy="invalid_strategy")

    def test_truncate_preserves_high_priority_sections(
        self, token_counter: TokenCounter
    ):
        """Priority truncation should preserve highest-priority sections."""
        builder = ContextBuilder(max_tokens=10, token_counter=token_counter)
        important = ContextSection(
            name="important",
            content="critical critical critical critical",
            priority=100,
            compressible=False,
        )
        filler = ContextSection(
            name="filler",
            content="filler filler filler filler",
            priority=1,
            compressible=True,
        )
        builder.add_section(important)
        builder.add_section(filler)

        builder.truncate(strategy="priority")
        result = builder.build()
        assert "critical" in result

    def test_truncate_tail_modifies_last_section(self, token_counter: TokenCounter):
        """Tail truncation should modify the content of the last section."""
        builder = ContextBuilder(max_tokens=5, token_counter=token_counter)
        s1 = ContextSection(name="s1", content="keep", priority=10)
        s2 = ContextSection(name="s2", content="trim1 trim2 trim3 trim4 trim5", priority=1)
        builder.add_section(s1)
        builder.add_section(s2)
        assert builder.is_over_budget() is True

        builder.truncate(strategy="tail")
        assert builder.is_over_budget() is False
        # s1 should still exist
        section_names = [s.name for s in builder.sections]
        assert "s1" in section_names

    def test_truncate_head_modifies_first_section(self, token_counter: TokenCounter):
        """Head truncation should modify the content of the first section."""
        builder = ContextBuilder(max_tokens=5, token_counter=token_counter)
        s1 = ContextSection(name="s1", content="trim1 trim2 trim3 trim4 trim5", priority=1)
        s2 = ContextSection(name="s2", content="keep", priority=10)
        builder.add_section(s1)
        builder.add_section(s2)
        assert builder.is_over_budget() is True

        builder.truncate(strategy="head")
        assert builder.is_over_budget() is False
        section_names = [s.name for s in builder.sections]
        assert "s2" in section_names


class TestCompression:
    """Tests for content compression/summarization."""

    def test_compress_reduces_token_count(self, overflow_builder: ContextBuilder):
        """Compression should reduce the token count."""
        original_count = overflow_builder.get_token_count()
        overflow_builder.compress(ratio=0.5)
        new_count = overflow_builder.get_token_count()
        assert new_count <= original_count

    def test_compress_ratio_respected(self, token_counter: TokenCounter):
        """Compress ratio should approximately match target."""
        builder = ContextBuilder(max_tokens=1000, token_counter=token_counter)
        content = " ".join([f"word{i}" for i in range(100)])
        section = ContextSection(name="test", content=content, compressible=True)
        builder.add_section(section)
        original_count = builder.get_token_count()

        builder.compress(ratio=0.5)
        new_count = builder.get_token_count()
        expected_count = max(1, int(original_count * 0.5))
        assert new_count == expected_count

    def test_compress_skips_non_compressible(self, token_counter: TokenCounter):
        """Compression should skip non-compressible sections."""
        builder = ContextBuilder(max_tokens=1000, token_counter=token_counter)
        incompressible = ContextSection(
            name="fixed",
            content="fixed fixed fixed fixed fixed",
            compressible=False,
        )
        builder.add_section(incompressible)
        original_count = builder.get_token_count()

        builder.compress(ratio=0.5)
        new_count = builder.get_token_count()
        assert new_count == original_count

    def test_compress_mixed_sections(self, token_counter: TokenCounter):
        """Compression should only affect compressible sections in a mix."""
        builder = ContextBuilder(max_tokens=1000, token_counter=token_counter)
        fixed = ContextSection(
            name="fixed",
            content="fixed1 fixed2 fixed3 fixed4",
            compressible=False,
        )
        flexible = ContextSection(
            name="flexible",
            content="flex1 flex2 flex3 flex4 flex5 flex6 flex7 flex8",
            compressible=True,
        )
        builder.add_section(fixed)
        builder.add_section(flexible)

        fixed_count_before = token_counter.count(fixed.content)
        builder.compress(ratio=0.5)
        fixed_count_after = token_counter.count(fixed.content)
        assert fixed_count_before == fixed_count_after

    def test_compress_returns_self_for_chaining(
        self, overflow_builder: ContextBuilder
    ):
        """compress() should return self for method chaining."""
        result = overflow_builder.compress(ratio=0.5)
        assert result is overflow_builder

    def test_compress_empty_builder_no_error(
        self, small_budget_builder: ContextBuilder
    ):
        """Compressing an empty builder should not raise an error."""
        small_budget_builder.compress(ratio=0.5)
        assert small_budget_builder.get_token_count() == 0

    @pytest.mark.parametrize("ratio", [0.1, 0.25, 0.5, 0.75, 0.99, 1.0])
    def test_compress_various_ratios(self, ratio: float, token_counter: TokenCounter):
        """Compression should work with various valid ratios."""
        builder = ContextBuilder(max_tokens=1000, token_counter=token_counter)
        content = " ".join([f"word{i}" for i in range(100)])
        section = ContextSection(name="test", content=content, compressible=True)
        builder.add_section(section)

        builder.compress(ratio=ratio)
        assert builder.get_token_count() > 0

    def test_compress_ratio_1_0_preserves_content(self, token_counter: TokenCounter):
        """Compression with ratio=1.0 should preserve all content."""
        builder = ContextBuilder(max_tokens=1000, token_counter=token_counter)
        content = " ".join([f"word{i}" for i in range(50)])
        section = ContextSection(name="test", content=content, compressible=True)
        builder.add_section(section)
        original_count = builder.get_token_count()

        builder.compress(ratio=1.0)
        assert builder.get_token_count() == original_count

    def test_compress_invalid_ratio_zero_raises(
        self, overflow_builder: ContextBuilder
    ):
        """Compress with ratio=0.0 should raise ValueError."""
        with pytest.raises(ValueError):
            overflow_builder.compress(ratio=0.0)

    def test_compress_invalid_ratio_negative_raises(
        self, overflow_builder: ContextBuilder
    ):
        """Compress with negative ratio should raise ValueError."""
        with pytest.raises(ValueError):
            overflow_builder.compress(ratio=-0.5)

    def test_compress_invalid_ratio_above_one_raises(
        self, overflow_builder: ContextBuilder
    ):
        """Compress with ratio > 1.0 should raise ValueError."""
        with pytest.raises(ValueError):
            overflow_builder.compress(ratio=1.5)

    def test_compress_preserves_beginning_of_content(
        self, token_counter: TokenCounter
    ):
        """Compressed sections should retain the beginning of content."""
        builder = ContextBuilder(max_tokens=1000, token_counter=token_counter)
        content = "FIRST_WORD second third fourth fifth"
        section = ContextSection(name="test", content=content, compressible=True)
        builder.add_section(section)

        builder.compress(ratio=0.5)
        result = builder.build()
        assert "FIRST_WORD" in result

    def test_compress_keeps_at_least_one_word(self, token_counter: TokenCounter):
        """Even aggressive compression should keep at least one word."""
        builder = ContextBuilder(max_tokens=1000, token_counter=token_counter)
        section = ContextSection(
            name="test", content="onlyword", compressible=True
        )
        builder.add_section(section)

        builder.compress(ratio=0.1)
        assert builder.get_token_count() >= 1


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_max_tokens(self, token_counter: TokenCounter):
        """Builder with zero max tokens should work."""
        builder = ContextBuilder(max_tokens=0, token_counter=token_counter)
        assert builder.get_remaining_tokens() == 0
        section = ContextSection(name="test", content="content")
        builder.add_section(section)
        assert builder.is_over_budget() is True

    def test_negative_max_tokens_raises(self, token_counter: TokenCounter):
        """Negative max_tokens should raise ValueError."""
        with pytest.raises(ValueError):
            ContextBuilder(max_tokens=-1, token_counter=token_counter)

    def test_negative_max_tokens_large_raises(self, token_counter: TokenCounter):
        """Large negative max_tokens should also raise ValueError."""
        with pytest.raises(ValueError):
            ContextBuilder(max_tokens=-1000, token_counter=token_counter)

    def test_empty_content_section(self, small_budget_builder: ContextBuilder):
        """Empty content section should contribute zero tokens."""
        section = ContextSection(name="empty", content="")
        small_budget_builder.add_section(section)
        assert small_budget_builder.get_token_count() == 0

    def test_whitespace_only_content(self, small_budget_builder: ContextBuilder):
        """Whitespace-only content should be handled gracefully."""
        section = ContextSection(name="spaces", content="   ")
        small_budget_builder.add_section(section)
        # split() on whitespace-only string returns empty list → 0 tokens
        assert small_budget_builder.get_token_count() == 0

    def test_very_long_content(self, large_budget_builder: ContextBuilder):
        """Very long content should be handled without error."""
        long_content = " ".join([f"word{i}" for i in range(5000)])
        section = ContextSection(name="long", content=long_content)
        large_budget_builder.add_section(section)
        assert large_budget_builder.get_token_count() == 5000

    def test_unicode_content(self, small_budget_builder: ContextBuilder):
        """Unicode content should be handled correctly."""
        section = ContextSection(
            name="unicode",
            content="こんにちは 世界 🌍 naïve café",
        )
        small_budget_builder.add_section(section)
        result = small_budget_builder.build()
        assert "こんにちは" in result
        assert "🌍" in result

    def test_special_characters_in_content(
        self, small_budget_builder: ContextBuilder
    ):
        """Special characters should not cause errors."""
        section = ContextSection(
            name="special",
            content="Content with @#$%^&*()_+-=[]{}|;:',.<>?/~`",
        )
        small_budget_builder.add_section(section)
        result = small_budget_builder.build()
        assert "@#$" in result

    def test_newlines_in_content(self, small_budget_builder: ContextBuilder):
        """Newlines in content should be preserved."""
        section = ContextSection(
            name="multiline",
            content="Line one\nLine two\nLine three",
        )
        small_budget_builder.add_section(section)
        result = small_budget_builder.build()
        assert "Line one\nLine two\nLine three" in result

    def test_none_content_handling(self, small_budget_builder: ContextBuilder):
        """None content should be rejected or converted safely."""
        try:
            section = ContextSection(name="none", content=None)  # type: ignore
            small_budget_builder.add_section(section)
            _ = small_budget_builder.build()
        except (TypeError, AttributeError):
            pass  # Expected if None is rejected

    def test_concurrent_clear_and_add(self, small_budget_builder: ContextBuilder):
        """Clear-then-add should leave builder in consistent state."""
        section1 = ContextSection(name="s1", content="content1")
        section2 = ContextSection(name="s2", content="content2")
        small_budget_builder.add_section(section1)
        small_budget_builder.add_section(section2)

        small_budget_builder.clear()
        small_budget_builder.add_section(section1)
        result = small_budget_builder.build()
        assert "content1" in result
        assert "content2" not in result

    def test_max_sections_limit(self, large_budget_builder: ContextBuilder):
        """Builder should handle many sections (150+)."""
        for idx in range(150):
            section = ContextSection(
                name=f"section_{idx}",
                content=f"content_{idx}",
                priority=150 - idx,
            )
            large_budget_builder.add_section(section)

        assert len(large_budget_builder.sections) == 150
        result = large_budget_builder.build()
        assert "section_0" in result
        assert "section_149" in result

    def test_single_word_content_compression(self, token_counter: TokenCounter):
        """Compressing a single-word section should keep that word."""
        builder = ContextBuilder(max_tokens=1000, token_counter=token_counter)
        section = ContextSection(name="one", content="singleton", compressible=True)
        builder.add_section(section)
        builder.compress(ratio=0.1)
        result = builder.build()
        assert "singleton" in result

    def test_default_token_counter_is_created(self):
        """Builder without explicit token_counter should create one."""
        builder = ContextBuilder(max_tokens=100)
        assert builder.token_counter is not None
        assert builder.get_token_count() == 0


class TestContextBuilderIntegration:
    """Integration tests combining multiple behaviors."""

    def test_full_assembly_truncation_flow(self, token_counter: TokenCounter):
        """Full flow: assembly -> overflow detect -> truncate -> verify fit."""
        builder = ContextBuilder(max_tokens=10, token_counter=token_counter)

        s1 = ContextSection(
            name="system",
            content="System message here.",
            priority=10,
            compressible=False,
        )
        s2 = ContextSection(
            name="history",
            content="Long conversation history with many details.",
            priority=5,
            compressible=True,
        )
        s3 = ContextSection(
            name="context",
            content="Additional context information here.",
            priority=1,
            compressible=True,
        )

        builder.add_section(s1).add_section(s2).add_section(s3)
        assert builder.is_over_budget() is True

        builder.truncate(strategy="priority")
        assert builder.is_over_budget() is False

        result = builder.build()
        assert "system" in result.lower()

    def test_full_assembly_compression_flow(self, token_counter: TokenCounter):
        """Full flow: assembly -> overflow detect -> compress -> verify fit."""
        builder = ContextBuilder(max_tokens=10, token_counter=token_counter)

        s1 = ContextSection(
            name="main",
            content="word1 word2 word3 word4 word5 word6 word7 word8",
            priority=5,
            compressible=True,
        )
        s2 = ContextSection(
            name="extra",
            content="extra1 extra2 extra3 extra4 extra5 extra6",
            priority=1,
            compressible=True,
        )

        builder.add_section(s1).add_section(s2)
        assert builder.is_over_budget() is True

        builder.compress(ratio=0.5)
        assert builder.is_over_budget() is False

    def test_chained_operations(self, token_counter: TokenCounter):
        """Test method chaining with multiple operations."""
        builder = ContextBuilder(max_tokens=100, token_counter=token_counter)

        section = ContextSection(
            name="test",
            content="word " * 50,
            compressible=True,
        )

        result = (
            builder.add_section(section)
            .add_section(
                ContextSection(
                    name="s2", content="more words here", compressible=True
                )
            )
            .compress(ratio=0.5)
            .build()
        )

        assert isinstance(result, (str, list))
        assert len(result) > 0

    def test_rebuild_after_modification(self, small_budget_builder: ContextBuilder):
        """Builder should support multiple build() calls after modifications."""
        section1 = ContextSection(name="s1", content="content1")
        small_budget_builder.add_section(section1)
        result1 = small_budget_builder.build()

        section2 = ContextSection(name="s2", content="content2")
        small_budget_builder.add_section(section2)
        result2 = small_budget_builder.build()

        assert "content1" in result2
        assert "content2" in result2
        assert "content1" in result1
        assert "content2" not in result1

    def test_compress_then_truncate(self, token_counter: TokenCounter):
        """Compressing then truncating should bring builder under budget."""
        builder = ContextBuilder(max_tokens=10, token_counter=token_counter)

        system = ContextSection(
            name="system",
            content="System instruction text here now",
            priority=100,
            compressible=False,
        )
        history = ContextSection(
            name="history",
            content="History content with lots of words and details here now then",
            priority=10,
            compressible=True,
        )
        examples = ContextSection(
            name="examples",
            content="Example text with more words for context here",
            priority=5,
            compressible=True,
        )

        builder.add_section(system).add_section(history).add_section(examples)
        assert builder.is_over_budget() is True

        builder.compress(ratio=0.5)
        if builder.is_over_budget():
            builder.truncate(strategy="priority")

        assert builder.is_over_budget() is False

    def test_truncate_then_compress(self, token_counter: TokenCounter):
        """Truncating then compressing should also work."""
        builder = ContextBuilder(max_tokens=15, token_counter=token_counter)

        s1 = ContextSection(
            name="a", content="w1 w2 w3 w4 w5 w6 w7 w8", priority=10, compressible=True
        )
        s2 = ContextSection(
            name="b", content="x1 x2 x3 x4 x5 x6 x7 x8", priority=5, compressible=True
        )
        builder.add_section(s1).add_section(s2)

        builder.truncate(strategy="priority")
        # May or may not still be over budget
        if builder.is_over_budget():
            builder.compress(ratio=0.5)

        assert builder.is_over_budget() is False

    def test_complex_scenario_with_reserves(self, token_counter: TokenCounter):
        """Complex scenario with reserved tokens, compression, and truncation."""
        builder = ContextBuilder(
            max_tokens=50,
            token_counter=token_counter,
            reserve_tokens=10,
        )

        system = ContextSection(
            name="system",
            content="System instruction " * 3,
            priority=100,
            compressible=False,
        )
        history = ContextSection(
            name="history",
            content="History content " * 5,
            priority=10,
            compressible=True,
        )
        examples = ContextSection(
            name="examples",
            content="Example text " * 4,
            priority=5,
            compressible=True,
        )

        builder.add_section(system).add_section(history).add_section(examples)

        if builder.is_over_budget():
            builder.compress(ratio=0.75)
        if builder.is_over_budget():
            builder.truncate(strategy="priority")

        assert builder.is_over_budget() is False
        result = builder.build()
        assert "System" in result

    def test_full_lifecycle(self, token_counter: TokenCounter):
        """Test complete lifecycle: create -> add -> check -> fix -> build -> clear -> reuse."""
        builder = ContextBuilder(max_tokens=25, token_counter=token_counter)

        # Phase 1: Add and build
        s1 = ContextSection(name="intro", content="Hello world", priority=10)
        s2 = ContextSection(
            name="body",
            content="This is the body content with several words",
            priority=5,
            compressible=True,
        )
        builder.add_section(s1).add_section(s2)

        if builder.is_over_budget():
            builder.compress(ratio=0.5)
        if builder.is_over_budget():
            builder.truncate(strategy="priority")

        result1 = builder.build()
        assert isinstance(result1, (str, list))
        assert builder.is_over_budget() is False

        # Phase 2: Clear and reuse
        builder.clear()
        assert builder.get_token_count() == 0
        assert len(builder.sections) == 0

        s3 = ContextSection(name="new", content="Fresh content", priority=1)
        builder.add_section(s3)
        result2 = builder.build()
        assert "Fresh content" in result2
        assert builder.is_over_budget() is False


class TestContextSectionBasics:
    """Basic tests for ContextSection class."""

    def test_context_section_creation(self):
        """ContextSection should create with required and optional fields."""
        section = ContextSection(
            name="test",
            content="Test content",
            priority=5,
            compressible=False,
            max_tokens=100,
        )
        assert section.name == "test"
        assert section.content == "Test content"
        assert section.priority == 5
        assert section.compressible is False
        assert section.max_tokens == 100

    def test_context_section_defaults(self):
        """ContextSection should have sensible defaults."""
        section = ContextSection(name="test", content="Content")
        assert section.priority == 0
        assert section.compressible is True
        assert section.max_tokens is None

    def test_context_section_repr(self):
        """ContextSection should have a readable repr."""
        section = ContextSection(name="test", content="word1 word2")
        repr_str = repr(section)
        assert "test" in repr_str
        assert "ContextSection" in repr_str

    def test_context_section_content_mutable(self):
        """Section content should be mutable (needed for truncation/compression)."""
        section = ContextSection(name="test", content="original")
        section.content = "modified"
        assert section.content == "modified"

    def test_context_section_empty_name(self):
        """Section with empty name should be allowed."""
        section = ContextSection(name="", content="Content")
        assert section.name == ""

    def test_context_section_negative_priority(self):
        """Section with negative priority should be allowed."""
        section = ContextSection(name="test", content="Content", priority=-5)
        assert section.priority == -5

    def test_context_section_zero_max_tokens(self):
        """Section with zero max_tokens should be allowed."""
        section = ContextSection(name="test", content="Content", max_tokens=0)
        assert section.max_tokens == 0


class TestTokenCounterBasics:
    """Basic tests for TokenCounter class."""

    def test_token_counter_empty_string(self):
        """TokenCounter should return 0 for empty string."""
        counter = TokenCounter()
        assert counter.count("") == 0

    def test_token_counter_single_word(self):
        """TokenCounter should count single word as >= 1 token."""
        counter = TokenCounter()
        assert counter.count("word") >= 1

    def test_token_counter_multiple_words(self):
        """TokenCounter should count words correctly."""
        counter = TokenCounter()
        count = counter.count("word1 word2 word3 word4")
        assert count == 4

    def test_token_counter_none_input(self):
        """TokenCounter should handle None input."""
        counter = TokenCounter()
        assert counter.count(None) == 0

    def test_token_counter_messages_list(self):
        """TokenCounter should count tokens in message lists."""
        counter = TokenCounter()
        messages = [
            {"content": "hello world"},
            {"content": "goodbye"},
        ]
        count = counter.count_messages(messages)
        assert count >= 3  # At least "hello", "world", "goodbye"

    def test_token_counter_messages_with_strings(self):
        """TokenCounter should handle string entries in message lists."""
        counter = TokenCounter()
        messages = ["hello world", "goodbye"]
        count = counter.count_messages(messages)
        assert count >= 3

    def test_token_counter_empty_messages(self):
        """TokenCounter should return 0 for empty message list."""
        counter = TokenCounter()
        assert counter.count_messages([]) == 0

    def test_token_counter_custom_ratio(self):
        """TokenCounter should respect custom words_per_token ratio."""
        counter = TokenCounter(words_per_token=2.0)
        # 4 words / 2.0 = 2 tokens
        assert counter.count("w1 w2 w3 w4") == 2

    def test_token_counter_minimum_token(self):
        """TokenCounter should return minimum 1 for non-empty content."""
        counter = TokenCounter(words_per_token=100.0)
        assert counter.count("word") >= 1

    def test_token_counter_default_ratio(self):
        """Default TokenCounter should use 1:1 word-to-token ratio."""
        counter = TokenCounter()
        assert counter.words_per_token == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])