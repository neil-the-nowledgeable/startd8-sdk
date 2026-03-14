# Hitsuzen Design Principle

Purpose: establish a cross-cutting design principle for the startd8-sdk pipeline — when an output is fully determined by inputs already available in the pipeline, derive it deterministically instead of generating it with an LLM.

This document is intentionally living guidance. Update it as new derivation opportunities are identified.

---

## The Principle

**Hitsuzen** (必然) — "inevitable; necessary consequence." In Japanese philosophy, hitsuzen describes outcomes that are the natural, unavoidable result of prior conditions — not random, not chosen, but determined by what came before.

Applied to the pipeline: **when the correct output is fully determined by data already flowing through the pipeline, compute it rather than generate it. LLM generation adds cost, latency, non-determinism, and failure modes to something that has exactly one right answer.**

---

## Why This Matters

The pipeline routes all code generation tasks through LLMs by default. This is correct for creative work (implementing business logic, writing algorithms) where the output genuinely requires judgment. But some tasks *look* like generation when they are actually derivation:

| Task | Looks Like | Actually Is |
|------|-----------|-------------|
| `requirements.in` | "Generate the dependency list" | Extract imports from sibling .py files → map to PyPI names |
| `__init__.py` re-exports | "Generate the package init" | Enumerate public symbols from sibling modules |
| `.gitignore` | "Generate ignore patterns" | Union of language-specific templates + project-specific paths |
| `Dockerfile` `COPY` lines | "Generate the copy directives" | List files in the build context |
| Type stub `.pyi` files | "Generate type stubs" | Extract signatures from the `.py` file via AST |

Each of these has a single correct answer derivable from data the pipeline already possesses. Sending them to an LLM introduces:

1. **Non-determinism** — the LLM may produce different output on each run
2. **Hallucination** — the LLM may invent dependencies, re-exports, or patterns that don't exist
3. **Cost** — API tokens spent on a problem that requires zero inference
4. **Failure modes** — size regression guards, truncation detectors, and review loops designed for code generation produce false positives on non-code outputs (the `requirements.in` false positive that motivated this principle)
5. **Latency** — seconds of API round-trip for something computable in milliseconds

---

## The Test

Before routing a pipeline task to an LLM, ask:

> **"Is the correct output fully determined by data already in the pipeline? If I had a perfect lookup table of all inputs, would there be exactly one valid output?"**

If yes → **derive deterministically** (AST parsing, file enumeration, alias mapping, template expansion).

If no → **generate with LLM** (business logic, algorithm implementation, architectural decisions).

### Decision Framework

```
Pipeline task to produce a file
        │
        ▼
Is the output determined by
existing pipeline data?
        │
   ┌────┴────┐
   Yes       No
   │         │
   ▼         ▼
Can it be   LLM generation
computed     is appropriate
via AST,
lookup, or
enumeration?
   │
   ┌────┴────┐
   Yes       No
   │         │
   ▼         ▼
DERIVE    LLM with
(zero      structured
 cost)     constraints
```

---

## Relationship to Other Principles

| Principle | Focus | Hitsuzen Interaction |
|-----------|-------|---------------------|
| **Mottainai** | Don't discard artifacts (within a run) | Mottainai says reuse what was produced; Hitsuzen says some artifacts don't need "producing" at all — they're derivable from what already exists |
| **Ichigo Ichie** | Every improvement must help first-run projects | Hitsuzen derivations are project-agnostic by nature — AST import extraction works on any Python project |
| **Kaizen** | Learn from every run | Kaizen observations identify *which* tasks are derivable; Hitsuzen provides the framework for acting on that knowledge |
| **Keiyaku** | Typed contracts at agent boundaries | Derivation inputs and outputs should be typed contracts, not ad-hoc string manipulation |

### The Mottainai–Hitsuzen Distinction

Mottainai says: "The imports are already in the manifest — don't ask the LLM to re-derive them."

Hitsuzen says: "The `requirements.in` file *is* the imports — don't ask the LLM to generate it at all."

Mottainai prevents waste of existing artifacts. Hitsuzen prevents generation of artifacts that are computable.

---

## Founding Example: `requirements.in`

**Observation (run-047, run-048):** The pipeline sent `requirements.in` generation to Claude Haiku as a bypass file. Haiku correctly produced a 6-line file, but the size regression detector compared it against the 233-line `requirements.txt` (a sibling file loaded for import context) and flagged it as 97% truncation. Three iterations of the same correct output → task failed.

**Root cause:** The task was misclassified as "generation" when it was actually "derivation." The correct `requirements.in` content is fully determined by the imports in the sibling Python files.

**Hitsuzen fix:** `requirements_generator.py` scans generated Python files, extracts third-party imports via AST, maps to PyPI package names via the alias map, and writes `requirements.in` directly. Zero LLM calls, zero false positives, deterministic output.

**Impact:**
- Cost: $0.00 (was ~$0.03/attempt × 3 attempts = $0.09 per feature)
- Latency: <10ms (was ~15s for 3 LLM round-trips)
- Reliability: 100% (was 0% — failed on every run due to size regression)
- Correctness: Deterministic (was non-deterministic — LLM might include/omit packages)

---

## Candidate Derivations (Backlog)

Tasks observed in production runs that may be Hitsuzen candidates. Each needs validation that the output is *fully* determined before implementation.

| Task Type | Input Data | Derivation Method | Confidence | Status |
|-----------|-----------|-------------------|------------|--------|
| `requirements.in` | Sibling .py imports | AST + alias map | High | **Implemented** |
| `__init__.py` re-exports | Sibling module public symbols | AST `__all__` + function/class names | High | Candidate |
| `.dockerignore` | Project structure + `.gitignore` | File enumeration + union | Medium | Candidate |
| `py.typed` marker | Package exists | Empty file creation | High | Candidate |
| `conftest.py` fixtures | Test file imports | AST fixture extraction | Medium | Candidate |
| `setup.cfg` / `pyproject.toml` deps | `requirements.in` content | Format conversion | High | Candidate |

### Validation Checklist for Candidates

Before implementing a Hitsuzen derivation:

1. **Enumerate the inputs** — what pipeline data does the output depend on?
2. **Prove determinism** — given identical inputs, is the output always identical?
3. **Check edge cases** — are there configurations where the output requires judgment? (If yes, it's not Hitsuzen)
4. **Verify Ichigo Ichie** — does the derivation work on projects the pipeline has never seen?
5. **Measure** — what was the LLM cost, failure rate, and latency for this task type?

---

## Implementation Pattern

```python
# Hitsuzen derivation template
def derive_<artifact>(
    source_files: dict[str, str],      # Existing pipeline data
    manifest: ForwardManifest,          # Structural metadata
    extra: list[str] | None = None,     # Optional overrides
) -> str | None:
    """Deterministically derive <artifact> from pipeline data.

    Returns content string, or None if insufficient data (fall through
    to LLM generation).
    """
    # 1. Extract relevant data via AST/parsing (not string matching)
    # 2. Map through lookup tables (not LLM inference)
    # 3. Format output (not prompt engineering)
    # 4. Return None if data is insufficient — don't guess
```

Key properties:
- **Returns `None` on insufficient data** — falls through to LLM gracefully
- **Uses AST/parsing** — not regex or string matching
- **Uses lookup tables** — not LLM inference
- **Is testable** — deterministic input → deterministic output

---

## Maintenance

When a pipeline task fails or produces incorrect output, tag the investigation:

- **[HITSUZEN]** — Output was derivable; implement deterministic path
- **[GENERATION]** — Output genuinely requires LLM judgment; improve prompt/model
- **[HYBRID]** — Partial derivation possible (e.g., derive structure, generate content)

Only **[HITSUZEN]** items should bypass LLM generation entirely. **[HYBRID]** items may benefit from deterministic scaffolding with LLM fill-in.
