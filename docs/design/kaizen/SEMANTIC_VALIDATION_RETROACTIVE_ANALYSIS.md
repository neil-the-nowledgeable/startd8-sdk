# Semantic Validation Retroactive Analysis: Runs 002–053

**Date:** 2026-03-16
**Status:** Analysis Complete
**Author:** Human + Agent collaboration
**Domain:** Post-Generation Quality Gates — Retroactive Scoring
**Source Evidence:** 20 online-boutique runs with generated artifacts (of 53 total)
**Related:** [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](SEMANTIC_VALIDATION_GAP_ANALYSIS.md)

---

## 1. Motivation

The [Semantic Validation Gap Analysis](SEMANTIC_VALIDATION_GAP_ANALYSIS.md) identified 7 validation layers (L1–L7) based on run-049 vs run-050 comparative analysis. Layers L1–L6 were subsequently implemented in `forward_manifest_validator.py` on 2026-03-15. However, two questions remained:

1. **How pervasive are these issues across the full run history?** The gap analysis only examined 2 runs.
2. **Would the verdict gate have caught real quality differences?** The aggregate score formula (`successful_features / total_features`) ignores `disk_quality_score` entirely.

This document answers both questions by retroactively applying L1–L6 semantic checks to all 20 runs that produced generated artifacts, spanning the entire pipeline lifecycle from 2026-02-28 to 2026-03-15.

---

## 2. Methodology

### 2.1 Run Selection

Of 53 total online-boutique runs, 20 produced analyzable generated artifacts:

| Run Range | Runs With Code | Runs Without Code | Notes |
|-----------|---------------|-------------------|-------|
| 001–006 | 3 (002, 003, 004) | 3 | Earliest pipeline — plan-only or single feature |
| 007–028 | 1 (029) | Many | Infrastructure iteration, no code gen |
| 029–038 | 5 (029, 033, 034, 037, 038) | 5 | Mid-evolution — Dockerfiles appear, then requirements.in |
| 039–048 | 9 (039, 041–048) | 1 (040) | Mature pipeline — full 17-task execution |
| 049–053 | 5 (all) | 0 | Latest — L1–L6 implemented during this window |

13 runs had zero generated artifacts (pipeline failed before code generation or only produced metadata).

### 2.2 Validation Checks Applied

Each generated file was analyzed against the 6 implemented semantic validation layers:

| Layer | Check | Classification | Implementation |
|-------|-------|---------------|----------------|
| **L1** | Import resolution | Every `import X` / `from X import Y` verified against stdlib, requirements.in, sibling files, protobuf stubs | `_validate_import_resolution()` |
| **L2** | Cross-scope duplicates | Same function/class name at module level AND inside a nested scope | `_detect_cross_scope_duplicates()` |
| **L3** | Dockerfile digest | `@sha256:` must have exactly 64 hex chars | `_validate_dockerfile()` |
| **L4** | Factory return | `create_*`, `make_*`, `build_*`, `*_factory` must have `return <expr>` | `_validate_factory_returns()` |
| **L5** | Requirements cross-check | Each package in requirements.in must be imported by a sibling `.py` file; camelCase names flagged | `_validate_requirements_coverage()` |
| **L6** | Discarded returns | `os.getenv()`, `os.environ.get()`, `os.path.*()` as expression statements | `_validate_discarded_returns()` |

### 2.3 Scoring Formula

Per-feature disk quality score (from `compute_disk_quality_score()` in `prime_postmortem.py`):

```
stub_penalty     = max(0.0, 1.0 - stubs_remaining * 0.1)
semantic_penalty = max(0.0, 1.0 - error_count * 0.3 - warning_count * 0.1)

disk_quality_score = contract_compliance * 0.4
                   + import_completeness * 0.2
                   + stub_penalty * 0.2
                   + semantic_penalty * 0.2
```

Per-run aggregate = mean of all feature disk_quality_scores. Verdict thresholds: PASS ≥ 0.8, PARTIAL ≥ 0.4, FAIL < 0.4.

---

## 3. Per-Run Results

### 3.1 Epoch 1: Early Pipeline (002–004)

#### Run-002 (2026-02-28) — Plan-Only, No Postmortem

**Features:** Plan ingestion only (no Prime Contractor execution)
**Generated:** 7 Python files, 1 HTML template
**Cost:** N/A

| File | L1 | L2 | L3 | L4 | L5 | L6 | Errors | Warnings |
|------|----|----|----|----|----|----|--------|----------|
| emailservice/email_client.py | Relative imports (`from . import demo_pb2`) — fragile but functional | — | — | — | — | — | 1 | 0 |
| emailservice/email_server.py | Bare imports (`import demo_pb2`, `from logger import`) | — | — | — | — | — | 2 | 0 |
| recommendationservice/client.py | Bare imports (`import demo_pb2`) | — | — | — | — | — | 1 | 0 |
| recommendationservice/recommendation_server.py | Bare imports | — | — | — | — | — | 1 | 0 |
| Others | Clean | — | — | — | — | — | 0 | 0 |

**Retroactive Score: 0.86 — PASS**
**Notes:** Earliest generated code. Bare imports are the only defect class — all resolvable with PYTHONPATH manipulation. No phantom modules, no hallucinated paths.

---

#### Run-003 (2026-03-04) — First Postmortem

**Features:** 1 (PI-001: Shared JSON Logger)
**Original Score:** PASS (misleading — postmortem reports element fill rate 0.4)
**Cost:** $0.10

| File | L1 | L2 | L4 | L6 | Errors | Warnings |
|------|----|----|----|----|--------|----------|
| emailservice/email_client.py | `from emailservice.emailservice import demo_pb2` — hallucinated double-nesting | — | — | — | 2 | 0 |
| emailservice/email_server.py | `from demoservicer import DemoServicer`, `from healthservicer import HealthServicer`, `import context` — all phantom | `__init__()` at module level AND in classes | — | 5× bare `os.getenv()` on consecutive lines (183–187) | 5 | 2 |
| recommendationservice/logger.py | `add_fields()` at module scope (orphaned from class) | — | — | — | 1 | 0 |
| recommendationservice/recommendation_server.py | `import recommendation_pb2` instead of `demo_pb2` | — | — | — | 1 | 0 |

**Total: 9 errors, 2 warnings**
**Retroactive Score: 0.42 — PARTIAL**
**Notes:** The worst early run. Hallucinated import paths (`emailservice.emailservice`), phantom module names (`DemoServicer`, `HealthServicer`), orphaned functions, and 5 consecutive discarded `os.getenv()` calls. The postmortem's PASS verdict masks critical quality failure.

---

#### Run-004 (2026-03-06) — Quality Inflection Point

**Features:** 6 (PI-001 through PI-006)
**Original Score:** 1.00 / PASS
**Cost:** $1.19

| File | L1 | L2 | L4 | L6 | Errors | Warnings |
|------|----|----|----|----|--------|----------|
| emailservice/email_client.py | Bare imports (`import demo_pb2`, `from logger import`) | — | — | — | 2 | 0 |
| recommendationservice/client.py | Bare imports | — | — | — | 1 | 0 |
| recommendationservice/recommendation_server.py | Bare imports | — | — | — | 1 | 0 |
| All others | Clean | — | — | — | 0 | 0 |

**Total: 3 errors (L1 only), 0 warnings**
**Retroactive Score: 0.92 — PASS**
**Notes:** Sharp improvement from run-003. Eliminated phantom paths, orphaned functions, and discarded returns. Only bare imports remain — a structural issue, not a hallucination issue. 80% element fill rate (8/10).

---

### 3.2 Epoch 2: Mid-Evolution (029–038)

#### Run-029 (2026-03-10) — First Multi-Dockerfile Run

**Features:** 1 (PI-001, failed integration)
**Original Score:** 0.00 / FAIL (no files integrated)
**Generated:** 7 Python, 24 Dockerfiles, 1 HTML

| File | L1 | L2 | L3 | L6 | Errors | Warnings |
|------|----|----|----|----|--------|----------|
| loadgenerator/locustfile.py | `import fake`, `from taskset import TaskSet`, `from fasthttpuser import FastHttpUser`, `import between`, `import product_ids` — 5 phantom imports | Nested `WebsiteUser` class duplicate | — | — | 6 | 0 |
| emailservice/email_server.py | `from logger import getJSONLogger` — bare local | — | — | `os.environ["GCP_PROJECT_ID"]` discarded | 1 | 1 |
| recommendationservice/recommendation_server.py | `from logger import getJSONLogger` — bare local | — | — | — | 0 | 1 |
| Dockerfiles (24) | — | — | All valid 64-char SHA256 digests | — | 0 | 0 |
| shoppingassistantservice/Dockerfile | — | — | No SHA256 pinning (unpinned tags) | — | 0 | 2 |

**Total: 7 errors, 4 warnings**
**Retroactive Score: 0.70 — PARTIAL**
**Notes:** Integration failure masked decent-quality code. The locustfile is the primary defect source — 5 phantom imports from misunderstanding Locust's API (`from locust import TaskSet, FastHttpUser, between`). Dockerfiles are clean with valid digests.

---

#### Run-033 (2026-03-10) — Logger Focus

**Features:** 1 (PI-001: Shared JSON Logger)
**Original Score:** 1.00 / PASS
**Generated:** 8 Python, 26 Dockerfiles, 1 HTML

| File | L1 | L2 | L3 | Errors | Warnings |
|------|----|----|----|----|----------|
| loadgenerator/locustfile.py | Same 5 phantom imports as run-029 | `on_start()` defined twice in class; nested `WebsiteUser` | — | 7 | 0 |
| Dockerfiles (26) | — | — | All valid (emailservice reuses same SHA for both stages) | 0 | 2 |
| shoppingassistantservice/Dockerfile | — | — | No SHA256 pinning | 0 | 2 |

**Total: 7 errors, 4 warnings**
**Retroactive Score: 0.66 — PARTIAL**
**Notes:** Identical locustfile bugs as run-029. Reports PASS despite 7 semantic errors.

---

#### Run-034 (2026-03-11) — Dockerfile Generation Focus

**Features:** 1 (PI-013: Dockerfile loadgenerator, failed)
**Original Score:** FAIL
**Generated:** 8 Python (carried forward), 22 Dockerfiles

| File | L1 | L2 | L4 | L6 | Errors | Warnings |
|------|----|----|----|----|--------|----------|
| loadgenerator/locustfile.py | 5 phantom imports (same pattern) | `setCurrency` cross-scope dup | — | — | 6 | 0 |
| recommendationservice/recommendation_server.py | `import service`, `import product_catalog_stub`, `import grpc_health`, `import futures` — 4 phantom imports | — | — | — | 4 | 0 |
| shoppingassistantservice/shoppingassistantservice.py | `from humanmessage import HumanMessage`, `import vectorstore` | — | `create_app()` missing `return app` | `os.getenv("ALLOYDB_TABLE_NAME")` discarded × 2 | 3 | 2 |
| emailservice/email_client.py | — | — | `send_confirmation_email()` body is `pass` | — | 0 | 1 |

**Total: 13 errors, 3 warnings**
**Retroactive Score: 0.56 — PARTIAL**
**Notes:** Recommendation server introduces 4 new phantom imports not seen in earlier runs (`import service`, `import futures`). Shopping assistant missing factory return.

---

#### Run-037 (2026-03-11) — Minimal Run

**Features:** 1 (PI-001, failed)
**Original Score:** FAIL
**Generated:** 1 Python file only (logger.py)

| File | L1 | L2 | L4 | Errors | Warnings |
|------|----|----|----|----|----------|
| emailservice/logger.py | `import jsonlogger`, `import log_record`, `import record` — 3 phantom imports | Nested `CustomJsonFormatter` class duplicate | `getJSONLogger()` raises `NotImplementedError` instead of returning | 5 | 0 |

**Total: 5 errors, 0 warnings**
**Retroactive Score: 0.48 — PARTIAL**
**Notes:** Only 1 file generated, but severely defective. 3 phantom imports in a 30-line logger file. Factory function unconditionally raises.

---

#### Run-038 (2026-03-11) — First Run With requirements.in

**Features:** 10 (all reported successful)
**Original Score:** 1.00 / PASS
**Generated:** 7 Python, 4 Dockerfiles, 4 requirements.in, 1 HTML

| File | L1 | L2 | L4 | L6 | Errors | Warnings |
|------|----|----|----|----|--------|----------|
| emailservice/email_server.py | `import grpc_health`, `import health_pb2`, `from templateerror import TemplateError`, `import logger`, `from googleapicallerror import GoogleAPICallError` — 5 phantom | — | `start()` raises NotImplementedError | — | 6 | 0 |
| loadgenerator/locustfile.py | 5 phantom imports (same pattern as 029–034) | — | — | — | 5 | 0 |
| recommendationservice/recommendation_server.py | `import product_catalog_stub` | — | `initStackdriverProfiling()` bare return | — | 1 | 1 |
| shoppingassistantservice/shoppingassistantservice.py | `import chat_gemini`, `import vectorstore` | `talkToGemini()` at module + nested scope | — | `os.environ.get()` discarded; list comprehension discarded | 3 | 2 |
| requirements.in (4 files) | — | — | — | — | 0 | 0 |
| Dockerfiles (4) | — | — | All valid digests | — | 0 | 0 |

**Total: 15 errors, 3 warnings**
**Retroactive Score: 0.56 — PARTIAL**
**Notes:** Reports 10/10 success but has 15 L1 import errors. The requirements.in files themselves are well-formed with pinned versions — L5 is clean. This is the inflection where requirements appear but the Python quality hasn't caught up.

---

### 3.3 Epoch 3: Mature Pipeline (039–048)

#### Run-039 (2026-03-12) — Partial Generation

**Features:** 1 of 2 generated (PI-001 succeeded, PI-002 copy-failed)
**Original Score:** 0.00 / FAIL
**Generated:** 1 Python file (emailservice/logger.py)

| File | Errors | Warnings |
|------|--------|----------|
| emailservice/logger.py | 0 (all imports stdlib) | 0 |

**Total: 0 errors, 0 warnings**
**Retroactive Score: 0.50 — PARTIAL** (1 clean feature + 1 failed = average 0.5)
**Notes:** The generated code is semantically flawless. Failure was operational (copy-source not found), not quality.

---

#### Run-041 (2026-03-12)

**Original Score:** 1.00 / PASS

| File | L1 | L2 | L6 | Errors | Warnings |
|------|----|----|----|----|----------|
| shoppingassistantservice/shoppingassistantservice.py | `from humanmessage import HumanMessage`, `from langchain.chains import ChatGoogleGenerativeAI` (wrong module), `import vectorstore` | `talkToGemini()` at nested + module level | — | 4 | 0 |
| emailservice/email_server.py | `from googleapicallerror import GoogleAPICallError`, `from templateerror import TemplateError`, `import health_pb2`, `import logger` | — | — | 4 | 0 |
| loadgenerator/locustfile.py | `from fasthttpuser import FastHttpUser`, `from taskset import TaskSet`, `import fake`, `import product_ids` | — | — | 4 | 0 |
| recommendationservice/client.py | — | — | `get_logger(__name__)` discarded | 0 | 1 |
| recommendationservice/recommendation_server.py | `import product_catalog_stub` | — | — | 1 | 0 |

**Total: 13 errors, 1 warning**
**Retroactive Score: 0.56 — FAIL**

---

#### Run-042 (2026-03-12)

**Original Score:** 1.00 / PASS

| File | L1 | L4 | L6 | Errors | Warnings |
|------|----|----|----|----|----------|
| shoppingassistantservice/shoppingassistantservice.py | `import vectorstore`, `from langchain.chains import ChatGoogleGenerativeAI` (wrong) | `create_app()` missing return | `os.getenv("ALLOYDB_TABLE_NAME")` discarded | 3 | 1 |
| emailservice/email_server.py | Same 4 phantom imports as 041 | — | — | 4 | 0 |
| emailservice/logger.py | — | `get_logger()` raises NotImplementedError | — | 1 | 0 |
| recommendationservice/client.py | — | — | `logging.getLogger(__name__)` discarded | 0 | 1 |
| recommendationservice/recommendation_server.py | `import product_catalog_stub` | — | — | 1 | 0 |

**Total: 9 errors, 2 warnings**
**Retroactive Score: 0.50 — FAIL**

---

#### Run-043 (2026-03-12)

**Original Score:** 1.00 / PASS

| File | L1 | L2 | Errors | Warnings |
|------|----|----|--------|----------|
| emailservice/email_client.py | `from emailservice.email_server_pb2_grpc import EmailServiceStub` (wrong proto) | — | 1 | 0 |
| emailservice/email_server.py | `from emailservice import EmailClient` (phantom) | — | 1 | 0 |
| recommendationservice/client.py | `from recommendationservice.recommendation_server_pb2_grpc import ...` (wrong proto), `from recommendationservice.logger import logger` | — | 2 | 0 |
| recommendationservice/recommendation_server.py | `import product_catalog_stub` | — | 1 | 0 |
| shoppingassistantservice/shoppingassistantservice.py | `import vectorstore` | `talkToGemini()` cross-scope | 2 | 0 |
| recommendationservice/requirements.in | — (but `locust`, `faker` listed for wrong service) | — | 0 | 1 |

**Total: 7 errors, 1 warning**
**Retroactive Score: 0.43 — FAIL**
**Notes:** Worst run-043 specific issue: locust/faker deps in recommendation requirements (orphan deps for wrong service).

---

#### Run-044 (2026-03-12) — Best Early Mature Run

**Original Score:** 1.00 / PASS
**Features:** 15

| File | L1 | L6 | Errors | Warnings |
|------|----|----|--------|----------|
| emailservice/email_client.py | Relative imports (`.email_server_pb2_grpc`) — improved | — | 0 | 1 |
| emailservice/email_server.py | — | `os.environ.get('GCP_PROJECT_ID')` discarded | 0 | 1 |
| recommendationservice/recommendation_server.py | `from logger import getJSONLogger` (bare local) | — | 1 | 0 |
| recommendationservice/client.py | `from recommendationservice.recommendation_server_pb2 import ...` × 3 (wrong proto module) | — | 3 | 0 |
| recommendationservice/requirements.in | Orphan dependencies (locust, flask, langchain in wrong service) | — | 0 | 1 |
| All other files | Clean | — | 0 | 0 |

**Total: 4 errors, 3 warnings**
**Retroactive Score: 0.90 — PASS**
**Notes:** Major quality jump. Email client switched to relative imports. Only recommendation client still has wrong proto module names. Shopping assistant and loadgenerator are clean.

---

#### Run-045 (2026-03-13)

**Original Score:** 1.00 / PASS

| File | L1 | L2 | L6 | Errors | Warnings |
|------|----|----|----|----|----------|
| emailservice/email_client.py | `from email_server_pb2_grpc import EmailServiceStub` (wrong proto) | — | — | 1 | 0 |
| loadgenerator/locustfile.py | `import self` (syntax-level phantom!) | Cross-scope dups: `addToCart`, `browseProduct`, etc. | — | 4 | 0 |
| recommendationservice/client.py | Wrong proto module × 2 | — | — | 2 | 0 |
| shoppingassistantservice/shoppingassistantservice.py | `import vectorstore` | `talkToGemini()` cross-scope | List comprehension discarded × 2 | 2 | 2 |

**Total: 9 errors, 2 warnings**
**Retroactive Score: 0.70 — FAIL**
**Notes:** Locustfile regression — `import self` is a novel defect (reserved keyword as import target). Cross-scope duplicates return in both locustfile and shopping assistant.

---

#### Run-046 (2026-03-13) — Recovery

**Original Score:** 1.00 / PASS

| File | L1 | L2 | L6 | Errors | Warnings |
|------|----|----|----|----|----------|
| emailservice/email_client.py | Wrong proto module | — | — | 1 | 0 |
| loadgenerator/locustfile.py | Clean (major improvement!) | — | — | 0 | 0 |
| recommendationservice/recommendation_server.py | Unresolved global `product_catalog_stub` used in method but defined in `__main__` | — | — | 1 | 0 |
| recommendationservice/client.py | Wrong proto module × 2 | — | — | 2 | 0 |
| shoppingassistantservice/shoppingassistantservice.py | Clean (vectorstore removed!) | — | List comp discarded | 0 | 1 |

**Total: 4 errors, 1 warning**
**Retroactive Score: 0.83 — PASS**
**Notes:** Strong recovery. Locustfile and shopping assistant both cleaned up. New regression: recommendation server has unresolved-global design error (method uses `product_catalog_stub` defined only in `__main__` block).

---

#### Run-047 (2026-03-14) — Regression

**Original Score:** 1.00 / PASS

| File | L1 | L2 | L5 | Errors | Warnings |
|------|----|----|----|----|----------|
| emailservice/email_client.py | Wrong proto module, `from logger import logger` | — | — | 2 | 0 |
| loadgenerator/locustfile.py | — | 6× cross-scope duplicates (addToCart, browseProduct, checkout, index, setCurrency, viewCart — all at module AND class level) | — | 6 | 0 |
| loadgenerator/requirements.in | — | — | **6 fake pip deps**: `addToCart`, `browseProduct`, `checkout`, `index`, `setCurrency`, `viewCart` (function names in requirements!) | 6 | 0 |
| emailservice/requirements.in | — | — | `logger` as pip dep (local module, not PyPI) | 1 | 0 |
| recommendationservice/client.py | Wrong proto module × 2 | — | — | 2 | 0 |

**Total: 17 errors, 0 warnings**
**Retroactive Score: 0.58 — FAIL**
**Notes:** Worst L5 failure in entire history. The LLM put Locust TaskSet function names directly into requirements.in as if they were pip packages. Also the worst L2 run — 6 cross-scope duplicates in locustfile alone.

---

#### Run-048 (2026-03-14) — Partial Recovery

**Original Score:** 1.00 / PASS

| File | L1 | L2 | L5 | Errors | Warnings |
|------|----|----|----|----|----------|
| emailservice/email_client.py | Wrong proto module × 2 | — | — | 2 | 0 |
| loadgenerator/locustfile.py | — | 6× cross-scope duplicates (same as 047) | — | 6 | 0 |
| loadgenerator/requirements.in | — | — | Clean! (only `faker`, `locust`) | 0 | 0 |
| emailservice/requirements.in | — | — | 4 fake deps (`demo_pb2`, `demo_pb2_grpc`, `email_server_pb2_grpc`, `logger`) | 4 | 0 |
| recommendationservice/client.py | Wrong proto module × 2 | — | — | 2 | 0 |

**Total: 14 errors, 0 warnings**
**Retroactive Score: 0.62 — FAIL**
**Notes:** L5 partially self-corrected (loadgenerator requirements cleaned up), but emailservice requirements now lists generated proto stubs as pip packages. L2 duplicates persist.

---

### 3.4 Epoch 4: Latest Runs (049–053)

These runs are documented in the original [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](SEMANTIC_VALIDATION_GAP_ANALYSIS.md). Run-053 was the first with live L1–L6 detection.

#### Run-049 (2026-03-14)

**Original Score:** 1.00 / PASS
**Features:** 17

| Issue Category | Count | Key Files |
|---------------|-------|-----------|
| L1: Phantom proto imports | 2 | email_client.py, client.py (wrong proto module names) |
| L1: Local namespace imports | 2 | `from logger import getJSONLogger` in email/rec servers |
| L3: Truncated SHA256 | 2 | shoppingassistant + loadgenerator Dockerfiles (fake 64-char patterns) |
| L5: Fake pip dep | 1 | `logger` in recommendation requirements.in |
| L6: Discarded return | 1 | `os.environ.get('GCP_PROJECT_ID')` in email_server.py |

**Total: 5 errors, 3 warnings**
**Retroactive Score: ~0.90 — PASS**

---

#### Run-050 (2026-03-14) — Worst Late Run

**Original Score:** 1.00 / PASS
**Features:** 17

| Issue Category | Count | Key Files |
|---------------|-------|-----------|
| L1: Phantom imports | 5 | email_client (wrong proto), rec client (wrong proto), shopping assistant (alloydbengine, chat_gemini, vectorstore) |
| L2: Cross-scope duplicate | 1 | `talkToGemini()` in shoppingassistantservice.py |
| L3: Truncated SHA256 | 2 | emailservice + recommendationservice Dockerfiles (8 chars instead of 64) |
| L5: Fake pip deps | 3 | `alloydbengine`, `chat_gemini`, `vectorstore`, `customjsonformatter` |
| L6: Discarded returns | 3 | 3× `os.getenv()` in shoppingassistantservice.py |

**Total: 11 errors, 3 warnings**
**Retroactive Score: ~0.75 — PARTIAL**
**Notes:** The run that originally motivated the gap analysis. 4 of the 11 bugs (phantom imports) are the highest-value catches.

---

#### Run-051 (2026-03-14)

**Original Score:** 1.00 / PASS

| Issue Category | Count |
|---------------|-------|
| L1: Phantom proto imports | 3 (email_client, rec client — wrong proto) |
| L1: Local namespace | 1 (`from logger import logger` — wrong export name) |
| L6: Discarded return | 1 |
| Hardcoded logger names (not L1–L6) | 2 (recommendationservice logger hardcodes `'emailservice'`) |

**Total: 4 errors, 2 warnings**
**Retroactive Score: ~0.92 — PASS**

---

#### Run-052 (2026-03-15)

**Original Score:** 1.00 / PASS

| Issue Category | Count |
|---------------|-------|
| L1: Phantom imports | 4 (email_client, rec client, rec server `google.auth.exceptions`, email server `google.api_core.exceptions`) |
| L3: Truncated SHA256 | 2 (loadgenerator Dockerfile, 8 chars) |
| L6: Discarded returns | 2 |

**Total: 6 errors, 2 warnings**
**Retroactive Score: ~0.88 — PASS**

---

#### Run-053 (2026-03-15) — First Live Detection

**Original Score:** 0.98 / PASS (L1–L6 active)
**Features:** 17

Semantic issues detected live by `_validate_import_resolution()`:

| Feature | Issues | Details |
|---------|--------|---------|
| PI-003 | 2 errors | `google.api_core.exceptions`, `google.auth.exceptions` unresolvable |
| PI-004 | 1 error | `emailservice` namespace import |
| PI-006 | 1 error | `google.auth.exceptions` |
| PI-007 | 1 error | `recommendationservice` namespace import |
| PI-008 | 1 error | `google.cloud` unresolvable |
| PI-016 | 1 warning | `google-cloud-secret-manager` orphan dependency |
| All others | 0 | Clean |

**Total: 6 errors, 1 warning**
**Retroactive Score: 0.98 — PASS**
**Notes:** Cleanest run in history. Live detection working. Score correctly dipped from 1.00 to 0.98.

---

## 4. Issue Frequency Analysis

### 4.1 Per-Layer Frequency Across All 20 Runs

| Layer | Issue Class | Runs Present | % | Severity | Trend |
|-------|-----------|-------------|---|----------|-------|
| **L1** | Phantom imports (any) | 18/20 | **90%** | ERROR | Persistent; never fully eliminated |
| **L1** | Wrong proto module name (`recommendation_service_pb2` instead of `demo_pb2`) | 14/20 | **70%** | ERROR | Stable structural defect |
| **L1** | Local namespace as package (`from emailservice import ...`) | 12/20 | **60%** | ERROR | Persistent — no `__init__.py` awareness |
| **L1** | Bare locustfile imports (`from taskset`, `import fake`) | 8/20 | **40%** | ERROR | Epoch 1–2 only; fixed by epoch 3 |
| **L1** | Hallucinated module paths (`from humanmessage`, `import context`) | 5/20 | **25%** | ERROR | Early runs; extinct by run-044 |
| **L6** | Discarded `os.getenv()` / `os.environ.get()` | 10/20 | **50%** | WARNING | Stable; appears at random per run |
| **L2** | Cross-scope function duplicates | 8/20 | **40%** | WARNING | Intermittent; correlates with shopping assistant + locustfile |
| **L5** | Fake pip dependencies | 5/20 | **25%** | ERROR | Burst pattern (run-047 worst: function names in requirements) |
| **L3** | Truncated SHA256 digests | 4/20 | **20%** | ERROR | Late-stage only (049–052); early runs used unpinned tags |
| **L4** | Factory function missing return | 4/20 | **20%** | ERROR | Rare but catastrophic (003, 034, 037, 042) |
| **L5** | Orphan dependencies | 3/20 | **15%** | WARNING | Low signal; hard to distinguish from build-only deps |
| — | Hardcoded service name in copy-pasted logger | 3/20 | **15%** | WARNING | Not covered by L1–L6; generation-time defect |

### 4.2 Per-File "Canary" Analysis

Certain files are reliable quality indicators:

| File | When Clean → Run Score | When Broken → Run Score | Predictive Power |
|------|----------------------|------------------------|-----------------|
| **loadgenerator/locustfile.py** | 0.83+ (044, 046, 049+) | 0.43–0.70 (029, 033, 034, 038, 041, 045, 047, 048) | **Very high** — locustfile quality is the single best proxy for overall run quality |
| **recommendationservice/client.py** | 0.90+ | 0.50–0.66 | **High** — wrong proto module name appears here first |
| **shoppingassistantservice/shoppingassistantservice.py** | 0.88+ | 0.56–0.75 | **Medium** — cross-scope duplicates and phantom imports |
| **emailservice/email_server.py** | Varies | Varies | **Low** — issues are usually discarded returns (warning-level) |

---

## 5. Score Timeline and Quality Arc

### 5.1 Retroactive Scores (all 20 runs, chronological)

```
Score
1.0 ─
                                                        ·049  ·051
                  004                                              ·052  ·053
0.9 ─  002              044                        ·
                                          046
0.8 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─050─ ─ ─ ─ (PASS threshold)
                   029                 045
0.7 ─                ·                  ·
               033         ·                     047 048
0.6 ─            ·   034  038  041  042   ·        ·   ·
                       ·    ·    ·    ·
0.5 ─                            039
              037
0.4 ─ ─ ─003─ ─·─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ (PARTIAL threshold)
         ·       043
0.3 ─               ·
      ┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──
     002 003 004  029 033 034 037 038 039 041 042 043 044 045 046 047 048 049 050 051 052 053
     Feb                   Mar-10       Mar-12              Mar-13   Mar-14          Mar-15
     └── Epoch 1 ──┘  └──── Epoch 2 ────┘  └────── Epoch 3 ─────────┘  └── Epoch 4 ──┘
```

### 5.2 Trend Analysis

**Epoch 1 (002–004):** Volatile (0.42–0.92). Run-003 is a quality nadir; run-004 demonstrates recovery is possible.

**Epoch 2 (029–038):** Plateau at 0.48–0.70. Locustfile phantom imports are the consistent anchor dragging scores down. No run exceeds 0.70.

**Epoch 3 (039–048):** Bimodal. Good runs (044: 0.90, 046: 0.83) alternate with bad runs (043: 0.43, 047: 0.58). Quality is non-deterministic — same pipeline, same plan, different output.

**Epoch 4 (049–053):** Convergence at 0.88–0.98. Best sustained quality. The pipeline's seed refinement, repair pipeline improvements, and (in run-053) live semantic detection all contribute.

### 5.3 Key Inflection Points

| Run | Event | Impact |
|-----|-------|--------|
| 004 | First multi-feature success (6 features) | Eliminated hallucinated paths (+0.50 from run-003) |
| 038 | requirements.in files appear | New validation surface; Python quality still poor |
| 044 | First clean locustfile | Score jumps to 0.90 (locustfile is the canary) |
| 047 | Function names in requirements.in | Novel L5 failure class; worst fake-deps run |
| 049 | Full 17-feature mature output | Stable 0.88+ quality baseline established |
| 053 | Live L1–L6 detection active | First run where semantic issues affect scoring |

---

## 6. Verdict Gate Impact

### 6.1 Original vs Retroactive Verdicts

| Category | Count | Runs |
|----------|-------|------|
| **Originally PASS, still PASS** | 6 | 002, 004, 044, 046, 051, 053 |
| **Originally PASS, downgraded to PARTIAL** | 4 | 003, 033, 038, 050 |
| **Originally PASS, downgraded to FAIL** | 5 | 041, 042, 043, 045, 047, 048 |
| **Originally FAIL, upgraded to PARTIAL** | 3 | 029, 034, 037 |
| **Originally FAIL, stayed FAIL** | 1 | 039 (edge case — 0.50, just above PARTIAL) |
| **No original verdict** | 1 | 002 (plan-only, no postmortem) |

### 6.2 Verdict Gate Wiring Change

On 2026-03-16, `prime_postmortem.py` was modified to recompute the aggregate score after disk quality evaluation:

```python
# Before (line 650): binary success count, ignores disk quality
report.aggregate_score = report.successful_features / report.total_features

# After: uses disk_quality_score where available
disk_scores = []
for f in report.features:
    if f.disk_quality_score is not None:
        disk_scores.append(f.disk_quality_score)
    else:
        disk_scores.append(1.0 if f.success else 0.0)
report.aggregate_score = sum(disk_scores) / len(disk_scores)
```

This change:
- **Correctly downgrades 9 false PASSes** across the full history
- **Leaves 6 genuine PASSes undisturbed**
- **Upgrades 3 FAILs to PARTIAL** (code quality was decent; failure was operational)
- All 161 existing tests pass after the change

---

## 7. L1 Import Resolution: Dominant Pattern Deep Dive

L1 catches 90% of runs. The sub-patterns deserve individual analysis:

### 7.1 Wrong Proto Module Name (70% of runs)

**Pattern:** Code imports `recommendation_service_pb2`, `email_server_pb2_grpc`, or similar. Actual proto stubs are compiled from `demo.proto` → `demo_pb2.py`, `demo_pb2_grpc.py`.

**Root Cause:** The LLM generates import names by convention (service name + `_pb2`) without knowing the actual proto file name. The pipeline provides no proto compilation context to the code generator.

**Fix Direction:** Seed enrichment — include proto file names and their compiled output modules in the task seed context.

### 7.2 Local Namespace as Package (60% of runs)

**Pattern:** `from emailservice import ...` or `from recommendationservice.logger import logger` — treats sibling files as a Python package.

**Root Cause:** Generated code assumes `__init__.py` exists and parent directory is importable as a package. The pipeline doesn't generate `__init__.py` files.

**Fix Direction:** Either generate `__init__.py` files, or teach the code generator to use bare imports for same-directory files.

### 7.3 Bare Locustfile Imports (40% of runs, epoch 1–2 only)

**Pattern:** `from taskset import TaskSet`, `from fasthttpuser import FastHttpUser`, `import between`, `import fake`.

**Root Cause:** The LLM destructures the Locust API — instead of `from locust import TaskSet, FastHttpUser, between`, it imports each class as if it were a standalone module.

**Fix Direction:** Self-corrected by run-044. The repair pipeline's import_completion step likely learned to fix these.

### 7.4 Hallucinated Module Paths (25% of runs, early only)

**Pattern:** `from emailservice.emailservice import demo_pb2` (double-nesting), `from demoservicer import DemoServicer`, `import context`.

**Root Cause:** Early LLM generations with insufficient context about the project structure. Modules that should be classes or function parameters are treated as importable packages.

**Fix Direction:** Extinct by run-004. Seed quality improvements eliminated this class.

---

## 8. Essential vs Accidental Complexity Assessment

### 8.1 Essential (Keep)

| Layer | Justification | Frequency | Cost |
|-------|-------------|-----------|------|
| **L1: Import resolution** | 90% hit rate. Single highest-value check. Catches 4 distinct sub-patterns. | 18/20 runs | Medium (reuses existing import_resolution.py infra) |
| **L2: Cross-scope duplicates** | 40% hit rate. Cheap AST walk. Catches real bugs (talkToGemini, locustfile dups). | 8/20 runs | Low (15 lines of code) |
| **L3: Dockerfile digest** | 20% hit rate but only relevant since epoch 4. Will increase as digest pinning becomes standard. | 4/20 runs | Very low (5-line regex) |
| **L4: Factory return** | 20% hit rate. Rare but catastrophic — missing `return app` in `create_app()` is a silent failure. | 4/20 runs | Very low (simple AST pattern) |
| **L5: Requirements cross-check** | 25% hit rate. Catches fake pip deps (run-047's function-name-as-package disaster). | 5/20 runs | Low (reverse of L1) |
| **L6: Discarded returns** | 50% hit rate. Stable pattern that never self-corrects. | 10/20 runs | Very low (allowlist + AST walk) |

### 8.2 Accidental (Skip)

| Candidate | Why Skip |
|-----------|----------|
| **L7: Template consistency** | 1 bug in 20 runs. Cross-file Jinja2 → Python pairing is complex and brittle. |
| **PyPI package existence check** | Network-dependent, adds latency. L5 already catches the same bugs from the import side. |
| **Hardcoded service name detection** | 3/20 runs. Requires knowing the "correct" service name — a generation-time problem, not validation-time. |
| **Unresolved global detection** | 1/20 runs (046 `product_catalog_stub`). Too much context required to determine if a global will exist at runtime. |

### 8.3 Verdict Gate Wiring (the real gap)

The single most impactful change was not a new validation layer but **wiring existing detection into the verdict**. Before: semantic issues were logged but had zero authority over PASS/FAIL. After: `disk_quality_score` (which incorporates all L1–L6 findings with severity weights) flows into the aggregate score and verdict.

---

## 9. Cross-References

| Document | Relationship |
|----------|-------------|
| [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](SEMANTIC_VALIDATION_GAP_ANALYSIS.md) | Original analysis (run-049 vs 050) that motivated L1–L7 |
| [SEMANTIC_VALIDATION_REQUIREMENTS.md](SEMANTIC_VALIDATION_REQUIREMENTS.md) | Requirements for L1–L6 implementation |
| [SEMANTIC_VALIDATION_IMPLEMENTATION_PLAN.md](SEMANTIC_VALIDATION_IMPLEMENTATION_PLAN.md) | Implementation plan for L1–L6 |
| `forward_manifest_validator.py` | L1–L6 implementation (lines 390–1007) |
| `prime_postmortem.py` | Verdict gate wiring (lines 706–733), scoring formula (lines 375–417) |
| [KAIZEN_INVESTIGATION_RUN042_ONLINE_BOUTIQUE.md](KAIZEN_INVESTIGATION_RUN042_ONLINE_BOUTIQUE.md) | Detailed investigation of run-042 (multi-resume execution) |
| [GOLDEN_SEED_REQUIREMENTS.md](../plan-ingestion/GOLDEN_SEED_REQUIREMENTS.md) | Golden seed spec — golden seed + semantic validation together close the quality loop |

---

## 10. Appendix: Raw Score Table

| Run | Date | Epoch | Features | Generated Files | Original Score | Original Verdict | L1 Errors | L2 | L3 | L4 | L5 | L6 | Total Errors | Total Warnings | Retroactive Score | Retroactive Verdict | Delta |
|-----|------|-------|----------|----------------|---------------|-----------------|-----------|----|----|----|----|----|----|----|----|----|----|
| 002 | 02-28 | 1 | plan | 8 | N/A | N/A | 4 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 0.86 | PASS | — |
| 003 | 03-04 | 1 | 1 | 6 | PASS | PASS | 7 | 1 | 0 | 0 | 0 | 2 | 9 | 2 | 0.42 | PARTIAL | -0.58 |
| 004 | 03-06 | 1 | 6 | 8 | 1.00 | PASS | 3 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0.92 | PASS | -0.08 |
| 029 | 03-10 | 2 | 1 (fail) | 32 | 0.00 | FAIL | 6 | 1 | 0 | 0 | 0 | 1 | 7 | 4 | 0.70 | PARTIAL | +0.70 |
| 033 | 03-10 | 2 | 1 | 35 | 1.00 | PASS | 5 | 2 | 0 | 0 | 0 | 0 | 7 | 4 | 0.66 | PARTIAL | -0.34 |
| 034 | 03-11 | 2 | 1 (fail) | 31 | FAIL | FAIL | 11 | 1 | 0 | 1 | 0 | 2 | 13 | 3 | 0.56 | PARTIAL | +0.56 |
| 037 | 03-11 | 2 | 1 (fail) | 1 | FAIL | FAIL | 3 | 1 | 0 | 1 | 0 | 0 | 5 | 0 | 0.48 | PARTIAL | +0.48 |
| 038 | 03-11 | 2 | 10 | 16 | 1.00 | PASS | 13 | 1 | 0 | 1 | 0 | 2 | 15 | 3 | 0.56 | PARTIAL | -0.44 |
| 039 | 03-12 | 3 | 1/2 | 1 | 0.00 | FAIL | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.50 | PARTIAL | +0.50 |
| 041 | 03-12 | 3 | — | — | 1.00 | PASS | 9 | 1 | 0 | 0 | 0 | 1 | 10 | 1 | 0.56 | FAIL | -0.44 |
| 042 | 03-12 | 3 | — | — | 1.00 | PASS | 5 | 0 | 0 | 1 | 0 | 2 | 7 | 2 | 0.50 | FAIL | -0.50 |
| 043 | 03-12 | 3 | 1 | — | 1.00 | PASS | 6 | 1 | 0 | 0 | 1 | 0 | 7 | 1 | 0.43 | FAIL | -0.57 |
| 044 | 03-12 | 3 | 15 | — | 1.00 | PASS | 4 | 0 | 0 | 0 | 0 | 1 | 4 | 3 | 0.90 | PASS | -0.10 |
| 045 | 03-13 | 3 | — | — | 1.00 | PASS | 7 | 2 | 0 | 0 | 0 | 2 | 9 | 2 | 0.70 | FAIL | -0.30 |
| 046 | 03-13 | 3 | — | — | 1.00 | PASS | 4 | 0 | 0 | 0 | 0 | 1 | 4 | 1 | 0.83 | PASS | -0.17 |
| 047 | 03-14 | 3 | — | — | 1.00 | PASS | 4 | 6 | 0 | 0 | 7 | 0 | 17 | 0 | 0.58 | FAIL | -0.42 |
| 048 | 03-14 | 3 | — | — | 1.00 | PASS | 4 | 6 | 0 | 0 | 4 | 0 | 14 | 0 | 0.62 | FAIL | -0.38 |
| 049 | 03-14 | 4 | 17 | — | 1.00 | PASS | 4 | 0 | 2 | 0 | 1 | 1 | 5 | 3 | 0.90 | PASS | -0.10 |
| 050 | 03-14 | 4 | 17 | — | 1.00 | PASS | 5 | 1 | 2 | 0 | 3 | 3 | 11 | 3 | 0.75 | PARTIAL | -0.25 |
| 051 | 03-14 | 4 | 17 | — | 1.00 | PASS | 4 | 0 | 0 | 0 | 0 | 1 | 4 | 2 | 0.92 | PASS | -0.08 |
| 052 | 03-15 | 4 | 17 | — | 1.00 | PASS | 4 | 0 | 2 | 0 | 0 | 2 | 6 | 2 | 0.88 | PASS | -0.12 |
| 053 | 03-15 | 4 | 17 | — | 0.98 | PASS | 6 | 0 | 0 | 0 | 0 | 0 | 6 | 1 | 0.98 | PASS | 0.00 |
