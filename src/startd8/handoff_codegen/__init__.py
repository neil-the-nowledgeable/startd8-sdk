"""``$0`` REQ+ledger → det-handoff/0.1 projector — the SECOND det-doc-kit projector.

Built against ``STANDARD_det-doc-kit-projector-pattern.md`` (the real ``/reflective-adoption`` gate),
mirroring ``plan_codegen``. The kit (``SCHEMA_det-handoff-0.1``) owns the format; this package is the
cited generator, registered as a deterministic provider.
"""

from __future__ import annotations

from .conformance import findings_to_sarif, validate_handoff
from .models import BuildStep, Handoff, HandoffFinding, Prerequisite
from .projector import NotHandoffOwedError, is_handoff_owed, project_handoff
from .provider import DetHandoffProjectorProvider
from .render import GENERATED_MARKER, render_handoff

__all__ = [
    "Handoff",
    "BuildStep",
    "Prerequisite",
    "HandoffFinding",
    "NotHandoffOwedError",
    "is_handoff_owed",
    "project_handoff",
    "render_handoff",
    "GENERATED_MARKER",
    "validate_handoff",
    "findings_to_sarif",
    "DetHandoffProjectorProvider",
]
