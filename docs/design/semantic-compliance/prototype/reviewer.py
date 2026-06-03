"""PROTOTYPE — the tiered agent reviewer (heart of the SCR).

NOT SHIPPED CODE. Intended shape of `src/startd8/semantic_compliance/reviewer.py`. The control
flow is sketched concretely (it's the load-bearing part); the two boundaries left as TODO are
(a) the actual agent call and (b) the rubric text (see prompts/review_rubric.md).

Tiered escalation (FR-15 / R4-S2): cheap Haiku review on every flagged feature; escalate to
Sonnet ONLY on `fail`/low-confidence; Sonnet is terminal. Deterministic decoding (R2-S5),
bounded output (R3-S4), parse-failure → one retry → inconclusive (R1-S7), provider 429/529 →
bounded backoff → inconclusive (R4-S1 scoped).
"""

from __future__ import annotations

from typing import Optional

from .models import (
    InconclusiveReason,
    ReportConfig,
    Tier,
    Verdict,
    VerdictResult,
)

# In the shipped module these come from the SDK:
#   from ..providers import ProviderRegistry, resolve_agent_spec
#   from ..micro_prime.models import validate_semantic_verification_json, SemanticVerificationResult
#   from ..model_catalog import Models


class SemanticReviewer:
    def __init__(self, config: ReportConfig) -> None:
        self.config = config

    def review(self, element_fqn: str, payload: dict) -> VerdictResult:
        """Cheap pass, then conditional escalation. Returns a VerdictResult (the persisted shape)."""
        cheap = self._one_pass(self.config.model_cheap, Tier.CHEAP, element_fqn, payload)

        # Escalate only when the cheap tier is unsure or says fail — the cost lever (FR-15).
        needs_escalation = cheap.verdict == Verdict.FAIL or cheap.confidence < (self.config.theta or 0.7)
        if not needs_escalation:
            return cheap

        sonnet = self._one_pass(self.config.model_escalation, Tier.ESCALATED, element_fqn, payload)
        return sonnet  # Sonnet is terminal — no further escalation (R4-S2)

    # -- single tier pass ----------------------------------------------------

    def _one_pass(self, model_spec: str, tier: Tier, element_fqn: str, payload: dict) -> VerdictResult:
        prompt = self._build_prompt(payload)  # rubric + delimited untrusted content (R1-S8)
        raw = self._call_agent(model_spec, prompt)  # deterministic, max_tokens-bounded
        if raw is None:
            # provider outage after bounded backoff (R4-S1 scoped) → inconclusive, never crash
            return VerdictResult(Verdict.INCONCLUSIVE, 0.0, InconclusiveReason.PARSE_FAILURE)
        return self._parse(raw, element_fqn, retry_with=(model_spec, prompt))

    def _parse(self, raw: str, element_fqn: str, retry_with) -> VerdictResult:
        """Parse via validate_semantic_verification_json (K-7). Malformed → one retry → inconclusive
        (fail-open on format); well-formed but content-invalid → fail (fail-closed on content) — FR-6/R1-S7."""
        # ok, result_or_err = validate_semantic_verification_json(raw, element_fqn)
        # if not ok:
        #     if retry_with: return self._parse(self._call_agent(*retry_with), element_fqn, retry_with=None)
        #     return VerdictResult(Verdict.INCONCLUSIVE, 0.0, InconclusiveReason.PARSE_FAILURE)
        # return VerdictResult(Verdict(result_or_err.verdict), result_or_err.confidence)
        raise NotImplementedError("wire to micro_prime.models.validate_semantic_verification_json")

    def _build_prompt(self, payload: dict) -> str:
        """Render the versioned, language-aware rubric (FR-7); delimit untrusted reviewed content and
        instruct the agent to ignore embedded instructions (anti-injection, R1-S8). See
        prompts/review_rubric.md."""
        raise NotImplementedError

    def _call_agent(self, model_spec: str, prompt: str) -> Optional[str]:
        """resolve_agent_spec(model_spec) → agenerate with temperature=0/seed (R2-S5) and
        max_tokens=config.max_output_tokens (R3-S4); debit the shared CostTracker (R2-S2).
        Returns raw text, or None after bounded backoff on 429/529 (R4-S1 scoped)."""
        raise NotImplementedError
