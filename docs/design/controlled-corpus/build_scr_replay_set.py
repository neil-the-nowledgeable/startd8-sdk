#!/usr/bin/env python3
"""Track B — Variance segregation + SCR labeled replay set.

Reads the online-boutique pipeline trove and answers two questions:
  1. Cached-vs-fresh / input-stability: did runs share inputs? (source_checksum,
     feature-count clusters) — so we know how much cross-run "consistency" is real.
  2. Per-feature determinism oracle: join kaizen-correlation PASS/FAIL labels to the
     actual feature *binding* (target_file) — NOT the positional PI-id — within a
     scope cluster, segregated by model (gemini vs claude-default).

Emits:
  - scr-variance-segregation.json   (run inventory: checksum, cluster, model)
  - scr-labeled-replay-set.json      (per-(cluster,target_file) PASS/FAIL stability)

Determinism note: this script itself is deterministic (sorted iteration, no rng).
"""
from __future__ import annotations
import json, glob, os, sys
from collections import defaultdict, Counter

TROVE = "/Users/neilyashinsky/Documents/dev/online-boutique-demo/.cap-dev-pipe/pipeline-output/online-boutique"
OUT = "/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/controlled-corpus"


def model_of(run_id: str) -> str:
    """Inferred from run-id prefix (gemini-* vs claude-default). Documented caveat:
    run-NNN runs do not record the model in run-metadata.json; default = claude."""
    return "gemini" if run_id.startswith("gemini") else "claude"


def load_seed(run_id: str):
    p = os.path.join(TROVE, run_id, "plan-ingestion", "prime-context-seed.json")
    try:
        return json.load(open(p))
    except Exception:
        return None


def feature_target(task: dict) -> str:
    cfg = task.get("config", {}) or {}
    ctx = cfg.get("context", {}) or {}
    tf = ctx.get("target_files") or task.get("target_files") or []
    return tf[0] if tf else ""


def main():
    # ---- 1. Run inventory: checksum + cluster + model ----------------------
    run_dirs = sorted(
        d for d in os.listdir(TROVE)
        if os.path.isdir(os.path.join(TROVE, d)) and (d.startswith("run-") or d.startswith("gemini-"))
    )
    inventory = []
    pi_to_target = {}  # (run_id, PI-id) -> target_file
    for rid in run_dirs:
        seed = load_seed(rid)
        if not seed:
            continue
        tasks = seed.get("tasks", [])
        for t in tasks:
            tid = t.get("id") or t.get("task_id")
            if tid:
                pi_to_target[(rid, tid)] = feature_target(t)
        inventory.append({
            "run_id": rid,
            "model": model_of(rid),
            "source_checksum": str(seed.get("source_checksum"))[:16],
            "feature_count": len(tasks),
        })

    # cluster by feature_count
    clusters = defaultdict(list)
    for inv in inventory:
        clusters[inv["feature_count"]].append(inv["run_id"])
    distinct_checksums = len({i["source_checksum"] for i in inventory})

    variance = {
        "trove": TROVE,
        "runs_with_seed": len(inventory),
        "distinct_source_checksums": distinct_checksums,
        "all_inputs_distinct": distinct_checksums == len(inventory),
        "interpretation": (
            "Every run has a distinct source_checksum => seeds were freshly re-derived "
            "(NOT cached) AND the input docs evolved across the dev phase. Cross-run "
            "consistency is therefore real stochastic re-derivation, but it spans MULTIPLE "
            "input scopes. The clean determinism signal is WITHIN a feature-count cluster."
        ),
        "clusters_by_feature_count": {str(k): sorted(v) for k, v in sorted(clusters.items())},
        "model_distribution": dict(Counter(i["model"] for i in inventory)),
        "inventory": inventory,
    }
    json.dump(variance, open(os.path.join(OUT, "scr-variance-segregation.json"), "w"), indent=2)

    # ---- 2. Labeled replay set: join kaizen labels by target_file ----------
    corr = json.load(open(os.path.join(TROVE, "kaizen-correlation.json")))
    points = corr.get("data_points", [])

    # Anchor on the largest repeated cluster (the 17-feature Python set) so
    # PI-id -> target_file is comparable run-to-run.
    anchor_n = max(clusters, key=lambda k: len(clusters[k]))
    anchor_runs = set(clusters[anchor_n])

    # per-target_file stability within the anchor cluster, segregated by model
    by_target = defaultdict(lambda: {"claude": {"pass": 0, "fail": 0}, "gemini": {"pass": 0, "fail": 0},
                                     "runs": set(), "titles": set()})
    labeled = skipped = 0
    for pt in points:
        if pt.get("label_status") != "labeled":
            continue
        rid = pt.get("run_id")
        if rid not in anchor_runs:
            skipped += 1
            continue
        tgt = pi_to_target.get((rid, pt.get("feature_id")))
        if not tgt:
            skipped += 1
            continue
        labeled += 1
        m = model_of(rid)
        bucket = "pass" if pt.get("success") else "fail"
        by_target[tgt][m][bucket] += 1
        by_target[tgt]["runs"].add(rid)

    # also collect the title-drift evidence per target from the seeds
    title_drift = defaultdict(set)
    for rid in anchor_runs:
        seed = load_seed(rid)
        if not seed:
            continue
        for t in seed.get("tasks", []):
            tgt = feature_target(t)
            if tgt:
                title_drift[tgt].add(t.get("title", t.get("name", "")))

    replay = []
    for tgt in sorted(by_target):
        rec = by_target[tgt]
        c, g = rec["claude"], rec["gemini"]
        tot_pass = c["pass"] + g["pass"]
        tot_fail = c["fail"] + g["fail"]
        tot = tot_pass + tot_fail
        replay.append({
            "target_file": tgt,
            "n_observations": tot,
            "n_runs": len(rec["runs"]),
            "pass": tot_pass,
            "fail": tot_fail,
            "stability": round(tot_pass / tot, 3) if tot else None,
            "by_model": {"claude": c, "gemini": g},
            "title_variants": sorted(title_drift.get(tgt, [])),  # the NL residue
            "title_variant_count": len(title_drift.get(tgt, [])),
            "corpus_class": (
                "deterministic_candidate" if tot and tot_pass / tot >= 0.95
                else "residue_corpus_gap" if tot and tot_pass / tot < 0.7
                else "mixed"
            ),
        })
    replay.sort(key=lambda r: (-(r["stability"] or 0), -r["n_observations"]))

    out = {
        "anchor_cluster_feature_count": anchor_n,
        "anchor_runs": sorted(anchor_runs),
        "labeled_points_used": labeled,
        "labeled_points_skipped_outside_cluster_or_unmapped": skipped,
        "join_key": "target_file (NOT positional PI-id)",
        "caveat": (
            "Stability is measured per target_file WITHIN the anchor cluster. "
            "title_variants shows the natural-language drift for the SAME binding "
            "(the stochastic residue the corpus abstracts away)."
        ),
        "features": replay,
    }
    json.dump(out, open(os.path.join(OUT, "scr-labeled-replay-set.json"), "w"), indent=2)

    # ---- console summary ----
    print(f"runs_with_seed={len(inventory)} distinct_checksums={distinct_checksums} "
          f"all_distinct={variance['all_inputs_distinct']}")
    print("clusters_by_feature_count:", {k: len(v) for k, v in sorted(clusters.items())})
    print("model_distribution:", variance["model_distribution"])
    print(f"\nAnchor cluster = {anchor_n} features, {len(anchor_runs)} runs; labeled_used={labeled} skipped={skipped}")
    print(f"{'target_file':52} {'stab':>5} {'n':>3} {'titles':>6} class")
    for r in replay:
        print(f"{r['target_file'][:52]:52} {str(r['stability']):>5} {r['n_observations']:>3} "
              f"{r['title_variant_count']:>6} {r['corpus_class']}")


if __name__ == "__main__":
    main()
