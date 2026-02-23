"""Edit-First Enforcement gate for the Artisan IMPLEMENT phase (REQ-EFE-020–023).

Post-generation size regression gate that compares output size to input size
and rejects destructive rewrites.  Character-count based with per-artifact-type
thresholds from ContextCore ``expected_output_contracts`` / ``schema_features``.

Fundamentally different from Gate 4's advisory line-count-based size regression
check (``_SIZE_REGRESSION_THRESHOLD = 0.70``): this gate is character-count
based, uses per-artifact-type thresholds, and is blocking with retry capability.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Optional

from startd8.logging_config import get_logger
from startd8.otel_conventions import EventNames

logger = get_logger(__name__)

# Default threshold when schema_features lacks "edit_first_enforcement"
_DEFAULT_EDIT_MIN_PCT = 80

# Valid values for EditFirstResult.action
_VALID_ACTIONS = frozenset({"passed", "rejected", "new_file", "force_overridden"})


@dataclass
class EditFirstResult:
    """Per-file edit-first gate check result."""

    file_path: str
    input_chars: int
    output_chars: int
    ratio: float  # output_chars / input_chars as percentage (0-100)
    threshold: float  # edit_min_pct for this artifact type
    artifact_type: str
    passed: bool
    action: str  # "passed" | "rejected" | "new_file" | "force_overridden"


@dataclass
class EditFirstGateResult:
    """Per-task aggregate gate result.

    Attributes:
        task_id: Task identifier.
        file_results: Per-file check results.
        any_rejected: True if any file failed the gate (before or after retry).
        retry_needed: True if the initial check rejected any file (set once,
            not cleared by retry — use ``retry_succeeded`` to check outcome).
        retry_succeeded: True only when retry was attempted AND all previously
            rejected files now pass.
    """

    task_id: str
    file_results: list[EditFirstResult] = field(default_factory=list)
    any_rejected: bool = False
    retry_needed: bool = False
    retry_succeeded: bool = False


def resolve_threshold(
    artifact_types: list[str],
    output_contracts: Optional[dict[str, Any]] = None,
    schema_features: Optional[dict[str, Any]] = None,
) -> float:
    """Resolve ``edit_min_pct`` threshold for the given artifact types.

    REQ-EFE-021: resolve from ``output_contracts``; when ``schema_features``
    lacks ``"edit_first_enforcement"``, default to 80% with warning.
    Multi-artifact tasks use ``max()`` (strictest threshold).

    Returns:
        The resolved threshold as a percentage (0-100).
    """
    output_contracts = output_contracts or {}
    schema_features = schema_features or {}

    # Check if edit_first_enforcement is declared in schema_features
    has_feature_flag = "edit_first_enforcement" in schema_features

    if not has_feature_flag:
        warnings.warn(
            "schema_features missing 'edit_first_enforcement' — "
            f"defaulting to {_DEFAULT_EDIT_MIN_PCT}% threshold",
            stacklevel=2,
        )
        logger.warning(
            "edit_first_enforcement not in schema_features — "
            "using default %d%% threshold",
            _DEFAULT_EDIT_MIN_PCT,
        )
        return float(_DEFAULT_EDIT_MIN_PCT)

    # Resolve per-artifact-type thresholds from output_contracts
    thresholds: list[float] = []
    for art_type in artifact_types:
        contract = output_contracts.get(art_type, {})
        pct = contract.get("edit_min_pct")
        if pct is not None:
            thresholds.append(float(pct))

    if not thresholds:
        # Feature flag present but no per-type thresholds found — use default
        return float(_DEFAULT_EDIT_MIN_PCT)

    # Multi-artifact: take strictest (highest) threshold
    return max(thresholds)


def validate_task_size_regression(
    task_id: str,
    generated_files: dict[str, str],
    existing_contents: dict[str, str],
    threshold: float,
    artifact_type: str = "unknown",
    force_rewrite: bool = False,
) -> EditFirstGateResult:
    """Per-file char-count comparison for edit-first enforcement (REQ-EFE-020).

    Args:
        task_id: Task identifier.
        generated_files: Mapping of file_path -> generated content (str).
        existing_contents: Mapping of file_path -> existing content (str).
            Files absent from this dict are treated as new files (always pass).
        threshold: Minimum output/input ratio as percentage (0-100).
        artifact_type: Artifact type label for telemetry.
        force_rewrite: If True, all files pass with action="force_overridden".

    Returns:
        EditFirstGateResult with per-file results.
    """
    result = EditFirstGateResult(task_id=task_id)

    for file_path, gen_content in generated_files.items():
        existing = existing_contents.get(file_path)

        if existing is None:
            # New file — always passes
            result.file_results.append(EditFirstResult(
                file_path=file_path,
                input_chars=0,
                output_chars=len(gen_content),
                ratio=100.0,
                threshold=threshold,
                artifact_type=artifact_type,
                passed=True,
                action="new_file",
            ))
            continue

        input_chars = len(existing)
        output_chars = len(gen_content)

        if input_chars == 0:
            # Empty existing file — treat as new
            ratio = 100.0
        else:
            ratio = (output_chars / input_chars) * 100.0

        if force_rewrite:
            result.file_results.append(EditFirstResult(
                file_path=file_path,
                input_chars=input_chars,
                output_chars=output_chars,
                ratio=ratio,
                threshold=threshold,
                artifact_type=artifact_type,
                passed=True,
                action="force_overridden",
            ))
            continue

        passed = ratio >= threshold
        action = "passed" if passed else "rejected"

        result.file_results.append(EditFirstResult(
            file_path=file_path,
            input_chars=input_chars,
            output_chars=output_chars,
            ratio=ratio,
            threshold=threshold,
            artifact_type=artifact_type,
            passed=passed,
            action=action,
        ))

        if not passed:
            result.any_rejected = True
            result.retry_needed = True
            logger.warning(
                "Edit-first gate REJECTED %s: %s — ratio=%.1f%% < threshold=%.1f%% "
                "(input=%d chars, output=%d chars)",
                task_id, file_path, ratio, threshold, input_chars, output_chars,
            )

    return result


def emit_rejection_telemetry(
    result: EditFirstGateResult,
    span: Any,
) -> None:
    """Emit OTel span event for edit-first size regression (REQ-EFE-022).

    Emits ``"edit_first.size_regression"`` event with required attributes
    for each rejected file in the gate result.
    """
    if span is None:
        return

    for fr in result.file_results:
        if fr.action == "rejected":
            try:
                span.add_event(
                    EventNames.EDIT_FIRST_SIZE_REGRESSION,
                    attributes={
                        "task.id": result.task_id,
                        "file.path": fr.file_path,
                        "edit_first.input_chars": fr.input_chars,
                        "edit_first.output_chars": fr.output_chars,
                        "edit_first.ratio_pct": round(fr.ratio, 2),
                        "edit_first.threshold_pct": fr.threshold,
                        "edit_first.artifact_type": fr.artifact_type,
                        "edit_first.action": fr.action,
                    },
                )
            except Exception as exc:
                logger.debug(
                    "Failed to emit edit-first telemetry for %s: %s",
                    fr.file_path, exc,
                )


def build_edit_retry_prompt(
    original_content: str,
    design_doc: str,
    task_description: str,
    ratio: float,
    threshold: float,
) -> str:
    """Build an edit-focused retry prompt for a rejected file (REQ-EFE-023).

    The prompt instructs the LLM to edit the existing file rather than
    rewriting it from scratch, preserving the majority of the original content.

    Args:
        original_content: The existing file content to be edited.
        design_doc: The design document for the task.
        task_description: Human-readable task description.
        ratio: The output/input ratio that triggered rejection (percentage).
        threshold: The minimum required ratio (percentage).

    Returns:
        A formatted prompt string for the retry attempt.
    """
    return (
        f"IMPORTANT: Your previous attempt was rejected by the edit-first "
        f"enforcement gate because the output was only {ratio:.1f}% of the "
        f"original file size (minimum required: {threshold:.1f}%).\n\n"
        f"You MUST EDIT the existing file, not rewrite it from scratch. "
        f"Preserve the existing structure and content. Only make the changes "
        f"described in the task — do not remove, reorganize, or rewrite "
        f"sections that are not part of the task.\n\n"
        f"## Task\n{task_description}\n\n"
        f"## Design Document\n{design_doc}\n\n"
        f"## Original File Content (PRESERVE THIS)\n"
        f"```\n{original_content}\n```\n\n"
        f"Apply ONLY the changes specified in the task and design document. "
        f"The output must retain at least {threshold:.1f}% of the original "
        f"file's character count."
    )
