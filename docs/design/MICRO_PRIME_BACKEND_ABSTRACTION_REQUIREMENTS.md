# Micro-Prime Backend Abstraction & Configuration — Requirements

**Version:** 0.2 (edge-brains serving code read; hard edge work deferred)
**Date:** 2026-06-03
**Status:** Draft

> **Update:** **Gemini CLOUD structured output is now implemented**
> (`GeminiAgent.agenerate_structured` via controlled generation —
> `response_mime_type="application/json"` + `response_schema`, validate +
> retry-once). This **lifts the gemini-flash app-default blocker** (#2): a Gemini
> model can now back the generated app's `call_ai_service`. Distinct from the
> **edge-brains** FastAPI server (still freeform / no structured output) — that
> freeform-and-parse fallback (FR-6) remains deferred to the edge phase.

---

## 0. Planning Insights (post-exploration update)

> Read `edge-brains/scripts/fastapi_serve.py`. Two load-bearing OQs resolved; the
> *hard* edge work is explicitly deferred to a final/subsequent phase (per direction).

| v0.1 question | Finding | Impact |
|---|---|---|
| OQ-1 serving protocol | edge-brains serves **OpenAI-compatible** endpoints (`/v1/chat/completions`, `/v1/models`, `/health`) | **No bespoke `edge` provider needed for v1** — the existing `openai` provider with a `base_url` override targets it. FR-4 shrinks to "config a base_url'd openai-compatible spec." |
| OQ-2 structured output | `ChatRequest` has **no** `tools`/`tool_choice`/`response_format` — **freeform text only** | The HARD part: micro-prime relies on `generate_structured`. Edge needs a freeform-and-parse fallback (FR-6). **Deferred** — see Phasing. |
| OQ-5 provider vs backend | OQ-1 ⇒ reuse `openai` provider (base_url), not a new provider | Removes a chunk of FR-4. |

**Resolved:** OQ-1 (OpenAI-compatible), OQ-2 (freeform-only ⇒ fallback required), OQ-5
(reuse openai+base_url). **Still open / deferred:** OQ-3 (cold-start health), OQ-4
(cluster discovery), OQ-6 (tier mapping) — all belong with the deferred edge phase.

### Phasing (defer the hard edge work)

- **NEAR-TERM (this effort):** FR-3 only — make the shared `resolve_role_agent`
  **backend-agnostic** (any role's spec may be `anthropic:`/`gemini:`/`ollama:`/future
  `edge:`/`openai:`+base_url; the resolver just calls `resolve_agent_spec`, no
  special-casing). Migrate the leaky sites (esp. the micro-prime cloud-retry
  `CLAUDE_HAIKU` last-resort) to it. This makes edge **plug-in-able later without
  re-touching the resolver** — without building edge now.
- **DEFERRED (final/subsequent phase):** FR-1 (LocalEdgeBackend protocol), FR-2
  (de-Ollama-ify micro-prime internals), FR-6 (freeform+parse fallback for
  no-structured-output edge models), FR-9 (hybrid-cluster routing), and the
  base_url/openai edge config + health/cold-start handling. These are the "hard
  questions" — they land when the edge cluster is real.
**Companion:** `MODEL_CONFIG_FIRST_CLASS_REQUIREMENTS.md` (cloud-provider selection — this
doc extends the same model-config spine to the **local/edge inference backend**).
**New capability driver:** `/Users/neilyashinsky/Documents/dev/edge-brains` — on-prem
QLoRA-fine-tuned code-style models (Mistral-7B-class) served from a FastAPI inference
server on Jetson Orin (eventually a Jetson+Mac hybrid cluster). $0 inference, single-tenant,
"no source leaves the building." The SDK's PrimeContractor+kaizen is already edge-brains'
RFT *scorer*; this doc makes edge-brains usable *as an inference backend*, as an upgraded
replacement for / alternative to Ollama.

---

## 1. Problem Statement

The just-shipped model-config capability abstracts **cloud** provider selection
(`--provider`, `default_provider`, per-role resolution). But micro-prime's **local**
generation path is still hardwired to *Ollama* as a concept — the local backend is not
pluggable. A new capability (edge-brains: a fine-tuned 7B served from a Jetson/Mac cluster)
must slot in as an upgraded/alternative local backend without rewriting micro-prime.

| Site | Current state | Gap for a pluggable local/edge backend |
|------|--------------|----------------------------------------|
| `micro_prime/context.py` | `ollama_available: bool`, `ollama_model="startd8-coder"` | backend identity is "Ollama", not a generic local backend |
| `micro_prime/artisan_adapter.py` | `_check_ollama_available()` (HTTP probe to Ollama) | health-check is Ollama-specific |
| `micro_prime/engine.py` | `_generate_ollama`, `generation_strategy="file_ollama_whole"`, `model="ollama:startd8-coder"` | generation + strategy names assume Ollama |
| `micro_prime/metrics.py` | "cost per 1M tokens for local Ollama models" | cost model is Ollama-labelled |
| `prime_adapter._resolve_cloud_agent_spec` | local→cloud escalation; last-resort `DRAFT_MODEL_CLAUDE_HAIKU` | escalation knows "local" only as Ollama |
| `providers/` | anthropic/gemini/mistral/openai/mock; `ollama` via entry point | **no `edge`/`edgebrains` provider** |
| model-config resolver (`resolve_role_agent`, planned #4) | resolves cloud + ollama specs | not yet backend-aware (health, endpoint, privacy) |

**edge-brains serving facts (to design against):** a **FastAPI** generate server (vLLM was a
build blocker on Tegra), single-tenant (`model.generate()` one at a time, second request
blocks), `max_tokens` defaults conservative (LoRA OOD past training horizon), a **cold-start
reboot race** (bnb #1936 — needs a warm-up forward pass before first load). Models are
code-style LoRAs (e.g. iter-002/003), seq_len 512→1024.

## 2. Requirements

- **FR-1 LocalEdgeBackend protocol.** Define one protocol the local/edge generator targets:
  `is_available()` (health probe), `generate_structured(prompt, schema, max_tokens)` /
  `generate(...)`, `model_id`, `endpoint`, `cost_model`. Ollama is one implementation;
  the edge-brains FastAPI server is another. Micro-prime calls the protocol, not `ollama_*`.

- **FR-2 De-Ollama-ify micro-prime (with back-compat).** Rename/abstract `ollama_available
  → local_backend_available`, `ollama_model → local_model`, `_check_ollama_available →
  _check_local_backend`, `file_ollama_whole → file_local_whole` (keep aliases / persisted-key
  back-compat so existing kaizen artifacts/strategy strings still parse).

- **FR-3 Backend selection via first-class config.** The micro-prime *local* role resolves
  through the same `resolve_role_agent` precedence as every other role (#4): explicit spec
  (`ollama:startd8-coder` | `edge:house-7b`) → run config → `~/.startd8` → default. A single
  `local_backend`/`MODEL_PROVIDER`-style knob picks Ollama vs edge.

- **FR-4 `edge` provider.** Add an `edge` (a.k.a. `edgebrains`) provider speaking the
  edge-brains FastAPI protocol: spec form `edge:<model>`, endpoint config (host:port, or a
  cluster of endpoints), request/response mapping, timeout. Registered like the other
  providers (entry point + `resolve_agent_spec`).

- **FR-5 Availability + graceful fallback.** If the selected local/edge backend is down (or in
  cold-start), micro-prime falls through its existing escalation (local → cloud retry) instead
  of hard-failing — and records *which* backend actually served (FR-7). Health-check must
  tolerate the edge-brains cold-start/warm-up window, not just a TCP probe.

- **FR-6 Capability awareness.** Edge LoRAs have real limits (single-tenant serialization,
  `max_tokens` horizon, possibly **no tool-use/structured-output** support). The backend
  declares capabilities (`supports_structured_output`, `max_safe_tokens`, `concurrency=1`); the
  router respects them (e.g. fall back to freeform+parse when structured output is unsupported;
  don't over-issue concurrent calls to a single-tenant edge node).

- **FR-7 Provenance.** Per element, record backend kind + model + endpoint + served-locally
  flag (extends per-role provenance, MODEL_CONFIG step 7). "What ran where" must include the
  local/edge backend, not just cloud roles.

- **FR-8 Privacy/cost accounting (NFR).** When an edge backend is selected, assert **no prompt
  leaves the building** (the edge-brains value prop) and account inference at $0 (as Ollama is
  today). Surface this in the run summary.

- **FR-9 Hybrid-cluster ready (forward-looking).** The `edge` provider config accepts **multiple
  endpoints** (Jetson + Mac nodes); v1 may target a single endpoint, but the config shape and
  the protocol must not preclude a future router (round-robin / least-loaded / model-affinity).

## 3. Non-Requirements

- Training / the RFT loop / LoRA recipes — **edge-brains owns** these (the SDK is only the scorer
  + the inference *consumer*).
- Cluster provisioning, model deployment, vLLM-vs-FastAPI serving choice — edge-brains' domain.
- Changing cloud-provider config — done in `MODEL_CONFIG_FIRST_CLASS_REQUIREMENTS.md`.
- A new generation algorithm — this is backend abstraction, not new micro-prime logic.

## 4. Open Questions

- **OQ-1** edge-brains serving protocol: is the FastAPI server **OpenAI-compatible** (so the
  existing openai provider with a base_url override suffices) or **custom** (needs a dedicated
  `edge` provider)? Check `edge-brains/.../fastapi_serve.py` + `REQUIREMENTS_VLLM_SERVING_TEGRA`.
- **OQ-2** Do the edge LoRAs support **tool-use / structured output** (the SDK's
  `generate_structured`)? If not, micro-prime's structured paths need a freeform+parse fallback
  for edge (FR-6).
- **OQ-3** Cold-start/warm-up contract: how does the SDK health-check distinguish "warming up"
  (bnb #1936 mitigation running) from "down"? Retry/backoff policy.
- **OQ-4** Endpoint discovery for the hybrid cluster — static config list, env, or a registry?
  How is model→node affinity expressed (which node hosts which LoRA)?
- **OQ-5** Does `edge` belong as a `providers/` provider (cleanest — reuses `resolve_agent_spec`)
  or a micro-prime-only backend? Provider is preferred for reuse, but micro-prime's local path
  has Ollama-specific assumptions (FR-2) to unwind first.
- **OQ-6** Tier mapping: which micro-prime tiers (TRIVIAL/SIMPLE) route to edge, and does an
  edge LoRA's quality justify a higher tier than Ollama's `startd8-coder`?

## 5. Relationship to the build sequence

This doc **gates step #4** (extract `resolve_role_agent`): the shared resolver must be
**backend-agnostic** (cloud | ollama | edge) so edge-brains plugs in without re-touching it.
Recommended order with the agreed roadmap:

1. **Phase-1 polish** (shared `resolve_role_agent` [#4], migrate remaining sites [step 5],
   per-role provenance [step 7], no-hardcoded-provider guard [step 8]) — build the resolver
   **backend-agnostic per FR-3/FR-1** so it's edge-ready by construction.
2. **#2** cheap generated-app default (independent; do anytime).
3. **#5** `startd8 config models` + provenance — extend to record local/edge backend (FR-7).
4. **#6** per-role mixing — naturally includes `local_backend` as a role.
5. **edge provider (FR-4)** once OQ-1/OQ-2 are answered from the edge-brains serving code.

*Draft 0.1 — written after exploring micro-prime + edge-brains. Resolve OQ-1/OQ-2 against the
edge-brains FastAPI serving code, then promote to v0.2 with a plan.*
