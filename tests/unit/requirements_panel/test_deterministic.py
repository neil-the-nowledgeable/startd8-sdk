# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Deterministic ($0) surface tests for the Requirements Panel (design v0.4 §7 / Step 8)."""

from __future__ import annotations

import pytest

from startd8.requirements_panel import (
    PROV_BASELINE,
    PROV_ESTIMATE,
    RequirementCandidate,
    RequirementDoc,
    check_readiness,
    ground_requirement,
    has_unsafe_heading,
    is_join_table,
    neutralize_headings,
    primary_entities,
    scaffold,
    synthesize,
)
from startd8.requirements_panel.domains import (
    get_domain,
    requirement_domains,
    resolve_requirement_owner,
)
from startd8.requirements_panel.grounding import (
    SEV_ADVISORY,
    SEV_ADVISORY_LOW,
    SEV_HIGH,
)
from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.stakeholder_panel.models import PersonaBrief

SCHEMA = """
model User { id String @id
  name String
  orders Order[]
}
model Order { id String @id
  userId String
  total Int
}
model UserRole {
  userId String
  roleId String
  @@id([userId, roleId])
}
"""


# ── FR-RP-1 baseline + "primary entity" (R2-F5) ───────────────────────────────


def test_baseline_excludes_join_tables():
    schema = parse_prisma_schema(SCHEMA)
    names = [m.name for m in primary_entities(schema)]
    assert names == ["User", "Order"]  # UserRole (compound @@id, no @id) dropped
    assert is_join_table(schema.models["UserRole"]) is True
    assert is_join_table(schema.models["User"]) is False


def test_baseline_is_zero_llm_and_stub_marked():
    doc = scaffold("Build a store.", SCHEMA)
    assert [c.entities_referenced[0] for c in doc.candidates] == ["User", "Order"]
    # every baseline stub is unowned intent + baseline provenance
    assert all(c.provenance == PROV_BASELINE for c in doc.candidates)
    assert all(c.needs_owner for c in doc.candidates)


def test_baseline_fr_ids_are_content_stable():
    # R1-F4: adding an entity must not renumber existing FR ids.
    doc_a = scaffold("", SCHEMA)
    schema_plus = SCHEMA + "\nmodel Widget { id String @id\n name String\n}\n"
    doc_b = scaffold("", schema_plus)
    ids_a = {c.entities_referenced[0]: c.fr_id for c in doc_a.candidates}
    ids_b = {c.entities_referenced[0]: c.fr_id for c in doc_b.candidates}
    for entity, fid in ids_a.items():
        assert ids_b[entity] == fid  # pre-existing ids unchanged
    assert "Widget" in ids_b


# ── FR-RP-2 owner resolution: route reusable, resolve_owner NOT (R1-F1) ───────


def test_input_domains_resolve_owner_is_not_reusable():
    # Proves the non-reuse: the panel's resolver returns None for a requirements area.
    from startd8.stakeholder_panel.input_domains import resolve_owner as panel_resolve

    briefs = [PersonaBrief(role_id="security", display_name="Sec", goals=["safety"])]
    assert panel_resolve("security", briefs) is None


def test_owned_resolver_default_role_and_answers_for():
    sec = get_domain("security")
    # default owning_role present on roster → resolves
    briefs = [PersonaBrief(role_id="security", display_name="Sec", goals=["g"])]
    assert resolve_requirement_owner(sec, briefs) == "security"
    # else a high-confidence answers_for alias
    briefs2 = [
        PersonaBrief(
            role_id="apps", display_name="A", goals=["g"], answers_for=["authz"]
        )
    ]
    assert resolve_requirement_owner(sec, briefs2) == "apps"
    # else skip (never a loose match)
    briefs3 = [
        PersonaBrief(
            role_id="marketing", display_name="M", goals=["g"], answers_for=["copy"]
        )
    ]
    assert resolve_requirement_owner(sec, briefs3) is None


def test_requirement_domains_enumerates_registry_not_yaml():
    doms = requirement_domains()
    areas = [d.area for d in doms]
    assert areas == ["problem", "data", "ux", "ops", "security", "compliance"]
    assert requirement_domains(["security", "nope"]) == [get_domain("security")]


# ── FR-RP-4 grounding: two severities, temporal port, soften=flags-only ───────


def test_grounding_schema_absence_is_high():
    flags = ground_requirement(
        text="The system MUST link a Ghost record.",
        entities_referenced=["Ghost"],
        brief="A store.",
        schema_entities=["User", "Order"],
    )
    assert any(f.severity == SEV_HIGH and f.kind == "schema-absence" for f in flags)


def test_grounding_money_advisory_year_advisory_low_bare_month_clean():
    flags = ground_requirement(
        text="The system MUST hit $2M ARR and ship by 2027; it may improve latency.",
        entities_referenced=[],
        brief="A store.",
        schema_entities=[],
    )
    sev = {f.kind: f.severity for f in flags}
    assert sev.get("money") == SEV_ADVISORY  # $2M unsupported
    assert sev.get("year") == SEV_ADVISORY_LOW  # 2027 floods → advisory-low
    assert "date" not in sev  # bare "may" is NOT a temporal flag (ported exclusion)


def test_grounding_supported_specific_passes():
    flags = ground_requirement(
        text="The system MUST reach $2M ARR.",
        entities_referenced=[],
        brief="Target is $2M ARR this year.",
        schema_entities=[],
    )
    assert not any(f.kind == "money" for f in flags)


# ── FR-RP-7 sanitization (R1-F5) + gate reconciliation (R2-S5) ────────────────


@pytest.mark.parametrize(
    "line",
    ["# h1 injected", "###### h6 injected", "## view: Injected"],
)
def test_sanitize_neutralizes_atx_headings(line):
    text = f"body\n{line}\nmore"
    out = neutralize_headings(text)
    assert f"> {line}" in out
    assert not has_unsafe_heading(out)


def test_sanitize_neutralizes_setext():
    text = "Injected Title\n---\nbody"
    out = neutralize_headings(text)
    assert has_unsafe_heading(text) is True
    assert has_unsafe_heading(out) is False


def test_blockquote_demoted_passes_bare_heading_fails_gate():
    # R2-S5: a demoted heading is safe; a bare line-start heading is not.
    demoted = RequirementCandidate(
        area="ux", title="T", body="ok\n> ## safe", provenance=PROV_ESTIMATE
    )
    bare = RequirementCandidate(
        area="ux", title="T2", body="ok\n## unsafe", provenance=PROV_ESTIMATE
    )
    assert check_readiness(RequirementDoc(title="d", candidates=[demoted])).ok is True
    assert check_readiness(RequirementDoc(title="d", candidates=[bare])).ok is False


# ── FR-RP-3 synthesis ($0, keep-both dedupe, conflicts→OQ) ────────────────────


def _cand(area, title, body, role="r", prov=PROV_ESTIMATE):
    return RequirementCandidate(
        area=area, title=title, body=body, role_id=role, provenance=prov
    )


def test_synthesis_merges_identical_keeps_distinct():
    base = RequirementDoc(title="d")
    a = _cand(
        "security",
        "Encrypt at rest",
        "The system MUST encrypt data at rest.",
        role="s1",
    )
    a_dup = _cand(
        "security",
        "Encrypt at rest",
        "The system MUST encrypt data at rest.",
        role="s2",
    )
    b = _cand("security", "Encrypt in transit", "The system MUST use TLS.", role="s1")
    doc = synthesize(base, [a, a_dup, b])
    titles = sorted(c.title for c in doc.candidates)
    assert titles == [
        "Encrypt at rest",
        "Encrypt in transit",
    ]  # dup merged, distinct kept


def test_synthesis_conflict_lifts_to_open_question_never_drops():
    base = RequirementDoc(title="d")
    a = _cand("ops", "Retention", "The system MUST retain logs 30 days.", role="ops1")
    b = _cand("ops", "Retention", "The system MUST retain logs 1 year.", role="legal")
    doc = synthesize(base, [a, b])
    assert len([c for c in doc.candidates if c.title == "Retention"]) == 1  # first kept
    assert any("Conflicting requirements" in oq for oq in doc.open_questions)
    assert any(
        "1 year" in oq for oq in doc.open_questions
    )  # alternative preserved verbatim


def test_synthesis_all_survive_no_llm():
    base = scaffold("", SCHEMA)  # 2 baseline stubs
    extra = [_cand("security", "Authz", "The system MUST enforce RBAC.")]
    doc = synthesize(base, extra)
    assert len(doc.candidates) == 3  # both baseline + the role FR


# ── FR-RP-5 provenance (per-FR, distinct baseline constant) ───────────────────


def test_baseline_stub_is_not_is_estimate():
    from startd8.stakeholder_panel.models import Recommendation
    from startd8.stakeholder_panel.recommend_provenance import is_estimate

    stub = scaffold("", SCHEMA).candidates[0]
    # A baseline stub must NOT satisfy the panel's is_estimate (no panel:<role> origin) — R2-S3.
    rec = Recommendation(
        domain="data",
        value_path="x",
        recommended_value="v",
        provenance=stub.provenance,  # "baseline"
        origin="",
    )
    assert is_estimate(rec) is False


def test_provenance_manifest_is_per_fr():
    base = scaffold("", SCHEMA)
    doc = synthesize(
        base, [_cand("security", "Authz", "The system MUST enforce RBAC.")]
    )
    manifest = doc.provenance_manifest()
    assert set(manifest.values()) == {PROV_BASELINE, PROV_ESTIMATE}
    assert len(manifest) == len(doc.candidates)
