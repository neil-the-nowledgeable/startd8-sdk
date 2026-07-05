# CRP Focus — cap-dev-pipe ↔ Project-Start Onboarding Merge

## Review targets (both brand-new, least-reviewed)

- `docs/design/capdevpipe-onboarding-merge/REQUIREMENTS.md` (v0.3)
- `docs/design/capdevpipe-onboarding-merge/PLAN.md` (v1.0)

Both docs are net-new and have had **zero external review**. Review them together (dual-document mode).

## Settled — do NOT relitigate (user decisions, already made)

1. **Owner = kickoff / project-start.** Not `startd8 init`, not `startd8 project init`. (Decision locked.)
2. **Forcefulness = offer via handoff, never gate/auto-install.** Non-blocking, opt-in. (Decision locked.)
3. **CLI-first:** `startd8 capdevpipe install` lands before/independent of the kickoff handoff. (Locked.)
4. **Value-gated reconciliation:** only touch SDK install logic where it adds value or reduces debt.
   Keep SDK-unique value (NR-2). Do NOT propose rewriting the whole installer onto canonical.
5. **No canonical-repo edits** (NR-4). All changes SDK-side.
6. **No graceful-degrade for pre-refactor canonical** (NR-7) — coupling already exists and is enforced.
7. **Advisory key named `capdevpipe`, not `pipeline`** (overloaded-term hardening) — settled.

## Where review energy is best spent (open/uncertain)

- **FR-A6/A10 manifest interop + migration:** is "rewrite old-schema manifest on next write" safe and
  sufficient? Any cross-tool race (SDK install then `pipeline verify` mid-migration)?
- **FR-A7 symlink delegation:** adapting canonical `InstallAction` → SDK `Action` while keeping SDK
  rollback/pending-marker transactionality — any correctness gap in the seam?
- **FR-B2 gating:** is "cascade readiness / post-`generate contract`" the right precondition, or does it
  miss brownfield paths (`kickoff derive`) that reach build-readiness differently?
- **FR-B3 non-regression:** is a parallel top-level key genuinely sufficient to guarantee byte-identical
  readiness/exit, or is there a hidden consumer of the assess dict that would react to the new key?
- **Testing adequacy:** is the guarded (`importorskip` on canonical checkout) interop test enough, given
  the whole thread exists to fix a cross-repo interop bug?
