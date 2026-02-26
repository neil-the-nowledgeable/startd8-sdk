"""
Unit tests for the Forward-Looking Code Manifest (FLCM) schema.

Covers: enums, InterfaceContract, ForwardElementSpec (kind invariants + to_element bridge),
ForwardImportSpec, ForwardDependencies, ForwardFileSpec, ForwardManifest queries,
compute_binding_text, JSON round-trip, and ContractViolation.
"""

from __future__ import annotations

import pytest

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ContractViolation,
    ForwardDependencies,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
    InterfaceContract,
    compute_binding_text,
)
from startd8.utils.code_manifest import (
    Element,
    ElementKind,
    Param,
    Signature,
    Span,
    Visibility,
)


# ═══════════════════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_contract(**overrides) -> InterfaceContract:
    """Create an InterfaceContract with sensible defaults."""
    defaults = {
        "contract_id": "C-001",
        "category": ContractCategory.FUNCTION_NAME,
        "confidence": ContractConfidence.EXPLICIT,
        "description": "Must use this name",
        "binding_text": "[BINDING] function=foo | Must use this name",
        "function_name": "foo",
    }
    defaults.update(overrides)
    return InterfaceContract(**defaults)


def _make_forward_element(**overrides) -> ForwardElementSpec:
    """Create a ForwardElementSpec with sensible defaults.

    Auto-creates a Signature for callable kinds if not provided.
    """
    defaults = {
        "kind": ElementKind.FUNCTION,
        "name": "my_func",
    }
    defaults.update(overrides)
    kind = defaults["kind"]
    callable_kinds = {
        ElementKind.FUNCTION,
        ElementKind.ASYNC_FUNCTION,
        ElementKind.METHOD,
        ElementKind.ASYNC_METHOD,
        ElementKind.PROPERTY,
    }
    if kind in callable_kinds and "signature" not in defaults:
        defaults["signature"] = Signature(params=[])
    return ForwardElementSpec(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
# Enum validation
# ═══════════════════════════════════════════════════════════════════════════


class TestEnumValues:
    def test_contract_category_has_eight_values(self) -> None:
        assert len(ContractCategory) == 8

    def test_contract_category_values(self) -> None:
        expected = {
            "function_name",
            "class_name",
            "api_endpoint",
            "config_key",
            "import_path",
            "formula",
            "render_pattern",
            "infrastructure",
        }
        assert {c.value for c in ContractCategory} == expected

    def test_contract_confidence_has_three_values(self) -> None:
        assert len(ContractConfidence) == 3

    def test_contract_confidence_values(self) -> None:
        expected = {"explicit", "inferred", "tentative"}
        assert {c.value for c in ContractConfidence} == expected

    def test_enum_str_serialization(self) -> None:
        assert str(ContractCategory.FUNCTION_NAME) == "ContractCategory.FUNCTION_NAME"
        assert ContractCategory.FUNCTION_NAME.value == "function_name"
        assert ContractConfidence.EXPLICIT.value == "explicit"


# ═══════════════════════════════════════════════════════════════════════════
# InterfaceContract
# ═══════════════════════════════════════════════════════════════════════════


class TestInterfaceContract:
    def test_minimal_construction(self) -> None:
        c = InterfaceContract(
            contract_id="C-001",
            category=ContractCategory.FUNCTION_NAME,
            confidence=ContractConfidence.EXPLICIT,
            description="Use this name",
            binding_text="[BINDING] function=foo",
        )
        assert c.contract_id == "C-001"
        assert c.category == ContractCategory.FUNCTION_NAME

    def test_category_specific_fields(self) -> None:
        c = _make_contract(
            category=ContractCategory.API_ENDPOINT,
            endpoint="/api/v1/users",
            request_schema={"type": "object"},
            response_schema={"type": "array"},
        )
        assert c.endpoint == "/api/v1/users"
        assert c.request_schema == {"type": "object"}
        assert c.response_schema == {"type": "array"}

    def test_frozen_enforcement(self) -> None:
        c = _make_contract()
        with pytest.raises(Exception):
            c.contract_id = "C-999"  # type: ignore[misc]

    def test_defaults(self) -> None:
        c = _make_contract()
        assert c.applicable_task_ids == []
        assert c.source_reference is None
        assert c.base_class is None
        assert c.env_var is None

    def test_applicable_task_ids(self) -> None:
        c = _make_contract(applicable_task_ids=["T-1", "T-2"])
        assert c.applicable_task_ids == ["T-1", "T-2"]


# ═══════════════════════════════════════════════════════════════════════════
# ForwardElementSpec
# ═══════════════════════════════════════════════════════════════════════════


class TestForwardElementSpec:
    def test_callable_requires_signature(self) -> None:
        with pytest.raises(ValueError, match="must have a signature"):
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="bad_func")

    def test_async_function_requires_signature(self) -> None:
        with pytest.raises(ValueError, match="must have a signature"):
            ForwardElementSpec(kind=ElementKind.ASYNC_FUNCTION, name="bad")

    def test_method_requires_signature(self) -> None:
        with pytest.raises(ValueError, match="must have a signature"):
            ForwardElementSpec(kind=ElementKind.METHOD, name="bad")

    def test_non_class_rejects_bases(self) -> None:
        with pytest.raises(ValueError, match="must not have bases"):
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="bad_func",
                signature=Signature(params=[]),
                bases=["SomeBase"],
            )

    def test_class_accepts_bases(self) -> None:
        spec = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="MyClass",
            bases=["BaseModel"],
        )
        assert spec.bases == ["BaseModel"]

    def test_constant_no_signature_ok(self) -> None:
        spec = ForwardElementSpec(kind=ElementKind.CONSTANT, name="MAX_RETRIES")
        assert spec.signature is None

    def test_to_element_bridge(self) -> None:
        sig = Signature(
            params=[Param(name="x", annotation="int")],
            return_annotation="str",
        )
        spec = _make_forward_element(
            name="process",
            kind=ElementKind.FUNCTION,
            signature=sig,
            visibility=Visibility.PROTECTED,
            decorators=["staticmethod"],
            docstring_hint="Process the input.",
        )
        el = spec.to_element()

        assert isinstance(el, Element)
        assert el.kind == ElementKind.FUNCTION
        assert el.name == "process"
        assert el.fqn == "process"
        assert el.span == Span(start_line=0, start_col=0, end_line=0, end_col=0)
        assert el.signature == sig
        assert el.visibility == Visibility.PROTECTED
        assert el.decorators == ["staticmethod"]
        assert el.docstring == "Process the input."

    def test_to_element_class_with_bases(self) -> None:
        spec = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="MyModel",
            bases=["BaseModel", "Serializable"],
        )
        el = spec.to_element()
        assert el.bases == ["BaseModel", "Serializable"]
        assert el.kind == ElementKind.CLASS

    def test_to_element_passes_element_validator(self) -> None:
        """to_element() produces a valid Element (Element's own validator doesn't raise)."""
        spec = _make_forward_element(
            kind=ElementKind.ASYNC_FUNCTION,
            name="fetch",
            signature=Signature(params=[Param(name="url", annotation="str")]),
        )
        el = spec.to_element()
        assert el.kind == ElementKind.ASYNC_FUNCTION
        assert el.signature is not None

    def test_frozen(self) -> None:
        spec = _make_forward_element()
        with pytest.raises(Exception):
            spec.name = "other"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# ForwardImportSpec + ForwardDependencies
# ═══════════════════════════════════════════════════════════════════════════


class TestForwardImportSpec:
    def test_import_kind(self) -> None:
        spec = ForwardImportSpec(kind="import", module="os")
        assert spec.kind == "import"
        assert spec.module == "os"

    def test_from_kind(self) -> None:
        spec = ForwardImportSpec(kind="from", module="pathlib", names=["Path"])
        assert spec.kind == "from"
        assert spec.names == ["Path"]

    def test_invalid_kind_rejected(self) -> None:
        with pytest.raises(Exception):
            ForwardImportSpec(kind="wildcard", module="os")  # type: ignore[arg-type]

    def test_defaults(self) -> None:
        spec = ForwardImportSpec(kind="import", module="sys")
        assert spec.names == []
        assert spec.alias is None

    def test_frozen(self) -> None:
        spec = ForwardImportSpec(kind="import", module="os")
        with pytest.raises(Exception):
            spec.module = "sys"  # type: ignore[misc]


class TestForwardDependencies:
    def test_construction(self) -> None:
        deps = ForwardDependencies(external=["httpx", "pydantic"], stdlib=["os", "json"])
        assert deps.external == ["httpx", "pydantic"]
        assert deps.stdlib == ["os", "json"]

    def test_defaults(self) -> None:
        deps = ForwardDependencies()
        assert deps.external == []
        assert deps.stdlib == []

    def test_frozen(self) -> None:
        deps = ForwardDependencies(external=["httpx"])
        with pytest.raises(Exception):
            deps.external = []  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# ForwardFileSpec
# ═══════════════════════════════════════════════════════════════════════════


class TestForwardFileSpec:
    def test_construction(self) -> None:
        elem = _make_forward_element(name="handler")
        imp = ForwardImportSpec(kind="from", module="flask", names=["Flask"])
        deps = ForwardDependencies(external=["flask"])
        spec = ForwardFileSpec(
            file="src/app.py",
            elements=[elem],
            imports=[imp],
            dependencies=deps,
        )
        assert spec.file == "src/app.py"
        assert len(spec.elements) == 1
        assert len(spec.imports) == 1
        assert spec.dependencies is not None
        assert spec.dependencies.external == ["flask"]

    def test_optional_dependencies(self) -> None:
        spec = ForwardFileSpec(file="src/utils.py")
        assert spec.dependencies is None
        assert spec.elements == []
        assert spec.imports == []

    def test_frozen(self) -> None:
        spec = ForwardFileSpec(file="src/utils.py")
        with pytest.raises(Exception):
            spec.file = "other.py"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# ForwardManifest queries
# ═══════════════════════════════════════════════════════════════════════════


class TestForwardManifestQueries:
    def _build_manifest(self) -> ForwardManifest:
        """Build a manifest with project-wide and task-specific contracts."""
        c_global = _make_contract(
            contract_id="C-GLOBAL",
            applicable_task_ids=[],
            description="Global constraint",
        )
        c_task1 = _make_contract(
            contract_id="C-T1",
            applicable_task_ids=["T-1"],
            description="Task 1 only",
        )
        c_task2 = _make_contract(
            contract_id="C-T2",
            applicable_task_ids=["T-2"],
            description="Task 2 only",
        )
        file_spec = ForwardFileSpec(
            file="src/handler.py",
            elements=[_make_forward_element(name="handle_request")],
        )
        return ForwardManifest(
            contracts=[c_global, c_task1, c_task2],
            file_specs={"src/handler.py": file_spec},
        )

    def test_contracts_for_task_includes_global(self) -> None:
        m = self._build_manifest()
        result = m.contracts_for_task("T-1")
        ids = [c.contract_id for c in result]
        assert "C-GLOBAL" in ids
        assert "C-T1" in ids

    def test_contracts_for_task_excludes_other(self) -> None:
        m = self._build_manifest()
        result = m.contracts_for_task("T-1")
        ids = [c.contract_id for c in result]
        assert "C-T2" not in ids

    def test_binding_constraints_for_task(self) -> None:
        m = self._build_manifest()
        texts = m.binding_constraints_for_task("T-1")
        assert len(texts) == 2
        assert all(isinstance(t, str) for t in texts)

    def test_binding_constraints_prefix_types(self) -> None:
        c_explicit = _make_contract(
            contract_id="C-E",
            confidence=ContractConfidence.EXPLICIT,
            binding_text="[BINDING] explicit",
        )
        c_tentative = _make_contract(
            contract_id="C-T",
            confidence=ContractConfidence.TENTATIVE,
            binding_text="[ADVISORY] tentative",
        )
        m = ForwardManifest(contracts=[c_explicit, c_tentative])
        texts = m.binding_constraints_for_task("any")
        assert "[BINDING]" in texts[0]
        assert "[ADVISORY]" in texts[1]

    def test_file_specs_for_task_match(self) -> None:
        m = self._build_manifest()
        result = m.file_specs_for_task("T-1", ["src/handler.py"])
        assert "src/handler.py" in result

    def test_file_specs_for_task_no_match(self) -> None:
        m = self._build_manifest()
        result = m.file_specs_for_task("T-1", ["src/nonexistent.py"])
        assert result == {}

    def test_contract_count_by_category(self) -> None:
        m = self._build_manifest()
        counts = m.contract_count_by_category()
        assert counts[ContractCategory.FUNCTION_NAME] == 3

    def test_not_frozen(self) -> None:
        m = ForwardManifest()
        m.stages_completed.append("DESIGN")
        assert "DESIGN" in m.stages_completed

    def test_default_schema_version(self) -> None:
        m = ForwardManifest()
        assert m.schema_version == "1.0.0"


# ═══════════════════════════════════════════════════════════════════════════
# compute_binding_text
# ═══════════════════════════════════════════════════════════════════════════


class TestComputeBindingText:
    def test_function_name_category(self) -> None:
        c = _make_contract(
            category=ContractCategory.FUNCTION_NAME,
            function_name="process_data",
            description="Must be named process_data",
        )
        result = compute_binding_text(c)
        assert "[BINDING]" in result
        assert "function=process_data" in result
        assert "Must be named process_data" in result

    def test_class_name_with_base(self) -> None:
        c = _make_contract(
            category=ContractCategory.CLASS_NAME,
            class_name="UserService",
            base_class="BaseService",
            description="Service class",
        )
        result = compute_binding_text(c)
        assert "class=UserService" in result
        assert "base=BaseService" in result

    def test_api_endpoint_category(self) -> None:
        c = _make_contract(
            category=ContractCategory.API_ENDPOINT,
            endpoint="/api/v1/health",
            description="Health check",
        )
        result = compute_binding_text(c)
        assert "endpoint=/api/v1/health" in result

    def test_config_key_category(self) -> None:
        c = _make_contract(
            category=ContractCategory.CONFIG_KEY,
            env_var="DATABASE_URL",
            description="Database connection",
        )
        result = compute_binding_text(c)
        assert "env_var=DATABASE_URL" in result

    def test_import_path_category(self) -> None:
        c = _make_contract(
            category=ContractCategory.IMPORT_PATH,
            import_path="myapp.services.user",
            description="User service module",
        )
        result = compute_binding_text(c)
        assert "import_path=myapp.services.user" in result

    def test_formula_category_with_value(self) -> None:
        c = _make_contract(
            category=ContractCategory.FORMULA,
            formula="TIMEOUT_MS",
            constant_value="30000",
            description="Timeout constant",
        )
        result = compute_binding_text(c)
        assert "formula=TIMEOUT_MS" in result
        assert "value=30000" in result

    def test_render_pattern_category(self) -> None:
        c = _make_contract(
            category=ContractCategory.RENDER_PATTERN,
            pattern="card-grid",
            description="Card grid layout",
        )
        result = compute_binding_text(c)
        assert "pattern=card-grid" in result

    def test_infrastructure_category(self) -> None:
        c = _make_contract(
            category=ContractCategory.INFRASTRUCTURE,
            dependency="redis",
            description="Redis cache",
        )
        result = compute_binding_text(c)
        assert "dependency=redis" in result

    def test_explicit_confidence_binding_prefix(self) -> None:
        c = _make_contract(confidence=ContractConfidence.EXPLICIT)
        result = compute_binding_text(c)
        assert result.startswith("[BINDING]")

    def test_inferred_confidence_binding_prefix(self) -> None:
        c = _make_contract(confidence=ContractConfidence.INFERRED)
        result = compute_binding_text(c)
        assert result.startswith("[BINDING]")

    def test_tentative_confidence_advisory_prefix(self) -> None:
        c = _make_contract(confidence=ContractConfidence.TENTATIVE)
        result = compute_binding_text(c)
        assert result.startswith("[ADVISORY]")

    def test_description_only_fallback(self) -> None:
        """When category-specific fields are missing, just prefix + description."""
        c = _make_contract(
            category=ContractCategory.INFRASTRUCTURE,
            dependency=None,
            description="Some generic constraint",
            function_name=None,
        )
        result = compute_binding_text(c)
        assert "[BINDING]" in result
        assert "Some generic constraint" in result
        # No category-specific field injected
        assert "dependency=" not in result

    def test_pipe_separator(self) -> None:
        c = _make_contract(function_name="foo", description="desc")
        result = compute_binding_text(c)
        assert " | " in result


# ═══════════════════════════════════════════════════════════════════════════
# JSON round-trip
# ═══════════════════════════════════════════════════════════════════════════


class TestJsonRoundTrip:
    def test_interface_contract_round_trip(self) -> None:
        c = _make_contract(applicable_task_ids=["T-1"])
        data = c.model_dump()
        restored = InterfaceContract.model_validate(data)
        assert restored == c

    def test_forward_element_spec_round_trip(self) -> None:
        spec = _make_forward_element(
            kind=ElementKind.FUNCTION,
            name="process",
            signature=Signature(
                params=[Param(name="x", annotation="int")],
                return_annotation="str",
            ),
            decorators=["cache"],
        )
        data = spec.model_dump()
        restored = ForwardElementSpec.model_validate(data)
        assert restored == spec

    def test_forward_file_spec_round_trip(self) -> None:
        fs = ForwardFileSpec(
            file="src/app.py",
            elements=[_make_forward_element()],
            imports=[ForwardImportSpec(kind="from", module="os", names=["path"])],
            dependencies=ForwardDependencies(external=["httpx"]),
        )
        data = fs.model_dump()
        restored = ForwardFileSpec.model_validate(data)
        assert restored == fs

    def test_forward_manifest_round_trip(self) -> None:
        m = ForwardManifest(
            schema_version="1.0.0",
            pipeline_run_id="run-001",
            generated_at="2026-02-25T00:00:00Z",
            source_checksum="sha256:abc",
            contracts=[_make_contract()],
            file_specs={
                "src/app.py": ForwardFileSpec(
                    file="src/app.py",
                    elements=[_make_forward_element()],
                )
            },
            stages_completed=["DESIGN"],
        )
        data = m.model_dump()
        restored = ForwardManifest.model_validate(data)
        assert restored == m

    def test_forward_manifest_json_string_round_trip(self) -> None:
        m = ForwardManifest(
            contracts=[_make_contract()],
            file_specs={
                "src/app.py": ForwardFileSpec(
                    file="src/app.py",
                    elements=[_make_forward_element()],
                )
            },
        )
        json_str = m.model_dump_json()
        restored = ForwardManifest.model_validate_json(json_str)
        assert restored == m

    def test_forward_import_spec_round_trip(self) -> None:
        spec = ForwardImportSpec(kind="from", module="typing", names=["Optional"], alias="opt")
        data = spec.model_dump()
        restored = ForwardImportSpec.model_validate(data)
        assert restored == spec

    def test_forward_dependencies_round_trip(self) -> None:
        deps = ForwardDependencies(external=["httpx"], stdlib=["os"])
        data = deps.model_dump()
        restored = ForwardDependencies.model_validate(data)
        assert restored == deps


# ═══════════════════════════════════════════════════════════════════════════
# ContractViolation
# ═══════════════════════════════════════════════════════════════════════════


class TestContractViolation:
    def test_construction(self) -> None:
        v = ContractViolation(
            contract_id="C-001",
            violation_type="naming",
            expected="process_data",
            actual="processData",
            file_path="src/app.py",
        )
        assert v.contract_id == "C-001"
        assert v.violation_type == "naming"
        assert v.expected == "process_data"
        assert v.actual == "processData"
        assert v.file_path == "src/app.py"

    def test_defaults(self) -> None:
        v = ContractViolation(
            contract_id="C-002",
            violation_type="missing",
            expected="create_user",
        )
        assert v.actual is None
        assert v.file_path is None
        assert v.severity == "error"

    def test_frozen(self) -> None:
        v = ContractViolation(
            contract_id="C-001",
            violation_type="naming",
            expected="foo",
        )
        with pytest.raises(Exception):
            v.contract_id = "C-999"  # type: ignore[misc]

    def test_equality(self) -> None:
        v1 = ContractViolation(
            contract_id="C-001",
            violation_type="naming",
            expected="foo",
            severity="warning",
        )
        v2 = ContractViolation(
            contract_id="C-001",
            violation_type="naming",
            expected="foo",
            severity="warning",
        )
        assert v1 == v2

    def test_inequality(self) -> None:
        v1 = ContractViolation(
            contract_id="C-001",
            violation_type="naming",
            expected="foo",
        )
        v2 = ContractViolation(
            contract_id="C-002",
            violation_type="naming",
            expected="foo",
        )
        assert v1 != v2
