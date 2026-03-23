# Polyglot MicroPrime — Validation Status & Requirements

> **Date:** 2026-03-23
> **Context:** Session implemented Phase 1 (TRIVIAL templates) + Phase 2 (SIMPLE bypass removal + splicer wiring) for polyglot MicroPrime. Zero end-to-end validation has occurred — all changes are unit-tested but no Prime Contractor run has exercised the new code paths.

---

## 1. What Was Built This Session

| Component | Files Changed | Unit Tested | E2E Tested |
|-----------|--------------|-------------|-----------|
| Template dispatch map (`_LANGUAGE_TEMPLATES`) | `templates.py` | Yes (8 tests) | **No** |
| TRIVIAL bypass removal (`_handle_trivial`) | `engine.py` | Yes (6 tests) | **No** |
| SIMPLE template short-circuit (`_try_simple_shortcircuit`) | `engine.py` | Yes (1 test) | **No** |
| SIMPLE bypass removal (`_handle_simple`) | `engine.py` | Yes (2 tests) | **No** |
| C# splicer dispatch (`_splice_csharp_dispatch`) | `splicer.py` | No | **No** |
| `NO_TEMPLATE_MATCH` escalation reason | `models.py` | Yes (1 test) | **No** |
| UPSERT template (PostgreSQL×C#) | `crud.py` | Yes (8 tests) | **No** |

### What "E2E Tested" Means
A Prime Contractor run where:
1. MicroPrime is enabled (`--micro-prime --complexity-routing`)
2. Elements are classified as TRIVIAL or SIMPLE
3. Templates actually match and produce code ($0.00)
4. OR Ollama generates code that gets spliced into skeletons
5. The generated code passes `validate_syntax()` and appears in the final output

**No run has validated this.** Run-113 had MicroPrime enabled but all features classified as COMPLEX → 100% cloud escalation → zero local generation.

---

## 2. Template Match Coverage (Simulated)

| Language | Template | Match Condition | Simulated | Works |
|----------|----------|----------------|-----------|-------|
| **Go** | `go_constructor` | `New{Name}` + params | Yes | Pass |
| **Go** | `go_main` | `main()` | Yes | Pass |
| **Go** | `go_stringer` | `String()` on parent | Not tested | — |
| **Go** | `go_getter` | `Get{Name}` + no params | Not tested | — |
| **Java** | `java_getter` | `get{Name}` / `is{Name}` | Yes | Pass |
| **Java** | `java_spring_main` | `main` with args | Yes | Pass |
| **Java** | `java_constructor` | name == parent_class | Not tested | — |
| **C#** | `csharp_di_constructor` | name == parent + interface params | Yes | Pass |
| **C#** | `csharp_constructor` | name == parent_class | Yes | Pass |
| **C#** | `csharp_property` | getter/setter property | Not tested | — |
| **Node.js** | `js_constructor` | `constructor` + parent_class | Yes | Pass |
| **Node.js** | `js_getter` | `get{Name}` | Not tested | — |

---

## 3. Known Gaps

### GAP-1: No E2E Validation Run

**Severity:** Critical
**Impact:** Every change from this session is unvalidated in a real pipeline run

**What's needed:** A Prime Contractor run where at least some elements classify as TRIVIAL or SIMPLE and attempt local generation. Run-113 showed "complex=15" — we need to understand why and ensure at least some elements hit the template path.

**Possible cause:** The feature-level classifier may be using different signals at runtime than our simulation (manifest_coverage, blast_radius from actual files on disk). Need to add logging to track per-element classification reasons.

### GAP-2: Splicer Dispatch Untested for C#

**Severity:** High
**Impact:** If `splice_csharp_bodies()` fails on real generated code, SIMPLE C# elements will silently produce `SpliceResult(code=None)` → escalation

**What's needed:** Integration test: generate a C# method body via Ollama → splice into skeleton → verify syntax valid

### GAP-3: Ollama C# Code Quality Unknown

**Severity:** High
**Impact:** If Ollama (startd8-coder) generates poor C# code, the SIMPLE tier path will always escalate → no cost savings

**What's needed:** Offline evaluation: feed 10 C# method bodies to Ollama, check syntax validity rate and functional correctness

### GAP-4: Dockerfile/HTML/YAML Templates Not Implemented

**Severity:** Medium
**Impact:** These file types always go to cloud LLM even when deterministic generation is possible

**Dockerfile specifics:**
- Language profiles already have `docker_base_image` and `docker_runtime_image`
- REQ-MP-3xx_POLYGLOT specs 2 Dockerfile templates (multi-stage, single-stage)
- C# profile has comprehensive Dockerfile guidance in `build_project_context_section()`
- A multi-stage Dockerfile template is highly deterministic per language

### GAP-5: `go.mod` and `.csproj`/`.sln` Templates Outside MicroPrime

**Severity:** Low
**Impact:** These are handled by dedicated generators (not in MicroPrime template registry) but should be unified for consistency

**Current state:**
- `go.mod`: `_try_generate_go_mod()` in prime_adapter.py (deterministic, works)
- `.csproj`: `CSharpLanguageProfile.generate_dependency_file()` (deterministic, works)
- `.sln`: `CSharpLanguageProfile.generate_solution_file()` (deterministic, works)
- `package.json`: `NodeLanguageProfile.generate_dependency_file()` (deterministic, works)
- `build.gradle`: `JavaLanguageProfile.generate_dependency_file()` (deterministic, works)

These work but are invoked at different pipeline stages, not through MicroPrime's template registry. Unification would be nice but isn't blocking.

---

## 4. Requirements for Validation

### REQ-MPV-001: Classification Observability

Add structured logging to `_handle_trivial()` and `_handle_simple()` showing:
- File path, language_id, and template match result (or no match)
- Element name, kind, parent_class
- Whether escalation occurred and why

**Purpose:** Without this, we can't diagnose why run-113 classified everything as COMPLEX. The log said "Tier distribution: complex=15" but simulation shows SIMPLE for several features.

### REQ-MPV-002: Template Match Integration Test

Create an integration test that:
1. Creates a `MicroPrimeEngine` with templates enabled
2. Calls `_handle_trivial()` with a Go `main` element → asserts success with `go_main` template
3. Calls `_handle_trivial()` with a C# `CartStore` constructor → asserts success with `csharp_constructor`
4. Calls `_handle_trivial()` with a Java `getName` getter → asserts success with `java_getter`
5. Verifies each output is valid code (not a stub, not empty)

### REQ-MPV-003: Splicer Integration Test

Create an integration test that:
1. Provides a C# skeleton with `throw new NotImplementedException()` stubs
2. Provides a generated method body
3. Calls `splice_body_into_skeleton()` with `file_path="CartStore.cs"`
4. Verifies the C# splicer dispatch fires (not Python AST)
5. Verifies the output contains the generated body, not the stub

### REQ-MPV-004: Dockerfile Template Registration

Register Dockerfile templates in the MicroPrime template registry:

**Template 1: Multi-stage .NET build**
- Match: file named `Dockerfile`, language context is C#
- Generate: `FROM mcr.microsoft.com/dotnet/sdk:{version} AS build` + restore-first + publish + runtime stage from `LanguageProfile.docker_base_image`/`docker_runtime_image`

**Template 2: Multi-stage Go build**
- Match: file named `Dockerfile`, language context is Go
- Generate: `FROM golang:{version} AS build` + module download + build + scratch/distroless runtime

**Template 3: Multi-stage Node.js build**
- Match: file named `Dockerfile`, language context is Node.js
- Generate: `FROM node:{version} AS build` + npm ci + copy + runtime

**Implementation:** Register in a new `_DOCKERFILE_TEMPLATES` list, add `"dockerfile"` to `_LANGUAGE_TEMPLATES` map, add `.dockerfile` detection (or filename-based matching).

### REQ-MPV-005: Proto File Template

Register `.proto` file template:
- Match: file ending in `.proto`
- Generate: `syntax = "proto3";` + package from namespace + service/message stubs from element names
- Leverage: `build_project_context_section()` already has proto guidance for C#/Go

---

## 5. Validation Plan

### Phase A: Observability (REQ-MPV-001)

Add logging, re-run C# cartservice. Inspect logs to understand why elements classify as COMPLEX despite low LOC.

### Phase B: Template Integration Tests (REQ-MPV-002, 003)

Write and run integration tests for all 4 languages + C# splicer. These validate the infrastructure without needing a full pipeline run.

### Phase C: Controlled Pipeline Run

Run C# cartservice with:
- `--micro-prime --complexity-routing` (already default via pipeline.env)
- Lower `loc_complex_min` to 300 (from 500) to force some features into SIMPLE tier
- Inspect: which elements got local templates, which got Ollama, which escalated
- Compare cost and quality against run-113

### Phase D: Dockerfile Templates (REQ-MPV-004)

After Phase C validates the template infrastructure works, add Dockerfile templates and verify they produce valid multi-stage builds.
