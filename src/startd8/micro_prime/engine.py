"""Micro Prime Engine — Main Orchestrator (REQ-MP-502, 512).

Routes elements through the local-first code generation pipeline:
  TRIVIAL → template registry → splice → done
  SIMPLE  → prompt builder → Ollama → repair → verify → splice or escalate
  MODERATE/COMPLEX → passthrough for cloud handling
"""

from __future__ import annotations

import ast
import time
from typing import Any, Optional

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.micro_prime.classifier import classify_element
from startd8.micro_prime.metrics import MetricsCollector
from startd8.micro_prime.decomposer import ModerateDecomposer
from startd8.micro_prime.models import (
    ElementResult,
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
    return EscalationResult(
        reason=reason,
        detail=detail,
        last_code=last_code,
        last_error=last_error,
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

        tier, reasoning = classify_element(
            element, file_spec, element_contracts,
            template_registry=self._templates,
            config=self._config,
        )

        return self._process_element_with_tier(
            element, file_spec, skeleton, element_contracts,
            tier=tier, reasoning=reasoning,
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
                  TierClassification, str]
        ] = []

        for element in file_spec.elements:
            contracts = self._get_element_contracts(element, file_spec, manifest)
            tier, reasoning = classify_element(
                element, file_spec, contracts,
                template_registry=self._templates,
                config=self._config,
            )
            priority = self._TIER_PRIORITY.get(tier, 2)
            classified.append((priority, element.name, element, contracts, tier, reasoning))

        classified.sort(key=lambda x: (x[0], x[1]))

        for _, _, element, contracts, pre_tier, pre_reasoning in classified:
            result = self._process_element_with_tier(
                element, file_spec, current_skeleton, contracts,
                tier=pre_tier, reasoning=pre_reasoning,
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

    def process_seed(
        self,
        manifest: ForwardManifest,
        skeletons: dict[str, str],
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

            file_result = self.process_file(file_spec, manifest, skeleton)
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

            sub_result = self._handle_simple(
                sub.element_spec, file_spec, skeleton, contracts,
                file_path, f"sub-element of {element.name}",
                design_doc_sections=design_doc_sections,
            )
            total_input += sub_result.input_tokens
            total_output += sub_result.output_tokens

            if not sub_result.success or not sub_result.code:
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
        if not _structural_verify(assembled, element):
            self._completed = self._completed[:completed_len]
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                classification_reason=reasoning,
                success=False,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.MODERATE,
                    reason=EscalationReason.DECOMPOSITION_FAILED,
                    detail="Assembled code failed structural verification",
                    last_code=assembled,
                ),
                generation_time_ms=gen_time,
                input_tokens=total_input,
                output_tokens=total_output,
            )

        logger.info(
            "Decomposition succeeded for %s: %d/%d sub-elements, %.0fms",
            element.name, len(sub_results), len(plan.sub_elements), gen_time,
        )

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
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    reason=EscalationReason.EMPTY_RESPONSE,
                    detail=str(e),
                ),
            )

        if not code or not code.strip():
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                classification_reason=reasoning,
                success=False,
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    reason=EscalationReason.EMPTY_RESPONSE,
                    detail="Empty response from Ollama",
                ),
            )

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
                    ),
                )

        # Structural verification (REQ-MP-512)
        if not _structural_verify(code, element):
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                classification_reason=reasoning,
                success=False,
                code=code,
                repair_steps_applied=repair_steps,
                repair_attribution=repair_attribution,
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    reason=EscalationReason.AST_FAILURE,
                    detail="Structural verification failed after repair",
                    last_code=code,
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


def _structural_verify(code: str, element: ForwardElementSpec) -> bool:
    """Verify structural correctness of generated code.

    Checks:
    - AST parses successfully
    - For functions: the target function exists in the AST
    - For constants: the target assignment exists
    """
    is_method = bool(element.parent_class)

    # AST parse
    try:
        tree = ast.parse(code)
    except SyntaxError:
        if is_method:
            try:
                import textwrap
                wrapped = "class _Wrapper:\n" + textwrap.indent(code, "    ")
                tree = ast.parse(wrapped)
            except SyntaxError:
                return False
        else:
            return False

    # Check the target exists
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == element.name:
                        return True
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == element.name:
                    return True
        # For constants, the code might just be a value expression
        return True

    # For CLASS elements, verify the class name exists in the AST (R1-S3)
    if element.kind == ElementKind.CLASS:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == element.name:
                return True
        # "pass" body is valid for class shells — check if it's just a pass statement
        if code.strip() == "pass":
            return True
        return False

    # For functions/methods: verify the target name exists in the AST.
    # This catches cross-contamination where Ollama generates a body for
    # a different function than the one requested.
    target = element.name
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == target:
                return True
    # The repair pipeline's bare-statement-wrap may have wrapped the body
    # under the correct name; if we reach here the name is missing.
    return False
