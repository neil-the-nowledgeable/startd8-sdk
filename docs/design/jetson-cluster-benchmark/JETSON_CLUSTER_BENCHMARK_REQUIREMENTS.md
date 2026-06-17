# Jetson Cluster as Benchmark Serving Backend — Requirements

**Version:** 0.3 (Post-CRP — R1 triage applied)
**Date:** 2026-06-16
**Status:** Draft (CRP R1 applied; ready for implementation)
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
  - **Alias-drift guard (R1-F6/R1-S5):** when the endpoint is up, every `ALIASES` served-id target
    MUST be validated against the live `GET /v1/models` response; a missing target MUST fail loudly
    **naming the missing id**, not degrade to a generic `infra_fail` (which would read as a model
    failure) or, worse, run a wrong/renamed adapter.
- **FR-J11 — Sentinel key for the no-auth LAN endpoint.** Because the SDK only nulls the API key for
  `localhost`/`127.0.0.1` (NOT `192.168.x.x`), the provider MUST supply a non-empty key —
  `os.getenv('LOCAL_FASTAPI_API_KEY', 'local-no-auth')` — which the no-auth FastAPI server ignores.
- **FR-J12 — Security posture + opt-in for the LAN endpoint (NEW, R1-F4/R1-S1).** The target is
  **plaintext HTTP on an RFC1918 address with a sentinel key that bypasses the SDK's localhost-only
  key-null guard** — there is no transport authentication or integrity, so any LAN host can
  impersonate the endpoint and feed crafted completions into the scorer. The provider MUST require an
  explicit operator opt-in (e.g. `STARTD8_ALLOW_LAN_ENDPOINT=1`) before `create_agent` returns an
  agent, so the SDK never silently dials a LAN box. A documented threat model accompanies this. TLS/
  mTLS is explicitly **out of scope** for v1 (NR-J6).
- **FR-J4 — Reuse the proven config shape (with divergences, R1-S10).** Behavior mirrors edge-brains'
  validated config (`base_url`, `model`, `LOCAL_FASTAPI_API_KEY`), encapsulated in the provider.
  **What does NOT transfer from the DeepSeek precedent:** transport security (DeepSeek = TLS; Jetson =
  plaintext LAN), key semantics (real key vs sentinel that defeats a safety guard), and contamination
  posture (clean hosted vendor vs corpus-fine-tuned adapters). The copied recipe must not import these
  false assurances.

### Contamination firewall (MANDATORY — three vectors)
- **FR-J5 — Fine-tuning vector.** Any model fine-tuned on the benchmark corpus (`iter_00x`) MUST run
  only in a separately labeled **"specialized / in-domain edge"** track, never ranked against general
  models; results carry a fine-tuned-on-corpus label; apply the perturbation probe
  ([[reference_edge_brains_contamination_probe]] / benchmark FR-47) where feasible. (= DeepSeek FR-15.)
  - **FR-J5a — Reachable-but-wrong-adapter (R1-F7/R1-S9).** A 200-OK from an **unloaded or silently
    base-fallback** adapter is NOT caught by FR-J1's infra-fail classification and would be scored as
    the wrong contestant. The server MUST echo the **actually-applied adapter id**, and the
    SDK/provenance MUST assert it matches the requested alias; a mismatch **invalidates the cell**
    (not an `infra_fail`, not a score). This is the dangerous case the firewall must close.
- **FR-J6 — System-prompt vector (server-side, with testable acceptance).** The serving harness'
  default `SYSTEM_PROMPT` names the corpus + house style (JSON logger, OTel, gRPC servicer, Apache
  header), which would bias **every** model served — including the clean baseline. The benchmark
  already sends its own uniform `{"role":"system"}` message (PrimeContractor drafter system prompt),
  so the SDK side is already neutral; the remaining requirement is **server-side**: `fastapi_serve.py`
  MUST honor the **request** system message over its default (no force-prepend).
  - **Acceptance criterion (R1-F1):** the system prompt **actually received by the served model**
    (captured into provenance) MUST byte-equal the benchmark's drafter system prompt AND MUST NOT
    contain corpus/house-style tokens (corpus name, "JSON logger", "OTel"/"OpenTelemetry", "gRPC
    servicer", "Apache header"). Verification artifacts: the captured prompt in provenance **and** the
    verified `edge-brains/fastapi_serve.py` commit SHA. A run failing this check is NOT a clean result.
- **FR-J6b — Inference-config / determinism vector (NEW, R1-F2/R1-S4).** Sampling params
  (temperature, top_p, seed) and quantization (NF4 config) MUST be **identical and recorded** for the
  base and adapter runs being compared; a mismatch invalidates a clean-vs-in-domain comparison. A
  base@temp0 vs adapter@temp0.7 (or differing quant) comparison is confounded regardless of prompt
  neutrality. Document the canonical values; treat absent/non-equal config within a track as a
  provenance error.
- **FR-J7 — Provenance labels.** Every Jetson result records: base model, **server-reported applied
  adapter id** (FR-J5a), quantization (NF4) config, serving host, sampling params (FR-J6b), and the
  **exact system prompt received** (FR-J6) — so a reader can audit which contamination vectors were
  neutralized.

### Clean contestants (the actual value)
- **FR-J8 — Clean baseline first.** The primary deliverable is enrolling the **untrained
  Mistral-7B-v0.3** as a fair "general 7B on $500 edge hardware" contestant.
  - **"Clean" is a checkable predicate (R1-F5):** a result is *clean* **iff** (a) base/untrained
    weights, AND (b) neutral system prompt verified per FR-J6, AND (c) no corpus-fine-tuned adapter
    applied (verified via FR-J5a applied-adapter echo), AND (d) recorded sampling/quant config per
    FR-J6b. A result missing **any** clause is NOT clean and MUST NOT enter the general leaderboard.
  - **Cost-axis gating (R1-F8/R1-S7):** because a ≈$0 marginal cost trivially "wins" the cost axis,
    **no Jetson row may appear on a cost ranking until OQ-J3 is resolved**; the chosen representation
    (amortized figure, or a separate "free/on-prem lane" tag in cells.json) is recorded in provenance.
  - **Residual contamination — what "clean" does NOT mean (scope honesty).** The 4-clause predicate
    defeats **our three vectors** (fine-tune weights, prompt, inference config). It does **NOT**
    eliminate **pretraining contamination**: the base model (Mistral-7B-v0.3) may have seen the
    microservices-demo corpus on public GitHub during its own pretraining — an irreducible vector
    shared by every frontier model. Therefore "clean" means *clean of our contamination*, a weaker
    and honest claim than *clean of all corpus exposure*. Any published Jetson result MUST state this
    caveat, and the perturbation probe ([[reference_edge_brains_contamination_probe]] / benchmark
    FR-47) is the only partial mitigation (it estimates memorization but cannot prove its absence).
- **FR-J9 — Optional clean small model.** Qwen2.5-1.5B/3B (untrained) MAY be enrolled as an
  "edge small-model" contestant once a serve setup is validated (OQ-J2).
- **FR-J9b — Explicit per-alias pricing (MANDATORY, R1-F3/R1-S6).** Each `jetson:*` alias MUST have a
  pricing entry; without one it inherits the **$3/$15-per-M flagged fallback** and looks expensive.
  Pricing MUST be registered under **whichever id `resolve_pricing` actually receives** in the
  `create_agent`→cost-tracker path (the alias-vs-served-id question is resolved by an **assertion**,
  not the v0.2 "test both" note): a fallback-priced `jetson:*` alias is a **release blocker**. Set the
  marginal on-prem rate (≈$0) OR an amortized figure (OQ-J3), `estimated=True` with a note. Add
  `"jetson"` to `PROVIDER_PATTERNS` for robustness.

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
- **NR-J6** — No TLS/mTLS to the LAN endpoint in v1 (FR-J12 mitigates via opt-in + threat model; transport security is future).
- **NR-J7** — Pretraining contamination of the base model is NOT eliminated (only our 3 vectors are; FR-J8 residual note). The probe estimates it; v1 does not attempt to scrub or certify pretraining-clean weights.

---

## 4. Open Questions

- **OQ-J1 — RESOLVED → dedicated `jetson` provider** (zero-plumbing, DeepSeek precedent). A general
  `BenchmarkRunSpec.base_url`/`openai-compatible` path is deferred as a future "arbitrary endpoint"
  enhancement (reusable for any vLLM/llama.cpp host), not needed for this single endpoint.
- **OQ-J2 — Serve Qwen2.5 as a clean small-model contestant now, or defer?** Needs a model pull +
  warmup test on rosie; unknown inference-time OOM behavior.
- **OQ-J3 — How to represent edge "cost"?** On-prem marginal cost is ~$0; a fair leaderboard needs an
  amortized hardware+energy figure or a separate "free/on-prem" lane, else it trivially "wins" cost.
  **Now gated (R1-F8/R1-S7):** must be decided BEFORE any Jetson row enters a cost ranking (FR-J8).
- **OQ-J4 — Run the in-domain `iter_002` track at all (FR-J5), or document-only?** Compelling story
  but only meaningful with the probe + airtight labels.

---

*v0.2 — Post-planning self-reflective update. OQ-J1 resolved (dedicated provider). 6 assumptions
corrected: FR-J3 simplified (zero plumbing), FR-J6 moved server-side (SDK already neutral), FR-J1
narrowed (infra-fail already covers unreachable). 3 requirements added (FR-J3a clean aliases, FR-J9b
mandatory per-alias pricing — the $3/$15 fallback would mislead, FR-J11 sentinel key — the v0.1
"RFC1918 accepted" claim was false per the bytes). Ready for CRP.*

*v0.3 — Post-CRP R1 (8/8 F-suggestions accepted; dispositions in Appendix A). Firewall grew from
**two vectors to three** (FR-J6b inference-config/determinism). Added FR-J5a (reachable-but-wrong-
adapter — the 200-OK hole infra_fail can't catch), FR-J6 testable acceptance criterion + recorded
SHA, FR-J12 (LAN security posture + opt-in), FR-J8 checkable "clean" predicate + cost-axis gating,
FR-J3a alias-drift guard, FR-J9b pricing-key resolved by assertion (release blocker), NR-J6 (no TLS
v1). OQ-J3 now gates the cost ranking. Post-triage addendum: FR-J8 residual-contamination note +
NR-J7 — "clean" means clean of OUR 3 vectors, not of pretraining exposure (honest-scope guard).*

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
| R1-F1 | FR-J6 testable acceptance criterion (byte-equal neutral prompt, banned corpus tokens, recorded SHA) | R1 (opus-4-8) | Merged into FR-J6 acceptance criterion | 2026-06-16 |
| R1-F2 | Third firewall vector: inference-config/determinism (sampling + quant identical, recorded) | R1 | Added as FR-J6b; firewall header → three vectors | 2026-06-16 |
| R1-F3 | FR-J9b: resolve alias-vs-served-id pricing key by assertion; fallback = release blocker | R1 | Merged into FR-J9b | 2026-06-16 |
| R1-F4 | LAN security posture + operator opt-in env before dialing | R1 | Added as FR-J12 + NR-J6 (TLS deferred) | 2026-06-16 |
| R1-F5 | Define "clean" as a checkable 4-clause predicate | R1 | Merged into FR-J8 | 2026-06-16 |
| R1-F6 | Alias-drift guard against live /v1/models | R1 | Merged into FR-J3a | 2026-06-16 |
| R1-F7 | Reachable-but-wrong-adapter disposition (server echoes applied adapter; mismatch invalidates) | R1 | Added as FR-J5a | 2026-06-16 |
| R1-F8 | Decide cost representation BEFORE enrolling on any cost ranking | R1 | Merged into FR-J8 cost-gating + OQ-J3 note | 2026-06-16 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-16

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-16 19:40:00 UTC
- **Scope**: Requirements quality (ambiguity, missing acceptance criteria, untestable statements, conflicts). Focus per orchestrator brief: contamination firewall completeness, cost-representation fairness, provider/alias contract, server-side prompt dependency, LAN-endpoint security/reproducibility.

**Executive summary (top requirements gaps):**

- FR-J6 is the firewall's load-bearing control but its acceptance is delegated to another repo with no objective, in-this-document verification criterion — "verify (and fix if needed)" is not testable as written.
- The contamination firewall enumerates exactly two vectors but a third (inference-config / quantization / sampling determinism) is acknowledged in FR-J7's field list yet has no firewall requirement of its own.
- FR-J9b is marked MANDATORY but its acceptance depends on an unresolved fact (which model id the cost tracker keys on) — the requirement can be "met" while still firing the misleading fallback.
- FR-J11's sentinel-key requirement has no security/threat-model framing or acceptance criterion bounding when dialing a LAN HTTP box is permissible.
- "Clean" is used as a firewall-grade term (FR-J8) without a checkable definition (untrained weights AND neutral prompt AND no corpus exposure), so a "clean" result is not independently auditable.
- FR-J1's "already classified infra_fail" guarantee is stated as covering unreachability but is silently relied on for correctness of contamination separation, which it does not provide for reachable-but-wrong responses.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Make FR-J6 testable with an objective, in-document acceptance criterion: "The system prompt actually received by the served model (captured from the request) MUST byte-equal the benchmark's drafter system prompt and MUST NOT contain corpus/house-style tokens (corpus name, 'JSON logger', 'OTel', 'gRPC servicer', 'Apache header'). Verification artifact: the captured prompt recorded in provenance + the verified edge-brains `fastapi_serve.py` commit SHA." | FR-J6 currently says "verify (and fix if needed) that `fastapi_serve.py` honors the request system message" — an action, not a checkable acceptance criterion. Without a concrete check, "fair run" is unverifiable and the most important firewall control is subjective. | FR-J6 (after "Gate any fair run on this verification.") | A reviewer can confirm a run passes by diffing the recorded system prompt against the expected neutral prompt; presence of any banned token fails. |
| R1-F2 | Risks | high | Add FR-J6b (or extend FR-J5) — a third firewall requirement covering inference-config determinism: sampling params (temperature/top_p/seed) and quantization (NF4) MUST be identical and recorded for base vs adapter runs; a mismatch invalidates a clean-vs-in-domain comparison. | The requirements state "two independent leakage vectors exist" and firewall exactly two, but FR-J7 already lists sampling params + quantization as provenance fields — implying they matter, yet nothing requires them to be controlled. A base@temp0 vs adapter@temp0.7 comparison is confounded regardless of prompt neutrality. | New requirement under "Contamination firewall" | Acceptance: provenance shows identical sampling+quant config across compared cells; CI/test asserts the fields are non-null and equal within a track. |
| R1-F3 | Data | high | FR-J9b: resolve the alias-vs-served-id keying question as part of the requirement rather than deferring it ("the REAL served ids the cost layer sees" in the plan is asserted, not proven). State: "Pricing MUST be registered under whichever id `resolve_pricing` actually receives in the create_agent→cost-tracker path, verified by an assertion; a fallback-priced `jetson:*` alias is a release blocker." | FR-J9b is MANDATORY, but its effectiveness hinges on a fact the docs themselves flag as uncertain ("confirm which id the cost tracker receives", "Test both"). As written, the requirement can pass review while the $3/$15 fallback still fires — the exact misleading-leaderboard failure it exists to prevent. | FR-J9b | Test drives a real agent→cost path; asserts `resolve_pricing` returns the non-fallback entry for both aliases. |
| R1-F4 | Security | high | Add FR-J12 (security posture for the LAN endpoint): state that the target is plaintext HTTP on an RFC1918 address with a sentinel key that bypasses the SDK's localhost-only key-null guard, that there is no transport authentication/integrity, and require an explicit operator opt-in (env flag) before the SDK will dial it; out of scope: TLS/mTLS (note as future). | FR-J11 introduces a sentinel key to defeat the SDK's own safety guard (key nulled only for localhost) but never frames the resulting exposure: any LAN host can impersonate the endpoint and feed crafted completions into the scorer. A benchmark that ingests untrusted model output over an unauthenticated channel needs a stated trust boundary. | New requirement near FR-J11 / Non-Requirements | Acceptance: a documented threat model exists; SDK refuses to construct a Jetson agent without the opt-in flag; NR explicitly defers TLS. |
| R1-F5 | Architecture | medium | Define "clean" as a checkable, firewall-grade predicate in FR-J8: a result is "clean" iff (a) base/untrained weights, AND (b) neutral system prompt verified per FR-J6, AND (c) no corpus-fine-tuned adapter applied, AND (d) recorded sampling/quant config per FR-J6b. A result missing any clause is NOT clean and may not enter the general leaderboard. | FR-J8 calls Mistral-7B-v0.3 a "fair general 7B contestant" and uses "clean" as a gating term throughout, but never defines it as an auditable conjunction. Without a definition, "clean" is an assertion, not a verifiable property. | FR-J8 | A reviewer can mechanically check each clause against provenance; failure of any clause excludes the result. |
| R1-F6 | Interfaces | medium | FR-J3a: require the alias→served-id map to be validated against the live `/v1/models` response (every served-id target MUST be present) when the endpoint is up, and specify behavior on mismatch (fail loudly naming the missing id, not a generic infra_fail). | FR-J3a hardcodes alias→served-id mappings (`mistralai/Mistral-7B-v0.3`, `iter_002`) with no requirement that these stay in sync with what the server serves. A server-side rename or unloaded adapter silently degrades to infra_fail (looks like model failure) or runs the wrong adapter. | FR-J3a | Endpoint-gated check: `/v1/models` superset-contains all alias targets; mismatch raises a named error. |
| R1-F7 | Validation | medium | FR-J5: specify the disposition of a reachable-but-wrong-adapter response. FR-J1's "infra_fail covers unreachable" does NOT cover a 200-OK from an unloaded/wrong adapter; require the server to echo the actually-applied adapter id and the SDK/provenance to assert it matches the requested alias. | The firewall depends on knowing which model produced a result, but a silent PEFT fallback-to-base returns a valid-looking response scored as the wrong contestant — undetectable by connection-error classification. | FR-J5 or FR-J7 | Acceptance: provenance records server-reported applied adapter; a mismatch with the requested alias invalidates the cell. |
| R1-F8 | Ops | low | OQ-J3 / FR-J9b: require the cost-representation decision (≈$0 marginal vs amortized vs separate "free/on-prem lane") to be made BEFORE the FR-J8 clean baseline is enrolled on any cost ranking, not after. | The requirements correctly warn a ≈$0 figure "trivially wins" the cost axis (OQ-J3), yet FR-J8 ships the clean baseline on "the benchmark's cost/quality axes" while OQ-J3 is still open — sequencing lets the misleading row land first. | FR-J8 / OQ-J3 | Acceptance: no Jetson row appears on a cost ranking until OQ-J3 is resolved and the chosen representation is recorded in provenance. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; Appendix C had no prior suggestions.
