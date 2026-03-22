"""Lightweight adapter bridging Prime Contractor to Artisan ReviewPhaseHandler.

REQ-RFL-120: Reviews Prime Contractor output using the existing Artisan
review infrastructure (~100 lines of adapter, zero modification to
ReviewPhaseHandler).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


class PrimeReviewAdapter:
    """Reviews Prime Contractor output using Artisan's ReviewPhaseHandler.

    The adapter:
    1. Maps FeatureSpec → synthetic SeedTask (with all required fields)
    2. Reads generated files from disk
    3. Packs validation signals into test_results (zero-modification path)
    4. Calls ReviewPhaseHandler._review_task()
    """

    def __init__(
        self,
        review_agent: Optional[str] = None,
        lead_agent: Optional[str] = None,
    ) -> None:
        self._review_agent = review_agent
        self._lead_agent = lead_agent
        self._handler: Any = None  # Lazy init

    def _ensure_handler(self) -> None:
        if self._handler is not None:
            return
        from startd8.contractors.context_seed.core import (
            HandlerConfig,
            ReviewPhaseHandler,
        )
        config = HandlerConfig(
            review_agent=self._review_agent,
            lead_agent=self._lead_agent or HandlerConfig.lead_agent,
        )
        self._handler = ReviewPhaseHandler(handler_config=config)

    def review_feature(
        self,
        feature: Any,  # FeatureSpec
        project_root: Path,
        integration_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Review a completed feature.

        Returns:
            Dict with keys: score, verdict, issues, suggestions, cost,
            tokens, task_id, status.  On error: verdict="ERROR".
        """
        self._ensure_handler()

        task = self._feature_to_seed_task(feature)

        generated_code = self._read_generated_code(feature, project_root)
        if not generated_code:
            return {
                "score": None,
                "verdict": "SKIP",
                "issues": [],
                "suggestions": [],
                "reason": "no generated code found",
            }

        # Pack validation signals into test_results (Option B — zero
        # ReviewPhaseHandler modification).
        test_results = self._pack_validation_as_test_results(
            integration_metadata or {},
        )

        try:
            review = self._handler._review_task(
                task=task,
                generated_code=generated_code,
                test_results=test_results,
            )
            return review
        except Exception:
            logger.warning(
                "Review failed for %s", feature.name, exc_info=True,
            )
            return {
                "score": None,
                "verdict": "ERROR",
                "issues": [],
                "suggestions": [],
            }

    def _feature_to_seed_task(self, feature: Any) -> Any:
        """Map FeatureSpec fields to a synthetic SeedTask.

        Provides all required positional fields that SeedTask.__init__
        expects (SeedTask is a dataclass with ~20 required fields).
        """
        from startd8.seeds.models import SeedTask

        meta = feature.metadata or {} if hasattr(feature, "metadata") else {}
        return SeedTask(
            task_id=str(feature.id),
            title=feature.name,
            task_type="task",
            story_points=0,
            priority="medium",
            labels=[],
            depends_on=[],
            description=feature.description or "",
            target_files=list(feature.target_files) if feature.target_files else [],
            estimated_loc=0,
            feature_id=str(feature.id),
            domain=meta.get("domain", "general"),
            domain_reasoning="",
            environment_checks=[],
            prompt_constraints=meta.get("prompt_constraints", []),
            post_generation_validators=[],
            available_siblings=[],
            existing_content_hash=None,
            design_doc_sections=[],
            artifact_types_addressed=[],
            file_scope={},
        )

    def _read_generated_code(
        self, feature: Any, project_root: Path,
    ) -> str:
        """Read generated files from disk into a single code string."""
        parts: List[str] = []
        file_list = feature.generated_files or feature.target_files or []
        for fpath in file_list:
            full = project_root / fpath
            if full.is_file():
                try:
                    parts.append(f"# {fpath}\n{full.read_text(encoding='utf-8')}")
                except OSError:
                    continue
        return "\n\n".join(parts)

    @staticmethod
    def _pack_validation_as_test_results(
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Pack disk compliance + repair data into test_results dict.

        Uses the test_results slot (Option B) so ReviewPhaseHandler
        renders validation signals without any modification.
        """
        results: Dict[str, Any] = {}
        compliance = metadata.get("disk_compliance")
        if compliance:
            results["validation_results"] = compliance
            score = metadata.get("disk_quality_score")
            if score is not None:
                results["disk_quality_score"] = score
        repair = metadata.get("repair_summaries")
        if repair:
            results["repair_summary"] = repair
        return results
