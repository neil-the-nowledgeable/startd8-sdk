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
        """Multiple functions referencing module-level globals → coupled.

        AC-R10: Thresholds raised to global_refs >= 4 and module_globals >= 2
        to avoid false positives on logger/common infra.  Test uses 2 real
        data globals each referenced by 2 functions (4 total refs).
        """
        skeleton = (
            "from faker import Faker\n"
            "\n"
            "fake = Faker()\n"
            "product_ids = ['A', 'B', 'C']\n"
            "\n"
            "def checkout():\n"
            "    email = fake.email()\n"
            "    pid = product_ids[0]\n"
            "    raise NotImplementedError\n"
            "\n"
            "def add_to_cart():\n"
            "    pid = product_ids[0]\n"
            "    name = fake.name()\n"
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
        """Multiple functions calling siblings → coupled.

        AC-R10: cross_refs threshold raised to >= 4.  Need 4+ cross-refs
        to trigger coupling (was 2).
        """
        skeleton = (
            "def add_to_cart(product_id):\n"
            "    raise NotImplementedError\n"
            "\n"
            "def view_cart():\n"
            "    add_to_cart('preview')\n"
            "    raise NotImplementedError\n"
            "\n"
            "def checkout():\n"
            "    add_to_cart('A')\n"
            "    view_cart()\n"
            "    raise NotImplementedError\n"
            "\n"
            "def finalize():\n"
            "    checkout()\n"
            "    view_cart()\n"
            "    raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="add_to_cart", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="view_cart", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="checkout", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="finalize", signature=_EMPTY_SIG),
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
        """__init__ sets multiple attrs, serve() reads them → coupled.

        AC-R10: shared_attrs threshold raised to >= 3.
        """
        skeleton = (
            "class EmailService:\n"
            "    def __init__(self):\n"
            "        self.template = None\n"
            "        self.client = None\n"
            "        self.config = {}\n"
            "        raise NotImplementedError\n"
            "\n"
            "    def serve(self):\n"
            "        self.template.render()\n"
            "        self.client.send()\n"
            "        self.config['port']\n"
            "        raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.CLASS, name="EmailService"),
        ])
        assert _has_high_within_file_coupling(file_spec, skeleton) is True

    def test_two_shared_attrs_not_enough(self):
        """Only 2 shared attrs is below threshold (AC-R10: raised to 3)."""
        skeleton = (
            "class Simple:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "        self.y = 2\n"
            "        raise NotImplementedError\n"
            "\n"
            "    def get(self):\n"
            "        self.x\n"
            "        self.y\n"
            "        raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.CLASS, name="Simple"),
        ])
        # AC-R10: Threshold raised to 3 shared attrs
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

    def test_manifest_variables_count_as_globals(self):
        """CONSTANT/VARIABLE manifest elements count toward module_globals
        even when the skeleton doesn't contain them (e.g. plan ingestion
        didn't include the variable in the skeleton).

        This ensures files like locustfile.py (with `fake = Faker()` in
        the manifest) get routed to file-whole when functions reference
        the variable.
        """
        skeleton = (
            "def checkout(self):\n"
            "    fake.name()\n"
            "    product_ids[0]\n"
            "    raise NotImplementedError\n"
            "\n"
            "def add_to_cart(self):\n"
            "    fake.email()\n"
            "    product_ids[1]\n"
            "    raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="checkout", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="add_to_cart", signature=_EMPTY_SIG),
            # These are VARIABLE elements in the manifest but NOT in skeleton
            ForwardElementSpec(kind=ElementKind.VARIABLE, name="fake"),
            ForwardElementSpec(kind=ElementKind.VARIABLE, name="product_ids"),
        ])
        # 2 manifest variables + 4 references → triggers coupling
        assert _has_high_within_file_coupling(file_spec, skeleton) is True

    def test_module_var_density_triggers_coupling(self):
        """When module-level variables outnumber function/class elements,
        coupling is detected even with few total global_refs.

        This catches the PI-008 pattern: 2 module variables (fake, product_ids)
        with only 1 function referencing them — the previous threshold (>=4
        global_refs) missed this, but the density signal catches it.
        """
        skeleton = (
            "fake = Faker()\n"
            "product_ids = ['A', 'B']\n"
            "config = {'port': 8080}\n"
            "\n"
            "def create_app():\n"
            "    fake.name()\n"
            "    raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="create_app", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.VARIABLE, name="fake"),
            ForwardElementSpec(kind=ElementKind.VARIABLE, name="product_ids"),
            ForwardElementSpec(kind=ElementKind.VARIABLE, name="config"),
        ])
        # 3 module vars, 1 function element → ratio 3.0 ≥ 1.0
        # with at least 1 global_ref → triggers density signal
        assert _has_high_within_file_coupling(file_spec, skeleton) is True

    def test_infra_globals_excluded_from_manifest_variables(self):
        """Variables named 'logger', 'app', etc. don't count even as manifest elements."""
        skeleton = (
            "def handle():\n"
            "    logger.info('x')\n"
            "    raise NotImplementedError\n"
        )
        file_spec = _make_file_spec([
            ForwardElementSpec(kind=ElementKind.FUNCTION, name="handle", signature=_EMPTY_SIG),
            ForwardElementSpec(kind=ElementKind.VARIABLE, name="logger"),
        ])
        assert _has_high_within_file_coupling(file_spec, skeleton) is False
