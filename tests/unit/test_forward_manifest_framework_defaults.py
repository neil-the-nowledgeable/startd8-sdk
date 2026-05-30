"""Fix 2 (Forward Manifest at draft time) — framework-conventions registry.

Covers t-extractor-test cases (a)-(d) plus anchoring/version checks. LLM-free.
"""

from startd8.forward_manifest import ForwardElementSpec
from startd8.forward_manifest_extractor import (
    FRAMEWORK_CONFIG_REGISTRY_VERSION,
    _FRAMEWORK_CONFIG_DEFAULTS,
    apply_framework_defaults,
)
from startd8.utils.code_manifest import ElementKind


def test_a_empty_input_filled_for_matching_paths():
    fe = {"next.config.mjs": []}
    apply_framework_defaults(fe)
    assert fe["next.config.mjs"], "convention should fill empty list"
    el = fe["next.config.mjs"][0]
    # MULTILANG FR-4: JS/TS default-export configs now use DEFAULT_EXPORT (was CONSTANT).
    assert el.kind == ElementKind.DEFAULT_EXPORT
    assert el.name == "config"
    assert el.decomposition_source == "framework-conventions"


def test_b_plan_declared_elements_win_full_source():
    existing = [ForwardElementSpec(kind=ElementKind.CONSTANT, name="customCfg")]
    fe = {"next.config.mjs": list(existing)}
    apply_framework_defaults(fe)
    # full-source override: convention does NOT merge into a non-empty list
    assert [e.name for e in fe["next.config.mjs"]] == ["customCfg"]


def test_c_deterministic_empty_collision_convention_wins():
    fe = {"next.config.mjs": []}  # deterministic produced empty -> no contribution
    apply_framework_defaults(fe)
    assert fe["next.config.mjs"][0].name == "config"


def test_d_pure_default_export_sentinel_name():
    # MULTILANG FR-4: pure default-export JS/TS configs use DEFAULT_EXPORT + sentinel "default".
    for path in ("tailwind.config.js", "vite.config.ts", "jest.config.cjs"):
        fe = {path: []}
        apply_framework_defaults(fe)
        el = fe[path][0]
        assert el.kind == ElementKind.DEFAULT_EXPORT
        assert el.name == "default", f"{path} should use sentinel name 'default'"


def test_json_configs_stay_constant_not_default_export():
    # JSON configs are NOT JavaScript (no `export default`) — they keep CONSTANT (FR-4 scope).
    for path in ("tsconfig.json", "package.json", "jest.config.json", "prisma/schema.prisma"):
        fe = {path: []}
        apply_framework_defaults(fe)
        assert fe[path][0].kind == ElementKind.CONSTANT, f"{path} must stay CONSTANT"


def test_non_matching_path_untouched():
    fe = {"src/app/page.tsx": []}
    apply_framework_defaults(fe)
    assert fe["src/app/page.tsx"] == []


def test_exact_extension_anchoring_no_glob():
    fe = {"vite.config.bak": []}
    apply_framework_defaults(fe)
    assert fe["vite.config.bak"] == [], ".bak is not a registered extension"


def test_prisma_path_qualified_match():
    fe = {"prisma/schema.prisma": []}
    apply_framework_defaults(fe)
    assert fe["prisma/schema.prisma"], "path-qualified prisma entry should match"
    # bare filename without the prisma/ prefix must NOT match
    fe2 = {"schema.prisma": []}
    apply_framework_defaults(fe2)
    assert fe2["schema.prisma"] == []


def test_registry_version_stamped_and_populated():
    assert FRAMEWORK_CONFIG_REGISTRY_VERSION
    assert "next.config.mjs" in _FRAMEWORK_CONFIG_DEFAULTS
    assert "tailwind.config.cjs" in _FRAMEWORK_CONFIG_DEFAULTS


# ── t-convention-marker (Increment 2): file-level provenance schema ──────────

def test_framework_provenance_for_matching_path():
    from startd8.forward_manifest_extractor import (
        FRAMEWORK_CONFIG_REGISTRY_VERSION,
        framework_provenance_for_path,
    )

    prov = framework_provenance_for_path("next.config.mjs")
    assert prov is not None
    assert prov.source == "framework-conventions"
    assert prov.pattern == "next.config.mjs"
    assert prov.version == FRAMEWORK_CONFIG_REGISTRY_VERSION


def test_framework_provenance_none_for_non_match():
    from startd8.forward_manifest_extractor import framework_provenance_for_path

    assert framework_provenance_for_path("src/app.py") is None


def test_forward_file_spec_carries_convention_provenance_round_trip():
    from startd8.forward_manifest import ConventionProvenance, ForwardFileSpec

    prov = ConventionProvenance(pattern="tailwind.config.js", version="1.0.0")
    fs = ForwardFileSpec(file="tailwind.config.js", convention_provenance=prov)
    assert fs.convention_provenance is not None
    assert fs.convention_provenance.source == "framework-conventions"
    # default None when not a convention file
    assert ForwardFileSpec(file="src/app.py").convention_provenance is None
    # serialization round-trip survives the new field
    assert ForwardFileSpec.model_validate(fs.model_dump()) == fs
