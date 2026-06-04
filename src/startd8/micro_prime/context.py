"""Workflow-agnostic Micro Prime context (REQ-MP-509)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from startd8.forward_manifest import ForwardManifest


@dataclass(frozen=True)
class MicroPrimeContext:
    """Normalized context consumed by Micro Prime adapters and engine."""

    manifest: ForwardManifest
    target_files: list[str]
    binding_constraints: list[str] = field(default_factory=list)
    existing_file_contents: dict[str, str] = field(default_factory=dict)
    ollama_available: bool = True
    ollama_model: str = "startd8-coder"
    # REQ-SIG-201: Dependency task imports from service communication graph.
    # Keyed by dep task ID → {"modules": [...], "target_files": [...]}.
    dependency_imports: dict[str, dict[str, Any]] = field(default_factory=dict)
    # FR-CAR-5: generator-derived Python house-style guidance, injected into the generation prompt so
    # the cheapest tier generates toward the conventions (FastAPI/SQLModel/app.tables) instead of generic
    # Flask/SQLAlchemy. Empty for non-Python targets. Defaulted → backward-compatible (frozen dataclass).
    convention_guidance: str = ""

    @classmethod
    def from_artisan(
        cls,
        chunk: Any,
        phase_data: dict,
        ollama_available: bool,
    ) -> Optional["MicroPrimeContext"]:
        """Build context from Artisan chunk + phase_data."""
        manifest = phase_data.get("forward_manifest") or phase_data.get("manifest")
        if manifest is None:
            return None

        target_files = list(getattr(chunk, "file_targets", []) or [])
        binding_constraints = list(phase_data.get("binding_constraints", []) or [])
        existing_files = dict(getattr(chunk, "file_contents", {}) or {})

        return cls(
            manifest=manifest,
            target_files=target_files,
            binding_constraints=binding_constraints,
            existing_file_contents=existing_files,
            ollama_available=ollama_available,
            ollama_model=str(phase_data.get("ollama_model", "startd8-coder")),
        )

    @classmethod
    def from_prime(
        cls,
        gen_context: dict[str, Any],
        manifest: ForwardManifest,
        target_files: list[str],
        ollama_available: bool,
    ) -> "MicroPrimeContext":
        """Build context from Prime Contractor generation context."""
        binding_constraints = list(gen_context.get("domain_constraints", []) or [])
        existing_files = dict(gen_context.get("existing_files", {}) or {})
        dep_imports = dict(gen_context.get("dependency_imports", {}) or {})
        ollama_model = "startd8-coder"
        if gen_context.get("ollama_model"):
            try:
                ollama_model = str(gen_context.get("ollama_model"))
            except (TypeError, ValueError):
                pass
        # FR-CAR-5: inject the Python house-style guidance for Python targets so micro-prime generates
        # toward FastAPI/SQLModel/app.tables (never break context construction if it's unavailable).
        convention_guidance = ""
        if any(str(f).endswith(".py") for f in target_files):
            try:
                from startd8.repair.convention import render_convention_guidance

                convention_guidance = render_convention_guidance()
            except Exception:
                convention_guidance = ""
        return cls(
            manifest=manifest,
            target_files=list(target_files),
            binding_constraints=binding_constraints,
            existing_file_contents=existing_files,
            ollama_available=ollama_available,
            ollama_model=ollama_model,
            dependency_imports=dep_imports,
            convention_guidance=convention_guidance,
        )
