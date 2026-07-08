# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Increment 2 — FIELD-LEVEL lane: LLM mapping (mocked), staging, and VIPP envelope production."""

from __future__ import annotations

import dataclasses
import json

from startd8.stakeholder_panel.proposals import ProposalStore
from startd8.stakeholder_panel.recommend_provenance import ESTIMATE_PROVENANCE, is_estimate
from startd8.stakeholder_panel.synthesis_bridge import (
    extract_field_mappings,
    serialize_accepted_to_vipp,
    stage_recommendations,
)


# ── extract_llm (OQ-9) — mocked mapper, no spend ──
def test_extract_field_mappings_zero_dollar_when_allowlist_empty():
    called = []

    def spy_mapper(prompt):
        called.append(prompt)
        return "[]"

    assert extract_field_mappings("some synthesis", frozenset(), mapper=spy_mapper) == []
    assert called == []  # never even built the prompt / called the model


def test_extract_field_mappings_validates_against_allowlist():
    def mapper(_prompt):
        return json.dumps([
            {"value_path": "business-targets.budget.target", "value": "$8,000", "rationale": "ceiling"},
            {"value_path": "Run.name", "value": "round3"},          # not allow-listed → dropped
            {"value_path": "business-targets.budget.target", "value": ""},  # empty value → dropped
        ])

    out = extract_field_mappings(
        "…synthesis…", {"business-targets.budget.target"}, mapper=mapper
    )
    assert out == [{"value_path": "business-targets.budget.target", "value": "$8,000", "rationale": "ceiling"}]


def test_extract_field_mappings_tolerates_code_fences_and_junk():
    assert extract_field_mappings("s", {"a.b"}, mapper=lambda p: "```json\n[]\n```") == []
    assert extract_field_mappings("s", {"a.b"}, mapper=lambda p: "not json") == []


# ── staging (FR-6) ──
def test_stage_recommendations_are_estimate_and_persisted(tmp_path):
    recs = stage_recommendations(
        tmp_path, "kp-1",
        [{"value_path": "business-targets.budget.target", "value": "$8,000",
          "domain": "business-targets", "rationale": "panel ceiling", "role_id": "operator"}],
    )
    assert len(recs) == 1
    r = recs[0]
    assert r.provenance == ESTIMATE_PROVENANCE and r.origin == "panel:operator"
    assert is_estimate(r) and r.disposition == "draft"
    # persisted + reloadable
    loaded = ProposalStore(tmp_path, "kp-1").load()
    assert [x.value_path for x in loaded] == ["business-targets.budget.target"]


# ── envelope production (FR-4 gate via build_proposal + FR-8 serialize) ──
def test_serialize_rejects_non_allowlisted_value_path(tmp_path):
    # A bare project has no kickoff manifest → allow-list empty → build_proposal rejects the capture.
    # This proves the FR-4 gate is enforced at serialization and the item is reported, not dropped.
    recs = stage_recommendations(
        tmp_path, "kp-2",
        [{"value_path": "Run.name", "value": "round3"}],
    )
    recs = [dataclasses.replace(r, disposition="accepted") for r in recs]  # frozen → replace (FR-7)
    result = serialize_accepted_to_vipp(tmp_path, recs)
    assert result["staged"] == []
    assert result["rejected"] and result["rejected"][0][0] == "Run.name"
    assert result["write"] is None  # nothing written to the inbox


def test_serialize_only_accepted_and_writes_inbox(tmp_path, monkeypatch):
    # Monkeypatch build_proposal so we can exercise the ACCEPT → buffer → serialize_buffer path
    # without standing up a real kickoff manifest/allow-list.
    from startd8.kickoff_experience import proposals as kp

    def fake_build_proposal(args, *, project_root, config=None):
        return kp.ProposedAction("capture", {"value_path": args["value_path"], "value": args["value"]},
                                 id="p1", base_sha="deadbeef")

    # stage.py imports build_proposal lazily from this source module, so patch it there.
    monkeypatch.setattr(kp, "build_proposal", fake_build_proposal)
    recs = stage_recommendations(
        tmp_path, "kp-3",
        [{"value_path": "business-targets.budget.target", "value": "$8,000"},
         {"value_path": "business-targets.deadline.target", "value": "Q4 2026"}],
    )
    recs = [dataclasses.replace(recs[0], disposition="accepted"), recs[1]]  # only first accepted (FR-7)
    result = serialize_accepted_to_vipp(tmp_path, recs)
    assert result["staged"] == ["business-targets.budget.target"]
    assert result["rejected"] == []
    inbox = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    assert inbox.is_file()
    envelope = json.loads(inbox.read_text())
    paths = [p["params"]["value_path"] for p in envelope["proposals"]]
    assert paths == ["business-targets.budget.target"]


def test_default_mapper_import_path_resolves():
    # Regression: `_default_mapper` once imported `resolve_agent_spec` from `startd8.agents`, which does
    # not export it (canonical: `startd8.utils.agent_resolution`) — the real paid path would ImportError.
    # The mock spec resolves a MockAgent (no network, no spend) and must return a string end-to-end.
    from startd8.stakeholder_panel.synthesis_bridge.extract_llm import _default_mapper

    out = _default_mapper("mock:mock-model")("return []")
    assert isinstance(out, str)
