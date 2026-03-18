"""Tests for the TODO Completion Workflow (REQ-TCW-200–303)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from startd8.seeds.todo_derivation import derive_tasks_from_todos
from startd8.validators.todo_scanner import TodoEntry, TodoInventory
from startd8.workflows.builtin.todo_completion_workflow import TodoCompletionWorkflow


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JAVA_WITH_STUBS = textwrap.dedent("""\
    package hipstershop;

    import io.grpc.Server;
    import io.grpc.ServerBuilder;

    public class AdService {
        private void initStats() {
            // TODO: implement metrics initialization
        }

        private void initTracing() {
            // TODO: implement tracing initialization
        }
    }
""")

DOCKERFILE_WITH_COMMENTS = textwrap.dedent("""\
    FROM golang:1.21 AS builder
    WORKDIR /app
    COPY . .
    RUN go build -o server .

    FROM gcr.io/distroless/base
    # TODO: uncomment profiler
    # RUN wget -q -O /tmp/profiler.tar.gz \\
    #     https://storage.googleapis.com/cloud-profiler/java/latest/profiler.tar.gz
    # RUN tar xzf /tmp/profiler.tar.gz -C /opt
    CMD ["/server"]
""")


def _make_inventory_with_entries() -> TodoInventory:
    """Create a TodoInventory with known entries."""
    return TodoInventory(entries=[
        TodoEntry(
            file_path="src/AdService.java",
            line=8,
            language="java",
            raw_text="// TODO: implement metrics initialization",
            category="B",
            context_lines="...",
            containing_function="initStats",
            contract_fields=("metrics.required",),
            confidence=0.9,
            rationale="Stub method with instrumentation vocabulary",
        ),
        TodoEntry(
            file_path="src/AdService.java",
            line=12,
            language="java",
            raw_text="// TODO: implement tracing initialization",
            category="B",
            context_lines="...",
            containing_function="initTracing",
            contract_fields=("traces.required",),
            confidence=0.9,
            rationale="Stub method with instrumentation vocabulary",
        ),
        TodoEntry(
            file_path="Dockerfile",
            line=7,
            language="dockerfile",
            raw_text="# TODO: uncomment profiler",
            category="A",
            context_lines="...",
            containing_function="",
            confidence=0.9,
            rationale="Adjacent commented-out code block",
        ),
    ])


# ---------------------------------------------------------------------------
# Test: derive_tasks_from_todos
# ---------------------------------------------------------------------------

class TestDeriveTasksFromTodos:
    """REQ-TCW-200: completion plan generation."""

    def test_category_a_produces_uncomment_task(self):
        inv = TodoInventory(entries=[
            TodoEntry("Dockerfile", 7, "dockerfile", "# TODO: uncomment",
                      "A", "", "", rationale="commented block"),
        ])
        tasks = derive_tasks_from_todos(inv)
        assert len(tasks) == 1
        assert tasks[0]["task_type"] == "uncomment"
        assert tasks[0]["mode"] == "edit"

    def test_category_b_produces_implement_task(self):
        inv = TodoInventory(entries=[
            TodoEntry("AdService.java", 8, "java", "// TODO: implement",
                      "B", "", "initStats", contract_fields=("metrics.required",),
                      rationale="stub"),
        ])
        tasks = derive_tasks_from_todos(inv)
        assert len(tasks) == 1
        assert tasks[0]["task_type"] == "implement"
        assert tasks[0]["mode"] == "edit"
        assert "initStats" in tasks[0]["title"]

    def test_category_c_skipped(self):
        inv = TodoInventory(entries=[
            TodoEntry("Foo.java", 1, "java", "// TODO: generic",
                      "C", "", "", rationale=""),
        ])
        tasks = derive_tasks_from_todos(inv)
        assert len(tasks) == 0

    def test_dependency_ordering(self):
        """Dep tasks come before implement tasks."""
        contract = {
            "dependencies": {
                "add": [
                    {"group": "io.opentelemetry", "artifact": "opentelemetry-sdk", "version": "latest"},
                ],
            },
            "metrics": {"required": [{"name": "rpc_server_duration_seconds"}]},
        }
        inv = TodoInventory(entries=[
            TodoEntry("AdService.java", 8, "java", "// TODO: implement",
                      "B", "", "initStats", contract_fields=("metrics.required",)),
        ])
        tasks = derive_tasks_from_todos(inv, instrumentation_contract=contract)
        assert len(tasks) >= 2
        # First task should be dependency
        assert "dependencies" in tasks[0]["title"].lower() or "dependencies" in str(tasks[0].get("config", {}))

    def test_task_ids_sequential(self):
        inv = _make_inventory_with_entries()
        tasks = derive_tasks_from_todos(inv)
        ids = [t["task_id"] for t in tasks]
        assert all(id.startswith("TODO-") for id in ids)
        # Check sequential ordering
        nums = [int(id.split("-")[1]) for id in ids]
        assert nums == sorted(nums)

    def test_source_run_id_threaded(self):
        inv = TodoInventory(entries=[
            TodoEntry("Dockerfile", 7, "dockerfile", "# TODO: uncomment",
                      "A", "", ""),
        ])
        tasks = derive_tasks_from_todos(inv, source_run_id="run-069")
        ctx = tasks[0]["config"]["context"]
        assert ctx["source_run_id"] == "run-069"

    def test_mixed_categories(self):
        inv = _make_inventory_with_entries()
        tasks = derive_tasks_from_todos(inv, source_run_id="run-069")
        task_types = {t["task_type"] for t in tasks}
        assert "uncomment" in task_types
        assert "implement" in task_types


# ---------------------------------------------------------------------------
# Test: TodoCompletionWorkflow
# ---------------------------------------------------------------------------

class TestTodoCompletionWorkflow:
    """REQ-TCW-300: workflow execution."""

    def test_metadata(self):
        wf = TodoCompletionWorkflow()
        meta = wf.metadata
        assert meta.workflow_id == "todo-completion"

    def test_validate_config_missing_scan_dir(self):
        wf = TodoCompletionWorkflow()
        result = wf.validate_config({"output_dir": "/tmp"})
        assert not result.valid

    def test_validate_config_valid(self):
        wf = TodoCompletionWorkflow()
        result = wf.validate_config({"scan_dir": "/tmp", "output_dir": "/tmp"})
        assert result.valid

    def test_scan_only_mode(self, tmp_path):
        """Scan without execution."""
        scan_dir = tmp_path / "generated"
        scan_dir.mkdir()
        (scan_dir / "AdService.java").write_text(JAVA_WITH_STUBS)

        out_dir = tmp_path / "output"
        wf = TodoCompletionWorkflow()
        result = wf.run({
            "scan_dir": str(scan_dir),
            "output_dir": str(out_dir),
            "source_run_id": "run-test",
            "execute": False,
        })
        assert result.success
        assert result.output["todo_count"] >= 2
        assert result.output["executed"] is False

        # Verify artifacts
        inv_path = out_dir / "todo-inventory.json"
        assert inv_path.is_file()
        seed_path = out_dir / "instrumentation-seed.json"
        assert seed_path.is_file()

    def test_scan_with_category_filter(self, tmp_path):
        """Only scan Category A."""
        scan_dir = tmp_path / "generated"
        scan_dir.mkdir()
        (scan_dir / "Dockerfile").write_text(DOCKERFILE_WITH_COMMENTS)
        (scan_dir / "AdService.java").write_text(JAVA_WITH_STUBS)

        out_dir = tmp_path / "output"
        wf = TodoCompletionWorkflow()
        result = wf.run({
            "scan_dir": str(scan_dir),
            "output_dir": str(out_dir),
            "categories": "A",
        })
        assert result.success
        # Only Category A should be in the output
        assert result.output.get("todo_count_b", 0) == 0

    def test_empty_directory(self, tmp_path):
        """No TODOs found."""
        scan_dir = tmp_path / "empty"
        scan_dir.mkdir()
        (scan_dir / "clean.java").write_text(
            "package foo;\npublic class Clean {}\n"
        )

        out_dir = tmp_path / "output"
        wf = TodoCompletionWorkflow()
        result = wf.run({
            "scan_dir": str(scan_dir),
            "output_dir": str(out_dir),
        })
        assert result.success
        assert result.output["todo_count"] == 0
