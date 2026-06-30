"""Golden end-to-end extraction over the fixture doc — every §2.x surface + the flags.

The fixture deliberately contains the contract's declared non-conformances (slash-row, unknown
type, `links X to nothing`, generator-gap settings) — the report must flag each, the manifests
must stay parser-clean (FR-WPI-4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from startd8.manifest_extraction import (
    Status,
    extract_manifests,
    report_to_json,
    report_to_markdown,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "manifest_extraction" / "kickoff.md"


@pytest.fixture(scope="module")
def result():
    return extract_manifests({"kickoff.md": FIXTURE.read_text(encoding="utf-8")})


def test_all_six_manifests_emitted(result) -> None:
    assert sorted(result.manifests) == [
        "ai_passes.yaml", "app.yaml", "completeness.yaml",
        "human_inputs.yaml", "pages.yaml", "views.yaml",
    ]


def test_round_trip_is_built_in(result) -> None:
    """FR-WPI-4: anything in result.manifests already survived its generator parser."""
    # Re-assert independently for the two strictest parsers.
    from startd8.backend_codegen.pages_generator import parse_pages
    from startd8.view_codegen.manifest import parse_views

    pages, nav = parse_pages(result.manifests["pages.yaml"])
    assert len(pages) == 3 and nav is not None
    views = parse_views(
        result.manifests["views.yaml"],
        known_entities=frozenset({"Profile", "Widget", "Tag", "WidgetTag"}),
    )
    assert len(views) == 5


def test_entities_and_relationships(result) -> None:
    rec = {r.value_path: r for r in result.records if r.manifest == "schema.prisma"}
    assert rec["/models/Profile"].status == Status.EXTRACTED
    # belongs-to + has-many extracted; symmetric links-to-many dedups to ONE join.
    joins = [p for p in rec if p.startswith("/joins/")]
    assert joins == ["/joins/WidgetTag"]
    # Declared non-conformances flagged:
    assert rec["/models/Widget/fields/in / out"].status == Status.NOT_EXTRACTED
    assert "one-field-per-row" in rec["/models/Widget/fields/in / out"].reason
    assert rec["/models/Widget/fields/blob"].status == Status.NOT_EXTRACTED
    nothing = [r for p, r in rec.items()
               if r.status == Status.NOT_EXTRACTED and "nothing" in (r.reason or "")]
    assert nothing, "links X to nothing (plain link) must flag as non-conforming"


def test_pages_unicode_and_annotations(result) -> None:
    data = yaml.safe_load(result.manifests["pages.yaml"])
    slugs = {p["slug"]: p for p in data["pages"]}
    assert "/resume" in slugs                       # F2: NFKD, not /r-sum
    assert slugs["/about"]["content"] == "pages/about.md"  # annotation stripped
    assert {n["label"] for n in data["nav"]} == {"Home", "Widgets", "Résumé"}


def test_views_all_five_kinds(result) -> None:
    data = yaml.safe_load(result.manifests["views.yaml"])
    by_name = {v["name"]: v for v in data["views"]}
    assert by_name["widget_wall"]["relations"] == [
        {"name": "WidgetTag", "from": "WidgetTag", "fk": "widgetId"}
    ]
    assert by_name["profile_dashboard"]["aggregates"][0] == {
        "name": "widgets_count", "of": "Widget", "fk": "profileId"
    }
    assert by_name["profile_workspace"]["route"] == "/profile/{id}"
    assert by_name["profile_export"]["route"] == "/profile/{id}/export"
    assert by_name["widget_board"]["group_by"] == "tier"
    assert by_name["widget_board"]["order"] == ["free", "pro"]


def test_view_panels_extracted_with_field_flagged(result) -> None:
    """VSP-G1 (D9): the `Panel:` line surfaces resolved Root fields; the unknown `ghostField` is
    flagged not_extracted and dropped (never guessed); the parenthetical on `score` is tolerated."""
    data = yaml.safe_load(result.manifests["views.yaml"])
    by_name = {v["name"]: v for v in data["views"]}
    assert by_name["widget_wall"]["panels"] == [
        {"name": "Details", "fields": ["title", "score"], "show_when": "any_set"}
    ]
    panel_flags = [r.reason for r in result.by_status(Status.NOT_EXTRACTED)
                   if r.manifest == "views.yaml" and "/panels/" in r.value_path]
    assert any("ghostField" in (x or "") and "never a guessed field" in (x or "")
               for x in panel_flags)


def test_views_generator_gaps_flagged(result) -> None:
    reasons = [r.reason for r in result.by_status(Status.NOT_EXTRACTED)
               if r.manifest == "views.yaml"]
    assert any("format-selection" in (x or "") for x in reasons)
    # workspace's prose Shows: flagged, not guessed
    assert any("neither the arrow nor the counts grammar" in (x or "") for x in reasons)
    # `Empty state:` is no longer a views.yaml generator-gap — it moved to view_prose.yaml (FR-VCE-2).
    assert not any("empty-state" in (x or "") for x in reasons)


def test_empty_state_routes_to_view_prose_not_a_dead_end(result) -> None:
    """FR-VCE-2: `Empty state:` is view-COPY, owned by view_prose.yaml. The fixture's `Widget Wall`
    is a ROW-scoped detail-compose (no `Scope: model`), so it has no no-rows surface → dropped
    off-archetype (back-compat), recorded under view_prose.yaml — not a views.yaml dead-end."""
    vp_reasons = [r.reason for r in result.by_status(Status.NOT_EXTRACTED)
                  if r.manifest == "view_prose.yaml"]
    assert any("no-rows surface" in (x or "") for x in vp_reasons)


def test_completeness_category_expansion_and_nudges(result) -> None:
    data = yaml.safe_load(result.manifests["completeness.yaml"])
    # D7: the author's nudge text is now carried into the per-entity manifest spec.
    assert data["entities"]["Widget"] == {"min_rows": 2, "weight": 2, "nudge": "Make more widgets."}
    assert data["entities"]["Tag"] == {"min_rows": 1}
    # "connection records" expands to the derived join models (F4/CRP R2 ordering).
    assert "WidgetTag" in data["exclude"] and "Profile" in data["exclude"]
    # D7: the nudge suffix is now EXTRACTED (was NOT_EXTRACTED(generator-gap)) — two rows per entry
    # (R2-G5), both extracted; the value is the author's message.
    nudge_rows = [r for r in result.by_status(Status.EXTRACTED)
                  if r.manifest == "completeness.yaml" and "/nudge" in r.value_path]
    assert len(nudge_rows) == 1  # only the Widget entry carries a nudge suffix
    assert nudge_rows[0].value == "Make more widgets."


def test_ai_passes_policy_and_derived_routes(result) -> None:
    data = yaml.safe_load(result.manifests["ai_passes.yaml"])
    by_name = {p["name"]: p for p in data["passes"]}
    assert by_name["draft_widget"]["output_entities"] == ["Widget"]   # "(except score)" stripped
    assert by_name["suggest_tags"]["input_entities"] == ["Widget"]
    assert "input_entities" not in by_name["draft_widget"]            # "pasted text" ⇒ text mode
    route_rows = [r for r in result.by_status(Status.DEFAULTED)
                  if r.manifest == "ai_passes.yaml" and r.value_path.endswith("/route_path")]
    assert len(route_rows) == 2  # routes derived, honestly flagged defaulted


def test_human_inputs_both_sources_merge(result) -> None:
    data = yaml.safe_load(result.manifests["human_inputs.yaml"])
    targets = {f["target"] for f in data["fields"]}
    assert targets == {"Widget.score", "Profile.rating"}  # field note + Only-humans line


def test_app_subset_rule(result) -> None:
    data = yaml.safe_load(result.manifests["app.yaml"])
    assert data["app"]["package"] == "demoapp"
    assert data["persistence"]["path"] == "./data/demo.db"
    # D8: port + env keys now have AppManifest homes (app.port / app.env_keys).
    assert data["app"]["port"] == 8099
    assert data["app"]["env_keys"] == [{"name": "ANTHROPIC_API_KEY", "qualifier": "optional"}]
    # `sqlite mode` remains the sole §2.7 generator-gap (app-code concern, not scaffold plumbing).
    gap_rows = [r for r in result.by_status(Status.NOT_EXTRACTED)
                if r.manifest == "app.yaml" and "generator-gap" in (r.reason or "")]
    assert {r.value_path for r in gap_rows} == {"/sqlite_mode"}


def test_report_byte_stable_and_sorted(result) -> None:
    """FR-WPI-3 (CRP R1): identity-sorted, byte-stable across identical-input runs."""
    again = extract_manifests({"kickoff.md": FIXTURE.read_text(encoding="utf-8")})
    assert report_to_json(result) == report_to_json(again)
    body = json.loads(report_to_json(result))
    identities = [(r["manifest"], r["value_path"]) for r in body["records"]]
    assert identities == sorted(identities)
    assert "kickoff.md" in body["source_docs"]
    report_to_markdown(result)  # renders without error


def test_diff_mode_against_live_contract() -> None:
    live = (
        "model Profile {\n  id String @id\n  name String\n  bio String?\n"
        "  yearsExp Int?\n  rating Float?\n  joined DateTime?\n  active Boolean?\n  tier String?\n}\n"
        "model Widget {\n  id String @id\n  title String\n  score Int?\n  profileId String\n}\n"
        "model Tag {\n  id String @id\n  label String\n}\n"
        "model WidgetTag {\n  widgetId String\n  tagId String\n  @@id([widgetId, tagId])\n}\n"
    )
    result = extract_manifests(
        {"kickoff.md": FIXTURE.read_text(encoding="utf-8")}, live_schema_text=live
    )
    assert result.contract_diff == []  # doc ↔ live agree
    # Now remove Tag from the live contract — drift must surface.
    drifted = extract_manifests(
        {"kickoff.md": FIXTURE.read_text(encoding="utf-8")},
        live_schema_text=live.replace("model Tag {\n  id String @id\n  label String\n}\n", ""),
    )
    assert any("Tag" in d for d in drifted.contract_diff)
