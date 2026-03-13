# Kaizen Investigation: Run-042 (online-boutique)

**Run ID:** `run-042-20260312T1434`
**Date:** 2026-03-12
**Previous investigation:** [Run-033](KAIZEN_INVESTIGATION_RUN033_LOGGER_MICRO_PRIME.md)
**Pipeline stage:** Prime Contractor (full 17-task execution)
**Analysis method:** [KAIZEN_DATA_ANALYSIS_GUIDE.md](../prime/KAIZEN_DATA_ANALYSIS_GUIDE.md)

---

## 1. Executive Summary

Run-042 is the culmination of a multi-run campaign (runs 015–042) to generate all 17 online-boutique PI-xxx tasks. While the Kaizen index recorded run-042 as processing 1 feature (PI-017), **the run actually processed all 17 tasks across ~9 resume invocations within the same run directory.** The postmortem only captured the final resume's result, making run-042 appear far smaller than it was.

**Key findings:**

1. **16 of 21 generated files are good-to-excellent** (A/A- grade). Infrastructure files (Dockerfiles, requirements.in, HTML templates, locustfile.py) came out clean.
2. **5 Python application files have semantic defects** that pass AST validation but fail at runtime. The root cause is element-by-element Micro Prime splicer assembly losing cross-element context (module-level globals, return values, `self` parameters).
3. **PI-009 failed on first pass** due to splicer losing the `fake = Faker()` global (`F821 Undefined name 'fake'`), then succeeded on resume using `file_ollama_whole` strategy.
4. **Postmortem aggregation is broken for multi-resume runs.** The index, trends, and correlation data all undercount run-042's actual output.

**Net assessment:** The pipeline can produce a complete 17-task project, but multi-class server files with cross-element dependencies are unreliable. Infrastructure-tier tasks (Dockerfiles, requirements, templates, single-concern scripts) are production-ready. Application-tier tasks need whole-file generation or post-assembly semantic validation.

---

## 2. Run Execution Timeline

Run-042 was not a single invocation. The batch result and individual result files tell the story:

| Time | Invocation | Features Processed | Result |
|------|-----------|-------------------|--------|
| 14:43–14:54 | Initial batch (all 17 in filter) | PI-001 through PI-009 (9) | 8 succeeded, **PI-009 failed** (F821 `fake` undefined) |
| 15:39 | Resume 1 | PI-009 | PASS (file_ollama_whole strategy) |
| 15:43 | Resume 2 | PI-010 | PASS |
| 16:09 | Resume 3 | PI-011 | PASS |
| 16:15 | Resume 4 | PI-012 | PASS |
| 16:21 | Resume 5 | PI-013 | PASS |
| 16:22 | Resume 6 | PI-014 | PASS |
| 16:27 | Resume 7 | PI-015 | PASS |
| 16:28 | Resume 8 | PI-016 | PASS |
| 16:37 | Resume 9 (final) | PI-017 | PASS — postmortem captured this invocation only |

**Total wall time:** ~2 hours. **Total cost:** $0.00 (all Ollama local generation).

---

## 3. Cross-Run Campaign Summary (runs 015–042)

The 17 tasks were not completed in a single run. Prior to run-042 the campaign spanned 20 indexed runs across 5 days:

| Metric | Value |
|--------|-------|
| Total indexed runs | 20 |
| Successful runs | 14 (70%) |
| Failed runs | 6 (30%) |
| Total feature-run instances | 43 |
| Cumulative cost | $3.40 |
| Success rate trend slope | -2.41% per run (misleading — see Section 3.1) |
| Strongest Kaizen correlation | `context_key_count` ρ=-0.456 |

### 3.1 Failed Runs

| Run | Feature | Root Cause | Stage | Error |
|-----|---------|-----------|-------|-------|
| run-018 | (none) | Circular dependency deadlock | Queue init | All 17 tasks blocked, 0 processed |
| run-029 | PI-001 | unknown | unknown | "No files were integrated" |
| run-034 | PI-013 | `generation_error` | `ollama_generation` | Ollama couldn't generate Dockerfile |
| run-035 | PI-001 | unknown | unknown | "No files were integrated" (repeat) |
| run-037 | PI-001 | `splicer_mismatch` (element-level) | splicer | 2/3 elements OK, `getJSONLogger` structural mismatch |
| run-039 | PI-002 | unknown | unknown | "Copy source task 'F-001a' not found in queue" |

**Three failure categories:**
1. **Queue/dependency** (run-018, run-039) — upstream plumbing, not output quality
2. **Generation** (run-034) — Ollama model failure on non-Python file type
3. **Splicer/integration** (run-029, run-035, run-037) — code generated but assembly failed

### 3.2 Trend Slope Caveat

The -2.41%/run success trend is an artifact of later runs being single-feature retries of stubborn tasks (PI-001, PI-002). Run-038 (10/10 PASS) was the quality inflection point; the "degradation" after it is retry noise.

### 3.3 Correlation Analysis

120 data points (36 labeled: 23 PASS, 13 FAIL):

| Prompt Feature | ρ (Spearman) | Interpretation |
|----------------|-------------|----------------|
| `context_key_count` | -0.456 | **Moderate negative** — more context keys correlates with failure |
| `total_prompt_words` | +0.114 | Weak positive — longer prompts slightly better |
| `draft_word_count` | +0.090 | Negligible |
| `spec_word_count` | +0.025 | Negligible |

The `context_key_count` signal suggests context overload. Example: PI-009's spec prompt injected 133 API signatures from ALL services, not just loadgenerator's 11. Scoping `api_signatures` to the target service would reduce noise.

---

## 4. Per-File Quality Assessment

### 4.1 Syntax Validation

All 7 Python files pass `ast.parse()`. No syntax errors.

### 4.2 Remaining Stubs

| File | Function | Line | Severity | Assessment |
|------|----------|------|----------|------------|
| `emailservice/logger.py` | `_extract_context()` | 42 | Low | Abstract hook, callers handle None |
| `emailservice/logger.py` | `get_logger()` | 72 | Medium | Alternative entry point; `getJSONLogger()` works but callers of `get_logger()` crash |
| `emailservice/email_server.py` | `start()` | 56 | **Critical** | Server entry point — service cannot start |
| `recommendationservice/recommendation_server.py` | `Watch()` | 25 | Low | gRPC health Watch is spec-compliant as UNIMPLEMENTED |
| `recommendationservice/recommendation_server.py` | `initStackdriverProfiling()` | 29 | Low | Optional profiling, no-op acceptable |

### 4.3 File Grades

#### Grade A — Production-ready (10 files)

**PI-009: `loadgenerator/locustfile.py`** (79 lines)
- All 9 product IDs match spec exactly
- Task weights correct: `{index:1, setCurrency:2, browseProduct:10, addToCart:2, viewCart:3, checkout:1}`
- `empty_cart`/`logout` correctly excluded from tasks dict per spec
- `checkout` calls `addToCart(l)` first, uses Faker for email/address/credit card
- Year range `current_year+1..+70`, CVV as `f"{random.randint(100, 999):03d}"`
- No repair annotations, no stubs, clean imports
- Generated via `file_ollama_whole` on retry (element-by-element failed first pass)

**PI-005: `emailservice/templates/confirmation.html`** (214 lines)
- Jinja2 email template with proper escaping (`{{ x | e }}`)
- Table-based email layout, responsive CSS, DM Sans font
- Handles nanos conversion: `item.cost.nanos // 10000000`
- Professional quality

**PI-010/011/012/013: Dockerfiles** (4 files, 50–68 lines each)
- Multi-stage builds, pinned SHA256 digests (email, recomm), non-root users
- Correct base images: alpine for email/recomm/loadgen, slim for shopping assistant (per spec)
- Proto compilation stages where needed (email, recomm)
- Loadgenerator: `GEVENT_SUPPORT=True`, shell-form ENTRYPOINT with `exec`, no EXPOSE (client not server)

**PI-014/015/016/017: Requirements files** (4 files, 2–11 lines each)
- Version-pinned dependencies matching `service_metadata.runtime_dependencies`
- Correctly scoped per service (not a superset)

#### Grade B — Functional with minor issues (2 files)

**PI-001: `emailservice/logger.py`** (75 lines) — **B-**
- `CustomJsonFormatter` and `JsonFormatter` both produce structured JSON
- `getJSONLogger()` correctly creates handler, sets formatter, prevents propagation
- **Bug**: Line 39/49 — `datetime.utcfromtimestamp()` should be `datetime.datetime.utcfromtimestamp()`. The `datetime` module was imported, not the `datetime.datetime` class. **Will crash at runtime** on any log message.
- `_extract_context()` stub (Low severity)
- `get_logger()` stub (Medium severity)
- Duplicate `from typing import` statements (cosmetic)

**PI-006: `recommendationservice/recommendation_server.py`** (32 lines) — **B+**
- `ListRecommendations`: Correct filter-and-sample logic (exclude requested, sample up to 5)
- `Check()` returns SERVING (correct)
- `Watch()` raises NotImplementedError (gRPC-compliant)
- Imports `product_catalog_stub` — will work only if proto stubs are generated at build time

#### Grade C — Structural issues (1 file)

**PI-008: `shoppingassistantservice/shoppingassistantservice.py`** (65 lines) — **C**
- `create_app()` creates `Flask(__name__)` but **doesn't return it** (line 17). App object is discarded.
- Line 22: `os.getenv("ALLOYDB_TABLE_NAME")` called but result not assigned
- `talkToGemini()`: Structurally correct 3-stage RAG pipeline but references `vectorstore` (line 4 import) which is never initialized — created in `create_app` scope but not stored
- Uses LangChain v0.1 import paths (`langchain.vectorstores`) — stale for v0.2+
- `import vectorstore` on line 4 — phantom module, doesn't exist

#### Grade D — Significant defects (1 file)

**PI-003: `emailservice/email_server.py`** (58 lines) — **D**
- **Line 20**: `print(f"Sending order confirmation to: {request.email}")` at **class body level** (outside any method). Executes at import time; `request` is Flask's request proxy → crash on import
- **Line 29**: `send_email(client, email_address, content)` missing `self` parameter → `TypeError` on call
- **Line 34**: `self.template.render(...)` but `template` never set in `__init__` → `AttributeError`
- **Line 43**: Unreachable `return demo_pb2.Empty()` after line 41 already returns inside the except block
- **Line 56**: `start()` is a stub — **service cannot start**
- Inconsistent health check imports: line 5–6 vs line 47 vs line 50 use different import styles for `grpc_health.v1`

#### Grade F — Empty/non-functional (2 files)

**PI-004: `emailservice/email_client.py`** (5 lines) — **F**
- `send_confirmation_email(email, order)` body is just `pass`
- Completely empty implementation — no gRPC channel, no test call

**PI-007: `recommendationservice/client.py`** (6 lines) — **F**
- `main()` calls `logging.getLogger(__name__)` and does nothing
- No gRPC channel creation, no test request, no output

### 4.4 Quality Distribution

| Grade | Count | Files |
|-------|-------|-------|
| A/A- | 10 | locustfile.py, confirmation.html, 4 Dockerfiles, 4 requirements.in |
| B-/B+ | 2 | logger.py, recommendation_server.py |
| C | 1 | shoppingassistantservice.py |
| D | 1 | email_server.py |
| F | 2 | email_client.py, client.py |

---

## 5. PI-009 Deep Dive

PI-009 is a useful case study because it **failed on the first pass and succeeded on retry**, revealing the splicer's failure mode.

### 5.1 First Pass (14:54) — FAIL

Strategy: **element-by-element** Micro Prime (11 elements, each generated independently via Ollama).

**What went wrong:** Each element was generated in isolation. The `checkout()` function referenced `fake` (the module-level `Faker()` instance), but the splicer assembled elements without carrying the module-level `fake = Faker()` declaration. Post-assembly lint caught 3 `F821 Undefined name 'fake'` errors on lines 37, 40, 41.

Element-level results from the batch:
- 9/11 elements passed individually (all simple-tier functions)
- `UserBehavior` (moderate): Generated `def index(l): l.client.get("/")` — wrong, should be the class body with `on_start` and `tasks` dict
- `WebsiteUser` (moderate): Generated `class WebsiteUser(FastHttpUser): l.client.get("/")` — wrong, should have `tasks = [UserBehavior]` and `wait_time`
- Each element redefined `product_ids` locally instead of referencing the module-level list

**Root cause:** Element-level generation has no visibility into sibling elements or module-level state. The spec prompt for each element contained the function signature but not the surrounding context (globals, imports, sibling definitions).

### 5.2 Retry (15:39) — PASS

Strategy: **file_ollama_whole** (entire file generated as a single unit).

The retry produced a clean 79-line file that is byte-for-byte identical to the file on disk. All module-level globals (`fake`, `product_ids`), class bodies, and cross-function references (`checkout` calling `addToCart`) are correct.

### 5.3 Lesson

For files where elements have cross-dependencies (shared globals, inter-function calls, class attributes referencing module-level functions), `file_ollama_whole` is the correct strategy. Element-by-element generation should only be used when elements are truly independent.

---

## 6. Draft vs Disk Comparison (Section 5 of Kaizen Guide)

| File | Draft Size | Disk Size | Match | Notes |
|------|-----------|-----------|-------|-------|
| locustfile.py | 1965 bytes | 1965 bytes | Byte-for-byte identical | file_ollama_whole, no post-assembly transforms |
| email_server.py | — | 58 lines | N/A | Element-spliced assembly, no single draft |
| logger.py | — | 75 lines | N/A | Element-spliced assembly |
| recommendation_server.py | — | 32 lines | N/A | Element-spliced assembly |

For element-spliced files, there is no single "draft" to compare — each element has its own draft. The assembly gap (Section 5 of the guide) is where defects are introduced: class-body misplacement (email_server.py line 20), lost globals (PI-009 first pass), and empty implementations (email_client.py, client.py).

---

## 7. Success Reporting Caveats (Section 7 of Kaizen Guide)

The batch result reported `succeeded: 8` out of 9, but this masks semantic defects:

| Feature | Reported | Actual Runtime Quality |
|---------|----------|----------------------|
| PI-001 (logger.py) | success: true | **Crashes** — `datetime.utcfromtimestamp()` NameError |
| PI-003 (email_server.py) | success: true | **Crashes** — class-body print, missing self, no template |
| PI-004 (email_client.py) | success: true | **Empty** — `pass` body |
| PI-007 (client.py) | success: true | **Empty** — getLogger only |
| PI-008 (shoppingassistantservice.py) | success: true | **Broken** — Flask app not returned |

**Confirmed:** Section 7's warning holds — `success: true` means AST + element-level verdict passed, **not** runtime correctness. 5 of 8 "successful" features have runtime defects.

---

## 8. Systemic Issues

### 8.1 Element-Level Generation Loses Cross-Element Context

The #1 quality issue. Element-by-element Micro Prime generates each function/class in isolation. When elements depend on:
- Module-level globals (`fake = Faker()`, `product_ids = [...]`)
- Sibling function calls (`checkout` → `addToCart`)
- Class attributes referencing module-level functions (`tasks = {index: 1, ...}`)
- Instance attributes set in `__init__` (`self.template`)

...the splicer cannot reconstruct the dependencies. The result is either `F821` lint errors (caught, as with PI-009) or semantic bugs that pass AST validation (not caught, as with email_server.py).

**Recommendation:** Route files with cross-element dependencies through `file_ollama_whole`. The classifier should detect when elements reference names not in their own scope.

### 8.2 Postmortem Only Captures Last Resume

The postmortem system writes a single report per invocation. When a run has multiple resume invocations, only the last one is captured. Run-042 processed 17 features across 9 invocations but the postmortem reported 1/1. The Kaizen index, trends, and correlation data all undercount.

**Recommendation:** Accumulate postmortem results across resumes within the same `run_id`, or write per-resume postmortem files and aggregate at the end.

### 8.3 Context Key Pollution

The spec prompt for PI-009 (loadgenerator) contained 133 API signatures from ALL services. Only 11 were relevant. The Kaizen correlation data confirms `context_key_count` is the strongest negative correlate (ρ=-0.456).

**Recommendation:** Filter `api_signatures` in the spec prompt to only the target file's service. This is a low-effort, high-impact change.

### 8.4 Root Cause Attribution Gap

5 of 6 failed runs across the campaign reported `unknown` for both `root_cause` and `pipeline_stage` at the feature level. Only run-034 (`generation_error` / `ollama_generation`) and run-037 (element-level `splicer_mismatch`) provided actionable diagnostics.

**Recommendation:** The "No files were integrated" error path needs instrumentation to capture which step failed and why.

### 8.5 No Post-Assembly Semantic Validation

AST parsing catches syntax errors. Lint catches undefined names. But missing `self` parameters, unreachable code, discarded return values, and empty function bodies all pass both checks. A lightweight semantic gate (e.g., "does every non-stub function body contain at least one statement beyond `pass`?", "do all methods have `self` as first parameter?") would catch the Grade D/F files.

---

## 9. Recommendations

| Priority | Issue | Action | Impact |
|----------|-------|--------|--------|
| **P0** | Element-level splicer loses globals | Route cross-dependent files through `file_ollama_whole`; add classifier heuristic for shared-state detection | Fixes PI-009 first-pass failure, email_server.py defects |
| **P1** | Postmortem doesn't aggregate across resumes | Accumulate results per `run_id` across invocations | Fixes Kaizen index undercounting, trend accuracy |
| **P1** | No semantic validation post-assembly | Add lightweight checks: non-empty function bodies, `self` parameter on methods, return value on factory functions | Catches Grade D/F files before reporting success |
| **P2** | Context key pollution in spec prompts | Scope `api_signatures` to target service only | Addresses strongest Kaizen correlation signal (ρ=-0.456) |
| **P2** | Root cause attribution gap | Instrument "No files were integrated" error path | 5/6 failed runs currently report `unknown` |
| **P3** | `datetime` module vs class confusion | Add `datetime.datetime` to import completion repair step | Fixes logger.py runtime crash |

---

## 10. Appendix: Generated File Inventory

### Run-042 Output Directory

```
run-042-20260312T1434/plan-ingestion/generated/src/
├── emailservice/
│   ├── Dockerfile                    (68 lines)  PI-010  Grade A
│   ├── email_client.py               (5 lines)   PI-004  Grade F
│   ├── email_server.py               (58 lines)  PI-003  Grade D
│   ├── logger.py                     (75 lines)  PI-001  Grade B-
│   ├── requirements.in               (11 lines)  PI-014  Grade A
│   └── templates/
│       └── confirmation.html         (214 lines) PI-005  Grade A
├── loadgenerator/
│   ├── Dockerfile                    (61 lines)  PI-013  Grade A
│   ├── locustfile.py                 (79 lines)  PI-009  Grade A
│   └── requirements.in              (2 lines)    PI-017  Grade A
├── recommendationservice/
│   ├── client.py                     (6 lines)   PI-007  Grade F
│   ├── Dockerfile                    (50 lines)  PI-011  Grade A-
│   ├── recommendation_server.py      (32 lines)  PI-006  Grade B+
│   └── requirements.in              (8 lines)    PI-015  Grade A
└── shoppingassistantservice/
    ├── Dockerfile                    (55 lines)  PI-012  Grade A-
    ├── requirements.in               (6 lines)   PI-016  Grade A
    └── shoppingassistantservice.py   (65 lines)  PI-008  Grade C
```

### Result Files in Run Directory

```
prime-result-PI-001-...-PI-017.json   (14:54) Batch: 9 processed, 8 succeeded, 1 failed
prime-result-PI-009.json              (15:39) Resume: 1/1 PASS
prime-result-PI-010.json              (15:43) Resume: 1/1 PASS
prime-result-PI-011.json              (16:09) Resume: 1/1 PASS
prime-result-PI-012.json              (16:15) Resume: 1/1 PASS
prime-result-PI-013.json              (16:21) Resume: 1/1 PASS
prime-result-PI-014.json              (16:22) Resume: 1/1 PASS
prime-result-PI-015.json              (16:27) Resume: 1/1 PASS
prime-result-PI-016.json              (16:28) Resume: 1/1 PASS
prime-result-PI-017.json              (16:37) Resume: 1/1 PASS (postmortem captured this only)
```
