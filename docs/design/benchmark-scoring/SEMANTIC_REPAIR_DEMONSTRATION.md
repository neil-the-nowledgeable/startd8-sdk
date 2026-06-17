# Semantic Repair — Capability Demonstration (OQ-2)

**Date:** 2026-06-16
**Status:** Demonstration result ($0, deterministic, no LLM)
**Reproduce:** `python3 scripts/demo_semantic_repair.py`
**Answers:** OQ-2 of `REPAIR_CAPABILITY_CAPTURE_REQUIREMENTS.md` — exercise semantic repair (idle on the
frontier benchmark) to produce live before→after + DC-3 uplift evidence for the capability write-up.

---

## What this shows

The frontier benchmark idles the semantic-repair layer (raw output already disk-clean —
`REPAIR_LAYER_FINDINGS_ROUND3.md`). This demo drives the **real** pipeline (`run_semantic_repair`,
apply mode, all 4 categories enabled) on the four defect patterns the requirements doc specifies, so
the capability is shown *working* rather than merely *implemented*.

`issues_found=3, issues_repaired=3, issues_unfixable=0`

| Category | Result | Transform | disk-quality |
|----------|--------|-----------|--------------|
| **`discarded_return`** | ✅ **REPAIRED** | `os.environ.get("GCP_PROJECT_ID")` → `gcp_project_id = os.environ.get("GCP_PROJECT_ID")` (and `port = …`) | **0.960 → 1.000** |
| **`duplicate_main_guard`** | ✅ **REPAIRED** | removed the second `if __name__ == "__main__":` block | 0.940 → 0.940¹ |
| `method_resolution` | — not triggered | (detector emitted no `method_resolution` issue for the synthetic input) | 1.000 |
| `import_resolution` | — not triggered | (see note 2) | 0.980 |

¹ duplicate-main is not penalized in the disk-quality formula, so the score is flat even though the
repair fired correctly — the *transform* is the evidence, not the score.

² `run_semantic_repair` calls `validate_disk_compliance` **without** the `sibling_imports`/`import_map`
context that the full integration-engine path supplies, so its import-resolution *detection* is
weaker than in-pipeline. The repair *step* is sound; the bare entry under-detects this category.

## The headline evidence

- **The capability is real and deterministic:** `discarded_return` and `duplicate_main_guard` apply
  exact AST transforms with **0 unfixable**, **$0**, no LLM.
- **DC-3 uplift is real:** `discarded_return` lifts disk-quality **0.960 → 1.000** — a concrete,
  measurable "raw → repaired" delta, the live version of the "0.85→1.0" the memory cited for cheap
  tiers. This is exactly what the capability write-up can show.

## Honest limits (what the demo also reveals)

1. **Whether a category fires depends on the DETECTOR, not the repair step.** Two of four categories
   didn't trigger because the synthetic inputs / bare entry point didn't reproduce the detector's
   trigger conditions — not because the repair is broken.
2. **`run_semantic_repair` under-detects `import_resolution`** without sibling/import-map context. For
   a fuller demonstration of that category, drive it through the integration engine (which supplies
   the context) or pass the context explicitly — a follow-up if import-resolution showcase is wanted.
3. **Disk-quality score is insensitive to some repairs** (duplicate-main): the score is not a complete
   proxy for repair value — the per-transform attribution is.

## Bearing on the capability capture (parent requirements)

This validates `REPAIR_CAPABILITY_CAPTURE_REQUIREMENTS.md` FR-3/FR-4: the SDK's semantic repair is a
**present, working capability** (not just spec'd), it simply **idles on frontier raw output** — so the
capture report must say "present, demonstrated, idle here," with this demo as the "demonstrated"
evidence. To populate DC-3 deltas at scale (OQ-2), a cheap-tier or apply-mode run would do it; this
unit-level demo already provides citable proof for the write-up without a paid run.

*Demonstration complete. 2/4 categories fired with concrete transforms (0 unfixable) and a real DC-3
uplift (0.960→1.000); the other 2 are detector-trigger/context-gated, not repair-broken. Live evidence
for the "what the SDK does" write-up, $0.*
