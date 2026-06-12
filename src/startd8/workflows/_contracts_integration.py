"""Optional ContextCore defense-in-depth contract checks (CONTEXTCORE_CONTRACTS_ADOPTION req).

The single integration surface (FR-CC-5) for the contract checks that bracket the propagation
boundary validation the registry already does:

- :func:`run_preflight` — **L3 pre-flight** (the quick win): validate the workflow `config` against
  its context contract **before** the run spends any tokens (fail-before-spend).
- :func:`compare_contracts` — **L7 contract-drift** (off-run): compare two contract versions to
  detect propagation-breaking changes.

Both are **optional and import-guarded** (FR-CC-1): if ContextCore (or the relevant module) is
absent, they degrade to a no-op and never raise. Both are **contract-gated** (FR-CC-2): they only do
work when a `contract_path` / contract is present. Default severity is **advisory/warn** (FR-CC-4);
``run_preflight`` blocks only in explicit ``fail_closed`` mode.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


def run_preflight(
    workflow: Any, config: Dict[str, Any], *, fail_closed: bool = False
) -> bool:
    """L3 pre-flight verification *before* a workflow runs (FR-PRE-1/2/3).

    Validates ``config`` (the initial context) against the workflow's context contract, letting the
    contract's own phase order default. Findings are logged. With ``fail_closed`` a **critical**
    violation makes this return ``False`` so the caller can block *before any LLM spend*; otherwise it
    warns and returns ``True``. No-op + ``True`` when there is no contract or ContextCore/preflight is
    unavailable.

    Returns: ``True`` if the run may proceed, ``False`` only to block (fail_closed + critical).
    """
    contract_path = getattr(getattr(workflow, "metadata", None), "contract_path", None)
    if not contract_path:
        return True
    try:
        from contextcore.contracts.preflight.checker import PreflightChecker
        from contextcore.contracts.propagation.loader import ContractLoader
    except ImportError:
        return True  # ContextCore / preflight module not installed — degrade silently
    try:
        contract = ContractLoader.load_contract(contract_path)
        # phase_order=None → defaults to contract.phases (planning OQ-2); initial_context = config.
        result = PreflightChecker().check(contract, config)
    except Exception as exc:  # a checker error must never break the run
        logger.debug("preflight: skipped (%s)", exc)
        return True

    if getattr(result, "passed", True):
        return True

    for v in getattr(result, "violations", []) or []:
        logger.warning("preflight: %s", getattr(v, "message", v))

    critical = []
    try:
        critical = result.critical_violations()
    except Exception:  # pragma: no cover - defensive
        pass
    if fail_closed and critical:
        logger.error(
            "preflight: %d critical violation(s) — blocking before spend (fail-before-spend)",
            len(critical),
        )
        return False
    return True


def compare_contracts(old_path: str, new_path: str) -> Optional[Any]:
    """L7 contract-drift: compare two context-contract versions (FR-REG-1).

    Returns a ContextCore ``DriftReport`` (propagation-breaking changes: added/removed phases, a phase
    that stops producing a required field), or ``None`` if ContextCore/regression is unavailable.
    Fully off-run — safe to call from CI / ``manifest validate`` (FR-REG-2).
    """
    try:
        from contextcore.contracts.propagation.loader import ContractLoader
        from contextcore.contracts.regression.drift import ContractDriftDetector
    except ImportError:
        return None
    old = ContractLoader.load_contract(old_path)
    new = ContractLoader.load_contract(new_path)
    return ContractDriftDetector().compare(old, new)
