# Loopback Mock-LLM Sidecar — Behavioral Coverage for AskProductAIAssistant

**Version:** 0.1 (Draft sketch)
**Date:** 2026-06-17
**Follow-on to:** `OTEL_DEMO_SEED_EXTRACTION_PLAN.md` (OQ-OT-2)
**Related:** `benchmark_matrix/behavioral/` (Track 2), `benchmark_matrix/sandbox.py` (FR-44),
[[project_summer2026_model_benchmark]]

---

## 1. Goal

Let Track-2 (behavioral) score `ProductReviewService.AskProductAIAssistant` — an RPC whose generated
implementation calls an external LLM — by running a tiny **trusted, loopback OpenAI-compatible mock
server** the sandboxed service-under-test (SUT) dials instead of a real model. Deterministic, offline,
no secrets, **no egress relaxation**.

## 2. Grounding facts (verified 2026-06-17)

- **Loopback is already allowed.** `sandbox._wrap_loopback_only` emits a Seatbelt profile that denies
  `network*` then re-allows `network-outbound (remote ip "localhost:*")` (+ bind/inbound). The SUT can
  already reach a loopback sidecar; **nothing in the network sandbox needs to change.**
- **Env injection is already post-scrub.** `run_service_sandboxed` does `env = scrub_env(...)` then
  `env.update(extra_env)` (sandbox.py:305-307). We inject the mock endpoint + a **dummy** key via
  `extra_env`; real secrets stay stripped.
- **The OTel service reads** (all required, `must_map_env`): `LLM_HOST`, `LLM_PORT`, `LLM_BASE_URL`,
  `OPENAI_API_KEY`, `LLM_MODEL`; it builds `llm_mock_url = http://{LLM_HOST}:{LLM_PORT}/v1`. It already
  has a **mock-LLM code path** (and an `llmRateLimitError` feature flag) — it is *designed* to talk to
  a mock, which makes faithful generated code use our endpoint by construction.
- **The mock is OUR code → it runs OUTSIDE the sandbox** (in the parent harness, like the gRPC test
  client already does). Only the SUT is sandboxed. Trusted-outside / untrusted-inside, talking over
  loopback.

## 3. Design

### 3.1 The mock server — `benchmark_matrix/behavioral/mock_llm.py`
- **stdlib `http.server`** (no new dependency, nothing to fetch at run time). One handler:
  - `POST /v1/chat/completions` → a **deterministic canned** `chat.completion` JSON: a fixed assistant
    message carrying a recognizable marker token (e.g. `"[[MOCK_LLM_OK]]"`) + tool-call echo if the
    request includes tools (the service defines a tool). Stable `id`, `created=0`, `model="mock"`.
  - `GET /v1/models` → `{"data":[{"id":"mock","object":"model"}]}`; `GET /health` → `ok`.
- `start_mock_llm() -> (host, port, stop_fn)`: bind `127.0.0.1:0` (free port), serve in a daemon
  thread, return the port + a `stop_fn` for guaranteed teardown.
- Optional `mode="rate_limit"` → return HTTP 429 (to exercise the service's `llmRateLimitError` path
  as a negative behavioral invariant).

### 3.2 Wiring into `run_behavioral_cell`
For a cell whose service needs the LLM (declared in the seed, see §4):
1. `host, port, stop = start_mock_llm()` **before** launching the SUT.
2. Add to `extra_env` (survives scrub):
   `LLM_HOST=127.0.0.1`, `LLM_PORT=<port>`, `LLM_BASE_URL=http://127.0.0.1:<port>/v1`,
   `OPENAI_API_KEY=sk-mock`, `LLM_MODEL=mock`.
3. `run_service_sandboxed(...)` as today (loopback-allowed); the SUT dials the sidecar on loopback.
4. `finally: stop()` — tear the sidecar down with the cell (mirror the SUT process-group kill).

### 3.3 Behavioral suite — `product_reviews_suite.py`
- Loopback gRPC client → SUT. Assert `AskProductAIAssistant` returns a non-empty response that
  **contains the mock marker** (proves the SUT correctly: built the OpenAI client against
  `LLM_BASE_URL`, made the call, parsed the completion). That is the real capability under test —
  *wiring an LLM-calling RPC against a contract*, not LLM quality.
- Optional negative: with `mode="rate_limit"`, assert the SUT surfaces the rate-limit path rather than
  crashing.

## 4. Seed flag
Add an optional `needs_llm_mock: true` to the seed `startup` block (additive; default false → today's
behavior unchanged). `run_behavioral_cell` starts the sidecar + injects env only when set. Keeps every
other service's path byte-identical.

## 5. Security posture (addresses "relax carefully because the code is well-known")

- **No egress relaxation — and that's deliberate.** The untrusted entity is the **model's output**,
  not the OTel target app: a model asked to reproduce product-reviews can still emit hallucinated or
  (under contamination/adversarial probing) exfiltrating code. Egress-denied is exactly what keeps the
  benchmark honest and the contamination firewall meaningful. The sidecar needs only loopback, which is
  already permitted, so we change nothing about the network controls.
- **Secrets stay scrubbed.** We inject a **dummy** `OPENAI_API_KEY=sk-mock`; `scrub_env` still strips
  every real key first.
- **Where "known corpus" *does* justify careful relaxation (network untouched):**
  - **Per-runtime rlimits.** Uniform `setrlimit` caps make JVM (`ad`) / .NET (`cart`) cells risk a
    false `degrade` (address-space/process limits sized for a Python leaf). A per-language rlimit
    profile is a bounded, defensible relaxation that never opens the network. *(Separate small change;
    flagged here, not built by this spec.)*
  - **Dependency allowlisting.** Known corpora have pinned deps (go.sum / package-lock / requirements);
    provisioning is already pre-sandbox — could tighten to an allowlist rather than ever opening egress.

## 6. Open questions

- **OQ-ML-1 — the DB dependency.** product-reviews also needs a database for `GetProductReviews` /
  `GetAverageProductReviewScore`. That's a *second* downstream the sidecar here does NOT cover. Options:
  in-memory SQLite shim (if the generated code is DB-agnostic), a loopback Postgres sidecar (heavier),
  or scope behavioral to `AskProductAIAssistant` only and keep the DB-backed RPCs structural-only. v1:
  LLM sidecar only; DB is its own follow-on.
- **OQ-ML-2 — tool-call fidelity.** The service defines an OpenAI *tool*; decide whether the mock must
  return a tool-call shape or a plain message suffices for the suite's assertion.
- **OQ-ML-3 — determinism vs realism.** The canned response is fully deterministic (good for scoring,
  FR-J6b-style). Confirm the suite asserts *wiring*, not content quality.

## 7. Effort
stdlib mock server ~40 LOC · `run_behavioral_cell` wiring ~30 LOC · suite ~40 LOC · seed flag ~5 LOC.
**~½ session, zero new dependencies, zero sandbox-network change.** Fully offline-testable (mock the
SUT, hit the sidecar directly).

---

*Draft 0.1 — sketch. The decisive finding: the loopback sidecar fits entirely within the existing
egress-denied/loopback-allowed sandbox + post-scrub env injection, so behavioral coverage of an
LLM-calling RPC needs new *trusted* code, not weaker controls.*
