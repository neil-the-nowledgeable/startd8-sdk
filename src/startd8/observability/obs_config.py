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

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Portal quality-gauge default (the only one not already a module dict elsewhere).
_QUALITY_THRESHOLDS_DEFAULT: Dict[str, float] = {"warning": 0.6, "healthy": 0.8}

# Importance-scaled SLO thresholds live in a config FILE (not hardcoded) — single source of truth
# for the values (design: importance-scaled-slo, FR-7). Manifest may override any cell.
_IMPORTANCE_THRESHOLDS_FILE = Path(__file__).resolve().parent / "config" / "importance_thresholds.yaml"


def _obs(manifest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return (manifest or {}).get("spec", {}).get("observability", {}) or {}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``override`` onto a copy of ``base`` (override wins at the leaves)."""
    out = copy.deepcopy(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


@lru_cache(maxsize=1)
def _importance_base() -> Dict[str, Any]:
    """Load + cache the base importance-threshold table from the config file (drop schema_version)."""
    data = yaml.safe_load(_IMPORTANCE_THRESHOLDS_FILE.read_text(encoding="utf-8")) or {}
    return {k: v for k, v in data.items() if k != "schema_version"}


def load_importance_thresholds(manifest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Importance-scaled SLO thresholds: config-file base, deep-merged with any manifest override
    under ``spec.observability.importanceThresholds`` (FR-7). Nested
    ``<criticality>.<deployment_mode|default>.{availability, latency_p99}``.
    """
    return _deep_merge(_importance_base(), _obs(manifest).get("importanceThresholds") or {})


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
