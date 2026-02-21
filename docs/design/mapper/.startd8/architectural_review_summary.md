# Architectural Review Summary

**Document**: 03_ISSUE_TO_LOCALIZATION_MAPPER_PLAN.md
**Feature Requirements**: 03_ISSUE_TO_LOCALIZATION_MAPPER.md
**Generated**: 2026-02-20 03:12:04 UTC

## Metrics

| Metric | Value |
|--------|-------|
| Review rounds | 2 |
| Reviewers | claude-4:claude-opus-4-6, gemini-3:gemini-3-pro-preview |
| Total cost | $0.3255 |
| Plan suggestions | 26 accepted, 7 rejected |
| Feature suggestions | 12 accepted, 1 rejected |
| Untriaged remaining | 0 |

## Area Coverage

| Area | Status | Applied IDs |
|------|--------|-------------|
| architecture | Addressed | R1-S3, R2-S1, R2-S5 |
| data | Addressed | R1-S7, R2-S2, R2-S6 |
| interfaces | Addressed | R1-S1, R1-S10, R3-S1, R3-S2 |
| ops | Addressed | R1-S8, R2-S3, R3-S8, R4-S5 |
| risks | Addressed | R1-S2, R1-S9, R3-S6, R4-S6, R4-S9 |
| security | Addressed | R1-S5, R3-S4, R3-S5, R3-S9 |
| validation | Addressed | R1-S4, R2-S4, R3-S7, R3-S10, R4-S10 |

## Applied Suggestions (Plan)

| ID | Summary | Source |
|----|---------|--------|
| R1-S1 | Define explicit shared schema types for capability_map and project_structure in a shared schemas.py file. | claude-4 (claude-opus-4-6) |
| R1-S2 | Add a concrete fallback for private functions that CapabilityExtractor skips, rather than relying on unverified assumptions about by_file index. | claude-4 (claude-opus-4-6) |
| R1-S3 | Make the 0.4/0.6 lexical/LLM score blending ratio configurable rather than hardcoded, with adaptive logic as a stretch goal. | claude-4 (claude-opus-4-6) |
| R1-S4 | Define a validation protocol with acceptance criteria (recall@k, MRR) and a benchmark set of real issues with known fault files. | claude-4 (claude-opus-4-6) |
| R1-S5 | Sanitize raw issue text before injecting into LLM prompts to mitigate prompt injection attacks. | claude-4 (claude-opus-4-6) |
| R1-S7 | Constrain component_type to a Literal type or StrEnum instead of free-form strings. | claude-4 (claude-opus-4-6) |
| R1-S8 | Add structured logging for each pass (keyword count, candidate count, scores, latency, LLM token usage). | claude-4 (claude-opus-4-6) |
| R1-S9 | Add a guard to skip the mapper entirely when both capability_map and project_structure are empty, setting candidates to None. | claude-4 (claude-opus-4-6) |
| R1-S10 | Define a formal schema (Pydantic model or validated TypedDict) for the LLM's JSON response and validate/coerce scores. | claude-4 (claude-opus-4-6) |
| R2-S1 | Inject the LLM client or a factory into the mapper instead of directly instantiating Anthropic(). | gemini-3 (gemini-3-pro-preview) |
| R2-S2 | Add specialized stack trace parsing to extract file paths and line numbers from structured stack trace formats. | gemini-3 (gemini-3-pro-preview) |
| R2-S3 | Enforce token/length limits on candidate descriptions sent to Pass 2 to control LLM cost and latency. | gemini-3 (gemini-3-pro-preview) |
| R2-S4 | Create a golden set retrieval benchmark script to measure recall@K against known historical bug/fix pairs. | gemini-3 (gemini-3-pro-preview) |
| R2-S5 | Externalize scoring thresholds and weights into a configuration dataclass. | gemini-3 (gemini-3-pro-preview) |
| R2-S6 | Formalize the file-only fallback strategy with explicit logic to convert project_structure files into CandidateComponent objects. | gemini-3 (gemini-3-pro-preview) |
| R3-S1 | Define a Protocol/ABC for the mapper interface to enable dependency injection and testability. | claude-4 (claude-opus-4-6) |
| R3-S2 | Specify the exact JSON schema for Pass 2's LLM response including field types, required/optional fields, and examples. | claude-4 (claude-opus-4-6) |
| R3-S3 | Add structured logging and observability for both passes including timing, candidate counts, and correlation IDs. | claude-4 (claude-opus-4-6) |
| R3-S4 | Sanitize issue_description before LLM prompt injection, using truncation, XML delimiters, and escaping. | claude-4 (claude-opus-4-6) |
| R3-S5 | Validate and sanitize file_path values in CandidateComponent to prevent path traversal attacks. | claude-4 (claude-opus-4-6) |
| R3-S6 | Specify a concrete fallback when Pass 1 produces zero or very few candidates for natural-language-only issues. | claude-4 (claude-opus-4-6) |
| R3-S7 | Add a benchmark harness measuring recall@k and precision@k against curated (issue, expected_files) pairs. | claude-4 (claude-opus-4-6) |
| R3-S8 | Define a 10-second timeout and circuit-breaker for the Pass 2 LLM call to prevent unbounded latency. | claude-4 (claude-opus-4-6) |
| R3-S9 | Validate all parsed fields from LLM response against expected types and ranges before incorporating into output. | claude-4 (claude-opus-4-6) |
| R3-S10 | Add contract tests verifying the mapper's expected input schema matches the Context Bridge's actual output schema. | claude-4 (claude-opus-4-6) |
| R4-S5 | Externalize scoring weights, thresholds, and limits to a MapperConfig class or environment variables. | gemini-3 (gemini-3-pro-preview) |
| R4-S6 | Implement a token budget guardrail (max input tokens) before calling the LLM in Pass 2. | gemini-3 (gemini-3-pro-preview) |
| R4-S9 | Use AsyncAnthropic client or thread executor if the host application environment is async. | gemini-3 (gemini-3-pro-preview) |
| R4-S10 | Ensure dry_run returns a fully populated mock LocalizationCandidates object, not None. | gemini-3 (gemini-3-pro-preview) |

## Applied Suggestions (Feature Requirements)

| ID | Summary | Source |
|----|---------|--------|
| R1-F1 | Define a canonical list of component_type values in the feature doc, reconciling the inconsistency between doc and plan. | claude-4 (claude-opus-4-6) |
| R1-F2 | Specify the score aggregation strategy (max across tiers, with multi-keyword boost) explicitly in the requirements. | claude-4 (claude-opus-4-6) |
| R1-F3 | Reframe the ~8x token reduction claim as illustrative rather than a commitment, and pair it with a benchmark protocol. | claude-4 (claude-opus-4-6) |
| R1-F4 | When capability_map is empty, skip Pass 2 (LLM) and return file-level candidates from Pass 1 only. | claude-4 (claude-opus-4-6) |
| R1-F5 | Specify model selection by capability tier (e.g., cheapest Claude model supporting JSON output) rather than hardcoded model ID, with config override. | claude-4 (claude-opus-4-6) |
| R1-F6 | Specify behavior when issue_description is missing from context: skip mapper with a warning rather than silent empty result. | claude-4 (claude-opus-4-6) |
| R2-F1 | Specify model selection by capability tier rather than hardcoded model ID in the requirements. | gemini-3 (gemini-3-pro-preview) |
| R1-F1 | Define a canonical enum for component_type values to resolve inconsistencies between feature doc and plan. | claude-4 (claude-opus-4-6) |
| R1-F2 | Specify that the scoring aggregation strategy is max-across-tiers with a multi-keyword boost. | claude-4 (claude-opus-4-6) |
| R1-F3 | Reframe the 8x token reduction claim as illustrative rather than a commitment, with a benchmark protocol. | claude-4 (claude-opus-4-6) |
| R1-F4 | Specify that if capability_map is empty, skip Pass 2 and return file-level candidates from Pass 1 only. | claude-4 (claude-opus-4-6) |
| R1-F5 | Specify model selection by capability tier rather than hardcoded model ID, with config override. | claude-4 (claude-opus-4-6) |
| R1-F6 | Specify that issue_description is a required context key, with clear error or skip behavior if absent. | claude-4 (claude-opus-4-6) |
| R2-F1 | Require model selection by capability tier (low-latency classification) rather than hardcoded model ID. | gemini-3 (gemini-3-pro-preview) |
| R3-F1 | Clarify that search_keywords in output is the union of Pass 1 extracted keywords and Pass 2 LLM-suggested keywords, deduplicated. | claude-4 (claude-opus-4-6) |
| R3-F2 | Specify that the 0.4 threshold applies to the final blended score, and consider retaining high-lexical-score candidates regardless. | claude-4 (claude-opus-4-6) |
| R3-F3 | Specify dependency traversal depth limit (1 hop) and maximum service-level candidates for multi-service issues. | claude-4 (claude-opus-4-6) |
| R3-F4 | Clarify that the mapper uses its own cheap model selection independent of the phase handler's model. | claude-4 (claude-opus-4-6) |
| R4-F1 | Add constraint that Pass 2 input is limited to top N (e.g., 50) candidates from Pass 1. | gemini-3 (gemini-3-pro-preview) |

## Rejected Suggestions

| ID | Summary | Rationale |
|----|---------|-----------|
| R1-S6 | Add pre-indexing and caching for the lexical matcher to avoid re-traversing capability_map on each call. | The mapper is called once per issue at the start of the explore phase, not repeatedly in a loop. For a single invocation, O(keywords × entries) on even 1000+ entries is likely sub-100ms without indexing. This is premature optimization for a component that isn't yet built. Can be revisited if profiling shows a bottleneck. |
| R4-S1 | Wrap issue_description in XML tags in the system prompt to prevent prompt injection. | Already covered by R3-S4 which was accepted with broader scope (truncation + XML delimiters + escaping). Duplicate. |
| R4-S2 | Implement strict path canonicalization and allowlist validation for file_path. | Already covered by R3-S5 which was accepted with equivalent scope. Duplicate. |
| R4-S3 | Create benchmark script to evaluate Recall@k against a golden set of historical issues. | Already covered by R3-S7 which was accepted with more detailed specification (curated fixtures, recall@5/10, MRR, regression tracking). Duplicate. |
| R4-S4 | Define strict InputSchema TypedDict for capability_map and validate inputs at init. | Already covered by R3-S10 (contract tests) and the previously applied R2-S3/R2-S4 suggestions. The schema validation concern is addressed. |
| R4-S7 | Add likely_root_cause field to LocalizationCandidates populated from LLM response. | Low severity, and the existing 'reasoning' field already captures the LLM's explanation. Adding a separate root cause field adds schema complexity for marginal value at this stage. Can be added later based on agent loop needs. |
| R4-S8 | Implement structured logging recording lexical_score, llm_score, and final_score per candidate. | Already covered by R3-S3 which was accepted with broader scope (timing, candidate counts, correlation IDs, score distributions). Duplicate. |
