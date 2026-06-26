"""Kickoff *value*-input parsers (FR-VIP) — the strict round-trip authorities for the value YAMLs.

The assembly manifests (`schema.prisma`, `pages.yaml`, `views.yaml`, …) have generator-owned parsers
that the prose extractors round-trip against. The **value** inputs (`conventions.yaml`,
`build-preferences.yaml`, `business-targets.yaml`, …) had none — they were YAML-only, hand-authored
from templates with no round-trip target. This package is their one home (D-VIP-1): each value class
gets a strict parser here that is BOTH the round-trip gate for its prose extractor and the canonical
schema for any future consumer.

Conventions is the proving slice; build-preferences / business-targets follow the same pattern.
"""

from __future__ import annotations

from .build_preferences import BuildPreferencesManifest, parse_build_preferences
from .business_targets import (
    BusinessTargetsManifest,
    Target,
    parse_business_targets,
)
from .conventions import (
    ConventionsManifest,
    DataModelConventions,
    parse_conventions,
)

__all__ = [
    "ConventionsManifest",
    "DataModelConventions",
    "parse_conventions",
    "BuildPreferencesManifest",
    "parse_build_preferences",
    "BusinessTargetsManifest",
    "Target",
    "parse_business_targets",
]
