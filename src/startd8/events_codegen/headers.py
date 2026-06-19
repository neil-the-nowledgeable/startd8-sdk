"""Provenance headers for events overlay artifacts."""

from __future__ import annotations


def header_events(
    events_source: str,
    events_sha: str,
    schema_source: str,
    schema_sha: str,
    kind: str,
    channel: str,
) -> str:
    return (
        f"# GENERATED from {events_source} + {schema_source} — do not edit by hand; "
        f"regenerate via `startd8 generate events`.\n"
        f"# startd8-artifact: {kind}\n"
        f"# Source of truth: events manifest + Prisma schema (payload projection).\n"
        f"# events-sha256: {events_sha}\n"
        f"# schema-sha256: {schema_sha}\n"
        f"# channel: {channel}"
    )
