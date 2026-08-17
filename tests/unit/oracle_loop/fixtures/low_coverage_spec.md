# Low-coverage fixture spec — 1 runnable + 3 prose FRs (coverage 0.25)

**Format:** det-req/0.1

## Functional requirements

- **FR-1 — Health check passes.** Name: the app health function returns ok. Touches: app/main.py. Lives: code app/main.py. Verify: `pytest tests/test_health.py -q` exits 0 proving the health function returns ok. Serves: O-1
- **FR-2 — Design A.** Name: design constraint A holds. Touches: app/main.py. Lives: doc app/main.py. Verify: a reviewer confirms design constraint A. Serves: O-1
- **FR-3 — Design B.** Name: design constraint B holds. Touches: app/main.py. Lives: doc app/main.py. Verify: a reviewer confirms design constraint B. Serves: O-1
- **FR-4 — Design C.** Name: design constraint C holds. Touches: app/main.py. Lives: doc app/main.py. Verify: a reviewer confirms design constraint C. Serves: O-1
