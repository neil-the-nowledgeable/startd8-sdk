"""AQW-1 (#226 de-overfit): service-kind vocabulary drift guard.

The SDK classifies every non-``unknown`` service kind into exactly one of three sets —
REQUEST_KINDS (transport default), grounded workload (`_KIND_DEFAULTS`), or
UNGROUNDED_KINDS (recognized-but-deferred). The canonical vocabulary is owned cross-repo
by ContextCore's ``ServiceKind`` enum (mirrored here as ``CANONICAL_SERVICE_KINDS``). If a
kind is added upstream and the SDK isn't updated, it would fall SILENTLY to the transport
default (the exact #226 overfit). This test makes that drift fail loudly.
"""

from __future__ import annotations

from startd8.observability.metric_descriptor import (
    CANONICAL_SERVICE_KINDS,
    REQUEST_KINDS,
    UNGROUNDED_KINDS,
    _KIND_DEFAULTS,
)


def test_sdk_kind_sets_partition_the_canonical_vocabulary():
    grounded = frozenset(_KIND_DEFAULTS)
    classified = REQUEST_KINDS | grounded | UNGROUNDED_KINDS
    # `unknown` is the producer's "no signal" sentinel — handled by the fallback path,
    # deliberately not in any of the three classifying sets.
    expected = CANONICAL_SERVICE_KINDS - {"unknown"}

    missing = expected - classified          # a canonical kind the SDK doesn't classify
    extra = classified - expected            # an SDK kind not in the canonical vocabulary
    assert not missing, (
        f"canonical service kind(s) {sorted(missing)} are unclassified — a new kind would "
        f"fall silently to the transport default. Add each to REQUEST_KINDS, _KIND_DEFAULTS, "
        f"or UNGROUNDED_KINDS (and CANONICAL_SERVICE_KINDS if it's genuinely new upstream)."
    )
    assert not extra, (
        f"SDK classifies kind(s) {sorted(extra)} absent from CANONICAL_SERVICE_KINDS — "
        f"either a typo or the canonical mirror drifted from ContextCore's ServiceKind."
    )


def test_classifying_sets_are_mutually_exclusive():
    # A kind must live in exactly ONE bucket (partition, not overlap).
    assert not (REQUEST_KINDS & UNGROUNDED_KINDS)
    assert not (REQUEST_KINDS & frozenset(_KIND_DEFAULTS))
    assert not (UNGROUNDED_KINDS & frozenset(_KIND_DEFAULTS))


def test_base_red_kinds_single_sourced_across_the_three_seams():
    # The base RED triplet is referenced at three seams that MUST agree — the two-tier suppression
    # gate, the declared-series covers-filter, and the convention-triplet skip/suppress. A local
    # re-literal at any one silently re-opens the #274 dead-SLI class for a future 4th base kind.
    # This guard fails loudly if any seam stops pointing at the single source.
    from startd8.observability.metric_descriptor import BASE_RED_KINDS
    from startd8.observability.artifact_generator_context import _RED_KINDS
    from startd8.observability.artifact_generator_generators import _TRIPLET_SIGNAL_KINDS

    assert BASE_RED_KINDS == frozenset({"availability", "latency", "throughput"})
    # `is` (not just ==) so a copied literal that happens to be equal today still fails.
    assert _RED_KINDS is BASE_RED_KINDS
    assert _TRIPLET_SIGNAL_KINDS is BASE_RED_KINDS
    # the two-tier gate in artifact_generator.py consumes BASE_RED_KINDS directly (no local literal).
    import startd8.observability.artifact_generator as ag
    assert ag.BASE_RED_KINDS is BASE_RED_KINDS
