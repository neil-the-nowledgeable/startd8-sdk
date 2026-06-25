# SDK-Native Agentic Tool-Use Loop — Implementation Plan

**Version:** 1.1 (against Requirements v0.3 — post-CRP)
**Date:** 2026-06-24
**Status:** Planning (CRP-revised)

> This plan maps each requirement to real files/APIs. Where planning contradicted a v0.1 assumption,
> it is flagged **[DISCOVERY Dn]** and fed back into Requirements §0. **§E (bottom) records the
> CRP-driven revisions (R1–R5 triage) layered onto the increment sequence below.**

---

## A. What the codebase actually provides (verified)

| Surface | Reality (file:line) | Consequence |
|---|---|---|
| `BaseAgent.agenerate(prompt, **kwargs)` | `agents/base.py:215` — returns `GenerateResult(text, time_ms, token_usage)` | **text-in/text-out only.** No `tools=`, no tool-call return. |
| `GenerateResult` | `models.py:106` — frozen 3-tuple `NamedTuple` | **Cannot carry tool calls.** Need a new richer turn/event type. **[D2]** |
| Only tool-use path | `agents/claude.py:563 agenerate_structured()` — forces **one** tool, `input_schema`=a Pydantic schema, parses the `tool_use` block, validates | A *single forced* tool for structured output — **not** a general multi-tool agentic call. But it proves the provider-level `tools=`/`tool_use` mechanism. **[D1]** |
| Streaming | provider protocol has `supports_streaming()` (`providers/protocol.py:162`), `get_model_info()` (:141), `estimate_safe_output()` (:187) — **agents implement none** | Token budgeting can use `get_model_info` at protocol level (no LiteLLM). Streaming is genuinely absent → its own increment. **[D3]** |
| Cost cache tokens | `costs/models.py:99-102` (`cache_creation_input_tokens`/`cache_read_input_tokens`); `costs/pricing.py:537-555` (write/read multipliers) | **Reusable as-is.** Confirms FR-7. |
| Retry | `utils/retry.py:54 RetryConfig` (base/max delay, `retryable_status_codes`) | **Reusable.** Confirms FR-8. |
| MCP gateway | `mcp/gateway.py` — `execute_skill`/`execute_workflow`/`list_skills`/`list_workflows` | **Skill/workflow-oriented, NOT a generic `list_tools`/`call_tool` MCP client.** Can't drive arbitrary MCP tools. **[D4]** |
| MCP server | `mcp/startd8-mcp-builder/startd8_mcp.py` (FastMCP, 17+ tools) | Tools are *exposed*; nothing in-SDK *consumes* them as a client. **[D4]** |
| Concierge | `concierge/core.py:227 handle_concierge_tool(action, project_root, **params)`, `READ_ACTIONS=("survey","assess")` (:27), deterministic `$0 no LLM` (:5) | Read-only seam already structural — wrap `READ_ACTIONS` as 2 tools. **Trivial + naturally safe.** **[D6]** |

---

## B. Revised build sequence

Planning shows the work is **not** "thin loop + 3 thin consumers." The provider/agent layer has no
tool-use or streaming primitive, and there is no MCP *client*. Correct order:

### Increment 0 — Tool-use generation primitive (NEW foundational, was assumed to exist)
**[D1]** The loop cannot sit "on" `agenerate()` — `agenerate()` is text-only and `GenerateResult`
can't carry tool calls.
- **Step 0.1** Add `AgenticTurn` / `ToolCallRequest` types (`models.py` or `agents/agentic_types.py`)
  — carries `text`, `tool_calls: list[ToolCallRequest]`, `usage`, `finish_reason`. **[D2]**
- **Step 0.2** Add a provider-level tool-use generate: extend `BaseAgent` with
  `agenerate_tools(messages, tools, **kw) -> AgenticTurn`. Implement for **Claude first** by
  generalizing `agenerate_structured` (`claude.py:563`) — multi-tool, no forced schema, return all
  `tool_use` blocks. Then **OpenAI**. **[D1][D9]**
- **Step 0.3** Non-streaming only at this increment. Streaming deferred. **[D3]**

### Increment 1 — The loop (`agents/agentic.py`)  → FR-1, FR-3, FR-4, FR-7, FR-8, FR-9
- **Step 1.1** `AgenticSession`: holds `messages`, runs `while` turns calling `agenerate_tools`,
  dispatches tool calls to a `ToolRegistry`, appends results, re-enters. (port `agent_loop.py` shape)
- **Step 1.2** `ToolRegistry` (OpenAI-format specs) — built-in callables + (later) MCP tools. FR-9.
- **Step 1.3** Token budgeting via provider `get_model_info()` (`protocol.py:141`), fallback default.
  FR-4 read path. (No LiteLLM. **[D3]**)
- **Step 1.4** Context-overflow → compaction → retry: provider-agnostic exception mapping in the
  loop; compaction = an `agenerate` summarization call. FR-3/FR-4.
- **Step 1.5** Wire usage into `costs/` (cache tokens included). FR-7. Rate-limit retry schedule via
  `utils/retry.py`. FR-8.

### Increment 2 — Streaming + tool-call accumulation  → FR-2
- Implement provider streaming (`supports_streaming` honored), accumulate `tool_calls` deltas across
  chunks. Loop gains a streaming path; consumers opt in. **[D3]** (Deferrable; loop works without it.)

### Increment 3 — Prompt caching + effort cascade  → FR-5, FR-6
- **Step 3.1** Finish `claude.py` `enable_prompt_caching` stub: inject `cache_control` on tool block +
  system prompt at the `agenerate_tools` boundary; no-op non-Anthropic. FR-6. **[D8]**
- **Step 3.2** Effort probe-and-cascade, cache per model. FR-5 (optional).

### Increment 4 — Consumers (NOT uniformly thin **[D7]**)
- **4a — Concierge front-end (thinnest).** FR-12/FR-13. Register exactly `survey`/`assess` (wrapping
  `handle_concierge_tool`) into a `ToolRegistry`; no write actions. Read-only seam = "only register
  READ_ACTIONS." **[D6]**
- **4b — TUI chat (thin).** FR-10. Replace the `agent.generate(user_input)` line at
  `tui/mixin_enhancement_chain.py:467` with an `AgenticSession.send()`; render streamed turns.
- **4c — MCP agent surface (NOT thin — needs a new MCP client first).** FR-11. Build `mcp/client.py`
  (port `ml-intern/tools.py` `fastmcp.Client` adapter) to `list_tools`/`call_tool` against the SDK's
  FastMCP server, expose them through `ToolRegistry`. The gateway does not provide this. **[D4]**

---

## C. Mapping

| Req | Increment / Step |
|---|---|
| FR-1 | 1.1 |
| FR-2 | 2 |
| FR-3 | 1.4 |
| FR-4 | 1.3 + 1.4 |
| FR-5 | 3.2 |
| FR-6 | 3.1 |
| FR-7 | 1.5 |
| FR-8 | 1.5 |
| FR-9 | 1.2 + (0.2 primitive) |
| FR-10 | 4b |
| FR-11 | 4c (+ new `mcp/client.py`) |
| FR-12 | 4a |
| FR-13 | 4a (register only READ_ACTIONS) |
| **(new) FR-0** | **Increment 0 — tool-use primitive** |
| **(new) FR-14** | **Concierge front-end is no longer `$0`/deterministic at the chat layer [D10]** |

---

## D. Risks / sequencing notes

- Increment 0 is the real cost center; everything depends on it. Don't promise "thin loop" timelines.
- Streaming (Inc 2) is deferrable — ship a non-streaming loop first to de-risk.
- The MCP agent surface (4c) is the heaviest consumer, not the lightest — re-order so Concierge/TUI
  prove the loop before the MCP client is built.
- Concierge cost reframing (FR-14) is a posture-adjacent nuance, not a posture violation — must be
  stated, see Requirements §0 OQ-4.

---

## E. Post-CRP revisions (R1–R5 triage → Requirements v0.3)

The CRP added 8 FRs and hardened 6. Layering onto the increment sequence:

### Increment 0 — Tool-use primitive (REVISED)
- **0.1** Change `agenerate_tools` to **`messages: list[dict]`** primary (+ `prompt:str` overload)
  — the landed spike's `prompt:str` is rework-bait (FR-0/R1-F1/R5-A3). Update the 3 spike tests.
- **0.2** Adopt a **canonical tool-spec** input; translate to provider-native *inside* each adapter
  (FR-9/R5-A1) — fixes the current Claude-Anthropic-native vs OpenAI-native asymmetry.
- **0.3 (NEW)** `MockAgent.agenerate_tools` scripted-turn double — **blocks all loop testing**
  (FR-0a/R5-C2). Same-increment prerequisite.
- **0.4** Provider-neutral transcript model + `MessageCodec`s (FR-1/R3-F1) so canonical records render
  to Claude/OpenAI shapes; golden codec tests.

### Increment 1 — The loop (EXPANDED with safety, was under-scoped)
- **1.1** `AgenticSession` loop (unchanged shape) **+ FR-15 bounds**: `max_turns`,
  `max_tool_calls_per_turn`, per-tool **timeout + cancellation** (R5-C4), repeated-identical-call
  breaker, **per-session token/$ budget** via `costs/budget.py` checked before each re-entry.
- **1.2** `ToolRegistry`: canonical schema, **unknown-tool reject + pre-exec arg validation + result
  envelope + ordering/bounded-parallelism** (FR-9). Effect-class tags + **default-deny** (FR-19) —
  build this *before* the MCP consumer.
- **1.3** Token budgeting via `get_model_info` with documented fallback + warn-log (FR-4/R5-D3).
- **1.4** Compaction = **tool-result-eviction-as-units then summarize**, gated on the **pairing
  invariant** (FR-4/OQ-6); typed **`ContextWindowExceededError`** + per-provider detector (FR-3/FR-17).
- **1.5** `costs/` usage wiring (FR-7) + idempotent retry across tool execution (FR-8/OQ-9).
- **1.6 (NEW)** `FR-16 ToolResultPolicy` (redact/size-cap/truncate) on every surface.
- **1.7 (NEW)** `FR-17` typed error taxonomy; `FR-18` OTel spans; `FR-20` trajectory serialization +
  fail-closed resume; `FR-21` mark new types **experimental**.

### Increment 4 — Consumers (REVISED)
- **4a Concierge**: FR-13 **two-layer** enforcement — frozen registry (`len==2`) **+ dispatch floor**
  `handle_concierge_read` hard-rejecting non-READ actions. FR-14 banner + running cost + fail-closed
  budget. Opt-in/config-gated (FR-12).
- **4b TUI**: swap the call site (`:467`) for `AgenticSession` via the **sync-bridge** (R5-C3),
  opt-in, legacy REPL retained (FR-10/R4-F6).
- **4c MCP**: `mcp/client.py` returns **canonical** specs (R5-A5); `list_tools` snapshot + drift
  invalidation (FR-11/R4-F4). **Gated on FR-19 default-deny existing.**

### Validation (NEW)
- One **gated live** round-trip (`STARTD8_RUN_INTEGRATION=1`, `max_turns=2`, hard $ budget) (FR-0/R5-D5/OQ-10).

### Falsified during triage
- The "live `startd8_concierge` `readOnlyHint:True`→disk-write" claim was **verified false** (MCP is
  preview-only; `writes.py:9`). Defensive floor (4a) kept regardless. See Requirements Appendix B.

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
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2.5 — 2026-06-25 02:00:00 UTC

- **Reviewer**: composer-2.5
- **Date**: 2026-06-25 02:00:00 UTC
- **Scope**: Dual-document initial pass — expensive-to-reverse interface decisions (CRP focus), Increment-0 spike alignment, plan↔requirements traceability

**Executive summary**

- Increment 0 partially landed (`supports_tool_use` + `agenerate_tools` + `AgenticTurn` in `models.py`); plan Step 0.x should mark spike status and defer only OpenAI + multi-message threading.
- Additive opt-in on `BaseAgent` is the correct v1 boundary; document a mixed-fleet gate pattern in Step 1.1 rather than forcing a breaking `Protocol` change now.
- `AgenticTurn` in `models.py` matches the `StructuredResult` sibling precedent; resolve OQ-8 as "stay unless import cycles appear when `agentic.py` lands."
- Step 1.4 compaction is underspecified for agentic correctness — tool-call/result pairing must be a first-class constraint, not left to OQ-6 alone.
- A separate `mcp/client.py` is right, but Step 4c should mandate reuse of gateway resilience (circuit breaker, rate limit, cache) via shared transport — not a greenfield client.
- OQ-7 needs a v1 decision before Increment 4 consumers ship: deny-by-default tool registry + effect classification beats ad-hoc per-tool prompts.
- FR-0 API drift: spike uses `prompt: str`; plan/FR-1 imply `messages` — reconcile before Increment 1 or the loop will rewrite the primitive.
- OQ-3 trajectory logging has no plan step despite §0 resolution — add observability task to Increment 1.
- Concierge structural `READ_ACTIONS` enforcement is strong; FR-14 needs executable acceptance tests, not only UI copy.
- TUI Step 4b references streaming before Increment 2 ships — flag non-streaming fallback in consumer steps.

##### Sponsor focus — explicit answers

**Focus 1 — FR-0 primitive shape (additive opt-in vs Protocol change)**

- **Summary answer:** Yes — additive opt-in is the right long-term *v1* boundary; defer Protocol extension until ≥2 providers pass FR-0 smoke tests.
- **Rationale:** The landed spike (`BaseAgent.supports_tool_use()` default `False`, `agenerate_tools` on `ClaudeAgent`, 3 unit tests green, 93 agent tests unchanged) proves zero-touch downstream compatibility. FR-0 and Step 0.2 already target Claude-first generalization of `agenerate_structured`; breaking the provider `Protocol` now would churn ~10 providers and ~9 downstream repos for no loop benefit yet.
- **Assumptions / conditions:** `AgenticSession` (Step 1.1) must gate on `supports_tool_use()` and fail closed; mixed-fleet loops document which agents are tool-capable.
- **Suggested improvements:** Add Step 0.4 "capability discovery contract"; note future optional `ProviderProtocol.supports_tool_use` once OpenAI lands.

**Focus 2 — `AgenticTurn` location (OQ-8)**

- **Summary answer:** Stay in `models.py` for v1; revisit `agents/agentic_types.py` only if Increment 1 introduces import cycles.
- **Rationale:** Spike placed types beside `GenerateResult`/`StructuredResult` with explicit "sibling type, don't extend" docstrings (`models.py:116-155`). Step 0.1 lists both locations as open — spike evidence resolves OQ-8 toward co-location with other generation result types.
- **Assumptions / conditions:** `agents/agentic.py` imports from `models` only; loop-specific helpers live in `agentic.py`, not new top-level types.
- **Suggested improvements:** Close OQ-8 in Requirements §4 as "resolved → `models.py`"; add one-line cross-ref in Step 0.1.

**Focus 3 — `mcp/client.py` vs extending `mcp/gateway.py` (FR-11)**

- **Summary answer:** Yes — a separate generic MCP client module is correct; gateway should expose shared transport/resilience, not grow skill semantics into `list_tools`.
- **Rationale:** Gateway header and API are skill/workflow-oriented (`execute_skill`, `list_skills`, circuit breaker per skill — `mcp/gateway.py:1-7`). FR-11 and Step 4c correctly flag `[D4]`. Conflating generic `list_tools`/`call_tool` into the skill registry blurs discovery models and makes FR-11 the heaviest consumer for the wrong reason.
- **Assumptions / conditions:** `mcp/client.py` wraps FastMCP transport; gateway resilience primitives become importable shared infrastructure.
- **Suggested improvements:** Step 4c bullet: "client delegates connection/rate-limit/circuit-breaker to gateway layer"; add interface diagram in plan §B Increment 4c.

**Focus 4 — Tool-execution approval gate (OQ-7)**

- **Summary answer:** Partial — read-only-by-default + explicit allowlists suffice for Concierge (FR-13); TUI/MCP v1 need deny-by-default registry plus approval for tools classified `effectful`.
- **Rationale:** FR-13's structural registry restriction is sufficient for Concierge. Non-Concierge surfaces (Step 4b/4c, FR-10/FR-11) can register MCP tools with side effects; ml-intern's per-tool gate is the reference for v1 safety without blocking read-only tool loops.
- **Assumptions / conditions:** ToolRegistry (Step 1.2) tags each tool with an effect class; default deny for `write`/`destructive` unless allowlisted or user-approved once per session.
- **Suggested improvements:** Resolve OQ-7 in Requirements §4 with tiered policy; add Step 1.2 sub-bullet on effect classification + optional approval hook.

**Focus 5 — Compaction strategy correctness (OQ-6)**

- **Summary answer:** Hybrid — summarize-and-replace for pre-tool narrative history plus bounded tool-result eviction; avoid naive sliding-window truncation.
- **Rationale:** Step 1.4 says "compaction = an `agenerate` summarization call" but does not preserve tool-call/result pairing. Sliding-window drops arbitrary message boundaries and breaks Anthropic tool-use sequences. Tool-result eviction (drop oldest tool results first, keep recent pairs intact) plus summary of pre-tool turns preserves loop correctness and FR-6 cache breakpoints on system + tool blocks.
- **Assumptions / conditions:** Compaction runs only after mapped `ContextWindowExceededError`; post-compaction transcript must validate pair integrity before retry.
- **Suggested improvements:** Expand Step 1.4 with ordered strategy; add acceptance test requirement in plan §D or Step 1.4 validation note.

**Focus 6 — FR-13/FR-14 Concierge posture under chat layer**

- **Summary answer:** Partial — structural `READ_ACTIONS`-only registry preserves posture; FR-14 banner + cost line are necessary but not sufficient without execution-layer tests.
- **Rationale:** Step 4a and FR-13 ("registry receives only the two read tools") block write actions at construction. FR-14 addresses cost disclosure. Residual risks: model hallucinating unregistered tool names (FR-9 must reject), dynamic registry mutation, or UX implying autonomy despite banner.
- **Assumptions / conditions:** ToolRegistry rejects unknown tool names; Concierge consumer uses frozen tool list; banner persists for session lifetime.
- **Suggested improvements:** Add Concierge integration test matrix to Increment 4a; extend FR-14 with "reject unregistered tool calls" acceptance criterion (requirements-side).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Mark Increment 0 Steps 0.1–0.2 as **partially complete** per landed spike (`ClaudeAgent.agenerate_tools`, `models.py` types, `tests/unit/agents/test_agentic_tools_spike.py`); retitle Step 0.2 remainder as "OpenAI adapter + multi-message `messages` param." | Plan still reads as greenfield ("Add `AgenticTurn`") while code exists — implementers may duplicate or conflict with spike. | §B Increment 0, Steps 0.1–0.2 | Diff plan against `git` spike files; confirm no duplicate type definitions |
| R1-S2 | Interfaces | high | In Step 1.1, require `AgenticSession` to call `agent.supports_tool_use()` before `agenerate_tools` and raise a typed error for unsupported agents — mirror spike's opt-in contract. | Step 1.1 says "calling `agenerate_tools`" but omits the capability gate the spike added on `BaseAgent` (`agents/base.py:262-268`). Mixed-fleet loops will hit `NotImplementedError` at runtime without an upfront check. | §B Step 1.1 | Unit test: session with `MockAgent` (`supports_tool_use() == False`) fails before API call |
| R1-S3 | Data | critical | Expand Step 1.4 compaction to a **three-phase policy**: (1) evict oldest tool-result messages over size threshold, (2) summarize pre-tool narrative turns, (3) validate tool-call/result pair integrity before retry — resolve OQ-6 in-plan. | Step 1.4: "compaction = an `agenerate` summarization call" is insufficient for FR-3/FR-4; naive summarization breaks tool-use transcripts. | §B Step 1.4 | Fixture transcript with interleaved tool calls; after compaction, re-run provider adapter smoke test |
| R1-S4 | Security | high | Add Step 1.2 sub-task: `ToolRegistry` registers each tool with an **effect class** (`read`/`write`/`destructive`) and routes `write`+ to an optional approval callback — prerequisite for OQ-7 before Step 4b/4c. | FR-13 covers Concierge only; Step 4c exposes full MCP tool surface with no plan-level safety seam. | §B Steps 1.2, 4b, 4c | Register mock `destructive` tool; assert loop blocks until approval callback returns true |
| R1-S5 | Architecture | medium | Step 4c: specify `mcp/client.py` as a **thin generic adapter** over shared gateway transport (connection pool, circuit breaker, rate limit from `mcp/gateway.py`) — not a parallel MCP stack. | `[D4]` correctly splits client from gateway but Step 4c reads like a standalone port; duplicating resilience violates DRY and ops consistency. | §B Increment 4c | Architecture test: client module imports gateway resilience helpers, no second circuit-breaker implementation |
| R1-S6 | Ops | medium | Add Step 1.6 (or expand 1.1): **trajectory log** per OQ-3 resolution — append-only turn/tool-result record under `.startd8/` separate from `session_tracking.py` metrics. | Requirements §0 resolves OQ-3 ("new trajectory log for turns/tool-results") but plan mapping has no increment/step — observability gap for debugging agentic loops. | §B Increment 1 (new Step 1.6); §C add FR-trajectory row | Integration test writes log on multi-turn session; file parseable JSON lines |
| R1-S7 | Validation | medium | Step 4b: note **non-streaming fallback** until Increment 2 — TUI replaces `agent.generate` at `mixin_enhancement_chain.py:467` but must not block on streaming render. | Step 4b says "render streamed turns" while Increment 2 (FR-2) is deferrable — creates sequencing contradiction for first TUI ship. | §B Step 4b | TUI integration test passes with `supports_streaming() == False` agent |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | Add §D risk: **FR-0 API shape drift** — spike `agenerate_tools(prompt: str, ...)` vs FR-1 loop needing full `messages` history; pick one threading model before Increment 1. | Increment 1 `AgenticSession` holds `messages` (Step 1.1) but spike API is single-string prompt (`agents/base.py:271-275`) — silent rework tax if not decided now. | §D Risks; cross-ref Step 0.2 | Spike test updated to accept `messages: list[dict]` OR loop wraps prompt-only until Step 0.5 |

#### Requirements Coverage

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-0 | Increment 0 (0.1–0.2) | Partial | Spike landed Claude path; OpenAI + `messages` threading not planned as explicit substeps |
| FR-1 | Step 1.1 | Partial | Missing `supports_tool_use()` gate, trajectory log (OQ-3) |
| FR-2 | Increment 2 | Full | — |
| FR-3 | Step 1.4 | Partial | Compaction strategy unspecified; pair integrity not validated |
| FR-4 | Steps 1.3 + 1.4 | Partial | Token ceiling read path present; compaction algorithm gap |
| FR-5 | Step 3.2 | Full | Optional, correctly deferred |
| FR-6 | Step 3.1 | Full | — |
| FR-7 | Step 1.5 | Full | — |
| FR-8 | Step 1.5 | Full | — |
| FR-9 | Steps 1.2 + 0.2 | Partial | No tool effect classification or unknown-tool rejection in plan |
| FR-10 | Step 4b | Partial | Streaming assumed before Increment 2; line-number drift vs requirements |
| FR-11 | Step 4c | Partial | Client/gateway seam underspecified; resilience reuse not stated |
| FR-12 | Step 4a | Full | — |
| FR-13 | Step 4a | Partial | Structural enforcement planned; execution-layer tests not in plan |
| FR-14 | §D + Step 4a | Partial | Cost/posture noted; testable acceptance criteria absent from plan |

#### Review Round R2 — gpt-5.5 — 2026-06-25 01:52:00 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-25 01:52:00 UTC
- **Scope**: Second-pass architectural review - provider dialect seams, loop safety bounds, retry/idempotency, cache correctness, and tool-result hygiene

**Executive summary**

- R1 correctly identifies the foundational API-shape and safety gaps; this pass focuses on execution details that become expensive once the loop is merged.
- The plan currently mixes "OpenAI-format specs" in `ToolRegistry` with provider-native Anthropic specs in `BaseAgent.agenerate_tools`; add an explicit translation layer.
- `AgenticSession` needs loop-level termination controls before any consumer ships, or a model can spin indefinitely through harmless read tools.
- Retry and compaction can accidentally re-execute tool calls; add an idempotency ledger keyed by provider tool-call IDs.
- Prompt caching at the tool boundary needs a tool-schema hash so a cached stale tool block cannot outlive registry changes.
- MCP and Concierge tool results need redaction and truncation before being fed back to the model, especially when survey outputs contain local paths or config fragments.
- Keep additive opt-in for v1, but make the capability discovery path visible in tests and user-facing errors.
- R1's major suggestions should be triaged before implementation; this pass adds adjacent requirements rather than replacing them.

##### Sponsor focus — R2 delta answers

**Focus 1 — FR-0 primitive shape (additive opt-in vs Protocol change)**

- **Summary answer:** Keep additive opt-in for v1, but add an explicit "tool-use capability matrix" artifact so the cost of additive support is managed rather than hidden.
- **Rationale:** R1's compatibility argument is sound. The additional risk is discovery drift: callers see a uniform `BaseAgent` type while only some instances can run tools, so Step 1.1 needs a typed unsupported-agent error and a provider/model capability test matrix.
- **Assumptions / conditions:** `AgenticSession` is the only high-level entry point for tool loops and always checks `supports_tool_use()`.
- **Suggested improvements:** Add a small Increment 0 deliverable: provider capability table covering Claude, OpenAI, and unsupported providers.

**Focus 2 — `AgenticTurn` location (OQ-8)**

- **Summary answer:** `models.py` remains the right home; the missing piece is not relocation but a companion transcript/message type for Increment 1.
- **Rationale:** The sibling-type precedent in `models.py` is strong. However, Step 1.1 introduces loop messages and tool results, which are different from provider turn results; those can live in `agents/agentic.py` or a small loop-local module without moving `AgenticTurn`.
- **Assumptions / conditions:** Provider-facing return types stay in `models.py`; loop-internal transcript records are not exported as stable SDK models until proven.
- **Suggested improvements:** Resolve OQ-8 as `models.py`; add a separate note for loop-local transcript envelope design.

**Focus 3 — `mcp/client.py` boundary (FR-11)**

- **Summary answer:** Separate `mcp/client.py` is correct, with one extra constraint: it should share gateway resilience primitives rather than duplicate them.
- **Rationale:** The gateway's skill/workflow API is not the same abstraction as generic MCP tools. The clean seam is `mcp/client.py` for MCP protocol operations, and shared lower-level connection/rate-limit/circuit-breaker helpers underneath both client and gateway.
- **Assumptions / conditions:** `mcp/client.py` exposes only `list_tools`/`call_tool` and does not import Concierge or workflow registries.
- **Suggested improvements:** Add a short boundary diagram or bullet under Step 4c.

**Focus 4 — Tool-execution approval gate (OQ-7)**

- **Summary answer:** Effectful tools need approval or pre-authorization in v1; read-only tools need loop bounds and result hygiene, not prompts.
- **Rationale:** R1 covers effect classification. This pass adds that even read-only tools can create cost/infinite-loop risk, so approval is not the only safety mechanism.
- **Assumptions / conditions:** Tool metadata includes effect class, timeout, max result size, and retry policy.
- **Suggested improvements:** Add loop controls to Step 1.1/1.2 and effectful approval to Step 1.2.

**Focus 5 — Compaction strategy correctness (OQ-6)**

- **Summary answer:** Use R1's hybrid strategy, and add an idempotency ledger so retry after compaction cannot replay already executed tool calls.
- **Rationale:** Preserving tool-call/result pairing prevents malformed transcripts; it does not by itself prevent duplicate side effects if the retry boundary is placed after execution. The plan should name where execution is committed.
- **Assumptions / conditions:** Tool call IDs are persisted for the session; tools can opt into stronger idempotency keys where supported.
- **Suggested improvements:** Add Step 1.1 or 1.5 sub-task for replay-safe execution state.

**Focus 6 — FR-13/FR-14 Concierge posture under chat layer**

- **Summary answer:** Structural read-only registration is sufficient for write prevention, but not sufficient for privacy and implication-of-autonomy risks.
- **Rationale:** `survey`/`assess` can still return local project details that the model will summarize. The plan should redact secrets and bound outputs before re-entry, and FR-14 should require the UI to distinguish "suggested next step" from "performed action."
- **Assumptions / conditions:** Concierge tools remain exactly `READ_ACTIONS`.
- **Suggested improvements:** Add a Step 4a validation row for redaction, bounded outputs, and no-action wording.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | Add an explicit `ToolSpecAdapter` seam: `ToolRegistry` owns canonical OpenAI-format schemas, while each provider adapter translates them to provider-native shapes before `agenerate_tools`. | Step 1.2 says "`ToolRegistry` (OpenAI-format specs)" but `BaseAgent.agenerate_tools` currently documents provider-native Anthropic specs; without a seam, Claude/OpenAI support will diverge immediately. | §B Step 1.2 and Step 0.2 | Unit tests assert the same registered tool is rendered as Anthropic `{name,input_schema}` and OpenAI function/tool schema without changing registry input |
| R2-S2 | Risks | high | Add loop termination controls to `AgenticSession`: `max_turns`, `max_tool_calls_per_turn`, per-tool timeout, cancellation propagation, and a typed `AgenticLoopExceeded` result/error. | Step 1.1 describes a `while` loop but no stop conditions beyond "tool_calls is empty"; a model can repeatedly call read tools and burn tokens without violating FR-13. | §B Step 1.1 and Step 1.2 | Test a fake model that always requests a tool; session stops at configured max and records final state |
| R2-S3 | Risks | high | Add a tool-execution idempotency ledger keyed by provider tool-call ID, tool name, and normalized args; retries after transport/context failures must not re-run a committed tool call. | Step 1.5 reuses retry and Step 1.4 retries after compaction, but neither names the execution commit boundary. This is critical once MCP tools can be effectful. | §B Steps 1.1, 1.4, 1.5 | Simulate failure after tool execution and before model re-entry; assert retry reuses stored tool result instead of calling tool twice |
| R2-S4 | Security | medium | Add a `ToolResultPolicy` before results re-enter the model: redact known secret patterns, cap size, summarize large read-only outputs, and preserve full raw output only in local trajectory logs. | Step 1.1 appends results directly and Step 4a wraps Concierge read actions; read-only does not mean safe-to-prompt, especially for project surveys. | §B Step 1.1, Step 4a, and §D risks | Fixture with `.env`-like content in a tool result; model transcript receives redacted/truncated output while trajectory log stores policy metadata |
| R2-S5 | Ops | medium | For FR-6, include a tool-schema hash in the prompt-cache boundary and invalidate cached tool blocks when registry contents or descriptions change. | Step 3.1 caches the tool block and system prompt, but agentic correctness depends on the model seeing the exact current tool contract. | §B Step 3.1 | Change a tool schema between turns; assert cache key changes and stale tool definition is not reused |
| R2-S6 | Validation | medium | Add a cross-provider smoke matrix for FR-0 and FR-9 covering: zero tools, one tool, multiple tools, malformed args, unsupported agent, and final text with no tool calls. | The spike has Claude tests, but the plan's "Then OpenAI" and mixed-fleet loop need parity checks before consumers depend on the primitive. | §B Increment 0 and Increment 1 validation notes | Parametrized tests run against Claude fake response, OpenAI fake response, and unsupported `MockAgent` |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: Important to prevent duplicate type/API work now that Increment 0 has partially landed.
- R1-S2: Capability gating is required if additive opt-in remains the boundary.
- R1-S3: Pair-preserving compaction is foundational for any provider tool protocol.
- R1-S4: Effect classification is the right basis for approval policy.
- R1-S5: Reusing gateway resilience avoids a second MCP reliability stack.
- R1-S6: Trajectory logging is necessary for debugging replay, compaction, and cost questions.
- R1-S8: The prompt-vs-messages API drift should be resolved before `AgenticSession` is implemented.

**Disagreements**:
- None.

## Requirements Coverage Matrix — R1

| Requirement ID | Plan Section / Task | Coverage | Notes |
| ---- | ---- | ---- | ---- |
| FR-0 | §B Increment 0, Steps 0.1–0.2 | Partial | Claude spike complete; OpenAI + message threading remain |
| FR-1 | §B Step 1.1 | Partial | Needs capability gate + OQ-3 trajectory logging step |
| FR-2 | §B Increment 2 | Covered | Explicitly deferrable |
| FR-3 | §B Step 1.4 | Partial | Overflow recovery planned; compaction algorithm TBD (OQ-6) |
| FR-4 | §B Steps 1.3, 1.4 | Partial | Budget read path OK; compaction detail missing |
| FR-5 | §B Step 3.2 | Covered | Optional increment |
| FR-6 | §B Step 3.1 | Covered | Prompt caching at `agenerate_tools` boundary |
| FR-7 | §B Step 1.5 | Covered | Reuses `costs/` |
| FR-8 | §B Step 1.5 | Covered | Reuses `utils/retry.py` |
| FR-9 | §B Steps 1.2, 0.2 | Partial | ToolRegistry planned; effect/safety routing not specified |
| FR-10 | §B Step 4b | Partial | Streaming/render sequencing conflict with Increment 2 deferral |
| FR-11 | §B Step 4c | Partial | New client correct; gateway reuse not documented |
| FR-12 | §B Step 4a | Covered | Thinnest consumer, first in sequence |
| FR-13 | §B Step 4a | Partial | Structural READ_ACTIONS; validation tests not in plan |
| FR-14 | §D, Step 4a | Partial | Posture/cost reframing noted; executable criteria missing |

## Requirements Coverage Matrix — R2

| Requirement ID | Plan Section / Task | Coverage | Notes |
| ---- | ---- | ---- | ---- |
| FR-0 | §B Increment 0, Steps 0.1-0.2 | Partial | Needs canonical tool-schema translation and provider parity smoke matrix |
| FR-1 | §B Step 1.1 | Partial | Needs loop bounds, cancellation, and replay-safe transcript state |
| FR-2 | §B Increment 2 | Covered | Deferrable streaming path remains appropriate |
| FR-3 | §B Step 1.4 | Partial | Needs idempotency behavior for retry after compaction |
| FR-4 | §B Steps 1.3, 1.4 | Partial | Needs compaction plus tool-result policy to manage large outputs |
| FR-5 | §B Step 3.2 | Covered | Optional effort cascade remains separable |
| FR-6 | §B Step 3.1 | Partial | Needs cache invalidation keyed by tool schema hash |
| FR-7 | §B Step 1.5 | Covered | Cost reuse is planned |
| FR-8 | §B Step 1.5 | Partial | Retry schedule planned; idempotency/replay boundary missing |
| FR-9 | §B Steps 1.2, 0.2 | Partial | Needs provider spec adapter, tool-result policy, and malformed-args tests |
| FR-10 | §B Step 4b | Partial | Still depends on non-streaming fallback from R1 |
| FR-11 | §B Step 4c | Partial | Generic client planned; shared resilience seam should be explicit |
| FR-12 | §B Step 4a | Covered | Scope and sequencing are clear |
| FR-13 | §B Step 4a | Partial | Write prevention clear; privacy/result hygiene missing |
| FR-14 | §D, Step 4a | Partial | Cost disclosure noted; no-action wording and result redaction should be testable |

#### Review Round R3 — gpt-5.5 — 2026-06-25 01:55:00 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-25 01:55:00 UTC
- **Scope**: Third-pass review - transcript codecs, argument validation, concurrent tool-call semantics, session budgets, and typed error taxonomy

**Executive summary**

- R1/R2 cover the key boundary decisions; R3 focuses on execution contracts that should be set before implementation hardens.
- The plan needs a provider message codec, separate from R2's tool-schema adapter, so canonical session history can round-trip through Anthropic/OpenAI role conventions.
- Tool argument validation is not yet specified; unknown-tool rejection is not enough if the known tool receives malformed arguments.
- Multi-tool turns need an ordering/concurrency rule before Step 1.1 dispatches multiple calls.
- FR-7 reuses cost telemetry but not cost enforcement; agentic loops need per-session token/dollar guards.
- Step 1.4 names provider-agnostic exception mapping, but the plan does not define the error taxonomy implementers should converge on.

##### Sponsor focus — R3 delta answers

**Focus 1 — FR-0 primitive shape (additive opt-in vs Protocol change)**

- **Summary answer:** Additive opt-in still holds, but the plan should add typed capability errors so unsupported providers fail with actionable routing guidance.
- **Rationale:** R1/R2 already endorse additive opt-in. The remaining cost is not compatibility; it is operator confusion when a mixed-fleet session chooses a non-tool provider.
- **Assumptions / conditions:** `AgenticSession` owns provider selection or receives a single agent already selected.
- **Suggested improvements:** Add `ToolUseUnsupportedError(provider, model)` to the Step 1.1 validation path.

**Focus 2 — `AgenticTurn` location (OQ-8)**

- **Summary answer:** Keep `AgenticTurn` in `models.py`, and add loop-local transcript/message codecs elsewhere.
- **Rationale:** `AgenticTurn` is a provider return type; transcript serialization is a loop concern. Separating those avoids bloating `models.py` while preserving discoverability for generation results.
- **Assumptions / conditions:** Provider adapters do not import `agents/agentic.py`.
- **Suggested improvements:** Add `MessageCodec`/`TranscriptCodec` as an Increment 1 implementation detail.

**Focus 3 — `mcp/client.py` boundary (FR-11)**

- **Summary answer:** Separate client remains correct; R3 adds that MCP tool metadata should feed the same validation/concurrency policies as built-in tools.
- **Rationale:** If MCP tools bypass the registry's schema validation, approval, timeout, and ordering rules, Step 4c becomes a safety bypass around Step 1.2.
- **Assumptions / conditions:** `mcp/client.py` returns enough schema/effect metadata to register tools canonically.
- **Suggested improvements:** Add MCP tool metadata normalization to Step 4c.

**Focus 4 — Tool-execution approval gate (OQ-7)**

- **Summary answer:** Approval is necessary for effectful tools, but deterministic argument validation and concurrency policy are equally necessary.
- **Rationale:** A user can approve the right tool with wrong arguments; the loop still needs schema validation before execution and deterministic result ordering afterward.
- **Assumptions / conditions:** Tool schemas are executable validators, not only model-facing documentation.
- **Suggested improvements:** Add pre-execution validation to Step 1.2.

**Focus 5 — Compaction strategy correctness (OQ-6)**

- **Summary answer:** Keep R1/R2's hybrid strategy; additionally, compaction should operate on canonical transcript records, not provider-formatted messages.
- **Rationale:** Provider messages differ in role and tool-result representation. Summarizing canonical records first and rendering to provider format last lowers the chance of producing invalid Anthropic/OpenAI transcripts.
- **Assumptions / conditions:** Message codecs are reversible enough for validation.
- **Suggested improvements:** Add canonical transcript model + provider codec tests.

**Focus 6 — FR-13/FR-14 Concierge posture under chat layer**

- **Summary answer:** Concierge posture is preserved only if read-only tool results are bounded, validated, and displayed as advisory evidence rather than performed actions.
- **Rationale:** Prior rounds covered registry freezing and redaction. R3 adds that UI wording should distinguish "I found" from "I changed" and that tool-result validation applies even to `survey`/`assess`.
- **Assumptions / conditions:** Concierge stays on READ_ACTIONS.
- **Suggested improvements:** Add a UI wording check and read-tool argument validation case to Step 4a.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Architecture | high | Add a provider `MessageCodec` seam: `AgenticSession` stores canonical transcript records, and Claude/OpenAI adapters render provider-specific roles/tool-result message shapes at the boundary. | Step 1.1 says the session "holds `messages`" and Step 0.2 calls `agenerate_tools(messages, tools, **kw)`, but Anthropic and OpenAI represent assistant tool calls and tool results differently. R2 covers tool schemas, not transcript encoding. | §B Step 1.1 and Step 0.2 | Golden tests render the same canonical transcript to valid Anthropic and OpenAI request payloads |
| R3-S2 | Validation | high | Add pre-execution argument validation in `ToolRegistry`: validate model-supplied args against the registered schema before calling the Python/MCP tool, and feed validation failures back as typed tool errors. | R1 covers unknown tools and R2 covers malformed provider blocks, but a known tool with bad args can still reach execution. Step 1.2 currently only says "ToolRegistry (OpenAI-format specs)." | §B Step 1.2 | Fake model calls known tool with missing/extra/wrong-type args; callable is not invoked and transcript receives a validation error result |
| R3-S3 | Risks | medium | Define multi-tool dispatch semantics: default sequential execution preserving `tool_calls` order; allow bounded parallelism only for tools marked `read` and order results by original call index. | `AgenticTurn` can return a list of tool calls and Step 1.1 says "dispatches tool calls"; without a concurrency rule, implementations may reorder results or parallelize effectful calls accidentally. | §B Step 1.1 and Step 1.2 | Test two tool calls with different latency; transcript result order remains deterministic |
| R3-S4 | Ops | medium | Add per-session budget enforcement using existing `costs/budget.py`: max turns/tokens/dollars should be checked before each model re-entry and surfaced in the cost line for Concierge/TUI. | Step 1.5 records usage via `costs/`, but agentic loops multiply calls; FR-14's per-session cost line benefits from the same guardrail. | §B Step 1.5 and Step 4a/4b | Configure a low session budget; loop stops before the next model turn and reports budget-exceeded state |
| R3-S5 | Interfaces | medium | Specify typed agentic errors (`ContextWindowExceededError`, `ToolUseUnsupportedError`, `ToolArgumentValidationError`, `ToolExecutionError`, `AgenticLoopExceeded`) and provider mapping rules. | Step 1.4 mentions "provider-agnostic exception mapping" but the existing generic `APIError`/`AgentError` taxonomy does not name agentic-loop failure modes. | §B Step 1.4 and §D risks | Unit tests map simulated provider errors/statuses into the typed taxonomy and consumers render user-safe messages |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S2: Capability gating remains prerequisite for additive opt-in.
- R1-S3: Pair-preserving compaction is still the highest-risk correctness issue.
- R1-S4 and R2-S2: Approval/effect policy and loop bounds should ship together.
- R2-S1: Tool-schema adapters are necessary; R3-S1 adds the parallel message-codec seam.
- R2-S3: Idempotency is essential once retry and compaction interact with tool execution.
- R2-S4: Tool-result redaction should be part of the core loop, not only Concierge.

**Disagreements**:
- None.

## Requirements Coverage Matrix — R3

| Requirement ID | Plan Section / Task | Coverage | Notes |
| ---- | ---- | ---- | ---- |
| FR-0 | §B Increment 0, Steps 0.1-0.2 | Partial | Needs provider message codec plus typed unsupported-tool-use errors |
| FR-1 | §B Step 1.1 | Partial | Needs canonical transcript storage and deterministic multi-tool dispatch |
| FR-2 | §B Increment 2 | Covered | Streaming remains separate; codec should be reusable for streamed deltas later |
| FR-3 | §B Step 1.4 | Partial | Needs explicit typed context-window exception and canonical transcript compaction |
| FR-4 | §B Steps 1.3, 1.4 | Partial | Budgeting and compaction should operate on canonical records |
| FR-5 | §B Step 3.2 | Covered | Optional cascade remains isolated |
| FR-6 | §B Step 3.1 | Partial | Prior R2 schema-hash cache invalidation still applies |
| FR-7 | §B Step 1.5 | Partial | Telemetry reuse covered; per-session enforcement missing |
| FR-8 | §B Step 1.5 | Partial | Retry reuse covered; typed errors and budget stop states missing |
| FR-9 | §B Steps 1.2, 0.2 | Partial | Needs argument validation and dispatch ordering |
| FR-10 | §B Step 4b | Partial | Consumer should surface budget/typed errors cleanly |
| FR-11 | §B Step 4c | Partial | MCP tool metadata should normalize into registry validation policy |
| FR-12 | §B Step 4a | Covered | Consumer scope remains clear |
| FR-13 | §B Step 4a | Partial | Read-only tools still need arg validation and advisory wording |
| FR-14 | §D, Step 4a | Partial | Cost line needs budget state, not only accumulated spend |

#### Review Round R4 — gpt-5.5 — 2026-06-25 01:56:00 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-25 01:56:00 UTC
- **Scope**: Fourth-pass review - public API rollout, resumability, observability, MCP discovery drift, and approval auditability

**Executive summary**

- Prior rounds cover the central loop mechanics; R4 focuses on operational hardening and release shape that become difficult to retrofit after consumers depend on the loop.
- The plan does not say whether `AgenticSession`, `AgenticTurn`, and registry APIs are stable public SDK surface or experimental imports.
- The trajectory log proposed in R1 should have a resume/replay contract, not only a debug-recording role.
- OTel instrumentation should be planned as part of Increment 1 while the loop boundaries are still clean.
- MCP tool discovery can drift during a session; freeze or version the discovered tool snapshot before approvals/cache decisions depend on it.
- Effectful-tool approvals need an audit artifact with argument hashes and operator decision metadata.
- Consumer rollout should preserve a fallback to the existing one-shot path until the agentic loop has provider parity and budget controls.

##### Sponsor focus — R4 delta answers

**Focus 1 — FR-0 primitive shape (additive opt-in vs Protocol change)**

- **Summary answer:** Additive opt-in remains the right v1 choice, but the plan should mark the new imports as experimental until Claude+OpenAI parity and loop consumers pass.
- **Rationale:** Additive avoids breaking downstream repos, but public import paths can still become a de facto contract. The rollout plan should separate "available for spike/early consumers" from "stable SDK API."
- **Assumptions / conditions:** The package can expose experimental APIs without SemVer guarantees pre-1.0.
- **Suggested improvements:** Add a Step 0.5 public API/export decision with `startd8.agents.agentic` and `startd8.models.AgenticTurn` status.

**Focus 2 — `AgenticTurn` location (OQ-8)**

- **Summary answer:** `models.py` remains acceptable; document whether it is exported as stable or internal-experimental.
- **Rationale:** The location question is mostly resolved by prior rounds. The remaining risk is downstream import churn if `AgenticTurn` moves after users adopt it.
- **Assumptions / conditions:** `models.py` stays the provider-result home.
- **Suggested improvements:** Add import-path stability note for `AgenticTurn`/`ToolCallRequest`.

**Focus 3 — `mcp/client.py` boundary (FR-11)**

- **Summary answer:** Keep a separate client and add a per-session discovered-tool snapshot to handle server-side drift.
- **Rationale:** R1/R2/R3 cover the client/gateway and metadata seams. Drift remains: `list_tools` can change between discovery, approval, caching, and execution.
- **Assumptions / conditions:** MCP tools can be listed at session start and refreshed explicitly.
- **Suggested improvements:** Step 4c should freeze tool definitions per session or force re-approval/cache invalidation on refresh.

**Focus 4 — Tool-execution approval gate (OQ-7)**

- **Summary answer:** Approval should be auditable, not only interactive.
- **Rationale:** Prior rounds establish when approval is required. For MCP/TUI surfaces, a later operator needs to know which tool, arguments hash, effect class, and user decision authorized an execution.
- **Assumptions / conditions:** Raw sensitive args may be redacted; hashes are enough for tamper evidence.
- **Suggested improvements:** Add approval audit entries to the trajectory log.

**Focus 5 — Compaction strategy correctness (OQ-6)**

- **Summary answer:** Pair-preserving compaction should be coupled with replay/resume validation.
- **Rationale:** A compacted transcript is not only used immediately; after crash/restart, the persisted state must still satisfy the same invariants. If resume is out of v1, the plan should say trajectory logs are non-resumable.
- **Assumptions / conditions:** Increment 1 writes some durable trajectory artifact.
- **Suggested improvements:** Add a yes/no resume scope decision to Step 1.6.

**Focus 6 — FR-13/FR-14 Concierge posture under chat layer**

- **Summary answer:** Posture is preserved if the rollout includes fallback and telemetry showing the chat layer did not execute write actions.
- **Rationale:** Structural READ_ACTIONS registration prevents writes, but rollout confidence improves if spans/logs expose tool names/effects and fallback keeps deterministic Concierge available.
- **Assumptions / conditions:** Existing deterministic Concierge remains callable.
- **Suggested improvements:** Add Concierge feature flag/fallback and OTel event assertions.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Architecture | medium | Add a Step 0.5 "public API/export policy": identify which symbols are stable vs experimental (`AgenticSession`, `ToolRegistry`, `AgenticTurn`, `ToolCallRequest`, typed errors) and where they are imported from. | The plan adds new SDK-native APIs but does not define their export surface; moving them after TUI/MCP/Concierge consume them will create avoidable downstream churn. | §B after Step 0.3 and §C mapping | Import smoke test verifies documented paths; docs label experimental symbols consistently |
| R4-S2 | Data | medium | Extend the Step 1.6 trajectory-log task (from R1-S6) with an explicit resume stance: either "debug-only, not resumable" or "resumable transcript with schema version, checksum, and invariant validation." | A log of turns/tool-results is useful, but implementers need to know whether crash recovery can replay or resume a session. Compaction/idempotency decisions depend on this scope. | §B Increment 1 new Step 1.6 | Kill/restart fixture either refuses resume with clear error or reconstructs canonical transcript and validates tool-call/result pairs |
| R4-S3 | Ops | medium | Add OTel spans/events for agentic runtime boundaries: session, model turn, tool call, compaction, approval decision, budget stop, and provider error mapping. | The SDK already has OTel conventions elsewhere; adding spans after loop code lands risks missing the clean boundaries and weakens debugging for multi-turn failures. | §B Increment 1 and §D risks | Trace test asserts span names/attributes include provider, model, tool name, effect class, status, cost, and session id |
| R4-S4 | Security | high | In Step 4c, freeze MCP `list_tools` results into a per-session tool snapshot with schema/effect metadata; any refresh must invalidate prompt cache and require re-approval for changed effectful tools. | Prior rounds cover client boundary and schema hashing, but not server-side discovery drift between `list_tools`, model prompt caching, approval, and `call_tool`. | §B Step 4c and Step 3.1 | Fake MCP server changes a tool schema/effect after discovery; session either keeps old snapshot or forces cache invalidation and approval |
| R4-S5 | Security | medium | Add approval audit records for TUI/MCP effectful tools: tool name, effect class, args hash, redaction policy, operator/session id, timestamp, and decision. | R1/R2 require approval, but no artifact proves what was approved later. This matters for debugging and for explaining why an effectful call ran. | §B Step 1.2 and Step 1.6 | Approval callback test writes an audit event; raw secrets absent, args hash stable for identical normalized args |
| R4-S6 | Risks | medium | Add consumer rollout/fallback steps: gate TUI/Concierge agentic mode behind a config flag and retain the existing one-shot/deterministic path until provider parity and session budget tests pass. | Increment 4 replaces consumer behavior after a large new runtime lands; fallback limits blast radius if the loop has provider-specific regressions. | §B Steps 4a and 4b; §D risks | Config test toggles agentic mode off and verifies legacy Concierge/TUI behavior still works |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S6: Trajectory logging is the base artifact R4-S2/R4-S5 build on.
- R2-S5: Tool-schema cache invalidation should include MCP discovery refreshes.
- R2-S6: Cross-provider smoke tests are required before marking imports stable.
- R3-S1: Canonical transcripts are prerequisite for resumability and OTel span correlation.
- R3-S4: Session budget enforcement should be visible in both traces and consumer UI.
- R3-S5: Typed errors make rollout/fallback behavior testable instead of string-matched.

**Disagreements**:
- None.

## Requirements Coverage Matrix — R4

| Requirement ID | Plan Section / Task | Coverage | Notes |
| ---- | ---- | ---- | ---- |
| FR-0 | §B Increment 0, Steps 0.1-0.2 | Partial | Needs public API/export policy before downstream adoption |
| FR-1 | §B Step 1.1 | Partial | Needs resume stance and OTel session/turn spans |
| FR-2 | §B Increment 2 | Covered | Streaming remains independent but should reuse OTel boundaries |
| FR-3 | §B Step 1.4 | Partial | Compaction should define persisted-state validity after restart |
| FR-4 | §B Steps 1.3, 1.4 | Partial | Budget stops should be observable and resumability-aware |
| FR-5 | §B Step 3.2 | Covered | Optional |
| FR-6 | §B Step 3.1 | Partial | Cache invalidation should include MCP discovery drift |
| FR-7 | §B Step 1.5 | Partial | Records usage; still needs spans and fallback visibility |
| FR-8 | §B Step 1.5 | Partial | Retry should be correlated with audit/idempotency records |
| FR-9 | §B Steps 1.2, 0.2 | Partial | Approval audit records and tool snapshot drift handling missing |
| FR-10 | §B Step 4b | Partial | Needs feature flag/fallback rollout |
| FR-11 | §B Step 4c | Partial | Needs per-session MCP tool snapshot and refresh semantics |
| FR-12 | §B Step 4a | Partial | Needs feature-flagged rollout while deterministic path remains |
| FR-13 | §B Step 4a | Partial | Needs telemetry proof that only read tools executed |
| FR-14 | §D, Step 4a | Partial | Cost line should align with session budget and trace data |
