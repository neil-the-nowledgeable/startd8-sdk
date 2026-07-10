"""Central registry of the kickoff read-model schema identifiers.

One home for every ``startd8.kickoff.*`` payload schema string, so a producer and its consumers
(CLI ``--json``, the MCP tools, tests) reference the SAME constant instead of re-typing the literal.
Before this, the CLI hardcoded ledger/exemplar literals that module constants *also* defined — the
kind of drift a single source of truth removes.
"""

from __future__ import annotations

STATUS = "startd8.kickoff.status.v1"
ACTIVATION = "startd8.kickoff.activation.v1"
ACTIVATION_LEDGER = "startd8.kickoff.activation-ledger.v1"
RETROSPECTIVE = "startd8.kickoff.retrospective.v1"
EXEMPLAR = "startd8.kickoff.exemplar.v1"
#: The combined, shareable single artifact `kickoff readout --full` emits: status + retrospective
#: ("how we got here") + activation ("what's left"), each nested under its own key.
READOUT = "startd8.kickoff.readout.v1"
