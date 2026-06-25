"""Round-3 system report + finalist ranking + decision gate (M6).

Turns per-finalist system scorecards (each finalist = one model's own 9-service fleet scored by
Adapter B + ``fleet.score``) into a ranked ``round3-system-report.{json,md}`` and an **advisory**
(FR-21) decision gate. The gate answers the two terminal questions of the round:
  * **does the journey discriminate finalists?** — is there real spread in system scores (if every
    finalist ties, the journey isn't separating them);
  * **is attribution trustworthy?** — did the M3 broken-mesh checks attribute faults to the right
    service+class (a harness-level property, supplied from ``validate_m3``).

System score = the canonical-journey **weighted** per-step coverage (the §1 locust mix — browse-heavy
with the deep checkout). Ties break on fewer own-service model-faults, then lower cost. Pure functions
over ``Scorecard`` — no transport — so the report + gate are unit-testable with synthetic finalists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .score import Scorecard


@dataclass
class FinalistScore:
    """One finalist: a model's id + its healthy-mesh system Scorecard + cost/speed metadata."""
    model: str
    scorecard: Scorecard
    cost_usd: float = 0.0
    wall_seconds: float = 0.0

    @property
    def system_score(self) -> float:
        return self.scorecard.weighted_coverage

    @property
    def model_fault_count(self) -> int:
        return len(self.scorecard.model_faulted_services)


def rank_finalists(finalists: list[FinalistScore]) -> list[FinalistScore]:
    """Rank by system score (desc); tie-break: fewer own model-faults, then lower cost, then model id
    (stable + deterministic)."""
    return sorted(finalists,
                  key=lambda f: (-f.system_score, f.model_fault_count, f.cost_usd, f.model))


@dataclass
class DecisionGate:
    discriminates: bool
    attribution_trustworthy: bool
    spread: float                 # max - min system score across finalists
    note: str = ""

    @property
    def verdict(self) -> str:
        """Advisory only (FR-21) — a human decides; this summarizes the two terminal questions."""
        return "GO" if (self.discriminates and self.attribution_trustworthy) else "NO-GO"


def decide(finalists: list[FinalistScore], *, attribution_trustworthy: bool,
           min_spread: float = 0.01) -> DecisionGate:
    """Build the decision gate. Discrimination needs ≥2 finalists AND a score spread ≥ ``min_spread``
    (all-tie ⇒ the journey doesn't separate them)."""
    scores = [f.system_score for f in finalists]
    spread = (max(scores) - min(scores)) if scores else 0.0
    discriminates = len(finalists) >= 2 and spread >= min_spread
    if len(finalists) < 2:
        note = "only one finalist — discrimination cannot be assessed"
    elif not discriminates:
        note = f"finalists tie within {min_spread} — journey does not separate them"
    elif not attribution_trustworthy:
        note = "journey separates finalists but attribution is NOT trustworthy (broken-mesh checks failed)"
    else:
        note = "journey discriminates AND attribution is trustworthy"
    return DecisionGate(discriminates=discriminates, attribution_trustworthy=attribution_trustworthy,
                        spread=spread, note=note)


def build_system_report(finalists: list[FinalistScore], *, attribution_trustworthy: bool,
                        min_spread: float = 0.01) -> tuple[dict, str]:
    """Render the ranked system report as (json-able dict, markdown). Advisory (FR-21)."""
    ranked = rank_finalists(finalists)
    gate = decide(ranked, attribution_trustworthy=attribution_trustworthy, min_spread=min_spread)

    rows = []
    for i, f in enumerate(ranked, 1):
        sc = f.scorecard
        rows.append({
            "rank": i, "model": f.model,
            "system_score": f.system_score, "unweighted_coverage": sc.unweighted_coverage,
            "journey_completed": sc.journey_completed, "confidence": sc.confidence,
            "model_faults": sorted(sc.model_faulted_services),
            "propagated": sorted(sc.propagated_services),
            "cost_usd": f.cost_usd, "wall_seconds": f.wall_seconds,
        })
    report = {
        "round": "round3",
        "advisory": True,  # FR-21 — no auto-orchestrator; a human picks the finalists
        "decision_gate": {"verdict": gate.verdict, "discriminates": gate.discriminates,
                          "attribution_trustworthy": gate.attribution_trustworthy,
                          "spread": gate.spread, "note": gate.note},
        "finalists": rows,
    }
    return report, _render_md(report)


def _f(x: Optional[float], p: int = 3) -> str:
    return "—" if x is None else f"{x:.{p}f}"


def _render_md(report: dict) -> str:
    g = report["decision_gate"]
    lines = [
        "# Round 3 — System Report (advisory)",
        "",
        f"**Decision gate: {g['verdict']}** — {g['note']}",
        f"(discriminates={g['discriminates']}, attribution_trustworthy={g['attribution_trustworthy']}, "
        f"score spread={_f(g['spread'])})",
        "",
        "## Finalist leaderboard",
        "",
        "| Rank | Model | system score | unweighted | journey | confidence | model-faults | cost $ | wall s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["finalists"]:
        faults = ", ".join(r["model_faults"]) or "—"
        lines.append(
            f"| {r['rank']} | `{r['model']}` | {_f(r['system_score'])} | {_f(r['unweighted_coverage'])} | "
            f"{'✓' if r['journey_completed'] else '✗'} | {r['confidence']} | {faults} | "
            f"{_f(r['cost_usd'], 4)} | {_f(r['wall_seconds'], 1)} |")
    if not report["finalists"]:
        lines.append("| — | (no finalists) | | | | | | | |")
    return "\n".join(lines) + "\n"
