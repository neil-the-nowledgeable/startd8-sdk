"""RoundRoster + AdvancementSpec — per-run team-lane and individual_invite (FR-DT-20).

``RoundRoster`` is the authored input for every tournament run. After heats, an
``AdvancementSpec`` compiles into one RoundRoster per follow-on lane (main / consolation).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from .entrant_roster import (
    EntrantRoster,
    labs_with_complete_tiers,
    models_for_lab,
    read_yaml_mapping,
)

ROUND_ROSTER_FILE = "round_roster.yaml"
ADVANCEMENT_FILE = "advancement.yaml"
VALID_LANES = frozenset({"heats", "main", "consolation", "unspecified"})


@dataclass
class RoundRoster:
    lane: str
    # None = "use heats default (all complete labs)"; [] = intentionally no team-lane labs.
    team_lane_labs: Optional[List[str]] = None
    individual_invite: List[Any] = field(default_factory=list)  # model ids or {lab, tier}
    parent_run: Optional[str] = None
    # Operator override: enroll every complete-squad lab on Team (ignore cut lists).
    carry_all_team_labs: bool = False

    def __post_init__(self) -> None:
        if self.lane not in VALID_LANES:
            raise ValueError(f"invalid lane {self.lane!r}; expected one of {sorted(VALID_LANES)}")
        if self.lane in ("main", "consolation") and not self.parent_run:
            raise ValueError(f"parent_run required for lane={self.lane!r}")


@dataclass(frozen=True)
class ResolvedEnrollment:
    """Flat model list + per-model classification for provenance (R1-S4)."""

    models: Tuple[str, ...]
    classification: Dict[str, str]  # model → team_lane | invite | both
    team_lane_labs: Tuple[str, ...]
    invite_models: Tuple[str, ...]
    carry_all_team_labs: bool = False


def round_roster_hash(rr: RoundRoster) -> str:
    payload = {
        "lane": rr.lane,
        "parent_run": rr.parent_run,
        "team_lane_labs": rr.team_lane_labs,
        "individual_invite": rr.individual_invite,
        "carry_all_team_labs": bool(rr.carry_all_team_labs),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def load_round_roster(path: Union[str, Path]) -> RoundRoster:
    """Load ``round_roster.yaml``.

    Args:
        path: Path to the authored RoundRoster YAML.

    Returns:
        Parsed RoundRoster. Missing/null ``team_lane_labs`` → None (heats default);
        explicit ``[]`` → invite-only (no team-lane labs).

    Raises:
        OSError: File unreadable.
        ValueError: Malformed fields or invalid lane/parent constraints.
    """
    path = Path(path)
    raw = read_yaml_mapping(path)
    lane = raw.get("lane", "unspecified")
    if "team_lane_labs" not in raw or raw["team_lane_labs"] is None:
        labs: Optional[List[str]] = None
    else:
        if not isinstance(raw["team_lane_labs"], list):
            raise ValueError(f"{path}: team_lane_labs must be a list or null")
        labs = [str(x) for x in raw["team_lane_labs"]]
    invite = raw.get("individual_invite") or []
    if not isinstance(invite, list):
        raise ValueError(f"{path}: individual_invite must be a list")
    parent = raw.get("parent_run")
    if parent is not None:
        parent = str(parent) or None
    return RoundRoster(
        lane=str(lane),
        team_lane_labs=labs,
        individual_invite=list(invite),
        parent_run=parent,
        carry_all_team_labs=bool(raw.get("carry_all_team_labs", False)),
    )


def dump_round_roster(rr: RoundRoster, path: Union[str, Path]) -> None:
    """Write RoundRoster as YAML (for run-dir provenance stamps)."""
    path = Path(path)
    data = {
        "lane": rr.lane,
        "parent_run": rr.parent_run,
        "team_lane_labs": rr.team_lane_labs,
        "individual_invite": rr.individual_invite,
        "carry_all_team_labs": bool(rr.carry_all_team_labs),
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def load_advancement(path: Union[str, Path]) -> Dict[str, Any]:
    """Load AdvancementSpec YAML (main/consolation lab lists + optional invites).

    Raises:
        OSError: File unreadable.
        ValueError: Non-mapping root or non-list main/consolation.
    """
    path = Path(path)
    raw = read_yaml_mapping(path)
    for key in ("main", "consolation"):
        if key in raw and not isinstance(raw[key], list):
            raise ValueError(f"{path}: {key} must be a list of lab ids")
    return raw


def compile_advancement(adv: Dict[str, Any], lane: str) -> RoundRoster:
    """Compile AdvancementSpec → RoundRoster for ``lane`` in {main, consolation}.

    When ``carry_all_team_labs`` is true, authored ``main``/``consolation`` cuts are
    retained for provenance but enrollment expands to every complete-squad lab
    (see ``resolve_enrollment``).

    Args:
        adv: Parsed advancement mapping (``parent_run`` required).
        lane: Target lane (``main`` or ``consolation``).

    Returns:
        RoundRoster with authored team_lane_labs and optional individual_invite.

    Raises:
        ValueError: Invalid lane or missing parent_run.
    """
    if lane not in ("main", "consolation"):
        raise ValueError(f"compile_advancement lane must be main|consolation, got {lane!r}")
    labs = [str(x) for x in (adv.get(lane) or [])]
    parent = adv.get("parent_run")
    if not parent:
        raise ValueError("advancement.parent_run is required")
    invite = list(adv.get("individual_invite") or [])
    return RoundRoster(
        lane=lane,
        team_lane_labs=labs,
        individual_invite=invite,
        parent_run=str(parent),
        carry_all_team_labs=bool(adv.get("carry_all_team_labs", False)),
    )


def _resolve_invite_item(item: Any, roster: EntrantRoster) -> List[str]:
    if isinstance(item, str):
        if item not in roster:
            raise ValueError(f"individual_invite unknown model id: {item!r}")
        return [item]
    if isinstance(item, dict):
        lab = item.get("lab")
        tier = item.get("tier")
        if not lab or not tier:
            raise ValueError(f"individual_invite selector requires lab+tier: {item!r}")
        models = models_for_lab(roster, str(lab), tiers=[str(tier)])
        if not models:
            raise ValueError(f"individual_invite no models for lab={lab!r} tier={tier!r}")
        return models
    raise ValueError(f"individual_invite entry must be model id or {{lab, tier}}: {item!r}")


def resolve_enrollment(
    rr: RoundRoster,
    roster: EntrantRoster,
    *,
    heats_default_complete_labs: bool = True,
) -> ResolvedEnrollment:
    """Union team-lane models + invites; classify each model; fail closed on unknown labs/ids.

    ``team_lane_labs is None`` on heats → default to all complete labs in the entrant roster.
    ``team_lane_labs == []`` → no team-lane labs (invite-only Individual deep is allowed).
    """
    known_labs = {m.lab for m in roster.values()}
    if rr.carry_all_team_labs:
        # Operator flag: every complete-squad lab stays on Team through this round.
        team_labs = labs_with_complete_tiers(roster, roster.keys())
    elif rr.team_lane_labs is None:
        if rr.lane == "heats" and heats_default_complete_labs:
            team_labs = labs_with_complete_tiers(roster, roster.keys())
        else:
            team_labs = []
    else:
        team_labs = list(rr.team_lane_labs)

    for lab in team_labs:
        if lab not in known_labs:
            raise ValueError(f"unknown team_lane lab: {lab!r}")

    team_models: List[str] = []
    for lab in team_labs:
        team_models.extend(models_for_lab(roster, lab, tiers=("flagship", "mid", "fast")))

    invite_models: List[str] = []
    for item in rr.individual_invite:
        invite_models.extend(_resolve_invite_item(item, roster))

    team_set = set(team_models)
    invite_set = set(invite_models)
    all_models = sorted(team_set | invite_set)
    classification: Dict[str, str] = {}
    for m in all_models:
        in_t, in_i = m in team_set, m in invite_set
        if in_t and in_i:
            classification[m] = "both"
        elif in_t:
            classification[m] = "team_lane"
        else:
            classification[m] = "invite"

    return ResolvedEnrollment(
        models=tuple(all_models),
        classification=classification,
        team_lane_labs=tuple(team_labs),
        invite_models=tuple(sorted(invite_set - team_set)),
        carry_all_team_labs=bool(rr.carry_all_team_labs),
    )


def find_round_roster(run_dir: Union[str, Path]) -> Optional[Path]:
    p = Path(run_dir) / ROUND_ROSTER_FILE
    return p if p.is_file() else None
