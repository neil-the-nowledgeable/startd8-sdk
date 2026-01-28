"""
Rule-Based Scoring Strategies for Evaluation System

Provides deterministic rule-based scoring for LLM responses,
useful for fast, consistent evaluation without requiring LLM calls.
"""

import re
from typing import Any, Dict, List, Optional

from .dimensions import DimensionScore, ScoringDimension
from .tasks import Task


class RuleBasedScorer:
    """
    Rule-based scorer for evaluating LLM responses.

    Applies deterministic rules to score responses on various dimensions
    without requiring LLM judge calls. Useful for:
    - Fast evaluation during development
    - Consistent baseline scoring
    - Pre-filtering before expensive LLM judging

    Example:
        >>> scorer = RuleBasedScorer()
        >>> is_valid = scorer.check_syntax_valid("def hello(): print('hi')", "python")
        >>> has_code = scorer.check_has_code_blocks("Here is code: ```python\\nprint('hi')\\n```")
    """

    # Language-specific syntax validation patterns
    _SYNTAX_PATTERNS: Dict[str, List[re.Pattern]] = {
        "python": [
            re.compile(r"^\s*(def|class|import|from|if|for|while|try|with)\s", re.MULTILINE),
            re.compile(r":\s*$", re.MULTILINE),  # Colon at end of line
        ],
        "javascript": [
            re.compile(r"(function|const|let|var|class|import|export)\s", re.MULTILINE),
            re.compile(r"[{};]", re.MULTILINE),  # Braces and semicolons
        ],
        "typescript": [
            re.compile(r"(function|const|let|var|class|interface|type|import|export)\s", re.MULTILINE),
            re.compile(r"[{};:]", re.MULTILINE),
        ],
        "java": [
            re.compile(r"(public|private|protected|class|interface|void|int|String)\s", re.MULTILINE),
            re.compile(r"[{};]", re.MULTILINE),
        ],
        "rust": [
            re.compile(r"(fn|let|mut|struct|impl|pub|use|mod)\s", re.MULTILINE),
            re.compile(r"[{};]", re.MULTILINE),
        ],
        "go": [
            re.compile(r"(func|package|import|type|var|const)\s", re.MULTILINE),
            re.compile(r"[{};]", re.MULTILINE),
        ],
    }

    # Common code block patterns
    _CODE_BLOCK_PATTERN = re.compile(r"```[\w]*\n[\s\S]*?\n```", re.MULTILINE)
    _INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")

    # TODO/placeholder patterns to detect incomplete responses
    _TODO_PATTERNS = [
        re.compile(r"\bTODO\b", re.IGNORECASE),
        re.compile(r"\bFIXME\b", re.IGNORECASE),
        re.compile(r"\bXXX\b"),
        re.compile(r"\.\.\..*implement", re.IGNORECASE),
        re.compile(r"#\s*add\s+(your|code|implementation)", re.IGNORECASE),
        re.compile(r"//\s*add\s+(your|code|implementation)", re.IGNORECASE),
        re.compile(r"pass\s*#.*todo", re.IGNORECASE),
        re.compile(r"\[placeholder\]", re.IGNORECASE),
        re.compile(r"<insert.*here>", re.IGNORECASE),
    ]

    def check_syntax_valid(self, response: str, language: str) -> bool:
        """
        Check if response contains syntactically valid-looking code.

        Note: This is a heuristic check, not a full syntax validator.
        It looks for language-specific patterns that indicate code structure.

        Args:
            response: The response text to check
            language: Programming language (python, javascript, etc.)

        Returns:
            True if response appears to contain valid code syntax
        """
        language = language.lower()

        # Extract code from code blocks if present
        code_blocks = self._CODE_BLOCK_PATTERN.findall(response)
        code_to_check = "\n".join(code_blocks) if code_blocks else response

        # If language not supported, be permissive
        patterns = self._SYNTAX_PATTERNS.get(language, [])
        if not patterns:
            # For unknown languages, check for basic code indicators
            return bool(code_blocks) or bool(self._INLINE_CODE_PATTERN.search(response))

        # Check if at least one pattern matches
        return any(pattern.search(code_to_check) for pattern in patterns)

    def check_has_code_blocks(self, response: str) -> bool:
        """
        Check if response contains markdown code blocks.

        Args:
            response: The response text to check

        Returns:
            True if response contains at least one code block (```...```)
        """
        return bool(self._CODE_BLOCK_PATTERN.search(response))

    def check_minimum_length(self, response: str, min_chars: int) -> bool:
        """
        Check if response meets minimum length requirement.

        Args:
            response: The response text to check
            min_chars: Minimum number of characters required

        Returns:
            True if response has at least min_chars characters
        """
        return len(response.strip()) >= min_chars

    def check_contains_keywords(self, response: str, keywords: List[str]) -> List[str]:
        """
        Check which keywords are present in the response.

        Args:
            response: The response text to check
            keywords: List of keywords to look for (case-insensitive)

        Returns:
            List of keywords that were found in the response
        """
        response_lower = response.lower()
        return [kw for kw in keywords if kw.lower() in response_lower]

    def check_no_todo_placeholders(self, response: str) -> bool:
        """
        Check if response is free of TODO/placeholder markers.

        Args:
            response: The response text to check

        Returns:
            True if response contains no TODO/placeholder patterns
        """
        for pattern in self._TODO_PATTERNS:
            if pattern.search(response):
                return False
        return True

    def calculate_completeness_score(
        self,
        response: str,
        criteria: List[str]
    ) -> float:
        """
        Calculate completeness score based on criteria coverage.

        Scores how well the response addresses the given criteria
        by checking for keyword presence.

        Args:
            response: The response text to evaluate
            criteria: List of criteria/keywords that should be addressed

        Returns:
            Score between 0.0 and 1.0 representing criteria coverage
        """
        if not criteria:
            return 1.0

        found = self.check_contains_keywords(response, criteria)
        return len(found) / len(criteria)

    def score_response(
        self,
        response: str,
        task: Task
    ) -> Dict[ScoringDimension, DimensionScore]:
        """
        Score a response across multiple dimensions using rules.

        Applies all available rule-based checks to generate scores
        for each scoring dimension.

        Args:
            response: The response text to evaluate
            task: The task definition for context

        Returns:
            Dictionary mapping dimensions to their scores
        """
        scores: Dict[ScoringDimension, DimensionScore] = {}

        # Score CORRECTNESS - basic structural checks
        correctness_score = self._score_correctness(response, task)
        scores[ScoringDimension.CORRECTNESS] = correctness_score

        # Score COMPLETENESS - criteria coverage
        completeness_score = self._score_completeness(response, task)
        scores[ScoringDimension.COMPLETENESS] = completeness_score

        # Score CODE_QUALITY - style and structure
        code_quality_score = self._score_code_quality(response, task)
        scores[ScoringDimension.CODE_QUALITY] = code_quality_score

        # Score EFFICIENCY - placeholder (rules can't deeply assess)
        efficiency_score = self._score_efficiency(response, task)
        scores[ScoringDimension.EFFICIENCY] = efficiency_score

        # Score SECURITY - basic pattern checks
        security_score = self._score_security(response, task)
        scores[ScoringDimension.SECURITY] = security_score

        return scores

    def _score_correctness(self, response: str, task: Task) -> DimensionScore:
        """Score response correctness based on structural rules."""
        checks_passed = 0
        total_checks = 3
        details: Dict[str, Any] = {}

        # Check 1: Has substantial content
        has_content = self.check_minimum_length(response, 100)
        details["has_content"] = has_content
        if has_content:
            checks_passed += 1

        # Check 2: No incomplete placeholders
        no_placeholders = self.check_no_todo_placeholders(response)
        details["no_placeholders"] = no_placeholders
        if no_placeholders:
            checks_passed += 1

        # Check 3: Has code if coding task
        # Handle both enum and string (Pydantic model uses use_enum_values=True)
        category = task.category.value if hasattr(task.category, 'value') else task.category
        if category == "coding":
            has_code = self.check_has_code_blocks(response)
            details["has_code"] = has_code
            if has_code:
                checks_passed += 1
        else:
            # Non-coding tasks get this point automatically
            checks_passed += 1
            details["has_code"] = None

        score = checks_passed / total_checks

        return DimensionScore(
            dimension=ScoringDimension.CORRECTNESS,
            score=score,
            confidence=0.6,  # Rule-based has moderate confidence
            explanation=f"Passed {checks_passed}/{total_checks} correctness checks",
            details=details,
        )

    def _score_completeness(self, response: str, task: Task) -> DimensionScore:
        """Score response completeness based on criteria coverage."""
        # Extract criteria names from task
        criteria_names = [c.name for c in task.evaluation_criteria]

        if not criteria_names:
            # No criteria defined, use task tags as proxy
            criteria_names = task.tags if task.tags else []

        if not criteria_names:
            return DimensionScore(
                dimension=ScoringDimension.COMPLETENESS,
                score=0.8,  # Default moderate score when no criteria
                confidence=0.3,  # Low confidence without criteria
                explanation="No explicit criteria to evaluate against",
                details={"criteria_count": 0},
            )

        coverage = self.calculate_completeness_score(response, criteria_names)

        return DimensionScore(
            dimension=ScoringDimension.COMPLETENESS,
            score=coverage,
            confidence=0.5,
            explanation=f"Addressed {int(coverage * len(criteria_names))}/{len(criteria_names)} criteria",
            details={
                "criteria_count": len(criteria_names),
                "found_criteria": self.check_contains_keywords(response, criteria_names),
            },
        )

    def _score_code_quality(self, response: str, task: Task) -> DimensionScore:
        """Score response code quality using heuristics."""
        # Handle both enum and string (Pydantic model uses use_enum_values=True)
        category = task.category.value if hasattr(task.category, 'value') else task.category
        if category != "coding":
            return DimensionScore(
                dimension=ScoringDimension.CODE_QUALITY,
                score=0.8,
                confidence=0.3,
                explanation="Code quality not applicable for non-coding task",
                details={"applicable": False},
            )

        score = 0.0
        details: Dict[str, Any] = {"applicable": True}

        # Check for code blocks
        has_blocks = self.check_has_code_blocks(response)
        details["has_code_blocks"] = has_blocks
        if has_blocks:
            score += 0.3

        # Check for no placeholders
        no_todos = self.check_no_todo_placeholders(response)
        details["no_placeholders"] = no_todos
        if no_todos:
            score += 0.3

        # Check for reasonable length (not too short)
        code_blocks = self._CODE_BLOCK_PATTERN.findall(response)
        total_code_length = sum(len(block) for block in code_blocks)
        details["code_length"] = total_code_length
        if total_code_length >= 50:
            score += 0.2

        # Check for comments (good practice)
        has_comments = bool(re.search(r"(#|//|/\*|\"\"\"|''')", response))
        details["has_comments"] = has_comments
        if has_comments:
            score += 0.2

        return DimensionScore(
            dimension=ScoringDimension.CODE_QUALITY,
            score=min(score, 1.0),
            confidence=0.5,
            explanation=f"Code quality heuristic score: {score:.2f}",
            details=details,
        )

    def _score_efficiency(self, response: str, task: Task) -> DimensionScore:
        """
        Score response efficiency.

        Note: Rule-based scoring has limited ability to assess efficiency,
        so this provides a baseline score with low confidence.
        """
        # Basic heuristics for efficiency
        score = 0.7  # Default moderate score
        details: Dict[str, Any] = {}

        # Check for efficiency-related keywords
        efficiency_keywords = [
            "O(n)", "O(1)", "O(log", "complexity", "efficient",
            "optimize", "performance", "cache", "memoize"
        ]
        found = self.check_contains_keywords(response, efficiency_keywords)
        details["efficiency_keywords_found"] = found

        if found:
            score = min(0.7 + len(found) * 0.05, 1.0)

        # Penalize if mentions inefficient patterns
        inefficient_keywords = ["O(n^2)", "O(n^3)", "nested loop", "brute force"]
        inefficient_found = self.check_contains_keywords(response, inefficient_keywords)
        details["inefficient_keywords_found"] = inefficient_found

        if inefficient_found:
            score = max(score - 0.2, 0.3)

        return DimensionScore(
            dimension=ScoringDimension.EFFICIENCY,
            score=score,
            confidence=0.3,  # Low confidence for rule-based efficiency
            explanation="Efficiency assessed via keyword heuristics (limited accuracy)",
            details=details,
        )

    def _score_security(self, response: str, task: Task) -> DimensionScore:
        """Score response security using pattern detection."""
        score = 1.0  # Start perfect, deduct for issues
        details: Dict[str, Any] = {"issues_found": []}

        # Security anti-patterns to check
        security_issues = [
            (r"eval\s*\(", "eval() usage detected"),
            (r"exec\s*\(", "exec() usage detected"),
            (r"shell\s*=\s*True", "Shell=True in subprocess"),
            (r"password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password"),
            (r"api_key\s*=\s*['\"][^'\"]+['\"]", "Hardcoded API key"),
            (r"secret\s*=\s*['\"][^'\"]+['\"]", "Hardcoded secret"),
            (r"SELECT\s+\*\s+FROM.*WHERE.*\+", "Potential SQL injection"),
            (r"\.format\(.*user", "Potential format string injection"),
            (r"pickle\.loads?\(", "Unsafe pickle usage"),
            (r"yaml\.load\([^)]*\)", "Unsafe YAML load (use safe_load)"),
        ]

        for pattern, issue_name in security_issues:
            if re.search(pattern, response, re.IGNORECASE):
                score -= 0.15
                details["issues_found"].append(issue_name)

        score = max(score, 0.0)

        explanation = (
            "No security issues detected"
            if not details["issues_found"]
            else f"Found {len(details['issues_found'])} potential security issues"
        )

        return DimensionScore(
            dimension=ScoringDimension.SECURITY,
            score=score,
            confidence=0.6,
            explanation=explanation,
            details=details,
        )
