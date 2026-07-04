# Native Multi-Turn Continuity — Requirements

**Version:** 0.3 (Post lessons-learned hardening — ready for CRP)
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
- **FR-NC-2 — Native `messages=` on `agenerate` (3 providers).** Claude, OpenAI, and Gemini agents
  accept an optional `messages=` (the FR-NC-1 shape). When provided it **takes precedence** over
  `prompt`/`images` and is rendered natively — Anthropic content-block messages, OpenAI role-tagged
  messages with parts, Gemini role-tagged `contents` — reusing the M1 image render helpers and adding
  assistant-message + role rendering. Returns a plain `GenerateResult` (no tools).
- **FR-NC-3 — Backward compatibility (byte-identity).** `agenerate(prompt, images=)` single-shot is
  unchanged; `messages=None` ⇒ the emitted request is byte-identical to today (extends the FR-MMC-2
  invariant). Agents without a `messages=` path are unaffected.
- **FR-NC-4 — Cost-hook threading.** `acreate_response` / `_run_with_cost_tracking` accept an optional
  `messages=` and pass it to `agenerate`, so native multi-turn calls keep per-turn cost attribution.
- **FR-NC-5 — Engine builds native messages.** The consultation engine constructs the canonical
  message list from a model's **valid history** (`valid_history`, ok-turns only — R1-S8) plus the new
  user turn, and sends it via `messages=` instead of the transcript prompt.
- **FR-NC-6 — Prior-image re-send (OQ-10), integrity-checked.** When re-sending a prior user turn's
  images, the engine **reloads bytes from the `SessionImageRef.source_path` and re-validates the
  content hash** (FR-MMC-6a). On missing file or hash mismatch it **degrades** (drops that image with
  a recorded note) and never sends different bytes than the audit trail claims. Whether prior images
  are re-sent every turn is **configurable** (default resolved in OQ-2) given the token cost.
- **FR-NC-7 — Provider-uniform text primitive (closes the AgenticSession gap).** `agenerate(messages=)`
  is the documented, tool-free, multi-turn-text primitive the codebase lacked; `AgenticSession` stays
  the tool-loop path (unchanged).
- **FR-NC-8 — Valid history only.** The message list never includes failed/skipped assistant turns
  (reuse `valid_history`), so no malformed sequence (e.g. empty-assistant) is sent to a provider.
- **FR-NC-9 — Transcript fallback.** For agents that don't support `messages=` (mock/others), the
  engine falls back to the existing transcript continuity, so behavior stays provider-uniform and no
  consultation breaks.

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
photos** are threaded as a native message array, so the answer references the actual image — not just
a text summary of it. A model whose image file was moved since turn 1 gets a recorded "image
unavailable" note and a text-only continuation (never a wrong image).

---

## 5. Open Questions

- **OQ-2 — Re-send prior images every turn (cost) vs only when the follow-up is image-relevant vs
  never-by-default with an opt-in.** Leaning: **re-send by default when the thread began with images,
  with a flag to disable** (correctness over cost; the user can trim).
- **OQ-4 — Detect `messages=` support** via a capability method (`supports_messages()`) vs try/except
  fallback. Leaning: an explicit opt-in flag (mirrors `supports_tool_use`).
- **OQ-5 — Assistant-message content** — do any providers need the assistant's *prior image/tool*
  content preserved, or is prior assistant text sufficient? (v1: assistant text only.)

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

*v0.3 — Reflective loop v0.1→v0.2 (5 corrections, 2 OQs resolved) → v0.3 (6 lessons). The load-bearing
risks are the **canonical-message contract fidelity across 3 different provider shapes** and the
**image-re-send integrity** (bytes aren't persisted). Ready for CRP.*
