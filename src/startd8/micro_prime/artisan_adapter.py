"""Artisan IMPLEMENT Phase Pre-Pass Adapter (REQ-MP-503, 506).

Runs the Micro Prime engine before ``ArtisanChunkExecutor`` processes chunks,
filling TRIVIAL and SIMPLE element bodies in skeleton files. Escalated
elements are added back to the chunk list with error context.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import urlopen

from startd8.forward_manifest import ForwardManifest
from startd8.logging_config import get_logger
from startd8.micro_prime.context import MicroPrimeContext
from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.micro_prime.metrics import generate_cost_report
from startd8.micro_prime.models import MicroPrimeConfig

logger = get_logger(__name__)


@dataclass
class _ChunkView:
    """Minimal chunk view for MicroPrimeContext.from_artisan()."""

    file_targets: list[str]
    file_contents: dict[str, str]


class MicroPrimePrePass:
    """Pre-pass adapter for the Artisan IMPLEMENT phase.

    Processes skeleton files from the SCAFFOLD phase through the Micro Prime
    engine, filling TRIVIAL and SIMPLE element bodies. Elements that can't be
    handled locally are returned as remaining work for the cloud executor.

    Args:
        config: Micro Prime configuration.
        manifest: Forward manifest from SCAFFOLD/DESIGN phase.
        skeletons: Dict mapping file paths to skeleton content.
        project_root: Project root directory.
    """

    def __init__(
        self,
        config: Optional[MicroPrimeConfig] = None,
        manifest: Optional[ForwardManifest] = None,
        skeletons: Optional[dict[str, str]] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._manifest = manifest
        self._skeletons = skeletons or {}
        self._project_root = project_root or Path(".")
        self._engine = MicroPrimeEngine(config=self._config)
        self._ollama_available: Optional[bool] = None

    def run(
        self,
        manifest: Optional[ForwardManifest] = None,
        skeletons: Optional[dict[str, str]] = None,
    ) -> PrePassResult:
        """Run the Micro Prime pre-pass.

        Args:
            manifest: Override manifest (if not set in constructor).
            skeletons: Override skeletons (if not set in constructor).

        Returns:
            PrePassResult with filled skeletons and escalated elements.
        """
        manifest = manifest or self._manifest
        skeletons = skeletons or self._skeletons

        if manifest is None:
            logger.warning("MicroPrimePrePass: no manifest provided, skipping")
            return PrePassResult(
                filled_skeletons=skeletons,
                escalated_elements=[],
                metrics={},
            )

        if not skeletons:
            logger.warning("MicroPrimePrePass: no skeletons provided, skipping")
            return PrePassResult(
                filled_skeletons={},
                escalated_elements=[],
                metrics={},
            )

        self._engine.metrics_collector.clear()
        ollama_ok = self._check_ollama_available()
        if not ollama_ok:
            logger.warning(
                "MicroPrimePrePass: Ollama unavailable — SIMPLE elements will be escalated",
            )

        # Process all files using normalized context (REQ-MP-509)
        context = MicroPrimeContext.from_artisan(
            _ChunkView(
                file_targets=list(skeletons.keys()),
                file_contents={},
            ),
            {
                "forward_manifest": manifest,
                "binding_constraints": [],
                "ollama_model": self._config.model,
            },
            ollama_ok,
        )
        if context is None:
            logger.warning("MicroPrimePrePass: failed to build context, skipping")
            return PrePassResult(
                filled_skeletons=skeletons,
                escalated_elements=[],
                metrics={},
            )
        seed_result = self._engine.process_seed_with_context(skeletons, context)

        # Collect results
        filled_skeletons: dict[str, str] = {}
        escalated_elements: list[dict[str, Any]] = []

        for file_result in seed_result.file_results:
            # Update skeleton with filled bodies
            if file_result.filled_skeleton:
                filled_skeletons[file_result.file_path] = file_result.filled_skeleton
            else:
                filled_skeletons[file_result.file_path] = skeletons.get(
                    file_result.file_path, "",
                )

            # Collect escalated elements (REQ-MP-506)
            for er in file_result.element_results:
                if er.escalation is not None:
                    esc_ctx = er.escalation.context
                    escalated_elements.append({
                        "element_name": er.element_name,
                        "file_path": er.file_path,
                        "tier": er.tier.value,
                        "reason": er.escalation.reason.value,
                        "detail": er.escalation.detail,
                        "last_error": er.escalation.last_error,
                        "last_code": er.escalation.last_code,
                        "raw_output": esc_ctx.raw_output if esc_ctx else "",
                        "repaired_code": esc_ctx.repaired_code if esc_ctx else "",
                        "repair_steps": (
                            list(esc_ctx.repair_steps_applied) if esc_ctx else []
                        ),
                    })

        # Generate cost report
        cost_report = generate_cost_report(seed_result, self._config)
        element_metrics = [
            m.model_dump() for m in self._engine.metrics_collector.metrics
        ]
        elements_filled = sum(
            1
            for fr in seed_result.file_results
            for er in fr.element_results
            if er.success
        )

        logger.info(
            "MicroPrimePrePass complete: %d/%d elements handled locally, "
            "%d escalated, %.1f%% success rate",
            cost_report.local_success_count,
            cost_report.total_elements,
            cost_report.escalated_count,
            cost_report.success_rate * 100,
        )

        return PrePassResult(
            filled_skeletons=filled_skeletons,
            escalated_elements=escalated_elements,
            metrics=cost_report.model_dump(),
            element_metrics=element_metrics,
            elements_filled=elements_filled,
        )

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is reachable and the configured model is pulled."""
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
                if not isinstance(m, dict):
                    continue
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

        except (socket.timeout, TimeoutError, URLError, OSError) as exc:
            logger.warning("Ollama not reachable at %s: %s", base_url, exc)
            self._ollama_available = False
            return False


class PrePassResult:
    """Result from a MicroPrimePrePass run."""

    def __init__(
        self,
        filled_skeletons: dict[str, str],
        escalated_elements: list[dict[str, Any]],
        metrics: dict[str, Any],
        element_metrics: Optional[list[dict[str, Any]]] = None,
        elements_filled: int = 0,
    ) -> None:
        self.filled_skeletons = filled_skeletons
        self.escalated_elements = escalated_elements
        self.metrics = metrics
        self.element_metrics = element_metrics or []
        self.elements_filled = elements_filled

    @property
    def local_success_count(self) -> int:
        return int(self.metrics.get("local_success_count", 0))

    @property
    def escalated_count(self) -> int:
        return len(self.escalated_elements)
