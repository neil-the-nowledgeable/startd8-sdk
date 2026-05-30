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

    def test_non_python_file_skipped(self):
        """The structural validator is Python-AST-based; non-.py files degrade to no-op."""
        fm = ForwardManifest(
            file_specs={
                "next.config.mjs": _spec("next.config.mjs", "config"),
            }
        )
        # No false 'missing config' violation for a JS file we cannot AST-parse.
        assert fm.validate_implementation("export default {}\n", ["next.config.mjs"]) == []

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
