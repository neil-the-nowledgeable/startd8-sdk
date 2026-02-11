"""
Policy Analysis Workflow.

Multi-agent parallel critical analysis of laws, bills, and policies
through a lens that centers the wellbeing and empowerment of ordinary people.
"""

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.agents import BaseAgent
from startd8.costs.pricing import PricingService
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

from .policy_analysis_models import (
    AgentAnalysis,
    AnalysisCriterion,
    ConsensusLevel,
    CriterionScore,
    CriterionScoreOutput,
    InputSource,
    OverallAssessment,
    PolicyAnalysisOutput,
    PolicyAnalysisResult,
    PolicyInput,
    PolicyInputType,
    RedFlag,
    RedFlagOutput,
    Severity,
    SynthesizedScore,
    parse_policy_type,
    score_to_assessment,
)


# ============================================================================
# Prompt Templates
# ============================================================================


ANALYSIS_PROMPT_TEMPLATE = """You are a critical policy analyst examining legislation and policies through a lens that centers the wellbeing and empowerment of ordinary people.

## Policy Document

Title: {policy_title}
Type: {policy_type}
Jurisdiction: {jurisdiction}

---
{policy_content}
---

## Analysis Framework

Analyze this policy using the following seven criteria. For each criterion, provide:
1. A score from 0-100 (where 100 = fully beneficial/no concerns, 0 = completely harmful)
2. Confidence level (0.0-1.0)
3. Rationale for your score
4. Direct evidence/quotes from the text
5. Any red flags identified

### Criteria

1. **Benefit to People at Large** (benefit_to_people)
   - Does this policy primarily serve ordinary people or concentrated interests?
   - Who gains the most material benefit?
   - Are there hidden costs imposed on the public?
   - Does it address real needs of everyday people?

2. **Empowerment of People** (people_empowerment)
   - Does this increase or decrease people's agency and autonomy?
   - Does it strengthen or weaken democratic participation?
   - Does it protect or erode individual/collective rights?
   - Does it give people more control over their lives?

3. **Power Imbalance Recognition** (power_imbalance)
   - Does this policy acknowledge existing power asymmetries?
   - Does it address or exacerbate regulatory capture?
   - Does it check or enable the wealthy subverting the will of the people?
   - Does it account for the reality that money buys political influence?

4. **Corporate Privilege Scrutiny** (corporate_privilege)
   - Does this grant special privileges to corporations not available to individuals?
   - Are liability protections balanced or one-sided?
   - Does it create barriers that favor established players?
   - Does it treat corporations as having rights beyond what individuals have?
   - It is always bad to give corporations powers not accessible practically to everyone else unless it benefits people at large first and foremost.

5. **Doctrine of Discovery Legacy** (doctrine_of_discovery)
   - Does this policy rely on or perpetuate legal frameworks built on colonial doctrines?
   - How does it treat indigenous rights and sovereignty?
   - Does it challenge or reinforce property claims rooted in dispossession?
   - Any legal precedent built upon the Doctrine of Discovery or precedents built on such precedents should be questioned.

6. **Supremacy Ideology Rejection** (supremacy_ideology)
   - Does this policy contain language or effects that privilege certain racial/religious groups?
   - Does it encode or challenge structural discrimination?
   - Who is centered and who is marginalized?
   - Any influence resting upon ideas of racial or religious supremacy are inherently worthless.

7. **Slavery Legacy Critique** (slavery_legacy)
   - Does this policy address or perpetuate structures rooted in slavery?
   - How does it handle issues like prison labor, wealth inequality from historical theft?
   - Does it work toward repair or maintain the status quo?
   - Any legacy of slavery encoded in founding documents may be legally binding but is devoid of moral meaning today.

## Required Output Format

Respond ONLY with valid JSON in exactly this structure:

```json
{{
  "overall_score": <0-100>,
  "overall_assessment": "<harmful|concerning|neutral|beneficial|highly_beneficial>",
  "executive_summary": "<2-3 paragraph summary of key findings>",
  "criterion_scores": [
    {{
      "criterion": "benefit_to_people",
      "score": <0-100>,
      "confidence": <0.0-1.0>,
      "rationale": "<explanation for this score>",
      "evidence": ["<relevant quote 1>", "<relevant quote 2>"],
      "red_flags": ["<specific concern>"]
    }},
    {{
      "criterion": "people_empowerment",
      "score": <0-100>,
      "confidence": <0.0-1.0>,
      "rationale": "<explanation>",
      "evidence": [],
      "red_flags": []
    }},
    {{
      "criterion": "power_imbalance",
      "score": <0-100>,
      "confidence": <0.0-1.0>,
      "rationale": "<explanation>",
      "evidence": [],
      "red_flags": []
    }},
    {{
      "criterion": "corporate_privilege",
      "score": <0-100>,
      "confidence": <0.0-1.0>,
      "rationale": "<explanation>",
      "evidence": [],
      "red_flags": []
    }},
    {{
      "criterion": "doctrine_of_discovery",
      "score": <0-100>,
      "confidence": <0.0-1.0>,
      "rationale": "<explanation>",
      "evidence": [],
      "red_flags": []
    }},
    {{
      "criterion": "supremacy_ideology",
      "score": <0-100>,
      "confidence": <0.0-1.0>,
      "rationale": "<explanation>",
      "evidence": [],
      "red_flags": []
    }},
    {{
      "criterion": "slavery_legacy",
      "score": <0-100>,
      "confidence": <0.0-1.0>,
      "rationale": "<explanation>",
      "evidence": [],
      "red_flags": []
    }}
  ],
  "red_flags": [
    {{
      "severity": "<critical|major|minor>",
      "category": "<criterion_name>",
      "title": "<brief title>",
      "description": "<detailed explanation of the concern>",
      "evidence_quotes": ["<direct quotes from policy>"]
    }}
  ],
  "recommendations": [
    "<specific, actionable recommendation for improving or opposing this policy>"
  ],
  "detailed_analysis": "<comprehensive narrative analysis covering all criteria>"
}}
```

Be thorough, cite specific sections, and maintain critical skepticism of claims that serve concentrated power over ordinary people.
"""


SYNTHESIS_PROMPT_TEMPLATE = """You are synthesizing multiple independent policy analyses into a unified assessment.

## Policy Being Analyzed

Title: {policy_title}
Type: {policy_type}
Jurisdiction: {jurisdiction}

## Individual Agent Analyses

{agent_analyses}

## Synthesis Instructions

Create a synthesized assessment that:
1. Combines scores using weighted averages based on confidence levels
2. Identifies areas of consensus and disagreement among agents
3. Elevates red flags that multiple agents identified
4. Provides a unified, prioritized recommendation set
5. Notes where agents diverged significantly and why

Focus on creating a balanced synthesis that acknowledges uncertainty while providing actionable guidance for people seeking to understand this policy's real-world impact.

## Required Output Format

Respond ONLY with valid JSON:

```json
{{
  "overall_score": <0-100>,
  "overall_assessment": "<harmful|concerning|neutral|beneficial|highly_beneficial>",
  "confidence": <0.0-1.0>,
  "consensus_level": "<high|moderate|low|divergent>",
  "synthesized_criterion_scores": {{
    "benefit_to_people": {{
      "mean_score": <float>,
      "min_score": <int>,
      "max_score": <int>,
      "consensus_rationale": "<synthesis of agent findings>"
    }},
    "people_empowerment": {{ ... }},
    "power_imbalance": {{ ... }},
    "corporate_privilege": {{ ... }},
    "doctrine_of_discovery": {{ ... }},
    "supremacy_ideology": {{ ... }},
    "slavery_legacy": {{ ... }}
  }},
  "consolidated_red_flags": [
    {{
      "severity": "<critical|major|minor>",
      "category": "<criterion>",
      "title": "<title>",
      "description": "<description>",
      "agents_identifying": <count>,
      "evidence_quotes": ["<quotes>"]
    }}
  ],
  "divergence_notes": [
    "<specific areas where agents disagreed significantly>"
  ],
  "synthesized_recommendations": [
    "<prioritized, actionable recommendations>"
  ],
  "executive_summary": "<comprehensive 3-4 paragraph summary of synthesized findings>"
}}
```
"""


NARRATIVE_REPORT_TEMPLATE = """## Policy Analysis Report

### {policy_title}

**Analysis Date:** {analysis_date}
**Document Type:** {policy_type}
**Jurisdiction:** {jurisdiction}

---

## Executive Summary

{executive_summary}

---

## Overall Assessment

| Metric | Value |
|--------|-------|
| **Score** | {overall_score}/100 |
| **Assessment** | {overall_assessment} |
| **Confidence** | {confidence:.0%} |
| **Agent Consensus** | {consensus_level} |

---

## Criterion-by-Criterion Analysis

{criterion_sections}

---

## Red Flags Identified

{red_flags_section}

---

## Recommendations

{recommendations_section}

---

## Methodology

This analysis was conducted by {agent_count} independent AI agents examining the policy through a critical framework that centers:

- **Benefit to ordinary people** over concentrated corporate/wealthy interests
- **Empowerment and autonomy** of individuals and communities
- **Recognition of power imbalances** including regulatory capture
- **Scrutiny of corporate privileges** not accessible to everyone
- **Awareness of colonial legal legacies** including the Doctrine of Discovery
- **Rejection of supremacist ideologies** whether racial or religious
- **Critique of slavery's structural legacy** in law and policy

---

**Analysis Cost:** ${total_cost:.4f}
**Analysis Duration:** {total_time_ms}ms
**Agents Used:** {agent_names}
"""


# ============================================================================
# Workflow Implementation
# ============================================================================


class PolicyAnalysisWorkflow(WorkflowBase):
    """
    Multi-agent policy analysis workflow.

    Analyzes laws, bills, and policies through a critical lens that centers
    the wellbeing and empowerment of ordinary people while identifying
    structures of power imbalance and historical injustice.

    Execution Flow:
    1. Input Processing: Parse/fetch content from text/URL/file
    2. Parallel Analysis: Each agent independently analyzes using the framework
    3. Synthesis: Combine analyses into unified assessment with structured + narrative output

    Example:
        result = workflow.run(
            config={
                "url": "https://congress.gov/bill/118th-congress/house-bill/1234",
                "agents": [
                    "anthropic:claude-sonnet-4-20250514",
                    "openai:gpt-4o",
                    "gemini:gemini-2.5-pro"
                ],
                "output_format": "both"
            }
        )
    """

    def __init__(self):
        self._pricing = PricingService()

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="policy-analysis",
            name="Policy Analysis Workflow",
            description=(
                "Multi-agent critical analysis of laws, bills, and policies "
                "centering the benefit to people at large"
            ),
            version="1.0.0",
            capabilities=[
                "policy-analysis",
                "multi-agent",
                "parallel-execution",
                "document-processing",
                "url-fetching",
                "critical-framework",
                "structured-output",
            ],
            tags=["policy", "analysis", "government", "legislation", "critical", "social-justice"],
            requires_agents=True,
            agent_count=AgentCount.CONFIGURABLE,
            min_agents=2,
            max_agents=5,
            inputs=[
                WorkflowInput(
                    name="content",
                    type="text",
                    required=False,
                    description="Raw policy text content",
                ),
                WorkflowInput(
                    name="url",
                    type="string",
                    required=False,
                    description="URL to fetch policy from (congress.gov, etc.)",
                ),
                WorkflowInput(
                    name="file_path",
                    type="file",
                    required=False,
                    description="Path to local policy file",
                ),
                WorkflowInput(
                    name="policy_title",
                    type="string",
                    required=False,
                    description="Title of the policy (optional, will extract if possible)",
                ),
                WorkflowInput(
                    name="policy_type",
                    type="string",
                    required=False,
                    description="Type: bill, law, regulation, executive_order, etc.",
                ),
                WorkflowInput(
                    name="jurisdiction",
                    type="string",
                    required=False,
                    description="Jurisdiction (e.g., 'US Federal', 'California', 'EU')",
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=True,
                    description="2-5 agent specs for parallel analysis",
                ),
                WorkflowInput(
                    name="synthesis_agent",
                    type="agent_spec",
                    required=False,
                    default="anthropic:claude-sonnet-4-20250514",
                    description="Agent for synthesis phase (defaults to Claude Sonnet)",
                ),
                WorkflowInput(
                    name="output_format",
                    type="string",
                    required=False,
                    default="both",
                    description="Output format: both, structured, narrative",
                ),
            ],
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate workflow configuration."""
        errors = []

        # Must provide at least one input source
        has_content = bool(config.get("content", "").strip() if config.get("content") else False)
        has_url = bool(config.get("url", "").strip() if config.get("url") else False)
        has_file = bool(config.get("file_path", "").strip() if config.get("file_path") else False)

        if not (has_content or has_url or has_file):
            errors.append("Must provide at least one of: content, url, or file_path")

        # Validate agent count
        agents = config.get("agents", [])
        if len(agents) < 2:
            errors.append("At least 2 agents required for multi-perspective analysis")
        if len(agents) > 5:
            errors.append("Maximum 5 agents allowed to manage costs")

        # Validate output format
        output_format = config.get("output_format", "both")
        if output_format not in ("both", "structured", "narrative"):
            errors.append("output_format must be: both, structured, or narrative")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    async def _aexecute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute workflow asynchronously for parallel agent calls."""
        started_at = datetime.now(timezone.utc)
        workflow_id = f"pa-{uuid.uuid4().hex[:12]}"
        steps: List[StepResult] = []

        try:
            # Phase 1: Input Processing
            self._emit_progress(on_progress, 1, 4, "Processing input")
            policy_input = await self._process_input(config)

            if policy_input.extraction_error:
                return WorkflowResult.from_error(
                    self.metadata.workflow_id,
                    f"Input processing failed: {policy_input.extraction_error}",
                )

            # Resolve agents
            resolved_agents = agents or resolve_agents(config.get("agents", []))

            # Phase 2: Parallel Analysis
            self._emit_progress(on_progress, 2, 4, f"Analyzing with {len(resolved_agents)} agents")
            agent_analyses = await self._run_parallel_analysis(
                policy_input, resolved_agents, on_progress
            )

            # Record analysis steps
            for analysis in agent_analyses:
                steps.append(
                    StepResult(
                        step_name=f"analysis_{analysis.agent_name}",
                        agent_name=analysis.agent_name,
                        output=analysis.executive_summary[:500],
                        time_ms=analysis.time_ms,
                        input_tokens=analysis.input_tokens,
                        output_tokens=analysis.output_tokens,
                        cost=analysis.cost,
                        metadata={"overall_score": analysis.overall_score},
                    )
                )

            if not agent_analyses:
                return WorkflowResult.from_error(
                    self.metadata.workflow_id,
                    "All agent analyses failed",
                )

            # Phase 3: Synthesis
            self._emit_progress(on_progress, 3, 4, "Synthesizing results")
            output_format = config.get("output_format", "both")

            synthesis_agent_spec = config.get(
                "synthesis_agent", "anthropic:claude-sonnet-4-20250514"
            )
            synthesis_agent = resolve_agent_spec(synthesis_agent_spec)

            structured_output, narrative_report, synthesis_step = await self._synthesize_analyses(
                policy_input,
                agent_analyses,
                synthesis_agent,
                output_format,
            )

            if synthesis_step:
                steps.append(synthesis_step)

            # Phase 4: Build result
            self._emit_progress(on_progress, 4, 4, "Finalizing")

            # Aggregate metrics
            total_cost = sum(a.cost for a in agent_analyses)
            total_input_tokens = sum(a.input_tokens for a in agent_analyses)
            total_output_tokens = sum(a.output_tokens for a in agent_analyses)
            total_time_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)

            if synthesis_step:
                total_cost += synthesis_step.cost
                total_input_tokens += synthesis_step.input_tokens
                total_output_tokens += synthesis_step.output_tokens

            # Update structured output with totals
            if structured_output:
                structured_output.total_cost = total_cost
                structured_output.total_time_ms = total_time_ms

            # Build output dict
            output_dict = {
                "policy_title": policy_input.title or "Untitled Policy",
                "policy_type": policy_input.policy_type.value,
                "jurisdiction": policy_input.jurisdiction,
                "agent_count": len(agent_analyses),
            }

            if output_format in ("both", "structured") and structured_output:
                output_dict["structured_output"] = structured_output.model_dump()

            if output_format in ("both", "narrative"):
                output_dict["narrative_report"] = narrative_report

            return WorkflowResult(
                workflow_id=self.metadata.workflow_id,
                success=True,
                output=output_dict,
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
                    "agent_count": len(agent_analyses),
                    "overall_score": structured_output.overall_score if structured_output else None,
                    "consensus_level": structured_output.consensus_level if structured_output else None,
                },
            )

        except Exception as e:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Workflow execution failed: {str(e)}",
            )

    # ========================================================================
    # Input Processing
    # ========================================================================

    async def _process_input(self, config: Dict[str, Any]) -> PolicyInput:
        """Process and extract content from input source."""
        input_id = f"input-{uuid.uuid4().hex[:8]}"

        policy_type = parse_policy_type(config.get("policy_type"))
        jurisdiction = config.get("jurisdiction")
        title = config.get("policy_title")

        # Priority: content > file_path > url
        if config.get("content"):
            content = config["content"]
            return PolicyInput(
                input_id=input_id,
                source_type=InputSource.RAW_TEXT,
                original_source="raw_text",
                content=content,
                title=title or self._extract_title_from_content(content),
                policy_type=policy_type,
                jurisdiction=jurisdiction,
            )

        if config.get("file_path"):
            return await self._process_file(
                config["file_path"], input_id, title, policy_type, jurisdiction
            )

        if config.get("url"):
            return await self._fetch_url(
                config["url"], input_id, title, policy_type, jurisdiction
            )

        return PolicyInput(
            input_id=input_id,
            source_type=InputSource.RAW_TEXT,
            original_source="",
            content="",
            extraction_error="No input source provided",
        )

    async def _process_file(
        self,
        file_path: str,
        input_id: str,
        title: Optional[str],
        policy_type: PolicyInputType,
        jurisdiction: Optional[str],
    ) -> PolicyInput:
        """Read and extract content from a local file."""
        try:
            path = Path(file_path)
            if not path.exists():
                return PolicyInput(
                    input_id=input_id,
                    source_type=InputSource.FILE,
                    original_source=file_path,
                    content="",
                    extraction_error=f"File not found: {file_path}",
                )

            suffix = path.suffix.lower()

            if suffix == ".pdf":
                content = self._extract_text_from_pdf_file(path)
            elif suffix in (".html", ".htm"):
                html_content = path.read_text(encoding="utf-8")
                content = self._extract_text_from_html(html_content)
            else:
                # Assume text file
                content = path.read_text(encoding="utf-8")

            return PolicyInput(
                input_id=input_id,
                source_type=InputSource.FILE,
                original_source=file_path,
                content=content,
                title=title or path.stem,
                policy_type=policy_type,
                jurisdiction=jurisdiction,
                metadata={"file_type": suffix},
            )

        except Exception as e:
            return PolicyInput(
                input_id=input_id,
                source_type=InputSource.FILE,
                original_source=file_path,
                content="",
                extraction_error=f"Failed to read file: {str(e)}",
            )

    async def _fetch_url(
        self,
        url: str,
        input_id: str,
        title: Optional[str],
        policy_type: PolicyInputType,
        jurisdiction: Optional[str],
    ) -> PolicyInput:
        """Fetch and extract content from URL."""
        try:
            import httpx

            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")

                if "application/pdf" in content_type:
                    content = self._extract_text_from_pdf_bytes(response.content)
                elif "text/html" in content_type:
                    content = self._extract_text_from_html(response.text)
                else:
                    content = response.text

                extracted_title = title or self._extract_title_from_url(url)

                return PolicyInput(
                    input_id=input_id,
                    source_type=InputSource.URL,
                    original_source=url,
                    content=content,
                    title=extracted_title,
                    policy_type=policy_type,
                    jurisdiction=jurisdiction,
                    metadata={"url": url, "content_type": content_type},
                )

        except Exception as e:
            return PolicyInput(
                input_id=input_id,
                source_type=InputSource.URL,
                original_source=url,
                content="",
                extraction_error=f"Failed to fetch URL: {str(e)}",
            )

    def _extract_text_from_html(self, html: str) -> str:
        """Extract readable text from HTML."""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML comments
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)

        # Decode HTML entities
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)

        # Clean whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _extract_text_from_pdf_bytes(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes."""
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(pdf_bytes))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts)
        except ImportError:
            raise ValueError("PDF extraction requires pypdf package: pip install pypdf")

    def _extract_text_from_pdf_file(self, path: Path) -> str:
        """Extract text from PDF file."""
        try:
            from pypdf import PdfReader

            reader = PdfReader(path)
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts)
        except ImportError:
            raise ValueError("PDF extraction requires pypdf package: pip install pypdf")

    def _extract_title_from_url(self, url: str) -> str:
        """Extract a reasonable title from URL."""
        # Handle congress.gov URLs
        if "congress.gov" in url:
            match = re.search(r"/bill/(\d+).*?-congress/([^/]+)/(\d+)", url)
            if match:
                congress, chamber, number = match.groups()
                return f"{congress}th Congress {chamber.upper()} {number}"

        # Generic: use last path segment
        path = url.rstrip("/").split("/")[-1]
        return path.replace("-", " ").replace("_", " ").title()

    def _extract_title_from_content(self, content: str) -> str:
        """Try to extract title from content."""
        # Look for common title patterns
        lines = content.strip().split("\n")[:10]
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 200:
                # Skip lines that look like metadata
                if not any(x in line.lower() for x in ["http", "www.", "@", "date:", "version:"]):
                    return line
        return "Untitled Policy"

    # ========================================================================
    # Parallel Analysis
    # ========================================================================

    async def _run_parallel_analysis(
        self,
        policy_input: PolicyInput,
        agents: List[BaseAgent],
        on_progress: Optional[ProgressCallback],
    ) -> List[AgentAnalysis]:
        """Run analysis in parallel across all agents."""
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            policy_title=policy_input.title or "Untitled Policy",
            policy_type=policy_input.policy_type.value,
            jurisdiction=policy_input.jurisdiction or "Unknown",
            policy_content=policy_input.content[:50000],  # Truncate if very long
        )

        # Create async tasks for all agents
        tasks = [self._analyze_with_agent(agent, prompt, policy_input) for agent in agents]

        # Run in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful analyses
        successful = []
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                raise result
            if isinstance(result, AgentAnalysis):
                successful.append(result)
            elif isinstance(result, Exception):
                # Log but continue with other agents
                pass

        return successful

    async def _analyze_with_agent(
        self,
        agent: BaseAgent,
        prompt: str,
        policy_input: PolicyInput,
    ) -> AgentAnalysis:
        """Single agent analysis."""
        analysis_id = f"analysis-{uuid.uuid4().hex[:8]}"
        start_time = datetime.now(timezone.utc)

        try:
            # Call agent
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
            parsed = self._parse_analysis_response(response_text)

            # Extract token counts
            input_tokens = token_usage.input if token_usage and hasattr(token_usage, "input") else 0
            output_tokens = token_usage.output if token_usage and hasattr(token_usage, "output") else 0

            # Calculate cost
            model_name = getattr(agent, "model", agent.name)
            cost = self._pricing.calculate_total_cost(model_name, input_tokens, output_tokens)

            # Build criterion scores
            criterion_scores = self._parse_criterion_scores(parsed)

            # Build red flags
            red_flags = self._parse_red_flags(parsed)

            # Determine overall assessment
            overall_score = parsed.get("overall_score", 50)
            overall_assessment = score_to_assessment(overall_score)

            return AgentAnalysis(
                analysis_id=analysis_id,
                agent_name=agent.name,
                model=model_name,
                overall_score=overall_score,
                overall_assessment=overall_assessment,
                criterion_scores=criterion_scores,
                red_flags=red_flags,
                executive_summary=parsed.get("executive_summary", ""),
                detailed_analysis=parsed.get("detailed_analysis", ""),
                recommendations=parsed.get("recommendations", []),
                raw_response=response_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                time_ms=time_ms,
            )

        except Exception as e:
            # Return a failed analysis
            time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            return AgentAnalysis(
                analysis_id=analysis_id,
                agent_name=agent.name,
                model=getattr(agent, "model", agent.name),
                overall_score=0,
                overall_assessment=OverallAssessment.HARMFUL,
                executive_summary=f"Analysis failed: {str(e)}",
                time_ms=time_ms,
            )

    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response with fallbacks."""
        # Try to find JSON in response
        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
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

    def _parse_criterion_scores(self, parsed: Dict[str, Any]) -> List[CriterionScore]:
        """Parse criterion scores from parsed response."""
        scores = []
        raw_scores = parsed.get("criterion_scores", [])

        for raw in raw_scores:
            try:
                criterion_str = raw.get("criterion", "")
                criterion = AnalysisCriterion(criterion_str)
                scores.append(
                    CriterionScore(
                        criterion=criterion,
                        score=raw.get("score", 50),
                        confidence=raw.get("confidence", 0.5),
                        rationale=raw.get("rationale", ""),
                        evidence=raw.get("evidence", []),
                        red_flags=raw.get("red_flags", []),
                    )
                )
            except (ValueError, KeyError):
                continue

        return scores

    def _parse_red_flags(self, parsed: Dict[str, Any]) -> List[RedFlag]:
        """Parse red flags from parsed response."""
        flags = []
        raw_flags = parsed.get("red_flags", [])

        for i, raw in enumerate(raw_flags):
            try:
                severity_str = raw.get("severity", "minor").lower()
                severity = Severity(severity_str)

                category_str = raw.get("category", "benefit_to_people")
                try:
                    category = AnalysisCriterion(category_str)
                except ValueError:
                    category = AnalysisCriterion.BENEFIT_TO_PEOPLE

                flags.append(
                    RedFlag(
                        flag_id=f"flag-{i}",
                        severity=severity,
                        category=category,
                        title=raw.get("title", "Untitled Flag"),
                        description=raw.get("description", ""),
                        evidence_quotes=raw.get("evidence_quotes", []),
                    )
                )
            except (ValueError, KeyError):
                continue

        return flags

    # ========================================================================
    # Synthesis
    # ========================================================================

    async def _synthesize_analyses(
        self,
        policy_input: PolicyInput,
        agent_analyses: List[AgentAnalysis],
        synthesis_agent: BaseAgent,
        output_format: str,
    ) -> tuple[Optional[PolicyAnalysisOutput], str, Optional[StepResult]]:
        """Synthesize multiple analyses into unified output."""

        # Build structured output from analyses
        structured_output = self._build_structured_output(policy_input, agent_analyses)

        # Generate narrative report
        narrative_report = ""
        synthesis_step = None

        if output_format in ("both", "narrative"):
            # Use synthesis agent to create narrative
            synthesis_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
                policy_title=policy_input.title or "Untitled Policy",
                policy_type=policy_input.policy_type.value,
                jurisdiction=policy_input.jurisdiction or "Unknown",
                agent_analyses=self._format_analyses_for_synthesis(agent_analyses),
            )

            start_time = datetime.now(timezone.utc)
            try:
                response = await synthesis_agent.agenerate(synthesis_prompt)

                if isinstance(response, tuple):
                    response_text = response[0]
                    token_usage = response[2] if len(response) > 2 else None
                else:
                    response_text = str(response)
                    token_usage = None

                time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                # Parse synthesis response
                synthesis_parsed = self._parse_analysis_response(response_text)

                # Update structured output with synthesis data
                if synthesis_parsed:
                    if "executive_summary" in synthesis_parsed:
                        structured_output.confidence = synthesis_parsed.get("confidence", 0.8)
                    if "synthesized_recommendations" in synthesis_parsed:
                        structured_output.recommendations = synthesis_parsed["synthesized_recommendations"]

                # Generate narrative report
                narrative_report = self._generate_narrative_report(
                    policy_input,
                    agent_analyses,
                    structured_output,
                    synthesis_parsed.get("executive_summary", ""),
                )

                # Record synthesis step
                input_tokens = token_usage.input if token_usage and hasattr(token_usage, "input") else 0
                output_tokens = token_usage.output if token_usage and hasattr(token_usage, "output") else 0
                model_name = getattr(synthesis_agent, "model", synthesis_agent.name)

                synthesis_step = StepResult(
                    step_name="synthesis",
                    agent_name=synthesis_agent.name,
                    output=narrative_report[:500],
                    time_ms=time_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=self._pricing.calculate_total_cost(model_name, input_tokens, output_tokens),
                    metadata={"synthesis_agent": model_name},
                )

            except Exception:
                # Fallback to basic narrative without synthesis agent
                narrative_report = self._generate_narrative_report(
                    policy_input,
                    agent_analyses,
                    structured_output,
                    "",
                )

        return structured_output, narrative_report, synthesis_step

    def _build_structured_output(
        self,
        policy_input: PolicyInput,
        agent_analyses: List[AgentAnalysis],
    ) -> PolicyAnalysisOutput:
        """Build structured output from agent analyses."""
        import statistics

        # Calculate overall scores
        overall_scores = [a.overall_score for a in agent_analyses]
        mean_overall = statistics.mean(overall_scores) if overall_scores else 50
        std_overall = statistics.stdev(overall_scores) if len(overall_scores) > 1 else 0

        # Determine consensus level
        if std_overall < 10:
            consensus = ConsensusLevel.HIGH
        elif std_overall < 20:
            consensus = ConsensusLevel.MODERATE
        elif std_overall < 30:
            consensus = ConsensusLevel.LOW
        else:
            consensus = ConsensusLevel.DIVERGENT

        # Synthesize criterion scores
        criterion_scores: Dict[str, CriterionScoreOutput] = {}
        for criterion in AnalysisCriterion:
            scores_for_criterion = []
            rationales = []

            for analysis in agent_analyses:
                for cs in analysis.criterion_scores:
                    if cs.criterion == criterion:
                        scores_for_criterion.append(cs.score)
                        rationales.append(cs.rationale)

            if scores_for_criterion:
                synthesized = SynthesizedScore.from_scores(
                    criterion, scores_for_criterion, " | ".join(rationales[:3])
                )
                criterion_scores[criterion.value] = CriterionScoreOutput(
                    criterion=criterion.value,
                    mean_score=synthesized.mean_score,
                    min_score=synthesized.min_score,
                    max_score=synthesized.max_score,
                    consensus_level=synthesized.consensus_level.value,
                    rationale=synthesized.synthesized_rationale,
                )

        # Consolidate red flags
        red_flags: List[RedFlagOutput] = []
        flag_titles_seen: Dict[str, int] = {}

        for analysis in agent_analyses:
            for flag in analysis.red_flags:
                key = f"{flag.category.value}:{flag.title}"
                if key in flag_titles_seen:
                    # Increment count for existing flag
                    for rf in red_flags:
                        if rf.title == flag.title and rf.category == flag.category.value:
                            rf.agents_identifying += 1
                            break
                else:
                    flag_titles_seen[key] = 1
                    red_flags.append(
                        RedFlagOutput(
                            flag_id=flag.flag_id,
                            severity=flag.severity.value,
                            category=flag.category.value,
                            title=flag.title,
                            description=flag.description,
                            evidence_quotes=flag.evidence_quotes,
                            agents_identifying=1,
                        )
                    )

        # Count flags by severity
        critical_count = sum(1 for f in red_flags if f.severity == "critical")
        major_count = sum(1 for f in red_flags if f.severity == "major")
        minor_count = sum(1 for f in red_flags if f.severity == "minor")

        # Collect recommendations
        all_recommendations: List[str] = []
        for analysis in agent_analyses:
            all_recommendations.extend(analysis.recommendations)
        # Deduplicate while preserving order
        seen = set()
        unique_recommendations = []
        for rec in all_recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)

        return PolicyAnalysisOutput(
            analysis_id=f"pa-{uuid.uuid4().hex[:8]}",
            policy_title=policy_input.title or "Untitled Policy",
            policy_type=policy_input.policy_type.value,
            jurisdiction=policy_input.jurisdiction,
            overall_score=int(mean_overall),
            overall_assessment=score_to_assessment(int(mean_overall)).value,
            confidence=0.8,  # Will be updated by synthesis
            criterion_scores=criterion_scores,
            red_flags=red_flags,
            critical_flags_count=critical_count,
            major_flags_count=major_count,
            minor_flags_count=minor_count,
            agent_count=len(agent_analyses),
            consensus_level=consensus.value,
            score_variance=std_overall,
            recommendations=unique_recommendations[:10],  # Limit to top 10
            analyzed_at=datetime.now(timezone.utc),
        )

    def _format_analyses_for_synthesis(self, analyses: List[AgentAnalysis]) -> str:
        """Format agent analyses for synthesis prompt."""
        parts = []
        for i, analysis in enumerate(analyses, 1):
            parts.append(f"""
### Agent {i}: {analysis.agent_name} ({analysis.model})

**Overall Score:** {analysis.overall_score}/100 ({analysis.overall_assessment.value})

**Executive Summary:**
{analysis.executive_summary}

**Criterion Scores:**
{self._format_criterion_scores(analysis.criterion_scores)}

**Red Flags Identified:** {len(analysis.red_flags)}
{self._format_red_flags_brief(analysis.red_flags)}

**Recommendations:**
{chr(10).join(f"- {r}" for r in analysis.recommendations[:5])}
""")
        return "\n---\n".join(parts)

    def _format_criterion_scores(self, scores: List[CriterionScore]) -> str:
        """Format criterion scores for display."""
        lines = []
        for cs in scores:
            lines.append(f"- {cs.criterion.value}: {cs.score}/100 (confidence: {cs.confidence:.1f})")
        return "\n".join(lines) if lines else "No criterion scores"

    def _format_red_flags_brief(self, flags: List[RedFlag]) -> str:
        """Format red flags briefly."""
        if not flags:
            return "None identified"
        lines = []
        for flag in flags[:5]:
            lines.append(f"- [{flag.severity.value.upper()}] {flag.title}")
        if len(flags) > 5:
            lines.append(f"- ... and {len(flags) - 5} more")
        return "\n".join(lines)

    def _generate_narrative_report(
        self,
        policy_input: PolicyInput,
        agent_analyses: List[AgentAnalysis],
        structured_output: PolicyAnalysisOutput,
        executive_summary: str,
    ) -> str:
        """Generate narrative markdown report."""
        # Build criterion sections
        criterion_sections = []
        for criterion in AnalysisCriterion:
            if criterion.value in structured_output.criterion_scores:
                cs = structured_output.criterion_scores[criterion.value]
                criterion_name = criterion.value.replace("_", " ").title()
                criterion_sections.append(f"""
### {criterion_name}

| Metric | Value |
|--------|-------|
| Mean Score | {cs.mean_score:.1f}/100 |
| Range | {cs.min_score} - {cs.max_score} |
| Consensus | {cs.consensus_level} |

{cs.rationale if cs.rationale else 'No detailed rationale available.'}
""")

        # Build red flags section
        if structured_output.red_flags:
            red_flags_lines = []
            for flag in structured_output.red_flags:
                severity_emoji = {"critical": "🚨", "major": "⚠️", "minor": "📝"}.get(flag.severity, "📝")
                red_flags_lines.append(
                    f"**{severity_emoji} [{flag.severity.upper()}] {flag.title}**\n\n"
                    f"{flag.description}\n\n"
                    f"*Identified by {flag.agents_identifying} agent(s)*"
                )
            red_flags_section = "\n\n---\n\n".join(red_flags_lines)
        else:
            red_flags_section = "No significant red flags identified."

        # Build recommendations section
        if structured_output.recommendations:
            recommendations_section = "\n".join(
                f"{i}. {rec}" for i, rec in enumerate(structured_output.recommendations, 1)
            )
        else:
            recommendations_section = "No specific recommendations provided."

        # Use executive summary from synthesis or build one
        if not executive_summary:
            executive_summary = f"""
This policy analysis examined "{policy_input.title or 'Untitled Policy'}" through the lens of
benefit to ordinary people, empowerment, power balance, and historical justice.

**Overall Assessment:** The policy received a score of {structured_output.overall_score}/100,
classified as "{structured_output.overall_assessment}".

**Agent Consensus:** {structured_output.agent_count} agents analyzed this policy with
{structured_output.consensus_level} consensus (score variance: {structured_output.score_variance:.1f}).

**Key Concerns:** {structured_output.critical_flags_count} critical, {structured_output.major_flags_count} major,
and {structured_output.minor_flags_count} minor red flags were identified.
"""

        # Calculate totals
        total_cost = sum(a.cost for a in agent_analyses)
        total_time_ms = sum(a.time_ms for a in agent_analyses)
        agent_names = ", ".join(a.model for a in agent_analyses)

        return NARRATIVE_REPORT_TEMPLATE.format(
            policy_title=policy_input.title or "Untitled Policy",
            analysis_date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            policy_type=policy_input.policy_type.value,
            jurisdiction=policy_input.jurisdiction or "Unknown",
            executive_summary=executive_summary,
            overall_score=structured_output.overall_score,
            overall_assessment=structured_output.overall_assessment,
            confidence=structured_output.confidence,
            consensus_level=structured_output.consensus_level,
            criterion_sections="\n".join(criterion_sections),
            red_flags_section=red_flags_section,
            recommendations_section=recommendations_section,
            agent_count=structured_output.agent_count,
            total_cost=total_cost,
            total_time_ms=total_time_ms,
            agent_names=agent_names,
        )
