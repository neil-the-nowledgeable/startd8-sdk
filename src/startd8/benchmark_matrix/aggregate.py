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
    STATUS_DEPS_MISSING,
    STATUS_INFRA_FAIL,
    STATUS_INTEGRITY_FAIL,
    STATUS_OK,
    STATUS_TIMEOUT,
    STATUS_FAILED,
    STATUS_BUDGET_SKIP,
    CellResult,
)

# Cells that did not produce a fair model signal — excluded from the model's pass-rate
# denominator and never counted catastrophic (the model isn't at fault). DEPS_MISSING = the
# generated service imports a required external dep (gRPC/proto stubs) absent in the offline
# sandbox — same fairness rationale as the Java/C# missing-dep degrade.
_EXCLUDED_STATUSES = (STATUS_BUDGET_SKIP, STATUS_INFRA_FAIL, STATUS_DEPS_MISSING)

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


def rank_models_by_consistency(agg: Dict) -> List[tuple]:
    """(model, pass_rate, quality_iqr, n_scored, n) sorted most-consistent first (FR-K1-2).

    Consistency ranks *reliability over peak*: highest pass-rate first, then tightest spread
    (lowest quality-IQR). A model that passes reliably with low variance outranks a
    higher-median-but-erratic model — the dimension near-equal flagships actually differ on.
    Complements ``rank_models_by_quality`` (peak); both are views over the SAME per-model
    aggregates (no new per-cell data). Missing values sort last.
    """
    rows = []
    for model, s in agg["by_model"].items():
        rows.append((model, s["pass_rate"], s["quality_iqr"], s["n_scored"], s["n"]))
    rows.sort(
        key=lambda r: (
            -(r[1] if r[1] is not None else -1.0),       # higher pass-rate first
            (r[2] if r[2] is not None else float("inf")),  # tighter IQR first
        )
    )
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
    lines += ["", "## Consistency (most reliable first)", "",
              "> Reliability over peak: ranked by pass-rate, then tightest spread (quality IQR). "
              "`scored/n` below 1 (⚠️) means some repetitions were excluded (infra/budget) — a "
              "smaller effective sample, so read its spread with caution (FR-K1-3).", "",
              "| Rank | Model | pass-rate | quality IQR | scored/n | catastrophic |",
              "|---:|---|---:|---:|---:|---:|"]
    for i, (model, _pr, _iqr, _ns, _n) in enumerate(rank_models_by_consistency(agg), 1):
        s = agg["by_model"][model]
        def f(x, p=3):
            return f"{x:.{p}f}" if isinstance(x, (int, float)) else "N/A"
        flag = " ⚠️" if s["n_scored"] < s["n"] else ""
        lines.append(
            f"| {i} | `{model}` | {f(s['pass_rate'])} | {f(s['quality_iqr'])} | "
            f"{s['n_scored']}/{s['n']}{flag} | {s['catastrophic_count']}/{s['n']} |"
        )
    lines += ["", "## By language (polyglot view)", "",
              "| Language | quality (median) | pass-rate | cost $ |", "|---|---:|---:|---:|"]
    for lang, s in agg["by_language"].items():
        def f(x, p=3):
            return f"{x:.{p}f}" if isinstance(x, (int, float)) else "N/A"
        lines.append(f"| {lang} | {f(s['quality_median'])} | {f(s['pass_rate'])} | {f(s['cost_total_usd'],4)} |")
    return "\n".join(lines) + "\n"


# --- K2: leverage delta (FR-K2-3) -------------------------------------------

# A coordinate's arm is unusable for a paired delta if it didn't cleanly score. Reason codes
# unify R1-S3 (infra), R2-S4 (budget abort), R3-S3 (cap breach → budget_skip), R4-S5 (timeout).
_UNPAIRED_REASON = {
    STATUS_INFRA_FAIL: "infra_fail",
    STATUS_BUDGET_SKIP: "budget_skip",
    STATUS_TIMEOUT: "timeout",
    STATUS_INTEGRITY_FAIL: "integrity_fail",
    STATUS_FAILED: "failed",
}


def _coord(c: CellResult):
    """Pairing key — the coordinate shared by a leverage off/on pair."""
    return (c.service, c.model, c.repetition)


def _scorable(c: Optional[CellResult]) -> bool:
    return c is not None and c.status == STATUS_OK and c.quality is not None


def leverage_delta(cells: List[CellResult],
                   pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> Dict:
    """Per-model leverage delta (FR-K2-3) via **paired** statistics (R3-S2): compute Δ per matched
    (service, model, rep) coordinate, then take the **median across pairs** — NOT
    ``median(on) − median(off)`` (the paired and unpaired estimators diverge at small bimodal N).

    A coordinate enters the delta only when **both** arms scored (status OK + quality present);
    otherwise it is dropped with a **reason code** (unified unpaired-coordinate policy: infra /
    budget / cap / timeout / integrity / failed / missing). Also records on-cell skip intensity
    (R2-S5), a `leverage_regressed` flag (R4-S3), and `branch_divergent_pairs` where the scoring
    branch differed across the pair (R5-S4 — those deltas are scorer-confounded, not pure leverage).
    """
    off = {_coord(c): c for c in cells if getattr(c, "leverage", "off") == "off"}
    on = {_coord(c): c for c in cells if getattr(c, "leverage", "off") == "on"}
    per_model: Dict[str, Dict] = {}
    unpaired: List[Dict] = []

    for coord in sorted(set(off) | set(on)):
        oc, nc = off.get(coord), on.get(coord)
        service, model, rep = coord
        if not (_scorable(oc) and _scorable(nc)):
            reason, arm = "missing", None
            for c, a in ((oc, "off"), (nc, "on")):
                if c is None:
                    reason, arm = "missing", a
                elif not _scorable(c):
                    reason, arm = _UNPAIRED_REASON.get(c.status, "unscored"), a
                    break
            unpaired.append({"service": service, "model": model, "repetition": rep,
                             "reason": reason, "arm": arm})
            continue
        d = per_model.setdefault(model, {"dq": [], "dcost": [], "on_skips": [],
                                         "off_cost": [], "on_cost": [], "branch_divergent": 0,
                                         "pairs": []})
        dq = nc.quality - oc.quality
        dcost = (nc.cost_usd or 0.0) - (oc.cost_usd or 0.0)
        divergent = (oc.compile_ok, oc.degraded) != (nc.compile_ok, nc.degraded)
        d["dq"].append(dq)
        d["dcost"].append(dcost)
        d["on_skips"].append(nc.deterministic_skips)
        d["off_cost"].append(oc.cost_usd or 0.0)
        d["on_cost"].append(nc.cost_usd or 0.0)
        d["branch_divergent"] += int(divergent)
        d["pairs"].append({"service": service, "repetition": rep,
                           "delta_quality": round(dq, 4), "delta_cost": round(dcost, 6),
                           "branch_divergent": divergent})

    models: Dict[str, Dict] = {}
    for m, d in per_model.items():
        dq_med = _median(d["dq"])
        dcost_tot = sum(d["dcost"])
        models[m] = {
            "n_pairs": len(d["dq"]),
            "delta_quality_median": dq_med,
            "delta_quality_iqr": _iqr(d["dq"]),
            "delta_cost_total": round(dcost_tot, 6),
            "on_skips_median": _median(d["on_skips"]),
            "off_cost_total": round(sum(d["off_cost"]), 6),
            "on_cost_total": round(sum(d["on_cost"]), 6),
            "branch_divergent_pairs": d["branch_divergent"],
            "leverage_regressed": bool(dq_med is not None
                                       and (dq_med < 0 or (dcost_tot > 0 and dq_med <= 0))),
            "pairs": d["pairs"],
        }
    return {
        "pass_threshold": pass_threshold,
        "n_pairs": sum(s["n_pairs"] for s in models.values()),
        "unpaired_count": len(unpaired),
        "by_model": dict(sorted(models.items(),
                                key=lambda kv: (kv[1]["delta_quality_median"] is None,
                                                -(kv[1]["delta_quality_median"] or 0.0)))),
        "unpaired": unpaired,
    }


def build_leverage_delta_markdown(delta: Dict) -> str:
    """Render the K2 delta table (FR-K2-3). Empty string when no paired data."""
    if not delta or not delta.get("by_model"):
        return ""

    def f(x, p=3):
        return f"{x:.{p}f}" if isinstance(x, (int, float)) else "N/A"

    lines = [
        "## Leverage delta (K2 — SDK leverage OFF→ON, paired per coordinate)",
        "",
        f"> {delta['n_pairs']} paired coordinates; {delta['unpaired_count']} unpaired (excluded — "
        "see `pairing_audit.json`). ΔQuality = median of per-coordinate (on − off); "
        "**regressed** = SDK leverage hurt quality (or cost it nothing).",
        "",
        "| Model | Δquality (median) | IQR | Δcost $ | on-skips (median) | regressed | n pairs | branch-divergent |",
        "|---|---:|---:|---:|---:|:--:|---:|---:|",
    ]
    for m, s in delta["by_model"].items():
        reg = "⚠ yes" if s["leverage_regressed"] else "no"
        lines.append(
            f"| `{m}` | {f(s['delta_quality_median'])} | {f(s['delta_quality_iqr'])} | "
            f"{f(s['delta_cost_total'], 4)} | {f(s['on_skips_median'], 1)} | {reg} | "
            f"{s['n_pairs']} | {s['branch_divergent_pairs']} |")
    return "\n".join(lines) + "\n"
