"""REQ-audience-tiered-disclosure (Move 2) — FR-keyed regression pins.

Audience-tiered disclosure is client-side JS in ``_template.py`` (the doc-context band re-renders its
field set at the tier the existing lens resolves), so these pin the FR contracts structurally — the
level the Move 3 / search FRs are tested at. The load-bearing pin is FR-5: the maximal tier registers
EVERY band field (a tier, not a delete). FR-7 is byte-identity.
"""

from __future__ import annotations

import re

import pytest

from startd8.wireframe_view import render_html
from tests.unit.wireframe.test_render_profile import _plan

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def html() -> str:
    return render_html(_plan())


def test_fr1_disclose_tier_derives_from_the_existing_lens(html):
    assert "function discloseTier" in html
    fn = html.split("function discloseTier")[1].split("\n  }")[0]
    # maps fluency → tier off the EXISTING `cur` lens key (no new audience state).
    assert 'cur||""' in fn and '.split("|")[1]' in fn
    assert 'return "maximal"' in fn and 'return "minimal"' in fn


def test_fr2_band_gates_advanced_fields_by_tier(html):
    band = html.split("function docContextBand")[1].split("function renderMast")[0]
    # criticality is ALWAYS shown (not gated); trust/data/version are advanced-only (gated by at()).
    assert 'at("trust")?chip' in band
    assert 'at("data")?chip' in band
    assert 'at("version")?chip' in band
    assert 'at("domain")?chip' in band and 'at("audience")?chip' in band
    # the risk DETAIL rows are advanced-only; the summary is always shown.
    assert 'at("riskDetail")' in band and "dc-risks-sum" in band


def test_fr4_one_documented_disclosure_seam(html):
    # the tier→fields registration lives in ONE place (DC_FIELD_TIER), read via atTier().
    assert html.count("var DC_FIELD_TIER=") == 1
    assert "function atTier(" in html
    seam = html.split("var DC_FIELD_TIER=")[1].split("}")[0]
    for f in ("criticality", "trust", "data", "version", "riskDetail"):
        assert f in seam


def test_fr5_maximal_tier_is_the_full_set_TIER_NOT_DELETE(html):
    # PARITY: every field the band emits is registered in the seam, and the maximal rank (2) covers all —
    # so at maximal the band renders the full set it shows today (nothing deleted; a beginner just defaults lower).
    seam = html.split("var DC_FIELD_TIER=")[1].split("}")[0]
    registered = dict(re.findall(r"(\w+):(\d+)", seam))
    for f in ("criticality", "counts", "riskSummary", "domain", "audience",
              "trust", "data", "version", "riskDetail"):
        assert f in registered, f"band field {f} not registered in the disclosure seam"
    assert max(int(v) for v in registered.values()) == 2  # maximal rank; nothing gated beyond the top tier
    # the deferred pare (trust/data/version/riskDetail) is the MAXIMAL tier, not a delete.
    assert all(registered[f] == "2" for f in ("trust", "data", "version", "riskDetail"))
    assert registered["criticality"] == "0"  # the minimal-tier anchor


def test_fr6_distinct_from_card_visibility(html):
    # disclosure tiering must NOT touch the Move 3 visibility model: no aud-hidden, PRE_PAGING_REASONS intact.
    assert "aud-hidden" not in html.split("function docContextBand")[1].split("function renderMast")[0]
    assert 'PRE_PAGING_REASONS=["pf-hidden","srch-hidden","aud-hidden"]' in html  # unchanged from Move 3


def test_fr7_app_scaffold_byte_identical():
    assert render_html(_plan()) == render_html(_plan(), profile=None)
