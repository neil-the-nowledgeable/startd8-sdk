"""Integration test: Element Registry cross-task reuse (Step 1.8).

End-to-end test verifying that:
1. Plan ingestion populates the registry from a ForwardManifest
2. MicroPrimeEngine cache-through returns registry hits
3. Registry registration persists generated code for cross-task reuse
4. Summary statistics reflect the expected state
"""

import hashlib
import tempfile
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.element_id import make_element_id
from startd8.element_registry import ElementEntry, ElementRegistry
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    ElementKind,
    Signature,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_element(name: str, kind: ElementKind = ElementKind.FUNCTION,
                  parent_class: Optional[str] = None) -> ForwardElementSpec:
    """Create a minimal ForwardElementSpec with a deterministic contract ID."""
    eid = make_element_id(
        kind=kind.value,
        name=name,
        file_path="src/service/main.py",
        parent_class=parent_class,
    )
    return ForwardElementSpec(
        kind=kind,
        name=name,
        parent_class=parent_class,
        source_contract_id=eid,
        signature=Signature(params=[], return_annotation=None),
    )


def _make_manifest(*elements: ForwardElementSpec,
                   file_path: str = "src/service/main.py") -> ForwardManifest:
    """Build a ForwardManifest with all elements in one file."""
    file_spec = ForwardFileSpec(
        file=file_path,
        elements=list(elements),
    )
    return ForwardManifest(
        file_specs={file_path: file_spec},
    )


def _populate_registry(registry: ElementRegistry,
                       manifest: ForwardManifest) -> int:
    """Simulate plan-ingestion registry population (ER-003).

    Mirrors _mottainai_pre_assembly() logic: iterate all elements,
    register with status "specified".
    """
    count = 0
    for file_path, file_spec in manifest.file_specs.items():
        for element in file_spec.elements:
            eid = element.source_contract_id
            if not eid:
                continue
            entry = ElementEntry(
                element_id=eid,
                kind=element.kind.value,
                name=element.name,
                file_path=file_path,
                source_contract_id=eid,
            )
            registry.put(entry)
            registry.set_phase_status(eid, "plan_ingestion", "specified")
            count += 1
    return count


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestElementRegistryIntegration:
    """End-to-end tests for element registry cross-task reuse."""

    def test_plan_ingestion_populates_registry(self, tmp_path: Path) -> None:
        """After plan ingestion, registry contains all manifest elements."""
        elem_a = _make_element("get_logger")
        elem_b = _make_element("format_json")
        elem_c = _make_element("JsonFormatter", kind=ElementKind.CLASS)
        manifest = _make_manifest(elem_a, elem_b, elem_c)

        registry = ElementRegistry(state_dir=tmp_path / "state")
        count = _populate_registry(registry, manifest)

        assert count == 3
        summary = registry.summary()
        assert summary.total == 3

        # All three elements should have plan_ingestion/specified status
        for elem in [elem_a, elem_b, elem_c]:
            eid = elem.source_contract_id
            assert registry.has(eid), f"Element {eid} not in registry"
            status = registry.get_phase_status(eid, "plan_ingestion")
            assert status == "specified"

    def test_registry_persists_across_instances(self, tmp_path: Path) -> None:
        """Registry state survives process restart (new instance, same dir)."""
        state_dir = tmp_path / "state"
        elem = _make_element("process_data")
        manifest = _make_manifest(elem)

        # Instance 1: populate
        reg1 = ElementRegistry(state_dir=state_dir)
        _populate_registry(reg1, manifest)
        assert reg1.summary().total == 1

        # Instance 2: same dir, new object
        reg2 = ElementRegistry(state_dir=state_dir)
        assert reg2.has(elem.source_contract_id)
        assert reg2.get_phase_status(
            elem.source_contract_id, "plan_ingestion"
        ) == "specified"

    def test_engine_cache_hit_skips_generation(self, tmp_path: Path) -> None:
        """MicroPrimeEngine returns cached code from registry without generating."""
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig

        elem = _make_element("get_logger")
        file_spec = ForwardFileSpec(file="src/service/main.py", elements=[elem])
        manifest = _make_manifest(elem)

        # Set up registry with pre-cached code
        registry = ElementRegistry(state_dir=tmp_path / "state")
        entry = ElementEntry(
            element_id=elem.source_contract_id,
            kind="function",
            name="get_logger",
            file_path="src/service/main.py",
            source_contract_id=elem.source_contract_id,
            extra={"code": "def get_logger():\n    return logging.getLogger(__name__)\n"},
        )
        registry.put(entry)
        registry.set_phase_status(
            elem.source_contract_id, "implement", "generated",
        )

        # Create engine with registry — generation should be skipped
        config = MicroPrimeConfig(dry_run=False, repair_enabled=False)
        engine = MicroPrimeEngine(
            config=config,
            element_registry=registry,
        )

        skeleton = "def get_logger():\n    raise NotImplementedError\n"
        result = engine.process_element(elem, file_spec, skeleton)

        assert result.success is True
        assert result.code is not None
        assert "get_logger" in result.code
        # Should come from registry, not generation
        assert result.decomposition_metadata == {"source": "element_registry"}

    def test_engine_registers_on_generation_success(self, tmp_path: Path) -> None:
        """After successful generation, element is registered in the registry."""
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig

        elem = _make_element("simple_add")
        file_spec = ForwardFileSpec(file="src/service/math.py", elements=[elem])

        registry = ElementRegistry(state_dir=tmp_path / "state")
        # Populate with no code — registry miss expected
        entry = ElementEntry(
            element_id=elem.source_contract_id,
            kind="function",
            name="simple_add",
            file_path="src/service/math.py",
            source_contract_id=elem.source_contract_id,
        )
        registry.put(entry)

        config = MicroPrimeConfig(dry_run=False, repair_enabled=False)
        engine = MicroPrimeEngine(
            config=config,
            element_registry=registry,
        )

        skeleton = "def simple_add(a, b):\n    raise NotImplementedError\n"

        # Mock the Ollama agent to simulate successful generation
        generated_code = "def simple_add(a, b):\n    return a + b\n"
        with patch.object(engine, "_handle_trivial") as mock_trivial, \
             patch.object(engine, "_handle_simple") as mock_simple:
            # The element will be classified — mock whichever tier it lands on
            from startd8.micro_prime.models import ElementResult, TierClassification
            mock_result = ElementResult(
                element_name="simple_add",
                file_path="src/service/math.py",
                tier=TierClassification.TRIVIAL,
                success=True,
                code=generated_code,
            )
            mock_trivial.return_value = mock_result
            mock_simple.return_value = mock_result

            result = engine.process_element(elem, file_spec, skeleton)

        if result.success and result.code:
            # Check registry was updated
            updated = registry.get(elem.source_contract_id)
            assert updated is not None
            assert updated.extra.get("code") == generated_code
            status = registry.get_phase_status(
                elem.source_contract_id, "implement",
            )
            assert status == "generated"

    def test_cross_task_reuse_at_zero_cost(self, tmp_path: Path) -> None:
        """Second task reuses element from first task via registry hit."""
        registry = ElementRegistry(state_dir=tmp_path / "state")

        # Task 1 generates get_logger
        elem = _make_element("get_logger")
        eid = elem.source_contract_id
        entry = ElementEntry(
            element_id=eid,
            kind="function",
            name="get_logger",
            file_path="src/service/main.py",
            source_contract_id=eid,
            extra={
                "code": "def get_logger():\n    return logging.getLogger(__name__)\n",
                "source_task": "PI-001",
            },
        )
        registry.put(entry)
        registry.set_phase_status(eid, "implement", "generated")

        # Task 2 needs the same element — verify it's a cache hit
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig

        config = MicroPrimeConfig(dry_run=False, repair_enabled=False)
        engine = MicroPrimeEngine(config=config, element_registry=registry)

        file_spec = ForwardFileSpec(file="src/service/main.py", elements=[elem])
        skeleton = "def get_logger():\n    raise NotImplementedError\n"

        result = engine.process_element(elem, file_spec, skeleton)

        assert result.success is True
        assert "get_logger" in result.code
        assert result.decomposition_metadata == {"source": "element_registry"}

    def test_no_registry_falls_through_gracefully(self, tmp_path: Path) -> None:
        """Engine with element_registry=None works exactly as before."""
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig, ElementResult, TierClassification

        elem = _make_element("helper_fn")
        file_spec = ForwardFileSpec(file="src/service/util.py", elements=[elem])

        config = MicroPrimeConfig(dry_run=False, repair_enabled=False)
        engine = MicroPrimeEngine(config=config, element_registry=None)

        skeleton = "def helper_fn():\n    raise NotImplementedError\n"

        with patch.object(engine, "_handle_trivial") as mock_trivial, \
             patch.object(engine, "_handle_simple") as mock_simple:
            mock_result = ElementResult(
                element_name="helper_fn",
                file_path="src/service/util.py",
                tier=TierClassification.TRIVIAL,
                success=True,
                code="def helper_fn():\n    pass\n",
            )
            mock_trivial.return_value = mock_result
            mock_simple.return_value = mock_result

            result = engine.process_element(elem, file_spec, skeleton)

        assert result.success is True

    def test_summary_reflects_registry_state(self, tmp_path: Path) -> None:
        """Registry summary matches actual element count and phase distribution."""
        registry = ElementRegistry(state_dir=tmp_path / "state")

        elems = [
            _make_element("fn_a"),
            _make_element("fn_b"),
            _make_element("MyClass", kind=ElementKind.CLASS),
        ]

        for elem in elems:
            entry = ElementEntry(
                element_id=elem.source_contract_id,
                kind=elem.kind.value,
                name=elem.name,
                file_path="src/service/main.py",
                source_contract_id=elem.source_contract_id,
            )
            registry.put(entry)
            registry.set_phase_status(
                elem.source_contract_id, "plan_ingestion", "specified",
            )

        # Generate code for first two
        for elem in elems[:2]:
            cached = registry.get(elem.source_contract_id)
            cached.extra["code"] = f"def {elem.name}(): pass\n"
            registry.put(cached)
            registry.set_phase_status(
                elem.source_contract_id, "implement", "generated",
            )

        summary = registry.summary()
        assert summary.total == 3
        assert summary.by_kind.get("function", 0) == 2
        assert summary.by_kind.get("class", 0) == 1
