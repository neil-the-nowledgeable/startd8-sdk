"""Thread B — `kickoff assess` offers cap-dev-pipe install, gated on full kickoff readiness.

The offer is a SEPARATE top-level `capdevpipe` block (never a cascade blocker, never through the
FR-5 headline), so readiness math and exit semantics are unchanged (FR-B3). It is emitted only
once the project has satisfied all required kickoff elements (FR-B2): a not-ready project is never
pitched the pipeline. Detection is a cheap $0 3-state presence heuristic (FR-B5).
"""

from __future__ import annotations

import pytest

from startd8.capdevpipe_installer import EMBED_DIR_NAME, MANIFEST_FILENAME
from startd8.concierge import build_assess
from startd8.concierge.core import (
    CMD_CAPDEVPIPE_INSTALL,
    CMD_CAPDEVPIPE_REPAIR,
    _assess_pipeline,
    _kickoff_ready,
)

pytestmark = pytest.mark.unit

_READY_CASCADE = {"status": "ok", "blockers": []}
_READY_INPUTS = {"domains": {
    "business-targets": {"status": "present"},
    "observability": {"status": "present"},
    "conventions": {"status": "present"},
    "build-preferences": {"status": "present"},
}}


class TestKickoffReadyGate:
    def test_ready_when_cascade_clean_and_inputs_present(self):
        assert _kickoff_ready(_READY_CASCADE, _READY_INPUTS) is True

    def test_not_ready_with_blockers(self):
        cascade = {"status": "ok", "blockers": [{"section": "Contract"}]}
        assert _kickoff_ready(cascade, _READY_INPUTS) is False

    def test_not_ready_when_cascade_unresolved(self):
        assert _kickoff_ready({"status": "inputs_error"}, _READY_INPUTS) is False

    def test_not_ready_with_absent_input(self):
        inputs = {"domains": dict(_READY_INPUTS["domains"], observability={"status": "absent"})}
        assert _kickoff_ready(_READY_CASCADE, inputs) is False

    def test_not_ready_with_no_domains(self):
        assert _kickoff_ready(_READY_CASCADE, {"domains": {}}) is False


class TestPipelineDetector:
    def test_absent_and_ready_offers_install(self, tmp_path):
        out = _assess_pipeline(tmp_path, ready=True)
        assert out["status"] == "absent"
        assert out["next_command"] == CMD_CAPDEVPIPE_INSTALL

    def test_absent_but_not_ready_makes_no_offer(self, tmp_path):
        out = _assess_pipeline(tmp_path, ready=False)
        assert out["status"] == "absent"
        assert out["next_command"] is None  # FR-B2: not-ready projects are not pitched

    def test_present_without_manifest_offers_repair(self, tmp_path):
        (tmp_path / EMBED_DIR_NAME).mkdir()
        # repair is a maintenance action on an existing embed → not readiness-gated
        out = _assess_pipeline(tmp_path, ready=False)
        assert out["status"] == "present_no_manifest"
        assert out["next_command"] == CMD_CAPDEVPIPE_REPAIR

    def test_healthy_makes_no_offer(self, tmp_path):
        embed = tmp_path / EMBED_DIR_NAME
        embed.mkdir()
        (embed / MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
        out = _assess_pipeline(tmp_path, ready=True)
        assert out["status"] == "healthy"
        assert out["next_command"] is None  # FR-B4: no noise on a healthy install


class TestBuildAssessWiring:
    def test_capdevpipe_block_present(self, tmp_path):
        out = build_assess(tmp_path)
        assert "capdevpipe" in out
        assert set(out["capdevpipe"]) >= {"status", "next_command", "kickoff_ready"}

    def test_bare_project_absent_no_offer(self, tmp_path):
        """A bare project is not kickoff-ready → absent but no install offer."""
        out = build_assess(tmp_path)
        assert out["capdevpipe"]["status"] == "absent"
        assert out["capdevpipe"]["kickoff_ready"] is False
        assert out["capdevpipe"]["next_command"] is None

    def test_offer_never_appears_in_cascade_blockers(self, tmp_path):
        """FR-B3: the advisory offer is never a cascade blocker."""
        out = build_assess(tmp_path)
        for b in out["cascade"].get("blockers") or []:
            assert "capdevpipe" not in str(b).lower() or b.get("section")  # not a synthetic blocker
            assert b.get("next_command") != CMD_CAPDEVPIPE_INSTALL

    def test_headline_unaffected_by_capdevpipe(self, tmp_path):
        """FR-B3: readiness headline is the cascade's, unchanged by the new block."""
        out = build_assess(tmp_path)
        # bare project → headline is a cascade blocker command, never the capdevpipe offer
        assert out["next_command"] != CMD_CAPDEVPIPE_INSTALL

    def test_broken_embed_offers_repair_even_on_bare_project(self, tmp_path):
        (tmp_path / EMBED_DIR_NAME).mkdir()
        out = build_assess(tmp_path)
        assert out["capdevpipe"]["status"] == "present_no_manifest"
        assert out["capdevpipe"]["next_command"] == CMD_CAPDEVPIPE_REPAIR
