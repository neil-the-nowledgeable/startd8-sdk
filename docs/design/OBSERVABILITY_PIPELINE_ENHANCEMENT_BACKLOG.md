# Observability Pipeline (OPI + AI-agent) — Enhancement Backlog

**Scope:** the just-built observability producer→consumer loop — OPI-150/200/600 enrichment + the
OPI-300 contractor-prompt consumption (#268, PR #271), riding on the AI-agent signal_kind generator
(#270). **Register:** implementer. **Date:** 2026-07-22.

---

## Top findings (do first)

**No defect leads.** The one candidate that looked like a built-but-unwired break — the
`observability_contract` reaching the contractor prompt — **cleared the verification gate**: the
`ContextSeed` model has *no* `observability_contract` field (`seeds/models.py:60` has only
`security_contract`), which *would* drop it on a round-trip — but the emitter bolts it onto
`seed_dict` **after** `to_dict()` (`plan_ingestion_emitter.py:1283`) and `prime_contractor`
consumes the **raw seed JSON** (`load_seed_context`, `prime_contractor.py:1627` — "Raw seed JSON
dictionary"), so it survives end-to-end. Confirmed the wire both ends; R2 works. (That trace *did*
surface a real fragility — see AQW-1 below.)

### 1. OPI-300 V2 — split the prompt section so metric names + SDK packages survive budget pressure — **S**
`_build_observability_guidance_section` emits the whole contract as **one P2 block**
(`spec_builder.py`; `prioritized.append((2, "observability_guidance", ...))`). Under budget
pressure the budget enforcer trims it **as a unit** — dropping the *metric names and SDK packages*
along with the thresholds. But those two are the **load-bearing** part: they're exactly what stops
the wrong-import bug class (a service importing a generic OTel package instead of
`opentelemetry-instrumentation-grpc`). The authoritative spec already defines the fix
(cap-dev-pipe `REQ_OBSERVABILITY_PIPELINE_INTEGRATION.md:114`, "V2 path"): a **P1 compact
subsection** (metric names + packages, ~100 tokens, never trimmed) + a **P2 detail subsection**
(thresholds/SLO targets, trimmable). The section builder already separates these fields — splitting
one append into two prioritized appends is a small refactor. → so a **token-pressured task still
gets the exact metric names + import packages**, instead of silently falling back to generic
instrumentation the moment the prompt is full. **Sharpest move** on the board.

### 2. Make `observability_contract` a first-class `ContextSeed` field — **S** (🏗️ drift seam)
Today it survives *only* because it's appended to `seed_dict` after `to_dict()` and read back as a
raw dict — a **bolt-on**, not a modeled field. `security_contract` is a real `ContextSeed` field
(`seeds/models.py:60`, in the `to_dict` key-list `:73`); `observability_contract` is not. The
moment anything round-trips the seed through `ContextSeed` (a re-serialize, a validator, a future
loader), the contract is **silently dropped** and OPI-300 goes dark with no error. Add
`observability_contract: Optional[Dict] = None` to `ContextSeed` + its `to_dict` list, mirroring
`security_contract` exactly, and drop the post-`to_dict` bolt-on. → so the **producer→consumer wire
can't be silently severed by a future refactor** — the same guarantee `security_contract` already
has. Cheap now; prevents a silent-dark regression later.

---

## Grounding note (belief → actual — where going-and-seeing changed the answer)

| Belief going in | Actual (grounded) | Effect |
|---|---|---|
| "`observability_contract` may never reach the prompt — a defect" | It DOES: bolted on post-`to_dict` (`emitter:1283`) + read as raw JSON (`prime_contractor:1627`). Wire complete both ends. | Demoted from P0-defect to a **fragility** (Top finding 2) — avoided a false headline |
| "OPI-300 reads the per-task `convention_metrics` first" | That branch is **dead**: only `spec_builder` reads it (`:746`); nothing in `contractors/` writes `gen_context["convention_metrics"]`; `resolve_task_context` threads only `service_name` (`context_resolution.py:902`). The section always uses the **contract fallback**. | It works (fallback), but the primary branch is dead code → an honest cleanup (hand to `/complexity-distiller`), not a value item |
| "The section surfaces the richer per-task fields (slo_targets)" | The section reads only fields the **contract** also carries (metrics/transport/sdk_packages/alert_thresholds); `slo_targets` is enriched onto the task but never read. | Reviving the dead branch would surface nothing new *unless* the section is taught `slo_targets` — noted, not sold as a quick win |

---

## Backlog appendix (draw from over later increments)

<details>
<summary>Full bucketed backlog</summary>

### ⚡ Quick wins
- **QW-1 — OPI-300 V2 P1/P2 split** — Top finding 1. **S.**
- **QW-2 — Delete or feed the dead `convention_metrics` branch** — the OPI-300 primary branch never
  fires (contract fallback always used). Either simplify to contract-only, or thread the per-task
  enriched context into `gen_context` (mirror `service_name` threading at `context_resolution.py:902`)
  AND teach the section `slo_targets` so the per-task richness actually reaches the prompt. Pure
  cleanup ⇒ `/complexity-distiller` lane; the "thread + surface slo_targets" variant is a real 🌱. **XS–S.**

### 🌱 Low-hanging fruit
- **LH-1 — AI-agent `llm_error_rate` (spec OQ-4)** — `startd8_requests_total` carries a `status`
  label (`session_tracking.py:64`); an error-rate ratio SLI is derivable *today* without an
  emission-side change. Add the `llm_error_rate` row to `_FUNCTIONAL_SLI_TEMPLATES` (ratio shape) +
  `_PROJECT_SCOPED_SIGNAL_KINDS`. Gated only on confirming the `status` value vocabulary. **S.**

### 🏗️ Architectural quick win (one — rides the single-source the build just introduced)
- **AQW-1 — First-class `observability_contract` on `ContextSeed`** — Top finding 2. **S.**

### 🚀 Enhanced capabilities
- **EC-1 — OPI-400: drive TODO-completion instrumentation from the contract** — TODO completion
  exists (`prime_contractor.py:742` `enable_todo_completion`) but does not consume the observability
  contract, so instrumentation-mode TODOs get generic guidance. Wire the contract into
  `run_todo_completion` so *existing* services get the exact metrics/packages too — not just
  newly-generated ones. *Cross-repo (cap-dev-pipe passes `--observability-manifest`); confirm the
  SDK-side `run_todo_completion` entry before sizing.* **M.**
- **EC-2 — AI-agent project-scope de-dup (spec OQ-2)** — a project-wide AI cost/context FR (no
  `service`) matches every service in `generate_functional_slos` (per-service loop), emitting **N
  identical SLOs**. Emit a project-scoped AI SLO **once** (a synthetic project service id, or dedupe
  in the caller). Grounded: the AI series are `model`/`project`-labeled, not per-service. **M.**

### 🔭 Operational / legibility
- **OL-1 — AI-agent SLOs in `fr_coverage`** — confirm a declared AI FR whose series is live shows
  `emitted`, and an `llm_error_rate`/`refusal_rate` FR with no series shows `unfulfilled` with the
  actionable reason (spec FR-4). Largely automatic via the existing functional-SLO coverage path;
  add a fixture-backed assertion so it's legible, not assumed. **XS.**

</details>

---

## Honest gaps (product decisions surfaced while grounding — not bugs)

- **AI-agent threshold VALUES are deferred by design (spec OQ-1), not missing.** The series are
  grounded (live-verified); the magnitudes (breaching $/call, paging context-saturation) need real
  agent-run distributions. Ship the shape, fill values from a grounded pilot — never invent them
  (the #226 overfit). Don't let a future reader "complete" the importance table with guessed cells.
- **batch/cron/ml_inference remain series-un-grounded (OQ-5)** — no local fleet emits their series
  (`kafka_consumer_*` exists; `job_*`/GPU do not). That's *find the subject or defer*, not a bug in
  this build.
- **`refusal_rate` needs an emission-side label** — out of scope for the generator; owned by
  `OBSERVABILITY_AI_AGENT_REQUIREMENTS.md` (REQ-AAO-009). `llm_error_rate` (LH-1) is the derivable
  substitute meanwhile.
