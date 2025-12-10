## startd8 Chat: Multi‑Agent Document Review – High‑Level Plan

### Goal

Add a new TUI menu item (e.g. "💬 startd8 Chat: Multi‑Agent Doc Review") that lets a user:
- **Select a markdown document** to review.
- **Ask a question / give instructions** about that document.
- **Route the request to all (or selected) agents with Ready status**.
- **Aggregate the agents' perspective responses** into a structured review and (optionally) an enhanced version of the document.

---

### 1. TUI / UX Flow

- **New main menu entry**
  - Add a `startd8 Chat / Multi‑Agent Doc Review` option to the main TUI menu (near Document Enhancement Chain and Agent tools).
  - Enable this option only when there is at least one agent with Ready status (using the existing agent‑status machinery).

- **Step 1 – Select document**
  - Reuse `_select_document_for_enhancement()` to choose a `.md` file.
  - Keep existing validation and optional preview (metadata, headings, first N lines).

- **Step 2 – Choose agents**
  - Reuse `_get_ready_agents_for_selection()` to fetch Ready agents.
  - Provide selection options:
    - **All Ready Agents**.
    - **Choose Agents Manually** (multi‑select from the Ready list).
  - Store a list of selected agent descriptors: name, type (built‑in / user added), model, internal ID.

- **Step 3 – Enter question / instructions**
  - Prompt user for a free‑text question / instruction, e.g.:
    - "Improve clarity and structure; flag logic gaps."
  - Optional toggles (configurable defaults):
    - Emphasis on writing quality vs correctness.
    - Structural feedback only vs in‑line rewrite suggestions.

- **Step 4 – Choose output destination**
  - Ask user how to output results:
    - Show review in TUI only.
    - Write a review report to a new `.md` file.
    - Optionally write an enhanced version of the document (non‑destructive, e.g. `original.enhanced.startd8.md`).

---

### 2. Orchestration / Backend Design

- **Context assembly**
  - Read the selected `.md` file from disk.
  - Build a shared context object containing:
    - File metadata (path, size, last modified, line count).
    - Full text (or chunked text if large).
    - User question/instructions.

- **Per‑agent "perspective" calls**
  - For each selected Ready agent:
    - Construct a standardized prompt template:
      - **System**: explain that the agent is reviewing a markdown document and should answer as a reviewer.
      - **User**: include the question/instructions and the document content (or the relevant excerpt / chunk).
    - Use the existing agent abstraction (`BaseAgent` instances via `AgentManager` / `AgentFramework`) for model calls.
    - Prefer parallelization where the orchestration layer supports it; otherwise loop with progress reporting.

- **Aggregation strategy**
  - Collect each agent's response as a separate "perspective".
  - Build an aggregated result structure that may include:
    - A high‑level consolidated summary of findings.
    - Per‑agent sections (what each agent suggested or flagged).
    - Optionally, a synthesized improved version of the document.
  - Two approaches:
    - **Simple**: purely structure the per‑agent outputs and generate a deterministic merged report without additional LLM calls.
    - **Advanced**: use a configurable "synthesizer" agent to merge perspectives into an enhanced markdown version.

---

### 3. Integration with Document Enhancement Chain

- **Shared or sibling config model**
  - Extend `DocumentEnhancementConfig` or add a sibling config type with fields like:
    - `selected_agents: List[str]` (identifiers for Ready agents).
    - `question: str` (user's prompt).
    - `output_mode: {"review_report", "enhanced_markdown", "both"}`.
    - `use_synthesizer: bool` and optional `synthesizer_agent_id`.

- **Chain API**
  - Implement a function such as:
    - `run_multi_agent_review(config, doc_text) -> ReviewResult`.
  - Keep this logic independent of the TUI so it can be reused from CLI or a future API.
  - `ReviewResult` should be a structured object (dataclass or dict) containing:
    - Per‑agent responses (name, model, raw output, derived summary).
    - Optional merged summary.
    - Optional enhanced document content.

---

### 4. Results Presentation

- **TUI views**
  - For quick inspection inside the TUI:
    - A table listing each agent, its model, and a short outcome tag (e.g. "Major issues", "Minor suggestions", "Looks good").
    - Paginated panels for each agent's full perspective (using Rich `Panel` with clear headings).

- **File outputs**
  - When writing to disk, prefer non‑destructive patterns like:
    - `original.review.startd8.md` – multi‑agent review report.
    - `original.enhanced.startd8.md` – synthesized enhanced document, if produced.
  - Follow existing folder conventions (e.g. per‑agent or per‑tool subfolders) where applicable.

---

### 5. Configuration and Safeguards

- **ConfigManager integration**
  - Add config options (e.g. under a `tui` or `chat` section) for:
    - Max number of Ready agents to include by default.
    - Whether the mock agent is allowed in this flow.
    - Default use of the synthesizer step.
    - Default output mode (review only vs review + enhanced doc).

- **Safety and limits**
  - Define a maximum document size for direct inclusion in prompts.
  - For larger documents:
    - Either summarize first with a fast agent.
    - Or chunk and review section‑by‑section, with clear UX messaging.
  - Handle per‑agent failures gracefully (mark that agent as failed in the report rather than aborting the whole run).

---

### 6. Testing and Validation

- **Non‑TUI helper for tests**
  - Implement a function that accepts:
    - A path to a test `.md` file.
    - A fixed set of agent IDs.
    - A canned question.
  - Returns a `ReviewResult` object without any interactive TUI prompts, to support automated tests.

- **Manual TUI validation**
  - Verify behavior when:
    - There are 0 Ready agents (menu item disabled or clear error).
    - Only one Ready agent exists.
    - Multiple Ready agents with different types/models are available.
    - Some agents time out or error while others succeed.

This document is intended as a reviewable high‑level design for the startd8 chat multi‑agent document review feature; comments and refinements can be added directly below as needed.