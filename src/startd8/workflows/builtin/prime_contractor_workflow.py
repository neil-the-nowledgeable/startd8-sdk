"""
PrimeContractorWorkflow adapter — WorkflowBase wrapper for CLI/registry integration.

Exposes the PrimeContractorWorkflow through `startd8 workflow run prime-contractor`
with all relevant configuration options (micro-prime, complexity routing, etc.).

Pattern follows lead_contractor_workflow.py.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..base import WorkflowBase, ProgressCallback
from ..models import (
    WorkflowMetadata,
    WorkflowInput,
    WorkflowResult,
    WorkflowMetrics,
    AgentCount,
)
from ...logging_config import get_logger

if TYPE_CHECKING:
    from ...agents import BaseAgent

logger = get_logger(__name__)


class PrimeContractorWorkflowAdapter(WorkflowBase):
    """WorkflowBase adapter wrapping PrimeContractorWorkflow for registry discovery.

    Enables ``startd8 workflow run prime-contractor --seed <path> [--micro-prime]``
    by translating a flat config dict into PrimeContractorWorkflow initialization,
    seed loading, optional micro-prime / complexity-routing enablement, and execution.
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="prime-contractor",
            name="Prime Contractor Workflow",
            description="Multi-feature batch code generation with optional micro-prime local routing",
            version="1.0.0",
            capabilities=[
                "batch-code-generation",
                "multi-feature",
                "micro-prime",
                "complexity-routing",
            ],
            tags=["development", "code-generation", "batch", "contractor"],
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            max_agents=2,
            inputs=[
                WorkflowInput(
                    name="seed_path", type="string", required=True,
                    description="Path to context seed JSON",
                ),
                WorkflowInput(
                    name="project_root", type="string", required=False,
                    description="Target project root (default: cwd)",
                ),
                WorkflowInput(
                    name="max_features", type="number", required=False,
                    description="Maximum features to process",
                ),
                WorkflowInput(
                    name="cost_budget", type="number", required=False,
                    description="Max cost in USD",
                ),
                WorkflowInput(
                    name="task_filter", type="string", required=False,
                    description="Comma-separated task IDs to process",
                ),
                WorkflowInput(
                    name="auto_commit", type="boolean", required=False,
                    description="Commit each feature after integration",
                ),
                WorkflowInput(
                    name="micro_prime", type="boolean", required=False,
                    description="Enable micro-prime local generation",
                ),
                WorkflowInput(
                    name="micro_prime_model", type="string", required=False,
                    description="Ollama model for micro-prime",
                ),
                WorkflowInput(
                    name="micro_prime_max_tokens", type="number", required=False,
                    description="Max tokens for micro-prime",
                ),
                WorkflowInput(
                    name="micro_prime_no_templates", type="boolean", required=False,
                    description="Disable micro-prime templates",
                ),
                WorkflowInput(
                    name="micro_prime_no_repair", type="boolean", required=False,
                    description="Disable micro-prime repair",
                ),
                WorkflowInput(
                    name="complexity_routing", type="boolean", required=False,
                    description="Enable complexity-based routing",
                ),
                WorkflowInput(
                    name="lead_agent", type="string", required=False,
                    description="Lead agent spec (provider:model)",
                ),
                WorkflowInput(
                    name="drafter_agent", type="string", required=False,
                    description="Drafter agent spec (provider:model)",
                ),
                WorkflowInput(
                    name="walkthrough", type="boolean", required=False,
                    description="Persist prompts without LLM calls",
                ),
                WorkflowInput(
                    name="force_regenerate", type="boolean", required=False,
                    description="Force regeneration ignoring cache",
                ),
            ],
        )

    def _custom_validate(self, config: Dict[str, Any]) -> List[str]:
        """Validate prime-contractor-specific config."""
        errors: List[str] = []
        seed_path = config.get("seed_path")
        if seed_path and not Path(seed_path).exists():
            errors.append(f"Seed file not found: {seed_path}")
        project_root = config.get("project_root")
        if project_root and not Path(project_root).is_dir():
            errors.append(f"Project root not found: {project_root}")
        return errors

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List["BaseAgent"]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute the Prime Contractor workflow.

        Stages:
            1. Initialize PrimeContractorWorkflow with code generator
            2. Load seed context and feature queue from seed JSON
            3. Enable micro-prime local generation (if requested)
            4. Enable complexity-based routing (if requested)
            5. Apply task filter, run workflow, convert result
        """
        from ...contractors.prime_contractor import PrimeContractorWorkflow
        from ...contractors.generators.lead_contractor import PrimaryContractorCodeGenerator
        from ...contractors.queue import FeatureStatus

        started_at = datetime.now(timezone.utc)
        wf_id = self.metadata.workflow_id

        seed_path = config["seed_path"]
        project_root = Path(config["project_root"]) if config.get("project_root") else Path.cwd()
        auto_commit = config.get("auto_commit", False)
        walkthrough = config.get("walkthrough", False)
        force_regenerate = config.get("force_regenerate", False)
        lead_agent = config.get("lead_agent")
        drafter_agent = config.get("drafter_agent")

        self._emit_progress(on_progress, 1, 5, "Initializing Prime Contractor")

        try:
            # Build code generator if agent specs provided
            code_generator = None
            if lead_agent or drafter_agent:
                output_dir = project_root / "generated"
                code_generator = PrimaryContractorCodeGenerator(
                    output_dir=output_dir,
                    lead_agent=lead_agent,
                    drafter_agent=drafter_agent,
                )

            workflow = PrimeContractorWorkflow(
                project_root=project_root,
                dry_run=False,
                auto_commit=auto_commit,
                code_generator=code_generator,
                walkthrough=walkthrough,
                allow_dirty=True,
            )
            workflow.force_regenerate = force_regenerate

            # Load seed — parse JSON with specific error handling
            self._emit_progress(on_progress, 2, 5, "Loading seed context")
            seed_file = Path(seed_path)
            try:
                seed_data = json.loads(seed_file.read_text())
            except json.JSONDecodeError as e:
                return WorkflowResult.from_error(
                    wf_id, f"Invalid JSON in seed file {seed_path}: {e}"
                )
            workflow.queue.add_features_from_seed(seed_path)
            workflow.load_seed_context(seed_data)

            # Enable micro-prime if requested
            if config.get("micro_prime"):
                self._emit_progress(on_progress, 3, 5, "Enabling micro-prime")
                mp_kwargs: Dict[str, Any] = {}
                if config.get("micro_prime_model"):
                    mp_kwargs["model"] = config["micro_prime_model"]
                if config.get("micro_prime_max_tokens") is not None:
                    mp_kwargs["max_tokens"] = config["micro_prime_max_tokens"]
                if config.get("micro_prime_no_templates"):
                    mp_kwargs["templates_enabled"] = False
                if config.get("micro_prime_no_repair"):
                    mp_kwargs["repair_enabled"] = False

                mp_config = None
                if mp_kwargs:
                    from ...micro_prime.models import MicroPrimeConfig
                    mp_config = MicroPrimeConfig(**mp_kwargs)

                workflow.enable_micro_prime(mp_config)

            # Enable complexity routing if requested — use getattr for private attrs
            if config.get("complexity_routing"):
                mp_generator = None
                if (
                    getattr(workflow, "_micro_prime_enabled", False)
                    and getattr(workflow, "_original_code_generator", None)
                ):
                    mp_generator = workflow.code_generator
                workflow.enable_complexity_routing(
                    trivial_generator=mp_generator,
                    simple_generator=mp_generator,
                )

            # Apply task filter
            task_filter_str = config.get("task_filter")
            if task_filter_str:
                allowed_ids = {t.strip() for t in task_filter_str.split(",") if t.strip()}
                kept = 0
                for fid, feature in workflow.queue.features.items():
                    if fid not in allowed_ids:
                        feature.status = FeatureStatus.COMPLETE
                    else:
                        kept += 1
                logger.info(
                    "Task filter applied: %d IDs requested, %d tasks kept",
                    len(allowed_ids), kept,
                )

            # Run
            self._emit_progress(on_progress, 4, 5, "Running workflow")
            max_features = config.get("max_features")
            cost_budget = config.get("cost_budget")
            result_dict = workflow.run(
                max_features=max_features,
                max_cost_usd=cost_budget,
            )

            self._emit_progress(on_progress, 5, 5, "Complete")

            # Convert to WorkflowResult — failed==0 is success (even if queue was empty)
            failed = result_dict.get("failed", 0)
            success = failed == 0

            metrics = WorkflowMetrics(
                total_time_ms=int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
                input_tokens=result_dict.get("total_input_tokens", 0),
                output_tokens=result_dict.get("total_output_tokens", 0),
                total_cost=result_dict.get("total_cost_usd", 0.0),
                step_count=result_dict.get("processed", 0),
            )

            return WorkflowResult(
                workflow_id=wf_id,
                success=success,
                output=result_dict,
                metrics=metrics,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                metadata={
                    "micro_prime": config.get("micro_prime", False),
                    "complexity_routing": config.get("complexity_routing", False),
                },
            )

        except Exception as e:
            logger.error("Prime Contractor workflow failed: %s", e, exc_info=True)
            return WorkflowResult.from_error(wf_id, str(e))
