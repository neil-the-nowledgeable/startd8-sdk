"""
Gate contracts for StartD8 internal quality gates.

This module provides the GateEmitter class which adapts StartD8 internal
quality signals (review results, checkpoint validation, preflight checks)
into ContextCore GateResult contracts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Dict, List
import logging

from startd8.events.bus import EventBus
from startd8.events.types import Event, EventType, EventPriority

# Lazy import helpers for ContextCore contracts
try:
    from contextcore.contracts.a2a.models import (
        GateResult,
        GateOutcome,
        GateSeverity,
        Phase,
        EvidenceItem,
    )
    CONTEXTCORE_AVAILABLE = True
except ImportError:
    CONTEXTCORE_AVAILABLE = False
    # Mock classes for type hinting when contextcore is missing
    GateResult = Any
    GateOutcome = Any
    GateSeverity = Any
    Phase = Any
    EvidenceItem = Any

logger = logging.getLogger(__name__)


class GateEmitter:
    """
    Emits GateResult contracts to ContextCore and the StartD8 EventBus.

    Adapts internal StartD8 results (ReviewResult, CheckpointResult, etc.)
    into the standardized GateResult schema.
    """

    @staticmethod
    def _get_current_time() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def emit(cls, gate_result: GateResult | Dict[str, Any]) -> None:
        """
        Emit a GateResult to the EventBus and ContextCore (if available).

        Args:
            gate_result: A ContextCore GateResult object or a dictionary
                         with the same shape if contextcore is missing.
        """
        # 1. Convert to dict for EventBus
        if CONTEXTCORE_AVAILABLE and hasattr(gate_result, "model_dump"):
            data = gate_result.model_dump(mode="json")
        elif isinstance(gate_result, dict):
            data = gate_result
        else:
            logger.warning("GateEmitter.emit received unknown type: %s", type(gate_result))
            data = {"raw": str(gate_result)}

        # 2. Emit to EventBus
        event = Event(
            type=EventType.QUALITY_GATE_RESULT,
            source="GateEmitter",
            data=data,
            priority=EventPriority.HIGH,
        )
        EventBus.publish(event)

        # 3. ContextCore integration is handled via the OTel adapter listening to
        #    QUALITY_GATE_RESULT events, or direct emission if we had a client here.
        #    Currently, the plan says "serializes to OTel span event via the ContextCore
        #    adapter's emit_event()". The adapter subscribes to EventBus, so publishing
        #    the event is sufficient to reach the adapter.

        gate_id = data.get("gate_id", "unknown")
        result = data.get("result", "unknown")
        logger.info(f"Emitted quality gate result: {gate_id} -> {result}")

    @classmethod
    def from_review_result(
        cls,
        task_id: str,
        review_dict: Dict[str, Any],
        workflow_id: str,
        trace_id: Optional[str] = None
    ) -> GateResult | Dict[str, Any]:
        """
        Map a review result dictionary to a GateResult contract.

        Args:
            task_id: The ID of the task being reviewed.
            review_dict: Dictionary containing review scores and feedback.
            workflow_id: The workflow execution ID.
            trace_id: Optional distributed trace ID.

        Returns:
            GateResult object or dict.
        """
        passed = review_dict.get("passed", False)
        score = review_dict.get("score", 0.0)
        feedback = review_dict.get("feedback", "")
        
        outcome = "pass" if passed else "fail"
        severity = "info" if passed else "error"
        
        if CONTEXTCORE_AVAILABLE:
            result = GateOutcome.PASS if passed else GateOutcome.FAIL
            sev = GateSeverity.INFO if passed else GateSeverity.ERROR
            phase = Phase.REVIEW_CALIBRATE
            
            evidence = []
            if "critiques" in review_dict:
                for critique in review_dict["critiques"]:
                     evidence.append(EvidenceItem(
                         description=critique,
                         location=f"task://{task_id}",
                         content_type="text/plain"
                     ))
            
            return GateResult(
                schema_version="v1",
                gate_id=f"artisan.review.{task_id}",
                trace_id=trace_id,
                task_id=task_id,
                phase=phase,
                result=result,
                severity=sev,
                reason=f"Review score: {score}. {feedback[:100]}...",
                next_action="proceed" if passed else "revise",
                blocking=not passed,
                evidence=evidence,
                checked_at=cls._get_current_time()
            )
        else:
            # Fallback dict
            return {
                "schema_version": "v1",
                "gate_id": f"artisan.review.{task_id}",
                "trace_id": trace_id,
                "task_id": task_id,
                "phase": "REVIEW_CALIBRATE",
                "result": outcome,
                "severity": severity,
                "reason": f"Review score: {score}. {feedback[:100]}...",
                "next_action": "proceed" if passed else "revise",
                "blocking": not passed,
                "evidence": review_dict.get("critiques", []),
                "checked_at": cls._get_current_time().isoformat()
            }

    @classmethod
    def from_checkpoint_result(
        cls,
        checkpoint_result: Any,  # CheckpointValidationResult
        workflow_id: str,
        trace_id: Optional[str] = None
    ) -> GateResult | Dict[str, Any]:
        """
        Map a CheckpointValidationResult to a GateResult contract.
        """
        # Assuming checkpoint_result has .valid, .errors, .checkpoint_id
        is_valid = getattr(checkpoint_result, "valid", False)
        errors = getattr(checkpoint_result, "errors", [])
        checkpoint_id = getattr(checkpoint_result, "checkpoint_id", "unknown")
        
        outcome = "pass" if is_valid else "fail"
        severity = "info" if is_valid else "critical"
        
        reason = "Checkpoint valid" if is_valid else f"Checkpoint validation failed: {len(errors)} errors"
        
        if CONTEXTCORE_AVAILABLE:
            return GateResult(
                schema_version="v1",
                gate_id=f"artisan.checkpoint.{checkpoint_id}",
                trace_id=trace_id,
                task_id=None,
                phase=Phase.FINALIZE_VERIFY,
                result=GateOutcome.PASS if is_valid else GateOutcome.FAIL,
                severity=GateSeverity.INFO if is_valid else GateSeverity.CRITICAL,
                reason=reason,
                next_action="resume" if is_valid else "halt",
                blocking=not is_valid,
                evidence=[
                    EvidenceItem(description=err, location="checkpoint", content_type="text/plain")
                    for err in errors
                ],
                checked_at=cls._get_current_time()
            )
        else:
            return {
                "schema_version": "v1",
                "gate_id": f"artisan.checkpoint.{checkpoint_id}",
                "trace_id": trace_id,
                "task_id": None,
                "phase": "FINALIZE_VERIFY",
                "result": outcome,
                "severity": severity,
                "reason": reason,
                "next_action": "resume" if is_valid else "halt",
                "blocking": not is_valid,
                "evidence": errors,
                "checked_at": cls._get_current_time().isoformat()
            }

    @classmethod
    def from_preflight_report(
        cls,
        report: Any,  # PreFlightReport
        workflow_id: str,
        trace_id: Optional[str] = None
    ) -> GateResult | Dict[str, Any]:
        """
        Map a PreFlightReport to a GateResult contract.
        """
        # PreFlightReport has .passed, .failed_checks, .warnings
        is_valid = getattr(report, "passed", False)
        failed_checks = getattr(report, "failed_checks", [])
        
        outcome = "pass" if is_valid else "fail"
        severity = "info" if is_valid else "critical"
        
        reason = "Preflight checks passed" if is_valid else f"Preflight checks failed: {len(failed_checks)} failures"
        
        evidence_list = []
        for check in failed_checks:
            msg = getattr(check, "message", str(check))
            name = getattr(check, "name", "unknown")
            evidence_list.append({"description": f"{name}: {msg}", "location": "preflight", "content_type": "text/plain"})

        if CONTEXTCORE_AVAILABLE:
            evidence_objects = [
                EvidenceItem(description=e["description"], location=e["location"], content_type=e["content_type"])
                for e in evidence_list
            ]
            
            return GateResult(
                schema_version="v1",
                gate_id=f"artisan.preflight.{workflow_id}",
                trace_id=trace_id,
                task_id=None,
                phase=Phase.TEST_VALIDATE,
                result=GateOutcome.PASS if is_valid else GateOutcome.FAIL,
                severity=GateSeverity.INFO if is_valid else GateSeverity.CRITICAL,
                reason=reason,
                next_action="proceed" if is_valid else "abort",
                blocking=not is_valid,
                evidence=evidence_objects,
                checked_at=cls._get_current_time()
            )
        else:
            return {
                "schema_version": "v1",
                "gate_id": f"artisan.preflight.{workflow_id}",
                "trace_id": trace_id,
                "task_id": None,
                "phase": "TEST_VALIDATE",
                "result": outcome,
                "severity": severity,
                "reason": reason,
                "next_action": "proceed" if is_valid else "abort",
                "blocking": not is_valid,
                "evidence": evidence_list,
                "checked_at": cls._get_current_time().isoformat()
            }
