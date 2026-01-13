# Startd8 Chat - Multi-Perspective LLM Discussion

## Overview

A new TUI menu option that allows users to submit a question or document to multiple LLMs with **Ready** status, gathering diverse perspectives and insights. Each LLM provides its unique viewpoint, and the responses can be synthesized into a comprehensive analysis.

## Key Differentiator from Document Enhancement Chain

| Feature | Document Enhancement Chain | Startd8 Chat |
|---------|---------------------------|--------------|
| **Purpose** | Sequentially refine a document | Gather multiple perspectives on a question |
| **Flow** | Serial (Agent1 → Agent2 → Agent3) | Parallel or Round-Table discussion |
| **Output** | Single enhanced document | Multiple perspectives + optional synthesis |
| **Focus** | Document improvement | Question exploration & diverse insights |

---

## Use Cases

### Primary Use Cases

1. **Multi-Perspective Analysis**
   - User has a design decision or question in a .md file
   - Multiple LLMs each provide their unique perspective
   - User gets diverse viewpoints to inform their decision

2. **Peer Review Simulation**
   - User submits a proposal document
   - Different LLMs act as "reviewers" with different focus areas
   - Collect feedback from multiple "experts"

3. **Brainstorming Session**
   - User poses an open-ended question
   - Multiple LLMs contribute ideas
   - Optional synthesis step combines best ideas

### Example Flow

```
User Question (design_question.md):
"Should we use Redis or PostgreSQL for session storage?"
                    ↓
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
[Anthropic]    [OpenAI]       [Gemini]
"Redis for     "PostgreSQL    "Hybrid: Redis
 speed..."      for ACID..."   for cache..."
    ↓               ↓               ↓
    └───────────────┼───────────────┘
                    ↓
         [Optional Synthesis Agent]
         "Summary of perspectives..."
                    ↓
         Final Output (multi_perspective_response.md)
```

---

## High-Level Architecture

### Components

1. **Multi-Perspective Chat Orchestrator**
   - Manages parallel or sequential agent calls
   - Collects and organizes responses
   - Optional synthesis step

2. **Ready Agent Selector**
   - Reuses `_get_ready_agents_for_selection()` from TUI
   - Filters to only show agents with Ready status
   - Allows multi-select for parallel perspectives

3. **Question/Document Loader**
   - File picker for .md files
   - Preview functionality
   - Extract question/content for prompts

4. **Response Aggregator & Display**
   - Collect responses from all agents
   - Side-by-side or tabbed display
   - Export to combined .md file

5. **Synthesis Engine (Optional)**
   - Designated "synthesizer" agent
   - Combines perspectives into summary
   - Highlights agreements/disagreements

---

## UI Flow Design

### Menu Integration

**Location:** Main TUI Menu

**New Menu Option:**
```
💬 Startd8 Chat (Multi-Perspective)
```

### User Flow

```
Step 1: Select Question/Document
├─ File picker (markdown files)
├─ OR enter question directly
├─ Preview content (optional)
└─ Confirm selection

Step 2: Select Ready Agents
├─ Display only agents with Ready status
├─ Multi-select agents (checkboxes)
├─ Minimum 2 agents recommended
├─ Show agent models for context
└─ Preview: "Getting perspectives from: Anthropic, OpenAI, Gemini"

Step 3: Configure Discussion Mode
├─ Parallel Mode: All agents respond independently (faster)
├─ Round-Table Mode: Agents can see previous responses (richer)
├─ Skip to parallel mode (default)
└─ Optional: Add custom context/instructions

Step 4: Configure Synthesis (Optional)
├─ Enable synthesis? (yes/no)
├─ If yes, select synthesizer agent
├─ Synthesis focus: "Compare", "Combine", "Debate summary"
└─ Skip if not needed

Step 5: Execute Discussion
├─ Show progress for each agent
├─ Display: "Asking Anthropic...", "Asking OpenAI..."
├─ Real-time response streaming (if supported)
└─ Token usage and cost tracking

Step 6: Review Perspectives
├─ Display each agent's response in panels
├─ Side-by-side comparison view
├─ Show synthesis (if enabled)
├─ Export options:
│   ├─ Combined document (all perspectives)
│   ├─ Individual responses
│   └─ Synthesis only
└─ Return to menu
```

---

## Data Models

```python
@dataclass
class ChatSessionConfig:
    """Configuration for multi-perspective chat session"""
    question_source: Union[Path, str]  # File path or direct question
    agents: List[BaseAgent]            # Selected ready agents
    mode: ChatMode                     # PARALLEL or ROUND_TABLE
    enable_synthesis: bool = False
    synthesis_agent: Optional[BaseAgent] = None
    synthesis_focus: Optional[str] = None  # "compare", "combine", "debate"
    custom_context: Optional[str] = None
    output_path: Optional[Path] = None

class ChatMode(Enum):
    PARALLEL = "parallel"      # All agents respond independently
    ROUND_TABLE = "round_table" # Agents see previous responses

@dataclass
class AgentPerspective:
    """Single agent's perspective/response"""
    agent_name: str
    agent_model: str
    response: str
    response_time_ms: int
    token_usage: TokenUsage
    timestamp: datetime

@dataclass
class ChatSessionResult:
    """Complete result from chat session"""
    config: ChatSessionConfig
    question: str
    perspectives: List[AgentPerspective]
    synthesis: Optional[str] = None
    total_time_ms: int = 0
    total_cost: float = 0.0
    output_path: Optional[Path] = None
```

---

## Core Implementation

### Multi-Perspective Chat Class

```python
class MultiPerspectiveChat:
    """
    Orchestrates multi-agent discussions for diverse perspectives.
    
    Supports:
    - Parallel mode: All agents respond simultaneously
    - Round-table mode: Agents see previous responses
    - Optional synthesis of all perspectives
    """
    
    def __init__(self, config: ChatSessionConfig):
        self.config = config
        self.perspectives: List[AgentPerspective] = []
    
    def run(
        self,
        on_agent_start: Optional[Callable] = None,
        on_agent_complete: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ) -> ChatSessionResult:
        """
        Execute the chat session.
        
        Flow:
        1. Load question from file or use direct input
        2. Build prompt for each agent
        3. Execute based on mode (parallel/round-table)
        4. Collect all perspectives
        5. Run synthesis if enabled
        6. Return combined result
        """
        pass
    
    def _run_parallel(self) -> List[AgentPerspective]:
        """Run all agents in parallel using ThreadPoolExecutor"""
        pass
    
    def _run_round_table(self) -> List[AgentPerspective]:
        """Run agents sequentially, each seeing previous responses"""
        pass
    
    def _synthesize(self, perspectives: List[AgentPerspective]) -> str:
        """Have synthesis agent summarize all perspectives"""
        pass
    
    def _build_prompt(
        self,
        question: str,
        previous_responses: Optional[List[AgentPerspective]] = None
    ) -> str:
        """Build prompt with optional previous responses for round-table"""
        pass
```

---

## Prompt Templates

### Parallel Mode Prompt

```python
PARALLEL_PROMPT_TEMPLATE = """
You are participating in a multi-perspective discussion. Please provide your unique perspective on the following question or document.

# Question/Document

{question_content}

{custom_context}

# Your Task

Provide your perspective on this topic. Be specific, draw on your strengths, and don't hesitate to offer a unique viewpoint. Focus on:
- Key insights you can offer
- Potential considerations or trade-offs
- Recommendations if applicable

Respond in markdown format.
"""
```

### Round-Table Mode Prompt

```python
ROUND_TABLE_PROMPT_TEMPLATE = """
You are participating in a round-table discussion. Other participants have already shared their perspectives. Please review their input and add your own unique viewpoint.

# Question/Document

{question_content}

# Previous Perspectives

{previous_perspectives}

{custom_context}

# Your Task

Consider the perspectives above, then add your own unique viewpoint. You may:
- Build on existing ideas
- Offer counterpoints or alternatives  
- Identify gaps in the discussion
- Synthesize or reconcile different views

Respond in markdown format.
"""
```

### Synthesis Prompt

```python
SYNTHESIS_PROMPT_TEMPLATE = """
You are tasked with synthesizing multiple perspectives on a topic.

# Original Question/Document

{question_content}

# Perspectives Collected

{all_perspectives}

# Synthesis Task: {synthesis_focus}

Please provide a synthesis that:
- Summarizes the key points from each perspective
- Identifies areas of agreement
- Highlights important disagreements or trade-offs
- Provides a balanced conclusion or recommendation

Respond in markdown format with clear sections.
"""
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (3-5 days)

- [ ] Create `ChatSessionConfig`, `AgentPerspective`, `ChatSessionResult` data models
- [ ] Implement `MultiPerspectiveChat` class with parallel execution
- [ ] Implement prompt building for parallel mode
- [ ] Add output formatting and file export
- [ ] Unit tests for core logic

### Phase 2: UI Integration (2-3 days)

- [ ] Add "💬 Startd8 Chat" menu option to main TUI menu
- [ ] Implement question/document selection UI (reuse file picker)
- [ ] Implement Ready agent multi-select UI (reuse `_get_ready_agents_for_selection`)
- [ ] Implement mode selection (parallel/round-table)
- [ ] Implement progress display for multiple agents
- [ ] Implement multi-panel response display

### Phase 3: Round-Table Mode (2-3 days)

- [ ] Implement sequential execution with context passing
- [ ] Build round-table prompt with previous responses
- [ ] Add order selection for round-table
- [ ] Test with real agents

### Phase 4: Synthesis Feature (1-2 days)

- [ ] Implement synthesis agent selection
- [ ] Build synthesis prompt template
- [ ] Add synthesis focus options (compare, combine, debate)
- [ ] Display synthesis in results

### Phase 5: Polish & Testing (2-3 days)

- [ ] Error handling for partial failures
- [ ] Cost estimation before execution
- [ ] Export options (combined, individual, synthesis-only)
- [ ] Integration testing with multiple real agents
- [ ] Documentation and examples

---

## File Structure

```
src/startd8/
├── multi_perspective_chat.py    # NEW: Core chat orchestration
├── tui_improved.py              # MODIFIED: Add chat menu + UI
└── models.py                    # MODIFIED: Add chat data models

docs/design/
└── STARTD8_CHAT_MULTI_PERSPECTIVE.md  # This document
```

---

## Integration Points

### With Existing TUI Infrastructure

- **Ready Agent Selection:** Reuse `_get_ready_agents_for_selection()` and `_select_ready_agent()`
- **File Picker:** Reuse document selection pattern from Document Enhancement Chain
- **Progress Display:** Reuse Live/Progress patterns from existing features
- **Agent Status:** Leverage `AgentConfigTester.test_all()` for Ready status

### With Agent Framework

- **Agent Instances:** Use same `BaseAgent` interface
- **Token Tracking:** Reuse `TokenUsage` model
- **Cost Calculation:** Reuse existing cost tracking

### With Config Manager

- **Settings:** Add `tui.chat_default_mode` (parallel/round_table)
- **Settings:** Add `tui.chat_enable_synthesis_default` (true/false)

---

## Success Criteria

1. ✅ User can select a question/document and multiple Ready agents
2. ✅ All selected agents provide independent perspectives (parallel mode)
3. ✅ Round-table mode allows agents to see previous responses
4. ✅ Optional synthesis combines all perspectives
5. ✅ Progress is displayed for each agent
6. ✅ Responses are displayed in a clear, comparable format
7. ✅ Output can be exported to .md file
8. ✅ Cost and token usage are tracked
9. ✅ Only agents with Ready status are selectable

---

## Example Output Format

```markdown
# Multi-Perspective Analysis

## Question
Should we use Redis or PostgreSQL for session storage?

---

## Perspective 1: Anthropic (claude-sonnet-4-20250514)

Redis excels for session storage due to its in-memory architecture...

**Key Points:**
- Sub-millisecond latency
- Built-in TTL for session expiry
- Simple key-value model matches session data

---

## Perspective 2: OpenAI (gpt-4o)

PostgreSQL offers advantages for session storage in certain contexts...

**Key Points:**
- ACID compliance for critical sessions
- No additional infrastructure
- Native JSON support

---

## Perspective 3: Gemini (gemini-2.0-flash)

A hybrid approach may serve best...

**Key Points:**
- Redis as cache layer
- PostgreSQL for persistence
- Fallback strategy

---

## Synthesis

After reviewing all perspectives, the consensus points toward...

**Agreements:**
- All acknowledge Redis's speed advantage
- All note PostgreSQL's reliability

**Key Trade-off:**
- Speed vs. durability

**Recommendation:**
Consider hybrid approach for production systems...

---

*Generated by Startd8 Chat • 3 agents • Total cost: $0.0234*
```

---

## Future Enhancements

1. **Debate Mode:** Agents explicitly argue for/against positions
2. **Expert Personas:** Assign roles (Security Expert, Performance Expert, etc.)
3. **Iterative Refinement:** Multiple rounds of discussion
4. **Voting/Consensus:** Agents vote on conclusions
5. **Chat History:** Save and continue previous discussions
6. **Templates:** Pre-built discussion formats for common scenarios
