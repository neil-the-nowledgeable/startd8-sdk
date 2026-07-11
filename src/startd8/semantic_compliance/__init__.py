# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Semantic Compliance Reviewer (SCR).

Agent-driven review of whether generated code semantically complies with the *original input
requirement*, routed into the Kaizen feedback loop so the next run is more compliant. The first
producer of the dormant ``SemanticVerificationResult`` (K-7) contract.

Post-run / Service-Assistant-orchestrated; tiered (cheap triage → Haiku → Sonnet escalation);
advisory in v1. See ``docs/design/semantic-compliance/`` for requirements (v0.3), plan (v0.3),
and the report schema (v1.0).
"""

from .models import (
    CrossFeaturePattern,
    FeatureReview,
    InconclusiveReason,
    KaizenSuggestion,
    ReportConfig,
    ReportSummary,
    SemanticComplianceReport,
    SelectionReason,
    Tier,
    Verdict,
)
from .orchestrator import SemanticComplianceOrchestrator, run_semantic_compliance
from .scoring import compute_compliance_score, severity_weight

__all__ = [
    "SemanticComplianceOrchestrator",
    "run_semantic_compliance",
    "SemanticComplianceReport",
    "FeatureReview",
    "ReportConfig",
    "ReportSummary",
    "CrossFeaturePattern",
    "KaizenSuggestion",
    "Verdict",
    "Tier",
    "SelectionReason",
    "InconclusiveReason",
    "compute_compliance_score",
    "severity_weight",
]
