"""ContextCore defense-in-depth contract checks — the single integration surface.

Covers preflight (L3), exit validation (L4), post-exec (L5) and contract-drift (L7).
All are optional + import-guarded: without ``contextcore.contracts`` they degrade to a
no-op (``True`` / ``None``) and never raise. Where ContextCore is importable, the real
paths run against a minimal valid ``ContextContract`` fixture (the SDK's own
``*.contract.yaml`` are Artisan/gate-schema, not ContextContracts).

These tests also pin the fix for a class of latent bugs: the historical
``ContractLoader.load_contract(str)`` did not exist (it is ``ContractLoader().load(Path)``),
and ``PreflightResult``/``ContractValidationResult`` have no ``critical_/has_blocking_
violations()`` helpers — so preflight/exit ``fail_closed`` were silently dead. The
fail_closed assertions below would fail if that regresses.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from startd8.workflows._contracts_integration import (
    compare_contracts,
    run_exit_validation,
    run_postexec,
    run_preflight,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal_context_contract.yaml"

_HAS_CC = True
try:  # the real-path assertions only run when ContextCore is installed
    import contextcore.contracts.preflight.checker  # noqa: F401
except ImportError:  # pragma: no cover
    _HAS_CC = False

requires_cc = pytest.mark.skipif(not _HAS_CC, reason="contextcore.contracts not installed")


def _wf(contract_path=None):
    return SimpleNamespace(metadata=SimpleNamespace(contract_path=contract_path))


# ── No-op / guard paths (always run) ────────────────────────────────────


def test_preflight_noop_without_contract_path():
    assert run_preflight(_wf(None), {"any": "config"}) is True


def test_exit_validation_noop_without_contract_path():
    assert run_exit_validation("wf", _wf(None), {"out": 1}) is None


def test_postexec_noop_without_contract_path():
    assert run_postexec(_wf(None), {"out": 1}) is None


def test_preflight_bad_contract_path_is_graceful():
    # A nonexistent contract must not break the run (load error swallowed → proceed).
    assert run_preflight(_wf("/no/such/contract.yaml"), {}) is True


def test_fail_closed_flag_accepted_without_contract():
    assert run_preflight(_wf(None), {}, fail_closed=True) is True


# ── Real ContextContract paths ──────────────────────────────────────────


@requires_cc
def test_preflight_passes_with_satisfied_initial_context():
    assert run_preflight(_wf(str(_FIXTURE)), {"project_id": "p"}) is True


@requires_cc
def test_preflight_missing_field_is_advisory_by_default():
    # Missing required `project_id` → warn but proceed (advisory default, FR-CC-4).
    assert run_preflight(_wf(str(_FIXTURE)), {}) is True


@requires_cc
def test_preflight_fail_closed_blocks_on_missing_blocking_field():
    # The fix: criticality derived from violation severity == BLOCKING (no dead helper).
    assert run_preflight(_wf(str(_FIXTURE)), {}, fail_closed=True) is False


@requires_cc
def test_exit_validation_passes_when_exit_requirements_met():
    assert run_exit_validation("ingest", _wf(str(_FIXTURE)), {"plan": "x"}) is None


@requires_cc
def test_exit_validation_advisory_by_default_on_missing():
    assert run_exit_validation("ingest", _wf(str(_FIXTURE)), {}) is None


@requires_cc
def test_exit_validation_fail_closed_returns_error_message():
    msg = run_exit_validation("ingest", _wf(str(_FIXTURE)), {}, fail_closed=True)
    assert msg and "exit validation failed" in msg


@requires_cc
def test_postexec_returns_report():
    rep = run_postexec(_wf(str(_FIXTURE)), {"project_id": "p", "plan": "x", "artifacts": "a"})
    assert rep is not None
    assert hasattr(rep, "passed")


@requires_cc
def test_compare_contract_with_itself_has_no_drift():
    out = compare_contracts(str(_FIXTURE), str(_FIXTURE))
    assert out is not None
    assert getattr(out, "breaking_count", None) == 0
    assert getattr(out, "total_changes", None) == 0


# ── FR-CC-4: findings emit via get_logger (the SDK's OTel log bridge → Loki) ──


@requires_cc
def test_preflight_findings_are_logged(caplog):
    """Advisory findings must be observable (FR-CC-4). get_logger carries the OTel
    log bridge, so a warning record here is also exported to Loki in a live run."""
    import logging

    with caplog.at_level(logging.WARNING, logger="startd8.workflows._contracts_integration"):
        run_preflight(_wf(str(_FIXTURE)), {})  # missing project_id → advisory warning
    assert any("preflight" in r.message for r in caplog.records)


@requires_cc
def test_exit_validation_findings_are_logged(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="startd8.workflows._contracts_integration"):
        run_exit_validation("ingest", _wf(str(_FIXTURE)), {})  # missing plan → warning
    assert any("exit-validation" in r.message for r in caplog.records)
