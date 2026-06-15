"""M2 unit tests for smoke.py — pure schema synthesis + resource selection (network-free)."""

from __future__ import annotations

import pytest

from startd8.deploy_harness import select_crud_resource, synthesize_body
from startd8.deploy_harness.smoke import _round_trip_ok

pytestmark = pytest.mark.unit


def _spec(
    item_schema: dict,
    *,
    path: str = "/items",
    with_get: bool = True,
    media: str = "application/json",
    extra_paths: dict | None = None,
) -> dict:
    post = {
        "requestBody": {
            "content": {media: {"schema": {"$ref": "#/components/schemas/X"}}}
        }
    }
    path_item = {"post": post}
    if with_get:
        path_item["get"] = {"responses": {"200": {}}}
    paths = {path: path_item}
    if extra_paths:
        paths.update(extra_paths)
    return {
        "openapi": "3.1.0",
        "paths": paths,
        "components": {"schemas": {"X": item_schema}},
    }


# --------------------------------------------------------------------------- synthesis (FR-9 R1-F4)


def test_synth_fills_only_required() -> None:
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}, "qty": {"type": "integer"}},
    }
    assert synthesize_body(schema, {}) == {"name": "sample"}


def test_synth_resolves_ref() -> None:
    spec = {
        "components": {
            "schemas": {
                "X": {
                    "type": "object",
                    "required": ["n"],
                    "properties": {"n": {"type": "integer"}},
                }
            }
        }
    }
    assert synthesize_body({"$ref": "#/components/schemas/X"}, spec) == {"n": 1}


def test_synth_enum_picks_first() -> None:
    schema = {
        "type": "object",
        "required": ["s"],
        "properties": {"s": {"type": "string", "enum": ["a", "b"]}},
    }
    assert synthesize_body(schema, {}) == {"s": "a"}


def test_synth_formats() -> None:
    schema = {
        "type": "object",
        "required": ["d", "u", "e"],
        "properties": {
            "d": {"type": "string", "format": "date-time"},
            "u": {"type": "string", "format": "uuid"},
            "e": {"type": "string", "format": "email"},
        },
    }
    out = synthesize_body(schema, {})
    assert out["d"].endswith("Z") and "-" in out["u"] and "@" in out["e"]


def test_synth_scalars_and_array() -> None:
    schema = {
        "type": "object",
        "required": ["i", "n", "b", "a"],
        "properties": {
            "i": {"type": "integer"},
            "n": {"type": "number"},
            "b": {"type": "boolean"},
            "a": {"type": "array", "items": {"type": "string"}},
        },
    }
    assert synthesize_body(schema, {}) == {"i": 1, "n": 1.0, "b": False, "a": []}


def test_synth_nullable_required_is_null_30_and_31() -> None:
    schema = {
        "type": "object",
        "required": ["a", "b"],
        "properties": {
            "a": {"type": "string", "nullable": True},  # 3.0
            "b": {"type": ["string", "null"]},
        },
    }  # 3.1
    assert synthesize_body(schema, {}) == {"a": None, "b": None}


def test_synth_allof_merge() -> None:
    spec = {
        "components": {
            "schemas": {
                "Base": {
                    "type": "object",
                    "required": ["a"],
                    "properties": {"a": {"type": "string"}},
                }
            }
        }
    }
    schema = {
        "allOf": [{"$ref": "#/components/schemas/Base"}],
        "required": ["b"],
        "properties": {"b": {"type": "integer"}},
    }
    assert synthesize_body(schema, spec) == {"a": "sample", "b": 1}


def test_synth_anyof_prefers_non_null_branch() -> None:
    schema = {
        "type": "object",
        "required": ["v"],
        "properties": {"v": {"anyOf": [{"type": "null"}, {"type": "integer"}]}},
    }
    assert synthesize_body(schema, {}) == {"v": 1}


def test_synth_nested_object() -> None:
    schema = {
        "type": "object",
        "required": ["meta"],
        "properties": {
            "meta": {
                "type": "object",
                "required": ["k"],
                "properties": {"k": {"type": "string"}},
            }
        },
    }
    assert synthesize_body(schema, {}) == {"meta": {"k": "sample"}}


def test_synth_default_wins() -> None:
    schema = {
        "type": "object",
        "required": ["x"],
        "properties": {"x": {"type": "string", "default": "preset"}},
    }
    assert synthesize_body(schema, {}) == {"x": "preset"}


# --------------------------------------------------------------------------- selection (FR-10 R1-F5)


def test_select_picks_fk_free_resource() -> None:
    spec = _spec(
        {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
    )
    choice, skip = select_crud_resource(spec)
    assert skip is None and choice.path == "/items"


def test_select_no_list_create() -> None:
    spec = _spec({"type": "object"}, with_get=False)
    choice, skip = select_crud_resource(spec)
    assert choice is None and skip == "skipped:no-list-create-resource"


def test_select_all_fk_coupled() -> None:
    spec = _spec(
        {
            "type": "object",
            "required": ["customer_id"],
            "properties": {"customer_id": {"type": "integer"}},
        }
    )
    choice, skip = select_crud_resource(spec)
    assert choice is None and skip == "skipped:all-resources-fk-coupled"


def test_select_ignores_non_json_form_route() -> None:
    spec = _spec({"type": "object"}, media="application/x-www-form-urlencoded")
    choice, skip = select_crud_resource(spec)
    assert choice is None and skip == "skipped:no-list-create-resource"


def test_select_ignores_path_param_collections() -> None:
    spec = _spec(
        {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        },
        path="/items/{id}",
    )
    choice, skip = select_crud_resource(spec)
    assert choice is None and skip == "skipped:no-list-create-resource"


def test_select_prefers_simplest_when_multiple_fk_free() -> None:
    simple = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "string"}},
    }
    complex_ = {
        "type": "object",
        "required": ["a", "b", "c"],
        "properties": {k: {"type": "string"} for k in "abc"},
    }
    spec = {
        "openapi": "3.1.0",
        "components": {"schemas": {"S": simple, "C": complex_}},
        "paths": {
            "/complex": {
                "get": {},
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/C"}
                            }
                        }
                    }
                },
            },
            "/simple": {
                "get": {},
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/S"}
                            }
                        }
                    }
                },
            },
        },
    }
    choice, _ = select_crud_resource(spec)
    assert choice.path == "/simple"


# --------------------------------------------------------------------------- round-trip


def test_round_trip_matches_created_id() -> None:
    assert _round_trip_ok({"id": 3}, [{"id": 1}, {"id": 3}])
    assert not _round_trip_ok({"id": 3}, [{"id": 1}])
    assert not _round_trip_ok({"id": 1}, [])  # empty list after create = failure


def test_round_trip_no_id_accepts_nonempty_list() -> None:
    assert _round_trip_ok({"ok": True}, [{"x": 1}])
    assert _round_trip_ok(None, {"items": [{"x": 1}]})  # wrapped list shape
