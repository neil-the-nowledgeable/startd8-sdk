"""``howto_codegen`` — the det-howto projector (the third det-doc-kit projector).

A ``$0``, LLM-free, pure projection of a REQ's declared command surface → a det-howto/0.1 command
reference (SCHEMA_det-howto-0.1). Built strictly from ``STANDARD_det-doc-kit-projector-pattern.md``'s
5-part shape + the Part-6 honesty behaviors:

- ``projector.py`` — ``project_howto`` (pure; gate raises ``NotHowtoOwedError``);
- ``render.py`` — ``render_howto`` (idempotent, no timestamps, ``GENERATED_MARKER``);
- ``conformance.py`` — ``validate_howto`` + ``findings_to_sarif`` (imports the ONE SARIF renderer);
- ``provider.py`` — ``DetHowtoProjectorProvider`` (deterministic-file provider).
"""

from __future__ import annotations

from .conformance import findings_to_sarif, validate_howto
from .models import (
    COMPANION_KIND,
    FORMAT_VERSION,
    INITIAL_MATURITY,
    Command,
    Howto,
    HowtoFinding,
    Prerequisite,
)
from .projector import NotHowtoOwedError, project_howto
from .provider import DetHowtoProjectorProvider
from .render import GENERATED_MARKER, render_howto

__all__ = [
    "Command",
    "Prerequisite",
    "Howto",
    "HowtoFinding",
    "FORMAT_VERSION",
    "COMPANION_KIND",
    "INITIAL_MATURITY",
    "project_howto",
    "NotHowtoOwedError",
    "render_howto",
    "GENERATED_MARKER",
    "validate_howto",
    "findings_to_sarif",
    "DetHowtoProjectorProvider",
]
