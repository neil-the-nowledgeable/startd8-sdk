"""
Plain Language Workflow.

Simplifies complex content (analyses, legal documents, technical reports)
into clear, jargon-free explanations accessible to general audiences.
"""

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from startd8.agents import BaseAgent
from startd8.agents.pool import TimeoutConfig
from startd8.costs.pricing import PricingService
from startd8.utils.retry import RetryConfig
from startd8.utils.agent_resolution import resolve_agent_spec, resolve_agents
from startd8.workflows.base import WorkflowBase, ProgressCallback
from startd8.workflows.models import (
    AgentCount,
    StepResult,
    ValidationResult,
    WorkflowInput,
    WorkflowMetadata,
    WorkflowMetrics,
    WorkflowResult,
)

from .plain_language_models import (
    AgentSimplification,
    ContentType,
    JargonTerm,
    KeyPoint,
    PlainLanguageOutput,
    PlainLanguageResult,
    ReadingLevel,
    SimplificationInput,
    SimplificationMode,
    get_reading_level_description,
    parse_content_type,
    parse_reading_level,
)


# ============================================================================
# Prompt Templates
# ============================================================================


SIMPLIFY_PROMPT_TEMPLATE = """You are an expert at explaining complex topics in plain, simple language that anyone can understand.

## Content to Simplify

Title: {title}
Type: {content_type}

---
{content}
---

## Your Task

Transform this content into clear, jargon-free explanations that would make sense to {reading_level_description}

**Key principles:**
- Use everyday words instead of technical terms
- Keep sentences short and direct
- Use concrete examples and analogies
- Focus on what matters to real people
- Explain the "so what?" - why this matters
- Avoid passive voice and bureaucratic language
- If you must use a technical term, define it immediately in simple words

## Required Output Format

Respond ONLY with valid JSON in exactly this structure:

```json
{{
  "one_sentence_summary": "<capture the essence in ONE clear sentence>",
  "one_paragraph_summary": "<expand to one paragraph with key context>",
  "key_points": [
    {{
      "point_number": 1,
      "original_concept": "<what the original text said>",
      "simplified": "<plain language version>",
      "importance": "<critical|important|context>"
    }}
  ],
  "plain_explanation": "<full plain-language explanation, multiple paragraphs if needed>",
  "bottom_line": "<the single most important takeaway - start with 'The bottom line is...'>",
  "who_is_affected": "<who this impacts and how it affects their daily lives>",
  "action_items": [
    "<specific things readers can or should do>"
  ],
  "glossary": [
    {{
      "term": "<technical term>",
      "definition": "<simple definition>",
      "context": "<how it's used here>"
    }}
  ]
}}
```

Remember: If your explanation requires expertise to understand, simplify further.
"""


SYNTHESIS_PROMPT_TEMPLATE = """You are synthesizing multiple plain-language explanations of the same content into a single, best version.

## Original Content Summary

Title: {title}
Type: {content_type}

## Agent Explanations

{agent_explanations}

## Your Task

Create a synthesized version that:
1. Takes the clearest, most accessible phrasing from each agent
2. Combines the best key points without repetition
3. Uses the simplest language that accurately conveys the meaning
4. Keeps the most helpful analogies and examples
5. Merges glossary terms, keeping the clearest definitions

## Required Output Format

Respond ONLY with valid JSON matching the same structure as the input explanations:

```json
{{
  "one_sentence_summary": "<best single sentence>",
  "one_paragraph_summary": "<best paragraph>",
  "key_points": [...],
  "plain_explanation": "<synthesized full explanation>",
  "bottom_line": "<clearest bottom line>",
  "who_is_affected": "<combined affected parties>",
  "action_items": [...],
  "glossary": [...]
}}
```
"""


# ============================================================================
# Workflow Implementation
# ============================================================================


class PlainLanguageWorkflow(WorkflowBase):
    """
    Plain language simplification workflow.

    Transforms complex content into clear, jargon-free explanations
    accessible to general audiences.

    Supports:
    - Single agent mode (default): One agent simplifies the content
    - Multi-agent mode: Multiple agents simplify, then synthesize best explanation

    Example:
        result = workflow.run(
            config={
                "content": "Complex policy analysis text...",
                "reading_level": "general_public",
                "agent": "anthropic:claude-sonnet-4-20250514"
            }
        )
    """

    def __init__(self):
        self._pricing = PricingService()

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="plain-language",
            name="Plain Language Workflow",
            description=(
                "Simplifies complex content into clear, jargon-free explanations "
                "accessible to general audiences"
            ),
            version="1.0.0",
            capabilities=[
                "simplification",
                "plain-language",
                "accessibility",
                "summarization",
                "jargon-removal",
            ],
            tags=["simplify", "explain", "accessibility", "summary", "plain-language"],
            requires_agents=True,
            agent_count=AgentCount.CONFIGURABLE,
            min_agents=1,
            max_agents=5,
            inputs=[
                WorkflowInput(
                    name="content",
                    type="text",
                    required=True,
                    description="Complex content to simplify (analysis, legal text, technical doc, etc.)",
                ),
                WorkflowInput(
                    name="title",
                    type="string",
                    required=False,
                    description="Title of the content (optional)",
                ),
                WorkflowInput(
                    name="content_type",
                    type="string",
                    required=False,
                    default="general",
                    description="Type: policy_analysis, legal, technical, scientific, financial, medical, general",
                ),
                WorkflowInput(
                    name="reading_level",
                    type="string",
                    required=False,
                    default="general_public",
                    description="Target: elementary, middle_school, high_school, general_public",
                ),
                WorkflowInput(
                    name="agent",
                    type="agent_spec",
                    required=False,
                    default="anthropic:claude-sonnet-4-20250514",
                    description="Agent for single-agent mode (default)",
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=False,
                    description="Multiple agents for multi-agent mode (overrides 'agent')",
                ),
                WorkflowInput(
                    name="synthesis_agent",
                    type="agent_spec",
                    required=False,
                    description="Agent for synthesizing multi-agent results (defaults to first agent)",
                ),
                WorkflowInput(
                    name="llm_read_timeout_seconds",
                    type="number",
                    required=False,
                    default=90,
                    description="Fast-fail read timeout for simplification LLM calls",
                ),
                WorkflowInput(
                    name="llm_max_attempts",
                    type="number",
                    required=False,
                    default=1,
                    description="Retry attempts for simplification LLM calls (1 = fail fast)",
                ),
            ],
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate workflow configuration."""
        errors = []

        # Must provide content
        content = config.get("content", "")
        if not content or not content.strip():
            errors.append("content is required and cannot be empty")

        # Validate reading level if provided
        reading_level = config.get("reading_level", "general_public")
        valid_levels = ["elementary", "middle_school", "high_school", "general_public"]
        if reading_level.lower() not in valid_levels:
            errors.append(f"reading_level must be one of: {', '.join(valid_levels)}")

        # Validate agent count in multi-agent mode
        agents = config.get("agents", [])
        if agents and len(agents) > 5:
            errors.append("Maximum 5 agents allowed in multi-agent mode")

        llm_read_timeout_seconds = config.get("llm_read_timeout_seconds", 90)
        try:
            timeout_val = float(llm_read_timeout_seconds)
            if timeout_val <= 0:
                errors.append("llm_read_timeout_seconds must be > 0")
        except (TypeError, ValueError):
            errors.append("llm_read_timeout_seconds must be a positive number")

        llm_max_attempts = config.get("llm_max_attempts", 1)
        try:
            attempts_val = int(llm_max_attempts)
            if attempts_val < 1:
                errors.append("llm_max_attempts must be >= 1")
        except (TypeError, ValueError):
            errors.append("llm_max_attempts must be an integer >= 1")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    async def _aexecute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute workflow asynchronously."""
        started_at = datetime.now(timezone.utc)
        workflow_id = f"pl-{uuid.uuid4().hex[:12]}"
        steps: List[StepResult] = []

        try:
            # Determine mode
            agent_specs = config.get("agents", [])
            is_multi_agent = bool(agent_specs and len(agent_specs) > 1)
            mode = SimplificationMode.MULTI_AGENT if is_multi_agent else SimplificationMode.SINGLE_AGENT

            # Parse configuration
            content = config["content"]
            title = config.get("title", "Untitled Content")
            content_type = parse_content_type(config.get("content_type"))
            reading_level = parse_reading_level(config.get("reading_level"))
            llm_timeout_config = TimeoutConfig(
                read=float(config.get("llm_read_timeout_seconds", 90))
            )
            llm_retry_config = RetryConfig(
                max_attempts=int(config.get("llm_max_attempts", 1))
            )

            # Create input object
            simplification_input = SimplificationInput(
                input_id=f"input-{uuid.uuid4().hex[:8]}",
                content=content,
                content_type=content_type,
                title=title,
            )

            # Resolve agents
            if is_multi_agent:
                self._emit_progress(on_progress, 1, 3, f"Simplifying with {len(agent_specs)} agents")
                resolved_agents = agents or resolve_agents(
                    agent_specs,
                    timeout_config=llm_timeout_config,
                    retry_config=llm_retry_config,
                )
            else:
                self._emit_progress(on_progress, 1, 2, "Simplifying content")
                single_agent_spec = config.get("agent", "anthropic:claude-sonnet-4-20250514")
                resolved_agents = [
                    resolve_agent_spec(
                        single_agent_spec,
                        timeout_config=llm_timeout_config,
                        retry_config=llm_retry_config,
                    )
                ]

            # Run simplification
            if is_multi_agent:
                # Parallel multi-agent simplification
                agent_outputs = await self._run_parallel_simplification(
                    simplification_input, resolved_agents, reading_level, on_progress
                )

                # Record steps
                for output in agent_outputs:
                    steps.append(
                        StepResult(
                            step_name=f"simplify_{output.agent_name}",
                            agent_name=output.agent_name,
                            output=output.one_sentence[:200],
                            time_ms=output.time_ms,
                            input_tokens=output.input_tokens,
                            output_tokens=output.output_tokens,
                            cost=output.cost,
                        )
                    )

                # Synthesize
                self._emit_progress(on_progress, 2, 3, "Synthesizing best explanation")
                synthesis_spec = config.get("synthesis_agent") or agent_specs[0]
                synthesis_agent = resolve_agent_spec(
                    synthesis_spec,
                    timeout_config=llm_timeout_config,
                    retry_config=llm_retry_config,
                )
                final_output, synthesis_step = await self._synthesize_simplifications(
                    simplification_input, agent_outputs, synthesis_agent, reading_level
                )
                if synthesis_step:
                    steps.append(synthesis_step)

                self._emit_progress(on_progress, 3, 3, "Complete")

            else:
                # Single agent simplification
                agent_outputs = await self._run_parallel_simplification(
                    simplification_input, resolved_agents, reading_level, on_progress
                )

                if not agent_outputs:
                    return WorkflowResult.from_error(
                        self.metadata.workflow_id,
                        "Agent simplification failed",
                    )

                output = agent_outputs[0]
                steps.append(
                    StepResult(
                        step_name="simplify",
                        agent_name=output.agent_name,
                        output=output.one_sentence[:200],
                        time_ms=output.time_ms,
                        input_tokens=output.input_tokens,
                        output_tokens=output.output_tokens,
                        cost=output.cost,
                    )
                )

                # Convert to final output
                final_output = self._agent_output_to_final(
                    simplification_input, output, reading_level, mode
                )

                self._emit_progress(on_progress, 2, 2, "Complete")

            # Calculate totals
            total_cost = sum(s.cost for s in steps)
            total_input_tokens = sum(s.input_tokens for s in steps)
            total_output_tokens = sum(s.output_tokens for s in steps)
            total_time_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)

            # Update output with totals
            final_output.total_cost = total_cost

            return WorkflowResult(
                workflow_id=self.metadata.workflow_id,
                success=True,
                output={
                    "one_sentence": final_output.one_sentence_summary,
                    "one_paragraph": final_output.one_paragraph_summary,
                    "plain_explanation": final_output.plain_explanation,
                    "key_points": final_output.key_points,
                    "bottom_line": final_output.bottom_line,
                    "who_is_affected": final_output.who_is_affected,
                    "action_items": final_output.action_items,
                    "glossary": final_output.glossary,
                    "mode": final_output.mode,
                    "agent_count": final_output.agent_count,
                    "reading_level": final_output.reading_level,
                },
                metrics=WorkflowMetrics(
                    total_time_ms=total_time_ms,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    total_cost=total_cost,
                    step_count=len(steps),
                ),
                steps=steps,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                metadata={
                    "workflow_id": workflow_id,
                    "mode": mode.value,
                    "agent_count": len(agent_outputs) if agent_outputs else 0,
                    "reading_level": reading_level.value,
                    "content_type": content_type.value,
                },
            )

        except Exception as e:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Workflow execution failed: {str(e)}",
            )

    # ========================================================================
    # Simplification Methods
    # ========================================================================

    async def _run_parallel_simplification(
        self,
        input_content: SimplificationInput,
        agents: List[BaseAgent],
        reading_level: ReadingLevel,
        on_progress: Optional[ProgressCallback],
    ) -> List[AgentSimplification]:
        """Run simplification in parallel across agents."""
        prompt = SIMPLIFY_PROMPT_TEMPLATE.format(
            title=input_content.title or "Untitled",
            content_type=input_content.content_type.value.replace("_", " "),
            content=input_content.content[:30000],  # Truncate if very long
            reading_level_description=get_reading_level_description(reading_level),
        )

        # Create async tasks
        tasks = [self._simplify_with_agent(agent, prompt) for agent in agents]

        # Run in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful results
        successful = []
        for result in results:
            if isinstance(result, AgentSimplification):
                successful.append(result)

        return successful

    async def _simplify_with_agent(
        self,
        agent: BaseAgent,
        prompt: str,
    ) -> AgentSimplification:
        """Single agent simplification."""
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        start_time = datetime.now(timezone.utc)

        try:
            response = await agent.agenerate(prompt)

            # Handle different response formats
            if isinstance(response, tuple):
                response_text = response.text if hasattr(response, 'text') else response[0]
                token_usage = response.token_usage if hasattr(response, 'token_usage') else (response[2] if len(response) > 2 else None)
            else:
                response_text = str(response)
                token_usage = None

            time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Parse JSON response
            parsed = self._parse_simplification_response(response_text)

            # Extract token counts
            input_tokens = token_usage.input if token_usage and hasattr(token_usage, "input") else 0
            output_tokens = token_usage.output if token_usage and hasattr(token_usage, "output") else 0

            # Calculate cost
            model_name = getattr(agent, "model", agent.name)
            cost = self._pricing.calculate_total_cost(model_name, input_tokens, output_tokens)

            # Build key points
            key_points = []
            for kp in parsed.get("key_points", []):
                key_points.append(
                    KeyPoint(
                        point_number=kp.get("point_number", 0),
                        original_concept=kp.get("original_concept", ""),
                        simplified=kp.get("simplified", ""),
                        importance=kp.get("importance", "context"),
                    )
                )

            # Build glossary
            glossary = []
            for term in parsed.get("glossary", []):
                glossary.append(
                    JargonTerm(
                        term=term.get("term", ""),
                        definition=term.get("definition", ""),
                        context=term.get("context", ""),
                    )
                )

            return AgentSimplification(
                agent_id=agent_id,
                agent_name=agent.name,
                model=model_name,
                one_sentence=parsed.get("one_sentence_summary", ""),
                one_paragraph=parsed.get("one_paragraph_summary", ""),
                key_points=key_points,
                plain_explanation=parsed.get("plain_explanation", ""),
                jargon_glossary=glossary,
                bottom_line=parsed.get("bottom_line", ""),
                who_affected=parsed.get("who_is_affected", ""),
                action_items=parsed.get("action_items", []),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                time_ms=time_ms,
            )

        except Exception as e:
            time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            return AgentSimplification(
                agent_id=agent_id,
                agent_name=agent.name,
                model=getattr(agent, "model", agent.name),
                one_sentence=f"Simplification failed: {str(e)}",
                one_paragraph="",
                time_ms=time_ms,
            )

    def _parse_simplification_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response."""
        # Try to find JSON in response
        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                return {}

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to fix common issues
            json_str = re.sub(r",\s*}", "}", json_str)
            json_str = re.sub(r",\s*]", "]", json_str)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {}

    # ========================================================================
    # Synthesis Methods
    # ========================================================================

    async def _synthesize_simplifications(
        self,
        input_content: SimplificationInput,
        agent_outputs: List[AgentSimplification],
        synthesis_agent: BaseAgent,
        reading_level: ReadingLevel,
    ) -> tuple[PlainLanguageOutput, Optional[StepResult]]:
        """Synthesize multiple agent simplifications."""
        # Format agent outputs for synthesis prompt
        agent_explanations = self._format_outputs_for_synthesis(agent_outputs)

        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            title=input_content.title or "Untitled",
            content_type=input_content.content_type.value.replace("_", " "),
            agent_explanations=agent_explanations,
        )

        start_time = datetime.now(timezone.utc)

        try:
            response = await synthesis_agent.agenerate(prompt)

            if isinstance(response, tuple):
                response_text = response[0]
                token_usage = response[2] if len(response) > 2 else None
            else:
                response_text = str(response)
                token_usage = None

            time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            parsed = self._parse_simplification_response(response_text)

            input_tokens = token_usage.input if token_usage and hasattr(token_usage, "input") else 0
            output_tokens = token_usage.output if token_usage and hasattr(token_usage, "output") else 0
            model_name = getattr(synthesis_agent, "model", synthesis_agent.name)
            cost = self._pricing.calculate_total_cost(model_name, input_tokens, output_tokens)

            # Build final output
            output = PlainLanguageOutput(
                output_id=f"output-{uuid.uuid4().hex[:8]}",
                title=input_content.title,
                content_type=input_content.content_type.value,
                reading_level=reading_level.value,
                one_sentence_summary=parsed.get("one_sentence_summary", agent_outputs[0].one_sentence),
                one_paragraph_summary=parsed.get("one_paragraph_summary", agent_outputs[0].one_paragraph),
                plain_explanation=parsed.get("plain_explanation", agent_outputs[0].plain_explanation),
                key_points=[kp.to_dict() for kp in self._merge_key_points(agent_outputs, parsed)],
                bottom_line=parsed.get("bottom_line", agent_outputs[0].bottom_line),
                who_is_affected=parsed.get("who_is_affected", agent_outputs[0].who_affected),
                action_items=parsed.get("action_items", agent_outputs[0].action_items),
                glossary=self._merge_glossaries(agent_outputs, parsed),
                agent_count=len(agent_outputs),
                mode=SimplificationMode.MULTI_AGENT.value,
                original_length=input_content.content_length,
                simplified_length=len(parsed.get("plain_explanation", "")),
            )

            if output.original_length > 0:
                output.compression_ratio = output.simplified_length / output.original_length

            step = StepResult(
                step_name="synthesis",
                agent_name=synthesis_agent.name,
                output=output.one_sentence_summary[:200],
                time_ms=time_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )

            return output, step

        except Exception:
            # Fallback to first agent's output
            return self._agent_output_to_final(
                input_content,
                agent_outputs[0],
                reading_level,
                SimplificationMode.MULTI_AGENT,
            ), None

    def _format_outputs_for_synthesis(self, outputs: List[AgentSimplification]) -> str:
        """Format agent outputs for synthesis prompt."""
        parts = []
        for i, output in enumerate(outputs, 1):
            parts.append(f"""
### Agent {i}: {output.agent_name}

**One Sentence:** {output.one_sentence}

**One Paragraph:** {output.one_paragraph}

**Bottom Line:** {output.bottom_line}

**Key Points:** {len(output.key_points)} points identified

**Glossary Terms:** {len(output.jargon_glossary)} terms defined
""")
        return "\n---\n".join(parts)

    def _merge_key_points(
        self,
        outputs: List[AgentSimplification],
        synthesis_parsed: Dict[str, Any],
    ) -> List[KeyPoint]:
        """Merge key points from multiple agents."""
        # Prefer synthesized key points if available
        if synthesis_parsed.get("key_points"):
            return [
                KeyPoint(
                    point_number=kp.get("point_number", i + 1),
                    original_concept=kp.get("original_concept", ""),
                    simplified=kp.get("simplified", ""),
                    importance=kp.get("importance", "context"),
                )
                for i, kp in enumerate(synthesis_parsed["key_points"])
            ]

        # Otherwise combine from agents
        all_points = []
        seen_simplified = set()
        for output in outputs:
            for kp in output.key_points:
                if kp.simplified not in seen_simplified:
                    seen_simplified.add(kp.simplified)
                    all_points.append(kp)

        # Renumber
        for i, kp in enumerate(all_points, 1):
            kp.point_number = i

        return all_points[:10]  # Limit to top 10

    def _merge_glossaries(
        self,
        outputs: List[AgentSimplification],
        synthesis_parsed: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """Merge glossaries from multiple agents."""
        # Prefer synthesized glossary if available
        if synthesis_parsed.get("glossary"):
            return synthesis_parsed["glossary"]

        # Otherwise combine from agents
        merged = {}
        for output in outputs:
            for term in output.jargon_glossary:
                if term.term not in merged:
                    merged[term.term] = {
                        "term": term.term,
                        "definition": term.definition,
                        "context": term.context,
                    }

        return list(merged.values())

    def _agent_output_to_final(
        self,
        input_content: SimplificationInput,
        output: AgentSimplification,
        reading_level: ReadingLevel,
        mode: SimplificationMode,
    ) -> PlainLanguageOutput:
        """Convert single agent output to final output format."""
        simplified_length = len(output.plain_explanation)
        compression_ratio = (
            simplified_length / input_content.content_length
            if input_content.content_length > 0
            else 0.0
        )

        return PlainLanguageOutput(
            output_id=f"output-{uuid.uuid4().hex[:8]}",
            title=input_content.title,
            content_type=input_content.content_type.value,
            reading_level=reading_level.value,
            one_sentence_summary=output.one_sentence,
            one_paragraph_summary=output.one_paragraph,
            plain_explanation=output.plain_explanation,
            key_points=[kp.to_dict() for kp in output.key_points],
            bottom_line=output.bottom_line,
            who_is_affected=output.who_affected,
            action_items=output.action_items,
            glossary=[
                {"term": t.term, "definition": t.definition, "context": t.context}
                for t in output.jargon_glossary
            ],
            agent_count=1,
            mode=mode.value,
            original_length=input_content.content_length,
            simplified_length=simplified_length,
            compression_ratio=compression_ratio,
        )
