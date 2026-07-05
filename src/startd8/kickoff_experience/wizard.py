# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Compat shim (GE-M2) — the Red Carpet wizard now lives in the ``orchestrator`` conductor.

GE-M2 consolidated the three "what's next" projections (``orchestrator`` + ``wizard`` +
``red_carpet_completion``) into one conductor module (``orchestrator``). This module re-exports the
wizard surface so the legacy import path ``from startd8.kickoff_experience.wizard import …`` keeps
working for one release. Prefer importing from ``orchestrator`` directly.

The NR-4a anti-import security property is enforced by the structural guard test against the
conductor module (``orchestrator``), where the real wizard code now lives.
"""

from __future__ import annotations

from .orchestrator import (  # noqa: F401
    _BRIEF_REL,
    _DERIVE_COMMAND,
    WizardAction,
    _instantiate_proposal,
    _package_present,
    _prefill_actions,
    _read_text,
    run_red_carpet_driver,
    wizard_inventory,
    wizard_prepopulate,
)

__all__ = [
    "WizardAction",
    "wizard_inventory",
    "wizard_prepopulate",
    "run_red_carpet_driver",
]
