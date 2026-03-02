"""Prime Contractor CodeGenerator Adapter (REQ-MP-504).

Implements the ``CodeGenerator`` protocol, wrapping the Micro Prime engine
for use in PrimeContractorWorkflow. Elements that can't be handled locally
are delegated to a fallback ``CodeGenerator``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.contractors.protocols import CodeGenerator, GenerationResult
from startd8.forward_manifest import ForwardManifest
from startd8.logging_config import get_logger
from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.micro_prime.models import MicroPrimeConfig

logger = get_logger(__name__)


class MicroPrimeCodeGenerator:
    """``CodeGenerator`` implementation using the Micro Prime engine.

    Processes TRIVIAL and SIMPLE elements locally, delegating MODERATE and
    COMPLEX elements to a fallback ``CodeGenerator`` (typically the
    LeadContractor pattern).

    Args:
        config: Micro Prime engine configuration.
        fallback: Fallback code generator for elements beyond local capability.
        manifest: Forward manifest for element metadata.
        skeletons: Dict of file path -> skeleton content.
    """

    def __init__(
        self,
        config: Optional[MicroPrimeConfig] = None,
        fallback: Optional[CodeGenerator] = None,
        manifest: Optional[ForwardManifest] = None,
        skeletons: Optional[dict[str, str]] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._fallback = fallback
        self._manifest = manifest
        self._skeletons = skeletons or {}
        self._engine = MicroPrimeEngine(config=self._config)

    def generate(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """Generate code for the given task.

        Attempts local generation first. For elements that require cloud
        processing, delegates to the fallback generator if available.

        Args:
            task: Description of what to implement.
            context: Additional context (existing code, requirements, etc.).
            target_files: Expected output file paths.

        Returns:
            GenerationResult with success status and generated file paths.
        """
        manifest = context.get("manifest") or self._manifest
        skeletons = context.get("skeletons") or self._skeletons

        # REQ-MP-702: Auto-generate skeletons from manifest when missing.
        # Prime Contractor has no SCAFFOLD phase, so stubs are produced on
        # demand using DeterministicFileAssembler.
        if manifest is not None and not skeletons:
            skeletons = self._generate_skeletons(manifest, target_files)

        if manifest is None:
            logger.warning(
                "MicroPrimeCodeGenerator: no manifest, delegating to fallback",
            )
            return self._delegate_to_fallback(task, context, target_files)

        # Process target files through the engine
        generated_files: list[Path] = []
        total_input = 0
        total_output = 0
        has_escalations = False

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            skeleton = skeletons.get(file_path, "")

            if file_spec is None or not skeleton:
                has_escalations = True
                continue

            file_result = self._engine.process_file(file_spec, manifest, skeleton)

            if file_result.filled_skeleton:
                # Write the filled skeleton
                output_path = Path(file_path)
                generated_files.append(output_path)

            # Track tokens
            for er in file_result.element_results:
                total_input += er.input_tokens
                total_output += er.output_tokens

            if file_result.escalated_count > 0:
                has_escalations = True

        # If there are escalations and we have a fallback, delegate remaining
        if has_escalations and self._fallback is not None:
            fallback_result = self._delegate_to_fallback(
                task, context, target_files,
            )
            # Merge results
            generated_files.extend(fallback_result.generated_files)
            total_input += fallback_result.input_tokens
            total_output += fallback_result.output_tokens
            return GenerationResult(
                success=fallback_result.success,
                generated_files=generated_files,
                input_tokens=total_input,
                output_tokens=total_output,
                model=f"micro-prime+{fallback_result.model}",
                metadata={
                    "micro_prime_files": len(generated_files) - len(fallback_result.generated_files),
                    "fallback_files": len(fallback_result.generated_files),
                },
            )

        return GenerationResult(
            success=len(generated_files) > 0,
            generated_files=generated_files,
            input_tokens=total_input,
            output_tokens=total_output,
            model=f"{self._config.provider}:{self._config.model}",
            metadata={"micro_prime_only": True},
        )

    def _generate_skeletons(
        self,
        manifest: ForwardManifest,
        target_files: List[str],
    ) -> dict[str, str]:
        """Generate stub skeletons from manifest for target files only.

        Uses ``DeterministicFileAssembler`` to render ``ForwardFileSpec``
        elements into Python source with ``raise NotImplementedError`` stubs.
        Only the current feature's target files are rendered (not the entire
        manifest).  Per-file failures are logged and skipped — they do not
        block other files.

        Returns:
            Dict mapping file path to skeleton source text.
        """
        from startd8.utils.file_assembler import DeterministicFileAssembler

        assembler = DeterministicFileAssembler()
        skeletons: dict[str, str] = {}

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            if file_spec is None:
                logger.debug("No file_spec for %s, skipping skeleton", file_path)
                continue
            try:
                source = assembler.render_file(file_spec)
                skeletons[file_path] = source
                logger.debug(
                    "Generated skeleton for %s (%d lines)",
                    file_path,
                    source.count("\n") + 1,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to generate skeleton for %s: %s", file_path, exc,
                )

        return skeletons

    def _delegate_to_fallback(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """Delegate to the fallback code generator."""
        if self._fallback is None:
            return GenerationResult(
                success=False,
                error="No fallback generator configured and elements need cloud processing",
            )
        return self._fallback.generate(task, context, target_files)
