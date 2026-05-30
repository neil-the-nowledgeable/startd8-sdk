"""Tests for ForwardManifest.validate_implementation — the canonical FR-3 enforcement path.

This is the real method that replaced the phantom ``validate_implementation`` reference
(see FORWARD_MANIFEST_DRAFT_TIME_REQUIREMENTS.md FR-3). It validates multiple Python files
from one drafted blob, plus task-scoped interface contracts.
"""

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.utils.code_manifest import ElementKind


def _spec(path, *element_names):
    return ForwardFileSpec(
        file=path,
        elements=[
            ForwardElementSpec(kind=ElementKind.CONSTANT, name=n) for n in element_names
        ],
    )


class TestFileSpecValidation:
    def test_single_file_present_element_no_violation(self):
        fm = ForwardManifest(file_specs={"mod.py": _spec("mod.py", "EXPECTED")})
        assert fm.validate_implementation("EXPECTED = 1\n", ["mod.py"]) == []

    def test_single_file_missing_element(self):
        fm = ForwardManifest(file_specs={"mod.py": _spec("mod.py", "EXPECTED")})
        viols = fm.validate_implementation("x = 1\n", ["mod.py"])
        assert [v.violation_type for v in viols] == ["missing_constant"]
        assert viols[0].file_path == "mod.py"

    def test_multi_file_blob_split_and_validated_per_file(self):
        """The big completeness win: one blob, multiple Python files, per-file specs."""
        fm = ForwardManifest(
            file_specs={
                "a.py": _spec("a.py", "ALPHA"),
                "b.py": _spec("b.py", "BETA"),
            }
        )
        blob = "# a.py\nALPHA = 1\n\n# b.py\nBETA = 2\n"
        assert fm.validate_implementation(blob, ["a.py", "b.py"]) == []

    def test_multi_file_violation_attributes_to_correct_file(self):
        """No cross-file false positives: a missing element flags only its own file."""
        fm = ForwardManifest(
            file_specs={
                "a.py": _spec("a.py", "ALPHA"),
                "b.py": _spec("b.py", "BETA"),
            }
        )
        blob = "# a.py\nALPHA = 1\n\n# b.py\nWRONG = 2\n"
        viols = fm.validate_implementation(blob, ["a.py", "b.py"])
        assert len(viols) == 1
        assert viols[0].violation_type == "missing_constant"
        assert viols[0].file_path == "b.py"

    def test_dict_input_accepted(self):
        fm = ForwardManifest(
            file_specs={"a.py": _spec("a.py", "ALPHA"), "b.py": _spec("b.py", "BETA")}
        )
        assert (
            fm.validate_implementation(
                {"a.py": "ALPHA=1\n", "b.py": "BETA=2\n"}, ["a.py", "b.py"]
            )
            == []
        )

    def test_no_target_files_returns_empty(self):
        """A bare blob with no target files cannot be attributed to a spec."""
        fm = ForwardManifest(file_specs={"mod.py": _spec("mod.py", "EXPECTED")})
        assert fm.validate_implementation("x = 1\n") == []

    def test_non_python_supported_language_now_enforced_advisory(self):
        """Post-MULTILANG FR-6: supported non-Python files (.mjs) are now element-enforced via
        the node adapter, at the ADVISORY tier — a missing element is a WARNING (never blocks),
        not silently skipped. (Pre-P5 this returned [] because non-.py was skipped entirely.)"""
        fm = ForwardManifest(
            file_specs={"next.config.mjs": _spec("next.config.mjs", "config")}
        )
        # 'config' (a CONSTANT spec) is absent from an anonymous `export default {}` (whose
        # only element is DEFAULT_EXPORT name="default") -> one advisory warning, never an error.
        viols = fm.validate_implementation("export default {}\n", ["next.config.mjs"])
        assert len(viols) == 1
        assert viols[0].severity == "warning"
        assert viols[0].tier == "advisory"

    def test_parse_error_degrades_to_empty(self):
        fm = ForwardManifest(file_specs={"mod.py": _spec("mod.py", "EXPECTED")})
        assert fm.validate_implementation("def (:\n  broken", ["mod.py"]) == []


class TestContractScoping:
    def _fm_with_contract(self):
        return ForwardManifest(
            file_specs={"mod.py": ForwardFileSpec(file="mod.py", elements=[])},
            contracts=[
                InterfaceContract(
                    contract_id="c1",
                    category=ContractCategory.FUNCTION_NAME,
                    confidence=ContractConfidence.EXPLICIT,
                    description="must define needed()",
                    binding_text="def needed()",
                    function_name="needed",
                    applicable_task_ids=["t1"],
                )
            ],
        )

    def test_contract_validated_when_task_scoped(self):
        fm = self._fm_with_contract()
        viols = fm.validate_implementation("x = 1\n", ["mod.py"], task_id="t1")
        assert "missing_function" in [v.violation_type for v in viols]

    def test_contract_skipped_without_task_id(self):
        """Without a task_id the relevant contract subset is unknown — skip, don't
        validate project-wide against a single draft (would false-flag undrafted symbols)."""
        fm = self._fm_with_contract()
        assert fm.validate_implementation("x = 1\n", ["mod.py"], task_id=None) == []

    def test_contract_skipped_when_include_contracts_false(self):
        fm = self._fm_with_contract()
        assert (
            fm.validate_implementation(
                "x = 1\n", ["mod.py"], task_id="t1", include_contracts=False
            )
            == []
        )

    def test_contract_not_applicable_to_task_skipped(self):
        fm = self._fm_with_contract()  # contract applies to t1 only
        assert fm.validate_implementation("x = 1\n", ["mod.py"], task_id="t2") == []


class TestMultiLanguageEnforcement:
    """MULTILANG FR-6: validate_implementation now enforces non-Python files via
    build_multilang_file_manifest, with tier-calibrated severity (advisory = warning)."""

    def test_typescript_present_class_clean(self):
        fm = ForwardManifest(
            file_specs={
                "app.ts": ForwardFileSpec(
                    file="app.ts",
                    elements=[ForwardElementSpec(kind=ElementKind.CLASS, name="Greeter")],
                )
            }
        )
        assert fm.validate_implementation(
            "export class Greeter {}\n", target_files=["app.ts"]
        ) == []

    def test_typescript_missing_element_is_warning(self):
        fm = ForwardManifest(
            file_specs={
                "app.ts": ForwardFileSpec(
                    file="app.ts",
                    elements=[ForwardElementSpec(kind=ElementKind.CLASS, name="Missing")],
                )
            }
        )
        viols = fm.validate_implementation(
            "export class Greeter {}\n", target_files=["app.ts"]
        )
        assert len(viols) == 1
        assert viols[0].severity == "warning"   # advisory (regex) tier — never blocks
        assert viols[0].tier == "advisory"

    def test_go_missing_element_is_warning(self):
        fm = ForwardManifest(
            file_specs={
                "svc.go": ForwardFileSpec(
                    file="svc.go",
                    elements=[ForwardElementSpec(kind=ElementKind.CLASS, name="Absent")],
                )
            }
        )
        viols = fm.validate_implementation(
            'package main\nfunc Hello() {}\n', target_files=["svc.go"]
        )
        assert len(viols) == 1 and viols[0].severity == "warning"

    def test_mixed_python_and_go_per_file(self):
        # Dict input, two languages: Python authoritative (error), Go advisory (warning).
        fm = ForwardManifest(
            file_specs={
                "a.py": ForwardFileSpec(
                    file="a.py",
                    elements=[ForwardElementSpec(kind=ElementKind.CONSTANT, name="MISSING_PY")],
                ),
                "svc.go": ForwardFileSpec(
                    file="svc.go",
                    elements=[ForwardElementSpec(kind=ElementKind.CLASS, name="MissingGo")],
                ),
            }
        )
        viols = fm.validate_implementation(
            {"a.py": "X = 1\n", "svc.go": "package main\nfunc F() {}\n"},
            target_files=["a.py", "svc.go"],
        )
        by_file = {v.file_path: v for v in viols}
        assert by_file["a.py"].severity == "error"      # Python = authoritative
        assert by_file["svc.go"].severity == "warning"  # Go = advisory

    def test_unsupported_language_skipped_no_false_error(self):
        # An unsupported language (.rs) has no element extractor -> tier None -> skipped,
        # so its spec elements are NOT false-flagged as missing errors (FR-6 regression guard).
        fm = ForwardManifest(
            file_specs={
                "main.rs": ForwardFileSpec(
                    file="main.rs",
                    elements=[ForwardElementSpec(kind=ElementKind.CLASS, name="Whatever")],
                )
            }
        )
        assert fm.validate_implementation(
            "fn main() {}\n", target_files=["main.rs"]
        ) == []
