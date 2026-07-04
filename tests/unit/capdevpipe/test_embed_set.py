"""Golden-fixture tests for the manifest-driven cap-dev-pipe embed set (FR-5, FR-16).

The embed inventory is resolved from ``embed-manifest.yaml`` via the shared cap-dev-pipe
planner (``pipeline/embed_manifest.py``). These tests:

1. pin the ``full`` profile against a frozen golden fixture (always runs, no external
   dependency), and
2. when the canonical checkout is present, cross-check the fixture against the live
   manifest — the drift signal (skipped when the source is absent, e.g. CI without the
   checkout).

The D-10 regression — a glob would wrongly capture ``run-compare.sh`` / ``run-clean-*.sh`` /
``run-kaizen-*.sh`` / ``create-project-wrapper.sh`` / ``prime-show-postmortem.py`` /
``resolve-questions.py`` — is guarded explicitly.
"""

import pytest

from startd8.capdevpipe_embed_manifest import DEFAULT_EMBED_PROFILE, resolve_embed_inventory
from startd8.capdevpipe_installer import DEFAULT_SOURCE, parse_canonical_embed_scripts

pytestmark = pytest.mark.unit


# Frozen golden fixture — the canonical ``full`` profile from embed-manifest.yaml.
# Update when the manifest legitimately changes — see scripts/regen_capdevpipe_embed_fixture.py.
GOLDEN_SCRIPTS = {
    "run.sh",
    "run-atomic.sh",
    "run-cap-delivery.sh",
    "run-plan-ingestion.sh",
    "run-prime-contractor.sh",
    "run-artisan.sh",
    "clean-prior-run.sh",
    "resolve-provenance.py",
    "resolve-project-root.py",
    "enrich-seed.py",
    "prime-list-tasks.py",
    "prime-post-run.py",
    "explain-pipeline.py",
    "explain-content.yaml",
}

GOLDEN_ALIASES = {
    "resolve_provenance.py",
    "enrich_seed.py",
    "prime_post_run.py",
}

GOLDEN_RESOURCE_TREES = {"design", "prompts"}
GOLDEN_PACKAGES = {"pipeline"}
GOLDEN_COPY_FILES = {"project-cap-dlv-pipe.sh.template"}

# Source scripts that exist in the canonical checkout but are deliberately NOT embedded.
KNOWN_NON_EMBEDDED = {
    "run-compare.sh",
    "run-clean-target.sh",
    "run-clean-kaizen.sh",
    "run-kaizen-correlation.sh",
    "run-kaizen-trends.sh",
    "create-project-wrapper.sh",
    "prime-show-postmortem.py",
    "resolve-questions.py",
    "kaizen-correlation.py",
    "kaizen-trends.py",
    "new-cnvrg-rvw-prmpt.sh",
    "install-cap-dev-pipe.sh",
}


def _full_inventory_from(source):
    return resolve_embed_inventory(source, DEFAULT_EMBED_PROFILE)


class TestEmbedSetGoldenFixture:
    """Set-equality against the frozen fixture (always runs)."""

    def test_scripts_match_golden_fixture(self):
        assert set(GOLDEN_SCRIPTS) == GOLDEN_SCRIPTS

    def test_aliases_match_golden_fixture(self):
        assert set(GOLDEN_ALIASES) == GOLDEN_ALIASES

    def test_full_profile_script_and_alias_count(self):
        assert len(GOLDEN_SCRIPTS) + len(GOLDEN_ALIASES) == 17

    def test_no_duplicates_in_golden(self):
        assert len(GOLDEN_SCRIPTS) == len(set(GOLDEN_SCRIPTS))
        assert len(GOLDEN_ALIASES) == len(set(GOLDEN_ALIASES))

    def test_scripts_and_aliases_disjoint(self):
        assert GOLDEN_SCRIPTS.isdisjoint(GOLDEN_ALIASES)

    def test_resolve_questions_excluded(self):
        assert "resolve-questions.py" not in GOLDEN_SCRIPTS
        assert "resolve-questions.py" not in GOLDEN_ALIASES

    def test_no_known_non_embedded_script_leaks_in(self):
        leaked = KNOWN_NON_EMBEDDED & (GOLDEN_SCRIPTS | GOLDEN_ALIASES)
        assert not leaked, f"non-embedded source scripts leaked into embed set: {leaked}"


class TestManifestResolutionAgainstGolden:
    """Resolve the bundled/live manifest and compare to the frozen golden sets."""

    def test_fixture_manifest_full_profile_matches_golden(self, tmp_path):
        from tests.unit.capdevpipe.conftest import seed_embed_inventory_files

        src = tmp_path / "cap-dev-pipe"
        src.mkdir()
        seed_embed_inventory_files(src)
        inv = _full_inventory_from(src)
        assert set(inv.scripts) == GOLDEN_SCRIPTS
        assert set(inv.python_aliases) == GOLDEN_ALIASES
        assert set(inv.resource_trees) == GOLDEN_RESOURCE_TREES
        assert set(inv.packages) == GOLDEN_PACKAGES
        assert set(inv.copy_files) == GOLDEN_COPY_FILES


class TestCanonicalParser:
    """Pure parsing of the CLAUDE.md ln -s block (legacy cross-check)."""

    SAMPLE = (
        "## Embedding in a Project\n"
        "```bash\n"
        "mkdir -p .cap-dev-pipe\n"
        "cd .cap-dev-pipe\n"
        "CAP_DEV_PIPE=~/Documents/dev/cap-dev-pipe\n"
        "ln -s $CAP_DEV_PIPE/run.sh\n"
        "ln -s $CAP_DEV_PIPE/explain-content.yaml\n"
        "```\n"
        "Create language profile directories:\n"
        "```bash\n"
        'ln -sf "../../PLAN.md" java-plan.md\n'
        "```\n"
    )

    def test_parses_only_cap_dev_pipe_ln_lines(self):
        assert parse_canonical_embed_scripts(self.SAMPLE) == [
            "run.sh",
            "explain-content.yaml",
        ]

    def test_ignores_relative_profile_symlinks(self):
        assert "java-plan.md" not in parse_canonical_embed_scripts(self.SAMPLE)


@pytest.mark.skipif(
    not (DEFAULT_SOURCE / "embed-manifest.yaml").is_file(),
    reason="canonical cap-dev-pipe checkout not present (drift check skipped)",
)
class TestLiveDriftAgainstCanonicalSource:
    """Drift signal: cross-check golden fixture against the live manifest."""

    def test_full_profile_scripts_match_manifest(self):
        inv = _full_inventory_from(DEFAULT_SOURCE)
        assert set(inv.scripts) == GOLDEN_SCRIPTS, (
            "GOLDEN_SCRIPTS drifted from embed-manifest.yaml full profile; "
            "regenerate via scripts/regen_capdevpipe_embed_fixture.py and review the diff"
        )

    def test_full_profile_aliases_match_manifest(self):
        inv = _full_inventory_from(DEFAULT_SOURCE)
        assert set(inv.python_aliases) == GOLDEN_ALIASES

    def test_every_embedded_script_exists_in_source(self):
        missing = [s for s in GOLDEN_SCRIPTS if not (DEFAULT_SOURCE / s).is_file()]
        assert not missing, f"embedded scripts missing from source: {missing}"

    def test_every_alias_exists_in_source(self):
        missing = [a for a in GOLDEN_ALIASES if not (DEFAULT_SOURCE / a).is_file()]
        assert not missing, f"underscore aliases missing from source: {missing}"

    def test_claude_md_script_set_matches_manifest_scripts(self):
        text = (DEFAULT_SOURCE / "CLAUDE.md").read_text(encoding="utf-8")
        claude_scripts = set(parse_canonical_embed_scripts(text))
        inv = _full_inventory_from(DEFAULT_SOURCE)
        assert claude_scripts == set(inv.scripts), (
            "CLAUDE.md ln -s block drifted from embed-manifest.yaml scripts; "
            "regenerate CLAUDE embed block in cap-dev-pipe"
        )

    def test_known_non_embedded_scripts_actually_exist_in_source(self):
        present = [s for s in KNOWN_NON_EMBEDDED if (DEFAULT_SOURCE / s).is_file()]
        assert present, "expected at least some known non-embedded scripts to exist in source"
