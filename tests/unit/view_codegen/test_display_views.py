"""Composite-view FK resolution — FR-DM-6 (display.yaml increment 2, the `neil-cpo-01` fix).

A model-compose view's relations resolve via_fk → target entity → label_field, so the rendered page
shows the target's LABEL, not the join-row id. Opt-in via display.yaml; absent ⇒ today's output.
"""

from __future__ import annotations

import pytest

from startd8.view_codegen.renderers import render_views

pytestmark = pytest.mark.unit

# Capability (root) → CapabilityOutcome (join: capabilityId, outcomeId) → Outcome (label = name).
SCHEMA = """
model Capability {
  id      String @id @default(cuid())
  ownerId String @default("local")
  name    String
}

model Outcome {
  id      String @id @default(cuid())
  ownerId String @default("local")
  name    String
}

model CapabilityOutcome {
  id           String @id @default(cuid())
  ownerId      String @default("local")
  capabilityId String
  outcomeId    String
}
""".strip()

VIEWS = """
views:
  - name: value_map
    kind: detail-compose
    scope: model
    root: Capability
    relations:
      - { name: outcomes, from: CapabilityOutcome, fk: capabilityId }
""".strip()

DISPLAY = """
views:
  value_map:
    root_label_field: name
    relations:
      - { name: outcomes, via_fk: outcomeId, label_field: name }
""".strip()


def _files(display=None):
    return dict(render_views(SCHEMA, VIEWS, display))


def test_data_fetch_resolves_join_row_to_target_label():
    mod = _files(DISPLAY)["app/views/value_map.py"]
    compile(mod, "<value_map>", "exec")
    assert "from app.tables import Capability, CapabilityOutcome, Outcome" in mod  # target imported
    assert "_t = session.get(Outcome, _tid)" in mod                                # FK → target
    assert "_tid = getattr(_j, 'outcomeId')" in mod
    assert "'label': getattr(_t, 'name', None) or _tid" in mod                      # → target label
    assert 'item["root_label"] = getattr(root, \'name\', None) or root.id' in mod   # root label


def test_template_renders_label_not_join_id():
    tpl = _files(DISPLAY)["app/templates/views/value_map.html"]
    assert "{{ item.root_label }}" in tpl          # heading = root's name, not neil-cap-01
    assert "{{ x.label }}" in tpl                   # relation row = target's name, not neil-cpo-01
    assert "{{ x.id }}" not in tpl
    assert "{{ item.root.id }}" not in tpl


def test_without_display_is_byte_identical():
    a = _files(None)["app/views/value_map.py"]
    b = dict(render_views(SCHEMA, VIEWS))["app/views/value_map.py"]
    assert a == b
    assert "session.exec(select(CapabilityOutcome)" in a   # today's join-row fetch
    tpl = _files(None)["app/templates/views/value_map.html"]
    assert "{{ x.id }}" in tpl and "{{ item.root.id }}" in tpl  # today's id rendering


def test_unresolvable_fk_falls_back_to_rows():
    # via_fk that doesn't map to a known model → no resolution (keep rows + id), never crash.
    bad_display = DISPLAY.replace("via_fk: outcomeId", "via_fk: nonexistentId")
    mod = _files(bad_display)["app/views/value_map.py"]
    compile(mod, "<vm>", "exec")
    assert "session.exec(select(CapabilityOutcome)" in mod   # fell back to the row fetch
    assert "session.get(Outcome" not in mod
