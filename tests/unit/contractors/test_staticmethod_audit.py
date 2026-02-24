"""AR-814: Static method audit for all phase handler classes.

Verifies that methods not using ``self`` are decorated with ``@staticmethod``.
This test prevents future regressions where a method that doesn't reference
``self`` is added without the decorator.
"""

from __future__ import annotations

import inspect
import textwrap

import pytest


def _get_phase_handler_classes():
    """Import all phase handler classes from context_seed_handlers."""
    from startd8.contractors.context_seed_handlers import (
        DesignPhaseHandler,
        FinalizePhaseHandler,
        ImplementPhaseHandler,
        IntegratePhaseHandler,
        PlanPhaseHandler,
        ScaffoldPhaseHandler,
        TestPhaseHandler,
        ReviewPhaseHandler,
    )
    return [
        PlanPhaseHandler,
        ScaffoldPhaseHandler,
        DesignPhaseHandler,
        ImplementPhaseHandler,
        IntegratePhaseHandler,
        TestPhaseHandler,
        ReviewPhaseHandler,
        FinalizePhaseHandler,
    ]


def _methods_of(cls):
    """Return all methods defined directly on *cls* (not inherited)."""
    results = []
    for name, obj in inspect.getmembers(cls, predicate=inspect.isfunction):
        # Only methods defined in this class, not inherited
        if name in cls.__dict__:
            results.append((name, obj))
    return results


def _uses_self(func) -> bool:
    """Check whether *func* references ``self`` in its body (not just signature)."""
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return True  # Can't inspect — assume it uses self

    lines = source.splitlines()
    # Find the def line and skip it (plus any decorators above)
    body_started = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("def "):
            body_started = True
            continue
        if not body_started:
            continue
        # Skip docstrings (triple-quote blocks)
        # Simple heuristic: look for 'self.' or 'self,' or 'self)' usage
        if "self." in stripped or "self," in stripped or "self)" in stripped:
            return True
    return False


@pytest.mark.unit
class TestStaticMethodAudit:
    """Verify that non-self methods are decorated with @staticmethod."""

    def test_all_non_self_methods_are_static(self):
        """Every method that doesn't reference self should be @staticmethod."""
        violations = []

        for cls in _get_phase_handler_classes():
            for name, func in _methods_of(cls):
                if name.startswith("__"):
                    continue  # Skip dunder methods

                is_static = isinstance(
                    inspect.getattr_static(cls, name), staticmethod,
                )
                if is_static:
                    continue  # Already a staticmethod

                # Check if it uses self
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                has_self_param = params and params[0] == "self"

                if has_self_param and not _uses_self(func):
                    violations.append(
                        f"{cls.__name__}.{name}: has 'self' param but "
                        f"doesn't use it — should be @staticmethod"
                    )

        if violations:
            msg = "Static method audit violations:\n" + "\n".join(
                f"  - {v}" for v in violations
            )
            pytest.fail(msg)

    def test_handler_classes_exist(self):
        """Smoke test: all 8 phase handler classes are importable."""
        classes = _get_phase_handler_classes()
        assert len(classes) == 8
        class_names = {c.__name__ for c in classes}
        assert "FinalizePhaseHandler" in class_names
        assert "ImplementPhaseHandler" in class_names
        assert "ScaffoldPhaseHandler" in class_names
