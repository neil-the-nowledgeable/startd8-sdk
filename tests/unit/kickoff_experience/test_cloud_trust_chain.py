"""M2 — the FR-14 cloud-write trust chain as an ordered AND-gate (R1-F1/R1-S1).

The headline security acceptance criterion: a cloud write is honored **iff ALL four factors** hold
{api-key valid, Origin ∈ configured, grant resolves, grant live}. The 2⁴ truth table asserts only the
all-present row allows; all 15 partial rows deny — and a bad api-key / bad Origin denies **before** the
grant store is touched (no use spent, no existence oracle).
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import (  # noqa: E402
    GrantDeny,
    GrantStore,
    GrantTarget,
    TrustChainInputs,
    evaluate_trust_chain,
)

T0 = 1_000_000.0
TARGET = GrantTarget(deployment_id="dep-A", project_id="proj-1", capability="chat-write")
KEY = "operator-consumer-key"
ORIGINS = frozenset({"https://cloud.example.com"})


def _store(*, resolves: bool, live: bool) -> GrantStore:
    s = GrantStore()
    if resolves:
        # live → long ttl + uses; not-live → already expired (a resolvable-but-dead grant).
        ttl = 900.0 if live else 1.0
        g = s.issue(TARGET, uses=1, ttl_seconds=ttl, now=T0, issued_by="op")
        if not live:
            # advance past expiry by evaluating at a later `now` (done per-call below)
            _ = g
    return s


def _inputs(*, api_key_ok: bool, origin_ok: bool) -> TrustChainInputs:
    return TrustChainInputs(
        api_key_expected=KEY,
        api_key_presented=(KEY if api_key_ok else "wrong-key"),
        allowed_origins=ORIGINS,
        origin_presented=("https://cloud.example.com" if origin_ok else "https://evil.example.com"),
    )


def test_trust_chain_2x4_truth_table():
    # 16 rows: only (api_key ∧ origin ∧ grant-resolves ∧ grant-live) allows.
    for api_key_ok, origin_ok, resolves, live in itertools.product([True, False], repeat=4):
        store = _store(resolves=resolves, live=live)
        # a not-live grant is modelled as expired → evaluate past its 1s ttl so it's dead but resolvable
        now = T0 + (2.0 if (resolves and not live) else 1.0)
        d = evaluate_trust_chain(store, TARGET, _inputs(api_key_ok=api_key_ok, origin_ok=origin_ok), now=now)
        expected = api_key_ok and origin_ok and resolves and live
        assert d.allowed is expected, (
            f"api_key={api_key_ok} origin={origin_ok} resolves={resolves} live={live} "
            f"→ allowed={d.allowed} (expected {expected}), reason={d.reason}"
        )


def test_bad_api_key_denies_before_touching_the_grant():
    # Ordering: a wrong api-key short-circuits — the single-use grant is NOT consumed (no oracle).
    s = _store(resolves=True, live=True)
    d = evaluate_trust_chain(s, TARGET, _inputs(api_key_ok=False, origin_ok=True), now=T0 + 1)
    assert d.reason is GrantDeny.API_KEY_INVALID
    # the grant is untouched — a subsequent all-present call still succeeds (use not spent)
    ok = evaluate_trust_chain(s, TARGET, _inputs(api_key_ok=True, origin_ok=True), now=T0 + 1)
    assert ok.allowed is True and ok.uses_remaining_after == 0


def test_bad_origin_denies_before_touching_the_grant():
    s = _store(resolves=True, live=True)
    d = evaluate_trust_chain(s, TARGET, _inputs(api_key_ok=True, origin_ok=False), now=T0 + 1)
    assert d.reason is GrantDeny.ORIGIN_REJECTED
    ok = evaluate_trust_chain(s, TARGET, _inputs(api_key_ok=True, origin_ok=True), now=T0 + 1)
    assert ok.allowed is True   # grant not spent by the bad-origin attempt


def test_no_store_denies():
    d = evaluate_trust_chain(None, TARGET, _inputs(api_key_ok=True, origin_ok=True), now=T0 + 1)
    assert d.reason is GrantDeny.ABSENT


def test_all_present_consumes_exactly_one_use():
    s = _store(resolves=True, live=True)
    first = evaluate_trust_chain(s, TARGET, _inputs(api_key_ok=True, origin_ok=True), now=T0 + 1)
    assert first.allowed is True and first.uses_remaining_after == 0
    second = evaluate_trust_chain(s, TARGET, _inputs(api_key_ok=True, origin_ok=True), now=T0 + 2)
    assert second.reason is GrantDeny.EXHAUSTED   # single-use consumed
