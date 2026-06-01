"""Data models for code manifests.

Extracted verbatim from ``code_manifest.py`` (Pass D). Pure pydantic models and
enums with no dependency on the parser/visitor logic. ``code_manifest`` re-exports
everything here (``from .code_manifest_models import *``) so existing import
paths (``from startd8.utils.code_manifest import Element``) keep working.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone  # noqa: F401  (annotation resolution)
from enum import Enum
from typing import Any, Generator, Literal, Optional, Union  # noqa: F401

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Schema version — 1.4.0 = Phase 5 (inspect-based runtime introspection)
# Version 1.1.0 is reserved for Phase 2 (docstring/decorator enrichment).
# Version 1.2.0 = Phase 3 (symtable augmentation).
# Version 1.3.0 = Phase 6 (bytecode call graph analysis).
SCHEMA_VERSION = "1.4.0"


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
    # Multi-language element kinds (MULTILANG_MANIFEST_VALIDATION FR-3): the native
    # kinds the per-language parsers (C#/Java/Go/Node) emit that Python's AST never
    # produces. Additive — existing values/serialization unchanged (NFR-2).
    INTERFACE = "interface"
    ENUM = "enum"
    STRUCT = "struct"
    RECORD = "record"
    FIELD = "field"
    DEFAULT_EXPORT = "default_export"  # JS/TS `export default <expr>` (FR-4)


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
    IMPORT_ERROR = "import_error"


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


class CallKind(str, Enum):
    """Classification of outbound calls extracted from bytecode."""

    FUNCTION_CALL = "function_call"
    METHOD_CALL = "method_call"
    BUILTIN_CALL = "builtin_call"
    DYNAMIC_CALL = "dynamic_call"


class AttributeAccessKind(str, Enum):
    """Classification of self-attribute access patterns."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"


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

    # Phase 5: inspect-based runtime introspection
    inspect_info: Optional[InspectInfo] = None

    # Phase 6: bytecode call graph
    call_graph: Optional[CallGraphInfo] = None

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


class ResolvedParam(BaseModel):
    """A resolved function parameter from runtime introspection."""

    model_config = ConfigDict(frozen=True)

    name: str
    annotation: Optional[str] = None
    default: Optional[str] = None
    kind: ParamKind = ParamKind.POSITIONAL
    has_default: bool = False


class ResolvedSignature(BaseModel):
    """Resolved callable signature from runtime introspection."""

    model_config = ConfigDict(frozen=True)

    params: list[ResolvedParam] = []
    return_annotation: Optional[str] = None


class InspectInfo(BaseModel):
    """Runtime introspection data from inspect module.

    Attached to elements when mode="introspect" is used.
    Provides resolved type annotations, MRO, and runtime attributes
    that cannot be determined from static analysis alone.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    resolved_signature: Optional[ResolvedSignature] = None
    class_mro: list[str] = Field(default=[], serialization_alias="mro", validation_alias="mro")
    resolved_annotations: dict[str, str] = {}
    runtime_attributes: list[str] = []
    is_callable: bool = False
    qualname: Optional[str] = None


class CallEntry(BaseModel):
    """A single outbound call from a callable element."""

    model_config = ConfigDict(frozen=True)

    target: str
    target_fqn: Optional[str] = None
    kind: CallKind
    receiver: Optional[str] = None
    line: Optional[int] = None


class AttributeAccess(BaseModel):
    """An attribute read/write/delete on self within a method."""

    model_config = ConfigDict(frozen=True)

    name: str
    access: AttributeAccessKind
    line: Optional[int] = None


class CallGraphInfo(BaseModel):
    """Per-element call graph summary derived from bytecode analysis."""

    model_config = ConfigDict(frozen=True)

    calls: list[CallEntry] = []
    attribute_reads: list[str] = []
    attribute_writes: list[str] = []
    has_dynamic_dispatch: bool = False
    unresolved_calls: list[str] = []


class CallEdge(BaseModel):
    """A single caller→callee edge in the project call graph."""

    model_config = ConfigDict(frozen=True)

    caller_fqn: str
    callee_fqn: str


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

    # Phase 5: module-level metadata from runtime introspection
    module_all: Optional[list[str]] = None
    module_version: Optional[str] = None

    # Phase 6: file-level call edges
    call_graph_edges: Optional[list[CallEdge]] = None
    # MULTILANG_MANIFEST_VALIDATION FR-5: confidence tier of the parse that produced
    # this manifest — "authoritative" (AST-grade: Python ast / C# tree-sitter / Java
    # javalang) or "advisory" (regex-grade, or an AST parser that fell back to regex).
    # Read by forward_manifest_validator to calibrate violation severity. None = unset,
    # treated as authoritative for the legacy Python path (backward-compatible).
    parser_tier: Optional[str] = None

    def to_yaml(self) -> str:
        """Serialize the manifest to YAML format."""
        import yaml
        return yaml.dump(
            self.model_dump(mode="json"),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
