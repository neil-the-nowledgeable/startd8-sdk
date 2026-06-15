# CRP Focus — Local Deploy Harness R1

Weight the review toward these sponsor concerns:

1. **Untrusted-code trust boundary.** v1 isolation is venv + subprocess + loopback bind only — it is
   explicitly NOT a kernel sandbox. The apps under test are raw LLM output (deterministic OFF). Is
   the v1 boundary honestly stated and is it adequate for running on a developer/benchmark machine?
   What can a malicious or buggy generated app still do (filesystem writes outside the app root,
   outbound network during `pip install` of attacker-named deps, fork bombs, resource exhaustion)?
   Where exactly should the v2/Docker (benchmark FR-44) line be drawn, and what cheap v1 mitigations
   are missing (e.g. pip `--no-build-isolation` vs not, dependency pinning/quarantine, ulimits,
   `--isolated`, network egress note)?

2. **OpenAPI → request-body synthesis brittleness (FR-9/10).** Synthesizing a valid POST body from a
   live `/openapi.json` is the riskiest correctness surface. How robust must `$ref` resolution,
   required vs nullable, enums, formats, and nested/FK objects be before the smoke rung produces
   trustworthy signal? Is "prefer FK-free resource + grade best-effort" enough, or does it bias the
   quality signal (apps with only FK-coupled resources always score `skipped`)?

3. **Input contract & batch discovery.** Deploy target is the per-model `workdir/` (not `output/`);
   batch globs `batch_root/*/workdir` and reverses `slug(model)`. Is reverse-slug lossy/ambiguous
   (slug collisions across providers)? Should the join key to `comparison-report.json` be carried
   explicitly rather than reconstructed from a directory name?

4. **Teardown / no-orphan guarantees (FR-13).** uvicorn child + throwaway venv must always be reaped,
   including on Ctrl-C and on exceptions mid-ladder. Is signal handling + try/finally sufficient, or
   are there leak paths (child spawns its own workers, zombie on SIGKILL race, tmp dir on crash)?

5. **Reuse correctness.** `boot_smoke.resolve_app_target()` and `backend_codegen.drift.embedded_mode()`
   are reused. Do their preconditions hold for non-canonical raw LLM apps (missing `app.yaml`,
   missing/garbled `app/settings.py`)? Any failure mode where reuse silently mis-detects?

6. **Signal integrity for the benchmark.** The whole point is comparing models. Are the ladder rungs
   defined so that an install/boot/smoke failure is attributable to *the model's code* and not to
   harness flakiness (network, port race, timeout too tight)? Should timeouts and environment be
   recorded in the result so a `fail` is reproducible and not confounded?
