"""FR-SAP-9 — host integration entry point (the cross-task output channel).

``domain-preflight``'s native output is per-task ``TaskEnrichment``; the Sapper friction report
is **cross-task** (it ranks across the whole plan). So this module is the *new* output channel
(requirements §0.9 discovery #4): given the in-memory ForwardManifest + skeleton_sources the
EMIT stage already produced, it runs the gate, writes the report artifact, emits metrics, and
returns the downstream-injection block.

A ``domain-preflight`` host calls ``sapper_preflight_hook(...)`` after classify/check; it does
not need to thread the report through ``TaskEnrichment``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from startd8.logging_config import get_logger

from .gate import SapperGateResult, run_sapper_gate
from .report import build_injection_block, emit_metrics, write_report

logger = get_logger(__name__)

SEED_NAME = "artisan-context-seed.json"


def load_from_ingestion_seed(seed_or_dir: str) -> Tuple[object, Dict[str, str]]:
    """Load the ``ForwardManifest`` + ``skeleton_sources`` from a plan-ingestion output.

    Accepts either the ``artisan-context-seed.json`` path or its containing directory. The EMIT
    step persists ``skeleton_sources`` under the seed's ``artifacts`` block and the
    ``forward_manifest`` at the seed's TOP LEVEL (pre-2026-06 seeds carried a duplicate copy
    under ``artifacts`` — still read as a fallback). If the full manifest was not persisted, a
    *minimal* manifest is reconstructed from the skeleton paths so the bore + convention route
    still run (the cross-contract / per-element lenses need the full manifest).

    Returns ``(manifest, skeleton_sources)``. ``manifest`` is ``None`` and ``skeleton_sources``
    empty if the seed has no EMIT artifacts — the gate then emits a loud ``input_absent`` report.
    """
    p = Path(seed_or_dir)
    seed_path = p / SEED_NAME if p.is_dir() else p
    if not seed_path.is_file():
        logger.warning("ingestion seed not found: %s", seed_path)
        return None, {}

    try:
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # malformed/unreadable seed → loud input_absent, never a traceback into the CLI
        logger.warning("ingestion seed %s unreadable (%s)", seed_path, exc)
        return None, {}
    if not isinstance(seed, dict):
        logger.warning("ingestion seed %s is not a JSON object", seed_path)
        return None, {}
    artifacts = seed.get("artifacts", {}) or {}
    skeleton_sources: Dict[str, str] = dict(artifacts.get("skeleton_sources") or {})
    if not skeleton_sources:
        logger.warning("seed %s has no skeleton_sources (pre-EMIT or no extractable plan)", seed_path)
        return None, {}

    manifest = _load_manifest(seed, artifacts, skeleton_sources)
    return manifest, skeleton_sources


def _load_manifest(seed: dict, artifacts: dict, skeleton_sources: Dict[str, str]):
    from startd8.forward_manifest import ForwardFileSpec, ForwardManifest

    # Canonical home is the seed top level; pre-2026-06 seeds duplicated it
    # under artifacts (since removed — it doubled an 88 MB seed).
    fm = seed.get("forward_manifest") or artifacts.get("forward_manifest")
    if isinstance(fm, dict):
        try:
            return ForwardManifest.model_validate(fm)
        except Exception as exc:  # tolerate schema drift — fall back to minimal
            logger.info("forward_manifest in seed failed validation (%s); using minimal manifest", exc)
    # Minimal manifest: enough for the bore + convention route (which read skeleton text),
    # while cross-contract / per-element lenses simply find nothing on empty file_specs.
    return ForwardManifest(
        file_specs={path: ForwardFileSpec(file=path) for path in skeleton_sources}
    )


@dataclass
class SapperPreflightOutcome:
    result: SapperGateResult
    artifacts: Dict[str, str]
    metrics: Dict[str, object]
    injection_block: str

    @property
    def blocked(self) -> bool:
        return self.result.blocked


def sapper_preflight_hook(
    manifest,
    skeleton_sources: Optional[dict],
    *,
    project_root: Optional[str] = None,
    out_dir: Optional[str] = None,
    fde=None,
) -> SapperPreflightOutcome:
    """Run the survey and deliver the report. The single seam a host stage calls (FR-SAP-9).

    Returns the gate result, written artifact paths (if ``out_dir`` given), the metric payload,
    and the prompt-injection block to fold into downstream generation prompts (FR-SAP-12).
    """
    result = run_sapper_gate(manifest, skeleton_sources, project_root, fde=fde)
    artifacts: Dict[str, str] = {}
    if out_dir:
        artifacts = write_report(result.report, out_dir)
    metrics = emit_metrics(result.report)
    injection = build_injection_block(result.report)

    logger.info(
        "sapper preflight complete",
        extra={
            "findings": len(result.report.findings),
            "unresolved_rate": result.report.unresolved_rate(),
            "bore_status": result.report.bore_status,
            "blocked": result.blocked,
        },
    )
    return SapperPreflightOutcome(
        result=result, artifacts=artifacts, metrics=metrics, injection_block=injection
    )
