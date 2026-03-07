# Kaizen Investigation: Run 004 — Online Boutique Demo

**Date:** 2026-03-06
**Run:** `run-004-20260306T1620` (online-boutique-demo)
**Pipeline:** `.cap-dev-pipe/pipeline-output/online-boutique/latest/`
**Features examined:** PI-001 through PI-007 across multiple incremental sub-runs
**Status:** All reported as SUCCESS, but manual inspection reveals systemic quality gaps

---

## 1. Executive Summary

Run 004 processed 7 features (PI-001 through PI-007) across 4 incremental sub-runs, all reporting success. Total cost: $0.95 across cloud fallback calls. Manual inspection reveals:

- **3 of 5 Python files on disk are broken skeletons** (PI-002, PI-004, PI-006) — all `micro_prime_only` features
- **2 spurious root-level files** written outside `src/` (PI-001 `logger.py`, PI-003 `email_server.py`)
- **1 garbled file** with duplicated code blocks (PI-007 `client.py`)
- **1 genuinely good file** (PI-003 `email_server.py` — cloud fallback)
- **1 good HTML template** (PI-005 `confirmation.html` — cloud fallback, 408 lines) despite review scoring it 72/100 FAIL
- The pattern is clear: **cloud fallback produces good code; micro-prime-only produces broken output**

---

## 2. Per-Feature Findings

### 2.1 PI-001: Shared JSON Logger — emailservice

| Metric | Value |
|---|---|
| Route | Micro-prime (1 element failed) → cloud fallback |
| Cost | $0.084 |
| Review Score | 97/100 PASS |
| File on disk | Correct |

**Draft quality:** High. Cloud fallback produced clean `CustomJsonFormatter` + `getJSONLogger`.

**File on disk (`src/emailservice/logger.py`):** Matches integration artifact. Functionally correct. Added handler-dedup guard (`if not logger.handlers:`) beyond spec.

**Issue — spurious root-level file:** Pipeline wrote `logger.py` to both `src/emailservice/logger.py` AND project root. Confirmed: `/online-boutique-demo/logger.py` exists (1,814 bytes).

**Micro Prime detail:**
- `add_fields`: Ollama produced indentation errors → repair failed → escalated to cloud
- `getJSONLogger`: `verification_verdict: "skipped"`, never generated — handled by fallback

### 2.2 PI-002: Shared JSON Logger — recommendationservice

| Metric | Value |
|---|---|
| Route | Micro-prime only (no fallback) |
| Cost | $0.00 |
| Review Score | 97/100 PASS |
| File on disk | **BROKEN SKELETON** |

**Draft quality:** Functionally valid but **divergent from PI-001** (ISO timestamp vs float, extra `pop("level")`, extra `datetime` import) despite spec requiring "identical copy."

**File on disk (`src/recommendationservice/logger.py`):**
```python
# [REPAIRED BY STARTD8: import_completion]
# [STARTD8-SKELETON]
def add_fields(self, log_record, record, message_dict) -> None:
    def add_fields(self, log_record, record, message_dict) -> None:  # nested duplicate!
        ...
def getJSONLogger(name: str) -> logging.Logger:
    raise NotImplementedError
```
Non-functional: nested duplicate, `NotImplementedError` stub. Pipeline reported `success: true`.

### 2.3 PI-003: Email Service — gRPC Server

| Metric | Value |
|---|---|
| Route | Micro-prime (3 elements) → cloud fallback for `start()` |
| Cost | $0.203 |
| Review Score | 97/100 PASS |
| File on disk | **Correct — best output of the run** |

**File on disk (`src/emailservice/email_server.py`):** 292 lines. Complete gRPC server with:
- `BaseEmailService` / `EmailService` / `DummyEmailService` class hierarchy
- Standalone `HealthCheck` class (duck-typed, no inheritance)
- `start()` with correct 8-step startup sequence
- OTel instrumentation, signal handlers, Jinja2 template rendering
- Clean import organization (stdlib → third-party → local)

**Micro Prime detail:**
- `__init__`: Template match (`dunder_method`), `code: "pass"` — correct
- `initStackdriverProfiling`: Ollama produced valid stub with commented profiler code, 13.8s generation
- `send_email`: Ollama produced minimal 1-line body, 1.7s generation
- `start`: "moderate" tier, `not_decomposable` → escalated to cloud fallback ($0.203)

**Issue — spurious root-level file:** `email_server.py` (10,146 bytes) written to project root alongside correct `src/emailservice/email_server.py`.

### 2.4 PI-004: Email Service — gRPC Test Client

| Metric | Value |
|---|---|
| Route | Micro-prime only (no fallback) |
| Cost | $0.00 |
| Review Score | N/A (no review artifacts) |
| File on disk | **BROKEN SKELETON** |

**File on disk (`src/emailservice/email_client.py`):**
```python
# [STARTD8-SKELETON]
def send_confirmation_email(email: str, order) -> None:
    import smtplib
    from email.mime.text import MIMEText
    def send_confirmation_email(email: str, order) -> None:  # nested duplicate!
        try:
            msg = MIMEText(f"Your order {order.id} has been confirmed.")
            ...
```
**Wrong function entirely.** Spec asks for a gRPC test client that calls `SendOrderConfirmation` via `demo_pb2_grpc`. Ollama generated an SMTP email sender instead. The skeleton has the same nested-duplicate pattern as PI-002.

**Micro Prime detail:**
- 1 element (`send_confirmation_email`), `verification_verdict: "pass"`, 16s generation
- Repair applied `over_generation_trim` + `bare_statement_wrap`
- The element name itself is wrong — should be a gRPC client function, not an SMTP sender

### 2.5 PI-005: Email Service — Jinja2 Order Confirmation Template

| Metric | Value |
|---|---|
| Route | Cloud fallback only (no micro-prime elements — HTML file) |
| Cost | $0.384 |
| Review Score | 72/100 **FAIL** |
| File on disk | **Good (408 lines)** |

**Review said FAIL, but the file is correct.** The review cited two blocking issues:
1. "Line count ~245" — **wrong.** Actual file is 408 lines, exceeding the 304 minimum.
2. "Google Fonts URL missing italic variants" — valid concern but the file on disk has a different URL than what the review examined.

This is a case where the review evaluated the **draft artifact**, but the **integration step** produced a better file. The review's FAIL verdict was based on stale data.

**File on disk (`src/emailservice/templates/confirmation.html`):** 408 lines. Complete Jinja2 template with order details, shipping info, nanos formatting, DM Sans font, email-client-compatible inline styles.

**Context keys note:** PI-005 metadata shows `has_existing_files: true` and `existing_files` in context keys — this is the only feature that had pre-existing content. It also lacks `forward_element_specs` (correct — HTML files have no decomposable elements).

### 2.6 PI-006: Recommendation Service — gRPC Server

| Metric | Value |
|---|---|
| Route | Micro-prime only (no fallback) |
| Cost | $0.00 |
| Review Score | N/A (no review artifacts) |
| File on disk | **BROKEN SKELETON** |

**File on disk (`src/recommendationservice/recommendation_server.py`):**
```python
# [STARTD8-SKELETON]
def initStackdriverProfiling() -> None:
    import os
    from google.cloud import profiler
    def initStackdriverProfiling() -> None:  # nested duplicate!
        ...
        profiler.start()
```
Same pattern: nested duplicate function, imports inside function body. The spec calls for a full gRPC server with product catalog filtering, health checks, and OTel instrumentation. Only the `initStackdriverProfiling` stub was generated.

**Micro Prime detail:**
- 1 element (`initStackdriverProfiling`), `verification_verdict: "pass"`, 19.7s generation
- Repair applied `over_generation_trim` + `bare_statement_wrap`
- All other server elements (class definitions, `serve()` function, health check) were not generated — they don't appear in `element_results` at all

### 2.7 PI-007: Recommendation Service — gRPC Test Client

| Metric | Value |
|---|---|
| Route | Cloud fallback only (no micro-prime elements) |
| Cost | $0.093 |
| Review Score | 97/100 PASS |
| File on disk | **GARBLED — duplicate code blocks** |

**Draft quality:** Clean 42-line client with correct structure (imports, logger, `main()`, `__main__` guard).

**File on disk (`src/recommendationservice/client.py`):** 30 lines of **garbled code**:
```python
def main():
    port = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_PORT
    ...
log = getJSONLogger('client')      # module-level code INSIDE function context
if __name__ == '__main__':          # duplicate __main__ guard
    port = sys.argv[1] ...          # duplicate logic
    response = stub.ListRecommendations(request)
    log.info(response)
'\nrecommendation_client.py\n...'   # bare docstring as expression
logger = getJSONLogger('client')    # second logger instantiation
_TEST_PRODUCT_IDS = [...]           # constants AFTER they're used
if __name__ == '__main__':          # third __main__ guard
    main()
```

The file has **3 `__main__` guards**, **2 logger instantiations**, constants defined after use, and a bare docstring as a string expression. This appears to be a concatenation of the draft output with the existing file content, without deduplication.

**Context keys note:** PI-007 metadata shows `has_existing_files: true` and `existing_files` in context keys — the integration merged new code with existing content but produced a garbled result.

---

## 3. Pattern Analysis

### 3.1 Cloud Fallback vs Micro-Prime-Only

| Feature | Route | Cost | File Quality |
|---|---|---|---|
| PI-001 | MP → fallback | $0.084 | Good |
| PI-002 | MP only | $0.00 | **Broken skeleton** |
| PI-003 | MP → fallback | $0.203 | Good |
| PI-004 | MP only | $0.00 | **Broken skeleton** |
| PI-005 | Fallback only | $0.384 | Good |
| PI-006 | MP only | $0.00 | **Broken skeleton** |
| PI-007 | Fallback only | $0.093 | **Garbled merge** |

**Pattern:** Every `micro_prime_only: true` feature (PI-002, PI-004, PI-006) produced a broken skeleton on disk. Every cloud-fallback feature (PI-001, PI-003, PI-005) produced correct code. PI-007 (fallback with `has_existing_files: true`) produced a garbled merge.

### 3.2 Ollama `startd8-coder` Over-Generation Pattern

Every Ollama generation exhibits the same defect: the model **re-emits the function signature and imports** inside the function body, creating nested duplicates.

| Feature | Element | Ollama Output Pattern |
|---|---|---|
| PI-001 | `add_fields` | Body has mixed indentation |
| PI-002 | `add_fields` | `def add_fields(...):\n    import ...\n    def add_fields(...):` |
| PI-004 | `send_confirmation_email` | `def send_confirmation_email(...):\n    import ...\n    def send_confirmation_email(...):` |
| PI-006 | `initStackdriverProfiling` | `def initStackdriverProfiling(...):\n    import ...\n    def initStackdriverProfiling(...):` |

The repair step `over_generation_trim` + `bare_statement_wrap` marks these as `verification_verdict: "pass"` but the assembled file retains the nested structure. The repair is verifying the element in isolation (AST-valid as a standalone snippet) but not checking whether the assembled file is correct.

### 3.3 Review Score vs Actual Quality

| Feature | Review Score | Actual File Quality | Gap |
|---|---|---|---|
| PI-001 | 97 PASS | Good | None |
| PI-002 | 97 PASS | Broken skeleton | **Critical** |
| PI-003 | 97 PASS | Good | None |
| PI-004 | N/A | Broken skeleton | No review ran |
| PI-005 | 72 FAIL | Good (408 lines) | **Review wrong** |
| PI-006 | N/A | Broken skeleton | No review ran |
| PI-007 | 97 PASS | Garbled merge | **Critical** |

The review phase evaluates **draft artifacts**, not files on disk. This means:
- Features that pass review can have broken files on disk (PI-002, PI-007)
- Features that fail review can have correct files on disk (PI-005)
- `micro_prime_only` features skip the review phase entirely (PI-004, PI-006)

### 3.4 Kaizen Prompt Metadata Observations

All 7 features captured kaizen prompts. Common patterns:
- All features have 12-13 context keys active
- `lead_agent_spec` and `drafter_agent_spec` are both `"unknown"` for every feature — the kaizen capture doesn't know which model was used
- `has_existing_files` correctly distinguishes greenfield (PI-001–PI-004, PI-006) from edit-mode (PI-005, PI-007)
- PI-005 and PI-007 have `existing_files` in context keys; the others have `forward_element_specs` instead
- No `prior_error_feedback` context was populated for any feature (all first attempts)

---

## 4. Investigation Items

### INV-1: Micro-Prime File Assembly When `micro_prime_only: true` [CRITICAL]

**Symptom:** PI-002, PI-004, PI-006 all have `micro_prime_only: true` and all produced broken skeletons on disk despite element-level `verification_verdict: "pass"`.

**Root cause hypothesis:** When no elements are escalated to cloud fallback, the file assembler writes the skeleton but never splices the generated element code into it. The fallback code path (which runs for PI-001, PI-003) appears to write a complete file. The micro-prime-only path appears to rely on in-place element replacement that isn't happening.

**Evidence:**
- All 3 broken files have the `# [STARTD8-SKELETON]` marker
- All 3 have nested duplicate function definitions (Ollama output concatenated rather than spliced)
- `getJSONLogger` in PI-001/PI-002 was never generated (`verification_verdict: "skipped"`) — the skeleton stub persists

**Where to look:**
- `src/startd8/contractors/integration_engine.py` — file assembly after micro-prime
- `src/startd8/micro_prime/decomposer.py` — skeleton → assembled file lifecycle
- The branch that runs when `fallback_files_delegated == 0`

### INV-2: Elements Skipped Without Generation [HIGH]

**Symptom:** Multiple elements across features have `verification_verdict: "skipped"`, `generation_time_ms: 0.0`, `model: null`, `code: null` — they were identified by the decomposer but never generated.

| Feature | Skipped Element | Reason |
|---|---|---|
| PI-001 | `getJSONLogger` | `element_kind: null` |
| PI-002 | `getJSONLogger` | `element_kind: null` |
| PI-003 | `start` | `not_decomposable` (moderate tier) |

**Hypothesis:** Elements with `element_kind: null` are not dispatched to Ollama. The decomposer identifies them as elements but the generation dispatcher filters them out. For `start`, the "moderate" tier with `not_decomposable` is correctly escalated to fallback — but for `getJSONLogger`, there's no fallback in the `micro_prime_only` path.

**Where to look:**
- Decomposer element classification — why `getJSONLogger` gets `element_kind: null`
- Generation dispatcher filter logic — what `element_kind` values are eligible for generation
- Whether `micro_prime_only` features can still delegate un-generated elements to fallback

### INV-3: Spurious Root-Level Files [MEDIUM]

**Symptom:** PI-001 and PI-003 (both cloud-fallback features) wrote files to both the correct `src/` path AND the project root.

| Feature | Correct Path | Spurious Path | Size |
|---|---|---|---|
| PI-001 | `src/emailservice/logger.py` | `logger.py` | 1,814 bytes |
| PI-003 | `src/emailservice/email_server.py` | `email_server.py` | 10,146 bytes |

No spurious files for micro-prime-only features (PI-002, PI-004, PI-006) — the bug is specific to the cloud-fallback file write path.

**Hypothesis:** The fallback code generator extracts the filename from the target path and writes it relative to both the `generated/` staging directory and the project root. One write uses the full relative path (`src/emailservice/logger.py`), the other uses just the basename (`logger.py`).

**Where to look:**
- `src/startd8/contractors/integration_engine.py` — dual-write logic
- `src/startd8/contractors/generators/` — file path construction in fallback

### INV-4: Garbled File Merge (PI-007 `client.py`) [HIGH]

**Symptom:** PI-007 (`has_existing_files: true`) produced a file with 3 `__main__` guards, 2 logger instantiations, constants defined after use, and a bare docstring expression.

**Root cause hypothesis:** The integration step concatenated the cloud-fallback draft output with the existing file content without deduplication. The draft contains a complete standalone file; the existing file also contains a complete standalone file. The merge just appended one to the other.

**Evidence:**
- Draft artifact is a clean 42-line file
- File on disk is ~30 lines of garbled concatenation
- PI-005 (also `has_existing_files: true`) produced a correct file — but PI-005 is an HTML template (no code dedup needed), while PI-007 is Python

**Where to look:**
- `src/startd8/contractors/integration_engine.py` — merge logic for `has_existing_files` Python files
- Whether the merge strategy differs for HTML vs Python files
- Whether the draft is supposed to replace (not merge with) the existing file

### INV-5: Review Evaluates Draft, Not Disk [HIGH]

**Symptom:**
- PI-005 review scored 72/100 FAIL citing "~245 lines" but actual file is 408 lines
- PI-002 review scored 97/100 PASS but file on disk is a broken skeleton
- PI-007 review scored 97/100 PASS but file on disk is garbled

**Root cause:** The review phase reads from `.artifacts/{name}-draft-1.md` (the LLM's raw output), not from the assembled file on disk. Draft quality ≠ final file quality because assembly/merge can corrupt the output.

**Where to look:**
- Review prompt construction — which file path does it read?
- Whether a post-assembly validation step exists (lint, AST parse, import check)
- Adding a post-assembly review or at minimum an AST validity check on the final file

### INV-6: Success Reporting Despite Broken Output [CRITICAL]

**Symptom:** PI-002, PI-004, PI-006 report `success: true` with broken skeletons. PI-007 reports `success: true` with garbled code.

**Root cause:** Success is determined by:
1. Element-level `verification_verdict` (passes for broken elements because they're checked in isolation)
2. Review score (evaluates draft, not disk)
3. No post-assembly validation gate

**Recommendation:** Add a post-assembly gate that:
1. Runs `ast.parse()` on each generated Python file
2. Runs ruff/lint check
3. Verifies no `raise NotImplementedError` stubs remain (unless spec explicitly requires them)
4. Verifies no `# [STARTD8-SKELETON]` markers remain

### INV-7: Ollama Over-Generation Pattern [MEDIUM]

**Symptom:** Every Ollama generation re-emits imports and the function signature inside the body, creating nested duplicate definitions. The repair step `over_generation_trim` trims excess nodes but `bare_statement_wrap` re-wraps, producing AST-valid but semantically wrong code.

**Hypothesis:** The element prompt asks Ollama to "implement the body of function X" but the model interprets this as "write the complete function including signature and imports." The repair trims some nodes but the result is still a nested function-inside-function.

**Where to look:**
- `src/startd8/micro_prime/` — element prompt template (does it say "body only" or "complete function"?)
- Repair step `over_generation_trim` — what does it trim? Why doesn't it detect the nested duplicate signature?
- Whether the prompt should include `# YOUR CODE HERE` markers to guide the model

### INV-8: PI-004 Wrong Function Generated [MEDIUM]

**Symptom:** PI-004 spec is "gRPC Test Client" that calls `SendOrderConfirmation` via `demo_pb2_grpc`. Ollama generated `send_confirmation_email` — an SMTP email sender using `smtplib`, which is a completely different function.

**Root cause:** The micro-prime decomposer derived element name `send_confirmation_email` from the skeleton, and Ollama generated a body matching that name literally rather than following the spec context. The element prompt may not include enough task context for Ollama to understand the actual requirement.

**Where to look:**
- How the decomposer names elements for the skeleton
- What context is passed in the element prompt (just signature? or also task description?)
- Whether `forward_element_specs` from the seed correctly describes gRPC client behavior

### INV-9: Cross-Feature Consistency (PI-001 vs PI-002) [LOW]

**Symptom:** PI-002's spec says "identical copy" of PI-001, but LLM produced a functionally different implementation. Reviewer didn't catch it.

**Where to look:**
- Whether `depends_on: [PI-001]` injects PI-001's output into PI-002's review context
- Review prompt construction for dependent features

### INV-10: Kaizen Correlation Path Bug [LOW]

**Symptom:** Correlation engine reports 0 data points. Skipped run reason shows doubled `plan-ingestion/plan-ingestion/` path segment.

**Where to look:**
- `src/startd8/contractors/prime_postmortem.py` — path construction for kaizen-prompts discovery

### INV-11: `agent_spec` Unknown in Kaizen Metadata [LOW]

**Symptom:** All 7 features have `lead_agent_spec: "unknown"` and `drafter_agent_spec: "unknown"` in kaizen metadata. This makes it impossible to correlate prompt quality with model choice.

**Where to look:**
- Kaizen metadata capture — where it reads agent specs from
- Whether the integration engine passes model info to the kaizen writer

---

## 5. Priority Matrix

| Priority | Items | Theme |
|---|---|---|
| **Critical** | INV-1, INV-6 | Micro-prime assembly + false success reporting |
| **High** | INV-2, INV-4, INV-5 | Skipped elements, garbled merge (FIXED: auto-replace), review file warnings (FIXED) |
| **Medium** | INV-3, INV-7, INV-8 | Spurious files, Ollama over-generation, wrong function |
| **Low** | INV-9, INV-10, INV-11 | Cross-feature review, kaizen path bug, unknown agent spec |

The critical items (INV-1 + INV-6) together mean: **the pipeline silently ships broken code and calls it a success.** This is the highest-priority fix — either the assembly must work, or the post-assembly validation must catch failures and report them accurately.

---

## 6. Cost Analysis

| Feature | Route | Cloud Cost | Ollama Cost | Total |
|---|---|---|---|---|
| PI-001 | MP → fallback | $0.084 | $0.00 | $0.084 |
| PI-002 | MP only | — | $0.00 | $0.000 |
| PI-003 | MP → fallback | $0.203 | $0.00 | $0.203 |
| PI-004 | MP only | — | $0.00 | $0.000 |
| PI-005 | Fallback only | $0.384 | — | $0.384 |
| PI-006 | MP only | — | $0.00 | $0.000 |
| PI-007 | Fallback only | $0.093 | — | $0.093 |
| **Total** | | | | **$0.764** |

The 3 micro-prime-only features cost $0.00 but produced 0 usable files. The 4 cloud-fallback features cost $0.764 and produced 3 good files + 1 garbled merge. **Effective cost per usable file: $0.255.**

---

## 7. Artifacts Referenced

All paths relative to `/Users/neilyashinsky/Documents/dev/online-boutique-demo/.cap-dev-pipe/pipeline-output/online-boutique/run-004-20260306T1620/`:

### Prime Result Files (incremental sub-runs)
| Sub-run | Features | File |
|---|---|---|
| 1 | PI-001, PI-002 | `plan-ingestion/prime-result-PI-001-PI-002-...-PI-017.json` |
| 2 | PI-003 | `plan-ingestion/prime-result-PI-003-...-PI-017.json` |
| 3 | PI-004, PI-005 | `plan-ingestion/prime-result-PI-004-...-PI-017.json` |
| 4 | PI-006, PI-007 | `plan-ingestion/prime-result-PI-006-...-PI-017.json` |

### Per-Feature Artifacts
| Feature | Draft | Review | Integration | Kaizen Prompts |
|---|---|---|---|---|
| PI-001 | `.artifacts/Shared_JSON_Logger_Utility___emailservice-draft-1.md` | `-review-1.md` | `-integration.md` | `kaizen-prompts/standalone/PI-001/` |
| PI-002 | `.artifacts/Shared_JSON_Logger_Utility___recommendationservice-draft-1.md` | `-review-1.md` | `-integration.md` | `kaizen-prompts/standalone/PI-002/` |
| PI-003 | `.artifacts/Email_Service___gRPC_Server-draft-1.md` | `-review-1.md` | `-integration.md` | `kaizen-prompts/standalone/PI-003/` |
| PI-004 | N/A (micro-prime only) | N/A | N/A | `kaizen-prompts/standalone/PI-004/` |
| PI-005 | `.artifacts/Email_Service___Jinja2_Order_Confirmation_Template-draft-1.md` | `-review-1.md` | `-integration.md` | `kaizen-prompts/standalone/PI-005/` |
| PI-006 | N/A (micro-prime only) | N/A | N/A | `kaizen-prompts/standalone/PI-006/` |
| PI-007 | `.artifacts/Recommendation_Service___gRPC_Test_Client-draft-1.md` | `-review-1.md` | `-integration.md` | `kaizen-prompts/standalone/PI-007/` |

### Files on Disk (project root: `/Users/neilyashinsky/Documents/dev/online-boutique-demo/`)
| File | Quality | Source |
|---|---|---|
| `src/emailservice/logger.py` | Good | Cloud fallback |
| `src/emailservice/email_server.py` | Good | Cloud fallback |
| `src/emailservice/email_client.py` | **Broken skeleton** | Micro-prime only |
| `src/emailservice/templates/confirmation.html` | Good (408 lines) | Cloud fallback |
| `src/recommendationservice/logger.py` | **Broken skeleton** | Micro-prime only |
| `src/recommendationservice/recommendation_server.py` | **Broken skeleton** | Micro-prime only |
| `src/recommendationservice/client.py` | **Garbled merge** | Cloud fallback + existing |
| `logger.py` (root — spurious) | Duplicate of emailservice | Cloud fallback bug |
| `email_server.py` (root — spurious) | Duplicate of emailservice | Cloud fallback bug |

---

## 7. Resolution Status

| INV | Priority | Status | Fix | Commit |
|-----|----------|--------|-----|--------|
| INV-1 | Critical | **FIXED** | Success cache now stores generated code (`dict[str, Optional[str]]`). Post-splice stub detection marks code-less cache hits as failed when stubs remain. | `270189e` |
| INV-2 | High | **FIXED** | `_success_cache` changed from `set` → `dict` to carry code through cache hits. Cache-hit results now populate `result.code`. | `270189e` |
| INV-3 | Medium | **FIXED** | `_derive_target_from_source()` now matches source filename against `unit.target_files` before falling back to bare filename at project root. | `076b3e2` |
| INV-4 | High | **FIXED** | `ASTMergeStrategy` auto-detects when source class/function names overlap target >50% and switches to "replace" mode, preventing garbled additive merge of complete standalone files. | `a89f060` |
| INV-5 | High | **FIXED** | Review phase now logs warnings when generated files are missing from disk instead of silently skipping, making staging cleanup / checkpoint path issues visible. | `a89f060` |
| INV-6 | Critical | **FIXED** | Post-assembly stub detection gate: files with remaining `raise NotImplementedError` are escalated to fallback (if available) or excluded from `effective_file_count` (Mottainai — keep partial file, report `success=false`). | `270189e` |
| INV-7 | Low | **NOT ADDRESSED** | Model quality issue with `startd8-coder`. Nested duplicate function pattern tracked for prompt/tier threshold tuning. | — |
