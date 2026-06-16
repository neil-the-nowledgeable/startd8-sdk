"""Combined (cross-run) scorecard renderer — M3 (CS-1/2/10/12/13).

``build_combined_scorecard(run_dirs)`` merges cells across runs (M1 ``merge_runs``) and renders ONE
scorecard in the v2.0 format, **reusing the per-run section renderers** (``scorecard.py``) over the
merged cell set — so the layout, ranking, and degrade-honesty are identical to a single-run scorecard.
It adds two cross-run sections the per-run card can't have: a **Provenance** section (where each model's
canonical cells came from, CS-2) and a **calibration annex** (the excluded other-method runs, CS-13).

Contamination (credibility) is merged **provenance-aware**: a run's CodeBLEU is shown only for the
``(service, model)`` pairs whose quality that run actually supplied — so e.g. an OpenAI re-run that
superseded the original's quality but was never contamination-probed shows a coverage gap, not the
original run's (different) outputs.

$0, deterministic. Markdown + self-contained HTML. ``run_dirs`` are passed most-canonical first
(anchor first) — see ``merge_runs``.
"""
from __future__ import annotations

import hashlib
import json
import statistics as _st
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from . import scorecard as _sc  # reuse the v2.0 renderers (markdown _*_section + HTML _h_*)
from .aggregate import aggregate_cells, rank_models_by_consistency
from .combined import MergeResult, RunInfo, merge_runs

CONTAMINATION_FILE = "contamination-probe.json"
COMBINED_MANIFEST = "combined-manifest.json"
MANIFEST_SCHEMA_VERSION = "1.0"


def _merge_for(dirs, *, align: bool, seeds_dir) -> MergeResult:
    """Run the M1 merge, optionally preceded by the M2 method-alignment step (CS-15).

    With ``align``, sandbox-bearing inputs behind the target method are re-scored to current ($0,
    non-destructive) and their aligned cells supplied to the merge via ``prealigned`` — while
    ``merge_runs`` stays the single authority for inclusion/exclusion (so the annex still lists
    excluded calibration runs). With current same-method inputs, alignment is a no-op.
    """
    if not align:
        return merge_runs(dirs)
    if seeds_dir is None:
        raise ValueError("align=True requires seeds_dir (forwarded to rescore_run)")
    from .combined_align import align_runs

    ares = align_runs(dirs, seeds_dir)
    prealigned = {inp.run_dir.name: inp.cells for inp in ares.inputs if inp.cells is not None}
    return merge_runs(dirs, prealigned=prealigned)
COMBINED_MD = "COMBINED_SCORECARD.md"
COMBINED_HTML = "COMBINED_SCORECARD.html"


# --------------------------------------------------------------------------- contamination merge
def _merge_contamination(
    runs: List[RunInfo], dir_by_name: Dict[str, Path], merged: MergeResult
) -> Optional[dict]:
    """Concatenate contamination cells from included runs, restricted to the (service, model) pairs
    each run won in the quality merge (provenance-aware)."""
    won: Dict[str, set] = {}
    for (svc, model, _rep), p in merged.provenance.items():
        won.setdefault(p.winner_run, set()).add((svc, model))

    cells: list = []
    ref_root = None
    for r in runs:
        if not r.included:
            continue
        try:
            probe = json.loads((dir_by_name[r.run] / CONTAMINATION_FILE).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a run without a probe just contributes nothing (CS-10)
            continue
        ref_root = ref_root or probe.get("reference_root")
        won_pairs = won.get(r.run, set())
        for c in probe.get("cells", []):
            if (c.get("service"), c.get("model")) in won_pairs:
                cells.append(c)
    if not cells:
        return None
    scored = [c for c in cells if c.get("available") and c.get("codebleu") is not None]
    return {"reference_root": ref_root, "n_cells": len(cells), "n_scored": len(scored), "cells": cells}


# --------------------------------------------------------------------------- combined headline/header
def _combined_headline(agg: Optional[dict]) -> str:
    """CS-9: lead by the reliability lens (pass-rate, then tightest IQR), not median alone."""
    if not agg:
        return "no scores computed."
    ranked = rank_models_by_consistency(agg)
    flags = [row for row in ranked if row[0] in _sc.FLAGSHIP_MODELS]
    pick = (flags or ranked)
    if not pick:
        return "no scores computed."
    lead = pick[0][0]
    s = agg["by_model"][lead]
    scope = "flagship" if lead in _sc.FLAGSHIP_MODELS else "overall"
    return (
        f"`{lead}` leads the {scope} board on reliability — pass-rate {_sc._f(s['pass_rate'])}, "
        f"IQR {_sc._f(s['quality_iqr'])}, median quality {_sc._f(s['quality_median'])}."
    )


def _combined_header(merged: MergeResult, agg: Optional[dict], now: datetime) -> str:
    inc, exc = merged.included_runs, merged.excluded_runs
    n_models = len(agg["by_model"]) if agg else 0
    inputs = " + ".join(f"{r.run}({'anchor' if r.reason == 'anchor' else 'match'})" for r in inc)
    excl = f" · excluded: {', '.join(r.run for r in exc)}" if exc else ""
    lines = [
        "# Combined Scoreboard — Summer 2026 (consolidated)",
        f"consolidated {now.strftime('%Y-%m-%dT%H:%MZ')} · method **{merged.anchor_method}** · $0 (no LLM)",
        f"inputs: {inputs}{excl}",
        f"coverage: {n_models} models · {len(merged.cells)} canonical cells from {len(inc)} run(s)",
        "",
        f"**Headline:** {_combined_headline(agg)}",
        "",
        "> Consolidated by `merge_runs` (M1): per `(service, model, rep)`, a scored `ok` cell beats a",
        "> scoreless one; ties break by input priority. Only same-scoring-method runs merge (CS-5);",
        "> calibration/other-method runs are excluded (see the annex). Every dimension below is",
        "> degrade-honest — marked `not computed` where its source is absent (FR-32).",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- new cross-run sections
def _provenance_section(merged: MergeResult) -> str:
    by_model: Dict[str, Dict[str, int]] = {}
    for (_svc, model, _rep), p in merged.provenance.items():
        by_model.setdefault(model, {})
        by_model[model][p.winner_run] = by_model[model].get(p.winner_run, 0) + 1
    rows = [
        "## Provenance — canonical cell sources",
        "> Where each model's canonical cells came from (CS-2). Inclusion decisions + warnings follow.",
        "",
        "| Model | sources (cells) |",
        "|---|---|",
    ]
    for m in sorted(by_model):
        src = ", ".join(f"`{r}`: {n}" for r, n in sorted(by_model[m].items(), key=lambda x: -x[1]))
        rows.append(f"| `{m}` | {src} |")
    rows += ["", "**Inputs:**"]
    for r in merged.runs:
        tag = "✅ included" if r.included else "⊘ excluded"
        rows.append(
            f"- `{r.run}` — {tag} · {r.signature.scoring_method} ({r.signature.source}) · {r.reason}"
        )
    if merged.warnings:
        rows += ["", "**Warnings:** " + "; ".join(merged.warnings)]
    return "\n".join(rows)


def _calibration_annex(merged: MergeResult) -> str:
    lines = [
        "## Annex — methodology evolution (NOT the ranking)",
        "> The calibration phase (naive harness → shadow+expose) validated the measurement before the",
        "> scored round. Calibration / other-method runs are **excluded from the ranking above** (CS-6);",
        "> listed here for provenance only.",
        "",
    ]
    excl = merged.excluded_runs
    if excl:
        for r in excl:
            lines.append(f"- `{r.run}` — {r.signature.scoring_method} · {r.reason}")
    else:
        lines.append("- (no calibration / other-method runs among the inputs)")
    return "\n".join(lines)


# --------------------------------------------------------------------------- markdown
def build_combined_scorecard(run_dirs, *, now: Optional[datetime] = None,
                             align: bool = False, seeds_dir=None) -> str:
    now = now or datetime.now(timezone.utc)
    dirs = [Path(d) for d in run_dirs]
    dir_by_name = {d.name: d for d in dirs}
    merged = _merge_for(dirs, align=align, seeds_dir=seeds_dir)
    cells = merged.cells
    agg = aggregate_cells(cells) if cells else None
    contam = _merge_contamination(merged.runs, dir_by_name, merged)

    sections = [
        _combined_header(merged, agg, now),
        _sc._scoreboard_section(agg),         # A — scores first
        _sc._consistency_section(agg),        # B
        _sc._credibility_section(contam),     # C
        _sc._behavioral_section(cells),       # D
        _sc._determinism_section(None),       # E (N/A for OB — present, degrade-honest)
        _sc._by_language_section(agg, contam),  # F
        _provenance_section(merged),          # + provenance (cross-run)
        _calibration_annex(merged),           # + annex (CS-13)
    ]
    cov = _sc._coverage_notes(contam, cells)
    if cov:
        sections.append(cov)
    return "\n\n".join(s for s in sections if s) + "\n"


def write_combined_scorecard(run_dirs, out_dir, *, now: Optional[datetime] = None,
                             align: bool = False, seeds_dir=None) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / COMBINED_MD
    path.write_text(build_combined_scorecard(run_dirs, now=now, align=align, seeds_dir=seeds_dir),
                    encoding="utf-8")
    return path


# --------------------------------------------------------------------------- manifest (M4 / CS-11)
def _sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:  # noqa: BLE001 - a missing input file is recorded as null, not a crash
        return None


def _cell_key_str(key) -> str:
    svc, model, rep = key
    return f"{svc}|{model}|r{rep}"


def build_combined_manifest(run_dirs, *, now: Optional[datetime] = None,
                            align: bool = False, seeds_dir=None) -> dict:
    """Content-addressed provenance manifest for a consolidated board (CS-11 / FR-40).

    Records every input run's method signature + the SHA-256 of the exact ``cells.json`` consumed, the
    supersedence winner (and losers) for every cell key, and the coverage summary. Deterministic given
    the same inputs (+ injected ``now``) — the integrity twin of the board.
    """
    now = now or datetime.now(timezone.utc)
    dirs = [Path(d) for d in run_dirs]
    dir_by_name = {d.name: d for d in dirs}
    merged = _merge_for(dirs, align=align, seeds_dir=seeds_dir)

    inputs = []
    for r in merged.runs:
        d = dir_by_name.get(r.run)
        sha = _sha256(d / r.cells_file) if (d is not None and r.cells_file.endswith(".json")) else None
        inputs.append({
            "run": r.run,
            "included": r.included,
            "reason": r.reason,
            "scoring_method": r.signature.scoring_method,
            "signature_source": r.signature.source,
            "sdk_version": r.signature.sdk_version,
            "cells_file": r.cells_file,
            "n_cells": r.n_cells,
            "cells_sha256": sha,
        })

    winners = {}
    for key in sorted(merged.provenance, key=_cell_key_str):
        p = merged.provenance[key]
        winners[_cell_key_str(key)] = {
            "winner_run": p.winner_run,
            "winner_cell_id": p.winner_cell_id,
            "status": p.winner_status,
            "reason": p.reason,
            "losers": [{"run": rn, "cell_id": cid, "status": st} for rn, cid, st in p.losers],
        }

    status_mix = Counter(c.status for c in merged.cells)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_utc": now.strftime("%Y-%m-%dT%H:%MZ"),
        "anchor_method": merged.anchor_method,
        "anchor_parity": list(merged.anchor_parity),
        "coverage": {
            "canonical_cells": len(merged.cells),
            "models": len({k[1] for k in merged.provenance}),
            "status_breakdown": dict(sorted(status_mix.items())),
            "included_runs": len(merged.included_runs),
            "excluded_runs": len(merged.excluded_runs),
        },
        "inputs": inputs,
        "cell_winners": winners,
        "warnings": list(merged.warnings),
    }


def write_combined_manifest(run_dirs, out_dir, *, now: Optional[datetime] = None,
                            align: bool = False, seeds_dir=None) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / COMBINED_MANIFEST
    manifest = build_combined_manifest(run_dirs, now=now, align=align, seeds_dir=seeds_dir)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- HTML
def _h_provenance(merged: MergeResult) -> str:
    by_model: Dict[str, Dict[str, int]] = {}
    for (_svc, model, _rep), p in merged.provenance.items():
        by_model.setdefault(model, {})
        by_model[model][p.winner_run] = by_model[model].get(p.winner_run, 0) + 1
    rows = []
    for m in sorted(by_model):
        src = ", ".join(f"{_sc._esc(r)}: {n}" for r, n in sorted(by_model[m].items(), key=lambda x: -x[1]))
        rows.append(f"<tr><td>{_sc._esc(m)}</td><td>{src}</td></tr>")
    table = _sc._h_table(["Model", "sources (cells)"], rows)
    inputs = "".join(
        f"<li>{'✅' if r.included else '⊘'} <code>{_sc._esc(r.run)}</code> — "
        f"{_sc._esc(r.signature.scoring_method)} ({_sc._esc(r.signature.source)}) · {_sc._esc(r.reason)}</li>"
        for r in merged.runs
    )
    warn = ("<p class=note>⚠️ " + "; ".join(_sc._esc(w) for w in merged.warnings) + "</p>") if merged.warnings else ""
    return table + f"<ul class=note>{inputs}</ul>{warn}"


def _h_annex(merged: MergeResult) -> str:
    excl = merged.excluded_runs
    if not excl:
        items = "<li>(no calibration / other-method runs among the inputs)</li>"
    else:
        items = "".join(
            f"<li><code>{_sc._esc(r.run)}</code> — {_sc._esc(r.signature.scoring_method)} · {_sc._esc(r.reason)}</li>"
            for r in excl
        )
    return (
        "<p class=note>The calibration phase (naive → shadow+expose) validated the measurement before "
        "the scored round. These runs are excluded from the ranking above (CS-6); shown for provenance.</p>"
        f"<ul class=note>{items}</ul>"
    )


def _combined_header_html(merged: MergeResult, agg: Optional[dict], now: datetime) -> str:
    inc, exc = merged.included_runs, merged.excluded_runs
    n_models = len(agg["by_model"]) if agg else 0
    chips = "".join(
        f'<span class=chip>{_sc._esc(r.run)} <b>{"anchor" if r.reason == "anchor" else "match"}</b></span>'
        for r in inc
    )
    if exc:
        chips += "".join(f'<span class=chip>{_sc._esc(r.run)} <b>excluded</b></span>' for r in exc)
    return (
        '<p class=kicker>Summer 2026 · consolidated</p>'
        '<h1>Combined <span class=accent>Scoreboard</span></h1>'
        '<div class=rule></div>'
        f'<div class=prov>{chips}'
        f'<span class=chip>method <b>{_sc._esc(merged.anchor_method)}</b></span>'
        f'<span class=chip><b>{n_models}</b> models · <b>{len(merged.cells)}</b> canonical cells · $0</span>'
        f'<span class=chip>{now.strftime("%Y-%m-%dT%H:%MZ")}</span></div>'
        f'<p class=note><b>Headline:</b> {_sc._esc(_combined_headline(agg)).replace("&#x60;", "")}</p>'
    )


def build_combined_scorecard_html(run_dirs, *, now: Optional[datetime] = None,
                                  align: bool = False, seeds_dir=None) -> str:
    now = now or datetime.now(timezone.utc)
    dirs = [Path(d) for d in run_dirs]
    dir_by_name = {d.name: d for d in dirs}
    merged = _merge_for(dirs, align=align, seeds_dir=seeds_dir)
    cells = merged.cells
    agg = aggregate_cells(cells) if cells else None
    contam = _merge_contamination(merged.runs, dir_by_name, merged)

    scoreboard = _sc._h_dim("A", "Scoreboard", _sc._SB_CAP, _sc._h_scoreboard(agg), 0.05)
    bodies = [
        _sc._h_consistency(agg),
        _sc._h_credibility(contam),
        _sc._h_behavioral(cells),
        _sc._h_determinism(None),
        _sc._h_bylang(agg, contam),
    ]
    supporting = "".join(
        _sc._h_dim(d[0], d[1], d[2], body, 0.12 + i * 0.07)
        for i, (d, body) in enumerate(zip(_sc._DIMS, bodies))
    )
    cross = _sc._h_dim("G", "Provenance", "Where each model's canonical cells came from (CS-2).",
                       _h_provenance(merged), 0.5)
    annex = _sc._h_dim("H", "Methodology annex", "Excluded calibration / other-method runs (CS-13).",
                       _h_annex(merged), 0.57)
    foot = ("<footer>Generated by <code>build_combined_scorecard_html</code> · "
            "docs/design/benchmark-scorecard/SCORECARD_FORMAT.md v2.0 (consolidated)</footer>")
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        "<title>Combined Scoreboard — Summer 2026</title><style>"
        + _sc._HTML_CSS
        + "</style></head><body><div class=\"wrap\">"
        + _combined_header_html(merged, agg, now)
        + scoreboard + supporting + cross + annex + foot
        + "</div></body></html>"
    )


def write_combined_scorecard_html(run_dirs, out_dir, *, now: Optional[datetime] = None,
                                  align: bool = False, seeds_dir=None) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / COMBINED_HTML
    path.write_text(build_combined_scorecard_html(run_dirs, now=now, align=align, seeds_dir=seeds_dir),
                    encoding="utf-8")
    return path
