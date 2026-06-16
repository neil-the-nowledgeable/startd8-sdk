# Jetson Cluster as Benchmark Serving Backend — Requirements

**Version:** 0.1 (Draft — pre-planning, grounded in a cluster investigation pass)
**Date:** 2026-06-16
**Status:** Draft
**Owner:** SDK / Summer 2026 Model Benchmark
**Related:** `docs/design/deepseek-vendor/` (FR-13/FR-15), `docs/design/model-benchmark/`,
[[project_summer2026_model_benchmark]], [[reference_edge_brains_contamination_probe]],
[[reference_multiworktree_env]]

> Sibling effort to the DeepSeek vendor wiring. DeepSeek adds a **clean hosted** vendor on the cost
> axis; this adds a **self-hosted edge** serving backend (4× Jetson Orin Nano) so the benchmark can
> ask "how does a $500 on-prem box compare to frontier APIs?" — but **only under a strict
> contamination firewall** (two independent leakage vectors exist).

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
- **FR-J1 — Preflight + bring-up.** Before enrolling any Jetson cell, the benchmark must (a) probe
  `GET http://192.168.7.57:8000/health` and `/v1/models`, and (b) treat an unreachable endpoint as
  `infra_fail` (excluded), never a model 0. Document the one-command bring-up
  (`edge-brains/scripts/start_fastapi_on_rosie.sh`) as an operator pre-step.
- **FR-J2 — Not a default-roster cell.** Jetson contestants are **opt-in** (`--model`/slate only),
  never in `DEFAULT_MODELS`, because the LAN endpoint is up only during experiments.

### SDK enrollment (the threading gap)
- **FR-J3 — base_url-carrying enrollment.** Provide a way for the benchmark `provider:model` path to
  reach a self-hosted endpoint. Two candidate designs (decide in planning, OQ-J1):
  - **(a) per-endpoint dedicated provider** — e.g. a `jetson` provider that hardcodes
    `http://192.168.7.57:8000/v1` (exact DeepSeek recipe; zero run-spec change), or
  - **(b) `BenchmarkRunSpec.base_url` (+ api_key_env) field** threaded through `build_command` to a
    new `run_prime_workflow` flag → `openai-compatible` provider (general, reusable for vLLM/llama.cpp).
- **FR-J4 — Reuse the proven config shape.** Whatever the design, mirror edge-brains'
  validated agent config: `provider: openai-compatible`, `base_url`, `model`, `api_key_env:
  LOCAL_FASTAPI_API_KEY` (the SDK already accepts RFC1918/no-auth local endpoints).

### Contamination firewall (MANDATORY — two vectors)
- **FR-J5 — Fine-tuning vector.** Any model fine-tuned on the benchmark corpus (`iter_00x`) MUST run
  only in a separately labeled **"specialized / in-domain edge"** track, never ranked against general
  models; results carry a fine-tuned-on-corpus label; apply the perturbation probe
  ([[reference_edge_brains_contamination_probe]] / benchmark FR-47) where feasible. (= DeepSeek FR-15.)
- **FR-J6 — System-prompt vector (NEW finding).** The serving harness' default `SYSTEM_PROMPT`
  names the corpus and its house style (JSON logger, OpenTelemetry, gRPC servicer, Apache header) —
  this biases the output of **every** model served through it, **including the clean untrained
  baseline**, toward the benchmark's scored structure. For any fair (non-in-domain) cell the
  benchmark MUST override the server system prompt to the **same neutral prompt all other vendors
  receive** (pass `system`/messages explicitly; do not rely on the server default). A clean model
  served under the corpus-aware default prompt is NOT a clean result.
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

- **OQ-J1 — FR-J3 design: dedicated `jetson` provider vs `BenchmarkRunSpec.base_url`?** Dedicated is
  zero-plumbing and ships fastest (DeepSeek precedent) but is endpoint-specific; the spec field is
  general (reusable for any vLLM/llama.cpp endpoint) but touches run_spec/build_command/runner.
  Lean: ship the dedicated provider first, design the general field as the follow-up.
- **OQ-J2 — Serve Qwen2.5 as a clean small-model contestant now, or defer?** Needs a model pull +
  warmup test on rosie; unknown inference-time OOM behavior.
- **OQ-J3 — How to represent edge "cost"?** On-prem marginal cost is ~$0; a fair leaderboard needs an
  amortized hardware+energy figure or a separate "free/on-prem" lane, else it trivially "wins" cost.
- **OQ-J4 — Run the in-domain `iter_002` track at all (FR-J5), or document-only?** Compelling story
  but only meaningful with the probe + airtight labels.

---

*Draft 0.1 — grounded in a full cluster investigation (topology, serving stack, model inventory,
reachability, scoring glue, contamination matrix). Will be updated after an SDK-side planning pass on
FR-J3 (the enrollment-threading design). Key new finding vs the DeepSeek spec: a **second
contamination vector** — the serving harness' corpus-aware default system prompt (FR-J6) — that taints
even clean models unless overridden.*
