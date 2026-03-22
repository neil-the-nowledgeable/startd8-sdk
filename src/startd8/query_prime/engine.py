"""Query Prime Engine — CLASSIFY -> ROUTE -> GENERATE -> VERIFY.

Supports both deterministic template generation (TRIVIAL tier, $0.00)
and LLM-backed generation with security verification gate and
T3→T2→T1 escalation.

Kaizen integration (REQ-KQP-*):
- Loads FalsePositiveRegistry for FP suppression (REQ-KQP-200)
- Loads RoutingOverrideStore for tier overrides (REQ-KQP-601)
- Injects prior-run security hints into generator prompts (REQ-KQP-600)
- Accumulates results for verification report emission (REQ-KQP-100)
- Sets prior_injection_failure signal from Kaizen history (REQ-QP-300)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.complexity.models import ComplexityTier
from startd8.logging_config import get_logger

from .classifier import QueryRoutingConfig, classify_query_tier
from .fp_registry import FalsePositiveRegistry
from .kaizen_metrics import build_verification_report, compute_query_security_score
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
from .routing_overrides import RoutingOverrideStore
from .security import verify_file
from .templates import generate as template_generate, is_trivial

logger = get_logger(__name__)

# Maximum number of Kaizen security hints injected per prompt (REQ-KQP-600).
_MAX_KAIZEN_HINTS = 3


class QueryPrimeEngine:
    """Query Prime engine — secure query generation with tier routing.

    Supports:
    - TRIVIAL tier: deterministic template generation (health checks, basic CRUD)
    - SIMPLE/MODERATE/COMPLEX: LLM-backed generation with security gate
    - T3→T2→T1 escalation when generation fails verification
    - Security verification of generated and existing code
    - Query signal extraction and classification
    - Kaizen feedback: FP suppression, routing overrides, hint injection,
      metrics accumulation (REQ-KQP-100–602)
    """

    def __init__(
        self,
        config: Optional[QueryRoutingConfig] = None,
        router_config: Optional[QueryRouterConfig] = None,
        *,
        fp_registry: Optional[FalsePositiveRegistry] = None,
        routing_overrides: Optional[RoutingOverrideStore] = None,
        kaizen_hints: Optional[List[str]] = None,
        output_dir: Optional[Path] = None,
        no_suppress: bool = False,
    ) -> None:
        self._config = config or QueryRoutingConfig()
        self._router_config = router_config or QueryRouterConfig()

        # REQ-KQP-201: audit mode bypasses all FP suppression
        self._no_suppress = no_suppress

        # Kaizen: FP suppression (REQ-KQP-200)
        self._fp_registry = fp_registry or FalsePositiveRegistry()
        self._fp_registry.load()

        # Kaizen: routing overrides (REQ-KQP-601)
        self._routing_overrides = routing_overrides or RoutingOverrideStore()
        self._routing_overrides.load()

        # Kaizen: prior-run security hints (REQ-KQP-600)
        self._kaizen_hints: List[str] = (kaizen_hints or [])[: _MAX_KAIZEN_HINTS]

        # Kaizen: result accumulation for verification report (REQ-KQP-100)
        self._accumulated_results: List[QueryResult] = []

        # Kaizen: prior-run injection history for signal extraction
        self._prior_injection_databases: set[str] = set()
        self._output_dir = output_dir
        self._load_prior_injection_history()

    # ------------------------------------------------------------------
    # Kaizen: load prior-run data
    # ------------------------------------------------------------------

    def _load_prior_injection_history(self) -> None:
        """Load injection history from prior run's query-security-metrics.json.

        Populates _prior_injection_databases so _extract_signals can set
        prior_injection_failure for work items targeting those databases.
        """
        if self._output_dir is None:
            return
        metrics_path = self._output_dir / "query-security-metrics.json"
        if not metrics_path.is_file():
            return
        try:
            data = json.loads(metrics_path.read_text())
            if data.get("injection_total", 0) > 0:
                for db, stats in data.get("by_database", {}).items():
                    if stats.get("injection_findings", 0) > 0 or stats.get("injection_found", 0) > 0:
                        self._prior_injection_databases.add(db)
            if self._prior_injection_databases:
                logger.info(
                    "Kaizen: prior injection history loaded for databases: %s",
                    self._prior_injection_databases,
                )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Kaizen: failed to load prior injection history: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

        # Kaizen: apply routing override (REQ-KQP-601)
        override_tier = self._routing_overrides.get_minimum_tier(work_item.id)
        if override_tier is not None and override_tier.value > tier.value:
            logger.info(
                "Kaizen: work_item=%s tier overridden %s -> %s",
                work_item.id, tier.value, override_tier.value,
            )
            tier = override_tier

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
                    fp_registry=self._fp_registry,
                    no_suppress=self._no_suppress,
                )
                result = QueryResult(
                    work_item_id=work_item.id,
                    code=code,
                    verification=verification,
                    tier_used=ComplexityTier.TRIVIAL,
                    model_used="template",
                    cost_usd=0.0,
                    escalations=0,
                    retry_count=0,
                )
                self._accumulated_results.append(result)
                return result

        # LLM generation path with escalation
        result = self._generate_with_escalation(work_item, tier, agent=agent)
        self._accumulated_results.append(result)
        return result

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
                        work_item,
                        current_agent,
                        hints=self._kaizen_hints,
                        fp_registry=self._fp_registry,
                        no_suppress=self._no_suppress,
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
            fp_registry=self._fp_registry,
            no_suppress=self._no_suppress,
        )

    def _extract_signals(self, work_item: QueryWorkItem) -> QuerySignals:
        """Extract classification signals from a query work item.

        Kaizen-bearing: sets prior_injection_failure from prior run history
        and target_framework_familiarity from accumulated run count.
        """
        # Kaizen: prior injection failure from history (REQ-QP-300)
        db_str = (
            work_item.database.value
            if isinstance(work_item.database, DatabaseType)
            else str(work_item.database)
        )
        prior_injection = db_str in self._prior_injection_databases

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
            prior_injection_failure=prior_injection,
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

    # ------------------------------------------------------------------
    # Kaizen: metrics report (REQ-KQP-100, 101, 102)
    # ------------------------------------------------------------------

    def get_verification_report(self, run_id: str) -> Dict[str, Any]:
        """Build and return the verification report from accumulated results.

        Args:
            run_id: Unique run identifier for the report.

        Returns:
            Dict suitable for JSON serialization as query-security-metrics.json.
        """
        return build_verification_report(self._accumulated_results, run_id)

    def save_verification_report(
        self, run_id: str, output_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """Build and persist query-security-metrics.json (advisory).

        Args:
            run_id: Unique run identifier.
            output_dir: Directory to write the report. Falls back to
                self._output_dir or current directory.

        Returns:
            Path to the written file, or None if write failed.
        """
        report = self.get_verification_report(run_id)
        target_dir = output_dir or self._output_dir or Path(".")
        target = target_dir / "query-security-metrics.json"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2) + "\n")
            logger.info("Wrote query-security-metrics.json to %s", target)
            return target
        except OSError as exc:
            logger.warning("Advisory: failed to write verification report: %s", exc)
            return None

    def save_fp_registry(self) -> None:
        """Persist the false positive registry to disk (advisory)."""
        self._fp_registry.save()

    @property
    def accumulated_results(self) -> List[QueryResult]:
        """Read-only access to accumulated results."""
        return list(self._accumulated_results)

    @property
    def fp_registry(self) -> FalsePositiveRegistry:
        """Read-only access to the false positive registry."""
        return self._fp_registry

    @property
    def routing_overrides(self) -> RoutingOverrideStore:
        """Read-only access to routing overrides."""
        return self._routing_overrides
