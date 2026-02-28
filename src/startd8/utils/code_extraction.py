"""
Code extraction utilities for LLM responses.

Extracts code from markdown-fenced LLM responses, stripping preamble text
and explanatory notes. Used by LeadContractorWorkflow and available for
downstream integration pipelines.
"""

import os
import re
from typing import Dict, List, Optional, Tuple

from startd8.logging_config import get_logger

#: Machine-readable sentinel embedded in every auto-generated stub.
#: Used by observability and downstream phases to detect stubs without
#: fragile substring heuristics.
STUB_SENTINEL = "STARTD8_AUTO_STUB"

logger = get_logger("startd8.utils.code_extraction")


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

    # No code blocks found - check if response looks like raw code.
    # These indicators must cover all languages the SDK's drafters produce,
    # not just Python (context-blind heuristic anti-pattern).
    stripped = response.strip()
    first_line = stripped.split('\n', 1)[0] if stripped else ''
    code_indicators = [
        # Universal
        first_line.startswith('#!/'),
        # Python
        first_line.startswith('import '),
        first_line.startswith('from '),
        first_line.startswith('def '),
        first_line.startswith('class '),
        first_line.startswith('# ==='),  # Common header pattern
        # TypeScript / JavaScript
        first_line.startswith('export '),
        first_line.startswith('const '),
        first_line.startswith('let '),
        first_line.startswith('function '),
        first_line.startswith('async '),
        first_line.startswith('interface '),
        first_line.startswith('type '),
        # Go
        first_line.startswith('package '),
        # Rust
        first_line.startswith('use '),
        first_line.startswith('fn '),
        first_line.startswith('pub '),
        first_line.startswith('mod '),
        # C / C++
        first_line.startswith('#include '),
        # Common comment-header patterns (// file.ts, /* ... */)
        first_line.startswith('// '),
        first_line.startswith('/* '),
    ]

    if any(code_indicators):
        logger.debug("Response appears to be raw code without markdown blocks")
        return stripped

    # Fallback: return as-is but log warning
    logger.warning(
        "No code blocks found in response (%d chars). "
        "Using raw response - may include commentary.",
        len(response),
    )
    return response


def extract_multi_file_code(
    response: str,
    target_files: List[str],
    *,
    stub_missing: bool = False,
) -> Dict[str, str]:
    """
    Split an LLM response containing multiple file implementations into per-file code.

    Tries strategies in order:
    1. **File-path comment markers** — looks for lines like ``// path/to/file.ts``
       or ``# path/to/file.py`` that precede code blocks.
    2. **Multiple fenced code blocks** — matches separate ````` blocks where the
       filename appears in the language tag or as a first-line comment.
    3. **Order-based fallback** — when exactly one file is unmatched and one
       block didn't match, assign by position (handles __init__.py etc.).
    4. **Stub generation** (when ``stub_missing=True``) — for any target file
       still unmatched, generate a minimal placeholder stub. This is the
       last-resort recovery layer for shared modules that the LLM omitted.

    Args:
        response: Raw LLM response (may contain markdown fencing, commentary, etc.)
        target_files: Expected output file paths (used for basename matching)
        stub_missing: If True, generate placeholder stubs for unmatched files
            instead of leaving them out. Enables graceful degradation for
            shared modules the LLM skipped.

    Returns:
        Dict mapping target filename → extracted code.
        Returns an empty dict if splitting fails and ``stub_missing`` is False.
    """
    if not response or not target_files:
        return {}

    basenames = {os.path.basename(f): f for f in target_files}

    # Try both strategies and return the one with the most matches.
    # This avoids Strategy 1 (markers) short-circuiting Strategy 2 (fenced
    # blocks) when markers appear inside fenced blocks and produce garbled results.

    best: Dict[str, str] = {}

    # --- Strategy 1: file-path comment markers ---
    # Matches lines like: // path/to/File.tsx  or  # path/to/file.py
    # The code block follows until the next such marker or end of string.
    marker_pattern = re.compile(
        r'^(?://|#)\s*(\S+\.(?:'
        r'ts|tsx|js|jsx|py|css|html|vue|svelte|go|rs|java|rb'  # code
        r'|csv|md|json|yaml|yml|toml|txt|sql|xml|cfg|ini|env|sh|bat'  # data/config/docs
        r'))\s*$',
        re.MULTILINE,
    )
    markers = list(marker_pattern.finditer(response))
    if markers:
        result = _extract_by_markers(response, markers, basenames)
        if len(result) > len(best):
            best = result

    # --- Strategy 2: multiple fenced code blocks with filename hints ---
    # Pattern: ```lang or ```filename.ext  followed by code  followed by ```
    block_pattern = re.compile(
        r'```(\S*)\s*\n(.*?)```', re.DOTALL
    )
    blocks = list(block_pattern.finditer(response))
    if len(blocks) >= 2:
        result = _extract_by_fenced_blocks(response, blocks, basenames, target_files)
        if len(result) > len(best):
            best = result

    # --- Strategy 4: stub generation for unmatched files ---
    if stub_missing:
        unmatched = [f for f in target_files if f not in best]
        for missing_file in unmatched:
            stub = _generate_stub(missing_file)
            best[missing_file] = stub
            logger.warning(
                "Multi-file split: generated stub for unmatched file %s "
                "(LLM did not produce a code block for this target)",
                missing_file,
            )

    return best


def _generate_stub(file_path: str) -> str:
    """Generate a minimal placeholder stub for a file the LLM omitted.

    Produces a syntactically valid file with a docstring explaining it's
    a stub. Every stub embeds :data:`STUB_SENTINEL` so downstream code
    can detect stubs without fragile substring heuristics.

    The stub is intentionally minimal — downstream tasks will implement
    the real logic.

    Args:
        file_path: Target file path (used to determine language/format).

    Returns:
        Stub file content string (always contains :data:`STUB_SENTINEL`).
    """
    basename = os.path.basename(file_path)
    ext = os.path.splitext(basename)[1].lower()

    if ext == ".py":
        return (
            f"# {STUB_SENTINEL}\n"
            f'"""{basename} — auto-generated stub.\n'
            f"\n"
            f"This file was not produced by the LLM drafter and has been\n"
            f"auto-stubbed to satisfy the multi-file build requirement.\n"
            f"Downstream tasks will implement the real logic.\n"
            f'"""\n'
            f"\n"
            f"__all__: list[str] = []\n"
        )
    elif ext in (".ts", ".tsx", ".js", ".jsx"):
        return (
            f"// {STUB_SENTINEL}\n"
            f"// {basename} — auto-generated stub.\n"
            f"//\n"
            f"// This file was not produced by the LLM drafter and has been\n"
            f"// auto-stubbed to satisfy the multi-file build requirement.\n"
            f"// Downstream tasks will implement the real logic.\n"
            f"export {{}};\n"
        )
    elif ext == ".go":
        # Go requires a package declaration; derive from parent directory name.
        parent_dir = os.path.basename(os.path.dirname(file_path)) or "main"
        return (
            f"// {STUB_SENTINEL}\n"
            f"// {basename} — auto-generated stub.\n"
            f"//\n"
            f"// This file was not produced by the LLM drafter.\n"
            f"// Downstream tasks will implement the real logic.\n"
            f"package {parent_dir}\n"
        )
    elif ext == ".rs":
        return (
            f"// {STUB_SENTINEL}\n"
            f"// {basename} — auto-generated stub.\n"
            f"//\n"
            f"// This file was not produced by the LLM drafter.\n"
            f"// Downstream tasks will implement the real logic.\n"
        )
    elif ext == ".java":
        # Java requires a class matching the filename (without extension).
        class_name = os.path.splitext(basename)[0]
        return (
            f"// {STUB_SENTINEL}\n"
            f"// {basename} — auto-generated stub.\n"
            f"//\n"
            f"// This file was not produced by the LLM drafter.\n"
            f"// Downstream tasks will implement the real logic.\n"
            f"public class {class_name} {{}}\n"
        )
    elif ext in (".c", ".h", ".cpp", ".hpp"):
        return (
            f"// {STUB_SENTINEL}\n"
            f"// {basename} — auto-generated stub.\n"
            f"//\n"
            f"// This file was not produced by the LLM drafter.\n"
            f"// Downstream tasks will implement the real logic.\n"
        )
    elif ext in (".yaml", ".yml"):
        return (
            f"# {STUB_SENTINEL}\n"
            f"# {basename} — auto-generated stub.\n"
            f"# This file was not produced by the LLM drafter.\n"
            f"# Downstream tasks will populate it.\n"
        )
    else:
        return (
            f"# {STUB_SENTINEL}\n"
            f"# {basename} — auto-generated stub.\n"
            f"# This file was not produced by the LLM drafter.\n"
        )


def _extract_by_markers(
    response: str,
    markers: list,
    basenames: Dict[str, str],
) -> Dict[str, str]:
    """Extract code sections delimited by file-path comment markers."""
    result: Dict[str, str] = {}

    for i, marker in enumerate(markers):
        marker_basename = os.path.basename(marker.group(1))
        # Find which target file this marker refers to
        matched_target = _match_basename(marker_basename, basenames)
        if not matched_target:
            continue

        # Extract content from after this marker to before the next marker (or end)
        start = marker.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(response)
        section = response[start:end].strip()

        # Strip fenced code block wrappers if present within the section
        code = extract_code_from_response(section)
        if code.strip():
            result[matched_target] = code.strip()

    # Return whatever we matched — caller handles unmatched files via fallback
    return result


def _extract_by_fenced_blocks(
    response: str,
    blocks: list,
    basenames: Dict[str, str],
    target_files: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Extract code from multiple fenced blocks matched to target files."""
    result: Dict[str, str] = {}
    unmatched_blocks: List[Tuple[str, int]] = []  # (code_content, block_index)

    for i, block in enumerate(blocks):
        lang_or_filename = block.group(1)
        code_content = block.group(2).strip()
        if not code_content:
            continue

        matched_target = None

        # Check if the language tag IS a filename (e.g. ```MigrationQueue.tsx or ```path/to/__init__.py)
        if '.' in lang_or_filename:
            block_basename = os.path.basename(lang_or_filename)
            matched_target = _match_basename(block_basename, basenames)
            # Also try path suffix match (e.g. lang="generators/__init__.py")
            if not matched_target and target_files:
                for tf in target_files:
                    if tf == lang_or_filename or tf.endswith("/" + lang_or_filename):
                        matched_target = tf
                        break

        # Check first line of code for a file-path comment
        if not matched_target:
            first_line = code_content.split('\n', 1)[0].strip()
            # Matches: // MigrationQueue.tsx  or  # path/to/__init__.py
            fname_comment = re.match(r'^(?://|#)\s*(\S+\.\w+)', first_line)
            if fname_comment:
                path_or_name = fname_comment.group(1)
                block_basename = os.path.basename(path_or_name)
                matched_target = _match_basename(block_basename, basenames)
                if not matched_target and target_files:
                    for tf in target_files:
                        if tf == path_or_name or tf.endswith("/" + path_or_name):
                            matched_target = tf
                            break
                # Strip the filename comment from the code
                if matched_target:
                    _, _, rest = code_content.partition('\n')
                    code_content = rest.strip()

        if matched_target and code_content:
            result[matched_target] = code_content
        else:
            unmatched_blocks.append((code_content, i))

    # Strategy 3a (Layer 4 defense-in-depth): content-heuristic matching for
    # __init__.py.  Models often produce a block with __all__, re-exports,
    # or "from .module import ..." but forget to label it as __init__.py.
    # Match unmatched blocks whose content looks like a package __init__ to
    # the unmatched __init__.py target (if any).
    targets = target_files or list(basenames.values())
    unmatched_targets = [t for t in targets if t not in result]
    init_targets = [t for t in unmatched_targets if t.endswith("__init__.py")]
    if init_targets and unmatched_blocks:
        for init_target in init_targets:
            for idx, (content, block_idx) in enumerate(unmatched_blocks):
                if _looks_like_init(content):
                    result[init_target] = content.strip()
                    unmatched_blocks.pop(idx)
                    logger.debug(
                        "Assigned unmatched block (idx=%d) to %s via "
                        "__init__.py content heuristic",
                        block_idx,
                        init_target,
                    )
                    break
        # Refresh unmatched targets after heuristic
        unmatched_targets = [t for t in targets if t not in result]

    # Strategy 3b: order-based fallback when exactly one file and one block unmatched
    if len(unmatched_targets) == 1 and len(unmatched_blocks) == 1:
        content, _ = unmatched_blocks[0]
        if content.strip():
            result[unmatched_targets[0]] = content.strip()
            logger.debug(
                "Assigned unmatched block to %s via order fallback",
                unmatched_targets[0],
            )

    return result


def _looks_like_init(code: str) -> bool:
    """Heuristic: does ``code`` look like a Python ``__init__.py``?

    Checks for common patterns: ``__all__``, relative imports
    (``from .foo import``), or the string ``__init__`` in a comment/docstring.
    """
    if not code:
        return False
    indicators = [
        "__all__" in code,
        "from ." in code,                       # relative imports
        "__init__" in code.split("\n", 3)[0],    # filename in first line comment
    ]
    return any(indicators)


def _match_basename(candidate: str, basenames: Dict[str, str]) -> Optional[str]:
    """Match a candidate filename against target basenames (case-insensitive).

    If multiple targets share the same case-insensitive basename (e.g.
    ``Foo.ts`` and ``foo.ts``), the match is ambiguous — log a warning and
    return ``None`` so the caller falls back to full-path matching.
    """
    # Exact match first
    if candidate in basenames:
        return basenames[candidate]
    # Case-insensitive fallback — collect ALL matches to detect ambiguity
    candidate_lower = candidate.lower()
    matches = [
        target
        for basename, target in basenames.items()
        if basename.lower() == candidate_lower
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.warning(
            "Ambiguous case-insensitive basename match for %r: "
            "matched %d targets %s — falling back to full-path matching",
            candidate,
            len(matches),
            matches,
        )
        return None
    return None
