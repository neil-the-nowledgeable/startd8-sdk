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

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

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

    Represents a single code element (function, class, method, property,
    constant, variable) that the design phase expects to exist after code
    generation.  Validated via ``_validate_kind_fields`` to enforce invariants
    (e.g., callables must have a signature, only classes may have bases).

    Attributes:
        kind: Element kind (function, class, method, constant, variable, etc.).
        name: Element name as it should appear in source.
        signature: Required for callable kinds; ``None`` for classes/constants.
        bases: Base classes (only valid for ``CLASS`` kind).
        visibility: Public or private visibility.
        decorators: Expected decorator names.
        docstring_hint: Suggested docstring content for the element.
        parent_class: Owning class name for methods and properties.
        source_contract_id: ID of the InterfaceContract that produced this spec.
        is_static: Whether the callable is a ``@staticmethod``.
        is_classmethod: Whether the callable is a ``@classmethod``.
        is_abstract: Whether the callable is abstract (``@abstractmethod``).
        type_annotation: Type annotation string for constants/variables.
        value_repr: Representative value for constants (e.g., ``"3.14"``).
        decomposition_source: Provenance tag from the decomposition phase.
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

    # Callable modifiers (bridged from Element)
    is_static: bool = False
    is_classmethod: bool = False
    is_abstract: bool = False

    # Assignment fields (for CONSTANT/VARIABLE kinds)
    type_annotation: Optional[str] = None
    value_repr: Optional[str] = None

    # Decomposition provenance (REQ: Phase 1, Step 8)
    decomposition_source: Optional[str] = None  # "simple", "moderate", "copy"

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
        """Bridge to code_manifest.Element with a sentinel zero-span.

        The returned ``Element`` uses ``Span(0, 0, 0, 0)`` because forward
        specs describe *expected* code that does not yet have a source
        location.  Callers that need a real span must update it after
        code generation.

        Returns:
            An ``Element`` populated from this spec's fields.
        """
        return Element(
            kind=self.kind,
            name=self.name,
            fqn=f"{self.parent_class}.{self.name}" if self.parent_class else self.name,
            span=Span(start_line=0, start_col=0, end_line=0, end_col=0),
            signature=self.signature,
            bases=list(self.bases),
            visibility=self.visibility,
            decorators=list(self.decorators),
            docstring=self.docstring_hint,
            is_static=self.is_static,
            is_classmethod=self.is_classmethod,
            is_abstract=self.is_abstract,
            type_annotation=self.type_annotation,
            value_repr=self.value_repr,
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


class ConventionProvenance(BaseModel):
    """Provenance for a ``ForwardFileSpec`` populated by the framework-conventions
    registry (Fix 2 / t-convention-marker).

    Lets the postmortem / Kaizen classifier (postmortem Fix 3) attribute a
    contract to a specific registry entry and version instead of treating it as
    plan-declared. Schema is pinned (R1-S6) so downstream consumers can rely on
    it: ``source`` is always ``"framework-conventions"``; ``pattern`` is the
    matched filename pattern; ``version`` is the registry version stamp.
    """

    model_config = ConfigDict(frozen=True)

    source: Literal["framework-conventions"] = "framework-conventions"
    pattern: str
    version: str


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
        language: Optional override aligned with ``language_id`` (FR-DFA-009,
            REQ-JSF-007), e.g. ``python``, ``nodejs``, ``vue``.
    """

    model_config = ConfigDict(frozen=True)

    file: str
    elements: list[ForwardElementSpec] = Field(default_factory=list)
    imports: list[ForwardImportSpec] = Field(default_factory=list)
    dependencies: Optional[ForwardDependencies] = None
    language: Optional[str] = None  # FR-DFA-009: "python", "dockerfile", "go", etc.
    convention_provenance: Optional[ConventionProvenance] = None  # Fix 2 / t-convention-marker


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
        file_specs: Per-file element and import specifications, keyed by
            relative file path.
        stages_completed: Pipeline stages that have enriched this manifest.
        metadata: Arbitrary key-value metadata attached by pipeline stages.
    """

    schema_version: str = "1.0.0"
    pipeline_run_id: Optional[str] = None
    generated_at: Optional[str] = None
    source_checksum: Optional[str] = None

    contracts: list[InterfaceContract] = Field(default_factory=list)
    file_specs: dict[str, ForwardFileSpec] = Field(default_factory=dict)
    stages_completed: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    # --- Lazy element indexes (excluded from serialization via PrivateAttr) ---
    #
    # _element_index: source_contract_id → ForwardElementSpec
    #     Only elements where source_contract_id is set are indexed here.
    # _name_index: element.name → list[ForwardElementSpec]
    #     All elements are indexed here regardless of source_contract_id.
    # _index_built: sentinel that prevents redundant rebuild passes.
    _element_index: dict[str, ForwardElementSpec] = PrivateAttr(default_factory=dict)
    _name_index: dict[str, list[ForwardElementSpec]] = PrivateAttr(default_factory=dict)
    _index_built: bool = PrivateAttr(default=False)

    def _build_element_index(self) -> None:
        """Build in-memory element indexes (lazy, called once).

        Populates two private indexes over all ``file_specs``:

        * ``_element_index`` — maps ``source_contract_id`` →
          ``ForwardElementSpec`` for elements where ``source_contract_id``
          is set.  If two elements share the same ``source_contract_id`` the
          later one wins and a warning is emitted.
        * ``_name_index`` — maps ``element.name`` →
          ``list[ForwardElementSpec]`` for *all* elements regardless of
          ``source_contract_id``.

        Idempotent: returns immediately if ``_index_built`` is ``True``.
        Neither index is serialized to JSON (both are ``PrivateAttr``).
        """
        if self._index_built:
            return

        element_index: dict[str, ForwardElementSpec] = {}
        name_index: dict[str, list[ForwardElementSpec]] = {}

        for file_spec in self.file_specs.values():
            for element in file_spec.elements:
                # --- ID index: only elements with a source_contract_id ---
                if element.source_contract_id:
                    if element.source_contract_id in element_index:
                        logger.warning(
                            "Duplicate source_contract_id in ForwardManifest element index; "
                            "later entry will overwrite earlier one.",
                            extra={
                                "source_contract_id": element.source_contract_id,
                                "element_name": element.name,
                            },
                        )
                    element_index[element.source_contract_id] = element

                # --- Name index: all elements ---
                name_index.setdefault(element.name, []).append(element)

        self._element_index = element_index
        self._name_index = name_index
        self._index_built = True

        logger.debug(
            "ForwardManifest element index built",
            extra={
                "indexed_by_id": len(element_index),
                "indexed_by_name": len(name_index),
            },
        )

    def get_element_by_id(self, element_id: str) -> Optional[ForwardElementSpec]:
        """Return the element spec whose ``source_contract_id`` matches *element_id*.

        Builds the element index on first call (O(n) once, O(1) thereafter).

        Args:
            element_id: The ``source_contract_id`` of the desired element.

        Returns:
            The matching ``ForwardElementSpec``, or ``None`` if not found.
        """
        self._build_element_index()
        return self._element_index.get(element_id)

    def get_elements_by_name(self, name: str) -> list[ForwardElementSpec]:
        """Return all element specs whose ``name`` field equals *name*.

        Multiple elements may share a name (e.g., a method named ``validate``
        defined in different classes across different files).

        Builds the element index on first call (O(n) once, O(1) thereafter).

        Args:
            name: The ``name`` field value to look up.

        Returns:
            A new list of matching ``ForwardElementSpec`` objects (may be
            empty).  Mutating the returned list does not affect the index.
        """
        self._build_element_index()
        return list(self._name_index.get(name, []))

    def all_elements(self) -> list[tuple[str, ForwardElementSpec]]:
        """Return all ``(source_contract_id, spec)`` pairs in the ID index.

        Only elements that have a non-``None`` ``source_contract_id`` are
        included, matching the population semantics of
        ``_build_element_index``.  Elements without a ``source_contract_id``
        can still be reached via ``get_elements_by_name`` or by iterating
        ``file_specs`` directly.

        Builds the element index on first call (O(n) once, O(1) thereafter).

        Returns:
            A new list of ``(element_id, ForwardElementSpec)`` tuples.
            Mutating the returned list does not affect the index.
        """
        self._build_element_index()
        return list(self._element_index.items())

    def contracts_for_task(self, task_id: str) -> list[InterfaceContract]:
        """Return project-wide contracts plus those specific to *task_id*.

        A contract is "project-wide" when its ``applicable_task_ids`` list
        is empty, meaning it applies to every task.

        Args:
            task_id: The task identifier to filter by.

        Returns:
            All contracts that apply to *task_id*.
        """
        return [
            c
            for c in self.contracts
            if not c.applicable_task_ids or task_id in c.applicable_task_ids
        ]

    def binding_constraints_for_task(self, task_id: str) -> list[str]:
        """Return ``binding_text`` strings for all contracts applicable to *task_id*.

        Args:
            task_id: The task identifier to filter by.

        Returns:
            Ordered list of binding-text directives ready for prompt injection.
        """
        return [c.binding_text for c in self.contracts_for_task(task_id)]

    def file_specs_for_task(
        self, task_id: str, target_files: list[str]
    ) -> dict[str, ForwardFileSpec]:
        """Return file specs whose path appears in *target_files*.

        Args:
            task_id: Unused by this method; reserved for future scoping logic.
            target_files: Relative file paths to include.

        Returns:
            Filtered subset of ``self.file_specs``.
        """
        return {
            path: spec
            for path, spec in self.file_specs.items()
            if path in target_files
        }

    def contract_count_by_category(self) -> Counter:
        """Return a ``Counter`` of contracts grouped by ``ContractCategory``.

        Returns:
            Mapping of ``ContractCategory`` → count.
        """
        return Counter(c.category for c in self.contracts)

    def validate_implementation(
        self,
        implementation,
        target_files=None,
        *,
        task_id=None,
        include_contracts=True,
    ):
        """Validate drafted code against this manifest's specs and contracts (FR-3).

        This is the **single canonical** post-generation enforcement path: the same
        ``ForwardManifest`` the drafter is shown at draft time (``spec_builder``) is the
        one whose ``validate_implementation`` the reviewer calls — so the drafter sees
        exactly what it will be reviewed against. (Historically this method was *referenced*
        by ``reviewer.py`` but never existed; the ``getattr`` returned ``None`` and
        enforcement was dormant — see ``FORWARD_MANIFEST_DRAFT_TIME_REQUIREMENTS.md`` FR-3.)

        Splits a multi-file implementation blob into per-file code, builds a Python
        :class:`ManifestRegistry`, and runs the structural validator over a **scoped**
        sub-manifest so a single-draft review never false-flags files it did not produce:

        * ``file_specs`` are scoped to ``target_files`` and to **Python** files that parse
          (the structural validator is AST-based; non-``.py`` files degrade to no-op rather
          than emit spurious ``missing_element`` violations).
        * ``contracts`` are validated only when ``include_contracts`` and a ``task_id`` is
          given (scoped via :meth:`contracts_for_task`); without a ``task_id`` the relevant
          contract subset cannot be determined safely, so contracts are skipped rather than
          validated project-wide against a single draft's registry (which would false-flag
          symbols defined in undrafted files).

        Args:
            implementation: Either a single drafted code string, or a mapping of
                ``relative_path -> source`` for an already-split multi-file draft.
            target_files: The relative paths this draft produced. Required to attribute a
                single ``str`` blob to file specs; with multiple files the blob is split via
                :func:`extract_multi_file_code`.
            task_id: When provided, scopes contract validation to contracts applicable to
                this task (:meth:`contracts_for_task`).
            include_contracts: Set ``False`` to validate ``file_specs`` only.

        Returns:
            List of ``ContractViolation`` (the validator's dataclass; field-identical to
            :class:`ContractViolation` here). Empty on a fully-compliant draft, on a parse
            failure, or when there is nothing in scope to validate.
        """
        from pathlib import Path as _Path

        from startd8.forward_manifest_validator import validate_forward_manifest
        from startd8.utils.code_manifest import generate_file_manifest
        from startd8.utils.manifest_registry import ManifestRegistry

        # 1. Resolve per-file source. A dict is taken as-is; a str is split by target_files.
        if isinstance(implementation, dict):
            per_file = dict(implementation)
        else:
            files = list(target_files or [])
            if not files:
                # A bare blob with no target files cannot be attributed to a spec.
                return []
            if len(files) == 1:
                per_file = {files[0]: implementation}
            else:
                from startd8.utils.code_extraction import extract_multi_file_code

                per_file = extract_multi_file_code(implementation, files)
                # Single unmatched file fallback (mirrors the lead-contractor path).
                if not per_file and len(files) == 1:
                    per_file = {files[0]: implementation}

        # 2. Build a Python registry (AST-based). Non-.py files are skipped: the structural
        #    validator parses Python only, so including them would yield false violations.
        manifests = {}
        for rel_path, src in per_file.items():
            if not str(rel_path).endswith(".py") or src is None:
                continue
            try:
                fm = generate_file_manifest(
                    file_path=rel_path, project_root=_Path("."), source=src,
                )
            except Exception as exc:  # noqa: BLE001 - degrade gracefully per file
                logger.debug(
                    "validate_implementation: could not build manifest for %s: %s",
                    rel_path, exc,
                )
                continue
            # A file that failed to parse has empty elements + populated errors;
            # validating its spec would emit misleading ``missing_element`` violations
            # for what is really a syntax error (caught separately by the reviewer).
            if getattr(fm, "errors", None):
                logger.debug(
                    "validate_implementation: skipping %s (parse errors: %s)",
                    rel_path, fm.errors,
                )
                continue
            manifests[rel_path] = fm
        if not manifests:
            return []
        registry = ManifestRegistry(manifests=manifests)

        # 3. Scope the manifest to what this draft actually produced.
        scope = set(target_files) if target_files else None
        scoped_specs = {
            path: spec
            for path, spec in self.file_specs.items()
            if path in manifests and (scope is None or path in scope)
        }
        if include_contracts and task_id is not None:
            scoped_contracts = self.contracts_for_task(task_id)
        else:
            scoped_contracts = []

        if not scoped_specs and not scoped_contracts:
            return []

        scoped_manifest = ForwardManifest(
            file_specs=scoped_specs,
            contracts=scoped_contracts,
        )
        return validate_forward_manifest(scoped_manifest, registry)


# ═══════════════════════════════════════════════════════════════════════════
# ContractViolation (plain dataclass, not Pydantic)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ContractViolation:
    """A detected violation of an interface contract.

    Produced by post-generation validation when generated code does not
    satisfy a binding constraint from the manifest.

    Attributes:
        contract_id: ID of the violated ``InterfaceContract``.
        violation_type: Category of the violation (e.g., ``"missing_element"``).
        expected: What the contract required.
        actual: What was found in generated code (``None`` if absent).
        file_path: File where the violation was detected.
        severity: Severity level — one of ``"error"``, ``"warning"``,
            ``"info"`` (default ``"error"``).
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


def _format_endpoint_schema_parts(
    req_schema: object,
    resp_schema: object,
) -> list[str]:
    """Format request/response schema dicts into binding-text field parts.

    Defensively accesses nested ``fields`` lists per existence → type → access
    order to avoid ``AttributeError`` or ``TypeError`` on malformed schemas.

    Args:
        req_schema: Value of ``InterfaceContract.request_schema`` (any type).
        resp_schema: Value of ``InterfaceContract.response_schema`` (any type).

    Returns:
        List of formatted strings such as
        ``["request_fields=[name, age]", "response_fields=[id, status]"]``.
        Empty if the schemas are ``None`` or malformed.
    """
    parts: list[str] = []
    for label, schema in (("request_fields", req_schema), ("response_fields", resp_schema)):
        if not isinstance(schema, dict):
            continue
        fields = schema.get("fields", [])
        if not fields or not isinstance(fields, list):
            continue
        field_names = ", ".join(
            f.get("name", "?") for f in fields[:5] if isinstance(f, dict)
        )
        if field_names:
            parts.append(f"{label}=[{field_names}]")
    return parts


def compute_binding_text(contract: InterfaceContract) -> str:
    """Compute a compact binding-text directive from an ``InterfaceContract``.

    Produces a ``[BINDING]`` or ``[ADVISORY]`` prefixed string with
    category-specific fields joined by `` | ``.

    ``[BINDING]`` is used for ``EXPLICIT`` and ``INFERRED`` confidence levels;
    ``[ADVISORY]`` is used for ``TENTATIVE``.

    Args:
        contract: The contract to render.

    Returns:
        A single-line binding-text string ready for prompt injection.
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
        parts.extend(
            _format_endpoint_schema_parts(contract.request_schema, contract.response_schema)
        )
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

    Supports all element kinds including ``CONSTANT``/``VARIABLE`` (which carry
    ``type_annotation`` and ``value_repr`` instead of a signature).
    Derives ``parent_class`` from ``element.fqn`` when the FQN is dotted and
    the element kind is a nested kind (method, property, constant, variable).

    Args:
        element: AST-derived element from ``code_manifest``.
        source_contract_id: Provenance ID linking this spec to an
            ``InterfaceContract``.  Callers should provide a stable ID such as
            ``"flcm-ast-{relpath}:{line}:{fqn}"``.  When ``None`` the element
            will not appear in ``ForwardManifest.all_elements()`` or be
            reachable via ``get_element_by_id()``.

    Returns:
        A validated ``ForwardElementSpec``.
    """
    # Derive parent_class only for nested kinds where the FQN is dotted.
    parent_class: Optional[str] = None
    nested_kinds = {
        ElementKind.METHOD,
        ElementKind.ASYNC_METHOD,
        ElementKind.PROPERTY,
        ElementKind.CONSTANT,
        ElementKind.VARIABLE,
    }
    if element.kind in nested_kinds and "." in element.fqn:
        parts = element.fqn.rsplit(".", 1)
        if parts[0]:
            # Strip outer nesting beyond one level (Outer.Inner → Inner).
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
        is_static=element.is_static,
        is_classmethod=element.is_classmethod,
        is_abstract=element.is_abstract,
        type_annotation=element.type_annotation,
        value_repr=element.value_repr,
    )


def forward_import_spec_from_entry(
    entry: ImportEntry,
    project_root: Optional[Path] = None,
    file_path: Optional[Path] = None,
) -> Optional[ForwardImportSpec]:
    """Convert an AST ``ImportEntry`` to a ``ForwardImportSpec``.

    Relative imports (``is_relative=True``) are resolved to absolute module
    paths using ``project_root`` and ``file_path``.  The ``src/`` directory is
    stripped from the package path because it is a layout convention and not
    part of the Python package namespace.

    If resolution fails or the required paths are not provided, the import is
    dropped and ``None`` is returned.

    Args:
        entry: AST-derived import from ``code_manifest``.
        project_root: Absolute path to the project root directory.
            Required for relative import resolution.
        file_path: Absolute path to the source file containing the import.
            Required for relative import resolution.

    Returns:
        A ``ForwardImportSpec``, or ``None`` if the import should be dropped.
    """
    module = entry.module

    if entry.is_relative:
        if project_root is None or file_path is None:
            return None
        try:
            project_root = Path(project_root)
            file_path = Path(file_path)
            rel = file_path.parent.relative_to(project_root)
            # Strip "src" — it's a layout convention, not a package component.
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


def path_language_hints_from_file_specs(
    file_specs: Optional[dict[str, "ForwardFileSpec"]],
) -> dict[str, str]:
    """Build path → ``language_id`` map from ``ForwardFileSpec.language`` (REQ-JSF-007).

    Populates both the manifest dict key and a POSIX-normalized path so
    ``resolve_language`` can match ``target_files`` regardless of separator style.
    """
    if not file_specs:
        return {}
    out: dict[str, str] = {}
    for path, spec in file_specs.items():
        lang = spec.language
        if not lang:
            continue
        lid = str(lang).strip().lower()
        out[path] = lid
        try:
            out[Path(path).as_posix()] = lid
        except (TypeError, ValueError):
            pass
    return out


def path_language_hints_from_forward_manifest(
    manifest: Optional["ForwardManifest"],
) -> dict[str, str]:
    """REQ-JSF-007: collect per-path language overrides from a deserialized manifest."""
    if manifest is None:
        return {}
    return path_language_hints_from_file_specs(manifest.file_specs)


def forward_dependencies_from_deps(deps: Dependencies) -> ForwardDependencies:
    """Convert AST ``Dependencies`` to ``ForwardDependencies``.

    Maps ``external`` and ``stdlib`` package lists; drops ``internal`` and
    ``conditional`` entries which are not relevant to the forward manifest.

    Args:
        deps: AST-derived dependency summary from ``code_manifest``.

    Returns:
        A ``ForwardDependencies`` with only external and stdlib packages.
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
    "path_language_hints_from_file_specs",
    "path_language_hints_from_forward_manifest",
]