"""Shared AST traversal utilities for micro_prime (X-1).

Centralises the "find AST node for a ForwardElementSpec" pattern that was
duplicated across repair.py (3 sites) and splicer.py (1 site).
"""

from __future__ import annotations

import ast
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec
from startd8.utils.code_manifest import ElementKind


def find_element_node(
    tree: ast.Module,
    element: ForwardElementSpec,
    *,
    search_all_classes: bool = False,
) -> Optional[ast.AST]:
    """Locate the AST node for *element* in *tree*.

    Handles constants (Assign/AnnAssign), classes, and functions/methods.
    For methods with ``element.parent_class`` set, searches inside the
    matching class first, then falls back to top-level.

    Args:
        tree: Parsed AST module.
        element: Element specification to locate.
        search_all_classes: If True and the element is not found at top level
            or in ``parent_class``, also search inside *all* class bodies.
            Useful for over_generation_trim where the LLM may wrap a
            function inside an unexpected class.
    """
    name = element.name
    is_constant = element.kind in (
        ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS,
    )

    if is_constant:
        return _find_constant_node(tree, name)

    if element.kind == ElementKind.CLASS:
        return _find_class_node(tree, name)

    # Function/method: prefer class-scoped match for methods.
    if element.parent_class:
        node = _find_method_in_class(tree, element.parent_class, name)
        if node is not None:
            return node

    # Top-level function search.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node

    # Optionally search inside any class body (over_generation_trim pattern).
    if search_all_classes:
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == name:
                        return child

    return None


def _find_constant_node(tree: ast.Module, name: str) -> Optional[ast.AST]:
    """Find an assignment node for a constant/variable/type-alias."""
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                return node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node
    return None


def _find_class_node(tree: ast.Module, name: str) -> Optional[ast.AST]:
    """Find a class definition by name."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _find_method_in_class(
    tree: ast.Module, class_name: str, method_name: str,
) -> Optional[ast.AST]:
    """Find a method inside a specific class."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    return child
    return None
