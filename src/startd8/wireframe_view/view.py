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
# non-technical voice at the STANDARD depth (intermediate = the approved role-base content). `beginner`
# (fuller) and `advanced` (terse) are opt-in via --fluency; fluency is authored for end_user only.
# Where a variant isn't authored, the resolver degrades to base (FR-AUD-1) — no blank narration.
DEFAULT_HTML_ROLE = "end_user"
DEFAULT_HTML_FLUENCY = "intermediate"


# QW-1: the audience variants embedded in every preview so the in-file toggle can switch voice/depth
# live (no regenerate). Deterministic + small; the section shape is identical across them (FR-AUD-4).
_EMBED_COMBOS = (
    ("end_user", "beginner"),
    ("end_user", "intermediate"),
    ("end_user", "advanced"),
    ("architect", "intermediate"),
)


def render_html(
    plan: WireframePlan,
    *,
    role: str = DEFAULT_HTML_ROLE,
    fluency: str = DEFAULT_HTML_FLUENCY,
) -> str:
    """The standalone offline HTML preview for ``plan`` — deterministic, no external assets.

    Embeds every audience variant (QW-1) with ``(role, fluency)`` as the default shown; the in-file
    toggle switches between them. Defaults to the end-user voice (FR-AUD-2)."""
    variants = {f"{r}|{f}": compose(plan, role=r, fluency=f) for r, f in _EMBED_COMBOS}
    default = f"{role}|{fluency}"
    if default not in variants:  # a requested combo we didn't pre-embed → include it
        variants[default] = compose(plan, role=role, fluency=fluency)
    payload = {"default": default, "variants": variants}
    return (
        WIREFRAME_VIEW_TEMPLATE
        .replace("__EXPECTED_SCHEMA__", str(EXPECTED_SCHEMA_VERSION))
        .replace("__PLAN_DATA__", _embed_json(payload))
    )


def view_model_json(
    plan: WireframePlan,
    *,
    role: str = DEFAULT_HTML_ROLE,
    fluency: str = DEFAULT_HTML_FLUENCY,
) -> str:
    """LH-2: the composed audience view-model as JSON — the FR-AUD benefit-first content *as data*, so
    other surfaces (a web app, the portal) can render it without the HTML. Deterministic; one variant
    per (role, fluency)."""
    return json.dumps(compose(plan, role=role, fluency=fluency), indent=2, sort_keys=True) + "\n"


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
