# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Q1 — triage the single-question ask-all into a typed, role-tagged report + loader (FR-1..FR-7)."""
from __future__ import annotations

from startd8.stakeholder_panel.models import PanelAnswer
from startd8.stakeholder_panel.synthesis_bridge import (
    InputKind,
    Lane,
    list_ask_all_sessions,
    load_ask_all_session,
    render_backlog_section,
    triage_ask_all,
)
from startd8.stakeholder_panel.transcript import TranscriptStore


def _answers():
    return [
        PanelAnswer(role_id="household-member", question="What matters most?",
                    text="I need to log a chore in under 10 seconds; I won't tolerate friction.",
                    cost_usd=0.001),
        PanelAnswer(role_id="finance-lead", question="What matters most?",
                    text="Bills must never be paid late; we should warn before the due date.",
                    cost_usd=0.002),
        PanelAnswer(role_id="dependent-member", question="What matters most?",
                    text="", cost_usd=0.0),  # empty/deferred → skipped, not dropped
    ]


# ── FR-1/FR-2/FR-4: one role-tagged candidate per non-empty answer ───────────
def test_one_candidate_per_answer_role_tagged():
    report = triage_ask_all(_answers(), session_id="sess-x")
    assert len(report.candidates) == 2  # the empty one is skipped
    roles = {c.role for c in report.candidates}
    assert roles == {"household-member", "finance-lead"}
    # answers are input, never auto FIELD_LEVEL (NR-3)
    assert all(c.lane is Lane.NON_DECIDABLE for c in report.candidates)
    # role is surfaced structurally (to_dict) AND via source_section
    d = report.candidates[0].to_dict()
    assert d["role"] == "household-member" and d["source_section"] == "household-member"


def test_input_kind_from_heuristic():
    report = triage_ask_all(_answers())
    kinds = {c.role: c.input_kind for c in report.candidates}
    # "won't tolerate" → not a suggestion/constraint keyword → content; "must never" + "should" → suggestion wins
    assert kinds["finance-lead"] in (InputKind.suggestion, InputKind.constraint)


# ── FR-7: health surfaces question, spend, and skipped personas ──────────────
def test_health_reports_question_cost_and_skips():
    report = triage_ask_all(_answers(), question="What matters most?")
    joined = " ".join(report.health)
    assert "What matters most?" in joined
    assert "$0.0030" in joined  # 0.001 + 0.002
    assert "1 persona(s) gave an empty/deferred answer" in joined


# ── FR-3: the ask-all report renders through the shared backlog surface ──────
def test_renders_through_backlog():
    report = triage_ask_all(_answers(), session_id="sess-x")
    section = render_backlog_section(report, project="proj")
    assert "SYNTHETIC & UNRATIFIED" in section
    assert "log a chore in under 10 seconds" in section
    assert "household-member" in section  # provenance visible


# ── FR-5: loader (list + load newest) round-trips through the real store ─────
def test_loader_lists_and_loads(tmp_path):
    for a in _answers():
        TranscriptStore(tmp_path, "sess-x").append(a)
    assert list_ask_all_sessions(tmp_path) == ["sess-x"]
    answers, question = load_ask_all_session(tmp_path)  # newest
    assert question == "What matters most?"
    assert len(answers) == 3  # loader returns all rows (triage does the skipping)
    report = triage_ask_all(answers, session_id="sess-x", question=question)
    assert len(report.candidates) == 2


def test_loader_empty_project_is_empty(tmp_path):
    assert list_ask_all_sessions(tmp_path) == []
    answers, question = load_ask_all_session(tmp_path)
    assert answers == [] and question == ""
