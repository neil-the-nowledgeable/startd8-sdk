# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Tests for the kickoff-panel viewer (observability UX, FR-UX-1..23).

Mirrors ``tests/unit/consultation/test_consultation_webui.py`` / ``test_consultation_m2.py``:
graceful-optional model, read-only store, two-axis render, and the escape-first XSS guard.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from startd8.kickoff_view import (
    KickoffPanelStore,
    KickoffTranscript,
    KickoffViewService,
    model_family,
    render_html,
    render_text,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "kickoff_panel"


def _load(name: str) -> KickoffTranscript:
    return KickoffTranscript.model_validate(json.loads((FIXTURES / name).read_text()))


# ── model / graceful optionals (FR-UX-3) ──
class TestModel:
    def test_complete_fixture_loads(self):
        t = _load("complete_retail.json")
        assert t.session_id.startswith("kp-")
        assert len(t.rounds) == 4
        assert t.roster_size == 12
        assert t.prep is not None and not t.prep.is_empty()
        assert t.synthesis is not None and t.synthesis.text

    def test_thin_schema_degrades(self):
        """Older fixture lacks prep/adversaries/status/halt — must not crash (FR-UX-3)."""
        t = _load("thin_schema.json")
        assert t.prep is None or t.prep.is_empty()
        assert t.adversaries == []
        assert t.is_halted is False
        assert t.rounds  # still has rounds

    def test_halted_is_first_class(self):
        t = _load("halted.json")
        assert t.is_halted is True
        assert t.rounds == []
        assert t.halt and "assumptions" in (t.halt.get("reason") or "")

    @pytest.mark.parametrize(
        "spec,fam",
        [
            ("anthropic:claude-opus-4-8", "Claude"),
            ("openai:gpt-5.5", "GPT"),
            ("gemini:gemini-3.1-pro-preview", "Gemini"),
            ("mistral:mistral-large", "Mistral"),
            ("unknownvendor:x", "Other"),
            ("", "Other"),
        ],
    )
    def test_model_family(self, spec, fam):
        assert model_family(spec) == fam

    def test_family_distribution_and_adversary(self):
        t = _load("complete_retail.json")
        dist = t.family_distribution()
        assert dist == {"Claude": 4, "GPT": 4, "Gemini": 4}
        assert sum(dist.values()) == t.roster_size
        # complete fixture has fraud + competitor adversaries
        assert t.adversaries
        assert t.is_adversary(t.adversaries[0])

    def test_all_entries_flatten(self):
        t = _load("complete_retail.json")
        pairs = t.all_entries()
        assert len(pairs) == sum(len(r.entries) for r in t.rounds)


# ── store (read-only, FR-UX-1/2) ──
class TestStore:
    def _project_with(self, tmp_path: Path, *fixtures: str) -> Path:
        d = tmp_path / ".startd8" / "kickoff-panel"
        d.mkdir(parents=True)
        for i, fx in enumerate(fixtures):
            # unique on-disk names so list() has >1 session
            dest = d / f"kp-2026070{i}T120000-aaa{i}.json"
            shutil.copy(FIXTURES / fx, dest)
        return tmp_path

    def test_empty_dir_lists_nothing(self, tmp_path):
        assert KickoffPanelStore(tmp_path).list_sessions() == []
        assert KickoffPanelStore(tmp_path).load_latest() is None
        assert KickoffPanelStore(tmp_path).latest_session_id() is None

    def test_list_newest_first(self, tmp_path):
        root = self._project_with(
            tmp_path, "complete_retail.json", "thin_schema.json", "halted.json"
        )
        store = KickoffPanelStore(root)
        ids = store.list_sessions()
        assert len(ids) == 3
        mtimes = [store.mtime(s) for s in ids]
        assert mtimes == sorted(mtimes, reverse=True)  # newest first

    def test_load_roundtrips(self, tmp_path):
        root = self._project_with(tmp_path, "complete_retail.json")
        store = KickoffPanelStore(root)
        sid = store.latest_session_id()
        t = store.load(sid)
        assert t.rounds and t.roster_size == 12

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            KickoffPanelStore(tmp_path).load("does-not-exist")


# ── HTML render (FR-UX-4..22) ──
class TestRenderHtml:
    def test_standalone_document(self):
        html = render_html(_load("complete_retail.json"))
        assert html.lstrip().startswith("<!doctype html>")
        assert html.rstrip().endswith("</html>")
        assert "__SESSION_JSON__" not in html

    def test_byte_identity_static_default(self):
        """serve is None ⇒ byte-identical to the no-arg call (static guarantee)."""
        t = _load("complete_retail.json")
        assert render_html(t) == render_html(t, serve=None)

    def test_embedded_json_no_raw_closing_script(self):
        """A </script> in any field cannot terminate the JSON container (FR-UX-22)."""
        evil = KickoffTranscript.model_validate(
            {
                "session_id": "kp-evil",
                "project": "p</script><script>alert(1)</script>",
                "model_assignment": {"r": "anthropic:claude-opus-4-8"},
                "rounds": [
                    {
                        "round_id": "R1",
                        "title": "t",
                        "kind": "individual",
                        "entries": [
                            {
                                "role_id": "r",
                                "display_name": "n",
                                "model": "anthropic:claude-opus-4-8",
                                "text": "x </script><script>alert(2)</script>",
                            }
                        ],
                    }
                ],
            }
        )
        html = render_html(evil)
        # exactly the two real template <script> containers, no injected ones
        assert html.count("</script>") == 2
        assert "<script>alert(2)" not in html
        assert "\\u003c" in html  # the escape is present

    def test_embedded_json_parses_after_unescaping(self):
        html = render_html(_load("complete_retail.json"))
        m = re.search(
            r'<script type="application/json" id="session-data">\s*(.*?)\s*</script>',
            html,
            re.DOTALL,
        )
        assert m
        payload = json.loads(m.group(1).replace("\\u003c", "<"))
        assert payload["session_id"].startswith("kp-")
        assert len(payload["rounds"]) == 4

    def test_contains_rounds_roles_and_families(self):
        t = _load("complete_retail.json")
        html = render_html(t)
        first_entry = t.rounds[0].entries[0]
        assert first_entry.display_name in html or first_entry.role_id in html
        assert t.rounds[0].title in html
        for fam in ("Claude", "GPT", "Gemini"):
            assert fam in html

    def test_adversary_marking_present(self):
        """FR-UX-10: adversary roles are visually distinguished in the payload/markup."""
        t = _load("complete_retail.json")
        assert t.adversaries
        html = render_html(t)
        assert '"is_adversary": true' in html
        assert "adversary" in html  # the attack-framed badge label

    def test_unratified_banner_always_present(self):
        for fx in ("complete_retail.json", "thin_schema.json", "halted.json"):
            html = render_html(_load(fx))
            assert "SYNTHETIC PANEL" in html
            assert "unratified" in html

    def test_halted_flag_and_no_rounds_payload(self):
        html = render_html(_load("halted.json"))
        m = re.search(r'id="session-data">\s*(.*?)\s*</script>', html, re.DOTALL)
        payload = json.loads(m.group(1).replace("\\u003c", "<"))
        assert payload["is_halted"] is True
        assert payload["rounds"] == []

    def test_cost_zero_renders_not_recorded(self):
        # complete fixture has cost_total_usd 0.0 → payload carries 0/None; text renderer says so
        txt = render_text(_load("complete_retail.json"))
        assert "not recorded" in txt


# ── text render (CLI show) ──
class TestRenderText:
    def test_round_major_default(self):
        txt = render_text(_load("complete_retail.json"))
        assert "SYNTHETIC PANEL" in txt.splitlines()[0]
        assert "R1" in txt and "R4" in txt

    def test_role_major_repivot(self):
        t = _load("complete_retail.json")
        role_txt = render_text(t, by_role=True)
        # a role id appears as a thread header
        assert any(e.role_id in role_txt for r in t.rounds for e in r.entries)

    def test_halted_shortcircuits(self):
        txt = render_text(_load("halted.json"))
        assert "HALTED" in txt
        assert "R1" not in txt  # no rounds rendered


# ── facade ──
class TestFacade:
    def test_service_list_load_render(self, tmp_path):
        d = tmp_path / ".startd8" / "kickoff-panel"
        d.mkdir(parents=True)
        shutil.copy(
            FIXTURES / "complete_retail.json", d / "kp-20260704T154131-e70156.json"
        )
        svc = KickoffViewService(tmp_path)
        assert svc.list_sessions() == ["kp-20260704T154131-e70156"]
        assert svc.latest_session_id() == "kp-20260704T154131-e70156"
        html = svc.render_html("kp-20260704T154131-e70156")
        assert "<!doctype html>" in html
        txt = svc.render_text("kp-20260704T154131-e70156", by_role=True)
        assert "SYNTHETIC PANEL" in txt


# ── live-follow (v2: FR-UX-17/18/19) ──
def _in_progress(rounds: int, roster: int = 3, status: str = "in_progress") -> dict:
    ma = {f"r{i}": "anthropic:claude-opus-4-8" for i in range(roster)}
    rnds = [
        {
            "round_id": f"R{n}",
            "title": f"round {n}",
            "kind": "individual",
            "entries": [
                {
                    "role_id": f"r{i}",
                    "display_name": f"R{i}",
                    "model": ma[f"r{i}"],
                    "text": "x",
                }
                for i in range(roster)
            ],
        }
        for n in range(1, rounds + 1)
    ]
    return {
        "session_id": "kp-live",
        "project": "p",
        "model_assignment": ma,
        "status": status,
        "rounds": rnds,
        "cost_total_usd": 0.0,
    }


class TestModelLiveState:
    def test_is_done(self):
        assert KickoffTranscript.model_validate(_in_progress(1)).is_done is False
        done = _in_progress(4, status="completed")
        assert KickoffTranscript.model_validate(done).is_done is True
        assert (
            KickoffTranscript.model_validate({"status": "halted", "halt": {}}).is_done
            is True
        )

    def test_active_round_pending_next(self):
        t = KickoffTranscript.model_validate(
            _in_progress(2)
        )  # 2 full rounds, still running
        # all landed rounds are full → the *next* round is pending
        assert t.active_round_id() == "R3"

    def test_active_round_filling_partial(self):
        d = _in_progress(2)
        d["rounds"][1]["entries"] = d["rounds"][1]["entries"][:1]  # R2 short of roster
        t = KickoffTranscript.model_validate(d)
        assert t.active_round_id() == "R2"

    def test_active_round_none_when_done(self):
        assert (
            KickoffTranscript.model_validate(
                _in_progress(4, status="completed")
            ).active_round_id()
            is None
        )


class TestLiveRender:
    def test_byte_identity_no_live(self):
        t = _load("complete_retail.json")
        assert render_html(t) == render_html(t, live_reload_secs=None)

    def test_live_injects_refresh_and_banner(self):
        t = KickoffTranscript.model_validate(_in_progress(2))
        html = render_html(t, live_reload_secs=3)
        assert '<meta http-equiv="refresh" content="3">' in html
        assert "live-banner" in html and "LIVE — following kp-live" in html
        # in-progress → payload marks the pending round for the filling badge
        assert '"active_round": "R3"' in html

    def test_text_marks_filling(self):
        d = _in_progress(2)
        d["rounds"][1]["entries"] = d["rounds"][1]["entries"][:1]
        txt = render_text(KickoffTranscript.model_validate(d))
        assert "◀ filling" in txt


class TestWatcher:
    def _store(self, tmp_path):
        from startd8.kickoff_view import KickoffPanelStore, TranscriptWatcher

        store = KickoffPanelStore(tmp_path)
        store.root.mkdir(parents=True, exist_ok=True)
        return store, TranscriptWatcher

    def _write(self, store, payload):
        store._path("kp-live").write_text(json.dumps(payload), encoding="utf-8")

    def test_poll_detects_change_only(self, tmp_path):
        store, Watcher = self._store(tmp_path)
        self._write(store, _in_progress(1))
        w = Watcher(store, "kp-live", interval=0)
        first = w.poll()
        assert first is not None and len(first.rounds) == 1
        assert w.poll() is None  # unchanged → None
        self._write(store, _in_progress(2))  # size grows → signature changes
        again = w.poll()
        assert again is not None and len(again.rounds) == 2

    def test_poll_absent_and_bad_json_tolerated(self, tmp_path):
        store, Watcher = self._store(tmp_path)
        w = Watcher(store, "kp-live", interval=0)
        assert w.poll() is None  # not there yet
        store._path("kp-live").write_text("{not json", encoding="utf-8")
        assert w.poll() is None  # unreadable → None, no crash
        self._write(store, _in_progress(1))
        assert w.poll() is not None  # settles on the next valid write

    def test_follow_streams_until_done(self, tmp_path):
        store, Watcher = self._store(tmp_path)
        self._write(store, _in_progress(1))
        # scripted future writes, applied one per sleep() call
        stages = iter([_in_progress(2), _in_progress(4, status="completed")])

        def fake_sleep(_):
            try:
                self._write(store, next(stages))
            except StopIteration:
                pass

        seen = []
        w = Watcher(store, "kp-live", interval=0)
        final = w.follow(
            lambda t: seen.append((t.status, len(t.rounds))),
            sleep=fake_sleep,
            max_ticks=50,
        )
        assert seen == [("in_progress", 1), ("in_progress", 2), ("completed", 4)]
        assert final is not None and final.is_done

    def test_follow_max_ticks_guard(self, tmp_path):
        store, Watcher = self._store(tmp_path)
        self._write(store, _in_progress(1))  # never becomes done
        calls = []
        w = Watcher(store, "kp-live", interval=0)
        final = w.follow(lambda t: calls.append(t), sleep=lambda _: None, max_ticks=5)
        # only the first (and only) change fires on_change; loop still exits via max_ticks
        assert len(calls) == 1
        assert final is not None and not final.is_done
