"""
Forward-Looking Code Manifest (FLCM) — Pydantic v2 schema models.

Defines the contract-first manifest that captures design-time constraints
(naming, API surface, config keys, infrastructure) BEFORE code generation.
The IMPLEMENT phase consumes these contracts as binding constraints.

See docs/design/forward-manifest/04_FORWARD_MANIFEST.md for the full spec.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from startd8.logging_config import get_logger
from startd8.utils.code_manifest import (
    Dependencies,
    Element,
    ElementKind,
    ImportEntry,
    Signature,
    Span,
    Visibility,
)

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════


class ContractCategory(str, Enum):
    """Classification of interface contracts."""

    FUNCTION_NAME = "function_name"
    CLASS_NAME = "class_name"
    API_ENDPOINT = "api_endpoint"
    CONFIG_KEY = "config_key"
    IMPORT_PATH = "import_path"
    FORMULA = "formula"
    RENDER_PATTERN = "render_pattern"
    INFRASTRUCTURE = "infrastructure"


class ContractConfidence(str, Enum):
    """Confidence level for a contract constraint."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    TENTATIVE = "tentative"


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════


class InterfaceContract(BaseModel):
    """A single design-time constraint that code generation must honor.

    Captures a named, categorized constraint extracted from design documents.
    Each contract carries a ``binding_text`` string that is injected verbatim
    into the IMPLEMENT phase prompt so the LLM treats it as an invariant.

    Attributes:
        contract_id: Unique identifier for this contract.
        category: Classification (function name, class name, endpoint, etc.).
        confidence: How strongly the constraint is supported by the design.
        description: Human-readable description of the constraint.
        binding_text: Compact directive string injected into LLM prompts.
        applicable_task_ids: Task IDs this contract applies to (empty = all).
        source_reference: Optional reference to the originating design section.
    """

    model_config = ConfigDict(frozen=True)

    # Required fields
    contract_id: str
    category: ContractCategory
    confidence: ContractConfidence
    description: str
    binding_text: str

    # Category-specific optional fields
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    base_class: Optional[str] = None
    endpoint: Optional[str] = None
    request_schema: Optional[dict] = None
    response_schema: Optional[dict] = None
    env_var: Optional[str] = None
    import_path: Optional[str] = None
    formula: Optional[str] = None
    constant_value: Optional[str] = None
    pattern: Optional[str] = None
    dependency: Optional[str] = None

    # Scoping
    applicable_task_ids: list[str] = Field(default_factory=list)
    source_reference: Optional[str] = None


class ForwardElementSpec(BaseModel):
    """Forward-looking element specification that bridges to code_manifest.Element.

    Represents a single code element (function, class, method, property) that
    the design phase expects to exist after code generation.  Validated via
    ``_validate_kind_fields`` to enforce invariants (e.g., callables must have
    a signature, only classes may have bases).

    Attributes:
        kind: Element kind (function, class, method, etc.).
        name: Element name as it should appear in source.
        signature: Required for callable kinds; ``None`` for classes/constants.
        bases: Base classes (only valid for ``CLASS`` kind).
        visibility: Public or private visibility.
        decorators: Expected decorator names.
        docstring_hint: Suggested docstring content for the element.
        parent_class: Owning class name for methods and properties.
        source_contract_id: ID of the InterfaceContract that produced this spec.
    """

    model_config = ConfigDict(frozen=True)

    kind: ElementKind
    name: str
    signature: Optional[Signature] = None
    bases: list[str] = Field(default_factory=list)
    visibility: Visibility = Visibility.PUBLIC
    decorators: list[str] = Field(default_factory=list)
    docstring_hint: Optional[str] = None
    parent_class: Optional[str] = None
    source_contract_id: Optional[str] = None

    @field_validator("parent_class", mode="before")
    @classmethod
    def _normalize_parent_class(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> ForwardElementSpec:
        """Mirror Element._validate_kind_fields — catch invariant violations early."""
        callable_kinds = {
            ElementKind.FUNCTION,
            ElementKind.ASYNC_FUNCTION,
            ElementKind.METHOD,
            ElementKind.ASYNC_METHOD,
            ElementKind.PROPERTY,
        }
        class_kinds = {ElementKind.CLASS}
        method_kinds = {
            ElementKind.METHOD,
            ElementKind.ASYNC_METHOD,
            ElementKind.PROPERTY,
            ElementKind.CONSTANT,
            ElementKind.VARIABLE,
        }

        if self.kind in callable_kinds and self.signature is None:
            raise ValueError(
                f"ForwardElementSpec of kind '{self.kind.value}' must have a signature"
            )
        if self.kind not in class_kinds and self.bases:
            raise ValueError(
                f"ForwardElementSpec of kind '{self.kind.value}' must not have bases"
            )
        if self.parent_class is not None and self.kind not in method_kinds:
            raise ValueError(
                f"ForwardElementSpec with parent_class must be METHOD, "
                f"ASYNC_METHOD, PROPERTY, CONSTANT, or VARIABLE, got '{self.kind.value}'"
            )
        if self.parent_class is not None and self.parent_class.count(".") > 1:
            raise ValueError(
                f"ForwardElementSpec parent_class has too many nesting levels: "
                f"'{self.parent_class}' — maximum 2-level nesting allowed "
                f"(e.g., 'Outer.Inner')"
            )
        return self

    def to_element(self) -> Element:
        """Bridge to code_manifest.Element with sentinel span."""
        return Element(
            kind=self.kind,
            name=self.name,
            fqn=f"{self.parent_class}.{self.name}" if self.parent_class else self.name,
            span=Span(start_line=0, start_col=0, end_line=0, end_col=0),  # Sentinel: forward specs have no source location
            signature=self.signature,
            bases=list(self.bases),
            visibility=self.visibility,
            decorators=list(self.decorators),
            docstring=self.docstring_hint,
        )


class ForwardImportSpec(BaseModel):
    """Forward-looking import specification.

    Models a single import statement expected in generated code, covering
    both ``import module`` and ``from module import name`` forms.

    Attributes:
        kind: Import style -- ``"import"`` or ``"from"``.
        module: Module path to import from.
        names: Specific names imported (for ``from`` imports).
        alias: Optional alias (``as`` clause).
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["import", "from"]
    module: str
    names: list[str] = Field(default_factory=list)
    alias: Optional[str] = None


class ForwardDependencies(BaseModel):
    """Simplified forward-looking dependency listing.

    Tracks the external (PyPI) and stdlib packages a generated file is
    expected to depend on, enabling pre-generation validation of the
    project's dependency set.

    Attributes:
        external: Third-party package names (e.g., ``["pydantic", "httpx"]``).
        stdlib: Standard library module names (e.g., ``["json", "pathlib"]``).
    """

    model_config = ConfigDict(frozen=True)

    external: list[str] = Field(default_factory=list)
    stdlib: list[str] = Field(default_factory=list)


class ForwardFileSpec(BaseModel):
    """Forward-looking file specification with elements, imports, and dependencies.

    Groups the expected code elements, import statements, and package
    dependencies for a single source file.  Used by the IMPLEMENT phase
    to validate that generated code matches the design contract.

    Attributes:
        file: Relative file path within the project.
        elements: Expected code elements (classes, functions, methods).
        imports: Expected import statements.
        dependencies: External and stdlib package dependencies.
    """

    model_config = ConfigDict(frozen=True)

    file: str
    elements: list[ForwardElementSpec] = Field(default_factory=list)
    imports: list[ForwardImportSpec] = Field(default_factory=list)
    dependencies: Optional[ForwardDependencies] = None


class ForwardManifest(BaseModel):
    """Top-level forward-looking code manifest -- mutable during pipeline stages.

    Aggregates all interface contracts and per-file element specifications
    produced by the DESIGN phase.  The IMPLEMENT phase consumes this manifest
    as binding constraints, and ``stages_completed`` tracks which pipeline
    stages have enriched it.

    Attributes:
        schema_version: Manifest schema version (currently ``"1.0.0"``).
        pipeline_run_id: ID of the pipeline run that produced the manifest.
        generated_at: ISO-8601 timestamp of manifest creation.
        source_checksum: Checksum of the source design document.
        contracts: Interface contracts extracted from the design.
        file_specs: Per-file element and import specifications.
        stages_completed: Pipeline stages that have enriched this manifest.
    """

    schema_version: str = "1.0.0"
    pipeline_run_id: Optional[str] = None
    generated_at: Optional[str] = None
    source_checksum: Optional[str] = None

    contracts: list[InterfaceContract] = Field(default_factory=list)
    file_specs: dict[str, ForwardFileSpec] = Field(default_factory=dict)
    stages_completed: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    def contracts_for_task(self, task_id: str) -> list[InterfaceContract]:
        """Return project-wide contracts plus those specific to *task_id*."""
        return [
            c
            for c in self.contracts
            if not c.applicable_task_ids or task_id in c.applicable_task_ids
        ]

    def binding_constraints_for_task(self, task_id: str) -> list[str]:
        """Return binding_text strings for all contracts applicable to *task_id*."""
        return [c.binding_text for c in self.contracts_for_task(task_id)]

    def file_specs_for_task(
        self, task_id: str, target_files: list[str]
    ) -> dict[str, ForwardFileSpec]:
        """Return file specs whose path appears in *target_files*."""
        return {
            path: spec
            for path, spec in self.file_specs.items()
            if path in target_files
        }

    def contract_count_by_category(self) -> Counter:
        """Return a Counter of contracts grouped by category."""
        return Counter(c.category for c in self.contracts)


# ═══════════════════════════════════════════════════════════════════════════
# ContractViolation (plain dataclass, not Pydantic)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ContractViolation:
    """A detected violation of an interface contract.

    Produced by post-generation validation when generated code does not
    satisfy a binding constraint from the manifest.

    Attributes:
        contract_id: ID of the violated InterfaceContract.
        violation_type: Category of the violation (e.g., missing element).
        expected: What the contract required.
        actual: What was found in generated code (``None`` if absent).
        file_path: File where the violation was detected.
        severity: Severity level (default ``"error"``).
    """

    contract_id: str
    violation_type: str
    expected: str
    actual: Optional[str] = None
    file_path: Optional[str] = None
    severity: str = "error"

    def __post_init__(self) -> None:
        if not self.contract_id or not isinstance(self.contract_id, str):
            raise ValueError(
                "ContractViolation contract_id must be a non-empty string"
            )
        if not self.violation_type or not isinstance(self.violation_type, str):
            raise ValueError(
                "ContractViolation violation_type must be a non-empty string"
            )
        _VALID_SEVERITIES = {"error", "warning", "info"}
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"ContractViolation severity must be one of {_VALID_SEVERITIES}, "
                f"got {self.severity!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════


def compute_binding_text(contract: InterfaceContract) -> str:
    """Compute a compact binding-text string from an InterfaceContract.

    Returns a ``[BINDING]`` or ``[ADVISORY]`` prefixed string with
    category-specific fields joined by `` | ``.
    """
    prefix = (
        "[BINDING]"
        if contract.confidence in (ContractConfidence.EXPLICIT, ContractConfidence.INFERRED)
        else "[ADVISORY]"
    )

    parts: list[str] = [prefix]

    cat = contract.category
    if cat == ContractCategory.FUNCTION_NAME and contract.function_name:
        parts.append(f"function={contract.function_name}")
    elif cat == ContractCategory.CLASS_NAME and contract.class_name:
        parts.append(f"class={contract.class_name}")
        if contract.base_class:
            parts.append(f"base={contract.base_class}")
    elif cat == ContractCategory.API_ENDPOINT and contract.endpoint:
        parts.append(f"endpoint={contract.endpoint}")
    elif cat == ContractCategory.CONFIG_KEY and contract.env_var:
        parts.append(f"env_var={contract.env_var}")
    elif cat == ContractCategory.IMPORT_PATH and contract.import_path:
        parts.append(f"import_path={contract.import_path}")
    elif cat == ContractCategory.FORMULA and contract.formula:
        parts.append(f"formula={contract.formula}")
        if contract.constant_value:
            parts.append(f"value={contract.constant_value}")
    elif cat == ContractCategory.RENDER_PATTERN and contract.pattern:
        parts.append(f"pattern={contract.pattern}")
    elif cat == ContractCategory.INFRASTRUCTURE and contract.dependency:
        parts.append(f"dependency={contract.dependency}")

    parts.append(contract.description)
    return " | ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Conversion functions (AST Element/ImportEntry/Dependencies → Forward specs)
# ═══════════════════════════════════════════════════════════════════════════


def forward_element_spec_from_element(
    element: Element,
    source_contract_id: Optional[str] = None,
) -> ForwardElementSpec:
    """Convert an AST ``Element`` to a ``ForwardElementSpec``.

    Skips CONSTANT/VARIABLE kinds (no signature for callables).
    Derives ``parent_class`` from ``element.fqn`` if dotted.

    Args:
        element: AST-derived element from ``code_manifest``.
        source_contract_id: Provenance ID. When ``None`` a rich ID is NOT
            set — callers should provide ``"flcm-ast-{relpath}:{line}:{fqn}"``.

    Returns:
        A validated ``ForwardElementSpec``.

    Raises:
        ValueError: If the element kind is CONSTANT or VARIABLE.
    """
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        raise ValueError(
            f"Cannot convert {element.kind.value} element '{element.name}' "
            "to ForwardElementSpec (no callable signature)"
        )

    # Derive parent_class only for method/property kinds.
    # For top-level elements, fqn includes module path (e.g. "app.main.func")
    # which is NOT a parent class. Only method-like elements nested in a class
    # should have parent_class set. The SourceReconciler overrides this for
    # class children, but we do a best-effort here: if the kind is METHOD-like
    # and the fqn contains a dot, use the last dotted component before the name.
    parent_class: Optional[str] = None
    method_kinds = {
        ElementKind.METHOD,
        ElementKind.ASYNC_METHOD,
        ElementKind.PROPERTY,
    }
    if element.kind in method_kinds and "." in element.fqn:
        # Extract just the immediate parent (class name), not the full module path
        # e.g. "app.main.MyClass.get_data" → "MyClass"
        parts = element.fqn.rsplit(".", 1)
        if parts[0]:
            # Take the last component of the prefix as the class name
            parent_class = parts[0].rsplit(".", 1)[-1]

    return ForwardElementSpec(
        kind=element.kind,
        name=element.name,
        signature=element.signature,
        bases=list(element.bases) if element.bases else [],
        visibility=element.visibility,
        decorators=list(element.decorators) if element.decorators else [],
        docstring_hint=element.docstring,
        parent_class=parent_class,
        source_contract_id=source_contract_id,
    )


def forward_import_spec_from_entry(
    entry: ImportEntry,
    project_root: Optional[Path] = None,
    file_path: Optional[Path] = None,
) -> Optional[ForwardImportSpec]:
    """Convert an AST ``ImportEntry`` to a ``ForwardImportSpec``.

    Relative imports (``is_relative=True``) are normalized to absolute module
    paths using ``project_root`` and ``file_path``. If normalization fails or
    the required paths are not provided, the import is dropped (returns ``None``).

    Args:
        entry: AST-derived import from ``code_manifest``.
        project_root: Project root for relative import resolution.
        file_path: Source file path for relative import resolution.

    Returns:
        A ``ForwardImportSpec`` or ``None`` if the import should be dropped.
    """
    module = entry.module

    if entry.is_relative:
        if project_root is None or file_path is None:
            return None
        try:
            project_root = Path(project_root)
            file_path = Path(file_path)
            # Compute package from file location.
            # Strip "src" directory since it's a common layout convention
            # (e.g., src/mypackage/utils.py → mypackage.utils) and is not
            # part of the Python package path.
            rel = file_path.parent.relative_to(project_root)
            package_parts = [p for p in rel.parts if p != "src"]
            if module:
                package_parts.append(module)
            module = ".".join(package_parts)
            if not module:
                return None
        except (ValueError, TypeError):
            return None

    return ForwardImportSpec(
        kind=entry.kind,
        module=module,
        names=list(entry.names) if entry.names else [],
        alias=entry.alias,
    )


def forward_dependencies_from_deps(deps: Dependencies) -> ForwardDependencies:
    """Convert AST ``Dependencies`` to ``ForwardDependencies``.

    Maps external and stdlib; drops internal and conditional.

    Args:
        deps: AST-derived dependency summary from ``code_manifest``.

    Returns:
        A ``ForwardDependencies`` with external and stdlib only.
    """
    return ForwardDependencies(
        external=list(deps.external) if deps.external else [],
        stdlib=list(deps.stdlib) if deps.stdlib else [],
    )


__all__ = [
    "ContractCategory",
    "ContractConfidence",
    "InterfaceContract",
    "ForwardElementSpec",
    "ForwardImportSpec",
    "ForwardDependencies",
    "ForwardFileSpec",
    "ForwardManifest",
    "ContractViolation",
    "compute_binding_text",
    "forward_element_spec_from_element",
    "forward_import_spec_from_entry",
    "forward_dependencies_from_deps",
]
