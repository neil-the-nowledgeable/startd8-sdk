"""
Copy Detection - Identifies identical-copy and copy-and-modify tasks.

Scans feature descriptions for duplication signals and validates that the
task is a pure file copy (not a copy-and-modify). Used by PrimeContractor
to bypass LLM generation when a task simply duplicates a predecessor's output,
or to inject predecessor context for copy-and-modify tasks.

Requirements: REQ-MP-1000, REQ-MP-1001, REQ-MP-1003.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Signals that indicate an identical-copy task.
_DUPLICATION_SIGNALS = (
    "identical copy",
    "duplicated identically",
    "exact copy",
    "same as",
    "mirror of",
)

# Signals that indicate modification — if present alongside duplication
# signals, the task is copy_and_modify, not file_copy.
_MODIFICATION_SIGNALS = (
    "with changes",
    "adapted for",
    "modified to",
)


@dataclass
class CopySource:
    """Descriptor for a file-copy source."""

    predecessor_id: str
    source_file: str
    workspace_root: str = ""


@dataclass
class CopyModifySource:
    """Descriptor for a copy-and-modify source (REQ-MP-1003).

    Unlike ``CopySource``, this indicates the task should use LLM generation
    with the predecessor's output injected as reference context.
    """

    predecessor_id: str
    source_file: str


def _infer_source_file(
    feature: Any, predecessor: Optional[Any],
) -> Optional[str]:
    """Infer source file from explicit field or predecessor's single target."""
    source_file = getattr(feature, "copy_source_file", None)
    if source_file is None and predecessor is not None:
        target_files = getattr(predecessor, "target_files", [])
        if len(target_files) == 1:
            source_file = target_files[0]
    return source_file


def detect_copy(
    feature: Any, predecessor: Optional[Any] = None,
) -> "Optional[CopySource | CopyModifySource]":
    """Detect whether *feature* is a copy or copy-and-modify task.

    Classification logic:
    - ``copy_source_task_id`` explicitly set → CopySource (trusted)
    - Duplication signals only + 1 dependency → CopySource
    - Duplication + modification signals + 1 dependency → CopyModifySource
    - Otherwise → None

    Args:
        feature: A ``FeatureSpec``-like object (duck-typed).
        predecessor: Optional predecessor for source file inference.

    Returns:
        ``CopySource``, ``CopyModifySource``, or ``None``.
    """
    # Explicit copy_source_task_id — trust it as a pure file copy.
    copy_source_task_id = getattr(feature, "copy_source_task_id", None)
    if copy_source_task_id is not None:
        source_file = _infer_source_file(feature, predecessor)
        return CopySource(
            predecessor_id=copy_source_task_id,
            source_file=source_file or "",
        )

    description = (getattr(feature, "description", None) or "").lower()

    has_duplication = any(signal in description for signal in _DUPLICATION_SIGNALS)
    if not has_duplication:
        return None

    # Guard: never copy across file types.  A Dockerfile is never a copy
    # of a .py file, even if the description mentions "identical copy" in
    # review commentary about a different aspect (e.g., logger duplication).
    target_files = getattr(feature, "target_files", [])
    if target_files and predecessor is not None:
        pred_targets = getattr(predecessor, "target_files", [])
        if pred_targets:
            target_ext = Path(target_files[0]).suffix
            source_ext = Path(pred_targets[0]).suffix
            if target_ext != source_ext:
                feature_name = getattr(feature, "name", getattr(feature, "id", "?"))
                logger.debug(
                    "Copy detection: '%s' target type (%s) differs from "
                    "predecessor type (%s) — skipping cross-type copy",
                    feature_name, target_ext or "(none)", source_ext or "(none)",
                )
                return None

    # Require exactly one dependency.
    dependencies = getattr(feature, "dependencies", [])
    if len(dependencies) != 1:
        feature_name = getattr(feature, "name", getattr(feature, "id", "?"))
        logger.debug(
            "Feature '%s' has %d dependencies (need exactly 1 for copy detection)",
            feature_name, len(dependencies),
        )
        return None

    predecessor_id = dependencies[0]
    source_file = _infer_source_file(feature, predecessor)

    has_modification = any(signal in description for signal in _MODIFICATION_SIGNALS)
    if has_modification:
        feature_name = getattr(feature, "name", getattr(feature, "id", "?"))
        logger.info(
            "Feature '%s' detected as copy_and_modify from predecessor '%s'",
            feature_name, predecessor_id,
        )
        return CopyModifySource(
            predecessor_id=predecessor_id,
            source_file=source_file or "",
        )

    return CopySource(
        predecessor_id=predecessor_id,
        source_file=source_file or "",
    )


# Backward-compat aliases for existing call sites.
def detect_copy_task(
    feature: Any, predecessor: Optional[Any] = None,
) -> Optional[CopySource]:
    """Detect identical-copy tasks. Delegates to :func:`detect_copy`."""
    result = detect_copy(feature, predecessor)
    return result if isinstance(result, CopySource) else None


def detect_copy_and_modify(
    feature: Any, predecessor: Optional[Any] = None,
) -> Optional[CopyModifySource]:
    """Detect copy-and-modify tasks. Delegates to :func:`detect_copy`."""
    result = detect_copy(feature, predecessor)
    return result if isinstance(result, CopyModifySource) else None


# Default token budget for reference_implementation injection (REQ-MP-1003).
_REFERENCE_TOKEN_BUDGET = 2000

# Rough chars-per-token estimate for budget enforcement.
_CHARS_PER_TOKEN = 4


def compress_reference(source_code: str, token_budget: int = _REFERENCE_TOKEN_BUDGET) -> str:
    """Compress predecessor source code to fit within a token budget.

    Applies tiered compression (REQ-MP-1003, R4-S6):
      1. Strip comments and docstrings
      2. Truncate to budget with a marker

    Args:
        source_code: Raw predecessor source code.
        token_budget: Maximum approximate token count.

    Returns:
        Compressed source code, possibly with a truncation marker.
    """
    char_budget = token_budget * _CHARS_PER_TOKEN

    # If already within budget, return as-is.
    if len(source_code) <= char_budget:
        return source_code

    # Tier 1: Strip comments and docstrings.
    import ast as _ast
    import io as _io
    import tokenize as _tokenize

    stripped = _strip_comments_and_docstrings(source_code)
    if len(stripped) <= char_budget:
        return stripped

    # Tier 2: Truncate with marker.
    truncated = stripped[: char_budget - 80]  # Leave room for marker
    return truncated + "\n# [TRUNCATED — reference exceeds token budget]\n"


def _strip_comments_and_docstrings(source: str) -> str:
    """Remove comments and module/class/function docstrings from Python source."""
    import ast as _ast
    import io as _io
    import tokenize as _tokenize

    # Pass 1: Remove comments via tokenizer.
    try:
        tokens = list(_tokenize.generate_tokens(_io.StringIO(source).readline))
    except _tokenize.TokenError:
        return source  # Unparseable — return as-is

    result_tokens = []
    for tok in tokens:
        if tok.type == _tokenize.COMMENT:
            continue
        result_tokens.append(tok)
    try:
        no_comments = _tokenize.untokenize(result_tokens)
    except ValueError:
        no_comments = source

    # Pass 2: Remove docstrings via AST.
    try:
        tree = _ast.parse(no_comments)
    except SyntaxError:
        return no_comments

    docstring_lines: set[int] = set()
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef, _ast.Module)):
            if (
                node.body
                and isinstance(node.body[0], _ast.Expr)
                and isinstance(node.body[0].value, _ast.Constant)
            ):
                ds_node = node.body[0]
                for line_no in range(ds_node.lineno, ds_node.end_lineno + 1):
                    docstring_lines.add(line_no)

    if not docstring_lines:
        return no_comments

    lines = no_comments.splitlines(keepends=True)
    filtered = [
        line for i, line in enumerate(lines, 1)
        if i not in docstring_lines
    ]
    return "".join(filtered)


def validate_copy_path(source_file: str, workspace_root: str) -> Path:
    """Validate and resolve *source_file* within *workspace_root*.

    Raises:
        ValueError: If the resolved path escapes *workspace_root* (path
            traversal attempt).
    """
    workspace = Path(workspace_root).resolve()
    resolved = Path(workspace_root, source_file).resolve(strict=False)
    if not resolved.is_relative_to(workspace):
        raise ValueError(
            f"Path traversal detected: '{source_file}' resolves to "
            f"'{resolved}' which is outside workspace '{workspace}'"
        )
    return resolved
