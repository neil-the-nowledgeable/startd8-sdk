"""
Primary Contractor Code Generator.

Implements the CodeGenerator protocol using the Primary Contractor workflow
(Claude specs/reviews, cheaper models draft).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from ...logging_config import get_logger
from ...repair.orchestrator import strip_repair_markers
from ..protocols import (
    DRAFT_MODEL_CLAUDE_HAIKU,
    GenerationResult,
    VALIDATE_MODEL_CLAUDE_SONNET,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_downstream_files(
    unmatched_files: List[str],
    design_doc: str,
) -> List[str]:
    """Detect files that the design doc designates as downstream/shared.

    Scans the design document for signals that a file is explicitly NOT
    meant to be implemented by this task (e.g. "F-002+", "downstream",
    "shared module", "implemented by later tasks").

    Returns the subset of ``unmatched_files`` that match these patterns.
    This enables the smart retry gate: if all unmatched files are
    downstream, we skip the expensive retry and go straight to stub,
    saving ~50% LLM cost.
    """
    if not design_doc or not unmatched_files:
        return []

    import re

    # Patterns that indicate a file is downstream/shared
    _DOWNSTREAM_PATTERNS = [
        r"F-\d+\+",           # "F-002+" style references
        r"downstream\s+task",
        r"later\s+task",
        r"shared,?\s+F-",     # "shared, F-002+"
        r"implement(?:ed)?\s+by\s+(?:downstream|later|other)",
        r"stub\s+(?:for|until)",
    ]
    _compiled = [re.compile(p, re.IGNORECASE) for p in _DOWNSTREAM_PATTERNS]

    downstream: List[str] = []
    for filepath in unmatched_files:
        filename = filepath.rsplit("/", 1)[-1]
        # Find lines mentioning this file in the design doc
        for line in design_doc.split("\n"):
            if filename in line:
                if any(pat.search(line) for pat in _compiled):
                    downstream.append(filepath)
                    break

    return downstream


class PrimaryContractorCodeGenerator:
    """
    Code generator using the Primary Contractor workflow.

    The Primary Contractor pattern uses Claude as the architect/reviewer
    while cheaper models (Gemini Flash, GPT-4o-mini) do the drafting.

    Example:
        generator = PrimaryContractorCodeGenerator(
            lead_agent=VALIDATE_MODEL_CLAUDE_SONNET.agent_spec,
            drafter_agent=DRAFT_MODEL_CLAUDE_HAIKU.agent_spec,
        )
        result = generator.generate(
            task="Implement a rate limiter",
            context={"language": "Python"},
            target_files=["rate_limiter.py"],
        )
    """

    def __init__(
        self,
        lead_agent: str = VALIDATE_MODEL_CLAUDE_SONNET.agent_spec,
        drafter_agent: str = DRAFT_MODEL_CLAUDE_HAIKU.agent_spec,
        max_iterations: int = 3,
        pass_threshold: int = 80,
        output_dir: Optional[Path] = None,
        max_tokens: Optional[int] = None,
        fail_on_truncation: bool = True,
        check_truncation: bool = True,
        strict_truncation: bool = False,
    ):
        """
        Initialize the Primary Contractor code generator.

        Args:
            lead_agent: Agent spec for primary contractor (architect/reviewer)
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
        self.output_dir = Path(output_dir).resolve() if output_dir else Path("generated")
        self.max_tokens = max_tokens
        self.fail_on_truncation = fail_on_truncation
        self.check_truncation = check_truncation
        self.strict_truncation = strict_truncation

    def _persist_artifact(
        self, feature_name: str, artifact_type: str, content: str,
    ) -> Optional[Path]:
        """Write a workflow artifact as Markdown alongside generated code.

        Failures are logged but never propagated — artifact persistence is
        advisory and must not abort an otherwise successful generation.
        """
        if not self.output_dir or not content:
            return None
        try:
            # Sanitize feature_name to prevent path traversal
            safe_name = "".join(
                c if c.isalnum() or c in "-_" else "_"
                for c in feature_name.replace("/", "_").replace("..", "_")
            )
            artifacts_dir = self.output_dir / ".artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            out_path = artifacts_dir / f"{safe_name}-{artifact_type}.md"
            out_path.write_text(content, encoding="utf-8")
            logger.info("Wrote %s: %s", artifact_type, out_path)
            return out_path
        except OSError as exc:
            logger.warning(
                "Failed to persist %s artifact for %s: %s",
                artifact_type, feature_name, exc,
            )
            return None

    def generate(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """
        Generate code using the Primary Contractor workflow.

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
                PrimaryContractorWorkflow,
            )

            workflow = PrimaryContractorWorkflow()

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
            # Per-task override from context (design_calibration implement_max_output_tokens)
            max_tokens = context.get("max_tokens")
            if max_tokens is not None:
                config["max_tokens"] = max_tokens
            elif self.max_tokens is not None:
                config["max_tokens"] = self.max_tokens

            # Run the workflow
            result = workflow.run(config=config)

            if not result.success:
                return GenerationResult(
                    success=False,
                    error=result.error or "Primary Contractor workflow failed",
                    input_tokens=result.metrics.input_tokens if result.metrics else 0,
                    output_tokens=result.metrics.output_tokens if result.metrics else 0,
                    cost_usd=result.metrics.total_cost if result.metrics else 0.0,
                    model=self.lead_agent,
                )

            # Get the final implementation
            final_implementation = result.output.get("final_implementation", "")

            # Persist workflow artifacts as .md files
            lc_summary = result.output.get("summary", {})
            feature_name = context.get("feature_name", "code")

            if lc_summary.get("spec_raw"):
                self._persist_artifact(feature_name, "spec", lc_summary["spec_raw"])

            for draft in lc_summary.get("drafts_raw", []):
                iteration = draft.get("iteration", 1)
                self._persist_artifact(
                    feature_name, f"draft-{iteration}",
                    draft.get("implementation", ""),
                )

            for review in lc_summary.get("reviews_raw", []):
                iteration = review.get("iteration", 1)
                review_content = (
                    f"# Review (iteration {iteration})\n\n"
                    f"**Score:** {review.get('score', '?')}/100\n"
                    f"**Passed:** {review.get('passed', '?')}\n\n"
                    f"{review.get('review_text', '')}"
                )
                self._persist_artifact(feature_name, f"review-{iteration}", review_content)

            if lc_summary.get("integration_raw"):
                self._persist_artifact(
                    feature_name, "integration", lc_summary["integration_raw"],
                )

            # Write to output files
            generated_files = []

            # For multi-file targets, try to split the output per file
            per_file_code: dict = {}
            if len(target_files) > 1:
                from startd8.utils.code_extraction import extract_multi_file_code

                # PCA-607: Prefer raw drafter response (contains ALL code blocks)
                # over final_implementation (which is the LARGEST code block only).
                raw_drafter = result.output.get("last_draft_raw_response", "")
                split_source = raw_drafter if raw_drafter else final_implementation
                per_file_code = extract_multi_file_code(
                    split_source, target_files
                )
                if len(per_file_code) == len(target_files):
                    logger.info(
                        "Split implementation into %d per-file blocks",
                        len(per_file_code),
                    )
                else:
                    # Retry once with explicit feedback about missing files
                    unmatched = [f for f in target_files if f not in per_file_code]

                    # ── Smart retry gate ──────────────────────────────────
                    # Check if ALL unmatched files are downstream/shared stubs
                    # (design doc says they belong to later tasks).  If so,
                    # skip the expensive retry — the drafter intentionally
                    # omitted them, and retrying won't change its mind.
                    # Go straight to stub fallback, saving ~50% LLM cost.
                    downstream_files = _detect_downstream_files(
                        unmatched, context.get("design_document") or "",
                    )
                    all_unmatched_are_downstream = (
                        len(downstream_files) > 0
                        and set(unmatched) == set(downstream_files)
                    )

                    if all_unmatched_are_downstream:
                        logger.info(
                            "Smart retry gate: all %d unmatched files are "
                            "downstream/shared (%s). Skipping retry — "
                            "stub fallback will handle them.",
                            len(downstream_files),
                            downstream_files,
                        )
                    elif unmatched and "_multi_file_retry" not in context:
                        logger.warning(
                            "Multi-file split failed (missing %s). Retrying once with explicit feedback.",
                            unmatched,
                        )
                        retry_context = dict(context)
                        retry_context["_multi_file_retry"] = True
                        unmatched_list = "\n".join(f"  - {f}" for f in unmatched)
                        # Layer 5 (defense-in-depth): per-file role hints
                        # so the retry feedback tells the model *what* each
                        # missing file should contain, not just that it's missing.
                        from startd8.workflows.builtin.prompts import (
                            format_prompt as _fmt_prime,
                            get_template as _get_prime_template,
                        )
                        role_hints = []
                        for missing in unmatched:
                            hint_name = "role_hints_init" if missing.endswith("__init__.py") else "role_hints_module"
                            role_hints.append(
                                _fmt_prime("prime_context", hint_name, filepath=missing)
                            )
                        role_hint_text = "\n".join(role_hints)

                        retry_context["_multi_file_retry_initial_feedback"] = (
                            _fmt_prime(
                                "prime_context", "multi_file_retry",
                                unmatched_list=unmatched_list,
                                role_hint_text=role_hint_text,
                                target_files=target_files,
                                unmatched=unmatched,
                            )
                        )
                        return self.generate(
                            task=task,
                            context=retry_context,
                            target_files=target_files,
                        )

                    # Defense-in-depth: after retry exhausted (or skipped via
                    # smart retry gate), generate stubs for unmatched files
                    # rather than failing the entire task.
                    logger.warning(
                        "Multi-file split incomplete for %s. "
                        "Generating stubs for unmatched files: %s%s",
                        context.get("task_id", "unknown"),
                        unmatched,
                        " (downstream — retry skipped)" if all_unmatched_are_downstream else "",
                    )
                    per_file_code = extract_multi_file_code(
                        final_implementation, target_files, stub_missing=True
                    )
                    stubbed_files = [
                        f for f in unmatched if f in per_file_code
                    ]
                    if stubbed_files:
                        logger.warning(
                            "Stub recovery: auto-generated stubs for %s. "
                            "These are minimal placeholders — downstream "
                            "tasks should implement the real logic.",
                            stubbed_files,
                        )

            for target_file in target_files:
                # Use full target path (e.g. src/pkg/__init__.py), not just filename.
                # Defense Layer 1: correct path resolution prevents project-root writes.
                output_path = self.output_dir / target_file
                output_path.parent.mkdir(parents=True, exist_ok=True)
                content = per_file_code.get(target_file, final_implementation)
                # L7: Strip repair traceability markers before project write
                content = strip_repair_markers(content)
                output_path.write_text(content, encoding="utf-8")
                generated_files.append(output_path)
                logger.info("Generated: %s", output_path)

            # If no target files specified, use a default
            if not generated_files:
                feature_name = context.get("feature_name", "code")
                output_path = self.output_dir / f"{feature_name}.py"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    strip_repair_markers(final_implementation), encoding="utf-8",
                )
                generated_files.append(output_path)

            # Build metadata with stub info for observability
            gen_metadata: dict = {
                "lead_cost": result.metadata.get("lead_cost", 0.0),
                "drafter_cost": result.metadata.get("drafter_cost", 0.0),
                "cost_efficiency_ratio": result.metadata.get(
                    "cost_efficiency_ratio", 0.0
                ),
                "artifact_dir": str(self.output_dir / ".artifacts"),
                "lead_agent_spec": self.lead_agent,
                "drafter_agent_spec": self.drafter_agent,
            }
            # Forward raw LLM responses for Kaizen capture (REQ-KZ-201)
            if lc_summary.get("spec_raw"):
                gen_metadata["spec_raw_response"] = lc_summary["spec_raw"]
            drafts_raw = lc_summary.get("drafts_raw", [])
            if drafts_raw:
                gen_metadata["draft_raw_response"] = drafts_raw[-1].get(
                    "implementation", ""
                )
            reviews_raw = lc_summary.get("reviews_raw", [])
            if reviews_raw:
                gen_metadata["review_raw_response"] = reviews_raw[-1].get(
                    "review_text", ""
                )
            # Upstream truncation signal (secondary — Gate 4 works independently)
            upstream_summary = (result.output or {}).get("summary") or {}
            if isinstance(upstream_summary, dict) and upstream_summary.get("was_truncated"):
                gen_metadata["_upstream_truncation"] = {
                    "was_truncated": True,
                    "truncation_source": upstream_summary.get("truncation_source"),
                }
            # Record multi-file split outcome for observability (Layer 8)
            if len(target_files) > 1:
                from startd8.utils.code_extraction import STUB_SENTINEL

                stubbed = [
                    f for f in target_files
                    if f in per_file_code and STUB_SENTINEL in per_file_code[f]
                ]
                gen_metadata["multi_file_split"] = {
                    "target_count": len(target_files),
                    "matched_count": len(target_files) - len(stubbed),
                    "stubbed_count": len(stubbed),
                    "stubbed_files": stubbed,
                    "retry_used": "_multi_file_retry" in context,
                }
                if stubbed:
                    logger.info(
                        "Multi-file split outcome for %s: %d/%d matched by LLM, "
                        "%d auto-stubbed %s",
                        context.get("task_id", "unknown"),
                        len(target_files) - len(stubbed),
                        len(target_files),
                        len(stubbed),
                        stubbed,
                    )

            return GenerationResult(
                success=True,
                generated_files=generated_files,
                input_tokens=result.metrics.input_tokens if result.metrics else 0,
                output_tokens=result.metrics.output_tokens if result.metrics else 0,
                cost_usd=result.metrics.total_cost if result.metrics else 0.0,
                iterations=result.metadata.get("total_iterations", 1),
                model=self.lead_agent,
                metadata=gen_metadata,
            )

        except ImportError as e:
            return GenerationResult(
                success=False,
                error=f"PrimaryContractorWorkflow not available: {e}",
            )
        except Exception as e:
            logger.error("Code generation failed: %s", e, exc_info=True)
            return GenerationResult(
                success=False,
                error=str(e),
            )


# Backward-compat alias (Phase 4 rename: Lead → Primary)
LeadContractorCodeGenerator = PrimaryContractorCodeGenerator
