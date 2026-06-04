"""FR-SAP-7 — Forward Deployed Engineer (FDE) query interface.

The far-side ground-truth crew, modelled here as a **consumer contract** (NR-1: the FDE agent
is not built). The near-side gate routes any assumption it can neither bore nor convention-check
(framework/orm idiom on Python, domain rules, residual module-source) to ``FdeQuery.answer``.

Contract: ``answer(question) -> FdeAnswer`` with verdict ``VALIDATED | REFUTED | OMIT``. ``OMIT``
(the FDE has no ground truth) is operationally distinct from a timeout — the gate maps ``OMIT``
to ``UNRESOLVED(omit/authority_absent)`` and a raised ``FdeTimeout`` to ``UNRESOLVED(bore_degraded)``.

v1 backing: ``ProjectKnowledge`` (negatives/interfaces/field-sets + its first-class ``omissions``);
for Python it is thin, so most answers are ``OMIT`` by design — the honest "we don't know yet"
that pairs with a human/FDE escalation. Answers are cached across runs by question fingerprint.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Protocol, runtime_checkable

from .models import AssumptionKind


class FdeVerdict(str, Enum):
    VALIDATED = "validated"
    REFUTED = "refuted"
    OMIT = "omit"


class FdeTimeout(Exception):
    """Raised when the FDE cannot answer in time (distinct from an explicit OMIT)."""


@dataclass(frozen=True)
class FdeQuestion:
    """Typed question payload (FR-SAP-7)."""

    assumption_id: str
    kind: AssumptionKind
    claim: str
    symbol: str = ""
    module: str = ""

    def fingerprint(self) -> str:
        raw = f"{self.kind.value}\x1f{self.module}\x1f{self.symbol}\x1f{self.claim}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True)
class FdeAnswer:
    """Typed answer payload."""

    verdict: FdeVerdict
    evidence: str = ""
    source: str = ""

    @classmethod
    def omit(cls, evidence: str = "no ground truth") -> "FdeAnswer":
        return cls(FdeVerdict.OMIT, evidence=evidence, source="fde")


@runtime_checkable
class FdeQuery(Protocol):
    """The consumer contract the near-side role depends on."""

    def answer(self, question: FdeQuestion) -> FdeAnswer:  # may raise FdeTimeout
        ...


class NullFde:
    """Always OMITs — the honest default when no project ground truth is wired."""

    def answer(self, question: FdeQuestion) -> FdeAnswer:
        return FdeAnswer.omit("no FDE backing configured")


class ProjectKnowledgeFde:
    """FDE backed by a ``ProjectKnowledge`` artifact (v1 — thin for Python).

    Answers module-source and field-authority questions from the knowledge graph; everything
    else (framework/orm idiom, domain rules) OMITs, since the graph does not encode it today.
    """

    def __init__(self, knowledge) -> None:
        self._k = knowledge
        self._negatives = {n.invented: n for n in getattr(knowledge, "negatives", ()) or ()}
        self._modules = {i.module_path: i for i in getattr(knowledge, "interfaces", ()) or ()}
        self._fields = {fs.entity: set(_field_names(fs)) for fs in getattr(knowledge, "field_sets", ()) or ()}

    def answer(self, question: FdeQuestion) -> FdeAnswer:
        if question.kind is AssumptionKind.MODULE_SOURCE:
            neg = self._negatives.get(question.module) or self._negatives.get(question.symbol)
            if neg is not None:
                return FdeAnswer(
                    FdeVerdict.REFUTED,
                    evidence=f"{neg.invented} → use {neg.correct}" + (f" ({neg.note})" if neg.note else ""),
                    source="project_knowledge.negatives",
                )
            if question.module in self._modules:
                return FdeAnswer(FdeVerdict.VALIDATED, evidence=f"{question.module} is a known interface", source="project_knowledge.interfaces")
            return FdeAnswer.omit(f"no authority for module {question.module!r}")

        if question.kind is AssumptionKind.FIELD_AUTHORITY:
            entity, _, fname = question.symbol.partition(".")
            known = self._fields.get(entity)
            if known is None:
                return FdeAnswer.omit(f"no field authority for entity {entity!r}")
            if fname in known:
                return FdeAnswer(FdeVerdict.VALIDATED, evidence=f"{question.symbol} exists", source="project_knowledge.field_sets")
            return FdeAnswer(
                FdeVerdict.REFUTED,
                evidence=f"{fname!r} not in {entity} fields {sorted(known)}",
                source="project_knowledge.field_sets",
            )

        # Framework/ORM idiom, domain rules: not encoded in the graph for Python → OMIT.
        return FdeAnswer.omit(f"ground truth for {question.kind.value} not encoded")


@dataclass
class CachingFde:
    """Wraps any ``FdeQuery`` with a cross-run cache keyed by question fingerprint (R4-F5)."""

    inner: FdeQuery
    _cache: Dict[str, FdeAnswer] = field(default_factory=dict)

    def answer(self, question: FdeQuestion) -> FdeAnswer:
        key = question.fingerprint()
        if key in self._cache:
            return self._cache[key]
        ans = self.inner.answer(question)
        self._cache[key] = ans
        return ans


def _field_names(field_set) -> list:
    out = []
    for f in getattr(field_set, "fields", ()) or ():
        name = getattr(f, "name", None)
        out.append(name if name is not None else str(f))
    return out
