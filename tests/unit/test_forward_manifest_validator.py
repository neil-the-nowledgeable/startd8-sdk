import pytest
from startd8.forward_manifest import (
    ForwardManifest,
    InterfaceContract,
    ForwardFileSpec,
    ContractConfidence,
    ForwardElementSpec,
)
from startd8.forward_manifest_validator import (
    validate_forward_manifest,
    ContractViolation,
)
from startd8.utils.manifest_registry import ManifestRegistry
from startd8.utils.code_manifest import FileManifest, Element, ElementKind, Signature, Param, Span


@pytest.fixture
def mock_registry():
    """Provides a mocked ManifestRegistry to test validation structurally."""
    # Build a fake Manifest map
    manifest_map = {
        "src/app/core.py": FileManifest(
            schema_version="1.0",
            module="app.core",
            file="src/app/core.py",
            digest="mock_hash",
            elements=[
                Element(
                    kind=ElementKind.CLASS,
                    name="UserProfile",
                    fqn="app.core.UserProfile",
                    span=Span(start_line=1, start_col=0, end_line=10, end_col=0),
                    bases=["BaseModel"],
                    children=[
                        Element(
                            kind=ElementKind.FUNCTION,
                            name="update",
                            fqn="app.core.UserProfile.update",
                            span=Span(start_line=2, start_col=4, end_line=10, end_col=0),
                            signature=Signature(
                                params=[
                                    Param(name="self", kind="positional"),
                                    Param(name="data", annotation="dict", kind="positional"),
                                ],
                                return_annotation="bool"
                            )
                        )
                    ]
                )
            ],
            imports=[]
        ),
        "src/app/utils.py": FileManifest(
            schema_version="1.0",
            module="app.utils",
            file="src/app/utils.py",
            digest="mock_hash",
            elements=[
                Element(
                    kind=ElementKind.FUNCTION,
                    name="calculate_tax",
                    fqn="app.utils.calculate_tax",
                    span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
                    signature=Signature(
                        params=[Param(name="amount", annotation="float", kind="positional")],
                        return_annotation="float"
                    )
                )
            ],
            imports=[]
        )
    }

    registry = ManifestRegistry(manifest_map)
    return registry


class TestForwardManifestValidator:

    def test_missing_function_name_yields_error(self, mock_registry):
        manifest = ForwardManifest(
            contracts=[
                InterfaceContract(
                    contract_id="req-1",
                    category="function_name",
                    function_name="app.core.missing",
                    severity="error",
                    confidence=ContractConfidence.EXPLICIT,
                    description="mock description",
                    binding_text="mock binding"
                )
            ],
            file_specs={}
        )

        violations = validate_forward_manifest(manifest, mock_registry)
        assert len(violations) == 1
        assert violations[0].violation_type == "missing_function"
        assert violations[0].severity == "error"
        assert "app.core.missing" in violations[0].expected

    def test_valid_function_name_passes(self, mock_registry):
        manifest = ForwardManifest(
            contracts=[
                InterfaceContract(
                    contract_id="req-1",
                    category="function_name",
                    function_name="app.utils.calculate_tax",
                    severity="error",
                    confidence=ContractConfidence.EXPLICIT,
                    description="mock description",
                    binding_text="mock binding"
                )
            ],
            file_specs={}
        )
        violations = validate_forward_manifest(manifest, mock_registry)
        assert len(violations) == 0

    def test_signature_mismatch_yields_error(self, mock_registry):
        manifest = ForwardManifest(
            contracts=[
                InterfaceContract(
                    contract_id="req-2",
                    category="function_name",
                    function_name="app.utils.calculate_tax",
                    severity="error",
                    confidence=ContractConfidence.EXPLICIT,
                    description="mock description",
                    binding_text="def calculate_tax(amount: float) -> int"
                )
            ],
            file_specs={}
        )
        violations = validate_forward_manifest(manifest, mock_registry)
        assert len(violations) == 1
        assert violations[0].violation_type == "signature_mismatch"
        assert violations[0].severity == "error"
        assert "float" in violations[0].actual
        assert "int" in violations[0].expected

    def test_valid_class_hierarchy_passes(self, mock_registry):
        manifest = ForwardManifest(
            contracts=[
                InterfaceContract(
                    contract_id="req-3",
                    category="class_name",
                    class_name="app.core.UserProfile",
                    base_class="BaseModel",
                    severity="error",
                    confidence=ContractConfidence.EXPLICIT,
                    description="mock description",
                    binding_text="mock binding"
                )
            ],
            file_specs={}
        )
        violations = validate_forward_manifest(manifest, mock_registry)
        assert len(violations) == 0

    def test_invalid_class_hierarchy_yields_error(self, mock_registry):
        manifest = ForwardManifest(
            contracts=[
                InterfaceContract(
                    contract_id="req-4",
                    category="class_name",
                    class_name="app.core.UserProfile",
                    base_class="SQLModel",
                    severity="error",
                    confidence=ContractConfidence.EXPLICIT,
                    description="mock description",
                    binding_text="mock binding"
                )
            ],
            file_specs={}
        )
        violations = validate_forward_manifest(manifest, mock_registry)
        assert len(violations) == 1
        assert violations[0].violation_type == "missing_base_class"
        assert "SQLModel" in violations[0].expected

    def test_advisory_contract_yields_warning(self, mock_registry):
        manifest = ForwardManifest(
            contracts=[
                InterfaceContract(
                    contract_id="advisory-1",
                    category="formula",
                    description="Tax must be at least 15%",
                    severity="warning",
                    confidence=ContractConfidence.INFERRED,
                    binding_text="mock binding"
                )
            ],
            file_specs={}
        )
        violations = validate_forward_manifest(manifest, mock_registry)
        assert len(violations) == 1
        assert violations[0].severity == "warning"
        assert "unverified_formula" in violations[0].violation_type

    def test_file_spec_verification(self, mock_registry):
        manifest = ForwardManifest(
            contracts=[],
            file_specs={
                "src/app/core.py": ForwardFileSpec(
                    file="src/app/core.py",
                    elements=[
                        ForwardElementSpec(kind=ElementKind.CLASS, name="UserProfile"),
                        ForwardElementSpec(
                            kind=ElementKind.FUNCTION,
                            name="update",
                            signature=Signature(params=[], return_annotation="bool")
                        ),
                    ]
                ),
                "src/app/missing.py": ForwardFileSpec(
                    file="src/app/missing.py",
                    elements=[
                        ForwardElementSpec(kind=ElementKind.CLASS, name="ShouldFail")
                    ]
                )
            }
        )
        violations = validate_forward_manifest(manifest, mock_registry)
        
        # Should flag missing.py completely
        assert len(violations) == 1
        assert violations[0].violation_type == "missing_file"
        assert violations[0].file_path == "src/app/missing.py"

    def test_file_spec_missing_element(self, mock_registry):
        manifest = ForwardManifest(
            contracts=[],
            file_specs={
                "src/app/core.py": ForwardFileSpec(
                    file="src/app/core.py",
                    elements=[
                        ForwardElementSpec(kind=ElementKind.CLASS, name="MissingClass")
                    ]
                )
            }
        )
        violations = validate_forward_manifest(manifest, mock_registry)
        assert len(violations) == 1
        assert violations[0].violation_type == "missing_class"
        assert "MissingClass" in violations[0].expected
