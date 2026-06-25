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
