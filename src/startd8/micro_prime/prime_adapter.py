"""Prime Contractor CodeGenerator Adapter (REQ-MP-504).

Implements the ``CodeGenerator`` protocol, wrapping the Micro Prime engine
for use in PrimeContractorWorkflow. Elements that can't be handled locally
are delegated to a fallback ``CodeGenerator``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import urlopen

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
        output_dir: Directory for writing generated files.  Defaults to cwd.
    """

    def __init__(
        self,
        config: Optional[MicroPrimeConfig] = None,
        fallback: Optional[CodeGenerator] = None,
        manifest: Optional[ForwardManifest] = None,
        skeletons: Optional[dict[str, str]] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._fallback = fallback
        self._manifest = manifest
        self._skeletons = skeletons or {}
        self._output_dir = output_dir or Path(".")
        self._engine = MicroPrimeEngine(config=self._config)
        self._ollama_available: Optional[bool] = None

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

        # REQ-MP-711: Ollama availability guard — check once per instance
        if not self._check_ollama_available():
            logger.info("Ollama unavailable — delegating all to fallback")
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
                # REQ-MP-703: Write filled skeleton to disk
                output_path = self._output_dir / file_path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    file_result.filled_skeleton, encoding="utf-8",
                )
                generated_files.append(output_path)
                logger.info(
                    "Micro Prime wrote %s (%d lines, %d elements filled)",
                    file_path,
                    file_result.filled_skeleton.count("\n") + 1,
                    sum(1 for er in file_result.element_results if er.success),
                )

            # Track tokens
            for er in file_result.element_results:
                total_input += er.input_tokens
                total_output += er.output_tokens

            if file_result.escalated_count > 0:
                has_escalations = True

        local_file_count = len(generated_files)

        # If there are escalations and we have a fallback, delegate remaining.
        # Fallback writes its own files — we only collect paths, no double-write.
        if has_escalations and self._fallback is not None:
            fallback_result = self._delegate_to_fallback(
                task, context, target_files,
            )
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
                    "micro_prime_files_written": local_file_count,
                    "fallback_files_written": len(fallback_result.generated_files),
                },
            )

        return GenerationResult(
            success=local_file_count > 0,
            generated_files=generated_files,
            input_tokens=total_input,
            output_tokens=total_output,
            model=f"{self._config.provider}:{self._config.model}",
            metadata={
                "micro_prime_only": True,
                "micro_prime_files_written": local_file_count,
            },
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

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is reachable and the configured model is pulled.

        Result is cached on ``self._ollama_available`` so the HTTP check
        only fires once per adapter instance.  Uses a 5-second timeout to
        avoid blocking generation (REQ-MP-711).
        """
        if self._ollama_available is not None:
            return self._ollama_available

        base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        url = f"{base_url}/api/tags"
        model_name = self._config.model

        try:
            with urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())

            model_names: list[str] = []
            for m in data.get("models", []):
                name = m.get("name", "")
                model_names.append(name)
                if ":" in name:
                    model_names.append(name.split(":")[0])

            model_base = model_name.split(":")[0]
            if model_name in model_names or model_base in model_names:
                self._ollama_available = True
                return True

            logger.warning(
                "Ollama model '%s' not found (available: %s)",
                model_name,
                sorted(set(model_names)),
            )
            self._ollama_available = False
            return False

        except (ConnectionRefusedError, TimeoutError, URLError, OSError) as exc:
            logger.warning("Ollama not reachable at %s: %s", base_url, exc)
            self._ollama_available = False
            return False

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
