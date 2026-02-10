"""
Standalone adapters for Prime Contractor protocols.

These adapters work without ContextCore and provide:
- Logging-based instrumentation
- Heuristic size estimation
- Simple file merge (overwrite)

Use these when running startd8 standalone or when ContextCore is not available.
"""

import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...logging_config import get_logger
from ..protocols import (
    MergeResult,
    MergeStatus,
    SizeEstimate,
    SpanContext,
)


logger = get_logger("startd8.contractors")


# ============================================================================
# LoggingInstrumentor
# ============================================================================


class LoggingInstrumentor:
    """
    Instrumentor that uses Python logging.

    Provides observability without external dependencies.
    Useful for debugging and development.

    Example:
        instrumentor = LoggingInstrumentor(project_id="myproject")
        ctx = instrumentor.emit_span("process_feature", {"feature_name": "auth"})
        instrumentor.emit_event("integration_started", {"files": ["auth.py"]})
        instrumentor.emit_metric("cost.usd", 0.05, {"agent": "drafter"})
    """

    def __init__(
        self,
        project_id: str = "default",
        log_level: int = logging.INFO,
    ):
        """
        Initialize the logging instrumentor.

        Args:
            project_id: Project identifier for log context
            log_level: Python logging level
        """
        self.project_id = project_id
        self.log_level = log_level
        self._active_spans: Dict[str, SpanContext] = {}

    def emit_span(
        self,
        name: str,
        attributes: Dict[str, Any],
    ) -> SpanContext:
        """Emit a span as a log entry."""
        trace_id = uuid.uuid4().hex[:16]
        span_id = uuid.uuid4().hex[:8]

        ctx = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            attributes=attributes,
        )
        self._active_spans[span_id] = ctx

        logger.log(
            self.log_level,
            f"[SPAN START] {name} trace={trace_id} span={span_id} "
            f"attrs={_format_attrs(attributes)}",
        )
        return ctx

    def emit_event(
        self,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Emit an event as a log entry."""
        logger.log(
            self.log_level,
            f"[EVENT] {event_type} project={self.project_id} "
            f"data={_format_attrs(data)}",
        )

    def emit_metric(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
    ) -> None:
        """Emit a metric as a log entry."""
        labels_str = ",".join(f"{k}={v}" for k, v in labels.items())
        logger.log(
            self.log_level,
            f"[METRIC] {name}={value} project={self.project_id} {labels_str}",
        )

    def emit_insight(
        self,
        insight_type: str,
        summary: str,
        confidence: float = 1.0,
        **context: Any,
    ) -> None:
        """Emit an insight as a log entry."""
        logger.log(
            self.log_level,
            f"[INSIGHT] {insight_type}: {summary} confidence={confidence:.0%} "
            f"project={self.project_id} context={_format_attrs(context)}",
        )


# ============================================================================
# HeuristicSizeEstimator
# ============================================================================


class HeuristicSizeEstimator:
    """
    Size estimator using heuristic rules.

    Estimates output size based on task description patterns
    and historical averages. No LLM calls required.

    Example:
        estimator = HeuristicSizeEstimator()
        estimate = estimator.estimate(
            task="Implement a rate limiter",
            inputs={"target_files": ["rate_limiter.py"]}
        )
        print(f"Estimated lines: {estimate.lines}")
    """

    # Pattern -> (base_lines, complexity_factor)
    TASK_PATTERNS = {
        r"implement.*class": (80, 1.2),
        r"add.*test": (50, 0.8),
        r"create.*api": (120, 1.5),
        r"refactor": (60, 1.0),
        r"fix.*bug": (30, 0.7),
        r"add.*feature": (100, 1.3),
        r"integrate": (90, 1.4),
        r"migrate": (150, 1.6),
    }

    # Base assumptions
    DEFAULT_LINES = 75
    TOKENS_PER_LINE = 8
    CONFIDENCE_BASE = 0.6

    def __init__(self):
        """Initialize the heuristic estimator."""
        pass

    def estimate(
        self,
        task: str,
        inputs: Dict[str, Any],
    ) -> SizeEstimate:
        """
        Estimate output size using heuristics.

        Args:
            task: Task description
            inputs: Additional context (target_files, required_exports, etc.)

        Returns:
            SizeEstimate based on pattern matching
        """
        task_lower = task.lower()
        base_lines = self.DEFAULT_LINES
        complexity_factor = 1.0
        matched_patterns: List[str] = []

        # Match task against patterns
        for pattern, (lines, factor) in self.TASK_PATTERNS.items():
            if re.search(pattern, task_lower):
                base_lines = max(base_lines, lines)
                complexity_factor = max(complexity_factor, factor)
                matched_patterns.append(pattern)

        # Adjust for number of target files
        target_files = inputs.get("target_files", [])
        if len(target_files) > 1:
            complexity_factor *= 1.0 + (len(target_files) - 1) * 0.3

        # Adjust for required exports
        required_exports = inputs.get("required_exports", [])
        if required_exports:
            base_lines += len(required_exports) * 15

        # Calculate final estimates
        estimated_lines = int(base_lines * complexity_factor)
        estimated_tokens = estimated_lines * self.TOKENS_PER_LINE

        # Determine complexity category
        if estimated_lines < 50:
            complexity = "low"
        elif estimated_lines < 150:
            complexity = "medium"
        else:
            complexity = "high"

        # Calculate confidence (lower for larger estimates)
        confidence = self.CONFIDENCE_BASE
        if matched_patterns:
            confidence += 0.1 * min(len(matched_patterns), 3)
        if estimated_lines > 200:
            confidence -= 0.1
        confidence = max(0.3, min(0.9, confidence))

        reasoning = (
            f"Matched patterns: {matched_patterns or ['none']}. "
            f"Base lines: {base_lines}, complexity factor: {complexity_factor:.1f}. "
            f"Target files: {len(target_files)}, required exports: {len(required_exports)}."
        )

        return SizeEstimate(
            lines=estimated_lines,
            tokens=estimated_tokens,
            complexity=complexity,
            confidence=confidence,
            reasoning=reasoning,
        )


# ============================================================================
# SimpleMergeStrategy
# ============================================================================


class SimpleMergeStrategy:
    """
    Simple merge strategy that overwrites target files.

    This is the safest default when AST-based merging is not available.
    Creates a backup of existing files before overwriting.

    Example:
        merger = SimpleMergeStrategy()
        if merger.can_merge(source, target):
            result = merger.merge(source, target)
            if result.status == MergeStatus.SUCCESS:
                print(f"Merged, backup at {result.backup_path}")
    """

    def __init__(self, backup_suffix: str = ".backup"):
        """
        Initialize the simple merge strategy.

        Args:
            backup_suffix: Suffix for backup files
        """
        self.backup_suffix = backup_suffix

    def can_merge(
        self,
        source: Path,
        target: Path,
    ) -> bool:
        """Check if files can be merged (always True for simple strategy)."""
        # Simple strategy can always handle files
        if not source.exists():
            return False
        return True

    def merge(
        self,
        source: Path,
        target: Path,
        backup: bool = True,
    ) -> MergeResult:
        """
        Merge by overwriting target with source.

        Args:
            source: Path to generated file
            target: Path to target file
            backup: Whether to create a backup

        Returns:
            MergeResult with status
        """
        try:
            # Check source exists
            if not source.exists():
                return MergeResult(
                    status=MergeStatus.ERROR,
                    error=f"Source file does not exist: {source}",
                )

            # Read source content
            source_content = source.read_text(encoding="utf-8")

            # Create backup if target exists
            backup_path: Optional[Path] = None
            if target.exists() and backup:
                backup_path = target.with_suffix(target.suffix + self.backup_suffix)
                shutil.copy2(target, backup_path)
                logger.debug(f"Created backup: {backup_path}")

            # Ensure target directory exists
            target.parent.mkdir(parents=True, exist_ok=True)

            # Write content to target
            target.write_text(source_content, encoding="utf-8")

            return MergeResult(
                status=MergeStatus.SUCCESS,
                merged_content=source_content,
                backup_path=backup_path,
            )

        except Exception as e:
            return MergeResult(
                status=MergeStatus.ERROR,
                error=str(e),
            )


# ============================================================================
# Helper Functions
# ============================================================================


def _format_attrs(attrs: Dict[str, Any], max_len: int = 200) -> str:
    """Format attributes dict for logging."""
    items = []
    total_len = 0
    for k, v in attrs.items():
        item = f"{k}={_truncate(str(v), 50)}"
        if total_len + len(item) > max_len:
            items.append("...")
            break
        items.append(item)
        total_len += len(item)
    return "{" + ", ".join(items) + "}"


def _truncate(s: str, max_len: int) -> str:
    """Truncate string with ellipsis."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."
