# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M0 contract tests for the VIPP Keiyaku models (FR-2, FR-6, FR-8, FR-13).

Covers: full nested JSON-canonical round-trip identity, markdown is derived/lossy (no from_markdown),
every claim label is a valid shared FDE ClaimLabel, PROTOCOL_VERSION is decoupled from the SDK
version, the host-shape pin (so ProposedAction drift fails loudly), and the reject-future guard.
"""

from __future__ import annotations

import dataclasses

from startd8.fde.models import ClaimLabel, LabeledClaim
from startd8.vipp.models import (
    HOST_PROPOSAL_FIELDS,
    PROTOCOL_VERSION,
    Decision,
    EnvelopedProposal,
    ProposalEnvelope,
    VippDisposition,
    VippReport,
    protocol_is_future,
)


def _sample_report() -> VippReport:
    """A report exercising all three decisions, params, base_sha, and labeled claims."""
    claim_obs = LabeledClaim(
        label=ClaimLabel.OBSERVED,
        text="app.tables has no `Match` entity",
        source="sapper:invented_entity",
        claim_id="fp-abc123",
    )
    claim_mech = LabeledClaim(
        label=ClaimLabel.MECHANISM,
        text="schema kind routes through promote_schema",
        source="proposals.py:343",
        claim_id="mech-1",
    )
    return VippReport(
        project_id="proj-xyz",
        generated_at="2026-06-30T00:00:00Z",
        envelope_seq=7,
        evidence_available=True,
        sdk_version="0.4.0",
        cost_usd=0.0,
        llm_used=False,
        dispositions=[
            VippDisposition(
                proposal_id="p1",
                decision=Decision.ACCEPT,
                envelope_seq=7,
                reason="entity present in ground truth",
                claims=[claim_obs, claim_mech],
            ),
            VippDisposition(
                proposal_id="p2",
                decision=Decision.REJECT,
                envelope_seq=7,
                reason="invented entity refuted by Sapper",
                claims=[claim_obs],
            ),
            VippDisposition(
                proposal_id="p3",
                decision=Decision.COUNTER,
                envelope_seq=7,
                reason="corrected field name",
                counter_params={"value_path": "profile.display_name", "value": "x"},
                claims=[claim_obs],
            ),
        ],
    )


def _sample_envelope() -> ProposalEnvelope:
    return ProposalEnvelope(
        project_id="proj-xyz",
        envelope_seq=7,
        generated_at="2026-06-30T00:00:00Z",
        content_checksum="sha256:deadbeef",
        proposals=[
            EnvelopedProposal(
                kind="schema",
                params={
                    "brief": "Entities: Profile",
                    "contract_path": "prisma/schema.prisma",
                },
                id="p1",
                base_sha=None,
            ),
            EnvelopedProposal(
                kind="capture",
                params={"value_path": "profile.headline", "value": "hi"},
                id="p3",
                base_sha="sha256:cafef00d",
            ),
        ],
    )


# --- FR-2: JSON-canonical full-graph round-trip identity ------------------------------------------


def test_report_round_trip_is_identity():
    report = _sample_report()
    assert VippReport.from_json(report.to_dict()).to_dict() == report.to_dict()


def test_report_round_trip_through_json_string():
    import json

    report = _sample_report()
    rebuilt = VippReport.from_json(json.dumps(report.to_dict()))
    assert rebuilt.to_dict() == report.to_dict()


def test_envelope_round_trip_is_identity():
    env = _sample_envelope()
    assert ProposalEnvelope.from_json(env.to_dict()).to_dict() == env.to_dict()


def test_disposition_round_trip_preserves_decision_enum_and_counter_params():
    disp = _sample_report().dispositions[2]  # the COUNTER
    rebuilt = VippDisposition.from_dict(disp.to_dict())
    assert rebuilt.decision is Decision.COUNTER
    assert rebuilt.counter_params == {
        "value_path": "profile.display_name",
        "value": "x",
    }
    assert rebuilt.to_dict() == disp.to_dict()


def test_enveloped_proposal_preserves_base_sha_and_params_verbatim():
    p = _sample_envelope().proposals[1]  # capture, with base_sha
    rebuilt = EnvelopedProposal.from_dict(p.to_dict())
    assert rebuilt.base_sha == "sha256:cafef00d"
    assert rebuilt.params == {"value_path": "profile.headline", "value": "hi"}


# --- FR-2: markdown is a derived, lossy view (no from_markdown) ------------------------------------


def test_markdown_is_derived_and_lossy():
    report = _sample_report()
    md = report.to_markdown()
    assert "VIPP Dispositions" in md
    assert "ACCEPT" in md and "REJECT" in md and "COUNTER" in md
    # No round-trip promise from markdown — the parse direction must not exist.
    assert not hasattr(VippReport, "from_markdown")
    assert not hasattr(VippDisposition, "from_markdown")


def test_prompt_section_preserves_labels():
    section = _sample_report().to_prompt_section()
    assert "OBSERVED (project)" in section
    assert "MECHANISM (sdk)" in section


# --- FR-6: claims reuse the shared FDE label vocabulary -------------------------------------------


def test_all_claims_carry_valid_shared_labels():
    for disp in _sample_report().dispositions:
        for claim in disp.claims:
            assert isinstance(claim, LabeledClaim)
            assert claim.label in set(ClaimLabel)


# --- FR-13: PROTOCOL_VERSION is decoupled from the SDK version -------------------------------------


def test_protocol_version_is_independent_of_sdk_version():
    import startd8

    assert PROTOCOL_VERSION == "1.0"
    sdk_version = getattr(startd8, "__version__", None)
    # The contract version must not be tied to the SDK version (FR-13 / FDE R1-F3 parity).
    if sdk_version is not None:
        assert PROTOCOL_VERSION != sdk_version
    assert ProposalEnvelope(project_id="x").protocol_version == PROTOCOL_VERSION
    assert VippReport(project_id="x").protocol_version == PROTOCOL_VERSION


def test_reject_future_guard():
    assert protocol_is_future("2.0") is True
    assert protocol_is_future("1.0") is False
    assert protocol_is_future("1.5") is False  # same major is forward-within-v1
    assert protocol_is_future("0.9") is False


# --- FR-8: host-shape pin — EnvelopedProposal must mirror the live ProposedAction field set --------


def test_host_proposal_shape_pin():
    """If ProposedAction gains/loses a field, this fails loudly → bump PROTOCOL_VERSION (FR-8/13)."""
    from startd8.kickoff_experience.proposals import ProposedAction

    live_fields = {f.name for f in dataclasses.fields(ProposedAction)}
    assert live_fields == set(HOST_PROPOSAL_FIELDS), (
        "ProposedAction shape drifted from EnvelopedProposal's mirror "
        f"({live_fields} != {set(HOST_PROPOSAL_FIELDS)}); update the envelope + bump PROTOCOL_VERSION."
    )


def test_enveloped_proposal_does_not_import_peer_type():
    """FR-8: the contract model mirrors by dict shape, not by importing ProposedAction."""
    import startd8.vipp.models as vipp_models

    # The peer type must not be referenced in the contract module's namespace.
    assert not hasattr(vipp_models, "ProposedAction")
