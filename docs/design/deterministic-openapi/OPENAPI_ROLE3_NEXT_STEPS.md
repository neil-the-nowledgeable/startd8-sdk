# OpenAPI Role 3 — Suggested Next Steps

**Date:** 2026-06-19  
**Status:** Handoff after v0.2 ship to `main`  
**Shipped:** M0–M3 + M2b (OTel) + M2c (remote smoke) — merge `2d474bf2` + review fixes `a7bc68e6`  
**Paired docs:** `OPENAPI_ROLE3_REQUIREMENTS.md`, `OPENAPI_ROLE3_PLAN.md`

---

## What shipped (v0.2 recap)

| Milestone | Deliverable |
|-----------|-------------|
| M0 | `--export-openapi` conformance; producer promotion path |
| M1 | `prisma/contexts.yaml` → `clients/{id}_client.py` + triple-hash drift |
| M2 | Local cross-context smoke (`TestClient` shim + generated tests) |
| M2b | `clients/_context_otel.py` — CLIENT spans on outbound HTTP (OQ-5) |
| M2c | Deploy harness `context_smoke` stage + `STARTD8_CONTEXT_<ID>_BASE_URL` |
| M3 | `ASSEMBLY_INPUTS_TEMPLATE.md` v0.2 + wireframe `contexts` catalog key |
| **M4** | Two-app fixture + pytest + `scripts/openapi_role3_m4_smoke.sh` |

**Start here on `main`:** branch for **P4** (doc hygiene) — M5 cross-repo seam is shipped.

---

## Priority 1 — Prove the seam on a real two-app fixture (M4) ✅

**Shipped:** `docs/design/deterministic-openapi/fixtures/two-app-seam/` + `tests/unit/backend_codegen/test_openapi_role3_m4_fixture.py` + `scripts/openapi_role3_m4_smoke.sh`

```bash
./scripts/openapi_role3_m4_smoke.sh
```

**Goal:** End-to-end producer → export → consumer pin → smoke, outside unit tests.

1. **Producer app** — minimal Prisma schema + `startd8 generate backend`; run
   `startd8 generate backend --export-openapi openapi/catalog.json`.
2. **Consumer app** — `prisma/contexts.yaml` with `contract: openapi/catalog.json` (not `local: true`).
3. **Verify drift** — edit producer `OPENAPI_SPEC` → consumer `generate backend --check` reports
   `contract-sha256` stale.
4. **Remote smoke** — boot producer via deploy harness; set `STARTD8_CONTEXT_CATALOG_BASE_URL`;
   run consumer deploy ladder through `context_smoke` stage.

**Done when:** documented fixture under `examples/` or `docs/design/deterministic-openapi/fixtures/`
with a one-command smoke script and CI-friendly `$0` pytest entry.

---

## Priority 2 — Bucket 3 integration wiring (Prime Contractor) ✅

Role 3 v0.2 emits **artifacts**; bucket 3 wires consumers into application logic via Prime
Contractor prompt injection.

| Task | Status |
|------|--------|
| Prime skip-hook recognition | ✅ `context_integration` prompt documents `python-context-*` kinds |
| Integration pass pattern | ✅ `app/context_clients.py` factories + `collect_context_integration_prompt()` |
| Source-bound extraction | ✅ Provenance stamps in prompt (`producer_id`, `contract-sha256`) |
| Kaizen hints | ✅ `context_contract_stale`, `invented_outbound_client` in `CAUSE_TO_SUGGESTION` |

**Shipped:** `context_integration_renderer.py`, `contractors/context_integration.py`, spec/draft
P0/P1 injection, drift for `python-context-integration`, `tests/fixtures/openapi_role3/integration_seed.json`.

**Done when:** one cap-dev-pipe seed demonstrates a feature that calls an outbound context client
and passes cross-context smoke in the generated test suite — satisfied by M4 fixture + P2 pytest +
`integration_seed.json` pattern.

---

## Priority 3 — Cross-repo contract story (M5) ✅

v0.2 filtered remote contracts through the consumer Prisma schema. M5 adds **pinned-contract**
filtering for divergent schemas.

| Task | Status |
|------|--------|
| Pinned contract filter | ✅ `filter_spec_for_context` — producer paths without consumer entity overlap |
| `routes: all_json` + `schemas:` | ✅ Grammar + explicit schema allowlist |
| Contract publish CI | ✅ `scripts/openapi_role3_publish_contract.sh` |
| Consumer regen workflow | ✅ `fixtures/cross-repo-seam/README.md` |
| Mismatched-schema test | ✅ `test_openapi_role3_m5_cross_repo.py` + `scripts/openapi_role3_m5_smoke.sh` |

**Done when:** requirements v0.3 closes cross-repo filter semantics and adds one integration test
with mismatched producer/consumer Prisma models — **satisfied**.

**Start here on `main`:** **P4** (doc + hygiene) or deferred polyglot tracks.

---

## Priority 4 — Doc + hygiene (quick wins)

| Task | Owner |
|------|-------|
| Update `OPENAPI_LEVERAGE_ANALYSIS.md` §4 — Role 3 → ✅ shipped | SDK docs |
| Bump `OPENAPI_ROLE3_*` headers to **v0.2 shipped on main** | SDK docs |
| Remove merged `startd8-openapi-role1` worktree + local `feat/openapi-role3-context` branch | Operator |
| Add Role 3 row to capability index / `SDK_ARCHITECTURE` inter-context section | SDK docs |

---

## Deferred (explicit non-goals for v0.3)

- TypeScript / polyglot consumer emit
- gRPC/proto inter-context promotion (`ProtoStubProvider` track)
- Auth header / credential propagation in generated clients
- Service mesh / API gateway codegen
- Grafana dashboard for `io.startd8.context.*` spans (OTel landscape work is separate)

---

## Suggested branch strategy

```bash
# M5 cross-repo: ./scripts/openapi_role3_m5_smoke.sh
# M4 two-app: ./scripts/openapi_role3_m4_smoke.sh
```

**Unrelated open threads (do not branch from these for Role 3):**

- `feat/otel-python-rebuild-openapi` — OTel demo Python AST index spike (not Role 3)
- `feat/otel-demo-corpus` — Tier-0 OTel demo bring-up scripts (not Role 3)

---

## Test commands (regression guard)

```bash
pytest tests/unit/backend_codegen/test_context_*.py \
       tests/unit/backend_codegen/test_cross_context_smoke.py \
       tests/unit/deploy_harness/test_context_smoke*.py -q
```

---

*Handoff doc — session 2026-06-19 (OpenAPI Role 3 M0–M3 merge).*
