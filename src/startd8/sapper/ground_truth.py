"""FR-SAP-7 — project **ground-truth oracle** (the far-side ground-truth authority).

The far-side crew Sapper bores toward: it answers "what does THIS project's codebase actually
contain?" (module paths, field sets, invented-vs-canonical names). The near-side gate routes any
assumption it can neither bore nor convention-check (framework/orm idiom, domain rules, residual
module-source) to ``GroundTruthQuery.answer``.

**Authority domain — distinct from the SDK-mechanism FDE in ``startd8.fde``.** That FDE
(``run_fde_explain`` / ``run_fde_preflight``) carries the *SDK's mechanism* authority into a
project — "which tier runs, what model by role, is there a repair step." This oracle carries
*project ground truth*. They are the two Tekizai-Tekisho halves (MECHANISM vs OBSERVED) and
**compose** rather than subsume — see ``sapper.fde_bridge``, which expresses this oracle's
findings as the FDE's OBSERVED ``LabeledClaim``s so the deployed FDE can front the pair.

Contract: ``answer(question) -> GroundTruthAnswer`` with verdict ``VALIDATED | REFUTED | OMIT``.
``OMIT`` (no ground truth) is operationally distinct from a timeout — the gate maps ``OMIT`` to
``UNRESOLVED(omit/authority_absent)`` and a raised ``GroundTruthTimeout`` to
``UNRESOLVED(bore_degraded)``.

v1 backing: ``ProjectKnowledge`` (negatives/interfaces/field-sets + its first-class ``omissions``);
for Python it is thin, so most answers are ``OMIT`` by design — the honest "we don't know yet"
that pairs with a human escalation. Answers are cached across runs by question fingerprint.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Protocol, runtime_checkable

from .models import AssumptionKind


class GroundTruthVerdict(str, Enum):
    VALIDATED = "validated"
    REFUTED = "refuted"
    OMIT = "omit"


class GroundTruthTimeout(Exception):
    """Raised when the FDE cannot answer in time (distinct from an explicit OMIT)."""


@dataclass(frozen=True)
class GroundTruthQuestion:
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
class GroundTruthAnswer:
    """Typed answer payload."""

    verdict: GroundTruthVerdict
    evidence: str = ""
    source: str = ""

    @classmethod
    def omit(cls, evidence: str = "no ground truth") -> "GroundTruthAnswer":
        return cls(GroundTruthVerdict.OMIT, evidence=evidence, source="fde")


@runtime_checkable
class GroundTruthQuery(Protocol):
    """The consumer contract the near-side role depends on."""

    def answer(self, question: GroundTruthQuestion) -> GroundTruthAnswer:  # may raise GroundTruthTimeout
        ...


class NullOracle:
    """Always OMITs — the honest default when no project ground truth is wired."""

    def answer(self, question: GroundTruthQuestion) -> GroundTruthAnswer:
        return GroundTruthAnswer.omit("no FDE backing configured")


class ProjectKnowledgeOracle:
    """FDE backed by a ``ProjectKnowledge`` artifact (v1 — thin for Python).

    Answers module-source and field-authority questions from the knowledge graph; everything
    else (framework/orm idiom, domain rules) OMITs, since the graph does not encode it today.
    """

    def __init__(self, knowledge) -> None:
        self._k = knowledge
        self._negatives = {n.invented: n for n in getattr(knowledge, "negatives", ()) or ()}
        self._modules = {i.module_path: i for i in getattr(knowledge, "interfaces", ()) or ()}
        self._fields = {fs.entity: set(_field_names(fs)) for fs in getattr(knowledge, "field_sets", ()) or ()}

    def answer(self, question: GroundTruthQuestion) -> GroundTruthAnswer:
        if question.kind is AssumptionKind.MODULE_SOURCE:
            neg = self._negatives.get(question.module) or self._negatives.get(question.symbol)
            if neg is not None:
                return GroundTruthAnswer(
                    GroundTruthVerdict.REFUTED,
                    evidence=f"{neg.invented} → use {neg.correct}" + (f" ({neg.note})" if neg.note else ""),
                    source="project_knowledge.negatives",
                )
            if question.module in self._modules:
                return GroundTruthAnswer(GroundTruthVerdict.VALIDATED, evidence=f"{question.module} is a known interface", source="project_knowledge.interfaces")
            return GroundTruthAnswer.omit(f"no authority for module {question.module!r}")

        if question.kind is AssumptionKind.FIELD_AUTHORITY:
            entity, _, fname = question.symbol.partition(".")
            known = self._fields.get(entity)
            if known is None:
                return GroundTruthAnswer.omit(f"no field authority for entity {entity!r}")
            if fname in known:
                return GroundTruthAnswer(GroundTruthVerdict.VALIDATED, evidence=f"{question.symbol} exists", source="project_knowledge.field_sets")
            return GroundTruthAnswer(
                GroundTruthVerdict.REFUTED,
                evidence=f"{fname!r} not in {entity} fields {sorted(known)}",
                source="project_knowledge.field_sets",
            )

        # Framework/ORM idiom, domain rules: not encoded in the graph for Python → OMIT.
        return GroundTruthAnswer.omit(f"ground truth for {question.kind.value} not encoded")


@dataclass
class CachingOracle:
    """Wraps any ``GroundTruthQuery`` with a cross-run cache keyed by question fingerprint (R4-F5)."""

    inner: GroundTruthQuery
    _cache: Dict[str, GroundTruthAnswer] = field(default_factory=dict)

    def answer(self, question: GroundTruthQuestion) -> GroundTruthAnswer:
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


# Files the ProjectKnowledge producer actually reads (Prisma schema + TS/JS interfaces).
_GROUND_TRUTH_GLOBS = ("**/*.prisma", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx")
_GT_IGNORE_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".next", "build", "dist"}


def oracle_for_project(project_root: str, *, max_files: int = 500) -> "FdeQueryLike":
    """Build a project ground-truth oracle from a target project (FR-SAP-7 wiring, Item 4a).

    Scans the project for the sources the ``ProjectKnowledge`` producer reads, builds the graph,
    and wraps it in a cached ``ProjectKnowledgeOracle``. Falls back to ``NullOracle`` on any
    failure or when nothing relevant is found.

    NB (honest): the producer is Prisma/TS-only today, so for a pure-Python project this yields a
    graph of mostly *omissions* and the oracle will ``OMIT`` — the wiring is real, the payoff waits
    on a Python ground-truth authority (the FR-CAR-0 / FR-MPF-1 track).
    """
    from pathlib import Path

    root = Path(project_root)
    if not root.is_dir():
        return NullOracle()
    try:
        sources: Dict[str, str] = {}
        for pattern in _GROUND_TRUTH_GLOBS:
            for fp in root.glob(pattern):
                if len(sources) >= max_files:
                    break
                if any(part in _GT_IGNORE_DIRS for part in fp.parts):
                    continue
                try:
                    sources[str(fp.relative_to(root))] = fp.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
        from startd8.contractors.project_knowledge.producer import DraftModeProducer

        pk = DraftModeProducer().build(sources, str(root))
        return CachingOracle(ProjectKnowledgeOracle(pk))
    except Exception:  # never let oracle construction break the survey
        return NullOracle()


# Structural alias for the protocol (avoids importing Protocol at call sites).
FdeQueryLike = GroundTruthQuery
