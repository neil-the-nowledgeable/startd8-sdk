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

**Start here on `main`:** branch from `origin/main` for **P2** (bucket-3 integration) or **M5** (cross-repo contracts).

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

## Priority 2 — Bucket 3 integration wiring (Prime Contractor)

Role 3 v0.2 emits **artifacts**; it does not wire consumers into application logic. That is
**bucket 3 (integration)** — the one in-scope LLM pass per `CLAUDE.md`.

| Task | Notes |
|------|-------|
| Prime skip-hook recognition | Ensure `python-context-client`, `python-context-otel`, `python-tests-cross-context` kinds are documented in contractor prompts |
| Integration pass pattern | Replace in-process `app.tables` imports with `CatalogClient` (or equivalent) where `contexts.yaml` declares an outbound producer |
| Source-bound extraction | Thread `producer_id` + `contract-sha256` into integration provenance stamps (FR-SBE precedent) |
| Kaizen hints | Add cross-context drift failures to post-mortem root-cause mappings |

**Done when:** one cap-dev-pipe seed demonstrates a feature that calls an outbound context client
and passes cross-context smoke in the generated test suite.

---

## Priority 3 — Cross-repo contract story (M5)

v0.2 filters remote contracts through the **consumer's** Prisma schema (`filter_spec_for_client`).
That is correct for shared-entity modular monoliths but breaks when producer and consumer schemas
diverge.

| Open question | Lean resolution |
|---------------|-----------------|
| Remote contract without consumer entity overlap | Add `routes: all_json` + optional `schemas: explicit` list in `contexts.yaml`; or skip Prisma filter when `contract:` is pinned |
| Contract publish CI | Producer pipeline uploads `openapi/{id}.json` + `contract-sha256` as a versioned artifact |
| Consumer regen workflow | Document: pin hash → edit `contexts.yaml` contract path → `generate backend --check` |

**Done when:** requirements v0.3 closes cross-repo filter semantics and adds one integration test
with mismatched producer/consumer Prisma models.

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
git checkout -b feat/openapi-role3-integration  # Priority 2 (next)
# M4 fixture: ./scripts/openapi_role3_m4_smoke.sh
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
