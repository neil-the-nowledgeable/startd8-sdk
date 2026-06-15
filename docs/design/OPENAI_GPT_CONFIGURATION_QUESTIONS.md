# OpenAI / GPT Configuration — Open Questions to Resolve

**Date:** 2026-06-02
**Status:** Answered — decisions below unblock the multi-model comparison run
**Context:** Surfaced while verifying the landmark + secondary model matrix for the E2E
multi-model comparison (`startd8 compare-models-e2e`). The Anthropic and Google picks are
callable; the **OpenAI tier needs decisions** because the catalog's configured flagship is not
usable via the SDK's current API path.

---

## Background — what we found

1. **`gpt-5.5-pro` is not a chat-completions model.** A live call returns:
   `404 — "This is not a chat model and thus not supported in the v1/chat/completions endpoint.
   Did you mean to use v1/completions?"` It is a Responses-API (`v1/responses`) "pro" reasoning
   model. The SDK's OpenAI agent (`agents/openai.py`) uses `chat.completions.create(...)`, so
   `gpt-5.5-pro` **cannot be called** today.
2. **`model_catalog.GPT_FLAGSHIP_LATEST` points at `gpt-5.5-pro`** — i.e. the catalog's designated
   OpenAI flagship is currently uncallable through the SDK. Pricing exists for it, which masks the
   problem (cost would compute, but generation 404s).
3. **What *is* callable** (proven this session): `gpt-5.5` (standard, won run-012), `gpt-5.4-mini`,
   `gpt-5.4-nano` (cost-efficiency sweep), and the gpt-4o/4.1 families. The gpt-5/o-series
   `max_completion_tokens` + default-temperature requirement is already handled
   (`requires_max_completion_tokens` / `_build_chat_kwargs`, on `main`).
4. **Worktree venv gap:** the E2E worktree `.venv` was installed with `[dev]` only and is **missing
   provider SDKs** (`openai`/`anthropic`/`google-genai`). In-process provider calls (inline backend,
   any future S0 provider-validation) fail there; iTerm2 stages currently work only because they run
   in the default shell's main venv.

---

## Questions to answer

### Q1 — Which model is the OpenAI **landmark** for the comparison?

The catalog flagship (`gpt-5.5-pro`) is not chat-callable. Options:

- **(A, recommended) Use `gpt-5.5`** as the landmark. Top chat-callable GPT-5 model; already proven
  (decisively won the 15-task run-012 vs Gemini). Zero new work.
- **(B) Use an o-series reasoning model** that *is* chat-callable (e.g. `o3`) as the "reasoning
  flagship." Needs a quick callability check; o-series uses `max_completion_tokens` (already handled).
- **(C) Add Responses-API support** (see Q2) to use the true `gpt-5.5-pro`.

**Decision:** **A — use `openai:gpt-5.5` as the OpenAI landmark for this comparison.**
It is the top GPT-5.5 model that is callable through the SDK's current Chat Completions path,
it has already been proven in prior comparison work, and it avoids blocking the E2E run on
Responses-API support.

### Q2 — Do we add Responses-API (`v1/responses`) support to the SDK OpenAI agent?

Required to call `gpt-5.5-pro` / `o*-pro` models at all. This is **real SDK work**, not a config
swap: a second code path in `agents/openai.py` (request shape, response parsing, token/cost mapping,
streaming differences) plus tests.

- Worth it if "true flagship" comparisons are a recurring need.
- Not worth it if `gpt-5.5` is an acceptable OpenAI landmark for now.

**Decision (build now / defer / never):** **Defer.**
Do not add Responses-API support as part of this E2E configuration pass. Treat it as follow-up SDK
work with its own tests because it requires a second request/response parsing path, token accounting
updates, and likely streaming differences. Build it later only if `gpt-5.5-pro` or other
Responses-only models become required comparison targets.

### Q3 — Fix `model_catalog` so the configured flagship is actually callable?

`GPT_FLAGSHIP_LATEST = gpt-5.5-pro` is misleading — it names an uncallable model as the default
flagship, so anything resolving `get_latest_model("openai","flagship")` silently targets a 404.
Options:

- **(A)** Repoint `GPT_FLAGSHIP_LATEST` → `gpt-5.5` (callable) until/unless Responses API lands.
- **(B)** Keep `gpt-5.5-pro` but add a `callable_via` / `api_surface` attribute and have resolution
  skip/flag Responses-only models for chat callers.
- **(C)** Leave as-is and rely on callers to avoid it (status quo — fragile).

**Decision:** **A now; consider B when Responses support exists.**
Repoint `GPT_FLAGSHIP_LATEST` to `openai:gpt-5.5` on `main` so "latest flagship" resolves to a model
the current SDK can actually call. A richer `api_surface` / `callable_via` field would be useful later,
but it should land with the Responses-API work rather than blocking this run.
*(Note: this is a change on `main`'s `model_catalog`, not just the E2E branch.)*

### Q4 — Which model is the OpenAI **secondary** tier?

Catalog "balanced" = `gpt-5.5` — but if `gpt-5.5` becomes the landmark (Q1-A), the secondary needs
to be a tier down. Options: `gpt-5.4-mini` (catalog "mini", proven) or `gpt-5.4` (if a distinct
standard exists and is callable).

- Cross-provider note: pairs against Anthropic `claude-sonnet-4-6` and Google `gemini-2.5-flash`.
  `gpt-5.4-mini` ≈ `gemini-2.5-flash` in tier; `claude-sonnet-4-6` is heavier — the secondary band
  is not perfectly matched across vendors.

**Decision:** **Use `openai:gpt-5.4-mini` as the OpenAI secondary tier.**
Because `gpt-5.5` is promoted to the landmark slot, the secondary should move one tier down to the
proven callable, lower-cost GPT-5.x option. Do not wait on a hypothetical `gpt-5.4` standard model
for this matrix.

### Q5 — Are o-series reasoning models (`o3`, `o4-mini`, …) in scope?

The param fix already routes them to `max_completion_tokens` + default temperature. If we want a
"reasoning model" lane in the comparison, confirm which o-series models are chat-callable on this key
and whether to include them. (`o1-pro`/`o3-pro` are likely Responses-only, same as Q1/Q2.)

**Decision:** **Out of scope for the landmark/secondary matrix; optional separate reasoning lane only.**
Live checks on 2026-06-02 confirmed `o3` and `o4-mini` are chat-callable with the current
`max_completion_tokens` path. Keep them out of the core two-tier cross-provider comparison so the
matrix remains simple. If a reasoning lane is added, use `openai:o3` as the primary o-series entry
and optionally `openai:o4-mini` as the cheaper reasoning entry. Do not include `o3-pro` in this run:
this key currently receives an organization-verification access error for it.

### Q6 — Close the worktree provider-package gap?

Install `pip install -e ".[all,dev]"` (or the provider extras) in the E2E worktree `.venv` so the
harness is self-contained (inline backend + any in-process provider validation work without relying
on the default-shell main venv).

**Decision (install / leave):** **Install.**
Install the provider extras in the E2E worktree venv with `pip install -e ".[all,dev]"` so the
harness is self-contained. The comparison should not depend on whichever provider packages happen
to be installed in the default shell's main venv.

---

## Recommended default (if we just want to run)

- **Landmark:** `openai:gpt-5.5` (Q1-A), **Secondary:** `openai:gpt-5.4-mini` (Q4).
- Repoint catalog flagship to `gpt-5.5` (Q3-A) to stop the silent-404 trap.
- Defer Responses-API support (Q2) until a true-flagship comparison is actually needed.
- Install provider extras in the worktree (Q6).

This yields a fully callable matrix today:

| Tier | Anthropic | Google | OpenAI |
| --- | --- | --- | --- |
| Landmark | `claude-opus-4-8` | `gemini-2.5-pro` | `gpt-5.5` |
| Secondary | `claude-sonnet-4-6` | `gemini-2.5-flash` | `gpt-5.4-mini` |

---

## Evidence / references

- `gpt-5.5-pro` 404 "not a chat model" — live `chat.completions` call, 2026-06-02.
- `gpt-5.5` chat call succeeded and resolved to `gpt-5.5-2026-04-23`, 2026-06-02.
- `o3` chat call succeeded and resolved to `o3-2025-04-16`, 2026-06-02.
- `o4-mini` chat call succeeded and resolved to `o4-mini-2025-04-16`, 2026-06-02.
- `o3-pro` is not usable on this key today: API returned an organization-verification access error,
  2026-06-02.
- `src/startd8/model_catalog.py` — `GPT_FLAGSHIP_LATEST=gpt-5.5-pro`, `GPT_STANDARD_LATEST=gpt-5.5`,
  `GPT_MINI_LATEST=gpt-5.4-mini`, `GPT_NANO_LATEST=gpt-5.4-nano`; `get_latest_model` tier map.
- `src/startd8/agents/openai.py` — `requires_max_completion_tokens` / `_build_chat_kwargs`
  (gpt-5/o-series param handling, already on `main`).
- `docs/design/COST_EFFICIENCY_SWEEP_2026-06-01.md` — proven-callable gpt-5.x tiers.
