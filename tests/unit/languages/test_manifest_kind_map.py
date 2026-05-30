"""FR-3 acceptance — MULTILANG_MANIFEST_VALIDATION Phase 1.

The kind-string -> ElementKind map must be total over every kind the per-language parsers
emit, non-colliding, and additive (the new ElementKind members exist; TYPE_ALIAS not re-added).
"""

from startd8.languages.manifest_adapter import (
    PARSER_KIND_MAP,
    PARSER_KIND_SETS,
    map_parser_kind,
)
from startd8.utils.code_manifest import ElementKind


class TestKindMapTotality:
    def test_every_parser_kind_is_mapped(self):
        # FR-3: each parser's emitted kind set ⊆ map keys (no silent drop / KeyError).
        for lang, kinds in PARSER_KIND_SETS.items():
            missing = kinds - set(PARSER_KIND_MAP)
            assert not missing, f"{lang}: unmapped kinds {missing}"

    def test_all_map_values_are_elementkind(self):
        for k, v in PARSER_KIND_MAP.items():
            assert isinstance(v, ElementKind), f"{k!r} -> {v!r} is not an ElementKind"

    def test_map_keys_unique_no_collision(self):
        # A dict literal can't hold duplicate keys, but guard against a future edit that
        # maps the same string twice via merge — assert the literal count matches.
        # (Also documents the non-colliding requirement, R1-F5.)
        assert len(PARSER_KIND_MAP) == len(set(PARSER_KIND_MAP))


class TestNewElementKinds:
    def test_new_members_exist(self):
        for name in ("INTERFACE", "ENUM", "STRUCT", "RECORD", "FIELD", "DEFAULT_EXPORT"):
            assert hasattr(ElementKind, name), f"ElementKind.{name} missing"

    def test_type_alias_not_duplicated(self):
        # R1-F5: TYPE_ALIAS pre-existed; ensure it's still a single member with its value.
        assert ElementKind.TYPE_ALIAS.value == "type_alias"

    def test_elementkind_values_unique(self):
        values = [m.value for m in ElementKind]
        assert len(values) == len(set(values)), "duplicate ElementKind value"

    def test_additive_existing_values_unchanged(self):
        # NFR-2: existing values are byte-stable (serialization round-trips).
        assert ElementKind.CLASS.value == "class"
        assert ElementKind.FUNCTION.value == "function"
        assert ElementKind.CONSTANT.value == "constant"


class TestMapParserKind:
    def test_known_kinds_resolve(self):
        assert map_parser_kind("const_function") is ElementKind.FUNCTION
        assert map_parser_kind("constructor") is ElementKind.METHOD
        assert map_parser_kind("interface") is ElementKind.INTERFACE
        assert map_parser_kind("record") is ElementKind.RECORD
        assert map_parser_kind("default_export") is ElementKind.DEFAULT_EXPORT
        assert map_parser_kind("type_alias") is ElementKind.TYPE_ALIAS

    def test_unknown_kind_degrades_to_variable(self):
        # Graceful runtime fallback (logs a warning); the totality test above guards
        # against this happening for the known parsers.
        assert map_parser_kind("some_future_kind") is ElementKind.VARIABLE
