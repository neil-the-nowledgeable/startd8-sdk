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
from html import escape as _esc
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


# =========================================================================== HTML
# A self-contained HTML scorecard — "precision instrument" aesthetic: charcoal panels,
# monospace data-readout, brass/analog-dial accent, signal-colored status pills, inline
# CodeBLEU meter bars, dashed "not computed" empty states. No external assets (embedded
# CSS + inline-SVG grain), so the file opens directly. Same data as the markdown renderer.

SCORECARD_HTML_FILE = "SCORECARD.html"

_HTML_CSS = """
:root{
  --bg:#0b0d10; --panel:#14171c; --panel2:#171b21; --ink:#e9e6dd; --dim:#9aa0a8;
  --muted:#646b75; --line:#262b32; --brass:#d8a657; --brass2:#a07f3e;
  --ok:#6fcf97; --warn:#e7b541; --bad:#ef6f64;
  --okbg:rgba(111,207,151,.13); --warnbg:rgba(231,181,65,.14); --badbg:rgba(239,111,100,.14);
  --mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Code",Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html{color-scheme:dark}
body{
  margin:0; background:var(--bg); color:var(--ink); font-family:var(--mono);
  font-size:14px; line-height:1.5; letter-spacing:.1px;
  background-image:radial-gradient(120% 80% at 50% -10%,rgba(216,166,87,.07),transparent 60%);
  background-attachment:fixed;
}
body::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.04;z-index:99;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");}
.wrap{max-width:1000px;margin:0 auto;padding:48px 28px 80px}
.kicker{color:var(--brass);text-transform:uppercase;letter-spacing:.32em;font-size:11px;margin:0 0 14px}
h1{font-size:30px;font-weight:600;margin:0;letter-spacing:-.4px}
h1 .accent{color:var(--brass)}
.rule{height:1px;background:linear-gradient(90deg,var(--brass),transparent);margin:20px 0 18px}
.prov{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1px solid var(--line);background:var(--panel);border-radius:5px;padding:6px 11px;font-size:12px;color:var(--dim)}
.chip b{color:var(--ink);font-weight:600}
.note{color:var(--muted);font-size:12px;margin:14px 0 0;max-width:62ch}
section.dim{margin-top:34px;opacity:0;transform:translateY(10px);animation:rise .55s cubic-bezier(.2,.7,.3,1) forwards}
@keyframes rise{to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){section.dim{animation:none;opacity:1;transform:none}}
.dhead{display:flex;align-items:baseline;gap:14px;margin-bottom:12px}
.dnum{font-size:13px;color:var(--brass2);border:1px solid var(--line);border-radius:5px;padding:2px 8px}
.dtitle{font-size:17px;font-weight:600;letter-spacing:-.2px}
.dcap{color:var(--muted);font-size:12px;margin:-4px 0 12px;max-width:74ch}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
table{width:100%;border-collapse:collapse}
thead th{font-size:10.5px;text-transform:uppercase;letter-spacing:.16em;color:var(--muted);
  text-align:right;padding:12px 14px;border-bottom:1px solid var(--line);font-weight:600}
thead th:nth-child(-n+2){text-align:left}
tbody td{padding:11px 14px;border-bottom:1px solid rgba(38,43,50,.55);text-align:right;font-variant-numeric:tabular-nums}
tbody td:nth-child(-n+2){text-align:left}
tbody tr:last-child td{border-bottom:none}
tbody tr{transition:background .12s}
tbody tr:hover{background:var(--panel2)}
tbody tr.top{background:linear-gradient(90deg,rgba(216,166,87,.09),transparent 70%);box-shadow:inset 3px 0 0 var(--brass)}
.rank{color:var(--brass);font-size:15px;font-weight:600;width:42px}
.model{color:var(--ink)}
.big{font-size:15px}
.dimv{color:var(--dim)}
.pill{display:inline-block;font-size:10.5px;text-transform:uppercase;letter-spacing:.1em;
  padding:2px 9px;border-radius:999px;border:1px solid}
.pill-ok{color:var(--ok);background:var(--okbg);border-color:rgba(111,207,151,.35)}
.pill-warn{color:var(--warn);background:var(--warnbg);border-color:rgba(231,181,65,.35)}
.pill-bad{color:var(--bad);background:var(--badbg);border-color:rgba(239,111,100,.35)}
.meter{display:inline-block;vertical-align:middle;width:96px;height:6px;border-radius:3px;
  background:rgba(255,255,255,.06);overflow:hidden;margin-right:9px}
.meter i{display:block;height:100%;border-radius:3px}
.verdict{margin-top:12px;padding:12px 15px;border-radius:8px;border:1px solid var(--line);
  background:var(--panel2);font-size:13px;color:var(--dim)}
.verdict.good{border-color:rgba(111,207,151,.3)}
.verdict.bad{border-color:rgba(239,111,100,.35)}
.empty{border:1px dashed var(--line);border-radius:10px;padding:22px;color:var(--muted);
  font-size:13px;text-align:center;background:repeating-linear-gradient(135deg,transparent,transparent 9px,rgba(255,255,255,.012) 9px,rgba(255,255,255,.012) 18px)}
.empty b{color:var(--dim);font-weight:600}
footer{margin-top:40px;border-top:1px solid var(--line);padding-top:16px;color:var(--muted);font-size:11.5px;line-height:1.7}
footer code{color:var(--dim)}
"""

_FLAG_PILL = {
    "ok": ("pill-ok", "ok"),
    "elevated": ("pill-warn", "elevated"),
    "verbatim": ("pill-bad", "verbatim?"),
}
_FLAG_COLOR = {"ok": "var(--ok)", "elevated": "var(--warn)", "verbatim": "var(--bad)"}


def _flag_of(mx: float) -> str:
    return "verbatim" if mx >= 0.70 else ("elevated" if mx >= 0.50 else "ok")


def _hf(x, p: int = 3) -> str:
    return (
        f"{x:.{p}f}" if isinstance(x, (int, float)) else "<span class=dimv>N/A</span>"
    )


def _empty(why: str) -> str:
    return (
        f'<div class="empty">— not computed for this run —<br><b>{_esc(why)}</b></div>'
    )


def _h_dim(num: str, title: str, cap: str, body: str, delay: float) -> str:
    return (
        f'<section class="dim" style="animation-delay:{delay:.2f}s">'
        f'<div class="dhead"><span class="dnum">§{num}</span><span class="dtitle">{_esc(title)}</span></div>'
        f'<div class="dcap">{cap}</div>{body}</section>'
    )


def _h_table(headers: List[str], rows: List[str]) -> str:
    ths = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    return f'<div class="panel"><table><thead><tr>{ths}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _h_quality(agg: Optional[Dict]) -> str:
    if not agg:
        return _empty("no cells.json (matrix aggregate) persisted")
    rows = []
    for i, (model, *_r) in enumerate(rank_models_by_quality(agg), 1):
        s = agg["by_model"][model]
        cls = ' class="top"' if i == 1 else ""
        rows.append(
            f"<tr{cls}><td class=rank>{i}</td><td class=model>{_esc(model)}</td>"
            f"<td class=big>{_hf(s['quality_median'])}</td><td class=dimv>{_hf(s['quality_iqr'])}</td>"
            f"<td>{_hf(s['pass_rate'])}</td><td class=dimv>{s['catastrophic_count']}/{s['n']}</td>"
            f"<td>{_hf(s['cost_total_usd'], 4)}</td></tr>"
        )
    return _h_table(
        [
            "Rank",
            "Model",
            "Quality (median)",
            "IQR",
            "Pass-rate",
            "Catastrophic",
            "Cost $",
        ],
        rows,
    )


def _h_consistency(agg: Optional[Dict]) -> str:
    if not agg:
        return _empty("depends on §1's cells.json aggregate")
    rows = []
    for i, (model, *_r) in enumerate(rank_models_by_consistency(agg), 1):
        s = agg["by_model"][model]
        cls = ' class="top"' if i == 1 else ""
        warn = " ⚠️" if s["n_scored"] < s["n"] else ""
        rows.append(
            f"<tr{cls}><td class=rank>{i}</td><td class=model>{_esc(model)}</td>"
            f"<td class=big>{_hf(s['pass_rate'])}</td><td class=dimv>{_hf(s['quality_iqr'])}</td>"
            f"<td>{s['n_scored']}/{s['n']}{warn}</td><td class=dimv>{s['catastrophic_count']}/{s['n']}</td></tr>"
        )
    return _h_table(
        ["Rank", "Model", "Pass-rate", "Quality IQR", "Scored/n", "Catastrophic"], rows
    )


def _h_credibility(contam: Optional[dict]) -> str:
    if not contam or not contam.get("cells"):
        return _empty("no contamination-probe.json")
    by_model: Dict[str, List[float]] = {}
    for c in contam["cells"]:
        if c.get("available") and c.get("codebleu") is not None:
            by_model.setdefault(c["model"], []).append(c["codebleu"])
    if not by_model:
        return _empty("probe present but 0 cells scored")
    order = sorted(by_model, key=lambda m: _st.mean(by_model[m]))
    worst = 0.0
    rows = []
    for i, m in enumerate(order, 1):
        v = by_model[m]
        mean, mx = _st.mean(v), max(v)
        worst = max(worst, mx)
        fl = _flag_of(mx)
        pill_cls, pill_txt = _FLAG_PILL[fl]
        width = min(
            100.0, mean / 0.70 * 100.0
        )  # meter scaled so 0.70 (≈verbatim) = full
        meter = f'<span class="meter"><i style="width:{width:.0f}%;background:{_FLAG_COLOR[fl]}"></i></span>'
        cls = ' class="top"' if i == 1 else ""
        rows.append(
            f"<tr{cls}><td class=rank>{i}</td><td class=model>{_esc(m)}</td>"
            f"<td class=big>{meter}{_hf(mean)}</td><td class=dimv>{_hf(mx)}</td><td class=dimv>{len(v)}</td>"
            f'<td><span class="pill {pill_cls}">{pill_txt}</span></td></tr>'
        )
    table = _h_table(
        ["Rank", "Model", "Mean CodeBLEU", "Max (worst)", "n", "Flag"], rows
    )
    top = max(by_model, key=lambda m: _st.mean(by_model[m]))
    if worst < 0.50:
        v = f'<div class="verdict good"><b style="color:var(--ok)">✓ Integrity holds.</b> No model shows elevated memorization — every max CodeBLEU &lt; 0.50 (verbatim ≈ 0.70+). Highest-similarity: <b>{_esc(top)}</b>.</div>'
    else:
        v = f'<div class="verdict bad"><b style="color:var(--bad)">⚠ Review.</b> At least one cell ≥ 0.50 — inspect for memorization before trusting its quality rank. Highest-similarity: <b>{_esc(top)}</b>.</div>'
    return table + v


def _h_behavioral(cells: List[CellResult]) -> str:
    ran = [c for c in cells if c.functional_coverage is not None]
    if not ran:
        return _empty("Track-2 behavioral was not run/persisted")
    by_model: Dict[str, List[float]] = {}
    for c in ran:
        by_model.setdefault(c.model, []).append(c.functional_coverage)
    rows = []
    for i, m in enumerate(sorted(by_model, key=lambda m: -_st.mean(by_model[m])), 1):
        v = by_model[m]
        cls = ' class="top"' if i == 1 else ""
        rows.append(
            f"<tr{cls}><td class=rank>{i}</td><td class=model>{_esc(m)}</td>"
            f"<td class=big>{_hf(_st.mean(v))}</td><td class=dimv>{len(v)}</td></tr>"
        )
    return _h_table(["Rank", "Model", "Functional coverage (mean)", "Cells run"], rows)


def _h_determinism(comparison: Optional[dict]) -> str:
    ranked = (comparison or {}).get("ranked")
    if not ranked:
        return _empty(
            "N/A — OB microservices are not backend-codegen targets (no owned $0 spine to drift)"
        )
    rows = []
    for r in ranked:
        st = (r.get("metrics") or {}).get("spine_check_status", "n/a")
        rows.append(
            f"<tr><td class=model>{_esc(str(r.get('model')))}</td><td>{_esc(str(st))}</td></tr>"
        )
    return _h_table(["Model", "Spine check"], rows)


def _h_bylang(agg: Optional[Dict], contam: Optional[dict]) -> str:
    contam_lang: Dict[str, List[float]] = {}
    if contam:
        for c in contam.get("cells", []):
            if c.get("available") and c.get("codebleu") is not None:
                contam_lang.setdefault(c["language"], []).append(c["codebleu"])
    langs = set(contam_lang) | set((agg or {}).get("by_language", {}))
    if not langs:
        return _empty("no aggregate and no contamination data")
    rows = []
    for lg in sorted(langs):
        s = (agg or {}).get("by_language", {}).get(lg)
        cb = (
            _hf(_st.mean(contam_lang[lg]))
            if lg in contam_lang
            else "<span class=dimv>—</span>"
        )
        ql = _hf(s["quality_median"]) if s else "<span class=dimv>—</span>"
        pr = _hf(s["pass_rate"]) if s else "<span class=dimv>—</span>"
        co = _hf(s["cost_total_usd"], 4) if s else "<span class=dimv>—</span>"
        rows.append(
            f"<tr><td class=model>{_esc(lg)}</td><td>{ql}</td><td>{pr}</td><td>{cb}</td><td>{co}</td></tr>"
        )
    return _h_table(
        ["Language", "Quality (median)", "Pass-rate", "Mean CodeBLEU", "Cost $"], rows
    )


def _h_header(
    spec: Dict, cells: List[CellResult], contam: Optional[dict], now: datetime
) -> str:
    name = spec.get("name") or "benchmark run"
    sh = (spec.get("spec_hash") or "")[:12] or "—"
    mp = spec.get("micro_prime_enabled")
    mp_s = "off" if mp is False else ("on" if mp is True else "n/a")
    s, m, r = (
        len(spec.get("services", [])),
        len(spec.get("models", [])),
        spec.get("repetitions"),
    )
    chips = [
        f"<span class=chip>spec <b>{_esc(sh)}</b></span>",
        f"<span class=chip>matrix <b>{s}×{m}×{r}</b></span>",
        f"<span class=chip>micro-prime <b>{mp_s}</b></span>",
        f"<span class=chip>generated <b>{now.strftime('%Y-%m-%d %H:%MZ')}</b></span>",
    ]
    if cells:
        chips.insert(2, f"<span class=chip>cells <b>{len(cells)}</b></span>")
    if contam:
        chips.append(
            f"<span class=chip>contamination <b>{contam.get('n_scored')}/{contam.get('n_cells')}</b></span>"
        )
    return (
        '<p class="kicker">Summer 2026 · Online Boutique Model Benchmark</p>'
        f'<h1>Scorecard <span class="accent">—</span> {_esc(name)}</h1>'
        f'<div class="rule"></div><div class="prov">{"".join(chips)}</div>'
        '<p class="note">Every dimension is shown; a source the run did not persist is marked '
        "<b>not computed</b>, never silently dropped. Credibility (CodeBLEU) is a leaderboard-integrity "
        "control, not a quality term.</p>"
    )


_DIMS: List[Tuple[str, str, str]] = [
    (
        "1",
        "Quality leaderboard",
        "Median composite — structural × compile-gate × behavioral fold × defect penalty. Ranked best-first; catastrophic ($0/fail/timeout/integrity) counted separately.",
    ),
    (
        "2",
        "Consistency",
        "Reliability over peak — pass-rate then tightest spread (quality IQR), the axis near-equal flagships differ on (FR-K1).",
    ),
    (
        "3",
        "Credibility — contamination",
        "CodeBLEU similarity to the <b>public</b> Online Boutique upstream. Ranked ascending (least memorized first). A credibility control, not quality (FR-47).",
    ),
    (
        "4",
        "Behavioral coverage",
        "Fraction of behavioral RPC contracts the live service satisfied. Folded into composite at 50% (FR-T2).",
    ),
    (
        "5",
        "Determinism boundary",
        "Did the model drift an owned ($0-generated) skeleton file instead of only adding glue (generate backend --check).",
    ),
    (
        "6",
        "By language",
        "Polyglot view — quality, pass-rate, contamination, cost per language.",
    ),
]


def build_scorecard_html(run_dir, *, now: Optional[datetime] = None) -> str:
    """Render the scorecard as a single self-contained HTML document (same data as the markdown)."""
    run_dir = Path(run_dir)
    now = now or datetime.now(timezone.utc)
    cells = _load_cells(run_dir)
    agg = aggregate_cells(cells) if cells else None
    spec = _spec_meta(run_dir)
    contam = _load_json(run_dir / CONTAMINATION_FILE)
    comparison = _load_json(run_dir / COMPARISON_FILE)

    bodies = [
        _h_quality(agg),
        _h_consistency(agg),
        _h_credibility(contam),
        _h_behavioral(cells),
        _h_determinism(comparison),
        _h_bylang(agg, contam),
    ]
    secs = "".join(
        _h_dim(d[0], d[1], d[2], body, 0.05 + i * 0.07)
        for i, (d, body) in enumerate(zip(_DIMS, bodies))
    )
    ref = (contam or {}).get("reference_root", "")
    foot = (
        "<footer>Generated by <code>build_scorecard_html</code> · "
        "docs/design/benchmark-scorecard/SCORECARD_FORMAT.md v1.0"
        + (f"<br>Contamination reference: <code>{_esc(ref)}</code>" if ref else "")
        + "</footer>"
    )
    title = _esc(spec.get("name") or "benchmark run")
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>Scorecard — {title}</title><style>"
        + _HTML_CSS
        + "</style></head><body>"
        '<div class="wrap">'
        + _h_header(spec, cells, contam, now)
        + secs
        + foot
        + "</div></body></html>"
    )


def write_scorecard_html(run_dir, *, now: Optional[datetime] = None) -> Path:
    """Build + write ``<run_dir>/SCORECARD.html``; returns the path."""
    run_dir = Path(run_dir)
    out = run_dir / SCORECARD_HTML_FILE
    out.write_text(build_scorecard_html(run_dir, now=now), encoding="utf-8")
    return out
