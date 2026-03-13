# Ichigo Ichie Design Principle

Purpose: establish a cross-cutting design principle for the startd8-sdk pipeline — every
pipeline run should be treated as if it were the first and only encounter with this
project. Optimizations must improve first-run quality, not just repeat-run familiarity.

This document is intentionally living guidance. Update it as new examples arise.

---

## The Principle

**Ichigo Ichie** (一期一会) — "one time, one meeting." In Japanese tea ceremony,
every gathering is treated as a once-in-a-lifetime encounter. The host prepares
with full care regardless of whether the guest has visited before, because this
exact meeting will never happen again.

Applied to the pipeline: **every improvement to code generation, repair, review,
or validation must produce better outcomes for a project the pipeline has never
seen before. Improvements that only benefit re-runs of a previously seen project
are calibration artifacts, not pipeline improvements.**

---

## Why This Matters

The SDK's calibration workflow runs the same project (online-boutique-demo) through
the pipeline repeatedly to measure improvement. This creates a natural temptation:

1. **Observation bias** — Quality issues are observed in calibration outputs
   (e.g., `import jsonlogger` is wrong in the emailservice logger)
2. **Targeted fix** — A hardcoded rule is added to catch that specific issue
   (e.g., a denylist blocking `jsonlogger`)
3. **Measurement confirms** — The next calibration run scores higher
4. **False conclusion** — The pipeline is "better"

But for a *new* project the pipeline has never seen, the denylist entry is
meaningless at best and a false positive at worst. The pipeline didn't get better —
it memorized one project's failure modes.

---

## Relationship to Other Principles

| Principle | Focus | Ichigo Ichie Interaction |
|-----------|-------|------------------------|
| **Mottainai** | Don't discard artifacts (within a run) | Mottainai forwarding benefits every run equally — no calibration bias |
| **Kaizen** | Don't discard lessons (across runs) | Kaizen observations must be generalized before adoption. "logger.py used wrong import" is a calibration observation; "LLMs hallucinate PyPI-name vs import-name mappings" is a generalizable lesson |
| **Warm Up** | Don't discard context (across toolchain transitions) | Context from prior runs is valid reuse; hardcoded corrections from prior runs are not |

### The Kaizen–Ichigo Ichie Tension

Kaizen says learn from every run. Ichigo Ichie says don't over-fit to observed runs.
The resolution: **generalize before you adopt.**

| Calibration Observation | Calibration Fix (violates Ichigo Ichie) | Generalized Fix (honors both) |
|------------------------|----------------------------------------|------------------------------|
| `import jsonlogger` is wrong | Add `jsonlogger` to denylist | Build bidirectional PyPI↔import alias map; detect mismatches via project deps |
| gRPC code has 3x error density | Add hardcoded gRPC import templates | Derive imports from sibling files in the same directory |
| All 4 services got identical deps | Filter deps for these specific services | Scope deps to co-located Python files (project-agnostic) |
| `google.cloud.vectordb` doesn't exist | Add to hallucination denylist | Validate imports against project's declared dependencies |
| Registry has 1.2% hit rate | Optimize for re-run hit rate | Optimize for within-run element sharing (benefits first run) |

---

## The Test

Before adopting any quality improvement, ask:

> **"If the next project the pipeline processes is something it has never seen —
> different language, different framework, different domain — does this change
> still help?"**

If the answer is "only if they happen to use gRPC" or "only if the LLM happens
to hallucinate `jsonlogger`," the change fails the Ichigo Ichie test.

### Decision Framework

```
Observation from calibration run
        │
        ▼
Is the root cause project-specific?
        │
   ┌────┴────┐
   Yes       No
   │         │
   ▼         ▼
STOP —    Can the fix be stated without
do not     referencing the calibration project?
hardcode        │
           ┌────┴────┐
           Yes       No
           │         │
           ▼         ▼
        ADOPT     GENERALIZE first,
                  then adopt
```

---

## Flagged Items in QUALITY_IMPROVEMENT_PLAN.md

The following items from the Run-016 quality improvement plan were reviewed
against this principle:

### Passes Ichigo Ichie

| Item | Why |
|------|-----|
| L1+ Deterministic import audit | AST-based; works on any Python code regardless of project |
| L2+ Two-tier stub detection | Uses pipeline-intrinsic `STUB_SENTINEL`; not project-specific |
| L3+ Dependency scoping | Scopes to co-located files; works for any multi-service project |
| L4+ Structured constraint emission | Emits from spec builder context fields; general-purpose |
| L5+ Sibling-file import derivation | Reads from actual project files; self-adapting |
| L6 Cloud fallback → registry backfill | Benefits within-run element sharing for any project |
| L7 Repair marker cleanup | Cosmetic cleanup; benefits all output |
| DFA pre-fill wiring | Benefits any project with repeated elements within a run |
| Semantic verification (config flag) | General-purpose validation |
| Simple-to-trivial decomposer (config flag) | General-purpose routing improvement |
| Bidirectional alias map (`package_aliases.py`) | Common PyPI↔import mappings; universally useful |

### Violates Ichigo Ichie (Must Be Reworked or Dropped)

| Item | Violation | Remediation |
|------|-----------|-------------|
| **Refinement 3: Known-bad import denylist** | Entries (`jsonlogger`, `google.cloud.vectordb`) are calibration-specific observations. `jsonlogger` is a valid import in some package versions. | **Drop the hardcoded denylist.** Instead, validate imports against the project's declared `runtime_dependencies` using the `package_aliases.py` alias map. If the code imports `jsonlogger` but `pythonjsonlogger` (via `python-json-logger`) is in deps, flag the mismatch. If `jsonlogger` IS in deps, allow it. |
| **Original L5: Hardcoded framework templates** | gRPC/Locust/OTel templates are the calibration project's stack. | **Already remediated by L5+** (sibling-file derivation). Drop `FRAMEWORK_IMPORT_DEFAULTS` fallback — if no sibling files exist, the import audit pass (L1+) handles it. |
| **Validation targets: registry hit rate** | "1.2% → 5-10% → 10-20%" assumes repeat-run measurement. | **Reframe metric** as "within-run element reuse rate" (elements shared across features in a single run). This is meaningful for first-run projects. |

---

## Examples

### Good: Bidirectional Alias Map

The `package_aliases.py` map (`grpcio → grpc`, `pillow → PIL`, etc.) was
*observed* in calibration but captures a *universal truth*: PyPI package names
often differ from Python import names. Any project using these packages benefits.
The map is extensible and the entries are verifiable facts, not project-specific
heuristics.

### Bad: Hallucination Denylist

A denylist of "imports the LLM got wrong in run-016" is the pipeline memorizing
one project's failure modes. `google.cloud.vectordb` doesn't exist today but
could tomorrow. `jsonlogger` is a legitimate import for some versions of
`python-json-logger`. The denylist grows from calibration but applies globally,
creating an ever-expanding surface for false positives.

### Good (Generalized from Bad): Dependency-Aware Import Validation

Instead of "block `jsonlogger`," validate that every import corresponds to
either (a) a declared runtime dependency (via alias map), (b) the standard
library, or (c) a project-local module. This catches `jsonlogger` when
`python-json-logger` is in deps (because the alias map says the correct import
is `pythonjsonlogger`), but also catches novel hallucinations in any future
project — without a growing denylist.

---

## Maintenance

When writing Kaizen investigation reports, explicitly tag findings as:

- **[GENERAL]** — Root cause is project-agnostic (e.g., "LLMs omit imports")
- **[CALIBRATION]** — Root cause is project-specific (e.g., "wrong import for this package")
- **[GENERALIZABLE]** — Calibration observation with a general-purpose fix available

Only **[GENERAL]** and **[GENERALIZABLE]** (after generalization) items should
proceed to implementation.
