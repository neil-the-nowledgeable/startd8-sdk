# Gap Bridge Priority 3: ManifestDiff INTEGRATE + Code Review Skill Call Graph

**Version:** 1.0.0
**Created:** 2026-02-26
**Status:** Draft
**Parent:** [ARTISAN_FEATURE_COVERAGE_GAP_ANALYSIS.md](ARTISAN_FEATURE_COVERAGE_GAP_ANALYSIS.md)
**Extends:** [CODE_MANIFEST_PHASE6_PIPELINE_REQUIREMENTS.md](../CODE_MANIFEST_PHASE6_PIPELINE_REQUIREMENTS.md)
**Dependencies:** [GAP_BRIDGE_PRIORITY_2_REQUIREMENTS.md](GAP_BRIDGE_PRIORITY_2_REQUIREMENTS.md) — `ManifestDiff` extensions from §3 must be implemented first.

---

## 1. Goal

Two remaining gaps from the Artisan feature coverage audit require work after the Priority 1 and Priority 2 foundations are in place:

1. **Type-aware INTEGRATE phase** — Wire `ManifestDiff.changed_resolved_signatures` and `ManifestDiff.mro_changes` into `IntegrationEngine._manifest_pre_merge_diff()` to catch type-level breaking changes invisible to AST diff.
2. **Code Review skill — call graph context** — Extend the `/code-review` skill to load and surface `ManifestRegistry` call graph data per reviewed function.

---

## 2. GAP3-A: Type-Aware INTEGRATE Phase

### 2.1 Problem

`IntegrationEngine._manifest_pre_merge_diff()` currently compares manifests structurally (removed
elements, element count regression). It does not detect:

- A function's *resolved* parameter type changed (`int → str` after decorator evaluation), even
  when the AST signature string is identical.
- A class's MRO changed (inheritance restructuring), even when the class name and direct base
  classes appear unchanged.
- `__all__` additions/removals.

These represent real breaking changes invisible to the current structural AST diff.

**Dependencies:** `ManifestDiff.changed_resolved_signatures`, `ManifestDiff.mro_changes`, and
`ManifestDiff.module_all_diff` from Priority 2 (§3) must be implemented first.

### 2.2 Requirements

#### REQ-GAP3-A-001: Resolved Signature Change Detection in INTEGRATE (IN-1)

**Requirement:** After computing `ManifestDiff.diff()` in `_manifest_pre_merge_diff()`, iterate
over `diff.changed_resolved_signatures`. For each entry where `old_resolved != new_resolved`,
log a WARNING.

**Implementation:**

```python
# IN-1: Resolved signature changes (type-level breaking changes)
for fqn, old_sig, new_sig in diff.changed_resolved_signatures:
    logger.warning(
        "INTEGRATE IN-1: Resolved type change detected for %s: %r → %r",
        fqn, old_sig, new_sig,
    )
    if manifest_registry and manifest_registry.callers_of(fqn):
        # Escalate if callers exist (cross-reference with CG-IN-1)
        logger.error(
            "INTEGRATE IN-1: %s has callers; type change may break callers.",
            fqn,
        )
```

**File:** `src/startd8/contractors/integration_engine.py` — `_manifest_pre_merge_diff()`

#### REQ-GAP3-A-002: MRO Change Detection in INTEGRATE (IN-2)

**Requirement:** When `diff.mro_changes` is non-empty, emit WARNING via `GateEmitter` for each changed class.

**Implementation:**

```python
# IN-2: MRO changes (inheritance restructuring)
for fqn, old_mro, new_mro in diff.mro_changes:
    added = set(new_mro) - set(old_mro)
    removed = set(old_mro) - set(new_mro)
    logger.warning(
        "INTEGRATE IN-2: MRO changed for %s — added: %s, removed: %s",
        fqn, added or "none", removed or "none",
    )
    # Emit via GateEmitter if available
    if gate_emitter:
        gate_emitter.emit(
            gate_name="manifest_mro_change",
            severity="WARNING",
            message=f"MRO changed for {fqn}",
            metadata={"fqn": fqn, "old_mro": old_mro, "new_mro": new_mro},
        )
```

**File:** `src/startd8/contractors/integration_engine.py` — `_manifest_pre_merge_diff()`

#### REQ-GAP3-A-003: `module_all` Change Logging in INTEGRATE (IN-3)

**Requirement:** When `diff.module_all_diff` is not `None`, log added/removed exports at INFO.

**Implementation:**

```python
# IN-3: __all__ changes
if diff.module_all_diff is not None:
    added, removed = diff.module_all_diff
    if added:
        logger.info("INTEGRATE IN-3: New exports in __all__: %s", added)
    if removed:
        logger.info(
            "INTEGRATE IN-3: Removed exports from __all__: %s "
            "(may break 'from module import *' consumers)",
            removed,
        )
```

**File:** `src/startd8/contractors/integration_engine.py` — `_manifest_pre_merge_diff()`

#### REQ-GAP3-A-004: Graceful Degradation (IN-4)

**Requirement:** All IN-1, IN-2, IN-3 logic is gated on introspect data availability. When either
manifest lacks `inspect_info` or `module_all`, the corresponding check is skipped.
The existing structural manifest diff (Phase 4 IN-1 through IN-3) and call graph diff (Phase 6
CG-IN-1 through CG-IN-4) continue unchanged.

---

## 3. GAP3-B: Code Review Skill — Call Graph Context

### 3.1 Problem

The `/code-review` skill operates on raw source code without any `ManifestRegistry` context.
It cannot know:

- Which reviewed functions are called by many other functions (deserving more scrutiny).
- Which are dead code candidates (zero known callers).
- Whether reviewed functions have unresolved call targets (dynamic dispatch warnings).

This matches `CG-CR-1` through `CG-CR-5` from the Phase 6 pipeline requirements.

### 3.2 Requirements

#### REQ-GAP3-B-001: Call Graph Context Loading (CG-CR-1)

**Requirement:** The code review skill must accept an optional `manifest_registry` parameter.
When provided, load call graph data for the reviewed files using `callers_of()` and
`blast_radius()`.

**Implementation:**

- Add an optional `registry: ManifestRegistry | None = None` parameter to the skill's main
  review function.
- When `registry` is provided and elements have call graph data, build per-element annotations:

  ```
  {fqn}: called by {N} known callers, blast radius {R} (depth=3)
  ```

- Pass these annotations into the review prompt as a `## Call Graph Context` section.

**File:** The relevant code review skill file (check `src/startd8/skills/` or `.agents/skills/`).

#### REQ-GAP3-B-002: Impact-Proportional Review Focus (CG-CR-2)

**Requirement:** Annotate each reviewed function with its blast radius. Instruct the reviewer
to apply proportional scrutiny.

**Prompt injection format:**

```
## Call Graph Context

The following functions in this file have known callers. Apply review scrutiny proportional
to blast radius:

| Function | Direct Callers | Blast Radius (depth=3) |
|----------|---------------|------------------------|
| process_order() | 8 | 34 |
| get_config() | 2 | 6 |
| _internal_helper() | 0 | 0 |
```

**Instruction to LLM:**

```
Functions with higher blast radius carry more risk — focus your review on backward compatibility,
error handling, and type correctness for functions with radius > 10.
```

#### REQ-GAP3-B-003: Dead Code Detection Finding (CG-CR-3)

**Requirement:** When `dead_candidates()` returns FQNs that match reviewed functions, include them
as a review finding under `category="maintainability"`.

**Format:**

```
### 🔍 Dead Code Candidates
The following functions have no known callers. Verify they are intentionally public:
- `_old_pipeline()` — 0 callers, no references found
```

#### REQ-GAP3-B-004: Unresolved Call Advisory (CG-CR-4)

**Requirement:** When a reviewed function has `call_graph.unresolved_calls` non-empty, include
an advisory that the function uses dynamic dispatch and its full call surface is unknown.

**Format:**

```
### ⚠ Dynamic Dispatch Warning
`fetch_handler()` uses `getattr()` / dynamic dispatch. The call graph is a lower bound —
additional runtime calls may not be captured. Manual review of dynamic call targets is needed.
```

#### REQ-GAP3-B-005: Graceful Degradation (CG-CR-5)

**Requirement:** When `manifest_registry` is not provided or elements lack call graph data,
the skill operates identically to its current behavior.

---

## 4. Proposed Changes Summary

| File | Change | Section |
|------|--------|---------|
| `src/startd8/contractors/integration_engine.py` | Add IN-1, IN-2, IN-3, IN-4 logic to `_manifest_pre_merge_diff()` | §2.2 |
| Code review skill file | Add `registry` parameter, `## Call Graph Context` section, dead code + dynamic dispatch findings | §3.2 |

---

## 5. Ordering Dependency

```
Priority 2 (§3): ManifestDiff.changed_resolved_signatures + mro_changes + module_all_diff
        ↓
Priority 3 GAP3-A: IntegrationEngine wires ManifestDiff extensions
```

`GAP3-A` cannot be implemented until the `ManifestDiff` extensions from Priority 2 are merged.
`GAP3-B` (code review skill) is independent of both and can be implemented at any time.

---

## 6. Verification Plan

### GAP3-A Verification

1. **Unit IN-1** — `ManifestDiff.diff()` with matching AST signatures but differing resolved
   types. Assert `INTEGRATE IN-1` WARNING log with `old_resolved` and `new_resolved`.
2. **Unit IN-2** — Class with changed MRO. Assert WARNING log + `GateEmitter` event with
   `gate_name="manifest_mro_change"`.
3. **Unit IN-3** — `FileManifest` with `module_all` that has an added name. Assert INFO log
   with the added name.
4. **Regression IN-4** — `mode="static"` manifests (no `inspect_info`). Assert all IN-1/2/3
   logic is skipped, existing structural diff continues unchanged.

### GAP3-B Verification

1. **Unit CG-CR-1,2** — Call skill with mock `registry`, file with elements having callers.
   Assert `## Call Graph Context` section in review prompt with blast radius table.
2. **Unit CG-CR-3** — Element with 0 callers in `dead_candidates()`. Assert dead code finding
   in review output.
3. **Unit CG-CR-4** — Element with non-empty `unresolved_calls`. Assert dynamic dispatch advisory.
4. **Regression CG-CR-5** — Call skill without `registry`. Assert identical output to current behavior.
