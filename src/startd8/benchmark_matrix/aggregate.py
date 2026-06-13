"""Distribution-appropriate aggregation of matrix results (FR-17 / FR-15 / R1-S5).

Quality is bounded [0,1] and typically bimodal (works/doesn't), so bare mean/stdev over
small N is misleading. We report **median + IQR + per-cell pass-rate**, and tally
**catastrophic failures** ($0 / failed / timeout / integrity_fail) separately so a single
bad run can't dominate the central summary. Pure stdlib (no numpy).
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional, Sequence

from .runner import (
    STATUS_INFRA_FAIL,
    STATUS_INTEGRITY_FAIL,
    STATUS_OK,
    STATUS_TIMEOUT,
    STATUS_FAILED,
    STATUS_BUDGET_SKIP,
    CellResult,
)

# Cells that did not produce a fair model signal — excluded from the model's pass-rate
# denominator and never counted catastrophic (the model isn't at fault).
_EXCLUDED_STATUSES = (STATUS_BUDGET_SKIP, STATUS_INFRA_FAIL)

DEFAULT_PASS_THRESHOLD = 0.5  # quality at/above this AND status ok == "pass"


def _median(xs: Sequence[float]) -> Optional[float]:
    return statistics.median(xs) if xs else None


def _iqr(xs: Sequence[float]) -> Optional[float]:
    """Interquartile range (Q3 - Q1). Needs >= 2 points; returns 0.0 for a single point."""
    if not xs:
        return None
    if len(xs) == 1:
        return 0.0
    q = statistics.quantiles(xs, n=4, method="inclusive")  # [Q1, Q2, Q3]
    return q[2] - q[0]


def _is_pass(c: CellResult, threshold: float) -> bool:
    return c.status == STATUS_OK and c.quality is not None and c.quality >= threshold


def _is_catastrophic(c: CellResult) -> bool:
    if c.status in (STATUS_FAILED, STATUS_TIMEOUT, STATUS_INTEGRITY_FAIL):
        return True
    return c.quality is not None and c.quality == 0.0


def summarize_group(cells: List[CellResult], pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> Dict:
    """Distribution summary for one group of repetitions/cells."""
    scored = [c for c in cells if c.status == STATUS_OK and c.quality is not None]
    qualities = [c.quality for c in scored]
    costs = [c.cost_usd for c in cells if c.cost_usd is not None]
    latencies = [c.latency_s for c in cells if c.latency_s is not None]
    tps = [c.tokens_per_sec for c in cells if c.tokens_per_sec is not None]
    ran = [c for c in cells if c.status not in _EXCLUDED_STATUSES]
    passes = sum(1 for c in cells if _is_pass(c, pass_threshold))
    infra = sum(1 for c in cells if c.status == STATUS_INFRA_FAIL)
    return {
        "n": len(cells),
        "n_ran": len(ran),
        "n_scored": len(scored),
        "infra_fail_count": infra,  # auth/access/rate-limit — excluded, not the model's fault
        "quality_median": _median(qualities),
        "quality_iqr": _iqr(qualities),
        "pass_rate": (passes / len(ran)) if ran else None,
        "catastrophic_count": sum(1 for c in cells if _is_catastrophic(c)),
        "cost_total_usd": sum(costs) if costs else 0.0,
        "cost_mean_usd": statistics.mean(costs) if costs else None,
        "latency_median_s": _median(latencies),
        "tokens_per_sec_median": _median(tps),
    }


def aggregate_cells(cells: List[CellResult], pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> Dict:
    """Roll up matrix cells by (service, model), by model, and by language (FR-15)."""
    def _group(key_fn):
        groups: Dict = {}
        for c in cells:
            groups.setdefault(key_fn(c), []).append(c)
        return {k: summarize_group(v, pass_threshold) for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))}

    return {
        "pass_threshold": pass_threshold,
        "overall": summarize_group(cells, pass_threshold),
        "by_service_model": {f"{s}|{m}": v for (s, m), v in
                             _group(lambda c: (c.service, c.model)).items()},
        "by_model": _group(lambda c: c.model),
        "by_language": _group(lambda c: c.language),
        "by_service": _group(lambda c: c.service),
    }


def rank_models_by_quality(agg: Dict) -> List[tuple]:
    """(model, quality_median, pass_rate, cost_total) sorted best-first (quality desc, then cost asc)."""
    rows = []
    for model, s in agg["by_model"].items():
        rows.append((model, s["quality_median"], s["pass_rate"], s["cost_total_usd"]))
    rows.sort(key=lambda r: (-(r[1] if r[1] is not None else -1.0), r[3]))
    return rows


def build_matrix_markdown(spec_name: str, spec_hash: str, agg: Dict) -> str:
    """Leaderboard markdown (FR-15): per-model quality/pass-rate/cost, ranked best-first."""
    lines = [
        f"# Online Boutique Model Benchmark — {spec_name}",
        f"`spec {spec_hash[:12]}`  ·  pass-threshold {agg['pass_threshold']}",
        "",
        "> Quality = median composite score; spread = IQR; pass-rate over cells that ran; "
        "catastrophic = $0/failed/timeout/integrity-fail (reported separately, FR-17).",
        "",
        "## Leaderboard (by median quality, then cost)",
        "",
        "| Rank | Model | quality (median) | IQR | pass-rate | catastrophic | cost $ |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for i, (model, _q, _pr, _ct) in enumerate(rank_models_by_quality(agg), 1):
        s = agg["by_model"][model]
        def f(x, p=3):
            return f"{x:.{p}f}" if isinstance(x, (int, float)) else "N/A"
        lines.append(
            f"| {i} | `{model}` | {f(s['quality_median'])} | {f(s['quality_iqr'])} | "
            f"{f(s['pass_rate'])} | {s['catastrophic_count']}/{s['n']} | {f(s['cost_total_usd'],4)} |"
        )
    lines += ["", "## By language (polyglot view)", "",
              "| Language | quality (median) | pass-rate | cost $ |", "|---|---:|---:|---:|"]
    for lang, s in agg["by_language"].items():
        def f(x, p=3):
            return f"{x:.{p}f}" if isinstance(x, (int, float)) else "N/A"
        lines.append(f"| {lang} | {f(s['quality_median'])} | {f(s['pass_rate'])} | {f(s['cost_total_usd'],4)} |")
    return "\n".join(lines) + "\n"
