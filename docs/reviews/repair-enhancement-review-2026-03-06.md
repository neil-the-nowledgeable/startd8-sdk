# Repair Enhancement Review: Defense-in-Depth for PARTIAL Quality Verdicts

**Date**: 2026-03-06
**Context**: Run-004 post-mortem revealed 3 PARTIAL and 2 FAIL verdicts despite pipeline PASS (aggregate 1.0). Mottainai audit identified 6 findings (F1-F6). Three upstream fixes were implemented in commit `beccdfd`.

---

## 1. What the Implemented Fixes Cover

The committed fixes address **structural data loss** — information that existed in the plan but was discarded or degraded before reaching the LLM prompt.

| Fix | Addresses | Defense Layer |
|-----|-----------|---------------|
| Class-aware signature parsing | F1: `api_signatures` stripped | **Layer 1: Structural identity** — the LLM now knows `CustomJsonFormatter` extends `jsonlogger.JsonFormatter` |
| Lead Contractor injection parity | F2: `ForwardElementSpec` unused | **Layer 1: Structural identity** — signatures, bases, return types reach the Lead Contractor prompt |
| Richer binding_text | F1+F3: detail stripped | **Layer 1: Structural identity** — `getJSONLogger(name: str) -> logging.Logger` not just `getJSONLogger` |

These fixes eliminate the **serialize-and-forget** and **compute-but-don't-forward** anti-patterns for data that was already in the pipeline. They are necessary but insufficient.

### What Layer 1 Does NOT Prevent

The three PARTIAL verdicts from run-004 each had a **behavioral** divergence, not just a structural one:

| PARTIAL | Structural (now fixed) | Behavioral (still unaddressed) |
|---------|----------------------|-------------------------------|
| PI-001 logger | Class `CustomJsonFormatter(jsonlogger.JsonFormatter)` now emitted | Timestamp must use `record.created` (float epoch), not `datetime.now().isoformat()`. Format string `'%(timestamp)s %(severity)s %(name)s %(message)s'` must be constructor arg. |
| PI-002 logger | Same class contract now emitted | Same behavioral gap — identical code, different service |
| PI-003 email_server | Class/method signatures now richer | `select_autoescape(['html', 'xml'])` required. `TracerProvider` + `OTLPSpanExporter` + `BatchSpanProcessor` chain required. Module-level template loading, not class-level. `while True: time.sleep(3600)` lifecycle pattern. |

Knowing that `CustomJsonFormatter` extends `jsonlogger.JsonFormatter` tells the LLM **what to build**. It does not tell it **how the timestamp field works** or **what constructor arguments to pass**. The LLM will still invent implementations for these behavioral details.

---

## 2. Defense-in-Depth: Remaining Layers

### Layer 2: Reference AST Behavioral Contracts (HIGH VALUE)

**Original analysis section**: 4, 9.3
**Status**: Not implemented. Highest-impact remaining gap.
**Still a good idea**: Yes — this is the primary defense against behavioral non-determinism.

The extractor already uses `ast` for signature parsing. A new extraction stage would parse reference source files and emit contracts for the three currently-dead `ContractCategory` values:

| Reference AST Pattern | Category | Binding | Prevents |
|----------------------|----------|---------|----------|
| `log_record['timestamp'] = record.created` | `FORMULA` | `[BINDING] formula=record.created \| timestamp field uses record.created (float epoch)` | PI-001/PI-002: three different timestamp implementations |
| `CustomJsonFormatter('%(timestamp)s ...')` | `RENDER_PATTERN` | `[BINDING] pattern=%(timestamp)s %(severity)s %(name)s %(message)s` | PI-001/PI-002: missing format string constructor arg |
| `select_autoescape(['html', 'xml'])` | `INFRASTRUCTURE` | `[BINDING] dependency=select_autoescape \| Jinja2 Environment must use select_autoescape` | PI-003: omitted autoescape |
| `OTLPSpanExporter(endpoint=..., insecure=True)` | `INFRASTRUCTURE` | `[BINDING] dependency=OTLPSpanExporter \| Use OTLPSpanExporter with COLLECTOR_SERVICE_ADDR` | PI-003: missing OTel exporter chain |
| `os.environ.get("COLLECTOR_SERVICE_ADDR")` | `CONFIG_KEY` | `[BINDING] env_var=COLLECTOR_SERVICE_ADDR \| OTel exporter endpoint` | PI-003: env var not surfaced |

**Why this matters even with Fix 1-3**: The structural fixes tell the LLM "there's a class called CustomJsonFormatter extending jsonlogger.JsonFormatter with an add_fields method." The LLM will generate that class. But inside `add_fields`, it must choose how to populate `log_record['timestamp']`. Without a `FORMULA` contract, the LLM guesses — and run-004 proved it guesses differently each time.

**Scope**: This is a regeneration-specific capability. It requires access to reference source files, which only exist when the pipeline is regenerating existing code. For greenfield generation, this layer doesn't apply. The precedence infrastructure already exists (`"source-ast": 0` at line 70 of the extractor).

### Layer 3: Quality Feedback into Kaizen (MEDIUM VALUE)

**Original analysis section**: 5, 9.4
**Status**: Not implemented. Closes the feedback loop.
**Still a good idea**: Yes — without this, the pipeline cannot learn from PARTIAL verdicts.

Current state:
- Post-mortem reports `aggregate_score: 1.0` and `verdict: PASS` for runs that produced 3 PARTIAL files
- `kaizen-suggestions.json`: `{"suggestions": []}` — empty
- `kaizen-correlation.json`: `{"total_data_points": 0}` — no signal
- The Kaizen system has 6 layers (post-mortem, metrics, trends, prompt capture, feedback, correlation) but produces no actionable output

What's needed:
1. **Quality evaluation in post-mortem**: Extend `prime-postmortem-report.json` to include a `quality_evaluation` field that captures structural equivalence verdicts (PASS/PARTIAL/FAIL) per file, not just "did code generate"
2. **PARTIAL-to-contract mapping**: Each PARTIAL verdict maps to specific missing contract categories (e.g., PI-001 PARTIAL → missing FORMULA for timestamp, missing RENDER_PATTERN for format string)
3. **Suggestions emission**: `kaizen-suggestions.json` should emit contract-shaped suggestions from PARTIAL evaluations, which the next run's extractor picks up as tentative contracts

**Why this matters even with Layer 2**: Reference AST analysis is deterministic and proactive — it catches what it's programmed to catch. Quality feedback is reactive and catches everything else. A new behavioral pattern that the AST analyzer doesn't recognize will still produce a PARTIAL verdict, which the feedback loop can surface as a suggestion for the next run.

**Dependency**: Requires a structural equivalence evaluator (comparison of generated code against reference). This could be AST-diff-based or a simpler heuristic (presence of specific imports, class bases, function signatures).

### Layer 4: Requirements Reconciliation (MEDIUM VALUE)

**Original analysis section**: Finding F4, 9.5
**Status**: Not implemented. Prevents contradictions before generation.
**Still a good idea**: Yes — catches upstream errors that no amount of prompt enrichment can fix.

The run-004 requirements for PI-001/PI-002 specified:
```
- `timestamp` -- ISO-8601 formatted time
```

The reference uses `record.created` — a float epoch. Even if the forward manifest had a perfect `FORMULA` contract saying "use record.created", the requirements text says "ISO-8601." The LLM receives contradictory instructions and must choose.

A reconciliation step would:
1. Parse reference AST contracts (Layer 2 output)
2. Compare against requirements text for semantic conflicts
3. Surface conflicts as warnings before generation begins
4. Optionally auto-correct requirements or flag for human review

**Scope**: This is lightweight — a text-matching heuristic against contract descriptions would catch the ISO-8601 vs epoch conflict. Full semantic reconciliation is harder but not necessary for the common case.

### Layer 5: Server Lifecycle Pattern Contracts (LOW VALUE)

**Original analysis section**: Table row 6 (while True / time.sleep)
**Status**: Not needed as a separate layer.
**Still a good idea**: No — this is adequately handled by Layer 2 (Reference AST) or requirements.

The `while True: time.sleep(3600)` vs `signal.signal + wait_for_termination()` divergence in PI-003 is an implementation style preference. Both are valid gRPC server lifecycle patterns. If structural equivalence to the reference is the goal, a `RENDER_PATTERN` contract from Layer 2 handles it. If not, this is acceptable variation.

---

## 3. Defense-in-Depth Stack Summary

```
Layer 4: Requirements Reconciliation
  Catches: Contradictions between requirements text and reference behavior
  Gate: Pre-generation (before any LLM call)
  Status: NOT IMPLEMENTED

Layer 3: Quality Feedback (Kaizen)
  Catches: Any behavioral divergence not caught by Layers 1-2
  Gate: Post-generation (feeds into next run)
  Status: NOT IMPLEMENTED (Kaizen produces no output)

Layer 2: Reference AST Behavioral Contracts
  Catches: Formulas, patterns, config keys, infrastructure setup
  Gate: Extraction time (forward manifest population)
  Status: NOT IMPLEMENTED (FORMULA, RENDER_PATTERN, CONFIG_KEY categories unused)

Layer 1: Structural Identity Contracts  [IMPLEMENTED]
  Catches: Class names, base classes, signatures, return types, element specs
  Gate: Extraction time + prompt injection
  Status: IMPLEMENTED (commit beccdfd)
```

Each layer catches a different class of defect. Layers 1+2 together would have prevented all 3 PARTIAL verdicts in run-004. Layer 3 provides the safety net for novel patterns. Layer 4 prevents the pipeline from generating code against self-contradictory instructions.

---

## 4. Prioritized Recommendations

### P0: Reference AST Behavioral Contracts (Layer 2)

Highest impact-to-effort ratio. The extractor already uses `ast`. The `FORMULA`, `RENDER_PATTERN`, and `CONFIG_KEY` contract categories already exist in the schema. The `InterfaceContract` model already has `formula`, `pattern`, `env_var`, and `constant_value` fields. `compute_binding_text()` already has branches for all three categories. The only missing piece is the extraction logic.

Concrete scope:
- New function `extract_from_reference_source(filepath: Path) -> list[InterfaceContract]` in `forward_manifest_extractor.py`
- Patterns to detect: `ast.Assign` (formula), `ast.Call` with string literal args (render_pattern), `os.environ` / `os.getenv` (config_key)
- Confidence level: `EXPLICIT` (derived from actual source code)
- Integration point: called by `DeterministicExtractor.extract()` when reference source paths are provided

### P1: Quality Evaluation in Kaizen (Layer 3)

Medium effort but essential for the closed-loop promise. Without this, the Kaizen system is decorative — it collects data but produces no suggestions.

Concrete scope:
- Add `quality_evaluation` field to post-mortem report schema
- Implement structural equivalence evaluator (AST-based comparison of generated vs reference)
- Map PARTIAL verdicts to missing contract categories
- Emit suggestions into `kaizen-suggestions.json`

### P2: Requirements Reconciliation (Layer 4)

Low effort, high specificity. Prevents a narrow but impactful class of errors.

Concrete scope:
- Post-extraction validation step comparing contract descriptions against requirements text
- Simple text-matching heuristic (e.g., "ISO-8601" in requirements vs "record.created" in contract)
- Output: warnings surfaced before generation begins

---

## 5. What Was Dropped from the Original Analysis

| Original Item | Disposition | Reason |
|--------------|------------|--------|
| Server lifecycle pattern (while True vs signal) | Dropped | Implementation style preference, not a defect. Handled by Layer 2 if reference equivalence is the goal. |
| Kaizen correlation layer data starvation | Absorbed into P1 | Correlation needs 10+ data points. Quality evaluation (P1) would produce the data points needed. |
| Kaizen empty suggestions | Absorbed into P1 | Suggestions are empty because quality evaluation doesn't exist. Fix the input, not the empty output. |

---

## 6. Relationship to Repair Pipeline (REQ-RPL)

The existing repair pipeline (REQ-RPL-001 through REQ-RPL-503) operates at a different level — it repairs code that fails validation (syntax errors, missing imports, test failures). The defense-in-depth layers described here operate upstream of repair:

- **Layers 1-2** reduce the need for repair by giving the LLM better instructions
- **Layer 3** feeds repair outcomes back into future runs
- **Layer 4** prevents contradictory instructions that repair cannot fix

The repair pipeline remains the last-resort safety net for code that passes all contract checks but still fails to compile or run. Defense-in-depth reduces its workload but does not replace it.
