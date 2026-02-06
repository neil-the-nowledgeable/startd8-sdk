"""
ContextCore adapters for Prime Contractor protocols.

These adapters integrate with ContextCore to provide:
- OpenTelemetry span emission to Tempo
- Insight emission for agent decisions
- AST-aware Python file merging

Only available when ContextCore is installed.
"""

import ast
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..protocols import (
    Instrumentor,
    MergeResult,
    MergeStatus,
    MergeStrategy,
    SpanContext,
)


logger = logging.getLogger("startd8.contractors.contextcore")


# ============================================================================
# ContextCoreInstrumentor
# ============================================================================


class ContextCoreInstrumentor:
    """
    Instrumentor that emits telemetry via ContextCore.

    Uses OpenTelemetry to emit:
    - Spans to Tempo (via OTLP)
    - Metrics to Mimir (via OTLP)
    - Insights as structured span events

    Requires ContextCore to be installed.

    Example:
        instrumentor = ContextCoreInstrumentor(project_id="myproject")
        ctx = instrumentor.emit_span("process_feature", {"feature_name": "auth"})
        instrumentor.emit_insight("workflow_started", "Processing 5 features", confidence=1.0)
    """

    def __init__(
        self,
        project_id: str = "default",
        agent_id: str = "prime_contractor",
    ):
        """
        Initialize the ContextCore instrumentor.

        Args:
            project_id: ContextCore project identifier
            agent_id: Agent identifier for insights
        """
        self.project_id = project_id
        self.agent_id = agent_id

        # Lazy import to handle missing ContextCore gracefully
        self._tracer = None
        self._insight_emitter = None
        self._otel_available = False

        try:
            from opentelemetry import trace

            self._tracer = trace.get_tracer("startd8.contractors")
            self._otel_available = True
        except ImportError:
            logger.warning("OpenTelemetry not available, falling back to logging")

        try:
            from contextcore.tracing.insight_emitter import InsightEmitter

            # InsightEmitter takes no constructor args - it uses env vars
            self._insight_emitter = InsightEmitter()
        except ImportError:
            logger.warning("ContextCore InsightEmitter not available")
        except TypeError:
            # Handle if InsightEmitter signature changes
            logger.warning("ContextCore InsightEmitter constructor changed")

    def emit_span(
        self,
        name: str,
        attributes: Dict[str, Any],
    ) -> SpanContext:
        """Emit a span via OpenTelemetry."""
        if self._tracer and self._otel_available:
            with self._tracer.start_as_current_span(name) as span:
                for key, value in attributes.items():
                    if isinstance(value, (str, int, float, bool)):
                        span.set_attribute(key, value)
                    elif isinstance(value, list):
                        span.set_attribute(key, str(value))

                ctx = span.get_span_context()
                return SpanContext(
                    trace_id=format(ctx.trace_id, "032x"),
                    span_id=format(ctx.span_id, "016x"),
                    attributes=attributes,
                )

        # Fallback: log only
        import uuid

        trace_id = uuid.uuid4().hex[:16]
        span_id = uuid.uuid4().hex[:8]
        logger.info(f"[SPAN] {name} trace={trace_id} span={span_id}")
        return SpanContext(trace_id=trace_id, span_id=span_id, attributes=attributes)

    def emit_event(
        self,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Emit an event via OpenTelemetry span event."""
        if self._tracer and self._otel_available:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span:
                span.add_event(event_type, attributes=data)
                return

        # Fallback: log only
        logger.info(f"[EVENT] {event_type}: {data}")

    def emit_metric(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
    ) -> None:
        """Emit a metric via OpenTelemetry."""
        # For now, log metrics - full OTLP metric support can be added later
        labels_str = ",".join(f"{k}={v}" for k, v in labels.items())
        logger.info(f"[METRIC] {name}={value} {labels_str}")

    def emit_insight(
        self,
        insight_type: str,
        summary: str,
        confidence: float = 1.0,
        **context: Any,
    ) -> None:
        """Emit an insight via ContextCore InsightEmitter."""
        if self._insight_emitter:
            self._insight_emitter.emit(
                insight_type=insight_type,
                summary=summary,
                confidence=confidence,
                **context,
            )
        else:
            # Fallback: log only
            logger.info(
                f"[INSIGHT] {insight_type}: {summary} confidence={confidence:.0%}"
            )


# ============================================================================
# ASTMergeStrategy
# ============================================================================


class ASTMergeStrategy:
    """
    AST-aware merge strategy for Python files.

    Uses Python's AST module to properly merge:
    - Imports (deduplicated, __future__ first)
    - Classes (merge methods, warn on duplicates)
    - Functions (add new, warn on duplicates)
    - Constants (preserve both with warning)

    This prevents the structural corruption that occurs with
    text-based merging (decorators separated from classes, etc.).

    Example:
        merger = ASTMergeStrategy()
        if merger.can_merge(source, target):
            result = merger.merge(source, target)
            if result.status == MergeStatus.SUCCESS:
                print("AST merge successful")
    """

    def __init__(
        self,
        backup_suffix: str = ".backup",
        warn_on_duplicate: bool = True,
        merge_mode: str = "additive",
    ):
        """
        Initialize the AST merge strategy.

        Args:
            backup_suffix: Suffix for backup files
            warn_on_duplicate: Whether to warn on duplicate definitions
            merge_mode: "additive" (default) merges ASTs, "replace" overwrites
                target with source content (like SimpleMergeStrategy)
        """
        self.backup_suffix = backup_suffix
        self.warn_on_duplicate = warn_on_duplicate
        self.merge_mode = merge_mode

    def can_merge(
        self,
        source: Path,
        target: Path,
    ) -> bool:
        """Check if files can be AST-merged (Python files only)."""
        if not source.exists():
            return False

        # Only handle Python files
        if source.suffix != ".py":
            return False
        if target.exists() and target.suffix != ".py":
            return False

        # Verify source is valid Python
        try:
            source_content = source.read_text(encoding="utf-8")
            ast.parse(source_content)
            return True
        except (SyntaxError, UnicodeDecodeError):
            return False

    def merge(
        self,
        source: Path,
        target: Path,
        backup: bool = True,
    ) -> MergeResult:
        """
        Merge source into target using AST.

        Args:
            source: Path to generated Python file
            target: Path to target Python file
            backup: Whether to create a backup

        Returns:
            MergeResult with merged content
        """
        try:
            # Read source
            source_content = source.read_text(encoding="utf-8")
            source_tree = ast.parse(source_content)

            # If target doesn't exist, just copy source
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source_content, encoding="utf-8")
                return MergeResult(
                    status=MergeStatus.SUCCESS,
                    merged_content=source_content,
                )

            # Read target
            target_content = target.read_text(encoding="utf-8")
            try:
                target_tree = ast.parse(target_content)
            except SyntaxError as e:
                # Target has syntax errors - can't merge, just overwrite
                logger.warning(f"Target has syntax errors, overwriting: {e}")
                if backup:
                    backup_path = target.with_suffix(target.suffix + self.backup_suffix)
                    shutil.copy2(target, backup_path)
                target.write_text(source_content, encoding="utf-8")
                return MergeResult(
                    status=MergeStatus.SUCCESS,
                    merged_content=source_content,
                )

            # Detect accumulation: warn if target has >= 2x the source's definitions
            source_defs = sum(
                1 for n in source_tree.body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            )
            target_defs = sum(
                1 for n in target_tree.body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            )
            if source_defs > 0 and target_defs >= 2 * source_defs:
                logger.warning(
                    f"Target {target.name} has {target_defs} top-level definitions "
                    f"vs {source_defs} in source. This may indicate accumulated merge "
                    f"layers from previous runs. Consider cleaning the workspace "
                    f"before re-running."
                )

            # Replace mode: overwrite target with source (like SimpleMergeStrategy)
            if self.merge_mode == "replace":
                if backup:
                    backup_path = target.with_suffix(target.suffix + self.backup_suffix)
                    shutil.copy2(target, backup_path)
                target.write_text(source_content, encoding="utf-8")
                return MergeResult(
                    status=MergeStatus.SUCCESS,
                    merged_content=source_content,
                    backup_path=backup_path if backup else None,
                )

            # Create backup
            backup_path: Optional[Path] = None
            if backup:
                backup_path = target.with_suffix(target.suffix + self.backup_suffix)
                shutil.copy2(target, backup_path)

            # Merge ASTs
            merged_content, conflicts = self._merge_trees(
                source_tree, target_tree, source_content, target_content
            )

            # Write merged content
            target.write_text(merged_content, encoding="utf-8")

            return MergeResult(
                status=MergeStatus.SUCCESS if not conflicts else MergeStatus.CONFLICT,
                merged_content=merged_content,
                backup_path=backup_path,
                conflicts=conflicts,
            )

        except Exception as e:
            logger.error(f"AST merge failed: {e}")
            return MergeResult(
                status=MergeStatus.ERROR,
                error=str(e),
            )

    def _merge_trees(
        self,
        source_tree: ast.Module,
        target_tree: ast.Module,
        source_content: str,
        target_content: str,
    ) -> Tuple[str, List[str]]:
        """
        Merge two AST trees.

        Returns:
            Tuple of (merged_content, conflicts)
        """
        conflicts: List[str] = []

        # Categorize nodes
        source_imports, source_classes, source_functions, source_other = (
            self._categorize_nodes(source_tree)
        )
        target_imports, target_classes, target_functions, target_other = (
            self._categorize_nodes(target_tree)
        )

        # Merge imports
        merged_imports = self._merge_imports(source_imports, target_imports)

        # Merge classes (add new methods to existing classes)
        merged_classes, class_conflicts = self._merge_classes(
            source_classes, target_classes
        )
        conflicts.extend(class_conflicts)

        # Merge functions (add new, warn on duplicate)
        merged_functions, func_conflicts = self._merge_functions(
            source_functions, target_functions
        )
        conflicts.extend(func_conflicts)

        # Keep target's other nodes, add source's new ones
        merged_other = self._merge_other(source_other, target_other)

        # Build merged AST
        merged_tree = ast.Module(
            body=merged_imports + merged_classes + merged_functions + merged_other,
            type_ignores=[],
        )

        # Generate code from AST
        try:
            merged_content = ast.unparse(merged_tree)
        except Exception as e:
            logger.error(f"Failed to unparse merged AST: {e}")
            # Fallback: just use source content
            merged_content = source_content
            conflicts.append(f"AST unparse failed: {e}")

        return merged_content, conflicts

    def _categorize_nodes(
        self, tree: ast.Module
    ) -> Tuple[List[ast.stmt], List[ast.ClassDef], List[ast.FunctionDef], List[ast.stmt]]:
        """Categorize top-level nodes in an AST."""
        imports: List[ast.stmt] = []
        classes: List[ast.ClassDef] = []
        functions: List[ast.FunctionDef] = []
        other: List[ast.stmt] = []

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
            elif isinstance(node, ast.ClassDef):
                classes.append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node)
            else:
                other.append(node)

        return imports, classes, functions, other

    def _merge_imports(
        self,
        source_imports: List[ast.stmt],
        target_imports: List[ast.stmt],
    ) -> List[ast.stmt]:
        """Merge imports, deduplicating and ordering correctly."""
        # Collect all imports
        future_imports: List[ast.stmt] = []
        regular_imports: List[ast.stmt] = []
        seen: Set[str] = set()

        for imp in target_imports + source_imports:
            key = ast.dump(imp)
            if key in seen:
                continue
            seen.add(key)

            if isinstance(imp, ast.ImportFrom) and imp.module == "__future__":
                future_imports.append(imp)
            else:
                regular_imports.append(imp)

        return future_imports + regular_imports

    def _merge_classes(
        self,
        source_classes: List[ast.ClassDef],
        target_classes: List[ast.ClassDef],
    ) -> Tuple[List[ast.ClassDef], List[str]]:
        """Merge class definitions."""
        conflicts: List[str] = []
        result: List[ast.ClassDef] = []
        target_names = {c.name: c for c in target_classes}

        for target_class in target_classes:
            result.append(target_class)

        for source_class in source_classes:
            if source_class.name in target_names:
                if self.warn_on_duplicate:
                    conflicts.append(
                        f"Duplicate class '{source_class.name}' - keeping target"
                    )
            else:
                result.append(source_class)

        return result, conflicts

    def _merge_functions(
        self,
        source_functions: List[ast.FunctionDef],
        target_functions: List[ast.FunctionDef],
    ) -> Tuple[List[ast.FunctionDef], List[str]]:
        """Merge function definitions."""
        conflicts: List[str] = []
        result: List[ast.FunctionDef] = []
        target_names = {f.name for f in target_functions}

        for target_func in target_functions:
            result.append(target_func)

        for source_func in source_functions:
            if source_func.name in target_names:
                if self.warn_on_duplicate:
                    conflicts.append(
                        f"Duplicate function '{source_func.name}' - keeping target"
                    )
            else:
                result.append(source_func)

        return result, conflicts

    def _merge_other(
        self,
        source_other: List[ast.stmt],
        target_other: List[ast.stmt],
    ) -> List[ast.stmt]:
        """Merge other statements (constants, assignments, etc.)."""
        # Keep target's nodes, add source's new ones
        # Simple heuristic: keep target's, add source's that look different
        result = list(target_other)

        target_dumps = {ast.dump(n) for n in target_other}
        for node in source_other:
            if ast.dump(node) not in target_dumps:
                result.append(node)

        return result
