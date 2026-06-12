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

**Phase 1 keys:** ``title``, ``intro``. **Phase 2 (incremental):** ``empty`` (the no-rows panel state,
only on a model-scoped ``detail-compose``); ``success``/``error`` (import-flow **restore** outcome copy,
rendered into an HTML result page with request-time substitution of a closed placeholder set);
``controls`` (a mapping ``control-id → label`` for an archetype's buttons — import-flow
``validate``/``restore``/``confirm``). Each control label renders into an untracked fragment the template
``{% include %}``s, **gated on presence** — so no HTML-id stamping and no downstream drift; the
control-id is the manifest key (the SDK's known per-archetype enum), not an HTML attribute. All
archetype/control-id validity is enforced per-view in :func:`render_views` (which knows the kind).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import yaml

# String-valued authorable keys. Each renders into an untracked fragment; archetype/placeholder validity
# is enforced in render_views (the parser is archetype-blind — it only knows view names). ``title``/
# ``intro`` → heading fragment; ``empty`` → no-rows fragment (model-compose); ``success``/``error`` →
# import-flow restore-outcome fragments. ``controls`` is a mapping (handled separately below).
_PROSE_KEYS = {"title", "intro", "empty", "success", "error"}
_ALLOWED_KEYS = _PROSE_KEYS | {"controls"}


@dataclass(frozen=True)
class ViewProse:
    """View-chrome copy for one composite view (title/intro = Phase 1; empty/success/error/controls = Phase 2)."""

    title: Optional[str] = None
    intro: Optional[str] = None
    empty: Optional[str] = None
    success: Optional[str] = None
    error: Optional[str] = None
    controls: Optional[Dict[str, Dict[str, str]]] = None  # control-id -> {label, help?} (validity in render_views)


def parse_view_prose(
    text: Optional[str], *, known_views: frozenset = frozenset()
) -> Dict[str, ViewProse]:
    """Parse + **strictly** validate ``view_prose.yaml`` → ``{view_name: ViewProse}``.

    Tolerant of absence (``None`` / empty / no file ⇒ ``{}`` ⇒ today's behavior). Loud-fails (``ValueError``,
    caught centrally by the CLI) on: a non-mapping root, a non-mapping per-view entry, unknown keys, a
    view name not in *known_views* (when given), a non-string value, and a malformed ``controls`` mapping.
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
        unknown = set(spec) - _ALLOWED_KEYS
        if unknown:
            raise ValueError(
                f"view_prose.yaml: entry {view!r} has unknown keys {sorted(unknown)}"
            )
        vals: Dict[str, object] = {}
        for key in _PROSE_KEYS:
            val = spec.get(key)
            if val is None:
                continue
            if not isinstance(val, str):
                raise ValueError(
                    f"view_prose.yaml: entry {view!r} key {key!r} must be a string"
                )
            vals[key] = val
        controls = spec.get("controls")
        if controls is not None:
            if not isinstance(controls, dict):
                raise ValueError(
                    f"view_prose.yaml: entry {view!r} `controls` must be a mapping of control-id -> label"
                )
            cvals: Dict[str, Dict[str, str]] = {}
            for cid, cval in controls.items():
                cid = str(cid)
                if isinstance(cval, str):                      # shorthand: control-id -> label
                    cvals[cid] = {"label": cval}
                elif isinstance(cval, dict):                   # full form: { label, help? }
                    extra = set(cval) - {"label", "help"}
                    if extra:
                        raise ValueError(
                            f"view_prose.yaml: entry {view!r} control {cid!r} has unknown keys "
                            f"{sorted(extra)} (allowed: label, help)"
                        )
                    label = cval.get("label")
                    if not isinstance(label, str):
                        raise ValueError(
                            f"view_prose.yaml: entry {view!r} control {cid!r} requires a string `label`"
                        )
                    entry = {"label": label}
                    help_text = cval.get("help")
                    if help_text is not None:
                        if not isinstance(help_text, str):
                            raise ValueError(
                                f"view_prose.yaml: entry {view!r} control {cid!r} `help` must be a string"
                            )
                        entry["help"] = help_text
                    cvals[cid] = entry
                else:
                    raise ValueError(
                        f"view_prose.yaml: entry {view!r} control {cid!r} must be a label string "
                        "or a {label, help} mapping"
                    )
            if cvals:
                vals["controls"] = cvals
        if vals:  # an entry with no recognized values is inert (no fragment, byte-identical output)
            out[view] = ViewProse(**vals)
    return out
