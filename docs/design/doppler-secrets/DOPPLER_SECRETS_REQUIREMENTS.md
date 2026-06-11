# Doppler Secrets Management Integration — Requirements

**Version:** 0.4 (NR-7 runtime rotation promoted → FR-ROT-1..6, IMPLEMENTED)
**Date:** 2026-06-11
**Status:** v0.3 shipped+merged; v0.4 adds runtime rotation (FR-ROT) — IMPLEMENTED 2026-06-11

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass (see `DOPPLER_SECRETS_PLAN.md`) verified the resolution path against the real code
> and overturned the central assumption behind FR-4.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Providers resolve credentials through `ConfigManager.get_api_key()`, so editing it inserts Doppler everywhere | **False.** Providers each call `config.get('api_key') or os.getenv('X')` **directly** — 8+ call sites across `anthropic.py:292`, `gemini.py:299`, `openai.py:265/356/417/482-505`, `mistral.py:111/134`. `get_api_key()` itself has only **2 callers**. | **FR-4 reframed** from "extend the central getter" to **environment hydration** (populate `os.environ` for absent keys). Zero provider edits; existing `os.getenv()` calls transparently see Doppler values. |
| Resolution is one-secret-at-a-time | Doppler's download endpoint returns the **whole config** as one JSON map | Hydration is the natural model: one fetch → many env vars. **OQ-4 resolved.** |
| Doppler I/O slots into `validate_config()` | That fires a blocking HTTP call on every agent creation | **Front-load** the fetch once at startup, idempotently. **OQ-5 resolved.** |
| There's a single SDK init point to hook | `discover()` is called from ~10 scattered sites; **no `@app.callback`** exists; no package auto-init | New **FR-17**: hydration must be wired at deliberate, idempotent bootstrap points (CLI callback + `AgentFramework.__init__` + explicit `hydrate()`). |
| Doppler SDK vs REST undecided | Hydration needs one endpoint; REST + httpx reuses `resilience/`/`ratelimit/` | **Direct REST, no new dependency. OQ-1 & OQ-7 resolved** (no `[doppler]` extra). |

**Resolved open questions:**
- **OQ-1 → Direct REST.** Call the v3 download endpoint with httpx; do not depend on the Doppler SDK.
- **OQ-4 → Whole-config fetch.** One download call populates the in-memory cache / environment.
- **OQ-5 → Front-loaded fetch.** Hydrate once at startup, not inside the per-agent sync path.
- **OQ-6 → 0 provider edits.** The ~8 `os.getenv` sites are *bypassed* by hydration, not rewritten.
- **OQ-7 → No optional extra.** Direct REST means no new packaged dependency.
- **OQ-2 → Inject-all-if-absent (default) + optional allowlist.** Doppler-native by default; allowlist
  caps blast radius for embedded callers. Folded into FR-4.
- **OQ-3 → Fail-open (default) + fail_closed opt-in.** Plus: downstream missing-key errors must
  reference the earlier Doppler failure so fail-open never hides the root cause. Folded into FR-13.

This is a >30% revision of the resolution mechanism — the loop caught it at document cost rather
than after editing every provider.

---

## 1. Problem Statement

Today the startd8 SDK resolves provider credentials (and other secrets) from exactly two
sources, in a fixed precedence: **environment variable first, then a local JSON config file**
(`~/.startd8/config.json`). Every provider repeats the same idiom:

```python
api_key = config.get('api_key') or os.getenv('ANTHROPIC_API_KEY')
```

This works for a single developer on one machine but has gaps for teams, CI, and
multi-environment deployments:

| Component | Current State | Gap |
|-----------|--------------|-----|
| Provider API keys | `config.get() or os.getenv()` per provider (`providers/*.py`) | No centralized/managed secret source; keys live in shell env or plaintext-ish JSON |
| Config file | `~/.startd8/config.json`, owner-only perms (`config.py:177-232`) | Secrets at rest on disk; no rotation, no audit, no per-environment scoping |
| Secret resolution | `ConfigManager.get_api_key()` | No pluggable backend; can't swap in a managed secrets store |
| Team/CI workflows | Manual env var export | No single source of truth; secret sprawl across `.env` files and CI variables |
| Rotation / audit | None | No central rotation *control point*; no access log. (Doppler centralizes the control point — rotate once in Doppler; processes pick it up on next start. In-process zero-downtime refresh is **out of scope for v1** — see NR-7.) |
| Per-environment scoping | Single flat config | No per-env separation. (Doppler closes this via per-config tokens; v1 resolves **one** config per process — multi-config-at-once is deferred, NR-8.) |

**Doppler** (doppler.com) is a managed secrets platform that addresses these gaps. It organizes
secrets as **Workplace → Project → Config** (config = an environment such as `dev`/`stg`/`prd`),
and exposes secrets via:
- **Service tokens** — read-only, scoped to a single project+config, Bearer-auth.
- **REST API** — `GET https://api.doppler.com/v3/configs/config/secrets/download?format=json`
  returns all secrets for the token's config as a JSON map.
- **CLI** (`doppler run -- <cmd>`) — injects secrets as environment variables into a child process.
- **OIDC / service-account identities** — keyless auth for AWS/K8s/GitHub runners.
- Official **Python SDK**.

**What should exist:** a first-class, optional **secrets-backend abstraction** in the SDK with a
**Doppler backend** as the first concrete implementation, so that provider credentials (and other
SDK secrets) can be sourced from Doppler — without changing any provider code and without breaking
the existing env-var-first workflow.

## 2. Goals / Non-Goals at a Glance

- **Goal:** make Doppler a drop-in secret source that slots *underneath* the existing
  `get_api_key()` resolution, behind a pluggable interface, off by default.
- **Goal:** zero required changes to provider modules.
- **Non-goal:** replacing the existing env-var/config-file flow; Doppler is additive and optional.
- **Non-goal:** writing/managing secrets *into* Doppler from the SDK (read-only consumer first).

## 3. Requirements

### Core abstraction
- **FR-1 — SecretsProvider protocol.** Define a `SecretsProvider` Protocol mirroring the existing
  `AgentProvider` pattern (`providers/protocol.py`), with at minimum: `name`, `get_secret(key) ->
  Optional[str]`, `get_all_secrets() -> dict[str,str]`, `validate_config() -> bool`,
  `get_required_env_vars() -> list[str]`.
- **FR-2 — Entry-point discovery.** Register secrets backends under a new
  `startd8.secrets` entry-point group with a `SecretsProviderRegistry.discover()` that mirrors
  `ProviderRegistry.discover()` (`providers/registry.py:109-207`), including the built-in fallback
  path. Ship two backends: `local` (current behavior) and `doppler`.
- **FR-3 — Doppler backend.** Implement `DopplerSecretsProvider` that reads all secrets for a
  configured service token via the v3 download endpoint and exposes them through the
  `SecretsProvider` interface.

### Resolution & precedence
- **FR-4 — Environment hydration (reframed in v0.2).** Resolution is achieved by **hydrating
  `os.environ`**: at startup the active backend fetches its secrets and sets each key into the
  environment **only if not already present**. Because every provider already calls
  `os.getenv(...)`, Doppler values become visible with **zero provider changes**, and the existing
  precedence is preserved end-to-end: explicit `config['api_key']` > env var (possibly
  Doppler-populated) > local config file. A generic `SecretsManager.get_secret(name)` is also
  provided for non-env consumers. (v0.1 proposed extending `ConfigManager.get_api_key()` as the
  chokepoint; planning showed providers bypass it — see §0.)
  - **Default scope (OQ-2 resolved): inject-all-if-absent.** Every secret in the Doppler config is
    hydrated, but only for keys not already in `os.environ` (Doppler-native, matches `doppler run`).
    An **optional `secrets_backend.allowlist`** restricts hydration to named keys for embedded/library
    callers who want to cap blast radius into the host process environment.
  - **FR-4a — Process-control deny-list (R1-F1, critical).** Hydration MUST NOT introduce or overwrite
    process-control environment variables even if present in the Doppler config: at minimum `PATH`,
    `LD_PRELOAD`, `LD_LIBRARY_PATH`, `DYLD_*`, `PYTHONPATH`, `PYTHONSTARTUP`, `IFS`, `BASH_ENV`. Such a
    key is **skipped with a masked warning**, never injected. This deny-list is unconditional and
    independent of the optional allowlist — `inject-all-if-absent` trusts the config to hold only
    credentials, and a misconfigured/compromised config injecting `LD_PRELOAD` would be a host-process
    code-execution surface created by the hydration mechanism itself.
  - **FR-4b — Allowlist fail-safe semantics (R1-F8).** Allowlist resolution is unambiguous and
    fail-safe: **absent/unset ⇒ inject-all-if-absent** (default); **empty list `[]` ⇒ hydrate nothing**;
    an allowlist naming an unknown key simply yields that key's absence (no error). The safe reading of
    an explicit empty list is "inject none," never "inject all."
- **FR-5 — Source transparency.** `SecretsManager.get_secret_source(name)` (and
  `get_api_key_source()`) must report whether a value came from `env`, `doppler`, or `local`.
  - **FR-5a — `local`-backend attribution (R1-F4).** Because the `local` backend hydrates nothing,
    no key is ever attributed to `local` via the hydration path. The contract must define
    `get_secret_source()` for the always-on default explicitly: a value found in the process
    environment is `env`; a value read from `~/.startd8/config.json` is `config`; `local` denotes the
    active backend, not a value provenance. `get_secret(name)` on the `local` backend returns the
    env/config-resolved value (mirroring today's `get_api_key()`), and `get_all_secrets()` returns `{}`.
- **FR-6 — Caching / single fetch.** Fetch the whole Doppler config **once per process** (the
  download endpoint returns the entire config map in one call); serve subsequent lookups from an
  in-memory cache. Hydration itself must be **idempotent** (guarded against re-running).
  - **FR-6a — Thread-safety (R1-F9).** "Idempotent" is not "thread-safe." Because hydration is wired
    into `AgentFramework.__init__` (FR-17) which embedded callers may construct from multiple threads,
    the guard-flag check and `os.environ` writes MUST be protected by a module-level lock (or a
    documented single-thread-bootstrap constraint). Acceptance: N concurrent `AgentFramework`
    constructions trigger **exactly one** fetch and leave `os.environ` in a consistent state.
  - **FR-6b — No runtime re-hydration in v1 (R1-F3; see NR-7).** The single-fetch + idempotent guard
    means a long-lived process does not pick up rotated secrets without a restart. This limit is
    **accepted for v1** (NR-7); the cache exposes no TTL or `force` refresh. If runtime rotation is
    later required, it is a deliberate follow-on, not an implicit expectation of FR-6.

### Configuration
- **FR-7 — Backend selection config.** Add a `secrets_backend` section to the SDK config
  (`config.py`) and/or env vars (`STARTD8_SECRETS_BACKEND=doppler`) selecting the active backend.
- **FR-8 — Doppler auth config.** Support a Doppler service token via `DOPPLER_TOKEN` env var
  (Doppler's own convention) and/or SDK config. Optionally support `DOPPLER_PROJECT` /
  `DOPPLER_CONFIG` where relevant.
  - **FR-8a — Single-token / single-config scope in v1 (R1-F6; see NR-8).** One service token
    resolves exactly one project+config, so the "per-environment scoping" benefit (§1) is realized by
    **swapping tokens**, not by targeting multiple configs at once. v1 supports exactly one active
    backend resolving one config; simultaneous multi-config / multi-project resolution is deferred
    (NR-8).
- **FR-9 — Off by default.** If no backend is configured, behavior is identical to today
  (local backend = env → config file). No network calls unless Doppler is explicitly enabled.

### CLI
- **FR-10 — `startd8 secrets` command group.** Add a `cli_secrets.py` Typer sub-app
  (mirroring `cli_queue.py`) registered via `app.add_typer(secrets_app, name="secrets")` with:
  - `secrets status` — show active backend, which secrets resolve and from where (masked).
  - `secrets test` — validate connectivity/auth to the configured backend.
  - `secrets list` — list available secret names (values masked).
- **FR-11 — Masking everywhere.** All secret values shown in CLI/logs must pass through
  `security.mask_api_key()` (`security.py:137-154`). Never print a full secret.

### Resilience & security
- **FR-12 — HTTP client reuse.** Use `httpx` with the SDK's existing `resilience/` retry and
  `ratelimit/` patterns for the Doppler API call (timeout, exponential backoff, jitter).
- **FR-13 — Failure semantics (configurable; OQ-3 resolved).** Default **fail-open**: on a Doppler
  fetch failure (network/auth) log a **loud masked warning** and continue with the un-hydrated
  environment (env/config still apply), so a Doppler outage never bricks an otherwise-working setup.
  To avoid fail-open masking the real cause, a **subsequent missing-secret error must reference the
  earlier Doppler failure** (e.g. "ANTHROPIC_API_KEY not set — note: Doppler fetch failed earlier:
  <masked>"). A `fail_closed` option raises `ConfigurationError` (from `exceptions.py`) immediately
  with an actionable message for environments that require Doppler to be authoritative.
  - **FR-13a — Bounded fail-open signalling (R1-F7).** The fail-open warning is emitted **exactly once
    per hydration** at **`WARNING`** level (not `INFO`) — "loud" is defined, not implied. The deferred
    root-cause note appended to downstream missing-key errors must be **bounded** (referenced once per
    error, not accumulated across N missing keys) and must reuse the masked failure string — it must
    never re-expose raw or full-length token material.
- **FR-14 — No secret-at-rest by default.** The Doppler backend must not write fetched secrets to
  disk. If local caching is ever added, it must reuse `security.KeyEncryption` and owner-only perms.
  This is a **testable negative invariant**, not merely an absence of caching code (see plan Step 9 /
  Step 10): a hydration run must leave no new file containing secret material.
- **FR-15 — Logging hygiene.** Use `get_logger` (per repo policy); never log raw token or secret
  values; log only masked forms and source labels.
- **FR-15a — Child-process / token-inheritance boundary (R1-F2, high).** The token and secret-leakage
  surface includes the very `os.environ` that hydration mutates, which every `subprocess` the SDK or
  host spawns inherits. Therefore: (a) the bearer `DOPPLER_TOKEN` is **read for the fetch and never
  written into `os.environ`** by hydration; (b) the requirements must state explicitly whether
  hydrated *secrets* are intended to flow to subprocesses (`doppler run` semantics — the default, since
  child tools may legitimately need the same provider keys) — this is a documented, tested boundary,
  not an accident. Acceptance: after `hydrate()`, a spawned child sees the intended keys and **does not**
  see `DOPPLER_TOKEN`.

### Telemetry
- **FR-16 — OTel spans (testable; R1-F5).** Wrap Doppler fetches in an OTel span with a canonical,
  enumerated attribute set so the requirement is verifiable: span name `secrets.hydrate` (and/or
  `secrets.fetch`) with attributes `secrets.backend`, `secrets.project`, `secrets.config`,
  `secrets.cache_hit` (bool), `secrets.outcome` (`ok|fail_open|fail_closed`), and `secrets.key_count`.
  **Negative requirement:** no span attribute, event, or status message may contain a secret or token
  value (masked or otherwise). Acceptance: an in-memory span exporter shows the required keys present
  and asserts no attribute value equals any known secret/token fixture.

### Bootstrap (added in v0.2)
- **FR-17 — Idempotent bootstrap hooks.** Because there is no single SDK init chokepoint (`discover()`
  is called from ~10 sites; no CLI `@app.callback` exists), hydration must be wired at deliberate,
  idempotent points: (a) a new `@app.callback` in `cli.py` (runs before any subcommand), (b)
  `AgentFramework.__init__`, and (c) a public `startd8.secrets.hydrate()` for library users who
  construct providers directly. Re-invocation must be a guarded no-op, and the guard must be
  **thread-safe** (FR-6a) since `AgentFramework.__init__` may be reached concurrently.

### Runtime rotation (added in v0.4 — promotes former NR-7)
> Closes the §1 "rotate centrally" contradiction by adding an explicit in-process refresh path.
> The single load-bearing design decision is **FR-ROT-2**.

- **FR-ROT-1 — Explicit refresh.** A public `SecretsManager.refresh()` / `startd8.secrets.refresh()`
  re-fetches the active backend (busting its cache) and re-hydrates, under the same module lock as
  `hydrate()` (FR-6a). For the `local` backend it is a no-op.
- **FR-ROT-2 — Refresh overwrites only backend-owned keys (the key decision).** On refresh, a key is
  updated in `os.environ` **only if the SDK injected it** (tracked in the `_source_map` from FR-5).
  Keys the user/shell set explicitly are **never overwritten** — "explicit env always wins" must hold
  across rotation exactly as it does at first hydration. A rotated Doppler value therefore updates the
  process iff the SDK owns that key; a user-pinned key is left intact. (Without this, refresh would
  either clobber user overrides or fail to pick up rotations — both wrong.)
- **FR-ROT-3 — Backend cache invalidation.** The Doppler backend must expose a way to force a fresh
  fetch (e.g. `get_all_secrets(force=True)` / `invalidate()`); refresh must not return the stale
  in-process cache (supersedes the FR-6 single-fetch limit *only* on explicit refresh).
- **FR-ROT-4 — Optional TTL (lazy).** An optional `secrets_backend.ttl_seconds` (env
  `STARTD8_SECRETS_TTL`) enables **lazy** auto-refresh: the next `hydrate()`/`get_secret()` after the
  TTL elapses triggers one refresh. No background thread. TTL unset/0 ⇒ fetch-once (today's behavior).
- **FR-ROT-5 — Refresh failure is fail-open-preserving.** A failed refresh fetch must not wipe the
  already-hydrated environment: on error, keep the prior values, honor FR-13 fail-open/closed, and
  record the masked failure (FR-13a). A refresh must never leave the process *worse* than before it.
- **FR-ROT-6 — CLI + telemetry.** `startd8 secrets refresh` forces a refresh and reports what changed
  (counts only, masked). The refresh fetch reuses the FR-16 OTel span (with `secrets.refresh=true`).

## 4. Non-Requirements

- **NR-1** Writing or mutating secrets in Doppler (create/update/delete). Read-only consumer only.
- **NR-2** Replacing or deprecating the env-var / `~/.startd8/config.json` path.
- **NR-3** Bundling/shelling out to the Doppler CLI (`doppler run`). The SDK talks to the API directly.
- **NR-4** OIDC / service-account identity auth in v1 (service token only first). Track for later.
- **NR-5** Other managed backends (Vault, AWS Secrets Manager, 1Password). The abstraction must
  *allow* them, but only `local` + `doppler` ship now.
- **NR-6** Secrets sync/mirroring into CI provider variables.
- **NR-7 — ~~Runtime secret rotation~~ → PROMOTED to FR-ROT-1..6 (v0.4).** Originally deferred in v0.3;
  now in scope. Runtime refresh (explicit `refresh()` + optional lazy TTL) is specified above; the
  load-bearing rule is FR-ROT-2 (refresh overwrites only SDK-injected keys, never user env).
- **NR-8 — Simultaneous multi-config / multi-project resolution (R1-F6).** One active backend resolves
  one project+config (one service token). Targeting dev+prd (or multiple Doppler projects) at once
  within a single process is deferred; the v1 "per-environment scoping" story is achieved by selecting
  the appropriate token/config per process.

## 5. Open Questions

> **All resolved.** OQ-1/4/5/6/7 resolved during planning; OQ-2/3 resolved by operator decision
> (2026-06-10). See §0 for the dispositions. No open questions remain.

---

*v0.3 — Post-CRP. R1 review (claude-opus-4-8-1m) triaged: 9/9 F-suggestions accepted and applied
(security: FR-4a deny-list, FR-15a token/subprocess boundary, FR-6a thread-safety; correctness:
FR-5a, FR-13a, FR-16; honest scope-outs: NR-7 rotation, NR-8 multi-config). Dispositions in
Appendix A. Predecessor: v0.2.1 (planning) — reframed FR-4 to env hydration, resolved 7 OQs. Paired
plan: `DOPPLER_SECRETS_PLAN.md` v1.1.*

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
| R1-F1 | Process-control deny-list (PATH/LD_PRELOAD/…) | R1 (claude-opus-4-8-1m) | Applied as **FR-4a** — unconditional deny-list, skip-with-masked-warning, independent of allowlist. | 2026-06-10 |
| R1-F2 | Child-process / DOPPLER_TOKEN inheritance boundary | R1 | Applied as **FR-15a** — token never hydrated into `os.environ`; subprocess secret-inheritance made an explicit, tested boundary. | 2026-06-10 |
| R1-F3 | Rotation / cache-invalidation contradiction | R1 | Applied as scope-out: **NR-7** (restart-to-rotate is the v1 limit) + **FR-6b** + §1 wording fixed to "control point, not in-process refresh". Operator-flagged; TTL/force-refresh available as a deliberate follow-on. | 2026-06-10 |
| R1-F4 | `local`-backend `get_secret_source` contract | R1 | Applied as **FR-5a** — env vs config vs backend-label semantics defined; `local.get_all_secrets()==[]`. | 2026-06-10 |
| R1-F5 | Testable OTel attrs + leakage-negative | R1 | Applied to **FR-16** — enumerated span/attr keys + negative assertion via in-memory exporter. | 2026-06-10 |
| R1-F6 | Multi-config / multi-project scoping | R1 | Applied as scope-out: **FR-8a** (single-token/single-config v1) + **NR-8** (multi deferred) + §1 scoping caveat. | 2026-06-10 |
| R1-F7 | Bounded/loud fail-open warning | R1 | Applied as **FR-13a** — WARNING level, once-per-hydration, non-accumulating masked root-cause note. | 2026-06-10 |
| R1-F8 | Allowlist empty/malformed fail-safe | R1 | Applied as **FR-4b** — absent⇒inject-all, `[]`⇒inject-none, unknown key⇒absent/no-error. | 2026-06-10 |
| R1-F9 | Thread-safe hydration guard | R1 | Applied as **FR-6a** + cross-ref in **FR-17** — module-level lock, exactly-one-fetch acceptance test. | 2026-06-10 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-10

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-10 20:05:00 UTC
- **Scope**: Requirements quality for a credential-handling integration that mutates `os.environ` inside an embedded library. Weighting security, ops, interface contracts, and failure-mode/edge-case testability per the review mandate.

**Executive summary (top risks / gaps in the requirements):**

- `os.environ` mutation is process-global and **not thread-safe**; FR-4/FR-6 say "idempotent" but never address concurrent hydration or interpreter-wide blast radius for embedded callers.
- The very hydration mechanism can **leak `DOPPLER_TOKEN` and fetched secrets to child processes** — every `subprocess` the SDK or host app spawns inherits the injected env. No requirement bounds this.
- FR-5/FR-13 promise a per-key **source map** and root-cause-preserving errors, but no requirement defines what `get_all_secrets()` returns for the `local` backend (`{}`) vs. how source attribution stays correct after env mutation.
- **Rotation / cache-invalidation** is a stated motivation (§1 "rotate a leaked key centrally") yet FR-6 mandates fetch-once-per-process with no re-hydrate / TTL / invalidation path — the feature cannot deliver its own headline benefit at runtime.
- No requirement covers **multi-config / multi-project scoping** (one token = one project+config) although §1 sells "per-environment scoping" as a gap Doppler closes.
- FR-16 OTel attributes are asserted but **untestable as written** (no required attribute keys/values, no negative assertion that secret/token values never appear as span attributes).
- FR-4 "inject-all-if-absent" silently lets Doppler set **arbitrary, non-credential env vars** (`PATH`, `PYTHONPATH`, `LD_PRELOAD`-class) into the host process — a code-execution / hijack surface with no deny policy required.
- Allowlist (OQ-2) caps blast radius but its **interaction with FR-9 "off by default"** and with the `local` backend is unspecified (does empty allowlist mean "hydrate nothing" or "hydrate all"?).

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | critical | Add a requirement that hydration MUST NOT overwrite or introduce process-control env vars (`PATH`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `PYTHONPATH`, `PYTHONSTARTUP`, `IFS`, etc.); a Doppler config containing such a key must be skipped-with-warning, not injected. | "inject-all-if-absent" (FR-4) trusts the Doppler config to contain only credentials. A compromised/misconfigured config can inject an env var that hijacks subprocess execution in the host process — a privilege-escalation surface created by the hydration mechanism itself. | FR-4, after the "Default scope (OQ-2 resolved)" bullet | Unit test: config containing `LD_PRELOAD` is not written to `os.environ` and emits a masked warning; assert `os.environ` unchanged for that key. |
| R1-F2 | Security | high | Add a requirement addressing `DOPPLER_TOKEN` and fetched-secret **inheritance by child processes**: state explicitly whether injected secrets are intended to flow to subprocesses (`doppler run` semantics) or be confined, and if confined, require the token itself never be hydrated into `os.environ`. | FR-15 covers *logging* leakage but not *env inheritance* leakage. Any `subprocess.run`/`Popen` in the SDK (or host app) inherits the mutated environment, exporting every secret + the bearer token to arbitrary children. This is the dominant real-world leak path for env-hydration designs. | New FR under "Resilience & security", or extend FR-14 | Test: spawn a child process after hydration; assert which keys are visible; assert `DOPPLER_TOKEN` is absent from the child env. |
| R1-F3 | Data | high | Specify the **rotation / re-hydration contract**: either (a) explicitly declare runtime rotation out of scope in §4 Non-Requirements with a forward note, or (b) add an FR for a TTL / explicit `hydrate(force=True)` cache-invalidation path. | §1 lists "rotate a leaked key centrally" and "per-environment scoping" as the gaps Doppler fixes, but FR-6 ("once per process", idempotent, guarded) makes rotation impossible without a process restart — the requirements promise a benefit they then design out. This is an internal contradiction a reader/implementer cannot resolve. | FR-6 (add invalidation clause) or §4 (add NR-7) | Acceptance: a documented mechanism to refresh secrets within a long-lived process, OR an explicit NR stating restart-to-rotate is the accepted v1 limitation. |
| R1-F4 | Interfaces | high | Define the **`local` backend contract for `get_all_secrets()` and `get_secret(key)` / `get_secret_source`** precisely: FR-2/FR-3 give `local` an empty `get_all_secrets()` (`{}`), but FR-5 requires `get_secret_source` to return `env`/`doppler`/`local` — clarify how a value sourced from the config file or env is labeled when the local backend returns nothing to hydrate. | FR-5 promises `local` as a source label, but the local backend by design hydrates nothing, so no key is ever attributed to `local` via the hydration path. The interface contract for the default (and only always-on) backend is underspecified, making FR-5 untestable for the common case. | FR-5 and FR-1 (clarify `get_secret` semantics for `local`) | Unit test on `local` backend: `get_secret_source("ANTHROPIC_API_KEY")` returns a defined, documented value for env-sourced and config-file-sourced keys. |
| R1-F5 | Validation | high | Make FR-16 OTel assertions testable: enumerate the **required span name and attribute keys** (e.g. `secrets.backend`, `secrets.cache_hit`, `secrets.outcome`, `secrets.project`, `secrets.config`) and add a **negative requirement** that no span attribute, event, or status message contains a secret or token value (even masked-by-accident). | FR-16 as written ("attributes for backend name, project/config, cache hit/miss, outcome") cannot be verified — there is no canonical key list and no prohibition that pins the leakage boundary. OTel attributes are a common silent exfiltration path. | FR-16 | Test with an in-memory OTel span exporter: assert required attribute keys present; assert no attribute value matches any known secret/token fixture. |
| R1-F6 | Data | medium | Add a requirement for **multi-config / multi-project scoping** behavior (or explicitly scope it out): one service token resolves exactly one project+config, so "per-environment scoping" (§1) is achieved only by swapping tokens. State whether multiple simultaneous backends/configs are supported in v1 or deferred. | §1 advertises "per-environment scoping" and "no per-environment scoping" as the current gap, but the design binds one token → one config with no requirement describing how an app targeting dev+prd simultaneously (or multiple Doppler projects) behaves. | New FR under "Configuration", or §4 Non-Requirements | Acceptance: requirement states single-token/single-config is the v1 model (with `DOPPLER_PROJECT`/`DOPPLER_CONFIG` selecting one), and multi-config is explicitly deferred. |
| R1-F7 | Risks | medium | Tighten FR-13: define **what "loud masked warning" means operationally** (log level, single-emit vs. per-key) and require that the fail-open warning is emitted **exactly once** and that the deferred root-cause note (the "Doppler fetch failed earlier" string) does not itself re-expose the masked token across many downstream missing-key errors. | FR-13's root-cause-preservation is good but unbounded: if 12 keys are missing after a fail-open, the masked failure string could be appended 12 times, and "loud" is undefined (could be `INFO`). Ambiguity makes the failure UX and the masking boundary untestable. | FR-13 | Test: simulate fetch failure + 3 missing keys; assert one WARNING at hydration time and that each downstream error references the failure without duplicating raw/masked token material. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Security | high | Require that an **empty or malformed `secrets_backend.allowlist`** has fail-safe semantics (empty list = hydrate nothing, not hydrate-all) and that allowlist + "off by default" (FR-9) compose unambiguously. | The allowlist is the only blast-radius control for embedded/library callers (the stated audience), yet its empty/absent/malformed semantics are undefined — the dangerous default (absent ⇒ inject-all) versus the safe default (empty ⇒ inject-none) is exactly the footgun an embedded host would trip on. | FR-4 "optional `secrets_backend.allowlist`" bullet | Test matrix: allowlist absent ⇒ inject-all-if-absent; allowlist `[]` ⇒ inject none; allowlist with unknown key ⇒ that key simply absent, no error. |
| R1-F9 | Validation | medium | Add an acceptance criterion that hydration is **concurrency-safe**: FR-6's "idempotent / guarded" must specify the guard is safe under threads (e.g. `AgentFramework` instances constructed on multiple threads) — either a lock or a documented single-thread-bootstrap constraint. | FR-17 wires hydration into `AgentFramework.__init__`, which embedded callers may invoke from multiple threads; a bare boolean guard plus `os.environ` writes is a data race that can double-fetch or partially hydrate. The requirement says "idempotent" but never says "thread-safe", and those differ. | FR-6 and FR-17 | Test: construct N `AgentFramework` instances concurrently; assert exactly one fetch occurs and `os.environ` is consistent. |

**Endorsements**: (none — R1 is the first round; no prior untriaged suggestions exist.)
**Disagreements**: (none — no prior suggestions to disagree with.)
