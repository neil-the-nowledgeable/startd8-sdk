# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Apply/lifecycle (FR-RP-6) + paid elicitation (FR-RP-2) tests, with a mock panel."""

from __future__ import annotations

import asyncio


from startd8.requirements_panel import (
    PROV_ESTIMATE,
    RequirementCandidate,
    RequirementDoc,
    apply_requirements,
    check_readiness,
    scaffold,
)
from startd8.requirements_panel.store import CandidateStore
from startd8.stakeholder_panel.models import Grounding, PersonaBrief


def _ok_candidate(
    area="security", title="Authz", body="The system MUST enforce RBAC.", role="sec"
):
    return RequirementCandidate(
        area=area, title=title, body=body, role_id=role, provenance=PROV_ESTIMATE
    )


# ── FR-RP-6 readiness gate ────────────────────────────────────────────────────


def test_readiness_blocks_unowned_stub():
    doc = scaffold("", "model User { id String @id\n name String\n}")
    res = check_readiness(doc)  # baseline stub carries <needs-owner>
    assert res.ok is False
    assert any("unowned stub" in b for b in res.blockers)


def test_readiness_blocks_ungrounded_mandate():
    c = _ok_candidate(body="The system MUST link a Ghost record.")
    c.flags = ["high: schema-absence: entity 'Ghost' not in schema"]
    res = check_readiness(RequirementDoc(title="d", candidates=[c]))
    assert res.ok is False
    assert any("ungrounded MUST/SHALL" in b for b in res.blockers)


def test_readiness_passes_clean_doc():
    assert (
        check_readiness(RequirementDoc(title="d", candidates=[_ok_candidate()])).ok
        is True
    )


# ── FR-RP-6 apply: atomic, one-shot lifecycle ─────────────────────────────────


def test_apply_writes_then_refuses_regeneration(tmp_path):
    target = tmp_path / "docs" / "FEATURE_REQUIREMENTS.md"
    doc = RequirementDoc(title="Requirements (draft)", candidates=[_ok_candidate()])

    r1 = apply_requirements(doc, target)
    assert r1.written is True
    assert target.is_file()
    first_bytes = target.read_bytes()
    assert r1.crp_handoff.startswith("/new-cnvrg-rvw-prmpt")

    # One-shot lifecycle (R2-S4) + no-clobber (R1-S3): a second approve refuses, bytes unchanged.
    r2 = apply_requirements(doc, target)
    assert r2.written is False
    assert "never regenerated over" in r2.reason
    assert target.read_bytes() == first_bytes


def test_apply_blocked_by_readiness_does_not_write(tmp_path):
    target = tmp_path / "REQ.md"
    doc = scaffold("", "model User { id String @id\n name String\n}")  # unowned stub
    result = apply_requirements(doc, target)
    assert result.written is False
    assert result.blockers
    assert not target.exists()


def test_store_roundtrip_and_atomicity(tmp_path):
    store = CandidateStore(tmp_path, "elicit-abc")
    cands = [
        _ok_candidate(),
        _ok_candidate(title="TLS", body="The system MUST use TLS."),
    ]
    store.save(cands)
    loaded = store.load()
    assert [c.title for c in loaded] == ["Authz", "TLS"]
    assert store.path.read_text().startswith("[")  # sorted+indented JSON


# ── FR-RP-2 paid elicitation via a mock panel ─────────────────────────────────


class _FakeAnswer:
    def __init__(self, text, grounding=Grounding.GROUNDED):
        self.text = text
        self.grounding = grounding
        self.model = "mock:mock-model"
        self.cost_usd = 0.001
        self.created_at = "2026-07-03T00:00:00Z"


class _FakePanel:
    """Duck-typed panel: records asks, returns scripted answers by role."""

    def __init__(self, briefs, answers):
        self._briefs = briefs
        self._answers = answers  # role_id -> _FakeAnswer or None(→deferred)
        self.session_id = "elicit-mock"
        self.asked = []
        self.preflight_calls = []

    @property
    def briefs(self):
        return self._briefs

    def preflight_budget(self, n):
        self.preflight_calls.append(n)

    async def ask(self, role_id, question, *, value_path=""):
        self.asked.append((role_id, value_path, question))
        ans = self._answers.get(role_id)
        if ans is None:
            return _FakeAnswer("", grounding=Grounding.DEFERRED)
        return ans


SCHEMA = "model User { id String @id\n name String\n}\nmodel Order { id String @id\n userId String\n}"


def test_elicit_uses_panel_ask_grounds_and_stages():
    from startd8.requirements_panel import elicit_requirements

    briefs = [
        PersonaBrief(role_id="security", display_name="Sec", goals=["safety"]),
        PersonaBrief(role_id="ops", display_name="Ops", goals=["uptime"]),
    ]
    answers = {
        "security": _FakeAnswer(
            "TITLE: Enforce RBAC || REQUIREMENT: The system MUST enforce RBAC on User records. || WHY: least privilege"
        ),
        "ops": _FakeAnswer(
            "TITLE: SLA || REQUIREMENT: The system MUST sustain 99.9% uptime by 2027. || WHY: reliability"
        ),
    }
    panel = _FakePanel(briefs, answers)
    run = asyncio.run(
        elicit_requirements(
            ".", panel, brief="A store.", schema_text=SCHEMA, session_id="s1"
        )
    )

    assert run.areas_drafted == 2
    assert panel.preflight_calls == [2]  # budget preflighted after resolution
    # went through panel.ask with the area as value_path (never a bare Persona)
    asked_areas = {a[1] for a in panel.asked}
    assert {"security", "ops"} <= asked_areas
    # security candidate references the real User entity verbatim (grounded, no schema-absence flag)
    sec = next(c for c in run.candidates if c.role_id == "security")
    assert "User" in sec.entities_referenced
    assert not any("schema-absence" in f for f in sec.flags)
    # ops candidate's bare year 2027 → advisory-low (not a hard flag)
    ops = next(c for c in run.candidates if c.role_id == "ops")
    assert any("advisory-low: year" in f for f in ops.flags)
    assert all(c.provenance == PROV_ESTIMATE for c in run.candidates)


def test_elicit_skips_unowned_area_and_deferrals():
    from startd8.requirements_panel import elicit_requirements

    # only a marketing persona with no requirements-area answers_for → every area is skipped
    briefs = [
        PersonaBrief(
            role_id="marketing",
            display_name="M",
            goals=["growth"],
            answers_for=["copy"],
        )
    ]
    panel = _FakePanel(briefs, {})
    run = asyncio.run(
        elicit_requirements(".", panel, brief="x", schema_text=SCHEMA, session_id="s2")
    )
    assert run.areas_drafted == 0
    assert all(s["status"] == "no-owner" for s in run.skipped)
    assert panel.asked == []  # never a loose match


def test_elicit_budget_denial_defers_all_no_spend():
    from startd8.requirements_panel import elicit_requirements

    briefs = [PersonaBrief(role_id="security", display_name="S", goals=["g"])]

    class _DenyPanel(_FakePanel):
        def preflight_budget(self, n):
            raise RuntimeError("budget exceeded")

    panel = _DenyPanel(
        briefs, {"security": _FakeAnswer("TITLE: x || REQUIREMENT: The system MUST y.")}
    )
    run = asyncio.run(
        elicit_requirements(".", panel, schema_text=SCHEMA, session_id="s3")
    )
    assert run.areas_drafted == 0
    assert panel.asked == []  # spent nothing
    assert any(s["status"] == "deferred-budget" for s in run.skipped)


def test_elicit_deferred_persona_leaves_area_empty():
    from startd8.requirements_panel import elicit_requirements

    briefs = [PersonaBrief(role_id="security", display_name="S", goals=["g"])]
    panel = _FakePanel(briefs, {"security": None})  # None → deferred
    run = asyncio.run(
        elicit_requirements(".", panel, schema_text=SCHEMA, session_id="s4")
    )
    assert run.areas_drafted == 0
    assert any(s["status"] == "deferred-persona" for s in run.skipped)
