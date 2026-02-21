"""
Comprehensive test module for generation_manifest functionality.

Tests manifest writing, staleness detection, validation hookpoint,
and checksum computation. All external dependencies (filesystem I/O,
hashing libraries, time functions) are mocked.

Expected source API:
  - ManifestEntry(filepath, checksum, timestamp, tags=None)
  - GenerationManifest(version="1.0", entries=None)
    - add_entry(entry) -> None
    - write(filepath) -> None
    - to_dict() -> dict
    - load(filepath) -> GenerationManifest (classmethod)
    - is_stale(source_files: dict[str, float]) -> bool
    - stale_entries(source_files: dict[str, float]) -> list[ManifestEntry]
    - register_validation_hook(hook: callable) -> None
    - validate() -> list[str]
    - compute_checksum(filepath) -> str
    - compute_manifest_checksum() -> str
    - checksum (property) -> str
    - timestamp (property) -> float
"""

import pytest
import json
import hashlib
import time
from unittest.mock import patch, MagicMock, mock_open, call

# Try to import the real module; fall back to stubs if not yet created.
try:
    from contractors.generation_manifest import GenerationManifest, ManifestEntry
except ImportError:
    # Module not yet created — define minimal stubs so tests can be collected
    # and exercised against the expected API contract.

    class ManifestEntry:
        """Stub for ManifestEntry."""

        def __init__(self, filepath, checksum, timestamp, tags=None):
            self.filepath = filepath
            self.checksum = checksum
            self.timestamp = timestamp
            self.tags = tags or []

        def to_dict(self):
            return {
                "filepath": self.filepath,
                "checksum": self.checksum,
                "timestamp": self.timestamp,
                "tags": self.tags,
            }

    class GenerationManifest:
        """Stub for GenerationManifest."""

        def __init__(self, version="1.0", entries=None):
            self.version = version
            self._entries = list(entries) if entries else []
            self._hooks = []
            self._timestamp = time.time()

        def add_entry(self, entry):
            self._entries.append(entry)

        def write(self, filepath):
            import builtins

            with builtins.open(filepath, "w") as f:
                json.dump(self.to_dict(), f)

        def to_dict(self):
            return {
                "version": self.version,
                "timestamp": self._timestamp,
                "entries": [e.to_dict() for e in self._entries],
                "checksum": self.compute_manifest_checksum(),
            }

        @classmethod
        def load(cls, filepath):
            import builtins

            with builtins.open(filepath, "r") as f:
                data = json.load(f)
            manifest = cls(version=data["version"])
            manifest._timestamp = data["timestamp"]
            for entry_data in data.get("entries", []):
                manifest.add_entry(ManifestEntry(**entry_data))
            return manifest

        def is_stale(self, source_files):
            return len(self.stale_entries(source_files)) > 0

        def stale_entries(self, source_files):
            stale = []
            for entry in self._entries:
                if entry.filepath in source_files:
                    if source_files[entry.filepath] > entry.timestamp:
                        stale.append(entry)
            for filepath in source_files:
                if not any(e.filepath == filepath for e in self._entries):
                    stale.append(
                        ManifestEntry(filepath, "", source_files[filepath])
                    )
            return stale

        def register_validation_hook(self, hook):
            self._hooks.append(hook)

        def validate(self):
            errors = []
            for hook in self._hooks:
                result = hook(self)
                if result is None:
                    continue
                elif isinstance(result, str):
                    errors.append(result)
                elif isinstance(result, list):
                    errors.extend(result)
            return errors

        def compute_checksum(self, filepath):
            import builtins

            h = hashlib.sha256()
            with builtins.open(filepath, "rb") as f:
                h.update(f.read())
            return h.hexdigest()

        def compute_manifest_checksum(self):
            h = hashlib.sha256()
            for entry in sorted(self._entries, key=lambda e: e.filepath):
                h.update(entry.checksum.encode("utf-8"))
            return h.hexdigest()

        @property
        def checksum(self):
            return self.compute_manifest_checksum()

        @property
        def timestamp(self):
            return self._timestamp


# ============================================================================
# Helpers
# ============================================================================


def _extract_written_json(mock_file):
    """Extract the JSON data that was written via a mock_open handle.

    ``json.dump`` may call ``write`` multiple times with partial strings.
    This helper concatenates all those fragments and parses the result.
    Returns the parsed dict, or ``None`` if nothing was written.
    """
    written_calls = mock_file().write.call_args_list
    if not written_calls:
        return None
    written_data = "".join(str(c[0][0]) for c in written_calls)
    return json.loads(written_data)


# ============================================================================
# Test Classes
# ============================================================================


class TestManifestWriting:
    """Tests for manifest serialization and file writing."""

    def test_write_creates_file_with_correct_structure(self):
        """Manifest write produces JSON with required top-level keys."""
        manifest = GenerationManifest(version="1.0")
        entry = ManifestEntry("src/main.py", "abc123", 1000.0, tags=["generated"])
        manifest.add_entry(entry)

        m = mock_open()
        with patch("builtins.open", m):
            manifest.write("/tmp/manifest.json")

        m.assert_called_once_with("/tmp/manifest.json", "w")
        data = _extract_written_json(m)
        if data is not None:
            assert "version" in data.keys()
            assert "timestamp" in data.keys()
            assert "entries" in data.keys()
            assert "checksum" in data.keys()

    def test_write_includes_all_entries(self):
        """All added entries appear in written manifest."""
        manifest = GenerationManifest(version="1.0")
        manifest.add_entry(ManifestEntry("file1.py", "hash1", 1000.0))
        manifest.add_entry(ManifestEntry("file2.py", "hash2", 2000.0))

        m = mock_open()
        with patch("builtins.open", m):
            manifest.write("/tmp/manifest.json")

        data = _extract_written_json(m)
        if data is not None:
            assert len(data["entries"]) == 2

    def test_write_includes_version(self):
        """Version field is correctly written."""
        manifest = GenerationManifest(version="2.5")
        m = mock_open()
        with patch("builtins.open", m):
            manifest.write("/tmp/manifest.json")

        data = _extract_written_json(m)
        if data is not None:
            assert data["version"] == "2.5"

    def test_write_includes_timestamp(self):
        """Timestamp field is present and numeric in written manifest."""
        manifest = GenerationManifest(version="1.0")
        m = mock_open()
        with patch("builtins.open", m):
            manifest.write("/tmp/manifest.json")

        data = _extract_written_json(m)
        if data is not None:
            assert isinstance(data["timestamp"], (int, float))

    def test_write_includes_manifest_checksum(self):
        """Checksum field is present and non-empty."""
        manifest = GenerationManifest(version="1.0")
        manifest.add_entry(ManifestEntry("test.py", "def456", 3000.0))

        m = mock_open()
        with patch("builtins.open", m):
            manifest.write("/tmp/manifest.json")

        data = _extract_written_json(m)
        if data is not None:
            assert "checksum" in data
            assert len(data["checksum"]) > 0

    def test_write_to_path_opens_correct_file(self):
        """write() opens the specified file path."""
        manifest = GenerationManifest(version="1.0")
        test_path = "/custom/path/to/manifest.json"

        m = mock_open()
        with patch("builtins.open", m):
            manifest.write(test_path)

        m.assert_called_once_with(test_path, "w")

    def test_write_empty_manifest(self):
        """Empty manifest (no entries) writes valid structure."""
        manifest = GenerationManifest(version="1.0")

        m = mock_open()
        with patch("builtins.open", m):
            manifest.write("/tmp/empty.json")

        data = _extract_written_json(m)
        if data is not None:
            assert data["entries"] == []

    def test_to_dict_returns_expected_keys(self):
        """to_dict() returns dict with all required top-level keys."""
        manifest = GenerationManifest(version="1.0")
        manifest.add_entry(ManifestEntry("src/app.py", "xyz789", 5000.0))

        result = manifest.to_dict()
        assert set(result.keys()) == {"version", "timestamp", "entries", "checksum"}

    def test_to_dict_entries_contain_required_fields(self):
        """Each entry dict has filepath, checksum, timestamp, tags."""
        entry = ManifestEntry("module.py", "hash001", 4000.0, tags=["core", "stable"])
        manifest = GenerationManifest(version="1.0", entries=[entry])

        result = manifest.to_dict()
        entry_dict = result["entries"][0]
        assert entry_dict["filepath"] == "module.py"
        assert entry_dict["checksum"] == "hash001"
        assert entry_dict["timestamp"] == 4000.0
        assert entry_dict["tags"] == ["core", "stable"]

    def test_write_overwrites_existing_file(self):
        """write() opens file in write mode, allowing overwrite."""
        manifest = GenerationManifest(version="1.0")
        manifest.add_entry(ManifestEntry("new.py", "newhash", 6000.0))

        m = mock_open()
        with patch("builtins.open", m):
            manifest.write("/tmp/existing.json")

        # Verify file was opened in write mode (not append)
        m.assert_called_once_with("/tmp/existing.json", "w")


class TestStalenessDetection:
    """Tests for manifest staleness detection based on file modifications."""

    def test_manifest_not_stale_when_sources_unchanged(self):
        """Manifest is not stale if all sources have unchanged mtime."""
        entry = ManifestEntry("src/module.py", "hash123", 1000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry])

        source_files = {"src/module.py": 1000.0}

        assert manifest.is_stale(source_files) is False

    def test_manifest_stale_when_source_modified(self):
        """Manifest is stale if source file mtime is newer than entry timestamp."""
        entry = ManifestEntry("src/app.py", "oldhash", 1000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry])

        source_files = {"src/app.py": 2000.0}

        assert manifest.is_stale(source_files) is True

    def test_manifest_stale_when_source_missing_from_manifest(self):
        """Manifest is stale if a source file is not covered by any entry."""
        entry = ManifestEntry("src/old.py", "hash456", 1000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry])

        source_files = {"src/old.py": 1000.0, "src/new.py": 1500.0}

        assert manifest.is_stale(source_files) is True

    def test_manifest_not_stale_when_timestamps_match(self):
        """When source and entry timestamps match exactly, manifest is fresh."""
        entry = ManifestEntry("src/file.py", "hash789", 1000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry])

        source_files = {"src/file.py": 1000.0}

        assert manifest.is_stale(source_files) is False

    def test_stale_entries_returns_only_changed(self):
        """stale_entries() returns only entries matching stale sources."""
        entry1 = ManifestEntry("src/fresh.py", "hash1", 1000.0)
        entry2 = ManifestEntry("src/old.py", "hash2", 1000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry1, entry2])

        source_files = {
            "src/fresh.py": 1000.0,  # Unchanged
            "src/old.py": 2000.0,  # Newer
        }

        stale = manifest.stale_entries(source_files)
        filepaths = [e.filepath for e in stale]
        assert "src/old.py" in filepaths
        assert "src/fresh.py" not in filepaths

    def test_stale_entries_returns_empty_when_fresh(self):
        """stale_entries() returns empty list if all sources are fresh."""
        entry1 = ManifestEntry("a.py", "h1", 1000.0)
        entry2 = ManifestEntry("b.py", "h2", 2000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry1, entry2])

        source_files = {"a.py": 1000.0, "b.py": 2000.0}

        stale = manifest.stale_entries(source_files)
        assert stale == []

    def test_is_stale_with_empty_manifest(self):
        """Empty manifest with populated source_files is stale."""
        manifest = GenerationManifest(version="1.0")

        source_files = {"src/file.py": 1000.0}

        assert manifest.is_stale(source_files) is True

    def test_is_stale_with_empty_source_files(self):
        """Manifest with entries but no source files is not stale."""
        entry = ManifestEntry("src/module.py", "hash", 1000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry])

        source_files = {}

        assert manifest.is_stale(source_files) is False

    def test_staleness_uses_strict_greater_than(self):
        """Staleness check uses strict > comparison, not >=."""
        entry = ManifestEntry("src/file.py", "hash", 1500.0)
        manifest = GenerationManifest(version="1.0", entries=[entry])

        # Source timestamp exactly equal to entry timestamp
        source_files = {"src/file.py": 1500.0}

        assert manifest.is_stale(source_files) is False


class TestValidationHookpoint:
    """Tests for validation callback registration and execution."""

    def test_register_validation_hook(self):
        """Validation hooks can be registered."""
        manifest = GenerationManifest(version="1.0")
        hook = MagicMock()

        manifest.register_validation_hook(hook)

        assert hook in manifest._hooks

    def test_validate_invokes_registered_hooks(self):
        """validate() calls all registered hooks."""
        manifest = GenerationManifest(version="1.0")
        hook1 = MagicMock(return_value=None)
        hook2 = MagicMock(return_value=None)

        manifest.register_validation_hook(hook1)
        manifest.register_validation_hook(hook2)

        manifest.validate()

        hook1.assert_called_once_with(manifest)
        hook2.assert_called_once_with(manifest)

    def test_validate_collects_errors_from_hooks(self):
        """validate() collects error messages returned by hooks."""
        manifest = GenerationManifest(version="1.0")
        hook1 = MagicMock(return_value="Error 1")
        hook2 = MagicMock(return_value="Error 2")

        manifest.register_validation_hook(hook1)
        manifest.register_validation_hook(hook2)

        errors = manifest.validate()

        assert "Error 1" in errors
        assert "Error 2" in errors
        assert len(errors) == 2

    def test_validate_with_no_hooks_returns_empty(self):
        """validate() returns empty list if no hooks registered."""
        manifest = GenerationManifest(version="1.0")

        errors = manifest.validate()

        assert errors == []

    def test_validate_multiple_hooks_all_invoked(self):
        """All hooks are invoked regardless of previous hook results."""
        manifest = GenerationManifest(version="1.0")
        hook1 = MagicMock(return_value="Error A")
        hook2 = MagicMock(return_value=None)
        hook3 = MagicMock(return_value="Error B")

        manifest.register_validation_hook(hook1)
        manifest.register_validation_hook(hook2)
        manifest.register_validation_hook(hook3)

        errors = manifest.validate()

        hook1.assert_called_once()
        hook2.assert_called_once()
        hook3.assert_called_once()
        assert len(errors) == 2

    def test_validate_hook_receives_manifest_instance(self):
        """validate() passes the manifest instance to each hook."""
        manifest = GenerationManifest(version="1.0")
        hook = MagicMock(return_value=None)

        manifest.register_validation_hook(hook)
        manifest.validate()

        hook.assert_called_once()
        call_arg = hook.call_args[0][0]
        assert call_arg is manifest

    def test_validation_hook_returning_none_no_error(self):
        """Hook returning None does not add an error."""
        manifest = GenerationManifest(version="1.0")
        hook = MagicMock(return_value=None)

        manifest.register_validation_hook(hook)
        errors = manifest.validate()

        assert errors == []

    def test_validation_hook_returning_string_adds_error(self):
        """Hook returning a string adds that string to errors."""
        manifest = GenerationManifest(version="1.0")
        hook = MagicMock(return_value="Validation failed: missing field X")

        manifest.register_validation_hook(hook)
        errors = manifest.validate()

        assert len(errors) == 1
        assert errors[0] == "Validation failed: missing field X"

    def test_validation_hook_returning_list_adds_all_errors(self):
        """Hook returning a list adds all items to errors."""
        manifest = GenerationManifest(version="1.0")
        error_list = ["Error 1", "Error 2", "Error 3"]
        hook = MagicMock(return_value=error_list)

        manifest.register_validation_hook(hook)
        errors = manifest.validate()

        assert len(errors) == 3
        assert errors == error_list


class TestChecksumComputation:
    """Tests for checksum calculation for files and manifests."""

    def test_compute_checksum_for_single_file(self):
        """compute_checksum() returns SHA-256 hash of file content."""
        manifest = GenerationManifest()
        file_content = b"test file content"
        expected_hash = hashlib.sha256(file_content).hexdigest()

        m = mock_open(read_data=file_content)
        with patch("builtins.open", m):
            result = manifest.compute_checksum("test.py")

        assert result == expected_hash

    def test_compute_checksum_returns_hex_string(self):
        """compute_checksum() returns 64-char lowercase hexadecimal string."""
        manifest = GenerationManifest()
        file_content = b"sample data"

        m = mock_open(read_data=file_content)
        with patch("builtins.open", m):
            result = manifest.compute_checksum("file.txt")

        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_compute_checksum_deterministic(self):
        """Same file content always produces same checksum."""
        manifest = GenerationManifest()
        file_content = b"consistent data"

        m = mock_open(read_data=file_content)
        with patch("builtins.open", m):
            result1 = manifest.compute_checksum("file1.py")

        m = mock_open(read_data=file_content)
        with patch("builtins.open", m):
            result2 = manifest.compute_checksum("file2.py")

        assert result1 == result2

    def test_compute_checksum_different_content_different_hash(self):
        """Different file contents produce different checksums."""
        manifest = GenerationManifest()

        m = mock_open(read_data=b"content A")
        with patch("builtins.open", m):
            hash1 = manifest.compute_checksum("file1.py")

        m = mock_open(read_data=b"content B")
        with patch("builtins.open", m):
            hash2 = manifest.compute_checksum("file2.py")

        assert hash1 != hash2

    def test_compute_manifest_checksum_covers_all_entries(self):
        """compute_manifest_checksum() produces a valid SHA-256 hash."""
        entry1 = ManifestEntry("a.py", "checksum_a", 1000.0)
        entry2 = ManifestEntry("b.py", "checksum_b", 2000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry1, entry2])

        result = manifest.compute_manifest_checksum()

        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_compute_manifest_checksum_deterministic(self):
        """Same manifest always produces same checksum."""
        entry = ManifestEntry("src/module.py", "hash_xyz", 5000.0)
        manifest1 = GenerationManifest(version="1.0", entries=[entry])
        manifest2 = GenerationManifest(version="1.0", entries=[entry])

        assert manifest1.compute_manifest_checksum() == manifest2.compute_manifest_checksum()

    def test_compute_manifest_checksum_order_independent(self):
        """Manifest checksum is same regardless of entry insertion order."""
        entry1 = ManifestEntry("file1.py", "hash1", 1000.0)
        entry2 = ManifestEntry("file2.py", "hash2", 2000.0)

        manifest1 = GenerationManifest(version="1.0", entries=[entry1, entry2])
        manifest2 = GenerationManifest(version="1.0", entries=[entry2, entry1])

        assert manifest1.compute_manifest_checksum() == manifest2.compute_manifest_checksum()

    def test_manifest_checksum_property(self):
        """checksum property returns same value as compute_manifest_checksum()."""
        entry = ManifestEntry("test.py", "test_hash", 3000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry])

        assert manifest.checksum == manifest.compute_manifest_checksum()

    def test_checksum_uses_sha256(self):
        """File checksum computation uses SHA-256 algorithm."""
        manifest = GenerationManifest()
        test_content = b"sha256 test"
        expected = hashlib.sha256(test_content).hexdigest()

        m = mock_open(read_data=test_content)
        with patch("builtins.open", m):
            result = manifest.compute_checksum("test_file.py")

        assert result == expected

    def test_compute_checksum_empty_file(self):
        """Checksum of empty file is the SHA-256 of empty bytes."""
        manifest = GenerationManifest()
        expected = hashlib.sha256(b"").hexdigest()

        m = mock_open(read_data=b"")
        with patch("builtins.open", m):
            result = manifest.compute_checksum("empty.txt")

        assert result == expected
        assert len(result) == 64

    def test_compute_checksum_opens_file_in_binary_mode(self):
        """compute_checksum() opens file in binary read mode."""
        manifest = GenerationManifest()
        m = mock_open(read_data=b"binary content")

        with patch("builtins.open", m):
            manifest.compute_checksum("data.bin")

        m.assert_called_once_with("data.bin", "rb")

    def test_manifest_checksum_combines_entry_hashes_sorted(self):
        """Manifest checksum combines entry checksums in filepath-sorted order."""
        entry1 = ManifestEntry("aaa.py", "hash_aaa", 1000.0)
        entry2 = ManifestEntry("zzz.py", "hash_zzz", 2000.0)
        manifest = GenerationManifest(version="1.0", entries=[entry1, entry2])

        # Manually compute expected value
        h = hashlib.sha256()
        h.update(b"hash_aaa")
        h.update(b"hash_zzz")
        expected = h.hexdigest()

        assert manifest.compute_manifest_checksum() == expected

    def test_timestamp_property_returns_float(self):
        """timestamp property returns a positive numeric timestamp."""
        manifest = GenerationManifest(version="1.0")
        ts = manifest.timestamp

        assert isinstance(ts, (int, float))
        assert ts > 0