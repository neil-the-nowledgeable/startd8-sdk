# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Shared fixtures for FDE unit tests — synthetic run artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """A run output dir with SA triage + post-mortem + raw prime-result artifacts.

    One deterministic failure (PI-001 / resolve_matches), tier=simple, repair fired,
    generation_strategy=template (raw-only), plus a cross-feature pattern.
    """
    run = tmp_path / "run-001"
    run.mkdir()
    _write(
        run / "service-assistant-triage.json",
        {
            "run": {"run_id": "run-001", "output_dir": str(run), "status": "partial"},
            "verdict": {"aggregate_verdict": "PARTIAL", "failed": 1},
            "summary": {"headline": "1 failed"},
            "failures": [
                {
                    "feature_id": "PI-001",
                    "root_cause": "duplicate_import",
                    "pipeline_stage": "repair",
                    "severity": "high",
                    "deterministic": True,
                    "element_id": "resolve_matches",
                    "recommended_action": {
                        "action": "regenerate",
                        "re_run_strategy": "regenerate_clean",
                    },
                }
            ],
            "cross_feature_patterns": [
                {
                    "pattern_type": "shared_cause",
                    "description": "dup imports",
                    "affected_features": ["PI-001"],
                    "severity": "high",
                }
            ],
        },
    )
    _write(
        run / "prime-postmortem-report.json",
        {
            "features": [
                {
                    "feature_id": "PI-001",
                    "elements": [
                        {
                            "element_name": "resolve_matches",
                            "tier": "simple",
                            "repair_steps": ["dedupe_imports"],
                            "template_used": False,
                            "escalation_reason": "",
                        }
                    ],
                }
            ]
        },
    )
    _write(
        run / "prime-result.json",
        {
            "history": [
                {
                    "generation_metadata": {
                        "micro_prime_file_results": [
                            {
                                "element_results": [
                                    {
                                        "element_name": "resolve_matches",
                                        "generation_strategy": "template",
                                    }
                                ],
                            }
                        ]
                    },
                }
            ]
        },
    )
    return run


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path
