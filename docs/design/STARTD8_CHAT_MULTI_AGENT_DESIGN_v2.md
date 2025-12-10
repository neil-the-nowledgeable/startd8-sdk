# Startd8 Chat: Multi-Agent Document Review (v2 Addendum)

> **Version:** 2.0  
> **Status:** Design Addendum to v1  
> **Base Spec:** `STARTD8_CHAT_MULTI_AGENT_DESIGN_v1.md`  
> **Related Spec:** `design/STARTD8_CHAT_MENU_PLAN.md`

---

## 1. Purpose of This Version

This document **does not replace** `STARTD8_CHAT_MULTI_AGENT_DESIGN_v1.md`. Instead, it:

- **Aligns** the multi-agent review feature with the **single-agent "💬 Chat with Agent" menu** described in `STARTD8_CHAT_MENU_PLAN.md`.
- **Identifies shared helpers and UX patterns** that should be reused across both features.
- **Clarifies how users move between quick single-agent chat and deeper multi-agent document review.**

All core architecture, data models, prompts, implementation plan, risks, and tests for the multi-agent feature **remain as specified in v1** unless explicitly overridden here.

---

## 2. Relationship to "💬 Chat with Agent" Menu

### 2.1 Distinct but Complementary Flows

- **Single-Agent Chat (Menu Plan)**
  - Objective: quick, ad-hoc questions to one Ready agent.
  - Input: free-text prompt (no required document).
  - Output: transient TUI response (no required file output).

- **Multi-Agent Document Review (This Feature)**
  - Objective: structured, multi-perspective review of a specific `.md` document.
  - Input: document path + review question/instructions.
  - Output: per-agent perspectives and optional synthesized report, usually written to `.md`.

**Guiding principle:**
- The **Chat menu** is the "fast lane" for experimentation.
- The **Multi-Agent Review** is the "deep-dive lane" for rigorous, persistent analysis of documents.

### 2.2 Cross-Navigation UX

Add lightweight bridges between the flows:

- From **Chat with Agent → Multi-Agent Review**:
  - If the user is chatting about a specific `.md` file (e.g., they paste a path or reference), offer a prompt:
    - "Run a multi-agent document review for this file?"
  - This launches the multi-agent flow prefilled with:
    - `source_document` = referenced path (if valid).
    - `question` = last chat question.

- From **Multi-Agent Review → Chat with Agent**:
  - After a multi-agent review completes, offer an option:
    - "Open a follow-up single-agent chat with one of the reviewers."
  - This opens the Chat menu with:
    - The chosen agent pre-selected.
    - The document path and a short summary inserted into the first prompt template.

These bridges are **optional** and can be implemented in a later iteration, but the design assumes that both features should feel like parts of a coherent "Startd8 Chat" ecosystem rather than disconnected tools.

---

## 3. Shared Helpers and Agent Selection

### 3.1 Ready-Agent Discovery

Unify the various "ready agent" helpers so that both features depend on the same logic:

- **Existing concepts:**
  - v1 uses `_get_ready_agents_for_selection()` and readiness tables in `tui_improved.py`.
  - The Chat Menu Plan defines `_get_ready_agents(self)` in `ImprovedTUI`.

### 3.2 Consolidated Helper

Define a single canonical helper in `tui_improved.py` (name not final, but conceptually):

```python
def _get_ready_agent_descriptors(self) -> List[Dict[str, Any]]:
    """Return ready agents with consistent metadata for selection.

    Used by:
    - Single-agent "💬 Chat with Agent" flow
    - Multi-agent document review flow
    """
    # Implementation delegates to AgentConfigTester.test_all() and
    # existing unified agent list builder from v1.
```

Both flows should build their UI choices from this same descriptor list, to avoid divergence in which agents appear as "Ready".

### 3.3 Agent Instantiation

From `STARTD8_CHAT_MENU_PLAN.md`:

- There is a requirement to **centralize "get agent instance by name" logic**, currently scattered (e.g., `cli.py`, benchmark code, TUI).

For v2:

- Introduce a shared factory function, e.g. `create_agent_from_id(agent_id: str) -> BaseAgent`, in a common module (such as `agents/__init__.py` or `orchestration.py`).
- Ensure **both**:
  - `chat_with_agent` (single-agent chat), and
  - the multi-agent `MultiAgentChat` / `_get_ready_agents_for_selection` paths

  use this same factory so that:

- Supported agent IDs and behavior are consistent across Startd8.
- Adding a new provider (e.g., Gemini, Ollama) requires **one** mapping change.

---

## 4. UX and Output Alignment

### 4.1 Console Output Patterns

Borrow small UX details from the Chat Menu Plan for multi-agent review:

- Use similar **headers** and **footers** in the TUI:
  - "Chatting with {Agent Name}" ↔ "Review by {Agent Name}".
  - Standard footer for exit/help, even when just viewing review results.
- Reuse **Rich markdown rendering** pattern already outlined for the chat responses to display multi-agent perspectives consistently.

### 4.2 Streaming vs Buffered Responses

The Chat Menu Plan explicitly allows for **streamed** responses ("Stream or print response"):

- v1 multi-agent design assumes **buffered** responses per agent.
- v2 design should:
  - Keep multi-agent review **buffered by default** for simplicity and deterministic file output.
  - Optionally expose a **streaming preview** mode for each agent in the TUI, aligned with the chat experience.

This is an optional enhancement, but the TUI plumbing should not make streaming impossible later.

---

## 5. Testing and Mock Agent Reuse

From the Chat Menu Plan:

- "Ensure `MockAgent` is always available for testing the UI flow."

For multi-agent v2:

- Reuse `MockAgent` in:
  - `run_multi_agent_review` integration tests.
  - Manual TUI validation flows where users want to verify the UX without real API keys.
- Ensure config allows a toggle:
  - `include_mock_agent` (already present in v1 config section) should apply **consistently** to both single-agent chat and multi-agent review.

---

## 6. Summary of Changes vs v1

- **No core model or API changes** are required; v1 data models, prompts, and orchestration remain valid.
- **New alignment requirements**:
  - Shared "ready agent" helper and shared agent factory.
  - Consistent use of `include_mock_agent` and readiness criteria across chat and review.
- **UX integration**:
  - Optional cross-navigation between single-agent and multi-agent flows.
  - Harmonized headers/footers and markdown rendering.
- **Future-proofing for streaming and history**:
  - Multi-agent review remains batch-oriented, but design leaves room to adopt the streaming and history concepts defined in the Chat Menu Plan.

For all other details (architecture diagrams, full user flow, prompts, implementation phases, risks, testing), refer to `STARTD8_CHAT_MULTI_AGENT_DESIGN_v1.md`. This v2 addendum should be read as an overlay focused on **alignment with the Chat Menu feature**.