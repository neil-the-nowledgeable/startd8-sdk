# CRP Focus — RUN-007 Remediation (where we need input most)

This package fixes a code-generation pipeline that shipped 9/16 empty-class stubs
(`export class <stem> {}`) at $0.00 while reporting 16/16 PASS. Weight your review
toward these high-risk areas. Use F-prefixed suggestions for the requirements
(`RUN_007_REMEDIATION_REQUIREMENTS.md`, FR-1..FR-8) and S-prefixed for the plan
(`RUN_007_REMEDIATION_PLAN.md`, steps 0–7).

1. **Escalate-once-then-refuse control flow (FR-2/3/4, plan steps 1/4).**
   Is the termination airtight — exactly one escalation, no loop, idempotent on retry/resume?
   What happens if the file-whole escalation *partially* fills (some real content + a residual
   stub)? Is "still empty/stub" well-defined enough to decide escalate-vs-refuse deterministically?

2. **Cost-budget interaction (FR-4, OQ-3, plan step 0/4).**
   Does the budget signal actually reach the micro-prime escalation site, or only the orchestration
   layer? If it doesn't reach, FR-4 ("refuse not stub when exhausted") is unimplementable as written.
   What is the correct behavior at the exact budget boundary (escalation would cross the cap)?

3. **Three-site language-split emitter (FR-1, plan steps 2/3).**
   The fix targets Java/C# assemblers + the Node upstream synthesizer + the skeleton-emission
   decision. **Did we miss emitters for Go, Vue, or Python?** Go has `go_file_assembler.py:196`
   (class_name from stem); Python uses `DeterministicFileAssembler`. Is the "three sites" claim
   complete, or is FR-1 under-covering some languages?

4. **Disk-validator empty-stub detector false-positive surface (FR-5/6, plan step 6).**
   The signal is "single top-level type, name == file stem, empty body, no other symbols."
   Stress it against legitimately-minimal valid files: barrel/re-export modules (`export * from`),
   empty `index.ts`, marker interfaces, ambient `.d.ts`, an empty enum, a config object module.
   Should this feed `disk_quality_score`, the FAIL verdict, or both — and at what severity?

5. **FR-7 dual-boundary SIMPLE guard (plan step 5 + step 2).**
   The guard sits at BOTH `classify_tier()` and the skeleton-emission stamp. Is there an ordering or
   consistency hazard (one boundary says SIMPLE, the other escalates)? Which is authoritative?

6. **`MissingTemplateError` + refusal surfacing (FR-2, plan steps 1/4).**
   A refused feature must surface as `success=False` in `prime-result.json` history. How does that
   interact with the (deferred) Fix 3 single-ledger and the postmortem's three disagreeing counts?
   Does a refusal need a distinct root_cause/pipeline_stage so the postmortem isn't blind to it?

7. **Backward-compat / regression on the legitimate $0.00 registry path (FR-2, plan step 2).**
   The `FRAMEWORK_CONFIG_DEFAULTS` path (next.config.mjs/tsconfig/package.json) must STILL produce a
   real skeleton at $0.00. Is there a risk the empty-spec guard accidentally catches registry-matched
   features and forces needless escalation/cost?
