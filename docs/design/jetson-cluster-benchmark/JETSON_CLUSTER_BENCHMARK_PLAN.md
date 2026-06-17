# Jetson Cluster Benchmark Enrollment — Implementation Plan

**Version:** 1.1 (Post-CRP R1 — 10/10 S-suggestions applied; see Appendix A)
**Date:** 2026-06-16
**Tracks:** `JETSON_CLUSTER_BENCHMARK_REQUIREMENTS.md` v0.3
**Precedent:** DeepSeek vendor wiring (PR #5) — same recipe, **but R1-S10 divergences apply**
(DeepSeek = TLS + real key + clean vendor; Jetson = plaintext LAN + sentinel key + contaminated
adapters — do not import those assurances).
**Estimated effort:** SDK side ~1 focused session; gated on operator (endpoint up) + one server check.

---

## Reality map (verified during planning)

| Concern | File:Line | Note |
|---------|-----------|------|
| Provider recipe to copy | `src/startd8/providers/deepseek.py` (this PR) | hardcoded base_url + sentinel key + alias map |
| No-auth only localhost | `agents/openai.py:484` | `192.168.x.x` NOT covered → FR-J11 sentinel key |
| Agent stores base_url | `agents/openai.py:62` (`self.base_url`) | test assertion target |
| Spec → command | `model_comparison.py:build_command:149`; `slug():55` | `--lead/--drafter` = spec; paths slug-safe |
| cell_id embeds raw model | `benchmark_matrix/runner.py:cell_id` | argues for slash-free aliases (FR-J3a) |
| Pricing fallback $3/$15 | `costs/pricing.py` `_FALLBACK_INPUT/OUTPUT_PER_M` | FR-J9b: explicit entries mandatory |
| Infra-fail covers unreachable | `runner.py:_INFRA_ERROR_MARKERS` (connection error) | FR-J1 needs no new code |
| Benchmark sends own system | `prime_contractor.py:2646` + `agents/openai.py:111` | FR-J6 is server-side only |
| Registration (dual) | `pyproject.toml` providers group + `registry.py:_register_builtin_providers` | mirror DeepSeek |

---

## Steps

### Step 1 — `jetson` provider (FR-J3, FR-J3a, FR-J11, FR-J12; R1-S1/S2/S10)
Create `src/startd8/providers/jetson.py` from `deepseek.py`, changing:
- `BASE_URL = os.getenv('JETSON_BASE_URL', 'http://192.168.7.57:8000/v1')` **(R1-S2: env-overridable,
  not a bare constant — survives DHCP/host changes and lets tests point at a mock server).**
- **Opt-in guard (R1-S1/FR-J12):** `create_agent` raises unless `STARTD8_ALLOW_LAN_ENDPOINT=1`, so the
  SDK never silently dials a plaintext LAN box with a bypass key. Module docstring carries the threat
  model + the "what does NOT transfer from DeepSeek" note (R1-S10: TLS, key semantics, contamination).
- `ALIASES = {"mistral-7b-base": "mistralai/Mistral-7B-v0.3", "iter-002": "iter_002", ...}`;
  `MODELS = list(ALIASES)`.
- `create_agent`: translate alias → real id (`served = self.ALIASES.get(model, model)`), pass `served`
  as the agent `model`; `api_key = config.get('api_key') or os.getenv('LOCAL_FASTAPI_API_KEY', 'local-no-auth')`.
- `name="jetson"`, `display_name="Jetson Edge Cluster"`.
- Each alias's `MODEL_INFO` carries a `contamination` label: `"clean"` (mistral-7b-base) vs
  `"in-domain-finetune"` (iter-002).

### Step 2 — Dual registration (mirror DeepSeek)
- `pyproject.toml`: `jetson = "startd8.providers.jetson:JetsonProvider"`.
- `registry.py:_register_builtin_providers`: add the guarded `from .jetson import JetsonProvider` block.

### Step 3 — Catalog (FR-J8/J9)
- `model_catalog.py`: `Models.JETSON_MISTRAL_BASE = "jetson:mistral-7b-base"` (+ iter alias);
  `_MODEL_REGISTRY` rows (`provider="jetson"`, tier `fast`, capabilities `{"text","code"}`);
  `tier_map["jetson"]`.

### Step 4 — Pricing (FR-J9b; R1-S6/S7)
- `costs/pricing.py` `DEFAULT_PRICING`: entries `provider="jetson"`, `estimated=True`, keyed under
  **whichever id `resolve_pricing` actually receives** in the create_agent→cost-tracker path.
- **R1-S6: resolve the key by ASSERTION, not "test both."** Step 7 adds a test that drives a real
  `create_agent`→cost path and asserts `resolve_pricing(<id the tracker sees>)` is non-fallback for
  both aliases. A fallback-priced alias is a release blocker (FR-J9b).
- **R1-S7/OQ-J3 cost-axis gate:** do NOT let a Jetson row onto a cost ranking until OQ-J3 is decided;
  tag a `cost_lane` (e.g. `free-on-prem`) in cells.json so the ≈$0 figure can't rank against amortized
  cloud cost. Add `"jetson": ["jetson"]` to `PROVIDER_PATTERNS`.

### Step 4b — Inference-config determinism (FR-J6b; R1-S4) — NEW
- Pin canonical sampling params (temperature/top_p/seed) and NF4 quant config; pass them explicitly
  and record them in provenance. A base-vs-adapter comparison with mismatched sampling/quant is a
  provenance error (invalidates the clean-vs-in-domain claim).

### Step 5 — Contamination labels & provenance (FR-J5, FR-J5a, FR-J7; R1-S9)
- Surface the per-alias `contamination` label in the matrix report / cells.json so in-domain cells are
  fenced off from the general leaderboard.
- **R1-S9/FR-J5a: capture the server-reported applied adapter id** into provenance and assert it
  matches the requested alias; a mismatch (unloaded/base-fallback adapter returning 200-OK)
  **invalidates the cell** — it is NOT an `infra_fail` and must not be scored.
- **VERIFIED 2026-06-16 — server side done (PARTIAL→closed), SDK side pending.** Findings on
  `edge-brains/scripts/fastapi_serve.py`:
  - ✅ unknown/renamed adapter already SAFE — `_set_adapter` raises `HTTPException(404)` → SDK
    classifies as `infra_fail` (the silent-fallback fear does not apply to *unknown* names).
  - ❌ was: response echoed `req.model` only (no applied-adapter signal); `state["active"]` went
    **stale on base requests** (use_base path skipped `_set_adapter`). **Fixed:** response now carries
    `system_fingerprint="served_adapter=<state.active>"` (server truth, independent of req.model), and
    the base path sets `state["active"]="__base__"` so the echo is truthful. Compiles.
  - ⚠️ residual: the sync endpoint mutates shared adapter state in a threadpool — **serial runs only**
    until a per-request lock or per-adapter model handle exists (note for the operator; benchmark
    cells are serial today).
  - **SDK-side verdict logic BUILT 2026-06-16** (`benchmark_matrix/firewall.py`): `evaluate_jetson_cell()`
    parses the `served_adapter=` echo, asserts it matches the requested alias's served id (mismatch ⇒
    `invalidated`, track=`invalid`), checks the sent prompt byte-equals neutral + carries no banned
    corpus tokens (FR-J6), and checks sampling/quant are recorded (FR-J6b). Returns a `FirewallVerdict`
    with `track` ∈ {general, in-domain, invalid} + `as_provenance()` for cells.json. 16 offline tests.
  - **Runtime wiring BUILT 2026-06-17** (`benchmark_matrix/jetson_lane.py` + agent capture):
    `OpenAICompatibleAgent` now records `last_system_fingerprint` + `last_system_prompt` after each
    `agenerate`; the **in-process** `run_jetson_cell()` sends the neutral prompt + recorded sampling,
    reads that capture, calls `evaluate_jetson_cell`, attaches `verdict.as_provenance()` +
    `cost_lane="on-prem"` + the pinned `server_commit_sha`, and sets `scored=False` for any cell that
    lands in the `invalid` track (wrong/absent adapter echo OR clean-label vector failure).
    `partition_by_track` / `scored_cells` split general / in-domain / invalid. 8 offline tests (mock
    agent). **In-process by design:** the normal benchmark cell runs the agent in a `run_prime_workflow`
    subprocess (parent can't read agent attrs), so the on-prem lane drives `JetsonProvider` directly —
    which also makes the firewall fully testable offline.
  - **Remaining = operator/cluster only:** bring rosie up with the FR-J6/J5a server fix
    (SHA `27e714fc`), pass that SHA as `server_commit_sha`, run a live cell. No SDK code left.

### Step 6 — Server-side neutral-prompt gate (FR-J6; R1-S3) — edge-brains + recorded artifact
- **VERIFIED 2026-06-16 — BUG CONFIRMED + FIXED.** `edge-brains/scripts/fastapi_serve.py::_format_chat`
  extracted only the `user` message and **force-prepended the corpus-aware `SYSTEM_PROMPT`**,
  discarding any request system message — so every served model (incl. a clean baseline) was getting
  the corpus prompt. The firewall control was broken at the server. Fixed: `_format_chat` now honors a
  request `role=="system"` message and falls back to `SYSTEM_PROMPT` only when none is supplied
  (backward-compatible with iter_002 training-time behavior). Compiles (`py_compile`).
  - **Caveat:** edge-brains has **no git remote** and pre-existing uncommitted edits in the same file
    (a separate sampling-params change). The FR-J6 fix is applied to the **working tree, uncommitted**,
    to avoid entangling that in-flight work. **SHA-pin pending:** record the `fastapi_serve.py` commit
    SHA in provenance once edge-brains is committed (operator).
- **R1-S3 (fail-closed, recorded):** Step 8 writes the request's actual system content into provenance
  and the smoke ASSERTS it byte-equals the benchmark drafter prompt AND contains no banned corpus
  tokens (FR-J6 acceptance). Pin the verified `fastapi_serve.py` commit SHA in provenance. Not a
  silently-skippable checklist item.

### Step 7 — Tests (mirror DeepSeek test file; R1-S5/S6/S8)
`tests/unit/providers/test_jetson_provider.py`: registry resolves `jetson`; alias→served-id
translation; sentinel key applied when no env; **opt-in guard refuses without `STARTD8_ALLOW_LAN_ENDPOINT`
(R1-S1)**; `base_url` reflects `JETSON_BASE_URL` override and the default when unset (R1-S2); pricing
real/non-fallback for the id the tracker sees (R1-S6); `get_provider_for_model` → `"jetson"`; clean vs
in-domain label present.
- **R1-S8 offline negative test:** with the network blocked, the dry-run cost is finite and
  non-fallback and **no socket is opened** — proves Steps 1–4b+7 are truly offline-landable.
- **R1-S5 alias-drift test (endpoint-gated):** `GET /v1/models` superset-contains every
  `ALIASES.values()`; a missing target fails loudly naming the id.

### Step 8 — End-to-end smoke (FR-J10) — operator-gated
1. Operator: `bash edge-brains/scripts/start_fastapi_on_rosie.sh`; confirm `curl …:8000/v1/models`.
2. `python3 scripts/run_behavioral_pilot.py --model jetson:mistral-7b-base --dry-run` → finite,
   non-fallback cost estimate.
3. One live `--run` cell; confirm scored output; assert provenance carries: applied-adapter id ==
   requested (R1-S9), system prompt == neutral & banned-token-free (R1-S3), sampling+quant recorded
   (R1-S4), `cost_lane` tag (R1-S7).

---

## Sequencing & risk
1. Steps 1–4 + 7 are pure SDK and can land + be tested **without the cluster online** (DeepSeek proved
   the dry-run path is offline). Steps 6 & 8 are operator/cluster-gated.
2. **Branch-first** off `origin/main` (`feat/jetson-vendor`); do not merge into shared main locally
   ([[reference_multiworktree_env]] contended-main hazard).
3. Pin `PYTHONPATH=<worktree>/src` for pytest.
4. **Do not enroll iter-002 on the general leaderboard** — FR-J5/J7 labels + FR-J6 server check are
   prerequisites; the clean `mistral-7b-base` is the v1 deliverable.

## Traceability
| FR | Step |
|----|------|
| FR-J1 | (none — already covered) / 8 optional |
| FR-J2 | 3 (opt-in; not in DEFAULT_MODELS) |
| FR-J3 / J3a / J11 | 1 |
| FR-J4 | 1 |
| FR-J5 / J7 | 1, 5 |
| FR-J6 | 6 (server-side) |
| FR-J8 / J9 | 3 |
| FR-J9b | 4 |
| FR-J10 | 8 |

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
| R1-S1 | Threat model + opt-in env guard for LAN HTTP target | R1 (opus-4-8) | Step 1 opt-in guard; mirrors req FR-J12 | 2026-06-16 |
| R1-S2 | Env-overridable `JETSON_BASE_URL` | R1 | Step 1 BASE_URL via os.getenv | 2026-06-16 |
| R1-S3 | FR-J6 promoted to recorded fail-closed gate + pinned SHA | R1 | Step 6 + Step 8.3; req FR-J6 acceptance | 2026-06-16 |
| R1-S4 | Inference-config determinism (sampling+quant pinned/recorded) | R1 | New Step 4b; req FR-J6b | 2026-06-16 |
| R1-S5 | Alias-drift guard vs `/v1/models` | R1 | Step 7 endpoint-gated test; req FR-J3a | 2026-06-16 |
| R1-S6 | Pricing-key resolved by assertion (not "test both") | R1 | Step 4 + Step 7; req FR-J9b | 2026-06-16 |
| R1-S7 | Cost-lane gate before any cost ranking | R1 | Step 4 cost_lane tag; req FR-J8/OQ-J3 | 2026-06-16 |
| R1-S8 | Offline network-blocked dry-run test | R1 | Step 7 negative test | 2026-06-16 |
| R1-S9 | Reachable-but-wrong-adapter: echo + assert applied adapter | R1 | Step 5; req FR-J5a | 2026-06-16 |
| R1-S10 | "What does NOT transfer from DeepSeek" note | R1 | Header + Step 1 docstring | 2026-06-16 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-16

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-16 19:40:00 UTC
- **Scope**: Full architectural review (plan) with requirements traceability. Focus per orchestrator brief: contamination firewall, cost-representation fairness, provider/alias design, server-side prompt dependency, reproducibility of a non-CI LAN endpoint, security of a LAN HTTP + sentinel-key target.

**Executive summary (top risks / opportunities / blocking gaps):**

- FR-J6 (server-side neutral-prompt verify) is the single highest-leverage gate yet it lives in *another repo* (edge-brains) as a checklist item (Step 6) with no pinned commit, recorded evidence artifact, or fail-closed mechanism in this repo — the firewall's load-bearing control is unenforced here.
- The firewall has a known *third* leakage path the plan does not address: NF4 quantization + sampling params (temperature/top_p/seed) drift between runs and between base vs adapter, which can confound "clean vs in-domain" comparisons even with prompts neutralized.
- Cost fairness (FR-J9b / OQ-J3) is left as "start ≈$0 with an amortized note" — an unresolved policy that the plan ships before deciding, so the first real leaderboard row may be misleading exactly as the requirements warned against.
- Security: pointing the SDK at `http://192.168.7.57` (plaintext HTTP, hardcoded RFC1918 IP, sentinel key that bypasses the SDK's localhost-only key-null guard) has no documented threat model — anyone on the LAN can MITM/serve a malicious OpenAI-shaped response into the scorer.
- Reproducibility: a hardcoded `BASE_URL` constant + a non-CI, "not always-on" endpoint means runs are non-reproducible and provider tests can only assert the *constant*, never the wiring; no override seam (env var) is provided.
- Provider/alias design has no test or guard that the `ALIASES` map stays in sync with what the server actually serves (`/v1/models`), so a silent server-side rename produces an `infra_fail` that looks like a model failure — or worse, a wrong-adapter run.
- Opportunity (low-hanging): the FR-J7 provenance fields (sampling params, exact system prompt, quantization, host) are mostly already in hand at request time; capturing them into cells.json is the same edit as the FR-J5 label surfacing in Step 5.
- Pricing-key ambiguity (Step 4 note) is flagged but not resolved: which id the cost tracker actually receives (alias vs served id) must be pinned by an assertion, or the mandatory FR-J9b entry silently misses and the fallback fires.
- The plan declares "do not enroll iter-002 on the general leaderboard" (Sequencing #4) but no code-level gate enforces the separation — it relies on operator discipline plus a report label.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | high | Add an explicit threat-model note + a hard opt-in guard for the LAN HTTP target: document that `BASE_URL` is plaintext HTTP on RFC1918 with a sentinel key (no transport auth/integrity), and require an env opt-in (e.g. `STARTD8_ALLOW_LAN_ENDPOINT=1`) before `JetsonProvider.create_agent` will return an agent, so the SDK never silently dials a LAN box. | A hardcoded LAN IP + sentinel key bypasses the SDK's localhost-only key-null safety (`agents/openai.py:484`); any host on the LAN can impersonate the endpoint and feed crafted completions into the scorer. Today nothing distinguishes "intended Jetson run" from "misconfig dialing a stranger." | Step 1 (provider) + new "Security" subsection under "Sequencing & risk" | Unit test: `create_agent` raises/refuses without the opt-in env; integration smoke only runs with it set. |
| R1-S2 | Ops | high | Make the endpoint location overridable: source `BASE_URL` from `os.getenv('JETSON_BASE_URL', 'http://192.168.7.57:8000/v1')` instead of a bare constant. | Step 1 hardcodes `BASE_URL = "http://192.168.7.57:8000/v1"`. A DHCP lease change, a different serving host (astro/judy/elroy are listed), or a tunnel makes the provider unusable and forces a code edit + reinstall. An env seam also lets tests point at a mock server. | Step 1, `BASE_URL` line | Test: with `JETSON_BASE_URL` set, agent `base_url` reflects the override; default preserved when unset. |
| R1-S3 | Validation | high | Promote FR-J6 from an out-of-repo checklist item to a recorded, fail-closed gate: have Step 8 write the request's actual `messages[0]` (system content) into the provenance/cells.json and add an assertion in the smoke that it equals the benchmark's drafter system prompt (not the corpus default). Pin the edge-brains `fastapi_serve.py` commit SHA verified. | Step 6 says "Gate any fair run on this" but provides no artifact, no SHA, and no in-repo check; the firewall's most important control is therefore unauditable and silently skippable. | Step 6 + Step 8.3 | Smoke asserts captured system prompt == expected neutral prompt; provenance records the verified edge-brains commit SHA. |
| R1-S4 | Risks | high | Add a fourth contamination/confound control for inference determinism: pin and record sampling params (temperature, top_p, seed) and the NF4 quant config identically for base and adapter runs; treat a mismatch as a provenance error. | FR-J5/J6 neutralize fine-tune and prompt vectors, but a clean-vs-in-domain comparison is still confounded if the base runs at temp 0.0 and an adapter at temp 0.7, or quant differs. The plan's Steps 1/5/8 never mention sampling determinism. | New Step (between 5 and 6) + FR traceability row | Smoke records sampling params in provenance; test asserts they are present and non-null; document the canonical values. |
| R1-S5 | Interfaces | medium | Add an alias-drift guard: in Step 8 (or a dedicated test that runs only when the endpoint is up), fetch `GET /v1/models` and assert every `ALIASES` served-id target is actually present; fail loudly with the missing id rather than letting it surface as a generic `infra_fail`. | A server-side adapter rename (`iter_002`→`iter-002b`) or an unloaded adapter currently degrades to `infra_fail` (looks like model failure) or, if the name is reused, a wrong-adapter run scored as the wrong contestant. The plan's reality map notes `cell_id` embeds the raw model but never checks the alias targets exist. | Step 7/8 | Endpoint-gated test: `/v1/models` superset-contains all `ALIASES.values()`. |
| R1-S6 | Data | medium | Resolve the pricing-key ambiguity deterministically in Step 4: add a test that drives a real `create_agent`→cost-tracker path and asserts the cost layer keys on the *served* id (and that `resolve_pricing` returns the non-fallback entry), rather than leaving "Test both" as a note. | Step 4's own note admits uncertainty about which id the cost tracker receives. If it keys on the alias while pricing is registered under the served id, the mandatory FR-J9b entry silently misses and the $3/$15 fallback fires — the exact "actively misleading leaderboard" the requirements call out. | Step 4 + Step 7 | Test asserts `resolve_pricing(<id the tracker actually sees>)` is non-fallback for both aliases. |
| R1-S7 | Ops | medium | Decide OQ-J3 (cost representation) before the v1 deliverable ships, or explicitly gate the clean-baseline leaderboard row behind a "free/on-prem lane" so the ≈$0 figure cannot rank against amortized-cost frontier APIs. | Step 4 ships "start ≈$0 marginal with an amortized note" while OQ-J3 is still open; a $0 marginal cost trivially wins the cost axis, which the requirements explicitly warn is the opposite of a fair comparison. Shipping the row before the policy decision bakes in the bias. | Step 4 + Sequencing & risk #4 | Reviewer check: leaderboard either excludes Jetson from the cost ranking or applies the documented amortized figure; assert a "lane" tag in cells.json. |
| R1-S8 | Validation | medium | Add a negative/offline test asserting the dry-run path produces a finite, non-fallback cost estimate with the endpoint DOWN (no network), proving Steps 1–4+7 are truly offline-landable as Sequencing #1 claims. | Sequencing #1 asserts the SDK side lands and tests "without the cluster online," but no test pins this; a hidden network call in `create_agent`/pricing would break the claim and only surface in operator-gated Step 8. | Step 7 | CI test with network blocked: dry-run cost is finite and non-fallback; no socket opened. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S9 | Risks | medium | Define behavior when the LAN endpoint is reachable but the requested adapter is NOT loaded (PEFT `set_adapter` fail / silent fallback to base). A reachable-but-wrong server does NOT match `_INFRA_ERROR_MARKERS`, so FR-J1's "auto-excluded as infra_fail" guarantee does not hold — a base-model response could be scored as `iter-002`. | The requirements lean heavily on connection errors being auto-classified, but a 200-OK response from the wrong/unloaded adapter is the dangerous case that bypasses every existing guard. | Sequencing & risk + Step 8 | Endpoint-gated test: request a known adapter, assert the response/provenance reflects the adapter actually applied (server should echo applied adapter id). |
| R1-S10 | Architecture | low | Note the precedent-coupling risk: the plan reuses `deepseek.py` "exact recipe," but DeepSeek is a clean hosted vendor with TLS + a real key, whereas Jetson is plaintext-LAN + sentinel + contaminated adapters. Call out which DeepSeek properties do NOT transfer (transport security, key semantics, contamination posture) so the copy doesn't import false assurances. | "Same recipe, this plan reuses it" (header + reality map) risks copying security/cost assumptions that are valid for DeepSeek but false for an on-prem LAN box. | Header / "Precedent" line + Step 1 | Doc review: a "what does NOT transfer from DeepSeek" list exists; provider code comments mark the divergences. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; Appendix C had no prior suggestions.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement in `JETSON_CLUSTER_BENCHMARK_REQUIREMENTS.md` v0.2 to the plan step(s) that address it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-J1 — Preflight + bring-up | Reality map (infra-fail row); Step 8.1; Traceability "none/8 optional" | Partial | Optional `/health` + `/v1/models` preflight nicety is mentioned but not implemented; reachable-but-wrong-adapter case (R1-S9) not covered by the infra-fail guarantee. |
| FR-J2 — Not a default-roster cell | Step 3 (opt-in, not in DEFAULT_MODELS) | Full | — |
| FR-J3 — Dedicated `jetson` provider | Step 1; Step 2 (registration) | Full | — |
| FR-J3a — Clean slash-free aliases | Step 1 (`ALIASES` map) | Partial | No guard that aliases stay in sync with the server's actual `/v1/models` (R1-S5); silent drift risk. |
| FR-J4 — Reuse proven config shape | Step 1 | Partial | DeepSeek properties that do NOT transfer (TLS, key semantics, contamination) are not distinguished (R1-S10). |
| FR-J5 — Fine-tuning vector firewall | Step 1 (contamination label); Step 5 (surface label) | Partial | Label is surfaced in the report but no code-level gate keeps in-domain cells off the general leaderboard (Sequencing #4 is operator discipline only). |
| FR-J6 — System-prompt vector (server-side verify) | Step 6 (edge-brains checklist); Step 8.3 | Partial | Out-of-repo checklist with no pinned SHA, no recorded evidence artifact, no in-repo fail-closed assertion (R1-S3). |
| FR-J7 — Provenance labels | Step 5; Step 8.3 | Partial | Sampling params + quantization config + exact system prompt enumerated in the requirement are not all shown captured into cells.json; determinism not pinned (R1-S4). |
| FR-J8 — Clean baseline first | Step 8; Sequencing #4 | Partial | Cost-axis representation (≈$0 vs amortized) unresolved before the v1 row ships (R1-S7, OQ-J3). |
| FR-J9 — Optional clean small model (Qwen) | Step 3 (catalog mention); OQ-J2 | Partial | Serve setup for Qwen unvalidated; deferred via OQ-J2 — acceptable but flagged. |
| FR-J9b — Explicit per-alias pricing (MANDATORY) | Step 4 | Partial | Pricing-key ambiguity (alias vs served id) unresolved (Step 4 note "Test both"); risk the mandatory entry silently misses and the $3/$15 fallback fires (R1-S6). |
| FR-J10 — End-to-end smoke | Step 8 | Full | — (depth additions proposed in R1-S3/S5/S8/S9 but the requirement itself is addressed). |
| FR-J11 — Sentinel key for no-auth LAN endpoint | Step 1 (`create_agent` api_key) | Partial | No threat model / opt-in guard for dialing a plaintext LAN box with a bypass key (R1-S1). |
