# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Parity/mirror tests for CoverageReport (complexity-distiller D1).

CoverageReport replaced 11 parallel local accumulator lists that
``generate_observability_artifacts`` assembled by hand into ``report.fr_coverage``.
These tests pin the serialization contract so the consolidation cannot silently
drift back apart — in particular the *byte-identity* rule: eight keys are always
present (in a fixed order); three are present only when non-empty.
"""

from startd8.observability.artifact_generator_models import CoverageReport


ALWAYS_KEYS = [
    "empty_services",
    "unfulfilled",
    "emitted",
    "ungrounded_kinds",
    "unverified_base_metrics",
    "suppressed_base_metrics",
    "bound_declared_series",
    "deferred_declared_kinds",
]
CONDITIONAL_KEYS = ["bound_declared_functional", "bound_declared_span", "pending_probes"]


def test_empty_report_emits_exactly_the_eight_always_keys_in_order():
    """A fresh report = the pre-#300/#307/#308 golden shape: 8 keys, none conditional."""
    fr = CoverageReport().to_fr_coverage()
    assert list(fr.keys()) == ALWAYS_KEYS
    assert all(fr[k] == [] for k in ALWAYS_KEYS)
    assert not any(k in fr for k in CONDITIONAL_KEYS)


def test_conditional_keys_absent_when_empty_present_when_populated():
    """The byte-identity discipline: an empty conditional list is ABSENT, not []."""
    c = CoverageReport()
    c.bound_declared_span.append({"service": "cart", "kind": "http"})
    fr = c.to_fr_coverage()
    # populated conditional appears...
    assert fr["bound_declared_span"] == [{"service": "cart", "kind": "http"}]
    # ...the other two stay absent (would be a new manifest byte otherwise)
    assert "bound_declared_functional" not in fr
    assert "pending_probes" not in fr
    # always-keys still lead, still in order
    assert list(fr.keys())[:8] == ALWAYS_KEYS


def test_to_fr_coverage_matches_hand_built_dict_bytewise():
    """Mirror guard: to_fr_coverage() == the exact dict the old inline block built."""
    c = CoverageReport()
    c.empty_services.append("svcA")
    c.unfulfilled.append({"fr": "FR-1"})
    c.emitted.extend(["FR-2", "FR-3"])
    c.ungrounded_kinds.append({"service": "svcB", "kind": "cron"})
    c.unverified_base_metrics.append({"service": "svcC"})
    c.suppressed_base_metrics.append({"service": "svcD"})
    c.bound_declared_series.append({"service": "svcE"})
    c.deferred_declared_kinds.append({"service": "svcF", "kind": "availability"})
    c.bound_declared_functional.append({"service": "svcG"})
    c.pending_probes.append({"service": "svcH"})
    # bound_declared_span intentionally left empty → must be absent

    expected = {
        "empty_services": ["svcA"],
        "unfulfilled": [{"fr": "FR-1"}],
        "emitted": ["FR-2", "FR-3"],
        "ungrounded_kinds": [{"service": "svcB", "kind": "cron"}],
        "unverified_base_metrics": [{"service": "svcC"}],
        "suppressed_base_metrics": [{"service": "svcD"}],
        "bound_declared_series": [{"service": "svcE"}],
        "deferred_declared_kinds": [{"service": "svcF", "kind": "availability"}],
        # conditionals: two populated (present), one empty (absent)
        "bound_declared_functional": [{"service": "svcG"}],
        "pending_probes": [{"service": "svcH"}],
    }
    fr = c.to_fr_coverage()
    assert fr == expected
    assert "bound_declared_span" not in fr
