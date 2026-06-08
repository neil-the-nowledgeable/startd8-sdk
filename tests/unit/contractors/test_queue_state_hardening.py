"""FeatureQueue resume-state hardening (R1-S2 gate ADR, 2026-06-07).

Covers the three failure classes ``load_state()`` previously mishandled:
unparseable JSON returned False silently; parse-clean corruption (truncated/
mutated content that still loads as valid JSON) resumed silently; and invalid
field values (bad status enum, unknown keys, missing required fields) crashed
the run instead of failing clean.
"""

import json
from pathlib import Path

import pytest

from startd8.contractors.queue import FeatureQueue, FeatureStatus


@pytest.fixture()
def queue_with_state(tmp_path: Path) -> FeatureQueue:
    """A queue with two features persisted to disk."""
    state_file = tmp_path / ".prime_contractor_state.json"
    queue = FeatureQueue(state_file=state_file, auto_save=False)
    queue.add_feature("feat-1", "Auth", description="OAuth2")
    queue.add_feature("feat-2", "Logout", dependencies=["feat-1"])
    queue.save_state()
    return queue


def _fresh_queue(state_file: Path) -> FeatureQueue:
    return FeatureQueue(state_file=state_file, auto_save=False)


class TestStateHashRoundTrip:
    def test_save_embeds_state_hash(self, queue_with_state: FeatureQueue):
        state = json.loads(Path(queue_with_state.state_file).read_text())
        assert "state_hash" in state
        assert state["state_hash"] == FeatureQueue._compute_state_hash(state)

    def test_clean_round_trip_resumes(self, queue_with_state: FeatureQueue):
        fresh = _fresh_queue(queue_with_state.state_file)
        assert fresh.load_state() is True
        assert set(fresh.features) == {"feat-1", "feat-2"}
        assert fresh.order == ["feat-1", "feat-2"]

    def test_legacy_file_without_hash_still_loads(self, queue_with_state: FeatureQueue):
        """State files written before state_hash existed skip the check."""
        path = Path(queue_with_state.state_file)
        state = json.loads(path.read_text())
        del state["state_hash"]
        path.write_text(json.dumps(state))

        fresh = _fresh_queue(path)
        assert fresh.load_state() is True
        assert set(fresh.features) == {"feat-1", "feat-2"}


class TestCorruptionRefusal:
    def test_mutated_content_fails_integrity_check(self, queue_with_state: FeatureQueue):
        """Parse-clean mutation (valid JSON, wrong content) must refuse resume."""
        path = Path(queue_with_state.state_file)
        state = json.loads(path.read_text())
        state["features"]["feat-1"]["status"] = "complete"  # mutate without re-hashing
        path.write_text(json.dumps(state))

        fresh = _fresh_queue(path)
        assert fresh.load_state() is False
        assert fresh.features == {}

    def test_truncated_feature_set_fails_integrity_check(self, queue_with_state: FeatureQueue):
        path = Path(queue_with_state.state_file)
        state = json.loads(path.read_text())
        del state["features"]["feat-2"]
        path.write_text(json.dumps(state))

        fresh = _fresh_queue(path)
        assert fresh.load_state() is False

    def test_unparseable_json_returns_false(self, queue_with_state: FeatureQueue):
        path = Path(queue_with_state.state_file)
        path.write_text('{"features": {')  # truncated mid-write

        fresh = _fresh_queue(path)
        assert fresh.load_state() is False

    def test_missing_file_returns_false(self, tmp_path: Path):
        fresh = _fresh_queue(tmp_path / "nope.json")
        assert fresh.load_state() is False


class TestInvalidRecordsFailClean:
    """Invalid field values previously escaped load_state() as crashes."""

    def _rewrite_with_valid_hash(self, path: Path, state: dict) -> None:
        """Re-stamp the hash so only the record validity is under test."""
        state["state_hash"] = FeatureQueue._compute_state_hash(state)
        path.write_text(json.dumps(state))

    def test_invalid_status_enum_returns_false(self, queue_with_state: FeatureQueue):
        path = Path(queue_with_state.state_file)
        state = json.loads(path.read_text())
        state["features"]["feat-1"]["status"] = "pending-ish"  # not a FeatureStatus
        self._rewrite_with_valid_hash(path, state)

        fresh = _fresh_queue(path)
        assert fresh.load_state() is False  # previously: uncaught ValueError

    def test_unknown_field_returns_false(self, queue_with_state: FeatureQueue):
        path = Path(queue_with_state.state_file)
        state = json.loads(path.read_text())
        state["features"]["feat-1"]["not_a_field"] = 1
        self._rewrite_with_valid_hash(path, state)

        fresh = _fresh_queue(path)
        assert fresh.load_state() is False  # previously: uncaught TypeError

    def test_order_referencing_unknown_feature_returns_false(
        self, queue_with_state: FeatureQueue
    ):
        path = Path(queue_with_state.state_file)
        state = json.loads(path.read_text())
        state["order"] = ["feat-1", "feat-2", "feat-ghost"]
        self._rewrite_with_valid_hash(path, state)

        fresh = _fresh_queue(path)
        assert fresh.load_state() is False


class TestResumeSemanticsPreserved:
    def test_statuses_survive_round_trip(self, queue_with_state: FeatureQueue):
        queue_with_state.start_feature("feat-1")
        queue_with_state.save_state()

        fresh = _fresh_queue(queue_with_state.state_file)
        assert fresh.load_state() is True
        assert fresh.features["feat-1"].status == FeatureStatus.DEVELOPING
        assert fresh.features["feat-2"].status == FeatureStatus.PENDING
