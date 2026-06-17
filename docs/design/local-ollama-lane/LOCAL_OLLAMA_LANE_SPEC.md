# Local Ollama Contestant Lane — Benchmark Enrollment Spec

**Version:** 0.1 (Draft)
**Date:** 2026-06-17
**Status:** Draft (pre-implementation). One code prerequisite (the localhost no-auth bug fix) is
being landed on a parallel branch and is referenced, not re-specified.
**Owner:** SDK / Summer 2026 Model Benchmark
**Related:** `docs/design/jetson-cluster-benchmark/` (the on-prem-lane precedent — REUSE the lane
machinery, NOT the adapter firewall), `docs/design/deepseek-vendor/`, `docs/design/model-benchmark/`,
[[project_summer2026_model_benchmark]], [[reference_edge_brains_contamination_probe]]

> Sibling effort to the Jetson on-prem lane. Jetson adds a **self-hosted edge** backend that serves
> **corpus-fine-tuned** adapters behind a strict three-vector firewall. This adds a **local,
> always-on, $0-marginal** lane of **clean general code models** already pulled into a localhost
> Ollama server — contestants that need **no new provider, no operator bring-up, and no
> applied-adapter firewall** (there are no adapters). The one thing they share with Jetson is the
> honest cost treatment (separate lane, never ranked on cost) and the pretraining-memorization caveat.

---

## 1. Goal

Enroll the code-specialized models already running on the developer's **localhost Ollama server**
(`localhost:11434`, OpenAI-compatible `/v1`) as a **separate "local" contestant lane** in the
Summer 2026 benchmark — measuring how a clean, free, locally-hosted code model compares to frontier
APIs on quality/speed, **without** letting its ≈$0 marginal cost trivially win the cost axis. The
lane **reuses the existing `ollama` provider**; the only code prerequisite is the localhost no-auth
agent-construction fix (below).

---

## 2. Grounding facts (verified live 2026-06-17 — cite, don't re-derive)

| Fact | Evidence |
|------|----------|
| A live Ollama server runs on `localhost:11434` exposing the OpenAI-compatible `/v1`. `ollama list` shows clean code models pulled: `qwen2.5-coder:14b`, `qwen2.5-coder:7b`, `codellama:latest`, `nemotron-3-nano:4b`, `startd8-coder:latest`, `gemma4:e2b/e4b/latest`, `gemma3:4b`. A live generation returned a valid OpenAI envelope (`system_fingerprint="fp_ollama"`). | live session probe |
| The `ollama` provider **exists and is registered** (entry point). `OllamaProvider.create_agent` builds `base_url=http://localhost:11434/v1` (via `OLLAMA_HOST`, `/v1` suffix enforced) and passes **`api_key=None`**. | `providers/openai.py:310-374` (`base_url` 356-360, `api_key=None` 365) |
| **PREREQUISITE (fixed on a parallel branch — do not re-spec):** `OpenAICompatibleAgent.__init__` only nulls the key for `localhost`/`127.0.0.1` URLs; for any URL the installed `openai` client **rejects `None`** ("api_key must be set"), so `create_agent('ollama', …)` currently raises. The fix is a sentinel placeholder (e.g. `"not-needed"`) instead of `None`. This spec **assumes it is fixed**. | `agents/openai.py:480-486` (the `if 'localhost' in base_url …: actual_api_key = None` block) |
| The benchmark `provider:model` spec splits on the **first** colon, so `ollama:qwen2.5-coder:14b` → provider=`ollama`, model=`qwen2.5-coder:14b` — the model's own colon is **preserved**. | `__init__.py:44` + `model_catalog.py:603` (`spec.split(":", 1)`) |
| The model's inner colon is path-safe: `slug()` regex-replaces it for filesystem ids; `cell_id` embeds the **raw** `cell.model` (colon preserved in the identity string, which is fine — no top-level `:` leaks because the role agents are slugged). | `model_comparison.py:slug:55-57`; `benchmark_matrix/runner.py:cell_id:64-72` |
| Localhost is the SDK's **nulled-key case** — no LAN, no `STARTD8_ALLOW_LAN_ENDPOINT` opt-in gate is needed (that gate exists only because Jetson dials a **plaintext RFC1918** box; localhost has no such exposure). | Jetson `FR-J12`; `agents/openai.py:484` |
| `$0`-marginal pricing entries already exist as a pattern under `provider="jetson"`, keyed under **both** the alias the estimate sees AND the served id the runtime tracker sees (the dual-key lesson from the Jetson dry-run). `PROVIDER_PATTERNS` has a per-provider list; the unknown-model fallback is a **flagged $3/$15-per-M** estimate (would make a free local model look expensive). | `costs/pricing.py:360-400` (dual-key), `PROVIDER_PATTERNS:403-410`, `_FALLBACK_*:456-457` |
| `model_catalog` already registers Ollama: `Models.STARTD8_CODER = "ollama:startd8-coder"` const, an `ollama` `_MODEL_REGISTRY` row, and an `ollama` `tier_map` block. New models extend these existing structures. | `model_catalog.py:189` (const), `:394-399` (registry row), `:535-539` (tier_map) |
| The Jetson lane runner (`jetson_lane.run_jetson_cell`) drives the provider **in-process** (the normal cell runs the agent in a `run_prime_workflow` subprocess the parent can't introspect), sends a NEUTRAL prompt, reads the agent capture, and calls `evaluate_jetson_cell` — which enforces the **applied-adapter echo** (FR-J5a) that is **irrelevant here** (no adapters). | `benchmark_matrix/jetson_lane.py:71-122`; `firewall.py:verify_applied_adapter:86-101` |

---

## 3. Requirements / Design

### Provider (reuse — no new provider)
- **FR-LO-1 — Reuse the existing `ollama` provider.** Unlike DeepSeek and Jetson (each got a
  dedicated provider), this lane adds **no new provider**. `OllamaProvider` already self-describes
  `base_url=http://localhost:11434/v1` and is registered (`providers/openai.py:310-374`). The
  `provider:model` spec carries no `base_url`, so enrollment needs **zero** changes to
  `BenchmarkRunSpec` / `build_command` / `runner` (same load-bearing simplification DeepSeek proved).
- **FR-LO-2 — Localhost no-auth fix is the ONLY code prerequisite.** Enrollment depends on the
  parallel-branch fix at `agents/openai.py:480-486` (sentinel placeholder instead of `None`). This
  spec references it as a prerequisite and **does not re-specify it**. Acceptance: once landed,
  `ProviderRegistry.get_provider('ollama').create_agent('qwen2.5-coder:14b')` returns an agent
  without raising.
- **FR-LO-3 — Inner-colon model ids are first-class.** Confirm (test) that
  `ollama:qwen2.5-coder:14b` resolves to provider=`ollama`, model=`qwen2.5-coder:14b` via the
  `split(":", 1)` path, that `slug()` produces a filesystem-safe id, and that `cell_id` round-trips
  (`split(":", 1)[0]` recovers the spec hash). No code change expected; this is a guard test.

### Catalog & pricing
- **FR-LO-4 — Catalog rows for the enrolled local models.** Extend the existing `ollama` structures
  in `model_catalog.py`: add `_MODEL_REGISTRY` `ModelInfo` rows (`provider="ollama"`, `tier="fast"`,
  capabilities `{"text","code"}`) for the v1 contestants (`qwen2.5-coder:14b`, `qwen2.5-coder:7b`,
  `codellama:latest`; others optional). Reuse the existing `ollama` `tier_map` block
  (`model_catalog.py:535-539`).
- **FR-LO-5 — $0 pricing entries, DUAL-KEYED (MANDATORY).** Each enrolled local model MUST have a
  `DEFAULT_PRICING` entry with `provider="ollama"`, `input/output_cost_per_million=0.0`,
  `estimated=True`, and a `notes` pointer — **otherwise it inherits the flagged $3/$15 fallback and
  looks expensive** (the exact mislead the Jetson FR-J9b guards). Apply the **dual-key lesson from
  the Jetson dry-run** (`costs/pricing.py:360-365`): the pre-run **estimate** keys on the public
  model id stripped from the `provider:model` spec, while the **runtime cost tracker** keys on the
  id the agent actually used — for Ollama these are **the same string** (no alias translation), so a
  single entry per model id suffices, but the requirement is stated in terms of "whichever id
  `resolve_pricing` receives at each call site," resolved by assertion (FR-LO-9), not assumed.
- **FR-LO-6 — `PROVIDER_PATTERNS` robustness.** Ensure `"ollama"` maps in `PROVIDER_PATTERNS`
  (`costs/pricing.py:403-410`) so `get_provider_for_model` attributes these ids to `ollama` even
  outside an exact-id match.

### Cost lane (the honesty constraint)
- **FR-LO-7 — Separate "local" lane, NEVER ranked on cost (same decision as Jetson OQ-J3).**
  Localhost marginal cost ≈ $0. Every local cell is tagged `cost_lane="local"` in cells.json and is
  **reported on its own**, never in the cloud cost ranking — because a $0 row trivially wins the cost
  axis, which is the opposite of a fair comparison. This is the Jetson on-prem-lane decision applied
  verbatim, differing only in the lane label (`local` vs `on-prem`).

### Contamination posture (the crucial DIFFERENCE from Jetson)
- **FR-LO-8 — General lane; NO applied-adapter firewall, NO in-domain fenced track.** These are
  **clean general code models** (qwen-coder, codellama, gemma, nemotron-nano) — **not fine-tuned on
  the OB/OTel corpus**. There are no LoRA adapters to load, so:
  - the Jetson **FR-J5a applied-adapter echo / firewall** (`firewall.py:verify_applied_adapter`) is
    **not applicable** — there is no "wrong adapter served a 200-OK" failure mode to close;
  - there is **no in-domain fenced track** — every local contestant runs in the **general lane**;
  - what **still applies**, exactly as for Jetson's clean baseline:
    - **(a) FR-J6 neutral-prompt fairness** — every local contestant MUST receive the **same neutral
      system prompt** the benchmark sends to all contestants (the PrimeContractor drafter prompt; the
      lane runner already sends a corpus-token-free `NEUTRAL_SYSTEM_PROMPT`, `jetson_lane.py:33-36`).
      No per-model special prompt. There is no corpus-aware serving default here (Ollama serves the
      model as-pulled), so this is a positive assertion, not a server-side fix.
    - **(b) the pretraining-memorization caveat** — these are **famous public models** that have
      almost certainly seen Online Boutique / the OTel demo on public GitHub **during pretraining**.
      So "clean" means **clean of OUR contamination vectors (no corpus fine-tune, no corpus prompt),
      NOT clean of pretraining exposure** — the irreducible vector shared by every frontier model
      (this is the Jetson FR-J8 residual / NR-J7 note, stated honestly). The **FR-47 perturbation
      probe** ([[reference_edge_brains_contamination_probe]]) is the only partial mitigation and any
      published local-lane result MUST carry this caveat.

### Validation
- **FR-LO-9 — Offline dry-run + pricing-key assertion.** `run_behavioral_pilot.py --dry-run --model
  ollama:qwen2.5-coder:14b` MUST produce a **finite, non-fallback** cost estimate (proves
  FR-LO-4/5/6 wired). A test drives the real `create_agent`→cost path and asserts
  `resolve_pricing(<id the tracker sees>)` is non-fallback for each enrolled model — a fallback-priced
  `ollama:*` entry is a release blocker (mirrors Jetson R1-F3/FR-J9b).
- **FR-LO-10 — End-to-end smoke (no operator step).** Because the server is **always on**, the smoke
  is one command: `run_behavioral_pilot.py --run --model ollama:qwen2.5-coder:14b` → one local cell,
  scored by the existing benchmark scorer, with provenance carrying `cost_lane="local"`, the model id,
  the neutral system prompt actually sent, and the sampling config. No `start_*` bring-up step (the
  Jetson Step 8.1 has no counterpart here).
- **FR-LO-11 — Provenance / honesty (no silent caps).** Each local cell records: `cost_lane="local"`,
  `model`, `sampling` (temperature/top_p/seed), and a `contestant_kind="local-pretraining-caveat"`
  label so a reader knows it is a clean-of-our-vectors-but-not-pretraining contestant. Nothing about
  the result is silently capped or hidden.

---

## 4. Comparison to the Jetson lane

| Dimension | Jetson on-prem lane | **Local Ollama lane (this spec)** |
|-----------|---------------------|-----------------------------------|
| Provider | dedicated `jetson` provider | **reuse existing `ollama`** (no new provider) |
| Endpoint | plaintext HTTP on RFC1918 LAN (`192.168.7.57:8000`) | **localhost** (`127.0.0.1:11434`) — SDK's nulled-key case |
| Security opt-in | `STARTD8_ALLOW_LAN_ENDPOINT=1` required (FR-J12) | **none needed** — no LAN exposure |
| Auth | sentinel key that bypasses the localhost-only guard | localhost no-auth (sentinel placeholder per FR-LO-2) |
| Availability | "not always-on"; operator bring-up (`start_fastapi_on_rosie.sh`) | **always-on**; no bring-up step |
| Models | base Mistral-7B + **corpus-fine-tuned LoRA adapters** | **clean general code models** (qwen-coder, codellama, …) |
| Adapter firewall | **mandatory** (FR-J5a echo, in-domain fenced track) | **N/A** — no adapters; general lane only |
| Neutral prompt (FR-J6) | required (server-side fix + assert) | required (positive assertion; no server fix) |
| Pretraining caveat | applies (FR-J8 residual) | **applies identically** |
| Cost treatment | separate `on-prem` lane, never cost-ranked (OQ-J3) | separate `local` lane, never cost-ranked (same decision) |
| Distinct value | edge-hardware story + fine-tuned in-domain adapters | clean + free + always-on; lowest-friction local contestant |

The two lanes are complementary: Jetson keeps its distinct value (the $500-edge-box story and the
in-domain adapter study); this lane is the clean, zero-friction local baseline.

---

## 5. Runner: reuse vs lean variant (RECOMMENDATION)

`jetson_lane.run_jetson_cell` (`benchmark_matrix/jetson_lane.py:71-122`) does three things: (1) sends
the neutral prompt + recorded sampling, (2) reads the agent capture, (3) calls `evaluate_jetson_cell`
— which enforces the **applied-adapter echo** verdict (`firewall.py:86-101`). Step (3) is **wholly
irrelevant** here: Ollama returns `system_fingerprint="fp_ollama"`, never a `served_adapter=` echo, so
`verify_applied_adapter` would always fail ("echo missing") and invalidate every clean local cell.

**Two options:**
- **(A) Generalize the lane runner** — add a `firewall=None` / `lane="local"` mode to
  `run_jetson_cell` that skips the adapter-echo verdict but keeps neutral-prompt + provenance
  (cost_lane, sampling, model). Risk: couples a clean-model path into the firewall-heavy module and
  muddies the Jetson runner's single responsibility.
- **(B) Lean `local_lane.py`** — a small sibling (`benchmark_matrix/local_lane.py`) that keeps the
  in-process driving pattern, the `NEUTRAL_SYSTEM_PROMPT`, the `DEFAULT_SAMPLING`, and a
  `LocalCellRecord` (cost_lane="local", model, sampling, text) but **drops the firewall verdict
  entirely** — there is nothing to firewall. It can still import the shared neutral-prompt constant
  and the partition/scored helpers.

**RECOMMENDATION: (B), the lean `local_lane.py`.** The adapter-echo verdict is the entire reason
`jetson_lane` exists; a clean general-model lane has no such verdict and should not carry the firewall
import or its failure modes. (B) keeps each module's responsibility crisp, makes the local lane fully
offline-testable with a mock agent (no firewall fixtures), and avoids a conditional that could
silently mis-fence a clean cell. Share only the neutral-prompt constant and the track/partition
helpers.

---

## 6. Non-Requirements

- **NR-LO-1** — No new provider (FR-LO-1 reuses `ollama`).
- **NR-LO-2** — No new serving/deployment work; the Ollama server is operator-managed and already up.
- **NR-LO-3** — No applied-adapter firewall, no in-domain fenced track (FR-LO-8 — no adapters exist).
- **NR-LO-4** — No `STARTD8_ALLOW_LAN_ENDPOINT` opt-in gate (localhost is not a LAN exposure).
- **NR-LO-5** — No cost-ranking of local cells against cloud models (FR-LO-7).
- **NR-LO-6** — Pretraining contamination is NOT eliminated; only OUR vectors are absent. The probe
  estimates it; v1 does not scrub or certify pretraining-clean weights.
- **NR-LO-7** — No re-specification of the localhost no-auth fix (FR-LO-2 references the parallel branch).

---

## 7. Open Questions

- **OQ-LO-1 — Which models in v1?** Default: `qwen2.5-coder:14b` + `qwen2.5-coder:7b` (strongest code
  models present); `codellama:latest` as a third. `startd8-coder` is already cataloged but is
  micro-prime-tuned (REQ-MP-104) — enroll as a contestant or keep it out of the general lane? Lean:
  keep `startd8-coder` out of the *general* lane to avoid an SDK-favored datapoint.
- **OQ-LO-2 — Run the FR-47 perturbation probe per local model, or document-only in v1?** The probe
  is the only partial mitigation for the pretraining caveat; a real run strengthens the honesty claim
  but adds cost/time. Default: document the caveat in v1; run the probe as a fast-follow.
- **OQ-LO-3 — `max_tokens` / sampling defaults for local code models.** `OllamaProvider` defaults
  `max_tokens=4096` (`providers/openai.py:367`), tighter than cloud contestants (8K–16K). Confirm a
  fair, recorded value so a truncation isn't scored as a model failure; record it in provenance.
- **OQ-LO-4 — Add any local model to `DEFAULT_MODELS`?** Default: opt-in via `--model` only (a local
  cell should not run on every default pilot), matching DeepSeek OQ-4 / Jetson FR-J2.
- **OQ-LO-5 — `OLLAMA_HOST` override seam.** `base_url` already honors `OLLAMA_HOST`
  (`providers/openai.py:356`); confirm tests can point the lane at a mock OpenAI server via that env
  (the local analogue of Jetson's `JETSON_BASE_URL` seam), keeping the lane offline-testable.

---

## 8. Effort

`model_catalog` rows + `DEFAULT_PRICING` dual-keyed $0 entries + `PROVIDER_PATTERNS` (FR-LO-4/5/6):
**small.** Lean `local_lane.py` (~80 LOC, mirrors `jetson_lane` minus the firewall) + the inner-colon
guard test + the offline dry-run / pricing-key assertion (FR-LO-3/9): **~½ session.** No new provider,
no new dependency, no serving work, no operator step. Gated only on the localhost no-auth fix
(FR-LO-2) landing from the parallel branch. Fully offline-testable (mock the agent; point
`OLLAMA_HOST` at a stub).

---

*Draft 0.1. Key decisions: reuse the `ollama` provider (only prerequisite = the localhost no-auth
fix); treat as a separate `local` lane never cost-ranked (Jetson OQ-J3 applied); general lane with NO
adapter firewall (clean models, no adapters) but KEEPING the neutral-prompt fairness rule and the
pretraining-memorization caveat; recommend a lean `local_lane.py` over generalizing the
firewall-heavy `jetson_lane`. Ready for CRP.*
