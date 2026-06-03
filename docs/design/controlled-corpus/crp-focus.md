## Where we need reviewer input most

1. **OQ-5 — Corpus scope (project vs shared-domain).** Persist per-project (`.startd8/`) or promote a
   stable subset to a shared cross-project domain corpus (`~/.startd8/corpus/`)? Determinism is
   workload-specific but the term vocabulary is reusable. Where is the promotion boundary?

2. **OQ-6 — Surface-form canonicalization.** What function maps drifting NL labels ("Shared JSON
   Logger — emailservice" vs "Email Service JSON Logger") to one `canonical_key`? Plan defaults to
   target_file-anchored; stress that choice (collisions, multi-binding files, language variants).

3. **OQ-7 — Term↔target_file altitude.** Proto terms are per-service/RPC/entity; the determinism
   oracle is per-target_file. Is the mapping well-defined when one file realizes many terms, or one
   term spans many files? Mirrors the SCR's feature-vs-element altitude (OQ-9).

4. **Two-axis determinism / false_pass_risk (FR-8).** Is combining success_stability AND
   requirement_score the right model? Are the thresholds (≥0.95 / ≥0.9 / <0.7) defensible, and does
   "never promote a false_pass_risk binding" belong in the corpus or solely in the SCR?

5. **Idempotent + order-independent merge (success criterion).** Is the dedup-by-(kind,canonical_key)
   + union + precedence-upgrade merge genuinely order-independent given maturity depends on recurrence?
   Look for a path where merge order changes the final corpus.

6. **Interface fidelity to real seams.** Does mirroring ExemplarRegistry's maturity ladder, reusing
   forward_manifest SOURCE_PRECEDENCE for binding conflicts, and trend_math.linear_slope for stability
   actually fit, or are there impedance mismatches (e.g. ExemplarRegistry dedups by id, corpus dedups
   by semantic key)?
