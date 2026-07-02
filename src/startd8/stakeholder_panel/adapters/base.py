# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Persona-format ingestion adapter contract (FR-3/FR-9).

An **adapter** converts one *external* persona format into a native :class:`Roster` — one-way
(external → roster). The contract is deliberately minimal:

    class MyAdapter:
        name = "my-format"
        def adapt(self, text: str) -> AdaptResult: ...

``adapt`` returns an :class:`AdaptResult` carrying the roster **plus a ``warnings`` channel** (empty
for a lossless adapter). Reserving warnings now (R1-F6) means a future *lossy* adapter can report
dropped fields without a breaking signature change to every registered adapter. A malformed source or
an unknown format raises :class:`AdapterError` — distinct from :class:`~startd8.stakeholder_panel.roster.RosterError`
(a structurally-invalid *roster document*), per the FR-9 error taxonomy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

try:  # Protocol is 3.8+; guard for very old typing just in case
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    from typing_extensions import Protocol, runtime_checkable  # type: ignore

from startd8.stakeholder_panel.models import Roster

__all__ = ["AdapterError", "AdaptResult", "Adapter"]


class AdapterError(ValueError):
    """The source format is malformed, or the requested ``--format`` is unknown (FR-9).

    Distinct from ``RosterError`` (an invalid *roster document*): an ``AdapterError`` says "your
    *source* is wrong or the adapter can't handle it", not "the produced roster is malformed".
    """


@dataclass(frozen=True)
class AdaptResult:
    """The output of an adapter: a native roster + a (v1-empty) diagnostics channel (R1-F6)."""

    roster: Roster
    warnings: List[str] = field(default_factory=list)


@runtime_checkable
class Adapter(Protocol):
    """A persona-format adapter. ``name`` is the ``--format`` slug; ``adapt`` does the conversion."""

    name: str

    def adapt(self, text: str) -> AdaptResult: ...
