"""
Code manifest generator — produces a deterministic, structured map of every
addressable element in a Python file using AST analysis.

Implements Phase 1 (P0) of the Code Manifest requirements:
- AST-based manifest generation for a single Python file
- Element extraction: classes, functions, methods, constants, imports
- FQN computation, span tracking, signature extraction
- JSON/YAML output with content digest for staleness detection

See docs/design/CODE_MANIFEST_REQUIREMENTS.md for the full specification.
"""

from __future__ import annotations

import ast
import dis
import hashlib
import importlib
import importlib.util
import inspect
import platform
import symtable
import sys
import threading
import types
import typing
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Generator, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Schema version — 1.4.0 = Phase 5 (inspect-based runtime introspection)
# Maximum value_repr lengths per requirements Section 3.2.3
_VALUE_REPR_STRING_MAX = 80
_VALUE_REPR_COLLECTION_MAX = 120
_VALUE_REPR_ABSOLUTE_MAX = 120

# Scope guard max length
_SCOPE_GUARD_MAX = 80

# ---------------------------------------------------------------------------
# Stdlib detection — prefer runtime set (3.10+), fallback to curated list
# ---------------------------------------------------------------------------
try:
    from startd8.workflows.builtin.preflight_rules._helpers import STDLIB_FALLBACK
except ImportError:
    STDLIB_FALLBACK: set[str] = set()  # type: ignore[no-redef]

_STDLIB_MODULES: set[str] = getattr(sys, "stdlib_module_names", None) or STDLIB_FALLBACK


# Data models live in code_manifest_models.py (Pass D extraction); re-exported
# here so `from startd8.utils.code_manifest import Element` keeps working.
from startd8.utils.code_manifest_models import *  # noqa: F401,F403,E402
# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _unparse(node: Optional[ast.AST]) -> Optional[str]:
    """Safely unparse an AST node to source text."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        logger.debug("ast.unparse failed for node type %s", type(node).__name__)
        return None


def _compute_digest(source: str) -> str:
    """Compute content hash for staleness detection."""
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()


def _compute_module_path(file_path: Path, project_root: Path) -> str:
    """
    Compute Python module path from file path.

    Examples:
        src/startd8/utils/code_manifest.py -> startd8.utils.code_manifest
        src/startd8/__init__.py -> startd8
        tests/unit/test_code_manifest.py -> tests.unit.test_code_manifest
    """
    relative = file_path.resolve().relative_to(project_root.resolve())
    parts = list(relative.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return relative.stem
    return ".".join(parts)


def _visibility_from_name(name: str) -> Visibility:
    """Determine visibility from Python naming conventions."""
    if name.startswith("__") and name.endswith("__"):
        return Visibility.PUBLIC  # dunder methods are public
    if name.startswith("__"):
        return Visibility.PRIVATE
    if name.startswith("_"):
        return Visibility.PROTECTED
    return Visibility.PUBLIC


def _is_constant_name(name: str) -> bool:
    """Check if a name follows the UPPER_CASE constant convention."""
    return name.isupper() or (name.startswith("_") and name.lstrip("_").isupper())


def _truncate_value_repr(node: Optional[ast.AST]) -> Optional[str]:
    """
    Produce a truncated string representation of an assignment value.

    Follows the requirements' type-specific truncation rules.
    """
    if node is None:
        return None
    try:
        text = ast.unparse(node)
    except Exception:
        return None

    # Normalize multi-line to single line
    if "\n" in text:
        text = " ".join(text.split())

    # Type-specific truncation (strings get a tighter limit)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        limit = _VALUE_REPR_STRING_MAX
    else:
        limit = _VALUE_REPR_ABSOLUTE_MAX

    if len(text) > limit:
        text = text[: limit - 3] + "..."

    # Absolute max safety
    if len(text) > _VALUE_REPR_ABSOLUTE_MAX:
        text = text[: _VALUE_REPR_ABSOLUTE_MAX - 3] + "..."

    return text


def _extract_decorator_text(node: ast.expr) -> str:
    """Extract full source text of a decorator expression."""
    return _unparse(node) or "<unknown>"


def _get_docstring(body: list[ast.stmt]) -> Optional[str]:
    """Extract docstring from the first statement in a body if it's a string."""
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[0].value.value
    return None


def _make_span(node: ast.AST) -> Span:
    """Create a Span from an AST node's location attributes."""
    return Span(
        start_line=getattr(node, "lineno", 0),
        start_col=getattr(node, "col_offset", 0),
        end_line=getattr(node, "end_lineno", 0) or getattr(node, "lineno", 0),
        end_col=getattr(node, "end_col_offset", 0),
    )


def _extract_signature(
    node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
) -> Signature:
    """Extract parameter list and return annotation from a function AST node."""
    params: list[Param] = []
    args = node.args

    # positional-only (before /)
    for i, arg in enumerate(args.posonlyargs):
        default_idx = i - (len(args.posonlyargs) - len(args.defaults))
        # posonlyargs share the defaults pool with args
        # Defaults are right-aligned across posonlyargs + args
        total_positional = len(args.posonlyargs) + len(args.args)
        default_offset = total_positional - len(args.defaults)
        default = args.defaults[i - default_offset] if i >= default_offset else None
        params.append(
            Param(
                name=arg.arg,
                annotation=_unparse(arg.annotation),
                default=_unparse(default),
                kind=ParamKind.POSITIONAL_ONLY,
            )
        )

    # regular positional/keyword
    for i, arg in enumerate(args.args):
        global_idx = len(args.posonlyargs) + i
        total_positional = len(args.posonlyargs) + len(args.args)
        default_offset = total_positional - len(args.defaults)
        default = (
            args.defaults[global_idx - default_offset]
            if global_idx >= default_offset
            else None
        )
        params.append(
            Param(
                name=arg.arg,
                annotation=_unparse(arg.annotation),
                default=_unparse(default),
                kind=ParamKind.POSITIONAL,
            )
        )

    # *args
    if args.vararg:
        params.append(
            Param(
                name=args.vararg.arg,
                annotation=_unparse(args.vararg.annotation),
                kind=ParamKind.VAR_POSITIONAL,
            )
        )

    # keyword-only (after *)
    for i, arg in enumerate(args.kwonlyargs):
        default = args.kw_defaults[i] if i < len(args.kw_defaults) else None
        params.append(
            Param(
                name=arg.arg,
                annotation=_unparse(arg.annotation),
                default=_unparse(default),
                kind=ParamKind.KEYWORD_ONLY,
            )
        )

    # **kwargs
    if args.kwarg:
        params.append(
            Param(
                name=args.kwarg.arg,
                annotation=_unparse(args.kwarg.annotation),
                kind=ParamKind.VAR_KEYWORD,
            )
        )

    return Signature(params=params, return_annotation=_unparse(node.returns))


def _resolve_relative_import(
    level: int,
    module_name: Optional[str],
    file_module_path: str,
) -> str:
    """Resolve a relative import to an absolute module path."""
    parts = file_module_path.split(".")
    # Go up `level` packages
    if level > len(parts):
        # Can't resolve — return raw relative syntax
        dots = "." * level
        return f"{dots}{module_name or ''}"
    base_parts = parts[: len(parts) - level]
    if module_name:
        return ".".join(base_parts + [module_name]) if base_parts else module_name
    return ".".join(base_parts) if base_parts else ""


def _detect_python_version(tree: ast.Module) -> str:
    """Infer minimum Python version from AST node types used."""
    version = "3.9"  # baseline

    for node in ast.walk(tree):
        # Python 3.10+: match statement
        if hasattr(ast, "Match") and isinstance(node, ast.Match):
            version = max(version, "3.10")
        # Python 3.12+: type alias statement
        if hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias):
            version = max(version, "3.12")

    return version


def _annotate_parents(tree: ast.AST) -> None:
    """Pre-pass: annotate every node with a _parent reference."""
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node  # type: ignore[attr-defined]


def _get_scope_guard(node: ast.AST) -> Optional[str]:
    """Determine the scope_guard for a node based on its parent context."""
    parent = getattr(node, "_parent", None)
    if parent is None:
        return None

    # Check if parent is a conditional block body
    if isinstance(parent, ast.If):
        cond_text = _unparse(parent.test) or ""
        # Check common patterns
        if "TYPE_CHECKING" in cond_text:
            return "TYPE_CHECKING"
        if "__name__" in cond_text and "__main__" in cond_text:
            return "__main__"
        guard = f"if {cond_text}"
        if len(guard) > _SCOPE_GUARD_MAX:
            guard = guard[: _SCOPE_GUARD_MAX - 3] + "..."
        return guard

    if isinstance(parent, ast.Try):
        # Determine if we're in the try body or an except handler
        if hasattr(parent, "handlers"):
            for handler in parent.handlers:
                if node in ast.iter_child_nodes(handler):
                    return "except"
        if node in getattr(parent, "body", []):
            return "try"
        if node in getattr(parent, "orelse", []):
            return None
        if node in getattr(parent, "finalbody", []):
            return None
        return "try"

    if isinstance(parent, ast.ExceptHandler):
        return "except"

    # For nodes in else blocks of if statements — check grandparent
    grandparent = getattr(parent, "_parent", None)
    if grandparent is not None and isinstance(grandparent, ast.If):
        if parent in getattr(grandparent, "orelse", []):
            cond_text = _unparse(grandparent.test) or ""
            guard = f"else (if {cond_text})"
            if len(guard) > _SCOPE_GUARD_MAX:
                guard = guard[: _SCOPE_GUARD_MAX - 3] + "..."
            return guard

    return None


def _is_conditional_context(node: ast.AST) -> bool:
    """Check if a node is inside a conditional context (TYPE_CHECKING, try/except)."""
    parent = getattr(node, "_parent", None)
    if parent is None:
        return False
    if isinstance(parent, ast.If):
        cond_text = _unparse(parent.test) or ""
        if "TYPE_CHECKING" in cond_text:
            return True
    if isinstance(parent, (ast.Try, ast.ExceptHandler)):
        # Check if the except handler catches ImportError
        if isinstance(parent, ast.ExceptHandler):
            if parent.type is not None:
                type_text = _unparse(parent.type) or ""
                if "ImportError" in type_text or "ModuleNotFoundError" in type_text:
                    return True
        return True
    return False


def _detect_class_tags(
    node: ast.ClassDef, decorator_texts: list[str]
) -> list[str]:
    """Detect framework/pattern tags for a class element."""
    tags: list[str] = []

    # Check base classes
    base_names = [_unparse(b) or "" for b in node.bases]
    if any("BaseModel" in b for b in base_names):
        tags.append("pydantic_model")
    if any("Protocol" in b for b in base_names):
        tags.append("protocol")
    if any(b in ("ABC", "abc.ABC") for b in base_names):
        tags.append("abstract")

    # Check decorators
    for dec_text in decorator_texts:
        if "dataclass" in dec_text:
            tags.append("dataclass")
            break
    for dec_text in decorator_texts:
        if dec_text in ("attr.s", "attrs", "define", "attr.define"):
            tags.append("attrs")
            break

    # Check body for pydantic indicators
    if "pydantic_model" not in tags:
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "model_config":
                        tags.append("pydantic_model")
                        break
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in stmt.decorator_list:
                    dec_text = _unparse(dec) or ""
                    if "validator" in dec_text or "field_validator" in dec_text:
                        if "pydantic_model" not in tags:
                            tags.append("pydantic_model")
                        break

    # Check for abstract methods
    if "abstract" not in tags:
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in stmt.decorator_list:
                    dec_text = _unparse(dec) or ""
                    if "abstractmethod" in dec_text:
                        tags.append("abstract")
                        break
                if "abstract" in tags:
                    break

    return sorted(set(tags))


# ═══════════════════════════════════════════════════════════════════════════
# AST Visitor
# ═══════════════════════════════════════════════════════════════════════════

class _ManifestVisitor(ast.NodeVisitor):
    """Single-pass AST visitor that builds manifest elements."""

    def __init__(
        self,
        module_path: str,
        file_module_path: str,
        all_names: Optional[set[str]] = None,
        is_init_file: bool = False,
        branch_names: Optional[set[str]] = None,
    ) -> None:
        self.module_path = module_path
        self.file_module_path = file_module_path
        self._scope_stack: list[str] = [module_path]
        self._in_class: bool = False
        self.elements: list[Element] = []
        self.imports: list[ImportEntry] = []
        self._all_names: Optional[set[str]] = all_names
        self._is_init_file: bool = is_init_file
        self._branch_names: set[str] = branch_names or set()
        # Track name occurrences for duplicate detection
        self._name_counts: dict[str, Counter[str]] = {}  # scope -> Counter of names

    @property
    def _current_scope(self) -> str:
        return ".".join(self._scope_stack) if self._scope_stack else self.module_path

    def _make_fqn(self, name: str) -> str:
        return f"{self._current_scope}.{name}" if self._current_scope else name

    def _count_name(self, name: str) -> int:
        """Track name occurrences in current scope for branch disambiguation."""
        scope = self._current_scope
        if scope not in self._name_counts:
            self._name_counts[scope] = Counter()
        count = self._name_counts[scope][name]
        self._name_counts[scope][name] += 1
        return count

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        decorator_texts = [_extract_decorator_text(d) for d in node.decorator_list]
        bases = [_unparse(b) or "" for b in node.bases]

        # Extract metaclass from keywords
        metaclass = None
        for kw in node.keywords:
            if kw.arg == "metaclass":
                metaclass = _unparse(kw.value)

        tags = _detect_class_tags(node, decorator_texts)
        scope_guard = _get_scope_guard(node)

        # Visit body to extract children
        children: list[Element] = []
        class_variables: list[Element] = []
        self._scope_stack.append(node.name)
        old_in_class = self._in_class
        self._in_class = True

        # Collect overload counts for disambiguation
        overload_names: Counter[str] = Counter()
        property_names: set[str] = set()
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                has_overload = any(
                    "overload" in (_unparse(d) or "") for d in stmt.decorator_list
                )
                if has_overload:
                    overload_names[stmt.name] += 1
                has_property_setter = any(
                    ".setter" in (_unparse(d) or "") or ".deleter" in (_unparse(d) or "")
                    for d in stmt.decorator_list
                )
                has_property = any(
                    (_unparse(d) or "") == "property" for d in stmt.decorator_list
                )
                if has_property or has_property_setter:
                    property_names.add(stmt.name)

        overload_counters: Counter[str] = Counter()
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child = self._process_function(
                    stmt,
                    in_class=True,
                    overload_names=overload_names,
                    overload_counters=overload_counters,
                    property_names=property_names,
                )
                if child:
                    children.append(child)
            elif isinstance(stmt, ast.ClassDef):
                # Nested class — recurse
                child_visitor = _ManifestVisitor(
                    self._current_scope, self.file_module_path, self._all_names,
                    is_init_file=self._is_init_file,
                    branch_names=self._branch_names,
                )
                child_visitor._in_class = False
                child_visitor._scope_stack = list(self._scope_stack)
                child_visitor.visit_ClassDef(stmt)
                if child_visitor.elements:
                    children.append(child_visitor.elements[0])
            elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                cv = self._process_assignment(stmt, is_class_var=True)
                if cv:
                    class_variables.append(cv)

        self._in_class = old_in_class
        self._scope_stack.pop()

        fqn = self._make_fqn(node.name)
        elem = Element(
            kind=ElementKind.CLASS,
            name=node.name,
            fqn=fqn,
            span=_make_span(node),
            docstring=_get_docstring(node.body),
            decorators=decorator_texts,
            children=children,
            scope_guard=scope_guard,
            bases=bases,
            metaclass=metaclass,
            tags=tags,
            class_variables=class_variables,
            visibility=_visibility_from_name(node.name),
            signature=None,
        )
        self.elements.append(elem)

    def _process_function(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        in_class: bool = False,
        overload_names: Optional[Counter[str]] = None,
        overload_counters: Optional[Counter[str]] = None,
        property_names: Optional[set[str]] = None,
    ) -> Optional[Element]:
        """Process a function/method definition into an Element."""
        decorator_texts = [_extract_decorator_text(d) for d in node.decorator_list]

        is_static = "staticmethod" in decorator_texts
        is_classmethod = "classmethod" in decorator_texts
        is_abstract = any("abstractmethod" in d for d in decorator_texts)

        # Determine kind
        is_property_getter = "property" in decorator_texts
        is_property_setter = any(".setter" in d for d in decorator_texts)
        is_property_deleter = any(".deleter" in d for d in decorator_texts)
        is_async = isinstance(node, ast.AsyncFunctionDef)

        if is_property_getter:
            kind = ElementKind.PROPERTY
        elif in_class:
            kind = ElementKind.ASYNC_METHOD if is_async else ElementKind.METHOD
        else:
            kind = ElementKind.ASYNC_FUNCTION if is_async else ElementKind.FUNCTION

        # FQN with disambiguation
        base_fqn = self._make_fqn(node.name)

        # Overload disambiguation
        has_overload = any("overload" in d for d in decorator_texts)
        overload_index: Optional[int] = None
        if has_overload and overload_counters is not None:
            overload_index = overload_counters[node.name]
            overload_counters[node.name] += 1
            fqn = f"{base_fqn}@overload[{overload_index}]"
        elif property_names and node.name in property_names:
            # Property triad disambiguation
            if is_property_getter:
                fqn = f"{base_fqn}@getter"
            elif is_property_setter:
                fqn = f"{base_fqn}@setter"
                kind = ElementKind.METHOD
            elif is_property_deleter:
                fqn = f"{base_fqn}@deleter"
                kind = ElementKind.METHOD
            else:
                fqn = base_fqn
        else:
            # Branch disambiguation for names in if/else conditionals
            if node.name in self._branch_names and _get_scope_guard(node) is not None:
                idx = self._count_name(node.name)
                fqn = f"{base_fqn}@branch[{idx}]"
            else:
                fqn = base_fqn

        scope_guard = _get_scope_guard(node)
        signature = _extract_signature(node)

        elem = Element(
            kind=kind,
            name=node.name,
            fqn=fqn,
            span=_make_span(node),
            docstring=_get_docstring(node.body),
            decorators=decorator_texts,
            scope_guard=scope_guard,
            signature=signature,
            is_static=is_static,
            is_classmethod=is_classmethod,
            is_abstract=is_abstract,
            visibility=_visibility_from_name(node.name),
            overload_index=overload_index,
        )
        return elem

    def _extract_function_children(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
    ) -> list[Element]:
        """Recurse into a function body to find nested functions and classes.

        Uses model_copy(update=...) to attach children because Element is
        frozen (immutable Pydantic model).
        """
        children: list[Element] = []
        self._scope_stack.append(node.name)
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child = self._process_function(stmt, in_class=False)
                if child:
                    # Recurse for deeper nesting
                    grandchildren = self._extract_function_children(stmt)
                    if grandchildren:
                        child = child.model_copy(update={"children": grandchildren})
                    children.append(child)
            elif isinstance(stmt, ast.ClassDef):
                child_visitor = _ManifestVisitor(
                    self._current_scope, self.file_module_path, self._all_names,
                    is_init_file=self._is_init_file,
                    branch_names=self._branch_names,
                )
                child_visitor._in_class = False
                child_visitor._scope_stack = list(self._scope_stack)
                child_visitor.visit_ClassDef(stmt)
                if child_visitor.elements:
                    children.append(child_visitor.elements[0])
        self._scope_stack.pop()
        return children

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._in_class:
            return  # Handled by visit_ClassDef
        elem = self._process_function(node, in_class=False)
        if elem:
            children = self._extract_function_children(node)
            if children:
                elem = elem.model_copy(update={"children": children})
            self.elements.append(elem)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._in_class:
            return
        elem = self._process_function(node, in_class=False)
        if elem:
            children = self._extract_function_children(node)
            if children:
                elem = elem.model_copy(update={"children": children})
            self.elements.append(elem)

    def _process_assignment(
        self, node: Union[ast.Assign, ast.AnnAssign], is_class_var: bool = False
    ) -> Optional[Element]:
        """Process an assignment statement into an Element."""
        if isinstance(node, ast.AnnAssign):
            if node.target is None or not isinstance(node.target, ast.Name):
                return None
            name = node.target.id
            type_ann = _unparse(node.annotation)

            # TypeAlias detection (pre-3.12)
            if type_ann == "TypeAlias":
                kind = ElementKind.TYPE_ALIAS
            elif is_class_var:
                kind = ElementKind.VARIABLE
            elif _is_constant_name(name):
                kind = ElementKind.CONSTANT
            else:
                kind = ElementKind.VARIABLE

            value_repr = _truncate_value_repr(node.value) if node.value else None
        elif isinstance(node, ast.Assign):
            if not node.targets or not isinstance(node.targets[0], ast.Name):
                return None
            name = node.targets[0].id
            type_ann = None

            if is_class_var:
                kind = ElementKind.VARIABLE
            elif _is_constant_name(name):
                kind = ElementKind.CONSTANT
            else:
                kind = ElementKind.VARIABLE

            value_repr = _truncate_value_repr(node.value)
        else:
            return None

        scope_guard = _get_scope_guard(node)
        base_fqn = self._make_fqn(name)

        # Branch disambiguation for names in if/else conditionals
        if name in self._branch_names and scope_guard is not None:
            idx = self._count_name(name)
            fqn = f"{base_fqn}@branch[{idx}]"
        else:
            fqn = base_fqn

        return Element(
            kind=kind,
            name=name,
            fqn=fqn,
            span=_make_span(node),
            scope_guard=scope_guard,
            type_annotation=type_ann,
            value_repr=value_repr,
            visibility=_visibility_from_name(name),
            signature=None,
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._in_class:
            return
        elem = self._process_assignment(node)
        if elem:
            self.elements.append(elem)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._in_class:
            return
        elem = self._process_assignment(node)
        if elem:
            self.elements.append(elem)

    def visit_Import(self, node: ast.Import) -> None:
        is_conditional = _is_conditional_context(node)
        for alias in node.names:
            is_reexport = (
                self._all_names is not None and alias.asname in self._all_names
            ) if alias.asname else (
                self._all_names is not None and alias.name in self._all_names
            )
            self.imports.append(
                ImportEntry(
                    kind="import",
                    module=alias.name,
                    names=[],
                    alias=alias.asname,
                    span=_make_span(node),
                    is_relative=False,
                    is_conditional=is_conditional,
                    is_reexport=bool(is_reexport),
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        is_conditional = _is_conditional_context(node)
        level = node.level or 0
        raw_module = node.module or ""

        if level > 0:
            module = _resolve_relative_import(level, raw_module or None, self.file_module_path)
            is_relative = True
        else:
            module = raw_module
            is_relative = False

        names = [alias.name for alias in (node.names or [])]
        # Check re-export: any imported name in __all__
        is_reexport = False
        if self._all_names is not None:
            for alias in (node.names or []):
                effective_name = alias.asname or alias.name
                if effective_name in self._all_names:
                    is_reexport = True
                    break

        # Heuristics (a) + (c): relative import in __init__.py without aliasing
        if not is_reexport and self._is_init_file and is_relative:
            has_no_alias = all(alias.asname is None for alias in (node.names or []))
            if has_no_alias:
                is_reexport = True

        self.imports.append(
            ImportEntry(
                kind="from",
                module=module,
                names=names,
                alias=None,
                span=_make_span(node),
                is_relative=is_relative,
                is_conditional=is_conditional,
                is_reexport=is_reexport,
            )
        )

    # Handle Python 3.12+ type statements
    def visit_TypeAlias(self, node: ast.AST) -> None:
        # ast.TypeAlias exists in 3.12+
        name_node = getattr(node, "name", None)
        if name_node is None:
            return
        name = getattr(name_node, "id", None) or str(name_node)
        fqn = self._make_fqn(name)
        value = getattr(node, "value", None)
        value_repr = _truncate_value_repr(value)
        scope_guard = _get_scope_guard(node)

        elem = Element(
            kind=ElementKind.TYPE_ALIAS,
            name=name,
            fqn=fqn,
            span=_make_span(node),
            scope_guard=scope_guard,
            value_repr=value_repr,
            visibility=_visibility_from_name(name),
            signature=None,
        )
        self.elements.append(elem)


def _scan_branch_names(body: list[ast.stmt]) -> set[str]:
    """
    Pre-scan a list of statements for names defined in multiple branches
    of the same if/else conditional.

    Only scans the immediate statement list — not recursive into nested scopes.
    Returns a set of names that need @branch[N] disambiguation.
    """
    branch_names: set[str] = set()
    for node in body:
        if not isinstance(node, ast.If):
            continue
        # Collect names defined in if.body and if.orelse
        if_names: set[str] = set()
        else_names: set[str] = set()

        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if_names.add(stmt.name)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        if_names.add(target.id)
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name):
                    if_names.add(stmt.target.id)

        for stmt in node.orelse:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                else_names.add(stmt.name)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        else_names.add(target.id)
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name):
                    else_names.add(stmt.target.id)

        # Names in both branches need disambiguation
        branch_names |= if_names & else_names
    return branch_names


def _extract_all_names(tree: ast.Module) -> Optional[set[str]]:
    """Extract names from __all__ if it's a literal list/tuple at module level."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        names = set()
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                names.add(elt.value)
                        return names
    return None


def _classify_imports(
    imports: list[ImportEntry],
    project_module: str,
    stdlib_set: set[str],
) -> Dependencies:
    """Classify imports into internal, external, stdlib, conditional."""
    internal: list[str] = []
    external: list[str] = []
    stdlib: list[str] = []
    conditional: list[str] = []

    for imp in imports:
        root = imp.module.split(".")[0] if imp.module else ""

        # Relative imports are always internal
        if imp.is_relative:
            internal.append(imp.module)
        elif root in stdlib_set:
            stdlib.append(imp.module)
        elif root == project_module or imp.module.startswith(project_module + "."):
            internal.append(imp.module)
        else:
            external.append(root)

        # Conditional imports are also tagged
        if imp.is_conditional:
            conditional.append(imp.module)

    return Dependencies(
        internal=sorted(set(internal)),
        external=sorted(set(external)),
        stdlib=sorted(set(stdlib)),
        conditional=sorted(set(conditional)),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 6: bytecode call graph analysis
# ═══════════════════════════════════════════════════════════════════════════

_BYTECODE_SUPPORTED = (
    platform.python_implementation() == "CPython"
    and sys.version_info >= (3, 12)
)

# Builtin names to filter from call graphs
_BUILTIN_NAMES: frozenset[str] = frozenset(
    __builtins__.keys() if isinstance(__builtins__, dict) else dir(__builtins__)
)

# Names that indicate dynamic dispatch
_DYNAMIC_DISPATCH_NAMES: frozenset[str] = frozenset({
    "getattr", "setattr", "delattr", "eval", "exec",
})

# Call opcodes in CPython 3.12+
_CALL_OPCODES: frozenset[str] = frozenset({
    "CALL", "CALL_KW", "CALL_FUNCTION_EX",
})

# Opcodes that load a name (preceding CALL)
_LOAD_OPCODES: frozenset[str] = frozenset({
    "LOAD_GLOBAL", "LOAD_ATTR", "LOAD_FAST", "LOAD_FAST_BORROW",
    "LOAD_DEREF", "LOAD_NAME", "LOAD_SUPER_ATTR",
})

# Callable element kinds for bytecode enrichment
_CALLABLE_ELEMENT_KINDS = frozenset({
    ElementKind.FUNCTION,
    ElementKind.ASYNC_FUNCTION,
    ElementKind.METHOD,
    ElementKind.ASYNC_METHOD,
    ElementKind.PROPERTY,
})


def _extract_code_objects(
    code: types.CodeType, max_depth: int = 20,
) -> dict[str, types.CodeType]:
    """Walk code.co_consts recursively to map co_qualname → code object."""
    if max_depth <= 0:
        return {}
    result: dict[str, types.CodeType] = {}
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            result[const.co_qualname] = const
            result.update(_extract_code_objects(const, max_depth - 1))
    return result


def _resolve_call_target(
    instructions: list[dis.Instruction],
    call_idx: int,
) -> tuple[str, CallKind, Optional[str]]:
    """Scan backwards from call_idx to find the callee.

    Uses a two-pass approach:
    1. First, look for high-priority callee indicators (LOAD_GLOBAL+NULL,
       LOAD_ATTR+method, LOAD_SUPER_ATTR) — these unambiguously identify
       the callable even when followed by argument-loading instructions.
    2. Fall back to LOAD_FAST/LOAD_DEREF/LOAD_NAME for local calls.

    Returns:
        (target_name, call_kind, receiver_name)
    """
    scan_start = max(call_idx - 30, 0)

    # Pass 1: Look for definitive callee indicators (highest priority)
    for i in range(call_idx - 1, scan_start - 1, -1):
        inst = instructions[i]

        # Stop scanning at boundaries
        if inst.opname in _CALL_OPCODES:
            break
        if inst.opname in (
            "STORE_FAST", "STORE_FAST_MAYBE_NULL", "STORE_NAME",
            "STORE_GLOBAL", "STORE_DEREF", "STORE_ATTR",
            "POP_TOP", "RETURN_VALUE", "RETURN_CONST",
            "JUMP_FORWARD", "JUMP_BACKWARD",
            "POP_JUMP_IF_TRUE", "POP_JUMP_IF_FALSE",
            "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE",
        ):
            break

        # LOAD_SUPER_ATTR — super().method()
        if inst.opname == "LOAD_SUPER_ATTR":
            return (str(inst.argval), CallKind.METHOD_CALL, "super()")

        # LOAD_ATTR with method flag — obj.method()
        if inst.opname == "LOAD_ATTR" and inst.arg is not None and inst.arg & 1:
            target = str(inst.argval)
            receiver = None
            for j in range(i - 1, max(i - 10, scan_start - 1), -1):
                prev = instructions[j]
                if prev.opname in ("LOAD_FAST", "LOAD_FAST_BORROW", "LOAD_DEREF"):
                    receiver = str(prev.argval)
                    break
                elif prev.opname == "LOAD_ATTR":
                    receiver = str(prev.argval)
                    break
                elif prev.opname == "LOAD_GLOBAL":
                    receiver = str(prev.argval)
                    break
            return (target, CallKind.METHOD_CALL, receiver)

        # LOAD_GLOBAL with NULL push — function call setup
        if inst.opname == "LOAD_GLOBAL" and inst.arg is not None and inst.arg & 1:
            target = str(inst.argval)
            if target in _BUILTIN_NAMES:
                return (target, CallKind.BUILTIN_CALL, None)
            if target in _DYNAMIC_DISPATCH_NAMES:
                return (target, CallKind.DYNAMIC_CALL, None)
            return (target, CallKind.FUNCTION_CALL, None)

        # LOAD_NAME — module-level call
        if inst.opname == "LOAD_NAME":
            target = str(inst.argval)
            if target in _BUILTIN_NAMES:
                return (target, CallKind.BUILTIN_CALL, None)
            return (target, CallKind.FUNCTION_CALL, None)

    # Pass 2: Fall back to LOAD_FAST/LOAD_DEREF (local callable)
    # Only match the instruction immediately before CALL (or before PUSH_NULL)
    for i in range(call_idx - 1, scan_start - 1, -1):
        inst = instructions[i]
        if inst.opname in _CALL_OPCODES:
            break
        if inst.opname in (
            "STORE_FAST", "STORE_FAST_MAYBE_NULL", "STORE_NAME",
            "STORE_GLOBAL", "STORE_DEREF", "STORE_ATTR",
            "POP_TOP", "RETURN_VALUE", "RETURN_CONST",
            "JUMP_FORWARD", "JUMP_BACKWARD",
            "POP_JUMP_IF_TRUE", "POP_JUMP_IF_FALSE",
            "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE",
        ):
            break
        if inst.opname in ("LOAD_FAST", "LOAD_FAST_BORROW"):
            return (str(inst.argval), CallKind.FUNCTION_CALL, None)
        if inst.opname == "LOAD_DEREF":
            return (str(inst.argval), CallKind.FUNCTION_CALL, None)

    return ("<unknown>", CallKind.DYNAMIC_CALL, None)


def _analyze_bytecode(code_obj: types.CodeType) -> CallGraphInfo:
    """Analyze a single code object's bytecode for calls and attribute access.

    Returns a CallGraphInfo with deduplicated calls, attribute patterns,
    and dynamic dispatch flag.

    Strategy: collect all instructions, then for each CALL opcode scan
    backwards to find the callable load.  For attribute access, detect
    LOAD_FAST 'self' → STORE_ATTR / LOAD_ATTR / DELETE_ATTR patterns.
    """
    calls: list[CallEntry] = []
    attr_reads: set[str] = set()
    attr_writes: set[str] = set()
    has_dynamic = False
    seen_calls: set[tuple[str, CallKind]] = set()

    all_insts = list(dis.get_instructions(code_obj))

    # Pass 1: extract attribute access on self
    for i, inst in enumerate(all_insts):
        if inst.opname not in ("LOAD_FAST", "LOAD_FAST_BORROW"):
            continue
        if inst.argval != "self":
            continue
        # Check next instruction
        if i + 1 >= len(all_insts):
            continue
        nxt = all_insts[i + 1]
        if nxt.opname == "LOAD_ATTR" and nxt.arg is not None and not (nxt.arg & 1):
            attr_reads.add(str(nxt.argval))
        elif nxt.opname == "STORE_ATTR":
            attr_writes.add(str(nxt.argval))
        elif nxt.opname == "DELETE_ATTR":
            attr_writes.add(str(nxt.argval))

    # Pass 2: extract calls
    for i, inst in enumerate(all_insts):
        if inst.opname not in _CALL_OPCODES:
            continue
        target, kind, receiver = _resolve_call_target(all_insts, i)

        # Check for dynamic dispatch
        if target in _DYNAMIC_DISPATCH_NAMES:
            has_dynamic = True

        # Deduplicate by (target, kind)
        key = (target, kind)
        if key not in seen_calls:
            seen_calls.add(key)
            calls.append(CallEntry(
                target=target,
                kind=kind,
                receiver=receiver,
                line=inst.positions.lineno if inst.positions else None,
            ))

    return CallGraphInfo(
        calls=calls,
        attribute_reads=sorted(attr_reads),
        attribute_writes=sorted(attr_writes),
        has_dynamic_dispatch=has_dynamic,
    )


def _qualname_to_fqn(qualname: str, module_path: str) -> str:
    """Convert co_qualname to a full FQN using the module path."""
    return f"{module_path}.{qualname}"


def _enrich_with_callgraph(
    elements: list[Element],
    code_objects: dict[str, types.CodeType],
    module_path: str,
) -> list[Element]:
    """Attach CallGraphInfo to callable elements by matching co_qualname."""
    enriched: list[Element] = []
    for elem in elements:
        try:
            if elem.kind in _CALLABLE_ELEMENT_KINDS:
                # Compute the qualname that would match the code object
                # Element FQN = module.path.ClassName.method_name
                # co_qualname = ClassName.method_name (no module prefix)
                qualname = elem.fqn
                if qualname.startswith(module_path + "."):
                    qualname = qualname[len(module_path) + 1:]
                # Strip disambiguation suffixes
                for suffix in ("@getter", "@setter", "@deleter"):
                    if qualname.endswith(suffix):
                        qualname = qualname[: -len(suffix)]
                        break
                # Strip @overload[N] and @branch[N]
                if "@overload[" in qualname:
                    qualname = qualname[: qualname.index("@overload[")]
                if "@branch[" in qualname:
                    qualname = qualname[: qualname.index("@branch[")]

                co = code_objects.get(qualname)
                if co is not None:
                    info = _analyze_bytecode(co)
                    # Recurse into children
                    enriched_children = (
                        _enrich_with_callgraph(elem.children, code_objects, module_path)
                        if elem.children else elem.children
                    )
                    enriched_class_vars = elem.class_variables
                    enriched.append(
                        elem.model_copy(update={
                            "call_graph": info,
                            "children": enriched_children,
                            "class_variables": enriched_class_vars,
                        })
                    )
                else:
                    # No matching code object — enrich children only
                    enriched_children = (
                        _enrich_with_callgraph(elem.children, code_objects, module_path)
                        if elem.children else elem.children
                    )
                    enriched.append(
                        elem.model_copy(update={"children": enriched_children})
                        if enriched_children is not elem.children else elem
                    )
            elif elem.kind == ElementKind.CLASS:
                # Recurse into class children and class_variables
                enriched_children = (
                    _enrich_with_callgraph(elem.children, code_objects, module_path)
                    if elem.children else elem.children
                )
                enriched_class_vars = elem.class_variables  # non-callable, skip
                enriched.append(
                    elem.model_copy(update={
                        "children": enriched_children,
                        "class_variables": enriched_class_vars,
                    })
                )
            else:
                enriched.append(elem)
        except Exception:
            logger.warning(
                "Failed to enrich %s '%s' with call graph; skipping",
                elem.kind.value, elem.name, exc_info=True,
            )
            enriched.append(elem)
    return enriched


def _resolve_intra_file_fqns(
    elements: list[Element],
    module_path: str,
    imports: list[ImportEntry],
) -> list[Element]:
    """Resolve call target FQNs for intra-file calls.

    For each element with call_graph, resolve target_fqn for:
    1. Global function calls → {module_path}.{name} if name exists in file
    2. Method calls on self → {enclosing_class_fqn}.{method_name}
    3. Imported names → cross-reference against imports list
    """
    # Build name→FQN index for all elements in the file
    file_names: dict[str, str] = {}
    _collect_element_names(elements, file_names)

    # Build imported name → module mapping
    import_names: dict[str, str] = {}
    for imp in imports:
        if imp.kind == "from":
            for name in imp.names:
                import_names[name] = f"{imp.module}.{name}"
        elif imp.kind == "import":
            name = imp.alias or imp.module.split(".")[-1]
            import_names[name] = imp.module

    return _resolve_elements(elements, module_path, file_names, import_names)


def _collect_element_names(elements: list[Element], names: dict[str, str]) -> None:
    """Collect name → FQN mappings for all elements recursively."""
    for elem in elements:
        names[elem.name] = elem.fqn
        _collect_element_names(elem.children, names)
        _collect_element_names(elem.class_variables, names)


def _resolve_elements(
    elements: list[Element],
    module_path: str,
    file_names: dict[str, str],
    import_names: dict[str, str],
) -> list[Element]:
    """Recursively resolve call target FQNs in elements."""
    resolved: list[Element] = []
    for elem in elements:
        if elem.call_graph is not None and elem.call_graph.calls:
            new_calls: list[CallEntry] = []
            unresolved: list[str] = list(elem.call_graph.unresolved_calls)
            for call in elem.call_graph.calls:
                if call.target_fqn is not None:
                    # Already resolved
                    new_calls.append(call)
                    continue
                fqn = _try_resolve_fqn(
                    call, elem, module_path, file_names, import_names,
                )
                if fqn is not None:
                    new_calls.append(call.model_copy(update={"target_fqn": fqn}))
                else:
                    new_calls.append(call)
                    if call.kind not in (CallKind.BUILTIN_CALL, CallKind.DYNAMIC_CALL):
                        if call.target not in unresolved:
                            unresolved.append(call.target)
            new_cg = elem.call_graph.model_copy(update={
                "calls": new_calls,
                "unresolved_calls": sorted(set(unresolved)),
            })
            # Recurse
            children = (
                _resolve_elements(elem.children, module_path, file_names, import_names)
                if elem.children else elem.children
            )
            resolved.append(elem.model_copy(update={
                "call_graph": new_cg,
                "children": children,
            }))
        else:
            # Recurse into children/class children even without call_graph
            children = (
                _resolve_elements(elem.children, module_path, file_names, import_names)
                if elem.children else elem.children
            )
            if children is not elem.children:
                resolved.append(elem.model_copy(update={"children": children}))
            else:
                resolved.append(elem)
    return resolved


def _try_resolve_fqn(
    call: CallEntry,
    elem: Element,
    module_path: str,
    file_names: dict[str, str],
    import_names: dict[str, str],
) -> Optional[str]:
    """Attempt to resolve a single call target to an FQN."""
    target = call.target

    # 1. Method call on self → resolve to enclosing class
    if call.kind == CallKind.METHOD_CALL and call.receiver == "self":
        # Find enclosing class from the element's FQN
        # e.g. module.ClassName.method -> module.ClassName
        parts = elem.fqn.rsplit(".", 1)
        if len(parts) == 2:
            class_fqn = parts[0]
            candidate = f"{class_fqn}.{target}"
            if candidate in file_names.values():
                return candidate
            # Even if not in file, still resolve to expected FQN
            return candidate
        return None

    # 2. Global function call → check file elements
    if call.kind == CallKind.FUNCTION_CALL:
        # Check local file names
        if target in file_names:
            return file_names[target]
        # Check imports
        if target in import_names:
            return import_names[target]

    # 3. Method call on non-self receiver
    if call.kind == CallKind.METHOD_CALL and call.receiver == "super()":
        # Best-effort: resolve to parent class method
        parts = elem.fqn.rsplit(".", 1)
        if len(parts) == 2:
            return f"{parts[0]}.{target}"
        return None

    return None


def _collect_call_edges(elements: list[Element]) -> list[CallEdge]:
    """Walk all elements recursively and collect resolved call edges."""
    edges: list[CallEdge] = []
    seen: set[tuple[str, str]] = set()

    def _walk(elems: list[Element]) -> None:
        for elem in elems:
            if elem.call_graph is not None:
                for call in elem.call_graph.calls:
                    if call.target_fqn is not None:
                        key = (elem.fqn, call.target_fqn)
                        if key not in seen:
                            seen.add(key)
                            edges.append(CallEdge(
                                caller_fqn=elem.fqn,
                                callee_fqn=call.target_fqn,
                            ))
            _walk(elem.children)
            _walk(elem.class_variables)

    _walk(elements)
    return edges


def _augment_with_bytecode(
    source: str,
    filename: str,
    elements: list[Element],
    module_path: str,
    imports: list[ImportEntry],
) -> tuple[list[Element], list[CallEdge]]:
    """Augment elements with bytecode-derived call graph information.

    Follows the same defensive pattern as _augment_with_symtable().
    Returns (enriched_elements, call_edges). On failure, returns
    (unenriched_elements, []).
    """
    if not _BYTECODE_SUPPORTED:
        logger.info("Bytecode analysis skipped: requires CPython 3.12+")
        return elements, []
    try:
        code_obj = compile(source, filename, "exec")
    except SyntaxError:
        logger.warning("compile() failed on %s; skipping bytecode", filename)
        return elements, []
    except Exception:
        logger.error(
            "Unexpected compile() error on %s", filename, exc_info=True,
        )
        return elements, []

    try:
        code_objects = _extract_code_objects(code_obj)
        enriched = _enrich_with_callgraph(elements, code_objects, module_path)
        enriched = _resolve_intra_file_fqns(enriched, module_path, imports)
        call_edges = _collect_call_edges(enriched)
        return enriched, call_edges
    except Exception:
        logger.error(
            "Bytecode enrichment failed on %s; returning unenriched elements",
            filename, exc_info=True,
        )
        return elements, []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: symtable augmentation
# ═══════════════════════════════════════════════════════════════════════════

_SCOPE_ELEMENT_KINDS = frozenset({
    ElementKind.CLASS,
    ElementKind.FUNCTION,
    ElementKind.ASYNC_FUNCTION,
    ElementKind.METHOD,
    ElementKind.ASYNC_METHOD,
    ElementKind.PROPERTY,
})


def _classify_scope_kind(sym: symtable.Symbol) -> ScopeKind:
    """Classify a symtable Symbol using the priority list from ScopeKind docstring.

    Priority (first match wins):
    1. parameter  2. imported  3. nonlocal  4. free  5. global  6. local

    nonlocal is checked before free because explicit ``nonlocal x`` declarations
    also have ``is_free()=True`` (they reference an enclosing scope).  Checking
    nonlocal first distinguishes explicit declarations from implicit captures.
    """
    if sym.is_parameter():
        return ScopeKind.PARAMETER
    if sym.is_imported():
        return ScopeKind.IMPORTED
    if sym.is_nonlocal():
        return ScopeKind.NONLOCAL
    if sym.is_free():
        return ScopeKind.FREE
    if sym.is_global():
        return ScopeKind.GLOBAL
    return ScopeKind.LOCAL


def _symbol_to_entry(sym: symtable.Symbol) -> SymbolEntry:
    """Convert a symtable Symbol to a SymbolEntry."""
    return SymbolEntry(
        name=sym.get_name(),
        scope=_classify_scope_kind(sym),
        is_referenced=sym.is_referenced(),
        is_assigned=sym.is_assigned(),
        is_parameter=sym.is_parameter(),
    )


def _build_symbol_info(scope: symtable.SymbolTable) -> SymbolInfo:
    """Build a SymbolInfo from all symbols in a symtable scope."""
    entries: list[SymbolEntry] = []
    local_vars: list[str] = []
    global_vars: list[str] = []
    nonlocal_vars: list[str] = []
    free_vars: list[str] = []
    imported_names: list[str] = []

    for sym in scope.get_symbols():
        entry = _symbol_to_entry(sym)
        entries.append(entry)
        kind = entry.scope
        name = entry.name
        if kind in (ScopeKind.LOCAL, ScopeKind.PARAMETER):
            local_vars.append(name)
        elif kind == ScopeKind.GLOBAL:
            global_vars.append(name)
        elif kind == ScopeKind.NONLOCAL:
            nonlocal_vars.append(name)
        elif kind == ScopeKind.FREE:
            free_vars.append(name)
        elif kind == ScopeKind.IMPORTED:
            imported_names.append(name)

    # Sort for deterministic output
    entries.sort(key=lambda e: e.name)

    return SymbolInfo(
        local_vars=sorted(local_vars),
        global_vars=sorted(global_vars),
        nonlocal_vars=sorted(nonlocal_vars),
        free_vars=sorted(free_vars),
        imported_names=sorted(imported_names),
        symbols=entries,
        is_closure=len(free_vars) > 0,
    )


def _build_single_symbol_info(sym: symtable.Symbol) -> SymbolInfo:
    """Build a minimal SymbolInfo for a non-scope element from a single symbol lookup."""
    entry = _symbol_to_entry(sym)
    kind = entry.scope
    name = entry.name
    return SymbolInfo(
        local_vars=[name] if kind in (ScopeKind.LOCAL, ScopeKind.PARAMETER) else [],
        global_vars=[name] if kind == ScopeKind.GLOBAL else [],
        nonlocal_vars=[name] if kind == ScopeKind.NONLOCAL else [],
        free_vars=[name] if kind == ScopeKind.FREE else [],
        imported_names=[name] if kind == ScopeKind.IMPORTED else [],
        symbols=[entry],
        is_closure=False,
    )


def _index_child_scopes(
    scope: symtable.SymbolTable,
) -> dict[str, list[tuple[int, symtable.SymbolTable]]]:
    """Index child scopes by name with lineno for disambiguation.

    Filters out __annotate__ scopes (Python 3.10+ synthetic annotation scopes).
    Note: Python 3.12+ may also emit TYPE_PARAMS scopes for PEP 695 type
    aliases; these are genuine child scopes and should NOT be filtered.
    """
    index: dict[str, list[tuple[int, symtable.SymbolTable]]] = {}
    for child in scope.get_children():
        name = child.get_name()
        if name == "__annotate__":
            continue
        index.setdefault(name, []).append((child.get_lineno(), child))
    return index


def _find_matching_scope(
    elem: Element,
    child_scope_index: dict[str, list[tuple[int, symtable.SymbolTable]]],
) -> Optional[symtable.SymbolTable]:
    """Find the matching child SymbolTable for a scope-creating element.

    Primary: match by (name, lineno).
    Fallback: source-order pop (first unused scope with matching name).
    """
    candidates = child_scope_index.get(elem.name)
    if not candidates:
        return None

    # Primary: match by (name, lineno).  Pop the matched entry to prevent
    # a second element with the same name from re-matching the same scope.
    for i, (lineno, scope) in enumerate(candidates):
        if lineno == elem.span.start_line:
            candidates.pop(i)
            return scope

    # Fallback: source-order pop — when lineno doesn't match (e.g., decorated
    # functions where AST lineno differs from symtable lineno), consume the
    # first remaining candidate to preserve one-to-one matching.
    logger.debug(
        "No exact lineno match for '%s' at line %d; falling back to source-order pop",
        elem.name,
        elem.span.start_line,
    )
    _, scope = candidates.pop(0)
    return scope


def _enrich_non_scope_element(
    elem: Element, parent_scope: symtable.SymbolTable,
) -> Element:
    """Enrich a non-scope element via symbol lookup in the parent scope."""
    try:
        sym = parent_scope.lookup(elem.name)
    except KeyError:
        logger.debug(
            "Symbol '%s' not found in scope '%s'; skipping enrichment",
            elem.name,
            parent_scope.get_name(),
        )
        return elem
    return elem.model_copy(update={"symbol_info": _build_single_symbol_info(sym)})


def _enrich_elements(
    elements: list[Element],
    scope: symtable.SymbolTable,
) -> list[Element]:
    """Recursively enrich a list of elements from a symtable scope.

    Uses bottom-up traversal: children are enriched before their parent so that
    the parent's ``model_copy(update=...)`` call only happens once (Pydantic
    frozen models are immutable, so each copy is O(fields)).
    """
    child_scope_index = _index_child_scopes(scope)
    enriched: list[Element] = []

    for elem in elements:
        try:
            if elem.kind in _SCOPE_ELEMENT_KINDS:
                matched = _find_matching_scope(elem, child_scope_index)
                if matched is None:
                    logger.debug(
                        "No matching symtable scope for %s '%s' at line %d",
                        elem.kind.value,
                        elem.name,
                        elem.span.start_line,
                    )
                    enriched.append(elem)
                    continue

                # Bottom-up: enrich children first, then rebuild parent
                enriched_children = (
                    _enrich_elements(elem.children, matched)
                    if elem.children
                    else elem.children
                )
                enriched_class_vars = (
                    [_enrich_non_scope_element(cv, matched) for cv in elem.class_variables]
                    if elem.class_variables
                    else elem.class_variables
                )

                symbol_info = _build_symbol_info(matched)
                enriched.append(
                    elem.model_copy(
                        update={
                            "symbol_info": symbol_info,
                            "children": enriched_children,
                            "class_variables": enriched_class_vars,
                        }
                    )
                )
            else:
                enriched.append(_enrich_non_scope_element(elem, scope))
        except Exception:
            logger.warning(
                "Failed to enrich %s '%s' at line %d; using unenriched element",
                elem.kind.value,
                elem.name,
                elem.span.start_line,
                exc_info=True,
            )
            enriched.append(elem)

    return enriched


def _augment_with_symtable(
    source: str,
    filename: str,
    elements: list[Element],
) -> list[Element]:
    """Augment elements with symtable scope and binding information.

    Catches any exception defensively — symtable failures should never
    crash manifest generation. Returns unenriched elements on failure.
    """
    try:
        table = symtable.symtable(source, filename, "exec")
    except SyntaxError:
        logger.warning(
            "symtable.symtable() failed on %s; returning unenriched manifest",
            filename,
            exc_info=True,
        )
        return elements
    except Exception:
        logger.error(
            "Unexpected error in symtable.symtable() on %s; returning unenriched manifest",
            filename,
            exc_info=True,
        )
        return elements

    return _enrich_elements(elements, table)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5: inspect-based runtime introspection
# ═══════════════════════════════════════════════════════════════════════════

_GUARDED_IMPORT_TIMEOUT = 10  # seconds


@contextmanager
def _guarded_import(
    module_path: str,
    project_root: Path,
    file_path: Path,
) -> Generator[Optional[types.ModuleType], None, None]:
    """Import a module in-process with isolation and a timeout guard.

    Saves and restores ``sys.path`` and ``sys.modules`` to prevent
    side-effects from leaking. Uses a daemon thread with a timeout
    to guard against modules that hang during import.

    Yields the imported module on success, ``None`` on failure.
    """
    saved_path = sys.path[:]
    saved_modules = set(sys.modules.keys())

    # Inject project paths so the target module's own imports resolve
    project_str = str(project_root)
    src_str = str(project_root / "src")
    for p in (src_str, project_str):
        if p not in sys.path:
            sys.path.insert(0, p)

    result: list[Optional[types.ModuleType]] = [None]
    error: list[Optional[Exception]] = [None]
    done = threading.Event()

    def _do_import() -> None:
        try:
            mod = importlib.import_module(module_path)
            result[0] = mod
        except Exception:
            # Fallback: spec_from_file_location for non-package files
            try:
                spec = importlib.util.spec_from_file_location(
                    module_path, str(file_path),
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # type: ignore[union-attr]
                    result[0] = mod
                else:
                    error[0] = ImportError(
                        f"Cannot create spec for {module_path}"
                    )
            except Exception as exc2:
                error[0] = exc2
        finally:
            done.set()

    thread = threading.Thread(target=_do_import, daemon=True)
    thread.start()

    try:
        if not done.wait(timeout=_GUARDED_IMPORT_TIMEOUT):
            logger.warning(
                "Import of %s timed out after %ds",
                module_path,
                _GUARDED_IMPORT_TIMEOUT,
            )
            yield None
            return

        if result[0] is not None:
            yield result[0]
        else:
            if error[0] is not None:
                logger.debug(
                    "Failed to import %s: %s", module_path, error[0],
                )
            yield None
    finally:
        # Restore sys.path
        sys.path[:] = saved_path
        # Remove any modules added during import
        new_modules = set(sys.modules.keys()) - saved_modules
        for mod_name in new_modules:
            sys.modules.pop(mod_name, None)


_INSPECT_PARAM_KIND_MAP: dict[inspect._ParameterKind, ParamKind] = {
    inspect.Parameter.POSITIONAL_ONLY: ParamKind.POSITIONAL_ONLY,
    inspect.Parameter.POSITIONAL_OR_KEYWORD: ParamKind.POSITIONAL,
    inspect.Parameter.VAR_POSITIONAL: ParamKind.VAR_POSITIONAL,
    inspect.Parameter.KEYWORD_ONLY: ParamKind.KEYWORD_ONLY,
    inspect.Parameter.VAR_KEYWORD: ParamKind.VAR_KEYWORD,
}


def _inspect_param_kind(kind: inspect._ParameterKind) -> ParamKind:
    """Map ``inspect.Parameter.kind`` to ``ParamKind``."""
    return _INSPECT_PARAM_KIND_MAP.get(kind, ParamKind.POSITIONAL)


def _format_type(tp: Any) -> str:
    """Convert a type object to its string representation."""
    if tp is type(None):
        return "None"
    module = getattr(tp, "__module__", None)
    qualname = getattr(tp, "__qualname__", None)
    if qualname and module:
        if module == "builtins":
            return qualname
        return f"{module}.{qualname}"
    return str(tp)


def _introspect_signature(obj: Any) -> Optional[ResolvedSignature]:
    """Extract a ``ResolvedSignature`` from a live callable.

    Uses ``inspect.signature()`` for parameters and return annotation,
    merged with ``typing.get_type_hints()`` for fully-resolved annotations.
    Returns ``None`` if the signature cannot be determined.
    """
    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError):
        return None

    # Try to get resolved type hints (handles forward refs)
    try:
        hints = typing.get_type_hints(obj)
    except Exception:
        hints = {}

    params: list[ResolvedParam] = []
    for name, param in sig.parameters.items():
        annotation: Optional[str] = None
        if name in hints:
            annotation = _format_type(hints[name])
        elif param.annotation is not inspect.Parameter.empty:
            annotation = str(param.annotation)

        default: Optional[str] = None
        has_default = param.default is not inspect.Parameter.empty
        if has_default:
            default_repr = repr(param.default)
            if len(default_repr) > _VALUE_REPR_ABSOLUTE_MAX:
                default_repr = default_repr[:_VALUE_REPR_ABSOLUTE_MAX] + "..."
            default = default_repr

        params.append(ResolvedParam(
            name=name,
            annotation=annotation,
            default=default,
            kind=_inspect_param_kind(param.kind),
            has_default=has_default,
        ))

    return_annotation: Optional[str] = None
    if "return" in hints:
        return_annotation = _format_type(hints["return"])
    elif sig.return_annotation is not inspect.Signature.empty:
        return_annotation = str(sig.return_annotation)

    return ResolvedSignature(
        params=params,
        return_annotation=return_annotation,
    )


def _introspect_element(
    obj: Any,
    elem: Element,
    parent_obj: Any = None,
) -> InspectInfo:
    """Build an ``InspectInfo`` for a single live object.

    For classes: extracts MRO, runtime attributes (diff against AST children),
    and the ``__init__`` signature.
    For callables: extracts resolved signature and type hints.
    For variables: checks callable status and qualname.
    """
    mro: list[str] = []
    resolved_annotations: dict[str, str] = {}
    runtime_attributes: list[str] = []
    resolved_signature: Optional[ResolvedSignature] = None
    qualname: Optional[str] = getattr(obj, "__qualname__", None)
    is_callable_flag = callable(obj)

    if inspect.isclass(obj):
        # MRO — sorted for determinism (excluding object and the class itself)
        try:
            raw_mro = inspect.getmro(obj)
            mro = sorted(
                _format_type(c)
                for c in raw_mro
                if c is not obj and c is not object
            )
        except Exception:
            pass

        # Runtime attributes — diff against AST children
        try:
            ast_names = {c.name for c in elem.children}
            ast_names.update(cv.name for cv in elem.class_variables)
            members = inspect.getmembers(obj)
            runtime_attributes = sorted(
                name
                for name, _ in members
                if name not in ast_names and not name.startswith("__")
            )
        except Exception:
            pass

        # Class signature reflects __init__
        resolved_signature = _introspect_signature(obj)

        # Resolved annotations
        try:
            hints = typing.get_type_hints(obj)
            resolved_annotations = {
                k: _format_type(v) for k, v in sorted(hints.items())
            }
        except Exception:
            pass

    elif callable(obj):
        resolved_signature = _introspect_signature(obj)

        # Resolved annotations
        try:
            hints = typing.get_type_hints(obj)
            resolved_annotations = {
                k: _format_type(v) for k, v in sorted(hints.items())
            }
        except Exception:
            pass

    return InspectInfo(
        resolved_signature=resolved_signature,
        mro=mro,
        resolved_annotations=resolved_annotations,
        runtime_attributes=runtime_attributes,
        is_callable=is_callable_flag,
        qualname=qualname,
    )


def _resolve_runtime_object(
    elem: Element,
    module: types.ModuleType,
    parent_obj: Any = None,
) -> Optional[Any]:
    """Map an Element to its live object via ``getattr()``.

    Handles property triads, overloaded methods, and nested functions.
    Returns ``None`` when the object cannot be resolved at runtime.
    """
    # Skip overload variants — not individually resolvable
    if elem.overload_index is not None:
        return None

    name = elem.name

    # For children of a class, look up on the class object
    target = parent_obj if parent_obj is not None else module

    # Property triads: extract fget/fset/fdel based on FQN suffix
    if elem.kind == ElementKind.PROPERTY and parent_obj is not None:
        prop = getattr(parent_obj, name, None)
        if isinstance(prop, property):
            if elem.fqn.endswith(".getter") or not elem.fqn.endswith(
                (".setter", ".deleter")
            ):
                return prop.fget
            elif elem.fqn.endswith(".setter"):
                return prop.fset
            elif elem.fqn.endswith(".deleter"):
                return prop.fdel
        return prop

    obj = getattr(target, name, None)
    if obj is None and parent_obj is None:
        # Nested functions are not resolvable at module level
        return None

    return obj


def _enrich_with_inspect(
    elements: list[Element],
    module: types.ModuleType,
    parent_obj: Any = None,
) -> list[Element]:
    """Recursively enrich elements with runtime introspection data.

    Bottom-up traversal: children are enriched before parents.
    Per-element try/except ensures one failure doesn't block siblings.
    """
    enriched: list[Element] = []

    for elem in elements:
        try:
            obj = _resolve_runtime_object(elem, module, parent_obj)

            # Enrich children first (bottom-up)
            enriched_children = elem.children
            enriched_class_vars = elem.class_variables
            if obj is not None and elem.kind == ElementKind.CLASS:
                enriched_children = _enrich_with_inspect(
                    elem.children, module, parent_obj=obj,
                )
                # Class variables get minimal InspectInfo
                enriched_class_vars = []
                for cv in elem.class_variables:
                    try:
                        cv_obj = getattr(obj, cv.name, None)
                        cv_info = InspectInfo(
                            is_callable=callable(cv_obj) if cv_obj is not None else False,
                            qualname=getattr(cv_obj, "__qualname__", None),
                        )
                        enriched_class_vars.append(
                            cv.model_copy(update={"inspect_info": cv_info})
                        )
                    except Exception:
                        enriched_class_vars.append(cv)
            elif elem.children:
                enriched_children = _enrich_with_inspect(
                    elem.children, module, parent_obj=parent_obj,
                )

            if obj is not None:
                info = _introspect_element(obj, elem, parent_obj)
                enriched.append(
                    elem.model_copy(
                        update={
                            "inspect_info": info,
                            "children": enriched_children,
                            "class_variables": enriched_class_vars,
                        }
                    )
                )
            else:
                enriched.append(
                    elem.model_copy(
                        update={
                            "children": enriched_children,
                            "class_variables": enriched_class_vars,
                        }
                    )
                )
        except Exception:
            logger.warning(
                "Failed to introspect %s '%s'; using unenriched element",
                elem.kind.value,
                elem.name,
                exc_info=True,
            )
            enriched.append(elem)

    return enriched


def _augment_with_inspect(
    module_path: str,
    project_root: Path,
    file_path: Path,
    elements: list[Element],
    errors: list[ParseError],
) -> tuple[list[Element], list[ParseError], Optional[list[str]], Optional[str]]:
    """Top-level entry point for runtime introspection enrichment.

    Mirrors ``_augment_with_symtable()`` defensive pattern: catches any
    ``Exception`` and returns unenriched elements on failure.

    Returns:
        (elements, errors, module_all, module_version)
    """
    module_all: Optional[list[str]] = None
    module_version: Optional[str] = None

    try:
        with _guarded_import(module_path, project_root, file_path) as mod:
            if mod is None:
                errors = errors + [
                    ParseError(
                        kind=ParseErrorKind.IMPORT_ERROR,
                        message=f"Failed to import {module_path} for introspection",
                    )
                ]
                return elements, errors, module_all, module_version

            # Extract module-level metadata
            raw_all = getattr(mod, "__all__", None)
            if isinstance(raw_all, (list, tuple)):
                module_all = sorted(str(x) for x in raw_all)

            raw_version = getattr(mod, "__version__", None)
            if isinstance(raw_version, str):
                module_version = raw_version

            # Enrich elements
            elements = _enrich_with_inspect(elements, mod)

    except Exception:
        logger.error(
            "Unexpected error during introspection of %s; returning unenriched",
            module_path,
            exc_info=True,
        )
        return elements, errors, module_all, module_version

    return elements, errors, module_all, module_version


# Valid analysis modes
_VALID_MODES = frozenset({"ast_only", "static", "introspect", "bytecode"})


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def generate_file_manifest(
    file_path: Union[Path, str],
    project_root: Union[Path, str],
    source: Optional[str] = None,
    mode: str = "static",
) -> FileManifest:
    """
    Generate a manifest for a single Python file.

    Args:
        file_path: Absolute or relative path to the Python file.
        project_root: Project root directory (for FQN computation).
        source: Optional pre-read source code. If None, reads from file_path.
        mode: Analysis depth — ``"static"`` (default) includes symtable
            augmentation; ``"ast_only"`` skips symtable for faster AST-only
            analysis; ``"introspect"`` adds runtime introspection via
            ``inspect`` module (resolves forward refs, MRO, runtime attrs);
            ``"bytecode"`` adds call graph extraction via ``dis`` module
            (CPython 3.12+ only). ``"full"`` raises ``NotImplementedError``.

    Returns:
        FileManifest with all structural elements, imports, and dependencies.
        On parse errors, returns a manifest with empty elements and populated errors.
    """
    if mode == "full":
        raise NotImplementedError(
            "Mode 'full' requires combined introspect + bytecode implementation"
        )
    if mode not in _VALID_MODES:
        raise ValueError(f"Unknown mode: '{mode}'")

    file_path = Path(file_path)
    project_root = Path(project_root)
    errors: list[ParseError] = []

    # Read source if not provided
    if source is None:
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            raise
        except OSError as exc:
            return FileManifest(
                file=str(file_path.relative_to(project_root)),
                module=_compute_module_path(file_path, project_root),
                digest="sha256:" + hashlib.sha256(b"").hexdigest(),
                errors=[
                    ParseError(
                        kind=ParseErrorKind.IO_ERROR,
                        message=str(exc),
                    )
                ],
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

    digest = _compute_digest(source)
    try:
        relative_path = str(file_path.relative_to(project_root))
    except ValueError:
        relative_path = str(file_path)
    module_path = _compute_module_path(file_path, project_root)

    # Parse AST
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        return FileManifest(
            file=relative_path,
            module=module_path,
            digest=digest,
            errors=[
                ParseError(
                    kind=ParseErrorKind.SYNTAX_ERROR,
                    message=str(exc.msg) if exc.msg else str(exc),
                    line=exc.lineno,
                    col=exc.offset,
                )
            ],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # Annotate parents for scope_guard detection
    _annotate_parents(tree)

    # Detect python version
    python_version = _detect_python_version(tree)

    # Extract __all__ for re-export detection
    all_names = _extract_all_names(tree)

    # Derive project module from project root (first-match: assumes single package under src/)
    project_module = ""
    try:
        src_dir = project_root / "src"
        if src_dir.is_dir():
            for child in src_dir.iterdir():
                if child.is_dir() and (child / "__init__.py").exists():
                    project_module = child.name
                    break
    except OSError:
        pass

    # Pre-scan for branch disambiguation
    branch_names = _scan_branch_names(tree.body)

    # Visit AST
    is_init = file_path.name == "__init__.py"
    visitor = _ManifestVisitor(
        module_path, module_path, all_names,
        is_init_file=is_init,
        branch_names=branch_names,
    )
    visitor.visit(tree)

    # Classify dependencies
    dependencies = _classify_imports(
        visitor.imports,
        project_module=project_module,
        stdlib_set=_STDLIB_MODULES,
    )

    # Phase 3: symtable augmentation (mode="static", "bytecode", or "introspect")
    elements = visitor.elements
    if mode in ("static", "bytecode", "introspect") and not errors:
        elements = _augment_with_symtable(source, str(file_path), elements)

    # Phase 5: inspect-based runtime introspection (mode="introspect" only)
    module_all: Optional[list[str]] = None
    module_version: Optional[str] = None
    if mode == "introspect" and not errors:
        elements, errors, module_all, module_version = _augment_with_inspect(
            module_path, project_root, file_path, elements, errors,
        )

    # Phase 6: bytecode call graph (mode="bytecode" only)
    call_graph_edges: Optional[list[CallEdge]] = None
    if mode == "bytecode" and not errors:
        elements, call_graph_edges_list = _augment_with_bytecode(
            source, str(file_path), elements, module_path, visitor.imports,
        )
        call_graph_edges = call_graph_edges_list if call_graph_edges_list else None

    return FileManifest(
        schema_version=SCHEMA_VERSION,
        file=relative_path,
        module=module_path,
        digest=digest,
        python_version=python_version,
        elements=elements,
        imports=visitor.imports,
        dependencies=dependencies,
        errors=errors,
        generated_at=datetime.now(timezone.utc).isoformat(),
        module_all=module_all,
        module_version=module_version,
        call_graph_edges=call_graph_edges,
    )


def lookup_element(manifest: FileManifest, fqn: str) -> Optional[Element]:
    """
    Find an element in a manifest by fully-qualified name.

    Searches top-level elements and their children recursively.
    Returns None if not found.
    """

    def _search(elements: list[Element]) -> Optional[Element]:
        for elem in elements:
            if elem.fqn == fqn:
                return elem
            # Search children
            found = _search(elem.children)
            if found:
                return found
            # Search class_variables
            found = _search(elem.class_variables)
            if found:
                return found
        return None

    return _search(manifest.elements)
