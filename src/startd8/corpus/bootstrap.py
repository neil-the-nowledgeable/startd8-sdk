"""Bootstrap the Controlled Corpus from the online-boutique v0 artifacts (FR-6).

Seeds a registry from:
  - controlled-corpus-v0.json   — proto terms (services/rpcs/entities) + SRE vocab + explicit bindings
  - scr-labeled-replay-set-v2.json — per-target_file determinism (success stability + requirement_score)

The determinism oracle stores aggregates (pass/fail counts, mean requirement_score); we replay
those as observations under synthetic run ids so the corpus computes the correct stability/class.

Usage: python -m startd8.corpus.bootstrap <corpus_v0.json> <oracle_v2.json> <out.json>
"""
from __future__ import annotations

import json
import sys
from typing import List

from startd8.corpus import Binding, ControlledCorpusRegistry, TermObservation
from startd8.corpus.canonical import canonical_key


def _proto_observations(v0: dict) -> List[TermObservation]:
    obs: List[TermObservation] = []
    terms = v0.get("layer_1_canonical_terms", {})
    for svc in terms.get("services", []):
        obs.append(TermObservation(
            kind="service", canonical_key=canonical_key("service", svc["name"]),
            surface_form=svc["name"], confidence="explicit",
            bindings=[Binding("proto", "service", svc["name"], "proto")]))
        for rpc in svc.get("rpcs", []):
            ref = f"{svc['name']}.{rpc['name']}"
            obs.append(TermObservation(
                kind="rpc", canonical_key=canonical_key("rpc", ref), surface_form=ref,
                confidence="explicit",
                bindings=[Binding("proto", "rpc", ref, "proto")]))
    for ent in terms.get("entities", []):
        obs.append(TermObservation(
            kind="entity", canonical_key=canonical_key("entity", ent["name"]),
            surface_form=ent["name"], confidence="explicit",
            bindings=[Binding("proto", "message", ent["name"], "proto")]))
    sre = v0.get("layer_3_sre_observability_vocab", {})
    for m in sre.get("metrics", []):
        obs.append(TermObservation(kind="metric", canonical_key=canonical_key("metric", m),
                                   surface_form=m, confidence="explicit",
                                   bindings=[Binding("prometheus", "metric", m, "deterministic")]))
    return obs


def bootstrap(v0_path: str, oracle_path: str, out_path: str) -> ControlledCorpusRegistry:
    v0 = json.load(open(v0_path))
    oracle = json.load(open(oracle_path))
    reg = ControlledCorpusRegistry(project_id="online-boutique")

    # 1. proto + SRE terms as a single synthetic 'corpus-v0' run
    reg.merge_run("corpus-v0", _proto_observations(v0))

    # 2. determinism per target_file — replay aggregate pass/fail as observations
    for feat in oracle.get("features", []):
        tgt = feat["target_file"]
        req = feat.get("mean_requirement_score")
        npass, nfail = feat.get("pass", 0), feat.get("fail", 0)
        surfaces = feat.get("title_variants") or [tgt]
        ck = canonical_key("file", surfaces[0], tgt)
        i = 0
        for _ in range(npass):
            reg.merge_run(f"replay-{tgt}-p{i}", [TermObservation(
                kind="file", canonical_key=ck, surface_form=surfaces[i % len(surfaces)],
                bindings=[Binding("python", "file", tgt, "deterministic")],
                confidence="explicit", success=True, requirement_score=req)]); i += 1
        for _ in range(nfail):
            reg.merge_run(f"replay-{tgt}-f{i}", [TermObservation(
                kind="file", canonical_key=ck, surface_form=surfaces[i % len(surfaces)],
                bindings=[Binding("python", "file", tgt, "deterministic")],
                confidence="explicit", success=False, requirement_score=req)]); i += 1

    reg.save(out_path)
    return reg


def main():
    v0, oracle, out = sys.argv[1], sys.argv[2], sys.argv[3]
    reg = bootstrap(v0, oracle, out)
    from collections import Counter
    classes = Counter(t.determinism.corpus_class for t in reg.terms)
    kinds = Counter(t.kind for t in reg.terms)
    print(f"corpus terms: {len(reg)}  -> {out}")
    print("by kind:", dict(kinds))
    print("by determinism class:", dict(classes))
    fpr = reg.by_class("false_pass_risk")
    if fpr:
        print("false_pass_risk terms:", [t.canonical_key for t in fpr])


if __name__ == "__main__":
    main()
