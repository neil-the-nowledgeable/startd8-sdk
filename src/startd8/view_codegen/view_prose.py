"""View-prose manifest (view-*chrome* copy: title/intro) — authored, kept OUTSIDE the drift hash.

The words a user reads on a composite view (the ``<h1>`` title, a short intro paragraph) are authored
in a standalone ``view_prose.yaml`` keyed by view name, rendered at **generate** time into an untracked
fragment (``app/templates/views/_<name>.prose.html``) that the owned view template ``{% include %}``s.

Hash-exemption is achieved exactly like ``pages.yaml`` → ``app/pages/*.md`` and ``ai_passes.yaml`` →
``app/ai/passes/*.md`` — by **architectural separation, not selective hashing** (the whole ``views.yaml``
is hashed; there is no subset-of-keys hashing). Two consequences:

- The owned template gains the ``{% include %}`` **only when prose exists for that view**, so a project
  with no ``view_prose.yaml`` renders **byte-identical** to today (the include line is content-
  independent — it never names the title text — so editing copy only rewrites the untracked fragment and
  never trips ``--check``). Adding/removing a view's prose entry is a structural regen, correctly caught.
- The fragment carries **no provenance header**, so it is not an "owned view file" and is skipped by
  drift/`--check`; it is overwritten on every regenerate.

Distinct from the ``rendered-content`` archetype's ``prose_key`` / ``app/views/_prose.py`` (which renders
an *entity's text column*). This is *view-chrome* copy; the standalone file + ``ViewProse`` type keep the
two "prose" concepts uncollided.

**Phase 1 keys:** ``title``, ``intro``. **Phase 2 (this increment):** ``empty`` — the no-rows panel
state, archetype-specific (only ``detail-compose`` *model* scope has a clean surface today, so ``empty``
on any other archetype loud-fails in :func:`render_views`). The remaining Phase-2 keys (``controls``,
``success``, ``error``) still need a render surface (stable control ids; an HTML outcome surface) and
stay **reserved**: present-but-unbuilt → loud-fail, so nobody authors against a surface that isn't there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import yaml

# View-chrome keys rendered into the untracked fragment. ``title``/``intro`` (Phase 1) live in the
# heading fragment; ``empty`` (Phase 2) renders into its own no-rows fragment and is valid only on
# archetypes that expose a no-rows surface (enforced per-view in render_views, which knows the kind).
_PROSE_KEYS = {"title", "intro", "empty"}
# Still-reserved (Phase-2-pending) keys — each awaits a render surface; present ⇒ loud-fail
# (reserved-until-built, mirroring the SDK's `filters:`/`forms:` reserved-key policy). See PLAN §2.
_RESERVED_KEYS = {"controls", "success", "error"}


@dataclass(frozen=True)
class ViewProse:
    """View-chrome copy for a single composite view (title/intro = Phase 1; empty = Phase 2)."""

    title: Optional[str] = None
    intro: Optional[str] = None
    empty: Optional[str] = None


def parse_view_prose(
    text: Optional[str], *, known_views: frozenset = frozenset()
) -> Dict[str, ViewProse]:
    """Parse + **strictly** validate ``view_prose.yaml`` → ``{view_name: ViewProse}``.

    Tolerant of absence (``None`` / empty / no file ⇒ ``{}`` ⇒ today's behavior). Loud-fails (``ValueError``,
    caught centrally by the CLI) on: a non-mapping root, a non-mapping per-view entry, **reserved Phase-2
    keys present**, unknown keys, a view name not in *known_views* (when given), and non-string values.
    Mirrors the ``parse_pages`` / ``parse_filters`` strict contract.
    """
    if text is None:
        return {}
    data = yaml.safe_load(text or "") or {}
    if not data:
        return {}
    if not isinstance(data, dict):
        raise ValueError("view_prose.yaml must be a mapping of view-name -> prose")
    out: Dict[str, ViewProse] = {}
    for name, spec in data.items():
        view = str(name)
        if known_views and view not in known_views:
            raise ValueError(f"view_prose.yaml: references unknown view {view!r}")
        if not isinstance(spec, dict):
            raise ValueError(f"view_prose.yaml: entry {view!r} must be a mapping")
        reserved = set(spec) & _RESERVED_KEYS
        if reserved:
            raise ValueError(
                f"view_prose.yaml: entry {view!r} uses reserved (not-yet-built) keys "
                f"{sorted(reserved)} — these ship in Phase 2 (each needs a render surface)"
            )
        unknown = set(spec) - _PROSE_KEYS
        if unknown:
            raise ValueError(
                f"view_prose.yaml: entry {view!r} has unknown keys {sorted(unknown)}"
            )
        vals: Dict[str, str] = {}
        for key in _PROSE_KEYS:
            val = spec.get(key)
            if val is None:
                continue
            if not isinstance(val, str):
                raise ValueError(
                    f"view_prose.yaml: entry {view!r} key {key!r} must be a string"
                )
            vals[key] = val
        if vals:  # an entry with no recognized values is inert (no fragment, byte-identical output)
            out[view] = ViewProse(**vals)
    return out
