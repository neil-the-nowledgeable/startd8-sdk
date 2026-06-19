"""Deterministic Kafka event stub generation from ``events.yaml`` + Prisma (Tier-1 PR4)."""

from __future__ import annotations

from .drift import events_file_in_sync, is_owned_events_file
from .engine import render_events_artifacts
from .events_manifest import parse_events_manifest
from .models import EventChannelSpec
from .provider import EventsFileProvider

__all__ = [
    "EventChannelSpec",
    "EventsFileProvider",
    "events_file_in_sync",
    "is_owned_events_file",
    "parse_events_manifest",
    "render_events_artifacts",
]
