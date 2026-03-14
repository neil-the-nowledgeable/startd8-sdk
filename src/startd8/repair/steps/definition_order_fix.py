"""Definition order repair step.

Reorders top-level definitions in generated Python files so that names
are defined before they are referenced.  Fixes F821 (undefined name)
errors caused by the model emitting a class that references functions
defined later in the file.

This is a file-whole repair step — it operates on complete Python files,
not element-body fragments.

The approach:
1. Parse the file into an AST
2. Identify top-level definition blocks (imports, assignments, functions,
   classes) preserving contiguous non-definition lines with their
   preceding definition
3. Build a dependency graph: which definitions reference which names
4. Topologically sort so dependencies come before dependents
5. Reconstruct the file from sorted blocks

Passes Ichigo Ichie: any generated Python file can have forward-reference
ordering issues regardless of project.  The fix uses only AST analysis —
no project-specific knowledge.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

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


def reorder_definitions(code: str) -> tuple[str, int] | None:
    """Reorder top-level definitions to resolve forward references.

    Returns (reordered_code, number_of_moves) or None if the code
    can't be parsed.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    lines = code.splitlines(keepends=True)
    if not lines:
        return code, 0

    # Step 1: Identify top-level definition blocks.
    # Each block is (defined_names, referenced_names, line_start, line_end).
    blocks = _extract_blocks(tree, lines)
    if len(blocks) <= 1:
        return code, 0

    # Step 2: Topological sort by dependency.
    sorted_blocks = _topo_sort(blocks)

    # Step 3: Reconstruct the file.
    original_order = [id(b) for b in blocks]
    sorted_order = [id(b) for b in sorted_blocks]
    if original_order == sorted_order:
        return code, 0

    moves = sum(1 for a, b in zip(original_order, sorted_order) if a != b)

    result_lines: list[str] = []
    for block in sorted_blocks:
        block_lines = lines[block.start : block.end]
        result_lines.extend(block_lines)

    reordered = "".join(result_lines)

    # Sanity check: reordered code must still parse
    try:
        ast.parse(reordered)
    except SyntaxError:
        return code, 0

    return reordered, moves


class _Block:
    """A contiguous block of top-level code with its defined/referenced names."""

    __slots__ = ("start", "end", "defines", "references", "is_import", "kind")

    def __init__(
        self,
        start: int,
        end: int,
        defines: frozenset[str],
        references: frozenset[str],
        is_import: bool,
        kind: str,
    ) -> None:
        self.start = start
        self.end = end
        self.defines = defines
        self.references = references
        self.is_import = is_import
        self.kind = kind


def _extract_blocks(tree: ast.Module, lines: list[str]) -> list[_Block]:
    """Extract top-level definition blocks from the AST."""
    blocks: list[_Block] = []

    # Gather top-level nodes with their line ranges
    top_nodes: list[tuple[ast.AST, int, int]] = []
    for node in ast.iter_child_nodes(tree):
        if not hasattr(node, "lineno"):
            continue
        start = node.lineno - 1  # 0-indexed
        end = (node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else node.lineno)
        top_nodes.append((node, start, end))

    if not top_nodes:
        return [_Block(0, len(lines), frozenset(), frozenset(), False, "other")]

    # Fill gaps (blank lines, comments) by extending previous block's end
    # to the next block's start
    for i in range(len(top_nodes)):
        node, start, end = top_nodes[i]

        # Extend to capture leading blank lines / comments
        # (attach them to this block)
        if i > 0:
            prev_end = top_nodes[i - 1][2]
            # Don't extend — keep gap with previous block
        else:
            start = 0  # first block starts at file top

        # Extend to next block's start to capture trailing blank lines
        if i < len(top_nodes) - 1:
            next_start = top_nodes[i + 1][1]
            end = next_start
        else:
            end = len(lines)

        defines = _names_defined_by(node)
        references = _names_referenced_by(node) - defines
        is_import = isinstance(node, (ast.Import, ast.ImportFrom))
        kind = type(node).__name__

        blocks.append(_Block(
            start=start if i == 0 else top_nodes[i][1],
            end=end,
            defines=frozenset(defines),
            references=frozenset(references),
            is_import=is_import,
            kind=kind,
        ))

    # Merge the leading section (imports, module-level assignments before
    # first function/class) into a single preamble block that stays first.
    # This prevents imports from being reordered relative to each other.
    preamble_end = 0
    for i, block in enumerate(blocks):
        if block.kind in ("FunctionDef", "AsyncFunctionDef", "ClassDef"):
            break
        preamble_end = i + 1

    if preamble_end > 1:
        merged_start = blocks[0].start
        merged_end = blocks[preamble_end - 1].end
        merged_defines: set[str] = set()
        merged_refs: set[str] = set()
        for b in blocks[:preamble_end]:
            merged_defines.update(b.defines)
            merged_refs.update(b.references)
        merged_refs -= merged_defines

        preamble = _Block(
            start=merged_start,
            end=merged_end,
            defines=frozenset(merged_defines),
            references=frozenset(merged_refs),
            is_import=True,
            kind="preamble",
        )
        blocks = [preamble] + blocks[preamble_end:]

    return blocks


def _names_defined_by(node: ast.AST) -> set[str]:
    """Return names defined by a top-level node."""
    names: set[str] = set()
    if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
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
    elif isinstance(node, ast.Import):
        for alias in node.names:
            names.add(alias.asname or alias.name)
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            names.add(alias.asname or alias.name)
    return names


def _names_referenced_by(node: ast.AST) -> set[str]:
    """Return all names referenced (used) within a node's subtree."""
    refs: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            refs.add(child.id)
        elif isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load):
            # Don't count attribute access as a name reference — only
            # bare names matter for forward-reference ordering
            pass
    return refs


def _topo_sort(blocks: list[_Block]) -> list[_Block]:
    """Topologically sort blocks so dependencies come before dependents.

    Preamble (imports/assignments) always stays first.
    Uses a stable sort — blocks with no dependency relationship preserve
    their original order.
    """
    if not blocks:
        return blocks

    # Build name → block index mapping (which block defines which name)
    name_to_block: dict[str, int] = {}
    for i, block in enumerate(blocks):
        for name in block.defines:
            name_to_block[name] = i

    # Build adjacency list: block i depends on block j if i references
    # a name defined by j
    n = len(blocks)
    deps: dict[int, set[int]] = {i: set() for i in range(n)}
    for i, block in enumerate(blocks):
        for ref in block.references:
            j = name_to_block.get(ref)
            if j is not None and j != i:
                deps[i].add(j)

    # Kahn's algorithm for topological sort (stable: use original index
    # as tiebreaker via a list-based queue)
    in_degree = {i: 0 for i in range(n)}
    for i in range(n):
        for j in deps[i]:
            in_degree[i] += 0  # i depends on j, not the other way
    # Reverse: j must come before i
    reverse_deps: dict[int, set[int]] = {i: set() for i in range(n)}
    for i in range(n):
        for j in deps[i]:
            reverse_deps[j].add(i)  # j has dependent i
            in_degree[i] += 1

    # Start with nodes that have no dependencies
    queue = sorted([i for i in range(n) if in_degree[i] == 0])
    result: list[int] = []

    while queue:
        # Pick the node with smallest original index (stable sort)
        current = queue.pop(0)
        result.append(current)
        for dependent in sorted(reverse_deps[current]):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
                queue.sort()  # maintain stable ordering

    # If there's a cycle, append remaining blocks in original order
    if len(result) < n:
        remaining = [i for i in range(n) if i not in set(result)]
        result.extend(remaining)

    return [blocks[i] for i in result]
