"""Tests for CallGraphValidator preflight rule (Phase 6, Tier 3).

Tests cover CG-PF-1 (missing targets), CG-PF-2 (cycles),
CG-PF-3 (dynamic dispatch), and graceful degradation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from startd8.utils.code_manifest import (
    CallEntry,
    CallGraphInfo,
    CallKind,
    Element,
    ElementKind,
    FileManifest,
    Param,
    ParamKind,
    Signature,
    Span,
    Visibility,
)
from startd8.utils.manifest_registry import ManifestRegistry
from startd8.workflows.builtin.preflight_rules._base import RuleContext
from startd8.workflows.builtin.preflight_rules.call_graph_validator import (
    CallGraphValidator,
)
from startd8.workflows.builtin.domain_preflight_models import (
    AvailableDeps,
    TaskDomain,
)


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
    has_dynamic: bool = False,
    visibility: Visibility = Visibility.PUBLIC,
) -> Element:
    cg = None
    if calls is not None or has_dynamic:
        cg = CallGraphInfo(
            calls=calls or [],
            has_dynamic_dispatch=has_dynamic,
        )
    return Element(
        kind=ElementKind.FUNCTION,
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


def _make_rule_context(
    manifest: FileManifest,
    registry: ManifestRegistry | None = None,
    target_file: str = "a.py",
) -> RuleContext:
    return RuleContext(
        target_file=target_file,
        target_path=Path(target_file),
        target_dir=Path("."),
        project_root=Path("."),
        domain=TaskDomain.PYTHON_SINGLE_MODULE,
        available_deps=AvailableDeps(),
        manifest=manifest,
        manifest_registry=registry,
    )


# ═══════════════════════════════════════════════════════════════════════════
# CallGraphValidator tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCallGraphValidator:
    def test_missing_call_target(self):
        """CG-PF-1: Call to nonexistent FQN produces warning."""
        a = _func_element("a", "mod.a", calls=[_call("b", "nonexistent.b")])
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})

        ctx = _make_rule_context(m, reg)
        rule = CallGraphValidator()
        result = rule.evaluate(ctx)

        assert result is not None
        assert len(result.checks) >= 1
        assert any(c.check_name == "missing_call_target" for c in result.checks)

    def test_existing_call_target_no_warning(self):
        """CG-PF-1: Call to existing FQN does not produce warning."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        ctx = _make_rule_context(m, reg)
        rule = CallGraphValidator()
        result = rule.evaluate(ctx)

        # Should have no checks (or None) since all targets exist
        if result is not None:
            assert not any(c.check_name == "missing_call_target" for c in result.checks)

    def test_cycle_detection(self):
        """CG-PF-2: Circular call chain produces warning."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b", calls=[_call("a", "mod.a")])
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        ctx = _make_rule_context(m, reg)
        rule = CallGraphValidator()
        result = rule.evaluate(ctx)

        assert result is not None
        assert any(c.check_name == "call_graph_cycle" for c in result.checks)

    def test_no_cycles(self):
        """CG-PF-2: Linear chain produces no cycle warning."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        ctx = _make_rule_context(m, reg)
        rule = CallGraphValidator()
        result = rule.evaluate(ctx)

        if result is not None:
            assert not any(c.check_name == "call_graph_cycle" for c in result.checks)

    def test_dynamic_dispatch_advisory(self):
        """CG-PF-3: Dynamic dispatch produces info advisory."""
        a = _func_element("a", "mod.a", has_dynamic=True)
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})

        ctx = _make_rule_context(m, reg)
        rule = CallGraphValidator()
        result = rule.evaluate(ctx)

        assert result is not None
        assert any(c.check_name == "dynamic_dispatch" for c in result.checks)
        assert any(c.status == "info" for c in result.checks)

    def test_no_dynamic_dispatch(self):
        """CG-PF-3: No dynamic dispatch produces no advisory."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        ctx = _make_rule_context(m, reg)
        rule = CallGraphValidator()
        result = rule.evaluate(ctx)

        if result is not None:
            assert not any(c.check_name == "dynamic_dispatch" for c in result.checks)

    def test_rule_id(self):
        rule = CallGraphValidator()
        assert rule.rule_id == "call_graph_validator"

    def test_priority(self):
        rule = CallGraphValidator()
        assert rule.priority == 210


# ═══════════════════════════════════════════════════════════════════════════
# Graceful degradation
# ═══════════════════════════════════════════════════════════════════════════


class TestCallGraphValidatorDegradation:
    def test_no_registry(self):
        """Returns None when manifest_registry is None."""
        a = _func_element("a", "mod.a")
        m = _manifest("a.py", "mod", [a])
        ctx = _make_rule_context(m, registry=None)

        rule = CallGraphValidator()
        assert rule.evaluate(ctx) is None

    def test_no_call_graph_on_elements(self):
        """Elements without call_graph don't cause errors."""
        a = _func_element("a", "mod.a")  # No calls
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})

        ctx = _make_rule_context(m, reg)
        rule = CallGraphValidator()
        result = rule.evaluate(ctx)

        # Should be None or empty — no call graph data to validate
        if result is not None:
            assert not any(c.check_name == "missing_call_target" for c in result.checks)

    def test_empty_registry(self):
        """Empty registry doesn't cause errors."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({})  # Empty but not None

        ctx = _make_rule_context(m, reg)
        rule = CallGraphValidator()
        result = rule.evaluate(ctx)

        # Should produce missing target warning since mod.b not in empty registry
        assert result is not None
        assert any(c.check_name == "missing_call_target" for c in result.checks)

    def test_no_manifest_in_context(self):
        """No crash when manifest is None in context."""
        reg = ManifestRegistry({})
        ctx = RuleContext(
            target_file="a.py",
            target_path=Path("a.py"),
            target_dir=Path("."),
            project_root=Path("."),
            domain=TaskDomain.PYTHON_SINGLE_MODULE,
            available_deps=AvailableDeps(),
            manifest=None,
            manifest_registry=reg,
        )

        rule = CallGraphValidator()
        result = rule.evaluate(ctx)
        # Cycles check still runs, but no element-level checks
        # Should not crash
        assert result is None or isinstance(result.checks, list)

    def test_registered_in_registry(self):
        """CallGraphValidator is registered via _import_builtin_rules."""
        from startd8.workflows.builtin.preflight_rules._registry import (
            PreflightRuleRegistry,
        )
        PreflightRuleRegistry.clear()
        PreflightRuleRegistry.discover(force=True)
        assert "call_graph_validator" in PreflightRuleRegistry.list_rules()
