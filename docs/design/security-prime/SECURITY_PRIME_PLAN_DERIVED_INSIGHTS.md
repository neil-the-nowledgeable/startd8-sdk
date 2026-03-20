# Security Prime — Plan-Derived Insights and Requirements Refinement

> **Date:** 2026-03-19
> **Source:** Implementation planning for SECURITY_PRIME_REQUIREMENTS.md (v0.2.0)
> **Purpose:** Insights that emerged from planning the implementation but were not visible from the requirements alone. Each insight maps to a concrete requirements improvement.

---

## Overview

Creating the implementation plan forced collision between the requirements' ideal architecture and the codebase's actual integration surfaces. This produced 7 categories of insight, 4 quick wins that can ship before Phase 1 begins, and 12 specific requirements improvements.

---

## 1. Quick Wins — Immediate Value Before Phase 1

The implementation plan revealed that several high-value deliverables require **zero new modules** — they are surgical improvements to existing code that directly fix runs 78–79.

### QW-1: Parameterization-Aware Suppression in Existing C# Checks

**Insight:** SP-T0-003 (recognize parameterized queries) can be implemented as a ~30-line enhancement to `csharp_semantic_checks.py:_check_sql_injection_risk()` WITHOUT the new `security/` module. This fixes the Spanner false positive TODAY.

**Change:** After detecting a SQL construction site, scan the next 5 lines for `Parameters.Add`, `Parameters.AddWithValue`, `SpannerParameterCollection`. If found, suppress the finding.

**Requirements impact:** Add new requirement:

> **SP-T0-003a (Quick Win):** Parameterization-aware suppression SHALL be implemented as an enhancement to the existing language-specific semantic checks (`csharp_semantic_checks.py`, `java_semantic_checks.py`) BEFORE the cross-language `security/` module is built. This provides immediate value and serves as the regression test baseline for the cross-language implementation.

### QW-2: Multiline SQL Tracking in Existing C# Checks

**Insight:** SP-T0-002 (multiline SQL detection) can be implemented as a ~40-line state machine addition to `_check_sql_injection_risk()`. Track whether we're inside a SQL construction site across consecutive lines.

**Requirements impact:** Same pattern as QW-1 — add quick-win variant to SP-T0-002.

### QW-3: `security_sensitive` Flag on TaskComplexitySignals

**Insight:** Adding `security_sensitive: bool = False` to `TaskComplexitySignals` (1 line) and a MODERATE floor in `classify_tier()` (~5 lines) delivers SP-PL-022 immediately. This is a ~10 line change.

**Requirements impact:** SP-PL-022 should be explicitly callable as a standalone quick win independent of the full Phase 6 pipeline integration.

### QW-4: `security_allowlist.yaml` File Convention

**Insight:** The allowlist (SP-FP-003) is a zero-code feature — it's just a file convention. Operators can create `security_allowlist.yaml` today and the Phase 1 implementation reads it. Define the schema now so teams can start building their allowlists.

**Requirements impact:** Add schema specification to SP-FP-003. The allowlist is immediately useful even with just the existing `_check_sql_injection_risk()` check.

---

## 2. Priority Level Contradiction (P0 vs P1)

### The Problem

SP-INJ-004 says security guidance is **P1 priority** ("below P0 task description but above P2 exemplar code").

SP-PL-031 says the draft prompt security constraint is **P0 priority** ("never trimmed by budget enforcement").

These contradict each other. The implementation plan exposed this because `budget.py` has exactly 4 priority levels (P0–P3) and each section must be assigned one.

### The Resolution

These are **two different things** that the requirements conflate:

1. **P0 — Security Constraint** (hard requirement, ~50 tokens): `"MUST use parameterized queries for all external inputs. NEVER use string interpolation in SQL strings."` — This is the non-negotiable constraint. It should NEVER be trimmed. It's P0 alongside the task description.

2. **P1 — Security Guidance** (helpful context, ~200–400 tokens): The secure/insecure code examples, CWE references, library-specific API patterns. This is valuable but trimmable under extreme budget pressure. P1 alongside Kaizen hints and forward contracts.

**Requirements impact:** Split SP-INJ-004 into two requirements:

> **SP-INJ-004a:** The hard security constraint ("MUST use parameterized queries...") SHALL be P0 priority — never trimmed by budget enforcement. Budget: ~200 characters (~50 tokens).
>
> **SP-INJ-004b:** Security guidance templates (secure/insecure examples, CWE references, library-specific patterns) SHALL be P1 priority — trimmed only under extreme budget pressure. Budget: ~800–1600 characters (~200–400 tokens).

---

## 3. Standalone Mode Gap

### The Problem

The Anzen pipeline integration (§14) assumes the full Capability Delivery Pipeline: CREATE → EXPORT → PLAN-INGESTION → CONTRACTOR. But `prime_contractor.py` supports `MODE_STANDALONE` where tasks are run without upstream pipeline stages. Many development and testing runs use standalone mode.

The requirements are silent on standalone mode. A standalone run would have no `.contextcore.yaml`, no `onboarding-metadata.json`, no security contract — and therefore no security validation.

### The Resolution

Security Prime must work in both modes, with graceful degradation:

**Requirements impact:** Add new requirement section:

> **REQ-SP-1060: Standalone Mode Support**
>
> | ID | Requirement |
> |----|-------------|
> | SP-SM-001 | In standalone mode (no upstream pipeline), Security Prime SHALL auto-detect security surfaces from task content: scan `target_files` for database imports, scan task description for security-relevant keywords, use `LanguageProfile.framework_imports` for library detection. |
> | SP-SM-002 | In standalone mode, the security contract SHALL be derived on-the-fly from auto-detection rather than loaded from `onboarding-metadata.json`. This produces a lower-fidelity contract but ensures security validation is never silently skipped. |
> | SP-SM-003 | The Anzen gate SHALL run in both standalone and pipeline modes. In standalone mode, the gate uses the auto-derived contract. In pipeline mode, it uses the full pipeline-derived contract. |
> | SP-SM-004 | Standalone mode SHALL emit an INFO log: "Running in standalone mode — security contract auto-derived from task content. For higher-fidelity security analysis, use pipeline mode with spec.security in .contextcore.yaml." |

---

## 4. Integration Engine Insertion Point

### The Problem

The requirements specify the Anzen gate runs "after code generation but before EXPORT" (SP-PL-040) but don't specify WHERE in `integration_engine.py`'s validation pipeline. The integration engine has a specific order: pre-validate → merge → post-merge cleanup → checkpoints → repair → semantic checks → advisory downgrade → final gate emission.

Getting this wrong means either:
- Gate runs too early (before semantic repair, so repaired code isn't re-checked)
- Gate runs too late (after advisory downgrade, so security findings get downgraded)

### The Resolution

The Anzen gate must run AFTER semantic checks and AFTER any repair attempts, but BEFORE advisory downgrade. This ensures:
1. Repaired code is evaluated (not just the initial broken version)
2. Security findings are NOT downgraded to advisory

**Requirements impact:** Add specificity to SP-PL-040:

> **SP-PL-040a:** In the `IntegrationEngine.integrate()` pipeline, the Anzen gate SHALL execute AFTER `_run_semantic_checks()` and `_attempt_semantic_repair()` but BEFORE advisory downgrade logic. Security findings from the gate SHALL NOT be subject to advisory downgrade — injection and credential findings are always hard failures regardless of the advisory/blocking configuration.
>
> **SP-PL-040b:** The Anzen gate SHALL receive the post-repair source code (not the pre-repair version). If semantic repair fixes a security issue (e.g., removes a bare `except: pass` that was swallowing a credential validation error), the gate evaluates the repaired code.

---

## 5. Security Score ↔ Quality Gate Interaction

### The Problem

The existing quality gate in `prime_contractor.py` checks `quality_score >= _MIN_QUALITY_SCORE` (threshold: 60). The requirements create an independent `security_score` (SP-SCR-006) but don't specify how it interacts with the existing gate.

Questions the requirements don't answer:
- Does security score have its own threshold?
- Can a file with `quality_score=90` and `security_score=0.3` pass?
- Is the gate additive, parallel, or hierarchical?

### The Resolution

**Parallel gates with independent thresholds:**

**Requirements impact:** Add new requirement:

> **REQ-SP-605: Security Score Quality Gate**
>
> | ID | Requirement |
> |----|-------------|
> | SP-SCR-030 | The security score SHALL be evaluated as a PARALLEL quality gate alongside the existing `quality_score` gate. Both must pass for the file to be accepted. |
> | SP-SCR-031 | The security score threshold SHALL be configurable via `SecurityRoutingConfig.min_security_score`, defaulting to `0.70`. |
> | SP-SCR-032 | A file that passes the quality gate (`quality_score >= 60`) but fails the security gate (`security_score < 0.70`) SHALL be reported as `QUALITY_PASS_SECURITY_FAIL` — this distinguishes "code that works but is insecure" from "code that is broken." |
> | SP-SCR-033 | In `warn` enforcement mode, a security gate failure produces a warning but does not block. In `block` mode, it blocks integration. Default: `block` for INJECTION and SECRETS domains, `warn` for all others. |

---

## 6. Scoring Formula Saturation Problem

### The Problem

SP-SCR-003 computes: `1.0 - sum(severity_penalty[f.severity] for f in confirmed_findings)`, clamped to [0.0, 1.0].

With severity penalties `info=0.02, warning=0.05, error=0.15, critical=0.30`:
- A file with 20 `info` findings scores 0.60 (20 × 0.02 = 0.40 penalty)
- A file with 7 `warning` findings scores 0.65 (7 × 0.05 = 0.35 penalty)
- A file with 1 `critical` + 1 `error` scores 0.55

The linear sum doesn't distinguish between "many minor issues" and "one critical vulnerability." Twenty informational notes about missing sealed classes shouldn't score worse than one SQL injection.

### The Resolution

**Use max-severity-weighted scoring with diminishing returns:**

**Requirements impact:** Revise SP-SCR-003:

> **SP-SCR-003 (revised):** The security score SHALL be computed as:
> ```
> worst_penalty = max(severity_penalty[f.severity] for f in confirmed_findings)
> additional_penalty = sum(severity_penalty[f.severity] for f in confirmed_findings) - worst_penalty
> diminished_additional = additional_penalty * 0.3  # diminishing returns
> security_score = max(0.0, 1.0 - worst_penalty - diminished_additional)
> ```
> This ensures a single critical finding dominates the score (0.70), while 20 info findings produce only 0.02 + (19 × 0.02 × 0.3) = 0.134 penalty (score 0.866). The worst vulnerability drives the score; additional findings contribute at 30% rate.

---

## 7. Existing `security.py` Module Collision

### The Problem

The implementation plan creates `src/startd8/security/` as a new package. But `src/startd8/security.py` ALREADY EXISTS — it contains `sanitize_path()`, `validate_api_key_format()`, `mask_api_key()`, `KeyEncryption`, `validate_api_endpoint()`.

You cannot have both `security.py` (file) and `security/` (package) at the same path in Python. One must be renamed.

### The Resolution

**Rename the existing module to `security_utils.py`** — it contains utility functions, not the security validation framework. Update all import sites (there are ~8 files importing from `security.py`).

**Requirements impact:** Add new requirement:

> **REQ-SP-050: Module Namespace**
>
> | ID | Requirement |
> |----|-------------|
> | SP-NS-001 | The existing `src/startd8/security.py` module (containing `sanitize_path`, `validate_api_key_format`, `mask_api_key`, `KeyEncryption`, `validate_api_endpoint`) SHALL be renamed to `src/startd8/security_utils.py` to free the `security` namespace for the Security Prime package. |
> | SP-NS-002 | A compatibility re-export SHALL be maintained: `security.py` becomes `security/__init__.py` which re-exports all symbols from `security_utils.py` for backward compatibility, following the `context_seed_handlers.py` compat wrapper pattern documented in CLAUDE.md. |
> | SP-NS-003 | All existing `from startd8.security import X` import sites (~8 files) SHALL continue working after the migration via the re-export in `security/__init__.py`. |

---

## 8. Cost Model Transparency

### The Problem

The requirements specify token budgets for each tier but don't translate to dollar costs. Operators making routing decisions need cost visibility.

### The Resolution

**Requirements impact:** Add cost estimates to §7:

> **REQ-SP-330: Cost Transparency**
>
> | Tier | Input Tokens | Output Tokens | Est. Cost/File (Sonnet) | Est. Cost/File (Opus) | Typical Trigger |
> |------|-------------|---------------|------------------------|-----------------------|-----------------|
> | 0 | 0 | 0 | $0.000 | $0.000 | All files |
> | 1 | 4,096 | 1,024 | ~$0.02 | ~$0.08 | MEDIUM risk |
> | 2 | 16,384 | 2,048 | ~$0.06 | ~$0.30 | HIGH risk |
> | 3 | 65,536 | 8,192 | ~$0.25 | ~$1.20 | CRITICAL / `--security-review deep` |
>
> For a 14-file microservice (Online Boutique cartservice scale):
> - Tier 0 only: $0.00 total (deterministic)
> - Tier 0 + Tier 1 on 5 MEDIUM files: ~$0.10 (Sonnet)
> - Full Tier 3 on all files: ~$3.50 (Sonnet) / ~$16.80 (Opus)

---

## 9. Improved Tier 0 Reduces Tier 2 Adjudication Need

### The Problem

SP-FP-001 specifies that Tier 2 adjudicates Tier 0 false positives. But the two-pass parameterization detection (SP-T0-004) already eliminates the class of false positives that motivated Tier 2 adjudication (the Spanner case). If Tier 0 checks for parameterization before flagging, there's no false positive for Tier 2 to adjudicate.

This matters because Tier 2 costs ~$0.06–$0.30 per file. If better Tier 0 eliminates the need for Tier 2 adjudication on 80% of files, that's significant cost savings.

### The Resolution

**Requirements impact:** Add:

> **SP-FP-001a:** Tier 2 adjudication is a FALLBACK for Tier 0 false positives that survive context-aware suppression (SP-FP-010). As Tier 0 checks improve (particularly the two-pass parameterization detection in SP-T0-004), the volume of findings requiring Tier 2 adjudication SHOULD decline. Routing decisions (SP-RT-001) SHOULD factor in the Tier 0 false positive rate — if Tier 0 FP rate is <5% for a given domain, Tier 2 adjudication can be skipped for that domain, saving ~$0.06–$0.30 per file.

---

## 10. Reference Deviation Policy

### The Problem

The AlloyDB case is explicitly about the LLM reproducing a vulnerability FROM THE REFERENCE IMPLEMENTATION. The requirements tell the LLM to deviate ("use parameterized queries instead") but don't address the tension: the task description says "match the reference" and the security constraint says "don't match the reference."

Without explicit guidance on this tension, the LLM may choose either direction unpredictably.

### The Resolution

**Requirements impact:** Add to §8 (Pre-Generation Security Injection):

> **REQ-SP-420: Reference Deviation Policy**
>
> | ID | Requirement |
> |----|-------------|
> | SP-DEV-001 | When a security constraint conflicts with the reference implementation, the security constraint WINS. The prompt SHALL explicitly state: "If the reference implementation uses an insecure pattern (e.g., string interpolation in SQL), you MUST use the secure alternative instead. Matching the reference is NOT required when it conflicts with security requirements." |
> | SP-DEV-002 | The reference deviation SHALL be documented in a code comment: `// SECURITY: Deviates from reference — uses parameterized queries instead of string interpolation (CWE-89)`. This makes the intentional deviation visible and auditable. |
> | SP-DEV-003 | Reference deviations SHALL be tracked in the post-mortem: count of security-motivated deviations, which reference patterns were overridden, and which secure alternatives were used. This data feeds the Kaizen loop — if a reference deviation causes functional regressions, the hint should be refined. |

---

## 11. Existing Semantic Check Migration Path

### The Problem

The requirements create a new `security/` module with cross-language SQL injection detection (SP-T0-001) but don't specify what happens to the EXISTING security-relevant checks in `csharp_semantic_checks.py`, `java_semantic_checks.py`, etc.

The implementation plan shows thin wrappers are needed, but the migration path isn't specified. Without it, we risk:
- Duplicate detection (both old and new checks flag the same issue)
- Regression (new module misses a pattern the old check caught)
- Test confusion (which module's tests are authoritative?)

### The Resolution

**Requirements impact:** Add:

> **REQ-SP-060: Semantic Check Migration**
>
> | ID | Requirement |
> |----|-------------|
> | SP-MIG-001 | Existing security-relevant checks in language-specific semantic check modules (`_check_sql_injection_risk` in C#, SQL-related checks in Java) SHALL be migrated to `security/checks/injection.py` over two phases: (a) Quick wins (QW-1, QW-2) enhance the existing checks in-place, (b) Phase 1 creates the cross-language module and the existing checks become thin wrappers that delegate to it. |
> | SP-MIG-002 | During the migration, the thin wrapper SHALL produce IDENTICAL results to the original check for all existing test cases. The cross-language module MAY produce ADDITIONAL findings (new patterns) but SHALL NOT miss any finding the original check caught. |
> | SP-MIG-003 | Existing test suites (`test_csharp_semantic_checks.py`, `test_csharp_disk_validators.py`) SHALL continue passing unchanged after migration. New security-specific tests go in `tests/unit/security/`. |
> | SP-MIG-004 | The wrapper SHALL be removed (not preserved indefinitely) once the cross-language module is stable and all downstream call sites have migrated to `security.checks.run_tier0_checks()`. Target: end of Phase 2. |

---

## 12. Domain Registration Mechanism

### The Problem

SP-TX-001 says `SecurityDomain` is "extensible via registration for future domains" but doesn't specify the registration mechanism. The plan exposed this because it mirrors the `LanguageRegistry` pattern — but needs explicit specification to avoid the static-enum-vs-dynamic-registry tension.

### The Resolution

**Requirements impact:** Revise SP-TX-001:

> **SP-TX-001 (revised):** The `SecurityDomain` enum SHALL include the 10 core domains. Extension SHALL use the same entry-point pattern as `LanguageRegistry`: third-party packages register new domains via `[project.entry-points."startd8.security_domains"]` in their `pyproject.toml`. Each registered domain provides: `domain_id`, `display_name`, `owasp_categories`, `cwe_ids`, `default_enforcement`, `applicable_languages`, and a `check_function(source, language_id, file_path) → List[SecurityFinding]`.

---

## Summary: Requirements Changes Needed

| # | Type | Section | Change | Impact |
|---|------|---------|--------|--------|
| 1 | **Quick Win** | New §0 | Add Phase 0 (quick wins before new module): QW-1 through QW-4 | Immediate fix for runs 78–79 |
| 2 | **Contradiction Fix** | §8, SP-INJ-004 | Split into SP-INJ-004a (P0 hard constraint) and SP-INJ-004b (P1 guidance) | Budget system correctness |
| 3 | **Gap Fill** | New §14.6 | Add REQ-SP-1060 standalone mode support (SP-SM-001–004) | Coverage for non-pipeline runs |
| 4 | **Precision** | §14.4, SP-PL-040 | Add SP-PL-040a/040b specifying integration engine insertion point | Correct pipeline ordering |
| 5 | **Gap Fill** | New §10.3 | Add REQ-SP-605 security score quality gate (SP-SCR-030–033) | Quality gate interaction |
| 6 | **Formula Fix** | §10, SP-SCR-003 | Revise to max-severity-weighted with diminishing returns | Score discrimination |
| 7 | **Collision Fix** | New §3.2 | Add REQ-SP-050 module namespace (SP-NS-001–003) | Python import correctness |
| 8 | **Transparency** | §7 | Add REQ-SP-330 cost model per tier | Operator decision-making |
| 9 | **Optimization** | §11, SP-FP-001 | Add SP-FP-001a improved T0 reduces T2 need | Cost optimization |
| 10 | **Design Gap** | New §8.3 | Add REQ-SP-420 reference deviation policy (SP-DEV-001–003) | LLM prompt coherence |
| 11 | **Migration Path** | New §3.3 | Add REQ-SP-060 semantic check migration (SP-MIG-001–004) | Backward compatibility |
| 12 | **Specificity** | §5, SP-TX-001 | Revise to specify entry-point registration mechanism | Extensibility mechanism |
