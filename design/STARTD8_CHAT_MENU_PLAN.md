# Design Plan: Startd8 Chat Menu Item

## Status
**Proposed**

## Objective
Enable a "Chat with Agent" menu item in the Startd8 TUI (Terminal User Interface). This feature will allow users to interactively ask questions to Large Language Models (LLMs) that have a "Ready" status (configured and working).

## Background
Currently, the Startd8 TUI focuses on task-based workflows (Prompt Creation, Distribution, Benchmarking). Users may want to quickly test an agent or ask ad-hoc questions without creating a formal prompt template or running a full benchmark.

## User Interface Changes

### 1. Main Menu Update
Modify the `main_menu` method in `src/startd8/tui_improved.py` to include a new option.
- **Location**: Under the `═══ WORKFLOW ═══` or `═══ AGENTS ═══` section.
- **Label**: `💬 Chat with Agent`

### 2. Chat Selection Interface
When selected, the system will:
1.  **Scan for Ready Agents**: Check the status of all available agents.
    -   Use `AgentConfigTester.test_all()` or reuse cached `self.agent_status`.
    -   Filter for agents where `working` is `True`.
2.  **Display Selection**: Present a list of ready agents to the user.
    -   Format: `{Agent Name} ({Model})`
    -   If no agents are ready, display a warning and return to the main menu.

### 3. Chat Session Interface
Once an agent is selected, enter a chat loop:
-   **Header**: Display `Chatting with {Agent Name}`.
-   **Input**: `You > ` (Prompt for user input).
-   **Output**:
    -   `{Agent} > ` (Stream or print response).
    -   Render markdown response using Rich.
-   **Footer/Help**: `(Type 'exit', 'quit', or 'back' to return to menu)`

## Implementation Plan

### Phase 1: Agent Identification
Implement a helper method `_get_ready_agents(self)` in `ImprovedTUI`.
-   **Logic**:
    ```python
    ready_agents = []
    statuses = AgentConfigTester.test_all() # Or use self.agent_status
    for agent_id, status in statuses.items():
        if status.get('working'):
            ready_agents.append(agent_id)
    return ready_agents
    ```

### Phase 2: Chat Logic
Implement `chat_with_agent(self)` method in `ImprovedTUI`.
1.  **Get Ready Agents**: Call `_get_ready_agents`.
2.  **Selection**: Use `questionary.select` to pick an agent.
3.  **Initialization**: Instantiate the selected agent.
    -   *Note*: Need to map the agent ID (e.g., 'claude') back to the class instantiation logic used elsewhere (like in `run_benchmark` or `manage_agents`).
4.  **Loop**:
    ```python
    while True:
        user_input = questionary.text("You > ").ask()
        if user_input.lower() in ['exit', 'quit', 'back']:
            break
        
        with console.status("Thinking..."):
            response, _, _ = agent.generate(user_input)
        
        console.print(Panel(Markdown(response), title=agent.name))
    ```

### Phase 3: Integration
1.  Add choice to `main_menu` in `src/startd8/tui_improved.py`.
2.  Add handler in `run` loop.

## Technical Considerations
-   **Agent Instantiation**: Ensure we can instantiate the agent easily. `cli.py` has logic for this inside `run_benchmark`. We might want to centralize "get agent instance by name" logic if it isn't already.
-   **History**: This initial plan is for *single-turn* or *stateless* chat (as `BaseAgent.generate` typically takes a string prompt).
    -   *Future Enhancement*: Maintain conversation history context if the underlying agent supports it. For now, we will treat each input as a standalone prompt, or manually append history to the prompt string if simple context is desired.
-   **Mock Agent**: Ensure `MockAgent` is always available for testing the UI flow.

## Next Steps
1.  Review this plan.
2.  Implement `_get_ready_agents` and `chat_with_agent` methods.
3.  Update `main_menu` and `run` loop.
4.  Test with Mock agent and one real agent.
