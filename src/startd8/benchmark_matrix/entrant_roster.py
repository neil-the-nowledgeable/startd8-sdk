"""Entrant roster — lab/tier metadata for dual-track Individual + Team scoring.

Authored config maps each enrolled model id → ``{lab, tier}``. Lab identity is **not** the
provider prefix (OpenRouter collapses many labs under ``openrouter:``). See
Summer2026 ``docs/DUAL_TRACK_SCOREBOARD_REQUIREMENTS_v0.5.md`` FR-DT-2/3.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)

VALID_TIERS = frozenset({"flagship", "mid", "fast", "solo"})
ENTRANT_ROSTER_FILE = "entrant_roster.yaml"


@dataclass(frozen=True)
class EntrantMeta:
    """One enrolled model’s lab/tier tags."""

    model: str
    lab: str
    tier: str
    display_name: Optional[str] = None

    def __post_init__(self) -> None:
        if self.tier not in VALID_TIERS:
            raise ValueError(
                f"invalid tier {self.tier!r} for model {self.model!r}; "
                f"expected one of {sorted(VALID_TIERS)}"
            )
        if not self.lab:
            raise ValueError(f"lab required for model {self.model!r}")
        if not self.model:
            raise ValueError("model id must be non-empty")


EntrantRoster = Dict[str, EntrantMeta]  # model id → meta


def read_yaml_mapping(path: Path) -> dict:
    """Load a YAML file that must be a top-level mapping (not a bare list/scalar).

    Args:
        path: Path to a UTF-8 YAML file.

    Returns:
        The top-level mapping.

    Raises:
        OSError: File unreadable.
        ValueError: Invalid YAML or non-mapping root (including empty/`null` files).
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OSError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping, got {type(raw).__name__}")
    return raw


def roster_hash(roster: EntrantRoster) -> str:
    """Stable content fingerprint for provenance (order-independent)."""
    payload = [
        {
            "model": m.model,
            "lab": m.lab,
            "tier": m.tier,
            **({"display_name": m.display_name} if m.display_name else {}),
        }
        for m in sorted(roster.values(), key=lambda e: e.model)
    ]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def load_entrant_roster(path: Union[str, Path]) -> EntrantRoster:
    """Load ``entrant_roster.yaml``.

    Args:
        path: Path to the authored roster YAML.

    Returns:
        Mapping of model id → EntrantMeta.

    Raises:
        OSError: File unreadable.
        ValueError: Missing/malformed fields, unknown tier, or duplicate model.
    """
    path = Path(path)
    raw = read_yaml_mapping(path)
    if "entrants" not in raw:
        raise ValueError(f"{path}: expected top-level 'entrants' list")
    rows = raw["entrants"]
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path}: 'entrants' must be a non-empty list")
    out: EntrantRoster = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{path}: entrants[{i}] must be a mapping")
        model = row.get("model")
        lab = row.get("lab")
        tier = row.get("tier")
        if not model or not lab or not tier:
            raise ValueError(
                f"{path}: entrants[{i}] requires non-empty model, lab, tier "
                f"(got model={model!r}, lab={lab!r}, tier={tier!r})"
            )
        model_s, lab_s, tier_s = str(model), str(lab), str(tier)
        if model_s in out:
            raise ValueError(f"{path}: duplicate model {model_s!r}")
        out[model_s] = EntrantMeta(
            model=model_s,
            lab=lab_s,
            tier=tier_s,
            display_name=(str(row["display_name"]) if row.get("display_name") else None),
        )
    logger.debug("loaded entrant roster %s (%d models)", path, len(out))
    return out


def find_entrant_roster(run_dir: Union[str, Path]) -> Optional[Path]:
    """Return ``<run_dir>/entrant_roster.yaml`` if present."""
    p = Path(run_dir) / ENTRANT_ROSTER_FILE
    return p if p.is_file() else None


def models_for_lab(
    roster: EntrantRoster,
    lab: str,
    *,
    tiers: Optional[Iterable[str]] = None,
) -> List[str]:
    """Model ids for ``lab``, optionally filtered to ``tiers`` (sorted)."""
    want = frozenset(tiers) if tiers is not None else None
    return sorted(
        m.model
        for m in roster.values()
        if m.lab == lab and (want is None or m.tier in want)
    )


def labs_with_complete_tiers(
    roster: EntrantRoster,
    models_present: Iterable[str],
) -> List[str]:
    """Labs that have flagship+mid+fast among ``models_present`` (FR-DT-4 conjunct)."""
    present = set(models_present)
    by_lab: Dict[str, set] = {}
    for mid in present:
        meta = roster.get(mid)
        if meta is None or meta.tier == "solo":
            continue
        by_lab.setdefault(meta.lab, set()).add(meta.tier)
    return sorted(
        lab for lab, tiers in by_lab.items() if {"flagship", "mid", "fast"} <= tiers
    )
