"""Inc 4 — scaffold lever tests (FR-5/FR-6, R3-S2 confinement, R2-S2 barrel)."""

from __future__ import annotations

from pathlib import Path

from startd8.repair.retry.scaffold import scaffold_barrel, scaffold_cofile


# ── cofile ───────────────────────────────────────────────────────────────────

def test_scaffold_cofile_creates_empty_css_when_missing(tmp_path):
    gen = tmp_path / "generated"
    (gen / "components" / "wizard").mkdir(parents=True)
    importer = gen / "components" / "wizard" / "StepNav.tsx"
    importer.write_text("import './StepNav.module.css'\n")
    created = scaffold_cofile(importer, "./StepNav.module.css", gen)
    assert created is not None and created.is_file()
    assert created.name == "StepNav.module.css"
    assert "TODO" in created.read_text()


def test_scaffold_cofile_never_overwrites(tmp_path):
    gen = tmp_path / "generated"
    (gen / "c").mkdir(parents=True)
    importer = gen / "c" / "X.tsx"
    importer.write_text("x")
    existing = gen / "c" / "X.module.css"
    existing.write_text(".real { color: red }\n")
    assert scaffold_cofile(importer, "./X.module.css", gen) is None
    assert existing.read_text() == ".real { color: red }\n"  # untouched


def test_scaffold_cofile_refuses_to_escape_run_tree(tmp_path):
    gen = tmp_path / "generated"
    (gen / "deep" / "a").mkdir(parents=True)
    importer = gen / "deep" / "a" / "X.tsx"
    importer.write_text("x")
    # ../../../../etc/evil.module.css escapes generated/
    created = scaffold_cofile(importer, "../../../../evil.module.css", gen)
    assert created is None
    assert not (tmp_path / "evil.module.css").exists()


def test_scaffold_cofile_alias_form(tmp_path):
    gen = tmp_path / "generated"
    (gen / "components").mkdir(parents=True)
    importer = gen / "components" / "Card.tsx"
    importer.write_text("x")
    created = scaffold_cofile(importer, "@/components/Card.module.css", gen)
    assert created is not None and created.name == "Card.module.css"


# ── barrel ───────────────────────────────────────────────────────────────────

def test_scaffold_barrel_reexports_default_steps(tmp_path):
    gen = tmp_path / "generated"
    steps = gen / "components" / "wizard" / "steps"
    steps.mkdir(parents=True)
    for name in ("EnrichStep", "ProofPointStep", "ProfileStep"):
        (steps / f"{name}.tsx").write_text(f"export default function {name}() {{ return null }}\n")
    index = scaffold_barrel(steps, gen)
    assert index is not None and index.name == "index.ts"
    text = index.read_text()
    assert "export { default as EnrichStep } from './EnrichStep';" in text
    assert "export { default as ProofPointStep } from './ProofPointStep';" in text
    assert "export *" not in text  # never a blind star


def test_scaffold_barrel_skips_when_index_exists(tmp_path):
    gen = tmp_path / "generated"
    steps = gen / "steps"
    steps.mkdir(parents=True)
    (steps / "A.tsx").write_text("export default function A(){return null}\n")
    (steps / "index.ts").write_text("export {}\n")
    assert scaffold_barrel(steps, gen) is None


def test_scaffold_barrel_drops_colliding_named_export(tmp_path):
    gen = tmp_path / "generated"
    steps = gen / "steps"
    steps.mkdir(parents=True)
    # two siblings both export `helper` -> that name must be dropped (collision)
    (steps / "A.ts").write_text("export const helper = 1\nexport const aOnly = 2\n")
    (steps / "B.ts").write_text("export const helper = 3\nexport const bOnly = 4\n")
    index = scaffold_barrel(steps, gen)
    assert index is not None
    text = index.read_text()
    assert "aOnly" in text and "bOnly" in text
    assert "helper" not in text  # colliding name dropped, not blindly re-exported


def test_scaffold_barrel_abstains_when_nothing_safe(tmp_path):
    gen = tmp_path / "generated"
    steps = gen / "steps"
    steps.mkdir(parents=True)
    # only an export * (un-nameable by the regex extractor) -> abstain
    (steps / "A.ts").write_text("export * from './somewhere'\n")
    assert scaffold_barrel(steps, gen) is None
