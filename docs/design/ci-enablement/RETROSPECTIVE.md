# Retrospective — safely enabling dormant CI in a dense multi-worktree repo (Hansei)

**Date:** 2026-07-23 · **Pilot:** the CI-enablement + merge-safety arc — PRs #299 (re-enable the
Tests workflow, scoped to the observability core), #301 (declared-series PromQL fixes — *another
session's*, reviewed + merged here), #302 (code-review fixes), plus the branch cleanup
(importance-scaled-slo deletions). **Method:** grounded in the actuals (git history, live test runs,
`gh api`), not the plan.

Twin of `../observability-compare/RETROSPECTIVE.md` — that one extracted how to build a fidelity
capability; this one extracts **how to enable dormant CI and verify green/merge-safety when your
local environment is not the CI environment and `main` moves under you.**

---

## Phase 3 — Retrospective insights (belief → actual)

| What was believed | What the actuals revealed | So the standard is… |
|---|---|---|
| "`tests/unit` collects cleanly → a green baseline" (664fd35d's claim + my collect-only check) | **85 failures across 28 files** (tests rotted vs evolved APIs while CI was off) **+ an irreducible flaky tail** (1–3 *different* tests per full run, all pass in isolation; xdist didn't fix it) | Collection-clean ≠ green. A "green baseline" claim requires a **full run whose real exit code you read**, and for a large suite, an explicit **flaky-tail strategy** — not a single pass. |
| "exit 0 → the run passed" (three times: the `tests.yml` check, the `-x` run, the xdist run) | Every one was `pytest … \| tail`/`… \| head` — **`$?`/exit was the pipe's tail/head, not pytest's**. Real results were failures. | **Never read a program's exit status through a pipe.** Capture it with no pipe (`cmd; echo $?`) or `PIPESTATUS[0]`. This burned me 3× *after* I'd documented it as a lesson — it is that sticky. |
| "these 2 tests fail on #301's branch → #301 regressed them" | The failure was `startd8-mixin/vendor/ is missing` — a **gitignored, `jb install`-produced dir present only in the PRIMARY worktree**. I'd compared #301-in-a-fresh-`/tmp`-worktree against main-in-the-primary. On equal footing (main, no vendor) they fail *identically* → #301 was clean. | A fresh worktree lacks primary-only gitignored artifacts (`startd8-mixin/vendor`, `.startd8/`). **Compare like-for-like**, and read *why* a test failed before attributing it. I nearly called a false regression. |
| "629 passed locally → the observability CI baseline is green" | Green **only because the primary worktree has `vendor/`**. A fresh CI checkout (no `jb install`) fails `test_datasource_uid_binding`'s 2 render tests (they hard-fail, no skip guard). CI would have been RED. | **Verify in CI conditions, not the primary worktree**: a fresh checkout, no gitignored deps, run from repo root. Pin `PYTHONPATH` to that tree. |
| "`git cherry`/`[gone]` says these importance-scaled-slo commits are unmerged → work would be lost" | **patch-id false positives**: the content reached `main` via a different integration path (evolved with a #226 note). A direct `git diff origin/main:<file> <branch>:<file>` showed `main` was a *superset* — 0 branch-only lines. | To decide "is this branch's work in main," trust **tree/patch content** (`diff`, "N branch-only added lines"), not `git cherry` patch-ids or `[gone]`/ahead-behind counts. |
| "rename `tests.yml.disabled` → `tests.yml` re-enables CI" | Necessary but **not sufficient** — repo-level Actions is `enabled: false` (a Settings change with no git trace). Confirmed via `gh api …/actions/permissions`. Nothing has run since Feb 2026. | A dormant workflow has **two independent off-switches**: the file (in git) and repo Actions permissions (in Settings). Check `gh api …/actions/permissions` before claiming CI will run. |

Six surprises → the loop worked (zero surprises would mean I read the docs, not the runs).

---

## Phase 4 — The extracted standard

### A. Verify in CI conditions, not your primary worktree
Your primary worktree carries state a fresh CI runner does not: gitignored, tool-produced dirs
(`startd8-mixin/vendor` from `jb install`, `.startd8/` stores), an editable install pointing at
*its* `src`, and env vars (`GRAFANA_API_TOKEN`). A pass there is not a pass in CI.
- Before claiming a suite is CI-green, run it in a **fresh worktree off the PR branch**, from the
  repo root, with `PYTHONPATH=<that-tree>/src`, and **no** primary-only artifacts.
- A test that **hard-fails when a toolchain/service is absent** (no skip guard) is a latent CI
  red — `test_datasource_uid_binding` (needs `vendor/`), the live-Grafana round-trip (needs a
  token+Grafana). Deselect them for the baseline (documented), and note the real fix: a
  skip-when-absent guard on the test.
- **Deselect nodeids are relative to the invocation dir.** `--deselect /abs/tmp/…::t` silently
  no-ops; run from the tree and use `tests/…::t` (I hit this in verification too).

### B. Read exit codes, never a pipe's
`pytest … | tail`/`| head` makes `$?` report tail/head (always 0). This masked a red run **three
times** in one session. Rules: run the suite with **no trailing pipe** and read `$?`; if you must
post-process, use `PIPESTATUS[0]` or `set -o pipefail`; for background runs, trust the harness's
reported exit code over any piped summary. In CI YAML, a bare `pytest` step is correct — its own
exit code fails the job (don't pipe it).

### C. A "green baseline" for a long-dormant suite is a project, not a check
When CI has been off for months, expect **rot** (tests behind evolved APIs — deterministic, one
root-cause per cluster, e.g. `SourceReconciler()` now needs `project_root`) **and a flaky tail**
(timing/perf, e2e/CLI subprocess, cross-module pollution — nondeterministic, a different set each
run, all green in isolation). `pytest-xdist --dist loadscope` did **not** tame it (perf tests
flake worse under parallel CPU load). Therefore:
- **Scope to a verified-stable core** (here: `tests/unit/observability`) so CI starts honestly
  green and protects live work; catalogue the rest as a widen-backlog (`tests/ci_known_failing.txt`).
- Widening past the core needs a **flaky-test strategy** (rerunfailures / quarantine markers),
  not just fixing the rot. Don't promise a full-suite green from a scoped pass.

### D. Merge-safety protocol for a moving multi-agent `main`
`main` advances under you (concurrent agents/worktrees). Before merging, especially someone
else's PR:
1. `gh pr view --json state,mergeable,mergeStateStatus,isDraft` — require `MERGEABLE`+`CLEAN`.
2. **Review another session's diff for soundness** and run **its own tests in CI conditions**
   (Standard A) — do not trust "author verified." #301 was sound, but its verification hadn't
   covered `test_datasource_uid_binding`.
3. When a test fails on the candidate, **read the assertion before attributing** (Standard on
   false-regressions) — compare like-for-like against `main`.
4. To decide "is a branch's work already in `main`," diff **tree content**, not `git cherry`.
5. After merge, **re-sync and confirm** (`git rev-parse main == origin/main`; grep the landed
   content); a squash makes the branch tip a non-ancestor — that's expected, verify by content.

---

## Phase 5 — Lessons + principle

**Lesson (reusable, cross-project):** *Your dev environment is not the CI environment.* Green on the
primary worktree can be red on a fresh checkout because of gitignored tool-produced dirs, env vars,
and editable-install path coupling. Verify in a fresh worktree from repo root before claiming
CI-green. **Detection:** run in `/tmp` worktree with pinned `PYTHONPATH`, no primary artifacts.
**Recovery:** deselect/skip-guard env-dependent tests; document.

**Lesson (sticky):** *Never read `$?` through a pipe.* `| tail`/`| head` returns the pipe stage's
exit. Cost this session: 3 false "exit 0" reads. **Detection:** any `cmd | …; echo $?`. **Recovery:**
drop the pipe or `PIPESTATUS[0]`.

**Principle candidate — "Parity of verification":** a check only proves what it claims if it runs in
the *conditions the claim is about*. A pass in a privileged local environment does not license a
claim about CI; an exit code read through a transform does not license a claim about the program.
Match the verification environment to the assertion, or narrow the assertion.

---

## Phase 6 — Yokoten (spread)

- The **fresh-worktree CI-parity check** applies to every "is it green?" claim in this repo —
  including the compare-live gate (whose local proof also ran in the primary worktree).
- The **skip-when-toolchain-absent guard** should replace the hard `assert result.success` in
  `test_datasource_uid_binding` and `test_artifact_generator` (mixin/vendor path) and the
  live-Grafana tests — so they skip (not fail) in CI, and the deselects can be removed.
- The **two-off-switches check** (`gh api …/actions/permissions`) belongs in any "why isn't CI
  running?" triage.
- Feeds the forward loop: this standard is an input to the next `/reflective-requirements` that
  touches CI, test-harness, or cross-worktree verification.
