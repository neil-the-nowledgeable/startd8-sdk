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


def detect_copy_task(feature: Any, predecessor: Optional[Any] = None) -> Optional[CopySource]:
    """Detect whether *feature* is an identical-copy task.

    Args:
        feature: A ``FeatureSpec``-like object (duck-typed).
        predecessor: Optional predecessor ``FeatureSpec`` used for fallback
            inference of ``copy_source_file`` when not explicitly set.

    Returns:
        A :class:`CopySource` if the feature qualifies, otherwise ``None``.
    """
    # If copy_source_task_id is already set, trust it.
    if feature.copy_source_task_id is not None:
        source_file = _infer_source_file(feature, predecessor)
        return CopySource(
            predecessor_id=feature.copy_source_task_id,
            source_file=source_file or "",
        )

    description = (feature.description or "").lower()

    # Check for duplication signals.
    has_duplication = any(signal in description for signal in _DUPLICATION_SIGNALS)
    if not has_duplication:
        return None

    # Check for modification signals — if both present, this is
    # copy_and_modify, not file_copy.
    has_modification = any(signal in description for signal in _MODIFICATION_SIGNALS)
    if has_modification:
        logger.debug(
            "Feature '%s' has both duplication and modification signals — "
            "not a file_copy task",
            getattr(feature, "name", feature.id),
        )
        return None

    # Require exactly one dependency.
    dependencies = getattr(feature, "dependencies", [])
    if len(dependencies) != 1:
        logger.debug(
            "Feature '%s' has %d dependencies (need exactly 1 for copy detection)",
            getattr(feature, "name", feature.id),
            len(dependencies),
        )
        return None

    predecessor_id = dependencies[0]
    source_file = _infer_source_file(feature, predecessor)

    return CopySource(
        predecessor_id=predecessor_id,
        source_file=source_file or "",
    )


def detect_copy_and_modify(
    feature: Any, predecessor: Optional[Any] = None,
) -> Optional[CopyModifySource]:
    """Detect whether *feature* is a copy-and-modify task (REQ-MP-1003).

    A copy-and-modify task has BOTH duplication signals AND modification
    signals in its description, plus exactly one dependency. The predecessor's
    output should be injected as reference context for LLM generation.

    Args:
        feature: A ``FeatureSpec``-like object (duck-typed).
        predecessor: Optional predecessor for source file inference.

    Returns:
        A :class:`CopyModifySource` if the feature qualifies, otherwise ``None``.
    """
    # Skip if explicit copy_source_task_id is set — that's a pure file copy.
    if getattr(feature, "copy_source_task_id", None) is not None:
        return None

    description = (getattr(feature, "description", None) or "").lower()

    has_duplication = any(signal in description for signal in _DUPLICATION_SIGNALS)
    if not has_duplication:
        return None

    has_modification = any(signal in description for signal in _MODIFICATION_SIGNALS)
    if not has_modification:
        return None

    dependencies = getattr(feature, "dependencies", [])
    if len(dependencies) != 1:
        return None

    predecessor_id = dependencies[0]
    source_file = _infer_source_file(feature, predecessor)

    logger.info(
        "Feature '%s' detected as copy_and_modify from predecessor '%s'",
        getattr(feature, "name", getattr(feature, "id", "?")),
        predecessor_id,
    )

    return CopyModifySource(
        predecessor_id=predecessor_id,
        source_file=source_file or "",
    )


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
                and isinstance(node.body[0].value, (_ast.Constant, _ast.Str))
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
