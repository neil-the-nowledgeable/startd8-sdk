"""Unit tests for CCD Layer 2: cumulative lane-peer context functions.

Covers:
    _format_lane_peer_context  (CCD-202)
    _apply_lane_peer_token_budget  (CCD-203)
"""

from __future__ import annotations

import pytest

from startd8.contractors.context_seed_handlers import (
    _apply_lane_peer_token_budget,
    _format_lane_peer_context,
)
from tests.unit.contractors.conftest import FakeSeedTask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _peer(task_id: str, title: str = "", doc: str = "") -> dict:
    return {"task_id": task_id, "title": title, "design_document": doc}


# ---------------------------------------------------------------------------
# TestLanePeerPromptFormat
# ---------------------------------------------------------------------------


class TestLanePeerPromptFormat:
    """Tests for _format_lane_peer_context."""

    def test_format_structure(self):
        """Verify outer delimiters and instruction header are present."""
        task = FakeSeedTask(task_id="T-10", target_files=["src/widget.py"])
        peers = [_peer("T-1", title="Widget core", doc="Some design.")]

        result = _format_lane_peer_context(peers, None, task)

        assert "=== LANE-PEER DESIGN CONTEXT ===" in result
        assert "=== END LANE-PEER DESIGN CONTEXT ===" in result
        # Instruction header must mention compatibility
        assert "compatible" in result.lower()
        # Peer delimiters must be present
        assert "--- Peer: T-1 (Widget core) ---" in result
        assert "--- End: T-1 ---" in result

    def test_shared_files_annotated(self):
        """Each peer entry lists shared files when the manifest shows overlap."""
        shared_file = "src/shared.py"
        task = FakeSeedTask(task_id="T-10", target_files=[shared_file])
        peer_id = "T-1"
        manifest = {shared_file: [peer_id, "T-10"]}
        peers = [_peer(peer_id, title="Peer one", doc="Peer design content.")]

        result = _format_lane_peer_context(peers, manifest, task)

        # Shared file line must appear inside the peer block
        assert f"Shared files: {shared_file}" in result

    def test_shared_files_not_annotated_when_no_overlap(self):
        """No shared-file line when the peer does not contest any of the current
        task's target files."""
        task = FakeSeedTask(task_id="T-10", target_files=["src/widget.py"])
        manifest = {"src/other.py": ["T-1", "T-2"]}  # T-10 not involved
        peers = [_peer("T-1", title="Other peer", doc="Peer design.")]

        result = _format_lane_peer_context(peers, manifest, task)

        assert "Shared files:" not in result

    def test_peer_design_doc_included_in_output(self):
        """The full design_document text of each peer appears in the output."""
        task = FakeSeedTask(task_id="T-5", target_files=[])
        doc_text = "This is the detailed design document for T-1."
        peers = [_peer("T-1", doc=doc_text)]

        result = _format_lane_peer_context(peers, None, task)

        assert doc_text in result

    def test_empty_returns_empty_string(self):
        """Empty peer list → returns empty string without any delimiters."""
        task = FakeSeedTask(task_id="T-1", target_files=[])

        result = _format_lane_peer_context([], None, task)

        assert result == ""

    def test_multiple_peers_all_present(self):
        """Multiple peers each get their own delimited block."""
        task = FakeSeedTask(task_id="T-99", target_files=[])
        peers = [
            _peer("T-1", title="Alpha", doc="Alpha design."),
            _peer("T-2", title="Beta", doc="Beta design."),
            _peer("T-3", title="Gamma", doc="Gamma design."),
        ]

        result = _format_lane_peer_context(peers, None, task)

        for pid in ("T-1", "T-2", "T-3"):
            assert f"--- Peer: {pid}" in result
            assert f"--- End: {pid} ---" in result

    def test_none_manifest_does_not_raise(self):
        """Passing None as shared_file_manifest must not raise."""
        task = FakeSeedTask(task_id="T-1", target_files=["src/a.py"])
        peers = [_peer("T-2", doc="Some doc.")]

        # Should not raise
        result = _format_lane_peer_context(peers, None, task)
        assert isinstance(result, str)
        assert result != ""

    def test_task_with_no_target_files(self):
        """Current task with empty target_files produces no shared-file annotation
        even when a manifest exists."""
        task = FakeSeedTask(task_id="T-1", target_files=[])
        manifest = {"src/shared.py": ["T-1", "T-2"]}
        peers = [_peer("T-2", doc="Peer doc.")]

        result = _format_lane_peer_context(peers, manifest, task)

        assert "Shared files:" not in result


# ---------------------------------------------------------------------------
# TestLanePeerTokenBudget
# ---------------------------------------------------------------------------


class TestLanePeerTokenBudget:
    """Tests for _apply_lane_peer_token_budget."""

    def _make_doc(self, char_count: int) -> str:
        """Return a single-line string of exactly ``char_count`` characters."""
        return "x" * char_count

    def test_budget_no_truncation_under_limit(self):
        """Docs whose total chars / 4 <= budget → returned unchanged, flag False."""
        # Two peers, each 100 chars → 200 chars → 50 estimated tokens
        designs = [
            _peer("T-1", doc=self._make_doc(100)),
            _peer("T-2", doc=self._make_doc(100)),
        ]
        result, was_truncated = _apply_lane_peer_token_budget(designs, budget_tokens=8000)

        assert was_truncated is False
        assert len(result) == 2
        assert len(result[0]["design_document"]) == 100
        assert len(result[1]["design_document"]) == 100

    def test_budget_truncates_oldest_first(self):
        """When over budget, oldest peers (earlier indices) are truncated first;
        the most recent (last) peer keeps its full document."""
        # 4 peers, each 2000 chars → 8000 chars → 2000 estimated tokens
        # Budget: 100 tokens → triggers truncation
        designs = [
            _peer("T-1", doc=self._make_doc(2000)),
            _peer("T-2", doc=self._make_doc(2000)),
            _peer("T-3", doc=self._make_doc(2000)),
            _peer("T-4", doc=self._make_doc(2000)),
        ]
        result, was_truncated = _apply_lane_peer_token_budget(designs, budget_tokens=100)

        assert was_truncated is True
        # Most recent (T-4, index 3) must NOT be truncated
        assert "[truncated]" not in result[-1]["design_document"]
        # At least one earlier peer must be truncated
        older_truncated = any(
            "[truncated]" in result[i]["design_document"]
            for i in range(len(result) - 1)
        )
        assert older_truncated

    def test_single_peer_never_truncated(self):
        """A single peer over budget is kept as-is (it is the 'most recent')."""
        designs = [_peer("T-1", doc=self._make_doc(10_000))]
        result, was_truncated = _apply_lane_peer_token_budget(designs, budget_tokens=10)

        # The loop skips the last element, so nothing is truncated
        assert was_truncated is False
        assert "[truncated]" not in result[0]["design_document"]
        assert len(result[0]["design_document"]) == 10_000

    def test_empty_input_returns_empty_unchanged(self):
        """Empty list → returns ([], False) without error."""
        result, was_truncated = _apply_lane_peer_token_budget([], budget_tokens=1000)

        assert result == []
        assert was_truncated is False

    def test_zero_budget_returns_unchanged(self):
        """budget_tokens=0 → guard short-circuits, returns input unchanged."""
        designs = [_peer("T-1", doc=self._make_doc(500))]
        result, was_truncated = _apply_lane_peer_token_budget(designs, budget_tokens=0)

        assert was_truncated is False
        assert result is designs  # same object returned

    def test_truncated_suffix_appended(self):
        """Truncated docs must end with '[truncated]'."""
        # Two peers, oldest well over 300 chars, budget tiny
        designs = [
            _peer("T-1", doc=self._make_doc(4000)),
            _peer("T-2", doc=self._make_doc(4000)),
        ]
        result, was_truncated = _apply_lane_peer_token_budget(designs, budget_tokens=1)

        assert was_truncated is True
        assert result[0]["design_document"].endswith("[truncated]")

    def test_truncated_doc_at_most_300_chars_plus_suffix(self):
        """The truncated content prefix is taken from the first 300 characters
        split at a newline boundary — result is short."""
        # Single-line doc of 1000 chars (oldest of two)
        designs = [
            _peer("T-1", doc="a" * 1000),
            _peer("T-2", doc=self._make_doc(4000)),
        ]
        result, _ = _apply_lane_peer_token_budget(designs, budget_tokens=1)

        # The truncated doc should be at most 300 chars + len("[truncated]")
        truncated_doc = result[0]["design_document"]
        if "[truncated]" in truncated_doc:
            assert len(truncated_doc) <= 300 + len(" [truncated]")

    def test_other_fields_preserved_after_truncation(self):
        """Non-design_document keys (task_id, title) are preserved on truncated peers."""
        designs = [
            {"task_id": "T-1", "title": "First peer", "design_document": "a" * 4000},
            {"task_id": "T-2", "title": "Last peer", "design_document": "b" * 4000},
        ]
        result, was_truncated = _apply_lane_peer_token_budget(designs, budget_tokens=1)

        assert result[0]["task_id"] == "T-1"
        assert result[0]["title"] == "First peer"
