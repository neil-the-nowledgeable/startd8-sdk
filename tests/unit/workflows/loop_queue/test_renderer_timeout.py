# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""EC-WLQ-01: CRP bundle renderer must fail closed on subprocess hang."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from startd8.workflows.loop_queue.models import (
    CrpReviewRequest,
    LoopQueueBlockedError,
)
from startd8.workflows.loop_queue.renderer import render_bundle


def _minimal_request(tmp_path: Path) -> CrpReviewRequest:
    req_path = tmp_path / "REQ.md"
    plan_path = tmp_path / "PLAN.md"
    req_path.write_text("# req\n", encoding="utf-8")
    plan_path.write_text("# plan\n", encoding="utf-8")
    return CrpReviewRequest(
        requirements_path=str(req_path),
        plan_path=str(plan_path),
        scope="EC-WLQ-01 timeout test",
        max_rounds=3,
        substantially_addressed_threshold=3,
        max_suggestions=10,
    )


def test_render_bundle_timeout_raises_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STARTD8_CRP_RENDERER_TIMEOUT_SECONDS", "1")
    script = tmp_path / "fake-renderer.sh"
    script.write_text("#!/bin/sh\necho unused\n", encoding="utf-8")
    script.chmod(0o755)
    request = _minimal_request(tmp_path)
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir()

    def _hang(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="fake", timeout=1)

    with patch(
        "startd8.workflows.loop_queue.renderer.subprocess.run",
        side_effect=_hang,
    ):
        with pytest.raises(LoopQueueBlockedError, match="timed out after 1"):
            render_bundle(
                request,
                round_number=1,
                artifact_dir=out_dir,
                renderer_script=script,
            )
