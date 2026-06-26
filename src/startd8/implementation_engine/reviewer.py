"""
Reviewer for the implementation engine.

Extracted from ``PrimaryContractorWorkflow._review_draft`` and
``_format_review_feedback``.  Extended with convergent review support
(issue tracking across iterations) and optional pipeline enrichment.
"""

import re
import uuid
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from ..costs.pricing import PricingService
from .budget import ENRICHMENT_BUDGET_CHARS, truncate_with_marker
from .drafter import build_supplementary_sections
from .models import ReviewResult
from .parsers import parse_list_section, parse_score
from .prompts import get_template
from .spec_builder import _fence_untrusted  # FR-A8: shared DATA-not-instructions fence


__all__ = [
    "review_draft",
    "format_review_feedback",
    "build_enrichment_sections",
    "build_prior_issues_section",
    "compute_issue_coverage",
]

logger = get_logger(__name__)

# CR-M3: Lazy initialization — avoids import-time side effects
_pricing: Optional[PricingService] = None


def _get_pricing() -> PricingService:
    """Return the module-level PricingService, creating it lazily."""
    global _pricing
    if _pricing is None:
        _pricing = PricingService()
    return _pricing


# ---------------------------------------------------------------------------
# Enrichment section builder (T2 reviewer budget)
# ---------------------------------------------------------------------------

def build_enrichment_sections(
    context: Optional[Dict[str, Any]] = None,
    *,
    design_document: Optional[str] = None,
    semantic_conventions: Optional[str] = None,
    task_id: str = "",
    budget_chars: int = ENRICHMENT_BUDGET_CHARS,
) -> str:
    """Build optional enrichment sections for the review prompt.

    Calls ``build_supplementary_sections`` for shared context (manifest,
    call graph, parameters), then appends reviewer-specific sections
    (design document, semantic conventions).

    Args:
        context: Pipeline context dict (forwarded to ``build_supplementary_sections``).
        design_document: Design doc for compliance checking.
        semantic_conventions: Naming convention rules.
        task_id: Current task ID for FLCM constraint injection.
        budget_chars: Character budget for all enrichment sections.

    Returns:
        Formatted enrichment sections string.
    """
    parts: List[str] = []

    # Shared sections (manifest, call graph, parameters) — half the budget
    if context:
        shared = build_supplementary_sections(
            context, task_id=task_id, budget_chars=budget_chars // 2,
        )
        if shared:
            parts.append(shared)

    # Design document — primary review input, separate budget. Untrusted-derived
    # (built from requirements/plan), so fence as data (FR-A8).
    if design_document:
        design_budget = min(budget_chars, 8000)
        truncated = truncate_with_marker(design_document, design_budget)
        fenced_design = _fence_untrusted(truncated, "design_document")
        parts.append(f"## Design Document (compliance reference)\n{fenced_design}")

    # Semantic conventions — untrusted-derived → fence as data (FR-A8).
    if semantic_conventions:
        fenced_conv = _fence_untrusted(str(semantic_conventions)[:2000], "semantic_conventions")
        parts.append(f"## Semantic Conventions\n{fenced_conv}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Issue coverage computation (hint for reviewer, not a gate)
# ---------------------------------------------------------------------------

def compute_issue_coverage(
    prior_review: "ReviewResult",
    current_review_text: str = "",
) -> Dict[str, List[Dict[str, str]]]:
    """Compute which prior issues appear addressed vs still outstanding.

    Uses simple heuristics: if key terms from a prior issue are absent
    from the current review text, mark as addressed.  This is a best-effort
    hint — the reviewer will verify.

    Args:
        prior_review: ReviewResult from the previous iteration.
        current_review_text: Current review's raw text (empty before review runs).

    Returns:
        ``{"addressed": [...], "outstanding": [...]}`` where each item
        has ``label``, ``text``, and ``severity`` keys.
    """
    addressed: List[Dict[str, str]] = []
    outstanding: List[Dict[str, str]] = []
    lower_text = current_review_text.lower()

    # Label blocking issues as B1, B2, ... and other issues as I1, I2, ...
    for idx, issue in enumerate(prior_review.blocking_issues or [], 1):
        label = f"B{idx}"
        entry = {"label": label, "text": issue, "severity": "BLOCKING"}
        # If review text mentions the issue as resolved, mark addressed
        key_words = _extract_key_terms(issue)
        if current_review_text and not any(
            kw in lower_text for kw in key_words
        ):
            addressed.append(entry)
        else:
            outstanding.append(entry)

    for idx, issue in enumerate(prior_review.issues or [], 1):
        label = f"I{idx}"
        entry = {"label": label, "text": issue, "severity": "MAJOR"}
        key_words = _extract_key_terms(issue)
        if current_review_text and not any(
            kw in lower_text for kw in key_words
        ):
            addressed.append(entry)
        else:
            outstanding.append(entry)

    return {"addressed": addressed, "outstanding": outstanding}


def _extract_key_terms(issue_text: str) -> List[str]:
    """Extract 2-3 distinctive 4+ char words from an issue for matching.

    Args:
        issue_text: Issue description string.

    Returns:
        Up to 3 lowercase key terms, excluding common stopwords.
    """
    words = re.findall(r'\b\w{4,}\b', str(issue_text).lower())
    # Take up to 3 distinctive words (skip common words)
    skip = {"that", "this", "with", "from", "should", "must", "have", "been",
            "does", "will", "need", "also", "some", "more", "very", "code"}
    terms = [w for w in words if w not in skip][:3]
    return terms


# ---------------------------------------------------------------------------
# Prior issues section builder (convergent review pattern)
# ---------------------------------------------------------------------------

def build_prior_issues_section(
    prior_review: Optional["ReviewResult"] = None,
    iteration: int = 1,
    max_iterations: int = 3,
) -> str:
    """Format prior review issues into a structured section for the reviewer.

    Produces "Issues Substantially Addressed" and "Issues Still Outstanding"
    sections modeled on the architectural review's convergent review pattern.

    Args:
        prior_review: ReviewResult from previous iteration (None on first iteration).
        iteration: Current iteration number.
        max_iterations: Maximum iterations configured.

    Returns:
        Formatted prior issues section, or empty string on first iteration.
    """
    if not prior_review or iteration <= 1:
        return ""

    has_blocking = bool(prior_review.blocking_issues)
    has_issues = bool(prior_review.issues)
    if not has_blocking and not has_issues:
        return ""

    parts = [f"## Issue Resolution Status (iteration {iteration} of {max_iterations})"]

    # List all prior issues with labels for reference
    if has_blocking:
        parts.append(
            "\n### Prior Blocking Issues (MUST verify resolution)"
        )
        for idx, issue in enumerate(prior_review.blocking_issues, 1):
            parts.append(f"- [B{idx}] {issue}")

    if has_issues:
        parts.append("\n### Prior Issues")
        for idx, issue in enumerate(prior_review.issues, 1):
            parts.append(f"- [I{idx}] {issue}")

    parts.append(
        "\nFor each prior issue, explicitly state whether it is "
        "RESOLVED or STILL OUTSTANDING. Do NOT re-raise issues that have "
        "been properly addressed unless the fix introduced a regression."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Convergence instructions builder
# ---------------------------------------------------------------------------

def _build_convergence_instructions(
    iteration: int,
    pass_threshold: int,
    has_prior_review: bool,
) -> str:
    """Build convergence instructions for the review prompt.

    Returns empty string on first iteration (no convergence context).
    """
    if iteration <= 1 or not has_prior_review:
        return ""

    return (
        f"\n## Convergence Criteria\n"
        f"This is iteration {iteration} of a convergent review loop.\n"
        f"- PASS when: score >= {pass_threshold} AND all blocking issues "
        f"from prior reviews are resolved AND no new blocking issues.\n"
        f"- FAIL when: any blocking issue remains unresolved OR new "
        f"blocking issues are found.\n"
        f"- In your Issues section, explicitly reference prior issues by "
        f"label (e.g., \"[B1] RESOLVED\" or \"[B1] STILL OUTSTANDING\").\n"
        f"- Do NOT penalize the score for issues marked \"ADDRESSED\" "
        f"above unless the fix introduced a regression."
    )


# ---------------------------------------------------------------------------
# FLCM contract validation (optional)
# ---------------------------------------------------------------------------

def _validate_against_manifest(
    forward_manifest: Any,
    implementation: str,
    target_files: Optional[List[str]] = None,
    task_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Run post-generation contract validation against the ForwardManifest.

    Thin adapter over the single canonical enforcement path,
    :meth:`ForwardManifest.validate_implementation` (FR-3) — the drafter is shown this
    manifest's contracts at draft time (``spec_builder``), and this method enforces the
    same manifest at review time, so producer and consumer cannot drift. (Historically
    ``validate_implementation`` was *referenced* here but never existed; the ``getattr``
    returned ``None`` and enforcement was dormant. It is now real and validates **multiple
    Python files** plus task-scoped interface **contracts**, not just single-file element
    specs.)

    Maps the returned ``ContractViolation`` objects to the dict shape the review consumes.
    Degrades gracefully to ``[]`` on any error (missing method, import failure, parse error).
    """
    try:
        validate = getattr(forward_manifest, "validate_implementation", None)
        if not callable(validate):
            return []
        violations = validate(
            implementation,
            target_files=target_files,
            task_id=task_id,
            include_contracts=task_id is not None,
        )
        return [
            {
                "severity": getattr(v, "severity", "warning"),
                "violation_type": getattr(v, "violation_type", "unknown"),
                "contract_id": getattr(v, "contract_id", ""),
                "expected": getattr(v, "expected", ""),
                "actual": getattr(v, "actual", "") or "",
            }
            for v in (violations or [])
        ]
    except (ImportError, ModuleNotFoundError) as exc:
        logger.debug(
            "FLCM contract validation not available: %s", exc,
        )
        return []
    except Exception as exc:
        logger.debug(
            "FLCM contract validation failed (%s): %s",
            type(exc).__name__, exc, exc_info=True,
        )
        return []


# ---------------------------------------------------------------------------
# CR-C2: Spec constraint verification section
# ---------------------------------------------------------------------------

def _build_constraint_verification_section(
    spec_constraints: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Build a constraint verification checklist for the review prompt.

    Formats machine-readable MUST/MUST_NOT constraints extracted from the
    spec into a numbered checklist the reviewer must verify against the
    implementation.

    Args:
        spec_constraints: List of constraint dicts with ``type``, ``text``,
            and ``source`` keys (from ``extract_spec_constraints()``).

    Returns:
        Formatted constraint verification section, or empty string if no
        constraints are available.
    """
    if not spec_constraints:
        return ""

    lines = [
        "## Constraint Verification Checklist",
        "",
        "The spec defined the following constraints. For EACH constraint, "
        "verify whether the implementation satisfies it and report any "
        "violations as BLOCKING issues.",
        "",
    ]
    for i, c in enumerate(spec_constraints, 1):
        ctype = c.get("type", "MUST")
        text = c.get("text", "")
        lines.append(f"{i}. **[{ctype}]** {text}")

    lines.append("")
    lines.append(
        "For each constraint, state SATISFIED or VIOLATED. "
        "Any VIOLATED constraint is a BLOCKING issue."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Review system prompt loader
# ---------------------------------------------------------------------------

def _get_review_system_prompt() -> str:
    """Load the review system prompt from YAML (or fallback)."""
    try:
        return get_template("review_system")
    except KeyError:
        return ""


# Language-specific review rules injected into the system prompt.
# These override reference implementation patterns that the reviewer
# would otherwise accept as correct.
_LANGUAGE_REVIEW_RULES: Dict[str, str] = {
    "csharp": (
        "## C# Quality Rules (enforce as MAJOR issues)\n"
        "- Console.Write/Console.WriteLine in service classes: MAJOR. "
        "Use ILogger<T> injected via constructor DI instead. "
        "Even if the spec explicitly uses Console.WriteLine, the coding standard "
        "takes precedence — flag as MAJOR (not BLOCKING) and quote the conflicting "
        "spec instruction so it can be corrected.\n"
        "- String interpolation in SQL queries ($\"SELECT ... '{var}'\"): BLOCKING (security). "
        "Use parameterized queries (cmd.Parameters.AddWithValue). "
        "This is a security violation (CWE-89) — spec CANNOT override this.\n"
        "- Block-scoped namespace (namespace X { }): MINOR for net8.0+ targets. "
        "Prefer file-scoped (namespace X;).\n"
        "- Missing ILogger<T> constructor injection in any service class: MAJOR.\n"
        "- Bare `catch { return false; }` without logging: MINOR.\n"
        "- .csproj MUST include `<Nullable>enable</Nullable>` in PropertyGroup: MAJOR. "
        "Modern C# projects require nullable reference type analysis.\n"
        "- IDisposable resources stored as fields MUST be disposed: "
        "implement IAsyncDisposable on the owning class.\n"
        "- Interface files (IFoo.cs) MUST contain ONLY the interface definition: MAJOR. "
        "Never put class implementations in an interface file."
    ),
    "go": (
        "## Go Quality Rules\n"
        "- fmt.Println/fmt.Printf in service code: MAJOR. "
        "Use slog or zap structured logger instead. "
        "Even if spec uses fmt.Println, coding standard takes precedence.\n"
        "- String formatting in SQL queries (fmt.Sprintf with %s/%v): BLOCKING (security, CWE-89). "
        "Use parameterized queries. Spec CANNOT override this.\n"
        "- Empty function bodies with only a TODO comment: MAJOR."
    ),
    "java": (
        "## Java Quality Rules\n"
        "- System.out.println in service code: MAJOR. "
        "Use SLF4J LoggerFactory instead. "
        "Even if spec uses System.out.println, coding standard takes precedence.\n"
        "- String concatenation in SQL queries: BLOCKING (security, CWE-89). "
        "Use PreparedStatement with ? placeholders. Spec CANNOT override this.\n"
        "- Empty catch blocks: MAJOR."
    ),
    "python": (
        "## Python Quality Rules\n"
        "- print() in service/library code: MAJOR. "
        "Use logging.getLogger(__name__) instead. "
        "Even if spec uses print(), coding standard takes precedence.\n"
        "- f-string in SQL queries: BLOCKING (security, CWE-89). "
        "Use parameterized queries (cursor.execute(sql, params)). "
        "Spec CANNOT override this.\n"
        "- Bare except: MAJOR. Catch specific exceptions."
    ),
}


def _build_language_review_rules(context: Optional[Dict[str, Any]]) -> str:
    """Build language-specific review rules from the pipeline context.

    Extracts the language_id from the context's language_profile and
    returns the corresponding review rules. Returns empty string if
    no language profile or no rules for the detected language.
    """
    if not context:
        return ""

    # Try language_profile object first
    lang_profile = context.get("language_profile")
    lang_id = ""
    if lang_profile and hasattr(lang_profile, "language_id"):
        lang_id = lang_profile.language_id
    elif isinstance(lang_profile, str):
        lang_id = lang_profile

    if not lang_id:
        # Fallback: infer from target files
        target_files = context.get("target_files", [])
        target_file = context.get("target_file", "")
        all_files = target_files + ([target_file] if target_file else [])
        for f in all_files:
            fl = f.lower()
            if fl.endswith(".cs") or fl.endswith(".csproj"):
                lang_id = "csharp"
                break
            elif fl.endswith(".go"):
                lang_id = "go"
                break
            elif fl.endswith(".java"):
                lang_id = "java"
                break
            elif fl.endswith(".py"):
                lang_id = "python"
                break

    return _LANGUAGE_REVIEW_RULES.get(lang_id, "")


# ---------------------------------------------------------------------------
# Main review entry point
# ---------------------------------------------------------------------------

def review_draft(
    agent: Any,
    task_description: str,
    spec: Any,
    implementation: str,
    pass_threshold: int = 80,
    iteration: int = 1,
    *,
    # Optional enrichment context
    design_document: Optional[str] = None,
    parameter_sources: Any = None,
    semantic_conventions: Optional[str] = None,
    # Phase 4/5/6 manifest context
    manifest_context: Optional[str] = None,
    call_graph_context: Optional[str] = None,
    call_graph_callers: Optional[List[Dict[str, Any]]] = None,
    # Convergent review context
    prior_review: Optional["ReviewResult"] = None,
    max_iterations: int = 3,
    # FLCM contract validation
    forward_manifest: Any = None,
    target_files: Optional[List[str]] = None,
    # Task id scopes interface-contract validation (FR-3); None -> file_specs only.
    task_id: Optional[str] = None,
    # Full context dict (for supplementary sections)
    context: Optional[Dict[str, Any]] = None,
    # CR-C2: Machine-readable constraints from spec for enforcement
    spec_constraints: Optional[List[Dict[str, str]]] = None,
) -> ReviewResult:
    """Review a draft implementation.

    Extended from ``PrimaryContractorWorkflow._review_draft()`` with:
    - Optional pipeline enrichment (design doc, parameters, conventions)
    - Manifest/call graph context (Phase 4/5/6)
    - Convergent review (prior issue tracking across iterations)
    - FLCM contract validation (post-generation)

    All new parameters are optional with None defaults for backward
    compatibility.

    Args:
        agent: Reviewer agent (must have ``.generate()``).
        task_description: Original task description.
        spec: Spec object with ``.raw_spec`` attribute.
        implementation: Implementation code to review.
        pass_threshold: Minimum score to pass (0-100).
        iteration: Current iteration number.
        design_document: Design doc for compliance checking.
        parameter_sources: Parameter provenance data.
        semantic_conventions: Naming convention rules.
        manifest_context: Phase 4/5 structural element summaries.
        call_graph_context: Phase 6 call graph impact.
        call_graph_callers: Phase 6 caller backward-compat data.
        prior_review: ReviewResult from previous iteration.
        max_iterations: Maximum iterations configured.
        forward_manifest: ForwardManifest object for post-gen validation.
        target_files: File list for multi-file validation.
        context: Full pipeline context dict for supplementary sections.

    Returns:
        ReviewResult with score, pass/fail, and parsed feedback.
    """
    review_id = f"review-{uuid.uuid4().hex[:8]}"
    logger.debug("Reviewer: starting review %s (iteration %d)", review_id, iteration)

    if hasattr(spec, "raw_spec"):
        raw_spec = spec.raw_spec
    else:
        logger.debug("Reviewer: spec lacks raw_spec attribute, using str(spec)")
        raw_spec = str(spec)

    # Build enrichment sections from kwargs and/or context
    enrichment_ctx = dict(context or {})
    # Overlay explicit kwargs onto context (kwargs take precedence)
    for _key, _val in (
        ("manifest_context", manifest_context),
        ("call_graph_context", call_graph_context),
        ("call_graph_callers", call_graph_callers),
        ("parameter_sources", parameter_sources),
    ):
        if _val is not None:
            enrichment_ctx[_key] = _val

    enrichment = build_enrichment_sections(
        context=enrichment_ctx if enrichment_ctx else None,
        design_document=design_document,
        semantic_conventions=semantic_conventions,
    )

    # Build prior issues section (convergent review)
    prior_issues = build_prior_issues_section(
        prior_review=prior_review,
        iteration=iteration,
        max_iterations=max_iterations,
    )

    # Build convergence instructions
    convergence = _build_convergence_instructions(
        iteration=iteration,
        pass_threshold=pass_threshold,
        has_prior_review=prior_review is not None,
    )

    # CR-C2: Build constraint verification checklist from spec constraints.
    # Also try to extract constraints from the spec object itself if the
    # caller didn't pass them explicitly.
    effective_constraints = spec_constraints
    if not effective_constraints:
        fallback = getattr(spec, "spec_constraints", None)
        if isinstance(fallback, list):
            effective_constraints = fallback
    constraint_section = _build_constraint_verification_section(effective_constraints)

    template = get_template("review")
    prompt = template.format(
        task_description=task_description,
        spec=raw_spec,
        implementation=implementation,
        pass_threshold=pass_threshold,
        enrichment_sections=enrichment,
        prior_issues_section=prior_issues,
        convergence_instructions=convergence,
    )

    # Append constraint verification section after the main prompt.
    # This is appended rather than templated to avoid breaking existing
    # YAML templates that don't have a {constraint_section} placeholder.
    if constraint_section:
        prompt = prompt + "\n\n" + constraint_section

    sys_prompt = _get_review_system_prompt()

    # REQ-KZ-CS-500c: Inject language-specific review criteria into system prompt.
    # The language profile's coding_standards contain rules like "use ILogger<T>
    # instead of Console.WriteLine" that the reviewer should enforce as MAJOR issues.
    _lang_review_rules = _build_language_review_rules(context)
    if _lang_review_rules:
        sys_prompt = (sys_prompt + "\n\n" + _lang_review_rules) if sys_prompt else _lang_review_rules

    if sys_prompt:
        response_text, response_time_ms, token_usage = agent.generate(
            prompt, system_prompt=sys_prompt,
        )
    else:
        response_text, response_time_ms, token_usage = agent.generate(prompt)

    review_text = response_text
    score = parse_score(review_text)
    has_pass_verdict = bool(re.search(r'\bPASS\b', review_text, re.IGNORECASE))

    issues = parse_list_section(review_text, "Issues")
    blocking = parse_list_section(review_text, "Blocking Issues")
    suggestions = parse_list_section(review_text, "Suggestions")
    strengths = parse_list_section(review_text, "Strengths")

    # A review cannot be "PASS" while it still lists unresolved blocking
    # issues — that is the "PASS on a non-working feature" trap. A high score
    # plus the word PASS is not enough if the reviewer itself flagged blockers.
    # Filter placeholder entries ("None"/"N/A") so an explicitly-empty section
    # doesn't false-fail.
    real_blocking = [
        b for b in blocking
        if b.strip().lower().rstrip(".") not in ("none", "n/a", "na", "")
    ]
    passed = score >= pass_threshold and has_pass_verdict and not real_blocking

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

    review.cost = _get_pricing().calculate_total_cost(
        getattr(agent, "model", "unknown"),
        review.input_tokens,
        review.output_tokens,
    )

    # FLCM contract validation (post-generation, optional)
    if forward_manifest:
        violations = _validate_against_manifest(
            forward_manifest, implementation, target_files, task_id,
        )
        error_violations = [
            v for v in violations
            if v.get("severity") == "error"
        ]
        if error_violations:
            review.passed = False
            for viol in error_violations:
                msg = (
                    f"[BLOCKING] {viol['violation_type']} "
                    f"({viol['contract_id']}): "
                    f"Expected {viol['expected']}"
                )
                if viol.get("actual"):
                    msg += f", got {viol['actual']}"
                if msg not in review.blocking_issues:
                    review.blocking_issues.append(msg)

    return review


# ---------------------------------------------------------------------------
# Convergence-aware review feedback formatter
# ---------------------------------------------------------------------------

def format_review_feedback(
    review: ReviewResult,
    prior_review: Optional[ReviewResult] = None,
) -> str:
    """Format review into feedback string for the next draft iteration.

    Without ``prior_review``: backward-compatible flat format.
    With ``prior_review``: convergence-focused format showing resolved
    vs outstanding issues so the drafter addresses specific gaps.

    Args:
        review: Current ReviewResult to format.
        prior_review: ReviewResult from the previous iteration (optional).

    Returns:
        Markdown feedback string.
    """
    if prior_review is None:
        # Backward-compatible flat format (iteration 1)
        return _format_flat_feedback(review)

    # Convergence-aware format (iteration 2+)
    return _format_convergence_feedback(review, prior_review)


def _format_flat_feedback(review: ReviewResult) -> str:
    """Format review as flat markdown feedback (iteration 1 format).

    Args:
        review: Current ReviewResult to format.

    Returns:
        Markdown feedback string with issues, blocking issues, and suggestions.
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


def _format_convergence_feedback(
    review: ReviewResult,
    prior_review: ReviewResult,
) -> str:
    """Format review as convergence-focused feedback (iteration 2+ format).

    Shows resolved vs outstanding issues from the prior review so the drafter
    addresses specific gaps rather than re-reading the full review.

    Args:
        review: Current ReviewResult.
        prior_review: ReviewResult from the previous iteration.

    Returns:
        Markdown feedback with convergence status, blocking/outstanding/new/resolved sections.
    """
    # Compute resolution status using current review text as evidence
    coverage = compute_issue_coverage(prior_review, review.review_text)
    prior_blocking_count = len(prior_review.blocking_issues)
    prior_issue_count = len(prior_review.issues)
    current_blocking_count = len(review.blocking_issues)
    current_issue_count = len(review.issues)

    resolved_blocking = [
        e for e in coverage["addressed"] if e["severity"] == "BLOCKING"
    ]
    resolved_issues = [
        e for e in coverage["addressed"] if e["severity"] != "BLOCKING"
    ]
    outstanding = coverage["outstanding"]

    parts = [
        f"## Review Feedback — Convergent Review (Score: {review.score}/100)",
        "",
        "### Convergence Status",
        f"- Prior blocking issues: {prior_blocking_count} → "
        f"Current: {current_blocking_count}",
        f"- Prior other issues: {prior_issue_count} → "
        f"Current: {current_issue_count}",
    ]

    # Blocking issues — MUST fix for convergence
    if review.blocking_issues:
        parts.append("")
        parts.append("### BLOCKING — Must Fix for Convergence")
        for issue in review.blocking_issues:
            parts.append(f"- {issue}")

    # Outstanding from prior review
    outstanding_blocking = [
        e for e in outstanding if e["severity"] == "BLOCKING"
    ]
    if outstanding_blocking:
        parts.append("")
        parts.append("### Still Outstanding from Prior Review")
        for entry in outstanding_blocking:
            parts.append(
                f"- [{entry['label']}] {entry['text']} (STILL OUTSTANDING)"
            )

    # New issues this iteration
    addressed_texts = {e["text"] for e in coverage.get("addressed", [])}
    new_issues = [
        iss for iss in review.issues
        if iss not in addressed_texts
    ]
    if new_issues:
        parts.append("")
        parts.append("### New Issues This Iteration")
        for issue in new_issues:
            parts.append(f"- {issue}")

    # Resolved since prior review
    if resolved_blocking or resolved_issues:
        parts.append("")
        parts.append("### Resolved Since Prior Review (no action needed)")
        for entry in resolved_blocking:
            parts.append(f"- [{entry['label']}] {entry['text']} — RESOLVED")
        for entry in resolved_issues:
            parts.append(f"- [{entry['label']}] {entry['text']} — RESOLVED")

    # Full feedback
    parts.append("")
    parts.append("### Full Feedback:")
    parts.append(review.review_text)

    return "\n".join(parts)
