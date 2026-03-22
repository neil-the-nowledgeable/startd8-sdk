"""Pydantic models for Security Prime gate verdict reports.

Provides typed schemas for security-gate-metrics.json, replacing Dict[str, Any]
to catch missing fields at construction time rather than downstream.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from startd8.logging_config import get_logger

logger = get_logger(__name__)


class GateFinding(BaseModel):
    """Individual security finding within a file."""
    check_type: str
    severity: str
    message: str = ""
    line: Optional[int] = None
    pattern_hash: str = ""


class GateFileEntry(BaseModel):
    """Per-file gate verdict breakdown (REQ-KSP-101)."""
    file_path: str
    verdict: str  # "pass", "warn", "fail"
    score: float
    findings_count: int = 0
    finding_types: Dict[str, int] = Field(default_factory=dict)
    finding_severities: List[str] = Field(default_factory=list)
    findings: List[GateFinding] = Field(default_factory=list)
    database: str = ""
    language: str = ""
    timing_ms: float = 0.0
    allowlisted: bool = False
    security_sensitive: bool = False
    prompt_security_features: Optional[Dict[str, Any]] = None


class PostureResult(BaseModel):
    """Security posture assessment (REQ-KSP-103)."""
    level: str  # "clean", "degraded", "critical"
    reason: str
    rules: Dict[str, str] = Field(default_factory=dict)
    interpretation: str = ""


class GateVerdictReport(BaseModel):
    """Top-level gate verdict report schema (REQ-KSP-100).

    Typed replacement for the Dict[str, Any] returned by
    build_gate_verdict_report(). Use .model_dump() for JSON serialization.
    """
    schema_version: str = "1.0.0"
    status: str = "completed"  # "completed" or "skipped"
    run_id: str
    timestamp: str
    files_checked: int = 0
    files_skipped: int = 0
    files_total: int = 0
    aggregate_score: float = 1.0
    mean_score: float = 1.0
    gate_pass_rate: float = 1.0
    security_posture: str = "CLEAN"
    total_findings: int = 0
    findings_by_type: Dict[str, int] = Field(default_factory=dict)
    verdict_counts: Dict[str, int] = Field(default_factory=lambda: {"pass": 0, "warn": 0, "fail": 0})
    databases_seen: List[str] = Field(default_factory=list)
    languages_seen: List[str] = Field(default_factory=list)
    total_timing_ms: float = 0.0
    posture: PostureResult = Field(default_factory=lambda: PostureResult(level="clean", reason="No files checked"))
    items: List[GateFileEntry] = Field(default_factory=list)

    # Optional sections
    allowlist: Optional[Dict[str, Any]] = None
    owasp_coverage: Optional[Dict[str, Any]] = None
    score_distribution: Optional[Dict[str, Any]] = None
    prompt_effectiveness: Optional[Dict[str, Any]] = None
    threshold_sensitivity: Optional[List[Dict[str, Any]]] = None
    component_contributions: Optional[List[Dict[str, Any]]] = None


def skipped_report(run_id: str = "", timestamp: str = "") -> GateVerdictReport:
    """Create a minimal gate-skipped sentinel report.

    Used when Security Prime is inactive (ImportError) so consumers
    can distinguish 'all clean' from 'never ran'.
    """
    import datetime  # Lazy import to avoid import-time side effects
    logger.debug("Creating gate-skipped sentinel report (Security Prime inactive)")
    ts = timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
    return GateVerdictReport(
        status="skipped",
        run_id=run_id or "unknown",
        timestamp=ts,
        security_posture="SKIPPED",
        posture=PostureResult(
            level="skipped",
            reason="Security Prime was not active (query_prime not available)",
        ),
    )
