"""Shared GENERATED-header builders for backend_codegen artifacts.

One source of truth for the ``# GENERATED from … / # startd8-artifact: … / # schema-sha256: …``
provenance block, so the spine/derived renderers and the AI-layer renderers emit byte-identical
headers (previously the block was copy-pasted in ``crud_generator`` and ``derived``).

- :func:`header_standard` — spine/derived artifacts: one source contract (the Prisma schema), one hash.
- :func:`header_ai_layer` — AI-layer artifacts: THREE inputs (schema + ai_passes + human_inputs),
  so three hashes; drift is stale if *any* of them changes (FR-MA-5).
"""

from __future__ import annotations


def header_standard(source_file: str, sha: str, kind: str) -> str:
    """The spine/derived provenance header (source of truth: the Prisma schema)."""
    return (
        f"# GENERATED from {source_file} — do not edit by hand; "
        f"regenerate via `startd8 generate backend`.\n"
        f"# startd8-artifact: {kind}\n"
        f"# Source of truth: the Prisma schema.\n"
        f"# schema-sha256: {sha}"
    )


def header_ai_layer(
    source_file: str,
    schema_sha: str,
    passes_sha: str,
    human_sha: str,
    kind: str,
) -> str:
    """AI-layer provenance header — derives from three inputs, so it carries three hashes.

    Drift on an AI-layer file is **stale if any one of** schema / ai_passes / human_inputs changes
    (see :func:`startd8.backend_codegen.drift.ai_layer_stale_reason`).
    """
    return (
        f"# GENERATED from {source_file} (+ ai_passes.yaml + human_inputs.yaml) — do not edit by "
        f"hand; regenerate via `startd8 generate backend`.\n"
        f"# startd8-artifact: {kind}\n"
        f"# Source of truth: the Prisma schema, AI passes, and human inputs.\n"
        f"# schema-sha256: {schema_sha}\n"
        f"# passes-sha256: {passes_sha}\n"
        f"# human-inputs-sha256: {human_sha}"
    )
