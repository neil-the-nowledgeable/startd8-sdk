"""M3 — Kickoff experience config (step/field model) + config linter.

This is **SDK-internal config**, NOT a new manifest grammar kind (OQ-1: no manifest-kind registry
exists; the grammar is frozen and this is a surface over it). It describes the kickoff *experience*
as data: ordered steps, the fields per step, each field's canonical ``value_path`` (the join key
back to extraction state / write-back), widget hint, grammar help, and provenance default.

The captured fields write back into ``docs/kickoff/inputs/*.yaml`` (the four input domains). Each
writable field carries a :class:`WriteTarget` (file + dotted key) — this is the FR-NEW-6 mapping
table, and the **server-side allow-list** M6 enforces so a surface-supplied ``value_path`` can never
redirect a write outside the configured inputs (R1-F6 / R1-S8).

``lint_config`` (R3-S2) runs **before** the surfaces are generated, so a typo cannot become a silent
missing / unwritable field or a parity drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

INPUTS_DIR = "docs/kickoff/inputs"

# The four kickoff input domains (the only legal write-back files — concierge package contract).
KNOWN_INPUT_FILES: frozenset[str] = frozenset(
    {
        "business-targets.yaml",
        "observability.yaml",
        "conventions.yaml",
        "build-preferences.yaml",
    }
)

# Widgets the deterministic renderer (M4) + TUI (M5) both know how to render.
WIDGETS: frozenset[str] = frozenset({"text", "textarea", "number", "select", "checkbox"})

# Provenance markers the kickoff package recognizes (KICKOFF_INPUT_PACKAGE_GUIDE).
PROVENANCE_DEFAULTS: frozenset[str] = frozenset(
    {"authored", "estimate", "config-default", "templated"}
)


@dataclass(frozen=True)
class WriteTarget:
    """Where a captured field value lands (FR-NEW-6). *file* is relative to ``INPUTS_DIR``."""

    file: str        # e.g. "conventions.yaml"
    key: str         # dotted YAML key path, e.g. "data_model.money"

    def as_tuple(self) -> Tuple[str, str]:
        return (self.file, self.key)


@dataclass(frozen=True)
class FieldDef:
    """One author-capturable field in the experience."""

    key: str                       # stable id, unique within the config
    label: str
    widget: str                    # one of WIDGETS
    value_path: str                # canonical join key, unique (e.g. "conventions.yaml#/language")
    grammar_help: str              # "what to type" — required (R3-S2)
    provenance_default: str        # one of PROVENANCE_DEFAULTS
    required: bool = False
    write_target: Optional[WriteTarget] = None
    choices: Tuple[str, ...] = ()  # required when widget == "select"
    value_help: Optional[str] = None  # "what this unlocks" (R2-F4 — field exists; Phase-2 enforced)

    @property
    def writable(self) -> bool:
        return self.write_target is not None

    def to_dict(self) -> dict:
        d = {
            "key": self.key,
            "label": self.label,
            "widget": self.widget,
            "value_path": self.value_path,
            "grammar_help": self.grammar_help,
            "provenance_default": self.provenance_default,
            "required": self.required,
        }
        if self.write_target is not None:
            d["write_target"] = {"file": self.write_target.file, "key": self.write_target.key}
        if self.choices:
            d["choices"] = list(self.choices)
        if self.value_help is not None:
            d["value_help"] = self.value_help
        return d


@dataclass(frozen=True)
class StepDef:
    """An ordered step of the experience (typically one input domain)."""

    key: str
    title: str
    intro: str
    fields: Tuple[FieldDef, ...]

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "intro": self.intro,
            "fields": [f.to_dict() for f in self.fields],
        }


@dataclass(frozen=True)
class KickoffExperienceConfig:
    """The whole experience config — ordered steps of fields."""

    steps: Tuple[StepDef, ...]

    def iter_fields(self) -> Iterator[FieldDef]:
        for step in self.steps:
            yield from step.fields

    def field_by_value_path(self, value_path: str) -> Optional[FieldDef]:
        for f in self.iter_fields():
            if f.value_path == value_path:
                return f
        return None

    def writable_fields(self) -> List[FieldDef]:
        return [f for f in self.iter_fields() if f.writable]

    def allowed_write_targets(self) -> frozenset[Tuple[str, str]]:
        """The M6 server-side allow-list: every (file, key) a capture may write (R1-F6/R1-S8)."""
        return frozenset(f.write_target.as_tuple() for f in self.writable_fields())

    def allowed_value_paths(self) -> frozenset[str]:
        """The set of value_paths a surface may submit for capture (allow-list, R1-F6)."""
        return frozenset(f.value_path for f in self.writable_fields())

    def to_dict(self) -> dict:
        return {"steps": [s.to_dict() for s in self.steps]}


# --- config linter (R3-S2) ---------------------------------------------------------------------


@dataclass(frozen=True)
class LintIssue:
    field_key: str
    code: str
    message: str


def lint_config(config: KickoffExperienceConfig) -> List[LintIssue]:
    """Validate the experience config (R3-S2). Returns issues; empty list == clean.

    Enforces: unique field keys, unique ``value_path``, supported widget, ``select`` has choices,
    non-empty grammar help, recognized provenance, and (for writable/required fields) exactly one
    write mapping into a known inputs file.
    """
    issues: List[LintIssue] = []
    seen_keys: set[str] = set()
    seen_paths: set[str] = set()

    for f in config.iter_fields():
        if f.key in seen_keys:
            issues.append(LintIssue(f.key, "duplicate_key", f"duplicate field key {f.key!r}"))
        seen_keys.add(f.key)

        if f.value_path in seen_paths:
            issues.append(
                LintIssue(f.key, "duplicate_value_path", f"duplicate value_path {f.value_path!r}")
            )
        seen_paths.add(f.value_path)

        if f.widget not in WIDGETS:
            issues.append(
                LintIssue(f.key, "bad_widget", f"widget {f.widget!r} not in {sorted(WIDGETS)}")
            )
        if f.widget == "select" and not f.choices:
            issues.append(LintIssue(f.key, "missing_choices", "select widget needs choices"))

        if not f.grammar_help.strip():
            issues.append(LintIssue(f.key, "missing_help", "grammar_help is required"))

        if f.provenance_default not in PROVENANCE_DEFAULTS:
            issues.append(
                LintIssue(
                    f.key,
                    "bad_provenance",
                    f"provenance_default {f.provenance_default!r} not in {sorted(PROVENANCE_DEFAULTS)}",
                )
            )

        # A required field must be capturable (have exactly one write mapping into a known file).
        if f.required and f.write_target is None:
            issues.append(
                LintIssue(f.key, "required_unwritable", "required field has no write_target")
            )
        if f.write_target is not None:
            if f.write_target.file not in KNOWN_INPUT_FILES:
                issues.append(
                    LintIssue(
                        f.key,
                        "unknown_write_file",
                        f"write_target.file {f.write_target.file!r} not in {sorted(KNOWN_INPUT_FILES)}",
                    )
                )
            if not f.write_target.key.strip():
                issues.append(LintIssue(f.key, "empty_write_key", "write_target.key is empty"))
            if ".." in f.write_target.key or "/" in f.write_target.key:
                issues.append(
                    LintIssue(f.key, "unsafe_write_key", "write_target.key must be a dotted key")
                )

    # M3 (FR-7/FR-8, A-OQ9): every audience-profile default must reference a real, confirmable, and
    # SHIELDABLE field, with a value valid for that field. This is what stops a profile from silently
    # pre-filling a field that has no safe default (A-OQ9) or an out-of-choices value.
    by_vp = {f.value_path: f for f in config.iter_fields()}
    confirmable = {
        f.value_path for f in config.writable_fields()
        if f.provenance_default in _CONFIRMABLE_PROVENANCE
    }
    for audience, profile in AUDIENCE_PROFILES.items():
        fkey = f"audience:{audience}"
        for vp, value in profile.items():
            fdef = by_vp.get(vp)
            if fdef is None:
                issues.append(LintIssue(
                    fkey, "profile_unknown_field",
                    f"audience {audience!r} default references unknown value_path {vp!r}"))
                continue
            if vp not in confirmable:
                issues.append(LintIssue(
                    fkey, "profile_not_confirmable",
                    f"audience {audience!r} default {vp!r} is not a confirmable (defaulted) field"))
            if vp not in SHIELDABLE_VALUE_PATHS:
                issues.append(LintIssue(
                    fkey, "profile_not_shieldable",
                    f"audience {audience!r} default {vp!r} has no safe default (A-OQ9) — cannot shield"))
            if fdef.choices and value not in fdef.choices:
                issues.append(LintIssue(
                    fkey, "profile_bad_value",
                    f"audience {audience!r} default {vp!r}={value!r} not in choices {fdef.choices}"))

    return issues


# --- the default seeded config (covers the four input domains) ----------------------------------


def _vp(file: str, key: str) -> str:
    """Canonical value_path for an input-domain field: ``<file>#/<dotted-key>``."""
    return f"{file}#/{key}"


def default_config() -> KickoffExperienceConfig:
    """The seeded kickoff experience: one step per input domain, representative capturable fields.

    Grounded in the real input-domain templates (conventions/build-preferences have stable keys;
    business-targets/observability are more free-form so we seed the stable anchors).
    """
    conv = "conventions.yaml"
    build = "build-preferences.yaml"
    biz = "business-targets.yaml"
    obs = "observability.yaml"

    conventions_step = StepDef(
        key="conventions",
        title="Technology conventions",
        intro="The stack and modeling choices all generated code must FOLLOW (not invent).",
        fields=(
            FieldDef(
                key="conv_language",
                label="Primary language",
                widget="select",
                choices=("python",),
                value_path=_vp(conv, "language"),
                grammar_help="The implementation language. Must match build-preferences generation.language.",
                provenance_default="authored",
                required=True,
                write_target=WriteTarget(conv, "language"),
                value_help="Determines the entire generated stack and toolchain.",
            ),
            FieldDef(
                key="conv_framework",
                label="Web framework",
                widget="select",
                choices=("fastapi",),
                value_path=_vp(conv, "stack.framework"),
                grammar_help="The web framework the generated app is built on.",
                provenance_default="authored",
                required=True,
                write_target=WriteTarget(conv, "stack.framework"),
            ),
            FieldDef(
                key="conv_money",
                label="Money representation",
                widget="select",
                choices=("cents", "float"),
                value_path=_vp(conv, "data_model.money"),
                grammar_help="How money is stored. 'cents' = integer minor units (exact sums).",
                provenance_default="authored",
                required=True,
                write_target=WriteTarget(conv, "data_model.money"),
                value_help="Prevents the generator from inventing a money type per entity.",
            ),
            FieldDef(
                key="conv_datetime",
                label="Datetime policy",
                widget="select",
                choices=("utc", "local"),
                value_path=_vp(conv, "data_model.datetime"),
                grammar_help="Timezone policy for stored timestamps.",
                provenance_default="authored",
                write_target=WriteTarget(conv, "data_model.datetime"),
            ),
        ),
    )

    build_step = StepDef(
        key="build-preferences",
        title="Build preferences",
        intro="How the build factory runs: spend ceilings, model routing, generation profile.",
        fields=(
            FieldDef(
                key="build_per_run",
                label="Per-pipeline-run budget",
                widget="text",
                value_path=_vp(build, "budgets.per_pipeline_run"),
                grammar_help='A dollar ceiling per run, e.g. "$5.00". Non-prod default: test $5 / internal $10.',
                provenance_default="estimate",
                write_target=WriteTarget(build, "budgets.per_pipeline_run"),
            ),
            FieldDef(
                key="build_profile",
                label="Generation profile",
                widget="select",
                choices=("full", "observability"),
                value_path=_vp(build, "generation.profile"),
                grammar_help="Which generation profile to run.",
                provenance_default="authored",
                write_target=WriteTarget(build, "generation.profile"),
            ),
        ),
    )

    business_step = StepDef(
        key="business-targets",
        title="Business targets",
        intro="What success looks like in numbers (provenance flips to 'authored' on a real decision).",
        fields=(
            FieldDef(
                key="biz_monetization_mode",
                label="Monetization mode (now)",
                widget="select",
                choices=("free-during-demo", "live"),
                value_path=_vp(biz, "monetization.mode_now"),
                grammar_help="Whether the product is monetizing now or in a demo/free phase.",
                provenance_default="estimate",
                write_target=WriteTarget(biz, "monetization.mode_now"),
            ),
        ),
    )

    observability_step = StepDef(
        key="observability",
        title="Observability",
        intro="SLOs, alert thresholds, and on-call contacts for the generated app.",
        fields=(
            FieldDef(
                key="obs_provenance",
                label="Observability provenance",
                widget="select",
                choices=("authored", "config-default"),
                value_path=_vp(obs, "provenance_default"),
                grammar_help="Whether the observability defaults are authored or industry config-defaults.",
                provenance_default="config-default",
                write_target=WriteTarget(obs, "provenance_default"),
            ),
        ),
    )

    return KickoffExperienceConfig(
        steps=(conventions_step, build_step, business_step, observability_step)
    )


# --- audience default profiles (M3: FR-7/FR-8, A-OQ9) -------------------------------------------

# The template-provenance markers that make a writable field *confirmable* (worth a human decision).
# Mirrors ``confirmation._CONFIRMABLE_PROVENANCE`` (kept as a literal here to avoid a manifest→
# confirmation import cycle; a test asserts the two agree).
_CONFIRMABLE_PROVENANCE: frozenset[str] = frozenset({"estimate", "config-default"})

#: A confirmable field is **shieldable** (an audience may silently pre-fill it) ONLY if it has a
#: safe, universally-reasonable, **reversible** default (A-OQ9 / R1-F5). A confirmable field WITHOUT
#: one is never shielded — always prompted, even for Beginner. A future confirmable field with no safe
#: default is simply omitted here, and ``lint_config`` then rejects any profile that references it.
SHIELDABLE_VALUE_PATHS: frozenset[str] = frozenset({
    "build-preferences.yaml#/budgets.per_pipeline_run",   # a low non-prod $ ceiling — safe, reversible
    "business-targets.yaml#/monetization.mode_now",        # "free-during-demo" — safe (not charging)
    "observability.yaml#/provenance_default",              # "config-default" — safe industry defaults
})

#: Per-audience default profiles (FR-7), PARTIAL by design (FR-8): a profile lists only the fields it
#: shields with a safe default; anything unlisted is left to the normal walk. **Beginner** shields all
#: shieldable fields (reduced surface); **Intermediate** / **Advanced** shield nothing (today's full
#: walk — byte-identical). Keyed by the audience SLUG (a plain string) so this module never imports the
#: ``KickoffAudience`` enum (no cycle). Every entry is validated by ``lint_config``.
AUDIENCE_PROFILES: dict[str, dict[str, str]] = {
    "beginner": {
        "build-preferences.yaml#/budgets.per_pipeline_run": "$5.00",
        "business-targets.yaml#/monetization.mode_now": "free-during-demo",
        "observability.yaml#/provenance_default": "config-default",
    },
    "intermediate": {},
    "advanced": {},
}


def audience_defaults(audience: str, config: Optional[KickoffExperienceConfig] = None) -> dict:
    """The ``{value_path: safe_default}`` a given audience pre-fills (FR-7).

    ``{}`` for an unknown audience or one that shields nothing (Intermediate/Advanced). Partial by
    design (FR-8) — the returned map is a copy, safe for the caller to iterate/mutate.
    """
    return dict(AUDIENCE_PROFILES.get(audience, {}))
