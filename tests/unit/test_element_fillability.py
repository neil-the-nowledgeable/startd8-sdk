"""Tests for RUN-007 FR-0/FR-1/FR-5 fillability + empty-stub predicates (Step 1)."""

import pytest

from startd8.utils.code_manifest import ElementKind
from startd8.element_fillability import (
    spec_fillable_elements,
    is_fillable_spec,
    is_empty_fillable_spec,
    is_empty_stem_type_artifact,
)
from startd8.exceptions import MissingTemplateError, Startd8Error


def _el(kind, name, **kw):
    """Minimal element dict (the predicate accepts dicts or objects)."""
    return {"kind": kind.value if hasattr(kind, "value") else kind, "name": name, **kw}


# ---------------------------------------------------------------------------
# FR-0: positive fillability matrix over every ElementKind
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFillabilityMatrix:
    DIRECTLY_FILLABLE = [
        ElementKind.FUNCTION, ElementKind.ASYNC_FUNCTION,
        ElementKind.METHOD, ElementKind.ASYNC_METHOD,
        ElementKind.PROPERTY, ElementKind.CONSTANT, ElementKind.VARIABLE,
        ElementKind.FIELD, ElementKind.DEFAULT_EXPORT,
    ]
    STRUCTURAL_TYPES = [
        ElementKind.CLASS, ElementKind.STRUCT, ElementKind.INTERFACE,
        ElementKind.ENUM, ElementKind.RECORD,
    ]

    @pytest.mark.parametrize("kind", DIRECTLY_FILLABLE)
    def test_directly_fillable_kinds_make_spec_nonempty(self, kind):
        assert is_fillable_spec([_el(kind, "x")]) is True
        assert is_empty_fillable_spec([_el(kind, "x")]) is False

    @pytest.mark.parametrize("kind", STRUCTURAL_TYPES)
    def test_member_less_type_is_not_fillable(self, kind):
        # An empty CLASS/STRUCT/INTERFACE/ENUM/RECORD with no members → empty spec
        assert is_empty_fillable_spec([_el(kind, "Thing")]) is True

    @pytest.mark.parametrize("kind", STRUCTURAL_TYPES)
    def test_type_with_members_is_fillable(self, kind):
        spec = [_el(kind, "Thing"), _el(ElementKind.METHOD, "do_it", parent_class="Thing")]
        assert is_empty_fillable_spec(spec) is False
        # the member itself is fillable, and the type now counts too
        fillable_names = {_el_name(e) for e in spec_fillable_elements(spec)}
        assert "do_it" in fillable_names and "Thing" in fillable_names

    def test_type_alias_is_never_fillable(self):
        assert is_empty_fillable_spec([_el(ElementKind.TYPE_ALIAS, "MyAlias")]) is True

    def test_registry_default_export_is_fillable(self):
        # next.config.mjs registry path → DEFAULT_EXPORT → NOT empty (preserve $0.00)
        assert is_empty_fillable_spec([_el(ElementKind.DEFAULT_EXPORT, "config")]) is False

    def test_unknown_kind_is_not_fillable(self):
        assert is_empty_fillable_spec([{"kind": "nonsense", "name": "x"}]) is True


# ---------------------------------------------------------------------------
# FR-1: the run-007 trigger — empty-fillable spec from the deriver
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRun007EmptySpec:
    def test_class_only_spec_is_empty(self):
        # the exact run-007 shape: a lone member-less CLASS named after the stem
        assert is_empty_fillable_spec([_el(ElementKind.CLASS, "value-model")]) is True

    def test_deriver_output_for_value_model_is_empty_fillable(self):
        # integration with the actual OQ-1 synthesizer
        from startd8.seeds.element_deriver import derive_elements_for_file
        els, _ = derive_elements_for_file("lib/value-model.ts", contracts=None)
        assert len(els) == 1 and els[0]["kind"] == "class"
        assert is_empty_fillable_spec(els) is True

    def test_empty_element_list_is_empty(self):
        assert is_empty_fillable_spec([]) is True


# ---------------------------------------------------------------------------
# FR-2: MissingTemplateError refusal type
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMissingTemplateError:
    def test_is_startd8_error_with_attribution(self):
        err = MissingTemplateError("no template", file_path="lib/value-model.ts", feature_id="PI-011")
        assert isinstance(err, Startd8Error)
        assert err.file_path == "lib/value-model.ts"
        assert err.feature_id == "PI-011"
        assert err.root_cause == "empty_spec_refusal"
        assert err.pipeline_stage == "micro_prime_escalation"


# ---------------------------------------------------------------------------
# FR-5: empty-stem-type artifact detector (Step 6 extends the FP matrix)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEmptyStemTypeArtifact:
    @pytest.mark.parametrize("path,content", [
        ("lib/env.ts", "\nexport class env {\n\n}\n"),
        ("lib/db.ts", "\nexport class db {\n\n}\n"),
        ("app/layout.tsx", "\nexport class layout {\n\n}\n"),
        ("app/page.tsx", "\nexport class page {\n\n}\n"),
        ("lib/value-model.ts", "\nexport class value-model {\n\n}\n"),  # hyphen
        ("app/api/profile/route.ts", "\nexport class route {\n\n}\n"),
    ])
    def test_run007_stub_shapes_flagged(self, path, content):
        assert is_empty_stem_type_artifact(path, content) is True

    def test_pascalcase_and_go_struct_match_stem(self):
        # Go assembler PascalCases the stem
        assert is_empty_stem_type_artifact("model/value-model.go", "package model\n\ntype ValueModel struct {\n}\n") is True
        assert is_empty_stem_type_artifact("model/widget.go", "package model\ntype Widget struct {}\n") is True

    def test_stub_with_imports_still_flagged(self):
        content = "import { x } from './x'\n\nexport class env {\n}\n"
        assert is_empty_stem_type_artifact("lib/env.ts", content) is True

    def test_real_class_with_members_not_flagged(self):
        content = "export class Env {\n  get() { return 1 }\n}\n"
        assert is_empty_stem_type_artifact("lib/Env.ts", content) is False

    def test_barrel_export_not_flagged(self):
        assert is_empty_stem_type_artifact("lib/index.ts", "export * from './a'\nexport * from './b'\n") is False

    def test_function_module_not_flagged(self):
        assert is_empty_stem_type_artifact("lib/util.ts", "export function util() { return 1 }\n") is False

    def test_name_mismatch_not_flagged(self):
        # empty class whose name != file stem is not the basename-stub shape
        assert is_empty_stem_type_artifact("lib/env.ts", "export class Something {}\n") is False

    def test_empty_file_not_flagged(self):
        assert is_empty_stem_type_artifact("lib/env.ts", "") is False


def _el_name(e):
    return e["name"] if isinstance(e, dict) else getattr(e, "name", None)
