# Secrets Management with Doppler — How-To

The startd8 SDK can source credentials and config from a **managed secrets backend** instead of
(or in addition to) shell env vars and `~/.startd8/config.json`. The first backend is
[Doppler](https://www.doppler.com/). It is **off by default** — nothing changes until you enable it,
and it never breaks an otherwise-working setup (fail-open).

- **Design docs:** `docs/design/doppler-secrets/`
- **Package:** `src/startd8/secrets/` · **CLI:** `startd8 secrets …`

---

## How it works (the one-paragraph version)

At startup the SDK **hydrates** `os.environ` from the active backend: it fetches the whole config once
and sets each key **only if it isn't already present**. Because every provider already calls
`os.getenv(...)`, Doppler values become visible with **zero provider changes**. Precedence is preserved
end-to-end: **explicit `config['api_key']` > env var (possibly Doppler-populated) > `~/.startd8/config.json`**.
Generated all-Python apps hydrate the same way (it's baked into their `app/main.py`).

---

## Quick start

### 1. Create a Doppler project + config and add your secrets

```bash
doppler login                                   # one-time CLI auth
doppler projects create myapp                   # creates dev/stg/prd configs
# load a secret without it landing in shell history (stdin):
printf '%s' "$ANTHROPIC_API_KEY" | doppler secrets set ANTHROPIC_API_KEY -p myapp -c dev --no-interactive
```

### 2. Mint a read-only service token (scoped to one project+config)

```bash
doppler configs tokens create sdk-readonly -p myapp -c dev --plain   # prints the token ONCE
```

### 3. Point the SDK at Doppler

**Option A — env vars (per shell, Doppler-native):**
```bash
export STARTD8_SECRETS_BACKEND=doppler
export DOPPLER_TOKEN=dp.st.xxxx-the-token
```

**Option B — SDK config (persistent, owner-only `~/.startd8/config.json`):**
```jsonc
{
  "secrets_backend": {
    "backend": "doppler",
    "doppler_token": "dp.st.…",   // owner-only file; or omit and use DOPPLER_TOKEN env
    "fail_closed": false           // default: fail-open
  }
}
```

### 4. Verify

```bash
startd8 secrets test     # connectivity/auth check (exit 0 = ok; 'local' backend = no-op)
startd8 secrets status   # active backend + how each known key resolves (masked)
startd8 secrets list     # secret names available from the backend (values masked)
```

---

## Behavior & guarantees

| Concern | Behavior |
|---------|----------|
| **Default** | `local` backend — env + `~/.startd8/config.json` exactly as before; **no network**. |
| **Precedence** | explicit config arg > env (incl. Doppler-hydrated) > config file. Existing env **always wins**. |
| **Dangerous keys** | `PATH`, `LD_*`, `DYLD_*`, `PYTHONPATH`, … are **never** injected, even if present in Doppler (deny-list). |
| **Token safety** | `DOPPLER_TOKEN` is read for the fetch and **never** hydrated into `os.environ` (no child-process leak). |
| **Failure** | **fail-open** by default: a masked warning, continue with env/config. `fail_closed: true` to hard-error. |
| **At rest** | the backend writes **no** secrets to disk. Masked everywhere in logs/CLI/telemetry. |
| **Concurrency** | hydration is thread-safe and runs exactly once per process. |

### Optional: allowlist (cap blast radius)

To hydrate only specific keys (e.g. embedded library use):

```bash
export STARTD8_SECRETS_ALLOWLIST=ANTHROPIC_API_KEY,DATABASE_URL   # absent ⇒ all; ""(empty) ⇒ none
```
or `"allowlist": ["ANTHROPIC_API_KEY", "DATABASE_URL"]` in the config section.

---

## Rotation (no restart)

Rotate a secret in Doppler, then pick it up in a long-lived process:

```bash
startd8 secrets refresh    # force re-fetch; rotates SDK-owned keys in place
```

```python
from startd8.secrets import refresh
refresh()   # overwrites ONLY keys the SDK injected; your env/shell keys are never touched
```

**Lazy TTL** — auto-refresh on next access after N seconds (no background thread):

```bash
export STARTD8_SECRETS_TTL=300        # or "ttl_seconds": 300 in the config section
```

A failed refresh is fail-open-preserving: it keeps the current values rather than leaving the
process worse off.

---

## Using it in a generated app (deterministic `generate backend`)

Apps emitted by `startd8 generate backend` hydrate **by default** — `app/main.py` contains a guarded
hydration preamble at the top (before `app/db.py` reads `DATABASE_URL`). So a generated app run with
`uvicorn app.main:app` automatically pulls its values from the configured backend. The preamble is
fully guarded: an app shipped without `startd8`, or with the `local` backend, runs identically.

To give a generated app its values: put them in your Doppler config (e.g. `ANTHROPIC_API_KEY`,
`DATABASE_URL`, `COST_BUDGET_USD`) and enable the backend (steps 3–4 above). Use a **valid**
`DATABASE_URL` for the app's driver (e.g. `sqlite:///./app.db`), not a Prisma-style `file:` URL.

---

## Library API

```python
from startd8.secrets import hydrate, refresh, get_secret, get_secret_source

hydrate()                              # idempotent; safe to call at startup
get_secret("ANTHROPIC_API_KEY")        # value from the (possibly hydrated) env
get_secret_source("ANTHROPIC_API_KEY") # 'doppler' | 'env' | None
```

`AgentFramework()` and the `startd8` CLI already call `hydrate()` for you.

---

## Programmatic / CI notes

- **Tests never hit a real backend:** the suite forces `STARTD8_SECRETS_BACKEND=local` unless
  `STARTD8_RUN_INTEGRATION=1`, so a persisted `backend=doppler` in your config can't make unit tests
  contact your live Doppler.
- **Containers:** the generated `Dockerfile` keeps `uvicorn app.main:app`; inject `DOPPLER_TOKEN`
  (+ `STARTD8_SECRETS_BACKEND=doppler`) at the platform layer, or use `doppler run -- …`.
- **Never commit tokens.** `.gitignore` covers `*.token`, `.env.*`, `secrets.json`. `doppler.yaml`
  (non-secret project config) is fine to commit.
