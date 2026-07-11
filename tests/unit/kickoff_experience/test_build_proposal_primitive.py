# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Contract of the shared per-kind validation primitive `build_proposal` (FR-PU-1/2).

`build_proposal` is the single per-kind validator, shared by the agentic `make_propose_handler` and
the deterministic `project init` producer. It is pure: returns a typed `ProposedAction` on success,
raises a typed error on invalid input — never a message string, never a buffer side-effect.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from startd8.kickoff_experience.concierge_apply import ConciergeInputError
from startd8.kickoff_experience.proposals import (
    ProposalBuffer,
    ProposedAction,
    build_proposal,
    make_propose_handler,
)


def _root(tmp_path) -> str:
    return str(Path(os.path.realpath(tmp_path)))


# --- build_proposal: returns a typed action on success -------------------------------------------


def test_valid_instantiate_returns_action(tmp_path):
    action = build_proposal({"kind": "instantiate", "posture": "prototype"}, project_root=_root(tmp_path))
    assert isinstance(action, ProposedAction)
    assert action.kind == "instantiate"
    assert action.params == {"posture": "prototype"}
    assert action.id  # an id is assigned


def test_valid_friction_returns_action(tmp_path):
    action = build_proposal(
        {"kind": "friction", "friction": "a", "what_happened": "b", "implication": "c"},
        project_root=_root(tmp_path),
    )
    assert action.kind == "friction"


# --- build_proposal: raises typed errors (no strings, no buffer) ----------------------------------


def test_unknown_kind_raises_typed_error(tmp_path):
    with pytest.raises(ConciergeInputError) as exc:
        build_proposal({"kind": "nonsense"}, project_root=_root(tmp_path))
    assert exc.value.code == "unknown_kind"


def test_invalid_posture_raises_typed_error(tmp_path):
    with pytest.raises(ConciergeInputError):
        build_proposal({"kind": "instantiate", "posture": "banana"}, project_root=_root(tmp_path))


def test_empty_friction_raises_typed_error(tmp_path):
    with pytest.raises(ConciergeInputError):
        build_proposal(
            {"kind": "friction", "friction": "", "what_happened": "b", "implication": "c"},
            project_root=_root(tmp_path),
        )


def test_manifest_without_source_raises_typed_error(tmp_path):
    with pytest.raises(ConciergeInputError):
        build_proposal({"kind": "manifest", "source": ""}, project_root=_root(tmp_path))


# --- FR-PU-2: make_propose_handler's ack/error string contract is unchanged -----------------------


def test_handler_success_ack_unchanged(tmp_path):
    buf = ProposalBuffer()
    handler = make_propose_handler(_root(tmp_path), buf)
    ack = handler({"kind": "instantiate", "posture": "prototype"})
    assert "recorded a proposal" in ack
    assert len(buf.pending()) == 1  # still records on success


def test_handler_rejection_still_returns_error_string_and_records_nothing(tmp_path):
    buf = ProposalBuffer()
    handler = make_propose_handler(_root(tmp_path), buf)
    err = handler({"kind": "instantiate", "posture": "banana"})
    assert err.startswith("error:")
    assert len(buf.pending()) == 0  # rejection records nothing


def test_handler_unknown_kind_still_errors(tmp_path):
    # Option B: unknown-kind now flows through the single "proposal rejected" error path.
    buf = ProposalBuffer()
    err = make_propose_handler(_root(tmp_path), buf)({"kind": "nope"})
    assert err.startswith("error:")
    assert len(buf.pending()) == 0
