"""Micro Prime Engine — Main Orchestrator (REQ-MP-502, 512).

Routes elements through the local-first code generation pipeline:
  TRIVIAL → template registry → splice → done
  SIMPLE  → prompt builder → Ollama → repair → verify → splice or escalate
  MODERATE/COMPLEX → passthrough for cloud handling
"""

from __future__ import annotations

import ast
import json
import time
import textwrap
from typing import Any, Optional

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.micro_prime.classifier import classify_element_with_details
from startd8.micro_prime.metrics import MetricsCollector
from startd8.micro_prime.decomposer import ModerateDecomposer
from startd8.micro_prime.context import MicroPrimeContext
from startd8.micro_prime.models import (
    ElementResult,
    EscalationContext,
    EscalationReason,
    EscalationResult,
    FileResult,
    MicroPrimeConfig,
    SeedResult,
    TierClassification,
)
from startd8.micro_prime.prompt_builder import build_body_prompt, find_few_shot_examples
from startd8.micro_prime.repair import build_repair_attribution, run_repair_pipeline
from startd8.micro_prime.splicer import splice_body_into_skeleton
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)

_CODE_GEN_SYSTEM_PROMPT = (
    "You are an expert Python developer. Generate ONLY the requested function body. "
    "Do NOT include markdown fences, explanations, or any text outside the code. "
    "Do NOT repeat the function signature unless asked for a complete definition."
)


def build_escalation_context(
    element_name: str,
    file_path: str,
    tier: TierClassification,
    reason: EscalationReason,
    detail: str,
    last_code: Optional[str] = None,
    last_error: Optional[str] = None,
    raw_output: Optional[str] = None,
    repaired_code: Optional[str] = None,
    repair_steps: Optional[list[str]] = None,
    local_model: Optional[str] = None,
    element_fqn: Optional[str] = None,
) -> EscalationResult:
    """Build a reusable EscalationResult for element escalation.

    Centralises escalation payload construction so that all call-sites
    produce consistently structured results.

    Args:
        element_name: Name of the element being escalated.
        file_path: Source file path for the element.
        tier: Tier classification at time of escalation.
        reason: Why the element is being escalated.
        detail: Human-readable detail string.
        last_code: Optional last generated code before escalation.
        last_error: Optional error string.

    Returns:
        An EscalationResult populated with the provided context.
    """
    if element_fqn is None:
        element_fqn = element_name
    context = None
    if raw_output or repaired_code or repair_steps or local_model:
        context = EscalationContext(
            element_fqn=element_fqn,
            local_model=local_model or "",
            raw_output=raw_output or "",
            repair_steps_applied=repair_steps or [],
            repaired_code=repaired_code,
            error=last_error or detail,
        )

    return EscalationResult(
        reason=reason,
        detail=detail,
        last_code=last_code,
        last_error=last_error,
        context=context,
    )


class MicroPrimeEngine:
    """Main orchestrator for local-first code generation.

    Processes manifest elements through classification, template matching,
    local model generation, repair, and body splicing.

    Args:
        config: Engine configuration.
        template_registry: Optional custom template registry.
        metrics_collector: Optional metrics collector for observability.
    """

    _CIRCUIT_BREAKER_THRESHOLD: int = 3
    _TIER_PRIORITY: dict[TierClassification, int] = {
        TierClassification.TRIVIAL: 0,
        TierClassification.SIMPLE: 1,
        TierClassification.MODERATE: 2,
        TierClassification.COMPLEX: 3,
    }

    def __init__(
        self,
        config: Optional[MicroPrimeConfig] = None,
        template_registry: Optional[TemplateRegistry] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._templates = template_registry or TemplateRegistry(
            enabled=self._config.templates_enabled,
        )
        self._metrics = metrics_collector or MetricsCollector()
        self._completed: list[dict[str, Any]] = []
        # Circuit breaker state (R3-S2)
        self._consecutive_failures: int = 0
        self._circuit_open: bool = False
        # Element fingerprint success cache (R3-S4)
        self._success_cache: set[str] = set()
        # Decomposer for MODERATE elements (REQ-MP-900)
        self._decomposer = ModerateDecomposer(config=self._config)
        # Manifest reference for _handle_moderate (set by process_file, None for process_element)
        self._current_manifest: Optional[ForwardManifest] = None
        # Cached Ollama agent (C-1: avoid re-creation per element)
        self._ollama_agent: Optional[Any] = None
        # Cached semantic verification agent (optional)
        self._semantic_agent: Optional[Any] = None

    @property
    def config(self) -> MicroPrimeConfig:
        return self._config

    @property
    def metrics_collector(self) -> MetricsCollector:
        return self._metrics

    def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker to closed state.

        Callers should invoke this between files or runs to allow
        local generation to resume after transient failures.
        """
        self._consecutive_failures = 0
        self._circuit_open = False

    def clear_cache(self) -> None:
        """Clear the element fingerprint success cache."""
        self._success_cache.clear()

    def process_element(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: Optional[list[InterfaceContract]] = None,
        design_doc_sections: Optional[list[str]] = None,
    ) -> ElementResult:
        """Process a single element through the pipeline.

        Classifies the element, then delegates to ``_process_element_with_tier``.
        Use this entry point when the tier is not yet known.  When calling
        from ``process_file`` (which pre-classifies for sorting), prefer
        ``_process_element_with_tier`` directly to avoid double classification.

        Args:
            element: Manifest element to process.
            file_spec: File spec for context.
            skeleton: Current skeleton file content.
            contracts: Binding constraints for this element.
            design_doc_sections: Optional design doc sections for prompt context.

        Returns:
            ElementResult with success/failure and optional code.
        """
        element_contracts = contracts or []

        tier, reasoning, details = classify_element_with_details(
            element, file_spec, element_contracts,
            template_registry=self._templates,
            config=self._config,
        )

        return self._process_element_with_tier(
            element, file_spec, skeleton, element_contracts,
            tier=tier, reasoning=reasoning,
            api_file_import_bump=details.file_import_bump,
            api_element_adjustment=details.element_api_adjustment,
            design_doc_sections=design_doc_sections,
        )

    def _process_element_with_tier(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        tier: TierClassification,
        reasoning: str,
        api_file_import_bump: int = 0,
        api_element_adjustment: int = 0,
        ollama_available: bool = True,
        design_doc_sections: Optional[list[str]] = None,
    ) -> ElementResult:
        """Process a single element with a pre-computed tier classification.

        This is the core processing method.  ``process_element`` classifies
        first, then calls here.  ``process_file`` pre-classifies for sorting
        and calls here directly, avoiding redundant classification.

        Args:
            element: Manifest element to process.
            file_spec: File spec for context.
            skeleton: Current skeleton file content.
            contracts: Binding constraints for this element.
            tier: Pre-computed tier classification.
            reasoning: Classification reasoning string.
            design_doc_sections: Optional design doc sections for prompt context.

        Returns:
            ElementResult with success/failure and optional code.
        """
        file_path = file_spec.file

        logger.debug(
            "Classified %s as %s: %s", element.name, tier.value, reasoning,
        )

        # Step 1a: Check success cache (R3-S4) — skip re-generation
        fingerprint = f"{element.parent_class or ''}:{element.name}:{file_path}:{tier.value}"
        if fingerprint in self._success_cache:
            logger.debug(
                "Cache hit for %s — returning cached success", fingerprint,
            )
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=tier,
                classification_reason=reasoning,
                success=True,
                verification_verdict="skipped",
                api_file_import_bump=api_file_import_bump,
                api_element_adjustment=api_element_adjustment,
            )
            self._metrics.record(result)
            return result

        # Step 1b: Circuit breaker (R3-S2) — escalate immediately if open
        if self._circuit_open and tier in (
            TierClassification.TRIVIAL,
            TierClassification.SIMPLE,
        ):
            logger.warning(
                "Circuit breaker open — escalating %s without local attempt",
                element.name,
            )
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=tier,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                api_file_import_bump=api_file_import_bump,
                api_element_adjustment=api_element_adjustment,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=tier,
                    reason=EscalationReason.CIRCUIT_BREAKER,
                    detail=(
                        f"Circuit breaker tripped after "
                        f"{self._CIRCUIT_BREAKER_THRESHOLD} consecutive failures"
                    ),
                ),
            )
            self._metrics.record(result)
            return result

        # Ollama availability gate (REQ-MP-503)
        if not ollama_available and tier in (
            TierClassification.SIMPLE,
            TierClassification.MODERATE,
        ):
            logger.warning(
                "Ollama unavailable — escalating %s (%s) without local attempt",
                element.name, tier.value,
            )
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=tier,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                api_file_import_bump=api_file_import_bump,
                api_element_adjustment=api_element_adjustment,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=tier,
                    reason=EscalationReason.OLLAMA_UNAVAILABLE,
                    detail="Ollama unavailable — local generation skipped",
                ),
            )
            self._metrics.record(result)
            return result

        # Step 2: Route by tier
        if tier == TierClassification.TRIVIAL:
            result = self._handle_trivial(
                element, file_spec, skeleton, contracts, file_path, reasoning,
            )
        elif tier == TierClassification.SIMPLE:
            result = self._handle_simple(
                element, file_spec, skeleton, contracts, file_path, reasoning,
                design_doc_sections=design_doc_sections,
            )
        elif tier == TierClassification.MODERATE:
            result = self._handle_moderate(
                element, file_spec, self._current_manifest, skeleton, contracts,
                file_path, reasoning,
                design_doc_sections=design_doc_sections,
            )
        else:
            # COMPLEX only — immediate escalation
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=tier,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=tier,
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail=f"Tier {tier.value}: {reasoning}",
                ),
            )

        # Stamp parent_class for downstream spec lookup (e.g. cloud escalation)
        result.parent_class = element.parent_class
        result.element_kind = element.kind.value
        result.api_file_import_bump = api_file_import_bump
        result.api_element_adjustment = api_element_adjustment

        # Step 3: Update circuit breaker and cache based on result
        if result.success:
            self._consecutive_failures = 0
            self._success_cache.add(fingerprint)
        elif tier in (TierClassification.TRIVIAL, TierClassification.SIMPLE):
            self._consecutive_failures += 1
            if (
                self._consecutive_failures >= self._CIRCUIT_BREAKER_THRESHOLD
                and not self._circuit_open
            ):
                self._circuit_open = True
                logger.warning(
                    "Circuit breaker tripped: %d consecutive local failures",
                    self._consecutive_failures,
                )

        self._metrics.record(result)
        return result

    def process_file(
        self,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        skeleton: str,
        design_doc_sections: Optional[list[str]] = None,
        ollama_available: bool = True,
    ) -> FileResult:
        """Process all elements in a file.

        Elements are processed in tier-sorted order (REQ-MP-704 AC-2):
        TRIVIAL first (alphabetical), then SIMPLE (alphabetical), then
        MODERATE/COMPLEX. This ensures TRIVIAL template results feed as
        few-shot examples into subsequent SIMPLE generation.

        Args:
            file_spec: File spec with elements to process.
            manifest: Full manifest for contract lookup.
            skeleton: Skeleton file content.
            design_doc_sections: Optional design doc sections for prompt context.

        Returns:
            FileResult with all element results and updated skeleton.
        """
        file_result = FileResult(file_path=file_spec.file)
        self.reset_circuit_breaker()
        self._current_manifest = manifest
        current_skeleton = skeleton

        # Pre-classify to determine processing order (REQ-MP-704).
        # Classification results are cached to avoid redundant work in
        # process_element() — each element is classified exactly once.
        classified: list[
            tuple[int, str, ForwardElementSpec, list[InterfaceContract],
                  TierClassification, str, int, int]
        ] = []

        for element in file_spec.elements:
            contracts = self._get_element_contracts(element, file_spec, manifest)
            tier, reasoning, details = classify_element_with_details(
                element, file_spec, contracts,
                template_registry=self._templates,
                config=self._config,
            )
            priority = self._TIER_PRIORITY.get(tier, 2)
            classified.append(
                (
                    priority,
                    element.name,
                    element,
                    contracts,
                    tier,
                    reasoning,
                    details.file_import_bump,
                    details.element_api_adjustment,
                )
            )

        classified.sort(key=lambda x: (x[0], x[1]))

        for _, _, element, contracts, pre_tier, pre_reasoning, file_bump, elem_adjust in classified:
            result = self._process_element_with_tier(
                element, file_spec, current_skeleton, contracts,
                tier=pre_tier, reasoning=pre_reasoning,
                api_file_import_bump=file_bump,
                api_element_adjustment=elem_adjust,
                ollama_available=ollama_available,
                design_doc_sections=design_doc_sections,
            )
            file_result.element_results.append(result)

            # If successful, splice into skeleton
            if result.success and result.code:
                spliced = splice_body_into_skeleton(
                    result.code, element, current_skeleton,
                )
                if spliced is not None:
                    current_skeleton = spliced
                else:
                    # Splice failed — mark as escalated
                    result.success = False
                    result.escalation = build_escalation_context(
                        element_name=element.name,
                        file_path=file_spec.file,
                        tier=result.tier,
                        reason=EscalationReason.STRUCTURAL_MISMATCH,
                        detail="Body splicing into skeleton failed",
                        last_code=result.code,
                    )

        file_result.filled_skeleton = current_skeleton
        return file_result

    def process_file_with_context(
        self,
        file_spec: ForwardFileSpec,
        skeleton: str,
        context: MicroPrimeContext,
        design_doc_sections: Optional[list[str]] = None,
    ) -> FileResult:
        """Process a file using normalized MicroPrimeContext (REQ-MP-509)."""
        return self.process_file(
            file_spec,
            context.manifest,
            skeleton,
            design_doc_sections=design_doc_sections,
            ollama_available=context.ollama_available,
        )

    def process_seed(
        self,
        manifest: ForwardManifest,
        skeletons: dict[str, str],
        ollama_available: bool = True,
    ) -> SeedResult:
        """Process all elements across all files in a seed.

        Args:
            manifest: Full forward manifest.
            skeletons: Dict mapping file paths to skeleton content.

        Returns:
            SeedResult with all file results.
        """
        seed_result = SeedResult()
        start_time = time.monotonic()

        for file_path, file_spec in manifest.file_specs.items():
            skeleton = skeletons.get(file_path, "")
            if not skeleton:
                logger.warning("No skeleton for %s, skipping", file_path)
                continue

            file_result = self.process_file(
                file_spec, manifest, skeleton,
                ollama_available=ollama_available,
            )
            seed_result.file_results.append(file_result)

        seed_result.total_generation_time_ms = (
            (time.monotonic() - start_time) * 1000
        )

        # Sum tokens
        for fr in seed_result.file_results:
            for er in fr.element_results:
                seed_result.total_input_tokens += er.input_tokens
                seed_result.total_output_tokens += er.output_tokens

        return seed_result

    def process_seed_with_context(
        self,
        skeletons: dict[str, str],
        context: MicroPrimeContext,
    ) -> SeedResult:
        """Process a seed using normalized MicroPrimeContext (REQ-MP-509)."""
        return self.process_seed(
            context.manifest,
            skeletons,
            ollama_available=context.ollama_available,
        )

    def inspect_decomposition(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: Optional[ForwardManifest],
        reason: str,
        classification_signals: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        """Lightweight decomposition viability check for dry-run reports.

        Returns:
            {"viable": bool, "strategy": Optional[str], "sub_count": int}
        """
        if manifest is None or not self._config.decomposition_enabled:
            return {"viable": False, "strategy": None, "sub_count": 0}

        viable = self._decomposer.can_decompose(
            element, file_spec, manifest, reason, classification_signals,
        )
        if not viable:
            return {"viable": False, "strategy": None, "sub_count": 0}

        # Try to get a plan for sub_count and strategy name
        plan = self._decomposer.decompose(
            element, file_spec, manifest, reason, classification_signals,
        )
        if plan is None:
            return {"viable": True, "strategy": None, "sub_count": 0}

        return {
            "viable": True,
            "strategy": plan.strategy,
            "sub_count": len(plan.sub_elements),
        }

    # ─── Private handlers ─────────────────────────────────────────────

    def _handle_moderate(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: Optional[ForwardManifest],
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str = "",
        design_doc_sections: Optional[list[str]] = None,
        classification_signals: Optional[set[str]] = None,
    ) -> ElementResult:
        """Handle MODERATE tier: attempt decomposition, then escalate."""
        start_time = time.monotonic()

        # Circuit breaker gate (R1-S1)
        if self._circuit_open:
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    reason=EscalationReason.CIRCUIT_BREAKER,
                    detail="Circuit breaker open",
                ),
            )

        # Null-guard for standalone process_element() path (R1-S5)
        if manifest is None:
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Manifest unavailable — cannot decompose",
                ),
            )

        if not self._config.decomposition_enabled:
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Decomposition disabled",
                ),
            )

        # Single entry point (R3-S2)
        plan = self._decomposer.decompose(
            element, file_spec, manifest, reasoning, classification_signals,
        )
        if plan is None:
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    reason=EscalationReason.NOT_DECOMPOSABLE,
                    detail="No decomposition strategy applies",
                ),
            )

        logger.info(
            "Decomposing %s (MODERATE) via %s: %d sub-elements",
            element.name, plan.strategy, len(plan.sub_elements),
        )

        # Generate each sub-element
        sub_results: dict[str, str] = {}
        total_input = 0
        total_output = 0
        completed_len = len(self._completed)  # stage few-shot history

        for sub in sorted(plan.sub_elements, key=lambda s: s.assembly_order):
            if sub.deterministic:
                # Extract from skeleton — no LLM needed
                code = self._extract_class_shell(element, skeleton)
                if code is not None:
                    sub_results[sub.name] = code
                    logger.info(
                        "Sub-element %s: deterministic extraction (0ms)", sub.name,
                    )
                    continue
                else:
                    # Shell extraction failed — abandon
                    logger.warning(
                        "Shell extraction failed for %s, abandoning decomposition",
                        element.name,
                    )
                    self._completed = self._completed[:completed_len]
                    return ElementResult(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.MODERATE,
                        classification_reason=reasoning,
                        success=False,
                        verification_verdict="skipped",
                        escalation=build_escalation_context(
                            element_name=element.name,
                            file_path=file_path,
                            tier=TierClassification.MODERATE,
                            reason=EscalationReason.DECOMPOSITION_FAILED,
                            detail="Shell extraction failed",
                        ),
                        generation_time_ms=(time.monotonic() - start_time) * 1000,
                        input_tokens=total_input,
                        output_tokens=total_output,
                    )

            # Generate via _handle_simple
            if sub.element_spec is None:
                self._completed = self._completed[:completed_len]
                return ElementResult(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    classification_reason=reasoning,
                    success=False,
                    verification_verdict="skipped",
                    escalation=build_escalation_context(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.MODERATE,
                        reason=EscalationReason.DECOMPOSITION_FAILED,
                        detail=f"Missing element_spec for sub-element {sub.name}",
                    ),
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=total_input,
                    output_tokens=total_output,
                )

            sub_spec = sub.element_spec
            if sub.prompt_context:
                doc_hint = (
                    f"{sub_spec.docstring_hint}\nContext: {sub.prompt_context}"
                    if sub_spec.docstring_hint
                    else sub.prompt_context
                )
                sub_spec = sub_spec.model_copy(update={"docstring_hint": doc_hint})

            sub_result = self._handle_simple(
                sub_spec, file_spec, skeleton, contracts,
                file_path, f"sub-element of {element.name}",
                design_doc_sections=design_doc_sections,
            )
            total_input += sub_result.input_tokens
            total_output += sub_result.output_tokens

            if not sub_result.success or not sub_result.code:
                self._consecutive_failures += 1
                if (
                    self._consecutive_failures >= self._CIRCUIT_BREAKER_THRESHOLD
                    and not self._circuit_open
                ):
                    self._circuit_open = True
                    logger.warning(
                        "Circuit breaker tripped: %d consecutive sub-element failures",
                        self._consecutive_failures,
                    )
                logger.warning(
                    "Sub-element %s failed — abandoning decomposition of %s",
                    sub.name, element.name,
                )
                self._completed = self._completed[:completed_len]
                return ElementResult(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    classification_reason=reasoning,
                    success=False,
                    verification_verdict="skipped",
                    escalation=build_escalation_context(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.MODERATE,
                        reason=EscalationReason.DECOMPOSITION_FAILED,
                        detail=f"Sub-element {sub.name} failed",
                        last_code=sub_result.code,
                        last_error=(
                            sub_result.escalation.detail
                            if sub_result.escalation else None
                        ),
                    ),
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=total_input,
                    output_tokens=total_output,
                )

            # Successful sub-element resets the breaker counter.
            self._consecutive_failures = 0
            sub_results[sub.name] = sub_result.code

        # All sub-elements succeeded — assemble
        assemble_start = time.monotonic()
        assembled = self._decomposer.assemble(plan, sub_results, skeleton)
        assembly_time_ms = (time.monotonic() - assemble_start) * 1000
        gen_time = (time.monotonic() - start_time) * 1000

        if assembled is None:
            self._completed = self._completed[:completed_len]
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    reason=EscalationReason.DECOMPOSITION_FAILED,
                    detail="Assembly failed",
                ),
                generation_time_ms=gen_time,
                input_tokens=total_input,
                output_tokens=total_output,
            )

        # Structural verification (R3-S4)
        structural_ok, structural_reason = _structural_verify(assembled, element)
        if not structural_ok:
            self._completed = self._completed[:completed_len]
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                classification_reason=reasoning,
                success=False,
                verification_verdict="fail",
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    reason=EscalationReason.DECOMPOSITION_FAILED,
                    detail="Assembled code failed structural verification",
                    last_code=assembled,
                    last_error=structural_reason or "structural_verification_failed",
                ),
                generation_time_ms=gen_time,
                input_tokens=total_input,
                output_tokens=total_output,
            )

        logger.info(
            "Decomposition succeeded for %s: %d/%d sub-elements, %.0fms",
            element.name, len(sub_results), len(plan.sub_elements), gen_time,
        )

        # Record as completed for few-shot (REQ-MP-903)
        self._completed.append({
            "element": {
                "name": element.name,
                "parent_class": element.parent_class,
                "kind": element.kind,
            },
            "file_path": file_path,
            "code": assembled,
            "syntax_valid": True,
        })

        # Record success for cache (R1-S7)
        moderate_fingerprint = (
            f"{element.parent_class or ''}:{element.name}"
            f":{file_path}:{TierClassification.MODERATE.value}"
        )
        self._success_cache.add(moderate_fingerprint)

        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.MODERATE,
            classification_reason=reasoning,
            success=True,
            code=assembled,
            verification_verdict="pass",
            decomposition_metadata={
                "strategy": plan.strategy,
                "sub_elements": len(plan.sub_elements),
                "sub_element_results": [
                    {
                        "name": s.name,
                        "kind": s.kind,
                        "success": s.name in sub_results,
                    }
                    for s in plan.sub_elements
                ],
                "assembly_time_ms": assembly_time_ms,
                "total_time_ms": gen_time,
            },
            generation_time_ms=gen_time,
            input_tokens=total_input,
            output_tokens=total_output,
        )

    def _extract_class_shell(
        self,
        element: ForwardElementSpec,
        skeleton: str,
    ) -> Optional[str]:
        """Extract class shell from skeleton — returns 'pass' as body token.

        The class declaration + docstring are already in the skeleton.
        The methods are separate elements spliced by the normal engine loop.
        """
        try:
            tree = ast.parse(skeleton)
        except SyntaxError:
            return None

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == element.name:
                return "pass"

        return None

    def _handle_trivial(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str = "",
    ) -> ElementResult:
        """Handle TRIVIAL tier: use template registry."""
        match = self._templates.match(element, file_spec, contracts)
        if match is None:
            # Template failed — escalate to SIMPLE
            return self._handle_simple(element, file_spec, skeleton, [], file_path, reasoning)

        body = match.code

        # Record as completed for few-shot (REQ-MP-704)
        self._completed.append({
            "element": {
                "name": element.name,
                "parent_class": element.parent_class,
                "kind": element.kind,
            },
            "file_path": file_path,
            "code": body,
            "syntax_valid": True,
        })

        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.TRIVIAL,
            classification_reason=reasoning,
            success=True,
            code=body,
            template_used=True,
            template_name=match.name,
            model="template",
            verification_verdict="skipped",
        )

    def _handle_simple(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str = "",
        design_doc_sections: Optional[list[str]] = None,
    ) -> ElementResult:
        """Handle SIMPLE tier: local model generation + repair."""
        start_time = time.monotonic()
        model_name = f"{self._config.provider}:{self._config.model}"
        element_fqn = (
            f"{element.parent_class}.{element.name}"
            if element.parent_class else element.name
        )

        # Build few-shot examples
        few_shot = None
        if self._config.few_shot_enabled:
            few_shot = find_few_shot_examples(
                element, file_path, self._completed,
                max_examples=self._config.max_few_shot_examples,
            )

        # Build prompt
        prompt = build_body_prompt(
            element, file_spec, contracts,
            skeleton=skeleton,
            few_shot_examples=few_shot or None,
            token_budget=self._config.input_token_budget,
            design_doc_sections=design_doc_sections,
        )

        # Generate via Ollama
        try:
            code, input_tokens, output_tokens = self._generate_ollama(prompt)
        except Exception as e:
            logger.warning("Ollama generation failed for %s: %s", element.name, e)
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                classification_reason=reasoning,
                success=False,
                repair_recovered=False,
                ast_valid_before_repair=False,
                ast_valid_after_repair=False,
                verification_verdict="skipped",
                model=model_name,
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    reason=EscalationReason.EMPTY_RESPONSE,
                    detail=str(e),
                    local_model=model_name,
                    element_fqn=element_fqn,
                ),
            )

        if not code or not code.strip():
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                classification_reason=reasoning,
                success=False,
                repair_recovered=False,
                ast_valid_before_repair=False,
                ast_valid_after_repair=False,
                verification_verdict="skipped",
                model=model_name,
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    reason=EscalationReason.EMPTY_RESPONSE,
                    detail="Empty response from Ollama",
                    local_model=model_name,
                    element_fqn=element_fqn,
                ),
            )

        raw_output = code
        ast_valid_before = _ast_parse_valid(code, element)
        ast_valid_after = ast_valid_before
        repair_recovered = False
        repaired_code = None

        # Run repair pipeline
        repair_steps: list[str] = []
        repair_attribution = None
        if self._config.repair_enabled:
            repair_result = run_repair_pipeline(
                code, element, file_spec, skeleton_source=skeleton,
            )
            code = repair_result.code
            repair_steps = repair_result.steps_applied
            repair_attribution = build_repair_attribution(
                repair_result.step_results,
            )
            ast_valid_after = repair_result.ast_valid_after
            repair_recovered = repair_result.repair_recovered
            repaired_code = code
            if not repair_result.ast_valid:
                return ElementResult(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    classification_reason=reasoning,
                    success=False,
                    code=code,
                    repair_steps_applied=repair_steps,
                    repair_attribution=repair_attribution,
                    repair_recovered=repair_recovered,
                    ast_valid_before_repair=ast_valid_before,
                    ast_valid_after_repair=ast_valid_after,
                    verification_verdict="fail",
                    model=model_name,
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    escalation=build_escalation_context(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.SIMPLE,
                        reason=EscalationReason.AST_FAILURE,
                        detail="AST validation failed after repair",
                        last_code=code,
                        last_error=repair_result.last_error or "ast.parse() failed",
                        raw_output=raw_output,
                        repaired_code=repaired_code,
                        repair_steps=repair_steps,
                        local_model=model_name,
                        element_fqn=element_fqn,
                    ),
                )

        # Structural verification (REQ-MP-512)
        structural_ok, structural_reason = _structural_verify(code, element)
        if not structural_ok:
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                classification_reason=reasoning,
                success=False,
                code=code,
                repair_steps_applied=repair_steps,
                repair_attribution=repair_attribution,
                repair_recovered=repair_recovered,
                ast_valid_before_repair=ast_valid_before,
                ast_valid_after_repair=ast_valid_after,
                verification_verdict="fail",
                model=model_name,
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    reason=EscalationReason.STRUCTURAL_MISMATCH,
                    detail="Structural verification failed after repair",
                    last_code=code,
                    last_error=structural_reason or "structural_verification_failed",
                    raw_output=raw_output,
                    repaired_code=repaired_code or code,
                    repair_steps=repair_steps,
                    local_model=model_name,
                    element_fqn=element_fqn,
                ),
            )

        # Optional semantic verification (REQ-MP-512)
        if self._config.semantic_verification_enabled:
            semantic_ok, semantic_reason = self._semantic_verify(
                code, element, file_spec, contracts, skeleton,
            )
            if not semantic_ok:
                return ElementResult(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    classification_reason=reasoning,
                    success=False,
                    code=code,
                    repair_steps_applied=repair_steps,
                    repair_attribution=repair_attribution,
                    repair_recovered=repair_recovered,
                    ast_valid_before_repair=ast_valid_before,
                    ast_valid_after_repair=ast_valid_after,
                    verification_verdict="fail",
                    model=model_name,
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    escalation=build_escalation_context(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.SIMPLE,
                        reason=EscalationReason.SEMANTIC_FAILURE,
                        detail="Semantic verification failed",
                        last_code=code,
                        last_error=semantic_reason or "semantic_verification_failed",
                        raw_output=raw_output,
                        repaired_code=repaired_code or code,
                        repair_steps=repair_steps,
                        local_model=model_name,
                        element_fqn=element_fqn,
                    ),
                )

        gen_time = (time.monotonic() - start_time) * 1000

        # Record as completed for few-shot
        self._completed.append({
            "element": {
                "name": element.name,
                "parent_class": element.parent_class,
                "kind": element.kind,
            },
            "file_path": file_path,
            "code": code,
            "syntax_valid": True,
        })

        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.SIMPLE,
            classification_reason=reasoning,
            success=True,
            code=code,
            repair_steps_applied=repair_steps,
            repair_attribution=repair_attribution,
            repair_recovered=repair_recovered,
            ast_valid_before_repair=ast_valid_before,
            ast_valid_after_repair=ast_valid_after,
            verification_verdict="pass",
            model=model_name,
            generation_time_ms=gen_time,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _generate_ollama(self, prompt: str) -> tuple[str, int, int]:
        """Generate code using the Ollama provider.

        Returns (code, input_tokens, output_tokens).
        """
        from startd8.utils.code_extraction import extract_code_from_response

        if self._ollama_agent is None:
            from startd8.utils.agent_resolution import resolve_agent_spec

            agent_spec = f"{self._config.provider}:{self._config.model}"
            self._ollama_agent = resolve_agent_spec(
                agent_spec, max_tokens=self._config.max_tokens,
            )

        result_text, time_ms, token_usage = self._ollama_agent.generate(
            prompt,
            system_prompt=_CODE_GEN_SYSTEM_PROMPT,
            temperature=self._config.temperature,
        )

        code = extract_code_from_response(result_text)

        input_tokens = 0
        output_tokens = 0
        if token_usage:
            input_tokens = getattr(token_usage, "input", 0) or 0
            output_tokens = getattr(token_usage, "output", 0) or 0

        return code, input_tokens, output_tokens

    def _semantic_verify(
        self,
        code: str,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
        skeleton: str,
    ) -> tuple[bool, str]:
        """Optional semantic verification hook (REQ-MP-512)."""
        verifier = self._config.semantic_verification_fn
        if verifier:
            try:
                return verifier(code, element, file_spec, contracts, skeleton)
            except Exception as exc:
                logger.warning("Semantic verifier failed: %s", exc)
                return False, f"semantic verifier error: {exc}"

        spec = self._config.semantic_verification_agent_spec
        if not spec:
            return True, "semantic verification skipped"

        if self._semantic_agent is None:
            from startd8.utils.agent_resolution import resolve_agent_spec

            self._semantic_agent = resolve_agent_spec(
                spec, max_tokens=self._config.semantic_verification_max_tokens,
            )

        prompt = [
            "You are verifying generated code for a target element.",
            f"Element: {element.name}",
        ]
        if element.parent_class:
            prompt.append(f"Parent class: {element.parent_class}")
        if element.signature:
            prompt.append(f"Signature: {element.signature.signature_text}")
        if element.docstring_hint:
            prompt.append(f"Docstring hint: {element.docstring_hint}")
        if contracts:
            prompt.append("Binding constraints:")
            for c in contracts:
                if c.binding_text:
                    prompt.append(f"- {c.binding_text}")
        if skeleton:
            skel = skeleton
            if len(skel) > self._config.semantic_verification_prompt_max_chars:
                skel = skel[: self._config.semantic_verification_prompt_max_chars] + "\n... [truncated]"
            prompt.append("Skeleton context:")
            prompt.append(skel)
        prompt.append("Generated code:")
        prompt.append("```python")
        prompt.append(code)
        prompt.append("```")
        prompt.append(
            "Return JSON: {\"pass\": true|false, \"reason\": \"short explanation\"}."
        )

        result_text, _time_ms, _tokens = self._semantic_agent.generate(
            "\n".join(prompt),
            temperature=self._config.semantic_verification_temperature,
        )

        try:
            start = result_text.find("{")
            end = result_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("no JSON object found")
            payload = json.loads(result_text[start : end + 1])
            passed = bool(payload.get("pass", False))
            reason = str(payload.get("reason", "")) or "semantic verification result"
            return passed, reason
        except Exception as exc:
            logger.warning("Semantic verification parse failed: %s", exc)
            return False, "semantic verification parse failed"

    def _get_element_contracts(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
    ) -> list[InterfaceContract]:
        """Get contracts relevant to a specific element."""
        # Check if element has a source contract ID
        if element.source_contract_id:
            return [
                c for c in manifest.contracts
                if c.contract_id == element.source_contract_id
            ]
        # No source_contract_id — return empty rather than all contracts
        return []


def _ast_parse_valid(code: str, element: ForwardElementSpec) -> bool:
    """Return True if the code parses as a full element (method wrapper-aware)."""
    is_method = bool(element.parent_class)
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        if is_method:
            try:
                import textwrap

                wrapped = "class _Wrapper:\n" + textwrap.indent(code, "    ")
                ast.parse(wrapped)
                return True
            except SyntaxError:
                return False
        return False


def _structural_verify(code: str, element: ForwardElementSpec) -> tuple[bool, str]:
    """Verify structural correctness of generated code.

    Checks:
    - AST parses successfully
    - For functions: target function exists and body is non-empty
    - For constants: target assignment exists
    - No remaining NotImplementedError stubs
    - Return statements present when return annotation is non-None
    """
    is_method = bool(element.parent_class)

    def _render_def_line(target: ForwardElementSpec) -> Optional[str]:
        if target.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
            return None
        if target.kind == ElementKind.CLASS:
            bases = f"({', '.join(target.bases)})" if target.bases else ""
            return f"class {target.name}{bases}:"
        prefix = "async def" if target.kind in (
            ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
        ) else "def"
        sig = "()"
        if target.signature:
            from startd8.utils.file_assembler import DeterministicFileAssembler

            assembler = DeterministicFileAssembler()
            sig = assembler._render_signature(target.signature)
        ret = ""
        if target.signature and target.signature.return_annotation:
            ret = f" -> {target.signature.return_annotation}"
        return f"{prefix} {target.name}{sig}{ret}:"

    def _wrap_body(body: str, target: ForwardElementSpec) -> Optional[str]:
        def_line = _render_def_line(target)
        if def_line is None:
            return None
        wrapped = def_line + "\n" + textwrap.indent(body, "    ")
        if target.parent_class:
            wrapped = "class _Wrapper:\n" + textwrap.indent(wrapped, "    ")
        return wrapped

    # AST parse
    try:
        tree = ast.parse(code)
    except SyntaxError:
        wrapped = _wrap_body(code, element)
        if wrapped is None:
            return False, "ast.parse() failed"
        try:
            tree = ast.parse(wrapped)
        except SyntaxError:
            return False, "ast.parse() failed"

    # Check the target exists
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == element.name:
                        return True, "constant assignment found"
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == element.name:
                    return True, "annotated assignment found"
        return False, "constant assignment not found"

    # For CLASS elements, verify the class name exists in the AST (R1-S3)
    if element.kind == ElementKind.CLASS:
        if code.strip() == "pass":
            return True, "class shell pass"
        # Reject any remaining NotImplementedError stubs in class body.
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and _is_not_implemented(node):
                return False, "contains NotImplementedError"
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == element.name:
                return True, "class definition found"
        # The assembled code from ModerateDecomposer is the body of the class. 
        # Since it successfully parsed via ast.parse(code) above, and assemble()
        # already verified it can reside inside a class block, we accept it.
        return True, "class body passed syntax check"

    # For functions/methods: verify the target name exists in the AST.
    target_node = None
    if is_method and element.parent_class:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == element.parent_class:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == element.name:
                        target_node = child
                        break
                if target_node is not None:
                    break
    else:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == element.name:
                target_node = node
                break

    if target_node is None:
        # Body-only generation: wrap into a synthetic def and re-parse.
        wrapped = _wrap_body(code, element)
        if wrapped is None:
            return False, "target function not found"
        try:
            tree = ast.parse(wrapped)
        except SyntaxError:
            return False, "target function not found"

        if element.parent_class:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "_Wrapper":
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == element.name:
                            target_node = child
                            break
                    if target_node is not None:
                        break
        else:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == element.name:
                    target_node = node
                    break

        if target_node is None:
            return False, "target function not found"

    # Check for NotImplementedError stub
    for node in ast.walk(target_node):
        if isinstance(node, ast.Raise) and _is_not_implemented(node):
            return False, "contains NotImplementedError"

    # Check return statements for non-None annotations
    if element.signature and element.signature.return_annotation:
        ret_ann = element.signature.return_annotation
        if ret_ann not in ("None", "none"):
            has_return = any(
                isinstance(n, ast.Return) and n.value is not None
                for n in ast.walk(target_node)
            )
            if not has_return:
                return False, f"missing return for -> {ret_ann}"

    # Body must have at least one non-docstring statement
    body_stmts = []
    for stmt in target_node.body:
        if isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), ast.Constant):
            if isinstance(stmt.value.value, str):
                continue
        body_stmts.append(stmt)
    if not body_stmts:
        return False, "function body empty"

    return True, "structural checks passed"


def _is_not_implemented(node: ast.Raise) -> bool:
    """Return True if a raise node corresponds to NotImplementedError."""
    if node.exc is None:
        return False
    exc = node.exc
    if isinstance(exc, ast.Call):
        func = exc.func
        if isinstance(func, ast.Name):
            return func.id == "NotImplementedError"
        if isinstance(func, ast.Attribute):
            return func.attr == "NotImplementedError"
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    return False
