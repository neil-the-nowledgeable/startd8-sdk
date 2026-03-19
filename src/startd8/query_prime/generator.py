"""LLM-backed query generation with security constraints — REQ-QP-500.

Generates parameterized query code via LLM with database-specific safe
pattern examples baked into the system prompt. Every LLM output passes
through verify_file() — injection or credential leakage findings cause
rejection and retry/escalation.
"""

from __future__ import annotations

from typing import Any

from startd8.logging_config import get_logger

from .models import (
    QueryWorkItem,
    SecurityVerificationResult,
)
from .patterns import DatabasePatternRegistry
from .security import verify_file

logger = get_logger(__name__)


def _build_system_prompt(work_item: QueryWorkItem) -> str:
    """Build a security-constrained system prompt for query generation.

    Injects database-specific safe pattern examples from the pattern
    registry so the LLM knows exactly which parameterization syntax to use.
    """
    db_pattern = DatabasePatternRegistry.get(
        work_item.database, work_item.target_language,
    )

    safe_examples = ""
    if db_pattern and db_pattern.safe_param_syntax:
        examples = "\n".join(f"  - {ex}" for ex in db_pattern.safe_param_syntax)
        safe_examples = (
            f"\n\nSafe parameterization patterns for "
            f"{work_item.database.value}/{work_item.target_language}:\n{examples}"
        )

    credential_warning = ""
    if db_pattern and db_pattern.credential_variable_names:
        cred_names = ", ".join(db_pattern.credential_variable_names[:5])
        credential_warning = (
            f"\n\nNEVER log or print these credential-bearing variables: {cred_names}. "
            f"Use redacted placeholders in any diagnostic output."
        )

    lifecycle_hint = ""
    if db_pattern and db_pattern.dispose_patterns:
        lifecycle_hint = (
            "\n\nAlways use proper resource lifecycle management "
            "(using/with/defer/try-with-resources). Never create database "
            "connections or data sources inside per-request methods without "
            "disposing them."
        )

    return (
        f"You are a database query code generator specializing in secure, "
        f"parameterized queries for {work_item.database.value} databases "
        f"in {work_item.target_language}.\n\n"
        f"MANDATORY SECURITY RULES:\n"
        f"1. ALWAYS use parameterized queries for ALL external inputs.\n"
        f"2. NEVER use string interpolation, concatenation, or format strings "
        f"to build SQL/query strings with user-supplied values.\n"
        f"3. NEVER log connection strings, passwords, API keys, or secrets.\n"
        f"4. Use proper resource lifecycle management (connection pooling, dispose)."
        f"{safe_examples}"
        f"{credential_warning}"
        f"{lifecycle_hint}\n\n"
        f"Return ONLY the code — no explanations, no markdown fences."
    )


def _build_user_prompt(work_item: QueryWorkItem) -> str:
    """Build the user prompt describing what to generate."""
    parts = [
        f"Generate a {work_item.operation_type.value} implementation "
        f"for {work_item.database.value} in {work_item.target_language}.",
        f"\nDescription: {work_item.description}",
    ]

    if work_item.tables:
        parts.append(f"\nTables: {', '.join(work_item.tables)}")

    if work_item.parameters:
        param_list = ", ".join(
            f"{p.name} ({p.param_type}, source: {p.source})"
            for p in work_item.parameters
        )
        parts.append(f"\nParameters: {param_list}")

    if work_item.joins:
        join_list = ", ".join(
            f"{j.left_table} {j.join_type} JOIN {j.right_table} ON {j.on_clause}"
            for j in work_item.joins
        )
        parts.append(f"\nJoins: {join_list}")

    if work_item.transaction_boundary.value != "none":
        parts.append(
            f"\nTransaction boundary: {work_item.transaction_boundary.value}"
        )

    if work_item.containing_function:
        parts.append(
            f"\nContaining function/method: {work_item.containing_function}"
        )

    if work_item.target_framework:
        parts.append(f"\nFramework: {work_item.target_framework}")

    return "\n".join(parts)


def generate_query(
    work_item: QueryWorkItem,
    agent: Any,
) -> tuple[str, SecurityVerificationResult, float]:
    """Generate query code via LLM with security verification.

    Args:
        work_item: The query work item to generate code for.
        agent: A BaseAgent instance (must have .generate()).

    Returns:
        Tuple of (code, verification_result, cost_usd).

    Raises:
        SecurityError: If generated code fails security verification
            after all retries.
    """
    system_prompt = _build_system_prompt(work_item)
    user_prompt = _build_user_prompt(work_item)

    result = agent.generate(user_prompt, system_prompt=system_prompt)
    code = result.text.strip()
    cost_usd = 0.0

    # Extract cost from token usage
    if result.token_usage:
        usage = result.token_usage
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
            output_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
        else:
            input_tokens = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0)
            output_tokens = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0)
        # Rough cost estimate (Haiku-tier pricing)
        cost_usd = (input_tokens * 0.25 + output_tokens * 1.25) / 1_000_000

    # Strip markdown fences if present
    code = _strip_code_fences(code)

    # Verify security
    verification = verify_file(
        code,
        work_item.file_path or f"<generated:{work_item.id}>",
        work_item.database,
        work_item.target_language,
    )

    logger.info(
        "QueryPrime LLM generation: work_item=%s verdict=%s cost=$%.6f",
        work_item.id, verification.verdict.value, cost_usd,
    )

    return code, verification, cost_usd


def _strip_code_fences(code: str) -> str:
    """Strip markdown code fences from LLM output."""
    lines = code.splitlines()
    if not lines:
        return code

    # Strip opening fence
    if lines[0].startswith("```"):
        lines = lines[1:]

    # Strip closing fence
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines)
