"""Offline cross-repo vocabulary parity — fires in SDK CI without ContextCore installed (CEP CH-1).

The sibling ``test_vocabulary_parity_contextcore.py`` guards the startd8 mirror sets against the LIVE
ContextCore enums, but it opens with ``pytest.importorskip("contextcore.contracts.types")`` — and
ContextCore is an **optional dependency** absent from the SDK venv. So every one of those parity
guards SKIPS in every SDK CI run, and the drift they exist to catch (a ContextCore-owned kind/signal/
surface/target-kind renamed or added while the startd8 hand-copied mirror goes stale → silent
mis-generation) goes completely unguarded.

This file closes that gap with a **committed snapshot** of ContextCore's vocabulary
(``data/contextcore_vocab_snapshot.json``):

  1. **Offline guards (always fire):** the startd8 mirrors are asserted against the snapshot — the
     exact assertions the sibling makes against the live enums, minus the ``importorskip``. These run
     in the SDK venv, so a stale mirror fails at PR time.
  2. **Freshness guard (fires when ContextCore IS importable):** the snapshot itself is asserted equal
     to the live enums, so it cannot silently rot vs a newer ContextCore — the "live upgrade-path
     check" the snapshot approach requires. When ContextCore is absent this ONE test skips (not the
     whole module).

Refresh the snapshot when the freshness guard fails (re-capture from ContextCore per the JSON's
``_provenance``, then commit).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.observability.metric_descriptor import (
    NON_EMITTING_CONVENTION_SURFACES,
    NON_SCRAPEABLE_SURFACES,
    REQUEST_KINDS,
    UNGROUNDED_KINDS,
    _KIND_DEFAULTS,
)
from startd8.observability.artifact_generator_generators import _TRIPLET_SIGNAL_KINDS
from startd8.observability.artifact_generator import _NON_K8S_TARGET_KINDS

_SNAPSHOT = json.loads(
    (Path(__file__).parent / "data" / "contextcore_vocab_snapshot.json").read_text(encoding="utf-8")
)

SERVICE_KINDS = set(_SNAPSHOT["SERVICE_KIND_VALUES"])
SIGNAL_KINDS = set(_SNAPSHOT["SIGNAL_KIND_VALUES"])
METRICS_SURFACES = set(_SNAPSHOT["METRICS_SURFACE_VALUES"])
DEPLOYMENT_RUNTIMES = set(_SNAPSHOT["DEPLOYMENT_RUNTIME_VALUES"])
NON_K8S_TARGET_KINDS = set(_SNAPSHOT["NON_K8S_TARGET_KINDS"])

# Every service kind startd8 partitions (server / defaulted / ungrounded).
STARTD8_SERVICE_KINDS = set(REQUEST_KINDS) | set(_KIND_DEFAULTS) | set(UNGROUNDED_KINDS)


# ── Offline guards — always fire in SDK CI (no importorskip) ───────────────────────────────

def test_startd8_service_kinds_are_known_offline():
    unknown = STARTD8_SERVICE_KINDS - SERVICE_KINDS
    assert not unknown, (
        f"startd8 references service kind(s) {sorted(unknown)} not in the ContextCore ServiceKind "
        f"snapshot ({sorted(SERVICE_KINDS)}). Reconcile metric_descriptor, or refresh the snapshot."
    )


def test_startd8_covers_every_real_service_kind_offline():
    # The dangerous direction: ContextCore ADDS a kind startd8 doesn't partition → silent transport
    # fallback. `unknown` is the fallback sentinel and is intentionally not partitioned.
    unhandled = (SERVICE_KINDS - {"unknown"}) - STARTD8_SERVICE_KINDS
    assert not unhandled, (
        f"ContextCore ServiceKind snapshot has {sorted(unhandled)} that startd8 does not partition "
        f"(REQUEST_KINDS / _KIND_DEFAULTS / UNGROUNDED_KINDS). Add a row or mark ungrounded."
    )


def test_triplet_signal_kinds_are_known_offline():
    unknown = set(_TRIPLET_SIGNAL_KINDS) - SIGNAL_KINDS
    assert not unknown, (
        f"startd8 _TRIPLET_SIGNAL_KINDS {sorted(unknown)} not in the ContextCore SignalKind snapshot "
        f"({sorted(SIGNAL_KINDS)})."
    )


def test_non_emitting_surfaces_are_known_offline():
    unknown = set(NON_EMITTING_CONVENTION_SURFACES) - METRICS_SURFACES
    assert not unknown, (
        f"startd8 NON_EMITTING_CONVENTION_SURFACES {sorted(unknown)} not in the ContextCore "
        f"MetricsSurface snapshot ({sorted(METRICS_SURFACES)}). Dead-SLI #274 class risk."
    )


def test_non_scrapeable_surfaces_are_known_offline():
    unknown = set(NON_SCRAPEABLE_SURFACES) - METRICS_SURFACES
    assert not unknown, (
        f"startd8 NON_SCRAPEABLE_SURFACES {sorted(unknown)} not in the ContextCore MetricsSurface "
        f"snapshot ({sorted(METRICS_SURFACES)})."
    )


def test_deployment_runtime_gate_token_is_known_offline():
    # startd8 fails ServiceMonitor closed on deployment_runtime == "unknown"; that token is a
    # cross-repo contract with ContextCore's DeploymentRuntime vocabulary.
    assert "unknown" in DEPLOYMENT_RUNTIMES, (
        f"startd8 gates ServiceMonitor on deployment_runtime=='unknown', absent from the ContextCore "
        f"DeploymentRuntime snapshot ({sorted(DEPLOYMENT_RUNTIMES)})."
    )


def test_non_k8s_target_kinds_are_known_offline():
    unknown = set(_NON_K8S_TARGET_KINDS) - NON_K8S_TARGET_KINDS
    assert not unknown, (
        f"startd8 _NON_K8S_TARGET_KINDS {sorted(unknown)} not in the ContextCore NON_K8S_TARGET_KINDS "
        f"snapshot ({sorted(NON_K8S_TARGET_KINDS)})."
    )
    assert "compose_service" in NON_K8S_TARGET_KINDS & set(_NON_K8S_TARGET_KINDS), (
        "compose_service (the kind init-from-plan emits for a compose runtime) must be non-k8s in BOTH "
        "the snapshot and startd8, else the ServiceMonitor FP-3 returns."
    )


# ── Freshness guard — snapshot must equal LIVE ContextCore when it is importable ───────────

def test_snapshot_matches_live_contextcore():
    """When ContextCore IS installed, the committed snapshot must equal the live enums — so the
    snapshot can't silently rot vs a newer ContextCore. Skips (this test only) when CC is absent."""
    ctypes = pytest.importorskip("contextcore.contracts.types")
    live = {
        "SERVICE_KIND_VALUES": set(ctypes.SERVICE_KIND_VALUES),
        "SIGNAL_KIND_VALUES": set(ctypes.SIGNAL_KIND_VALUES),
    }
    if hasattr(ctypes, "METRICS_SURFACE_VALUES"):
        live["METRICS_SURFACE_VALUES"] = set(ctypes.METRICS_SURFACE_VALUES)
    if hasattr(ctypes, "DEPLOYMENT_RUNTIME_VALUES"):
        live["DEPLOYMENT_RUNTIME_VALUES"] = set(ctypes.DEPLOYMENT_RUNTIME_VALUES)
    try:
        from contextcore.models.core import NON_K8S_TARGET_KINDS as _live_nk
        live["NON_K8S_TARGET_KINDS"] = set(_live_nk)
    except Exception:  # pragma: no cover - only when ContextCore predates the partition
        pass

    stale = {
        key: {"snapshot": sorted(_SNAPSHOT[key]), "live": sorted(live_vals)}
        for key, live_vals in live.items()
        if set(_SNAPSHOT[key]) != live_vals
    }
    assert not stale, (
        "The committed ContextCore vocabulary snapshot is stale vs the installed ContextCore: "
        f"{stale}. Re-capture data/contextcore_vocab_snapshot.json (see its _provenance) and commit."
    )
