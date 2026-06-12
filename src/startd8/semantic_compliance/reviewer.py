# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Tiered agent reviewer — the heart of the SCR (FR-6/7/15).

Cheap Haiku pass on every flagged feature; escalate to Sonnet ONLY on ``fail``/low-confidence;
Sonnet is terminal (R4-S2). Deterministic decoding (R2-S5) + bounded output (R3-S4). Parse failure
→ one retry → ``inconclusive`` (fail-open on format, R1-S7). Non-Python → ``inconclusive``
(language_unsupported, R2-S1). The first producer of ``SemanticVerificationResult`` (K-7).

An ``agent_factory`` seam keeps this testable without API keys and lets the same code be hoisted
into the in-run ``MicroPrimeConfig.semantic_verification_*`` hook later (FR-13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..logging_config import get_logger
from ..micro_prime.models import validate_semantic_verification_json
from .models import (
    InconclusiveReason,
    ReportConfig,
    Tier,
    Verdict,
    VerdictResult,
    VerificationIssue,
)
from .prompts import render_rubric
from .requirement_loader import LoadedRequirement

logger = get_logger(__name__)

# spec -> agent with a `.generate(prompt, **kwargs) -> result-with-.text`
AgentFactory = Callable[[str], object]

_CHARS_PER_TOKEN = 4  # rough budget conversion for input truncation (R3-S1)


@dataclass
class ReviewOutcome:
    verdict: VerdictResult
    issues: List[VerificationIssue] = field(default_factory=list)
    tier: Tier = Tier.CHEAP
    truncated: bool = False


def _default_agent_factory(spec: str) -> object:
    from ..utils.agent_resolution import resolve_agent_spec

    return resolve_agent_spec(spec, name="scr-reviewer")


def contract_bindings_for_feature(
    contracts: Optional[List[object]],
    feature_id: Optional[str],
) -> List[str]:
    """``InterfaceContract.binding_text`` for the feature's api-sig-derived contracts (E2).

    The structured authority the rubric validates against (FR-CL-2): the extractor
    already turned ``api_signatures`` into contracts with a ``binding_text``; reading
    those removes the reviewer's reliance on the raw prose. Scoped to the feature via
    ``applicable_task_ids`` (empty = project-wide). Returns ``[]`` when no manifest is
    available so the caller degrades to the api_signatures prose.
    """
    bindings: List[str] = []
    for c in contracts or []:
        if getattr(c, "source_reference", None) != "deterministic":
            continue
        applicable = getattr(c, "applicable_task_ids", None) or []
        if applicable and feature_id is not None and feature_id not in applicable:
            continue
        text = getattr(c, "binding_text", None)
        if text and text not in bindings:
            bindings.append(text)
    return bindings


class SemanticReviewer:
    def __init__(self, config: ReportConfig, agent_factory: Optional[AgentFactory] = None) -> None:
        self.config = config
        self._factory = agent_factory or _default_agent_factory

    def review(
        self,
        loaded: LoadedRequirement,
        generated_code: str,
        element_fqn: str,
        contract_bindings: Optional[List[str]] = None,
    ) -> ReviewOutcome:
        if (loaded.language or "python").lower() != "python":
            # v1 is Python-only — never mis-verdict another language (R2-S1).
            return ReviewOutcome(
                VerdictResult(Verdict.INCONCLUSIVE, 0.0, InconclusiveReason.LANGUAGE_UNSUPPORTED)
            )

        code, truncated = self._bound_input(generated_code)
        cheap = self._one_pass(
            self.config.model_cheap, Tier.CHEAP, loaded, code, element_fqn, contract_bindings,
        )
        cheap.truncated = truncated

        theta = self.config.theta or 0.7
        needs_escalation = cheap.verdict.verdict == Verdict.FAIL or cheap.verdict.confidence < theta
        if not needs_escalation or cheap.verdict.inconclusive_reason is not None:
            return cheap

        sonnet = self._one_pass(
            self.config.model_escalation, Tier.ESCALATED, loaded, code, element_fqn, contract_bindings,
        )
        sonnet.truncated = truncated
        return sonnet  # Sonnet is terminal — no further escalation (R4-S2)

    # -- internals -----------------------------------------------------------

    def _bound_input(self, code: str) -> tuple[str, bool]:
        budget = self.config.max_input_tokens * _CHARS_PER_TOKEN
        if len(code) <= budget:
            return code, False
        return code[:budget] + "\n... [truncated] ...", True

    def _one_pass(
        self,
        model_spec: str,
        tier: Tier,
        loaded: LoadedRequirement,
        code: str,
        element_fqn: str,
        contract_bindings: Optional[List[str]] = None,
    ) -> ReviewOutcome:
        prompt = render_rubric(
            feature_id=loaded.feature_id,
            element_fqn=element_fqn,
            language=loaded.language,
            seed_task_id=loaded.feature_id,
            requirement_text=loaded.requirement_text,
            api_signatures=loaded.api_signatures,
            negative_scope=loaded.negative_scope,
            generated_code=code,
            contract_bindings=contract_bindings,
        )
        raw = self._call(model_spec, prompt)
        if raw is None:
            return ReviewOutcome(
                VerdictResult(Verdict.INCONCLUSIVE, 0.0, InconclusiveReason.PARSE_FAILURE), tier=tier
            )

        outcome = self._parse(raw, element_fqn, tier)
        if outcome is None:  # malformed → one retry (fail-open on format, R1-S7)
            raw2 = self._call(model_spec, prompt)
            outcome = self._parse(raw2, element_fqn, tier) if raw2 else None
        if outcome is None:
            return ReviewOutcome(
                VerdictResult(Verdict.INCONCLUSIVE, 0.0, InconclusiveReason.PARSE_FAILURE), tier=tier
            )
        return outcome

    def _parse(self, raw: str, element_fqn: str, tier: Tier) -> Optional[ReviewOutcome]:
        ok, result_or_err = validate_semantic_verification_json(raw, element_fqn)
        if not ok:
            logger.debug("SCR parse miss (%s): %s", tier.value, result_or_err)
            return None
        svr = result_or_err
        issues = [
            VerificationIssue(i.severity, i.category, i.description, i.line_hint, i.suggested_fix)
            for i in svr.issues
        ]
        return ReviewOutcome(
            VerdictResult(Verdict(svr.verdict), svr.confidence), issues=issues, tier=tier
        )

    def _call(self, model_spec: str, prompt: str) -> Optional[str]:
        """Resolve the agent and generate; deterministic + bounded. Returns raw text or None.

        Provider/transport failures degrade to None (→ inconclusive); they never crash the run
        (R4-S1 scoped — bounded backoff/fallback is a follow-up).
        """
        kwargs = {"max_tokens": self.config.max_output_tokens}
        if self.config.deterministic:
            kwargs["temperature"] = 0.0
        try:
            agent = self._factory(model_spec)
            result = agent.generate(prompt, **kwargs)
            return getattr(result, "text", None) or (result if isinstance(result, str) else None)
        except Exception as exc:  # pragma: no cover - exercised via injected factory in tests
            logger.warning("SCR agent call failed (%s): %s", model_spec, exc)
            return None
