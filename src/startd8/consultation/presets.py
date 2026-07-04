"""Named roster presets for consultations (QW-4 / OQ-9).

Lets a user save a cross-vendor "council" under a name and reuse it instead of retyping
``--models``. Stored as plain JSON under the storage dir (local, single-user — like the rest of
``.startd8``).
"""

from __future__ import annotations

import json
from pathlib import Path


class PresetStore:
    """A tiny JSON-backed store of ``{name: [model_id, ...]}`` roster presets."""

    def __init__(self, base_dir: "str | Path" = ".startd8") -> None:
        self.path = Path(base_dir) / "consult-presets.json"

    def _read(self) -> "dict[str, list[str]]":
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}

    def _write(self, data: "dict[str, list[str]]") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save(self, name: str, models: "list[str]") -> None:
        data = self._read()
        data[name] = list(models)
        self._write(data)

    def load(self, name: str) -> "list[str] | None":
        return self._read().get(name)

    def list(self) -> "dict[str, list[str]]":
        return self._read()

    def delete(self, name: str) -> bool:
        data = self._read()
        if name in data:
            del data[name]
            self._write(data)
            return True
        return False
