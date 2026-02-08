"""
Truncation Detection Utilities

Detects when LLM output appears to be truncated, which commonly happens when:
- Processing documents that are too large for single-pass operations
- The LLM hits its max output token limit
- Network issues cause incomplete responses

This module provides utilities to detect truncation and prevent corrupted
outputs from being saved or passed to subsequent pipeline steps.
"""

import logging
import re
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Truncation confidence thresholds — single source of truth.
# Callers should import these rather than hard-coding values.
CONFIDENCE_IS_TRUNCATED = 0.5        # Default gate for TruncationResult.is_truncated
CONFIDENCE_IS_TRUNCATED_STRICT = 0.3 # Gate when strict_mode=True
CONFIDENCE_HIGH = 0.7                # High-confidence truncation (triggers rejection/error)
CONFIDENCE_HIGH_PROSE = 0.9          # Higher bar for prose heuristics (more false-positive prone)


@dataclass
class TruncationResult:
    """Result of truncation detection analysis"""
    is_truncated: bool
    confidence: float  # 0.0 to 1.0
    indicators: List[str]
    details: Dict[str, Any]

    def __bool__(self):
        return self.is_truncated


@dataclass
class PreFlightEstimate:
    """
    Pre-flight size estimation for proactive truncation prevention.

    Used to estimate output size BEFORE generation to prevent truncation,
    rather than detecting it after the fact.

    Attributes:
        estimated_lines: Estimated number of output lines
        estimated_tokens: Estimated output token count
        complexity: Task complexity level
        confidence: Confidence in the estimate (0.0 to 1.0)
        exceeds_limit: Whether estimate exceeds the safe limit
        suggested_action: Recommended action ('generate', 'decompose', 'reject')
        reasoning: Human-readable explanation
    """
    estimated_lines: int
    estimated_tokens: int
    complexity: str  # "low", "medium", "high"
    confidence: float
    exceeds_limit: bool
    suggested_action: str  # "generate", "decompose", "reject"
    reasoning: str
    safe_line_limit: int = 150
    safe_token_limit: int = 500


def estimate_output_size(
    task_description: str,
    inputs: Optional[Dict[str, Any]] = None,
    safe_line_limit: int = 150,
    safe_token_limit: int = 500,
) -> PreFlightEstimate:
    """
    Estimate output size BEFORE generation for proactive truncation prevention.

    This function uses heuristics to estimate how large the LLM output will be,
    allowing callers to decompose large tasks BEFORE hitting token limits.

    Args:
        task_description: Natural language description of what to generate
        inputs: Additional context (target_file, required_exports, etc.)
        safe_line_limit: Maximum safe lines for output (default 150)
        safe_token_limit: Maximum safe tokens for output (default 500)

    Returns:
        PreFlightEstimate with size prediction and recommended action

    Example:
        estimate = estimate_output_size(
            "Implement a REST API client with CRUD operations",
            inputs={"required_exports": ["APIClient", "Response"]}
        )

        if estimate.exceeds_limit:
            # Decompose into smaller tasks
            print(f"Task too large: {estimate.reasoning}")
    """
    inputs = inputs or {}
    task_lower = task_description.lower()

    # Detect complexity from keywords
    high_keywords = [
        "comprehensive", "complete", "full", "entire", "all methods",
        "with tests", "crud", "api", "rest api", "async", "concurrent",
        "error handling", "logging", "metrics", "observability",
    ]
    medium_keywords = [
        "implement", "create", "build", "add", "multiple",
        "methods", "functions", "class", "module", "service",
    ]
    low_keywords = [
        "fix", "patch", "update", "modify", "simple", "basic",
        "single", "one", "small", "minor", "quick",
    ]

    high_score = sum(1 for kw in high_keywords if kw in task_lower)
    medium_score = sum(1 for kw in medium_keywords if kw in task_lower)
    low_score = sum(1 for kw in low_keywords if kw in task_lower)

    if high_score >= 2 or (high_score >= 1 and medium_score >= 2):
        complexity = "high"
        base_multiplier = 1.4
    elif low_score >= 2 and high_score == 0:
        complexity = "low"
        base_multiplier = 0.8
    else:
        complexity = "medium"
        base_multiplier = 1.0

    # Estimate constructs from task and inputs
    lines = 20  # Base minimum

    # Count from required exports
    required_exports = inputs.get("required_exports") or []
    for export in required_exports:
        if export and export[0].isupper():
            lines += 40  # Class
        else:
            lines += 15  # Function

    # Count from task description patterns
    if "class" in task_lower:
        lines += 40
    if "dataclass" in task_lower:
        lines += 15
    if "enum" in task_lower:
        lines += 10
    if "crud" in task_lower:
        lines += 48  # 4 methods * 12 lines
    if "api" in task_lower and "client" in task_lower:
        lines += 60  # API client typically needs multiple methods
    if "test" in task_lower:
        lines += 50  # Tests add significant code

    # Apply complexity multiplier
    estimated_lines = int(lines * base_multiplier)
    estimated_tokens = estimated_lines * 3  # ~3 tokens per line

    # Determine if limits exceeded
    exceeds_limit = estimated_lines > safe_line_limit or estimated_tokens > safe_token_limit

    # Determine action
    if exceeds_limit:
        allows_chunking = inputs.get("allows_chunking", True)
        suggested_action = "decompose" if allows_chunking else "reject"
    else:
        suggested_action = "generate"

    # Calculate confidence
    confidence = 0.5
    if required_exports:
        confidence += 0.2
    if inputs.get("context_files"):
        confidence += 0.1
    if "vague" in task_lower or "something" in task_lower:
        confidence -= 0.2
    confidence = max(0.2, min(0.9, confidence))

    # Build reasoning
    reasoning_parts = [f"Complexity: {complexity}"]
    if required_exports:
        reasoning_parts.append(f"{len(required_exports)} exports requested")
    reasoning_parts.append(f"Estimated {estimated_lines} lines ({estimated_tokens} tokens)")
    if exceeds_limit:
        reasoning_parts.append(f"Exceeds safe limit of {safe_line_limit} lines")

    return PreFlightEstimate(
        estimated_lines=estimated_lines,
        estimated_tokens=estimated_tokens,
        complexity=complexity,
        confidence=confidence,
        exceeds_limit=exceeds_limit,
        suggested_action=suggested_action,
        reasoning="; ".join(reasoning_parts),
        safe_line_limit=safe_line_limit,
        safe_token_limit=safe_token_limit,
    )


# Language-specific code structure markers for truncation detection.
# Each language maps to keywords expected in non-trivial source files.
_LANGUAGE_SECTIONS = {
    "python": ["def ", "class "],
    "typescript": ["function ", "const ", "export "],
    "javascript": ["function ", "const ", "export "],
    "go": ["func ", "type "],
    "rust": ["fn ", "struct "],
    "java": ["class ", "public "],
    "ruby": ["def ", "class "],
    "swift": ["func ", "struct "],
    "kotlin": ["fun ", "class "],
}


def infer_code_language(code: str) -> Optional[str]:
    """Infer programming language from code content using keyword heuristics.

    Returns a language key (e.g. ``"python"``, ``"typescript"``) or ``None``
    if the language cannot be determined.
    """
    if not code or not code.strip():
        return None

    # Strong single-keyword signals (order matters: check specific before generic)
    strong_signals = [
        ("typescript", ["interface ", ": string", ": number", ": boolean",
                        "=> {", "React.", "<React", "useState(", "useEffect("]),
        ("python", ["def ", "self.", "__init__", "elif ", "except ",
                    "yield ", "async def "]),
        ("go", ["func ", "package "]),
        ("rust", ["fn ", "let mut ", "impl ", "let ", "println!", "use std::"]),
        ("java", ["public class ", "private void ", "System.out"]),
        ("ruby", ["def ", "end\n", "require "]),
        ("kotlin", ["fun ", "val ", "data class "]),
        ("swift", ["func ", "var ", "guard let "]),
    ]

    for lang, keywords in strong_signals:
        if sum(1 for kw in keywords if kw in code) >= 2:
            return lang

    # Fallback: TypeScript vs JavaScript (both share const/export/function)
    if any(kw in code for kw in ["import ", "export ", "const "]):
        # Type annotations suggest TypeScript
        if any(kw in code for kw in [": string", ": number", "interface ",
                                      "<", "as ", "readonly "]):
            return "typescript"
        return "javascript"

    return None


def get_expected_sections_for_code(code: str) -> Optional[List[str]]:
    """Return expected code structure markers based on inferred language.

    Returns ``None`` when the language cannot be determined, signalling
    that the ``expected_sections`` check should be skipped entirely.
    """
    language = infer_code_language(code)
    if language is None:
        return None
    return _LANGUAGE_SECTIONS.get(language)


def _looks_like_code(text: str) -> bool:
    """Conservative heuristic: does this text look like source code?

    Used as a fallback when ``infer_code_language()`` returns ``None`` — the
    language isn't recognized but the content is clearly not prose/markdown.

    Checks for structural patterns common across ALL programming languages:
    balanced-looking brace usage, semicolons at line ends, ``import``/
    ``#include`` statements, shebang lines, etc.  Requires 2+ signals to
    trigger, reducing false positives on prose that happens to contain a
    single code-like token.
    """
    if not text or len(text) < 20:
        return False

    signals = 0
    lines = text.split('\n')

    # Lines ending with { or ; (common in C-family, Java, Go, Rust, etc.)
    brace_or_semi = sum(1 for ln in lines if ln.rstrip().endswith(('{', ';')))
    if brace_or_semi >= 3:
        signals += 1

    # Import / include / require at start of lines
    import_lines = sum(
        1 for ln in lines
        if re.match(r'^\s*(import |from |#include |require |use |using )', ln)
    )
    if import_lines >= 1:
        signals += 1

    # Shebang
    if text.startswith('#!'):
        signals += 1

    # Function/method definitions (language-agnostic patterns)
    if re.search(r'\b(function |def |fn |func |sub |proc )\b', text):
        signals += 1

    # Indentation-heavy (4+ lines indented with spaces or tabs)
    indented = sum(1 for ln in lines if re.match(r'^[\t ]{2,}\S', ln))
    if indented >= 4:
        signals += 1

    return signals >= 2


def detect_truncation(
    output: str,
    original_input: Optional[str] = None,
    expected_sections: Optional[List[str]] = None,
    min_output_ratio: float = 0.3,
    strict_mode: bool = False,
    code_mode: Optional[bool] = None,
) -> TruncationResult:
    """
    Detect if LLM output appears to be truncated.

    Uses multiple heuristics to determine if output was cut off:
    1. Unclosed code blocks (```)
    2. Unclosed JSON/YAML structures
    3. Mid-sentence endings
    4. Missing expected sections (if provided)
    5. Dramatic length reduction compared to input
    6. Incomplete markdown structures

    Args:
        output: The LLM output to check
        original_input: Original input document (for length comparison)
        expected_sections: List of section headers expected in output
        min_output_ratio: Minimum acceptable output/input length ratio (default 0.3 = 30%)
        strict_mode: If True, be more aggressive about detecting truncation
        code_mode: Controls whether text-oriented heuristics are skipped.
            - ``True``: Skip prose heuristics (mid-sentence, unclosed strings,
              markdown). Use structural checks only (code blocks, brace balance).
            - ``False``: Use all heuristics (for LLM prose/markdown output).
            - ``None`` (default): **Auto-detect** via ``infer_code_language()``.
              If the content looks like source code, code_mode is enabled
              automatically.  This prevents false positives when callers forget
              to specify the mode — the function adapts to its input.

    Returns:
        TruncationResult with detection results
    """
    indicators = []
    details = {}
    confidence = 0.0

    if not output or not output.strip():
        return TruncationResult(
            is_truncated=True,
            confidence=1.0,
            indicators=["Empty output"],
            details={"output_length": 0}
        )

    output_stripped = output.strip()
    output_length = len(output_stripped)
    details["output_length"] = output_length

    # Auto-detect code_mode when not explicitly set.
    # Conservative: when uncertain, assume code.  False positives on code
    # (blocking valid files) are expensive; false negatives on prose (missing
    # a truncation warning) are cheap since the API-level check still catches
    # real truncation.
    if code_mode is None:
        code_mode = (
            infer_code_language(output_stripped) is not None
            or _looks_like_code(output_stripped)
        )
    details["code_mode"] = code_mode

    # 1. Check for unclosed code blocks
    # Useful for both prose and code (catches LLM wrapper artifacts)
    code_block_count = output_stripped.count("```")
    if code_block_count % 2 != 0:
        indicators.append("Unclosed code block (odd number of ```)")
        confidence += 0.4
        details["code_blocks"] = {"count": code_block_count, "closed": False}

    # 2. Check for unclosed JSON/YAML structures
    if code_mode:
        # In code mode, only flag significant brace imbalance.
        # Naive {/} counting is unreliable for source code (braces in strings,
        # template literals, comments, regex). Only flag when the imbalance is
        # large enough to indicate real truncation, not just string artifacts.
        _code_brace_check = _check_code_brace_balance(output_stripped)
        if _code_brace_check:
            indicators.append(f"Significant brace imbalance: {_code_brace_check}")
            confidence += 0.35
            details["brace_imbalance"] = _code_brace_check
    else:
        json_truncation = _check_json_truncation(output_stripped)
        if json_truncation:
            indicators.append(f"Unclosed JSON/YAML: {json_truncation}")
            confidence += 0.35
            details["json_truncation"] = json_truncation

    # 3-4: Text-oriented checks — skip in code mode
    if not code_mode:
        # 3. Check for mid-sentence ending
        mid_sentence = _check_mid_sentence_ending(output_stripped)
        if mid_sentence:
            indicators.append(f"Mid-sentence ending: {mid_sentence}")
            confidence += 0.3
            details["mid_sentence"] = mid_sentence

        # 4. Check for incomplete markdown structures
        markdown_issues = _check_markdown_truncation(output_stripped)
        if markdown_issues:
            indicators.extend(markdown_issues)
            confidence += 0.2 * len(markdown_issues)
            details["markdown_issues"] = markdown_issues

    # 5. Check length ratio if original input provided
    if original_input:
        input_length = len(original_input.strip())
        details["input_length"] = input_length

        if input_length > 0:
            ratio = output_length / input_length
            details["length_ratio"] = ratio

            # For document polishing, output should be similar length or longer
            if ratio < min_output_ratio:
                indicators.append(f"Output too short: {ratio:.1%} of input (expected >{min_output_ratio:.0%})")
                confidence += 0.4

    # 6. Check for missing expected sections
    if expected_sections:
        missing_sections = []
        for section in expected_sections:
            if code_mode:
                # In code mode, just check for the keyword in the source
                # (no markdown header variants — source code doesn't have them)
                found = section.lower() in output_stripped.lower()
            else:
                # Check for section header in various formats
                section_patterns = [
                    f"## {section}",
                    f"### {section}",
                    f"# {section}",
                    f"**{section}**",
                    section.lower()
                ]
                found = any(p.lower() in output_stripped.lower() for p in section_patterns)
            if not found:
                missing_sections.append(section)

        if missing_sections:
            details["missing_sections"] = missing_sections
            if len(missing_sections) >= len(expected_sections) * 0.5:
                indicators.append(f"Missing {len(missing_sections)}/{len(expected_sections)} expected sections")
                confidence += 0.3

    # 7. Check for common truncation patterns at end — skip in code mode
    # These patterns (unclosed quotes, backticks) are designed for markdown/prose
    # and false-positive on virtually every source code file.
    if not code_mode:
        truncation_patterns = _check_truncation_patterns(output_stripped)
        if truncation_patterns:
            indicators.extend(truncation_patterns)
            confidence += 0.25 * len(truncation_patterns)
            details["truncation_patterns"] = truncation_patterns

    # Cap confidence at 1.0
    confidence = min(confidence, 1.0)

    # Determine if truncated based on confidence threshold
    threshold = CONFIDENCE_IS_TRUNCATED_STRICT if strict_mode else CONFIDENCE_IS_TRUNCATED
    is_truncated = confidence >= threshold

    return TruncationResult(
        is_truncated=is_truncated,
        confidence=confidence,
        indicators=indicators,
        details=details
    )


def _check_code_brace_balance(text: str) -> Optional[str]:
    """Check for significant brace/bracket imbalance in source code.

    Unlike ``_check_json_truncation``, this uses a threshold to tolerate
    small imbalances caused by braces inside string literals, template
    literals, comments, or regex patterns.  Only flags imbalances large
    enough to strongly suggest real truncation (3+ unmatched).
    """
    open_braces = text.count('{')
    close_braces = text.count('}')
    open_brackets = text.count('[')
    close_brackets = text.count(']')
    open_parens = text.count('(')
    close_parens = text.count(')')

    issues = []
    # Threshold of 3 filters out single-brace string literals while still
    # catching genuinely truncated files (which tend to have many unclosed
    # scopes).
    if open_braces - close_braces >= 3:
        issues.append(f"unclosed braces ({open_braces} open, {close_braces} close)")
    if open_brackets - close_brackets >= 3:
        issues.append(f"unclosed brackets ({open_brackets} open, {close_brackets} close)")
    if open_parens - close_parens >= 3:
        issues.append(f"unclosed parentheses ({open_parens} open, {close_parens} close)")

    return ", ".join(issues) if issues else None


def _check_json_truncation(text: str) -> Optional[str]:
    """Check for unclosed JSON/YAML structures"""
    # Count opening and closing braces/brackets
    open_braces = text.count('{')
    close_braces = text.count('}')
    open_brackets = text.count('[')
    close_brackets = text.count(']')
    
    issues = []
    if open_braces > close_braces:
        issues.append(f"unclosed braces ({open_braces} open, {close_braces} close)")
    if open_brackets > close_brackets:
        issues.append(f"unclosed brackets ({open_brackets} open, {close_brackets} close)")
    
    # Check if ends mid-JSON (inside a code block with JSON)
    if "```json" in text.lower() or "```typescript" in text.lower():
        # Find the last code block
        last_code_start = max(
            text.rfind("```json"),
            text.rfind("```JSON"),
            text.rfind("```typescript"),
            text.rfind("```TypeScript")
        )
        if last_code_start != -1:
            after_start = text[last_code_start:]
            # Check if there's a closing ```
            if after_start.count("```") == 1:  # Only the opening, no closing
                issues.append("code block not closed")
    
    return ", ".join(issues) if issues else None


def _check_mid_sentence_ending(text: str) -> Optional[str]:
    """Check if text ends mid-sentence"""
    # Get last 100 characters
    ending = text[-100:].strip() if len(text) > 100 else text.strip()
    
    # Common mid-sentence indicators
    mid_sentence_patterns = [
        # Ends with incomplete word or punctuation
        (r'[a-zA-Z]{2,}$', "ends mid-word"),
        (r'[,:;]\s*$', "ends with comma/colon/semicolon"),
        (r'\.\.\.\s*$', "ends with ellipsis"),
        (r'["\']$', "ends with unclosed quote"),
        (r'\($', "ends with unclosed parenthesis"),
        # Ends with common incomplete phrases
        (r'(?:the|a|an|and|or|but|in|on|at|to|for|of|with)\s*$', "ends with incomplete phrase"),
        # Ends mid-property in JSON/YAML
        (r'["\']:\s*$', "ends mid-property assignment"),
        (r'["\'],?\s*$', "ends mid-JSON value"),
    ]
    
    for pattern, description in mid_sentence_patterns:
        if re.search(pattern, ending, re.IGNORECASE):
            return description
    
    return None


def _check_markdown_truncation(text: str) -> List[str]:
    """Check for incomplete markdown structures"""
    issues = []
    
    # Check for unclosed tables
    table_rows = re.findall(r'^\|.*\|$', text, re.MULTILINE)
    if table_rows:
        last_row = table_rows[-1]
        # Check if table seems incomplete (no closing row or ends mid-table)
        if last_row.count('|') < 3:  # Minimal table has at least 3 pipes
            issues.append("Incomplete table structure")
    
    # Check for incomplete lists
    lines = text.split('\n')
    if lines:
        last_lines = lines[-5:]  # Check last 5 lines
        for line in last_lines:
            # Check for incomplete list items
            if re.match(r'^\s*[-*+]\s*$', line):
                issues.append("Empty list item at end")
                break
            if re.match(r'^\s*\d+\.\s*$', line):
                issues.append("Empty numbered list item at end")
                break
    
    # Check for incomplete headers
    if re.search(r'^#+\s*$', text.split('\n')[-1] if text.split('\n') else '', re.MULTILINE):
        issues.append("Empty header at end")
    
    return issues


def _check_truncation_patterns(text: str) -> List[str]:
    """Check for common truncation patterns at the end of text"""
    patterns = []
    
    # Get last 200 characters for analysis
    ending = text[-200:] if len(text) > 200 else text
    
    # Check for abrupt endings in common structures
    abrupt_patterns = [
        (r'"[^"]*$', "Unclosed string at end"),
        (r"'[^']*$", "Unclosed single-quoted string at end"),
        (r'`[^`]*$', "Unclosed inline code at end"),
        (r'\[\s*$', "Empty/unclosed link at end"),
        (r'!\[\s*$', "Empty/unclosed image at end"),
    ]
    
    for pattern, description in abrupt_patterns:
        if re.search(pattern, ending):
            patterns.append(description)
    
    return patterns


def estimate_document_sections(text: str) -> List[str]:
    """
    Estimate expected sections from a document's table of contents.
    
    Useful for detecting if a polished document is missing sections
    that were present in the original.
    
    Args:
        text: Document text
        
    Returns:
        List of section names found in table of contents
    """
    sections = []
    
    # Look for table of contents patterns
    toc_patterns = [
        # Numbered list in TOC
        r'^\d+\.\s*\[([^\]]+)\]',
        # Markdown headers
        r'^#{1,3}\s+(?:\d+\.?\s*)?(.+?)(?:\s*{#|$)',
        # Bold section names
        r'^\*\*(\d+\.?\s*.+?)\*\*',
    ]
    
    for line in text.split('\n'):
        for pattern in toc_patterns:
            match = re.match(pattern, line.strip())
            if match:
                section_name = match.group(1).strip()
                # Clean up section name
                section_name = re.sub(r'^\d+\.?\s*', '', section_name)
                if section_name and len(section_name) > 2:
                    sections.append(section_name)
                break
    
    return sections


def get_truncation_warning_message(result: TruncationResult, step_name: str = None) -> str:
    """
    Generate a user-friendly warning message for truncation detection.
    
    Args:
        result: TruncationResult from detect_truncation
        step_name: Optional pipeline step name
        
    Returns:
        Formatted warning message
    """
    if not result.is_truncated:
        return ""
    
    lines = [
        "⚠️ TRUNCATION DETECTED",
        f"Confidence: {result.confidence:.0%}",
    ]
    
    if step_name:
        lines.append(f"Step: {step_name}")
    
    if result.indicators:
        lines.append("Indicators:")
        for indicator in result.indicators:
            lines.append(f"  • {indicator}")
    
    if "length_ratio" in result.details:
        ratio = result.details["length_ratio"]
        lines.append(f"Output is only {ratio:.1%} of input length")
    
    lines.append("")
    lines.append("The output appears to be incomplete. This typically happens when:")
    lines.append("  1. The document is too large for single-pass processing")
    lines.append("  2. The LLM hit its max output token limit")
    lines.append("")
    lines.append("Recommendation: Use chunked processing for large documents")
    
    return "\n".join(lines)


def log_truncation_result(
    result: TruncationResult,
    source_file: Optional[str] = None,
    feature_name: Optional[str] = None,
    step_name: Optional[str] = None,
    emit_event: bool = True,
) -> None:
    """
    Log a truncation detection result and optionally emit an event.

    Centralizes truncation reporting so callers don't need to handle
    logging and event emission individually.

    Args:
        result: TruncationResult from detect_truncation
        source_file: File that was checked (for log context)
        feature_name: Feature being processed (for log context)
        step_name: Pipeline step name (for log context)
        emit_event: Whether to emit an EventBus event (default True)
    """
    if not result.is_truncated:
        logger.debug(
            "Truncation check passed",
            extra={
                "source_file": source_file,
                "feature_name": feature_name,
                "confidence": result.confidence,
            },
        )
        return

    extra = {
        "source_file": source_file,
        "feature_name": feature_name,
        "step_name": step_name,
        "confidence": result.confidence,
        "indicators": result.indicators,
        "output_length": result.details.get("output_length"),
        "code_mode": result.details.get("code_mode"),
    }

    if result.confidence >= CONFIDENCE_HIGH:
        logger.error(
            "Truncation detected (high confidence): %s — indicators: %s",
            source_file or "unknown",
            "; ".join(result.indicators),
            extra=extra,
        )
    else:
        logger.warning(
            "Possible truncation (low confidence): %s — indicators: %s",
            source_file or "unknown",
            "; ".join(result.indicators),
            extra=extra,
        )

    if emit_event:
        try:
            from .events.types import Event, EventType, EventPriority
            from .events.bus import EventBus

            event_type = (
                EventType.TRUNCATION_DETECTED
                if result.confidence >= CONFIDENCE_HIGH
                else EventType.TRUNCATION_WARNING
            )
            priority = (
                EventPriority.HIGH
                if result.confidence >= CONFIDENCE_HIGH
                else EventPriority.NORMAL
            )

            EventBus.emit(Event(
                type=event_type,
                source="TruncationDetection",
                data={
                    "source_file": source_file,
                    "feature_name": feature_name,
                    "step_name": step_name,
                    "confidence": result.confidence,
                    "indicators": result.indicators,
                    "details": result.details,
                },
                priority=priority,
            ))
        except Exception:
            # Don't let event emission failures break the caller
            logger.debug("Failed to emit truncation event", exc_info=True)

