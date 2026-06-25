# SDK-Native Agentic Tool-Use Loop — Implementation Plan

**Version:** 1.0 (against Requirements v0.1, updated alongside v0.2)
**Date:** 2026-06-24
**Status:** Planning

> This plan maps each requirement to real files/APIs. Where planning contradicted a v0.1 assumption,
> it is flagged **[DISCOVERY Dn]** and fed back into Requirements §0.

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
