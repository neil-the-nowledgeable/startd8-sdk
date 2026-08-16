"""$0 grounding pass — FR- / capability_id mention counts (FR-9)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_FR_KEY = re.compile(r"\b(FR-[\w-]+)\b")
_CAP_KEY = re.compile(r"\b(startd8\.[\w.]+)\b")
_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".tox", "dist", "build"}


def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in {".py", ".md", ".yaml", ".yml", ".toml", ".txt", ".json"}:
            yield p


def ground_tree(root: Path, *, extra_patterns: Optional[List[re.Pattern[str]]] = None) -> Dict[str, Any]:
    """Enumerate keys under ``root`` and count file mentions."""
    root = Path(root)
    counts: Dict[str, int] = {}
    patterns = [_FR_KEY, _CAP_KEY] + list(extra_patterns or [])
    for path in _iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in patterns:
            for m in pat.finditer(text):
                key = m.group(1)
                counts[key] = counts.get(key, 0) + 1
    dated = datetime.now(timezone.utc).date().isoformat()
    return {
        "grounded": dated,
        "root": str(root.resolve()),
        "keys": {k: counts[k] for k in sorted(counts)},
        "key_count": len(counts),
    }


def write_grounding(root: Path, out: Path) -> Dict[str, Any]:
    payload = ground_tree(root)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
