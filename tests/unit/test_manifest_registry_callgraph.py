"""Tests for ManifestRegistry call graph methods (Phase 6).

Tests cover call_graph(), reverse_call_graph(), blast_radius(),
dead_candidates(), callers_of(), callees_of(), and cache invalidation.
"""

from __future__ import annotations

import pytest

from startd8.utils.code_manifest import (
    CallEdge,
    CallEntry,
    CallGraphInfo,
    CallKind,
    Element,
    ElementKind,
    FileManifest,
    SCHEMA_VERSION,
    Span,
    Signature,
    Param,
    ParamKind,
    Visibility,
)
from startd8.utils.manifest_registry import ManifestDiff, ManifestRegistry


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _span() -> Span:
    return Span(start_line=1, start_col=0, end_line=1, end_col=10)


def _sig() -> Signature:
    return Signature(params=[Param(name="self", kind=ParamKind.POSITIONAL)])


def _func_element(
    name: str,
    fqn: str,
    calls: list[CallEntry] | None = None,
    visibility: Visibility = Visibility.PUBLIC,
    kind: ElementKind = ElementKind.FUNCTION,
) -> Element:
    """Create a function element with optional call graph."""
    cg = None
    if calls is not None:
        cg = CallGraphInfo(calls=calls)
    return Element(
        kind=kind,
        name=name,
        fqn=fqn,
        span=_span(),
        signature=_sig(),
        call_graph=cg,
        visibility=visibility,
    )


def _manifest(
    file: str, module: str, elements: list[Element],
) -> FileManifest:
    return FileManifest(
        file=file,
        module=module,
        digest="sha256:test",
        generated_at="2026-01-01T00:00:00Z",
        elements=elements,
    )


def _call(target: str, fqn: str | None = None) -> CallEntry:
    return CallEntry(
        target=target,
        target_fqn=fqn,
        kind=CallKind.FUNCTION_CALL,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Call graph construction
# ═══════════════════════════════════════════════════════════════════════════


class TestCallGraph:
    def test_basic_call_graph(self):
        """A→B edge appears in call_graph."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        cg = reg.call_graph()
        assert "mod.a" in cg
        assert "mod.b" in cg["mod.a"]

    def test_empty_registry(self):
        reg = ManifestRegistry({})
        assert reg.call_graph() == {}

    def test_no_resolved_calls(self):
        """Unresolved calls (target_fqn=None) are excluded."""
        a = _func_element("a", "mod.a", calls=[_call("external", None)])
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})

        cg = reg.call_graph()
        assert "mod.a" not in cg

    def test_multiple_callees(self):
        a = _func_element("a", "mod.a", calls=[
            _call("b", "mod.b"),
            _call("c", "mod.c"),
        ])
        b = _func_element("b", "mod.b")
        c = _func_element("c", "mod.c")
        m = _manifest("a.py", "mod", [a, b, c])
        reg = ManifestRegistry({"a.py": m})

        cg = reg.call_graph()
        assert cg["mod.a"] == {"mod.b", "mod.c"}

    def test_call_graph_is_cached(self):
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        cg1 = reg.call_graph()
        cg2 = reg.call_graph()
        assert cg1 is cg2  # Same object — cached


# ═══════════════════════════════════════════════════════════════════════════
# Reverse call graph
# ═══════════════════════════════════════════════════════════════════════════


class TestReverseCallGraph:
    def test_reverse_is_transpose(self):
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b", calls=[_call("c", "mod.c")])
        c = _func_element("c", "mod.c")
        m = _manifest("a.py", "mod", [a, b, c])
        reg = ManifestRegistry({"a.py": m})

        rev = reg.reverse_call_graph()
        assert "mod.b" in rev
        assert "mod.a" in rev["mod.b"]
        assert "mod.c" in rev
        assert "mod.b" in rev["mod.c"]

    def test_reverse_empty(self):
        reg = ManifestRegistry({})
        assert reg.reverse_call_graph() == {}


# ═══════════════════════════════════════════════════════════════════════════
# Blast radius
# ═══════════════════════════════════════════════════════════════════════════


class TestBlastRadius:
    def test_transitive_callers(self):
        """A→B→C: blast_radius(C) = {A, B}."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b", calls=[_call("c", "mod.c")])
        c = _func_element("c", "mod.c")
        m = _manifest("a.py", "mod", [a, b, c])
        reg = ManifestRegistry({"a.py": m})

        radius = reg.blast_radius("mod.c")
        assert radius == {"mod.a", "mod.b"}

    def test_depth_limit(self):
        """A→B→C: blast_radius(C, max_depth=1) = {B} only."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b", calls=[_call("c", "mod.c")])
        c = _func_element("c", "mod.c")
        m = _manifest("a.py", "mod", [a, b, c])
        reg = ManifestRegistry({"a.py": m})

        radius = reg.blast_radius("mod.c", max_depth=1)
        assert radius == {"mod.b"}

    def test_unknown_fqn(self):
        reg = ManifestRegistry({})
        assert reg.blast_radius("nonexistent.func") == set()

    def test_no_callers(self):
        a = _func_element("a", "mod.a")
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})
        assert reg.blast_radius("mod.a") == set()


# ═══════════════════════════════════════════════════════════════════════════
# Dead code candidates
# ═══════════════════════════════════════════════════════════════════════════


class TestDeadCandidates:
    def test_orphaned_public_function(self):
        """Public function with no callers appears in dead_candidates."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        orphan = _func_element("orphan", "mod.orphan")
        m = _manifest("a.py", "mod", [a, b, orphan])
        reg = ManifestRegistry({"a.py": m})

        dead = reg.dead_candidates()
        assert "mod.orphan" in dead
        assert "mod.a" in dead  # a is also never called
        assert "mod.b" not in dead  # b is called by a

    def test_private_excluded(self):
        """Private functions are excluded from dead candidates."""
        priv = _func_element(
            "_private", "mod._private", visibility=Visibility.PRIVATE,
        )
        m = _manifest("a.py", "mod", [priv])
        reg = ManifestRegistry({"a.py": m})

        dead = reg.dead_candidates()
        assert "mod._private" not in dead

    def test_protected_excluded(self):
        """Protected functions are excluded."""
        prot = _func_element(
            "_protected", "mod._protected", visibility=Visibility.PROTECTED,
        )
        m = _manifest("a.py", "mod", [prot])
        reg = ManifestRegistry({"a.py": m})

        dead = reg.dead_candidates()
        assert "mod._protected" not in dead

    def test_sorted_alphabetically(self):
        z = _func_element("z", "mod.z")
        a = _func_element("a", "mod.a")
        m_func = _func_element("m", "mod.m")
        m = _manifest("a.py", "mod", [z, a, m_func])
        reg = ManifestRegistry({"a.py": m})

        dead = reg.dead_candidates()
        assert dead == sorted(dead)


# ═══════════════════════════════════════════════════════════════════════════
# callers_of and callees_of
# ═══════════════════════════════════════════════════════════════════════════


class TestCallersCalleesOf:
    def test_callers_of(self):
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        assert reg.callers_of("mod.b") == {"mod.a"}

    def test_callees_of(self):
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        assert reg.callees_of("mod.a") == {"mod.b"}

    def test_callers_of_unknown(self):
        reg = ManifestRegistry({})
        assert reg.callers_of("nonexistent") == set()

    def test_callees_of_unknown(self):
        reg = ManifestRegistry({})
        assert reg.callees_of("nonexistent") == set()


# ═══════════════════════════════════════════════════════════════════════════
# Cache invalidation via with_updated_files
# ═══════════════════════════════════════════════════════════════════════════


class TestCacheInvalidation:
    def test_with_updated_files_resets_caches(self):
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        # Populate caches
        _ = reg.call_graph()
        _ = reg.reverse_call_graph()

        # Create updated registry
        new_b = _func_element("b", "mod.b", calls=[_call("c", "mod.c")])
        c = _func_element("c", "mod.c")
        m2 = _manifest("a.py", "mod", [a, new_b, c])
        reg2 = reg.with_updated_files({"a.py": m2})

        # New registry should have fresh caches
        cg = reg2.call_graph()
        assert "mod.b" in cg
        assert "mod.c" in cg["mod.b"]


# ═══════════════════════════════════════════════════════════════════════════
# Cross-file call graph
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossFileCallGraph:
    def test_cross_file_edges(self):
        """Calls from file1 to file2 appear in unified graph."""
        a = _func_element("a", "pkg.a", calls=[_call("b", "pkg2.b")])
        b = _func_element("b", "pkg2.b")
        m1 = _manifest("pkg/a.py", "pkg", [a])
        m2 = _manifest("pkg2/b.py", "pkg2", [b])
        reg = ManifestRegistry({"pkg/a.py": m1, "pkg2/b.py": m2})

        cg = reg.call_graph()
        assert "pkg.a" in cg
        assert "pkg2.b" in cg["pkg.a"]

        rev = reg.reverse_call_graph()
        assert "pkg2.b" in rev
        assert "pkg.a" in rev["pkg2.b"]


# ═══════════════════════════════════════════════════════════════════════════
# callers_of_file
# ═══════════════════════════════════════════════════════════════════════════


class TestCallersOfFile:
    def test_cross_file_callers(self):
        """Cross-file callers are returned; intra-file callers are not."""
        a = _func_element("a", "pkg.a", calls=[_call("b", "pkg2.b")])
        b = _func_element("b", "pkg2.b")
        m1 = _manifest("pkg/a.py", "pkg", [a])
        m2 = _manifest("pkg2/b.py", "pkg2", [b])
        reg = ManifestRegistry({"pkg/a.py": m1, "pkg2/b.py": m2})

        result = reg.callers_of_file("pkg2/b.py")
        assert "pkg2.b" in result
        assert "pkg.a" in result["pkg2.b"]

    def test_no_callers(self):
        """File with no external callers returns empty dict."""
        a = _func_element("a", "mod.a")
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})

        assert reg.callers_of_file("a.py") == {}

    def test_intra_file_excluded(self):
        """Callers within the same file are excluded."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        result = reg.callers_of_file("a.py")
        # b is called by a, but both are in a.py — excluded
        assert result == {}

    def test_nonexistent_file(self):
        reg = ManifestRegistry({})
        assert reg.callers_of_file("nonexistent.py") == {}


# ═══════════════════════════════════════════════════════════════════════════
# call_graph_summary
# ═══════════════════════════════════════════════════════════════════════════


class TestCallGraphSummary:
    def test_basic_summary(self):
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        summary = reg.call_graph_summary("a.py", budget=2000)
        assert "mod.a" in summary
        assert "mod.b" in summary
        assert "called by" in summary
        assert "calls" in summary

    def test_budget_truncation(self):
        """Very small budget triggers truncation."""
        elements = [
            _func_element(f"f{i}", f"mod.f{i}", calls=[_call(f"f{i+1}", f"mod.f{i+1}")])
            for i in range(20)
        ]
        elements.append(_func_element("f20", "mod.f20"))
        m = _manifest("a.py", "mod", elements)
        reg = ManifestRegistry({"a.py": m})

        summary = reg.call_graph_summary("a.py", budget=50)
        assert len(summary) <= 60  # Allow some margin for count-only tier

    def test_empty_file(self):
        m = _manifest("a.py", "mod", [])
        reg = ManifestRegistry({"a.py": m})

        assert reg.call_graph_summary("a.py") == ""

    def test_nonexistent_file(self):
        reg = ManifestRegistry({})
        assert reg.call_graph_summary("nonexistent.py") == ""

    def test_no_connections(self):
        """File with elements but no call edges returns empty."""
        a = _func_element("a", "mod.a")
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})

        assert reg.call_graph_summary("a.py") == ""


# ═══════════════════════════════════════════════════════════════════════════
# max_blast_radius
# ═══════════════════════════════════════════════════════════════════════════


class TestMaxBlastRadius:
    def test_multiple_fqns(self):
        """Returns FQN with the most transitive callers."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b", calls=[_call("c", "mod.c")])
        c = _func_element("c", "mod.c")
        d = _func_element("d", "mod.d")
        m = _manifest("a.py", "mod", [a, b, c, d])
        reg = ManifestRegistry({"a.py": m})

        fqn, count = reg.max_blast_radius(["mod.c", "mod.b", "mod.d"])
        assert fqn == "mod.c"  # c has callers a, b (transitive)
        assert count == 2

    def test_empty_list(self):
        reg = ManifestRegistry({})
        assert reg.max_blast_radius([]) == ("", 0)

    def test_nonexistent_fqns(self):
        reg = ManifestRegistry({})
        fqn, count = reg.max_blast_radius(["nonexistent.a", "nonexistent.b"])
        assert count == 0

    def test_single_fqn(self):
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        fqn, count = reg.max_blast_radius(["mod.b"])
        assert fqn == "mod.b"
        assert count == 1  # a calls b


# ═══════════════════════════════════════════════════════════════════════════
# call_graph_cycles
# ═══════════════════════════════════════════════════════════════════════════


class TestCallGraphCycles:
    def test_simple_cycle(self):
        """A→B→A is detected."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b", calls=[_call("a", "mod.a")])
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        cycles = reg.call_graph_cycles()
        assert len(cycles) >= 1
        # At least one cycle should contain both a and b
        found = any(
            "mod.a" in c and "mod.b" in c
            for c in cycles
        )
        assert found

    def test_longer_cycle(self):
        """A→B→C→A is detected."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b", calls=[_call("c", "mod.c")])
        c = _func_element("c", "mod.c", calls=[_call("a", "mod.a")])
        m = _manifest("a.py", "mod", [a, b, c])
        reg = ManifestRegistry({"a.py": m})

        cycles = reg.call_graph_cycles()
        assert len(cycles) >= 1
        found = any(
            "mod.a" in c and "mod.b" in c and "mod.c" in c
            for c in cycles
        )
        assert found

    def test_no_cycles(self):
        """Linear chain has no cycles."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b", calls=[_call("c", "mod.c")])
        c = _func_element("c", "mod.c")
        m = _manifest("a.py", "mod", [a, b, c])
        reg = ManifestRegistry({"a.py": m})

        assert reg.call_graph_cycles() == []

    def test_depth_bound(self):
        """Cycle deeper than max_depth is not detected."""
        # Chain: f0→f1→f2→...→f15→f0 (cycle at depth 16)
        elements = []
        for i in range(16):
            next_i = (i + 1) % 16
            elements.append(
                _func_element(f"f{i}", f"mod.f{i}", calls=[_call(f"f{next_i}", f"mod.f{next_i}")])
            )
        m = _manifest("a.py", "mod", elements)
        reg = ManifestRegistry({"a.py": m})

        # With depth=5, should not find the 16-node cycle
        cycles = reg.call_graph_cycles(max_depth=5)
        # The cycle is longer than 5, so it should be missed
        long_cycle = [c for c in cycles if len(c) > 7]
        assert len(long_cycle) == 0

    def test_empty_graph(self):
        reg = ManifestRegistry({})
        assert reg.call_graph_cycles() == []


# ═══════════════════════════════════════════════════════════════════════════
# ManifestDiff call edge fields
# ═══════════════════════════════════════════════════════════════════════════


class TestManifestDiffCallEdges:
    def test_added_edges(self):
        """New call edges appear in added_call_edges."""
        a = _func_element("a", "mod.a")
        b = _func_element("b", "mod.b")
        old = _manifest("a.py", "mod", [a, b])

        a_new = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        new = _manifest("a.py", "mod", [a_new, b])

        diff = ManifestDiff.diff(old, new)
        assert len(diff.added_call_edges) == 1
        assert diff.added_call_edges[0].caller_fqn == "mod.a"
        assert diff.added_call_edges[0].callee_fqn == "mod.b"
        assert diff.removed_call_edges == []

    def test_removed_edges(self):
        """Removed call edges appear in removed_call_edges."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        old = _manifest("a.py", "mod", [a, b])

        a_new = _func_element("a", "mod.a")
        new = _manifest("a.py", "mod", [a_new, b])

        diff = ManifestDiff.diff(old, new)
        assert len(diff.removed_call_edges) == 1
        assert diff.removed_call_edges[0].caller_fqn == "mod.a"
        assert diff.removed_call_edges[0].callee_fqn == "mod.b"
        assert diff.added_call_edges == []

    def test_no_changes(self):
        """Identical call graphs produce empty edge diffs."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])

        diff = ManifestDiff.diff(m, m)
        assert diff.removed_call_edges == []
        assert diff.added_call_edges == []

    def test_call_edge_diff_standalone(self):
        """call_edge_diff static method works independently."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        old = _manifest("a.py", "mod", [a, b])

        a_new = _func_element("a", "mod.a", calls=[_call("c", "mod.c")])
        c = _func_element("c", "mod.c")
        new = _manifest("a.py", "mod", [a_new, b, c])

        removed, added = ManifestDiff.call_edge_diff(old, new)
        assert len(removed) == 1
        assert removed[0].caller_fqn == "mod.a"
        assert removed[0].callee_fqn == "mod.b"
        assert len(added) == 1
        assert added[0].caller_fqn == "mod.a"
        assert added[0].callee_fqn == "mod.c"

    def test_signature_changes_with_callers(self):
        """When registry is provided, sig changes include callers."""
        # Build a registry with a → b (a calls b)
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        # Old b has no params, new b has a param
        b_new = Element(
            kind=ElementKind.FUNCTION,
            name="b",
            fqn="mod.b",
            span=_span(),
            signature=Signature(params=[
                Param(name="self", kind=ParamKind.POSITIONAL),
                Param(name="x", kind=ParamKind.POSITIONAL, annotation="int"),
            ]),
            visibility=Visibility.PUBLIC,
        )
        new_m = _manifest("a.py", "mod", [a, b_new])

        diff = ManifestDiff.diff(m, new_m, registry=reg)
        assert len(diff.changed_signatures) == 1
        assert len(diff.signature_changes_with_callers) == 1
        fqn, _, _, callers = diff.signature_changes_with_callers[0]
        assert fqn == "mod.b"
        assert "mod.a" in callers
