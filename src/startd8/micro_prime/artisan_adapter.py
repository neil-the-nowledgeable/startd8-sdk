"""Artisan IMPLEMENT Phase Pre-Pass Adapter (REQ-MP-503, 506).

Runs the Micro Prime engine before ``ArtisanChunkExecutor`` processes chunks,
filling TRIVIAL and SIMPLE element bodies in skeleton files. Escalated
elements are added back to the chunk list with error context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from startd8.forward_manifest import ForwardManifest
from startd8.logging_config import get_logger
from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.micro_prime.metrics import generate_cost_report
from startd8.micro_prime.models import MicroPrimeConfig

logger = get_logger(__name__)


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

        # Process all files
        seed_result = self._engine.process_seed(manifest, skeletons)

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
                    escalated_elements.append({
                        "element_name": er.element_name,
                        "file_path": er.file_path,
                        "tier": er.tier.value,
                        "reason": er.escalation.reason.value,
                        "detail": er.escalation.detail,
                        "last_error": er.escalation.last_error,
                        "last_code": er.escalation.last_code,
                    })

        # Generate cost report
        cost_report = generate_cost_report(seed_result, self._config)

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
        )


class PrePassResult:
    """Result from a MicroPrimePrePass run."""

    def __init__(
        self,
        filled_skeletons: dict[str, str],
        escalated_elements: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> None:
        self.filled_skeletons = filled_skeletons
        self.escalated_elements = escalated_elements
        self.metrics = metrics

    @property
    def local_success_count(self) -> int:
        return int(self.metrics.get("local_success_count", 0))

    @property
    def escalated_count(self) -> int:
        return len(self.escalated_elements)
