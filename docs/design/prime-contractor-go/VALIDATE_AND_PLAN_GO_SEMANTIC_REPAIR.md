# Prompt: Validate & Plan Go Semantic Repair (REQ-KZ-GO-403)

> Provide this prompt alongside `KAIZEN_GO_REQUIREMENTS.md` to validate the requirements and produce an implementation plan.

---

## Context

The StartD8 SDK has a multi-language code generation pipeline (Prime Contractor) with a Kaizen quality system. The C# language has a working semantic-to-repair bridge that flows: detection → collection → bridge → routing → repair step → verification. Java has convention requirements (REQ-KZ-JV-402) following the same pattern.

Go has 6 semantic checks in `go_semantic_checks.py` and compliance_results collection (just implemented), but no repair steps or dispatch. REQ-KZ-GO-403 defines the convention — all categories are advisory in Phase 1; Phase 2 adds two text-based repair steps (`dot_import` cleanup, `python_contamination` strip).

**Go-specific constraint:** No Python-hosted AST layer for Go. Repairs must be text-based transformations validated by external tools (`goimports`, `gofmt`). The Go compiler's error messages are specific enough that re-prompting the LLM is preferred over programmatic repair for structural issues.

## Task

### Part 1: Validate Requirements

Read REQ-KZ-GO-403 (Section 5, after REQ-KZ-GO-402) and validate against the codebase:

1. **Category inventory accuracy** — Confirm all 6 categories in `go_semantic_checks.py` are listed in REQ-KZ-GO-403b. Check `check=` field string values match exactly.
2. **Classification correctness** — For each Phase 2 "Repairable" category, verify the repair technique is feasible:
   - `dot_import`: Is `import . "pkg"` → `import "pkg"` a safe regex replacement? Will `goimports -w` successfully qualify the now-unqualified symbols? What happens if the package has many exported symbols used bare?
   - `python_contamination`: Is line removal safe? Could a Python fingerprint match appear in a Go string literal or comment? Check the fingerprint patterns in `go_semantic_checks.py:_check_python_contamination()`.
3. **Compliance results wiring** — Confirm REQ-KZ-GO-403c (IMPLEMENTED) by reading the Go block in `integration_engine.py:_run_semantic_checks()`.
4. **repair_enabled discrepancy** — The requirements state `repair_enabled = False` but `go.py` returns `True`. Determine which is correct:
   - `repair_enabled = True` makes sense if Go syntax/import repair routes already work
   - `repair_enabled = False` is what the requirements say (Python AST repair doesn't apply)
   - Check if `repair_enabled` gates semantic repair or only syntax repair. Read how it's consumed.
5. **External tool dependency** — Both Phase 2 steps depend on `goimports`/`gofmt`. Verify the fallback behavior: what happens when these tools are missing? Check `GoLanguageProfile.post_generation_cleanup()` for the existing fallback pattern.
6. **Phase 2 rollback safety** — Both steps specify "rollback if tool exits non-zero." Verify `repair/staging.py` provides atomic staging that supports this pattern. Read the C# repair step for the rollback pattern.

### Part 2: Create Implementation Plan

Produce a phased implementation plan for REQ-KZ-GO-403.

**Phase 1 deliverables (advisory-only — current state):**
- Confirm all 6 categories appear in postmortem reports via compliance_results
- Verify Kaizen suggestions reference Go categories via `CAUSE_TO_SUGGESTION` mappings in `prime_postmortem.py`
- Add any missing Go category → suggestion mappings
- Test: run postmortem on a Go file with `fmt_println_in_service` — verify it appears in `kaizen-metrics.json`

**Phase 2 deliverables:**

1. **`GoDotImportCleanupStep`** in `repair/steps/go_dot_import_cleanup.py`:
   - Regex: replace `import . "pkg"` with `import "pkg"` (handle multiline import blocks)
   - Post-repair: run `goimports -w` to qualify symbols
   - Rollback: restore original if `goimports` exits non-zero
   - Register in `_STEP_FACTORIES`

2. **`GoPythonContaminationStripStep`** in `repair/steps/go_contamination_strip.py`:
   - Remove lines matching Python fingerprint patterns (reuse pattern list from `go_semantic_checks.py`)
   - Post-repair: run `gofmt -w` to verify file still parses
   - Rollback: restore original if `gofmt` exits non-zero
   - Register in `_STEP_FACTORIES`

3. **Routing entries:**
   - `("semantic", "dot_import", ["go_dot_import_cleanup", "go_syntax_validate"], "MEDIUM", "go")`
   - `("semantic", "python_contamination", ["go_contamination_strip", "go_syntax_validate"], "HIGH", "go")`

4. **Bridge updates:**
   - Add `"dot_import"` and `"python_contamination"` to `_REPAIRABLE_CATEGORIES`
   - Add `".go"` to `_SEMANTIC_REPAIR_EXTENSIONS`
   - Add `_repair_single_go_file()` to orchestrator (or make the C# pattern generic)

5. **Tests:**
   - Unit: `.go` file with `import . "fmt"` → verify rewrite
   - Unit: `.go` file with `def main():` Python contamination → verify line removed
   - Integration: end-to-end repair with rollback on tool failure

## Key Files to Read

| File | Purpose |
|------|---------|
| `src/startd8/validators/go_semantic_checks.py` | 6 semantic checks — verify category names and fingerprint patterns |
| `src/startd8/languages/go.py` | `repair_enabled`, `post_generation_cleanup()`, `stub_patterns` |
| `src/startd8/repair/semantic_bridge.py` | `_REPAIRABLE_CATEGORIES`, `translate_to_diagnostics()` |
| `src/startd8/repair/routing.py` | `_ROUTING_TABLE`, `_STEP_FACTORIES` |
| `src/startd8/repair/orchestrator.py` | `_SEMANTIC_REPAIR_EXTENSIONS`, `_repair_single_csharp_file()` (reference) |
| `src/startd8/repair/staging.py` | Atomic staging for rollback support |
| `src/startd8/repair/steps/sql_parameterize.py` | Reference repair step pattern |
| `src/startd8/contractors/integration_engine.py` | Go block in `_run_semantic_checks()` |
| `src/startd8/contractors/prime_postmortem.py` | `CAUSE_TO_SUGGESTION` mappings for Go categories |
| `tests/unit/validators/test_go_semantic_checks.py` | Existing Go semantic check tests |
| `tests/unit/repair/test_go_repair_steps.py` | Existing Go repair step tests |
| `docs/design/prime-contractor-go/KAIZEN_GO_REQUIREMENTS.md` | REQ-KZ-GO-403 requirements |
