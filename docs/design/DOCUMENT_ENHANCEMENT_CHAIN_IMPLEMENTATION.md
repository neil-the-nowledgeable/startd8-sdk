# Document Enhancement Chain - Implementation Plan (Context Injection Strategy)

## Overview
This plan implements the **Document Enhancement Chain** using the **Context Injection Strategy (Option 1)**. 
The framework acts as a bridge: it reads local files, injects their content into prompts, sends them to AI agents, and writes the enhanced output back to the disk. This solves the limitation of cloud agents not having direct file access.

## Implementation Phases

### Phase 1: Core Data Models & Infrastructure (Week 1)

#### Task 1.1: Create Data Models
**File:** `src/startd8/document_enhancement.py` (or `models.py`)

Define structures to hold the document content and chain state.

```python
@dataclass
class DocumentEnhancementConfig:
    source_document: Path       # Path to local file to read
    enhancement_instructions: Optional[str]
    agents: List[AgentConfig]
    save_intermediate: bool     # Save output after each step?

@dataclass
class EnhancementStepResult:
    input_document: str         # The full text content injected into the agent
    output_document: str        # The full text content received from the agent
    # ... metrics (tokens, time, etc.)
```

#### Task 1.2: Implement File I/O (The "Bridge")
**File:** `src/startd8/document_enhancement.py`

Implement the robust file reading/writing that enables Context Injection.

- `_load_document(path)`: Reads local file with encoding detection.
- `_save_document(path, content)`: Writes enhanced content safely.
- `_extract_document_from_response(response)`: Parses the agent's text response to extract just the document content (handling markdown blocks, etc.).

#### Task 1.3: Prompt Builder (The "Injector")
**File:** `src/startd8/document_enhancement.py`

Create the mechanism that wraps the file content into a prompt the agent understands.

- **Template:**
  ```text
  You are an expert...
  
  # INSTRUCTIONS
  {user_instructions}
  
  # DOCUMENT TO ENHANCE
  {file_content}  <-- content injected here
  
  # TASK
  Return the full enhanced document...
  ```
- Logic to handle large files (warn if nearing token limits).

### Phase 2: Core Execution Logic (Week 1-2)

#### Task 2.1: Sequential Chain Orchestrator
**File:** `src/startd8/document_enhancement.py`

Implement the `DocumentEnhancementChain.run()` method that passes the "baton" (document content) from one agent to the next.

**Flow:**
1. **Read:** Load `source_document` from disk into memory string `current_content`.
2. **Loop:** For each agent in the chain:
   - **Inject:** Create prompt using `current_content` + `instructions`.
   - **Send:** Call `agent.generate(prompt)`.
   - **Receive:** Get response text.
   - **Extract:** Parse `new_content` from response.
   - **Update:** Set `current_content = new_content` for the next agent.
   - **Save (Optional):** Write `current_content` to an intermediate file.
3. **Finalize:** Return the final `current_content`.

#### Task 2.2: Error Handling & Recovery
Ensure the chain doesn't break the user's data if an agent fails.

- **Validation:** Check file existence and permissions before starting.
- **Graceful Failure:** If Agent 2 fails, save Agent 1's output so work isn't lost.
- **Output Parsing:** Handle cases where an agent adds "Here is the code:" chatter (clean it before passing to next agent).

### Phase 3: UI Integration (Week 2)

#### Task 3.1: Integration with TUI
**File:** `src/startd8/tui_improved.py`

Connect the logic to the visual interface (already partially scaffolded).

- **File Selector:** Uses `questionary.path` to pick the local file.
- **Agent Selector:** Allows picking specific agents (e.g., GPT-4 -> Composer).
- **Progress Bar:** Visual indication of "Reading...", "Agent Processing...", "Writing...".

### Phase 4: Testing & Validation (Week 2-3)

#### Task 4.1: Unit Tests
- Test prompt injection with various file sizes.
- Test document extraction regex (robustness against chatty agents).

#### Task 4.2: Integration Tests
- Run a real file through a MockAgent chain (verify data flow).
- Run a real file through a GPT-4 -> Claude chain (verify API connectivity).

## Risk Mitigation (Specific to Context Injection)

1. **Token Limits:**
   - *Risk:* File is too large for the model's context window.
   - *Mitigation:* Calculate token count of file *before* sending. If > limit, warn user or abort.

2. **Hallucination/Truncation:**
   - *Risk:* Agent returns a summarized or truncated version instead of the full document.
   - *Mitigation:* Strict system prompts ("Return the FULL document", "Do not summarize"). Validate output length roughly matches input length.

3. **Formatting Loss:**
   - *Risk:* Agent strips markdown formatting.
   - *Mitigation:* Prompt instructions to "preserve all formatting".

## Next Steps
1. Create `src/startd8/document_enhancement.py`.
2. Implement the `DocumentEnhancementConfig` and `DocumentEnhancementChain` classes.
3. Implement the `_load_document` and `_build_prompt` methods.
