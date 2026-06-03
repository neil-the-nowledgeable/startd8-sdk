"""Data models for the Service Assistant triage artifact.

These dataclasses mirror ``SERVICE_ASSISTANT_TRIAGE_SCHEMA.md`` v1.0. ``TriageReport``
is serialized to ``service-assistant-triage.json`` (the authoritative project<->SDK
bridge, FR-7) via :func:`dataclasses.asdict`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"


@dataclass
class RunInfo:
    run_id: str
    output_dir: str
    status: str  # completed | partial | aborted | in_progress
    detected_at: Optional[str] = None


@dataclass
class AuxSignals:
    """Auxiliary error sources beyond the run/post-mortem sentinels (HOWL prior art).

    Detected but not deeply parsed — counts feed triage severity and are surfaced for
    the operator. This is the FR-12 extension point realized for error stores.
    """

    failed_checkpoints: int = 0
    task_errors: int = 0
    pi_errors: int = 0
    sources: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.failed_checkpoints + self.task_errors + self.pi_errors


@dataclass
class Detection:
    run_sentinel_present: bool = False
    postmortem_present: bool = False
    state_file_present: bool = False
    hard_abort: bool = False
    features_attempted: Optional[int] = None
    aux_signals: Optional[AuxSignals] = None


@dataclass
class Verdict:
    aggregate_verdict: str = "UNKNOWN"  # PASS | PARTIAL | FAIL | ABORTED | UNKNOWN
    total_features: int = 0
    succeeded: int = 0
    failed: int = 0
    total_cost_usd: Optional[float] = None


@dataclass
class ProjectContext:
    project_id: Optional[str] = None
    task_ids: List[str] = field(default_factory=list)
    requirement_refs: List[str] = field(default_factory=list)
    contextcore_state_path: Optional[str] = None
    source: str = "none"  # contextcore | contextcore_yaml | forward_manifest | none


@dataclass
class RecommendedAction:
    action: str
    re_run_strategy: str
    rationale: Optional[str] = None
    source_classification: str = "postmortem_report"  # postmortem_report | fallback_classifier


@dataclass
class FailureTriage:
    feature_id: str
    root_cause: str
    pipeline_stage: str
    severity: str
    recommended_action: RecommendedAction
    actionable: bool = True
    element_id: Optional[str] = None
    file: Optional[str] = None
    persistent: bool = False
    occurrences: int = 1
    force_regenerated: bool = False


@dataclass
class CrossFeaturePatternView:
    pattern_type: str
    description: str
    affected_features: List[str]
    severity: str


@dataclass
class BatchInfo:
    batch_id: str
    runs_in_batch: int = 1
    persistent_failure_count: int = 0
    velocity_trend: str = "unknown"


@dataclass
class EmittedEvent:
    type: str
    priority: str
    at: Optional[str] = None


@dataclass
class CursorInfo:
    cursor_path: str
    previously_processed: bool = False
    run_checksum: Optional[str] = None


@dataclass
class SemanticReviewRef:
    """Folded summary of a Semantic Compliance Reviewer report, when present (FR-12)."""

    status: str                      # complete | pending
    report_path: str
    aggregate: Optional[float] = None
    fail: int = 0
    inconclusive: int = 0


@dataclass
class Summary:
    headline: str
    top_recommendation: Optional[str] = None


@dataclass
class TriageReport:
    """Top-level triage artifact (``service-assistant-triage.json``)."""

    generated_at: str
    assistant_version: str
    run: RunInfo
    detection: Detection
    verdict: Verdict
    summary: Summary
    cursor: CursorInfo
    schema_version: str = SCHEMA_VERSION
    project_context: Optional[ProjectContext] = None
    failures: List[FailureTriage] = field(default_factory=list)
    cross_feature_patterns: List[CrossFeaturePatternView] = field(default_factory=list)
    batch: Optional[BatchInfo] = None
    events_emitted: List[EmittedEvent] = field(default_factory=list)
    semantic_review: Optional[SemanticReviewRef] = None

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)
