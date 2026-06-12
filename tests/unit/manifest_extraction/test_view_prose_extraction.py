"""FR-VCE-1/2/3 — view COPY in a requirements doc is deterministically compiled to view_prose.yaml.

Closes the kickoff→manifest loop for the words layer: the consumer (`parse_view_prose`) shipped; this
adds the producer (`extract_view_prose`). Pins:
- `Title:`/`Intro:` extract on any HTML view (FR-VCE-1);
- `Empty state:` routes to `empty:` ONLY for a model-scoped detail-compose (`Scope: model`), the only
  archetype with a no-rows surface — and is silently dropped (back-compat) elsewhere (FR-VCE-2/F6);
- the emitted manifest round-trips through `parse_view_prose` keyed by VIEW names from the views
  candidate (not model names — CRP R1-F5), so a copy block on a non-existent view fails ingestion.
"""

from __future__ import annotations

import yaml

from startd8.manifest_extraction import Status, extract_manifests

_DOC = """
## Entities

### Widget

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |

## Views

### View: Value Map
- Kind: detail-compose
- Root: Widget
- Scope: model
- Title: Your value map
- Intro: How your widgets connect.
- Empty state: No widgets yet — add one to begin.

### View: Widget Board
- Kind: board
- Root: Widget
- Group by: name
- Title: Board of widgets
- Empty state: nothing on the board
""".strip()


def _result():
    return extract_manifests({"reqs.md": _DOC})


def test_view_prose_manifest_is_emitted_and_round_trips():
    # If the emitted view_prose.yaml failed parse_view_prose, extract_manifests would raise.
    res = _result()
    assert "view_prose.yaml" in res.manifests
    vp = yaml.safe_load(res.manifests["view_prose.yaml"])
    assert set(vp) == {"value_map", "widget_board"}


def test_title_and_intro_extract_on_any_view():
    vp = yaml.safe_load(_result().manifests["view_prose.yaml"])
    assert vp["value_map"]["title"] == "Your value map"
    assert vp["value_map"]["intro"] == "How your widgets connect."
    assert vp["widget_board"]["title"] == "Board of widgets"


def test_empty_extracts_only_for_model_scoped_detail_compose():
    vp = yaml.safe_load(_result().manifests["view_prose.yaml"])
    # model-scoped detail-compose → empty: extracted
    assert vp["value_map"]["empty"] == "No widgets yet — add one to begin."
    # board → empty silently dropped (no no-rows surface); title still extracted
    assert "empty" not in vp["widget_board"]


def test_off_archetype_empty_is_recorded_dropped_not_a_dead_end():
    res = _result()
    vp_dropped = [
        r for r in res.by_status(Status.NOT_EXTRACTED)
        if r.manifest == "view_prose.yaml" and "no-rows surface" in (r.reason or "")
    ]
    assert vp_dropped, "the board's Empty state should be recorded as an off-archetype drop"


def test_scope_model_is_emitted_into_views_manifest():
    """The `Scope: model` that unblocks `empty` also reaches views.yaml (the Value Map is whole-model)."""
    views = yaml.safe_load(_result().manifests["views.yaml"])
    value_map = next(v for v in views["views"] if v["name"] == "value_map")
    assert value_map.get("scope") == "model"
    board = next(v for v in views["views"] if v["name"] == "widget_board")
    assert board.get("scope") is None  # row-scoped (default) — no scope key emitted


# --------------------------------------------------------------------------- #
# Expanded vocabulary: import-flow + computed-panel are now authorable, and
# their success/error/controls copy extracts (the remaining copy keys).
# --------------------------------------------------------------------------- #

_CONTRACT_DOC = """
## Entities

### Widget

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |

## Views

### View: Restore
- Kind: import-flow
- Route: /import
- Title: "Restore from a backup"
- Success: "Restored {imported} items ({total} total)."
- Error: "Could not read that export: {errors}"
- Controls: validate = "Check this file", restore = "Restore my data", bogus = "x"

### View: Completeness
- Kind: computed-panel
- Compute: completeness
- Title: "How complete is your value model?"
""".strip()


def _contract():
    return extract_manifests({"reqs.md": _CONTRACT_DOC})


def test_import_flow_and_computed_panel_are_authorable():
    views = {v["name"]: v for v in yaml.safe_load(_contract().manifests["views.yaml"])["views"]}
    assert views["restore"]["kind"] == "import-flow" and views["restore"]["route"] == "/import"
    assert views["completeness"]["kind"] == "computed-panel"
    assert views["completeness"]["compute"] == "completeness"


def test_quotes_are_stripped_from_copy():
    vp = yaml.safe_load(_contract().manifests["view_prose.yaml"])
    assert vp["restore"]["title"] == "Restore from a backup"   # no surrounding quotes


def test_import_flow_success_error_extract():
    vp = yaml.safe_load(_contract().manifests["view_prose.yaml"])
    assert vp["restore"]["success"] == "Restored {imported} items ({total} total)."
    assert vp["restore"]["error"].startswith("Could not read")


def test_import_flow_controls_extract_and_filter_unknown_ids():
    vp = yaml.safe_load(_contract().manifests["view_prose.yaml"])
    assert vp["restore"]["controls"] == {"validate": "Check this file", "restore": "Restore my data"}
    # `bogus` is not a valid import-flow control-id → dropped, not emitted
    assert "bogus" not in vp["restore"]["controls"]


def test_computed_panel_gets_title_only_no_outcome_keys():
    vp = yaml.safe_load(_contract().manifests["view_prose.yaml"])
    assert vp["completeness"] == {"title": "How complete is your value model?"}


def test_success_on_non_import_flow_is_dropped():
    doc = _CONTRACT_DOC + '\n- Success: "should not apply"\n'  # appended to the computed-panel block
    res = extract_manifests({"reqs.md": doc})
    vp = yaml.safe_load(res.manifests["view_prose.yaml"])
    assert "success" not in vp.get("completeness", {})


def test_unknown_compute_binding_drops_the_panel():
    doc = _CONTRACT_DOC.replace("Compute: completeness", "Compute: bogus_binding")
    res = extract_manifests({"reqs.md": doc})
    views = {v["name"]: v for v in yaml.safe_load(res.manifests["views.yaml"])["views"]}
    assert "completeness" not in views  # dropped: unknown binding
    reasons = [r.reason for r in res.by_status(Status.NOT_EXTRACTED) if r.manifest == "views.yaml"]
    assert any("not a registered binding" in (x or "") for x in reasons)
