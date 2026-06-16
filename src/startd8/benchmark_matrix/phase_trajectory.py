"""Multi-phase judging — Tier-A compile-gate trajectory over persisted DRAFT artifacts.

The benchmark makes ~8 LLM calls per feature (spec → draft×N → review×N → integration) but
judges exactly one artifact per cell: the final, integrated on-disk file. The intermediate
``draft-1 … draft-N`` artifacts are full, self-contained code in the same language, already
persisted under each cell's sandbox ``.startd8/.../generated/.artifacts/``, and are discarded
ungraded. This module re-runs the **existing compile gate** on every draft — a **$0** re-score of
already-persisted artifacts (Mottainai: generate once, re-score free) — and derives a per-feature
**compile trajectory** plus refinement metrics.

Tier A only (per the requirements/plan, v0.3): the readily-judgeable per-draft signal is the
**compile verdict** (``compile_ok`` / ``degraded``), NOT a quality/structural score. ``score_file``
reuses a *stored* structural score that drafts don't have, so its composite ``.value`` is
meaningless for a draft and is deliberately ignored here. A per-draft structural/quality score is
Tier B (deferred). See:
- ``docs/design/benchmark-scoring/MULTIPHASE_JUDGING_READILY_JUDGEABLE_REQUIREMENTS.md`` (v0.3)
- ``docs/design/benchmark-scoring/MULTIPHASE_JUDGING_READILY_JUDGEABLE_PLAN.md`` (v1.0)

The output is an **advisory, non-ranking** sidecar (FR-10): the trajectory never enters
``CellResult`` / ``aggregate_cells``, so it cannot move the leaderboard. The CLI
``scripts/rescore_phase_trajectory.py`` writes ``phase-trajectory.json`` keyed by ``cell_id``.

This mirrors :func:`startd8.benchmark_matrix.rescore.rescore_run`'s cell loop, adding a per-feature
inner loop over the draft artifacts.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .runner import CellResult, sandbox_dir_name
from .sandbox import SandboxConfig
from .scoring import score_file

CELLS_FILE = "cells.json"
SANDBOXES_DIR = "sandboxes"
TRAJECTORY_FILE = "phase-trajectory.json"

# Persisted per-feature artifacts live UNDER the hidden ``.startd8`` dir. NOTE: Python glob's ``**``
# skips dotted path components, so a ``glob('**/.artifacts/*-draft-*.md')`` silently finds nothing —
# we walk explicitly (FR-1 / plan D-FR1).
_ARTIFACTS_SUBPATH = (".startd8", "benchmark-output", "generated", ".artifacts")

# ``<Feature>__<lang>__…-draft-<N>.md`` — capture the iteration index N; the feature key is the
# filename prefix before ``-draft-``.
_DRAFT_RE = re.compile(r"-draft-(\d+)\.md$")

# Canonical fallback extension per language_id, when the seed's target_files don't give one.
_FALLBACK_EXT = {
    "python": ".py",
    "go": ".go",
    "nodejs": ".js",
    "java": ".java",
    "csharp": ".cs",
}


def build_phase_trajectory(run_dir, seeds_dir, *, cfg: Optional[SandboxConfig] = None) -> dict:
    """Build the Tier-A compile-gate trajectory for every cell of a completed benchmark run.

    Mirrors :func:`rescore.rescore_run`'s loop: load ``cells.json``, resolve each cell's sandbox
    with the FULL coordinate (leverage / lead / drafter), then — instead of re-scoring the single
    final file — locate the per-feature ``*-draft-*.md`` artifacts and run the **compile gate** on
    each one ($0, no LLM, no network).

    Args:
        run_dir: a benchmark run directory (holds ``cells.json`` + ``sandboxes/``).
        seeds_dir: the OB seeds dir — used to resolve each service's language + target extension.
        cfg: sandbox config for the compile gate (defaults to a no-network config).

    Returns a dict ``{cells: {cell_id: {...}}, coverage: {...}}``. Pure read — never writes, never
    raises on a cell with no draft artifacts (FR-9: such cells are marked ``"not computed"``).
    """
    from ..languages import LanguageRegistry

    run_dir = Path(run_dir)
    seeds_dir = Path(seeds_dir)
    cells_path = run_dir / CELLS_FILE
    if not cells_path.exists():
        raise FileNotFoundError(f"no {CELLS_FILE} in {run_dir}")

    raw = json.loads(cells_path.read_text(encoding="utf-8"))
    cells = [CellResult.from_dict(d) for d in raw]
    LanguageRegistry.discover()

    if cfg is None:
        cfg = SandboxConfig(no_network=True)

    out_cells: Dict[str, dict] = {}
    computed = not_computed = 0

    for c in cells:
        # Resolve the cell's workdir with its FULL coordinate — leverage (K2) and lead/drafter (K3)
        # are part of sandbox_dir_name; omitting them would miss off-diagonal sandboxes (mirrors
        # rescore.rescore_run's R3-S4 / R6-S4 round-trip requirement).
        sandbox = run_dir / SANDBOXES_DIR / sandbox_dir_name(
            c.service, c.model, c.repetition,
            leverage=getattr(c, "leverage", "off"),
            lead=getattr(c, "lead", None), drafter=getattr(c, "drafter", None))

        feature_drafts = _discover_draft_artifacts(sandbox)
        if not feature_drafts:
            # FR-9: no persisted drafts (infra_fail / early-fail / older run) — never raise.
            out_cells[c.cell_id] = {"features": [], "rollup": {}, "status": "not computed"}
            not_computed += 1
            continue

        lang_id, ext = _resolve_language_and_ext(seeds_dir, c.service, feature_drafts)
        profile = LanguageRegistry.get(lang_id) if lang_id else None

        features: List[dict] = []
        for feature_key, drafts in feature_drafts:
            features.append(_score_feature(feature_key, drafts, profile, ext, c, cfg))

        out_cells[c.cell_id] = {
            "features": features,
            "rollup": _rollup(features),
            "status": "computed",
        }
        computed += 1

    return {
        "cells": out_cells,
        "coverage": {
            "computed": computed,
            "total": len(cells),
            "not_computed": not_computed,
        },
    }


def _discover_draft_artifacts(sandbox: Path) -> List[Tuple[str, List[Tuple[int, Path]]]]:
    """Enumerate ``*-draft-*.md`` artifacts under the cell's hidden ``.artifacts`` dir (FR-1).

    Uses ``os.walk`` (not glob ``**``, which skips dotdirs). Returns a list of
    ``(feature_key, [(n, path), …])`` ordered by feature key, drafts ordered by the integer N.
    """
    art_dir = sandbox.joinpath(*_ARTIFACTS_SUBPATH)
    if not art_dir.is_dir():
        return []

    groups: Dict[str, List[Tuple[int, Path]]] = {}
    for dirpath, _dirnames, filenames in os.walk(art_dir):
        for fn in filenames:
            m = _DRAFT_RE.search(fn)
            if not m:
                continue
            feature_key = fn[: m.start()]
            n = int(m.group(1))
            groups.setdefault(feature_key, []).append((n, Path(dirpath) / fn))

    result: List[Tuple[str, List[Tuple[int, Path]]]] = []
    for feature_key in sorted(groups):
        drafts = sorted(groups[feature_key], key=lambda t: t[0])
        result.append((feature_key, drafts))
    return result


def _resolve_language_and_ext(seeds_dir: Path, service: str,
                              feature_drafts: List[Tuple[str, List[Tuple[int, Path]]]]
                              ) -> Tuple[Optional[str], str]:
    """Resolve (language_id, canonical extension) for a cell's drafts.

    Language comes from the **artifact NAME** (``<Feature>__<lang>__…``) first — the language the
    feature was generated in — falling back to the seed's recorded language; NOT from the ``.md``
    path (D6). The extension comes from the seed's ``target_files`` (the exact file the model wrote),
    falling back to a per-language canonical extension.
    """
    seed = _load_seed(seeds_dir, service)
    seed_lang = _seed_language(seed)

    name_lang = None
    if feature_drafts:
        name_lang = _language_from_artifact_name(feature_drafts[0][0])

    lang_id = name_lang or seed_lang

    ext = _seed_target_extension(seed)
    if not ext:
        ext = _FALLBACK_EXT.get((lang_id or "").lower(), ".txt")
    return lang_id, ext


def _language_from_artifact_name(feature_key: str) -> Optional[str]:
    """Extract the language token from ``<Feature>__<lang>__…`` (the 2nd ``__``-delimited token)."""
    tokens = [t for t in feature_key.split("__") if t]
    if len(tokens) >= 2:
        return tokens[1].lower()
    return None


def _load_seed(seeds_dir: Path, service: str) -> dict:
    seed_path = Path(seeds_dir) / f"seed-{service}.json"
    if not seed_path.exists():
        return {}
    try:
        return json.loads(seed_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _seed_language(seed: dict) -> Optional[str]:
    lang = (seed.get("service_metadata") or {}).get("language")
    if lang:
        return str(lang).lower()
    tasks = seed.get("tasks") or []
    if tasks:
        ctx = (tasks[0].get("config", {}) or {}).get("context", {}) or {}
        if ctx.get("language"):
            return str(ctx["language"]).lower()
    return None


def _seed_target_extension(seed: dict) -> str:
    tasks = seed.get("tasks") or []
    if not tasks:
        return ""
    targets = ((tasks[0].get("config", {}) or {}).get("context", {}) or {}).get("target_files") or []
    if not targets:
        return ""
    return os.path.splitext(targets[0])[1]


def _score_feature(feature_key: str, drafts: List[Tuple[int, Path]], profile, ext: str,
                   cell: CellResult, cfg: SandboxConfig) -> dict:
    """Compile-gate every draft of one feature and derive the per-feature metrics."""
    draft_points: List[dict] = []
    for n, path in drafts:
        compiles, degraded = _compile_judge_draft(path, profile, ext, cfg)
        draft_points.append({"n": n, "compiles": compiles, "degraded": degraded})

    # FR-4 endpoint: reuse the STORED final compile_ok (do not recompute the final — D8).
    final_compiles = _final_compiles(cell)

    compile_flags = [d["compiles"] for d in draft_points]

    # FR-5a universal (N>=1)
    first_draft_compiles = bool(compile_flags[0]) if compile_flags else None

    feature: dict = {
        "feature": feature_key,
        "drafts": draft_points,
        "final_compiles": final_compiles,
        "first_draft_compiles": first_draft_compiles,
    }

    # FR-5b refinement subsample (cells/features with >=2 drafts)
    if len(compile_flags) >= 2:
        feature["iterations_to_first_compile"] = _iterations_to_first_compile(compile_flags)
        feature["compile_convergence"] = _compile_convergence(compile_flags)
        feature["monotonicity"] = _monotonicity(compile_flags)
    else:
        # Universal field still reported for the single-draft case (1-based, or None if it never
        # compiles) — keeps the headline metric available without claiming a convergence curve.
        feature["iterations_to_first_compile"] = (
            1 if (compile_flags and compile_flags[0]) else None)

    return feature


def _compile_judge_draft(path: Path, profile, ext: str, cfg: SandboxConfig) -> Tuple[bool, bool]:
    """Write a draft's bytes to a temp file with the language's canonical extension, run the
    EXISTING compile gate (``score_file`` with ``structural=None``), and return (compiles, degraded).

    Only ``comp.compile_ok`` + ``comp.degraded`` are read (FR-2). "compiles" treats a genuine
    ``compile_ok is False`` as not compiling; ``True`` OR a degrade (missing toolchain/deps) counts
    as compiles/excused — exactly how the final scorer's compile term distinguishes a model fault
    from an absent-dependency degrade (FR-3).
    """
    data = path.read_bytes()
    tmpdir = tempfile.mkdtemp(prefix="phasetraj-")
    try:
        tmp = Path(tmpdir) / f"draft{ext or '.txt'}"
        tmp.write_bytes(data)
        if profile is None:
            # No resolvable language profile → no compile gate → degrade (excused), don't floor.
            return True, True
        comp = score_file(tmp, profile, cfg=cfg, structural=None)
        compiles = comp.compile_ok is not False  # True or None(degraded) → compiles/excused
        return bool(compiles), bool(comp.degraded)
    finally:
        try:
            for child in Path(tmpdir).iterdir():
                child.unlink()
        except OSError:
            pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


def _final_compiles(cell: CellResult) -> Optional[bool]:
    """The cell's stored final compile verdict (FR-4 endpoint). ``compile_ok`` is ``None`` when the
    final degraded (toolchain/deps absent) — treat that as compiles/excused, matching the draft
    convention; only a stored ``False`` is "not compiling"."""
    if cell.compile_ok is False:
        return False
    if cell.compile_ok is True:
        return True
    # None: degraded or never gated. Treat a degraded final as excused/compiles, otherwise unknown.
    if getattr(cell, "degraded", False):
        return True
    return None


def _iterations_to_first_compile(compile_flags: List[bool]) -> Optional[int]:
    """1-based index of the first compiling draft, or None if none compiled."""
    for i, ok in enumerate(compile_flags):
        if ok:
            return i + 1
    return None


def _compile_convergence(compile_flags: List[bool]) -> bool:
    """Did the chain go non-compiling → compiling across iterations (FR-5b)?"""
    saw_broken = False
    for ok in compile_flags:
        if not ok:
            saw_broken = True
        elif saw_broken:
            return True
    return False


def _monotonicity(compile_flags: List[bool]) -> float:
    """Fraction of adjacent steps that did NOT regress compiling → broken (FR-5b).

    A step counts as a regression only when it goes from compiling (True) to broken (False).
    1.0 when there are no adjacent pairs (vacuously non-regressing)."""
    pairs = list(zip(compile_flags, compile_flags[1:]))
    if not pairs:
        return 1.0
    non_regress = sum(1 for prev, cur in pairs if not (prev and not cur))
    return round(non_regress / len(pairs), 4)


def _rollup(features: List[dict]) -> dict:
    """Per-cell rollup over per-feature trajectories (FR-7). Mean of ``first_draft_compiles`` as a
    rate (OB cells are mostly single-feature), plus the max draft chain length seen."""
    fdc = [1.0 if f.get("first_draft_compiles") else 0.0
           for f in features if f.get("first_draft_compiles") is not None]
    finals = [1.0 if f.get("final_compiles") else 0.0
              for f in features if f.get("final_compiles") is not None]
    n_drafts_max = max((len(f.get("drafts") or []) for f in features), default=0)
    rollup: dict = {"n_features": len(features), "n_drafts_max": n_drafts_max}
    if fdc:
        rollup["first_draft_compiles"] = round(sum(fdc) / len(fdc), 4)
    if finals:
        rollup["final_compiles"] = round(sum(finals) / len(finals), 4)
    return rollup
