"""
ArchitecturalReviewLogWorkflow - High-quality sequential architectural review with append-only review rounds.

This workflow is a strategic variation of doc-review-log:
- Defaults to 1+ flagship models (high quality) when agents are not explicitly provided
- Runs models sequentially (one after another)
- Appends suggestions to the SAME document (Appendix C) in an append-only fashion
- Uses Applied/Rejected appendices as memory so later reviewers avoid re-suggesting rejected/applied items
- Enforces a strict suggestion-table schema to keep feedback actionable and triage-ready

Implementation is split across companion modules:
- architectural_review_log_constants.py — constants, utilities, dataclasses
- architectural_review_log_prompts.py   — prompt builders (YAML-backed)
- architectural_review_log_helpers.py   — validation, parsing, document mutation
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..base import WorkflowBase, ProgressCallback
from ..models import (
    WorkflowMetadata,
    WorkflowInput,
    WorkflowResult,
    WorkflowMetrics,
    StepResult,
    AgentCount,
    ValidationResult,
)
from ...agents import BaseAgent
from ...exceptions import GeminiSafetyFilterError
from ...logging_config import get_logger
from ...utils.agent_resolution import resolve_agents
from ...utils.file_operations import FileLock, atomic_write, atomic_write_json

# ---------------------------------------------------------------------------
# Re-export all public & private symbols that tests and other modules import
# directly from this module.  This preserves backward compatibility.
# ---------------------------------------------------------------------------

from .architectural_review_log_constants import (  # noqa: F401 — re-exports
    RELAXED_SAFETY_SETTINGS,
    APPENDIX_HEADING,
    APPENDIX_TEMPLATE,
    ALLOWED_AREAS,
    _AREA_ALIASES,
    _normalize_area,
    REVIEW_PROFILES,
    ALLOWED_SEVERITIES,
    CORE_COLUMNS,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    _OPTIONAL_COLUMN_DEFAULT,
    _MAX_DISPLAYED_IDS,
    _KNOWN_TIERS,
    _is_agent_type,
    _is_openai_agent,
    _is_gemini_agent,
    _is_anthropic_agent,
    _looks_like_model_not_found_error,
    _relaxed_safety,
    _extract_token_metrics,
    _select_default_agents,
    _now_utc,
    _strip_code_fences,
    _strip_json_fences,
    _split_cells,
    _is_separator_row,
    _normalize_header,
    _ensure_appendix_exists,
    _strip_appendix_for_prompt,
    _agent_label,
    _make_error_step,
    _MetricsAccumulator,
    _RoundRecord,
)

from .architectural_review_log_prompts import (  # noqa: F401 — re-exports
    _build_prompt,
    _build_triage_prompt,
    _build_shared_system_prompt,
    _build_apply_prompt,
    _build_untriaged_block,
)

from .architectural_review_log_helpers import (  # noqa: F401 — re-exports
    _max_review_round,
    _extract_table_ids,
    _extract_untriaged_suggestions,
    _validate_snippet,
    _validate_triage_output,
    _validate_apply_output,
    _apply_triage_decisions,
    _insert_appendix_rows,
    _compute_substantially_addressed,
    _build_id_to_area_map,
    _compute_substantially_addressed_from_doc,
    _compute_area_coverage,
    _insert_areas_needing_review_section,
    _insert_substantially_addressed_section,
    _extract_accepted_suggestions_for_apply,
    _apply_suggestions_to_doc,
    _extract_reviewer_sources,
    _fix_snippet_ids,
    _get_feature_doc_path,
    _extract_feature_snippet,
)

_logger = get_logger(__name__)


class ArchitecturalReviewLogWorkflow(WorkflowBase):
    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="architectural-review-log",
            name="Architectural Review Log Workflow",
            description=(
                "High-quality sequential architectural review. Uses flagship models by default "
                "and appends structured suggestions to the document's review appendix."
            ),
            version="1.0.0",
            capabilities=["document-review", "architecture", "multi-agent", "append-only"],
            tags=["architecture", "review", "appendix", "premium"],
            requires_agents=False,  # can select default agents from model catalog
            agent_count=AgentCount.CONFIGURABLE,
            min_agents=0,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="document_path",
                    type="string",
                    required=True,
                    description="Path to the markdown document to append architectural review rounds to",
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=False,
                    description="Optional explicit agents (provider:model) to run sequentially; overrides default selection",
                ),
                WorkflowInput(
                    name="quality_tier",
                    type="string",
                    required=False,
                    default="flagship",
                    description="Default model tier when agents not specified: flagship|balanced|fast|mini",
                ),
                WorkflowInput(
                    name="providers",
                    type="string_list",
                    required=False,
                    description="Optional provider allowlist for default selection (e.g., ['anthropic','gemini'])",
                ),
                WorkflowInput(
                    name="reviewer_count",
                    type="number",
                    required=False,
                    default=2,
                    description="Number of default high-quality reviewers to run when agents not specified",
                ),
                WorkflowInput(
                    name="max_suggestions",
                    type="number",
                    required=False,
                    default=10,
                    description="Maximum number of suggestions per review round",
                ),
                WorkflowInput(
                    name="scope",
                    type="string",
                    required=False,
                    default="Improve plan clarity, auditability, and execution safety (architecture-focused).",
                    description="One-sentence scope statement inserted into the review round metadata",
                ),
                WorkflowInput(
                    name="init_if_missing",
                    type="boolean",
                    required=False,
                    default=True,
                    description="If true, initializes the Applied/Rejected/Incoming appendix structure when missing",
                ),
                WorkflowInput(
                    name="state_path",
                    type="string",
                    required=False,
                    description="Optional path for workflow state JSON (defaults to <doc_dir>/.startd8/architectural_review_state.json)",
                ),
                WorkflowInput(
                    name="warn_cost_usd",
                    type="number",
                    required=False,
                    description="Warn if cumulative cost exceeds this amount (USD)",
                ),
                WorkflowInput(
                    name="max_cost_usd",
                    type="number",
                    required=False,
                    description="Fail-fast if cumulative cost exceeds this amount (USD)",
                ),
                WorkflowInput(
                    name="review_template",
                    type="text",
                    required=False,
                    description="Optional prompt template override (must include required placeholders)",
                ),
                WorkflowInput(
                    name="context_files",
                    type="array",
                    required=False,
                    description=(
                        "List of file or directory paths to include as reference material in the reviewer prompt. "
                        "Directories are scanned recursively for .md files. "
                        "Use for lessons learned, design docs, or prior decisions."
                    ),
                ),
                WorkflowInput(
                    name="max_context_chars",
                    type="number",
                    required=False,
                    default=200_000,
                    description="Maximum total characters of context file content to include (default 200000)",
                ),
                WorkflowInput(
                    name="fallback_openai_model",
                    type="string",
                    required=False,
                    default="openai:gpt-4.1",
                    description=(
                        "If the configured OpenAI model is not available (e.g., access denied / model not found), "
                        "retry the round once with this fallback model."
                    ),
                ),
                WorkflowInput(
                    name="fallback_on_model_not_found",
                    type="boolean",
                    required=False,
                    default=True,
                    description="If true, retries OpenAI rounds with fallback_openai_model on model-not-found errors.",
                ),
                WorkflowInput(
                    name="gemini_safety_settings",
                    type="array",
                    required=False,
                    description=(
                        "Custom Gemini safety_settings applied to all Gemini reviewers. "
                        "Each entry: {category: 'HARM_CATEGORY_*', threshold: 'BLOCK_NONE'|'BLOCK_ONLY_HIGH'|...}. "
                        "When not set, Gemini uses its default filters (with automatic relaxation on SAFETY retry)."
                    ),
                ),
                WorkflowInput(
                    name="enable_triage",
                    type="boolean",
                    required=False,
                    default=True,
                    description="Enable automated triage step after all reviewers to classify suggestions as ACCEPT/REJECT",
                ),
                WorkflowInput(
                    name="enable_apply",
                    type="boolean",
                    required=False,
                    default=True,
                    description=(
                        "Enable apply-suggestions step after triage to integrate accepted suggestions "
                        "into the document body. Requires enable_triage=True."
                    ),
                ),
                WorkflowInput(
                    name="enable_prompt_caching",
                    type="boolean",
                    required=False,
                    default=True,
                    description=(
                        "Enable prompt caching for Anthropic agents. Moves the document body "
                        "into a system prompt for ~90%% input cost reduction on cache hits."
                    ),
                ),
                WorkflowInput(
                    name="substantially_addressed_threshold",
                    type="number",
                    required=False,
                    default=3,
                    description="Minimum accepted suggestions per area to mark it as 'substantially addressed'",
                ),
                WorkflowInput(
                    name="review_profile",
                    type="string",
                    required=False,
                    default="architecture",
                    description="Review profile to use (architecture|requirements|design)",
                ),
                WorkflowInput(
                    name="custom_review_profile",
                    type="object",
                    required=False,
                    description="Custom review profile object with keys: areas (list), persona (str), focus (str)",
                ),
                WorkflowInput(
                    name="feature_requirements",
                    type="array",
                    required=False,
                    description="List of paths to feature requirement documents (markdown). Enables dual-doc review mode.",
                ),
            ],
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        errors: List[str] = []
        doc_path = config.get("document_path")
        if not doc_path:
            errors.append("document_path is required")
        else:
            p = Path(str(doc_path)).expanduser()
            if not p.exists() or not p.is_file():
                errors.append(f"document_path does not exist or is not a file: {p}")

        reviewer_count = config.get("reviewer_count", 2)
        if reviewer_count is not None and (not isinstance(reviewer_count, int) or reviewer_count < 1 or reviewer_count > 5):
            errors.append("reviewer_count must be an int between 1 and 5")

        max_suggestions = config.get("max_suggestions", 10)
        if not isinstance(max_suggestions, int) or max_suggestions < 1 or max_suggestions > 25:
            errors.append("max_suggestions must be an int between 1 and 25")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Run the architectural review workflow.

        Sequentially executes review rounds (one per agent), validates and
        appends each reviewer's suggestions to the document's Appendix C,
        then optionally runs automated triage to classify suggestions into
        Appendix A (applied) or Appendix B (rejected).

        All document mutations are protected by a file lock to prevent
        concurrent writes.
        """
        started_at = datetime.now(timezone.utc)

        doc_path = Path(str(config["document_path"])).expanduser().resolve()
        init_if_missing = bool(config.get("init_if_missing", True))
        max_suggestions = int(config.get("max_suggestions", 10))
        scope = str(config.get("scope") or "").strip() or "Architecture-focused review"

        warn_cost_usd = config.get("warn_cost_usd")
        max_cost_usd = config.get("max_cost_usd")
        fallback_openai_model = str(config.get("fallback_openai_model") or "openai:gpt-4.1").strip()
        fallback_on_model_not_found = bool(config.get("fallback_on_model_not_found", True))

        default_state_path = doc_path.parent / ".startd8" / "architectural_review_state.json"
        state_path = Path(config.get("state_path") or default_state_path).expanduser().resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        lock_path = doc_path.parent / ".startd8" / "architectural_review.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Resolve review profile
        profile_name = config.get("review_profile", "architecture")
        custom_profile = config.get("custom_review_profile")

        # Default to architecture if unknown profile name
        base_profile = REVIEW_PROFILES.get(profile_name, REVIEW_PROFILES["architecture"])

        # Allow custom override
        if custom_profile and isinstance(custom_profile, dict):
            allowed_areas = set(custom_profile.get("areas", base_profile["areas"]))
            persona = custom_profile.get("persona", base_profile["persona"])
            focus = custom_profile.get("focus", base_profile["focus"])
        else:
            allowed_areas = base_profile["areas"]
            persona = base_profile["persona"]
            focus = base_profile["focus"]

        # Resolve agents: explicit list in config OR provided agents param OR default selection
        resolved_agents: List[BaseAgent] = []
        explicit_specs = config.get("agents") or []
        if agents:
            resolved_agents = agents
        elif explicit_specs:
            resolved_agents = resolve_agents(explicit_specs)
        else:
            quality_tier = str(config.get("quality_tier") or "flagship")
            providers = config.get("providers")
            reviewer_count = int(config.get("reviewer_count", 2))  # matches default in metadata
            default_specs = _select_default_agents(quality_tier, reviewer_count, providers)
            resolved_agents = resolve_agents(default_specs)

        if not resolved_agents:
            return WorkflowResult.from_error(self.metadata.workflow_id, "No agents available for architectural review")

        # Apply caller-provided Gemini safety_settings to all Gemini agents
        gemini_safety = config.get("gemini_safety_settings")
        if gemini_safety:
            for ag in resolved_agents:
                if _is_gemini_agent(ag) and hasattr(ag, "safety_settings"):
                    ag.safety_settings = gemini_safety

        # Enable Anthropic prompt caching for input cost reduction
        enable_caching = bool(config.get("enable_prompt_caching", True))
        if enable_caching:
            for ag in resolved_agents:
                if _is_anthropic_agent(ag) and hasattr(ag, "enable_prompt_caching"):
                    ag.enable_prompt_caching = True

        step_results: List[StepResult] = []
        round_records: List[_RoundRecord] = []
        totals = _MetricsAccumulator()

        with FileLock(lock_path):
            # Load Feature Requirements (Dual-Document Mode)
            feature_reqs = config.get("feature_requirements")
            feature_doc_path = _get_feature_doc_path(feature_reqs)
            requirements_content = ""
            if feature_doc_path:
                try:
                    requirements_content = feature_doc_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as e:
                    _logger.warning("Failed to read feature requirements doc: %s", e, exc_info=True)

            doc_text = doc_path.read_text(encoding="utf-8")
            if init_if_missing:
                doc_text = _ensure_appendix_exists(doc_text)

                # Also initialize feature doc if present
                if feature_doc_path:
                    try:
                        fd_text = feature_doc_path.read_text(encoding="utf-8")
                        fd_text = _ensure_appendix_exists(fd_text)
                        atomic_write(feature_doc_path, fd_text, mode="w", backup=True)
                    except (OSError, UnicodeDecodeError) as e:
                        _logger.warning("Failed to initialize feature doc appendix: %s", e)

            applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
            rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")
            next_round = _max_review_round(doc_text) + 1

            total_rounds = len(resolved_agents)
            self._emit_progress(on_progress, 0, total_rounds, f"Starting {total_rounds} architectural review round(s)")

            template_override = config.get("review_template")

            # Load context files (lessons learned, design docs, prior decisions)
            context_files = config.get("context_files") or []
            context_content = ""
            if context_files:
                max_context_chars = int(config.get("max_context_chars", 200_000))
                parts: List[str] = []
                for cf in context_files:
                    p = Path(str(cf)).expanduser().resolve()
                    if p.is_file():
                        try:
                            parts.append(f"### {p.name}\n\n{p.read_text(encoding='utf-8')}")
                        except (OSError, UnicodeDecodeError) as e:
                            _logger.warning("Failed to read context file %s: %s", p, e, exc_info=True)
                    elif p.is_dir():
                        for md_file in sorted(p.glob("**/*.md")):
                            try:
                                parts.append(
                                    f"### {md_file.relative_to(p)}\n\n"
                                    f"{md_file.read_text(encoding='utf-8')}"
                                )
                            except (OSError, UnicodeDecodeError) as e:
                                _logger.warning("Failed to read context file %s: %s", md_file, e, exc_info=True)
                context_content = "\n\n".join(parts)
                if len(context_content) > max_context_chars:
                    context_content = context_content[:max_context_chars] + "\n\n[... truncated ...]"

            # Compute substantially addressed areas and per-area coverage from existing Appendix A
            sa_threshold = int(config.get("substantially_addressed_threshold", 3))
            substantially_addressed = _compute_substantially_addressed_from_doc(doc_text, sa_threshold, allowed_areas=allowed_areas)
            coverage = _compute_area_coverage(doc_text, sa_threshold, allowed_areas=allowed_areas)

            # Build shared system prompt for prompt caching (document + context + requirements)
            shared_system_prompt: Optional[str] = None
            use_sp = enable_caching and not template_override  # skip caching with custom templates
            if use_sp:
                shared_system_prompt = _build_shared_system_prompt(
                    document_without_appendix=_strip_appendix_for_prompt(doc_text),
                    context_content=context_content,
                    requirements_content=requirements_content or "",
                )

            for i, agent in enumerate(resolved_agents):
                round_number = next_round + i
                step_name = f"architectural_review_R{round_number}"

                reviewer_label = f"{agent.name} ({getattr(agent, 'model', '')})"
                self._emit_progress(on_progress, i, total_rounds, f"Running Round R{round_number} with {reviewer_label}")

                prompt = _build_prompt(
                    document_without_appendix=_strip_appendix_for_prompt(doc_text),
                    applied_ids=applied_ids,
                    rejected_ids=rejected_ids,
                    round_number=round_number,
                    max_suggestions=max_suggestions,
                    reviewer_label=reviewer_label,
                    scope=scope,
                    template_override=template_override,
                    context_content=context_content,
                    substantially_addressed_areas=substantially_addressed,
                    area_coverage=coverage,
                    allowed_areas=allowed_areas,
                    persona=persona,
                    focus_guidance=focus,
                    requirements_content=requirements_content,
                    has_feature_requirements=bool(feature_doc_path),
                    use_system_prompt=use_sp,
                )

                # Build generate kwargs (system_prompt for caching)
                gen_kwargs: Dict[str, Any] = {}
                if shared_system_prompt is not None:
                    gen_kwargs["system_prompt"] = shared_system_prompt

                # Execute generation with graceful error handling, Gemini SAFETY
                # retry, and OpenAI model fallback.
                try:
                    response_text, time_ms, token_usage = agent.generate(prompt, **gen_kwargs)

                except GeminiSafetyFilterError as safety_err:
                    _logger.warning(
                        "Gemini SAFETY filter hit for R%d (%s); "
                        "prompt_tokens=%s, safety_ratings=%s; "
                        "attempting reduced-context retry",
                        round_number,
                        reviewer_label,
                        safety_err.prompt_tokens,
                        safety_err.safety_ratings,
                    )
                    self._emit_progress(
                        on_progress, i, total_rounds,
                        f"Gemini SAFETY filter on R{round_number}; retrying with reduced context",
                    )

                    reduced_prompt = _build_prompt(
                        document_without_appendix=_strip_appendix_for_prompt(doc_text),
                        applied_ids=applied_ids,
                        rejected_ids=rejected_ids,
                        round_number=round_number,
                        max_suggestions=max_suggestions,
                        reviewer_label=reviewer_label,
                        scope=scope,
                        template_override=template_override,
                        context_content="",  # drop context files
                        allowed_areas=allowed_areas,
                        persona=persona,
                        focus_guidance=focus,
                    )

                    try:
                        response_text, time_ms, token_usage = agent.generate(reduced_prompt)
                    except GeminiSafetyFilterError:
                        _logger.warning(
                            "Reduced-context retry still blocked; retrying with relaxed safety_settings",
                        )
                        self._emit_progress(
                            on_progress, i, total_rounds,
                            f"R{round_number}: retrying with relaxed safety settings",
                        )
                        try:
                            with _relaxed_safety(agent):
                                response_text, time_ms, token_usage = agent.generate(reduced_prompt)
                        except Exception as e3:
                            _logger.warning(
                                "Gemini SAFETY retry exhausted for R%d; skipping reviewer",
                                round_number,
                            )
                            self._emit_progress(
                                on_progress, i, total_rounds,
                                f"R{round_number}: skipping {reviewer_label} after repeated SAFETY blocks",
                            )
                            step_results.append(_make_error_step(
                                step_name, agent,
                                f"Gemini SAFETY filter (skipped): {e3}",
                            ))
                            continue

                except Exception as e:
                    if (
                        fallback_on_model_not_found
                        and fallback_openai_model
                        and _is_openai_agent(agent)
                        and _looks_like_model_not_found_error(e)
                    ):
                        self._emit_progress(
                            on_progress,
                            i,
                            total_rounds,
                            f"OpenAI model unavailable ({getattr(agent, 'model', '')}); retrying with {fallback_openai_model}",
                        )
                        try:
                            fallback_agent = resolve_agents([fallback_openai_model])[0]
                            response_text, time_ms, token_usage = fallback_agent.generate(prompt, **gen_kwargs)
                            agent = fallback_agent
                        except Exception as e2:
                            step_results.append(_make_error_step(step_name, agent, str(e2)))
                            continue
                    else:
                        step_results.append(_make_error_step(step_name, agent, str(e)))
                        continue

                input_tokens, output_tokens, cost = _extract_token_metrics(token_usage)
                totals.add(input_tokens, output_tokens, cost, time_ms)

                if warn_cost_usd is not None and totals.cost >= float(warn_cost_usd):
                    self._emit_progress(
                        on_progress,
                        i,
                        total_rounds,
                        f"Cost warning: cumulative ${totals.cost:.2f} >= warn_cost_usd=${float(warn_cost_usd):.2f}",
                    )

                if max_cost_usd is not None and totals.cost >= float(max_cost_usd):
                    step_results.append(_make_error_step(
                        step_name, agent,
                        f"Max cost exceeded: ${totals.cost:.2f} >= max_cost_usd=${float(max_cost_usd):.2f}",
                        time_ms=time_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                    ))
                    break

                response_text = _strip_code_fences(response_text)

                if feature_doc_path:
                    feature_snippet = _extract_feature_snippet(
                        response_text,
                        round_number,
                        reviewer_label,
                        scope,
                    )
                    if feature_snippet:
                        try:
                            curr_feat = feature_doc_path.read_text(encoding="utf-8")
                            updated_feat = curr_feat.rstrip() + "\n\n" + feature_snippet + "\n"
                            atomic_write(feature_doc_path, updated_feat, mode="w", backup=True)
                        except (OSError, UnicodeDecodeError) as e:
                            _logger.warning("Failed to append feature suggestions: %s", e, exc_info=True)

                ok, message, ids = _validate_snippet(response_text, round_number, max_suggestions, allowed_areas=allowed_areas)
                if not ok:
                    _logger.warning(
                        "Validation failed for R%d (%s): %s",
                        round_number,
                        reviewer_label,
                        message,
                    )

                    retry_prompt = (
                        f"Your previous response failed validation: {message}\n\n"
                        f"Please regenerate the review snippet for Round R{round_number}. "
                        f"Requirements:\n"
                        f"- Start with: #### Review Round R{round_number}\n"
                        f"- Table header row EXACTLY (plain text, no bold): | {' | '.join(REQUIRED_COLUMNS)} |\n"
                        f"- IDs: R{round_number}-S1, R{round_number}-S2, etc.\n"
                        f"- Area must be one of: {', '.join(sorted(ALLOWED_AREAS))}\n"
                        f"- Severity must be one of: {', '.join(sorted(ALLOWED_SEVERITIES))}\n"
                        f"- Do NOT wrap output in code blocks (no ```)\n\n"
                        f"Original prompt:\n{prompt}"
                    )
                    self._emit_progress(
                        on_progress, i, total_rounds,
                        f"R{round_number}: validation failed ({message}); retrying",
                    )
                    try:
                        retry_text, retry_time_ms, retry_token_usage = agent.generate(retry_prompt, **gen_kwargs)
                        retry_text = _strip_code_fences(retry_text)
                        retry_input, retry_output, retry_cost = _extract_token_metrics(retry_token_usage)
                        totals.add(retry_input, retry_output, retry_cost, retry_time_ms)

                        ok2, message2, ids = _validate_snippet(retry_text, round_number, max_suggestions, allowed_areas=allowed_areas)
                        if ok2:
                            _logger.info(
                                "Validation retry succeeded for R%d (%s)",
                                round_number,
                                reviewer_label,
                            )
                            response_text = retry_text
                            time_ms += retry_time_ms
                            input_tokens += retry_input
                            output_tokens += retry_output
                            cost += retry_cost
                        else:
                            _logger.warning(
                                "Validation retry also failed for R%d (%s): %s; skipping reviewer",
                                round_number,
                                reviewer_label,
                                message2,
                            )
                            step_results.append(_make_error_step(
                                step_name, agent,
                                f"Invalid snippet after retry: {message2}",
                                output=retry_text[:500] + "..." if len(retry_text) > 500 else retry_text,
                                time_ms=time_ms + retry_time_ms,
                                input_tokens=input_tokens + retry_input,
                                output_tokens=output_tokens + retry_output,
                                cost=cost + retry_cost,
                            ))
                            continue
                    except Exception as retry_err:
                        _logger.warning(
                            "Validation retry call failed for R%d (%s): %s; skipping reviewer",
                            round_number,
                            reviewer_label,
                            retry_err,
                        )
                        step_results.append(_make_error_step(
                            step_name, agent,
                            f"Validation retry failed: {retry_err}",
                            output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                            time_ms=time_ms,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost=cost,
                        ))
                        continue

                response_text = _fix_snippet_ids(response_text, round_number)
                ids = [re.sub(r"R\d+-([SF]\d+)", rf"R{round_number}-\1", sid) for sid in ids]

                doc_text = doc_text.rstrip() + "\n\n" + response_text.strip() + "\n"
                atomic_write(doc_path, doc_text, mode="w", backup=True)

                applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
                rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")

                record = _RoundRecord(
                    round_number=round_number,
                    agent=agent.name,
                    model=getattr(agent, "model", ""),
                    ids=ids,
                    appended_at_utc=_now_utc(),
                    cost=cost,
                )
                round_records.append(record)

                step_results.append(StepResult(
                    step_name=step_name,
                    agent_name=_agent_label(agent),
                    output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                    time_ms=time_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    error=None,
                ))

                try:
                    state = {
                        "document_path": str(doc_path),
                        "updated_at_utc": _now_utc(),
                        "applied_ids": applied_ids,
                        "rejected_ids": rejected_ids,
                        "rounds": [
                            {
                                "round": r.round_number,
                                "agent": r.agent,
                                "model": r.model,
                                "ids": r.ids,
                                "appended_at_utc": r.appended_at_utc,
                                "cost": r.cost,
                            }
                            for r in round_records
                        ],
                        "cumulative_cost_usd": totals.cost,
                    }
                    atomic_write_json(state_path, state, indent=2, sort_keys=False)
                except Exception as e:
                    _logger.warning("Failed to write state file %s: %s", state_path, e, exc_info=True)

                self._emit_progress(on_progress, i + 1, total_rounds, f"Appended Round R{round_number}")

            # ── Automated Triage Step ──────────────────────────────────────
            enable_triage = bool(config.get("enable_triage", True))
            triage_decisions: List[Dict[str, Any]] = []
            untriaged: List[Dict[str, Any]] = []
            triage_info: Dict[str, Any] = {
                "enabled": enable_triage,
                "accepted": 0,
                "rejected": 0,
                "feature_accepted": 0,
                "feature_rejected": 0,
                "untriaged_remaining": [],
                "substantially_addressed_areas": [],
                "areas_needing_review": [],
            }

            if enable_triage and round_records and resolved_agents:
                triage_agent = resolved_agents[0]

                applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
                rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")

                untriaged, endorsements = _extract_untriaged_suggestions(doc_text, applied_ids, rejected_ids)

                if untriaged:
                    self._emit_progress(on_progress, total_rounds, total_rounds, "Running automated triage")
                    untriaged_ids = [s["id"] for s in untriaged]
                    untriaged_block = _build_untriaged_block(untriaged)
                    reviewer_sources = _extract_reviewer_sources(doc_text)

                    triage_prompt = _build_triage_prompt(
                        document_without_appendix=_strip_appendix_for_prompt(doc_text),
                        applied_ids=applied_ids,
                        rejected_ids=rejected_ids,
                        untriaged_block=untriaged_block,
                        endorsement_counts=endorsements,
                        allowed_areas=allowed_areas,
                        persona=persona,
                        has_feature_suggestions=bool(feature_doc_path),
                        use_system_prompt=use_sp,
                    )

                    triage_gen_kwargs: Dict[str, Any] = {}
                    if shared_system_prompt is not None:
                        triage_gen_kwargs["system_prompt"] = shared_system_prompt

                    triage_ok = False
                    triage_decisions: List[Dict[str, Any]] = []
                    triage_missing: List[str] = []

                    try:
                        triage_text, triage_time_ms, triage_token_usage = triage_agent.generate(triage_prompt, **triage_gen_kwargs)
                    except GeminiSafetyFilterError:
                        _logger.warning("Triage blocked by Gemini SAFETY filter; retrying with relaxed settings")
                        try:
                            with _relaxed_safety(triage_agent):
                                triage_text, triage_time_ms, triage_token_usage = triage_agent.generate(triage_prompt, **triage_gen_kwargs)
                        except Exception as triage_err:
                            _logger.warning("Triage failed after retry: %s", triage_err)
                            step_results.append(_make_error_step(
                                "triage", triage_agent, f"Triage failed: {triage_err}",
                            ))
                            triage_text = None
                            triage_time_ms = 0
                            triage_token_usage = None
                    except Exception as triage_err:
                        _logger.warning("Triage failed: %s", triage_err)
                        step_results.append(_make_error_step(
                            "triage", triage_agent, f"Triage failed: {triage_err}",
                        ))
                        triage_text = None
                        triage_time_ms = 0
                        triage_token_usage = None

                    if triage_text is not None:
                        triage_input_tokens, triage_output_tokens, triage_cost = _extract_token_metrics(triage_token_usage)
                        totals.add(triage_input_tokens, triage_output_tokens, triage_cost, triage_time_ms)

                        triage_ok, triage_msg, triage_decisions, triage_missing = _validate_triage_output(
                            triage_text, untriaged_ids, allowed_areas=allowed_areas
                        )

                        if not triage_ok:
                            _logger.warning("Triage validation failed: %s", triage_msg)
                            retry_prompt = (
                                f"Your previous triage response failed validation: {triage_msg}\n\n"
                                f"Please output ONLY a JSON array with entries for each suggestion. "
                                f"Required fields: id, decision (ACCEPT or REJECT), summary, rationale, "
                                f"area (one of: {', '.join(sorted(allowed_areas))}).\n\n"
                                f"Suggestions to triage:\n{untriaged_block}"
                            )
                            try:
                                retry_text, retry_time_ms, retry_token_usage = triage_agent.generate(retry_prompt, **triage_gen_kwargs)
                                retry_input, retry_output, retry_cost = _extract_token_metrics(retry_token_usage)
                                totals.add(retry_input, retry_output, retry_cost, retry_time_ms)
                                triage_input_tokens += retry_input
                                triage_output_tokens += retry_output
                                triage_cost += retry_cost
                                triage_time_ms += retry_time_ms

                                triage_ok, triage_msg, triage_decisions, triage_missing = _validate_triage_output(
                                    retry_text, untriaged_ids, allowed_areas=allowed_areas
                                )
                                if not triage_ok:
                                    _logger.warning("Triage retry also failed: %s", triage_msg)
                            except Exception as retry_err:
                                _logger.warning("Triage retry call failed: %s", retry_err)

                        if triage_decisions:
                            plan_decisions = [d for d in triage_decisions if "F" not in d["id"]]
                            feature_decisions = [d for d in triage_decisions if "F" in d["id"]]

                            if plan_decisions:
                                doc_text = _apply_triage_decisions(doc_text, plan_decisions, reviewer_sources)

                                applied_with_area = [(d["id"], d["area"]) for d in plan_decisions if d["decision"] == "ACCEPT"]
                                prev_addressed = _compute_substantially_addressed_from_doc(doc_text, sa_threshold, allowed_areas=allowed_areas)
                                for area, ids in prev_addressed.items():
                                    for sid in ids:
                                        if (sid, area) not in applied_with_area:
                                            applied_with_area.append((sid, area))
                                addressed = _compute_substantially_addressed(applied_with_area, sa_threshold)

                                if addressed:
                                    doc_text = _insert_substantially_addressed_section(doc_text, addressed)
                                    triage_info["substantially_addressed_areas"] = list(addressed.keys())

                                post_triage_coverage = _compute_area_coverage(doc_text, sa_threshold, allowed_areas=allowed_areas)
                                doc_text = _insert_areas_needing_review_section(doc_text, post_triage_coverage, sa_threshold)
                                areas_needing = [
                                    area for area, info in post_triage_coverage.items()
                                    if not info["addressed"]
                                ]
                                triage_info["areas_needing_review"] = sorted(areas_needing)

                                atomic_write(doc_path, doc_text, mode="w", backup=True)

                            if feature_decisions and feature_doc_path:
                                try:
                                    fd_text = feature_doc_path.read_text(encoding="utf-8")
                                    fd_text = _ensure_appendix_exists(fd_text)
                                    fd_text = _apply_triage_decisions(fd_text, feature_decisions, reviewer_sources)
                                    atomic_write(feature_doc_path, fd_text, mode="w", backup=True)

                                    triage_info["feature_accepted"] = sum(1 for d in feature_decisions if d["decision"] == "ACCEPT")
                                    triage_info["feature_rejected"] = sum(1 for d in feature_decisions if d["decision"] == "REJECT")
                                except (OSError, UnicodeDecodeError) as e:
                                    _logger.warning("Failed to apply feature triage: %s", e, exc_info=True)

                            accepted_count = sum(1 for d in triage_decisions if d["decision"] == "ACCEPT")
                            rejected_count = sum(1 for d in triage_decisions if d["decision"] == "REJECT")
                            triage_info["accepted"] = accepted_count
                            triage_info["rejected"] = rejected_count
                            triage_info["untriaged_remaining"] = triage_missing
                            triage_info["decisions"] = triage_decisions

                        step_results.append(StepResult(
                            step_name="triage",
                            agent_name=_agent_label(triage_agent),
                            output=f"Accepted: {triage_info['accepted']}, Rejected: {triage_info['rejected']}, Remaining: {len(triage_missing)}",
                            time_ms=triage_time_ms,
                            input_tokens=triage_input_tokens,
                            output_tokens=triage_output_tokens,
                            cost=triage_cost,
                            error=None if triage_decisions else f"Triage validation failed: {triage_msg}",
                            metadata={
                                "accepted": triage_info["accepted"],
                                "rejected": triage_info["rejected"],
                                "untriaged_remaining": triage_missing,
                            },
                        ))

            # ── Apply Suggestions Step ────────────────────────────────────
            enable_apply = bool(config.get("enable_apply", True))
            apply_info: Dict[str, Any] = {
                "enabled": enable_apply and enable_triage,
                "applied_count": 0,
                "applied_ids": [],
                "warning_ids": [],
                "feature_applied_count": 0,
                "error": None,
            }

            if enable_apply and enable_triage and triage_info["accepted"] > 0 and resolved_agents:
                apply_agent = resolved_agents[0]
                self._emit_progress(on_progress, total_rounds, total_rounds, "Applying accepted suggestions to document")

                plan_accepted = _extract_accepted_suggestions_for_apply(
                    [d for d in triage_decisions if "-S" in d.get("id", "")] if triage_decisions else [],
                    untriaged,
                )

                if plan_accepted:
                    try:
                        (
                            updated_doc, apply_ok, apply_msg, apply_warnings,
                            apply_time_ms, apply_input, apply_output, apply_cost,
                        ) = _apply_suggestions_to_doc(
                            doc_text, plan_accepted, apply_agent,
                            persona=persona,
                            system_prompt=shared_system_prompt,
                        )
                        totals.add(apply_input, apply_output, apply_cost, apply_time_ms)

                        if apply_ok:
                            doc_text = updated_doc
                            atomic_write(doc_path, doc_text, mode="w", backup=True)
                            apply_info["applied_count"] = len(plan_accepted)
                            apply_info["applied_ids"] = [s["id"] for s in plan_accepted]
                            apply_info["warning_ids"] = apply_warnings
                        else:
                            _logger.warning("Apply validation failed: %s; retrying", apply_msg)
                            try:
                                (
                                    updated_doc, apply_ok, apply_msg, apply_warnings,
                                    r_time, r_in, r_out, r_cost,
                                ) = _apply_suggestions_to_doc(
                                    doc_text, plan_accepted, apply_agent,
                                    persona=persona,
                                    system_prompt=shared_system_prompt,
                                )
                                totals.add(r_in, r_out, r_cost, r_time)
                                apply_time_ms += r_time
                                apply_input += r_in
                                apply_output += r_out
                                apply_cost += r_cost

                                if apply_ok:
                                    doc_text = updated_doc
                                    atomic_write(doc_path, doc_text, mode="w", backup=True)
                                    apply_info["applied_count"] = len(plan_accepted)
                                    apply_info["applied_ids"] = [s["id"] for s in plan_accepted]
                                    apply_info["warning_ids"] = apply_warnings
                                else:
                                    apply_info["error"] = f"Retry also failed: {apply_msg}"
                            except Exception as retry_err:
                                _logger.warning("Apply retry failed: %s", retry_err, exc_info=True)
                                apply_info["error"] = f"Apply retry failed: {retry_err}"

                        step_results.append(StepResult(
                            step_name="apply_suggestions",
                            agent_name=_agent_label(apply_agent),
                            output=f"Applied: {apply_info['applied_count']}, Warnings: {len(apply_info['warning_ids'])}",
                            time_ms=apply_time_ms,
                            input_tokens=apply_input,
                            output_tokens=apply_output,
                            cost=apply_cost,
                            error=apply_info["error"],
                            metadata={
                                "applied_count": apply_info["applied_count"],
                                "applied_ids": apply_info["applied_ids"],
                                "warning_ids": apply_info["warning_ids"],
                            },
                        ))

                    except GeminiSafetyFilterError:
                        _logger.warning("Apply step blocked by Gemini SAFETY filter; retrying with relaxed settings")
                        try:
                            with _relaxed_safety(apply_agent):
                                (
                                    updated_doc, apply_ok, apply_msg, apply_warnings,
                                    apply_time_ms, apply_input, apply_output, apply_cost,
                                ) = _apply_suggestions_to_doc(
                                    doc_text, plan_accepted, apply_agent,
                                    persona=persona,
                                    system_prompt=shared_system_prompt,
                                )
                            totals.add(apply_input, apply_output, apply_cost, apply_time_ms)
                            if apply_ok:
                                doc_text = updated_doc
                                atomic_write(doc_path, doc_text, mode="w", backup=True)
                                apply_info["applied_count"] = len(plan_accepted)
                                apply_info["applied_ids"] = [s["id"] for s in plan_accepted]
                                apply_info["warning_ids"] = apply_warnings
                        except Exception as e2:
                            _logger.warning("Apply SAFETY retry failed: %s", e2, exc_info=True)
                            apply_info["error"] = f"Apply SAFETY retry failed: {e2}"
                        if apply_info.get("error"):
                            step_results.append(_make_error_step(
                                "apply_suggestions", apply_agent,
                                apply_info["error"],
                            ))
                        else:
                            step_results.append(StepResult(
                                step_name="apply_suggestions",
                                agent_name=_agent_label(apply_agent),
                                output=f"Applied: {apply_info['applied_count']} (SAFETY retry), Warnings: {len(apply_info['warning_ids'])}",
                                time_ms=apply_time_ms,
                                input_tokens=apply_input,
                                output_tokens=apply_output,
                                cost=apply_cost,
                                error=None,
                                metadata={
                                    "applied_count": apply_info["applied_count"],
                                    "applied_ids": apply_info["applied_ids"],
                                    "warning_ids": apply_info["warning_ids"],
                                    "safety_retry": True,
                                },
                            ))
                    except Exception as apply_err:
                        _logger.warning("Apply step failed: %s", apply_err, exc_info=True)
                        apply_info["error"] = str(apply_err)
                        step_results.append(_make_error_step(
                            "apply_suggestions", apply_agent, str(apply_err),
                        ))

                if feature_doc_path and triage_info.get("feature_accepted", 0) > 0:
                    feature_accepted = _extract_accepted_suggestions_for_apply(
                        [d for d in triage_decisions if "-F" in d.get("id", "")] if triage_decisions else [],
                        untriaged,
                    )
                    if feature_accepted:
                        try:
                            fd_text = feature_doc_path.read_text(encoding="utf-8")
                            (
                                updated_fd, fd_ok, fd_msg, fd_warns,
                                fd_time, fd_in, fd_out, fd_cost,
                            ) = _apply_suggestions_to_doc(
                                fd_text, feature_accepted, apply_agent,
                                persona=persona,
                                system_prompt=None,
                            )
                            totals.add(fd_in, fd_out, fd_cost, fd_time)
                            if fd_ok:
                                atomic_write(feature_doc_path, updated_fd, mode="w", backup=True)
                                apply_info["feature_applied_count"] = len(feature_accepted)
                        except Exception as e:
                            _logger.warning("Failed to apply suggestions to feature doc: %s", e, exc_info=True)

            # Update state file with triage + apply info
            try:
                applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
                rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")
                state = {
                    "document_path": str(doc_path),
                    "updated_at_utc": _now_utc(),
                    "applied_ids": applied_ids,
                    "rejected_ids": rejected_ids,
                    "rounds": [
                        {
                            "round": r.round_number,
                            "agent": r.agent,
                            "model": r.model,
                            "ids": r.ids,
                            "appended_at_utc": r.appended_at_utc,
                            "cost": r.cost,
                        }
                        for r in round_records
                    ],
                    "cumulative_cost_usd": totals.cost,
                    "triage": triage_info,
                    "apply": apply_info,
                }
                atomic_write_json(state_path, state, indent=2, sort_keys=False)
            except Exception as e:
                _logger.warning("Failed to write state file %s: %s", state_path, e, exc_info=True)

        completed_at = datetime.now(timezone.utc)
        success = bool(round_records) and all(
            s.error is None for s in step_results
            if s.step_name not in ("triage", "apply_suggestions")
        )

        metrics = WorkflowMetrics(
            total_time_ms=totals.time_ms,
            input_tokens=totals.input_tokens,
            output_tokens=totals.output_tokens,
            total_cost=totals.cost,
            step_count=len(step_results),
        )

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=success,
            output={
                "document_path": str(doc_path),
                "feature_document_path": str(feature_doc_path) if feature_doc_path else None,
                "rounds_appended": len(round_records),
                "round_numbers": [r.round_number for r in round_records],
                "state_path": str(state_path),
                "cumulative_cost_usd": totals.cost,
                "triage": triage_info,
                "apply": apply_info,
            },
            metrics=metrics,
            steps=step_results,
            error=None if success else "Architectural review did not complete successfully; see steps for details",
            started_at=started_at,
            completed_at=completed_at,
        )
