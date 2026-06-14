# Java Compile-Gate Capability — Requirements

**Version:** 0.2 (Post-planning — self-reflective update; Tier-1 SHIPPED)
**Date:** 2026-06-14
**Status:** Tier-1 implemented & merged to main; Tier-2 planned (deferred)
**Owner SDK area:** `startd8.languages` (Java `LanguageProfile`) + `startd8.benchmark_matrix.scoring`
**Consumers:** Summer 2026 benchmark (and any model-codegen quality gate)

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (pre-planning) and v0.2. **Tier-1 is now shipped**; Tier-2 was planned
> in `TIER2_VENDORED_DEPS_PLAN_v0.1.md` (shared with C#) and the planning pass re-scoped it.

| v0.1 assumption | Planning/impl discovery | Impact |
|---|---|---|
| Tier-1 wiring via `syntax_check_command` OR `validate_syntax` (FR-J3) | The scorer already has a `_FALLBACK_SYNTAX_COMMANDS` seam (Node precedent); the Java profile's `validate_syntax` uses the **javalang parser** (no type/symbol checking, unsandboxed). | Tier-1 wired via the fallback seam: `javac -proc:none` in the FR-44 sandbox. **SHIPPED.** |
| "missing symbol" ambiguity is a worry | Confirmed via real adservice: gRPC/`hipstershop` imports → `cannot find symbol`/`does not exist`. | FR-J2 classifier ships; conservatively **degrades** (not floors) — the documented Tier-1 trade-off. |
| Tier-2 is the immediate next step | Tier-2 lifts **only 2 of 9 services** and, under metric saturation, likely leaves the leaderboard ~1.000; it only moves a score if a model emitted a *real* compile error now masked by degradation. | **OQ-J3 resolved: ship Round 1 Java disclosed-degraded; Tier-2 is a fast-follow.** |
| Tier-2 = "vendor the deps" | `javac -cp` needs **compiled** jars; the proto stubs must be **generated + compiled**, and `protoc-gen-grpc-java` is a separate Maven acquisition. | Tier-2 is a **pinned build pipeline**, not a download (see plan §2–3). |

**Resolved open questions:** OQ-J1 → SDK-resident bundle (`benchmark_matrix/vendored/java/`),
checksum-manifested (commit/lfs = open §5 decision in the plan). OQ-J2 → single pinned
network-once generator + provenance manifest. OQ-J3 → **degraded for Round 1**, Tier-2 deferred.

*Tier-1 (FR-J1/J2/J3/J7/J8) is implemented in `benchmark_matrix/scoring.py` and merged.
Tier-2 (FR-J4/J5/J6) is specified below and planned in `TIER2_VENDORED_DEPS_PLAN_v0.1.md`.*

---

## 1. Problem Statement

The benchmark composite quality (FR-11) folds in a **compile gate** (FR-29): the generated file is
run through its language's syntax/compile check inside the FR-44 sandbox. Today the gate fires only
for **Python** (`py_compile`) and **Go** (`gofmt -e`); **Java** degrades (FR-32) because:

1. The Java `LanguageProfile.syntax_check_command` is `None` — no command for the scorer to run.
2. A naive single-file `javac` of an Online Boutique service (e.g. `AdService.java`) **fails on the
   gRPC/`hipstershop` imports** that aren't present, and the FR-44 sandbox **denies network**, so the
   dependencies (grpc-java, protobuf-java, the protoc-generated stubs) cannot be fetched at run time.

Result: Java cells score structural-only and don't discriminate on functional correctness — the same
saturation the compile gate is meant to break.

### Gap table

| Aspect | Current | Needed |
|--------|---------|--------|
| `syntax_check_command` (Java) | `None` → scorer degrades | a real Java check the scorer can run |
| single-file `javac` | fails on absent gRPC/package imports | classify those as *missing-deps*, not model-fail |
| dependency resolution | blocked (no-network sandbox) | vendored offline deps for a real compile |
| failure classification | "degraded" lumps everything | distinguish syntax-error / missing-dep / toolchain-absent / sandbox-violation |

---

## 2. Requirements

### Tier 1 — single-file syntax gate (cheap, partial)

- **FR-J1.** Provide a Java single-file syntax/type check the scorer can invoke — `javac -d <tmp>
  {file}` (or `-proc:none`), run inside the FR-44 sandbox (no network, rlimits, scrubbed env).
- **FR-J2.** **Failure classification (load-bearing):** parse `javac` output and classify
  - `error: package ... does not exist` / `cannot find symbol` / `cannot access` → **DEGRADED
    (missing-deps)** — do NOT floor the model (the gRPC stubs are legitimately absent in Tier 1);
  - genuine syntax/type errors in the file → **compile FAIL** → FR-11 compile floor;
  - `javac` not found / non-zero with toolchain markers → **toolchain-absent** (FR-32 degraded).
- **FR-J3.** Wire it so `benchmark_matrix.scoring` consumes it (either via `LanguageProfile`
  `syntax_check_command` + a classifier, or a `validate_syntax`-style method the scorer falls back to).

### Tier 2 — real compile with vendored deps (high fidelity)

- **FR-J4.** Ship a **vendored offline dependency bundle** for Java: the protoc-generated
  `hipstershop` Java stubs (from `demo.proto`) + pinned `grpc-java` + `protobuf-java` jars.
- **FR-J5.** Compile gate runs `javac -cp <vendored-bundle> -d <tmp> {file}` **with no network**
  (deps are vendored, satisfying both the build need AND FR-44 dependency-quarantine).
- **FR-J6.** Bundle is **checksummed + checked in** (reproducibility, FR-19) and generated by a
  documented, pinned step (protoc + dependency versions recorded in provenance, FR-28).

### Cross-cutting

- **FR-J7.** Runs entirely inside the FR-44 sandbox (no network, resource-limited, scrubbed env);
  a sandbox violation is recorded as such, never as model quality.
- **FR-J8.** Toolchain detection (`javac` present + version) recorded in provenance; absence →
  degraded (FR-32), not failure.

---

## 3. Non-Requirements

- **Not** executing tests (OQ-11 — model-written tests deferred); compile only.
- **Not** a full Gradle/Maven build of `adservice` (needs network / heavy) — vendored-classpath `javac`.
- **Not** Kotlin/Scala (the JVM profile's other dialects).
- **Not** fetching any dependency at run time — vendored only (FR-44).

## 4. Open Questions

- **OQ-J1.** Bundle home: SDK fixtures (`startd8/...`) vs the benchmark project? (Capability is SDK;
  data may be benchmark-specific.)
- **OQ-J2.** protoc + grpc-java/protobuf-java version pinning + reproducible stub generation.
- **OQ-J3.** Is Tier-1 (syntax + missing-dep-degraded) sufficient for Round 1, with Tier-2 deferred?
- **OQ-J4.** Does the existing Java `LanguageProfile.validate_syntax` (if any) already do single-file
  `javac`? If so, the scorer just needs the fallback + FR-J2 classification.

*Draft 0.1 — will be refined via a planning pass (reflective-requirements) before implementation.*
