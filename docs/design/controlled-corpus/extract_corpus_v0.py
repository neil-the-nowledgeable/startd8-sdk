#!/usr/bin/env python3
"""Track A — Extract controlled-corpus-v0 from the online-boutique trove.

Three corpus layers, distilled into one artifact:
  1. Canonical term layer  — parse demo.proto (hipstershop): services, RPCs, entities+fields.
  2. Binding layer         — EXPLICIT-confidence forward_manifest contracts (curated, not the
                             1655 inferred-noise ones), grouped by category.
  3. SRE/observability vocab — metric names, SLO targets, env-var lexicon from a run's
                             observability artifacts + onboarding semantic_conventions.

Optionally merges per-target_file stability from scr-labeled-replay-set.json (Track B) if present,
so each binding can carry its own determinism evidence.

Emits: controlled-corpus-v0.json  (+ console summary)
Deterministic: sorted iteration, no rng.
"""
from __future__ import annotations
import json, os, re, glob
from collections import defaultdict

TROVE = "/Users/neilyashinsky/Documents/dev/online-boutique-demo/.cap-dev-pipe/pipeline-output/online-boutique"
PROTO = "/Users/neilyashinsky/Documents/dev/online-boutique-demo/.cap-dev-pipe/context/demo.proto"
OUT = "/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/controlled-corpus"


def _block_body(txt: str, open_idx: int):
    """Return (body, end_idx) for the balanced {...} starting at the '{' at open_idx."""
    depth, i = 0, open_idx
    while i < len(txt):
        if txt[i] == "{":
            depth += 1
        elif txt[i] == "}":
            depth -= 1
            if depth == 0:
                return txt[open_idx + 1:i], i
        i += 1
    return txt[open_idx + 1:], len(txt)


def parse_proto(path: str):
    """Balanced-brace parser: services{rpc...} and messages{fields...}.
    Handles rpc method `{}` bodies that would truncate a naive non-greedy capture."""
    txt = re.sub(r"//[^\n]*", "", open(path).read())  # strip // comments
    services, messages = [], []
    for m in re.finditer(r"\bservice\s+(\w+)\s*\{", txt):
        body, _ = _block_body(txt, m.end() - 1)
        rpcs = [
            {"name": r.group(1), "request": r.group(2), "response": r.group(3)}
            for r in re.finditer(
                r"rpc\s+(\w+)\s*\(\s*([\w.]+)\s*\)\s*returns\s*\(\s*([\w.]+)\s*\)", body)
        ]
        services.append({"name": m.group(1), "protocol": "grpc", "rpcs": rpcs})
    for m in re.finditer(r"\bmessage\s+(\w+)\s*\{", txt):
        body, _ = _block_body(txt, m.end() - 1)
        fields = [
            {"name": f.group(3), "type": f.group(2), "repeated": bool(f.group(1))}
            for f in re.finditer(r"(?:(repeated)\s+)?([\w.]+)\s+(\w+)\s*=\s*\d+", body)
        ]
        messages.append({"name": m.group(1), "fields": fields})
    return services, messages


def load_explicit_contracts():
    """Pull EXPLICIT-confidence contracts from a representative seed's forward_manifest."""
    # prefer the largest/most-recent seed
    seeds = sorted(glob.glob(os.path.join(TROVE, "run-*/plan-ingestion/prime-context-seed.json")))
    if not seeds:
        return {}, None
    # pick the latest run as representative
    seed_path = seeds[-1]
    d = json.load(open(seed_path))
    fm = d.get("forward_manifest", {}) or {}
    contracts = fm.get("contracts", [])
    by_cat = defaultdict(list)
    for c in contracts:
        if c.get("confidence") != "explicit":
            continue
        cat = c.get("category")
        entry = {
            "id": c.get("contract_id"),
            "binding_text": c.get("binding_text"),
            "description": c.get("description"),
        }
        # keep the category-specific payload field
        for k in ("class_name", "function_name", "endpoint", "env_var", "formula",
                  "pattern", "import_path", "constant_value", "base_class"):
            if c.get(k):
                entry[k] = c[k]
        by_cat[cat].append(entry)
    return {k: v for k, v in by_cat.items()}, os.path.basename(os.path.dirname(os.path.dirname(seed_path)))


def extract_sre_vocab():
    """Metric names, SLO targets, alert patterns, env-vars from observability + onboarding."""
    metrics, slo_targets, alerts, env_vars = set(), {}, set(), set()
    # observability artifacts in any run
    for slo in glob.glob(os.path.join(TROVE, "*/observability/slos/*")):
        try:
            txt = open(slo).read()
            for mm in re.finditer(r"(availability|latency_p\d+|error_rate)\D{0,20}?([\d.]+)", txt):
                slo_targets[mm.group(1)] = mm.group(2)
        except Exception:
            pass
    for dash in glob.glob(os.path.join(TROVE, "*/observability/**/*"), recursive=True):
        if not os.path.isfile(dash):
            continue
        try:
            txt = open(dash).read()
            for mm in re.finditer(r"\b(rpc_server_\w+|startd8_\w+|http_server_\w+)\b", txt):
                metrics.add(mm.group(1))
            for am in re.finditer(r'"?(\w+(?:LatencyP\d+High|ErrorRateHigh|AvailabilityLow))"?', txt):
                alerts.add(am.group(1))
        except Exception:
            pass
    # env-vars from onboarding + seeds
    for ob in glob.glob(os.path.join(TROVE, "*/onboarding-metadata.json"))[:3]:
        try:
            s = open(ob).read()
            for ev in re.finditer(r"\b([A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]+){1,5})\b", s):
                tok = ev.group(1)
                if any(tok.endswith(suf) or suf in tok for suf in
                       ("_ADDR", "_PORT", "TRACING", "_TYPE", "_HOST", "_ENDPOINT", "_KEY", "_URL")):
                    env_vars.add(tok)
        except Exception:
            pass
    return {
        "metrics": sorted(metrics),
        "slo_targets": slo_targets,
        "alert_patterns": sorted(alerts),
        "env_vars": sorted(env_vars),
    }


def merge_stability(services, messages):
    """If Track B's replay set exists, attach per-target stability hints."""
    rp = os.path.join(OUT, "scr-labeled-replay-set.json")
    if not os.path.exists(rp):
        return None
    data = json.load(open(rp))
    return {
        "source": "scr-labeled-replay-set.json",
        "anchor_cluster_feature_count": data.get("anchor_cluster_feature_count"),
        "deterministic_candidates": [f["target_file"] for f in data.get("features", [])
                                     if f.get("corpus_class") == "deterministic_candidate"],
        "residue_corpus_gaps": [f["target_file"] for f in data.get("features", [])
                                if f.get("corpus_class") == "residue_corpus_gap"],
    }


def main():
    services, messages = parse_proto(PROTO)
    bindings, rep_run = load_explicit_contracts()
    sre = extract_sre_vocab()
    stability = merge_stability(services, messages)

    corpus = {
        "corpus_version": "0.1",
        "domain": "service-web-app / google-microservices-demo (hipstershop)",
        "provenance": {
            "proto": PROTO,
            "representative_seed_run": rep_run,
            "trove": TROVE,
        },
        "layer_1_canonical_terms": {
            "services": services,
            "service_count": len(services),
            "rpc_count": sum(len(s["rpcs"]) for s in services),
            "entities": messages,
            "entity_count": len(messages),
        },
        "layer_2_explicit_bindings": {
            "note": "EXPLICIT-confidence forward_manifest contracts only (inferred-noise excluded).",
            "counts": {k: len(v) for k, v in sorted(bindings.items())},
            "by_category": bindings,
        },
        "layer_3_sre_observability_vocab": sre,
        "layer_4_determinism_evidence": stability or
            {"note": "run build_scr_replay_set.py first to attach per-binding stability"},
    }
    json.dump(corpus, open(os.path.join(OUT, "controlled-corpus-v0.json"), "w"), indent=2)

    # ---- console summary ----
    print(f"PROTO: {len(services)} services, {sum(len(s['rpcs']) for s in services)} rpcs, "
          f"{len(messages)} entities")
    for s in services:
        print(f"  {s['name']:26} rpcs: {', '.join(r['name'] for r in s['rpcs'])}")
    print(f"\nEXPLICIT bindings (run {rep_run}):", {k: len(v) for k, v in sorted(bindings.items())})
    print("SRE metrics:", sre["metrics"])
    print("SLO targets:", sre["slo_targets"])
    print("alert patterns:", sre["alert_patterns"][:6])
    print("env vars:", sre["env_vars"][:12])
    if stability:
        print("determinism: det_candidates=%d residue_gaps=%d"
              % (len(stability["deterministic_candidates"]), len(stability["residue_corpus_gaps"])))


if __name__ == "__main__":
    main()
