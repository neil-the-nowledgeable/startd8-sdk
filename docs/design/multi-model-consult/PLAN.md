# Multi-Model Consultation (TUI Workflow) — Implementation Plan

**Version:** 1.1 (Post-CRP — R1+R2 applied; see §E)
**Date:** 2026-07-03
**Status:** Draft — pairs with `REQUIREMENTS.md` v0.3
**Pre-condition (standing rule):** requirements built/refined via the reflective loop before code.

---

## A. Discoveries (what planning revealed)

| Requirements assumed | Planning revealed | Consequence |
|----------------------|-------------------|-------------|
| Images already sendable | No image path anywhere; `agenerate(prompt: str)` text-only | Milestone M1 = build multimodal support first (blocks everything) |
| Fan-out is net-new | `arun_benchmark` already gathers N agents w/ `return_exceptions=True` | Reuse; don't rebuild concurrency |
| Reuse `AgentResponse` for turns | No messages field; schema is benchmark-owned | New `ConsultationSession` artifact + storage kind |
| Routing UI is net-new | ALL-or-one select + async reply bridge exist | Compose existing TUI patterns |
| TUI reads workflow registry | TUI hand-wires mixins | Wire via `mixin_*.py`, not entry points |

The image gap makes this a **layered** build: infra (multimodal) → orchestration (session +
fan-out) → UI (TUI mixin). >30% of v0.1 assumptions were wrong (mostly the image assumption and the
persistence-schema assumption) — the loop paid for itself.

---

## B. Milestones

### M0 — Design lock (this doc set)
- REQUIREMENTS v0.3 + PLAN v1.0. Offer CRP before M1.

### M1 — Multimodal agent support (FR-MMC-2, -2a) — the enabling layer
1. Define an internal `ImageInput` value (path or bytes + mime + content-hash). Small dataclass in
   a new `agents/multimodal.py`; keep it provider-neutral.
2. Add optional `images: list[ImageInput] | None = None` to `BaseAgent.agenerate` (`base.py:215`)
   and thread through `TrackedAgent.agenerate` (already `**kwargs`, `tracked.py:159`).
3. Per-provider adapters (three genuinely different payloads):
   - **Anthropic** — build `content` block list at `claude.py:314-316`: text block + image blocks
     `{"type":"image","source":{"type":"base64","media_type":...,"data":...}}`.
   - **OpenAI** — parts array at `openai.py:214` & `openai.py:896`:
     `{"type":"image_url","image_url":{"url":"data:...;base64,..."}}`.
   - **Gemini** — `contents` parts list at `gemini.py:226`: text + inline `Part` bytes w/ mime.
4. **Invariant:** when `images` is falsy, the constructed payload is byte-identical to today
   (regression guard test per provider).
5. Capability gate helper: read the `vision` capability flags (`anthropic.py:370`, `openai.py:305`,
   `gemini.py:334`) to answer "is model M vision-capable?" (FR-MMC-2a).
6. Tests: per-provider payload-shape unit tests (mocked clients) + text-only byte-identity tests.

### M2 — Consultation session model + storage (FR-MMC-6, -6a, -7, -11)
1. `ConsultationSession` Pydantic model (new module, e.g. `consultation/models.py`): `id`, `prompt`,
   `images: list[ImageRef]`, `roster`, `turns_by_model: dict[model_id, list[Turn]]`, timestamps,
   per-model status/error.
2. Storage: add a `consultations/` kind under the FileSystemStorage layout (mirrors
   `responses/`/`benchmarks/`, `storage/backend.py:82`). One `session.json` + a `summary.md`
   per `<session-id>/`; images referenced by path+hash (+ optional copied thumbnail), FR-MMC-6a.
3. Fan-out driver: reuse the `asyncio.gather(..., return_exceptions=True)` shape from
   `benchmark.py:107` but over the consultation roster, threading each model's prior `turns` in as
   history (mirroring `AgenticSession.messages`, `agentic.py:401`). Failed models → recorded error
   (FR-MMC-11), others complete.
4. Follow-up routing at the model level: send to all (parallel gather) or one (single await), each
   continuing its own thread (FR-MMC-7).
5. Cost: ensure each call goes through `acreate_response`/`_run_with_cost_tracking` (`base.py:388`).

### M3 — TUI workflow (FR-MMC-1, -4, -8, -9, -10)
1. New `tui/mixin_consultation.py` (`from ._shared import *`), class `ConsultationMixin` with entry
   `consultation_menu()`, modeled on `iterative_workflow_menu` (`mixin_iterative_workflow.py:6`).
2. Register on `ImprovedTUI` base list (`tui_improved.py:83-102`); add a menu label under the right
   `questionary.Separator`; add an `elif "Consult" in choice:` dispatch branch (`run()`).
3. Steps: prompt entry (reuse `_get_text_or_file_input`) → image path/folder pick (≤2, validated,
   FR-MMC-1) → roster select (vision-only, default council, FR-MMC-4) → confirm → parallel run under
   `rich.progress` → comparison view (`_show_comparison` extension, FR-MMC-10).
4. Follow-up loop: routing select modeled on `step2_distribute_prompt` (`mixin_prompt_workflow.py:787`)
   — ALL vs single model — driven through the async bridge (`agentic_chat.py:54`). (FR-MMC-8)
5. Acceptance: run the §4 front-door test case end-to-end.

### M3.5 — `startd8 consult` CLI (FR-MMC-13, OQ-2 resolved: in v1)
1. Add a `consult` Typer command in `cli.py` (sibling to `tui`, `cli.py:724`): `--prompt`/
   `--prompt-file`, `--image` (≤2) / `--image-dir`, `--models`, and follow-up
   `--session <id> --to all|<model>`.
2. Wrap the **same** M2 session/fan-out core the TUI uses — no logic fork (FR-MMC-13). CLI renders
   a compact side-by-side/JSON summary; persists the identical `ConsultationSession` artifact.
3. Tests: one headless end-to-end run of the §4 front-door case with mocked agents.

### M4 — Optional (OQ-driven, may defer)
- `startd8.workflows` entry point registration (OQ-2 — deferred).
- Resumability from a persisted session (FR-MMC-12).
- Image downscaling / per-provider transport limits (OQ-6, OQ-10).
- Saved roster presets (OQ-9).

---

## C. Risks

- **Provider payload drift** — the three image shapes differ; a shared "just send bytes" abstraction
  would leak. Keep three thin per-provider adapters co-located with each `_make_api_call`.
- **Token cost of base64 images** — large images inflate input tokens; surface cost per model and
  consider downscaling (OQ-6). Don't persist full base64 in `session.json` (FR-MMC-6a).
- **Concurrency on `.startd8/consultations/`** — two TUI instances (OQ-8); use unique session ids +
  atomic writes (`storage/base.py:66`).
- **Text-only regression** — the `images` kwarg must not change existing text calls; byte-identity
  tests per provider (M1.4) are the guard.
- **Repo reality** — concurrent worktrees/agents; pin `PYTHONPATH=<wt>/src` for tests and branch
  from `origin/main` before building (`reference_multiworktree_env`).

---

## D. Traceability

| FR | Milestone(s) |
|----|--------------|
| FR-MMC-1 | M3.3 |
| FR-MMC-2 / -2a | M1 |
| FR-MMC-3 | M2.3 |
| FR-MMC-4 | M3.3 |
| FR-MMC-5 | M1/M2.5 |
| FR-MMC-6 / -6a | M2.1–M2.2 |
| FR-MMC-7 | M2.3–M2.4 |
| FR-MMC-8 | M3.4 |
| FR-MMC-9 | M3.1–M3.2 |
| FR-MMC-10 | M3.3 |
| FR-MMC-11 | M2.3 |
| FR-MMC-12 | M4 (deferred) |
| FR-MMC-13 | M3.5 |

---

## E. Post-CRP Hardening (v1.1 — R1+R2 applied)

Concrete plan sub-steps added by the Convergent Review (all S-suggestions ACCEPTED). Each is also
reflected in a hardened FR (see `REQUIREMENTS.md` v0.4 Appendix A).

**M1 — Multimodal:**
- **M1.1a Shared pre-adapter** (`agents/multimodal.py`): owns base64 encode, mime sniff (magic-byte,
  reject multi-frame), size/count enforcement, and the falsy-`images` short-circuit. The 3 provider
  adapters assemble *shape only*. *(R1-S1, R2-S3)*
- **M1.3 OpenAI dual site:** patch **both** `openai.py:214` and `openai.py:896`; guard test asserts
  neither entry point sends a vision-roster call without image parts. *(R2-S4)*
- **M1.4 Byte-identity as a golden-file property test** on the mocked client's *received body*
  (not the argument). *(R1-S2)*
- **M1.5 Pre-flight transport check** (per-provider min limit) + a mocked-4xx "image unsupported"
  test proving a runtime vision refusal is recorded, not crashed. *(R1-S11, R1-S13)*
- **M1.6 Provider SDK version pin + contract test** per provider (fail-loud on shape drift). *(R2-S5)*

**M2 — Session/storage:**
- **M2.1 State enum per turn** (`pending|ok|failed|skipped-non-vision`) + **structured** provider
  error (`type`+`code`, not a string). *(R1-S5, R2-S8)*
- **M2.2 Concurrency:** write `session.json.tmp` + `os.replace`; **exclusive `mkdir` session-dir
  creation**, fail-loud on collision; process-unique id (ts+slug+rand/ULID); guard the
  read-modify-write lost-update hazard on overlapping follow-ups (version/lock check). *(R1-S6, R1-S7, R2-S6)*
- **M2.3 Errored-turn history threading** — replay only prior valid turns; persist structured error;
  image hash re-validation on follow-up (fail-loud on mismatch/missing). *(R1-S8, R1-S12)*
- **M2.4 Follow-up ordering** — a `to=all` follow-up must not thread a model whose prior turn hasn't
  persisted (wait or fail-loud for that model). *(R2-S10)*
- **M2.5 Cost:** image tokens per-model-per-turn in the session + comparison view; exactly-once
  under retry; billed-vs-zero-cost-failed attribution. *(R1-S9, R2-S7)*

**M3 / M3.5 — TUI + CLI:**
- **M3.3 Path trust boundary** (canonicalize, reject `..`/symlink/non-regular) + **bounded** dir scan
  (reject FIFO/device, cap entries) + **deterministic** lexicographic-first-2 selection recording
  chosen paths. *(R2-S1, R2-S2, R2-S9)*
- **M3.5 No-fork proof:** the §4 front-door case is a **single shared fixture** driven by both TUI
  and CLI, asserting a byte-identical `ConsultationSession` (modulo id/timestamp). *(R1-S10)*
- **M3.5 `--image`/`--image-dir` mutual exclusion + precedence.** *(R2-F6)*

---

*v1.1 — Post-CRP (R1+R2, reviewer `claude-opus-4-8-1m`): all 23 plan S-suggestions accepted and
mapped into §E sub-steps. v1.0 reflected the reflective-loop planning pass; the image-input gap
remains the critical-path discovery — build order infra → session → UI.*

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

> **Triage summary (2026-07-03):** all 23 plan S-suggestions ACCEPTED and mapped into §E. R1 = 13
> (S1–S13), R2 = 10 (S1–S10). R2-S6/S7/S8 sharpen R1-S7/S8; R2's disagreement on R1-S7 (process-
> uniqueness) was accepted as a strengthening. No rejections.

| ID | Suggestion | Source | Mapped to | Date |
|----|------------|--------|-----------|------|
| R1-S1 | Shared pre-adapter (encode/validate/short-circuit) | R1 | §E M1.1a | 2026-07-03 |
| R1-S2 | Byte-identity property test on serialized body | R1 | §E M1.4 | 2026-07-03 |
| R1-S3 | `images` = `agenerate`-only scope | R1 | REQ FR-MMC-2 scope | 2026-07-03 |
| R1-S4 | `ImageInput` vs `ImageRef` distinct types | R1 | REQ FR-MMC-6 | 2026-07-03 |
| R1-S5 | Per-turn state enum | R1 | §E M2.1 | 2026-07-03 |
| R1-S6 | Atomic write + lost-update hazard | R1 | §E M2.2 | 2026-07-03 |
| R1-S7 | Pin session-id scheme | R1 | §E M2.2 / FR-MMC-13a | 2026-07-03 |
| R1-S8 | Errored-turn history threading | R1 | §E M2.3 | 2026-07-03 |
| R1-S9 | Image tokens per-model-per-turn, surfaced | R1 | §E M2.5 | 2026-07-03 |
| R1-S10 | Shared TUI+CLI golden-session fixture | R1 | §E M3.5 | 2026-07-03 |
| R1-S11 | Runtime vision-refusal 4xx case | R1 | §E M1.5 | 2026-07-03 |
| R1-S12 | Moved/deleted image hash re-validate | R1 | §E M2.3 | 2026-07-03 |
| R1-S13 | Pre-flight per-provider transport limit | R1 | §E M1.5 | 2026-07-03 |
| R2-S1 | `--image-dir` path trust boundary | R2 | §E M3.3 / FR-MMC-14 | 2026-07-03 |
| R2-S2 | Deterministic folder selection | R2 | §E M3.3 / FR-MMC-1 | 2026-07-03 |
| R2-S3 | Magic-byte content validation, multi-frame | R2 | §E M1.1a | 2026-07-03 |
| R2-S4 | Both OpenAI call sites + guard test | R2 | §E M1.3 | 2026-07-03 |
| R2-S5 | Provider SDK version pin + drift guard | R2 | §E M1.6 / NR-9 | 2026-07-03 |
| R2-S6 | Cross-surface process-unique id + `mkdir`-exclusive | R2 | §E M2.2 / FR-MMC-13a | 2026-07-03 |
| R2-S7 | Cost under partial failure/retry | R2 | §E M2.5 / FR-MMC-5 | 2026-07-03 |
| R2-S8 | Persist structured provider error | R2 | §E M2.1 | 2026-07-03 |
| R2-S9 | Bound dir scan, reject FIFO/device | R2 | §E M3.3 / FR-MMC-14 | 2026-07-03 |
| R2-S10 | Follow-up-to-all with in-flight prior turn | R2 | §E M2.4 | 2026-07-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | High-signal review; all accepted (R2 "disagreements" folded as refinements). | 2026-07-03 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-03 21:51:44 UTC

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-03 21:51:44 UTC
- **Scope**: First external review of the plan; sponsor-weighted toward multimodal adapter risk (M1/FR-MMC-2), session schema + `.startd8/consultations/` concurrency (M2/OQ-8), per-model continuity under partial failure (M2.3-2.4/FR-MMC-7,-11), and base64 image cost handling (M1/M2.5/OQ-6).

**Focus-file asks — direct answers (orchestrator triages later):**

- **Ask 1 — Is "thin per-provider adapter, no shared abstraction" (M1.3) right?**
  - **Summary answer:** Yes for payload *construction*, but a small shared *pre-adapter* stage is needed.
  - **Rationale:** The three shapes (Anthropic `source`/base64, OpenAI `image_url` data-URL, Gemini inline `Part` bytes) genuinely diverge at the wire, so a per-provider builder is correct (Risks §C "Provider payload drift"). But three concerns are *identical* across providers and will be silently re-implemented 3× if there is no shared step: (a) bytes→base64 + media-type detection, (b) the ≤2-image / size-ceiling enforcement (FR-MMC-1), (c) the byte-identity short-circuit when `images` is falsy (M1.4). Those belong in `agents/multimodal.py` (the `ImageInput` home, M1.1), leaving each adapter to do only shape assembly.
  - **Assumptions / conditions:** `ImageInput` carries decoded bytes + mime + hash so no adapter re-reads the file.
  - **Suggested improvements:** See R1-S1, R1-S2.
- **Ask 2 — How should `agenerate_tools` / structured paths interact?** (see R1-S3)
  - **Summary answer:** Out of scope for v1, but the plan must state that `images` is *not* threaded through `agenerate_tools`/structured-output paths, or M1.2 will imply it is.
- **Ask 3 — Is `turns_by_model` sufficient for continuity, and are atomic writes / two-instance collisions handled?** (see R1-S5, R1-S6, R1-S7)
  - **Summary answer:** Shape is sufficient; concurrency and write-atomicity are under-specified in M2.2.
- **Ask 4 — Does a failed model's thread stay resumable (FR-MMC-11)?** (see R1-S8)
  - **Summary answer:** Only if per-model status distinguishes "no turns yet" from "failed after a turn"; M2.1's flat `status/error` field does not.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | In M1, add a shared pre-adapter step in `agents/multimodal.py` that owns base64 encoding, media-type sniffing, size/count enforcement (FR-MMC-1), and the falsy-`images` short-circuit — so the three per-provider adapters (M1.3) assemble shape *only*. | The plan keeps three adapters "thin" but leaves encoding, validation, and the byte-identity guard implicit; without a shared stage each is re-implemented 3× and the byte-identity invariant (M1.4) is enforced in triplicate, inviting drift. | M1, new sub-step between M1.1 and M1.3 | Unit test: one `ImageInput`→base64 fixture consumed identically by all three adapters; mutation test that removing the short-circuit breaks exactly the byte-identity tests. |
| R1-S2 | Risks | high | State M1.4's byte-identity invariant as a property test over the *serialized request body* actually handed to each SDK/client, not just the `content`/`parts` argument — capture and diff the outgoing payload with `images=None` vs today. | "Byte-identical to today" is asserted at the argument level, but providers may wrap content differently (e.g. Anthropic string-vs-list `content`); a diff at the argument boundary can pass while the emitted request changes. | M1 step 4 (expand) + Risks §C "Text-only regression" | Golden-file test capturing the mocked client's received kwargs/body for a text-only call, asserted byte-equal pre/post-change. |
| R1-S3 | Interfaces | medium | Explicitly scope M1.2 so `images` is added to `agenerate` only, and record that `agenerate_tools` / structured-output / streaming paths are text-only in v1 (or enumerate which providers route vision through a different method). | M1.2 says "thread through" but only names `agenerate`/`TrackedAgent.agenerate`; an implementer may wire (or forget to wire) images into tool/structured calls, and some SDKs require a different call shape for vision + tools. Ambiguity here is a silent-coverage risk. | M1 step 2 (add scope note) + Risks §C | Grep test asserting no `images=` reaches `agenerate_tools`; doc note reviewed. |
| R1-S4 | Data | medium | Specify the `ImageInput`/`ImageRef` field contract in M1.1/M2.1 (required vs optional fields, hash algorithm, mime source of truth) and make `ImageRef` (persisted) a distinct type from `ImageInput` (in-flight bytes). | M1.1 (`path or bytes + mime + content-hash`) and M2.1 (`images: list[ImageRef]`) name two types with overlapping-but-different roles; conflating them risks persisting raw bytes into `session.json`, which §C explicitly forbids. | M1 step 1 + M2 step 1 | Schema test: `ConsultationSession` round-trips to JSON with no base64 payload; `ImageRef` has no `bytes` field. |
| R1-S5 | Data | high | M2.1: split the per-model field into an explicit state enum (`pending`/`ok`/`failed`/`skipped-non-vision`) plus a `last_error`, rather than a single `status/error`, and put it on each `turns_by_model` entry so state is per-turn, not per-session. | FR-MMC-11 (retry failed models on a later turn) and FR-MMC-7 (independent per-model threads) require distinguishing "failed this turn but has prior turns" from "never succeeded"; a flat per-model status cannot express partial-turn failure. | M2 step 1 | Unit test: a 3-model session where model B fails turn 1, succeeds turn 2 — assert B's turn-1 error and turn-2 answer both persist and are individually addressable. |
| R1-S6 | Data | high | M2.2: specify the atomic-write mechanism concretely (write `session.json.tmp` + `os.replace`) and state the read-modify-write hazard for follow-ups — each follow-up mutates an existing session, so a lost-update race exists even single-instance if two follow-ups overlap. | §C and OQ-8 mention "atomic writes" and cite `storage/base.py:66`, but the *follow-up* path is read-modify-write on the same `session.json`; atomic replace alone does not prevent lost updates without a version/lock check. | M2 step 2 + Risks §C "Concurrency" | Test: concurrent follow-ups to disjoint models on one session must both land (or one must fail-loud), never silently overwrite. |
| R1-S7 | Data | medium | M2.2: pin the session-id scheme now (recommend ULID or `timestamp-slug-<rand>`), since the id is the collision-avoidance primitive named in §C/OQ-8 and is baked into the on-disk path and CLI `--session <id>`. | OQ-8 leaves ULID-vs-timestamp open, but M2.2, M3.5, and FR-MMC-13 all already depend on the id shape; deferring it blocks the CLI follow-up contract. | M2 step 2 (resolve OQ-8 inline) | Assert generated ids are lexicographically sortable and collision-free across a tight loop + two processes. |
| R1-S8 | Risks | high | M2.3: define history-threading for a model that has a *recorded error* on its last turn — does its prior successful turns replay, is the errored turn included as context, and is the retry a new turn or a replacement? | FR-MMC-7/-11 interact: replaying a thread that ends in an assistant error could send a malformed history (assistant turn with no content) to the provider; the plan says "thread each model's prior turns" without saying how errored turns are represented in history. | M2 step 3 (expand) | Unit test: model with `[user, assistant(ok), user, assistant(error)]` → retry produces a valid message sequence the provider accepts (no empty assistant turn). |
| R1-S9 | Ops | medium | M2.5 / FR-MMC-5: state that image-input tokens are attributed *per model per turn* in the persisted session and surfaced in the comparison view, and note that providers report image tokens differently (some fold into prompt tokens). | The plan routes cost through `_run_with_cost_tracking` but does not say the image-token cost is *recorded in the session* or shown to the user; OQ-6's downscaling decision needs this signal to be visible first. | M2 step 5 + M3 step 3 | Test: a session with images records non-zero input-token cost per model; comparison view renders per-model cost. |
| R1-S10 | Validation | medium | M3.5/M3 acceptance: make the §4 front-door case a single shared fixture driven by *both* the TUI (M3.5 acceptance) and the CLI (M3.5 tests) so the "no logic fork" claim (FR-MMC-13) is actually enforced, not just asserted. | M3.5 promises the CLI wraps "the same core" but tests TUI and CLI separately; a shared golden-session assertion is the only thing that proves the artifacts are identical. | M3 step 5 + M3.5 step 3 | Both surfaces run the §4 case against mocked agents and produce a byte-identical `ConsultationSession` (modulo timestamps/id). |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S11 | Risks | high | Adversarial (FR-MMC-2 adapter risk): add a case for a model that advertises `vision` but the *specific* selected model variant rejects the image (or the account lacks vision entitlement) — a run-time 4xx from the provider, distinct from the M1.5 static capability gate. | Capability gating (FR-MMC-2a) is a static string check (`anthropic.py:370` etc.); it cannot catch per-variant or per-account vision refusals, so a "vision-capable" roster can still fail mid-fan-out — exactly the case FR-MMC-2a claims to prevent. | Risks §C (new bullet) + M1.5 note | Inject a mocked provider 4xx "image not supported"; assert it is recorded as a per-model error (FR-MMC-11), not a crash. |
| R1-S12 | Data | medium | Adversarial (OQ-8 concurrency): specify behavior when the referenced image file is moved/deleted between the initial turn and a follow-up (FR-MMC-6a stores path+hash, not bytes) — re-validate hash on follow-up and fail-loud on mismatch. | FR-MMC-6a deliberately does not re-embed base64, so a follow-up that re-sends visual context (OQ-10 append mode) can silently send a *different* image if the path was reused, or crash if deleted. | Risks §C + M2 step 2 | Test: mutate the on-disk image between turns; assert hash-mismatch is detected and surfaced. |
| R1-S13 | Ops | medium | Adversarial (base64 cost, OQ-6): add a pre-flight per-provider transport-limit check in M1 so an oversized image is rejected *before* the fan-out spends tokens on the models that would accept it, rather than discovering the limit as a mid-run per-provider error. | FR-MMC-1's "size ceiling" is a single local cap, but providers have *different* max bytes/dimensions (OQ-6); a single ceiling either rejects valid images or lets through images one provider bounces after billing others. | M1 (new step) + OQ-6 | Test: an image between two providers' limits is either rejected up front or the per-provider rejection is attributed without charging the others. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — R1 is the first round)

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-03 UTC

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-03 UTC
- **Scope**: Second external pass. R1 covered the load-bearing structure (shared pre-adapter, byte-identity boundary, per-turn state, atomic writes, session-id, errored-turn history, per-provider limits, static-vs-runtime vision gate). R2 goes deeper into surfaces R1 did **not** touch: filesystem trust boundary of `--image-dir` / folder pick, image **content** validation (magic-byte vs extension, animated/multi-frame formats), provider SDK/API-version payload drift across the *two* OpenAI call sites, session-id **creation** collision across the new concurrent CLI+TUI surfaces, and cost attribution when an image call **partially** fails or is retried. No R1 item re-proposed; settled list (arun_benchmark gather, human-only eval, 2-image cap, ConsultationSession artifact, TUI+CLI surface) respected.

**Executive summary (top risks / opportunities):**
- The `--image-dir` / folder-pick path (M3.3, M3.5) is an **untrusted-path trust boundary** — no milestone step constrains traversal, symlinks, or which 2 files get auto-selected; selection is also **non-deterministic**, which breaks the R1-S10 "byte-identical session" claim.
- Image **format validation** in M3.3 is asserted (FR-MMC-1) but no step decodes the header — extension-only checks let a renamed/corrupt/animated file through to three different provider decoders with three different failure modes.
- M1.3 lists **two** OpenAI construction sites (`openai.py:214` **and** `openai.py:896`); the plan does not say both get the image path, so vision can be wired into one call path and silently absent in the other.
- Session-id collision (OQ-8/R1-S7) is scoped to "two TUI instances," but M3.5 adds a **concurrent CLI** on the same `.startd8/consultations/` tree — a CLI run and a TUI run started in the same millisecond can collide even with a timestamp scheme.
- Cost attribution (M2.5) is undefined under **partial image-call failure**: a model that 4xx's *after* the provider counted image tokens, or a retried turn (R1-S8/FR-MMC-11), can double-count or under-count image spend.
- Opportunity: the roster/fan-out core (M2.3) already gathers per-model results with `return_exceptions=True` — persisting the **raw provider error object** (not just a string) is ~free and makes R1-S8's errored-turn-history and R1-S11's runtime-refusal cases classifiable.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Security | high | M3.3 / M3.5: constrain the `--image-dir` and TUI folder-pick to a trust boundary — resolve to an absolute real path, reject paths that escape an allowed root via `..` or symlink, and skip (not follow) symlinked entries when auto-selecting the ≤2 images. | The folder-pick and `--image-dir` accept arbitrary user paths and then read bytes to base64-embed; without canonicalization a symlink or `..` lets the tool read + transmit an out-of-tree file to three external providers. Neither M3.3 nor M3.5 names any path constraint. | M3 step 3 + M3.5 step 1 (new path-safety sub-step) | Test: `--image-dir` containing a symlink to `/etc/passwd` and a `../` traversal are both rejected/skipped; only regular files under the resolved root are selected. |
| R2-S2 | Data | high | M3.3 / M1.1: define the **deterministic selection rule** when a folder holds >2 images (e.g. lexicographic by name, first 2) and record the *chosen* paths in the session, since R1-S10 asserts a byte-identical session across TUI+CLI. | "up to 2 images are selected" (FR-MMC-1) is unspecified as to *which* 2; a directory-order-dependent pick makes the TUI and CLI select different images from the same folder, silently breaking the R1-S10 "no logic fork / identical artifact" guarantee. | M3 step 3 + M1 step 1 | Test: a 5-image folder yields the same 2 image hashes from both TUI and CLI selection code paths. |
| R2-S3 | Risks | high | M3.3 / M1: validate image **content by header/magic bytes**, not extension, and reject multi-frame/animated inputs (or define how one frame is chosen) before base64 — GIF is in the FR-MMC-1 allow-list but animated GIF / large WebP behave differently per provider. | FR-MMC-1 lists PNG/JPEG/WebP/GIF but the plan never decodes the file; a `.png` that is actually HEIC, a truncated JPEG, or an animated GIF reaches three provider adapters and fails in three different ways *after* the run starts — the opposite of the "validate before any model call" intent. | M1 (new validation sub-step) + M3 step 3 | Test: a renamed-HEIC-as-.png and an animated GIF are rejected pre-fan-out with a clear reason; a truncated JPEG is caught locally. |
| R2-S4 | Interfaces | high | M1.3: state explicitly that **both** OpenAI construction sites (`openai.py:214` and `openai.py:896`) receive the image parts, and add a guard test that neither path can send a vision roster call without images. | M1.3 cites two OpenAI line numbers but the prose ("parts array") reads as one adapter; if only one call site is patched, some code paths (e.g. sync vs async, or `agenerate` vs an internal retry) drop images silently — a partial-coverage bug the byte-identity tests won't catch (they test the *absent* case). | M1 step 3 (OpenAI bullet) | Test: exercise both OpenAI entry points with a vision roster; assert image parts present in the mocked body for each. |
| R2-S5 | Ops | medium | M1.3 / Risks §C: add a provider **SDK/API-version pin + drift guard** — the three payload shapes (Anthropic beta image blocks, OpenAI `image_url` data-URL, Gemini `Part`) are tied to specific SDK versions; pin them and add a contract test that fails loudly when the installed SDK's expected field/shape changes. | "Provider payload drift" in §C is framed as *cross-provider* divergence; the un-addressed risk is *temporal* drift — an SDK minor bump changing `media_type`→`mime_type` or `Part.from_bytes` signature breaks vision at runtime with no local signal. NR-3 (no new providers) does not cover version bumps of existing ones. | Risks §C (new bullet "Provider SDK version drift") + M1 step 3 | Contract test per provider asserting the constructed block matches the pinned SDK's expected schema; CI fails on shape change. |
| R2-S6 | Data | high | M2.2 / M3.5: extend the session-id collision guard (R1-S7/OQ-8) to the **CLI+TUI cross-surface** case — the id must be process-unique (include a pid/random component), and creation must fail-loud (not overwrite) if `<session-id>/` already exists. | R1-S7 and §C scope collision to "two TUI instances," but M3.5 introduces a *second binary* writing the same tree concurrently; a pure timestamp/slug id collides when a CLI and TUI run start together. Creation must be `mkdir`-exclusive, not just atomic-replace of `session.json`. | M2 step 2 + M3.5 step 1 | Test: two processes create sessions in the same millisecond → distinct dirs; a forced duplicate id fails loudly rather than clobbering. |
| R2-S7 | Ops | medium | M2.5: define cost attribution under **partial image-call failure and retry** — record image-input tokens only when the provider actually billed them, avoid double-counting a retried turn (R1-S8), and attribute a mid-fan-out 4xx (R1-S11) as zero-cost-but-failed vs billed-but-failed per provider semantics. | M2.5 routes every call through the cost hook, but a call that errors *after* the provider metered image tokens (or a retry that re-sends the image) will either double-count or lose the image spend; the plan has no rule for cost on the failure/retry path, undermining FR-MMC-5's "attributed and visible." | M2 step 5 (new failure-path note) | Test: a model that 4xx's post-metering and a retried turn each produce exactly-once, correctly-signed cost rows in the session. |
| R2-S8 | Validation | medium | M2 / M2.3: persist the **raw provider error (type + status/code)**, not just a message string, on each failed per-model turn, so R1-S8 (errored-turn history), R1-S11 (runtime vision refusal), and R2-S7 (billed-but-failed) are classifiable downstream rather than parsed from prose. | The gather already yields exception objects (`return_exceptions=True`, benchmark.py:107); flattening them to a string at persist time is lossy and forces every later consumer (retry logic, cost attribution, history threading) to re-derive intent from text. Capturing structured error data is ~free at the fan-out boundary. | M2 step 3 (error recording) | Test: a mocked 429 and a mocked 400-image-unsupported persist with distinguishable structured codes; retry logic branches on code, not substring. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S9 | Security | medium | Adversarial (path boundary): specify behavior when `--image-dir` points at a directory containing a **huge number of files** or a FIFO/device node — bound the directory scan (max entries examined) and reject non-regular files, so folder-pick cannot hang or block on a special file. | The auto-select "up to 2 from a folder" scan is unbounded and untyped; a directory with 10⁶ entries or a named pipe makes selection hang before any validation, a DoS on the local tool. R1 never considered the folder-pick as an input surface. | M3 step 3 + M3.5 step 1 | Test: a directory with a FIFO and 10k files returns promptly, selects only regular image files, and never blocks on the FIFO. |
| R2-S10 | Risks | medium | Adversarial (concurrency + cost): specify what a **follow-up to `all`** does when one model's *prior* turn is still in-flight or its session-write from the previous turn hasn't landed — the read-modify-write of `session.json` (R1-S6) plus a re-fan-out can replay stale history or drop the in-flight result. | R1-S6 flagged lost-update on overlapping follow-ups; the sharper case is a follow-up issued *before* a slow model's prior turn persisted — the new fan-out reads a session missing that turn and threads incomplete history, corrupting FR-MMC-7 continuity for that model only. | Risks §C + M2 step 4 | Test: model B's turn-1 write is delayed; a turn-2 `all` follow-up either waits for B or fails-loud for B, never threads B with missing turn-1 context. |

**Endorsements** (prior untriaged R1 suggestions this reviewer agrees with):
- R1-S1: the shared pre-adapter (encode/validate/short-circuit) is the correct home for the concerns R2-S2/S3 add; endorse strongly.
- R1-S5: per-turn state enum + last_error is the prerequisite for R2-S7/S8 cost-and-error attribution.
- R1-S6: atomic-write + lost-update hazard is real; R2-S6/S10 extend it to cross-surface and in-flight cases.
- R1-S8: errored-turn history threading; R2-S8's structured-error persistence is what makes it implementable.
- R1-S11: static-vs-runtime vision gate; R2-S7 depends on distinguishing its billed-but-failed outcome.

**Disagreements** (untriaged prior R1 items this reviewer would flag):
- R1-S7 (partial): pinning the id scheme is right, but its *sortability* rationale is secondary to *process-uniqueness* (R2-S6) — a lexicographically-sortable id that isn't process-unique still collides across CLI+TUI. Recommend triage weight the uniqueness property above sortability.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to plan coverage.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-MMC-1 (prompt + ≤2 image input, validation) | M3.3 (TUI pick), M3.5 (CLI `--image`) | Partial | Validation (existence/format/size ceiling) named in reqs but not owned by any milestone step; per-provider limit divergence (OQ-6) not enforced pre-fan-out (see R1-S13). |
| FR-MMC-2 (multimodal agent support) | M1.1–M1.4 | Full | Shared encode/validate stage implicit (R1-S1); byte-identity asserted at arg not request level (R1-S2). |
| FR-MMC-2a (capability gating) | M1.5, M3.3 | Partial | Static-string gate only; run-time per-variant/per-account vision refusal uncovered (R1-S11). |
| FR-MMC-3 (parallel fan-out) | M2.3 | Full | — |
| FR-MMC-4 (roster selection, default council) | M3.3 | Full | — |
| FR-MMC-5 (cost tracking incl. image tokens) | M2.5 | Partial | Image-token cost routed through hook but not persisted-per-turn or surfaced in comparison view (R1-S9). |
| FR-MMC-6 (persisted ConsultationSession) | M2.1–M2.2 | Full | — |
| FR-MMC-6a (image reference persistence, no base64) | M2.2 | Partial | `ImageRef` vs `ImageInput` types not disambiguated (R1-S4); stale/moved-image hazard on follow-up (R1-S12). |
| FR-MMC-7 (per-model conversation continuity) | M2.3–M2.4 | Partial | History threading of an errored last turn undefined (R1-S8); per-turn state shape needed (R1-S5). |
| FR-MMC-8 (follow-up routing control) | M3.4 | Full | — |
| FR-MMC-9 (TUI integration) | M3.1–M3.2 | Full | — |
| FR-MMC-10 (comparison view) | M3.3 | Partial | Turn-aware/image-grounded extension named but per-turn cost surfacing not specified (R1-S9). |
| FR-MMC-11 (partial-failure resilience) | M2.3 | Partial | Retry-ability requires per-turn status enum + last_error, not the flat per-model status in M2.1 (R1-S5, R1-S8). |
| FR-MMC-12 (resumability, may defer) | M4 (deferred) | Partial | Deferred by design; flagged so orchestrator notes the dependency of CLI `--session` (FR-MMC-13) on the same load path. |
| FR-MMC-13 (`startd8 consult` CLI) | M3.5 | Partial | "No logic fork" asserted but not enforced by a shared golden-session fixture across TUI+CLI (R1-S10). |

---

## Requirements Coverage Matrix — R2

Analysis only (not triage). R2 delta — coverage gaps newly surfaced this round (does not restate R1 rows already Partial for the same reason; new gaps only).

| Requirement | Plan Step(s) | Coverage | Gaps (new this round) |
| ---- | ---- | ---- | ---- |
| FR-MMC-1 (prompt + ≤2 image input, validation) | M3.3, M3.5 | Partial | `--image-dir`/folder-pick is an untrusted-path surface with no traversal/symlink guard (R2-S1), no deterministic which-2 selection rule (R2-S2), and no header/magic-byte or multi-frame validation (R2-S3, R2-S9). |
| FR-MMC-2 (multimodal agent support) | M1.1–M1.4 | Partial | Two OpenAI construction sites may be patched asymmetrically (R2-S4); no provider SDK/API-version pin against temporal payload drift (R2-S5). |
| FR-MMC-5 (cost tracking incl. image tokens) | M2.5 | Partial | Cost attribution undefined under partial image-call failure / retry double-count (R2-S7); depends on structured error capture (R2-S8). |
| FR-MMC-6 (persisted ConsultationSession) | M2.1–M2.2 | Partial | Session-id creation collision across concurrent CLI+TUI surfaces; needs process-unique id + exclusive-create (R2-S6). |
| FR-MMC-7 (per-model conversation continuity) | M2.3–M2.4 | Partial | `all` follow-up issued before a slow model's prior turn persists can thread stale/incomplete history (R2-S10). |
| FR-MMC-11 (partial-failure resilience) | M2.3 | Partial | Retry/attribution need raw provider error type+code persisted, not a flattened string (R2-S8). |
| FR-MMC-13 (`startd8 consult` CLI) | M3.5 | Partial | Adds a second concurrent writer to `.startd8/consultations/` (R2-S6) and a second path-input surface (R2-S1); folder-pick determinism must match TUI (R2-S2). |
