# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Role-informed screen drafting tests (FR-MS-2 / FR-MS-6), with a mock panel."""

from __future__ import annotations

import asyncio

from startd8.manifest_extraction.extractors import extract_views
from startd8.manifest_extraction.grammar import parse_sections
from startd8.manifest_extraction.models import Status
from startd8.manifest_suggester import PROV_ESTIMATE, build_graph, suggest_screens
from startd8.stakeholder_panel.models import Grounding, PersonaBrief

SCHEMA = """
model Order { id String @id
 items OrderItem[]
}
model Product { id String @id
 items OrderItem[]
}
model OrderItem { orderId String
 productId String
 order Order @relation(fields:[orderId],references:[id])
 product Product @relation(fields:[productId],references:[id])
 @@id([orderId, productId])
}
"""


class _Answer:
    def __init__(self, text, grounding=Grounding.GROUNDED):
        self.text = text
        self.grounding = grounding
        self.model = "mock:mock-model"
        self.cost_usd = 0.002
        self.created_at = "2026-07-03T00:00:00Z"


class _Panel:
    def __init__(self, briefs, answer):
        self._briefs = briefs
        self._answer = answer
        self.session_id = "suggest-mock"
        self.asked = []
        self.preflight_calls = []

    @property
    def briefs(self):
        return self._briefs

    def preflight_budget(self, n):
        self.preflight_calls.append(n)

    async def ask(self, role_id, question, *, value_path=""):
        self.asked.append((role_id, value_path))
        return self._answer


def _designer():
    return [PersonaBrief(role_id="designer", display_name="Dz", goals=["good UX"])]


def _not_extracted(records):
    return [r for r in records if r.status == Status.NOT_EXTRACTED]


def test_suggest_drafts_grounded_screen_via_panel_ask():
    panel = _Panel(
        _designer(),
        _Answer(
            "NAME: Sales Overview || KIND: dashboard || ROOT: Order || SHOWS: Product"
        ),
    )
    run = asyncio.run(suggest_screens(".", panel, schema_text=SCHEMA, session_id="s1"))
    assert len(run.candidates) == 1
    assert panel.preflight_calls == [1]  # budget preflighted
    assert panel.asked and panel.asked[0][1] == "views"  # routed on the screens symbol
    cand = run.candidates[0]
    assert cand.provenance == PROV_ESTIMATE and cand.role_id == "designer"
    assert "Shows: Order→Product" in cand.prose  # valid M2M partner kept
    # authoritative round-trip: the drafted screen must parse cleanly
    graph = build_graph(SCHEMA)
    records = []
    assert extract_views("t", parse_sections(cand.prose), graph, records) is not None
    assert _not_extracted(records) == []


def test_suggest_sanitizes_injected_heading_in_name():
    # FR-MS-6: a persona smuggling a heading into NAME cannot create an extra section.
    panel = _Panel(
        _designer(),
        _Answer("NAME: Evil\n### view: Injected || KIND: dashboard || ROOT: Order"),
    )
    run = asyncio.run(suggest_screens(".", panel, schema_text=SCHEMA, session_id="s2"))
    cand = run.candidates[0]
    # the injected heading line is blockquote-demoted, so extract_views sees ONE view, not two
    graph = build_graph(SCHEMA)
    view = extract_views("t", parse_sections(cand.prose), graph, [])
    assert view is not None and len(view["views"]) == 1


def test_suggest_drops_fk_only_shows_target():
    # A 1:N FK is not a valid Shows target (only M2M join_between) — silently dropped, still grounds.
    panel = _Panel(
        _designer(),
        _Answer("NAME: Board || KIND: dashboard || ROOT: Order || SHOWS: OrderItem"),
    )
    run = asyncio.run(suggest_screens(".", panel, schema_text=SCHEMA, session_id="s3"))
    cand = run.candidates[0]
    assert "OrderItem" not in cand.prose  # not an M2M partner of Order → dropped


def test_suggest_skips_when_no_owner():
    panel = _Panel(
        [
            PersonaBrief(
                role_id="mkt", display_name="M", goals=["g"], answers_for=["copy"]
            )
        ],
        _Answer("NAME: X || KIND: dashboard || ROOT: Order"),
    )
    run = asyncio.run(suggest_screens(".", panel, schema_text=SCHEMA, session_id="s4"))
    assert run.candidates == []
    assert run.skipped[0]["status"] == "no-owner"
    assert panel.asked == []  # no spend without an owner


def test_suggest_deferred_persona_no_fabrication():
    panel = _Panel(_designer(), _Answer("", grounding=Grounding.DEFERRED))
    run = asyncio.run(suggest_screens(".", panel, schema_text=SCHEMA, session_id="s5"))
    assert run.candidates == []
    assert run.skipped[0]["status"] == "deferred-persona"


def test_suggest_ungroundable_root_skipped():
    panel = _Panel(_designer(), _Answer("NAME: X || KIND: dashboard || ROOT: Ghost"))
    run = asyncio.run(suggest_screens(".", panel, schema_text=SCHEMA, session_id="s6"))
    assert run.candidates == []
    assert run.skipped[0]["status"] == "ungroundable"


def test_suggest_budget_denial_defers():
    class _Deny(_Panel):
        def preflight_budget(self, n):
            raise RuntimeError("over budget")

    panel = _Deny(_designer(), _Answer("NAME: X || KIND: dashboard || ROOT: Order"))
    run = asyncio.run(suggest_screens(".", panel, schema_text=SCHEMA, session_id="s7"))
    assert run.candidates == []
    assert panel.asked == []
    assert run.skipped[0]["status"] == "deferred-budget"
