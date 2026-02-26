# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
Data structures for managing the Project Scaffolder state and manifest.
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, Optional

from .scaffold_constants import SCAFFOLD_MANIFEST_FILE, SCHEMA_VERSION

@dataclass
class ProjectScaffoldManifest:
    """State tracking for a scaffolded project to enable safe updates.

    Stores the template, context, and file hashes to determine if a file
    was modified by the user/LLM since it was initially scaffolded.
    """
    version: str = SCHEMA_VERSION
    template: str = ""
    template_version: str = "1.0"
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Store relative_file_path -> sha256_hash
    file_hashes: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectScaffoldManifest":
        return cls(**data)

    def save(self, project_root: Path) -> None:
        """Save the manifest to the project root."""
        manifest_path = project_root / SCAFFOLD_MANIFEST_FILE
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, project_root: Path) -> Optional["ProjectScaffoldManifest"]:
        """Load manifest from the project root if it exists."""
        manifest_path = project_root / SCAFFOLD_MANIFEST_FILE
        if not manifest_path.exists():
            return None
        try:
            data = json.loads(manifest_path.read_text())
            return cls.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None
