# Code Manifest Phase 5: DESIGN Phase Integration Requirements

**Status:** Draft
**Date:** 2026-02-24
**Author:** Neil Yashinsky + agent:claude-code
**Parent:** [CODE_MANIFEST_PHASE4_REQUIREMENTS.md](CODE_MANIFEST_PHASE4_REQUIREMENTS.md) (extends Phase 4 with DESIGN-specific integration)
**Implements:** Manifest-backed structural awareness for the DESIGN phase across 5 integration surfaces

---

## 1. Objective

Wire AST-based code manifests into the DESIGN phase of the Artisan pipeline, giving the design LLM structural ground truth about target files. Phase 4 integrated manifests into IMPLEMENT, INTEGRATE, Preflight, Plan Ingestion, Capability Index, and Context Threading — but **completely omitted the DESIGN phase**. This is a critical gap because:

- **DESIGN decides modification scope** but doesn't know what's in the target files. The LLM invents element names, references non-existent APIs, and proposes modifications to files whose structure it cannot see.
- **IMPLEMENT receives vague designs and interprets loosely**, leading to full-file overwrites instead of surgical edits (Lesson 13 #29: LLM complete-file overwrite).
- **Designs reference non-existent elements** due to staleness when target files have changed since the plan was written (Lesson 13 #28: feature-serial design staleness).
- **The dual-review pipeline (Reviewer + Arbiter) has no structural ground truth** to validate element references against, so reviews cannot catch phantom-element errors.

The IMPLEMENT phase already has a working manifest integration pattern (`context_seed_handlers.py` lines 5658–5680) that reads `ManifestRegistry` from context and injects `file_element_summary()` per chunk. The DESIGN phase needs an analogous but purpose-specific integration: manifest data flows into design prompts (system, user, reviewer, arbiter) so the LLM produces designs that are structurally grounded.

Five integration surfaces consume manifests in the DESIGN phase:

1. **Context Seed Assembly** — `ManifestRegistry` read + per-task element injection
2. **Design System Prompt** — structural awareness instructions
3. **Design User Prompt** — `{manifest_context}` placeholder with file summaries
4. **Design Review / Arbiter Prompts** — structural validation instructions
5. **Edit-Mode Block Enhancement** — structural file context replacing path-only listings

---

## 2. Integration Architecture Overview

### 2.1 Data Flow

```
ManifestRegistry              DesignPhaseHandler           Design Prompts
(from Phase 4 CT-1)          (context_seed_handlers.py)   (design.yaml / v2 modules)
──────────────────   read    ─────────────────────────     ───────────────────────────
context["project_   ───────► file_element_summary()  ──►  {manifest_context} in user
  manifests"]                 dependency_graph()      ──►  {manifest_context} in user
                              ManifestDiff.diff()     ──►  edit-mode structural diff
                              public_element_count()  ──►  review structural criteria
```

### 2.2 Established Pattern (IMPLEMENT)

The IMPLEMENT phase manifest integration (`context_seed_handlers.py` lines 5658–5680) serves as the reference pattern:

```python
# Phase 4: Enrich chunks with manifest context (IM-1 through IM-4)
_manifest_registry = None
if self.config.manifest_consumption_enabled:
    _manifest_registry = self.config.manifest_registry or context.get("project_manifests")
if _manifest_registry is not None:
    _manifest_budget = self.config.manifest_context_budget
    for chunk in chunks:
        _mc_parts = []
        for tf in getattr(chunk, "target_files", []):
            summary = _manifest_registry.file_element_summary(tf, _manifest_budget)
            if summary:
                _mc_parts.append(f"### {tf}\n{summary}")
        if _mc_parts:
            chunk.metadata["_manifest_context"] = "\n\n".join(_mc_parts)
```

The DESIGN phase mirrors this pattern: read registry from context, call `file_element_summary()` per task's `target_files`, inject into prompt context. Key differences:

- DESIGN operates on `SeedTask` (not `ImplementChunk`), so injection targets `additional_context` or `FeatureContext` fields
- DESIGN needs `ManifestDiff` for edit-mode tasks (pre/post structural comparison)
- DESIGN needs `dependency_graph()` for cross-file awareness in the design prompt
- DESIGN reviewer/arbiter prompts need manifest context for structural validation

### 2.3 Kill Switch

All manifest consumption in the DESIGN phase is gated by `HandlerConfig.manifest_consumption_enabled` (req R1-S10 from Phase 4), the same flag that controls IMPLEMENT consumption. When `False`, all 5 integration surfaces fall through to their pre-manifest behavior.

---

## 3. Integration Surface 1 — Context Seed Assembly (CS)

**Current state:** `DesignPhaseHandler._task_to_feature_context()` (line 1908) builds a `FeatureContext` per task with `additional_context` dict, but has no structural awareness of target file contents. The `HandlerConfig` already has `manifest_consumption_enabled`, `manifest_context_budget`, and `manifest_registry` fields (lines 441–443).

### Requirements

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| CS-1 | **Read `ManifestRegistry` from pipeline context.** In `DesignPhaseHandler.handle()`, resolve the manifest registry using the same pattern as IMPLEMENT: `_manifest_registry = self.config.manifest_registry or context.get("project_manifests")`, gated by `manifest_consumption_enabled`. | Mirrors the established IMPLEMENT pattern (lines 5658–5661). Single resolution point prevents duplicate registry lookups across tasks. | Unit test: `DesignPhaseHandler` with `manifest_consumption_enabled=True` and a mock `ManifestRegistry` in context reads the registry; with `manifest_consumption_enabled=False`, the registry is not accessed. |
| CS-2 | **Per-task `file_element_summary()` injection.** For each task's `target_files`, call `_manifest_registry.file_element_summary(tf, budget)` and inject the result into the `additional_context` dict under the key `"manifest_context"`. Format: `"### {path}\n{summary}"` per file, joined by `"\n\n"`. | Gives the design LLM a structured inventory of existing classes, functions, constants, and their signatures in target files. Directly addresses the root cause of phantom-element references. | Unit test: task with 2 target files → `additional_context["manifest_context"]` contains both file summaries with `###` headers. |
| CS-3 | **`ManifestDiff` for edit-mode tasks.** When `edit_mode_hint == "edit"` and the manifest registry has a manifest for the target file, compute structural context by calling `file_element_summary()` (diff is only meaningful when a previous design iteration exists — see EM-4 for diff-on-redesign). Store the element summary under `additional_context["manifest_edit_context"]`. | Edit-mode tasks modify existing files. The LLM needs to see what exists to describe surgical changes rather than greenfield rewrites. Addresses Lesson 13 #29. | Unit test: edit-mode task with manifest → `additional_context["manifest_edit_context"]` populated; create-mode task → key absent. |
| CS-4 | **Cross-task dependency extraction via `dependency_graph()`.** Call `_manifest_registry.dependency_graph()` once per handler invocation (not per task). For each task, extract the subset of dependency edges involving the task's `target_files` and inject as `additional_context["manifest_dependencies"]` — a human-readable string listing import relationships. | Cross-file dependencies inform design decisions: if file A imports from file B, changes to B's API surface must be coordinated in A's design. Currently the design phase has no visibility into import relationships between target files. | Unit test: task targeting `src/foo.py` which imports `src/bar.py` → `additional_context["manifest_dependencies"]` mentions the dependency. |
| CS-5 | **Budget-aware manifest context.** Use `HandlerConfig.manifest_context_budget` (default 4000 chars) as the `budget_chars` argument to `file_element_summary()`. When a task has multiple `target_files`, divide the budget equally across files (floor division). If total rendered manifest context exceeds `manifest_context_budget`, truncate from the bottom (last file summary first). | Prevents manifest context from consuming excessive prompt tokens. The 4000-char default (~1000 tokens) is calibrated to leave room for the design prompt's other context fields. Mirrors IMPLEMENT's budget pattern. | Unit test: task with 4 target files and budget=4000 → each file gets ≤1000 chars. Task with oversized manifest → total ≤ budget. |
| CS-6 | **Tiered rendering integration.** Register `"manifest_context"` at Tier 1 (High) in `CONTEXT_FIELD_TIERS` (`prompt_utils.py` line 18). This ensures manifest context survives the progressive compression cascade (`format_tiered_context()`) and is rendered with full fidelity, dropping only under extreme budget pressure (after T3 and T2 are compressed). | Manifest context is structural ground truth that should never be silently dropped in favor of advisory fields. T1 placement is consistent with `"constraints_from_manifest"` and `"scope_boundary"` which serve similar structural framing purposes. | Unit test: `format_tiered_context()` with a large additional_context dict → manifest_context preserved in output when T3/T2 fields are compressed. |
| CS-7 | **V2 prompt path integration.** Add a `ManifestModule` to the v2 modular prompt system (`design_prompts/modules.py`). Add `extract_manifest_context()` to `seed_mapping.py`. The module renders manifest summaries and dependencies as a `PromptFragment` with `category="manifest"` and `droppable=False`. Wire into `assemble_design_prompt()` via a `manifest_registry` parameter. | The V2 prompt path (`use_modular_prompts=True`) bypasses `_task_to_feature_context()` entirely, using `assemble_design_prompt()` instead. Without a `ManifestModule`, V2 prompts would never include manifest context, creating V1/V2 parity drift. | Unit test: `assemble_design_prompt()` with a mock `ManifestRegistry` → output includes manifest summary text. Without registry → no manifest fragment. |

---

## 4. Integration Surface 2 — Design System Prompt (DS)

**Current state:** `design.yaml` → `design_system` template (line 4) contains instructions for the design LLM, including File Structure Authority and Protocol/Parameter Fidelity blocks. The system prompt is formatted by `_format_system_prompt()` (line 557) with placeholder substitution. No structural awareness instructions exist.

### Requirements

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| DS-1 | **Structural awareness instruction block.** Add a new `{structural_awareness_block}` placeholder to `design_system` and `refine_system` templates, rendered by `_format_system_prompt()`. When manifest context is available, the block instructs the LLM to use the provided element inventory as ground truth for existing code structure. When absent, the block is empty string. | System-level instructions steer the LLM's behavior across the entire design. Without explicit instructions to use manifest data, the LLM may ignore the element summaries in the user prompt. | Unit test: `_format_system_prompt()` with manifest available → output contains "Structural Awareness" section. Without manifest → placeholder renders empty. |
| DS-2 | **Element-reference accuracy directive.** Within the structural awareness block, include the directive: "When referencing existing elements (classes, functions, constants), use the exact fully-qualified names (FQNs) provided in the Code Structure section of the user prompt. Do not invent element names that are not in the manifest." | Directly addresses the phantom-element problem. The LLM frequently invents plausible-sounding but non-existent method names when designing modifications to existing code. Grounding references in manifest FQNs reduces this. | Review: DS-1 block text includes FQN accuracy directive. |
| DS-3 | **Edit-mode structural constraint.** When `edit_mode_hint == "edit"`, the structural awareness block includes: "This is an EDIT task. The Code Structure section shows what currently exists in the target file(s). Your design MUST describe changes relative to these existing elements. Do not redesign elements that are not listed in the modification scope." | Prevents the LLM from proposing wholesale rewrites of files it should only surgically modify. The edit-mode block (`_build_edit_mode_block()` line 521) currently lists file paths but not their contents — this adds structural grounding. | Unit test: `_format_system_prompt()` with `edit_mode_hint="edit"` and manifest → output contains edit-mode structural constraint. |
| DS-4 | **New-element declaration requirement.** The structural awareness block includes: "If your design introduces elements not present in the current manifest (new classes, functions, or constants), explicitly mark them as NEW in the design document and list them in the ### Files Touched section." | Enables downstream consumers (IMPLEMENT, reviewers) to distinguish between references to existing elements and newly proposed elements. Without this, IMPLEMENT cannot tell whether a design reference is to something that exists or something that should be created. | Review: DS-1 block text includes new-element declaration directive. |

---

## 5. Integration Surface 3 — Design User Prompt (DU)

**Current state:** `design.yaml` → `design_user` template (line 35) has placeholders for `{feature_name}`, `{description}`, `{target_file}`, `{constraints}`, `{additional_context}`, and `{revision_guidance}`. Manifest context flows through `{additional_context}` via CS-2's injection into the `additional_context` dict. No dedicated manifest section exists.

### Requirements

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| DU-1 | **`{manifest_context}` placeholder in `design_user` template.** Add a dedicated `{manifest_context}` placeholder after `{additional_context}` in the `design_user` and `refine_user` templates. This renders the manifest summaries as a separate, clearly labeled section rather than burying them in the generic additional_context blob. | Dedicated placement ensures the LLM consistently finds and uses manifest data. Embedding in `additional_context` risks the data being lost in a large context dict or compressed by tiered rendering. The IMPLEMENT phase similarly uses a dedicated `## Code Structure` section (AC-5 from Phase 4). | Unit test: formatted `design_user` prompt with manifest data → contains `## Code Structure` section separate from Additional Context. |
| DU-2 | **Per-file element summary rendering.** The `{manifest_context}` section renders each target file's element summary under a `### {path}` subheader, showing: element type (class/function/constant), FQN, signature, visibility, and span (line range). Uses `ManifestRegistry.file_element_summary()` output directly. | Provides the LLM with a complete inventory of what exists in each target file. This is the structural ground truth that prevents phantom-element references and enables precise modification descriptions. | Unit test: manifest context for a file with 3 classes and 5 functions → all elements listed with types, FQNs, and spans. |
| DU-3 | **Dependency context rendering.** Below the per-file summaries, render a `### Dependencies` subsection listing import relationships for target files. Format: `- {file} imports from: {dep1}, {dep2}` and `- {file} is imported by: {consumer1}, {consumer2}`. Uses `ManifestRegistry.dependency_graph()`. | Cross-file dependencies are critical for design decisions. If the target file exports an API used by 5 other files, the design must preserve backward compatibility. If it imports from a file being concurrently modified, the design must coordinate. | Unit test: target file with 2 inbound and 3 outbound dependencies → dependency section lists all 5 relationships. |
| DU-4 | **Edit-mode diff summary.** When `edit_mode_hint == "edit"` and a prior design exists (`prior_design` field), include a `### Structural Changes Since Last Design` subsection summarizing what changed in the target files since the prior design was written. If `ManifestDiff` data is available (from CS-3), render added/removed/changed elements. | Multi-iteration design (refine path) can suffer from staleness: the prior design references elements that have been added, removed, or renamed since it was written. A structural diff summary helps the refine LLM understand what has changed. Addresses Lesson 13 #28. | Unit test: edit-mode refine task with manifest diff showing 1 removed and 2 added elements → diff summary section present in prompt. |
| DU-5 | **`FeatureContext` dataclass extension.** Add `manifest_summary: str = ""` field to `FeatureContext` (`design_documentation.py` line 165). This field carries the pre-rendered manifest context string from `_task_to_feature_context()` to the prompt assembly layer. | `FeatureContext` is the data transfer object between `DesignPhaseHandler` and `DesignDocumentationPhase`. Adding a dedicated field (vs relying on `additional_context` dict) provides type safety and makes manifest consumption explicit in the data flow. | Unit test: `FeatureContext(manifest_summary="...")` round-trips correctly. |
| DU-6 | **`_build_edit_mode_block()` enhancement.** Extend `_build_edit_mode_block()` (`design_documentation.py` line 521) to accept an optional `manifest_summaries: dict[str, str]` parameter. When provided, replace the path-only file listing with structural file summaries showing element inventories per file. Falls back to current path-only listing when `manifest_summaries` is `None`. | The current edit-mode block tells the LLM which files exist but not what's in them. This is the minimum information gap that causes full-file overwrites: the LLM knows a file exists but not its structure, so it writes the entire file from scratch instead of describing changes. | Unit test: `_build_edit_mode_block("edit", ["src/foo.py"], manifest_summaries={"src/foo.py": "- Foo(x, y)\n- bar(z)"})` → output contains element listing, not just path. |
| DU-7 | **Graceful fallback when manifest is absent.** When `manifest_summary` is empty or `ManifestRegistry` is `None`, the `{manifest_context}` placeholder renders as empty string (no "Code Structure" section in the prompt). Do NOT render "No structural context available" — absent manifest should be invisible to the LLM, not flagged as a gap. | Flagging absence ("No structural context available") could cause the LLM to hallucinate structural concerns or refuse to design without it. Silent absence is the correct degradation behavior, consistent with IMPLEMENT's pattern (lines 5676–5679: manifest absent → no injection, no message). | Unit test: `FeatureContext` with empty `manifest_summary` → formatted prompt does not contain "Code Structure" or "manifest" strings. |

---

## 6. Integration Surface 4 — Design Review / Arbiter Prompts (DR)

**Current state:** `design.yaml` → `reviewer_system` (line 128), `reviewer_user` (line 151), `arbiter_system` (line 156), `arbiter_user` (line 179). Reviewers evaluate the design document against "technical correctness," "completeness," "best practices," and "feasibility." Neither reviewer has access to target file structure — reviews are purely based on the design document text.

### Requirements

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| DR-1 | **Structural validation instruction for reviewer.** Add a structural validation focus item to `reviewer_system`: "When Code Structure data is provided, verify that the design's element references (class names, function signatures, imports) match the actual file structure. Flag any design references to elements not present in the manifest as potential errors." | Reviewers currently have no objective basis to validate element references. They can only check internal consistency of the design document. With manifest context, reviewers can catch phantom-element errors before the design reaches IMPLEMENT. | Unit test: `reviewer_system` prompt with manifest context → contains structural validation instruction. Without manifest → instruction absent. |
| DR-2 | **Breaking change detection directive.** Add to `reviewer_system`: "If the design proposes removing or renaming public elements listed in the Code Structure, flag this as a potential breaking change. Note which consumers (from the Dependencies section) would be affected." | Public API changes cascade through dependent files. The reviewer should flag these proactively rather than letting IMPLEMENT discover the breakage during integration. Leverages `ManifestDiff.has_breaking_changes` data from the manifest. | Review: reviewer system prompt includes breaking-change detection directive referencing public elements and dependencies. |
| DR-3 | **`{manifest_context}` in reviewer and arbiter user prompts.** Add `{manifest_context}` placeholder to `reviewer_user` and `arbiter_user` templates, rendered after `{design_document}`. Format: same `## Code Structure` section as the design user prompt. | Reviewers need the same structural ground truth as the designer to validate element references. Without it, the reviewer can only check if the design is internally consistent, not whether it matches reality. | Unit test: formatted `reviewer_user` with manifest → contains `## Code Structure` section after the design document. |
| DR-4 | **Arbiter structural ground-truth tiebreaker.** Add to `arbiter_system`: "When the Reviewer and the design document disagree about what exists in the codebase, use the Code Structure section as objective evidence. The manifest reflects the actual file contents and takes precedence over assumptions in either the design or the review." | The arbiter resolves disagreements between the design and the reviewer. Manifest data provides an objective tiebreaker — if the design says `FooClass.bar()` exists but the manifest doesn't list it, the arbiter can definitively flag this as an error rather than deferring to either party's opinion. | Review: arbiter system prompt includes ground-truth tiebreaker instruction referencing Code Structure. |
| DR-5 | **Review criteria weight adjustment.** When manifest context is provided, add "Structural Accuracy" as an explicit review criterion in both `reviewer_system` and `arbiter_system`, alongside the existing criteria (correctness, completeness, best practices, feasibility). Define it as: "Do the design's element references, file modifications, and API changes align with the actual code structure provided?" | Makes structural accuracy a first-class review dimension that reviewers must explicitly address in their verdict. Without explicit weight, reviewers may acknowledge manifest data but not systematically check against it. | Unit test: `reviewer_system` with manifest → "Structural Accuracy" listed as review focus item. |

---

## 7. Integration Surface 5 — Edit-Mode Block Enhancement (EM)

**Current state:** `_build_edit_mode_block()` (`design_documentation.py` line 521) generates a text block for edit-mode tasks listing existing target file paths with `(modify)` annotations. The block tells the LLM to describe changes rather than greenfield implementation. It has no visibility into file contents.

### Requirements

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| EM-1 | **Replace path-only listing with structural file summaries.** When manifest data is available, replace the current `- \`path/to/file.py\`` listing with `- \`path/to/file.py\` (modify) — {element_count} elements ({public_count} public)` followed by a compact element inventory. | The current block provides zero information about file contents. Adding element counts and inventories gives the LLM the minimum context needed to describe modifications rather than rewrites. | Unit test: edit-mode block with manifest → file listing includes element counts. Without manifest → falls back to current path-only format. |
| EM-2 | **Public API surface rendering.** For each existing target file, list public classes, functions, and constants with their signatures. Use `ManifestRegistry.file_element_summary()` at Tier 3 (compact, public-only) to keep the edit-mode block concise. | The public API surface is what downstream consumers depend on. Making it visible in the edit-mode block ensures the LLM knows what it must preserve or explicitly declare as changed. | Unit test: file with 3 public and 5 private elements → edit-mode block lists only the 3 public elements. |
| EM-3 | **Import dependency rendering.** For each existing target file, append a line: `Imported by: {consumer1}, {consumer2}` (from `dependency_graph()` inverse lookup). This shows which files would break if the target file's API changes. | Import dependency visibility is critical for edit-mode designs: the LLM must know that changing `FooClass.bar()` would break 3 other files. Without this, the design may propose breaking changes unknowingly. | Unit test: file imported by 2 other files → edit-mode block includes "Imported by: file1.py, file2.py". File with no consumers → line omitted. |
| EM-4 | **Element span hints.** For key elements (public classes and functions), include line range hints: `[lines 45-120]`. Uses `Element.span.start_line` and `Element.span.end_line` from the manifest. | Span hints help the LLM understand element size and location within the file. A 75-line class is a different modification target than a 5-line function. This context improves the precision of "add method to class X" directives. | Unit test: element with span (45, 120) → edit-mode block includes `[lines 45-120]`. Element with no span → line range omitted. |
| EM-5 | **Budget-aware progressive truncation.** Apply the same 4-tier progressive truncation as `file_element_summary()` (full → compact → public-only → FQN-only) to the edit-mode block, with a separate budget of `manifest_context_budget // 2` (default 2000 chars). The edit-mode block is a subset of the full prompt manifest context and should use half the budget. | The edit-mode block competes for prompt space with the main manifest context section. Using half the budget prevents double-counting. Progressive truncation ensures graceful degradation for files with many elements. | Unit test: file with 100 elements and budget=2000 → block truncates to public-only or FQN-only tier within budget. |

---

## 8. Performance Budget

Manifest consumption in the DESIGN phase must operate within strict token and latency budgets.

| ID | Metric | Budget | Rationale |
|----|--------|--------|-----------|
| PB-1 | Total manifest context in design user prompt | ≤ 4000 chars (~1000 tokens) | Consistent with IMPLEMENT's `manifest_context_budget` default. Leaves room for the design prompt's other context fields (~8000 tokens for a standard design prompt). |
| PB-2 | Edit-mode block manifest additions | ≤ 2000 chars (~500 tokens) | Half of PB-1 budget. Edit-mode block is a supplementary context, not the primary structural data carrier. |
| PB-3 | Reviewer/arbiter manifest context | ≤ 4000 chars (~1000 tokens) | Same budget as design prompt. Reviewer prompts are shorter overall, so manifest context can use the full budget. |
| PB-4 | `file_element_summary()` latency per file | < 10ms | Inherited from Phase 4 AP-3. |
| PB-5 | `dependency_graph()` call (once per handler) | < 100ms | Lazy-computed and cached on `ManifestRegistry`. Called once per `DesignPhaseHandler.handle()` invocation, not per task. |
| PB-6 | Total manifest overhead per design task | < 50ms | Sum of element summaries + dependency extraction + prompt formatting. Must not meaningfully increase design phase latency. |

---

## 9. Graceful Degradation

| ID | Requirement | Rationale |
|----|-------------|-----------|
| GD-1 | **Absent manifest.** When `ManifestRegistry` is `None` or `manifest_consumption_enabled` is `False`, all 5 integration surfaces produce identical behavior to pre-Phase 5. No manifest-related text appears in any prompt. No errors or warnings. | Ensures the DESIGN phase works identically on projects without manifests or when the kill switch is active. |
| GD-2 | **Partial manifest.** When the registry exists but has no manifest for a specific target file, that file is excluded from manifest context. Other target files with manifests are still rendered. Log at DEBUG: `"DESIGN: no manifest for {path}"`. | Common case: a task targets both existing files (in manifest) and new files (not yet created, no manifest). The new files should not prevent manifest context for existing files. |
| GD-3 | **Corrupt manifest.** When `file_element_summary()` returns an empty string for a file that is in the registry, treat as manifest-absent for that file. Do not inject empty sections into prompts. | Defensive against corrupted or partially-parsed manifest entries. Empty summaries provide no value and would consume prompt space with empty headers. |
| GD-4 | **Budget exceeded.** When total manifest context exceeds `manifest_context_budget`, apply progressive truncation (Tier 1 → Tier 4 per `file_element_summary()`). If still over budget after Tier 4, truncate from the last file. Log at INFO: `"DESIGN: manifest context truncated from {original} to {budget} chars"`. | Prevents manifest context from consuming excessive prompt tokens under any circumstances. Logging at INFO gives visibility into truncation frequency. |
| GD-5 | **Kill switch.** `HandlerConfig.manifest_consumption_enabled = False` forces all 5 surfaces to the pre-manifest code path. All manifest-related parameters in `_task_to_feature_context()` are skipped. Log at DEBUG: `"DESIGN: manifest consumption disabled"`. | Operational escape hatch for safe rollout. If manifest context causes design quality regression, operators can disable it without code changes. Shares the same flag as IMPLEMENT (R1-S10 from Phase 4). |

---

## 10. Acceptance Criteria

### 10.1 Functional Criteria

| ID | Criterion | Validation |
|----|-----------|------------|
| AC-1 | **Element reference accuracy.** A design generated with manifest context references only FQNs that exist in the manifest (no phantom elements). | Semi-automated: post-design validation script extracts element references from design text and checks each against `ManifestRegistry.fqn_exists()`. Target: ≥90% reference accuracy on a 10-task sample. |
| AC-2 | **Edit-mode constraint adherence.** When `edit_mode_hint == "edit"` and manifest context is provided, the design describes modifications to existing elements rather than greenfield implementation. | Manual review of 5 edit-mode design outputs: each should reference existing elements from the manifest and describe changes relative to them. |
| AC-3 | **Review structural validation.** When manifest context is provided to reviewers, review verdicts include structural accuracy assessments (mentions of element references, breaking changes, or structural alignment). | Manual review of 5 reviewer verdicts with manifest context: each should include at least one structural accuracy observation. |
| AC-4 | **Performance within budget.** Manifest context in design prompts never exceeds `manifest_context_budget` chars. | Unit test with oversized manifests (100+ elements per file, 5 target files): verify total manifest context ≤ budget after truncation. |
| AC-5 | **Graceful degradation.** Pipeline run with `context["project_manifests"] = None` produces identical DESIGN phase behavior to pre-Phase 5. | Integration test: compare design phase code paths (via mock instrumentation) with and without manifest. Assert heuristic paths invoked when manifest absent. |
| AC-6 | **Kill switch.** Setting `manifest_consumption_enabled = False` with manifests present forces all 5 surfaces to pre-manifest behavior. | Unit test: mock `ManifestRegistry` in context, set flag to `False`, verify no manifest methods called and no manifest text in prompts. |
| AC-7 | **V1/V2 parity.** `assemble_design_prompt()` (V2 path) includes manifest context when available, producing equivalent structural information as the V1 `_task_to_feature_context()` path. | Unit test: same task processed through V1 and V2 paths with same manifest → both prompts contain equivalent manifest summary sections. |
| AC-8 | **Backward compatibility.** `FeatureContext` with `manifest_summary=""` (default) behaves identically to current `FeatureContext` without the field. No changes to `DesignDocumentationPhase.run()` behavior when manifest fields are at defaults. | Unit test: `FeatureContext` without manifest_summary field → no errors, no manifest text in prompts. |

### 10.2 Performance Criteria

| ID | Criterion | Budget | Validation |
|----|-----------|--------|------------|
| AP-1 | Manifest context assembly per task | < 50ms | Benchmark test with `time.perf_counter()` on a task with 5 target files. |
| AP-2 | Edit-mode block rendering with manifest | < 10ms | Benchmark test with largest target file manifest. |
| AP-3 | Reviewer prompt assembly with manifest | < 20ms | Benchmark test including manifest context formatting. |

---

## 11. Rollout Strategy

Phase 5 (DESIGN manifest integration) is delivered in two tiers, both gated by the existing `manifest_consumption_enabled` kill switch from Phase 4.

### Tier 1: Core Context Assembly

| Component | Description | Deps |
|-----------|-------------|------|
| CS-1 through CS-6 | Registry read, per-task element injection, dependency extraction, budget enforcement, tier registration | Phase 4 (ManifestRegistry, context threading) |
| DU-1 through DU-3, DU-5, DU-7 | User prompt manifest section, file summaries, dependencies, FeatureContext field, graceful fallback | CS-1, CS-2, CS-4 |
| DS-1 through DS-4 | System prompt structural awareness instructions | — |
| GD-1 through GD-5 | All degradation paths implemented and tested | — |

### Tier 2: Review & Edit-Mode Enhancement

| Component | Description | Deps |
|-----------|-------------|------|
| DR-1 through DR-5 | Reviewer/arbiter structural validation, breaking change detection, ground-truth tiebreaker | Tier 1 |
| DU-4, DU-6 | Edit-mode diff summary, `_build_edit_mode_block()` enhancement | Tier 1, CS-3 |
| EM-1 through EM-5 | Edit-mode block structural summaries, API surface, dependencies, spans, truncation | Tier 1 |
| CS-7 | V2 prompt path `ManifestModule` | Tier 1 |

---

## 12. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | **Manifest staleness.** If manifests are not refreshed after prior pipeline phases modify files, the DESIGN phase may inject outdated structural data, leading to designs that reference removed or renamed elements. | Medium | High | Rely on Phase 4's staleness detection (GD-3 digest-based) and IN-4 cache refresh after INTEGRATE. For feature-serial mode, the handoff between design iterations should trigger a manifest refresh check. Log stale files at WARNING. |
| R2 | **Token budget overrun.** Large files with many elements could generate manifest summaries that consume excessive prompt tokens, crowding out other design context. | Medium | Medium | PB-1 enforces a 4000-char budget with progressive truncation. CS-5 divides budget across files. The 4-tier truncation in `file_element_summary()` provides graceful degradation from full to FQN-only. |
| R3 | **Prompt injection via manifest content.** Manifest elements (function names, docstrings, signatures) are user-authored strings injected into LLM prompts. A maliciously crafted function name or docstring could contain prompt injection payloads. | Low | Medium | Same risk as Phase 4's R2-S7 (accepted as documented risk). Manifest-derived strings sit alongside instruction text in the prompt. Mitigation: the manifest's `file_element_summary()` renders only FQNs, signatures, and spans — docstrings are truncated to first line at Tier 1 and dropped entirely at Tier 2+. This limits the injection surface. Document as accepted risk. |
| R4 | **V1/V2 prompt path drift.** The V1 path (`_task_to_feature_context()`) and V2 path (`assemble_design_prompt()`) could diverge if one is updated and the other isn't. | Medium | Medium | AC-7 requires parity testing. CS-7 creates a dedicated `ManifestModule` for V2 that mirrors CS-2's logic. Both paths read from the same `ManifestRegistry` and use the same `file_element_summary()` API. |
| R5 | **LLM ignores manifest context.** The design LLM may not consistently use the structural data provided, continuing to invent element names. | Medium | Medium | DS-1 through DS-4 provide explicit system-level instructions. DR-1 and DR-5 add reviewer enforcement. If manifest context proves ineffective, the kill switch (GD-5) allows disabling without code changes. A/B evaluation comparing manifest-enriched vs baseline designs is recommended before full rollout. |
| R6 | **Reviewer over-reliance on manifest.** Reviewers may flag every element reference that isn't in the manifest, including legitimately new elements proposed by the design. | Low | Low | DS-4 instructs the designer to explicitly mark new elements as NEW. DR-1's instruction specifies "elements not present in the manifest" as potential errors, not definitive errors — the reviewer should check whether the design explicitly introduces them. |

---

## 13. Cross-Reference with Phase 4

This section verifies alignment with Phase 4's integration surfaces and prevents overlap or contradiction.

| Phase 4 Surface | Phase 5 Relationship | Notes |
|------------------|----------------------|-------|
| Plan Ingestion (PI-1 through PI-5) | No overlap | Plan ingestion runs before DESIGN. Manifest data flows to plan ingestion independently. |
| IMPLEMENT (IM-1 through IM-6) | Complementary | DESIGN provides the blueprint that IMPLEMENT executes. Both inject `file_element_summary()` but for different purposes: DESIGN for scope decisions, IMPLEMENT for code generation context. |
| INTEGRATE (IN-1 through IN-4) | No overlap | INTEGRATE runs after IMPLEMENT. Uses `ManifestDiff` for post-merge validation, not design-time. |
| Preflight (PF-1 through PF-5) | No overlap | Preflight validators use manifest for rule evaluation, not design prompt construction. |
| Capability Index (CI-1 through CI-4) | No overlap | Capability validation is a CLI command, not a pipeline phase. |
| Context Threading (CT-1 through CT-5) | Consumed | CT-1 (`context["project_manifests"]`) is the source for CS-1's registry read. No modifications to context threading — DESIGN is a pure consumer. |

---

## Appendix: Iterative Review Log

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

*(Awaiting first review round)*

### Areas Needing Further Review

*(Awaiting first review round)*

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(Awaiting first review round)*
