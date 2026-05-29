"""Golden-fixture tests for the curated cap-dev-pipe embed set (FR-5, discovery D-10).

The embed set is a *curated subset* of the canonical checkout, NOT a glob: the source has
more top-level scripts than are embedded. The single source of truth is the
``ln -s $CAP_DEV_PIPE/<name>`` block in cap-dev-pipe's ``CLAUDE.md`` "Embedding in a Project"
section. These tests:

1. pin :data:`~startd8.capdevpipe_installer.EMBED_SCRIPTS` / ``EMBED_ALIASES`` against a
   frozen golden fixture (always runs, no external dependency), and
2. when the canonical checkout is present, cross-check the constant against the live
   ``CLAUDE.md`` ``ln -s`` block and the on-disk files — the *drift signal* (skipped when the
   source is absent, e.g. CI without the checkout).

The D-10 regression — a glob would wrongly capture ``run-compare.sh`` / ``run-clean-*.sh`` /
``run-kaizen-*.sh`` / ``create-project-wrapper.sh`` / ``prime-show-postmortem.py`` /
``resolve-questions.py`` — is guarded explicitly.
"""

import pytest

from startd8.capdevpipe_installer import (
    DEFAULT_SOURCE,
    EMBED_ALIASES,
    EMBED_SCRIPTS,
    parse_canonical_embed_scripts,
)

pytestmark = pytest.mark.unit


# Frozen golden fixture — the canonical 14-script embed set (cap-dev-pipe CLAUDE.md ln -s
# block) plus the 3 imported underscore aliases. Update this *and* EMBED_SCRIPTS together
# (review the diff in the PR) when the canonical list legitimately changes — see the regen
# helper scripts/regen_capdevpipe_embed_fixture.py.
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

# Source scripts that exist in the canonical checkout but are deliberately NOT embedded.
# A glob over run*.sh/clean-*.sh/*.py would wrongly capture these (D-10). If any appears in
# EMBED_SCRIPTS the curated-subset invariant is broken.
KNOWN_NON_EMBEDDED = {
    "run-compare.sh",
    "run-clean-target.sh",
    "run-clean-kaizen.sh",
    "run-kaizen-correlation.sh",
    "run-kaizen-trends.sh",
    "create-project-wrapper.sh",
    "prime-show-postmortem.py",
    "resolve-questions.py",  # referenced by nothing — verified
    "kaizen-correlation.py",
    "kaizen-trends.py",
    "new-cnvrg-rvw-prmpt.sh",
    "install-cap-dev-pipe.sh",
}


class TestEmbedSetGoldenFixture:
    """Set-equality against the frozen fixture (always runs)."""

    def test_scripts_match_golden_fixture(self):
        assert set(EMBED_SCRIPTS) == GOLDEN_SCRIPTS

    def test_aliases_match_golden_fixture(self):
        assert set(EMBED_ALIASES) == GOLDEN_ALIASES

    def test_total_embed_count_is_17(self):
        assert len(EMBED_SCRIPTS) + len(EMBED_ALIASES) == 17

    def test_no_duplicates(self):
        assert len(EMBED_SCRIPTS) == len(set(EMBED_SCRIPTS))
        assert len(EMBED_ALIASES) == len(set(EMBED_ALIASES))

    def test_scripts_and_aliases_disjoint(self):
        assert set(EMBED_SCRIPTS).isdisjoint(set(EMBED_ALIASES))

    def test_resolve_questions_excluded(self):
        # D-10 regression: resolve-questions.py is referenced by nothing and must not embed.
        assert "resolve-questions.py" not in EMBED_SCRIPTS
        assert "resolve-questions.py" not in EMBED_ALIASES

    def test_no_known_non_embedded_script_leaks_in(self):
        # A glob-based set would pull these in; assert the curated subset excludes them all.
        leaked = KNOWN_NON_EMBEDDED & (set(EMBED_SCRIPTS) | set(EMBED_ALIASES))
        assert (
            not leaked
        ), f"non-embedded source scripts leaked into the embed set: {leaked}"


class TestCanonicalParser:
    """Pure parsing of the CLAUDE.md ln -s block (no filesystem dependency)."""

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
        'ln -sf "../../PLAN.md" java-plan.md\n'  # must NOT be parsed (no $CAP_DEV_PIPE)
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
    not (DEFAULT_SOURCE / "CLAUDE.md").is_file(),
    reason="canonical cap-dev-pipe checkout not present (drift check skipped)",
)
class TestLiveDriftAgainstCanonicalSource:
    """Drift signal: cross-check the constant against the live canonical checkout.

    Skipped when the checkout is absent so CI without it stays green; on a dev machine it
    fails loudly the moment cap-dev-pipe's embed list legitimately changes — the intended
    drift signal (regenerate the fixture + EMBED_SCRIPTS and review the PR diff).
    """

    def test_embed_scripts_equal_canonical_claude_md_block(self):
        text = (DEFAULT_SOURCE / "CLAUDE.md").read_text(encoding="utf-8")
        canonical = parse_canonical_embed_scripts(text)
        assert canonical, "could not parse any ln -s block from cap-dev-pipe CLAUDE.md"
        assert set(canonical) == set(EMBED_SCRIPTS), (
            "EMBED_SCRIPTS drifted from cap-dev-pipe CLAUDE.md ln -s block; "
            "regenerate via scripts/regen_capdevpipe_embed_fixture.py and review the diff"
        )

    def test_every_embedded_script_exists_in_source(self):
        # No phantom embeds: each curated script is a real file in the checkout.
        missing = [s for s in EMBED_SCRIPTS if not (DEFAULT_SOURCE / s).is_file()]
        assert not missing, f"embedded scripts missing from source: {missing}"

    def test_every_alias_exists_in_source(self):
        missing = [a for a in EMBED_ALIASES if not (DEFAULT_SOURCE / a).is_file()]
        assert not missing, f"underscore aliases missing from source: {missing}"

    def test_known_non_embedded_scripts_actually_exist_in_source(self):
        # Sanity: the D-10 exclusions are real source files (else the guard is vacuous).
        # Only assert for the subset that should exist; tolerate upstream removals.
        present = [s for s in KNOWN_NON_EMBEDDED if (DEFAULT_SOURCE / s).is_file()]
        assert (
            present
        ), "expected at least some known non-embedded scripts to exist in source"
