# Synthetic-Probe SLI — P1–P3 (runner spec · live pending-probe verdict · link-aware) — Requirements

**Version:** 0.4 (post CRP Round 1 — 8 suggestions + adversarial, all applied; ready to implement)
**Date:** 2026-07-23
**Status:** IMPLEMENTED (unit tier, 2026-07-23) — P1 runner-spec + exclusion + reason_code state machine; P2 `pending_probe` verdict synthesis + severity-0 + promotion builder; P3 pure `SpanLite` delta core. 14 tests. **P2-live + P3-validation are EXTERNAL (a live Mastodon/Tempo subject), NOT done here.**
**Owner:** observability artifact generator (`src/startd8/observability/`)
**GitHub:** startd8-sdk **#308**, Phases **P1/P2/P3** (P0 shipped, PR #312)
**Refs:** `SYNTHETIC_PROBE_SLI_DESIGN.md` (the P0–P3 frame), `SYNTHETIC_PROBE_P0_REQUIREMENTS.md` (v0.4,
IMPLEMENTED), option-b2, #300 D2 / #307 (the declared-lane patterns)

---

## 0. Planning Insights (Self-Reflective Update)

> What the planning pass (reading `validate_promql`, `compare_live`, the extended-artifact + secret-
> reference emitters) corrected from the naïve "run the probe and bind the SLI" draft.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| P1 writes the freshness SLO to `slos/` (finally emitting the P0-deferred SLO). | The metric is published only when the probe **actually runs** (deploy-time, P2), not when the runner *spec* is emitted (P1). Writing the SLO at P1 reintroduces the exact R1-F1 dead-SLI leak P0 closed. | **P1 emits only the runner SPEC** (a non-PromQL artifact); the freshness SLO stays in `pending_probes` until a **live run confirms binding (P2)**, then is promoted to `slos/`. The lifecycle is declared→runner→live-confirmed→SLO. |
| The runner spec needs new exclusion plumbing so `validate_promql` skips it. | `validate_promql._EXCLUDED_ARTIFACT_DIRS` already excludes non-PromQL sibling dirs (`service-monitors`/`loki-rules`/`notifications`/`runbooks`) by subdir. | **Add one entry** (`probe-specs → probe_spec`); the runner spec rides the existing exclusion seam. No new mechanism. |
| The probe needs bespoke secret handling. | The notification-policy path already has a **reference-secrets-never-fabricate** discipline (`Receiver.target` → `# UNRESOLVED REQUIRED PARAM:` on a dangling ref). | **Reuse it:** the runner spec references credentials by name (env/secret ref), never inlines them; a missing ref is emitted as an explicit unresolved marker, not a fabricated token. |
| P2's "pending-probe" is a new verdict engine. | `compare_live`/`validate_promql` already have a closed verdict taxonomy (`pass\|fail\|bound_no_data\|error\|excluded`) + a rollup where `unknown > fail > pass`, and `fr_coverage` is already threaded into the merge. | **Add ONE verdict value** `pending_probe` (a metric that's *expected-absent until the runner runs* — NOT a `fail`/dead SLI), keyed off the `pending_probes` fr_coverage the P0 lane already emits. Reuse the taxonomy + rollup; do not restate. |
| P3 link-aware cross-trace is buildable now. | It needs **Tempo trace data with span links** (`FeedInsertWorker`→enqueue) to compute the delta; there is no trace-query client or link fixture in-repo, and the analysis is novel (most connectors don't do cross-trace link math). | **P3 = the alternative track:** specify the algorithm + a testable pure-function core (given two linked spans, compute the delta) but gate live validation on a trace fixture (OQ). Do NOT fake a live proof. |

**Resolved (from the design doc OQs):**
- **OQ-1 (runner artifact) → a portable `probe-spec.yaml`** (declarative; one concrete runner recipe
  documented) — the SDK emits the spec, an operator/runner executes it (mirrors ServiceMonitor/alert: emit,
  don't run). **OQ-2 (credentials) → secret-reference discipline** (reuse notification-policy). **OQ-5
  (compare semantics) → the `pending_probe` verdict** (FR-P2-1).

### 0.1 Lessons-Learned Hardening (v0.3)
- **Phantom-reference audit** — verified: `_EXCLUDED_ARTIFACT_DIRS` (`validate_promql.py:274`), the verdict
  taxonomy (`compare_live`/`validate_promql` `ExprVerdict.verdict`), `_EXTENDED_PER_SERVICE_GENERATORS`
  (`artifact_generator.py:214`), the notification-policy secret discipline, the P0 `pending_probes` lane
  (shipped #312). Added §9.
- **[verify-consumer-against-merged-diff]** — the P2 live-binding proof is gated on a REAL Tempo/Mastodon
  surface; it is NOT claimed complete from unit tests (the SDK harness is unit-tested, the live proof is an
  external run — §5, OQ).
- **Single-source vocabulary ownership** — the verdict taxonomy stays owned by `validate_promql`; P2 adds a
  value, never a parallel enum. The published-metric contract stays owned by the `DeclaredProbe` (P0).

### 0.2 Design-Principle Hardening (v0.3.1)
- **Genchi Genbutsu / not-fabrication** — the runner spec references real credentials (never inlines/fakes);
  the SLO is promoted to `slos/` only after a **real** live run confirms the metric exists (not on faith).
- **Mottainai** — reuse the exclusion dir, the verdict taxonomy+rollup, the secret discipline, the P0
  `pending_probes` lane; build no parallel machinery.
- **Accidental-Complexity anti-principle** — P1 adds one artifact type + one exclusion entry; P2 adds one
  verdict value. No new engines.
- **Hitsuzen** — the runner spec is deterministic from the `DeclaredProbe`; only the *measurement* is
  runtime. Emit the determinable spec; run nothing at generation time.

---

## 1. Problem Statement

P0 (shipped) records a freshness SLI as `pending_probes` — a positive finding, statically, at $0. But it is
*inert*: nothing runs the probe, so the metric is never published and the SLO never binds. P1–P3 close that:
**P1** emits a runnable probe spec (so an operator can run it); **P2** teaches `compare-live` that a
probe SLI is *pending a run* (not a dead SLI) and promotes it to a real SLO once a live run confirms binding;
**P3** offers a trace-native alternative (follow the span link, compute the delta) needing no synthetic
traffic. P1 is deterministic/$0; P2 is an SDK harness + an external live run; P3 is novel + trace-gated.

## 2. Requirements

### P1 — runner spec emission (deterministic, $0)

**FR-P1-1 — Emit a `probe-spec.yaml` runner artifact.** For each `DeclaredProbe`, emit
`probe-specs/{svc}-{name}-probe.yaml`: a declarative runner recipe carrying `{name, action, poll, assert,
measure, interval, timeout, published_metric, metric_kind}` + a `runner` block (a blackbox-style recipe:
how to run the action, poll for the assertion, and publish the measured latency as `published_metric`). One
concrete runner recipe (e.g. a Python/HTTP loop or a k8s CronJob shape) is documented as the reference.

**FR-P1-2 — Secret-reference discipline + structurally non-runnable on a dangling ref *(R1-F5)*.**
Credentials the action/poll need (API token, base URL) are carried as **references** (`${SECRET:...}`/env
names), never inlined; a required-but-undeclared ref is emitted as `# UNRESOLVED REQUIRED PARAM:` as the
notification-policy path does. **But** — unlike declarative Alertmanager config, a probe spec is *executed*:
a spec with ANY unresolved ref MUST be emitted **structurally non-runnable** (a top-level `runnable: false`
that the reference recipe MUST honor, or the `runner` block omitted) so a runner cannot silently run a
partial spec and publish a spurious `published_metric` (a fabrication path NR-2 forbids). See NR-6.

**FR-P1-3 — Excluded from PromQL replay.** Add `probe-specs → probe_spec` to
`validate_promql._EXCLUDED_ARTIFACT_DIRS` — the runner spec carries no PromQL, so it is enumerated as a
deliberate exclusion, never a fidelity miss. (Empty-probe byte-identity holds: the map entry is always
present, but `scan_excluded_artifacts` reports the type only when the `probe-specs/` dir exists with files —
absent probes ⇒ no dir ⇒ unchanged report. *adversarial*)

**FR-P1-4 — SLO stays in `pending_probes`; `reason_code` state machine *(R1-F1)*.** P1 does NOT write a
`slos/` file and does NOT change the P0 record's `status`/`output_path`. It **mutates the existing
`pending_probes` entry in place** — same shape, `query`/`published_metric`/`target` fields intact —
advancing only `reason_code` along the lifecycle **`probe_pending_no_runner`** (P0) **→ `probe_runner_emitted`**
(P1: a runner spec exists but hasn't run) **→ `probe_bound`** (P2: a live run confirmed + promoted). Byte-
identity when no probes (additive only).

### P2 — live pending-probe verdict + SLO promotion (SDK harness $0; live proof external)

**FR-P2-1 — A synthesized `pending_probe` verdict, EXCLUDED from the coverage denominator *(R1-F2, critical;
R1-F3, R1-F4)*.** Because P0/P1 write no SLO YAML, `extract_exprs` yields no verdict for the probe metric —
so `compare-live` **synthesizes** a `pending_probe` `ExprVerdict` from each `pending_probes` fr_coverage
entry (identified by the entry's recorded **`published_metric`** — a fr_coverage JOIN, never a `probe_`
name-prefix heuristic, since `published_metric` is author-overridable). That synthetic verdict is treated
like **`excluded`**: it is **NOT passed to `compute_coverage`** (`validate_promql.py:981`), so it can never
move `binding_coverage` below `min_coverage` and trip `status="fail"`→`EXIT_FAIL=2` — the exact #274
regression it must never cause. `pending_probe` is added **explicitly** to the verdict-taxonomy docstring
(`validate_promql.py:556`) and to the `_SEVERITY` rollup map as **severity 0** (`compare_live.py:35`) — a
declared invariant, not a `.get(default=0)` accident. It is excluded from `fail_verdicts`/`new_fail_verdicts`
(already, since it is not `"fail"`).

**FR-P2-2 — SLO promotion on live confirmation (single-sourced, no re-derivation) *(R1-F8)*.** When a live
run DOES return data for the probe metric, the freshness SLI is reported **bound** (`pass`) and the SLO is
eligible for promotion: an explicit step writes `slos/{svc}-{name}.yaml` **built from the already-recorded
`query`/`target` in the `pending_probes` entry** (Mottainai — no re-derivation; the promoted PromQL `==` the
P0-recorded string, so the next `validate_promql` self-heals off the same query). Promotion is explicit
(a `--promote-probes` flag), gated on ≥2 consecutive live scrapes (warm-up, NR-5), and `{svc}-{name}` naming
disambiguates two services' same-named probes *(adversarial)*.

**FR-P2-3 — Live proof is an external run (honesty).** The end-to-end "run against a real Mastodon, show it
binds" is an **external** live run (needs a running Mastodon + credentials + the runner). P2's SDK code
(verdict + promotion) is unit-tested with a fixture; the live proof is documented as a manual/CI-with-subject
step, NOT claimed from unit tests.

### P3 — link-aware cross-trace freshness (novel; trace-gated)

**FR-P3-1 — A pure delta-compute core with a declared input contract *(R1-F6)*.** Implement a pure function
over a typed `SpanLite{trace_id, span_id, start_ns, end_ns, links: [{trace_id, span_id}]}` pair (enqueue span
+ the linked `FeedInsertWorker` span). Compute `t(feed-visible) − t(created)` in **nanoseconds→seconds**,
sign convention `delta ≥ 0`. Typed error cases (never a negative/zero silent result): a missing/broken link
→ an `unlinkable` result; reversed timestamps → an `error`. Unit-testable on synthetic `SpanLite` inputs (no
network); the Tempo-file adapter (OQ-3) maps real trace JSON → `SpanLite`.

**FR-P3-2 — Trace-native, no synthetic traffic.** Document that this grounds freshness by following the real
`propagation_style: :link` span link — an alternative to the P1 synthetic probe (no injected statuses).

**FR-P3-3 — Live validation is trace-gated (OQ).** A real proof needs Tempo traces carrying the link; P3
ships the algorithm + pure-core tests, and gates the live binding on a trace fixture/OQ — not faked.

## 3. Non-Requirements

**NR-1 — P1/P2/P3 run nothing at generation time.** The SDK emits specs and classifies; it does not execute
probes or query Tempo during artifact generation.
**NR-2 — No fabricated credentials or metrics.** (Genchi Genbutsu.)
**NR-3 — No new verdict engine / no parallel exclusion mechanism.** Reuse the taxonomy + the exclusion dir.
**NR-4 — P3 is the alternative track, not a P1 replacement.** They coexist (synthetic vs trace-native).
**NR-5 — No auto-promotion of a pending SLO on a single scrape** (warm-up discipline).
**NR-6 — Never emit a runnable spec with a dangling secret** (R1-F5) — unresolved ref ⇒ `runnable: false`.

## 4a. Definition of Done (per-phase tier) *(R1-F7)*

| FR | Deliverable | DoD tier |
|----|-------------|----------|
| FR-P1-1..4 | probe-spec artifact + exclusion + reason_code state machine | **unit** ($0, gates merge) |
| FR-P2-1 | synthesized `pending_probe` verdict, excluded from coverage | **unit** |
| FR-P2-2 | promotion logic (pending entry → `slos/` yaml, single-sourced) | **unit** |
| FR-P2-3 / P2-live | run against a real Mastodon, show it binds | **external** (not merge-gating) |
| FR-P3-1 | pure `SpanLite` delta core | **unit** |
| FR-P3-2/3 / P3-validation | live link-aware proof on real Tempo traces | **external** |

Only **unit**-tier FRs gate merge; **external**-tier FRs are documented as manual/CI-with-subject runs and
are NOT claimed complete from unit tests.

## 4. Open Questions

- **OQ-1 — runner recipe surface.** Which ONE concrete runner does the reference recipe target — a portable
  Python/HTTP loop (zero infra) or a k8s CronJob (cluster-native)? Lean: the portable loop as the reference,
  the CronJob shape documented.
- **OQ-2 — P2 promotion trigger.** A `--promote-probes` flag on `compare-live`, or a separate `promote`
  verb? Lean: a flag, gated on ≥2 consecutive live scrapes (warm-up).
- **OQ-3 — P3 trace client.** Does the SDK gain a minimal Tempo trace-query client for P3, or does P3 consume
  an exported trace file? Lean: consume a trace file (no live Tempo dependency in the SDK) for v1.
- **OQ-4 — ContextCore carry.** `declared_probes` carry (shared with P0) — still pending cross-repo.

## 9. Reference Audit

| Symbol / fact | Location | Exists? |
|---|---|---|
| `_EXCLUDED_ARTIFACT_DIRS` (add `probe-specs`) | `validate_promql.py:274` | ✅ |
| verdict taxonomy `pass\|fail\|bound_no_data\|error\|excluded` (add `pending_probe`) | `validate_promql.py:556` | ✅ |
| rollup `unknown > fail > pass` + `fr_coverage` merge | `compare_live.py:34/101` | ✅ |
| `_EXTENDED_PER_SERVICE_GENERATORS` (add the probe-spec generator) | `artifact_generator.py:214` | ✅ |
| notification-policy secret-reference discipline | `generate_notification_policy` | ✅ |
| P0 `pending_probes` lane (the P2 key) | shipped #312 | ✅ |
| `generate_declared_probe_spec` / `pending_probe` verdict / link-delta core | — | ❌ to add |
| Live Mastodon/Tempo surface (P2 live, P3 validation) | external | ⏳ not in-repo |

---

*v0.4 — Post CRP Round 1 (8 F-suggestions + adversarial, all ACCEPTED; dispositions in Appendix A). The load-bearing change: FR-P2-1 synthesizes the pending_probe verdict from fr_coverage and excludes it from the coverage denominator (never exit-2). Plus FR-P1-4 reason_code state machine, FR-P1-2 runnable:false, FR-P3-1 SpanLite contract, §4a Definition of Done. 10 FRs / 6 NRs / 4 OQs. Ready to implement.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | FR-P1-4 as a reason_code state machine, mutate pending entry in place | CRP R1 | Applied → FR-P1-4 (probe_pending_no_runner→probe_runner_emitted→probe_bound) | 2026-07-23 |
| R1-F2 | **Critical:** synthesize the pending_probe verdict from fr_coverage; exclude from compute_coverage (never exit-2) | CRP R1 | Applied → FR-P2-1 | 2026-07-23 |
| R1-F3 | Add pending_probe to _SEVERITY map (severity 0) explicitly, not .get default | CRP R1 | Applied → FR-P2-1 | 2026-07-23 |
| R1-F4 | Identify probe metric by fr_coverage published_metric join, not probe_ prefix | CRP R1 | Applied → FR-P2-1 | 2026-07-23 |
| R1-F5 | Runner spec with a dangling secret must be structurally non-runnable (runnable:false) | CRP R1 | Applied → FR-P1-2 + NR-6 | 2026-07-23 |
| R1-F6 | FR-P3-1 needs a typed SpanLite contract + units/sign + unlinkable/error cases | CRP R1 | Applied → FR-P3-1 | 2026-07-23 |
| R1-F7 | Per-phase Definition of Done (unit vs external) | CRP R1 | Applied → new §4a | 2026-07-23 |
| R1-F8 | Promotion writes slos/ from the recorded query (Mottainai, no re-derivation) | CRP R1 | Applied → FR-P2-2 | 2026-07-23 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-23

- **Reviewer**: claude-opus-4-8 (1M context)
- **Date**: 2026-07-23 00:40:00 UTC
- **Scope**: Requirements review of P1/P2/P3, grounded in `validate_promql.py`, `compare_live.py`, `artifact_generator_generators.py` (`generate_declared_probe_slos`, `generate_notification_policy`), `artifact_generator_models.py` (`DeclaredProbe`). Focus-file asks answered first, then F-suggestions.

##### Focus-file asks

**Ask 1 — FR-P1-4 lifecycle boundary (P1 emits runner spec, does NOT write the SLO).**
- **Summary answer:** Yes — the seam is correct; P1 must NOT write the SLO. But `reason_code` advancement needs to be specified as a transition, not just a new terminal value.
- **Rationale:** `generate_declared_probe_slos` already returns `status="skipped"`, `output_path=""`, and stashes the SLO shape in `quality={"pending_probes": [...]}` with `reason_code="probe_pending_no_runner"` (`artifact_generator_generators.py:1760,1773-1781`). Writing the SLO at P1 would put a query on `probe_<name>_seconds` into `slos/`, which `extract_exprs` (`validate_promql.py:228`) would replay against a metric that does not exist yet → a `fail` verdict → the R1-F1 dead-SLI leak P0 closed. The runner spec is a *non-PromQL* artifact, so it cannot leak into replay **provided FR-P1-3's exclusion lands** (see F2). The spec content is opaque YAML (`action`/`poll`/`assert`), not PromQL — no replay-leak path exists once `probe-specs/` is in `_EXCLUDED_ARTIFACT_DIRS`.
- **Assumptions / conditions:** FR-P1-3 lands (probe-specs excluded); the P1 record keeps `output_path=""` for the SLO record itself.
- **Suggested improvements:** State FR-P1-4 as a **reason_code state machine** (`probe_pending_no_runner` → `probe_runner_emitted` → [P2] `probe_bound`/promoted), and specify which record carries the advanced code (the pending_probes entry, unchanged shape, mutated `reason_code`). See R1-F1.

**Ask 2 — FR-P2-1 the `pending_probe` verdict vs rollup / fail_verdicts / verdict_id baseline.**
- **Summary answer:** Partial — the doc under-specifies the single most important interaction. A `pending_probe` is safe against exit-2 *by default* but only because `_SEVERITY.get()` silently defaults unknown verdicts to 0; that is a fragile accident, not a designed guarantee, and the doc never says where the verdict is even produced.
- **Rationale:** The CI gate keys on `verdict == "fail"` in three places: `fail_verdicts` (`compare_live.py:101`), `new_fail_verdicts` (`compare_live.py:253-260`), and `_rollup_reason` (`:124`). A `pending_probe` value is not `"fail"`, so it is excluded from all three — good. The rollup `_SEVERITY = {"pass":0,"fail":1,"unknown":2}` (`compare_live.py:35`) has NO `pending_probe` key, so `_SEVERITY.get("pending_probe", 0)` → 0 (pass-equivalent) — safe but implicit. **The real gap:** P0 writes NO SLO YAML for the probe metric, so `extract_exprs` never yields an `ExprVerdict` for it — meaning there is nowhere for a `pending_probe` verdict to be *created* in the current file-driven `validate_promql` flow. FR-P2-1 says compare-live "classifies a probe SLI whose metric is absent" but the probe SLI is not on disk to be classified. The doc must specify the **injection point**: does compare-live synthesize a synthetic verdict from the `pending_probes` fr_coverage key (recommended), and if so, does that synthetic verdict enter `verdicts[]` (and thus `compute_coverage`'s denominator, `validate_promql.py:981`) or a separate list?
- **Assumptions / conditions:** none.
- **Suggested improvements:** R1-F2, R1-F3, R1-F4.

**Ask 3 — FR-P1-2 secret-reference for an executable runner.**
- **Summary answer:** Partial — reusing the `# UNRESOLVED REQUIRED PARAM:` discipline is right for *emission honesty*, but an executable runner needs one extra guarantee the notification-policy path never needed: a spec with a dangling secret must be **structurally non-runnable**, not merely annotated.
- **Rationale:** `generate_notification_policy` emits `_UNRESOLVED_PREFIX` as a comment marker (`:2237,2266`) because Alertmanager config is *declarative* — a human reconciles it. A probe spec is *executed*; a runner that ignores the comment and runs a spec with a missing token produces a partial/failed probe that could publish garbage or a spurious metric. The notification path's guarantee ("never a silent Slack default") does not translate to "never a silently-runnable spec."
- **Assumptions / conditions:** the reference runner recipe reads the spec.
- **Suggested improvements:** R1-F5.

**Ask 4 — FR-P3-1 pure delta core + P3 honesty.**
- **Summary answer:** Yes — the pure-function core is genuinely unit-testable without traces, and the trace-gated split is honest.
- **Rationale:** FR-P3-1 takes two spans (start/end timestamps + link) and returns a float delta — no I/O, matching the `build_live_comparison` "pure merge — the unit-test core" pattern (`compare_live.py:78`). FR-P3-3 + OQ-3 correctly gate the live proof on a trace fixture and lean "consume a trace file (no live Tempo dependency) for v1." Nothing claims a live link-aware proof from unit tests.
- **Assumptions / conditions:** the pure core's input type is a declared contract (see F6), not raw Tempo JSON.
- **Suggested improvements:** R1-F6.

**Ask 5 — P2/P3 external-dependency honesty.**
- **Summary answer:** Yes — NR-1, FR-P2-3, FR-P3-3, and §9's `⏳ not in-repo` row make the external dependency explicit and unit-provability boundaries clear.
- **Rationale:** FR-P2-3 states the live proof is "NOT claimed from unit tests"; §9 marks the Mastodon/Tempo surface `⏳ external`. This is the honesty bar the focus file asked for. One residual gap: no per-phase "Definition of Done" separating unit-provable from external — see R1-F7.
- **Assumptions / conditions:** none.

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | Specify FR-P1-4 as an explicit `reason_code` state machine and name which record advances. State: P1 mutates the existing `pending_probes` entry's `reason_code` from `probe_pending_no_runner` to `probe_runner_emitted` (same shape, `artifact_generator_generators.py:1760`), keeping `query`/`published_metric`/`target` fields intact; it does NOT add a `slos/` file and does NOT change `status`/`output_path`. Add the full lifecycle chain `probe_pending_no_runner → probe_runner_emitted → (P2) probe_bound`. | The doc says the code "advances to `probe_runner_emitted`" but never says which artifact carries it or that the pending_probes entry is mutated-in-place vs a new record. An implementer could add a parallel record or, worse, emit an SLO. The exact P0 field shape must be preserved so P2 promotion can read `query`/`target` off it. | FR-P1-4 body | Unit test: run P1 on a `DeclaredProbe`, assert exactly the `reason_code` field changed, `pending_probes` len unchanged, no file under `slos/`, `query` field still present. |
| R1-F2 | Interfaces | critical | Specify **where the `pending_probe` verdict is produced** and **that it is excluded from the coverage denominator.** Because P0 writes no SLO YAML, `extract_exprs` (`validate_promql.py:228`) yields no verdict for the probe metric — there is no natural locus for the verdict. Require FR-P2-1 to state: compare-live synthesizes a `pending_probe` `ExprVerdict` from each `pending_probes` fr_coverage entry, and that verdict is treated like `excluded` — i.e. NOT passed to `compute_coverage` (`validate_promql.py:981`), so it never moves `binding_coverage` and thus never trips `status="fail"`→exit 2 (`:1009`). | This is the exact "could a pending_probe be counted as a new dead SLI (exit 2)?" risk from the focus file. Today `binding_coverage < min_coverage` → fail → `EXIT_FAIL=2`. If a synthetic pending verdict enters the denominator as a non-bind, it can DROP coverage below min and fail the build — the precise #274 regression FR-P2-1 forbids. The `excluded` verdict already has this "not a verdict for coverage" carve-out (`:981` comment "excluded queries aren't verdicts"); `pending_probe` must join it. | FR-P2-1 body; add to §9 audit | Unit test: a run with 1 real passing SLI + N pending_probes yields `binding_coverage == 1.0` and exit 0; assert `pending_probe` verdicts are absent from `compute_coverage` input. |
| R1-F3 | Data | high | Add `pending_probe` to the closed verdict-taxonomy enum comment and to the `_SEVERITY` rollup map explicitly (as severity 0), rather than relying on `_SEVERITY.get(..., 0)` defaulting. Update the docstring at `ExprVerdict.verdict` (`validate_promql.py:556`) and `_SEVERITY` (`compare_live.py:35`). | The doc says "reuse the taxonomy + rollup; do not restate," but rollup-safety currently rests on `.get(default=0)` silently swallowing an unknown value. That is an accident, not a contract: a future refactor that raises on unknown verdicts (or maps unknown→`unknown`=severity 2) would flip pending probes into exit-3 or worse. Make the 0-severity explicit so the safety is a declared invariant. | FR-P2-1 / §9 audit row for the enum | Unit test: assert `_SEVERITY["pending_probe"] == 0`; assert a report with only pass + pending_probe verdicts rolls up to `pass`. |
| R1-F4 | Interfaces | high | Specify how compare-live **identifies a metric as a probe metric** — by fr_coverage `pending_probes` key match, NOT by a `probe_` metric-name heuristic. State the join key: the `published_metric` recorded in the `pending_probes` entry (`_probe_metric_name(probe)`, default `probe_<name>_seconds`) is the identity; matching on the `probe_` name prefix is forbidden (an author-supplied `published_metric` need not start with `probe_`). | The focus file explicitly asks "where does compare-live learn a metric is a probe metric (fr_coverage key match vs metric-name heuristic)." `DeclaredProbe.published_metric` is author-overridable (`artifact_generator_models.py:109`), so a name-prefix heuristic would misclassify. The pending_probes entry already carries `published_metric` — join on it. | FR-P2-1 body | Unit test: a probe with `published_metric="mastodon_fanout_seconds"` (no `probe_` prefix) is still classified `pending_probe` via the fr_coverage join. |
| R1-F5 | Security | high | Strengthen FR-P1-2: a probe spec with any unresolved secret ref must be emitted in a **structurally non-runnable** form (e.g. the `runner` block gated behind a `status: unresolved` / `runnable: false` field the reference recipe MUST honor), not merely annotated with `# UNRESOLVED REQUIRED PARAM:`. Distinguish the notification path (declarative, human-reconciled) from the runner (executed). | An executable runner that ignores a comment marker can run a partial spec and publish a spurious/garbage `published_metric`, creating a real (not pending) metric that then binds falsely — a fabrication path NR-2 forbids. The comment-only discipline was sufficient for declarative Alertmanager config but not for an executed spec. | FR-P1-2 body; add an NR forbidding "a runnable spec with a dangling secret." | Unit test: emit a probe spec missing a required token; assert the emitted YAML carries `runnable: false` (or omits the `runner` block) AND the `# UNRESOLVED` marker; document that the reference recipe refuses to run when `runnable: false`. |
| R1-F6 | Interfaces | medium | Give FR-P3-1's pure core a **declared input contract** (a typed `SpanLite{trace_id, span_id, start_ns, end_ns, links:[{trace_id,span_id}]}` pair) rather than "the enqueue span and the linked span," and state units (ns vs s) + the sign convention `t(feed-visible) − t(created) ≥ 0`. Specify the error case: a missing/broken link returns a typed "unlinkable" result, not a negative or zero delta. | "given two linked spans, compute the delta" is untestable without a declared input shape and unit/sign convention. The Keiyaku "declare the contract before the boundary" discipline applies. Ambiguity here means the unit tests and the eventual Tempo-file adapter can drift on the shape. | FR-P3-1 body | Unit test the pure fn on synthetic `SpanLite` pairs: normal delta, zero-duration, missing-link (→ unlinkable), reversed timestamps (→ error, never negative). |
| R1-F7 | Validation | medium | Add a per-phase **Definition of Done** table separating unit-provable deliverables from external-subject deliverables: P1 = fully unit-provable ($0); P2-harness (verdict + promotion logic) = unit-provable, P2-live = external; P3-core = unit-provable, P3-validation = external. Mark each FR with its DoD tier. | §9 flags external rows and FR-P2-3/FR-P3-3 state honesty prose, but no single table lets a reviewer/CI see at a glance which FRs are "done" on merge vs "done pending an external run." This is the focus file's Ask 5 made checkable and prevents a future "P2 done" over-claim. | New §5 "Definition of Done" or extend §9 | Manual: each of the 10 FRs has a DoD tier ∈ {unit, external}; CI asserts only unit-tier FRs have tests gating merge. |
| R1-F8 | Data | low | Clarify FR-P2-2 promotion mechanics: which artifact does promotion WRITE, and does it reuse `generate_declared_probe_slos`'s recorded `query`/`target`? State that promotion emits a real `slos/{svc}-{name}.yaml` built from the pending_probes entry (single-sourced — no re-derivation), and that the now-published metric makes the SLI replay as `pass`/`bound_no_data` on the next `validate_promql` run (self-healing off the same query string). | FR-P2-2 says "eligible for promotion to `slos/`" but not that the SLO YAML is built from the already-recorded `query` (Mottainai: don't re-derive). Without this, promotion could re-synthesize a query that drifts from the P0-recorded one. | FR-P2-2 body | Unit test: promote a confirmed probe; assert the emitted `slos/` file's PromQL `==` the `query` string recorded in pending_probes. |

##### Adversarial stress-test

- **Empty-probe byte-identity (NR / FR-P1-4 "byte-identical when no probes"):** FR-P1-4 claims additive/byte-identical when no probes. But FR-P1-3 adds `probe-specs → probe_spec` to `_EXCLUDED_ARTIFACT_DIRS` unconditionally, and `scan_excluded_artifacts` (`validate_promql.py:282`) only reports a type when `base.is_dir()` and files exist — so with no probes there is no `probe-specs/` dir and `excluded_artifacts` is unchanged. This is safe, but the doc should assert it (the exclusion-DIR entry is always present in the map; the *report* is empty absent files). Covered implicitly; worth an explicit NR so a future reviewer doesn't "fix" it. (→ folded into R1-F2 audit note.)
- **Two services, same probe name:** `generate_declared_probe_slos` scopes the selector `{{service="{svc}"}}` (`:1737`) and the metric via `_probe_metric_name`. If two services declare `fanout_freshness`, the pending_probes entries differ by `service` but may share `published_metric` default `probe_fanout_freshness_seconds`. On promotion (F8) the two `slos/` files must not collide — verify `verdict_id`'s dir-qualified source key (`compare_live.py:238-250`) disambiguates them; if promotion writes `{svc}-{name}.yaml` this is fine. Flag as a promotion-collision test case (extends R1-F4/R1-F8).

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first review round (Appendix A/B/C empty prior to this block).
