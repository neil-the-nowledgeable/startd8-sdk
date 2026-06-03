"""Read views over the Controlled Corpus (FR-9/10).

Two consumers, two views:
  - SCR triage (FR-10): `triage_signal` / `should_escalate` — the deterministic
    replacement for the SCR's keyword `requirement_score` circularity.
  - Generation (FR-9): `stable_authorities` / `render_authorities_md` — corpus-native
    authorities to inject into prompts; plus `as_project_knowledge` for a literal
    ProjectKnowledge-shaped view.

Planning-reflection note: `ProjectKnowledge` is Prisma/TS-shaped (`field_sets`,
`negatives`, TS `interfaces`) and is owned by the CKG producer. The corpus owns a
different vocabulary (services/RPCs/entities/files/metrics), so `as_project_knowledge`
returns the correct shape but leaves the CKG-owned authorities empty and STATES the
boundary in `omissions` — the corpus's own authorities are exposed via
`stable_authorities`. This honors FR-9's "expose a view, don't rewrite the producer".
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from startd8.corpus.registry import ControlledCorpusRegistry

__all__ = [
    "triage_signal",
    "should_escalate",
    "stable_authorities",
    "render_authorities_md",
    "as_project_knowledge",
]


# ---------------------------------------------------------------------------
# SCR triage read (FR-10)
# ---------------------------------------------------------------------------
def triage_signal(registry: ControlledCorpusRegistry, target_file: str) -> Optional[Dict[str, Any]]:
    """Per-target_file determinism signal for the SCR triage. None if unseen."""
    term = registry.find_by_canonical_key("file", target_file)
    if term is None:
        return None
    det = term.determinism
    return {
        "target_file": target_file,
        "success_stability": det.success_stability,
        "mean_requirement_score": det.mean_requirement_score,
        "corpus_class": det.corpus_class,
        "maturity": term.maturity,
        "n_observations": det.n_observations,
    }


def should_escalate(registry: ControlledCorpusRegistry, target_file: str) -> bool:
    """SCR escalation decision (FR-10). Two-axis (R4-F2): escalate unless the corpus is
    confident on BOTH axes — i.e. unless `corpus_class == "deterministic_candidate"`
    (structurally stable AND semantically compliant AND enough samples).

    This deliberately escalates `needs_semantic_review` (stable build, mid requirement_score
    — the SCR's highest-value target), `deterministic_candidate_unscored` (no semantic signal
    yet), `unobserved`, `insufficient_samples`, `false_pass_risk`, `residue_corpus_gap`, and
    `needs_more_runs`. Deferring to `corpus_class` means the stability threshold has a single
    source of truth in `classify_determinism` (R3-S3: no independent threshold to drift).
    """
    sig = triage_signal(registry, target_file)
    if sig is None:
        return True  # never seen — review it
    return sig["corpus_class"] != "deterministic_candidate"


# ---------------------------------------------------------------------------
# Generation reads (FR-9)
# ---------------------------------------------------------------------------
def stable_authorities(
    registry: ControlledCorpusRegistry,
    *,
    min_maturity: int = 2,
    kinds: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Corpus-native authorities for prompt injection: mature, recurring terms.

    Excludes `false_pass_risk` terms — a stable build that doesn't meet the
    requirement must NOT be presented to generation as an authority (FR-8).
    """
    out: List[Dict[str, Any]] = []
    for t in registry.terms:
        if t.maturity < min_maturity:
            continue
        if kinds and t.kind not in kinds:
            continue
        if t.determinism.corpus_class == "false_pass_risk":
            continue
        # R3-S2: never inject zero-evidence terms as authorities. Proto terms reach
        # L2 by recurrence alone (no success/fail observations) — exclude them until
        # a run actually exercises their binding.
        if t.determinism.n_observations == 0:
            continue
        out.append({
            "kind": t.kind,
            "canonical": t.canonical_key,
            "surface_forms": sorted(t.surface_forms),
            "bindings": [b.to_dict() for b in t.bindings],
            "maturity": t.maturity,
            "stability": t.determinism.success_stability,
        })
    return out


def render_authorities_md(registry: ControlledCorpusRegistry, *, min_maturity: int = 2) -> str:
    """Render mature corpus terms as a prompt-injectable markdown block (mirrors
    project_knowledge/render.py style). Empty string when no mature terms."""
    auth = stable_authorities(registry, min_maturity=min_maturity)
    if not auth:
        return ""
    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for a in auth:
        by_kind.setdefault(a["kind"], []).append(a)
    lines = ["## Established project vocabulary (use these canonical names exactly)"]
    for kind in sorted(by_kind):
        lines.append(f"\n### {kind}")
        for a in sorted(by_kind[kind], key=lambda x: x["canonical"]):
            refs = ", ".join(b["construct_ref"] for b in a["bindings"]) or a["canonical"]
            lines.append(f"- `{a['canonical']}` → {refs}")
    return "\n".join(lines)


def as_project_knowledge(registry: ControlledCorpusRegistry, project_root: str = ""):
    """A literal ProjectKnowledge-shaped view (FR-9).

    Returns a real `ProjectKnowledge`. CKG-owned authorities (field_sets/negatives/
    TS interfaces) stay empty — the corpus does not own them — and the boundary is
    stated in `omissions`. The corpus's authorities are exposed via `stable_authorities`.
    """
    from startd8.contractors.project_knowledge.models import ProjectKnowledge

    mature = stable_authorities(registry, min_maturity=2)
    omission = (
        f"controlled-corpus exposes {len(mature)} mature term(s) via "
        "corpus.view.stable_authorities(); field_sets / negatives / TS interfaces "
        "remain CKG-producer-owned (not corpus-derived)."
    )
    return ProjectKnowledge(
        project_root=project_root,
        field_sets=(),
        interfaces=(),
        negatives=(),
        omissions=(omission,),
    )
