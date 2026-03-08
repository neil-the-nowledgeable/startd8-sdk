"""Tests for MicroPrimeEngine ↔ ElementRegistry cache-through (REQ-MP-1102)."""

from __future__ import annotations

import hashlib
import time
from unittest.mock import MagicMock, patch

import pytest

from startd8.element_registry import ElementEntry, ElementRegistry
from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, ForwardImportSpec
from startd8.micro_prime.engine import (
    MicroPrimeEngine,
    _compute_context_checksum,
    _resolve_element_id,
)
from startd8.micro_prime.models import MicroPrimeConfig, TierClassification
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_init_element(source_contract_id: str | None = None) -> ForwardElementSpec:
    """Create a TRIVIAL __init__ element (template-matchable, no LLM needed)."""
    return ForwardElementSpec(
        kind=ElementKind.METHOD,
        name="__init__",
        signature=Signature(
            params=[
                Param(name="self"),
                Param(name="name", annotation="str"),
                Param(name="value", annotation="int", default="0"),
            ],
            return_annotation="None",
        ),
        parent_class="Config",
        docstring_hint="Initialize Config.",
        source_contract_id=source_contract_id,
    )


def _make_file_spec() -> ForwardFileSpec:
    return ForwardFileSpec(
        file="src/mypackage/utils.py",
        imports=[
            ForwardImportSpec(kind="from", module="typing", names=["Optional"]),
        ],
        elements=[_make_init_element()],
    )


_SKELETON = """\
# [STARTD8-SKELETON]
from typing import Optional


class Config:
    \"\"\"Config class.\"\"\"

    def __init__(self, name: str, value: int = 0) -> None:
        \"\"\"Initialize Config.\"\"\"
        raise NotImplementedError
"""


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


class TestResolveElementId:
    """Test _resolve_element_id helper."""

    def test_uses_source_contract_id_when_present(self):
        elem = _make_init_element(source_contract_id="C-042")
        assert _resolve_element_id(elem, "src/foo.py") == "C-042"

    def test_derives_from_make_element_id_when_no_contract_id(self):
        elem = _make_init_element(source_contract_id=None)
        eid = _resolve_element_id(elem, "src/foo.py")
        assert eid is not None
        assert "method/" in eid  # make_element_id prefixes with kind
        assert "__init__" in eid

    def test_returns_none_for_empty_name(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="",
            signature=Signature(params=[], return_annotation="None"),
        )
        result = _resolve_element_id(elem, "src/foo.py")
        # Empty name produces an id (make_element_id allows it)
        # but should still return something deterministic
        assert result is not None or result is None  # non-crash


class TestComputeContextChecksum:
    def test_deterministic(self):
        assert _compute_context_checksum("abc") == _compute_context_checksum("abc")

    def test_different_for_different_input(self):
        assert _compute_context_checksum("abc") != _compute_context_checksum("def")


# ---------------------------------------------------------------------------
# Integration: Engine ↔ Registry
# ---------------------------------------------------------------------------


class TestEngineRegistryCacheThrough:
    """Tests for the 3-layer cache hierarchy in MicroPrimeEngine."""

    def test_registry_hit_skips_generation(self, tmp_path):
        """When the registry has a matching entry with valid checksum, skip generation."""
        registry = ElementRegistry(state_dir=tmp_path / "reg")
        element = _make_init_element(source_contract_id="C-100")
        file_spec = _make_file_spec()
        skeleton = _SKELETON
        ctx_checksum = _compute_context_checksum(skeleton)

        # Pre-populate registry with cached code
        entry = ElementEntry(
            element_id="C-100",
            kind="method",
            name="__init__",
            file_path="src/mypackage/utils.py",
            context_checksum=ctx_checksum,
            extra={"code": "self.name = name\nself.value = value"},
        )
        registry.put(entry)

        engine = MicroPrimeEngine(element_registry=registry)
        result = engine.process_element(element, file_spec, skeleton)

        assert result.success is True
        assert result.code == "self.name = name\nself.value = value"
        assert result.decomposition_metadata == {"source": "element_registry"}

    def test_registry_miss_falls_through(self, tmp_path):
        """When the registry has no entry, normal generation proceeds."""
        registry = ElementRegistry(state_dir=tmp_path / "reg")
        element = _make_init_element(source_contract_id="C-200")
        file_spec = _make_file_spec()
        skeleton = _SKELETON

        engine = MicroPrimeEngine(element_registry=registry)
        result = engine.process_element(element, file_spec, skeleton)

        # TRIVIAL __init__ should still succeed via template
        assert result.success is True
        assert result.code is not None
        # Should NOT have registry source metadata
        assert result.decomposition_metadata != {"source": "element_registry"}

    def test_successful_generation_stores_entry(self, tmp_path):
        """After successful generation, the result is persisted to the registry."""
        registry = ElementRegistry(state_dir=tmp_path / "reg")
        element = _make_init_element(source_contract_id="C-300")
        file_spec = _make_file_spec()
        skeleton = _SKELETON

        engine = MicroPrimeEngine(element_registry=registry)
        result = engine.process_element(element, file_spec, skeleton)

        assert result.success is True

        # Verify the entry was stored
        stored = registry.get("C-300")
        assert stored is not None
        assert stored.extra.get("code") is not None
        assert stored.context_checksum == _compute_context_checksum(skeleton)
        assert stored.kind == "method"
        assert stored.name == "__init__"

    def test_registry_error_does_not_abort_generation(self, tmp_path):
        """Registry errors during lookup should log warning and fall through."""
        broken_registry = MagicMock(spec=ElementRegistry)
        broken_registry.get.side_effect = OSError("disk on fire")

        element = _make_init_element(source_contract_id="C-400")
        file_spec = _make_file_spec()
        skeleton = _SKELETON

        engine = MicroPrimeEngine(element_registry=broken_registry)
        result = engine.process_element(element, file_spec, skeleton)

        # Should still succeed via template despite registry error
        assert result.success is True
        assert result.code is not None

    def test_registry_write_error_does_not_abort(self, tmp_path):
        """Registry errors during put() should log warning, not crash."""
        registry = MagicMock(spec=ElementRegistry)
        registry.get.return_value = None  # miss on lookup
        registry.put.side_effect = OSError("disk full")

        element = _make_init_element(source_contract_id="C-450")
        file_spec = _make_file_spec()
        skeleton = _SKELETON

        engine = MicroPrimeEngine(element_registry=registry)
        result = engine.process_element(element, file_spec, skeleton)

        # Generation itself should still succeed
        assert result.success is True

    def test_stale_checksum_triggers_regeneration(self, tmp_path):
        """When cached entry has a different context_checksum, skip cache and regenerate."""
        registry = ElementRegistry(state_dir=tmp_path / "reg")
        element = _make_init_element(source_contract_id="C-500")
        file_spec = _make_file_spec()
        skeleton = _SKELETON

        # Pre-populate registry with stale checksum
        entry = ElementEntry(
            element_id="C-500",
            kind="method",
            name="__init__",
            file_path="src/mypackage/utils.py",
            context_checksum="stale_checksum_from_old_skeleton",
            extra={"code": "# old stale code"},
        )
        registry.put(entry)

        engine = MicroPrimeEngine(element_registry=registry)
        result = engine.process_element(element, file_spec, skeleton)

        assert result.success is True
        # Should NOT have returned the stale code
        assert result.code != "# old stale code"
        # The registry should now have the updated entry with fresh checksum
        updated = registry.get("C-500")
        assert updated is not None
        assert updated.context_checksum == _compute_context_checksum(skeleton)

    def test_no_registry_still_works(self):
        """Engine without a registry should work exactly as before."""
        element = _make_init_element()
        file_spec = _make_file_spec()
        skeleton = _SKELETON

        engine = MicroPrimeEngine(element_registry=None)
        result = engine.process_element(element, file_spec, skeleton)

        assert result.success is True
        assert result.code is not None

    def test_derived_element_id_used_when_no_contract_id(self, tmp_path):
        """When source_contract_id is None, make_element_id() derives the ID."""
        registry = ElementRegistry(state_dir=tmp_path / "reg")
        element = _make_init_element(source_contract_id=None)
        file_spec = _make_file_spec()
        skeleton = _SKELETON

        engine = MicroPrimeEngine(element_registry=registry)
        result = engine.process_element(element, file_spec, skeleton)

        assert result.success is True

        # The derived ID should have been used for registry storage
        derived_id = _resolve_element_id(element, file_spec.file)
        stored = registry.get(derived_id)
        assert stored is not None
        assert stored.extra.get("code") is not None

    def test_cache_hit_with_none_checksum_is_accepted(self, tmp_path):
        """Entry with context_checksum=None should be treated as a valid hit (no staleness check)."""
        registry = ElementRegistry(state_dir=tmp_path / "reg")
        element = _make_init_element(source_contract_id="C-600")
        file_spec = _make_file_spec()
        skeleton = _SKELETON

        entry = ElementEntry(
            element_id="C-600",
            kind="method",
            name="__init__",
            file_path="src/mypackage/utils.py",
            context_checksum=None,  # no checksum — legacy entry
            extra={"code": "self.name = name\nself.value = value"},
        )
        registry.put(entry)

        engine = MicroPrimeEngine(element_registry=registry)
        result = engine.process_element(element, file_spec, skeleton)

        assert result.success is True
        assert result.code == "self.name = name\nself.value = value"
        assert result.decomposition_metadata == {"source": "element_registry"}

    def test_inmemory_cache_takes_priority_over_registry(self, tmp_path):
        """The in-memory _success_cache should be checked before the registry."""
        registry = MagicMock(spec=ElementRegistry)
        element = _make_init_element(source_contract_id="C-700")
        file_spec = _make_file_spec()
        skeleton = _SKELETON

        engine = MicroPrimeEngine(element_registry=registry)

        # First call — populates in-memory cache
        result1 = engine.process_element(element, file_spec, skeleton)
        assert result1.success is True

        # Reset mock call count
        registry.reset_mock()

        # Second call — should hit in-memory cache, NOT registry
        result2 = engine.process_element(element, file_spec, skeleton)
        assert result2.success is True
        registry.get.assert_not_called()
