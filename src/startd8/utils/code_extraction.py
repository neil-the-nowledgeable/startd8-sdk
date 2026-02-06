"""
Code extraction utilities for LLM responses.

Extracts code from markdown-fenced LLM responses, stripping preamble text
and explanatory notes. Used by LeadContractorWorkflow and available for
downstream integration pipelines.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger("startd8.utils.code_extraction")


def extract_code_from_response(response: str, language: Optional[str] = None) -> str:
    """
    Extract code from markdown code blocks in an LLM response.

    Handles responses that include preamble text, code blocks, and
    explanatory notes.  Returns only the code content.

    Supports:
    - ``​`python ... ``​`
    - ``​`yaml ... ``​`
    - ``​` ... ``​` (generic)
    - Multiple code blocks (returns the largest one)

    Falls back to raw response if no code block is found.

    Args:
        response: Raw LLM response text
        language: Optional language hint (currently unused, reserved for
            future filtering by language tag)

    Returns:
        Extracted code string, or the raw response as fallback
    """
    if not response:
        return response

    # Pattern to match code blocks with optional language specifier
    # Captures content between ``` markers
    pattern = r'```(?:\w+)?\s*\n(.*?)```'
    matches = re.findall(pattern, response, re.DOTALL)

    if matches:
        # Return the first (and typically main) code block
        extracted = matches[0].strip()

        # If multiple code blocks, return the largest one
        if len(matches) > 1:
            largest = max(matches, key=len).strip()
            if len(largest) > len(extracted):
                extracted = largest

        logger.debug(
            "Extracted %d chars from code block (response was %d chars)",
            len(extracted),
            len(response),
        )
        return extracted

    # No code blocks found - check if response looks like raw code
    code_indicators = [
        response.strip().startswith('#!/'),
        response.strip().startswith('import '),
        response.strip().startswith('from '),
        response.strip().startswith('def '),
        response.strip().startswith('class '),
        response.strip().startswith('# ==='),  # Common header pattern
    ]

    if any(code_indicators):
        logger.debug("Response appears to be raw code without markdown blocks")
        return response.strip()

    # Fallback: return as-is but log warning
    logger.warning(
        "No code blocks found in response (%d chars). "
        "Using raw response - may include commentary.",
        len(response),
    )
    return response
