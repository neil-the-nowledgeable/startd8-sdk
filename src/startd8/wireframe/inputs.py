"""Assembly-inputs resolution for the wireframe (FR-W6, FR-W7, FR-W8).

The first **machine-readable** instantiation of the per-project inventory in
``docs/design/kickoff/ASSEMBLY_INPUTS_TEMPLATE.md`` (OQ-3): one or more YAML files mapping each
catalog key to a manifest path (+ optional kickoff status override), merged last-wins, then
overridden by direct CLI flags, falling back to the documented path convention.

Resolution order (FR-W6..W8):
  1. convention defaults — the seven exact catalog filenames (R6-F2; no glob enumeration)
  2. each ``--inputs`` YAML in order, last wins per key (overwrites recorded — R5-S5)
  3. direct CLI flags

All reads are UTF-8 (R5-S2); resolved paths are confined to ``project_root`` (R3-F4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from ..logging_config import get_logger

logger = get_logger(__name__)

# Catalog keys ↔ conventional paths, per ASSEMBLY_INPUTS_TEMPLATE.md §"Contract / assembly
# manifests" (FR-W8/R6-F2: exact per-key filenames — a stray prisma/extra.yaml is never picked up).
CONVENTION_PATHS: Dict[str, str] = {
    "schema": "prisma/schema.prisma",
    "app": "app.yaml",
    "human_inputs": "prisma/human_inputs.yaml",
    "ai_passes": "prisma/ai_passes.yaml",
    "pages": "prisma/pages.yaml",
    "completeness": "prisma/completeness.yaml",
    "views": "prisma/views.yaml",
}
CATALOG_KEYS: Tuple[str, ...] = tuple(CONVENTION_PATHS)

# Kickoff provisioning states accepted as explicit per-key overrides (FR-W6/R2-F1).
_OVERRIDE_STATUSES = {"authored", "placeholder", "absent"}

_SOURCE_CONVENTION = "convention"
_SOURCE_YAML = "yaml"
_SOURCE_FLAG = "flag"


class AssemblyInputsError(ValueError):
    """A fatal assembly-inputs problem (exit 2 at the CLI): unreadable/garbled inputs YAML,
    unknown keys, or a path escaping the project root (R3-F4). Manifest *content* problems are
    NOT this — those degrade to ``invalid`` section statuses (FR-W13)."""


@dataclass(frozen=True)
class ResolvedInput:
    """One catalog entry after resolution: where it points and where that came from (R3-S2)."""

    key: str
    path: Path                      # as declared (relative paths kept for display)
    resolved_path: Path             # absolute, confined to project_root
    source: str                     # convention | yaml | flag
    status_override: Optional[str] = None  # kickoff state declared in the inputs YAML, if any


@dataclass(frozen=True)
class AssemblyInputs:
    """The resolved input set the plan builder consumes (FR-W6..W8)."""

    project_root: Path
    entries: Mapping[str, ResolvedInput]
    merge_warnings: Tuple[Dict[str, str], ...] = field(default_factory=tuple)

    def entry(self, key: str) -> ResolvedInput:
        return self.entries[key]


def _confine(path: Path, project_root: Path, *, origin: str) -> Path:
    """Resolve *path* against *project_root* and reject escapes (R3-F4) before any read."""
    resolved = (project_root / path).resolve() if not path.is_absolute() else path.resolve()
    root = project_root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise AssemblyInputsError(
            f"{origin}: manifest path {str(path)!r} resolves outside the project root "
            f"({resolved} not under {root})"
        )
    return resolved


def _read_inputs_yaml(yaml_path: Path) -> dict:
    """Strict load of one assembly-inputs YAML (loud-fail style, mirrors parse_app_manifest)."""
    try:
        text = yaml_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise AssemblyInputsError(f"{yaml_path}: not valid UTF-8 ({exc})")
    except OSError as exc:
        raise AssemblyInputsError(f"{yaml_path}: unreadable ({exc})")
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise AssemblyInputsError(f"{yaml_path}: malformed YAML ({exc})")
    if not isinstance(data, dict):
        raise AssemblyInputsError(f"{yaml_path}: must be a mapping with a top-level `inputs:` key")
    unknown = set(data) - {"inputs"}
    if unknown:
        raise AssemblyInputsError(f"{yaml_path}: unknown top-level keys {sorted(unknown)}")
    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise AssemblyInputsError(f"{yaml_path}: `inputs:` must be a mapping")
    bad_keys = set(inputs) - set(CATALOG_KEYS)
    if bad_keys:
        raise AssemblyInputsError(
            f"{yaml_path}: unknown catalog keys {sorted(bad_keys)} (known: {list(CATALOG_KEYS)})"
        )
    return inputs


def _parse_entry(yaml_path: Path, key: str, raw: object) -> Tuple[str, Optional[str]]:
    """One per-key entry: ``key: <path>`` or ``key: {path: <p>, status?: <override>}``."""
    if isinstance(raw, str):
        return raw, None
    if isinstance(raw, dict):
        unknown = set(raw) - {"path", "status"}
        if unknown:
            raise AssemblyInputsError(f"{yaml_path}: `{key}` has unknown keys {sorted(unknown)}")
        path = raw.get("path")
        if not path or not isinstance(path, str):
            raise AssemblyInputsError(f"{yaml_path}: `{key}` needs a string `path`")
        status = raw.get("status")
        if status is not None:
            status = str(status)
            if status not in _OVERRIDE_STATUSES:
                raise AssemblyInputsError(
                    f"{yaml_path}: `{key}` status override {status!r} not one of "
                    f"{sorted(_OVERRIDE_STATUSES)}"
                )
        return path, status
    raise AssemblyInputsError(f"{yaml_path}: `{key}` must be a path string or a mapping")


def load_assembly_inputs(
    yaml_paths: Sequence[Path] = (),
    overrides: Optional[Mapping[str, Path]] = None,
    project_root: Optional[Path] = None,
) -> AssemblyInputs:
    """Resolve the assembly input set (FR-W6..W8).

    *yaml_paths* — zero or more assembly-inputs YAML files, merged in order (last wins per key).
    *overrides* — direct CLI flag values per catalog key (highest precedence).
    *project_root* — defaults to the current working directory.
    """
    root = (project_root or Path.cwd()).resolve()
    overrides = overrides or {}
    bad_flags = set(overrides) - set(CATALOG_KEYS)
    if bad_flags:
        raise AssemblyInputsError(f"unknown catalog keys in flag overrides: {sorted(bad_flags)}")

    # 1. Convention defaults (FR-W8) — existence checked later by the plan builder.
    entries: Dict[str, ResolvedInput] = {
        key: ResolvedInput(
            key=key,
            path=Path(rel),
            resolved_path=_confine(Path(rel), root, origin="convention defaults"),
            source=_SOURCE_CONVENTION,
        )
        for key, rel in CONVENTION_PATHS.items()
    }

    # 2. Assembly-inputs YAML files, in order, last wins (FR-W6) — overwrites recorded (R5-S5).
    merge_warnings: List[Dict[str, str]] = []
    seen_from_yaml: Dict[str, str] = {}  # key -> source file that last set it
    for yaml_path in yaml_paths:
        yaml_path = Path(yaml_path)
        inputs = _read_inputs_yaml(yaml_path)
        base = yaml_path.parent  # paths relative to the YAML file's directory (plan Step 1)
        for key in CATALOG_KEYS:  # deterministic catalog order, not dict order
            if key not in inputs:
                continue
            raw_path, status = _parse_entry(yaml_path, key, inputs[key])
            declared = Path(raw_path)
            resolved = _confine(
                declared if declared.is_absolute() else base / declared,
                root,
                origin=str(yaml_path),
            )
            if key in seen_from_yaml:
                merge_warnings.append(
                    {
                        "key": key,
                        "previous_path": str(entries[key].path),
                        "new_path": str(declared),
                        "source_file": str(yaml_path),
                    }
                )
                logger.warning(
                    "assembly-inputs: %s overwrites `%s` (%s -> %s)",
                    yaml_path, key, entries[key].path, declared,
                )
            seen_from_yaml[key] = str(yaml_path)
            entries[key] = ResolvedInput(
                key=key,
                path=declared,
                resolved_path=resolved,
                source=_SOURCE_YAML,
                status_override=status,
            )

    # 3. Direct CLI flags win last (FR-W7).
    for key, flag_path in overrides.items():
        if flag_path is None:
            continue
        declared = Path(flag_path)
        resolved = _confine(declared, root, origin=f"--{key.replace('_', '-')}")
        entries[key] = ResolvedInput(
            key=key, path=declared, resolved_path=resolved, source=_SOURCE_FLAG
        )

    return AssemblyInputs(
        project_root=root, entries=entries, merge_warnings=tuple(merge_warnings)
    )
