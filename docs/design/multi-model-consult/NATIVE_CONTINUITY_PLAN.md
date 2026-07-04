# Native Multi-Turn Continuity — Implementation Plan

**Version:** 1.0 (Post-reflection)
**Date:** 2026-07-04
**Status:** Draft — pairs with `NATIVE_CONTINUITY_REQUIREMENTS.md` v0.3

---

## A. Discoveries (what planning revealed)

| Requirements assumed | Planning revealed | Consequence |
|----------------------|-------------------|-------------|
| No message path exists | Claude `_make_api_call` already takes `messages` | Claude is half-done; expose + render images-in-messages |
| Reuse `agenerate_tools` messages | It's tool-shaped, returns `AgenticTurn` | New tool-free `messages=` on `agenerate` → `GenerateResult` |
| Re-send images is easy | Persisted refs have no bytes (FR-MMC-6a) | Reload from `source_path` + hash-revalidate; degrade on mismatch |
| Cost hook is ready | Takes prompt+images only | Thread `messages=` through the tracked path |
| Every agent supports it | mock/others won't | `supports_messages()` opt-in + transcript fallback |

The build is bounded: **one canonical message type + three per-provider renderers**, then thread it
through `agenerate`→cost-hook→engine, with an image-reload guard. Byte-identity for the single-shot
path is the safety invariant.

## B. Milestones

### M0 — Design lock (this doc set). Offer CRP (contract + per-provider fidelity are the review targets).

### M1 — Canonical message contract + per-provider renderers (FR-NC-1/2/3)
1. `agents/messages.py` (new): `Message = {role, content}` where `content: str | list[Part]`, `Part` =
   text or `ImageInput`; a `normalize(...)` helper. Owned here; providers cite it.
2. Per-provider `render_messages(messages) -> native`:
   - **Anthropic**: list of `{role, content: [text/image blocks]}` (reuse `to_anthropic_block`); pass to
     the existing `_make_api_call(messages=…)`.
   - **OpenAI**: role-tagged messages; user content via `_build_user_content`-style parts, assistant as
     text.
   - **Gemini**: `contents` with `role` (`user`/`model`) + parts (reuse `to_gemini_part`).
3. Add `messages=` to each `agenerate`; when set it wins over `prompt`/`images`. **Byte-identity guard:**
   `messages=None` ⇒ payload unchanged (golden test per provider). `supports_messages()` → True on the 3.

### M2 — Tracked-path threading (FR-NC-4)
1. `acreate_response` / `_run_with_cost_tracking` accept optional `messages=`; pass to `agenerate`
   (guarded like `images`, so agents without the param are unaffected). Token/cost recording unchanged.

### M3 — Engine native messages + image re-send (FR-NC-5/6/8/9)
1. Native builder: from `valid_history(model_id)` + the new user turn → canonical messages. Assistant
   text from ok turns; user text (+ images) per turn (FR-NC-8: no failed/skipped).
2. **Image re-send guard (FR-NC-6):** to attach a prior turn's images, reload bytes via
   `load_image(ref.source_path)` and assert `sha256 == ref.sha256`; on missing/mismatch, drop that image
   and record a note. Config flag for re-send default (OQ-2).
3. Dispatch: if `agent.supports_messages()` → `acreate_response(messages=…)`; else the existing
   transcript path (FR-NC-9). Persisted `turns_by_model` unchanged (NR-3).

### M4 — Tests + acceptance
1. Per-provider payload tests: a 3-turn `messages=` renders the right native shape (roles, image blocks);
   `messages=None` byte-identical to today.
2. Engine test: a 2-turn thread builds native messages (not a transcript) when the agent supports it;
   falls back to transcript for a non-supporting agent.
3. Image-re-send: prior image reloaded + hash-checked; a mutated/missing file degrades with a note.
4. Cost still recorded on a `messages=` call. Acceptance: §4 door follow-up references the real photo.

### M5 — Optional
- `AgenticSession` could later delegate its text turns to this primitive (out of scope now).

## C. Risks
- **Per-provider fidelity** — 3 different role/þcontent shapes; a wrong role mapping (Gemini `model` vs
  `assistant`) silently degrades answers. Golden payload tests per provider.
- **Byte-identity regression** — `messages=` must not perturb the single-shot path. Guard tests.
- **Image-re-send cost** — re-sending images each turn is expensive; default + flag (OQ-2), and never
  re-send un-revalidated bytes (FR-NC-6).
- **Fallback correctness** — a mis-detected `supports_messages()` could send a transcript to a
  native-capable model (harmless) or messages to a non-capable one (error) — gate on the explicit flag.

## D. Traceability
| FR | Milestone |
|----|-----------|
| FR-NC-1 | M1.1 |
| FR-NC-2 | M1.2–M1.3 |
| FR-NC-3 | M1.3 (byte-identity) |
| FR-NC-4 | M2 |
| FR-NC-5 | M3.1 |
| FR-NC-6 | M3.2 |
| FR-NC-7 | M1.3 (the primitive) |
| FR-NC-8 | M3.1 |
| FR-NC-9 | M3.3 |

---

*v1.0 — Bounded: one message contract + three renderers, threaded through the existing cost hook and
engine. The two review-worthy risks are cross-provider rendering fidelity and image-re-send integrity.*
