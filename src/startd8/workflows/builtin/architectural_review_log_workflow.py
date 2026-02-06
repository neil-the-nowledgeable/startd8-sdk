"""
ArchitecturalReviewLogWorkflow - High-quality sequential architectural review with append-only review rounds.

This workflow is a strategic variation of doc-review-log:
- Defaults to 1+ flagship models (high quality) when agents are not explicitly provided
- Runs models sequentially (one after another)
- Appends suggestions to the SAME document (Appendix C) in an append-only fashion
- Uses Applied/Rejected appendices as memory so later reviewers avoid re-suggesting rejected/applied items
- Enforces a strict suggestion-table schema to keep feedback actionable and triage-ready
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
from ...model_catalog import Models, list_models_by_tier
from ...utils.agent_resolution import resolve_agents
from ...utils.file_operations import FileLock, atomic_write, atomic_write_json


APPENDIX_HEADING = "## Appendix: Iterative Review Log (Applied / Rejected Suggestions)"

# This matches the appendix scaffold we already introduced in target docs.
APPENDIX_TEMPLATE = """---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future models don’t re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
"""


ALLOWED_AREAS = {
    "architecture",
    "interfaces",
    "data",
    "risks",
    "validation",
    "ops",
    "security",
}

ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}

REQUIRED_COLUMNS = [
    "ID",
    "Area",
    "Severity",
    "Suggestion",
    "Rationale",
    "Proposed Placement",
    "Validation Approach",
]

def _token_usage_input(token_usage: Any) -> int:
    """
    Normalize token usage input count across SDK versions/providers.

    StartD8 TokenUsage uses `input`/`output`. Some older callers used
    `input_tokens`/`output_tokens`.
    """
    return int(getattr(token_usage, "input_tokens", getattr(token_usage, "input", 0)) or 0)


def _token_usage_output(token_usage: Any) -> int:
    return int(getattr(token_usage, "output_tokens", getattr(token_usage, "output", 0)) or 0)


def _token_usage_cost(token_usage: Any) -> float:
    # Prefer explicit cost if present, otherwise TokenUsage.cost_estimate property.
    if hasattr(token_usage, "cost") and getattr(token_usage, "cost") is not None:
        return float(getattr(token_usage, "cost"))
    if hasattr(token_usage, "cost_estimate"):
        try:
            return float(getattr(token_usage, "cost_estimate"))
        except Exception:
            return 0.0
    return 0.0


def _is_openai_agent(agent: BaseAgent) -> bool:
    mod = getattr(agent.__class__, "__module__", "") or ""
    return ".agents.openai" in mod or mod.endswith("agents.openai")


def _looks_like_model_not_found_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("model" in msg and ("not found" in msg or "not available" in msg or "does not exist" in msg))


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _split_cells(row: str) -> List[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _ensure_appendix_exists(doc: str) -> str:
    if APPENDIX_HEADING in doc:
        return doc
    return doc.rstrip() + "\n\n" + APPENDIX_TEMPLATE


def _strip_appendix_for_prompt(doc: str) -> str:
    idx = doc.find(APPENDIX_HEADING)
    if idx == -1:
        return doc
    return doc[:idx].rstrip() + "\n"


def _max_review_round(doc: str) -> int:
    rounds = [int(x) for x in re.findall(r"^####\s+Review Round R(\d+)\s*$", doc, re.MULTILINE)]
    return max(rounds) if rounds else 0


def _extract_table_ids(doc: str, section_heading: str) -> List[str]:
    m = re.search(rf"^{re.escape(section_heading)}\s*$", doc, re.MULTILINE)
    if not m:
        return []
    tail = doc[m.end() :]
    lines = tail.splitlines()

    table_lines: List[str] = []
    in_table = False
    for line in lines:
        if line.strip().startswith("|"):
            in_table = True
            table_lines.append(line)
            continue
        if in_table:
            break

    if len(table_lines) < 3:
        return []

    ids: List[str] = []
    for row in table_lines[2:]:
        cells = _split_cells(row)
        if not cells:
            continue
        first = cells[0]
        if not first or first.startswith("("):
            continue
        ids.append(first)
    return ids


def _select_default_agents(
    quality_tier: str,
    reviewer_count: int,
    providers: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    Select default models by tier from the model catalog.

    Returns a list of agent specs in provider:model format.
    """
    tier = (quality_tier or "flagship").strip().lower()

    # For strategic architectural review, prefer an explicit high-quality trio by default.
    # IMPORTANT: Preserve this explicit ordering (do not sort it away), so the
    # default run is: Opus -> Gemini Pro -> GPT-5.2 Codex.
    preferred: List[str] = []
    if tier == "flagship":
        preferred = [
            Models.CLAUDE_OPUS_LATEST,
            Models.GEMINI_PRO_LATEST,
            Models.GPT5_2_CODEX_LATEST,
        ]

    # Apply provider allowlist to preferred first (preserving order)
    allowed: Optional[set[str]] = None
    if providers:
        allowed = {p.strip().lower() for p in providers if p and p.strip()}
        preferred = [m for m in preferred if m.split(":", 1)[0].lower() in allowed]

    if len(preferred) >= reviewer_count:
        return preferred[:reviewer_count]

    # Fill remaining slots from tier registry (stable, provider-prioritized)
    remainder = [m for m in list_models_by_tier(tier) if m not in preferred]
    if allowed is not None:
        remainder = [m for m in remainder if m.split(":", 1)[0].lower() in allowed]

    priority = {"anthropic": 0, "gemini": 1, "openai": 2}
    remainder.sort(key=lambda full: (priority.get(full.split(":", 1)[0].lower(), 99), full))

    return (preferred + remainder)[:reviewer_count]


def _build_prompt(
    document_without_appendix: str,
    applied_ids: List[str],
    rejected_ids: List[str],
    round_number: int,
    max_suggestions: int,
    reviewer_label: str,
    scope: str,
    template_override: Optional[str] = None,
) -> str:
    """
    Build the reviewer prompt. Supports override template that must include:
    - {round_number}, {max_suggestions}, {applied_ids}, {rejected_ids}, {document}, {reviewer_label}, {scope}
    """
    applied_list = ", ".join(applied_ids[:50]) if applied_ids else "(none)"
    rejected_list = ", ".join(rejected_ids[:50]) if rejected_ids else "(none)"

    if template_override:
        return template_override.format(
            round_number=round_number,
            max_suggestions=max_suggestions,
            applied_ids=applied_list,
            rejected_ids=rejected_list,
            document=document_without_appendix,
            reviewer_label=reviewer_label,
            scope=scope,
        )

    cols = " | ".join(REQUIRED_COLUMNS)
    sep = " | ".join(["----"] * len(REQUIRED_COLUMNS))

    return f"""You are an expert enterprise architect performing a strategic architectural review.

You are Review Round R{round_number}. You MUST output ONLY an appendable markdown snippet for Appendix C.

Before proposing anything:
- Applied IDs (do not repeat): {applied_list}
- Rejected IDs (do not repeat): {rejected_list}
- If you want to revisit a rejected idea, explicitly reference its rejected ID and argue why the original rationale no longer applies.

Your task:
- Propose up to {max_suggestions} high-leverage improvements to this plan/document.
- Focus on: architecture clarity, execution safety, risk management, validation completeness, and operational readiness.
- Do NOT rewrite the document. Do NOT modify Appendix A or Appendix B.

Required output format (append-only snippet):
- Start with:
  #### Review Round R{round_number}
- Then include:
  - **Reviewer**: {reviewer_label}
  - **Date**: {_now_utc()}
  - **Scope**: {scope}
- Then output a markdown table EXACTLY with these columns:
  | {cols} |
  | {sep} |
  Rows must use IDs R{round_number}-S1..R{round_number}-S{max_suggestions} (you may output fewer rows).
  Area must be one of: Architecture, Interfaces, Data, Risks, Validation, Ops, Security.
  Severity must be one of: critical, high, medium, low.

Document (excluding the review appendix):
---
{document_without_appendix}
---
"""


def _validate_snippet(snippet: str, round_number: int, max_suggestions: int) -> Tuple[bool, str, List[str]]:
    """
    Validate agent output is a safe, append-only review-round block with required table schema.
    """
    if not snippet or not snippet.strip():
        return False, "Empty snippet", []

    if f"#### Review Round R{round_number}" not in snippet:
        return False, f"Missing required heading: '#### Review Round R{round_number}'", []

    # Disallow attempts to edit other appendices
    for forbidden in ("### Appendix A", "### Appendix B"):
        if forbidden in snippet:
            return False, f"Snippet appears to modify {forbidden}; only Appendix C additions are allowed", []

    # Find the first markdown table and validate header
    lines = [ln.rstrip() for ln in snippet.strip().splitlines() if ln.strip()]
    table_start = None
    for idx, ln in enumerate(lines):
        if ln.strip().startswith("|") and "ID" in ln:
            table_start = idx
            break
    if table_start is None or table_start + 1 >= len(lines):
        return False, "Missing required markdown table", []

    header = _split_cells(lines[table_start])
    if header != REQUIRED_COLUMNS:
        return False, f"Table header mismatch. Expected columns: {REQUIRED_COLUMNS}", []

    # Require separator row after header
    sep = lines[table_start + 1]
    if not sep.strip().startswith("|"):
        return False, "Missing table separator row", []

    # Extract IDs and validate enums from rows
    ids: List[str] = []
    for ln in lines[table_start + 2 :]:
        if not ln.strip().startswith("|"):
            break
        cells = _split_cells(ln)
        if len(cells) != len(REQUIRED_COLUMNS):
            return False, "Table row has wrong column count", ids

        suggestion_id = cells[0]
        ids.append(suggestion_id)

        # Validate ID pattern
        if not re.fullmatch(rf"R{round_number}-S\d+", suggestion_id):
            return False, f"Invalid suggestion ID '{suggestion_id}' for round R{round_number}", ids

        # Validate area and severity values
        area = cells[1].strip().lower()
        severity = cells[2].strip().lower()
        if area not in ALLOWED_AREAS:
            return False, f"Invalid Area '{cells[1]}' (allowed: {sorted(ALLOWED_AREAS)})", ids
        if severity not in ALLOWED_SEVERITIES:
            return False, f"Invalid Severity '{cells[2]}' (allowed: {sorted(ALLOWED_SEVERITIES)})", ids

    unique_ids = sorted(set(ids), key=lambda x: int(re.search(r"-S(\d+)$", x).group(1)) if re.search(r"-S(\d+)$", x) else 9999)
    if not unique_ids:
        return False, "No suggestion rows found in table", []
    if len(unique_ids) > max_suggestions:
        return False, f"Too many suggestions: {len(unique_ids)} > {max_suggestions}", unique_ids

    return True, "ok", unique_ids


@dataclass
class _RoundRecord:
    round_number: int
    agent: str
    model: str
    ids: List[str]
    appended_at_utc: str
    cost: float


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
                    default=3,
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
                    name="fallback_openai_model",
                    type="string",
                    required=False,
                    default="openai:gpt-4o",
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
        started_at = datetime.now(timezone.utc)

        doc_path = Path(str(config["document_path"])).expanduser().resolve()
        init_if_missing = bool(config.get("init_if_missing", True))
        max_suggestions = int(config.get("max_suggestions", 10))
        scope = str(config.get("scope") or "").strip() or "Architecture-focused review"

        warn_cost_usd = config.get("warn_cost_usd")
        max_cost_usd = config.get("max_cost_usd")
        fallback_openai_model = str(config.get("fallback_openai_model") or "openai:gpt-4o").strip()
        fallback_on_model_not_found = bool(config.get("fallback_on_model_not_found", True))

        default_state_path = doc_path.parent / ".startd8" / "architectural_review_state.json"
        state_path = Path(config.get("state_path") or default_state_path).expanduser().resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        lock_path = doc_path.parent / ".startd8" / "architectural_review.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

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
            reviewer_count = int(config.get("reviewer_count", 2))
            default_specs = _select_default_agents(quality_tier, reviewer_count, providers)
            resolved_agents = resolve_agents(default_specs)

        if not resolved_agents:
            return WorkflowResult.from_error(self.metadata.workflow_id, "No agents available for architectural review")

        step_results: List[StepResult] = []
        round_records: List[_RoundRecord] = []

        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        total_time_ms = 0

        with FileLock(lock_path):
            doc_text = doc_path.read_text(encoding="utf-8")
            if init_if_missing:
                doc_text = _ensure_appendix_exists(doc_text)

            applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
            rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")
            next_round = _max_review_round(doc_text) + 1

            total_rounds = len(resolved_agents)
            self._emit_progress(on_progress, 0, total_rounds, f"Starting {total_rounds} architectural review round(s)")

            template_override = config.get("review_template")

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
                )

                # Execute generation with graceful error handling and OpenAI model fallback
                try:
                    response_text, time_ms, token_usage = agent.generate(prompt)
                except Exception as e:
                    # If OpenAI model is unavailable, retry once with a fallback model (default gpt-4o)
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
                            response_text, time_ms, token_usage = fallback_agent.generate(prompt)
                            agent = fallback_agent  # record agent/model that actually ran
                        except Exception as e2:
                            step_results.append(
                                StepResult(
                                    step_name=step_name,
                                    agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                                    output="",
                                    time_ms=0,
                                    input_tokens=0,
                                    output_tokens=0,
                                    cost=0.0,
                                    error=str(e2),
                                )
                            )
                            break
                    else:
                        step_results.append(
                            StepResult(
                                step_name=step_name,
                                agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                                output="",
                                time_ms=0,
                                input_tokens=0,
                                output_tokens=0,
                                cost=0.0,
                                error=str(e),
                            )
                        )
                        break

                input_tokens = _token_usage_input(token_usage) if token_usage else 0
                output_tokens = _token_usage_output(token_usage) if token_usage else 0
                cost = _token_usage_cost(token_usage) if token_usage else 0.0

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_cost += cost
                total_time_ms += time_ms

                if warn_cost_usd is not None and total_cost >= float(warn_cost_usd):
                    self._emit_progress(
                        on_progress,
                        i,
                        total_rounds,
                        f"Cost warning: cumulative ${total_cost:.2f} >= warn_cost_usd=${float(warn_cost_usd):.2f}",
                    )

                if max_cost_usd is not None and total_cost >= float(max_cost_usd):
                    step_results.append(
                        StepResult(
                            step_name=step_name,
                            agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                            output="",
                            time_ms=time_ms,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost=cost,
                            error=f"Max cost exceeded: ${total_cost:.2f} >= max_cost_usd=${float(max_cost_usd):.2f}",
                        )
                    )
                    break

                ok, message, ids = _validate_snippet(response_text, round_number, max_suggestions)
                if not ok:
                    step_results.append(
                        StepResult(
                            step_name=step_name,
                            agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                            output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                            time_ms=time_ms,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost=cost,
                            error=f"Invalid snippet: {message}",
                        )
                    )
                    break

                # Append snippet and persist
                doc_text = doc_text.rstrip() + "\n\n" + response_text.strip() + "\n"
                atomic_write(doc_path, doc_text, mode="w", backup=True)

                # Update memory from current doc for next round
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

                step_results.append(
                    StepResult(
                        step_name=step_name,
                        agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                        output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                        time_ms=time_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                        error=None,
                    )
                )

                # State file (best-effort)
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
                        "cumulative_cost_usd": total_cost,
                    }
                    atomic_write_json(state_path, state, indent=2, sort_keys=False)
                except Exception:
                    pass

                self._emit_progress(on_progress, i + 1, total_rounds, f"Appended Round R{round_number}")

        completed_at = datetime.now(timezone.utc)
        success = bool(round_records) and all(s.error is None for s in step_results)

        metrics = WorkflowMetrics(
            total_time_ms=total_time_ms,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_cost=total_cost,
            step_count=len(step_results),
        )

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=success,
            output={
                "document_path": str(doc_path),
                "rounds_appended": len(round_records),
                "round_numbers": [r.round_number for r in round_records],
                "state_path": str(state_path),
                "cumulative_cost_usd": total_cost,
            },
            metrics=metrics,
            steps=step_results,
            error=None if success else "Architectural review did not complete successfully; see steps for details",
            started_at=started_at,
            completed_at=completed_at,
        )

