"""``build-preferences.yaml`` — how the build factory runs (spend / model routing / profile).

The second FR-VIP value-input class (the fan-out the conventions slice proved). This is the pass
``cli_kickoff.py`` already flags as deferred ("needs a ``build_preferences_text`` pass added to
``extract_manifests``"). Strict round-trip authority (FR-VIP-2): ``parse_build_preferences`` loud-fails
on a malformed sheet so the prose extractor can gate every emitted ``build-preferences.yaml`` against it.

Shape (§2.11): ``domain == "build-preferences"``, optional ``provenance_default``, and the scalar-map
groups ``budgets`` / ``model_routing`` / ``generation`` / ``unattended`` (``unattended.non_interactive``
is a bool, everything else a string — model TIER names never pinned versions). Unknown top-level keys are
rejected (typo guard); group sub-keys are open vocabulary (D-VIP-3). Project-agnostic (FR-VIP-9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import yaml

_TOP_LEVEL_KEYS = frozenset({
    "domain", "provenance_default", "budgets", "model_routing", "generation", "unattended",
    "concierge_agent", "guided",
})


@dataclass(frozen=True)
class BuildPreferencesManifest:
    """A parsed, validated ``build-preferences.yaml`` — the build factory's spend/routing/profile."""

    domain: str = "build-preferences"
    provenance_default: Optional[str] = None
    budgets: Dict[str, str] = field(default_factory=dict)
    model_routing: Dict[str, str] = field(default_factory=dict)
    generation: Dict[str, str] = field(default_factory=dict)
    unattended: Dict[str, object] = field(default_factory=dict)  # values are str or bool
    # The agent spec (provider:model / provider / model-id / alias) the agentic Concierge uses
    # for THIS project (FR-PC-2). A full resolve_agent_spec string, never a tier.
    concierge_agent: Optional[str] = None
    # GE-M0 (FR-GE-3/4): the project's guided-experience preference — **tri-state**. ``None`` is
    # ``unset`` (fall through to the next layer); ``True``/``False`` are explicit ``on``/``off``. An
    # explicit ``False`` here must NOT be lost to a falsy fall-through — it terminates resolution at
    # the routing seam (see ``guided_routing.py``). Stored as a real bool so ``off`` ≠ ``unset``.
    guided: Optional[bool] = None


def _scalar_map(value: object, key: str, *, bool_keys: frozenset = frozenset()) -> Dict[str, object]:
    """Validate a ``- Key: value`` group → a scalar map. Loud-fails on a non-mapping or a nested value.
    Keys in *bool_keys* keep their bool type; every other scalar is carried as a string (open vocab)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"build-preferences.yaml: `{key}` must be a mapping of name -> value")
    out: Dict[str, object] = {}
    for k, v in value.items():
        ks = str(k)
        if ks in bool_keys:
            if not isinstance(v, bool):
                raise ValueError(f"build-preferences.yaml: `{key}.{ks}` must be a boolean (true/false)")
            out[ks] = v
        elif isinstance(v, bool):
            raise ValueError(f"build-preferences.yaml: `{key}.{ks}` must be a string value")
        elif isinstance(v, (str, int, float)):
            out[ks] = str(v)
        else:
            raise ValueError(f"build-preferences.yaml: `{key}.{ks}` must be a scalar value")
    return out


def parse_build_preferences(text: Optional[str]) -> BuildPreferencesManifest:
    """Parse + **strictly** validate ``build-preferences.yaml`` → :class:`BuildPreferencesManifest`.

    Loud-fails (``ValueError``) on a non-mapping root, an unknown top-level key, a wrong ``domain``, a
    non-mapping group, or a non-scalar group value. ``unattended.non_interactive`` must be a bool.
    """
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict):
        raise ValueError("build-preferences.yaml must be a mapping")
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(
            f"build-preferences.yaml: unknown top-level keys {sorted(unknown)} "
            f"(allowed: {sorted(_TOP_LEVEL_KEYS)})"
        )
    domain = data.get("domain", "build-preferences")
    if domain != "build-preferences":
        raise ValueError(
            f"build-preferences.yaml: `domain` must be 'build-preferences', got {domain!r}"
        )
    prov = data.get("provenance_default")
    if prov is not None and not isinstance(prov, str):
        raise ValueError("build-preferences.yaml: `provenance_default` must be a string")
    concierge_agent = data.get("concierge_agent")
    if concierge_agent is not None and not isinstance(concierge_agent, str):
        raise ValueError("build-preferences.yaml: `concierge_agent` must be a string (agent spec)")
    # GE-M0 (FR-GE-3/4): tri-state. Absent ⇒ ``None`` (unset). A present value must be a real bool so
    # that ``guided: false`` (off) stays distinct from absence (unset) — no string coercion here.
    guided = data.get("guided")
    if guided is not None and not isinstance(guided, bool):
        raise ValueError("build-preferences.yaml: `guided` must be a boolean (true/false)")

    return BuildPreferencesManifest(
        domain=domain,
        provenance_default=prov,
        budgets=_scalar_map(data.get("budgets"), "budgets"),
        model_routing=_scalar_map(data.get("model_routing"), "model_routing"),
        generation=_scalar_map(data.get("generation"), "generation"),
        unattended=_scalar_map(
            data.get("unattended"), "unattended", bool_keys=frozenset({"non_interactive"})
        ),
        concierge_agent=concierge_agent,
        guided=guided,
    )
