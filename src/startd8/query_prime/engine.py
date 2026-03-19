"""Query Prime Engine — CLASSIFY -> ROUTE -> GENERATE -> VERIFY.

Phase 1: Template path works end-to-end; LLM paths raise NotImplementedError.
"""

from __future__ import annotations

from typing import Optional

from startd8.complexity.models import ComplexityTier
from startd8.logging_config import get_logger

from .classifier import QueryRoutingConfig, classify_query_tier
from .models import (
    DatabaseType,
    OperationType,
    QueryResult,
    QuerySignals,
    QueryWorkItem,
    SecurityVerificationResult,
)
from .security import verify_file
from .templates import generate as template_generate, is_trivial

logger = get_logger(__name__)


class QueryPrimeEngine:
    """Query Prime engine — secure query generation with tier routing.

    Phase 1 supports:
    - TRIVIAL tier: deterministic template generation (health checks, basic CRUD)
    - Security verification of generated and existing code
    - Query signal extraction and classification

    Phase 3 (future) will add LLM-backed generation for SIMPLE/MODERATE/COMPLEX.
    """

    def __init__(self, config: Optional[QueryRoutingConfig] = None) -> None:
        self._config = config or QueryRoutingConfig()

    def process_work_item(self, work_item: QueryWorkItem) -> QueryResult:
        """Process a query work item through CLASSIFY -> ROUTE -> GENERATE -> VERIFY.

        Args:
            work_item: The query work item to process.

        Returns:
            QueryResult with generated code and verification result.

        Raises:
            NotImplementedError: For tiers that require LLM generation (Phase 3).
        """
        # CLASSIFY
        signals = self._extract_signals(work_item)
        classification = classify_query_tier(
            signals,
            self._config,
            operation_type=work_item.operation_type,
        )
        tier = classification.tier
        logger.info(
            "QueryPrime: work_item=%s tier=%s reason=%s",
            work_item.id, tier.value, classification.reason,
        )

        # ROUTE + GENERATE
        if tier == ComplexityTier.TRIVIAL and is_trivial(work_item):
            code = template_generate(work_item)
            if code is None:
                raise NotImplementedError(
                    f"No template for {work_item.database.value}/"
                    f"{work_item.target_language}/{work_item.operation_type.value}. "
                    f"LLM generation not yet available (Phase 3)."
                )
        elif tier in (ComplexityTier.SIMPLE, ComplexityTier.MODERATE, ComplexityTier.COMPLEX):
            # Check if we can still use a template
            if is_trivial(work_item):
                code = template_generate(work_item)
                if code is None:
                    raise NotImplementedError(
                        f"LLM generation for tier {tier.value} not yet available (Phase 3)."
                    )
            else:
                raise NotImplementedError(
                    f"LLM generation for tier {tier.value} not yet available (Phase 3). "
                    f"Work item: {work_item.id}"
                )
        else:
            raise NotImplementedError(
                f"Unknown tier {tier.value} for work item {work_item.id}"
            )

        # VERIFY
        verification = verify_file(
            code,
            work_item.file_path or f"<generated:{work_item.id}>",
            work_item.database,
            work_item.target_language,
        )

        return QueryResult(
            work_item_id=work_item.id,
            code=code,
            verification=verification,
            tier_used=tier,
            model_used="template",
            cost_usd=0.0,
            escalations=0,
            retry_count=0,
        )

    def verify_existing_file(
        self,
        source: str,
        file_path: str,
        database: DatabaseType | str,
        language: str,
        *,
        strict_lifecycle: bool = False,
    ) -> SecurityVerificationResult:
        """Standalone verification for Anzen gate (no generation).

        Args:
            source: Source code text.
            file_path: Path to the source file.
            database: Database type.
            language: Programming language.
            strict_lifecycle: When True, lifecycle issues cause FAIL.

        Returns:
            SecurityVerificationResult with verdict and findings.
        """
        return verify_file(
            source, file_path, database, language,
            strict_lifecycle=strict_lifecycle,
        )

    def _extract_signals(self, work_item: QueryWorkItem) -> QuerySignals:
        """Extract classification signals from a query work item."""
        return QuerySignals(
            table_count=len(work_item.tables),
            join_count=len(work_item.joins),
            has_subquery=False,  # Requires parsing; not available from work item
            has_transaction=work_item.transaction_boundary != work_item.transaction_boundary.NONE,
            has_dynamic_columns=False,  # Requires parsing
            has_aggregate=False,  # Requires parsing
            parameter_count=len(work_item.parameters),
            has_upsert=work_item.operation_type == OperationType.UPSERT,
            target_framework_familiarity=1.0,
            prior_injection_failure=False,
        )
