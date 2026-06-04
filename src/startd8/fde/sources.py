# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Mechanism-authority source-of-truth readers (FDE deterministic core).

This module is the FDE's analogue of the §6 source-of-truth table in the requirements:
one reader per mechanism question, each returning a :class:`LabeledClaim` that cites the
authoritative SDK symbol/artifact. **Deterministic-first (FR-15):** nothing here calls an
LLM — it reads artifacts and calls pure SDK functions. A guard test (Phase 6) asserts this
module imports no provider/agent modules.

Two read modes (FR-16):
  * **explain**  — read recorded facts FROM the run's artifacts (``ElementResult`` /
    ``ElementPostMortem``); label ``MECHANISM``.
  * **preflight** — compute LIVE (``classify_tier`` / ``LanguageRegistry`` / model catalog);
    label ``PREDICTION``.

Artifact trust (FR-18): every consumed artifact is loaded through :func:`load_json_artifact`,
which validates JSON + a light schema sentinel and degrades (returns ``None`` + a labeled
"unavailable" claim) rather than fabricating a confident claim from a malformed input.
"""

from __future__ import annotations

import glob
import json
from ..logging_config import get_logger
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import ClaimLabel, LabeledClaim

logger = get_logger(__name__)

TRIAGE_FILENAME = "service-assistant-triage.json"
POSTMORTEM_FILENAME = "prime-postmortem-report.json"
RUN_RESULT_GLOB = "prime-result*.json"

# cap-dev-pipe output layout: <project-root>/.cap-dev-pipe/pipeline-output/<project>/run-*/plan-ingestion
PIPELINE_OUTPUT_REL = ".cap-dev-pipe/pipeline-output"
RUN_SUBDIR = "plan-ingestion"


class LatestRunError(Exception):
    """Raised when latest-run resolution cannot pick a single target (FR-28)."""


def resolve_latest_run(
    *,
    project_root: Optional[Path] = None,
    base: Optional[Path] = None,
    project_id: Optional[str] = None,
) -> Path:
    """Resolve the most recent run dir to explain (FR-28).

    Picks the newest ``run-*/plan-ingestion`` that has a ``service-assistant-triage.json``
    (the evidence half); falls back to the newest with ``prime-result*.json``. ``base`` defaults
    to ``<project-root>/.cap-dev-pipe/pipeline-output``. Raises :class:`LatestRunError` with an
    actionable message when the project subdir is ambiguous or no run is found.
    """
    root = Path(project_root) if project_root else Path.cwd()
    base_dir = Path(base) if base else root / PIPELINE_OUTPUT_REL
    if not base_dir.is_dir():
        raise LatestRunError(
            f"no pipeline-output base at {base_dir} — pass --base or an explicit run dir"
        )

    project_dir = _select_project_dir(base_dir, project_id)
    run_dirs = sorted(
        (d for d in project_dir.iterdir() if d.is_dir() and d.name.startswith("run-")),
        key=lambda d: d.name,
        reverse=True,  # run-NNN-YYYYMMDDThhmm sorts chronologically
    )
    if not run_dirs:
        raise LatestRunError(f"no run-* directories under {project_dir}")

    # Prefer the newest with a triage; remember the newest with a prime-result for fallback.
    fallback: Optional[Path] = None
    for run in run_dirs:
        candidate = run / RUN_SUBDIR if (run / RUN_SUBDIR).is_dir() else run
        if (candidate / TRIAGE_FILENAME).exists():
            return candidate
        if fallback is None and list(candidate.glob(RUN_RESULT_GLOB)):
            fallback = candidate
    if fallback is not None:
        logger.warning(
            "FDE latest-run: no run has a triage; falling back to %s (explain will degrade). "
            "Run `startd8 assist scan` first for the full composition.",
            fallback,
        )
        return fallback
    raise LatestRunError(
        f"no run under {project_dir} has a triage or prime-result*.json — "
        f"run `startd8 assist scan <run-dir>` first or pass an explicit path"
    )


def _select_project_dir(base_dir: Path, project_id: Optional[str]) -> Path:
    """Pick the project subdir under the pipeline-output base (FR-28 disambiguation)."""
    project_dirs = [d for d in base_dir.iterdir() if d.is_dir()]
    if project_id:
        match = base_dir / project_id
        if match.is_dir():
            return match
    if len(project_dirs) == 1:
        return project_dirs[0]
    if not project_dirs:
        raise LatestRunError(f"no project directories under {base_dir}")
    names = ", ".join(sorted(d.name for d in project_dirs))
    raise LatestRunError(
        f"multiple projects under {base_dir} ({names}); disambiguate with --base "
        f"<base>/<project> or an explicit run dir"
    )


# --------------------------------------------------------------------------------------
# Registry init (FR-26 / R4-S1) — must run before any LIVE preflight read.
# --------------------------------------------------------------------------------------


def ensure_registries() -> None:
    """Discover the language registry (idempotent) before LIVE preflight reads.

    Deliberately does NOT touch the providers/agents registries — the deterministic core never
    needs them, and keeping them out is what lets the Phase-6 import-guard prove this module is
    LLM-free (FR-15 / R4-S5). Provider discovery, if ever needed, belongs in ``preflight.py``.
    """
    try:
        from ..languages import LanguageRegistry

        LanguageRegistry.discover()
    except Exception:  # pragma: no cover - discovery is best-effort
        logger.debug("LanguageRegistry.discover() failed", exc_info=True)


# --------------------------------------------------------------------------------------
# Artifact trust gate (FR-18 / R1-S2)
# --------------------------------------------------------------------------------------


class ArtifactTrustError(Exception):
    """Raised when a consumed artifact is present but fails the schema/trust gate."""


def load_json_artifact(
    path: Path,
    *,
    require_keys: Tuple[str, ...] = (),
    kind: str = "artifact",
) -> Optional[Dict[str, Any]]:
    """Load + validate a consumed artifact. Returns ``None`` if absent.

    Degrade-or-fail (FR-18): a missing file is a clean ``None`` (caller degrades); a present
    but malformed/old-schema file raises :class:`ArtifactTrustError` so the caller can emit a
    labeled failure rather than a confident claim from garbage.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ArtifactTrustError(f"{kind} at {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ArtifactTrustError(f"{kind} at {path} is not a JSON object")
    missing = [k for k in require_keys if k not in data]
    if missing:
        raise ArtifactTrustError(
            f"{kind} at {path} missing required keys {missing} (schema mismatch)"
        )
    return data


# --------------------------------------------------------------------------------------
# Artifact location + evidence (FR-4) / mechanism artifacts
# --------------------------------------------------------------------------------------


def read_triage(run_output_dir: Path) -> Optional[Dict[str, Any]]:
    """Read the SA triage artifact (the EVIDENCE half, FR-4). ``None`` if absent."""
    return load_json_artifact(
        run_output_dir / TRIAGE_FILENAME,
        require_keys=("run", "verdict"),
        kind="service-assistant-triage.json",
    )


def read_triage_run_id(run_output_dir: Path) -> Optional[str]:
    """Best-effort run id from the triage artifact (no raise; for idempotency keying)."""
    try:
        triage = read_triage(run_output_dir)
    except ArtifactTrustError:
        return None
    if not triage:
        return None
    return (triage.get("run") or {}).get("run_id")


def read_postmortem(run_output_dir: Path) -> Optional[Dict[str, Any]]:
    """Read the post-mortem report (flattened element surface). ``None`` if absent."""
    return load_json_artifact(
        run_output_dir / POSTMORTEM_FILENAME,
        require_keys=("features",),
        kind="prime-postmortem-report.json",
    )


def read_raw_run_results(run_output_dir: Path) -> List[Dict[str, Any]]:
    """Read all ``prime-result*.json`` files (raw element surface; has generation_strategy)."""
    out: List[Dict[str, Any]] = []
    for p in sorted(glob.glob(str(run_output_dir / RUN_RESULT_GLOB))):
        data = load_json_artifact(Path(p), kind="prime-result*.json")
        if data is not None:
            out.append(data)
    return out


def _iter_raw_elements(run_results: List[Dict[str, Any]]):
    """Yield (feature_dict, element_dict) from the raw history nesting (OQ-2')."""
    for result in run_results:
        for entry in result.get("history", []) or []:
            gen_meta = (entry or {}).get("generation_metadata", {}) or {}
            for fr in gen_meta.get("micro_prime_file_results", []) or []:
                for er in fr.get("element_results", []) or []:
                    yield entry, er


def _find_postmortem_feature(
    postmortem: Dict[str, Any], feature_id: str
) -> Optional[Dict[str, Any]]:
    for feat in postmortem.get("features", []) or []:
        if feat.get("feature_id") == feature_id:
            return feat
    return None


def _select_elements(
    feature: Dict[str, Any], element_id: Optional[str]
) -> List[Dict[str, Any]]:
    """Feature↔element join (FR-25 / R2-S2): targeted element, or all (no silent pick-first)."""
    elements = feature.get("elements", []) or []
    if element_id:
        matched = [
            e
            for e in elements
            if e.get("element_name") == element_id or e.get("file_path") == element_id
        ]
        return matched or elements
    return elements


def _raw_strategy_for(
    run_results: List[Dict[str, Any]], element_name: str
) -> Optional[str]:
    """generation_strategy is raw-JSON-only (R2-F2) — never on ElementPostMortem."""
    for _entry, er in _iter_raw_elements(run_results):
        if (
            er.get("element_name") == element_name
            or er.get("file_path") == element_name
        ):
            strat = er.get("generation_strategy")
            if strat:
                return strat
    return None


def read_element_mechanism(
    run_output_dir: Path,
    feature_id: str,
    element_id: Optional[str] = None,
) -> List[LabeledClaim]:
    """Compose the MECHANISM half for one failure from recorded artifacts (explain mode).

    Sources, per §6:
      * tier               → ElementPostMortem.tier (recorded)
      * repair steps       → ElementPostMortem.repair_steps
      * generation_strategy → raw prime-result*.json only (NOT on the flattened surface)

    Handles double-absence (→ "mechanism unavailable") and post-mortem-vs-raw conflict
    (→ "MECHANISM (sdk, conflict)") per FR-18 / R1-F14 / R5-S3.
    """
    claims: List[LabeledClaim] = []
    try:
        postmortem = read_postmortem(run_output_dir)
    except ArtifactTrustError as exc:
        return [
            LabeledClaim(
                ClaimLabel.MECHANISM,
                str(exc),
                source=POSTMORTEM_FILENAME,
                qualifier="unavailable",
            )
        ]
    run_results = read_raw_run_results(run_output_dir)

    if postmortem is None and not run_results:
        return [
            LabeledClaim(
                ClaimLabel.MECHANISM,
                f"no recorded element data for feature '{feature_id}' "
                f"(neither {POSTMORTEM_FILENAME} nor {RUN_RESULT_GLOB} present)",
                source="(none)",
                qualifier="unavailable",
            )
        ]

    feature = _find_postmortem_feature(postmortem, feature_id) if postmortem else None
    elements = _select_elements(feature, element_id) if feature else []

    if not elements:
        # No post-mortem element rows; fall back to raw strategy only.
        strat = _raw_strategy_for(run_results, element_id or feature_id)
        if strat:
            claims.append(
                LabeledClaim(
                    ClaimLabel.MECHANISM,
                    f"generation strategy was `{strat}`",
                    source="prime-result*.json:element_results[].generation_strategy",
                    claim_id=f"{feature_id}:strategy",
                )
            )
        else:
            claims.append(
                LabeledClaim(
                    ClaimLabel.MECHANISM,
                    f"feature '{feature_id}' has no element-level mechanism record",
                    source="(none)",
                    qualifier="unavailable",
                )
            )
        return claims

    for el in elements:
        ename = el.get("element_name", "?")
        cid = f"{feature_id}:{ename}"
        tier = el.get("tier")
        if tier:
            claims.append(
                LabeledClaim(
                    ClaimLabel.MECHANISM,
                    f"element `{ename}` ran at tier **{tier}**",
                    source="ElementPostMortem.tier",
                    claim_id=f"{cid}:tier",
                )
            )
        repair_steps = el.get("repair_steps") or []
        if repair_steps:
            claims.append(
                LabeledClaim(
                    ClaimLabel.MECHANISM,
                    f"repair steps fired on `{ename}`: {', '.join(repair_steps)}",
                    source="ElementPostMortem.repair_steps",
                    claim_id=f"{cid}:repair",
                )
            )
        esc = el.get("escalation_reason")
        if esc:
            claims.append(
                LabeledClaim(
                    ClaimLabel.MECHANISM,
                    f"escalation reason for `{ename}`: {esc}",
                    source="ElementPostMortem.escalation_reason",
                    claim_id=f"{cid}:escalation",
                )
            )
        # generation_strategy — raw-only; report unavailable if missing (R2-F2)
        strat = _raw_strategy_for(run_results, ename)
        if strat:
            claims.append(
                LabeledClaim(
                    ClaimLabel.MECHANISM,
                    f"generation strategy was `{strat}`",
                    source="prime-result*.json:element_results[].generation_strategy",
                    claim_id=f"{cid}:strategy",
                )
            )
        elif run_results:
            claims.append(
                LabeledClaim(
                    ClaimLabel.MECHANISM,
                    f"generation strategy for `{ename}` not recorded on the available surface",
                    source="prime-result*.json",
                    qualifier="unavailable",
                    claim_id=f"{cid}:strategy",
                )
            )
        else:
            # post-mortem present but raw absent: template_used is a partial proxy only
            tused = el.get("template_used")
            claims.append(
                LabeledClaim(
                    ClaimLabel.MECHANISM,
                    f"generation strategy for `{ename}` unavailable on the flattened post-mortem "
                    f"surface (template_used={tused}; raw prime-result*.json absent)",
                    source="ElementPostMortem.template_used",
                    qualifier="unavailable",
                    claim_id=f"{cid}:strategy",
                )
            )
    return claims


# --------------------------------------------------------------------------------------
# LIVE mechanism (preflight) — labeled PREDICTION (FR-16 / FR-21)
# --------------------------------------------------------------------------------------


def classify_live(signals: Any) -> Tuple[Optional[Any], Optional[LabeledClaim]]:
    """Run the complexity classifier live. Returns (ClassificationResult, PREDICTION claim)."""
    try:
        from ..complexity.classifier import classify_tier
    except Exception:  # pragma: no cover
        return None, None
    result = classify_tier(signals)
    tier = getattr(getattr(result, "tier", None), "value", None) or str(
        getattr(result, "tier", "?")
    )
    reason = getattr(result, "reason", "")
    claim = LabeledClaim(
        ClaimLabel.PREDICTION,
        f"would classify as tier **{tier}** — {reason}",
        source="complexity.classify_tier() → ClassificationResult",
    )
    return result, claim


def resolve_model_by_tier(provider: str, tier: str = "balanced") -> LabeledClaim:
    """Model that *would* run for a provider/tier (preflight). Label PREDICTION."""
    try:
        from ..model_catalog import get_latest_model

        model = get_latest_model(provider, tier=tier)
    except Exception:  # pragma: no cover
        model = None
    if model:
        return LabeledClaim(
            ClaimLabel.PREDICTION,
            f"tier `{tier}` on `{provider}` resolves to model `{model}`",
            source="model_catalog.get_latest_model(provider, tier)",
        )
    return LabeledClaim(
        ClaimLabel.PREDICTION,
        f"no model resolved for provider `{provider}` tier `{tier}`",
        source="model_catalog.get_latest_model",
        qualifier="unavailable",
    )


def resolve_model_by_role(role: str) -> LabeledClaim:
    """Contractor-role model(s) that would run (DRAFT/VALIDATE/REVIEW). Label PREDICTION."""
    try:
        from ..contractors.protocols import ModelRole, get_models_by_role

        models = get_models_by_role(ModelRole[role.upper()])
        specs = [getattr(m, "agent_spec", str(m)) for m in models]
    except Exception:  # pragma: no cover
        specs = []
    if specs:
        return LabeledClaim(
            ClaimLabel.PREDICTION,
            f"role `{role}` maps to: {', '.join(specs)}",
            source="contractors.protocols.get_models_by_role() / ModelCatalogEntry.agent_spec",
        )
    return LabeledClaim(
        ClaimLabel.PREDICTION,
        f"no models registered for role `{role}`",
        source="contractors.protocols.get_models_by_role",
        qualifier="unavailable",
    )


def language_capability(language_id: str) -> LabeledClaim:
    """Whether/how the SDK supports a language (preflight). Label PREDICTION."""
    try:
        from ..languages import LanguageRegistry

        profile = LanguageRegistry.get(language_id)
    except Exception:
        profile = None
    if profile is None:
        return LabeledClaim(
            ClaimLabel.PREDICTION,
            f"language `{language_id}` is not supported by the SDK",
            source="languages.LanguageRegistry.get",
            qualifier="unavailable",
        )
    repair = getattr(profile, "repair_enabled", None)
    return LabeledClaim(
        ClaimLabel.PREDICTION,
        f"language `{language_id}` is supported (repair_enabled={repair})",
        source="languages.LanguageRegistry.get(language_id)",
    )
