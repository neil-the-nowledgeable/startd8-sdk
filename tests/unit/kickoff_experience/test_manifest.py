"""M3 — kickoff experience config + linter."""

from __future__ import annotations

from startd8.kickoff_experience.manifest import (
    FieldDef,
    KickoffExperienceConfig,
    StepDef,
    WriteTarget,
    default_config,
    lint_config,
)


def test_default_config_lints_clean() -> None:
    issues = lint_config(default_config())
    assert issues == [], f"seeded config should lint clean, got: {issues}"


def test_default_config_has_steps_for_each_domain() -> None:
    cfg = default_config()
    step_keys = {s.key for s in cfg.steps}
    assert {"conventions", "build-preferences", "business-targets", "observability"} <= step_keys


def test_value_paths_are_unique() -> None:
    cfg = default_config()
    paths = [f.value_path for f in cfg.iter_fields()]
    assert len(paths) == len(set(paths))


def test_allow_lists_cover_writable_fields() -> None:
    cfg = default_config()
    writable = cfg.writable_fields()
    assert writable
    assert cfg.allowed_value_paths() == frozenset(f.value_path for f in writable)
    assert cfg.allowed_write_targets() == frozenset(
        f.write_target.as_tuple() for f in writable
    )


def test_field_by_value_path_round_trips() -> None:
    cfg = default_config()
    f = next(cfg.iter_fields())
    assert cfg.field_by_value_path(f.value_path) is f
    assert cfg.field_by_value_path("nonexistent.yaml#/nope") is None


# --- linter catches the failure classes R3-S2 names --------------------------------------------


def _cfg(*fields: FieldDef) -> KickoffExperienceConfig:
    return KickoffExperienceConfig(steps=(StepDef("s", "S", "intro", tuple(fields)),))


def test_lint_flags_duplicate_value_path() -> None:
    a = FieldDef("a", "A", "text", "conventions.yaml#/x", "help", "authored",
                 write_target=WriteTarget("conventions.yaml", "x"))
    b = FieldDef("b", "B", "text", "conventions.yaml#/x", "help", "authored",
                 write_target=WriteTarget("conventions.yaml", "x"))
    codes = {i.code for i in lint_config(_cfg(a, b))}
    assert "duplicate_value_path" in codes


def test_lint_flags_required_unwritable() -> None:
    f = FieldDef("a", "A", "text", "conventions.yaml#/x", "help", "authored", required=True)
    codes = {i.code for i in lint_config(_cfg(f))}
    assert "required_unwritable" in codes


def test_lint_flags_unknown_write_file_and_unsafe_key() -> None:
    f = FieldDef(
        "a", "A", "text", "evil.yaml#/x", "help", "authored",
        write_target=WriteTarget("evil.yaml", "../../etc/passwd"),
    )
    codes = {i.code for i in lint_config(_cfg(f))}
    assert "unknown_write_file" in codes
    assert "unsafe_write_key" in codes


def test_lint_flags_bad_widget_missing_choices_and_help() -> None:
    f = FieldDef("a", "A", "select", "conventions.yaml#/x", "  ", "authored",
                 write_target=WriteTarget("conventions.yaml", "x"))  # bad: no choices, blank help
    codes = {i.code for i in lint_config(_cfg(f))}
    assert "missing_choices" in codes
    assert "missing_help" in codes


def test_lint_flags_bad_provenance() -> None:
    f = FieldDef("a", "A", "text", "conventions.yaml#/x", "help", "made-up",
                 write_target=WriteTarget("conventions.yaml", "x"))
    codes = {i.code for i in lint_config(_cfg(f))}
    assert "bad_provenance" in codes
