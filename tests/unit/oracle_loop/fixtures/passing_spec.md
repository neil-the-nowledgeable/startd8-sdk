# Passing fixture spec — oracle-loop $0 test

**Format:** det-req/0.1

## Functional requirements

- **FR-1 — Health check passes.** Name: the app health function returns ok. Touches: app/main.py. Lives: code app/main.py. Verify: `pytest tests/test_health.py -q` exits 0 proving the health function returns ok. Serves: O-1
- **FR-2 — Health route live.** Name: the running app answers a health probe with 200. Touches: app/main.py. Lives: code app/main.py. Verify: probe `GET /health -> 200` — the health endpoint is live. Serves: O-1
- **FR-3 — Documented design.** Name: the module carries a docstring describing intent. Touches: app/main.py. Lives: doc app/main.py. Verify: the module has a clear docstring a reviewer can read. Serves: O-2
