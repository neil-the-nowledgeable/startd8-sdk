"""DESIGN phase handler."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import re
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
    compute_lanes,
)
from startd8.contractors.context_schema import DesignPhaseOutput
from startd8.contractors.context_seed.shared import (
    SeedTask,
    _ensure_context_loaded,
    _log_context_completeness,
    _track_onboarding_consumption,
)
from startd8.contractors.protocols import (
    DRAFT_MODEL_CLAUDE_HAIKU,
    GenerationResult,
)
from startd8.exceptions import Startd8Error
from startd8.logging_config import get_logger
from startd8.otel import attach_context, capture_context, detach_context
from startd8.utils.artifact_inventory import (
    load_artifact_content,
    load_inventory,
    lookup_artifact,
)
from startd8.utils.retry import RetryConfig, _calculate_delay, _is_retryable_exception
from startd8.utils.token_usage import (
    token_usage_cost,
    token_usage_input,
    token_usage_output,
)
from startd8.contractors.artisan_phases.self_consistency import (
    validate_dockerfile_coherence,
    validate_protocol_fidelity,
)
from startd8.contractors.context_seed.handler_support import (
    _build_provenance_links,
    _capture_task_span_context,
    _coerce_optional_float,
    _compute_design_results_hash,
    _log_task_boundary_complete,
    _log_task_boundary_start,
    _log_task_timing,
    HandlerConfig,
)
from startd8.contractors.context_seed.tracing import _HAS_OTEL, _phase_tracer
from startd8.contractors.context_seed.design_support import (
    _classify_complexity_tier,
    _compute_ccd_task_metadata,
    _compute_manifest_file_checksums,
    _detect_cross_file_edges,
    _extract_complexity_signals,
    _extract_design_target_files,
    _extract_referenced_elements,
    _extract_structural_delta,
    _normalize_target_path,
    _set_default_complexity_metadata,
    build_shared_file_manifest,
    compute_critical_path_tasks,
    compute_lane_to_file_mapping,
)
from startd8.contractors.design_collision import check_lane_collisions
from startd8.contractors.forensic_log import (
    get_boundary_result,
    reset_boundary_result,
    set_boundary_result,
)
from startd8.contractors.handoff import (
    DESIGN_HANDOFF_FILENAME,
    load_design_handoff,
    validate_handoff_against_context,
    verify_context_checksums,
    write_design_handoff,
)
from startd8.contractors.artisan_phases.design_documentation import DesignSectionV2
from startd8.contractors.artisan_phases.design_prompts import assemble_design_prompt
from startd8.contractors.gate_contracts import GateEmitter

logger = get_logger("startd8.contractors.context_seed_handlers")

class DesignPhaseHandler(AbstractPhaseHandler):
    """DESIGN phase: Generate design docs per task (single LLM call).

    In dry-run mode: reports what would be designed per task (no LLM calls).
    In real mode: generates a design document via ``_run_v2_generate()`` for
    each task, running the async generation via a thread-owned event loop
    (same pattern as :class:`ImplementPhaseHandler`).

    Data flow (REQ-DSR-001 — dual-review removed):
        1. ``SeedTask`` → ``assemble_design_prompt()`` (V2 modular prompts)
        2. ``_run_v2_generate(prompt)`` → raw design text
        3. Quality gates: parameter completeness + structure validation
        4. Results serialized → ``context["design_results"]``

    Output files:
        When ``output_dir`` is set, writes ``{task_id}-design.md`` files
        containing the raw design document text.
    """

    def __init__(
        self,
        handler_config: Optional[HandlerConfig] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        self.config = handler_config or HandlerConfig()
        self.output_dir = output_dir
        self._llm_backend: Any = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_llm_backend(self) -> Any:
        """Lazily create the AgentLLMBackend."""
        if self._llm_backend is not None:
            return self._llm_backend

        from startd8.contractors.artisan_phases.design_documentation import (
            AgentLLMBackend,
        )

        agent_spec = self.config.design_agent or self.config.lead_agent
        self._llm_backend = AgentLLMBackend(
            agent_spec=agent_spec,
            enable_prompt_caching=self.config.enable_prompt_caching,
        )
        return self._llm_backend

    @staticmethod
    def _extract_task_suggestions(
        refine_text: str, task_id: str, feature_id: str | None
    ) -> str:
        """Extract refine suggestions relevant to a specific task.

        Extracts plan-level suggestions (S-prefix) and feature-matching
        suggestions (F-prefix) from the REFINE phase output text.
        """
        if not refine_text:
            return ""
        lines = refine_text.splitlines()
        relevant: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Plan-level suggestions start with S- prefix
            if stripped.startswith("S-"):
                relevant.append(stripped)
            # Feature-specific suggestions start with F- prefix
            elif stripped.startswith("F-"):
                # Match by task_id or feature_id
                if task_id and task_id in stripped:
                    relevant.append(stripped)
                elif feature_id and feature_id in stripped:
                    relevant.append(stripped)
        return "\n".join(relevant) if relevant else ""

    @staticmethod
    def _format_structured_suggestions(
        suggestions: list[dict[str, Any]],
    ) -> str:
        """Format structured REFINE triage suggestions as markdown for prompt injection.

        Handles two formats:
        - Individual ACCEPT decisions with id/area/severity/rationale
        - Aggregate triage summary (fallback when per-decision data unavailable)
        """
        if not suggestions:
            return ""

        parts: list[str] = []
        parts.append("REFINE Phase Accepted Suggestions:")

        for sug in suggestions:
            if sug.get("source") == "triage_summary":
                # Aggregate summary format
                accepted = sug.get("triage_accepted_count", 0)
                areas = sug.get("substantially_addressed_areas", [])
                needs_review = sug.get("areas_needing_review", [])
                parts.append(f"- {accepted} suggestion(s) accepted by triage")
                if areas:
                    parts.append(
                        f"  Addressed areas: {', '.join(str(a) for a in areas)}"
                    )
                if needs_review:
                    parts.append(
                        f"  Areas needing review: {', '.join(str(a) for a in needs_review)}"
                    )
            else:
                # Individual decision format
                sid = sug.get("id", "?")
                area = sug.get("area", "")
                severity = sug.get("severity", "")
                rationale = sug.get("rationale", "")
                line = f"- [{sid}]"
                if area:
                    line += f" ({area}"
                    if severity:
                        line += f", {severity}"
                    line += ")"
                if rationale:
                    line += f": {rationale}"
                parts.append(line)

        return "\n".join(parts)

    @staticmethod
    def _extract_plan_section(plan_text: str, section_name: str) -> str:
        """Extract a named markdown section from plan text.

        Looks for ``## {section_name}`` or ``### {section_name}`` headers
        and returns content up to the next header of same or higher level.
        """
        import re

        if not plan_text:
            return ""
        # Find the section header (## or ###)
        pattern = rf"^(#{{2,3}})\s+{re.escape(section_name)}.*$"
        match = re.search(pattern, plan_text, re.MULTILINE | re.IGNORECASE)
        if not match:
            return ""

        start = match.end()
        header_level = len(match.group(1))

        # Find the next header of same or higher level
        next_header = re.search(
            rf"^#{{{1},{header_level}}}\s+",
            plan_text[start:],
            re.MULTILINE,
        )
        if next_header:
            end = start + next_header.start()
        else:
            end = len(plan_text)

        section = plan_text[start:end].strip()
        # Truncate to avoid massive context injection
        if len(section) > 2000:
            section = section[:2000] + "\n... (truncated)"
        return section

    @staticmethod
    def _run_v2_generate(
        backend: Any,
        prompt: str,
        system_prompt: str,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """Run backend.generate() in a dedicated thread-owned event loop.

        Mirrors ``_run_design_async`` but invokes a single LLM call
        (no dual-review, no revision loop) for the v2 modular prompt path.
        """
        result_box: dict[str, Any] = {}
        error_box: dict[str, Exception] = {}
        parent_ctx = capture_context()
        from startd8.contractors.forensic_log import (
            get_boundary_result,
            set_boundary_result,
            reset_boundary_result,
        )
        parent_boundary_result = get_boundary_result()

        def _runner() -> None:
            token = attach_context(parent_ctx)
            br_token = set_boundary_result(parent_boundary_result)
            try:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    result_box["result"] = loop.run_until_complete(
                        backend.generate(
                            prompt,
                            system_prompt=system_prompt,
                            max_tokens=max_tokens,
                        )
                    )
                except Exception as exc:
                    error_box["error"] = exc
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            finally:
                reset_boundary_result(br_token)
                detach_context(token)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Race guard — thread may have completed between join() and is_alive()
            if "result" in result_box or "error" in error_box:
                logger.debug(
                    "_run_v2_generate thread reported alive after join() "
                    "but result_box is populated — treating as completed",
                )
            else:
                logger.error(
                    "v2 design generate did not complete within %.0fs — "
                    "abandoning background thread (daemon=True)",
                    timeout,
                )
                raise TimeoutError(
                    f"v2 design generate did not complete within {timeout}s"
                )

        if "error" in error_box:
            raise error_box["error"]
        if "result" not in result_box:
            raise RuntimeError(
                "_run_v2_generate: thread completed but produced neither result nor error"
            )
        return result_box["result"]

    @staticmethod
    def _flatten_parameter_values(
        value: Any,
        *,
        key_prefix: str = "",
    ) -> list[tuple[str, str]]:
        """Flatten nested parameter structures into key/value scalar pairs."""
        flattened: list[tuple[str, str]] = []
        if isinstance(value, dict):
            for key, child in value.items():
                next_prefix = f"{key_prefix}.{key}" if key_prefix else str(key)
                flattened.extend(
                    DesignPhaseHandler._flatten_parameter_values(
                        child,
                        key_prefix=next_prefix,
                    )
                )
            return flattened
        if isinstance(value, (list, tuple, set)):
            for idx, child in enumerate(value):
                next_prefix = f"{key_prefix}[{idx}]" if key_prefix else str(idx)
                flattened.extend(
                    DesignPhaseHandler._flatten_parameter_values(
                        child,
                        key_prefix=next_prefix,
                    )
                )
            return flattened
        if value is None:
            return flattened
        value_text = str(value).strip()
        if not value_text:
            return flattened
        flattened.append((key_prefix or "value", value_text))
        return flattened

    @staticmethod
    def _collect_resolved_parameters_for_task(
        task: SeedTask,
        *,
        inv_resolved_parameters: dict[str, Any] | None,
        onboarding_resolved_parameters: dict[str, Any] | None,
        parameter_sources: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        """Collect resolved parameter key/value pairs relevant to a task."""
        artifact_types = set(task.artifact_types_addressed or [])
        task_markers = {
            str(task.task_id or "").lower(),
            str(task.feature_id or "").lower(),
        } - {""}
        collected: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def _emit(key: str, value: str, source: str) -> None:
            pair = (key, value)
            if pair in seen:
                return
            seen.add(pair)
            collected.append({"key": key, "value": value, "source": source})

        def _collect_from_mapping(data: dict[str, Any], source: str) -> None:
            for raw_key, raw_value in data.items():
                key_str = str(raw_key)
                key_lc = key_str.lower()
                if artifact_types:
                    if not any(atype in key_str for atype in artifact_types):
                        continue
                elif task_markers and not any(marker in key_lc for marker in task_markers):
                    # Without artifact typing, only evaluate task-scoped keys.
                    continue
                for param_key, param_val in DesignPhaseHandler._flatten_parameter_values(
                    raw_value,
                    key_prefix=key_str,
                ):
                    _emit(param_key, param_val, source)

        for source_name, mapping in [
            ("inventory", inv_resolved_parameters or {}),
            ("onboarding", onboarding_resolved_parameters or {}),
        ]:
            if isinstance(mapping, dict) and mapping:
                _collect_from_mapping(mapping, source_name)

        # Fallback path for seeds that only include parameter_sources.
        if (
            not collected
            and artifact_types
            and isinstance(parameter_sources, dict)
            and parameter_sources
        ):
            source_subset = parameter_sources
            if artifact_types:
                source_subset = {
                    atype: parameter_sources.get(atype)
                    for atype in artifact_types
                    if atype in parameter_sources
                }
            for source_key, source_val in source_subset.items():
                if isinstance(source_val, dict):
                    for param_key, param_val in source_val.items():
                        if isinstance(param_val, (str, int, float, bool)):
                            _emit(str(param_key), str(param_val), f"parameter_sources:{source_key}")

        return collected[:60]

    @staticmethod
    def _evaluate_parameter_completeness(
        implementation_spec: str,
        resolved_parameters: list[dict[str, str]],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Evaluate AR-139 parameter completeness against implementation spec text."""
        if not resolved_parameters:
            return {
                "status": "not_applicable",
                "passed": True,
                "evaluated_count": 0,
                "present_count": 0,
                "missing_count": 0,
                "missing": [],
                "dry_run": dry_run,
            }

        spec_text = implementation_spec or ""
        spec_lc = spec_text.lower()
        missing: list[dict[str, str]] = []
        present_count = 0

        def _word_boundary_match(needle: str, haystack: str) -> bool:
            """R2-D5: Use word-boundary matching instead of substring `in`.

            Prevents false positives like "url" matching "base_url".
            """
            return bool(re.search(r'\b' + re.escape(needle) + r'\b', haystack))

        for param in resolved_parameters:
            key = str(param.get("key", "") or "")
            value = str(param.get("value", "") or "")
            source = str(param.get("source", "unknown") or "unknown")
            value_candidates = {
                value.lower(),
                value.strip('"').strip("'").lower(),
            }
            key_candidate = key.lower()

            found = False
            for candidate in value_candidates:
                if candidate and len(candidate) >= 2 and _word_boundary_match(candidate, spec_lc):
                    found = True
                    break
            if not found and key_candidate and len(key_candidate) >= 3 and _word_boundary_match(key_candidate, spec_lc):
                found = True

            if found:
                present_count += 1
                continue

            missing.append({
                "key": key,
                "value": value,
                "source": source,
            })

        missing_count = len(missing)
        status = "pass" if missing_count == 0 else "fail"
        return {
            "status": status,
            "passed": missing_count == 0,
            "evaluated_count": len(resolved_parameters),
            "present_count": present_count,
            "missing_count": missing_count,
            "missing": missing,
            "dry_run": dry_run,
        }

    def _apply_design_quality_gates(
        self,
        *,
        task: SeedTask,
        entry: dict[str, Any],
        resolved_parameters: list[dict[str, str]],
        quality_policy_mode: str,
        dry_run: bool,
    ) -> None:
        """Apply quality gates to a task design result.

        After dual-review removal (REQ-DSR-001), the remaining gates are:
        - Parameter completeness (AR-139)
        - V2 structure validation (REQ-DSR-003)
        """
        design_text = str(entry.get("design_document", "") or "")
        if not design_text:
            design_text = str(entry.get("implementation_spec", "") or "")
        entry["implementation_spec"] = design_text
        entry["implementation_spec_artifact"] = {
            "kind": "inline_design_spec",
            "present": bool(design_text.strip()),
            "char_count": len(design_text),
            "line_count": len(design_text.splitlines()) if design_text else 0,
        }

        # REQ-DSR-003: V2 structure validation (zero LLM cost)
        structure_validation = self._validate_v2_structure(design_text)
        entry["structure_validation"] = structure_validation

        completeness = self._evaluate_parameter_completeness(
            design_text,
            resolved_parameters,
            dry_run=dry_run,
        )
        entry["parameter_completeness"] = completeness

        if completeness.get("missing_count", 0):
            missing_preview = ", ".join(
                f"{p['key']}={p['value']}"
                for p in completeness.get("missing", [])[:5]
            )
            feedback = (
                "Resolved parameters are missing from the implementation spec: "
                f"{missing_preview}. Add them verbatim to a Critical Parameters "
                "section and implementation steps."
            )
            entry["completeness_feedback"] = feedback
            prior_feedback = str(entry.get("next_iteration_feedback", "") or "").strip()
            entry["next_iteration_feedback"] = (
                f"{prior_feedback}\n{feedback}".strip()
                if prior_feedback
                else feedback
            )

        if structure_validation.get("missing_sections"):
            structure_feedback = (
                "Design document is missing required sections: "
                + ", ".join(structure_validation["missing_sections"])
            )
            prior_feedback = str(entry.get("next_iteration_feedback", "") or "").strip()
            entry["next_iteration_feedback"] = (
                f"{prior_feedback}\n{structure_feedback}".strip()
                if prior_feedback
                else structure_feedback
            )

        if structure_validation.get("empty_sections"):
            empty_feedback = (
                "Design document has sections with insufficient content "
                "(each section needs at least 2 non-empty lines): "
                + ", ".join(structure_validation["empty_sections"])
            )
            prior_feedback = str(entry.get("next_iteration_feedback", "") or "").strip()
            entry["next_iteration_feedback"] = (
                f"{prior_feedback}\n{empty_feedback}".strip()
                if prior_feedback
                else empty_feedback
            )

        if dry_run:
            entry["completeness_gate_decision"] = "dry_run_report_only"
            return

        # REQ-DSR-003: Structure validation gate
        structure_failed = not structure_validation.get("passed", True)
        completeness_failed = not completeness.get("passed", True)

        if structure_failed:
            _missing = structure_validation.get("missing_sections", [])
            _empty = structure_validation.get("empty_sections", [])
            _detail_parts: list[str] = []
            if _missing:
                _detail_parts.append(f"missing sections: {', '.join(_missing)}")
            if _empty:
                _detail_parts.append(f"empty sections: {', '.join(_empty)}")
            _detail = "; ".join(_detail_parts) if _detail_parts else "unknown"

            if quality_policy_mode == "block":
                entry["quality_failure_reason"] = "STRUCTURE_VALIDATION_FAILED"
                if entry.get("status") in ("designed", "refined", "adopted"):
                    entry["status"] = "design_failed"
                entry["error"] = (
                    f"V2 structure validation failed for {task.task_id}: "
                    f"{_detail}"
                )
                entry["completeness_gate_decision"] = "not_evaluated_due_to_structure_failure"
                return
            logger.warning(
                "DESIGN: task %s structure validation failed (%s) — "
                "continuing per %s policy",
                task.task_id,
                _detail,
                quality_policy_mode,
            )

        if completeness_failed:
            if quality_policy_mode == "skip":
                entry["completeness_gate_decision"] = "skipped"
            elif quality_policy_mode == "block":
                entry["quality_failure_reason"] = "PARAMETER_COMPLETENESS_FAILED"
                if entry.get("status") in ("designed", "refined", "adopted"):
                    entry["status"] = "design_failed"
                entry["error"] = (
                    "AR-139 completeness gate failed in block mode for "
                    f"{task.task_id}: {completeness.get('missing_count', 0)} parameter(s) missing."
                )
                entry["completeness_gate_decision"] = "blocked"
            else:
                entry["quality_failure_reason"] = "PARAMETER_COMPLETENESS_DEGRADED"
                entry["completeness_gate_decision"] = "degraded"
            return

        entry["completeness_gate_decision"] = "pass"

    @staticmethod
    def _task_quality_passed(entry: dict[str, Any]) -> bool:
        """Return whether a DESIGN task entry passes all quality gates.

        After dual-review removal (REQ-DSR-001), checks:
        - Status is a success state
        - Parameter completeness passed
        """
        status = entry.get("status", "")
        if status not in ("designed", "refined", "adopted"):
            return False
        completeness = entry.get("parameter_completeness")
        if isinstance(completeness, dict) and not completeness.get("passed", False):
            return False
        return True

    @staticmethod
    def _task_quality_reason(entry: dict[str, Any]) -> str | None:
        """Return machine-friendly reason for DESIGN quality failure."""
        if entry.get("status") == "design_failed":
            return str(
                entry.get("quality_failure_reason")
                or "DESIGN_FAILED"
            )
        completeness = entry.get("parameter_completeness")
        if isinstance(completeness, dict) and not bool(completeness.get("passed", False)):
            decision = str(entry.get("completeness_gate_decision", "") or "")
            if decision == "degraded":
                return "PARAMETER_COMPLETENESS_DEGRADED"
            return "PARAMETER_COMPLETENESS_FAILED"
        structure = entry.get("structure_validation")
        if isinstance(structure, dict) and not structure.get("passed", False):
            return "STRUCTURE_VALIDATION_FAILED"
        return None

    @staticmethod
    @staticmethod
    def _section_content_lines(raw_text: str, header: str) -> int:
        """Count non-empty content lines between *header* and the next ``##`` header.

        Returns the number of non-blank lines that follow ``header`` before
        the next ``## …`` header (or end-of-text).  Used to detect
        placeholder-only sections that have a header but no real content.
        """
        pattern = rf'^{re.escape(header)}\s*$'
        match = re.search(pattern, raw_text, re.MULTILINE)
        if not match:
            return 0
        start = match.end()
        # Find the next ## header (same or higher level)
        next_header = re.search(r'^## ', raw_text[start:], re.MULTILINE)
        if next_header:
            section_body = raw_text[start:start + next_header.start()]
        else:
            section_body = raw_text[start:]
        return sum(1 for line in section_body.splitlines() if line.strip())

    _MIN_SECTION_CONTENT_LINES = 2

    @staticmethod
    def _validate_v2_structure(raw_text: str) -> dict[str, Any]:
        """Check V2 design document has all required section headers and content.

        REQ-DSR-003: Zero-LLM-cost structural validation replacing the
        dual-review gate signal.  Uses DesignSectionV2 enum sections.

        Checks both header *presence* and that each section has at least
        ``_MIN_SECTION_CONTENT_LINES`` non-empty lines of content.
        """
        from startd8.contractors.artisan_phases.design_documentation import DesignSectionV2
        required = [f"## {s.value}" for s in DesignSectionV2]
        missing = [
            h for h in required
            if not re.search(rf'^{re.escape(h)}\s*$', raw_text, re.MULTILINE)
        ]

        # Check content depth for present sections
        empty_sections: list[str] = []
        min_lines = DesignPhaseHandler._MIN_SECTION_CONTENT_LINES
        for h in required:
            if h in missing:
                continue  # already flagged as missing
            content_lines = DesignPhaseHandler._section_content_lines(raw_text, h)
            if content_lines < min_lines:
                empty_sections.append(h)

        passed = len(missing) == 0 and len(empty_sections) == 0
        return {
            "passed": passed,
            "missing_sections": missing,
            "empty_sections": empty_sections,
        }

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("DESIGN", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)

        logger.info("DESIGN phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)

        # REQ-PD-010: Source checksum drift detection (advisory only)
        _source_checksum = context.get("source_checksum")
        _source_checksum_status = "unavailable"
        if _source_checksum:
            # Try to find a reference file to verify against
            _ref_file: Path | None = None
            for _candidate_dir in [
                Path(self.output_dir) if self.output_dir else None,
                Path(context.get("enriched_seed_path", "")).parent if context.get("enriched_seed_path") else None,
            ]:
                if _candidate_dir is None:
                    continue
                for _fname in (".contextcore.yaml", "onboarding-metadata.json"):
                    _cpath = _candidate_dir / _fname
                    if _cpath.exists():
                        _ref_file = _cpath
                        break
                if _ref_file:
                    break

            if _ref_file:
                try:
                    _ref_hash = hashlib.sha256(
                        _ref_file.read_bytes()
                    ).hexdigest()
                    if _ref_hash == _source_checksum:
                        _source_checksum_status = "match"
                        logger.info(
                            "DESIGN: source_checksum MATCH — provenance intact "
                            "(ref=%s)", _ref_file.name,
                        )
                    else:
                        _source_checksum_status = "mismatch"
                        logger.warning(
                            "DESIGN: source_checksum MISMATCH — reference file "
                            "%s may have changed since plan ingestion "
                            "(expected %s..., got %s...)",
                            _ref_file.name,
                            _source_checksum[:16],
                            _ref_hash[:16],
                        )
                except OSError:
                    logger.debug(
                        "DESIGN: could not read reference file for checksum verification"
                    )
            else:
                logger.debug(
                    "DESIGN: no reference file found for source_checksum verification"
                )
        else:
            logger.debug("DESIGN: source_checksum not present in context")
        context["_source_checksum_status"] = _source_checksum_status

        # REQ-PD-013: Chain status logging — assess Plan→Design data chain
        _chain_signals = {
            "plan_document_text": bool(context.get("plan_document_text")),
            "complexity_dimensions": bool(context.get("complexity_dimensions")),
            "complexity_composite": context.get("complexity_composite") is not None,
            "wave_metadata": bool(context.get("wave_metadata")),
            "architectural_context": bool(context.get("architectural_context")),
            "design_calibration": bool(context.get("design_calibration")),
            "source_checksum": bool(context.get("source_checksum")),
        }
        _chain_present = sum(1 for v in _chain_signals.values() if v)
        _chain_total = len(_chain_signals)
        if _chain_present == _chain_total:
            _pi_design_chain_status = "INTACT"
        elif _chain_present > 0:
            _pi_design_chain_status = "DEGRADED"
        else:
            _pi_design_chain_status = "BROKEN"
        context["_pi_design_chain_status"] = _pi_design_chain_status
        logger.info(
            "DESIGN: Plan→Design chain status: %s (%d/%d signals present: %s)",
            _pi_design_chain_status, _chain_present, _chain_total,
            {k for k, v in _chain_signals.items() if v},
        )
        _quality_gate_summary = context.get("quality_gate_summary", {}) or {}
        quality_policy_mode = str(
            _quality_gate_summary.get("policy_mode", "warn")
        ).lower()
        if quality_policy_mode not in {"skip", "warn", "block"}:
            quality_policy_mode = "warn"

        design_results: dict[str, dict[str, Any]] = {}
        total_cost = 0.0
        tasks_designed = 0
        tasks_agreed = 0
        tasks_failed = 0
        tasks_adopted = 0
        tasks_refined = 0
        route_decision_counts: dict[str, int] = defaultdict(int)
        route_quality_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"passed": 0, "failed": 0}
        )

        # Prior design_results injected via --adopt-prior (or checkpoint resume)
        prior_design_results: dict[str, dict[str, Any]] = context.get("design_results", {})

        # --- Auto-load prior design results from disk (handoff.json) ---
        # Mirror IMPLEMENT's auto-cache pattern: check disk first, adopt
        # automatically. --adopt-prior injects via context; this covers the
        # case where no flag was passed but a handoff exists from a prior run.
        if not prior_design_results and not dry_run and not self.config.force_design:
            if self.output_dir:
                from startd8.contractors.handoff import (
                    load_design_handoff,
                    DESIGN_HANDOFF_FILENAME,
                    validate_handoff_against_context,
                    verify_context_checksums,
                )
                handoff_path = Path(self.output_dir) / DESIGN_HANDOFF_FILENAME
                if handoff_path.exists():
                    try:
                        handoff = load_design_handoff(handoff_path)
                        if handoff.design_results:
                            # Cross-validate handoff against current context
                            validation_warnings = validate_handoff_against_context(
                                handoff, context,
                            )
                            # Verify context file checksums for drift
                            if handoff.context_files:
                                checksum_warnings = verify_context_checksums(
                                    handoff.context_files,
                                )
                                for w in checksum_warnings:
                                    logger.warning("DESIGN: handoff checksum: %s", w)
                                validation_warnings.extend(checksum_warnings)

                            if validation_warnings:
                                for w in validation_warnings:
                                    logger.warning("DESIGN: handoff validation: %s", w)
                                logger.warning(
                                    "DESIGN: handoff has %d validation warning(s) — "
                                    "adopting anyway (use --force-design to regenerate)",
                                    len(validation_warnings),
                                )

                            prior_design_results = handoff.design_results
                            logger.info(
                                "DESIGN: auto-loaded %d prior design result(s) from %s",
                                len(prior_design_results), handoff_path,
                            )
                            # C-5: Compute design_quality from prior results
                            # so that downstream consumers (handoff write,
                            # DesignPhaseOutput validation) have it available
                            # even before the end-of-phase quality loop runs.
                            _adopted_passed = 0
                            _adopted_failed = 0
                            for _adr in prior_design_results.values():
                                if not isinstance(_adr, dict):
                                    continue
                                _adr_status = _adr.get("status", "")
                                if _adr_status in (
                                    "dry_run_skipped", "env_blocked",
                                ):
                                    continue
                                if DesignPhaseHandler._task_quality_passed(_adr):
                                    _adopted_passed += 1
                                else:
                                    _adopted_failed += 1
                            _adopted_total = _adopted_passed + _adopted_failed
                            _adopted_agreement = (
                                _adopted_passed / _adopted_total
                                if _adopted_total > 0
                                else 0.0
                            )
                            context["design_quality"] = {
                                "total_passed": _adopted_passed,
                                "total_failed": _adopted_failed,
                                "agreement_rate": _adopted_agreement,
                                "evaluated_task_count": _adopted_total,
                            }
                            logger.info(
                                "DESIGN: pre-seeded design_quality from "
                                "prior results: passed=%d, failed=%d, "
                                "agreement_rate=%.2f",
                                _adopted_passed,
                                _adopted_failed,
                                _adopted_agreement,
                            )
                    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
                        logger.warning(
                            "DESIGN: failed to auto-load handoff from %s: %s",
                            handoff_path, exc,
                        )

        # Phase 5: Manifest registry resolution for DESIGN (CS-1)
        _design_manifest_registry = None
        if self.config.manifest_consumption_enabled:
            _design_manifest_registry = (
                self.config.manifest_registry
                or context.get("project_manifests")
            )
        if _design_manifest_registry is not None:
            logger.info("DESIGN: manifest registry available for structural context")
        else:
            logger.info(
                "manifest.fallback",
                extra={
                    "surface": "design_enrichment",
                    "reason": (
                        "registry_unavailable"
                        if not self.config.manifest_consumption_enabled
                        else "no_registry"
                    ),
                },
            )

        # Extract shared context for cross-task design quality
        plan_goals = context.get("plan_goals", [])
        arch_context = context.get("architectural_context", {})
        calibration_map = context.get("design_calibration", {})
        prior_summaries: list[str] = []
        previous_task_started_mono: Optional[float] = None
        # REQ-PD-007: Completed design summaries for dependency injection
        completed_designs: dict[str, str] = {}
        # REQ-PD-008: Wave boundary tracking
        _prev_wave_index: int | None = None

        # Mottainai: load artifact inventory from export-stage provenance
        inv_derivation_rules: dict[str, Any] | None = None
        inv_resolved_parameters: dict[str, Any] | None = None
        inv_output_contracts: dict[str, Any] | None = None
        inv_refine_suggestions: str | list[dict[str, Any]] | None = None
        inv_plan_document: str | None = None
        inv_calibration_hints: dict[str, Any] | None = None

        inventory_dir = None
        if self.output_dir:
            # Derive export output dir: check output_dir first, then parent
            for candidate in [Path(self.output_dir), Path(self.output_dir).parent]:
                if (candidate / "run-provenance.json").exists():
                    inventory_dir = candidate
                    break
        # Also check enriched_seed_path parent (common in artisan runs)
        if not inventory_dir:
            seed_path = context.get("enriched_seed_path", "")
            if seed_path:
                candidate = Path(seed_path).parent
                if (candidate / "run-provenance.json").exists():
                    inventory_dir = candidate

        if inventory_dir:
            inventory = load_inventory(inventory_dir)
            if inventory:
                for role, var_name in [
                    ("derivation_rules", "inv_derivation_rules"),
                    ("resolved_parameters", "inv_resolved_parameters"),
                    ("output_contracts", "inv_output_contracts"),
                    ("calibration_hints", "inv_calibration_hints"),
                ]:
                    entry, outcome = lookup_artifact(inventory, role)
                    if entry and outcome == "hit":
                        data = load_artifact_content(entry, inventory_dir)
                        if data and isinstance(data, dict):
                            if var_name == "inv_derivation_rules":
                                inv_derivation_rules = data
                            elif var_name == "inv_resolved_parameters":
                                inv_resolved_parameters = data
                            elif var_name == "inv_output_contracts":
                                inv_output_contracts = data
                            elif var_name == "inv_calibration_hints":
                                inv_calibration_hints = data

                # Refine suggestions (text, not dict)
                entry, outcome = lookup_artifact(inventory, "refine_suggestions")
                if entry and outcome == "hit":
                    data = load_artifact_content(entry, inventory_dir)
                    if isinstance(data, str):
                        inv_refine_suggestions = data

                # Plan document (text)
                entry, outcome = lookup_artifact(inventory, "plan_document")
                if entry and outcome == "hit":
                    # plan_document may be a markdown file read as text
                    source_file = entry.get("source_file", "")
                    if source_file:
                        plan_path = inventory_dir / source_file
                        if plan_path.exists():
                            try:
                                inv_plan_document = plan_path.read_text(
                                    encoding="utf-8"
                                )
                            except OSError:
                                logger.debug("Could not read file: %s", plan_path, exc_info=True)

        # Mottainai fallback: when inventory lookup didn't find these fields,
        # try the onboarding-metadata forwarded through the seed by PLAN phase.
        _fallback_map = [
            ("inv_derivation_rules", "onboarding_derivation_rules"),
            ("inv_resolved_parameters", "onboarding_resolved_parameters"),
            ("inv_output_contracts", "onboarding_output_contracts"),
            ("inv_calibration_hints", "onboarding_calibration_hints"),
        ]
        _fb_count = 0
        _profile = context.get("generation_profile", "full")
        for local_var, ctx_key in _fallback_map:
            if locals()[local_var] is None:
                fb_val = context.get(ctx_key)
                # REQ-GPC-500: log when profile omission causes fallback skip
                if fb_val is None and _profile != "full":
                    logger.debug(
                        "DESIGN: %s skipped (omitted by %s profile)",
                        ctx_key, _profile,
                    )
                    continue
                if fb_val and isinstance(fb_val, dict):
                    if local_var == "inv_derivation_rules":
                        inv_derivation_rules = fb_val
                    elif local_var == "inv_resolved_parameters":
                        inv_resolved_parameters = fb_val
                    elif local_var == "inv_output_contracts":
                        inv_output_contracts = fb_val
                    elif local_var == "inv_calibration_hints":
                        inv_calibration_hints = fb_val
                    _fb_count += 1
        if _fb_count:
            logger.info(
                "DESIGN: %d inventory field(s) loaded from onboarding fallback",
                _fb_count,
            )

        # IMP-8a: structured onboarding fallback — prefer structured triage
        # decisions from REFINE forwarding (REQ-RF-003) over text extraction
        if inv_refine_suggestions is None:
            structured = context.get("onboarding_refine_suggestions")
            if structured and isinstance(structured, list):
                inv_refine_suggestions = structured
                logger.info(
                    "DESIGN: refine_suggestions loaded from onboarding (%d entries)",
                    len(structured),
                )

        # Mottainai B2+B3 fallback: when inventory didn't find plan_document
        # or refine_suggestions, use the plan document text loaded by PLAN phase
        # directly from the seed's artifacts.plan_document_path.
        if inv_plan_document is None:
            plan_text = context.get("plan_document_text")
            if plan_text and isinstance(plan_text, str):
                inv_plan_document = plan_text
                logger.info(
                    "DESIGN: plan_document loaded from seed fallback (%d chars)",
                    len(plan_text),
                )
        if inv_refine_suggestions is None and inv_plan_document:
            # REFINE suggestions live inside the plan document (Appendix C).
            # When loaded via seed fallback, the full plan text IS the source.
            inv_refine_suggestions = inv_plan_document
            logger.info("DESIGN: refine_suggestions derived from plan document text")

        # ==============================================================
        # CCD-100: Compute lane assignments at DESIGN time
        # ==============================================================
        _design_lanes: list[list[SeedTask]] | None = None
        _lane_assignments: dict[str, int] = {}
        try:
            _design_lanes = compute_lanes(tasks)
            for _lane_idx, _lane_tasks in enumerate(_design_lanes):
                for _lt in _lane_tasks:
                    _lane_assignments[_lt.task_id] = _lane_idx
            logger.info(
                "DESIGN: computed %d lane(s) for %d tasks",
                len(_design_lanes), len(tasks),
            )
        except Exception as _lane_exc:
            # CCD-104: Graceful fallback
            logger.warning(
                "DESIGN: compute_lanes() failed — falling back to flat "
                "iteration: %s",
                _lane_exc,
            )
            _design_lanes = None

        # CCD-603: Lane computation state flags for FINALIZE coherence summary
        context["_design_lane_computation_skipped"] = _design_lanes is None
        context["_design_lane_count"] = (
            len(_design_lanes) if _design_lanes else 0
        )

        # CCD-101: Wave-sort tasks within each lane
        if _design_lanes is not None:
            for _li, _lane in enumerate(_design_lanes):
                _design_lanes[_li] = sorted(
                    _lane,
                    key=lambda t: (
                        t.wave_index if t.wave_index is not None else float("inf"),
                        t.task_id,
                    ),
                )

        # CCD-300: Build shared-file manifest
        shared_file_manifest: dict[str, list[str]] = {}
        try:
            shared_file_manifest = build_shared_file_manifest(tasks)
            if shared_file_manifest:
                logger.info(
                    "DESIGN: %d contested file(s) across %d tasks",
                    len(shared_file_manifest),
                    len({tid for tids in shared_file_manifest.values() for tid in tids}),
                )
        except Exception as exc:
            logger.warning("DESIGN: manifest computation failed: %s", exc)
            shared_file_manifest = {}
        _scaffold_existing_for_route = set(
            context.get("scaffold", {}).get("existing_target_files", [])
        )

        # CCD-302: Lane-to-file mapping
        lane_to_file_mapping: dict[int, list[str]] = {}
        if _design_lanes is not None and shared_file_manifest:
            lane_to_file_mapping = compute_lane_to_file_mapping(
                _design_lanes, shared_file_manifest,
            )

        # CCD-400: Validate wave_index populated at DESIGN time
        _tasks_without_wave = [t.task_id for t in tasks if t.wave_index is None]
        if _tasks_without_wave:
            logger.warning(
                "DESIGN: %d task(s) have no wave_index: %s",
                len(_tasks_without_wave),
                ", ".join(_tasks_without_wave[:10]),
            )

        # CCD-403: Critical-path task detection
        _critical_task_ids: set[str] = set()
        try:
            _critical_task_ids = compute_critical_path_tasks(
                tasks, shared_file_manifest,
            )
            if _critical_task_ids:
                logger.info(
                    "DESIGN: %d critical-path task(s): %s",
                    len(_critical_task_ids),
                    ", ".join(sorted(_critical_task_ids)),
                )
        except Exception as _crit_exc:
            logger.warning("DESIGN: critical-path detection failed: %s", _crit_exc)

        # CCD-200: Lane-peer design accumulator
        lane_prior_designs: list[dict[str, Any]] = []
        # CCD-303: Task title lookup for contested file annotations
        _task_title_lookup = {t.task_id: t.title for t in tasks}

        # CCD-102: Lane-sequential design iteration
        _current_lane_idx: int = -1
        if _design_lanes is not None:
            _iteration_order: list[tuple[int, SeedTask, int]] = []
            _global_idx = 0
            for _li, _lane in enumerate(_design_lanes):
                for _task in _lane:
                    _global_idx += 1
                    _iteration_order.append((_global_idx, _task, _li))
        else:
            # CCD-104: Flat iteration fallback
            _iteration_order = [
                (i, t, 0) for i, t in enumerate(tasks, start=1)
            ]

        for idx, task, _task_lane_idx in _iteration_order:
            # CCD-200: Reset lane-peer accumulator at lane boundary
            if _task_lane_idx != _current_lane_idx:
                lane_prior_designs = []
                _current_lane_idx = _task_lane_idx
            _task_span_cm = _phase_tracer.start_as_current_span(
                f"task.{task.task_id}",
                attributes={
                    "task.id": task.task_id,
                    "task.title": task.title,
                    "task.domain": task.domain or "",
                    "task.phase": "design",
                    "task.target_files": ",".join(task.target_files[:5]),
                    # CCD-601: lane-awareness attributes
                    "task.lane_index": _lane_assignments.get(task.task_id, 0),
                    "task.lane_peer_count": (
                        len(_design_lanes[_lane_assignments[task.task_id]]) - 1
                        if _design_lanes and task.task_id in _lane_assignments
                        else -1
                    ),
                    "task.shared_file_count": sum(
                        1 for tf in task.target_files
                        if _normalize_target_path(tf) in shared_file_manifest
                    ) if shared_file_manifest else 0,
                },
            )
            _task_span = _task_span_cm.__enter__()
            previous_task_started_mono = _log_task_timing(
                "DESIGN",
                task.task_id,
                idx,
                len(tasks),
                start,
                previous_task_started_mono,
            )
            _log_task_boundary_start(task, phase="design")
            # Skip tasks with env failures
            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            if env_fails:
                logger.warning(
                    "DESIGN: skipping task %s — env_blocked (%d failing check(s): %s)",
                    task.task_id,
                    len(env_fails),
                    ", ".join(c.get("check_name", "?") for c in env_fails),
                )
                design_results[task.task_id] = {
                    "status": "env_blocked",
                    "environment_issues": env_fails,
                    "prompt_version": "n/a",
                    "path_tag": "unknown",
                    "quality_outcome": "not_evaluated",
                }
                _task_span.set_attribute("task.status", "env_blocked")
                _sc = _capture_task_span_context(_task_span)
                if _sc:
                    design_results[task.task_id]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status="env_blocked",
                    phase="design",
                )
                _task_span_cm.__exit__(None, None, None)
                continue

            # ----------------------------------------------------------
            # Three-way branch: adopt / refine / fresh generation
            # ----------------------------------------------------------
            prior = prior_design_results.get(task.task_id, {})
            prior_design_text: str | None = None
            carry_forward_quality_feedback = "\n".join(
                part.strip()
                for part in [
                    str(prior.get("next_iteration_feedback", "") or ""),
                    str(prior.get("completeness_feedback", "") or ""),
                    str(prior.get("review_feedback", "") or ""),
                ]
                if part and part.strip()
            ).strip()
            task_resolved_parameters = self._collect_resolved_parameters_for_task(
                task,
                inv_resolved_parameters=inv_resolved_parameters,
                onboarding_resolved_parameters=context.get(
                    "onboarding_resolved_parameters"
                ),
                parameter_sources=context.get("parameter_sources", {}),
            )

            if (
                prior.get("status") in ("designed", "adopted")
                and prior.get("design_document")
            ):
                # R2-D6: Check whether task inputs have changed since the
                # prior design was created.  If they differ, skip auto-adoption
                # and regenerate to avoid adopting stale designs.
                _current_input_hash = hashlib.sha256(
                    json.dumps(
                        {
                            "task_id": task.task_id,
                            "description": task.description,
                            "target_files": sorted(task.target_files),
                            "constraints": sorted(task.prompt_constraints),
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                _prior_input_hash = prior.get("_task_input_hash", "")
                _inputs_changed = (
                    _prior_input_hash
                    and _current_input_hash != _prior_input_hash
                )
                if _inputs_changed:
                    logger.info(
                        "DESIGN: task inputs changed for %s since prior design "
                        "(hash %s → %s) — skipping auto-adoption, will regenerate",
                        task.task_id,
                        _prior_input_hash[:12],
                        _current_input_hash[:12],
                    )
                    # Fall through to fresh generation below
                elif self.config.refine_design:
                    # Refine mode: pass prior design to LLM for improvement
                    prior_design_text = prior["design_document"]
                    logger.info(
                        "DESIGN: will refine prior design for %s via LLM",
                        task.task_id,
                    )
                else:
                    # Adopt as-is (existing behavior)
                    adopted_entry = {
                        **prior,
                        "status": "adopted",
                        "adopted_from": "prior_design_results",
                        "prompt_version": "v2",
                        "path_tag": "variant",
                    }
                    self._apply_design_quality_gates(
                        task=task,
                        entry=adopted_entry,
                        resolved_parameters=task_resolved_parameters,
                        quality_policy_mode=quality_policy_mode,
                        dry_run=False,
                    )
                    design_results[task.task_id] = adopted_entry
                    route_decision_counts["v2"] += 1
                    if adopted_entry.get("status") == "design_failed":
                        tasks_failed += 1
                    else:
                        tasks_adopted += 1
                    if adopted_entry.get("agreed"):
                        tasks_agreed += 1
                    adopted_quality_passed = self._task_quality_passed(adopted_entry)
                    if adopted_quality_passed:
                        route_quality_counts["v2"]["passed"] += 1
                        adopted_entry["quality_outcome"] = "pass"
                    else:
                        route_quality_counts["v2"]["failed"] += 1
                        adopted_entry["quality_outcome"] = "fail"

                    doc_text = prior["design_document"]
                    if adopted_entry.get("status") != "design_failed":
                        # Feed into cross-task progressive context
                        first_line = doc_text[:300].split("\n")[0]
                        summary = f"{task.task_id} ({task.title}): {first_line}"
                        prior_summaries.append(summary)
                        # REQ-PD-007: Track completed designs for dependency injection
                        completed_designs[task.task_id] = summary
                        # CCD-200/205: Lane-peer design accumulation
                        lane_prior_designs.append({
                            "task_id": task.task_id,
                            "title": task.title,
                            "design_document": doc_text,
                        })
                    # CCD-401: Wave/lane metadata in design results
                    design_results[task.task_id].update(
                        _compute_ccd_task_metadata(
                            task, _lane_assignments, _design_lanes,
                            len(tasks), shared_file_manifest, _critical_task_ids,
                        )
                    )

                    # Copy design doc to current output_dir if configured
                    if self.output_dir:
                        out_path = Path(self.output_dir) / f"{task.task_id}-design.md"
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(doc_text, encoding="utf-8")
                        design_results[task.task_id]["output_file"] = str(out_path)

                    # PCA-605c: extract file decisions from adopted design doc
                    if doc_text and task.target_files:
                        if "discovered_target_files" not in design_results[task.task_id]:
                            _discovered = _extract_design_target_files(
                                doc_text, task.target_files,
                            )
                            if _discovered != task.target_files:
                                design_results[task.task_id]["discovered_target_files"] = _discovered
                                logger.info(
                                    "DESIGN→IMPLEMENT file propagation (adopted): task %s "
                                    "target_files expanded %s → %s",
                                    task.task_id,
                                    task.target_files,
                                    _discovered,
                                )

                    logger.info(
                        "DESIGN: adopted prior result for %s (agreed=%s, cost=$%.4f)",
                        task.task_id, prior.get("agreed"), prior.get("cost", 0.0),
                    )
                    _task_span.set_attribute(
                        "task.status",
                        str(adopted_entry.get("status", "adopted")),
                    )
                    _sc = _capture_task_span_context(_task_span)
                    if _sc:
                        design_results[task.task_id]["_span_context"] = _sc
                    _log_task_boundary_complete(
                        task.task_id,
                        status=str(adopted_entry.get("status", "adopted")),
                        phase="design",
                        cost_usd=_coerce_optional_float(
                            design_results[task.task_id].get("cost")
                        ),
                    )
                    _task_span_cm.__exit__(None, None, None)
                    continue

            if dry_run:
                dry_run_entry = {
                    "status": "dry_run_skipped",
                    "title": task.title,
                    "target_file": task.target_files[0] if task.target_files else "",
                    "constraints_count": len(task.prompt_constraints),
                    "domain": task.domain,
                    "prompt_version": "n/a",
                    "path_tag": "unknown",
                    "quality_outcome": "not_evaluated",
                    "implementation_spec": task.description,
                }
                self._apply_design_quality_gates(
                    task=task,
                    entry=dry_run_entry,
                    resolved_parameters=task_resolved_parameters,
                    quality_policy_mode=quality_policy_mode,
                    dry_run=True,
                )
                design_results[task.task_id] = dry_run_entry
                _task_span.set_attribute("task.status", "dry_run_skipped")
                _sc = _capture_task_span_context(_task_span)
                if _sc:
                    design_results[task.task_id]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status="dry_run_skipped",
                    phase="design",
                )
                _task_span_cm.__exit__(None, None, None)
                continue

            # REQ-PD-008: Wave boundary logging
            if task.wave_index is not None and task.wave_index != _prev_wave_index:
                if _prev_wave_index is not None:
                    _wave_task_count = sum(
                        1 for _, t, _ in _iteration_order
                        if t.wave_index == task.wave_index
                    )
                    logger.info(
                        "DESIGN: wave boundary %d → %d (%d tasks in wave %d)",
                        _prev_wave_index, task.wave_index,
                        _wave_task_count, task.wave_index,
                    )
                _prev_wave_index = task.wave_index

            # REQ-PD-007: Build dependency designs from completed_designs
            _dep_designs: dict[str, str] = {}
            for _dep_id in (task.depends_on or []):
                if _dep_id in completed_designs:
                    _dep_designs[_dep_id] = completed_designs[_dep_id]
                else:
                    logger.debug(
                        "DESIGN: task %s depends on %s but design not yet "
                        "available (may be in a later wave or failed)",
                        task.task_id, _dep_id,
                    )

            # REQ-PD-002/007/008/009: Build bridge_context
            _bridge_context: dict[str, Any] = {}
            if context.get("complexity_dimensions"):
                _bridge_context["complexity_dimensions"] = context["complexity_dimensions"]
            if context.get("complexity_composite") is not None:
                _bridge_context["complexity_composite"] = context["complexity_composite"]
            if _dep_designs:
                _bridge_context["dependency_designs"] = _dep_designs
            _scaffold = context.get("scaffold", {})
            if _scaffold.get("staleness_classification"):
                _bridge_context["staleness_classification"] = _scaffold["staleness_classification"]
            if context.get("wave_metadata"):
                _bridge_context["wave_metadata"] = context["wave_metadata"]
            if task.wave_index is not None:
                _bridge_context["wave_index"] = task.wave_index

            # Real-mode: run design documentation phase per task
            task_calibration = calibration_map.get(task.task_id, {})

            # Snapshot cost before this task
            backend = self._get_llm_backend()
            cost_before = backend.total_cost_usd

            # Retry loop for transient API errors (e.g. APIConnectionError, 529)
            _design_retry_config = RetryConfig(
                max_attempts=1,  # Placeholder for API compat — retry orchestration is handled by the outer _max_attempts loop with phase-aware backoff
                base_delay=5.0,
                max_delay=60.0,
                retryable_exceptions=(ConnectionError, TimeoutError, OSError),
                retryable_status_codes=(429, 500, 502, 503, 504, 529),
            )
            _max_attempts = 1 + self.config.design_task_retries
            # REQ-DSR-002: V2 is the sole path (V1 removed)
            selected_prompt_version = "v2"

            for _attempt in range(_max_attempts):
                try:
                    _wt_capture_dir: Optional[Path] = None
                    if self.config.walkthrough:
                        _wt_root = (
                            Path(context.get("project_root", ""))
                            if context.get("project_root")
                            else Path(".")
                        )
                        _wt_capture_dir = (
                            _wt_root / ".startd8" / "walkthrough"
                            / "design" / task.task_id
                        )
                    # ── V2: modular prompt + single LLM call (REQ-DSR-001) ──
                    from startd8.contractors.artisan_phases.design_prompts import (
                        assemble_design_prompt,
                    )
                    from startd8.contractors.artisan_phases.design_documentation import (
                        DesignDocument,
                    )
                    _v2_system, _v2_user, _v2_max_tokens = assemble_design_prompt(
                        task,
                        plan_goals=plan_goals,
                        architectural_context=arch_context,
                        prior_design_summaries=prior_summaries,
                        calibration=task_calibration,
                        design_max_tokens_override=self.config.design_max_tokens,
                        dependency_designs=_dep_designs,
                        scaffold_existing_files=context.get(
                            "scaffold", {},
                        ).get("existing_target_files", []),
                        staleness_classification=_scaffold.get(
                            "staleness_classification",
                        ),
                        scaffold_file_stubs=_scaffold.get("file_stubs", []),
                        scaffold_assembly_degraded=_scaffold.get(
                            "assembly_degraded", False,
                        ),
                        wave_index=task.wave_index,
                        wave_metadata=context.get("wave_metadata"),
                        parameter_sources=context.get("parameter_sources", {}),
                        semantic_conventions=context.get(
                            "semantic_conventions", {},
                        ),
                        refine_suggestions=inv_refine_suggestions,
                        open_questions=context.get("onboarding_open_questions"),
                        calibration_hints=inv_calibration_hints,
                        complexity_dimensions=context.get("complexity_dimensions"),
                        # R2-D9: Thread per-task design doc section hints to prompt
                        design_doc_sections=task.design_doc_sections,
                        prior_design_text=prior_design_text,
                        # Phase 5: Manifest context for V2 path
                        manifest_registry=_design_manifest_registry,
                        manifest_context_budget=self.config.manifest_context_budget,
                        enable_introspect=self.config.enable_introspect,
                        forward_manifest=context.get("forward_manifest"),
                    )
                    if carry_forward_quality_feedback:
                        _v2_user = (
                            _v2_user
                            + "\n\n# Prior Quality Feedback\n"
                            + carry_forward_quality_feedback
                        )
                    _high_signal_missing: list[str] = []
                    if not (
                        (task.requirements_text or "").strip()
                        or (context.get("plan_document_text") or "").strip()
                    ):
                        _high_signal_missing.append("requirements_text")
                    if not (arch_context or plan_goals):
                        _high_signal_missing.append("plan_architecture_or_project_goals")
                    if not context.get("parameter_sources"):
                        _high_signal_missing.append("critical_parameters_checklist")
                    if _high_signal_missing:
                        logger.warning(
                            "DESIGN task %s high-signal floor degraded (v2): %s",
                            task.task_id,
                            ", ".join(_high_signal_missing),
                        )
                    if _wt_capture_dir is not None:
                        _wt_capture_dir.mkdir(parents=True, exist_ok=True)
                        (_wt_capture_dir / "generate_system_prompt.md").write_text(
                            _v2_system,
                            encoding="utf-8",
                        )
                        (_wt_capture_dir / "generate_user_prompt.md").write_text(
                            _v2_user,
                            encoding="utf-8",
                        )
                        (_wt_capture_dir / "prompt_diagnostics.json").write_text(
                            json.dumps(
                                {
                                    "generate": {
                                        "kind": "design_generate",
                                        "iteration": 1,
                                        "prompt_chars": len(_v2_user),
                                        "system_prompt_chars": len(_v2_system),
                                        "prompt_tokens_estimate": len(_v2_user) // 4,
                                        "system_prompt_tokens_estimate": len(_v2_system) // 4,
                                        "max_tokens": _v2_max_tokens,
                                    }
                                },
                                indent=2,
                                default=str,
                            ),
                            encoding="utf-8",
                        )
                        _v2_raw = "[walkthrough placeholder]"
                    else:
                        _v2_raw = self._run_v2_generate(
                            backend, _v2_user, _v2_system,
                            max_tokens=_v2_max_tokens,
                            timeout=self.config.development_timeout_seconds,
                        )
                    task_cost = backend.total_cost_usd - cost_before
                    total_cost += task_cost
                    serialized = {
                        "design_document": _v2_raw,
                        "feature_name": task.title,
                        # DEPRECATED: always True after dual-review removal; use design_gate_passed
                        "agreed": True,
                        "iterations": 1,
                        "completed_at": datetime.datetime.now(
                            tz=datetime.timezone.utc,
                        ).isoformat(),
                        "prompt_version": "v2",
                        "prompt_telemetry": {
                            "total_calls": 1,
                            "calls": [
                                {
                                    "kind": "design_generate",
                                    "iteration": 1,
                                    "prompt_chars": len(_v2_user),
                                    "system_prompt_chars": len(_v2_system),
                                    "prompt_tokens_estimate": len(_v2_user) // 4,
                                    "system_prompt_tokens_estimate": len(_v2_system) // 4,
                                    "max_tokens": _v2_max_tokens,
                                }
                            ],
                        },
                    }
                    serialized["high_signal_floor_status"] = (
                        "degraded" if _high_signal_missing else "ok"
                    )
                    if _high_signal_missing:
                        serialized["high_signal_floor_missing"] = _high_signal_missing

                    # ── Post-processing ──
                    serialized["status"] = "refined" if prior_design_text else "designed"
                    serialized["cost"] = task_cost
                    serialized["prompt_version"] = "v2"
                    serialized["path_tag"] = "variant"
                    self._apply_design_quality_gates(
                        task=task,
                        entry=serialized,
                        resolved_parameters=task_resolved_parameters,
                        quality_policy_mode=quality_policy_mode,
                        dry_run=False,
                    )
                    # R2-D6: Store task input hash so future auto-adoption
                    # can detect stale designs when inputs change.
                    serialized["_task_input_hash"] = hashlib.sha256(
                        json.dumps(
                            {
                                "task_id": task.task_id,
                                "description": task.description,
                                "target_files": sorted(task.target_files),
                                "constraints": sorted(task.prompt_constraints),
                            },
                            sort_keys=True,
                        ).encode()
                    ).hexdigest()
                    design_results[task.task_id] = serialized

                    # PCA-605c: extract file decisions from design doc
                    _design_text = serialized.get("design_document", "")
                    if _design_text and task.target_files:
                        _discovered = _extract_design_target_files(
                            _design_text, task.target_files,
                        )
                        if _discovered != task.target_files:
                            design_results[task.task_id]["discovered_target_files"] = _discovered
                            logger.info(
                                "DESIGN→IMPLEMENT file propagation: task %s "
                                "target_files expanded %s → %s",
                                task.task_id,
                                task.target_files,
                                _discovered,
                            )

                    # REQ-DSR-004: design_gate_passed reflects actual quality outcome
                    _completeness_ok = bool(
                        serialized.get("parameter_completeness", {}).get("passed", True)
                    )
                    _structure_ok = bool(
                        serialized.get("structure_validation", {}).get("passed", True)
                    )
                    serialized["design_gate_passed"] = _completeness_ok and _structure_ok

                    if serialized.get("status") == "design_failed":
                        tasks_failed += 1
                    elif prior_design_text:
                        tasks_refined += 1
                    else:
                        tasks_designed += 1
                    if serialized.get("agreed"):
                        tasks_agreed += 1
                    route_decision_counts["v2"] += 1
                    task_quality_passed = self._task_quality_passed(serialized)
                    if task_quality_passed:
                        route_quality_counts["v2"]["passed"] += 1
                        serialized["quality_outcome"] = "pass"
                    else:
                        route_quality_counts["v2"]["failed"] += 1
                        serialized["quality_outcome"] = "fail"

                    # Accumulate cross-task summary for progressive context
                    doc_text = serialized.get("design_document", "")
                    if serialized.get("status") != "design_failed":
                        first_line = doc_text[:300].split("\n")[0]
                        summary = f"{task.task_id} ({task.title}): {first_line}"
                        prior_summaries.append(summary)
                        # REQ-PD-007: Track completed designs for dependency injection
                        completed_designs[task.task_id] = summary
                        # CCD-200/205: Lane-peer design accumulation
                        lane_prior_designs.append({
                            "task_id": task.task_id,
                            "title": task.title,
                            "design_document": doc_text,
                        })
                    # CCD-401: Wave/lane metadata in design results
                    design_results[task.task_id].update(
                        _compute_ccd_task_metadata(
                            task, _lane_assignments, _design_lanes,
                            len(tasks), shared_file_manifest, _critical_task_ids,
                        )
                    )

                    # Write design doc to output_dir if configured
                    if self.output_dir:
                        out_path = Path(self.output_dir) / f"{task.task_id}-design.md"
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(doc_text, encoding="utf-8")
                        design_results[task.task_id]["output_file"] = str(out_path)
                        logger.info("Wrote design doc: %s", out_path)

                    _task_span.set_attribute("task.cost", task_cost)
                    _task_span.set_attribute("task.attempts", _attempt + 1)
                    _task_span.set_attribute(
                        "task.status",
                        str(serialized.get("status", "designed")),
                    )
                    _task_span.set_attribute("task.prompt_version", selected_prompt_version)
                    # REQ-DSR-008: design_gate_passed telemetry
                    _task_span.set_attribute(
                        "design.design_gate_passed",
                        bool(serialized.get("design_gate_passed", True)),
                    )
                    break  # success — exit retry loop

                except Exception as exc:
                    if (
                        _attempt < _max_attempts - 1
                        and _is_retryable_exception(exc, _design_retry_config)
                    ):
                        _delay = _calculate_delay(_attempt, _design_retry_config)
                        logger.warning(
                            "DESIGN: task %s failed (attempt %d/%d), retrying in %.1fs: %s",
                            task.task_id,
                            _attempt + 1,
                            _max_attempts,
                            _delay,
                            exc,
                        )
                        time.sleep(_delay)
                        continue

                    # Final attempt or non-retryable — fail as before
                    task_cost = backend.total_cost_usd - cost_before
                    total_cost += task_cost
                    tasks_failed += 1
                    logger.warning(
                        "DESIGN: failed for task %s: %s", task.task_id, exc
                    )
                    design_results[task.task_id] = {
                        "status": "design_failed",
                        "error": str(exc),
                        "cost": task_cost,
                        "prompt_version": "v2",
                        "path_tag": "variant",
                        "quality_outcome": "fail",
                        "design_gate_passed": False,
                    }
                    route_decision_counts["v2"] += 1
                    route_quality_counts["v2"]["failed"] += 1
                    break  # non-retryable or final attempt — exit retry loop

            # Capture span context before closing (E6 provenance linking)
            _sc = _capture_task_span_context(_task_span)
            if _sc and task.task_id in design_results:
                design_results[task.task_id]["_span_context"] = _sc
            _design_entry = design_results.get(task.task_id, {})
            _log_task_boundary_complete(
                task.task_id,
                status=str(_design_entry.get("status", "unknown")),
                phase="design",
                cost_usd=(
                    _coerce_optional_float(_design_entry.get("cost"))
                    if isinstance(_design_entry, dict)
                    else None
                ),
            )
            # Close the per-task span after the retry loop completes
            _task_span_cm.__exit__(None, None, None)

        # REQ-PD-015: Artifact inventory extension — aggregate foundation stats
        _tasks_with_foundation = sum(
            1 for r in design_results.values()
            if isinstance(r, dict) and r.get("foundation_coverage", 0) > 0
        )
        _tasks_without_foundation = sum(
            1 for r in design_results.values()
            if isinstance(r, dict) and r.get("foundation_coverage", 0) == 0
            and r.get("status") not in ("env_blocked", "dry_run_skipped", "design_failed")
        )
        _coverages = [
            r["foundation_coverage"]
            for r in design_results.values()
            if isinstance(r, dict) and "foundation_coverage" in r
        ]
        _mean_coverage = (
            sum(_coverages) / len(_coverages) if _coverages else 0.0
        )
        # Collect all consumed fields across tasks
        _all_fields: set[str] = set()
        for r in design_results.values():
            if isinstance(r, dict):
                prov = r.get("foundation_provenance", {})
                if isinstance(prov, dict):
                    _all_fields.update(prov.get("fields_consumed", []))

        _inventory_entry = {
            "phase": "design",
            "bridge": "plan_to_design",
            "tasks_with_foundation": _tasks_with_foundation,
            "tasks_without_foundation": _tasks_without_foundation,
            "mean_foundation_coverage": round(_mean_coverage, 3),
            "fields_consumed_summary": sorted(_all_fields),
            "chain_status": context.get("_pi_design_chain_status", "unknown"),
        }
        context.setdefault("_artifact_inventory", []).append(_inventory_entry)

        context["design_results"] = design_results
        # CCD-301: Persist shared-file manifest in context
        context["shared_file_manifest"] = shared_file_manifest
        # CCD-302: Lane-to-file mapping
        context["lane_to_file_mapping"] = lane_to_file_mapping

        # B-6: Derive design_mode_summary from filesystem ground truth
        # (scaffold.existing_target_files) instead of design iteration status.
        # Used by chain 5 (design_mode_to_implement) for verifiable propagation.
        _scaffold_data = context.get("scaffold", {})
        _scaffold_existing = set(
            _scaffold_data.get("existing_target_files", [])
        )
        _task_by_id = {t.task_id: t for t in tasks}

        # H-9: On DESIGN resume (auto-load from handoff.json), scaffold may
        # not be in context.  If scaffold data is absent, mode classification
        # cannot distinguish create vs update reliably — skip overwriting
        # design_mode_summary so any previously-computed values are preserved.
        if not _scaffold_data:
            logger.warning(
                "design_mode_summary: scaffold data missing from context — "
                "mode classification may be inaccurate (DESIGN resume?). "
                "Retaining existing design_mode_summary if present."
            )
            context.setdefault("design_mode_summary_degraded", True)
            context.setdefault("design_mode_summary", {})
        else:
            context["design_mode_summary"] = {}
            for tid, entry in design_results.items():
                if not isinstance(entry, dict) or entry.get("status") in (
                    "design_failed", "env_blocked", "dry_run_skipped",
                ):
                    context["design_mode_summary"][tid] = "skipped"
                elif _task_by_id.get(tid) and any(
                    f in _scaffold_existing
                    for f in _task_by_id[tid].target_files
                ):
                    context["design_mode_summary"][tid] = "update"
                elif _task_by_id.get(tid) and getattr(
                    _task_by_id[tid], "existing_content_hash", None
                ) is not None:
                    context["design_mode_summary"][tid] = "update"
                else:
                    context["design_mode_summary"][tid] = "create"

        # ── Gaps 1-5: Handoff enrichment extraction ────────────────────
        _design_structural_delta: dict[str, dict[str, list[dict[str, str]]]] = {}
        _design_referenced_elements: dict[str, dict[str, list[str]]] = {}
        _manifest_file_checksums: dict[str, str] = {}
        _design_mode_evidence: dict[str, dict[str, Any]] = {}
        _manifest_truncation_tier: dict[str, str] = {}

        _project_root = context.get("project_root", "")

        # Build manifest element index for cross-validation (Gap 1)
        _manifest_elements: dict[str, list[str]] = {}
        if _design_manifest_registry is not None:
            try:
                for _task in tasks:
                    for _tf in _task.target_files:
                        if _tf not in _manifest_elements:
                            _summary = _design_manifest_registry.file_element_summary(
                                _tf, 500,
                            )
                            if _summary:
                                # Extract element names from summary lines
                                _elems: list[str] = []
                                for _sl in _summary.splitlines():
                                    _sl = _sl.strip()
                                    # Lines like "  ClassName(Base)" or "  func_name(x, y)"
                                    _em = re.match(r'^(\w[\w.]*)', _sl)
                                    if _em and _em.group(1) not in (
                                        "Classes", "Functions", "Imports", "Lines",
                                    ):
                                        _elems.append(_em.group(1))
                                _manifest_elements[_tf] = _elems
            except (AttributeError, TypeError, ValueError) as exc:
                logger.warning(
                    "DESIGN: manifest element index build failed: %s", exc,
                    exc_info=True,
                )

        for tid, entry in design_results.items():
            if not isinstance(entry, dict):
                continue
            doc_text = entry.get("design_document", "")
            if not doc_text or entry.get("status") in (
                "design_failed", "env_blocked", "dry_run_skipped",
            ):
                continue

            # Gap 3: Structural delta from ### Files Touched section
            try:
                delta = _extract_structural_delta(doc_text)
                if delta:
                    _design_structural_delta[tid] = delta
            except (re.error, ValueError, KeyError) as exc:
                logger.debug("DESIGN Gap 3: delta extraction failed for %s: %s", tid, exc)

            # Gap 1: Referenced elements cross-validated against manifest
            _task_manifest_elems = {}
            _task_obj = _task_by_id.get(tid)
            if _task_obj:
                for _tf in _task_obj.target_files:
                    if _tf in _manifest_elements:
                        _task_manifest_elems[_tf] = _manifest_elements[_tf]
            try:
                refs = _extract_referenced_elements(doc_text, _task_manifest_elems)
                if refs:
                    _design_referenced_elements[tid] = refs
            except (re.error, ValueError, KeyError) as exc:
                logger.debug("DESIGN Gap 1: element extraction failed for %s: %s", tid, exc)

            # Gap 4: Design mode evidence — collect signals that informed the mode
            mode = context["design_mode_summary"].get(tid, "create")
            evidence: list[str] = []
            if _task_obj:
                if any(f in _scaffold_existing for f in _task_obj.target_files):
                    evidence.append("scaffold.existing_target_files")
                if getattr(_task_obj, "existing_content_hash", None) is not None:
                    evidence.append("existing_content_hash")
            if entry.get("status") == "refined":
                evidence.append("design_status=refined")
            # Check design doc for edit signals
            doc_lower = doc_text.lower()
            if "(modify)" in doc_lower or "(update)" in doc_lower:
                evidence.append("design_doc_modify_annotation")
            if "(create)" in doc_lower or "(new)" in doc_lower:
                evidence.append("design_doc_create_annotation")
            _design_mode_evidence[tid] = {
                "mode": mode,
                "evidence": evidence,
                "reasoning": (
                    f"{len(evidence)} signal(s): {', '.join(evidence)}"
                    if evidence else "no upstream signals"
                ),
            }

        # Gap 2: Manifest file checksums for all target files at design time
        _all_target_files = list(dict.fromkeys(
            f for _task in tasks for f in _task.target_files
        ))
        _manifest_file_checksums = _compute_manifest_file_checksums(
            _all_target_files, _project_root,
        )

        # Gap 5: Record manifest truncation tier per file
        # Threshold fractions for classifying truncation fidelity
        _TIER_FULL_THRESHOLD = 0.95
        _TIER_COMPACT_THRESHOLD = 0.50
        if _design_manifest_registry is not None:
            # Ensure the "full" probe budget always exceeds the design budget
            _full_probe_budget = max(10_000, self.config.manifest_context_budget * 5)
            for _tf in _all_target_files:
                try:
                    full_summary = _design_manifest_registry.file_element_summary(
                        _tf, _full_probe_budget,
                    )
                    if not full_summary:
                        _manifest_truncation_tier[_tf] = "unavailable"
                        continue
                    budget_summary = _design_manifest_registry.file_element_summary(
                        _tf, self.config.manifest_context_budget,
                    )
                    if budget_summary and len(budget_summary) >= len(full_summary) * _TIER_FULL_THRESHOLD:
                        _manifest_truncation_tier[_tf] = "full"
                    elif budget_summary and len(budget_summary) >= len(full_summary) * _TIER_COMPACT_THRESHOLD:
                        _manifest_truncation_tier[_tf] = "compact"
                    elif budget_summary:
                        _manifest_truncation_tier[_tf] = "public_only"
                    else:
                        _manifest_truncation_tier[_tf] = "fqn_only"
                except (AttributeError, TypeError, ValueError):
                    _manifest_truncation_tier[_tf] = "unavailable"

        # Persist enrichment data in context for downstream consumption
        context["design_structural_delta"] = _design_structural_delta
        context["design_referenced_elements"] = _design_referenced_elements
        context["manifest_file_checksums"] = _manifest_file_checksums
        context["design_mode_evidence"] = _design_mode_evidence
        context["manifest_truncation_tier"] = _manifest_truncation_tier

        logger.info(
            "DESIGN enrichment: delta=%d, refs=%d, checksums=%d, "
            "evidence=%d, truncation=%d (of %d tasks)",
            len(_design_structural_delta),
            len(_design_referenced_elements),
            len(_manifest_file_checksums),
            len(_design_mode_evidence),
            len(_manifest_truncation_tier),
            len(design_results),
        )

        # CCD-500: Post-lane compatibility check
        _lane_conflicts: list[dict[str, Any]] = []
        if _design_lanes is not None and shared_file_manifest:
            try:
                from startd8.contractors.design_collision import (
                    CollisionSeverity,
                    check_lane_collisions,
                )
                for _li, _lane_tasks in enumerate(_design_lanes):
                    _lc = check_lane_collisions(
                        lane_index=_li,
                        lane_tasks=_lane_tasks,
                        design_results=design_results,
                        shared_file_manifest=shared_file_manifest,
                        design_mode_summary=context["design_mode_summary"],
                    )
                    _lane_conflicts.append(_lc.to_dict())

                # CCD-503: Apply collision resolution strategy
                _conflicting_lanes = [
                    lc for lc in _lane_conflicts
                    if lc.get("status") == "CONFLICTING"
                ]
                if _conflicting_lanes:
                    _strategy = self.config.design_collision_strategy
                    if _strategy == "warn":
                        logger.warning(
                            "DESIGN CCD-503 [warn]: %d lane(s) have CONFLICTING designs",
                            len(_conflicting_lanes),
                        )
                    elif _strategy == "abort":
                        logger.error(
                            "DESIGN CCD-503 [abort]: marking %d conflicting lane(s) "
                            "as design_failed",
                            len(_conflicting_lanes),
                        )
                        for _clc in _conflicting_lanes:
                            for _tid in _clc.get("task_ids", []):
                                design_results[_tid] = {
                                    **design_results.get(_tid, {}),
                                    "status": "design_failed",
                                    "error": (
                                        f"CCD-503 abort: design collision in lane "
                                        f"{_clc['lane_index']}"
                                    ),
                                }
            except ImportError:
                logger.debug("DESIGN: design_collision module not available — skipping")
        context["lane_conflicts"] = _lane_conflicts

        # Context contract validation runs after aggregate quality metrics
        # are computed and attached to context.

        env_blocked = sum(
            1 for r in design_results.values()
            if isinstance(r, dict) and r.get("status") == "env_blocked"
        )
        # REQ-PAQ-400: deterministic DESIGN quality metrics for gate policy.
        quality_per_task: dict[str, dict[str, Any]] = {}
        quality_failed = 0
        quality_passed = 0
        for tid, entry in design_results.items():
            status = entry.get("status", "")
            if status in ("dry_run_skipped", "env_blocked"):
                continue
            passed = self._task_quality_passed(entry)
            reason = self._task_quality_reason(entry)
            if passed:
                quality_passed += 1
            else:
                quality_failed += 1
            quality_per_task[tid] = {
                "passed": passed,
                "status": status,
                "reason": reason,
                "prompt_version": entry.get("prompt_version", "n/a"),
                "path_tag": entry.get("path_tag", "unknown"),
                "quality_outcome": "pass" if passed else "fail",
                "parameter_completeness": entry.get("parameter_completeness"),
                "structure_validation": entry.get("structure_validation"),
                "design_gate_passed": entry.get("design_gate_passed"),
            }
        quality_total = quality_passed + quality_failed
        agreement_rate = (
            quality_passed / quality_total if quality_total > 0 else 0.0
        )
        design_quality = {
            "total_passed": quality_passed,
            "total_failed": quality_failed,
            "agreement_rate": agreement_rate,
            "evaluated_task_count": quality_total,
        }
        context["design_quality"] = design_quality

        # Persist design results for auto-adoption on re-run
        # (must come AFTER quality computation so handoff contains final metrics)
        if design_results and not dry_run and self.output_dir:
            from startd8.contractors.handoff import write_design_handoff
            try:
                # R2-D3: Filter out design-failed tasks from handoff so that
                # IMPLEMENT does not receive tasks without valid design documents.
                _HANDOFF_EXCLUDE_STATUSES = frozenset({
                    "design_failed", "error", "env_blocked",
                })
                handoff_design_results = {}
                excluded_task_ids = []
                for tid, entry in design_results.items():
                    status = entry.get("status", "") if isinstance(entry, dict) else ""
                    if status in _HANDOFF_EXCLUDE_STATUSES:
                        excluded_task_ids.append(tid)
                    else:
                        handoff_design_results[tid] = entry
                if excluded_task_ids:
                    logger.warning(
                        "DESIGN: excluding %d design-failed task(s) from handoff: %s",
                        len(excluded_task_ids),
                        excluded_task_ids,
                    )

                # R2-D10: Build completed_phases dynamically from context
                # so the implementation half knows which phases actually ran.
                _handoff_completed_phases: list[str] = []
                if context.get("plan_title") or context.get("plan_goals"):
                    _handoff_completed_phases.append("plan")
                if context.get("scaffold"):
                    _handoff_completed_phases.append("scaffold")
                _handoff_completed_phases.append("design")

                handoff_path = write_design_handoff(
                    output_dir=self.output_dir,
                    enriched_seed_path=context.get("enriched_seed_path", ""),
                    project_root=context.get("project_root", ""),
                    workflow_id=context.get("workflow_id", "unknown"),
                    completed_phases=_handoff_completed_phases,
                    design_results=handoff_design_results,
                    scaffold=context.get("scaffold", {}),
                    source_checksum=context.get("source_checksum"),
                    design_mode_summary=context.get("design_mode_summary", {}),
                    shared_file_manifest=shared_file_manifest,
                    design_structural_delta=_design_structural_delta,
                    design_referenced_elements=_design_referenced_elements,
                    manifest_file_checksums=_manifest_file_checksums,
                    design_mode_evidence=_design_mode_evidence,
                    manifest_truncation_tier=_manifest_truncation_tier,
                    design_quality=design_quality,
                )
                logger.info("DESIGN: wrote handoff for auto-adoption: %s", handoff_path)
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("DESIGN: failed to write handoff: %s", exc, exc_info=True)

        prompt_calls_total = 0
        prompt_chars_total = 0
        prompt_system_chars_total = 0
        prompt_tasks_with_telemetry = 0
        prompt_dropped_field_total = 0
        prompt_truncation_event_count = 0
        for entry in design_results.values():
            if not isinstance(entry, dict):
                continue
            prompt_info = entry.get("prompt_telemetry")
            if isinstance(prompt_info, dict):
                prompt_tasks_with_telemetry += 1
                prompt_calls_total += int(prompt_info.get("total_calls", 0) or 0)
                prompt_chars_total += int(prompt_info.get("total_prompt_chars", 0) or 0)
                prompt_system_chars_total += int(
                    prompt_info.get("total_system_prompt_chars", 0) or 0
                )
                for call in prompt_info.get("calls", []):
                    if not isinstance(call, dict):
                        continue
                    ctx_budget = call.get("context_budget")
                    if not isinstance(ctx_budget, dict):
                        continue
                    dropped = int(ctx_budget.get("dropped_field_count", 0) or 0)
                    prompt_dropped_field_total += dropped
                    if ctx_budget.get("compression_steps"):
                        prompt_truncation_event_count += 1

        prompt_telemetry_summary = {
            "tasks_with_telemetry": prompt_tasks_with_telemetry,
            "prompt_calls_total": prompt_calls_total,
            "prompt_chars_total": prompt_chars_total,
            "system_prompt_chars_total": prompt_system_chars_total,
            "dropped_field_total": prompt_dropped_field_total,
            "truncation_event_count": prompt_truncation_event_count,
        }
        route_quality_summary = {
            route: {
                "passed": counts["passed"],
                "failed": counts["failed"],
                # Post-dual-review-removal: measures generation success, not reviewer agreement
                "agreement_rate": (
                    counts["passed"] / (counts["passed"] + counts["failed"])
                    if (counts["passed"] + counts["failed"]) > 0
                    else 0.0
                ),
            }
            for route, counts in route_quality_counts.items()
        }
        output: dict[str, Any] = {
            "tasks_designed": tasks_designed,
            "tasks_refined": tasks_refined,
            "tasks_adopted": tasks_adopted,
            "tasks_agreed": tasks_agreed,
            "tasks_failed": tasks_failed,
            "tasks_skipped": len(tasks) - tasks_designed - tasks_refined - tasks_adopted - tasks_failed - env_blocked,
            "total_passed": quality_passed,
            "total_failed": quality_failed,
            "agreement_rate": agreement_rate,
            "per_task": quality_per_task,
            "design_quality": design_quality,
            "route_decisions": dict(route_decision_counts),
            "route_quality": route_quality_summary,
            "prompt_telemetry": prompt_telemetry_summary,
            "total_cost": total_cost,
        }
        if self.output_dir:
            output["output_dir"] = self.output_dir

        # Context contract: validate DESIGN output model with quality payload.
        # Wrap in try-except so Pydantic validation failures respect the
        # quality gate policy (block vs warn) instead of crashing the phase.
        try:
            DesignPhaseOutput(
                design_results=context["design_results"],
                design_quality=context["design_quality"],
            )
        except Exception as _val_exc:
            _gate_mode = context.get("quality_gate_summary", {}).get(
                "policy_mode", "warn",
            )
            if _gate_mode == "block":
                raise RuntimeError(
                    f"DESIGN output validation failed (block policy): {_val_exc}"
                ) from _val_exc
            logger.warning(
                "DESIGN output validation failed (continuing per %s policy): %s",
                _gate_mode,
                _val_exc,
            )

        duration = time.monotonic() - start
        logger.info(
            "DESIGN phase complete: %d designed, %d refined, %d adopted, %d agreed, %d failed, $%.4f cost (%.2fs)",
            tasks_designed, tasks_refined, tasks_adopted, tasks_agreed, tasks_failed, total_cost, duration,
        )

        return {"output": output, "cost": total_cost, "metadata": {"duration": duration}}


# ============================================================================
# Complexity-Driven Model Router (CMR) — REQ-CMR-010, REQ-CMR-011
# ============================================================================

