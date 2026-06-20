# Cross-Tool Bias Audit — Completion Guide & Next Steps

**Updated:** 2026-06-20 (branch codex/cross-tool-bias-audit-phase3)

**Bottom line:** the repository-side security and integrity work is complete
and tested. The audit is still **not ready for bias analysis**: the
oracle/mutant gate is correctly blocked pending independent evidence and two
reviewer sign-offs. Do not make a cross-tool bias claim until the derived gate
is genuinely accepted.

## Status at a glance

| Phase | State | Evidence |
|---|---|---|
| 1. Harden authoring controller | done | declarative per-tool policy; scrubbed credentials; immutable attempts |
| 2. Resolve quarantined batch | done | reconciliation accepted for 30/30 runs; promoted immutable store |
| 4. Review intake + normalize | done | store-authoritative mechanical-only normalization; 29/30 accepted |
| 3. Oracle & mutant gate | blocked (correct) | all four derived checks blocked; six explicit validation errors |
| 5. Freeze analysis, run S4-S7 | blocked | requires Phase 3 acceptance |

The scoped integration and gate-validation tests pass. The gate report now
derives every per-check status and error from the same evidence that controls
admission, avoiding misleading static accepted entries.

## Do now: Phase 3, independently

Read [PHASE3_READINESS.md](oracle/PHASE3_READINESS.md) before contributing
semantic evidence. This is a bias audit whose measured vendors include
claude-code, so the scoring oracle and mutant battery require independent,
non-Claude implementation and review.

1. Implement and review the canonical reference oracle without relying on a
   Claude-authored oracle. Record authorship, source inputs, tool contribution,
   commits, and independent review in oracle/oracle-provenance.json.
2. Complete oracle/fixed-open-evidence.json: each FIXED and OPEN item needs
   Liferay/schema traceability, a targeted probe, and expected behavior.
3. Implement the planned single-fault mutants. Every high-risk rounding,
   ordering, cap, decimal, and error dimension needs at least two
   discriminating mutants; harness failures are not kills.
4. Run the oracle and calibration suite against every mutant. Fill the
   expected-kill matrix, exclude or rewrite equivalent/invalid mutants, and
   mark the mutant manifest and adequacy report accepted only with that
   evidence.
5. Obtain two complete reviewer sign-offs, one blinded to author vendor where
   practical. Each record needs reviewer ID, role, blinding, evidence reviewed,
   decision, rationale, and date.
6. Derive rather than hand-edit the gate:

   ~~~bash
   python3 scripts/validate_cross_tool_oracle_gate.py
   python3 scripts/validate_cross_tool_oracle_gate.py --sync-status
   ~~~

   The first command is read-only and returns exit code 2 while blocked. Run
   --sync-status after changing evidence so the checked-in report reflects the
   derived state.

## Do not repeat completed phases

- Do not rerun authoring merely to replace the accepted 30-run batch.
- Do not modify raw evidence to address intake decisions. The single rejected
  artifact stays rejected with its recorded reason.
- Do not broaden child-process secrets or remove the documented, isolated
  CLI execution policy.
- Do not enter S4-S7, inspect semantic results, or publish a bias conclusion
  before the oracle/mutant gate is accepted.

## After Phase 3 acceptance

1. Commit analysis/ANALYSIS_PLAN.md, analysis scripts, and the pre-registration
   manifest before consuming semantic results.
2. Run S4 with the canonical specification fixed, producing equivalence and
   kill matrices from accepted suites and the accepted oracle/mutant battery.
3. Run S5 with the canonical proto/harness fixed. Log mechanical adapters and
   report contract-shape sensitivity separately from the primary analysis.
4. Run S6 coding and adjudication blinded to author vendor where practical.
   A two-versus-one split is a flag, not a bias verdict.
5. Publish S7 only after secret/license review and all gates pass; otherwise
   label the output provisional or blocked.

## Follow-up hardening

These do not admit the audit, but should be addressed before the next raw
batch:

- Execute generated suites in an isolated sandbox rather than the raw-evidence
  tree, so __pycache__ and .pytest_cache cannot appear beside evidence.
- Add a batch lock or completion marker before promotion, preventing a
  lingering controller process from mutating a supposedly frozen batch.

## Immediate stop condition

The audit is **not ready for bias analysis**. The current blocked gate is the
intended fail-closed outcome until independent oracle evidence, mutant
adequacy, and reviewer sign-offs are complete.
