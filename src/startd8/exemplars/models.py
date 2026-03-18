"""Data models for the Proven Exemplar Pipeline (REQ-PEP-000–003).

ExemplarEntry is a frozen dataclass representing a validated (spec, code, score)
tuple from a successful Prime Contractor run.  ConfigFingerprint captures the
structural identity of a task for similarity matching.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


__all__ = [
    "ConfigFingerprint",
    "ExemplarEntry",
    "ExemplarScores",
    "SCHEMA_VERSION",
    "MAX_REGISTRY_SIZE",
]

SCHEMA_VERSION = "1.0.0"
MAX_REGISTRY_SIZE = 500


# ---------------------------------------------------------------------------
# Configuration Fingerprint (REQ-PEP-002)
# ---------------------------------------------------------------------------

# Filename → file_type classification
_TEST_PATTERNS = re.compile(
    r"(?:_test\.go$|Test\.java$|test_.*\.py$|\.test\.[jt]sx?$|\.spec\.[jt]sx?$)",
    re.IGNORECASE,
)
_DOCKERFILE_PATTERNS = re.compile(r"^Dockerfile(?:\..+)?$", re.IGNORECASE)
_BUILD_CONFIG_NAMES = frozenset({
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "pom.xml",
    "Cargo.toml",
})
_BUILD_CONFIG_EXTS = frozenset({".csproj", ".fsproj", ".sln"})
_CONFIG_EXTS = frozenset({".xml", ".yaml", ".yml", ".json", ".properties", ".toml", ".ini"})
_SOURCE_EXTS = frozenset({".java", ".go", ".py", ".js", ".ts", ".cs", ".rs", ".kt"})


@dataclass(frozen=True)
class ConfigFingerprint:
    """Structural identity of a task for exemplar matching (REQ-PEP-002).

    Serialized as ``"{language}:{file_type}:{transport}:{archetype}"``.
    """

    language: str   # e.g. "java", "go", "python", "nodejs"
    file_type: str  # source | test | dockerfile | build_config | config_file
    transport: str  # grpc | http | none
    archetype: str  # grpc_server | grpc_client | unit_test | ...

    def __str__(self) -> str:
        return f"{self.language}:{self.file_type}:{self.transport}:{self.archetype}"

    @classmethod
    def from_string(cls, s: str) -> ConfigFingerprint:
        """Parse a fingerprint from its ``language:file_type:transport:archetype`` string form."""
        parts = s.split(":")
        if len(parts) != 4:
            raise ValueError(
                f"Invalid fingerprint string: {s!r} (expected 4 colon-separated parts, got {len(parts)})"
            )
        return cls(language=parts[0], file_type=parts[1], transport=parts[2], archetype=parts[3])

    def matches_exact(self, other: ConfigFingerprint) -> bool:
        return self == other

    def matches_partial(self, other: ConfigFingerprint) -> bool:
        """Match on (language, file_type, archetype) ignoring transport."""
        return (
            self.language == other.language
            and self.file_type == other.file_type
            and self.archetype == other.archetype
        )

    @classmethod
    def compute(
        cls,
        target_file: str,
        *,
        language: str = "",
        transport: str = "none",
        element_specs: Optional[List[Dict[str, Any]]] = None,
    ) -> ConfigFingerprint:
        """Compute a fingerprint from a target file path and metadata.

        Args:
            target_file: Relative path of the target file.
            language: Language ID (e.g. "java", "go"). If empty, inferred
                from extension.
            transport: Transport protocol (grpc | http | none).
            element_specs: Optional list of element spec dicts for archetype
                inference.
        """
        p = Path(target_file)
        name = p.name
        ext = p.suffix.lower()
        stem = p.stem.lower()

        # --- language ---
        if not language:
            language = _ext_to_language(ext)

        # --- file_type ---
        file_type = _classify_file_type(name, ext)

        # --- archetype ---
        archetype = _derive_archetype(stem, name, file_type, transport, element_specs)

        return cls(
            language=language,
            file_type=file_type,
            transport=transport,
            archetype=archetype,
        )


def _ext_to_language(ext: str) -> str:
    """Map a file extension (e.g. '.java') to a language ID (e.g. 'java')."""
    _map = {
        ".java": "java", ".kt": "java",
        ".go": "go",
        ".py": "python",
        ".js": "nodejs", ".ts": "nodejs", ".jsx": "nodejs", ".tsx": "nodejs",
        ".cs": "csharp",
        ".rs": "rust",
    }
    return _map.get(ext, "unknown")


def _classify_file_type(name: str, ext: str) -> str:
    """Classify a file into source | test | dockerfile | build_config | config_file."""
    if _DOCKERFILE_PATTERNS.match(name):
        return "dockerfile"
    if _TEST_PATTERNS.search(name):
        return "test"
    if name in _BUILD_CONFIG_NAMES or ext in _BUILD_CONFIG_EXTS:
        return "build_config"
    if ext in _SOURCE_EXTS:
        return "source"
    if ext in _CONFIG_EXTS:
        return "config_file"
    return "source"


def _derive_archetype(
    stem: str,
    name: str,
    file_type: str,
    transport: str,
    element_specs: Optional[List[Dict[str, Any]]],
) -> str:
    """Derive archetype from filename, file_type, transport, and elements."""
    # Dockerfiles
    if file_type == "dockerfile":
        return "multi_stage_dockerfile"

    # Build configs
    if file_type == "build_config":
        if name == "build.gradle" or name == "build.gradle.kts":
            return "gradle_build"
        if name == "go.mod":
            return "go_mod"
        if name == "package.json":
            return "package_json"
        if name == "pyproject.toml" or name == "setup.py":
            return "pyproject"
        if name.endswith(".csproj"):
            return "csproj"
        return "build_config"

    # Tests
    if file_type == "test":
        return "unit_test"

    # Config files
    if file_type == "config_file":
        if "log" in stem:
            return "logging_config"
        if stem == "settings" or stem.startswith("settings."):
            return "settings_file"
        return "config_file"

    # Source files — use transport + name heuristics
    if transport == "grpc":
        if "client" in stem:
            return "grpc_client"
        if "server" in stem or "service" in stem:
            return "grpc_server"
        return "grpc_module"

    if transport == "http":
        if "client" in stem:
            return "http_client"
        if "server" in stem or "handler" in stem:
            return "http_server"
        return "http_module"

    # Fallback by name patterns
    if "logger" in stem or "logging" in stem:
        return "logging_module"
    if "config" in stem:
        return "config_module"
    if "util" in stem or "helper" in stem:
        return "utility_module"
    if "main" in stem:
        return "main_module"

    # Element-based fallback
    if element_specs:
        kinds = {e.get("kind", "unknown") for e in element_specs}
        if "class" in kinds and len(element_specs) > 3:
            return "class_module"
        if len(element_specs) <= 2:
            return "simple_module"

    return "source_module"


# ---------------------------------------------------------------------------
# Exemplar Scores
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExemplarScores:
    """Validation scores proving exemplar correctness."""

    requirement_score: float = 0.0
    disk_quality_score: float = 0.0
    assembly_delta: float = 0.0
    semantic_error_count: int = 0
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Exemplar Entry (REQ-PEP-001)
# ---------------------------------------------------------------------------

@dataclass
class ExemplarEntry:
    """A proven-correct (spec, code, score) tuple from a successful run.

    Mutable only for maturity promotion — scores and content are fixed
    at extraction time.
    """

    id: str
    fingerprint: ConfigFingerprint
    maturity: int  # 0=candidate, 1=validated, 2=confirmed, 3=invariant, 4=template
    source_run_id: str
    source_feature_id: str
    spec_artifact_path: str  # relative to run dir
    code_artifact_path: str  # relative to run dir
    draft_artifact_path: str  # relative to run dir
    seed_task_digest: str  # SHA-256 of forward manifest entry
    scores: ExemplarScores
    agent_specs: Dict[str, str] = dataclasses.field(default_factory=dict)
    code_summary: str = ""  # first 50 lines of generated code
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["fingerprint"] = str(self.fingerprint)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ExemplarEntry:
        """Deserialize from a dict (e.g. loaded from JSON).

        Forward-compatible: silently ignores keys not in the dataclass
        schema, so registries written by newer versions can still be read.
        """
        d = dict(d)  # shallow copy to avoid mutating caller's dict

        fp_str = d.pop("fingerprint", "")
        if isinstance(fp_str, str):
            fp = ConfigFingerprint.from_string(fp_str)
        elif isinstance(fp_str, dict):
            fp = ConfigFingerprint(**fp_str)
        else:
            fp = ConfigFingerprint("unknown", "source", "none", "source_module")

        scores_raw = d.pop("scores", {})
        if isinstance(scores_raw, dict):
            scores = ExemplarScores(**{
                k: scores_raw[k]
                for k in ExemplarScores.__dataclass_fields__
                if k in scores_raw
            })
        else:
            scores = scores_raw

        # Drop keys not in the dataclass to handle forward-compatibility
        known_fields = {f.name for f in dataclasses.fields(cls)} - {"fingerprint", "scores"}
        filtered = {k: v for k, v in d.items() if k in known_fields}
        return cls(fingerprint=fp, scores=scores, **filtered)

    @staticmethod
    def make_id(fingerprint: ConfigFingerprint, run_id: str, feature_id: str) -> str:
        """Generate a stable exemplar ID: ex-{fingerprint_hash}-{run_id}-{feature_id}."""
        fp_hash = hashlib.sha256(str(fingerprint).encode()).hexdigest()[:8]
        return f"ex-{fp_hash}-{run_id}-{feature_id}"
