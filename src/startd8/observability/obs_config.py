# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Declarative resolution of the remaining hardcoded observability policy maps (extends A1).

Same precedence idiom as `persona_config` (the polish ``DEFAULT_THEME`` pattern): a project may
override these *policy* maps in its ContextManifest ``spec.observability``; otherwise the hardcoded
defaults apply. The resolved maps ride on `BusinessContext` (already threaded into every generator),
so consumers read e.g. ``business.severity_map`` instead of the module-level dict.

Manifest overrides (all optional, under ``spec.observability``)::

    observability:
      severityMapping:   {critical: critical, high: critical, medium: warning, low: info}
      defaultThresholds: {availability: "99", latency_p99: "500ms", throughput: "100rps"}
      qualityThresholds: {warning: 0.6, healthy: 0.8}
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Portal quality-gauge default (the only one not already a module dict elsewhere).
_QUALITY_THRESHOLDS_DEFAULT: Dict[str, float] = {"warning": 0.6, "healthy": 0.8}


def _obs(manifest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return (manifest or {}).get("spec", {}).get("observability", {}) or {}


def load_severity_map(manifest: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """criticality → alert severity (manifest ``severityMapping`` over the hardcoded default)."""
    from .artifact_generator_generators import _CRITICALITY_TO_SEVERITY

    return {**_CRITICALITY_TO_SEVERITY, **(_obs(manifest).get("severityMapping") or {})}


def load_default_thresholds(manifest: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """SLO default thresholds (manifest ``defaultThresholds`` over the hardcoded default)."""
    from .artifact_generator_generators import _DEFAULT_THRESHOLDS

    return {**_DEFAULT_THRESHOLDS, **(_obs(manifest).get("defaultThresholds") or {})}


def load_quality_thresholds(manifest: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Portal quality-gauge bands (manifest ``qualityThresholds`` over ``{warning: 0.6, healthy: 0.8}``)."""
    return {**_QUALITY_THRESHOLDS_DEFAULT, **(_obs(manifest).get("qualityThresholds") or {})}
