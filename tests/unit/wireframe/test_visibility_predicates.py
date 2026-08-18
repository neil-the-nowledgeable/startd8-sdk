"""REQ-unify-card-visibility-predicates (Move 3) — FR-keyed regression pins.

The predicate model is client-side JS embedded in ``_template.py``; the wireframe suite is Python, so
these pin the FR contracts *structurally* in the emitted JS (the same level the paging/status FRs are
tested at). The load-bearing one is FR-4 — a pin so a future edit can't silently revert the survivor-set
bug fix. Behavioural parity is guarded by the full wireframe suite + ``test_no_profile_is_byte_identical``.
"""

from __future__ import annotations

import pytest

from startd8.wireframe_view import render_html
from tests.unit.wireframe.test_render_profile import _plan

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def html() -> str:
    return render_html(_plan())


def test_fr1_single_visibility_recompute_point(html):
    # ONE applyVisibility recompute that composes the pre-paging reasons then re-pages.
    assert "var applyVisibility" in html
    assert "applyVisibility=function()" in html
    assert "applyPaging();" in html  # applyVisibility re-pages the survivor set


def test_fr2_distinct_non_clobbering_classes(html):
    # status owns pf-hidden, paging owns pg-hidden — each set only by its owner (FR-2).
    assert 'toggle("pf-hidden"' in html
    assert 'toggle("pg-hidden"' in html
    # the status handler must NOT touch pg-hidden (no clobber) — pf and pg live in different handlers.
    applyfilter = html.split("function _applyFilter")[1].split("function ")[0]
    assert "pf-hidden" in applyfilter and "pg-hidden" not in applyfilter


def test_fr3_status_routes_through_the_model(html):
    # _applyFilter defers the composed recompute to applyVisibility().
    applyfilter = html.split("function _applyFilter")[1].split("\n  }")[0]
    assert "applyVisibility();" in applyfilter


def test_fr4_pagedcards_pages_the_survivor_set_REGRESSION(html):
    # THE bug fix, pinned: pagedCards must exclude pre-paging hide-reasons. A revert to the old
    # "all .item minus .vd-template" (ignoring pf-hidden) MUST fail this test.
    paged = html.split("function pagedCards")[1].split("function applyPaging")[0]
    assert "PRE_PAGING_REASONS.some" in paged
    assert "classList.contains(r)" in paged
    assert "vd-template" in paged  # still excludes the display template


def test_fr5_documented_seam_single_registration_point(html):
    assert "FR-5 SEAM" in html
    # the ordered pre-paging reason set is declared in exactly ONE place.
    assert html.count('PRE_PAGING_REASONS=["pf-hidden"') == 1
    # reserved classes for search (Move 3→search) and audience (Move 2) are registered in the seam.
    seam = html.split("FR-5 SEAM")[1].split("applyVisibility=function")[0]
    assert "srch-hidden" in seam and "aud-hidden" in seam


def test_fr6_recompute_survives_re_render(html):
    # the renderAll paging hook re-invokes applyVisibility (not just applyPaging) so composition survives.
    hook = html.split("_pagingHook=function()")[1].split(";")[0]
    assert "applyVisibility()" in hook


def test_fr7_app_scaffold_byte_identical():
    # FR-7: the whole model is inert without a profile → not one changed byte.
    assert render_html(_plan()) == render_html(_plan(), profile=None)
