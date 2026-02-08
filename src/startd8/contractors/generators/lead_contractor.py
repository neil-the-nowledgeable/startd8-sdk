"""
Lead Contractor Code Generator.

Implements the CodeGenerator protocol using the Lead Contractor workflow
(Claude specs/reviews, cheaper models draft).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..protocols import CodeGenerator, GenerationResult

logger = logging.getLogger("startd8.contractors.generators")


class LeadContractorCodeGenerator:
    """
    Code generator using the Lead Contractor workflow.

    The Lead Contractor pattern uses Claude as the architect/reviewer
    while cheaper models (Gemini Flash, GPT-4o-mini) do the drafting.

    Example:
        generator = LeadContractorCodeGenerator(
            lead_agent="anthropic:claude-sonnet-4-20250514",
            drafter_agent="gemini:gemini-2.5-flash-lite",
        )
        result = generator.generate(
            task="Implement a rate limiter",
            context={"language": "Python"},
            target_files=["rate_limiter.py"],
        )
    """

    def __init__(
        self,
        lead_agent: str = "anthropic:claude-sonnet-4-20250514",
        drafter_agent: str = "gemini:gemini-2.5-flash-lite",
        max_iterations: int = 3,
        pass_threshold: int = 80,
        output_dir: Optional[Path] = None,
        max_tokens: Optional[int] = None,
        fail_on_truncation: bool = True,
        check_truncation: bool = True,
        strict_truncation: bool = False,
    ):
        """
        Initialize the Lead Contractor code generator.

        Args:
            lead_agent: Agent spec for lead contractor (architect/reviewer)
            drafter_agent: Agent spec for drafter (implementation)
            max_iterations: Maximum draft/review iterations
            pass_threshold: Minimum score to pass review (0-100)
            output_dir: Directory for generated files
            max_tokens: Override max_tokens for agent creation (None = provider default)
            fail_on_truncation: Fail workflow if truncation detected (default: True)
            check_truncation: Enable truncation detection (default: True)
            strict_truncation: Use strict detection threshold (default: False)
        """
        self.lead_agent = lead_agent
        self.drafter_agent = drafter_agent
        self.max_iterations = max_iterations
        self.pass_threshold = pass_threshold
        self.output_dir = output_dir or Path("generated")
        self.max_tokens = max_tokens
        self.fail_on_truncation = fail_on_truncation
        self.check_truncation = check_truncation
        self.strict_truncation = strict_truncation

    def generate(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """
        Generate code using the Lead Contractor workflow.

        Args:
            task: Description of what to implement
            context: Additional context (existing code, requirements, etc.)
            target_files: Expected output file paths

        Returns:
            GenerationResult with success status and generated file paths
        """
        try:
            # Import the workflow
            from startd8.workflows.builtin.lead_contractor_workflow import (
                LeadContractorWorkflow,
            )

            workflow = LeadContractorWorkflow()

            # Build config — include target_files in context so spec mentions them
            enriched_context = dict(context)
            if len(target_files) > 1:
                enriched_context["target_files"] = target_files

            config = {
                "task_description": task,
                "context": enriched_context,
                "lead_agent": self.lead_agent,
                "drafter_agent": self.drafter_agent,
                "max_iterations": self.max_iterations,
                "pass_threshold": self.pass_threshold,
                "fail_on_truncation": self.fail_on_truncation,
                "check_truncation": self.check_truncation,
                "strict_truncation": self.strict_truncation,
            }
            if self.max_tokens is not None:
                config["max_tokens"] = self.max_tokens

            # Run the workflow
            result = workflow.run(config=config)

            if not result.success:
                return GenerationResult(
                    success=False,
                    error=result.error or "Lead Contractor workflow failed",
                    input_tokens=result.metrics.input_tokens if result.metrics else 0,
                    output_tokens=result.metrics.output_tokens if result.metrics else 0,
                    cost_usd=result.metrics.total_cost if result.metrics else 0.0,
                    model=self.lead_agent,
                )

            # Get the final implementation
            final_implementation = result.output.get("final_implementation", "")

            # Write to output files
            generated_files = []

            # For multi-file targets, try to split the output per file
            per_file_code: dict = {}
            if len(target_files) > 1:
                from startd8.utils.code_extraction import extract_multi_file_code

                per_file_code = extract_multi_file_code(
                    final_implementation, target_files
                )
                if len(per_file_code) == len(target_files):
                    logger.info(
                        "Split implementation into %d per-file blocks",
                        len(per_file_code),
                    )
                else:
                    # Drafter didn't produce distinct code for every target file.
                    # Falling back to the full blob would write identical content
                    # to multiple files (e.g. hook code into a component file).
                    # Fail fast with a clear error instead of silent corruption.
                    matched = list(per_file_code.keys())
                    unmatched = [f for f in target_files if f not in per_file_code]
                    error_msg = (
                        f"Multi-file split failed: drafter output matched "
                        f"{matched or 'no files'} but not {unmatched}. "
                        f"The drafter must produce distinct code blocks for "
                        f"each target file. Consider retrying or splitting "
                        f"this feature into single-file tasks."
                    )
                    logger.error(error_msg)
                    return GenerationResult(
                        success=False,
                        error=error_msg,
                        input_tokens=result.metrics.input_tokens if result.metrics else 0,
                        output_tokens=result.metrics.output_tokens if result.metrics else 0,
                        cost_usd=result.metrics.total_cost if result.metrics else 0.0,
                        model=self.lead_agent,
                    )

            for target_file in target_files:
                output_path = self.output_dir / Path(target_file).name
                output_path.parent.mkdir(parents=True, exist_ok=True)
                content = per_file_code.get(target_file, final_implementation)
                output_path.write_text(content, encoding="utf-8")
                generated_files.append(output_path)
                logger.info(f"Generated: {output_path}")

            # If no target files specified, use a default
            if not generated_files:
                feature_name = context.get("feature_name", "code")
                output_path = self.output_dir / f"{feature_name}.py"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(final_implementation, encoding="utf-8")
                generated_files.append(output_path)

            return GenerationResult(
                success=True,
                generated_files=generated_files,
                input_tokens=result.metrics.input_tokens if result.metrics else 0,
                output_tokens=result.metrics.output_tokens if result.metrics else 0,
                cost_usd=result.metrics.total_cost if result.metrics else 0.0,
                iterations=result.metadata.get("total_iterations", 1),
                model=self.lead_agent,
                metadata={
                    "lead_cost": result.metadata.get("lead_cost", 0.0),
                    "drafter_cost": result.metadata.get("drafter_cost", 0.0),
                    "cost_efficiency_ratio": result.metadata.get(
                        "cost_efficiency_ratio", 0.0
                    ),
                },
            )

        except ImportError as e:
            return GenerationResult(
                success=False,
                error=f"LeadContractorWorkflow not available: {e}",
            )
        except Exception as e:
            logger.error(f"Code generation failed: {e}", exc_info=True)
            return GenerationResult(
                success=False,
                error=str(e),
            )
