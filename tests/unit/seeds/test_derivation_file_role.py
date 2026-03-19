"""Tests for file-role constraint injection in split_oversized_tasks."""

import pytest

from startd8.seeds.derivation import split_oversized_tasks


def _make_task(task_id, title, target_files, estimated_loc=200):
    """Build a task dict matching the prime-route schema."""
    return {
        "task_id": task_id,
        "title": title,
        "task_type": "task",
        "priority": "medium",
        "labels": [],
        "depends_on": [],
        "config": {
            "task_description": "Parent task description",
            "requirements_text": "",
            "context": {
                "feature_id": "F-1",
                "target_files": target_files,
                "estimated_loc": estimated_loc,
            },
        },
    }


class TestSplitOversizedTasksFileRole:
    def test_split_with_interface_file_contains_role(self):
        task = _make_task(
            "PI-001", "Cart Service",
            ["CartStore.cs", "ICartStore.cs"],
        )
        result = split_oversized_tasks([task], max_files=1)
        # Should have 2 sub-tasks
        assert len(result) == 2

        # Find the sub-task for ICartStore.cs
        interface_tasks = [
            t for t in result
            if "ICartStore.cs" in t["config"]["context"]["target_files"]
        ]
        assert len(interface_tasks) == 1
        desc = interface_tasks[0]["config"]["task_description"]
        assert "INTERFACE" in desc
        assert "FILE ROLE CONSTRAINT" in desc

    def test_split_with_dockerfile_contains_role(self):
        task = _make_task(
            "PI-001", "Service Setup",
            ["main.go", "Dockerfile"],
        )
        result = split_oversized_tasks([task], max_files=1)
        assert len(result) == 2

        dockerfile_tasks = [
            t for t in result
            if "Dockerfile" in t["config"]["context"]["target_files"]
        ]
        assert len(dockerfile_tasks) == 1
        desc = dockerfile_tasks[0]["config"]["task_description"]
        assert "Dockerfile" in desc
        assert "FILE ROLE CONSTRAINT" in desc

    def test_split_with_regular_py_no_role_constraint(self):
        task = _make_task(
            "PI-001", "Python Module",
            ["service.py", "utils.py"],
        )
        result = split_oversized_tasks([task], max_files=1)
        assert len(result) == 2

        for t in result:
            desc = t["config"]["task_description"]
            assert "FILE ROLE CONSTRAINT" not in desc

    def test_split_with_csproj_contains_role(self):
        task = _make_task(
            "PI-001", "Project Config",
            ["CartService.cs", "CartService.csproj"],
        )
        result = split_oversized_tasks([task], max_files=1)
        assert len(result) == 2

        csproj_tasks = [
            t for t in result
            if "CartService.csproj" in t["config"]["context"]["target_files"]
        ]
        assert len(csproj_tasks) == 1
        desc = csproj_tasks[0]["config"]["task_description"]
        assert "FILE ROLE CONSTRAINT" in desc
        assert "project configuration" in desc

    def test_split_with_proto_contains_role(self):
        task = _make_task(
            "PI-001", "Cart API",
            ["cart.proto", "server.go"],
        )
        result = split_oversized_tasks([task], max_files=1)
        assert len(result) == 2

        proto_tasks = [
            t for t in result
            if "cart.proto" in t["config"]["context"]["target_files"]
        ]
        assert len(proto_tasks) == 1
        desc = proto_tasks[0]["config"]["task_description"]
        assert "FILE ROLE CONSTRAINT" in desc
        assert "Protocol Buffer" in desc

    def test_no_split_when_single_file(self):
        task = _make_task(
            "PI-001", "Single File",
            ["service.py"],
        )
        result = split_oversized_tasks([task], max_files=1)
        assert len(result) == 1
        assert result[0]["task_id"] == "PI-001"

    def test_split_preserves_parent_id_in_description(self):
        task = _make_task(
            "PI-001", "Multi File",
            ["a.py", "b.py"],
        )
        result = split_oversized_tasks([task], max_files=1)
        for t in result:
            assert "PI-001" in t["config"]["task_description"]
            assert "Auto-split" in t["config"]["task_description"]

    def test_split_sub_task_ids(self):
        task = _make_task(
            "PI-001", "Multi File",
            ["a.py", "b.py", "c.py"],
        )
        result = split_oversized_tasks([task], max_files=1)
        assert len(result) == 3
        ids = [t["task_id"] for t in result]
        assert "PI-001a" in ids
        assert "PI-001b" in ids
        assert "PI-001c" in ids
