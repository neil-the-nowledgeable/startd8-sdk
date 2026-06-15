"""Unified benchmark scorecard renderer (docs/design/benchmark-scorecard/SCORECARD_FORMAT.md v1.0).

`build_scorecard(run_dir)` composes one markdown doc per run from whatever artifacts the run
persisted — `cells.json` (quality/consistency/behavioral/cost/by-language), `contamination-probe.json`
(credibility), `comparison-report.json` (determinism boundary). Each dimension is **degrade-honest**:
a section is always present, marked `_Not computed for this run_` when its source is absent — never
silently dropped (FR-32). Supersedes `aggregate.build_matrix_markdown` (which omitted the newer signals).
"""

from __future__ import annotations

import json
import statistics as _st
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .aggregate import (
    aggregate_cells,
    rank_models_by_consistency,
    rank_models_by_quality,
)
from .runner import CellResult

CELLS_FILE = "cells.json"
CONTAMINATION_FILE = "contamination-probe.json"
COMPARISON_FILE = "comparison-report.json"
SCORECARD_FILE = "SCORECARD.md"

_NOT_COMPUTED = "_Not computed for this run — {why}._"


def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _f(x, p: int = 3) -> str:
    return f"{x:.{p}f}" if isinstance(x, (int, float)) else "N/A"


def _load_cells(run_dir: Path) -> List[CellResult]:
    raw = _load_json(run_dir / CELLS_FILE)
    if not isinstance(raw, list):
        return []
    out = []
    for d in raw:
        try:
            out.append(CellResult.from_dict(d))
        except Exception:  # noqa: BLE001 - a malformed cell shouldn't sink the report
            continue
    return out


def _spec_meta(run_dir: Path) -> Dict:
    return _load_json(run_dir / "run-spec.json") or {}


# --------------------------------------------------------------------------- sections


def _header(
    spec: Dict, cells: List[CellResult], contam: Optional[dict], now: datetime
) -> str:
    name = spec.get("name") or "benchmark run"
    sh = (spec.get("spec_hash") or "")[:12]
    mp = spec.get("micro_prime_enabled")
    mp_s = "off" if mp is False else ("on" if mp is True else "n/a")
    s, m, r = (
        len(spec.get("services", [])),
        len(spec.get("models", [])),
        spec.get("repetitions"),
    )
    line2 = f"spec `{sh}` · generated {now.strftime('%Y-%m-%dT%H:%MZ')} · micro-prime **{mp_s}**"
    matrix = f"matrix: {s} services × {m} models × {r} reps"
    if cells:
        matrix += f" = {len(cells)} cells"
    if contam:
        matrix += f" · contamination scored **{contam.get('n_scored')}/{contam.get('n_cells')}** cells"
    return (
        f"# Benchmark Scorecard — {name}\n{line2}\n{matrix}\n\n"
        "> Per docs/design/benchmark-scorecard/SCORECARD_FORMAT.md v1.0. Every dimension is shown; a\n"
        "> source the run didn't persist is marked `not computed for this run`, never silently dropped."
    )


def _quality_section(agg: Optional[Dict]) -> str:
    head = "## 1. Quality leaderboard (by median composite, then cost)"
    if not agg:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="no `cells.json` (matrix aggregate) persisted"
        )
    rows = [
        "> Quality = median composite (structural + compile-gate + behavioral fold + defect penalty);",
        "> catastrophic = $0/failed/timeout/integrity-fail, reported separately (FR-17).",
        "",
        "| Rank | Model | quality (median) | IQR | pass-rate | catastrophic | cost $ |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for i, (model, *_r) in enumerate(rank_models_by_quality(agg), 1):
        s = agg["by_model"][model]
        rows.append(
            f"| {i} | `{model}` | {_f(s['quality_median'])} | {_f(s['quality_iqr'])} | "
            f"{_f(s['pass_rate'])} | {s['catastrophic_count']}/{s['n']} | {_f(s['cost_total_usd'], 4)} |"
        )
    return f"{head}\n\n" + "\n".join(rows)


def _consistency_section(agg: Optional[Dict]) -> str:
    head = "## 2. Consistency (most reliable first)"
    if not agg:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="depends on §1's `cells.json` aggregate"
        )
    rows = [
        "> Reliability over peak: pass-rate then tightest spread (quality IQR) — the axis near-equal",
        "> flagships differ on (FR-K1). `scored/n` below 1 (⚠️) = some reps excluded (infra/budget).",
        "",
        "| Rank | Model | pass-rate | quality IQR | scored/n | catastrophic |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for i, (model, *_r) in enumerate(rank_models_by_consistency(agg), 1):
        s = agg["by_model"][model]
        flag = " ⚠️" if s["n_scored"] < s["n"] else ""
        rows.append(
            f"| {i} | `{model}` | {_f(s['pass_rate'])} | {_f(s['quality_iqr'])} | "
            f"{s['n_scored']}/{s['n']}{flag} | {s['catastrophic_count']}/{s['n']} |"
        )
    return f"{head}\n\n" + "\n".join(rows)


def _credibility_section(contam: Optional[dict]) -> str:
    head = "## 3. Credibility — contamination / memorization (lower = more credible)"
    if not contam or not contam.get("cells"):
        return f"{head}\n\n" + _NOT_COMPUTED.format(why="no `contamination-probe.json`")
    by_model: Dict[str, List[float]] = {}
    for c in contam["cells"]:
        if c.get("available") and c.get("codebleu") is not None:
            by_model.setdefault(c["model"], []).append(c["codebleu"])
    if not by_model:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="probe present but 0 cells scored"
        )

    def _flag(mx: float) -> str:
        return (
            "🟥 verbatim?" if mx >= 0.70 else ("🟧 elevated" if mx >= 0.50 else "🟩 ok")
        )

    rows = [
        "> CodeBLEU vs the **public** Online Boutique upstream; higher ⇒ more likely reproduced from",
        "> pretraining than solved. Ranked **ascending** (least memorized first). NOT a quality term —",
        "> a leaderboard-integrity control (FR-47). Clean signal needs a repair-OFF (or shadow) run.",
        "",
        "| Rank | Model | mean CodeBLEU | max (worst cell) | n | flag |",
        "|---:|---|---:|---:|---:|---|",
    ]
    order = sorted(by_model, key=lambda m: _st.mean(by_model[m]))
    worst_max = 0.0
    for i, m in enumerate(order, 1):
        v = by_model[m]
        worst_max = max(worst_max, max(v))
        rows.append(
            f"| {i} | `{m}` | {_f(_st.mean(v))} | {_f(max(v))} | {len(v)} | {_flag(max(v))} |"
        )
    top = max(by_model, key=lambda m: _st.mean(by_model[m]))
    verdict = (
        "no model shows elevated memorization — every max CodeBLEU < 0.50 (verbatim is ~0.70+); "
        if worst_max < 0.50
        else "⚠️ at least one cell ≥ 0.50 — inspect for memorization before trusting its quality rank; "
    )
    rows += ["", f"**Verdict:** {verdict}highest-similarity model: `{top}`."]
    return f"{head}\n\n" + "\n".join(rows)


def _behavioral_section(cells: List[CellResult]) -> str:
    head = "## 4. Behavioral (functional coverage)"
    ran = [c for c in cells if c.functional_coverage is not None]
    if not ran:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="Track-2 behavioral was not run/persisted"
        )
    by_model: Dict[str, List[float]] = {}
    for c in ran:
        by_model.setdefault(c.model, []).append(c.functional_coverage)
    rows = [
        "> Fraction of behavioral RPC contracts the live service satisfied (e.g. Charge:",
        "> valid/invalid/expired). Folded into composite quality at 50% (FR-T2-COMPOSITE).",
        "",
        "| Model | functional coverage (mean) | cells run |",
        "|---|---:|---:|",
    ]
    for m in sorted(by_model, key=lambda m: -_st.mean(by_model[m])):
        v = by_model[m]
        rows.append(f"| `{m}` | {_f(_st.mean(v))} | {len(v)} |")
    return f"{head}\n\n" + "\n".join(rows)


def _determinism_section(comparison: Optional[dict]) -> str:
    head = "## 5. Determinism boundary (spine in-sync)"
    ranked = (comparison or {}).get("ranked")
    if not ranked:
        return (
            f"{head}\n\n"
            "_N/A for this run — Online Boutique microservices are not backend-codegen targets, so there\n"
            "is no owned $0 spine to drift. (Populated from `comparison-report.json` `spine_check_status`\n"
            "on a `compare-models` run against a backend-codegen seed.)_"
        )
    rows = ["| Model | spine check |", "|---|---|"]
    for r in ranked:
        st = (r.get("metrics") or {}).get("spine_check_status", "n/a")
        rows.append(f"| `{r.get('model')}` | {st} |")
    return (
        f"{head}\n\n> Did the model drift an owned ($0-generated) skeleton file (`generate backend --check`).\n\n"
        + "\n".join(rows)
    )


def _by_language_section(agg: Optional[Dict], contam: Optional[dict]) -> str:
    head = "## 6. By language (polyglot view)"
    contam_lang: Dict[str, List[float]] = {}
    if contam:
        for c in contam.get("cells", []):
            if c.get("available") and c.get("codebleu") is not None:
                contam_lang.setdefault(c["language"], []).append(c["codebleu"])
    if not agg and not contam_lang:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="no aggregate and no contamination data"
        )
    rows = [
        "| Language | quality (median) | pass-rate | mean CodeBLEU | cost $ |",
        "|---|---:|---:|---:|---:|",
    ]
    langs = set(contam_lang)
    if agg:
        langs |= set(agg.get("by_language", {}))
    for lg in sorted(langs):
        s = (agg or {}).get("by_language", {}).get(lg)
        cb = _f(_st.mean(contam_lang[lg])) if lg in contam_lang else "—"
        if s:
            rows.append(
                f"| {lg} | {_f(s['quality_median'])} | {_f(s['pass_rate'])} | {cb} | {_f(s['cost_total_usd'], 4)} |"
            )
        else:
            rows.append(f"| {lg} | — | — | {cb} | — |")
    return f"{head}\n\n" + "\n".join(rows)


def _coverage_notes(contam: Optional[dict], cells: List[CellResult]) -> Optional[str]:
    if not contam:
        return None
    n_deg = (contam.get("n_cells") or 0) - (contam.get("n_scored") or 0)
    svcs = sorted({c["service"] for c in contam.get("cells", []) if c.get("available")})
    return (
        "## Coverage notes\n\n"
        f"- Contamination: {contam.get('n_scored')}/{contam.get('n_cells')} cells scored; "
        f"{n_deg} degraded.\n"
        f"- Reference: `{contam.get('reference_root')}`.\n"
        f"- Services with contamination data: {', '.join(svcs) or '(none)'}."
    )


def build_scorecard(run_dir, *, now: Optional[datetime] = None) -> str:
    """Render the unified scorecard for ``run_dir`` (degrade-honest per missing artifact)."""
    run_dir = Path(run_dir)
    now = now or datetime.now(timezone.utc)
    cells = _load_cells(run_dir)
    agg = aggregate_cells(cells) if cells else None
    spec = _spec_meta(run_dir)
    contam = _load_json(run_dir / CONTAMINATION_FILE)
    comparison = _load_json(run_dir / COMPARISON_FILE)

    sections = [
        _header(spec, cells, contam, now),
        _quality_section(agg),
        _consistency_section(agg),
        _credibility_section(contam),
        _behavioral_section(cells),
        _determinism_section(comparison),
        _by_language_section(agg, contam),
        _coverage_notes(contam, cells),
    ]
    return "\n\n".join(s for s in sections if s) + "\n"


def write_scorecard(run_dir, *, now: Optional[datetime] = None) -> Path:
    """Build + write ``<run_dir>/SCORECARD.md``; returns the path."""
    run_dir = Path(run_dir)
    out = run_dir / SCORECARD_FILE
    out.write_text(build_scorecard(run_dir, now=now), encoding="utf-8")
    return out
