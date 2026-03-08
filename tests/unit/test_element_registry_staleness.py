"""
Unit tests for ElementEntry staleness detection (REQ-MP-1108).

Tests cover:
- compute_element_context_checksum determinism
- Checksum sensitivity to each input field
- is_stale() with matching, mismatching, and None checksums
- Contract checksum ordering independence
"""

import pytest

from startd8.element_registry import (
    ElementEntry,
    compute_element_context_checksum,
    is_stale,
)


# ============================================================================
# compute_element_context_checksum
# ============================================================================


class TestComputeElementContextChecksum:
    """Tests for the shared context-checksum computation."""

    def test_deterministic_same_inputs(self):
        """Same inputs must always produce the same checksum."""
        cs1 = compute_element_context_checksum("foo", "function", "(x: int) -> int", "")
        cs2 = compute_element_context_checksum("foo", "function", "(x: int) -> int", "")
        assert cs1 == cs2

    def test_length_is_16_hex(self):
        """Checksum should be a 16-character hex string."""
        cs = compute_element_context_checksum("bar", "method")
        assert len(cs) == 16
        assert all(c in "0123456789abcdef" for c in cs)

    def test_different_name_different_checksum(self):
        cs1 = compute_element_context_checksum("foo", "function")
        cs2 = compute_element_context_checksum("bar", "function")
        assert cs1 != cs2

    def test_different_kind_different_checksum(self):
        cs1 = compute_element_context_checksum("foo", "function")
        cs2 = compute_element_context_checksum("foo", "method")
        assert cs1 != cs2

    def test_different_signature_different_checksum(self):
        cs1 = compute_element_context_checksum("foo", "function", "(x: int) -> int")
        cs2 = compute_element_context_checksum("foo", "function", "(x: str) -> str")
        assert cs1 != cs2

    def test_different_parent_class_different_checksum(self):
        cs1 = compute_element_context_checksum("foo", "method", "", "ClassA")
        cs2 = compute_element_context_checksum("foo", "method", "", "ClassB")
        assert cs1 != cs2

    def test_contract_checksums_change_result(self):
        cs_no_contracts = compute_element_context_checksum("foo", "function")
        cs_with_contracts = compute_element_context_checksum(
            "foo", "function", contract_checksums=["abc123"]
        )
        assert cs_no_contracts != cs_with_contracts

    def test_contract_checksums_order_independent(self):
        """Contract checksums are sorted internally, so order should not matter."""
        cs1 = compute_element_context_checksum(
            "foo", "function", contract_checksums=["aaa", "bbb", "ccc"]
        )
        cs2 = compute_element_context_checksum(
            "foo", "function", contract_checksums=["ccc", "aaa", "bbb"]
        )
        assert cs1 == cs2

    def test_empty_contract_list_same_as_none(self):
        """An empty list should behave the same as None (no contracts)."""
        cs_none = compute_element_context_checksum("foo", "function", contract_checksums=None)
        cs_empty = compute_element_context_checksum("foo", "function", contract_checksums=[])
        assert cs_none == cs_empty

    def test_defaults_produce_stable_checksum(self):
        """Calling with only required args should produce a stable result."""
        cs = compute_element_context_checksum("x", "constant")
        assert isinstance(cs, str)
        assert len(cs) == 16


# ============================================================================
# is_stale
# ============================================================================


class TestIsStale:
    """Tests for the is_stale() staleness predicate."""

    def _make_entry(self, context_checksum=None):
        return ElementEntry(
            element_id="test.mod.func",
            kind="function",
            name="func",
            context_checksum=context_checksum,
        )

    def test_matching_checksum_not_stale(self):
        entry = self._make_entry(context_checksum="abcd1234abcd1234")
        assert is_stale(entry, "abcd1234abcd1234") is False

    def test_mismatching_checksum_is_stale(self):
        entry = self._make_entry(context_checksum="abcd1234abcd1234")
        assert is_stale(entry, "9999888877776666") is True

    def test_none_checksum_not_stale_legacy_compat(self):
        """Entries with no checksum (legacy) should never be considered stale."""
        entry = self._make_entry(context_checksum=None)
        assert is_stale(entry, "anything") is False

    def test_stale_with_real_computed_checksum(self):
        """End-to-end: compute a checksum, store it, then detect staleness on change."""
        cs_v1 = compute_element_context_checksum("foo", "function", "(x: int) -> int")
        entry = self._make_entry(context_checksum=cs_v1)

        # Same context → not stale
        cs_same = compute_element_context_checksum("foo", "function", "(x: int) -> int")
        assert is_stale(entry, cs_same) is False

        # Signature changed → stale
        cs_v2 = compute_element_context_checksum("foo", "function", "(x: int, y: int) -> int")
        assert is_stale(entry, cs_v2) is True
