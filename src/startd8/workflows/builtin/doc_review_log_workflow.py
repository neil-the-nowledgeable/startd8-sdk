"""
DocReviewLogWorkflow - Append-only multi-agent review rounds with applied/rejected memory.

This workflow is designed for iterative document improvement where:
- Multiple models review a document sequentially
- Each model appends suggestions to the bottom of the SAME document (append-only)
- Humans (or a separate workflow) validate suggestions and record dispositions:
  - Appendix A: Applied Suggestions
  - Appendix B: Rejected Suggestions (with rationale)

Key behavior:
- Reads the existing Applied/Rejected appendices to prevent re-suggesting
  already-applied or explicitly-rejected ideas.
- Appends a new "Review Round R{n}" block under Appendix C for each agent run.
- Writes a state JSON file tracking rounds and IDs to support downstream automation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from ...utils.agent_resolution import resolve_agents
from ...utils.file_operations import FileLock, atomic_write, atomic_write_json


APPENDIX_HEADING = "## Appendix: Iterative Review Log (Applied / Rejected Suggestions)"


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

def _token_usage_input(token_usage: Any) -> int:
    return int(getattr(token_usage, "input_tokens", getattr(token_usage, "input", 0)) or 0)


def _token_usage_output(token_usage: Any) -> int:
    return int(getattr(token_usage, "output_tokens", getattr(token_usage, "output", 0)) or 0)


def _token_usage_cost(token_usage: Any) -> float:
    if hasattr(token_usage, "cost") and getattr(token_usage, "cost") is not None:
        return float(getattr(token_usage, "cost"))
    if hasattr(token_usage, "cost_estimate"):
        try:
            return float(getattr(token_usage, "cost_estimate"))
        except Exception:
            return 0.0
    return 0.0


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _split_cells(row: str) -> List[str]:
    # Markdown tables: | a | b | c |
    parts = [c.strip() for c in row.strip().strip("|").split("|")]
    return parts


def _extract_table_ids(doc: str, section_heading: str) -> List[str]:
    """
    Extract IDs from the first column of a markdown table under a heading.
    """
    # Find heading
    m = re.search(rf"^{re.escape(section_heading)}\s*$", doc, re.MULTILINE)
    if not m:
        return []

    # Grab following lines
    tail = doc[m.end() :]
    lines = tail.splitlines()

    # Find first table row start
    table_lines: List[str] = []
    in_table = False
    for line in lines:
        if line.strip().startswith("|"):
            in_table = True
            table_lines.append(line)
            continue
        if in_table:
            # table ended at first non-table line
            break

    if len(table_lines) < 3:
        return []

    ids: List[str] = []
    for row in table_lines[2:]:  # skip header + separator
        cells = _split_cells(row)
        if not cells:
            continue
        first = cells[0]
        if not first or first.startswith("("):
            continue
        ids.append(first)
    return ids


def _max_review_round(doc: str) -> int:
    rounds = [int(x) for x in re.findall(r"^####\s+Review Round R(\d+)\s*$", doc, re.MULTILINE)]
    return max(rounds) if rounds else 0


def _ensure_appendix_exists(doc: str) -> str:
    if APPENDIX_HEADING in doc:
        return doc
    # Ensure a trailing newline
    base = doc.rstrip() + "\n"
    return base + "\n" + APPENDIX_TEMPLATE


def _strip_appendix_for_prompt(doc: str) -> str:
    """
    Remove the iterative review appendix from the prompt payload to keep token usage down.
    """
    idx = doc.find(APPENDIX_HEADING)
    if idx == -1:
        return doc
    return doc[:idx].rstrip() + "\n"


def _validate_snippet(snippet: str, round_number: int, max_suggestions: int) -> Tuple[bool, str, List[str]]:
    """
    Ensure the agent output is an appendable markdown snippet for Appendix C.
    """
    if not snippet or not snippet.strip():
        return False, "Empty snippet", []

    if f"#### Review Round R{round_number}" not in snippet:
        return False, f"Snippet missing required heading: '#### Review Round R{round_number}'", []

    # Extract IDs in rows
    ids = re.findall(rf"\|\s*(R{round_number}-S\d+)\s*\|", snippet)
    unique_ids = sorted(set(ids), key=lambda x: int(re.search(r"-S(\d+)$", x).group(1))) if ids else []

    if not unique_ids:
        return False, "Snippet did not contain any suggestion IDs in markdown table rows", []

    if len(unique_ids) > max_suggestions:
        return False, f"Snippet contains {len(unique_ids)} suggestions, exceeds max_suggestions={max_suggestions}", unique_ids

    # Basic safety: discourage editing other appendices
    forbidden = ["### Appendix A", "### Appendix B"]
    for f in forbidden:
        if f in snippet:
            return False, f"Snippet appears to modify {f}; only Appendix C additions are allowed", unique_ids

    return True, "ok", unique_ids


def _build_review_prompt(
    document_without_appendix: str,
    applied_ids: List[str],
    rejected_ids: List[str],
    round_number: int,
    max_suggestions: int,
) -> str:
    applied_list = ", ".join(applied_ids[:50]) if applied_ids else "(none)"
    rejected_list = ", ".join(rejected_ids[:50]) if rejected_ids else "(none)"

    return f"""You are Review Round R{round_number} for this document.

Your job: propose high-leverage improvements to the plan/document WITHOUT rewriting it.
Instead, you must append suggestions to Appendix C (Incoming Suggestions) as a new review-round block.

Hard constraints:
- Before proposing anything, consider what is already applied/rejected:
  - Applied IDs: {applied_list}
  - Rejected IDs: {rejected_list}
- Do NOT re-suggest anything already applied or rejected.
- If you want to revisit a rejected idea, explicitly reference its rejected ID and argue why the original rationale no longer applies.

Task:
- Propose up to {max_suggestions} improvements (clarity, completeness, auditability, execution safety).
- For each suggestion, include: (1) crisp description, (2) rationale, (3) where it should go.

Required output format:
- Output ONLY a markdown snippet that can be appended under:
  "### Appendix C: Incoming Suggestions (Untriaged, append-only)"
- The snippet MUST start with heading:
  "#### Review Round R{round_number}"
- Include reviewer metadata lines:
  - **Reviewer**: <agent name + model>
  - **Date**: {_now_utc_iso()}
  - **Scope**: <1 sentence>
- Then include a markdown table with rows using IDs:
  R{round_number}-S1 .. R{round_number}-S{max_suggestions}
  (You may output fewer than {max_suggestions} rows, but IDs must match the round.)

Document (excluding the review appendix):
---
{document_without_appendix}
---
"""


@dataclass
class _RoundRecord:
    round_number: int
    agent: str
    model: str
    ids: List[str]
    appended_at_utc: str


class DocReviewLogWorkflow(WorkflowBase):
    """
    Append-only sequential document review workflow with applied/rejected memory.

    Each agent produces a "Review Round" block that gets appended to the end
    of the document (Appendix C). Human triage updates Appendix A/B afterwards.
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="doc-review-log",
            name="Document Review Log Workflow",
            description=(
                "Sequential multi-agent document review that appends review rounds to the "
                "same document and maintains applied/rejected suggestion memory"
            ),
            version="1.0.0",
            capabilities=["document-review", "multi-agent", "append-only", "change-log"],
            tags=["document", "review", "appendix", "iteration"],
            requires_agents=True,
            agent_count=AgentCount.CONFIGURABLE,
            min_agents=1,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="document_path",
                    type="string",
                    required=True,
                    description="Path to the markdown document to append review rounds to",
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=True,
                    description="Agents (provider:model) to run sequentially; each agent becomes a new review round",
                ),
                WorkflowInput(
                    name="max_suggestions",
                    type="number",
                    required=False,
                    default=10,
                    description="Maximum number of suggestions per review round",
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
                    description="Optional path for the workflow state JSON (defaults to <doc_dir>/.startd8/doc_review_state.json)",
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

        agents = config.get("agents", [])
        if not agents or not isinstance(agents, list):
            errors.append("agents must be a non-empty list")

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

        # Resolve agents (workflow requires sequential list)
        resolved_agents = agents or []
        if not resolved_agents:
            resolved_agents = resolve_agents(config["agents"])

        doc_path = Path(str(config["document_path"])).expanduser().resolve()
        init_if_missing = bool(config.get("init_if_missing", True))
        max_suggestions = int(config.get("max_suggestions", 10))

        default_state_path = doc_path.parent / ".startd8" / "doc_review_state.json"
        state_path = Path(config.get("state_path") or default_state_path).expanduser().resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        lock_path = doc_path.parent / ".startd8" / "doc_review.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        step_results: List[StepResult] = []
        round_records: List[_RoundRecord] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        total_time_ms = 0

        with FileLock(lock_path):
            try:
                doc_text = doc_path.read_text(encoding="utf-8")
            except Exception as e:
                return WorkflowResult.from_error(self.metadata.workflow_id, f"Failed to read document: {e}")

            if init_if_missing:
                doc_text = _ensure_appendix_exists(doc_text)

            applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
            rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")
            next_round = _max_review_round(doc_text) + 1

            total_rounds = len(resolved_agents)
            self._emit_progress(on_progress, 0, total_rounds, f"Starting {total_rounds} review round(s)")

            for i, agent in enumerate(resolved_agents):
                round_number = next_round + i
                step_name = f"review_round_R{round_number}"

                self._emit_progress(on_progress, i, total_rounds, f"Generating Round R{round_number} with {agent.name}")

                doc_without_appendix = _strip_appendix_for_prompt(doc_text)
                prompt = _build_review_prompt(
                    document_without_appendix=doc_without_appendix,
                    applied_ids=applied_ids,
                    rejected_ids=rejected_ids,
                    round_number=round_number,
                    max_suggestions=max_suggestions,
                )

                try:
                    response_text, time_ms, token_usage = agent.generate(prompt)
                except Exception as e:
                    step_results.append(
                        StepResult(
                            step_name=step_name,
                            agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                            output="",
                            time_ms=0,
                            error=str(e),
                        )
                    )
                    break

                input_tokens = _token_usage_input(token_usage) if token_usage else 0
                output_tokens = _token_usage_output(token_usage) if token_usage else 0
                cost = _token_usage_cost(token_usage) if token_usage else 0.0

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

                # Append snippet (ensure we don't jam against prior content)
                appended = "\n\n" + response_text.strip() + "\n"
                doc_text = doc_text.rstrip() + appended

                # Update in-memory "seen" IDs so later rounds don't re-suggest
                applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
                rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")

                record = _RoundRecord(
                    round_number=round_number,
                    agent=agent.name,
                    model=getattr(agent, "model", ""),
                    ids=ids,
                    appended_at_utc=_now_utc_iso(),
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

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_cost += cost
                total_time_ms += time_ms

                # Persist document after each round (fail-fast / incremental state)
                try:
                    atomic_write(doc_path, doc_text, mode="w", backup=True)
                except Exception as e:
                    step_results[-1].error = f"Failed to write document: {e}"
                    break

                # Persist state after each round
                try:
                    state = {
                        "document_path": str(doc_path),
                        "updated_at_utc": _now_utc_iso(),
                        "applied_ids": applied_ids,
                        "rejected_ids": rejected_ids,
                        "rounds": [
                            {
                                "round": r.round_number,
                                "agent": r.agent,
                                "model": r.model,
                                "ids": r.ids,
                                "appended_at_utc": r.appended_at_utc,
                            }
                            for r in round_records
                        ],
                    }
                    atomic_write_json(state_path, state, indent=2, sort_keys=False)
                except Exception:
                    # Best-effort; don't fail the workflow on state write
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
                "note": "Triage suggestions by updating Appendix A (applied) / Appendix B (rejected with rationale).",
            },
            metrics=metrics,
            steps=step_results,
            error=None if success else "One or more review rounds failed; see steps for details",
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "agents_count": len(resolved_agents),
                "max_suggestions": max_suggestions,
                "init_if_missing": init_if_missing,
            },
        )

