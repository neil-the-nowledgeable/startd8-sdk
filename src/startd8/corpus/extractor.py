"""Corpus extractor — turn one run's postmortem into corpus term observations (FR-5/7/11).

Runs at the postmortem alongside exemplar extraction. For each feature it emits a
file-kind TermObservation carrying the target_file binding + the two determinism axes
(success, requirement_score). The drifting feature title is captured as a surface_form.

Features with no target_files are skipped (the positional PI-id noise documented in
CORPUS_V0_FINDINGS) rather than keyed on a meaningless id.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.corpus.canonical import canonical_key
from startd8.corpus.models import Binding, TermObservation
from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["extract_corpus_from_run", "extract_seed_terms_from_context",
           "stable_run_id", "input_scope_id_for", "seed_source_checksum"]

# requirement-doc pseudo-services in service_communication_graph (not real services)
_PSEUDO_SVC = re.compile(r"^req|guidance|servicelevelobjectives|servicedashboard|servicemonitor",
                         re.IGNORECASE)

_EXT_LANG = {
    ".py": "python", ".go": "go", ".js": "nodejs", ".ts": "nodejs", ".mjs": "nodejs",
    ".cjs": "nodejs", ".java": "java", ".cs": "csharp", ".html": "html",
    ".proto": "proto", ".yaml": "config", ".yml": "config", ".json": "config",
    ".in": "config", ".txt": "config",
}


def _language_for(path: str) -> str:
    return _EXT_LANG.get(Path(path).suffix.lower(), "unknown")


def stable_run_id(output_dir: str, fallback: str = "") -> str:
    """Derive a STABLE run id from the output dir (idempotency: re-running the
    postmortem on the same dir must not double-count). Prefer a ``run-*`` ancestor."""
    p = Path(output_dir).resolve()
    for cand in (p, *p.parents):
        if cand.name.startswith("run-") or cand.name.startswith("gemini-"):
            return cand.name
    return p.name or fallback or "unknown-run"


def input_scope_id_for(report: Any) -> str:
    """R4-F1: scope cluster id for determinism — runs of different scope (feature count)
    must not share a stability aggregate. Derived from the postmortem's feature count."""
    n = getattr(report, "total_features", None)
    return f"feat{n}" if n else ""


def extract_corpus_from_run(report: Any, run_id: str) -> List[TermObservation]:
    """Build file-kind TermObservations from a PrimePostMortemReport's features (FR-5/7)."""
    scope = input_scope_id_for(report)
    obs: List[TermObservation] = []
    for fpm in getattr(report, "features", []) or []:
        target_files = getattr(fpm, "target_files", None) or []
        if not target_files:
            continue  # skip positional-id noise (no real binding to key on)
        surface = getattr(fpm, "name", "") or ""
        success = bool(getattr(fpm, "success", False))
        req = getattr(fpm, "requirement_score", None)
        # R2-S4: emit one observation per target_file (multi-file features keep all targets).
        for target in target_files:
            obs.append(TermObservation(
                kind="file",
                canonical_key=canonical_key("file", surface, target),
                surface_form=surface,
                # R2-F1: confidence is binding PROVENANCE, NOT a runtime quality score.
                bindings=[Binding(language=_language_for(target), construct_kind="file",
                                  construct_ref=target, source_reference="deterministic")],
                confidence="inferred",
                success=success,
                requirement_score=req,
                input_scope_id=scope,
            ))
    return obs


def _find_seed(output_dir: str) -> Optional[str]:
    """Latest-by-name prime-context-seed*.json under output_dir (same rule as the SCR)."""
    pats = [str(Path(output_dir) / "prime-context-seed*.json"),
            str(Path(output_dir) / "plan-ingestion" / "prime-context-seed*.json")]
    hits = sorted({p for pat in pats for p in glob.glob(pat)})
    return hits[-1] if hits else None


def seed_source_checksum(output_dir: str) -> Optional[str]:
    """The run's input source_checksum from its seed — the durable content-store key (FR-9)."""
    seed_path = _find_seed(output_dir)
    if not seed_path:
        return None
    try:
        return json.load(open(seed_path, encoding="utf-8")).get("source_checksum")
    except (OSError, json.JSONDecodeError):
        return None


def extract_seed_terms_from_context(output_dir: str, run_id: str) -> List[TermObservation]:
    """R4-S1: grow the VOCABULARY layer (services/rpcs) from each run's seed — not just
    bootstrap. Reads prime-context-seed.json's service graph. Vocabulary terms carry no
    determinism (they are names, not file outcomes); recurrence validates them (caps L2).
    """
    seed_path = _find_seed(output_dir)
    if not seed_path:
        return []
    try:
        seed = json.load(open(seed_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    obs: List[TermObservation] = []
    services = ((seed.get("service_communication_graph") or {}).get("services") or {})
    names = services.keys() if isinstance(services, dict) else services
    for name in names or []:
        if not isinstance(name, str) or _PSEUDO_SVC.search(name):
            continue  # skip requirement-doc pseudo-services
        obs.append(TermObservation(
            kind="service", canonical_key=canonical_key("service", name), surface_form=name,
            bindings=[Binding(language="proto", construct_kind="service",
                              construct_ref=name, source_reference="proto")],
            confidence="inferred"))
    return obs
