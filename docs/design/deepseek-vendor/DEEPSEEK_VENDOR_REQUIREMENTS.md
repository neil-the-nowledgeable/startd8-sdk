# DeepSeek Vendor Wiring — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-16
**Status:** Draft (pre-implementation)
**Owner:** SDK / Summer 2026 Model Benchmark
**Related:** `docs/design/model-benchmark/`, [[project_summer2026_model_benchmark]], [[project_doppler_secrets]]

---

## 0. Planning Insights (Self-Reflective Update)

> This section records what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> The planning pass read the actual provider/benchmark/pricing code rather than assuming.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Adding a new vendor to the benchmark needs base_url threading through the `provider:model` spec | `build_command` (`model_comparison.py:149`) passes the spec straight to `--lead-agent`/`--drafter-agent`; resolution is `ProviderRegistry.get_provider(provider).create_agent(model)`. A **dedicated provider that hardcodes its own base_url** (Mistral pattern) needs **zero** threading changes. | FR-6 reframed: dedicated provider, NOT generic `openai-compatible`. Base_url threading is deferred to the self-hosted extension (FR-13) only. |
| A missing DeepSeek key would score the model a catastrophic 0 | `_INFRA_ERROR_MARKERS` (`benchmark_matrix/runner.py:35`) already matches `"api key required"` + `"failed to resolve agents"`; the Mistral-pattern error string ("DeepSeek API key required…") matches. | FR-3 only needs the error message to follow the existing phrasing — infra-fail exclusion is **already** wired. No runner change. |
| Pricing just needs the model in the catalog | Pricing is a **separate** table `DEFAULT_PRICING` in `costs/pricing.py:70`, keyed by bare `model_id`; `get_pricing` returns `None` for unknown models and `resolve_pricing` falls back to a *flagged estimate*. **Mistral has no entry at all.** | FR-4 added: real DeepSeek rows are mandatory (cheapness is the whole point on the cost axis) — fallback estimate would defeat the purpose. |
| Entry-point registration is enough | Editable installs across multiple worktrees serve **stale** entry-point metadata ([[reference_multiworktree_env]]); the live registry showed only 6 providers though `nim`/`openai-compatible` are declared. There is a `_register_builtin_providers()` fallback. | FR-2 added: register in **both** `pyproject.toml` and the builtin fallback so it works without a reinstall. |
| DeepSeek is "just OpenAI-compatible" | `deepseek-reasoner` emits `reasoning_content` and has different output-token semantics than `deepseek-chat`; `OpenAICompatibleAgent._is_openai_endpoint()` only enforces next-gen params for the *real* OpenAI host, so classic `max_tokens` is used (good). | OQ-1/OQ-2: reasoner support scoped as optional; v1 targets `deepseek-chat` first. |
| edge-brains / quantization have reusable adapter code | Neither ships adapter code. **edge-brains** *consumes* the SDK's `openai-compatible` provider against a self-hosted endpoint (`run_multi_agent_benchmark.py`: `provider: openai-compatible`, `base_url: http://astro:8000/v1`). **quantization** points at llama.cpp (`:8080`) / Ollama (`:11434`) OpenAI-compatible servers. | Reuse is a **config/serving pattern**, not code. Captured as the FR-13 self-hosted extension, not a v1 dependency. |
| quantization is just a serving reference | It hosts a **concrete contestant**: a fine-tuned **Mistral-7B QLoRA adapter** (`iter_002`/`iter_003`) served OpenAI-compatible at `http://192.168.7.57:8000/v1` (model id `iter_002`), already scored against needle-based structural findings (`report_iter_002_recommendation_server.json`). **It was trained on the microservices-demo / Online Boutique corpus — the benchmark's own corpus.** | FR-13 gains a concrete target endpoint; **FR-15 added** (in-domain/contamination guard) — this model is fine-tuned-on-corpus and must be a separate labeled track, never a peer of general models. Ties to [[reference_edge_brains_contamination_probe]] / benchmark FR-47. |

**Resolved open questions:**
- **OQ-A → Dedicated provider.** Cleaner than generic `openai-compatible` for the benchmark because the `provider:model` spec carries no base_url.
- **OQ-B → Key flows via Doppler.** Benchmark runs under `doppler run -p startd8 -c dev`; the subprocess inherits env, the provider reads `os.getenv('DEEPSEEK_API_KEY')`.

---

## 1. Problem Statement

The Summer 2026 Model Benchmark currently enrolls models from **already-wired vendors only**
(Anthropic, OpenAI, Google, + Mistral/Ollama declared). Round 1 found the structural metric
saturates among frontier models, leaving **cost as the primary differentiator**
(`docs/design/model-benchmark/results/ROUND1_PARTIAL_2026-06-12.md`). Adding a **new vendor with a
strong cost position** (DeepSeek) sharpens the cost axis and broadens the leaderboard beyond the
three incumbents.

DeepSeek is reachable today via the generic `openai-compatible` provider, but that path requires a
`base_url` the benchmark's `provider:model` spec does not carry, and it has no first-class pricing,
catalog presence, or key management. This effort makes DeepSeek a **first-class benchmark
contestant** end-to-end.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Provider | generic `openai-compatible` only (needs base_url) | No dedicated `deepseek` provider |
| Catalog | no DeepSeek entries in `model_catalog.py` | Missing `Models.*` consts + `_MODEL_REGISTRY` rows |
| Pricing | no DeepSeek rows in `DEFAULT_PRICING` | Cost would be a flagged estimate, not real |
| Secrets | no `DEEPSEEK_API_KEY` in Doppler `startd8/dev` | Cells would infra-fail (excluded) |
| Benchmark roster | `DEFAULT_MODELS` = 3 incumbents | DeepSeek not enrollable by `provider:model` alone |
| Tests | none | No provider/pricing/registration coverage |

---

## 2. Requirements

### Provider
- **FR-1 — Dedicated DeepSeek provider.** Add `src/startd8/providers/deepseek.py` defining
  `DeepSeekProvider`, modeled on `MistralProvider`: hardcoded `base_url='https://api.deepseek.com/v1'`,
  reads `api_key` from config or `DEEPSEEK_API_KEY`, returns an `OpenAICompatibleAgent`. `name`
  returns `"deepseek"`; `display_name` returns `"DeepSeek"`.
- **FR-2 — Dual registration.** Register `deepseek` as a `startd8.providers` entry point in
  `pyproject.toml` **and** in `ProviderRegistry._register_builtin_providers()` (guarded by
  `_register_if_missing`), so it resolves with or without a fresh editable reinstall.
- **FR-3 — Infra-fail-compatible error.** `validate_config` / `create_agent` must raise the
  existing phrasing ("DeepSeek API key required. Set DEEPSEEK_API_KEY…") so a missing key is
  classified `infra_fail` by the existing `_INFRA_ERROR_MARKERS`, not scored as a model failure.
- **FR-5 — Supported models.** Expose at minimum `deepseek-chat` (V3-class). `deepseek-reasoner`
  is OPTIONAL in v1 (see OQ-1).

### Catalog & Pricing
- **FR-4 — Real pricing rows.** Add `deepseek-chat` (and `deepseek-reasoner` if FR-5 includes it)
  to `DEFAULT_PRICING` in `costs/pricing.py` with **published** input/output per-million rates and
  `provider="deepseek"`. Rates that cannot be confirmed at publish time MUST set `estimated=True`
  with a `notes` source pointer (matching the existing convention).
- **FR-7 — Catalog presence.** Add `Models.DEEPSEEK_CHAT` (`"deepseek:deepseek-chat"`) constants and
  `_MODEL_REGISTRY` `ModelInfo` rows (tier/capabilities) so the model participates in catalog-driven
  tooling and `get_latest_model("deepseek", …)` resolves.
- **FR-8 — Provider→model mapping.** `PricingService.get_provider_for_model` and any tier maps must
  return `"deepseek"` for DeepSeek model ids.

### Secrets
- **FR-9 — Doppler key.** Add `DEEPSEEK_API_KEY` to Doppler `startd8/dev` (and document the local
  env fallback). No key value is committed to the repo. The benchmark invocation
  (`doppler run -p startd8 -c dev -- …`) injects it into the cell subprocess.

### Benchmark enrollment
- **FR-10 — Roster enrollment.** DeepSeek must be enrollable via `--model deepseek:deepseek-chat`
  in `scripts/run_behavioral_pilot.py` with **no code change to the runner/executor/`build_command`**
  (validated by FR-6). Optionally add it to `DEFAULT_MODELS` once a live cell passes.
- **FR-6 — Zero threading change (design constraint).** Because the provider self-describes its
  endpoint, no `base_url` plumbing through `BenchmarkRunSpec` / `build_command` is required for
  DeepSeek. This is the load-bearing simplification — preserve it.

### Validation
- **FR-11 — Dry-run cost estimate.** `run_behavioral_pilot.py --dry-run` with the DeepSeek model
  must produce a finite, non-fallback cost estimate (proves FR-4 + FR-7 + FR-8 wired).
- **FR-12 — Unit tests.** Cover: provider resolves via registry (both registration paths),
  `validate_config` raises infra-compatible error when key absent, pricing returns a real
  (non-`estimated`-fallback) entry, and `get_provider_for_model` maps correctly.

### Extension path (documented, not all built in v1)
- **FR-13 — Self-hosted / local-quantized path (documented, concrete target).** Document that
  self-hosted and local-quantized models (vLLM, llama.cpp `:8080`, Ollama `:11434`) enroll via the
  generic `openai-compatible` provider + a `base_url`, per the edge-brains pattern
  (`run_multi_agent_benchmark.py`). The **concrete reference target** is the quantization repo's
  fine-tuned **Mistral-7B QLoRA** (`iter_002`/`iter_003`) served OpenAI-compatible at a Jetson
  endpoint (`http://192.168.7.57:8000/v1` / `http://astro:8000/v1`, model id `iter_002`). Enumerate
  the genuine gaps: (i) the benchmark's `provider:model` spec cannot carry a `base_url`, so local
  endpoints need either a per-endpoint dedicated provider or a future `BenchmarkRunSpec.base_url`
  field; (ii) a LAN endpoint is **not CI-stable** (up only when the Jetson is on-network) → an
  opportunistic/manual run, not a default-roster cell. v1 documents; does not build.
- **FR-15 — In-domain / contamination guard for fine-tuned local models (MANDATORY for FR-13).**
  Any model **fine-tuned on the benchmark corpus** (the `iter_00x` adapters were trained on the
  microservices-demo / Online Boutique services this benchmark generates) MUST NOT be ranked as a
  peer of general models. It enrolls only in a **separately labeled "specialized / in-domain edge
  model" track**, its results carry an explicit fine-tuned-on-corpus label, and — where feasible —
  the contamination perturbation probe ([[reference_edge_brains_contamination_probe]],
  benchmark FR-47) is applied. This guards the leaderboard's integrity.
- **FR-14 — Other hosted OpenAI-compatible vendors (documented).** Document that xAI/Grok
  (`api.x.ai/v1`), Groq (`api.groq.com/openai/v1`), and OpenRouter (`openrouter.ai/api/v1`) each
  add via the **same DeepSeek recipe** (copy `deepseek.py`, swap base_url + env var + pricing).
  DeepSeek is the reference implementation for all of them.

---

## 3. Non-Requirements

- **NR-1** — No generic base_url threading through `BenchmarkRunSpec`/`build_command` in v1 (FR-13 documents the gap only).
- **NR-2** — No actual provisioning of xAI/Groq/OpenRouter providers in v1 (FR-14 is documentation; they follow the recipe later).
- **NR-3** — No local-model serving setup (llama.cpp/vLLM/Ollama deployment) in v1.
- **NR-4** — No streaming/tool-calling/vision feature parity work beyond what `OpenAICompatibleAgent` already gives.
- **NR-5** — No change to scoring/aggregation; DeepSeek flows through the existing metric unchanged.
- **NR-6** — No `deepseek-reasoner` reasoning-trace capture/scoring (OQ-1 may add the model, not trace handling).

---

## 4. Open Questions

- **OQ-1 — Include `deepseek-reasoner` in v1?** It changes output semantics (`reasoning_content`,
  larger thinking budget). Default: ship `deepseek-chat` first; add reasoner in a fast-follow once
  the chat path is green.
- **OQ-2 — `max_tokens` ceiling.** `deepseek-chat` caps output ~8K. Confirm the value to set
  (Mistral uses 8192). Reasoner allows much larger; revisit with OQ-1.
- **OQ-3 — Published pricing at implementation time.** Confirm current DeepSeek list price
  (and off-peak discount, if modeled) for FR-4; otherwise flag `estimated=True`.
- **OQ-4 — Add to `DEFAULT_MODELS`?** Only after a live cell passes; otherwise leave opt-in via
  `--model` to avoid spending on every default pilot run.
- **OQ-5 — Actually run the Jetson `iter_00x` contestant (FR-13/FR-15), or document-only?** It's a
  compelling "$500 edge box vs frontier on cost" story, but needs the Jetson on-network, a base_url
  enrollment path, AND the FR-15 in-domain track + contamination probe to be fair. Default: document
  in v1, run as a separate dedicated experiment after DeepSeek (the general-vendor add) lands.

---

*v0.2 — Post-planning self-reflective update. 7 assumptions corrected (1 simplified the design
substantially: dedicated provider ⇒ zero benchmark-threading change; 1 surfaced a concrete
local contestant + contamination risk), 3 requirements added (real pricing, dual registration,
in-domain guard FR-15), 1 reframed (FR-6), extension path split into documented FR-13/FR-14 with a
concrete Jetson target. 2 open questions resolved, 1 added (OQ-5).*
