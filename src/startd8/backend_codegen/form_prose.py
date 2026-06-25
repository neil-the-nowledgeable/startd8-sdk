"""Form-prose manifest (the form **Words layer**: per-field help/placeholder + per-form intro).

The words a user reads *at the point of data entry* — a per-field help line ("Amount in dollars,
e.g. 42.00"), an input placeholder, and a per-form intro paragraph — are authored in a standalone
``form_prose.yaml`` keyed by entity, parallel to ``view_prose.yaml`` (the view Words layer). Help/intro
render at **generate** time into untracked, headerless fragments
(``app/templates/<entity>/_help_<field>.html`` and ``app/templates/<entity>/_form_intro.html``) that
the owned form template ``{% include %}``s. Mirrors the ``view_prose.yaml`` invariants exactly:

- **Hash-exempt (SOTTO, FR-FH-3).** The owned ``<entity>/form.html`` gains the ``{% include %}`` (and an
  ``aria-describedby`` reference) **only when prose exists** for that field/form. The include line is
  **content-independent** — it names the field id, never the help *words* — so editing copy only rewrites
  the untracked fragment and never trips ``generate backend --check``. The fragment carries no provenance
  header, so it is not an "owned file" and is skipped by drift (the ``app/pages/*.md`` precedent).
- **Byte-identical when absent (FR-FH-4).** No ``form_prose.yaml`` ⇒ forms render exactly as today.
- **Placeholder is structural.** Unlike ``help``/``intro``, a ``placeholder`` is an attribute on the
  owned ``<input>`` (FR-FH-3 names only help/intro as the hash-exempt Words layer); editing a placeholder
  value is a structural regen, correctly caught by ``--check``.

Distinct from ``forms_manifest`` (``forms:`` in ``views.yaml``, which carries ``on_create`` behavior) and
from ``display.yaml`` (the hashed Structure layer: labels/columns/sections). Help is *copy*
(author→approve), so it lives in its own Words file (D-FH-1), keeping the Words/Structure split clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Dict, Optional

import yaml


@dataclass(frozen=True)
class FormFieldProse:
    """Authored help copy for one form field. Either part may be omitted."""

    help: Optional[str] = None         # persistent description, wired as aria-describedby (hash-exempt)
    placeholder: Optional[str] = None  # in-field example hint, a structural <input> attribute


@dataclass(frozen=True)
class FormProse:
    """The form Words layer for one entity: a per-form ``intro`` + per-field help/placeholder."""

    intro: Optional[str] = None
    fields: Dict[str, FormFieldProse] = _dc_field(default_factory=dict)


def parse_form_prose(
    text: Optional[str],
    *,
    known_entities: frozenset = frozenset(),
    known_fields: Optional[Dict[str, frozenset]] = None,
) -> Dict[str, FormProse]:
    """Parse + **strictly** validate ``form_prose.yaml`` → ``{entity: FormProse}``.

    Tolerant of absence (``None`` / empty / no file ⇒ ``{}`` ⇒ today's behavior). Loud-fails (``ValueError``,
    caught centrally by the CLI) on: a non-mapping root, an unknown top-level key (only ``forms`` is
    allowed), a non-mapping ``forms`` / per-entity / per-field entry, unknown keys, an entity not in
    *known_entities*, a field not in *known_fields[entity]* (the dangling-target guard, FR-FH-5), and a
    non-string ``intro``/``help``/``placeholder``. Mirrors the ``parse_view_prose`` strict contract.
    """
    if text is None:
        return {}
    data = yaml.safe_load(text or "") or {}
    if not data:
        return {}
    if not isinstance(data, dict):
        raise ValueError("form_prose.yaml must be a mapping with a top-level 'forms' key")
    unknown_top = set(data) - {"forms"}
    if unknown_top:
        raise ValueError(
            f"form_prose.yaml: unknown top-level keys {sorted(unknown_top)} (expected 'forms')"
        )
    forms = data.get("forms") or {}
    if not isinstance(forms, dict):
        raise ValueError("form_prose.yaml: 'forms' must be a mapping of entity -> form prose")

    out: Dict[str, FormProse] = {}
    for ename, spec in forms.items():
        entity = str(ename)
        if known_entities and entity not in known_entities:
            raise ValueError(f"form_prose.yaml: references unknown entity {entity!r}")
        if not isinstance(spec, dict):
            raise ValueError(f"form_prose.yaml: entry {entity!r} must be a mapping")
        unknown = set(spec) - {"intro", "fields"}
        if unknown:
            raise ValueError(
                f"form_prose.yaml: entry {entity!r} has unknown keys {sorted(unknown)} "
                "(allowed: intro, fields)"
            )
        intro = spec.get("intro")
        if intro is not None and not isinstance(intro, str):
            raise ValueError(f"form_prose.yaml: entry {entity!r} `intro` must be a string")

        fields_spec = spec.get("fields") or {}
        if not isinstance(fields_spec, dict):
            raise ValueError(
                f"form_prose.yaml: entry {entity!r} `fields` must be a mapping of field -> help"
            )
        kf = known_fields.get(entity) if known_fields else None
        fields: Dict[str, FormFieldProse] = {}
        for fname, fval in fields_spec.items():
            fld = str(fname)
            if kf is not None and fld not in kf:
                raise ValueError(
                    f"form_prose.yaml: entry {entity!r} references unknown form field {fld!r}"
                )
            if not isinstance(fval, dict):
                raise ValueError(
                    f"form_prose.yaml: entry {entity!r} field {fld!r} must be a "
                    "{help, placeholder} mapping"
                )
            extra = set(fval) - {"help", "placeholder"}
            if extra:
                raise ValueError(
                    f"form_prose.yaml: entry {entity!r} field {fld!r} has unknown keys "
                    f"{sorted(extra)} (allowed: help, placeholder)"
                )
            help_text = fval.get("help")
            placeholder = fval.get("placeholder")
            for key, val in (("help", help_text), ("placeholder", placeholder)):
                if val is not None and not isinstance(val, str):
                    raise ValueError(
                        f"form_prose.yaml: entry {entity!r} field {fld!r} `{key}` must be a string"
                    )
            if help_text is not None or placeholder is not None:
                fields[fld] = FormFieldProse(help=help_text, placeholder=placeholder)

        if intro is not None or fields:  # an inert entry (no copy) emits no fragments → byte-identical
            out[entity] = FormProse(intro=intro, fields=fields)
    return out
