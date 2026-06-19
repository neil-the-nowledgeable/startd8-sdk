"""Data models for events overlay generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventChannelSpec:
    name: str
    direction: str
    topic: str
    payload: str
