# Generalized Compile-Gate (Go / Java / C#) — Implementation Plan

**Version:** 0.3 (Post-CRP — triage applied)
**Date:** 2026-06-01
**Status:** Draft (ready for implementation)
**Requirements:** `docs/design/COMPILE_GATE_REQUIREMENTS.md` (v0.3 — FR-1..FR-9)

Every FR maps to a step; every step traces to an FR. Ordered smallest-blast-radius-first. Mirrors the RUN-008 plan; the TS gate is the proven reference implementation being generalized.

---

## Steps

| # | Step | FR | Files | Verify |
|---|------|----|-------|--------|
| **0 ✅ DONE** | **Discovery** — protocol is `@runtime_checkable`; provisioning is distinct from compile; build-root ≠ project_root; `test_command` already compiles (Go: `None`). See requirements §0 + §0.1. | — | (read-only) | ✅ captured |
| **1** | **Optional capability (NON-atomic, v0.3/R1-S1).** Add `compile_check_command` + `compile_provision_commands` to the **compiled profiles only** (go/java/csharp) + the TS retrofit; the gate reads them via `getattr(profile, …, None)` — **NOT** a required `@runtime_checkable` member (would `TypeError` third-party entry-point profiles `registry.py:114-119`). No atomic co-land; non-compiled profiles need no edit. | FR-1, FR-2 | `languages/{go,java,csharp}.py`, optional `protocol.py` doc-only | **registry round-trip (R1-S2):** `clear(); discover()` → all profiles register incl. a stub external profile lacking the members; `getattr` returns correct value per lang, `None` otherwise |
| **2** | **Build-root locator (bounded, v0.3/R1-S4)** — search upward from each generated file for nearest `go.mod`/`build.gradle(.kts)`/`pom.xml`/`*.csproj`/`*.sln`/`tsconfig.json`; **stop at `project_root`/first `.git`** (no ancestor outside project). Group files → distinct roots. | FR-7 | `validators/compile_gate.py` (new) | unit: go.mod subdir → that subdir; no in-project build file → None/`unavailable` (not an ancestor); two roots → two groups |
| **3** | **Per-language parsers + dual-stream capture (v0.3/R2-S2)** — `parse_*_diagnostics(text)` for Go/Java/C# (reuse `parse_tsc_output` for TS); capture **stdout & stderr separately**, gate on a per-language error sentinel (Go `\.go:\d+:\d+:`, javac `error:`, Roslyn `error CS\d+`) — no `stdout or stderr` OR-fallback. | FR-3 | `validators/compile_gate.py` | unit: banner+`error:` on one stream → only diagnostic extracted; banner-only → not false `fail` |
| **4** | **Gate runner: per-root, per-language, aggregated (v0.3/R1-S3/R2-S4/R2-S5/R2-S7)** `run_compile_gate(project_root, generated_files)`: for each (build-root × compiled-language) group → provision (cached, R2-S1) → compile → parse; **aggregate** (any fail→fail; any unavailable&no-fail→unavailable; else pass). Per-language dispatch (not dominant-profile). C# build-dir isolated from checkpoint `--no-build`. Cold-toolchain timeouts → `unavailable`. | FR-4, FR-5 | `validators/compile_gate.py` | toolchain-gated: coherent→pass; incoherent→fail; two roots (one broken)→aggregate fail; Go+broken-C#→fail; absent/timeout→unavailable |
| **5** | **TS retrofit — alias (v0.3/R1-S5).** `CompileGateResult` ≡ `ToolchainResult` (shared `.verdict`/`.diagnostics`/`.is_pass`; verdict literals unchanged); `run_project_typecheck` becomes the TS impl behind `run_compile_gate`. Commit to alias (not rewrite). | FR-9 | `validators/ts_toolchain.py`, `validators/compile_gate.py` | `test_ts_toolchain.py` passes **unmodified**; grep guard on verdict literals |
| **6** | **Integration + relative-path attribution (v0.3/R2-S3/R1-S6).** Generalize `ts-verify-gate.py` → `verify-gate.py`; `_evaluate_ts_toolchain` → `_evaluate_compile_gate`: on `fail` hard-FAIL + Kaizen; on `unavailable` **advisory note only** (no `success=False`/`CROSS_FILE_CONTRACT`). Attribute by **build-root-relative path, not basename** (fixes `prime_postmortem.py:1738,1767`). | FR-6 | `cap-dev-pipe/verify-gate.py`, `run-prime-contractor.sh`, `contractors/prime_postmortem.py` | cross-file error→FAIL + correct attribution w/ duplicate basenames; `unavailable`→advisory, no FAIL; Python unaffected |
| **7** | **Regression fixtures (v0.3/R2-S6)** per language: coherent→pass; cross-file-broken→fail; toolchain-absent→unavailable; **+ false-PASS/build-root-pollution** (broken ref resolved only via a stray pre-existing file). Parsers tested from captured output without the real toolchain. | FR-8 | `tests/unit/validators/test_compile_gate.py` + fixtures | per-language pass/fail/unavailable + false-PASS isolation; direct-to-parser lock |

**Sequencing (v0.3 — atomic constraint removed):** the CRP narrowing of FR-1 to an **optional `getattr` capability** dissolves the v0.2 atomic-7-profile co-land — Step 1 now touches only the compiled profiles and cannot break registration (third-party profiles included). Order: Step 1 (capability) → Steps 2–4 (locator, parsers, runner) → Step 5 (TS alias retrofit, tests stay green) → Steps 6–7 (integration + fixtures). Step 4 depends on 2+3.

**Alignment:** reuses RUN-008 OQ-3 (pipeline-owned gate after every batch + cap-dev-pipe provisioning) and the postmortem `CROSS_FILE_CONTRACT`/`CROSS_FEATURE_CONTRACT` attribution already added for FR-10. One gate runner serves all four languages (RUN-008 OQ-6 / R3 distillation — no N bespoke gates).

---

## Step 0 — Discovery Findings
See `COMPILE_GATE_REQUIREMENTS.md` §0 + §0.1. Net: no blocker. The v0.2 "sharp edge" (atomic Protocol-member rollout) was **removed by CRP** — FR-1 is now an optional `getattr` capability touching only the compiled profiles. Provisioning + build-root are net-new but mechanical; the TS gate is the proven template.

---

## Appendix A — Accepted Suggestions

> Triaged 2026-06-01 (v0.3). Round history preserved in Appendix C (cross-model memory — do not strip).

| ID | Merged into |
|----|-------------|
| R1-S1 | Step 1 (optional `getattr` capability — third-party-safe) |
| R1-S2 | Step 1 Verify (registry round-trip incl. stub external profile) |
| R1-S3 | Step 4 (per-build-root iteration + verdict aggregation) |
| R1-S4 | Step 2 (bounded upward search; stop at project_root/.git) |
| R1-S5 | Step 5 (commit to alias retrofit + frozen `test_ts_toolchain.py`) |
| R1-S6 | Step 6 (`unavailable` advisory path, distinct from `fail`) |
| R1-S7 | Step 3 + Step 6 (relative-path normalization for attribution) |
| R2-S1 | Step 4 (provision once per build-root per run; cache key) |
| R2-S2 | Step 3 (dual-stream capture + per-language error sentinel) |
| R2-S3 | Step 6 (build-root-relative attribution, not basename) |
| R2-S4 | Step 4 (per-language dispatch; no dominant-profile false PASS) |
| R2-S5 | Step 6 (C# `--no-build` artifact-ordering isolation) |
| R2-S6 | Step 7 (false-PASS / build-root-pollution fixture) |
| R2-S7 | Step 4 (cold-toolchain timeout sizing → `unavailable`) |

## Appendix B — Rejected / Narrowed Suggestions (with rationale)

| ID | Disposition | Rationale |
|----|-------------|-----------|
| R1-S1 | **NARROWED → optional path** | Offered the required-vs-optional choice; resolved to **optional `getattr`** (not a breaking required Protocol member), which is third-party-safe and removes the atomic-rollout constraint entirely. Step 1 + the sequencing note rewritten. See requirements Appendix B (R1-F1). |

## Appendix C — Incoming Suggestions (Untriaged, append-only)
*(CRP review rounds append here)*

#### Review Round R1 — claude-opus-4-8 — 2026-06-01

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-01 00:00:00 UTC
- **Scope**: Plan review (steps 0–7) weighted to focus asks #1 (atomic Step 1 rollout / 3rd-party profiles), #3 (build-root locator across multi-* layouts, Step 2), #4 (TS retrofit Step 5), #6 (FR-5 loud-degradation parity in Steps 4/6). Anchored against `languages/registry.py`, `protocol.py`, `go.py`, `java.py`, `csharp.py`, `validators/ts_toolchain.py`, `cap-dev-pipe/ts-verify-gate.py`, `contractors/prime_postmortem.py`.

##### Executive summary (top risks / opportunities / gaps)

- Step 1 "ATOMIC" co-land covers the 5 in-tree profiles but ignores third-party `startd8.languages` entry-point profiles (`registry.py:114-119`) — the atomicity guarantee does not extend to code this repo can't co-land; registration `TypeError` (`registry.py:77`) hits downstream.
- Step 1 lists 7 profiles to edit but `registry.py` registers 7 builtins (python/go/nodejs/java/csharp/vue/prisma) — the plan's `{go,java,csharp,nodejs,python,vue,prisma}` file list matches, but should add a registry round-trip test as the atomic gate, not just "discover() registers all 7".
- Step 2 build-root locator is single-root; multi-module Go / multi-project Gradle / multi-`.csproj` (the common multi-service batch) needs once-per-root iteration + verdict aggregation — currently unplanned at the runner level (Step 4).
- Step 2 has no upward-search stop boundary → risk of selecting an ancestor build file outside the project on a dev host.
- Step 5 TS retrofit: the alias path (`ToolchainResult`↔`CompileGateResult`) is lower-churn and provably no-regression because callers consume `.verdict`/`.diagnostics` (`ts-verify-gate.py:93,104`); plan should commit to alias + a frozen-test gate rather than leaving "(or alias)" optional.
- Step 6 wires the FAIL path but not the `unavailable`-distinct-from-`fail` postmortem behavior (focus ask #6) — risk of infra noise polluting Kaizen trends.
- Step 4 lacks a per-step Verify for build-root selection feeding the runner; Step 2's unit test is isolated from Step 4's integration.
- Opportunity: Step 2's build-root locator is reusable by `csharp.py:346` (`glob("**/*.csproj")`) and the existing TS `_resolve_tsc` root logic — generalize once, replace two ad-hoc lookups.

##### Plan Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Step 1 must add a sub-task + Verify for third-party entry-point profiles: either gate registration with `getattr(profile, "compile_check_command", None)` in `registry.py:register` (optional-member path) or document the breaking change + SDK minor bump (required-member path). | The "ATOMIC ... co-land" note (Step 1 + co-landing constraint) only guarantees the 5 in-tree profiles; `registry.py:114-119` loads external profiles whose authors can't co-land, and `isinstance` at `registry.py:76` will `TypeError` them. | Step 1 row "Verify" column + a new bullet under "Co-landing constraint" | Register a stub external profile lacking the members → assert the path the plan commits to (documented `TypeError`, or graceful registration). |
| R1-S2 | Validation | high | Step 1 Verify should be a registry round-trip assertion: `LanguageRegistry.clear(); discover()` then assert all builtins registered AND each profile's `compile_check_command`/`compile_provision_commands` returns the FR-1/FR-2 value (incl. `None`/`[]` for python/vue/prisma/nodejs). | Current Verify ("registers all 7, no isinstance error; compile_check_command correct per lang") is prose; the atomic risk demands an executable lock that fails loudly if any profile is missed. `registry.py:281` `clear()` enables the round-trip. | Step 1 Verify column | New test `test_compile_capability_all_profiles` asserting per-profile expected values. |
| R1-S3 | Architecture | high | Step 4 `run_compile_gate` must iterate per distinct build root: group `generated_files` by resolved root (Step 2), run provision+compile once per root, aggregate verdicts (any fail→fail; any unavailable & no fail→unavailable; else pass). Update the `run_compile_gate(project_root, profile)` signature/contract accordingly. | OQ-1 + multi-module Go / multi-project Gradle / multi-`.csproj` make multi-root batches the norm; Step 4's single-root signature silently gates only one root, missing cross-file breakage in siblings. | Step 4 row + a note in the Steps table preamble | Toolchain-gated fixture: two `go.mod` subdirs (one broken) → aggregate `fail` with diagnostics attributed to the broken root. |
| R1-S4 | Risks | medium | Step 2 build-root locator must define an upward-search stop boundary (stop at `project_root` or first `.git`); return None (→ `unavailable`) rather than escaping to an ancestor build file. | Step 2 says "search upward ... for nearest build file" with no terminus; on a dev host a stray ancestor `go.mod`/`*.sln` could be chosen, running the gate outside the project. OQ-1 "bound the scan" is unresolved in the plan. | Step 2 row "Step" + "Verify" | Unit: file under project_root with no in-project build file → locator stops at project_root, returns None. |
| R1-S5 | Interfaces | high | Step 5 should commit to the *alias* retrofit (`CompileGateResult` ≡ `ToolchainResult` with shared `.verdict`/`.diagnostics`/`.is_pass`) and add a frozen-test Verify naming `test_ts_toolchain.py` as must-pass-unmodified, removing the "(or alias)" optionality. | OQ-5 asks for lowest-churn; callers (`ts-verify-gate.py:93,104`, `_evaluate_ts_toolchain` at `prime_postmortem.py:1742`) consume `.verdict`/`.diagnostics`, so an alias is provably no-regression while a shared rewrite churns `ts_toolchain.py:46-71`. | Step 5 row "Step" + "Verify" | Run `test_ts_toolchain.py` unmodified post-retrofit; assert verdict literals (`pass`/`fail`/`unavailable`) unchanged via grep guard. |
| R1-S6 | Ops | high | Step 6 must add the `unavailable`-distinct-from-`fail` postmortem path: when `run_compile_gate` returns `unavailable`, `_evaluate_compile_gate` records a reduced-confidence note WITHOUT `success=False`/`disk_quality_score=0`/`CROSS_FILE_CONTRACT` Kaizen (those reserved for `fail`). Mirror `ts-verify-gate.py:104`. | Focus ask #6: infra-absent ≠ code fault. Step 6 only specifies the hard-FAIL path; conflating `unavailable` with `fail` pollutes Kaizen failure-pattern trends (`prime_postmortem.py:1697`). | Step 6 row "Step" + "Verify" | Postmortem fixture: `unavailable` result → assert no FAIL attribution, no `CROSS_FILE_CONTRACT` suggestion, advisory note present. |
| R1-S7 | Validation | medium | Step 3/Step 6 must normalize diagnostic `file` paths to the build root (relative) before attribution; `diagnostics_by_file` (`ts_toolchain.py:181`) only `as_posix()`-normalizes, not relative-to-root. Go emits relative, gradle/dotnet may emit absolute. | OQ-3 path-fidelity: per-feature attribution (FR-6) joins diagnostic paths to `generated_files`; mixed relative/absolute silently drops matches into "unattributed", hiding real failures. | Step 3 (parsers) + Step 6 (attribution) Verify columns | Fixture: absolute C# diag + relative Go diag → both resolve to correct `generated_files` after normalization. |

**Endorsements**: none (Appendix C had no prior untriaged rounds — R1 is the first).

---

## Requirements Coverage Matrix — R1

*Analysis only (CRP dual-mode). Maps each FR → plan step → coverage. Gaps generate the R1-S/R1-F suggestions above.*

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 — `compile_check_command` on all profiles | Step 1 | Partial | In-tree atomicity covered; third-party entry-point profiles (`registry.py:114-119`) unaddressed (R1-F1 / R1-S1). Verify is prose, not an executable round-trip (R1-S2). |
| FR-2 — `compile_provision_commands` | Step 1 | Full | Co-landed with FR-1; values per-language enumerated. Provisioning *caching* (OQ-4) is an open question, not an FR. |
| FR-3 — Per-language diagnostic parsing | Step 3 | Partial | Parsers + banner-noise tolerance covered; path normalization (relative-vs-absolute) for attribution unaddressed (R1-F6 / R1-S7). |
| FR-4 — Unified gate runner (compile-only) | Step 4 | Partial | Single-root runner specified; multi-root iteration + verdict aggregation missing (R1-F4 / R1-S3). |
| FR-5 — Loud degradation (`unavailable` non-pass) | Step 4, Step 6 | Partial | `unavailable` verdict produced; postmortem treating `unavailable` distinctly from `fail` not specified (R1-F3 / R1-S6). |
| FR-6 — Pipeline + postmortem integration | Step 6 | Partial | FAIL path + env toggles + per-batch wiring covered; `unavailable` path (R1-S6) and path-attribution fidelity (R1-S7) missing. |
| FR-7 — Build-root location | Step 2 | Partial | Upward nearest-build-file search covered; multi-root grouping (R1-F4) and search stop-boundary (R1-F5 / R1-S4) missing. |
| FR-8 — Regression fixtures per language | Step 7 | Full | Coherent/incoherent/absent cases + direct-to-parser tests enumerated per language. |
| FR-9 — TypeScript retrofit (no regression) | Step 5 | Partial | Refactor intent covered; no named frozen-test set and verdict-literal lock; alias-vs-shared still optional (R1-F2 / R1-S5). |

#### Review Round R2 — claude-opus-4-8 — 2026-06-01

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-01 00:00:00 UTC
- **Scope**: ADVERSARIAL stress-test + data/ops lens on the plan (steps 0–7). Weighted to focus asks #2 (provisioning cost/caching + parse fidelity + path attribution) and #5 (compile-only vs build-on-test / double-compile / strictness). Builds on R1 (do not re-propose R1-S1..S7). Anchored against `cap-dev-pipe/ts-verify-gate.py`, `validators/ts_toolchain.py`, `contractors/prime_postmortem.py`, `go.py`/`java.py`/`csharp.py`, `contractors/checkpoint.py`.

##### Executive summary (top risks / opportunities / gaps)

- Step 6 reuses the `ts-verify-gate.py` provisioning shape, which runs `npm ci`/`install` **every batch** with no cache (`ts-verify-gate.py:73-80`, 600s timeout); generalizing to `dotnet restore` + gradle + a cold Gradle daemon multiplies per-batch cost — Step 4/6 need a provision-once-per-build-root-per-run contract (OQ-4 unplanned).
- Step 4 inherits `ts_toolchain.py:168`'s `stdout or stderr` OR-fallback; gradle/MSBuild interleave diagnostics + banners across both streams → false PASS or unattributable `unavailable`. Step 3/4 must capture both streams + per-language genuine-error sentinel.
- Step 6 attribution copies `_evaluate_ts_toolchain`'s **basename** keying (`prime_postmortem.py:1738,1767`) — duplicate basenames (`main.go`/`Program.cs`) across multi-service modules collide/misattribute. Must key on build-root-relative path.
- Compile-vs-test redundancy is **language-asymmetric** and Step 6 treats it uniformly: Go `test_command` is `None` (`go.py:54`, no test compile, fully additive); Java/C# tests compile (`java.py:93`, `csharp.py:111`) so the gate duplicates compile work — and C#'s `--no-build` test (`csharp.py:111`) couples to a prior build, creating a gate↔checkpoint artifact-ordering hazard.
- Mixed-language batch: `resolve_language()` returns the dominant profile, so Step 4's single-`profile` runner silently skips the minority language → false PASS. Not planned.
- Opportunity: Step 6 already imports `_evaluate_ts_toolchain`'s structure; the `unavailable`-as-non-success warning path (`prime_postmortem.py:1744-1758`) is the proven template for R1-S6 — generalize it verbatim rather than re-deriving.

##### Plan Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Ops | high | Step 4/Step 6 must add a provisioning cache: run `compile_provision_commands` **once per build root per run**, skipping if already provisioned (or keyed on `go.sum`/`gradle.lockfile`/`packages.lock.json`). Do not copy `ts-verify-gate.py`'s per-batch `npm ci`. | `ts-verify-gate.py:73-80` re-provisions every batch (600s timeout); `dotnet restore` + gradle + cold Gradle daemon per batch will dominate run wall-clock. OQ-4 unplanned at the runner/integration level. | Step 4 (runner) + Step 6 (gate) "Step" + "Verify"; note in Steps preamble | Two batches, same build root, one run → assert provisioning runs once (cache hit second batch); time the second gate excludes restore. |
| R2-S2 | Data | high | Step 3/Step 4 must capture stdout and stderr **separately** and scan both, plus add a per-language genuine-error sentinel (Go `\.go:\d+:\d+:`, javac `error:`, Roslyn `error CS\d+`) before declaring `fail` vs `unavailable`. Replace the `stdout or stderr` OR-fallback for compiled langs. | `ts_toolchain.py:168` (`result.stdout.strip() or result.stderr.strip()`) picks one stream; gradle/MSBuild split diagnostics + daemon banners/summary across streams → missed errors (false PASS) or noise misread as diagnostics. Step 3's "tolerate banner noise" has no mechanism. | Step 3 (parsers) + Step 4 (runner) "Step" + "Verify" | Fixture: gradle output with banner+`error:` on stdout, dotnet errors+summary → parser yields only real diagnostics; no false `unavailable`. |
| R2-S3 | Data | high | Step 6 attribution must key on **build-root-relative path**, not basename. The reference `_evaluate_ts_toolchain` uses `Path(fp).name` (`prime_postmortem.py:1738,1767`); generalizing it verbatim collides duplicate basenames across modules. | Multi-service batches (Step 2's multi-root norm) routinely have `main.go`/`Program.cs` per service; basename keying misattributes or silently drops diagnostics. Extends R1-S7 (relative-vs-absolute) with the collision class. | Step 6 "Step" + "Verify"; cross-ref R1-S7 | Fixture: two features each with `main.go` in distinct go.mod dirs, one broken → diagnostic attributes to the correct feature only. |
| R2-S4 | Risks | high | Step 4 `run_compile_gate(project_root, profile)` must handle **mixed-language batches**: detect ≥2 compiled languages among generated files and dispatch the gate per language (or document the single-language constraint loudly). `resolve_language()` returns only the dominant profile, silently skipping the minority. | A Go+C# monorepo batch gates only the majority language under the single-`profile` signature → minority cross-file breakage ships as false PASS. Compounds R1-S3 (multi-root) with multi-language. | Step 4 "Step" + Steps preamble; relate to R1-S3 | Fixture: batch with Go (majority) + broken C# minority → gate detects C# break or documents per-language dispatch, not global PASS. |
| R2-S5 | Risks | medium | Step 6 must document the C# build-artifact ordering hazard: the gate's `dotnet build --no-restore` vs the checkpoint's `dotnet test --no-build` (`csharp.py:111`) — define whether the test consumes the gate's build or builds independently, to avoid stale/absent-`bin` false test results. | Step 6 wires the gate "after every batch" while the checkpoint already ran `--no-build` tests; the two share an implicit `bin/` dependency the plan never states. Risk: false test PASS/FAIL from stale artifacts. | Step 6 "Step"; note in Step 4 isolation | Fixture: gate build → `dotnet test --no-build` ordering; assert test compiles against a known artifact or gate isolates its build dir. |
| R2-S6 | Validation | medium | Step 7 must add a **false-PASS** regression fixture: a build root polluted with a pre-existing (ungenerated) file that accidentally resolves a broken cross-feature reference → assert the gate isolates the build root and still surfaces the incoherence. | Run-008 scored 0.99 verify-blind precisely because un-gated context masked a defect; Step 7's coherent/incoherent/absent triad omits the "passes due to stray scaffolding" class. Without it, a PASS may be a build-root-pollution artifact. | Step 7 "Step" (fourth fixture class) | Fixture: broken reference resolved via stray pre-existing file → gate either flags incoherence or runs in an isolated/clean build root. |
| R2-S7 | Ops | medium | Step 4 must set explicit per-stage timeouts distinct from the TS 180s/600s defaults, accounting for cold `dotnet restore`/gradle daemon spin-up, and treat timeout as `unavailable` (infra), not `fail`. | `ts_toolchain.py:127` defaults 180s and `ts-verify-gate.py:40` 600s; a cold Gradle daemon or large `dotnet restore` can exceed these, and `ts_toolchain.py:161-163` already maps timeout→`status="timeout"`→`unavailable`. The plan inherits TS timeouts without sizing for slower compiled toolchains. | Step 4 "Step" + "Verify" | Unit: a provisioning step exceeding timeout → verdict `unavailable` with a timeout note, not `fail`. |

**Endorsements** (R1 untriaged items I agree with):
- R1-S1: third-party entry-point profile registration break is real (`registry.py:76` `isinstance`); the plan's "ATOMIC" note covers only in-tree profiles.
- R1-S3: multi-root iteration + verdict aggregation — the common multi-service case; single-root runner is a gap (R2-S4 extends to multi-language).
- R1-S6: `unavailable`-distinct-from-`fail` postmortem path is mandatory; `_evaluate_ts_toolchain:1744-1758` is the proven template to generalize.
- R1-S7: path normalization for attribution; R2-S3 extends with basename-collision.

**Disagreements** (R1 untriaged):
- None. R1's seven S-items are sound; R2 extends rather than contradicts.

---

## Requirements Coverage Matrix — R2

*Analysis only (CRP dual-mode). R2 adversarial/data-ops lens; re-maps FRs where R2 found new gaps beyond R1. Gaps generate the R2-S/R2-F suggestions above.*

| Requirement | Plan Step(s) | Coverage | Gaps (R2 additions beyond R1) |
| ---- | ---- | ---- | ---- |
| FR-1 — `compile_check_command` on all profiles | Step 1 | Partial | (R1 unchanged) third-party profiles + executable round-trip. No new R2 gap. |
| FR-2 — `compile_provision_commands` | Step 1, Step 4/6 | Partial | **R2 downgrade**: provisioning *caching/idempotence* (OQ-4) unplanned — per-batch `npm ci` pattern (`ts-verify-gate.py:73-80`) generalized to slower `dotnet restore`/gradle dominates wall-clock (R2-F1 / R2-S1). |
| FR-3 — Per-language diagnostic parsing | Step 3 | Partial | Stream selection (`stdout or stderr` OR-fallback, `ts_toolchain.py:168`) + per-language genuine-error sentinel unaddressed (R2-F2 / R2-S2). Path normalization (R1) still open. |
| FR-4 — Unified gate runner (compile-only) | Step 4 | Partial | Multi-*language* batch (dominant-profile silent skip) unplanned (R2-F7 / R2-S4); C# `--no-build` artifact ordering (R2-F6 / R2-S5); timeout sizing for cold toolchains (R2-S7). Multi-root (R1) still open. |
| FR-5 — Loud degradation (`unavailable` non-pass) | Step 4, Step 6 | Partial | Legitimately-unresolvable external deps (private feed / GOPRIVATE) → must be `unavailable` not `fail` (R2-F5). `unavailable`≠`fail` postmortem (R1) still open. |
| FR-6 — Pipeline + postmortem integration | Step 6 | Partial | Basename-collision attribution (`_evaluate_ts_toolchain:1738,1767`) → must key on build-root-relative path (R2-F3 / R2-S3). |
| FR-7 — Build-root location | Step 2 | Partial | (R1) multi-root grouping + stop-boundary. R2 adds: mixed-language layouts interact with multi-root (R2-S4). |
| FR-8 — Regression fixtures per language | Step 7 | Partial | **R2 downgrade**: missing the false-PASS / build-root-pollution fixture class (R2-F8 / R2-S6) — the exact run-008 verify-blind mode. |
| FR-9 — TypeScript retrofit (no regression) | Step 5 | Partial | (R1 unchanged) named frozen-test set + verdict-literal lock + alias commitment. No new R2 gap. |
| Non-Req — compile-only vs test | §0 / Non-Req | Partial | **R2 new**: blanket "test_command already compiles" is false for Go (`go.py:54` → `None`, fully additive) and incomplete for C# (`--no-build`); per-language asymmetry must be recorded (R2-F4). |
