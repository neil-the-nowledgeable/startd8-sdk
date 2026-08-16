# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Drift guard for the single criticality-vocabulary authority (collector-enrichment gap #4).

Before this, ``collector_enrichment_validation.CRITICALITY_VALUES`` was a hand-maintained
``frozenset`` snapshot, and two other observability maps restated the same ``{critical, high,
medium, low}`` key set independently — a drift surface (add a value in one place, the others
silently disagree). The vocabulary is now single-sourced from ``taxonomy_enums`` and these tests
metabolize the drift into a LOUD failure: if any consumer's criticality key set diverges from the
authority, or the canonical values change, a test breaks at exactly the divergence.

The canonical-values pin doubles as the cross-repo contract check: ContextCore forwards criticality
via the manifest ``spec.business.criticality`` / ``spec.targets[].criticality`` field, and these four
values are its agreed vocabulary. A change to the pin is the signal to coordinate cross-repo.
"""

from startd8.observability.taxonomy_enums import (
    Criticality,
    CRITICALITY_ORDER,
    CRITICALITY_VALUES,
    is_valid_criticality,
)


class TestAuthorityIsSingleSourced:
    def test_collector_enrichment_reexports_the_authority(self):
        """The enrichment validator must use the shared frozenset object, not a private copy."""
        from startd8.observability import collector_enrichment_validation as cev

        assert cev.CRITICALITY_VALUES is CRITICALITY_VALUES

    def test_observability_artifact_checks_sees_the_same_set(self):
        """The soft validator imports CRITICALITY_VALUES from the enrichment module — same authority."""
        from startd8.observability.collector_enrichment_validation import (
            CRITICALITY_VALUES as via_enrichment,
        )

        assert via_enrichment is CRITICALITY_VALUES


class TestCanonicalValuesPin:
    def test_exact_four_values(self):
        # Pin the vocabulary. Changing this is a deliberate, cross-repo-coordinated act
        # (ContextCore's manifest `criticality:` field shares this set) — not an accident.
        assert CRITICALITY_VALUES == frozenset({"critical", "high", "medium", "low"})

    def test_order_is_descending_severity_and_covers_the_set(self):
        assert CRITICALITY_ORDER == ("critical", "high", "medium", "low")
        assert frozenset(CRITICALITY_ORDER) == CRITICALITY_VALUES

    def test_enum_members_match_values(self):
        assert {c.value for c in Criticality} == CRITICALITY_VALUES

    def test_is_valid_criticality(self):
        assert is_valid_criticality("critical")
        assert not is_valid_criticality("")  # unset is not valid
        assert not is_valid_criticality("severe")


class TestConsumingMapsCoverTheVocabulary:
    """Every criticality-keyed map in the package must cover exactly the authority (plus any
    documented sentinel). This is the drift guard: add a criticality value and forget a map → red.
    """

    def test_criticality_to_severity_keys_equal_authority(self):
        from startd8.observability.artifact_generator_generators import (
            _CRITICALITY_TO_SEVERITY,
        )

        assert set(_CRITICALITY_TO_SEVERITY) == CRITICALITY_VALUES

    def test_coverage_rank_keys_are_authority_plus_unknown_sentinel(self):
        from startd8.observability.portal_spec_builder import _COV_CRIT_RANK

        # _COV_CRIT_RANK carries a non-criticality "unknown" bucket for un-tagged services.
        assert set(_COV_CRIT_RANK) - {"unknown"} == CRITICALITY_VALUES
