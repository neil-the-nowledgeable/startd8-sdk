# Dockerfile Skeleton Assembly — Convergent Review Agent Guide

**Purpose:** Custom review instructions for AI agents evaluating the Dockerfile Skeleton Assembly requirements, implementation plan, and supporting research. Derived from the [Convergent Review Protocol (CRP)](../arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md) with domain-specific adaptations.

**Documents under review:**

| Document | Role | Path |
|----------|------|------|
| Requirements | Primary target (requirements) | `docs/design/micro-prime/REQ-MP-3xx_DOCKERFILE_SKELETON_ASSEMBLY.md` |
| Implementation Plan | Primary target (plan) | `docs/design/micro-prime/DOCKERFILE_SKELETON_ASSEMBLY_IMPLEMENTATION_PLAN.md` |
| Best Practices Research | Reference (read-only) | `docs/design/scaffold/docker-file-assembly-via-python.md` |
| Polyglot Template Registry | Parent requirements (read-only) | `docs/design/micro-prime/REQ-MP-3xx_POLYGLOT_TEMPLATE_REGISTRY.md` |
| Python File Assembly | Pattern reference (read-only) | `docs/design/scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md` |

**Mode:** Dual-document (requirements + plan) per CRP Phase 3-DD.

---

## Domain-Specific Review Configuration

### Review Areas (adapted from CRP 7-area model)

The standard CRP areas are reinterpreted for this domain:

| CRP Area | Domain Interpretation | What to Evaluate |
|----------|----------------------|------------------|
| **Architecture** | Pipeline integration design | Does the Dockerfile path integrate cleanly into the existing MicroPrime pipeline without distorting it? Is the language-dispatch pattern extensible to Go/proto without refactoring? Does the `bypass_files` vs `escalated_files` split create a clean separation of concerns? |
| **Interfaces** | Module boundaries and contracts | Are the interfaces between `lang_detect`, `validators/dockerfile`, `dockerfile_templates`, `file_assembler`, `splicer`, and `prime_adapter` well-defined? Do data models (`ForwardFileSpec.language`, `DockerfileValidationResult`) carry the right information at each boundary? |
| **Data** | Dockerfile content model fidelity | Does the `ForwardFileSpec` with empty elements/imports adequately represent a Dockerfile? Does the validator's directive-line parsing handle real-world Dockerfiles (continuation lines, parser directives, BuildKit features, `--platform` flags)? Is the template variable system rich enough? |
| **Risks** | Failure modes and regressions | What happens when the validator encounters a valid Dockerfile it can't parse? What are the Python regression risks? What if `ForwardManifestExtractor` runs before `lang_detect` is available? What if the template renders an invalid Dockerfile? |
| **Validation** | Test coverage and verification | Do the ~55 planned tests cover the critical paths? Are there untested edge cases in the validator (BuildKit syntax, heredocs, multi-line ENV)? Is the PI-013 test case sufficient, or do we need more real-world Dockerfile samples? |
| **Ops** | Pipeline observability and debugging | When a Dockerfile fails in the pipeline, can the user diagnose why? Are log messages at the right level? Does the `DockerfileValidationResult` carry enough information for debugging? Are advisory rules surfaced in pipeline output? |
| **Security** | Dockerfile security best practices | Does the template output follow security best practices (non-root USER, no ADD, pinned versions, no secrets in ENV)? Does the validator catch security anti-patterns? Is the advisory rule set complete? |

### Severity Calibration

| Severity | Domain Meaning |
|----------|---------------|
| **critical** | Would cause PI-013 (or equivalent) to fail again, or would regress existing Python pipeline functionality |
| **high** | Would produce invalid/insecure Dockerfiles in production, or would make the polyglot extension pattern non-reusable for Go |
| **medium** | Missed edge case, incomplete test coverage, or missing observability that would make debugging hard |
| **low** | Style, naming, documentation, or nice-to-have improvements |

---

## Domain-Specific Review Lenses

In addition to the standard CRP gap-hunting lenses (Phase 2b), apply these domain-specific lenses:

### Lens A: Real-World Dockerfile Fidelity

The validator and templates will encounter Dockerfiles from real projects, not textbook examples. Evaluate against these real-world patterns:

**BuildKit features (increasingly common):**
- `# syntax=docker/dockerfile:1` parser directive
- `RUN --mount=type=cache,target=/root/.cache/pip pip install ...` (cache mounts)
- `RUN --mount=type=secret,id=mysecret ...` (build secrets)
- `COPY --link` (merge-optimized copy)
- Heredoc syntax: `RUN <<EOF ... EOF` (Docker BuildKit 1.3+)

**Platform-aware builds:**
- `FROM --platform=$BUILDPLATFORM` / `FROM --platform=linux/amd64`
- `ARG TARGETPLATFORM` / `ARG BUILDPLATFORM` (auto-populated)
- Cross-compilation patterns (`GOARCH`, `GOARM`)

**Multi-stage patterns beyond simple 2-stage:**
- 3+ stages (builder → tester → runtime)
- Named stages referenced by `COPY --from=stagename`
- Stages that don't produce the final image (test-only stages)

**Continuation line edge cases:**
- `\` at end of RUN with inline comments: `RUN apt-get install -y \  # install deps`
- Extremely long RUN chains (50+ continuation lines)
- Continuation inside ENV multiline: `ENV FOO=bar \n    BAZ=qux`

**Question to answer:** Does the validator handle all of the above without false positives or false negatives? Does the plan address these, or are they deferred?

### Lens B: Edit Mode vs Create Mode Completeness

The requirements define two rendering modes. Evaluate their completeness:

**Edit mode (existing file passthrough):**
- What happens if the existing Dockerfile is malformed? Does passthrough still work?
- If the task description requests specific changes (e.g., "update base image to 3.14"), how does the pipeline communicate this to the LLM? Is the task description forwarded?
- Is passthrough the right default, or should the pipeline at least validate and annotate the existing file?

**Create mode (template rendering):**
- Are the template defaults sensible for the most common use cases?
- Can the template selection heuristic distinguish between "Python web service" and "Python load generator" (PI-013 is a load generator, not a web service — the Gold Standard template would be wrong for it)?
- What happens when no context is available? Is the fallback template usable?
- How does the user override template selection (e.g., force multi-stage for an interpreted language)?

### Lens C: Polyglot Extension Pattern

This is the first non-Python language through the pipeline. The patterns established here will be copied for Go, proto, YAML, and others. Evaluate:

- Is `lang_detect.py` the right abstraction? Would a `Language` enum be better than string returns?
- Is the `validators/` package structure ready for `validators/go.py` without restructuring?
- Does `ForwardFileSpec.language` carry enough information, or will Go need additional fields (e.g., `go_module_path`, `package_name`)?
- Does the `dockerfile_templates.py` peer-file pattern scale, or will 5+ template files become unwieldy?
- Is the `CodeTemplate` dataclass `language` field sufficient for registry integration, or does it need a language-aware match/render protocol?

### Lens D: Escalation Conflation Fix Completeness

The Phase 1 fix is critical and ships independently. Evaluate:

- Does the `bypass_files` vs `escalated_files` split handle all edge cases?
  - What about a file where `file_spec` exists but `skeleton` is empty? (Currently goes to `escalated_files` — should it?)
  - What about a Python file that fails skeleton generation due to a render error? (It has a `file_spec` but no skeleton.)
  - What about a file with `language="unknown"`?
- Does `_generate_with_fallback()` need modification to accept a subset of files (bypass only)?
- Is the metadata in `GenerationResult` updated to distinguish bypass from escalation?
- Can the user observe the distinction in pipeline output (logs, prime-result.json)?

### Lens E: Best Practices Research Integration

The research doc ([docker-file-assembly-via-python.md](../scaffold/docker-file-assembly-via-python.md)) contains 14 prioritized best practices. Evaluate:

- Are all Critical/High practices reflected in either templates or validator advisory rules?
- The research recommends `python:X.Y-slim` as default — but PI-013's loadgenerator uses `python:3.14.2-alpine`. Does the validator flag this? Should it? (The alpine choice may be intentional for that project.)
- The Gold Standard template includes `apt-get` with `build-essential` — but not all Python projects need C compilation. Is this an unnecessary bloat in the template?
- The research says "always use multi-stage unless user opts out" — but the plan offers single-stage as a create-mode option. Is this a contradiction?
- The `HEALTHCHECK` in the multi-stage template uses `curl` — but `python:X.Y-slim` may not have `curl` installed. The Go template uses `wget`. Is this consistent?
- The research mentions `.dockerignore` — but the templates don't generate one. Should they? (Arguably out of scope for skeleton assembly.)

### Lens F: Test Case Adequacy

The PI-013 loadgenerator Dockerfile is the primary test case. But it has specific characteristics that may not generalize:

- It uses `--platform=$BUILDPLATFORM` (platform-aware builds)
- It uses `pip install --prefix` (not wheels, not venv)
- It uses shell-form ENTRYPOINT (not exec form) — the validator should flag this as DV-BP-004
- It uses `alpine` base images — the validator should flag this as DV-BP-010

**Are additional test Dockerfiles needed?** Consider:
- A Go multi-stage build (online-boutique has several)
- A Node.js single-stage (different dependency pattern)
- A minimal `FROM scratch` (distroless)
- A Dockerfile with heredoc syntax
- A Dockerfile with ARG-based version pinning

---

## Suggestion ID Format

Follow CRP convention:
- **Plan suggestions:** `R{n}-S{m}` (target: implementation plan)
- **Requirements suggestions:** `R{n}-F{m}` (target: requirements doc)

---

## Threshold Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Substantially addressed threshold | 2 per area | Smaller document scope than typical CRP targets — 7 areas across ~15 files |
| Max suggestions per round | 10 | Standard CRP default |
| Max rounds before convergence check | 3 | Focused scope — should converge faster than a full architecture review |

---

## Phase 2 Guidance: Priority Steering

### First Review Round (R1)

For the first review, prioritize these areas based on impact:

| Priority | Area | Why |
|----------|------|-----|
| 1 | Risks | The escalation conflation fix ships independently — any gap there blocks PI-013 |
| 2 | Data | Dockerfile content model fidelity determines whether the validator works on real Dockerfiles |
| 3 | Interfaces | Module boundaries established here become the polyglot extension pattern for Go |
| 4 | Architecture | Pipeline integration design — does this distort existing Python flow? |
| 5 | Validation | Test coverage — are the ~55 tests adequate? |
| 6 | Security | Best practice advisory rules — completeness check |
| 7 | Ops | Observability — lower priority for initial review |

### Subsequent Rounds (R2+)

Apply standard CRP two-tier priority based on coverage gaps. Additionally:

- If Risks and Data are addressed, shift focus to Lens C (polyglot extension pattern) — this is the highest long-term value area
- If Interfaces are addressed, apply Lens E (research integration) to verify template quality
- In late rounds, apply Lens D (escalation fix completeness) as a focused deep-dive — this is the code most likely to ship first

---

## Cross-Document Traceability Requirements

The Requirements Coverage table (CRP Phase 3-DD, Section 3) must map these requirement sections:

| Requirement (from REQ-MP-3xx) | Expected Plan Phase |
|-------------------------------|-------------------|
| FR-DFA-001: Escalation conflation | Phase 1 |
| FR-DFA-002: Language detection | Phase 2 |
| FR-DFA-003: Extractor Dockerfile support | Phase 3 |
| FR-DFA-004: Dockerfile structural validator | Phase 4 |
| FR-DFA-005: Dockerfile templates | Phase 5 |
| FR-DFA-006: Assembler Dockerfile rendering | Phase 6 |
| FR-DFA-007: Full-file splicing | Phase 6 |
| FR-DFA-008: Template registry integration | Phase 5 |
| FR-DFA-009: ForwardFileSpec language field | Phase 3 |
| FR-DFA-010: Prime adapter integration | Phase 7 |
| NFR-DFA-001: Zero LLM cost | All phases |
| NFR-DFA-002: No new dependencies | All phases |
| NFR-DFA-003: Python regression safety | All phases |
| NFR-DFA-004: Validator extensibility | Phase 4 |
| NFR-DFA-005: Performance | Phase 4, 5 |

Verify that every FR and NFR has corresponding implementation steps and test coverage in the plan.

---

## Context: Existing Codebase Patterns

When reviewing, be aware of these existing patterns that the implementation must follow:

| Pattern | Where | Relevance |
|---------|-------|-----------|
| `get_logger(__name__)` | All SDK modules | New modules must use this, not `logging.getLogger()` — Loki visibility |
| `ForwardElementSpec` model validators | `forward_manifest.py:168-206` | Template for field validation patterns |
| `DeterministicFileAssembler` render contract | `file_assembler.py:253-299` | The `render_file()` method returns a complete source string — `render_dockerfile()` must follow same contract |
| `splice_body_into_skeleton()` | `splicer.py` | Existing Python splicing function — `splice_dockerfile()` should follow naming and error handling conventions |
| `_FileProcessingState` dataclass | `prime_adapter.py:246-266` | Adding `bypass_files` field — follow existing field patterns |
| `SKELETON_SENTINEL` marker | `file_assembler.py:56-58` | Python skeletons are marked — consider whether Dockerfiles need an equivalent marker |
| `MicroPrimeConfig` model | `micro_prime/models.py` | Config loading pattern — if Dockerfile assembly needs config flags, add them here |
| Error handling: per-file try/except | `prime_adapter.py:461-489` | Single-file failures must not abort the entire feature — follow existing guard pattern |

---

## Output Routing

After generating your review round:

1. **S-prefix suggestions** (plan improvements) → Append to `DOCKERFILE_SKELETON_ASSEMBLY_IMPLEMENTATION_PLAN.md` Appendix C
2. **F-prefix suggestions** (requirements improvements) → Append to `REQ-MP-3xx_DOCKERFILE_SKELETON_ASSEMBLY.md` Appendix C
3. **Requirements Coverage table** → Append alongside S-prefix suggestions in the plan document

Do not modify the research doc or the parent polyglot registry requirements — those are read-only reference material.
