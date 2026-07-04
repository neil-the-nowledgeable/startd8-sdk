# Native Multi-Turn Continuity — Requirements

**Version:** 0.4 (Post-CRP — R1+R2 triaged & applied)
**Date:** 2026-07-04
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Extends:** the consultation feature (M1 multimodal `images=`; M2 engine continuity).
**Source:** ENHANCEMENTS.md #3 (the M-effort answer-quality lever).

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 and v0.2 after reading the agent layer + engine.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| "No message-array path exists" | **Claude's `_make_api_call` already accepts a `messages` list** (`claude.py:273`, from the FR-0 tool work) and prefers it over `prompt`. OpenAI/Gemini build their arrays inline. | Claude is **half-done**; the gap is (a) exposing `messages=` on `agenerate` and (b) rendering *images inside prior messages*. OpenAI/Gemini need the array path built. |
| "A canonical message primitive exists to reuse" | `agenerate_tools(messages, tools)` + `_normalize_messages` (`base.py:280,311`) take a canonical list — but it's welded to **tool use** (requires `supports_tool_use`, returns `AgenticTurn` with tool calls). | The new path is a **separate `messages=` on `agenerate`** returning a plain `GenerateResult` (no tools). This is exactly the "provider-uniform multi-turn *text* primitive" that's missing (the AgenticSession gap). |
| "Re-sending prior images is straightforward" | **False — the persisted session has no image bytes.** `SessionImageRef` stores path + hash + mime only (FR-MMC-6a). Re-sending a prior turn's images means **reloading bytes from `source_path` and re-validating the hash**; the file may have moved/changed. | New **FR-NC-6**: prior-image re-send reloads + hash-revalidates (FR-MMC-6a); missing/mismatch → degrade (skip that image with a note), never silently send different bytes. |
| "The cost hook already carries what's needed" | `acreate_response`/`_run_with_cost_tracking` take `prompt` + `images` only (`base.py:460,575`); they call `agenerate(prompt, images=)`. | **FR-NC-4**: thread an optional `messages=` through the tracked path so native turns keep cost attribution. |
| "Every agent can do messages=" | The 5th+ agents (mock, ollama, etc.) won't implement the array path. | **FR-NC-9**: the engine keeps the **transcript fallback** for agents that don't support `messages=`, so continuity stays provider-uniform. |

**Resolved open questions:**
- **OQ-3 → The canonical message type lives in the agent layer** (`agents/multimodal.py` or a small
  `agents/messages.py`), since providers render it — not in `consultation/`.
- **OQ-1 → A new lightweight text+image message shape**, not `agenerate_tools`' (which returns tool
  turns). Reuse the M1 per-provider *image* render helpers; add assistant-message + role rendering.

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified every symbol: `agenerate`/`agenerate_tools`/`_normalize_messages`/
  `acreate_response`/`_run_with_cost_tracking` (`agents/base.py`), Claude `_make_api_call` `messages` param
  (`claude.py:273`), `to_anthropic_block`/`to_openai_part`/`to_gemini_part` + `_build_user_content`
  (`multimodal.py`/`openai.py`), `_render_history`/`valid_history` (`engine.py`/`models.py`),
  `SessionImageRef` (no bytes, `models.py`). See §7.
- **[Overloaded-term co-location]** — do **not** overload `agenerate_tools`' message list (tool-shaped)
  with a text-continuity meaning. The new canonical text+image message type gets its own name/module
  (FR-NC-1), distinct from the tool-turn path.
- **[Single-source vocabulary ownership]** — the canonical message format is **owned by one module**
  and each provider *cites/renders* it; this doc references it rather than restating per-provider JSON.
- **[Backward-compat discipline]** — `agenerate(prompt, images=)` single-shot must stay byte-identical
  (the M1/FR-MMC-2 byte-identity invariant extends here: `messages=None` ⇒ unchanged). FR-NC-3.
- **[Image-integrity inheritance]** — prior-image re-send inherits FR-MMC-6a: reload + hash-revalidate,
  fail-loud/degrade on mismatch (FR-NC-6). No bytes are ever invented.
- **[CRP steering memory]** — least-reviewed = this new doc; the **canonical-message contract +
  per-provider rendering fidelity + image-re-send integrity** are the highest-value review targets.

*Checked lessons base; six classes applied. Ready for CRP.*

---

## 1. Problem Statement

Consultation follow-ups give each model *some* memory today, but crudely: the engine flattens prior
**ok** turns into a transcript string and prepends it to the new prompt (`_render_history`). It's
provider-uniform but (a) not how the providers natively represent conversation (weaker fidelity,
wastes tokens re-quoting), and (b) **prior images are lost** — a follow-up can't reference the photos
the model saw in turn 1. The result is a real answer-quality ceiling on multi-turn consultations.

| Component | Current State | Gap |
|-----------|---------------|-----|
| Continuity mechanism | Transcript string prepended to prompt (`engine._render_history`) | Not native; images dropped |
| Agent primitive | `agenerate(prompt, images=)` single-shot; `agenerate_tools(messages, tools)` tool-only | No provider-uniform multi-turn **text** path |
| Claude payload | `_make_api_call` already accepts `messages` | Not exposed on `agenerate`; images-in-messages unrendered |
| Persisted images | `SessionImageRef` (path+hash, no bytes) | Re-send needs reload + hash-revalidate |

---

## 2. Requirements

- **FR-NC-1 — Canonical message contract.** A single owned message shape: an ordered list of
  `{role: "user"|"assistant", content}` where `content` is a string **or** a list of parts (text +
  `ImageInput`). Owned by one agent-layer module; each provider renders it to its native form.
  - **FR-NC-1a — System-prompt composition (R1-F1, R2-F2).** The spec defines how an agent's effective
    `system_prompt` composes with `messages=` across **all three system sinks**: Anthropic's separate
    top-level `system` parameter, OpenAI's `{"role":"system"}` **message** (`openai.py:230`), and
    Gemini's `system_instruction` in the config (**out-of-band**, not a `contents` entry). The renderer
    routes system content to the right sink per provider; `system` is **not** a role in the canonical
    contract (which is user/assistant only).
  - **FR-NC-1b — Type versioning / forward-compat (R2-F3).** The canonical message/part schema carries
    a version tag and a defined policy for **unknown part kinds or roles** (reject-loud, not
    silently-drop) so future part types can't be mis-rendered.
- **FR-NC-2 — Native `messages=` on `agenerate` (3 providers).** Claude, OpenAI, and Gemini agents
  accept an optional `messages=` (the FR-NC-1 shape). When provided it **takes precedence** over
  `prompt`/`images` and is rendered natively — Anthropic content-block messages, OpenAI role-tagged
  messages with parts, Gemini role-tagged `contents` (`role: user`/**`model`**). The renderer **owns
  all per-turn image rendering** (builds `to_anthropic_block`/etc. blocks for **every** user turn
  before dispatch) — note Claude's `_make_api_call(messages=)` passes messages **verbatim** and renders
  no images itself (R1-F2), Gemini currently sends role-less flat `contents` and needs true role tags
  (R1-S1). Returns a plain `GenerateResult` (no tools).
- **FR-NC-3 — Backward compatibility (byte-identity).** `agenerate(prompt, images=)` single-shot is
  unchanged; `messages=None` ⇒ the emitted request is byte-identical to today (extends FR-MMC-2). A
  golden test also guards the **`messages=`-present system composition** (FR-NC-1a) per provider, not
  only the `messages=None` path (R1-S3).
- **FR-NC-4 — Cost-hook threading + share observability.** `acreate_response`/`_run_with_cost_tracking`
  accept an optional `messages=` and pass it to `agenerate`, keeping per-turn cost attribution.
  > **Implementation status (2026-07-04):** threading + per-turn attribution **DONE**. The
  > **re-sent-context token-share split (R2-F5) is DEFERRED to v2** — providers report a single
  > `input_tokens` total per call and do not break out re-sent-context vs new-turn tokens, so the split
  > isn't derivable without a local re-tokenizer. The O(n²) growth is still *visible* via the rising
  > per-turn `input_tokens` (surfaced by QW-1 cost display); only the *attribution split* is deferred.
- **FR-NC-5 — Engine builds native messages.** The engine builds the canonical message list from a
  model's **valid history** (`valid_history`, ok-turns only) plus the new user turn, and sends it via
  `messages=`. The built user messages are assembled **from the turn's own fields** (text + image refs),
  never re-derived from `_render_history` output (R2-F7).
  - **FR-NC-5a — Mode-mixing determinism (R2-F1, the key R2 catch).** A model was originally answered
    with a transcript-**prefixed** prompt while the persisted user `Turn.text` holds only the **raw**
    prompt (`engine.py:181`). Switching that thread to native `messages=` therefore replays a
    *different* history than the model saw. The spec **pins one continuity mode per session** (recorded
    on the session) OR requires the native builder to reproduce equivalent context — so a roster is
    never silently part-native/part-transcript with divergent histories.
- **FR-NC-6 — Prior-image re-send (OQ-10), integrity-checked.** When re-sending a prior user turn's
  images, the engine **reloads bytes from `SessionImageRef.source_path`, hashes the bytes it actually
  read, and requires that hash == the stored ref** (FR-MMC-6a; TOCTOU-safe: the hashed bytes are the
  sent bytes — R1-F8/S8). Three distinct degrade cases each **record a per-turn note + a machine-visible
  `[image unavailable]` marker** and never send different bytes (R1-F3/F4):
  - `source_path is None` (pasted image, no path) — cannot reload;
  - file missing/moved;
  - hash mismatch.
  A cumulative **re-sent-image token/byte ceiling** per request caps cost; over-budget drops oldest
  images first (R1-F7/S5). Re-send-every-turn default is resolved in OQ-2.
- **FR-NC-7 — Provider-uniform text primitive (closes the AgenticSession gap).** `agenerate(messages=)`
  is the documented, tool-free, multi-turn-text primitive the codebase lacked; `AgenticSession` stays
  the tool-loop path (unchanged).
- **FR-NC-8 — Well-formed history (structural invariant).** The built array contains **only ok turns**,
  **alternates roles** (no consecutive same-role, no empty/whitespace assistant turn), and starts with a
  user turn — a structural invariant asserted on the *built array*, not just "ok-filtered" (R1-F6). v1
  assistant turns are **text-only** (any assistant turn carrying only non-text content is dropped or
  text-substituted — folds R1-F9).
  - **FR-NC-8a — Context-window truncation (R2-F6).** When the rebuilt array (even text-only) would
    exceed a model's context window, the engine applies a **defined truncation policy** (e.g. drop
    oldest turns, keep the alternation invariant) rather than letting the provider hard-error.
- **FR-NC-9 — Transcript fallback + per-modality capability.** For agents that don't support `messages=`
  (mock/others) the engine falls back to transcript continuity, so nothing breaks. Capability is
  **per-modality** (R2-F4): `supports_messages()` gates the text array; **image parts remain gated by
  vision capability** (a text-array-capable but non-vision model gets text-only messages). If
  `supports_messages()` is True but a provider **rejects** the array at runtime, that model's turn is
  recorded as a per-model error (mis-detection contract, R1-F5) — it does not sink the fan-out.

---

## 3. Non-Requirements

- **NR-1 — Not tool calling.** Native text turns return `GenerateResult`; tool loops stay in
  `agenerate_tools`/`AgenticSession` (untouched).
- **NR-2 — No streaming** (still batch; NR-5 of the base feature holds).
- **NR-3 — No persisted-schema change.** `turns_by_model` is unchanged; canonical messages are built
  at send time. `SessionImageRef` stays byte-free (FR-MMC-6a).
- **NR-4 — No new providers**; only the existing Claude/OpenAI/Gemini agents gain the path.
- **NR-5 — Does not replace the transcript path outright** — it remains the fallback (FR-NC-9).

---

## 4. First Acceptance Scenario

On the door session: a follow-up to Gemini asks *"in the second photo, which screw do I remove
first?"* With native continuity **and** prior-image re-send, Gemini's prior turns **and the two door
photos** are threaded as a native message array (roles `user`/`model`), so the answer references the
actual image — not just a text summary of it. A model whose image file was moved since turn 1 gets a
recorded `[image unavailable]` marker and a text-only continuation (never a wrong image).

**Equivalence criterion (R2-F8):** for the *same* image follow-up, the native-mode answer must
demonstrably reference the image (e.g. names a visible feature) where the transcript-fallback answer
can only paraphrase — the observable proof that native continuity beats the transcript shortcut.

---

## 5. Open Questions

- **OQ-2 → RESOLVED: re-send by default when the thread began with images, `--no-image-resend` to
  disable, capped by the FR-NC-6 token/byte ceiling.** Correctness over cost; the ceiling + flag bound it.
- **OQ-4 → RESOLVED (per-modality, R2-F4): an explicit `supports_messages()` flag** (mirrors
  `supports_tool_use`) gates the text array; image parts stay gated by vision capability (FR-NC-9).
- **OQ-5 → RESOLVED: v1 assistant turns are text-only** (folded into FR-NC-8).
- **OQ-6 (new) — Where the per-session continuity mode is recorded** for FR-NC-5a (a session field vs
  inferred). Leaning: an explicit session field set on first follow-up.

---

## 6. Reference Audit (verified symbols)

| Symbol | Location | Role |
|--------|----------|------|
| `agenerate(prompt, **kwargs)` (abstract) / concrete per-provider | `agents/base.py:215` + provider files | gains `messages=` (FR-NC-2) |
| `agenerate_tools` / `_normalize_messages` | `agents/base.py:280,311` | tool-shaped list — **not** reused for text (OQ-1) |
| `acreate_response` / `_run_with_cost_tracking` | `agents/base.py:575,388` | thread `messages=` (FR-NC-4) |
| Claude `_make_api_call` `messages` param | `agents/claude.py:273` | already accepts messages; extend for images |
| `to_anthropic_block`/`to_openai_part`/`to_gemini_part`, `_build_user_content` | `agents/multimodal.py:208+`, `openai.py:46` | per-message rendering building blocks |
| `_render_history` / `valid_history` | `consultation/engine.py:214`, `models.py` | transcript today; source of native messages (FR-NC-5/8) |
| `SessionImageRef` (path+hash, no bytes) | `consultation/models.py` | why re-send needs reload+revalidate (FR-NC-6) |
| `ImageInput` / `load_image` (hash) | `agents/multimodal.py` | reload + hash check for re-send |

*To-be-created:* the canonical message type + `render_messages` per provider; `messages=` on the 3
`agenerate`s + the tracked path; `supports_messages()` opt-in; engine native-message builder +
image-reload/revalidate; transcript fallback wiring.

---

*v0.4 — Post-CRP. Reflective loop v0.1→v0.3, then a 2-round CRP (R1+R2, reviewer `claude-opus-4-8[1m]`,
R2 endorsed ~all R1 with 1 dedup): all 17 requirements suggestions accepted. Added FR-NC-1a (system
composition, 3 sinks), FR-NC-1b (type versioning), FR-NC-5a (mode-mixing determinism — the key catch),
FR-NC-8a (context-window truncation); hardened FR-NC-2 (renderer owns all image rendering; Claude verbatim
+ Gemini role tags), FR-NC-4 (token-share observability), FR-NC-6 (source_path=None + TOCTOU read-once +
token ceiling + audit marker), FR-NC-8 (structural well-formedness), FR-NC-9 (per-modality capability +
mis-detection contract); §4 equivalence criterion; OQ-2/4/5 resolved, OQ-6 added. Dispositions in Appendix A.*

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

> **Triage (2026-07-04):** strongly convergent (R2 endorsed R1-F1/F3–F8 + all R1-S). All 17
> requirements suggestions ACCEPTED. R1-F9 folded into FR-NC-8 per R2's dedup (not rejected). Plan
> `R*-S*` dispositions in `NATIVE_CONTINUITY_PLAN.md`.

| ID | Suggestion | Applied to |
|----|------------|-----------|
| R1-F1 | System-prompt composition with messages= | FR-NC-1a |
| R1-F2 | Renderer owns all image rendering; Claude verbatim | FR-NC-2 |
| R1-F3 | source_path=None distinct degrade case | FR-NC-6 |
| R1-F4 | Record degraded (image-dropped) turn + marker | FR-NC-6 |
| R1-F5 | supports_messages mis-detection contract | FR-NC-9 |
| R1-F6 | Role-alternation / no-empty-assistant invariant | FR-NC-8 |
| R1-F7 | Re-sent-image cost/size ceiling | FR-NC-6 |
| R1-F8 | Reload TOCTOU / read-once (hash the sent bytes) | FR-NC-6 |
| R1-F9 | v1 assistant text-only | Folded into FR-NC-8 |
| R2-F1 | Mode-mixing determinism | FR-NC-5a |
| R2-F2 | System composition — all 3 sinks | FR-NC-1a |
| R2-F3 | Canonical-type versioning + unknown-kind policy | FR-NC-1b |
| R2-F4 | Per-modality capability | FR-NC-9 / OQ-4 |
| R2-F5 | Re-sent-context token-share observability | FR-NC-4 |
| R2-F6 | Context-window truncation policy | FR-NC-8a |
| R2-F7 | Never re-derive user text from _render_history | FR-NC-5 |
| R2-F8 | Native-vs-transcript equivalence acceptance | §4 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-04

- **Reviewer:** claude-opus-4-8[1m]
- **Date:** 2026-07-04 (UTC)
- **Scope:** Requirements review (F-prefix). Crux focus per NC_CRP_FOCUS: canonical message contract (FR-NC-1), per-provider rendering fidelity (FR-NC-2), image re-send integrity (FR-NC-6), fallback detection (FR-NC-9/OQ-4), byte-identity (FR-NC-3). Verified against source: `agents/claude.py:281-345`, `agents/gemini.py:227-240`, `agents/openai.py:230-233`, `consultation/models.py:53-66,117`, `consultation/engine.py:181,214-216`.

**Focus-file asks (answered before suggestions):**

- **Ask 1 — Is `{role, content: str|list[Part]}` sufficient; roles beyond user/assistant (system)?**
  - **Summary answer:** Partial — the two-role enum is under-specified for OpenAI, whose agent prepends a `{"role":"system",...}` message from `self.system_prompt`/per-call override (`openai.py:230-233`).
  - **Rationale:** FR-NC-1 restricts `role` to `"user"|"assistant"`. But the single-shot OpenAI path injects a system message the caller never sees. When the engine sends `messages=`, either (a) that system prompt is silently dropped (fidelity regression vs single-shot), or (b) it must be re-injected by the renderer — a rule FR-NC-1/FR-NC-2 do not state. Claude takes `system` out-of-band (`claude.py` `system_prompt` kwarg), Gemini has yet another convention. This is a genuine cross-provider gap, not a byte-identity concern.
  - **Assumptions / conditions:** Holds if any of the 3 agents is ever constructed with a `system_prompt`. If the consultation engine never sets one, the risk is latent but should still be documented as a precondition.
  - **Suggested improvements:** Add FR-NC-1a stating how the system prompt composes with `messages=` (renderer re-injects the agent's effective system prompt out-of-band; `role` stays user/assistant in the canonical shape). See R1-F1.

- **Ask 2 — Does Claude's `_make_api_call(messages=)` render images in *prior* user messages, or only the last?**
  - **Summary answer:** Neither — it renders images in **no** message. `claude.py:314-315` assigns `resolved_messages = messages` verbatim; the image-block rendering (line 320, `content` from `_build_user_content`) is **only** on the single-shot `prompt` branch.
  - **Rationale:** So "Claude is half-done" (§0 row 1) overstates readiness: the existing `messages=` param passes dicts straight to the SDK with zero image handling. FR-NC-2 must render **every** user turn's image parts (via `to_anthropic_block`) before calling `_make_api_call`, not rely on it. The requirement says this but the discovery table frames Claude as closer to done than the bytes support.
  - **Assumptions / conditions:** none (verified in source).
  - **Suggested improvements:** Tighten §0 row 1 / FR-NC-2 to state the renderer owns *all* per-turn image rendering; `_make_api_call` is a pass-through. See R1-F2.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | Add **FR-NC-1a — system-prompt composition**: specify how an agent's effective `system_prompt` composes with `messages=` (renderer injects it out-of-band per provider; canonical `role` stays user/assistant). | OpenAI agent prepends a system message from `self.system_prompt`/override (`openai.py:230-233`); Claude/Gemini pass system out-of-band. FR-NC-1's two-role contract is silent on this, so a `messages=` send can silently drop the system prompt present in the single-shot path — a fidelity regression the byte-identity guard (FR-NC-3) will NOT catch (it only guards `messages=None`). | New FR under §2, after FR-NC-1 | Test: an OpenAI agent built with a `system_prompt`, sent via `messages=`, still emits the `{"role":"system"}` message in the payload. |
| R1-F2 | Data | medium | Correct the §0 "Claude is half-done" framing and make FR-NC-2 state the renderer owns **all** per-turn image rendering; `_make_api_call(messages=)` is a verbatim pass-through (renders no images). | Verified: `claude.py:314-315` assigns `messages` unmodified; image blocks (line 320) exist only on the single-shot branch. The doc's discovery table implies `_make_api_call` already handles images-in-messages ("Claude is half-done; the gap is … rendering images inside prior messages"), which could mislead an implementer into extending `_make_api_call` rather than the pre-call renderer. | §0 discovery table row 1; FR-NC-2 | Grep the shipped renderer: image blocks are produced before `_make_api_call`, and `_make_api_call` is unchanged for the messages branch. |
| R1-F3 | Risks | high | FR-NC-6: handle `SessionImageRef.source_path is None` explicitly as a distinct degrade case, separate from "file moved/changed". | `models.py:58` — `source_path: Optional[str] = None`. A ref persisted without a source path cannot be reloaded at all; FR-NC-6 only enumerates "missing file or hash mismatch", not "no path recorded". Without this, `load_image(None)` raises rather than degrades. | FR-NC-6 | Test: a `SessionImageRef` with `source_path=None` degrades to a recorded "image unavailable (no source)" note, not an exception. |
| R1-F4 | Ops | high | FR-NC-6: require the degraded (image-dropped) turn to be **recorded in the audit trail / turn note**, and state whether the model is told an image was omitted. | The requirement says "drops that image with a recorded note" but does not define *where* the note lives (transcript? turn metadata? a message part telling the model "image N unavailable"?). If the model silently receives a text turn referencing "the second photo" with no image and no note, it will hallucinate. Audit honesty (the §4 "recorded 'image unavailable' note") needs a concrete sink. | FR-NC-6; §4 acceptance | Test: degraded re-send produces a persisted note AND the sent message array contains a machine-visible "[image unavailable]" placeholder for the omitted image. |
| R1-F5 | Validation | medium | OQ-4/FR-NC-9: define the **mis-detection failure contract** — what happens when `supports_messages()` returns True but the provider rejects the array (e.g. alternating-role violation, empty content). | FR-NC-9 covers the "doesn't support" direction (fallback). It does not cover a *capable* agent that still errors on a specific array (empty/whitespace assistant turn, non-alternating roles some providers enforce). Without a stated contract this becomes an uncaught 400. | FR-NC-9 or new FR-NC-9a | Test: a malformed-but-well-typed array (consecutive user turns; empty assistant) is either normalized or rejected pre-send with a clear error, never sent raw. |
| R1-F6 | Data | medium | FR-NC-8 ("valid history only") should also assert **role alternation / no empty-assistant** as a structural invariant of the built array, not just "ok turns only". | `valid_history` filters non-ok turns, but two consecutive user turns (a follow-up before any assistant reply, or a dropped assistant) can still produce a non-alternating array. Anthropic requires strict user/assistant alternation and rejects empty content; the requirement conflates "ok turn" with "well-formed sequence". | FR-NC-8 | Test: build array from a history with a missing assistant reply → array is either merged or the send is blocked with a structural error. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F7 | Risks | high | OQ-2 default ("re-send images every turn when the thread began with images") needs a **cost/size ceiling** requirement: a long thread re-sends the same photos on every turn, multiplying image tokens by turn count and risking context-window overflow. | Re-sending 2 door photos across a 6-turn thread sends them 6× (or 21× cumulatively if every turn re-sends all priors). Anthropic/OpenAI image tokens are large; this can both blow cost and exceed the window, causing a hard 400 mid-consultation. The doc treats cost as a user-trims-it flag; it needs a bound. | OQ-2 / new FR-NC-6a | Test: N-turn image thread stays under a configurable image-token/byte budget; over-budget → oldest images dropped-with-note before send. |
| R1-F8 | Risks | medium | FR-NC-6: address the **reload race / TOCTOU** — hash is validated at reload, but the file could change between hash-check and read, or be a symlink/permission-denied. State that bytes hashed are the bytes sent (read-once, hash-the-read-buffer), and that permission errors degrade (not crash). | FR-NC-6 says "reload bytes … and re-validate the content hash"; if implemented as stat/hash then re-open/read, the sent bytes may differ from the hashed bytes. `load_image` behavior on `PermissionError` is unspecified. | FR-NC-6 | Test: hash is computed over the exact buffer that is sent (single read); a permission-denied path degrades with a note. |
| R1-F9 | Interfaces | medium | OQ-5 (assistant prior image content): state explicitly that v1 assistant turns are **text-only**, and that any assistant turn carrying only non-text content (v-future) must not produce an empty-content assistant message. | Gemini/Anthropic reject empty-content messages. If a future assistant turn had image/tool content stripped to nothing, the array becomes invalid. Pinning "assistant = text, never empty" now prevents a latent FR-NC-8 violation. | OQ-5 / FR-NC-8 | Test: assistant message content is always a non-empty string in v1. |

**Endorsements (prior untriaged):** none — first review round; Appendix C was empty.

#### Review Round R2 — claude-opus-4-8[1m] — 2026-07-04

- **Reviewer:** claude-opus-4-8[1m]
- **Date:** 2026-07-04 (UTC)
- **Scope:** Requirements review (F-prefix), Round 2 — deeper/adversarial pass over angles R1 under-covered: system-prompt-as-a-message-role, cross-turn mode-mixing non-determinism (transcript-generated history replayed as native), per-capability `supports_messages()`, canonical-type versioning/migration, quadratic re-send cost attribution, Gemini `system_instruction` vs system turn, and transcript-prefix leakage into native history. Verified against source: `consultation/engine.py:180-224` (`_render_history`, `effective_prompt = _render_history + prompt`; user `Turn.text=prompt` raw), `consultation/models.py:71-85,117-136` (`Turn.text`, `valid_history`), `agents/openai.py:230-233` (system-message prepend), `agents/claude.py:314-320`.

**Executive summary (top risks / gaps R1 missed):**
- **Mode-mixing non-determinism (new, high):** the persisted user `Turn.text` is the *raw* prompt (`engine.py:182`) but the assistant answer was generated seeing the *transcript-prefixed* `effective_prompt` (`engine.py:181,187`). When a native-`messages=` turn rebuilds history from clean `turn.text`, a thread whose early turns ran in transcript mode presents a **different context** to the model than it originally saw — silent answer drift, not caught by any byte-identity guard.
- **`system` is a role R1 half-covered:** R1-F1 handled OpenAI's prepended system message, but not that Gemini uses `system_instruction` (out-of-band, not a `contents` role) and Anthropic uses a top-level `system` — three different sinks for one concept; FR-NC-1 still needs the portable rule.
- **No canonical-type version/migration story:** FR-NC-1 introduces a new owned shape with no version tag; future part kinds (audio, tool, doc) or role additions have no forward/back-compat rule.
- **`supports_messages()` is coarse (OQ-4):** modeled as one agent-level flag, but message capability is really per-part (text vs image vs future) — mirrors the existing per-capability `supports_vision`/`supports_tool_use` split; a vision-less model that supports text `messages=` needs both signals.
- **Quadratic thread cost is unbounded and unattributed:** re-sending the whole thread each turn grows prompt tokens ~O(n²) cumulatively; R1-F7 bounded images but not the text transcript, and FR-NC-4 attributes cost per-turn without flagging the re-sent-context share.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Risks | high | Add **FR-NC-5a — mode-mixing determinism**: when a thread contains turns generated in transcript mode, the native builder must reproduce equivalent context (or the doc must state that switching modes mid-thread is disallowed / pins one mode per session). | `engine.py:182` persists the raw prompt as user `Turn.text`; `engine.py:181` feeds the model the transcript-prefixed `effective_prompt`. Native mode rebuilds from clean `Turn.text`, so a model that answered turn 1 seeing `<conversation-history>…` will, on a later native turn, see a structurally different history for the *same* session. Roster models split native/transcript will diverge on identical inputs. | New FR after FR-NC-5; §1 gap table | Test: a session with turn 1 run transcript-mode and turn 2 native-mode either pins the mode (asserted) or the native turn-1 reconstruction is context-equivalent (documented rule). |
| R2-F2 | Interfaces | high | Generalize R1-F1 into **FR-NC-1a covering all three system sinks**: OpenAI system *message* (`openai.py:230`), Gemini `system_instruction` (out-of-band), Anthropic top-level `system` — the canonical shape carries system intent once and each renderer routes it to its provider's sink. | R1-F1 named only OpenAI's prepended message. The portability rule must be provider-complete or Gemini/Anthropic renderers will each invent an ad-hoc convention, defeating "single owned contract". Gemini in particular has *no* system role inside `contents`. | FR-NC-1 / new FR-NC-1a (supersede-extend R1-F1) | Test: one canonical system intent renders to a `{"role":"system"}` msg (OpenAI), a `system_instruction=` kwarg (Gemini), and a top-level `system=` (Anthropic). |
| R2-F3 | Data | medium | Add **FR-NC-1b — canonical-type versioning**: tag the message/part schema with a version and state the forward-compat rule for unknown part kinds (renderer drops-with-note vs errors) and new roles. | FR-NC-1 defines a brand-new owned type but NR-3 only freezes the *persisted* schema; the in-memory canonical type has no migration story. OQ-5 already foreshadows future assistant image/tool parts. Without a version + unknown-part policy, adding audio/doc parts later silently changes 3 renderers' behavior. | New FR after FR-NC-1a; ref OQ-5 | Test: an unknown part kind hits a defined path (skip-with-note or explicit error), never a renderer `KeyError`. |
| R2-F4 | Interfaces | medium | Refine OQ-4/FR-NC-9: make capability detection **per-modality**, not one boolean — e.g. `supports_messages()` gates the text array, but image *parts* inside a message must still consult `supports_vision` (already exists). | The doc treats `supports_messages()` as monolithic (mirrors `supports_tool_use`), but a model can support multi-turn text arrays yet not images. A capable-text/no-vision model sent an image part in a message will 400. FR-MMC-2a's vision gate must compose with the new flag. | OQ-4; FR-NC-9; ref FR-MMC-2a | Test: a text-capable, vision-incapable agent sent a message array with an image part degrades the image (per FR-NC-6) rather than being routed to transcript wholesale. |
| R2-F5 | Ops | medium | Extend cost attribution (FR-NC-4): require the re-sent-context token share to be **distinguishable** from the new-turn tokens, so a thread's O(n²) growth is observable, not buried in one per-turn number. | Re-sending the full thread each turn means turn-k's input tokens include all prior turns; FR-NC-4 records one input-token count per turn with no split. A 10-turn thread's cost is dominated by re-sent context, invisible in the current signal — blocks any future "trim old turns" decision. | FR-NC-4; §5 OQ-2 | Test: per-turn cost record exposes (new-turn tokens, re-sent-context tokens) or an equivalent breakdown. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F6 | Risks | high | Add **FR-NC-8a — thread truncation policy for context-window overflow**: when the rebuilt array (even text-only) exceeds a model's context window, define deterministic truncation (drop-oldest-turns / summarize) rather than emitting a request that 400s. | R1-F7 bounded *image* tokens; a long *text* thread re-sent each turn independently overflows the window. FR-NC-8 guarantees valid *ordering* but not that the array *fits*. Different roster models have different windows, so the same thread may fit some and overflow others — the panel must degrade per-model, not fail the panel. | FR-NC-8; §5 | Test: a thread engineered past a model's window truncates oldest turns with a recorded note and still sends a valid request; smaller-window models truncate more. |
| R2-F7 | Data | medium | Pin explicitly (extend R1-F2/OQ-5) that the native builder must **never** re-derive a user turn's text from `_render_history` output — it reads only raw `Turn.text` — to prevent the transcript prefix leaking into a native user message. | `Turn.text` is clean today (`engine.py:182`), but an implementer wiring the builder near `_render_history` (`engine.py:214`) could accidentally source `effective_prompt`, embedding `<conversation-history>` *inside* a native user turn — double-history. This is a live foot-gun given both live in the same method. | FR-NC-5; FR-NC-8 | Test: built native user messages equal raw `Turn.text`, asserting no `<conversation-history>` substring appears in any message content. |
| R2-F8 | Validation | medium | State the **cross-model equivalence acceptance criterion** the §4 scenario implies: native-mode and transcript-fallback answers to the *same* follow-up should be compared, and any large divergence flagged, since a mixed roster returns some native + some transcript answers to the user side-by-side. | §4 asserts native "references the actual image — not just a text summary", implicitly claiming native ≥ transcript quality. But a mixed roster shows both in one comparison view; if native silently degrades (wrong role, dropped system prompt) it could be *worse* than transcript with no signal. An acceptance probe protects the headline claim. | §4 acceptance | Manual/eval: for one image follow-up, capture a native and a transcript answer from comparable models; native must at minimum reference the image, transcript must not error. |

**Endorsements (prior untriaged):**
- R1-F1: correct and load-bearing — system-prompt composition is the sharpest cross-provider gap; R2-F2 extends it to all three sinks rather than duplicating it.
- R1-F3: verified in source (`models.py` `source_path: Optional[str] = None`); the `None` branch is a real crash-vs-degrade fork.
- R1-F4: the audit sink + in-array "[image unavailable]" marker is essential to stop hallucination on a dropped photo; strongly agree.
- R1-F5 and R1-F6: the mis-detection contract and role-alternation invariant are both real provider-rejection paths R2-F6 builds on.
- R1-F7: image-token ceiling is right; R2-F6 generalizes the same concern to the text thread.
- R1-F8: read-once/TOCTOU integrity is a genuine correctness gap for the hash guarantee.

**Disagreements (prior untriaged):**
- R1-F9 (low): pinning "assistant = non-empty text in v1" is fine but arguably redundant once FR-NC-8's well-formedness invariant (R1-F6) exists — the alternation/empty-content guard already forbids empty assistant messages; keep as a note under FR-NC-8 rather than a standalone requirement to avoid two requirements guarding one invariant.

