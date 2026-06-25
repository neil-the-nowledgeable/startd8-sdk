"""Round-3 orchestration (M6 wiring) — resolve a roster, score each finalist's fleet, emit the report.

``run_round3`` is the testable core: it maps each ``FinalistSpec`` through an injectable ``score_fn``
(so the orchestration is unit-tested with synthetic Scorecards, no docker) and renders the ranked
``round3-system-report.{json,md}`` via ``fleet.report``. The CLI passes ``live_score_fn`` (build/boot
the finalist's namespaced fleet + drive Adapter B + score) and ``live_attribution_check`` (the
reference broken-mesh trustworthiness signal). Advisory only (FR-21) — a human picks the roster.

A finalist whose fleet images are absent scores as **infra-degraded** (a sentinel Scorecard), NOT a
model 0 — a missing build is an environment outcome, never the model's catastrophic failure (the
benchmark infra-vs-model discipline).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .report import FinalistScore, build_system_report
from .roster import FinalistSpec
from .score import Scorecard


@dataclass
class ScoreOutcome:
    scorecard: Scorecard
    cost_usd: float = 0.0
    wall_seconds: float = 0.0
    note: str = "ok"


ScoreFn = Callable[[FinalistSpec], ScoreOutcome]


def _infra_degraded(reason: str) -> ScoreOutcome:
    """Sentinel for a finalist that couldn't be scored for an ENV reason (images missing, won't boot)
    — zero coverage, flagged low-confidence, NOT a model fault (no service charged)."""
    return ScoreOutcome(Scorecard(0.0, 0.0, journey_completed=False, confidence="low", faults=[]),
                        note=f"infra: {reason}")


def run_round3(roster: list[FinalistSpec], *, score_fn: ScoreFn, attribution_trustworthy: bool,
               out_dir: Optional[Path] = None) -> tuple[dict, str]:
    """Score every finalist via ``score_fn`` and render the ranked advisory system report. Writes
    ``round3-system-report.{json,md}`` into ``out_dir`` when given. Returns (report dict, markdown)."""
    finalists: list[FinalistScore] = []
    notes: dict[str, str] = {}
    for spec in roster:
        out = score_fn(spec)
        finalists.append(FinalistScore(spec.model, out.scorecard, out.cost_usd, out.wall_seconds))
        notes[spec.model] = out.note
    report, md = build_system_report(finalists, attribution_trustworthy=attribution_trustworthy)
    # carry each finalist's score note (e.g. infra-degraded) into the report for transparency.
    for row in report["finalists"]:
        row["note"] = notes.get(row["model"], "ok")
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "round3-system-report.json").write_text(json.dumps(report, indent=2))
        (out_dir / "round3-system-report.md").write_text(md)
    return report, md


# --- live scoring (used by the CLI; not unit-tested — exercised by validate_m6's reference path) ---

def _images_present(image_namespace: str) -> bool:
    """True iff every contestant backend image exists under ``image_namespace`` (r3/<model>/<svc>)."""
    from .services import contestant_services
    for s in contestant_services():
        tag = f"{image_namespace}/{s.name}:{s.language}"
        if subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode != 0:
            return False
    return True


def live_score_fn(spec: FinalistSpec) -> ScoreOutcome:
    """Bring up the finalist's namespaced fleet, drive Adapter B, score. Reference namespace ("r3")
    is built-if-missing; a model namespace with absent images degrades infra-honestly (its fleet is
    model-generated, not built here)."""
    from .validate_m6 import score_namespace_fleet  # lazy: heavy docker imports
    if spec.image_namespace != "r3" and not _images_present(spec.image_namespace):
        return _infra_degraded(f"fleet images missing under {spec.image_namespace}")
    try:
        # score_namespace_fleet returns a Scorecard; wrap it as the ScoreOutcome run_round3 expects.
        return ScoreOutcome(score_namespace_fleet(spec.image_namespace))
    except Exception as e:  # noqa: BLE001 — a finalist's env failure never aborts the round
        return _infra_degraded(f"{type(e).__name__}: {e}")


def live_attribution_check() -> bool:
    """The reference broken-mesh trustworthiness signal (break payment / catalog → right attribution)."""
    from .validate_m6 import reference_attribution_trustworthy  # lazy
    return reference_attribution_trustworthy()
