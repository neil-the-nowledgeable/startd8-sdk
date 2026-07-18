"""M-WV1 — render the composed view-model to a self-contained HTML file (FR-WV-1/6/7).

Mirrors ``kickoff_view.view.render_html``: a single escape-first substitution of the view-model into a
``<script type="application/json">`` container (neutralize ``<`` so a ``</script>`` inside any label
can't break out), plus the viewer's expected ``schema_version`` for the client-side drift guard.
Deterministic — same plan ⇒ byte-identical HTML (no timestamp in the body). Atomic file write.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..wireframe.plan import WireframePlan
from ..wireframe.render import SCHEMA_VERSION
from ._template import WIREFRAME_VIEW_TEMPLATE
from .compose import compose

# The schema_version this viewer's client renderer was written against. Kept in lockstep with the plan
# JSON contract by ``test_visual_html`` — if they drift, the client banners (FR-WV-7).
EXPECTED_SCHEMA_VERSION = SCHEMA_VERSION


def _embed_json(obj: dict) -> str:
    """Escape-first JSON embed (the kickoff_view seam): ASCII-safe + neutralize ``<``."""
    return json.dumps(obj, ensure_ascii=True, sort_keys=True).replace("<", "\\u003c")


def render_html(plan: WireframePlan) -> str:
    """The standalone offline HTML preview for ``plan`` — deterministic, no external assets."""
    view_model = compose(plan)
    return (
        WIREFRAME_VIEW_TEMPLATE
        .replace("__EXPECTED_SCHEMA__", str(EXPECTED_SCHEMA_VERSION))
        .replace("__PLAN_DATA__", _embed_json(view_model))
    )


def render_to_file(plan: WireframePlan, path: Path) -> Path:
    """Write the preview atomically (temp + rename); create the parent dir. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(render_html(plan), encoding="utf-8")
    os.replace(tmp, path)
    return path
