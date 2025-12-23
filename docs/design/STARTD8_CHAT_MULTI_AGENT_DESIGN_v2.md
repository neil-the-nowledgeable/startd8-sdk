# Startd8 Chat: Multi-Agent Document Review

> **Version:** 2.0  
> **Status:** Design Specification  
> **Created:** December 6, 2025  
> **Updated:** December 6, 2025 (v2: Added streaming, conversation history, agent instantiation patterns)

---

## Table of Contents

1. [Overview](#overview)
2. [Comparison with Existing Features](#comparison-with-existing-features)
3. [Use Cases](#use-cases)
4. [Architecture](#architecture)
5. [User Flow](#user-flow)
6. [Data Models](#data-models)
7. [Core Implementation](#core-implementation)
8. [Agent Instantiation](#agent-instantiation) *(NEW in v2)*
9. [Streaming Support](#streaming-support) *(NEW in v2)*
10. [Conversation History](#conversation-history) *(NEW in v2)*
11. [Prompt Templates](#prompt-templates)
12. [Implementation Plan](#implementation-plan)
13. [Configuration](#configuration)
14. [Risk Mitigation](#risk-mitigation)
15. [Testing Strategy](#testing-strategy)
16. [Example Output](#example-output)
17. [Success Criteria](#success-criteria)
18. [Future Enhancements](#future-enhancements)

---

## Changelog (v2)

| Addition | Source | Description |
|----------|--------|-------------|
| **Streaming Support** | Document D | Real-time response streaming for better UX |
| **Conversation History** | Document D | Context management for round-table mode |
| **Agent Instantiation** | Document D | Centralized "get agent by name" pattern |
| **Interactive Mode** | Document D | Added to Future Enhancements |
| **MockAgent Testing** | Document D | Emphasized in Testing Strategy |

---

## Overview

### Goal

Add a new TUI menu item **"💬 Startd8 Chat: Multi-Agent Review"** that allows users to:

1. **Select a markdown document** to review
2. **Ask a question or provide instructions** about that document
3. **Route the request to all (or selected) agents with Ready status**
4. **Aggregate agent perspectives** into a structured review with optional synthesis

### Technical Strategy: Context Injection

The framework acts as a **bridge**: it reads local files, injects their content into prompts, sends them to AI agents, and writes the aggregated output back to disk. This solves the limitation of cloud agents not having direct file access.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Context Injection Flow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   [Local .md File]                                               │
│         │                                                        │
│         ▼                                                        │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│   │  Framework  │────▶│   Prompt    │────▶│   Agent     │       │
│   │  (Bridge)   │     │  (Injected) │     │   (Cloud)   │       │
│   └─────────────┘     └─────────────┘     └─────────────┘       │
│         │                                        │               │
│         │◀───────────────────────────────────────┘               │
│         ▼                                                        │
│   [Output .md File]                                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Comparison with Existing Features

| Feature | Document Enhancement Chain | Startd8 Chat (This Feature) | Single-Agent Chat* |
|---------|---------------------------|------------------------------|-------------------|
| **Purpose** | Sequentially refine a document | Gather multiple perspectives | Quick ad-hoc questions |
| **Agent Flow** | Serial (Agent1 → Agent2 → Agent3) | Parallel or Round-Table | Single agent |
| **Output** | Single enhanced document | Multiple perspectives + synthesis | TUI display only |
| **Focus** | Document improvement | Question exploration | Testing / quick queries |
| **Use Case** | Polish a draft | Get multi-reviewer feedback | Test agent connectivity |

*\*Single-Agent Chat is a related but separate feature (see Future Enhancements)*

---

## Use Cases

### Primary Use Cases

1. **Multi-Perspective Analysis**
   - User has a design decision or question in a `.md` file
   - Multiple LLMs each provide their unique perspective
   - User gets diverse viewpoints to inform their decision

2. **Peer Review Simulation**
   - User submits a proposal document
   - Different LLMs act as "reviewers" with different focus areas
   - Collect feedback from multiple "experts"

3. **Technical Decision Support**
   - User poses an architectural question
   - Agents provide trade-off analysis from different angles
   - Optional synthesis highlights consensus and disagreements

### Example Flow

```
User Document (architecture_decision.md):
"Should we use Redis or PostgreSQL for session storage?"

                         ↓
         ┌───────────────┼───────────────┐
         ↓               ↓               ↓
    [Claude]        [GPT-4]         [Gemini]
    "Redis for      "PostgreSQL     "Hybrid: Redis
     speed..."       for ACID..."    for cache..."
         ↓               ↓               ↓
         └───────────────┼───────────────┘
                         ↓
              [Optional Synthesizer]
              "Summary of perspectives..."
                         ↓
         Final Output (architecture_decision.review.startd8.md)
```

---

## Architecture

### Components

```
┌──────────────────────────────────────────────────────────────────┐
│                     Component Architecture                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    TUI Layer (tui_improved.py)              │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │ │
│  │  │ Doc Picker  │  │Agent Picker │  │ Progress Display    │  │ │
│  │  │ (reuse)     │  │ (reuse)     │  │ (Rich Live/Stream)  │  │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                    │
│                              ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              Orchestration Layer (multi_agent_chat.py)      │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │ │
│  │  │ Context     │  │ Executor    │  │ Aggregator          │  │ │
│  │  │ Builder     │  │ (Par/Seq)   │  │ + Synthesizer       │  │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │ │
│  │  ┌─────────────┐  ┌─────────────┐                           │ │
│  │  │ History     │  │ Agent       │  ← NEW in v2              │ │
│  │  │ Manager     │  │ Factory     │                           │ │
│  │  └─────────────┘  └─────────────┘                           │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                    │
│                              ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Agent Layer (BaseAgent)                  │ │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────────┐   │ │
│  │  │ Claude  │  │ GPT-4   │  │ Gemini  │  │ User Added    │   │ │
│  │  └─────────┘  └─────────┘  └─────────┘  └───────────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Reuse From |
|-----------|---------------|------------|
| **Document Picker** | Select `.md` file with validation & preview | `_select_document_for_enhancement()` |
| **Agent Picker** | Multi-select Ready agents | `_get_ready_agents_for_selection()` |
| **Agent Factory** | Centralized agent instantiation by ID | New (consolidate from cli.py) |
| **Context Builder** | Read file, build context object with metadata | New |
| **History Manager** | Track conversation context for round-table | New |
| **Executor** | Run agents (parallel or round-table) with streaming | New (uses `ThreadPoolExecutor`) |
| **Aggregator** | Collect responses, format output | New |
| **Synthesizer** | Optional LLM call to merge perspectives | New |

---

## User Flow

### Menu Integration

**Location:** Main TUI Menu (near Document Enhancement Chain)

**Menu Option:**
```
💬 Startd8 Chat: Multi-Agent Review
```

**Enable Condition:** At least one agent with Ready status

### Step-by-Step Flow

```
Step 1: Select Document
├─ File picker (markdown files only)
├─ Validation: exists, readable, not empty
├─ Preview: metadata, headings, first 50 lines (optional)
└─ Confirm selection

Step 2: Choose Agents
├─ Display Ready agents table:
│   ├─ Name, Type (Built-in/User Added), Model, Status
├─ Selection options:
│   ├─ "All Ready Agents" (quick option)
│   └─ "Choose Manually" (multi-select checkboxes)
├─ Minimum: 1 agent (2+ recommended for multiple perspectives)
└─ Preview: "Selected: Claude, GPT-4, Gemini"

Step 3: Enter Question/Instructions
├─ Prompt: "What would you like the agents to review or answer?"
├─ Multi-line text input
├─ Examples shown:
│   ├─ "Improve clarity and structure; flag logic gaps"
│   ├─ "What are the security implications of this design?"
│   └─ "Compare trade-offs and recommend an approach"
└─ Optional toggles (from config):
    ├─ Emphasis: writing quality vs technical correctness
    └─ Feedback type: structural only vs in-line suggestions

Step 4: Choose Execution Mode
├─ Parallel Mode (default, faster):
│   └─ All agents respond independently
├─ Round-Table Mode (richer):
│   └─ Each agent sees previous responses before adding theirs
└─ Skip: default to Parallel

Step 5: Configure Synthesis (Optional)
├─ Enable synthesis? (yes/no, default from config)
├─ If yes:
│   ├─ Select synthesizer agent (from Ready list)
│   └─ Synthesis focus: "Compare", "Combine", "Debate Summary"
└─ Skip if not needed

Step 6: Choose Output Destination
├─ Options:
│   ├─ Show in TUI only (no file)
│   ├─ Write review report to file
│   └─ Write review + enhanced document (if synthesis enabled)
├─ File naming: `{original}.review.startd8.md`
└─ Directory: same as source or configured output folder

Step 7: Execute (with streaming)
├─ Progress display per agent:
│   ├─ "Asking Claude..." → [streaming response] → "✓ Claude (2.3s)"
│   ├─ "Asking GPT-4..." → [streaming response] → "✓ GPT-4 (1.8s)"
├─ Show token usage and cost as agents complete
├─ Handle partial failures gracefully (mark failed, continue others)
└─ Run synthesis if enabled

Step 8: Review Results
├─ Display: Agent panels with responses (Rich Markdown rendering)
├─ Table: Summary of each agent's key findings
├─ Synthesis panel (if enabled)
├─ Cost summary: tokens, time, estimated cost
├─ Save confirmation (if file output selected)
└─ Return to menu
```

---

## Data Models

**File:** `src/startd8/models.py` (additions) and `src/startd8/multi_agent_chat.py`

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union, Callable, Dict

from .agents import BaseAgent
from .models import TokenUsage


class ChatMode(Enum):
    """Execution mode for multi-agent chat"""
    PARALLEL = "parallel"        # All agents respond independently
    ROUND_TABLE = "round_table"  # Agents see previous responses


class SynthesisFocus(Enum):
    """Focus type for synthesis step"""
    COMPARE = "compare"      # Highlight agreements/disagreements
    COMBINE = "combine"      # Merge best ideas into one
    DEBATE = "debate"        # Summarize as a debate


@dataclass
class ChatSessionConfig:
    """Configuration for multi-agent chat session"""
    source_document: Path                          # Path to .md file
    question: str                                  # User's question/instructions
    agents: List[BaseAgent]                        # Selected Ready agents
    mode: ChatMode = ChatMode.PARALLEL             # Execution mode
    enable_synthesis: bool = False                 # Run synthesis step?
    synthesis_agent: Optional[BaseAgent] = None    # Agent for synthesis
    synthesis_focus: SynthesisFocus = SynthesisFocus.COMPARE
    output_mode: str = "file"                      # "tui_only", "file", "file_with_enhanced"
    output_path: Optional[Path] = None             # Override default output path
    enable_streaming: bool = True                  # Stream responses in TUI (v2)


@dataclass
class DocumentContext:
    """Context object for the document being reviewed"""
    path: Path
    filename: str
    content: str
    line_count: int
    char_count: int
    headings: List[str]
    last_modified: datetime
    estimated_tokens: int  # Rough estimate for limit checking


@dataclass
class ConversationHistory:
    """Tracks conversation context for round-table mode (v2)"""
    entries: List[Dict[str, str]] = field(default_factory=list)
    
    def add(self, agent_name: str, response: str):
        """Add an agent's response to history"""
        self.entries.append({
            "agent": agent_name,
            "response": response,
            "timestamp": datetime.now().isoformat()
        })
    
    def format_for_prompt(self) -> str:
        """Format history for injection into round-table prompts"""
        if not self.entries:
            return "(No previous responses)"
        
        formatted = []
        for i, entry in enumerate(self.entries, 1):
            formatted.append(f"### Reviewer {i}: {entry['agent']}\n\n{entry['response']}")
        
        return "\n\n---\n\n".join(formatted)
    
    def clear(self):
        """Clear history for new session"""
        self.entries = []


@dataclass
class AgentPerspective:
    """Single agent's perspective/response"""
    agent_name: str
    agent_model: str
    agent_type: str              # "builtin" or "user_added"
    response: str
    summary_tag: str             # "Major issues", "Minor suggestions", "Looks good"
    response_time_ms: int
    token_usage: TokenUsage
    success: bool
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ChatSessionResult:
    """Complete result from multi-agent chat session"""
    config: ChatSessionConfig
    document_context: DocumentContext
    perspectives: List[AgentPerspective]
    synthesis: Optional[str] = None
    total_time_ms: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    output_path: Optional[Path] = None
    success: bool = True
    partial_failure: bool = False  # True if some agents failed
```

---

## Agent Instantiation

*(NEW in v2 - from Document D)*

### Problem

Agent instantiation logic is currently scattered across multiple files:
- `cli.py` has logic in `run_benchmark`
- `tui_improved.py` has logic in multiple methods
- Custom agents require different instantiation paths

### Solution: Centralized Agent Factory

**File:** `src/startd8/agent_factory.py`

```python
"""
Centralized agent instantiation.

This module provides a single place to get an agent instance by name/ID,
avoiding scattered instantiation logic across CLI, TUI, and other modules.
"""

from typing import Optional, Dict, Any
from .agents import BaseAgent, ClaudeAgent, GPT4Agent, MockAgent
from .custom_agents import CustomAgentManager


class AgentFactory:
    """
    Factory for creating agent instances by name.
    
    Usage:
        factory = AgentFactory(storage_dir)
        agent = factory.get_agent("claude")  # Returns ClaudeAgent instance
        agent = factory.get_agent("my-custom-agent")  # Returns custom agent
    """
    
    # Built-in agent mapping
    BUILTIN_AGENTS = {
        "claude": ClaudeAgent,
        "gpt4": GPT4Agent,
        "mock": MockAgent,
    }
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir
        self.custom_manager = CustomAgentManager(storage_dir) if storage_dir else None
    
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """
        Get an agent instance by ID.
        
        Args:
            agent_id: Agent identifier (e.g., "claude", "gpt4", "my-custom-agent")
        
        Returns:
            BaseAgent instance or None if not found
        """
        # Check built-in agents first
        if agent_id.lower() in self.BUILTIN_AGENTS:
            return self.BUILTIN_AGENTS[agent_id.lower()]()
        
        # Check custom agents
        if self.custom_manager:
            custom_agents = self.custom_manager.list_agents()
            for agent_config in custom_agents:
                if agent_config.get('id') == agent_id or agent_config.get('name') == agent_id:
                    return self.custom_manager.create_agent_instance(agent_config)
        
        return None
    
    def get_ready_agents(self, agent_status: Dict[str, Any]) -> List[BaseAgent]:
        """
        Get instances of all agents with Ready status.
        
        Args:
            agent_status: Dict from AgentConfigTester.test_all()
        
        Returns:
            List of BaseAgent instances that are working
        """
        ready = []
        for agent_id, status in agent_status.items():
            if status.get('working'):
                agent = self.get_agent(agent_id)
                if agent:
                    ready.append(agent)
        return ready
    
    def list_available_ids(self) -> List[str]:
        """List all available agent IDs (built-in + custom)"""
        ids = list(self.BUILTIN_AGENTS.keys())
        if self.custom_manager:
            for agent in self.custom_manager.list_agents():
                ids.append(agent.get('id', agent.get('name', 'unknown')))
        return ids
```

### Integration

```python
# In tui_improved.py
from .agent_factory import AgentFactory

class ImprovedTUI:
    def __init__(self, ...):
        ...
        self.agent_factory = AgentFactory(storage_dir)
    
    def _get_agent_by_id(self, agent_id: str) -> Optional[BaseAgent]:
        """Single method for agent lookup"""
        return self.agent_factory.get_agent(agent_id)
```

---

## Streaming Support

*(NEW in v2 - from Document D)*

### Overview

Streaming responses improve UX by showing partial results as they arrive, rather than waiting for the complete response.

### Implementation

**File:** `src/startd8/multi_agent_chat.py`

```python
from typing import Generator, Optional
from rich.live import Live
from rich.panel import Panel
from rich.markdown import Markdown


class StreamingResponseHandler:
    """
    Handles streaming responses from agents.
    
    For agents that support streaming, displays tokens as they arrive.
    For agents that don't, falls back to showing a spinner then full response.
    """
    
    def __init__(self, console: Console):
        self.console = console
    
    def stream_response(
        self,
        agent: BaseAgent,
        prompt: str,
        panel_title: str
    ) -> str:
        """
        Stream agent response with live display.
        
        Args:
            agent: The agent to call
            prompt: The prompt to send
            panel_title: Title for the display panel
        
        Returns:
            Complete response string
        """
        # Check if agent supports streaming
        if hasattr(agent, 'generate_stream'):
            return self._stream_with_live(agent, prompt, panel_title)
        else:
            return self._fallback_generate(agent, prompt, panel_title)
    
    def _stream_with_live(
        self,
        agent: BaseAgent,
        prompt: str,
        panel_title: str
    ) -> str:
        """Stream with Rich Live display"""
        response_chunks = []
        
        with Live(
            Panel("[dim]Waiting for response...[/dim]", title=panel_title),
            console=self.console,
            refresh_per_second=10
        ) as live:
            for chunk in agent.generate_stream(prompt):
                response_chunks.append(chunk)
                current_response = "".join(response_chunks)
                live.update(Panel(
                    Markdown(current_response),
                    title=panel_title,
                    border_style="cyan"
                ))
        
        return "".join(response_chunks)
    
    def _fallback_generate(
        self,
        agent: BaseAgent,
        prompt: str,
        panel_title: str
    ) -> str:
        """Fallback for non-streaming agents"""
        with self.console.status(f"[cyan]Thinking...[/cyan]", spinner="dots"):
            response, _, _ = agent.generate(prompt)
        
        self.console.print(Panel(
            Markdown(response),
            title=panel_title,
            border_style="green"
        ))
        
        return response
```

### Agent Streaming Interface

```python
# In src/startd8/agents/base.py - Optional streaming method

class BaseAgent:
    ...
    
    def generate_stream(self, prompt: str) -> Generator[str, None, None]:
        """
        Generate response with streaming (optional).
        
        Override this method to enable streaming for an agent.
        Default implementation calls generate() and yields full response.
        
        Yields:
            Response chunks as they become available
        """
        response, _, _ = self.generate(prompt)
        yield response
```

### TUI Integration

```python
# In tui_improved.py chat method

def _execute_agent_with_streaming(self, agent: BaseAgent, prompt: str) -> str:
    """Execute agent with optional streaming display"""
    handler = StreamingResponseHandler(self.console)
    return handler.stream_response(
        agent=agent,
        prompt=prompt,
        panel_title=f"{agent.name} ({agent.model})"
    )
```

---

## Conversation History

*(NEW in v2 - from Document D)*

### Overview

For Round-Table mode, each agent needs to see previous agents' responses. The `ConversationHistory` class manages this context.

### Usage in Round-Table Mode

```python
def _run_round_table(
    self,
    document_context: DocumentContext,
    callbacks: dict
) -> List[AgentPerspective]:
    """
    Run agents sequentially, each seeing previous responses.
    
    Uses ConversationHistory to accumulate context.
    """
    history = ConversationHistory()
    perspectives = []
    
    for i, agent in enumerate(self.config.agents):
        # Notify callback
        if callbacks.get('on_agent_start'):
            callbacks['on_agent_start'](agent.name)
        
        # Build prompt with history
        prompt = self._build_prompt(
            document_context,
            previous_responses=history.entries if i > 0 else None
        )
        
        # Generate response
        start_time = time.time()
        try:
            response, token_usage, _ = agent.generate(prompt)
            success = True
            error = None
        except Exception as e:
            response = ""
            token_usage = TokenUsage(0, 0)
            success = False
            error = str(e)
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        # Create perspective
        perspective = AgentPerspective(
            agent_name=agent.name,
            agent_model=agent.model,
            agent_type="builtin" if agent.name in ["Claude", "GPT-4", "Mock"] else "user_added",
            response=response,
            summary_tag=self._extract_summary_tag(response) if success else "Error",
            response_time_ms=elapsed_ms,
            token_usage=token_usage,
            success=success,
            error=error
        )
        perspectives.append(perspective)
        
        # Add to history for next agent (only if successful)
        if success:
            history.add(agent.name, response)
        
        # Notify callback
        if callbacks.get('on_agent_complete'):
            callbacks['on_agent_complete'](perspective)
    
    return perspectives
```

### History Format in Prompts

```
# PREVIOUS PERSPECTIVES

### Reviewer 1: Claude

Redis excels for session storage due to its in-memory architecture...

---

### Reviewer 2: GPT-4

PostgreSQL offers ACID compliance, which may matter for sensitive session data...
```

---

## Core Implementation

**File:** `src/startd8/multi_agent_chat.py`

```python
class MultiAgentChat:
    """
    Orchestrates multi-agent document review sessions.
    
    Supports:
    - Parallel mode: All agents respond simultaneously (ThreadPoolExecutor)
    - Round-table mode: Agents see previous responses sequentially
    - Optional synthesis: Designated agent merges all perspectives
    - Streaming responses (v2): Real-time display of agent output
    
    This class is TUI-independent and can be used from CLI or tests.
    """
    
    def __init__(
        self,
        config: ChatSessionConfig,
        framework: Optional[AgentFramework] = None,
        agent_factory: Optional[AgentFactory] = None  # v2
    ):
        self.config = config
        self.framework = framework
        self.agent_factory = agent_factory or AgentFactory()
        self.perspectives: List[AgentPerspective] = []
        self.history = ConversationHistory()  # v2
    
    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────
    
    def run(
        self,
        on_agent_start: Optional[Callable[[str], None]] = None,
        on_agent_complete: Optional[Callable[[AgentPerspective], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_stream_chunk: Optional[Callable[[str, str], None]] = None  # v2: (agent_name, chunk)
    ) -> ChatSessionResult:
        """
        Execute the multi-agent chat session.
        
        Args:
            on_agent_start: Callback when agent begins (agent_name)
            on_agent_complete: Callback when agent finishes (perspective)
            on_progress: Callback for progress (current, total)
            on_stream_chunk: Callback for streaming chunks (agent_name, chunk) - v2
        
        Returns:
            ChatSessionResult with all perspectives and optional synthesis
        """
        pass
    
    # ─────────────────────────────────────────────────────────────
    # File I/O (The "Bridge")
    # ─────────────────────────────────────────────────────────────
    
    def _load_document(self, path: Path) -> DocumentContext:
        """
        Load document from disk with metadata extraction.
        
        - Detects encoding (UTF-8, Latin-1, etc.)
        - Extracts headings, line count, char count
        - Estimates token count for limit checking
        """
        pass
    
    def _save_output(self, result: ChatSessionResult, path: Path) -> None:
        """
        Write aggregated result to disk.
        
        - Uses non-destructive naming: {original}.review.startd8.md
        - Creates parent directories if needed
        - Writes UTF-8 with proper line endings
        """
        pass
    
    # ─────────────────────────────────────────────────────────────
    # Prompt Building (The "Injector")
    # ─────────────────────────────────────────────────────────────
    
    def _build_prompt(
        self,
        document_context: DocumentContext,
        previous_responses: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Build prompt with document content injected.
        
        Uses PARALLEL_PROMPT_TEMPLATE or ROUND_TABLE_PROMPT_TEMPLATE
        based on mode and whether previous_responses is provided.
        
        v2: Uses ConversationHistory.format_for_prompt() for round-table.
        """
        pass
    
    def _build_synthesis_prompt(
        self,
        document_context: DocumentContext,
        perspectives: List[AgentPerspective]
    ) -> str:
        """Build prompt for synthesis agent to merge perspectives."""
        pass
    
    # ─────────────────────────────────────────────────────────────
    # Execution Modes
    # ─────────────────────────────────────────────────────────────
    
    def _run_parallel(
        self,
        document_context: DocumentContext,
        callbacks: dict
    ) -> List[AgentPerspective]:
        """
        Run all agents in parallel using ThreadPoolExecutor.
        
        - Max workers = min(len(agents), 5)  # Avoid rate limits
        - Each agent gets same prompt (no previous responses)
        - Collects results as they complete
        - v2: Supports streaming via on_stream_chunk callback
        """
        pass
    
    def _run_round_table(
        self,
        document_context: DocumentContext,
        callbacks: dict
    ) -> List[AgentPerspective]:
        """
        Run agents sequentially, each seeing previous responses.
        
        - Agent 1: sees only document + question
        - Agent 2: sees document + question + Agent 1's response
        - Agent N: sees document + question + all previous responses
        
        v2: Uses ConversationHistory for context management.
        """
        pass
    
    def _run_synthesis(
        self,
        document_context: DocumentContext,
        perspectives: List[AgentPerspective]
    ) -> str:
        """
        Run synthesis agent to merge all perspectives.
        
        Returns synthesized text (not a perspective object).
        """
        pass
    
    # ─────────────────────────────────────────────────────────────
    # Response Processing
    # ─────────────────────────────────────────────────────────────
    
    def _extract_summary_tag(self, response: str) -> str:
        """
        Extract or generate a summary tag from response.
        
        Tags: "Major issues", "Minor suggestions", "Looks good", "Error"
        """
        pass
    
    def _format_output(self, result: ChatSessionResult) -> str:
        """
        Format result as markdown for file output.
        """
        pass


# ─────────────────────────────────────────────────────────────────
# Non-TUI Helper for Tests
# ─────────────────────────────────────────────────────────────────

def run_multi_agent_review(
    doc_path: Path,
    agent_ids: List[str],
    question: str,
    mode: ChatMode = ChatMode.PARALLEL,
    enable_synthesis: bool = False,
    agent_factory: Optional[AgentFactory] = None  # v2
) -> ChatSessionResult:
    """
    Standalone function for automated testing.
    
    No TUI prompts—accepts all parameters directly.
    Returns ChatSessionResult for assertions.
    
    Example:
        result = run_multi_agent_review(
            doc_path=Path("test_doc.md"),
            agent_ids=["claude", "gpt4"],
            question="Review this design for security issues",
            mode=ChatMode.PARALLEL
        )
        assert result.success
        assert len(result.perspectives) == 2
    """
    pass
```

---

## Prompt Templates

**File:** `src/startd8/multi_agent_chat.py`

### Parallel Mode Prompt

```python
PARALLEL_PROMPT_TEMPLATE = """
You are a senior technical reviewer participating in a multi-perspective document review. Your task is to provide your unique perspective on the document below.

# DOCUMENT METADATA
- File: {filename}
- Lines: {line_count}
- Last Modified: {last_modified}

# DOCUMENT CONTENT

{document_content}

# REVIEW INSTRUCTIONS

{question}

# YOUR TASK

Provide your perspective as a reviewer. Be specific and actionable:

1. **Key Observations**: What stands out (positive or negative)?
2. **Issues Found**: Any bugs, gaps, inconsistencies, or risks?
3. **Suggestions**: Concrete improvements or alternatives?
4. **Verdict**: Overall assessment (Major issues / Minor suggestions / Looks good)

Respond in markdown format. Be concise but thorough.
"""
```

### Round-Table Mode Prompt

```python
ROUND_TABLE_PROMPT_TEMPLATE = """
You are participating in a round-table document review. Other reviewers have already shared their perspectives. Please review their input and add your own unique viewpoint.

# DOCUMENT METADATA
- File: {filename}
- Lines: {line_count}

# DOCUMENT CONTENT

{document_content}

# REVIEW INSTRUCTIONS

{question}

# PREVIOUS PERSPECTIVES

{previous_perspectives}

# YOUR TASK

Consider the perspectives above, then add your own:

1. **Your Unique Observations**: What did others miss or underemphasize?
2. **Agreements**: Which previous points do you endorse?
3. **Counterpoints**: Where do you disagree or see alternatives?
4. **Synthesis**: How would you reconcile differing views?
5. **Verdict**: Your overall assessment

Respond in markdown format.
"""
```

### Synthesis Prompt

```python
SYNTHESIS_PROMPT_TEMPLATE = """
You are tasked with synthesizing multiple reviewer perspectives into a coherent summary.

# ORIGINAL DOCUMENT

{document_content}

# REVIEW INSTRUCTIONS

{question}

# PERSPECTIVES COLLECTED

{all_perspectives}

# SYNTHESIS TASK: {synthesis_focus}

Please provide a synthesis that:

1. **Summary of Key Points**: What did each reviewer emphasize?
2. **Areas of Agreement**: Where do all/most reviewers align?
3. **Areas of Disagreement**: Where do opinions diverge? What are the trade-offs?
4. **Consolidated Recommendations**: A prioritized list of actions
5. **Final Verdict**: Overall assessment based on collective input

Respond in markdown format with clear section headings.
"""
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1)

| Task | File | Description |
|------|------|-------------|
| 1.1 | `models.py` | Add `ChatMode`, `SynthesisFocus`, `ChatSessionConfig`, `DocumentContext`, `AgentPerspective`, `ChatSessionResult`, `ConversationHistory` dataclasses |
| 1.2 | `agent_factory.py` | Create centralized `AgentFactory` class (v2) |
| 1.3 | `multi_agent_chat.py` | Create file, implement `_load_document()` with encoding detection |
| 1.4 | `multi_agent_chat.py` | Implement `_build_prompt()` with parallel template |
| 1.5 | `multi_agent_chat.py` | Implement `_run_parallel()` with ThreadPoolExecutor |
| 1.6 | `multi_agent_chat.py` | Implement `_format_output()` and `_save_output()` |

### Phase 2: TUI Integration (Week 1-2)

| Task | File | Description |
|------|------|-------------|
| 2.1 | `tui_improved.py` | Add menu option "💬 Startd8 Chat: Multi-Agent Review" |
| 2.2 | `tui_improved.py` | Implement `_run_multi_agent_chat()` entry point |
| 2.3 | `tui_improved.py` | Reuse `_select_document_for_enhancement()` for doc selection |
| 2.4 | `tui_improved.py` | Add agent multi-select UI (reuse `_get_ready_agents_for_selection()`) |
| 2.5 | `tui_improved.py` | Implement question input with examples |
| 2.6 | `tui_improved.py` | Implement progress display with Rich Live panels |
| 2.7 | `tui_improved.py` | Implement results display with per-agent panels |
| 2.8 | `tui_improved.py` | Integrate `AgentFactory` for agent instantiation (v2) |

### Phase 3: Round-Table Mode (Week 2)

| Task | File | Description |
|------|------|-------------|
| 3.1 | `multi_agent_chat.py` | Implement `ConversationHistory` class (v2) |
| 3.2 | `multi_agent_chat.py` | Implement `_run_round_table()` with history management |
| 3.3 | `multi_agent_chat.py` | Add round-table prompt template with previous responses |
| 3.4 | `tui_improved.py` | Add mode selection UI (Parallel / Round-Table) |

### Phase 4: Streaming & Synthesis (Week 2)

| Task | File | Description |
|------|------|-------------|
| 4.1 | `multi_agent_chat.py` | Implement `StreamingResponseHandler` class (v2) |
| 4.2 | `agents/base.py` | Add optional `generate_stream()` method to `BaseAgent` (v2) |
| 4.3 | `multi_agent_chat.py` | Implement `_build_synthesis_prompt()` |
| 4.4 | `multi_agent_chat.py` | Implement `_run_synthesis()` |
| 4.5 | `tui_improved.py` | Add synthesis configuration UI |

### Phase 5: Polish & Testing (Week 3)

| Task | File | Description |
|------|------|-------------|
| 5.1 | `multi_agent_chat.py` | Add error handling for partial failures |
| 5.2 | `multi_agent_chat.py` | Implement `run_multi_agent_review()` test helper |
| 5.3 | `tests/` | Unit tests: prompt building, output formatting, history management |
| 5.4 | `tests/` | Integration tests: **MockAgent chain first**, then real agent chain |
| 5.5 | `config.py` | Add config options for defaults |

---

## Configuration

**File:** `src/startd8/config.py` (additions)

```python
# Default config additions under 'chat' section
DEFAULT_CHAT_CONFIG = {
    "default_mode": "parallel",           # "parallel" or "round_table"
    "default_synthesis": False,           # Enable synthesis by default?
    "default_synthesis_focus": "compare", # "compare", "combine", "debate"
    "default_output_mode": "file",        # "tui_only", "file", "file_with_enhanced"
    "max_agents": 5,                      # Max agents to include by default
    "include_mock_agent": False,          # Allow mock agent in reviews?
    "max_document_chars": 100000,         # ~25K tokens, warn if exceeded
    "max_document_lines": 5000,           # Warn if exceeded
    "enable_streaming": True,             # Enable response streaming (v2)
}
```

**ConfigManager Integration:**

```python
# In tui_improved.py, access via:
chat_config = self.config_manager._config.get('chat', {})
default_mode = chat_config.get('default_mode', 'parallel')
enable_streaming = chat_config.get('enable_streaming', True)
```

---

## Risk Mitigation

### Risk 1: Token Limits

| Aspect | Details |
|--------|---------|
| **Risk** | Document content exceeds model's context window |
| **Detection** | Estimate tokens before sending: `chars / 4` (rough) or `tiktoken` for accuracy |
| **Mitigation** | Warn user if estimated tokens > 80% of model limit. Offer options: proceed anyway, summarize first, or cancel |
| **Implementation** | Add `estimated_tokens` to `DocumentContext`, check in `run()` before execution |

### Risk 2: Agent Hallucination/Truncation

| Aspect | Details |
|--------|---------|
| **Risk** | Agent returns summarized or truncated version instead of full review |
| **Detection** | N/A for reviews (we want agent's synthesis, not document echo) |
| **Mitigation** | Strict prompt instructions to stay on-topic. Validate response is non-empty. |
| **Implementation** | Check `len(response) > 50` before accepting |

### Risk 3: Partial Agent Failures

| Aspect | Details |
|--------|---------|
| **Risk** | Some agents fail (timeout, rate limit, API error) while others succeed |
| **Detection** | Catch exceptions per-agent in executor |
| **Mitigation** | Mark failed agents with `success=False`, continue with others. Report partial failure in result. |
| **Implementation** | Set `partial_failure=True` on `ChatSessionResult`, include error messages in output |

### Risk 4: Rate Limiting (Parallel Mode)

| Aspect | Details |
|--------|---------|
| **Risk** | Too many parallel requests trigger API rate limits |
| **Detection** | HTTP 429 responses |
| **Mitigation** | Limit ThreadPoolExecutor to 5 workers. Add 500ms delay between thread starts. |
| **Implementation** | `max_workers=min(len(agents), 5)`, optional staggered start |

### Risk 5: Large Document Performance

| Aspect | Details |
|--------|---------|
| **Risk** | Very large documents cause slow response times and high costs |
| **Detection** | Check `line_count > 5000` or `char_count > 100000` |
| **Mitigation** | Warn user with estimated cost. Offer chunking: review sections separately. |
| **Implementation** | Display warning panel in TUI, require confirmation to proceed |

### Risk 6: Streaming Compatibility (v2)

| Aspect | Details |
|--------|---------|
| **Risk** | Not all agents/providers support streaming |
| **Detection** | Check for `generate_stream` method on agent |
| **Mitigation** | Fallback to non-streaming with spinner display |
| **Implementation** | `StreamingResponseHandler._fallback_generate()` |

---

## Testing Strategy

### Unit Tests

**File:** `tests/test_multi_agent_chat.py`

```python
class TestMultiAgentChat:
    """Unit tests for multi-agent chat orchestration"""
    
    def test_load_document_utf8(self):
        """Load UTF-8 document with metadata extraction"""
        pass
    
    def test_load_document_encoding_detection(self):
        """Handle Latin-1 and other encodings"""
        pass
    
    def test_build_parallel_prompt(self):
        """Prompt includes document content and question"""
        pass
    
    def test_build_round_table_prompt_with_previous(self):
        """Round-table prompt includes previous responses"""
        pass
    
    def test_conversation_history_formatting(self):
        """ConversationHistory formats correctly for prompts (v2)"""
        history = ConversationHistory()
        history.add("Claude", "First response")
        history.add("GPT-4", "Second response")
        formatted = history.format_for_prompt()
        assert "Reviewer 1: Claude" in formatted
        assert "Reviewer 2: GPT-4" in formatted
    
    def test_extract_summary_tag_major_issues(self):
        """Extract 'Major issues' from critical response"""
        pass
    
    def test_extract_summary_tag_looks_good(self):
        """Extract 'Looks good' from positive response"""
        pass
    
    def test_format_output_markdown(self):
        """Output is valid markdown with all sections"""
        pass


class TestAgentFactory:
    """Unit tests for centralized agent instantiation (v2)"""
    
    def test_get_builtin_agent(self):
        """Get built-in agent by ID"""
        factory = AgentFactory()
        agent = factory.get_agent("mock")
        assert agent is not None
        assert agent.name == "Mock"
    
    def test_get_unknown_agent_returns_none(self):
        """Unknown agent ID returns None"""
        factory = AgentFactory()
        agent = factory.get_agent("nonexistent")
        assert agent is None
    
    def test_list_available_ids(self):
        """List includes built-in agents"""
        factory = AgentFactory()
        ids = factory.list_available_ids()
        assert "claude" in ids
        assert "gpt4" in ids
        assert "mock" in ids
```

### Integration Tests

**File:** `tests/test_multi_agent_chat_integration.py`

```python
class TestMultiAgentChatIntegration:
    """Integration tests with mock and real agents"""
    
    def test_parallel_mode_mock_agents(self):
        """
        Full flow with MockAgent (no API calls).
        
        IMPORTANT: Always test with MockAgent first to validate
        UI flow without incurring API costs.
        """
        result = run_multi_agent_review(
            doc_path=Path("tests/fixtures/sample_design.md"),
            agent_ids=["mock", "mock"],
            question="Review for clarity",
            mode=ChatMode.PARALLEL
        )
        assert result.success
        assert len(result.perspectives) == 2
    
    def test_round_table_mode_with_history(self):
        """Round-table with history context passing (v2)"""
        result = run_multi_agent_review(
            doc_path=Path("tests/fixtures/sample_design.md"),
            agent_ids=["mock", "mock", "mock"],
            question="Review iteratively",
            mode=ChatMode.ROUND_TABLE
        )
        assert result.success
        # Verify history was built correctly
        # (Would need to inspect internal state or prompts)
    
    def test_partial_failure_handling(self):
        """Continue when one agent fails"""
        result = run_multi_agent_review(
            doc_path=Path("tests/fixtures/sample_design.md"),
            agent_ids=["mock", "failing_mock"],
            question="Review",
            mode=ChatMode.PARALLEL
        )
        assert result.partial_failure
        assert len([p for p in result.perspectives if p.success]) == 1
    
    def test_synthesis_with_mock(self):
        """Synthesis step runs after perspectives"""
        result = run_multi_agent_review(
            doc_path=Path("tests/fixtures/sample_design.md"),
            agent_ids=["mock", "mock"],
            question="Review",
            mode=ChatMode.PARALLEL,
            enable_synthesis=True
        )
        assert result.synthesis is not None
    
    def test_agent_factory_integration(self):
        """AgentFactory correctly instantiates agents for review (v2)"""
        factory = AgentFactory()
        result = run_multi_agent_review(
            doc_path=Path("tests/fixtures/sample_design.md"),
            agent_ids=["mock"],
            question="Review",
            agent_factory=factory
        )
        assert result.success
```

### Manual TUI Validation Checklist

| Scenario | Expected Behavior |
|----------|-------------------|
| 0 Ready agents | Menu item disabled or shows error message |
| 1 Ready agent | Warn "2+ recommended for multiple perspectives", allow proceed |
| 5 Ready agents | All selectable, default "All Ready Agents" option works |
| Agent times out | Marked as failed, others continue, shown in results |
| Very large document | Warning shown with estimated cost, confirmation required |
| Round-table mode | Progress shows "Agent 2 reviewing Agent 1's feedback..." |
| Synthesis enabled | Extra step shown, synthesis appears in final output |
| File output | File created at `{original}.review.startd8.md` |
| **MockAgent flow (v2)** | **Always verify with MockAgent before using real agents** |
| **Streaming enabled (v2)** | Response text appears incrementally in TUI |
| **Streaming fallback (v2)** | Non-streaming agents show spinner then full response |

---

## Example Output

**File:** `architecture_decision.review.startd8.md`

```markdown
# Multi-Agent Review Report

## Document
**File:** architecture_decision.md  
**Lines:** 87  
**Reviewed:** 2025-12-06 14:32:15 UTC

## Question
Should we use Redis or PostgreSQL for session storage?

---

## Perspective 1: Claude (claude-sonnet-4-20250514)

**Verdict:** Minor suggestions

### Key Observations
Redis excels for session storage due to its in-memory architecture. Sub-millisecond latency is critical for session lookups on every request.

### Issues Found
- No mention of Redis persistence configuration (RDB vs AOF)
- Missing consideration of Redis Cluster for HA

### Suggestions
1. Add `appendonly yes` for session durability
2. Consider Redis Sentinel or Cluster for production
3. Document TTL strategy for session expiry

---

## Perspective 2: GPT-4 (gpt-4o)

**Verdict:** Minor suggestions

### Key Observations
PostgreSQL offers ACID compliance, which may matter for sensitive session data (e.g., financial applications).

### Issues Found
- Document assumes Redis without evaluating PostgreSQL's native JSON support
- No cost analysis (Redis requires separate infrastructure)

### Suggestions
1. For simple apps, PostgreSQL sessions reduce infrastructure complexity
2. Use `UNLOGGED` tables for speed if durability isn't critical
3. Consider hybrid: PostgreSQL for persistence, Redis for caching

---

## Perspective 3: Gemini (gemini-pro)

**Verdict:** Looks good

### Key Observations
The hybrid approach mentioned in the document is solid. Redis as a cache layer with PostgreSQL backing provides the best of both worlds.

### Agreements
- Agree with Claude on Redis TTL strategy
- Agree with GPT-4 on hybrid approach

### Additional Suggestions
1. Add circuit breaker for Redis failures (fallback to PostgreSQL)
2. Document session serialization format (JSON vs MessagePack)

---

## Synthesis

### Summary
All reviewers acknowledge Redis's speed advantage for session storage. GPT-4 and Gemini both suggest considering PostgreSQL as a persistence layer or fallback.

### Agreements
- Redis is ideal for low-latency session lookups
- Durability configuration is missing from the current design
- A hybrid approach offers resilience

### Disagreements
- Claude focuses on pure Redis with persistence
- GPT-4 advocates PostgreSQL-first for simpler stacks

### Recommendations (Prioritized)
1. **High:** Define TTL and persistence strategy for Redis
2. **Medium:** Implement fallback to PostgreSQL on Redis failure
3. **Low:** Evaluate cost impact of running both systems

### Final Verdict
The document provides a reasonable starting point. Address durability and failover concerns before production deployment.

---

*Generated by Startd8 Chat • 3 agents • Mode: Parallel • Synthesis: Compare*  
*Total tokens: 4,521 • Estimated cost: $0.0234 • Time: 8.7s*
```

---

## Success Criteria

| # | Criterion | Testable? |
|---|-----------|-----------|
| 1 | User can select a `.md` document and multiple Ready agents | ✓ Manual |
| 2 | All selected agents provide independent perspectives (parallel mode) | ✓ Integration test |
| 3 | Round-table mode passes previous responses to subsequent agents | ✓ Integration test |
| 4 | Optional synthesis combines all perspectives | ✓ Integration test |
| 5 | Progress is displayed for each agent during execution | ✓ Manual |
| 6 | Responses are displayed in a clear, comparable panel format | ✓ Manual |
| 7 | Output can be exported to `.md` file with consistent naming | ✓ Unit test |
| 8 | Cost and token usage are tracked and displayed | ✓ Integration test |
| 9 | Only agents with Ready status are selectable | ✓ Unit test |
| 10 | Partial failures are handled gracefully (others continue) | ✓ Integration test |
| 11 | Large documents trigger a warning before execution | ✓ Manual |
| 12 | Menu item is disabled when no Ready agents exist | ✓ Manual |
| 13 | **AgentFactory centralizes agent instantiation (v2)** | ✓ Unit test |
| 14 | **Streaming responses display incrementally (v2)** | ✓ Manual |
| 15 | **ConversationHistory correctly tracks round-table context (v2)** | ✓ Unit test |
| 16 | **MockAgent works for full UI flow testing (v2)** | ✓ Integration test |

---

## Future Enhancements

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| **Single-Agent Chat** | Interactive chat loop with one agent for quick testing (from Document D) | **High** |
| **Debate Mode** | Agents explicitly argue for/against positions | Medium |
| **Expert Personas** | Assign roles: Security Expert, Performance Expert, UX Expert | Medium |
| **Iterative Refinement** | Multiple discussion rounds | Low |
| **Voting/Consensus** | Agents vote on conclusions | Low |
| **Chat History Persistence** | Save and continue previous discussions | Medium |
| **Templates** | Pre-built prompts: "Security Review", "Code Review", "Architecture Review" | High |
| **Chunked Review** | Split large documents into sections, review each | Medium |
| **Cost Estimation** | Show estimated cost before execution | High |
| **Native Streaming for Claude/GPT-4** | Implement `generate_stream()` for built-in agents | Medium |

### Single-Agent Chat Mode (from Document D)

A simpler feature for quick ad-hoc questions:

```
💬 Chat with Agent (Single)

- Select one Ready agent
- Enter questions interactively
- No document required
- Exit with 'quit' / 'exit' / 'back'

Use case: Quick testing, simple questions, agent verification
```

This would complement the multi-agent review feature and could share infrastructure (AgentFactory, streaming).

---

## File Structure

```
src/startd8/
├── multi_agent_chat.py      # NEW: Core orchestration logic
├── agent_factory.py         # NEW: Centralized agent instantiation (v2)
├── models.py                # MODIFIED: Add chat data models + ConversationHistory
├── config.py                # MODIFIED: Add chat config defaults
├── agents/
│   └── base.py              # MODIFIED: Add optional generate_stream() (v2)
└── tui_improved.py          # MODIFIED: Add menu + UI flow + streaming

tests/
├── test_multi_agent_chat.py              # NEW: Unit tests
├── test_multi_agent_chat_integration.py  # NEW: Integration tests
├── test_agent_factory.py                 # NEW: Agent factory tests (v2)
└── fixtures/
    └── sample_design.md                  # NEW: Test fixture

docs/design/
└── STARTD8_CHAT_MULTI_AGENT_DESIGN_v2.md  # This document
```

---

*Document Version: 2.0 • Last Updated: December 6, 2025*  
*Changes from v1: Added streaming support, conversation history management, centralized agent instantiation, enhanced testing strategy with MockAgent emphasis*
