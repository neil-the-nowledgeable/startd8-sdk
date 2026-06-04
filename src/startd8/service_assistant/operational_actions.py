"""Operator-facing remediation mapping for the Service Assistant (FR-10).

This layer is intentionally distinct from two existing mappings:

* ``CAUSE_TO_SUGGESTION`` (``contractors/prime_postmortem.py``) produces *prompt hints*
  for the **next generation attempt** — it speaks to the LLM, not the operator.
* ``repair/routing.py`` produces deterministic **code transforms** — it fixes bytes,
  it does not recommend a strategy.

``CAUSE_TO_OPERATIONAL_ACTION`` answers the operator's question: *"this run failed —
what should I do about it?"* Each entry maps a :class:`RootCause` to a severity, a
controlled ``re_run_strategy`` token, and a human-readable action sentence.

Coverage is **exhaustive** over the 19 ``RootCause`` members (OQ-9); any future enum
addition that is not mapped falls through to :data:`FALLBACK_ACTION` and is caught by
``test_operational_action_coverage`` so it can never ship silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from ..contractors.prime_postmortem import RootCause


# Controlled vocabulary for re_run_strategy (see SERVICE_ASSISTANT_TRIAGE_SCHEMA.md §1).
RE_RUN_STRATEGIES = frozenset(
    {
        "retry_as_is",
        "reduce_scope",
        "split_element_or_increase_tier",
        "re_run_prior_stage",
        "from_latest_producer",
        "unblock_dependency",
        "regenerate_clean",
        "fix_repair_routing",
        "fix_deterministic_generator",
        "align_types",
        "manual_review",
    }
)

DETERMINISTIC_STRATEGY = "fix_deterministic_generator"

SEVERITIES = frozenset({"critical", "high", "medium", "low"})


@dataclass(frozen=True)
class OperationalAction:
    """An operator-facing recommendation for a classified failure.

    ``actionable`` is the skip-filter (Coyote prior art): when ``False`` the cause is
    environmental/transient (infra health, a transient empty response) and there is no
    code/spec change for the operator to make — the triage still records it, but the
    summary will not elevate it above a genuinely actionable failure.
    """

    severity: str
    re_run_strategy: str
    action: str
    actionable: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {
            "severity": self.severity,
            "re_run_strategy": self.re_run_strategy,
            "action": self.action,
            "actionable": self.actionable,
        }


# Exhaustive mapping over all RootCause members (18 concrete + UNKNOWN).
CAUSE_TO_OPERATIONAL_ACTION: Dict[RootCause, OperationalAction] = {
    RootCause.SKELETON_MISSING: OperationalAction(
        "critical",
        "re_run_prior_stage",
        "Re-run plan-ingestion/skeleton generation — the scaffold for this feature was never produced.",
    ),
    RootCause.CROSS_FILE_CONTRACT: OperationalAction(
        "critical",
        "from_latest_producer",
        "Re-run from the feature that owns the contract; re-sync its exported schema before the consumer.",
    ),
    RootCause.SCOPE_CORRUPTION: OperationalAction(
        "critical",
        "regenerate_clean",
        "Force a clean regeneration — generated scope leaked/corrupted across element boundaries.",
    ),
    RootCause.DEPENDENCY_BLOCKED: OperationalAction(
        "high",
        "unblock_dependency",
        "Resolve the upstream feature first; this one cannot generate until its dependency passes.",
    ),
    RootCause.UNFILLED_STUB: OperationalAction(
        "high",
        "regenerate_clean",
        "Regenerate — the element was left as an unfilled stub; check the draft prompt budget.",
    ),
    RootCause.AST_FAILURE: OperationalAction(
        "high",
        "regenerate_clean",
        "Regenerate — output failed to parse; if it recurs, reduce element scope.",
    ),
    RootCause.SPLICER_MISMATCH: OperationalAction(
        "high",
        "regenerate_clean",
        "Regenerate the element — splicer could not place the body; verify the target signature.",
    ),
    RootCause.REPAIR_EXHAUSTED: OperationalAction(
        "high",
        "fix_repair_routing",
        "Inspect repair routing — automatic repair ran out of attempts; the failure class may be misrouted.",
    ),
    RootCause.REPAIR_LANGUAGE_MISMATCH: OperationalAction(
        "high",
        "fix_repair_routing",
        "Fix repair routing — a repair step for the wrong language was applied; check resolve_language().",
    ),
    RootCause.TYPE_CLASS_MISMATCH: OperationalAction(
        "high",
        "align_types",
        "Re-run with the consumer's types pinned — generated values don't match their consumers.",
    ),
    RootCause.OLLAMA_CIRCUIT_BREAKER: OperationalAction(
        "high",
        "retry_as_is",
        "Check Ollama availability/health, then re-run — the circuit breaker tripped on the local model.",
        actionable=False,  # environmental (local model health), not a code/spec fix
    ),
    RootCause.PHANTOM_IMPORT: OperationalAction(
        "medium",
        "regenerate_clean",
        "Regenerate — code imports a module that doesn't exist; constrain imports to real modules.",
    ),
    RootCause.DUPLICATE_IMPORT: OperationalAction(
        "medium",
        "regenerate_clean",
        "Regenerate — duplicate imports detected; dedupe on the next pass.",
    ),
    RootCause.TIER_ESCALATION: OperationalAction(
        "medium",
        "split_element_or_increase_tier",
        "Decompose the element or raise its tier — it escalated past the cheap tier unresolved.",
    ),
    RootCause.SIZE_REGRESSION: OperationalAction(
        "medium",
        "reduce_scope",
        "Reduce element scope (fewer lines/generation) — output shrank vs. the expected size.",
    ),
    RootCause.OLLAMA_TIMEOUT: OperationalAction(
        "medium",
        "reduce_scope",
        "Reduce element scope and/or check Ollama latency, then re-run — generation timed out.",
    ),
    RootCause.OLLAMA_EMPTY_RESPONSE: OperationalAction(
        "medium",
        "retry_as_is",
        "Re-run — the local model returned empty; if persistent, fall back to a hosted tier.",
        actionable=False,  # transient model output, resolves on retry
    ),
    RootCause.GENERATION_ERROR: OperationalAction(
        "medium",
        "retry_as_is",
        "Re-run — a transient generation error occurred; escalate to manual review if it persists.",
        actionable=False,  # transient, resolves on retry
    ),
    RootCause.UNKNOWN: OperationalAction(
        "low",
        "manual_review",
        "Manual review — the failure did not match a known root cause.",
    ),
}


FALLBACK_ACTION = OperationalAction(
    "low",
    "manual_review",
    "Manual review — unmapped root cause; update CAUSE_TO_OPERATIONAL_ACTION.",
)


def apply_cost_overlay(
    op: OperationalAction,
    root_cause: RootCause | str,
    cost_usd: float | None,
) -> tuple[OperationalAction, bool]:
    """FR-14 — cost-aware remediation. When a failed feature had **zero generation cost**, a plain
    re-run is idempotent (the $0 deterministic path reproduces the identical defect), so recommend
    **fixing the deterministic generator/template** instead of regenerating.

    Returns ``(action, deterministic)``. A non-zero / unknown cost returns the action unchanged.
    """
    if cost_usd is None or cost_usd > 0:
        return op, False
    rc = root_cause.value if isinstance(root_cause, RootCause) else str(root_cause)
    if rc == RootCause.DUPLICATE_IMPORT.value:
        action = (
            "Fix the deterministic generator/splicer — a re-run reproduces the same F811 "
            "collision; remove EITHER the import OR the local redefinition of the colliding name."
        )
    else:
        action = (
            f"Fix the deterministic generator/splicer/template (or escalate this element off the "
            f"$0 deterministic path) — a plain re-run is idempotent and will reproduce '{rc}'."
        )
    return OperationalAction(op.severity, DETERMINISTIC_STRATEGY, action, actionable=True), True


def resolve_operational_action(root_cause: RootCause | str) -> OperationalAction:
    """Return the operator recommendation for a root cause.

    Accepts either a :class:`RootCause` member or its string value (as read from
    ``prime-postmortem-report.json``). Unmapped/unknown values resolve to
    :data:`FALLBACK_ACTION` rather than raising — a wrong recommendation is recoverable,
    a crash in the post-run hook is not.
    """
    if isinstance(root_cause, str):
        try:
            root_cause = RootCause(root_cause)
        except ValueError:
            return FALLBACK_ACTION
    return CAUSE_TO_OPERATIONAL_ACTION.get(root_cause, FALLBACK_ACTION)
