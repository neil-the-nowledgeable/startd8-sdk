# Retrospective — #226 Observability Determination-Model Build (Hansei)

**Date:** 2026-07-22
**Scope:** the #226 build, spec → Phase 2b, as it actually shipped.
**Method:** `/reflective-retrospective` — grounded in the merged code/diffs/PRs on
`origin/main`, not the docs about them.

---

## Phase 1 — the pilot (raw material)

A multi-session effort that shipped end-to-end this session: **6 merged PRs** implementing
the SDK-side determination model, plus a de-overfit research pass, a CRP round, the OQ-5
pilot grounding, and 8 filed issues. The determination surface was **grounded-verified
present on `origin/main`** before writing this (resolve_sli_kinds, _service_sli_kinds,
generate_functional_slos, messaging-semconv profile, profile_for_kinds, ServiceHints.kinds,
GenerationReport.fr_coverage, the FR-14 admission guard; 8 golden files).

| PR | FR | What shipped |
|----|----|--------------|
| #224 | — | deterministic `generated_at` (pre-work fix) |
| #238 | FR-14 | `transport` optional + `kinds`; admit transport-less kind-declaring workers |
| #243 | FR-6 | kind→profile table (`messaging-semconv`; `profile_for_kinds`; `resolve_descriptor` kind tier) |
| #244 | FR-12/13/5a | `resolve_sli_kinds`; delete unconditional RED synthesis; consume `functional[]` |
| #245 | FR-5/9 | `generate_functional_slos` (convention-sourced, `source_fr` labels); `fr_coverage` (∅ vs unfulfilled) |
| #246 | FR-12a | gate the alert/SLO triplet on the SLI set (ANDed with the per-metric gate) |

---

## Phase 3 — Retrospective Insights (belief → actual)

Every row is a place my model of my own work was wrong — the richest ore.

| What I believed | What the actuals revealed | So the standard is… |
|-----------------|---------------------------|---------------------|
| #226 = "add an `async_worker` branch." | The de-overfit research (2 agents) proved the defect was an **unconditional-RED determination model** — async_worker was one symptom of a general overfit to the Online-Boutique/HTTP first use case. 6 latent sibling symptoms filed (#228–233). | **Run a de-overfit audit before a "just add a case" fix** — find the general defect the case is an instance of. |
| FR-7 (per-signal_kind thresholds) was mine to build. | A **concurrent agent's PR #234** had already shipped its *own* "FR-7" on the **same** `_resolve_threshold` (criticality-scaled thresholds). Discovered only while implementing. | **Check for concurrent in-flight work on the target seam** (`git fetch` + grep `origin/*` for the function) before building; **compose onto the collision, don't rebuild** it. |
| Once I emit the ∅-coverage report (FR-9), it will populate. | It was **dead code**: `extract_service_hints` hard-dropped transport-less services *before* the resolver ran (fixed by FR-14). The CRP caught this as its load-bearing finding. | **Trace the data path end-to-end** — a new output path is dead if an upstream gate drops its inputs. |
| The v0.4 spec's FR-12 ("fallback only when nothing declared") was internally consistent. | My **own unit test** exposed it contradicting OQ-6 ("additive") — a declared signal *suppressed* the RED base instead of adding to it. Resolved to additive. | **Tests-as-design-pressure**: a failing test on your own new code often means the *spec* self-contradicts, not the code. |
| The OQ-5 pilot evidence was lost / never committed. | It existed at a **mis-spelled path** (`dev/OSS/mastadon/`, under `OSS/` not `dev/`) and was fully byte-verifiable. Mid-investigation a **folder rename** made it look deleted. | **Broaden the search** (whole `~/Documents`, not just `dev/`) before concluding "absent"; **a vanished dir may be a rename**, not a delete — verify/ask. |
| GitHub "MERGEABLE" ⇒ safe to merge. | MERGEABLE is **textual**, not semantic. #234 and #246 each touched a file under a golden/regression gate; only a **simulated merged-state test run** (scratch worktree) proved they didn't break the goldens. | **Simulate + test the merged state** before merging any PR that shares a gated file with in-flight work. |
| My worktree/branch base was current. | A **stale `origin/main`** base (missing #239's §0.4) was caught before it regressed the spec; the shared working tree got **switched to another agent's branch** mid-session. | **`git fetch` before branching; one dedicated worktree per effort;** never trust the shared tree's current branch. |

---

## Phase 4 — the standards this build PROVED

Three reusable standards, each grounded in the evidence above.

### STD-1 — Byte-parity-gated incremental generator evolution
When evolving a deterministic generator whose output consumers depend on:
1. **Land a full-output golden fixture matrix FIRST** (before touching the generator), chosen
   so each fixture exercises a path a later change will touch. (Evidence: `test_http_golden.py`,
   8 goldens; http-with-availability / counter-only / grpc.)
2. Hold the invariant **"absent the new input ⇒ byte-identical output"** in every increment.
   (Evidence: `ServiceHints.kinds` empty ⇒ transport default; `functional[]` empty ⇒ pre-#226;
   goldens **9/9 through all 6 PRs**.)
3. **One FR per small PR**, branched off *fresh* `origin/main`, full suite at each step.
   (Evidence: only 3 pre-existing failures throughout; each PR independently reviewed.)
4. Regenerate goldens **only on intended change**, via an explicit flag, and review the diff
   (it makes a behavior change *visible* — e.g. FR-13's future effect on counter-only RED).

### STD-2 — Concurrent-multi-agent git safety protocol
When multiple agents share a repo/worktree tree:
- `git fetch` **before** every branch/base operation (stale-base catch).
- Branch off **fresh `origin/main`** per increment; work in a **dedicated worktree**, never the
  shared tree (which another agent may switch out from under you).
- Before merging a PR that shares a file with another in-flight PR: **create a scratch worktree,
  merge the other's state, run the tests** — "MERGEABLE" is textual, not semantic.
- A colliding concurrent PR on the same seam → **reconcile by composing onto it** (extend its
  table/mechanism), not by building a rival. (Evidence: #226 FR-7 composed onto #234's
  criticality table — one `_resolve_threshold`, two axes.)
- A vanished gitignored dir is more likely a **rename / another agent's action** than a delete —
  verify before concluding. (See also the existing memory on `git worktree remove` deleting
  gitignored payload.)

### STD-3 — Grounding-gated spec derivation
Never let a spec outrun its evidence:
- **Byte-verify sub-agent claims** before baking them into a spec. (Evidence: the pilot's "worker
  got HTTP SLOs" and "no async series", the availability-gauge independence, and the transport
  hard-drop were each `grep`/`sed`-confirmed against source before being written down.)
- Resolve grounding open-questions by **locating real evidence** (the pilot), not inventing.
- Where **no universal series exists**, the honest move is **convention-source it or report it
  `unfulfilled`** (FR-9), **never fake PromQL**. (Evidence: FR-6a; `generate_functional_slos`
  records ungroundable FRs as unfulfilled rather than emitting a fabricated artifact.)

---

## Phase 5 — principle hardening

The three standards map cleanly onto the ecosystem design principles, which is corroboration:
- **Genchi Genbutsu** — STD-3's byte-verification + go-and-see-the-pilot; STD-1's goldens bind to
  *real* current output.
- **Mottainai** — STD-2's "compose onto the collision, don't rebuild"; forwarding evidence, not
  re-deriving it.
- **Accidental-Complexity anti-principle** — the whole de-overfit reframing (one general rule over
  a per-case list); STD-1's single golden gate over ad-hoc spot checks.
- **Context-Correctness-by-Construction** — STD-1's byte-parity invariant; the dead-path detection
  (a slot exists but its input never arrives) is exactly this principle's failure mode.

---

## What is PROVEN vs still UNVALIDATED (the honest boundary)

- **PROVEN:** the determination model is **byte-parity-safe** (goldens 9/9) and **unit-correct**
  (each FR independently tested; the ∅-service, hybrid, additive-signal, and mis-fed-metric cases
  covered). The three standards above are proven by the build itself.
- **NOT YET PROVEN — live end-to-end.** The entire Phase 2b is **inert until cross-repo CR-1/2/3**
  ship `functional[]` + service `kind` from ContextCore/cap-dev-pipe. Until then the new paths
  execute only against synthetic fixtures. The correctness of the *convention-sourced series*
  (FR-6a's `messaging_*` names) against a real worker fleet is **a validation task**, not a proven
  fact — it needs a fresh pilot on a subject that actually exports worker metrics (the Mastodon
  subject emits none). Do not describe Phase 2b as "working" — describe it as "built, gated, and
  awaiting the cross-repo unlock."

---

## Phase 6 — Yokoten (spread) + feed the forward loop

- **Spread STD-1** to the other deterministic generators (`backend_/view_/scaffold_codegen`) and to
  **#77** (`view_codegen` workspace archetype — the confirmed sibling of the #226 overfit pattern):
  land a golden before evolving, hold absent-input parity.
- **Spread STD-2** repo-wide — it generalizes the existing worktree/stale-base memories into a
  merge-time protocol.
- **Feed forward:** these standards become inputs to the next `/reflective-requirements` — the next
  generator-evolution spec should *open* with STD-1's golden-first clause and STD-3's grounding gate,
  rather than re-deriving them.
- **Next concrete step for #226 itself:** the cross-repo CR-1/2/3 work, then an OQ-5-style grounding
  pilot to validate the convention series live.

---

*Captured to the SDK Design-Docs Lessons base (Yokoten). PROVEN/UNVALIDATED boundary is
load-bearing — this build proved a mechanism, not a live outcome.*
