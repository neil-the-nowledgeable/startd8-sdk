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


# The end-user is the primary reader of the HTML preview (FR-AUD-2), so it defaults to the plain,
# non-technical voice; the terminal `--describe` keeps the architect base. Where an end_user variant
# isn't authored yet, the resolver degrades to base (FR-AUD-1) — no blank narration.
DEFAULT_HTML_ROLE = "end_user"
DEFAULT_HTML_FLUENCY = "beginner"


def render_html(
    plan: WireframePlan,
    *,
    role: str = DEFAULT_HTML_ROLE,
    fluency: str = DEFAULT_HTML_FLUENCY,
) -> str:
    """The standalone offline HTML preview for ``plan`` — deterministic, no external assets.

    Defaults to the end-user audience (FR-AUD-2); ``role``/``fluency`` change only the wording."""
    view_model = compose(plan, role=role, fluency=fluency)
    return (
        WIREFRAME_VIEW_TEMPLATE
        .replace("__EXPECTED_SCHEMA__", str(EXPECTED_SCHEMA_VERSION))
        .replace("__PLAN_DATA__", _embed_json(view_model))
    )


def render_to_file(
    plan: WireframePlan,
    path: Path,
    *,
    role: str = DEFAULT_HTML_ROLE,
    fluency: str = DEFAULT_HTML_FLUENCY,
) -> Path:
    """Write the preview atomically (temp + rename); create the parent dir. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(render_html(plan, role=role, fluency=fluency), encoding="utf-8")
    os.replace(tmp, path)
    return path
