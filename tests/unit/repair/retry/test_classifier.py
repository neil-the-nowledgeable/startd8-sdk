"""Inc 2 — TargetExistenceSearch + classifier tests (FR-3).

These run with **no Inc 3 code present** (R1-S1): the classifier consumes only the
`TargetExistenceSearch` over an on-disk fixture tree mirroring run-012's generated
surface (the 6 `.tsx` + `types.ts`, missing the 3 CSS co-files + the steps barrel).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.repair.retry.classifier import RetryClass, classify
from startd8.repair.retry.models import RetryViolation
from startd8.repair.retry.search import DiskTargetSearch, specifier_tokens


@pytest.fixture
def run012_tree(tmp_path):
    """A faithful run-012 generated surface: components exist, co-files/barrel don't."""
    gen = tmp_path / "generated"
    (gen / "components" / "wizard" / "steps").mkdir(parents=True)
    # shared types (PI-006, succeeded) — the real rewrite target for #4
    (gen / "components" / "wizard" / "types.ts").write_text("export type Wizard = {}\n")
    # components that exist
    for rel in [
        "components/wizard/StepNav.tsx",
        "components/wizard/WizardShell.tsx",
        "components/wizard/WizardSteps.tsx",
        "components/ModeToggle.tsx",
        "components/wizard/steps/EnrichStep.tsx",
        "components/wizard/steps/ProofPointStep.tsx",
        "components/wizard/steps/ProfileStep.tsx",
    ]:
        (gen / rel).write_text("export default function C() { return null }\n")
    return gen


def _v(feature_id, importer, specifier):
    return RetryViolation(
        feature_id=feature_id,
        file_path=importer,
        category="unresolvable_import",
        specifier=specifier,
        message="",
    )


# ── the run-012 five ────────────────────────────────────────────────────────

def test_pi012_relative_wrongpath_is_rewritable(run012_tree):
    """#4: ../../../types/wizard → the one on-disk module containing {types, wizard}."""
    search = DiskTargetSearch(run012_tree)
    v = _v("PI-012", "components/wizard/steps/EnrichStep.tsx", "../../../types/wizard")
    res = classify(v, search)
    assert res.retry_class == RetryClass.REWRITABLE_PATH
    assert res.target.name == "types.ts"
    assert res.target.parent.name == "wizard"


@pytest.mark.parametrize("fid,importer,spec", [
    ("PI-007", "components/wizard/StepNav.tsx", "./StepNav.module.css"),
    ("PI-005", "components/ModeToggle.tsx", "./ModeToggle.module.css"),
    ("PI-011", "components/wizard/steps/ProofPointStep.tsx", "./ProofPointStep.module.css"),
])
def test_missing_css_is_scaffoldable_cofile(run012_tree, fid, importer, spec):
    search = DiskTargetSearch(run012_tree)
    res = classify(_v(fid, importer, spec), search)
    assert res.retry_class == RetryClass.SCAFFOLDABLE_COFILE
    assert res.target.name.endswith(".module.css")


def test_pi008_directory_import_is_scaffoldable_barrel(run012_tree):
    """#5: @/components/wizard/steps resolves to a dir with siblings, no index."""
    search = DiskTargetSearch(run012_tree)
    v = _v("PI-008", "components/wizard/WizardShell.tsx", "@/components/wizard/steps")
    res = classify(v, search)
    assert res.retry_class == RetryClass.SCAFFOLDABLE_BARREL
    assert res.target.name == "steps" and res.target.is_dir()


def test_full_run012_set_is_1_rewrite_3_cofile_1_barrel_0_regen(run012_tree):
    search = DiskTargetSearch(run012_tree)
    fives = [
        _v("PI-012", "components/wizard/steps/EnrichStep.tsx", "../../../types/wizard"),
        _v("PI-007", "components/wizard/StepNav.tsx", "./StepNav.module.css"),
        _v("PI-005", "components/ModeToggle.tsx", "./ModeToggle.module.css"),
        _v("PI-011", "components/wizard/steps/ProofPointStep.tsx", "./ProofPointStep.module.css"),
        _v("PI-008", "components/wizard/WizardShell.tsx", "@/components/wizard/steps"),
    ]
    classes = [classify(v, search).retry_class for v in fives]
    assert classes.count(RetryClass.REWRITABLE_PATH) == 1
    assert classes.count(RetryClass.SCAFFOLDABLE_COFILE) == 3
    assert classes.count(RetryClass.SCAFFOLDABLE_BARREL) == 1
    assert classes.count(RetryClass.NEEDS_REGEN) == 0


# ── edge / safety cases ──────────────────────────────────────────────────────

def test_ambiguous_two_matches_is_needs_regen(tmp_path):
    gen = tmp_path / "generated"
    (gen / "a").mkdir(parents=True)
    (gen / "b").mkdir(parents=True)
    (gen / "a" / "widget.ts").write_text("export const x = 1\n")
    (gen / "b" / "widget.ts").write_text("export const x = 1\n")
    search = DiskTargetSearch(gen)
    res = classify(_v("PI-X", "c/Foo.tsx", "../widget"), search)
    assert res.retry_class == RetryClass.NEEDS_REGEN
    assert res.reason == "ambiguous_target"
    assert len(res.candidates) == 2


def test_absent_module_is_needs_regen(run012_tree):
    search = DiskTargetSearch(run012_tree)
    res = classify(_v("PI-Y", "components/X.tsx", "@/totally/unrelated/thing"), search)
    assert res.retry_class == RetryClass.NEEDS_REGEN
    assert res.reason == "absent"


def test_unparseable_violation_is_needs_regen(run012_tree):
    search = DiskTargetSearch(run012_tree)
    v = RetryViolation("PI-Z", "components/X.tsx", "unresolvable_import", "", "garbled", parse_ok=False)
    res = classify(v, search)
    assert res.retry_class == RetryClass.NEEDS_REGEN
    assert res.reason == "unparseable_message"


def test_css_stays_cofile_even_if_a_stray_match_exists(tmp_path):
    """FR-3 precedence: a style/asset specifier is cofile by extension, not a rewrite."""
    gen = tmp_path / "generated"
    (gen / "components").mkdir(parents=True)
    (gen / "components" / "Card.tsx").write_text("export default function C(){return null}\n")
    # a stray module whose path segments would token-match 'card'
    (gen / "components" / "card.ts").write_text("export const card = 1\n")
    search = DiskTargetSearch(gen)
    res = classify(_v("PI-W", "components/Card.tsx", "./Card.module.css"), search)
    assert res.retry_class == RetryClass.SCAFFOLDABLE_COFILE


def test_barrel_with_existing_index_is_not_scaffoldable(tmp_path):
    gen = tmp_path / "generated"
    (gen / "components" / "steps").mkdir(parents=True)
    (gen / "components" / "steps" / "A.tsx").write_text("export default function A(){return null}\n")
    (gen / "components" / "steps" / "index.ts").write_text("export {}\n")
    search = DiskTargetSearch(gen)
    # already has index -> not a barrel scaffold; falls through to needs_regen (no module match)
    res = classify(_v("PI-V", "components/Shell.tsx", "@/components/steps"), search)
    assert res.retry_class != RetryClass.SCAFFOLDABLE_BARREL


# ── token heuristic (the shared predicate, R3-F3) ───────────────────────────

def test_specifier_tokens_strips_dots_at_and_ext():
    assert specifier_tokens("../../../types/wizard") == ["types", "wizard"]
    assert specifier_tokens("@/components/wizard/steps") == ["components", "wizard", "steps"]
    assert specifier_tokens("./StepNav") == ["StepNav"]
