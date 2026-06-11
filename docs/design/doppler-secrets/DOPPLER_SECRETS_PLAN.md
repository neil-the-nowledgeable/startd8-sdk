# Doppler Secrets Management Integration — Implementation Plan

**Version:** 1.1 (Post-CRP — R1 triaged & applied; paired with Requirements v0.3)
**Date:** 2026-06-10
**Status:** IMPLEMENTED (2026-06-10) — all 10 steps built; 36 unit tests green

> **Implementation note (2026-06-10).** Shipped as `src/startd8/secrets/` (protocol/registry/
> local/doppler/manager) + `cli_secrets.py` + `startd8.secrets` entry-point group; wired via a new
> `@app.callback` in `cli.py`, `AgentFramework.__init__`, and `ConfigManager.get_secrets_backend_config()`
> / `get_api_key_source()` doppler-reporting. Tests: `tests/unit/secrets/` (backends/registry,
> doppler download+retry+OTel-no-leak, hydration matrix incl. deny-list/allowlist/fail-open/fail-closed/
> thread-safety, subprocess+no-secret-at-rest, CLI). All security invariants from R1 verified.

> This plan was written against Requirements v0.1, reshaped them during planning (see Requirements §0),
> and was then hardened by CRP Round 1: 9/9 S-suggestions accepted and applied (deny-list, token/
> subprocess boundary, thread-safety, single-resolution-path, OTel-at-source, bounded fail-open,
> `secrets test` semantics, no-secret-at-rest Step 10). Dispositions in Appendix A. Aligned to
> Requirements v0.3.

---

## Discoveries that reshaped the requirements

| v0.1 assumed | Planning revealed | Impact |
|--------------|-------------------|--------|
| Providers resolve keys through `ConfigManager.get_api_key()`; editing it inserts Doppler everywhere | Providers do **not** use it. Each calls `config.get('api_key') or os.getenv('X')` directly — **8+ call sites across 4 files** (`anthropic.py:292`, `gemini.py:299`, `openai.py:265/356/417/482-505`, `mistral.py:111/134`). `get_api_key()` has only **2 callers** (`prompt_enhancer.py:199`, internal `has_api_key`). | **FR-4 reframed.** The chokepoint doesn't exist. Either edit every provider (invasive, breaks "zero provider changes") or **hydrate `os.environ`** so existing `os.getenv()` calls transparently see Doppler values. → hydration chosen. |
| A central resolver returns one secret at a time | Doppler's download endpoint returns the **entire config** as a JSON map in one call | Whole-config fetch → **environment hydration** is the natural model (one fetch populates many env vars). Resolves OQ-4. |
| `validate_config()` (sync, per-agent-creation) is where Doppler I/O slots in | That would fire a blocking HTTP call on *every* agent creation | **Front-load** the fetch once at startup (hydrate), not per-validate. Resolves OQ-5. |
| There's a single SDK init point to hook | `discover()` is called from ~10 scattered sites; there is **no `@app.callback`** in `cli.py` and no package-level auto-init | Hydration hook must be **placed deliberately and made idempotent**: a new CLI `@app.callback` + an `AgentFramework.__init__` hook + an explicit public `hydrate()` for library users. |
| Doppler SDK vs REST is open (OQ-1) | Hydration needs only one endpoint; REST + httpx reuses `resilience/`/`ratelimit/` with no new hard dep | Use **direct REST**; no `[doppler]` extra needed. Resolves OQ-1, OQ-7. |

**Net:** the integration is *simpler and less invasive* than v0.1 implied — no provider edits — but the
**resolution mechanism changed from "central getter" to "environment hydration."**

---

## Architecture

```
startup (CLI callback / AgentFramework.__init__ / explicit hydrate())
   └─> SecretsManager.hydrate()                 # guarded by a module-level lock (R1-S3)
          ├─ if already hydrated: return        # thread-safe, exactly-once
          ├─ select backend from config/env (default: local = no-op)
          ├─ DopplerSecretsProvider.get_all_secrets()   # one httpx GET, cached, OTel-wrapped (R1-S5)
          │     GET https://api.doppler.com/v3/configs/config/secrets/download?format=json
          │     Authorization: Bearer $DOPPLER_TOKEN     # token READ only — never written to env (R1-S2)
          └─ for k, v in secrets:
                 if k in DANGEROUS_KEYS:        # PATH/LD_PRELOAD/PYTHONPATH/… (R1-S1)
                     warn_masked(skip); continue
                 if allowlist is not None and k not in allowlist:  # []==none, absent==all (R1-F8)
                     continue
                 if k not in os.environ:        # existing env ALWAYS wins
                     os.environ[k] = v          # provider os.getenv() now sees it
```

Providers are untouched. `config['api_key']` (explicit) still beats env; env (now possibly
Doppler-populated) beats local config file. Precedence preserved end-to-end. The bearer
`DOPPLER_TOKEN` is consumed for the fetch and is **not** among the hydrated keys, so it is not
re-exported to child processes (R1-S2).

## Steps

### Step 1 — `secrets/` package + protocol (FR-1)
`src/startd8/secrets/__init__.py`, `protocol.py`. Define `SecretsProvider` Protocol:
`name`, `get_secret(key)`, `get_all_secrets() -> dict`, `validate_config()`,
`get_required_env_vars()`. Mirror `providers/protocol.py` style.

### Step 2 — Registry + entry points (FR-2)
`secrets/registry.py` = `SecretsProviderRegistry.discover()` cloned from
`providers/registry.py:109-207` (entry-point load + built-in fallback). Add to `pyproject.toml`:
```toml
[project.entry-points."startd8.secrets"]
local = "startd8.secrets.local:LocalSecretsProvider"
doppler = "startd8.secrets.doppler:DopplerSecretsProvider"
```

### Step 3 — Local backend (FR-2, FR-9)
`secrets/local.py` = `LocalSecretsProvider`: `get_all_secrets()` returns `{}` (env+config file path
already covers it). Makes "no backend configured" a real, default, no-network backend.

### Step 4 — Doppler backend (FR-3, FR-12, FR-13, FR-16)
`secrets/doppler.py` = `DopplerSecretsProvider`:
- Reads `DOPPLER_TOKEN` (env, Doppler convention) or SDK config (FR-8). Token is held locally for the
  request only; it is **never** placed into `os.environ` (R1-S2 / FR-15a).
- `get_all_secrets()`: httpx GET the download endpoint, Bearer auth, parse JSON map; strip Doppler
  metadata keys (`DOPPLER_PROJECT`, `DOPPLER_CONFIG`, `DOPPLER_ENVIRONMENT`).
- **Instrument at source (R1-S5):** the OTel span (FR-16 keys) wraps *this* httpx call when first
  written — not retrofitted in a later step — so the fetch is never un-instrumented and no secret/token
  value is ever set as a span attribute.
- Wrap in `resilience/` retry + timeout; on failure honor configured fail-open/fail-closed (OQ-3,
  default fail-open). On fail-open, stash the **masked** failure (single instance) so `SecretsManager`
  can cite it once per later missing-key error without duplicating token material (R1-S9 / FR-13a).
- In-memory cache (FR-6). **Cache is fetch-once-per-process with no TTL/force-refresh in v1 — rotation
  requires restart (R1-S7 / NR-7).** Leave an explicit `# v1: no runtime invalidation (NR-7)` marker
  so a future TTL path is a deliberate change, not silent drift.

### Step 5 — SecretsManager + hydration (FR-4, FR-4a/b, FR-5, FR-5a, FR-6a)
`secrets/manager.py` = `SecretsManager`:
- `hydrate()`: **thread-safe** via a module-level `threading.Lock` around the guard-flag check + env
  writes (R1-S3 / FR-6a) — "idempotent" alone is a data race under concurrent `AgentFramework`
  construction. Select backend; `get_all_secrets()`; then per key: skip `DANGEROUS_KEYS` deny-list
  with masked warning (R1-S1 / FR-4a); apply allowlist (absent⇒all, `[]`⇒none — R1-F8 / FR-4b);
  set only-if-absent into `os.environ`; record per-key source map for FR-5; retain the single masked
  fetch-failure for bounded root-cause errors (FR-13a).
- `get_secret_source(name)` → `env|config|doppler` (backend label is separate; `local` hydrates
  nothing, so a value resolves as `env` or `config`, never `local` — R1-S? / FR-5a).
- **Single resolution path (R1-S6):** do **not** add a second Doppler lookup inside
  `ConfigManager.get_api_key()`. Because hydration populates `os.environ`, the getter's existing
  `os.getenv` check already sees Doppler values — so its 2 callers and the 8 provider `os.getenv`
  sites resolve identically. Only extend `get_api_key_source()` to *report* `doppler` when the
  hydrated env value's recorded source is Doppler. This avoids a getter-vs-env divergence (e.g. an
  allowlist-excluded key must be "not set" via both paths).

### Step 6 — Bootstrap hooks (FR-17, thread-safe)
- `cli.py`: add `@app.callback()` (new) → `SecretsManager.hydrate()` before any subcommand.
- `framework.py` `AgentFramework.__init__` → `hydrate()` (guarded + locked, once per process).
- Public `from startd8.secrets import hydrate` for library users who construct providers directly.

### Step 6b — Subprocess / token-inheritance boundary (FR-15a, R1-S2)
- Confirm and test the env-inheritance contract: hydrated *secrets* intentionally flow to child
  processes (`doppler run` semantics — child tools may need the same provider keys), but the bearer
  `DOPPLER_TOKEN` does not (it was never hydrated). Document this in the `secrets/` package docstring
  and the CLI help so the boundary is explicit, not incidental.

### Step 7 — CLI command group (FR-10, FR-11)
`cli_secrets.py` Typer sub-app (mirror `cli_queue.py`), `app.add_typer(secrets_app, name="secrets")`:
`status`, `test`, `list` — all values via `security.mask_api_key()`.
- **`secrets test` behavior (R1-S8):** it is the one command whose purpose is a live call. Define:
  against `local` it is a defined **no-op success** (exit 0, "no remote backend"); against `doppler`
  it performs one auth/connectivity probe. In CI it is exercised **only against a mocked transport**
  (Step 9 forbids live calls); it must never crash the CLI when the backend is `local`. Specify exit
  codes (0 ok / non-zero auth-fail) for scripting.

### Step 8 — Telemetry + logging (FR-15, FR-16)
OTel span attribute contract (`secrets.backend`, `secrets.project`, `secrets.config`,
`secrets.cache_hit`, `secrets.outcome`, `secrets.key_count`) — **defined here, emitted at the Step 4
call site.** `get_logger`; masked-only logging; never log token. (No retrofit: Step 4 already wraps
the span; this step pins the attribute schema and the leakage-negative assertion.)

### Step 9 — Tests
Unit: protocol/registry/local/doppler (httpx mocked), hydration precedence (existing env wins),
fail-open/closed, masking. CLI: `secrets status/test/list`. No live Doppler calls in CI. **Plus the
security/failure-mode matrix the v1.0 plan omitted (R1-S4):**
- **Deny-list (FR-4a):** config containing `LD_PRELOAD` leaves `os.environ` untouched for that key +
  masked warning.
- **Allowlist fail-safe (FR-4b):** absent⇒inject-all, `[]`⇒inject-none, unknown-key⇒absent/no-error.
- **Subprocess inheritance (FR-15a):** spawn a child post-`hydrate()`; assert intended keys visible,
  `DOPPLER_TOKEN` absent.
- **Concurrency (FR-6a):** N threads construct `AgentFramework`; assert exactly one fetch + consistent env.
- **OTel leakage-negative (FR-16):** in-memory span exporter; required attr keys present; no attr value
  equals a secret/token fixture.
- **Fail-open bounding (FR-13a / R1-S9):** induce fetch failure + 3 missing keys; assert one WARNING,
  masked-only, root-cause note attached once per error (not accumulated).

### Step 10 — No-secret-at-rest assertion (FR-14, R1-S4)
Close the coverage gap the R1 matrix flagged: add a test that a full hydration run (Doppler backend,
mocked transport) writes **no new file** containing secret material — snapshot the project/temp dirs
before/after and assert no secret-bearing artifact appears. Makes FR-14 a verified invariant, not an
implicit consequence of "no caching code."

### Step 11 — Runtime rotation (FR-ROT-1..6, added 2026-06-11)
Promotes former NR-7. **IMPLEMENTED + live-verified against real Doppler.**
- `doppler.py`: `invalidate()` + `get_all_secrets(force=True)` bust the in-process cache (FR-ROT-3);
  span carries `secrets.refresh`.
- `manager.py`: shared `_run_hydration(force_fetch, overwrite_owned, reason)` body; `refresh()`
  overwrites **only `_source_map`-owned keys**, never user env (FR-ROT-2); fail-open-preserving — a
  failed refresh keeps current env (FR-ROT-5); lazy TTL via `secrets_backend.ttl_seconds` /
  `STARTD8_SECRETS_TTL`, checked in `hydrate()`/`get_secret()` (FR-ROT-4).
- `secrets.refresh()` public export; `startd8 secrets refresh` CLI reports rotated-key counts.
- Tests: `test_rotation.py` (owned-overwrite, user-env-preserved, lazy TTL, fail-open-preserving,
  fail-closed) + doppler force-invalidation + CLI refresh. Live proof: rotated a key in `startd8/dev`
  mid-process → `refresh()` picked it up, provider keys untouched.
- **Test-isolation fix:** a persisted `backend=doppler` in `~/.startd8/config.json` was bleeding into
  the unit suite (every `AgentFramework()` hit live Doppler). Added `pytest_configure` in
  `tests/conftest.py` forcing `STARTD8_SECRETS_BACKEND=local` unless `STARTD8_RUN_INTEGRATION=1`,
  plus per-suite config neutralization in `tests/unit/secrets/conftest.py`.

## Sequencing
1 → 2 → (3, 4 parallel) → 5 → 6 → 6b → 7 → 8 → 9 → 10 → 11. Steps 1–5 are the core; 6–6b–7 wire it in;
8–10 harden; 11 adds rotation. Note OTel (8) is *specified* late but *implemented* at the Step 4 call site (R1-S5).

## Open questions resolved by planning
- **OQ-1** → REST + httpx (no SDK dep, no extra). **OQ-4** → whole-config fetch (hydration).
- **OQ-5** → front-load at startup, not per-validate. **OQ-6** → ~8 provider call sites exist but are
  bypassed via hydration → **0 provider edits**. **OQ-7** → no `[doppler]` extra needed.
- **OQ-2** → inject-all-if-absent + optional allowlist (now hardened with the FR-4a deny-list).
  **OQ-3** → fail-open default with bounded, masked signalling (see Requirements v0.3 FR-13/FR-13a).

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Process-control deny-list | R1 (claude-opus-4-8-1m) | Applied to Architecture + Step 4/5 (`DANGEROUS_KEYS`, skip-with-masked-warning); test in Step 9. Mirrors req FR-4a. | 2026-06-10 |
| R1-S2 | Subprocess/token inheritance confinement | R1 | Applied as **Step 6b** + Architecture note; token never hydrated; subprocess boundary documented+tested. Mirrors req FR-15a. | 2026-06-10 |
| R1-S3 | Thread-safe hydrate() | R1 | Applied to Step 5/6 (`threading.Lock` around guard+env writes); concurrency test in Step 9. Mirrors req FR-6a. | 2026-06-10 |
| R1-S4 | Expand test matrix (security/failure modes) | R1 | Applied to Step 9 (deny-list, allowlist, subprocess, concurrency, OTel-negative, fail-open bounding) + new **Step 10** for FR-14. | 2026-06-10 |
| R1-S5 | OTel span at fetch source | R1 | Applied: span moved to Step 4 call site; Step 8 now pins attribute schema only; sequencing note added. | 2026-06-10 |
| R1-S6 | Dual-resolution-path consistency | R1 | Applied by **simplifying** — no second Doppler lookup in `get_api_key()`; lean on hydrated `os.environ` so getter + provider sites agree; only `get_api_key_source()` reports `doppler`. | 2026-06-10 |
| R1-S7 | Cache lifetime / rotation | R1 | Applied as explicit v1 limitation marker in Step 4 (no TTL/force; restart-to-rotate). Mirrors req NR-7. | 2026-06-10 |
| R1-S8 | `secrets test` network/CI/local behavior | R1 | Applied to Step 7 — `local`⇒no-op success, `doppler`⇒probe, CI⇒mocked, defined exit codes. | 2026-06-10 |
| R1-S9 | Fail-open masked, bounded note | R1 | Applied to Step 4 (single masked stash) + Step 9 test. Mirrors req FR-13a. | 2026-06-10 |
| (matrix) | FR-14 coverage gap | R1 Coverage Matrix | Closed via new **Step 10** (no-secret-at-rest negative test). | 2026-06-10 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-10

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-10 20:05:00 UTC
- **Scope**: Implementation-plan review for an embedded-library integration that mutates `os.environ` and handles credentials. Weighting security, ops, interface contracts, failure modes, sequencing, and validation strategy per the review mandate.

**Executive summary (top risks / gaps in the plan):**

- The Architecture pseudocode mutates `os.environ` with **no thread guard** and no concurrency story; Step 6 wires hydration into `AgentFramework.__init__`, which embedded callers may construct from multiple threads.
- **Step 4 strips Doppler metadata keys but does not deny dangerous keys** (`PATH`, `LD_PRELOAD`, `PYTHONPATH`, …) — the inject-all loop will happily set them into the host process.
- The injected `DOPPLER_TOKEN` and all secrets **leak to every subprocess** the SDK/host spawns; nothing in the plan confines them.
- **Step 9's test matrix omits** the highest-risk behaviors: subprocess inheritance, key-deny policy, concurrency, OTel leakage negatives, and the FR-13 "exactly-once warning / no duplicate root-cause leak" path.
- **OTel span placement (Step 8) is sequenced after Step 4/5**, so the fetch in Step 4 isn't instrumented when first written; the span must wrap the Step 4 httpx call, not be bolted on later.
- **FR-14 (no secret-at-rest) has no corresponding plan step** — there is no negative test that the Doppler backend never writes to disk.
- Step 5's extension of `ConfigManager.get_api_key()` to `env→backend→config` introduces a **second resolution path** that can disagree with the hydration path (FR-4) for the same key — a precedence-consistency risk between the two callers and the 8 provider sites.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | critical | In Step 4 / Step 5, add an explicit **deny-list of process-control env keys** (`PATH`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `DYLD_*`, `PYTHONPATH`, `PYTHONSTARTUP`, `IFS`, `BASH_ENV`) that are never hydrated even if present in the Doppler config — skip-with-masked-warning. | The `for k, v in secrets: if k not in os.environ: os.environ[k] = v` loop in Architecture trusts the config to hold only credentials. A malicious/misconfigured Doppler config injecting `LD_PRELOAD` achieves code execution in the host. The plan only strips Doppler *metadata* keys, not dangerous ones. | Architecture pseudocode + Step 4 ("strip Doppler metadata keys") | Unit test: secrets map containing `LD_PRELOAD` leaves `os.environ['LD_PRELOAD']` untouched and logs a masked skip warning. |
| R1-S2 | Security | high | Add a plan step (or extend Step 6) confining secret/token inheritance to child processes: decide and document whether subprocesses should see injected secrets; at minimum ensure **`DOPPLER_TOKEN` is consumed and never written into `os.environ`** (it is only read for the fetch). | Step 6 mutates the process environment that every `subprocess.Popen` inherits. The plan never states whether children should receive secrets, and the bearer token could be re-exported. This is the primary leak vector of env-hydration designs and has zero coverage. | New step after Step 6, or note in Architecture | Test: after `hydrate()`, spawn a child and assert `DOPPLER_TOKEN` is absent and only intended keys are visible. |
| R1-S3 | Ops | high | Add a thread-safety mechanism to `hydrate()` in Step 5/Step 6: a module-level lock (or documented single-thread-bootstrap constraint) around the guard-flag check + `os.environ` writes. | Step 6 calls `hydrate()` from `AgentFramework.__init__`; embedded callers may build frameworks on multiple threads. A bare boolean guard + `os.environ` writes is a data race (double-fetch / partial hydration). "Idempotent" (the plan's word) is not "thread-safe." | Step 5 (`hydrate()`: idempotent (guard flag)) and Step 6 | Test: construct N `AgentFramework` instances concurrently; assert exactly one fetch and consistent env. |
| R1-S4 | Validation | high | Expand Step 9's test list to explicitly include: subprocess inheritance, dangerous-key deny policy, concurrent hydration, OTel attribute-leakage negatives, FR-13 exactly-once warning + non-duplicating root-cause note, and an FR-14 no-disk-write assertion. | Step 9 currently tests precedence, fail-open/closed, and masking but omits every adversarial/failure-mode behavior that makes this a *credential* feature rather than a config feature. Untested security invariants regress silently. | Step 9 — Tests | CI: each listed behavior has a dedicated unit test; coverage gate on `secrets/` security paths. |
| R1-S5 | Ops | high | Move/duplicate the OTel span (Step 8) so it **wraps the Step 4 httpx fetch at the point of implementation**, and add an explicit assertion that no span attribute/event carries a secret or token value. | Sequencing `8` after `4/5` means the fetch is written un-instrumented and instrumentation is retrofitted, risking attributes added ad-hoc (and possibly leaking values). Instrument-at-source is both cleaner and the only way FR-16's leakage boundary is enforced. | Step 4 (add span wrap) + Step 8 + Sequencing note | Test with in-memory span exporter: required attrs present; no attr value equals a secret/token fixture. |
| R1-S6 | Architecture | medium | Resolve the **dual-resolution-path consistency** between FR-4 hydration and Step 5's extended `ConfigManager.get_api_key()` (`env→backend→config`): document precedence so both the 2 `get_api_key()` callers and the 8 provider `os.getenv()` sites resolve the same key identically. | Step 5 adds a *second* place Doppler is consulted (the getter, for its 2 callers) on top of env hydration (for the 8 provider sites). If the getter's `backend` lookup and the hydrated env disagree (e.g. allowlist excluded a key from env but the getter still fetches it), the same key resolves differently per caller. | Step 5 (the `ConfigManager.get_api_key()` extension bullet) | Test: a key excluded by allowlist returns identical results (or identical "not set") via both `os.getenv` and `get_api_key()`. |
| R1-S7 | Data | medium | Add a step (or extend Step 4) defining **cache lifetime / invalidation**: the in-memory cache is fetch-once-per-process with no TTL or `force` refresh, which precludes runtime key rotation — either implement a refresh path or record the restart-to-rotate limitation in the plan. | FR-6 mandates single fetch; §1 of the requirements sells "rotate a leaked key centrally" as a benefit. The plan must either deliver runtime refresh or explicitly accept restart-to-rotate, so implementers don't silently ship a non-rotating "secrets manager." | Step 4 (In-memory cache (FR-6)) and Sequencing | Acceptance: documented refresh API or an explicit plan note that rotation requires process restart in v1. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | Specify the **`secrets test` CLI command's network behavior under fail-closed** and during CI: Step 7 lists `test` (validate connectivity/auth) but Step 9 forbids live Doppler calls in CI — define how `secrets test` is exercised (mocked) and that it never crashes the CLI when the backend is `local`. | `secrets test` is the one command whose purpose is a live call; the plan must reconcile it with "no live Doppler calls in CI" and define its behavior for the default `local` backend (no-op success vs. error). Otherwise the command is either untested or breaks CI. | Step 7 (CLI command group) + Step 9 | Test: `secrets test` against mocked Doppler (success/auth-fail) and against `local` (defined no-op result); assert exit codes. |
| R1-S9 | Security | medium | Add an assertion to Step 9 that the **fail-open masked warning and the deferred root-cause note never emit the raw or full-length token**, and that the "Doppler fetch failed earlier" note is attached **once per downstream error without accumulating** across many missing keys. | Step 4 "stash the masked failure" + Step 5 "retain masked fetch-failure" create a string that flows into potentially many later errors. Without a test, a refactor could swap masked for raw, or duplicate the note across every missing-key error, amplifying exposure. | Step 9 — Tests | Test: induce fetch failure + 3 missing keys; assert masked-only, single warning, bounded note attachment. |

**Endorsements**: (none — R1 is the first round; no prior untriaged suggestions exist.)
**Disagreements**: (none — no prior suggestions to disagree with.)

---

## Requirements Coverage Matrix — R1

> Analysis only (not triage). Maps each requirement (FR/NR) to the plan step(s) addressing it. `Covered` = plan fully implements it; `Partial` = mentioned but missing detail/edge-cases; `Gap` = not addressed by the plan.

| Requirement | Plan Step(s) | Coverage | Gaps / Notes |
| ---- | ---- | ---- | ---- |
| FR-1 — SecretsProvider protocol | Step 1 | Covered | Protocol surface matches; see R1-F4 re: `local` semantics for `get_secret_source`. |
| FR-2 — Entry-point discovery | Step 2, Step 3 | Covered | Cloned from `providers/registry.py`; built-in fallback included. |
| FR-3 — Doppler backend | Step 4 | Covered | — |
| FR-4 — Environment hydration (inject-all-if-absent + allowlist) | Architecture, Step 5, Step 6 | Partial | No dangerous-key deny policy (R1-S1); allowlist empty/malformed semantics unspecified (R1-F8); subprocess inheritance unaddressed (R1-S2). |
| FR-5 — Source transparency | Step 5 (`get_secret_source`) | Partial | `local`-backend source attribution undefined when nothing is hydrated (R1-F4). |
| FR-6 — Caching / single fetch / idempotent | Step 4 (cache), Step 5 (guard) | Partial | No cache invalidation / rotation path (R1-S7, R1-F3); idempotent guard not shown thread-safe (R1-S3, R1-F9). |
| FR-7 — Backend selection config | Step 5 (backend select), implied Step 2 | Partial | Plan selects backend in `hydrate()` but no explicit step adds the `secrets_backend` config section / `STARTD8_SECRETS_BACKEND` parsing. |
| FR-8 — Doppler auth config | Step 4 (reads `DOPPLER_TOKEN`/config) | Covered | `DOPPLER_PROJECT`/`DOPPLER_CONFIG` handling implied by endpoint, not detailed. |
| FR-9 — Off by default | Architecture (default local = no-op), Step 3 | Covered | Interaction of allowlist with off-by-default could be clarified (R1-F8). |
| FR-10 — `startd8 secrets` command group | Step 7 | Partial | `secrets test` network/CI behavior + `local`-backend behavior undefined (R1-S8). |
| FR-11 — Masking everywhere | Step 7, Step 8 | Covered | — |
| FR-12 — HTTP client reuse (resilience/ratelimit) | Step 4 | Covered | — |
| FR-13 — Failure semantics (fail-open default + root-cause note) | Step 4, Step 5 | Partial | "Loud" log level undefined; warning-once / non-duplicating note not specified or tested (R1-F7, R1-S9). |
| FR-14 — No secret-at-rest by default | (none explicit) | Gap | No plan step asserts/tests the no-disk-write invariant; relies on absence of caching code (R1-S4). |
| FR-15 — Logging hygiene | Step 8 | Covered | — |
| FR-16 — OTel spans | Step 8 | Partial | Span sequenced after fetch (Step 4); no required attribute key list or leakage-negative assertion (R1-S5, R1-F5). |
| FR-17 — Idempotent bootstrap hooks | Step 6 | Partial | All three hooks present (CLI callback, `__init__`, public `hydrate`); concurrency safety of the guard unaddressed (R1-S3, R1-F9). |
| NR-1..NR-6 (non-requirements) | n/a | Covered | Plan respects read-only, no-CLI-shellout, service-token-only scope; no violations observed. (Multi-config scoping ambiguity noted in R1-F6, but NR scope is honored.) |
