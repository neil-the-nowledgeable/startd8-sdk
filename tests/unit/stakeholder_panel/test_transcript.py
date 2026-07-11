# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Transcript persistence tests (FR-12/R1-F5/R2-F3)."""

from __future__ import annotations

import os
import stat
import sys

import pytest

from startd8.stakeholder_panel.models import Grounding, PanelAnswer
from startd8.stakeholder_panel.transcript import TranscriptStore, prune_sessions


def _answer(role_id="po", text="ship"):
    return PanelAnswer(
        role_id=role_id,
        question="when?",
        text=text,
        grounding=Grounding.GROUNDED,
        brief_hash="sha256:abc",
        roster_version="sha256:ros",
        session_id="sess-1",
    )


def test_append_and_load_round_trip(tmp_path):
    store = TranscriptStore(tmp_path, "sess-1")
    store.append(_answer(text="one"))
    store.append(_answer(text="two"))
    loaded = store.load()
    assert [a.text for a in loaded] == ["one", "two"]
    # Provenance survives the round trip (R2-F3).
    assert loaded[0].brief_hash == "sha256:abc"
    assert loaded[0].roster_version == "sha256:ros"


def test_load_absent_is_empty(tmp_path):
    assert TranscriptStore(tmp_path, "nope").load() == []


def test_load_survives_malformed_numeric_field(tmp_path):
    # Regression: a corrupt/edited numeric field must not crash load() (which would brick appends).
    import json

    store = TranscriptStore(tmp_path, "sess-1")
    store.dir.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            [{"role_id": "po", "text": "x", "cost_usd": "oops", "input_tokens": "NaNe"}]
        ),
        encoding="utf-8",
    )
    loaded = store.load()  # must not raise
    assert loaded[0].cost_usd == 0.0 and loaded[0].input_tokens == 0
    store.append(_answer(text="after"))  # append still works after a bad entry
    assert store.load()[-1].text == "after"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX perms")
def test_transcript_file_is_0600(tmp_path):
    store = TranscriptStore(tmp_path, "sess-1")
    store.append(_answer())
    mode = stat.S_IMODE(os.stat(store.path).st_mode)
    assert mode == 0o600


def test_unsafe_session_id_rejected(tmp_path):
    for bad in ["../evil", "a/b", "..", ""]:
        with pytest.raises(ValueError):
            TranscriptStore(tmp_path, bad)


def test_prune_keeps_most_recent(tmp_path):
    # Create 5 session files with increasing mtime.
    import time

    for i in range(5):
        s = TranscriptStore(tmp_path, f"sess-{i}")
        s.append(_answer(text=f"a{i}"))
        os.utime(s.path, (1000 + i, 1000 + i))
        time.sleep(0.001)
    deleted = prune_sessions(tmp_path, keep=2)
    assert len(deleted) == 3
    remaining = sorted(
        p.stem for p in (tmp_path / ".startd8" / "stakeholder-panel").glob("*.json")
    )
    assert remaining == ["sess-3", "sess-4"]  # the two newest survive


def test_prune_noop_under_cap(tmp_path):
    TranscriptStore(tmp_path, "sess-only").append(_answer())
    assert prune_sessions(tmp_path, keep=10) == []
