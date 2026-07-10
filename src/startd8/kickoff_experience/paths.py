"""The single home for the kickoff/project-start on-disk store layout.

Every store location under a project's ``.startd8/`` root was previously re-typed as a bare literal
(the ``.startd8`` string alone appears 100+ times across the SDK). This module owns the **root** and
the **well-known subdir names**, so a subsystem builds its paths on ``startd8_dir(root)`` instead of
re-typing the literal — and renaming the store root or a subdir becomes a one-line change.

**Ownership is preserved (SOTTO — don't disturb what exists).** Each subsystem keeps its own path
helper for the *files* it owns (``activation.ledger_path``, ``session_snapshot.snapshot_path``,
``promotion.exemplars_dir``, ``vipp_seam.inbox_path``); those helpers now *build on* ``startd8_dir``
rather than re-typing ``.startd8``. This module does not centralise filenames a single module owns.
"""

from __future__ import annotations

from pathlib import Path

#: The project-local store root. One definition; do not re-type the literal elsewhere.
STARTD8_DIRNAME = ".startd8"

# Well-known subdir names under the store root (each used by ≥1 subsystem). Filenames stay with their
# owning module.
KICKOFF = "kickoff"                       # activation-ledger.jsonl, agentic-session.json
VIPP = "vipp"                             # proposals-inbox.json, dispositions.json (owner: vipp_seam)
DASHBOARDS = "dashboards"                 # generated Grafana dashboard JSON
EXEMPLARS = "kickoff-exemplars"           # promoted-kickoff registry (owner: promotion)
KICKOFF_PANEL = "kickoff-panel"           # facilitator synthesis transcripts
KICKOFF_SCRATCH = "kickoff-scratch"       # serve scratch space
STAKEHOLDER_PANEL = "stakeholder-panel"   # panel proposals
STAKEHOLDER_RUN = "stakeholder-run"       # stakeholder-run endpoint state


def startd8_dir(project_root: str | Path) -> Path:
    """The ``.startd8`` store root for a project. The one place that names the store root."""
    return Path(project_root) / STARTD8_DIRNAME
