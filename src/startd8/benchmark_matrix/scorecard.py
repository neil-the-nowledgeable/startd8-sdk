"""Unified benchmark scorecard renderer (docs/design/benchmark-scorecard/SCORECARD_FORMAT.md v2.0).

`build_scorecard(run_dir)` (markdown) / `build_scorecard_html(run_dir)` (self-contained HTML) compose
one scorecard per run from whatever it persisted — `cells.json` (quality), `contamination-probe.json`
(credibility), `comparison-report.json` (determinism). **Inverted-pyramid (v2.0):** scores first — a
headline verdict, then the **Scoreboard** of five composite-quality leaderboards (flagship → providers
→ all, each best→worst), then the supporting dimensions (consistency, credibility, behavioral,
determinism, by-language). Every dimension is **degrade-honest**: always present, marked `not computed`
when its source is absent (FR-32). Credibility (CodeBLEU) is a leaderboard-integrity control, not folded
into quality.
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

# The cross-provider headline set (SCORECARD_FORMAT v2.0). Overridable; a run that lacks one of these
# ids simply shows the flagships it has.
FLAGSHIP_MODELS = frozenset(
    {
        "anthropic:claude-opus-4-8",
        "openai:gpt-5.5",
        "gemini:gemini-2.5-pro",
    }
)
_PROVIDER_LABEL = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "gemini": "Google",
    "google": "Google",
}

# The Liferay-derived complex-pricing lane (FR-1). One named home, not a scattered literal.
# Mirrors the four services in docs/design/model-benchmark/seeds/hardened-index.json whose
# `derived_from` is Liferay Commerce pricing. These are hardened-tier by construction (axes
# B/C/E) — there is no baseline pricing seed; the lane IS the hardened tier. The behavioral
# suites for these de-saturate where the OB-leaf services saturate, which is where flagship
# models actually differentiate.
PRICING_LANE = frozenset(
    {
        "resolvedpriceservice",
        "pricingservice",
        "rest-pricingservice",
        "graphql-pricingservice",
    }
)

# The checkout orchestrator (CQ-4). checkoutservice is its OWN scorecard axis — distinct from the
# per-service skill the leaf suites measure: it asks "does the model correctly *wire six services
# together* into one PlaceOrder", the integration/orchestration frontier. One named home.
CHECKOUT_SERVICE = "checkoutservice"

# The six PlaceOrder orchestration steps (FR-CO-19), in step order. Mirrors checkout_suite's
# RpcResult names + their dialed dependency (the call-counter provenance is keyed by *_SERVICE_ADDR).
_CHECKOUT_STEPS: List[Tuple[str, str]] = [
    ("catalog_priced", "PRODUCT_CATALOG_SERVICE_ADDR"),
    ("cart_honored", "CART_SERVICE_ADDR"),
    ("currency_converted", "CURRENCY_SERVICE_ADDR"),
    ("shipping_applied", "SHIPPING_SERVICE_ADDR"),
    ("payment_charged", "PAYMENT_SERVICE_ADDR"),
    ("email_confirmed", "EMAIL_SERVICE_ADDR"),
]


def _provider(model: str) -> str:
    return _PROVIDER_LABEL.get(
        model.split(":", 1)[0].lower(), model.split(":", 1)[0].title()
    )


def _ranked_models(agg: Dict) -> List[str]:
    """Models best→worst by composite quality (quality desc, cost asc) — reuses rank_models_by_quality."""
    return [m for (m, *_r) in rank_models_by_quality(agg)]


# (group key, table title). Order is the inverted-pyramid Scoreboard order.
_SCOREBOARD_GROUPS = [
    ("flagship", "Flagship comparison"),
    ("Anthropic", "Anthropic models"),
    ("Google", "Google models"),
    ("OpenAI", "OpenAI models"),
    ("all", "All models"),
]


def _group_models(ordered: List[str], key: str) -> List[str]:
    if key == "all":
        return ordered
    if key == "flagship":
        return [m for m in ordered if m in FLAGSHIP_MODELS]
    return [m for m in ordered if _provider(m) == key]  # key is a provider label


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
        f"**Headline:** {_headline(agg_or_none(cells), contam)}\n\n"
        "> Per docs/design/benchmark-scorecard/SCORECARD_FORMAT.md v2.0 (inverted-pyramid: scores first).\n"
        "> Every dimension is shown; a source the run didn't persist is marked `not computed`."
    )


def agg_or_none(cells: List[CellResult]) -> Optional[Dict]:
    return aggregate_cells(cells) if cells else None


def _headline(agg: Optional[Dict], contam: Optional[dict]) -> str:
    if agg:
        ordered = _ranked_models(agg)
        flag = [m for m in ordered if m in FLAGSHIP_MODELS]
        lead = flag[0] if flag else (ordered[0] if ordered else None)
        if lead:
            q = agg["by_model"][lead]["quality_median"]
            scope = "flagship" if lead in FLAGSHIP_MODELS else "overall"
            return (
                f"`{lead}` leads the {scope} scoreboard on composite quality ({_f(q)})."
            )
    if contam and contam.get("cells"):
        by = {}
        for c in contam["cells"]:
            if c.get("available") and c.get("codebleu") is not None:
                by.setdefault(c["model"], []).append(c["codebleu"])
        if by:
            clean = min(by, key=lambda m: _st.mean(by[m]))
            return (
                "quality not computed for this run — see Credibility below; cleanest contamination "
                f"signal: `{clean}`."
            )
    return "no scores computed for this run."


def _qtable(agg: Dict, models: List[str]) -> str:
    """A quality-leaderboard markdown table for an ordered model subset (or a no-models marker)."""
    if not models:
        return "_(no models in this group for this run)_"
    rows = [
        "| Rank | Model | quality (median) | IQR | pass-rate | catastrophic | cost $ | model tok/s med |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for i, model in enumerate(models, 1):
        s = agg["by_model"][model]
        rows.append(
            f"| {i} | `{model}` | {_f(s['quality_median'])} | {_f(s['quality_iqr'])} | "
            f"{_f(s['pass_rate'])} | {s['catastrophic_count']}/{s['n']} | {_f(s['cost_total_usd'], 4)} | "
            f"{_f(s.get('model_tokens_per_sec_median'), 1)} |"  # FR-SPEED-2 headline
        )
    return "\n".join(rows)


def _speed_section(agg: Optional[Dict]) -> str:
    """Section E (FR-SPEED-4): two time measures + harness overhead, ranked by pure-model throughput."""
    head = "## Speed (generation time — reported, not scored)"
    if not agg or not agg.get("by_model"):
        return f"{head}\n\n" + _NOT_COMPUTED.format(why="no `cells.json` aggregate persisted")
    rows = [
        head, "",
        "> `model` = pure model API time (Σ GenerateResult.time_ms); `pipeline wall` = whole subprocess; "
        "`harness overhead` = (wall − model)/wall.", "",
        "| Rank | Model | model time med (s) | model tok/s med | pipeline wall med (s) | "
        "pipeline tok/s med | harness overhead |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    ranked = sorted(agg["by_model"],
                    key=lambda m: agg["by_model"][m].get("model_tokens_per_sec_median") or -1.0,
                    reverse=True)
    for i, model in enumerate(ranked, 1):
        s = agg["by_model"][model]
        mt, wall = s.get("model_time_median_s"), s.get("latency_median_s")
        overhead = (f"{(wall - mt) / wall:.0%}"
                    if isinstance(mt, (int, float)) and isinstance(wall, (int, float)) and wall > 0
                    else "N/A")
        rows.append(
            f"| {i} | `{model}` | {_f(mt, 1)} | {_f(s.get('model_tokens_per_sec_median'), 1)} | "
            f"{_f(wall, 1)} | {_f(s.get('tokens_per_sec_median'), 1)} | {overhead} |"
        )
    return "\n".join(rows)


def _scoreboard_section(agg: Optional[Dict]) -> str:
    head = "## Scoreboard — composite quality (best → worst)"
    if not agg:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="no `cells.json` aggregate persisted (the whole Scoreboard degrades together)"
        )
    cap = (
        "> Quality = median composite (structural × compile-gate × behavioral fold × defect penalty);\n"
        "> catastrophic = $0/failed/timeout/integrity-fail (FR-17). Each table ranked best→worst."
    )
    ordered = _ranked_models(agg)
    blocks = [head, cap]
    for key, title in _SCOREBOARD_GROUPS:
        blocks.append(f"### {title}\n\n" + _qtable(agg, _group_models(ordered, key)))
    return "\n\n".join(blocks)


def _consistency_section(agg: Optional[Dict]) -> str:
    head = "## Consistency (most reliable first)"
    if not agg:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="depends on the `cells.json` aggregate (see Scoreboard)"
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
    head = "## Credibility — contamination / memorization (lower = more credible)"
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
    head = "## Behavioral (functional coverage)"
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


def _observability_readiness_section(cells: List[CellResult]) -> str:
    """B1 — does each model's generated service present an observable RED surface?

    Reported-not-scored (Scorecard Principle 7): $0-recomputable from the persisted
    ``observability_coverage`` (static, zero-runtime), and it does NOT alter the
    Scoreboard ranking. A net-new axis — the benchmark otherwise measures whether the
    code works, never whether the service is *observable*.
    """
    head = "## Observability readiness (reported-not-scored)"
    ran = [c for c in cells if c.observability_coverage is not None]
    if not ran:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="no `observability_coverage` persisted (needs cells.json from a post-B1 run)"
        )
    by_model: Dict[str, List[float]] = {}
    for c in ran:
        by_model.setdefault(c.model, []).append(c.observability_coverage)
    rows = [
        "> Fraction of the RED metric surface (throughput + latency) that standard",
        "> observability would query which the generated service actually emits —",
        "> explicit instruments + transport-implied auto-instrumentation, vs the",
        "> descriptor's semconv metrics. Static, $0. Does NOT affect quality/ranking.",
        "",
        "| Model | observability readiness (mean) | cells |",
        "|---|---:|---:|",
    ]
    for m in sorted(by_model, key=lambda m: -_st.mean(by_model[m])):
        v = by_model[m]
        rows.append(f"| `{m}` | {_f(_st.mean(v))} | {len(v)} |")
    return f"{head}\n\n" + "\n".join(rows)


def _is_pricing(c: CellResult) -> bool:
    return c.service in PRICING_LANE


def _suite_results(c: CellResult) -> List[dict]:
    """Per-case results persisted at behavioral.suite.results ({name, passed, detail}).

    Returns [] for a degraded/no-suite cell (behavioral present but no suite key) — the
    degrade-honest path (FR-6). Guards every level since a degraded cell's behavioral dict
    has only readiness/violation keys, no ``suite``."""
    beh = getattr(c, "behavioral", None) or {}
    suite = beh.get("suite") or {}
    res = suite.get("results") or []
    return [r for r in res if isinstance(r, dict) and "name" in r]


def _pricing_lane_section(cells: List[CellResult]) -> str:
    """FR-3/FR-5: the pricing lane as a distinct discriminator + the lane-vs-leaf contrast.

    Coverage restricted to the Liferay pricing services, ranked best→worst per model, beside
    the OB-leaf coverage so the 'where models differentiate' gap is one glance. Reported, never
    folded into the Scoreboard ranking (Scorecard Principle 7)."""
    head = "## Pricing lane (Liferay-derived discriminator)"
    priced = [c for c in cells if _is_pricing(c) and c.functional_coverage is not None]
    if not priced:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="no pricing-lane cells with behavioral coverage were persisted"
        )
    leaf: Dict[str, List[float]] = {}
    for c in cells:
        if not _is_pricing(c) and c.functional_coverage is not None:
            leaf.setdefault(c.model, []).append(c.functional_coverage)
    by_model: Dict[str, List[float]] = {}
    for c in priced:
        by_model.setdefault(c.model, []).append(c.functional_coverage)
    rows = [
        "> Functional coverage over the **Liferay-derived complex-pricing** services only "
        "(`resolvedpriceservice`,",
        "> `pricingservice`, `rest-/graphql-pricingservice`) — chain-vs-addition stacking, "
        "rounding-mode, tax",
        "> ordering. This lane de-saturates where the OB-leaf services (Section above) saturate. "
        "`leaf Δ` =",
        "> pricing-lane mean − OB-leaf mean for the same model (negative ⇒ the lane is harder, "
        "as intended).",
        "> Reported, not folded into the Scoreboard (Principle 7).",
        "",
        "| Model | pricing coverage (mean) | cells | OB-leaf (mean) | leaf Δ |",
        "|---|---:|---:|---:|---:|",
    ]
    for m in sorted(by_model, key=lambda m: -_st.mean(by_model[m])):
        v = by_model[m]
        pmean = _st.mean(v)
        if leaf.get(m):
            lmean = _st.mean(leaf[m])
            lcol, dcol = _f(lmean), _f(pmean - lmean)
        else:
            lcol, dcol = "N/A", "N/A"
        rows.append(f"| `{m}` | {_f(pmean)} | {len(v)} | {lcol} | {dcol} |")
    return f"{head}\n\n" + "\n".join(rows)


def _pricing_discriminator_rows(cells: List[CellResult]) -> Dict[str, Dict[str, Dict[str, Tuple[int, int]]]]:
    """{service: {case_name: {model: (passed, total)}}} over pricing cells with suite results."""
    out: Dict[str, Dict[str, Dict[str, Tuple[int, int]]]] = {}
    for c in cells:
        if not _is_pricing(c):
            continue
        results = _suite_results(c)
        if not results:
            continue
        svc = out.setdefault(c.service, {})
        for r in results:
            cell = svc.setdefault(r["name"], {})
            p, t = cell.get(c.model, (0, 0))
            cell[c.model] = (p + (1 if r.get("passed") else 0), t + 1)
    return out


def _pricing_discriminators_section(cells: List[CellResult]) -> str:
    """FR-4: per-case pass/fail of the named discriminator cases, per service, per model.

    Aggregate coverage hides that a model fails *exactly* the spec-reasoning cases (chain-vs-
    addition, rounding-mode, tax-ordering). This exposes it — a per-service matrix of case ×
    model showing pass-rate across reps (e.g. `5/5`, `0/5`)."""
    head = "## Pricing discriminators (per-case, by model)"
    data = _pricing_discriminator_rows(cells)
    if not data:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="no pricing-lane cell persisted per-case suite results (degraded or not run)"
        )
    blocks: List[str] = [
        "> Per-case outcome of the SDK-authored ground-truth suites, by service and model "
        "(`passed/reps`).",
        "> The cases that separate spec-reasoning from pattern-matching — strategy stacking, "
        "rounding mode,",
        "> tax/discount ordering — are where flagships diverge even when aggregate coverage looks even.",
    ]
    for svc in sorted(data):
        cases = data[svc]
        models = sorted({m for case in cases.values() for m in case})
        header = "| Case | " + " | ".join(f"`{m}`" for m in models) + " |"
        sep = "|---|" + "|".join([":--:"] * len(models)) + "|"
        block = [f"\n### `{svc}`", "", header, sep]
        for case in sorted(cases):
            cells_out = []
            for m in models:
                if m in cases[case]:
                    p, t = cases[case][m]
                    cells_out.append(f"{p}/{t}")
                else:
                    cells_out.append("—")
            block.append(f"| `{case}` | " + " | ".join(cells_out) + " |")
        blocks.append("\n".join(block))
    return f"{head}\n\n" + "\n".join(blocks)


def _is_checkout(c: CellResult) -> bool:
    return c.service == CHECKOUT_SERVICE


def _checkout_frontier_section(cells: List[CellResult]) -> str:
    """FR-CO-20 / CQ-4: checkout's orchestration coverage as a distinct integration frontier.

    Per-model PlaceOrder coverage (mean of the 6 equal-weight steps), ranked best→worst with `n`.
    This is a SEPARATE axis from per-service skill: it measures whether the model wires the six
    dependencies into one working order, where the leaf suites measure a single service in isolation.
    Reported, never folded into the Scoreboard ranking (Scorecard Principle 7). Degrade-honest:
    `not computed` when no checkout cells ran."""
    head = "## Checkout integration frontier (orchestration coverage)"
    ran = [c for c in cells if _is_checkout(c) and c.functional_coverage is not None]
    if not ran:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="no checkoutservice cells with behavioral coverage were persisted"
        )
    by_model: Dict[str, List[float]] = {}
    for c in ran:
        by_model.setdefault(c.model, []).append(c.functional_coverage)
    rows = [
        "> PlaceOrder coverage over the **six** orchestrated dependencies "
        "(catalog/cart/currency/shipping/",
        "> payment/email), each an equal-weight step. This is the **integration/orchestration "
        "frontier** —",
        "> does the model correctly wire six services into one order — a distinct axis from the "
        "per-service",
        "> skill the leaf suites measure. Reported, not folded into the Scoreboard (Principle 7).",
        "",
        "| Rank | Model | PlaceOrder coverage (mean) | cells |",
        "|---:|---|---:|---:|",
    ]
    for i, m in enumerate(sorted(by_model, key=lambda m: -_st.mean(by_model[m])), 1):
        v = by_model[m]
        rows.append(f"| {i} | `{m}` | {_f(_st.mean(v))} | {len(v)} |")
    return f"{head}\n\n" + "\n".join(rows)


def _checkout_step_passed(c: CellResult, step: str, addr_env: str) -> Optional[bool]:
    """Per-step pass for one checkout cell, from persisted provenance (FR-CO-19).

    Primary signal: the per-step suite result (``behavioral.suite.results`` — same shape as the
    pricing per-case table, the six named PlaceOrder steps). Fallback when no suite results were
    persisted but call-counts were: a step is treated as reached when its dependency was dialed
    (``behavioral.checkout_call_counts[addr_env] > 0``) — a weaker proxy, surfaced as such. Returns
    None when neither provenance is present (degrade-honest)."""
    for r in _suite_results(c):
        if r.get("name") == step:
            return bool(r.get("passed"))
    beh = getattr(c, "behavioral", None) or {}
    counts = beh.get("checkout_call_counts")
    if isinstance(counts, dict) and counts:
        return counts.get(addr_env, 0) > 0
    return None


def _checkout_ran_suite(c: CellResult) -> bool:
    """A checkout cell has *real* per-step signal only if it actually ran the suite.

    True when behavioral coverage was computed (``functional_coverage is not None``) OR per-step
    suite results were persisted. A degraded cell (service never launched: provisioning failed, no
    ``suite.results``, ``functional_coverage`` None) has all-zero ``checkout_call_counts`` — those
    zeros are *absence of a run*, not genuine per-step misses, so it must be excluded from D5 rather
    than rendered as ``0/1`` across all six steps (degrade-honest, mirrors D4's `not computed`)."""
    return c.functional_coverage is not None or bool(_suite_results(c))


def _checkout_step_rows(cells: List[CellResult]) -> Dict[str, Dict[str, Tuple[int, int]]]:
    """{step_name: {model: (passed, total)}} over checkout cells that actually ran the suite.

    Degraded checkout cells (no run) are excluded so their all-zero call-counts are not fabricated
    into ``0/1`` all-fail rows (degrade-honest). For a cell that *ran*, a step at count 0 is a real
    miss (the model genuinely never dialed that dependency) and is kept."""
    out: Dict[str, Dict[str, Tuple[int, int]]] = {}
    for c in cells:
        if not _is_checkout(c) or not _checkout_ran_suite(c):
            continue
        for step, addr_env in _CHECKOUT_STEPS:
            ok = _checkout_step_passed(c, step, addr_env)
            if ok is None:
                continue
            cell = out.setdefault(step, {})
            p, t = cell.get(c.model, (0, 0))
            cell[c.model] = (p + (1 if ok else 0), t + 1)
    return out


def _checkout_steps_section(cells: List[CellResult]) -> str:
    """FR-CO-19: per-step PlaceOrder breakdown — which of the six steps each model passed.

    The analog of the pricing per-case table for the orchestrator: a matrix of step × model
    (`passed/reps`) over the six dialed dependencies. Aggregate coverage hides *which* dependency a
    model fails to wire (e.g. never dialing email, or charging payment with the wrong address);
    this exposes it. Degrade-honest when no checkout cell persisted per-step provenance."""
    head = "## Checkout orchestration steps (per-step, by model)"
    data = _checkout_step_rows(cells)
    if not data:
        return f"{head}\n\n" + _NOT_COMPUTED.format(
            why="no checkoutservice cell persisted per-step suite results or call-counts "
                "(degraded or not run)"
        )
    models = sorted({m for step in data.values() for m in step})
    blocks = [
        "> Per-step outcome of the one happy-path PlaceOrder, by model (`passed/reps`). The six "
        "steps are the",
        "> six orchestrated dependencies — catalog, cart, currency, shipping, payment, email — each "
        "equal-weight.",
        "> Where aggregate coverage looks even, this shows *which* dependency a model fails to wire "
        "(FR-CO-19).",
        "",
        "| Step | " + " | ".join(f"`{m}`" for m in models) + " |",
        "|---|" + "|".join([":--:"] * len(models)) + "|",
    ]
    # Render in canonical step order (not alphabetical) — the order PlaceOrder executes them.
    for step, _addr in _CHECKOUT_STEPS:
        if step not in data:
            continue
        cells_out = []
        for m in models:
            if m in data[step]:
                p, t = data[step][m]
                cells_out.append(f"{p}/{t}")
            else:
                cells_out.append("—")
        blocks.append(f"| `{step}` | " + " | ".join(cells_out) + " |")
    return f"{head}\n\n" + "\n".join(blocks)


def _determinism_section(comparison: Optional[dict]) -> str:
    head = "## Determinism boundary (spine in-sync)"
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
    head = "## By language (polyglot view)"
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


PHASE_TRAJECTORY_FILE = "phase-trajectory.json"


def _refinement_summary(run_dir: Path, cells: List[CellResult]) -> Optional[dict]:
    """Aggregate the per-draft compile sidecar (if present). Advisory — never scored."""
    data = _load_json(run_dir / PHASE_TRAJECTORY_FILE)
    if not data:
        return None
    id2sm = {c.cell_id: (c.service, c.model) for c in cells}
    feats = fdc = 0
    tail: List[tuple] = []      # non-compiling first drafts (the discriminating signal)
    converged = 0               # broke on draft-1, compiled after a later draft
    for cid, rec in (data.get("cells") or {}).items():
        if rec.get("status") != "computed":
            continue
        svc, model = id2sm.get(cid, ("?", "?"))
        for f in rec.get("features", []):
            feats += 1
            if f.get("first_draft_compiles"):
                fdc += 1
            else:
                tail.append((model, svc))
                if f.get("final_compiles"):
                    converged += 1
    return {"cov": data.get("coverage", {}), "feats": feats, "fdc": fdc,
            "tail": tail, "converged": converged}


def _refinement_trajectory_section(run_dir: Path, cells: List[CellResult]) -> Optional[str]:
    s = _refinement_summary(run_dir, cells)
    if s is None:
        return None  # sidecar absent → omit (optional, advisory)
    head = "## Refinement trajectory (per-draft compile — advisory, NOT scored)"
    cov, feats, fdc = s["cov"], s["feats"], s["fdc"]
    rate = (fdc / feats) if feats else 0.0
    rows = [
        "> Does the model's **first draft** compile? Computed $0 from persisted draft artifacts —",
        "> a diagnostic, NOT a ranking term: it saturates among frontier models, so there is no",
        "> per-model column (it would read ~100% for everyone). The signal is the tail (FR-10).",
        "",
        f"- **First-draft compiles: {fdc}/{feats} features ({_f(rate)})** over "
        f"{cov.get('computed', '?')}/{cov.get('total', '?')} cells "
        f"({cov.get('not_computed', '?')} had no draft artifacts).",
    ]
    if s["tail"]:
        rows.append(f"- **Non-compiling first drafts ({len(s['tail'])})** — the discriminating exceptions:")
        for model, svc in s["tail"][:12]:
            rows.append(f"    - `{model}` · {svc}")
        if s["converged"]:
            rows.append(f"  ({s['converged']} compiled after a later draft — the draft→review loop recovered them)")
    else:
        rows.append("- No non-compiling first drafts — every computed first draft passed the compile gate.")
    return f"{head}\n\n" + "\n".join(rows)


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
        _scoreboard_section(agg),  # A — scores first (inverted pyramid)
        _consistency_section(agg),
        _credibility_section(contam),
        _behavioral_section(cells),
        _pricing_lane_section(cells),          # D2 — pricing lane discriminator (FR-3/FR-5)
        _pricing_discriminators_section(cells),  # D3 — per-case discriminators (FR-4)
        _checkout_frontier_section(cells),     # D4 — checkout integration frontier (FR-CO-20/CQ-4)
        _checkout_steps_section(cells),        # D5 — per-step PlaceOrder breakdown (FR-CO-19)
        _observability_readiness_section(cells),  # D6 — observability readiness (B1, reported-not-scored)
        _speed_section(agg),       # E — speed (two time measures), FR-SPEED-4
        _determinism_section(comparison),
        _refinement_trajectory_section(run_dir, cells),  # G — advisory, omitted if no sidecar
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
.headline{font-size:14.5px;color:var(--ink);margin:16px 0 0;padding:13px 16px;border-radius:8px;
  border:1px solid var(--line);border-left:3px solid var(--brass);background:var(--panel)}
.headline code{color:var(--brass)}
.grp{font-size:11.5px;text-transform:uppercase;letter-spacing:.18em;color:var(--brass2);margin:20px 0 9px}
.grp:first-of-type{margin-top:2px}
.grp::before{content:"▸ ";color:var(--brass)}
.sb-empty{color:var(--muted);font-size:12px;padding:7px 2px 4px}
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


_QCOLS = [
    "Rank",
    "Model",
    "Quality (median)",
    "IQR",
    "Pass-rate",
    "Catastrophic",
    "Cost $",
]


def _h_qrows(agg: Dict, models: List[str]) -> List[str]:
    rows = []
    for i, model in enumerate(models, 1):
        s = agg["by_model"][model]
        cls = ' class="top"' if i == 1 else ""
        rows.append(
            f"<tr{cls}><td class=rank>{i}</td><td class=model>{_esc(model)}</td>"
            f"<td class=big>{_hf(s['quality_median'])}</td><td class=dimv>{_hf(s['quality_iqr'])}</td>"
            f"<td>{_hf(s['pass_rate'])}</td><td class=dimv>{s['catastrophic_count']}/{s['n']}</td>"
            f"<td>{_hf(s['cost_total_usd'], 4)}</td></tr>"
        )
    return rows


def _h_scoreboard(agg: Optional[Dict]) -> str:
    if not agg:
        return _empty(
            "no cells.json aggregate persisted (the whole Scoreboard degrades together)"
        )
    ordered = _ranked_models(agg)
    parts = []
    for key, title in _SCOREBOARD_GROUPS:
        models = _group_models(ordered, key)
        parts.append(f'<h3 class="grp">{_esc(title)}</h3>')
        parts.append(
            _h_table(_QCOLS, _h_qrows(agg, models))
            if models
            else '<div class="sb-empty">— no models in this group for this run —</div>'
        )
    return "".join(parts)


def _h_consistency(agg: Optional[Dict]) -> str:
    if not agg:
        return _empty("depends on the cells.json aggregate (see Scoreboard)")
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


def _h_pricing_lane(cells: List[CellResult]) -> str:
    priced = [c for c in cells if _is_pricing(c) and c.functional_coverage is not None]
    if not priced:
        return _empty("no pricing-lane cells with behavioral coverage were persisted")
    leaf: Dict[str, List[float]] = {}
    for c in cells:
        if not _is_pricing(c) and c.functional_coverage is not None:
            leaf.setdefault(c.model, []).append(c.functional_coverage)
    by_model: Dict[str, List[float]] = {}
    for c in priced:
        by_model.setdefault(c.model, []).append(c.functional_coverage)
    rows = []
    for i, m in enumerate(sorted(by_model, key=lambda m: -_st.mean(by_model[m])), 1):
        v = by_model[m]
        pmean = _st.mean(v)
        cls = ' class="top"' if i == 1 else ""
        if leaf.get(m):
            lmean = _st.mean(leaf[m])
            lcol, dcol = _hf(lmean), _hf(pmean - lmean)
        else:
            lcol = dcol = "<span class=dimv>—</span>"
        rows.append(
            f"<tr{cls}><td class=rank>{i}</td><td class=model>{_esc(m)}</td>"
            f"<td class=big>{_hf(pmean)}</td><td class=dimv>{len(v)}</td>"
            f"<td>{lcol}</td><td>{dcol}</td></tr>"
        )
    return _h_table(
        ["Rank", "Model", "Pricing coverage (mean)", "Cells", "OB-leaf (mean)", "leaf Δ"], rows
    )


def _h_pricing_discriminators(cells: List[CellResult]) -> str:
    data = _pricing_discriminator_rows(cells)
    if not data:
        return _empty("no pricing-lane cell persisted per-case suite results (degraded or not run)")
    out = []
    for svc in sorted(data):
        cases = data[svc]
        models = sorted({m for case in cases.values() for m in case})
        rows = []
        for case in sorted(cases):
            tds = []
            for m in models:
                if m in cases[case]:
                    p, t = cases[case][m]
                    cell = f"{p}/{t}" if p == t else f'<span class="pill bad">{p}/{t}</span>'
                    tds.append(f"<td>{cell}</td>")
                else:
                    tds.append("<td class=dimv>—</td>")
            rows.append(f"<tr><td class=model>{_esc(case)}</td>" + "".join(tds) + "</tr>")
        headers = ["Case"] + models
        out.append(f"<h4><code>{_esc(svc)}</code></h4>" + _h_table(headers, rows))
    return "".join(out)


def _h_checkout_frontier(cells: List[CellResult]) -> str:
    ran = [c for c in cells if _is_checkout(c) and c.functional_coverage is not None]
    if not ran:
        return _empty("no checkoutservice cells with behavioral coverage were persisted")
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
    return _h_table(["Rank", "Model", "PlaceOrder coverage (mean)", "Cells"], rows)


def _h_checkout_steps(cells: List[CellResult]) -> str:
    data = _checkout_step_rows(cells)
    if not data:
        return _empty(
            "no checkoutservice cell persisted per-step suite results or call-counts "
            "(degraded or not run)"
        )
    models = sorted({m for step in data.values() for m in step})
    rows = []
    for step, _addr in _CHECKOUT_STEPS:
        if step not in data:
            continue
        tds = []
        for m in models:
            if m in data[step]:
                p, t = data[step][m]
                cell = f"{p}/{t}" if p == t else f'<span class="pill bad">{p}/{t}</span>'
                tds.append(f"<td>{cell}</td>")
            else:
                tds.append("<td class=dimv>—</td>")
        rows.append(f"<tr><td class=model>{_esc(step)}</td>" + "".join(tds) + "</tr>")
    return _h_table(["Step"] + models, rows)


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


def _h_headline(agg: Optional[Dict], contam: Optional[dict]) -> str:
    """Headline verdict as HTML — escape, then promote `model` backtick spans to <code>."""
    import re

    txt = re.sub(r"`([^`]+)`", r"<code>\1</code>", _esc(_headline(agg, contam)))
    return f'<p class="headline"><b style="color:var(--brass)">Headline ·</b> {txt}</p>'


def _h_header(
    spec: Dict,
    cells: List[CellResult],
    contam: Optional[dict],
    now: datetime,
    agg: Optional[Dict],
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
        + _h_headline(agg, contam)
        + '<p class="note">Inverted-pyramid: scores first. Every dimension is shown; a source the run '
        "did not persist is marked <b>not computed</b>. Credibility (CodeBLEU) is a leaderboard-integrity "
        "control, not a quality term.</p>"
    )


# Scoreboard caption (dim A — rendered separately, first).
_SB_CAP = (
    "Composite quality (median) — structural × compile-gate × behavioral fold × defect penalty. "
    "Five leaderboards (flagship → providers → all), each ranked best→worst."
)

# Supporting dimensions (B–F), shown below the Scoreboard.
_DIMS: List[Tuple[str, str, str]] = [
    (
        "B",
        "Consistency",
        "Reliability over peak — pass-rate then tightest spread (quality IQR), the axis near-equal flagships differ on (FR-K1).",
    ),
    (
        "C",
        "Credibility — contamination",
        "CodeBLEU similarity to the <b>public</b> Online Boutique upstream. Ranked ascending (least memorized first). A credibility control, not quality (FR-47).",
    ),
    (
        "D",
        "Behavioral coverage",
        "Fraction of behavioral RPC contracts the live service satisfied. Folded into composite at 50% (FR-T2).",
    ),
    (
        "D2",
        "Pricing lane (Liferay discriminator)",
        "Behavioral coverage over the Liferay-derived complex-pricing services only — de-saturates where OB-leaf saturates. <code>leaf Δ</code> = pricing − leaf mean (negative ⇒ harder, as intended). Reported, not scored.",
    ),
    (
        "D3",
        "Pricing discriminators (per-case)",
        "Per-case pass-rate (<code>passed/reps</code>) of the spec-reasoning cases — strategy stacking, rounding mode, tax ordering — by service and model. Where flagships diverge even at even aggregate coverage.",
    ),
    (
        "D4",
        "Checkout integration frontier",
        "PlaceOrder coverage over the six orchestrated dependencies (catalog/cart/currency/shipping/payment/email) — does the model wire six services into one order. A distinct axis from per-service skill (CQ-4). Reported, not scored.",
    ),
    (
        "D5",
        "Checkout orchestration steps (per-step)",
        "Per-step PlaceOrder pass-rate (<code>passed/reps</code>) by model — which of the six dialed dependencies the model wires correctly. The analog of the pricing per-case table for the orchestrator (FR-CO-19).",
    ),
    (
        "E",
        "Determinism boundary",
        "Did the model drift an owned ($0-generated) skeleton file instead of only adding glue (generate backend --check).",
    ),
    (
        "F",
        "By language",
        "Polyglot view — quality, pass-rate, contamination, cost per language.",
    ),
    (
        "G",
        "Refinement trajectory",
        "Does the first draft compile? Advisory diagnostic ($0 from draft artifacts), NOT scored — saturates among frontier models, so the signal is the non-compiling tail (FR-10).",
    ),
]


def _h_refinement(run_dir: Path, cells: List[CellResult]) -> str:
    s = _refinement_summary(run_dir, cells)
    if s is None:
        return _empty("per-draft compile trajectory not computed (no phase-trajectory.json sidecar)")
    feats, fdc = s["feats"], s["fdc"]
    rate = (fdc / feats) if feats else 0.0
    if not s["tail"]:
        return _empty(f"first-draft compiles {fdc}/{feats} ({_hf(rate)}) — saturated, no exceptions")
    rows = []
    for model, svc in s["tail"][:12]:
        rows.append(f"<tr><td class=model>{_esc(model)}</td><td>{_esc(svc)}</td></tr>")
    extra = f" · {s['converged']} recovered by a later draft" if s["converged"] else ""
    rows.append(
        f"<tr><td colspan=2 class=dimv>first-draft compiles {fdc}/{feats} ({_hf(rate)}){extra}</td></tr>"
    )
    return _h_table(["Non-compiling first draft — model", "Service"], rows)


def build_scorecard_html(run_dir, *, now: Optional[datetime] = None) -> str:
    """Render the scorecard as a single self-contained HTML document (same data as the markdown)."""
    run_dir = Path(run_dir)
    now = now or datetime.now(timezone.utc)
    cells = _load_cells(run_dir)
    agg = aggregate_cells(cells) if cells else None
    spec = _spec_meta(run_dir)
    contam = _load_json(run_dir / CONTAMINATION_FILE)
    comparison = _load_json(run_dir / COMPARISON_FILE)

    scoreboard = _h_dim(
        "A", "Scoreboard", _SB_CAP, _h_scoreboard(agg), 0.05
    )  # scores first
    bodies = [
        _h_consistency(agg),
        _h_credibility(contam),
        _h_behavioral(cells),
        _h_pricing_lane(cells),
        _h_pricing_discriminators(cells),
        _h_checkout_frontier(cells),
        _h_checkout_steps(cells),
        _h_determinism(comparison),
        _h_bylang(agg, contam),
        _h_refinement(run_dir, cells),
    ]
    supporting = "".join(
        _h_dim(d[0], d[1], d[2], body, 0.12 + i * 0.07)
        for i, (d, body) in enumerate(zip(_DIMS, bodies))
    )
    ref = (contam or {}).get("reference_root", "")
    foot = (
        "<footer>Generated by <code>build_scorecard_html</code> · "
        "docs/design/benchmark-scorecard/SCORECARD_FORMAT.md v2.0"
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
        + _h_header(spec, cells, contam, now, agg)
        + scoreboard
        + supporting
        + foot
        + "</div></body></html>"
    )


def write_scorecard_html(run_dir, *, now: Optional[datetime] = None) -> Path:
    """Build + write ``<run_dir>/SCORECARD.html``; returns the path."""
    run_dir = Path(run_dir)
    out = run_dir / SCORECARD_HTML_FILE
    out.write_text(build_scorecard_html(run_dir, now=now), encoding="utf-8")
    return out
