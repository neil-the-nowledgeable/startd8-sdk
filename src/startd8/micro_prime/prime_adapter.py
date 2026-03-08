"""Prime Contractor CodeGenerator Adapter (REQ-MP-504).

Implements the ``CodeGenerator`` protocol, wrapping the Micro Prime engine
for use in PrimeContractorWorkflow. Elements that can't be handled locally
are delegated to a fallback ``CodeGenerator``.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import urlopen

from startd8.agents.base import BaseAgent
from startd8.contractors.protocols import (
    CodeGenerator,
    DRAFT_MODEL_CLAUDE_HAIKU,
    GenerationResult,
)
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.micro_prime.classifier import classify_element
from startd8.micro_prime.context import MicroPrimeContext
from startd8.micro_prime.engine import MicroPrimeEngine, _CODE_GEN_SYSTEM_PROMPT
from startd8.micro_prime.models import (
    EscalationReason,
    FileResult,
    MicroPrimeConfig,
    TierClassification,
)
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)

# OTel metrics (REQ-MP-705) — optional dependency
try:
    from opentelemetry import metrics as otel_metrics
    _meter = otel_metrics.get_meter("startd8.micro_prime")
    _elements_local_counter = _meter.create_counter(
        "micro_prime.elements_local",
        description="Elements processed locally by Micro Prime",
    )
    _elements_escalated_counter = _meter.create_counter(
        "micro_prime.elements_escalated",
        description="Elements escalated to fallback generator",
    )
    _template_hits_counter = _meter.create_counter(
        "micro_prime.template_hits",
        description="Elements resolved by template registry",
    )
except ImportError:
    _elements_local_counter = None
    _elements_escalated_counter = None
    _template_hits_counter = None


# Size-regression threshold: if filled skeleton is below this ratio of the
# existing target file (by semantic line count), escalate to the fallback
# generator.  Uses semantic lines (non-blank, non-comment, non-docstring)
# to avoid penalising lean Ollama output against verbose cloud-generated
# files that have rich docstrings and inline comments.
_SIZE_REGRESSION_THRESHOLD = 0.55
_MIN_EXISTING_LINES = 50

# ElementKind values that map to ast.FunctionDef / ast.AsyncFunctionDef
# rather than ast.ClassDef.  Used by _extract_element_from_generated and
# _escalate_elements_to_cloud to translate manifest kinds to AST node types.
_FUNCTION_LIKE_KINDS = frozenset({
    "function", "async_function", "method", "async_method", "property",
})


def _serialize_file_result(fr: Any) -> dict:
    """Serialize a FileResult dataclass to dict, truncating code to avoid bloat."""
    from enum import Enum as _Enum

    result = dataclasses.asdict(fr)
    for er in result.get("element_results", []):
        code = er.get("code")
        if code and len(code) > 500:
            er["code"] = code[:500] + "... [truncated]"
        # Normalize enum values (dataclasses.asdict uses str() on str(Enum))
        for key in ("tier", "reason"):
            val = er.get(key)
            if val and isinstance(val, str) and "." in val:
                er[key] = val.rsplit(".", 1)[-1].lower()
        esc = er.get("escalation")
        if isinstance(esc, dict):
            reason = esc.get("reason", "")
            if isinstance(reason, str) and "." in reason:
                esc["reason"] = reason.rsplit(".", 1)[-1].lower()
            ctx = esc.get("context")
            if isinstance(ctx, dict):
                raw_output = ctx.get("raw_output")
                if raw_output and len(raw_output) > 500:
                    ctx["raw_output"] = raw_output[:500] + "... [truncated]"
                repaired = ctx.get("repaired_code")
                if repaired and len(repaired) > 500:
                    ctx["repaired_code"] = repaired[:500] + "... [truncated]"
    # Drop filled_skeleton from serialization — too large for metadata
    result.pop("filled_skeleton", None)
    return result


def _sanitize_for_json(value: Any) -> Any:
    """Recursively convert Pydantic models to dicts for JSON compatibility."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    return value


def _extract_element_from_generated(
    source: str, element_name: str, element_kind: str,
) -> Optional[str]:
    """Extract a named function/class from *source* using AST.

    Returns the source lines for the matching element (including the def/class
    line), suitable for feeding into ``splice_body_into_skeleton()``.  Returns
    ``None`` if the element cannot be found or *source* fails to parse.

    Args:
        source: Complete Python source text (e.g. fallback-generated file).
        element_name: Name of the function or class to extract.
        element_kind: ``"class"`` for ClassDef, or any value in
            ``_FUNCTION_LIKE_KINDS`` for FunctionDef/AsyncFunctionDef.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    target_types: tuple[type, ...] = (
        (ast.ClassDef,) if element_kind == "class"
        else (ast.FunctionDef, ast.AsyncFunctionDef)
    )

    # ast.walk visits in no guaranteed order.  This is acceptable because
    # fallback-generated files are typically flat (no duplicate names).
    source_lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, target_types) and node.name == element_name:
            start = node.lineno - 1
            end = node.end_lineno or len(source_lines)
            return "\n".join(source_lines[start:end])

    return None


_SKELETON_MARKER = "# [STARTD8-SKELETON]"


def _semantic_line_count(source: str) -> int:
    """Count semantic lines in Python source (non-blank, non-comment, non-docstring).

    Normalises the comparison between lean Ollama-assembled code and verbose
    cloud-generated code by ignoring differences in docstring/comment density.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback to raw non-blank lines if source doesn't parse
        return sum(1 for line in source.splitlines() if line.strip())

    # Collect line ranges occupied by docstrings (module, class, function)
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                ds = node.body[0]
                for ln in range(ds.lineno, (ds.end_lineno or ds.lineno) + 1):
                    docstring_lines.add(ln)

    count = 0
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if i in docstring_lines:
            continue
        count += 1
    return count


def _detect_assembly_defect(content: str, file_path: str) -> Optional[str]:
    """Return a human-readable defect description, or ``None`` if clean.

    Checks for three classes of assembly defect:
    1. Remaining ``raise NotImplementedError`` stubs
    2. ``[STARTD8-SKELETON]`` markers (skeleton was never fully assembled)
    3. Nested duplicate function definitions (Ollama over-generation artifact)
    """
    if "raise NotImplementedError" in content:
        return "remaining `raise NotImplementedError` stubs"
    if _SKELETON_MARKER in content:
        return "`[STARTD8-SKELETON]` marker still present"
    # Nested duplicate: a function whose body contains a def with the same name
    if file_path.endswith(".py"):
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return "file does not parse (SyntaxError)"
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if (
                        child is not node
                        and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and child.name == node.name
                    ):
                        return (
                            f"nested duplicate function `{node.name}` "
                            f"(Ollama over-generation)"
                        )
    return None


class MicroPrimeCodeGenerator:
    """``CodeGenerator`` implementation using the Micro Prime engine.

    Processes TRIVIAL and SIMPLE elements locally, delegating MODERATE and
    COMPLEX elements to a fallback ``CodeGenerator`` (typically the
    LeadContractor pattern).

    Args:
        config: Micro Prime engine configuration.
        fallback: Fallback code generator for elements beyond local capability.
        manifest: Forward manifest for element metadata.
        skeletons: Dict of file path -> skeleton content.
        output_dir: Directory for writing generated files.  Defaults to cwd.
        cloud_agent_spec: Optional agent spec (e.g. ``"anthropic:claude-haiku-4-5-20251001"``)
            for direct per-element cloud escalation.  When set, escalated elements
            use a single LLM call instead of the full fallback pipeline.  Falls back
            to ``fallback.drafter_agent`` or ``DRAFT_MODEL_CLAUDE_HAIKU``.
    """

    def __init__(
        self,
        config: Optional[MicroPrimeConfig] = None,
        fallback: Optional[CodeGenerator] = None,
        manifest: Optional[ForwardManifest] = None,
        skeletons: Optional[dict[str, str]] = None,
        output_dir: Optional[Path] = None,
        cloud_agent_spec: Optional[str] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._fallback = fallback
        self._manifest = manifest
        self._skeletons = skeletons or {}
        self._output_dir = output_dir or Path(".")
        self._engine = MicroPrimeEngine(config=self._config)
        self._ollama_available: Optional[bool] = None
        self._cloud_agent_spec = cloud_agent_spec
        self._cloud_agent: Optional[BaseAgent] = None

    def generate(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """Generate code for the given task.

        Attempts local generation first. For elements that require cloud
        processing, delegates to the fallback generator if available.

        Args:
            task: Description of what to implement.
            context: Additional context (existing code, requirements, etc.).
            target_files: Expected output file paths.

        Returns:
            GenerationResult with success status and generated file paths.
        """
        manifest = context.get("manifest") or self._manifest
        skeletons = context.get("skeletons") or self._skeletons

        # REQ-MP-702: Auto-generate skeletons from manifest when missing.
        # Prime Contractor has no SCAFFOLD phase, so stubs are produced on
        # demand using DeterministicFileAssembler.
        if manifest is not None and not skeletons:
            skeletons = self._generate_skeletons(manifest, target_files)

        if manifest is None:
            logger.warning(
                "MicroPrimeCodeGenerator: no manifest, delegating to fallback",
            )
            return self._delegate_to_fallback(task, context, target_files)

        # REQ-MP-711: Ollama availability guard — check once per instance
        ollama_ok = self._check_ollama_available()

        if self._config.dry_run:
            return self._dry_run_classify(manifest, skeletons, target_files, ollama_ok)

        if not ollama_ok:
            logger.info(
                "Ollama unavailable — SIMPLE elements will be escalated to fallback",
            )

        mp_context = MicroPrimeContext.from_prime(
            context, manifest, target_files, ollama_ok,
        )

        # Existing target files for size-regression escalation guard
        existing_files: Dict[str, str] = mp_context.existing_file_contents

        # Process target files through the engine
        all_file_results: list = []
        file_results_by_path: Dict[str, Any] = {}
        generated_files: list[Path] = []
        written_file_paths: set[str] = set()  # relative paths that were successfully written
        total_input = 0
        total_output = 0
        escalated_files: list[str] = []
        local_element_count = 0
        template_count = 0
        ollama_count = 0
        escalated_element_count = 0
        decomposed_count = 0
        decomposition_failure_count = 0

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            skeleton = skeletons.get(file_path, "")

            if file_spec is None or not skeleton:
                escalated_files.append(file_path)
                continue

            # REQ-DDS-002: Thread design_doc_sections to engine
            _dds = context.get("design_doc_sections") or []
            # Mottainai Rule 2: Forward task description to element prompts
            _task_desc = task or None
            file_result = self._engine.process_file_with_context(
                file_spec, skeleton, mp_context,
                design_doc_sections=_dds if _dds else None,
                task_description=_task_desc,
            )
            all_file_results.append(file_result)
            file_results_by_path[file_path] = file_result

            if file_result.filled_skeleton:
                # Size-regression escalation guard: if the filled skeleton is
                # significantly smaller than the existing target file, escalate
                # to the fallback generator instead of writing a tiny skeleton.
                # Uses semantic line count (non-blank, non-comment) to avoid
                # penalising lean Ollama output against verbose cloud-generated
                # files with rich docstrings and inline comments.
                existing_content = existing_files.get(file_path, "")
                if existing_content:
                    filled_sem = _semantic_line_count(file_result.filled_skeleton)
                    existing_sem = _semantic_line_count(existing_content)
                    existing_raw = existing_content.count("\n") + 1
                    ratio = filled_sem / existing_sem if existing_sem > 0 else 1.0
                    if ratio < _SIZE_REGRESSION_THRESHOLD and existing_raw >= _MIN_EXISTING_LINES:
                        logger.warning(
                            "Micro Prime size-regression guard: %s has %d semantic "
                            "lines vs %d existing (%.0f%%) — escalating to fallback",
                            file_path, filled_sem, existing_sem, ratio * 100,
                        )
                        escalated_files.append(file_path)
                        continue

                # REQ-MP-703: Write filled skeleton to disk
                # Strip the skeleton sentinel — it's a build marker, not output.
                final_content = file_result.filled_skeleton.replace(
                    _SKELETON_MARKER + "\n", "",
                ).replace(_SKELETON_MARKER, "")

                # Phase 1, Step 9: ast.parse syntax gate AFTER sentinel strip.
                # Validates the content that will actually be written to disk.
                try:
                    ast.parse(final_content)
                except SyntaxError as syn_err:
                    logger.warning(
                        "Micro Prime ast.parse gate failed for %s: %s — skipping write",
                        file_path, syn_err,
                    )
                    escalated_files.append(file_path)
                    continue
                output_path = self._output_dir / file_path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(final_content, encoding="utf-8")
                generated_files.append(output_path)
                written_file_paths.add(file_path)
                logger.info(
                    "Micro Prime wrote %s (%d lines, %d elements filled)",
                    file_path,
                    final_content.count("\n") + 1,
                    sum(1 for er in file_result.element_results if er.success),
                )

            # Track tokens and element counts
            for er in file_result.element_results:
                total_input += er.input_tokens
                total_output += er.output_tokens
                if er.success:
                    local_element_count += 1
                    if er.template_used:
                        template_count += 1
                    else:
                        ollama_count += 1
                if er.escalation is not None:
                    escalated_element_count += 1
                    if er.escalation.reason == EscalationReason.DECOMPOSITION_FAILED:
                        decomposition_failure_count += 1
                if er.decomposition_metadata is not None:
                    decomposed_count += 1

            # OTel metrics (REQ-MP-705)
            if _elements_local_counter is not None:
                for er in file_result.element_results:
                    if er.success:
                        _elements_local_counter.add(
                            1, {"tier": er.tier.value, "file_path": file_path},
                        )
                        if er.template_used and _template_hits_counter is not None:
                            _template_hits_counter.add(
                                1, {"file_path": file_path},
                            )
                    if er.escalation is not None and _elements_escalated_counter is not None:
                        _elements_escalated_counter.add(
                            1,
                            {"reason": er.escalation.reason.value, "file_path": file_path},
                        )

            # Element-level escalation: only delegate the whole file to
            # fallback when ZERO elements succeeded locally.  When some
            # elements were filled successfully, keep the partial skeleton
            # (Mottainai — don't waste locally-produced assets).
            if file_result.escalated_count > 0 and file_result.success_count == 0:
                escalated_files.append(file_path)

        local_file_count = len(generated_files)

        partial_files = sum(
            1 for fp in target_files
            if fp not in escalated_files and fp not in written_file_paths
        )
        logger.info(
            "Micro Prime: %d elements local (%d files), %d escalated "
            "(%d files to fallback, %d partial kept)",
            local_element_count,
            local_file_count,
            escalated_element_count,
            len(escalated_files),
            partial_files,
        )

        # Element-level escalation: for files where SOME elements succeeded
        # but others were escalated, delegate escalated elements to cloud
        # and splice results into the partial skeleton (REQ-MP-505/512).
        element_escalation_cost = 0.0
        element_escalation_count = 0
        element_escalation_attempt_cost = 0.0
        element_escalation_attempt_count = 0
        partial_escalation_candidates = [
            fp for fp in target_files
            if fp not in escalated_files
            and (fr := file_results_by_path.get(fp))
            and fr.escalated_count > 0 and fr.success_count > 0
        ]
        cloud_escalation_available = self._cloud_agent_spec is not None
        element_escalation_allowed = bool(ollama_ok)
        if partial_escalation_candidates and self._fallback is not None and not cloud_escalation_available:
            for fp in partial_escalation_candidates:
                if fp not in escalated_files:
                    escalated_files.append(fp)
            logger.info(
                "Element-level escalation disabled — delegating %d file(s) to fallback",
                len(partial_escalation_candidates),
            )
        if partial_escalation_candidates and not element_escalation_allowed:
            for fp in partial_escalation_candidates:
                if fp not in escalated_files:
                    escalated_files.append(fp)
            logger.info(
                "Ollama unavailable — skipping element-level escalation for %d file(s)",
                len(partial_escalation_candidates),
            )
        if partial_escalation_candidates and not cloud_escalation_available:
            logger.debug(
                "Skipping element-level escalation for %d file(s) — no cloud agent configured",
                len(partial_escalation_candidates),
            )
        if cloud_escalation_available and element_escalation_allowed:
            for fp in partial_escalation_candidates:
                fr = file_results_by_path[fp]
                try:
                    esc_result = self._escalate_elements_to_cloud(
                        fp, fr, task, context, manifest,
                    )
                    if esc_result:
                        total_input += esc_result.input_tokens
                        total_output += esc_result.output_tokens
                        element_escalation_attempt_cost += esc_result.cost_usd
                        element_escalation_attempt_count += 1
                        if esc_result.success:
                            element_escalation_cost += esc_result.cost_usd
                            element_escalation_count += 1
                except (OSError, ValueError, RuntimeError, TypeError):
                    # Narrow catch per [SDK Leg 11 #28] — let
                    # KeyboardInterrupt / SystemExit propagate.
                    logger.warning(
                        "Element-level cloud escalation failed for %s, "
                        "keeping partial skeleton",
                        fp, exc_info=True,
                    )

        # Post-generation file-level repair (lint + import completion)
        if generated_files:
            self._run_post_generation_repair(generated_files)

        # Post-assembly file-level validation: detect files that are
        # structurally incomplete even when all elements pass individually.
        # Checks: (1) remaining `raise NotImplementedError` stubs,
        # (2) `[STARTD8-SKELETON]` markers, (3) nested duplicate functions.
        # Incomplete files are escalated to fallback or excluded from
        # effective count.
        stub_escalated: list[str] = []
        for file_path in list(written_file_paths):
            fr = file_results_by_path.get(file_path)
            if fr is None or not fr.filled_skeleton or not fr.element_results:
                continue
            output_path = self._output_dir / file_path
            # Re-read from disk in case post-generation repair modified it
            try:
                content = output_path.read_text(encoding="utf-8")
            except OSError:
                continue

            # Check for assembly defects
            defect = _detect_assembly_defect(content, file_path)
            if defect is not None:
                if self._fallback is not None:
                    logger.warning(
                        "Micro Prime file %s has assembly defect: %s "
                        "— escalating to fallback",
                        file_path, defect,
                    )
                    stub_escalated.append(file_path)
                    written_file_paths.discard(file_path)
                    generated_files[:] = [p for p in generated_files if p != output_path]
                    escalated_files.append(file_path)
                    try:
                        output_path.unlink()
                    except OSError:
                        pass
                else:
                    # No fallback available — keep the partial file but
                    # exclude from effective count so success=false.
                    logger.warning(
                        "Micro Prime file %s has assembly defect: %s "
                        "(no fallback available)",
                        file_path, defect,
                    )
                    stub_escalated.append(file_path)

        # Compute effective file count based on element fill rate.
        # Files where <min_element_fill_rate of elements were filled are
        # considered incomplete and excluded from the success check.
        # Files with remaining stubs (stub_escalated) are always excluded.
        effective_file_count = 0
        incomplete_files: list[str] = []
        for file_path in written_file_paths:
            if file_path in stub_escalated:
                incomplete_files.append(file_path)
                continue
            fr = file_results_by_path.get(file_path)
            if fr is None:
                effective_file_count += 1
                continue
            total = len(fr.element_results)
            filled = sum(1 for er in fr.element_results if er.success)
            rate = filled / total if total > 0 else 1.0
            if rate >= self._config.min_element_fill_rate:
                effective_file_count += 1
            else:
                incomplete_files.append(file_path)
                logger.warning(
                    "File %s has low element fill rate: %d/%d (%.0f%%) — marking as incomplete",
                    file_path, filled, total, rate * 100,
                )

        # Mottainai: only delegate files that had escalations to the fallback.
        # Files where all elements were handled locally are kept as-is.
        if escalated_files and self._fallback is not None:
            fallback_context = self._with_escalation_context(
                context, all_file_results,
            )
            fallback_result = self._delegate_to_fallback(
                task, fallback_context, escalated_files,
            )
            generated_files.extend(fallback_result.generated_files)
            total_input += fallback_result.input_tokens
            # The generation is successful if the fallback succeeded AND
            # either there were no locally-handled files, or the ones that
            # were handled locally met the effective fill rate.
            local_files_kept = sum(1 for fp in target_files if fp not in escalated_files)
            local_success = True if local_files_kept == 0 else (effective_file_count > 0)
            
            return GenerationResult(
                success=fallback_result.success and local_success,
                generated_files=generated_files,
                input_tokens=total_input,
                output_tokens=total_output,
                cost_usd=fallback_result.cost_usd + element_escalation_attempt_cost,
                model=f"micro-prime+{fallback_result.model}",
                metadata={
                    "micro_prime_files_written": local_file_count,
                    "effective_file_count": effective_file_count,
                    "incomplete_files": incomplete_files,
                    "fallback_files_delegated": len(escalated_files),
                    "fallback_files_written": len(fallback_result.generated_files),
                    "micro_prime_elements": local_element_count,
                    "micro_prime_template_hits": template_count,
                    "micro_prime_ollama_generations": ollama_count,
                    "fallback_elements": escalated_element_count,
                    "micro_prime_decomposed_count": decomposed_count,
                    "micro_prime_decomposition_failures": decomposition_failure_count,
                    "micro_prime_cost_usd": 0.0,
                    "fallback_cost_usd": fallback_result.cost_usd,
                    "element_escalation_cost_usd": element_escalation_cost,
                    "element_escalation_count": element_escalation_count,
                    "element_escalation_attempt_cost_usd": element_escalation_attempt_cost,
                    "element_escalation_attempt_count": element_escalation_attempt_count,
                    "micro_prime_file_results": [
                        _serialize_file_result(fr) for fr in all_file_results
                    ],
                },
            )

        return GenerationResult(
            success=effective_file_count > 0,
            generated_files=generated_files,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=element_escalation_attempt_cost,
            model=f"{self._config.provider}:{self._config.model}",
            metadata={
                "micro_prime_only": element_escalation_attempt_count == 0,
                "micro_prime_files_written": local_file_count,
                "effective_file_count": effective_file_count,
                "incomplete_files": incomplete_files,
                "micro_prime_elements": local_element_count,
                "micro_prime_template_hits": template_count,
                "micro_prime_ollama_generations": ollama_count,
                "micro_prime_decomposed_count": decomposed_count,
                "micro_prime_decomposition_failures": decomposition_failure_count,
                "micro_prime_cost_usd": 0.0,
                "element_escalation_cost_usd": element_escalation_cost,
                "element_escalation_count": element_escalation_count,
                "element_escalation_attempt_cost_usd": element_escalation_attempt_cost,
                "element_escalation_attempt_count": element_escalation_attempt_count,
                "micro_prime_file_results": [
                    _serialize_file_result(fr) for fr in all_file_results
                ],
            },
        )

    def _with_escalation_context(
        self,
        context: Dict[str, Any],
        file_results: list[FileResult],
    ) -> Dict[str, Any]:
        """Attach micro-prime escalation context for fallback prompts."""
        feedback = self._format_escalation_feedback(file_results)
        if not feedback:
            return context
        merged = dict(context)
        existing = merged.get("last_error") or ""
        if existing:
            merged["last_error"] = f"{existing}\n\n{feedback}"
        else:
            merged["last_error"] = feedback
        return merged

    def _format_escalation_feedback(
        self,
        file_results: list[FileResult],
        max_chars: int = 4000,
    ) -> str:
        """Summarize local failures for cloud fallback (REQ-MP-502)."""
        lines: list[str] = ["Micro Prime local attempt failed for:"]
        count = 0
        for fr in file_results:
            for er in fr.element_results:
                if er.escalation is None:
                    continue
                count += 1
                reason = er.escalation.reason.value
                err = er.escalation.last_error or er.escalation.detail
                lines.append(
                    f"- {er.file_path}:{er.element_name} "
                    f"({reason}) — {err}"
                )
        if count == 0:
            return ""
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [truncated]"
        return text

    def _run_post_generation_repair(self, generated_files: list[Path]) -> int:
        """Run lint + syntax checks and auto-repair generated files.

        Uses the shared repair pipeline (``IntegrationCheckpoint`` +
        ``run_file_repair``) to fix F821/import/syntax errors in generated
        output.  Returns the number of files repaired, or 0 if checks pass
        or repair is unavailable.
        """
        if not generated_files:
            return 0

        try:
            from startd8.contractors.checkpoint import IntegrationCheckpoint
            from startd8.repair.config import RepairConfig
            from startd8.repair.diagnostics import parse_checkpoint_diagnostics
            from startd8.repair.orchestrator import run_file_repair
        except ImportError:
            logger.debug(
                "Repair infrastructure not available, skipping post-generation repair",
            )
            return 0

        try:
            checkpoint = IntegrationCheckpoint(project_root=self._output_dir)
            results = []
            results.append(checkpoint.check_syntax(generated_files))
            results.append(checkpoint.check_lint(generated_files))
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(
                "Post-generation checkpoint failed, skipping repair: %s", exc,
            )
            return 0

        diagnostics = parse_checkpoint_diagnostics(results)
        if not diagnostics:
            logger.debug("Post-generation checks passed — no repair needed")
            return 0

        logger.info(
            "Post-generation repair: %d diagnostic(s) found in %d file(s)",
            len(diagnostics), len(generated_files),
        )

        files_dict = {}
        for fp in generated_files:
            try:
                files_dict[fp] = fp.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Cannot read %s for repair, skipping", fp)

        if not files_dict:
            return 0

        try:
            outcome = run_file_repair(
                files_dict, diagnostics, RepairConfig(), self._output_dir,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("Post-generation repair failed: %s", exc)
            return 0

        repaired_count = 0
        for fp, content in outcome.repaired_files.items():
            try:
                fp.write_text(content, encoding="utf-8")
                repaired_count += 1
            except OSError:
                logger.warning("Cannot write repaired file %s", fp)

        if repaired_count:
            logger.info("Post-generation repair: %d file(s) repaired", repaired_count)
        return repaired_count

    def _dry_run_classify(
        self,
        manifest: ForwardManifest,
        skeletons: dict[str, str],
        target_files: List[str],
        ollama_available: bool,
    ) -> GenerationResult:
        """Run classification on all elements and print a report without generating code.

        Iterates every target file's elements through ``classify_element()`` and
        the template registry, collecting tier counts and per-file summaries.
        Prints a formatted console report and returns a zero-cost result with
        classification metadata.
        """
        base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        model_name = self._config.model
        templates = self._engine._templates if self._config.templates_enabled else None

        per_file: list[dict[str, Any]] = []
        tier_totals = {t: 0 for t in TierClassification}
        total_elements = 0
        total_local = 0
        total_escalated = 0

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            skeleton = skeletons.get(file_path, "")
            if file_spec is None:
                per_file.append({
                    "file": file_path,
                    "skipped": True,
                    "reason": "no file_spec in manifest",
                })
                continue
            if not skeleton:
                per_file.append({
                    "file": file_path,
                    "skipped": True,
                    "reason": "no skeleton generated",
                })
                continue

            skeleton_lines = skeleton.count("\n") + 1
            elements_info: list[dict[str, str]] = []
            file_local = 0
            file_escalated = 0

            for element in file_spec.elements:
                contracts = self._engine._get_element_contracts(
                    element, file_spec, manifest,
                )
                tier, reason = classify_element(
                    element, file_spec, contracts,
                    template_registry=templates,
                    config=self._config,
                )
                tier_totals[tier] += 1
                total_elements += 1

                template_hit = (
                    templates.match(element, file_spec, contracts) is not None
                    if templates else False
                )

                # Decomposition viability for MODERATE elements (REQ-MP-906a, REQ-MP-909)
                decomposable = False
                decompose_strategy = None
                if tier == TierClassification.MODERATE and self._config.decomposition_enabled:
                    decomposable = self._engine._decomposer.can_decompose(
                        element, file_spec, manifest, reason,
                    )
                    if decomposable:
                        # Identify which strategy would handle it
                        for s in self._engine._decomposer._strategies:
                            if s.can_handle(element, file_spec, manifest, reason):
                                decompose_strategy = s.name
                                break

                # Routing: TRIVIAL with template works without Ollama;
                # SIMPLE requires Ollama; MODERATE/COMPLEX always escalate.
                if tier == TierClassification.TRIVIAL and template_hit:
                    file_local += 1
                    total_local += 1
                elif tier in (TierClassification.TRIVIAL, TierClassification.SIMPLE) and ollama_available:
                    file_local += 1
                    total_local += 1
                elif tier == TierClassification.MODERATE and decomposable and ollama_available:
                    file_local += 1
                    total_local += 1
                else:
                    file_escalated += 1
                    total_escalated += 1

                elem_entry: dict[str, Any] = {
                    "name": element.name,
                    "tier": tier.value.upper(),
                    "reason": reason,
                    "template_hit": template_hit,
                }
                if decomposable:
                    elem_entry["decomposable"] = True
                    elem_entry["decompose_strategy"] = decompose_strategy
                elements_info.append(elem_entry)

            per_file.append({
                "file": file_path,
                "element_count": len(file_spec.elements),
                "skeleton_lines": skeleton_lines,
                "elements": elements_info,
                "local": file_local,
                "escalated": file_escalated,
            })

        # Print bypasses log-level filtering — this is a user-facing report.
        report = self._format_dry_run_report(
            per_file, tier_totals, total_elements, total_local,
            ollama_available, model_name, base_url,
        )
        print(report)

        return GenerationResult(
            success=True,
            generated_files=[],
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model="micro-prime-dry-run",
            metadata={
                "dry_run": True,
                "ollama_available": ollama_available,
                "total_elements": total_elements,
                "total_local": total_local,
                "total_escalated": total_escalated,
                "tier_totals": {t.value: c for t, c in tier_totals.items()},
                "per_file": per_file,
            },
        )

    @staticmethod
    def _format_dry_run_report(
        per_file: list[dict[str, Any]],
        tier_totals: dict[TierClassification, int],
        total_elements: int,
        total_local: int,
        ollama_available: bool,
        model_name: str,
        base_url: str,
    ) -> str:
        """Format the dry-run classification report as a box-drawing string."""
        local_pct = (total_local / total_elements * 100) if total_elements else 0
        ollama_status = (
            f"available ({model_name} @ {base_url})"
            if ollama_available
            else f"unavailable ({base_url})"
        )

        lines = [
            "",
            "\u2554" + "\u2550" * 62 + "\u2557",
            "\u2551  Micro Prime \u2014 Dry Run Classification Report" + " " * 17 + "\u2551",
            "\u255a" + "\u2550" * 62 + "\u255d",
            "",
            f"  Ollama: {ollama_status}",
            "",
        ]

        for pf in per_file:
            if pf.get("skipped"):
                lines.append(f"  {pf['file']}  [SKIPPED: {pf['reason']}]")
                lines.append("")
                continue

            lines.append(
                f"  {pf['file']} ({pf['element_count']} elements, "
                f"skeleton: {pf['skeleton_lines']} lines)"
            )
            for el in pf.get("elements", []):
                line = f"    {el['tier']:<10} {el['name']:<35} {el['reason']}"
                if el["template_hit"]:
                    line += "  [template]"
                if el.get("decomposable"):
                    line += f"  [decomposable: {el.get('decompose_strategy', '?')}]"
                lines.append(line)

            decomposable_count = sum(
                1 for el in pf.get("elements", []) if el.get("decomposable")
            )
            summary = f"    -> {pf['local']} local, {pf['escalated']} escalated"
            if decomposable_count:
                summary += f", {decomposable_count} decomposable"
            lines.append(summary)
            lines.append("")

        file_count = sum(1 for p in per_file if not p.get("skipped"))
        lines.append("  " + "-" * 60)
        lines.append(f"  Summary: {file_count} files, {total_elements} elements")
        lines.append(
            f"    TRIVIAL:  {tier_totals[TierClassification.TRIVIAL]:>3}  (template match)"
        )
        lines.append(
            f"    SIMPLE:   {tier_totals[TierClassification.SIMPLE]:>3}  (Ollama local)"
        )
        total_decomposable = sum(
            1 for pf in per_file
            for el in pf.get("elements", [])
            if el.get("decomposable")
        )
        mod_label = "(cloud fallback)"
        if total_decomposable:
            mod_label = f"({total_decomposable} decomposable -> local, rest cloud)"
        lines.append(
            f"    MODERATE: {tier_totals[TierClassification.MODERATE]:>3}  {mod_label}"
        )
        lines.append(
            f"    COMPLEX:  {tier_totals[TierClassification.COMPLEX]:>3}  (cloud fallback)"
        )
        lines.append("")
        lines.append(
            f"  Local generation: {total_local}/{total_elements} elements "
            f"({local_pct:.0f}%)"
        )
        lines.append("")
        return "\n".join(lines)

    def _generate_skeletons(
        self,
        manifest: ForwardManifest,
        target_files: List[str],
    ) -> dict[str, str]:
        """Generate stub skeletons from manifest for target files only.

        Uses ``DeterministicFileAssembler`` to render ``ForwardFileSpec``
        elements into Python source with ``raise NotImplementedError`` stubs.
        Only the current feature's target files are rendered (not the entire
        manifest).  Per-file failures are logged and skipped — they do not
        block other files.

        Returns:
            Dict mapping file path to skeleton source text.
        """
        from startd8.utils.file_assembler import DeterministicFileAssembler

        assembler = DeterministicFileAssembler()
        skeletons: dict[str, str] = {}

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            if file_spec is None:
                logger.debug("No file_spec for %s, skipping skeleton", file_path)
                continue
            try:
                source = assembler.render_file(file_spec)
                skeletons[file_path] = source
                logger.debug(
                    "Generated skeleton for %s (%d lines)",
                    file_path,
                    source.count("\n") + 1,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to generate skeleton for %s: %s", file_path, exc,
                )

        return skeletons

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is reachable and the configured model is pulled.

        Result is cached on ``self._ollama_available`` so the HTTP check
        only fires once per adapter instance.  Uses a 5-second timeout to
        avoid blocking generation (REQ-MP-711).
        """
        if self._ollama_available is not None:
            return self._ollama_available

        base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        url = f"{base_url}/api/tags"
        model_name = self._config.model

        try:
            with urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())

            model_names: list[str] = []
            for m in data.get("models", []):
                if not isinstance(m, dict):
                    continue
                name = m.get("name", "")
                model_names.append(name)
                if ":" in name:
                    model_names.append(name.split(":")[0])

            model_base = model_name.split(":")[0]
            if model_name in model_names or model_base in model_names:
                self._ollama_available = True
                return True

            logger.warning(
                "Ollama model '%s' not found (available: %s)",
                model_name,
                sorted(set(model_names)),
            )
            self._ollama_available = False
            return False

        except (ConnectionRefusedError, TimeoutError, URLError, OSError) as exc:
            logger.warning("Ollama not reachable at %s: %s", base_url, exc)
            self._ollama_available = False
            return False

    def _delegate_to_fallback(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """Delegate to the fallback code generator.

        Sanitizes the context dict before delegation: Pydantic models
        (e.g. ForwardManifest) are converted to dicts so downstream
        ``json.dumps(context)`` calls in the spec builder don't crash.
        """
        if self._fallback is None:
            return GenerationResult(
                success=False,
                error="No fallback generator configured and elements need cloud processing",
            )
        # Sanitize: recursively convert Pydantic models to dicts for JSON compatibility
        clean_context = _sanitize_for_json(context)
        return self._fallback.generate(task, clean_context, target_files)

    def _resolve_cloud_agent_spec(self) -> str:
        """Resolve the cloud agent spec string for element-level escalation.

        Priority: explicit ``cloud_agent_spec`` → fallback's ``drafter_agent``
        → ``DRAFT_MODEL_CLAUDE_HAIKU.agent_spec``.
        """
        if self._cloud_agent_spec is not None:
            return self._cloud_agent_spec
        drafter = getattr(self._fallback, "drafter_agent", None)
        if drafter is not None:
            # drafter_agent may be a string spec or an agent object with a spec
            if isinstance(drafter, str):
                return drafter
            spec = getattr(drafter, "agent_spec", None)
            if isinstance(spec, str):
                return spec
        return DRAFT_MODEL_CLAUDE_HAIKU.agent_spec

    @staticmethod
    def _resolve_cloud_agent_max_tokens(spec: str) -> Optional[int]:
        """Resolve max_tokens for the cloud agent from user config.

        Uses ~/.startd8/config.json model presets when available.
        """
        try:
            from startd8.config import get_config_manager
        except Exception:
            return None

        config_mgr = get_config_manager()
        provider = ""
        model = spec
        if ":" in spec:
            provider, model = spec.split(":", 1)
        model_lower = model.lower()

        # Map model name to config key.
        key = None
        if "haiku" in model_lower:
            key = "haiku"
        elif "sonnet" in model_lower or "opus" in model_lower:
            key = "claude"
        elif provider == "anthropic":
            key = "claude"
        elif "gpt-4" in model_lower or "gpt4" in model_lower:
            key = "gpt4"

        if not key:
            return None

        cfg = config_mgr.get_model_config(key)
        max_tokens = cfg.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            return max_tokens
        return None

    def _get_cloud_agent(self) -> BaseAgent:
        """Lazily create a cloud agent for element-level escalation.

        Mirrors ``engine.py:_generate_ollama()`` lazy agent pattern.
        """
        if self._cloud_agent is None:
            from startd8.utils.agent_resolution import resolve_agent_spec

            spec = self._resolve_cloud_agent_spec()
            max_tokens = self._resolve_cloud_agent_max_tokens(spec) or 4096
            self._cloud_agent = resolve_agent_spec(spec, max_tokens=max_tokens)
            logger.debug("Cloud agent created: %s", spec)

        return self._cloud_agent

    def _direct_cloud_generate(
        self,
        element_name: str,
        element_spec: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
        skeleton: str,
        escalation_reason: str = "",
        last_error: str = "",
        retry_context: str = "",
        last_code: str = "",
        raw_output: str = "",
        repaired_code: str = "",
        repair_steps: Optional[list[str]] = None,
    ) -> Optional[tuple[str, int, int]]:
        """Single direct LLM call for one escalated element.

        Returns ``(code, input_tokens, output_tokens)`` or ``None`` on failure.
        """
        from startd8.micro_prime.prompt_builder import build_body_prompt
        from startd8.utils.code_extraction import extract_code_from_response

        prompt = build_body_prompt(
            element_spec, file_spec, contracts,
            skeleton=skeleton, token_budget=4096,
        )

        # Append escalation context so cloud model can learn from local failure
        if escalation_reason:
            prompt += f"\n\n# Escalation context: {escalation_reason}"
        if last_error:
            prompt += f"\n# Previous error: {last_error}"
        if retry_context:
            prompt += f"\n\n# Retry context: {retry_context}"
        if raw_output or repaired_code or last_code:
            truncated = raw_output or last_code
            if len(truncated) > 2000:
                truncated = truncated[:2000] + "\n# ... [truncated]"
            prompt += "\n\n# Prior local model attempt:"
            prompt += "\n# Repair steps attempted: "
            prompt += ", ".join(repair_steps or []) or "none"
            prompt += "\n```python\n" + truncated + "\n```"
            if repaired_code and repaired_code != truncated:
                repaired = repaired_code
                if len(repaired) > 2000:
                    repaired = repaired[:2000] + "\n# ... [truncated]"
                prompt += "\n\n# Repaired output:"
                prompt += "\n```python\n" + repaired + "\n```"

        agent = self._get_cloud_agent()
        result_text, _time_ms, token_usage = agent.generate(
            prompt,
            system_prompt=_CODE_GEN_SYSTEM_PROMPT,
            temperature=0.2,
        )

        code = extract_code_from_response(result_text)
        if not code or not code.strip():
            logger.debug(
                "Cloud agent returned empty code for element %s", element_name,
            )
            return None

        input_tokens = 0
        output_tokens = 0
        if token_usage:
            input_tokens = getattr(token_usage, "input", 0) or 0
            output_tokens = getattr(token_usage, "output", 0) or 0

        return code, input_tokens, output_tokens

    def _escalate_elements_to_cloud(
        self,
        file_path: str,
        file_result: FileResult,
        task: str,
        context: Dict[str, Any],
        manifest: ForwardManifest,
    ) -> Optional[GenerationResult]:
        """Delegate escalated elements via direct per-element cloud LLM calls.

        For each escalated element, builds a prompt using the same
        ``build_body_prompt()`` used by the local engine, makes a single
        cloud LLM call, and splices the result back into the partial skeleton.

        Returns:
            A ``GenerationResult`` for cost/token tracking, or ``None`` if
            there are no elements to escalate or splicing produces no changes.
        """
        from startd8.micro_prime.splicer import splice_body_into_skeleton

        if not file_result.filled_skeleton:
            return None

        file_spec = manifest.file_specs.get(file_path)
        if file_spec is None:
            return None

        # Collect escalated element results and their specs.
        # Key by (name, parent_class) to avoid collisions when multiple
        # classes define methods with the same name (e.g. SendOrderConfirmation).
        escalated_elements = []
        spec_by_key: dict[tuple[str, Optional[str]], ForwardElementSpec] = {
            (e.name, e.parent_class): e for e in file_spec.elements
        }
        for er in file_result.element_results:
            if er.escalation is None:
                continue
            key = (er.element_name, er.parent_class)
            spec = spec_by_key.get(key)
            if spec is None:
                # Fallback: match by name only (backward compat)
                spec = next(
                    (e for e in file_spec.elements if e.name == er.element_name),
                    None,
                )
            if spec is not None:
                escalated_elements.append((er, spec))

        if not escalated_elements:
            return None

        element_names = [er.element_name for er, _ in escalated_elements]
        names_str = ", ".join(element_names)
        logger.info(
            "Element-level direct cloud escalation for %s: %d elements (%s)",
            file_path, len(element_names), names_str,
        )

        updated_skeleton = file_result.filled_skeleton
        total_input = 0
        total_output = 0
        spliced_count = 0

        max_attempts = max(1, int(self._config.cloud_escalation_max_attempts))
        strategy = (self._config.cloud_escalation_retry_strategy or "same_prompt").lower()
        if strategy not in ("same_prompt", "append_error"):
            logger.warning(
                "Unknown cloud escalation retry strategy '%s' — defaulting to same_prompt",
                strategy,
            )
            strategy = "same_prompt"
        retry_max_chars = max(0, int(self._config.cloud_escalation_retry_max_chars))

        for er, spec in escalated_elements:
            # Class elements don't have raise NotImplementedError stubs —
            # their methods are handled as separate elements.  Splicing a
            # class body would overwrite locally-filled methods.
            if spec.kind == ElementKind.CLASS:
                logger.debug(
                    "Skipping class element %s — methods handled individually",
                    er.element_name,
                )
                continue

            try:
                contracts = self._engine._get_element_contracts(
                    spec, file_spec, manifest,
                )
                # er.escalation is guaranteed non-None by the filter on L848-850
                escalation_reason = er.escalation.reason.value
                prompt_error = er.escalation.last_error or ""
                last_error = prompt_error
                last_code = er.code or (er.escalation.last_code or "")
                repair_steps = er.repair_steps_applied or []
                raw_output = ""
                repaired_code = ""
                esc_ctx = er.escalation.context if er.escalation else None
                if esc_ctx:
                    raw_output = esc_ctx.raw_output or ""
                    repaired_code = esc_ctx.repaired_code or ""
                    if esc_ctx.repair_steps_applied:
                        repair_steps = list(esc_ctx.repair_steps_applied)
                    if esc_ctx.error:
                        prompt_error = esc_ctx.error
                        last_error = esc_ctx.error

                attempts = 0
                success = False
                while attempts < max_attempts and not success:
                    attempts += 1

                    retry_context = ""
                    if attempts > 1 and strategy == "append_error":
                        retry_context = (
                            f"Retry attempt {attempts}/{max_attempts}. "
                            f"Previous failure: {last_error or 'unknown'}"
                        )
                        if retry_max_chars and len(retry_context) > retry_max_chars:
                            retry_context = retry_context[:retry_max_chars]
                    if attempts > 1:
                        logger.info(
                            "Cloud escalation retry for %s in %s (attempt %d/%d, strategy=%s)",
                            er.element_name,
                            file_path,
                            attempts,
                            max_attempts,
                            strategy,
                        )

                    gen_result = self._direct_cloud_generate(
                        er.element_name, spec, file_spec, contracts,
                        updated_skeleton,
                        escalation_reason=escalation_reason,
                        last_error=prompt_error or "",
                        retry_context=retry_context,
                        last_code=last_code,
                        raw_output=raw_output,
                        repaired_code=repaired_code,
                        repair_steps=repair_steps,
                    )
                    if gen_result is None:
                        last_error = "empty_response"
                        if attempts < max_attempts:
                            continue
                        break

                    code, inp_tokens, out_tokens = gen_result

                    # Try AST extraction first (in case cloud returned full def)
                    kind_str = spec.kind.value
                    if kind_str in _FUNCTION_LIKE_KINDS:
                        kind_str = "function"
                    extracted = _extract_element_from_generated(
                        code, er.element_name, kind_str,
                    )
                    extraction_failed = extracted is None
                    splice_source = extracted if extracted is not None else code

                    spliced = splice_body_into_skeleton(
                        splice_source, spec, updated_skeleton,
                    )
                    if spliced is not None:
                        updated_skeleton = spliced
                        spliced_count += 1
                        success = True
                        total_input += inp_tokens
                        total_output += out_tokens
                        break

                    last_error = "extraction_failed" if extraction_failed else "splice_failed"

                er.cloud_retry_attempts = attempts
                er.cloud_retry_success = success
                er.cloud_retry_strategy = strategy
                er.cloud_retry_last_error = last_error or None

                if not success:
                    logger.debug(
                        "Cloud escalation failed for %s after %d/%d attempts",
                        er.element_name,
                        attempts,
                        max_attempts,
                    )
            except (OSError, ValueError, RuntimeError, TypeError):
                logger.warning(
                    "Cloud escalation failed for element %s in %s, continuing",
                    er.element_name, file_path, exc_info=True,
                )

        if spliced_count > 0:
            output_path = self._output_dir / file_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(updated_skeleton, encoding="utf-8")
            logger.info(
                "Spliced %d/%d escalated elements into %s",
                spliced_count, len(escalated_elements), file_path,
            )

        # Compute cost via PricingService
        cost_usd = 0.0
        if total_input > 0 or total_output > 0:
            try:
                from startd8.costs.pricing import PricingService
                pricing = PricingService()
                agent_spec = self._resolve_cloud_agent_spec()
                # Extract model name from provider:model spec
                model_name = agent_spec.split(":")[-1] if ":" in agent_spec else agent_spec
                cost_usd = pricing.calculate_total_cost(
                    model_name, total_input, total_output,
                )
            except ImportError:
                logger.debug("PricingService not available, skipping cost computation")
            except (KeyError, ValueError):
                logger.warning(
                    "Could not compute cost for cloud model %s — pricing data may be missing",
                    model_name, exc_info=True,
                )

        return GenerationResult(
            success=spliced_count > 0,
            generated_files=[self._output_dir / file_path] if spliced_count > 0 else [],
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost_usd,
            model=self._resolve_cloud_agent_spec(),
        )
