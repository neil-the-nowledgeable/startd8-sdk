"""Definition order repair step.

Reorders top-level definitions in generated Python files so that names
are defined before they are referenced.  Fixes F821 (undefined name)
errors caused by the model emitting a class that references functions
defined later in the file.

File-whole repair step only — element-body fragments have a single
definition so ordering is irrelevant.

Passes Ichigo Ichie: any generated Python file can have forward-reference
ordering issues regardless of project.  Uses only AST analysis.
"""

from __future__ import annotations

import ast
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import NamedTuple, Optional

from ..models import ElementContext, RepairContext, RepairStepResult


class DefinitionOrderFixStep:
    """Reorder top-level definitions to resolve forward references."""

    name: str = "definition_order_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        result = reorder_definitions(code)
        if result is None:
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"reason": "parse_failed"},
            )

        reordered, moves = result
        modified = reordered != code
        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code=reordered,
            metrics={"moves": moves},
        )


class _Block(NamedTuple):
    """A contiguous block of top-level code."""

    start: int  # 0-indexed line start
    end: int  # 0-indexed line end (exclusive)
    defines: frozenset[str]  # names defined by this block
    references: frozenset[str]  # names referenced (excluding self-defined)
    kind: str  # AST node type or "preamble"


def reorder_definitions(code: str) -> tuple[str, int] | None:
    """Reorder top-level definitions to resolve forward references.

    Returns (reordered_code, number_of_moves) or None on parse failure.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    lines = code.splitlines(keepends=True)
    if not lines:
        return code, 0

    blocks = _extract_blocks(tree, lines)
    if len(blocks) <= 1:
        return code, 0

    sorted_blocks = _topo_sort(blocks)

    if [id(b) for b in blocks] == [id(b) for b in sorted_blocks]:
        return code, 0

    moves = sum(1 for a, b in zip(blocks, sorted_blocks) if a is not b)
    result_lines: list[str] = []
    for block in sorted_blocks:
        result_lines.extend(lines[block.start:block.end])

    reordered = "".join(result_lines)

    # Sanity check: reordered code must still parse
    try:
        ast.parse(reordered)
    except SyntaxError:
        return code, 0

    return reordered, moves


def _extract_blocks(tree: ast.Module, lines: list[str]) -> list[_Block]:
    """Extract top-level definition blocks from the AST."""
    # Gather top-level nodes with line ranges
    top_nodes: list[tuple[ast.AST, int, int]] = []
    for node in ast.iter_child_nodes(tree):
        if not hasattr(node, "lineno"):
            continue
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        top_nodes.append((node, start, end))

    if not top_nodes:
        return [_Block(0, len(lines), frozenset(), frozenset(), "other")]

    # Build blocks — each block extends to the next node's start
    # to capture trailing blank lines
    blocks: list[_Block] = []
    for i, (node, node_start, node_end) in enumerate(top_nodes):
        start = 0 if i == 0 else node_start
        end = top_nodes[i + 1][1] if i < len(top_nodes) - 1 else len(lines)

        defines = _names_defined_by(node)
        references = _names_referenced_by(node) - defines

        blocks.append(_Block(
            start=start,
            end=end,
            defines=frozenset(defines),
            references=frozenset(references),
            kind=type(node).__name__,
        ))

    # Merge preamble (imports + assignments before first function/class)
    # into a single block that stays first
    preamble_end = 0
    for i, block in enumerate(blocks):
        if block.kind in ("FunctionDef", "AsyncFunctionDef", "ClassDef"):
            break
        preamble_end = i + 1

    if preamble_end > 1:
        merged_defines: set[str] = set()
        merged_refs: set[str] = set()
        for b in blocks[:preamble_end]:
            merged_defines.update(b.defines)
            merged_refs.update(b.references)
        merged_refs -= merged_defines

        preamble = _Block(
            start=blocks[0].start,
            end=blocks[preamble_end - 1].end,
            defines=frozenset(merged_defines),
            references=frozenset(merged_refs),
            kind="preamble",
        )
        blocks = [preamble] + blocks[preamble_end:]

    return blocks


def _names_defined_by(node: ast.AST) -> set[str]:
    """Return names defined by a top-level node."""
    names: set[str] = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        names.add(node.name)
    elif isinstance(node, ast.ClassDef):
        names.add(node.name)
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Tuple):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        names.add(elt.id)
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            names.add(node.target.id)
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        for alias in node.names:
            names.add(alias.asname or alias.name)
    return names


def _names_referenced_by(node: ast.AST) -> set[str]:
    """Return all bare names referenced (used) within a node's subtree."""
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }


def _topo_sort(blocks: list[_Block]) -> list[_Block]:
    """Topologically sort blocks so dependencies come before dependents.

    Uses graphlib.TopologicalSorter for the core algorithm.  On cycles,
    falls back to original order for the cyclic subset.  Stable: blocks
    with no dependency relationship preserve their original order.
    """
    if not blocks:
        return blocks

    # Map: name → block index
    name_to_block: dict[str, int] = {}
    for i, block in enumerate(blocks):
        for name in block.defines:
            name_to_block[name] = i

    # Build dependency graph: block i depends on block j
    ts = TopologicalSorter()
    for i, block in enumerate(blocks):
        predecessors = set()
        for ref in block.references:
            j = name_to_block.get(ref)
            if j is not None and j != i:
                predecessors.add(j)
        ts.add(i, *predecessors)

    # Ensure all block indices are in the graph (isolated blocks too)
    for i in range(len(blocks)):
        ts.add(i)

    try:
        sorted_indices = list(ts.static_order())
    except CycleError:
        # Cycle detected — return original order (can't fix)
        return blocks

    return [blocks[i] for i in sorted_indices]
