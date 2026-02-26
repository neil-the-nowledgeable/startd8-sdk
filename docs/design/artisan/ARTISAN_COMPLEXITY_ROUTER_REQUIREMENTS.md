# Complexity-Driven Model Router (CMR) -- Requirements

**Version:** 0.1.0
**Created:** 2026-02-25
**Status:** Draft
**Tracking prefix:** REQ-CMR

## Overview

Route each IMPLEMENT task to a model tier based on manifest-derived complexity signals, saving cost on simple tasks and improving quality on complex ones.

The Artisan IMPLEMENT phase currently uses a fixed 2-tier model: Haiku (T1 drafter) generates code unconditionally, then Sonnet (T2 refiner) rewrites it -- regardless of task complexity. The code manifest system (Phases 1-6) already produces per-task complexity signals that are currently used only for prompt context.

## Tier Definitions

### Tier 1 -- Haiku only (no T2)

ALL conditions must be true:

- `blast_radius == 0`
- `edit_mode == "create"`
- `caller_count == 0`
- `has_dynamic_dispatch == False`
- `estimated_loc < 150`
- Single target file
- Manifest call graph data present (confidence guard)

### Tier 2 -- Haiku + T2 (default)

Everything that is not Tier 1 or Tier 3. Matches current behavior.

### Tier 3 -- Opus as T1 drafter

ANY condition triggers:

- `blast_radius > 5`
- `has_dynamic_dispatch == True`
- `caller_count > 3` in edit mode
- `mro_depth > 3` (when Phase 5 data available)
- `unresolved_call_count > 2`
- `estimated_loc > 500`
- Multiple target files with cross-file call edges

## Requirements

### Layer 0: Data Model

**REQ-CMR-000: TaskComplexityTier Enum** [P0]

`str` enum with values `TIER_1`, `TIER_2`, `TIER_3`. Default `TIER_2` (matches current behavior). Located in `development.py` alongside `ChunkStatus`.

**REQ-CMR-001: TaskComplexitySignals Dataclass** [P0]

Frozen dataclass with fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `blast_radius` | `int` | `0` | Transitive caller count from manifest |
| `caller_count` | `int` | `0` | Direct (1-hop) callers |
| `has_dynamic_dispatch` | `bool` | `False` | Any `getattr()`/dynamic attribute access |
| `is_closure` | `bool` | `False` | Function defined inside another function |
| `estimated_loc` | `int` | `0` | Lines of code estimate from seed task |
| `target_file_count` | `int` | `1` | Number of target files |
| `edit_mode` | `str` | `"unknown"` | `"create"` / `"edit"` / `"unknown"` |
| `mro_depth` | `int` | `0` | Method resolution order depth (Phase 5) |
| `unresolved_call_count` | `int` | `0` | Calls to unresolved targets |
| `has_cross_file_edges` | `bool` | `False` | Cross-file call edges among target files |

All primitive types. Safe defaults classify as TIER_2. Includes `to_dict()` for JSON serialization.

**REQ-CMR-002: Chunk Metadata Contract** [P0]

Two new metadata keys per chunk:

- `_complexity_tier` (str): The tier classification result
- `_complexity_signals` (dict): Full signal snapshot for forensics

Set during enrichment loop after call graph enrichment. Default `"tier_2"` when absent (backward compatible).

**REQ-CMR-003: HandlerConfig Extensions** [P0]

New fields on `HandlerConfig`:

| Field | Type | Default | Description |
|---|---|---|---|
| `complexity_routing_enabled` | `bool` | `True` | Kill switch |
| `tier3_agent` | `Optional[str]` | `None` -> `REVIEW_MODEL_CLAUDE_OPUS.agent_spec` | Opus drafter spec |
| `complexity_blast_radius_tier3` | `int` | `5` | Blast radius threshold for Tier 3 |
| `complexity_loc_tier1_max` | `int` | `150` | Max LOC for Tier 1 eligibility |
| `complexity_loc_tier3_min` | `int` | `500` | Min LOC to trigger Tier 3 |
| `complexity_caller_tier3` | `int` | `3` | Caller count threshold for Tier 3 in edit mode |

All participate in `from_config()` priority chain.

### Layer 1: Classification

**REQ-CMR-010: Signal Extraction** [P0]

Function: `_extract_complexity_signals(chunk, manifest_registry) -> TaskComplexitySignals`

- Reads from existing enrichment data (`_call_graph_callers`, `_edit_mode`, `estimated_loc`)
- Queries registry for `has_dynamic_dispatch`, `is_closure`, `unresolved_calls`, `mro_depth`
- Never raises -- all lookups wrapped in try/except

**REQ-CMR-011: Tier Classification** [P0]

Function: `_classify_complexity_tier(signals, config) -> TaskComplexityTier`

- Pure function, stateless, deterministic
- Tier 3 triggers checked first (any one triggers)
- Then Tier 1 eligibility (all must pass)
- Default Tier 2
- Thresholds read from config, not hardcoded

**REQ-CMR-012: Enrichment Loop Integration** [P0]

Classification runs after Phase 6 call graph enrichment, before executor construction. Summary log: `"CMR: T1=%d, T2=%d, T3=%d across %d chunks"`.

**REQ-CMR-013: Tier 1 Confidence Guard** [P1]

Tier 1 only assigned when manifest call graph data is actually present. `blast_radius == 0` because manifest was unavailable -> stays Tier 2. `_complexity_signals` includes `manifest_coverage: "full"|"partial"|"none"`.

**REQ-CMR-014: Unknown Edit Mode Handling** [P1]

`edit_mode == "unknown"` disqualifies from Tier 1 (treated as "edit"). Does NOT trigger Tier 3's `caller_count > 3 in edit mode` rule.

### Layer 2: Routing

**REQ-CMR-020: Per-Chunk T2 Skip (Tier 1)** [P0]

In `ArtisanChunkExecutor.execute()`, check `_complexity_tier`:

- Tier 1: skip T2 refinement
- Tier 2 and Tier 3: run T2 as before
- When `_complexity_tier` absent: default to `"tier_2"` (backward compatible)

**REQ-CMR-021: Per-Chunk Drafter Override (Tier 3)** [P1]

Executor accepts `tier3_drafter_spec` parameter. Tier 3 chunks use Opus as T1 drafter via lazy-cached agent resolution. Cost metrics reflect actual model used.

**REQ-CMR-022: Gate-Driven T2 Escalation** [P2]

Future: Tier 2 initially skips T2, runs it only when gates flag issues. Bounded: max 1 T2 retry per chunk.

**REQ-CMR-023: Executor Construction Update** [P0]

Pass `tier3_drafter_spec=self.config.tier3_agent` to executor. Existing tests unaffected (parameter defaults to None).

**REQ-CMR-024: Walkthrough Mode Support** [P1]

Walkthrough output includes `complexity_tier`, `complexity_signals`, `effective_drafter`.

**REQ-CMR-025: Resume Cache Compatibility** [P0]

`_complexity_tier` and `_complexity_signals` are NOT part of cache key. Pre-CMR cached results load with default `"tier_2"`.

### Layer 3: Observability

**REQ-CMR-030: Per-Chunk Tier Logging** [P0]

- INFO log per chunk: tier + key signal values
- Summary log after classification: tier distribution
- Execute-time log: actual model + T2 decision

**REQ-CMR-031: OTel Span Attributes** [P1]

Attributes on `implement.chunk` span:

- `task.complexity_tier`
- `task.blast_radius`
- `task.caller_count`
- `task.has_dynamic_dispatch`

**REQ-CMR-032: Forensic Log Extension** [P0]

- `complexity_tier` in `call` dict
- `complexity_signals` in `task` dict
- T2 forensic log records whether T2 was skipped vs. run

**REQ-CMR-033: Phase Output Metadata** [P1]

`_tier_distribution: {tier_1: N, tier_2: N, tier_3: N}` in implementation metadata. Per-task reports include `complexity_tier`.

**REQ-CMR-034: Degradation Reason Code** [P1]

`COMPLEXITY_MANIFEST_MISSING` in `DegradationReasons`.

### Layer 4: Configuration

**REQ-CMR-040: CLI Arguments** [P1]

`--complexity-routing / --no-complexity-routing`, `--tier3-agent SPEC`, threshold override flags.

**REQ-CMR-041: Config File Support** [P2]

All CMR fields readable from artisan config YAML.

**REQ-CMR-042: Per-Task Override via Seed** [P2]

Optional `complexity_tier_override` in seed task JSON.

**REQ-CMR-043: Contract YAML Extension** [P1]

IMPLEMENT exit: `_complexity_tier` optional field in artisan-pipeline.contract.yaml.

## Graceful Degradation

| Condition | Behavior |
|---|---|
| `ManifestRegistry` is `None` | All chunks -> Tier 2 |
| Call graph unavailable | Tier 1 blocked by confidence guard -> Tier 2 |
| Phase 5 data unavailable | MRO rule skipped |
| `edit_mode` missing | Treated as "unknown" -> blocked from Tier 1 |
| `complexity_routing_enabled=False` | All chunks -> Tier 2 |
| Pre-CMR cached results loaded | Default `"tier_2"` |

## Files Modified

| File | Changes |
|---|---|
| `src/startd8/contractors/artisan_phases/development.py` | `TaskComplexityTier` enum, `TaskComplexitySignals` dataclass, per-chunk T2 skip, per-chunk drafter override, forensic log extension |
| `src/startd8/contractors/context_seed_handlers.py` | `HandlerConfig` extensions, `_extract_complexity_signals()`, `_classify_complexity_tier()`, enrichment loop integration, executor construction update |
| `src/startd8/otel_conventions.py` | 4 new OTel attribute keys, 1 degradation reason code |
| `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml` | IMPLEMENT exit: `_complexity_tier` optional field |
| `tests/unit/contractors/test_complexity_router.py` | Unit tests for classification, signal extraction, routing |

## Open Questions

1. **Threshold calibration**: blast_radius > 5, LOC > 500, etc. are domain intuition. After 10+ runs, analyze correlation between tier, gate failure rate, and review scores to tune.
2. **Dynamic dispatch false positives**: `has_dynamic_dispatch` flags any `getattr()` including benign cases. Start with boolean (P0), consider count threshold in P2.
3. **Tier 3 T2**: Should Tier 3 (Opus as T1) also run T2? Initially yes, but consider `tier3_skip_t2` flag in P2.
