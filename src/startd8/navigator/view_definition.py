"""View Definition + cascade resolver — the presentation twin of ``NODE-SCHEMA`` (REQ-10).

The keystone of the navig8r presentation-definition architecture
(``ARCHITECTURE_navig8r-presentation-definition-inheritance.md`` §7 step 1): presentation is a
**separate, serializable, inheritable** structure, distinct from content (the Node graph).

A :class:`ViewDefinition` carries an ``extends`` pointer and sections mirroring the scaffold taxonomy
(``theme`` · ``vocabulary`` · ``chrome`` · ``glance`` · ``control`` · ``regions`` · ``lenses``), using
**keyed maps** for overridable collections (``vocabulary.statuses`` keyed by status id). :func:`resolve`
computes ``deep_merge(resolve(extends), definition)`` — later-wins **per leaf key**, keyed collections
merged **by id** (never positional-replace) — so a domain overrides at the finest grain and still inherits
base updates to its siblings, and a base change propagates to every non-overriding domain (atomic).

Renderers are untouched: a resolved definition **projects to the existing** :class:`RenderProfile` via
:func:`to_render_profile`, so the deterministic app-scaffold path stays byte-identical (guarded by
``test_no_profile_is_byte_identical``). Only ``vocabulary`` + ``chrome`` project today; ``theme`` /
``lenses`` / ``control`` / ``glance`` / ``regions`` ride in the definition for the inheritance proof but
are NOT yet extracted into the profile (architecture §7 steps 2/5 — later REQs; NR-3).

Scope (NR-1/NR-2): plain dict/dataclass + JSON — no bespoke DSL, no plugin/theming engine. Schema +
resolver + base + a 2-domain proof + the RenderProfile projection, nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

from startd8.wireframe.profile import RenderProfile, StatusStyle

# The seven scaffold-taxonomy sections a definition (and its resolution) carry.
_SECTIONS = ("theme", "vocabulary", "chrome", "glance", "control", "regions", "lenses")

# A defaults holder so the projection falls back to the RenderProfile field defaults (single source of
# truth) for any chrome key a (partial) definition omits — the real domains supply every key.
_PROFILE_DEFAULTS = RenderProfile(statuses=())


def _copy(value: Any) -> Any:
    """Deep, JSON-shaped copy so :func:`resolve` never aliases (or mutates) an authored definition."""
    if isinstance(value, dict):
        return {k: _copy(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(v) for v in value]
    return value


def _deep_merge(base: Mapping[str, Any], over: Mapping[str, Any]) -> Dict[str, Any]:
    """later-wins **per leaf key**; nested dicts (keyed collections) merged **by id**, never replaced.

    Scalars and lists are replaced wholesale (a list is not an overridable collection — NR keyed maps
    carry the collections that must merge). The result is a fresh structure (see :func:`_copy`).
    """
    out: Dict[str, Any] = {k: _copy(v) for k, v in base.items()}
    for key, val in over.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = _copy(val)
    return out


@dataclass(frozen=True)
class ViewDefinition:
    """A serializable presentation definition with an ``extends`` pointer and taxonomy sections.

    Overridable collections use **keyed maps** (e.g. ``vocabulary={"statuses": {"grounded": {...}}}``),
    never positional lists, so an inheritor can override one entry and keep its siblings.
    """

    name: str
    extends: Optional[str] = None
    theme: Dict[str, Any] = field(default_factory=dict)
    vocabulary: Dict[str, Any] = field(default_factory=dict)
    chrome: Dict[str, Any] = field(default_factory=dict)
    glance: Dict[str, Any] = field(default_factory=dict)
    control: Dict[str, Any] = field(default_factory=dict)
    regions: Dict[str, Any] = field(default_factory=dict)
    lenses: Dict[str, Any] = field(default_factory=dict)

    def _sections(self) -> Dict[str, Any]:
        """The seven taxonomy sections as a fresh dict (identity/extends excluded)."""
        return {name: _copy(getattr(self, name)) for name in _SECTIONS}

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe payload: identity (``name``/``extends``) + the seven sections."""
        payload: Dict[str, Any] = {"name": self.name, "extends": self.extends}
        payload.update(self._sections())
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ViewDefinition":
        """Inverse of :meth:`to_dict` — round-trips through JSON (``from_dict(to_dict(d)) == d``)."""
        return cls(
            name=data["name"],
            extends=data.get("extends"),
            **{name: _copy(data.get(name, {})) for name in _SECTIONS},
        )


@dataclass(frozen=True)
class ResolvedDefinition:
    """The result of resolving a :class:`ViewDefinition`'s ``extends`` chain — no ``extends`` remains.

    Distinct type from an authored definition: a resolved definition is a flattened snapshot ready to
    project to a :class:`RenderProfile`.
    """

    theme: Dict[str, Any] = field(default_factory=dict)
    vocabulary: Dict[str, Any] = field(default_factory=dict)
    chrome: Dict[str, Any] = field(default_factory=dict)
    glance: Dict[str, Any] = field(default_factory=dict)
    control: Dict[str, Any] = field(default_factory=dict)
    regions: Dict[str, Any] = field(default_factory=dict)
    lenses: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """The seven resolved sections as a fresh JSON-safe dict."""
        return {name: _copy(getattr(self, name)) for name in _SECTIONS}


def resolve(
    definition: ViewDefinition,
    registry: Mapping[str, ViewDefinition],
) -> ResolvedDefinition:
    """Flatten ``definition``'s ``extends`` chain: ``deep_merge(resolve(extends), definition)``.

    Recursive over ``extends`` (looked up by name in ``registry``); later-wins per leaf key; keyed
    collections merged by id. A definition with ``extends=None`` resolves to itself (idempotent).
    """
    merged: Dict[str, Any] = {}
    if definition.extends is not None:
        parent = registry[definition.extends]
        merged = resolve(parent, registry).to_dict()
    merged = _deep_merge(merged, definition._sections())
    return ResolvedDefinition(**merged)


def to_render_profile(resolved: ResolvedDefinition) -> RenderProfile:
    """Project a resolved definition to the existing :class:`RenderProfile` (renderers unchanged).

    Reads ``vocabulary`` (ordered ``statuses`` keyed map + ``gap_noun``) and ``chrome`` (masthead + apex
    strings). ``theme``/``lenses``/``control``/``glance``/``regions`` are intentionally NOT projected yet
    (NR-3 — later architecture steps). Any omitted chrome key falls back to the RenderProfile default.
    """
    vocab = resolved.vocabulary or {}
    chrome = resolved.chrome or {}
    statuses = tuple(
        StatusStyle(
            key=sid,
            label=spec.get("label", sid),
            color=spec.get("color", "#948b78"),
            meaning=spec.get("meaning", ""),
            severity=spec.get("severity", 5),
            is_gap=spec.get("is_gap", False),
        )
        for sid, spec in (vocab.get("statuses") or {}).items()
    )
    return RenderProfile(
        statuses=statuses,
        title=chrome.get("title", _PROFILE_DEFAULTS.title),
        eyebrow=chrome.get("eyebrow", _PROFILE_DEFAULTS.eyebrow),
        section_lead=chrome.get("section_lead", _PROFILE_DEFAULTS.section_lead),
        headline=chrome.get("headline", _PROFILE_DEFAULTS.headline),
        gap_noun=vocab.get("gap_noun", _PROFILE_DEFAULTS.gap_noun),
        summary_meta=tuple(chrome.get("summary_meta", _PROFILE_DEFAULTS.summary_meta)),
        why=chrome.get("why", _PROFILE_DEFAULTS.why),
        do=chrome.get("do", _PROFILE_DEFAULTS.do),
    )


# ─────────────────────────────────────────────────────────────────────────────
# The shared base + the domain deltas that extend it.
# ─────────────────────────────────────────────────────────────────────────────

# FR-3: the shared design definition every domain extends. Carries the domain-neutral defaults —
# theme palette, the lens reference, control-panel structure, glance binding, and the region/layer
# skeleton. It owns NO vocabulary/chrome (those are each domain's delta). ``extends=None`` (a root).
BASE_NAVIG8R_DEFINITION = ViewDefinition(
    name="base",
    extends=None,
    theme={"ink": "#2a2620", "paper": "#faf8f3", "accent": "#3d7a57"},
    lenses={"axes": ["role", "fluency"]},
    control={"panel": "top-right", "groups": ["view", "overlays", "template-anatomy"]},
    glance={"summary": "status-counts"},
    regions={"layers": ["node", "derived", "computed", "scaffold"]},
)

# FR-4: the requirements domain — ``extends: base`` + a thin delta (its vocabulary/statuses + chrome).
# The masthead/chrome the standalone RenderProfile literal used to own now lives under ``chrome`` here;
# projecting the resolution reproduces today's REQUIREMENTS_PROFILE byte-for-byte (guarded by tests).
REQUIREMENTS_DEFINITION = ViewDefinition(
    name="requirements",
    extends="base",
    vocabulary={
        "gap_noun": "requirement",
        "statuses": {
            "grounded": {"label": "Grounded", "color": "#3d7a57", "meaning": "reuses existing code", "severity": 0},
            "spec": {"label": "Spec", "color": "#6b6252", "meaning": "written, not built", "severity": 2},
            "awaiting": {"label": "Awaiting", "color": "#a9781a", "meaning": "needs a decision", "severity": 3, "is_gap": True},
            "excluded": {"label": "Excluded", "color": "#948b78", "meaning": "out of scope", "severity": 2},
            "unknown": {"label": "Unknown", "color": "#ab473a", "meaning": "done-claim without Lives", "severity": 4, "is_gap": True},
        },
    },
    chrome={
        "title": "This spec — a first look",
        "eyebrow": "This spec",
        "section_lead": "What this spec defines",
        "headline": "A first look at this spec",
        "summary_meta": [
            "A glance-approvable view of every requirement in this spec — each grounded in code, "
            "or flagged as still-spec.",
        ],
        "why": (
            "Each requirement is a Node: what it does, where it Lives (code/test refs), and "
            "whether evidence grounds it."
        ),
        "do": (
            "Read top-down — grounded (green) reuses existing code; spec/awaiting needs a "
            "decision. Approve or flag each requirement below."
        ),
    },
)

# FR-5: a SECOND domain extending the SAME base — the cross-domain reuse proof. The capability index
# supplies only its own vocabulary + chrome deltas (and its own ``theme.accent`` override, to prove a
# domain keeps its override while inheriting the base's other theme tokens — FR-6). Its ``theme``
# override is NOT projected to the RenderProfile yet (NR-3), so its rendered profile is unaffected.
CAPABILITY_DEFINITION = ViewDefinition(
    name="capability",
    extends="base",
    theme={"accent": "#3a6a94"},
    vocabulary={
        "gap_noun": "capability",
        "statuses": {
            "built": {"label": "Built", "color": "#3d7a57", "meaning": "code leaf present", "severity": 0},
            "thin": {"label": "Thin", "color": "#a9781a", "meaning": "early / incomplete evidence", "severity": 2, "is_gap": True},
            "spec": {"label": "Spec", "color": "#6b6252", "meaning": "declared, not built", "severity": 3, "is_gap": True},
            "deprecated": {"label": "Deprecated", "color": "#ab473a", "meaning": "do not use", "severity": 4},
        },
    },
    chrome={
        "title": "Capabilities — a first look",
        "eyebrow": "Capability index",
        "section_lead": "What the SDK ships",
        "headline": "A first look at SDK capabilities",
        "summary_meta": [
            "A glance-approvable view of what the SDK ships — each capability grounded in a code "
            "leaf, or flagged as thin/spec.",
        ],
        "why": (
            "Each capability is a Node: what it does, where it Lives (code refs), and whether a "
            "code leaf grounds it."
        ),
        "do": (
            "Read top-down — built (green) has a code leaf; thin/spec needs evidence or is "
            "declared-only. Approve or flag each capability below."
        ),
    },
)

# The definition registry the resolver consults for ``extends`` lookups.
DEFINITION_REGISTRY: Dict[str, ViewDefinition] = {
    "base": BASE_NAVIG8R_DEFINITION,
    "requirements": REQUIREMENTS_DEFINITION,
    "capability": CAPABILITY_DEFINITION,
}
