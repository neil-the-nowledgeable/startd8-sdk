# C# Compile-Gate Capability — Requirements

**Version:** 0.1 (Draft — pre-planning)
**Date:** 2026-06-14
**Status:** Draft
**Owner SDK area:** `startd8.languages` (C# `LanguageProfile`) + `startd8.benchmark_matrix.scoring`
**Consumers:** Summer 2026 benchmark (and any model-codegen quality gate)

---

## 1. Problem Statement

The benchmark compile gate (FR-29) degrades for **C#** (`cartservice`). The C# `LanguageProfile`'s
`syntax_check_command` is `None`, and C# has **no clean single-file compile**: `dotnet build` needs a
`.csproj` and a **NuGet restore**, which the FR-44 sandbox **blocks (no network)**. So even though the
`dotnet` SDK is installed, the gate cannot fire and `cartservice` scores structural-only.

### Gap table

| Aspect | Current | Needed |
|--------|---------|--------|
| `syntax_check_command` (C#) | `None` → degrades | a C# check the scorer can run offline |
| single-file check | none (no `csc --check`) | Roslyn parse (Tier 1) or project build (Tier 2) |
| NuGet restore | blocked (no-network sandbox) | pre-restored / vendored packages, `--no-restore` |
| failure classification | "degraded" lumps everything | syntax-error / missing-dep / toolchain-absent / sandbox-violation |

---

## 2. Requirements

### Tier 1 — single-file syntax (cheap, partial)

- **FR-C1.** Provide an **offline Roslyn-based syntax check** of the generated `.cs` file (e.g. a tiny
  prebuilt analyzer/host, or `dotnet` invoking Roslyn `CSharpSyntaxTree.ParseText` with diagnostics) —
  syntax-only, no project, no restore. Runs inside the FR-44 sandbox.
- **FR-C2.** If a clean offline single-file check proves infeasible, the gate stays **degraded (FR-32)**
  for C# until Tier 2 — recorded honestly, never scored as a model failure.
- **FR-C3.** Classify: in-file syntax errors → **compile FAIL** (FR-11 floor); type/`using` resolution
  errors → **DEGRADED (missing-deps)**; `dotnet`/Roslyn absent → **toolchain-absent** (FR-32).

### Tier 2 — real compile with offline-restored deps (high fidelity)

- **FR-C4.** Generate a **minimal `.csproj`** for the service referencing pinned NuGet packages
  (`Grpc.Net.Client`/`Grpc.Core`, `Google.Protobuf`, `Grpc.Tools`) + the protoc-generated C# stubs
  from `demo.proto`.
- **FR-C5.** **Offline restore workflow:** restore those packages **once with network**, vendor the
  result (a local NuGet `global-packages` folder or an offline feed) + check it in; at run time the
  gate runs `dotnet build --no-restore` **with no network** (FR-44 dependency-quarantine satisfied).
- **FR-C6.** Bundle + csproj are **checksummed/checked in**; package + SDK versions recorded in
  provenance (FR-28/FR-19 reproducibility).

### Cross-cutting

- **FR-C7.** Entirely inside the FR-44 sandbox (no network, rlimits, scrubbed env, disposable
  workspace); sandbox violations recorded separately, never as model quality.
- **FR-C8.** `dotnet` SDK detection (present + version) in provenance; absence → degraded (FR-32).
- **FR-C9.** Integrates via `LanguageProfile` + the `benchmark_matrix.scoring` composite (floor on real
  fail, degrade on missing-dep/toolchain).

---

## 3. Non-Requirements

- **Not** executing tests (OQ-11 deferred); compile only.
- **Not** a full solution / multi-project build — single service project.
- **Not** VB.NET / F#.
- **Not** any run-time network/NuGet fetch — pre-restored/vendored only (FR-44).

## 4. Open Questions

- **OQ-C1.** Cleanest offline single-file Roslyn check on macOS dotnet 10 — `dotnet script`, a prebuilt
  analyzer exe, or skip Tier 1 and go straight to Tier 2?
- **OQ-C2.** Offline-restore mechanism: vendored `global-packages` dir vs a checked-in local feed
  (`nuget.config` `<packageSources>`), and how to keep it reproducible/pinned.
- **OQ-C3.** Bundle home: SDK fixtures vs benchmark project (same as Java OQ-J1).
- **OQ-C4.** Is C# acceptable as **degraded for Round 1** (1 of 9 services), with Tier 2 a fast-follow?

*Draft 0.1 — will be refined via a planning pass (reflective-requirements) before implementation.
Shares the Tier-2 "vendored offline dependency bundle" pattern with the Java compile gate.*
