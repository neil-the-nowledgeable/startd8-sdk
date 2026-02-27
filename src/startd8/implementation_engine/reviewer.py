"""
Reviewer for the implementation engine.

Extracted from ``LeadContractorWorkflow._review_draft`` and
``_format_review_feedback``.
"""

import re
import uuid
from typing import Any, Optional

from ..logging_config import get_logger
from ..costs.pricing import PricingService
from .models import ReviewResult
from .parsers import parse_list_section, parse_score
from .prompts import get_template


__all__ = ["review_draft", "format_review_feedback"]

logger = get_logger(__name__)

_pricing = PricingService()


def review_draft(
    agent: Any,
    task_description: str,
    spec: Any,
    implementation: str,
    pass_threshold: int = 80,
    iteration: int = 1,
) -> ReviewResult:
    """Review a draft implementation.

    Equivalent to ``LeadContractorWorkflow._review_draft()`` (without
    forward manifest validation, which is Prime-specific).

    Args:
        agent: Reviewer agent (must have ``.generate()``).
        task_description: Original task description.
        spec: Spec object with ``.raw_spec`` attribute.
        implementation: Implementation code to review.
        pass_threshold: Minimum score to pass (0-100).
        iteration: Current iteration number.

    Returns:
        ReviewResult with score, pass/fail, and parsed feedback.
    """
    review_id = f"review-{uuid.uuid4().hex[:8]}"

    raw_spec = spec.raw_spec if hasattr(spec, "raw_spec") else str(spec)

    template = get_template("review")
    prompt = template.format(
        task_description=task_description,
        spec=raw_spec,
        implementation=implementation,
        pass_threshold=pass_threshold,
    )

    response_text, response_time_ms, token_usage = agent.generate(prompt)

    review_text = response_text
    score = parse_score(review_text)
    has_pass_verdict = bool(re.search(r'\bPASS\b', review_text, re.IGNORECASE))
    passed = score >= pass_threshold and has_pass_verdict

    issues = parse_list_section(review_text, "Issues")
    blocking = parse_list_section(review_text, "Blocking Issues")
    suggestions = parse_list_section(review_text, "Suggestions")
    strengths = parse_list_section(review_text, "Strengths")

    review = ReviewResult(
        review_id=review_id,
        iteration=iteration,
        passed=passed,
        score=score,
        review_text=review_text,
        issues=issues,
        blocking_issues=blocking,
        suggestions=suggestions,
        strengths=strengths,
        input_tokens=token_usage.input if token_usage else 0,
        output_tokens=token_usage.output if token_usage else 0,
        time_ms=response_time_ms,
    )

    review.cost = _pricing.calculate_total_cost(
        agent.model, review.input_tokens, review.output_tokens
    )

    return review


def format_review_feedback(review: ReviewResult) -> str:
    """Format review into feedback string for the next draft iteration.

    Equivalent to ``LeadContractorWorkflow._format_review_feedback()``.

    Args:
        review: ReviewResult to format.

    Returns:
        Markdown feedback string.
    """
    issues_str = (
        '\n'.join(f'- {issue}' for issue in review.issues)
        if review.issues else '- None listed'
    )
    blocking_str = (
        '\n'.join(f'- {b}' for b in review.blocking_issues)
        if review.blocking_issues else '- None'
    )
    suggestions_str = (
        '\n'.join(f'- {s}' for s in review.suggestions)
        if review.suggestions else '- None listed'
    )

    return f"""## Review Feedback (Score: {review.score}/100)

### Issues to Address:
{issues_str}

### Blocking Issues (MUST FIX):
{blocking_str}

### Suggestions:
{suggestions_str}

### Full Feedback:
{review.review_text}
"""
