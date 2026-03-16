# Run-055 Evaluation — Post-Contracts Cleanup

> **Date:** 2026-03-16
> **Run:** run-055-20260316T1737
> **Aggregate Score:** 0.986 / PASS
> **Features:** 17/17 passed
> **Cost:** $0.53
> **Context:** First run after REQ-SIG-200/201 (service communication graph threading) and semantic validation hardening (REQ-SV2-100/200/300/700). Binding injection removal (GAP-SDK-003) and REQ-SV2-1300/1400 were merged but not yet active in the seed used for this run.

---

## 1. Per-Feature Letter Grades

| Feature | File | Grade | Score | Summary |
|---|---|---|---|---|
| PI-001 | emailservice/logger.py | **A** | 1.00 | Clean. 9 elements, all AST-valid. Correct `__all__`. |
| PI-002 | recommendationservice/logger.py | **B+** | 1.00 | Functional but hardcodes `component='emailservice'` (lines 17, 64, 74). Copy-paste identity bug. |
| PI-003 | emailservice/email_server.py | **A-** | 0.96 | Correct proto imports. 1 discarded return (L6), 1 intentional stub. |
| PI-004 | emailservice/email_client.py | **C+** | 1.00 | Wrong proto module names (`email_service_pb2` instead of `demo_pb2`). L1 false negative. |
| PI-005 | emailservice/templates/confirmation.html | **A** | 1.00 | HTML template, non-Python. |
| PI-006 | recommendationservice/recommendation_server.py | **A** | 0.98 | Best file. Correct protos, correct logger, proper OTel, gRPC health. 1 intentional stub. |
| PI-007 | recommendationservice/client.py | **D** | 1.00 | Hallucinated imports + logger formatters spliced into test client. False negative in scoring. |
| PI-008 | shoppingassistantservice/shoppingassistantservice.py | **A** | 0.88 | Excellent code. 2 L1 FPs (`google.cloud`, `langchain.schema`). 1 escalated element. |
| PI-009 | loadgenerator/locustfile.py | **B+** | 0.94 | Correct Locust imports. `self.index()` method resolution bug. 2 orphaned functions. |
| PI-010 | emailservice/Dockerfile | **A** | 1.00 | Clean. |
| PI-011 | recommendationservice/Dockerfile | **A** | 1.00 | Clean. |
| PI-012 | shoppingassistantservice/Dockerfile | **A** | 1.00 | Clean. |
| PI-013 | loadgenerator/Dockerfile | **A** | 1.00 | Clean. No fabricated digests. |
| PI-014 | emailservice/requirements.in | **A** | 1.00 | Clean. |
| PI-015 | recommendationservice/requirements.in | **A** | 1.00 | Clean. |
| PI-016 | shoppingassistantservice/requirements.in | **A** | 1.00 | Clean. |
| PI-017 | loadgenerator/requirements.in | **A** | 1.00 | Clean. No fake pip deps. |

### Grade Distribution

```
A  : 12 features (71%)  — production quality
A- :  1 feature  ( 6%)  — minor warning-level issue
B+ :  2 features (12%)  — functional with known defects
C+ :  1 feature  ( 6%)  — would fail at runtime
D  :  1 feature  ( 6%)  — structurally broken
```

---

## 2. Detailed Findings

### F-1: PI-007 False Negative — Score 1.00 for Grade-D Code

**Severity:** Critical (scoring integrity)
**File:** `recommendationservice/client.py`

The file imports `from recommendationservicestub import RecommendationServiceStub` and `from listrecommendationsrequest import ListRecommendationsRequest` — both are hallucinated module names (should be `from demo_pb2_grpc import RecommendationServiceStub` and `from demo_pb2 import ListRecommendationsRequest`).

Additionally, the file contains 2 logger formatter classes (`CustomJsonFormatter`, `JsonFormatter`) that don't belong in a test client. The `[REPAIRED BY STARTD8]` header indicates the repair pipeline spliced in wrong content.

The L1 validator scored this 1.00 because the hallucinated names (`recommendationservicestub`, `listrecommendationsrequest`) are being treated as resolvable local files — they match the pattern of bare sibling imports.

**Root cause:** L1 import resolution resolves bare imports as "local file" without checking whether the file actually exists in the project. Any single-word import passes.

### F-2: PI-004 False Negative — Score 1.00 for Wrong Proto Modules

**Severity:** High (scoring integrity)
**File:** `emailservice/email_client.py`

Imports `from email_service_pb2 import SendOrderConfirmationRequest` — proto stubs are compiled from `demo.proto`, not `email_service.proto`. The actual module is `demo_pb2`.

Same L1 false negative mechanism as F-1: `email_service_pb2` resolves as a plausible local file name.

**Root cause:** Same as F-1. The validator lacks a proto stub inventory (golden seed `import_map` from REQ-GS-302 would fix this).

### F-3: PI-008 False Positives — Score 0.88 for Grade-A Code

**Severity:** High (scoring integrity, opposite direction)
**File:** `shoppingassistantservice/shoppingassistantservice.py`

Two L1 errors flagged:
- `google.cloud` at line 22 — valid import for `google-cloud-secret-manager`
- `langchain.schema` at line 25 — valid import for `langchain`

Both are correct imports from packages listed in the project's requirements. The alias mapping in `package_aliases.py` doesn't cover:
- `google-cloud-secret-manager` → `google.cloud.secretmanager` (but `google.cloud` is the top-level)
- `langchain` → `langchain.schema` (sub-module)

**Root cause:** REQ-SV2-200 added GCP aliases for `storage`, `bigquery`, `logging`, `profiler` but not `secretmanager`. Also, `langchain` sub-module resolution isn't handled.

### F-4: PI-002 Copy-Paste Service Identity

**Severity:** Medium (functional but wrong)
**File:** `recommendationservice/logger.py`

`CustomJsonFormatter.__init__` defaults `component='emailservice'` (line 17). `get_logger` defaults `name='emailservice'` (line 74). The recommendation service logger identifies itself as emailservice.

Same bug appeared in 3/20 retroactive runs. REQ-SV2-400 (L8) would catch this but is not yet implemented.

### F-5: PI-003 Discarded Return

**Severity:** Low (warning, functional)
**File:** `emailservice/email_server.py`

`os.environ.get('GCP_PROJECT_ID')` at line 93 — return value discarded. REQ-SV2-1400 (anti-pattern section) should prevent this in the next run.

### F-6: PI-009 Method Resolution + Orphaned Functions

**Severity:** Low (warning, functional)
**File:** `loadgenerator/locustfile.py`

`self.index()` at line 46 — `index` is a module-level function, not a method of `UserBehavior`. Locust TaskSet calls module functions via `tasks` dict, not `self`. The `on_start` method should use `index(self)` or `self.client.get("/")`.

`empty_cart` (line 61) and `logout` (line 64) are defined after the class but never referenced in `tasks` dict — orphaned.

---

## 3. REQ-SIG-200/201 Validation

The service communication graph threading shipped in commit 6c757ef. Run-055 results:

| File | Prior Proto Import Pattern | Run-055 | Verdict |
|---|---|---|---|
| PI-003 email_server.py | `import demo_pb2` (sometimes wrong in epochs 1-3) | `import demo_pb2` | **FIXED** |
| PI-006 recommendation_server.py | `import demo_pb2` (sometimes `product_catalog_stub`) | `import demo_pb2` | **FIXED** |
| PI-004 email_client.py | Various wrong proto names (70% of runs) | `from email_service_pb2 import ...` | **NOT FIXED** |
| PI-007 client.py | Various wrong proto names | `from recommendationservicestub import ...` | **NOT FIXED** |

**Assessment:** REQ-SIG-200/201 fixes proto imports for files whose target path matches a service communication graph key (e.g., `emailservice/email_server.py` → `emailservice` service). Test client files don't benefit because `_collect_dependency_imports()` matches by target file directory, not by what the file imports from.

---

## 4. Defect Classes Eliminated vs Persisting

| Defect Class | Retroactive Frequency | Run-055 Status |
|---|---|---|
| Hallucinated module paths | 25% (extinct by epoch 3) | **Eliminated** |
| Bare locustfile imports | 40% (extinct by epoch 3) | **Eliminated** |
| Fake pip deps in requirements.in | 25% | **Eliminated** |
| Fabricated SHA256 digests | 20% | **Eliminated** |
| Wrong proto module name (servers) | 70% | **Fixed by REQ-SIG-200/201** |
| Wrong proto module name (clients) | 70% | **Persists** (F-1, F-2) |
| Copy-paste service identity | 15% | **Persists** (F-4) |
| Discarded returns | 50% | **Reduced to 1 instance** (F-5) |
| Method resolution errors | 15% | **Persists** (F-6) |
| Cross-scope duplicates | 40% | **Eliminated** |

---

## 5. Cross-References

| Document | Relationship |
|---|---|
| [SEMANTIC_VALIDATION_RETROACTIVE_ANALYSIS.md](SEMANTIC_VALIDATION_RETROACTIVE_ANALYSIS.md) | Historical baseline (20 runs) for trend comparison |
| [SEMANTIC_VALIDATION_V2_REQUIREMENTS.md](SEMANTIC_VALIDATION_V2_REQUIREMENTS.md) | REQ-SV2-1300/1400 (import conventions, anti-patterns) — merged, not yet active |
| [REQ_CONTRACTS_CONSUMER_GAPS.md](REQ_CONTRACTS_CONSUMER_GAPS.md) | GAP-SDK-003 closure (binding injection removed) |
| [KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md](KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md) | Phase A-E validation framework |
| `forward_manifest_validator.py` | L1-L6 implementation (false negative root cause) |
| `package_aliases.py` | L1 FP root cause (missing aliases) |
