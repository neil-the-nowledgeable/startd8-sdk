"""Search/Replace edit block parser and applicator.

Provides structured edit blocks for surgical file modifications,
avoiding the need for the LLM to output entire files.  The format
mirrors the proven SEARCH/REPLACE pattern used by aider and Claude Code.

Usage::

    from startd8.utils.search_replace import (
        parse_edit_blocks, apply_edit_blocks, has_edit_markers,
    )

    blocks = parse_edit_blocks(llm_response)
    if blocks is not None:
        result = apply_edit_blocks(existing_content, blocks)
        if result.success:
            new_content = result.content
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ── Markers ──────────────────────────────────────────────────────────
_SEARCH_MARKER = "<<<<<<< SEARCH"
_DIVIDER_MARKER = "======="
_REPLACE_MARKER = ">>>>>>> REPLACE"


# ── Data structures ──────────────────────────────────────────────────

@dataclass(frozen=True)
class EditBlock:
    """A single search/replace edit operation."""

    search_text: str
    """Exact text to find in the file."""

    replace_text: str
    """Replacement text."""

    block_index: int
    """Ordering index (0-based)."""

    file_hint: Optional[str] = None
    """Optional file path hint extracted from context preceding the block.

    When the LLM emits a filename comment or header (e.g. ``# path/to/file.py``
    or ``## path/to/file.py``) before the SEARCH marker, this field captures
    the path for file-scoped S/R routing (R2-I5).
    """


@dataclass
class EditResult:
    """Outcome of applying edit blocks to file content."""

    success: bool
    """True if all blocks applied successfully."""

    content: str
    """Final file content after applying all blocks."""

    applied: int
    """Number of blocks that matched and were applied."""

    failed: List[Tuple[EditBlock, str]]
    """List of (block, reason) for blocks that did not match."""


# ── Public API ───────────────────────────────────────────────────────

def has_edit_markers(response: str) -> bool:
    """Quick check: does the response contain SEARCH/REPLACE markers?"""
    return _SEARCH_MARKER in response and _REPLACE_MARKER in response


def parse_edit_blocks(response: str) -> Optional[List[EditBlock]]:
    """Parse ``<<<<<<< SEARCH / ======= / >>>>>>> REPLACE`` blocks.

    Returns ``None`` if no markers are found (response is a whole file).
    Returns an empty list if markers are found but malformed.

    R2-I5: Captures file path hints from lines preceding each SEARCH marker
    (e.g. ``# path/to/file.py``, ``## path/to/file.py``, ``// file.ts``).
    The ``file_hint`` is stored on each :class:`EditBlock` so callers can
    scope S/R blocks to the intended target file.
    """
    if not has_edit_markers(response):
        return None

    # R2-I5: Regex to detect file path hints preceding SEARCH blocks.
    # Matches lines like: # path/to/file.py, ## file.ts, // Component.tsx
    _file_hint_re = re.compile(
        r'^(?:#{1,3}|//|#)\s+(\S+\.(?:'
        r'ts|tsx|js|jsx|py|css|html|vue|svelte|go|rs|java|rb'
        r'|csv|md|json|yaml|yml|toml|txt|sql|xml|cfg|ini|env|sh|bat'
        r'))\s*$'
    )

    blocks: List[EditBlock] = []
    lines = response.splitlines(keepends=True)
    i = 0
    block_index = 0
    # R2-I5: Track the most recent file hint seen before a SEARCH marker.
    current_file_hint: Optional[str] = None

    while i < len(lines):
        line = lines[i].rstrip("\n\r")

        # R2-I5: Check for file path hints before SEARCH markers
        hint_match = _file_hint_re.match(line.strip())
        if hint_match:
            current_file_hint = hint_match.group(1)

        # Look for SEARCH marker
        if line.strip() == _SEARCH_MARKER:
            # Capture the file hint active at this SEARCH marker
            block_file_hint = current_file_hint

            # Collect search text until divider
            search_lines: List[str] = []
            i += 1
            found_divider = False
            while i < len(lines):
                cur = lines[i].rstrip("\n\r")
                if cur.strip() == _DIVIDER_MARKER:
                    found_divider = True
                    i += 1
                    break
                search_lines.append(lines[i])
                i += 1

            if not found_divider:
                # Malformed block — skip
                continue

            # Collect replace text until REPLACE marker
            replace_lines: List[str] = []
            found_replace = False
            while i < len(lines):
                cur = lines[i].rstrip("\n\r")
                if cur.strip() == _REPLACE_MARKER:
                    found_replace = True
                    i += 1
                    break
                replace_lines.append(lines[i])
                i += 1

            if not found_replace:
                continue

            # Join and strip trailing newline only (preserve internal whitespace)
            search_text = "".join(search_lines)
            replace_text = "".join(replace_lines)

            # Strip single trailing newline if present (block delimiter artifact)
            if search_text.endswith("\n"):
                search_text = search_text[:-1]
            if replace_text.endswith("\n"):
                replace_text = replace_text[:-1]

            blocks.append(EditBlock(
                search_text=search_text,
                replace_text=replace_text,
                block_index=block_index,
                file_hint=block_file_hint,
            ))
            block_index += 1
        else:
            i += 1

    return blocks


def apply_edit_blocks(content: str, blocks: List[EditBlock]) -> EditResult:
    """Apply edit blocks sequentially to file content.

    Matching strategy (per block):
    1. Exact ``str.find()`` — fast, handles most cases.
    2. Per-line trailing whitespace stripped — handles LLM whitespace drift.
    3. If both fail, record as failed with a clear error message.

    Blocks are applied in order; each subsequent block operates on the
    content as modified by all previous blocks.
    """
    applied = 0
    failed: List[Tuple[EditBlock, str]] = []
    current = content

    for block in blocks:
        # Strategy 1: exact match
        idx = current.find(block.search_text)
        if idx != -1:
            current = (
                current[:idx]
                + block.replace_text
                + current[idx + len(block.search_text):]
            )
            applied += 1
            continue

        # Strategy 2: whitespace-normalized per-line match
        matched, new_content = _whitespace_normalized_replace(
            current, block.search_text, block.replace_text,
        )
        if matched:
            current = new_content
            applied += 1
            continue

        # Both strategies failed
        preview = block.search_text[:80].replace("\n", "\\n")
        failed.append((
            block,
            f"Block {block.block_index}: no match found for: {preview!r}",
        ))

    success = len(failed) == 0
    return EditResult(
        success=success,
        content=current,
        applied=applied,
        failed=failed,
    )


# ── Internal helpers ─────────────────────────────────────────────────

def _strip_trailing_ws(text: str) -> str:
    """Strip trailing whitespace from each line."""
    return "\n".join(line.rstrip() for line in text.splitlines())


def _whitespace_normalized_replace(
    content: str,
    search: str,
    replace: str,
) -> Tuple[bool, str]:
    """Try to match *search* against *content* with trailing whitespace
    stripped from each line on both sides.

    Returns ``(True, modified_content)`` on success, ``(False, "")``
    on failure.
    """
    norm_content = _strip_trailing_ws(content)
    norm_search = _strip_trailing_ws(search)

    if not norm_search:
        return False, ""

    idx = norm_content.find(norm_search)
    if idx == -1:
        return False, ""

    # Map the normalized index back to the original content.
    # We do this by finding which original lines correspond to the
    # normalized match range.
    content_lines = content.splitlines(keepends=True)
    norm_lines = norm_content.splitlines(keepends=True)

    # Find the line range in normalized content
    chars_before = 0
    start_line = 0
    for li, nline in enumerate(norm_lines):
        if chars_before + len(nline) > idx:
            start_line = li
            break
        chars_before += len(nline)

    search_norm_lines = norm_search.splitlines()
    end_line = start_line + len(search_norm_lines)

    # Verify line-by-line match
    if end_line > len(content_lines):
        return False, ""
    for j, sline in enumerate(search_norm_lines):
        if content_lines[start_line + j].rstrip("\n\r").rstrip() != sline.rstrip():
            return False, ""

    # Replace the matched lines with the replacement text
    before = "".join(content_lines[:start_line])
    after = "".join(content_lines[end_line:])
    new_content = before + replace + ("\n" if after and not replace.endswith("\n") else "") + after

    return True, new_content
