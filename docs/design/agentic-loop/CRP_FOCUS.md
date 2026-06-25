# CRP Focus — Where We Need Review Input Most

This review emphasizes **interface/architecture decisions that are expensive to reverse**. An
Increment-0 spike has already landed (additive `agenerate_tools` on `ClaudeAgent` +
`AgenticTurn`/`ToolCallRequest` types, 3 passing tests, 93 existing agent tests still green), so weigh
that working evidence when judging the foundational call.

1. **FR-0 primitive shape — breaking Protocol change vs. additive opt-in.** The spike implemented the
   *additive opt-in* path: `BaseAgent.supports_tool_use() -> bool` (default `False`) +
   `agenerate_tools(prompt, tools, **kw) -> AgenticTurn`, leaving the provider `Protocol` and the 10
   providers / ~9 downstream repos untouched. Is additive-opt-in the right long-term boundary, or
   does tool-use belong in the provider `Protocol` itself? What does additive cost us later (capability
   discovery, mixed-fleet loops, type-narrowing)?

2. **`AgenticTurn` location (OQ-8).** Spike put `AgenticTurn`/`ToolCallRequest` in `models.py` next to
   `GenerateResult`/`StructuredResult`. Better there, or in a new `agents/agentic_types.py`? Consider
   import cycles, discoverability, and the "sibling type, don't extend `GenerateResult`" precedent.

3. **`mcp/client.py` boundary (FR-11).** The plan adds a *new* generic MCP client (list_tools/call_tool)
   rather than extending `mcp/gateway.py` (skill/workflow-oriented). Is a second MCP component the
   right call, or should the gateway grow a generic tool path? Where's the clean seam?

4. **Tool-execution approval gate (OQ-7).** Concierge is read-only by construction (FR-13). For the TUI
   and MCP surfaces that *can* call effectful tools, is a per-tool approval gate required for v1, or is
   read-only-by-default + explicit allowlists sufficient?

5. **Compaction strategy correctness (OQ-6).** summarize-and-replace vs sliding-window vs tool-result
   eviction — which preserves agentic correctness (tool-call/result pairing, system-prompt caching)
   when recovering from `ContextWindowExceededError`?

6. **FR-13/FR-14 — Concierge posture under a chat layer.** The conversational front-end reintroduces
   LLM cost the deterministic `$0` core never had. Does FR-14's banner + per-session cost line, plus
   "register only READ_ACTIONS," fully preserve "assist, not operate"? Any path by which the chat layer
   could leak write capability or imply autonomy?
