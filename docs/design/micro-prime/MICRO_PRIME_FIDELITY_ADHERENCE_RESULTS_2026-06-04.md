# Micro-Prime Fidelity — FR-MPF-5 Adherence Measurement (cheap LOCAL tier)

**Date:** 2026-06-04
**Status:** Run 1 complete (N=10, lead-path shape) — **INCONCLUSIVE; thesis does NOT cleanly transfer to
the fine-tuned local model.** Run 2 (N=30, micro-prime shape) was attempted but **crashed on a transient
broken `main`** (a duplicate-feature merge left conflict markers; since resolved) → no data.
**Superseded for the strategic decision by RUN-036** (`RUN_036_CONVENTION_INJECTION_VALIDATION_POSTMORTEM.md`),
a real end-to-end cap-dev-pipe validation that **converges with this finding** (injection works where it
reaches; bypass moved to test-gen/spec paths; do NOT tighten FR-MPF-3/4). The micro-prime-shape harness is
built + tested and remains available for an isolated prompt-shape re-run if needed (now lower priority).
**Harness:** `scripts/ckg_adherence_harness.py` + `contractors/project_knowledge/adherence.py` (REQ-CKG-530).
**Closes (partially):** the long-pending OQ-5 "prevent-axis / cheap-tier end-to-end" item — the cross-tier
work that validated the 0.05→1.00 lift used **cloud** Haiku/Flash/Pro; the actual micro-prime **local** model
had never been measured. This is that measurement.

---

## 1. Method

- **Model:** `ollama:startd8-coder` (the real micro-prime local tier — a *fine-tuned* coder model).
- **Cases:** `RUN011_CASES` (strengthened, forced-`db.<model>({data})` Gap-A + module-path Gap-B).
- **Scoring:** structural (`measure_adherence_structural`: `scan_prisma_usage` + Prisma↔Zod symmetry for
  Gap A; `@/`-import allowlist for Gap B) — the false-pass-killer, not a denylist.
- **N:** 10 seeds/case. **Temperature:** 0.7 (wired this session so seeds are genuine stochastic samples;
  the scaffold previously ignored the seed → greedy → identical output → faked the rate).
- **Prompt shape:** **lead-path** (`build_spec_prompt`: base + the provider's `## Prisma data model`
  section). ⚠️ NOT the micro-prime terse/skeleton shape — see Caveats.
- **Threshold:** 0.90 per-Gap.

## 2. Results

| Case | Gap | Baseline | Injected | Δ |
|------|-----|----------|----------|---|
| PI-004 | A (field-invention) | 0.10 | **1.00** | **+0.90** |
| PI-002 | B (module path) | 0.80 | 1.00 | +0.20 |
| PI-001 | A | 0.90 | 0.70 | −0.20 |
| PI-007 | B | 1.00 | 0.70 | −0.30 |
| **Gap A** (PI-001+PI-004) | | **0.50** | **0.85** | +0.35 — still **BELOW** 0.90 |
| **Gap B** (PI-002+PI-007) | | **0.90** | **0.85** | **−0.05** — injection slightly *hurt* |

## 3. Honest analysis (no spin)

- **The clean cloud lift does NOT transfer.** On cloud Haiku/Flash/Pro the lift was 0.05–0.40 → ~1.0,
  decisive. Here it is **mixed**: neither Gap clears the 0.90 gate injected, and **Gap B nets negative**.
- **Injection decisively fixes the case that needs it most.** PI-004 (raw field-invention) went
  **0.10 → 1.00** — the core Gap-A failure mode injection exists to kill. That part works.
- **Two cases regressed** (PI-001 −0.20, PI-007 −0.30). At N=10 these are within sampling range
  (±~0.15), so they are **not confirmed** — but they are **not dismissed either**: they are a real signal
  that injecting verbose authority into a model that **already has high baseline adherence** may *distract*
  it. (This is a fine-tuned model: baseline Gap B was already **0.90 unaided** — little headroom, and the
  one bad case is PI-004, which injection fixes.)
- **D1 "injection ≠ adherence" is vindicated.** Putting the truth in the prompt is necessary, not
  sufficient, and on this tier it is occasionally counter-productive. This is exactly why FR-MPF-5 gates on
  *measured* adherence, not on the wiring being present.

## 4. Caveats (why this is a first signal, not a verdict)

1. **Prompt shape mismatch.** This used the lead-path shape (a verbose `## Prisma data model` section).
   The real micro-prime path renders the authority tersely under `# Domain constraints (MUST follow these):`
   and caps it (FR-MPF-1). A verbose section is the prime suspect for the PI-001/PI-007 regressions on a
   small model → **re-run with the micro-prime shape.**
2. **N=10 is too low** to resolve −0.20/−0.30 deltas → **bump to N=30.**
3. **Temperature 0.7** adds variance; the regressions could be sampling. (A greedy N=1 sanity earlier showed
   Gap A 0.50→1.00, Gap B 1.00→1.00 — different from this N=10, underscoring the variance.)

## 5. Implications (acted on)

- **FR-MPF-3/4 thresholds stay where they are: DISABLED.** The data does not justify tightening routing.
  FR-MPF-4 (route-away) rationale **weakens** — the local model is already decent and its one real failure
  (PI-004) is the case injection fixes, so wholesale route-away is unwarranted.
- **The deferred prompt-shape-fidelity follow-up is now WARRANTED** (it was "only if inconclusive" — it is).
- The run also re-confirmed the pre-existing **provider-registry bug** (both `nim` and `openai-compatible`
  entry points reference non-existent classes; non-fatal but logs loudly).

## 6. Follow-up measurement (deferred — RUN-036 answered the strategic question)

The micro-prime-shape harness (`--prompt-shape microprime --seeds 30`) exists and is tested; it would
isolate whether the PI-001/PI-007 regressions are a lead-path-verbosity artifact. **But RUN-036 (real
pipeline) already settled the decision** that this synthetic run fed into — FR-MPF-5 gate stays closed,
FR-MPF-3/4 stay disabled — so the isolated prompt-shape re-run is **lower priority** than the substantive
prevention work RUN-036 surfaced (reach the test-gen + spec paths). Re-run it only if the prompt-shape
question becomes decision-relevant again.
