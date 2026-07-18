"""M-WV0 — the wireframe-visual view-model composer + form-field parser (FR-WV-2/3/5/6/9).

Guards the pure view-model that the M-WV1 HTML shell will embed:
  - the form ``detail`` parser round-trips the real ``plan._forms_section`` format and
    degrades-never-fabricates on anything else (FR-WV-9);
  - ``compose(plan)`` is deterministic (FR-WV-6), JSON-safe (M-WV1 embeds it), covers every
    section 1:1 (FR-WV-3), carries the inverted-pyramid summary (FR-WV-2) + narration (FR-WV-5),
    and attaches a structured mockup only where derivable.
"""

from __future__ import annotations

import json
from pathlib import Path

from startd8.wireframe import build_wireframe_plan, load_assembly_inputs
from startd8.wireframe.render import SCHEMA_VERSION
from startd8.wireframe_view import compose, parse_form_detail


def _plan(root: Path):
    return build_wireframe_plan(load_assembly_inputs(project_root=root), authoring=True)


# --- FR-WV-9: the form detail parser ------------------------------------------------------------

def test_parser_reads_shown_and_omitted_groups() -> None:
    got = parse_form_detail(
        "fields: name, email | omitted — server-managed: id, createdAt; owned: sourceDocumentId"
    )
    assert got == {
        "shown": ["name", "email"],
        "omitted": {"server_managed": ["id", "createdAt"], "owned": ["sourceDocumentId"]},
        "help": None,
        "on_create": None,
    }


def test_parser_handles_none_fields_and_metadata_segments() -> None:
    got = parse_form_detail("fields: (none) | omitted — server-managed: id | help: 2/3, intro | on_create: redirect")
    assert got["shown"] == []
    assert got["omitted"]["server_managed"] == ["id"]
    assert got["omitted"]["owned"] == []
    assert got["help"] == "2/3, intro"
    assert got["on_create"] == "redirect"


def test_parser_degrades_never_fabricates() -> None:
    # A non-form detail (pages/entities prose) must yield None — the renderer keeps the raw detail.
    assert parse_form_detail("auto-derived from the schema; --no-nav opts out") is None
    assert parse_form_detail("31 entities") is None
    assert parse_form_detail("") is None
    # A bare fields list with no omissions still parses, with empty omitted groups.
    assert parse_form_detail("fields: title") == {
        "shown": ["title"],
        "omitted": {"server_managed": [], "owned": []},
        "help": None,
        "on_create": None,
    }


# --- FR-WV-2/3/5/6: compose() -------------------------------------------------------------------

def test_compose_is_deterministic_and_json_safe(golden_root: Path) -> None:
    plan = _plan(golden_root)
    vm1 = compose(plan)
    vm2 = compose(plan)
    assert vm1 == vm2, "compose must be a pure function of the plan (FR-WV-6)"
    # M-WV1 embeds this as escape-first JSON — it MUST serialize with no custom encoder.
    assert json.loads(json.dumps(vm1)) == vm1
    assert vm1["schema_version"] == SCHEMA_VERSION


def test_compose_covers_every_section_and_carries_summary(golden_root: Path) -> None:
    plan = _plan(golden_root)
    vm = compose(plan)
    composed_keys = [s["key"] for s in vm["sections"]]
    assert composed_keys == [s.key for s in plan.sections], "outline maps 1:1 to plan.sections (FR-WV-3)"
    summary = vm["summary"]
    assert summary["counts"] and summary["shape"] and summary["readiness"]  # inverted-pyramid band
    assert summary["meta"] and isinstance(summary["meta"], list)            # tool-level what/why/how (FR-SV-13)
    assert summary["why"] and summary["do"]                                 # FR-DL-12 meaning (FR-WV-5)
    assert isinstance(summary["shape_data"], dict) and summary["shape_data"]  # figures behind the badges


def test_compose_attaches_form_mockups_only_where_derivable(golden_root: Path) -> None:
    vm = compose(_plan(golden_root))
    by_key = {s["key"]: s for s in vm["sections"]}

    forms = by_key["forms"]["items"]
    field_forms = [it for it in forms if it["detail"].startswith("fields:")]
    assert field_forms, "golden fixture should have at least one entity form"
    for it in field_forms:
        m = it["mockup"]
        assert m is not None and m["kind"] == "form"
        assert m["entity"] and "create/edit form" not in m["entity"]  # entity extracted from label
        assert isinstance(m["shown"], list)
        assert set(m["omitted"]) == {"server_managed", "owned"}

    # A non-form section (pages) must carry no fabricated mockup.
    for it in by_key["pages"]["items"]:
        assert it["mockup"] is None


# --- FR-AUD: the (role × fluency) audience abstraction ------------------------------------------

def test_default_audience_is_byte_identical_base(golden_root: Path) -> None:
    """The default (architect, intermediate) MUST resolve to base — no regression to today (FR-AUD-2)."""
    from startd8.wireframe.describe import describe, describe_summary

    plan = _plan(golden_root)
    for s in plan.sections:
        assert describe(s, plan) == describe(s, plan, role="architect", fluency="intermediate")
    assert describe_summary(plan) == describe_summary(plan, role="architect", fluency="intermediate")


def test_end_user_variant_overrides_where_authored_and_degrades_elsewhere(golden_root: Path) -> None:
    from startd8.wireframe.describe import describe

    plan = _plan(golden_root)
    by_key = {s.key: s for s in plan.sections}

    # 'entities' has an authored end_user variant — it must differ from base AND drop the jargon.
    ent_base = describe(by_key["entities"], plan)["what"]
    ent_eu = describe(by_key["entities"], plan, role="end_user", fluency="beginner")["what"]
    assert ent_eu != ent_base
    low = ent_eu.lower()
    for jargon in ("entity", "crud", "schema", "prisma", "foreign-key"):
        assert jargon not in low, f"end_user voice must avoid {jargon!r} (FR-AUD-C1)"

    # An un-authored role (no 'backend' variant exists yet) MUST degrade to base, not go blank (FR-AUD-1).
    ent_base_full = describe(by_key["entities"], plan)
    ent_backend = describe(by_key["entities"], plan, role="backend", fluency="intermediate")
    assert ent_backend == ent_base_full


def test_audience_changes_only_wording_not_shape(golden_root: Path) -> None:
    """Switching audience changes narration only — shape, items, statuses, mockups identical (FR-AUD-4)."""
    plan = _plan(golden_root)
    base = compose(plan)
    eu = compose(plan, role="end_user", fluency="beginner")

    assert base["audience"] == {"role": "architect", "fluency": "intermediate"}
    assert eu["audience"] == {"role": "end_user", "fluency": "beginner"}
    # strip narration, compare everything else
    def skeleton(vm):
        return {
            "sections": [
                {"key": s["key"], "status": s["status"],
                 "items": s["items"]}  # labels, statuses, mockups
                for s in vm["sections"]
            ],
            "summary_shape": vm["summary"]["shape_data"],
        }
    assert skeleton(base) == skeleton(eu)
    # but at least one section's narration DID change (the end_user voice is live)
    changed = [b["key"] for b, e in zip(base["sections"], eu["sections"])
               if b["narration"] != e["narration"]]
    assert "entities" in changed


def test_fluency_varies_depth_for_end_user_only(golden_root: Path) -> None:
    """FR-AUD fluency axis: end_user forms get terser→fuller across advanced/intermediate/beginner;
    the axis is authored for end_user ONLY — the architect role ignores fluency (degrades to base)."""
    from startd8.wireframe.describe import describe

    plan = _plan(golden_root)
    forms = next(s for s in plan.sections if s.key == "forms")
    adv = describe(forms, plan, role="end_user", fluency="advanced")["what"]
    std = describe(forms, plan, role="end_user", fluency="intermediate")["what"]
    beg = describe(forms, plan, role="end_user", fluency="beginner")["what"]
    assert adv != std != beg and adv != beg          # three distinct depths
    assert len(adv) < len(std) < len(beg)            # advanced tersest, beginner fullest

    # Fluency is end_user-only: the architect role is unaffected by fluency (byte-identical to base).
    arch_std = describe(forms, plan, role="architect", fluency="intermediate")
    arch_adv = describe(forms, plan, role="architect", fluency="advanced")
    assert arch_std == arch_adv

    # A section without a fluency variant (scaffold) degrades to its end_user standard at any depth.
    scaffold = next(s for s in plan.sections if s.key == "scaffold")
    assert (describe(scaffold, plan, role="end_user", fluency="advanced")
            == describe(scaffold, plan, role="end_user", fluency="intermediate"))


def test_end_user_carries_does_wont_need_and_title(golden_root: Path) -> None:
    """FR-AUD-C2 — the end_user voice adds WON'T + NEED + a friendly title; architect base has none."""
    from startd8.wireframe.describe import describe

    plan = _plan(golden_root)
    forms = next(s for s in plan.sections if s.key == "forms")
    base = describe(forms, plan)
    eu = describe(forms, plan, role="end_user", fluency="beginner")

    assert base["wont"] == "" and base["need"] == "" and base["title"] is None  # base = architect, unaffected
    assert eu["wont"] and eu["need"] and eu["title"]                            # framing + title authored
    for jargon in ("entity", "crud", "schema", "field"):
        assert jargon not in eu["title"].lower()


def test_compose_plain_summary_lines_are_jargon_free(golden_root: Path) -> None:
    """FR-AUD gap-3 — the band gets deterministic plain-language shape/status for the end user."""
    summary = compose(_plan(golden_root))["summary"]
    assert "tracked" in summary["plain_shape"] and "route" not in summary["plain_shape"].lower()
    assert summary["plain_status"]  # non-empty; reassures when clean, names gaps in plain words otherwise


def test_compose_preserves_raw_detail_and_narration(golden_root: Path) -> None:
    vm = compose(_plan(golden_root))
    entities = next(s for s in vm["sections"] if s["key"] == "entities")
    # narration is the authored descriptive.yaml record (FR-WV-5), reused not rewritten.
    assert entities["narration"] is not None and entities["narration"]["what"]
    # raw detail is always preserved (degrade target for unparseable mockups).
    for it in entities["items"]:
        assert "detail" in it
