# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for reflective Phase 4.5 / 4.6 lightweight harden gate."""

from startd8.workflows.loop_queue.reflective_hardening import (
    reflective_hardening_gaps,
)

_HARDENED = """# Feature Requirements

**Version:** 0.3.1 (Post design-principle hardening)

## 0. Planning Insights
| v0.1 | Discovery | Impact |
|------|-----------|--------|

### 0.1 Lessons-Learned Hardening (v0.3)

> Checked sdk lessons; none applicable.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked design principles; applied Mottainai.

## 2. Requirements
FR-1. Do the thing.
"""


def test_hardened_doc_passes():
    assert reflective_hardening_gaps(_HARDENED) == []


def test_bare_draft_fails():
    gaps = reflective_hardening_gaps("# Requirements\n\nFR-1.\n")
    assert any("4.5" in g for g in gaps)
    assert any("4.6" in g for g in gaps)


def test_sections_without_version_pass():
    text = """# Reqs

### 0.1 Lessons-Learned Hardening (v0.3)
Applied phantom-reference-audit.

### 0.2 Design-Principle Hardening (v0.3.1)
Applied Genchi Genbutsu.
"""
    assert reflective_hardening_gaps(text) == []


def test_explicit_noop_checks_pass():
    text = """
**Version:** 0.3.1

Checked the lessons index; none applicable.
Checked the design-principle index; none applicable.
"""
    assert reflective_hardening_gaps(text) == []
