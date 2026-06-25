# Agentic Loop — Streaming (FR-2) Requirements

**Version:** 0.3 (post-CRP — 3-round panel triaged)
**Date:** 2026-06-25
**Status:** Design — CRP-reviewed (R1–R3 triaged; dispositions in Appendix A/B). Ready to build MVP-A.
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

> **§0.1 CRP triage (R1–R3).** A 3-lens panel hardened this spec: parity is structural (not
> byte-equivalent); the taxonomy needs error/compaction/reset events; an async generator needs a
> **sync-bridge** for the TUI and **cancellation/teardown** semantics; a stream that errors before the
> usage chunk is a **budget-bypass** (fail-closed needs a usage fallback); overflow can fire
> **mid-stream** → a **double-render** hazard; and the riskiest, most provider-divergent part is
> tool-call delta accumulation — so it is split out behind an **MVP boundary**. Dispositions in
> Appendix A/B.

### 2.0 Scope decision — MVP-A first (go/no-go) **[R3-F6]**
Streaming is a **UX/latency-perception win, not a capability or safety win** — the loop is already
correct without it. Commit to the cheap, low-risk cut first; tool-call streaming (the divergent part)
is a separate, later decision:
- **MVP-A (build first):** live **text** streaming — FR-S0a, FR-S1, FR-S2(text), FR-S5, FR-S6, FR-S8,
  FR-S9, FR-S10, FR-S11, FR-S12. Tool turns still run, but tool *args* are not streamed — the model's
  tool calls surface at `TurnComplete` (one `ToolCallStarted`/`ToolCallResult` pair each, from the
  accumulated turn). Delivers the entire TUI UX win at ~half the accumulator complexity.
- **MVP-B (later, only if a consumer needs live tool activity):** FR-S3 + FR-S4 streamed tool-call
  delta accumulation + the optional `ToolCallDelta`/`ReasoningDelta` events.

### Event model
- **FR-S1 — Typed event taxonomy.** Frozen event types in **`models.py`** (next to
  `AgenticTurn`/`AgenticResult`), under a closed `AgenticEvent` base so `AsyncIterator[AgenticEvent]`
  is real-typed **[R1-F7]**: `StreamStart`, `TextDelta(text)`, `ToolCallStarted(id, name)`,
  `ToolCallResult(id, name, ok)` *(named to avoid colliding with the existing `ToolResult` envelope —
  R1-F7)*, `CompactionEvent(attempt)` **[R1-F2]**, `StreamReset(reason)` *(emitted before a turn is
  retried after mid-stream overflow so consumers clear partial text — R2-F3)*, `ErrorEvent(scope,
  error_type, message, recoverable)` **[R1-F1]**, `TurnComplete(turn: AgenticTurn)`,
  `RunComplete(result: AgenticResult)`. Events are **data only** (teeable; FR-S7). *(MVP-B adds
  optional capability-gated `ToolCallDelta(id, partial_args)` / `ReasoningDelta(text)` — R1-F8.)*
- **FR-S0a — Streaming test double (NEW, prerequisite) [R3-F1].** `MockAgent.agenerate_tools_stream`
  yields a scripted event/chunk sequence and accumulates into a scripted `AgenticTurn`;
  `MockAgent.supports_streaming()` is constructor-controlled (to exercise FR-S6 fallback). Same
  prerequisite class as FR-0a — without it FR-S2/S3/S5/S6/S7 have no zero-spend harness.

### Provider primitive
- **FR-S2 — Streaming primitive + STRUCTURAL parity [R2-F1].** `agenerate_tools_stream(messages, tools,
  **kw)` **yields** provider-normalized events **and** returns the final accumulated `AgenticTurn`.
  Parity is **structural, not byte-equivalent**: equal `tool_calls` (id, name, parsed-args dict), equal
  concatenated `text`, equal `finish_reason`, and equal `token_usage` **when both paths report usage**.
  *Acceptance:* feed one recorded chunk transcript through the accumulator and assert the resulting
  `AgenticTurn` is field-equal to the `AgenticTurn` the existing non-streaming parser builds from the
  equivalent non-streamed response object (same fixture, both paths). Claude + OpenAI.
- **FR-S3 — Tool-call delta accumulation (MVP-B).** Reassemble streamed fragments into `ToolCallRequest`s.
  *Acceptance cases (faked chunks, $0)* **[R2-F2]**: (a) OpenAI `tool_calls` at indices 0/1 arriving
  **non-monotonically** (index is the key); (b) multiple Anthropic `tool_use` blocks; (c) id+name with
  **zero `arguments` deltas** → `{}`, call NOT dropped; (d) args valid JSON only after the **last**
  fragment (no mid-accumulation parse); (e) stream ends **mid-tool-call** → args `{}` but **id+name
  preserved** so the loop can still thread/dispatch.
- **FR-S4 — Streaming usage + fallback (MVP-B for streamed, but the fallback rule applies to MVP-A)
  [R2-F4].** Capture end-of-stream usage into `AgenticTurn.token_usage` incl. cache tokens (FR-7
  unchanged). **If the stream errors/cancels before the usage chunk**, produce a non-`None`
  `token_usage` via fallback estimate (count accumulated output text; reuse last-known input count)
  flagged `estimated=True`, so `_account` still charges it and the **before-turn budget check (FR-S8)
  does not read stale totals** (a `None` here is a budget-bypass, not just a reporting gap). Stamp
  `gen_ai.usage.estimated=true` on the span.

### Session surface
- **FR-S5 — `AgenticSession.stream(user_message) -> AsyncIterator[AgenticEvent]`.** Drives the loop,
  forwarding model fragments, dispatching tools, ending with `RunComplete(result)`. `send()` is
  unchanged and remains the default. *Acceptance — canonical event sequence for a one-tool turn*
  **[R3-F2]**: `StreamStart, TextDelta*, ToolCallStarted, ToolCallResult, TurnComplete, …(loop)…,
  RunComplete`.
- **FR-S5a — Sync bridge (NEW) [R1-F3].** `asyncio.run` cannot consume an async generator, and the TUI
  REPL is synchronous. Ship a `stream_sync()` / queue-pump bridge that drives the async generator from
  a sync caller and yields events; **it is FR-S11's entry point.** Without it FR-S11 is unbuildable on
  the current sync TUI.
- **FR-S5b — Cancellation/teardown (NEW) [R1-F4].** On early consumer exit (`break`/`aclose()`):
  cancel the in-flight provider stream, **start no new tool dispatch**, and propagate `aclose()` to the
  underlying provider iterator. A tee'd branch closing must not starve the others.
- **FR-S6 — Graceful, UNIFORM fallback [R2-F6].** Providers where `supports_streaming()` is False emit
  the whole text as one `TextDelta`, **and still synthesize `ToolCallStarted`/`ToolCallResult` for tool
  turns** from the accumulated `AgenticTurn.tool_calls` — so the event *sequence* is identical to the
  streaming path (modulo text-delta granularity). *Acceptance:* a MockAgent tool turn via fallback
  yields the same event sequence as via streaming.
- **FR-S7 — Teeable, non-blocking.** *Resolution (OQ-S1) [R1-F5]:* `stream()` returns one
  `AsyncIterator[AgenticEvent]`; fan-out is a **standalone `tee(aiter, n)` util**, not a `stream()`
  parameter — keeping `stream()` single-responsibility and the ContextCore observer a *caller* concern.
  *Acceptance [R3-F2]:* two consumers attached, one slow; both receive the identical full event list,
  none dropped/reordered, and a blocked consumer does not deadlock the other (bounded buffer).

### Interactions (locked, baked as requirements)
- **FR-S8 — Budget + hard per-stream cap [R2-F5].** Fail-closed budget (FR-15) checked **before each
  turn**; mid-stream budget abort is a non-goal. **Add a hard per-stream output cap** (tokens/bytes)
  that aborts a single runaway stream independent of the cross-turn budget. Worst-case overshoot is
  bounded at **`budget + one_stream_cap`**.
- **FR-S9 — Overflow/compaction, open OR mid-stream + no double-render [R2-F3].** Overflow may surface
  at **stream-open or mid-stream**. The existing `_call_with_compaction` continues to wrap the model
  call (now the streaming call at the same site); on overflow → compact (FR-4) → retry. To avoid
  **double-rendering** retried text on top of already-emitted `TextDelta`s, the stream MUST emit a
  `StreamReset(reason="overflow_retry")` (FR-S1) before the retry **or** withhold consumer-visible
  `TextDelta`s until past the overflow-possible boundary — implementations pick one and test it.
- **FR-S10 — Spans (FR-18).** Add `gen_ai.first_token_latency_ms` (wall time: request send → first
  `TextDelta`/`ToolCallStarted`) to `agentic.turn`, plus a `StreamStart` span event. *Acceptance:* the
  in-memory exporter shows the attribute + event.

### Consumer
- **FR-S11 — TUI live render.** The TUI agentic chat (`STARTD8_TUI_AGENTIC`) renders `TextDelta`s live
  (via FR-S5a sync bridge) instead of the blocking spinner; opt-in, legacy single-shot retained.

### Boundary
- **FR-S12 — Zero-ContextCore-import invariant (NEW) [R3-F3].** `agents/agentic.py`, the streaming
  primitive, and the event types import **nothing** from `startd8.integrations.contextcore`. FR-CC1/2/3
  live entirely in `integrations/`. A guard test asserts no `import …contextcore` in the agentic/
  streaming modules. (The inline `io.contextcore.*` span *attribute strings* from FR-18 are naming, not
  imports — allowed.)

### Traceability (loop seams streaming touches) **[R3-F5]**
The streamed turn flows through the **existing** `_account()` (FR-S4 usage → unchanged accounting) and
the **existing** message codec `_assistant_message`/`_tool_result_messages` (FR-S2 structural parity is
what keeps these untouched — acceptance: a streamed turn threads an identical `messages` list). The
model call site `self.agent.agenerate_tools(...)` wrapped by `_call_with_compaction` is the single seam
swapped for the streaming primitive (FR-S9).

---

## 3. Requirements — Phase 2 (ContextCore, optional, after Phase 1)

> Built only when there is a real consumer (e.g. the loop running inside a cap-dev-pipe/workflow
> context). The loop **never depends** on these.

> **§3.0 Lessons-applied (Lessons Learned review, 2026-06-25; build-recon corrected same day).** A
> pass over the `observability`, `sdk`, `mcp`, and `h2a_h2h_a2a` lesson domains sharpened the
> requirements below; the `[LL …]` tags trace each refinement to its lesson. **A subsequent build-surface
> recon corrected two FR-CC3 assumptions** (see the box on FR-CC3): the span-registration target is the
> **`_OTEL_DESCRIPTORS` + `collector.py:_INSTRUMENTED_MODULES`** mechanism (not `ObservabilitySpec`,
> which is alert/signal-only), and the run-level span **already exists as `agentic.session`** — so
> FR-CC3 **registers** it rather than emitting a redundant new span (Decision A).

- **FR-CC1 — Progress tee (observer).** A `ContextCoreProgressObserver` that consumes the FR-S1 event
  stream and emits `emit_progress()` / span events to ContextCore (turn started, tool called,
  completed) via the existing `TaskTrackerWrapper`. Pure observer — reads the tee, drives nothing.
  - **[LL sdk-12 — protocol injection]** The session accepts a `ProgressEmitter` **protocol** (or
    `None`), and ContextCore *implements* it — injected late via constructor/entry-point, **not** a
    bridge package. Keeps the core loop import-clean (FR-S12).
  - **[LL sdk-12/16 — defensive optional import]** The observer catches **both `ImportError` and
    `TypeError`** (ContextCore absent *or* its emitter signature drifted), logs a warning, and
    **no-ops** — never crashes or alters the loop's output/timing.
  - **[LL mcp-02 — idempotent events]** Each emitted progress event is atomic: a dropped or duplicate
    event must leave ContextCore state consistent (use stable per-event ids).
- **FR-CC2 — Task-lifecycle wrapper.** A `ContextCoreAgenticAdapter` that runs a session as a tracked
  ContextCore **task** — SpanState-v2 compliant: top-level `status` (OK/ERROR/UNSET), `task.status`
  lifecycle (`in_progress`→`done`/`cancelled`), `task.type`, `task.percent_complete` derived from
  turns, zero-point `task.created` event. Reuses `ContextCoreWorkflowAdapter`'s `TaskTrackerWrapper`
  pattern (net-new ~50 LoC; no agent-run wrapper exists today).
  - **[LL h2a-01 — zero-point first]** Emit the `task.created` event **at run start** (with
    `task.type`, initial `task.status`), not retroactively — it is what makes the span task-aware and
    drives burndown.
  - **[LL h2a-03 — transition validation]** Validate status transitions against the canonical state
    machine; reject illegal ones so the cross-agent audit trail can't be corrupted. On any lossy A2A
    reduction, **preserve the canonical `task.status` value** in the span (don't discard it).
  - **[LL sdk-09 — guard via filesystem probe]** The "adapter is wired" guard test **probes the file**
    (or greps source), it does **not** import `integrations.contextcore` (an optional dep). (Matches
    the existing FR-S12 guard.)
- **FR-CC3 — Register the run-level span for artifact generation [R3-F4].**
  > **Build-recon correction (2026-06-25).** v0.3 said "emit a net-new `agentic.run` span" and
  > "register a descriptor in the `ObservabilitySpec` span manifest." Reading the bytes corrected
  > **both**: (1) the existing **`agentic.session`** root span is already emitted once per
  > `send()`/`stream()` run and already carries every run-level attribute below — a separate
  > `agentic.run` span would be **redundant telemetry** (**Decision A**, confirmed). (2)
  > `ObservabilitySpec` is **alert/signal-focused** (`signals`+`receivers`) and has **no span field**;
  > spans are registered via a **different** mechanism — an `_OTEL_DESCRIPTORS` dict in the module plus
  > listing the module in `collector.py:_INSTRUMENTED_MODULES`, harvested by `collect_span_descriptors()`.

  **Register `agentic.session` (the run-level span) as a `SpanDescriptor`** so the artifact generator
  (`observability/artifact_generator.py`) auto-derives Dashboard/SLO/Alert artifacts. Concretely:
  add an `_OTEL_DESCRIPTORS` dict to `agents/agentic.py` declaring the span name `agentic.session`,
  kind INTERNAL, and its attributes — `gen_ai.system`, `gen_ai.request.model`,
  `gen_ai.usage.input_tokens|output_tokens`, `io.contextcore.project.id|task.id`, `agentic.stop_reason`,
  `agentic.turns`, `agentic.tool_count` — and add `agents/agentic` to `_INSTRUMENTED_MODULES`. *(No
  new span emission; the span already exists from `fce92b6c`.)*
  - **[LL obs — schema-first / single source of truth]** The descriptor is the contract; **never
    hand-write** the dashboard JSON — derive via the generator / `/dbrd-cr8r`. No mixing derived +
    hand-edited artifacts.
  - **[LL obs — "derive don't guess" + resolvability gate]** Verify generated queries **resolve
    against live `agentic.session` spans** (a 100%-coverage / **0-series** dashboard from a wrong
    selector is the failure to gate out).
  - **[LL obs/h2a — TraceQL `span.` prefix]** Document every attribute **with the `span.` prefix**
    (`{ span.agentic.stop_reason = "completed" }`); a bare name *silently returns empty*.
  - **[LL obs — name both OTel & Prometheus]** For any derived metric/threshold, document the OTel name
    **and** its OTLP→Prometheus form (+ unit suffix), e.g. `gen_ai.usage.input_tokens` →
    `gen_ai_usage_input_tokens`. *Note: the spec validator now rejects non-numeric threshold values
    (`a3015a84`) — any declared SLO threshold must be a real number.*
  - **[LL obs — emission≠capability]** Add a **runtime coverage assertion** (FR-CC4) that a real run
    actually emits the `agentic.session` span with the declared attrs — registration alone doesn't
    prove emission. *(The `BatchSpanProcessor` atexit flush this lesson also called for is **already
    satisfied** — `otel.py:configure_otel` registers `atexit → shutdown_otel → force_flush`; nothing
    to add.)*
  - *Acceptance:* `collect_span_descriptors()` returns the `agentic.session` descriptor; the artifact
    generator, fed a recorded `agentic.session` span, emits a Dashboard/SLO/Alert set whose queries
    resolve against that span (non-zero series).
- **FR-CC4 — Dogfood validation (NEW) [LL km-02].** Phase-2 integration tests emit **real**
  `agentic.session` / task spans (in-memory exporter) and query them back — not mocks — to catch
  attribute-name / timestamp-semantics mismatches before a user does.

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

- **OQ-S1 → RESOLVED [R1-F5]:** one `AsyncIterator[AgenticEvent]` + a standalone `tee(aiter, n)` util
  (not `stream(observers=…)`). See FR-S7.
- **OQ-S2 → RESOLVED [R1-F6]:** terminal `RunComplete(result)` is the sole source of truth; **no**
  `stream.result` attribute (a mid-stream-readable attribute invites reading a half-built result). If a
  convenience is ever wanted, expose an awaitable that drains — not an attribute.
- **OQ-S3.** Anthropic `messages.stream()` `text_stream` helper vs raw events — use **raw events**
  (`text_stream` skips tool_use blocks, which MVP-B needs). (Unchanged.)
- **OQ-S4 (NEW).** MVP-A vs MVP-B commitment is recorded (§2.0) — confirm at build time whether any
  consumer needs live tool-arg streaming before investing in FR-S3/S4.

---

## 6. Plan / Increment Sequence

| Increment | Scope | Testable without spend? |
|---|---|---|
| **S0** | FR-S0a `MockAgent.agenerate_tools_stream` double + FR-S1 event types (`models.py`) | ✅ unit |
| **S1 (MVP-A)** | FR-S2(text) streaming primitive (Claude+OpenAI) + FR-S5/S5a/S5b + FR-S6 + FR-S8/S9/S10/S12 | ✅ faked chunk iterators + streaming double |
| **S2 (MVP-B)** | FR-S3/S4 tool-call delta accumulation + optional `ToolCallDelta`/`ReasoningDelta` | ✅ faked chunks |
| **S3** | FR-S11 TUI live render (via FR-S5a sync bridge) | ✅ (helper testable; live render manual) |
| **P2** | FR-CC1/CC2 ContextCore observer + task adapter; FR-CC3 register `agentic.session` descriptor; FR-CC4 dogfood | ✅ in-memory exporter + fake tracker |

---

*v0.3 — Post-CRP (3-lens panel). **3 new FRs (FR-S0a, FR-S5a, FR-S5b, FR-S12), 7 hardened (FR-S1/2/4/6/
8/9 + FR-CC3), MVP-A/B split added, OQ-S1/S2 resolved, +OQ-S4.** Central CRP themes: parity is
structural not byte-equivalent; the taxonomy needed error/compaction/reset events; an async-generator
API needs a sync-bridge + cancellation semantics; a pre-usage stream error is a budget-bypass; overflow
can fire mid-stream (double-render); tool-call streaming is the risky part → split behind MVP-B.*

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

> Triaged 2026-06-25 across R1 (Interface/API), R2 (Correctness/edge), R3 (Completeness/Phase-2).

| ID(s) | Suggestion (theme) | Merged into | Date |
|----|------------|-----------------------------------|------|
| R1-F1 | `ErrorEvent` in taxonomy | FR-S1 | 2026-06-25 |
| R1-F2 | `CompactionEvent` | FR-S1 | 2026-06-25 |
| R1-F3 | sync-bridge for `stream()` → TUI | FR-S5a (new) | 2026-06-25 |
| R1-F4 | cancellation/teardown (`aclose`) | FR-S5b (new) | 2026-06-25 |
| R1-F5 | OQ-S1 → single iterator + `tee()` util | FR-S7 / OQ-S1 | 2026-06-25 |
| R1-F6 | OQ-S2 → terminal event only, no `.result` attr | OQ-S2 | 2026-06-25 |
| R1-F7 | events in models.py + `AgenticEvent` union + rename `ToolResultEvent`→`ToolCallResult` (collision) | FR-S1 | 2026-06-25 |
| R1-F8 | optional `ToolCallDelta`/`ReasoningDelta` | FR-S1 (MVP-B optional) | 2026-06-25 |
| R2-F1 | parity is structural, not byte-equivalent + shared-fixture test | FR-S2 | 2026-06-25 |
| R2-F2 | FR-S3 accumulation edge cases as acceptance | FR-S3 | 2026-06-25 |
| R2-F3 | overflow can fire mid-stream → double-render; `StreamReset` | FR-S9 + FR-S1 | 2026-06-25 |
| R2-F4 | usage fallback on pre-usage error = budget-bypass guard | FR-S4 | 2026-06-25 |
| R2-F5 | hard per-stream output cap | FR-S8 | 2026-06-25 |
| R2-F6 | fallback must synthesize tool events (uniformity) | FR-S6 | 2026-06-25 |
| R3-F1 | `MockAgent.agenerate_tools_stream` double | FR-S0a (new) | 2026-06-25 |
| R3-F2 | acceptance bars per FR (event sequence, tee, latency) | FR-S2/S5/S7/S10 | 2026-06-25 |
| R3-F3 | zero-ContextCore-import guard test | FR-S12 (new) | 2026-06-25 |
| R3-F4 | FR-CC3 actionable: net-new span name + enumerated attrs + manifest | FR-CC3 | 2026-06-25 |
| R3-F5 | traceability to `_account`/codec/call-site seams | §2 Traceability | 2026-06-25 |
| R3-F6 | MVP-A/B split + explicit go/no-go | §2.0 | 2026-06-25 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — all R1–R3 suggestions accepted; the panel was consistent and code-grounded) |  |  |  | 2026-06-25 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 (Interface/API lens) — 2026-06-25 16:30 UTC

8 suggestions (F-1…F-8): add `ErrorEvent` (no error event despite 4 typed failure modes); add
`CompactionEvent` (live TUI freezes during multi-attempt compaction); **specify the sync-bridge** for
`stream()` (asyncio.run can't drive an async generator — FR-S11 unbuildable on the sync TUI without it);
**cancellation/teardown** (early `break`/`aclose` must cancel the provider stream + run no further
tools); resolve OQ-S1 → single iterator + `tee()` util; resolve OQ-S2 → terminal event only; place
events in `models.py` + `AgenticEvent` union + **rename `ToolResultEvent` (collides with the existing
`ToolResult` envelope)**; optional capability-gated `ToolCallDelta`/`ReasoningDelta`. *All applied (App A).*

#### Review Round R2 — claude-opus-4-8 (Correctness/edge lens) — 2026-06-25 16:30 UTC

6 suggestions (F-1…F-6): "byte-equivalent" parity is unachievable/untestable → **structural equivalence
on a shared fixture** (both paths, field-equal); FR-S3 accumulation **edge cases as acceptance**
(non-monotonic OpenAI indices, multiple Anthropic blocks, zero-arg calls, last-fragment-only-valid JSON,
truncated mid-call preserving id+name); **double-render hazard** — overflow can fire mid-stream after
`TextDelta`s reached the consumer → require `StreamReset` before retry; **usage fallback** — a stream
erroring before the usage chunk leaves `token_usage=None`, the before-turn budget reads stale totals →
**budget-bypass**, require an estimated fallback; **hard per-stream output cap** (one-turn overshoot is
otherwise unbounded); FR-S6 fallback must **synthesize tool events** to be truly uniform. *All applied.*

#### Review Round R3 — claude-opus-4-8 (Completeness/Phase-2 lens) — 2026-06-25 16:30 UTC

6 suggestions (F-1…F-6): **missing FR-S0a** `MockAgent.agenerate_tools_stream` (the plan already
assumes it — build blocker, same class as FR-0a); **acceptance bars** per FR (canonical event sequence,
tee non-blocking bar, latency measurement); **zero-ContextCore-import guard** as a testable invariant
(FR-18 already inlines `io.contextcore.*` attribute strings — make the no-import boundary checkable);
**FR-CC3 actionable** (net-new `agentic.run` span name + enumerated attrs + name the manifest; not
re-documenting existing spans); **traceability** to `_account`/codec/call-site seams; **MVP-A/B split +
go/no-go** (text-delta-only MVP-A delivers the whole TUI win at ~half the accumulator risk; tool-call
streaming = MVP-B). *All applied.*
