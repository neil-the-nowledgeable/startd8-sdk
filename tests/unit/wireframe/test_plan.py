"""Plan derivation tests: statuses (FR-W4), recoverability (R6-F1), composition (R6-F3),
degradation (FR-W13), readiness (R4-F2)."""

from __future__ import annotations

from pathlib import Path


from startd8.wireframe import Status, build_wireframe_plan, load_assembly_inputs


def _plan(root: Path, **kw):
    return build_wireframe_plan(load_assembly_inputs(project_root=root), **kw)


# --------------------------------------------------------------------------- #
# Per-manifest absence semantics (FR-W4 table)
# --------------------------------------------------------------------------- #

def test_absence_semantics_schema_only_project(mini_root: Path) -> None:
    plan = _plan(mini_root)
    assert plan.section("scaffold").status == Status.DEFAULTS          # app.yaml absent
    assert plan.section("services").status == Status.PLANNED          # schema planned
    assert plan.section("entities").status == Status.PLANNED
    assert plan.section("pages").status == Status.NOT_DEFINED
    assert plan.section("views").status == Status.NOT_DEFINED
    assert plan.section("completeness").status == Status.DEFAULTS
    # human_inputs absent → defaults participates in Forms worst-wins (FR-W4).
    assert plan.section("forms").status == Status.DEFAULTS


def test_absence_semantics_empty_project(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    assert plan.section("entities").status == Status.NOT_DEFINED
    assert plan.section("services").status == Status.NOT_DEFINED
    assert plan.section("forms").status == Status.NOT_DEFINED
    assert "no contract" in plan.section("entities").consequence
    assert plan.readiness["backend"] == "blocked(missing schema.prisma)"


def test_defaults_consequences_rendered(mini_root: Path) -> None:
    """FR-W5: consequence lines in app-shape terms."""
    plan = _plan(mini_root)
    assert "default scaffold" in plan.section("scaffold").consequence
    assert "presence-rule fallback" in plan.section("completeness").consequence
    # R3-F5: defaults completeness enumerates the presence-rule signals.
    labels = [i.label for i in plan.section("completeness").items]
    assert "signal: Profile" in labels


# --------------------------------------------------------------------------- #
# Schema recoverability (R6-F1) — the lenient-parser tripwire
# --------------------------------------------------------------------------- #

def test_garbled_schema_is_invalid_not_placeholder(tmp_path: Path) -> None:
    root = tmp_path / "p"
    (root / "prisma").mkdir(parents=True)
    # Two declared models; A's missing close-brace swallows B → parsed < declared.
    # (Empirically verified: the lenient parser recovers an unclosed *last* block, but a
    # nested-unclosed *first* block drops the inner declaration.)
    (root / "prisma" / "schema.prisma").write_text(
        "model A {\n  id String @id\nmodel B {\n  name String\n}\n", encoding="utf-8"
    )
    plan = _plan(root)
    section = plan.section("entities")
    assert section.status == Status.INVALID
    assert "lenient parse dropped" in section.error
    assert plan.readiness["backend"] == "blocked(invalid schema.prisma)"
    # The views known_entities degradation also keys off the schema (FR-W13).
    assert plan.section("services").status == Status.INVALID


def test_zero_model_schema_is_placeholder_only_when_nothing_dropped(tmp_path: Path) -> None:
    root = tmp_path / "p"
    (root / "prisma").mkdir(parents=True)
    (root / "prisma" / "schema.prisma").write_text(
        "// scaffolded stub — no models yet\n", encoding="utf-8"
    )
    plan = _plan(root)
    assert plan.section("entities").status == Status.PLACEHOLDER
    assert plan.readiness["backend"] == "blocked(placeholder schema.prisma (no models))"


# --------------------------------------------------------------------------- #
# Worst-wins composition (R6-F3) + Services degradation (R2-S3/R5-S6)
# --------------------------------------------------------------------------- #

def test_invalid_human_inputs_degrades_forms(mini_root: Path) -> None:
    (mini_root / "prisma" / "human_inputs.yaml").write_text(
        "fields:\n  - no_target_key: 1\n", encoding="utf-8"
    )
    plan = _plan(mini_root)
    assert plan.section("forms").status == Status.INVALID
    assert plan.section("entities").status == Status.PLANNED  # only Forms composes human_inputs


def test_invalid_ai_passes_degrades_services(mini_root: Path) -> None:
    (mini_root / "prisma" / "ai_passes.yaml").write_text("passes: []\n", encoding="utf-8")
    plan = _plan(mini_root)
    assert plan.section("services").status == Status.INVALID
    assert plan.readiness["backend"] == "blocked(invalid ai_passes.yaml)"


def test_absent_ai_passes_scopes_to_ai_items_not_section(mini_root: Path) -> None:
    """FR-W4 table: ai_passes absent → AI layer not_defined; core services stay planned."""
    plan = _plan(mini_root)
    section = plan.section("services")
    assert section.status == Status.PLANNED
    ai_items = [i for i in section.items if i.label == "AI layer"]
    assert ai_items and ai_items[0].status == Status.NOT_DEFINED


def test_services_never_planned_without_schema(tmp_path: Path) -> None:
    root = tmp_path / "p"
    (root / "prisma").mkdir(parents=True)
    plan = _plan(root)
    assert plan.section("services").status == Status.NOT_DEFINED
    assert not [i for i in plan.section("services").items if i.status == Status.PLANNED]


def test_invalid_views_manifest_degrades_views_only(golden_copy: Path) -> None:
    (golden_copy / "prisma" / "views.yaml").write_text(
        "views:\n  - {name: x, kind: nonsense, route: /x, root: Profile}\n", encoding="utf-8"
    )
    plan = _plan(golden_copy)
    assert plan.section("views").status == Status.INVALID
    assert "unknown kind" in plan.section("views").error
    assert plan.section("entities").status == Status.PLANNED
    assert plan.readiness["views"] == "blocked(invalid views.yaml)"


# --------------------------------------------------------------------------- #
# Sentinels, overrides, error capping (FR-W4/W6/W13)
# --------------------------------------------------------------------------- #

def test_sentinel_marks_placeholder(mini_root: Path) -> None:
    (mini_root / "app.yaml").write_text(
        "app:\n  name: REPLACE_WITH_PROJECT_NAME\n", encoding="utf-8"
    )
    plan = _plan(mini_root)
    assert plan.section("scaffold").status == Status.PLACEHOLDER


def test_status_override_applies_only_when_absent(mini_root: Path) -> None:
    """FR-W6/R2-F1: parser wins when the file exists; override labels the absent case."""
    inv = mini_root / "inputs.yaml"
    inv.write_text(
        "inputs:\n"
        "  pages: {path: prisma/pages.yaml, status: placeholder}\n"
        "  schema: {path: prisma/schema.prisma, status: absent}\n",
        encoding="utf-8",
    )
    inputs = load_assembly_inputs(yaml_paths=[inv], project_root=mini_root)
    plan = build_wireframe_plan(inputs)
    # pages file absent + override placeholder → placeholder (declared ahead of authoring).
    assert plan.section("pages").status == Status.PLACEHOLDER
    # schema file EXISTS: parser-derived planned wins over the `absent` override.
    assert plan.section("entities").status == Status.PLANNED


def test_error_text_capped_at_500(mini_root: Path) -> None:
    """FR-W13/R5-F2: bounded error surface + truncation flag."""
    long_key = "k" * 600
    (mini_root / "prisma" / "pages.yaml").write_text(
        f"pages:\n  - {{slug: /x, title: T, content: c.md, {long_key}: 1}}\n", encoding="utf-8"
    )
    plan = _plan(mini_root)
    section = plan.section("pages")
    assert section.status == Status.INVALID
    assert len(section.error) == 500
    assert section.error_truncated is True


def test_non_utf8_manifest_is_invalid_not_fatal(mini_root: Path) -> None:
    """R5-S2: a binary manifest degrades to `invalid`; the plan still builds."""
    (mini_root / "prisma" / "pages.yaml").write_bytes(b"\xff\xfe\x00garbled")
    plan = _plan(mini_root)
    assert plan.section("pages").status == Status.INVALID
    assert "not valid UTF-8" in plan.section("pages").error
    assert plan.section("entities").status == Status.PLANNED


# --------------------------------------------------------------------------- #
# Golden fixture: full shape + readiness + content inputs (FR-W15)
# --------------------------------------------------------------------------- #

def test_golden_fixture_full_shape(golden_root: Path) -> None:
    plan = _plan(golden_root, authoring=True)
    assert plan.shape == {
        "entities": 3, "crud_routes": 15, "pages": 2, "views": 1, "ai_passes": 1,
    }
    assert plan.readiness == {"scaffold": "ready", "backend": "ready", "views": "ready"}
    for key in ("scaffold", "services", "entities", "pages", "forms", "views"):
        assert plan.section(key).status == Status.PLANNED, key

    # FR-W15 content inputs: about.md planned, home.md missing, prompt file present.
    content = plan.section("content")
    by_label = {i.label: i.status for i in content.items}
    assert by_label["page body: app/pages/about.md"] == Status.PLANNED
    assert by_label["page body: app/pages/home.md"] == Status.NOT_DEFINED
    assert by_label["prompt: prompts/suggest_notes.md"] == Status.PLANNED
    assert content.status == Status.NOT_DEFINED  # worst of its items

    # Owned-field policy reaches the Forms detail (Metric.value — app FR-6).
    forms = plan.section("forms")
    metric = next(i for i in forms.items if i.label.startswith("Metric"))
    assert "owned: value" in metric.detail


def test_forms_section_surfaces_on_create(golden_copy: Path) -> None:
    """OQ-3: views.yaml's `forms:` section reaches the Forms detail + plans created.html."""
    views = golden_copy / "prisma" / "views.yaml"
    views.write_text(
        views.read_text(encoding="utf-8")
        + "forms:\n  Profile: { on_create: confirmation }\n",
        encoding="utf-8",
    )
    plan = _plan(golden_copy, authoring=True)
    forms = plan.section("forms")
    profile = next(i for i in forms.items if i.label.startswith("Profile"))
    assert "on_create: confirmation" in profile.detail
    assert "app/templates/profile/created.html" in profile.paths
    # undeclared entities stay at the default — no noise in their detail
    metric = next(i for i in forms.items if i.label.startswith("Metric"))
    assert "on_create" not in metric.detail
    # the views section itself is untouched by the sibling section
    assert plan.section("views").status == Status.PLANNED


def test_view_copy_coverage_surfaces_in_views_section(golden_copy: Path) -> None:
    """FR-WCI-1: the wireframe reports which views carry authored copy (view_prose.yaml) vs render
    raw machine names, keyed by VIEW name — completing the pre-gen readout for the words layer."""
    # No view_prose.yaml → every view reads "copy: raw"; the package summarizes 0/N.
    views = _plan(golden_copy).section("views")
    pkg = next(i for i in views.items if i.label == "views package")
    assert "view copy: 0/1 authored" in (pkg.detail or "")
    pd = next(i for i in views.items if i.label.startswith("profile_dashboard"))
    assert "copy: raw" in pd.detail

    # Author copy for the view → it flips to "authored" and the package summary updates.
    (golden_copy / "prisma" / "view_prose.yaml").write_text(
        'profile_dashboard:\n  title: "Your profile"\n', encoding="utf-8"
    )
    views2 = _plan(golden_copy).section("views")
    pkg2 = next(i for i in views2.items if i.label == "views package")
    assert "view copy: 1/1 authored" in (pkg2.detail or "")
    pd2 = next(i for i in views2.items if i.label.startswith("profile_dashboard"))
    assert "copy: authored" in pd2.detail


def test_merge_warnings_surface_in_plan(mini_root: Path) -> None:
    a = mini_root / "a.yaml"
    b = mini_root / "b.yaml"
    a.write_text("inputs:\n  views: {path: prisma/views.yaml}\n", encoding="utf-8")
    b.write_text("inputs:\n  views: {path: prisma/other-views.yaml}\n", encoding="utf-8")
    inputs = load_assembly_inputs(yaml_paths=[a, b], project_root=mini_root)
    plan = build_wireframe_plan(inputs)
    assert len(plan.merge_warnings) == 1
    assert plan.input_provenance["views"]["source"] == "yaml"
