"""Kickoff audience (fluency) — M1 persistence spine (FR-1/FR-2/FR-3).

``audience`` is a **lens** over the one guided kickoff experience: a new dimension **orthogonal** to
``posture``, selecting how much scaffolding a user needs (Beginner / Intermediate / Advanced). It is
resolved by the **same precedence ladder** as ``guided`` (``guided_routing.py``) — flag → per-project
``build-preferences.yaml`` → global ``~/.startd8/config.json`` → default — but over a **distinct
3-value domain** (not the tri-state bool). Unset everywhere ⇒ **Intermediate** (FR-2), so the kernel
path stays **byte-identical** for anyone who never picks an audience.

**M1 is the persistence spine only.** It owns the enum, the resolver, and the single canonical setter.
It writes **only the preference** — it never runs the audience pre-pass (FR-11, M3), which fires later
at *walk-start* on an explicit action, never here and never on a read (A-OQ10). Disclosure tiers (M4),
the surface pre-pass (M3), and the web selector (FR-19, M5) all build on this module; none exist yet.

Naming note (§0.3): the canonical term is ``audience``. ``persona`` is reserved for the
``stakeholder_panel`` roster concept and is deliberately **not** used here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# Project preference path — pinned exactly as the ``guided`` ladder pins it (this file only, never an
# examples/ or templates/ copy). Mirrors ``guided_routing._PROJECT_BUILD_PREFS``.
_PROJECT_BUILD_PREFS = ("docs", "kickoff", "inputs", "build-preferences.yaml")

# Global-config preferences key (``~/.startd8/config.json`` → ``preferences.audience``).
_GLOBAL_PREF_KEY = "audience"


class KickoffAudience(Enum):
    """The three fluency archetypes. The ``value`` strings are the canonical on-disk / CLI tokens."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


# FR-2: the default when no layer expresses an audience. Intermediate == today's guided walk, so an
# unset user's experience is byte-identical to pre-feature behavior.
DEFAULT_AUDIENCE = KickoffAudience.INTERMEDIATE

#: The DISCLOSURE knob (M4, FR-9/FR-10): each audience → the ``load_experience_doc`` tier it reads.
#: Beginner gets the plain-language ``expanded`` rewrite; Intermediate the ``light`` full body
#: (today's default → byte-identical); Advanced the terse ``compact`` TL;DR. Intermediate mapping to
#: ``light`` is what keeps an unset user's prose unchanged.
_DISCLOSURE_TIER = {
    KickoffAudience.BEGINNER: "expanded",
    KickoffAudience.INTERMEDIATE: "light",
    KickoffAudience.ADVANCED: "compact",
}


def disclosure_tier(audience: "str | KickoffAudience") -> str:
    """The experience-doc disclosure tier for an audience (``expanded``/``light``/``compact``)."""
    return _DISCLOSURE_TIER.get(coerce_audience(audience) or DEFAULT_AUDIENCE, "light")


def coerce_audience(value: Any) -> Optional[KickoffAudience]:
    """Coerce a heterogeneous preference value → :class:`KickoffAudience`, or ``None`` (unset).

    Accepts an enum instance, a case-insensitive token string (``"beginner"``…), or ``None`` (absent).
    An empty or unrecognized value degrades to ``None`` (fall through to the next layer) — it never
    raises and never silently substitutes a wrong audience. (The strict project-manifest parser
    loud-fails on a bad ``audience`` at parse time; this resolver-side coercion stays tolerant so a
    stale global-config value can't crash the kernel.)
    """
    if value is None:
        return None
    if isinstance(value, KickoffAudience):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        for a in KickoffAudience:
            if s == a.value:
                return a
    return None


@dataclass(frozen=True)
class AudienceResolution:
    """The resolved audience + the ladder layer that decided it."""

    value: KickoffAudience
    source: str  # "flag" | "project" | "global" | "default"


def _project_audience(project_root: str | Path) -> Optional[KickoffAudience]:
    """Read the project layer from ``build-preferences.yaml``; skip (``None``) on absence or any error."""
    path = Path(project_root).expanduser().joinpath(*_PROJECT_BUILD_PREFS)
    if not path.is_file():
        return None
    try:
        from ..kickoff_inputs import parse_build_preferences

        return coerce_audience(parse_build_preferences(path.read_text(encoding="utf-8")).audience)
    except Exception:
        # Malformed sheet / IO error → skip this layer (degrade to the next), never crash.
        return None


def _global_audience() -> Optional[KickoffAudience]:
    """Read the global layer from ``~/.startd8/config.json`` preferences; skip (``None``) on error."""
    try:
        from ..config import get_config_manager

        return coerce_audience(get_config_manager().get_preference(_GLOBAL_PREF_KEY))
    except Exception:
        return None


def resolve_audience_preference(
    project_root: str | Path,
    flag: Optional[str | KickoffAudience] = None,
) -> AudienceResolution:
    """Resolve the effective audience by the precedence ladder (FR-1/FR-2).

    Precedence: ``flag`` (``--audience``) > project ``build-preferences.yaml`` > global
    ``~/.startd8/config.json`` > default. The **first layer expressing a recognized audience wins**;
    an unrecognized/absent value at a layer falls through. When no layer expresses one, the result is
    :data:`DEFAULT_AUDIENCE` (Intermediate, FR-2) with source ``"default"``.
    """
    flag_a = coerce_audience(flag)
    if flag_a is not None:
        return AudienceResolution(flag_a, "flag")
    proj = _project_audience(project_root)
    if proj is not None:
        return AudienceResolution(proj, "project")
    glob = _global_audience()
    if glob is not None:
        return AudienceResolution(glob, "global")
    return AudienceResolution(DEFAULT_AUDIENCE, "default")


@dataclass(frozen=True)
class AudienceWriteResult:
    """What :func:`set_audience_preference` wrote — the value, the scope, and the target path."""

    value: KickoffAudience
    scope: str          # "project" | "global"
    target: str         # human-readable path/location written


def _write_project_audience(project_root: str | Path, audience: KickoffAudience) -> str:
    """Persist ``audience`` into the project ``build-preferences.yaml`` with a **SOTTO-safe** edit.

    A *targeted line* write, not a YAML round-trip: replaces an existing top-level ``audience:`` line
    or appends one, preserving every other byte (comments, ordering, formatting). The result is
    re-parsed with the strict parser and the write is **aborted** (``ValueError`` re-raised) if it
    would produce a malformed sheet — so a bad edit never lands. Creates a minimal sheet if absent.
    """
    from ..kickoff_inputs import parse_build_preferences

    path = Path(project_root).expanduser().joinpath(*_PROJECT_BUILD_PREFS)
    if path.is_file():
        original = path.read_text(encoding="utf-8")
        # Validate the current sheet first — never mutate a file we can't parse (loud-fail upstream).
        parse_build_preferences(original)
        lines = original.splitlines()
        new_line = f"audience: {audience.value}"
        replaced = False
        for i, ln in enumerate(lines):
            if ln.lstrip().startswith("audience:") and ln == ln.lstrip():  # top-level only
                lines[i] = new_line
                replaced = True
                break
        if not replaced:
            lines.append(new_line)
        new_text = "\n".join(lines) + ("\n" if original.endswith("\n") else "")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_text = f"domain: build-preferences\naudience: {audience.value}\n"

    # Validate the *result* before writing — abort on any malformation (re-raises ValueError).
    parse_build_preferences(new_text)
    path.write_text(new_text, encoding="utf-8")
    return str(path)


def set_audience_preference(
    audience: str | KickoffAudience,
    *,
    project_root: str | Path = ".",
    scope: str = "project",
) -> AudienceWriteResult:
    """The **single canonical audience writer** — the sole preference-write path (FR-3).

    Called by the CLI now and by the web selector later (FR-19), so both surfaces share one writer
    rather than forking a second one. Writes **only the preference** — never the pre-pass (A-OQ10):
    the audience takes effect at the next walk-start, not here.

    ``scope="project"`` (default; "project-remembered", FR-1) writes the project
    ``build-preferences.yaml`` via a SOTTO-safe targeted edit. ``scope="global"`` writes the
    user-level ``~/.startd8/config.json`` preference. Raises ``ValueError`` on an unknown audience
    token or an unknown scope.
    """
    resolved = coerce_audience(audience)
    if resolved is None:
        valid = ", ".join(a.value for a in KickoffAudience)
        raise ValueError(f"unknown audience {audience!r} (expected one of: {valid})")

    if scope == "global":
        from ..config import get_config_manager

        get_config_manager().set_preference(_GLOBAL_PREF_KEY, resolved.value)
        return AudienceWriteResult(resolved, "global", "~/.startd8/config.json")
    if scope == "project":
        target = _write_project_audience(project_root, resolved)
        return AudienceWriteResult(resolved, "project", target)
    raise ValueError(f"unknown scope {scope!r} (expected 'project' or 'global')")


# --- M3: the walk-start surface pre-pass (FR-11 / FR-5 / A-FR11b / A-FR6c) -----------------------


@dataclass(frozen=True)
class PrepassResult:
    """The outcome of :func:`apply_audience_defaults` at a walk-start."""

    audience: KickoffAudience
    ran: bool                              # False for a non-shielding audience (Intermediate/Advanced)
    written: tuple                         # value_paths newly shielded this run
    skipped_ledgered: tuple                # already ledgered (explicit or prior default) — FR-5/idempotent
    blocked_missing_inputs: tuple          # shieldable fields whose input file is absent (A-FR11b)

    @property
    def blocked(self) -> bool:
        """True when the pre-pass wrote nothing because the project isn't instantiated (fail-closed)."""
        return bool(self.blocked_missing_inputs)


def _input_present(project_root: str | Path, file: str) -> bool:
    return (Path(project_root) / "docs" / "kickoff" / "inputs" / file).is_file()


def apply_audience_defaults(
    project_root: str | Path,
    audience: str | KickoffAudience,
    *,
    config: Optional[Any] = None,
    timestamp: Optional[str] = None,
) -> PrepassResult:
    """The walk-start pre-pass (FR-11): pre-fill an audience's shielded defaults into the ledger as
    ``audience-default:<slug>`` entries, so they drop out of the confirm walk (Beginner's reduced
    surface). It is the machine writer M2's provenance was built for.

    Guarantees:
    - **FR-5 / idempotent (R2-S21):** writes ONLY fields not already in the ledger, so it never
      overrides an explicit choice and a second run writes nothing (no ``at`` re-bump).
    - **A-FR6c:** every write is stamped ``audience-default:<slug>`` — it never writes an untagged
      (would-be-``explicit``) entry.
    - **A-FR11b (fail-closed):** if any shieldable field's input YAML is absent (the project isn't
      instantiated), it writes **NOTHING** and reports the missing fields, so a Beginner is never
      silently full-surfaced. The caller directs the user to ``kickoff instantiate`` first.
    - Non-shielding audiences (Intermediate/Advanced) are a no-op (``ran=False``) — byte-identical
      to today.
    """
    from ..kickoff_experience.manifest import audience_defaults, default_config
    from .confirmation import (
        apply_confirm,
        audience_default_provenance,
        build_confirm_plan,
        confirmed_value_paths,
    )

    aud = coerce_audience(audience) or DEFAULT_AUDIENCE
    cfg = config or default_config()
    profile = audience_defaults(aud.value, cfg)
    if not profile:
        return PrepassResult(aud, ran=False, written=(), skipped_ledgered=(), blocked_missing_inputs=())

    ledgered = confirmed_value_paths(project_root)

    # Fail-closed present-file gate (A-FR11b): every field we WOULD write must have its input on disk.
    missing = []
    for vp in profile:
        if vp in ledgered:
            continue
        fdef = cfg.field_by_value_path(vp)
        if fdef is None or fdef.write_target is None:
            continue
        if not _input_present(project_root, fdef.write_target.file):
            missing.append(vp)
    if missing:
        return PrepassResult(
            aud, ran=True, written=(), skipped_ledgered=(), blocked_missing_inputs=tuple(sorted(missing))
        )

    written: list = []
    skipped: list = []
    for vp, value in profile.items():
        if vp in ledgered:
            skipped.append(vp)   # FR-5 + idempotent: never overwrite / re-bump an existing entry
            continue
        plan = build_confirm_plan(
            project_root, vp, value, mode="set", timestamp=timestamp,
            config=cfg, provenance=audience_default_provenance(aud.value),
        )
        apply_confirm(project_root, plan)
        written.append(vp)
    return PrepassResult(
        aud, ran=True, written=tuple(written), skipped_ledgered=tuple(skipped), blocked_missing_inputs=()
    )
