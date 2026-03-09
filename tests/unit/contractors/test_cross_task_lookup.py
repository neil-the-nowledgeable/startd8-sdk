"""Tests for REQ-MP-1105: Cross-task element cache lookup in PrimeContractor.

Verifies that ``_try_element_cache_assembly()`` correctly assembles features
from cached element code in the ElementRegistry, falls through to normal
generation on partial or no cache hits, and handles errors gracefully.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.contractors.protocols import GenerationResult
from startd8.contractors.queue import FeatureSpec, FeatureStatus
from startd8.element_registry import ElementEntry, ElementRegistry
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature, Visibility


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signature() -> Signature:
    """Build a minimal Signature for callable element specs."""
    return Signature(params=[], return_annotation=None)


def _make_element_spec(
    name: str,
    contract_id: str,
    kind: ElementKind = ElementKind.FUNCTION,
    parent_class: Optional[str] = None,
) -> ForwardElementSpec:
    """Build a ForwardElementSpec with the given name and contract ID."""
    sig = _make_signature() if kind != ElementKind.CLASS else None
    return ForwardElementSpec(
        kind=kind,
        name=name,
        source_contract_id=contract_id,
        signature=sig,
        parent_class=parent_class,
    )


def _make_feature(**overrides: Any) -> FeatureSpec:
    defaults = {
        "id": "F-001",
        "name": "Widget module",
        "description": "Implement a widget module.",
        "target_files": ["src/widget.py"],
        "dependencies": [],
    }
    defaults.update(overrides)
    return FeatureSpec(**defaults)


def _make_registry_entry(
    element_id: str,
    code: str,
    context_checksum: Optional[str] = None,
) -> ElementEntry:
    """Build an ElementEntry with cached code in the extra dict."""
    return ElementEntry(
        element_id=element_id,
        kind="function",
        name=element_id.split(".")[-1],
        extra={"code": code},
        context_checksum=context_checksum,
    )


def _make_workflow(tmp_path: Path, skeleton_sources: Optional[Dict[str, str]] = None) -> PrimeContractorWorkflow:
    """Build a PrimeContractorWorkflow with mocked internals."""
    wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
    wf.project_root = tmp_path
    wf._element_registry = None
    wf._forward_manifest = None
    wf.code_generator = MagicMock()
    wf.code_generator.output_dir = tmp_path / "generated"
    wf.seed_forward_manifest = None
    wf.force_regenerate = False
    wf._skeleton_sources = skeleton_sources or {}
    return wf


# ---------------------------------------------------------------------------
# Tests: _try_element_cache_assembly
# ---------------------------------------------------------------------------


class TestAllElementsInCache:
    """All elements for a feature are in the registry -- assembled at $0.00."""

    def test_all_cached_returns_generation_result(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        # Set up registry with cached code
        registry = ElementRegistry(state_dir=tmp_path / "reg")
        entry_a = _make_registry_entry("contract.func_a", "def func_a(): pass")
        entry_b = _make_registry_entry("contract.func_b", "def func_b(): pass")
        registry.put(entry_a)
        registry.put(entry_b)
        wf._element_registry = registry

        # Set up forward manifest with matching elements
        elem_a = _make_element_spec("func_a", "contract.func_a")
        elem_b = _make_element_spec("func_b", "contract.func_b")
        file_spec = ForwardFileSpec(
            file="src/widget.py",
            elements=[elem_a, elem_b],
        )
        manifest = ForwardManifest(
            file_specs={"src/widget.py": file_spec},
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is not None
        assert result.success is True
        assert result.cost_usd == 0.0
        assert result.metadata["strategy"] == "element_reuse"
        assert result.metadata["elements_from_cache"] == 2
        assert result.metadata["elements_generated"] == 0
        assert len(result.generated_files) == 1

    def test_assembled_file_content(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        registry.put(_make_registry_entry("c.a", "def func_a(): pass"))
        registry.put(_make_registry_entry("c.b", "def func_b(): pass"))
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec("func_a", "c.a"),
                        _make_element_spec("func_b", "c.b"),
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is not None
        assembled_file = result.generated_files[0]
        content = assembled_file.read_text(encoding="utf-8")
        assert "def func_a(): pass" in content
        assert "def func_b(): pass" in content


class TestPartialCacheHit:
    """Some elements cached, some missing -- falls through to generation."""

    def test_partial_returns_none(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        registry.put(_make_registry_entry("c.a", "def func_a(): pass"))
        # c.b is NOT in the registry
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec("func_a", "c.a"),
                        _make_element_spec("func_b", "c.b"),
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is None

    def test_partial_stores_prefill_metadata(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        registry.put(_make_registry_entry("c.a", "def func_a(): pass"))
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec("func_a", "c.a"),
                        _make_element_spec("func_b", "c.b"),
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        feature.metadata = {}
        wf._try_element_cache_assembly(feature)

        assert "_prefill_elements" in feature.metadata
        assert "c.a" in feature.metadata["_prefill_elements"]
        assert feature.metadata["_prefill_elements"]["c.a"] == "def func_a(): pass"


class TestNoCacheHits:
    """No elements in registry -- returns None (normal generation path)."""

    def test_no_hits_returns_none(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec("func_a", "c.a"),
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is None

    def test_no_registry_returns_none(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)
        wf._element_registry = None

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is None

    def test_no_manifest_returns_none(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)
        wf._element_registry = ElementRegistry(state_dir=tmp_path / "reg")
        wf._forward_manifest = None

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is None

    def test_no_target_files_returns_none(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)
        wf._element_registry = ElementRegistry(state_dir=tmp_path / "reg")
        wf._forward_manifest = ForwardManifest()

        feature = _make_feature(target_files=[])
        result = wf._try_element_cache_assembly(feature)

        assert result is None


class TestRegistryError:
    """Registry errors are non-fatal -- falls through to generation."""

    def test_registry_exception_returns_none(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        broken_registry = MagicMock()
        broken_registry.get.side_effect = RuntimeError("disk I/O error")
        wf._element_registry = broken_registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec("func_a", "c.a"),
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is None


class TestStaleChecksum:
    """Stale checksum causes element to be skipped (treated as missing)."""

    def test_stale_checksum_falls_through(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        # Entry has old checksum
        registry.put(
            _make_registry_entry("c.a", "def func_a(): pass", context_checksum="old_hash")
        )
        wf._element_registry = registry

        manifest = ForwardManifest(
            source_checksum="new_hash",
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec("func_a", "c.a"),
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        # Stale = missing, so should return None (no full cache hit)
        assert result is None


class TestAssemblyDefectDetection:
    """Assembly defect detection prevents returning invalid code."""

    def test_defect_detected_falls_through(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        # Code with a NotImplementedError stub (assembly defect)
        registry.put(
            _make_registry_entry("c.a", "def func_a():\n    raise NotImplementedError")
        )
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec("func_a", "c.a"),
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        # Defect detected -> should fall through to normal generation
        assert result is None


class TestMetadataElementCounts:
    """Metadata includes elements_from_cache and elements_generated counts."""

    def test_metadata_counts(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        for i in range(3):
            registry.put(
                _make_registry_entry(f"c.func_{i}", f"def func_{i}(): pass")
            )
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec(f"func_{i}", f"c.func_{i}")
                        for i in range(3)
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is not None
        assert result.metadata["elements_from_cache"] == 3
        assert result.metadata["elements_generated"] == 0
        assert result.metadata["strategy"] == "element_reuse"
        assert result.cost_usd == 0.0
        assert result.input_tokens == 0
        assert result.output_tokens == 0


class TestElementsWithoutContractId:
    """Elements without source_contract_id are skipped (not cached)."""

    def test_elements_without_contract_id_ignored(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        wf._element_registry = registry

        # Element spec with no source_contract_id
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="orphan_func",
            source_contract_id=None,
            signature=_make_signature(),
        )
        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[elem],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        # No elements with contract IDs -> returns None
        assert result is None


class TestCachedEntryWithoutCode:
    """Registry entry exists but has no code in extra -> treated as missing."""

    def test_entry_without_code_is_missing(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        # Entry without code
        entry = ElementEntry(
            element_id="c.a",
            kind="function",
            name="func_a",
            extra={},  # no "code" key
        )
        registry.put(entry)
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec("func_a", "c.a"),
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is None


# ---------------------------------------------------------------------------
# Tests: Skeleton-based assembly (L6 fix — preserves class wrappers)
# ---------------------------------------------------------------------------


_SKELETON_WITH_CLASS = textwrap.dedent("""\
    import logging


    class JsonFormatter:
        def add_fields(self, log_record, record, message_dict):
            raise NotImplementedError

        def format(self, record):
            raise NotImplementedError


    def get_logger(name: str) -> logging.Logger:
        raise NotImplementedError
""")


class TestSkeletonBasedAssembly:
    """When a skeleton is available, splices cached code into it."""

    def test_class_methods_preserved_in_skeleton(self, tmp_path: Path) -> None:
        """Core L6 fix: class wrappers are NOT lost during cache assembly."""
        wf = _make_workflow(
            tmp_path,
            skeleton_sources={"src/widget.py": _SKELETON_WITH_CLASS},
        )

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        registry.put(_make_registry_entry(
            "c.add_fields",
            "log_record.update({'severity': record.levelname})",
        ))
        registry.put(_make_registry_entry(
            "c.format",
            "return super().format(record)",
        ))
        registry.put(_make_registry_entry(
            "c.get_logger",
            "logger = logging.getLogger(name)\nreturn logger",
        ))
        wf._element_registry = registry

        elem_add = _make_element_spec("add_fields", "c.add_fields", kind=ElementKind.METHOD, parent_class="JsonFormatter")
        elem_fmt = _make_element_spec("format", "c.format", kind=ElementKind.METHOD, parent_class="JsonFormatter")
        elem_get = _make_element_spec("get_logger", "c.get_logger")

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[elem_add, elem_fmt, elem_get],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is not None
        content = result.generated_files[0].read_text(encoding="utf-8")

        # Class definition must be present (the L6 bug lost it)
        assert "class JsonFormatter:" in content
        # Methods must be indented inside the class
        assert "    def add_fields(" in content
        assert "    def format(" in content
        # Module-level function must be present
        assert "def get_logger(" in content
        # Import preserved from skeleton
        assert "import logging" in content
        # Stubs should be replaced
        assert "raise NotImplementedError" not in content

    def test_skeleton_assembly_metadata_flag(self, tmp_path: Path) -> None:
        """Metadata indicates skeleton-based assembly was used."""
        wf = _make_workflow(
            tmp_path,
            skeleton_sources={"src/widget.py": "def func_a():\n    raise NotImplementedError\n"},
        )

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        registry.put(_make_registry_entry("c.a", "return 42"))
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[_make_element_spec("func_a", "c.a")],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is not None
        assert result.metadata.get("skeleton_assembly") is True

    def test_no_skeleton_falls_back_to_concatenation(self, tmp_path: Path) -> None:
        """Without skeleton, falls back to concatenation (backward-compat)."""
        wf = _make_workflow(tmp_path)  # no skeleton_sources

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        registry.put(_make_registry_entry("c.a", "def func_a(): pass"))
        registry.put(_make_registry_entry("c.b", "def func_b(): pass"))
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[
                        _make_element_spec("func_a", "c.a"),
                        _make_element_spec("func_b", "c.b"),
                    ],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is not None
        content = result.generated_files[0].read_text(encoding="utf-8")
        assert "def func_a(): pass" in content
        assert "def func_b(): pass" in content
        assert result.metadata.get("skeleton_assembly") is False

    def test_all_splices_fail_falls_through(self, tmp_path: Path) -> None:
        """If all element splices fail, returns None (falls to generation)."""
        # Skeleton has no matching stub for the cached element
        wf = _make_workflow(
            tmp_path,
            skeleton_sources={"src/widget.py": "# empty skeleton\npass\n"},
        )

        registry = ElementRegistry(state_dir=tmp_path / "reg")
        registry.put(_make_registry_entry("c.a", "return 42"))
        wf._element_registry = registry

        manifest = ForwardManifest(
            file_specs={
                "src/widget.py": ForwardFileSpec(
                    file="src/widget.py",
                    elements=[_make_element_spec("func_a", "c.a")],
                ),
            },
        )
        wf._forward_manifest = manifest

        feature = _make_feature()
        result = wf._try_element_cache_assembly(feature)

        assert result is None
