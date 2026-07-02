# Stakeholder Panel Requirements

**Version:** 0.3 (Post-CRP — convergent review R1/R2 applied)
**Date:** 2026-07-01
**Status:** Draft
**Codename (proposed):** *Kaigi* (会議, "council/meeting") — the synthetic stakeholder panel. Descriptive name used throughout: **Stakeholder Panel**.

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass read the merged VIPP/Sapper/FDE/Concierge code and overturned several assumptions.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| VIPP is on an unmerged branch; may not be integrable yet | VIPP is **merged to `origin/main`** (`src/startd8/vipp/`); the feature branch is gone | Can integrate against real code now; OQ-2 reframed |
| The panel plugs in as a Sapper **fallback oracle** (`CompositeOracle`, first-non-OMIT-wins) | That would put **paid LLM inside VIPP's `$0` deterministic core** (`evaluate_envelope`), breaking the invariant | **FR-9 rewritten**: panel is an opt-in paid pass invoked *around* the core, mirroring `enhance_narrative` (`assistant.py:138`), gated by a panel arg |
| An OMIT disposition can be routed to a persona as-is | OMIT-default dispositions record only `proposal.id`/`kind` — **not the question text or value_path** | **New FR-9b**: thread the unanswered question's `symbol`/`claim` into the OMIT disposition so it can be routed |
| Synthetic answers might need a new claim label / schema change | `LabeledClaim.qualifier`+`source` are free-text; VIPP mints **only OBSERVED**; PREDICTION would be wrong | **FR-10 firmed**: `OBSERVED (project, synthetic)` via `qualifier="synthetic"`, `source="panel:<role_id>"` — **no schema change** |
| Roster is a kickoff input domain (possibly a grammar kind) | A grammar kind would enroll it in deterministic **app codegen + round-trip validation** — wrong | **FR-1 narrowed**: plain kickoff YAML read only by the panel; **do not touch `manifest_extraction/`** |
| `instantiate-kickoff` projection is template/config-driven | **Two independent hardcoded lists** — `_KICKOFF_FILES` (`writes.py:38`) and the assess tuple (`core.py:180`) | **FR-3/FR-4 firmed**: both lists + a template file must be edited |
| `AgenticSession` drives the personas | It requires `supports_tool_use()` + a `ToolRegistry` + a full tool loop — dead weight for Q&A; `arun_parallel_agents` passes no per-agent `system_prompt` | **FR-5/FR-8 narrowed**: thin wrapper over `agenerate(system_prompt=…)`; bake persona into the agent instance; panel-local fan-out |
| A read-only MCP/Concierge tool could host panel queries | Concierge read floor is contractually **`$0`/no-LLM/deterministic**; a live paid query violates it | **FR-8 + NR-7**: primary surface is a dedicated **CLI** command; MCP paid tool deferred |

**Resolved open questions:**
- **OQ-1 → Not a grammar kind.** Plain kickoff YAML the panel reads; `manifest_extraction/` untouched.
- **OQ-2 → A standalone `stakeholder_panel/` module** VIPP calls into via a bridge — kept out of VIPP's `$0` core.
- **OQ-3 → Panel is an explicit opt-in paid pass around the deterministic core** (mirrors `enhance_narrative`); VIPP stays `$0` when the panel is not supplied.
- **OQ-4 → Thin `agenerate(system_prompt=…)` wrapper**, not `AgenticSession`. Tool use not needed in v1.
- **OQ-5 → Distinctly-flagged OBSERVED** (`qualifier="synthetic"`), never PREDICTION. No schema change.
- **OQ-6 → Caller/bridge names the `role_id`** (routed from the OMIT question); a moderator/router is deferred (NR-3).
- **OQ-7 → CLI primary** (only spend-authorized path); read-only MCP tool is not an appropriate host for a paid query.

---

## 1. Problem Statement

During kickoff **preparation**, the project-side VIPP evaluates the SDK onboarding hosts' proposals
(Concierge / Welcome Mat / Red Carpet) against project ground truth, emitting per-proposal
dispositions (ACCEPT / REJECT / COUNTER). VIPP resolves questions against **Sapper's project
oracle** (`oracle_for_project → GroundTruthAnswer` = VALIDATED / REFUTED / **OMIT**) and the
manifest-extraction grammar's `ExtractionRecord`s.

The gap: when the oracle returns **OMIT** — a question the project's *artifacts* cannot answer —
today there is nothing to fall back on except a human. In a real onboarding, that human would walk
down the hall and ask the product owner, the compliance lead, or a representative end user. Those
people are not always available at kickoff-prep time, and the questions VIPP raises are often
answerable in principle from stakeholder *intent* that simply hasn't been written into the artifacts
yet.

This capability stands up a **panel of agents role-playing named project stakeholders**, each
bounded to a **human-authored persona brief**, kept **available** so VIPP (or Concierge `assess`)
can query them **live, on demand** at the moments it would otherwise stall on OMIT. The panel is a
*synthetic OBSERVED(project)-authority oracle* — a stand-in for absent stakeholders — never a
replacement for ratified project ground truth.

> **Authority framing (the load-bearing constraint).** Real project ground truth (Sapper, ratified
> artifacts) is the only source VIPP may treat as fact. Stakeholder-agent answers are **synthetic,
> unratified** input: they inform VIPP's questions and shape draft dispositions, but anything
> load-bearing must be surfaced for **human ratification** before it becomes a project fact. The
> panel *narrows* the human's decision surface; it does not *replace* the human.

| Component | Current State | Gap |
|-----------|--------------|-----|
| VIPP OMIT handling | OMIT → dead-ends at "ask a human" | No structured fallback oracle for unanswerable-from-artifacts questions |
| Stakeholder intent | Lives in people's heads until authored into YAML | No way to interrogate stakeholder intent before it's written down |
| Agent personas | `BaseAgent` has `name` only; `system_prompt` is a per-call kwarg | No persona/role construct, no "kept-available" session layer, no multi-agent panel loop (`arun_parallel_agents` is fan-out only) |
| Kickoff input domains | intro + 4 input-domain YAMLs projected by `instantiate-kickoff` | No stakeholder-roster domain; no place to declare who the stakeholders are |

---

## 2. Requirements

### A. Roster & Personas (authoring surface)

- **FR-1 — Stakeholder roster as a kickoff input domain.** The roster is declared in a versioned
  kickoff YAML (`docs/kickoff/inputs/stakeholders.yaml`), projected as a template by Concierge
  `instantiate-kickoff`. It is a plain kickoff input the **panel reads directly** — **not** a
  registered manifest-extraction grammar kind (a grammar kind would wrongly enroll it in
  deterministic app codegen + round-trip validation). `manifest_extraction/` is not touched. The
  roster is a project artifact under human authorship, not SDK-internal config.
- **FR-2 — Persona brief schema.** Each roster entry declares at minimum: a stable `role_id`, a
  human `display_name`, the stakeholder's `goals`, `constraints`, `known_positions`/opinions, and
  `out_of_scope` topics the persona should refuse. The brief is the **sole** substantive knowledge
  source for that persona (see FR-7).
- **FR-3 — Template scaffolding.** `instantiate-kickoff` projects a stakeholder roster template with
  1–2 exemplar personas (e.g. Product Owner, Representative End User) and inline authoring guidance,
  consistent with the other input domains. This requires adding a template file
  (`concierge_templates/inputs/stakeholders.yaml`) **and** a tuple to the projection list
  `_KICKOFF_FILES` (`concierge/writes.py:38`); the read-only download manifest derives from that
  list, so the two cannot drift.
- **FR-4 — Roster validation.** A roster is validated (unique `role_id`s, required fields present,
  no empty briefs) as part of `assess`/wireframe readiness — hooked into `_assess_kickoff_inputs` by
  adding `"stakeholders"` to its domain tuple (`concierge/core.py:180`, a **second** hardcoded list
  independent of FR-3's). An invalid roster is reported present/absent/**invalid**, not silently
  accepted.

### B. Panel lifecycle ("kept available")

- **FR-5 — Panel instantiation.** The SDK can instantiate a live Stakeholder Panel from a validated
  roster: one agent per persona, each created via `ProviderRegistry.create_agent(...)`. Personas use
  a **thin wrapper over `agenerate(prompt, system_prompt=…)`** with manually threaded history —
  **not** `AgenticSession` (which requires tool-use support + a `ToolRegistry` and is dead weight for
  bounded Q&A). The persona brief is baked into the agent **instance's** system prompt.
- **FR-6 — Availability / session persistence.** Instantiated personas remain queryable across
  multiple questions within a kickoff-prep session (multi-turn, per-persona conversational history
  retained by threading prior turns into the prompt), without re-instantiation per question. Panel
  identity is scoped to a `project_id` + kickoff-prep session.
- **FR-7 — In-character, brief-bounded answering.** A persona answers **in character**, bounded to
  its brief. When asked something its brief does not support, it must **defer/refuse**
  ("out of my area" / "not something I've decided") rather than improvise a fact. No persona may
  speak for another persona's domain. **(v0.3, from R1-F3)** The bound addresses not only
  *out-of-scope drift* but *in-scope fabrication*: a load-bearing answer must carry a
  **grounding/uncertainty signal**, and the FR-11 ratification view must render the persona's brief
  text **alongside** the answer so a human can check the answer against its declared source. Scope
  bounding alone does not catch a confident in-scope fabrication.

### C. VIPP integration (the consumer)

- **FR-8 — Live query interface.** A caller can pose a question to a specific persona (by `role_id`)
  or to the whole panel and receive structured answers on demand. Whole-panel queries use a
  **panel-local fan-out** (`asyncio.gather` over each persona's own `agenerate(system_prompt=…)`),
  not `orchestration.arun_parallel_agents` verbatim — that helper sends one shared string to every
  agent with no per-agent `system_prompt`, so persona identity must ride on the agent instance. The
  primary surface is a dedicated **CLI** command (`startd8 panel …`); see NR-7.
- **FR-9 — OMIT fallback: opt-in pass *around* VIPP's core.** The panel must **not** be injected as
  a Sapper fallback oracle (that would run paid LLM inside VIPP's `$0` `evaluate_envelope` core).
  Instead, mirroring `compose.enhance_narrative`: `run_vipp_negotiate` gains an opt-in
  `panel=…` argument; after the deterministic `evaluate_envelope` returns, if a panel is supplied,
  each disposition flagged `source="vipp:omit-default"` has its question routed to the relevant
  persona, and the answer is attached to the report as a **synthetic advisory claim**. It does
  **not** mutate the deterministic verdict. VIPP stays `$0` when no panel is supplied; the pass is
  cost-tracked when it is.
- **FR-9b — Routing context on OMIT dispositions.** OMIT-default dispositions currently record only
  `proposal.id`/`kind`, not the unanswered question. The evaluate step must thread the unanswered
  `GroundTruthQuestion`'s `symbol` (value_path) + `claim` onto the OMIT disposition so the FR-9 pass
  can route it to the correct persona. The threaded fields must be **strictly additive/optional**
  (absent/null when there is no OMIT) so VIPP's deterministic `evaluate_envelope` output stays
  back-compatible (**v0.3, from R2-S1**).
- **FR-9c — Routing failure modes (resolves OQ-9).** Routing must define both failure modes: (a) if
  **no persona matches** an OMIT question, the disposition **stays OMIT**, flagged
  "no stakeholder available" — it is never routed to a non-matching persona; (b) an **ambiguous
  match** resolves by a deterministic tie-break or an explicit multi-route, never an arbitrary pick.
  A mis-route would produce an authoritative-sounding answer that violates FR-7's
  "no persona speaks for another's domain." **(v0.3, from R1-F4)**
- **FR-10 — Synthetic provenance labeling.** Every panel answer is emitted as
  `LabeledClaim(label=OBSERVED, qualifier="synthetic", source="panel:<role_id>")` — rendering
  `"OBSERVED (project, synthetic)"`. This reuses existing free-text fields, needs **no `LabeledClaim`
  schema change**, and passes the FR-21 label gate (prefix check). **OBSERVED, not PREDICTION** —
  VIPP is architecturally constrained to mint OBSERVED(project) only.
  **(v0.3, from R1-F2) The synthetic marker must be load-bearing, not cosmetic:** because the FR-21
  gate checks only the label *prefix*, (a) any consumer making a load-bearing decision **must**
  inspect the synthetic qualifier (a typed flag preferred over free-text matching), not just the
  OBSERVED prefix; and (b) it is an **invariant** that a claim carrying the synthetic qualifier can
  never be written into a ratified store without first passing the FR-11 / FR-18 handoff. Prefix-only
  consumers are a laundering vector and must be enumerated and fixed.
  **(v0.3, from R1-F6, accepted-in-part)** The `qualifier`/`source` markers must **survive
  serialization round-trips byte-identically** — `from_dict` must not default a missing `qualifier`
  to empty (which would silently upgrade a reloaded synthetic claim to an unqualified fact).
  *(The reserved-`panel:`-prefix forgery-prevention half of R1-F6 is deferred — see Appendix B.)*
  **(v0.3, from R2-F4)** A `PanelAnswer` also carries the `value_path`/`symbol` it answers (the same
  field threaded onto the OMIT disposition per FR-9b), directly on the answer, so the deferred
  interactive-kickoff consumer (NR-6/OQ-8) can read per-field provenance without a VIPP disposition.
- **FR-11 — Ratification handoff.** Any panel answer that would become load-bearing (feed an ACCEPT
  disposition, fill a manifest `value_path`, alter a contract) is surfaced to the human for explicit
  ratification. Ratification is a human, at-human-privilege action — the panel never writes.

### D. Provenance, cost, observability

- **FR-12 — Transcript persistence (Mottainai).** Panel Q&A is persisted per session (question,
  answering persona, answer, provenance label, cost, timestamp) so it is auditable and re-readable
  without re-spending. Location follows the VIPP session-file convention
  (`.startd8/…`, `0600`, `.gitignore`'d). **(v0.3, from R1-F5)** Persisted transcripts define a
  **retention/cleanup policy** for `.startd8/stakeholder-panel/` (`0600`-at-rest is confidentiality,
  not lifecycle). **(v0.3, from R2-F3)** Each transcript entry records the **brief content hash +
  roster version** that produced the answer, so a persisted answer is traceable to the exact brief
  revision even after `stakeholders.yaml` is later edited.
- **FR-13 — Cost tracking.** Every panel query is a tracked LLM call via the SDK `CostTracker`.
  **(v0.3, from R2-F1)** Each cost record carries the persona `role_id` and the kickoff-prep
  `session_id` as **explicit attribution dimensions** (not merely "a cost was recorded"), and a
  per-session aggregate must reconcile to the report's total panel `cost_usd`.
- **FR-14 — OTel instrumentation.** Panel instantiation and queries emit OTel spans consistent with
  the SDK's logging/telemetry conventions (`get_logger`, `otel.py`). **(v0.3, from R2-F2)** The span
  contract is concrete and testable: one **instantiation span** (`project_id`, `session_id`, persona
  count) and a **child query span per call** (`role_id`, `session_id`, model, prompt/completion token
  counts, `cost_usd`, provenance label; **status ERROR on persona failure**). **(v0.3, from R1-F5)**
  Span attributes **exclude raw question/answer/brief text** (counts/IDs/costs only) — spans flow to
  Loki/Tempo where raw text would leak PII/secrets across the observability boundary.

### E. Framework

- **FR-15 — Native agent abstraction.** The panel is built on the SDK's native primitives —
  `BaseAgent` + `ProviderRegistry` + a **thin per-persona wrapper over `agenerate(prompt,
  system_prompt=…)`** with manually threaded history, and a **panel-local `asyncio.gather` fan-out**
  for whole-panel queries. It does **not** use `AgenticSession` (tool-use loop + `ToolRegistry` is
  dead weight for bounded Q&A, per FR-5) and does **not** reuse `orchestration.arun_parallel_agents`
  verbatim (it passes no per-agent `system_prompt`, per FR-8). **No LangChain** (see Decision D-1 and
  Non-Requirement NR-4). *(v0.3, from R1-F1: v0.2 text wrongly named the two rejected constructs —
  reconciled with §0/FR-5/FR-8.)*

### F. Safety & degradation (v0.3 — from CRP R1/R2)

- **FR-16 — Persona-failure degradation (from R2-F5/R2-S2).** A persona error, timeout,
  rate-limit/infra failure, or refusal during the FR-9 pass must leave the corresponding OMIT
  **unchanged** (stays OMIT, marked "stakeholder unavailable"), must **never fabricate** a fallback
  answer, must **never abort** sibling personas or `run_vipp_negotiate`, and any partial spend must
  still be cost-tracked (FR-13). The deterministic verdict for a failed OMIT is identical to the `$0`
  run.
- **FR-17 — Bounded paid fan-out (from R1-S1).** The FR-9 per-OMIT routing and the `panel ask-all`
  surface must enforce a **configurable max-questions cap** and a **budget preflight** (reusing the
  SDK CostTracker/budget infra) that aborts or degrades *before* spend. Beyond the cap, remaining
  OMITs are marked "deferred (budget)". "`$0` unless opted in" must not become "unbounded once
  opted in".
- **FR-18 — Mechanized ratification boundary (from R1-S3, strengthening FR-11).** The
  synthetic→ratified boundary is **enforced, not procedural**: a gate refuses to write a synthetic
  claim into any ratified/load-bearing store unless a **human ratification token** accompanies it,
  and after ratification the stored fact **retains provenance carry-through** (`panel:<role_id>`
  synthetic origin + originating brief hash per FR-12) so the audit trail survives.
- **FR-19 — Anti-anchoring in the ratification report (from R1-S5).** Even though a synthetic answer
  never mutates the verdict, the report must render each synthetic answer with a persistent
  "synthetic, unratified" banner, the persona brief adjacent (per FR-7), and the **original OMIT
  question** — so the human ratifies against the *gap*, not against a persuasive fill. Presenting a
  confident synthetic answer alone risks manufacturing consent.
- **FR-20 — Session concurrency & lifecycle (from R1-S2).** The session-scoped panel must
  **serialize concurrent `ask()` per persona** (or make per-persona history append atomic),
  **cap/summarize** threaded history to bound token growth, and define **session teardown** that
  releases live agents. "Kept-available" implies a lifecycle that must be closed.

---

## 3. Non-Requirements

- **NR-1 — Not a replacement for real stakeholders or ratified ground truth.** The panel is a
  synthetic stand-in for *absent* stakeholders during prep; it never overrides Sapper or a human.
- **NR-2 — No autonomous writes.** The panel answers questions; it does not apply changes, write
  manifests, or emit dispositions. Consistent with Concierge/VIPP "assist, not operate."
- **NR-3 — No cross-agent debate/negotiation in v1.** Personas answer questions independently
  (single-persona or parallel fan-out). A moderated multi-agent dialogue/debate loop is out of scope
  for v1 (candidate for a later phase).
- **NR-4 — LangChain not adopted.** The SDK already provides provider abstraction, cost tracking,
  OTel, and multi-agent fan-out; LangChain would duplicate these and add a heavy dependency with its
  own parallel agent model. Revisit only if native multi-agent orchestration proves insufficient
  (would require an ADR trigger).
- **NR-5 — No new provider or model work.** Uses existing providers/models; persona quality is a
  prompt/brief concern, not a model concern.
- **NR-6 — Not an interactive-kickoff UI feature (v1).** Filling `not_extracted`/`defaulted`
  `value_path` gaps conversationally in the interactive kickoff surface is a plausible *secondary*
  consumer but is out of scope for v1; VIPP is the primary consumer.
- **NR-7 — Not hosted on the Concierge/MCP read floor.** The Concierge read surface
  (`handle_concierge_read` / `READ_ACTIONS`) is contractually `$0` / no-LLM / deterministic; a live
  paid panel query cannot live there. A read-only MCP tool is `readOnlyHint`-defensible (no disk
  write) but is a *paid* surface and is deferred; the CLI is the v1 host (only spend-authorized path).

---

## 4. Decisions

- **D-1 — Native SDK primitives over LangChain.** Confirmed with the requester. Rationale in NR-4.
- **D-2 — Live oracle interaction model.** The panel is queried on demand at gap points, not
  pre-baked into a corpus. (Persistence per FR-12 gives a Mottainai re-read benefit without changing
  the interaction model to pre-baked.)
- **D-3 — Human-authored persona briefs are the knowledge source.** Personas do not derive facts
  from project artifacts autonomously; the brief bounds them. This keeps hallucination surface small
  and provenance honest.
- **D-4 — Roster is a kickoff input domain (project artifact), not standalone config.** Lives with
  the other kickoff YAMLs, projected by `instantiate-kickoff`, versioned with the project.

---

## 5. Open Questions

*(OQ-1 through OQ-7 resolved by the planning pass — see §0.)*

- **OQ-8 (deferred)** — How does the panel interact with the interactive kickoff experience's
  per-field provenance model? Design seam only; no v1 build (NR-6).
- **OQ-9 → Resolved (R1-F4 → FR-9c).** Roster carries an **explicit optional** persona↔domain
  mapping with a heuristic fallback; **no-match stays OMIT**, ambiguous-match uses a deterministic
  tie-break. Never an arbitrary route.
- **OQ-10 → Resolved (R1-F3 → FR-7 + FR-18/FR-19).** Prompt bounding is *not* sufficient alone:
  load-bearing answers carry a grounding signal, the ratification view shows the brief + original
  OMIT question, and the FR-18 gate stops any synthetic claim reaching a ratified store without a
  human token.

---

*v0.3 — Post-CRP convergent review (R1+R2, dual-document). Applied 11 requirements suggestions:
FR-15 corrected (R1-F1), FR-10 hardened (R1-F2/F6/R2-F4), FR-7 broadened to in-scope fabrication
(R1-F3), FR-9c added for routing failure modes (R1-F4), FR-12/FR-14 given redaction + span content
rules (R1-F5), FR-9b made additive (R2-S1), FR-13 given an attribution key (R2-F1), FR-14 given a
span contract (R2-F2), FR-12 given brief-hash provenance (R2-F3); new §F safety FRs FR-16..FR-20
(persona-failure, bounded fan-out, mechanized ratification gate, anti-anchoring, session lifecycle);
OQ-9/OQ-10 resolved. One suggestion accepted-in-part (R1-F6 forgery half deferred — Appendix B). Full
dispositions in Appendix A/B. Companion plan: `STAKEHOLDER_PANEL_PLAN.md` v1.1.*

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
| R1-F1 | Reconcile FR-15 with FR-5/FR-8/§0 (stop naming AgenticSession/arun_parallel_agents as primitives) | R1 | Applied → FR-15 rewritten to name the chosen primitives; noted as a v0.2 correction | 2026-07-01 |
| R1-F2 | Make the synthetic marker load-bearing (consumer must inspect qualifier; ratified-store invariant) | R1 | Applied → FR-10 consumer-obligation + invariant clauses; enforced by FR-18 gate | 2026-07-01 |
| R1-F3 | FR-7 must address in-scope fabrication, not only out-of-scope drift (grounding signal + brief in ratification view) | R1 | Applied → FR-7 broadened; resolves OQ-10 with FR-18/FR-19 | 2026-07-01 |
| R1-F4 | Define OMIT-routing failure modes (no-match stays OMIT; ambiguous tie-break) | R1 | Applied → new FR-9c; resolves OQ-9 | 2026-07-01 |
| R1-F5 | Redaction + retention (FR-12) + telemetry-content exclusion (FR-14) | R1 | Applied → FR-12 retention/cleanup, FR-14 span attrs exclude raw text | 2026-07-01 |
| R1-F6 (part) | Synthetic qualifier/source survive serialization byte-identically | R1 | Applied-in-part → FR-10 serialization invariant. Forgery half deferred (see B). | 2026-07-01 |
| R2-F1 | FR-13 attribution key (`role_id`+`session_id`) + session aggregate reconciliation | R2 | Applied → FR-13 attribution dimensions | 2026-07-01 |
| R2-F2 | FR-14 concrete testable span contract (instantiation + per-query child span, ERROR on failure) | R2 | Applied → FR-14 span contract | 2026-07-01 |
| R2-F3 | Bind PanelAnswer/transcript/claim to brief content hash + roster version | R2 | Applied → FR-12 per-entry brief hash; FR-18 carry-through | 2026-07-01 |
| R2-F4 | PanelAnswer carries answered `value_path`/`symbol` (forward-compat for NR-6 consumer) | R2 | Applied → FR-10 symbol-on-answer clause | 2026-07-01 |
| R2-F5 | Persona-failure requirement (stays OMIT, no fabricate, no abort, track partial spend) | R2 | Applied → new FR-16 | 2026-07-01 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-F6 (part) | Reserved-prefix forgery prevention (non-panel producers cannot set a `panel:` source) | R1 | Deferred, not v1. Per R2's disagreement: forging a `panel:` source requires another *trusted* SDK component to act maliciously — a broader trust-boundary concern this feature does not own. The serialization-survival half (the real laundering risk) is applied (Appendix A). Revisit if a cross-component provenance-integrity effort is scoped. | 2026-07-01 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 02:15:00 UTC
- **Scope**: (Feature Requirements) Provenance integrity of synthetic OBSERVED claims, persona hallucination bound, OMIT-routing correctness, secret/PII in transcripts + telemetry, and an internal consistency sweep vs the self-reflective §0 update.

**Executive summary (top risks / gaps):**

- **Laundering vector (critical):** FR-10 makes a synthetic claim distinguishable from a ratified fact *only* by a free-text `qualifier`, yet the FR-21 gate it cites checks the label **prefix** only. Any consumer that filters on `label==OBSERVED` and ignores `qualifier` treats synthetic input as ratified fact.
- **FR-15 is stale and self-contradictory:** it still names `AgenticSession` and `arun_parallel_agents` as the build primitives — the exact two constructs §0/FR-5/FR-8 explicitly reject. A reader trusting FR-15 builds the wrong thing.
- **FR-7 bounds *scope*, not *truthfulness*:** the advisory guard flags out-of-brief answers, but an in-scope confident fabrication is uncaught and can reach the FR-11 ratification handoff (OQ-10 is really asking about this).
- **Routing correctness (FR-9b/OQ-9) has undefined failure modes:** no-persona-match and wrong-domain-match behaviors are unspecified; a mis-route violates FR-7's "no persona speaks for another's domain."
- **Transcript + telemetry are a PII/secret surface:** FR-12 persists raw Q&A and FR-14 emits spans, with no redaction, retention, or span-attribute-content requirement.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | Reconcile FR-15 with FR-5/FR-8 and §0. FR-15 currently lists "AgenticSession (per-persona multi-turn) + arun_parallel_agents (whole-panel fan-out)" as the native primitives, but §0, FR-5, and FR-8 explicitly reject AgenticSession (dead weight, needs ToolRegistry) and reject reusing arun_parallel_agents verbatim (no per-agent system_prompt). Rewrite FR-15 to name the actually-chosen primitives (thin agenerate(system_prompt=…) wrapper + panel-local asyncio.gather fan-out). | An unrevised v0.1 requirement that names the two rejected constructs will mislead an implementer and directly contradicts the doc's own self-reflective update. This is a blocking internal inconsistency, not a nuance. | FR-15 (E. Framework) | Grep the requirements for "AgenticSession"/"arun_parallel_agents" and confirm every occurrence is in a *reject* context. |
| R1-F2 | Security | critical | Strengthen FR-10 to make the synthetic marker load-bearing, not cosmetic. Require that (a) any consumer making a load-bearing decision MUST inspect `qualifier=="synthetic"` (or a typed flag), not just the OBSERVED prefix; and (b) an invariant that a claim carrying the synthetic qualifier can never be written into a ratified store without first passing the FR-11 handoff. | FR-10 states the answer "passes the FR-21 label gate (prefix check)" — the very gate that ignores the qualifier. Distinguishability that no code is required to honor is not distinguishability; a synthetic OBSERVED claim can be laundered into a ratified fact. | FR-10 (add explicit consumer-obligation + invariant clauses) | Unit test: a synthetic LabeledClaim is rejected by the ratified-fact write path unless a ratification token is present; assert prefix-only consumers are enumerated and fixed. |
| R1-F3 | Risks | high | Tighten FR-7 to address in-scope fabrication, not only out-of-scope drift. Require that a load-bearing answer carry a grounding/uncertainty signal, and that the FR-11 ratification handoff present the persona brief alongside the answer so a human can check the answer against its declared source. | FR-7 says a persona must not "improvise a fact" when outside its brief, but the guard is scope-based; a persona can confidently assert a fabricated fact *within* its declared scope, which the advisory flag never catches. This is the substance of OQ-10 and D-3's "hallucination surface small" claim. | FR-7 (and cross-link to OQ-10, FR-11) | Test persona with a brief that omits a specific value; assert the answer either defers or is flagged low-grounding; assert ratification view renders the brief text. |
| R1-F4 | Interfaces | medium | Specify OMIT-routing failure modes for FR-9b/OQ-9: define behavior when (a) no persona matches the OMIT question and (b) the match is ambiguous. Mandate that unmatched OMITs remain OMIT (flagged "no stakeholder available") and are never routed to a non-matching persona. | FR-9b threads `symbol`/`claim` so the pass "can route it to the correct persona," but "correct" is undefined under heuristic matching (OQ-9). A silent drop loses the gap; a wrong-domain route produces an authoritative-sounding answer that violates FR-7. | FR-9b (add no-match / ambiguous-match clause); resolve OQ-9 | Test OMIT with no matching persona → disposition stays OMIT with a "no stakeholder" marker; test ambiguous match → deterministic tie-break or explicit multi-route, never arbitrary. |
| R1-F5 | Data | medium | Add a redaction + retention + telemetry-content requirement covering FR-12 and FR-14. Persona briefs and Q&A may contain sensitive stakeholder positions or project secrets; require that persisted transcripts define a retention/cleanup policy and that OTel spans (FR-14) exclude raw question/answer/brief text (attribute counts/IDs/costs only). | FR-12 relies on `0600`+gitignore (confidentiality at rest) but says nothing about span attributes; FR-14 spans flow to Loki/Tempo where raw Q&A/brief text would leak PII/secrets across the observability boundary. `0600` on disk does not protect telemetry. | FR-12 and FR-14 (add redaction/retention/span-content clauses) | Assert span attributes contain no raw Q&A/brief substrings (allow-list check); assert a documented retention/cleanup path exists for `.startd8/stakeholder-panel/`. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F6 | Security | medium | Require that the synthetic `qualifier`/`source` survive serialization round-trips byte-identically and that reserved `source` prefixes (e.g. `panel:`) cannot be forged onto a claim that bypassed the panel. The `models.py` `to_dict`/`from_dict`/canonical-JSON path (plan §1) is an unguarded place for the synthetic marker to be dropped or spoofed. | If `from_dict` defaults a missing `qualifier` to empty, a persisted-then-reloaded synthetic claim silently upgrades to an unqualified OBSERVED fact — the laundering vector of R1-F2 reached via persistence rather than the gate. Conversely, free-text `source` lets any producer mint `panel:*`. | FR-10 (add serialization-invariant + reserved-prefix clause) | Round-trip test: synthetic claim → to_dict → from_dict preserves `qualifier=="synthetic"`; assert non-panel producers cannot set a `panel:` source. |

#### Review Round R2

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 22:05:00 UTC
- **Scope**: (Feature Requirements) Testability of the observability/cost requirements (FR-13/FR-14) as written; provenance rot from roster/persona versioning over a long project; the deferred interactive-kickoff secondary consumer seam (NR-6/OQ-8) as a forward-compat constraint; and persona-agent failure/timeout as an unspecified requirement. Deliberately avoids re-treading R1's laundering (R1-F2/F6), FR-15 staleness (R1-F1), in-scope fabrication (R1-F3), OMIT-routing (R1-F4), and redaction (R1-F5).

**Executive summary (top risks / gaps):**

- **FR-13 is not testable as written:** "attributable per persona and per kickoff-prep session" names no attribution key (what dimension on the CostTracker record identifies persona + session), so "cost tracked" is the only assertable outcome.
- **FR-14 is not testable as written:** "emit OTel spans consistent with conventions" specifies no span tree, no required attributes, no error-status expectation — R1-F5 constrained span *content* but nothing constrains span *shape/existence*.
- **Provenance rot (high):** a persisted answer / ratified fact is bound to a `role_id` but not to the **brief revision** that produced it; over a long project the brief changes and the answer's grounding silently becomes stale. R1-F2/F6 bind `qualifier`/`source`, not brief version.
- **Deferred consumer may be blocked by a VIPP-shaped contract:** NR-6/OQ-8 defer the interactive-kickoff per-field consumer, but if `PanelAnswer`/provenance is designed only around VIPP now it may need rework later; a small forward-compat clause is cheap insurance.
- **Persona failure/timeout is unspecified:** no requirement states that a persona error/timeout leaves the OMIT unchanged, never fabricates, and never crashes the negotiate — the `$0` core is protected but the *paid* pass's degradation contract is absent.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Validation | medium | Make FR-13 testable by naming the attribution key. Require each panel query's `CostTracker` entry to carry the persona `role_id` and the kickoff-prep `session_id` as explicit dimensions, and require a per-session aggregate that reconciles to the report's total panel spend. Today FR-13 only says spend is "attributable per persona and per kickoff-prep session" with no field named. | Without a named attribution dimension, "attributable" is aspirational — the only assertable behavior is "a cost was recorded." An implementer cannot write a test that a specific persona's spend is isolable, and the plan §6 test (d) reflects this by asserting only "cost tracked." | FR-13 (add the `role_id`+`session_id` attribution-key clause) | Unit/integration: after N queries across M personas, assert CostTracker records carry `role_id`+`session_id`; assert sum over a session equals the report's panel `cost_usd`. |
| R2-F2 | Ops | medium | Give FR-14 a concrete, testable span contract: one span for panel instantiation (attrs: `project_id`, `session_id`, persona count) and a child span per query (attrs: `role_id`, `session_id`, model, prompt/completion token counts, `cost_usd`, provenance label; span status ERROR on persona failure). This is orthogonal to R1-F5 (which constrains span *content* — no raw text); this constrains span *shape/existence*. | "Emit OTel spans consistent with conventions" is unfalsifiable — an implementation emitting nothing, or a flat unparented span, both "comply." A named parent/child tree with required attributes is what lets a test assert instrumentation actually happened and errors are visible in Tempo. | FR-14 (add span-tree + required-attribute contract; cross-link R1-F5 for the content allow-list) | Assert an instantiation span with a child query span per call; assert required attrs present; assert a persona failure sets span status = ERROR. |
| R2-F3 | Data | high | Bind every `PanelAnswer` / transcript entry / synthetic `LabeledClaim` to a content hash of the persona brief (and a roster version) that produced it. A `role_id` alone does not pin *which revision* of the brief answered; over a long project the brief is edited and prior answers — and any fact ratified from them — lose traceable grounding. | FR-2 makes the brief the "sole substantive knowledge source" and D-3 rests hallucination-honesty on that binding, yet nothing records the brief revision. R1-F2/F6 protect the `qualifier`/`source` marker but not the *content* the answer was grounded in; a stale-brief answer is a distinct provenance-rot failure. | FR-2 / FR-10 / FR-12 (add brief-hash + roster-version provenance field) | Edit a brief → new answers carry the new hash; a pre-edit transcript entry retains the old hash; a ratified fact retains its originating brief hash for audit. |
| R2-F4 | Interfaces | medium | Add a forward-compat clause (scope trade-off, not a v1 build) so the deferred interactive-kickoff consumer (NR-6/OQ-8) is not blocked by a VIPP-only contract: require `PanelAnswer` to carry the `value_path`/`symbol` it answers (already threaded onto the OMIT disposition per FR-9b) directly on the answer, not only on the disposition. | NR-6 names interactive-kickoff a "plausible secondary consumer" whose need is per-field (`value_path`) provenance. If the v1 answer contract exposes the answered `symbol` only via VIPP's disposition, the deferred consumer must re-thread it — a rework the FR-9b data already makes free to avoid now. | FR-10 (or a new FR under §C) + note against NR-6/OQ-8 | Assert `PanelAnswer.symbol`/`value_path` is populated for routed answers; confirm a non-VIPP caller can read the answered field without a VIPP disposition. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F5 | Risks | high | Add an explicit persona-failure requirement: a persona error, timeout, rate-limit/infra failure, or refusal during the FR-9 pass must leave the corresponding OMIT **unchanged** (stays OMIT, marked "stakeholder unavailable"), must never fabricate a fallback answer, must never abort sibling personas or the negotiate pass, and any partial spend must still be cost-tracked (FR-13). | The requirements protect VIPP's `$0` deterministic verdict but never state how the *paid* pass degrades when an LLM call fails mid-pass. Absent this, an implementer may crash the negotiate, drop the OMIT silently, or (worst) synthesize a placeholder — all of which violate NR-1/FR-7. This is the requirement-level counterpart to plan suggestion R2-S2. | New FR under §C (or extend FR-9) | Integration: a persona agent raising / timing out → that OMIT unchanged with "unavailable" marker, other personas answer, pass completes, successful-call cost tracked. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F2: the synthetic marker must be load-bearing, not cosmetic — my R2-F3 (brief-version binding) presumes exactly this provenance-integrity posture.
- R1-F4: unmatched/ambiguous OMIT routing must stay OMIT — my R2-F5 and R2-S2 both assume "stays OMIT" is the safe default and would be incoherent without it.
- R1-F1: FR-15 naming the two rejected primitives is a blocking internal contradiction that must be reconciled before implementation reads it.

**Disagreements** (untriaged prior items I would weigh down, for triage):
- R1-F6 (partial): the *serialization-survival* half is essential (keep it), but the *reserved-prefix forgery* half ("non-panel producers cannot set a `panel:` source") is arguably out of scope for v1 — forging a `panel:` source requires another trusted SDK component to act maliciously, a broader trust-boundary concern than this feature owns. Consider splitting R1-F6 so the survival invariant lands now and forgery-prevention is deferred with a rationale, rather than gold-plating v1.
