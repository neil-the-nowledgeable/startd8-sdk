# The Capability-Delivery Loop — a retrospectively-extracted standard

**Type:** Process standard (Hansei/Yokoten — extracted from a lived pilot, grounded in the actuals)
**Date:** 2026-07-23
**Extracted from:** the ContextCore-on-Mastodon observability arc, PRs #300/#306/#307/#310/#311/#312/#313/#314
**Status:** Proven (each clause is grounded in a merged PR / persisted CRP appendix below)

> This is a **retrospective** standard: it was not designed up front, it was **read off** eight
> consecutive capabilities that all — independently — converged on the same shape. Every rule cites the
> PR/commit/appendix that proved it. A rule the arc did not actually exercise is marked *speculative*.

---

## 0. What actually happened (the raw material)

Eight observability capabilities shipped to `main` in one arc, each closing a gap the Mastodon pilot found:

| PR | Capability | The loop that produced it |
|----|-----------|---------------------------|
| #301 | #300 A–D — four PromQL defects in the #286 declared-series binder | direct fix + regression tests |
| #306 | #300 D2 — declared-**functional** SLI binding | reflective-reqs → CRP → v0.4 → impl |
| #311 | #307 — span-metrics SLI binding | reflective-reqs → CRP → v0.4 → impl |
| #310 | latent `fr_coverage`-gate bug in **already-shipped** code | **surfaced BY the #307 CRP**, fixed standalone |
| #312 | #308 P0 — synthetic-probe freshness (static/$0) | reflective-reqs → CRP → v0.4 → impl |
| #313 | #308 P1–P3 — runner spec / pending-probe verdict / link-aware core | reflective-reqs → CRP → v0.4 → impl |
| #314 | code-review `--fix` over #313 | `/code-review` → grounded fix + declined-with-rationale |

Persisted proof the CRP rounds happened (Appendix A dispositions, on `main`):
`DECLARED_FUNCTIONAL_SLI_REQUIREMENTS.md` (v0.4, ~10 applied), `SPANMETRICS_SLI_BINDING_REQUIREMENTS.md`
(v0.4, 10 applied), `SYNTHETIC_PROBE_P0_REQUIREMENTS.md` (v0.4, 10 applied),
`SYNTHETIC_PROBE_P1P3_REQUIREMENTS.md` (v0.4, 8 applied).

---

## 1. Retrospective Insights (belief → actual)

| What I believed | What the actuals revealed | So the standard is… |
|-----------------|---------------------------|---------------------|
| "The dead-key lesson recurred **verbatim** 3×." | Grep of the merged specs: `DECLARED_FUNCTIONAL` 6 mentions, `SPANMETRICS` 1, `SYNTHETIC_PROBE_P0` **0**. The lesson recurred **structurally** (every new lane added a `bound_*`/`pending_*` `fr_coverage` key **and** a `compare.py` consumer edit) but not lexically. | **§3 Recurring-Failure Checklist item C is structural, not a phrase to grep for** — codify the *shape* ("new key ⇒ consumer edit"), verify it by consumer wiring, not by doc wording. |
| "CRP was 2 rounds per spec." | The `#### Review Round` string counts **2** only because the reviewer-instruction template also contains it; there was **1 real round** per spec. | The loop's value came from **one well-scoped round**, not many — a single grounded adversarial pass caught the bugs (§2). |
| "CRP is a nice-to-have review." | It caught **real, shipping-blocking bugs** every time, incl. **two latent bugs in already-merged code** (#310; the validate_promql leak in P0 R1-F1). | CRP is **load-bearing**, not optional — and it audits *adjacent shipped code*, not just the diff (§2). |
| "P2-live/P3 could be finished here." | They need a live Mastodon + Tempo traces that don't exist in-repo; only the SDK harness + pure cores are unit-provable. | **Definition-of-Done tiering (unit vs external) is mandatory** — never claim external-tier work done from unit tests (§4). |

---

## 2. The Standard: the Capability-Delivery Loop

Every non-trivial capability in the arc followed this exact sequence. It is the process to repeat.

```
reflective-requirements                       CRP round                     ship
┌─────────────────────────────┐   ┌──────────────────────────┐   ┌───────────────────────┐
v0.1 draft                    │   │ spawn a reviewing agent  │   │ worktree off origin/  │
→ plan/GROUND against real    │   │ grounded in the MERGED   │   │   main (branch-first) │
   code (not the docstring)   │──▶│   code (not the doc)     │──▶│ implement → test      │
→ reflect (discovery table)   │   │ 8–10 anchored suggestions│   │ → merge → clean up wt │
→ lessons hardening (v0.3)    │   │ triage ALL → Appendix A  │   │ → update memory       │
→ principle hardening (v0.3.1)│   │ → v0.4                   │   │                       │
└─────────────────────────────┘   └──────────────────────────┘   └───────────────────────┘
```

**Non-negotiable clauses (each proven by the arc):**

1. **Ground before you spec.** The planning pass reads the *actual* code, and it repeatedly overturned the
   naïve draft: #307 found a `span-metrics-connector` descriptor already existed (with the *wrong* unit);
   #308 P0 found the `freshness` template's `age` shape was wrong for a probe. *Proof: the §0 Planning
   Insights tables in each spec.*
2. **One grounded CRP round, triaged to persistence.** Spawn an independent reviewer, force it to verify
   against the merged tree, take **all** accept-worthy suggestions into **Appendix A** (cross-model memory).
   *Proof: 4 specs × ~10 dispositions each, on `main`.*
3. **CRP audits the neighbourhood, not just the diff.** Two of the arc's bugs were in *already-shipped*
   code the review touched tangentially (#310 gate; the P0 validate_promql leak). *Proof: #310 commit body
   cites "found during the #307 CRP (R1-F7)".*
4. **Implement in a worktree off `origin/main`, merge, clean up, update memory.** Never on the shared
   working tree. *Proof: every feature PR; the worktree-removal + memory-append steps.*
5. **Tier the Definition of Done.** Mark each FR **unit** (gates merge) or **external** (needs a live
   subject); never fake the external tier. *Proof: #313 spec §4a; P2-live/P3-validation shipped as
   documented-external, not claimed.*
6. **Close with `/code-review --fix`, documenting Applied AND Declined.** *Proof: #314 commit body.*

---

## 3. The Recurring-Failure Checklist (the bugs CRP caught — grep for these on the next capability)

These are the failure *classes* the arc's reviews caught. Run this list against any new
observability-generator capability **before** the CRP round, to front-load them:

- **A — Cross-lane double-emit.** A new declared lane and an existing one both bind the same
  `(service, kind)`. *Caught: #307 R1-F4 (span-vs-declared-series) → a single `declared_binding_owner`
  authority.*
- **B — Unit/scale mismatch in a threshold.** A metric family in seconds vs milliseconds → a **1000×**
  wrong SLO target. *Caught: #307 R1-F2 → `scale_threshold_seconds`.*
- **C — A new `fr_coverage` key is DEAD unless `compare.py` consumes it** (structural, §1). Every
  `bound_*`/`pending_*` key needs a `ComparisonReport` field + `build_comparison_report` read +
  `render_report` section + often an `_entry_line` shape. *Caught: D2 R1-F10, #307 R1-F6, and the P0
  compare surface — three lanes, same shape.*
- **D — A drift-prone hardcoded key/enum list.** A gate keyed on a fixed subset that silently omits new
  keys. *Caught: #310 (the `fr_coverage`-emission gate) → gate on `any(values())`, drift-proof.*
- **E — A dead-SLI leak into a file-based validator.** An artifact on disk whose query targets a
  not-yet-real metric → replayed as a #274 dead SLI / exit-2. *Caught: P0 R1-F1 (write no SLO file) and
  P1–P3 R1-F2 (synthesize the verdict, exclude from the coverage denominator).*
- **F — A fabrication path.** Inventing a threshold / credential / metric the SDK has no basis for.
  *Caught repeatedly by NR-1 discipline (Genchi Genbutsu); P1–P3 R1-F5 (a runner spec with a dangling
  secret must be structurally `runnable: false`).*
- **G — Byte-identity regression.** A new key emitted as `[]` (not absent) breaks golden fixtures.
  *Caught: D2 FR-9, echoed in #307/#308.*

---

## 4. Definition-of-Done tiering (the honesty discipline)

For any capability that touches a runtime/external surface, split the FRs:

- **unit tier** — deterministic, unit-testable, **gates merge**. (P1 runner spec, P2 verdict/promotion
  logic, P3 pure delta core.)
- **external tier** — needs a live subject (a running Mastodon, real Tempo traces); documented as a
  manual/CI-with-subject run, **NOT claimed complete from unit tests**.

State the split in a per-phase table (proof: #313 spec §4a) and in the PR body. This is what let the arc
ship P1–P3 honestly without a live subject.

---

## 5. Yokoten (where this standard applies next)

- The **immediate siblings**: the cross-repo ContextCore #58 / REQ-CCL-109 carry (feeds `declared_probes`
  + `declared_span_signals`), and #308 P2-live / P3-validation once a live Mastodon/Tempo subject exists —
  run each through this loop.
- **Any new `fr_coverage` lane** (a future `bound_*`/`pending_*` key): checklist item C is mandatory.
- **Feeds the forward loop:** this doc is now an *input* to the next `/reflective-requirements` for an
  observability-generator capability — the Recurring-Failure Checklist (§3) becomes the draft's
  pre-CRP self-audit, so the same bugs are front-loaded before the review round even runs.

---

*Extracted retrospectively (Hansei). Every clause cites a merged PR / persisted CRP appendix; the one
belief→actual correction (the "3× dead-key" over-claim) is recorded in §1 rather than propagated.*
