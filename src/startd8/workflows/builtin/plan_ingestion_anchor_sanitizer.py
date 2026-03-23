"""Acceptance anchor sanitization for Query-Informed Plan Ingestion (REQ-QPI-200–203).

Validates acceptance anchors and task descriptions against Query Prime's
``DatabasePatternRegistry`` to detect and replace anti-pattern SQL construction
directives (e.g., "All SQL uses string interpolation") with safe equivalents
(e.g., "All SQL uses parameterized queries").

All detection is regex-based — no LLM calls.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Detection patterns — SQL anti-pattern anchors
# ---------------------------------------------------------------------------

# SQL keywords that indicate a database context
_SQL_KW_RE = re.compile(
    r"\b(?:SQL|SELECT|INSERT|UPDATE|DELETE|UPSERT|query|queries)\b",
    re.IGNORECASE,
)

# Unsafe construction keywords
_UNSAFE_CONSTRUCTION_RE = re.compile(
    r"\b(?:string\s+interpolat|interpolat\w+|concatenat\w+|String\.Format|"
    r'\$"|f"|f\'|format\s*\()\b',
    re.IGNORECASE,
)

# Explicit "no parameterized" / "not parameterized" directives
_NO_PARAM_RE = re.compile(
    r"\b(?:no|not|don'?t|without)\s+(?:use\s+)?parameteriz",
    re.IGNORECASE,
)

# "intentional" + SQL/injection context (either order)
_INTENTIONAL_INJECTION_RE = re.compile(
    r"(?:"
    r"\b(?:intentional|deliberate|by\s+design|accepted\s+risk)\b.*\b(?:SQL|inject|interpolat|vulnerab)\b"
    r"|"
    r"\b(?:SQL|inject|interpolat|vulnerab)\b.*\b(?:intentional|deliberate|by\s+design|accepted\s+risk)\b"
    r")",
    re.IGNORECASE,
)

# "reference match" + SQL context
_REFERENCE_MATCH_SQL_RE = re.compile(
    r"\b(?:reference|match\w*\s+reference|structural\s+equivalence)\b.*"
    r"\b(?:SQL|interpolat|string)\b",
    re.IGNORECASE,
)

# Negative scope patterns to strip — covers multiple phrasings:
# "No parameterized queries"
# "Parameterized queries not used"
# "Parameterized queries (intentionally uses string interpolation...)"
# "Don't use parameterized queries"
_NEG_SCOPE_CONFLICT_RE = re.compile(
    r"(?:"
    r"\b(?:no|not|don'?t|without)\s+(?:use\s+)?parameteriz"
    r"|"
    r"\bparameteriz\w+\s+(?:queries?\s+)?(?:intentionally\s+)?not\s+used"
    r"|"
    r"\bparameteriz\w+\s+(?:queries?\s+)?\(.*(?:interpolat|inject|vulnerab)"
    r"|"
    r"\bintentionally\s+(?:uses?\s+)?(?:string\s+)?interpolat"
    r")",
    re.IGNORECASE,
)


# Fallback safe syntax examples per language — used when DatabasePatternRegistry
# is unavailable (R1: module-level constant, not rebuilt per call).
_SAFE_SYNTAX_FALLBACKS: dict[str, str] = {
    "csharp": 'cmd.Parameters.AddWithValue("@param", value)',
    "python": 'cursor.execute("SELECT ... WHERE id = %s", (value,))',
    "nodejs": 'client.query("SELECT ... WHERE id = $1", [value])',
    "go": 'spanner.Statement{SQL: "... @param", Params: map}',
    "java": 'PreparedStatement with ? placeholders',
}

# R2: Regexes used in sanitize_task_description — compiled at module level.
_INTERP_SQL_RE = re.compile(
    r"(?:string[- ]interpolat\w+\s+SQL|"
    r"SQL\s+(?:using\s+)?string[- ]interpolat\w+|"
    r"Uses\s+string[- ]interpolat\w+\s+SQL\b[^.]*)",
    re.IGNORECASE,
)
_REF_MATCH_RE = re.compile(
    r"matching\s+reference\s+implementation",
    re.IGNORECASE,
)


def _get_safe_syntax(detected_database: str, language: str) -> str:
    """Look up safe parameterization syntax from DatabasePatternRegistry.

    Args:
        detected_database: Database identifier (e.g., ``"postgresql"``, ``"spanner"``).
        language: Language identifier (e.g., ``"csharp"``, ``"python"``).

    Returns:
        A human-readable safe parameterization example string.
        Falls back to a generic example if the registry is unavailable.
    """
    try:
        from startd8.query_prime.patterns import DatabasePatternRegistry
        pattern = DatabasePatternRegistry.get(detected_database, language)
        if pattern and pattern.safe_param_syntax:
            return pattern.safe_param_syntax[0]
    except (ImportError, AttributeError) as exc:
        logger.debug("DatabasePatternRegistry unavailable: %s", exc)
    return _SAFE_SYNTAX_FALLBACKS.get(language, "parameterized query syntax")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_acceptance_anchor(
    anchor: str,
    detected_database: str = "",
    language: str = "",
) -> Dict[str, Any]:
    """Classify an acceptance anchor as safe or anti-pattern.

    Args:
        anchor: A single acceptance obligation string from the seed.
        detected_database: Database identifier for safe-syntax lookup
            (e.g., ``"postgresql"``). Empty if unknown.
        language: Target language for safe-syntax lookup (e.g., ``"csharp"``).

    Returns:
        ``{"classified": "safe"}`` or
        ``{"classified": "anti_pattern", "reason": "...", "safe_replacement": "..."}``
    """
    # Rule 1: SQL keyword + unsafe construction
    if _SQL_KW_RE.search(anchor) and _UNSAFE_CONSTRUCTION_RE.search(anchor):
        safe = _get_safe_syntax(detected_database, language)
        return {
            "classified": "anti_pattern",
            "reason": "sql_interpolation",
            "original": anchor,
            "safe_replacement": f"All SQL uses parameterized queries ({safe})",
        }

    # Rule 2: Explicit "no parameterized queries"
    if _NO_PARAM_RE.search(anchor):
        return {
            "classified": "anti_pattern",
            "reason": "no_parameterized_directive",
            "original": anchor,
            "safe_replacement": "",  # empty = REMOVE
        }

    # Rule 3: "intentional" + SQL/injection context
    if _INTENTIONAL_INJECTION_RE.search(anchor):
        safe = _get_safe_syntax(detected_database, language)
        return {
            "classified": "anti_pattern",
            "reason": "intentional_injection",
            "original": anchor,
            "safe_replacement": f"All SQL uses parameterized queries ({safe})",
        }

    # Rule 4: "reference match" + SQL context
    if _REFERENCE_MATCH_SQL_RE.search(anchor):
        return {
            "classified": "anti_pattern",
            "reason": "reference_match_sql",
            "original": anchor,
            "safe_replacement": "Matches reference API contract; query implementation uses parameterized queries",
        }

    return {"classified": "safe"}


def sanitize_acceptance_obligations(
    obligations: List[str],
    detected_database: str,
    language: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Sanitize a list of acceptance obligations.

    Returns:
        (sanitized_obligations, audit_trail)
    """
    sanitized: List[str] = []
    audit: List[Dict[str, Any]] = []

    for anchor in obligations:
        result = classify_acceptance_anchor(anchor, detected_database, language)
        if result["classified"] == "safe":
            sanitized.append(anchor)
        else:
            audit.append(result)
            replacement = result.get("safe_replacement", "")
            if replacement:
                sanitized.append(replacement)
                logger.info(
                    "QPI anchor sanitized: %r → %r (reason: %s)",
                    anchor, replacement, result.get("reason"),
                )
            else:
                logger.info(
                    "QPI anchor removed: %r (reason: %s)",
                    anchor, result.get("reason"),
                )

    return sanitized, audit


def strip_conflicting_negative_scope(
    negative_scope: List[str],
    detected_database: str,
) -> Tuple[List[str], List[str]]:
    """Remove negative_scope entries that conflict with safe query patterns.

    Returns:
        (cleaned_scope, stripped_entries)
    """
    cleaned: List[str] = []
    stripped: List[str] = []

    for entry in negative_scope:
        if _NEG_SCOPE_CONFLICT_RE.search(entry):
            stripped.append(entry)
            logger.info("QPI negative_scope stripped: %r", entry)
        else:
            cleaned.append(entry)

    return cleaned, stripped


def sanitize_task_description(
    description: str,
    detected_database: str,
    language: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Sanitize a task description to remove SQL anti-pattern language.

    Returns:
        (sanitized_description, audit_trail)
    """
    audit: List[Dict[str, Any]] = []
    result = description

    # R2: Uses module-level _INTERP_SQL_RE (compiled once, not per call).
    safe = _get_safe_syntax(detected_database, language)
    if (match := _INTERP_SQL_RE.search(result)):
        original_phrase = match.group(0)
        replacement = f"parameterized SQL using {safe}"
        result = result[:match.start()] + replacement + result[match.end():]
        audit.append({
            "original": original_phrase,
            "replacement": replacement,
            "reason": "description_sql_interpolation",
        })
        logger.info(
            "QPI description sanitized: %r → %r",
            original_phrase, replacement,
        )

    # R3: Check "matching reference implementation" against the ORIGINAL
    # description (not the modified `result`) to avoid matching content
    # introduced by the replacement above.
    if (m := _REF_MATCH_RE.search(result)) and _SQL_KW_RE.search(description):
        replacement_2 = "using secure parameterized query patterns"
        result = _REF_MATCH_RE.sub(replacement_2, result, count=1)
        audit.append({
            "original": m.group(0),
            "replacement": replacement_2,
            "reason": "description_reference_match",
        })

    return result, audit
