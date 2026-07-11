# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Explain mode (FDE) — compose Service Assistant evidence with SDK mechanism authority.

Per Tekizai-Tekisho: the SA triage supplies the OBSERVED (project) half; this module supplies
the MECHANISM (sdk) half from recorded artifacts (``sources.py``); the output is a *composed*,
source-labeled report — never a solo cross-boundary verdict. Deterministic by default (FR-15);
no LLM is invoked on this path.
"""

from __future__ import annotations

from ..logging_config import get_logger
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import sources
from .models import ClaimLabel, FailureExplanation, FdeExplanation, LabeledClaim

logger = get_logger(__name__)

# SA re_run_strategies that a $0 deterministic failure makes futile (FR-7).
_FUTILE_ON_DETERMINISTIC = {"regenerate_clean", "retry_as_is", "re_run_prior_stage"}


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _observed_claims(failure: Dict[str, Any]) -> List[LabeledClaim]:
    """Lift the SA failure record into OBSERVED (project) claims (the evidence half)."""
    fid = failure.get("feature_id", "?")
    claims = [
        LabeledClaim(
            ClaimLabel.OBSERVED,
            f"feature `{fid}` failed — root_cause `{failure.get('root_cause')}` at stage "
            f"`{failure.get('pipeline_stage')}` (severity {failure.get('severity')})",
            source=sources.TRIAGE_FILENAME,
            claim_id=f"{fid}:observed",
        )
    ]
    rec = failure.get("recommended_action") or {}
    if rec.get("action"):
        claims.append(
            LabeledClaim(
                ClaimLabel.OBSERVED,
                f"SA recommended: {rec.get('action')} (re_run_strategy `{rec.get('re_run_strategy')}`)",
                source=f"{sources.TRIAGE_FILENAME}:recommended_action",
                claim_id=f"{fid}:sa-reco",
            )
        )
    return claims


def _correction_for(failure: Dict[str, Any]) -> Optional[str]:
    """FR-7: where the SA recommendation rests on a wrong mechanism assumption, correct it."""
    rec = failure.get("recommended_action") or {}
    strategy = rec.get("re_run_strategy")
    if failure.get("deterministic") and strategy in _FUTILE_ON_DETERMINISTIC:
        return (
            f"The SA strategy `{strategy}` assumes a re-run can differ, but this failure is on the "
            f"$0 deterministic path (`deterministic=true`): a plain re-run is idempotent and "
            f"reproduces the identical defect. Fix the deterministic generator/template (or escalate "
            f"the element off the deterministic path) — do not 'regenerate next pass'."
        )
    return None


def _batch_claims(triage: Dict[str, Any]) -> List[LabeledClaim]:
    """FR-25: surface SA cross_feature_patterns at batch altitude with a mechanism note."""
    out: List[LabeledClaim] = []
    for pat in triage.get("cross_feature_patterns", []) or []:
        out.append(
            LabeledClaim(
                ClaimLabel.OBSERVED,
                f"batch pattern `{pat.get('pattern_type')}`: {pat.get('description')} "
                f"(affects {', '.join(pat.get('affected_features', []))})",
                source=f"{sources.TRIAGE_FILENAME}:cross_feature_patterns",
            )
        )
    return out


def _semantic_claim(triage: Dict[str, Any]) -> Optional[LabeledClaim]:
    """FR-25 three-way: summarize a folded SCR ref without issuing a competing semantic verdict."""
    sr = triage.get("semantic_review")
    if not sr:
        return None
    claim = LabeledClaim(
        ClaimLabel.OBSERVED,
        f"semantic-compliance review present: aggregate {sr.get('aggregate')}, "
        f"{sr.get('fail', 0)} fail / {sr.get('inconclusive', 0)} inconclusive "
        f"(see {sr.get('report_path')})",
        source="service-assistant-triage.json:semantic_review",
        qualifier="semantic",  # → OBSERVED (project, semantic)
    )
    return claim


def explain_run(
    run_output_dir: Path,
    *,
    feature_ids: Optional[Sequence[str]] = None,
    sdk_version: str = "",
    run_id: Optional[str] = None,
) -> FdeExplanation:
    """Build a composed, source-labeled explanation for a completed/failed run.

    Degrades to a MECHANISM-only report (``evidence_available=False``) when the SA triage is
    absent (FR-25 / R3-S5) — the caller's CLI exits non-zero in that case.
    """
    run_output_dir = Path(run_output_dir)
    triage = sources.read_triage(
        run_output_dir
    )  # may raise ArtifactTrustError → caller handles
    resolved_run_id = (
        run_id
        or ((triage or {}).get("run", {}).get("run_id") if triage else None)
        or run_output_dir.name
    )

    exp = FdeExplanation(
        run_id=resolved_run_id,
        generated_at=_utcnow(),
        sdk_version=sdk_version,
        evidence_available=triage is not None,
    )

    wanted = set(feature_ids or [])
    failures = (triage or {}).get("failures", []) if triage else []
    if wanted:
        failures = [f for f in failures if f.get("feature_id") in wanted]

    if triage is None:
        # Degraded MECHANISM-only: we have no failure list, so emit a single banner claim.
        exp.failures.append(
            FailureExplanation(
                feature_id="(unknown)",
                claims=[
                    LabeledClaim(
                        ClaimLabel.MECHANISM,
                        "no Service Assistant triage found — run `startd8 assist scan <output-dir>` first "
                        "for the full composed explanation",
                        source="(degraded)",
                        qualifier="unavailable",
                    )
                ],
            )
        )
        return exp

    # Batch + three-way claims (composed once, at report altitude).
    exp.batch_claims.extend(_batch_claims(triage))
    sem = _semantic_claim(triage)
    if sem is not None:
        exp.batch_claims.append(sem)

    for failure in failures:
        fid = failure.get("feature_id", "?")
        eid = failure.get("element_id")
        fexp = FailureExplanation(feature_id=fid, element_id=eid)
        fexp.claims.extend(_observed_claims(failure))
        fexp.claims.extend(sources.read_element_mechanism(run_output_dir, fid, eid))
        # RUN-038 #5/#2: convention violations + the safe-fix gap, composed at feature altitude.
        fexp.claims.extend(sources.read_convention_status(run_output_dir, fid))
        fexp.correction = _correction_for(failure)
        exp.failures.append(fexp)

    return exp
