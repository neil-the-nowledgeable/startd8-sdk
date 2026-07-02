# Stakeholder Panel Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
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
  speak for another persona's domain.

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
  can route it to the correct persona.
- **FR-10 — Synthetic provenance labeling.** Every panel answer is emitted as
  `LabeledClaim(label=OBSERVED, qualifier="synthetic", source="panel:<role_id>")` — rendering
  `"OBSERVED (project, synthetic)"`. This reuses existing free-text fields, needs **no `LabeledClaim`
  schema change**, and passes the FR-21 label gate (prefix check). **OBSERVED, not PREDICTION** —
  VIPP is architecturally constrained to mint OBSERVED(project) only. The qualifier makes a panel
  answer always distinguishable from a ratified fact.
- **FR-11 — Ratification handoff.** Any panel answer that would become load-bearing (feed an ACCEPT
  disposition, fill a manifest `value_path`, alter a contract) is surfaced to the human for explicit
  ratification. Ratification is a human, at-human-privilege action — the panel never writes.

### D. Provenance, cost, observability

- **FR-12 — Transcript persistence (Mottainai).** Panel Q&A is persisted per session (question,
  answering persona, answer, provenance label, cost, timestamp) so it is auditable and re-readable
  without re-spending. Location follows the VIPP session-file convention
  (`.startd8/…`, `0600`, `.gitignore`'d).
- **FR-13 — Cost tracking.** Every panel query is a tracked LLM call via the SDK `CostTracker`;
  panel spend is attributable per persona and per kickoff-prep session.
- **FR-14 — OTel instrumentation.** Panel instantiation and queries emit OTel spans consistent with
  the SDK's logging/telemetry conventions (`get_logger`, `otel.py`).

### E. Framework

- **FR-15 — Native agent abstraction.** The panel is built on the SDK's native primitives —
  `BaseAgent` + per-call `system_prompt` personas + `AgenticSession` (per-persona multi-turn) +
  `arun_parallel_agents` (whole-panel fan-out) + `ProviderRegistry`. **No LangChain** (see
  Decision D-1 and Non-Requirement NR-4).

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
- **OQ-9** — Should routing OMIT questions to a persona require an explicit persona↔proposal-kind
  mapping in the roster, or is a heuristic (match `q.symbol` entity/field against a persona's
  declared `goals`/scope) acceptable for v1? Leaning: explicit optional mapping, heuristic fallback.
- **OQ-10** — Persona answer bounding (FR-7) is prompt-enforced plus an advisory post-gen scope
  flag. Is that sufficient for v1, or does a load-bearing answer need a stricter refusal gate before
  it reaches the ratification handoff?

---

*v0.2 — Post-planning self-reflective update. 6 requirements narrowed/rewritten (FR-1, FR-5, FR-8,
FR-9, FR-10, plus FR-3/FR-4 firmed), 1 added (FR-9b), 1 non-requirement added (NR-7), 7 open
questions resolved, 3 residual/deferred. Consumers/integration points: VIPP
(`src/startd8/vipp/`, merged), Concierge (`src/startd8/concierge/`), Sapper oracle
(`sapper/ground_truth.py`), FDE claim labels (`fde/models.py`). Companion plan:
`STAKEHOLDER_PANEL_PLAN.md` v1.0.*
