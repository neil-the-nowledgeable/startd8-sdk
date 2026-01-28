# Prime Contractor Workflow Guide

## StartD8 SDK (ContextCore-Beaver / Beaver)

**Version:** 0.4.0  
**Last Updated:** January 25, 2026  
**Audience:** Humans and AI Agents

---

## Table of Contents

1. [Key Questions Answered](#key-questions-answered)
2. [Overview](#overview)
3. [Architecture](#architecture)
4. [The Prime Contractor Pattern](#the-prime-contractor-pattern)
5. [Quick Start](#quick-start)
6. [Installation](#installation)
7. [Configuration](#configuration)
8. [Task Specification](#task-specification)
9. [Running Workflows](#running-workflows)
10. [Model Selection Guide](#model-selection-guide)
11. [Cost Optimization](#cost-optimization)
12. [ContextCore Integration](#contextcore-integration)
13. [Best Practices](#best-practices)
14. [API Reference](#api-reference)
15. [Troubleshooting](#troubleshooting)
16. [Examples](#examples)

---

## Key Questions Answered

### Q1: Is the Prime Contractor Pattern something we need to build first?

**No. It's already built and ready to use.**

The Prime Contractor Pattern (Drafter → Reviewer → Revision loop) is fully implemented in the StartD8 SDK:

- `LeadContractorWorkflow` - The core workflow class
- `LeadContractorContextCoreWorkflow` - With ContextCore task tracking integration

You can use it **right now** by:

```python
from startd8.workflows.builtin import LeadContractorWorkflow

workflow = LeadContractorWorkflow()
result = workflow.run(config={
    "task_description": "Your implementation task here"
})
```

Or via CLI:
```bash
python scripts/run_contextcore_workflow.py \
    --task-id TASK-001 \
    --task-description "Your task" \
    --project-id my-project
```

### Q2: How does Beaver integrate? Is it the LLM abstraction layer?

**Yes. Beaver (StartD8 SDK) IS the LLM abstraction layer.**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              YOUR APPLICATION                                │
│                          (e.g., Squirrel, ContextCore)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     BEAVER (StartD8 SDK) - ABSTRACTION LAYER                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────┐   ┌─────────────────────────────────────────────┐  │
│  │  WORKFLOW LAYER     │   │  AGENT ABSTRACTION                          │  │
│  │  ─────────────────  │   │  ─────────────────────────                  │  │
│  │  • LeadContractor   │   │  • BaseAgent interface                      │  │
│  │  • Pipeline         │   │  • Unified generate() API                   │  │
│  │  • Benchmark        │   │  • Token tracking                           │  │
│  │  • DocumentEnhance  │   │  • Cost calculation                         │  │
│  └─────────────────────┘   └─────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  PROVIDER REGISTRY (Pluggable Backends)                                 ││
│  │  ─────────────────────────────────────────────────────────────────────  ││
│  │  "anthropic:claude-sonnet-4-5-20250927" → ClaudeAgent                   ││
│  │  "gemini:gemini-2.5-flash-lite"         → GeminiAgent                   ││
│  │  "openai:gpt-4.1-nano"                  → GPT4Agent                     ││
│  │  "ollama:llama3"                        → OllamaAgent                   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
            ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
            │  Anthropic  │   │   Google    │   │   OpenAI    │
            │    API      │   │  Gemini API │   │    API      │
            └─────────────┘   └─────────────┘   └─────────────┘
```

**Key Point:** You don't call LLM APIs directly. You call Beaver, and it:
1. Resolves `"gemini:gemini-2.5-flash-lite"` to the correct provider
2. Creates the appropriate agent instance
3. Handles authentication, retries, error handling
4. Tracks tokens and costs
5. Returns unified response format

### Q3: Should implementation tasks be executed now (A) or defined for later (B)?

**Both options are valid. Choose based on your situation:**

| Scenario | Recommendation | Why |
|----------|----------------|-----|
| **Exploratory/Complex design** | (A) Execute now with Claude Opus 4.5 | You're in conversation, can iterate, ask questions |
| **Well-defined implementation tasks** | (B) Define as workflow tasks | Automated, tracked, cost-optimized |
| **Hybrid approach** | Design with Opus, implement with workflow | Best of both worlds |

#### Option A: Execute Now (Interactive Mode)

When you (Claude Opus 4.5 in Cursor) directly implement:

```
✅ Best for:
   - Complex architectural decisions
   - Tasks requiring back-and-forth clarification
   - Exploratory coding
   - When you need to see the codebase context

❌ Less ideal for:
   - Batch of similar tasks
   - Cost-sensitive projects
   - Tasks that need tracking/audit trail
```

#### Option B: Define as Workflow Tasks (Automated Mode)

When you define tasks for the Prime Contractor Pattern:

```
✅ Best for:
   - Well-specified implementation tasks
   - Batch processing multiple tasks
   - Cost optimization (uses cheaper drafters)
   - Audit trail / project tracking
   - Reproducible workflows

❌ Less ideal for:
   - Tasks needing real-time clarification
   - Complex multi-file refactoring
   - When codebase context is critical
```

#### Recommended Hybrid Approach

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: DESIGN (You - Claude Opus 4.5 in Cursor)             │
│  ─────────────────────────────────────────────────────────────  │
│  • Understand requirements                                      │
│  • Design architecture                                          │
│  • Break down into discrete tasks                               │
│  • Create task specifications                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2: TASK DEFINITION (You create task specs)              │
│  ─────────────────────────────────────────────────────────────  │
│  Create YAML or ContextCore tasks with detailed prompts:       │
│                                                                 │
│  - task_id: SQUIRREL-001                                       │
│    title: "Implement TokenBucket rate limiter"                 │
│    config:                                                      │
│      task_description: |                                        │
│        [Detailed spec you write based on design]               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3: EXECUTION (Prime Contractor Workflow)                │
│  ─────────────────────────────────────────────────────────────  │
│  python scripts/run_contextcore_workflow.py \                  │
│      --from-contextcore \                                       │
│      --project-id squirrel \                                    │
│      --yes                                                      │
│                                                                 │
│  → Claude Sonnet 4.5 creates specs                             │
│  → Gemini 2.5 Flash Lite drafts implementation                 │
│  → Claude Sonnet 4.5 reviews                                   │
│  → Iterate until pass                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 4: INTEGRATION (You - Claude Opus 4.5 in Cursor)        │
│  ─────────────────────────────────────────────────────────────  │
│  • Review generated code                                        │
│  • Integrate into codebase                                      │
│  • Handle edge cases workflow missed                            │
│  • Final testing                                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Overview

### What is Beaver (StartD8 SDK)?

**Beaver** (also known as **ContextCore-Beaver** or **StartD8 SDK**) is a Python SDK and CLI tool for orchestrating multi-LLM agent workflows. It provides:

- **LLM Abstraction Layer** - Unified interface to call Anthropic, Google, OpenAI, Ollama models
- **Cost-efficient multi-agent patterns** - Claude acts as architect/reviewer while cheaper models do drafting work
- **Unified task tracking** - Integration with ContextCore for project observability
- **Iterative development** - Automated draft/review cycles until quality thresholds are met
- **Model benchmarking** - Compare different LLMs on the same tasks

### Why "Prime Contractor"?

The workflow is modeled after construction industry practices:

| Construction | AI Workflow |
|--------------|-------------|
| Prime Contractor | Claude (Sonnet 4.5/Opus 4.5) |
| Subcontractor | Gemini Flash Lite, GPT-4.1-nano |
| Blueprint | Implementation Specification |
| Inspection | Code Review |
| Final Walkthrough | Integration Phase |

The Prime Contractor (Claude) provides expertise, creates specifications, reviews work, and ensures quality—while cost-efficient subcontractors (Gemini, GPT-4.1-nano) handle the bulk of implementation work.

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STARTD8 SDK (BEAVER)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        WORKFLOW LAYER                                  │  │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐  │  │
│  │  │LeadContractor   │ │Pipeline         │ │DocumentEnhancement     │  │  │
│  │  │Workflow         │ │                 │ │Chain                   │  │  │
│  │  │                 │ │ step1 → step2   │ │                        │  │  │
│  │  │ Spec→Draft→     │ │   → step3       │ │ agent1 → agent2 →      │  │  │
│  │  │ Review→Integrate│ │                 │ │ agent3                 │  │  │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                     │                                        │
│                                     ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      AGENT ABSTRACTION LAYER                          │  │
│  │                                                                        │  │
│  │  class BaseAgent:                                                      │  │
│  │      def generate(prompt: str) -> Tuple[str, int, TokenUsage]         │  │
│  │                                                                        │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │  │
│  │  │ ClaudeAgent  │ │ GeminiAgent  │ │ GPT4Agent    │ │ OllamaAgent  │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                     │                                        │
│                                     ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                       PROVIDER REGISTRY                                │  │
│  │                                                                        │  │
│  │  ProviderRegistry.discover()  # Auto-discovers via entry points       │  │
│  │                                                                        │  │
│  │  resolve_agent_spec("anthropic:claude-sonnet-4-5-20250927")           │  │
│  │    → AnthropicProvider.create_agent("claude-sonnet-4-5-20250927")     │  │
│  │    → ClaudeAgent instance                                              │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                       SUPPORTING SERVICES                              │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │  │
│  │  │CostTracker  │ │PricingService│ │BudgetManager│ │ContextCore     │  │  │
│  │  │             │ │             │ │             │ │Integration     │  │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How Agent Resolution Works

When you specify an agent like `"gemini:gemini-2.5-flash-lite"`:

```python
from startd8.utils.agent_resolution import resolve_agent_spec

# This single line:
agent = resolve_agent_spec("gemini:gemini-2.5-flash-lite")

# Does all of this internally:
# 1. Parse "gemini:gemini-2.5-flash-lite" → provider="gemini", model="gemini-2.5-flash-lite"
# 2. Look up GeminiProvider in ProviderRegistry
# 3. Validate configuration (API key from GOOGLE_API_KEY env var)
# 4. Create GeminiAgent with correct settings
# 5. Return ready-to-use agent with unified interface
```

### What's Already Built vs What You Build

| Component | Status | Description |
|-----------|--------|-------------|
| **Provider Registry** | ✅ Built | Auto-discovers Anthropic, OpenAI, Gemini, Ollama |
| **Agent Classes** | ✅ Built | ClaudeAgent, GPT4Agent, GeminiAgent, etc. |
| **LeadContractorWorkflow** | ✅ Built | The Prime Contractor Pattern |
| **Cost Tracking** | ✅ Built | CostTracker, PricingService, BudgetManager |
| **ContextCore Integration** | ✅ Built | Task-as-spans tracking |
| **CLI Runner** | ✅ Built | `run_contextcore_workflow.py` |
| **Your Application** | 🔨 You Build | Uses Beaver as the LLM layer |

---

## The Prime Contractor Pattern

### Workflow Phases

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PRIME CONTRACTOR WORKFLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 1: SPECIFICATION (Lead Agent - Claude)                        │   │
│  │  • Analyze task requirements                                          │   │
│  │  • Create detailed implementation spec                                │   │
│  │  • Define acceptance criteria                                         │   │
│  │  • Identify edge cases                                                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                     │                                        │
│                                     ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 2: DRAFTING (Drafter Agent - Gemini/GPT)                      │   │
│  │  • Implement from specification                                       │   │
│  │  • Follow requirements exactly                                        │   │
│  │  • Handle edge cases                                                  │   │
│  │  • Document implementation                                            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                     │                                        │
│                                     ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 3: REVIEW (Lead Agent - Claude)                               │   │
│  │  • Score implementation (0-100)                                       │   │
│  │  • Identify issues and blocking problems                              │   │
│  │  • Provide specific feedback                                          │   │
│  │  • Verdict: PASS (≥80) or FAIL                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                     │                                        │
│                    ┌────────────────┴────────────────┐                       │
│                    │                                 │                       │
│               FAIL │                                 │ PASS                  │
│                    ▼                                 ▼                       │
│  ┌─────────────────────────────┐   ┌────────────────────────────────────┐   │
│  │  PHASE 4: REVISION          │   │  PHASE 5: INTEGRATION (Lead)       │   │
│  │  • Incorporate feedback     │   │  • Final polish                    │   │
│  │  • Fix blocking issues      │   │  • Production-ready cleanup        │   │
│  │  • Re-submit for review     │   │  • Integration notes               │   │
│  │  (max 3 iterations)         │   │  • Test plan generation            │   │
│  └─────────────────────────────┘   └────────────────────────────────────┘   │
│                    │                                                         │
│                    └──────────────► (Back to Phase 3)                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cost Structure (January 2026)

#### Lead Agents (Claude 4.5 Family)

| Model | Input | Output | Best For |
|-------|-------|--------|----------|
| **Claude Sonnet 4.5** | $3.00/1M | $15.00/1M | Default - best for coding/agents |
| Claude Opus 4.5 | $5.00/1M | $25.00/1M | Most intelligent, complex reasoning |
| Claude Haiku 4.5 | $1.00/1M | $5.00/1M | Fastest, near-frontier performance |

#### Drafter Agents (Cost-Efficient)

| Model | Input | Output | Best For |
|-------|-------|--------|----------|
| **Gemini 2.5 Flash Lite** | $0.075/1M | $0.30/1M | **Default** - best value |
| GPT-4.1-nano | $0.10/1M | $0.40/1M | Ultra-fast, lowest cost |
| Gemini 3 Flash Preview | $0.10/1M | $0.40/1M | Latest, experimental |
| GPT-4o-mini | $0.15/1M | $0.60/1M | Reliable, legacy |
| Gemini 2.5 Flash | $0.15/1M | $0.60/1M | Balanced performance |

### Cost Savings Example

| Approach | Spec | Draft×2 | Review×2 | Integrate | **Total** |
|----------|------|---------|----------|-----------|-----------|
| Claude-only | $0.15 | $0.30 | $0.30 | $0.15 | **$0.90** |
| Prime Contractor | $0.15 | $0.02 | $0.30 | $0.15 | **$0.62** |

**Savings: ~30%** with equivalent quality (Claude reviews all output)

---

## Quick Start

### 1. Install Beaver

```bash
# Install from PyPI
pip install startd8

# Or install with all providers
pip install startd8[all]

# Or from source
cd startd8-sdk
pip install -e ".[all]"
```

### 2. Set API Keys

```bash
export ANTHROPIC_API_KEY="sk-ant-..."    # Required for Claude
export GOOGLE_API_KEY="..."              # For Gemini models
export OPENAI_API_KEY="sk-..."           # For GPT models
```

### 3. Run Your First Task

```python
from startd8.workflows.builtin import LeadContractorWorkflow

workflow = LeadContractorWorkflow()

result = workflow.run(config={
    "task_description": """
    Implement a rate limiter using the token bucket algorithm.
    
    Requirements:
    1. TokenBucket class with configurable capacity and refill rate
    2. acquire() method returns True if token available
    3. wait_for_token() async method
    4. Thread-safe using asyncio.Lock
    
    Output: Python module
    """,
    "context": {
        "language": "Python",
        "framework": "asyncio"
    }
})

print(f"Success: {result.success}")
print(f"Cost: ${result.metrics.total_cost:.4f}")
print(result.output["final_implementation"])
```

---

## Installation

### Requirements

- Python 3.9+ (venv uses 3.14)
- API keys for at least one provider (Anthropic recommended)

### Install Methods

```bash
# Basic installation
pip install startd8

# With specific providers
pip install startd8[anthropic]      # Claude only
pip install startd8[openai]         # GPT only
pip install startd8[gemini]         # Gemini only
pip install startd8[all]            # All providers

# Development installation
pip install startd8[all,dev]
```

### Verify Installation

```bash
# Check CLI
startd8 --help

# Check providers
python -c "from startd8.providers import ProviderRegistry; ProviderRegistry.discover(); print(ProviderRegistry.list_providers())"
```

---

## Configuration

### Workflow Configuration Schema

```python
config = {
    # REQUIRED
    "task_description": str,  # What to implement
    
    # OPTIONAL - Task Context
    "context": {              # Additional context dict
        "language": str,      # Programming language
        "framework": str,     # Framework being used
        "file": str,          # Target file path
        "existing_code": str, # Existing code to modify
        # ... any other context
    },
    
    # OPTIONAL - Agent Selection
    "lead_agent": str,        # Default: "anthropic:claude-sonnet-4-5-20250927"
    "drafter_agent": str,     # Default: "gemini:gemini-2.5-flash-lite"
    
    # OPTIONAL - Workflow Tuning
    "max_iterations": int,    # Default: 3 (1-10)
    "pass_threshold": int,    # Default: 80 (0-100)
    
    # OPTIONAL - Output Control
    "output_format": str,     # Expected output format guidance
    "integration_instructions": str,  # Final integration notes
    
    # OPTIONAL - ContextCore Tracking
    "task_id": str,           # ContextCore task ID
    "project_id": str,        # ContextCore project ID
    "parent_id": str,         # Parent task/story ID
    "sprint_id": str,         # Sprint identifier
}
```

### Agent Specification Format

Agents are specified as `provider:model` strings:

```python
# Anthropic Claude
"anthropic:claude-sonnet-4-5-20250927"    # Sonnet 4.5 (recommended)
"anthropic:claude-opus-4-5-20251101"      # Opus 4.5 (most capable)
"anthropic:claude-haiku-4-5-20251008"     # Haiku 4.5 (fastest)

# Google Gemini
"gemini:gemini-2.5-flash-lite"            # Best value (recommended drafter)
"gemini:gemini-2.5-flash"                 # Balanced
"gemini:gemini-3-flash-preview"           # Latest

# OpenAI GPT
"openai:gpt-4.1-nano"                     # Ultra-fast, lowest cost
"openai:gpt-4.1-mini"                     # Fast, cost-efficient
"openai:gpt-4o-mini"                      # Reliable legacy
```

---

## Task Specification

### Writing Effective Task Descriptions

A good task description has these components:

```markdown
## Task Title

[Brief summary of what needs to be built]

## Requirements
1. [Specific requirement 1]
2. [Specific requirement 2]
3. [Specific requirement 3]

## Technical Constraints
- [Constraint 1: e.g., "Must use asyncio"]
- [Constraint 2: e.g., "Python 3.9+ compatible"]

## Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]

## Edge Cases
- [Edge case 1]
- [Edge case 2]

## Output Format
[What the output should look like - file structure, class names, etc.]
```

### Example: Good vs Bad Task Descriptions

❌ **Bad:**
```
"Implement caching"
```

✅ **Good:**
```
Implement a caching layer using Redis.

Requirements:
1. Create CacheService class with get(), set(), delete() methods
2. Support TTL (time-to-live) for cache entries
3. Handle Redis connection failures gracefully
4. Add retry logic with exponential backoff

Acceptance Criteria:
- All methods have type hints
- Connection errors don't crash the application
- TTL is configurable per-key
- Includes unit tests

Output: Python module with CacheService class
```

### Context Object

The `context` dict provides additional information to both agents:

```python
config = {
    "task_description": "Implement user authentication",
    "context": {
        # Code context
        "language": "Python",
        "framework": "FastAPI",
        "file": "src/auth/service.py",
        
        # Existing code
        "existing_models": ["User", "Session"],
        "database": "PostgreSQL",
        "orm": "SQLAlchemy 2.0",
        
        # Project context
        "test_framework": "pytest",
        "style_guide": "Google Python Style",
        
        # Constraints
        "python_version": "3.11+",
        "no_external_deps": True,
    }
}
```

---

## Running Workflows

### Method 1: Python API

```python
from startd8.workflows.builtin import LeadContractorWorkflow

# Create workflow
workflow = LeadContractorWorkflow()

# Run with configuration
result = workflow.run(config={
    "task_description": "Your task here",
    "drafter_agent": "gemini:gemini-2.5-flash-lite",
    "max_iterations": 3,
})

# Check results
if result.success:
    print(result.output["final_implementation"])
else:
    print(f"Failed: {result.error}")

# Access metrics
print(f"Cost: ${result.metrics.total_cost:.4f}")
print(f"Time: {result.metrics.total_time_ms}ms")
print(f"Tokens: {result.metrics.input_tokens} in / {result.metrics.output_tokens} out")
```

### Method 2: CLI with Single Task

```bash
python scripts/run_contextcore_workflow.py \
    --task-id TASK-001 \
    --task-description "Implement rate limiter using token bucket algorithm" \
    --project-id my-project \
    --drafter-agent "gemini:gemini-2.5-flash-lite" \
    --output result.json
```

### Method 3: CLI with ContextCore Project

```bash
# Dry run - see what tasks would execute
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --dry-run

# Execute all pending tasks
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --yes
```

### Method 4: YAML Task File

Create `tasks.yaml`:

```yaml
project:
  id: my-project
  sprint_id: sprint-3

tasks:
  - task_id: SDK-101
    title: Create base models
    story_points: 2
    config:
      task_description: |
        Create Pydantic models for User and Session.
        
        Requirements:
        1. User model with email, password_hash, created_at
        2. Session model with token, user_id, expires_at
        3. Add validation for email format
        
        Output: Python module with models
      context:
        language: Python
        framework: Pydantic v2

  - task_id: SDK-102
    title: Implement repository layer
    depends_on:
      - SDK-101
    config:
      task_description: |
        Create repository classes for User and Session models.
        ...
```

Run:

```bash
python scripts/run_contextcore_workflow.py \
    --tasks-file tasks.yaml \
    --project-id my-project
```

---

## Model Selection Guide

### When to Use Each Lead Agent

| Scenario | Recommended Lead | Why |
|----------|------------------|-----|
| **General coding tasks** | Claude Sonnet 4.5 | Best balance of capability and cost |
| **Complex architecture** | Claude Opus 4.5 | Superior reasoning for system design |
| **Simple refactoring** | Claude Haiku 4.5 | Fast, cost-effective for straightforward tasks |
| **Agentic workflows** | Claude Sonnet 4.5 | Optimized for tool use and multi-step tasks |

### When to Use Each Drafter Agent

| Scenario | Recommended Drafter | Why |
|----------|---------------------|-----|
| **Default choice** | Gemini 2.5 Flash Lite | Best value at $0.075/$0.30 per 1M |
| **Maximum speed** | GPT-4.1-nano | Fastest response times |
| **Experimental** | Gemini 3 Flash Preview | Latest capabilities |
| **Proven reliability** | GPT-4o-mini | Well-tested, consistent |

### Model Combinations

```python
# Cost-optimized (recommended default)
config = {
    "lead_agent": "anthropic:claude-sonnet-4-5-20250927",
    "drafter_agent": "gemini:gemini-2.5-flash-lite",
}

# Maximum quality
config = {
    "lead_agent": "anthropic:claude-opus-4-5-20251101",
    "drafter_agent": "gemini:gemini-2.5-flash",
}

# Maximum speed
config = {
    "lead_agent": "anthropic:claude-haiku-4-5-20251008",
    "drafter_agent": "openai:gpt-4.1-nano",
}

# Budget-conscious
config = {
    "lead_agent": "anthropic:claude-haiku-4-5-20251008",
    "drafter_agent": "gemini:gemini-2.5-flash-lite",
}
```

---

## Cost Optimization

### Strategies

1. **Use the Right Drafter**: Gemini 2.5 Flash Lite is 50% cheaper than GPT-4o-mini with comparable quality.

2. **Tune Iterations**: Start with `max_iterations=2` for simpler tasks.

3. **Write Better Prompts**: Clear specifications reduce revision cycles.

4. **Use Context Wisely**: Include only relevant context to reduce token usage.

5. **Batch Similar Tasks**: Group related tasks to reuse context.

### Cost Tracking

```python
from startd8.costs import CostTracker

tracker = CostTracker()

result = workflow.run(config={
    "task_description": "...",
    "cost_tracker": tracker,  # Inject tracker
})

# Get detailed breakdown
print(f"Lead cost: ${result.metadata['lead_cost']:.4f}")
print(f"Drafter cost: ${result.metadata['drafter_cost']:.4f}")
print(f"Efficiency ratio: {result.metadata['cost_efficiency_ratio']:.2f}")
```

### Budget Management

```python
from startd8.costs import BudgetManager

budget = BudgetManager(
    daily_limit=10.00,
    monthly_limit=100.00,
)

# Check before running
if budget.can_spend(estimated_cost=0.50):
    result = workflow.run(config=config)
    budget.record_spend(result.metrics.total_cost)
else:
    print("Budget exceeded!")
```

---

## ContextCore Integration

### Overview

ContextCore provides project observability by modeling tasks as OpenTelemetry spans. This enables:

- **Task hierarchy tracking** (Epic → Story → Task)
- **Sprint velocity metrics**
- **Blocker detection and duration tracking**
- **Grafana dashboard visualization**

### Using LeadContractorContextCoreWorkflow

```python
from startd8.workflows.builtin import LeadContractorContextCoreWorkflow

workflow = LeadContractorContextCoreWorkflow()

result = workflow.run(config={
    "task_description": "Implement rate limiter",
    
    # ContextCore tracking
    "task_id": "SDK-101",
    "project_id": "my-project",
    "parent_id": "EPIC-001",
    "sprint_id": "sprint-3",
    
    # Workflow config
    "drafter_agent": "gemini:gemini-2.5-flash-lite",
})
```

### Creating ContextCore Tasks

```bash
# Create task via CLI
contextcore task start \
    --id SDK-101 \
    --title "Implement rate limiter" \
    --project my-project \
    --type task \
    --status todo \
    --priority high \
    --points 3

# Add detailed prompt by editing the JSON file
# ~/.contextcore/state/my-project/SDK-101.json
```

### Task JSON Structure

```json
{
  "task_id": "SDK-101",
  "attributes": {
    "task.id": "SDK-101",
    "task.title": "Implement rate limiter",
    "task.type": "task",
    "task.status": "todo",
    "task.priority": "high",
    "task.story_points": 3,
    
    "task.prompt": "Implement rate limiter using token bucket...",
    "task.language": "Python",
    "task.framework": "asyncio",
    "task.file": "src/ratelimit.py",
    
    "task.depends_on": ["SDK-100"]
  }
}
```

### Running from ContextCore Project

```bash
# Preview tasks
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --dry-run

# Execute with sprint tracking
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --sprint-id sprint-3 \
    --yes
```

---

## Best Practices

### 1. Task Decomposition

Break large tasks into smaller, focused units:

```
❌ "Implement user authentication system"

✅ 
├── AUTH-001: Create User model
├── AUTH-002: Implement password hashing
├── AUTH-003: Create registration endpoint
├── AUTH-004: Create login endpoint
├── AUTH-005: Implement JWT tokens
└── AUTH-006: Add session management
```

### 2. Dependency Management

Use `depends_on` to ensure correct execution order:

```yaml
tasks:
  - task_id: AUTH-001
    title: Create User model
    # No dependencies - runs first
    
  - task_id: AUTH-002
    title: Implement password hashing
    depends_on: [AUTH-001]  # Needs User model
    
  - task_id: AUTH-003
    title: Create registration endpoint
    depends_on: [AUTH-001, AUTH-002]  # Needs both
```

### 3. Context Reuse

For related tasks, share context:

```python
shared_context = {
    "language": "Python",
    "framework": "FastAPI",
    "database": "PostgreSQL",
    "orm": "SQLAlchemy 2.0",
}

for task in tasks:
    task.config["context"] = {**shared_context, **task.specific_context}
```

### 4. Quality Thresholds

Adjust `pass_threshold` based on task criticality:

| Task Type | Threshold | Rationale |
|-----------|-----------|-----------|
| Security-critical | 90 | No room for error |
| Core business logic | 85 | High quality needed |
| Standard features | 80 | Default balance |
| Prototypes/POCs | 70 | Speed over perfection |

### 5. Review Dry Runs First

Always preview before executing:

```bash
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --dry-run
```

---

## API Reference

### LeadContractorWorkflow

```python
class LeadContractorWorkflow(WorkflowBase):
    """Cost-efficient multi-agent implementation workflow."""
    
    def run(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> WorkflowResult:
        """Execute the workflow."""
        
    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate configuration before execution."""
```

### WorkflowResult

```python
@dataclass
class WorkflowResult:
    workflow_id: str
    success: bool
    output: Dict[str, Any]  # Contains "final_implementation" and "summary"
    metrics: WorkflowMetrics
    steps: List[StepResult]
    error: Optional[str]
    started_at: datetime
    completed_at: datetime
    metadata: Dict[str, Any]
    project_context: Optional[ProjectContext]
```

### WorkflowMetrics

```python
@dataclass
class WorkflowMetrics:
    total_time_ms: int
    input_tokens: int
    output_tokens: int
    total_cost: float
    step_count: int
```

### StepResult

```python
@dataclass
class StepResult:
    step_name: str
    agent_name: str
    output: str
    time_ms: int
    input_tokens: int
    output_tokens: int
    cost: float
    metadata: Dict[str, Any]
```

---

## Troubleshooting

### Common Issues

#### "No API key found"

```bash
# Check environment variables
echo $ANTHROPIC_API_KEY
echo $GOOGLE_API_KEY
echo $OPENAI_API_KEY

# Set them
export ANTHROPIC_API_KEY="sk-ant-..."
```

#### "Model not found"

```python
# Verify model name spelling
# Use the exact model identifier
"anthropic:claude-sonnet-4-5-20250927"  # Correct
"anthropic:claude-sonnet-4.5"           # Wrong
```

#### "Review never passes"

```python
# Lower the threshold or increase iterations
config = {
    "pass_threshold": 70,    # Lower from default 80
    "max_iterations": 5,     # Increase from default 3
}
```

#### "Task skipped due to dependency"

```bash
# Check that dependent task succeeded
cat ~/.contextcore/state/my-project/SDK-101.json | jq '.attributes["task.status"]'

# Remove or fix the dependency
```

#### "ContextCore not installed"

```bash
pip install contextcore

# Or run without tracking
python scripts/run_contextcore_workflow.py \
    --task-id TASK-001 \
    --task-description "..." \
    --project-id my-project
    # (tracking will be disabled but workflow runs)
```

### Debug Mode

```bash
# Enable verbose logging
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --verbose

# Or in Python
from startd8.logging_config import setup_logging
setup_logging(level="DEBUG")
```

---

## Examples

### Example 1: Simple Code Generation

```python
from startd8.workflows.builtin import LeadContractorWorkflow

workflow = LeadContractorWorkflow()

result = workflow.run(config={
    "task_description": """
    Create a Python dataclass for a BlogPost with:
    - id: UUID
    - title: str (max 200 chars)
    - content: str
    - author_id: UUID
    - created_at: datetime
    - updated_at: Optional[datetime]
    - published: bool = False
    - tags: List[str] = []
    
    Include validation and a to_dict() method.
    """,
    "context": {"language": "Python", "framework": "dataclasses"}
})

print(result.output["final_implementation"])
```

### Example 2: API Endpoint Implementation

```python
result = workflow.run(config={
    "task_description": """
    Implement a FastAPI endpoint for user registration.
    
    Requirements:
    1. POST /api/v1/users/register
    2. Accept: email, password, name
    3. Validate email format and password strength
    4. Hash password using bcrypt
    5. Store in database via UserRepository
    6. Return created user (without password)
    7. Handle duplicate email error
    
    Acceptance Criteria:
    - Returns 201 on success
    - Returns 400 for validation errors
    - Returns 409 for duplicate email
    - Password never returned in response
    """,
    "context": {
        "framework": "FastAPI",
        "existing_models": ["User", "UserCreate", "UserResponse"],
        "repository": "UserRepository with create() method",
    }
})
```

### Example 3: Multi-Task Sprint

```yaml
# sprint-3-tasks.yaml
project:
  id: my-app
  sprint_id: sprint-3

tasks:
  - task_id: S3-001
    title: Add pagination to list endpoints
    story_points: 3
    config:
      task_description: |
        Add cursor-based pagination to all list endpoints.
        ...
        
  - task_id: S3-002
    title: Implement search functionality
    story_points: 5
    depends_on: [S3-001]
    config:
      task_description: |
        Add full-text search using PostgreSQL.
        ...
        
  - task_id: S3-003
    title: Add rate limiting
    story_points: 3
    config:
      task_description: |
        Implement API rate limiting.
        ...
```

```bash
python scripts/run_contextcore_workflow.py \
    --tasks-file sprint-3-tasks.yaml \
    --project-id my-app \
    --sprint-id sprint-3 \
    --output sprint-3-results.json
```

### Example 4: With ContextCore Observability

```python
from startd8.workflows.builtin import LeadContractorContextCoreWorkflow

workflow = LeadContractorContextCoreWorkflow()

result = workflow.run(config={
    "task_description": "Implement user authentication",
    
    # ContextCore integration
    "task_id": "AUTH-001",
    "project_id": "my-app",
    "parent_id": "EPIC-AUTH",
    "sprint_id": "sprint-3",
    
    # Emit insights for observability
    "emit_insights": True,
    
    # Workflow config
    "lead_agent": "anthropic:claude-sonnet-4-5-20250927",
    "drafter_agent": "gemini:gemini-2.5-flash-lite",
    "max_iterations": 3,
})

# Task is now tracked in ContextCore
# View in Grafana: http://localhost:3000
# Dashboard: "ContextCore: Project Progress"
```

---

## Summary

The Prime Contractor workflow in Beaver (StartD8 SDK) provides:

1. **Cost Efficiency**: 30%+ savings by using cheaper models for drafting
2. **Quality Assurance**: Claude reviews all output before acceptance
3. **Project Tracking**: ContextCore integration for observability
4. **Flexibility**: Configurable agents, thresholds, and iterations
5. **Automation**: Batch execution with dependency management

**Default Configuration:**
- Lead: `anthropic:claude-sonnet-4-5-20250927` ($3/$15 per 1M tokens)
- Drafter: `gemini:gemini-2.5-flash-lite` ($0.075/$0.30 per 1M tokens)
- Max Iterations: 3
- Pass Threshold: 80

**Quick Command:**
```bash
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --yes
```

---

*Document generated for StartD8 SDK v0.4.0 - January 2026*
