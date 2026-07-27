"""Cross-repo parity guard: the observability kind/signal vocabulary must not drift from ContextCore.

The `ServiceKind` / `SignalKind` / `MetricsSurface` enums are *owned* by ContextCore
(`contextcore.contracts.types`, the normative #226/REQ-CCL-106 vocabulary). startd8 mirrors that
vocabulary as string sets (`REQUEST_KINDS`, `_KIND_DEFAULTS`, `UNGROUNDED_KINDS`, `_TRIPLET_SIGNAL_KINDS`,
`NON_EMITTING_CONVENTION_SURFACES`, `NON_SCRAPEABLE_SURFACES`) because it reads the values as strings
across an **optional-dependency** boundary — it cannot hard-import the enum. This test replaces the
previous manual "keep in sync" docstring instruction with an automated guard: if ContextCore renames or
adds a kind/signal/surface and the startd8 mirror goes stale, this fails instead of silently mis-generating.

Skips cleanly when ContextCore is not installed (the optional-dependency contract).
"""

from __future__ import annotations

import pytest

# Optional-dependency boundary: no ContextCore → nothing to guard against.
ctypes = pytest.importorskip("contextcore.contracts.types")

from startd8.observability.metric_descriptor import (  # noqa: E402
    NON_EMITTING_CONVENTION_SURFACES,
    NON_SCRAPEABLE_SURFACES,
    REQUEST_KINDS,
    UNGROUNDED_KINDS,
    _KIND_DEFAULTS,
)
from startd8.observability.artifact_generator_generators import (  # noqa: E402
    _TRIPLET_SIGNAL_KINDS,
)

SERVICE_KINDS = set(ctypes.SERVICE_KIND_VALUES)
SIGNAL_KINDS = set(ctypes.SIGNAL_KIND_VALUES)
# Ordering-safe against an older installed ContextCore that predates MetricsSurface: fall back to None
# and skip the metrics_surface guards rather than erroring if the owner symbol isn't present yet.
METRICS_SURFACES = getattr(ctypes, "METRICS_SURFACE_VALUES", None)

# Every service kind startd8 partitions (server / defaulted / ungrounded).
STARTD8_SERVICE_KINDS = set(REQUEST_KINDS) | set(_KIND_DEFAULTS) | set(UNGROUNDED_KINDS)


def test_startd8_service_kinds_are_known_to_contextcore():
    """No startd8 kind may be absent from the ContextCore ServiceKind enum."""
    unknown = STARTD8_SERVICE_KINDS - SERVICE_KINDS
    assert not unknown, (
        f"startd8 references service kind(s) {sorted(unknown)} not in ContextCore's ServiceKind "
        f"({sorted(SERVICE_KINDS)}). Reconcile metric_descriptor with contextcore.contracts.types."
    )


def test_startd8_covers_every_real_service_kind():
    """startd8 must handle every ServiceKind except `unknown` (the fallback).

    Guards the dangerous direction: ContextCore ADDS a kind that startd8's generator does not
    partition, so services of that kind silently fall back to the transport default.
    """
    unhandled = (SERVICE_KINDS - {"unknown"}) - STARTD8_SERVICE_KINDS
    assert not unhandled, (
        f"ContextCore ServiceKind adds {sorted(unhandled)} that startd8 does not partition "
        f"(REQUEST_KINDS / _KIND_DEFAULTS / UNGROUNDED_KINDS). Add a row or mark ungrounded."
    )


def test_triplet_signal_kinds_are_known_to_contextcore():
    """The request-triplet signal kinds must be a subset of ContextCore's SignalKind."""
    unknown = set(_TRIPLET_SIGNAL_KINDS) - SIGNAL_KINDS
    assert not unknown, (
        f"startd8 _TRIPLET_SIGNAL_KINDS {sorted(unknown)} not in ContextCore's SignalKind "
        f"({sorted(SIGNAL_KINDS)})."
    )


@pytest.mark.skipif(METRICS_SURFACES is None, reason="installed ContextCore predates MetricsSurface")
def test_non_emitting_surfaces_are_known_to_contextcore():
    """`NON_EMITTING_CONVENTION_SURFACES` must be a subset of ContextCore's MetricsSurface.

    Guards the cross-repo hand-copy: if ContextCore renames/removes a surface, or startd8 gains a
    surface ContextCore never declared, the base-RED suppression set drifts and services get
    mis-generated (dead SLIs re-open the #274 class). Fails here instead.
    """
    unknown = set(NON_EMITTING_CONVENTION_SURFACES) - set(METRICS_SURFACES)
    assert not unknown, (
        f"startd8 NON_EMITTING_CONVENTION_SURFACES {sorted(unknown)} not in ContextCore's MetricsSurface "
        f"({sorted(METRICS_SURFACES)}). Reconcile metric_descriptor with contextcore.contracts.types."
    )


@pytest.mark.skipif(METRICS_SURFACES is None, reason="installed ContextCore predates MetricsSurface")
def test_non_scrapeable_surfaces_are_known_to_contextcore():
    """`NON_SCRAPEABLE_SURFACES` (ServiceMonitor suppression set) must be a subset of MetricsSurface."""
    unknown = set(NON_SCRAPEABLE_SURFACES) - set(METRICS_SURFACES)
    assert not unknown, (
        f"startd8 NON_SCRAPEABLE_SURFACES {sorted(unknown)} not in ContextCore's MetricsSurface "
        f"({sorted(METRICS_SURFACES)}). Reconcile metric_descriptor with contextcore.contracts.types."
    )
