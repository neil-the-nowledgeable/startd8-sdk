# How To Perform the Second Non-Claude Review

## Purpose

This review is an admission control for a cross-tool bias audit. Your job is
to decide whether the oracle and mutant battery are defensible scoring
instruments. It is not a review of model-generated suites or a bias verdict.

Do not change a pending artifact to accepted merely because it has a plausible
shape. Every acceptance must be backed by executable or source-traceable
evidence.

## Independence and blinding

1. Do not use a Claude-authored oracle, test suite, or calibration result as
   the reference implementation.
2. Review independently of Reviewer 1. Reviewer 1 is Codex/OpenAI-affiliated
   and unblinded, so you should be blinded to author vendor where practical.
3. Ask the audit operator for a blinded packet when reviewing any generated
   output: replace tool IDs, author-vendor fields, and run-directory names with
   neutral labels. Preserve content hashes and an operator-held label mapping.
4. Disclose your identity, role, tool assistance, conflicts, and whether you
   were blinded in your sign-off. A conflict does not become acceptable by
   omission.

## Review sequence

1. Read the canonical contract:
   - canonical/spec.md
   - canonical/pricing.proto
   - canonical/canonicalization_decisions.md
2. Inspect oracle/oracle-provenance.json. Confirm it identifies the reference
   oracle, its authorship, source inputs, commits, tool-generated portions, and
   independent non-Claude review or reimplementation.
3. Inspect oracle/fixed-open-evidence.json. Every FIXED and OPEN behavior must
   cite its Liferay or schema source, name a targeted probe, and state expected
   behavior.
4. Inspect each executable mutant. It must change one material behavior only;
   it must not be a harness failure or a broader rewrite.
5. Run the oracle and calibration suites against every mutant. Confirm the
   expected-kill matrix records the actual result. Equivalent or invalid mutants
   must be excluded with a reason, not counted as kills.
6. Verify high-risk coverage: rounding, ordering, cap or fixed-overrun,
   decimal precision, and error behavior each require at least two
   discriminating mutants.
7. Confirm raw evidence is immutable and all referenced paths, commits, and
   checksums resolve from the review checkout.

## Acceptance criteria

Approve only when all conditions hold:

- The oracle is independently authored or reimplemented and provenance is
  complete.
- Every FIXED and OPEN item has source traceability and an executable probe.
- The mutant manifest and adequacy report are accepted from real calibration
  evidence.
- The kill matrix contains a row for each valid mutant and no harness failure
  is treated as a kill.
- You can explain why the oracle does not import author-vendor assumptions.

Otherwise record decision blocked or reject, list the exact missing evidence,
and leave the overall sign-off status pending.

## Recording the sign-off

Add one object to oracle/reviewer-signoffs.json. Use a decision of accept only
when the acceptance criteria are met.

~~~json
{
  "reviewer_id": "stable-reviewer-identifier",
  "role": "independent non-Claude reviewer",
  "blinded": true,
  "evidence_reviewed": [
    "commit-or-content-hash",
    "oracle artifact paths",
    "mutant calibration artifact paths"
  ],
  "decision": "accept",
  "rationale": "Concise evidence-backed decision.",
  "date": "YYYY-MM-DD"
}
~~~

After both reviewers record accepting decisions and the evidence artifacts are
accepted, run:

~~~bash
python3 scripts/validate_cross_tool_oracle_gate.py
python3 scripts/validate_cross_tool_oracle_gate.py --sync-status
~~~

The validator must report accepted with no errors. Do not hand-edit the
derived gate status.
