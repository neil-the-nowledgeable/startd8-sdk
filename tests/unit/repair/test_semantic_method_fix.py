"""Tests for SemanticMethodFixStep (Kaizen run-042 P1b).

Covers:
1. Missing self insertion on methods
2. datetime module/class disambiguation
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.repair.models import ElementContext, RepairContext, RepairStepResult
from startd8.repair.steps.semantic_method_fix import (
    SemanticMethodFixStep,
    _fix_datetime_confusion,
    _fix_missing_self,
)


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def step() -> SemanticMethodFixStep:
    return SemanticMethodFixStep()


@pytest.fixture
def method_context() -> ElementContext:
    return ElementContext(
        parent_class="EmailService",
        element_kind="method",
        element_name="send_email",
    )


@pytest.fixture
def function_context() -> ElementContext:
    return ElementContext(
        parent_class=None,
        element_kind="function",
        element_name="process",
    )


# ── 1. Missing self insertion ───────────────────────────────────────────


class TestMissingSelfInsertion:

    def test_insert_self_no_params(self, method_context):
        """def send_email() → def send_email(self)."""
        code = "def send_email():\n    return True"
        result, fixes = _fix_missing_self(code, method_context)
        assert "def send_email(self):" in result
        assert len(fixes) == 1
        assert "self" in fixes[0]

    def test_insert_self_with_params(self, method_context):
        """def send_email(client, addr) → def send_email(self, client, addr)."""
        code = "def send_email(client, email_address, content):\n    return True"
        result, fixes = _fix_missing_self(code, method_context)
        assert "def send_email(self, client, email_address, content):" in result
        assert len(fixes) == 1

    def test_self_already_present(self, method_context):
        """No change when self is already there."""
        code = "def send_email(self, addr):\n    return True"
        result, fixes = _fix_missing_self(code, method_context)
        assert result == code
        assert len(fixes) == 0

    def test_classmethod_inserts_cls(self, method_context):
        """@classmethod without cls gets cls inserted."""
        code = "@classmethod\ndef from_config(path: str):\n    return EmailService()"
        result, fixes = _fix_missing_self(code, method_context)
        assert "def from_config(cls, path: str):" in result
        assert "cls" in fixes[0]

    def test_staticmethod_skipped(self, method_context):
        """@staticmethod should not get self/cls."""
        code = "@staticmethod\ndef validate(data: dict):\n    return bool(data)"
        result, fixes = _fix_missing_self(code, method_context)
        assert result == code
        assert len(fixes) == 0

    def test_function_context_skipped(self, function_context):
        """Standalone functions should not get self inserted."""
        code = "def process(data):\n    return data"
        result, fixes = _fix_missing_self(code, function_context)
        assert result == code
        assert len(fixes) == 0

    def test_no_context_skipped(self):
        """No element context → no changes."""
        code = "def foo():\n    pass"
        result, fixes = _fix_missing_self(code, None)
        assert result == code

    def test_multiple_methods_fixed(self, method_context):
        """Multiple methods in one file all get self."""
        code = (
            "class EmailService:\n"
            "    def send(addr):\n"
            "        return True\n"
            "    def validate(data):\n"
            "        return bool(data)\n"
        )
        result, fixes = _fix_missing_self(code, method_context)
        assert "def send(self, addr):" in result
        assert "def validate(self, data):" in result
        assert len(fixes) == 2


# ── 2. datetime module/class disambiguation ─────────────────────────────


class TestDatetimeConfusion:

    def test_module_import_fixed(self):
        """datetime.utcfromtimestamp → datetime.datetime.utcfromtimestamp."""
        code = (
            "import datetime\n"
            "\n"
            "def fmt(ts):\n"
            "    return datetime.utcfromtimestamp(ts).strftime('%Y')\n"
        )
        result, fixes = _fix_datetime_confusion(code)
        assert "datetime.datetime.utcfromtimestamp" in result
        assert len(fixes) == 1

    def test_class_import_not_touched(self):
        """from datetime import datetime → already correct."""
        code = (
            "from datetime import datetime\n"
            "\n"
            "def fmt(ts):\n"
            "    return datetime.utcfromtimestamp(ts).strftime('%Y')\n"
        )
        result, fixes = _fix_datetime_confusion(code)
        assert result == code
        assert len(fixes) == 0

    def test_no_datetime_import_skipped(self):
        """No datetime import → don't touch anything."""
        code = "def fmt(ts):\n    return str(ts)\n"
        result, fixes = _fix_datetime_confusion(code)
        assert result == code

    def test_multiple_methods_fixed(self):
        """Multiple datetime class methods all get fixed."""
        code = (
            "import datetime\n"
            "\n"
            "def a():\n"
            "    return datetime.utcnow()\n"
            "\n"
            "def b(ts):\n"
            "    return datetime.fromtimestamp(ts)\n"
        )
        result, fixes = _fix_datetime_confusion(code)
        assert "datetime.datetime.utcnow" in result
        assert "datetime.datetime.fromtimestamp" in result
        assert len(fixes) == 2

    def test_datetime_timedelta_not_touched(self):
        """datetime.timedelta is NOT a class method — don't change it."""
        code = (
            "import datetime\n"
            "\n"
            "def get_delta():\n"
            "    return datetime.timedelta(days=1)\n"
        )
        result, fixes = _fix_datetime_confusion(code)
        assert result == code
        assert len(fixes) == 0


# ── 3. Full step integration ────────────────────────────────────────────


class TestSemanticMethodFixStep:

    def test_step_name(self, step):
        assert step.name == "semantic_method_fix"

    def test_both_fixes_applied(self, step, method_context):
        """Step applies both self-insertion and datetime fix."""
        code = (
            "import datetime\n"
            "\n"
            "class EmailService:\n"
            "    def format_time(ts: float) -> str:\n"
            "        return datetime.utcfromtimestamp(ts).strftime('%Y')\n"
        )
        ctx = RepairContext(element_context=method_context)
        result = step(code, ctx, Path("email_server.py"), method_context)
        assert result.modified is True
        assert "def format_time(self, ts: float)" in result.code
        assert "datetime.datetime.utcfromtimestamp" in result.code

    def test_no_changes_returns_unmodified(self, step, method_context):
        """Clean code returns modified=False."""
        code = "def send_email(self, addr):\n    return True"
        ctx = RepairContext(element_context=method_context)
        result = step(code, ctx, Path("email_server.py"), method_context)
        assert result.modified is False
        assert result.code == code
