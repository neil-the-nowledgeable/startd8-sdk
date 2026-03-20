"""P1 security guidance injection — SP-INJ-020 through SP-INJ-022.

Sources safe/unsafe pattern examples from ``query_prime.patterns.DatabasePatternRegistry``
and formats them as a prompt section for ``enforce_prompt_budget()`` at P1 priority.
"""

from __future__ import annotations

from typing import Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


def inject_p1_guidance(
    database: str,
    language: str,
) -> Optional[str]:
    """Build P1 security guidance section from the pattern registry.

    Loads safe/unsafe patterns from ``DatabasePatternRegistry`` and formats
    them as a human-readable prompt section with CWE reference.

    Args:
        database: Database type string (e.g. "postgresql", "spanner").
        language: Language identifier (e.g. "csharp", "python").

    Returns:
        Formatted guidance string, or None if no pattern registered for
        the (database, language) pair.
    """
    try:
        from startd8.query_prime.patterns import DatabasePatternRegistry
    except ImportError:
        return None

    pattern = DatabasePatternRegistry.get(database, language)
    if pattern is None:
        return None

    parts = [
        f"## Security Guidance — {pattern.client_library} ({database}/{language})\n",
    ]

    # Safe patterns: concrete API examples
    if pattern.safe_param_syntax:
        parts.append("**Secure patterns (USE THESE):**")
        for example in pattern.safe_param_syntax:
            parts.append(f"  - `{example}`")
        parts.append("")

    # Unsafe patterns: what to avoid
    parts.append(
        "**Insecure patterns (DO NOT USE):**\n"
        "  - String interpolation in SQL (`$\"...{var}...\"`)\n"
        "  - String concatenation (`\"SELECT...\" + variable`)\n"
        "  - String.Format / fmt.Sprintf with SQL keywords"
    )

    # Credential handling
    if pattern.credential_variable_names:
        cred_names = ", ".join(f"`{n}`" for n in pattern.credential_variable_names[:5])
        parts.append(
            f"\n**Credential safety:** Never log or print: {cred_names}. "
            f"Use redacted placeholders in diagnostic output."
        )

    # Lifecycle
    if pattern.dispose_patterns:
        parts.append(
            "\n**Resource lifecycle:** Use proper disposal patterns "
            "(`using`/`with`/`defer`/try-with-resources). "
            "Never create connections inside per-request methods without disposing."
        )

    parts.append("\n*CWE-89: SQL Injection. CWE-798: Hardcoded Credentials.*")

    guidance = "\n".join(parts)
    logger.info(
        "P1 security guidance injected for %s/%s (%d chars)",
        database, language, len(guidance),
    )
    return guidance
