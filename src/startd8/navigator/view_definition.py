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

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from startd8.wireframe.profile import RenderProfile, StatusStyle

# REQ-12: a chrome-binding placeholder — ``{field}`` referencing a single content-context key.
_BINDING = re.compile(r"\{([a-z_][a-z0-9_]*)\}")

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

    Fails loud on a malformed chain — an ``extends`` naming a definition absent from ``registry``, or a
    cycle — with a :class:`ValueError` naming the offender, rather than a bare ``KeyError`` /
    ``RecursionError`` (an ``extends`` graph assembled from authored or ``from_dict``-deserialized JSON
    is not guaranteed acyclic).
    """
    return _resolve(definition, registry, ())


def _resolve(
    definition: ViewDefinition,
    registry: Mapping[str, ViewDefinition],
    seen: tuple,
) -> ResolvedDefinition:
    """Recursion core carrying the ``seen`` chain (root→…→current) for cycle detection."""
    if definition.name in seen:
        chain = " → ".join((*seen, definition.name))
        raise ValueError(f"cyclic 'extends' chain: {chain}")
    merged: Dict[str, Any] = {}
    if definition.extends is not None:
        try:
            parent = registry[definition.extends]
        except KeyError:
            raise ValueError(
                f"{definition.name!r} extends unknown definition {definition.extends!r} "
                f"(known: {sorted(registry)})"
            ) from None
        merged = _resolve(parent, registry, (*seen, definition.name)).to_dict()
    merged = _deep_merge(merged, definition._sections())
    return ResolvedDefinition(**merged)


def _diff_leaves(base: Mapping[str, Any], over: Mapping[str, Any]) -> Dict[str, Any]:
    """The leaf keys where ``over`` differs from ``base`` — recursing dicts, comparing other leaves."""
    out: Dict[str, Any] = {}
    for key, val in over.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            sub = _diff_leaves(base[key], val)
            if sub:
                out[key] = sub
        elif base.get(key) != val:
            out[key] = _copy(val)
    return out


def definition_diff(
    domain: ViewDefinition,
    base: ViewDefinition,
    registry: Mapping[str, ViewDefinition],
) -> Dict[str, Any]:
    """The leaves a ``domain`` overrides/adds vs a ``base`` — *what makes this domain different*.

    Compares the two RESOLVED forms and returns only the differing/added leaves (nested by section),
    so an author or governance check can see exactly a domain's delta without reading the whole merge
    (e.g. capability → ``{"theme": {"accent": "#3a6a94"}, "vocabulary": {...}, "chrome": {...}}``).
    Inherited-and-unchanged sections (lenses/control/…) are omitted.
    """
    resolved_base = resolve(base, registry).to_dict()
    resolved_domain = resolve(domain, registry).to_dict()
    return _diff_leaves(resolved_base, resolved_domain)


def resolve_bindings(template: str, context: Mapping[str, str]) -> str:
    """REQ-12 FR-1: substitute ``{field}`` placeholders in a chrome ``template`` from ``context``.

    Single-field substitution only — no functions, conditionals, or arithmetic (NR-2). An unknown or
    empty field substitutes the empty string; a template with no placeholder is returned unchanged.
    """
    return _BINDING.sub(lambda m: str(context.get(m.group(1), "")), template)


def _binding_fields(template: Any) -> List[str]:
    """The context fields a template (str or list of str) references."""
    parts = template if isinstance(template, list) else [template]
    return [f for part in parts for f in _BINDING.findall(str(part))]


def to_render_profile(
    resolved: ResolvedDefinition,
    context: Optional[Mapping[str, str]] = None,
) -> RenderProfile:
    """Project a resolved definition to the existing :class:`RenderProfile` (renderers unchanged).

    Reads ``vocabulary`` (ordered ``statuses`` keyed map + ``gap_noun``), ``chrome`` (masthead + apex
    strings), ``theme`` (REQ-11 → ``theme_tokens``), and ``control`` + ``regions`` (REQ-14 → the
    debug-panel schema + region/layer taxonomy, applied as an additive runtime override). ``lenses``/
    ``glance`` are still NOT projected. Any omitted chrome key falls back to the RenderProfile default.

    REQ-12: when a ``context`` is supplied, a chrome field named in ``chrome.bindings`` is derived by
    substituting its ``{field}`` template against the context — but ONLY when every referenced field
    resolves non-empty; otherwise the static chrome value stands. ``context=None`` ⇒ static chrome
    (byte-identical). Bindings are consumed here, not carried on the RenderProfile.
    """
    vocab = resolved.vocabulary or {}
    chrome = resolved.chrome or {}
    bindings = (chrome.get("bindings") or {}) if context else {}

    def _chrome(field: str, static: Any) -> Any:
        """The bound value for ``field`` if its binding fully resolves, else the static value."""
        template = bindings.get(field)
        if template is None:
            return static
        fields = _binding_fields(template)
        if not fields or not all(context.get(f) for f in fields):
            return static
        if isinstance(template, list):
            return tuple(resolve_bindings(str(t), context) for t in template)
        return resolve_bindings(template, context)

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
        title=_chrome("title", chrome.get("title", _PROFILE_DEFAULTS.title)),
        eyebrow=_chrome("eyebrow", chrome.get("eyebrow", _PROFILE_DEFAULTS.eyebrow)),
        section_lead=_chrome("section_lead", chrome.get("section_lead", _PROFILE_DEFAULTS.section_lead)),
        headline=_chrome("headline", chrome.get("headline", _PROFILE_DEFAULTS.headline)),
        gap_noun=vocab.get("gap_noun", _PROFILE_DEFAULTS.gap_noun),
        summary_meta=_chrome("summary_meta", tuple(chrome.get("summary_meta", _PROFILE_DEFAULTS.summary_meta))),
        why=_chrome("why", chrome.get("why", _PROFILE_DEFAULTS.why)),
        do=_chrome("do", chrome.get("do", _PROFILE_DEFAULTS.do)),
        theme_tokens=dict(resolved.theme or {}),
        control=dict(resolved.control or {}),      # REQ-14 FR-2: the debug-panel schema
        regions=dict(resolved.regions or {}),      # REQ-14 FR-5a: the region/layer taxonomy
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
    # REQ-11 FR-1: the theme tokens are the renderer's ACTUAL ``:root`` values (``_template.py``), so
    # projecting them (FR-3) reproduces today's rendered colours for a non-overriding domain — the
    # byte-identity anchor. (REQ-10 shipped placeholder values here; those recoloured every domain.)
    theme={"ink": "#241f17", "paper": "#f4efe4", "accent": "#1b545f"},
    lenses={"axes": ["role", "fluency"]},
    # REQ-14 FR-1: the debug control panel modelled as ordered groups of toggles — populated with the
    # EXACT groups/toggles/labels the template hardcodes today (`_template.py` ~774-793), so projecting
    # + consuming them (FR-2/FR-3) reproduces the current panel byte-for-byte. Keyed maps (merged by id);
    # `order` gives the render sequence, `first` = the `dbg-group-first` class, `sub` = `dbg-sub`.
    control={
        "panel": "top-right",
        "groups": {
            "view": {"label": "View", "hint": "· pick one (Full is default)", "order": 0, "first": True,
                     "toggles": {
                         "structOnly": {"label": "Structure only", "order": 0},
                         "combined": {"label": "Combined (structure + content)", "order": 1},
                     }},
            "overlays": {"label": "Overlays", "hint": "· additive", "order": 1,
                         "toggles": {
                             "hideScaffold": {"label": "Hide app-scaffold chrome", "order": 0},
                         }},
            "template-anatomy": {"label": "Template anatomy", "hint": "· debug", "order": 2,
                                 "toggles": {
                                     "scaffold": {"label": "Scaffold mode (template anatomy)", "order": 0},
                                     "scaffoldOnly": {"label": "Scaffold only (hide node content)", "order": 1, "sub": True},
                                 }},
        },
    },
    glance={"summary": "status-counts"},
    # REQ-14 FR-4: the scaffold region/layer taxonomy modelled as ordered region bindings — each region
    # (keyed by its element id) carries its `layer` + the `scaffold` anatomy label the template hardcodes
    # today (`_template.py` data-layer/data-scaffold). Populated verbatim so consuming them (FR-5) is
    # byte-identical; a domain delta can override one region's label atomically. `layers` = the legend.
    regions={
        # REQ-15 FR-2: the layer taxonomy as an ordered keyed schema owned by the definition (was a flat,
        # 3-way-inconsistent list). Populated with the renderer's ACTUAL layer names + outline colours
        # (`_template.py` scaffold CSS) so rendering the legend + colouring FROM it (FR-3) is byte-identical.
        "layers": {
            "control": {"label": "control", "color": "accent2", "order": 0},
            "descriptive": {"label": "descriptive", "color": "accent", "order": 1},
            "computed": {"label": "computed", "color": "ochre", "order": 2},
            "node": {"label": "node-driven", "color": "planned", "order": 3},
        },
        "bindings": {
            "mast": {"layer": "descriptive", "scaffold": "masthead — profile chrome (eyebrow · headline · why/do)", "order": 0},
            "glance": {"layer": "computed", "scaffold": "glance band — computed summary (status_counts · plan.shape)", "order": 1},
            "toolbar": {"layer": "control", "scaffold": "control layer — audience × fluency lenses", "order": 2},
            "legend": {"layer": "descriptive", "scaffold": "status legend — profile.statuses[].meaning", "order": 3},
            "seclead": {"layer": "descriptive", "scaffold": "section lead — profile.section_lead", "order": 4},
            "outline": {"layer": "node", "scaffold": "outline — node sections + cards (the node-driven layer)", "order": 5},
            "whybox": {"layer": "descriptive", "scaffold": "reading guidance — profile.why / profile.do", "order": 6},
            "shape": {"layer": "computed", "scaffold": "shape — plan.shape (dialect-aware)", "order": 7},
            "glance-status-cell": {"layer": "computed", "scaffold": "status roll-up — status_counts (+ PF-1 grounding filter)", "order": 8},
        },
    },
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
        # REQ-12 FR-4: the FR-17/18 masthead derivations as declarative single-field bindings — applied
        # (over the static values above) only when a per-doc content context is passed at projection.
        # The compound page-title (`{key} — {title}` with 3-way degradation) is NOT here — it stays in
        # requirements_profile_for (NR-2). why/do/gap_noun are intentionally not bound (ride static).
        "bindings": {
            "eyebrow": "{key}",
            "headline": "{title}",
            "section_lead": "What {key} defines",
            "summary_meta": ["{semantic_name}"],
        },
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

# EC-2 (REQ-10 backlog): a THIRD real domain extending the same base — the node-schema (Kagami) view.
# Widens the cross-domain proof from 2 to 3 real domains and de-dups the former standalone
# ``NODE_SCHEMA_PROFILE`` literal (now projected from here). Overrides no theme → inherits the base
# tokens, so its rendered colours are unchanged (byte-safe); it now shares the activated theme (REQ-11).
NODE_SCHEMA_DEFINITION = ViewDefinition(
    name="node-schema",
    extends="base",
    vocabulary={
        "gap_noun": "field",
        "statuses": {
            "authored": {"label": "Authored", "color": "#3d7a57", "meaning": "a human writes this field", "severity": 0},
            "derived": {"label": "Derived", "color": "#2b7382", "meaning": "computed from evidence × maturity", "severity": 1},
            "computed": {"label": "Computed", "color": "#6b6252", "meaning": "assembled by the harness", "severity": 1},
            "meta": {"label": "Meta", "color": "#948b78", "meaning": "open extension bag", "severity": 2},
        },
    },
    chrome={
        "title": "Node structure — a first look",
        "eyebrow": "NODE-SCHEMA",
        "section_lead": "What a Node is made of",
        "headline": "A first look at the Node structure",
        "summary_meta": [
            "The Node model rendered as Nodes — a Kagami mirror of models.py (field names/types/defaults "
            "introspected, not hand-drawn).",
        ],
        "why": (
            "Each field IS a node: what it holds, its type/default (from the code), and who fills it "
            "(authored · derived · computed · meta)."
        ),
        "do": (
            "Read by group — identity, descriptive, evidence, axes, hierarchy, derived, meta. A field "
            "present in models.py but missing an annotation below is a gap to fill."
        ),
    },
)

# REQ-08 FR-1/D-1: a FOURTH real domain extending the same base — the prose→product pipeline view.
# Each stage is a Node (``category="pipeline-stage"``); its status derives from its ``sdk_artifact``
# resolving on disk via ``derive_status(has_code_evidence=…, maturity="stable")`` → {built, spec}
# only (never thin — the constant maturity closes the outcome). The ``vocabulary.statuses`` map is
# therefore **keyed by the ``NodeStatus`` ids** ``built``/``spec`` (R1-F2), not prose labels, so the
# legend resolves every status ``nodes_from_pipeline()`` can emit. Overrides no theme → inherits the
# base tokens (byte-safe), shares the activated theme.
PIPELINE_DEFINITION = ViewDefinition(
    name="pipeline",
    extends="base",
    vocabulary={
        "gap_noun": "stage",
        "statuses": {
            "built": {"label": "Built", "color": "#3d7a57", "meaning": "the stage's SDK artifact exists on disk", "severity": 0},
            "spec": {"label": "Spec", "color": "#6b6252", "meaning": "the stage's SDK artifact is not present yet", "severity": 3, "is_gap": True},
        },
    },
    chrome={
        "title": "The pipeline — a first look",
        "eyebrow": "Prose→product pipeline",
        "section_lead": "How prose becomes a product",
        "headline": "A first look at the prose→product pipeline",
        "summary_meta": [
            "The six stages of the prose→product compiler rendered as Nodes — intent · functional · "
            "contract · impl · test · doc, each grounded in the SDK artifact that realises it.",
        ],
        "why": (
            "Each stage is a Node: what it transforms, its compiler analogue, and where it Lives "
            "(the SDK artifact) — built (green) when that artifact exists, spec when it doesn't."
        ),
        "do": (
            "Read top-down along the DEPENDS-ON edges — intent → functional → contract → "
            "{impl, test, doc}. A spec stage marks a gap in the pipeline's realisation."
        ),
    },
)

# The definition registry the resolver consults for ``extends`` lookups.
DEFINITION_REGISTRY: Dict[str, ViewDefinition] = {
    "base": BASE_NAVIG8R_DEFINITION,
    "requirements": REQUIREMENTS_DEFINITION,
    "capability": CAPABILITY_DEFINITION,
    "node-schema": NODE_SCHEMA_DEFINITION,
    "pipeline": PIPELINE_DEFINITION,
}

# REQ-12: the content-context fields a chrome binding may reference (from ``requirement_identity``).
BINDING_CONTEXT_FIELDS = ("key", "title", "semantic_name", "initiative")


def validate_definitions(registry: Mapping[str, ViewDefinition]) -> List[str]:
    """EC-6: governance check for a definition registry — returns a list of issues (empty = clean).

    Read-only. Catches the two classes an author can get wrong: (1) a definition whose ``extends``
    chain is broken (unknown parent or a cycle — surfaced by :func:`resolve`'s guards); (2) a
    ``chrome.bindings`` template referencing an unknown content-context field (not one of
    :data:`BINDING_CONTEXT_FIELDS`), which would silently substitute the empty string at render.
    """
    issues: List[str] = []
    for name, definition in registry.items():
        try:
            resolve(definition, registry)
        except ValueError as exc:
            issues.append(f"{name}: {exc}")
        for field_name, template in (definition.chrome.get("bindings") or {}).items():
            for ref in _binding_fields(template):
                if ref not in BINDING_CONTEXT_FIELDS:
                    issues.append(
                        f"{name}: chrome.bindings.{field_name} references unknown context field "
                        f"{ref!r} (known: {', '.join(BINDING_CONTEXT_FIELDS)})"
                    )
    return issues


def load_definition(source: Union[str, Path, Mapping[str, Any]]) -> ViewDefinition:
    """REQ-13 FR-1: load an externally-authored View Definition from a VIEW-SCHEMA JSON file or dict.

    ``source`` is a path to a JSON file or an already-parsed mapping. The import half of the cross-repo
    seam (EC-1 is the export half) — a second repo authors its presentation as ``{name, extends, …}``
    JSON and the navigator consumes it via :meth:`ViewDefinition.from_dict`. Raises a clear ``ValueError``
    when the payload is not a JSON object or lacks a ``name``.
    """
    if isinstance(source, (str, Path)):
        data = json.loads(Path(source).read_text(encoding="utf-8"))
    else:
        data = source
    if not isinstance(data, Mapping):
        raise ValueError(f"VIEW-SCHEMA must be a JSON object, got {type(data).__name__}")
    if not data.get("name"):
        raise ValueError("VIEW-SCHEMA is missing the required 'name' field")
    return ViewDefinition.from_dict(data)


def resolve_external(
    definition: ViewDefinition,
    registry: Mapping[str, ViewDefinition] = DEFINITION_REGISTRY,
) -> ResolvedDefinition:
    """REQ-13 FR-2: resolve an external definition against the shipped base registry (read-only).

    The external definition is resolved against a COPY of ``registry`` that includes it, so its
    ``extends: "base"`` chain flattens against the shipped base and it inherits the shared
    theme/lenses/control/glance/regions. The shipped registry is never mutated (NR-2).
    """
    return resolve(definition, {**registry, definition.name: definition})
