"""CKG Phase 2 — adherence harness core (REQ-CKG-530, D1). SCAFFOLD.

D1, the headline guardrail: injection ≠ adherence. Putting the real field sets /
module paths in the spec prompt is *necessary but not sufficient* — RUN-011 proved
the drafter read ``schema.prisma`` and still invented fields. So success is measured
at **two levels**:

- **Injection** (deterministic, unit-tested elsewhere): the prompt contains the truth.
- **Adherence** (empirical, here): the *generated code* uses it — measured over
  **N ≥ 5 seeds/feature** against an **adherence-rate threshold (~0.9)**. A single
  passing re-run can't distinguish a fix from sampling luck; below threshold →
  escalate (Approach C contract-first).

This module is the **measurement scaffold**: cases, prompt builder (reusing the
Phase-2 provider), the adherence check, and per-Gap rate aggregation. The actual
generation is pluggable via :class:`GenerationBackend`. :class:`MockBackend` makes
the harness runnable/testable with no API cost; a real LLM backend (see
``scripts/ckg_adherence_harness.py``) plugs in to run it for real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Protocol, Sequence, Tuple

from .producer import DraftModeProducer
from .render import render
from .scoping import referenced_entities

__all__ = [
    "AdherenceCase",
    "GenerationBackend",
    "MockBackend",
    "AdherenceResult",
    "SuiteReport",
    "RUN011_CASES",
    "DEFAULT_THRESHOLD",
    "DEFAULT_SEEDS",
    "build_spec_prompt",
    "measure_adherence",
    "measure_adherence_structural",
    "run_case",
    "run_suite",
]

DEFAULT_THRESHOLD = 0.9
DEFAULT_SEEDS = 5

# A small schema standing in for the RUN-011 project (Capability/Outcome domain).
_CAP_SCHEMA = (
    "model Capability {\n id String @id @default(cuid())\n name String\n"
    " summary String\n score Float?\n}\n"
    "model Outcome {\n id String @id\n label String\n capabilityId String\n}\n"
)


@dataclass(frozen=True)
class AdherenceCase:
    """One RUN-011 failure-class reproduction.

    ``forbidden`` are the invented tokens that MUST NOT appear in adherent output
    (the literal RUN-011 inventions); their absence is the adherence signal.
    """

    case_id: str
    gap: str  # "A" (field invention) | "B" (path invention)
    feature_name: str
    description: str
    target_files: Tuple[str, ...]
    prisma_schema: str
    forbidden: Tuple[str, ...]
    # Structural-scoring inputs (REQ-CKG-530 hardening): the `@/`-aliased modules the
    # feature may legitimately import. For Gap-B cases, any other `@/` import is an
    # invention — a positive check that catches novel wrong paths the `forbidden`
    # denylist would miss.
    real_modules: Tuple[str, ...] = ()
    prisma_path: str = "prisma/schema.prisma"


# RUN-011 M4 field/path invention reproductions (Gap A + Gap B).
RUN011_CASES: Tuple[AdherenceCase, ...] = (
    AdherenceCase(
        case_id="PI-001", gap="A", feature_name="enrich-capabilities",
        description="Enrich each Capability with a derived Outcome score.",
        target_files=("app/actions/enrich.ts",), prisma_schema=_CAP_SCHEMA,
        forbidden=("aiRefId", "supportingEvidence", "title"),
    ),
    AdherenceCase(
        case_id="PI-004", gap="A", feature_name="capability-card",
        description="Render a Capability summary card.",
        target_files=("components/CapabilityCard.tsx",), prisma_schema=_CAP_SCHEMA,
        forbidden=("bio", "label", "headline"),
    ),
    AdherenceCase(
        case_id="PI-002", gap="B", feature_name="capability-route",
        description="API route that queries Capability rows via the Prisma client.",
        target_files=("app/api/capability/route.ts",), prisma_schema=_CAP_SCHEMA,
        forbidden=("@/lib/prisma", "@/lib/db/capability"),
        real_modules=("@/lib/db",),
    ),
    AdherenceCase(
        case_id="PI-007", gap="B", feature_name="outcome-service",
        description="Service that loads Outcome rows and calls the AI service.",
        target_files=("lib/outcome-service.ts",), prisma_schema=_CAP_SCHEMA,
        forbidden=("@/lib/prisma", "@/lib/ai/client"),
        real_modules=("@/lib/db", "@/lib/ai/service"),
    ),
)


class GenerationBackend(Protocol):
    """Pluggable code generator. Real backends call an LLM; Mock is deterministic."""

    def generate(self, *, prompt: str, seed: int) -> str:
        ...


@dataclass
class MockBackend:
    """Deterministic backend for scaffold self-test (no API cost).

    ``outputs_by_case`` maps case_id → the canned outputs to cycle through across
    seeds, so a test can model an obedient vs an inventing drafter. ``default`` is
    returned for unknown cases.
    """

    outputs_by_case: Dict[str, Sequence[str]] = field(default_factory=dict)
    default: str = ""

    def generate(self, *, prompt: str, seed: int) -> str:
        # the case_id is embedded in the prompt header (see build_spec_prompt)
        for cid, outs in self.outputs_by_case.items():
            if f"[case:{cid}]" in prompt and outs:
                return outs[seed % len(outs)]
        return self.default


@dataclass(frozen=True)
class AdherenceResult:
    case_id: str
    gap: str
    inject: bool
    n: int
    adherent: int

    @property
    def rate(self) -> float:
        return self.adherent / self.n if self.n else 0.0


@dataclass(frozen=True)
class SuiteReport:
    results: Tuple[AdherenceResult, ...]
    threshold: float

    def rate_by_gap(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for gap in sorted({r.gap for r in self.results}):
            rs = [r for r in self.results if r.gap == gap]
            n = sum(r.n for r in rs)
            adherent = sum(r.adherent for r in rs)
            out[gap] = adherent / n if n else 0.0
        return out

    def passes(self) -> bool:
        return all(rate >= self.threshold for rate in self.rate_by_gap().values())


def build_spec_prompt(case: AdherenceCase, *, inject: bool) -> str:
    """Construct the drafter prompt; with ``inject`` it appends the provider section.

    The ``[case:<id>]`` marker lets a MockBackend route deterministically; a real
    backend ignores it. Injection reuses the Phase-2 provider end-to-end: build the
    artifact, scope to the referenced entities, render.
    """
    base = (
        f"[case:{case.case_id}] Implement feature '{case.feature_name}'.\n"
        f"{case.description}\n"
        f"Target files: {', '.join(case.target_files)}"
    )
    if not inject:
        return base
    pk = DraftModeProducer().build({"prisma/schema.prisma": case.prisma_schema}, ".")
    signal = " ".join([case.feature_name, case.description, *case.target_files])
    referenced = referenced_entities([signal], pk.entities())
    scoped = _scope_to_entities(pk, referenced) if referenced else pk
    section = render(scoped, log=False)
    return base + ("\n\n" + section if section else "")


def _scope_to_entities(pk, entities):
    """Narrow a ProjectKnowledge artifact to the referenced entities (REQ-524)."""
    from .models import ProjectKnowledge
    keep = set(entities)
    return ProjectKnowledge(
        project_root=pk.project_root,
        field_sets=tuple(fs for fs in pk.field_sets if fs.entity in keep),
        interfaces=pk.interfaces,
        negatives=pk.negatives,
        omissions=pk.omissions,
    )


def measure_adherence(code: str, case: AdherenceCase) -> bool:
    """Denylist scoring: adherent iff the code contains none of the literal
    RUN-011 invention tokens. Fast/deterministic — used for harness mechanics
    and the unit tests. Can FALSE-PASS a *different* invented field/path.
    """
    return not any(tok in code for tok in case.forbidden)


def measure_adherence_structural(code: str, case: AdherenceCase) -> bool:
    """Structural scoring (REQ-CKG-530 hardening): a POSITIVE check via the Phase-1
    detectors — adherent iff the code uses only *real* fields/paths, catching
    inventions the denylist would miss (the false-pass killer).

    - **Gap A (fields):** run `scan_prisma_usage` (db.<model> calls) + the Prisma↔Zod
      symmetry check against the case's real schema; any error finding = non-adherent.
    - **Gap B (paths):** any ``@/``-aliased import not under a declared real module = non-adherent.
    """
    if case.gap == "A":
        from ...validators.prisma_usage import scan_prisma_usage
        from ...validators.prisma_zod_symmetry import evaluate_cross_file_integrity

        sources = {case.prisma_path: case.prisma_schema, "generated.ts": code}
        if scan_prisma_usage(sources, "."):
            return False
        if any(f.severity == "error" for f in evaluate_cross_file_integrity(sources)):
            return False
        return True

    # Gap B: positive allowlist over @/-aliased imports.
    from ..upstream_interface import extract_import_specifiers

    reals = [m.rstrip("/") for m in case.real_modules]
    for spec in extract_import_specifiers(code):
        if not spec.startswith("@/"):
            continue  # bare packages (zod, next, …) are not project modules
        s = spec.rstrip("/")
        if not any(s == m or s.startswith(m + "/") for m in reals):
            return False  # an @/ import outside the real module set → invention
    return True


_SCORERS = {"denylist": measure_adherence, "structural": measure_adherence_structural}


def run_case(
    case: AdherenceCase,
    backend: GenerationBackend,
    *,
    inject: bool,
    n_seeds: int = DEFAULT_SEEDS,
    scoring: str = "denylist",
) -> AdherenceResult:
    score = _SCORERS[scoring]
    prompt = build_spec_prompt(case, inject=inject)
    adherent = sum(
        1 for s in range(n_seeds)
        if score(backend.generate(prompt=prompt, seed=s), case)
    )
    return AdherenceResult(case.case_id, case.gap, inject, n_seeds, adherent)


def run_suite(
    cases: Sequence[AdherenceCase],
    backend: GenerationBackend,
    *,
    inject: bool,
    n_seeds: int = DEFAULT_SEEDS,
    threshold: float = DEFAULT_THRESHOLD,
    scoring: str = "denylist",
) -> SuiteReport:
    results = tuple(
        run_case(c, backend, inject=inject, n_seeds=n_seeds, scoring=scoring)
        for c in cases
    )
    return SuiteReport(results=results, threshold=threshold)
