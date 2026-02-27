# Tool-Using Phase Handler: Agent Loop for Targeted Exploration

## Status: Not Built

## Problem

startd8-sdk's `AbstractPhaseHandler` is designed for single-shot LLM calls: receive context, call LLM, return output. It has no support for **iterative tool use** — calling the LLM, parsing tool_use blocks, executing tools, feeding results back, and looping until the task is complete.

The EXPLORE phase of the hybrid scaffold requires this pattern: the LLM needs to read specific files, search for patterns, and run tests — guided by the deterministic maps from Eagle and ContextCore, but with the freedom to dig deeper where needed.

## Goal

A new abstract base class `ToolUsingPhaseHandler` that extends `AbstractPhaseHandler` with:
1. A tool registry (define tools the LLM can call)
2. An agent loop (LLM → tool_use → execute → feedback → LLM)
3. Bounded iteration (max turns, token budget)
4. Full cost tracking (compatible with startd8-sdk's budget enforcement)
5. OTel instrumentation per tool call

## Interface Design

### AbstractPhaseHandler (existing — unchanged)

```python
class AbstractPhaseHandler(ABC):
    supports_feature_serial: bool = False

    @abstractmethod
    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Returns {"output": Any, "cost": float, "metadata": dict}"""

    def on_retry(self, phase, attempt, error) -> None: ...
```

### ToolUsingPhaseHandler (new — extends AbstractPhaseHandler)

```python
class ToolUsingPhaseHandler(AbstractPhaseHandler):
    """Base class for phase handlers that use LLM tool_use in an agent loop."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 15,
        token_budget: int = 50_000,
        tool_timeout_seconds: float = 30.0,
    ):
        self.model = model
        self.max_iterations = max_iterations
        self.token_budget = token_budget
        self.tool_timeout_seconds = tool_timeout_seconds
        self.supports_feature_serial = False

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """Define tools available to the LLM.

        Returns Anthropic tool_use format:
        [
            {
                "name": "read_file",
                "description": "Read file contents",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            },
        ]
        """
        ...

    @abstractmethod
    def handle_tool_use(
        self, tool_name: str, tool_input: dict
    ) -> str:
        """Execute a tool call and return the result as a string.

        Implementations should handle:
        - read_file: return file contents
        - search_codebase: return matching lines
        - list_directory: return directory listing
        - run_command: return stdout/stderr

        Raise ToolExecutionError for failures.
        """
        ...

    @abstractmethod
    def get_system_prompt(self, context: dict[str, Any]) -> str:
        """Build the system prompt for the agent loop.

        Should include:
        - Task description (e.g., "Localize the bug described in this issue")
        - Available context summaries (Eagle structure, capability map)
        - Code manifest structural context (element summaries, call graph) when available
        - Output format instructions
        """
        ...

    @abstractmethod
    def parse_final_output(
        self, messages: list[dict], context: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract structured output from the conversation history.

        Called after the agent loop completes.
        Returns data to be stored in context for downstream phases.
        """
        ...

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run the agent loop. Do not override — override the abstract methods instead."""

        if dry_run:
            return {"output": None, "cost": 0.0, "metadata": {"dry_run": True}}

        tools = self.get_tools()
        system_prompt = self.get_system_prompt(context)
        messages = [{"role": "user", "content": self._build_initial_message(context)}]

        total_input_tokens = 0
        total_output_tokens = 0
        tool_calls_made = 0
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1

            # Call LLM with tools
            response = self._call_llm(system_prompt, messages, tools)
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Check token budget
            if (total_input_tokens + total_output_tokens) > self.token_budget:
                break

            # Check stop reason
            if response.stop_reason == "end_turn":
                # LLM is done — extract final answer
                messages.append({"role": "assistant", "content": response.content})
                break

            if response.stop_reason == "tool_use":
                # Process tool calls
                assistant_content = response.content
                tool_results = []

                for block in assistant_content:
                    if block.type == "tool_use":
                        tool_calls_made += 1
                        result = self._execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_results})

        # Extract structured output
        output = self.parse_final_output(messages, context)

        cost = self._calculate_cost(total_input_tokens, total_output_tokens)

        return {
            "output": output,
            "cost": cost,
            "metadata": {
                "iterations": iteration,
                "tool_calls": tool_calls_made,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "model": self.model,
            },
        }
```

## Concrete Implementation: ExplorePhaseHandler

```python
class ExplorePhaseHandler(ToolUsingPhaseHandler):
    """SWE-Agent-style exploration bounded by Eagle + ContextCore maps."""

    def __init__(self, project_root: Path, manifest_registry=None, **kwargs):
        super().__init__(**kwargs)
        self.project_root = project_root
        self.manifest_registry = manifest_registry  # ManifestRegistry | None

    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "read_file",
                "description": "Read a file's contents. Use start_line/end_line for large files.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to file"},
                        "start_line": {"type": "integer", "description": "First line (1-indexed)"},
                        "end_line": {"type": "integer", "description": "Last line (inclusive)"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "search_codebase",
                "description": "Search for a regex pattern across files. Returns matching lines with file paths and line numbers.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex pattern"},
                        "file_glob": {"type": "string", "description": "Glob filter, e.g. '*.py'"},
                        "max_results": {"type": "integer", "description": "Max matches to return"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "list_directory",
                "description": "List files and subdirectories at a path.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path"},
                        "recursive": {"type": "boolean", "description": "Include subdirectories"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "run_test",
                "description": "Run a test command and return stdout/stderr. Use to reproduce a failing test.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Test command, e.g. 'python -m pytest tests/test_auth.py -v'"},
                        "timeout_seconds": {"type": "integer", "description": "Max seconds to wait"},
                    },
                    "required": ["command"],
                },
            },
        ] + (self._manifest_tools() if self.manifest_registry else [])

    def handle_tool_use(self, tool_name: str, tool_input: dict) -> str:
        """Execute tools against the local filesystem."""
        # Implementation routes to actual file I/O, subprocess, etc.
        # Each tool is sandboxed to project_root
        # query_code_structure routes to self.manifest_registry methods
        ...

    def _manifest_tools(self) -> list[dict]:
        """Conditional manifest-backed tools. Only registered when ManifestRegistry is available."""
        return [
            {
                "name": "query_code_structure",
                "description": "Query the pre-computed code manifest for structural information. "
                    "Use this BEFORE reading files — it instantly answers questions about "
                    "function signatures, callers, callees, and change impact without file I/O.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["element_summary", "lookup", "callers_of", "blast_radius"],
                            "description": "element_summary: list all elements in a file. "
                                "lookup: get details for a specific FQN. "
                                "callers_of: find direct callers of a function. "
                                "blast_radius: find all transitive callers (change impact).",
                        },
                        "target": {
                            "type": "string",
                            "description": "File path (for element_summary) or fully-qualified name (for lookup/callers_of/blast_radius). "
                                "Example FQN: 'startd8.auth._validate_token'",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "For blast_radius: max caller chain depth (default 3)",
                        },
                    },
                    "required": ["action", "target"],
                },
            },
        ]

    def get_system_prompt(self, context: dict[str, Any]) -> str:
        codebase_summary = context.get("codebase_summary", "No codebase summary available.")
        manifest_context = self._render_manifest_context(context)
        return f"""You are a code exploration agent. Your task is to localize a bug or
understand a codebase issue well enough to write a fix specification.

You have access to a pre-computed codebase map:

{codebase_summary}
{manifest_context}
Use the tools to read specific files, search for patterns, and run tests.
Focus your exploration — the codebase map already tells you what exists and where.
{self._manifest_tool_guidance()}
When you have enough information, respond with a structured localization report containing:
- fault_files: list of files that need changes
- target_fqns: (if manifest available) fully-qualified names of fault elements
- root_cause: description of the underlying problem
- relevant_code: key code snippets with file paths and line numbers
- affected_tests: tests that should pass after the fix
- fix_approach: high-level description of the fix strategy
- blast_radius: (if manifest available) dict of target FQN → transitive caller count
"""

    def _render_manifest_context(self, context: dict[str, Any]) -> str:
        """Render manifest structural context for the system prompt.

        Budget: 4000 chars max (manifest_context_budget). Progressive truncation:
        full element summaries → top-N by caller count → count-only.
        When ManifestRegistry is absent, returns empty string.
        """
        if not self.manifest_registry:
            return ""
        # Render element summaries + call graph summaries for issue-referenced files
        ...

    def _manifest_tool_guidance(self) -> str:
        """Additional system prompt guidance when manifest tools are available."""
        if not self.manifest_registry:
            return ""
        return (
            "\nYou also have the `query_code_structure` tool for instant structural queries. "
            "Use it to look up function signatures, find callers, and assess blast radius "
            "BEFORE reading full files — it's faster and more precise than grep.\n"
        )

    def parse_final_output(self, messages, context) -> dict:
        """Extract the localization report from the final assistant message."""
        # Parse the last assistant message for the structured report
        ...

    def _build_initial_message(self, context) -> str:
        issue = context.get("issue_description", "")
        return f"Localize the following issue:\n\n{issue}"
```

## Tool Safety

### Sandboxing

All tools are restricted to `project_root`:
- `read_file`: Path must be under `project_root`. Symlinks resolved and checked.
- `search_codebase`: Only searches within `project_root`.
- `list_directory`: Only lists within `project_root`.
- `run_test`: Runs in a subprocess with `cwd=project_root`, timeout enforced, no network access.
- `query_code_structure`: (conditional) Reads from in-memory `ManifestRegistry`. No file I/O, no subprocess calls. Pure data lookup — inherently safe.

### Resource Limits

- `max_iterations`: Caps agent loop turns (default 15)
- `token_budget`: Caps total token usage (default 50,000)
- `tool_timeout_seconds`: Per-tool execution timeout (default 30s)
- `run_test` has an additional hard timeout (default 60s)
- File reads are capped at 10,000 lines per call
- `manifest_context_budget`: Caps manifest context injected into system prompt (default 4,000 chars). Progressive truncation: full element summaries → top-N by caller count → count-only summary

### No Destructive Operations

The tool set is **read-only + test-only**:
- No file writes
- No file deletes
- No git operations
- No network calls (beyond what tests may internally do)
- `run_test` only runs commands matching a whitelist pattern (`pytest`, `unittest`, `npm test`, etc.)
- `query_code_structure` performs zero I/O — pure in-memory lookups against pre-computed manifest data

## OTel Instrumentation

Each agent loop iteration emits a span:

```
span: explore.iteration.{n}
  attributes:
    explore.iteration: int
    explore.tool_calls: int (this iteration)
    explore.cumulative_tokens: int
    explore.model: str
  events:
    - tool_call: {name, input_summary, duration_ms, result_length}
    - tool_call: ...
```

The overall phase emits:

```
span: phase.explore
  attributes:
    explore.total_iterations: int
    explore.total_tool_calls: int
    explore.total_tokens: int
    explore.cost_usd: float
    explore.fault_files: [str]
    explore.root_cause_summary: str (first 200 chars)
```

## Integration with Artisan Pipeline

### Phase Registration

```python
workflow = ArtisanContractorWorkflow(
    config=WorkflowConfig(cost_budget=5.0),
    phases=["explore"] + WorkflowPhase.ordered(),  # prepend explore
)

explore_handler = ExplorePhaseHandler(
    project_root=Path("/path/to/project"),
    model="claude-sonnet-4-20250514",
    max_iterations=15,
    token_budget=10_000,
)
workflow.register_handler("explore", explore_handler)
```

### Context Flow

```
EXPLORE output:
  context["localization"] = {
      "fault_files": ["src/auth.py", "src/auth_utils.py"],
      "root_cause": "Token expiry check skipped when refresh=True",
      "relevant_code": {
          "src/auth.py:73-85": "def _validate_token(token, refresh=False): ...",
          "src/auth_utils.py:120-130": "def _refresh_token(token): ...",
      },
      "affected_tests": ["tests/test_auth.py::test_token_expiry"],
      "fix_approach": "Add expiry check to both _validate_token and _refresh_token",

      # --- Manifest-enriched fields (present only when ManifestRegistry available) ---
      "target_fqns": [                          # FQN-precise localization
          "startd8.auth._validate_token",
          "startd8.auth_utils._refresh_token",
      ],
      "blast_radius": {                         # Transitive caller impact per target
          "startd8.auth._validate_token": 7,
          "startd8.auth_utils._refresh_token": 3,
      },
  }

DESIGN phase reads context["localization"] and generates a design document.
IMPLEMENT phase reads context["localization"] + context["design_results"].

Manifest-enriched fields are optional — downstream phases MUST tolerate their absence
(graceful degradation: absent = skip enrichment, no behavioral change).
```

## Relationship to Code Manifest

The EXPLORE phase may have both a Code Manifest (`ManifestRegistry` instance, from `context["project_manifests"]`) and Context Bridge output (`context["bridge_context"]`) available simultaneously. These are **complementary, not conflicting** data sources:

| Dimension | Code Manifest (ManifestRegistry) | Context Bridge (ContextBridgeResult) |
|-----------|--------------------------------|--------------------------------------|
| **Granularity** | Per-element: FQNs, signatures, spans, call graph | Per-file/per-service: capability inventory, service dependencies, LOC |
| **EXPLORE usage** | `query_code_structure` tool + system prompt structural context | `codebase_summary` in system prompt |
| **Output enrichment** | `target_fqns`, `blast_radius` in localization report | `fault_files`, `relevant_code` (file-level) |
| **Cost** | Zero (in-memory lookup of pre-computed static analysis) | Zero (deterministic transformation) |
| **Availability** | Requires `startd8 manifest generate` or cache from prior run | Requires Eagle + ContextCore installed |

**Design guidelines for ExplorePhaseHandler:**
- Prefer `ManifestRegistry` for element-level queries (signature lookup, FQN resolution, call graph traversal, blast radius)
- Prefer `bridge_context` for project-level queries (service topology, language mix, total LOC, codebase summary)
- When both provide overlapping data (e.g., function signatures), `ManifestRegistry` is authoritative (deeper analysis)
- Both follow the same **graceful degradation** pattern: absent = skip enrichment, no behavioral change to the phase. The `ExplorePhaseHandler` MUST function identically with 4 tools (no manifest) or 5 tools (with manifest) — the 5th tool is additive, never required

**Context key namespace:**
- `context["bridge_context"]` → Context Bridge output (project_structure, capability_map, codebase_summary)
- `context["project_manifests"]` → Code Manifest output (ManifestRegistry)
- `context["localization"]` → EXPLORE phase output (consumed by DESIGN, IMPLEMENT)

These keys are non-overlapping by design. No merge or precedence logic is needed at the context dict level.

---

## Estimated Effort

~2 days:
- 4 hours: Implement `ToolUsingPhaseHandler` base class with agent loop
- 4 hours: Implement the 4 tools (read_file, search_codebase, list_directory, run_test)
- 4 hours: Implement `ExplorePhaseHandler` (system prompt, output parsing, initial message)
- 4 hours: Sandboxing, safety, OTel instrumentation, unit tests

## Dependencies

- `anthropic` Python SDK (already a startd8-sdk dependency)
- `opentelemetry-api` (already a startd8-sdk dependency)
- No new external dependencies

## Open Questions

1. **Should run_test be available in the Explore phase?** It's useful for reproducing issues but adds risk (arbitrary command execution). Could restrict to a test-runner whitelist.
2. **Should the agent loop use streaming?** Streaming would give faster perceived response but complicates tool_use parsing. Recommend: no streaming for v1.
3. **Should there be a fallback for non-Python projects?** The ContextCore extract only works for Python. For other languages, the agent would rely on Eagle's macro map + raw file reading. This is still better than nothing.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Resolve the contradiction between the docstring ('raise ToolExecutionError') and the plan ('return error string, don't raise'). | claude-4 (claude-opus-4-6) | Contradictory instructions will lead to inconsistent subclass implementations. The resolution via R1-S4's ToolResult type is clean: expected failures return ToolResult(is_error=True), unexpected failures propagate as exceptions caught by the base class wrapper. | 2026-02-20 02:09:03 UTC |
| R1-F2 | Add _build_initial_message as an abstract method on ToolUsingPhaseHandler in the requirements doc. | claude-4 (claude-opus-4-6) | This is a duplicate of R1-S2/R2-S8 from the requirements perspective. The plan acknowledges the gap in Risk 6 but the requirements doc doesn't mandate the fix. Both the plan and requirements should be aligned. | 2026-02-20 02:09:03 UTC |
| R1-F3 | Specify the exact whitelist regex for _run_test instead of using informal descriptions with 'etc.'. | claude-4 (claude-opus-4-6) | 'etc.' is dangerous for a security boundary. Implementers must not guess which commands are allowed. The exact regex, plus rules on whether post-prefix arguments are validated, must be explicitly specified to prevent security holes or broken functionality. | 2026-02-20 02:09:03 UTC |
| R1-F4 | Standardize on WorkflowPhase enum (not strings) for phase registration in both the requirements doc and the plan. | claude-4 (claude-opus-4-6) | Inconsistency between string and enum types in examples will cause implementer confusion and potential key mismatches. Since WorkflowPhase is an enum, all examples should use the enum consistently. | 2026-02-20 02:09:03 UTC |
| R1-F6 | Reconcile the 50K vs 10K token_budget discrepancy and provide sizing guidance. | claude-4 (claude-opus-4-6) | A 5x discrepancy between the class default and the integration example will confuse users. Providing sizing guidance helps users pick appropriate values and prevents both premature termination and cost overruns. | 2026-02-20 02:09:03 UTC |
| R2-F1 | Clarify whether explore phase cost tracking integrates with the global workflow budget during execution (real-time enforcement vs. post-phase check). | gemini-3 (gemini-3-pro-preview) | If the explore phase can burn most of a $5 budget without the workflow being able to intervene, downstream phases will fail or be starved. The plan must specify whether budget checks happen per-iteration (allowing mid-phase termination) or only at phase boundaries. | 2026-02-20 02:09:03 UTC |
| R1-F1 | Resolve contradiction between raising ToolExecutionError and returning error strings for tool failures. | claude-4 (claude-opus-4-6) | The contradiction between the docstring and the plan will confuse implementers and lead to inconsistent error handling. The proposed resolution (ToolResult for expected failures, exceptions for bugs caught by wrapper) is clean and aligns with R1-S4. | 2026-02-20 02:15:20 UTC |
| R1-F2 | Make _build_initial_message an abstract method on ToolUsingPhaseHandler. | claude-4 (claude-opus-4-6) | Without this, subclasses can be instantiated and will fail at runtime with AttributeError. The plan's own Risk 6 acknowledges this gap but the requirements don't fix it. This is a straightforward interface correctness issue. | 2026-02-20 02:15:20 UTC |
| R1-F3 | Provide the exact whitelist regex for run_test instead of informal description with 'etc.' | claude-4 (claude-opus-4-6) | A security boundary defined with 'etc.' is unacceptable. Implementers need the exact regex. This is a security-critical specification gap. | 2026-02-20 02:15:20 UTC |
| R1-F4 | Standardize on WorkflowPhase enum (not strings) for phase registration. | claude-4 (claude-opus-4-6) | Inconsistency between string and enum types in examples will cause registration failures. Standardizing on the enum is the obvious fix and prevents type mismatches. | 2026-02-20 02:15:20 UTC |
| R1-F6 | Reconcile the 50K vs 10K token_budget discrepancy and provide sizing guidance. | claude-4 (claude-opus-4-6) | Contradictory defaults (50K in class, 10K in example) will confuse users. Sizing guidance helps users avoid premature termination or cost overruns. This is a basic documentation/consistency fix. | 2026-02-20 02:15:20 UTC |
| R2-F1 | Specify how phase-level cost tracking integrates with global workflow budget during execution. | gemini-3 (gemini-3-pro-preview) | If the explore phase can burn most of a global budget without real-time enforcement, operators lose budget control. The interaction between per-phase token_budget and global cost_budget must be explicitly defined. | 2026-02-20 02:15:20 UTC |
| R3-F1 | Wrap agent loop in try/except to preserve partial results and cost tracking on failure. | claude-4 (claude-opus-4-6) | Directly overlaps with R3-S7 but focuses specifically on the execute() method implementation. Losing cost visibility on failed runs makes budget tracking inaccurate. Re-raising as PhaseExecutionError with partial results is the right pattern. | 2026-02-20 02:15:20 UTC |
| R3-F2 | Explicitly specify sequential execution for multiple tool calls in v1. | claude-4 (claude-opus-4-6) | The plan acknowledges multiple tool calls per response but doesn't specify execution order. Making the explicit choice of sequential execution for v1 (with future concurrent_tools parameter) is a good architectural decision that reduces complexity and avoids resource contention. | 2026-02-20 02:15:20 UTC |
| R3-F3 | Change 'no network access' requirement to honest statement that network isolation is not enforced in v1. | claude-4 (claude-opus-4-6) | The requirement is unimplementable as specified without platform-specific sandboxing that's out of scope. Stating an unenforceable security boundary is worse than being honest about limitations. The proposed wording is pragmatic and accurate. | 2026-02-20 02:15:20 UTC |
| R3-F4 | Specify context flow for partial/empty EXPLORE results with confidence field for downstream decision-making. | claude-4 (claude-opus-4-6) | Without this, downstream phases can't distinguish 'found nothing' from 'failed.' The confidence field and partial flag enable graceful degradation in DESIGN phase rather than hard failures. | 2026-02-20 02:15:20 UTC |
| R4-F1 | Require whitelist regex to be strictly anchored and forbid shell metacharacters. | gemini-3 (gemini-3-pro-preview) | This is the requirements-level counterpart to R4-S1 (the implementation-level fix). Both are needed — the requirements must mandate the security constraint, and the implementation must enforce it. Overlaps with R4-S1 but addresses it at the specification layer. | 2026-02-20 02:15:20 UTC |
| R4-F2 | Add cost_budget parameter to the interface and require dynamic token limits based on model pricing. | gemini-3 (gemini-3-pro-preview) | This is the requirements-level fix for the token_budget vs cost_budget mismatch. Users think in dollars, not tokens. While I rejected R4-S2 (the specific implementation proposal), the requirement itself is valid — the interface should accept a cost budget. Implementation can be as simple as converting cost_budget to token_budget at init time using PricingService. | 2026-02-20 02:15:20 UTC |
| R1-F1 | Resolve contradiction between 'raise ToolExecutionError' and 'return error string' for tool failure handling. | claude-4 (claude-opus-4-6) | The contradiction between the docstring and plan Section 5 will cause inconsistent implementations. The proposed resolution (ToolResult for expected failures, exceptions for bugs) is clean and aligns with already-accepted R1-S4. | 2026-02-20 02:21:54 UTC |
| R1-F2 | Make _build_initial_message an abstract method on ToolUsingPhaseHandler. | claude-4 (claude-opus-4-6) | The method is called in execute() but not declared abstract, which will cause AttributeError at runtime for subclasses that forget it. The plan's Risk 6 acknowledges this gap but doesn't fix it. | 2026-02-20 02:21:54 UTC |
| R1-F3 | Specify the exact whitelist regex for run_test instead of informal 'etc.' description. | claude-4 (claude-opus-4-6) | A security boundary cannot be defined with 'etc.' — implementers need an exact regex. The plan's Section 5 actually has a concrete regex, but the requirements doc doesn't match it. Standardize on the exact pattern. | 2026-02-20 02:21:54 UTC |
| R1-F4 | Standardize phase registration on WorkflowPhase enum instead of mixing strings and enums. | claude-4 (claude-opus-4-6) | Type inconsistency between examples will cause registration failures. Since WorkflowPhase is an enum, all examples should use it consistently. | 2026-02-20 02:21:54 UTC |
| R1-F6 | Reconcile token_budget default (50K vs 10K) and provide sizing guidance. | claude-4 (claude-opus-4-6) | Contradictory defaults between the class definition and example will confuse users. Sizing guidance helps users pick appropriate values and avoids both premature termination and cost overruns. | 2026-02-20 02:21:54 UTC |
| R2-F1 | Clarify how per-phase cost tracking integrates with global workflow budget enforcement during execution. | gemini-3 (gemini-3-pro-preview) | If the explore phase can burn most of the global budget without mid-loop enforcement, downstream phases will fail. The interaction between per-phase token_budget and global cost_budget must be specified. | 2026-02-20 02:21:54 UTC |
| R3-F1 | Add try/except around the agent loop to preserve partial results and cost tracking on failure. | claude-4 (claude-opus-4-6) | An unhandled exception in the loop loses all cost visibility and partial results. This is critical for budget tracking accuracy and operational debugging. Aligns with R3-S7 which was already accepted. | 2026-02-20 02:21:54 UTC |
| R3-F2 | Explicitly specify sequential tool execution for v1 with a reserved concurrent_tools parameter. | claude-4 (claude-opus-4-6) | The requirements must make an explicit choice since the LLM can return multiple tool_use blocks. Sequential is the right v1 choice for simplicity and safety, and documenting it prevents implementer ambiguity. | 2026-02-20 02:21:54 UTC |
| R3-F3 | Change 'no network access' to an honest statement that v1 relies on command whitelist, with a recommendation for containerized isolation in production. | claude-4 (claude-opus-4-6) | The 'no network access' requirement is unimplementable with subprocess.run and shell=True without OS-level sandboxing. Making the security boundary honest prevents false confidence and is realistic for the 2-day estimate. | 2026-02-20 02:21:54 UTC |
| R3-F4 | Add confidence and partial fields to localization output so downstream phases can distinguish 'found nothing' from 'failed'. | claude-4 (claude-opus-4-6) | Without these fields, downstream phases cannot make informed fallback decisions. The confidence threshold approach for DESIGN phase fallback is practical and well-specified. | 2026-02-20 02:21:54 UTC |
| R4-F1 | Require whitelist regex to be strictly anchored and reject shell metacharacters. | gemini-3 (gemini-3-pro-preview) | An unanchored regex with shell=True is a command injection vulnerability. This is a critical security fix that directly addresses the gap in the current plan. | 2026-02-20 02:21:54 UTC |
| R5-F1 | Document signatures and contracts for private methods _call_llm, _execute_tool, _calculate_cost, and _build_initial_message. | claude-4 (claude-opus-4-6) | The base class implementer must know the contract of these 4 undocumented private methods. _call_llm in particular has critical behavioral requirements (retry logic per R5-S2, timeout, error handling) that affect correctness. | 2026-02-20 02:21:54 UTC |
| R5-F2 | Document Anthropic-only tool format as an intentional v1 design decision. | claude-4 (claude-opus-4-6) | Option (a) — documenting this as intentional — is the right v1 call. Adding a provider-neutral schema is over-engineering, but the coupling should be explicitly acknowledged so future multi-provider work knows where to intervene. | 2026-02-20 02:21:54 UTC |
| R5-F3 | Change read_file path schema to accept both absolute and relative paths, resolving relative against project_root. | claude-4 (claude-opus-4-6) | LLMs overwhelmingly produce relative paths. Requiring absolute paths will cause most tool calls to fail or require the system prompt to always include project_root. Resolving relative paths is more robust and matches user expectations. | 2026-02-20 02:21:54 UTC |
| R5-F5 | Add size constraint on relevant_code in ExplorePhaseOutput to prevent inflating downstream token budgets. | claude-4 (claude-opus-4-6) | Unbounded relevant_code can waste significant tokens in DESIGN and IMPLEMENT phases. A 10K char cap with truncation in parse_final_output is a practical safeguard. | 2026-02-20 02:21:54 UTC |
| R6-F1 | Explicitly list issue_description and codebase_summary as required context keys for ExplorePhaseHandler. | gemini-3 (gemini-3-pro-preview) | This complements R6-S5 but also adds codebase_summary (used in get_system_prompt). Both are implicit dependencies that should be explicit entry requirements to fail fast with clear errors. | 2026-02-20 02:21:54 UTC |
| R6-F2 | Add a requirement to handle context window exhaustion gracefully, terminating the loop and returning partial results. | gemini-3 (gemini-3-pro-preview) | This is the requirements-level counterpart to R5-S3 (architecture) and R6-S6 (implementation). The requirements doc must acknowledge that context window limits exist independently of token_budget and specify graceful degradation. | 2026-02-20 02:21:54 UTC |
| R1-F1 | Resolve contradiction between raising ToolExecutionError and returning error strings for tool failures. | claude-4 (claude-opus-4-6) | The docstring and plan give contradictory guidance on error handling. Since R1-S4 (ToolResult) was already accepted, this clarification is necessary to make the contract consistent: expected failures return ToolResult(is_error=True), unexpected failures propagate as exceptions caught by the base class. | 2026-02-20 02:52:27 UTC |
| R1-F2 | Make _build_initial_message an abstract method on ToolUsingPhaseHandler. | claude-4 (claude-opus-4-6) | The plan's own Risk 6 acknowledges this gap. Without it, subclasses can be instantiated without implementing this method, causing runtime AttributeError. This is a straightforward fix already identified in the plan. | 2026-02-20 02:52:27 UTC |
| R1-F3 | Provide the exact whitelist regex for run_test instead of informal examples with 'etc.' | claude-4 (claude-opus-4-6) | A security boundary must be precisely defined. 'etc.' is ambiguous and dangerous. The exact regex is needed for both implementers and security reviewers. R4-F1 (accepted) already requires anchoring, but the base regex itself must be specified. | 2026-02-20 02:52:27 UTC |
| R1-F4 | Standardize on WorkflowPhase enum values instead of mixing strings and enums for phase registration. | claude-4 (claude-opus-4-6) | Inconsistency between string and enum usage will cause key mismatches or registration failures. Simple fix: use the enum consistently throughout documentation and examples. | 2026-02-20 02:52:27 UTC |
| R1-F6 | Reconcile the 50K vs 10K token_budget discrepancy and provide sizing guidance. | claude-4 (claude-opus-4-6) | Having two different default values in the same document is a concrete bug. Sizing guidance helps users make informed choices and prevents cost overruns or premature termination. | 2026-02-20 02:52:27 UTC |
| R2-F1 | Clarify how phase-level cost tracking integrates with the global workflow budget during execution. | gemini-3 (gemini-3-pro-preview) | If the explore phase burns most of a global budget, the behavior must be defined — does it check per-iteration or only at phase boundaries? This is critical for cost control and was flagged but left ambiguous. | 2026-02-20 02:52:27 UTC |
| R3-F1 | Wrap the agent loop in try/except to ensure partial cost tracking and error reporting on failures. | claude-4 (claude-opus-4-6) | Losing cost visibility on failed runs is operationally unacceptable. The base class execute() method must guarantee cost reporting even on exceptions. This is a fundamental reliability requirement. | 2026-02-20 02:52:27 UTC |
| R3-F2 | Explicitly specify that v1 executes multiple tool calls sequentially, with concurrent_tools reserved for future use. | claude-4 (claude-opus-4-6) | The requirements must make an explicit choice since the plan acknowledges multiple tool calls per response. Sequential is the right v1 choice and documenting it prevents implementer ambiguity. The reserved parameter is lightweight. | 2026-02-20 02:52:27 UTC |
| R3-F3 | Change 'no network access' requirement to an honest statement about v1 limitations with container recommendation for production. | claude-4 (claude-opus-4-6) | Stating an unimplementable requirement is worse than documenting a known limitation. The requirement as written cannot be enforced without OS-level sandboxing which is out of scope. Honesty about the security boundary is critical. | 2026-02-20 02:52:27 UTC |
| R3-F4 | Require context['localization'] to always be written with confidence and partial fields so downstream phases can handle partial/empty results. | claude-4 (claude-opus-4-6) | Endorsed by 1 reviewer. Downstream phases need to distinguish 'EXPLORE found nothing' from 'EXPLORE failed.' The confidence threshold for fallback behavior is a practical mechanism for graceful degradation. | 2026-02-20 02:52:27 UTC |
| R4-F1 | Require the whitelist regex to be strictly anchored and prevent shell metacharacters. | gemini-3 (gemini-3-pro-preview) | Already accepted previously. Anchoring is essential to prevent prefix-matching bypasses like 'make test; rm -rf /'. This is a basic security requirement for the command whitelist. | 2026-02-20 02:52:27 UTC |
| R5-F1 | Document signatures and contracts for private methods _call_llm, _execute_tool, _calculate_cost, and _build_initial_message. | claude-4 (claude-opus-4-6) | The base class implementer needs clear specifications for these four methods that are called in execute() but never formally defined. Without this, the implementer must reverse-engineer intent from scattered references. | 2026-02-20 02:52:27 UTC |
| R5-F2 | Document that get_tools() returns Anthropic-specific format as an intentional v1 design decision. | claude-4 (claude-opus-4-6) | Option (a) — documenting it as intentional Anthropic-only — is the right v1 approach. This prevents future confusion without over-engineering a provider-neutral abstraction that isn't needed yet. | 2026-02-20 02:52:27 UTC |
| R5-F3 | Allow both absolute and relative paths in read_file, resolving relative paths against project_root. | claude-4 (claude-opus-4-6) | Endorsed by 1 reviewer. LLMs overwhelmingly produce relative paths. Requiring absolute paths would cause most tool calls to fail. Resolving relative paths is both practical and secure (validation still checks the resolved path is under project_root). | 2026-02-20 02:52:27 UTC |
| R5-F5 | Cap relevant_code total size to prevent oversized context flowing to downstream phases. | claude-4 (claude-opus-4-6) | Without a size limit, the LLM could copy hundreds of lines of code into relevant_code, inflating downstream phase token consumption. A 10K char cap is reasonable and prevents budget waste in DESIGN and IMPLEMENT phases. | 2026-02-20 02:52:27 UTC |
| R6-F1 | Explicitly list issue_description and codebase_summary as required context keys for EXPLORE phase. | gemini-3 (gemini-3-pro-preview) | These are clearly needed (for the initial message and system prompt) but not listed in entry requirements. Without them the agent runs without a goal. Adding them to entry requirements enables early validation and clear error messages. | 2026-02-20 02:52:27 UTC |
| R6-F2 | Add a requirement to handle context window exhaustion gracefully with partial results. | gemini-3 (gemini-3-pro-preview) | Endorsed by 1 reviewer. Token budget controls cost but doesn't prevent context window overflow. If the conversation exceeds the model's context window, the API returns a 400 error. The plan must address this as a distinct stop condition. | 2026-02-20 02:52:27 UTC |
| R7-F1 | Enforce non-overridability of execute() via __init_subclass__ check. | claude-4 (claude-opus-4-6) | The execute() method contains critical invariants (cost tracking, OTel, budget enforcement). Python can't prevent overriding, but a __init_subclass__ check that raises TypeError is a simple, well-established pattern that enforces the 'do not override' contract at class definition time. | 2026-02-20 02:52:27 UTC |
| R7-F2 | Specify that EXPLORE always replaces context['localization'] and document that skipping EXPLORE preserves prior data. | claude-4 (claude-opus-4-6) | Checkpoint restore behavior must be defined. The simplest correct behavior is always-replace, with the orchestrator skipping EXPLORE if prior data should be preserved. This is consistent with how other phases work. | 2026-02-20 02:52:27 UTC |
| R7-F3 | Validate tool name uniqueness from get_tools() at the start of execute(). | claude-4 (claude-opus-4-6) | Duplicate tool names cause silent dispatch bugs. A uniqueness check is trivial to implement (one set comprehension) and prevents a class of subtle errors. Good defensive programming. | 2026-02-20 02:52:27 UTC |
| R7-F4 | Add regex pre-validation for search_codebase pattern and restrict file_glob to prevent path traversal. | claude-4 (claude-opus-4-6) | LLM-generated regex patterns are frequently malformed. Pre-validating with re.compile() catches syntax errors before invoking grep. Rejecting path separators in file_glob prevents traversal. Character length limits prevent catastrophic backtracking. All lightweight checks. | 2026-02-20 02:52:27 UTC |
| R8-F1 | Recommend a submit_report tool as the primary mechanism for returning structured results instead of free-text parsing. | gemini-3 (gemini-3-pro-preview) | This directly addresses the fragility of parse_final_output. A submit_report tool leverages the LLM's tool-use formatting to guarantee JSON structure, making parsing reliable. R7-S3 (accepted) for budget-exhaustion summary calls complements this. This is a significant architectural improvement. | 2026-02-20 02:52:27 UTC |
| R1-F1 | Resolve contradiction between 'raise ToolExecutionError' and 'return error string' for tool failure handling. | claude-4 (claude-opus-4-6) | The contradiction between the docstring and the plan will cause inconsistent error handling across subclasses. Clarifying the ToolResult-based contract (aligned with already-accepted R1-S4) is essential for a consistent interface. | 2026-02-20 02:58:02 UTC |
| R1-F2 | Add _build_initial_message as an abstract method on ToolUsingPhaseHandler. | claude-4 (claude-opus-4-6) | The method is called in execute() but not declared abstract, which will cause AttributeError at runtime for subclasses that don't implement it. The plan's own Risk 6 acknowledges this gap. | 2026-02-20 02:58:02 UTC |
| R1-F3 | Provide exact whitelist regex for run_test instead of informal description with 'etc.' | claude-4 (claude-opus-4-6) | A security boundary defined with 'etc.' is unacceptable. Implementers need an exact regex to avoid either security holes or broken functionality. This complements accepted R4-F1. | 2026-02-20 02:58:02 UTC |
| R1-F4 | Standardize phase references to use WorkflowPhase enum consistently instead of mixing strings and enums. | claude-4 (claude-opus-4-6) | Inconsistency between string and enum types for phases will cause registration failures. Standardizing on the enum is straightforward and prevents type mismatch bugs. | 2026-02-20 02:58:02 UTC |
| R1-F6 | Reconcile token_budget default discrepancy (50K vs 10K) and provide sizing guidance. | claude-4 (claude-opus-4-6) | Contradictory defaults between class definition and example will confuse users. Sizing guidance helps operators set appropriate budgets and avoid cost overruns or premature termination. | 2026-02-20 02:58:02 UTC |
| R2-F1 | Clarify how phase-level cost tracking integrates with global workflow budget enforcement during execution. | gemini-3 (gemini-3-pro-preview) | Without specifying whether the phase checks the global budget mid-loop, an explore phase could exhaust the entire workflow budget, leaving nothing for downstream phases. This is operationally critical. | 2026-02-20 02:58:02 UTC |
| R3-F1 | Wrap agent loop in try/except to ensure cost tracking and partial results on failure. | claude-4 (claude-opus-4-6) | Unhandled exceptions in the agent loop losing all cost data and partial results is a significant operational gap. Returning partial results with cost enables debugging and accurate budget tracking. | 2026-02-20 02:58:02 UTC |
| R3-F2 | Explicitly specify sequential tool execution for v1 with a reserved concurrent_tools parameter. | claude-4 (claude-opus-4-6) | The ambiguity about sequential vs concurrent execution affects error handling, resource contention, and testing strategy. Making the v1 choice explicit with a path forward is good design. | 2026-02-20 02:58:02 UTC |
| R3-F3 | Change 'no network access' to honest documentation that network isolation is not enforced in v1. | claude-4 (claude-opus-4-6) | Stating a requirement that cannot be implemented as specified is worse than honestly documenting the limitation. The command whitelist is the actual security boundary in v1. | 2026-02-20 02:58:02 UTC |
| R3-F4 | Require context['localization'] always be written with confidence and partial fields to distinguish empty results from failures. | claude-4 (claude-opus-4-6) | Downstream phases need to distinguish 'explored and found nothing' from 'explore failed'. The confidence and partial fields enable fallback behavior. Has 1 endorsement. | 2026-02-20 02:58:02 UTC |
| R4-F1 | Mandate anchored regex (^...$) for the run_test command whitelist. | gemini-3 (gemini-3-pro-preview) | An unanchored regex is trivially bypassed by appending shell commands after the whitelisted prefix. Anchoring is a minimum requirement for the whitelist to function as a security boundary. | 2026-02-20 02:58:02 UTC |
| R5-F1 | Document private method signatures and contracts for _call_llm, _execute_tool, _calculate_cost, and _build_initial_message. | claude-4 (claude-opus-4-6) | These are called in execute() but their contracts are unspecified. The base class implementer needs clear specifications for retry logic, timeout, and error handling behavior. | 2026-02-20 02:58:02 UTC |
| R5-F2 | Document Anthropic-only tool format as intentional v1 design decision with note about multi-provider support. | claude-4 (claude-opus-4-6) | Option (a) is pragmatic — acknowledging the coupling and deferring abstraction is better than ignoring it or over-engineering v1. This sets expectations for future work. | 2026-02-20 02:58:02 UTC |
| R5-F3 | Allow relative paths in read_file tool and resolve them against project_root. | claude-4 (claude-opus-4-6) | LLMs overwhelmingly produce relative paths. Requiring absolute paths would cause most tool calls to fail. The schema description contradicts the sandboxing behavior. Has 1 endorsement. | 2026-02-20 02:58:02 UTC |
| R5-F4 | Serialize explore.fault_files as JSON string attribute for OTel backend compatibility. | claude-4 (claude-opus-4-6) | List attributes are dropped by some exporters, and fault_files is the most operationally important attribute. JSON serialization is a simple, compatible solution. | 2026-02-20 02:58:02 UTC |
| R5-F5 | Cap relevant_code total size in ExplorePhaseOutput to prevent inflating downstream phase context. | claude-4 (claude-opus-4-6) | Unbounded relevant_code directly wastes tokens in downstream DESIGN and IMPLEMENT phases. A 10K char cap is reasonable and prevents cost overruns in subsequent phases. | 2026-02-20 02:58:02 UTC |
| R6-F1 | Explicitly list issue_description and codebase_summary as required context keys for ExplorePhaseHandler. | gemini-3 (gemini-3-pro-preview) | These are implicitly required but not documented. Without them the agent runs without a goal, wasting money. Explicit entry requirements enable proper validation. | 2026-02-20 02:58:02 UTC |
| R6-F2 | Add requirement to handle context window exhaustion gracefully. | gemini-3 (gemini-3-pro-preview) | Token budget != context window. A conversation can exceed the model's context window before hitting the token budget, causing API errors. Graceful termination with partial results is essential. Has 1 endorsement. | 2026-02-20 02:58:02 UTC |
| R7-F1 | Enforce non-overridability of execute() via __init_subclass__ check. | claude-4 (claude-opus-4-6) | The 'do not override' comment is insufficient protection. A simple __init_subclass__ check prevents accidental breakage of the agent loop, cost tracking, and OTel instrumentation by subclass authors. | 2026-02-20 02:58:02 UTC |
| R7-F2 | Specify that EXPLORE always replaces context['localization'] and document skip-phase for preserving prior data. | claude-4 (claude-opus-4-6) | Checkpoint restore semantics need to be explicit. Replace-on-write is the simplest correct behavior, and the skip mechanism already handles preservation. Has 1 endorsement. | 2026-02-20 02:58:02 UTC |
| R7-F3 | Validate tool name uniqueness in execute() before starting the agent loop. | claude-4 (claude-opus-4-6) | Duplicate tool names cause silent dispatch ambiguity. A one-line validation check at loop start is cheap and prevents subtle bugs that would be very hard to diagnose. | 2026-02-20 02:58:02 UTC |
| R7-F4 | Add regex pre-validation and length/path restrictions for search_codebase pattern and file_glob parameters. | claude-4 (claude-opus-4-6) | LLM-generated regex can cause catastrophic backtracking, hanging grep for the full timeout. Pre-validation with re.compile() and length limits is a straightforward mitigation. | 2026-02-20 02:58:02 UTC |
| R8-F1 | Add a submit_report tool as the primary mechanism for structured result output, with parse_final_output as fallback. | gemini-3 (gemini-3-pro-preview) | Free-text parsing is fragile. A structured tool call gives the LLM a clear mechanism to return results in the expected format, significantly improving output reliability. Has 1 endorsement. | 2026-02-20 02:58:02 UTC |
| R9-F1 | Resolve contradiction between execute() return pattern and direct context mutation for output writing. | claude-4 (claude-opus-4-6) | This duplicates R9-S8 and identifies the same critical contradiction. The return-value pattern should be canonical for testability. Accepting to reinforce the importance of resolving this. | 2026-02-20 02:58:02 UTC |
| R9-F2 | Require shell=False for subprocess execution to eliminate shell injection via test path arguments. | claude-4 (claude-opus-4-6) | This reinforces R9-S1 with additional detail about argument-level injection. Even with anchored regex, LLM-supplied arguments after the prefix are interpreted by the shell. shell=False is the only robust solution. | 2026-02-20 02:58:02 UTC |
| R9-F3 | Fully specify submit_report tool behavior including loop termination, multiple call handling, parse_final_output interaction, and input schema. | claude-4 (claude-opus-4-6) | R8-F1 was accepted at a high level but left critical implementation details unspecified. These details (termination semantics, last-wins, fallback chain, schema) are architecturally significant and must be in the requirements. | 2026-02-20 02:58:02 UTC |
| R9-F4 | Specify that pending tool calls are NOT executed when token budget is exceeded, with a synthetic summary message appended. | claude-4 (claude-opus-4-6) | The behavior at budget exhaustion with pending tool calls is ambiguous and affects parse_final_output correctness. Skipping tools and appending a clean summary message is the right choice. Aligns with accepted R7-S3. | 2026-02-20 02:58:02 UTC |
| R10-F1 | Specify the regex flavor (Python re vs grep PCRE) for search_codebase patterns. | gemini-3 (gemini-3-pro-preview) | LLMs generate regex with features that differ between flavors. If validation uses Python re.compile() (per R7-F4) but execution uses grep without -P, valid-looking patterns will fail. The flavor must be consistent between validation and execution. | 2026-02-20 02:58:02 UTC |
| R10-F2 | Add loop termination signal capability to ToolResult for submit_report to avoid wasting an extra turn. | gemini-3 (gemini-3-pro-preview) | Without a termination signal, the agent wastes a full LLM round-trip after submit_report just to say 'I'm done.' A terminate_loop field on ToolResult is a clean mechanism that saves tokens and latency. Aligns with R9-F3. | 2026-02-20 02:58:02 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-F5 | Specify OTel SpanKind and exact span hierarchy for tool calls and iterations. | claude-4 (claude-opus-4-6) | While helpful for consistency, this is an over-specification for this stage. The default INTERNAL SpanKind is reasonable for all these spans, and the plan already specifies tool calls as events (not spans) on iteration spans. This can be refined after initial implementation based on actual trace analysis needs. | 2026-02-20 02:09:03 UTC |
| R1-F5 | Specify OTel SpanKind and detailed span hierarchy for tool calls. | claude-4 (claude-opus-4-6) | The existing codebase uses default INTERNAL spans consistently. Over-specifying SpanKind at this stage adds complexity without clear operational benefit. The plan's current approach (events for tool calls, child spans for iterations) is sufficient for v1. Can be refined based on actual trace analysis. | 2026-02-20 02:15:20 UTC |
| R1-F5 | Specify OTel SpanKind and exact span hierarchy for tool calls. | claude-4 (claude-opus-4-6) | The plan already specifies iteration child spans and tool call events in Section 7. SpanKind defaults to INTERNAL which is appropriate for all these cases. This level of OTel specification detail is over-engineering for a v1 plan. | 2026-02-20 02:21:54 UTC |
| R4-F2 | Add cost_budget parameter with dynamic token limits based on model pricing. | gemini-3 (gemini-3-pro-preview) | This adds significant complexity (dynamic pricing lookup, token-to-cost conversion at each iteration) for v1. The global workflow cost_budget already exists at the orchestrator level. Per-phase cost budgets can be added in v2. Token budget is sufficient for v1 iteration control. | 2026-02-20 02:21:54 UTC |
| R5-F4 | Serialize explore.fault_files as JSON string for OTel backend compatibility. | claude-4 (claude-opus-4-6) | The OTel spec supports Sequence[str] attributes. Working around older Jaeger versions is not worth the complexity of JSON serialization/deserialization. Modern backends (Tempo, OTLP) handle list attributes correctly. This is a minor operational concern. | 2026-02-20 02:21:54 UTC |
| R1-F5 | Specify OTel SpanKind and detailed span hierarchy rules for all spans. | claude-4 (claude-opus-4-6) | The current plan already specifies iteration spans as children of the phase span and tool calls as events. SpanKind defaults to INTERNAL which is appropriate for all these cases (subprocess calls are local, not remote service calls). This level of OTel specification detail is over-prescriptive for a requirements doc and can be handled at implementation time. | 2026-02-20 02:52:27 UTC |
| R4-F2 | Add a cost_budget parameter with dynamic token limits based on model pricing. | gemini-3 (gemini-3-pro-preview) | The global workflow already has a cost_budget (WorkflowConfig). Adding a second cost_budget at the phase level creates confusing dual budget semantics. Token budget is the appropriate phase-level control; cost budget belongs at the workflow/orchestrator level. R2-F1 addresses the integration question. | 2026-02-20 02:52:27 UTC |
| R5-F4 | Serialize explore.fault_files as JSON string instead of native list attribute for OTel backend compatibility. | claude-4 (claude-opus-4-6) | The OTel specification explicitly supports Sequence[str] attributes. Degrading to JSON strings for compatibility with outdated backends is a premature optimization. Modern backends (and the ones likely in use) handle list attributes correctly. This can be addressed if a specific backend issue arises. | 2026-02-20 02:52:27 UTC |
| R1-F5 | Specify OTel SpanKind and exact span hierarchy for tool calls. | claude-4 (claude-opus-4-6) | This is over-specification for v1. The default INTERNAL SpanKind is appropriate for all these operations (they're internal processing, not outbound RPCs to external services). Tool call events as events on iteration spans is already specified and sufficient. | 2026-02-20 02:58:02 UTC |
| R4-F2 | Add cost_budget parameter with dynamic token limits based on model pricing. | gemini-3 (gemini-3-pro-preview) | This adds significant complexity (requiring real-time pricing lookups during the loop) for v1. The workflow-level cost_budget already exists in WorkflowConfig. Phase-level token budgets are simpler and sufficient; R2-F1 addresses the integration with workflow budget. | 2026-02-20 02:58:02 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:07:20 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interface Design — `handle_tool_use` | Contradiction | The docstring says "Raise `ToolExecutionError` for failures" but the plan (Section 5, `_read_file`) says "return error string (don't raise — LLM should see errors)." These are contradictory instructions for implementers. | Subclass authors will be confused about error handling contract. Some will raise, some will return strings, leading to inconsistent behavior and potential unhandled exceptions in the agent loop. | Clarify: `handle_tool_use` should return a `ToolResult` (see R1-S4). For expected tool failures (file not found, timeout), return `ToolResult(content=error_msg, is_error=True)`. For unexpected failures (bugs in tool code), let exceptions propagate to the base class's `_execute_tool` wrapper which catches and converts them. |
| R1-F2 | Interface Design — `_build_initial_message` | Missing from ABC | `_build_initial_message` is called in `execute()` but is not listed as an `@abstractmethod` on `ToolUsingPhaseHandler`. It only appears in `ExplorePhaseHandler`. | Subclasses can be instantiated without implementing this method, causing `AttributeError` at runtime. | Add `_build_initial_message(self, context: dict[str, Any]) -> str` as an abstract method on `ToolUsingPhaseHandler`. (The plan's Risk 6 notes this but the requirements doc doesn't fix it.) |
| R1-F3 | Tool Safety — `run_test` | Ambiguity | The whitelist regex pattern is described informally ("pytest, unittest, npm test, etc.") but no exact regex is specified. The "etc." is dangerous for a security boundary. | Implementers must guess which commands are allowed. Different interpretations lead to either too-permissive (security hole) or too-restrictive (broken functionality) implementations. | Provide the exact whitelist regex in the requirements. Specify whether arguments after the whitelisted command prefix are unrestricted or also validated. |
| R1-F4 | Integration — Phase Registration | Ambiguity | The example shows `phases=["explore"] + WorkflowPhase.ordered()` using a string, but the plan uses `phases=[WorkflowPhase.EXPLORE] + WorkflowPhase.ordered()` using an enum. The requirements doc and plan are inconsistent on whether phases are strings or enums. | Implementers may use the wrong type, causing registration failures or key mismatches. | Standardize on one type. Since `WorkflowPhase` is an enum, use the enum consistently. Update the requirements example to match. |
| R1-F5 | OTel Instrumentation | Missing detail | The requirements specify span names and attributes but do not specify which OTel `SpanKind` to use, or whether tool call spans should be children of the iteration span or siblings. | Inconsistent span hierarchy makes traces hard to read in Jaeger/Tempo. Missing `SpanKind` means default `INTERNAL` is used even for subprocess calls that arguably are `SpanKind.CLIENT`. | Specify: iteration spans are `INTERNAL` children of the phase span. Tool call events remain as events (not separate spans) unless they exceed a duration threshold. `_run_test` subprocess calls should be separate child spans with `SpanKind.INTERNAL`. |
| R1-F6 | Bounded Iteration | Missing detail | The `token_budget` default is 50,000 in the class definition but 10,000 in the integration example. No guidance on how to choose a budget for different tasks. | Users will pick arbitrary values. Too low → premature termination. Too high → cost overruns. | Provide sizing guidance: "A typical explore run on a medium-sized Python project uses 15,000–30,000 tokens. Set `token_budget` to 2× expected usage for safety margin." Reconcile the 50K vs 10K discrepancy. |

---

#### Review Round R2

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:07:57 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Issue | Description |
| ---- | ---- | ---- |
| R2-F1 | Ambiguity | **Requirement:** "Full cost tracking". **Issue:** The plan calculates cost but doesn't specify if/how this integrates with the *global* workflow budget during the execution loop. If the explore phase burns $4.00 of a $5.00 budget, does it stop immediately or wait for the phase to finish? |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:12:13 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Interface Design — `execute()` | Missing error handling | The `execute()` method in the requirements shows no try/except around the agent loop. If `_call_llm` or `_execute_tool` raises an unhandled exception, the entire phase fails with no partial results and no cost tracking for the tokens already consumed. The requirements should specify error handling behavior for the non-overridable `execute()` method. | Operators lose cost visibility on failed runs. Retry logic has no information about how far the loop progressed. Budget tracking becomes inaccurate (consumed tokens not reported). | Wrap the agent loop in try/except. On any exception, still compute and return cost for tokens consumed so far. Include `error` key in metadata. Re-raise as `PhaseExecutionError` with partial results attached. |
| R3-F2 | Interface Design — `handle_tool_use` | Missing concurrency specification | The requirements show `handle_tool_use` called sequentially for each tool_use block in a response. The LLM can return multiple tool_use blocks in a single response (acknowledged in the unit test plan: `test_multiple_tool_calls_in_single_response`). The requirements don't specify whether multiple tool calls should execute sequentially or concurrently. | Sequential execution of independent tool calls (e.g., reading 3 different files) wastes wall-clock time. Concurrent execution risks resource contention and complicates error handling. The requirements should make an explicit choice. | Specify: v1 executes tool calls sequentially within an iteration. Add a `concurrent_tools: bool = False` constructor parameter reserved for future use. Document the rationale: sequential is simpler, safer, and sufficient for v1 where iterations are cheap relative to LLM calls. |
| R3-F3 | Tool Safety — Sandboxing | Missing specification | The requirements say "no network access" for `run_test` but provide no mechanism to enforce it. `subprocess.run` with `shell=True` does not restrict network access. On Linux, this would require `unshare --net`, seccomp, or a container. On macOS, there's no simple equivalent. The requirement is stated but unimplementable as specified. | Either the requirement is silently violated (tests make network calls), or implementers add platform-specific sandboxing that's out of scope for the 2-day estimate. | Change "no network access" to "network access is not prevented in v1; the tool relies on the command whitelist to limit execution to test runners. Production deployments SHOULD run the explore phase in a network-isolated container." This makes the security boundary honest. |
| R3-F4 | Context Flow | Missing failure mode specification | The context flow shows a happy path where `context["localization"]` is fully populated. The requirements don't specify what happens if EXPLORE produces partial or empty results. Does DESIGN phase skip? Does it fall back to non-localized mode? Does the workflow abort? | Downstream phases can't distinguish "EXPLORE ran and found nothing" from "EXPLORE failed." Operators can't configure fallback behavior. | Add to Context Flow: `context["localization"]` MUST always be written (even on partial failure). Include a `confidence: float` field (0.0-1.0) and `partial: bool` field. DESIGN phase checks `confidence > 0.3` to use localization, otherwise falls back to full-context mode. |

#### Review Round R4

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:13:56 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Tool Safety — `run_test` | Security | The requirement specifies a whitelist regex but does not mandate anchors (`^...$`) or shell injection prevention. | `shell=True` with unanchored regex allows `make test; rm -rf /`. | Require whitelist regex to be strictly anchored to start and end of string, or forbid shell metacharacters. |
| R4-F2 | Resource Limits | Conflict | Requirement asks for "Full cost tracking (compatible with budget enforcement)" but defines `token_budget` (int). | Users setting a $5.00 budget expect the phase to stop at $5.00, not at 50k tokens (which could be $0.15 or $15.00 depending on model). | Add `cost_budget` parameter to the interface and require dynamic token limits based on model pricing. |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:19:14 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Interface Design — `execute()` | Missing specification | The `execute()` method shows `response = self._call_llm(...)` but `_call_llm` is never defined as a method on the class — it's not abstract, not concrete, and not documented. Similarly, `_execute_tool`, `_calculate_cost`, and `_build_initial_message` are called but their signatures and contracts are unspecified in the requirements. These are internal implementation methods that subclass authors shouldn't override, but their behavior needs to be specified for the base class implementer. | The base class implementer must guess the contract of 4 undocumented private methods. `_call_llm` in particular has critical behavioral requirements (retry logic, timeout, error handling) that affect correctness. | Add a "Private Methods" subsection to the Interface Design section specifying signatures and contracts for `_call_llm`, `_execute_tool`, `_calculate_cost`, and `_build_initial_message` (the latter already flagged in R1-F2 but only as abstract — the others remain undocumented). |
| R5-F2 | Interface Design — `get_tools()` | Vendor lock-in | `get_tools()` returns Anthropic-specific tool format. The requirements explicitly say "Returns Anthropic tool_use format." If the SDK later needs to support OpenAI or other providers (which use a different tool schema with `"type": "function"` wrapper), every subclass must be rewritten. | Tight coupling to Anthropic's schema in the abstract interface makes multi-provider support a breaking change. This contradicts the plan's use of a `model` parameter that suggests provider flexibility. | Either: (a) document this as an intentional Anthropic-only design decision with a note that multi-provider support would require a schema translation layer, or (b) define a provider-neutral tool schema and add a `_to_anthropic_tools()` translation in the base class. Option (a) is recommended for v1 with a clear note. |
| R5-F3 | Tool Safety — `read_file` | Ambiguity | The tool's `input_schema` defines `path` as `"description": "Absolute path to file"` but the sandboxing section says paths are resolved relative to `project_root`. If the LLM sends a relative path (which it frequently does — e.g., `src/auth.py`), should it be rejected (schema says absolute) or resolved relative to `project_root` (which is more useful)? The requirement contradicts itself. | LLMs overwhelmingly produce relative paths. Requiring absolute paths means either (a) the system prompt must always include `project_root` for the LLM to construct absolute paths, or (b) most tool calls will fail. Neither is ideal. | Change the schema description to "Path to file (absolute or relative to project root)" and document that `_validate_path` resolves relative paths against `project_root` before validation. |
| R5-F4 | OTel Instrumentation | Missing specification | The requirements specify OTel spans emit `explore.fault_files` as `[str]` but OTel span attributes do not support list types in all backends. The OpenTelemetry specification supports `Sequence[str]` attributes, but some exporters (e.g., older Jaeger versions) flatten or drop them. | Traces may lose the most operationally important attribute (which files were identified as faulty) depending on the backend. | Specify that `explore.fault_files` should be serialized as a JSON string attribute (e.g., `'["src/auth.py","src/utils.py"]'`) for maximum backend compatibility, with a note that native list attributes may be used when backend support is confirmed. |
| R5-F5 | Context Flow | Missing specification | The context flow example shows `context["localization"]["relevant_code"]` as a dict mapping `"src/auth.py:73-85"` to code snippets. There's no size limit on this field. If the LLM copies large code blocks (hundreds of lines across multiple files), this inflates context for downstream phases, consuming their token budgets. | DESIGN and IMPLEMENT phases inherit the full `localization` dict. Oversized `relevant_code` wastes tokens in downstream prompts and could push them over their own budgets. | Add a size constraint to `ExplorePhaseOutput` validation: `relevant_code` total character count should be capped (e.g., 10,000 chars). `parse_final_output` should truncate if necessary. |

#### Review Round R6

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:20:26 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | Interface Design | Missing Requirement | The `ExplorePhaseHandler` implicitly depends on `issue_description` (for the initial message) and `codebase_summary` (for the system prompt), but these are not listed as required inputs. | If these are missing from the context, the agent will run without a goal or map, wasting money and failing silently. | Explicitly list `issue_description` and `codebase_summary` as required keys in the `Context Flow` or `Integration` section. |
| R6-F2 | Resource Limits | Missing Requirement | The requirements specify a `token_budget` (cost control) but fail to address **Context Window** limits (technical constraint). | If the conversation history exceeds the model's context window, the API call will fail with a 400 error, crashing the workflow. | Add a requirement to handle context window exhaustion (e.g., "If context limit is reached, terminate loop gracefully and return partial results"). |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:49:35 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | Interface Design — `execute()` | Missing specification | The `execute()` method is documented as "Do not override" but Python has no mechanism to enforce this on non-`__dunder__` methods. A subclass that accidentally overrides `execute()` (e.g., to add logging) will silently break the agent loop, cost tracking, and OTel instrumentation. The requirements should specify enforcement strategy. | Subclass authors unfamiliar with the codebase may override `execute()` thinking they can customize behavior, breaking all the safety invariants the base class provides. | Either: (a) add a `__init_subclass__` check that raises `TypeError` if a subclass defines `execute`, or (b) rename the non-overridable method to `_run_agent_loop` and have `execute()` be a thin wrapper that calls it. Option (a) is simpler and matches the "do not override" intent. |
| R7-F2 | Context Flow | Missing specification | The requirements specify that `context["localization"]` is written by EXPLORE and read by DESIGN, but they don't specify whether EXPLORE should *merge* with or *replace* an existing `context["localization"]` if one exists (e.g., from a previous run, a manual override, or a checkpoint restore). If the workflow is resumed from a checkpoint that already has localization data, does EXPLORE overwrite it? | Checkpoint restore + re-run could lose manually-curated localization data. Conversely, stale localization from a failed run could persist if EXPLORE errors out before writing. | Specify that EXPLORE always writes `context["localization"]`, replacing any existing value. If preserving prior localization is needed, the orchestrator should skip the EXPLORE phase (which is already possible since EXPLORE is not in `ordered()`). Document this as an explicit design decision. |
| R7-F3 | Interface Design — `get_tools()` | Missing constraint | The requirements specify `get_tools()` returns a list of tool definitions, but there is no validation that the returned tools have unique names. If a subclass returns two tools with the same `name`, the Anthropic API may accept it but `handle_tool_use` dispatch becomes ambiguous. | Duplicate tool names cause silent misbehavior where the wrong tool handler is invoked. The base class should validate tool name uniqueness at the start of `execute()`. | Add to `execute()` before the loop: validate that all tool names from `get_tools()` are unique. Raise `ValueError` if duplicates detected. This is a cheap check that prevents subtle bugs. |
| R7-F4 | Tool Safety — `search_codebase` | Missing specification | The `search_codebase` tool accepts a `pattern` parameter described as "Regex pattern" but the requirements don't specify any validation or sanitization of the regex. A catastrophic backtracking regex (e.g., `(a+)+$`) can cause `grep` to hang, consuming CPU until the tool timeout. More concerning, the `file_glob` parameter could contain shell glob characters that behave unexpectedly with `--include`. | LLM-generated regex patterns are frequently malformed or pathological. Without input validation, a single bad pattern can hang `grep` for the full 30-second timeout on every file in the project. | Add regex pre-validation: (1) attempt `re.compile(pattern)` to verify it's valid regex, (2) reject patterns exceeding 200 characters, (3) reject `file_glob` values containing path separators or `..`. |

#### Review Round R8

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:50:39 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R8-F1 | Interface Design | Robustness | The example system prompt instructs the agent to "respond with a structured localization report" as text, and `parse_final_output` extracts it. Free-text parsing is fragile compared to structured tool calls. | The agent may output valid text that fails regex parsing (e.g., markdown formatting, conversational filler), causing the phase to fail despite finding the bug. | Update requirements to recommend a `submit_report` tool (or similar) as the primary mechanism for returning the final structured result, using `parse_final_output` to extract the tool payload. |

#### Review Round R9

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:55:17 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R9-F1 | Interface Design — `execute()` | Contradiction | The requirements show `execute()` calling `self._call_llm()` and returning `{"output": output}`, implying the orchestrator handles context writing. But the Integration section says "Handler writes directly to context dict: `context['localization'] = output`". These are two different patterns and the requirements specify both without reconciling them. The `execute()` signature doesn't even receive a mutable context reference in the return path — it receives `context` as input but returns a dict. | Implementers will be confused about whether to mutate `context` inside `execute()` or return output for the orchestrator. Testing strategy differs significantly between the two approaches. Existing handlers in the codebase may use either pattern inconsistently. | Pick one canonical pattern. Recommended: `execute()` returns `{"output": localization_dict, ...}` and the orchestrator writes `context["localization"] = result["output"]`. This matches the return type contract and is more testable. Update the Integration section accordingly. |
| R9-F2 | Tool Safety — `run_test` | Incomplete | The requirements specify `shell=True` for subprocess execution and a command whitelist regex as the security boundary. Even with the anchored regex from R4-F1, `shell=True` interprets shell metacharacters that appear *within* the whitelisted command's arguments (e.g., `python -m pytest 'tests/$(rm -rf /)'`). The regex anchors the prefix but LLM-supplied arguments after the prefix are unconstrained. | Shell injection via test path arguments. The LLM constructs the full command string including arguments, and those arguments are interpreted by the shell. A malicious or confused LLM could craft arguments containing shell metacharacters that execute arbitrary code. | Require `shell=False` with argument list parsing. The whitelist validates the command structure, then `shlex.split()` tokenizes it, and `subprocess.run()` receives a list. This eliminates shell interpretation entirely. |
| R9-F3 | Interface Design — `submit_report` tool | Missing specification | R8-F1 was accepted recommending a `submit_report` tool, but the requirements don't specify: (a) whether `submit_report` terminates the loop or allows continued exploration, (b) how multiple `submit_report` calls are handled, (c) the relationship between `submit_report` and `parse_final_output`, (d) the exact input_schema for the tool. | Without these details, the implementer must make design decisions that should be specified at the requirements level. The interaction between structured tool output and free-text parsing fallback is architecturally significant. | Add a subsection specifying: `submit_report` sets a flag that terminates the loop after the current iteration. Last call wins if multiple are made. `parse_final_output` first checks for `submit_report` payloads in the message history, falling back to free-text extraction only if none found. Define the input_schema matching `ExplorePhaseOutput` fields. |
| R9-F4 | Resource Limits | Missing specification | The requirements specify `token_budget` checks "AFTER adding response tokens but BEFORE executing tools" but don't specify what happens to the *current response's tool calls* when the budget is exceeded. If the LLM returns 3 tool_use blocks and the budget is exceeded after counting the response tokens, are the tool calls executed or skipped? | Skipping tool calls means the LLM's last response is never fulfilled, and the message history ends with an unanswered tool request. Executing them means exceeding the budget. Both have implications for `parse_final_output` — it may receive an incomplete conversation. | Specify: when token budget is exceeded after an LLM response, do NOT execute pending tool calls. Instead, append a synthetic assistant message summarizing the budget exhaustion, then call `parse_final_output`. This gives the parser a clean conversation to work with. (This interacts with R7-S3 which was accepted for budget-exhaustion summary calls.) |

#### Review Round R10

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:56:21 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R10-F1 | Tool Specifications | Ambiguity | The `search_codebase` tool requires a "Regex pattern" but does not specify the regex flavor (PCRE vs Python `re`). | LLMs may generate regexes with lookaheads/lookbehinds that work in Python but fail in `grep` (or vice versa depending on flags), causing tool errors. | Specify that the pattern must be compatible with Python's `re` module (if using Python validation) or PCRE (if using `grep -P`). |
| R10-F2 | Interface Design | Missing Feature | The Agent Loop design assumes a "continue" loop. If a tool like `submit_report` is used (per R8-F1), the loop should terminate immediately to save a turn. | Without a termination signal, the agent must call `submit_report`, get a result, and then emit "I am done" in a separate turn, wasting time and tokens. | Add a `terminate_loop: bool` field to `ToolResult` or allow `handle_tool_use` to signal loop termination. |

