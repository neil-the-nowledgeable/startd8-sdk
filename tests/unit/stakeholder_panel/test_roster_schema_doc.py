# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""ROSTER_SCHEMA.md drift guard (FR-1 / R2-F2): the doc's field lists must equal the models."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import yaml

from startd8.stakeholder_panel.models import PersonaBrief
from startd8.stakeholder_panel.roster import PERSONA_KEYS, TOPLEVEL_KEYS

_SCHEMA_DOC = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "design"
    / "stakeholder-panel"
    / "ROSTER_SCHEMA.md"
)
_MARKER = "ROSTER-SCHEMA-FIELDS"


def _machine_block() -> dict:
    text = _SCHEMA_DOC.read_text(encoding="utf-8")
    # The marker HTML comment is immediately followed by a ```yaml … ``` fenced block.
    m = re.search(rf"{_MARKER}.*?```yaml\n(.*?)```", text, re.DOTALL)
    assert m, f"machine-readable {_MARKER} block not found in {_SCHEMA_DOC.name}"
    return yaml.safe_load(m.group(1))


def test_schema_doc_persona_fields_match_the_model():
    block = _machine_block()
    doc_fields = set(block["persona_fields"])
    model_fields = {f.name for f in dataclasses.fields(PersonaBrief)}
    assert doc_fields == model_fields == set(PERSONA_KEYS)


def test_schema_doc_top_level_keys_match_the_allow_set():
    block = _machine_block()
    assert set(block["roster_top_level_keys"]) == set(TOPLEVEL_KEYS)
