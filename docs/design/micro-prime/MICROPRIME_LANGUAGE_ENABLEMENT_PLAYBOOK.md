# MicroPrime Language Enablement Playbook

> **Purpose:** Systematic checklist for enabling a new language in MicroPrime, ordered by pipeline stage from earliest (enrichment) to latest (postmortem). Derived from the Go enablement experience (run-118) and the Hayai Design Principle.
>
> **Audience:** Anyone adding or auditing a language in the MicroPrime pipeline.
>
> **Principle:** Quality knowledge must bind at the earliest pipeline stage where it can be resolved. Each checkpoint below identifies where knowledge enters and when it should take effect.

---

## How to Use This Playbook

For a new language: work through every checkpoint in order. Check the box when the integration point is verified. For an existing language audit: use the "Audit Question" column to identify Hayai violations — places where knowledge exists but isn't applied.

The playbook is organized by pipeline stage, from plan ingestion (earliest) to postmortem (latest). Each stage builds on the previous one.

---

## Stage 0: Language Profile Foundation

These are prerequisites. Without them, no downstream stage can function.

| # | Checkpoint | File(s) | Audit Question | Go Status |
|---|-----------|---------|----------------|-----------|
| 0.1 | `LanguageProfile` implementation exists | `languages/{lang}.py` | Does a concrete profile class exist with all protocol properties? | Done |
| 0.2 | Profile registered via entry point | `pyproject.toml` `[startd8.languages]` | Does `LanguageRegistry.discover()` find this profile? | Done |
| 0.3 | `source_extensions` populated | Profile property | Does the profile declare all file extensions for this language? | Done (`.go`) |
| 0.4 | `coding_standards` populated | Profile property | Does the property cover naming, error handling, logging, imports, and security? | Done |
| 0.5 | `system_prompt_role` populated | Profile property | Does it return a language-specific role string? | Done ("an expert Go engineer") |
| 0.6 | `sanitize_code_examples()` implemented | Profile method | Does it transform known anti-patterns (e.g., `fmt.Println` → `slog.Info`)? | Done |
| 0.7 | `validate_syntax()` implemented | Profile method | Does it call the language's native syntax checker (e.g., `gofmt -e`)? | Done |
| 0.8 | `stub_patterns` populated | Profile property | Does it list language-idiomatic stub markers (e.g., `panic("not implemented")`)? | Done |

**Hayai test:** After Stage 0, the command `resolve_language(["src/main.{ext}"])` must return the correct profile, and `profile.coding_standards` must be a non-empty string.

---

## Stage 1: Plan Ingestion Enrichment

Quality knowledge binds to seed tasks at the earliest pipeline stage.

| # | Checkpoint | File(s) | Audit Question | Go Status |
|---|-----------|---------|----------------|-----------|
| 1.1 | `_enrich_coding_standards()` resolves language from target_files | `plan_ingestion_enrichment.py` | Does `language_id` appear in enriched seed context? | Done (40/40 tasks) |
| 1.2 | `coding_standards` persisted in seed | Same | Is the string available in `task.config.context.coding_standards`? | Done |
| 1.3 | `language_role` persisted in seed | Same | Is the role string available for drafter system prompt? | Done |
| 1.4 | Task descriptions sanitized | Same | Does `sanitize_code_examples()` run on descriptions? | Done (0 transforms needed) |
| 1.5 | Design doc sections sanitized | Same | Do design doc entries get sanitized? | Done |
| 1.6 | Batch context used for language-neutral files | Same | Do Dockerfiles/configs infer language from sibling `.{ext}` files? | Done |

**Hayai test:** After plan ingestion, inspect `prime-context-seed-enriched.json`. Every task with language-specific target files must have `language_id`, `coding_standards`, and `language_role` in its context.

**Diagnostic metric:** `enrichment.coding_standards_injected` in `plan-ingestion-diagnostic.json` should equal `total_tasks` (or close — tasks without target_files are skipped).

---

## Stage 2: Spec Building

Coding standards and project context reach the spec LLM.

| # | Checkpoint | File(s) | Audit Question | Go Status |
|---|-----------|---------|----------------|-----------|
| 2.1 | `coding_standards` injected at P0 priority in spec prompt | `spec_builder.py` line ~1248 | Is the coding standards section present in the spec prompt at P0 (never dropped by budget)? | Done |
| 2.2 | `build_project_context_section()` produces language-specific rules | `languages/{lang}.py` | Does the profile inject structural constraints (import rules, error handling, package organization)? | Done (21+ rules for Go) |
| 2.3 | `sanitize_code_examples()` runs on spec inputs (defense-in-depth) | `spec_builder.py` | Does spec builder call `lang_profile.sanitize_code_examples()` on design docs, task descriptions, reference implementations? | Done |
| 2.4 | Spec LLM output sanitized | `spec_builder.py` `build_spec()` | Is the LLM's raw spec text run through `sanitize_code_examples()` before becoming `raw_spec`? | Done |
| 2.5 | Security constraints language-aware | `drafter.py` line ~252 | Are parameterized query rules injected when database frameworks are detected? | Done (shared P0 constraint) |

**Hayai test:** Read a spec prompt from `kaizen-prompts/` directory. Verify the coding standards section appears and contains language-specific rules (e.g., `if err != nil` for Go).

---

## Stage 3: MicroPrime Element Routing

The complexity classifier and MicroPrime engine route elements correctly.

| # | Checkpoint | File(s) | Audit Question | Go Status |
|---|-----------|---------|----------------|-----------|
| 3.1 | `_is_non_python_file()` returns `False` for this language's extensions | `engine.py` line ~155 | Does `.{ext}` correctly pass the bypass gate? | Done (`.go` → False) |
| 3.2 | `_get_microprime_extensions()` includes this language | `engine.py` line ~113 | Are all profile extensions in the auto-discovered set? | Done |
| 3.3 | Complexity classifier assigns tiers to elements | `complexity/classifier.py` | Are elements from this language classified (TRIVIAL/SIMPLE/MODERATE/COMPLEX)? | Done (12 SIMPLE) |
| 3.4 | File-level special cases handled | `engine.py` non-Python bypass | Are build files (go.mod, package.json, build.gradle) handled deterministically? | Done (`_try_generate_go_mod`) |
| 3.5 | Dockerfiles handled | Same | Are Dockerfiles correctly bypassed or deterministically generated? | Done |

**Hayai test:** Run `_is_non_python_file("src/main.{ext}")` — must return `False`. Run `_is_non_python_file("{build_file}")` — must return `True` for build files.

---

## Stage 4: Template Matching

Templates provide zero-cost, deterministic generation for common patterns.

| # | Checkpoint | File(s) | Audit Question | Go Status |
|---|-----------|---------|----------------|-----------|
| 4.1 | Templates registered in `_LANGUAGE_TEMPLATES` | `templates.py` | Does the language have entries in the template dict? | Done (7 Go templates) |
| 4.2 | `TemplateRegistry.has_templates_for(language_id)` returns True | `templates.py` | Does the registry recognize this language? | Done |
| 4.3 | Template match functions evaluate correctly | `templates.py` | Do match functions fire for representative elements (constructors, getters, interface methods)? | **Gap** — templates match function-level elements but run-118 had file-level elements |
| 4.4 | Structural verification uses language-aware path | `engine.py` line ~3843 | Does template output get verified with `gofmt`/language parser, not `ast.parse()`? | Partial — Python-only guard at line 3843; non-Python templates skip structural verify |
| 4.5 | Templates actually match in practice | Postmortem `template_used` field | Did any element in a real run use a template? | **No** — 0/12 in run-118 |

**Hayai test:** Create a `ForwardElementSpec` for a constructor (`NewCartService`) and verify `registry.match()` returns a template. If templates never match in practice, the granularity gap (4.3) needs investigation.

**Common gap pattern:** Templates exist but elements are too coarse-grained (file-level instead of function-level). Fix: enable function-level decomposition for this language (see Stage 5).

---

## Stage 5: Element Decomposition and Splicer

Element-level generation produces bodies; the splicer assembles them into skeletons.

| # | Checkpoint | File(s) | Audit Question | Go Status |
|---|-----------|---------|----------------|-----------|
| 5.1 | Language parser extracts function declarations | `languages/{lang}_parser.py` or `go_parser.py` | Can the parser identify individual functions, methods, types? | Done (`go_parser.py`) |
| 5.2 | Splicer dispatch wired | `splicer.py` `splice_body_into_skeleton()` | Does the splicer have a language dispatch (`_splice_{lang}_dispatch`)? | Done (line 179) |
| 5.3 | Splicer handles language-specific body replacement | `languages/{lang}_splicer.py` | Does brace-matching (or language-appropriate) body replacement work? | Done (`go_splicer.py`) |
| 5.4 | SIMPLE decomposer produces function-level elements | `engine.py` `_function_body_decomposer` | Does decomposition break multi-function files into individual function elements? | **Gap** — decomposer is Python-AST-based; Go files stay as single elements |
| 5.5 | Splicer exercised in practice | Postmortem splice metrics | Did any element in a real run use the splicer? | **No** — file-level generation means no body-level splicing |

**Hayai test:** Given a skeleton with 3 function stubs and 3 generated bodies, does `splice_body_into_skeleton()` produce a valid merged file? This should work in unit tests even if the pipeline doesn't exercise it yet.

**Common gap pattern:** Parser and splicer exist but the decomposer doesn't produce function-level elements for this language. The decomposer uses Python AST (`ast.parse()`) which can't parse other languages. Fix: add a language-aware decomposition path that uses the language's own parser.

---

## Stage 6: Generation and Validation

The LLM generates code; the validation gate checks it.

| # | Checkpoint | File(s) | Audit Question | Go Status |
|---|-----------|---------|----------------|-----------|
| 6.1 | `ast_parse_valid()` dispatches to language validator | `structural_verify.py` line ~250 | Does the function call `_try_parse()` with the correct `language_id` for non-Python? | Done |
| 6.2 | `_try_parse()` calls language-specific tool | `repair.py` line ~1343 | Does Go dispatch to `gofmt -e`? C# to tree-sitter? Java to assume-valid? | Done |
| 6.3 | Repair pipeline receives `language_id` | `engine.py` line ~4120 | Is the language threaded through `run_repair_pipeline()`? | Done |
| 6.4 | `fence_strip` handles language-specific fences | `repair/steps/fence_strip.py` | Does extraction handle `` ```go ``, `` ```java ``, etc.? | Done |
| 6.5 | Post-generation cleanup runs language tools | `LanguageProfile.post_generation_cleanup()` | Does `goimports`/`gofmt` (or equivalent) run on generated files? | Done |
| 6.6 | Fence-strip rate is reasonable (< 50%) | Postmortem `repair_step_distribution` | Is the LLM consistently wrapping output in fences? | **Gap** — 100% fence-strip rate for Go |

**Hayai test:** Generate a Go function body via Ollama, feed it through `_validate_element()`. Verify it reaches `gofmt -e`, not `ast.parse()`.

**Common gap pattern:** 100% fence-strip rate means the prompt isn't effective at preventing markdown wrapping. Fix: add language-specific "no fences" instruction to the element generation prompt, or pre-strip fences before validation.

---

## Stage 7: Repair Pipeline

Post-generation repair catches and fixes defects.

| # | Checkpoint | File(s) | Audit Question | Go Status |
|---|-----------|---------|----------------|-----------|
| 7.1 | Syntax repair route exists | `repair/routing.py` | Is there a `({lang}_syntax_error, [...])` route? | Done |
| 7.2 | Import repair route exists | Same | Is there an import-specific repair route? | Done |
| 7.3 | Semantic repair routes exist | Same | Are language-specific semantic categories (contamination, style) routed? | Done (5 routes) |
| 7.4 | Repair step factories registered | `repair/routing.py` `_STEP_FACTORIES` | Do language-specific steps have factory entries? | Done (4 Go steps) |
| 7.5 | `_CANONICAL_ORDER` includes language steps | Same | Are steps ordered correctly (text transforms → syntax validate)? | Done |
| 7.6 | Semantic repair categories configured | `RepairConfig.semantic_repair_categories` | Does the Prime Contractor pass the correct categories for this language? | Verify — may need explicit wiring |

**Hayai test:** Create a `DiskComplianceResult` with `semantic_issues=[{"category": "python_contamination"}]` for a `.go` file. Verify the repair pipeline dispatches to `go_contamination_strip` → `go_syntax_validate`.

---

## Stage 7.5: Python Leakage Audit (REQ-MPL-105)

**Run this BEFORE the first real run of a new language.** The Go run-118 forensic analysis found Python-specific assumptions in 4 functions that Go elements traverse. A systematic audit would have caught these before the run.

| # | Checkpoint | Grep Pattern | What It Catches | Go Status |
|---|-----------|-------------|-----------------|-----------|
| 7.5.1 | `_detect_definition_line()` recognizes this language | `grep -n '"def "' src/startd8/micro_prime/repair.py` | Python `def`/`class`/`@` as the only recognized function declarations. Go `func`, Java `public`, C# `private`, Node.js `function` missing → `bare_statement_wrap` produces Python `def` wrappers for non-Python code | **FOUND** — caused 3/12 Go escalations in run-118 |
| 7.5.2 | `render_def_line()` is language-aware | `grep -n 'render_def_line' src/startd8/micro_prime/models.py` | Always produces Python `def foo():` syntax for any language. Go elements get `def tracker():` instead of `func tracker()` | **FOUND** — produces invalid hybrid code |
| 7.5.3 | Element prompts use language-appropriate stub markers | `grep -rn 'raise NotImplementedError' src/startd8/micro_prime/prompt_builder.py` | Hardcoded Python stub marker in instructions. Go should say `panic("not implemented")`, Java `throw new UnsupportedOperationException()` | **FOUND** — all 12 Go elements got Python instructions |
| 7.5.4 | Indentation instructions match language | `grep -rn 'indent.*spaces\|4-space' src/startd8/micro_prime/prompt_builder.py` | Python 4-space indentation hardcoded. Go mandates tabs; Java/C# use configurable spaces | **FOUND** — Go elements told to use spaces |
| 7.5.5 | `ast.parse()` calls in validation paths are language-gated | `grep -rn 'ast\.parse(' src/startd8/micro_prime/` | Python AST used on non-Python code. Should dispatch via `_try_parse()` or `LanguageProfile.validate_syntax()` | **OK** — `ast_parse_valid()` in `structural_verify.py` dispatches correctly |
| 7.5.6 | `extract_function_body()` is language-aware | `grep -rn 'extract_function_body' src/startd8/micro_prime/engine.py` | Uses Python AST to extract body from `def` statement. Will fail silently on Go `func` | **FOUND** — non-Python should use `full_function` mode (REQ-MPL-102) |
| 7.5.7 | `_hoist_leading_imports()` is language-aware | `grep -rn '_hoist_leading_imports' src/startd8/micro_prime/repair.py` | Python `import`/`from` hoisting logic applied to Go/Java imports. May mishandle `import "pkg"` (Go) or `import pkg.Class` (Java) | **CHECK** — verify behavior with Go import syntax |
| 7.5.8 | Repair steps that produce syntax are language-gated | `grep -rn '_current_repair_language_id' src/startd8/micro_prime/repair.py` | Steps like `bare_statement_wrap`, `import_completion`, `future_import_reorder` that produce Python syntax must check language before modifying | **FOUND** — `bare_statement_wrap` has no language guard |

**Procedure:** For each grep match, verify the function either:
1. Checks `_current_repair_language_id` or `language_id` before producing language-specific output, OR
2. Uses `LanguageProfile` methods that dispatch by language, OR
3. Is truly language-agnostic (e.g., `fence_strip` which removes markdown fences regardless of language)

If none of the above: **flag as Python leakage** and file a requirement.

---

## Stage 8: Semantic Checks and Postmortem

Post-generation quality measurement and cross-run learning.

| # | Checkpoint | File(s) | Audit Question | Go Status |
|---|-----------|---------|----------------|-----------|
| 8.1 | Semantic check module exists | `validators/{lang}_semantic_checks.py` | Does a language-specific check function exist? | Done (6 checks) |
| 8.2 | Checks wired into disk compliance | `forward_manifest_validator.py` | Does `validate_disk_compliance()` call the language's checks for `.{ext}` files? | Done |
| 8.3 | All check categories have `_SEMANTIC_CATEGORY_TO_SUGGESTION` entries | `prime_postmortem.py` | Does every semantic category route to a Kaizen suggestion? | Done (all 6 Go categories mapped) |
| 8.4 | All root causes have `CAUSE_TO_SUGGESTION` entries | Same | Does every root cause have a hint text and target phase? | Done |
| 8.5 | Cross-language contamination check exists | Semantic checks module | Does the check detect Python/Go/Java artifacts in this language's files? | Done (Python detection; Go detection planned for Node.js) |
| 8.6 | False positive hardening | Semantic checks module | Are string literals, comments, and raw strings excluded from contamination detection? | **Gap** — substring match, not line-anchored |

**Hayai test:** Run semantic checks on a clean file — zero findings. Run on a file with known anti-patterns — correct findings. Run on a file with anti-patterns in string literals — zero false positives.

---

## Summary: Common Gap Patterns Across Languages

These patterns recur when enabling a new language. Check for them proactively.

| Gap Pattern | Description | Detection | Fix Direction | Requirement |
|-------------|-------------|-----------|---------------|-------------|
| **Python syntax leakage in repair** | Repair steps produce Python `def`/`class` wrappers for non-Python code. `bare_statement_wrap` generates `def tracker():` for Go functions, causing `ast_failure` escalation. | `bare_statement_wrap` in non-Python element `repair_steps` + `ast_failure` escalation | Language guard on repair steps that produce syntax; expand `_detect_definition_line()` to recognize all 5 languages | REQ-MPL-100 |
| **Python-centric element prompts** | User prompt contains hardcoded `raise NotImplementedError`, `4-space indentation`, `def` keyword instructions regardless of target language. System prompt IS language-aware but user prompt is not. | Inspect element prompts in `kaizen-prompts/` for Python keywords in non-Python elements | Thread `LanguageProfile` through prompt builder; use `stub_marker_text`, language-specific indent rules | REQ-MPL-101 |
| **Body-only mode on non-Python** | Body-only generation mode depends on Python `ast.parse()` body extraction and `bare_statement_wrap` fallback. Non-Python elements should always use `full_function` mode. | `element_prompt_mode` = `body` for non-Python elements | Force `full_function` when `language_id != "python"` | REQ-MPL-102 |
| **100% fence-strip rate** | LLM always wraps output in markdown fences despite prompt instruction | `fence_strip` in every element's `repair_steps` | Pre-strip fences before validation, not after failure; reinforce in user prompt | REQ-MPL-103 |
| **Postmortem language blind spot** | Repair-induced language mismatch classified as generic `ast_failure`, not as pipeline bug | 3 `ast_failure` escalations in run-118 with `bare_statement_wrap` in steps but no language-specific root cause | Add `REPAIR_LANGUAGE_MISMATCH` root cause to postmortem taxonomy | REQ-MPL-104 |
| **Template granularity mismatch** | Templates match function-level patterns but elements are file-level | `template_used: false` on all elements | Enable function-level decomposition for the language | Deferred |
| **Splicer exists but unused** | Language splicer wired in dispatch but never called | Zero splice operations in postmortem | Same as above — depends on function-level decomposition | Deferred |
| **Python AST decomposer bottleneck** | SIMPLE decomposer uses `ast.parse()`, can't break non-Python files into functions | Single element per file for non-Python | Add language-aware decomposition using the language's own parser | Deferred |
| **Semantic check false positives** | Contamination detection uses substring match instead of line-anchored patterns | False CRITICAL findings on clean files with string literals | Line-level detection with comment/string exclusion |
| **Missing semantic repair config** | Repair steps exist but `semantic_repair_categories` is empty | Zero semantic repairs despite findings | Wire categories into `RepairConfig` in `PrimeContractorWorkflow` |
| **Coding standards compliance gap** | Standards injected at enrichment but LLM doesn't follow them | Recurring semantic findings for patterns covered by coding_standards | Elevate critical patterns to P0 constraints; add template-level enforcement |

---

## Checklist: New Language Enablement (Copy-Paste)

```
Language: _____________
Profile file: languages/_____________.py

Stage 0: Foundation
[ ] 0.1 Profile class implemented
[ ] 0.2 Entry point registered in pyproject.toml
[ ] 0.3 source_extensions populated
[ ] 0.4 coding_standards populated
[ ] 0.5 system_prompt_role populated
[ ] 0.6 sanitize_code_examples() implemented
[ ] 0.7 validate_syntax() implemented
[ ] 0.8 stub_patterns populated

Stage 1: Enrichment
[ ] 1.1 Language resolves from target_files
[ ] 1.2 coding_standards in seed context
[ ] 1.3 language_role in seed context
[ ] 1.4 Task descriptions sanitized
[ ] 1.5 Design doc sections sanitized
[ ] 1.6 Batch context resolves language-neutral files

Stage 2: Spec Building
[ ] 2.1 Coding standards at P0 in spec prompt
[ ] 2.2 build_project_context_section() produces rules
[ ] 2.3 Spec inputs sanitized (defense-in-depth)
[ ] 2.4 Spec LLM output sanitized
[ ] 2.5 Security constraints language-aware

Stage 3: Element Routing
[ ] 3.1 _is_non_python_file() returns False
[ ] 3.2 Extensions in _get_microprime_extensions()
[ ] 3.3 Complexity classifier assigns tiers
[ ] 3.4 Build files handled deterministically
[ ] 3.5 Dockerfiles handled

Stage 4: Templates
[ ] 4.1 Templates registered
[ ] 4.2 has_templates_for() returns True
[ ] 4.3 Match functions evaluate correctly
[ ] 4.4 Structural verify language-aware
[ ] 4.5 Templates match in practice

Stage 5: Decomposition & Splicer
[ ] 5.1 Parser extracts declarations
[ ] 5.2 Splicer dispatch wired
[ ] 5.3 Body replacement works
[ ] 5.4 Decomposer produces function-level elements
[ ] 5.5 Splicer exercised in practice

Stage 6: Generation & Validation
[ ] 6.1 ast_parse_valid() dispatches correctly
[ ] 6.2 _try_parse() calls language tool
[ ] 6.3 Repair receives language_id
[ ] 6.4 fence_strip handles language fences
[ ] 6.5 Post-gen cleanup runs language tools
[ ] 6.6 Fence-strip rate < 50%
[ ] 6.7 full_function mode forced for non-Python (REQ-MPL-102)
[ ] 6.8 Pre-extraction fence strip active (REQ-MPL-103)

Stage 7: Repair
[ ] 7.0 bare_statement_wrap guarded for non-Python (REQ-MPL-100)
[ ] 7.0.1 _detect_definition_line() recognizes this language's keywords
[ ] 7.1 Syntax repair route exists
[ ] 7.2 Import repair route exists
[ ] 7.3 Semantic repair routes exist
[ ] 7.4 Step factories registered
[ ] 7.5 Canonical order correct
[ ] 7.6 Semantic repair categories configured

Stage 7.5: Python Leakage Audit (REQ-MPL-105)
[ ] 7.5.1 _detect_definition_line() recognizes this language
[ ] 7.5.2 render_def_line() is language-aware (or unreachable)
[ ] 7.5.3 Element prompts use language stub markers (REQ-MPL-101)
[ ] 7.5.4 Indentation instructions match language
[ ] 7.5.5 ast.parse() calls in validation are language-gated
[ ] 7.5.6 extract_function_body() bypassed for non-Python
[ ] 7.5.7 _hoist_leading_imports() handles language import syntax
[ ] 7.5.8 All syntax-producing repair steps are language-gated

Stage 8: Semantic Checks & Postmortem
[ ] 8.1 Semantic check module exists
[ ] 8.2 Checks wired into disk compliance
[ ] 8.3 All categories have suggestion mappings
[ ] 8.4 All root causes have hint text
[ ] 8.5 Cross-language contamination check
[ ] 8.6 False positive hardening
[ ] 8.7 REPAIR_LANGUAGE_MISMATCH root cause wired (REQ-MPL-104)
```
