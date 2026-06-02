# CKG (Code Knowledge Graph) — Next-Session Hand-off

**Date:** 2026-06-01
**From:** the CKG Phase-1 implementation session
**To:** the next session that picks up CKG (branch from *current* main)
**Status:** Phase 1 (detection/verification) **landed on main**; two tracks remain.

> One-screen orientation so a fresh session can start without re-reading the whole doc set.
> Deep context: `project_code_observability.md` (memory), `CODE_KNOWLEDGE_GRAPH_DESIGN.md`.

---

## What's DONE (landed on main, commit `cd63aa25`)

CKG Phase 1 — the **detection / verification** half — is merged into main and tested:

| Increment | Delivers |
|---|---|
| 690a | regression lock + Zod-composition audit (`test_run009_regression_lock.py`) |
| Inc-0 | `code_observability/` — `scip_runner` (subprocess, safety, advisory-degrade) + `scip_reader` (typed accessors) + vendored `scip_pb2` |
| Inc-1 | `validators/external_type_presence.py` — signature (f), catches RUN_009 #4/#11 |
| Inc-2 | `validators/tsconfig_paths.py` (real `paths`+`extends`) + `utils/jsonc.py` (string-aware JSONC) |
| Inc-4 | `validators/cross_file_verifier.py` — unified registry + Finding contract (REQ-CKG-235); `_evaluate_cross_file_integrity` delegates to it (behaviour-preserving, 690a-proven) |
| Inc-5 (partial) | aggregate any-error rule (REQ-CKG-245) — `_cap_verdict_on_cross_file_errors` kills mean-dilution |

Phase-2 (Knowledge Provider) **requirements skeleton** drafted:
`CODE_KNOWLEDGE_GRAPH_PHASE2_KNOWLEDGE_PROVIDER_REQUIREMENTS.md` (v0.1, pre-reflection/pre-CRP).

---

## Prerequisites before cutting a new branch

1. **Clear main's working tree.** It still has *unrelated* in-progress edits (`CLAUDE.md`,
   `src/startd8/contractors/prime_contractor.py`, `exemplar-registry.json`) — **not CKG's**.
   Track 1 edits `prime_contractor.py`, so commit/stash that work first to avoid collision.
2. **Push main if desired** — local main is ~12 commits ahead of `origin/main` (unpushed).
3. **Branch from *current* main** (the old `feat/ckg-phase1` worktree/branch was retired after merge).
4. **Fresh venv:** `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`. For the SCIP
   reader add `protobuf` (`pip install -e ".[code-observability]"`); to regenerate the vendored
   `scip_pb2.py` you need `grpcio-tools` (dev-time only). The Node `scip-typescript` tool is a
   separate prereq, env-gated by `STARTD8_CKG_SCIP` (default off → external check advisory).

---

## TRACK 1 — REQ-CKG-240 synchronous verdict consumption (finishes Phase 1; do FIRST)

**Problem (code-verified):** the cross-file verdict is computed in a detached
`daemon=False` thread (`prime_postmortem.launch_prime_postmortem_async:~2728`) **after**
`prime_contractor.run()` already returned `result_dict` (`prime_contractor.py:~5241`) — so the
FAIL never gates the run. The aggregate rule (Inc-5) makes the *report* verdict correct, but it
isn't consumed.

**Do:** run the cross-file gate synchronously (or join the postmortem thread deterministically
in CI/acceptance), fold the verdict into `result_dict` + CLI exit code.
**Acceptance:** a batch containing #4/#11 yields a **non-PASS run result / exit code** (not just
an async log line); **NFR-5 determinism** (20 repeats, identical verdict, no race).
**Caution:** edits `prime_contractor.py` — the file dirty on main now (see Prereq 1). Smaller/
contained (one orchestrator seam) but central; add an integration test.

## TRACK 2 — Phase-2 Knowledge Provider (Approach A converged; do SECOND)

**Spec:** `CODE_KNOWLEDGE_GRAPH_PHASE2_KNOWLEDGE_PROVIDER_REQUIREMENTS.md` (v0.1 skeleton).
**Process:** run `/reflective-requirements` then `/new-cnvrg-rvw-prmpt` on it first (as Phase 1 did).
**Build:** the pre-generation provider as CKG's L5 — a **view over the Phase-1 resolver**, NOT a
bespoke scanner (CROSS_FILE §11). Reuse `prisma_parser` / `tsconfig_paths` / `cross_file_imports` /
`ScipReader` / the verifier Finding model.
**Fold in the validated deltas:** D1 injection≠adherence (measure over N≥5 seeds, ~0.9 threshold —
don't declare "done" on an injection test); D2 explicit negatives (seeded list); D3 `omissions`
field (never render "use only these fields: (none)"); D4 characterization-snapshot
`_collect_upstream_interfaces` (`prime_contractor.py:4223`) before refactor + drop the
`_feature_mirrors_data_model` heuristic (`:4320`, likely the RUN-011 Gap-A fix).
**Detail behind D1–D4:** `APPROACH_A_TO_CKG_HANDOFF.md` + the superseded
`APPROACH_A_PROJECT_KNOWLEDGE_{REQUIREMENTS,PLAN}.md` Appendix A/B/C (CRP-R1 dispositions).

---

## Non-negotiable disciplines (carried from Phase 1)

- **Regression-lock before refactor.** Capture a characterization snapshot (golden output) of any
  shared surface *before* editing it, assert byte-parity after (how 690a guarded Inc-4; how D4
  guards the Track-2 seam).
- **Advisory-degrade, never silent PASS.** SCIP/tool/config unavailable → explicit
  `skipped_unavailable`, never read as PASS (REQ-CKG-230/235 availability states).
- **Don't build twice.** One resolver shared by detection (Verifier) and prevention (Knowledge
  Provider) — CROSS_FILE §11.
- **Tests gate everything; lint clean; tag known gaps as `xfail(strict=True)`** so a later fix auto-alerts.

## Verify the landed state in a fresh checkout
```
.venv/bin/python -m pytest tests/unit/code_observability/ tests/unit/utils/test_jsonc.py \
  tests/unit/validators/test_run009_regression_lock.py tests/unit/validators/test_cross_file_verifier.py \
  tests/unit/validators/test_external_type_presence.py tests/unit/validators/test_tsconfig_paths.py \
  tests/unit/contractors/test_inc5_verdict_gating.py tests/unit/contractors/test_cross_file_integrity_postmortem.py -q
# expect ~all green + a few xfail (Zod-composition + strategy-(a) boundary, intentional)
```

## Pointers
- **Design:** `CODE_KNOWLEDGE_GRAPH_DESIGN.md` (§8.1 Knowledge Provider, §-phased) · `MIERUKA_DESIGN_PRINCIPLE.md`
- **Phase 1:** `CODE_KNOWLEDGE_GRAPH_PHASE1_{REQUIREMENTS,PLAN}.md` · spike `scripts/spikes/ckg/SG_FINDINGS.md`
- **Phase 2:** `CODE_KNOWLEDGE_GRAPH_PHASE2_KNOWLEDGE_PROVIDER_REQUIREMENTS.md`
- **Forcing context:** `CROSS_FILE_CONTRACT_RESOLUTION.md` (§4 locality, §11 convergence) · `APPROACH_A_TO_CKG_HANDOFF.md`
- **Memory:** `project_code_observability.md` (live status + hard-won facts)
