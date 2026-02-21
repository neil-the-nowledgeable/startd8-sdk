"""Context formatters for transforming structured data into Markdown.

This module provides pure formatter functions that transform structured
JSON/dict data into well-formatted Markdown strings for prompt assembly.
Each formatter accepts a dict (or None) and returns a Markdown string
(or empty string for missing/empty data).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

__all__ = [
    "FormatterFn",
    "SECTION_FORMATTERS",
    "CANONICAL_SECTION_ORDER",
    "format_architectural_context",
    "format_requirements",
    "format_constraints",
    "format_design_decisions",
    "format_dependencies",
    "format_interfaces",
    "format_general_section",
    "format_section",
    "format_full_context",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SECTION_HEADER_LEVEL: int = 2
SUBSECTION_HEADER_LEVEL: int = 3
MAX_HEADER_LEVEL: int = 6
SECTION_SEPARATOR: str = "\n\n"
BULLET_PREFIX: str = "- "
NESTED_BULLET_PREFIX: str = "  - "
MAX_OUTPUT_LENGTH: int = 50_000
MAX_VALUE_REPR_LENGTH: int = 2_000

CANONICAL_SECTION_ORDER: tuple[str, ...] = (
    "architectural_context",
    "requirements",
    "constraints",
    "design_decisions",
    "dependencies",
    "interfaces",
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type Aliases
# ---------------------------------------------------------------------------

FormatterFn = Callable[[dict | None], str]

# ---------------------------------------------------------------------------
# Sanitization Utilities
# ---------------------------------------------------------------------------


def _sanitize_text(value: str) -> str:
    """Sanitize a string value to mitigate prompt injection risks.

    Handles:
    - Template variable injection ({{ }})
    - Triple backtick context escaping
    - Markdown heading injection (lines starting with #)
    - Markdown link/image injection ([text](url), ![alt](url))
    - HTML tag injection (<tag>, </tag>)
    - Leading/trailing whitespace
    """
    if not isinstance(value, str):
        logger.debug(
            "_sanitize_text received non-string type %s; coercing.",
            type(value).__name__,
        )
        value = str(value)

    sanitized = value.strip()

    # Neutralize template variable patterns
    sanitized = sanitized.replace("{{", "{ {").replace("}}", "} }")

    # Escape triple backticks that could break out of fenced code blocks
    sanitized = sanitized.replace("