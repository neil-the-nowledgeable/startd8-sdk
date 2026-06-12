"""Drift / in-sync checking for composite-view artifacts (two-input: schema + views.yaml).

Verification re-renders the **whole** view set from (schema, views.yaml) and byte-compares the file
at the given path — simpler than per-view re-render dispatch, and correct because the renderers are
deterministic. A view file is owned iff it carries the two-hash GENERATED header; in-sync iff its
bytes match a fresh render. Any doubt → ``False`` (caller falls through to the LLM — safe failure).
"""

from __future__ import annotations

from pathlib import Path

_MARKER = "# GENERATED from prisma/schema.prisma (+ views.yaml)"


def is_owned_view_file(text: str) -> bool:
    t = text or ""
    return _MARKER in t and "views-sha256:" in t


def views_in_sync(
    schema_text: str, views_text: str, path, ondisk_text: str, display_text=None,
    view_prose_text=None,
) -> bool:
    """True iff *ondisk_text* at *path* matches a fresh render of (schema, views.yaml[, display.yaml,
    view_prose.yaml]).

    *view_prose_text* must be threaded so the re-render reproduces the ``{% include %}`` an owned
    template carries when its view has prose — otherwise a prose-annotated view would false-flag as
    drift. Prose *content* never affects the owned template (only its presence does), so editing copy
    still leaves ``--check`` green; this argument only carries presence/structure.
    """
    if not is_owned_view_file(ondisk_text):
        return False
    from .renderers import render_views

    try:
        rendered = render_views(schema_text, views_text, display_text, view_prose_text)
    except ValueError:
        return False
    tail = Path(path).as_posix()
    for rel, content in rendered:
        if tail.endswith(rel):
            return content == ondisk_text
    return False
