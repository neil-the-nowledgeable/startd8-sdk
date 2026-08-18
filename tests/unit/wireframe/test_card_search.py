"""REQ-freetext-search-on-navigator-card-browse — FR-keyed regression pins.

Free-text card search is client-side JS in ``_template.py`` composed through the Move 3 predicate seam;
the wireframe suite is Python, so these pin the FR contracts structurally (the level the paging/status/
Move-3 FRs are tested at). FR-4/FR-5 (intersect status + page the survivor set) are satisfied *by
construction* because Move 3 put ``srch-hidden`` in ``PRE_PAGING_REASONS`` — pinned here as the
three-way-compose guard. FR-6 is asserted on the projected View Definition; FR-7 is byte-identity.
"""

from __future__ import annotations

import pytest

from startd8.navigator.view_definition import (
    BASE_NAVIG8R_DEFINITION,
    DEFINITION_REGISTRY,
    resolve,
)
from startd8.wireframe_view import render_html
from tests.unit.wireframe.test_render_profile import _plan

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def html() -> str:
    return render_html(_plan())


def test_fr1_search_input_present(html):
    assert 'id="q-cards"' in html
    assert 'placeholder="search requirements…"' in html


def test_fr2_data_search_blob_is_structural(html):
    # built BY KEY from item.fields + item.touches[].path (never a prose reparse), profile-gated + lowercased.
    blob = html.split('setAttribute("data-search"')[0].rsplit("if(payload.profile){", 1)[-1]
    assert "item.fields" in blob
    assert "_sf.name" in blob and "_sf.verify" in blob
    assert "t.path" in html and ".toLowerCase()" in html


def test_fr3_applysearch_toggles_only_srch_hidden(html):
    assert "function _applySearch" in html
    fn = html.split("function _applySearch")[1].split("\n  }")[0]
    assert 'toggle("srch-hidden"' in fn
    # sets ONLY its own class — never touches pf-hidden/pg-hidden (no clobber, FR-4/FR-2)
    assert "pf-hidden" not in fn and "pg-hidden" not in fn
    assert 'addEventListener("input", _applySearch)' in html


def test_fr4_fr5_composes_via_the_move3_seam_THREE_WAY(html):
    # The three-way compose guard: search rides Move 3's pre-paging seam, so it intersects status AND
    # is excluded from the paged survivor set BY CONSTRUCTION — no re-patch of pagedCards/applyPaging.
    assert '"srch-hidden"' in html.split("PRE_PAGING_REASONS=[")[1].split("]")[0]
    fn = html.split("function _applySearch")[1].split("\n  }")[0]
    assert "applyVisibility();" in fn  # defers composition + re-page to the single recompute point


def test_fr6_definition_owned_search_control():
    control = resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY).control
    assert "search" in control["groups"]
    assert set(control["groups"]["search"]["toggles"]) == {"q-cards"}
    regions = resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY).regions
    assert "qcards" in regions["bindings"]
    assert regions["bindings"]["qcards"]["layer"] == "control"


def test_fr7_app_scaffold_byte_identical():
    assert render_html(_plan()) == render_html(_plan(), profile=None)
