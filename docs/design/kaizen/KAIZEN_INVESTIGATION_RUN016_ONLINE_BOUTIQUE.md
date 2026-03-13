# Kaizen Investigation: Run 016 — Online Boutique Demo (Retry, Plan Completion)

**Date:** 2026-03-09
**Run:** `run-016-20260308T2237` (online-boutique-demo)
**Pipeline:** `.cap-dev-pipe/pipeline-output/online-boutique/run-016-20260308T2237/`
**Features examined:** PI-001 through PI-017 (full 17-feature plan)
**Status:** 17/17 complete, reported PASS (aggregate score 1.0)

---

## 1. Executive Summary

Run-016 completed the entire online-boutique 17-feature plan across two invocations,
processing the final 8 features (3 Dockerfiles, 1 Dockerfile, 4 requirements.in) at
$1.31 total. Combined with earlier runs within run-016 (PI-001 through PI-009), all
17 features report SUCCESS.

Manual quality inspection of all 15 generated source files reveals:

- **7 files are production-quality** (A tier, 90+): 4 Dockerfiles, locustfile, email template, email server
- **4 files are good with minor issues** (B tier, 80-89): recommendation server, test client, 2 requirements files
- **3 files have significant quality issues** (C tier, 65-79): both loggers, shopping assistant service, 1 requirements file
- **1 file is a non-functional stub** (D tier): email_client.py (function body is `pass`)

**Weighted average quality score: 83.2/100 (B+)**

The pipeline's self-reported 100% success rate diverges from actual usability.
The repair pipeline caught syntax/import errors in 100% of Python files but
did not catch semantic bugs (hallucinated APIs, dead code, stub bodies).

---

## 2. Run Structure

Run-016 completed in two invocations:

| Invocation | Features | Files | Cost | Route |
|------------|----------|-------|------|-------|
| 1 | PI-010, PI-011, PI-012 | 3 Dockerfiles | $0.763 | Cloud fallback |
| 2 | PI-013, PI-014, PI-015, PI-016, PI-017 | 1 Dockerfile + 4 requirements.in | $0.543 | Cloud fallback |
| **Total** | **8** | **8** | **$1.306** | |

All 8 features bypassed micro-prime (non-Python files) and went to cloud fallback.
The remaining 9 features (PI-001 through PI-009) were completed in earlier executions
within run-016's scope.

---

## 3. Per-Feature Quality Assessment

### 3.1 Python Files (PI-001 through PI-009)

| Feature | File | Grade | Key Issues |
|---------|------|-------|------------|
| PI-001 | emailservice/logger.py | C+ (70) | Wrong import (`jsonlogger` vs `pythonjsonlogger`), `datetime.datetime.now()` crash, duplicate `CustomJsonFormatter` classes |
| PI-002 | recommendationservice/logger.py | B+ (85) | `CustomJsonFormatter` defined but unused; `getJSONLogger` uses base `JsonFormatter` instead |
| PI-003 | emailservice/email_server.py | A- (90) | Complete gRPC server, proper lifecycle, minor: `initStackdriverProfiling` is no-op stub per spec |
| PI-004 | emailservice/email_client.py | D (40) | Function body is `pass` — non-functional skeleton reported as PASS |
| PI-005 | templates/confirmation.html | A (95) | Excellent email template, correct nanos formatting, empty-state handling |
| PI-006 | recommendationservice/recommendation_server.py | A- (88) | Complete service, module-level channel opened at import time |
| PI-007 | recommendationservice/client.py | B+ (85) | Clean test client, f-strings in log calls (minor) |
| PI-008 | shoppingassistantservice/shoppingassistantservice.py | C (65) | `google.cloud.vectordb.VectorStoreClient` doesn't exist, duplicate `talkToGemini()`, `app.run()` inside factory |
| PI-009 | loadgenerator/locustfile.py | A (93) | Proper Locust patterns, realistic flows, correct task weights |

### 3.2 Dockerfiles (PI-010 through PI-013)

| Feature | File | Grade | Key Highlights |
|---------|------|-------|----------------|
| PI-010 | emailservice/Dockerfile | A (95) | Multi-stage Alpine, grpcio-tools isolated via `--prefix=/build-tools`, non-root user, pinned SHA256 |
| PI-011 | recommendationservice/Dockerfile | A- (90) | Multi-stage Alpine, proto compilation, grpcio-tools not isolated (leaks to final image) |
| PI-012 | shoppingassistantservice/Dockerfile | A (95) | Correctly chose Debian slim (needs libpq, libssl), `--prefix=/install` pattern, `--no-log-init` |
| PI-013 | loadgenerator/Dockerfile | A (93) | Alpine, `GEVENT_SUPPORT=True`, exec-form with shell variable expansion |

### 3.3 Requirements Files (PI-014 through PI-017)

| Feature | File | Grade | Key Issues |
|---------|------|-------|------------|
| PI-014 | emailservice/requirements.in | B+ (85) | 19 deps, correct pins, missing category comments |
| PI-015 | recommendationservice/requirements.in | B (80) | 19 deps, no category comments, alphabetical sort inconsistent |
| PI-016 | shoppingassistantservice/requirements.in | C+ (75) | File contains LLM review commentary baked into output (lines 1-14 are analysis text, not requirements) |
| PI-017 | loadgenerator/requirements.in | A- (90) | 19 deps with category grouping and comments — best of the four |

---

## 4. Cross-Cutting Quality Findings

### 4.1 Repair Pipeline Activity

100% of Python files required import repair. 6 repair attempts across 5 files:

| File | Lint Errors | Repairs | Steps Applied |
|------|-------------|---------|---------------|
| logger.py (emailservice) | 3 | **2 passes** | fence_strip, import_completion (non-idempotent) |
| email_server.py | 12 | 1 pass | duplicate_removal, fence_strip, import_completion |
| recommendation_server.py | 19 | 1 pass | duplicate_removal, fence_strip, import_completion |
| shoppingassistantservice.py | 3 | 1 pass | extended_lint_fix, fence_strip, import_completion |
| locustfile.py | 17 | 1 pass | fence_strip, import_completion |

### 4.2 Requirements Cross-Contamination

All 4 services generated **identical 19-dependency lists**. emailservice should not
need `locust`, loadgenerator should not need `langchain`, etc. The LLM used the shared
plan context (which mentions all dependencies across all services) as the source for
each individual service.

### 4.3 Semantic Bugs That Survived Repair + Review

| Bug | File | Type |
|-----|------|------|
| `import jsonlogger` (wrong package) | logger.py (email) | Hallucinated import |
| `datetime.datetime.now()` (module vs class) | logger.py (email) | Name resolution |
| `google.cloud.vectordb.VectorStoreClient` (doesn't exist) | shoppingassistantservice.py | Hallucinated API |
| `talkToGemini()` duplicates `recommend()` | shoppingassistantservice.py | Dead code |
| `email_client.py` body is `pass` | email_client.py | Stub as PASS |
| Duplicate `CustomJsonFormatter` definitions | logger.py (email) | Dead code |

### 4.4 Framework Error Density

| Code Type | Avg Lint Errors Pre-Repair |
|-----------|--------------------------|
| Simple utility (logger) | 3 |
| Framework code (gRPC, Locust, OTel) | 12-19 |

Framework-specific code has **3-6x higher error density** due to domain-specific
import patterns (proto-generated modules, decorator-based registration, instrumentation
setup) that the code generator doesn't model well.

---

## 5. Element Registry Effectiveness

### 5.1 Registry Status

| Metric | Value |
|--------|-------|
| Registry entries | 66 |
| Storage | `.startd8/state/elements/` |
| Cross-run hits (runs 013-016) | **1** (1.2% hit rate) |
| Total element processing events | ~86 |

### 5.2 Hit/Miss by Run

| Run | Features | Micro-Prime Elements | Hits | Misses | Hit Rate |
|-----|----------|---------------------|------|--------|----------|
| Run-013 | 2 | 1 | **1** | 0 | 100% |
| Run-014 | 1 | 5 | 0 | 4 | 0% |
| Run-015 | 1 | 2 | 0 | 1 | 0% |
| Run-016 | 8 | 0 | 0 | 0 | N/A |

### 5.3 Why the Registry Isn't Delivering Value

1. **Cloud fallback bypasses registry.** When elements escalate, the whole feature
   goes to cloud, which generates from scratch without querying cached elements.

2. **First-run penalty.** Each feature's elements are new on first encounter. The
   one hit (`initStackdriverProfiling` in run-013) happened because the same file
   was re-processed after a prior run populated the registry.

3. **Pre-fill not wired.** REQ-MP-1106 (skeleton pre-fill from registry) is
   implemented but not integrated into the generation flow. Cached implementations
   sit in JSON files while skeletons start from `raise NotImplementedError`.

4. **Non-Python invisible.** 47% of features (Dockerfiles, requirements.in) bypass
   micro-prime entirely — no elements to cache or retrieve.

---

## 6. Cross-Run Trend

| Run | Date | Features | Cost | Cost/Feature | Verdict |
|-----|------|----------|------|-------------|---------|
| plan-ingestion | 2026-03-05 | 1 | $0.105 | $0.105 | PASS |
| run-005 | 2026-03-07 | 1 | $0.115 | $0.115 | PASS |
| run-006 | 2026-03-07 | 1 | $0.114 | $0.114 | PASS |
| run-008 | 2026-03-07 | 1 | $0.110 | $0.110 | PASS |
| run-009 | 2026-03-07 | 1 | $0.122 | $0.122 | PASS |
| run-010 | 2026-03-08 | 3 | $0.434 | $0.145 | PASS |
| run-013 | 2026-03-08 | 2 | $0.772 | $0.386 | PASS |
| run-014 | 2026-03-08 | 1 | $0.230 | $0.230 | PASS |
| run-015 | 2026-03-08 | 1 | $0.108 | $0.108 | PASS |
| **run-016** | **2026-03-08** | **3** | **$0.763** | **$0.254** | **PASS** |

10 consecutive PASS runs. Cost slope is +$0.053/run (driven by multi-feature
batches, not per-feature inflation). Run-016 flagged as cost outlier by trend
engine, but per-feature cost ($0.254) is within normal range.

---

## 7. Lessons Identified

| ID | Lesson | Impact | Priority |
|----|--------|--------|----------|
| L1 | Import tracking in code generator — 100% of files need repair | Eliminates 80%+ of repairs | HIGH |
| L2 | Semantic validation post-repair — hallucinated APIs, stubs survive | Catches 6 bugs that slipped through | MEDIUM |
| L3 | Per-service dependency scoping — all 4 services got identical deps | Prevents cross-contamination | HIGH |
| L4 | Structured constraint checking in review — design decisions violated | Catches spec fidelity gaps | LOW |
| L5 | Framework import templates — gRPC/Locust/OTel 3x error density | Reduces framework-specific failures | MEDIUM |

See `QUALITY_IMPROVEMENT_PLAN.md` for implementation plan addressing all 5 lessons.

---

## 8. Comparison to Prior Runs

| Metric | Run-004 (pre-fix) | Run-004 Sub-5 | Run-005 | Run-016 |
|--------|-------------------|---------------|---------|---------|
| Features | 7 | 6 | 4 | 17 |
| Reported success | 100% | 100% | 100% | 100% |
| Actual usable | 43% | 100% | 100% | 88% (15/17) |
| Broken skeletons | 3 | 0 | 0 | 1 (email_client) |
| Semantic bugs | Not measured | Not measured | Not measured | 6 |
| Import repair needed | Not measured | Not measured | Not measured | 100% of .py files |
| Total cost | $0.76 | $1.19 | $0.96 | $1.31 (final 8) |

Run-016 represents the most comprehensive quality assessment to date. The actual
usability gap (12% non-functional files vs 0% reported failures) is smaller than
run-004 (57%) but persists due to the lack of semantic validation.
