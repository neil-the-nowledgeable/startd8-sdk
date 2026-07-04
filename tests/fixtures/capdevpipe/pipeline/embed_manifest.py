"""Load and resolve embed-manifest.yaml — authoritative embed inventory (FR-1, FR-2).

Provides manifest load, profile resolution via ``extends``, managed-path listing, and the
shared install planner ``resolve_install_plan()`` consumed by ``pipeline embed``,
``install-cap-dev-pipe.sh``, and the SDK installer (A2+).
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

SUPPORTED_SCHEMA_VERSION = 1
EMBED_DIR_NAME = ".cap-dev-pipe"
INSTALL_MANIFEST_FILENAME = ".install-manifest.json"
INSTALL_MANIFEST_SCHEMA_VERSION = 1

_MANIFEST_FILENAME = "embed-manifest.yaml"
_LN_S_EMBED_RE = re.compile(r"^\s*ln -s\s+\$CAP_DEV_PIPE/(\S+)\s*$", re.MULTILINE)

CLAUDE_EMBED_BLOCK_START = "<!-- cap-dev-pipe-embed-block:start -->"
CLAUDE_EMBED_BLOCK_END = "<!-- cap-dev-pipe-embed-block:end -->"
_CLAUDE_EMBED_BLOCK_RE = re.compile(
    re.escape(CLAUDE_EMBED_BLOCK_START)
    + r"\s*```bash\n.*?\n```\s*"
    + re.escape(CLAUDE_EMBED_BLOCK_END),
    re.DOTALL,
)

_PATH_LIST_KEYS = frozenset(
    {"scripts", "python_aliases", "resource_trees", "packages", "copy_files"}
)

InstallMethod = Literal["symlink", "copy"]


class EmbedManifestError(ValueError):
    """Manifest load or profile resolution failed; message names field/path + remediation."""

    pass


class InstallPlanError(EmbedManifestError):
    """Install plan resolution or apply failed."""

    pass


class EmbedActionType(str, Enum):
    """Filesystem action types for embed install plans."""

    MKDIR = "mkdir"
    SYMLINK = "symlink"
    COPY_FILE = "copy_file"
    COPY_TREE = "copy_tree"


@dataclass(frozen=True)
class InstallAction:
    """One idempotent embed install step (FR-3 preview==execute)."""

    action_id: str
    action_type: EmbedActionType
    target_rel: str
    source_rel: str = ""

    def describe(self, *, embed_dir: Path | None = None) -> str:
        """Human-readable line for dry-run output."""
        target = f"{embed_dir}/{self.target_rel}" if embed_dir else self.target_rel
        if self.action_type is EmbedActionType.MKDIR:
            return f"mkdir {target}"
        if self.action_type is EmbedActionType.SYMLINK:
            return f"symlink {target} -> {self.source_rel}"
        if self.action_type is EmbedActionType.COPY_FILE:
            return f"copy_file {self.source_rel} -> {target}"
        if self.action_type is EmbedActionType.COPY_TREE:
            return f"copy_tree {self.source_rel} -> {target}"
        return f"{self.action_type.value} {target}"


@dataclass(frozen=True)
class VerifyReport:
    """Outcome of ``verify_embed()`` / ``repair_embed()``."""

    passed: bool
    missing: tuple[str, ...] = ()
    broken_symlinks: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()
    message: str = ""


# Paths the bash installer may add under ``.cap-dev-pipe/`` outside embed-manifest managed set.
_VERIFY_ALLOWLIST = frozenset(
    {
        "pipeline.env",
        "pipeline.env.example",
        INSTALL_MANIFEST_FILENAME,
    }
)
_VERIFY_ALLOWLIST_DIRS = frozenset({"java"})


@dataclass(frozen=True)
class EmbedManifest:
    """Parsed embed-manifest.yaml (schema_version 1)."""

    schema_version: int
    scripts: tuple[str, ...]
    python_aliases: tuple[str, ...]
    resource_trees: tuple[str, ...]
    packages: tuple[str, ...]
    copy_files: tuple[str, ...]
    profiles: Mapping[str, "ProfileSpec"]
    source_path: Path


@dataclass(frozen=True)
class ProfileSpec:
    """One embed profile entry from the manifest."""

    name: str
    description: str
    extends: str | None
    scripts: tuple[str, ...]
    python_aliases: tuple[str, ...]
    resource_trees: tuple[str, ...]
    packages: tuple[str, ...]
    copy_files: tuple[str, ...]
    defaults: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedEmbedProfile:
    """Fully merged embed profile — all managed paths relative to ``.cap-dev-pipe/``."""

    name: str
    scripts: tuple[str, ...]
    python_aliases: tuple[str, ...]
    resource_trees: tuple[str, ...]
    packages: tuple[str, ...]
    copy_files: tuple[str, ...]
    defaults: Mapping[str, Any]

    def managed_paths(self) -> tuple[str, ...]:
        """Sorted relative paths included in this profile (trees/packages as dir paths)."""
        paths: list[str] = []
        paths.extend(self.scripts)
        paths.extend(self.python_aliases)
        paths.extend(self.resource_trees)
        paths.extend(self.packages)
        paths.extend(self.copy_files)
        return tuple(sorted(set(paths)))


def default_manifest_path(source_root: Path | None = None) -> Path:
    """Return ``embed-manifest.yaml`` under *source_root* or the repo root of this package."""
    if source_root is not None:
        return source_root / _MANIFEST_FILENAME
    return Path(__file__).resolve().parent.parent / _MANIFEST_FILENAME


def parse_claude_embed_scripts(claude_md_text: str) -> list[str]:
    """Extract ``ln -s $CAP_DEV_PIPE/<name>`` script names from CLAUDE.md embed block."""
    return _LN_S_EMBED_RE.findall(claude_md_text)


def render_claude_embed_block(
    scripts: Sequence[str],
    *,
    cap_dev_pipe_var: str = "$CAP_DEV_PIPE",
) -> str:
    """Render the bash embed snippet for CLAUDE.md from a script name list."""
    lines = [
        "mkdir -p .cap-dev-pipe",
        "cd .cap-dev-pipe",
        "",
        "# Symlink all scripts from canonical source (generated from embed-manifest.yaml)",
        "CAP_DEV_PIPE=~/Documents/dev/cap-dev-pipe",
    ]
    for name in scripts:
        lines.append(f"ln -s {cap_dev_pipe_var}/{name}")
    return "\n".join(lines)


def claude_embed_block_for_profile(
    source_root: Path,
    profile: str = "full",
) -> str:
    """Resolved ``full`` (or other) profile script list as a CLAUDE.md bash block body."""
    manifest = load_embed_manifest(source_root=source_root)
    resolved = resolve_embed_profile(manifest, profile)
    return render_claude_embed_block(resolved.scripts)


def regen_claude_embed_section(
    claude_path: Path,
    *,
    source_root: Path,
    profile: str = "full",
    write: bool = False,
) -> tuple[str, str]:
    """Replace the marked CLAUDE.md embed block from ``embed-manifest.yaml``.

    Returns ``(previous_text, new_text)`` for the full file. When *write* is True, persists
    the update to *claude_path*.
    """
    if not claude_path.is_file():
        raise EmbedManifestError(f"CLAUDE.md not found: {claude_path}")

    block_body = claude_embed_block_for_profile(source_root, profile)
    replacement = (
        f"{CLAUDE_EMBED_BLOCK_START}\n"
        f"```bash\n{block_body}\n```\n"
        f"{CLAUDE_EMBED_BLOCK_END}"
    )

    text = claude_path.read_text(encoding="utf-8")
    if CLAUDE_EMBED_BLOCK_START not in text or CLAUDE_EMBED_BLOCK_END not in text:
        raise EmbedManifestError(
            f"CLAUDE.md missing embed block markers "
            f"({CLAUDE_EMBED_BLOCK_START} / {CLAUDE_EMBED_BLOCK_END}). "
            f"Add markers around the Embedding in a Project ln -s block."
        )

    match = _CLAUDE_EMBED_BLOCK_RE.search(text)
    if not match:
        raise EmbedManifestError(
            f"could not locate fenced embed block between markers in {claude_path}"
        )

    new_text = text[: match.start()] + replacement + text[match.end() :]
    if write:
        claude_path.write_text(new_text, encoding="utf-8")
    return text, new_text


def check_claude_embed_drift(
    claude_path: Path,
    *,
    source_root: Path,
    profile: str = "full",
) -> bool:
    """Return True when committed CLAUDE.md matches the generated embed block."""
    _, new_text = regen_claude_embed_section(
        claude_path, source_root=source_root, profile=profile, write=False
    )
    current = claude_path.read_text(encoding="utf-8")
    return current == new_text


def load_embed_manifest(
    manifest_path: Path | None = None,
    *,
    source_root: Path | None = None,
) -> EmbedManifest:
    """Load and validate ``embed-manifest.yaml`` from *manifest_path* or *source_root*."""
    path = manifest_path or default_manifest_path(source_root)
    if not path.is_file():
        raise EmbedManifestError(
            f"embed manifest not found: {path}. "
            f"Expected {_MANIFEST_FILENAME} at the cap-dev-pipe checkout root."
        )

    raw = _load_yaml_dict(path)
    schema_version = raw.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise EmbedManifestError(
            f"unsupported embed-manifest schema_version {schema_version!r} in {path}; "
            f"expected {SUPPORTED_SCHEMA_VERSION}. Upgrade cap-dev-pipe or pin an older release."
        )

    catalog = {
        key: _parse_path_list(raw.get(key), field=key, manifest_path=path)
        for key in ("scripts", "python_aliases", "resource_trees", "packages", "copy_files")
    }

    profiles_raw = raw.get("profiles")
    if not isinstance(profiles_raw, dict) or not profiles_raw:
        raise EmbedManifestError(
            f"embed manifest {path} must define a non-empty 'profiles' mapping."
        )

    profiles: dict[str, ProfileSpec] = {}
    for name, spec in profiles_raw.items():
        if not isinstance(name, str) or not name.strip():
            raise EmbedManifestError(f"invalid profile name {name!r} in {path}")
        if not isinstance(spec, dict):
            raise EmbedManifestError(
                f"profile {name!r} in {path} must be a mapping, got {type(spec).__name__}"
            )
        profiles[name] = _parse_profile_spec(name, spec, path, catalog)

    _validate_profile_catalog_refs(profiles, catalog, path)
    _validate_extends_acyclic(profiles)

    return EmbedManifest(
        schema_version=schema_version,
        scripts=catalog["scripts"],
        python_aliases=catalog["python_aliases"],
        resource_trees=catalog["resource_trees"],
        packages=catalog["packages"],
        copy_files=catalog["copy_files"],
        profiles=profiles,
        source_path=path.parent,
    )


def resolve_embed_profile(manifest: EmbedManifest, profile_name: str) -> ResolvedEmbedProfile:
    """Merge *profile_name* with its ``extends`` chain into a resolved path set."""
    if profile_name not in manifest.profiles:
        known = ", ".join(sorted(manifest.profiles))
        raise EmbedManifestError(
            f"unknown embed profile {profile_name!r}; known profiles: {known}"
        )

    merged_scripts: list[str] = []
    merged_aliases: list[str] = []
    merged_trees: list[str] = []
    merged_packages: list[str] = []
    merged_copy: list[str] = []
    merged_defaults: dict[str, Any] = {}

    def merge_from(spec: ProfileSpec) -> None:
        if spec.extends:
            if spec.extends not in manifest.profiles:
                raise EmbedManifestError(
                    f"profile {spec.name!r} extends unknown profile {spec.extends!r}"
                )
            merge_from(manifest.profiles[spec.extends])
        _extend_preserve_order(merged_scripts, spec.scripts)
        _extend_preserve_order(merged_aliases, spec.python_aliases)
        _extend_preserve_order(merged_trees, spec.resource_trees)
        _extend_preserve_order(merged_packages, spec.packages)
        _extend_preserve_order(merged_copy, spec.copy_files)
        merged_defaults.update(spec.defaults)

    merge_from(manifest.profiles[profile_name])

    return ResolvedEmbedProfile(
        name=profile_name,
        scripts=tuple(merged_scripts),
        python_aliases=tuple(merged_aliases),
        resource_trees=tuple(merged_trees),
        packages=tuple(merged_packages),
        copy_files=tuple(merged_copy),
        defaults=dict(merged_defaults),
    )


def list_profile_names(manifest: EmbedManifest) -> tuple[str, ...]:
    """Return profile names in manifest definition order."""
    return tuple(manifest.profiles.keys())


def embed_dir_for(target_root: Path, embed_dir_name: str = EMBED_DIR_NAME) -> Path:
    """Return the embed directory path under *target_root*."""
    return target_root.resolve() / embed_dir_name


def resolve_install_plan(
    source_root: Path,
    profile: str,
    method: InstallMethod,
    target_root: Path,
    *,
    embed_dir_name: str = EMBED_DIR_NAME,
    manifest_path: Path | None = None,
) -> list[InstallAction]:
    """Build the ordered install action list for *profile* (shared planner spine).

    *target_root* is the project directory that will contain ``.cap-dev-pipe/``.
    ``target_rel`` paths are relative to the embed directory.
    """
    source = source_root.resolve()
    manifest = load_embed_manifest(manifest_path, source_root=source)
    resolved = resolve_embed_profile(manifest, profile)

    for rel in resolved.managed_paths():
        _validate_embed_path(rel, field="managed_paths", manifest_path=manifest.source_path / _MANIFEST_FILENAME)
        src = source / rel
        if rel in resolved.resource_trees or rel in resolved.packages:
            if not src.is_dir():
                raise InstallPlanError(
                    f"embed source directory missing: {src}. "
                    f"Check cap-dev-pipe checkout at {source}."
                )
        elif rel in resolved.copy_files or rel in resolved.scripts or rel in resolved.python_aliases:
            if not src.is_file():
                raise InstallPlanError(
                    f"embed source file missing: {src}. "
                    f"Check cap-dev-pipe checkout at {source}."
                )

    actions: list[InstallAction] = [
        InstallAction(
            action_id=f"mkdir:.",
            action_type=EmbedActionType.MKDIR,
            target_rel=".",
        )
    ]

    if method == "symlink":
        for name in (*resolved.scripts, *resolved.python_aliases):
            actions.append(
                InstallAction(
                    action_id=f"symlink:{name}",
                    action_type=EmbedActionType.SYMLINK,
                    target_rel=name,
                    source_rel=name,
                )
            )
        for pkg in resolved.packages:
            actions.append(
                InstallAction(
                    action_id=f"symlink:{pkg}",
                    action_type=EmbedActionType.SYMLINK,
                    target_rel=pkg,
                    source_rel=pkg,
                )
            )
        for tree in resolved.resource_trees:
            actions.append(
                InstallAction(
                    action_id=f"copy_tree:{tree}",
                    action_type=EmbedActionType.COPY_TREE,
                    target_rel=tree,
                    source_rel=tree,
                )
            )
        for copy_name in resolved.copy_files:
            actions.append(
                InstallAction(
                    action_id=f"copy_file:{copy_name}",
                    action_type=EmbedActionType.COPY_FILE,
                    target_rel=copy_name,
                    source_rel=copy_name,
                )
            )
    elif method == "copy":
        for name in (*resolved.scripts, *resolved.python_aliases, *resolved.copy_files):
            actions.append(
                InstallAction(
                    action_id=f"copy_file:{name}",
                    action_type=EmbedActionType.COPY_FILE,
                    target_rel=name,
                    source_rel=name,
                )
            )
        for tree in (*resolved.resource_trees, *resolved.packages):
            actions.append(
                InstallAction(
                    action_id=f"copy_tree:{tree}",
                    action_type=EmbedActionType.COPY_TREE,
                    target_rel=tree,
                    source_rel=tree,
                )
            )
    else:
        raise InstallPlanError(f"unknown install method {method!r}; use 'symlink' or 'copy'")

    return actions


def action_ids(actions: Sequence[InstallAction]) -> tuple[str, ...]:
    """Stable action ID tuple for preview==execute comparisons."""
    return tuple(a.action_id for a in actions)


def check_embed_namespace(
    target_root: Path,
    embed_dir: Path,
    *,
    profile: str,
    source_root: Path,
) -> None:
    """Refuse embed when a generic ``pipeline`` module would shadow the embed package."""
    del embed_dir  # guard focuses on project-root collisions before install
    manifest = load_embed_manifest(source_root=source_root.resolve())
    resolved = resolve_embed_profile(manifest, profile)
    if "pipeline" not in resolved.packages:
        return

    root = target_root.resolve()
    conflicts: list[str] = []
    sibling_dir = root / "pipeline"
    if sibling_dir.is_dir() and not sibling_dir.is_symlink():
        conflicts.append(str(sibling_dir))
    sibling_file = root / "pipeline.py"
    if sibling_file.is_file():
        conflicts.append(str(sibling_file))

    if conflicts:
        raise InstallPlanError(
            "namespace guard: project already contains a generic 'pipeline' module "
            f"that can shadow the embed package: {', '.join(conflicts)}. "
            "Rename or remove it, or choose a different project root."
        )


def write_install_manifest(
    embed_dir: Path,
    *,
    install_method: InstallMethod,
    source_path: Path,
    embed_profile: str,
    managed_paths: Sequence[str],
) -> Path:
    """Write ``.install-manifest.json`` after a successful embed (FR-4 / A3)."""
    embed_dir.mkdir(parents=True, exist_ok=True)
    path = embed_dir / INSTALL_MANIFEST_FILENAME
    payload = {
        "schema_version": INSTALL_MANIFEST_SCHEMA_VERSION,
        "manifest_version": INSTALL_MANIFEST_SCHEMA_VERSION,
        "install_method": install_method,
        "source_path": str(source_path.resolve()),
        "embed_profile": embed_profile,
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "managed_paths": sorted(set(managed_paths)),
        "state": "complete",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_install_manifest(embed_dir: Path) -> dict[str, Any]:
    """Load ``.install-manifest.json`` from an embed directory."""
    path = embed_dir / INSTALL_MANIFEST_FILENAME
    if not path.is_file():
        raise EmbedManifestError(
            f"install manifest not found: {path}. Re-run embed or install-cap-dev-pipe.sh."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EmbedManifestError(f"install manifest is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise EmbedManifestError(f"install manifest must be a JSON object: {path}")
    schema_version = data.get("schema_version", data.get("manifest_version"))
    if schema_version != INSTALL_MANIFEST_SCHEMA_VERSION:
        raise EmbedManifestError(
            f"unsupported install manifest schema_version {schema_version!r} in {path}; "
            f"expected {INSTALL_MANIFEST_SCHEMA_VERSION}."
        )
    return data


def is_install_action_satisfied(
    action: InstallAction,
    *,
    embed_dir: Path,
    source_root: Path,
) -> bool:
    """Return whether on-disk state matches a planned embed action (repair idempotency)."""
    target = embed_dir / action.target_rel if action.target_rel != "." else embed_dir
    src = source_root / action.source_rel if action.source_rel else None

    if action.action_type is EmbedActionType.MKDIR:
        return target.is_dir()
    if action.action_type is EmbedActionType.SYMLINK:
        return bool(src) and _symlink_is_correct(target, src)
    if action.action_type is EmbedActionType.COPY_FILE:
        return target.is_file() and not target.is_symlink()
    if action.action_type is EmbedActionType.COPY_TREE:
        return target.is_dir() and not target.is_symlink()
    return False


def _manifest_install_context(embed_dir: Path) -> tuple[Path, Path, str, InstallMethod, list[InstallAction]]:
    """Load install manifest and rebuild the planned action list."""
    embed_dir = embed_dir.resolve()
    if not embed_dir.is_dir():
        raise EmbedManifestError(
            f"embed directory not found: {embed_dir}. Pass --target or --embed-dir."
        )
    data = read_install_manifest(embed_dir)
    source_root = Path(data["source_path"]).resolve()
    profile = str(data["embed_profile"])
    method = str(data["install_method"])
    if method not in ("symlink", "copy"):
        raise EmbedManifestError(
            f"unsupported install_method {method!r} in {embed_dir / INSTALL_MANIFEST_FILENAME}"
        )
    install_method: InstallMethod = method  # type: ignore[assignment]
    target_root = embed_dir.parent
    actions = resolve_install_plan(source_root, profile, install_method, target_root)
    return source_root, target_root, profile, install_method, actions


def _list_unmanaged_extras(embed_dir: Path, managed_paths: Sequence[str]) -> list[str]:
    managed = set(managed_paths)
    extras: list[str] = []
    if not embed_dir.is_dir():
        return extras
    for entry in sorted(embed_dir.iterdir(), key=lambda p: p.name):
        name = entry.name
        if name in managed or name in _VERIFY_ALLOWLIST:
            continue
        if name in _VERIFY_ALLOWLIST_DIRS:
            continue
        extras.append(name)
    return extras


def verify_embed(
    embed_dir: Path,
    *,
    strict_extras: bool = False,
) -> VerifyReport:
    """Compare on-disk embed tree to ``.install-manifest.json`` / resolved install plan."""
    try:
        source_root, _target_root, _profile, _method, actions = _manifest_install_context(embed_dir)
    except EmbedManifestError as exc:
        return VerifyReport(passed=False, message=str(exc))

    embed_dir = embed_dir.resolve()
    missing: list[str] = []
    broken: list[str] = []

    for action in actions:
        if action.action_type is EmbedActionType.MKDIR:
            continue
        rel = action.target_rel
        target = embed_dir / rel
        if target.is_symlink() and not target.exists():
            broken.append(rel)
        if not is_install_action_satisfied(
            action, embed_dir=embed_dir, source_root=source_root
        ):
            if rel not in missing:
                missing.append(rel)

    data = read_install_manifest(embed_dir)
    extras = _list_unmanaged_extras(embed_dir, data.get("managed_paths", []))
    passed = not missing and not broken and (not extras or not strict_extras)

    if passed:
        message = f"Verified: {len(data.get('managed_paths', []))} managed path(s) ok."
    else:
        parts: list[str] = []
        if missing:
            parts.append(f"missing or incorrect: {', '.join(missing)}")
        if broken:
            parts.append(f"broken symlinks: {', '.join(broken)}")
        if extras and strict_extras:
            parts.append(f"unexpected entries: {', '.join(extras)}")
        message = "; ".join(parts) if parts else "verify failed"

    return VerifyReport(
        passed=passed,
        missing=tuple(missing),
        broken_symlinks=tuple(broken),
        extra=tuple(extras),
        message=message,
    )


def repair_embed(embed_dir: Path) -> VerifyReport:
    """Restore missing or incorrect managed paths only; refresh install manifest."""
    source_root, target_root, profile, method, actions = _manifest_install_context(embed_dir)
    embed_dir = embed_dir.resolve()

    check_embed_namespace(
        target_root,
        embed_dir,
        profile=profile,
        source_root=source_root,
    )

    to_apply = [
        action
        for action in actions
        if action.action_type is EmbedActionType.MKDIR
        or not is_install_action_satisfied(
            action, embed_dir=embed_dir, source_root=source_root
        )
    ]
    apply_install_plan(to_apply, source_root=source_root, embed_dir=embed_dir)

    manifest = load_embed_manifest(source_root=source_root)
    resolved = resolve_embed_profile(manifest, profile)
    write_install_manifest(
        embed_dir,
        install_method=method,
        source_path=source_root,
        embed_profile=profile,
        managed_paths=resolved.managed_paths(),
    )
    return verify_embed(embed_dir)


def apply_install_plan(
    actions: Sequence[InstallAction],
    *,
    source_root: Path,
    embed_dir: Path,
) -> None:
    """Apply *actions* under *embed_dir* (symlink method semantics for trees on symlink path)."""
    source = source_root.resolve()
    root = embed_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)

    for action in actions:
        target = root / action.target_rel if action.target_rel != "." else root
        src = source / action.source_rel if action.source_rel else None

        if action.action_type is EmbedActionType.MKDIR:
            target.mkdir(parents=True, exist_ok=True)
            continue

        if action.action_type is EmbedActionType.SYMLINK:
            if src is None:
                raise InstallPlanError(f"symlink action {action.action_id} has no source_rel")
            abs_source = src.resolve()
            if not abs_source.exists():
                raise InstallPlanError(f"symlink source missing: {abs_source}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if _symlink_is_correct(target, abs_source):
                continue
            if target.is_symlink() or target.exists():
                if target.is_dir() and not target.is_symlink():
                    raise InstallPlanError(
                        f"cannot symlink {target}: path exists and is a directory. "
                        f"Remove it or choose a clean embed directory."
                    )
                target.unlink()
            os.symlink(abs_source, target)
            continue

        if action.action_type is EmbedActionType.COPY_FILE:
            if src is None:
                raise InstallPlanError(f"copy_file action {action.action_id} has no source_rel")
            if not src.is_file():
                raise InstallPlanError(f"copy source missing: {src}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                target.unlink()
            shutil.copy2(src, target)
            continue

        if action.action_type is EmbedActionType.COPY_TREE:
            if src is None:
                raise InstallPlanError(f"copy_tree action {action.action_id} has no source_rel")
            if not src.is_dir():
                raise InstallPlanError(f"copy_tree source missing: {src}")
            if target.is_symlink():
                target.unlink()
            elif target.is_file():
                raise InstallPlanError(f"cannot copy_tree over file: {target}")
            shutil.copytree(src, target, dirs_exist_ok=True)
            continue

        raise InstallPlanError(f"unsupported action type: {action.action_type}")


def _symlink_is_correct(link: Path, source: Path) -> bool:
    if not link.is_symlink():
        return False
    try:
        return Path(os.path.realpath(link)) == source.resolve()
    except OSError:
        return False


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise EmbedManifestError(
            "PyYAML is required to load embed-manifest.yaml; install PyYAML (pip3 install pyyaml)."
        ) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EmbedManifestError(f"embed manifest {path} must be a YAML mapping at top level.")
    return data


def _parse_path_list(
    value: Any,
    *,
    field: str,
    manifest_path: Path,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise EmbedManifestError(
            f"embed manifest field {field!r} in {manifest_path} must be a list, "
            f"got {type(value).__name__}"
        )
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise EmbedManifestError(
                f"embed manifest field {field!r} in {manifest_path} contains invalid entry {item!r}"
            )
        _validate_embed_path(item, field=field, manifest_path=manifest_path)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _parse_profile_spec(
    name: str,
    spec: dict[str, Any],
    manifest_path: Path,
    catalog: Mapping[str, tuple[str, ...]],
) -> ProfileSpec:
    extends = spec.get("extends")
    if extends is not None and (not isinstance(extends, str) or not extends.strip()):
        raise EmbedManifestError(
            f"profile {name!r} 'extends' in {manifest_path} must be a non-empty string"
        )

    path_fields = {
        key: _parse_path_list(spec.get(key), field=f"profiles.{name}.{key}", manifest_path=manifest_path)
        for key in _PATH_LIST_KEYS
    }

    for key, paths in path_fields.items():
        allowed = set(catalog[key])
        unknown = [p for p in paths if p not in allowed]
        if unknown:
            raise EmbedManifestError(
                f"profile {name!r} lists unknown {key} {unknown!r} in {manifest_path}; "
                f"add them to the top-level {key} catalog first."
            )

    defaults = spec.get("defaults", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise EmbedManifestError(
            f"profile {name!r} 'defaults' in {manifest_path} must be a mapping"
        )

    description = spec.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise EmbedManifestError(
            f"profile {name!r} 'description' in {manifest_path} must be a string"
        )

    return ProfileSpec(
        name=name,
        description=description,
        extends=extends,
        scripts=path_fields["scripts"],
        python_aliases=path_fields["python_aliases"],
        resource_trees=path_fields["resource_trees"],
        packages=path_fields["packages"],
        copy_files=path_fields["copy_files"],
        defaults=defaults,
    )


def _validate_embed_path(path: str, *, field: str, manifest_path: Path) -> None:
    if path.startswith("/") or path.startswith("\\"):
        raise EmbedManifestError(
            f"embed manifest field {field!r} in {manifest_path} must use relative paths; "
            f"got absolute path {path!r}"
        )
    if ".." in Path(path).parts:
        raise EmbedManifestError(
            f"embed manifest field {field!r} in {manifest_path} must not contain '..'; "
            f"got {path!r}"
        )


def _validate_profile_catalog_refs(
    profiles: Mapping[str, ProfileSpec],
    catalog: Mapping[str, tuple[str, ...]],
    manifest_path: Path,
) -> None:
    del catalog, manifest_path  # refs validated per profile in _parse_profile_spec
    if "minimal" not in profiles:
        raise EmbedManifestError(
            f"embed manifest {manifest_path} must define a 'minimal' profile (FR-2)."
        )


def _validate_extends_acyclic(profiles: Mapping[str, ProfileSpec]) -> None:
    for name in profiles:
        visited: set[str] = set()
        current: str | None = name
        while current is not None:
            if current in visited:
                raise EmbedManifestError(
                    f"cyclic 'extends' chain detected for embed profile {name!r} "
                    f"(revisits {current!r})"
                )
            visited.add(current)
            spec = profiles.get(current)
            if spec is None:
                break
            current = spec.extends


def _extend_preserve_order(target: list[str], additions: Sequence[str]) -> None:
    for item in additions:
        if item not in target:
            target.append(item)
