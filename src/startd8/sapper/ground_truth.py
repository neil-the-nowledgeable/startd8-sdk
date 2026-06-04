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
from pathlib import Path
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


_CORPUS_KINDS = ("entity", "service", "rpc", "message", "class")


class ControlledCorpusOracle:
    """Ground-truth backing from the **Controlled Corpus** (FR-SAP-7, v0.8).

    The SDK's first-class store of canonical domain terms (services/RPCs/entities/metrics),
    bootstrapped from the online-boutique microservices demo. Language-agnostic — it answers
    "is this entity/term canonical?" for *any* project that has a corpus, closing the oracle's
    Python/polyglot OMIT gap without waiting on a Python schema authority.

    `VALIDATED` when the referenced symbol is a canonical term; `REFUTED` on a close near-miss
    (an invented term that resembles a real one — e.g. ``Match`` near ``Matches``); else `OMIT`
    (conservative — absence alone is not refutation, since the corpus may be incomplete).
    """

    def __init__(self, registry) -> None:
        self._registry = registry
        self._surfaces: list = []  # all known canonical surface forms (for near-miss)
        for t in registry.terms:
            self._surfaces.extend(t.surface_forms or [t.canonical_key])

    def answer(self, question) -> GroundTruthAnswer:
        sym = (question.symbol or question.module or "").split(".")[-1].strip()
        if not sym:
            return GroundTruthAnswer.omit("no symbol to resolve against the corpus")
        from startd8.corpus.canonical import canonical_key

        for kind in _CORPUS_KINDS:
            term = self._registry.find_by_canonical_key(kind, canonical_key(kind, surface_form=sym))
            if term is not None:
                return GroundTruthAnswer(
                    GroundTruthVerdict.VALIDATED,
                    evidence=f"'{sym}' is a canonical {kind} (maturity L{term.maturity})",
                    source="controlled_corpus",
                )
        near = self._closest(sym)
        if near is not None:
            return GroundTruthAnswer(
                GroundTruthVerdict.REFUTED,
                evidence=f"'{sym}' is not a canonical corpus term; closest is '{near}'",
                source="controlled_corpus",
            )
        return GroundTruthAnswer.omit(f"'{sym}' not in the controlled corpus")

    def _closest(self, sym: str):
        import difflib

        m = difflib.get_close_matches(sym, self._surfaces, n=1, cutoff=0.8)
        return m[0] if (m and m[0] != sym) else None


@dataclass
class CompositeOracle:
    """Composes ground-truth backings: tried in order, the first non-``OMIT`` answer wins.

    Order matters: the Controlled Corpus (broad domain-term authority) is consulted before
    ``ProjectKnowledge`` (narrow schema/field authority), so an entity question resolves against
    the corpus and a field question falls through to the schema. A backing that raises is skipped.
    """

    oracles: list

    def answer(self, question) -> GroundTruthAnswer:
        last: Optional[GroundTruthAnswer] = None
        for o in self.oracles:
            try:
                ans = o.answer(question)
            except GroundTruthTimeout:
                raise
            except Exception:
                continue
            if ans.verdict is not GroundTruthVerdict.OMIT:
                return ans
            last = ans
        return last or GroundTruthAnswer.omit("no oracle had an answer")


def _build_corpus_oracle(project_root: str):
    """ControlledCorpusOracle for the target project's corpus, or None if absent/empty."""
    try:
        from startd8.corpus.registry import ControlledCorpusRegistry
        from startd8.paths import controlled_corpus_path

        corpus_path = controlled_corpus_path(Path(project_root))
        if not corpus_path.is_file():
            return None
        registry = ControlledCorpusRegistry.load(corpus_path)
        return ControlledCorpusOracle(registry) if len(registry) > 0 else None
    except Exception:
        return None


def _build_project_knowledge_oracle(project_root: str, max_files: int):
    """ProjectKnowledgeOracle (Prisma/TS schema authority) for the target project, or None."""
    try:
        root = Path(project_root)
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
        # Gate on *extracted* authority (field-sets / interfaces). The producer always seeds a
        # baseline negative even for an empty project, so negatives alone is not real authority —
        # an oracle with neither field-sets nor interfaces can only OMIT, so don't present it.
        if not (getattr(pk, "field_sets", None) or getattr(pk, "interfaces", None)):
            return None
        return ProjectKnowledgeOracle(pk)
    except Exception:
        return None


def oracle_for_project(project_root: str, *, max_files: int = 500) -> "FdeQueryLike":
    """Build a composed project ground-truth oracle (FR-SAP-7, Item 4a + v0.8 corpus).

    Composes two backings for the **target** project (never a foreign one): the **Controlled
    Corpus** (canonical domain-term authority, language-agnostic — closes the Python/polyglot
    gap) and **ProjectKnowledge** (Prisma/TS schema/field authority). Returns a cached composite;
    falls back to ``NullOracle`` when neither is available. Never raises into the caller.
    """
    if not Path(project_root).is_dir():
        return NullOracle()
    oracles = [
        o for o in (
            _build_corpus_oracle(project_root),                       # domain-term authority (corpus)
            _build_project_knowledge_oracle(project_root, max_files),  # schema/field authority (Prisma/TS)
        )
        if o is not None
    ]
    if not oracles:
        return NullOracle()
    return CachingOracle(CompositeOracle(oracles))


# Structural alias for the protocol (avoids importing Protocol at call sites).
FdeQueryLike = GroundTruthQuery
