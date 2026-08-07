"""REQ-02 OQ-1 — cross-repo parity guard for the Workflow Dry-Run vocabulary (the single-source triad).

The AUTHORITATIVE ``WouldAct`` enum + ``DryRunVerdict`` schema live in **contextcore**
(``contracts.dry_run``). startd8-sdk carries only a plain ``dry_run``/``dry_run_trace`` on ``WorkflowLoopJob``
(no contextcore import — the ``admit_from_wlq`` "read JSON, don't import" seam) plus a guarded Literal MIRROR
of the ``would_act`` values (``DRY_RUN_WOULD_ACT_VALUES``). This guard fails on drift in EITHER direction —
the same pattern as ``tests/.../test_conversation_kernel_parity.py`` (CVM FR-17) and GRADER_AGGREGATE_INPUT_KEYS.

Two-way:
  (1) startd8's mirror == the vendored contract snapshot (always runs, no sibling repo needed — CI-safe).
  (2) the vendored snapshot == the LIVE contextcore authority (runs only when contextcore is importable) — so
      the snapshot itself cannot silently rot away from the source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.workflows.loop_queue.models import (
    DRY_RUN_WOULD_ACT_VALUES,
    WorkflowLoopJob,
)

_CONTRACT = (
    Path(__file__).resolve().parents[4]
    / "tests" / "fixtures" / "dry_run" / "contextcore-dryrunverdict.contract.json"
)


def _load_contract() -> dict:
    return json.loads(_CONTRACT.read_text(encoding="utf-8"))


def test_startd8_mirror_matches_vendored_contract():
    """(1) The startd8-side ``would_act`` mirror == the vendored contextcore contract (fails on drift)."""
    contract = _load_contract()
    assert list(DRY_RUN_WOULD_ACT_VALUES) == contract["would_act_values"], (
        "startd8 DRY_RUN_WOULD_ACT_VALUES drifted from the vendored contextcore contract — "
        "coordinate the schema change in contextcore.contracts.dry_run first, then update the snapshot."
    )


def test_vendored_contract_matches_live_contextcore_authority():
    """(2) The vendored snapshot == the LIVE contextcore authority — so the snapshot can't rot.

    Skips when contextcore's dry_run module is not importable (a fresh startd8 CI without the sibling repo);
    (1) still fully guards the startd8 mirror against the snapshot in that case."""
    dr = pytest.importorskip(
        "contextcore.contracts.dry_run",
        reason="contextcore.contracts.dry_run not importable — snapshot guards the mirror standalone",
    )
    contract = _load_contract()
    assert list(dr.WOULD_ACT_VALUES) == contract["would_act_values"], (
        "the vendored contract snapshot drifted from the live contextcore WouldAct authority — "
        "regenerate tests/fixtures/dry_run/contextcore-dryrunverdict.contract.json from contextcore."
    )
    # the verdict field set is also part of the contract the job's dry_run_trace dicts carry
    assert list(dr._VERDICT_FIELDS) == contract["verdict_fields"], (
        "DryRunVerdict field set drifted from the snapshot"
    )


def test_workflow_loop_job_carries_additive_dry_run_fields():
    """FR-1: the additive fields exist, default correctly, and an old 0.1.0 job still validates (NR-4)."""
    new = WorkflowLoopJob(
        job_id="j-new", loop_id="l", executor="sdk-workflow", workflow_id="w"
    )
    assert new.schema_version == "0.1.1"
    assert new.dry_run is False and new.dry_run_trace == []

    old = WorkflowLoopJob.model_validate(
        {
            "schema_version": "0.1.0",
            "job_id": "j-old",
            "loop_id": "l",
            "executor": "sdk-workflow",
            "workflow_id": "w",
        }
    )
    assert old.schema_version == "0.1.0"
    assert old.dry_run is False and old.dry_run_trace == []  # additive default under extra="forbid"

    dry = WorkflowLoopJob(
        job_id="j-dry", loop_id="l", executor="sdk-workflow", workflow_id="w", dry_run=True
    )
    # round-trips through model_dump/model_validate (the on-disk form)
    reloaded = WorkflowLoopJob.model_validate(dry.model_dump(mode="json"))
    assert reloaded.dry_run is True
