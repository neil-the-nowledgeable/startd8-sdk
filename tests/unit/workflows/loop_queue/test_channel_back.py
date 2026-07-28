# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Channel-back enqueue-caller — acceptance = compact-declared-base remand.

The implement-tick withdrawal for ``compact-declared-base`` (transport-gate
premise FALSE; real root = unmatched-bucket attribution to ``components[0]``)
is the first exercise of ``enqueue_withdrawal_remand``. Acceptance: the drained
bundle opens with the corrected premise in ``{{scope}}``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.workflows.loop_queue import (
    DrainHandoff,
    LoopJobStatus,
    LoopQueueConfig,
    LoopQueueValidationError,
    WithdrawalCause,
    WithdrawalVerdict,
    WorkflowLoopQueue,
    enqueue_withdrawal_remand,
)

#: Condensed from the grounded Step-1 remand envelope
#: (``analysis/remediation-design/remand-compact-declared-base.job.json``).
#: Load-bearing claims only — enough to prove the wire carries the corrected
#: premise into the drained bundle's ``{{scope}}`` slot.
_COMPACT_DECLARED_BASE_VERDICT = """\
REMAND. The prior design (transport-gate convention request-RED on \
`transport == ""`) was WITHDRAWN at the implement tick: its premise is \
factually false and the gate is a verified no-op. Do NOT reuse the transport gate.

WHAT IS DISPROVEN (verified):
(1) compact.transport is 'http', NOT ''.
(2) The dead SLIs are DECLARED-SERIES SLOs from generate_declared_base_slos \
(`compact-declared-base/*`), bound via DeclaredEmittedSeries.covers — NOT \
convention base-RED.

THE ACTUAL ROOT CAUSE: with resolved_prefixes == {}, subject_plan.render_plan \
attributes the entire unmatched bucket to components[0] (== 'compact'). All 243 \
families land under ## compact; the other six services declare none. Fix lives \
in ContextCore repoprobe/subject_plan.py — drop the components[0] fallback.
"""

_FINDING_ID = "derivation_0_compact-declared-base_20_dead_slis_live_binding_0.3069"


def _design_dir(tmp_path: Path) -> tuple[Path, Path]:
    """Parent dirs must exist at enqueue (reflective validation); files may not."""
    design = tmp_path / "remediation-design" / _FINDING_ID
    design.mkdir(parents=True)
    return design / "requirements.md", design / "plan.md"


def test_compact_declared_base_remand_is_acceptance(
    tmp_path: Path,
) -> None:
    """Acceptance: enqueue_withdrawal_remand + drain opens with corrected premise.

    Mirrors the hand-authored Step-1 envelope, but through the auto-wire.
    """
    reqs, plan = _design_dir(tmp_path)
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))

    job = enqueue_withdrawal_remand(
        queue,
        WithdrawalVerdict(
            cause=WithdrawalCause.DESIGN_PREMISE_INVALID,
            scope=_COMPACT_DECLARED_BASE_VERDICT,
            finding_id=_FINDING_ID,
        ),
        requirements_path=reqs,
        plan_path=plan,
    )

    assert job.status is LoopJobStatus.PENDING
    assert job.loop_id == "reflective-requirements"
    assert job.executor.value == "agent-surface"
    assert job.metadata.get("channel_back") is True
    assert job.metadata.get("withdrawal_cause") == "design_premise_invalid"
    assert job.metadata.get("finding_id") == _FINDING_ID
    assert job.job_id.startswith("refl-remand-")
    assert "compact-declared-base" in job.job_id
    assert job.config["requirements_path"] == str(reqs)
    assert job.config["plan_path"] == str(plan)

    handoff = queue.run_next(job.job_id)
    assert isinstance(handoff, DrainHandoff)
    assert handoff.loop_id == "reflective-requirements"
    bundle = Path(handoff.bundle_path).read_text(encoding="utf-8")

    # The drained bundle MUST open with the corrected premise (doc acceptance).
    assert bundle.startswith("# Reflective Requirements — REMAND.")
    assert "transport-gate" in bundle
    assert "verified no-op" in bundle
    assert "components[0]" in bundle
    assert "DeclaredEmittedSeries.covers" in bundle
    assert "Do NOT reuse the transport gate" in bundle
    assert str(reqs) in bundle
    assert str(plan) in bundle


def test_implementation_failure_does_not_channel_back(tmp_path: Path) -> None:
    """Patch-hard / tests-red stay on the implement tick — refuse silently."""
    reqs, plan = _design_dir(tmp_path)
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="does not channel back"):
        enqueue_withdrawal_remand(
            queue,
            WithdrawalVerdict(
                cause=WithdrawalCause.IMPLEMENTATION_FAILURE,
                scope="tests red after patch",
                finding_id="x",
            ),
            requirements_path=reqs,
            plan_path=plan,
        )


def test_empty_verdict_refused(tmp_path: Path) -> None:
    reqs, plan = _design_dir(tmp_path)
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="scope is empty"):
        enqueue_withdrawal_remand(
            queue,
            WithdrawalVerdict(
                cause=WithdrawalCause.DESIGN_PREMISE_INVALID,
                scope="   ",
                finding_id="x",
            ),
            requirements_path=reqs,
            plan_path=plan,
        )


def test_explicit_job_id_honoured(tmp_path: Path) -> None:
    reqs, plan = _design_dir(tmp_path)
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    job = enqueue_withdrawal_remand(
        queue,
        WithdrawalVerdict(
            cause=WithdrawalCause.DESIGN_PREMISE_INVALID,
            scope="REMAND. premise false.",
            finding_id=_FINDING_ID,
        ),
        requirements_path=reqs,
        plan_path=plan,
        job_id="refl-remand-compact-declared-base-accept",
    )
    assert job.job_id == "refl-remand-compact-declared-base-accept"
