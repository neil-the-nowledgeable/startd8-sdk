"""Prefer commit-anchored ``git:<sha>:<path>`` lives refs when the soft path is in HEAD.

Phase 2 / EVIDENCE-1: soft ``file:line`` stays transitional; when the blob is reachable
from ``HEAD``, rewrite to the strong form. Untracked / missing paths stay soft.
"""

from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional

_GIT_REF = re.compile(r"^git:[0-9a-f]{40}:\S+")
_SOFT_LINE = re.compile(r"^(?P<path>.+?)(?::(?P<line>\d+))?$")


@lru_cache(maxsize=8)
def _head_sha(repo: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    sha = (out.stdout or "").strip()
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def _path_in_head(repo: str, rel: str) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", repo, "cat-file", "-e", f"HEAD:{rel}"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def prefer_git_ref(ref: str, *, repo: Optional[Path] = None) -> str:
    """Return ``git:<sha>:<path>`` when ``ref`` is a soft path present at HEAD; else ``ref``."""
    ref = (ref or "").strip()
    if not ref or _GIT_REF.match(ref):
        return ref
    # strip optional ``file:`` prefix
    soft = ref[5:] if ref.startswith("file:") else ref
    m = _SOFT_LINE.match(soft)
    if not m:
        return ref
    path = m.group("path").lstrip("./")
    if not path or path.startswith("/") or ".." in path.split("/"):
        return ref
    root = Path(repo) if repo else Path.cwd()
    root_s = str(root.resolve())
    sha = _head_sha(root_s)
    if not sha or not _path_in_head(root_s, path):
        return ref
    return f"git:{sha}:{path}"
