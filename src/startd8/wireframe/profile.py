"""RenderProfile — parameterize the wireframe HTML preview's *domain vocabulary*.

The preview was authored for the app-scaffold domain: its status words
(``planned``/``not_defined``/…), legend meanings ("not set up yet"), and chrome
("What your app includes", "your app") are app-build language. A non-app consumer
(e.g. the ContextCore requirements navigator) reusing the renderer inherits that
language as *bleed-through* — a fully-written requirement rendered "NOT DEFINED".

A ``RenderProfile`` lets the consumer supply its own status vocabulary + chrome.
It is **opt-in and backward-compatible**: ``render_html`` embeds the profile only
when one is passed, so the app path's payload — and its bytes — are unchanged
(guarded by the byte-identity tests). When absent, the template falls back to its
built-in app strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class StatusStyle:
    """One entry in a domain's status vocabulary — how a status renders."""

    key: str            # the status string a WireframeItem/Section carries
    label: str          # badge text (the template upper-cases it for display)
    color: str          # hex background for the badge/dot
    meaning: str        # one-clause legend gloss ("written, not built")
    severity: int = 5   # roll-up order — higher = worse (worst() wins, min-rolls-up)
    is_gap: bool = False  # counts toward the "needs attention" summary


@dataclass(frozen=True)
class RenderProfile:
    """A domain's status vocabulary + chrome for the wireframe HTML preview."""

    statuses: Tuple[StatusStyle, ...]
    title: str = "Your app — a first look"
    eyebrow: str = "Your app"
    section_lead: str = "What your app includes"
    headline: str = "A first look at your app"
    gap_noun: str = "part"  # "N parts not set up yet"

    def to_dict(self) -> dict:
        """JSON-safe payload the template's client renderer reads (``data.profile``)."""
        return {
            "statuses": [
                {
                    "key": s.key,
                    "label": s.label,
                    "color": s.color,
                    "meaning": s.meaning,
                    "severity": s.severity,
                    "is_gap": s.is_gap,
                }
                for s in self.statuses
            ],
            "title": self.title,
            "eyebrow": self.eyebrow,
            "section_lead": self.section_lead,
            "headline": self.headline,
            "gap_noun": self.gap_noun,
        }


# The default profile == the current hardcoded app vocabulary/colors. It is NOT
# embedded unless explicitly requested (see render_html) so the app path stays
# byte-identical; it exists so callers can start from the app statuses and relabel.
APP_PROFILE = RenderProfile(
    statuses=(
        StatusStyle("planned", "planned", "#3d7a57", "ready to build", 0),
        StatusStyle("defaults", "defaults", "#3a6a94", "using defaults", 1),
        StatusStyle("placeholder", "placeholder", "#a9781a", "rough draft", 2, True),
        StatusStyle("not_defined", "not defined", "#948b78", "not set up yet", 3, True),
        StatusStyle("invalid", "invalid", "#ab473a", "needs fixing", 4, True),
    ),
)
