"""Agentic Concierge — proposal core, registry/prompt pairing, floor guard, confirm-apply."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.concierge.writes import build_instantiate_plan
from startd8.kickoff_experience.capture import CaptureCode
from startd8.kickoff_experience.chat import (
    KICKOFF_AGENTIC_SYSTEM_PROMPT,
    KICKOFF_SYSTEM_PROMPT,
    build_kickoff_registry,
)
from startd8.kickoff_experience.concierge_apply import ConciergeWriteCode
from startd8.kickoff_experience.proposals import (
    BufferFull,
    ProposalBuffer,
    ProposedAction,
    apply_proposal,
    make_propose_handler,
)

CONVENTIONS = textwrap.dedent(
    """\
    # header — must survive
    domain: conventions
    provenance_default: authored
    language: python
    data_model:
      money: cents
    """
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text(CONVENTIONS, encoding="utf-8")
    return tmp_path


def _tree(root: Path):
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


# --- M2: mode-paired prompts (R1-F3) -----------------------------------------------------------

def test_pure_prompt_does_not_mention_propose_action() -> None:
    assert "propose_action" not in KICKOFF_SYSTEM_PROMPT
    assert "exactly three tools" in KICKOFF_SYSTEM_PROMPT


def test_agentic_prompt_mentions_propose_and_human_confirm() -> None:
    assert "propose_action" in KICKOFF_AGENTIC_SYSTEM_PROMPT
    assert "confirm" in KICKOFF_AGENTIC_SYSTEM_PROMPT.lower()
    assert "never write" in KICKOFF_AGENTIC_SYSTEM_PROMPT.lower()


# --- M1: registry pairing + floor guard (R1-F6) ------------------------------------------------

def test_pure_registry_is_three_read_tools() -> None:
    reg = build_kickoff_registry("/tmp/x")
    assert reg.names() == {"survey", "assess", "field_states"}


def test_agentic_registry_adds_only_propose_action_read_tool() -> None:
    buf = ProposalBuffer()
    reg = build_kickoff_registry("/tmp/x", proposal_sink=make_propose_handler("/tmp/x", buf))
    assert reg.names() == {"survey", "assess", "field_states", "propose_action"}
    assert reg.allow_effect_classes == {"read"}
    for spec in reg._tools.values():
        assert spec.effect_class == "read"
    # No write tool name is reachable.
    for w in ("instantiate", "friction", "capture", "apply", "log-friction"):
        assert w not in reg.names()


def test_propose_handler_writes_zero_files(project: Path) -> None:
    buf = ProposalBuffer()
    handler = make_propose_handler(project, buf)
    before = _tree(project)
    ack = handler({"kind": "instantiate", "posture": "prototype"})
    assert "recorded a proposal" in ack
    assert _tree(project) == before          # the read-effect tool touched no files
    assert len(buf) == 1 and buf.pending()[0].kind == "instantiate"


# --- M1: propose validation -------------------------------------------------------------------

def test_propose_rejects_invalid(project: Path) -> None:
    buf = ProposalBuffer()
    h = make_propose_handler(project, buf)
    assert "error" in h({"kind": "instantiate", "posture": "bogus"}).lower()
    assert "error" in h({"kind": "friction", "friction": "", "what_happened": "x",
                         "implication": "y"}).lower()
    assert "error" in h({"kind": "capture", "value_path": "conventions.yaml#/nope",
                         "value": "x"}).lower()
    assert "error" in h({"kind": "frobnicate"}).lower()
    assert len(buf) == 0                      # nothing recorded on rejection


def test_propose_capture_captures_base_sha(project: Path) -> None:
    buf = ProposalBuffer()
    make_propose_handler(project, buf)({"kind": "capture",
                                        "value_path": "conventions.yaml#/data_model.money",
                                        "value": "float"})
    assert buf.pending()[0].base_sha   # propose-time sha recorded (R1-F1)


def test_buffer_is_bounded() -> None:
    buf = ProposalBuffer()
    for _ in range(ProposalBuffer._MAX):
        buf.add(ProposedAction("instantiate", {"posture": "prototype"}, id="x"))
    with pytest.raises(BufferFull):
        buf.add(ProposedAction("instantiate", {"posture": "prototype"}, id="y"))


# --- M3/M4: apply_proposal --------------------------------------------------------------------

def test_apply_instantiate_clean_project_is_ok(tmp_path: Path) -> None:
    # Package missing → instantiate writes ALL files → terminal OK.
    out = apply_proposal(tmp_path, ProposedAction("instantiate", {"posture": "prototype"}, id="i"))
    assert out.ok and out.code == ConciergeWriteCode.OK
    assert (tmp_path / "docs" / "kickoff" / "KICKOFF_INTRO.md").exists()


def test_apply_instantiate_partial_when_some_exist(project: Path) -> None:
    # conventions.yaml already exists → no-clobber skip → PARTIAL (retriable); re-confirm → SKIPPED.
    out = apply_proposal(project, ProposedAction("instantiate", {"posture": "prototype"}, id="i"))
    assert out.code == ConciergeWriteCode.PARTIAL and out.retriable
    out2 = apply_proposal(project, ProposedAction("instantiate", {"posture": "prototype"}, id="i"))
    assert out2.code == ConciergeWriteCode.SKIPPED and out2.ok   # converges to terminal success


def test_apply_friction_stamps_timestamp(project: Path) -> None:
    out = apply_proposal(project, ProposedAction(
        "friction", {"friction": "grammar gap", "what_happened": "x", "implication": "y"}, id="f"))
    assert out.ok
    log = (project / "concierge-friction.jsonl").read_text()
    assert "grammar gap" in log and '"ts":' in log


def test_apply_capture_ok_preserves_comments(project: Path) -> None:
    buf = ProposalBuffer()
    make_propose_handler(project, buf)({"kind": "capture",
                                        "value_path": "conventions.yaml#/data_model.money",
                                        "value": "float"})
    out = apply_proposal(project, buf.pending()[0])
    assert out.code == CaptureCode.OK
    disk = (project / "docs/kickoff/inputs/conventions.yaml").read_text()
    assert "money: float" in disk and "# header — must survive" in disk


def test_apply_capture_stale_file_via_propose_time_sha(project: Path) -> None:
    # R1-F1: the file is edited in the propose→confirm window → apply must refuse with STALE_FILE.
    buf = ProposalBuffer()
    make_propose_handler(project, buf)({"kind": "capture",
                                        "value_path": "conventions.yaml#/data_model.money",
                                        "value": "float"})
    target = project / "docs/kickoff/inputs/conventions.yaml"
    target.write_text(CONVENTIONS + "\nextra: changed\n", encoding="utf-8")  # external edit
    out = apply_proposal(project, buf.pending()[0])
    assert out.code == CaptureCode.STALE_FILE
    assert out.retriable                       # kept pending for retry
    assert "extra: changed" in target.read_text()   # the concurrent edit was not clobbered


def test_apply_capture_revalidates_allow_list(project: Path) -> None:
    # A proposal whose value_path is not in the live allow-list is refused at confirm (R1-S4).
    out = apply_proposal(project, ProposedAction(
        "capture", {"value_path": "conventions.yaml#/not_allowed", "value": "x"}, id="c"))
    assert out.code == CaptureCode.VALUE_PATH_NOT_ALLOWED
    assert not out.ok


def test_apply_proposal_unknown_kind_is_typed_not_crash(project: Path) -> None:
    # apply_proposal is public — a malformed proposal must return a typed outcome, not KeyError.
    out = apply_proposal(project, ProposedAction("frobnicate", {}, id="z"))
    assert out.code == "unknown_kind"
    assert not out.ok


def test_apply_proposal_missing_params_typed(project: Path) -> None:
    out = apply_proposal(project, ProposedAction("capture", {}, id="z"))  # no value_path
    assert out.code == CaptureCode.VALUE_PATH_NOT_ALLOWED
    assert not out.ok
