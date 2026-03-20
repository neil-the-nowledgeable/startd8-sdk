"""Derive Prime Contractor seed tasks from TODO inventory (REQ-TCW-200).

Transforms classified TodoEntries into seed tasks consumable by the Prime
Contractor workflow.  Category A TODOs become ``uncomment`` tasks (TRIVIAL),
Category B become ``implement`` tasks (SIMPLE) with instrumentation contract
context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger
from startd8.validators.todo_scanner import TodoEntry, TodoInventory

logger = get_logger(__name__)

__all__ = ["derive_tasks_from_todos"]


def derive_tasks_from_todos(
    inventory: TodoInventory,
    instrumentation_contract: Optional[Dict[str, Any]] = None,
    *,
    source_run_id: str = "",
) -> List[Dict[str, Any]]:
    """Generate seed tasks from a classified TODO inventory.

    Args:
        inventory: Classified TodoInventory from the TODO scanner.
        instrumentation_contract: Optional per-service instrumentation contract
            from onboarding metadata (REQ-TCW-003).
        source_run_id: The run that produced the TODO-bearing code.

    Returns:
        List of seed task dicts in Prime Contractor format, ordered:
        1. Dependency additions (build file changes)
        2. Category A (uncomment) tasks
        3. Category B (implement) tasks
    """
    dep_tasks: List[Dict[str, Any]] = []
    uncomment_tasks: List[Dict[str, Any]] = []
    implement_tasks: List[Dict[str, Any]] = []

    # Track which files need dependency additions
    dep_files_added: set = set()

    for entry in inventory.entries:
        if entry.category == "A":
            task = _make_uncomment_task(entry, source_run_id)
            if task:
                uncomment_tasks.append(task)

        elif entry.category == "B":
            task = _make_implement_task(entry, instrumentation_contract, source_run_id)
            if task:
                implement_tasks.append(task)

                # Generate dependency task if needed
                if instrumentation_contract and entry.file_path not in dep_files_added:
                    dep_task = _make_dependency_task(
                        entry, instrumentation_contract, source_run_id,
                    )
                    if dep_task:
                        dep_tasks.append(dep_task)
                        dep_files_added.add(entry.file_path)

    # Order: deps first, then uncomment, then implement
    all_tasks = dep_tasks + uncomment_tasks + implement_tasks

    # Assign sequential task IDs
    for i, task in enumerate(all_tasks, start=1):
        task["task_id"] = f"TODO-{i:03d}"
        # Set dependencies
        if task["_task_type"] == "implement" and dep_tasks:
            # Implement tasks depend on dep tasks
            task["depends_on"] = [d["task_id"] for d in dep_tasks]

    logger.info(
        "Derived %d tasks from TODO inventory: %d dep, %d uncomment, %d implement",
        len(all_tasks), len(dep_tasks), len(uncomment_tasks), len(implement_tasks),
    )

    # Clean up internal fields
    for task in all_tasks:
        task.pop("_task_type", None)

    return all_tasks


def _make_uncomment_task(
    entry: TodoEntry,
    source_run_id: str,
) -> Optional[Dict[str, Any]]:
    """Create an uncomment task for a Category A TODO."""
    return {
        "_task_type": "uncomment",
        "task_id": "",  # assigned later
        "title": f"Uncomment code block near line {entry.line} in {Path(entry.file_path).name}",
        "task_type": "uncomment",
        "story_points": 1,
        "priority": "medium",
        "labels": ["instrumentation", "category-a", "auto-derived"],
        "depends_on": [],
        "description": (
            f"Uncomment the commented-out code block adjacent to the TODO "
            f"at line {entry.line} in {entry.file_path}.\n\n"
            f"TODO text: {entry.raw_text}\n"
            f"Rationale: {entry.rationale}"
        ),
        "target_files": [entry.file_path],
        "estimated_loc": 10,
        "mode": "edit",
        "config": {
            "task_description": (
                f"Uncomment the commented-out code block adjacent to the TODO "
                f"at line {entry.line} in {entry.file_path}.\n\n"
                f"TODO text: {entry.raw_text}\n"
                f"Rationale: {entry.rationale}"
            ),
            "context": {
                "todo_line": entry.line,
                "todo_text": entry.raw_text,
                "containing_function": entry.containing_function,
                "context_lines": entry.context_lines,
                "source_run_id": source_run_id,
            },
        },
    }


def _make_implement_task(
    entry: TodoEntry,
    instrumentation_contract: Optional[Dict[str, Any]],
    source_run_id: str,
) -> Optional[Dict[str, Any]]:
    """Create an implement task for a Category B TODO."""
    contract_context = {}
    if instrumentation_contract and entry.contract_fields:
        for contract_field in entry.contract_fields:
            parts = contract_field.split(".")
            section = instrumentation_contract
            for p in parts:
                if isinstance(section, dict):
                    section = section.get(p, {})
            if section:
                contract_context[contract_field] = section

    return {
        "_task_type": "implement",
        "task_id": "",  # assigned later
        "title": (
            f"Implement {entry.containing_function or 'stub'} "
            f"in {Path(entry.file_path).name}"
        ),
        "task_type": "implement",
        "story_points": 2,
        "priority": "high",
        "labels": ["instrumentation", "category-b", "auto-derived"],
        "depends_on": [],
        "description": (
            f"Implement the stub method '{entry.containing_function}' "
            f"at line {entry.line} in {entry.file_path}.\n\n"
            f"TODO text: {entry.raw_text}\n"
            f"Contract fields: {', '.join(entry.contract_fields)}\n"
            f"Rationale: {entry.rationale}"
        ),
        "target_files": [entry.file_path],
        "estimated_loc": 30,
        "mode": "edit",
        "config": {
            "task_description": (
                f"Implement the stub method '{entry.containing_function}' "
                f"at line {entry.line} in {entry.file_path}.\n\n"
                f"TODO text: {entry.raw_text}\n"
                f"Contract fields: {', '.join(entry.contract_fields)}\n"
                f"Rationale: {entry.rationale}"
            ),
            "context": {
                "todo_line": entry.line,
                "todo_text": entry.raw_text,
                "containing_function": entry.containing_function,
                "context_lines": entry.context_lines,
                "instrumentation_contract": contract_context,
                "contract_fields": entry.contract_fields,
                "source_run_id": source_run_id,
            },
        },
    }


def _make_dependency_task(
    entry: TodoEntry,
    instrumentation_contract: Dict[str, Any],
    source_run_id: str,
) -> Optional[Dict[str, Any]]:
    """Create a dependency-addition task for instrumentation packages."""
    deps = instrumentation_contract.get("dependencies", {}).get("add", [])
    if not deps:
        return None

    # Determine the build file from the source file's directory
    src_dir = Path(entry.file_path).parent
    language = entry.language

    build_file_map = {
        "java": "build.gradle",
        "go": "go.mod",
        "nodejs": "package.json",
        "python": "requirements.txt",
    }
    build_file = build_file_map.get(language, "build.gradle")
    build_path = str(src_dir / build_file)

    deps_text = "\n".join(
        f"- {d.get('group', '')}:{d.get('artifact', '')} {d.get('version', 'latest')}"
        for d in deps
    )

    return {
        "_task_type": "dependency",
        "task_id": "",  # assigned later
        "title": f"Add instrumentation dependencies to {build_file}",
        "task_type": "edit",
        "story_points": 1,
        "priority": "high",
        "labels": ["instrumentation", "dependencies", "auto-derived"],
        "depends_on": [],
        "description": (
            f"Add the following dependencies to {build_path}:\n\n"
            f"{deps_text}\n\n"
            f"These are required for OTel instrumentation."
        ),
        "target_files": [build_path],
        "estimated_loc": 10,
        "mode": "edit",
        "config": {
            "task_description": (
                f"Add the following dependencies to {build_path}:\n\n"
                f"{deps_text}\n\n"
                f"These are required for OTel instrumentation."
            ),
            "context": {
                "dependencies": deps,
                "source_run_id": source_run_id,
            },
        },
    }
