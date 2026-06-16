"""Concierge safe-writer — the single chokepoint where any Concierge byte reaches disk.

Enforces the enumerated confinement invariants of CONCIERGE_MCP_REQUIREMENTS v0.4
(FR-C3.1–C3.6). The WritePlan is treated as **untrusted input** (FR-C3.6): every path and
action is re-confined and re-classified here, independently of who built the plan — so a
hand-crafted or agent-round-tripped escaping path is hard-stopped regardless.

Confinement uses dir-fd-relative operations (`O_NOFOLLOW`/`O_EXCL`, `dir_fd=`) so the inode
validated during the parent walk is the inode written — closing the resolve→replace TOCTOU
window (FR-C3.3). Where the platform lacks `dir_fd` support, a documented resolve-then-reverify
fallback applies (still confined, just without the atomic-inode guarantee).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

SCHEMA_VERSION = 1

# Actions a planned write may carry.
ACTION_NEW = "new"
ACTION_OVERWRITE = "overwrite"
ACTION_APPEND = "append"
_VALID_ACTIONS = (ACTION_NEW, ACTION_OVERWRITE, ACTION_APPEND)

# The confinement walk needs only open/mkdir/stat with dir_fd (supported on macOS + Linux).
# os.replace's dir_fd support is absent on macOS, so the atomic replace uses lexical paths the
# walk has already proven symlink-free (see _atomic_write) rather than gating the whole path on it.
_DIR_FD_OK = {os.open, os.mkdir, os.stat} <= os.supports_dir_fd
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class SafeWriteError(RuntimeError):
    """Hard stop — a confinement/root-integrity violation. Aborts the whole apply."""


@dataclass
class PlannedWrite:
    """One planned write. ``path`` is relative to the project root (absolute paths and any
    ``..`` are rejected as confinement violations)."""

    path: str
    action: str
    content: Optional[str] = None        # new / overwrite
    append_text: Optional[str] = None    # append


@dataclass
class WriteResult:
    written: List[str] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)   # {path, reason} — e.g. exists, no --force
    blocked: List[dict] = field(default_factory=list)   # {path, reason} — confinement refusal
    errors: List[dict] = field(default_factory=list)    # {path, error}

    @property
    def ok(self) -> bool:
        return not self.blocked and not self.errors


def _allowed_roots() -> List[Path]:
    raw = os.environ.get("STARTD8_CONCIERGE_ALLOWED_ROOTS", "").strip()
    if not raw:
        return []
    return [Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip()]


def _is_within(child: Path, parent: Path) -> bool:
    """True if *child* (already resolved) is *parent* or lexically beneath it.

    Exact (case-sensitive) part comparison — **fail-closed**. Folding case unconditionally would
    over-match distinct directories on a case-sensitive FS (e.g. allowlist ``/data/proj`` vs real
    ``/data/Proj`` on Linux). On a case-insensitive FS a differently-cased allowlist entry simply
    won't match — the user controls both the env var and the path and can align them. Write-target
    confinement is unaffected either way: targets are built from *parent*, so they share its exact
    prefix bytes.
    """
    return child.parts[: len(parent.parts)] == parent.parts


def resolve_confined_root(project_root) -> Path:
    """FR-C3.1 — root integrity. Reject a symlinked root (lexical path ≠ realpath) unless it
    sits under an explicit ``STARTD8_CONCIERGE_ALLOWED_ROOTS`` entry."""
    p = Path(project_root).expanduser()
    lexical = Path(os.path.abspath(p))
    real = Path(os.path.realpath(p))
    allow = _allowed_roots()
    if allow:
        if not any(_is_within(real, a) for a in allow):
            raise SafeWriteError(
                f"project_root {real} is not under any STARTD8_CONCIERGE_ALLOWED_ROOTS entry"
            )
    elif lexical != real:
        raise SafeWriteError(
            f"project_root '{project_root}' is a symlink or contains symlinked/.. components "
            f"(lexical {lexical} ≠ realpath {real}); reject or set STARTD8_CONCIERGE_ALLOWED_ROOTS"
        )
    if not real.is_dir():
        raise SafeWriteError(f"project_root is not a directory: {real}")
    return real


def _split_rel(root: Path, rel: str) -> Optional[List[str]]:
    """Return the path components of *rel* under *root*, or None if it escapes (abs / ``..``)."""
    if os.path.isabs(rel):
        return None
    parts = [c for c in Path(rel).parts if c not in ("", ".")]
    if any(c == ".." for c in parts):
        return None
    # Final lexical guard: the joined+normalized path must stay under root.
    target = Path(os.path.normpath(os.path.join(str(root), *parts)))
    if not _is_within(target, root):
        return None
    return parts


def _walk_to_parent(root_fd: int, dir_parts: List[str], *, create: bool) -> int:
    """Open the confined parent dir fd, walking each component with ``O_NOFOLLOW`` so a
    symlinked intermediate is refused (FR-C3.2/C3.3). Caller closes the returned fd."""
    cur = root_fd
    cur_is_root = True
    try:
        for part in dir_parts:
            flags = _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC
            try:
                nxt = os.open(part, flags, dir_fd=cur)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o755, dir_fd=cur)
                nxt = os.open(part, flags, dir_fd=cur)
            except OSError as e:  # ELOOP (symlink + O_NOFOLLOW), ENOTDIR, …
                raise SafeWriteError(
                    f"parent component '{part}' is a symlink or not a real directory under root"
                ) from e
            if not cur_is_root:
                os.close(cur)
            cur, cur_is_root = nxt, False
        return cur
    except Exception:
        if not cur_is_root:
            os.close(cur)
        raise


def _stat_exists(name: str, parent_fd: int) -> bool:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _write_all(fd: int, data: bytes) -> None:
    """Write all of *data* — ``os.write`` may return after a short write."""
    mv = memoryview(data)
    while mv:
        mv = mv[os.write(fd, mv):]


def _atomic_write(parent_fd: int, parent_path: str, name: str, data: bytes) -> None:
    """Write *data* to *name* via temp+replace. The temp is created through *parent_fd*
    (`O_EXCL|O_NOFOLLOW` — confined, atomic create); the replace uses lexical paths under
    *parent_path*, which the dir-fd walk has already proven symlink-free (so it is safe to use a
    path-based replace where ``os.replace`` lacks ``dir_fd`` support, e.g. macOS)."""
    tmp = f".{name}.concierge.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_CLOEXEC
    try:
        os.unlink(tmp, dir_fd=parent_fd)  # clear a stale temp from a prior crash
    except FileNotFoundError:
        pass
    fd = os.open(tmp, flags, 0o644, dir_fd=parent_fd)
    try:
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(os.path.join(parent_path, tmp), os.path.join(parent_path, name))


def _append(parent_fd: int, name: str, text: str) -> None:
    """FR-C3.5 — atomic append: O_APPEND single write, never truncates, crash/concurrency safe."""
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | _O_NOFOLLOW | _O_CLOEXEC
    fd = os.open(name, flags, 0o644, dir_fd=parent_fd)
    try:
        _write_all(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def apply_write_plan(project_root, writes: List[PlannedWrite], *, force: bool = False) -> WriteResult:
    """Apply *writes* under *project_root*, enforcing FR-C3.1–C3.6. Returns a structured result;
    a root-integrity violation raises ``SafeWriteError`` (hard stop for the whole call), while
    per-file confinement/clobber refusals are collected as ``blocked`` and processing continues."""
    if not _DIR_FD_OK:  # pragma: no cover - platform fallback
        return _apply_fallback(project_root, writes, force=force)

    root = resolve_confined_root(project_root)  # FR-C3.1 (may raise)
    result = WriteResult()
    root_fd = os.open(str(root), _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC)
    try:
        for w in writes:
            if w.action not in _VALID_ACTIONS:
                result.errors.append({"path": w.path, "error": f"unknown action {w.action!r}"})
                continue
            parts = _split_rel(root, w.path)  # FR-C3.2/C3.6 — re-confine untrusted path
            if parts is None or not parts:
                result.blocked.append({"path": w.path, "reason": "escapes project root (abs/..)"})
                continue
            *dir_parts, name = parts
            parent_path = str(root.joinpath(*dir_parts))  # lexically validated by the walk below
            try:
                parent_fd = _walk_to_parent(root_fd, dir_parts, create=(w.action != ACTION_OVERWRITE))
            except SafeWriteError as e:
                result.blocked.append({"path": w.path, "reason": str(e)})
                continue
            except FileNotFoundError:
                result.blocked.append({"path": w.path, "reason": "parent directory missing"})
                continue
            try:
                exists = _stat_exists(name, parent_fd)
                if w.action == ACTION_NEW and exists:
                    result.skipped.append({"path": w.path, "reason": "exists (use --force to overwrite)"})
                    continue
                if w.action == ACTION_OVERWRITE and exists and not force:
                    result.skipped.append({"path": w.path, "reason": "exists; overwrite needs --force"})
                    continue
                if w.action == ACTION_APPEND:
                    _append(parent_fd, name, w.append_text or "")
                else:
                    _atomic_write(parent_fd, parent_path, name, (w.content or "").encode("utf-8"))
                result.written.append(w.path)
            except OSError as e:
                result.errors.append({"path": w.path, "error": f"{type(e).__name__}: {e}"})
            finally:
                if parent_fd != root_fd:
                    os.close(parent_fd)
    finally:
        os.close(root_fd)
    return result


def _apply_fallback(project_root, writes: List[PlannedWrite], *, force: bool) -> WriteResult:  # pragma: no cover
    """Resolve-then-reverify fallback for platforms without dir_fd (no atomic-inode guarantee)."""
    root = resolve_confined_root(project_root)
    result = WriteResult()
    for w in writes:
        if w.action not in _VALID_ACTIONS:
            result.errors.append({"path": w.path, "error": f"unknown action {w.action!r}"})
            continue
        parts = _split_rel(root, w.path)
        if parts is None or not parts:
            result.blocked.append({"path": w.path, "reason": "escapes project root (abs/..)"})
            continue
        target = root.joinpath(*parts)
        # Reverify after resolution: no symlink components, still within root.
        if any(p.is_symlink() for p in list(target.parents)[: len(parts) - 1]) or not _is_within(
            Path(os.path.realpath(target.parent)), root
        ):
            result.blocked.append({"path": w.path, "reason": "symlinked parent / escapes root"})
            continue
        exists = target.exists()
        if w.action == ACTION_NEW and exists:
            result.skipped.append({"path": w.path, "reason": "exists (use --force)"})
            continue
        if w.action == ACTION_OVERWRITE and exists and not force:
            result.skipped.append({"path": w.path, "reason": "exists; overwrite needs --force"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if w.action == ACTION_APPEND:
            with open(target, "a", encoding="utf-8") as f:
                f.write(w.append_text or "")
        else:
            tmp = target.with_suffix(target.suffix + ".concierge.tmp")
            tmp.write_text(w.content or "", encoding="utf-8")
            os.replace(tmp, target)
        result.written.append(w.path)
    return result
