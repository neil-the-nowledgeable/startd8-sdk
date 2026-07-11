"""M4a — the durable FileGrantStore + append-only AuditLog (OQ-4 control-plane persistence + FR-10).

The CLI issues into a JSON file; the served app reads + consumes it. Each op reloads the file (a
CLI-issued grant is visible) under an inter-process flock (consume is atomic across instances). Audit is
append-only and **fail-closed**: an un-auditable issuance/consume does not proceed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import (  # noqa: E402
    AuditLog,
    FileGrantStore,
    GrantDeny,
    GrantTarget,
    StoreUnavailable,
)

T0 = 1_000_000.0
TGT = GrantTarget("dep-A", "proj-1", "chat-write")


def test_issue_persists_and_a_fresh_store_sees_and_consumes_it(tmp_path):
    path = tmp_path / "grants.json"
    FileGrantStore(path).issue(TGT, uses=1, ttl_seconds=900.0, now=T0, issued_by="op")   # CLI process
    # a SEPARATE store instance (the served app) reloads and consumes the CLI-issued grant
    app_store = FileGrantStore(path)
    d = app_store.resolve_and_consume(TGT, now=T0 + 1)
    assert d.allowed is True and d.uses_remaining_after == 0
    # the decrement is durable — a third instance sees it exhausted
    assert FileGrantStore(path).resolve_and_consume(TGT, now=T0 + 2).reason is GrantDeny.EXHAUSTED


def test_persist_is_valid_json_and_survives_revoke(tmp_path):
    path = tmp_path / "grants.json"
    s = FileGrantStore(path)
    g = s.issue(TGT, uses=2, ttl_seconds=900.0, now=T0, issued_by="op")
    assert s.revoke(g.id) is True
    data = json.loads(path.read_text())
    assert data[g.id]["revoked"] is True
    assert FileGrantStore(path).resolve_and_consume(TGT, now=T0 + 1).reason is GrantDeny.REVOKED


def test_all_grants_lists_for_the_cli(tmp_path):
    path = tmp_path / "grants.json"
    s = FileGrantStore(path)
    s.issue(TGT, uses=1, ttl_seconds=900.0, now=T0, issued_by="op")
    s.issue(GrantTarget("dep-A", "proj-1", "read-metrics"), uses=1, ttl_seconds=900.0, now=T0, issued_by="op")
    assert len(FileGrantStore(path).all_grants()) == 2


def test_unreadable_store_raises_store_unavailable(tmp_path):
    path = tmp_path / "grants.json"
    path.write_text("{ this is not json")
    with pytest.raises(StoreUnavailable):
        FileGrantStore(path)


# --------------------------------------------------------------------------- audit


def test_audit_records_issue_consume_revoke_appendonly(tmp_path):
    apath = tmp_path / "audit.jsonl"
    s = FileGrantStore(tmp_path / "grants.json", audit=AuditLog(apath))
    g = s.issue(TGT, uses=1, ttl_seconds=900.0, now=T0, issued_by="operator:alice")
    s.resolve_and_consume(TGT, now=T0 + 1)
    s.revoke(g.id)
    events = [json.loads(ln) for ln in apath.read_text().splitlines()]
    kinds = [e["event"] for e in events]
    assert kinds == ["issue", "consume", "revoke"]
    assert events[0]["issued_by"] == "operator:alice"   # attribution captured (FR-10)
    # no message text anywhere (FR-WM2-14a): audit only carries structured grant metadata
    assert not any("message" in e or "text" in e for e in events)


def test_audit_write_failure_fails_closed_on_issue(tmp_path):
    def _boom(event):
        raise StoreUnavailable("audit sink down")

    s = FileGrantStore(tmp_path / "grants.json", audit=_boom)
    with pytest.raises(StoreUnavailable):
        s.issue(TGT, uses=1, ttl_seconds=900.0, now=T0, issued_by="op")
    # fail-closed: no grant was persisted
    assert not (tmp_path / "grants.json").exists() or json.loads((tmp_path / "grants.json").read_text()) == {}


def test_audit_write_failure_denies_consume_with_no_debit(tmp_path):
    path = tmp_path / "grants.json"
    FileGrantStore(path).issue(TGT, uses=1, ttl_seconds=900.0, now=T0, issued_by="op")

    class _FlakyAudit:
        armed = False

        def __call__(self, event):
            if self.armed:
                raise StoreUnavailable("audit sink down")

    audit = _FlakyAudit()
    s = FileGrantStore(path, audit=audit)
    audit.armed = True
    d = s.resolve_and_consume(TGT, now=T0 + 1)
    assert d.reason is GrantDeny.STORE_UNAVAILABLE          # un-auditable consume → deny
    # no debit: a fresh store still has the use
    assert FileGrantStore(path).resolve_and_consume(TGT, now=T0 + 2).allowed is True
