"""FR-E17 — the SQLite grant backend: same contract as FileGrantStore + structural properties
(DB-as-lock, CHECK floor, consumer_only cannot issue, suffix-dispatch factory)."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import (  # noqa: E402
    FileGrantStore,
    SqliteGrantStore,
    StoreUnavailable,
    GrantTarget,
    open_grant_store,
)

T = GrantTarget("dep", "proj", "chat-write")


def _db(tmp_path):
    return SqliteGrantStore(tmp_path / "grants.db")


def test_same_contract_as_file_backend(tmp_path):
    s = _db(tmp_path)
    s.issue(T, uses=2, ttl_seconds=100, now=0.0, issued_by="op")
    assert s.resolve_and_consume(T, now=1.0).allowed          # 2 -> 1
    d = s.resolve_and_consume(T, now=2.0)                      # 1 -> 0
    assert d.allowed and d.uses_remaining_after == 0
    assert s.resolve_and_consume(T, now=3.0).reason.value == "exhausted"
    # revalidate (no consume) on a fresh grant
    g2 = s.issue(T, uses=1, ttl_seconds=100, now=0.0, issued_by="op")
    assert s.revalidate(g2.id, T, now=1.0).allowed
    assert s.revoke(g2.id) is True
    assert s.revalidate(g2.id, T, now=1.0).reason.value == "revoked"


def test_redeem_link_on_sqlite(tmp_path):
    s = _db(tmp_path)
    s.issue(T, uses=1, ttl_seconds=100, now=0.0, issued_by="op", link_token="TOK")
    assert s.redeem_link("TOK", T, now=1.0).allowed
    assert s.redeem_link("TOK", T, now=2.0).reason.value == "absent"   # burned


def test_cross_instance_visibility_and_atomicity(tmp_path):
    # Two stores on the same DB file (issuer + served app). A grant issued by one is consumed by the
    # other, and a 1-use grant yields exactly one allow across the two instances (DB serializes).
    p = tmp_path / "grants.db"
    issuer = SqliteGrantStore(p)
    app = SqliteGrantStore(p, consumer_only=True)
    issuer.issue(T, uses=1, ttl_seconds=100, now=0.0, issued_by="op")
    first = app.resolve_and_consume(T, now=1.0)
    second = app.resolve_and_consume(T, now=1.0)
    assert first.allowed and not second.allowed and second.reason.value == "exhausted"


def test_consumer_only_cannot_issue(tmp_path):
    app = SqliteGrantStore(tmp_path / "grants.db", consumer_only=True)
    try:
        app.issue(T, uses=1, ttl_seconds=100, now=0.0, issued_by="op")
        assert False, "consumer_only must refuse issuance"
    except PermissionError:
        pass
    # but it can still consume a grant an issuer minted
    SqliteGrantStore(tmp_path / "grants.db").issue(T, uses=1, ttl_seconds=100, now=0.0, issued_by="op")
    assert app.resolve_and_consume(T, now=1.0).allowed


def test_check_floor_rejects_negative_uses(tmp_path):
    # The CHECK(uses_remaining >= 0) is defense-in-depth: a direct persist of a negative-use grant is
    # rejected by the ENGINE (StoreUnavailable), not just by app code.
    s = _db(tmp_path)
    g = s.issue(T, uses=1, ttl_seconds=100, now=0.0, issued_by="op")
    bad = replace(g, uses_remaining=-1)
    try:
        with s._op():
            s._persist(bad)
        assert False, "CHECK floor should reject uses_remaining < 0"
    except StoreUnavailable:
        pass


def test_factory_dispatch(tmp_path):
    assert isinstance(open_grant_store(tmp_path / "g.db"), SqliteGrantStore)
    assert isinstance(open_grant_store(tmp_path / "g.sqlite"), SqliteGrantStore)
    assert isinstance(open_grant_store(tmp_path / "g.json"), FileGrantStore)
    # consumer_only only reaches the sqlite backend; the file backend silently ignores it (no way to enforce)
    assert isinstance(open_grant_store(tmp_path / "g.json", consumer_only=True), FileGrantStore)


def test_prune_removes_dead_rows(tmp_path):
    s = _db(tmp_path)
    s.issue(T, uses=1, ttl_seconds=10, now=0.0, issued_by="op")     # will be expired
    assert s.prune(now=1000.0) == 1
    assert s.all_grants() == []
