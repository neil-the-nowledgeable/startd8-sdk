# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Two-track preflight (FR-8/FR-9/FR-10/FR-26) — spot SDK-mechanism landmines in plans.

Track 1 (prose-assumption, no signals, runs on raw markdown after redaction): scan the plan /
requirements text for assertions about SDK behavior that contradict how the SDK actually
decides — e.g. naming a language the SDK does not support. Deterministic by default; an LLM
pass may extend it (off by default, FR-15a/FR-22).

Track 2 (mechanism-prediction, signals required, after ``plan-ingestion``): gated and isolated
(FR-26 / R2-S3) — predicts tier/route only for features whose ``target_file`` exists on disk
(greenfield guard, R4-S2), tagging predictions ``PREDICTION (sdk, low-confidence …)`` otherwise.
Heavy + LLM-backed, so it is opt-in and budget-bounded; when unavailable it records a skip.
"""

from __future__ import annotations

from ..logging_config import get_logger
import re
from pathlib import Path
from typing import List, Optional

from . import redaction, sources
from .models import FdePreflightReport, Landmine

logger = get_logger(__name__)

# Languages the SDK reasons about (for prose mention detection). Authority is LanguageRegistry;
# this list only bounds what we *look* for in prose.
_LANGUAGE_HINTS = {
    "python": "python",
    "go": "go",
    "golang": "go",
    "node": "nodejs",
    "nodejs": "nodejs",
    "node.js": "nodejs",
    "javascript": "nodejs",
    "typescript": "nodejs",
    "java": "java",
    "c#": "csharp",
    "csharp": "csharp",
    ".net": "csharp",
    "rust": "rust",
    "ruby": "ruby",
    "php": "php",
    "kotlin": "kotlin",
    "swift": "swift",
    "scala": "scala",
}


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _sdk_version() -> str:
    try:
        from .. import __version__

        return str(__version__)
    except Exception:  # pragma: no cover
        return "0.0.0"


def _detect_language_mentions(text: str) -> List[str]:
    found = []
    low = text.lower()
    for hint, lang_id in _LANGUAGE_HINTS.items():
        if re.search(r"(?<![\w.])" + re.escape(hint) + r"(?![\w])", low):
            if lang_id not in found:
                found.append(lang_id)
    return found


def _track1_prose_landmines(text: str) -> List[Landmine]:
    """Deterministic Track-1 scan: language-support assumptions vs LanguageRegistry."""
    sources.ensure_registries()
    landmines: List[Landmine] = []
    n = 0
    for lang_id in _detect_language_mentions(text):
        cap = sources.language_capability(lang_id)
        if cap.qualifier == "unavailable":  # SDK does not support it
            n += 1
            landmines.append(
                Landmine(
                    landmine_id=f"PF-T1-{n:02d}",
                    track=1,
                    severity="high",
                    title=f"plan targets `{lang_id}`, which the SDK does not support",
                    assumption=f"the plan assumes code generation for `{lang_id}`",
                    mechanism=cap,  # PREDICTION (sdk, ... unavailable)
                )
            )
    return landmines


def preflight_plan(
    plan_path: Optional[Path] = None,
    requirements_path: Optional[Path] = None,
    *,
    enable_track2: bool = False,
    project_root: Optional[Path] = None,
    max_cost_usd: Optional[float] = None,
) -> FdePreflightReport:
    """Run preflight over a plan and/or requirements doc, returning a landmine report.

    Track 1 always runs (cheap, deterministic, redacted). Track 2 runs only when
    ``enable_track2`` and the prerequisites are met; otherwise its intent is recorded as a skip
    so coverage is never silently dropped.
    """
    sdk_version = _sdk_version()
    rep = FdePreflightReport(
        generated_at=_utcnow(),
        sdk_version=sdk_version,
        plan_path=str(plan_path) if plan_path else None,
        requirements_path=str(requirements_path) if requirements_path else None,
    )

    text_parts: List[str] = []
    for p in (plan_path, requirements_path):
        if p and Path(p).exists():
            text_parts.append(Path(p).read_text(encoding="utf-8"))
    raw_text = "\n\n".join(text_parts)

    # FR-23: redact before any LLM could see it (and before we log/emit anything derived).
    redacted_text, manifest = redaction.redact(raw_text)
    rep.redaction_manifest = manifest

    # Track 1 (deterministic over redacted prose).
    rep.landmines.extend(_track1_prose_landmines(redacted_text))

    # Track 2 (gated). The full implementation runs plan-ingestion in an isolated scratch dir,
    # extracts signals for features whose target files exist, and calls classify_live. It is
    # LLM-backed and opt-in; when not enabled we record the intent so coverage is explicit.
    if not enable_track2:
        rep.skipped_track2.append(
            "track2 disabled (pass --track2 to predict tiers via plan-ingestion + classify_tier)"
        )
    else:
        try:
            rep.track2_ran = _run_track2(
                redacted_text,
                plan_path,
                requirements_path,
                project_root,
                rep,
                max_cost_usd,
            )
        except Exception as exc:  # pragma: no cover - track2 is best-effort
            logger.warning("FDE Track 2 failed: %s", exc, exc_info=True)
            rep.skipped_track2.append(f"track2 error: {exc}")

    return rep


def _run_track2(
    redacted_text: str,
    plan_path: Optional[Path],
    requirements_path: Optional[Path],
    project_root: Optional[Path],
    rep: FdePreflightReport,
    max_cost_usd: Optional[float],
) -> bool:
    """Isolated, greenfield-guarded tier prediction. Returns True if it actually ran.

    Records per-feature skips for plan-only (not-materialized) features rather than emitting
    low-signal tier fiction (R4-S2). Requires plan-ingestion (LLM); on absence records a skip.
    """
    from . import context as fde_context

    if not plan_path:
        rep.skipped_track2.append("track2 needs a plan_path for plan-ingestion")
        return False
    root = Path(project_root) if project_root else Path.cwd()
    try:
        from ..workflows import WorkflowRegistry

        WorkflowRegistry.discover()
        wf = WorkflowRegistry.get_workflow("plan-ingestion")
    except Exception:
        rep.skipped_track2.append("plan-ingestion workflow unavailable")
        return False
    if wf is None:
        rep.skipped_track2.append("plan-ingestion workflow not registered")
        return False

    scratch = fde_context.scratch_dir(root, fde_context.checksum_text(redacted_text))
    try:
        result = wf.run({"plan_path": str(plan_path), "output_dir": str(scratch)})
    except Exception as exc:
        rep.skipped_track2.append(f"plan-ingestion run failed: {exc}")
        return False

    features = _extract_features(result)
    if not features:
        rep.skipped_track2.append("plan-ingestion produced no features to classify")
        return True

    n = 0
    for feat in features:
        target_files = getattr(feat, "target_files", None) or (
            feat.get("target_files") if isinstance(feat, dict) else []
        )
        on_disk = any((root / f).exists() for f in (target_files or []))
        fid = getattr(feat, "id", None) or (
            feat.get("feature_id") if isinstance(feat, dict) else "?"
        )
        if not on_disk:
            rep.skipped_track2.append(
                f"{fid}: file_not_materialized (greenfield — Track 1 only)"
            )
            continue
        try:
            from ..complexity.signals import extract_signals_from_feature

            signals = extract_signals_from_feature(feat, root)
            _result, claim = sources.classify_live(signals)
        except Exception:
            continue
        if claim is None:
            continue
        n += 1
        rep.landmines.append(
            Landmine(
                landmine_id=f"PF-T2-{n:02d}",
                track=2,
                severity="medium",
                title=f"tier prediction for `{fid}` (verify against plan expectation)",
                assumption="(compare the plan's stated tier/route expectation to this prediction)",
                mechanism=claim,
                feature_id=fid,
            )
        )
    return True


def _extract_features(workflow_result) -> list:
    """Pull a feature list out of a plan-ingestion WorkflowResult (defensive)."""
    out = getattr(workflow_result, "output", None) or {}
    if isinstance(out, dict):
        for key in ("features", "tasks", "seed_tasks"):
            if isinstance(out.get(key), list):
                return out[key]
    return []
