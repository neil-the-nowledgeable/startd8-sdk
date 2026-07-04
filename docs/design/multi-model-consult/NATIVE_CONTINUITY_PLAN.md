# Native Multi-Turn Continuity — Implementation Plan

**Version:** 1.1 (Post-CRP — R1+R2 applied; see §E)
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

## E. Post-CRP Hardening (v1.1 — R1+R2 applied)

Plan steps added by the CRP (all 17 S-suggestions accepted; each also in `NATIVE_CONTINUITY_REQUIREMENTS`
v0.4 Appendix A):

**M1 — contract + renderers:** version-tag `Message`/`Part` + unknown-kind/role reject-loud (R2-S4);
Gemini role-tagged `contents` (`user`/`model`) is **new** structure not a flat reuse (R1-S1); Claude
renderer builds per-turn image blocks **before** `_make_api_call` (verbatim pass, R1-S2); **system
routing** to all 3 sinks — OpenAI system message / Gemini `system_instruction` / Anthropic `system` param
(R2-S2); a second golden test for the `messages=`-present system composition (R1-S3); per-modality gating
(R2-S5).

**M2 — cost:** record re-sent-context token share separately from new-turn tokens (R2-S7).

**M3 — engine:** never embed `_render_history` output in built user messages (R2-S6); resolve
**mode-mixing** — pin one continuity mode per session or reproduce equivalent context (R2-S1); image guard
adds `source_path is None` (R1-S4), re-sent-image token/byte ceiling drop-oldest (R1-S5), degraded-turn +
`[image unavailable]` marker (R1-S7), **read-once** hash-the-sent-bytes (R1-S8); text-thread
context-window ceiling distinct from image budget (R2-S3).

**M4 — tests:** non-alternating/empty-assistant guard (R1-S6); TOCTOU read-once (R1-S8); cost-to-right-turn
(R1-S9); native-builder-never-embeds-transcript (R2-S6); native-vs-transcript equivalence probe on §4 (R2-S8).

---

*v1.1 — Post-CRP (R1+R2, reviewer `claude-opus-4-8[1m]`): 17 S-suggestions mapped into §E. Still bounded
(contract + 3 renderers + engine threading); the CRP added mode-mixing determinism, system-sink routing,
and image-integrity/window ceilings as load-bearing.*

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

> All 17 plan S-suggestions ACCEPTED and mapped into §E (R1-S1..S9, R2-S1..S8). Strongly convergent
> with the requirements F-suggestions; no rejections (R1-F9 was deduped, not rejected — see requirements A).

| ID | Mapped to |
|----|-----------|
| R1-S1 Gemini role-tagged contents = new structure | §E M1 |
| R1-S2 Claude renderer builds image blocks pre-`_make_api_call` | §E M1 |
| R1-S3 second golden for system composition | §E M1 |
| R1-S4 source_path=None branch | §E M3 |
| R1-S5 re-sent-image token/byte ceiling | §E M3 |
| R1-S6 non-alternating/empty-assistant test | §E M4 |
| R1-S7 degraded-turn audit + marker | §E M3 |
| R1-S8 TOCTOU read-once assertion | §E M3/M4 |
| R1-S9 cost-to-right-turn test | §E M4 |
| R2-S1 mode-mixing resolution | §E M3 |
| R2-S2 system routing — 3 sinks | §E M1 |
| R2-S3 text-thread window ceiling | §E M3 |
| R2-S4 canonical-type versioning | §E M1 |
| R2-S5 per-modality gating | §E M1 |
| R2-S6 never-embed-transcript guard | §E M3/M4 |
| R2-S7 token-share observability | §E M2 |
| R2-S8 native-vs-transcript equivalence probe | §E M4 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | High-signal review; all accepted (R1-F9 deduped into FR-NC-8, not rejected). | 2026-07-04 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-04

- **Reviewer:** claude-opus-4-8[1m]
- **Date:** 2026-07-04 (UTC)
- **Scope:** Plan review (S-prefix). Crux focus per NC_CRP_FOCUS: per-provider rendering fidelity, byte-identity guard, image re-send integrity, fallback detection, cost threading. Verified against source: `agents/claude.py:281-345`, `agents/gemini.py:227-240`, `agents/openai.py:230-233,63-77`, `consultation/models.py:53-66,117`, `consultation/engine.py:181,214-216`.

**Executive summary (top risks / gaps):**
- M1.2 Gemini renderer is a **bigger change than stated**: today Gemini sends a flat `contents=[prompt, *parts]` with **no role tags** (`gemini.py:231`). Role-tagged multi-turn `contents` with `role:"model"` is net-new plumbing, not "reuse `to_gemini_part`".
- M1.2 Claude renderer must render images itself — `_make_api_call(messages=)` passes messages **verbatim** (`claude.py:314-315`); it renders images only on the single-shot branch (line 320). Plan wording "pass to the existing `_make_api_call`" hides that the per-turn image blocks must be built *before* the call.
- M3.2 image-reload guard has an **unhandled `source_path=None`** case (`models.py:58` is `Optional`).
- Byte-identity guard (M1.3) tests `messages=None` only — it does **not** catch a system-prompt-composition regression on the `messages=` path (OpenAI prepends system; see requirements R1-F1).
- No cost/window ceiling for the OQ-2 "re-send every turn" default → mid-thread 400 / cost blow-up.
- M4 tests don't include a **non-alternating / empty-assistant** array case, which providers reject.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | M1.2 Gemini: state that role-tagged `contents` (`role: user`/`model` + `parts`) is **new structure**, not a reuse of the current flat `contents=[prompt,*parts]` path (`gemini.py:231`), and that the `assistant`→`model` role remap is an explicit, tested mapping. | The plan reads as if Gemini already has a role-tagged array to extend. It does not; the current call is role-less. A silent wrong/absent role is the exact "silently degrades answers" risk in §C — the mapping deserves its own build step + test, not a parenthetical. | M1.2 (Gemini bullet); §C fidelity risk | Golden payload test asserting each assistant turn renders `role:"model"` and each user turn `role:"user"` with correct parts. |
| R1-S2 | Interfaces | high | M1.2 Claude: make explicit that the renderer builds per-turn image blocks (`to_anthropic_block`) **before** `_make_api_call`, which is a verbatim pass-through (`claude.py:314-315`). Remove/qualify "pass to the existing `_make_api_call(messages=…)`". | Verified `_make_api_call` does no image rendering on the messages branch. If an implementer reads M1.2 literally they may hand raw canonical messages to `_make_api_call` and ship image-less prior turns — defeating the whole feature. | M1.2 (Anthropic bullet) | Test: a 2-turn `messages=` with a prior-turn image emits Anthropic image blocks in message[0]. |
| R1-S3 | Security | high | M1.3 byte-identity guard: add a **second** golden test that guards the `messages=`-present path's *system-prompt composition*, not just `messages=None`. | The stated guard (`messages=None ⇒ unchanged`) proves single-shot is untouched but proves nothing about whether the OpenAI system prompt (`openai.py:230-233`) survives the `messages=` path. A regression there is invisible to the current guard. Pairs with requirements R1-F1. | M1.3; §C byte-identity risk | Golden test: OpenAI agent w/ `system_prompt` + `messages=` → payload still contains the system message. |
| R1-S4 | Risks | high | M3.2 image-reload guard: add the `ref.source_path is None` branch alongside missing-file/mismatch. | `models.py:58` — `source_path` is `Optional[str] = None`. `load_image(None)` will raise, not degrade; the plan only enumerates missing/mismatch. | M3.2 | Test: ref with `source_path=None` → drop-with-note, no exception. |
| R1-S5 | Risks | high | Add an OQ-2 **cost/window ceiling** to M3.2: cap cumulative re-sent image tokens/bytes per request; over-budget drops oldest images with a note before send. | "Re-send by default" (OQ-2) on a long image thread multiplies image tokens per turn and can exceed the model context window → hard 400 mid-consultation, not just higher cost. The plan lists cost as a flag, not a bound. Pairs with requirements R1-F7. | M3.2; §C image-re-send-cost risk | Test: N-turn image thread stays under a configured image budget; over-budget → oldest-first drop-with-note. |
| R1-S6 | Validation | medium | M4: add a test for a **non-alternating / empty-assistant** array (consecutive user turns; ok-filtered history that still yields a bad sequence) — assert normalize-or-block, never raw send. | `valid_history` (`models.py:117`) filters non-ok turns but does not guarantee user/assistant alternation. Anthropic rejects non-alternating and empty-content messages. M4's tests only cover the happy 2–3-turn path. Pairs with requirements R1-F5/F6. | M4.1/M4.2 | Test: history missing an assistant reply → array merged or send blocked with a structural error. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Ops | medium | M3.2/§4: record the degraded (image-dropped) turn in the audit trail and inject a machine-visible "[image unavailable]" placeholder into the sent array, so the model isn't asked about a photo it never received. | §4 promises a "recorded 'image unavailable' note" but the plan (M3.2) only says "drop that image and record a note" with no sink and no in-array signal. A silent drop makes the model hallucinate about "the second photo". Pairs with requirements R1-F4. | M3.2; M4.3; §4 | Test: degraded re-send persists a note AND the message array carries an explicit unavailable-image marker. |
| R1-S8 | Validation | medium | M4: add a **TOCTOU / read-once** assertion for the reload guard — the bytes hashed are the bytes sent (hash the read buffer, not stat-then-reopen), and permission-denied degrades. | If M3.2 hashes then re-reads, a file changed between the two reads sends bytes that don't match the audit hash — the exact integrity guarantee FR-NC-6 exists to provide. Pairs with requirements R1-F8. | M3.2; M4.3 | Test: single-read hash-and-send; simulated permission error degrades with a note. |
| R1-S9 | Ops | low | M2 cost threading: add a test that a `messages=` call attributes cost to the **right turn/model** in a multi-turn thread (not just "cost still recorded"). | M2/M4.4 verify cost is recorded but not that per-turn attribution is correct when the same model has several native turns — an attribution mix-up is invisible to a presence-only test. | M4.4 | Test: 2 native turns on one model produce 2 distinct, correctly-attributed cost records. |

**Endorsements (prior untriaged):** none — first review round; Appendix C was empty.

#### Review Round R2 — claude-opus-4-8[1m] — 2026-07-04

- **Reviewer:** claude-opus-4-8[1m]
- **Date:** 2026-07-04 (UTC)
- **Scope:** Plan review (S-prefix), Round 2 — deeper/adversarial pass on angles R1 under-covered: cross-turn mode-mixing determinism, text-thread (not just image) context-window ceiling, canonical-type versioning, per-modality capability gating, Gemini/Anthropic system sinks, and cost-share observability. Verified against source: `consultation/engine.py:180-224` (raw `Turn.text` vs transcript-prefixed `effective_prompt`; `_render_history`), `consultation/models.py:117-136` (`valid_history`), `agents/openai.py:230-233`, `agents/gemini.py:227-240`, `agents/claude.py:314-320`.

**Executive summary (top risks / gaps R1 missed):**
- **Mode-mixing determinism (high, new):** M3.1's native builder sources `valid_history` → clean `Turn.text`, but turns generated *before* native mode ran saw the transcript-prefixed `effective_prompt` (`engine.py:181`). No milestone addresses a session whose history is part-transcript, part-native → the model sees a different context than it originally answered.
- **Text-thread window ceiling missing:** R1-S5 bounded *image* tokens; M3 has no bound on the re-sent *text* thread, which alone can overflow a model's context window on long consultations (and differently per roster model).
- **No versioning milestone for the new canonical type (M1.1):** unknown future part kinds / roles have no defined renderer behavior.
- **`supports_messages()` (M1.3) is monolithic:** should compose with the existing `supports_vision` gate for image parts, not be a single all-or-nothing switch.
- **Gemini/Anthropic system sinks unbuilt:** R1-S3 guarded OpenAI's system-message survival; M1.2 doesn't state where Gemini's `system_instruction` / Anthropic's top-level `system` are routed from the canonical shape.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Risks | high | Add an M3 sub-step (or an explicit constraint) resolving **mode-mixing**: either pin one continuity mode per session, or have the native builder reconstruct context equivalent to what a transcript turn originally saw. | `engine.py:182` stores the raw prompt as user `Turn.text`; `engine.py:181` sent the model `_render_history(...) + prompt`. M3.1 rebuilds from clean `Turn.text`, so a session that started in transcript mode and later dispatches native (a newly-added-model retry, a flag flip, an upgraded roster) presents a *different* history for the same turns. Pairs with requirements R2-F1. | M3.1; §C new "mode-mixing" risk | Test: turn 1 transcript + turn 2 native for one model asserts the mode is pinned, or the native turn-1 reconstruction is context-equivalent. |
| R2-S2 | Interfaces | high | M1.2: add a system-routing build step covering **all three sinks** — OpenAI system message, Gemini `system_instruction=` kwarg, Anthropic top-level `system=` — sourced once from the canonical shape. | R1-S3 only guarded OpenAI. `gemini.py` sends `contents` with no system role at all; a naive port drops the system prompt for Gemini entirely. Each renderer needs an explicit, tested system sink or the "one owned contract" claim breaks. Pairs with requirements R2-F2. | M1.2 (all three provider bullets) | Golden test per provider: a canonical system intent lands in that provider's system sink (message / `system_instruction` / top-level `system`). |
| R2-S3 | Risks | high | Add to M3.2/M3.3 a **text-thread context-window ceiling** (distinct from R1-S5's image budget): when the rebuilt array exceeds a model's window, truncate oldest turns with a note before send, per-model. | Even text-only, re-sending the whole thread each turn grows input O(n²) cumulatively and eventually overflows the window → hard 400 mid-consultation. Roster models have different windows, so the panel must degrade per-model, not fail wholesale. Pairs with requirements R2-F6. | M3.2/M3.3; §C | Test: an over-window thread truncates oldest turns with a recorded note and still emits a valid request; smaller-window model truncates more. |
| R2-S4 | Data | medium | M1.1: give the canonical `Message`/`Part` type a **version tag** and define the unknown-part-kind / unknown-role policy (skip-with-note vs error) now, before three renderers hard-code today's shape. | OQ-5 already anticipates future assistant image/tool parts; NR-3 freezes only the *persisted* schema, not this new in-memory type. Without a version + unknown-kind rule, adding a part later silently changes all 3 renderers. Pairs with requirements R2-F3. | M1.1 | Test: an unknown part kind takes a defined path (skip-with-note or explicit error), never a renderer `KeyError`. |
| R2-S5 | Interfaces | medium | M1.3/M3.3: make capability gating **per-modality** — `supports_messages()` gates the text array, but image parts still consult `supports_vision` (already exists, FR-MMC-2a). | A text-capable, vision-incapable model routed a message array containing an image part will 400. The plan's single `supports_messages()` switch (M1.3) doesn't compose with the vision gate. Pairs with requirements R2-F4. | M1.3; M3.3 | Test: text-capable/vision-incapable agent + image-bearing array degrades the image (FR-NC-6), not wholesale transcript fallback. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S6 | Validation | medium | M4: add a **negative-guard test that the native builder never embeds `_render_history` output** — built user messages equal raw `Turn.text`, no `<conversation-history>` substring. | M3.1's builder and `_render_history` live in the same engine method (`engine.py:181,214`); an implementer could accidentally source `effective_prompt`, double-nesting the transcript inside a native message. Cheap guard, catches a live foot-gun. Pairs with requirements R2-F7. | M4.2 | Test: assert no built message content contains `<conversation-history>`; content == raw `Turn.text`. |
| R2-S7 | Ops | medium | M2/M4.4: record the **re-sent-context token share** separately from new-turn tokens, so O(n²) thread growth is observable (extends R1-S9's per-turn attribution). | R1-S9 asserts correct per-turn attribution but not the *composition* of that turn's input tokens. A 10-turn thread's cost is dominated by re-sent context; without a split, no future "trim old turns" decision is measurable. Pairs with requirements R2-F5. | M2; M4.4 | Test: per-turn cost record exposes (new-turn tokens, re-sent-context tokens) or equivalent. |
| R2-S8 | Validation | low | M4: add a **native-vs-transcript equivalence probe** for one image follow-up (the §4 door case) — native must reference the image; a comparable transcript answer must not error — protecting the "native ≥ transcript" headline. | A mixed roster shows native + transcript answers side-by-side in one comparison view; if native silently degrades (wrong role / dropped system), it could be *worse* with no signal. Pairs with requirements R2-F8. | M4.4; §4 acceptance | Eval: capture one native + one transcript answer to the same image follow-up; assert native references the image, transcript does not error. |

**Endorsements (prior untriaged):**
- R1-S1: verified — `gemini.py:231` sends flat role-less `contents`; role-tagged `contents` with `role:"model"` is net-new, not a reuse. Deserves its own build step + test.
- R1-S2: verified — `claude.py:314-315` passes `messages` verbatim; the renderer must build image blocks pre-call. Load-bearing for the whole feature.
- R1-S3: correct; R2-S2 extends the same guard to Gemini/Anthropic system sinks.
- R1-S4: the `source_path=None` degrade branch is a real crash-vs-degrade fork.
- R1-S5: image-token ceiling right; R2-S3 adds the parallel text-thread ceiling.
- R1-S6, R1-S7, R1-S8: non-alternating array test, audit sink + in-array marker, and read-once/TOCTOU are all genuine gaps I agree with.

**Disagreements (prior untriaged):** none — R1-S1..S9 are all well-anchored and verified; R2 extends rather than contradicts them.

---

## Requirements Coverage Matrix — R2

> R2 addendum to the R1 matrix (above). Same requirements; columns re-evaluated against R2 findings. Analysis only.

| Requirement | Plan Step(s) | Coverage | Gaps (R2) |
| ---- | ---- | ---- | ---- |
| FR-NC-1 (canonical message contract) | M1.1 | Partial | No version tag / unknown-part-or-role policy for the new in-memory type (R2-F3/R2-S4). |
| FR-NC-1a (system-prompt composition, R1) | M1.2 | Partial | R1 covered OpenAI only; Gemini `system_instruction` + Anthropic top-level `system` sinks unbuilt (R2-F2/R2-S2). |
| FR-NC-2 (native `messages=`, 3 providers) | M1.2–M1.3 | Partial | Per-modality gating: image parts must still consult `supports_vision`, not just `supports_messages()` (R2-F4/R2-S5). |
| FR-NC-3 (byte-identity) | M1.3 | Partial | (unchanged from R1) system-composition on the `messages=` path; see R1-S3. |
| FR-NC-4 (cost-hook threading) | M2 | Partial | Re-sent-context token share not distinguished from new-turn tokens; O(n²) growth unobservable (R2-F5/R2-S7). |
| FR-NC-5 (engine builds native messages) | M3.1 | Partial | Mode-mixing: native builder reads clean `Turn.text` while transcript-era turns saw prefixed context — divergent history (R2-F1/R2-S1). Transcript-prefix-leak foot-gun (R2-F7/R2-S6). |
| FR-NC-6 (prior-image re-send, integrity) | M3.2 | Partial | (R1 gaps stand) plus per-modality image gate interaction (R2-F4/R2-S5). |
| FR-NC-7 (provider-uniform text primitive) | M1.3 | Full | — |
| FR-NC-8 (valid history only) | M3.1 | Partial | No context-window truncation policy for a long text thread that overflows per-model (R2-F6/R2-S3). |
| FR-NC-9 (transcript fallback) | M3.3 | Partial | Capability detection is monolithic; should compose per-modality (R2-F4/R2-S5). |
| §4 acceptance (native ≥ transcript) | M4.4 | Partial | No native-vs-transcript equivalence probe; mixed roster could show a silently-worse native answer (R2-F8/R2-S8). |
| OQ-2 (re-send default) | M3.2, §C | Partial | Text-thread window ceiling (distinct from R1 image budget) missing (R2-S3). |
| OQ-4 (`supports_messages()` detection) | M1.3, §C | Partial | Per-modality composition with `supports_vision` undefined (R2-F4/R2-S5). |
| OQ-5 (assistant prior image content) | M5 (deferred) | Partial | Ties to canonical-type versioning for future part kinds (R2-F3/R2-S4). |

---

## Requirements Coverage Matrix — R1

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-NC-1 (canonical message contract) | M1.1 | Partial | No system-prompt composition rule for the two-role enum (R1-F1/R1-S3). |
| FR-NC-2 (native `messages=`, 3 providers) | M1.2–M1.3 | Partial | Gemini role-tagged `contents` is net-new not a reuse (R1-S1); Claude renderer must build image blocks pre-call, `_make_api_call` is pass-through (R1-S2/R1-F2). |
| FR-NC-3 (byte-identity) | M1.3 | Partial | Guard covers `messages=None` only; system-prompt composition on the `messages=` path unguarded (R1-S3/R1-F1). |
| FR-NC-4 (cost-hook threading) | M2 | Partial | Per-turn attribution in a multi-turn thread untested (R1-S9). |
| FR-NC-5 (engine builds native messages) | M3.1 | Full | — |
| FR-NC-6 (prior-image re-send, integrity) | M3.2 | Partial | `source_path=None` case (R1-S4/R1-F3); no cost/window ceiling (R1-S5/R1-F7); TOCTOU/read-once + permission (R1-S8/R1-F8); audit sink + in-array marker (R1-S7/R1-F4). |
| FR-NC-7 (provider-uniform text primitive) | M1.3 | Full | — |
| FR-NC-8 (valid history only) | M3.1 | Partial | Filters ok-turns but not role-alternation / empty-assistant (R1-S6/R1-F6). |
| FR-NC-9 (transcript fallback) | M3.3 | Partial | Covers "not supported"; no contract for a capable agent that rejects a specific array (R1-S6/R1-F5). |
| OQ-2 (re-send default) | M3.2, §C | Partial | Default named; no cost/window bound (R1-S5/R1-F7). |
| OQ-4 (`supports_messages()` detection) | M1.3, §C | Partial | Opt-in flag chosen; mis-detection-on-capable-agent path undefined (R1-F5). |
| OQ-5 (assistant prior image content) | M5 (deferred) | Partial | v1 text-only stated in reqs; plan doesn't pin "assistant never empty" (R1-F9). |
