# Observability (requirement-shaped / de-overfit) — Enhancement Backlog

**Scope:** the just-built grounding-free slice for the #226 de-overfit family — `UNGROUNDED_KINDS`
+ incidental-transport suppression + `fr_coverage.ungrounded_kinds` (PR #258), riding on the
already-shipped FR-6/FR-9/FR-12 machinery. **Register:** implementer. **Date:** 2026-07-22.

> Consumers to keep in frame: the observability generator runs at **cap-dev-pipe export stage**
> (not a direct CLI — see Grounding note), and its `observability-manifest.yaml` is a **cross-repo
> handoff** that **ContextCore** and **cap-dev-pipe** read. So "surface the coverage" has three
> audiences, not one: the human at the terminal, the cap-dev-pipe run summary, and ContextCore.

---

## Top findings (do first)

**None is a defect.** The one candidate that looked like a built-but-unwired defect —
`fr_coverage` reaching disk but nothing displaying it — **cleared out as by-design**: PLAN.md:49 /
risk R1-S7 scoped FR-9 to *"an `fr_coverage` block in the `_write_index` summary"* (the manifest),
never a human surface. So it's a latent **value path**, not a break. (Verification gate: confirmed
the negative by grep — `fr_coverage` is read nowhere in `src/` outside its own write; traced the
producer at `artifact_generator.py:566–589`; no test asserts a human/portal surface exists.)

### 1. Surface `fr_coverage` to its three audiences — the coverage data is on disk but invisible — **S**
`report.fr_coverage` (now four classes: `empty_services` / `unfulfilled` / `emitted` /
`ungrounded_kinds`) is written **only** to `observability-manifest.yaml`
(`artifact_generator.py:1233`). Confirmed unsurfaced: the portal builder has ten `_build_*(report)`
panel functions (`portal_spec_builder.py:341–517`) and **none reads `fr_coverage`**; the
`observability` CLI has no `generate` verb and its `--min-coverage` is a *different* metric
(PromQL binding, `cli.py`/`observability/cli.py:61`). So the entire point of FR-9 + #258 — *make the
deferral/gap visible* — currently means "grep a YAML." **Cheapest high-leverage move:** add
`_build_coverage_gap_panels(report)` (a text/table panel: N services observed by nothing; the
ungrounded-kind services + their next-step) and register it beside `_build_artifact_health_panels`
— the portal already renders report-derived panels, so the plumbing is there. → so an **author**
sees "your `mailer` worker is observed by nothing / your `ranker` is ungrounded — declare a
`freshness` FR" **in Grafana**, without opening the manifest. Ripple: the same `fr_coverage` block
already sits in the manifest for **cap-dev-pipe**'s run summary and **ContextCore** to read — a one-
line "coverage: 2 gaps" in the pipe's post-export summary closes the loop for the machine audience too.

### 2. Sharpen the ungrounded-kind hint from a generic list to a per-kind shape — **S**
`fr_coverage.ungrounded_kinds[].reason` (`artifact_generator.py:575–586`) tells **every** ungrounded
service the same generic string: *"declare … (run_success/freshness/saturation/lag)."* But the
fitting shape is **kind-specific** and already asserted in the issues: cron → `freshness`/`run_success`
(#233), batch → `run_success`/`freshness` (#230), ml_inference → `saturation`/`lag` (#231). Add a
`_KIND_SUGGESTED_SIGNALS = {"cron": (...), "batch": (...), "ml_inference": (...)}` beside
`UNGROUNDED_KINDS` (`metric_descriptor.py:205`) and interpolate the per-kind tuple into the reason.
This is **shape, not value** — it names *which SLI fits*, never a threshold magnitude — so it stays
inside the OQ-5 grounding gate. → so an author of a `cron` gets "declare a **freshness** FR"
(actionable) instead of a four-option menu they must triage.

---

## Prioritization (all findings, ranked)

The ordering *is* the recommendation. Two rules drive it: **wire cheap latent value before building
new** (Mottainai — the S items ship value now; the L flagship is fleet-gated), and **refine the
record before surfacing it** (do the data-shape fixes QW-2/LH-1 *before* the portal panel QW-1, so
the surface is good on day one instead of showing a hint you immediately re-polish).

| Rank | Finding | Effort | Value / audience | Gating / dependency | Do when |
|------|---------|--------|------------------|---------------------|---------|
| ✅ **P1a** | QW-2 per-kind signal hint | S | author — sharper, actionable guidance | none | **Delivered (PR #263)** |
| ✅ **P1b** | LH-1 `empty_services ⊇ ungrounded` cross-ref | S | author — one story, not two gaps | none | **Delivered (PR #263)** |
| ✅ **P1c** | QW-1 portal coverage-gap panel | S | human/author — invisible → visible in Grafana | *displays* P1a/P1b output | **Delivered (PR #263)** |
| **P2** | QW-3 cap-dev-pipe / ContextCore coverage line | S–M | machine / cross-repo ripple | **hypothesis** — confirm the consumer reads `fr_coverage` first | fast-follow, after a short cross-repo spike |
| ✅ **P3** | AQW-1 kind-vocab drift guard | S | dev — prevents a silent future regression | independent | **Delivered (PR #263)** |
| **P4** | EC-1 OQ-5 grounding pilot | L | **highest ultimate** — closes #230/#231/#233 | **gated** on a real worker/batch/ML fleet + grounded values | a scheduled milestone, not a backlog quick-win |

> **Delivered increment (PR #263):** P1a+P1b+P1c+P3. `fr_coverage.ungrounded_kinds[]` now carries
> `suggested_signals` (kind-specific shape) + `observed_by_nothing` (∅ cross-reference); a self-gating
> **Coverage Gaps** portal panel surfaces all three gap classes for operator/engineer personas; and a
> drift test asserts the SDK's kind sets partition `CANONICAL_SERVICE_KINDS`. Remaining: **P2** (needs
> the cross-repo consumer spike) and **P4** (the grounding pilot).

**Why this order, not "highest value first":** EC-1 has the biggest payoff (it closes three issues)
but it is **blocked** — it needs a real fleet and grounded threshold values that don't exist yet, so
it can't lead. The **P1 bundle** (three S items, no deps) is the leverage available *today*: it makes
the slice we just shipped actually legible to an author, and it makes EC-1's eventual output legible
too. P2 rests on an unverified cross-repo assumption — **spike the confirmation before building it**,
or it risks being effort spent on a surface no consumer reads. P3 is cheap insurance with no urgency.

**Suggested first increment:** P1a → P1b → P1c as one PR (all touch `artifact_generator.py` +
`metric_descriptor.py` + `portal_spec_builder.py`; ~S total), landing "worker/batch/cron/ML coverage
gaps are visible and per-kind-actionable" end-to-end.

---

## Grounding note (belief → actual — where going-and-seeing changed the answer)

| Belief going in | Actual (grounded) | Effect |
|---|---|---|
| "`fr_coverage` unsurfaced = a built-but-unwired **defect**, lead with it" | PLAN.md:49 / R1-S7 scoped FR-9 to the **manifest summary** by design; the write is correct + tested | Demoted from P0-defect to a latent **value path** (Top finding 1) — avoided a false headline |
| "There's a `startd8 observability generate` command that could print the gaps" | No `generate` verb exists; the generator runs at **cap-dev-pipe export stage**; the CLI's `--min-coverage` is PromQL-binding, unrelated | Reframed the surface from "add a CLI print" to "portal panel + pipe run-summary + ContextCore" |
| "The ungrounded `reason` already guides per kind" | It's **one generic string** for all kinds (`artifact_generator.py:581`) though the per-kind shapes are known | Became Top finding 2 (per-kind hint) |

---

## Backlog appendix (draw from over later increments)

<details>
<summary>Full bucketed backlog</summary>

### ⚡ Quick wins
- **QW-1 — Portal coverage-gap panel** — Top finding 1. `_build_coverage_gap_panels(report)` reading
  `report.fr_coverage`, registered in the persona panel assembly. **S.**
- **QW-2 — Per-kind suggested-signal hint** — Top finding 2. **S.**
- **QW-3 — cap-dev-pipe post-export coverage one-liner** — the export stage already produces the
  manifest; emit a `coverage: N observed-by-nothing, M ungrounded` line in the run summary read from
  the manifest's `fr_coverage`. *Hypothesis (cross-repo): confirm cap-dev-pipe's export summary hook
  before sizing.* **S–M.**

### 🌱 Low-hanging fruit
- **LH-1 — `empty_services` ⊇ `ungrounded_kinds` cross-reference** — a service is often in **both**
  lists (an `ml_inference`+http service with no FRs is ∅-SLI *and* ungrounded). Today they read as
  two unrelated gaps. Tag the `empty_services` entry with `ungrounded: true` (or have the surface in
  QW-1 join them) so the author sees one story — "observed by nothing **because** its kind is
  ungrounded" — not two. Grounded: both appended in the same loop, `artifact_generator.py:568–586`. **S.**

### 🏗️ Architectural quick win (max one — the rest is a `/complexity-distiller` hand-off)
- **AQW-1 — Single-source the service-kind vocabulary (drift seam)** — `REQUEST_KINDS`,
  `_KIND_DEFAULTS`, `_KIND_SLI_DEFAULTS`, and `UNGROUNDED_KINDS` are four independent literals in
  `metric_descriptor.py:185–211`, and the canonical `ServiceKind` enum lives cross-repo in
  ContextCore (`contracts/types.py`, per `DE_OVERFIT_FAMILY_THRESHOLD_SEAM.md`). If ContextCore adds
  a kind (e.g. a new worker type), **none of the four learns it** — a new kind falls silently to the
  transport default. Cheap guard: a single test asserting `UNGROUNDED_KINDS ∪ grounded-kinds ∪
  REQUEST_KINDS == the ContextCore ServiceKind enum` (minus `unknown`), so drift fails loudly. This
  is a **drift-seam** smell (`/complexity-distiller` territory) — hand off the deeper single-source
  consolidation there; take only the parity guard here. **S.**

### 🚀 Enhanced capabilities
- **EC-1 (flagship) — the OQ-5 grounding pilot: fill FR-7 values + graduate a kind out of
  `UNGROUNDED_KINDS`** — OQ-5 is *resolved as located/verified* (REQUIREMENTS.md:33) but the
  per-`signal_kind` threshold **values** and grounded metric **series** for batch/cron/ml_inference
  are still deliberately deferred. The capstone that closes **#230/#231/#233**: run a real
  worker/batch/cron/ML fleet, ground the `criticality × signal_kind` threshold cells, then move a
  kind from `UNGROUNDED_KINDS` into `_KIND_DEFAULTS`/`_KIND_SLI_DEFAULTS` (+ a profile row). The slice
  we just shipped is *designed* to make this a clean forward-`/reflective-requirements` step: "move a
  kind out of the registry and fill its cell." Needs a real fleet + grounded values — not a
  this-week item. RETROSPECTIVE.md:128 names it the next concrete step. **L.**

### 🔭 Operational / legibility
- (Folded into QW-1/QW-3 — surfacing `fr_coverage` *is* the observability move for this slice.)

</details>

---

## Honest gaps (product decisions surfaced while grounding — not bugs)

- **The deferral is deliberate, and that's correct.** batch/cron/ml_inference producing **no**
  default SLOs is the designed behavior (`metric_descriptor.py:190` "intentionally absent until
  grounded") — the fix is *visibility* (QW-1/QW-2), never fabricating values. Don't let a future
  reader "complete" the table by inventing thresholds; that reopens the exact overfit #226 condemns.
- **`fr_coverage` living only in the manifest is a valid machine-first choice.** For the cross-repo
  audience (cap-dev-pipe / ContextCore) the manifest *is* the right surface. The gap is purely the
  **human** surface (portal/pipe-summary). Confirm both machine consumers actually read the block
  before investing in a richer schema — QW-3 is a hypothesis until that's checked.
- **`signal_kind` enum orthogonality is an open design question, not a task** — crp-focus-R1.md:20
  flags "is `retry_rate` a special case of `run_success`? is `lag` vs `freshness` real?" Left as a
  spec question for the grounding pilot (EC-1) to settle with evidence, not to guess now.
