"""DeterministicFileAssembler typing-import completion (OQ-8 / run-039 fix).

A rendered skeleton whose signatures reference typing names (`-> List[Dict]`) must import them,
or it fails type-check AND breaks FastAPI/SQLModel `get_type_hints` at runtime.
"""

from __future__ import annotations

import re

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature
from startd8.utils.file_assembler import DeterministicFileAssembler

pytestmark = pytest.mark.unit


def _typing_line(src: str) -> str:
    for line in src.splitlines():
        if line.strip().startswith("from typing import"):
            return line.strip()
    return ""


def _func(name, return_annotation=None, params=None):
    return ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name=name,
        signature=Signature(params=params or [], return_annotation=return_annotation),
    )


def test_return_annotation_typing_names_completed():
    fs = ForwardFileSpec(
        file="app/jobs.py",
        imports=[ForwardImportSpec(kind="from", module="typing", names=["Any"])],
        elements=[_func("resolve_matches", return_annotation="List[Dict]")],
    )
    src = DeterministicFileAssembler().render_file(fs)
    line = _typing_line(src)
    assert "Dict" in line and "List" in line and "Any" in line, line
    # exactly one merged typing import line (no duplicates)
    assert len(re.findall(r"^from typing import", src, re.M)) == 1


def test_param_annotation_typing_names_completed():
    fs = ForwardFileSpec(
        file="app/x.py",
        imports=[],
        elements=[_func("f", params=[Param(name="x", annotation="Optional[int]")])],
    )
    assert "Optional" in _typing_line(DeterministicFileAssembler().render_file(fs))


def test_domain_name_not_shadowed_by_typing():
    # `Match` is a domain entity from app.tables — must NOT become `from typing import Match`.
    fs = ForwardFileSpec(
        file="app/jobs.py",
        imports=[ForwardImportSpec(kind="from", module="app.tables", names=["Match"])],
        elements=[_func("resolve", return_annotation="List[Match]")],
    )
    src = DeterministicFileAssembler().render_file(fs)
    typing_line = _typing_line(src)
    assert "List" in typing_line          # the real typing name is completed
    assert "Match" not in typing_line     # the domain name is NOT pulled into typing
    assert "from app.tables import Match" in src  # it stays resolved from its real module


def test_no_typing_usage_adds_no_typing_import():
    fs = ForwardFileSpec(
        file="app/x.py",
        imports=[ForwardImportSpec(kind="from", module="app.db", names=["get_session"])],
        elements=[_func("f", return_annotation="int", params=[Param(name="x", annotation="str")])],
    )
    src = DeterministicFileAssembler().render_file(fs)
    assert _typing_line(src) == ""  # no spurious typing import
