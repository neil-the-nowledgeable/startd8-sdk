"""Tests for Gate 3b: post-IMPLEMENT semantic content validation.

Validates ``ImplementPhaseHandler._validate_generation_content()`` which
runs all 5 self-consistency validators against generated files.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from startd8.contractors.protocols import GenerationResult

from conftest import FakeSeedTask


class TestGate3bContentValidation:

    @staticmethod
    def _get_validator():
        """Import the static method."""
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler
        return ImplementPhaseHandler._validate_generation_content

    def test_placeholder_detected(self, tmp_path: Path):
        """Gate 3b catches REPLACE_WITH placeholder (DEV-002 pattern)."""
        validate = self._get_validator()

        # Create a file with placeholder
        gen_file = tmp_path / "config.py"
        gen_file.write_text(
            'DIGEST = "REPLACE_WITH_ACTUAL_DIGEST"\n',
            encoding="utf-8",
        )

        task = FakeSeedTask(
            task_id="T-1",
            target_files=["config.py"],
        )
        gr = GenerationResult(
            success=True,
            generated_files=[gen_file],
        )

        findings = validate(
            tasks=[task],
            generation_results={"T-1": gr},
            project_root=tmp_path,
        )
        assert "T-1" in findings
        assert len(findings["T-1"]) >= 1
        assert any(
            "REPLACE_WITH" in issue["message"]
            for issue in findings["T-1"]
        )

    def test_clean_code_no_findings(self, tmp_path: Path):
        """Clean production code passes all validators."""
        validate = self._get_validator()

        gen_file = tmp_path / "main.py"
        gen_file.write_text(
            textwrap.dedent("""\
                import os

                def get_path():
                    return os.getcwd()
            """),
            encoding="utf-8",
        )

        task = FakeSeedTask(
            task_id="T-2",
            target_files=["main.py"],
        )
        gr = GenerationResult(
            success=True,
            generated_files=[gen_file],
        )

        findings = validate(
            tasks=[task],
            generation_results={"T-2": gr},
            project_root=tmp_path,
        )
        assert findings == {}

    def test_protocol_fidelity_with_metadata(self, tmp_path: Path):
        """Gate 3b catches HTTP client in gRPC-declared service."""
        validate = self._get_validator()

        gen_file = tmp_path / "client.py"
        gen_file.write_text(
            textwrap.dedent("""\
                import requests
                def call_service():
                    return requests.get("http://api.example.com")
            """),
            encoding="utf-8",
        )

        task = FakeSeedTask(
            task_id="T-3",
            target_files=["client.py"],
        )
        gr = GenerationResult(
            success=True,
            generated_files=[gen_file],
        )

        findings = validate(
            tasks=[task],
            generation_results={"T-3": gr},
            project_root=tmp_path,
            service_metadata={"transport_protocol": "grpc"},
        )
        assert "T-3" in findings
        assert any(
            i["validator"] == "protocol_fidelity"
            for i in findings["T-3"]
        )

    def test_failed_generation_skipped(self, tmp_path: Path):
        """Tasks with failed generation are skipped entirely."""
        validate = self._get_validator()

        task = FakeSeedTask(
            task_id="T-4",
            target_files=["missing.py"],
        )
        gr = GenerationResult(
            success=False,
            error="Generation failed",
        )

        findings = validate(
            tasks=[task],
            generation_results={"T-4": gr},
            project_root=tmp_path,
        )
        assert findings == {}

    def test_none_generation_result_skipped(self, tmp_path: Path):
        """Tasks without a generation result are skipped."""
        validate = self._get_validator()

        task = FakeSeedTask(
            task_id="T-5",
            target_files=["missing.py"],
        )

        findings = validate(
            tasks=[task],
            generation_results={},
            project_root=tmp_path,
        )
        assert findings == {}
