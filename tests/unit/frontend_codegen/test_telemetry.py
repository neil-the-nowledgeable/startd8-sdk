"""NFR-6 — telemetry: deterministic render stats + no-op-safe OTel emission.

Emission must never raise (and must no-op when OTel is unconfigured, as in CI). The render
stats are deterministic counts that don't affect the rendered text.
"""

from __future__ import annotations

import pytest

from startd8.frontend_codegen import (
    record_drift_check,
    record_render,
    render_zod_schema,
)

pytestmark = pytest.mark.unit


def test_render_result_stats_are_deterministic_counts():
    schema = (
        "enum E { A B }\n"
        "model M {\n"
        "  id String @id\n"
        "  n Int\n"
        "  email String?\n"
        "  url String?\n"
        "}"
    )
    r = render_zod_schema(schema)
    assert r.models_rendered == 1  # the enum is not a model
    assert r.fields_rendered == 4  # id, n, email, url
    assert r.format_hints_applied == 2  # .email() + .url()
    # stats don't change the text, and are stable across renders
    r2 = render_zod_schema(schema)
    assert (r.models_rendered, r.fields_rendered, r.format_hints_applied) == (
        r2.models_rendered,
        r2.fields_rendered,
        r2.format_hints_applied,
    )


def test_record_render_never_raises():
    # No OTel provider configured in unit tests → must be a clean no-op.
    r = render_zod_schema("model M {\n  id String @id\n}")
    record_render(r)  # must not raise
    record_render(r)  # idempotent / repeatable


def test_record_drift_check_never_raises():
    for status in ("in_sync", "stale", "tampered", "missing"):
        record_drift_check(status)  # must not raise
