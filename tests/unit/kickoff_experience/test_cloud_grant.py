"""M0 — the CloudGrant primitive (CLOUD_MIRROR_GRANT_REQUIREMENTS.md v0.4).

Covers the CRP acceptance criteria: single-atomic consume (N-parallel → exactly 1; R1-F4/S4),
store-fail-mid-consume → deny + no debit (R1-F4), the 6-trigger fail-closed set (R1-F5), target-mismatch
denies (R1-F8), no-refund/forfeit (FR-7), and per-action re-validation without re-consuming (R1-F10).
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import (  # noqa: E402
    CloudGrant,
    GrantDeny,
    GrantStore,
    GrantTarget,
    StoreUnavailable,
)

T0 = 1_000_000.0
TARGET = GrantTarget(deployment_id="dep-A", project_id="proj-1", capability="chat-write")


def _store_with_grant(*, uses=1, ttl=900.0, now=T0, target=TARGET):
    s = GrantStore()
    g = s.issue(target, uses=uses, ttl_seconds=ttl, now=now, issued_by="operator:test")
    return s, g


# --------------------------------------------------------------------------- happy path + basics


def test_issue_then_resolve_and_consume_allows_and_decrements():
    s, g = _store_with_grant(uses=1)
    d = s.resolve_and_consume(TARGET, now=T0 + 1)
    assert d.allowed is True
    assert d.grant_id == g.id
    assert d.uses_remaining_after == 0
    # a second redemption is exhausted (single use)
    assert s.resolve_and_consume(TARGET, now=T0 + 2).reason is GrantDeny.EXHAUSTED


def test_issue_rejects_bad_params():
    s = GrantStore()
    for kwargs in ({"uses": 0}, {"ttl_seconds": 0}):
        try:
            s.issue(TARGET, ttl_seconds=900.0, now=T0, issued_by="op", **kwargs) if "uses" in kwargs \
                else s.issue(TARGET, uses=1, now=T0, issued_by="op", **kwargs)
            assert False, "expected ValueError"
        except ValueError:
            pass


# --------------------------------------------------------------------------- FR-5 deny triggers (each independent)


def test_absent_denies():
    assert GrantStore().resolve_and_consume(TARGET, now=T0).reason is GrantDeny.ABSENT


def test_expired_denies_without_consuming():
    s, g = _store_with_grant(uses=1, ttl=100.0, now=T0)
    d = s.resolve_and_consume(TARGET, now=T0 + 101)   # past expiry
    assert d.reason is GrantDeny.EXPIRED
    assert s.get(g.id).uses_remaining == 1            # not debited


def test_exhausted_denies():
    s, _ = _store_with_grant(uses=1)
    s.resolve_and_consume(TARGET, now=T0 + 1)          # spend the one use
    assert s.resolve_and_consume(TARGET, now=T0 + 2).reason is GrantDeny.EXHAUSTED


def test_revoked_denies_without_consuming():
    s, g = _store_with_grant(uses=2)
    assert s.revoke(g.id) is True
    d = s.resolve_and_consume(TARGET, now=T0 + 1)
    assert d.reason is GrantDeny.REVOKED
    assert s.get(g.id).uses_remaining == 2


def test_clock_untrusted_denies_without_consuming():
    s, g = _store_with_grant(uses=1)
    d = s.resolve_and_consume(TARGET, now=T0 + 1, clock_trusted=False)
    assert d.reason is GrantDeny.CLOCK_UNTRUSTED
    assert s.get(g.id).uses_remaining == 1


def test_store_unavailable_mid_consume_denies_with_no_debit():
    # A backend that fails on the consume-persist must roll back: deny + uses unchanged (FR-7 TOCTOU).
    class _FlakyStore(GrantStore):
        fail = False

        def _persist(self, grant):
            if self.fail:
                raise StoreUnavailable("backend down")

    s = _FlakyStore()
    g = s.issue(TARGET, uses=1, ttl_seconds=900.0, now=T0, issued_by="op")
    s.fail = True
    d = s.resolve_and_consume(TARGET, now=T0 + 1)
    assert d.reason is GrantDeny.STORE_UNAVAILABLE
    assert s.get(g.id).uses_remaining == 1            # rolled back — no debit


# --------------------------------------------------------------------------- FR-8 target binding


def test_wrong_deployment_target_denies():
    s, _ = _store_with_grant(uses=1, target=TARGET)   # bound to dep-A
    other = GrantTarget(deployment_id="dep-B", project_id="proj-1", capability="chat-write")
    assert s.resolve_and_consume(other, now=T0 + 1).reason is GrantDeny.ABSENT


def test_wrong_capability_denies():
    s, _ = _store_with_grant(uses=1, target=TARGET)   # capability=chat-write
    other = GrantTarget(deployment_id="dep-A", project_id="proj-1", capability="read-metrics")
    assert s.resolve_and_consume(other, now=T0 + 1).reason is GrantDeny.ABSENT


# --------------------------------------------------------------------------- FR-7 single-atomic consume


def test_n_parallel_redemptions_of_one_use_grant_exactly_one_wins():
    s, _ = _store_with_grant(uses=1)
    results = []
    barrier = threading.Barrier(24)

    def _redeem():
        barrier.wait()                                 # maximize contention
        results.append(s.resolve_and_consume(TARGET, now=T0 + 1).allowed)

    threads = [threading.Thread(target=_redeem) for _ in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1                    # exactly one allow across 24 racers
    assert results.count(False) == 23


def test_no_refund_path_a_consumed_use_stays_forfeit():
    # There is no increment/refund API: once consumed the use is forfeit even if the caller's action
    # would have failed (a refund would be a replay vector). Revalidate never restores uses.
    s, g = _store_with_grant(uses=1)
    s.resolve_and_consume(TARGET, now=T0 + 1)
    assert s.get(g.id).uses_remaining == 0
    assert not hasattr(s, "refund") and not hasattr(s, "restore")
    s.revalidate(g.id, TARGET, now=T0 + 2)             # a live grant at 0 uses
    assert s.get(g.id).uses_remaining == 0             # still forfeit


# --------------------------------------------------------------------------- FR-15/OQ-7 per-action re-validation


def test_revalidate_does_not_consume():
    s, g = _store_with_grant(uses=1)
    s.resolve_and_consume(TARGET, now=T0 + 1)          # session created, 1→0
    for i in range(3):                                 # three "turns"
        d = s.revalidate(g.id, TARGET, now=T0 + 2 + i)
        assert d.allowed is True                       # live → allowed
    assert s.get(g.id).uses_remaining == 0             # turns never re-consume


def test_revalidate_denies_after_expiry_even_though_use_was_consumed():
    # A session created just before expiry cannot keep spending after it (R1-F10 / OQ-7).
    s, g = _store_with_grant(uses=1, ttl=100.0, now=T0)
    assert s.resolve_and_consume(TARGET, now=T0 + 99).allowed is True   # created just before expiry
    assert s.revalidate(g.id, TARGET, now=T0 + 101).reason is GrantDeny.EXPIRED


def test_revalidate_denies_after_revocation():
    s, g = _store_with_grant(uses=3)
    s.resolve_and_consume(TARGET, now=T0 + 1)
    s.revoke(g.id)
    assert s.revalidate(g.id, TARGET, now=T0 + 2).reason is GrantDeny.REVOKED


def test_revalidate_rejects_target_mismatch():
    s, g = _store_with_grant(uses=1, target=TARGET)
    s.resolve_and_consume(TARGET, now=T0 + 1)
    other = GrantTarget(deployment_id="dep-B", project_id="proj-1", capability="chat-write")
    assert s.revalidate(g.id, other, now=T0 + 2).reason is GrantDeny.TARGET_MISMATCH


def test_is_live_helper_reports_specific_reason():
    live = CloudGrant("id", TARGET, uses_remaining=1, expires_at=T0 + 10, issued_by="op", issued_at=T0)
    assert live.is_live(T0 + 1) is None
    assert live.is_live(T0 + 11) is GrantDeny.EXPIRED
    from dataclasses import replace
    assert replace(live, revoked=True).is_live(T0 + 1) is GrantDeny.REVOKED
