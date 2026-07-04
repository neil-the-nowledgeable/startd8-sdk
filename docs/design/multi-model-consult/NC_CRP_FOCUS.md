# CRP Focus — Native Multi-Turn Continuity

**Least-reviewed target:** Both `NATIVE_CONTINUITY_REQUIREMENTS.md` (v0.3) and `NATIVE_CONTINUITY_PLAN.md`
(v1.0) are brand-new — first external review. This adds a `messages=` path across the **shared agent
layer** (Claude/OpenAI/Gemini), so cross-provider fidelity and backward-compat are the crux.

## Settled — do NOT relitigate
- The new path is a **tool-free `messages=` on `agenerate` returning `GenerateResult`** — NOT
  `agenerate_tools` (which is tool-shaped and returns `AgenticTurn`).
- Single-shot `agenerate(prompt, images=)` stays **byte-identical** (`messages=None` ⇒ unchanged).
- Persisted schema unchanged; `SessionImageRef` stays byte-free (FR-MMC-6a); messages built at send time.
- Transcript continuity remains the **fallback** for agents without `messages=` (mock/others).
- Claude/OpenAI/Gemini only; no new providers; no streaming; not tool calling.

## Where review input is most valuable
1. **Canonical message contract (FR-NC-1).** Is `{role, content: str|list[Part]}` sufficient? Roles
   beyond user/assistant (system)? How is a per-message image part represented portably? Where should
   the type live (agent-layer module) and how do the 3 providers cite vs restate it?
2. **Per-provider rendering fidelity (FR-NC-2).** The 3 shapes differ: Anthropic content-block messages,
   OpenAI role-tagged messages, Gemini `contents` with `role: "model"` (not "assistant"). What silently
   degrades on a wrong role/shape? Does Claude's existing `_make_api_call(messages=)` render images in
   *prior* user messages, or only the last one?
3. **Backward-compat / byte-identity (FR-NC-3).** Is a per-provider golden payload test the right guard?
   Any path where adding a `messages=` param perturbs the single-shot request?
4. **Image re-send integrity (FR-NC-6).** Reload-from-`source_path` + hash-revalidate — failure modes
   (file moved/changed/permission)? Cost of re-sending images every turn (OQ-2 default)? Should the
   *assistant's* prior image content be preserved (OQ-5)?
5. **Fallback detection (FR-NC-9, OQ-4).** `supports_messages()` opt-in vs try/except — mis-detection
   consequences (transcript to a capable model = harmless; messages to a non-capable one = error).
6. **Cost-hook threading (FR-NC-4).** Any attribution edge when a turn is sent as messages vs prompt?
