# Multi-Model Consultation (TUI Workflow) — Requirements

**Version:** 0.4 (Post-CRP — R1+R2 triaged & applied)
**Date:** 2026-07-03
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Location of design set:** `docs/design/multi-model-consult/` (this doc + `PLAN.md`)

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> The planning pass (see `PLAN.md`) explored the agent/provider layer, the parallel-execution
> primitives, the persistence layer, and the TUI, and revealed the following corrections.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| "The SDK can already send images to models" | **False.** Image/multimodal input is entirely absent. `agenerate(prompt: str, ...)` is text-only on `BaseAgent` (`agents/base.py:215`) and every provider agent. "vision" exists only as static capability strings (`providers/anthropic.py:370`, `openai.py:305`, `gemini.py:334`). | Image support is now the **load-bearing infrastructure FR** (FR-MMC-2), not an assumed given. It needs three genuinely different per-provider payload adapters. |
| "Parallel fan-out must be built" | **Partly built.** `BenchmarkRunner.arun_benchmark` already fans out one prompt → N agents with real `asyncio.gather` concurrency (`benchmark.py:107-110`) and persists each result (`benchmark.py:91`). | FR-MMC-3 (parallel exec) narrows to *reuse* the gather pattern; error isolation is already handled via `return_exceptions=True`. |
| "Persisted responses can carry a conversation" | **False.** `AgentResponse` (`models.py:323`) stores only a single `response` string — **no messages/turns field**. The multi-turn model (`AgenticSession.messages`, `agentic.py:401`) is single-agent, in-memory, and never persisted. | FR-MMC-6/7 must define a **new persisted artifact** (a consultation session with per-model conversation arrays) rather than lean on `AgentResponse`. |
| "The follow-up 'one or all' UI is net-new" | **Mostly exists.** `step2_distribute_prompt` (`mixin_prompt_workflow.py:787-916`) already renders an ALL-vs-individual `questionary.select`; `agentic_chat.py` bridges async multi-turn replies into the sync questionary loop. | FR-MMC-8 (routing control) narrows to *composing* these patterns; reduces UI risk. |
| "Add it to the workflow entry-point registry" | The TUI does **not** consult `WorkflowRegistry`; it hand-wires concrete classes via mixins (`tui_improved.py:83-102`). | FR-MMC-9 specifies the mixin wiring path; entry-point registration becomes optional (OQ-2). |

**Resolved open questions:**
- **OQ-1 → Default roster = the "council" trio** (one Anthropic, one OpenAI, one Google model) drawn from `model_catalog.py`, user-overridable at run start. Rationale: mirrors the Summer2026 cross-vendor comparison intent without hardcoding.
- **OQ-3 → Cap at 2 images for v1** but store them as a list (`images: [...]`) so N-image is a config bump, not a schema change.
- **OQ-4 → New artifact, not an `AgentResponse` extension.** A `ConsultationSession` record with per-model conversation arrays (avoids overloading the benchmark response schema — see §0.1).
- **OQ-5 → Persist under `.startd8/consultations/<session-id>/`** (sibling to `responses/`, `benchmarks/`), one JSON per session + a `summary.md`.
- **OQ-7 → Non-vision models are excluded from the roster at selection time with a visible warning**, not silently errored mid-fan-out.

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted `Lessons_Learned/sdk/Design_Docs_LESSONS_LEARNED.md`, the SDK memory index, and
> `CLAUDE.md`. Applied lessons before CRP:

- **[Phantom-reference audit]** — every code symbol this doc names is grep-verified against the owning module; see §7 Reference Audit. No to-be-created symbol is cited as if it exists.
- **[Overloaded-term co-location]** — did **not** stack conversation state onto `AgentResponse`/the benchmark path (OQ-4). The new `ConsultationSession` concept gets its **own module + storage kind**, keeping the benchmark response schema single-meaning (see FR-MMC-6, NR-8).
- **[Bucket separation, `CLAUDE.md`]** — this workflow is a **model-skill comparison / consultation tool**, adjacent to the Summer2026 benchmark but explicitly NOT the deterministic codegen path and NOT a formal benchmark scorer (NR-1, NR-2). It generates *end-user advisory content* (bucket 4) — the SDK ships the harness, not the answer quality.
- **[Prune phantom scope]** — automated ranking/judging of model answers moved to a Non-Requirement (NR-2); evaluation is human-in-the-loop, consistent with `project_kaizen_value_model`.
- **[Single-source vocabulary ownership]** — provider image-payload shapes are owned by each provider agent module; this doc cites the call sites (§7) rather than restating payload JSON that could drift.
- **[CRP steering memory]** — least-reviewed artifact = this brand-new doc set; carried into the CRP focus file. Settled/do-not-relitigate: reuse of `arun_benchmark` gather pattern; human-only evaluation (NR-2); 2-image cap for v1.

*Checked lessons base; the five classes above applied. Ready for CRP review.*

---

## 1. Problem Statement

There is no way to pose a single question — **with supporting images** — to several LLMs at once,
keep every model's answer side-by-side, and then continue the conversation with either the whole
panel or one chosen model. The Summer2026 benchmark work fans prompts across models but is a
*scoring* harness (subprocess-isolated, one-shot, no images, no interactive follow-up). Users who
simply want a **multi-model second opinion** on a real problem — e.g. "here are two photos of my
broken door, help me open it" — have no first-class surface.

| Component | Current State | Gap |
|-----------|---------------|-----|
| Parallel one-prompt→N-model exec | Exists: `arun_benchmark` (`benchmark.py:107`), `asyncio.gather`, persists responses | Reusable, but one-shot and text-only |
| Image / multimodal input | **Absent** across all agents/providers | Must be built (FR-MMC-2) |
| Per-model conversation persistence | `AgentResponse` has no messages field; `AgenticSession` is single-agent, in-memory | New artifact needed (FR-MMC-6) |
| Follow-up "all or one" routing UI | Distribution select exists (`mixin_prompt_workflow.py:787`); async reply bridge exists (`agentic_chat.py`) | Compose into a consultation loop (FR-MMC-8) |
| Side-by-side comparison view | Partial (`_show_comparison`, `mixin_prompt_workflow.py:1026`) | Extend for image-grounded, multi-turn answers |

---

## 2. Goals & Non-Goals

**Goals**
- Send one prompt + up to 2 images to N models in parallel and persist every model's answer.
- Let the user read all answers side-by-side for human comparison/evaluation.
- Let the user send a follow-up prompt to **all** models or a **single** selected model, with
  each model's prior conversation preserved.
- First validated test case: the front-door-repair diagnostic (prompt + 2 images).

**Non-Goals** — see §6.

---

## 3. Requirements

### Core input
- **FR-MMC-1 — Prompt + image input.** The workflow accepts (a) a free-text prompt (multi-line)
  and (b) **up to 2 images**, specified either as explicit file paths or by pointing at a folder.
  Before any model call, each image is validated for:
  - **Existence + regular-file** (not a symlink, FIFO, or device node — see FR-MMC-14). *(R2-F1/F2)*
  - **Content/header (magic-byte) format** — the file is decoded, not trusted by extension; allowed
    formats are PNG/JPEG/WebP/GIF. A renamed HEIC, a truncated file, or a **multi-frame/animated**
    image is rejected pre-fan-out with a clear reason (v1 does not down-select a frame). *(R2-F2)*
  - **Size ceiling** — a concrete default of **≤ 5 MB and ≤ 8000 px on the long edge** per image;
    the effective cap is the **minimum across the selected providers' documented limits** (OQ-6),
    checked as a pre-flight so an oversized image is rejected before spending tokens on providers
    that would accept it. *(R1-F1, R1-S13)*
  - **Deterministic folder selection** — when a folder holds > 2 images, the chosen ≤ 2 are picked
    by a fixed rule (**lexicographic by filename, first 2**), and the *resolved chosen paths* are
    recorded in the session so the TUI and CLI select byte-identical images from the same folder
    (upholds the FR-MMC-13 no-fork guarantee). *(R2-F3, R1-S10)*
- **FR-MMC-2 — Multimodal agent support (enabling infra).** The agent/provider layer gains the
  ability to send images alongside a text prompt. `agenerate` accepts an optional `images`
  argument (list of in-flight `ImageInput` values); each provider agent renders images into its
  native shape: Anthropic base64 `source` blocks, OpenAI `image_url` data-URLs, Gemini inline
  `Part` bytes. A **shared pre-adapter** owns base64 encoding, mime sniffing, and size/count
  enforcement so the three per-provider adapters assemble *shape only* (no triplicated logic). *(R1-S1)*
  - **Scope (v1):** `images` is wired into **`agenerate` only**. The tool/structured-output
    (`agenerate_tools`) and streaming paths remain text-only in v1; this is an explicit boundary,
    not an oversight. *(R1-F7, R1-S3)*
  - **Byte-identity invariant:** when `images` is absent/empty, the **serialized request body handed
    to each provider client** is byte-identical to today's — measured at the emitted-payload
    boundary (golden-file diff of the mocked client's received body), not merely at the `agenerate`
    argument. *(R1-F2, R1-S2)*
  - **OpenAI dual call-site:** both OpenAI construction sites (`openai.py:214` and `openai.py:896`)
    must receive image parts; a guard test asserts neither path can send a vision-roster call
    without images. *(R2-F4→plan R2-S4)*
  - **FR-MMC-2a — Capability gating (best-effort, not a guarantee).** Models that do not advertise
    `vision` capability are excluded from a roster at selection time with a visible warning. This is
    a **static** gate and cannot prevent every mid-run failure: a statically vision-capable model
    may still return a run-time image-unsupported/entitlement error, which is **recorded as a
    per-model error per FR-MMC-11**, never a crash. *(R1-F9, R1-S11)*

### Fan-out & persistence
- **FR-MMC-3 — Parallel fan-out.** The prompt+images are sent to all selected models concurrently,
  reusing the `asyncio.gather(..., return_exceptions=True)` pattern so one model's failure does not
  abort the others. Failed models are recorded with their error, not dropped silently.
- **FR-MMC-4 — Roster selection.** At run start the user selects the target models. A default
  cross-vendor roster is offered (OQ-1 resolution) and is user-overridable. Only vision-capable
  models appear as selectable.
- **FR-MMC-5 — Cost tracking.** Every model call flows through the existing per-call cost hook
  (`_run_with_cost_tracking`, `base.py:388`) so consultation spend is attributed and visible,
  including the base64 image token cost, recorded **per model per turn** in the session and shown
  in the comparison view. *(R1-S9)*
  - **Failure/retry accounting:** image-input tokens are counted **exactly once**; a retried turn
    is not double-counted; a mid-fan-out failure is attributed per provider billing semantics
    (distinguish *billed-but-failed* from *zero-cost-failed*). Acceptance: a model 4xx'ing
    post-metering and a retried turn each produce exactly-once, correctly-signed cost entries.
    *(R2-F5, R2-S7)*
  - **Redaction:** image bytes / base64 and absolute image paths are excluded from persisted
    sessions **and** from cost/telemetry logs; only path-hash + mime + token counts are recorded.
    *(R1-F6)*
- **FR-MMC-6 — Persisted consultation session.** Each run persists a **`ConsultationSession`**
  artifact under `.startd8/consultations/<session-id>/` (a new artifact kind — it does not reuse or
  extend `AgentResponse`, §0.1/NR-8). Schema (typed, JSON-round-trippable): *(R1-F3, R1-S4)*

  | Field | Type | Req? | Notes |
  |-------|------|------|-------|
  | `id` | str (session-id, FR-MMC-13a) | yes | process-unique; == on-disk dir name |
  | `prompt` | str | yes | initial turn's user text |
  | `images` | `list[ImageRef]` | yes | **persisted** refs — path + content-hash + mime, **no bytes** |
  | `roster` | `list[model_id]` | yes | vision-capable models selected |
  | `turns_by_model` | `dict[model_id, list[Turn]]` | yes | independent per-model threads |
  | `created_at` / `updated_at` | ts | yes | |

  A `Turn` carries `{role, text, images?: list[ImageRef], status, error?}` where `status ∈
  {pending, ok, failed, skipped-non-vision}` and `error` is a **structured** provider error
  (`type` + `status/code`), not a flattened string, so retry / cost / history logic can branch on
  code rather than parse prose. *(R1-F4, R1-S5, R1-S8, R2-S8)*

  `ImageRef` (persisted) is a **distinct type** from the in-flight `ImageInput` (which holds bytes);
  `ImageRef` has no bytes field. *(R1-S4)*
  - **FR-MMC-6a — Image reference persistence + integrity.** Persisted records reference images by
    resolved path + content hash (+ optional copied-in thumbnail), never full base64 in JSON. On a
    follow-up that re-sends visual context, the stored **content hash is re-validated** against the
    on-disk file; a mismatch or missing file **fails loud** (never silently sends different bytes
    than the audit trail claims). *(R1-F10, R1-S12)*
- **FR-MMC-7 — Per-model conversation continuity.** Each model's prior turns are retained and
  replayed on follow-up so a reply to a single model continues *that model's* thread, and a reply
  to all models continues each thread independently and in parallel. A thread whose last turn is a
  recorded **error** replays only its prior *valid* turns — the retry never sends a malformed
  history (e.g. an empty-assistant turn) to the provider. *(R1-F4, R1-S8)*

### Interaction (TUI)
- **FR-MMC-8 — Follow-up routing control.** After the initial fan-out, the user can enter a
  follow-up prompt and choose a routing target: **ALL models** (re-fan-out, each with its own
  history) or **a single selected model**. This composes the existing distribution-select
  (`mixin_prompt_workflow.py:787`) and async-reply bridge (`agentic_chat.py`) patterns.
  Follow-up turns may include new images (subject to FR-MMC-1 limits) but are not required to.
- **FR-MMC-9 — TUI integration.** The workflow is reachable from `startd8 tui` as a new menu
  entry, implemented as a `tui/mixin_*.py` mixin registered on `ImprovedTUI`
  (`tui_improved.py:83-102`), with a menu label + dispatch branch, following the multi-step shape
  of `iterative_workflow_menu` (`mixin_iterative_workflow.py:6`).
- **FR-MMC-10 — Comparison view.** The user can view all models' answers side-by-side for a given
  turn (human comparison/evaluation), extending the existing `_show_comparison`
  (`mixin_prompt_workflow.py:1026`) pattern to be image-grounded and turn-aware.

### Robustness
- **FR-MMC-11 — Partial-failure resilience.** A consultation with some models failing still
  persists a valid session. **Retry acceptance:** a follow-up routed to `all` or to a failed model
  re-invokes **only the models needing retry** (it does not re-run already-succeeded models) and
  records the new per-turn outcome. Acceptance: a 3-model run with 1 failure, then a retry, updates
  only the failed model. *(R1-F5)*
- **FR-MMC-12 — Resumability (nice-to-have, may defer).** A persisted session can be re-opened
  from the TUI to continue the conversation later.
- **FR-MMC-13 — `startd8 consult` CLI (OQ-2 resolution).** A thin CLI command runs a consultation
  headlessly: takes a prompt (arg or `--prompt-file`), up to 2 `--image` paths **or** `--image-dir`,
  and a `--models` roster; performs the same parallel fan-out and persists the same
  `ConsultationSession` artifact as the TUI. Follow-up turns via `--session <id> --to all|<model>`.
  The CLI is a wrapper over the same session/fan-out core as the TUI (**no logic fork** — enforced
  by a shared §4 golden-session fixture, R1-S10).
  - `--image` and `--image-dir` are **mutually exclusive** (error if both given); the directory
    scan is **bounded** (max entries examined) so a huge/special-file directory cannot hang the CLI
    before validation. *(R2-F6, R2-S9)*
- **FR-MMC-13a — Session-id contract.** The session id is **process-unique** (includes a
  pid/random component in addition to a sortable timestamp component, e.g. `ULID`- or
  `<ts>-<slug>-<rand>`-style) and is a stable, documented, user-facing token (CLI `--session`).
  Session-dir creation is **exclusive (`mkdir`-style), fail-loud on collision** — never a silent
  overwrite — so the concurrent CLI+TUI writers introduced by FR-MMC-13 cannot clobber each other.
  Resolves OQ-8. *(R1-F8 + R2-F1 refinement, R1-S7, R2-S6)*

### Security
- **FR-MMC-14 — Image path trust boundary.** Folder-pick and `--image-dir`/`--image` inputs are
  treated as an **untrusted path boundary**: paths are canonicalized to an absolute real path;
  `..` traversal and **symlinked** entries are rejected/skipped; only **regular files** are eligible
  for selection (no FIFO/device/special files). This matters because the tool base64-embeds the
  bytes and transmits them to three external providers. *(R2-F1, R2-S1, R2-S9)*

---

## 4. First Test Case (Acceptance Scenario)

Prompt (verbatim intent): *"My front door is broken. Look at these 2 images … the first is the
front of the door … push down on the handle and (unlocked) it opens, but not anymore. The second
shows the inside with the knob removed; I can't turn the knob from the inside either even though
it's unlocked. Help me fix it — first help me open the door so I can access the inner workings."*

Images: two files under `/Users/neilyashinsky/Documents/dev/benchmarking/Summer2026/docs/images`.

**Pass criteria:**
1. All roster models receive the prompt + both images and return an answer (or a recorded error).
2. Every model's answer is persisted and viewable side-by-side.
3. A follow-up clarification ("the latch won't retract — what tool do I need?") can be sent to
   **all** models or to **one** chosen model, and each targeted model's answer reflects the prior
   turn's context.

---

## 5. Non-Requirements

- **NR-1 — Not a benchmark scorer.** This is inspired by, but not part of, the Summer2026 benchmark;
  it produces no scores, no rankings, no leaderboard, and is not wired into `benchmark_matrix/`.
- **NR-2 — No automated judging/ranking of answers.** Evaluation is human-in-the-loop
  (`project_kaizen_value_model`). An automated "which answer is best" judge is explicitly deferred.
- **NR-3 — No new providers.** Uses the existing Anthropic/OpenAI/Gemini agents only.
- **NR-4 — Image input only, no image generation.**
- **NR-5 — Does not touch the deterministic $0 codegen path** (`backend_codegen`, etc.).
- **NR-6 — No streaming rendering in v1** (batch answers under a progress spinner is acceptable;
  streaming is a later enhancement).
- **NR-7 — No cloud sync / sharing;** sessions are local under `.startd8/`.
- **NR-8 — Does not overload `AgentResponse` / the benchmark response schema** with conversation
  state (§0.1); the consultation session is its own artifact kind.
- **NR-9 — Provider SDK version obligation (not "no new providers").** Distinct from NR-3: the
  three vision payload shapes (Anthropic image blocks, OpenAI `image_url`, Gemini `Part`) are tied
  to specific installed-SDK versions. v1 **pins** the provider SDK versions it builds vision
  payloads against and carries a **per-provider contract test** that fails loudly when the installed
  SDK's expected field/shape drifts (temporal drift — e.g. `media_type`→`mime_type`,
  `Part.from_bytes` signature change). This is an obligation the doc records, not a promise that no
  drift can occur. *(R2-F4, R2-S5)*

---

## 6. Open Questions

- **OQ-2 → RESOLVED (2026-07-03): TUI + a `startd8 consult` CLI in v1.** The TUI is the primary
  surface (FR-MMC-9); a thin `startd8 consult` CLI wrapper ships in the same increment for
  scripted/headless runs (new FR-MMC-13). A `startd8.workflows` entry point stays deferred (M4).
- **OQ-6 → PARTIALLY RESOLVED.** FR-MMC-1 now sets a concrete default ceiling (≤5 MB / ≤8000 px)
  and a min-across-providers pre-flight; the **remaining open** piece is whether to *auto-downscale*
  (vs reject) oversized images — deferred to M4 (needs per-provider limit tables + a downscale
  policy). *(R1-S13)*
- **OQ-8 → RESOLVED by FR-MMC-13a** (process-unique id + `mkdir`-exclusive creation, covering the
  cross-surface CLI+TUI case).
- **OQ-9 — Roster persistence.** Should the chosen roster be remembered across runs (a saved
  "council" preset)?
- **OQ-10 — Follow-up image accumulation.** When a follow-up adds images, do they replace or
  append to the visual context sent to the model? (Providers differ on cost/limits.)

---

## 7. Reference Audit (verified symbols)

Every code symbol cited in this doc, grep-verified against the owning module at draft time:

| Symbol / path | Location | Role |
|---------------|----------|------|
| `BaseAgent.agenerate(prompt: str, ...)` | `agents/base.py:215` | text-only generate; image kwarg to be added (FR-MMC-2) |
| `_run_with_cost_tracking` | `agents/base.py:388` | per-call cost hook (FR-MMC-5) |
| `BenchmarkRunner.arun_benchmark` | `benchmark.py:29,107` | parallel fan-out to reuse (FR-MMC-3) |
| `save_response` → `.startd8/responses/` | `benchmark.py:91`, `storage/backend.py:160` | existing persistence precedent |
| `AgentResponse` (no messages field) | `models.py:323` | why a new artifact is needed (NR-8) |
| `AgenticSession.messages` / `.send()` | `agents/agentic.py:401,407` | in-memory multi-turn model to mirror (FR-MMC-7) |
| provider image payload sites (Anthropic/OpenAI/Gemini) | `agents/claude.py:314`, `agents/openai.py:214/896`, `agents/gemini.py:226` | three distinct adapters (FR-MMC-2) |
| capability "vision" strings | `providers/anthropic.py:370`, `openai.py:305`, `gemini.py:334` | gating source (FR-MMC-2a) |
| `ImprovedTUI` mixin registration | `tui_improved.py:83-102` | how to wire the new workflow (FR-MMC-9) |
| `iterative_workflow_menu` (multi-step shape) | `tui/mixin_iterative_workflow.py:6` | UX template |
| `step2_distribute_prompt` (all-or-one select) | `tui/mixin_prompt_workflow.py:787` | routing-control template (FR-MMC-8) |
| `make_chat_session` / `reply` async bridge | `tui/agentic_chat.py:39,54` | sync↔async follow-up bridge |
| `_show_comparison` | `tui/mixin_prompt_workflow.py:1026` | comparison-view template (FR-MMC-10) |

*To-be-created (do not exist yet):* `ConsultationSession` artifact/module, `.startd8/consultations/`
storage kind, the `images` kwarg on `agenerate`, the per-provider image adapters, and the new TUI
mixin. All are explicitly marked as net-new in the FRs.

---

*v0.4 — Post-CRP. Reflective loop v0.1→v0.3, then a 2-round Convergent Review (R1+R2, reviewer
`claude-opus-4-8-1m`): all 16 requirements F-suggestions ACCEPTED (several consolidated). Added
FR-MMC-13a (session-id), FR-MMC-14 (path trust boundary), NR-9 (provider SDK version obligation);
hardened FR-MMC-1/-2/-2a/-5/-6/-6a/-7/-11/-13; resolved OQ-8 and partially OQ-6. Dispositions in
Appendix A.*

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

> **Triage summary (2026-07-03, orchestrator):** R1+R2 converged strongly (R2 endorsed 10 R1 items;
> its only "disagreements" were *strengthenings* of R1-F8/R1-S7, folded into FR-MMC-13a). All
> requirements-level suggestions ACCEPTED; none rejected. IDs prefixed `R1-F*`/`R2-F*` are the
> requirements review; the parallel `R*-S*` (plan) dispositions live in `PLAN.md` Appendix A.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Concrete size ceiling + provider-awareness | R1 | FR-MMC-1: ≤5 MB/≤8000 px default, min-across-providers pre-flight | 2026-07-03 |
| R1-F2 | Byte-identity = serialized request body | R1 | FR-MMC-2 byte-identity invariant bullet (golden-file on emitted body) | 2026-07-03 |
| R1-F3 | `ConsultationSession` schema table + distinct `ImageRef` | R1 | FR-MMC-6 schema table + `ImageRef` (no bytes) | 2026-07-03 |
| R1-F4 | Per-turn state enum + errored-turn history | R1 | FR-MMC-6 `Turn.status`, FR-MMC-7 valid-turn replay | 2026-07-03 |
| R1-F5 | Retry acceptance criterion | R1 | FR-MMC-11 retry-only-failed acceptance | 2026-07-03 |
| R1-F6 | Redact bytes/paths from logs | R1 | FR-MMC-5 redaction bullet | 2026-07-03 |
| R1-F7 | `images` = `agenerate`-only scope | R1 | FR-MMC-2 scope bullet (tools/streaming text-only v1) | 2026-07-03 |
| R1-F8 | Pin `--session` id format | R1 | Folded into FR-MMC-13a (+ R2 process-unique strengthening) | 2026-07-03 |
| R1-F9 | Soften static vision gate | R1 | FR-MMC-2a "best-effort, not a guarantee" | 2026-07-03 |
| R1-F10 | Re-validate hash on moved/changed image | R1 | FR-MMC-6a integrity/fail-loud | 2026-07-03 |
| R2-F1 | Folder/`--image-dir` trust boundary | R2 | New FR-MMC-14 | 2026-07-03 |
| R2-F2 | Magic-byte content validation + multi-frame | R2 | FR-MMC-1 content/header bullet | 2026-07-03 |
| R2-F3 | Deterministic folder selection | R2 | FR-MMC-1 lexicographic-first-2 + record chosen paths | 2026-07-03 |
| R2-F4 | SDK version pin + drift guard | R2 | New NR-9 | 2026-07-03 |
| R2-F5 | Cost under partial failure/retry | R2 | FR-MMC-5 failure/retry accounting bullet | 2026-07-03 |
| R2-F6 | `--image`/`--image-dir` exclusivity + bounded scan | R2 | FR-MMC-13 bullet | 2026-07-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | R1+R2 were high-signal and fully accepted; R2's two "disagreements" were accepted as *refinements* (FR-MMC-13a), not rejections. | 2026-07-03 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-03 21:51:44 UTC

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-03 21:51:44 UTC
- **Scope**: First external review of the requirements; testability/ambiguity of the sponsor-weighted areas — multimodal adapter contract (FR-MMC-2), ConsultationSession schema + concurrency (FR-MMC-6/-6a, OQ-8), per-model continuity under partial failure (FR-MMC-7/-11), base64 image cost (FR-MMC-5, OQ-6).

**Executive summary (top risks / gaps):**
- FR-MMC-1's "per-image size ceiling" has no numeric value and no per-provider awareness — untestable as written and in tension with OQ-6.
- FR-MMC-2's byte-identity claim ("Text-only calls remain byte-identical") lacks a defined measurement boundary (argument vs emitted request).
- FR-MMC-6's `ConsultationSession` lists fields in prose but has no schema table; `ImageRef` (persisted) vs the in-flight image type are not distinguished.
- FR-MMC-11 ("re-tryable on a subsequent turn") has no acceptance criterion and depends on a per-turn status shape the doc doesn't define.
- FR-MMC-6a + OQ-10 interact: a follow-up that re-sends visual context by path+hash has undefined behavior if the file changed/moved.
- FR-MMC-2a's "vision capability" is a static string; the requirement implies it *prevents* mid-run failure, which a static gate cannot guarantee.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | FR-MMC-1: replace "a per-image size ceiling" with a concrete default (e.g. bytes and max dimensions) and state whether the ceiling is a single local cap or the minimum across selected providers' limits (cross-ref OQ-6). | As written ("a per-image size ceiling") the requirement is untestable — no number, no provider-awareness — and silently conflicts with OQ-6's per-provider transport limits. | §3 FR-MMC-1 | Acceptance: an image at ceiling+1 byte is rejected before any model call; documented default value present. |
| R1-F2 | Interfaces | high | FR-MMC-2: define the measurement boundary for "Text-only calls remain byte-identical in behavior when `images` is absent/empty" — specify it is the *serialized request body* handed to each provider client, not just the `agenerate` argument. | "byte-identical in behavior" is ambiguous; an implementer can satisfy it at the argument level while the emitted request changes (e.g. Anthropic string-vs-list `content`). Ambiguity defeats the invariant's purpose. | §3 FR-MMC-2 (final sentence) | Golden-file test on the mocked client's received body, asserted equal pre/post-change. |
| R1-F3 | Data | high | FR-MMC-6: add a schema table for `ConsultationSession` (field, type, required?) and introduce a distinct persisted `ImageRef` type (path + hash + mime, no bytes) separate from the in-flight image value. | The record is described only in prose ("the prompt, image references, the roster, and a per-model conversation array"); without a typed schema, FR-MMC-6a's "no base64 in JSON" rule can't be verified and `ImageRef` vs in-flight bytes blur. | §3 FR-MMC-6 (new sub-table) | Schema/round-trip test: serialized session contains no base64; `ImageRef` has no bytes field. |
| R1-F4 | Data | high | FR-MMC-7 / FR-MMC-11: define per-model, per-turn state (e.g. `pending`/`ok`/`failed` + `last_error`) so "each model's prior turns are retained and replayed" and "re-tryable on a subsequent turn" have a concrete data contract. Specify how an errored turn appears in replayed history. | FR-MMC-7 and -11 jointly require distinguishing "failed this turn, has prior turns" from "never succeeded," and require that replaying a thread ending in an error not send a malformed (empty-assistant) history to the provider. Neither is specified. | §3 FR-MMC-7 and FR-MMC-11 | Test: model fails turn 1, succeeds turn 2; both persist and are individually addressable; retried history is a provider-valid message sequence. |
| R1-F5 | Validation | medium | FR-MMC-11: add an explicit acceptance criterion for "re-tryable" — a follow-up routed to `all` or to the failed model re-invokes only the models needing retry and records the new outcome. | "The failed models are re-tryable on a subsequent turn" states a capability with no verifiable criterion (what does a retry target, does it re-run succeeded models?). | §3 FR-MMC-11 | Acceptance step added to §4 or FR-MMC-11: a 3-model run with 1 failure, then a retry updates only the failed model. |
| R1-F6 | Security | medium | FR-MMC-5 / FR-MMC-6a: state that image bytes and any base64 are excluded from persisted sessions *and* from cost/telemetry logs, and that only path+hash+token-count are recorded. | The reqs forbid base64 in `session.json` (FR-MMC-6a) but say nothing about logs; the cost hook (FR-MMC-5) and any OTel path could leak image bytes/paths. Local-only (NR-7) reduces but does not remove the concern. | §3 FR-MMC-5 / FR-MMC-6a | Grep/redaction test: no base64 or absolute image path in emitted logs; only hash + token counts. |
| R1-F7 | Interfaces | medium | FR-MMC-2: state whether the `images` argument is supported on `agenerate` only, or also on tool/structured-output/streaming paths; if v1 is `agenerate`-only, say so as an explicit boundary. | The FR says "`agenerate` accepts an optional `images` argument" but the SDK has other call paths (tools, structured, streaming/NR-6); silence creates a coverage ambiguity and a possible SDK-shape mismatch for vision+tools. | §3 FR-MMC-2 | Doc note reviewed; grep test asserts `images` not wired into non-`agenerate` paths in v1. |
| R1-F8 | Interfaces | medium | FR-MMC-13: pin the `--session <id>` id format in the requirement (cross-ref OQ-8) since the CLI follow-up contract is a user-facing surface that depends on the id scheme. | FR-MMC-13 exposes `--session <id>` to users while OQ-8 leaves the id scheme open; a user-facing contract cannot depend on an unresolved OQ. | §3 FR-MMC-13 + §6 OQ-8 | Verify a documented, stable id format; CLI accepts the id emitted by a prior run. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Risks | medium | FR-MMC-2a: soften the claim that non-vision models are "excluded... not silently errored mid-fan-out" to acknowledge that a *statically* vision-capable model can still fail a real image at run time; require that such run-time refusals be recorded per FR-MMC-11 rather than implying they cannot occur. | The requirement's phrasing implies the static gate prevents mid-run vision failures; it cannot (per-variant/per-account entitlement), so the doc over-promises and lacks a fallback contract. | §3 FR-MMC-2a | Test: a "vision" model returns a run-time image-unsupported error → recorded as a per-model error, not a crash. |
| R1-F10 | Data | medium | FR-MMC-6a + OQ-10: specify follow-up image behavior when a referenced file has changed/moved since the initial turn — re-validate the stored content hash and fail-loud on mismatch (do not silently send a different image). | Because images are stored by path+hash and not re-embedded, an append-mode follow-up (OQ-10) can send different bytes than the audit trail claims, or crash on a missing file. This is a correctness/auditability hole in the "reproducible/auditable" promise. | §3 FR-MMC-6a + §6 OQ-10 | Test: mutate the on-disk image between turns → hash-mismatch detected and surfaced; missing file fails loudly. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — R1 is the first round)

**Disagreements** (untriaged prior items this reviewer would flag):
- (none — R1 is the first round)

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-03 UTC

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-03 UTC
- **Scope**: Second requirements pass. R1 hardened numeric ceilings, byte-identity boundary, the ConsultationSession schema, per-turn state, retry criteria, log redaction, `agenerate`-only scoping, id-format pin, and runtime-vision-refusal. R2 targets requirement gaps R1 did **not** raise: the `--image-dir`/folder trust boundary as a *requirement*, image **content**-vs-extension validation and multi-frame formats, deterministic folder selection, provider SDK-version drift as a stated constraint, and cost/attribution semantics on partial failure. No R1 F-item re-proposed; settled list respected.

**Executive summary (top gaps):**
- FR-MMC-1 names format + size validation but not a **content/header** check nor a rule for *which* 2 files a folder yields — both untestable/nondeterministic as written.
- No requirement governs the **folder/`--image-dir` path as a trust boundary** (traversal, symlink, non-regular files) even though FR-MMC-13 exposes `--image-dir` to shell users.
- FR-MMC-2's per-provider payloads are pinned to specific SDK versions, but no requirement or NR states a **version-pin/drift** obligation (NR-3 only bars *new* providers).
- FR-MMC-5 has no acceptance criterion for cost under **partial failure / retry** (double-count, billed-but-failed).
- Animated GIF / WebP variants are in the allow-list without a single-frame or size-behavior rule; providers differ.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Security | high | FR-MMC-1 / FR-MMC-13: add a requirement that folder / `--image-dir` inputs are treated as an untrusted path boundary — paths are canonicalized, `..` traversal and symlinked entries are rejected/skipped, and only regular files are eligible for selection. | FR-MMC-1 accepts "a folder from which up to 2 images are selected" and FR-MMC-13 exposes `--image-dir` to shell users, but no requirement constrains what those paths may resolve to; the tool then base64-embeds and transmits the bytes to three external providers. | §3 FR-MMC-1 (new sub-bullet) + FR-MMC-13 | Acceptance: a symlink-to-`/etc/passwd` and a `../` path in `--image-dir` are rejected/skipped; only regular files under the resolved root are selectable. |
| R2-F2 | Validation | high | FR-MMC-1: require **content/header (magic-byte) validation**, not extension-only, and state behavior for **multi-frame/animated** inputs (reject, or define single-frame selection) — the PNG/JPEG/WebP/GIF allow-list must be verified by decoding. | "readable format (PNG/JPEG/WebP/GIF)" is satisfiable by extension alone; a renamed HEIC, a truncated JPEG, or an animated GIF passes the stated check but fails differently at each provider — violating "validated ... before any model call." | §3 FR-MMC-1 | Test: renamed-HEIC-as-.png, truncated JPEG, and animated GIF are each rejected pre-fan-out with a clear reason. |
| R2-F3 | Data | medium | FR-MMC-1: specify a **deterministic selection rule** for which ≤2 images a folder yields (e.g. lexicographic, first 2) and require the chosen paths be recorded in the session. | "up to 2 images are selected" is nondeterministic; TUI and CLI (FR-MMC-13, "same core / no logic fork") can select *different* images from the same folder, contradicting the no-fork guarantee and auditability (FR-MMC-6a). | §3 FR-MMC-1 + FR-MMC-13 | Test: a 5-image folder yields the same 2 hashes from TUI and CLI code paths. |
| R2-F4 | Ops | medium | Add a requirement (or NR) that per-provider image payload construction is **pinned to a declared SDK/API version** with a drift/contract check, distinct from NR-3's "no new providers." | FR-MMC-2's three shapes (Anthropic image blocks, OpenAI `image_url`, Gemini `Part`) are SDK-version-specific; a minor bump of an *existing* provider SDK (field rename, `Part` API change) breaks vision at runtime, and NR-3 does not cover version bumps. | §3 FR-MMC-2 or §5 (new NR) | Contract test per provider asserting the built block matches the pinned SDK's schema; CI fails on drift. |
| R2-F5 | Validation | medium | FR-MMC-5: add an acceptance criterion for cost under **partial failure and retry** — image-input tokens counted exactly once, a retried turn not double-counted, and a mid-fan-out failure attributed per provider billing semantics (billed-but-failed vs zero-cost-failed). | FR-MMC-5 says spend is "attributed and visible, including the base64 image token cost," but is silent on the failure/retry path where double-counting or lost image spend is most likely (interacts with FR-MMC-11 retry). | §3 FR-MMC-5 | Test: a model 4xx'ing post-metering and a retried turn each produce exactly-once, correctly-signed cost entries. |
| R2-F6 | Interfaces | low | FR-MMC-13: require `--image-dir` and `--image` to be **mutually-exclusive or precedence-defined**, and bound the directory scan (max entries) so a huge/special-file directory cannot hang the CLI. | FR-MMC-13 offers both "`--image` paths (or `--image-dir`)" without stating precedence when both are given, and an unbounded folder scan on a device node/FIFO or 10⁶-entry dir can hang before validation. | §3 FR-MMC-13 | Test: `--image` + `--image-dir` together resolves per documented precedence; a FIFO/large dir returns promptly without blocking. |

**Endorsements** (prior untriaged R1 F-suggestions this reviewer agrees with):
- R1-F1: numeric size ceiling + provider-awareness is the base R2-F2/F3 build on.
- R1-F3: the typed `ConsultationSession`/`ImageRef` schema is the precondition for recording the selected paths (R2-F3) and hashes.
- R1-F4: per-turn state + errored-turn history is required for the retry-cost semantics in R2-F5.
- R1-F6: log/telemetry redaction; R2-F1's canonicalized-path handling should feed the same redaction rule (record hash, not the resolved absolute path).
- R1-F9 / R1-F10: runtime vision-refusal and moved/mutated-image hazard; R2-F5 and R2-F2 sharpen the same failure surfaces.

**Disagreements** (untriaged prior R1 F-items this reviewer would flag):
- R1-F8 (partial): pinning the `--session <id>` *format* is necessary but insufficient — the requirement should also state the id is **process-unique** so it survives the concurrent CLI+TUI writers FR-MMC-13 introduces (see PLAN R2-S6); format-only leaves a cross-surface collision hole.
