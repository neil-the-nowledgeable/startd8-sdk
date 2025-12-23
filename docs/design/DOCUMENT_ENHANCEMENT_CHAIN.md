# Document Enhancement Chain - High-Level Plan & Design

## Overview

A feature that allows users to select a single existing design document and chain multiple AI agents to review and enhance it sequentially. Each agent receives the output from the previous agent, creating a refinement pipeline.

## Use Cases

### Primary Use Case
1. User selects an existing design document
2. User selects multiple agents (e.g., GPT-4, then Composer)
3. User optionally provides enhancement instructions
4. System chains agents serially:
   - Agent 1 receives original document + instructions → produces enhanced version
   - Agent 2 receives Agent 1's output + instructions → produces further enhanced version
   - Process continues for all selected agents
5. Final output is saved and displayed

### Example Flow
```
Original Document (FEATURE_01_HIGH_SCORE_STORAGE.md)
    ↓
[User Instructions: "Add accessibility section and improve CSS animations"]
    ↓
GPT-4 Agent → Enhanced Document v1
    ↓
Composer Agent → Enhanced Document v2 (Final)
```

## High-Level Architecture

### Components

1. **Document Enhancement Chain Orchestrator**
   - Manages the sequential execution of agents
   - Handles document state between steps
   - Tracks progress and errors

2. **Agent Selection & Configuration UI**
   - Document file picker
   - Multi-select agent chooser with ordering
   - Optional instruction input

3. **Document Enhancement Pipeline**
   - Wraps existing Pipeline class
   - Specialized for document enhancement workflow
   - Handles document-specific prompt construction

4. **Progress Tracking & Results Display**
   - Real-time progress updates
   - Step-by-step results view
   - Final output preview and save

## Detailed Design

### 1. Data Models

```python
@dataclass
class DocumentEnhancementConfig:
    """Configuration for document enhancement chain"""
    source_document: Path
    enhancement_instructions: Optional[str] = None
    agents: List[AgentConfig] = field(default_factory=list)
    output_path: Optional[Path] = None
    save_intermediate: bool = False  # Save each agent's output

@dataclass
class AgentConfig:
    """Configuration for a single agent in the chain"""
    agent_name: str  # e.g., "openai:gpt-4-turbo-preview"
    agent_instance: BaseAgent
    step_name: str  # e.g., "openai:gpt-4-turbo-preview-enhancement"
    order: int  # Position in chain (0-based)

@dataclass
class EnhancementStepResult:
    """Result from a single enhancement step"""
    step_number: int
    agent_name: str
    model: str
    input_document: str  # Document content before enhancement
    output_document: str  # Document content after enhancement
    response_time_ms: int
    token_usage: TokenUsage
    success: bool
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class DocumentEnhancementResult:
    """Complete result from enhancement chain"""
    config: DocumentEnhancementConfig
    steps: List[EnhancementStepResult]
    final_document: str
    total_time_ms: int
    total_tokens: int
    total_cost: float
    success: bool
    output_path: Optional[Path] = None
```

### 2. Core Orchestrator Class

```python
class DocumentEnhancementChain:
    """
    Orchestrates sequential document enhancement using multiple agents.
    
    Each agent receives:
    1. The document from the previous step (or original if first)
    2. User's enhancement instructions (if provided)
    3. Context about the enhancement task
    """
    
    def __init__(
        self,
        config: DocumentEnhancementConfig,
        framework: Optional[AgentFramework] = None
    ):
        self.config = config
        self.framework = framework
        self.results: List[EnhancementStepResult] = []
    
    def build_prompt(
        self,
        document_content: str,
        instructions: Optional[str] = None,
        step_context: Optional[str] = None
    ) -> str:
        """
        Build enhancement prompt for an agent.
        
        Template:
        - Document content
        - User instructions (if provided)
        - Step context (e.g., "This is the second enhancement pass")
        - Task description
        """
        pass
    
    def run(
        self,
        on_step_start: Optional[Callable] = None,
        on_step_complete: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ) -> DocumentEnhancementResult:
        """
        Execute the enhancement chain.
        
        Flow:
        1. Load source document
        2. For each agent in order:
           a. Build prompt with current document + instructions
           b. Call agent.generate()
           c. Extract enhanced document from response
           d. Store step result
           e. Use enhanced document as input for next step
        3. Return final result
        """
        pass
    
    def _extract_document_from_response(
        self,
        response: str,
        original_document: str
    ) -> str:
        """
        Extract the enhanced document from agent response.
        
        Strategies:
        1. If response is markdown, assume it's the full document
        2. Look for markdown code blocks
        3. If response contains "```markdown" or "```md", extract content
        4. Fallback: Use entire response as document
        """
        pass
```

### 3. UI Flow Design

#### 3.1 Main Entry Point
**Location:** `document_updater_menu()` in `tui_improved.py`

**New Menu Option:**
```
"🔗 Document Enhancement Chain (Multi-Agent)"
```

#### 3.2 User Flow

```
Step 1: Select Document
├─ File picker (markdown files)
├─ Preview document (optional)
└─ Confirm selection

Step 2: Configure Enhancement Instructions (Optional)
├─ Multi-line text input
├─ Examples/templates (optional)
└─ Skip if no instructions needed

Step 3: Select Agents & Order
├─ Display available agents:
│  ├─ GPT-4 (OpenAI)
│  ├─ Claude (Anthropic)
│  ├─ Composer (Custom)
│  └─ Other configured agents
├─ Multi-select with ordering:
│  ├─ Select agents (checkboxes)
│  ├─ Reorder selected agents (up/down arrows)
│  └─ Remove agents
└─ Preview chain: Agent1 → Agent2 → Agent3

Step 4: Configure Output
├─ Output directory selection
├─ Filename pattern (e.g., "{original}_enhanced.md")
├─ Save intermediate results? (yes/no)
└─ Confirm

Step 5: Execute Chain
├─ Show progress for each step
├─ Display agent name, model, status
├─ Show token usage and cost per step
└─ Real-time updates

Step 6: Review Results
├─ Show final enhanced document
├─ Compare original vs final (optional)
├─ Show step-by-step changes (optional)
├─ Save options
└─ Return to menu
```

### 4. Prompt Engineering

#### Base Prompt Template

```python
ENHANCEMENT_PROMPT_TEMPLATE = """
You are an expert technical writer and software architect. Your task is to review and enhance a design document.

# Original Document

{document_content}

# Enhancement Instructions

{instructions}

# Task

Please review the document above and provide an enhanced version that:
1. Incorporates the enhancement instructions provided
2. Maintains the document structure and formatting
3. Improves clarity, completeness, and technical accuracy
4. Preserves all important information from the original

# Output Format

Please provide the complete enhanced document in markdown format. Return ONLY the enhanced document content, without additional commentary or explanations outside the document itself.

If you need to include notes about changes, add them as comments within the document using HTML comments: <!-- Your note here -->
"""
```

#### Step Context Addition

For steps after the first:
```python
STEP_CONTEXT = """

# Context

This document has already been enhanced by {previous_agent_name}. Please review their enhancements and apply your own improvements based on the instructions above.
"""
```

### 5. Implementation Plan

#### Phase 1: Core Infrastructure
1. Create `DocumentEnhancementChain` class
2. Implement prompt building logic
3. Implement document extraction from responses
4. Add result data models
5. Unit tests for core logic

#### Phase 2: UI Integration
1. Add menu option to `document_updater_menu()`
2. Implement document selection UI
3. Implement agent selection & ordering UI
4. Implement instruction input UI
5. Implement progress display
6. Implement results review UI

#### Phase 3: Error Handling & Edge Cases
1. Handle agent failures gracefully
2. Handle malformed responses
3. Handle document extraction failures
4. Add retry logic (optional)
5. Add validation for document format

#### Phase 4: Advanced Features
1. Save intermediate results
2. Document comparison view
3. Step-by-step diff view
4. Cost estimation before execution
5. Template presets for common enhancement tasks

### 6. File Structure

```
src/startd8/
├── document_enhancement.py       # New: Core enhancement chain logic
├── tui_improved.py               # Modified: Add UI flow
└── models.py                     # Modified: Add enhancement data models

docs/
└── design/
    └── DOCUMENT_ENHANCEMENT_CHAIN.md  # This document
```

### 7. Integration Points

#### 7.1 With Existing Pipeline Class
- Reuse `Pipeline` class for sequential execution
- Extend with document-specific transformations
- Leverage existing metrics tracking

#### 7.2 With Agent Framework
- Use `AgentFramework` for storing results
- Track enhancement runs as prompts/responses
- Enable comparison with previous enhancements

#### 7.3 With Document Updater
- Share document loading utilities
- Reuse document detection logic
- Consistent output directory structure

### 8. Error Handling Strategy

```python
class EnhancementError(Exception):
    """Base exception for enhancement errors"""
    pass

class AgentFailureError(EnhancementError):
    """Agent call failed"""
    pass

class DocumentExtractionError(EnhancementError):
    """Could not extract document from agent response"""
    pass

class InvalidDocumentError(EnhancementError):
    """Source document is invalid or unreadable"""
    pass
```

**Error Recovery:**
- If an agent fails, stop the chain and return partial results
- Allow user to resume from failed step
- Save intermediate results even on failure
- Provide clear error messages with context

### 9. Performance Considerations

1. **Token Usage**
   - Document content can be large
   - Consider token limits per agent
   - Track cumulative token usage
   - Warn if approaching limits

2. **Response Time**
   - Each step is sequential (by design)
   - Show estimated time based on document size
   - Allow cancellation mid-chain

3. **Cost Estimation**
   - Calculate estimated cost before execution
   - Show cost per step
   - Track actual vs estimated

### 10. Testing Strategy

#### Unit Tests
- Prompt building logic
- Document extraction logic
- Error handling
- Data model validation

#### Integration Tests
- Full chain execution with mock agents
- Error scenarios
- Edge cases (empty document, no instructions, etc.)

#### Manual Testing
- Real agent chains (GPT-4 → Composer)
- Various document sizes
- Different instruction types
- UI flow validation

### 11. Future Enhancements

1. **Parallel Processing** (if needed)
   - Run independent enhancement passes in parallel
   - Merge results intelligently

2. **Agent-Specific Instructions**
   - Different instructions per agent
   - Agent-specific prompt templates

3. **Document Sections**
   - Enhance specific sections only
   - Section-level granularity

4. **Version Control Integration**
   - Track enhancement history
   - Compare versions
   - Rollback capabilities

5. **Batch Processing**
   - Process multiple documents
   - Apply same enhancement chain to all

## Implementation Checklist

### Core Implementation
- [ ] Create `DocumentEnhancementChain` class
- [ ] Implement prompt building
- [ ] Implement document extraction
- [ ] Add data models
- [ ] Add error handling
- [ ] Unit tests

### UI Implementation
- [ ] Add menu option
- [ ] Document selection UI
- [ ] Agent selection & ordering UI
- [ ] Instruction input UI
- [ ] Progress display
- [ ] Results review UI
- [ ] Save functionality

### Integration
- [ ] Integrate with Pipeline class
- [ ] Integrate with AgentFramework
- [ ] Integrate with document updater utilities
- [ ] Add to TUI menu

### Documentation
- [ ] User guide
- [ ] API documentation
- [ ] Example use cases
- [ ] Troubleshooting guide

## Example Usage

```python
from startd8 import AgentFramework
from startd8.document_enhancement import DocumentEnhancementChain
from startd8.models import DocumentEnhancementConfig, AgentConfig
from startd8.providers import ProviderRegistry
from pathlib import Path

# Optional: framework for saving prompts/responses
framework = AgentFramework()

# Configure agents (provider:model)
ProviderRegistry.discover()
openai = ProviderRegistry.get_provider("openai")
anthropic = ProviderRegistry.get_provider("anthropic")
if not openai or not anthropic:
    raise RuntimeError("Required providers not available")
openai.validate_config({})
anthropic.validate_config({})

# Configure
config = DocumentEnhancementConfig(
    source_document=Path("FEATURE_01_HIGH_SCORE_STORAGE.md"),
    enhancement_instructions="Add accessibility section and improve CSS animations",
    agents=[
        AgentConfig(
            agent_name="openai:gpt-4-turbo-preview",
            agent_instance=openai.create_agent("gpt-4-turbo-preview"),
            step_name="openai:gpt-4-turbo-preview-enhancement",
            order=0
        ),
        AgentConfig(
            agent_name="anthropic:claude-3-5-sonnet-20241022",
            agent_instance=anthropic.create_agent("claude-3-5-sonnet-20241022"),
            step_name="anthropic:claude-3-5-sonnet-20241022-refinement",
            order=1
        )
    ],
    output_path=Path("enhanced/FEATURE_01_ENHANCED.md"),
    save_intermediate=True
)

# Execute
chain = DocumentEnhancementChain(config, framework)
result = chain.run(
    on_step_start=lambda step_num, total, agent_name: print(f"Starting {agent_name} ({step_num}/{total})..."),
    on_step_complete=lambda step_num, total, agent_name, step_result: print(f"Completed {agent_name}"),
    on_progress=lambda current, total: print(f"Progress: {current}/{total}")
)

# Review
print(f"Success: {result.success}")
print(f"Total cost: ${result.total_cost:.4f}")
print(f"Final document saved to: {result.output_path}")
```

## Success Criteria

1. ✅ User can select a document and chain multiple agents
2. ✅ Each agent receives previous agent's output
3. ✅ User can provide optional enhancement instructions
4. ✅ Progress is displayed in real-time
5. ✅ Final output is saved and accessible
6. ✅ Errors are handled gracefully
7. ✅ Cost and token usage are tracked
8. ✅ UI is intuitive and follows existing patterns
