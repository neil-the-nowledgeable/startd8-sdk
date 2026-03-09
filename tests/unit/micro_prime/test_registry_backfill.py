"""Tests for L6: cloud fallback → element registry backfill."""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from startd8.element_registry import ElementEntry


@pytest.fixture
def mock_registry():
    """Create a mock ElementRegistry that stores entries in a dict."""
    registry = MagicMock()
    storage: dict[str, ElementEntry] = {}

    def put(entry):
        storage[entry.element_id] = entry

    def get(element_id):
        return storage.get(element_id)

    registry.put = MagicMock(side_effect=put)
    registry.get = MagicMock(side_effect=get)
    registry.set_phase_status = MagicMock()
    registry._storage = storage
    return registry


@pytest.fixture
def adapter(mock_registry, tmp_path):
    """Create a MicroPrimeCodeGenerator with mock registry."""
    from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

    return MicroPrimeCodeGenerator(
        element_registry=mock_registry,
        output_dir=tmp_path,
    )


class TestBackfillExtractsFunctions:
    def test_three_functions(self, adapter, mock_registry, tmp_path):
        code = textwrap.dedent("""\
            def foo():
                return 1

            def bar():
                return 2

            def baz():
                return 3
        """)
        f = tmp_path / "module.py"
        f.write_text(code)

        count = adapter._backfill_registry_from_cloud([str(f)], "feat-1")
        assert count == 3
        assert mock_registry.put.call_count == 3


class TestBackfillExtractsClasses:
    def test_class_entry(self, adapter, mock_registry, tmp_path):
        code = textwrap.dedent("""\
            class MyService:
                def handle(self):
                    return True
        """)
        f = tmp_path / "service.py"
        f.write_text(code)

        count = adapter._backfill_registry_from_cloud([str(f)], "feat-2")
        # Should get class + method
        assert count >= 1
        entries = list(mock_registry._storage.values())
        class_entries = [e for e in entries if e.kind == "class"]
        assert len(class_entries) == 1
        assert class_entries[0].name == "MyService"


class TestBackfillExtractsMethodsWithParent:
    def test_method_has_parent_class(self, adapter, mock_registry, tmp_path):
        code = textwrap.dedent("""\
            class Server:
                def start(self):
                    pass

                def stop(self):
                    pass
        """)
        f = tmp_path / "server.py"
        f.write_text(code)

        count = adapter._backfill_registry_from_cloud([str(f)], "feat-3")
        entries = list(mock_registry._storage.values())
        method_entries = [e for e in entries if e.kind == "function"]
        assert all(e.parent_class == "Server" for e in method_entries)


class TestBackfillSkipsNonPython:
    def test_dockerfile_ignored(self, adapter, mock_registry, tmp_path):
        f = tmp_path / "Dockerfile"
        f.write_text("FROM python:3.11\n")

        count = adapter._backfill_registry_from_cloud([str(f)], "feat-4")
        assert count == 0


class TestBackfillSkipsSyntaxError:
    def test_broken_file_no_crash(self, adapter, mock_registry, tmp_path):
        f = tmp_path / "broken.py"
        f.write_text("def foo(\n")

        count = adapter._backfill_registry_from_cloud([str(f)], "feat-5")
        assert count == 0


class TestBackfillSetsGeneratorCloud:
    def test_generator_metadata(self, adapter, mock_registry, tmp_path):
        code = "def hello():\n    return 'world'\n"
        f = tmp_path / "hello.py"
        f.write_text(code)

        adapter._backfill_registry_from_cloud([str(f)], "feat-6")
        entries = list(mock_registry._storage.values())
        assert len(entries) >= 1
        assert entries[0].extra["generator"] == "cloud-backfill"
        assert entries[0].extra["feature_id"] == "feat-6"


class TestBackfillNoRegistry:
    def test_no_registry_returns_zero(self, tmp_path):
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator(
            element_registry=None,
            output_dir=tmp_path,
        )
        f = tmp_path / "module.py"
        f.write_text("def foo(): return 1\n")
        count = adapter._backfill_registry_from_cloud([str(f)], "feat-7")
        assert count == 0
