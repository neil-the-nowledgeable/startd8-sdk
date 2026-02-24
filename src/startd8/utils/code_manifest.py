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
import hashlib
import symtable
import sys
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, model_validator

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Schema version — 1.2.0 = Phase 3 (symtable augmentation)
# Version 1.1.0 is reserved for Phase 2 (docstring/decorator enrichment).
SCHEMA_VERSION = "1.2.0"

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


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════

class ElementKind(str, Enum):
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    ASYNC_METHOD = "async_method"
    PROPERTY = "property"
    CONSTANT = "constant"
    VARIABLE = "variable"
    TYPE_ALIAS = "type_alias"


class Visibility(str, Enum):
    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"


class ParamKind(str, Enum):
    POSITIONAL = "positional"
    KEYWORD = "keyword"
    VAR_POSITIONAL = "var_positional"
    VAR_KEYWORD = "var_keyword"
    POSITIONAL_ONLY = "positional_only"
    KEYWORD_ONLY = "keyword_only"


class ParseErrorKind(str, Enum):
    SYNTAX_ERROR = "syntax_error"
    ENCODING_ERROR = "encoding_error"
    IO_ERROR = "io_error"
    PARTIAL_PARSE = "partial_parse"


class ScopeKind(str, Enum):
    """Variable scope classification from symtable analysis.

    Classification priority (first match wins):
    1. parameter — is_parameter()
    2. imported  — is_imported()
    3. nonlocal  — is_nonlocal() (explicit declaration, also has is_free()=True)
    4. free      — is_free() (implicit closure capture without nonlocal keyword)
    5. global    — is_global()
    6. local     — fallback
    """

    LOCAL = "local"
    GLOBAL = "global"
    NONLOCAL = "nonlocal"
    FREE = "free"
    IMPORTED = "imported"
    PARAMETER = "parameter"


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════

class Span(BaseModel):
    """Source location of a code element."""

    model_config = ConfigDict(frozen=True)

    start_line: int
    start_col: int
    end_line: int
    end_col: int


class Param(BaseModel):
    """A function/method parameter."""

    model_config = ConfigDict(frozen=True)

    name: str
    annotation: Optional[str] = None
    default: Optional[str] = None
    kind: ParamKind = ParamKind.POSITIONAL


class Signature(BaseModel):
    """Callable signature."""

    model_config = ConfigDict(frozen=True)

    params: list[Param]
    return_annotation: Optional[str] = None


class Element(BaseModel):
    """A structural code element (class, function, variable, etc.)."""

    model_config = ConfigDict(frozen=True)

    kind: ElementKind
    name: str
    fqn: str
    span: Span
    docstring: Optional[str] = None
    decorators: list[str] = []
    children: list[Element] = []
    scope_guard: Optional[str] = None

    # Callable fields (function/method)
    signature: Optional[Signature] = None
    is_static: bool = False
    is_classmethod: bool = False
    is_abstract: bool = False
    visibility: Visibility = Visibility.PUBLIC
    overload_index: Optional[int] = None

    # Class fields
    bases: list[str] = []
    metaclass: Optional[str] = None
    tags: list[str] = []
    class_variables: list[Element] = []

    # Assignment fields (constant/variable)
    type_annotation: Optional[str] = None
    value_repr: Optional[str] = None

    # Phase 3: symtable augmentation
    symbol_info: Optional[SymbolInfo] = None

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> Element:
        """Enforce field-presence invariants based on element kind."""
        callable_kinds = {
            ElementKind.FUNCTION,
            ElementKind.ASYNC_FUNCTION,
            ElementKind.METHOD,
            ElementKind.ASYNC_METHOD,
            ElementKind.PROPERTY,
        }
        class_kinds = {ElementKind.CLASS}

        if self.kind in callable_kinds and self.signature is None:
            raise ValueError(
                f"Element of kind '{self.kind.value}' must have a signature"
            )
        if self.kind not in class_kinds and self.bases:
            raise ValueError(
                f"Element of kind '{self.kind.value}' must not have bases"
            )
        return self


class ImportEntry(BaseModel):
    """An import statement."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["import", "from"]
    module: str
    names: list[str] = []
    alias: Optional[str] = None
    span: Span
    is_relative: bool = False
    is_conditional: bool = False
    is_reexport: bool = False


class Dependencies(BaseModel):
    """Classified dependency summary."""

    model_config = ConfigDict(frozen=True)

    internal: list[str] = []
    external: list[str] = []
    stdlib: list[str] = []
    conditional: list[str] = []


class ParseError(BaseModel):
    """An error encountered during manifest generation."""

    model_config = ConfigDict(frozen=True)

    kind: ParseErrorKind
    message: str
    line: Optional[int] = None
    col: Optional[int] = None


class SymbolEntry(BaseModel):
    """Per-symbol scope and binding detail from symtable analysis."""

    model_config = ConfigDict(frozen=True)

    name: str
    scope: ScopeKind
    is_referenced: bool = False
    is_assigned: bool = False
    is_parameter: bool = False


class SymbolInfo(BaseModel):
    """Scope-level symbol table summary attached to each manifest Element.

    For scope-creating elements (functions, classes, methods), contains all
    symbols visible in that scope. For non-scope elements (variables, constants),
    contains a single-entry symbols list from parent scope lookup.
    """

    model_config = ConfigDict(frozen=True)

    local_vars: list[str] = []
    global_vars: list[str] = []
    nonlocal_vars: list[str] = []
    free_vars: list[str] = []
    imported_names: list[str] = []
    symbols: list[SymbolEntry] = []
    is_closure: bool = False


class FileManifest(BaseModel):
    """Complete manifest for a single Python file."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = SCHEMA_VERSION
    file: str
    module: str
    digest: str
    python_version: str = "3.9"
    elements: list[Element] = []
    imports: list[ImportEntry] = []
    dependencies: Dependencies = Dependencies()
    errors: list[ParseError] = []
    generated_at: str = ""

    def to_yaml(self) -> str:
        """Serialize the manifest to YAML format."""
        import yaml
        return yaml.dump(
            self.model_dump(mode="json"),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


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
            analysis. Other modes raise ``NotImplementedError``.

    Returns:
        FileManifest with all structural elements, imports, and dependencies.
        On parse errors, returns a manifest with empty elements and populated errors.
    """
    if mode not in ("static", "ast_only"):
        raise NotImplementedError(f"Mode '{mode}' requires Phase 5+ implementation")

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

    # Phase 3: symtable augmentation (mode="static" only, skip on parse errors)
    elements = visitor.elements
    if mode == "static" and not errors:
        elements = _augment_with_symtable(source, str(file_path), elements)

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
