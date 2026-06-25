# SDK-Native Agentic Tool-Use Loop — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-24
**Status:** Reviewed against implementation plan
**Author:** Neil Yashinsky

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass against the real code surfaced
> **8 discoveries** — the central one being that the "thin loop on top of the provider layer"
> assumption was false: there is no tool-use or streaming primitive to build on.

| v0.1 Assumption | Planning Discovery (file:line) | Impact |
|-----------------|-------------------|--------|
| Loop sits "on" `agenerate()` (extend it) — FR-1 | `agenerate()` is **text-in/text-out only** (`agents/base.py:215`); the *only* tool-use path is `agenerate_structured` — a **single forced** tool for schema output (`claude.py:563`) | **New FR-0: a tool-use generation primitive must be built first** (Increment 0). Biggest reframe. |
| `GenerateResult` can carry tool calls | It's a frozen 3-tuple `NamedTuple` (`models.py:106`) | Need a new `AgenticTurn`/`ToolCallRequest` type; don't overload `GenerateResult`. |
| Streaming substrate exists at agent level — FR-2 | Provider protocol has `supports_streaming/get_model_info/estimate_safe_output` but **agents implement none** (`providers/protocol.py:141-187`) | Streaming is a **separate, deferrable increment**; a non-streaming loop ships first. Tool-call *accumulation* (FR-2) moves with streaming. |
| MCP gateway can drive arbitrary tools — FR-11 | Gateway is **skill/workflow-oriented** (`execute_skill`/`list_skills`), **not** a generic `list_tools`/`call_tool` MCP client (`mcp/gateway.py`) | MCP agent surface needs a **new `mcp/client.py`** (port ml-intern `tools.py`); it is the **heaviest** consumer, not the lightest. |
| Three consumers are uniformly "thin" | Concierge = trivial; TUI = thin; **MCP surface = not thin** (needs the new client) | Re-sequence: Concierge/TUI prove the loop **before** the MCP client is built. |
| Cost cache-token normalization may need work — FR-7 | **Already present & better than ml-intern** (`costs/models.py:99`, `pricing.py:537`) | Reuse as-is; confirmed. |
| Concierge front-end is still `$0`/deterministic | Concierge *core* is `$0 no LLM` (`core.py:5`), but a **conversational layer spends LLM** for the dialogue | **New FR-14**: the chat layer is **not** `$0`; posture ("assist, not operate") is preserved but the `$0`-deterministic property is **not** — must be disclosed. |
| Building from scratch | `agenerate_structured` is a usable **reference** for forcing `tool_use` on Claude | Generalize it into the FR-0 primitive rather than greenfield. |

**Resolved open questions:**
- **OQ-1 → Streaming deferred to Increment 2.** A non-streaming `agenerate_tools`-based loop is v1.
- **OQ-2 → Parallel runtime, no merge.** `orchestration.py`/contractors are deterministic pipelines;
  the agentic loop is a distinct runtime. They do not fold together.
- **OQ-3 → Extend `session_tracking.py` for metrics; new trajectory log for turns/tool-results.**
- **OQ-4 → Yes (now FR-14).** Concierge front-end needs a posture banner **and** a cost-visibility line,
  because the chat layer reintroduces LLM cost the deterministic core never had.
- **OQ-5 → Claude + OpenAI first** (both evidence the `tool_use` mechanism); Go/Node/Java/C# later.

---

## 1. Problem Statement

The startd8 SDK has every *substrate* for an agentic runtime — a multi-provider abstraction
(`providers/`), cost/cache-token telemetry (`costs/`), retry/backoff (`utils/retry.py`), an MCP
gateway + FastMCP server (`mcp/`), and truncation detection (`truncation_detection.py`) — but **no
multi-turn, tool-using agent loop** that ties them together. Every model interaction today is a
single-shot `agent.generate(prompt)` → text.

The HF `ml-intern` project (LiteLLM-based) is a clean reference implementation of exactly that
missing loop. We want to **port its patterns** onto the SDK's *own* layers (not adopt LiteLLM —
the SDK's cross-provider cache-token normalization is already better), then expose the loop through
three consumers.

### Gap table

| Component | Current State | Gap |
|-----------|--------------|-----|
| Agentic loop | none | multi-turn, tool-calling, async loop missing |
| TUI chat (`tui/mixin_enhancement_chain.py:391`) | stateless one-shot `agent.generate()` REPL — no history | needs real conversation + tool use |
| MCP agent surface | FastMCP server *exposes* tools; nothing *drives* them in a loop | an agent that consumes the SDK's own MCP tools |
| Concierge (`concierge/`) | deterministic `$0`, read-only `survey`/`assess` (`core.py:5`) | a conversational front-end — without losing read-only/assist posture |

---

## 2. Requirements

### Foundational — the tool-use primitive (NEW, prerequisite)

- **FR-0 — Tool-use generation primitive.** `BaseAgent.agenerate_tools(messages, tools, **kw) ->
  AgenticTurn` returning text + zero-or-more `ToolCallRequest`s + usage + finish_reason. Implemented
  for **Claude first** (generalizing `agenerate_structured`, `claude.py:563`), then **OpenAI**. A new
  `AgenticTurn`/`ToolCallRequest` type carries tool calls — `GenerateResult` (frozen 3-tuple,
  `models.py:106`) **cannot**. *This did not exist in v0.1; it is the prerequisite for FR-1.*

### Foundational — the loop

- **FR-1 — `agents/agentic.py` AgenticSession.** A new async, multi-turn session object that holds
  conversation history and drives a model to completion across turns by calling **FR-0's
  `agenerate_tools`** (NOT `agenerate()`, which is text-only).
- **FR-2 — Streaming + tool-call accumulation.** *(Increment 2, deferrable.)* Stream model output;
  reassemble streamed `tool_calls` deltas (id, name, concatenated args) across chunks. Requires new
  provider-level streaming (none exists today). The non-streaming loop (FR-1) ships first.
- **FR-3 — Context-overflow recovery.** Catch a provider-agnostic context-window-exceeded error,
  trigger compaction, retry the turn.
- **FR-4 — Context compaction at the model ceiling.** Summarize older history when usage approaches
  the model's real input-token ceiling (read from provider model info).
- **FR-5 — Reasoning-effort probe-and-cascade (optional).** On model switch, probe highest effort and
  walk down until accepted; cache the working effort per model.
- **FR-6 — Prompt caching.** Inject Anthropic `cache_control` breakpoints (tool block + system
  prompt); no-op for non-Anthropic. (Finish the existing stub flag in `claude.py`.)
- **FR-7 — Reuse cost telemetry.** Record usage via `costs/` including cache tokens; do **not**
  reimplement cost math.
- **FR-8 — Reuse retry.** Use `utils/retry.py` backoff; add rate-limit-specific schedule.
- **FR-9 — Tool routing.** Present tools in OpenAI function-calling format; execute tool calls and
  feed results back into the loop. Tool sources are pluggable (built-in fns + MCP tools).

### Consumers (separate increments)

- **FR-10 — TUI chat consumer.** Replace the one-shot REPL at `tui/mixin_enhancement_chain.py:391`
  with an `AgenticSession`; gain multi-turn memory + streaming render.
- **FR-11 — MCP agent surface.** An agent that lists and calls the SDK's own FastMCP server tools
  through the loop. **Requires a new `mcp/client.py`** (generic `list_tools`/`call_tool` MCP client,
  ported from ml-intern `tools.py`) — the existing `mcp/gateway.py` is skill/workflow-oriented and
  cannot drive arbitrary MCP tools. **This is the heaviest consumer; sequence it last.**
- **FR-12 — Concierge conversational front-end.** A chat surface whose toolbox is **only** Concierge's
  read-only `survey`/`assess` (wrapping `handle_concierge_tool`, registering only `READ_ACTIONS`).
  Makes onboarding a dialogue. **Thinnest consumer; sequence it first.**

### Constraint

- **FR-13 — Concierge posture is inviolable.** The Concierge consumer must not gain write power or
  autonomy. Its tool set is restricted to `READ_ACTIONS`; no `instantiate-kickoff`/`log-friction`/
  `derive-contract`, no cascade, no gate writes. Enforcement is structural: the registry receives
  only the two read tools — write actions are never constructed for this surface.
- **FR-14 — Concierge chat-layer cost disclosure (NEW).** The Concierge front-end's *tools* stay
  `$0`/deterministic/read-only, but the *conversation* spends LLM tokens. The surface must show a
  posture banner ("assist, not operate — read-only") **and** a per-session cost line, so the
  capability's historical "`$0`, no LLM" property is not silently broken. Posture is preserved
  (explaining ≠ operating); the cost property is not, and that must be visible.

---

## 3. Non-Requirements

- Not adopting LiteLLM as a dependency (port patterns only).
- Not building a web/HTTP agent server (TUI + MCP + CLI surfaces only).
- Not replacing `orchestration.py` / contractor workflows (those are deterministic pipelines).
- Not enabling autonomous file writes from the loop in v1.
- Not a new provider; works with existing providers.

---

## 4. Open Questions

*All five v0.1 open questions were resolved by planning — see §0 "Resolved open questions."* Remaining
items for CRP/implementation:

- **OQ-6.** Compaction strategy: summarize-and-replace vs. sliding-window vs. tool-result eviction —
  which preserves agentic correctness best? (Increment 1.4.)
- **OQ-7.** Tool-execution safety: do non-Concierge surfaces (TUI, MCP) need a per-tool approval gate
  (ml-intern has one) before v1, or is read-only-by-default sufficient?
- **OQ-8.** Should the new `AgenticTurn` type live in `models.py` or a new `agents/agentic_types.py`?

---

*v0.2 — Post-planning self-reflective update. **1 requirement added as prerequisite (FR-0),
1 added (FR-14), 4 corrected (FR-1, FR-2, FR-11, FR-12), 5 open questions resolved.** Central
correction: there is no tool-use/streaming primitive to build on — the foundational scope is larger
than v0.1 assumed, and the three consumers are not uniformly thin.*

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
- **Scope**: Requirements quality, acceptance criteria gaps, plan↔spike alignment (Feature Requirements)

**Executive summary**

- FR-0 text assumes `messages` param but Increment-0 spike ships `prompt: str` — requirements must declare v1 threading contract.
- FR-3/FR-4 lack testable acceptance criteria for post-compaction transcript integrity (OQ-6).
- FR-9 omits unknown-tool rejection and tool-error result shape — needed before multi-tool loops.
- OQ-7 should be resolved with tiered policy text, not left as open question through consumer increments.
- FR-10 line anchor (`:391`) disagrees with plan (`:467`) — pick canonical cite.
- FR-14 needs machine-verifiable checks beyond banner/cost copy.
- FR-13 should explicitly require frozen registry (no runtime tool registration) for Concierge consumer.
- Add FR-0 acceptance: `supports_tool_use()` false agents must not be used in tool loops.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | critical | Amend FR-0 to state v1 **message threading contract**: either (a) `agenerate_tools(messages: list[dict], tools, **kw)` as primary API, or (b) document prompt-only v1 with loop-owned history assembly — must match landed `BaseAgent` signature. | FR-0: "`agenerate_tools(messages, tools, **kw)`" conflicts with spike "`agenerate_tools(prompt: str, tools, **kw)`" (`agents/base.py:271-275`). Implementers cannot satisfy FR-0 and FR-1 simultaneously without clarification. | §2 FR-0 bullet | Contract test: FR-0 signature matches `BaseAgent` after chosen option; update spike tests accordingly |
| R1-F2 | Validation | high | Add acceptance criteria to FR-3/FR-4: after compaction, **every `tool_use` block has a matching tool-result message** and system prompt + recent tool block remain cache-eligible (FR-6). | FR-3: "trigger compaction, retry the turn" and FR-4: "Summarize older history" — no verifiable correctness bar; OQ-6 left entirely open. | §2 FR-3 and FR-4 bullets | Automated test: inject oversize transcript, compact, assert pair count invariant |
| R1-F3 | Interfaces | high | Extend FR-9 with: (1) **reject** tool calls whose `name` is not in the registered set (return provider-format tool-error to model), (2) standard **tool result envelope** (success/error, bounded payload size). | FR-9: "execute tool calls and feed results back" — silent skip of hallucinated tool names breaks agentic loops and Concierge posture (FR-13). | §2 FR-9 bullet | Unit test: model calls `fake_tool`; loop returns error result, continues without executing |
| R1-F4 | Security | high | Resolve OQ-7 in §4 with normative tiered policy: Concierge = FR-13 structural allowlist only; TUI/MCP = deny-by-default for `write`/`destructive` tools unless explicitly allowlisted or user-approved per session. | OQ-7: "per-tool approval gate ... or read-only-by-default sufficient?" — leaves safety architecture undecided while FR-11 exposes effectful MCP tools. | §4 OQ-7 → move to §2 new FR-15 or FR-9 constraint | Policy table in requirements; integration test for blocked destructive tool |
| R1-F5 | Validation | medium | Fix FR-10 file anchor: align with plan Step 4b (`tui/mixin_enhancement_chain.py:467`) or re-verify both lines and cite the **call site** that invokes `agent.generate(user_input)`. | FR-10 cites "`:391`" while plan Step 4b cites "`:467`" — undermines traceability for consumer increment. | §2 FR-10 bullet | `rg agent.generate mixin_enhancement_chain.py` confirms single canonical line in both docs |
| R1-F6 | Security | medium | Extend FR-13 with: Concierge consumer **must not** expose runtime `ToolRegistry.register()` — tool list frozen at session construction; add FR-14 acceptance: **session-lifetime** posture banner + running cost total updated after each turn. | FR-13: "registry receives only the two read tools" — does not forbid dynamic registration; FR-14 UI requirements are not testable as written. | §2 FR-13 and FR-14 bullets | Concierge integration test: assert registry length==2 after init; snapshot test for banner + cost widget |

#### Review Round R2 — gpt-5.5 — 2026-06-25 01:52:00 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-25 01:52:00 UTC
- **Scope**: Requirements second pass - execution bounds, provider schema translation, retry semantics, cache invalidation, and prompt hygiene

**Executive summary**

- R1 covers the major open safety and API-shape issues; R2 focuses on requirements that should be explicit before implementation begins.
- FR-1 needs bounded loop behavior, not just "drives a model to completion."
- FR-9 needs a canonical tool schema plus provider translation contract; otherwise "OpenAI function-calling format" conflicts with Claude-native implementation.
- FR-8 should distinguish retrying provider calls from retrying committed tool executions.
- FR-6 prompt caching must be invalidated when the tool contract changes.
- FR-13/FR-14 protect write posture and cost disclosure, but not sensitive data echoed through tool results.
- Acceptance criteria should include malformed arguments and provider adapter failures, not only happy-path tool calls.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Risks | high | Add a new requirement for bounded loop execution: `AgenticSession` must expose `max_turns`, `max_tool_calls_per_turn`, per-tool timeout, and cancellation behavior, with a typed terminal state when limits are reached. | FR-1 says the session "drives a model to completion across turns" and FR-9 says it "execute[s] tool calls and feed[s] results back"; neither defines what prevents infinite tool loops or runaway read-only cost. | §2 after FR-1 or as new FR-1a | Test a fake model that always requests a tool; assert session stops at configured limit and reports a non-success terminal state |
| R2-F2 | Interfaces | high | Amend FR-9 to define one canonical SDK tool schema and a provider translation layer; `ToolRegistry` should not leak Anthropic-native or OpenAI-native shapes to callers. | FR-9 says "Present tools in OpenAI function-calling format" while FR-0's Claude-first implementation generalizes `agenerate_structured`; provider adapters need a formal schema boundary. | §2 FR-9 bullet | Same registered tool renders correctly for Claude and OpenAI fake adapters from one canonical definition |
| R2-F3 | Risks | high | Extend FR-8/FR-9 with idempotency semantics: retries may replay provider requests before tool execution, but once a tool result is committed, retry must reuse the recorded result unless the tool declares itself idempotent and retry-safe. | FR-8 says "Use `utils/retry.py` backoff" and FR-9 says "execute tool calls"; together they create ambiguity about whether failures after tool execution can run tools twice. | §2 FR-8 and FR-9 bullets | Simulate exception after tool execution; assert the tool is not called again on retry and the stored result is reused |
| R2-F4 | Security | medium | Add prompt-hygiene acceptance criteria for tool results: redact known secret patterns, cap result size, and mark summarized/truncated results before sending them back to the model. | FR-13 restricts Concierge to `READ_ACTIONS`, and FR-14 discloses cost, but neither says how read-only outputs that contain local paths, config fragments, or secrets are handled. | §2 FR-9, FR-13, or FR-14 constraint text | Fixture tool returns `.env`-like content; transcript contains redacted value and a truncation/redaction marker |
| R2-F5 | Ops | medium | Strengthen FR-6: prompt caching must include a cache key or invalidation rule tied to the active tool schema, system prompt, and model provider. | FR-6 says "Inject Anthropic `cache_control` breakpoints (tool block + system prompt)" but does not define when a cached tool block is stale after tool registry changes. | §2 FR-6 bullet | Change a tool description/schema between turns; assert the cache boundary changes and old tool definitions are not reused |
| R2-F6 | Validation | medium | Add provider-adapter error cases to FR-0 acceptance: malformed OpenAI JSON arguments, non-dict Anthropic `input`, duplicate tool call IDs, and final text with no tool calls. | FR-0 requires "zero-or-more `ToolCallRequest`s" but does not specify normalization failures; these failures decide whether loops degrade gracefully or crash provider-specifically. | §2 FR-0 bullet | Parametrized adapter tests normalize valid blocks and return typed provider errors for malformed blocks |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: The prompt-vs-messages contract is the highest-priority requirement ambiguity.
- R1-F2: Compaction correctness needs acceptance criteria, not only an open question.
- R1-F3: Unknown-tool rejection and a standard result envelope are prerequisites for Concierge safety.
- R1-F4: OQ-7 should become normative policy before TUI/MCP consumers ship.
- R1-F5: The line-anchor mismatch should be fixed to keep plan-to-code traceability credible.
- R1-F6: Frozen Concierge registry plus persistent cost/posture UI makes FR-13/FR-14 verifiable.

**Disagreements**:
- None.

#### Review Round R3 — gpt-5.5 — 2026-06-25 01:55:00 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-25 01:55:00 UTC
- **Scope**: Requirements third pass - transcript encoding, argument validation, concurrency semantics, session budget enforcement, and typed error contracts

**Executive summary**

- R1/R2 should be triaged first; this round adds missing executable contracts that are adjacent rather than duplicative.
- FR-1 says `AgenticSession` holds history, but requirements do not define a provider-neutral transcript model.
- FR-9 says tools are executed and fed back, but not whether arguments are validated before execution.
- Multiple tool calls can be returned in one turn; requirements should define ordering and bounded parallelism.
- FR-7 covers cost recording, but agentic loops need budget enforcement before the next turn is spent.
- FR-3 requires provider-agnostic recovery, but requirements do not name provider-agnostic error types.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Architecture | high | Add a requirement for a provider-neutral transcript model plus provider `MessageCodec`s: `AgenticSession` stores canonical records, then adapters render Anthropic/OpenAI-specific message shapes. | FR-1 says the session "holds conversation history" and calls FR-0's `agenerate_tools`; FR-0/FR-9 do not specify how tool-call/result messages survive provider dialect differences. | §2 FR-1 or new FR-1a | Golden tests convert one canonical transcript into valid Claude and OpenAI request messages |
| R3-F2 | Validation | high | Extend FR-9 with pre-execution argument validation against the registered tool schema; validation failures must be returned as tool-error results and must not invoke the callable. | FR-9 says "execute tool calls and feed results back into the loop"; R1 covers unknown tool names, but known tools with invalid arguments remain unspecified. | §2 FR-9 bullet | Unit test calls a registered tool with missing/wrong-type args; callable call count stays zero |
| R3-F3 | Interfaces | medium | Add deterministic multi-tool-call semantics: preserve model-provided order in transcript results, execute sequentially by default, and permit bounded parallelism only for tools declared read-only. | FR-0 returns "zero-or-more `ToolCallRequest`s" and FR-9 executes tool calls, but the requirements do not define ordering or parallelism; this affects reproducibility and side effects. | §2 FR-0 and FR-9 bullets | Fake turn emits two calls with inverse latency; final transcript preserves original call order |
| R3-F4 | Ops | medium | Extend FR-7/FR-14 with per-session budget enforcement: configured token/dollar limits stop the loop before the next model call and surface a user-visible budget-exceeded state. | FR-7 says "Record usage via `costs/`" and FR-14 requires a "per-session cost line"; neither says the loop can stop spending before exceeding a session budget. | §2 FR-7 and FR-14 bullets | Configure low dollar/token budget; session stops before next turn and cost line shows stopped reason |
| R3-F5 | Interfaces | medium | Add a typed agentic error taxonomy requirement covering unsupported tool-use provider, context-window overflow, invalid tool arguments, tool execution failure, budget exceeded, and loop limit exceeded. | FR-3 says "provider-agnostic context-window-exceeded error" and OQ-7/FR-9 imply tool failures, but consumers need stable error types to render TUI/Concierge/MCP messages consistently. | §2 after FR-9 or §4 open questions resolved list | Tests map simulated provider/tool failures into stable exception/result classes and verify consumer-safe messages |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: The prompt/messages contract should be resolved before transcript codecs are designed.
- R1-F2: Compaction acceptance criteria should be based on canonical transcript invariants.
- R1-F3: Unknown-tool rejection and result envelopes remain baseline FR-9 requirements.
- R1-F4: Tiered safety policy is needed before effectful MCP tools are exposed.
- R2-F1: Loop bounds are a prerequisite to safe TUI/Concierge chat.
- R2-F2: Canonical tool schemas pair naturally with R3-F2 argument validation.
- R2-F3: Idempotency semantics are required once retries cross tool execution boundaries.
- R2-F4: Prompt hygiene for tool results should be a core loop requirement.

**Disagreements**:
- None.

#### Review Round R4 — gpt-5.5 — 2026-06-25 01:56:00 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-25 01:56:00 UTC
- **Scope**: Requirements fourth pass - public API status, resumability, observability, MCP tool drift, approval auditability, and rollout fallback

**Executive summary**

- Earlier rounds define the loop mechanics; R4 asks for release and operations requirements so the feature can ship safely.
- Requirements do not say whether new agentic APIs are stable SDK surface or experimental.
- The trajectory log implied by §0/OQ-3 needs a resume stance.
- OTel traces should be a requirement while session/tool boundaries are being designed.
- MCP `list_tools` can drift between discovery and execution; requirements need snapshot/refresh semantics.
- Effectful tool approval should leave an auditable record.
- TUI and Concierge should have an opt-in rollout path with fallback to current behavior.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Architecture | medium | Add a requirement that names the public API status and import paths for `AgenticSession`, `ToolRegistry`, `AgenticTurn`, `ToolCallRequest`, and agentic error types, marking them stable or experimental for v1. | FR-0 introduces `AgenticTurn`/`ToolCallRequest` and FR-1 introduces `agents/agentic.py` `AgenticSession`, but the requirements do not define whether these are public SDK contracts or internal implementation details. | §2 FR-0/FR-1 or new "Public API" subsection | Import-path smoke test and docs check match the declared stable/experimental status |
| R4-F2 | Data | medium | Extend OQ-3/trajectory-log requirements with an explicit resume stance: debug-only logs are non-resumable, or resumable logs must include schema version, session id, transcript checksum, and invariant validation. | §0 says "new trajectory log for turns/tool-results" but FR-1/FR-3 do not say whether a crashed session can be reconstructed or must fail closed. | §0 OQ-3 resolution and §2 FR-1/FR-3 | Crash/restart test either refuses resume with a typed error or reconstructs and validates the transcript |
| R4-F3 | Ops | medium | Add observability requirements for OTel spans/events around session start/end, model turn, tool call, compaction, approval decision, budget stop, and provider error mapping. | The problem statement lists provider/cost/retry substrates but omits observability, and multi-turn debugging will otherwise depend only on local logs. | §2 after FR-7 or new FR-7a | Trace test asserts expected span names and attributes: provider, model, tool name, effect class, cost, status, session id |
| R4-F4 | Security | high | Extend FR-11 with MCP discovery snapshot semantics: `list_tools` results are frozen per session or explicitly refreshed; changed schemas/effect classes invalidate prompt cache and require renewed approval. | FR-11 requires a generic `mcp/client.py` with `list_tools`/`call_tool`, but does not cover tool metadata drift between discovery, prompt caching, approval, and execution. | §2 FR-11 bullet | Fake MCP server changes a tool from read to write; session blocks execution until refresh policy and approval are satisfied |
| R4-F5 | Security | medium | Extend OQ-7/FR-9 with an approval audit requirement for effectful tools: record tool name, effect class, normalized args hash, redaction policy, operator/session id, timestamp, and allow/deny decision. | R1/R2 recommend approval gates, but requirements do not state what evidence remains after an effectful call is approved. | §2 FR-9 or OQ-7 resolution | Approval test writes audit record without raw secrets; identical normalized args produce same hash |
| R4-F6 | Risks | medium | Add rollout/fallback acceptance for FR-10/FR-12: TUI and Concierge agentic modes are opt-in/config-gated for v1, and existing one-shot/deterministic paths remain available until provider parity and session-budget tests pass. | FR-10 says "Replace the one-shot REPL" and FR-12 adds a chat surface; replacing behavior without fallback raises rollout risk for a new multi-call runtime. | §2 FR-10 and FR-12 bullets | Config test disables agentic mode and verifies legacy TUI/Concierge behavior still works |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: API shape must be resolved before public import paths are documented.
- R1-F4: Approval policy should become normative and auditable.
- R2-F1: Loop bounds are prerequisite to opt-in consumer rollout.
- R2-F3: Idempotency semantics should be reflected in approval and replay records.
- R2-F5: Cache invalidation should include tool discovery refreshes.
- R3-F1: Canonical transcripts are the right substrate for resumability and tracing.
- R3-F4: Budget enforcement should be a user-visible and trace-visible requirement.
- R3-F5: Typed errors make resume refusal, fallback, and provider failures testable.

**Disagreements**:
- None.
