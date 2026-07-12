"""FR-E4 — cloud-grant lifecycle → OTel metrics.

Verifies the `metrics` sink fires the right (event, reason) for every lifecycle path, that it is
FAIL-OPEN (a raising sink never breaks a grant), and that `GrantMetrics` degrades to a no-op when
OTel has no provider configured.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import (  # noqa: E402
    GrantMetrics,
    GrantStore,
    GrantTarget,
    TrustChainInputs,
    evaluate_trust_chain,
)


def _target(cap="chat-write"):
    return GrantTarget(deployment_id="dep-1", project_id="proj-1", capability=cap)


def _store():
    events: list[tuple[str, str | None]] = []
    store = GrantStore(metrics=lambda event, reason: events.append((event, reason)))
    return store, events


def test_issue_consume_revoke_emit():
    store, events = _store()
    t = _target()
    store.issue(t, uses=1, ttl_seconds=100, now=0.0, issued_by="op")
    assert ("issue", None) in events

    dec = store.resolve_and_consume(t, now=1.0)
    assert dec.allowed and ("consume", None) in events

    # second consume — exhausted → deny with the reason label
    store.resolve_and_consume(t, now=2.0)
    assert ("deny", "exhausted") in events


def test_absent_and_clock_denies_emit_reason():
    store, events = _store()
    store.resolve_and_consume(_target(), now=1.0)               # no grant
    assert ("deny", "absent") in events
    store.resolve_and_consume(_target(), now=1.0, clock_trusted=False)
    assert ("deny", "clock_untrusted") in events


def test_expired_revalidate_and_revoke_emit():
    store, events = _store()
    t = _target()
    g = store.issue(t, uses=5, ttl_seconds=10, now=0.0, issued_by="op")
    store.revalidate(g.id, t, now=999.0)                        # past expiry
    assert ("deny", "expired") in events
    assert store.revoke(g.id) is True
    assert ("revoke", None) in events


def test_trust_chain_auth_denies_emit_reason():
    store, events = _store()
    t = _target()
    store.issue(t, uses=1, ttl_seconds=100, now=0.0, issued_by="op")
    # bad api-key short-circuits before the grant is touched — still counted
    bad_key = TrustChainInputs(api_key_expected="k", api_key_presented="WRONG",
                               allowed_origins=frozenset({"https://x"}), origin_presented="https://x")
    evaluate_trust_chain(store, t, bad_key, now=1.0)
    assert ("deny", "api_key_invalid") in events
    # good key, bad origin
    bad_origin = TrustChainInputs(api_key_expected="k", api_key_presented="k",
                                  allowed_origins=frozenset({"https://x"}), origin_presented="https://EVIL")
    evaluate_trust_chain(store, t, bad_origin, now=1.0)
    assert ("deny", "origin_rejected") in events


def test_metrics_sink_is_fail_open():
    def boom(event, reason):
        raise RuntimeError("telemetry down")

    store = GrantStore(metrics=boom)
    t = _target()
    # a raising metrics sink must NOT break issuance or consume
    store.issue(t, uses=1, ttl_seconds=100, now=0.0, issued_by="op")
    dec = store.resolve_and_consume(t, now=1.0)
    assert dec.allowed


def test_grant_metrics_is_a_noop_without_a_provider():
    # No MeterProvider configured in the test process → GrantMetrics degrades to a silent no-op.
    m = GrantMetrics()
    # must never raise for any event
    m("issue")
    m("consume")
    m("revoke")
    m("deny", "exhausted")
    m("unknown-event", None)


def test_grant_metrics_records_against_a_fake_meter():
    calls: list[tuple[str, dict | None]] = []

    class _Counter:
        def __init__(self, name):
            self.name = name

        def add(self, amount, attrs=None):
            calls.append((self.name, attrs))

    class _Meter:
        def create_counter(self, name, description=""):
            return _Counter(name)

    m = GrantMetrics(meter=_Meter())
    m("issue")
    m("deny", "origin_rejected")
    names = [c[0] for c in calls]
    assert "startd8.cloud_grant.issued" in names
    deny = [c for c in calls if c[0] == "startd8.cloud_grant.denied"][0]
    assert deny[1] == {"reason": "origin_rejected"}
