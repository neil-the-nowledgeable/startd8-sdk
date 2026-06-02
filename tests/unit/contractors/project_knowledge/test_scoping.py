"""REQ-CKG-524/527 — structural relevance scoping (no keyword gate)."""

from __future__ import annotations

from startd8.contractors.project_knowledge import module_closure, referenced_entities


class TestModuleClosure:
    def test_resolves_alias_import_to_project_module(self):
        target = {"app/api/cap.ts": "import { db } from '@/lib/db'\n"}
        reached = module_closure(target, ["lib/db.ts", "lib/other.ts"])
        assert reached == {"lib/db.ts"}

    def test_bare_package_import_resolves_to_nothing(self):
        target = {"app/x.ts": "import { z } from 'zod'\n"}
        assert module_closure(target, ["lib/db.ts"]) == set()

    def test_relative_import_resolved_against_importer(self):
        target = {"lib/a.ts": "import { b } from './b'\n"}
        assert module_closure(target, ["lib/b.ts"]) == {"lib/b.ts"}


class TestReferencedEntities:
    def test_pascalcase_type_reference(self):
        # PI-001-style: filename matches no _MIRROR_NAMES stem, but the body
        # references the entity → REQ-527 still scopes it.
        texts = ["export async function enrich() { return prisma.capability.findMany() }"]
        assert referenced_entities(texts, ["Capability", "Outcome"]) == {"Capability"}

    def test_matches_in_description(self):
        assert referenced_entities(["update the Outcome rows"], ["Capability", "Outcome"]) == {"Outcome"}

    def test_no_reference_scopes_to_none(self):
        assert referenced_entities(["render a button"], ["Capability"]) == set()

    def test_plural_form_matches(self):
        # PI-001: "enrich-capabilities" references the Capability entity (y→ies).
        assert referenced_entities(["enrich-capabilities feature"], ["Capability"]) == {"Capability"}
        assert referenced_entities(["update outcomes"], ["Outcome"]) == {"Outcome"}

    def test_unrelated_substring_no_false_positive(self):
        # "Capacitor" shares a prefix but is not a plural form of "Capability"
        assert referenced_entities(["a Capacitor component"], ["Capability"]) == set()

    def test_empty_inputs(self):
        assert referenced_entities([], ["Capability"]) == set()
        assert referenced_entities(["Capability"], []) == set()
