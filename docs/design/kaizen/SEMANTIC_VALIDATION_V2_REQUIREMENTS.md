# Semantic Validation v2 — Diagnose Before You Prescribe

**Date:** 2026-03-16
**Status:** Draft
**Author:** Human + Agent collaboration
**Derived From:** 7 production runs (047–053) with L1–L6 active, SEMANTIC_VALIDATION_GAP_ANALYSIS.md, run-053 individual file grading
**Principle:** Iterative diagnostic precision — identify root causes with confidence before attempting automated repair. Fixing symptoms without understanding causes creates brittle heuristics that mask the real problem.

---

## 1. Design Philosophy

### The Anti-Pattern We're Avoiding

The temptation is to jump from "we detected a bad import" to "let's auto-fix it." This is the symptom-fixing trap:

- **Symptom**: `from emailservice import demo_pb2` doesn't resolve
- **Quick fix**: Auto-rewrite to `import demo_pb2` (local import)
- **Root cause**: The LLM doesn't understand the project's module layout because the prompt doesn't describe it
- **Result of quick fix**: The import resolves locally, but the code still doesn't work because the proto stubs aren't in the right directory. The postmortem now scores 1.0 for a file that's just as broken.

Auto-repair that improves scores without improving code is **worse than no repair** — it removes the signal that tells us what to fix in the prompt pipeline.

### The Iterative Approach

Three stages, each building confidence before the next can activate:

```
Stage 1: DIAGNOSE    — Detect and classify semantic errors with precision
                       (L1–L6 active today; L3+, L5 alias, L8–L10 new)
                       Output: structured issues, severity, category, evidence

Stage 2: CORRELATE   — Connect diagnostic findings to upstream causes
                       (Kaizen feedback loop, prompt characteristic correlation)
                       Output: "files with >2 import errors correlate with
                       missing service_metadata in prompt context"

Stage 3: REPAIR      — Fix the upstream cause, not the downstream symptom
                       (Prompt enrichment, seed improvements, generation hints)
                       Output: better prompts → better code → fewer diagnostics
                       Gate: only activate per-category repair when that category's
                       false positive rate is <5% across 10+ runs
```

**Stage 3 does not auto-edit generated code.** It fixes the inputs (prompts, seeds, context) that produce bad outputs. The generator should produce correct code, not have its mistakes silently patched afterward.

---

## 2. Current State (Stages 1–2 Baseline)

### What's Working (L1–L6, runs 047–053)

| Layer | Status | Run-053 Findings | Accuracy |
|-------|--------|-----------------|----------|
| L1: Import Resolution | Active | 5 errors (google.*, emailservice, recommendationservice) | ~60% true positive — GCP/project-local imports are FPs |
| L2: Cross-Scope Duplicates | Active | 0 | Correct (none to catch) |
| L3: Dockerfile Digest | Active | 0 | **Missed**: fabricated 64-char digest in PI-013 (grade F) |
| L4: Factory Return | Active | 0 | Correct (`create_app()` has return) |
| L5: Requirements Cross-Check | Active (just wired) | 1 orphan_dependency | Minor FP — alias resolution gap |
| L6: Expression Lint | Active | 0 | Correct (no discarded returns this run) |

### What's Working (Scoring + Verdict)

| Mechanism | Status | Run-053 Evidence |
|-----------|--------|-----------------|
| Severity-weighted penalty | Active | PI-003: 2 errors → score 0.88 (was 0.91 with uniform penalty) |
| Semantic verdict gate | Active | PI-003: `PARTIAL:semantic` (first activation) |
| Repair attribution threading | Active | All 24 elements report `ast_valid_before_repair`, `repair_attribution` |

### What's Not Working

| Gap | Impact | Root Cause |
|-----|--------|------------|
| L1 false positives on GCP imports | 3/5 L1 errors are FPs | `google.*` packages use non-standard import paths that don't match `requirements.in` via `pypi_to_import` |
| L3 misses fabricated digests | Grade-F Dockerfile passes all checks | Length check (64 chars) is necessary but not sufficient |
| L5 alias resolution gap | 1 FP on `google-cloud-secret-manager` | Reverse alias doesn't match `from google.cloud import secretmanager` |
| No detection of copy-paste string constants | Grade-D logger (hardcoded wrong service name) | No cross-file or intra-file consistency check for service identity strings |
| No detection of method-vs-function call errors | `self.index()` vs `index(self)` | Requires scope/type awareness beyond current AST walk |
| No detection of fabricated package names | `langchain_google_alloydb_pg` (underscores) | PEP 508 allows underscores; heuristic needed |

---

## 3. Stage 1 Requirements: Improve Diagnostic Precision

### Principle: Fix the Detectors Before Adding New Ones

The existing L1–L6 layers have known false positive and false negative patterns. Hardening these is higher ROI than adding new layers. Each requirement below either reduces false signals or catches issues that escaped existing layers.

---

### REQ-SV2-100: L3+ Dockerfile Digest Plausibility (P0)

**Problem:** Run-053 PI-013 has `sha256:9b4929a7826e4b8e1a2c4d5f6e7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f56` — a 64-char digest that passes L3's length check but is obviously fabricated (sequential hex pattern). This file is grade F (unbuildable) but scored 1.0.

**Requirement:** After the existing length check, apply plausibility heuristics:

1. **Sequential byte detection** — flag digests where ≥8 consecutive bytes form an arithmetic sequence (e.g., `0d1e2f3a4b5c6d7e`)
2. **Entropy check** — flag digests with Shannon entropy below 3.0 bits/char (real SHA256 digests average ~3.9). Threshold tuned against known-good digests from runs 049–053.
3. **Repeated pattern detection** — flag digests where any 4-char substring repeats ≥4 times

Severity: `error` (fabricated digest = build failure).

**Category:** `dockerfile_digest_fabricated`

**Success criterion:** PI-013's fabricated digest caught. Zero false positives on PI-010, PI-011, PI-012 (valid digests from the same runs).

**Essential complexity:** ~20 LOC. Shannon entropy is `−Σ(p·log₂p)` over hex char frequencies — 4 lines of code.

---

### REQ-SV2-200: L1 Import Resolution — Reduce GCP False Positives (P0)

**Problem:** 3 of 5 L1 errors in run-053 are false positives on `google.api_core`, `google.auth`, `google.cloud`. These packages use non-standard import paths: `google-api-core` installs as `google.api_core`, `google-auth` installs as `google.auth`, `google-cloud-secret-manager` installs as `google.cloud.secretmanager`. The existing `pypi_to_import` map doesn't cover the `google.*` namespace family.

**Requirement:** Extend `package_aliases.py` with the Google Cloud namespace family:

```python
# Google Cloud packages use dotted import paths
"google-api-core": "google.api_core",
"google-auth": "google.auth",
"google-cloud-secret-manager": "google.cloud.secretmanager",
"google-cloud-storage": "google.cloud.storage",
"google-cloud-aiplatform": "google.cloud.aiplatform",
```

Also add a **prefix-family rule**: any import starting with `google.` where a sibling `requirements.in` contains any `google-*` package should downgrade from `error` to `warning`. The `google.*` namespace is a known shared namespace across dozens of PyPI packages — resolving the exact package requires deep dependency analysis that's out of scope.

**Success criterion:** PI-003, PI-006, PI-008 false positives eliminated or downgraded to warning. PI-004 (`from emailservice import demo_pb2`) remains `error` (correct — not a Google package).

**Essential complexity:** ~15 LOC in `package_aliases.py`, ~10 LOC for prefix-family rule in `_validate_import_resolution()`.

---

### REQ-SV2-300: L5 Alias Resolution Fix (P1)

**Problem:** PI-016 flagged `google-cloud-secret-manager` as orphan dependency, but the sibling Python file does `from google.cloud import secretmanager`. The L5 check compares the `pypi_to_import()` result (`google.cloud.secretmanager`) against actual imports (`google.cloud`). The actual import is a prefix of the expected import, but the current match logic requires exact or `startswith` from the import side, not from the package side.

**Requirement:** In `_validate_requirements_coverage()`, add reverse prefix matching: if `expected_import.startswith(actual_import + ".")`, consider the package used. This handles `from google.cloud import secretmanager` matching `google-cloud-secret-manager`.

**Essential complexity:** 2 lines added to the `found` check in `_validate_requirements_coverage()`.

---

### REQ-SV2-400: L8 — Service Identity Constant Validation (P1)

**Problem:** Run-053 PI-002 (`recommendationservice/logger.py`) is a near-identical copy of `emailservice/logger.py` with hardcoded `'emailservice'` in 3 places. All recommendation service logs are mislabeled. Grade D. No existing layer catches this because it requires understanding that a string constant should match the service directory name.

**Requirement:** New check — when a Python file resides in a service directory (detected by presence of `Dockerfile` or `requirements.in` as sibling), verify that string literals used in logging configuration (`getLogger(name)`, `logging.basicConfig(...)`, custom formatter `component` fields) reference the correct service name.

**Detection heuristic:**
1. Derive expected service name from the file's parent directory name
2. Walk AST for string literals passed to:
   - `logging.getLogger(<str>)` — first argument
   - `getLogger(<str>)` / `getJSONLogger(<str>)` — first argument
   - Keyword argument `component=<str>` or `service=<str>` in any call
3. If the string contains a different service directory name (from known siblings), flag it

```python
{"category": "service_identity_mismatch", "severity": "error",
 "message": f"Logger initialized with '{found_name}' but file is in '{expected_service}/' directory",
 "line": node.lineno, "symbol": found_name}
```

**What this is NOT:** This is not a generic "check all strings for correctness" — it targets a specific, recurring LLM failure pattern (copy-paste across service directories) with a narrow, high-precision heuristic.

**Essential complexity:** ~40 LOC. AST walk for Call nodes with string args matching `*Logger*` / `*logger*` patterns.

---

### REQ-SV2-500: L9 — TaskSet Method Resolution (P2)

**Problem:** Run-053 PI-009 (`locustfile.py`) has `self.index()` in `on_start()` but `index` is a module-level function, not a method on `UserBehavior`. This is a recurring error across runs — the LLM confuses module-level functions with instance methods when they share a name. Grade B-.

**Requirement:** New check — when a class method body contains `self.<name>(...)` where `<name>` is also defined as a module-level function (not a method on that class or its bases), flag it.

**Detection heuristic:**
1. Collect all module-level function names
2. For each class, collect method names (from `ast.FunctionDef` children of `ast.ClassDef`)
3. Walk class method bodies for `ast.Attribute` nodes where `value` is `ast.Name(id='self')` and `attr` matches a module-level function name but NOT a method on the class

```python
{"category": "method_resolution", "severity": "warning",
 "message": f"'self.{name}()' called but '{name}' is a module-level function, not a method of '{class_name}'",
 "line": node.lineno, "symbol": name}
```

Severity: `warning` (not `error`) — Python allows this pattern via `__getattr__` or dynamic method assignment, though in generated code it's almost always a bug.

**Essential complexity:** ~35 LOC. Two-pass AST walk: collect names, then check references.

---

### REQ-SV2-600: L10 — Dead Code Detection (P2)

**Problem:** Run-053 PI-004 and PI-007 (test client files) are grade C/C- — they define functions that no other generated file calls. They're scaffolding artifacts, not functional code. Similarly, `locustfile.py` defines `empty_cart()` and `logout()` that aren't in `UserBehavior.tasks`.

**Requirement:** New check — detect module-level functions that are:
1. Not called by any other function in the same file
2. Not referenced in any `__all__` list
3. Not named `main` or prefixed with `_` (private)
4. Not a class method
5. Not in a `if __name__ == "__main__"` block

These are flagged as warnings, not errors — dead code doesn't break anything, but it indicates incomplete generation.

```python
{"category": "unreachable_function", "severity": "warning",
 "message": f"Module-level function '{name}' is defined but never called within the file",
 "line": node.lineno, "symbol": name}
```

**Scope constraint:** Single-file analysis only. Cross-file reachability is out of scope (would require manifest-level call graph).

**Essential complexity:** ~30 LOC. Collect function defs, then collect all `Name` references in non-def contexts. Diff.

---

## 4. Stage 2 Requirements: Correlate Diagnostics to Upstream Causes

Stage 2 does not add new checks. It makes existing diagnostic data usable for root cause identification.

---

### REQ-SV2-700: Semantic Issue Category Aggregation in Kaizen Metrics (P1)

**Problem:** `kaizen-metrics.json` includes `avg_assembly_delta` but not a per-category breakdown of semantic issues. The Kaizen correlation system can see "this run had more semantic errors" but can't distinguish "all errors were import resolution" from "errors were distributed across 4 categories."

**Requirement:** Add to `kaizen-metrics.json`:

```json
{
  "semantic_issue_breakdown": {
    "import_resolution": {"error": 5, "warning": 0},
    "orphan_dependency": {"error": 0, "warning": 1},
    "dockerfile_digest_fabricated": {"error": 0, "warning": 0},
    "service_identity_mismatch": {"error": 0, "warning": 0}
  },
  "semantic_verdict_downgrades": 1,
  "features_with_semantic_errors": ["PI-003", "PI-004", "PI-006", "PI-007", "PI-008"]
}
```

This enables Kaizen trend analysis per category: "import_resolution errors are declining across runs" or "service_identity_mismatch appeared in run-053 for the first time."

**Essential complexity:** ~15 LOC in `run_prime_postmortem.py` — aggregate from `FeaturePostMortem.semantic_issue_summary` (property already exists).

---

### REQ-SV2-800: False Positive Tracking (P1)

**Problem:** L1 has ~40% false positive rate (3/5 issues in run-053 are FPs). L5 has 100% (1/1 is FP). Without tracking FP rates per category, we can't know when a detector is reliable enough to gate on.

**Requirement:** Add an optional `known_false_positives` parameter to `validate_disk_compliance()`. When provided (dict of `{symbol: reason}`), matching issues are annotated with `"false_positive": true` and excluded from severity-weighted scoring.

The postmortem caller maintains a per-project FP allowlist that grows as users mark FPs. This is a manual feedback loop, not automatic — the point is to track the rate, not suppress issues silently.

Kaizen metrics include:
```json
{
  "semantic_fp_rate": {
    "import_resolution": 0.60,
    "orphan_dependency": 1.00
  }
}
```

**Gate for Stage 3:** A category becomes eligible for automated repair only when its FP rate drops below 5% across 10+ consecutive runs. This prevents repairing based on unreliable signals.

**Essential complexity:** ~25 LOC. Filter + annotate + count.

---

### REQ-SV2-900: Prompt Characteristic → Semantic Error Correlation (P2)

**Problem:** The Kaizen correlation system has `total_prompt_words ρ=+0.259` as the strongest signal, but this is against PASS/FAIL — not against semantic quality. With `PARTIAL:semantic` verdicts now flowing, we can correlate prompt features against semantic issue categories.

**Requirement:** Extend `kaizen-correlation.json` to include per-category correlations:

```json
{
  "category_correlations": {
    "import_resolution": {
      "strongest": "context_key_count",
      "rho": -0.45,
      "interpretation": "moderate negative — fewer context keys → more import errors"
    }
  }
}
```

This tells us: "import errors correlate with missing context in prompts." That's the signal Stage 3 needs to know WHERE in the prompt pipeline to intervene.

**Prerequisite:** 20+ labeled data points per category (currently only 1 run with `PARTIAL:semantic`). This requirement is forward-looking — the infrastructure should be built now, but meaningful correlations won't emerge until ~10 more runs.

**Essential complexity:** ~30 LOC in `kaizen_correlation.py` — group by category, compute Spearman per group.

---

## 5. Stage 3 Requirements: Upstream Repair (Deferred)

Stage 3 is intentionally **not specified in detail** because it depends on Stage 2 insights. The requirements below describe the repair philosophy and activation criteria, not implementations.

---

### REQ-SV2-1000: Repair Activation Gate

**Requirement:** No automated repair mechanism for a semantic issue category is activated until:

1. The category's false positive rate is below 5% across 10+ consecutive runs (from REQ-SV2-800)
2. The Kaizen correlation system has identified at least one prompt characteristic with |ρ| > 0.3 for that category (from REQ-SV2-900)
3. A human has reviewed the correlation finding and approved the repair strategy

**Rationale:** Premature repair is the primary risk. A repair that improves scores without improving code teaches the Kaizen system the wrong lesson — it sees "scores improved" and attributes it to unrelated prompt changes, poisoning the correlation data.

---

### REQ-SV2-1100: Repair Targets Inputs, Not Outputs

**Requirement:** Automated repair operates on the generation pipeline inputs (prompts, context, seed data), not on generated code.

Examples of permitted repairs:
- **Kaizen hints**: "Previous runs had import_resolution errors in emailservice — ensure proto import paths use relative imports"
- **Context enrichment**: Add `service_directory_layout` to the spec prompt so the LLM knows which modules exist as siblings
- **Seed improvement**: Add `import_map` to the golden seed for closed-world import validation

Examples of prohibited repairs:
- Rewriting `from emailservice import demo_pb2` to `import demo_pb2` in generated code
- Inserting `# type: ignore` to suppress type checker warnings on bad imports
- Deleting flagged functions to reduce dead code warnings

**Rationale:** Fixing generated code treats the LLM as a black box that produces fixable output. Fixing the inputs treats the LLM as a learnable system that produces better output when given better context. The second approach compounds — each improvement persists across all future runs.

---

### REQ-SV2-1200: Kaizen Suggestion Targeting

**Requirement:** When Stage 2 identifies a stable correlation (e.g., "import_resolution errors correlate with missing service_metadata in prompt"), `generate_kaizen_suggestions()` produces targeted suggestions:

```json
{
  "pattern": "import_resolution",
  "suggested_action": "Add service directory layout to spec prompt context",
  "config_key": "context.service_metadata.include_sibling_modules",
  "confidence": 0.85,
  "evidence": "ρ=-0.45 across 15 runs, FP rate 3%",
  "repair_type": "prompt_enrichment"
}
```

The suggestion targets a specific `config_key` in the pipeline configuration, not a code transformation. The `evidence` field provides the statistical backing so a human reviewer can decide whether to activate it.

---

## 6. Implementation Phases

### Phase 5: Harden Existing Detectors (P0–P1)

| Requirement | Effort | Files |
|-------------|--------|-------|
| REQ-SV2-100: L3+ digest plausibility | ~20 LOC + ~30 test LOC | `forward_manifest_validator.py` |
| REQ-SV2-200: L1 GCP false positive reduction | ~25 LOC + ~20 test LOC | `package_aliases.py`, `forward_manifest_validator.py` |
| REQ-SV2-300: L5 alias resolution fix | ~5 LOC + ~10 test LOC | `forward_manifest_validator.py` |
| REQ-SV2-700: Category aggregation in Kaizen | ~15 LOC | `run_prime_postmortem.py` |

**~65 LOC + ~60 test LOC. Ships as one commit. Immediately reduces FP rate and catches the grade-F Dockerfile.**

### Phase 6: New Diagnostic Layers (P1–P2)

| Requirement | Effort | Files |
|-------------|--------|-------|
| REQ-SV2-400: L8 service identity mismatch | ~40 LOC + ~50 test LOC | `forward_manifest_validator.py` |
| REQ-SV2-500: L9 method resolution | ~35 LOC + ~40 test LOC | `forward_manifest_validator.py` |
| REQ-SV2-600: L10 dead code detection | ~30 LOC + ~40 test LOC | `forward_manifest_validator.py` |
| REQ-SV2-800: FP tracking infrastructure | ~25 LOC + ~20 test LOC | `forward_manifest_validator.py`, `prime_postmortem.py` |

**~130 LOC + ~150 test LOC. Ships as 2 commits (L8+L9, L10+FP tracking).**

### Phase 7: Correlation Infrastructure (P2)

| Requirement | Effort | Files |
|-------------|--------|-------|
| REQ-SV2-900: Per-category correlation | ~30 LOC | `kaizen_correlation.py` |

**~30 LOC. Requires 10+ runs with semantic labels before producing meaningful output. Build now, harvest later.**

### Phase 8: Upstream Repair (Deferred — requires Stage 2 data)

REQ-SV2-1000, 1100, 1200 are design constraints, not implementations. They activate when Stage 2 data meets the gate criteria.

REQ-SV2-1300 and REQ-SV2-1400 below are **concrete Stage 3 repairs** with sufficient retroactive evidence to specify now. They target the two highest-frequency remaining defect classes (60% and 50% of runs) and follow the REQ-SV2-1100 principle: fix inputs, not outputs.

---

### REQ-SV2-1300: L1.2 Local Namespace-as-Package — `__init__.py` Generation or Bare Import Instruction (P1)

**Problem:** 60% of runs (12/20) contain `from emailservice import demo_pb2` or `from recommendationservice.logger import logger` — treating sibling files as importable packages. Generated code assumes `__init__.py` exists and parent directories are Python packages. The pipeline generates no `__init__.py` files.

**Root Cause (per retroactive analysis §7.2):** The LLM generates imports by convention (package-style `from X import Y`) without knowing the project's module layout or whether `__init__.py` files exist. The spec prompt provides no directory layout or import style guidance.

**Evidence:** 12/20 runs across all 4 epochs. Never self-corrected. Not addressed by REQ-SIG-200/201 (which provides proto module names but not import style guidance).

**Requirement:** Address via one or both upstream repairs (per REQ-SV2-1100, fix inputs not outputs):

**Option A: Spec prompt import style instruction**

Add a `## Import Conventions` section to the spec builder when the target project does NOT use package-style imports (no `__init__.py` in service directories). Content:

```
## Import Conventions
This project uses flat module layout (no __init__.py). Import sibling files with:
  import demo_pb2          # NOT: from emailservice import demo_pb2
  from logger import get_logger  # NOT: from emailservice.logger import get_logger
```

Inject this section when the forward manifest's `file_specs` shows sibling `.py` files in the same directory with no `__init__.py` present.

- **Where:** `implementation_engine/spec_builder.py` — new P1 section derived from `file_specs` directory analysis
- **Effort:** ~20 LOC (directory scan + conditional section injection)
- **Activation gate:** L1 `local_namespace_as_package` FP rate < 5% across 10+ runs (per REQ-SV2-1000)

**Option B: Generate `__init__.py` files during SCAFFOLD phase**

Add empty `__init__.py` generation for each service directory during plan ingestion or scaffold:

- **Where:** `plan_ingestion_emitter.py` or `artisan_phases/preflight.py`
- **Effort:** ~15 LOC
- **Risk:** Changes project structure; may conflict with projects that intentionally use flat layout

**Recommendation:** Option A (prompt instruction) is lower risk and follows the repair-inputs principle. Option B is a valid complement if the project structure demands packages.

**Verification:** Re-run online-boutique. L1 `local_namespace_as_package` errors drop to 0 in runs where the import conventions section is present.

---

### REQ-SV2-1400: L6 Discarded Returns — Spec Prompt Anti-Pattern Instruction (P2)

**Problem:** 50% of runs (10/20) contain discarded `os.getenv()`, `os.environ.get()`, or `os.path.*()` calls as expression statements. The return value is computed and thrown away:

```python
os.getenv("GCP_PROJECT_ID")           # discarded — should be: project_id = os.getenv(...)
os.environ.get("ALLOYDB_TABLE_NAME")  # discarded — 5 consecutive calls in run-003
```

**Root Cause:** The LLM generates environment variable lookups as "configuration statements" rather than assignments. This pattern appears when the LLM is adapting a reference implementation that uses environment variables but doesn't show the assignment target (e.g., Dockerfile `ENV` statements or `.env` file entries rewritten as Python).

**Evidence:** 10/20 runs. Stable pattern that never self-corrects. Concentrated in `email_server.py` and `shoppingassistantservice.py`. Severity is WARNING (the code runs but silently discards configuration).

**Requirement:** Add an anti-pattern instruction to the spec prompt when the task involves environment variable configuration:

```
## Anti-Patterns to Avoid
- Do NOT write `os.getenv("KEY")` as a bare expression statement. Always assign the result:
    project_id = os.getenv("GCP_PROJECT_ID", "")
- Do NOT write `os.environ.get("KEY")` as a bare statement. This computes a value and discards it.
```

Inject this section when:
1. The task description or dependencies mention environment variables, `.env`, or configuration
2. OR the `forward_element_specs` for the task include functions that reference `os.getenv` in their signatures

- **Where:** `implementation_engine/spec_builder.py` — conditional P2 section
- **Effort:** ~15 LOC (keyword detection + section injection)
- **Activation gate:** L6 `discarded_return` FP rate < 5% across 10+ runs (per REQ-SV2-1000). Current FP rate is ~0% — every detection has been a true positive.

**Verification:** Re-run online-boutique. L6 `discarded_return` warnings drop to 0 for `email_server.py` and `shoppingassistantservice.py`.

---

## 7. Success Criteria

| Criterion | Metric | Target |
|-----------|--------|--------|
| L3+ catches fabricated digests | PI-013 type files detected | 100% |
| L1 FP rate reduction | GCP import FPs per run | <1 (from ~3) |
| L5 FP rate reduction | Orphan dependency FPs per run | 0 (from 1) |
| L8 catches copy-paste logger bug | PI-002 type files detected | 100% |
| L9 catches self.method() errors | PI-009 type files detected | 100% |
| L10 flags dead code files | PI-004/PI-007 type files flagged | warning-level |
| Kaizen category breakdown | Per-category metrics in kaizen-metrics.json | Present |
| FP tracking operational | FP rates per category computed | Present |
| No premature repair | Stage 3 not activated without gate criteria | Enforced |
| L1.2 namespace-as-package eliminated | `local_namespace_as_package` errors per run | 0 (from ~2) |
| L6 discarded returns eliminated | `discarded_return` warnings per run | 0 (from ~1.5) |

---

## 8. Cross-References

| Document | Relationship |
|----------|-------------|
| [SEMANTIC_VALIDATION_REQUIREMENTS.md](SEMANTIC_VALIDATION_REQUIREMENTS.md) | v1 requirements (L1–L6) — this doc extends, not replaces |
| [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](SEMANTIC_VALIDATION_GAP_ANALYSIS.md) | Source evidence from runs 049–050 |
| [SEMANTIC_VALIDATION_IMPLEMENTATION_PLAN.md](SEMANTIC_VALIDATION_IMPLEMENTATION_PLAN.md) | v1 implementation plan (Phases 1–4 complete) |
| Run-053 post-mortem evaluation | Source evidence for L3+, L8, L9, L10 requirements |
| `forward_manifest_validator.py` | Implementation target for L3+, L8, L9, L10 |
| `package_aliases.py` | Implementation target for L1 GCP alias expansion |
| `prime_postmortem.py` | Implementation target for category aggregation, FP tracking |
| `kaizen_correlation.py` | Implementation target for per-category correlation |
| [SEMANTIC_VALIDATION_RETROACTIVE_ANALYSIS.md](SEMANTIC_VALIDATION_RETROACTIVE_ANALYSIS.md) | §7.2 (L1.2 root cause), §4.1 (L6 frequency) — evidence for REQ-SV2-1300/1400 |
| [REQ_CONTRACTS_CONSUMER_GAPS.md](REQ_CONTRACTS_CONSUMER_GAPS.md) | GAP-SDK-003 — binding injection removed; import context via REQ-SIG-200/201 |
| `implementation_engine/spec_builder.py` | Implementation target for REQ-SV2-1300 (import conventions) and REQ-SV2-1400 (anti-patterns) |
