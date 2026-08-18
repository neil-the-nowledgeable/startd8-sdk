# Oracle-loop $0 dry-run against the email-py fixture — det-req spec

**Format:** det-req/0.1
**Grammar:** `a1` (locked) — one-shot `pytest …` + service `probe METHOD /path [body={json}] -> STATUS`
**Target app:** `fixtures/otel-demo/email-py/` (an ALREADY-EXISTING `backend_codegen` FastAPI app)
**Purpose (OL-EB-1 phase 1):** a **$0 oracle-rung dry-run** — validate the deploy→boot→probe path
against a real backend_codegen FastAPI app **without spending a cent on Prime**. This spec is NOT
generated-from; it is **checked-against**, to prove `run_oracle` / the ORACLE rung works end-to-end.

> Every `Verify:` clause below targets a **real route** that exists in
> `fixtures/otel-demo/email-py/app/{health.py,routers.py}` (confirmed against `ROUTE_MANIFEST` in
> `app/openapi_contract.py`). Because the app is real and pre-built, the runnable set should reach
> near-total pass, exercising the coverage / no_fitness / floor machinery on a known-good backend.

## Objectives

- **O-1 — Deploy/boot path proven.** The harness can boot the real FastAPI app and drive its routes.
- **O-2 — Grammar/runner proven.** Both a1 forms (one-shot pytest + service probe) execute and grade.
- **O-3 — Residue path proven.** A prose-only FR lands in the human-gate residue, not the fitness.

## Functional requirements

- **FR-1 — Readiness route answers.** Name: the running app answers a readiness probe with 200. Touches: fixtures/otel-demo/email-py/app/health.py. Lives: code fixtures/otel-demo/email-py/app/health.py. Verify: probe `GET /health -> 200` — the bare readiness route returns ok when the DB answers. Serves: O-1
- **FR-2 — Liveness route answers.** Name: the running app answers a liveness probe with 200. Touches: fixtures/otel-demo/email-py/app/health.py. Lives: code fixtures/otel-demo/email-py/app/health.py. Verify: probe `GET /health/live -> 200` — the no-DB liveness route is live. Serves: O-1
- **FR-3 — Order-confirmation list route answers.** Name: the collection route returns 200 with a JSON list. Touches: fixtures/otel-demo/email-py/app/routers.py. Lives: code fixtures/otel-demo/email-py/app/routers.py. Verify: probe `GET /orderconfirmation/ -> 200` — the list endpoint is live over the booted fleet. Serves: O-1
- **FR-4 — Order-confirmation create route answers.** Name: posting an order confirmation returns 200 with the created row. Touches: fixtures/otel-demo/email-py/app/routers.py. Lives: code fixtures/otel-demo/email-py/app/routers.py. Verify: probe `POST /orderconfirmation/ body={"orderId":"ord-dryrun-1","email":"dryrun@example.com"} -> 200` — create persists a row and echoes it. Serves: O-1
- **FR-5 — Unknown row is a 404.** Name: fetching a missing item id returns 404 not 500. Touches: fixtures/otel-demo/email-py/app/routers.py. Lives: code fixtures/otel-demo/email-py/app/routers.py. Verify: probe `GET /orderconfirmation/does-not-exist -> 404` — a missing row is a clean not-found. Serves: O-2
- **FR-6 — Health test suite passes.** Name: the generated health test passes as a one-shot oracle. Touches: fixtures/otel-demo/email-py/tests/test_health.py. Lives: code fixtures/otel-demo/email-py/tests/test_health.py. Verify: `pytest tests/test_health.py -q` exits 0 proving the health function returns ok. Serves: O-2
- **FR-7 — Route manifest is documented.** Name: the app documents its route surface for reviewers. Touches: fixtures/otel-demo/email-py/app/openapi_contract.py. Lives: doc fixtures/otel-demo/email-py/app/openapi_contract.py. Verify: a reviewer can read ROUTE_MANIFEST and confirm it lists every wired route. Serves: O-3
