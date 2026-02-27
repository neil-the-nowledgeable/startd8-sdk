"""
DefaultImplementationEngine — full per-task pipeline orchestrator.

Orchestrates: spec creation -> [draft -> truncation check -> review -> feedback]* -> result.
Extracted from ``LeadContractorWorkflow._aexecute`` iteration loop.
"""

from typing import Any, Optional

from ..logging_config import get_logger
from ..utils.agent_resolution import resolve_agent_spec
from .models import EngineRequest, EngineResult
from .spec_builder import build_spec
from .drafter import create_draft
from .reviewer import format_review_feedback, review_draft


__all__ = ["DefaultImplementationEngine"]

logger = get_logger(__name__)

# Continuation prompt injected on truncation auto-retry
_TRUNCATION_CONTINUATION_FEEDBACK = (
    "Your previous response was TRUNCATED — it was cut off before "
    "the code was complete. You MUST output the COMPLETE file in a "
    "single response. Do not add commentary — output ONLY the full "
    "source code for the file."
)


class DefaultImplementationEngine:
    """Implementation engine that orchestrates the full per-task pipeline.

    Implements the ``ImplementationEngine`` protocol.

    The engine does NOT include an integration/polish phase — that is
    Prime-specific and remains in LeadContractorWorkflow.

    Truncation handling: when a draft is truncated and iterations remain,
    the engine skips the review phase, injects a continuation prompt, and
    re-drafts immediately.  Truncation events are recorded in the result.
    """

    def build_and_execute(self, request: EngineRequest) -> EngineResult:
        """Run the full spec -> draft -> review loop for a single task.

        Flow:
        1. Create spec from task description and context
        2. Iteration loop (max N):
           a. Create draft from spec + feedback
           b. If truncated and iterations remain: auto-retry with continuation
           c. Review draft
           d. If passed: break
           e. Format review feedback for next iteration
        3. Assemble result

        Args:
            request: Engine request with task description, context, and config.

        Returns:
            EngineResult with spec, drafts, reviews, and final code.
        """
        result = EngineResult()

        try:
            # --- Resolve agents ---
            drafter_agent = self._resolve_agent(request.drafter_agent_spec)
            reviewer_agent = self._resolve_agent(request.reviewer_agent_spec)

            # --- Phase 1: Spec creation ---
            logger.info(
                "Engine: creating spec for task (template=%s)",
                request.template_key or "auto",
            )
            spec = build_spec(
                agent=reviewer_agent,  # Spec built by the lead/reviewer agent
                task_description=request.task_description,
                context=dict(request.context),  # Copy to avoid mutation
                output_format=request.output_format,
                template_key=request.template_key,
                edit_min_pct=request.edit_min_pct,
            )
            result.spec = spec
            result.spec_cost = spec.cost
            result.total_input_tokens += spec.input_tokens
            result.total_output_tokens += spec.output_tokens
            result.total_cost += spec.cost

            # --- Phase 2: Iteration loop ---
            review_feedback = ""
            max_iterations = request.max_iterations
            current_implementation = ""

            for iteration in range(1, max_iterations + 1):
                logger.info(
                    "Engine: drafting iteration %d/%d",
                    iteration, max_iterations,
                )

                draft = create_draft(
                    agent=drafter_agent,
                    spec=spec,
                    feedback=review_feedback,
                    iteration=iteration,
                    check_truncation=request.check_truncation,
                    strict_truncation=request.strict_truncation,
                    target_files=request.target_files,
                    existing_files=request.existing_files,
                    edit_mode=request.edit_mode,
                )
                result.drafts.append(draft)
                result.draft_cost += draft.cost
                result.total_input_tokens += draft.input_tokens
                result.total_output_tokens += draft.output_tokens
                result.total_cost += draft.cost
                current_implementation = draft.implementation

                # --- Truncation handling ---
                if request.check_truncation and draft.was_truncated:
                    is_api = draft.truncation_source == "api"
                    should_fail = (
                        (is_api and request.fail_on_api_truncation)
                        or (not is_api and request.fail_on_heuristic_truncation)
                    )

                    result.truncation_events.append({
                        "iteration": iteration,
                        "source": draft.truncation_source,
                        "output_tokens": draft.output_tokens,
                    })

                    if should_fail and iteration < max_iterations:
                        logger.warning(
                            "Draft truncated at iteration %d (source: %s, "
                            "%d tokens). Retrying with continuation prompt.",
                            iteration, draft.truncation_source, draft.output_tokens,
                        )
                        review_feedback = _TRUNCATION_CONTINUATION_FEEDBACK
                        continue
                    elif should_fail:
                        logger.warning(
                            "Draft truncated at final iteration %d (source: %s).",
                            iteration, draft.truncation_source,
                        )
                    else:
                        logger.warning(
                            "Draft truncation detected at iteration %d "
                            "(source: %s), continuing anyway.",
                            iteration, draft.truncation_source,
                        )

                # --- Review phase ---
                logger.info(
                    "Engine: reviewing iteration %d/%d",
                    iteration, max_iterations,
                )

                review = review_draft(
                    agent=reviewer_agent,
                    task_description=request.task_description,
                    spec=spec,
                    implementation=current_implementation,
                    pass_threshold=request.pass_threshold,
                    iteration=iteration,
                )
                result.reviews.append(review)
                result.review_cost += review.cost
                result.total_input_tokens += review.input_tokens
                result.total_output_tokens += review.output_tokens
                result.total_cost += review.cost

                logger.info(
                    "Engine: iteration %d — score=%d, passed=%s",
                    iteration, review.score, review.passed,
                )

                if review.passed:
                    result.passed = True
                    break

                review_feedback = format_review_feedback(review)

                if iteration == max_iterations:
                    logger.warning(
                        "Engine: max iterations (%d) reached without passing review",
                        max_iterations,
                    )

            # --- Assemble result ---
            result.iterations_used = len(result.drafts)
            result.final_code = current_implementation
            result.last_raw_response = (
                result.drafts[-1].raw_response if result.drafts else ""
            )

            logger.info(
                "Engine: completed — iterations=%d, passed=%s, cost=$%.4f",
                result.iterations_used, result.passed, result.total_cost,
            )

        except Exception as exc:
            logger.error(
                "Engine: failed (%s) — %s", type(exc).__name__, exc,
                exc_info=True,
            )
            result.error = str(exc)
            result.error_type = type(exc).__name__

        return result

    @staticmethod
    def _resolve_agent(agent_spec: Optional[str]) -> Any:
        """Resolve an agent spec string to an agent instance.

        Args:
            agent_spec: Agent spec (e.g. ``anthropic:claude-sonnet-4-20250514``).

        Returns:
            Agent instance.

        Raises:
            ValueError: If agent_spec is None.
        """
        if not agent_spec:
            raise ValueError("Agent spec must not be None")
        return resolve_agent_spec(agent_spec)
