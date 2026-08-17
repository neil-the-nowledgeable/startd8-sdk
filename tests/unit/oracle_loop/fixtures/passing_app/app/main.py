"""A tiny passing fixture app for the oracle-loop tests ($0, deterministic).

Deliberately dependency-light: a plain callable health endpoint so the fixture can be exercised
without a live FastAPI/uvicorn boot in unit tests (the sandbox boundary is patched).
"""


def health() -> dict:
    return {"status": "ok"}
