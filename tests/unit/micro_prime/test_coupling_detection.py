"""Tests for within-file coupling detection (Kaizen run-042 P1a).

Verifies that _has_high_within_file_coupling correctly detects:
1. Module-level globals referenced by multiple functions
2. Functions calling sibling functions
3. Class methods sharing instance state
"""

from __future__ import annotations

import pytest

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, ForwardImportSpec
from startd8.micro_prime.engine import _has_high_within_file_coupling
from startd8.utils.code_manifest import ElementKind, Param, Signature

_EMPTY_SIG = Signature(params=[])


# ── Fixtures ────────────────────────────────────────────────────────────


def _make_file_spec(elements: list[ForwardElementSpec], path: str = "src/app.py") -> ForwardFileSpec:
    return ForwardFileSpec(file=path, elements=elements)


# ── 1. Module-level globals ─────────────────────────────────────────────


class TestModuleLevelGlobals:
    """Detect coupling via shared module-level globals (PI-009 pattern)."""

    def test_shared_global_detected(self):
        """Multiple functions referencing a module-level global → coupled."""
        skeleton = (
            "from faker import Faker\n"
            "\n"
            "fake = Faker()\n"
            "product_ids = ['A', 'B', 'C']\n"
            "\n"
            "def checkout():\n"
            "    email = fake.email()\n"
            "    raise NotImplementedError\n"
            "\n"
            "def add_to_cart():\n"
            "    pid = product_ids[0]\n"
            "    raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="checkout", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="add_to_cart", signature=_EMPTY_SIG),
        ])
        assert _has_high_within_file_coupling(file_spec, skeleton) is True

    def test_no_globals_no_coupling(self):
        """Independent functions with no shared globals → not coupled."""
        skeleton = (
            "def func_a():\n"
            "    raise NotImplementedError\n"
            "\n"
            "def func_b():\n"
            "    raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="func_a", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="func_b", signature=_EMPTY_SIG),
        ])
        assert _has_high_within_file_coupling(file_spec, skeleton) is False


# ── 2. Cross-function calls ─────────────────────────────────────────────


class TestCrossFunctionCalls:
    """Detect coupling via inter-function calls."""

    def test_function_calling_sibling(self):
        """checkout() calls add_to_cart() → coupled."""
        skeleton = (
            "def add_to_cart(product_id):\n"
            "    raise NotImplementedError\n"
            "\n"
            "def view_cart():\n"
            "    raise NotImplementedError\n"
            "\n"
            "def checkout():\n"
            "    add_to_cart('A')\n"
            "    view_cart()\n"
            "    raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="add_to_cart", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="view_cart", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="checkout", signature=_EMPTY_SIG),
        ])
        assert _has_high_within_file_coupling(file_spec, skeleton) is True

    def test_no_cross_calls(self):
        """Functions that don't reference each other → not coupled."""
        skeleton = (
            "import os\n"
            "\n"
            "def func_a():\n"
            "    os.path.exists('x')\n"
            "    raise NotImplementedError\n"
            "\n"
            "def func_b():\n"
            "    os.getcwd()\n"
            "    raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="func_a", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="func_b", signature=_EMPTY_SIG),
        ])
        assert _has_high_within_file_coupling(file_spec, skeleton) is False


# ── 3. Shared instance state ────────────────────────────────────────────


class TestSharedInstanceState:
    """Detect coupling via self.x shared between methods."""

    def test_init_writes_other_reads(self):
        """__init__ sets self.template, serve() reads it → coupled."""
        skeleton = (
            "class EmailService:\n"
            "    def __init__(self):\n"
            "        self.template = None\n"
            "        self.client = None\n"
            "        raise NotImplementedError\n"
            "\n"
            "    def serve(self):\n"
            "        self.template.render()\n"
            "        self.client.send()\n"
            "        raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.CLASS, name="EmailService"),
        ])
        assert _has_high_within_file_coupling(file_spec, skeleton) is True

    def test_single_shared_attr_not_enough(self):
        """Only 1 shared attr is below threshold."""
        skeleton = (
            "class Simple:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "        raise NotImplementedError\n"
            "\n"
            "    def get(self):\n"
            "        self.x\n"
            "        raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.CLASS, name="Simple"),
        ])
        # Threshold is 2 shared attrs
        assert _has_high_within_file_coupling(file_spec, skeleton) is False


# ── 4. Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:

    def test_syntax_error_skeleton_returns_false(self):
        """Unparseable skeleton should not crash."""
        skeleton = "def broken(\n"
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="broken", signature=_EMPTY_SIG),
        ])
        assert _has_high_within_file_coupling(file_spec, skeleton) is False

    def test_empty_skeleton(self):
        file_spec = _make_file_spec([])
        assert _has_high_within_file_coupling(file_spec, "") is False

    def test_single_element_no_coupling(self):
        """A single function can't be coupled to itself."""
        skeleton = (
            "def solo():\n"
            "    x = 1\n"
            "    raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="solo", signature=_EMPTY_SIG),
        ])
        assert _has_high_within_file_coupling(file_spec, skeleton) is False
