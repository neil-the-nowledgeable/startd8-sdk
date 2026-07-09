"""Unit tests for the kickoff portal spec builder (docs/design/kickoff-portal/)."""
from __future__ import annotations

import pytest

from startd8.kickoff_experience.portal_spec import build_kickoff_portal_spec
from startd8.kickoff_experience.state import FieldState, KickoffState, SourceInventory

pytestmark = pytest.mark.unit


def _fs(manifest: str, path: str, attention: str, value: str = "v", status: str = "extracted") -> FieldState:
    return FieldState(
        manifest=manifest,
        value_path=path,
        status=status,
        attention=attention,
        ambiguity="none",
        value=value,
    )


def _state(*fields: FieldState, grammar: str = "authoring-contract-v0.4") -> KickoffState:
    return KickoffState(
        fields=tuple(fields),
        inventory=SourceInventory((), (), (), {}),
        grammar_version=grammar,
        contract_diff=(),
    )


def _titles(spec: dict) -> list[str]:
    return [p["title"] for p in spec["panels"]]


@pytest.fixture
def demo_state() -> KickoffState:
    return _state(
        _fs("business-targets.yaml", "/product_funnel/on_time_rate", "ok", "95%"),
        _fs("business-targets.yaml", "/monetization/mode_now", "blocked", None, status="not_extracted"),
        _fs("observability.yaml", "/owners/0/team", "ok", "household-core"),
        _fs("conventions.yaml", "/stack/framework", "ok", "fastapi"),
        _fs("build-preferences.yaml", "/budgets/llm_monthly", "review", "$25", status="defaulted"),
        _fs("app.yaml", "/app/port", "ok", "8099"),  # non-canonical manifest
    )


def test_spec_shape(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "demo")
    assert spec["uid"] == "cc-portal-kickoff-demo"
    assert spec["title"] == "demo — Digital Project Workbook"
    assert spec["tags"] == ["portal", "kickoff", "workbook", "demo"]
    # prometheus datasource variable is required by the gauge/stat panels + workflow validation
    assert any(v["type"] == "prometheusDatasource" for v in spec["variables"])
    types = [p["type"] for p in spec["panels"]]
    assert "text" in types and "gauge" in types and "stat" in types


def test_unique_panel_titles(demo_state: KickoffState) -> None:
    # DashboardCreatorWorkflow validation rejects duplicate panel titles — guard it here.
    titles = _titles(build_kickoff_portal_spec(demo_state, "demo"))
    assert len(titles) == len(set(titles)), f"duplicate titles: {titles}"


def test_completeness_and_gaps(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "demo")
    gauge = next(p for p in spec["panels"] if p["type"] == "gauge")
    # 4 of 6 fields are attention 'ok'
    assert gauge["expr"] == "vector(0.6667)"
    gaps = next(p for p in spec["panels"] if p["title"].startswith("Open Gaps"))
    assert gaps["expr"] == "vector(1)"  # exactly one 'blocked' field


def test_per_domain_chips_only_for_present_domains(demo_state: KickoffState) -> None:
    titles = _titles(build_kickoff_portal_spec(demo_state, "demo"))
    assert "business-targets · confirmed" in titles
    assert "observability · confirmed" in titles
    # 'build-preferences' present (review counts as a field) -> chip exists
    assert "build-preferences · confirmed" in titles


def test_cites_explain_content(demo_state: KickoffState) -> None:
    # single-source vocabulary: the business-targets section carries the canonical label + question
    spec = build_kickoff_portal_spec(demo_state, "demo")
    bt = next(p for p in spec["panels"] if "business-targets.yaml" in p["title"])
    content = bt["options"]["content"]
    assert "Business targets" in content
    assert "**Who:**" in content
    # gaps sort first: the blocked monetization field precedes the ok funnel field in the table
    assert content.index("/monetization/mode_now") < content.index("/product_funnel/on_time_rate")


def test_gap_field_marked(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "demo")
    bt = next(p for p in spec["panels"] if "business-targets.yaml" in p["title"])
    assert "🔴" in bt["options"]["content"]  # the blocked field is flagged


def test_deterministic(demo_state: KickoffState) -> None:
    assert build_kickoff_portal_spec(demo_state, "demo") == build_kickoff_portal_spec(demo_state, "demo")


def test_uid_slugifies_project_name(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "My Project_Name")
    assert spec["uid"] == "cc-portal-kickoff-my-project-name"


class _P:
    """Minimal duck-typed PersonaBrief for the stakeholders-section tests."""

    def __init__(self, role_id, display_name, answers_for=()):
        self.role_id = role_id
        self.display_name = display_name
        self.answers_for = list(answers_for)


class _R:
    def __init__(self, personas):
        self.personas = personas


def test_stakeholders_section_empty_state(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "demo")  # no roster
    sec = next(p for p in spec["panels"] if p["title"] == "Stakeholders")
    assert "No stakeholder roster yet" in sec["options"]["content"]
    assert "kickoff instantiate" in sec["options"]["content"]


def test_stakeholders_section_renders_roster(demo_state: KickoffState) -> None:
    roster = _R([_P("owner", "Business Owner", ["business-targets"]), _P("sre", "On-call SRE")])
    spec = build_kickoff_portal_spec(demo_state, "demo", roster=roster)
    sec = next(p for p in spec["panels"] if p["title"] == "Stakeholders")
    content = sec["options"]["content"]
    assert "owner" in content and "Business Owner" in content
    assert "sre" in content
    assert "2 personas" in content
    assert "SYNTHETIC & UNRATIFIED" in content  # the paid-run guardrail label
    # still unique titles with the extra section
    titles = _titles(spec)
    assert len(titles) == len(set(titles))


def test_stakeholders_section_renders_latest_run(demo_state: KickoffState) -> None:
    roster = _R([_P("owner", "Business Owner")])
    results = [
        {"role_id": "owner", "text": "Ship the MVP by Q3.", "grounding": "grounded",
         "cost_usd": 0.012, "question": "What's the top priority?", "session_id": "s-123"},
        {"role_id": "sre", "text": "Guard the error budget.", "grounding": "uncertain",
         "cost_usd": 0.008, "question": "What's the top priority?", "session_id": "s-123"},
    ]
    spec = build_kickoff_portal_spec(demo_state, "demo", roster=roster, panel_results=results)
    content = next(p for p in spec["panels"] if p["title"] == "Stakeholders")["options"]["content"]
    assert "Latest run" in content
    assert "s-123" in content and "What's the top priority?" in content
    assert "Ship the MVP by Q3." in content and "Guard the error budget." in content
    assert "SYNTHETIC & UNRATIFIED" in content
    assert "$0.0200" in content  # summed cost 0.012 + 0.008


def test_stakeholders_section_no_run_no_latest_block(demo_state: KickoffState) -> None:
    spec = build_kickoff_portal_spec(demo_state, "demo", roster=_R([_P("owner", "Owner")]))
    content = next(p for p in spec["panels"] if p["title"] == "Stakeholders")["options"]["content"]
    assert "Latest run" not in content


def test_load_panel_run_specific_vs_latest(tmp_path) -> None:
    import time

    from startd8.kickoff_experience.portal_build import _load_panel_run
    from startd8.stakeholder_panel.models import Grounding, PanelAnswer
    from startd8.stakeholder_panel.transcript import TranscriptStore

    TranscriptStore(tmp_path, "old").append(
        PanelAnswer(role_id="a", question="q", text="OLD", grounding=Grounding.GROUNDED, session_id="old")
    )
    time.sleep(0.02)
    TranscriptStore(tmp_path, "new").append(
        PanelAnswer(role_id="b", question="q", text="NEW", grounding=Grounding.GROUNDED, session_id="new")
    )
    assert _load_panel_run(tmp_path)[0]["text"] == "NEW"           # latest by mtime (Phase 1.5)
    assert _load_panel_run(tmp_path, "old")[0]["text"] == "OLD"    # FR-8 specific session
    assert _load_panel_run(tmp_path, "missing") is None


def test_pipeline_section_renders_funnel(demo_state: KickoffState) -> None:
    pipeline = {
        "staged": [
            {"value_path": "business-targets.on_time_rate", "recommended_value": "95%",
             "role_id": "owner", "grounding": "grounded", "disposition": "accepted", "cost_usd": 0.01},
            {"value_path": "observability.slo", "recommended_value": "99.5", "role_id": "sre",
             "grounding": "uncertain", "disposition": "draft"},
        ],
        "inbox": {"present": True, "count": 1, "envelope_seq": 3},
        "dispositions": {"present": True, "counts": {"ACCEPT": 1}, "evidence_available": False,
                         "items": [{"proposal_id": "p-abc123", "decision": "ACCEPT", "reason": "field ok"}],
                         "advisories": [{"question": "what about X?", "advisory": "consider Y"}]},
    }
    spec = build_kickoff_portal_spec(demo_state, "demo", pipeline=pipeline)
    sec = next(p for p in spec["panels"] if p["title"] == "Panel Processing Pipeline")["options"]["content"]
    assert "2 staged (1 accepted)" in sec and "1 in inbox" in sec
    assert "business-targets.on_time_rate" in sec and "accepted" in sec
    assert "p-abc123" in sec and "ACCEPT" in sec
    assert "SYNTHETIC & UNRATIFIED" in sec
    assert "evidence unavailable" in sec              # degraded qualifier
    assert "what about X?" in sec                     # anti-anchoring advisory
    assert "pending negotiate/apply" in sec           # apply status (inbox present)
    titles = _titles(spec)
    assert len(titles) == len(set(titles))


def test_pipeline_section_empty_and_omitted(demo_state: KickoffState) -> None:
    # None → no pipeline section at all
    spec = build_kickoff_portal_spec(demo_state, "demo")
    assert not any(p["title"] == "Panel Processing Pipeline" for p in spec["panels"])
    # present-but-empty → an empty-state panel
    spec2 = build_kickoff_portal_spec(demo_state, "demo", pipeline={"staged": [], "inbox": {"present": False}})
    sec = next(p for p in spec2["panels"] if p["title"] == "Panel Processing Pipeline")["options"]["content"]
    assert "No pipeline activity yet" in sec


def test_empty_state_still_valid() -> None:
    spec = build_kickoff_portal_spec(_state(), "empty")
    assert spec["uid"] == "cc-portal-kickoff-empty"
    gauge = next(p for p in spec["panels"] if p["type"] == "gauge")
    assert gauge["expr"] == "vector(0.0000)"
    assert len(_titles(spec)) == len(set(_titles(spec)))


# --- Audience personalization, Era 1 (WORKBOOK_AUDIENCE_PERSONALIZATION_REQUIREMENTS v0.4) ----------

from startd8.concierge.audience import KickoffAudience  # noqa: E402
from startd8.concierge.confirmation import audience_default_provenance  # noqa: E402


def _overview(spec: dict) -> str:
    return spec["panels"][0]["options"]["content"]


def _open_gaps(spec: dict) -> str:
    return next(p for p in spec["panels"] if p["title"] == "Open Gaps (author action)")["expr"]


def _ad(vp: str, value: str = "v", slug: str = "business-targets") -> dict:
    """A ledger entry stamped as an audience-default shield for ``vp``."""
    return {vp: {"value": value, "at": "t", "mode": "set", "provenance": audience_default_provenance(slug)}}


def test_byte_identity_defaults_reproduce_pre_audience_board(demo_state: KickoffState) -> None:
    """FR-6 / persona FR-4 / NR-3: Intermediate (default tier) + empty ledger ⇒ the FULL spec dict is
    byte-identical to the pre-audience call. The load-bearing regression guard."""
    baseline = build_kickoff_portal_spec(demo_state, "demo")
    with_defaults = build_kickoff_portal_spec(
        demo_state, "demo", audience=None, tier="light", provenance=None
    )
    assert with_defaults == baseline
    # and passing an empty ledger / Intermediate explicitly is still byte-identical
    assert build_kickoff_portal_spec(
        demo_state, "demo", audience=KickoffAudience.INTERMEDIATE, tier="light", provenance={}
    ) == baseline
    assert "Rendered for" not in _overview(baseline)


def test_slice_a_tier_renders_workbook_doc(demo_state: KickoffState) -> None:
    """FR-2/FR-4: the intro is rendered from the tiered workbook experience doc. light == legacy
    narrative; expanded (Beginner) serves the PLAIN rewrite; compact degrades to light (by design)."""
    light = _overview(build_kickoff_portal_spec(demo_state, "demo", tier="light"))
    expanded = _overview(
        build_kickoff_portal_spec(
            demo_state, "demo", audience=KickoffAudience.BEGINNER, tier="expanded"
        )
    )
    compact = _overview(build_kickoff_portal_spec(demo_state, "demo", tier="compact"))
    assert light.startswith("The **Digital Project Workbook** —")
    assert expanded != light                       # marker-slice guard (R1-S5): PLAIN really slices
    assert "Your Project Workbook" in expanded     # the Beginner rewrite
    # compact has no TL;DR region → degrades to light (Advanced == Intermediate); documented in FR-2
    assert compact.split("\n\n")[0] == light.split("\n\n")[0]


def test_rendered_for_note_gated_on_non_default_audience(demo_state: KickoffState) -> None:
    """OQ-3 / R1-S8: the note appears for Beginner/Advanced (reads audience.value), never Intermediate."""
    beg = _overview(build_kickoff_portal_spec(demo_state, "demo", audience=KickoffAudience.BEGINNER, tier="expanded"))
    adv = _overview(build_kickoff_portal_spec(demo_state, "demo", audience=KickoffAudience.ADVANCED, tier="compact"))
    inter = _overview(build_kickoff_portal_spec(demo_state, "demo", audience=KickoffAudience.INTERMEDIATE, tier="light"))
    assert "Rendered for: **beginner**" in beg
    assert "Rendered for: **advanced**" in adv
    assert "Rendered for" not in inter              # structural gate preserves byte-identity


def test_slice_b_badge_overrides_glyph_and_sorts_after_ok(demo_state: KickoffState) -> None:
    """FR-5/R1-S1/R1-S2: a shielded field shows 🛡️ (not ✅) and sorts with/after ok, never at blocked rank 0."""
    st = _state(
        _fs("business-targets.yaml", "/a_gap", "blocked", None, status="not_extracted"),
        _fs("business-targets.yaml", "/b_shielded", "blocked", None, status="not_extracted"),
    )
    spec = build_kickoff_portal_spec(st, "demo", provenance=_ad("/b_shielded"))
    section = next(p for p in spec["panels"] if "business-targets.yaml" in p["title"])["options"]["content"]
    assert "🛡️" in section and "safe default set for you" in section
    # the shielded row's glyph is NOT the ok/extraction ✅
    shielded_row = next(ln for ln in section.splitlines() if "/b_shielded" in ln)
    assert "✅" not in shielded_row and "🛡️" in shielded_row
    # sort: the still-blocked /a_gap row comes BEFORE the shielded /b_shielded row
    assert section.index("/a_gap") < section.index("/b_shielded")


def test_slice_b_honest_counts_discount_and_zero_floor() -> None:
    """FR-7/R1-S3/R2-F4: gap-facing widgets discount blocked∧shielded; floor is 0; gauge untouched."""
    st = _state(
        _fs("business-targets.yaml", "/g1", "blocked", None, status="not_extracted"),
        _fs("business-targets.yaml", "/g2", "blocked", None, status="not_extracted"),
        _fs("conventions.yaml", "/ok", "ok", "python"),
    )
    assert _open_gaps(build_kickoff_portal_spec(st, "demo")) == "vector(2)"
    # shield one of the two gaps → 1
    one = build_kickoff_portal_spec(st, "demo", provenance=_ad("/g1"))
    assert _open_gaps(one) == "vector(1)"
    assert "· 1 set for you" in _overview(one)
    assert "**1 gaps**" in _overview(one)
    # shield BOTH → 0 (never negative)
    both = {**_ad("/g1"), **_ad("/g2")}
    assert _open_gaps(build_kickoff_portal_spec(st, "demo", provenance=both)) == "vector(0)"
    # the Fields Confirmed gauge stays on extraction basis (1 ok / 3 total), NOT re-based on shields
    gauge = next(p for p in build_kickoff_portal_spec(st, "demo", provenance=both)["panels"] if p["type"] == "gauge")
    assert gauge["expr"] == "vector(0.3333)"


def test_slice_b_transient_badge_disappears_when_provenance_stripped() -> None:
    """FR-8: once kickoff confirm strips the audience-default provenance, the row reverts to normal."""
    st = _state(_fs("business-targets.yaml", "/x", "blocked", None, status="not_extracted"))
    shielded = build_kickoff_portal_spec(st, "demo", provenance=_ad("/x"))
    stripped = build_kickoff_portal_spec(
        st, "demo", provenance={"/x": {"value": "v", "at": "t", "mode": "set"}}  # no provenance key = explicit
    )
    assert "🛡️" in next(p for p in shielded["panels"] if "business-targets.yaml" in p["title"])["options"]["content"]
    assert "🛡️" not in next(p for p in stripped["panels"] if "business-targets.yaml" in p["title"])["options"]["content"]


def test_slice_b_fail_open_on_malformed_and_asymmetric_provenance(demo_state: KickoffState) -> None:
    """FR-6/FR-6a: a non-dict entry, or a value_path only in the ledger (not in state), never crashes and
    never wrongly discounts."""
    st = _state(
        _fs("business-targets.yaml", "/g1", "blocked", None, status="not_extracted"),
        _fs("business-targets.yaml", "/g2", "blocked", None, status="not_extracted"),
    )
    prov = {
        "/g1": "oops-a-scalar-not-a-dict",             # malformed → no badge, no discount, no crash
        "/only-in-ledger": {"provenance": audience_default_provenance("x")},  # asymmetry → ignored
    }
    spec = build_kickoff_portal_spec(st, "demo", provenance=prov)
    assert _open_gaps(spec) == "vector(2)"             # neither field discounted
    section = next(p for p in spec["panels"] if "business-targets.yaml" in p["title"])["options"]["content"]
    assert "🛡️" not in section                         # malformed entry is not a shield
    assert "only-in-ledger" not in section             # no phantom row
