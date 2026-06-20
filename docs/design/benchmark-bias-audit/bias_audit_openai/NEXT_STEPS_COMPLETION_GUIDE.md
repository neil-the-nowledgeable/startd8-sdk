# Cross-Tool Bias Audit — Completion Guide & Next Steps

**Updated:** 2026-06-20 (branch `codex/resolved-pricing-adapter`)

**Bottom line:** the security/integrity phases an assisting agent can safely do are **complete and
tested** (Phases 1, 2, 4). The audit is **still not ready for bias analysis** — the oracle/mutant gate
is correctly `blocked` and requires **independent, non-Claude** work plus two reviewer sign-offs
(Phase 3), after which Phase 5 (S4–S7) can run. Do not make any cross-tool bias claim until the gate
is genuinely `accepted`.

## Status at a glance

| Phase | State | Evidence |
|------|-------|----------|
| 1. Harden authoring controller | ✅ **done** | commit `7863e9c7` · 15 tests |
| 2. Resolve quarantined batch | ✅ **done** | commit `52f8d440` · reconcile `accepted` 30/30, promoted |
| 4. Review intake + normalize | ✅ **done** | commit `b68c720b` · 13 tests, 29/30 accepted |
| 3. Oracle & mutant gate | ⛔ **blocked** (correct) | `oracle/PHASE3_READINESS.md` · gate 6 errors |
| 5. Freeze analysis, run S4–S7 | ⛔ **blocked** on Phase 3 | — |

All four buildable commits are on `codex/resolved-pricing-adapter` (local; not pushed). 32 focused
tests pass. Raw evidence verified byte-stable throughout; the promoted store is gitignored
(`.startd8/bias-audit-store/`).

---

## ✅ Phase 1 — Authoring controller (done)
`scripts/run_cross_tool_bias_authoring.py` + `tests/unit/test_run_cross_tool_bias_authoring.py`.
- Per-tool **scrubbed** credentials (was: full Doppler env + every vendor key into every child).
  `fetch_doppler_credentials(needed)` + `build_tool_env` inject only the one vendor credential; fails
  closed if absent. No cross-vendor key or ambient secret reaches a subprocess.
- Declarative versioned `TOOL_POLICY` (`tool-policy/1`); each privilege flag carries a documented
  rationale (guide allows "unless a documented capability requires one"). Metadata = names/flags, never
  secret values.
- Immutable per-attempt capture (`record_attempt`, `exist_ok=False`): retries never overwrite attempt one.

## ✅ Phase 2 — Quarantined batch (done)
`scripts/reconcile_cross_tool_bias_runs.py`.
- The 3 quarantined `dotenv_line` findings were **false positives**: the lowercase identifier
  `line_key = ln.get("line_key")` (a pricing line-item key), matched only because the shared
  prose-redaction rule is case-insensitive. No secret values.
- Reviewed allow-list rule `reconcile-scan/2`: re-verifies each hit case-sensitively against ALL-CAPS
  env names; lowercase-only hits drop **with the redacted line recorded** in the report; a real
  `OPENAI_API_KEY=…` still quarantines. Shared `redaction.py` untouched.
- Result: reconciliation `accepted` (30/30), raw content verified unchanged (225/225 checksums),
  clean immutable store promoted (`audit.sqlite` + report; execution junk excluded).

## ✅ Phase 4 — Intake & normalize (done)
`scripts/intake_and_normalize_artifacts.py` + `tests/unit/test_intake_and_normalize_artifacts.py`.
- Sources from the **promoted store gated on an accepted report** (was: read the unaccepted temp batch).
- Store-authoritative output (`intake.sqlite`, `intake-ledger.json`, `normalized/` inside the store —
  no more second SQLite layout beside raw).
- Mechanical-only normalization (whitespace, idempotent), self-guarded by `is_mechanical_only`; any
  non-whitespace change is **refused** (`non_mechanical_normalization_refused`), not repaired. Records
  raw+normalized checksums and the exact diff. Structured reason codes.
- Run result: 29/30 accepted; run-27 rejected `forbidden_import: google.protobuf.json_format`.

---

## ⛔ Phase 3 — Oracle & mutant gate (NEXT, independent + non-Claude)

**Read `oracle/PHASE3_READINESS.md` first.** The assisting agent deliberately did **not** author the
oracle: this is a bias audit in which `claude-code` is a measured vendor, so a Claude-authored oracle
would contaminate the bias under test (the schema requires `independent_non_claude_review`).

Order of work (the validator derives the gate only when all are present):
1. **Independent reference oracle** for the canonical contract (`canonical/spec.md`, `pricing.proto`,
   `canonicalization_decisions.md`) — non-Claude authorship/review recorded in
   `oracle/oracle-provenance.json` → `status: accepted`.
2. **FIXED/OPEN evidence mapping** (`oracle/fixed-open-evidence.json`): each item → Liferay/schema
   evidence + targeted probe + expected behavior → `accepted`.
3. **Executable mutants**: implement the 10 fault definitions already in `mutants/manifest.json` as
   single-fault variants (≥2 for each high-risk dimension: rounding, ordering, cap, decimal, error).
   A harness failure is not a kill.
4. **Run oracle + calibration suites** against each mutant → complete `mutants/expected-kill-matrix.csv`;
   exclude equivalent/invalid mutants; fill `mutants/adequacy-report.json` and flip
   `mutants/manifest.json` `planned → accepted`.
5. **Two reviewer sign-offs** (`oracle/reviewer-signoffs.json`), one blinded to author vendor; each with
   `reviewer_id, role, blinded, evidence_reviewed, decision, rationale, date`.
6. **Derive the gate:** `python3 scripts/validate_cross_tool_oracle_gate.py --sync-status` (do not
   hand-edit `status`). The authoring controller's `--run` path is also gated on this accepted gate.

## ⛔ Phase 5 — Freeze analysis, run S4–S7 (blocked on Phase 3)
Commit `analysis/ANALYSIS_PLAN.md` + pre-registration **before** inspecting semantic results. Run S4
(accepted suites × accepted oracle/mutants → equivalence + kill matrices), S5 (canonical proto/harness
fixed), S6 (coding/adjudication blinded to vendor where practical — a 2-vs-1 split is a flag, not a
verdict). Publish S7 only after secret/license review and all gates pass; else label provisional/blocked.

---

## Operator checklist
- [x] Controller security review completed and committed separately (`7863e9c7`)
- [x] `dotenv_line` findings dispositioned (4, reviewed rule `reconcile-scan/2`)
- [x] Reconciliation report accepted and batch promoted (clean immutable store)
- [x] Intake aligned to promoted store and run mechanically (`b68c720b`)
- [ ] Oracle provenance and FIXED/OPEN evidence complete — **independent, non-Claude**
- [ ] Executable mutants and calibration evidence complete — **independent**
- [ ] Two reviewer sign-offs recorded; derived gate accepted — **human, one blinded**
- [ ] Analysis plan frozen before S4/S5/S6 results are consumed

## Follow-ups surfaced this session (not yet fixed)
1. **Suites executed in-place in the raw evidence tree** (`__pycache__`/`.pytest_cache` found under
   `raw/`). Generated code must run in an **isolated sandbox**, not the evidence dir. The reconcile +
   controller now exclude this junk from the store/attempt copies, but the root cause (whatever runs the
   suites in-place) should be moved to an isolated workspace.
2. A **hung authoring controller (PID 9852)** held the batch dir open for ~1h (idle, no children);
   terminated this session. The batch was complete and the promoted snapshot is consistent, but it
   highlights that "batch frozen" was not enforced — consider a lock/`--done` marker before promotion.

## Immediate stop condition
The audit is **not ready for bias analysis**. A blocked oracle/mutant gate leaves no defensible
cross-tool bias conclusion. The single-cell flagship result validates runtime execution only.
