"""
LLM-as-Judge Implementation for Evaluation System

Provides LLM-based evaluation of responses using judge prompts
for semantic understanding of quality dimensions.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .dimensions import DimensionScore, ScoringDimension
from .tasks import Task


@dataclass
class JudgePromptTemplate:
    """
    Template for generating LLM judge prompts.

    Contains prompt templates for different evaluation aspects
    that can be customized per dimension.

    Attributes:
        dimension: The dimension this template evaluates
        system_prompt: System prompt for the judge
        evaluation_prompt: Main evaluation prompt template
        rubric: Scoring rubric description
    """
    dimension: ScoringDimension
    system_prompt: str
    evaluation_prompt: str
    rubric: str

    @classmethod
    def default_templates(cls) -> Dict[ScoringDimension, "JudgePromptTemplate"]:
        """Get default judge templates for all dimensions."""
        return {
            ScoringDimension.CORRECTNESS: cls(
                dimension=ScoringDimension.CORRECTNESS,
                system_prompt="You are an expert code reviewer evaluating solution correctness.",
                evaluation_prompt="""Evaluate the CORRECTNESS of the following response.

## Task Description
{task_description}

## Response to Evaluate
{response}

{reference_section}

## Evaluation Criteria
- Does the response correctly solve the problem?
- Are there any logical errors or bugs?
- Does it handle edge cases appropriately?
- Would this code work as expected?

Provide your evaluation in the following JSON format:
{{
    "score": <float 0.0-1.0>,
    "confidence": <float 0.0-1.0>,
    "explanation": "<detailed explanation>",
    "issues": ["<issue1>", "<issue2>", ...],
    "strengths": ["<strength1>", "<strength2>", ...]
}}""",
                rubric="""Scoring Rubric:
0.0-0.3: Major errors, solution does not work
0.3-0.5: Significant issues, partially works
0.5-0.7: Minor issues, mostly correct
0.7-0.9: Correct with small improvements possible
0.9-1.0: Excellent, fully correct solution""",
            ),

            ScoringDimension.COMPLETENESS: cls(
                dimension=ScoringDimension.COMPLETENESS,
                system_prompt="You are an expert evaluating solution completeness and thoroughness.",
                evaluation_prompt="""Evaluate the COMPLETENESS of the following response.

## Task Description
{task_description}

## Response to Evaluate
{response}

{reference_section}

## Evaluation Criteria
- Are all requirements from the task addressed?
- Is the solution thorough and comprehensive?
- Are there any missing components or features?
- Does it include proper documentation/comments?

Provide your evaluation in the following JSON format:
{{
    "score": <float 0.0-1.0>,
    "confidence": <float 0.0-1.0>,
    "explanation": "<detailed explanation>",
    "missing_elements": ["<element1>", "<element2>", ...],
    "addressed_requirements": ["<req1>", "<req2>", ...]
}}""",
                rubric="""Scoring Rubric:
0.0-0.3: Major requirements missing
0.3-0.5: Several requirements unaddressed
0.5-0.7: Most requirements addressed
0.7-0.9: Nearly complete, minor gaps
0.9-1.0: Fully complete and thorough""",
            ),

            ScoringDimension.CODE_QUALITY: cls(
                dimension=ScoringDimension.CODE_QUALITY,
                system_prompt="You are a senior software engineer evaluating code quality and best practices.",
                evaluation_prompt="""Evaluate the CODE QUALITY of the following response.

## Task Description
{task_description}

## Response to Evaluate
{response}

{reference_section}

## Evaluation Criteria
- Is the code readable and well-structured?
- Does it follow language idioms and best practices?
- Is naming clear and consistent?
- Is error handling appropriate?
- Are there proper comments and documentation?

Provide your evaluation in the following JSON format:
{{
    "score": <float 0.0-1.0>,
    "confidence": <float 0.0-1.0>,
    "explanation": "<detailed explanation>",
    "quality_issues": ["<issue1>", "<issue2>", ...],
    "good_practices": ["<practice1>", "<practice2>", ...]
}}""",
                rubric="""Scoring Rubric:
0.0-0.3: Poor quality, hard to read/maintain
0.3-0.5: Below average, several issues
0.5-0.7: Acceptable quality
0.7-0.9: Good quality, minor improvements possible
0.9-1.0: Excellent, production-ready quality""",
            ),

            ScoringDimension.EFFICIENCY: cls(
                dimension=ScoringDimension.EFFICIENCY,
                system_prompt="You are a performance expert evaluating algorithmic efficiency and optimization.",
                evaluation_prompt="""Evaluate the EFFICIENCY of the following response.

## Task Description
{task_description}

## Response to Evaluate
{response}

{reference_section}

## Evaluation Criteria
- What is the time complexity of the solution?
- What is the space complexity?
- Are there unnecessary operations or redundant code?
- Could the solution be optimized significantly?
- Is the approach appropriate for the problem scale?

Provide your evaluation in the following JSON format:
{{
    "score": <float 0.0-1.0>,
    "confidence": <float 0.0-1.0>,
    "explanation": "<detailed explanation>",
    "time_complexity": "<big-O notation>",
    "space_complexity": "<big-O notation>",
    "optimization_opportunities": ["<opt1>", "<opt2>", ...]
}}""",
                rubric="""Scoring Rubric:
0.0-0.3: Very inefficient, poor complexity
0.3-0.5: Suboptimal, could be significantly improved
0.5-0.7: Acceptable efficiency
0.7-0.9: Efficient, minor optimizations possible
0.9-1.0: Optimal or near-optimal solution""",
            ),

            ScoringDimension.SECURITY: cls(
                dimension=ScoringDimension.SECURITY,
                system_prompt="You are a security expert evaluating code for vulnerabilities and security best practices.",
                evaluation_prompt="""Evaluate the SECURITY of the following response.

## Task Description
{task_description}

## Response to Evaluate
{response}

{reference_section}

## Evaluation Criteria
- Are there any security vulnerabilities (injection, XSS, etc.)?
- Is user input properly validated and sanitized?
- Are secrets/credentials handled securely?
- Does it follow security best practices?
- Are there any unsafe operations?

Provide your evaluation in the following JSON format:
{{
    "score": <float 0.0-1.0>,
    "confidence": <float 0.0-1.0>,
    "explanation": "<detailed explanation>",
    "vulnerabilities": ["<vuln1>", "<vuln2>", ...],
    "security_practices": ["<practice1>", "<practice2>", ...]
}}""",
                rubric="""Scoring Rubric:
0.0-0.3: Critical vulnerabilities present
0.3-0.5: Significant security issues
0.5-0.7: Some security concerns
0.7-0.9: Generally secure, minor issues
0.9-1.0: Excellent security practices""",
            ),
        }


class LLMJudge:
    """
    LLM-based judge for evaluating response quality.

    Uses an LLM agent to semantically evaluate responses across
    multiple quality dimensions.

    Example:
        >>> from startd8.agents import ClaudeAgent
        >>> agent = ClaudeAgent(name="judge", model="claude-sonnet-4-20250514")
        >>> judge = LLMJudge(agent=agent)
        >>> scores = await judge.evaluate(response, task)
    """

    def __init__(
        self,
        agent: Any,  # BaseAgent type
        dimensions: Optional[List[ScoringDimension]] = None,
        templates: Optional[Dict[ScoringDimension, JudgePromptTemplate]] = None,
    ):
        """
        Initialize the LLM judge.

        Args:
            agent: BaseAgent instance to use for judging
            dimensions: List of dimensions to evaluate (default: all)
            templates: Custom prompt templates (default: built-in templates)
        """
        self.agent = agent
        self.dimensions = dimensions or list(ScoringDimension)
        self.templates = templates or JudgePromptTemplate.default_templates()

    async def evaluate(
        self,
        response: str,
        task: Task,
        reference: Optional[str] = None,
    ) -> List[DimensionScore]:
        """
        Evaluate a response using LLM judge across configured dimensions.

        Args:
            response: The response text to evaluate
            task: The task definition
            reference: Optional reference solution for comparison

        Returns:
            List of DimensionScore objects for each evaluated dimension
        """
        scores: List[DimensionScore] = []

        for dimension in self.dimensions:
            prompt = self._build_judge_prompt(response, task, dimension, reference)
            score = await self._evaluate_dimension(prompt, dimension)
            scores.append(score)

        return scores

    def _build_judge_prompt(
        self,
        response: str,
        task: Task,
        dimension: ScoringDimension,
        reference: Optional[str] = None,
    ) -> str:
        """
        Build the evaluation prompt for a dimension.

        Args:
            response: Response to evaluate
            task: Task definition
            dimension: Dimension to evaluate
            reference: Optional reference solution

        Returns:
            Formatted prompt string
        """
        template = self.templates.get(dimension)
        if not template:
            raise ValueError(f"No template for dimension: {dimension}")

        # Build reference section
        reference_section = ""
        if reference:
            reference_section = f"""## Reference Solution
{reference}

Compare the response to this reference solution."""
        elif task.reference_solution:
            reference_section = f"""## Reference Solution
{task.reference_solution}

Compare the response to this reference solution."""

        # Build task description from template and description
        task_description = f"""Task: {task.name}

{task.description}

Prompt:
{task.prompt_template}"""

        # Format the prompt
        prompt = f"""{template.system_prompt}

{template.rubric}

{template.evaluation_prompt.format(
    task_description=task_description,
    response=response,
    reference_section=reference_section,
)}"""

        return prompt

    async def _evaluate_dimension(
        self,
        prompt: str,
        dimension: ScoringDimension,
    ) -> DimensionScore:
        """
        Execute evaluation for a single dimension.

        Args:
            prompt: The judge prompt
            dimension: Dimension being evaluated

        Returns:
            DimensionScore for the dimension
        """
        try:
            # Call the agent
            response_text, _, _ = await self.agent.agenerate(prompt)

            # Parse the response
            return self._parse_judge_response(response_text, dimension)

        except Exception as e:
            # Return a fallback score on error
            return DimensionScore(
                dimension=dimension,
                score=0.5,
                confidence=0.1,
                explanation=f"Evaluation failed: {str(e)}",
                details={"error": str(e)},
            )

    def _parse_judge_response(
        self,
        response: str,
        dimension: ScoringDimension,
    ) -> DimensionScore:
        """
        Parse the LLM judge response to extract scores.

        Args:
            response: Raw LLM response text
            dimension: The dimension being scored

        Returns:
            Parsed DimensionScore
        """
        # Try to extract JSON from the response
        json_match = re.search(r"\{[\s\S]*\}", response)

        if json_match:
            try:
                data = json.loads(json_match.group())

                score = float(data.get("score", 0.5))
                confidence = float(data.get("confidence", 0.5))
                explanation = data.get("explanation", "No explanation provided")

                # Clamp values to valid range
                score = max(0.0, min(1.0, score))
                confidence = max(0.0, min(1.0, confidence))

                # Build details from remaining fields
                details = {k: v for k, v in data.items()
                          if k not in ["score", "confidence", "explanation"]}

                return DimensionScore(
                    dimension=dimension,
                    score=score,
                    confidence=confidence,
                    explanation=explanation,
                    details=details if details else None,
                )

            except (json.JSONDecodeError, ValueError, TypeError) as e:
                # Fall through to fallback parsing
                pass

        # Fallback: try to extract score from text
        score = self._extract_score_from_text(response)
        return DimensionScore(
            dimension=dimension,
            score=score,
            confidence=0.3,  # Low confidence for fallback parsing
            explanation=response[:500] if len(response) > 500 else response,
            details={"parse_method": "fallback"},
        )

    def _extract_score_from_text(self, text: str) -> float:
        """
        Extract a score from unstructured text as fallback.

        Args:
            text: Response text to parse

        Returns:
            Extracted score (0.0-1.0), defaults to 0.5 if not found
        """
        text_lower = text.lower()

        # Pattern with explicit denominator (most specific, check first)
        # X/100 format
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*/\s*100", text_lower)
        if match:
            return min(float(match.group(1)) / 100.0, 1.0)

        # X out of 100 format
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*out\s*of\s*100", text_lower)
        if match:
            return min(float(match.group(1)) / 100.0, 1.0)

        # X/10 format
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*/\s*10\b", text_lower)
        if match:
            return min(float(match.group(1)) / 10.0, 1.0)

        # X out of 10 format
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*out\s*of\s*10\b", text_lower)
        if match:
            return min(float(match.group(1)) / 10.0, 1.0)

        # Score: X format (generic)
        match = re.search(r"score[:\s]+([0-9]+(?:\.[0-9]+)?)", text_lower)
        if match:
            value = float(match.group(1))
            if value <= 1.0:
                return value
            elif value <= 10.0:
                return value / 10.0
            else:
                return min(value / 100.0, 1.0)

        # Rating: X format (generic)
        match = re.search(r"rating[:\s]+([0-9]+(?:\.[0-9]+)?)", text_lower)
        if match:
            value = float(match.group(1))
            if value <= 1.0:
                return value
            elif value <= 10.0:
                return value / 10.0
            else:
                return min(value / 100.0, 1.0)

        # Default fallback
        return 0.5
