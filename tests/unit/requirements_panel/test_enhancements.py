# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M-series enhancement tests: shared toolkit (FR-PD-*), default roster (FR-RP-10),
coverage score (FR-RP-11)."""

from __future__ import annotations

from startd8.persona_drafting import (
    JsonSessionStore,
    has_unsafe_heading,
    neutralize_headings,
    resolve_bounded_owner,
)
from startd8.requirements_panel import (
    PROV_BASELINE,
    PROV_ESTIMATE,
    RequirementCandidate,
    RequirementDoc,
    coverage_report,
    default_roster_text,
    install_default_roster,
    scaffold,
    synthesize,
)
from startd8.requirements_panel.store import CandidateStore
from startd8.stakeholder_panel.models import PersonaBrief

SCHEMA = "model User { id String @id\n name String\n}\nmodel Order { id String @id\n userId String\n}"


# ── FR-PD-1 sanitize is shared (behavior-preserving) ──────────────────────────


def test_toolkit_sanitize_is_the_same_object():
    from startd8.requirements_panel import sanitize as rp_sanitize

    # requirements_panel.sanitize re-exports the toolkit implementation (P2)
    assert rp_sanitize.neutralize_headings is neutralize_headings
    out = neutralize_headings("body\n## injected")
    assert "> ## injected" in out and not has_unsafe_heading(out)


# ── FR-PD-2/FR-PD-3 shared store base + GC (backlog #9) ───────────────────────


def test_candidate_store_uses_toolkit_base_and_gcs(tmp_path):
    assert issubclass(CandidateStore, JsonSessionStore)
    for i in range(5):
        CandidateStore(tmp_path, f"elicit-{i}").save(
            [
                RequirementCandidate(
                    area="data", title=f"T{i}", body="The system MUST x."
                )
            ]
        )
    assert len(CandidateStore.session_ids(tmp_path)) == 5
    deleted = CandidateStore.gc(tmp_path, keep=2)
    assert len(deleted) == 3
    assert len(CandidateStore.session_ids(tmp_path)) == 2


def test_candidate_store_roundtrip(tmp_path):
    store = CandidateStore(tmp_path, "elicit-x")
    store.save(
        [RequirementCandidate(area="ux", title="Flow", body="The system MUST guide.")]
    )
    loaded = store.load()
    assert loaded[0].title == "Flow"


# ── FR-PD-4 shared bounded owner-resolution ───────────────────────────────────


def test_resolve_bounded_owner_default_alias_skip():
    briefs = [PersonaBrief(role_id="security", display_name="S", goals=["g"])]
    assert (
        resolve_bounded_owner(
            owning_role="security", aliases=(), symbol="security", briefs=briefs
        )
        == "security"
    )
    briefs2 = [
        PersonaBrief(
            role_id="apps", display_name="A", goals=["g"], answers_for=["authz"]
        )
    ]
    assert (
        resolve_bounded_owner(
            owning_role="security",
            aliases=("authz",),
            symbol="security",
            briefs=briefs2,
        )
        == "apps"
    )
    briefs3 = [
        PersonaBrief(role_id="mkt", display_name="M", goals=["g"], answers_for=["copy"])
    ]
    assert (
        resolve_bounded_owner(
            owning_role="security",
            aliases=("authz",),
            symbol="security",
            briefs=briefs3,
        )
        is None
    )


def test_requirement_resolver_delegates_to_toolkit():
    # resolve_requirement_owner still behaves identically after delegation.
    from startd8.requirements_panel.domains import get_domain, resolve_requirement_owner

    sec = get_domain("security")
    briefs = [PersonaBrief(role_id="security", display_name="S", goals=["g"])]
    assert resolve_requirement_owner(sec, briefs) == "security"


# ── FR-RP-10 default roster ───────────────────────────────────────────────────


def test_default_roster_is_valid_and_covers_all_areas():
    from startd8.stakeholder_panel import load_roster, validate_roster
    from startd8.requirements_panel.domains import DEFAULT_DOMAINS

    text = default_roster_text()
    assert "domain: stakeholders" in text
    # writes to a temp file, parses + validates clean via the panel's own loader
    import tempfile
    import os

    fd, name = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    from pathlib import Path

    Path(name).write_text(text, encoding="utf-8")
    roster = load_roster(name)
    assert validate_roster(roster) == []
    role_ids = {p.role_id for p in roster.personas}
    # every RequirementDomain owning_role has a matching persona (clean resolution, no fallback needed)
    assert {d.owning_role for d in DEFAULT_DOMAINS} <= role_ids


def test_install_default_roster_refuses_clobber(tmp_path):
    r1 = install_default_roster(tmp_path)
    assert r1.written is True and r1.path.is_file()
    original = r1.path.read_bytes()
    r2 = install_default_roster(tmp_path)
    assert r2.written is False and "already exists" in r2.reason
    assert r1.path.read_bytes() == original
    r3 = install_default_roster(tmp_path, force=True)
    assert r3.written is True


def test_default_roster_resolves_every_requirement_area():
    # End-to-end: the shipped roster resolves an owner for all 6 areas (no skips).
    from startd8.requirements_panel.domains import (
        requirement_domains,
        resolve_requirement_owner,
    )
    from startd8.stakeholder_panel.roster import parse_roster

    roster = parse_roster(default_roster_text())
    briefs = roster.personas
    for dom in requirement_domains():
        assert resolve_requirement_owner(dom, briefs) is not None, dom.area


# ── FR-RP-11 advisory coverage score ──────────────────────────────────────────


def _cand(area, title, body, prov=PROV_ESTIMATE, flags=None):
    return RequirementCandidate(
        area=area, title=title, body=body, provenance=prov, flags=flags or []
    )


def test_coverage_reports_provenance_split_and_paid_delta():
    base = scaffold("", SCHEMA)  # 2 baseline 'data' stubs
    doc = synthesize(base, [_cand("security", "RBAC", "The system MUST enforce RBAC.")])
    rep = coverage_report(doc)
    assert rep.total_frs == 3
    assert rep.by_area["data"][PROV_BASELINE] == 2
    assert rep.by_area["security"][PROV_ESTIMATE] == 1
    assert "security" in rep.areas_with_role_input  # paid-pass value delta
    assert "data" in rep.areas_baseline_only
    assert rep.unowned_stubs == 2  # the two baseline <needs-owner> stubs


def test_coverage_counts_flags_by_severity_and_near_duplicates():
    doc = RequirementDoc(
        title="d",
        candidates=[
            _cand(
                "ops",
                "Retain logs 30 days",
                "The system MUST retain logs.",
                flags=["advisory-low: year: 2027"],
            ),
            _cand(
                "ops",
                "Retain logs 90 days",
                "The system MUST keep logs.",
                flags=["high: schema-absence: x"],
            ),
        ],
    )
    rep = coverage_report(doc)
    assert rep.flags_by_severity.get("advisory-low") == 1
    assert rep.flags_by_severity.get("high") == 1
    # "Retain logs 30 days" ~ "Retain logs 90 days" share {retain, logs, days} → near-duplicate surfaced
    assert len(rep.near_duplicates) == 1


def test_coverage_is_advisory_not_a_gate():
    # coverage never blocks; a doc that fails readiness still yields a report.
    doc = scaffold("", SCHEMA)
    rep = coverage_report(doc)
    assert rep.total_frs == 2  # produced regardless of readiness state
    assert rep.render().startswith("coverage:")
