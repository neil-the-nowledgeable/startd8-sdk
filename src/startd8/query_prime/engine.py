"""Query Prime Engine — CLASSIFY -> ROUTE -> GENERATE -> VERIFY.

Supports both deterministic template generation (TRIVIAL tier, $0.00)
and LLM-backed generation with security verification gate and
T3→T2→T1 escalation.
"""

from __future__ import annotations

from typing import Any, List, Optional

from startd8.complexity.models import ComplexityTier
from startd8.logging_config import get_logger

from .classifier import QueryRoutingConfig, classify_query_tier
from .models import (
    DatabaseType,
    OperationType,
    QueryResult,
    QuerySignals,
    QueryWorkItem,
    SecurityVerdict,
    SecurityVerificationResult,
)
from .router import QueryRouterConfig, get_agent_spec_for_tier, get_escalation_tier
from .security import verify_file
from .templates import generate as template_generate, is_trivial

logger = get_logger(__name__)


class QueryPrimeEngine:
    """Query Prime engine — secure query generation with tier routing.

    Supports:
    - TRIVIAL tier: deterministic template generation (health checks, basic CRUD)
    - SIMPLE/MODERATE/COMPLEX: LLM-backed generation with security gate
    - T3→T2→T1 escalation when generation fails verification
    - Security verification of generated and existing code
    - Query signal extraction and classification
    """

    def __init__(
        self,
        config: Optional[QueryRoutingConfig] = None,
        router_config: Optional[QueryRouterConfig] = None,
    ) -> None:
        self._config = config or QueryRoutingConfig()
        self._router_config = router_config or QueryRouterConfig()

    def process_work_item(
        self,
        work_item: QueryWorkItem,
        *,
        agent: Optional[Any] = None,
    ) -> QueryResult:
        """Process a query work item through CLASSIFY -> ROUTE -> GENERATE -> VERIFY.

        Args:
            work_item: The query work item to process.
            agent: Optional pre-resolved agent. When None, an agent is
                resolved from the tier's agent spec (requires providers
                to be configured).

        Returns:
            QueryResult with generated code and verification result.
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

        # ROUTE + GENERATE: try template first for any tier
        if is_trivial(work_item):
            code = template_generate(work_item)
            if code is not None:
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
                    tier_used=ComplexityTier.TRIVIAL,
                    model_used="template",
                    cost_usd=0.0,
                    escalations=0,
                    retry_count=0,
                )

        # LLM generation path with escalation
        return self._generate_with_escalation(work_item, tier, agent=agent)

    def _generate_with_escalation(
        self,
        work_item: QueryWorkItem,
        initial_tier: ComplexityTier,
        *,
        agent: Optional[Any] = None,
    ) -> QueryResult:
        """Generate via LLM with T3→T2→T1 escalation on verification failure.

        Args:
            work_item: The query work item.
            initial_tier: Starting complexity tier.
            agent: Optional pre-resolved agent (bypasses agent resolution).

        Returns:
            QueryResult with the best generation result.
        """
        from .generator import generate_query

        current_tier = initial_tier
        escalations = 0
        total_cost = 0.0
        total_retries = 0
        last_code = ""
        last_verification: Optional[SecurityVerificationResult] = None
        last_model = ""

        while True:
            # Resolve agent for current tier
            current_agent = agent
            if current_agent is None:
                agent_spec = get_agent_spec_for_tier(
                    current_tier, self._router_config,
                )
                current_agent = self._resolve_agent(agent_spec)
                last_model = agent_spec
            else:
                last_model = getattr(current_agent, "name", "provided")

            # Generate with retries at current tier
            for retry in range(self._router_config.max_retries_per_tier + 1):
                total_retries += 1
                try:
                    code, verification, cost = generate_query(
                        work_item, current_agent,
                    )
                    total_cost += cost
                    last_code = code
                    last_verification = verification

                    # Check verification
                    if verification.verdict != SecurityVerdict.FAIL:
                        logger.info(
                            "QueryPrime: work_item=%s PASSED at tier=%s "
                            "escalations=%d retries=%d cost=$%.6f",
                            work_item.id, current_tier.value,
                            escalations, total_retries, total_cost,
                        )
                        return QueryResult(
                            work_item_id=work_item.id,
                            code=code,
                            verification=verification,
                            tier_used=current_tier,
                            model_used=last_model,
                            cost_usd=total_cost,
                            escalations=escalations,
                            retry_count=total_retries,
                        )

                    logger.warning(
                        "QueryPrime: work_item=%s FAILED verification at "
                        "tier=%s retry=%d: %s",
                        work_item.id, current_tier.value, retry,
                        [f.message for f in verification.findings[:3]],
                    )

                except Exception as exc:
                    logger.warning(
                        "QueryPrime: generation error for %s at tier=%s: %s",
                        work_item.id, current_tier.value, exc,
                    )
                    last_verification = None

            # Escalate to next tier
            next_tier = get_escalation_tier(current_tier)
            if next_tier is None or escalations >= self._router_config.max_escalations:
                logger.error(
                    "QueryPrime: work_item=%s EXHAUSTED all tiers "
                    "(escalations=%d, retries=%d)",
                    work_item.id, escalations, total_retries,
                )
                return QueryResult(
                    work_item_id=work_item.id,
                    code=last_code,
                    verification=last_verification,
                    tier_used=current_tier,
                    model_used=last_model,
                    cost_usd=total_cost,
                    escalations=escalations,
                    retry_count=total_retries,
                )

            escalations += 1
            current_tier = next_tier
            agent = None  # Re-resolve for new tier
            logger.info(
                "QueryPrime: escalating %s to tier=%s (escalation %d/%d)",
                work_item.id, current_tier.value,
                escalations, self._router_config.max_escalations,
            )

    def _resolve_agent(self, agent_spec: str) -> Any:
        """Resolve an agent spec string into a BaseAgent instance."""
        from startd8.utils.agent_resolution import resolve_agent_spec

        return resolve_agent_spec(agent_spec)

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

    def process_feature(
        self,
        feature_id: str,
        description: str,
        target_files: List[str],
        metadata: Optional[dict] = None,
        *,
        agent: Optional[Any] = None,
    ) -> List[QueryResult]:
        """Decompose a feature and process all query work items.

        Convenience method that combines decomposer + engine.

        Args:
            feature_id: The feature identifier.
            description: Feature description text.
            target_files: Target file paths.
            metadata: Optional feature metadata.
            agent: Optional pre-resolved agent.

        Returns:
            List of QueryResult, one per decomposed work item.
            Empty list if no database operations detected.
        """
        from .decomposer import decompose_feature

        work_items = decompose_feature(
            feature_id, description, target_files, metadata,
        )
        if not work_items:
            return []

        results: List[QueryResult] = []
        for wi in work_items:
            result = self.process_work_item(wi, agent=agent)
            results.append(result)

        return results
