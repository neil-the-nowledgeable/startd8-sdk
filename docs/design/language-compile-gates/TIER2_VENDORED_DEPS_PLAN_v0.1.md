# Tier-2 Vendored Dependency Bundles — Reflection & Implementation Plan

**Version:** 0.1 (planning pass for Java FR-J4/J5/J6 + C# FR-C4/C5/C6)
**Date:** 2026-06-14
**Status:** Planning — no gate/vendoring code written yet
**Source reqs:** `JAVA_COMPILE_GATE_REQUIREMENTS_v0.1.md`, `CSHARP_COMPILE_GATE_REQUIREMENTS_v0.1.md`
**Scope:** lift the 2 services that currently degrade (adservice=Java, cartservice=C#) from
missing-deps-degraded to a **real offline compile**, by vendoring their gRPC/protobuf deps.

---

## 1. What Tier-1 already established (the baseline this builds on)

Both gates ship and fire offline in the FR-44 sandbox (`benchmark_matrix/scoring.py`):
- **Java:** single-file `javac -proc:none` → real syntax/type check; gRPC imports unresolved →
  `cannot find symbol` / `does not exist` → **degraded (missing-deps)**, not floored (FR-J2).
- **C#:** Roslyn `csc.dll` + the SDK framework ref assemblies (`-r:…`) driven directly — **no
  project, no NuGet restore** → gRPC `using`s → `CS0246` → **degraded** (FR-C3).

Tier-2's only job: supply the missing deps so those two compile for real. Everything else
(classification, floor-on-syntax, sandbox, provenance) is reused unchanged.

---

## 2. Planning insights (what the plan revealed vs the v0.1 reqs)

| # | v0.1 assumption | Planning discovery | Impact |
|---|---|---|---|
| **P1** | **C#: `dotnet build --no-restore`** is the Tier-2 mechanism (FR-C5) | Tier-1 spike proved `dotnet build` is **hostile in the sandbox** — redirected `HOME` + no network triggers the first-run/workload experience and it bails (rc=1, welcome text). | **Reframe FR-C5:** C# Tier-2 = **`csc -r:<vendored gRPC/protobuf DLLs>`** (extend the proven Tier-1 csc invocation with extra `-r:` refs), NOT `dotnet build`. Sidesteps the project/restore/first-run machinery entirely. |
| **P2** | "vendor the deps" reads as *download jars/packages* | `javac -cp` needs **compiled** `.class`/jars; `csc -r` needs **compiled** `.dll`s. The proto stubs must be **generated AND compiled**, then vendored — not just fetched. | Tier-2 is a **build pipeline**, not a download. Adds a compile-the-stubs step (gradle for Java; `csc`/`dotnet` for the C# stub DLL). Heavier than v0.1 implied. |
| **P3** | protoc + gRPC plugins are "available" | `protoc` not on PATH; `grpc_tools` (venv) bundles protoc **+ the Python gRPC plugin only**. Java needs `protoc-gen-grpc-java` (Maven); C# needs `grpc_csharp_plugin` (ships in the **Grpc.Tools** NuGet). | The **plugin acquisition** is the real network-once cost. Plan must pin + fetch: Java→Maven (`grpc-java`, `protobuf-java`, `protoc-gen-grpc-java`); C#→NuGet (`Grpc.Tools`, `Grpc.Net.Client`/`Grpc.Core`, `Google.Protobuf`). gradle + dotnet are present to drive each side. |
| **P4** | Tier-2 is the next thing to build | It lifts **exactly 2 of 9 services**, and given metric saturation the leaderboard almost certainly stays ~1.000. It only changes a *score* if a model emitted a **real** Java/C# compile error currently masked by missing-deps degradation. | **Low marginal Round-1 value, high effort/repo-weight.** Resolves OQ-J3/OQ-C4: **ship Round 1 with Java/C# disclosed-degraded; Tier-2 is a fast-follow, NOT Round-1-blocking.** Real value = methodological completeness + future rounds + a concrete FR-44 dependency-quarantine demonstration. |
| **P5** | Bundle home is an open fork | The capability (the gate) is SDK-owned and `demo.proto` already lives in the SDK (`docs/design/model-benchmark/seeds/`). | Recommend **SDK-resident bundle** (`src/startd8/benchmark_matrix/vendored/<lang>/`) + a checksum manifest. **But** binary weight (jars ~10–20 MB, DLLs) is a real cost → flag **commit vs git-lfs vs generate-not-commit** as a user decision (§5). |
| **P6** | Gate command is static | Tier-1 already split static (`_FALLBACK_SYNTAX_COMMANDS`) vs dynamic (`_discover_dotnet_csc`). | Add a parallel **`_vendored_bundle(language_id)`** discovery: bundle present → real compile command (`javac -cp` / `csc -r vendored`); absent → **fall back to Tier-1 (degraded)**. Tier-2 is purely **additive + gracefully degrading** — zero Round-1 risk. |

**Resolved open questions**
- **OQ-J1 / OQ-C3 (bundle home) →** SDK-resident (`benchmark_matrix/vendored/`), checksum-manifested; commit-vs-lfs deferred to a §5 decision.
- **OQ-J2 / OQ-C2 (reproducible generation) →** a single pinned, network-once generator script writing a provenance manifest (versions + sha256); gate runs fully offline thereafter.
- **OQ-J3 / OQ-C4 (vendor now vs degraded for Round 1) →** **degraded for Round 1** (disclosed); Tier-2 built as a fast-follow.
- **OQ-C1 (C# offline mechanism) →** already resolved in Tier-1 (csc, not dotnet build); Tier-2 = same csc + vendored `-r:` refs (P1).

---

## 3. Target design

### 3.1 Bundle layout (SDK-resident)
```
src/startd8/benchmark_matrix/vendored/
  manifest.json              # tool+dep versions, sha256 of every vendored file, proto sha256, generator provenance
  java/
    stubs.jar                # compiled hipstershop message + gRPC service classes (from demo.proto)
    lib/*.jar                # grpc-java (api/stub/protobuf), protobuf-java — pinned
  csharp/
    Hipstershop.Stubs.dll    # compiled C# message + gRPC service classes
    ref/*.dll                # Grpc.Net.Client/Grpc.Core, Google.Protobuf (+ transitive) — pinned
```

### 3.2 Gate command (offline, in the FR-44 sandbox)
- **Java:** `javac -proc:none -cp <vendored/java/stubs.jar:vendored/java/lib/*> -d . {file}`
- **C#:** `dotnet <csc.dll> -nologo -nostdlib -t:library -out:/dev/null -r:<framework refs> -r:<vendored/csharp/*.dll> {file}`

Both: bundle present → real compile (floor on real error, **pass** on success); bundle
absent/incomplete → Tier-1 path (degraded). Classification (FR-J2/FR-C3) unchanged.

### 3.3 Generator (network-once, pinned, provenance-stamped)
`scripts/build_compile_gate_bundle.py` (or `.sh`): pin versions → fetch protoc + plugins +
dep jars/packages → `protoc --java_out/--grpc-java_out` & `--csharp_out/--grpc_out` →
compile stubs (gradle / csc) → copy deps → write `manifest.json` (versions + sha256 +
`proto_sha256` + generated-at). Re-runnable; output is byte-stable given pinned inputs.

---

## 4. Phased plan

| Phase | Deliverable | Notes |
|---|---|---|
| **T2-0** | This plan + v0.2 reqs + **§5 decisions resolved** | gate: don't build until bundle-home + commit/lfs + build-now/defer are answered |
| **T2-1** | `vendored/` discovery + gate wiring in `scoring.py` (`_vendored_bundle`, `-cp`/`-r:` threading) + tests with a **fake/tiny bundle** | additive; no real bundle needed to test the wiring; degrades when absent |
| **T2-2** | **Java** generator + bundle (protoc + protoc-gen-grpc-java + grpc-java/protobuf-java → stubs.jar) + manifest | network-once; verify `javac -cp` compiles real adservice offline in-sandbox |
| **T2-3** | **C#** generator + bundle (Grpc.Tools protoc/grpc_csharp_plugin + Grpc/Protobuf DLLs → Stubs.dll) + manifest | verify `csc -r vendored` compiles real cartservice offline in-sandbox |
| **T2-4** | `$0` re-score round-1 with bundles present; provenance (FR-19/J6/C6); docs | reuses the shipped re-score path; updates leaderboard coverage (likely still ~1.000) |

T2-1 is safe to build anytime (pure wiring, degrades gracefully). T2-2/T2-3 are the
network-once, repo-weight steps gated on §5.

---

## 5. Decisions required before T2-2/T2-3 (user)

1. **Build now vs defer?** Reflection P4 says Tier-2 is low marginal Round-1 value. Recommend:
   build **T2-1 wiring now** (cheap, additive), **defer T2-2/T2-3** until after Round 1 ships
   Java/C# disclosed-degraded — unless a real Java/C# compile error is suspected.
2. **Bundle home + storage:** SDK `benchmark_matrix/vendored/` (recommended) vs benchmark repo;
   and **commit binaries** vs **git-lfs** vs **generate-not-commit** (CI/dev runs the generator).
3. **Pinned versions:** grpc-java / protobuf-java / Grpc.* / Google.Protobuf / protoc — exact pins
   recorded in `manifest.json` (proposed: latest stable at build time, then frozen).

---

*Planning pass per the reflective-requirements loop. Next: bump both req docs to v0.2 with §0
Planning Insights, then resolve §5 and (optionally) run a CRP review before implementing.*
