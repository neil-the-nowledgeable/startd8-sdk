# Issue-to-Localization Mapper: From Bug Report to Affected Components

## Status: Not Built

## Problem

The Explore phase has two deterministic inputs:
1. A **bug report / issue description** (unstructured natural language)
2. A **codebase map** (structured output from Eagle + ContextCore extract)

And one optional structural input:
3. A **Code Manifest** (`ManifestRegistry` — AST-derived element inventory with FQNs, signatures, call graph, and symbol table data)

Nothing currently bridges the gap: mapping the issue's description to specific files, functions, and components in the codebase maps. Without this, the agent loop in `ToolUsingPhaseHandler` starts from scratch — reading the issue, then blindly exploring.

## Goal

A pre-exploration step that uses the capability map (and optionally the Code Manifest) to **narrow the search space** before the agent loop begins. Given an issue and a codebase map, produce a ranked list of likely-affected components, so the agent can start its exploration from the most relevant files instead of wandering the repo.

This is the "aim before you fire" step that makes the agent loop surgical.

## Where It Fits

```
Context Bridge (01)           → project_structure + capability_map
Code Manifest (optional)      → ManifestRegistry (FQNs, call graph, all elements)
Issue-to-Localization (this)  → candidate_components (narrowed search space)
Tool-Using Phase Handler (02) → localization (confirmed fault files + root cause)
```

It runs **inside** the ExplorePhaseHandler, after the context bridge has populated the maps, but **before** the agent loop begins tool use:

```
ExplorePhaseHandler.execute():
    1. Context Bridge populates project_structure + capability_map
    2. Issue-to-Localization Mapper narrows candidates    ← THIS
    3. Agent loop explores candidates with tools
    4. Returns localization dict
```

## Design

### Input

```python
issue_description: str
# "When a user refreshes their token with refresh=True, the expiry check
#  is skipped and expired tokens are accepted. This allows access after
#  token expiration."

project_structure: dict   # From Eagle (services, files, dependencies)
capability_map: dict      # From ContextCore extract (functions, classes, APIs, tests)
manifest_registry: ManifestRegistry | None  # From Code Manifest (FQNs, signatures, call graph)
```

When `manifest_registry` is available, the mapper gains:
- **Complete element coverage** — includes private functions (e.g., `_validate_token`) that ContextCore's `CapabilityExtractor` skips
- **FQN-based matching** — fully-qualified names enable precise element identification
- **Call graph context** — caller/callee relationships inform relevance ranking
- **Blast radius data** — transitive caller counts quantify change impact

### Output

```python
@dataclass
class CandidateComponent:
    """A component that likely relates to the issue."""
    file_path: str
    component_name: str           # function/class/endpoint name
    component_type: str           # "function", "class", "api", "cli"
    relevance_score: float        # 0.0 to 1.0
    relevance_reason: str         # why this component is a candidate
    line_number: Optional[int]
    signature: Optional[str]
    docstring: Optional[str]
    fqn: Optional[str]            # Fully-qualified name (manifest-enriched, when available)
    caller_count: Optional[int]   # Number of direct callers (manifest-enriched, when available)

@dataclass
class LocalizationCandidates:
    """Narrowed search space for the agent loop."""
    candidates: list[CandidateComponent]   # ranked by relevance_score
    search_keywords: list[str]             # extracted from issue for grep
    likely_services: list[str]             # Eagle services likely involved
    confidence: float                      # overall confidence in candidates
    reasoning: str                         # LLM's explanation of its mapping
```

### Approach: Two-Pass Mapping

#### Pass 1: Keyword Extraction + Lexical Matching (No LLM)

Fast, deterministic filtering using the issue text:

1. **Extract keywords** from the issue:
   - Code identifiers: `refresh`, `token`, `expiry`, `validate`
   - File paths mentioned: `auth.py`, `test_auth.py`
   - Error messages: `"expired tokens are accepted"`
   - Class/function names: `_validate_token`, `TokenRefresh`

2. **Match against capability_map.by_type**:
   - Search function names for keyword overlap
   - Search class names
   - Search docstrings
   - Search API endpoint paths

3. **Match against project_structure.services**:
   - Service names containing keywords
   - File paths containing keywords

4. **Match against ManifestRegistry** (when available):
   - Search element FQNs for keyword overlap (includes private functions)
   - Search element signatures for parameter names
   - Use `manifest_registry.file_element_summary()` for file-level context
   - Enrich candidates with FQN, caller count, and blast radius data

5. **Score each match**:
   - Name exact match: 1.0
   - FQN match (manifest): 1.0
   - Name substring match: 0.7
   - Docstring keyword match: 0.5
   - File path keyword match: 0.3

Output: ranked list of candidates with lexical relevance scores.

#### Pass 2: LLM Semantic Ranking (Single LLM Call)

One focused LLM call to refine the lexical matches:

```
System: You are a bug localization expert. Given an issue description
and a list of candidate components from the codebase, rank which
components are most likely related to the issue.

User:
Issue: {issue_description}

Candidate components (from lexical matching):
1. src/auth.py:_validate_token(token, refresh=False) -> bool
   Docstring: "Validate a JWT token. Optionally skip checks for refresh tokens."
   Lexical score: 0.85

2. src/auth.py:TokenValidator (class)
   Docstring: "Handles JWT validation with configurable policies."
   Lexical score: 0.70

3. src/auth_utils.py:_refresh_token(token) -> Token
   Docstring: "Generate a new token from a refresh token."
   Lexical score: 0.65

4. tests/test_auth.py:test_token_expiry
   Docstring: None
   Lexical score: 0.50

[... more candidates ...]

For each candidate, output:
- relevance_score (0.0-1.0)
- relevance_reason (one sentence)
- should_explore (true/false)

Also output:
- search_keywords: additional terms to grep for
- likely_root_cause: your hypothesis (will be verified by exploration)
```

This single LLM call costs ~$0.01-0.05 (small prompt, small response). It transforms lexical matches into **semantically ranked** candidates with explanations.

When `ManifestRegistry` is available, Pass 2's prompt is enriched with call graph context for each candidate:
- **Caller count**: "This function is called by 7 other functions" — helps the LLM assess importance
- **Key callers**: Top callers listed by FQN — helps the LLM understand dependency chains
- **Blast radius**: Transitive caller count — helps the LLM prioritize high-impact candidates

### Why Two Passes

| | Pass 1 (Lexical) | Pass 2 (Semantic) |
|---|---|---|
| **Cost** | $0.00 | ~$0.01-0.05 |
| **Speed** | Milliseconds | ~2-5 seconds |
| **Recall** | High (keyword matching finds many candidates) | Lower (LLM may dismiss some) |
| **Precision** | Low (many false positives) | High (LLM understands context) |
| **Hallucination** | None (deterministic) | Possible but bounded (works from real data) |

Pass 1 ensures nothing is missed. Pass 2 eliminates noise. The agent loop in Step 3 only explores components that survived both passes.

## Token Savings

Without the mapper, the agent loop explores blindly:

```
Without mapper (typical SWE-Agent):
  Agent: "Let me search for 'token' in the codebase"  → 50 results, 2000 tokens
  Agent: "Let me search for 'refresh'"                  → 30 results, 1500 tokens
  Agent: "Let me read auth.py"                           → 300 lines, 1000 tokens
  Agent: "Let me read auth_utils.py"                     → 200 lines, 700 tokens
  Agent: "Let me read config.py" (irrelevant)            → 150 lines, 500 tokens wasted
  Agent: "Let me read middleware.py" (irrelevant)         → 400 lines, 1200 tokens wasted
  Total exploration: ~7,000 tokens, 6 iterations, 2 wasted reads

With mapper:
  Pass 1: Lexical matching → 12 candidates (0 tokens)
  Pass 2: LLM ranking → 4 high-relevance candidates (500 tokens)
  Agent: "Reading _validate_token in auth.py:73-85"      → 12 lines, 100 tokens
  Agent: "Reading _refresh_token in auth_utils.py:120"    → 10 lines, 80 tokens
  Agent: "Running test_token_expiry to reproduce"         → test output, 200 tokens
  Total exploration: ~880 tokens, 3 iterations, 0 wasted reads
```

**~8x token reduction** on the exploration phase.

## Integration with ExplorePhaseHandler

```python
class ExplorePhaseHandler(ToolUsingPhaseHandler):

    def execute(self, phase, context, dry_run=False):
        if dry_run:
            return {"output": None, "cost": 0.0, "metadata": {"dry_run": True}}

        # Step 1: Context Bridge (01) — already populated by pipeline
        # context["bridge_context"] contains project_structure + capability_map

        # Step 2: Issue-to-Localization Mapper (THIS)
        bridge = context.get("bridge_context") or {}
        mapper = IssueToLocalizationMapper(
            project_structure=bridge.get("project_structure", {}),
            capability_map=bridge.get("capability_map", {}),
            manifest_registry=self.manifest_registry,  # ManifestRegistry | None
        )
        candidates = mapper.map(
            issue_description=context["issue_description"],
            model=self.model,
        )
        context["localization_candidates"] = candidates

        # Step 3: Targeted Agent Loop (02)
        # Agent receives candidates in its system prompt,
        # explores only high-relevance files
        return super().execute(phase, context, dry_run)

    def get_system_prompt(self, context):
        candidates = context.get("localization_candidates")
        candidate_text = self._format_candidates(candidates)

        return f"""You are a code exploration agent localizing a bug.

Pre-analysis has identified these likely-affected components:

{candidate_text}

Start by reading the highest-ranked candidates. Use tools to verify
the hypothesis and identify the root cause. You do NOT need to explore
the entire codebase — focus on the candidates above.

Search keywords suggested: {', '.join(candidates.search_keywords)}
"""
```

## IssueToLocalizationMapper Class

```python
class IssueToLocalizationMapper:
    """Maps an issue description to candidate codebase components."""

    def __init__(
        self,
        project_structure: dict,
        capability_map: dict,
        manifest_registry=None,  # ManifestRegistry | None
    ):
        self.project_structure = project_structure
        self.capability_map = capability_map
        self.manifest_registry = manifest_registry

    def map(
        self,
        issue_description: str,
        model: str = "claude-haiku-4-5-20251001",
        max_candidates: int = 20,
    ) -> LocalizationCandidates:
        """Two-pass mapping: lexical then semantic."""

        # Pass 1: Keyword extraction + lexical matching
        keywords = self._extract_keywords(issue_description)
        lexical_candidates = self._lexical_match(keywords, max_results=50)

        # Pass 2: LLM semantic ranking
        ranked = self._semantic_rank(
            issue_description, lexical_candidates, model
        )

        # Filter to top candidates
        top = [c for c in ranked.candidates if c.relevance_score >= 0.4]
        top = top[:max_candidates]

        return LocalizationCandidates(
            candidates=top,
            search_keywords=ranked.search_keywords,
            likely_services=ranked.likely_services,
            confidence=ranked.confidence,
            reasoning=ranked.reasoning,
        )

    def _extract_keywords(self, issue: str) -> list[str]:
        """Extract code identifiers, file paths, error messages from issue text.

        Uses regex patterns for:
        - snake_case identifiers
        - CamelCase identifiers
        - File paths (*.py, *.js, etc.)
        - Quoted strings (error messages)
        - Function calls (name(...))
        """
        ...

    def _lexical_match(
        self, keywords: list[str], max_results: int
    ) -> list[CandidateComponent]:
        """Match keywords against capability_map and manifest entries.

        Searches (in order):
        - manifest_registry elements (FQNs, signatures — when available)
        - capability_map.by_type.functions[].name
        - capability_map.by_type.classes[].name
        - capability_map.by_type.api_endpoints[].name
        - capability_map.by_type.*.docstring
        - project_structure.services[].files[].path

        When manifest_registry is available, candidates are enriched
        with fqn and caller_count fields.
        """
        ...

    def _semantic_rank(
        self,
        issue: str,
        candidates: list[CandidateComponent],
        model: str,
    ) -> LocalizationCandidates:
        """Single LLM call to rank candidates by semantic relevance."""
        ...
```

## Model Selection for Pass 2

**Haiku 4.5** is the recommended model for the semantic ranking pass:
- The task is classification/ranking, not generation — Haiku excels at this
- Input is small (~500-1000 tokens of candidates + issue)
- Output is small (~200-500 tokens of rankings)
- Cost: ~$0.001-0.005 per issue
- Latency: ~1-2 seconds

Using Opus or Sonnet here would be wasteful — the task doesn't require deep reasoning, just semantic matching.

## Edge Cases

### Issue mentions no code identifiers

```
Issue: "The app crashes when I click the login button"
```

Pass 1 extracts: `["login", "button", "crash"]`
Lexical matches may be weak. Pass 2 becomes more important — the LLM understands that "login button" maps to auth-related components even without exact identifier matches.

### Issue mentions files that don't exist

```
Issue: "Bug in authentication.py line 45"
```

Pass 1 looks for `authentication.py` — not found. Falls back to fuzzy matching: `auth.py`, `auth_handler.py`. Pass 2 confirms the fuzzy match.

### Multi-service issue

```
Issue: "Payment fails when email notification service is down"
```

Eagle's service dependency map identifies: `paymentservice → emailservice (gRPC)`. Both services and their dependency edge become candidates.

### No capability_map available (non-Python project)

Fall back to Eagle's project_structure only. Pass 1 matches against file paths and service names. Pass 2 does its best with file-level information. The agent loop in Step 3 will need to read more files manually.

**Note**: When `ManifestRegistry` is available but `capability_map` is empty (Python project without ContextCore), the manifest provides a superior fallback — it includes all elements with FQNs, signatures, and call graph data. In this case, Pass 1 uses manifest elements as the primary data source rather than falling back to file-level-only matching.

### ManifestRegistry available without capability_map

When `manifest_registry` is present but `capability_map` is empty, the mapper uses manifest elements directly for Pass 1 matching. This provides richer candidates than file-level-only matching because the manifest includes function/class names, signatures, and FQNs. Pass 2 (LLM) proceeds normally since manifest-sourced candidates have sufficient metadata for semantic ranking.

## Relationship to Code Manifest

The mapper may have both a Code Manifest (`ManifestRegistry` instance, from `context["project_manifests"]`) and Context Bridge output (`context["bridge_context"]`) available simultaneously. These are **complementary, not conflicting** data sources for candidate discovery:

| Dimension | Code Manifest (ManifestRegistry) | Context Bridge (capability_map + project_structure) |
|-----------|--------------------------------|-----------------------------------------------------|
| **Granularity** | Per-element: FQNs, signatures, spans, call graph, symbol table | Per-file/per-service: capability inventory, service dependencies, LOC |
| **Element coverage** | All elements including private functions (`_validate_token`) | Public functions only (CapabilityExtractor skips `_`-prefixed and undocumented) |
| **Mapper usage** | Pass 1 FQN/signature matching + Pass 2 caller context enrichment | Pass 1 name/docstring/path matching + Pass 2 service topology |
| **Output enrichment** | `fqn`, `caller_count` on CandidateComponent | `service_name` on CandidateComponent |
| **Cost** | Zero (in-memory lookup of pre-computed static analysis) | Zero (deterministic transformation) |
| **Availability** | Requires `startd8 manifest generate` or cache from prior run | Requires Eagle + ContextCore installed |

**Design guidelines for the mapper:**
- Prefer `ManifestRegistry` for element-level matching (FQN resolution, signature matching, caller context) — it has deeper analysis and complete coverage
- Prefer `capability_map` for cross-source matching (docstrings, API endpoints, test associations) — it captures metadata from ContextCore's multi-type extraction
- Prefer `project_structure` for service-level matching (service names, service dependencies, file paths) — it provides the macro architecture view
- When both provide overlapping data (e.g., function names), `ManifestRegistry` is authoritative (deeper analysis, complete coverage)
- Both follow the same **graceful degradation** pattern: absent = skip enrichment, no behavioral change. The mapper MUST produce valid `LocalizationCandidates` with any combination of available sources (all three, any two, any one, or none)

## Estimated Effort

~1 day:
- 3 hours: Implement keyword extraction (regex-based, no dependencies)
- 3 hours: Implement lexical matching against capability_map + project_structure
- 2 hours: Implement LLM semantic ranking call (single Anthropic API call)
- 2 hours: Integration with ExplorePhaseHandler, unit tests

## Dependencies

- `anthropic` Python SDK (for Pass 2 LLM call — already a startd8-sdk dependency)
- `re` (standard library, for keyword extraction)
- No new external dependencies

## Relationship to Other Components

```
01_CONTEXT_BRIDGE.md
  → Produces project_structure + capability_map (via context["bridge_context"])
  → Consumed by this mapper as input

Code Manifest (ManifestRegistry)
  → Produces per-element structural data (via context["project_manifests"])
  → Consumed by this mapper as optional enrichment source
  → Provides FQNs, call graph, private function coverage

02_TOOL_USING_PHASE_HANDLER.md
  → Consumes this mapper's output (localization_candidates)
  → Uses candidates to focus the agent loop
  → Also consumes ManifestRegistry directly (query_code_structure tool)

Together:
  Context Bridge ($0, 5s) + Manifest ($0, cached) → Mapper ($0.005, 2s) → Agent Loop ($0.05-0.50, 1-3min)
  Total Explore phase: ~$0.06-0.51, ~1-4 minutes
```

**Context key namespace** (non-overlapping by design):
- `context["bridge_context"]` → Context Bridge output (project_structure, capability_map, codebase_summary)
- `context["project_manifests"]` → Code Manifest output (ManifestRegistry)
- `context["localization_candidates"]` → This mapper's output (consumed by agent loop system prompt)
- `context["localization"]` → EXPLORE phase output (consumed by DESIGN, IMPLEMENT)

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
| R1-F1 | Define a canonical list of component_type values in the feature doc, reconciling the inconsistency between doc and plan. | claude-4 (claude-opus-4-6) | The feature doc says "function", "class", "api", "cli" while the plan adds "test", "file", "service". This inconsistency will cause confusion. A canonical enum in the requirements prevents downstream filtering bugs. Aligns with R1-S7. | 2026-02-20 03:03:37 UTC |
| R1-F2 | Specify the score aggregation strategy (max across tiers, with multi-keyword boost) explicitly in the requirements. | claude-4 (claude-opus-4-6) | The scoring tiers are described but the aggregation method is ambiguous. The plan chose max() but this wasn't specified in requirements. Making this explicit prevents implementer confusion and ensures alignment between spec and implementation. | 2026-02-20 03:03:37 UTC |
| R1-F3 | Reframe the ~8x token reduction claim as illustrative rather than a commitment, and pair it with a benchmark protocol. | claude-4 (claude-opus-4-6) | The 8x figure is based on invented numbers with no empirical backing. Presenting it as a commitment sets unrealistic expectations. Reframing as illustrative with a validation protocol (aligns with R1-S4) is more honest and actionable. | 2026-02-20 03:03:37 UTC |
| R1-F4 | When capability_map is empty, skip Pass 2 (LLM) and return file-level candidates from Pass 1 only. | claude-4 (claude-opus-4-6) | With only file paths and no function/class metadata, the LLM has very low signal for semantic ranking. The $0.005 cost per call is small but the value is near-zero, and the LLM may introduce noise. Skipping Pass 2 in this case is the pragmatic choice. | 2026-02-20 03:03:37 UTC |
| R1-F5 | Specify model selection by capability tier (e.g., cheapest Claude model supporting JSON output) rather than hardcoded model ID, with config override. | claude-4 (claude-opus-4-6) | Both the feature doc and plan hardcode a specific model version ID that is already mismatched between them. Model IDs change frequently. Specifying by capability tier with a config override is future-proof and aligns with R2-F1. | 2026-02-20 03:03:37 UTC |
| R1-F6 | Specify behavior when issue_description is missing from context: skip mapper with a warning rather than silent empty result. | claude-4 (claude-opus-4-6) | The current code uses context.get("issue_description", "") which silently produces an empty string. This leads to an empty candidates result with no indication of why. Explicit handling (warning + skip) is better than silent degradation. | 2026-02-20 03:03:37 UTC |
| R2-F1 | Specify model selection by capability tier rather than hardcoded model ID in the requirements. | gemini-3 (gemini-3-pro-preview) | This is functionally identical to R1-F5 and both should be accepted for the same reason: hardcoded model IDs are fragile and already mismatched between documents. Specifying by capability tier with config override is the correct approach. | 2026-02-20 03:03:37 UTC |
| R1-F1 | Define a canonical enum for component_type values to resolve inconsistencies between feature doc and plan. | claude-4 (claude-opus-4-6) | Inconsistent type values will cause downstream filtering bugs and confusion for implementers. A canonical enum is low-cost and high-value. | 2026-02-20 03:12:04 UTC |
| R1-F2 | Specify that the scoring aggregation strategy is max-across-tiers with a multi-keyword boost. | claude-4 (claude-opus-4-6) | The plan chose max() but the requirement was silent. This ambiguity would cause inconsistent implementations. Already endorsed by a reviewer. | 2026-02-20 03:12:04 UTC |
| R1-F3 | Reframe the 8x token reduction claim as illustrative rather than a commitment, with a benchmark protocol. | claude-4 (claude-opus-4-6) | The numbers are invented and setting them as expectations creates accountability for unvalidated claims. Reframing as illustrative is honest and appropriate. | 2026-02-20 03:12:04 UTC |
| R1-F4 | Specify that if capability_map is empty, skip Pass 2 and return file-level candidates from Pass 1 only. | claude-4 (claude-opus-4-6) | Spending $0.005 on an LLM call with only file paths and no function/class info is wasteful. Clear fallback behavior prevents wasted cost and simplifies implementation. | 2026-02-20 03:12:04 UTC |
| R1-F5 | Specify model selection by capability tier rather than hardcoded model ID, with config override. | claude-4 (claude-opus-4-6) | Hardcoded model IDs are brittle and already show version discrepancies between the feature doc and SDK. This is endorsed by a reviewer and aligns with R2-F1. | 2026-02-20 03:12:04 UTC |
| R1-F6 | Specify that issue_description is a required context key, with clear error or skip behavior if absent. | claude-4 (claude-opus-4-6) | The code uses context.get() with empty string default, which silently degrades. Explicit handling prevents confusing failures. | 2026-02-20 03:12:04 UTC |
| R2-F1 | Require model selection by capability tier (low-latency classification) rather than hardcoded model ID. | gemini-3 (gemini-3-pro-preview) | Directly overlaps with R1-F5. Both identify the same real technical debt risk. Accepting to reinforce the pattern. | 2026-02-20 03:12:04 UTC |
| R3-F1 | Clarify that search_keywords in output is the union of Pass 1 extracted keywords and Pass 2 LLM-suggested keywords, deduplicated. | claude-4 (claude-opus-4-6) | The contradictory definitions (extracted vs. LLM-generated) will confuse implementers. A clear specification prevents ambiguity. | 2026-02-20 03:12:04 UTC |
| R3-F2 | Specify that the 0.4 threshold applies to the final blended score, and consider retaining high-lexical-score candidates regardless. | claude-4 (claude-opus-4-6) | A candidate with strong lexical signal (0.8) but poor LLM score (0.1) would be incorrectly filtered out. This is a real design gap that could cause the mapper to miss obvious matches. | 2026-02-20 03:12:04 UTC |
| R3-F3 | Specify dependency traversal depth limit (1 hop) and maximum service-level candidates for multi-service issues. | claude-4 (claude-opus-4-6) | Unbounded traversal in microservice architectures could include dozens of irrelevant services. A depth limit is a reasonable constraint. | 2026-02-20 03:12:04 UTC |
| R3-F4 | Clarify that the mapper uses its own cheap model selection independent of the phase handler's model. | claude-4 (claude-opus-4-6) | The inconsistency between requirement (model=self.model) and plan (hardcoded Haiku) could lead to accidentally using an expensive model. This overlaps with R1-F5 and R2-F1 but addresses the specific interface issue. | 2026-02-20 03:12:04 UTC |
| R4-F1 | Add constraint that Pass 2 input is limited to top N (e.g., 50) candidates from Pass 1. | gemini-3 (gemini-3-pro-preview) | Without a cap, a generic issue matching 500 files could overflow the context window or cause excessive cost. This is a practical guardrail. | 2026-02-20 03:12:04 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R4-F2 | Add requirement for XML delimiter isolation of user input in prompts. | gemini-3 (gemini-3-pro-preview) | Already covered by R3-S4 which was accepted with more specific guidance (truncation, XML delimiters, escaping). Duplicate. | 2026-02-20 03:12:04 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 03:01:44 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Recommendation |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Output / CandidateComponent | Ambiguity | `component_type` values listed inconsistently: the feature doc says `"function", "class", "api", "cli"` but the plan adds `"test"`, `"file"`, `"service"`. No canonical list exists. | Downstream consumers cannot reliably filter by type. | Define a canonical enum in the feature doc's Output section. |
| R1-F2 | Two-Pass Mapping / Pass 1 Scoring | Missing Detail | Scoring algorithm described at high level ("Name exact match: 1.0, Name substring match: 0.7") but doesn't specify how multiple tiers combine — is it max? sum? weighted? | Implementers will make inconsistent choices. The plan chose `max()` but this wasn't specified in requirements. | Specify aggregation strategy (max across tiers, with multi-keyword boost). |
| R1-F3 | Token Savings | Ambiguity | The "~8x token reduction" claim compares a hypothetical "without mapper" agent (7000 tokens, 6 iterations) to a hypothetical "with mapper" agent (880 tokens, 3 iterations). These are invented numbers, not measured. | Sets unrealistic expectations. Stakeholders may hold the team to 8x savings that were never benchmarked. | Reframe as "expected significant reduction, to be validated" with a benchmark protocol. Provide the example as illustrative, not a commitment. |
| R1-F4 | Edge Cases / No capability_map | Missing Detail | "Fall back to Eagle's project_structure only" — but what does Pass 2 (LLM) receive in this case? File paths with no function/class info is very low signal for semantic ranking. | LLM call may be wasted ($0.005 for near-zero value). | Specify: if capability_map is empty, skip Pass 2 and return file-level candidates from Pass 1 only. |
| R1-F5 | Model Selection | Conflict | Feature doc hardcodes `claude-haiku-4-5-20251001`. Plan §11 Risk 3 notes SDK lists `20251008`. Neither is future-proof. | Brittle to model version changes. | Specify model selection by capability tier (e.g., "cheapest Claude model supporting JSON output") rather than exact model ID. Allow override via config. |
| R1-F6 | Integration with ExplorePhaseHandler | Missing Detail | The feature doc shows the mapper being called inside `execute()` but doesn't specify what happens if `issue_description` is missing from context. | Silent empty result or KeyError crash. | Specify: `issue_description` is a required context key. If absent, raise a clear error or skip the mapper with a warning. |

#### Review Round R2

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 03:02:33 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Issue | Suggested Resolution |
| ---- | ---- | ---- |
| R2-F1 | The Requirement "Pass 2... (Single LLM Call)" implies using a specific model ID (`claude-haiku-4-5-20251001`) in the design text. This creates immediate technical debt if the model version changes. | Update requirement to specify "Low-latency classification model" generally, and allow the implementation to resolve the specific ID via SDK constants. |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 03:09:52 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Recommendation |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Output / LocalizationCandidates | Missing Detail | `search_keywords` is described as "extracted from issue for grep" in the dataclass but in Pass 2's prompt it says "additional terms to grep for" (i.e., LLM-generated terms NOT in the original issue). These are contradictory definitions. | Implementer won't know whether search_keywords should be the Pass 1 extracted keywords, the Pass 2 LLM-suggested keywords, or both merged. The plan (§6) blends them but the requirement is ambiguous. | Clarify: `search_keywords` in the output is the union of Pass 1 extracted keywords and Pass 2 LLM-suggested additional keywords, deduplicated. |
| R3-F2 | Design / Two-Pass Mapping | Missing Detail | The requirement specifies a 0.4 relevance_score threshold for filtering (`[c for c in ranked.candidates if c.relevance_score >= 0.4]`) but doesn't specify whether this applies to the lexical score, LLM score, or blended score. | The plan uses blended score (0.4 lexical + 0.6 LLM) but the requirement's threshold predates the blending specification. A candidate with lexical=0.8 and LLM=0.1 gets blended=0.38 and is filtered out despite strong lexical signal. | Specify that the 0.4 threshold applies to the final blended score, and consider whether candidates with high lexical score (≥0.8) should be retained regardless of LLM score (to avoid LLM errors filtering out strong lexical matches). |
| R3-F3 | Edge Cases / Multi-service issue | Ambiguity | The requirement says "Payment fails when email notification service is down" and describes using Eagle's dependency map, but doesn't specify how deep to traverse dependencies. Should transitive dependencies (A→B→C) be included? | In a large microservice architecture, dependency traversal without depth limits could include dozens of irrelevant services, overwhelming the candidate list. | Specify dependency traversal depth limit (recommend: 1 hop direct dependencies only) and maximum number of service-level candidates. |
| R3-F4 | Integration with ExplorePhaseHandler | Missing Detail | The requirement shows `mapper.map(issue_description=context["issue_description"], model=self.model)` but the plan (§8) uses `context.get("issue_description", "")`. The requirement implies `self.model` is passed (the phase handler's model), but the plan hardcodes `"claude-haiku-4-5-20251001"`. Which model should be used? | If the phase handler's model is used, the mapper might use Opus ($0.50+) for a ranking task that only needs Haiku ($0.005). If Haiku is hardcoded, the requirement's `model=self.model` parameter is misleading. | Clarify that the mapper uses its own model selection (cheap classification model) independent of the phase handler's model, with a configurable override. The requirement's `model=self.model` should be removed or changed to `model=mapper_model`. |

#### Review Round R4

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 03:11:00 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Recommendation |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Pass 2: LLM Semantic Ranking | Missing Constraint | The requirement "One focused LLM call... to refine the lexical matches" implies unbounded input. If Pass 1 returns 500 matches, the single LLM call will be massive/expensive. | Potential for context window overflow or excessive cost per issue. | Add constraint: "Pass 2 input is limited to the top N (e.g., 50) candidates from Pass 1." |
| R4-F2 | Design / Input | Security Gap | The `issue_description` is user-provided and untrusted. The requirements do not specify sanitization or prompting defenses against injection. | Malicious users could inject instructions to override the ranking logic. | Add requirement: "System prompt must use delimiters (e.g., XML tags) to isolate user input from instructions." |

