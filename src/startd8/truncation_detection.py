"""
Truncation Detection Utilities

Detects when LLM output appears to be truncated, which commonly happens when:
- Processing documents that are too large for single-pass operations
- The LLM hits its max output token limit
- Network issues cause incomplete responses

This module provides utilities to detect truncation and prevent corrupted
outputs from being saved or passed to subsequent pipeline steps.
"""

import re
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class TruncationResult:
    """Result of truncation detection analysis"""
    is_truncated: bool
    confidence: float  # 0.0 to 1.0
    indicators: List[str]
    details: Dict[str, Any]
    
    def __bool__(self):
        return self.is_truncated


def detect_truncation(
    output: str,
    original_input: Optional[str] = None,
    expected_sections: Optional[List[str]] = None,
    min_output_ratio: float = 0.3,
    strict_mode: bool = False
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
    
    # 1. Check for unclosed code blocks
    code_block_count = output_stripped.count("```")
    if code_block_count % 2 != 0:
        indicators.append("Unclosed code block (odd number of ```)")
        confidence += 0.4
        details["code_blocks"] = {"count": code_block_count, "closed": False}
    
    # 2. Check for unclosed JSON/YAML structures
    json_truncation = _check_json_truncation(output_stripped)
    if json_truncation:
        indicators.append(f"Unclosed JSON/YAML: {json_truncation}")
        confidence += 0.35
        details["json_truncation"] = json_truncation
    
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
    
    # 7. Check for common truncation patterns at end
    truncation_patterns = _check_truncation_patterns(output_stripped)
    if truncation_patterns:
        indicators.extend(truncation_patterns)
        confidence += 0.25 * len(truncation_patterns)
        details["truncation_patterns"] = truncation_patterns
    
    # Cap confidence at 1.0
    confidence = min(confidence, 1.0)
    
    # Determine if truncated based on confidence threshold
    threshold = 0.3 if strict_mode else 0.5
    is_truncated = confidence >= threshold
    
    return TruncationResult(
        is_truncated=is_truncated,
        confidence=confidence,
        indicators=indicators,
        details=details
    )


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

