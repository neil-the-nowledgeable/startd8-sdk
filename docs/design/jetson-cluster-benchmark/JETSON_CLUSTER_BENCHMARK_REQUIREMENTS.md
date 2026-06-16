# Jetson Cluster as Benchmark Serving Backend — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-16
**Status:** Draft (planning pass complete; ready for CRP)
**Owner:** SDK / Summer 2026 Model Benchmark
**Related:** `docs/design/deepseek-vendor/` (FR-13/FR-15), `docs/design/model-benchmark/`,
[[project_summer2026_model_benchmark]], [[reference_edge_brains_contamination_probe]],
[[reference_multiworktree_env]]

> Sibling effort to the DeepSeek vendor wiring. DeepSeek adds a **clean hosted** vendor on the cost
> axis; this adds a **self-hosted edge** serving backend (4× Jetson Orin Nano) so the benchmark can
> ask "how does a $500 on-prem box compare to frontier APIs?" — but **only under a strict
> contamination firewall** (two independent leakage vectors exist).

---

## 0. Planning Insights (Self-Reflective Update)

> Changes from v0.1 (pre-planning) to v0.2, after reading the SDK provider/benchmark/pricing code.
> The DeepSeek implementation (shipped this session, PR #5) is the proven precedent throughout.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| FR-J3 was an open A/B (dedicated provider vs `BenchmarkRunSpec.base_url`) | A dedicated provider needs **zero** run-spec/build_command/runner changes (DeepSeek proved it this session). Option (b) touches the immutable content-hashed `BenchmarkRunSpec`, `build_command`, `runner`, AND `run_prime_workflow` arg parsing — far more surface, generality not needed for one endpoint. | **OQ-J1 RESOLVED → dedicated `jetson` provider.** Option (b) deferred to a future "arbitrary endpoint" enhancement. |
| Self-hosted endpoint serves "a model" | rosie serves the base model **and all adapters at the same `base_url`**, selected by the request `model` field. **One** `jetson` provider covers base Mistral + every adapter. | FR-J3 simplified: one provider, model field selects the served model. |
| The SDK auto-detects local/no-auth endpoints (v1 report claimed "SDK accepts RFC1918") | **FALSE per `agents/openai.py:484`** — key is nulled only for `localhost`/`127.0.0.1`, NOT `192.168.x.x`. The OpenAI SDK rejects an empty key. | **FR-J11 added**: provider supplies a sentinel key (`LOCAL_FASTAPI_API_KEY` or a harmless default) so a LAN IP authenticates against the no-auth server. |
| FR-J6 (neutral prompt) is an SDK requirement | The PrimeContractor **already** builds + sends its own `draft_system_prompt.md` as a `{"role":"system"}` message (`prime_contractor.py:2646`; `OpenAICompatibleAgent` prepends it). The benchmark already sends a uniform, vendor-neutral system prompt. | **FR-J6 reframed → server-side verification.** The only risk is the FastAPI server *force-prepending* its corpus-aware default over the request system. Fix/verify lives in edge-brains `fastapi_serve.py`, not the SDK. |
| Unknown-model cost would be ~$0 (trivially wins cost axis) | `resolve_pricing` fallback is a flagged **$3 in / $15 out per M** (`pricing.py`) — a local model with no entry looks **expensive**, the opposite of reality. | **FR-J9b added**: explicit per-alias pricing entries are mandatory (≈$0 marginal or an amortized figure), else the leaderboard is actively misleading. Sharpens OQ-J3. |
| HF model ids (`mistralai/Mistral-7B-v0.3`) drop in cleanly | Paths use `slug()` (slash-safe) but `cell_id` embeds **raw** `cell.model`; a `/` is cosmetically/latently risky in identity strings. | **FR-J3a added**: the provider exposes **clean slash-free aliases** (`jetson:mistral-7b-base`, `jetson:iter-002`) mapped to the server's real model id — also the natural home for per-alias pricing + contamination labels. |
| FR-J1 needs a new reachability/preflight mechanism | Connection failures already match `_INFRA_ERROR_MARKERS` (`apiconnectionerror`/`connection error`/`timed out connecting`) → an unreachable endpoint is **already** auto-excluded as `infra_fail`. | FR-J1 narrowed: explicit `/health` preflight is a fast-fail nicety, not required for correctness. |

**Resolved open questions:**
- **OQ-J1 → dedicated `jetson` provider** (zero-plumbing, DeepSeek recipe). General `base_url` field deferred.

---

## 1. Problem Statement

The `quantization` + `edge-brains` repos operate a working 4× Jetson Orin Nano cluster that serves
an **OpenAI-compatible** endpoint reachable from the Mac over LAN. It can serve a **clean untrained
Mistral-7B-v0.3** (a fair general small-model contestant) and several **corpus-fine-tuned LoRA
adapters** (`iter_00x`, contaminated). The Summer 2026 benchmark currently cannot enroll any of
these because (a) its `provider:model` spec cannot carry a `base_url`, and (b) there is no
contamination policy for in-domain models.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Cluster | 4× Orin Nano 8GB; astro `.28`, **rosie `.57` (serving)**, judy `.66`, elroy `.67`; LAN-reachable, no tunnel | Not stable/always-on; LAN-only |
| Serving | FastAPI (`fastapi_serve.py`) on rosie `:8000/v1`, OpenAI-compatible chat/models/health; `start_fastapi_on_rosie.sh` brings up | Not vLLM/llama.cpp; LoRA via PEFT `set_adapter` |
| Clean models | base `mistralai/Mistral-7B-v0.3` served; Qwen2.5-1.5B/3B trainable, not yet served | Qwen needs a serve setup |
| Contaminated models | `iter_001/002/003` LoRA — trained on microservices-demo (Online Boutique) | Must be firewalled, not peers |
| SDK enrollment | `openai-compatible` provider needs a `base_url` the run spec can't carry | Threading gap (see FR-J3) |
| Fairness | server default **system prompt names the corpus + house style** | Biases EVERY model incl. clean baseline (FR-J6) |

---

## 2. Requirements

### Reachability & lifecycle
- **FR-J1 — Preflight + bring-up.** An unreachable endpoint is **already** classified `infra_fail`
  (excluded), never a model 0, because connection errors match `_INFRA_ERROR_MARKERS` — no new code
  required for correctness. OPTIONAL fast-fail nicety: probe `GET /health` + `/v1/models` before a
  batch. Document the one-command bring-up (`edge-brains/scripts/start_fastapi_on_rosie.sh`) as an
  operator pre-step.
- **FR-J2 — Not a default-roster cell.** Jetson contestants are **opt-in** (`--model`/slate only),
  never in `DEFAULT_MODELS`, because the LAN endpoint is up only during experiments.

### SDK enrollment (the threading gap)
- **FR-J3 — Dedicated `jetson` provider (RESOLVED, option a).** Add `providers/jetson.py`
  (`JetsonProvider`, exact DeepSeek recipe) that hardcodes `base_url=http://192.168.7.57:8000/v1` and
  returns an `OpenAICompatibleAgent`. The `provider:model` spec carries no `base_url`, so this needs
  **zero** changes to `BenchmarkRunSpec`/`build_command`/`runner`. One provider covers the base model
  and every adapter (the request `model` field selects which).
- **FR-J3a — Clean slash-free aliases.** The provider exposes aliases without `/` (e.g.
  `jetson:mistral-7b-base`, `jetson:iter-002`) and maps each to the server's real model id
  (`mistralai/Mistral-7B-v0.3`, `iter_002`) inside `create_agent`. Avoids slash-in-`cell_id` risk and
  is the home for per-alias pricing (FR-J9b) and contamination labels (FR-J7).
- **FR-J11 — Sentinel key for the no-auth LAN endpoint.** Because the SDK only nulls the API key for
  `localhost`/`127.0.0.1` (NOT `192.168.x.x`), the provider MUST supply a non-empty key —
  `os.getenv('LOCAL_FASTAPI_API_KEY', 'local-no-auth')` — which the no-auth FastAPI server ignores.
- **FR-J4 — Reuse the proven config shape.** Behavior mirrors edge-brains' validated config
  (`base_url`, `model`, `LOCAL_FASTAPI_API_KEY`) — now encapsulated inside the dedicated provider.

### Contamination firewall (MANDATORY — two vectors)
- **FR-J5 — Fine-tuning vector.** Any model fine-tuned on the benchmark corpus (`iter_00x`) MUST run
  only in a separately labeled **"specialized / in-domain edge"** track, never ranked against general
  models; results carry a fine-tuned-on-corpus label; apply the perturbation probe
  ([[reference_edge_brains_contamination_probe]] / benchmark FR-47) where feasible. (= DeepSeek FR-15.)
- **FR-J6 — System-prompt vector (server-side, reframed).** The serving harness' default
  `SYSTEM_PROMPT` names the corpus + house style (JSON logger, OTel, gRPC servicer, Apache header),
  which would bias **every** model served — including the clean baseline. **Planning correction:** the
  benchmark already sends its own uniform `{"role":"system"}` message (PrimeContractor drafter system
  prompt), so the SDK side is already neutral. The remaining requirement is **server-side**: verify
  (and fix if needed) that `edge-brains/fastapi_serve.py` honors the **request** system message over
  its hardcoded default — it must NOT force-prepend the corpus prompt. A clean model served under the
  corpus-aware default is NOT a clean result. Gate any fair run on this verification.
- **FR-J7 — Provenance labels.** Every Jetson result records: base model, adapter (or none),
  quantization (NF4), serving host, sampling params, and the exact system prompt used — so a reader
  can audit which contamination vectors were neutralized.

### Clean contestants (the actual value)
- **FR-J8 — Clean baseline first.** The primary deliverable is enrolling the **untrained
  Mistral-7B-v0.3** (served, NF4, neutral prompt per FR-J6) as a fair "general 7B on $500 edge
  hardware" contestant on the benchmark's cost/quality axes. Cost axis = $0 marginal (on-prem) +
  amortized hardware/energy note.
- **FR-J9 — Optional clean small model.** Qwen2.5-1.5B/3B (untrained) MAY be enrolled as an
  "edge small-model" contestant once a serve setup is validated (OQ-J2).
- **FR-J9b — Explicit per-alias pricing (MANDATORY).** Each `jetson:*` alias MUST have a pricing
  entry; without one it inherits the **$3/$15-per-M flagged fallback** and looks expensive. Set the
  marginal on-prem rate (≈$0) OR an amortized hardware+energy figure (OQ-J3), `estimated=True` with a
  note. Add `"jetson"` to `PROVIDER_PATTERNS` for robustness.

### Validation
- **FR-J10 — End-to-end smoke.** One prompt → clean Mistral cell via the FR-J3 path → scored by the
  existing benchmark scorer, proving the endpoint, neutral prompt, and provenance labels work before
  any full run.

---

## 3. Non-Requirements

- **NR-J1** — No new serving stack on the cluster (use the existing FastAPI; llama.cpp/GGUF is future).
- **NR-J2** — No multi-Jetson distributed *inference* (Gemma-26B-class is OOM-blocked; out of scope).
- **NR-J3** — No training/fine-tuning work; this is serving + enrollment only.
- **NR-J4** — No always-on/CI hosting of the endpoint; opt-in manual/operator-gated runs (FR-J2).
- **NR-J5** — `iter_003` not enrolled unless specifically studying memorization (NR per cluster report).

---

## 4. Open Questions

- **OQ-J1 — RESOLVED → dedicated `jetson` provider** (zero-plumbing, DeepSeek precedent). A general
  `BenchmarkRunSpec.base_url`/`openai-compatible` path is deferred as a future "arbitrary endpoint"
  enhancement (reusable for any vLLM/llama.cpp host), not needed for this single endpoint.
- **OQ-J2 — Serve Qwen2.5 as a clean small-model contestant now, or defer?** Needs a model pull +
  warmup test on rosie; unknown inference-time OOM behavior.
- **OQ-J3 — How to represent edge "cost"?** On-prem marginal cost is ~$0; a fair leaderboard needs an
  amortized hardware+energy figure or a separate "free/on-prem" lane, else it trivially "wins" cost.
- **OQ-J4 — Run the in-domain `iter_002` track at all (FR-J5), or document-only?** Compelling story
  but only meaningful with the probe + airtight labels.

---

*v0.2 — Post-planning self-reflective update. OQ-J1 resolved (dedicated provider). 6 assumptions
corrected: FR-J3 simplified (zero plumbing), FR-J6 moved server-side (SDK already neutral), FR-J1
narrowed (infra-fail already covers unreachable). 3 requirements added (FR-J3a clean aliases, FR-J9b
mandatory per-alias pricing — the $3/$15 fallback would mislead, FR-J11 sentinel key — the v0.1
"RFC1918 accepted" claim was false per the bytes). Ready for CRP.*
