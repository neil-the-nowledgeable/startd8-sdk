"""Optional ContextCore defense-in-depth contract checks (CONTEXTCORE_CONTRACTS_ADOPTION req).

The single integration surface (FR-CC-5) for the contract checks that bracket the propagation
boundary the registry validates, all routed through one ``ContractLoader`` path:

- :func:`run_preflight` — **L3 pre-flight** (quick win): validate the workflow ``config`` against its
  context contract **before** the run spends tokens (fail-before-spend).
- :func:`run_exit_validation` — **L4 boundary (exit)**: validate the workflow output against the
  contract after the run (the keystone the SDK already adopted — consolidated here, FR-CC-5).
- :func:`run_postexec` — **L5 post-exec**: end-to-end propagation-chain integrity + final exit
  requirements after all phases (FR-POST-1; L4 runtime cross-ref deferred — no runtime_summary passed).
- :func:`compare_contracts` — **L7 contract-drift** (off-run): compare two contract versions.

All are **optional + import-guarded** (FR-CC-1): absent ContextCore degrades to a no-op, never raises.
All are **contract-gated** (FR-CC-2): work happens only when a ``contract_path`` is present. Findings
emit via :func:`get_logger` (FR-CC-4: the SDK's OTel log bridge ships these to Loki). Default severity
is **advisory/warn**; the run-path checks block only in explicit ``fail_closed`` mode.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


def _contract_path(workflow: Any) -> Optional[str]:
    return getattr(getattr(workflow, "metadata", None), "contract_path", None)


def _load_contract(contract_path: str) -> Any:
    """Load a ``ContextContract`` via the (instance) ``ContractLoader``.

    ``ContractLoader.load`` is an instance method taking a ``Path`` — the historical
    ``ContractLoader.load_contract(str)`` call did not exist and silently broke every
    contract check (AttributeError swallowed by callers). This is the one correct path.
    """
    from contextcore.contracts.propagation.loader import ContractLoader

    return ContractLoader().load(Path(contract_path))


def _is_blocking(violation: Any) -> bool:
    """True when a violation's severity is BLOCKING (PreflightResult has no helper for this)."""
    sev = getattr(violation, "severity", None)
    return str(getattr(sev, "value", sev)).lower() == "blocking"


def run_preflight(
    workflow: Any, config: Dict[str, Any], *, fail_closed: bool = False
) -> bool:
    """L3 pre-flight verification *before* a workflow runs (FR-PRE-1/2/3).

    Validates ``config`` (initial context) against the workflow's context contract, letting the
    contract's phase order default (OQ-2). With ``fail_closed`` a **blocking** violation returns
    ``False`` so the caller can stop *before any LLM spend*; otherwise it warns and returns ``True``.
    No-op + ``True`` when there is no contract or ContextCore/preflight is unavailable.
    """
    contract_path = _contract_path(workflow)
    if not contract_path:
        return True
    try:
        from contextcore.contracts.preflight.checker import PreflightChecker
    except ImportError:
        return True  # ContextCore / preflight module not installed — degrade silently
    try:
        contract = _load_contract(contract_path)
        # phase_order=None → defaults to contract.phases (OQ-2); initial_context = config.
        result = PreflightChecker().check(contract, config)
    except Exception as exc:  # a checker error must never break the run
        logger.debug("preflight: skipped (%s)", exc)
        return True

    if getattr(result, "passed", True):
        return True

    violations = list(getattr(result, "violations", []) or [])
    for v in violations:
        logger.warning("preflight: %s", getattr(v, "message", v))

    blocking = [v for v in violations if _is_blocking(v)]
    if fail_closed and blocking:
        logger.error(
            "preflight: %d blocking violation(s) — blocking before spend (fail-before-spend)",
            len(blocking),
        )
        return False
    return True


def run_exit_validation(
    workflow_id: str, workflow: Any, output: Any, *, fail_closed: bool = False
) -> Optional[str]:
    """L4 boundary (exit) validation of the workflow output against its contract.

    Advisory by default (FR-CC-4): logs blocking failures / warnings and returns ``None`` (proceed).
    With ``fail_closed`` a blocking failure returns an error message string so the caller can fail the
    run. No-op (``None``) without a contract or ContextCore.

    Consolidates the two previously-duplicated inline blocks in ``run``/``arun`` (FR-CC-5) and fixes
    the dead ``load_contract`` / ``has_blocking_violations`` calls that made exit validation a no-op.
    """
    contract_path = _contract_path(workflow)
    if not contract_path:
        return None
    try:
        from contextcore.contracts.propagation.validator import BoundaryValidator
    except ImportError as exc:
        logger.warning("exit-validation: ContextCore unavailable (%s)", exc)
        return None
    try:
        contract = _load_contract(contract_path)
        exit_context = output if isinstance(output, dict) else {"output": output}
        result = BoundaryValidator().validate_exit(workflow_id, exit_context, contract)
    except Exception as exc:  # validation must never crash the run
        logger.error("exit-validation: error (%s)", exc, exc_info=True)
        return None

    if getattr(result, "passed", True):
        return None

    for w in getattr(result, "warnings", []) or []:
        logger.warning("exit-validation: %s", w)
    blocking = list(getattr(result, "blocking_failures", []) or [])
    for b in blocking:
        logger.warning("exit-validation (blocking): %s", b)
    if fail_closed and blocking:
        return f"Context Contract exit validation failed: {len(blocking)} blocking failure(s)"
    return None


def run_postexec(
    workflow: Any, final_context: Dict[str, Any], *, fail_closed: bool = False
) -> Optional[Any]:
    """L5 post-execution validation after all phases complete (FR-POST-1/2).

    Runs ``PostExecutionValidator`` for end-to-end propagation-chain integrity + the final phase's
    exit requirements against ``final_context``. The L4 runtime-record cross-reference is **deferred**
    (no ``runtime_summary`` is passed — the SDK persists no L4 boundary records; OQ-5). Findings are
    logged (FR-CC-4 / FR-POST-2). Returns the ``PostExecutionReport`` (or ``None`` when there is no
    contract or ContextCore). ``fail_closed`` is advisory here (post-run): a failing report is logged
    at error level but the run has already completed.
    """
    contract_path = _contract_path(workflow)
    if not contract_path:
        return None
    try:
        from contextcore.contracts.postexec import PostExecutionValidator
    except ImportError:
        return None
    try:
        contract = _load_contract(contract_path)
        report = PostExecutionValidator().validate(contract, final_context)
    except Exception as exc:
        logger.debug("postexec: skipped (%s)", exc)
        return None

    if getattr(report, "passed", True):
        return report

    level = logger.error if fail_closed else logger.warning
    level(
        "postexec: contract integrity FAILED — %d/%d chains intact (%.0f%% complete), %d broken",
        getattr(report, "chains_intact", 0),
        getattr(report, "chains_total", 0),
        getattr(report, "completeness_pct", 0.0),
        getattr(report, "chains_broken", 0),
    )
    for d in getattr(report, "runtime_discrepancies", []) or []:
        logger.warning("postexec discrepancy: %s", getattr(d, "message", d))
    return report


def compare_contracts(old_path: str, new_path: str) -> Optional[Any]:
    """L7 contract-drift: compare two context-contract versions (FR-REG-1).

    Returns a ContextCore ``DriftReport`` (propagation-breaking changes: added/removed phases, a phase
    that stops producing a required field), or ``None`` if ContextCore/regression is unavailable.
    Fully off-run — safe to call from CI / ``manifest validate`` (FR-REG-2).
    """
    try:
        from contextcore.contracts.regression.drift import ContractDriftDetector
    except ImportError:
        return None
    old = _load_contract(old_path)
    new = _load_contract(new_path)
    return ContractDriftDetector().compare(old, new)
