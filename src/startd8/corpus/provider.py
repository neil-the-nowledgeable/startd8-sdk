"""Corpus-driven deterministic provider (DETERMINISTIC_PROVIDER_REQUIREMENTS, prototype).

For a file the Controlled Corpus oracle proves deterministic-ready, emit proven content with
NO LLM call; fall through (return None) for everything else. Purely additive — it can only
*skip* the LLM for proven files, never block generation.

Safety (FR-1): NEVER routes `false_pass_risk` (or any unproven class). Content comes from a
pluggable resolver (FR-2) so exemplar / golden / cache backends compose. v1 emits content
verbatim (NR-1) and validates it structurally before accepting (FR-5).

This module is standalone (not yet wired into the live drafter — FR-7 is phased). It proves
the route→emit→fall-through mechanism; live wiring is gated on the validation run.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from startd8.corpus.registry import ControlledCorpusRegistry
from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["RouteDecision", "ProviderResult", "DeterministicCorpusProvider",
           "dict_content_resolver"]

# A resolver maps a target_file -> proven content (or None if unavailable).
ContentResolver = Callable[[str], Optional[str]]
# A validator returns True if content is structurally acceptable for the target_file.
ContentValidator = Callable[[str, str], bool]

_DEFAULT_MIN_MATURITY = 3  # L3 "stable" (OQ-1)


@dataclass
class RouteDecision:
    target_file: str
    eligible: bool
    reason: str
    term_id: Optional[str] = None
    corpus_class: Optional[str] = None
    maturity: Optional[int] = None


@dataclass
class ProviderResult:
    target_file: str
    content: str
    term_id: Optional[str]
    fill_source: str = "corpus_deterministic"  # FR-6 provenance


class DeterministicCorpusProvider:
    """Routes corpus-proven files to deterministic content; LLM fall-through otherwise."""

    def __init__(
        self,
        corpus: ControlledCorpusRegistry,
        content_resolver: ContentResolver,
        *,
        min_maturity: int = _DEFAULT_MIN_MATURITY,
        validator: Optional[ContentValidator] = None,
    ) -> None:
        self._corpus = corpus
        self._resolve = content_resolver
        self._min_maturity = min_maturity
        self._validator = validator

    # ---- routing decision (FR-1) ----
    def route(self, target_file: str) -> RouteDecision:
        term = self._corpus.find_by_canonical_key("file", target_file)
        if term is None:
            return RouteDecision(target_file, False, "not_in_corpus")
        cls = term.determinism.corpus_class
        m = term.maturity
        # NEVER route a false-PASS — the load-bearing guardrail (FR-1 / FR-8 corpus invariant).
        if cls == "false_pass_risk":
            return RouteDecision(target_file, False, "refused:false_pass_risk", term.term_id, cls, m)
        if cls != "deterministic_candidate":
            return RouteDecision(target_file, False, f"ineligible:{cls}", term.term_id, cls, m)
        if m < self._min_maturity:
            return RouteDecision(target_file, False, f"ineligible:maturity<{self._min_maturity}",
                                 term.term_id, cls, m)
        return RouteDecision(target_file, True, "deterministic_candidate", term.term_id, cls, m)

    # ---- emission (FR-3/4/5) ----
    def generate(self, target_file: str) -> Optional[ProviderResult]:
        """Return proven content (no LLM) if eligible + resolvable + valid; else None (→ LLM)."""
        decision = self.route(target_file)
        if not decision.eligible:
            return None
        content = self._resolve(target_file)
        if content is None:
            logger.debug("corpus-deterministic: eligible but no content for %s — LLM fallthrough",
                         target_file)
            return None
        if self._validator is not None and not self._validator(target_file, content):
            logger.warning("corpus-deterministic: content for %s failed validation — LLM fallthrough",
                           target_file)
            return None
        logger.info("corpus-deterministic: served %s from proven content ($0, no LLM)", target_file)
        return ProviderResult(target_file, content, decision.term_id)


def dict_content_resolver(mapping: dict) -> ContentResolver:
    """Simple resolver backed by a {target_file: content} dict (tests / golden cache)."""
    return lambda tf: mapping.get(tf)
