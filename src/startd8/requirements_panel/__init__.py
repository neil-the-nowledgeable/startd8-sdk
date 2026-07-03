# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Requirements Panel — persona-driven requirements *drafting* (design: REQUIREMENTS_PANEL_*.md v0.4).

The third sibling after the Stakeholder Panel (value-inputs) and Manifest Suggester (screens): role-
based agents draft candidate *requirements* for human approval. **Scope lock (P1):** the output is
estimate-provenance drafts a human owns and approves — an elicitation simulator, never an authority on
what the product must do.

The `$0` deterministic surface (baseline / grounding / sanitize / synthesis / store / readiness /
apply / domains) imports with no LLM/agent coupling. The paid pass (:func:`elicit_requirements`) is
lazy-imported so importing this package stays cheap.
"""

from __future__ import annotations

from startd8.requirements_panel.apply import ApplyResult, apply_requirements
from startd8.requirements_panel.baseline import (
    is_join_table,
    primary_entities,
    scaffold,
)
from startd8.requirements_panel.domains import (
    DEFAULT_DOMAINS,
    RequirementDomain,
    get_domain,
    requirement_domains,
    resolve_requirement_owner,
)
from startd8.requirements_panel.grounding import (
    GroundingFlag,
    ground_requirement,
)
from startd8.requirements_panel.models import (
    PROV_BASELINE,
    PROV_ESTIMATE,
    PROV_HUMAN,
    RequirementCandidate,
    RequirementDoc,
    fr_id,
)
from startd8.requirements_panel.coverage import CoverageReport, coverage_report
from startd8.requirements_panel.readiness import ReadinessResult, check_readiness
from startd8.requirements_panel.roster import (
    InstallResult,
    default_roster_text,
    install_default_roster,
)
from startd8.requirements_panel.sanitize import (
    has_unsafe_heading,
    neutralize_headings,
)
from startd8.requirements_panel.store import CandidateStore
from startd8.requirements_panel.synthesis import synthesize

__all__ = [
    # models
    "RequirementCandidate",
    "RequirementDoc",
    "fr_id",
    "PROV_BASELINE",
    "PROV_ESTIMATE",
    "PROV_HUMAN",
    # domains
    "RequirementDomain",
    "DEFAULT_DOMAINS",
    "requirement_domains",
    "get_domain",
    "resolve_requirement_owner",
    # deterministic pipeline
    "scaffold",
    "primary_entities",
    "is_join_table",
    "ground_requirement",
    "GroundingFlag",
    "neutralize_headings",
    "has_unsafe_heading",
    "synthesize",
    "check_readiness",
    "ReadinessResult",
    "coverage_report",
    "CoverageReport",
    "install_default_roster",
    "default_roster_text",
    "InstallResult",
    "apply_requirements",
    "ApplyResult",
    "CandidateStore",
    # paid pass (lazy)
    "elicit_requirements",
    "ElicitationRun",
]


def __getattr__(name: str):
    """Lazy-load the paid elicitation pass (keeps the deterministic surface import-cheap)."""
    if name in ("elicit_requirements", "ElicitationRun", "schema_entity_names"):
        from startd8.requirements_panel import elicit

        return getattr(elicit, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
