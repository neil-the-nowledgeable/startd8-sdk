"""
Shared parsers for the implementation engine.

Pure functions for extracting structured data from LLM responses:
score parsing, list section parsing, section content parsing.
"""

import re
from typing import List


__all__ = [
    "parse_score",
    "parse_list_section",
    "parse_section_content",
]


def parse_score(review_text: str) -> int:
    """Parse numeric score from review text.

    Looks for ``Score: N`` pattern and clamps to [0, 100].

    Args:
        review_text: Raw review text from LLM.

    Returns:
        Integer score in [0, 100], or 0 if not found.
    """
    match = re.search(r'Score:\s*(\d+)', review_text, re.IGNORECASE)
    if match:
        return min(100, max(0, int(match.group(1))))
    return 0


def parse_list_section(text: str, section_name: str) -> List[str]:
    """Parse a bulleted list section from markdown text.

    Looks for a markdown header (## or ###) matching ``section_name``
    followed by bulleted items (``-`` or ``*``).

    Args:
        text: Markdown text to parse.
        section_name: Name of the section header (case-insensitive).

    Returns:
        List of stripped item strings, or empty list if section not found.
    """
    pattern = rf'###?\s*{re.escape(section_name)}[^\n]*\n((?:\s*[-*]\s*[^\n]+\n?)+)'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        items_text = match.group(1)
        items = re.findall(r'[-*]\s*(.+)', items_text)
        return [item.strip() for item in items if item.strip()]
    return []


def parse_section_content(text: str, section_name: str) -> str:
    """Parse paragraph content of a section from markdown text.

    Captures content between a matching header and the next header or end.

    Args:
        text: Markdown text to parse.
        section_name: Name of the section header (case-insensitive).

    Returns:
        Stripped section content, or empty string if not found.
    """
    pattern = rf'###?\s*{re.escape(section_name)}[^\n]*\n(.*?)(?=###|\Z)'
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        content = match.group(1).strip()
        content = re.sub(r'^[-*]\s*', '', content, flags=re.MULTILINE)
        return content.strip()
    return ""
