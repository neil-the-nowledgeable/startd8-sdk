# Stakeholder Panel Implementation Plan

**Version:** 1.1 (Post-CRP — convergent review R1/R2 applied)
**Date:** 2026-07-01
**Tracks requirements:** `STAKEHOLDER_PANEL_REQUIREMENTS.md` v0.3
**Status:** Planned (pre-implementation)

---

## 0. Grounding: what the planning pass established

- **VIPP is merged to `origin/main`** (`src/startd8/vipp/`, head `951b0e96`); the old
  `feat/vipp-project-counterpart` branch is gone. Integrate against real code.
- **VIPP's `$0` invariant is structural.** Deterministic core = `evaluate.evaluate_envelope` +
  `compose.render_dispositions` (no LLM import). The *sole* paid surface is
  `compose.enhance_narrative`, invoked only at `assistant.py:138-144` behind
  `if narrative and agent is not None`, with cost flowing back as `report.cost_usd` /
  `report.llm_used`. **The panel must copy this pattern** — a second opt-in paid pass invoked
  *around* the deterministic core, never inside it.
- **FDE labels need no schema change.** `LabeledClaim.qualifier` and `.source` are free-text; the
  FR-21 label gate only checks the OBSERVED/MECHANISM/PREDICTION *prefix*. Synthetic answers →
  `label=OBSERVED, qualifier="synthetic", source="panel:<role_id>"`, rendered
  `"OBSERVED (project, synthetic)"`.
- **Roster is a plain kickoff YAML**, not a manifest-extraction grammar kind. Do not touch
  `manifest_extraction/`.
- **Persona primitive** = thin wrapper over `agenerate(prompt, system_prompt=…)` with manually
  threaded history. `AgenticSession` (tool loop + `ToolRegistry` + `supports_tool_use()` gate) is
  overkill. `acreate_response` drops `system_prompt` on one branch — avoid it.

---

## 1. Module layout

New package `src/startd8/stakeholder_panel/` (distinct from `vipp/` to keep VIPP's `$0` core clean):

| File | Responsibility | Requirements |
|------|----------------|--------------|
| `models.py` | `PersonaBrief`, `Roster`, `PanelQuestion`, `PanelAnswer` (frozen dataclasses, `to_dict`/`from_dict`, canonical JSON) | FR-2, FR-10 |
| `roster.py` | Load + validate `docs/kickoff/inputs/stakeholders.yaml` → `Roster`; `validate_roster()` | FR-1, FR-4 |
| `persona.py` | `Persona` — compiles brief → system prompt; `ask(question, history) -> PanelAnswer` via `agenerate(system_prompt=…)`; enforces in-character/defer bound | FR-5, FR-7 |
| `panel.py` | `StakeholderPanel` — instantiates one `Persona` per roster entry; holds live agents + per-persona transcript; `ask(role_id, q)`, `ask_all(q)`; session-scoped | FR-5, FR-6, FR-8 |
| `provenance.py` | Wrap a `PanelAnswer` into a `LabeledClaim(OBSERVED, qualifier="synthetic", source="panel:<role_id>")` | FR-10 |
| `transcript.py` | Persist Q&A to `.startd8/stakeholder-panel/<session>.json` (`0600`, gitignore'd); Mottainai re-read | FR-12 |
| `vipp_bridge.py` | The opt-in VIPP pass (see §3) | FR-9, FR-11 |
| `cli.py` (wire into `cli.py`) | `startd8 panel ask/list/session` commands | FR-8, FR-13 |

Persona identity is baked into the **agent instance** (system prompt set at creation), because
`arun_parallel_agents` sends one shared string with no per-call kwargs — for `ask_all` we write a
small panel-local fan-out (`asyncio.gather` over each persona's own `agenerate(system_prompt=…)`)
rather than reuse `arun_parallel_agents` verbatim.

**Concurrency, history, lifecycle (v1.1, R1-S2 → FR-20).** `panel.py` must serialize concurrent
`ask()` to the same persona (per-persona lock or atomic history append), **cap/summarize** threaded
history to bound token growth, and expose an explicit **session teardown** that releases live agents.
**Versioning pin (v1.1, R2-S3 → FR-12/FR-2).** The `StakeholderPanel` pins the roster revision it was
instantiated from (records a roster version + per-brief content hash); each `transcript.py` entry
carries that brief hash. A live session is **pinned** — an on-disk `stakeholders.yaml` edit mid-session
either emits a staleness warning or requires a new session (documented behavior, not silent drift).

## 2. Roster authoring surface (FR-1, FR-3, FR-4)

1. **Template** — add `src/startd8/concierge_templates/inputs/stakeholders.yaml` with 1–2 exemplar
   personas + inline authoring guidance.
2. **Projection** — add one tuple to `_KICKOFF_FILES` (`concierge/writes.py:38`):
   `("inputs/stakeholders.yaml", "docs/kickoff/inputs/stakeholders.yaml")`. The read-only download
   manifest derives from this list (`_TEMPLATE_GROUPS`), so no drift.
3. **Readiness** — add `"stakeholders"` to the assessment tuple in `_assess_kickoff_inputs`
   (`concierge/core.py:180`) so `assess`/`ReadinessView` reports present/absent/invalid. Roster
   structural validation (`roster.validate_roster`) is invoked here.

> ⚠️ Two independent hardcoded lists (`writes.py:38` projection, `core.py:180` assessment) — both
> must be edited or projection/readiness drift.

**Sequencing caveat (v1.1, R2-S5).** M0 projects `stakeholders.yaml` into every kickoff before the
consuming panel (M1) or VIPP fallback (M2) exists. To avoid a capability-expectation gap, the
template header states "live panel ships in a later increment," and `assess` distinguishes
**"roster authored"** from **"roster consumable."** So an early adopter authoring a roster after M0
is not misled into expecting live-panel behavior that is not yet built.

## 3. VIPP integration — the paid pass AROUND the core (FR-9, FR-11)

Mirror `enhance_narrative` exactly. Do **not** add the panel to `build_oracle`/`CompositeOracle`.

1. **Thread routing context into OMIT dispositions.** Small `evaluate.py` change: when `_evaluate_one`
   produces the `source="vipp:omit-default"` accept (`evaluate.py:152-159`), attach the unanswered
   `GroundTruthQuestion`s' `symbol` (value_path) + `claim` so a later pass can route them. (Alt:
   re-derive via `_build_questions` in the bridge — rejected: duplicates logic.)
   **Back-compat invariant (v1.1, R2-S1 → FR-9b):** the added fields are **strictly
   additive/optional** (absent/null when there is no OMIT); a new golden asserts existing
   `evaluate_envelope` output is unchanged except for the optional fields, with `$0`/no-LLM
   preserved (no LLM import reachable from `evaluate_envelope`).
2. **New opt-in pass.** Add `panel: StakeholderPanel | None = None` (and reuse the existing `agent`)
   to `run_vipp_negotiate` (`assistant.py:52`). After `evaluate_envelope` returns ($0), if
   `panel is not None`: for each disposition flagged `vipp:omit-default`, route its question(s) to
   the panel via `vipp_bridge`, collect `PanelAnswer`s, and attach them to the report as **synthetic
   advisory claims** (`LabeledClaim` per §provenance) — they do **not** mutate the disposition
   verdict.
   **Bounded fan-out (v1.1, R1-S1 → FR-17):** a configurable **max-questions cap** + **budget
   preflight** (reuse CostTracker/budget infra) gates the loop *before* spend; over the cap, OMITs
   are marked "deferred (budget)". The same guard applies to `panel ask-all` (§5).
   **Per-route failure handling (v1.1, R2-S2 → FR-16):** wrap each route so a persona
   error/timeout/refusal leaves that OMIT **unchanged** ("stakeholder unavailable"), never fabricates,
   never aborts siblings or the negotiate, and still cost-tracks partial spend.
3. **Ratification handoff (FR-11) — mechanized (v1.1, R1-S3 → FR-18).** The synthetic→ratified
   boundary is a **gate**, not prose: writing a synthetic claim into any ratified/load-bearing store
   is refused unless a **human ratification token** accompanies it, and the stored fact retains
   provenance carry-through (`panel:<role_id>` synthetic origin + originating brief hash). No
   auto-apply; the human ratifies via the CLI write path (human privilege).
   **Anti-anchoring report rendering (v1.1, R1-S5 → FR-19):** each synthetic answer renders with a
   persistent "synthetic, unratified" banner, the persona brief adjacent, and the **original OMIT
   question**, so the human ratifies against the gap, not against a persuasive fill. No synthetic
   claim renders as an unmarked fact.
4. **Cost** — the pass is cost-tracked; spend flows back on the report like `enhance_narrative`.

### 3.5 Observability task (v1.1, R1-S4 → FR-14)

Explicit instrumentation task (was implied only): emit an OTel **instantiation span** and a **child
query span per call** via `get_logger`/`otel.py`, with the required attributes (`role_id`,
`session_id`, model, token counts, `cost_usd`, provenance label; **status ERROR on persona failure**)
and the R1-F5 content constraint (**no raw Q&A/brief text** in attributes). Assigned to M1.

## 4. Persona semantics (FR-7)

- System prompt template: role, goals, constraints, known positions, and an explicit **defer rule**
  ("If asked outside your brief, say so; do not invent project facts.").
- Post-generation guard: a lightweight check that flags answers that assert facts clearly outside the
  brief's declared scope (advisory flag on the `PanelAnswer`, not a hard block in v1).

## 5. Surfaces (FR-8)

- **Primary: CLI.** `startd8 panel ask --role <id> "question"`, `panel ask-all "question"`,
  `panel list`. Paid, explicit, cost-reported. CLI is the only spend-authorized path.
- **NOT the Concierge read floor.** `handle_concierge_read`/`READ_ACTIONS` is contractually
  `$0`/no-LLM/deterministic; a live paid query cannot live there. (An MCP surface, if ever added, is
  a separate paid tool — deferred, see requirements NR/OQ.)

## 6. Test plan

- Unit: roster load/validate (valid, missing fields, dupe role_id, empty brief); persona defer
  behavior (mock agent); provenance labeling produces `OBSERVED (project, synthetic)` and passes the
  FR-21 gate; transcript round-trip.
- Integration: `run_vipp_negotiate(panel=…)` with a mock panel — assert (a) `$0` when `panel=None`
  (no LLM), (b) OMIT dispositions get synthetic advisory claims when panel provided, (c) verdicts
  unchanged, (d) cost tracked **and each CostTracker record carries `role_id`+`session_id`, summing
  to the report's panel `cost_usd`** (v1.1, R2-S4 → FR-13); (e) a persona failure/timeout leaves that
  OMIT unchanged ("unavailable"), siblings answer, pass completes (FR-16); (f) the per-pass cap
  bounds paid calls (FR-17).
- Telemetry (v1.1, R2-S4 → FR-14): assert an instantiation span with a child query span per call;
  required attributes present; **no raw Q&A/brief substrings** in attributes; span status ERROR on a
  persona failure.
- Back-compat golden (v1.1, R2-S1 → FR-9b): existing VIPP `evaluate_envelope` goldens still pass; new
  `symbol`/`claim` fields absent/null when no OMIT.
- Provenance goldens (v1.1): synthetic `LabeledClaim` round-trips `to_dict`→`from_dict` preserving
  `qualifier=="synthetic"` (R1-F6); a synthetic claim is refused by the ratified-write path without a
  ratification token (R1-F2/R1-S3); a transcript entry retains its originating brief hash after the
  brief is edited (R2-F3/R2-S3).
- Golden: `instantiate-kickoff` projects `stakeholders.yaml`; `assess` reports the new domain **and
  distinguishes authored vs consumable** (R2-S5).

## 7. Sequencing

- **M0** — `models.py` + `roster.py` + template + `instantiate-kickoff`/`assess` wiring (authoring
  surface, `$0`, no LLM). Ship-able alone. **Includes** the authored-vs-consumable `assess`
  distinction + template header caveat (R2-S5) so projecting the roster ahead of the consumer does
  not mislead.
- **M1** — `persona.py` + `panel.py` + `provenance.py` + `transcript.py` + `startd8 panel` CLI (live
  panel, standalone of VIPP). **Includes** FR-20 concurrency/history/teardown + FR-12 brief-hash/
  roster-pin (R1-S2/R2-S3), FR-14 span task (§3.5), FR-17 `ask-all` budget guard, and the FR-10
  serialization/ratified-write-gate provenance invariants (R1-F2/F6/R1-S3).
- **M2** — `evaluate.py` routing-context change (**strictly additive** + back-compat golden, R2-S1) +
  `vipp_bridge.py` + `run_vipp_negotiate(panel=…)` (VIPP OMIT fallback + ratification handoff).
  **Includes** FR-9c routing failure modes, FR-16 per-route failure handling, FR-17 per-pass cap,
  FR-18 mechanized ratification gate, FR-19 anti-anchoring report rendering.
- **M3** — persona defer-guard hardening (FR-7 in-scope-fabrication grounding signal); optional
  moderator/router (deferred per NR-3).

Each milestone is branch-first, tested, merged before the next.

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
| R1-S1 | Cost/quantity guard on FR-9 pass + `ask-all` (max-questions cap + budget preflight) | R1 | Applied → §3.2 bounded fan-out; FR-17; §6 (f) test | 2026-07-01 |
| R1-S2 | Session concurrency + history bound + teardown | R1 | Applied → §1 concurrency/lifecycle para; FR-20; M1 | 2026-07-01 |
| R1-S3 | Mechanized synthetic→ratified gate + provenance carry-through | R1 | Applied → §3.3 gate; FR-18; §6 provenance golden | 2026-07-01 |
| R1-S4 | Add FR-14 instrumentation task to the plan | R1 | Applied → new §3.5; M1; §6 telemetry test | 2026-07-01 |
| R1-S5 | Report anti-anchoring (banner + brief + original OMIT question) | R1 | Applied → §3.3 rendering; FR-19 | 2026-07-01 |
| R2-S1 | `evaluate.py` change strictly additive/optional + back-compat golden | R2 | Applied → §3.1 invariant; FR-9b; §6 golden | 2026-07-01 |
| R2-S2 | Per-persona route error/timeout handling | R2 | Applied → §3.2 failure handling; FR-16; §6 (e) | 2026-07-01 |
| R2-S3 | Roster/live-panel versioning (pin + drift behavior + brief hash) | R2 | Applied → §1 versioning pin; FR-12; M1 | 2026-07-01 |
| R2-S4 | Strengthen §6 to actually assert FR-13/FR-14 | R2 | Applied → §6 attribution + telemetry tests | 2026-07-01 |
| R2-S5 | Reconcile M0-ships-alone with template-before-consumer | R2 | Applied → §2 sequencing caveat; §7 M0; authored-vs-consumable assess | 2026-07-01 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All plan-side (S) suggestions from R1/R2 accepted. The only partial rejection is on the requirements side: R1-F6 forgery-prevention half (see requirements Appendix B). | 2026-07-01 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 02:15:00 UTC
- **Scope**: Cost-explosion vectors, session concurrency/lifecycle, synthetic→ratified provenance gate, OMIT-routing failure modes, telemetry coverage, and the anchoring-bias second-order risk of the ratification report.

**Executive summary (top risks / gaps):**

- **Unbounded paid fan-out (high):** §3.2 routes "question(s)" per OMIT disposition and §5 exposes `panel ask-all`; neither has a cost ceiling, max-question cap, or budget preflight. A many-OMIT negotiate pass or a large-roster `ask-all` is a cost-explosion vector inside a pass that is otherwise sold as "$0 unless opted in."
- **Session concurrency undefined (high):** §1 describes a session-scoped panel holding live agents + per-persona transcript with `asyncio.gather` fan-out, but concurrent `ask()`/`ask_all()` against a shared per-persona history is a data race, and history growth is unbounded (cost + context creep).
- **No mechanized synthetic→ratified boundary (high):** §3.3 hands ratification to "the normal VIPP/Concierge write path" with no assertion that a synthetic claim cannot be written as ratified without passing the handoff, and no provenance carry-through recording that a ratified fact originated as synthetic.
- **FR-14 instrumentation is untasked:** no plan section covers OTel/`get_logger` spans; it appears in the module table only implicitly.
- **Report anchoring bias:** rendering a confident synthetic answer in the same report a human uses to ratify can manufacture consent even though the verdict is unchanged.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Risks | high | Add a cost/quantity guard to the FR-9 pass and to `panel ask-all`: a per-pass max-questions cap and a budget preflight (reuse the SDK CostTracker/budget-preflight infra) that aborts or degrades before spend, with the cap configurable. §3.2 "for each disposition flagged vipp:omit-default, route its question(s)" is an unbounded loop; §5 `ask-all` fans out across the whole roster. | The panel's headline safety property is "$0 unless opted in," but once opted in there is no ceiling on how many paid calls one negotiate pass or one ask-all triggers. A large roster times many OMITs times threaded history is a real cost-explosion path. | §3.2 (add cap/preflight) and §5 (ask-all budget guard) | Integration test: N OMIT dispositions with cap=k → at most k paid calls, remainder marked "deferred (budget)"; ask-all over a large roster respects the cap. |
| R1-S2 | Architecture | high | Specify concurrency and history bounds for the session-scoped panel (§1 `panel.py`, fan-out paragraph): serialize concurrent `ask()` per persona (or make per-persona history append atomic), and cap/summarize threaded history to bound token growth. Define session teardown so live agents are released. | `ask_all` uses `asyncio.gather`; two concurrent questions to the same persona interleave writes to a shared per-persona transcript/history with undefined ordering, and FR-6's "thread prior turns into the prompt" grows unboundedly (cost + context-window creep). "Kept-available" implies a lifecycle that §1 never closes. | §1 (panel.py responsibility + fan-out note); cross-link §7 M1 | Concurrency test: parallel asks to one persona produce a consistent history; assert history token count is capped; assert session close releases agents. |
| R1-S3 | Security | high | Make the ratification boundary mechanized, not procedural. §3.3 should require (a) a gate that refuses to write a synthetic claim into any ratified/load-bearing store unless a human ratification token accompanies it, and (b) provenance carry-through so the ratified fact records it originated as `panel:<role_id>` synthetic input. | §3.3 says the human ratifies "via the normal VIPP/Concierge write path" — prose, not an enforced invariant. Nothing stops a synthetic claim from reaching a ratified store, and after ratification the synthetic origin is lost, defeating the audit trail FR-11/FR-12 promise. | §3.3 (add gate + provenance carry-through) | Test: writing a synthetic claim to the ratified path without a token is rejected; after ratification the stored fact retains a synthetic-origin provenance field. |
| R1-S4 | Ops | medium | Add an FR-14 instrumentation task to the plan. No section (§1–§7) describes emitting OTel spans / using `get_logger`; FR-14 is only implied. Add spans for panel instantiation and per-query calls, with the attribute-content constraint from requirements R1-F5 (no raw Q&A/brief text). | FR-14 is a stated requirement with no plan coverage — the Requirements Coverage Matrix below marks it Missing. Without an explicit task it will be skipped or bolted on inconsistently with SDK conventions. | New subsection (e.g. §3.5 or §4) + §7 milestone assignment | Golden/unit: assert spans emitted for instantiate + query; assert span attributes exclude raw Q&A text. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S5 | Risks | medium | Even though §3.2 guarantees the synthetic claim "does not mutate the disposition verdict," require the report to (a) render each synthetic answer with a persistent "synthetic, unratified" banner and the persona brief adjacent, and (b) always show the original OMIT question so the human ratifies against the gap, not against the persuasive fill. | The requirements framing "narrows the human's decision surface" inverts into "manufactures consent": a confident synthetic answer read in the ratification report anchors the human toward accepting it. Verdict-immutability protects the deterministic core but not the human decision that FR-11 routes to. | §3.3 (report rendering requirements) | Reader test / snapshot: the ratification section shows OMIT question + synthetic banner + brief for each synthetic claim; no synthetic claim renders as an unmarked fact. |

#### Review Round R2

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 22:05:00 UTC
- **Scope**: M0→M2 sequencing and FR-dependency satisfiability; backward-compat risk of mutating VIPP's deterministic `evaluate.py` core output; persona-failure/timeout degradation of the paid pass; roster/live-panel versioning drift; and closing the test-plan gaps for FR-13/FR-14. Deliberately avoids re-treading R1's cost cap (R1-S1), concurrency/history (R1-S2), ratification gate (R1-S3), the FR-14 instrumentation task (R1-S4), and report anchoring (R1-S5).

**Executive summary (top risks / gaps):**

- **`evaluate.py` change touches the `$0` core's output shape (high):** §3.1 attaches `symbol`+`claim` to OMIT dispositions produced by `_evaluate_one` — a schema change to the deterministic core that can break existing `evaluate_envelope` golden tests / VIPP consumers if the fields are not strictly additive/optional.
- **No persona-failure degradation path (high):** §3.2 "collect PanelAnswers" assumes every route succeeds; a persona error/timeout mid-pass has no defined behavior, risking a crash, a silently-dropped OMIT, or a fabricated fill.
- **Roster/live-panel drift (medium):** §1's session-scoped panel bakes briefs into agent instances at instantiation; editing `stakeholders.yaml` on disk mid-session leaves the live panel stale with no pin or detection, and transcripts record no brief revision.
- **Test plan under-asserts FR-13/FR-14 (medium):** §6 (d) asserts only "cost tracked," and no test covers FR-14 spans; both requirements are effectively untested.
- **M0 projects a template for a capability that ships in M1/M2 (medium):** `instantiate-kickoff` will emit `stakeholders.yaml` into every kickoff after M0, before any panel exists to consume it — a possible expectation mismatch.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | Treat the §3.1 `evaluate.py` change as a backward-compatible extension of the deterministic core's output: require the added `symbol`/`claim` on OMIT dispositions to be strictly additive/optional (absent/null when there is no OMIT), and add a golden asserting existing `evaluate_envelope` output is unchanged except for the new optional fields, with `$0`/no-LLM preserved. | §3.1 modifies `_evaluate_one` inside VIPP's `$0` core (`evaluate.py:152-159`). The plan calls it "small," but any shape change to a deterministic core's output can break golden tests and downstream consumers that parse dispositions. Additivity must be an explicit, tested invariant, not an assumption. | §3.1 (add additivity clause) + §6 (new golden) | Existing VIPP evaluate goldens still pass; new field absent/null when no OMIT; assert no LLM import reachable from `evaluate_envelope`. |
| R2-S2 | Risks | high | Wrap each per-persona route in the §3.2 pass with error/timeout handling: on any persona failure (exception, timeout, infra/rate-limit, refusal), that OMIT stays OMIT (marked "stakeholder unavailable"), the deterministic verdict is untouched, partial spend is still tracked, and one persona's failure never aborts sibling routes or `run_vipp_negotiate`. Implements requirements R2-F5. | §3.2 "route ... collect PanelAnswers" has no failure branch. Because this is the paid pass wrapped around a `$0` core, an unhandled error could crash the whole negotiate or (worse) leave a partial/fabricated report — defeating the "degrades to `$0` behavior when the panel can't answer" promise implied by FR-9. | §3.2 (add per-route failure handling) + §6 integration | Integration: a persona agent raising / timing out → pass completes, that OMIT unchanged with "unavailable" marker, siblings answer, successful-call cost tracked, verdict identical to the `$0` run for the failed OMIT. |
| R2-S3 | Ops | medium | Address roster/live-panel versioning: (a) pin a session's panel to the roster revision it was instantiated from (record a roster version / per-brief content hash on the `StakeholderPanel` and on each `transcript.py` entry), and (b) define behavior when `stakeholders.yaml` changes while a session is live — either detect and warn, or document that the session is pinned and a reload requires a new session. Implements requirements R2-F3 on the plan side. | §1 bakes each brief into an agent instance at creation and keeps it "session-scoped/kept-available"; a mid-session disk edit silently diverges the live panel from `stakeholders.yaml`, and transcripts record no brief revision, so a persisted answer cannot be traced to the brief that produced it. | §1 (panel.py + transcript.py responsibilities) + §7 M1 | Assert transcript entries carry a brief hash + roster version; assert a live session ignores on-disk edits (pinned) or emits a staleness warning; assert a reloaded session picks up the new revision. |
| R2-S4 | Validation | medium | Strengthen §6 so FR-13 and FR-14 are actually asserted: integration test (d) should assert the CostTracker record carries `role_id`+`session_id` (not merely "cost tracked"), and add a telemetry test asserting the FR-14 span tree + required attributes (per requirements R2-F1/R2-F2), including span status ERROR on a persona failure. | §6 (d) currently asserts only "cost tracked" and no §6 item covers FR-14 — the Coverage Matrix marks FR-13 Partial and FR-14 Missing. Adding the instrumentation task (R1-S4) without a test that verifies its shape leaves the requirements effectively unvalidated. | §6 (extend integration + add telemetry test) | The tests themselves: attribution-key assertions pass; span-tree + attribute + error-status assertions pass. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S5 | Architecture | medium | Reconcile the M0-ships-alone claim (§7) with the fact that M0's `instantiate-kickoff` projection (§2.1–2.2) emits `stakeholders.yaml` into every kickoff before the consuming panel (M1) or VIPP fallback (M2) exists. Either gate/label the projected template with inline guidance ("live panel ships in a later increment") or have `assess` distinguish "roster authored" from "roster consumable," so an early adopter authoring a roster after M0 is not misled into expecting live-panel behavior that is not built. | §7 says "M0 ... Ship-able alone," but shipping the authoring surface project-wide ahead of the consumer creates a capability-expectation gap: users see a stakeholder-roster template appear in their kickoff with no way to query it for two more milestones. | §7 M0 (add sequencing note) + §2.1 (template header guidance) | Template header documents consumer availability; a golden asserts `assess` copy distinguishes authored vs consumable, or the projection is feature-gated until M1. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: a cost/quantity guard is essential — my R2-S2 (failure degradation) and R2-S1 (core additivity) share the same "the paid pass must be bounded and safe" posture.
- R1-S3: the synthetic→ratified boundary must be mechanized with provenance carry-through — my R2-S3 (brief-hash carry-through) extends exactly that audit chain.
- R1-S4: FR-14 needs an explicit instrumentation task — my R2-S4 adds the test that would verify it, and requirements R2-F2 gives it a testable span contract.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to the plan section(s) that address it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (roster as kickoff input) | §2, §7 M0, §1 roster.py | Full | — |
| FR-2 (persona brief schema) | §1 models.py | Full | — |
| FR-3 (template scaffolding) | §2.1–2.2 | Full | — |
| FR-4 (roster validation) | §2.3, §6 golden | Full | — |
| FR-5 (panel instantiation) | §1 persona.py/panel.py, §7 M1 | Full | — |
| FR-6 (availability / session persistence) | §1 panel.py ("session-scoped") | Partial | No concurrency safety, history bound, or session teardown (see R1-S2) |
| FR-7 (in-character, brief-bounded) | §4 | Partial | Advisory scope flag only; in-scope fabrication uncaught (see R1-F3) |
| FR-8 (live query interface) | §1, §5 | Full | — |
| FR-9 (opt-in pass around core) | §3.2, §3.4, §6 integration | Partial | No cost ceiling on the per-OMIT fan-out (see R1-S1) |
| FR-9b (routing context on OMIT) | §3.1 | Partial | No-match / mis-route behavior undefined (see R1-F4) |
| FR-10 (synthetic provenance labeling) | §1 provenance.py, §3.2 | Partial | Qualifier not enforced downstream; serialization invariant unstated (see R1-F2, R1-F5, R1-F6) |
| FR-11 (ratification handoff) | §3.3 | Partial | No mechanized synthetic→ratified gate or provenance carry-through (see R1-S3, R1-S5) |
| FR-12 (transcript persistence) | §1 transcript.py | Partial | No redaction or retention/cleanup policy (see R1-F5) |
| FR-13 (cost tracking) | §3.4, §5 | Partial | Per-persona/per-session attribution mechanism unspecified; no budget guard (see R1-S1) |
| FR-14 (OTel instrumentation) | (none) | Missing | Plan has no instrumentation task; only implied by conventions (see R1-S4) |
| FR-15 (native agent abstraction) | §0, §1 | Partial | Requirement text itself is stale/contradictory (see R1-F1); plan uses the corrected primitives |

## Requirements Coverage Matrix — R2

Analysis only (not triage). Re-assessed after R2's focus areas (sequencing, core-output back-compat, persona failure, versioning, FR-13/FR-14 testability). Rows unchanged from R1 are marked "(as R1)"; deltas cite R2 IDs.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (roster as kickoff input) | §2, §7 M0, §1 roster.py | Full | (as R1) |
| FR-2 (persona brief schema) | §1 models.py | Partial | No brief-revision/content-hash binding for provenance over time (see R2-F3) |
| FR-3 (template scaffolding) | §2.1–2.2 | Full | (as R1) |
| FR-4 (roster validation) | §2.3, §6 golden | Full | (as R1) |
| FR-5 (panel instantiation) | §1 persona.py/panel.py, §7 M1 | Full | (as R1) |
| FR-6 (availability / session persistence) | §1 panel.py ("session-scoped") | Partial | Concurrency/history (R1-S2) plus roster/live-panel drift + session pinning (see R2-S3) |
| FR-7 (in-character, brief-bounded) | §4 | Partial | Advisory scope flag only (R1-F3); persona-failure ≠ fabrication not stated (see R2-F5) |
| FR-8 (live query interface) | §1, §5 | Full | (as R1) |
| FR-9 (opt-in pass around core) | §3.2, §3.4, §6 integration | Partial | Cost ceiling (R1-S1); no persona-failure degradation path (see R2-S2/R2-F5) |
| FR-9b (routing context on OMIT) | §3.1 | Partial | Mis-route behavior (R1-F4); core-output additivity/back-compat unverified (see R2-S1) |
| FR-10 (synthetic provenance labeling) | §1 provenance.py, §3.2 | Partial | Downstream enforcement + serialization (R1-F2/F6); brief-hash + answered-`symbol` on answer (see R2-F3/R2-F4) |
| FR-11 (ratification handoff) | §3.3 | Partial | Mechanized gate/carry-through (R1-S3/R1-S5); ratified fact should retain brief-hash (see R2-F3) |
| FR-12 (transcript persistence) | §1 transcript.py | Partial | Redaction/retention (R1-F5); no brief-revision recorded per entry (see R2-F3/R2-S3) |
| FR-13 (cost tracking) | §3.4, §5, §6(d) | Partial | Attribution key (`role_id`+`session_id`) unnamed → untestable (see R2-F1); test asserts only "cost tracked" (see R2-S4) |
| FR-14 (OTel instrumentation) | (none) | Missing | No instrumentation task (R1-S4) and no testable span contract/shape (see R2-F2/R2-S4) |
| FR-15 (native agent abstraction) | §0, §1 | Partial | Requirement text stale/contradictory (R1-F1); plan uses corrected primitives |
