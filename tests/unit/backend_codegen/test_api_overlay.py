"""Unit tests for api.yaml overlay parse/merge/reconcile (OpenAPI Role 2 M0+M1)."""

from __future__ import annotations

import pytest

from startd8.backend_codegen import owned_file_in_sync
from startd8.backend_codegen.api_overlay_manifest import (
    ReconcileError,
    apply_api_overlay,
    merge_openapi_specs,
    parse_api_overlay,
    prepare_overlay_merge,
    reconcile_overlay,
)
from startd8.backend_codegen.openapi_contract_renderer import render_openapi_contract
from startd8.openapi_contract import select_crud_resource
from startd8.validators.openapi_spec_gate import extract_openapi_spec_from_text

pytestmark = pytest.mark.unit

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""

OVERLAY_WEBHOOK = """\
paths:
  /webhooks/stripe:
    post:
      summary: Stripe webhook
      responses:
        "200":
          description: OK
"""

OVERLAY_COLLISION = """\
paths:
  /note/:
    get:
      responses:
        "200":
          description: OK
"""


def _base_spec() -> dict:
    text = render_openapi_contract(SCHEMA)
    spec = extract_openapi_spec_from_text(text)
    assert spec is not None
    return spec


def test_parse_minimal_overlay() -> None:
    spec = parse_api_overlay(OVERLAY_WEBHOOK)
    assert spec["openapi"] == "3.0.3"
    assert "/webhooks/stripe" in spec["paths"]


def test_merge_adds_overlay_path() -> None:
    base = _base_spec()
    overlay = parse_api_overlay(OVERLAY_WEBHOOK)
    merged, warnings = apply_api_overlay(base, overlay, SCHEMA)
    assert not warnings
    assert "/webhooks/stripe" in merged["paths"]
    assert "/note/" in merged["paths"]


def test_base_path_validation_only_no_collision() -> None:
    base = _base_spec()
    overlay = parse_api_overlay(OVERLAY_COLLISION)
    warnings = reconcile_overlay(base, overlay, SCHEMA)
    assert not warnings
    plan = prepare_overlay_merge(base, overlay)
    assert "/note/" not in plan.additive["paths"]
    merged = merge_openapi_specs(base, plan.additive)
    assert merged["paths"] == base["paths"]


def test_base_path_extra_method_warns() -> None:
    base = _base_spec()
    overlay = parse_api_overlay(
        """\
paths:
  /note/:
    put:
      responses:
        "200":
          description: OK
"""
    )
    warnings = reconcile_overlay(base, overlay, SCHEMA)
    assert any("PUT /note/" in w for w in warnings)


def test_validation_only_manifest_path_warns_not_merged() -> None:
    base = _base_spec()
    overlay = parse_api_overlay(
        """\
paths:
  /ai/extract:
    x-startd8-validation-only: true
    post:
      responses:
        "200":
          description: OK
"""
    )
    warnings = reconcile_overlay(base, overlay, SCHEMA)
    assert any("validation-only" in w and "/ai/extract" in w for w in warnings)
    plan = prepare_overlay_merge(base, overlay)
    assert "/ai/extract" not in plan.additive["paths"]


def test_render_surfaces_validation_warnings() -> None:
    warnings: list[str] = []
    render_openapi_contract(
        SCHEMA,
        api_text="""\
paths:
  /ai/extract:
    x-startd8-validation-only: true
    post:
      responses:
        "200":
          description: OK
""",
        overlay_warnings=warnings,
    )
    assert warnings


def test_render_includes_overlay_route_in_manifest() -> None:
    text = render_openapi_contract(SCHEMA, api_text=OVERLAY_WEBHOOK)
    assert '"/webhooks/stripe"' in text
    assert '("POST", "/webhooks/stripe")' in text
    assert "# api-sha256:" in text


def test_absent_overlay_byte_identical_to_role1() -> None:
    assert render_openapi_contract(SCHEMA) == render_openapi_contract(SCHEMA, api_text=None)
    assert "# api-sha256:" not in render_openapi_contract(SCHEMA)


def test_overlay_drift_detects_api_edit() -> None:
    text = render_openapi_contract(SCHEMA, api_text=OVERLAY_WEBHOOK)
    assert owned_file_in_sync(SCHEMA, text, api_text=OVERLAY_WEBHOOK) is True
    edited = OVERLAY_WEBHOOK + "\n# touch\n"
    assert owned_file_in_sync(SCHEMA, text, api_text=edited) is False


def test_merged_spec_still_supports_smoke_selection() -> None:
    text = render_openapi_contract(SCHEMA, api_text=OVERLAY_WEBHOOK)
    spec = extract_openapi_spec_from_text(text)
    assert spec is not None
    choice, reason = select_crud_resource(spec)
    assert choice is not None, reason


def test_overlay_path_params_required() -> None:
    base = _base_spec()
    overlay = parse_api_overlay(
        """\
paths:
  /items/{item_id}/publish:
    post:
      responses:
        "200":
          description: OK
"""
    )
    with pytest.raises(ReconcileError, match="missing parameters"):
        reconcile_overlay(base, overlay, SCHEMA)


def test_overlay_prisma_dto_ref_allowed() -> None:
    base = _base_spec()
    overlay = parse_api_overlay(
        """\
paths:
  /notes/summary:
    get:
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NoteRead'
"""
    )
    reconcile_overlay(base, overlay, SCHEMA)
    merged, _ = apply_api_overlay(base, overlay, SCHEMA)
    assert "/notes/summary" in merged["paths"]


def test_merged_spec_passes_validator_when_installed() -> None:
    pytest.importorskip("openapi_spec_validator")
    from startd8.validators.openapi_spec_gate import validate_openapi_spec_dict

    text = render_openapi_contract(SCHEMA, api_text=OVERLAY_WEBHOOK)
    spec = extract_openapi_spec_from_text(text)
    assert spec is not None
    result = validate_openapi_spec_dict(spec)
    assert result.is_pass
