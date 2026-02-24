"""AR-822: Module inventory injection in IMPLEMENT prompts.

Verifies that SCAFFOLD module_inventory data reaches chunk metadata
and is available for import grounding in code generation prompts.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
class TestModuleInventoryInChunkMetadata:
    """Verify module_inventory flows from SCAFFOLD to IMPLEMENT chunks."""

    def test_module_inventory_in_chunk_metadata(self):
        """_tasks_to_chunks should include module_inventory in chunk metadata."""
        from tests.unit.contractors.conftest import FakeSeedTask
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        task = FakeSeedTask(
            task_id="T-1",
            title="Test task",
            target_files=["src/pkg/module.py"],
            estimated_loc=50,
        )

        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(
            tasks=[task],
            max_retries=1,
            module_inventory=["pkg", "pkg.sub", "pkg.utils"],
        )

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.metadata.get("module_inventory") == [
            "pkg", "pkg.sub", "pkg.utils",
        ]

    def test_no_module_inventory_defaults_to_empty(self):
        """Without module_inventory, chunk metadata has empty list."""
        from tests.unit.contractors.conftest import FakeSeedTask
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        task = FakeSeedTask(
            task_id="T-1",
            title="Test task",
            target_files=["src/pkg/module.py"],
            estimated_loc=50,
        )

        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(
            tasks=[task],
            max_retries=1,
        )

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.metadata.get("module_inventory") == []
