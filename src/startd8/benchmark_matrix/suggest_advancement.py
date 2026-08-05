"""Suggest-don't-auto-advance (FR-DT-12 / M6) — $0 Team ranking → AdvancementSpec draft.

Never mutates ``advancement.yaml`` unless the caller adopts explicitly. Ties (OQ-DT-6 unresolved)
are marked ``tied: true`` / ``needs_operator_choice: true`` rather than inventing a unique cut.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import yaml

from .aggregate import aggregate_cells
from .entrant_roster import EntrantRoster
from .team_score import TeamRow, team_rows

CELLS_FILE = "cells.json"
AGGREGATE_FILE = "aggregate.json"
SUGGESTED_FILE = "advancement.suggested.yaml"


@dataclass
class AdvancementSuggestion:
    """Draft AdvancementSpec fields — operator must adopt before a deep run."""

    parent_run: str
    main_suggested: List[str]
    consolation_suggested: List[str]
    individual_invite_suggested: List[Any] = field(default_factory=list)
    tied: bool = False
    needs_operator_choice: bool = False
    tie_groups: List[List[str]] = field(default_factory=list)
    metric_id: str = "mean_tier_quality_v1"
    main_n: int = 4
    notes: List[str] = field(default_factory=list)
    # When true, operator intends all complete labs on Team next round (no cut).
    carry_all_team_labs: bool = False

    def to_mapping(self) -> Dict[str, Any]:
        return asdict(self)


def _load_agg(run_dir: Path) -> Dict:
    from .runner import CellResult

    agg_path = run_dir / AGGREGATE_FILE
    if agg_path.is_file():
        return json.loads(agg_path.read_text(encoding="utf-8"))
    cells_path = run_dir / CELLS_FILE
    if not cells_path.is_file():
        raise FileNotFoundError(f"{run_dir}: need {AGGREGATE_FILE} or {CELLS_FILE}")
    raw = json.loads(cells_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{cells_path}: expected a list of cells")
    cells = [CellResult.from_dict(c) if isinstance(c, dict) else c for c in raw]
    return aggregate_cells(cells)


def _quality_tie_groups(rows: Sequence[TeamRow], *, eps: float = 1e-9) -> List[List[str]]:
    """Group consecutive labs with equal team quality (already quality-sorted)."""
    if not rows:
        return []
    groups: List[List[str]] = []
    cur = [rows[0].lab]
    q = rows[0].quality
    for r in rows[1:]:
        if abs(r.quality - q) <= eps:
            cur.append(r.lab)
        else:
            if len(cur) > 1:
                groups.append(cur)
            cur = [r.lab]
            q = r.quality
    if len(cur) > 1:
        groups.append(cur)
    return groups


def _cut_respecting_ties(
    ranked: Sequence[TeamRow],
    n: int,
    *,
    eps: float = 1e-9,
) -> tuple[List[str], bool, bool]:
    """Take top-N but never split a quality-tie group.

    Returns (labs, tied_at_cut, needs_operator_choice).
    If the Nth lab sits inside a larger tie, expand to the whole group and set needs_operator_choice.
    """
    if n <= 0 or not ranked:
        return [], False, False
    if n >= len(ranked):
        labs = [r.lab for r in ranked]
        tied = any(
            abs(ranked[i].quality - ranked[i - 1].quality) <= eps
            for i in range(1, len(ranked))
        )
        return labs, tied, False

    boundary_q = ranked[n - 1].quality
    # Expand forward while same quality as boundary (never split a tie at the cut).
    end = n
    while end < len(ranked) and abs(ranked[end].quality - boundary_q) <= eps:
        end += 1

    if end > n:
        labs = [r.lab for r in ranked[:end]]
        return labs, True, True
    labs = [r.lab for r in ranked[:n]]
    tied = any(
        abs(ranked[i].quality - ranked[i - 1].quality) <= eps for i in range(1, n)
    )
    return labs, tied, False


def suggest_invites_cut_mid_fast(
    roster: EntrantRoster,
    *,
    main_labs: Sequence[str],
) -> List[Dict[str, str]]:
    """All mid+fast models for labs not on next main (FR-DT-19 / OQ-DT-10 template)."""
    main = set(main_labs)
    out: List[Dict[str, str]] = []
    for meta in sorted(roster.values(), key=lambda m: (m.lab, m.tier, m.model)):
        if meta.lab in main:
            continue
        if meta.tier in ("mid", "fast"):
            out.append({"lab": meta.lab, "tier": meta.tier})
    # Deduplicate selectors (one per lab+tier)
    seen = set()
    uniq: List[Dict[str, str]] = []
    for sel in out:
        key = (sel["lab"], sel["tier"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(sel)
    return uniq


def suggest_invites_top_k_individual(
    agg: Dict,
    roster: EntrantRoster,
    *,
    main_labs: Sequence[str],
    k: int = 3,
) -> List[str]:
    """Top-K Individual models (by quality_median) whose lab ∉ next team-lane."""
    from .aggregate import rank_models_by_quality

    main = set(main_labs)
    picks: List[str] = []
    for model, *_rest in rank_models_by_quality(agg):
        meta = roster.get(model)
        if meta is None:
            continue
        if meta.lab in main:
            continue
        picks.append(model)
        if len(picks) >= k:
            break
    return picks


def build_suggestion(
    run_dir: Union[str, Path],
    roster: EntrantRoster,
    *,
    main_n: int = 4,
    consolation: str = "rest",  # rest | all | none
    suggest_invites: Optional[str] = None,  # cut-mid-fast | top-k-individual[=N]
    team_lane: Optional[Sequence[str]] = None,
    carry_all_team_labs: bool = False,
) -> AdvancementSuggestion:
    """Build an AdvancementSuggestion from a scored parent run dir."""
    run_dir = Path(run_dir)
    agg = _load_agg(run_dir)
    rows = team_rows(agg, roster, team_lane=team_lane)
    if not rows:
        return AdvancementSuggestion(
            parent_run=str(run_dir),
            main_suggested=[],
            consolation_suggested=[],
            notes=["no eligible Team rows — nothing to suggest"],
            main_n=main_n,
            carry_all_team_labs=carry_all_team_labs,
        )

    eligible = [r.lab for r in rows]
    if carry_all_team_labs:
        main = list(eligible)
        tied_cut, needs = False, False
        tie_groups: List[List[str]] = []
        cons: List[str] = []
        notes = [
            "carry_all_team_labs=true — main_suggested = all eligible Team labs; no cut applied",
        ]
        main_set = set(main)
    else:
        main, tied_cut, needs = _cut_respecting_ties(rows, main_n)
        tie_groups = _quality_tie_groups(rows)
        main_set = set(main)
        notes = []
        if consolation == "none":
            cons = []
        elif consolation == "all":
            cons = list(eligible)
        else:  # rest
            cons = [lab for lab in eligible if lab not in main_set]

    invites: List[Any] = []
    if suggest_invites and not carry_all_team_labs:
        mode, _, rest = suggest_invites.partition("=")
        if mode == "cut-mid-fast":
            invites = suggest_invites_cut_mid_fast(roster, main_labs=main)
            notes.append("individual_invite_suggested via cut-mid-fast (adopt to copy)")
        elif mode == "top-k-individual":
            try:
                k = int(rest) if rest else 3
            except ValueError as exc:
                raise ValueError(
                    f"top-k-individual expects integer K, got {rest!r}"
                ) from exc
            if k < 1:
                raise ValueError(f"top-k-individual K must be >= 1, got {k}")
            invites = suggest_invites_top_k_individual(agg, roster, main_labs=main, k=k)
            notes.append(f"individual_invite_suggested via top-k-individual k={k}")
        else:
            raise ValueError(
                f"unknown --suggest-invites={suggest_invites!r}; "
                "expected cut-mid-fast or top-k-individual[=N]"
            )

    if tied_cut:
        notes.append(
            "main cut fell inside a quality-tie group; expanded suggestion and set "
            "needs_operator_choice (OQ-DT-6 unresolved — do not invent unique order)"
        )

    return AdvancementSuggestion(
        parent_run=str(run_dir),
        main_suggested=main,
        consolation_suggested=cons,
        individual_invite_suggested=invites,
        tied=bool(tied_cut or tie_groups),
        needs_operator_choice=needs,
        tie_groups=tie_groups,
        main_n=main_n,
        notes=notes,
        carry_all_team_labs=carry_all_team_labs,
    )


def dump_suggestion(sug: AdvancementSuggestion, path: Union[str, Path]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(sug.to_mapping(), sort_keys=False), encoding="utf-8")


def adopt_suggestion(
    suggested_path: Union[str, Path],
    dest: Union[str, Path],
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Copy suggestion into an authored AdvancementSpec shape (never silent).

    Maps ``main_suggested`` → ``main``, ``consolation_suggested`` → ``consolation``,
    ``individual_invite_suggested`` → ``individual_invite``.

    Raises:
        FileExistsError: ``dest`` exists and ``force`` is False (FR-DT-12: no silent overwrite).
        ValueError: Malformed suggestion mapping.
        OSError: Unreadable suggestion path.
    """
    suggested_path = Path(suggested_path)
    try:
        raw = yaml.safe_load(suggested_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OSError(f"cannot read suggestion {suggested_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"{suggested_path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{suggested_path}: expected a mapping, got {type(raw).__name__}")
    out = {
        "parent_run": raw.get("parent_run"),
        "main": list(raw.get("main_suggested") or []),
        "consolation": list(raw.get("consolation_suggested") or []),
        "individual_invite": list(raw.get("individual_invite_suggested") or []),
        "carry_all_team_labs": bool(raw.get("carry_all_team_labs", False)),
    }
    dest = Path(dest)
    if dest.is_file() and not force:
        raise FileExistsError(
            f"{dest} already exists — re-run with force=True / --force after review "
            f"(refuses silent overwrite of authored AdvancementSpec)"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(out, sort_keys=False), encoding="utf-8")
    return out
