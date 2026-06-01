# Generalized Compile-Gate (Go / Java / C#) — Requirements

**Version:** 0.3 (Post-CRP — triage applied)
**Date:** 2026-06-01
**Status:** Draft (ready for implementation)
**Precedent:** RUN-008 TypeScript toolchain gate — `src/startd8/validators/ts_toolchain.py` (FR-4 project-level `tsc --noEmit`, FR-9 loud degradation) + the cap-dev-pipe post-run gate `ts-verify-gate.py` + the in-process postmortem hook `_evaluate_ts_toolchain`. This doc generalizes that gate to the compiled languages and unifies all four under one abstraction.
**Related:** `docs/design/RUN_008_REMEDIATION_REQUIREMENTS.md` (§4 OQ-3 — pipeline-owned gate + provisioning decision, reused here).

> **Origin.** A RUN-008 follow-up audit confirmed that only TypeScript was vulnerable to a per-file *false positive* (resolving compiler in isolation), but surfaced the *inverse* gap: Go/Java/C# have **no project-level cross-file resolution gate decoupled from test execution**. Their per-file validators are syntax-only (`gofmt -e`, javalang AST, tree-sitter); cross-file resolution happens only if the checkpoint's `test_command` runs (which compiles), and that needs a provisioned toolchain *and* tests to run. When unprovisioned (the run-008 condition), cross-file incoherence in a compiled-language batch slips through silently — the same verify-blind failure mode, generalized.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the protocol, the per-language profiles, and the existing `ts_toolchain`. It corrected four assumptions baked into the v0.1 framing:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| "Add a `compile_check_command` to the protocol" is a localized change | `LanguageProfile` is a `@runtime_checkable` Protocol; `registry.register()` does `isinstance(profile, LanguageProfile)`, which checks **attribute presence**. A new required member makes **all 7 registered profiles** (python/go/nodejs/java/csharp/vue/prisma) fail `isinstance` until each defines it → registration `TypeError`. | **FR-1 must add the member to all 7 profiles at once** (return `None` for non-compiled langs), like `syntax_check_command`. Net-new breadth, not a one-file change. |
| The gate is "run one compile command per language" | Each compiled language needs **dependency provisioning** *before* compile (`go mod download`; `dotnet restore`; gradle resolves on compile; TS `npm install`+`prisma generate`) — a separate concern from the compile invocation. | **FR-2 adds a distinct provisioning capability**; the gate is provision-then-compile, not a single command. |
| Run the compiler at `project_root` (like `tsc -p project_root`) | `go build ./...`/`go test ./...` require `go.mod` **at cwd**, which `go.py:43-44` notes may live in a **subdirectory** (multi-module). Java/C# similarly key off the nearest `build.gradle`/`pom.xml`/`.csproj`. | **FR-7 adds build-root location**; the gate runs from the build root, not necessarily `project_root`. |
| Compile-only is obviously better than running tests | `test_command` **already compiles** (`go test`/`gradle test`/`dotnet test`, e.g. `java.py:93`, `csharp.py:111`). The justification for a *separate* compile gate must be explicit: tests need fixtures/infra, fail for non-compile reasons, and are slower — compile-only isolates the cross-file *resolution* check and runs without test setup. | **Non-Requirement made explicit**; FR-4 framed as compile-only, complementary to (not replacing) build-on-test. |

**Resolved open questions (from planning):**
- **"Just reuse `test_command` for resolution?" → No.** Compile-only is faster, deterministic, and independent of test fixtures/infra. The gate complements build-on-test; it does not replace it.
- **"One bespoke gate per language?" → No.** Unify under one `compile_check_command` capability + one gate runner dispatching by resolved language (mirrors RUN-008 OQ-6 / R3 distillation — don't build N inheritance/gate implementations). The existing `ts_toolchain` is retrofit as the TS implementation.
- **Provisioning host → reuse RUN-008 OQ-3.** Pipeline-owned gate after every batch (incl. terminal), `cap-dev-pipe` provisions the toolchain. Same decision, same place.

---

## 0.1 CRP Triage (v0.3)

> A 2-round Convergent Review (Appendix C) surfaced 14 F-suggestions (+ 14 mirrored S-suggestions in the plan), all code-anchored. Triage: **13 accepted, 1 narrowed** (R1-F1 — see Appendix B). The review materially corrected the v0.2 design; the headline change dissolves the v0.2 "atomic rollout" risk entirely.

| ID | Disp. | Change made |
|----|-------|-------------|
| R1-F1 | **NARROWED** | Members are **OPTIONAL**, read via `getattr(profile, "compile_check_command", None)` — **not** a required Protocol member. This avoids breaking third-party entry-point profiles (`registry.py:114-119` `isinstance` `TypeError`) **and dissolves the atomic-7-profile co-land risk** (FR-1 rewritten; supersedes §0 row 1). |
| R1-F2 | ACCEPTED | FR-9 names the frozen no-regression suite (`test_ts_toolchain.py`) and forbids changing `verdict` literals. |
| R1-F3 | ACCEPTED | FR-5 + FR-6: `unavailable` → reduced-confidence advisory note, **never** `success=False`/`disk_quality_score=0`/`CROSS_FILE_CONTRACT` (those are `fail`-only). |
| R1-F4 | ACCEPTED | FR-4 + FR-7: group `generated_files` by build root, run once per root, aggregate verdicts (any `fail`→fail; any `unavailable`&no-fail→unavailable; else pass). |
| R1-F5 | ACCEPTED | FR-7: upward search stops at `project_root` / first `.git`; no in-project build file → `unavailable`, never an ancestor outside the project. |
| R1-F6 | ACCEPTED | FR-6: normalize diagnostic paths to **build-root-relative** before feature attribution. |
| R2-F1 | ACCEPTED | FR-2: provisioning **once per build-root per run** (idempotent), keyed on `go.sum`/`gradle.lockfile`/`packages.lock.json`; do not copy the per-batch `npm ci`. Resolves OQ-4. |
| R2-F2 | ACCEPTED | FR-3: capture stdout **and** stderr separately + a per-language genuine-error sentinel (Go `\.go:\d+:\d+:`, javac `error:`, Roslyn `error CS\d+`); no `stdout or stderr` OR-fallback. |
| R2-F3 | ACCEPTED | FR-6: attribute by build-root-relative path, **not basename** (the merged `_evaluate_ts_toolchain` basename keying `prime_postmortem.py:1738,1767` is a latent collision bug → fix in the retrofit). |
| R2-F4 | ACCEPTED | §0 row 4 + Non-Req corrected: "test_command already compiles" is **false for Go** (`go.py:54` → `None`, fully additive) and only partial for Java/C#. |
| R2-F5 | ACCEPTED | FR-5: legitimately-unresolvable external deps (private feed / GOPRIVATE / offline `dotnet restore`) → `unavailable`, not `fail` (avoids false FAIL poisoning Kaizen). |
| R2-F6 | ACCEPTED | FR-4 + FR-6: document the C# `dotnet build --no-restore` (gate) ↔ `dotnet test --no-build` (checkpoint, `csharp.py:111`) artifact-ordering hazard; gate isolates its build dir. |
| R2-F7 | ACCEPTED | FR-4 + FR-7: **mixed-language batches** — `resolve_language()` returns the dominant profile, so dispatch the gate **per compiled language present**, not once globally (else minority-language breakage is a false PASS). |
| R2-F8 | ACCEPTED | FR-8: add a **false-PASS / build-root-pollution** fixture (a broken cross-feature ref that resolves only via a stray pre-existing file) — the exact run-008 verify-blind mode. |

---

## 1. Problem Statement

For the compiled languages (Go, Java, C#), the SDK has **no project-level compile check that is decoupled from test execution**. Per-file validation is syntax-only and cannot resolve cross-file/imports; the only cross-file resolution is a side effect of the checkpoint running `test_command`, which requires both a provisioned toolchain and runnable tests. So a multi-feature compiled-language batch generated without a provisioned toolchain (the run-008 condition) can ship cross-file-incoherent code — a caller invoking a sibling with the wrong signature, an `import`/`using` of a package/class/namespace another feature named differently — and **no gate catches it**. This is the verify-blind failure mode RUN-008 closed for TypeScript, now generalized to the compiled languages.

| Language | Per-file validator | Resolution today | Gap |
|----------|--------------------|------------------|-----|
| **Go** | `gofmt -e` temp file (`go.py:253`) — syntax only | only via `go test ./...` (`go.py:54`) when run + provisioned | no compile-only gate; silent when unprovisioned |
| **Java** | javalang AST (`java.py:523`); `syntax_check_command=None` | only via `gradle test` (`java.py:93`) when run + provisioned | same |
| **C#** | tree-sitter (`csharp.py:370`); `syntax_check_command=None` | only via `dotnet test --no-build` (`csharp.py:111`) when run + provisioned | same |
| **TypeScript** | `tsc --noEmit` temp file (per-file, syntax) | **project gate done** (`ts_toolchain.py`, RUN-008 FR-4) | — (retrofit into the unified abstraction) |

---

## 2. Requirements

### Group A — Unified compile-check capability (the abstraction)

#### FR-1 — `compile_check_command` as an OPTIONAL profile capability *(narrowed v0.3, R1-F1)*
Expose a project-level `compile_check_command` (distinct from the per-file `syntax_check_command`). **It MUST be an optional capability, NOT a required `@runtime_checkable` Protocol member** — the gate reads it via `getattr(profile, "compile_check_command", None)`. This is the load-bearing v0.3 correction: adding a *required* Protocol member would make `registry.register()`'s `isinstance` check (`registry.py:76`) raise `TypeError` for **third-party `startd8.languages` entry-point profiles** (`registry.py:114-119`) that this repo cannot co-land — and it dissolves the v0.2 "atomic 7-profile co-land" risk (only the compiled profiles need editing; others simply don't define it). The Protocol MAY document it as an optional member for discoverability.
Values (compiled profiles + TS define it; others leave it absent → `getattr` yields `None`):
- **Go:** `["go", "build", "./..."]`
- **Java:** `["gradle", "compileJava"]` (or `["gradle", "classes"]`; Maven `["mvn", "-q", "compile"]` when `pom.xml` — see OQ-2)
- **C#:** `["dotnet", "build", "--no-restore", "-clp:NoSummary"]`
- **TypeScript:** `["tsc", "--noEmit", "-p", "{build_root}"]` (retrofit of the existing gate)
- **Python / Prisma / Vue / Node-non-TS:** absent → `None` (no compile gate).
*Acceptance:* a profile **without** the capability (incl. a stub third-party profile) still registers — no `isinstance`/`TypeError` regression; `getattr(profile, "compile_check_command", None)` returns the correct value for go/java/csharp/ts and `None` otherwise; a registry round-trip test (`clear(); discover()`) asserts per-profile expected values (R1-S2).

#### FR-2 — Provisioning capability (`compile_provision_commands`)
Add a `compile_provision_commands` property returning the ordered commands that must succeed *before* `compile_check_command` resolves cross-file deps:
- **Go:** `[["go", "mod", "download"]]`
- **C#:** `[["dotnet", "restore"]]`
- **Java:** `[]` (gradle resolves dependencies during `compileJava`)
- **TypeScript:** `[["npm", "ci"]` or `["npm","install"]`, `["npx","prisma","generate"]]` (lockfile-aware; the existing `ts-verify-gate.py` logic)
- **Python / Prisma / Vue:** `[]`
Provisioning failure that prevents compilation MUST surface as `unavailable` (FR-5), not as a compile `fail`.
**Idempotence/caching (v0.3, R2-F1 — resolves OQ-4):** provisioning runs **once per build-root per run** (skip-if-already-provisioned, or keyed on `go.sum`/`gradle.lockfile`/`packages.lock.json`) — it MUST NOT copy the per-batch `npm ci` of `ts-verify-gate.py:73-80`, which on slower `dotnet restore`/Gradle-daemon toolchains would dominate run wall-clock.
*Acceptance:* the gate runs provisioning before compile; two batches on the same build root in one run → provisioning executes once (cache hit on the second); a missing toolchain yields `unavailable`.

#### FR-3 — Per-language compile-diagnostic parsing
Compiler output formats differ; the gate MUST parse each into a structured `CompileDiagnostic{file, line, col, code, message}` (mirroring `ts_toolchain.TscDiagnostic`):
- **Go:** `path/file.go:LINE:COL: message`
- **Java (javac via gradle):** `path/File.java:LINE: error: message`
- **C# (Roslyn via dotnet):** `path/File.cs(LINE,COL): error CSxxxx: message`
- **TypeScript:** existing `parse_tsc_output`.
Parsing MUST tolerate the build tool's wrapper noise (gradle/dotnet banners, progress) and extract only genuine compiler errors. **(v0.3, R2-F2):** the runner MUST capture **stdout and stderr separately and scan both** — NOT the `stdout or stderr` OR-fallback of `ts_toolchain.py:168`, which picks one stream and can miss diagnostics gradle/MSBuild split across streams (→ false PASS) — and each parser MUST gate on a per-language genuine-error sentinel (Go `\.go:\d+:\d+:`, javac `error:`, Roslyn `error CS\d+`), mirroring `_is_real_tsc_output`, before declaring `fail` vs `unavailable`.
*Acceptance:* fixture compiler outputs per language parse to the correct diagnostics; a gradle banner + `error:` on the same stream → only the diagnostic is extracted; banner/progress-only output → not a false `fail`.

### Group B — The unified gate runner + integration

#### FR-4 — Gate runner: per-build-root, per-language, compile-only *(expanded v0.3, R1-F4/R2-F7/R2-F6)*
`run_compile_gate(project_root, generated_files)` → `CompileGateResult{status, diagnostics, verdict: pass|fail|unavailable}` that: (a) groups `generated_files` by resolved build root (FR-7) **and by compiled language present**, (b) for each (build-root, language) unit runs `compile_provision_commands` then `compile_check_command` (read via `getattr`, FR-1) and parses output (FR-3), and (c) **aggregates verdicts** — any `fail`→`fail`; any `unavailable` with no `fail`→`unavailable`; else `pass`. It MUST dispatch **per compiled language present** (not once on the dominant profile from `resolve_language()`), or a minority language's breakage is a false PASS (R2-F7). It is **compile-only** — it MUST NOT run `test_command`. The existing `ts_toolchain.run_project_typecheck` becomes the TS implementation behind this runner (FR-9). **C# ordering (R2-F6):** the gate's `dotnet build --no-restore` MUST isolate its build output so it does not collide with the checkpoint's later `dotnet test --no-build` (`csharp.py:111`) — define the gate's build dir or document it does not share artifacts.
*Acceptance:* a coherent project → `pass`; a cross-file-incoherent one → `fail`; a two-build-root batch (one broken) → aggregate `fail` attributed to the broken root; a Go+C# batch with broken C# minority → `fail` (not a dominant-Go PASS); TS behavior unchanged.

#### FR-5 — Loud degradation + `unavailable` ≠ `fail` *(expanded v0.3, R1-F3/R2-F5/R2-S7)*
When the build toolchain (`go`/`gradle`/`mvn`/`dotnet`), the build file, dependency provisioning, **or a legitimately-unresolvable external dependency** (private feed, `GOPRIVATE`, offline `dotnet restore`) prevents compilation, the result MUST be `verdict=unavailable` — **non-pass, but distinct from `fail`** (a `fail` is reserved for genuine compile errors in generated code). A provisioning/compile **timeout** is also `unavailable` (sized for cold `dotnet restore`/Gradle daemon, larger than the TS 180s/600s defaults), not `fail`. The postmortem (FR-6) MUST record `unavailable` as a **reduced-confidence advisory note** — NOT `success=False`, NOT `disk_quality_score=0`, NOT a `CROSS_FILE_CONTRACT` Kaizen suggestion (those would poison Kaizen failure-pattern trends with infra noise). A note records which step was unavailable.
*Acceptance:* missing toolchain / missing build file / unreachable dep feed / timeout → `unavailable` (not pass, not fail); postmortem fixture with an `unavailable` result → `success` unchanged, no `disk_quality_score=0`, no `CROSS_FILE_CONTRACT` suggestion.

#### FR-6 — Pipeline + postmortem integration; relative-path attribution *(expanded v0.3, R1-F6/R2-F3)*
- **cap-dev-pipe:** generalize `ts-verify-gate.py` → a language-dispatching `verify-gate.py` that resolves the project language(s) and runs `run_compile_gate`. Same toggles (`STARTD8_*_GATE_STRICT`, `*_VERIFY_GATE=0`), same skip-when-absent behavior. Runs after every batch incl. the terminal one (RUN-008 OQ-3).
- **in-process:** generalize `_evaluate_ts_toolchain` → `_evaluate_compile_gate` in `prime_postmortem.py`. On `fail`: force FAIL (`disk_quality_score=0`, `success=False`, `root_cause=CROSS_FILE_CONTRACT`, `pipeline_stage=CROSS_FEATURE_CONTRACT`) + ≥1 Kaizen suggestion. On `unavailable`: advisory note only (FR-5). Diagnostics MUST be attributed to features by **build-root-relative path, NOT basename** — the merged `_evaluate_ts_toolchain` keys on `Path(fp).name` (`prime_postmortem.py:1738,1767`), which collides duplicate basenames (`main.go`/`Program.cs`) across modules; the retrofit MUST fix this (R2-F3). Env-gated per language.
*Acceptance:* a compiled-language batch with a cross-file error → gate FAIL + correct per-feature attribution even with duplicate basenames across build roots; an `unavailable` batch → advisory note, no FAIL; a Python batch unaffected.

#### FR-7 — Build-root location (multi-root, bounded) *(expanded v0.3, R1-F4/R1-F5)*
The gate MUST locate the build root by searching upward from each generated file for the nearest build file (`go.mod`, `build.gradle`/`build.gradle.kts`/`pom.xml`, `*.csproj`/`*.sln`) and run provisioning/compile from there — not assume `project_root`. The upward search MUST be **bounded**: stop at `project_root` (or the first `.git` boundary); if no in-project build file is found, the unit is `unavailable` — never select an ancestor build file **outside** the project. A batch spanning **multiple** build roots is grouped and gated per root (FR-4 aggregation).
*Acceptance:* `go.mod` in a subdir → gate runs from that subdir; two build roots → two gate runs aggregated; a generated file with no in-project build file → search stops at `project_root`, returns `unavailable` (not an ancestor outside the project).

### Group C — Cross-cutting

#### FR-8 — Regression fixtures per language *(expanded v0.3, R2-F8)*
Tests MUST include, per language: (a) a coherent multi-file project that compiles → `pass`; (b) a cross-file-incoherent project that the per-file syntax check passes but compilation rejects → `fail` (Go: caller with wrong arg count / undefined symbol from a sibling; Java: `import` of a class no feature defines / wrong method signature; C#: `using`/type from a missing namespace, CS0246); (c) a toolchain-absent case → `unavailable`; and **(d) a false-PASS / build-root-pollution fixture** — a broken cross-feature reference that resolves *only* via a stray pre-existing (ungenerated) file, asserting the gate isolates the build root and still surfaces the incoherence (the exact run-008 verify-blind mode). Diagnostic parsers tested from captured fixture output without invoking the real toolchain (the subprocess path behind a toolchain-available guard).

#### FR-9 — TypeScript retrofit (no regression) *(tightened v0.3, R1-F2/OQ-5)*
The existing merged TS gate MUST be preserved behaviorally when refactored behind the unified abstraction. Commit to the **alias** retrofit: `CompileGateResult` is `ToolchainResult` (or attribute-compatible — same `.verdict`/`.diagnostics`/`.is_pass`), and the `verdict` string literals (`pass`/`fail`/`unavailable`) MUST NOT change. *Acceptance (executable):* `tests/unit/validators/test_ts_toolchain.py` and the cap-dev-pipe gate behavior pass **unmodified** post-retrofit; a grep guard asserts the verdict literals are unchanged.

---

## 3. Non-Requirements
- **Does NOT run tests.** Compile-only. Test execution remains the checkpoint's separate concern; this gate is the resolution check decoupled from it.
- **Does NOT replace build-on-test** — *and the relationship is language-asymmetric (v0.3, R2-F4; corrects §0 row 4's blanket "test_command already compiles"):* **Go** `test_command` is `None` (`go.py:54`), so the gate is **fully additive** (no double-compile, no existing test-driven resolution). **Java/C#** tests *do* compile (`java.py:93`, `csharp.py:111`), so the gate is the *decoupled, fixture-free, earlier* resolution check that also runs when tests don't. The gate never replaces tests; it guarantees the compile/resolution check independent of test execution.
- **Does NOT add languages beyond Go/Java/C#** (+ the TS retrofit). Python has no compile gate; Vue script blocks ride the TS path; other languages remain out of scope until a run reproduces a defect.
- **Does NOT do per-feature incremental compilation.** One whole-project compile per batch (cheapest correct unit; matches the compiler's whole-program nature).
- **Does NOT introduce a new provisioning host decision** — reuses RUN-008 OQ-3 (pipeline-owned gate, cap-dev-pipe provisions).

---

## 4. Open Questions (for CRP / implementation)
- **OQ-1 — build-root heuristic.** Nearest-ancestor build file from each generated file vs a single project-wide scan; multi-module Go / multi-project Gradle / multi-`.csproj` solutions — run once per build root or once per project? Bound the scan.
- **OQ-2 — Java build-system detection.** `gradle compileJava` vs `gradle classes` vs Maven `mvn compile` — detect from `build.gradle*` vs `pom.xml`; handle Gradle wrapper (`./gradlew`) presence. Which is the canonical compile-only target?
- **OQ-3 — diagnostic-parse fidelity & attribution.** Gradle/dotnet wrap compiler output (daemon banners, MSBuild summary); regexes must be robust. Per-feature attribution relies on the diagnostic's file path resolving to a feature's `generated_files` — confirm reliability across build tools (relative vs absolute paths).
- **OQ-4 — provisioning cost & caching.** `dotnet restore`, gradle dependency resolution, and the Gradle daemon are slow. Cache strategy analogous to the TS `npm ci` lockfile cache (keyed on `go.sum`/`gradle.lockfile`/`packages.lock.json`)? Acceptable per-batch wall-clock?
- **OQ-5 — unified result type.** One `CompileGateResult` shared with TS (rename/alias `ToolchainResult`) vs a thin adapter — pick the lower-churn retrofit that keeps the merged TS tests green (FR-9).
- **OQ-6 — strictness default.** Match the TS gate (informational by default, `*_GATE_STRICT` to fail the pipeline) — confirm the compiled-language default is also informational to avoid disrupting existing flows.

---

## 5. Implementation Plan
A companion plan lives at **`docs/design/COMPILE_GATE_PLAN.md`** (mirrors the RUN-008 plan structure: build-root + capability first, per-language compile/parse, gate runner, TS retrofit, integration, regression).

---

## Appendix A — Accepted Suggestions

> Triaged 2026-06-01 (v0.3). Full disposition + merge targets in **§0.1 CRP Triage**. Round history preserved in Appendix C (cross-model memory — do not strip).

| ID | Merged into |
|----|-------------|
| R1-F2 | FR-9 (named frozen suite + verdict-literal lock) |
| R1-F3 | FR-5 + FR-6 (`unavailable` advisory, not `fail`) |
| R1-F4 | FR-4 + FR-7 (multi-root group + verdict aggregation) |
| R1-F5 | FR-7 (bounded upward search; stop at project_root/.git) |
| R1-F6 | FR-6 (build-root-relative path attribution) |
| R2-F1 | FR-2 (provision once per build-root per run; cache key) |
| R2-F2 | FR-3 (per-stream capture + per-language error sentinel) |
| R2-F3 | FR-6 (relative-path, not basename — fix the merged TS attribution) |
| R2-F4 | §0 row 4 + Non-Requirements (Go-vs-Java/C# asymmetry) |
| R2-F5 | FR-5 (unresolvable external deps / timeout → `unavailable`) |
| R2-F6 | FR-4 + FR-6 (C# `--no-build` artifact-ordering isolation) |
| R2-F7 | FR-4 + FR-7 (per-language dispatch; no dominant-profile false PASS) |
| R2-F8 | FR-8 (false-PASS / build-root-pollution fixture) |

*(S-suggestions R1-S1..R1-S7 / R2-S1..R2-S7 are the plan-side mirrors — triaged in `COMPILE_GATE_PLAN.md` Appendix A.)*

## Appendix B — Rejected / Narrowed Suggestions (with rationale)

| ID | Disposition | Rationale |
|----|-------------|-----------|
| R1-F1 | **NARROWED** | Proposed deciding *required* vs *optional* members. Resolved toward **OPTIONAL** (`getattr(profile, "compile_check_command", None)`) rather than a required `@runtime_checkable` member: required would `TypeError` third-party entry-point profiles (`registry.py:114-119`) the repo can't co-land, and would impose the v0.2 atomic-7-profile rollout. The optional path is strictly safer (no breaking change, no atomic constraint) and only the compiled profiles need editing. FR-1 rewritten accordingly; supersedes §0 row 1's "all 7 at once" framing. |

## Appendix C — Incoming Suggestions (Untriaged, append-only)
*(CRP review rounds append here)*

#### Review Round R1 — claude-opus-4-8 — 2026-06-01

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-01 00:00:00 UTC
- **Scope**: Requirements review (FR-1..FR-9) weighted to focus asks #1 (atomic Protocol rollout / isinstance / 3rd-party entry-point profiles), #3 (build-root across multi-* layouts), #4 (TS retrofit no-regression), #6 (FR-5 loud-degradation parity). Anchored against `languages/protocol.py`, `registry.py`, `go.py`, `java.py`, `csharp.py`, `validators/ts_toolchain.py`, `cap-dev-pipe/ts-verify-gate.py`, `contractors/prime_postmortem.py`.

##### Focus-file asks (answered before standard suggestions)

**Ask #1 — Atomic Protocol-member rollout vs optional members; third-party profiles.**
- **Summary answer:** Partial — atomic co-land is correct for the *5 in-tree* profiles, but the requirement is silent on third-party entry-point profiles, which it will break.
- **Rationale:** `registry.py:76` does `isinstance(profile, LanguageProfile)` and the Protocol is `@runtime_checkable` (`protocol.py:14`), so adding two required members breaks `isinstance` for *any* registered profile lacking them — including externally-shipped profiles loaded at `registry.py:114-119` that this repo cannot co-land. `@runtime_checkable` only checks attribute *presence* (methods/props), so a class missing `compile_check_command` fails registration with the `TypeError` at `registry.py:77`. FR-1's "all 7 profiles" scope is in-tree only.
- **Assumptions / conditions:** A third-party `startd8.languages` entry point exists in some downstream env. The 9-repo downstream consumer set (per MEMORY) raises this likelihood.
- **Suggested improvements:** Decide and state in FR-1 whether the two members are *required* (Protocol breaking change → bump SDK minor, document in `DOWNSTREAM_WORKAROUND_CATALOG.md`) or *optional* (registry reads via `getattr(profile, "compile_check_command", None)` so legacy/3rd-party profiles still register). See R1-F1.

**Ask #3 — Build-root location across multi-module / multi-project / multi-csproj.**
- **Summary answer:** Partial — FR-7 defines *upward* search to the nearest build file but does not define behavior when generated files span *multiple* build roots in one batch.
- **Rationale:** FR-7 acceptance ("go.mod in a subdirectory → run from that subdirectory") assumes one build root. Multi-module Go, multi-project Gradle, and multiple `.csproj`/`.sln` (`csharp.py:97` patterns `["*.csproj","*.sln"]`) can yield N distinct roots from one batch's `generated_files`. OQ-1 raises "once per build root or once per project" but no FR resolves it, leaving FR-4's `run_compile_gate(project_root, profile)` single-root signature ambiguous.
- **Assumptions / conditions:** Batches can write files into more than one module/project (online-boutique-style multi-service repos make this the norm, not the edge).
- **Suggested improvements:** FR-7 must specify: group generated files by resolved build root, run the gate once per distinct root, and aggregate verdicts (any `fail`→fail, any `unavailable` with no fail→unavailable). Define the upward-search stop boundary (project_root or VCS root). See R1-F4 and R1-F5.

**Ask #4 — TS retrofit without regression.**
- **Summary answer:** Yes, achievable — and the *alias* path (OQ-5) is lower-churn than a shared rewrite.
- **Rationale:** `ts_toolchain.ToolchainResult` already exposes the exact `verdict` contract (`ts_toolchain.py:62-66`) the new `CompileGateResult` needs (`pass|fail|unavailable`). `ts-verify-gate.py:93,104` and `_evaluate_ts_toolchain` (`prime_postmortem.py:1706,1742`) consume `.verdict`/`.diagnostics`, so preserving those attribute names keeps both green. FR-9 says "refactor not rewrite" but gives no *executable* no-regression criterion.
- **Assumptions / conditions:** `CompileGateResult` keeps `.verdict`, `.diagnostics`, `.is_pass` attribute-compatible with `ToolchainResult`.
- **Suggested improvements:** FR-9 acceptance must name the exact frozen test set (`test_ts_toolchain.py`) that must pass *unmodified*, and forbid changing `verdict` string values. See R1-F2.

**Ask #6 — FR-5 loud-degradation parity with RUN-008 FR-9.**
- **Summary answer:** Partial — FR-5 states the `unavailable` contract but does not require the postmortem to treat `unavailable` *distinctly from* `fail`.
- **Rationale:** Focus ask #6 demands `unavailable` (infra) ≠ `fail` (code fault) in the postmortem. FR-6 only specifies the FAIL path (`disk_quality_score=0`, `root_cause=CROSS_FILE_CONTRACT`); it is silent on what the postmortem records for `unavailable`. The existing TS gate distinguishes them at `ts-verify-gate.py:104` (separate `unavailable` branch) but `_evaluate_ts_toolchain` behavior on `unavailable` is unstated in this doc.
- **Assumptions / conditions:** Postmortem must not score an `unavailable` batch as a code fault (would corrupt Kaizen failure-pattern trends).
- **Suggested improvements:** FR-5/FR-6 must require `unavailable` → reduced-confidence advisory note, NOT `success=False`/`disk_quality_score=0`, and NOT a `CROSS_FILE_CONTRACT` Kaizen suggestion. See R1-F3.

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | FR-1 must explicitly resolve third-party entry-point profiles: either declare the two members REQUIRED (a breaking Protocol change — bump SDK minor + catalog entry) or OPTIONAL (registry reads via `getattr(..., None)`). State which, and why. | FR-1 only enumerates the 7 in-tree profiles, but `registry.py:114-119` loads external `startd8.languages` profiles whose authors cannot co-land; `isinstance` at `registry.py:76` will `TypeError` them. The doc currently has a silent breaking-change gap. | FR-1, after the "all 7 registered profiles MUST implement it" sentence | Register a stub external profile (no compile members) and assert either documented `TypeError` (required path) or successful registration (optional path) — matching whichever FR-1 declares. |
| R1-F2 | Validation | high | FR-9 acceptance must name the frozen no-regression test set verbatim (`tests/.../test_ts_toolchain.py` + cap-dev-pipe gate test) that MUST pass unmodified, and forbid changing `ToolchainResult.verdict` string values (`pass`/`fail`/`unavailable`). | FR-9 says "tests MUST stay green" but cites no concrete suite; the contract is enforced by `ts_toolchain.py:62-66` verdict strings that `ts-verify-gate.py:104` branches on. Without naming them, "no regression" is untestable. | FR-9, replace the closing sentence with a named acceptance criterion | CI job runs the named test file with `--no-modify` diff guard; grep asserts verdict literals unchanged. |
| R1-F3 | Risks | high | FR-5 must require that `unavailable` is recorded by the postmortem as an infra/reduced-confidence note — NOT `success=False`, `disk_quality_score=0`, or a `CROSS_FILE_CONTRACT` Kaizen suggestion (those are reserved for genuine compile `fail`). | Focus ask #6: infra-absent must not masquerade as a code fault. FR-6 (`prime_postmortem.py:1697` sets `CROSS_FILE_CONTRACT` on FAIL) describes only the fail path; conflating `unavailable` with `fail` would poison Kaizen failure-pattern trends with infra noise. | New sentence in FR-5; cross-ref in FR-6 | Postmortem fixture: feed an `unavailable` `CompileGateResult` → assert `success` unchanged, no `disk_quality_score=0`, no `CROSS_FILE_CONTRACT` suggestion emitted. |
| R1-F4 | Architecture | high | FR-7 must define multi-root batch behavior: group `generated_files` by resolved build root, run the gate once per distinct root, and define verdict aggregation (any fail→fail; any unavailable & no fail→unavailable; else pass). | FR-7 + OQ-1 acknowledge multi-module Go / multi-project Gradle / multi-`.csproj` but no FR resolves how `run_compile_gate(project_root, ...)` (single signature, FR-4) handles N roots. Online-boutique-style multi-service batches make this the common case. | FR-7, add a "Multi-root batches" paragraph; promote OQ-1 to a decided requirement | Fixture with two `go.mod` subdirs, one coherent + one broken → aggregate verdict `fail` with diagnostics attributed to the right root. |
| R1-F5 | Risks | medium | FR-7 must bound the upward build-file search with an explicit stop boundary (stop at `project_root`, or at the first VCS/`.git` boundary) to prevent escaping into host filesystem build files. | FR-7 says "searching upward ... for the nearest build file" with no terminus; on a dev host a stray ancestor `go.mod`/`*.sln` could be selected, running the gate outside the project. OQ-1 says "bound the scan" but the FR leaves it unbounded. | FR-7, add stop-condition clause | Unit: generated file under project_root with no in-project build file → search stops at project_root and returns None (→ `unavailable`), never an ancestor outside it. |
| R1-F6 | Validation | medium | FR-3/OQ-3 must require diagnostic `file` paths be normalized to the build root (relative) before feature attribution, since Go emits build-root-relative paths, gradle/dotnet may emit absolute paths, and `diagnostics_by_file` (`ts_toolchain.py:181`) keys on raw path. | Per-feature attribution (FR-6) joins diagnostic paths to `generated_files`; mixed relative/absolute paths across toolchains (OQ-3) will silently miss matches, dropping real failures into "unattributed". The TS grouper normalizes via `Path(...).as_posix()` only — not relative-to-root. | FR-3 acceptance + OQ-3 | Fixture: absolute-path C# diagnostic + relative-path Go diagnostic → both resolve to the correct `generated_files` entry after normalization. |

**Endorsements**: none (Appendix C had no prior untriaged rounds — R1 is the first).

#### Review Round R2 — claude-opus-4-8 — 2026-06-01

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-01 00:00:00 UTC
- **Scope**: ADVERSARIAL stress-test + data/ops lens. Weighted to focus asks #2 (provisioning cost/caching + diagnostic-parse fidelity across gradle/dotnet/MSBuild wrapper noise + per-feature file-path attribution relative-vs-absolute) and #5 (compile-only vs build-on-test redundancy / double-compile / strictness default). Builds on R1 (do not re-propose R1-F1..F6). Anchored against `validators/ts_toolchain.py`, `cap-dev-pipe/ts-verify-gate.py`, `contractors/prime_postmortem.py:_evaluate_ts_toolchain`, `go.py`, `java.py`, `csharp.py`, `contractors/checkpoint.py`.

##### Focus-file asks (answered before standard suggestions)

**Ask #2 — Provisioning cost/caching + diagnostic-parse fidelity + relative-vs-absolute attribution.**
- **Summary answer:** Partial/No on all three sub-parts — caching is wholly unaddressed (OQ-4 is open, no FR), parse fidelity is under-specified for stream selection, and the *existing* attribution code (`_evaluate_ts_toolchain`) keys on **basename only**, which the generalized doc inherits as a latent false-attribution bug.
- **Rationale:** (a) *Caching:* `ts-verify-gate.py:73-80` runs `npm ci`/`npm install` **every batch** with a 600s timeout and no cache reuse; generalizing to `dotnet restore` + gradle resolution + the stateful Gradle daemon multiplies this cost per-batch. OQ-4 raises it but no FR commits a cache key or a "provision-once-per-run" contract. (b) *Stream/noise:* `ts_toolchain.py:168` selects output via `result.stdout.strip() or result.stderr.strip()` — an OR-fallback that picks **one** stream. gradle writes diagnostics to stdout interleaved with daemon banners and MSBuild writes a summary; `_is_real_tsc_output` (`ts_toolchain.py:90-92`) guards TS but FR-3 has no equivalent "genuine-error sentinel" per language. (c) *Attribution:* `_evaluate_ts_toolchain` builds `path_to_feature` keyed on `Path(fp).name` (`prime_postmortem.py:1738`) and looks up by `Path(file_key).name` (`:1767`) — **basename**, so two `main.go`/`Program.cs` in different modules collide and misattribute. R1-F6 raised relative-vs-absolute normalization but not the basename-collision class.
- **Assumptions / conditions:** Multi-service batches contain duplicate basenames (online-boutique: `main.go` per service). Provisioning dominates per-batch wall-clock for Java/C#.
- **Suggested improvements:** FR-2 must state a caching/idempotence contract (provision once per build-root per run, or key on `go.sum`/`gradle.lockfile`/`packages.lock.json`); FR-3 must require per-stream capture (not OR-fallback) + a per-language genuine-error sentinel; FR-6/OQ-3 must require **build-root-relative path** attribution (not basename) to defeat duplicate-basename collisions. See R2-F1, R2-F2, R2-F3.

**Ask #5 — Compile-only vs build-on-test; double-compile; strictness default.**
- **Summary answer:** Yes, genuinely additive — but the redundancy/double-compile profile is **language-asymmetric** and the doc treats it uniformly, which is wrong.
- **Rationale:** Go `test_command` returns **`None`** (`go.py:54-58`, "Disable until checkpoint supports per-service cwd"), so for Go there is **no** existing test-driven compile — the gate is purely additive, zero double-compile. Java is `["gradle","test"]` (`java.py:93`) and C# is `["dotnet","test","--no-build"]` (`csharp.py:111`) which the checkpoint **does** run from project_root (`checkpoint.py:1051,1063`). So: for Java/C#, the compile gate's `gradle compileJava`/`dotnet build` *does* duplicate compile work the test run also does — but critically, C#'s `--no-build` test **assumes a prior build exists**; if the gate's `dotnet build --no-restore` and the checkpoint's `dotnet test --no-build` interact, ordering matters (stale or missing build → test fails for non-compile reasons). The doc's blanket "test_command already compiles" (§0 row 4) is false for Go and incomplete for C#. Strictness default: FR-5/OQ-6 correctly inherit the TS gate's informational default (`ts-verify-gate.py:34-37`).
- **Assumptions / conditions:** Checkpoint runs `test_command` before the pipeline-owned compile gate (gate runs "after every batch", FR-6).
- **Suggested improvements:** §0 row 4 / Non-Requirements must record the per-language asymmetry (Go: no test compile, fully additive; Java/C#: test compiles too, gate is the *decoupled/earlier/test-fixture-free* resolution check) and FR-4/FR-6 must note the C# `--no-build` ordering hazard. See R2-F4, R2-F6.

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Ops | high | FR-2 must add a provisioning idempotence/caching contract: provision **once per build-root per run** (not per batch), and define the cache key per language (`go.sum`, `gradle.lockfile`/`~/.gradle`, `packages.lock.json`). State an acceptable per-batch wall-clock budget or a skip-if-already-provisioned check. | `ts-verify-gate.py:73-80` re-runs `npm ci`/`install` every batch (600s timeout, no reuse); adding `dotnet restore` + gradle resolution + a cold Gradle daemon per batch makes provisioning dominate run time. OQ-4 flags it but no FR commits a contract, so the implementer will copy the per-batch TS behavior by default. | FR-2, after the provisioning command list; resolve OQ-4 into FR-2 | Run two consecutive batches in one run on the same build root → assert provisioning executes once (cache hit on second), wall-clock of second batch's gate excludes restore. |
| R2-F2 | Data | high | FR-3 must require **per-stream capture** (capture stdout and stderr separately, scan both) and a per-language "genuine compiler error" sentinel (Go: `\.go:\d+:\d+:`; javac: `error:`; Roslyn: `error CS\d+`), mirroring `_is_real_tsc_output`. Forbid the `stdout or stderr` OR-fallback for the compiled langs. | `ts_toolchain.py:168` uses `result.stdout.strip() or result.stderr.strip()` — picks one stream. gradle/MSBuild interleave diagnostics with daemon banners/summary across both streams; an OR-fallback can select the banner stream and miss real errors (→ false PASS) or pick noise (→ unattributable `unavailable`). FR-3 says "tolerate wrapper noise" but specifies no mechanism. | FR-3 acceptance (after the format list) | Fixture: a gradle build that writes a daemon banner to stdout and `error:` to the same stream → parser extracts only the diagnostic; a dotnet build with errors in stdout + summary → no false unavailable. |
| R2-F3 | Data | high | FR-6/OQ-3 must require diagnostic→feature attribution by **build-root-relative path**, not basename. Two features owning same-named files (`main.go`, `Program.cs`, `index.ts`) in different modules will collide under basename keying. | The reference impl `_evaluate_ts_toolchain` keys `path_to_feature` on `Path(fp).name` (`prime_postmortem.py:1738`) and looks up `Path(file_key).name` (`:1767`) — pure basename. In a multi-service batch (the FR-7 multi-root norm) duplicate basenames misattribute or drop diagnostics, hiding real failures or blaming the wrong feature. Extends R1-F6 (relative-vs-absolute) with the collision class. | FR-6 acceptance + OQ-3; cross-ref R1-F6 | Fixture: two features each with a `main.go` in distinct `go.mod` dirs, one broken → diagnostic attributes to the correct feature, not both/neither. |
| R2-F4 | Risks | high | §0 row 4 ("test_command already compiles") and the Non-Requirements "Does NOT replace build-on-test" bullet must be corrected/qualified per-language: Go `test_command` is **`None`** (no test compile — gate fully additive); Java/C# tests do compile (gate is the decoupled, fixture-free, earlier check). | The doc's blanket claim is the load-bearing justification for compile-only, but it is **false for Go** (`go.py:54-58` returns `None`) and so the "redundant where tests already run?" worry (focus #5) does not apply to Go at all, and applies only partially to Java/C#. An implementer reading §0 may wrongly assume all three behave like Java. | §0 Planning Insights row 4; Non-Requirements bullet 2 | Doc check: assertion table per language (Go: additive; Java/C#: complementary-decoupled) matching the actual `test_command` values. |
| R2-F5 | Risks | medium | FR-5 must define behavior for a generated project with **legitimately unresolvable external deps** the gate cannot provision (private registry, network-isolated `dotnet restore`, a Go module behind GOPRIVATE). This is `unavailable` (provisioning failed), not `fail` — but FR-5 currently only enumerates missing-toolchain/missing-build-file as `unavailable`. | A generated multi-feature project can reference a real external package that restore/download can't fetch in the gate's environment; treating that compile failure as `fail` (code fault) is a **false FAIL** that poisons Kaizen. FR-5's `unavailable` triggers list omits "provisioning succeeded-partially / dep fetch failed". | FR-5, extend the `unavailable` trigger enumeration | Fixture: `dotnet restore` fails on an unreachable feed → verdict `unavailable` (not `fail`), reduced-confidence note names the unresolved dep. |
| R2-F6 | Architecture | medium | FR-4/FR-6 must note the C# ordering hazard: `csharp.py:111` test is `dotnet test --no-build` (assumes a prior build). If the compile gate runs `dotnet build --no-restore` and the checkpoint later runs `--no-build` tests, define which build artifact the test consumes, or the test may run against a stale/absent build. | `--no-build` couples the test to a build the gate may or may not have produced; "one whole-project compile per batch" (Non-Req) plus a separate `--no-build` test creates an implicit artifact dependency the doc never states. Risk: false test PASS/FAIL from stale `bin/`. | FR-4 (runner isolation note) + FR-6 (integration ordering) | Fixture: gate build then `dotnet test --no-build` → confirm the test compiles against the gate's output or document that the gate must not share build artifacts with the checkpoint. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F7 | Risks | high | FR-4/FR-7 must define behavior for a **mixed-language batch** (e.g. a Go service + a C# service in one batch). `resolve_language()` returns the *dominant* profile (CLAUDE.md), so a single-profile `run_compile_gate(project_root, profile)` will compile-gate only the majority language and silently skip the minority — a **false PASS** for the un-gated language. | The doc assumes one profile per batch; multi-service monorepos routinely mix languages. FR-4's single-`profile` signature cannot gate two toolchains, and the dominant-language fallback means the minority language's cross-file breakage ships unverified. | FR-4 + FR-7 (multi-root already raised in R1-F4; this adds multi-*language*) | Fixture: batch with Go + C# files, C# broken, Go majority → assert the gate detects the C# break (or documents per-language dispatch), not a global PASS. |
| R2-F8 | Validation | medium | FR-8 must add a **false-PASS regression fixture**: a project where the per-file syntax checks all pass AND the toolchain is present AND it compiles clean, but a feature references a symbol that only resolves due to an unrelated file the *batch did not generate* (pre-existing host file) — confirming the gate doesn't credit cross-file coherence to ungenerated context. | FR-8 enumerates coherent→pass / incoherent→fail / absent→unavailable but not the "accidentally passes because of pre-existing scaffolding" case, which is exactly how run-008 scored 0.99 (verify-blind). Without it, the gate's PASS could be an artifact of a polluted build root. | FR-8, add a fourth fixture class | Fixture: broken cross-feature reference made to resolve via a stray pre-existing file → assert the gate still surfaces the intended incoherence or the fixture isolates the build root. |

**Endorsements** (R1 untriaged items I agree with):
- R1-F1: third-party entry-point profile breakage is a real `isinstance` `TypeError` risk (`registry.py:76`); must be decided, not left silent.
- R1-F3: `unavailable` must not be scored as a code fault — directly supported by `_evaluate_ts_toolchain:1744-1758` already treating TS `unavailable` as a non-success warning; the generalized FR must preserve this.
- R1-F4: multi-root iteration + verdict aggregation is the common case for multi-service batches; the single-root signature is a genuine gap.
- R1-F6: relative-vs-absolute path normalization is necessary; R2-F3 extends it with the basename-collision class.

**Disagreements** (R1 untriaged):
- None. R1's six F-items are sound; R2 extends rather than contradicts them.


---

*v0.2 — Post-planning self-reflective update. 4 assumptions corrected, 3 open questions resolved at planning time. Scope: Go/Java/C# compile-gate + unified `compile_check_command` abstraction with TS retrofit; test execution out of scope.*

*v0.3 — Post-CRP triage (2-round Convergent Review, Appendix C). 14 F-suggestions: 13 accepted, 1 narrowed (R1-F1 → optional `getattr` capability, dissolving the atomic-rollout risk). Materially expanded FR-1 (optional member), FR-2 (provision caching), FR-3 (dual-stream + error sentinel), FR-4 (per-build-root + per-language dispatch + C# artifact isolation), FR-5 (`unavailable`≠`fail`, unresolvable-dep/timeout triggers), FR-6 (relative-path attribution), FR-7 (bounded multi-root), FR-8 (false-PASS fixture), FR-9 (alias retrofit + frozen tests); corrected §0 row 4 / Non-Req (Go-vs-Java/C# asymmetry). Dispositions in §0.1 + Appendix A/B.*
