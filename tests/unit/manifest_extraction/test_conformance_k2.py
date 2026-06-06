"""K2 conformance fixes: collision pre-flight, reserved-name guard, env-keys agreement."""

from __future__ import annotations

import pytest

from startd8.manifest_extraction import Status, extract_manifests

BASE_ENTITIES = """\
## Entities

### Profile
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |
"""


def _records(result, manifest, status=None):
    out = [r for r in result.records if r.manifest == manifest]
    if status:
        out = [r for r in out if r.status == status]
    return out


# ---------------------------------------------------------------- collisions (R1-G4-i)

def test_page_slug_collision_flags_both_never_roundtrip_error() -> None:
    doc = BASE_ENTITIES + """
## Pages

| Page | Purpose | Content file |
|------|---------|--------------|
| About Us | a | about.md |
| About-Us | b | about2.md |
| Home | c | home.md |
"""
    result = extract_manifests({"d.md": doc})  # must NOT raise (author error ≠ extraction bug)
    flags = [r for r in _records(result, "pages.yaml", Status.NOT_EXTRACTED)
             if "collision" in (r.reason or "")]
    assert len(flags) == 2  # BOTH colliding rows flagged
    import yaml

    pages = yaml.safe_load(result.manifests["pages.yaml"])["pages"]
    assert [p["slug"] for p in pages] == ["/"]  # survivors only — partial conformance


def test_view_ident_collision_flags_both() -> None:
    doc = BASE_ENTITIES + """
## Views

### View: Profile Wall
- Kind: dashboard
- Root: Profile
- Shows: counts of profiles per profile

### View: Profile-Wall
- Kind: dashboard
- Root: Profile
"""
    result = extract_manifests({"d.md": doc})
    flags = [r for r in _records(result, "views.yaml", Status.NOT_EXTRACTED)
             if "collision" in (r.reason or "")]
    assert flags and "profile_wall" in flags[0].value_path
    assert "views.yaml" not in result.manifests  # both excluded ⇒ nothing to emit


def test_view_route_override_collision_excludes_latter() -> None:
    doc = BASE_ENTITIES + """
## Views

### View: Alpha
- Kind: dashboard
- Root: Profile
- Route: /shared

### View: Beta
- Kind: dashboard
- Root: Profile
- Route: /shared
"""
    result = extract_manifests({"d.md": doc})
    import yaml

    views = yaml.safe_load(result.manifests["views.yaml"])["views"]
    assert [v["name"] for v in views] == ["alpha"]
    flags = [r for r in _records(result, "views.yaml", Status.NOT_EXTRACTED)
             if "route" in (r.reason or "") and "collision" in (r.reason or "")]
    assert flags and "'alpha'" in flags[0].reason


# ---------------------------------------------------------------- reserved names (R1-G4-iv)

def test_reserved_field_name_flags_at_extraction() -> None:
    doc = """\
## Entities

### Widget
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| title | text | yes | |
| metadata | text | no | the crash class |
| class | text | no | python keyword |
"""
    result = extract_manifests({"d.md": doc})
    reserved = [r for r in _records(result, "schema.prisma", Status.NOT_EXTRACTED)
                if "reserved name" in (r.reason or "")]
    assert {r.value_path for r in reserved} == {
        "/models/Widget/fields/metadata", "/models/Widget/fields/class",
    }
    assert "RESERVED_ATTRS" in reserved[0].reason  # cites the backend guard


# ---------------------------------------------------------------- env-keys agreement (§2.7)

SCAFFOLD_DOC = BASE_ENTITIES + """
## Scaffold & runtime

| Setting | Value | Plain meaning |
|---------|-------|---------------|
| package name | demo | |
| env keys | ANTHROPIC_API_KEY (optional) · COST_BUDGET_USD (default 10.00) | |
"""


@pytest.mark.parametrize(
    "pref_value, expect_flag",
    [("\"$10.00\"", False), ("\"$5.00\"", True), ("\"$<5.00>\"", False)],  # placeholder ⇒ skip
)
def test_env_keys_agreement_check(pref_value: str, expect_flag: bool) -> None:
    prefs = f"domain: build-preferences\nbudgets:\n  per_pipeline_run: {pref_value}\n"
    result = extract_manifests({"d.md": SCAFFOLD_DOC}, build_preferences_text=prefs)
    flags = [r for r in _records(result, "app.yaml", Status.NOT_EXTRACTED)
             if "two-surfaces-disagree" in (r.reason or "")]
    assert bool(flags) == expect_flag
    if expect_flag:
        assert flags[0].value_path == "/env_keys/COST_BUDGET_USD"


def test_env_keys_no_prefs_no_agreement_rows() -> None:
    result = extract_manifests({"d.md": SCAFFOLD_DOC})
    assert not [r for r in result.records if "two-surfaces" in (r.reason or "")]
    # The generator-gap flag itself is unchanged.
    assert [r for r in _records(result, "app.yaml", Status.NOT_EXTRACTED)
            if "generator-gap" in (r.reason or "")]
