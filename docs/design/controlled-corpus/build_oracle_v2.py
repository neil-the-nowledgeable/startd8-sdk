#!/usr/bin/env python3
"""Determinism oracle v2 — widened, multi-signal, direct from postmortems.

v1 (build_scr_replay_set.py) joined kaizen-correlation's sparse PASS/FAIL (49 obs).
v2 reads each anchor run's prime-postmortem-report.json directly, giving more runs and
richer per-feature signals (requirement_score, disk_quality_score, assembly_delta,
semantic_error_count) keyed on target_file, segregated by model.

Emits: scr-labeled-replay-set-v2.json  (+ console summary)
Deterministic: sorted iteration, no rng.
"""
from __future__ import annotations
import json, os
from collections import defaultdict
from statistics import mean

TROVE = "/Users/neilyashinsky/Documents/dev/online-boutique-demo/.cap-dev-pipe/pipeline-output/online-boutique"
OUT = "/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/controlled-corpus"
SEG = os.path.join(OUT, "scr-variance-segregation.json")


def model_of(rid): return "gemini" if rid.startswith("gemini") else "claude"


def main():
    seg = json.load(open(SEG))
    anchor = sorted(seg["clusters_by_feature_count"]["17"])

    agg = defaultdict(lambda: {
        "obs": [], "titles": set(), "models": defaultdict(lambda: {"pass": 0, "fail": 0}),
        "runs": set(),
    })
    runs_used, runs_missing = [], []
    for rid in anchor:
        pm_path = os.path.join(TROVE, rid, "plan-ingestion", "prime-postmortem-report.json")
        if not os.path.exists(pm_path):
            runs_missing.append(rid)
            continue
        runs_used.append(rid)
        pm = json.load(open(pm_path))
        m = model_of(rid)
        for f in pm.get("features", []):
            tfs = f.get("target_files") or []
            tgt = tfs[0] if tfs else f.get("feature_id", "?")
            rec = agg[tgt]
            ok = bool(f.get("success"))
            rec["obs"].append({
                "run": rid, "model": m, "success": ok,
                "verdict": f.get("verdict"),
                "requirement_score": f.get("requirement_score"),
                "disk_quality_score": f.get("disk_quality_score"),
                "assembly_delta": f.get("assembly_delta"),
                "semantic_error_count": f.get("semantic_error_count"),
            })
            rec["titles"].add(f.get("name", ""))
            rec["models"][m]["pass" if ok else "fail"] += 1
            rec["runs"].add(rid)

    def safe_mean(xs):
        xs = [x for x in xs if isinstance(x, (int, float))]
        return round(mean(xs), 3) if xs else None

    def classify(stab, req):
        """Combine STRUCTURAL stability (success) with SEMANTIC compliance
        (requirement_score). A structurally-stable feature with low requirement_score
        is a FALSE-PASS risk — the SCR's core target — not a deterministic candidate."""
        if stab is None:
            return "mixed"
        if stab >= 0.95 and (req is None or req >= 0.9):
            return "deterministic_candidate"
        if stab >= 0.95 and req is not None and req < 0.7:
            return "false_pass_risk"            # stable build, unmet requirement
        if stab < 0.7:
            return "residue_corpus_gap"
        return "mixed"

    features = []
    for tgt in sorted(agg):
        rec = agg[tgt]
        obs = rec["obs"]
        n = len(obs)
        npass = sum(1 for o in obs if o["success"])
        stab = round(npass / n, 3) if n else None
        features.append({
            "target_file": tgt,
            "n_observations": n,
            "n_runs": len(rec["runs"]),
            "pass": npass, "fail": n - npass,
            "stability": stab,
            "by_model": {m: dict(v) for m, v in rec["models"].items()},
            "mean_requirement_score": safe_mean([o["requirement_score"] for o in obs]),
            "mean_disk_quality_score": safe_mean([o["disk_quality_score"] for o in obs]),
            "mean_assembly_delta": safe_mean([o["assembly_delta"] for o in obs]),
            "any_semantic_errors": any((o["semantic_error_count"] or 0) > 0 for o in obs),
            "title_variants": sorted(t for t in rec["titles"] if t),
            "title_variant_count": len({t for t in rec["titles"] if t}),
            "corpus_class": classify(stab, safe_mean([o["requirement_score"] for o in obs])),
        })
    features.sort(key=lambda r: (-(r["stability"] or 0), -r["n_observations"]))

    total_obs = sum(f["n_observations"] for f in features)
    out = {
        "oracle_version": "2.0",
        "method": "direct per-feature join from prime-postmortem-report.json, keyed on target_file",
        "anchor_cluster_feature_count": 17,
        "anchor_runs_total": len(anchor),
        "anchor_runs_with_postmortem": len(runs_used),
        "runs_used": runs_used,
        "runs_missing_postmortem": runs_missing,
        "total_observations": total_obs,
        "v1_observations_for_comparison": 49,
        "distinct_target_files": len(features),
        "caveat": (
            f"{len(runs_used)}/{len(anchor)} anchor runs have a postmortem; the rest predate "
            "postmortem emission or failed. Still multi-signal and wider than v1's 49 obs. "
            "Model mix remains Claude-dominated."
        ),
        "features": features,
    }
    json.dump(out, open(os.path.join(OUT, "scr-labeled-replay-set-v2.json"), "w"), indent=2)

    print(f"anchor runs with postmortem: {len(runs_used)}/{len(anchor)} | total observations: "
          f"{total_obs} (v1 was 49) | distinct target_files: {len(features)}")
    print(f"{'target_file':52} {'stab':>5} {'n':>3} {'reqsc':>5} {'dqs':>5} {'titles':>6} class")
    for f in features:
        print(f"{f['target_file'][:52]:52} {str(f['stability']):>5} {f['n_observations']:>3} "
              f"{str(f['mean_requirement_score']):>5} {str(f['mean_disk_quality_score']):>5} "
              f"{f['title_variant_count']:>6} {f['corpus_class']}")


if __name__ == "__main__":
    main()
