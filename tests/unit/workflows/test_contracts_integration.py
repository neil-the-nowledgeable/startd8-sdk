"""Quick-win ContextCore contract checks — preflight (L3) + contract-drift (L7).

These are optional + import-guarded: in an environment without ``contextcore.contracts`` they MUST
degrade to a no-op (return ``True`` / ``None``) and never raise. Where ContextCore *is* importable,
the real-path assertions run; otherwise they skip. (At time of writing the SDK venv lacks
``contextcore.contracts``, so the guard paths are what's exercised by default.)
"""

from pathlib import Path
from types import SimpleNamespace


from startd8.workflows._contracts_integration import compare_contracts, run_preflight

pytestmark = []

_CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "src/startd8/contractors/contracts/plan-ingestion.contract.yaml"
)


def _wf(contract_path=None):
    return SimpleNamespace(metadata=SimpleNamespace(contract_path=contract_path))


def test_preflight_noop_without_contract_path():
    # No contract declared → always proceed, never touch ContextCore.
    assert run_preflight(_wf(None), {"any": "config"}) is True


def test_preflight_never_raises_with_a_contract_path():
    # Whether ContextCore is present (real check) or absent (guarded no-op), it returns a bool and
    # never raises — and with default (advisory) severity it must allow the run to proceed.
    result = run_preflight(_wf(str(_CONTRACT)), {"domain": "test"})
    assert result is True  # advisory by default → proceed


def test_preflight_bad_contract_path_is_graceful():
    # A nonexistent contract path must not break the run (checker/load error is swallowed → True).
    assert run_preflight(_wf("/no/such/contract.yaml"), {}) is True


def test_compare_contracts_is_graceful():
    # Off-run drift check: returns None when regression module is unavailable, else a DriftReport.
    out = compare_contracts(str(_CONTRACT), str(_CONTRACT))
    try:
        import contextcore.contracts.regression.drift  # noqa: F401
    except ImportError:
        assert out is None  # guarded no-op
    else:
        # comparing a contract with itself → no propagation-breaking drift
        assert out is not None
        assert hasattr(out, "changes") or hasattr(out, "has_breaking_changes")


def test_fail_closed_flag_is_accepted():
    # The fail_closed path must be callable; without a contract it still proceeds.
    assert run_preflight(_wf(None), {}, fail_closed=True) is True
