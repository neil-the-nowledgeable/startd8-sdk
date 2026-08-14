"""Tests for health-neutral element verification of immutable evidence blobs."""

import startd8.forward_manifest_evidence as evidence_module
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
)
from startd8.forward_manifest_evidence import (
    ElementVerificationStatus,
    verify_forward_manifest_elements,
)
from startd8.utils.code_manifest import ElementKind


def _manifest(path: str, name: str = "expected_symbol") -> ForwardManifest:
    return ForwardManifest(
        file_specs={
            path: ForwardFileSpec(
                file=path,
                elements=[
                    ForwardElementSpec(
                        kind=ElementKind.FUNCTION,
                        name=name,
                        signature={"params": []},
                    )
                ],
            )
        }
    )


def test_verified_python_blob_reports_authoritative_tier():
    result = verify_forward_manifest_elements(
        _manifest("src/proof.py"),
        "src/proof.py",
        b"def expected_symbol():\n    return True\n",
    )

    assert result.status == ElementVerificationStatus.VERIFIED
    assert result.scope == "file"
    assert result.parser_tier == "authoritative"
    assert [item.name for item in result.expected_elements] == ["expected_symbol"]
    assert result.issues == []


def test_missing_element_is_a_structured_violation():
    result = verify_forward_manifest_elements(
        _manifest("src/proof.py"),
        "src/proof.py",
        "def other_symbol():\n    return False\n",
    )

    assert result.status == ElementVerificationStatus.VIOLATED
    assert result.finding_severity == "error"
    assert result.issues[0].violation_type == "missing_function"
    assert result.issues[0].severity == "error"


def test_suffix_match_preserves_manifest_key_for_validation():
    result = verify_forward_manifest_elements(
        _manifest("generated/src/proof.py"),
        "src/proof.py",
        "def expected_symbol():\n    pass\n",
    )

    assert result.status == ElementVerificationStatus.VERIFIED
    assert result.manifest_file_path == "generated/src/proof.py"


def test_benign_manifest_path_aliases_use_the_evidence_registry_key():
    for manifest_path in ("./src/proof.py", r"src\proof.py"):
        result = verify_forward_manifest_elements(
            _manifest(manifest_path),
            "src/proof.py",
            "def expected_symbol():\n    pass\n",
        )

        assert result.status == ElementVerificationStatus.VERIFIED
        assert result.manifest_file_path == manifest_path
        assert not any(issue.violation_type == "missing_file" for issue in result.issues)


def test_bare_manifest_filename_does_not_guess_a_deeper_evidence_path():
    result = verify_forward_manifest_elements(
        _manifest("proof.py"),
        "services/checkout/proof.py",
        "def expected_symbol():\n    pass\n",
    )

    assert result.status == ElementVerificationStatus.NOT_APPLICABLE
    assert result.reason == "file_spec_not_found"


def test_unsafe_manifest_alias_that_looks_matching_is_unavailable():
    for manifest_path in ("/repo/src/proof.py", "../src/proof.py"):
        result = verify_forward_manifest_elements(
            _manifest(manifest_path),
            "src/proof.py",
            "def expected_symbol():\n    pass\n",
        )

        assert result.status == ElementVerificationStatus.VERIFICATION_UNAVAILABLE
        assert result.reason is not None
        assert result.reason.startswith("invalid_manifest_file_path:")


def test_ambiguous_suffix_match_is_unavailable_not_green():
    manifest = ForwardManifest(
        file_specs={
            "one/src/proof.py": _manifest("one/src/proof.py").file_specs["one/src/proof.py"],
            "two/src/proof.py": _manifest("two/src/proof.py").file_specs["two/src/proof.py"],
        }
    )

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.py",
        "def expected_symbol():\n    pass\n",
    )

    assert result.status == ElementVerificationStatus.VERIFICATION_UNAVAILABLE
    assert result.reason is not None and result.reason.startswith("ambiguous_file_spec:")


def test_unsupported_language_is_unavailable_not_empty_success():
    manifest = ForwardManifest(
        file_specs={
            "src/proof.rs": ForwardFileSpec(
                file="src/proof.rs",
                elements=[
                    ForwardElementSpec(kind=ElementKind.CLASS, name="Expected")
                ],
            )
        }
    )

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.rs",
        "struct Expected {}\n",
    )

    assert result.status == ElementVerificationStatus.VERIFICATION_UNAVAILABLE
    assert result.reason == "parser_unavailable_or_unsupported"


def test_unsupported_manifest_major_is_unavailable():
    manifest = _manifest("src/proof.py").model_copy(
        update={"schema_version": "2.0.0"}
    )

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.py",
        "def expected_symbol():\n    pass\n",
    )

    assert result.status == ElementVerificationStatus.VERIFICATION_UNAVAILABLE
    assert result.reason == "unsupported_manifest_schema: 2.0.0"
    assert result.manifest_schema_version == "2.0.0"


def test_parse_error_is_unavailable_not_a_missing_element():
    result = verify_forward_manifest_elements(
        _manifest("src/proof.py"),
        "src/proof.py",
        "def (:\n",
    )

    assert result.status == ElementVerificationStatus.VERIFICATION_UNAVAILABLE
    assert result.reason == "source_parse_error"
    assert result.issues == []


def test_parser_exception_is_unavailable_not_a_reconcile_failure(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(evidence_module, "build_multilang_file_manifest", _boom)
    result = verify_forward_manifest_elements(
        _manifest("src/proof.py"),
        "src/proof.py",
        "def expected_symbol():\n    pass\n",
    )

    assert result.status == ElementVerificationStatus.VERIFICATION_UNAVAILABLE
    assert result.reason == "parser_error: RuntimeError"


def test_absent_or_empty_file_spec_is_not_applicable():
    absent = verify_forward_manifest_elements(
        ForwardManifest(),
        "src/proof.py",
        "def expected_symbol():\n    pass\n",
    )
    empty = verify_forward_manifest_elements(
        ForwardManifest(
            file_specs={
                "src/proof.py": ForwardFileSpec(file="src/proof.py", elements=[])
            }
        ),
        "src/proof.py",
        "def expected_symbol():\n    pass\n",
    )

    assert absent.status == ElementVerificationStatus.NOT_APPLICABLE
    assert absent.reason == "file_spec_not_found"
    assert empty.status == ElementVerificationStatus.NOT_APPLICABLE
    assert empty.reason == "no_elements_declared"


def test_absolute_or_parent_traversal_path_is_unavailable():
    manifest = _manifest("src/proof.py")

    absolute = verify_forward_manifest_elements(
        manifest,
        "/src/proof.py",
        "def expected_symbol():\n    pass\n",
    )
    traversal = verify_forward_manifest_elements(
        manifest,
        "../src/proof.py",
        "def expected_symbol():\n    pass\n",
    )

    assert absolute.status == ElementVerificationStatus.VERIFICATION_UNAVAILABLE
    assert absolute.reason == "invalid_file_path"
    assert traversal.status == ElementVerificationStatus.VERIFICATION_UNAVAILABLE
    assert traversal.reason == "invalid_file_path"


def test_import_contracts_are_outside_the_element_evidence_boundary():
    manifest = _manifest("src/proof.py")
    spec = manifest.file_specs["src/proof.py"].model_copy(
        update={
            "imports": [
                ForwardImportSpec(kind="from", module="missing_package", names=["x"])
            ]
        }
    )
    manifest = ForwardManifest(file_specs={"src/proof.py": spec})

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.py",
        "def expected_symbol():\n    pass\n",
    )

    assert result.status == ElementVerificationStatus.VERIFIED
    assert result.issues == []


def test_advisory_parser_keeps_violation_tier():
    manifest = ForwardManifest(
        file_specs={
            "src/proof.ts": ForwardFileSpec(
                file="src/proof.ts",
                elements=[
                    ForwardElementSpec(kind=ElementKind.CLASS, name="Expected")
                ],
            )
        }
    )

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.ts",
        "export class Other {}\n",
    )

    assert result.status == ElementVerificationStatus.VIOLATED
    assert result.finding_severity == "warning"
    assert result.parser_tier == "advisory"
    assert result.issues[0].severity == "warning"
    assert result.issues[0].tier == "advisory"


def test_same_name_with_wrong_kind_is_not_verified():
    manifest = ForwardManifest(
        file_specs={
            "src/proof.py": ForwardFileSpec(
                file="src/proof.py",
                elements=[
                    ForwardElementSpec(kind=ElementKind.CLASS, name="Widget")
                ],
            )
        }
    )

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.py",
        "def Widget():\n    pass\n",
    )

    assert result.status == ElementVerificationStatus.VIOLATED
    assert result.issues[0].violation_type == "wrong_element_kind"


def test_coarse_function_kind_accepts_async_source_shape():
    result = verify_forward_manifest_elements(
        _manifest("src/proof.py", name="run"),
        "src/proof.py",
        "async def run():\n    return True\n",
    )

    assert result.status == ElementVerificationStatus.VERIFIED


def test_explicit_async_function_promise_remains_exact():
    manifest = ForwardManifest(
        file_specs={
            "src/proof.py": ForwardFileSpec(
                file="src/proof.py",
                elements=[
                    ForwardElementSpec(
                        kind=ElementKind.ASYNC_FUNCTION,
                        name="run",
                        signature={"params": []},
                    )
                ],
            )
        }
    )

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.py",
        "def run():\n    return True\n",
    )

    assert result.status == ElementVerificationStatus.VIOLATED
    assert result.issues[0].violation_type == "wrong_element_kind"


def test_coarse_method_kind_accepts_property_source_shape():
    manifest = ForwardManifest(
        file_specs={
            "src/proof.py": ForwardFileSpec(
                file="src/proof.py",
                elements=[
                    ForwardElementSpec(
                        kind=ElementKind.METHOD,
                        name="value",
                        parent_class="Order",
                        signature={"params": []},
                    )
                ],
            )
        }
    )

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.py",
        "class Order:\n    @property\n    def value(self):\n        return 1\n",
    )

    assert result.status == ElementVerificationStatus.VERIFIED


def test_constant_promise_accepts_parser_class_variable_shape():
    manifest = ForwardManifest(
        file_specs={
            "src/proof.py": ForwardFileSpec(
                file="src/proof.py",
                elements=[
                    ForwardElementSpec(
                        kind=ElementKind.CONSTANT,
                        name="MAX_RETRIES",
                        parent_class="Config",
                    )
                ],
            )
        }
    )

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.py",
        "class Config:\n    MAX_RETRIES = 3\n",
    )

    assert result.status == ElementVerificationStatus.VERIFIED


def test_struct_promise_accepts_advisory_go_class_projection():
    manifest = ForwardManifest(
        file_specs={
            "main.go": ForwardFileSpec(
                file="main.go",
                elements=[
                    ForwardElementSpec(kind=ElementKind.STRUCT, name="Server")
                ],
            )
        }
    )

    result = verify_forward_manifest_elements(
        manifest,
        "main.go",
        "package main\n\ntype Server struct{}\n",
    )

    assert result.status == ElementVerificationStatus.VERIFIED


def test_method_must_belong_to_the_prescribed_parent():
    manifest = ForwardManifest(
        file_specs={
            "src/proof.py": ForwardFileSpec(
                file="src/proof.py",
                elements=[
                    ForwardElementSpec(
                        kind=ElementKind.METHOD,
                        name="save",
                        parent_class="Order",
                        signature={"params": []},
                    )
                ],
            )
        }
    )

    result = verify_forward_manifest_elements(
        manifest,
        "src/proof.py",
        "class Cart:\n    def save(self):\n        pass\n",
    )

    assert result.status == ElementVerificationStatus.VIOLATED
    assert result.expected_elements[0].parent_class == "Order"
    assert result.issues[0].violation_type == "wrong_parent_class"
