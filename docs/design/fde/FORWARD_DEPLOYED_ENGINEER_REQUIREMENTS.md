# Forward Deployed Engineer (FDE) Requirements

**Version:** 0.3.1 (adds FR-28 latest-run resolution)
**Date:** 2026-06-04
**Status:** Draft
**Owner:** neil-the-nowledgeable

> **v0.3 triage summary.** Convergent Review produced 5 rounds (R1 opus + R2–R5 sonnet) totalling
> ~35 F-suggestions (requirements) and ~31 S-suggestions (plan), all code-anchored. **Disposition:
> ACCEPT all material suggestions; 1 duplicate round deduped; 0 rejected on merit** — the reviews
> were anchored, code-verified, and non-overlapping with settled decisions, so a near-total accept
> is the correct outcome (not a rubber-stamp — see Appendix A for per-ID where-merged and Appendix B
> for the dedup). Accepted changes are consolidated into new requirements **FR-18…FR-26** (§3.G) plus
> in-place fixes to the §6 table (the R2-F2 `generation_strategy` correctness defect), FR-5/FR-16
> (R2-F1 explain-vs-preflight tier-rationale split), and FR-8 (R4 greenfield-signal guard). One
> correctness defect was caught and fixed. CRP earned its pass.

---

## Locked design decisions (pre-draft)

These were decided before drafting and frame every requirement below:

1. **Form — Hybrid.** The FDE's *brain* (mechanism-authority logic) is a first-class SDK
   component (a class + `startd8 fde` CLI surface). Its *posting* (project-local context
   bundle + the `fde-*.md` communication protocol) lives in the project under
   `.startd8/fde/`. The SDK side is versioned/testable/home-authoritative; the project side
   is the deployed footprint the Service Assistant writes to and the FDE answers in.
2. **Authority role — SDK mechanism authority.** Per
   [Tekizai-Tekisho](../../design-princples/TEKIZAI_TEKISHO_DESIGN_PRINCIPLE.md), the FDE
   supplies the **MECHANISM** half of a cross-boundary composition (how the SDK actually
   decides). The **Service Assistant** supplies the project **EVIDENCE** half (what happened
   on disk). FDE output is a *composed* report, never a solo cross-boundary verdict.
3. **Preflight — reuse + SDK-mechanism lens.** Landmine-spotting in plans/requirements builds
   on existing review machinery (`domain-preflight` workflow, plan-ingestion, the semantic
   compliance reviewer, CRP). The FDE adds only its unique lens: *"does this plan/requirement
   assume SDK behavior that isn't how the SDK actually decides?"*
4. **Sync roadmap — A2A typed contract (Keiyaku).** v1 communication is `fde-*.md` files. The
   eventual synchronous channel is an A2A typed contract. The `.md` protocol is designed as
   the serialized form of whatever the A2A contract will later carry. *(Refined post-planning —
   see §0 / FR-12: there is **no A2A transport in the SDK today**, so the decision is realized as
   a **Keiyaku-contract-shaped, transport-agnostic** protocol; A2A is a roadmap dependency, not a
   v1 wiring target.)*

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> The planning pass mapped each requirement to real SDK seams (three parallel codebase
> sweeps) and revealed **6 material corrections** — enough to confirm the v0.1 draft carried
> the usual share of wrong assumptions, which is the loop working as intended. The single
> most important discovery is itself a Tekizai-Tekisho lesson: **the draft named the wrong
> source-of-truth artifact for "did micro-prime run," and verifying the real one is a
> home-authority step the requirements must not skip.**

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-5: the FDE reads `prime-result*.json` as the authoritative source for micro-prime/tier/repair mechanism. | **No file in `src/` writes `prime-result*.json`** — only Service Assistant (`detector.py`/`triage.py`) and `cli_assist.py` *read* it; it's produced upstream (workflow runner / out-of-repo wrapper). The fields the FDE actually needs (`generation_strategy`, `tier`, `repair_steps_applied`, `repair_attribution`) live on the serialized **`ElementResult`** inside `FileResult.element_results[]` (`micro_prime/models.py:214-440`), consumed by `prime_postmortem.py:1776`. | **FR-5 rewritten.** The authoritative fields are `ElementResult.*`, not a loosely-named JSON. *Which on-disk file* serializes them is **not confirmable from `src/` alone** → new residual **OQ-2'** (a home-verification step — exactly the move the principle prescribes, refusing to assert a "reachable" artifact as truth). |
| OQ-3: unclear whether the FDE computes mechanism live or reads it from an artifact. | **It's both, split by function.** Tier decisions are **never persisted** (only OTel metrics + logs; `classify_tier()` → `ClassificationResult`, `complexity/classifier.py:58`) → must be recomputed live, *or* read back as `ElementResult.tier` if the element already ran. Micro-prime strategy + repair steps **are fully recorded** on `ElementResult`. | **New FR-16.** Two explicit read modes: **explain** (FROM ARTIFACT — `ElementResult` of a completed run) vs **preflight** (LIVE — `classify_tier`/`LanguageRegistry`/`model_catalog` over hypothetical tasks). OQ-3 resolved. |
| OQ-8 / FR-3: the FDE's mechanism reasoning is implicitly LLM-backed. | Almost every mechanism fact is a **deterministic read or call** (`ElementResult` fields, `classify_tier`, `LanguageRegistry.get()`, `get_latest_model`). LLM is only needed to (a) detect assumptions in prose plans and (b) compose readable narrative. | **New FR-15 (deterministic-first).** Mechanism *facts* are deterministic; LLM is confined to prose parsing + narrative. Controls surprise-spend (cf. semantic-compliance reviewer's deferred auto-launch). OQ-8 resolved. |
| FR-9: the FDE layers on `domain-preflight` for raw plan/requirements review. | `domain-preflight` is **deterministic and consumes a post-ingestion `artisan-context-seed.json`**, not a raw plan/requirements `.md` (`workflows/builtin/domain_preflight_workflow.py`). The front-door for raw markdown is **`plan-ingestion`** (parses prose → features) and **`convergent-review`** (an *in-SDK* `ConvergentReviewWorkflow`, distinct from the external `/new-cnvrg-rvw-prmpt` skill). All are callable as a **library** via `WorkflowRegistry.run_workflow(...)` and `run_semantic_compliance(...)`. | **FR-9 corrected + sharpened.** Reuse is **function-call composition**, not CLI orchestration. Front-door = `plan-ingestion` + `convergent-review`; `domain-preflight` is reusable only *after* ingestion yields a context-seed. |
| FR-12 / sync-target: advance the protocol toward an **A2A typed contract**. | **There is no A2A transport in the SDK** — `docs/design/a2a/` is empty; the only A2A references are lazy imports to an external `contextcore.contracts.a2a` with `Any` fallbacks. The established in-SDK pattern for typed boundaries is **Keiyaku contracts** (K-6…K-10): frozen dataclasses with `.to_dict()`/`.from_json()`/`.to_prompt_section()` (`micro_prime/models.py`, `complexity/models.py`). | **FR-12 reframed.** "A2A-ready" → "**Keiyaku-contract-shaped and transport-agnostic**": define the FDE request/response as a frozen-dataclass contract pair now; the `.md` is its serialized view; it rides a synchronous transport (EventBus, or a contextcore A2A layer) **if/when one exists**. A2A is a roadmap *dependency the SDK does not yet have*, not a wiring target. |
| FR-14: the SA "hands off" to the FDE via an `fde-request.md`. | SA's `TriageReport` already carries an **optional folded-report reference** (`semantic_review: SemanticReviewRef`, `service_assistant/models.py`) — a proven precedent for referencing another component's report. SA's per-failure `FailureTriage.deterministic` / `.actionable` flags are the exact trigger signal for "this needs mechanism authority." | **FR-14 made concrete + new FR-17.** SA references the FDE report via a new optional `fde_explanation` ref field on `TriageReport` (mirroring `semantic_review`); the trigger is `FailureTriage.deterministic == True` or a recommendation that rests on a mechanism assumption. Auto-launch stays **deferred** (surprise-spend), matching the semantic-compliance reviewer. |

**Resolved open questions:**
- **OQ-1 → Separate package `src/startd8/fde/`** mirroring `service_assistant/`, with a `cli_fde.py` Typer sub-app registered via `app.add_typer(fde_app, name="fde")` (`cli.py:774` shows the `assist` pattern) and a thin `scripts/run_fde.py` shim that always exits 0. Different authority role ⇒ different home ⇒ separate package.
- **OQ-2 → Mechanism-source map pinned** to concrete symbols (see FR-5 / the new §6 source-of-truth table): tier=`classify_tier`/`ElementResult.tier`, strategy=`ElementResult.generation_strategy`, repair=`ElementResult.repair_steps_applied`+`repair_attribution`, model=`get_latest_model`/`Models`, language caps=`LanguageRegistry.get()`. **OQ-2' (residual):** confirm *which on-disk file* serializes `FileResult.element_results[]` — a home-verification step, deliberately left unasserted.
- **OQ-3 → Both, split by function** (FR-16): explain reads artifacts, preflight computes live.
- **OQ-4 → Library composition** via `WorkflowRegistry.run_workflow(...)` / `run_semantic_compliance(...)`; not CLI orchestration (FR-9).
- **OQ-5 → No A2A transport exists.** Follow the Keiyaku contract pattern; transport is a roadmap dependency (FR-12).
- **OQ-7 → Both operator and SA can invoke**, but SA **auto-launch is deferred** (FR-14/FR-17); v1 ships the file handoff + the trigger condition, not unconditional auto-spend.
- **OQ-8 → Deterministic-first** (FR-15); LLM confined to prose-plan parsing + narrative composition.

---

## 1. Problem Statement

A project built **with** the startd8 SDK is a consumer that sits *on top of* SDK mechanism
it cannot see. When something goes wrong — a Prime Contractor run fails, a generated file is
truncated, a tier route surprises the operator — the project's own agent is forced to infer
*why* from the artifacts in its own reach. As [Tekizai-Tekisho](../../design-princples/TEKIZAI_TEKISHO_DESIGN_PRINCIPLE.md)
documents (the 2026-06-03 micro-prime incident), this produces **plausible-but-wrong causal
stories**: real project evidence stitched to a misunderstood SDK mechanism, read as
authoritative, and propagated.

The **Service Assistant** (`src/startd8/service_assistant/`) already closes half of this gap:
it detects completed cap-dev-pipe runs and post-mortems from the project filesystem and
writes a triage artifact recommending an operator action. But the Service Assistant is
deliberately **Rabbit-weight** — it relays project *evidence* and maps causes to operational
actions; it does **not** carry SDK-mechanism authority. Its recommendations are sourced from
on-disk proxies in the project's reach, which is exactly the side of the composition the
principle warns is unreliable when it tries to narrate framework internals.

There is **no component whose authoritative home is the SDK that is deployed into the project
to answer "why, per the SDK's real mechanism?"** — and no component that reviews the project's
plans/requirements for assumptions about SDK behavior *before* a run burns cost reproducing a
predictable failure.

The **Forward Deployed Engineer** is that component. It is the SDK's insider, posted to the
project: it reads the SDK's own source-of-truth artifacts and mechanism, composes that with
the Service Assistant's project evidence, and (a) explains failures with home-authority and
(b) flags SDK-mechanism landmines in plans/requirements before implementation.

### Gap table

| Concern | Current State | Gap the FDE fills |
|---------|--------------|-------------------|
| Failure *evidence* (what happened on disk) | Service Assistant detects + triages | Covered (SA) — FDE consumes it as the EVIDENCE half |
| Failure *mechanism* (why, per SDK control flow) | Inferred by the project agent from reachable proxies | No SDK-home authority deployed downstream → FDE supplies MECHANISM half |
| Pre-run plan/requirements review | `domain-preflight`, plan-ingestion, semantic-compliance, CRP | None checks *SDK-mechanism assumptions* in the plan |
| Source-of-truth artifact knowledge | Only the SDK home knows which artifact is authoritative (`prime-result*.json` vs `generation_cache`) | FDE encodes that knowledge as code, not prose |
| Composed, source-labeled reporting | SA report is project-sourced only | FDE tags each claim OBSERVED(project) vs MECHANISM(sdk) |
| Project↔SDK communication | SA writes triage `.json`/`.md`; EventBus fire-and-forget | FDE establishes a durable `fde-*.md` protocol, A2A-ready |

---

## 2. Goals & Non-Goals (summary)

**Goal.** A hybrid FDE that is *deployed to a project* and, drawing its mechanism authority
from the SDK, (a) **explains failures** by composing Service Assistant project-evidence with
SDK-mechanism truth into a source-labeled report, and (b) **spots SDK-mechanism landmines** in
the project's plans and requirements *before* implementation — communicating via a durable
`fde-*.md` protocol designed to graduate to an A2A typed contract.

**Not a goal (v1).** Auto-remediation or executing fixes; replacing the Service Assistant's
detection/triage; a long-running daemon; a synchronous transport (v1 is `.md` files);
re-implementing existing review machinery.

---

## 3. Requirements

### A. Deployment & identity (hybrid form)

- **FR-1 — SDK-resident brain.** The FDE's mechanism logic SHALL live in the SDK as a
  first-class component (a class plus a `startd8 fde` CLI sub-app, mirroring `startd8 assist`),
  versioned and tested with the SDK. *Assumption: the CLI uses the same Typer `add_typer`
  pattern as `assist`/`manifest`.*

- **FR-2 — Project-deployed posting (scope-split footprint).** The FDE SHALL maintain a
  project-local footprint, established **automatically on first invocation** (optional
  `startd8 fde init` for explicit setup), split by scope (per OQ-6): **project-scoped** under
  **`.startd8/fde/`** — the context bundle `fde-context.json` (project id, contract/plan ref,
  SDK version from `startd8.__version__`), the idempotency `fde-cursor.json`, the inbound
  `fde-request.md`, and `fde-preflight.md`; **run-scoped** — `fde-explanation.md` written into
  the *run output dir* alongside `service-assistant-triage.json` (so FR-17's ref is a local
  sibling). "Deployed" means this footprint is established in the project, and the FDE operates
  with the project as its working context.

- **FR-3 — Mechanism authority is code, not prose.** Every MECHANISM claim the FDE makes SHALL
  be derived from reading an SDK source-of-truth artifact or calling SDK code at invocation
  time (the complexity classifier, the model catalog, the serialized `ElementResult`, the
  language registry — see the §6 source-of-truth table), NOT from a static knowledge-bundle
  string that can drift. *This is the direct answer to the principle's "trust the home's
  source-of-truth artifact" — the FDE encodes which symbol/artifact is authoritative for each
  question.* *(Resolved: two complementary catalogs — `get_latest_model(provider,
  tier)`/`Models.*` (`model_catalog.py`) for tier defaults, and `ModelCatalogEntry.agent_spec`/
  `get_models_by_role()` (`contractors/protocols.py:432`) for contractor roles. See OQ-10.)*

### B. Failure explanation (compose with Service Assistant)

- **FR-4 — Consume Service Assistant evidence.** The FDE SHALL read the Service Assistant's
  triage artifact (`service-assistant-triage.json`) as the **EVIDENCE half** of the
  composition — detection results, observed verdict, the project's on-disk reality. It SHALL
  NOT re-derive that evidence.

- **FR-5 — Supply SDK-mechanism authority (concrete sources).** For each failure in the SA
  triage, the FDE SHALL answer the *mechanism* question — *why did the SDK behave this way?* —
  by reading the SDK's authoritative symbols/artifacts, **not** a loosely-named JSON. Per the
  planning sweep the concrete sources are: **which tier ran and why** → `ElementResult.tier`
  (recorded) with the rationale recomputable via `classify_tier()` → `ClassificationResult.
  reason` (`complexity/classifier.py:58`); **whether micro-prime ran / which path** →
  `ElementResult.generation_strategy` (`micro_prime/models.py:246`); **which repair steps
  fired** → `ElementResult.repair_steps_applied` + `repair_attribution`; **the default model**
  → `get_latest_model(provider, tier)` / `Models.*`. This is the **MECHANISM half**. *(Resolved
  (OQ-2'): the element data is serialized in `prime-result*.json` under
  `history[].generation_metadata.micro_prime_file_results[].element_results[]`, and
  already-flattened/classified in `prime-postmortem-report.json` as `ElementPostMortem` — the
  FDE prefers the post-mortem surface for *explain* mode, falling back to the raw nesting.)*

- **FR-6 — Composed, source-labeled report.** The FDE SHALL emit `fde-explanation.md` that
  presents a composed causal story, with **every load-bearing claim tagged** `OBSERVED
  (project)` or `MECHANISM (sdk)`, per the principle's labeling rule. It SHALL NOT present a
  solo cross-boundary verdict (no unlabeled "why" claims).

- **FR-7 — Correct, not just relay.** Where the Service Assistant's operational recommendation
  rests on a mechanism assumption that is wrong (the SA is project-sourced and may misattribute
  mechanism), the FDE SHALL flag the correction with its home-authority — e.g. SA says
  "regenerate next pass" but the FDE knows the failure was on the `$0` deterministic path
  (cf. SA FR-14) so a plain re-run is idempotent-futile.

### C. Plan / requirements landmine review (pre-implementation)

- **FR-8 — SDK-mechanism-assumption lens (two tracks).** Given a project plan and/or
  requirements doc, the FDE SHALL review it for **assumptions about SDK behavior that contradict
  how the SDK actually decides**, across two tracks (per OQ-9):
  - **Track 1 — prose-assumption landmines (pre-ingestion, no signals):** detect assertions in
    the raw text about SDK behavior — "assumes micro-prime is off," "assumes a repair step exists
    for language X," "assumes tier T uses an LLM." LLM-driven (FR-15(a)); runs on raw markdown.
  - **Track 2 — mechanism-prediction landmines (post-ingestion, signals required):** after
    reusing `plan-ingestion` to produce features, extract `TaskComplexitySignals` and call
    `classify_tier()` live, flagging where the plan's stated expectation diverges from the
    predicted tier/route. Requires ingestion (prose cannot supply blast_radius/mro_depth/etc.).

  Output: `fde-preflight.md` listing each landmine with severity, its track, and the
  authoritative mechanism (§6 source) it contradicts.

- **FR-9 — Reuse existing review machinery (library composition).** The FDE SHALL build on,
  not replace, existing review components, layering on only the SDK-mechanism lens (FR-8);
  generic plan/requirements quality stays with those components. **Confirmed surfaces
  (planning):** all are callable as a *library*, not just CLI —
  `WorkflowRegistry.run_workflow("plan-ingestion", …)` (parses raw prose → features),
  `WorkflowRegistry.run_workflow("convergent-review", …)` (the *in-SDK* `ConvergentReviewWorkflow`
  over a requirements+plan pair — distinct from the external `/new-cnvrg-rvw-prmpt` skill), and
  `run_semantic_compliance(output_dir, …)`. **Correction:** the `domain-preflight` workflow
  consumes a *post-ingestion* `artisan-context-seed.json`, **not** a raw plan/requirements
  `.md` — so for raw-markdown landmine review the front-door is `plan-ingestion` +
  `convergent-review`, and `domain-preflight` is reusable only *downstream* of ingestion. The
  FDE SHALL compose via function calls, not CLI orchestration.

- **FR-10 — Landmine taxonomy is mechanism-grounded.** Each landmine class SHALL name the SDK
  source-of-truth that adjudicates it (router source, catalog entry, language profile
  capability table), so a flagged landmine carries home-authority, not FDE opinion.

### D. Communication protocol

- **FR-11 — `.md` file protocol (v1).** Project↔FDE communication SHALL be via a defined set of
  markdown artifacts in `.startd8/fde/`: an inbound request (`fde-request.md` — "explain this
  failure" / "review this plan") and outbound responses (`fde-explanation.md`,
  `fde-preflight.md`). The protocol SHALL define the required sections of each.

- **FR-12 — Keiyaku-contract-shaped, transport-agnostic protocol.** The FDE request/response
  SHALL be defined as a **Keiyaku-style typed contract** — a frozen dataclass pair with
  `.to_dict()` / `.from_json()` (and optionally `.to_prompt_section()`), matching the K-6…K-10
  pattern in `micro_prime/models.py` / `complexity/models.py`. The `fde-*.md` files (FR-11) are
  the **serialized view** of that contract. **Correction (planning):** there is **no A2A
  transport in the SDK today** (`docs/design/a2a/` is empty; A2A refs are lazy imports to an
  external `contextcore.contracts.a2a` with `Any` fallbacks). Therefore the synchronous channel
  is a **roadmap dependency, not a v1 wiring target**: when a transport materializes (EventBus,
  or a contextcore A2A layer), the *same* typed contract rides it unchanged. The contract is the
  durable interface; the transport is swappable.

- **FR-13 — Idempotent, one-shot.** Like the Service Assistant, the FDE SHALL be a one-shot
  invocation (no daemon) that is idempotent per (request artifact + SDK version), so
  re-invocation on an unchanged request does not redo work.

### E. Service Assistant handshake

- **FR-14 — SA triggers FDE on mechanism-relevant failures (concrete handshake).** When the
  Service Assistant produces a triage whose per-failure `FailureTriage.deterministic == True`
  (or whose recommendation rests on a mechanism assumption), the FDE SHALL be invocable to
  deepen that triage with home-authority. **Trigger signal (confirmed):** SA's existing
  `FailureTriage.deterministic` / `.actionable` flags (`service_assistant/models.py:80-93`).
  **v1:** SA emits an `fde-request.md` (file handoff); the FDE answers with `fde-explanation.md`.
  **Auto-launch is DEFERRED** — like the semantic-compliance reviewer, SA does not auto-spend
  on the FDE in v1; v1 ships the handoff artifact + the trigger condition, and operator/agent
  pulls the trigger. *v-next: the Keiyaku contract (FR-12) rides a synchronous transport.*

### F. Execution model (added in planning)

- **FR-15 — Deterministic-first mechanism core.** The FDE's mechanism *facts* SHALL come from
  deterministic reads/calls (the §6 sources), NOT an LLM. LLM use SHALL be confined to two
  bounded jobs: (a) detecting SDK-behavior *assumptions* in prose plans/requirements (FR-8),
  and (b) composing the human-readable narrative of the source-labeled report (FR-6). A failure
  explanation that requires *no* assumption-detection SHALL be producible with **zero LLM
  calls**. *This keeps mechanism authority deterministic-and-verifiable and caps surprise-spend.*

- **FR-16 — Two read modes (artifact vs live).** The FDE SHALL operate in two explicit modes:
  - **explain** (post-failure): read mechanism **FROM ARTIFACT** — the serialized `ElementResult`
    fields of a *completed* run (strategy, repair steps, recorded tier). No recomputation.
  - **preflight** (pre-implementation): compute mechanism **LIVE** — `classify_tier()` over
    extracted signals, `LanguageRegistry.get()` for capability, `get_latest_model()` for the
    model that *would* run — because the task has not run and nothing is recorded yet.

  The mode determines the source; a tier claim in *explain* cites `ElementResult.tier`, the same
  claim in *preflight* cites a live `classify_tier()` result (labeled `PREDICTION (sdk, live)` per
  FR-21, not an observation). **Clarification (R2-F1):** in *explain* mode the FDE SHALL NOT call
  `classify_tier()` — the tier *value* is `ElementResult.tier` (recorded) and the classifier
  *rationale string* (`ClassificationResult.reason`) is **preflight-only**; its absence in explain
  is not an error. The recorded `escalation_reason` MAY be cited in explain. Only an explicit
  operator "what would we classify today?" addendum may run `classify_tier()` in an explain
  context, and it MUST be tagged `PREDICTION`.

- **FR-17 — FDE report referenced from the SA triage (decoupled, no import cycle).** Mirroring
  SA's existing `semantic_review: SemanticReviewRef` folded-report pattern
  (`service_assistant/models.py:126,159`), the SA `TriageReport` SHALL gain an optional
  `fde_explanation` reference field pointing at the FDE's `fde-explanation.md` (path + checksum).
  **Coupling direction (verified):** `SemanticReviewRef` is an **SA-local, lightweight dataclass**
  — `service_assistant/models.py` imports **no** producer package. The FDE ref SHALL follow the
  same rule: SA owns a local `FdeRef` (path + checksum only) and does **not** import the `fde`
  package; the FDE depends on SA (reads `service-assistant-triage.json` as an artifact, or
  imports `TriageReport` for a typed read) but SA never depends on the FDE. **One-directional,
  no import cycle.** The FDE writes the report; SA (or the operator) attaches the ref.

### G. CRP-hardened requirements (v0.3 — consolidated from R1–R5 triage)

> These encode the accepted CRP suggestions. Each cross-references the originating suggestion IDs
> (full per-ID disposition in Appendix A). They amend/extend §A–F; on conflict, the more specific
> clause here governs.

- **FR-18 — Consumed-artifact trust gate.** Before treating any artifact it did not produce
  (`prime-result*.json`, `prime-postmortem-report.json`, `service-assistant-triage.json`,
  `.contextcore.yaml`) as mechanism/evidence, the FDE SHALL validate its schema/version and apply
  a defined **degrade-or-fail** policy on mismatch — never emit a confident claim from a
  malformed/old-schema input. *(R1-F11, R1-S2.)* When both the post-mortem and raw `prime-result`
  surfaces exist but disagree on `tier`/`repair_steps`, the FDE SHALL emit a
  `MECHANISM (sdk, conflict)` banner citing both paths + mtimes rather than silently picking one
  *(R5-S3)*.

- **FR-19 — Idempotency keyed on what actually changed.** The FDE cursor SHALL mirror the Service
  Assistant cursor shape — `processed: { "<run_id>": { request_checksum, triage_checksum,
  mechanism_checksum, sdk_version, processed_at } }`. Explain keys on `run_id` + the consumed-artifact
  checksums (so a regenerated `prime-result.json` re-explains); preflight keys on
  `(plan_checksum, requirements_checksum, sdk_version)`. *(Supersedes FR-13's request-only key;
  R1-F12, R1-S4, R2-S5, R5-F5.)*

- **FR-20 — Protocol/contract versioning + JSON-canonical serialization.** The FDE contract pair
  SHALL carry a `protocol_version` field **distinct from** the SDK-version staleness stamp, so a
  contract-shape change is distinguishable from an SDK bump *(R1-F3, R1-S5)*. The **JSON form
  (`.to_dict()`/`fde-explanation.json`/`fde-preflight.json`) is canonical**; the `.md` is a
  **derived, lossy human view** (`to_markdown()` from the dict) — no `from_markdown()` round-trip is
  promised *(R1-F4, R5-F4, R5-S5)*. Each contract SHALL implement `.to_prompt_section()` (Keiyaku
  K-6…K-10 parity) for bounded prompt/EventBus injection *(R3-S4)*.

- **FR-21 — Enforceable source-labeling (structural, not aspirational).** FR-6 SHALL be enforced by
  construction, not convention: a **third label `PREDICTION (sdk, live)`** is added (distinct from
  `MECHANISM (sdk, recorded)` and `OBSERVED (project)`) and is REQUIRED for all preflight/Track-2
  live-classification claims *(R1-F9)*. The composer SHALL build from a **slot template** whose
  `OBSERVED`/`MECHANISM`/`PREDICTION` blocks are pre-filled deterministically from a `List[LabeledClaim]`
  produced by `sources.py`; any LLM narrative may only reference already-emitted claim ids and SHALL
  NOT introduce new load-bearing claims *(R1-F5, R5-F2, R5-S2)*. A CI lint SHALL fail when a
  load-bearing line in an emitted report lacks a recognized tag *(R1-F10, R1-S8)*. The deterministic
  zero-LLM explain path SHALL be a **separate code path** (`deterministic_compose.py`) with a named
  test asserting `llm_call_count == 0` and an import guard that `sources.py`/`deterministic_compose.py`
  import no provider/agent modules *(R1-F6, R3-S2, R4-S5)*.

- **FR-22 — Cost-bounded LLM invocation.** Every FDE LLM entry point (Track 1, Track 2 ingestion,
  optional narrative) SHALL accept a configurable budget (`--max-cost-usd` / `STARTD8_FDE_MAX_COST_USD`)
  and record spend via the shared `CostTracker`, emitting `fde.cost_usd` in the report footer; on
  budget exhaustion it SHALL abort with a **labeled partial report**, not silent truncation.
  *(R2-F5, R2-S4.)*

- **FR-23 — Track-1 inbound redaction.** Before sending plan/requirements prose to an LLM (FR-8
  Track 1), the FDE SHALL pass it through a redaction pass (credential/env/bearer-token patterns,
  reusing `security.py`/SCR helpers) and list stripped spans under a `## Redaction manifest` in
  `fde-preflight.md`; unredacted secrets SHALL NOT reach the model. *(R3-F2, R3-S3.)*

- **FR-24 — FR-17 write-back transaction + discoverability.** On successful explain, the FDE SHALL
  **atomically** patch `service-assistant-triage.json` with `fde_explanation: {path, checksum,
  generated_at}` (the SA-local `FdeRef`), via `attach_fde_ref_to_triage()` in the FDE package; a
  failed patch SHALL be reported as partial success with non-zero CLI exit *(R3-F1, R3-S1)*. The FDE
  SHALL read SA **only via the JSON artifact** (no typed `TriageReport` import — no version-lockstep),
  and `FdeRef` is owned by and defined in `service_assistant/models.py` only *(R1-F1, R1-F2, R1-S6)*.
  A relocated run dir (path-miss with checksum-match) SHALL be detected and reported as a stale/relocated
  ref, not silently failed *(R1-F15)*. SA's `_render_markdown` SHALL append a one-line link to
  `fde-explanation.md` when the ref is present (SA-owned rendering, no import cycle) *(R4-S4)*.

- **FR-25 — Explain robustness: join, degrade, batch, three-way composition.**
  - **Feature↔element join:** when `FailureTriage.element_id`/`file` is set, mechanism reads target
    that element; absent + multiple elements ⇒ per-element subsections (no silent pick-first); absent
    + single element ⇒ use it *(R2-F3, R2-S2)*.
  - **Missing triage (degrade):** absent `service-assistant-triage.json` ⇒ a degraded MECHANISM-only
    report with a prominent `OBSERVED (project): unavailable` banner + remediation, CLI exit 2;
    opt-in `--allow-no-triage`; never silently re-run SA *(R3-F4, R3-S5)*.
  - **Batch patterns:** when the triage has `cross_feature_patterns`, the report SHALL include a
    **Batch patterns** section composing `OBSERVED (project)` + a `MECHANISM (sdk)` sentence citing
    the shared §6 source *(R4-F3)*.
  - **Three-way composition:** when `semantic_review` is present on the triage, the FDE SHALL summarize
    it as `OBSERVED (project, semantic)` and SHALL NOT issue competing semantic verdicts — mechanism
    claims stay `MECHANISM (sdk)` *(R3-F3)*.
  - **Legitimate disagreement:** when SA evidence and SDK mechanism are both valid but diverge, the
    report SHALL present both labeled halves — no solo winner (FR-6/NR-7) *(R1-F13, R1-S9)*.

- **FR-26 — Preflight soundness, isolation, and registry init.**
  - **Greenfield guard:** Track 2 tier-prediction SHALL run only for features with ≥1 `target_file`
    existing on disk under `project_root`; plan-only features get Track-1 prose landmines only, and any
    tier guess is tagged `PREDICTION (sdk, low-confidence — file not materialized)` *(R4-F1, R4-S2)*.
  - **Isolation:** Track 2's `plan-ingestion` SHALL write to an ephemeral
    `.startd8/fde/preflight-scratch/<request-checksum>/` (gitignored) — never the operator's pipeline
    output dir; only `fde-preflight.md` is durable *(R2-S3)*. Track 2 output is **non-authoritative**
    and carries a divergence disclaimer *(R1-F7, R1-S7)*; Track 2 is skippable and budget-gated
    *(R1-F8, R1-S3)*.
  - **Registry init:** `LanguageRegistry.discover()` / `ProviderRegistry.discover()` SHALL be called
    before any live preflight read *(R4-S1)*.
  - **Severity rubric:** landmines SHALL use `critical|high|medium|low` with the rubric in FR-10
    *(R4-F4)*.

- **FR-27 — Trigger breadth, exit codes, observability, context, hook, feature-scope (ops cluster).**
  - **FR-14 trigger** expands beyond `deterministic == True` to recommendations whose `re_run_strategy`
    ∈ {`re_run_prior_stage`, `regenerate_clean`, `split_element_or_increase_tier`} **and** a
    mechanism-sensitive `root_cause` (per SA's `CAUSE_TO_OPERATIONAL_ACTION`) *(R4-F2)*.
  - **Exit codes:** the `scripts/run_fde.py` shim MAY exit 0 on failure (logged); the `startd8 fde`
    CLI SHALL exit non-zero on failure/partial/budget-abort *(R3-F5)*.
  - **Observability:** on success the FDE SHALL emit `FDE_EXPLAIN_COMPLETE`/`FDE_PREFLIGHT_COMPLETE`
    EventBus events (new `EventType`s) with `OTelEventBridge` activation, mirroring SA/SCR
    *(R5-F1, R5-S1)*.
  - **Project context:** `fde-context.json` SHALL include a `project_context` block populated by the
    same rules as SA FR-5 (`.contextcore.yaml` walk-up + optional ContextCore state + `source` tag),
    reused via artifact read or a shared `startd8/project/` helper (no SA import cycle) *(R4-F5)*.
  - **cap-dev-pipe hook (opt-in):** an optional Step-12 hook runs `run_fde.py` after the SA shim when
    `STARTD8_FDE_AFTER_ASSIST=1` and the trigger matches; off by default (no surprise spend) *(R4-S3)*.
  - **Inbound request schema:** FR-11 SHALL define the inbound `fde-request.md` schema (`mode` ∈
    {explain, preflight}, `run_output_dir`, `plan_path`/`requirements_path`, optional `feature_id`,
    `sdk_version`) round-tripping to `FdeRequest` *(R2-F4)*; `explain --feature-id` (repeatable) scopes
    multi-failure triage *(R5-S4)*.
  - **Contract-related root causes:** explain SHALL cite `forward_manifest`/disk-compliance sources for
    contract-class root causes (e.g. `CROSS_FILE_CONTRACT`) *(R5-F3)*.

### H. Latest-run resolution (v0.3.1)

- **FR-28 — Default to the most recent run (explain).** The `explain` run-dir argument SHALL be
  **optional**. When the argument is omitted, or when a `--latest` flag is passed, the FDE SHALL
  resolve the target run automatically:
  1. **Search root:** the cap-dev-pipe pipeline-output base, auto-discovered as
     `<project-root>/.cap-dev-pipe/pipeline-output/`, with a `--base <path>` override. Within it,
     select the project subdirectory by the posting's `project_context.project_id` when known; if
     exactly one project subdir exists, use it; if several and none is selected, exit non-zero with
     a disambiguation message (name the candidates).
  2. **Recency + completeness:** among that project's `run-*/plan-ingestion` directories, pick the
     **newest that contains a `service-assistant-triage.json`** (the evidence half). Recency is by
     run-directory ordering (the `run-NNN-YYYYMMDDThhmm` naming sorts chronologically). If none has
     a triage, **fall back** to the newest containing `prime-result*.json` (explain will then
     degrade to MECHANISM-only per FR-25 and exit non-zero).
  3. **Override:** an explicit path argument always wins over `--latest`/the default.
  4. **No run found:** exit non-zero with a clear message ("no run with a triage under `<base>`;
     run `startd8 assist scan` first or pass a path").
  The resolved run id and the fact that it was auto-selected SHALL be reported to the operator
  (so "latest" is never silently ambiguous). This is **explain-only** — `preflight` targets plans,
  not runs, and is unaffected. *(Field-driven: operators repeatedly want "explain the run I just
  did" without pasting the full `run-*/plan-ingestion` path.)*

---

## 4. Non-Requirements

- **NR-1.** No auto-remediation or fix execution — the FDE explains and flags; it does not act.
- **NR-2.** No daemon / inotify watcher — one-shot invocation like the Service Assistant.
- **NR-3.** Does not replace the Service Assistant's detection or triage — it composes on top.
- **NR-4.** Does not re-implement `domain-preflight` / plan-ingestion / semantic-compliance /
  CRP — only adds the SDK-mechanism lens.
- **NR-5.** No synchronous transport in v1 — `.md` files only; A2A is the roadmap, not v1.
- **NR-6.** No new failure-classification taxonomy — reuse `RootCause`/`PipelineStage` (as SA
  does). The FDE adds *mechanism authority*, not a new taxonomy.
- **NR-7.** Not a decision-maker — it supplies the MECHANISM half for a human/agent to act on.

---

## 5. Open Questions

> OQ-1, 3, 4, 5, 7, 8 were resolved by the planning pass (see §0). Retained in condensed form
> for traceability; OQ-2 narrowed to a residual home-verification step; OQ-6 still open.

- **OQ-1 → RESOLVED.** Separate package `src/startd8/fde/` + `cli_fde.py` Typer sub-app + thin
  `scripts/run_fde.py` shim. Different authority role ⇒ different home.
- **OQ-2 → RESOLVED (incl. the OQ-2' residual).** The per-question mechanism sources are pinned
  (§6 table). The residual — *which on-disk file serializes the element data* — is now confirmed:
  **`prime-result.json` / `prime-result-<task-id>.json`**, written by
  `scripts/run_prime_workflow.py:838` (in-repo, in `scripts/`). The earlier sweep's "nothing in
  `src/` writes it" was a `src/`-only blind spot — the producer is the workflow *runner* script,
  not a library module. Field path: `result_dict["history"][i]["generation_metadata"]
  ["micro_prime_file_results"][j]["element_results"][k]` → `.tier` / `.generation_strategy` /
  `.repair_steps_applied` / `.repair_attribution` (serialized at `prime_adapter.py:1257` via
  `_serialize_file_result`, attached to history at `prime_contractor.py:3919`). **Cleaner
  alternative for the FDE:** read `prime-postmortem-report.json`, whose `ElementPostMortem`
  records already-*flattened and classified* the same fields (`prime_postmortem.py:1773-1815`) —
  preferred for *explain* mode; fall back to the raw `prime-result*.json` nesting if the
  post-mortem is absent. *(Meta-note: v0.1 named `prime-result.json` and was right; the
  planning sweep's correction was itself wrong — caught only by checking the home, which is the
  Tekizai-Tekisho lesson in miniature.)*
- **OQ-3 → RESOLVED** (FR-16). Both — *explain* reads `ElementResult`; *preflight* calls
  `classify_tier()` live. Tier is never persisted as a standalone artifact (OTel metrics + logs
  only); the recorded form is `ElementResult.tier`.
- **OQ-4 → RESOLVED** (FR-9). All reusable components are library-callable via
  `WorkflowRegistry.run_workflow(...)` / `run_semantic_compliance(...)`. Function-call
  composition, not CLI. `domain-preflight` is downstream of ingestion (consumes a context-seed).
- **OQ-5 → RESOLVED** (FR-12). No A2A transport exists in the SDK; follow the Keiyaku
  frozen-dataclass contract pattern; the transport is a roadmap dependency.
- **OQ-6 → RESOLVED.** **Auto-create on first invocation** (no *mandatory* init — matches the
  Service Assistant's no-init precedent); an **optional `startd8 fde init`** is provided for
  explicit setup / version re-stamp. **Footprint split by scope:** project-scoped posting
  (`fde-context.json`, `fde-cursor.json`, inbound `fde-request.md`, and `fde-preflight.md` which
  is not tied to a run) lives in **`.startd8/fde/`** (the `.startd8/` storage convention);
  run-scoped **`fde-explanation.md` is written into the run output dir** next to
  `service-assistant-triage.json`, so FR-17's `fde_explanation` ref is a local sibling and the
  explanation co-locates with the run evidence it composes. SDK version stamped from
  `startd8.__version__` into `fde-context.json` on create and refreshed each invocation (feeds
  the FR-13 staleness key).
- **OQ-7 → RESOLVED** (FR-14). Both operator and SA can invoke; SA **auto-launch deferred** to
  avoid surprise LLM spend; v1 ships the file handoff + trigger condition only.
- **OQ-8 → RESOLVED** (FR-15). Deterministic-first; LLM confined to prose-plan assumption
  detection + narrative composition. Zero-LLM path exists for pure artifact explanation.

### New open questions surfaced during planning

- **OQ-9 → RESOLVED (two-track preflight).** Full `TaskComplexitySignals` (blast_radius,
  mro_depth, cross-file edges, …) **cannot** be extracted from prose — they need real code/AST —
  so tier *prediction* requires ingestion. Resolution splits preflight into two tracks
  (formalized in **FR-8**): **Track 1 — prose-assumption landmines** (no signals): the LLM reads
  the raw plan/requirements and flags assertions about SDK behavior ("assumes micro-prime is
  off," "assumes a Go repair step exists") — runs **pre-ingestion, on raw markdown**.
  **Track 2 — mechanism-prediction landmines** (signals required): the FDE first runs
  `plan-ingestion` (FR-9 reuse) to produce features, then `extract_signals_from_feature()` →
  live `classify_tier()`, flagging where the plan's stated expectation diverges from the
  predicted tier/route — runs **after ingestion**. Track 1 preserves "works on raw markdown" for
  the high-value prose lens; Track 2 is honest that tier prediction needs ingestion.
- **OQ-10 → RESOLVED (no discrepancy).** Both catalogs exist and are complementary, not
  conflicting: `ModelCatalogEntry` with `.agent_spec` lives at **`contractors/protocols.py:432`**
  (role-based — `DRAFT`/`VALIDATE`/`REVIEW`, via `get_models_by_role`); `Models.*` /
  `get_latest_model(provider, tier)` live in **`model_catalog.py`** (tier-based defaults). The
  sweep only checked `model_catalog.py` and missed the former. FR-5 uses `get_latest_model` for
  the tier-default question and `ModelCatalogEntry`/`get_models_by_role` for the contractor-role
  question.

---

## 6. Mechanism Source-of-Truth Table (pinned in planning)

> The home-authority map. Every FDE MECHANISM claim cites one of these. "Read mode" is per
> FR-16. This is the FDE's analogue of SA's `CAUSE_TO_OPERATIONAL_ACTION` mapping.

| Mechanism question | Authoritative source (symbol / file:line) | Read mode | Notes |
|--------------------|--------------------------------------------|-----------|-------|
| Which tier ran? | `ElementResult.tier` (`micro_prime/models.py:214+`) | explain: ARTIFACT | Recorded per element. |
| Why that tier? | `classify_tier()` → `ClassificationResult.reason` (`complexity/classifier.py:58`) | preflight: LIVE | Decision **not persisted** standalone (OTel + logs only). |
| Did micro-prime run / which path? | `ElementResult.generation_strategy` (`micro_prime/models.py:246`) — **raw `prime-result*.json` only** | explain: ARTIFACT | Values: `template`, `llm_simple`, `escalation`, `cache:*`, … **CORRECTION (R2-F2/R2-S1): `ElementPostMortem` does NOT carry `generation_strategy`** (only `template_used`, a partial proxy) — strategy requires the raw element_results, not the flattened post-mortem surface. |
| Which repair steps fired? | `ElementResult.repair_steps_applied` + `repair_attribution` | explain: ARTIFACT | AST-valid-before/after recorded too. |
| What model would run (by tier)? | `get_latest_model(provider, tier)` / `Models.*` (`model_catalog.py`) | preflight: LIVE | Tier-based defaults. |
| What model would run (by contractor role)? | `ModelCatalogEntry.agent_spec` / `get_models_by_role()` (`contractors/protocols.py:432`) | preflight: LIVE | Role-based (DRAFT/VALIDATE/REVIEW). |
| Does the SDK support X for language Y? | `LanguageRegistry.get(lang_id)` props (`languages/registry.py`, `protocol.py`) | preflight: LIVE | `repair_enabled`, `syntax_check_command`, MicroPrime support, etc. |
| **Where is the element data serialized?** | **`prime-result*.json`** (`scripts/run_prime_workflow.py:838`); partially flattened in **`prime-postmortem-report.json`** | explain: ARTIFACT | Path: `history[].generation_metadata.micro_prime_file_results[].element_results[]`. `ElementPostMortem` carries `tier`/`repair_steps`/`template_used`/`repair_attribution` (use for those); **`generation_strategy` is raw-JSON-only** (R2-F2). Double-absence → labeled "mechanism unavailable" (R1-F14/S10). On both-present mismatch → `MECHANISM (sdk, conflict)` banner (R5-S3). |

---

*v0.2 — Post-planning self-reflective update. 6 requirements revised (FR-3/5/9/12/14 sharpened
or corrected, FR-12 reframed), 3 added (FR-15 deterministic-first, FR-16 two read modes, FR-17
SA reference field). A §6 source-of-truth table pins the mechanism map.*

*v0.2.1 — Open-question resolution pass (home-verified against the codebase). **OQ-2' resolved:**
the element data lives in `prime-result*.json` (`scripts/run_prime_workflow.py:838`) /
flattened in `prime-postmortem-report.json` — and notably the planning sweep's own "nothing
writes it" correction was itself wrong (a `src/`-only blind spot), caught only by checking the
home. **OQ-10 resolved:** no discrepancy — `ModelCatalogEntry.agent_spec` exists at
`contractors/protocols.py:432` (role-based) alongside `get_latest_model` (tier-based).
**SA↔FDE coupling resolved:** one-directional, no import cycle (FR-17).*

*v0.2.2 — Final two open questions resolved. **OQ-6:** auto-create footprint (optional
`fde init`), scope-split placement — project-scoped under `.startd8/fde/`, run-scoped
`fde-explanation.md` beside the SA triage (FR-2). **OQ-9:** two-track preflight — Track 1
prose-assumption landmines on raw markdown (no signals), Track 2 mechanism-prediction landmines
after `plan-ingestion` (FR-8). **All open questions now resolved.** Ready for Convergent Review.*

*v0.3 — CRP R1–R5 triaged. ~35 F-suggestions accepted (1 duplicate round deduped, 0 rejected on
merit), consolidated into **FR-18…FR-27** (§3.G) + in-place fixes to §6 (R2-F2 `generation_strategy`
correctness defect), FR-16 (R2-F1 explain/preflight tier-rationale split). Per-ID dispositions in
Appendix A; dedup in Appendix B. One correctness defect caught — CRP earned its pass. Next:
implement from v0.3 (Phase 6).*

*v0.3.1 — Added **FR-28 (latest-run resolution)**: the `explain` run-dir arg is optional;
bare `explain` or `--latest` targets the newest `run-*/plan-ingestion` with a triage under the
pipeline-output base (fallback: newest with `prime-result*.json`); explicit path overrides;
auto-selection is reported. Explain-only. Field-driven (operators want "explain the run I just
did" without the full path).*

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

> Triage of CRP R1–R5 (F-suggestions). **Every material F-suggestion ACCEPTED.** "Merged into" cites
> where the obligation now lives. Many R-IDs co-merge into one consolidated FR (§3.G) — that is the
> point of consolidation, not a loss of traceability.

| ID(s) | Theme | Merged into | Date |
|-------|-------|-------------|------|
| R2-F2 | `ElementPostMortem` lacks `generation_strategy` (correctness defect) | §6 table row fix + FR-18/FR-25 | 2026-06-04 |
| R2-F1 | explain must not call `classify_tier`; rationale is preflight-only | FR-16 clarification | 2026-06-04 |
| R1-F11 | consumed-artifact schema/version trust gate | FR-18 | 2026-06-04 |
| R5-F3 | cite forward_manifest for contract root causes | FR-27 (contract root causes) | 2026-06-04 |
| R1-F12, R5-F5 | idempotency key includes consumed-artifact checksums | FR-19 | 2026-06-04 |
| R1-F3 | `protocol_version` distinct from SDK version | FR-20 | 2026-06-04 |
| R1-F4, R5-F4 | `.md` derived/lossy; JSON canonical | FR-20 | 2026-06-04 |
| R1-F9 | third label `PREDICTION (sdk, live)` | FR-21 | 2026-06-04 |
| R1-F5, R5-F2 | composer over pre-labeled claim list; slot template | FR-21 | 2026-06-04 |
| R1-F10 | CI lint fails on untagged load-bearing line | FR-21 | 2026-06-04 |
| R1-F6 | zero-LLM explain path acceptance test (separate code path) | FR-21 | 2026-06-04 |
| R2-F5 | per-invocation cost budget via `CostTracker` | FR-22 | 2026-06-04 |
| R3-F2 | Track-1 inbound redaction before LLM | FR-23 | 2026-06-04 |
| R3-F1 | FR-17 write-back transaction (`attach_fde_ref_to_triage`) | FR-24 | 2026-06-04 |
| R1-F1 | drop typed `TriageReport` import — artifact-only | FR-24 | 2026-06-04 |
| R1-F2 | `FdeRef` owned by `service_assistant/models.py` | FR-24 | 2026-06-04 |
| R1-F15 | relocated run-dir / dangling ref detection | FR-24 | 2026-06-04 |
| R2-F3 | feature↔element join rule | FR-25 (join) | 2026-06-04 |
| R3-F4 | missing-triage degraded report + exit 2 | FR-25 (degrade) | 2026-06-04 |
| R4-F3 | batch `cross_feature_patterns` section | FR-25 (batch) | 2026-06-04 |
| R3-F3 | three-way SCR composition, no competing semantic verdict | FR-25 (three-way) | 2026-06-04 |
| R1-F13 | legitimate SA↔mechanism disagreement (both labeled) | FR-25 (disagreement) | 2026-06-04 |
| R1-F14 | double-absence fallback ("mechanism unavailable") | FR-18 + §6 + FR-25 | 2026-06-04 |
| R4-F1 | Track-2 greenfield guard (predict only if file on disk) | FR-26 (greenfield) | 2026-06-04 |
| R1-F7 | Track-2 non-authoritative + divergence disclaimer | FR-26 (isolation) | 2026-06-04 |
| R1-F8 | Track-2 cost budget + skip control | FR-26 + FR-22 | 2026-06-04 |
| R4-F4 | landmine severity rubric `critical|high|medium|low` | FR-26 (severity) → FR-10 | 2026-06-04 |
| R4-F2 | FR-14 trigger breadth (re_run_strategy + mechanism-sensitive cause) | FR-27 (trigger) | 2026-06-04 |
| R3-F5 | shim exit-0 vs CLI non-zero | FR-27 (exit codes) | 2026-06-04 |
| R5-F1 | `FDE_*_COMPLETE` EventBus + OTel bridge | FR-27 (observability) | 2026-06-04 |
| R4-F5 | `project_context` block in `fde-context.json` | FR-27 (context) | 2026-06-04 |
| R2-F4 | inbound `fde-request.md` schema | FR-27 (inbound schema) | 2026-06-04 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Disposition / Rationale | Date |
|----|------------|--------|-------------------------|------|
| R3 (2nd block, lines ~675–763) | Duplicate of R3 round (identical R3-F1…F5) | append artifact | **DEDUP — not a rejection.** Identical content appended twice; triaged once under the R3 entries above. Retained in Appendix C as round history per CRP protocol (do not strip). | 2026-06-04 |
| — | (No F-suggestion rejected on merit.) | R1–R5 | All were anchored, code-verified, and non-overlapping with settled decisions; near-total accept is the correct outcome for a review of this quality, not a rubber-stamp. | 2026-06-04 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-04

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-04 17:20:00 UTC
- **Scope**: External architecture/interface/risk review weighted to the sponsor focus asks (SA↔FDE coupling, transport-agnostic Keiyaku protocol, deterministic/LLM boundary, two-track preflight, source-labeling enforceability, security/ops). Requirements-targeted (F-prefix) suggestions; plan-targeted (S-prefix) and the coverage matrix are in the plan file.

##### Sponsor focus-ask answers (read first; orchestrator triages, no ACCEPT/REJECT here)

**Ask 1 — SA↔FDE coupling & dependency direction (FR-17).**
- **Summary answer:** Partial — the *one-directional* claim holds only if FDE reads SA via the **artifact**, not via a typed `TriageReport` import; the current FR-17 prose permits both ("reads `service-assistant-triage.json` as an artifact, *or* imports `TriageReport` for a typed read") and the typed-import branch reintroduces a build-time version lockstep.
- **Rationale:** FR-17 verifies SA stays import-free of `fde` (good, no cycle), but it leaves the FDE→SA edge as *either* artifact *or* typed import. A typed `from startd8.service_assistant.models import TriageReport` makes the FDE fail to import whenever SA's dataclass shape changes — a soft version-lockstep, which is exactly the Tekizai-Tekisho coupling the artifact boundary is meant to avoid. FR-4 already mandates reading the JSON artifact, so the typed-import branch is redundant *and* riskier.
- **Assumptions / conditions:** SA and FDE ship in the same wheel today (no independent versioning), so a typed import would not break at install — but it still couples test/refactor cadence and defeats "transport-agnostic."
- **Suggested improvements:** see R1-F1 (drop the typed-import option; artifact-only read with a schema-version gate) and R1-F2 (pin `FdeRef` ownership/location).

**Ask 2 — Keiyaku-contract-shaped, transport-agnostic protocol (FR-12).**
- **Summary answer:** Depends on a versioning field the doc does not yet require — the markdown↔contract round-trip is not guaranteed lossless or independently versionable as written.
- **Rationale:** FR-12 defines `.to_dict()`/`.from_json()` but the `.md` is only described as "the serialized view" with no `from_markdown()` inverse and no stated round-trip invariant; FR-11 lists "required sections" but not a parseable grammar. The only version stamp in the doc is the *SDK version* (FR-13/OQ-6), which is a staleness key, not a *protocol* version — so a contract-shape change is indistinguishable from an SDK bump.
- **Assumptions / conditions:** EventBus is fire-and-forget with no resident consumer, so "transport-agnostic" is currently aspirational (no transport exercises the contract); the contract must therefore be validated by serialization round-trip tests, not by a live channel.
- **Suggested improvements:** R1-F3 (add an explicit `protocol_version` field distinct from SDK version + a round-trip invariant), R1-F4 (decide whether `.md` is authoritative-or-derived and require a `from_markdown` inverse or declare `.md` lossy/derived-only).

**Ask 3 — Deterministic-first vs LLM boundary (FR-15).**
- **Summary answer:** Partial — the boundary is clean for *facts* but FR-15(b) "narrative composition" is an unconstrained LLM step that can emit unlabeled synthesis, directly threatening FR-6.
- **Rationale:** FR-15 confines the LLM to (a) prose-assumption detection and (b) narrative composition, but nothing constrains (b) to *only* restate already-labeled facts. An LLM composing prose can interpolate a plausible mechanism sentence with no `OBSERVED`/`MECHANISM` tag — the precise failure mode (plausible-but-wrong causal story) the Problem Statement cites.
- **Assumptions / conditions:** Holds whenever FR-6 labeling is enforced only by prose convention rather than by a structural check on the composer's output.
- **Suggested improvements:** R1-F5 (require the composer to operate over a pre-labeled claim list and forbid introducing new load-bearing claims; add a post-compose lint that every load-bearing sentence carries a tag), R1-F6 (define the zero-LLM explain-path acceptance test).

**Ask 4 — Two-track preflight ordering (FR-8 / OQ-9).**
- **Summary answer:** Partial — Track 2 silently re-runs `plan-ingestion`, which can duplicate or diverge from the operator's later real ingestion, and the requirements do not bound its cost/latency or reconcile the two ingestions.
- **Rationale:** FR-8 Track 2 calls `WorkflowRegistry.run_workflow("plan-ingestion", …)` to extract signals, but the operator's actual pipeline run will ingest again — two ingestions of the same plan can yield different feature decompositions (LLM nondeterminism), so a preflight tier *prediction* may not match what later runs. FR-8 also does not cap the cost of invoking a full workflow purely for prediction.
- **Assumptions / conditions:** `plan-ingestion` is itself LLM-backed and nondeterministic; if it were deterministic the divergence risk would shrink.
- **Suggested improvements:** R1-F7 (state that Track 2 ingestion is preflight-only and MUST NOT be treated as authoritative by the later real run; require a cache/handoff or an explicit "prediction may diverge" disclaimer in `fde-preflight.md`), R1-F8 (add a cost/latency budget + a skip/opt-in for Track 2).

**Ask 5 — Tekizai-Tekisho source-labeling guarantee (FR-6).**
- **Summary answer:** No — as written FR-6 is aspirational prose; there is no enforceable test/lint that fails on an unlabeled load-bearing claim, and preflight *predictions* (FR-16) are not labeled distinctly from explain *observations*.
- **Rationale:** FR-6 says "every load-bearing claim tagged" but defines neither "load-bearing" operationally nor an automated gate. FR-16 says preflight tier claims are "labeled a *prediction*" but introduces no third tag — `OBSERVED`/`MECHANISM` only — leaving PREDICTION ambiguous against MECHANISM.
- **Assumptions / conditions:** none.
- **Suggested improvements:** R1-F9 (add a third label `PREDICTION (sdk, live)` distinct from `MECHANISM (sdk, recorded)` and require it for all Track 2 / preflight claims), R1-F10 (make FR-6 testable: a structural check on emitted `.md` that fails CI if any bulleted load-bearing line lacks a recognized tag).

**Ask 6 — Security & ops (cross-boundary reads).**
- **Summary answer:** Partial — the FDE reads artifacts it did not produce with no stated trust boundary, and the idempotency key (request checksum + SDK version) is correct across SDK upgrades but blind to changes in the *upstream artifacts* it reads.
- **Rationale:** FR-3/FR-5 read `prime-result*.json`, `prime-postmortem-report.json`, SA triage, `.contextcore.yaml` — none are validated for schema/trust before being treated as mechanism truth. FR-13 keys idempotency on (request artifact + SDK version), so if `prime-result.json` is regenerated with the *same* request and SDK, a stale cached explanation is served (the input that actually changed is not in the key). FR-14 deferring auto-launch is sufficient for *FDE-initiated* spend but does not cap spend when an operator/agent pulls the trigger repeatedly.
- **Assumptions / conditions:** artifacts live in the project's own tree (semi-trusted), not a third-party source.
- **Suggested improvements:** R1-F11 (require schema/version validation of every consumed artifact with a defined degrade-or-fail policy), R1-F12 (add the consumed-artifact checksums to the idempotency key, not just the request + SDK version).

##### Numbered suggestions (F-prefix — requirements)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | In FR-17, drop the "or imports `TriageReport` for a typed read" branch; mandate FDE reads SA **only** via the `service-assistant-triage.json` artifact. | The typed-import branch reintroduces a build/refactor-time version lockstep between `fde` and `service_assistant`, defeating the transport-agnostic, artifact-boundary goal; FR-4 already requires the artifact read. | FR-17, sentence "imports `TriageReport` for a typed read" | Lint: assert `src/startd8/fde/` has no `import` of `service_assistant.models`; unit test reads SA triage purely from JSON. |
| R1-F2 | Interfaces | medium | State explicitly that `FdeRef` is **owned by and lives in** `service_assistant/models.py` (SA-local, path+checksum only), and that the `fde` package never defines or imports it. | FR-17 says "SA owns a local `FdeRef`" but the schema owner/location is asserted, not pinned; ambiguity invites the FDE to define a shared type and recreate a cycle. | FR-17, "SA owns a local `FdeRef`" | Grep test: `FdeRef` defined only under `service_assistant/`; no reference under `fde/`. |
| R1-F3 | Interfaces | high | Add a `protocol_version` field to the FdeRequest/Response contract (FR-12), distinct from the SDK-version staleness key (FR-13/OQ-6). | The doc's only version stamp is the SDK version, which is a staleness key, not a contract-shape version; a contract change is currently indistinguishable from an SDK bump, breaking forward/backward compat detection. | FR-12, after "frozen dataclass pair with `.to_dict()` / `.from_json()`" | Round-trip test asserts `protocol_version` survives `to_dict`/`from_json`; a contract change bumps it and old `.md` parses with a clear version-mismatch error. |
| R1-F4 | Data | high | Declare whether `fde-*.md` is **authoritative or derived**; if the contract is authoritative, mark `.md` lossy/one-way and drop any round-trip claim; if `.md` must round-trip, require a `from_markdown()` inverse with a stated invariant. | FR-12 calls `.md` "the serialized view" but provides only `to_dict/from_json` (JSON), no `from_markdown`; "lossless round-trip" cannot be assumed across a prose rendering. | FR-11 / FR-12, ".md files ... are the serialized view" | If round-trippable: property test `from_markdown(to_markdown(x)) == x`. If derived: doc states `.md` is non-authoritative and the JSON/dataclass is the source of truth. |
| R1-F5 | Validation | high | Constrain FR-15(b) narrative composition to operate over a **pre-labeled claim list** produced by `sources.py`; forbid the composer from introducing new load-bearing claims. | An unconstrained LLM narrative step can interpolate an unlabeled mechanism sentence — the exact plausible-but-wrong failure the Problem Statement cites — violating FR-6. | FR-15, item "(b) composing the human-readable narrative" | Test: feed a fixed labeled-claim set; assert every load-bearing sentence in output maps back to an input claim id (no orphan claims). |
| R1-F6 | Validation | medium | Add an explicit acceptance criterion for the **zero-LLM explain path**: a named test that runs `explain` over a fixture run with assertion `llm_call_count == 0`. | FR-15 promises a zero-LLM path but gives no way to verify the LLM was not invoked; without a test this regresses silently the first time compose() calls an LLM unconditionally. | FR-15, "producible with **zero LLM calls**" | Unit test asserts the explain path completes and the agent/cost tracker records zero LLM calls on a no-assumption fixture. |
| R1-F7 | Risks | high | State that Track 2's `plan-ingestion` run is **preflight-only and non-authoritative**: its features/tier predictions MUST NOT be reused by the operator's later real run, and `fde-preflight.md` must carry a "prediction may diverge from the actual run" disclaimer. | `plan-ingestion` is LLM-backed and nondeterministic; running it twice (preflight + real) can yield different decompositions, so a preflight tier prediction can mislead if mistaken for ground truth. | FR-8, Track 2 bullet | Doc review: disclaimer text present; test that preflight output is written to `fde-preflight.md` only, never to a path the real pipeline ingests. |
| R1-F8 | Ops | medium | Add a cost/latency budget and an opt-in/skip control for Track 2 (full-workflow invocation for prediction). | FR-8 invokes a full `plan-ingestion` workflow purely for preflight prediction with no spend cap; this is the same surprise-spend class FR-14 guards against, but unguarded here. | FR-8, Track 2 "after reusing `plan-ingestion`" | Test: Track 2 is skippable via flag; a budget breach aborts with a clear message; Track 1 (cheap, prose) always runs. |
| R1-F9 | Data | high | Introduce a third source label `PREDICTION (sdk, live)` distinct from `MECHANISM (sdk, recorded)`; require all preflight/Track-2 claims to use it. | FR-6 defines only `OBSERVED`/`MECHANISM`; FR-16 says preflight tier claims are "labeled a prediction" but provides no tag, so a live `classify_tier()` prediction is indistinguishable from a recorded mechanism fact. | FR-6 (label set) + FR-16 (preflight cites a live result) | Lint: every preflight `.md` claim uses `PREDICTION`; no preflight claim uses `MECHANISM`; explain uses `MECHANISM`/`OBSERVED` only. |
| R1-F10 | Validation | high | Make FR-6 enforceable: define "load-bearing claim" operationally (e.g. any bulleted causal/mechanism line) and add a CI lint that fails when such a line in `fde-explanation.md`/`fde-preflight.md` lacks a recognized tag. | FR-6 is currently aspirational prose with no gate; the focus file explicitly asks whether the guarantee is enforceable — it is not, as written. | FR-6, "every load-bearing claim tagged" | CI check parses emitted `.md`, flags any untagged load-bearing line; fixture with an untagged claim must fail the check. |
| R1-F11 | Security | high | Require schema/version validation of every **consumed** artifact (`prime-result*.json`, `prime-postmortem-report.json`, `service-assistant-triage.json`, `.contextcore.yaml`) before treating it as mechanism/evidence, with a defined degrade-or-fail policy on mismatch. | FR-3/FR-4/FR-5 read artifacts the FDE did not produce with no trust boundary; a malformed/old-schema artifact would be read as authoritative mechanism truth — the cross-boundary trust gap the focus file flags. | New FR under §F, or extend FR-3 | Test: feed a wrong-schema/old-version artifact; assert the FDE fails or degrades with a labeled warning rather than emitting a confident claim. |
| R1-F12 | Security | medium | Extend the FR-13 idempotency key to include checksums of the **consumed upstream artifacts**, not just (request artifact + SDK version). | If `prime-result.json` is regenerated under the same request + SDK version, the current key serves a stale cached explanation; the input that actually changed is excluded from the key. | FR-13, "idempotent per (request artifact + SDK version)" | Test: change only `prime-result.json` content; assert the FDE recomputes rather than returning the cached explanation. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F13 | Risks | medium | Specify FDE behavior when SA triage and SDK mechanism **disagree but neither is wrong** (e.g. SA observed a truncated file; mechanism says the tier/strategy was correct) — FR-7 only covers SA being *wrong*. | FR-7 frames the FDE as "correct, not just relay" only for SA mechanism-misattribution; it omits the legitimate-disagreement case where both halves are right and the composition must present both, not pick a winner. | FR-7, "Where the Service Assistant's operational recommendation rests on a mechanism assumption that is wrong" | Fixture where SA evidence and SDK mechanism are both valid but point different directions; assert the report presents both halves labeled, no solo verdict (FR-6 NR-7). |
| R1-F14 | Data | medium | Define the fallback contract when `prime-postmortem-report.json` is absent **and** `prime-result*.json` nesting is partial/malformed (OQ-2' resolved the happy path only). | FR-5/OQ-2 pin a preferred surface + fallback, but not the case where *both* are missing or the nested path `history[].generation_metadata.micro_prime_file_results[]` is empty (e.g. an all-cache or pre-micro-prime run). | FR-5, "fall back to the raw `prime-result*.json` nesting" | Test with a run dir missing both surfaces and one with empty `element_results[]`; assert a labeled "mechanism unavailable" claim, not a crash or fabricated tier. |
| R1-F15 | Architecture | low | Clarify whether `fde-explanation.md` (run-scoped, OQ-6) and the FR-17 `FdeRef` checksum stay consistent when a run dir is copied/moved (the ref stores path + checksum). | FR-2/OQ-6 place the explanation in the run output dir while the ref lives on the SA `TriageReport`; a moved run dir invalidates the path but not the checksum, leaving a dangling ref with no detection rule. | FR-17, "path + checksum" / FR-2 run-scoped placement | Test: move the run dir; assert the consumer detects path-miss vs checksum-match and reports a clear "relocated/stale ref" rather than silently failing. |

**Endorsements**: none (R1 is the first round; no prior untriaged suggestions exist).
**Disagreements**: none (no prior rounds).

---

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-04

**Scope:** Second-pass requirements review (F-prefix). Deduped against R1-F1…F15 and R1 focus-ask answers. Code-verified gaps: `ElementPostMortem` field parity, FR-16 vs FR-5 tier-rationale conflict, inbound `fde-request.md` contract.

**Executive summary:** FR-16 forbids recomputation in explain mode, but FR-5 promises tier *rationale* via live `classify_tier()` — those cannot both apply to explain. §6 lists `generation_strategy` on the post-mortem-preferred path where the flattened record does not carry it. FR-11 defines outbound sections but not inbound `fde-request.md` validation — the handoff is one-way.

| ID | Area | Severity | Suggestion | Proposed Placement | Validation Approach |
|----|------|----------|------------|--------------------|---------------------|
| R2-F1 | Architecture | high | FR-16 vs FR-5: in explain mode, tier *value* is artifact; tier *rationale* is unavailable unless recomputed — state explicitly | FR-16 + FR-5 + §6 "Why that tier?" row | Explain fixture: assert report cites `ElementResult.tier` without calling `classify_tier()` unless labeled PREDICTION |
| R2-F2 | Data | high | §6 row `generation_strategy`: correct preferred read path (raw JSON or extend `ElementPostMortem`) | §6 table + FR-5 | Test: post-mortem-only fixture still returns correct `generation_strategy` |
| R2-F3 | Interfaces | high | FR-5/FR-4: specify feature↔element join when SA failure is feature-scoped | FR-5, FR-4 | Multi-element feature fixture: explain lists all elements or honors `element_id` |
| R2-F4 | Ops | medium | FR-11: define inbound `fde-request.md` schema (mode, run_dir, artifact paths) | FR-11 | Invalid request → clear error; valid round-trips to `FdeRequest` |
| R2-F5 | Ops | medium | FR-15/FR-14: operator invocation SHALL respect a per-run cost budget via `CostTracker` | FR-15 + FR-14 | Test: budget=0 skips LLM steps; over-budget aborts with labeled message |

---

#### R2-F1 — Architecture — high
**Anchor:** FR-16, bullet "explain (post-failure): read mechanism **FROM ARTIFACT** … No recomputation." / FR-5, "rationale recomputable via `classify_tier()` → `ClassificationResult.reason`"

**Finding:** FR-16 says explain mode does not recompute; recorded tier is `ElementResult.tier`. FR-5 simultaneously offers "why that tier?" from `classify_tier()` → `ClassificationResult.reason`, which is a **live** call requiring `TaskComplexitySignals` not present in the post-mortem artifact. §6 lists "Why that tier?" with read mode "preflight: LIVE" only for the rationale row, but FR-5 prose blurs this. An implementer following FR-5 will call `classify_tier()` inside explain and violate FR-16, or skip rationale and under-deliver.

**Suggestion:** Split §6 and FR-5: **explain** cites `ElementResult.tier` (recorded) and MAY cite `escalation_reason` / classifier outputs already serialized on the element record; it SHALL NOT call `classify_tier()` unless the operator explicitly requests a "what would we classify today?" addendum tagged `PREDICTION (sdk, live)`. **Preflight** owns `ClassificationResult.reason`. Add to FR-16: "The `classify_tier()` rationale string is not an explain-mode artifact; absence is not an error."

**Expected impact:** Removes a direct FR-5/FR-16 contradiction. Clarifies what "mechanism authority" means for explain vs preflight (focus ask #3, second-order).

---

#### R2-F2 — Data — high
**Anchor:** §6 table row "Did micro-prime run / which path? → `ElementResult.generation_strategy`" / §6 row "Where is the element data serialized? → prefer `ElementPostMortem`"

**Finding:** The §6 table assigns `generation_strategy` to explain: ARTIFACT and recommends the post-mortem flattened surface. Code shows `ElementPostMortem` does not include `generation_strategy` (`prime_postmortem.py:1798-1812`); only `template_used` is copied. Requirements therefore over-promise what the preferred read surface delivers.

**Suggestion:** Update §6: split the row into (a) `generation_strategy` → **raw** `prime-result*.json` element_results[] (required when strategy matters); (b) note `ElementPostMortem.template_used` is a partial proxy only. Alternatively add FR-5 sub-clause: "post-mortem flattening SHALL include `generation_strategy`" (requires a one-field addition in `prime_postmortem.py` — document as preferred fix). Until then, FR-5 MUST state post-mortem-only reads cannot assert strategy path without raw fallback.

**Expected impact:** Aligns requirements with code. Prevents false MECHANISM claims on the common explain path.

---

#### R2-F3 — Interfaces — high
**Anchor:** FR-4 ("read … triage artifact as the EVIDENCE half") / FR-5 ("for each failure in the SA triage")

**Finding:** `FailureTriage` includes optional `element_id` and `file` (`service_assistant/models.py:88-89`) because SA already encounters element-level failures. FR-5 says "for each failure" without stating how mechanism rows are selected when `FeaturePostMortem.elements` has length > 1. This mirrors controlled-corpus OQ-7 (term↔file altitude) on the FDE explain path.

**Suggestion:** Add to FR-5: "When the SA failure carries `element_id` or `file`, mechanism reads SHALL target that element only. When absent and multiple elements exist for the feature, the FDE SHALL emit per-element mechanism subsections for each element (no silent first-element selection). When absent and exactly one element exists, that element is used."

**Expected impact:** Testable join semantics. Improves end-user value — explanations name the actual failing element.

---

#### R2-F4 — Ops — medium
**Anchor:** FR-11, "`fde-request.md` — 'explain this failure' / 'review this plan'"

**Finding:** FR-11 defines outbound `fde-explanation.md` / `fde-preflight.md` sections but not the **inbound** request contract. FR-14 says SA "emits `fde-request.md`" but does not specify required fields (mode, `run_output_dir`, plan paths, feature_id). Without a schema, hand-written requests fail unpredictably and cannot round-trip to `FdeRequest` (FR-12).

**Suggestion:** Extend FR-11 with an inbound section table for `fde-request.md`: `mode` ∈ {explain, preflight}, `run_output_dir` (required for explain), `plan_path`/`requirements_path` (preflight), optional `feature_id`, `sdk_version` stamp. Require `FdeRequest.from_markdown()` or reject with a labeled parse error. SA-generated requests MUST conform to the same schema (FR-14).

**Expected impact:** Low-effort protocol hardening. Makes file handoff machine-verifiable before implementation.

---

#### R2-F5 — Ops — medium
**Anchor:** FR-15 ("caps surprise-spend") / FR-14 ("auto-launch is DEFERRED")

**Finding:** Deferring SA auto-launch prevents *unconditional* spend but not *unbounded* spend when an operator runs `startd8 fde preflight` on a large plan with Track 1 + Track 2. FR-15 names surprise-spend control but does not require integration with the SDK's existing cost accounting.

**Suggestion:** Add to FR-15: "Each FDE invocation SHALL accept a configurable cost budget (CLI flag or env) and SHALL record LLM spend via the shared `CostTracker` (or successor). When the budget is exhausted, remaining LLM steps (Track 1 continuation, Track 2 ingestion, narrative compose) SHALL abort with a labeled partial report, not silent truncation." Cross-reference semantic-compliance reviewer's budget pattern.

**Expected impact:** Operational robustness for operator-triggered runs. Reuses existing SDK cost surfaces.

---

**Endorsements:**
- R1-F9 (`PREDICTION` label) — required once FR-16/FR-5 split is clarified (R2-F1).
- R1-F10 (FR-6 labeling lint) — still the enforceability gate.
- R1-F11 (artifact schema validation) — pairs with R2-F4 inbound schema.

**Disagreements:** none.

---

#### Review Round R3 — claude-sonnet-4-6 — 2026-06-04

**Scope:** Third-pass requirements review (F-prefix). Deduped against R1–R2. Adds second-order focus coverage: FR-17 ref persistence, triage-absent degrade, SCR coexistence on the same triage artifact.

##### Sponsor focus addendum (second-order; orchestrator triages)

**Ask 1 addendum (FR-17 ref write-back).**
- **Summary answer:** No — FR-17 specifies the ref field but not **who writes it** after explain completes.
- **Rationale:** SA generates triage before FDE runs; `fde_explanation` can only be populated after `fde-explanation.md` exists. Without a required write-back step, the ref is documentation-only.
- **Assumptions / conditions:** FDE explain is operator- or script-triggered after SA.
- **Suggested improvements:** R3-F1.

**Ask 6 addendum (preflight LLM reads).**
- **Summary answer:** Partial — artifact path validation is covered by R1-F11; **content redaction** before LLM reads of plan prose is not.
- **Rationale:** Trust boundary is on bytes read and on secrets in prompts.
- **Assumptions / conditions:** Plans may contain example credentials.
- **Suggested improvements:** R3-F2 (redaction); see plan R3-S3.

| ID | Area | Severity | Suggestion | Proposed Placement | Validation Approach |
|----|------|----------|------------|--------------------|---------------------|
| R3-F1 | Interfaces | high | FR-17: explain SHALL atomically patch `service-assistant-triage.json` with `FdeRef` | FR-17 | After explain, triage JSON contains ref; checksum matches `fde-explanation.md` |
| R3-F2 | Security | medium | FR-8 Track 1: redact plan/requirements content before LLM; document stripped classes | FR-8 Track 1 | Fixture plan with fake API key never appears in LLM payload |
| R3-F3 | Interfaces | medium | FR-4/FR-6: when `semantic_review` ref present, explain SHALL cross-reference SCR, not re-litigate | FR-4 + FR-17 area | Triage with SCR ref → explanation cites SCR path; no duplicate semantic verdict |
| R3-F4 | Validation | medium | FR-4: missing SA triage → degraded MECHANISM-only report, non-zero CLI exit | FR-4 | No triage fixture → banner + exit 2; full report when triage present |
| R3-F5 | Ops | low | FR-13 / FR-1: distinguish CLI exit codes from `scripts/run_fde.py` always-exit-0 shim | FR-13 + NR-2 | CLI returns 1 on failure; shim returns 0 |

---

#### R3-F1 — Interfaces — high
**Anchor:** FR-17, "the SA `TriageReport` SHALL gain an optional `fde_explanation` reference field … The FDE writes the report; SA (or the operator) attaches the ref."

**Finding:** The requirement describes ownership but not the **completion transaction**. Without mandating that `explain` updates the triage artifact, downstream consumers (dashboards, agents that only open `service-assistant-triage.json`) will not discover the FDE output. This is distinct from R1-F2 (where `FdeRef` lives) — it is the missing **write-back** obligation.

**Suggestion:** Add to FR-17: "On successful explain, the FDE SHALL atomically update `service-assistant-triage.json` in the run output directory with `fde_explanation: {path, checksum, generated_at}` using the SA-local `FdeRef` type. Failure to update the triage file SHALL be reported as a partial success (explanation written, ref not attached) with a non-zero CLI exit." SA auto-launch remains deferred; SA does not need to import `fde`.

**Expected impact:** Makes FR-17 operational. One-file discovery for operators.

---

#### R3-F2 — Security — medium
**Anchor:** FR-8 Track 1, "LLM-driven (FR-15(a)); runs on raw markdown"

**Finding:** FR-8 Track 1 processes raw plan/requirements text. FR-15(a) is an LLM boundary. Neither FR-8 nor the security focus (ask 6) requires **content redaction** before that call — only artifact schema trust (R1-F11). Example credentials in a plan could be exfiltrated to the model provider.

**Suggestion:** Add to FR-8 Track 1: "Before LLM submission, plan and requirements text SHALL pass through a redaction pass (credential-like patterns, `.env` excerpts, bearer tokens). Redacted spans SHALL be listed in `fde-preflight.md` under `## Redaction manifest`. The LLM SHALL NOT receive unredacted secrets." Reuse or factor shared helpers with semantic-compliance prompt assembly.

**Expected impact:** Closes an obvious ops/security gap for a component that reads arbitrary project markdown.

---

#### R3-F3 — Interfaces — medium
**Anchor:** FR-4 ("read … triage artifact as the EVIDENCE half") / `TriageReport.semantic_review` (`service_assistant/models.py:159`)

**Finding:** SA triage may already include a folded `semantic_review` ref (SCR report). The FDE explain path is a **second** SDK-home authority layered on the same failure. Nothing in FR-4/FR-6 prevents the FDE narrative from contradicting SCR semantic verdicts or duplicating them without attribution — a three-way composition (SA evidence + SCR semantic + FDE mechanism) is unstated.

**Suggestion:** Add to FR-4: "When `semantic_review` is present on the triage artifact, the FDE SHALL include an `OBSERVED (project, semantic)` section summarizing the SCR ref (path, aggregate, fail count) and SHALL NOT issue competing semantic verdicts — mechanism claims remain `MECHANISM (sdk)` only." Cross-link semantic-compliance FRs for boundary clarity.

**Expected impact:** End-user value — one explanation that composes all three lenses without contradiction.

---

#### R3-F4 — Validation — medium
**Anchor:** FR-4, "SHALL read the Service Assistant's triage artifact … as the EVIDENCE half"

**Finding:** FR-4 is absolute ("SHALL read") with no missing-triage behavior. In practice explain will be invoked on incomplete run dirs. Hard failure is correct for strict mode but hurts operability; silent MECHANISM-only reports without a banner violate FR-6 (unlabeled absence of evidence).

**Suggestion:** Add to FR-4: "If `service-assistant-triage.json` is absent, the FDE SHALL emit a **degraded** `fde-explanation.md` containing only `MECHANISM (sdk)` sections plus a prominent `OBSERVED (project): unavailable` banner and remediation (`startd8 assist --output-dir …`). CLI SHALL exit non-zero. Full composed explain requires triage."

**Expected impact:** Robust operator workflow when SA hook was skipped.

---

#### R3-F5 — Ops — low
**Anchor:** FR-13 ("one-shot invocation") / FR-1 (`scripts/run_fde.py` shim)

**Finding:** FR-1 mirrors SA's `run_service_assistant.py` shim that **always exits 0** so cap-dev-pipe hooks never block. The requirements do not distinguish shim behavior from interactive `startd8 fde` CLI exit codes. Operators scripting against exit status will get false success on explain failure.

**Suggestion:** Add to NR-2 or FR-13: "The cap-dev-pipe shim (`scripts/run_fde.py`) MAY exit 0 on failure (logged only). The Typer CLI (`startd8 fde …`) SHALL return non-zero on failure, partial success (explanation without triage ref), or budget abort." Document in FR-1.

**Expected impact:** Clear automation contract. Prevents silent pipeline green when FDE failed.

---

**Endorsements:**
- R2-F4 (inbound `fde-request.md` schema) — pairs with R3-F1 write-back for a complete file protocol.
- R1-F6 (zero-LLM acceptance test) — satisfied structurally by plan R3-S2 split.
- R3-F3 complements semantic-compliance reviewer without duplicating its scope.

**Disagreements:** none.

---

#### Review Round R3 — claude-sonnet-4-6 — 2026-06-04

**Scope:** Third-pass requirements review (F-prefix). Deduped against R1–R2. Adds second-order focus coverage: FR-17 ref persistence, triage-absent degrade, SCR coexistence on the same triage artifact.

##### Sponsor focus addendum (second-order; orchestrator triages)

**Ask 1 addendum (FR-17 ref write-back).**
- **Summary answer:** No — FR-17 specifies the ref field but not **who writes it** after explain completes.
- **Rationale:** SA generates triage before FDE runs; `fde_explanation` can only be populated after `fde-explanation.md` exists. Without a required write-back step, the ref is documentation-only.
- **Assumptions / conditions:** FDE explain is operator- or script-triggered after SA.
- **Suggested improvements:** R3-F1.

**Ask 6 addendum (preflight LLM reads).**
- **Summary answer:** Partial — artifact path validation is covered by R1-F11; **content redaction** before LLM reads of plan prose is not.
- **Rationale:** Trust boundary is on bytes read and on secrets in prompts.
- **Assumptions / conditions:** Plans may contain example credentials.
- **Suggested improvements:** R3-F2 (redaction); see plan R3-S3.

| ID | Area | Severity | Suggestion | Proposed Placement | Validation Approach |
|----|------|----------|------------|--------------------|---------------------|
| R3-F1 | Interfaces | high | FR-17: explain SHALL atomically patch `service-assistant-triage.json` with `FdeRef` | FR-17 | After explain, triage JSON contains ref; checksum matches `fde-explanation.md` |
| R3-F2 | Security | medium | FR-8 Track 1: redact plan/requirements content before LLM; document stripped classes | FR-8 Track 1 | Fixture plan with fake API key never appears in LLM payload |
| R3-F3 | Interfaces | medium | FR-4/FR-6: when `semantic_review` ref present, explain SHALL cross-reference SCR, not re-litigate | FR-4 + FR-17 area | Triage with SCR ref → explanation cites SCR path; no duplicate semantic verdict |
| R3-F4 | Validation | medium | FR-4: missing SA triage → degraded MECHANISM-only report, non-zero CLI exit | FR-4 | No triage fixture → banner + exit 2; full report when triage present |
| R3-F5 | Ops | low | FR-13 / FR-1: distinguish CLI exit codes from `scripts/run_fde.py` always-exit-0 shim | FR-13 + NR-2 | CLI returns 1 on failure; shim returns 0 |

---

#### R3-F1 — Interfaces — high
**Anchor:** FR-17, "the SA `TriageReport` SHALL gain an optional `fde_explanation` reference field … The FDE writes the report; SA (or the operator) attaches the ref."

**Finding:** The requirement describes ownership but not the **completion transaction**. Without mandating that `explain` updates the triage artifact, downstream consumers (dashboards, agents that only open `service-assistant-triage.json`) will not discover the FDE output. This is distinct from R1-F2 (where `FdeRef` lives) — it is the missing **write-back** obligation.

**Suggestion:** Add to FR-17: "On successful explain, the FDE SHALL atomically update `service-assistant-triage.json` in the run output directory with `fde_explanation: {path, checksum, generated_at}` using the SA-local `FdeRef` type. Failure to update the triage file SHALL be reported as a partial success (explanation written, ref not attached) with a non-zero CLI exit." SA auto-launch remains deferred; SA does not need to import `fde`.

**Expected impact:** Makes FR-17 operational. One-file discovery for operators.

---

#### R3-F2 — Security — medium
**Anchor:** FR-8 Track 1, "LLM-driven (FR-15(a)); runs on raw markdown"

**Finding:** FR-8 Track 1 processes raw plan/requirements text. FR-15(a) is an LLM boundary. Neither FR-8 nor the security focus (ask 6) requires **content redaction** before that call — only artifact schema trust (R1-F11). Example credentials in a plan could be exfiltrated to the model provider.

**Suggestion:** Add to FR-8 Track 1: "Before LLM submission, plan and requirements text SHALL pass through a redaction pass (credential-like patterns, `.env` excerpts, bearer tokens). Redacted spans SHALL be listed in `fde-preflight.md` under `## Redaction manifest`. The LLM SHALL NOT receive unredacted secrets." Reuse or factor shared helpers with semantic-compliance prompt assembly.

**Expected impact:** Closes an obvious ops/security gap for a component that reads arbitrary project markdown.

---

#### R3-F3 — Interfaces — medium
**Anchor:** FR-4 ("read … triage artifact as the EVIDENCE half") / `TriageReport.semantic_review` (`service_assistant/models.py:159`)

**Finding:** SA triage may already include a folded `semantic_review` ref (SCR report). The FDE explain path is a **second** SDK-home authority layered on the same failure. Nothing in FR-4/FR-6 prevents the FDE narrative from contradicting SCR semantic verdicts or duplicating them without attribution — a three-way composition (SA evidence + SCR semantic + FDE mechanism) is unstated.

**Suggestion:** Add to FR-4: "When `semantic_review` is present on the triage artifact, the FDE SHALL include an `OBSERVED (project, semantic)` section summarizing the SCR ref (path, aggregate, fail count) and SHALL NOT issue competing semantic verdicts — mechanism claims remain `MECHANISM (sdk)` only." Cross-link semantic-compliance FRs for boundary clarity.

**Expected impact:** End-user value — one explanation that composes all three lenses without contradiction.

---

#### R3-F4 — Validation — medium
**Anchor:** FR-4, "SHALL read the Service Assistant's triage artifact … as the EVIDENCE half"

**Finding:** FR-4 is absolute ("SHALL read") with no missing-triage behavior. In practice explain will be invoked on incomplete run dirs. Hard failure is correct for strict mode but hurts operability; silent MECHANISM-only reports without a banner violate FR-6 (unlabeled absence of evidence).

**Suggestion:** Add to FR-4: "If `service-assistant-triage.json` is absent, the FDE SHALL emit a **degraded** `fde-explanation.md` containing only `MECHANISM (sdk)` sections plus a prominent `OBSERVED (project): unavailable` banner and remediation (`startd8 assist --output-dir …`). CLI SHALL exit non-zero. Full composed explain requires triage."

**Expected impact:** Robust operator workflow when SA hook was skipped.

---

#### R3-F5 — Ops — low
**Anchor:** FR-13 ("one-shot invocation") / FR-1 (`scripts/run_fde.py` shim)

**Finding:** FR-1 mirrors SA's `run_service_assistant.py` shim that **always exits 0** so cap-dev-pipe hooks never block. The requirements do not distinguish shim behavior from interactive `startd8 fde` CLI exit codes. Operators scripting against exit status will get false success on explain failure.

**Suggestion:** Add to NR-2 or FR-13: "The cap-dev-pipe shim (`scripts/run_fde.py`) MAY exit 0 on failure (logged only). The Typer CLI (`startd8 fde …`) SHALL return non-zero on failure, partial success (explanation without triage ref), or budget abort." Document in FR-1.

**Expected impact:** Clear automation contract. Prevents silent pipeline green when FDE failed.

---

**Endorsements:**
- R2-F4 (inbound `fde-request.md` schema) — pairs with R3-F1 write-back for a complete file protocol.
- R1-F6 (zero-LLM acceptance test) — satisfied structurally by plan R3-S2 split.
- R3-F3 complements semantic-compliance reviewer without duplicating its scope.

**Disagreements:** none.

---

#### Review Round R4 — claude-sonnet-4-6 — 2026-06-04

**Scope:** Fourth-pass requirements review (F-prefix). Deduped against R1–R3. Focus ask #4 second-order (Track 2 signal soundness), FR-14 trigger completeness, batch-level composition, preflight severity rubric.

##### Sponsor focus addendum (second-order)

**Ask 4 addendum (Track 2 tier prediction on greenfield plans).**
- **Summary answer:** No — not as written; `extract_signals_from_feature()` needs materialized files, so tier predictions on hypothetical paths are unreliable.
- **Rationale:** `complexity/signals.py` reads the filesystem under `project_root`; plan-only features yield empty signals but still produce a tier.
- **Assumptions / conditions:** Preflight runs before implementation.
- **Suggested improvements:** R4-F1.

| ID | Area | Severity | Suggestion | Proposed Placement | Validation Approach |
|----|------|----------|------------|--------------------|---------------------|
| R4-F1 | Risks | high | FR-8 Track 2: only tier-predict when ≥1 `target_file` exists on disk; else prose-only | FR-8 Track 2 | Hypothetical path → Track 2 landmine suppressed or low-confidence tag |
| R4-F2 | Interfaces | medium | FR-14: expand FDE trigger beyond `deterministic` to mechanism-dependent recommendations | FR-14 | Fixture: non-deterministic failure + futile re-run strategy → explain recommended |
| R4-F3 | Data | medium | FR-6/FR-7: explain SHALL address `cross_feature_patterns` from SA triage | FR-6 + FR-7 | Triage with batch pattern → explanation section cites pattern + mechanism source |
| R4-F4 | Validation | medium | FR-8: define landmine severity rubric (critical/high/medium) | FR-8 output clause | Three fixture landmines map to defined severities |
| R4-F5 | Ops | medium | FR-2: `fde-context.json` SHALL record `project_context` from `.contextcore.yaml` (mirror SA FR-5) | FR-2 | Context fields populated when yaml present |

---

#### R4-F1 — Risks — high
**Anchor:** FR-8 Track 2, "extract `TaskComplexitySignals` and call `classify_tier()` live" / §6 "Why that tier? → preflight: LIVE"

**Finding:** Track 2 assumes ingestion-produced `target_files` are sufficient for signal extraction. In practice `extract_signals_from_feature()` (`complexity/signals.py:95+`) uses `project_root` to inspect whether those paths exist and derive AST-adjacent signals. On a greenfield plan, paths are often **aspirational** — the classifier still emits a tier from sparse signals, and FR-8 treats divergence from the plan's expectation as a landmine. That is not sound prediction; it is noise labeled as mechanism authority.

**Suggestion:** Add to FR-8 Track 2: "Tier-route landmines SHALL only be emitted for features where at least one `target_file` exists on disk under `project_root`. For plan-only features, Track 1 prose landmines apply; Track 2 SHALL emit `skipped_track2: file_not_materialized` in `fde-preflight.md` rather than a tier prediction." Optionally require `ClassificationResult.confidence` or signal-count threshold before a tier landmine is allowed.

**Expected impact:** Makes preflight credible for the primary use case (review before first run). Directly addresses focus ask #4.

---

#### R4-F2 — Interfaces — medium
**Anchor:** FR-14, "When … `FailureTriage.deterministic == True` (or whose recommendation rests on a mechanism assumption)"

**Finding:** FR-14 names `deterministic == True` and mechanism-assumption recommendations in prose, but SA also marks failures **non-deterministic yet actionably wrong** — e.g. recommending `re_run_prior_stage` when the mechanism path makes re-run futile for a different reason than determinism. FR-7's example (deterministic path, futile re-run) is exactly this. FR-14's trigger predicate is narrower than FR-7's correction scope — explain may not run when it is most needed.

**Suggestion:** Expand FR-14 trigger: "FDE explain is recommended when `FailureTriage.deterministic == True` **OR** `recommended_action.re_run_strategy` ∈ {`re_run_prior_stage`, `regenerate`, `split_element_or_increase_tier`} **and** the failure's `root_cause` is in the mechanism-sensitive set (tier_escalation, repair_exhausted, template_miss, …) per SA's `CAUSE_TO_OPERATIONAL_ACTION`." Document the explicit list or reference SA's map. Auto-launch remains deferred.

**Expected impact:** Aligns trigger with FR-7. Operators know when to invoke explain without reading source code.

---

#### R4-F3 — Data — medium
**Anchor:** FR-6 ("composed causal story") / SA `TriageReport.cross_feature_patterns` (`service_assistant/models.py:156`)

**Finding:** SA triage includes **batch-level** `cross_feature_patterns` (shared root causes across features). FR-6/FR-7 focus on per-failure composition only. A systemic mechanism issue (e.g. shared tier_escalation across features) appears in SA evidence but has no FR-6 section — the FDE may repeat per-feature mechanism paragraphs without surfacing the batch pattern the SA already detected.

**Suggestion:** Add to FR-6: "When the triage artifact includes `cross_feature_patterns`, `fde-explanation.md` SHALL include a **Batch patterns** section summarizing each pattern with `OBSERVED (project)` and, where applicable, one `MECHANISM (sdk)` sentence citing the shared §6 source (e.g. classifier default for that tier). Per-feature sections reference pattern ids when applicable (FR-7 batch corrections)."

**Expected impact:** Better end-user narrative for multi-feature failures — reuses SA work, adds mechanism authority at batch altitude.

---

#### R4-F4 — Validation — medium
**Anchor:** FR-8, "listing each landmine with severity, its track, and the authoritative mechanism"

**Finding:** FR-8 requires severity on each landmine but does not define the rubric — unlike SA's controlled `SEVERITIES` vocabulary (`operational_actions.py`). Implementers will invent incompatible scales (P0/P1 vs critical/high vs blocker/minor), blocking comparison across runs and Grafana-style trending.

**Suggestion:** Add to FR-8: "Severity SHALL be one of `critical` | `high` | `medium` | `low`. **`critical`**: would cause deterministic waste or wrong-tier spend on first run; **`high`**: likely wrong mechanism assumption; **`medium`**: plausible drift; **`low`**: advisory. FR-10 landmine classes map to a default severity." Table in FR-10 appendix.

**Expected impact:** Testable, comparable preflight output. Low doc cost.

---

#### R4-F5 — Ops — medium
**Anchor:** FR-2, "`fde-context.json` (project id, contract/plan ref, SDK version)" / SA FR-5 (`service_assistant/context.py`)

**Finding:** FR-2 stamps project id and SDK version into `fde-context.json` but does not require **project context** assembly. SA's `load_project_context()` already walks `.contextcore.yaml` and ContextCore state (`service_assistant/context.py`). Preflight and explain benefit from the same project/task binding (which plan, which sprint) — especially when multiple plans live in one repo.

**Suggestion:** Extend FR-2: "`fde-context.json` SHALL include a `project_context` block populated via the same rules as SA FR-5 (`.contextcore.yaml` walk-up, optional ContextCore state path, `source` tag). Preflight landmines that reference project scope SHALL cite this block as `OBSERVED (project, context)`." Reuse `load_project_context()` from SA via artifact read or shared helper in `startd8/project/` to avoid import cycle.

**Expected impact:** Quick reuse — one function call. Makes FDE reports self-contained for operators.

---

**Endorsements:**
- R4-F1 complements R2-F1 (FR-16 explain vs preflight tier rationale split).
- R3-F2 (Track 1 redaction) — required before FR-8 Track 1 LLM on customer plans.
- R1-F7 / R1-S7 (preflight non-authoritative disclaimer).

**Disagreements:** none.

---

#### Review Round R5 — claude-sonnet-4-6 — 2026-06-03

**Scope:** Fifth-pass requirements review (F-prefix). Deduped against R1–R4. Focus ask #2 (EventBus without resident consumer) and #5 (labeling enforceability); forward-manifest mechanism gaps; idempotency depth.

##### Sponsor focus addendum (second-order)

**Ask 2 addendum (EventBus as near-term transport).**
- **Summary answer:** Partial — fire-and-forget EventBus is sufficient for v1 **if** FDE emits typed events and activates `OTelEventBridge` (same as SA/SCR); no synchronous consumer required.
- **Rationale:** `service_assistant/notify.py` and `semantic_compliance/orchestrator.py` already treat EventBus as the observability transport.
- **Assumptions / conditions:** Operators use Loki/Tempo, not in-process handlers.
- **Suggested improvements:** R5-F1.

**Ask 5 addendum (enforceable labeling).**
- **Summary answer:** Partial — aspirational unless compose is constrained; post-hoc lint alone is insufficient.
- **Rationale:** Unconstrained LLM narrative can smuggle mechanism claims.
- **Assumptions / conditions:** FR-15(b) remains enabled for explain.
- **Suggested improvements:** R5-F2 (endorse plan R5-S2).

| ID | Area | Severity | Suggestion | Proposed Placement | Validation Approach |
|----|------|----------|------------|--------------------|---------------------|
| R5-F1 | Ops | medium | FR-12: emit `FDE_*_COMPLETE` EventBus events + OTel bridge | FR-12 + new NR note | Mock emit after explain; OTel bridge activate called |
| R5-F2 | Validation | high | FR-6: compose SHALL pre-fill labeled mechanism blocks before any LLM narrative | FR-6 + FR-15 | Fixture explain: all MECHANISM claims appear in deterministic sections |
| R5-F3 | Data | medium | FR-5: explain SHALL cite `forward_manifest` / disk compliance for contract-related root causes | FR-5 §6 row | `CROSS_FILE_CONTRACT` failure → explanation cites validator source |
| R5-F4 | Interfaces | medium | FR-11/FR-12: JSON artifact canonical; `.md` derived-only | FR-11 | `fde-explanation.json` round-trips; `.md` optional for humans |
| R5-F5 | Ops | medium | FR-13: idempotency key includes triage + postmortem checksums, not request-only | FR-13 | Triage edit without request change → re-explains |

---

#### R5-F1 — Ops — medium
**Anchor:** FR-12, "rides a synchronous transport (EventBus, or a contextcore A2A layer) **if/when one exists**" / NR-5 "No synchronous transport in v1"

**Finding:** NR-5 correctly defers synchronous A2A, but FR-12 already names EventBus as a future transport. SA and SCR **already emit** on EventBus in v1 with no blocking consumer — the OTel bridge is the subscriber. FDE requirements omit any emission obligation, so "transport-agnostic" never gets exercised and operators lack parity with SA/SCR signals.

**Suggestion:** Add to FR-12 (or a short FR-18 observability clause): "On successful explain or preflight, the FDE SHALL emit `FDE_EXPLAIN_COMPLETE` or `FDE_PREFLIGHT_COMPLETE` on `EventBus` with `{run_id, mode, report_path, cost_usd}` and SHALL activate `OTelEventBridge` (best-effort). NR-5 is not violated — emission is async/fire-and-forget." Cross-reference `EventType` registration in `events/types.py`.

**Expected impact:** Observability quick win. Validates the contract dict as the event payload before any future A2A layer.

---

#### R5-F2 — Validation — high
**Anchor:** FR-6, "every load-bearing claim tagged `OBSERVED (project)` or `MECHANISM (sdk)`" / FR-15(b) "composing the human-readable narrative"

**Finding:** FR-6 and FR-15(b) interact dangerously: the narrative step can restate mechanism as untagged prose ("Micro Prime used the template path") and violate Tekizai-Tekisho. R1-F10 proposed a post-hoc lint; that catches errors late. Requirements do not require **generation-time** separation of authority.

**Suggestion:** Add to FR-6: "Mechanism facts SHALL be rendered in pre-composed, source-labeled blocks produced without LLM authorship. The LLM narrative step (FR-15(b)) MAY only reference claim ids defined in those blocks and SHALL NOT introduce new mechanism assertions. Violations fail the compose step." Mirror in FR-15: "(b) is glue text only, not mechanism discovery."

**Expected impact:** Closes focus ask #5 enforceability gap. Pairs with plan R5-S2.

---

#### R5-F3 — Data — medium
**Anchor:** FR-5, "Supply SDK-mechanism authority" / §6 source-of-truth table / SA `RootCause.CROSS_FILE_CONTRACT` (`operational_actions.py:80`)

**Finding:** §6 maps tier, strategy, repair, model, language — but not **forward-manifest / disk contract compliance**, which is a distinct mechanism surface (`forward_manifest_validator.py`, Kaizen disk scoring). SA already maps `CROSS_FILE_CONTRACT` to operational actions. FDE explain mode has no FR-5 obligation to read `ContractViolation` / `DiskComplianceResult` when triage cites contract failures — leaving a hole for "why did review fail?" questions.

**Suggestion:** Extend §6 with a row: "Contract / disk compliance?" → `validate_disk_compliance()` / `prime-postmortem-report.json` `disk_compliance` section → explain: ARTIFACT. FR-5: "When `root_cause` ∈ {`cross_file_contract`, contract-adjacent SA causes}, the FDE SHALL cite forward-manifest validator output as `MECHANISM (sdk)`." Step 5 `sources.read_disk_compliance(output_dir, feature_id)`.

**Expected impact:** Functional quick win for a common failure class. Reuses existing validator — no new taxonomy (NR-6).

---

#### R5-F4 — Interfaces — medium
**Anchor:** FR-11, "markdown artifacts in `.startd8/fde/`" / FR-12 ".md files … are the serialized view"

**Finding:** FR-11 centers markdown; FR-12's durable interface is the dataclass/JSON pair. Without declaring precedence, implementers treat `.md` as authoritative and skip JSON — breaking idempotency parsing and EventBus payloads (R5-F1). R1-F4 remains open.

**Suggestion:** Amend FR-11: "The canonical serialized form SHALL be `fde-explanation.json` / `fde-preflight.json` (Keiyaku `.to_dict()`). The `.md` files are a **derived, human-readable view** (may be lossy; not round-tripped). `FdeRequest`/`FdeExplanation` parsers SHALL accept JSON; markdown parsing is optional convenience only."

**Expected impact:** Resolves R1-F4 without `from_markdown()` on the critical path. Enables machine consumers and Grafana JSON panels.

---

#### R5-F5 — Ops — medium
**Anchor:** FR-13, "idempotent per (request artifact + SDK version)" / Plan Step 10 `fde-cursor.json`

**Finding:** FR-13 keys idempotency on the **request** artifact only (per R1-F12). Explain consumes **triage JSON**, **post-mortem**, and optionally **prime-result** — any of which can change while `fde-request.md` is unchanged (SA re-run, post-mortem refresh). Skipping re-explain produces stale mechanism authority attached to fresh triage (FR-17 ref checksum mismatch risk).

**Suggestion:** Extend FR-13: "The idempotency fingerprint SHALL be `hash(fde-request.md) + hash(service-assistant-triage.json) + hash(prime-postmortem-report.json if present) + sdk_version`." Cursor records each component checksum separately for debugging. Partial cache hit re-runs only changed inputs.

**Expected impact:** Operational robustness when operators iterate SA without re-stamping the request. Low implementation cost (mirror SA cursor `run_id`+`checksum` pattern in `detector.py:229-235`).

---

**Endorsements:**
- R5-F4 implements R1-F4 (derived-only markdown) without requiring lossless `from_markdown()`.
- R2-F2 (`generation_strategy` gap) — R5-F3 disk row is orthogonal; both needed.
- R3-F1 (triage write-back) — checksum in R5-F5 must include post-write triage state.

**Disagreements:** none.

