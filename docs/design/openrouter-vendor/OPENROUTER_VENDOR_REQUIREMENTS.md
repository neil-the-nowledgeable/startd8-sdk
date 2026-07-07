# OpenRouter Vendor Lane — Requirements

**Version:** 0.3 (Post lessons-learned hardening — ready for CRP)
**Date:** 2026-07-06
**Status:** Draft (planning + lessons pass complete)
**Owner:** SDK / Summer 2026 Model Benchmark
**Related:** `docs/design/deepseek-vendor/` (the recipe), `docs/design/jetson-cluster-benchmark/`
(cost-lane + contamination precedents), `docs/design/local-ollama-lane/`,
[[project_summer2026_model_benchmark]], [[reference_edge_brains_contamination_probe]]

> **Why:** DeepSeek's own top-ups keep getting cancelled (cross-border card flags), blocking the
> DeepSeek-vs-`qwen-coder 0.193` contamination differential and any DeepSeek benchmark cell.
> OpenRouter is a **US-billed OpenAI-compatible aggregator** that hosts DeepSeek's V3/R1 models —
> plus Grok, Qwen, Llama — behind **one key and one bill**. It solves the payment blocker AND turns a
> single integration into access to many vendors.

---

## 0. Planning Insights (Self-Reflective Update)

> Changes from v0.1 to v0.2 after reading the provider/agent/pricing/benchmark code.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| OpenRouter needs alias translation for slash ids (like the Jetson HF-id fix) | `slug()` already maps `openrouter:deepseek/deepseek-chat` → `openrouter-deepseek-deepseek-chat` (path-safe); `sandbox_dir_name` slugs; `cell_id` embeds the raw id but is identity-only, and `rescore` recovers the spec-hash via `split(":",1)[0]`. | **FR-OR-2 simplified: pass through OpenRouter's canonical ids** — no alias map to maintain (their ids *are* the API contract). Unlike Jetson, no translation layer. |
| OpenRouter attribution headers (HTTP-Referer/X-Title) can be set on the agent | `OpenAICompatibleAgent` constructs `OpenAI(...)`/`AsyncOpenAI(...)` **without** `default_headers` — there is no header passthrough. | **FR-OR-3 → Non-Requirement (NR-OR-1):** headers are OPTIONAL (OpenRouter works without them; they only affect app-ranking on openrouter.ai). v1 skips them; a small agent change is noted for later. |
| A dedicated provider vs the generic `openai-compatible` is an open choice | The DeepSeek/Jetson dedicated-provider recipe (hardcode base_url + read env key → `OpenAICompatibleAgent`) has shipped 3× this session with **zero** benchmark-plumbing changes. | **OQ resolved → dedicated `openrouter` provider.** |
| OpenRouter cost gets the "local lane" treatment | It is a **real paid per-token API**, not $0-local. | **FR-OR-7: normal cost-ranked cloud contestant** — NO `cost_lane` special-casing (differs from Jetson/Ollama). It competes on the real cost axis. |
| The model ids I name will exist | OpenRouter renames/deprecates ids over time; the exact strings must be verified against its live `/models`. | **OQ-OR-4 added:** pin + validate enrolled ids against `GET /models` (an alias-drift guard, mirroring Jetson FR-J3a). |

**Resolved open questions:**
- **OQ (provider shape) → dedicated `openrouter` provider** (DeepSeek recipe; zero plumbing).
- **OQ (slash ids) → pass-through canonical ids** (`slug()` makes them safe; no alias layer).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied SDK design-doc lessons before CRP. Each changed or verified the draft:

- **[Phantom-reference audit]** — verified the exact enrolled model ids against OpenRouter's **live**
  `GET /models` (343 models, 2026-07-06): `deepseek/deepseek-chat` ✓, `deepseek/deepseek-r1` ✓,
  `qwen/qwen-2.5-coder-32b-instruct` ✓ — none are phantoms. Confirmed `qwen-2.5-coder-32b` is the same
  2.5 family as the local `qwen2.5-coder:7b`, so FR-OR-10's scale-controlled comparison is valid.
  (Newer `deepseek-chat-v3.1` / `qwen3-coder*` exist but the pinned ids are the deliberate, motivated
  choice.) Strengthens OQ-OR-4 with a confirmed baseline.
- **[Single-source vocabulary ownership]** — the contamination caveat and the cost-lane decision are
  **owned** by the Jetson/DeepSeek specs; FR-OR-7 and FR-OR-10 **cite** them (Jetson OQ-J3, FR-J8/NR-J7)
  rather than restate-and-drift.
- **[Prune phantom scope]** — OpenRouter attribution headers are architecturally out for v1 (no agent
  `default_headers` passthrough) → moved to **NR-OR-1**; live pricing-sync → **NR-OR-4**.

---

## 1. Problem Statement

| Component | Current State | Gap |
|-----------|--------------|-----|
| DeepSeek access | dedicated `deepseek` provider works, but the **account can't be funded** (top-ups cancelled) | Need DeepSeek's models via a payable channel |
| Cheap cloud vendor breadth | Anthropic/OpenAI/Google wired + funded; DeepSeek blocked | One US-billed lane → DeepSeek + Grok + Qwen + Llama |
| Aggregator | none | No single-key access to many vendors |
| Probe differential | `qwen-coder 0.193` (local) has no hosted comparator | A hosted model scored the same way |

---

## 2. Requirements

### Provider (reuse the recipe)
- **FR-OR-1 — Dedicated `openrouter` provider.** Add `providers/openrouter.py` (`OpenRouterProvider`,
  DeepSeek recipe): hardcode `base_url="https://openrouter.ai/api/v1"`, read `api_key` from config or
  `OPENROUTER_API_KEY`, return an `OpenAICompatibleAgent`. Dual registration (entry point +
  `_register_builtin_providers` fallback). `provider:model` needs **zero** run-spec/build_command/runner change.
- **FR-OR-2 — Pass-through canonical model ids.** Enrolled models use OpenRouter's own ids verbatim
  (`deepseek/deepseek-chat`, `qwen/qwen-2.5-coder-32b-instruct`, …). No alias translation; `slug()`
  makes the slash path-safe. The provider MAY warn (not error) on an id absent from its `MODELS` list
  (aggregator catalog is large and drifts).
- **FR-OR-3 — Infra-fail-compatible errors.** Missing key raises "OpenRouter API key required…" so a
  missing/funding failure classifies `infra_fail` (reuses the `_INFRA_ERROR_MARKERS` incl. the new
  `402`/`insufficient balance`, so an unfunded OpenRouter account is excluded, not a model 0).

### Catalog & pricing
- **FR-OR-4 — Catalog rows** for the v1 enrolled models (`_MODEL_REGISTRY`, `provider="openrouter"`,
  tier, capabilities) + `Models.OPENROUTER_*` constants + an `openrouter` `tier_map` block.
- **FR-OR-5 — Real per-model pricing (MANDATORY, dual-key safe).** Each enrolled model gets a
  `DEFAULT_PRICING` entry (`provider="openrouter"`, OpenRouter's **published per-model** input/output
  rate, `estimated=True`, source note). **Not $0** — a real cost-ranked vendor. Keyed under whichever
  id `resolve_pricing` receives at each call site (for OpenRouter the estimate-id == served-id, one
  entry suffices), verified by assertion (FR-OR-11) — the Jetson/DeepSeek dual-key lesson. Missing
  entry ⇒ the flagged $3/$15 fallback fires and mis-ranks the model (release blocker).
- **FR-OR-6 — `PROVIDER_PATTERNS`** maps `openrouter` (e.g. `["openrouter"]`) for `get_provider_for_model`.

### Cost posture (the key difference from the local lanes)
- **FR-OR-7 — Normal cost-ranked cloud contestant.** OpenRouter is a paid per-token API and is ranked
  on the **real cost axis** alongside Anthropic/OpenAI/Google — **no** `cost_lane` tag, **no** on-prem/
  free lane (that treatment is Jetson/Ollama-only, per Jetson OQ-J3). Its cost story: cheap DeepSeek/
  Qwen/Llama access with a small OpenRouter margin.

### Secrets
- **FR-OR-8 — Doppler key.** `OPENROUTER_API_KEY` in Doppler `startd8/dev`. **US-billed** (Stripe) —
  the point: it sidesteps DeepSeek's cancelled top-ups. No key committed to the repo.

### v1 model roster
- **FR-OR-9 — v1 roster (focused).** Enroll **`deepseek/deepseek-chat`** (the immediate unblock:
  DeepSeek's model without DeepSeek billing) and **`qwen/qwen-2.5-coder-32b-instruct`** (the hosted,
  bigger sibling of the local `qwen2.5-coder:7b` → a scale-controlled contamination comparison).
  `deepseek/deepseek-r1` optional. Grok/Llama are FR-OR-13 (recipe, later).

### Contamination
- **FR-OR-10 — Same pretraining caveat + FR-47 probe.** These are famous public models — clean of *our*
  vectors, **not** of pretraining (the Jetson FR-J8 residual / NR-J7, cited not restated). Published
  OpenRouter-lane results carry the caveat; the FR-47 probe applies. **Bonus:** `qwen-2.5-coder-32b`
  via OpenRouter is probe-comparable to the local `qwen2.5-coder:7b` (`0.193`) — a same-family,
  scale-varying memorization datapoint; and `deepseek-chat` gives the original hosted differential.

### Validation
- **FR-OR-11 — Dry-run + pricing-key assertion.** `run_behavioral_pilot.py --dry-run --model
  openrouter:deepseek/deepseek-chat` yields a finite, **non-fallback** estimate; a test asserts
  `resolve_pricing(<id the tracker sees>)` is non-fallback for each enrolled model (fallback = blocker).
- **FR-OR-12 — Live smoke.** `doppler run -p startd8 -c dev -- … agenerate` on
  `openrouter:deepseek/deepseek-chat` returns text (proves Doppler→provider→OpenRouter auth+billing).

### Extension (the aggregator payoff)
- **FR-OR-13 — More vendors by data, not code.** Grok (`x-ai/grok-*`), Llama (`meta-llama/…`), other
  Qwen/DeepSeek variants enroll by **adding a catalog + pricing row only** — same provider, same key,
  no new code. This is OpenRouter's structural advantage over per-vendor dedicated providers.

---

## 3. Non-Requirements

- **NR-OR-1** — No OpenRouter attribution headers (HTTP-Referer/X-Title) in v1 (optional; needs a
  `default_headers` passthrough in `OpenAICompatibleAgent` — deferred).
- **NR-OR-2** — No `cost_lane`/on-prem/free treatment (FR-OR-7 — it's cost-ranked).
- **NR-OR-3** — No alias translation layer (FR-OR-2 — pass-through canonical ids).
- **NR-OR-4** — No live sync of OpenRouter's `/models` pricing; the enrolled set is hardcoded (a guard
  test may *validate* ids against `/models`, but pricing is pinned).
- **NR-OR-5** — Pretraining contamination not eliminated; only *our* vectors absent (FR-OR-10).
- **NR-OR-6** — Not a replacement for the dedicated `deepseek` provider; both coexist (direct DeepSeek
  billing may work later).

---

## 4. Open Questions

- **OQ-OR-1 — v1 roster size?** Default (FR-OR-9): `deepseek-chat` + `qwen-coder-32b`; `deepseek-r1`
  optional. More via FR-OR-13.
- **OQ-OR-2 — Attribution headers now or defer?** Defer (NR-OR-1) — optional, needs an agent change.
- **OQ-OR-3 — Pricing basis: OpenRouter's published per-model rate vs the underlying vendor's raw rate?**
  Use OpenRouter's published rate (what we actually pay, incl. margin), `estimated=True` with a note.
- **OQ-OR-4 — Guard enrolled ids against `/models` drift?** OpenRouter renames/deprecates; add an
  endpoint-gated test that every enrolled id is present in `GET /models` (mirrors Jetson FR-J3a
  alias-drift). Fail loudly naming the missing id, don't silently `infra_fail`.
- **OQ-OR-5 — Add any OpenRouter model to `DEFAULT_MODELS`?** No — opt-in via `--model` (matches
  DeepSeek OQ-4 / Jetson FR-J2), so a paid cell isn't run on every default pilot.

---

*v0.2 — Post-planning self-reflective update. Provider shape + slash-id handling resolved (dedicated
provider, pass-through canonical ids). 1 requirement narrowed to a Non-Requirement (attribution
headers — no agent passthrough), FR-OR-7 hardened (cost-ranked, NOT a local lane), OQ-OR-4 added
(id-drift guard). 5 open questions, 2 resolved.*

*v0.3 — Lessons-learned hardening. Applied 3 lessons: phantom-reference audit (all enrolled ids
verified against live /models), single-source vocabulary (cite Jetson/DeepSeek, don't restate),
prune phantom scope (attribution headers + pricing-sync → Non-Requirements). Ready for CRP.*
