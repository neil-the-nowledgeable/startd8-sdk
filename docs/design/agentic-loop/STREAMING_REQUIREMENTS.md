# Agentic Loop — Streaming (FR-2) Requirements

**Version:** 0.2 (decision-locked; planning insights folded in)
**Date:** 2026-06-25
**Status:** Design — ready for reflective-requirements → CRP before build
**Author:** Neil Yashinsky
**Depends on:** the agentic loop on `main` (FR-0/1/3/4/9/15/16/17/18/19, all merged PRs #36–#41 + span enrichment `fce92b6c`)

---

## 0. Planning Insights (locked decisions + what the design pass revealed)

> The design pass was run against the **real** Anthropic and OpenAI streaming APIs and the existing
> loop/ContextCore code. Three things were surfaced and are now baked in:

| Surfaced | Decision |
|---|---|
| `AgenticTurn` is a single return value; streaming needs incremental output **and** the same final `AgenticTurn` so the loop's tool-dispatch/threading/budget/compaction stay unchanged | **Parity rule (FR-S2):** the streaming primitive *accumulates into* an `AgenticTurn` and feeds the identical `_run_loop`. Only the model-call step differs. |
| Three event-API shapes were compared (async-generator / callback / stream-handle). ContextCore is an **observer** of progress, not a trigger; the TUI is a second consumer. Multiple independent consumers need a **teeable** stream. | **LOCKED: async-generator of typed events.** It is the only shape that lets the TUI render *and* a ContextCore observer tee progress without either blocking the other. Callback forces one shared sink; handle is heavier. |
| Token usage only arrives at **stream end** (OpenAI needs `stream_options={"include_usage": True}`); a context-overflow surfaces at **stream open** (request rejected before tokens flow) | **Budget:** keep the existing before-each-turn check; **mid-stream abort on budget is a non-goal for v1** (one streamed turn may overshoot by a turn). **Overflow:** the existing `_call_with_compaction` wrapper moves to the stream-open point — compact + retry still works. |
| Tool-call deltas fragment **differently per provider** (OpenAI: by `index`, `arguments` as a built-up JSON string, id/name in first chunk; Anthropic: by content block, `input_json_delta.partial_json` concatenated) | A provider-agnostic **accumulator** reassembles both into identical `ToolCallRequest`s. Fully testable with **faked chunk iterators — zero API spend.** |
| ContextCore is record + query only (no notify/trigger); `add_project_context_to_span` + `gen_ai.*` already wired (`fce92b6c`) | ContextCore wraps **from above** as an optional observer/adapter — **Phase 2**, never a dependency of the loop or a driver of the stream. |

---

## 1. Problem Statement

The loop works but is **non-streaming**: a turn blocks until the full response is ready (the TUI shows a
"Thinking…" spinner, then dumps text). Streaming surfaces tokens and tool-call activity *as they
happen* — a latency-*perception* and UX win (not a capability or safety win; the loop is already
correct without it). The same incremental event stream also unlocks **live progress** for ContextCore
(Phase 2), which the non-streaming loop cannot provide.

---

## 2. Requirements — Phase 1 (streaming core)

### Event model
- **FR-S1 — Typed event taxonomy.** A small set of frozen event types yielded by the stream:
  `StreamStart`, `TextDelta(text)`, `ToolCallStarted(id, name)`, `ToolResultEvent(id, name, ok)`,
  `TurnComplete(turn: AgenticTurn)`, `RunComplete(result: AgenticResult)`. Events are **data only**
  (teeable — any number of consumers may read them; FR-S7).

### Provider primitive
- **FR-S2 — Streaming generation primitive + parity.** A streaming variant of the tool-use primitive
  (e.g. `agenerate_tools_stream(messages, tools, **kw)`) that **yields** provider-normalized fragments
  **and** returns the final accumulated `AgenticTurn` — byte-equivalent to what non-streaming
  `agenerate_tools` would return for the same response. Implemented for **Claude + OpenAI** first.
- **FR-S3 — Tool-call delta accumulation.** Reassemble streamed tool-call fragments (OpenAI by index +
  concatenated `arguments` JSON string; Anthropic by content block + `partial_json`) into complete
  `ToolCallRequest`s. Malformed/partial JSON at stream end degrades to `{}` (consistent with FR-0).
- **FR-S4 — Streaming usage.** Capture end-of-stream usage (OpenAI via `stream_options.include_usage`;
  Anthropic via `message_delta`) into the `AgenticTurn.token_usage`, including cache tokens, so FR-7
  cost accounting is unchanged.

### Session surface
- **FR-S5 — `AgenticSession.stream(user_message) -> AsyncIterator[Event]`.** Drives the loop, forwarding
  model fragments as events, dispatching tools (emitting `ToolCallStarted`/`ToolResultEvent`), and
  ending with `RunComplete(result)`. Non-streaming `send()` is unchanged and remains the default.
- **FR-S6 — Graceful fallback.** Providers where `supports_streaming()` is False emit the whole text as
  a single `TextDelta` then `TurnComplete` — so **every consumer gets a uniform event stream**
  regardless of provider capability.
- **FR-S7 — Teeable, non-blocking.** Multiple consumers (TUI render + optional ContextCore observer)
  must each receive every event without one starving the other (e.g. fan-out helper, not a single
  shared callback).

### Interactions (locked, baked as requirements)
- **FR-S8 — Budget.** The fail-closed budget (FR-15) is checked **before each turn** as today;
  mid-stream abort is a **non-goal** for v1 — document the one-turn overshoot bound.
- **FR-S9 — Overflow/compaction.** Context-overflow detection (FR-3) wraps **stream open**; on overflow
  → compact (FR-4) → retry the turn. No mid-stream compaction.
- **FR-S10 — Spans (FR-18).** Add `gen_ai.first_token_latency_ms` to `agentic.turn` and a `StreamStart`
  span event; otherwise the existing span tree is unchanged.

### Consumer
- **FR-S11 — TUI live render.** The TUI agentic chat (`STARTD8_TUI_AGENTIC`) renders `TextDelta`s live
  instead of the blocking spinner; opt-in, legacy single-shot retained.

---

## 3. Requirements — Phase 2 (ContextCore, optional, after Phase 1)

> Built only when there is a real consumer (e.g. the loop running inside a cap-dev-pipe/workflow
> context). The loop **never depends** on these.

- **FR-CC1 — Progress tee (observer).** A `ContextCoreProgressObserver` that consumes the FR-S1 event
  stream and emits `emit_progress()` / span events to ContextCore (turn started, tool called,
  completed) via the existing `TaskTrackerWrapper`. Pure observer — reads the tee, drives nothing.
- **FR-CC2 — Task-lifecycle wrapper.** A `ContextCoreAgenticAdapter` that runs a session as a tracked
  ContextCore **task** — SpanState-v2 compliant: top-level `status` (OK/ERROR/UNSET), `task.status`
  lifecycle (`in_progress`→`done`/`cancelled`), `task.type`, `task.percent_complete` derived from
  turns, zero-point `task.created` event. Reuses `ContextCoreWorkflowAdapter`'s `TaskTrackerWrapper`
  pattern (net-new ~50 LoC; no agent-run wrapper exists today).
- **FR-CC3 — `agentic.run` span convention.** Register a first-class span convention for a multi-turn
  agentic run (`gen_ai.*` + `io.contextcore.*` + `agentic.{stop_reason,turns,tools}`) as descriptors
  in the AI Agent Observability taxonomy, so its **artifact generator auto-derives dashboards/SLOs/
  alerts** for agentic runs (today it targets single `agent.generate` spans only).

---

## 4. Non-Requirements

- No mid-stream budget abort (v1).
- ContextCore is **not** a dependency of the loop, **not** an abstraction layer, **not** a trigger
  (it has no notify/trigger surface — the async generator is the mechanism; `events/` EventBus is the
  path if reactive triggering is ever wanted).
- No streaming for non-tool-capable providers beyond the FR-S6 single-delta fallback.
- Not adopting any new streaming dependency — use the provider SDKs' native streaming.

---

## 5. Open Questions

- **OQ-S1.** Fan-out mechanism for FR-S7: a small `tee` helper over the async generator, or have
  `stream()` accept N observers? (Lean: return one async-iterator; provide a `tee()` util.)
- **OQ-S2.** How is `RunComplete`'s `AgenticResult` delivered — terminal event only, or also a
  `stream.result` convenience? (Lean: terminal event; optional `.result` later.)
- **OQ-S3.** Anthropic exposes a `messages.stream()` context-manager helper with `text_stream`; use it
  or iterate raw events for tool_use deltas? (Likely raw events — `text_stream` skips tool blocks.)

---

## 6. Plan / Increment Sequence

| Increment | Scope | Testable without spend? |
|---|---|---|
| **S1** | FR-S1 events + FR-S2/S3/S4 provider primitive (Claude+OpenAI) with delta accumulation | ✅ faked chunk iterators |
| **S2** | FR-S5 `stream()` + loop integration + FR-S6 fallback + FR-S8/S9/S10 interactions | ✅ MockAgent streaming double |
| **S3** | FR-S11 TUI live render | ✅ (helper testable; live render manual) |
| **P2** | FR-CC1/CC2/CC3 ContextCore observer + adapter + convention | ✅ in-memory exporter + fake tracker |

---

*v0.2 — async-generator + teeable-events locked; budget/overflow interactions resolved; ContextCore
folded in as an optional Phase 2 (observer + task-lifecycle adapter + agentic.run convention). Ready
to run the reflective-requirements → CRP loop before S1 build.*
