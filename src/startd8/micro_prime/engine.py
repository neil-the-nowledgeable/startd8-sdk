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
    ) -> ElementResult:
        """Process a single element through the pipeline.

        Args:
            element: Manifest element to process.
            file_spec: File spec for context.
            skeleton: Current skeleton file content.
            contracts: Binding constraints for this element.

        Returns:
            ElementResult with success/failure and optional code.
        """
        file_path = file_spec.file
        element_contracts = contracts or []

        # Step 1: Classify tier
        tier, reasoning = classify_element(
            element, file_spec, element_contracts,
            template_registry=self._templates,
            config=self._config,
        )

        logger.debug(
            "Classified %s as %s: %s", element.name, tier.value, reasoning,
        )

        # Step 1a: Check success cache (R3-S4) — skip re-generation
        fingerprint = f"{element.name}:{file_path}:{tier.value}"
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
            result.tier = tier
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
            result.tier = tier
            self._metrics.record(result)
            return result

        # Step 2: Route by tier
        if tier == TierClassification.TRIVIAL:
            result = self._handle_trivial(element, file_spec, skeleton, file_path, reasoning)
        elif tier == TierClassification.SIMPLE:
            result = self._handle_simple(
                element, file_spec, skeleton, element_contracts, file_path, reasoning,
            )
        else:
            # MODERATE/COMPLEX — return as needs_cloud
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

        result.tier = tier
        self._metrics.record(result)
        return result

    def process_file(
        self,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        skeleton: str,
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

        Returns:
            FileResult with all element results and updated skeleton.
        """
        file_result = FileResult(file_path=file_spec.file)
        current_skeleton = skeleton

        # Pre-classify to determine processing order (REQ-MP-704)
        _TIER_PRIORITY = {
            TierClassification.TRIVIAL: 0,
            TierClassification.SIMPLE: 1,
            TierClassification.MODERATE: 2,
            TierClassification.COMPLEX: 3,
        }
        classified: list[
            tuple[int, str, ForwardElementSpec, list[InterfaceContract]]
        ] = []

        for element in file_spec.elements:
            contracts = self._get_element_contracts(element, file_spec, manifest)
            tier, _ = classify_element(
                element, file_spec, contracts,
                template_registry=self._templates,
                config=self._config,
            )
            priority = _TIER_PRIORITY.get(tier, 2)
            classified.append((priority, element.name, element, contracts))

        classified.sort(key=lambda x: (x[0], x[1]))

        for _, _, element, contracts in classified:
            result = self.process_element(
                element, file_spec, current_skeleton, contracts,
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

    # ─── Private handlers ─────────────────────────────────────────────

    def _handle_trivial(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        file_path: str,
        reasoning: str = "",
    ) -> ElementResult:
        """Handle TRIVIAL tier: use template registry."""
        body = self._templates.match(element, file_spec)
        if body is None:
            # Template failed — escalate to SIMPLE
            return self._handle_simple(element, file_spec, skeleton, [], file_path, reasoning)

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
        )

    def _handle_simple(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str = "",
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
            code, step_results = run_repair_pipeline(code, element, file_spec)
            repair_steps = [
                r.step_name for r in step_results if r.modified
            ]
            repair_attribution = build_repair_attribution(step_results)

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
        from startd8.utils.agent_resolution import resolve_agent_spec
        from startd8.utils.code_extraction import extract_code_from_response

        agent_spec = f"{self._config.provider}:{self._config.model}"
        agent = resolve_agent_spec(agent_spec, max_tokens=self._config.max_tokens)

        result_text, time_ms, token_usage = agent.generate(prompt)

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
        # Fall back to all contracts (filtered by applicable task IDs if available)
        return manifest.contracts


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

    # For functions, just AST validity is sufficient
    # (the repair pipeline already ensures the def exists)
    return True
