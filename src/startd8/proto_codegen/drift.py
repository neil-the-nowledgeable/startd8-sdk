"""Drift helpers for proto skeleton artifacts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..frontend_codegen.schema_renderer import schema_sha256
from .engine import render_grpc_skeletons

_KINDS = frozenset({"proto-skeleton-python", "proto-skeleton-go"})
_KIND_RE = re.compile(r"#\s*startd8-artifact:\s*(\S+)")
_PROTO_SHA_RE = re.compile(r"#\s*proto-sha256:\s*([0-9a-f]{64})")


def embedded_kind(text: str) -> Optional[str]:
    m = _KIND_RE.search(text or "")
    return m.group(1) if m else None


def embedded_proto_sha(text: str) -> Optional[str]:
    m = _PROTO_SHA_RE.search(text or "")
    return m.group(1) if m else None


def is_owned_proto_skeleton(text: str) -> bool:
    t = text or ""
    kind = embedded_kind(t)
    return kind in _KINDS and embedded_proto_sha(t) is not None


def proto_skeleton_in_sync(
    manifest_text: str, project_root: Path, rel_path: str, ondisk_text: str
) -> bool:
    if not is_owned_proto_skeleton(ondisk_text):
        return False
    try:
        artifacts = {
            rel: content for rel, content in render_grpc_skeletons(manifest_text, project_root)
        }
    except (OSError, ValueError):
        return False
    expected = artifacts.get(rel_path.replace("\\", "/"))
    if expected is None:
        return False
    return expected == ondisk_text


def manifest_sha256(manifest_text: str) -> str:
    return schema_sha256(manifest_text)
