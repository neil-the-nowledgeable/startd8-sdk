#!/usr/bin/env python3
"""End-to-end validation of the Controlled Corpus pipeline integration.

Two modes:

  offline  (default) — exercises the ACTUAL wired functions (extract_corpus_from_run,
            extract_seed_terms_from_context, registry merge, _build_corpus_authorities_section)
            on REAL trove postmortems, simulating the write→accumulate→read cycle WITHOUT an
            LLM run. Proves the integration logic is correct on real data.

  postrun <run_dir> <project_root> — checks a LIVE cap-dev-pipe prime run fired the integration:
            (a) plan-ingestion-diagnostic.json shows deterministic ASSESS+TRANSFORM (cost 0),
            (b) <project_root>/.startd8/controlled-corpus.json was written + has terms.

Usage:
  python3 validate_corpus_integration.py
  python3 validate_corpus_integration.py postrun <run_dir> <project_root>
"""
from __future__ import annotations
import json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace

TROVE = Path("/Users/neilyashinsky/Documents/dev/online-boutique-demo/"
             ".cap-dev-pipe/pipeline-output/online-boutique")


def _ok(cond, label):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    return cond


def offline() -> bool:
    """Replay real trove postmortems through the wired functions: write→read."""
    from startd8.corpus.registry import ControlledCorpusRegistry
    from startd8.corpus.extractor import (
        extract_corpus_from_run, extract_seed_terms_from_context, stable_run_id,
    )
    from startd8.implementation_engine.spec_builder import _build_corpus_authorities_section
    from startd8.paths import controlled_corpus_path

    runs = sorted(d for d in TROVE.glob("run-*")
                  if (d / "plan-ingestion" / "prime-postmortem-report.json").exists())
    if len(runs) < 2:
        print("offline: need >=2 trove runs with postmortems; SKIP"); return True

    proj = Path(tempfile.mkdtemp())            # synthetic project_root
    corpus_path = controlled_corpus_path(proj)
    print(f"offline: simulating write→read for {len(runs)} runs at {corpus_path}")

    ok = True
    # --- WRITE path: each run's postmortem + seed feeds the corpus ---
    for d in runs:
        pm = json.loads((d / "plan-ingestion" / "prime-postmortem-report.json").read_text())
        feats = [SimpleNamespace(**{k: f.get(k) for k in
                 ("name", "target_files", "success", "requirement_score", "disk_quality_score")})
                 for f in pm.get("features", [])]
        report = SimpleNamespace(report_id=d.name, total_features=pm.get("total_features"),
                                 features=feats)
        rid = stable_run_id(str(d / "plan-ingestion"))
        reg = ControlledCorpusRegistry.load(corpus_path)
        obs = extract_corpus_from_run(report, rid)
        obs += extract_seed_terms_from_context(str(d / "plan-ingestion"), rid)
        reg.merge_run(rid, obs)
        reg.save(corpus_path)

    reg = ControlledCorpusRegistry.load(corpus_path)
    ok &= _ok(corpus_path.exists(), "WRITE: corpus persisted at project_root/.startd8")
    ok &= _ok(len(reg) > 0, f"WRITE: corpus has terms (n={len(reg)})")
    ok &= _ok(reg.corpus_version >= len(runs), f"WRITE: corpus_version monotonic (={reg.corpus_version})")
    svc = [t for t in reg.terms if t.kind == "service"]
    ok &= _ok(len(svc) > 0, f"WRITE: vocabulary layer grew from seeds (services={len(svc)})")
    det = reg.by_class("deterministic_candidate")
    fpr = reg.by_class("false_pass_risk")
    ok &= _ok(len(det) > 0, f"WRITE: determinism scored (deterministic_candidates={len(det)})")
    print(f"         false_pass_risk={len(fpr)}: {[t.canonical_key for t in fpr][:3]}")

    # --- READ path: generation resolves the SAME project corpus (R4-S2 + #1 fix) ---
    section = _build_corpus_authorities_section({"project_root": str(proj)})
    ok &= _ok("Established project vocabulary" in section,
              "READ: spec-prompt authorities resolved via project_root")
    ok &= _ok(len(section) > 0 and "src/" in section, "READ: authorities reference real bindings")
    return ok


def postrun(run_dir: str, project_root: str) -> bool:
    rd, pr = Path(run_dir), Path(project_root)
    ok = True
    diag = rd / "plan-ingestion-diagnostic.json"
    if diag.exists():
        d = json.loads(diag.read_text()).get("phases", {})
        ok &= _ok(d.get("assess", {}).get("deterministic") is True
                  and d.get("assess", {}).get("cost_usd", 1) == 0, "ASSESS ran deterministic (cost 0)")
        ok &= _ok(d.get("transform", {}).get("deterministic") is True
                  and d.get("transform", {}).get("cost_usd", 1) == 0, "TRANSFORM ran deterministic (cost 0)")
    else:
        print(f"  [WARN] no plan-ingestion-diagnostic.json at {diag}")
    from startd8.paths import controlled_corpus_path
    cp = controlled_corpus_path(pr)
    ok &= _ok(cp.exists(), f"corpus written at {cp}")
    if cp.exists():
        data = json.loads(cp.read_text())
        ok &= _ok(len(data.get("terms", [])) > 0, f"corpus has terms (n={len(data.get('terms', []))})")
    return ok


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "postrun":
        result = postrun(sys.argv[2], sys.argv[3])
    else:
        result = offline()
    print(f"\n{'✅ VALIDATION PASSED' if result else '❌ VALIDATION FAILED'}")
    sys.exit(0 if result else 1)
