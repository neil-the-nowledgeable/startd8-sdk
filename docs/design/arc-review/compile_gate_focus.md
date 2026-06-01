# CRP Focus — Generalized Compile-Gate (Go/Java/C#)

Weight the review toward these high-risk areas. F-suggestions → requirements
(`COMPILE_GATE_REQUIREMENTS.md`, FR-1..FR-9); S-suggestions → plan
(`COMPILE_GATE_PLAN.md`, steps 0–7).

1. **Atomic Protocol-member rollout (FR-1, plan step 1).** `LanguageProfile` is
   `@runtime_checkable`; `registry.register()` does `isinstance`. Adding
   `compile_check_command` + `compile_provision_commands` requires all 7 profiles
   to define them or registration raises. Is the atomic co-land the right move,
   or should the members be optional (getattr with default) to avoid a breaking
   protocol change? What about third-party profiles registered via entry points?

2. **Provisioning cost/caching + diagnostic-parse fidelity (FR-2/FR-3, OQ-3/OQ-4).**
   `dotnet restore`, gradle dependency resolution, and the Gradle daemon are slow
   and stateful. Is per-batch provisioning acceptable, and what's the cache key
   (go.sum / gradle.lockfile / packages.lock.json)? Will the per-language regex
   parsers survive gradle/dotnet/MSBuild wrapper noise and resolve diagnostic
   file paths to feature `generated_files` reliably (relative vs absolute)?

3. **Build-root location across multi-* layouts (FR-7, OQ-1/OQ-2).** Multi-module
   Go, multi-project Gradle, multiple `.csproj`/`.sln`. Run once per build root or
   once per project? Gradle wrapper (`./gradlew`) vs system `gradle`; `compileJava`
   vs `classes` vs Maven `mvn compile`. Where does the upward search stop?

4. **TS retrofit without regression (FR-9, OQ-5).** Refactoring
   `ts_toolchain.run_project_typecheck` behind the unified runner must keep the
   merged TS-gate tests + cap-dev-pipe `ts-verify-gate.py` behavior identical.
   Shared `CompileGateResult` vs adapter — which is the lower-churn retrofit?

5. **Compile-only vs build-on-test boundary + strictness default
   (Non-Requirements, OQ-6).** Is compile-only genuinely additive over the
   existing `test_command` compile, or redundant where tests already run? Should
   the default be informational (like the TS gate) or strict? Any double-compile
   waste to avoid when both the gate and `test_command` run?

6. **FR-5 loud-degradation parity with RUN-008 FR-9.** Confirm
   toolchain/build-file/provision-absent → `unavailable` (non-pass), never a
   silent pass, and that the postmortem treats `unavailable` distinctly from
   `fail` (infra condition vs code fault) — matching the TS gate's semantics.
