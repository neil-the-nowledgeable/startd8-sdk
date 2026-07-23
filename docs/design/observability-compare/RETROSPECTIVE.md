# Retrospective — building the compare-live fidelity/regression capability (Hansei)

**Date:** 2026-07-23 · **Pilot:** the `compare-live` arc — PRs #283 (Tier-B live runner + CI gate),
#288 (warm-up gate), #290 (pilot-repro fixture + CI-gate-in-CI), plus the CRP R1 review, the live-proof
against the OTel-demo Prometheus, and the `/code-review` pass. **Method:** grounded in the actuals
(code, commits, test runs, review findings), not the design docs.

This is the inductive twin of the `../observability-requirement-shaped/RETROSPECTIVE.md` — it extracts
the **standard the arc proved**: how to build, verify, and gate a *fidelity/regression* capability.

---

## Phase 3 — Retrospective insights (belief → actual)

| What was believed | What the actuals revealed | So the standard is… |
|---|---|---|
| Tier A was "being prototyped in parallel / in flight" (the proposal + the ask) | Tier A had **already merged** — `de5f40a3` #282, 2026-07-22 22:40, before Tier B work began (`git log`) | Before building a twin/tier, `git log`+grep the **real tree**; treat "in flight" as an unverified claim. Import the merged surface read-only. |
| "Reuse `fleet.compose` (relax egress-deny)" (proposal §4) | `generate_compose_dict` is ServiceSpec-fleet-shaped, `internal:true`, **no Prometheus concept** anywhere | Verify a "reuse X" claim against **X's actual shape** before designing on it; a purpose-built 60-line standup beat bending the projector. |
| Mastodon is the hero subject to *stand up* | Mastodon is multi-container (PG+Redis+Sidekiq) — one `subject_image` can't | Scope by the **subject's real topology**; single-image v1 + `--prometheus` for heavy subjects. |
| "Wait for a scrape, then replay" is the gate | A single landed sample releases before lazy SLI series register → **false `fail`** (surfaced in CRP R1-F1/F2, built in #288) | A fidelity gate must confirm the subject is **warm** (series set settled across ≥2 scrapes), not merely responsive. `live_standup.py:192`. |
| Unit-green ⇒ the capability works | The **live-proof** against real telemetry was the true validator — the demo emits `*_milliseconds` / the `span-metrics-connector` convention, producing real `fail` verdicts + an actionable one-line fix | A fidelity capability is not proven until **fired at real telemetry** (genchi genbutsu), not just fixtures. |
| The baseline-diff CI gate guards regressions | It is **blind to *dropped* SLIs** (0 fails ⇒ 0 new fails ⇒ false PASS), and the workflow **silently-greened on a crash** (`exit 1` fell through to pass) — both found by `/code-review` | A diff/allowlist gate needs a **presence floor** + a **fail-closed** exit mapping. |
| `$?` after the CLI reports the CLI's exit | `... | head` made `$?` report *head* — a `FAIL` (exit 2) read as `0` | Never read `$?` through a pipe; capture without the pipe (or `PIPESTATUS`). |
| The red parity test was ours/unrelated-and-open | Fixed by a **concurrent session** — `add509af` #284 (declare kickoff+grant metrics) | Re-check `origin/main` before acting on a "known-broken" test; the tree moves under you. |
| I was adding *the* observability CI gate | An **`observability-fidelity.yml`** workflow already existed (reusable `validate-promql` coverage gate); I'd added a parallel one without checking — violating this doc's own **Rule 1** while writing it | Rule 1 is load-bearing precisely because it is easy to skip: grep `.github/workflows/` before adding CI. Kept both (genuinely complementary) but **differentiated** them in-header + README. |

Nine surprises → the loop worked (Phase-3 heuristic: zero surprises means you read the docs, not the code). The last one is the sharpest: I tripped Rule 1 *while authoring it* — evidence the rule earns its place.

---

## Phase 4 — The extracted standard: building a fidelity/regression capability

A **fidelity capability** answers "does the derived/declared artifact bind to the *real* emitted
surface?" This arc proved a repeatable shape for building one:

1. **Reconcile against the real tree first.** `git log` + grep the actual code before accepting any
   "in flight / reuse X / X is the subject" premise. (Surprise rows 1–3.) Import merged siblings
   read-only; never re-spec them.
2. **Reuse the authoritative engine; add only the missing seam.** The replay engine (`run_validation`
   → `FidelityReport`, verdicts `pass|bound_no_data|fail`) and the Prometheus client were reused
   verbatim; the only new substrate was standup + the readiness gate. Mottainai over rebuild.
3. **The readiness gate is load-bearing and must prove *warmth*, not liveness.** Gate on the subject's
   metric surface having **settled** (samples landed **and** series count stable across two consecutive
   scrapes, `live_standup._await_scrape`), else replay reads a false `fail`. Timeout → `unknown`, never
   `fail` — an un-observable subject is not a dead SLI.
4. **Merge tiers with an explicit severity rollup; the live signal is authoritative.**
   `unknown > fail > pass`; static/advisory gaps never mask a live failure and never fail the build
   unless opted in (`--strict-tier-a`).
5. **A regression gate is a *diff* — so it needs two guards the diff itself lacks:**
   - a **presence floor** (the known artifacts still generate) — a diff is blind to *disappeared*
     coverage (`compare_live_gate.sh` `EXPECT_MIN_SLOS`);
   - a **fail-closed exit mapping** — unexpected/crash codes must fail, never fall through to pass.
   - a **stable, dir-qualified identity** for baselined items (basename alone collides across dirs —
     CRP R1-F8), and **explicit-operator-only** re-baselining (never self-heal — NR-4).
6. **Prove it on real telemetry before declaring done.** Fixtures test the *logic*; only a live replay
   against a real emitting subject proves the *fidelity claim*. Persist the repro as a committed fixture
   so the proof is repeatable, then wire it as the CI gate.
7. **Adversarially review the gate itself.** The gate's whole value is catching regressions, so its
   worst failure is a **silent green**. Review specifically for "could a broken pipeline PASS?" — that
   lens found both silent-green modes in #290.

---

## Phase 5 — Lessons + principle

**Lesson (reusable):** *A baseline-diff / allowlist gate is asymmetric — it catches NEW bad items but
is blind to EXPECTED items that vanished.* Any such gate needs a companion presence/floor check and a
fail-closed exit mapping, or a regression that deletes coverage passes silently. (Detection: drop a
baselined id → must exit non-zero; drop the generated artifacts → must exit non-zero. Archived:
`craft/Lessons_Learned/skills/python-code-refactor/archive/2026-07-23-compare-live-ci-gate.md`.)

**Principle candidate — "Prove warmth, not liveness" / genchi-genbutsu for gates:** a check that judges
a live system must bind to the *settled real surface* and fail **open** to `unknown` when it cannot
observe, and fail **closed** to a build failure when its own machinery breaks. Distinct from the
existing Genchi Genbutsu principle by naming the *temporal* trap (respond ≠ warm) and the *gate-integrity*
trap (a gate that can't run must not pass).

---

## Phase 6 — Yokoten (spread)

- The **presence-floor + fail-closed** pair applies to every baseline/allowlist gate in the repo
  (parity guards, golden-matrix checks, the security gates) — audit them for the disappeared-item blind
  spot and crash-passes.
- The **"prove on real telemetry, persist as a committed fixture, wire as CI"** rung applies to the
  sibling deterministic-codegen gates (drift/idempotency) — they are fixture-proven but not live-proven.
- Feeds the forward loop: this standard is an input to the next `/reflective-requirements` for any
  fidelity/regression capability (e.g. a Tier-B multi-container subject, NR-1).
