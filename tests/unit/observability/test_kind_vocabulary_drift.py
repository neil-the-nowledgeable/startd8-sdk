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
