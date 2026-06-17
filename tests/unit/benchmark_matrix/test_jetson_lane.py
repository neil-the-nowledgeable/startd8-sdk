"""Tests for the Jetson on-prem lane runner (runtime firewall wiring, FR-J5a/J6/J6b/J8).

Offline — a mock agent stands in for the live OpenAICompatibleAgent, setting the FR-J5a/J6 capture
attributes the runner reads. Proves the runner enforces the verdict (drops inadmissible cells) and
partitions tracks correctly without any network.
"""

import pytest
from types import SimpleNamespace

from startd8.benchmark_matrix import jetson_lane as lane
from startd8.benchmark_matrix import firewall as fw


class MockAgent:
    """Mimics OpenAICompatibleAgent's FR-J5a/J6 capture after agenerate()."""

    def __init__(self, fingerprint, *, sent_prompt_override=None, text="def main():\n    pass\n"):
        self._fp = fingerprint
        self._override = sent_prompt_override
        self._text = text
        self.last_system_fingerprint = None
        self.last_system_prompt = None

    async def agenerate(self, prompt, system_prompt=None, temperature=None):
        # capture what we "sent" (or an override simulating a corpus-prompt leak), and the server echo
        self.last_system_prompt = self._override if self._override is not None else system_prompt
        self.last_system_fingerprint = self._fp
        return SimpleNamespace(text=self._text)


SAMPLING = {"temperature": 0.0, "top_p": 1.0, "seed": 0}


@pytest.mark.asyncio
async def test_clean_base_cell_scored_general():
    agent = MockAgent("served_adapter=__base__")
    rec = await lane.run_jetson_cell(
        agent, requested_alias="mistral-7b-base", prompt="build paymentservice",
        sampling=SAMPLING, server_commit_sha="27e714fc",
    )
    assert rec.track == fw.TRACK_GENERAL and rec.scored
    assert rec.cost_lane == "on-prem"
    assert rec.server_commit_sha == "27e714fc"
    assert rec.text.startswith("def main")


@pytest.mark.asyncio
async def test_in_domain_cell_scored_in_domain():
    agent = MockAgent("served_adapter=iter_002")
    rec = await lane.run_jetson_cell(
        agent, requested_alias="iter-002", prompt="build x", sampling=SAMPLING,
    )
    assert rec.track == fw.TRACK_IN_DOMAIN and rec.scored


@pytest.mark.asyncio
async def test_wrong_adapter_dropped():
    # requested the clean base, but the server served iter_002 → invalidated, dropped
    agent = MockAgent("served_adapter=iter_002")
    rec = await lane.run_jetson_cell(
        agent, requested_alias="mistral-7b-base", prompt="build x", sampling=SAMPLING,
    )
    assert rec.track == fw.TRACK_INVALID and not rec.scored
    assert rec.firewall["invalidated"] is True


@pytest.mark.asyncio
async def test_missing_fingerprint_dropped():
    agent = MockAgent(None)  # old server: no FR-J5a echo
    rec = await lane.run_jetson_cell(
        agent, requested_alias="iter-002", prompt="build x", sampling=SAMPLING,
    )
    assert not rec.scored and rec.track == fw.TRACK_INVALID


@pytest.mark.asyncio
async def test_corpus_prompt_leak_dropped():
    # adapter correct, but the captured sent-prompt carries corpus tokens → inadmissible, dropped
    corpus = "Match the house style: JSON logger, OpenTelemetry, gRPC servicer, Apache header."
    agent = MockAgent("served_adapter=__base__", sent_prompt_override=corpus)
    rec = await lane.run_jetson_cell(
        agent, requested_alias="mistral-7b-base", prompt="build x", sampling=SAMPLING,
    )
    assert rec.track == fw.TRACK_INVALID and not rec.scored


@pytest.mark.asyncio
async def test_missing_quant_not_scored():
    # FR-J6b: quant must be recorded; an empty quant string fails the determinism vector
    agent = MockAgent("served_adapter=__base__")
    rec = await lane.run_jetson_cell(
        agent, requested_alias="mistral-7b-base", prompt="build x",
        sampling=SAMPLING, quant="",
    )
    assert rec.track == fw.TRACK_INVALID and not rec.scored


@pytest.mark.asyncio
async def test_neutral_prompt_is_clean_itself():
    """The canonical neutral prompt must not itself trip the banned-token check."""
    v = fw.verify_system_prompt(lane.NEUTRAL_SYSTEM_PROMPT, lane.NEUTRAL_SYSTEM_PROMPT)
    assert v.ok


def test_partition_and_scored_helpers():
    cells = [
        lane.JetsonCellRecord("mistral-7b-base", "x", fw.TRACK_GENERAL, True, {}),
        lane.JetsonCellRecord("iter-002", "y", fw.TRACK_IN_DOMAIN, True, {}),
        lane.JetsonCellRecord("mistral-7b-base", None, fw.TRACK_INVALID, False, {}),
    ]
    parts = lane.partition_by_track(cells)
    assert len(parts[fw.TRACK_GENERAL]) == 1
    assert len(parts[fw.TRACK_IN_DOMAIN]) == 1
    assert len(parts[fw.TRACK_INVALID]) == 1
    assert len(lane.scored_cells(cells)) == 2
