#!/usr/bin/env python3
"""SPIKE (throwaway) — preview the dogfood AFTER the definition-driven presentation logic (REQ-10).

Prototypes the three moving parts the architecture describes:
  1. a serializable View Definition (base + per-domain deltas),
  2. a per-leaf cascade resolver (deep-merge, keyed collections → atomic override + propagation),
  3. a projection to the EXISTING RenderProfile so today's renderers are unchanged.

Then renders the SAME dogfood Nodes through TWO domains that share ONE base (requirements + a fictional
"legal" domain), and demonstrates propagation + atomicity live. NOT production — no tests, no gate; this is
a spike to SEE the payoff. Run:  PYTHONPATH=src python3 docs/design/requirements-visualization/_spike/view_definition_spike.py
"""
from __future__ import annotations

import copy
from pathlib import Path

from startd8.navigator.project import render_nodes_html
from startd8.navigator.sources_requirements import nodes_from_requirements
from startd8.wireframe.profile import RenderProfile, StatusStyle

REPO = Path(__file__).resolve().parents[4]
OUT = Path("/tmp/vd-spike")
OUT.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# 2. the cascade resolver (deep-merge, per leaf; keyed collections merge by id)
# --------------------------------------------------------------------------- #
def deep_merge(base: dict, patch: dict) -> dict:
    """later-wins per LEAF key; nested dicts merge (so a `statuses` map merges by id → atomic)."""
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve(name: str, registry: dict) -> dict:
    d = registry[name]
    if not d.get("extends"):
        return copy.deepcopy(d)
    return deep_merge(resolve(d["extends"], registry), d)


# --------------------------------------------------------------------------- #
# 3. projection to the EXISTING RenderProfile (FR-7 — renderers unchanged)
# --------------------------------------------------------------------------- #
def to_render_profile(resolved: dict) -> RenderProfile:
    voc, chrome = resolved.get("vocabulary", {}), resolved.get("chrome", {})
    statuses = tuple(
        StatusStyle(sid, s["label"], s["color"], s["meaning"], s.get("severity", 5), s.get("is_gap", False))
        for sid, s in sorted(voc.get("statuses", {}).items(), key=lambda kv: (kv[1].get("severity", 5), kv[0]))
    )
    return RenderProfile(
        statuses=statuses,
        eyebrow=chrome.get("eyebrow", "Your app"),
        headline=chrome.get("headline", "A first look"),
        section_lead=chrome.get("section_lead", "What this defines"),
        gap_noun=voc.get("gap_noun", "item"),
        summary_meta=(chrome["subtitle"],) if chrome.get("subtitle") else (),
        why=chrome.get("why", ""),
        do=chrome.get("do", ""),
    )


# --------------------------------------------------------------------------- #
# 1. the definitions — ONE base, TWO domain deltas
# --------------------------------------------------------------------------- #
REGISTRY = {
    # the shared top-level navig8r design definition — every domain inherits these
    "base": {
        "extends": None,
        "theme": {"accent": "#1b545f", "ink": "#241f17"},   # (not projected yet — architecture step 2)
        "lenses": "audience-fluency",                        # shared crown jewel
        "chrome": {
            "why": "Each item is a Node: what it does, where it Lives (code/refs), and whether evidence grounds it.",
            "do": "Read top-down — grounded reuses what exists; unsettled needs a decision. Approve or flag each below.",
        },
        "vocabulary": {"statuses": {
            "excluded": {"label": "Excluded", "color": "#948b78", "meaning": "out of scope", "severity": 2},
            "unknown": {"label": "Unknown", "color": "#ab473a", "meaning": "claim without evidence", "severity": 4, "is_gap": True},
        }},
    },
    # domain A: requirements (extends base + its own vocabulary/chrome delta)
    "requirements": {
        "extends": "base",
        "chrome": {"eyebrow": "This spec", "headline": "A first look at this spec", "section_lead": "What this spec defines"},
        "vocabulary": {"gap_noun": "requirement", "statuses": {
            "grounded": {"label": "Grounded", "color": "#3d7a57", "meaning": "reuses existing code", "severity": 0},
            "spec": {"label": "Spec", "color": "#6b6252", "meaning": "written, not built", "severity": 2},
            "awaiting": {"label": "Awaiting", "color": "#a9781a", "meaning": "needs a decision", "severity": 3, "is_gap": True},
        }},
    },
    # domain B: a fictional legal navigator — SAME base, different vocabulary/chrome. Note it OVERRIDES only
    # `chrome.do` (keeps the base `why`) and only `excluded.color` (keeps base excluded meaning/severity).
    "legal": {
        "extends": "base",
        "chrome": {"eyebrow": "This statute", "headline": "A first look at this statute", "section_lead": "What this statute enacts",
                   "do": "Read top-down — enacted is in force; proposed awaits a vote; contested is under challenge."},
        "vocabulary": {"gap_noun": "provision", "statuses": {
            "grounded": {"label": "Enacted", "color": "#3d7a57", "meaning": "in force", "severity": 0},
            "spec": {"label": "Proposed", "color": "#6b6252", "meaning": "drafted, not enacted", "severity": 2},
            "awaiting": {"label": "Contested", "color": "#a9781a", "meaning": "under challenge", "severity": 3, "is_gap": True},
            "excluded": {"color": "#7a3b3b"},   # ← override ONE leaf; base meaning/severity still inherited
        }},
    },
}


def main() -> None:
    nodes = nodes_from_requirements(REPO / "docs/design/requirements-visualization/REQ-01-sdk-node-home.md")

    # --- render the SAME nodes through both domains (cross-domain reuse, made visible) ---
    for domain in ("requirements", "legal"):
        prof = to_render_profile(resolve(domain, REGISTRY))
        render_nodes_html(nodes, OUT / f"{domain}.html", profile=prof)
        print(f"wrote {OUT}/{domain}.html  (eyebrow={prof.eyebrow!r}, gap_noun={prof.gap_noun!r}, "
              f"grounded→{prof.statuses[0].label!r})")

    print("\n=== CASCADE (base ⊕ domain), atomic override ===")
    leg = resolve("legal", REGISTRY)
    print(f"  legal.chrome.why  = {leg['chrome']['why'][:52]!r}   ← inherited from base")
    print(f"  legal.chrome.do   = {leg['chrome']['do'][:52]!r}   ← legal's own override")
    print(f"  legal.excluded    = color {leg['vocabulary']['statuses']['excluded']['color']!r} (legal) + "
          f"meaning {leg['vocabulary']['statuses']['excluded']['meaning']!r} (inherited base) — ATOMIC")

    print("\n=== PROPAGATION: change the BASE once → flows to BOTH domains ===")
    REGISTRY["base"]["chrome"]["do"] = "CHANGED-IN-BASE: read top-down and sign off each item."
    req_do = resolve("requirements", REGISTRY)["chrome"]["do"]
    leg_do = resolve("legal", REGISTRY)["chrome"]["do"]
    print(f"  requirements.do → {req_do[:40]!r}   (took the base change — no override)")
    print(f"  legal.do        → {leg_do[:40]!r}   (kept its OWN — override survives) ")
    REGISTRY["base"]["theme"]["accent"] = "#8a2f2f"
    print(f"  base.theme.accent changed → both domains resolve accent "
          f"{resolve('requirements', REGISTRY)['theme']['accent']!r} / "
          f"{resolve('legal', REGISTRY)['theme']['accent']!r} (shared, propagated)")


if __name__ == "__main__":
    main()
