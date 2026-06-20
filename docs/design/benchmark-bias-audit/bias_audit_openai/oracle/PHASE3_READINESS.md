# Phase 3 (Oracle & Mutant Gate) — Readiness & Independence Boundary

**Status:** BLOCKED (correct fail-closed state). Gate `validation-gate.json` = `blocked`, 6 errors.
**Author of this note:** Claude (Opus 4.8) — assisting agent. **Deliberately did NOT author the oracle.**

## Why this phase stops here (read first)

This is a **cross-tool bias audit** whose measured vendors include **`claude-code`** (see the authoring
runs: claude-code, codex-cli, gemini-cli each author suites/specs). The oracle and mutant battery are
the instrument that *scores* those vendor outputs. Therefore:

- **An oracle authored by Claude would contaminate the audit.** It would let one measured vendor define
  the yardstick used to judge all three — exactly the bias the audit exists to detect. The evidence
  schema encodes this: `oracle-provenance.json` requires an **`independent_non_claude_review`** field.
- The assisting agent (Claude) has therefore **not** implemented the reference oracle, mutants, kill
  matrix, or calibration suite. Doing so would not merely be unsignable — it would **anchor the
  required independent reimplementation** on a Claude artifact and defeat the independence guarantee.

The two preceding security/integrity phases were safe for an assisting agent to do and are complete
(reconcile/promote, controller hardening, intake alignment — all committed, all tested). Phase 3 is the
point where independent, **non-Claude** human/agent work is structurally required.

## What remains (for an independent, non-Claude implementer + two reviewers)

The fault definitions already exist in `mutants/manifest.json` (10 single-fault mutants across the
canonical spec's OPEN items: rounding default, cascade-vs-sum, reduction ordering, candidate selection,
decimal precision, output-only rounding, fixed overrun, price-on-request). They are **definitions, not
executable mutants** (per the manifest's own `admission_note`). To accept the gate:

1. **Reference oracle (independent).** A correct ComputeBasket implementation of the **canonical**
   contract (`canonical/spec.md`, `canonical/pricing.proto`, `canonical/canonicalization_decisions.md`)
   — authored/reviewed by a non-Claude party. Record authorship, commits, source inputs, any
   tool-generated contribution, and the independent review/reimplementation in
   `oracle/oracle-provenance.json` → set `status: accepted` only when that review exists.
2. **FIXED/OPEN evidence mapping** (`oracle/fixed-open-evidence.json`): map every FIXED and OPEN item to
   Liferay/schema evidence + a targeted probe + expected behavior (deterministic decimal, rounding,
   ordering, cap, error). `status: accepted` when complete.
3. **Executable mutants** (`mutants/`): implement each manifest fault as a single-fault variant of the
   reference oracle. ≥2 mutants for each high-risk dimension (rounding, ordering, cap, decimal, error).
   A harness failure is **not** a kill.
4. **Run oracle + calibration suites against every mutant** → complete `mutants/expected-kill-matrix.csv`
   (header is in place); rewrite/exclude equivalent or invalid mutants; fill `mutants/adequacy-report.json`
   (`status: accepted`) and flip `mutants/manifest.json` `status` `planned → accepted`.
5. **Two complete reviewer sign-offs** (`oracle/reviewer-signoffs.json`), one blinded to author vendor
   where practical. Each needs `reviewer_id, role, blinded, evidence_reviewed, decision, rationale, date`.
6. **Derive the gate:** `python3 scripts/validate_cross_tool_oracle_gate.py --sync-status`. It flips to
   `accepted` only when 1–5 are all present; do not hand-edit the status.

## Note on a reusable oracle that already exists (independence caveat)

The `startd8-sdk` repo contains a *different* pricing oracle (`benchmark_matrix/behavioral/pricing_suite.py`
+ a `_ReferencePricing` reference server) for the SDK's own Online-Boutique-derived pricing service. It is
**not** the canonical Liferay contract this audit uses, and — more importantly — it was authored within the
same Claude-assisted line of work, so it does **not** satisfy the `independent_non_claude_review`
requirement. It may be useful as *prior art a non-Claude reviewer consults*, but it cannot be the accepted
oracle here without independent reimplementation/review.

## Current gate state (verified)

```
$ python3 scripts/validate_cross_tool_oracle_gate.py
status: blocked   (6 errors: provenance/evidence/adequacy not accepted; <2 sign-offs; mutants not executable)
```

This is the intended state until the independent work above lands. The authoring controller's `--run`
path is also gated on this same accepted gate (`run_cross_tool_bias_authoring.py:oracle_gate_passes`),
so no further authoring can spend until Phase 3 is genuinely accepted.
