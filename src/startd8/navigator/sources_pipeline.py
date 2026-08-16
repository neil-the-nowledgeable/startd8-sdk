"""Project the prose→product pipeline as Nodes — the compiler made observable (REQ-08).

The source thesis (``~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md``) names the SDK's
existing machinery as a **compiler whose source language is prose**: functional description (the *source
language*) → contract / Node (the *IR*) → implementation (the code-gen back-end) → tests derived from
``Verify:`` (the *oracle*) → docs (the *man-page*). This source **models** those six stages as ``Node``s
so any project can be *viewed* as a compilation — it does NOT re-implement the pipeline (NR-1/NR-2).

Kagami (鏡): a ``Stage`` is **not** a new dataclass and adds **no** field to ``Node`` — it is a ``Node``
in the reserved ``category="pipeline-stage"`` with typed ``attributes`` and the existing ``child_keys``
DEPENDS-ON edge (the same ``category``+``attributes`` projection convention ``sources_node_schema`` uses).
A stage's ``status`` derives from its ``sdk_artifact`` resolving on disk (``derive_status`` with a
constant ``maturity="stable"`` → BUILT when present, SPEC when absent — never THIN), so the view is
grounded in the real repo, not hand-drawn.
"""
from __future__ import annotations

import graphlib
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

from .models import DerivationEdge, Node, NodeEvidence, RealizationRegime, derive_status
from .naming import name_forms
from .view_definition import (
    DEFINITION_REGISTRY,
    PIPELINE_DEFINITION,
    resolve,
    to_render_profile,
)

# REQ-08 FR-1/D-1: the pipeline profile is projected from the registered ``PIPELINE_DEFINITION`` delta
# over ``base`` (like every other domain), NOT a hand-built RenderProfile literal.
PIPELINE_PROFILE = to_render_profile(resolve(PIPELINE_DEFINITION, DEFINITION_REGISTRY))


class Stage(NamedTuple):
    """One row of the ``_STAGES`` table — a projection spec for a pipeline-stage Node."""

    key: str
    ordinal: int
    human_form: str
    sdk_artifact: str  # repo-relative path whose on-disk presence grounds the stage
    compiler_analogue: str
    essence: str  # essential | accidental
    does: str
    child_keys: Tuple[str, ...]  # DEPENDS-ON: the stage(s) this one consumes
    # REQ-18 FR-1: the DECLARED realization regime of the transform that produces this stage — the
    # prose→product pipeline the source models is the deterministic ``$0`` compiler (backend_codegen /
    # det-req / forward_manifest), so its edges declare ``deterministic``. The honest, natural place to
    # declare (handoff §2); requirement graphs carry no declared regime until REQ-19 (b) measures it.
    regime: str = RealizationRegime.DETERMINISTIC


# The six named stages of the prose→product compiler, with the concrete SDK artifact that realises each
# (R1-S2). Ordinals 0..5; edges: intent(0) → functional(1) → contract(2) → {impl(3), test(4), doc(5)}.
# ``child_keys`` points a stage at the stage it CONSUMES (its upstream dependency), so the DAG reads
# intent → … → doc when topologically sorted.
_STAGES: Tuple[Stage, ...] = (
    Stage(
        key="stage:intent",
        ordinal=0,
        human_form="the prose brief / seed task",
        sdk_artifact="src/startd8/seeds/",
        compiler_analogue="source text (the prose brief)",
        essence="essential",
        does="prose brief → a structured intent",
        child_keys=(),
    ),
    Stage(
        key="stage:functional",
        ordinal=1,
        human_form="det-req functional requirements",
        sdk_artifact="src/startd8/navigator/det_req.py",
        compiler_analogue="lexer/parser → FR tokens",
        essence="essential",
        does="intent → structured requirements (FRs)",
        child_keys=("stage:intent",),
    ),
    Stage(
        key="stage:contract",
        ordinal=2,
        human_form="the contract / Node (the IR)",
        sdk_artifact="src/startd8/forward_manifest.py",
        compiler_analogue="IR (the contract/Node)",
        essence="essential",
        does="requirements → a contract / Node (the IR)",
        child_keys=("stage:functional",),
    ),
    Stage(
        key="stage:impl",
        ordinal=3,
        human_form="the generated implementation",
        sdk_artifact="src/startd8/backend_codegen/",
        compiler_analogue="code-gen back-end / interpreter",
        essence="accidental",
        does="contract → implementation code",
        child_keys=("stage:contract",),
    ),
    Stage(
        key="stage:test",
        ordinal=4,
        human_form="the derived test suite",
        sdk_artifact="src/startd8/backend_codegen/test_emitter.py",
        compiler_analogue="oracle (tests from Verify:)",
        essence="accidental",
        does="contract → tests (the oracle)",
        child_keys=("stage:contract",),
    ),
    Stage(
        key="stage:doc",
        ordinal=5,
        human_form="the documentation",
        sdk_artifact="docs/",
        compiler_analogue="man-page",
        essence="accidental",
        does="contract → documentation (the man-page)",
        child_keys=("stage:contract",),
    ),
)

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def stages() -> Tuple[Stage, ...]:
    """The immutable ``_STAGES`` table (consumed by FR-6 provenance ownership resolution)."""
    return _STAGES


def nodes_from_pipeline(repo: Optional[Path] = None) -> List[Node]:
    """Project the six prose→product stages as ``Node``s (``category="pipeline-stage"``).

    Each stage's ``status`` derives from its ``sdk_artifact`` resolving under ``repo`` (default: the SDK
    repo root) — present → a ``code`` Lives → ``derive_status(has_code_evidence=True, maturity="stable")``
    = BUILT; absent → SPEC. ``child_keys`` carries the DEPENDS-ON edges (FR-2). No field is added to
    ``Node`` (FR-1 / NR-3) — the stage-specific typing rides the open ``attributes`` bag.
    """
    repo_root = Path(repo) if repo else _repo_root()
    nodes: List[Node] = []
    for st in _STAGES:
        artifact_path = repo_root / st.sdk_artifact
        has_code = artifact_path.exists()
        status = derive_status(has_code_evidence=has_code, maturity="stable")
        semantic = (
            f"Pipeline stage {st.human_form} — {st.does} "
            f"(compiler analogue: {st.compiler_analogue})"
        )
        attrs: Dict[str, str] = {
            "kind": "stage",
            "title": st.key,
            "ordinal": str(st.ordinal),
            "human_form": st.human_form,
            "sdk_artifact": st.sdk_artifact,
            "compiler_analogue": st.compiler_analogue,
            "essence": st.essence,
            "status_key": status,
            "section_order": str(st.ordinal * 10),
        }
        attrs.update(name_forms(semantic, st.key, initiative="pipeline", kind="pipeline-stage"))
        # The stage Lives to its own SDK artifact (grounded, like node-schema fields Live to models.py).
        lives = (
            NodeEvidence(type="code", ref=st.sdk_artifact, note=f"stage artifact ({st.compiler_analogue})"),
        )
        nodes.append(Node(
            key=st.key,
            does=st.does,
            status=status,
            lives=lives,
            category="pipeline-stage",
            orientation="pipeline",
            route_state="sdk_emitted",
            child_keys=st.child_keys,
            # REQ-16 FR-1: the stage's upstream dependency is a *typed* derivation edge (``derived-from``),
            # distinct from containment ``children`` — so ``pipeline_provenance`` reads the compilation
            # chain from the typed edge rather than reconstructing it. ``child_keys`` is retained for
            # topo_order + backward compat; the ``regime`` slot stays unset here (NR-6).
            derivation=tuple(DerivationEdge(from_key=ck, regime=st.regime) for ck in st.child_keys),
            attributes=attrs,
        ))
    # Fail-loud build-time acyclicity guard (R8-EB-3): validate the stage DAG is acyclic at construction,
    # not only in a test. Raises graphlib.CycleError if an edit ever introduces a cycle in _STAGES. Pass
    # the freshly-built nodes so topo_order does not re-enter nodes_from_pipeline.
    topo_order(nodes)
    return nodes


def topo_order(stage_nodes: Optional[List[Node]] = None) -> List[str]:
    """Topologically sort the stage DAG (FR-2 acceptance) — raises ``graphlib.CycleError`` on a cycle.

    Consumes ``child_keys`` (the DEPENDS-ON edge = upstream dependency) so the returned order lists a
    stage AFTER the stage(s) it consumes — intent → functional → contract → {impl, test, doc}.
    """
    src = nodes_from_pipeline() if stage_nodes is None else stage_nodes
    ts: graphlib.TopologicalSorter = graphlib.TopologicalSorter()
    for n in src:
        ts.add(n.key, *n.child_keys)
    return list(ts.static_order())
