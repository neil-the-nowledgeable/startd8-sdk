"""Round-3 layered scoring (M3) — turn an Adapter-B JourneyResult into the system scorecard with
honest per-service fault attribution.

The headline is **per-step coverage** (weighted by the §1 locust mix + unweighted), already on
``JourneyResult``. M3 adds:
  * **per-service fault attribution** — each failed step names a culprit service; the scorer classifies
    it as ``model-fault`` (the service's own code is broken), ``propagated`` (the entry service of an
    orchestrated step failed because a downstream dep is broken — the entry is NOT charged), or
    ``harness`` (no culprit identified). A downstream break is NEVER charged as the entry service's
    model-fault: break payment → payment is model-fault, checkoutservice is propagated.
  * **canonical-journey-completed** boolean (FR-13) — did the checkout step pass.
  * **confidence** (FR-22) — ``low`` when EVERY step failed (no healthy baseline to attribute against,
    an all-degrade run), else ``high``.

Pure function of a ``JourneyResult`` (+ the journey spec) — no transport — so it is unit-testable
against synthetic results (healthy / break-payment / break-catalog) with no live fleet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import journey as J
from .adapter_b import JourneyResult

# attribution classes
MODEL_FAULT = "model-fault"   # the service's own code failed (its RPC errored / its response was wrong)
PROPAGATED = "propagated"     # the orchestrated entry service failed because a downstream dep broke
HARNESS = "harness"           # a failed step with no identified culprit (treat as harness, not a model)


@dataclass
class ServiceFault:
    service: str
    classification: str           # MODEL_FAULT | PROPAGATED | HARNESS
    step: str                     # the journey step that surfaced it
    via: Optional[str] = None     # for PROPAGATED on the entry service: the downstream dep that broke
    detail: str = ""


@dataclass
class Scorecard:
    unweighted_coverage: float
    weighted_coverage: float
    journey_completed: bool
    confidence: str               # "high" | "low"
    faults: list[ServiceFault] = field(default_factory=list)

    @property
    def model_faulted_services(self) -> set[str]:
        """Services whose OWN code is the fault (the ones a model is charged for)."""
        return {f.service for f in self.faults if f.classification == MODEL_FAULT}

    @property
    def propagated_services(self) -> set[str]:
        """Entry services that failed only because a downstream dep broke (exonerated)."""
        return {f.service for f in self.faults if f.classification == PROPAGATED}

    def to_dict(self) -> dict:
        return {
            "unweighted_coverage": self.unweighted_coverage,
            "weighted_coverage": self.weighted_coverage,
            "journey_completed": self.journey_completed,
            "confidence": self.confidence,
            "faults": [{"service": f.service, "classification": f.classification, "step": f.step,
                        "via": f.via, "detail": f.detail} for f in self.faults],
            "model_faulted_services": sorted(self.model_faulted_services),
        }


def score_journey(result: JourneyResult) -> Scorecard:
    """Classify each failed step's culprit and assemble the system scorecard."""
    faults: list[ServiceFault] = []
    for step in result.steps:
        if step.passed:
            continue
        spec = J.JOURNEY_BY_NAME.get(step.name)
        culprit = step.culprit
        if culprit is None:
            faults.append(ServiceFault(step.name, HARNESS, step.name, detail=step.detail))
            continue
        entry = spec.services[0] if spec else None
        if spec and spec.orchestrated and culprit != entry:
            # A downstream dep broke the orchestrator → the dep is model-fault, the entry is propagated
            # (exonerated). This is the "downstream never charged for an upstream break" rule.
            faults.append(ServiceFault(culprit, MODEL_FAULT, step.name, detail=step.detail))
            faults.append(ServiceFault(entry, PROPAGATED, step.name, via=culprit, detail=step.detail))
        else:
            # Direct step, or the orchestrator's own logic failed → the culprit's own code is at fault.
            faults.append(ServiceFault(culprit, MODEL_FAULT, step.name, detail=step.detail))

    # Dedup: a service model-faulted in several steps appears once (model-fault wins over propagated).
    deduped = _dedup_faults(faults)

    journey_completed = J.JOURNEY_BY_NAME["checkout"].name not in result.failed_steps
    all_failed = bool(result.steps) and all(not s.passed for s in result.steps)
    return Scorecard(
        unweighted_coverage=result.unweighted_coverage,
        weighted_coverage=result.weighted_coverage,
        journey_completed=journey_completed,
        confidence="low" if all_failed else "high",
        faults=deduped,
    )


def _dedup_faults(faults: list[ServiceFault]) -> list[ServiceFault]:
    """One verdict per service: model-fault dominates propagated (a service truly broken in one step is
    model-fault even if it's only propagated-through in another). Keep the first occurrence's step."""
    model = {f.service for f in faults if f.classification == MODEL_FAULT}
    out: list[ServiceFault] = []
    seen: set[str] = set()
    for f in faults:
        if f.service in seen:
            continue
        if f.classification == PROPAGATED and f.service in model:
            continue  # the service is genuinely model-faulted elsewhere — drop the propagated verdict
        out.append(f)
        seen.add(f.service)
    return out
