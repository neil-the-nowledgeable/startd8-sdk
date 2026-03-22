"""Exemplar-to-template promotion (Layer 4).

When 3+ level-3 exemplars for a fingerprint share >80% invariant lines,
extracts a deterministic template ($0 cost). Uses line normalization and
LCS computation -- no LLM calls.

Algorithm:
1. Group level-3 exemplars by fingerprint
2. For groups with 3+ members: normalize whitespace + replace identifiers with {param_N}
3. Compute LCS across all normalized versions
4. If LCS >= 80% of average line count -> extract template
5. Only template method/function bodies, not entire files (Ichigo Ichie guard)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["PromotedTemplate", "promote_exemplars_to_templates"]


@dataclass(frozen=True)
class PromotedTemplate:
    """A deterministic code template promoted from exemplars.

    Represents crystallized LLM knowledge from 3+ validated runs.
    Variable positions are marked with {param_0}, {param_1}, etc.
    """

    fingerprint: str  # e.g. "go:source:grpc:grpc_server"
    template_lines: tuple[str, ...]  # invariant lines with {param_N} placeholders
    param_names: tuple[str, ...]  # original identifiers replaced by params
    source_exemplar_ids: tuple[str, ...]  # IDs of exemplars that contributed
    invariant_ratio: float  # fraction of lines that are invariant (0.0-1.0)

    def render(self, substitutions: Dict[str, str] | None = None) -> str:
        """Render the template with parameter substitutions.

        Args:
            substitutions: Mapping from param placeholder to actual value.
                E.g. {"param_0": "MyService", "param_1": "50051"}

        Returns:
            Rendered code string.
        """
        subs = substitutions or {}
        lines: List[str] = []
        for line in self.template_lines:
            rendered = line
            for key, value in subs.items():
                rendered = rendered.replace(f"{{{key}}}", value)
            lines.append(rendered)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Line normalization
# ---------------------------------------------------------------------------

# Patterns for identifier normalization
_IDENTIFIER_PATTERN = re.compile(
    r"\b[A-Z][a-zA-Z0-9]*(?:Service|Server|Client|Handler|Manager|Controller|Factory)\b"
)


def _normalize_line(line: str) -> tuple[str, List[str]]:
    """Normalize a line by replacing domain-specific identifiers with placeholders.

    Returns (normalized_line, list_of_replaced_identifiers).
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return (stripped, [])

    replaced: List[str] = []
    result = stripped

    # Replace service/handler class names
    for match in _IDENTIFIER_PATTERN.finditer(stripped):
        ident = match.group(0)
        if ident not in replaced:
            replaced.append(ident)

    for i, ident in enumerate(replaced):
        result = result.replace(ident, f"{{param_{i}}}")

    # Normalize whitespace
    result = re.sub(r"\s+", " ", result)

    return (result, replaced)


def _normalize_lines(code: str) -> tuple[List[str], List[str]]:
    """Normalize all lines, returning (normalized_lines, all_replaced_identifiers)."""
    all_params: List[str] = []
    normalized: List[str] = []

    for line in code.splitlines():
        norm, params = _normalize_line(line)
        if norm:  # skip blank lines
            normalized.append(norm)
            for p in params:
                if p not in all_params:
                    all_params.append(p)

    return normalized, all_params


# ---------------------------------------------------------------------------
# LCS computation (line-level)
# ---------------------------------------------------------------------------


def _lcs_lines(a: List[str], b: List[str]) -> List[str]:
    """Compute longest common subsequence of two line lists.

    Standard DP approach -- O(n*m) time and space.
    """
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return []

    # Guard against unexpectedly large inputs (O(n×m) DP)
    if n * m > 50_000:
        logger.debug("LCS skipped: %d × %d = %d cells exceeds ceiling", n, m, n * m)
        return []

    # Build DP table
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Backtrack to find LCS
    result: List[str] = []
    i, j = n, m
    while i > 0 and j > 0:
        if a[i - 1] == b[j - 1]:
            result.append(a[i - 1])
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1

    result.reverse()
    return result


def _multi_lcs(sequences: List[List[str]]) -> List[str]:
    """Compute LCS across multiple sequences by pairwise reduction."""
    if not sequences:
        return []
    result = sequences[0]
    for seq in sequences[1:]:
        result = _lcs_lines(result, seq)
        if not result:
            break
    return result


# ---------------------------------------------------------------------------
# Promotion logic
# ---------------------------------------------------------------------------

_INVARIANT_THRESHOLD = 0.80  # 80% of average line count
_MIN_EXEMPLARS = 3


def promote_exemplars_to_templates(
    exemplars: Sequence,
    threshold: float = _INVARIANT_THRESHOLD,
    min_exemplars: int = _MIN_EXEMPLARS,
) -> List[PromotedTemplate]:
    """Promote groups of level-3 exemplars to templates.

    Groups exemplars by fingerprint, normalizes their code, computes
    multi-way LCS, and promotes groups where the LCS covers >= threshold
    of average line count.

    Args:
        exemplars: All exemplars (will be filtered to level-3).
        threshold: Minimum invariant line ratio (default 0.80).
        min_exemplars: Minimum exemplars per fingerprint (default 3).

    Returns:
        List of promoted templates.
    """
    # Group level-3 exemplars by fingerprint
    by_fp: Dict[str, List[Any]] = {}
    for e in exemplars:
        if e.maturity == 3 and e.code_summary:
            key = str(e.fingerprint)
            by_fp.setdefault(key, []).append(e)

    templates: List[PromotedTemplate] = []

    for fp_str, entries in by_fp.items():
        if len(entries) < min_exemplars:
            continue

        # Normalize all code summaries
        normalized_sets: List[List[str]] = []
        all_params: List[str] = []

        for entry in entries:
            norm_lines, params = _normalize_lines(entry.code_summary)
            normalized_sets.append(norm_lines)
            for p in params:
                if p not in all_params:
                    all_params.append(p)

        if not normalized_sets:
            continue

        # Compute multi-way LCS
        lcs = _multi_lcs(normalized_sets)

        # Check threshold against average line count
        avg_lines = sum(len(ns) for ns in normalized_sets) / len(normalized_sets)
        if avg_lines == 0:
            continue

        ratio = len(lcs) / avg_lines

        if ratio < threshold:
            logger.debug(
                "Fingerprint %s: LCS ratio %.2f < %.2f threshold (%d lines / %.1f avg), skipping",
                fp_str,
                ratio,
                threshold,
                len(lcs),
                avg_lines,
            )
            continue

        template = PromotedTemplate(
            fingerprint=fp_str,
            template_lines=tuple(lcs),
            param_names=tuple(all_params),
            source_exemplar_ids=tuple(e.id for e in entries),
            invariant_ratio=ratio,
        )
        templates.append(template)

        logger.info(
            "Promoted template for %s: %d invariant lines (%.0f%%), %d params, from %d exemplars",
            fp_str,
            len(lcs),
            ratio * 100,
            len(all_params),
            len(entries),
        )

    return templates
