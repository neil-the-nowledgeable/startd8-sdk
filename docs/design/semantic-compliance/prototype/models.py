"""PROTOTYPE — Semantic Compliance Reviewer data contract.

NOT SHIPPED CODE. This lives under docs/design/ to make the dev footprint concrete; it is the
intended shape of `src/startd8/semantic_compliance/models.py`. Dataclasses mirror
`SEMANTIC_COMPLIANCE_REPORT_SCHEMA.md` v1.0 and trace to FRs in REQUIREMENTS v0.3.

The verdict/issue shape deliberately matches the dormant `micro_prime.models.SemanticVerificationResult`
(K-7) so the SCR is a drop-in *producer* of that contract (FR-6/FR-13).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

SCHEMA_VERSION = "1.0"


# --- controlled vocabularies (schema §1) ------------------------------------

class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class Tier(str, Enum):
    CHEAP = "cheap"            # Haiku first pass (FR-15)
    ESCALATED = "escalated"    # Sonnet re-review on fail/low-confidence


class SelectionReason(str, Enum):
    SUSPECT = "suspect"            # above suspicion threshold (FR-5)
    PASS_SAMPLE = "pass_sample"    # reserved false-PASS quota (FR-5a)
    NOT_REVIEWED = "not_reviewed"  # budget-skipped (no-silent-caps)


class InconclusiveReason(str, Enum):
    REQUIREMENT_TEXT_UNAVAILABLE = "requirement_text_unavailable"  # FR-1
    REQUIREMENT_JOIN_AMBIGUOUS = "requirement_join_ambiguous"      # FR-1 / S-R1-4
    LANGUAGE_UNSUPPORTED = "language_unsupported"                  # R2-S1 (Python-only v1)
    POSTMORTEM_UNAVAILABLE = "postmortem_unavailable"             # R3-S3
    PARSE_FAILURE = "parse_failure"                               # R1-S7
    INPUT_TRUNCATED = "input_truncated"                          # R3-S1


# --- contract pieces --------------------------------------------------------

@dataclass(frozen=True)
class VerificationIssue:
    """Mirrors micro_prime.models.VerificationIssue (K-7)."""
    severity: str          # critical|high|medium|low
    category: str
    description: str
    line_hint: Optional[int] = None
    suggested_fix: Optional[str] = None


@dataclass
class RequirementRef:
    seed_task_id: Optional[str] = None
    text_excerpt: Optional[str] = None      # bounded; never a full file (R4-S3)
    join_corroborated: bool = False         # target_files ∩ generated_files (S-R1-4)


@dataclass
class Selection:
    suspicion_score: float
    tier: Tier
    reason: SelectionReason
    not_reviewed_reason: Optional[str] = None


@dataclass
class VerdictResult:
    verdict: Verdict
    confidence: float
    inconclusive_reason: Optional[InconclusiveReason] = None


@dataclass
class FeatureReview:
    feature_id: str
    language: str
    review_granularity: str                 # "feature" | "element" (OQ-9)
    element_fqn: str                        # synthetic feature:<id> at feature granularity (R1-S4)
    selection: Selection
    verdict: VerdictResult
    requirement: RequirementRef = field(default_factory=RequirementRef)
    issues: List[VerificationIssue] = field(default_factory=list)
    semantic_compliance_score: Optional[float] = None  # FR-8; None when inconclusive
    reviewed_files: List[str] = field(default_factory=list)   # paths only (no raw code, R4-S3)
    review_status: str = "complete"          # complete | pending | error


@dataclass
class CrossFeaturePattern:
    """Reuses prime_postmortem.CrossFeaturePattern shape (R2-S6)."""
    pattern_type: str
    grouping_key: str                        # category | contract_id | seed_task_id (R1-F5)
    description: str
    affected_features: List[str]
    severity: str


@dataclass
class ReportConfig:
    suspicion_threshold: float = 0.5
    max_escalations: int = 10
    reserved_pass_quota: int = 2
    model_cheap: str = "anthropic:claude-haiku-4-5"
    model_escalation: str = "anthropic:claude-sonnet-4-6"
    theta: Optional[float] = 0.7             # gate confidence default (FR-14)
    max_input_tokens: int = 12000            # R3-S1
    max_output_tokens: int = 1024            # R3-S4
    deterministic: bool = True               # R2-S5


@dataclass
class ReportSummary:
    total_features: int = 0
    escalated: int = 0
    reviewed: int = 0
    not_reviewed: int = 0
    pass_: int = 0                           # serialized as "pass"
    fail: int = 0
    inconclusive: int = 0
    semantic_compliance_aggregate: Optional[float] = None  # mean over CONCLUSIVE only (FR-8)
    inconclusive_rate: float = 0.0
    inconclusive_rate_exceeded: bool = False  # → SYSTEM_WARNING (FR-14/R4-F1)
    cost_usd: Optional[float] = None          # reconciles with CostSummary (FR-16/R2-S2)


@dataclass
class SemanticComplianceReport:
    """Top-level FR-9 artifact (`semantic-compliance-report.json`)."""
    generated_at: str
    scr_version: str
    run_id: str
    output_dir: str
    config: ReportConfig
    summary: ReportSummary
    status: str = "complete"                 # pending | complete (atomic-write gate, R2-S3)
    schema_version: str = SCHEMA_VERSION
    run_language: Optional[str] = "python"
    features: List[FeatureReview] = field(default_factory=list)
    cross_feature_patterns: List[CrossFeaturePattern] = field(default_factory=list)
    kaizen_emitted: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        # "pass" is a Python keyword on ReportSummary → fix the serialized key.
        d["summary"]["pass"] = d["summary"].pop("pass_")
        return d


@dataclass
class KaizenSuggestion:
    """Structured record written into kaizen-suggestions.json (FR-10) — NOT a bare string (R1-S2)."""
    pattern_type: str = "requirement_semantic_gap"
    suggested_action: str = ""
    config_key: str = "prompt_hints"
    phase: str = "draft"
    confidence: float = 0.0
    auto_applicable: bool = False
    source: str = "semantic_compliance_reviewer"
    feature_id: str = ""
    advisory: bool = True                    # next gen validates, doesn't blindly inject (R3-F2)
