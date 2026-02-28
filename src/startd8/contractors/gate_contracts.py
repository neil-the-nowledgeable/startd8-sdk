"""
Gate contract emission for StartD8 internal quality gates.

Adapts StartD8-internal quality signals (review scores, checkpoint results,
preflight reports) into ContextCore ``GateResult`` contracts and emits them
via the StartD8 EventBus.  When the ``contextcore`` package is installed the
results are fully-typed Pydantic models; otherwise plain dicts with the same
shape are emitted so downstream listeners can still consume them.

Phase 4, Item 10 of the StartD8 Agent Communication Design.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from startd8.events.bus import EventBus
from startd8.events.types import Event, EventPriority, EventType

# ---------------------------------------------------------------------------
# Lazy import of ContextCore contract models
# ---------------------------------------------------------------------------

try:
    from contextcore.contracts.a2a.models import (
        EvidenceItem,
        GateOutcome,
        GateResult,
        GateSeverity,
        Phase,
    )

    CONTEXTCORE_AVAILABLE = True
except ImportError:
    CONTEXTCORE_AVAILABLE = False
    # Fallback type aliases so the module loads without contextcore.
    GateResult = Any  # type: ignore[assignment,misc]
    GateOutcome = Any  # type: ignore[assignment,misc]
    GateSeverity = Any  # type: ignore[assignment,misc]
    Phase = Any  # type: ignore[assignment,misc]
    EvidenceItem = Any  # type: ignore[assignment,misc]

from startd8.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# GateEmitter
# ---------------------------------------------------------------------------


class GateEmitter:
    """Emit :class:`GateResult` contracts from internal quality gates.

    All factory methods return either a real ``GateResult`` (when contextcore
    is installed) or a plain ``dict`` with an identical shape.  The
    :meth:`emit` class-method publishes the result to the framework
    ``EventBus`` as a ``QUALITY_GATE_RESULT`` event so that ContextCore
    adapters (or any other subscriber) can forward it to OTel.
    """

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _now() -> datetime:
        """Return current UTC time (seam for testing)."""
        return datetime.now(timezone.utc)

    # -- emit ----------------------------------------------------------------

    @classmethod
    def emit(cls, gate_result: GateResult | Dict[str, Any]) -> None:
        """Publish *gate_result* to the framework ``EventBus``.

        Args:
            gate_result: A ContextCore ``GateResult`` model or a fallback dict
                with the same shape.
        """
        if CONTEXTCORE_AVAILABLE and hasattr(gate_result, "model_dump"):
            data = gate_result.model_dump(mode="json")
        elif isinstance(gate_result, dict):
            data = gate_result
        else:
            logger.error(
                "GateEmitter.emit: gate_result must be GateResult or dict, "
                "got %s — skipping emission",
                type(gate_result).__name__,
            )
            return

        event = Event(
            type=EventType.QUALITY_GATE_RESULT,
            source="GateEmitter",
            data=data,
            priority=EventPriority.HIGH,
        )
        EventBus.emit(event)

        gate_id = data.get("gate_id", "unknown")
        result_val = data.get("result", "unknown")
        logger.info("Emitted quality gate result: %s -> %s", gate_id, result_val)

    # -- factory: review result ----------------------------------------------

    @classmethod
    def from_review_result(
        cls,
        task_id: str,
        review_dict: Dict[str, Any],
        workflow_id: str,
        trace_id: Optional[str] = None,
    ) -> GateResult | Dict[str, Any]:
        """Map an artisan REVIEW-phase result dict to a ``GateResult``.

        The *review_dict* is the per-task dict produced by
        ``ReviewPhaseHandler._review_task`` (keys: ``score``, ``verdict``,
        ``passed``, ``issues``, ``suggestions``, ``strengths``).
        """
        passed = review_dict.get("passed", False)
        score = review_dict.get("score", 0)
        verdict = review_dict.get("verdict", "FAIL")
        issues: List[str] = review_dict.get("issues", [])
        suggestions: List[str] = review_dict.get("suggestions", [])

        reason = f"Review score {score}/100, verdict {verdict}"

        if CONTEXTCORE_AVAILABLE:
            evidence: list[EvidenceItem] = []
            for issue in issues:
                evidence.append(
                    EvidenceItem(type="issue", ref=f"task://{task_id}", description=issue)
                )
            for suggestion in suggestions:
                evidence.append(
                    EvidenceItem(
                        type="suggestion", ref=f"task://{task_id}", description=suggestion
                    )
                )

            return GateResult(
                schema_version="v1",
                gate_id=f"artisan.review.{task_id}",
                trace_id=trace_id,
                task_id=task_id,
                phase=Phase.REVIEW_CALIBRATE,
                result=GateOutcome.PASS if passed else GateOutcome.FAIL,
                severity=GateSeverity.INFO if passed else GateSeverity.ERROR,
                reason=reason,
                next_action="proceed" if passed else "revise",
                blocking=not passed,
                evidence=evidence or None,
                checked_at=cls._now(),
            )

        # Fallback dict -------------------------------------------------------
        evidence_dicts: list[dict[str, str]] = []
        for issue in issues:
            evidence_dicts.append(
                {"type": "issue", "ref": f"task://{task_id}", "description": issue}
            )
        for suggestion in suggestions:
            evidence_dicts.append(
                {"type": "suggestion", "ref": f"task://{task_id}", "description": suggestion}
            )

        return {
            "schema_version": "v1",
            "gate_id": f"artisan.review.{task_id}",
            "trace_id": trace_id,
            "task_id": task_id,
            "phase": "REVIEW_CALIBRATE",
            "result": "pass" if passed else "fail",
            "severity": "info" if passed else "error",
            "reason": reason,
            "next_action": "proceed" if passed else "revise",
            "blocking": not passed,
            "evidence": evidence_dicts or None,
            "checked_at": cls._now().isoformat(),
        }

    # -- factory: checkpoint result ------------------------------------------

    @classmethod
    def from_checkpoint_result(
        cls,
        checkpoint_result: Any,
        workflow_id: str,
        trace_id: Optional[str] = None,
    ) -> GateResult | Dict[str, Any]:
        """Map a :class:`CheckpointResult` to a ``GateResult``.

        ``CheckpointResult`` (from ``contractors.checkpoint``) exposes:
        ``status`` (PASSED/FAILED/SKIPPED/WARNING), ``name``, ``message``,
        ``details``, ``errors``, ``warnings``, and a ``.passed`` property.
        """
        is_passed: bool = getattr(checkpoint_result, "passed", False)
        name: str = getattr(checkpoint_result, "name", "unknown")
        message: str = getattr(checkpoint_result, "message", "")
        errors: list[str] = getattr(checkpoint_result, "errors", [])
        warnings_list: list[str] = getattr(checkpoint_result, "warnings", [])

        reason = f"Checkpoint '{name}': {message}"

        if CONTEXTCORE_AVAILABLE:
            evidence: list[EvidenceItem] = []
            for err in errors:
                evidence.append(
                    EvidenceItem(type="error", ref=f"checkpoint://{name}", description=err)
                )
            for warn in warnings_list:
                evidence.append(
                    EvidenceItem(type="warning", ref=f"checkpoint://{name}", description=warn)
                )

            return GateResult(
                schema_version="v1",
                gate_id=f"artisan.checkpoint.{name}",
                trace_id=trace_id,
                task_id=None,
                phase=Phase.FINALIZE_VERIFY,
                result=GateOutcome.PASS if is_passed else GateOutcome.FAIL,
                severity=GateSeverity.INFO if is_passed else GateSeverity.CRITICAL,
                reason=reason,
                next_action="resume" if is_passed else "halt",
                blocking=not is_passed,
                evidence=evidence or None,
                checked_at=cls._now(),
            )

        # Fallback dict -------------------------------------------------------
        evidence_dicts: list[dict[str, str]] = []
        for err in errors:
            evidence_dicts.append(
                {"type": "error", "ref": f"checkpoint://{name}", "description": err}
            )
        for warn in warnings_list:
            evidence_dicts.append(
                {"type": "warning", "ref": f"checkpoint://{name}", "description": warn}
            )

        return {
            "schema_version": "v1",
            "gate_id": f"artisan.checkpoint.{name}",
            "trace_id": trace_id,
            "task_id": None,
            "phase": "FINALIZE_VERIFY",
            "result": "pass" if is_passed else "fail",
            "severity": "info" if is_passed else "critical",
            "reason": reason,
            "next_action": "resume" if is_passed else "halt",
            "blocking": not is_passed,
            "evidence": evidence_dicts or None,
            "checked_at": cls._now().isoformat(),
        }

    # -- factory: preflight report -------------------------------------------

    @classmethod
    def from_preflight_report(
        cls,
        report: Any,
        workflow_id: str,
        trace_id: Optional[str] = None,
    ) -> GateResult | Dict[str, Any]:
        """Map a :class:`PreFlightReport` to a ``GateResult``.

        ``PreFlightReport`` (from ``contractors.artisan_phases.preflight``)
        exposes: ``passed``, ``failed_checks``, ``warnings``, ``results``.
        """
        is_passed: bool = getattr(report, "passed", False)
        failed_checks: list[Any] = getattr(report, "failed_checks", [])
        warn_checks: list[Any] = getattr(report, "warnings", [])

        n_fail = len(failed_checks)
        n_warn = len(warn_checks)
        reason = (
            "All preflight checks passed"
            if is_passed
            else f"Preflight failed: {n_fail} failure(s), {n_warn} warning(s)"
        )

        if CONTEXTCORE_AVAILABLE:
            evidence: list[EvidenceItem] = []
            for chk in failed_checks:
                chk_name = getattr(chk, "name", "unknown")
                chk_msg = getattr(chk, "message", str(chk))
                evidence.append(
                    EvidenceItem(
                        type="preflight_failure",
                        ref=f"preflight://{chk_name}",
                        description=chk_msg,
                    )
                )
            for chk in warn_checks:
                chk_name = getattr(chk, "name", "unknown")
                chk_msg = getattr(chk, "message", str(chk))
                evidence.append(
                    EvidenceItem(
                        type="preflight_warning",
                        ref=f"preflight://{chk_name}",
                        description=chk_msg,
                    )
                )

            return GateResult(
                schema_version="v1",
                gate_id=f"artisan.preflight.{workflow_id}",
                trace_id=trace_id,
                task_id=None,
                phase=Phase.TEST_VALIDATE,
                result=GateOutcome.PASS if is_passed else GateOutcome.FAIL,
                severity=GateSeverity.INFO if is_passed else GateSeverity.CRITICAL,
                reason=reason,
                next_action="proceed" if is_passed else "abort",
                blocking=not is_passed,
                evidence=evidence or None,
                checked_at=cls._now(),
            )

        # Fallback dict -------------------------------------------------------
        evidence_dicts: list[dict[str, str]] = []
        for chk in failed_checks:
            chk_name = getattr(chk, "name", "unknown")
            chk_msg = getattr(chk, "message", str(chk))
            evidence_dicts.append(
                {
                    "type": "preflight_failure",
                    "ref": f"preflight://{chk_name}",
                    "description": chk_msg,
                }
            )
        for chk in warn_checks:
            chk_name = getattr(chk, "name", "unknown")
            chk_msg = getattr(chk, "message", str(chk))
            evidence_dicts.append(
                {
                    "type": "preflight_warning",
                    "ref": f"preflight://{chk_name}",
                    "description": chk_msg,
                }
            )

        return {
            "schema_version": "v1",
            "gate_id": f"artisan.preflight.{workflow_id}",
            "trace_id": trace_id,
            "task_id": None,
            "phase": "TEST_VALIDATE",
            "result": "pass" if is_passed else "fail",
            "severity": "info" if is_passed else "critical",
            "reason": reason,
            "next_action": "proceed" if is_passed else "abort",
            "blocking": not is_passed,
            "evidence": evidence_dicts or None,
            "checked_at": cls._now().isoformat(),
        }
