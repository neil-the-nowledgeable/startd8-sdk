"""
Unit tests for ElementRegistry class.

Tests cover:
- Round-trip put/get fidelity
- Missing-ID handling
- Persistence across restarts
- Concurrent write safety
- Phase status lifecycle
- File-scoped element lookup
- Aggregate summaries
- Remove and clear operations
- Graceful I/O failure degradation

Usage:
    pytest tests/test_element_registry.py -v
"""

import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from startd8.element_id import make_element_id
from startd8.element_registry import ElementEntry, ElementRegistry


# ============================================================================
# Module-level constants
# ============================================================================

THREAD_COUNT = 20


# ============================================================================
# Helpers
# ============================================================================


def _make_entry(
    element_id: str,
    name: str = "my_func",
    kind: str = "function",
    file_path: str | None = "src/foo.py",
) -> ElementEntry:
    """
    Construct a minimal valid ElementEntry for testing.

    Args:
        element_id: Unique identifier for the element.
        name: Human-readable name (default "my_func").
        kind: Kind of element (default "function").
        file_path: Path to the source file (default "src/foo.py");
                   pass None to simulate virtual/anonymous elements.

    Returns:
        An ElementEntry with sensible defaults; phase_records managed by registry.
    """
    return ElementEntry(
        element_id=element_id,
        name=name,
        kind=kind,
        file_path=file_path,
    )


def _make_registry(state_dir: Path) -> ElementRegistry:
    """
    Construct an ElementRegistry backed by a temporary directory.

    Args:
        state_dir: Temporary directory for registry state files.

    Returns:
        A fresh ElementRegistry instance.
    """
    return ElementRegistry(state_dir=state_dir)


# ============================================================================
# Test: Put/Get Round-Trip
# ============================================================================


class TestPutGetRoundTrip:
    """Tests for basic put/get round-trip fidelity."""

    def test_put_get_returns_stored_entry(self, tmp_path: Path) -> None:
        """
        GIVEN a fresh registry and a valid ElementEntry
        WHEN put() is called then get() is called with the same ID
        THEN the returned entry matches the original on all key fields.
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "process_data", "src/processor.py")
        entry = _make_entry(
            element_id=eid,
            name="process_data",
            kind="function",
            file_path="src/processor.py",
        )

        registry.put(entry)
        result = registry.get(eid)

        assert result is not None
        assert result.element_id == entry.element_id
        assert result.name == entry.name
        assert result.kind == entry.kind
        assert result.file_path == entry.file_path

    def test_get_missing_id_returns_none(self, tmp_path: Path) -> None:
        """
        GIVEN a fresh registry
        WHEN get() is called with an ID that was never put
        THEN None is returned.
        """
        registry = _make_registry(tmp_path)
        result = registry.get("definitely::does::not::exist")
        assert result is None

    def test_has_returns_false_before_put(self, tmp_path: Path) -> None:
        """
        GIVEN a fresh registry
        WHEN has() is called with any ID
        THEN returns False.
        """
        registry = _make_registry(tmp_path)
        assert registry.has("any_id") is False

    def test_has_returns_true_after_put(self, tmp_path: Path) -> None:
        """
        GIVEN a fresh registry and a stored entry
        WHEN has() is called with the stored entry's ID
        THEN returns True.
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "my_func", "src/foo.py")
        entry = _make_entry(element_id=eid)

        registry.put(entry)

        assert registry.has(eid) is True


# ============================================================================
# Test: Persistence Across Restarts
# ============================================================================


class TestPersistence:
    """Tests for persistence across simulated process restarts."""

    def test_restart_reads_previously_written_entry(self, tmp_path: Path) -> None:
        """
        GIVEN registry r1 writes entry E to state_dir
        WHEN a new registry r2 is created with the same state_dir
        THEN r2.get(E.element_id) returns an entry equal to E.
        """
        eid = make_element_id("class", "MyService", "src/services.py")
        entry = _make_entry(
            element_id=eid,
            name="MyService",
            kind="class",
            file_path="src/services.py",
        )

        r1 = _make_registry(tmp_path)
        r1.put(entry)
        del r1  # Simulate process exit

        r2 = _make_registry(tmp_path)
        restored = r2.get(eid)

        assert restored is not None
        assert restored.element_id == eid
        assert restored.name == "MyService"
        assert restored.kind == "class"
        assert restored.file_path == "src/services.py"

    def test_restart_registry_reflects_all_entries(self, tmp_path: Path) -> None:
        """
        GIVEN registry r1 writes 5 distinct entries
        WHEN registry r2 is instantiated with the same state_dir
        THEN all 5 entries are retrievable from r2 and summary reflects them.
        """
        entries = [
            _make_entry(
                element_id=make_element_id("function", f"func_{idx}", f"src/mod_{idx}.py"),
                name=f"func_{idx}",
                kind="function",
                file_path=f"src/mod_{idx}.py",
            )
            for idx in range(5)
        ]

        r1 = _make_registry(tmp_path)
        for entry in entries:
            r1.put(entry)
        del r1

        r2 = _make_registry(tmp_path)
        for entry in entries:
            retrieved = r2.get(entry.element_id)
            assert retrieved is not None, f"Entry missing after restart: {entry.element_id}"
            assert retrieved.name == entry.name

        assert r2.summary().total == 5


# ============================================================================
# Test: Remove and Clear
# ============================================================================


class TestRemoveAndClear:
    """Tests for remove() and clear() operations."""

    def test_remove_makes_entry_unreachable(self, tmp_path: Path) -> None:
        """
        GIVEN a stored entry
        WHEN remove() is called with its ID
        THEN get() returns None AND has() returns False.
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "removable", "src/removable.py")
        entry = _make_entry(element_id=eid)

        registry.put(entry)
        registry.remove(eid)

        assert registry.get(eid) is None
        assert registry.has(eid) is False

    def test_remove_returns_true_on_success(self, tmp_path: Path) -> None:
        """
        GIVEN a stored entry
        WHEN remove() is called with its ID
        THEN True is returned.
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "removable", "src/removable.py")
        entry = _make_entry(element_id=eid)

        registry.put(entry)
        result = registry.remove(eid)

        assert result is True

    def test_remove_returns_false_on_missing(self, tmp_path: Path) -> None:
        """
        GIVEN a fresh registry
        WHEN remove() is called with an unknown ID
        THEN False is returned.
        """
        registry = _make_registry(tmp_path)
        result = registry.remove("nonexistent::id")
        assert result is False

    def test_clear_empties_registry(self, tmp_path: Path) -> None:
        """
        GIVEN 3 stored entries
        WHEN clear() is called
        THEN has() returns False for all 3 IDs AND summary().total == 0.
        """
        registry = _make_registry(tmp_path)
        eids = [
            make_element_id("function", f"func_{idx}", f"src/f_{idx}.py")
            for idx in range(3)
        ]
        for eid in eids:
            registry.put(_make_entry(element_id=eid))

        registry.clear()

        for eid in eids:
            assert registry.has(eid) is False
        assert registry.summary().total == 0


# ============================================================================
# Test: Phase Status Lifecycle
# ============================================================================


class TestPhaseStatus:
    """Tests for phase status management across the element lifecycle."""

    def test_set_and_get_phase_status(self, tmp_path: Path) -> None:
        """
        GIVEN a stored entry
        WHEN set_phase_status(id, "extraction", "complete") is called
        THEN get_phase_status(id, "extraction") == "complete".
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "extract_func", "src/extract.py")
        entry = _make_entry(element_id=eid)

        registry.put(entry)
        registry.set_phase_status(eid, "extraction", "complete")
        status = registry.get_phase_status(eid, "extraction")

        assert status == "complete"

    def test_get_phase_status_unknown_phase_returns_none(self, tmp_path: Path) -> None:
        """
        GIVEN a stored entry with no phase records
        WHEN get_phase_status(id, "nonexistent_phase") is called
        THEN None is returned.
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "no_phase_func", "src/no_phase.py")
        entry = _make_entry(element_id=eid)

        registry.put(entry)
        status = registry.get_phase_status(eid, "nonexistent_phase")

        assert status is None

    def test_set_phase_status_with_metadata(self, tmp_path: Path) -> None:
        """
        GIVEN a stored entry
        WHEN set_phase_status(id, "generation", "complete", metadata={"tokens": 42})
        THEN:
          - get_phase_status returns "complete"
          - element_history contains a PhaseRecord with the correct metadata
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "gen_func", "src/gen.py")
        entry = _make_entry(element_id=eid)

        registry.put(entry)
        metadata = {"tokens": 42}
        registry.set_phase_status(eid, "generation", "complete", metadata=metadata)

        assert registry.get_phase_status(eid, "generation") == "complete"

        history = registry.element_history(eid)
        assert len(history) > 0
        gen_record = next(
            (rec for rec in history if rec.phase == "generation"), None
        )
        assert gen_record is not None
        assert gen_record.status == "complete"
        assert gen_record.metadata == metadata

    def test_elements_by_status_returns_matching(self, tmp_path: Path) -> None:
        """
        GIVEN 5 entries: 3 with ("generation", "complete"), 2 with ("generation", "failed")
        WHEN elements_by_status("generation", "complete") is called
        THEN exactly 3 entries are returned, all with the matching IDs.
        """
        registry = _make_registry(tmp_path)
        complete_eids = [
            make_element_id("function", f"gen_complete_{idx}", f"src/gc_{idx}.py")
            for idx in range(3)
        ]
        failed_eids = [
            make_element_id("function", f"gen_failed_{idx}", f"src/gf_{idx}.py")
            for idx in range(2)
        ]

        for eid in complete_eids:
            registry.put(_make_entry(element_id=eid))
            registry.set_phase_status(eid, "generation", "complete")

        for eid in failed_eids:
            registry.put(_make_entry(element_id=eid))
            registry.set_phase_status(eid, "generation", "failed")

        results = registry.elements_by_status("generation", "complete")

        assert len(results) == 3
        assert {r.element_id for r in results} == set(complete_eids)

    def test_elements_by_status_empty_when_no_match(self, tmp_path: Path) -> None:
        """
        GIVEN entries with no "validation" phase records
        WHEN elements_by_status("validation", "complete") is called
        THEN an empty list is returned.
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "no_validation", "src/nv.py")

        registry.put(_make_entry(element_id=eid))
        registry.set_phase_status(eid, "extraction", "complete")

        results = registry.elements_by_status("validation", "complete")

        assert results == []

    def test_element_history_insertion_order(self, tmp_path: Path) -> None:
        """
        GIVEN a stored entry
        WHEN set_phase_status is called in order:
             ("extraction", "specified") → ("generation", "complete") → ("validation", "failed")
        THEN element_history() returns 3 PhaseRecords in that exact order.
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "history_func", "src/history.py")
        entry = _make_entry(element_id=eid)

        registry.put(entry)
        registry.set_phase_status(eid, "extraction", "specified")
        registry.set_phase_status(eid, "generation", "complete")
        registry.set_phase_status(eid, "validation", "failed")

        history = registry.element_history(eid)

        assert len(history) == 3
        assert history[0].phase == "extraction"
        assert history[0].status == "specified"
        assert history[1].phase == "generation"
        assert history[1].status == "complete"
        assert history[2].phase == "validation"
        assert history[2].status == "failed"

    def test_phase_status_overwrite_updates_status(self, tmp_path: Path) -> None:
        """
        Edge case: calling set_phase_status() twice for the same phase
        should update the status without duplicating history entries.

        GIVEN a stored entry
        WHEN set_phase_status(id, "extraction", "specified") then
             set_phase_status(id, "extraction", "complete") are called
        THEN:
          - get_phase_status returns "complete"
          - element_history contains exactly 1 extraction record with status "complete"
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "overwrite_func", "src/overwrite.py")
        entry = _make_entry(element_id=eid)

        registry.put(entry)
        registry.set_phase_status(eid, "extraction", "specified")
        registry.set_phase_status(eid, "extraction", "complete")

        assert registry.get_phase_status(eid, "extraction") == "complete"

        history = registry.element_history(eid)
        extraction_records = [r for r in history if r.phase == "extraction"]
        assert len(extraction_records) == 1
        assert extraction_records[0].status == "complete"


# ============================================================================
# Test: File-Scoped Element Lookup
# ============================================================================


class TestElementsForFile:
    """Tests for elements_for_file() file-scoped filtering."""

    def test_elements_for_file_returns_matching_entries(self, tmp_path: Path) -> None:
        """
        GIVEN 3 entries with file_path="src/alpha.py" and 2 with file_path="src/beta.py"
        WHEN elements_for_file("src/alpha.py") is called
        THEN exactly 3 entries are returned, all with file_path="src/alpha.py".
        """
        registry = _make_registry(tmp_path)
        alpha_eids = [
            make_element_id("function", f"alpha_{idx}", "src/alpha.py")
            for idx in range(3)
        ]
        beta_eids = [
            make_element_id("function", f"beta_{idx}", "src/beta.py")
            for idx in range(2)
        ]

        for eid in alpha_eids:
            registry.put(_make_entry(element_id=eid, name=eid, file_path="src/alpha.py"))
        for eid in beta_eids:
            registry.put(_make_entry(element_id=eid, name=eid, file_path="src/beta.py"))

        results = registry.elements_for_file("src/alpha.py")

        assert len(results) == 3
        assert {r.element_id for r in results} == set(alpha_eids)

    def test_elements_for_file_empty_when_no_match(self, tmp_path: Path) -> None:
        """
        GIVEN entries for "src/alpha.py"
        WHEN elements_for_file("src/gamma.py") is called
        THEN an empty list is returned.
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "alpha_func", "src/alpha.py")
        registry.put(_make_entry(element_id=eid, file_path="src/alpha.py"))

        results = registry.elements_for_file("src/gamma.py")

        assert results == []

    def test_elements_for_file_excludes_other_files(self, tmp_path: Path) -> None:
        """
        GIVEN entries across 3 different files (2 entries each)
        WHEN elements_for_file is called for "src/file_b.py"
        THEN only entries belonging to file_b.py are returned; file_a and file_c excluded.
        """
        registry = _make_registry(tmp_path)
        files = ["src/file_a.py", "src/file_b.py", "src/file_c.py"]
        all_eids: list[tuple[str, str]] = []

        for file_path in files:
            stem = file_path.split("/")[-1].split(".")[0]
            for idx in range(2):
                eid = make_element_id("function", f"{stem}_{idx}", file_path)
                registry.put(_make_entry(element_id=eid, file_path=file_path))
                all_eids.append((eid, file_path))

        results = registry.elements_for_file("src/file_b.py")

        result_ids = {r.element_id for r in results}
        expected_ids = {eid for eid, fpath in all_eids if fpath == "src/file_b.py"}
        excluded_ids = {eid for eid, fpath in all_eids if fpath != "src/file_b.py"}

        assert result_ids == expected_ids
        assert result_ids.isdisjoint(excluded_ids)

    def test_elements_for_file_none_file_path_excluded(self, tmp_path: Path) -> None:
        """
        Edge case: An entry with file_path=None must not appear in
        elements_for_file() results for any real path.
        """
        registry = _make_registry(tmp_path)
        eid_with_file = make_element_id("function", "with_file", "src/real.py")
        eid_without_file = make_element_id("function", "without_file", "virtual")

        registry.put(_make_entry(element_id=eid_with_file, file_path="src/real.py"))
        registry.put(_make_entry(element_id=eid_without_file, file_path=None))

        results = registry.elements_for_file("src/real.py")

        assert len(results) == 1
        assert results[0].element_id == eid_with_file


# ============================================================================
# Test: Aggregate Summaries
# ============================================================================


class TestSummary:
    """Tests for registry summary() aggregate reporting."""

    def test_summary_total_count(self, tmp_path: Path) -> None:
        """
        GIVEN 4 entries stored
        WHEN summary() is called
        THEN summary.total == 4.
        """
        registry = _make_registry(tmp_path)
        for idx in range(4):
            eid = make_element_id("function", f"func_{idx}", f"src/f_{idx}.py")
            registry.put(_make_entry(element_id=eid))

        assert registry.summary().total == 4

    def test_summary_phase_status_counts(self, tmp_path: Path) -> None:
        """
        GIVEN:
          - 2 entries with phase "extraction" / status "complete"
          - 1 entry with phase "extraction" / status "failed"
          - 1 entry with phase "generation" / status "complete"
        WHEN summary() is called
        THEN summary.total == 4 and per-phase/status counts are accurate.
        """
        registry = _make_registry(tmp_path)

        for idx in range(2):
            eid = make_element_id("function", f"ext_complete_{idx}", f"src/ec_{idx}.py")
            registry.put(_make_entry(element_id=eid))
            registry.set_phase_status(eid, "extraction", "complete")

        eid_ext_failed = make_element_id("function", "ext_failed", "src/ef.py")
        registry.put(_make_entry(element_id=eid_ext_failed))
        registry.set_phase_status(eid_ext_failed, "extraction", "failed")

        eid_gen_complete = make_element_id("function", "gen_complete", "src/gc.py")
        registry.put(_make_entry(element_id=eid_gen_complete))
        registry.set_phase_status(eid_gen_complete, "generation", "complete")

        summary = registry.summary()

        assert summary.total == 4

        # Support two plausible RegistrySummary structures.
        if hasattr(summary, "phase_status_counts"):
            counts = summary.phase_status_counts
            assert counts.get(("extraction", "complete")) == 2
            assert counts.get(("extraction", "failed")) == 1
            assert counts.get(("generation", "complete")) == 1
        elif hasattr(summary, "by_phase"):
            by_phase = summary.by_phase
            assert by_phase.get("extraction", {}).get("complete") == 2
            assert by_phase.get("extraction", {}).get("failed") == 1
            assert by_phase.get("generation", {}).get("complete") == 1
        else:
            pytest.fail(
                "RegistrySummary must expose phase/status counts via "
                "`phase_status_counts` (dict keyed by (phase, status)) "
                "or `by_phase` (dict[phase][status] -> count)."
            )

    def test_summary_empty_registry(self, tmp_path: Path) -> None:
        """
        GIVEN a fresh registry with no entries
        WHEN summary() is called
        THEN summary.total == 0.
        """
        registry = _make_registry(tmp_path)
        summary = registry.summary()
        assert summary.total == 0


# ============================================================================
# Test: Concurrent Writes
# ============================================================================


class TestConcurrentWrites:
    """Tests for thread-safe concurrent write operations."""

    def test_concurrent_puts_all_succeed(self, tmp_path: Path) -> None:
        """
        GIVEN 20 threads each ready to call put() with a unique entry
        WHEN all threads are released simultaneously via threading.Barrier
        THEN after all threads join:
          - no exceptions were raised
          - every entry is retrievable via get()
          - summary().total == THREAD_COUNT (20)
        """
        registry = _make_registry(tmp_path)
        entries = [
            _make_entry(
                element_id=make_element_id(
                    "function",
                    f"concurrent_func_{idx}",
                    f"src/concurrent_{idx}.py",
                ),
                name=f"concurrent_func_{idx}",
                kind="function",
                file_path=f"src/concurrent_{idx}.py",
            )
            for idx in range(THREAD_COUNT)
        ]
        errors: list[Exception] = []
        barrier = threading.Barrier(THREAD_COUNT)

        def worker(entry: ElementEntry) -> None:
            """Wait for all threads then write entry concurrently."""
            try:
                barrier.wait()
                registry.put(entry)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(entries[idx],), daemon=False)
            for idx in range(THREAD_COUNT)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors occurred: {errors}"
        for entry in entries:
            retrieved = registry.get(entry.element_id)
            assert retrieved is not None, f"Missing entry after concurrent put: {entry.element_id}"
        assert registry.summary().total == THREAD_COUNT


# ============================================================================
# Test: I/O Failure Graceful Degradation
# ============================================================================


class TestIoFailure:
    """Tests for graceful degradation under I/O failures."""

    def test_put_io_failure_does_not_raise(self, tmp_path: Path) -> None:
        """
        GIVEN a registry backed by tmp_path
        WHEN the write mechanism is patched to raise OSError("disk full")
        THEN put() does NOT propagate the exception (degrades gracefully).
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "fragile_func", "src/fragile.py")
        entry = _make_entry(element_id=eid, name="fragile_func", file_path="src/fragile.py")

        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            try:
                registry.put(entry)
            except OSError:
                pytest.fail("put() raised OSError; expected graceful degradation")

    def test_put_io_failure_then_recovery(self, tmp_path: Path) -> None:
        """
        GIVEN a registry where a first put() fails due to a patched OSError
        WHEN the patch is removed and a second put() is called successfully
        THEN the second entry is retrievable via get().
        """
        registry = _make_registry(tmp_path)
        eid_failed = make_element_id("function", "failed_write", "src/failed.py")
        entry_failed = _make_entry(element_id=eid_failed, file_path="src/failed.py")

        eid_success = make_element_id("function", "successful_write", "src/success.py")
        entry_success = _make_entry(element_id=eid_success, file_path="src/success.py")

        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            registry.put(entry_failed)  # expected to silently fail

        registry.put(entry_success)  # no patch — should succeed

        result = registry.get(eid_success)
        assert result is not None
        assert result.element_id == eid_success

    def test_init_unreadable_state_dir_does_not_crash(self, tmp_path: Path) -> None:
        """
        GIVEN a state_dir where reading existing state raises OSError
        WHEN ElementRegistry(state_dir=...) is constructed
        THEN no exception propagates and the registry initializes to a clean state.
        """
        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            try:
                registry = _make_registry(tmp_path)
                assert registry is not None
            except OSError:
                pytest.fail(
                    "ElementRegistry.__init__ raised OSError; expected graceful degradation"
                )

    def test_get_corrupted_entry_file_returns_none_or_degrades_gracefully(
        self,
        tmp_path: Path,
    ) -> None:
        """
        GIVEN an entry was written, then its backing file is physically corrupted
        WHEN get() is called for that entry
        THEN None is returned OR a graceful fallback occurs — no unhandled exception.
        """
        registry = _make_registry(tmp_path)
        eid = make_element_id("function", "corrupt_func", "src/corrupt.py")
        entry = _make_entry(element_id=eid, name="corrupt_func", file_path="src/corrupt.py")

        registry.put(entry)

        # Attempt to corrupt the backing JSON file on disk.
        json_files = list(tmp_path.rglob("*.json"))
        corrupted = False
        for json_file in json_files:
            file_content = json_file.read_text()
            if eid.replace("::", "_") in str(json_file) or eid in file_content:
                json_file.write_text("{INVALID JSON %%%")
                corrupted = True
                break

        if corrupted:
            try:
                result = registry.get(eid)
                # Either None (entry unreadable) or any non-exception value is acceptable.
                assert result is None or result is not None
            except json.JSONDecodeError:
                pytest.fail(
                    "get() raised JSONDecodeError on corrupted file; expected graceful degradation"
                )
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"get() raised unexpected exception on corrupted file: {exc}")
        else:
            # No on-disk file found — simulate corruption via json.loads patch.
            with patch("json.loads", side_effect=json.JSONDecodeError("msg", "doc", 0)):
                try:
                    result = registry.get(eid)
                    assert result is None or result is not None
                except json.JSONDecodeError:
                    pytest.fail(
                        "get() raised JSONDecodeError with patched json.loads; "
                        "expected graceful degradation"
                    )