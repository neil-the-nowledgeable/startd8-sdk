# Tiny Todo/Cart API — OL-EB-1 oracle-loop pilot spec (generated-from)

**Format:** det-req/0.1
**Grammar:** `a1` (locked) — one-shot `pytest …` + service `probe METHOD /path [body={json}] -> STATUS`
**Role:** the **generated-from** target for OL-EB-1 — the FIRST real-LLM validation of
`startd8 build-to-spec`. Prime GENERATES this app; the ORACLE rung grades it against these clauses;
on failure the loop regenerates-with-feedback. Kept deliberately **small + cheap** to generate+boot.

> **Design intent — prove convergence, not a lucky one-shot.** FR-5 (checkout total) is deliberately
> **under-specified/ambitious** relative to the bare CRUD the rest of the spec implies: it demands a
> *computed* `total` field over cart items via a route that isn't a plain CRUD projection. A cheap
> model's iteration-1 draft is expected to plausibly MISS it (wrong field, 422, or 500) → the ORACLE
> rung fails FR-5 → `build_feedback` renders its intent+probe+observed/expected → Prime re-develops
> that feature (`process_feature`, GENERATED + `error_message`). Convergence across iterations — not a
> first-pass green — is the pilot's evidence that the regenerate-with-feedback wire fires (FR-4).

> **Grammar discipline:** only `pytest` one-shots and `probe` service clauses are used — **no
> console-scripts** (the OL-EB-3 venv-bin caveat: a bare console-script token needs runner-side
> venv-bin resolution the pilot deliberately avoids). One prose FR (FR-7) exercises the FR-6
> residue/coverage report. Runnable coverage is **6/7 ≈ 0.86** (5 service probes + 1 pytest one-shot;
> classification confirmed via `oracle_loop.grammar.parse_verify_clause`) — set `--min-coverage 0.6`
> to stay well above the floor while still proving the floor gate is wired.

## Objectives

- **O-1 — Items CRUD works.** A todo/cart item can be created, listed, fetched, and deleted over HTTP.
- **O-2 — Checkout computes a real total.** The cart checkout returns a *computed* total, not a stored field.
- **O-3 — Reviewable design.** The app carries human-readable intent a reviewer gates (residue).

## Functional requirements

- **FR-1 — App boots and is ready.** Name: the running app answers a readiness probe with 200. Touches: app/health.py. Lives: code app/health.py. Verify: probe `GET /health -> 200` — the app boots and the readiness route returns ok. Serves: O-1
- **FR-2 — Create a cart item.** Name: posting a cart item returns 200 with the created row. Touches: app/routers.py. Lives: code app/routers.py. Verify: probe `POST /item/ body={"name":"widget","qty":2,"price":300} -> 200` — create persists the item and echoes it. Serves: O-1
- **FR-3 — List cart items.** Name: the collection route returns 200 with a JSON list of items. Touches: app/routers.py. Lives: code app/routers.py. Verify: probe `GET /item/ -> 200` — the list endpoint returns the current items. Serves: O-1
- **FR-4 — CRUD suite passes as a one-shot.** Name: the generated CRUD test proves create/list/get/delete round-trip. Touches: app/tests/test_item_crud.py. Lives: code app/tests/test_item_crud.py. Verify: `pytest tests/test_item_crud.py -q` exits 0 proving create→list→get→delete round-trips over the item resource. Serves: O-1
- **FR-5 — Checkout returns a computed total.** Name: the checkout route returns the summed price times quantity over all cart items. Touches: app/routers.py. Lives: code app/routers.py. Verify: probe `POST /checkout body={"items":[{"name":"widget","qty":2,"price":300},{"name":"bolt","qty":3,"price":100}]} -> 200` — checkout returns a JSON body whose computed `total` equals 900 (2*300 + 3*100), derived at request time, not a stored column. Serves: O-2
- **FR-6 — Empty cart checkout is a clean 400.** Name: checking out an empty cart is a validated client error not a 500. Touches: app/routers.py. Lives: code app/routers.py. Verify: probe `POST /checkout body={"items":[]} -> 400` — an empty cart returns a validation error, never an unhandled 500. Serves: O-2
- **FR-7 — Reviewable module intent.** Name: the router module carries a docstring describing the cart+checkout intent. Touches: app/routers.py. Lives: doc app/routers.py. Verify: a reviewer can read the router module docstring and confirm it describes the cart CRUD and the computed-total checkout. Serves: O-3
