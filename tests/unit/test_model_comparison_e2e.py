"""S0–S4 unit tests for model_comparison_e2e.

S0: preflight (FR-17) + redact_secrets (FR-19).
S1–S4: orchestration spine — shared preamble abort (FR-5), per-model continue-on-failure (FR-5),
model-pin assertion (FR-14), seed-hash integrity (FR-15), and dry-run plan (FR-12, R1-S6).

NO real subprocess runs: every external invocation goes through an injectable ``runner`` that a
fake records + canned-responds to.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

import startd8.model_comparison_e2e as e2e
from startd8.model_comparison_e2e import (
    DEFAULT_ROUND1_GATE,
    MANIFEST_FROZEN_V1,
    REASON_ADVANCED,
    REASON_BELOW_CAPABILITY,
    REASON_INPUTS_MISSING,
    REASON_INVALID_COMPARISON,
    STAGE_PLAN_INGESTION,
    STAGE_PRIME,
    STAGE_SHARED_PREAMBLE,
    W_INGESTION,
    W_PRIME,
    AdvancementGate,
    E2EBatchResult,
    ModelResult,
    StageResult,
    StageStatus,
    apply_advancement,
    assert_model_pin,
    build_manifest,
    build_report_markdown,
    collect_versions,
    compute_capability,
    compute_cost_fields,
    evaluate_advancement,
    extract_stage_costs,
    hash_shared_artifacts,
    orchestrate_e2e,
    plan_e2e,
    preflight,
    redact_secrets,
    sanitize_run_record,
    score_batch,
    write_batch_outputs,
    write_inputs_archive,
)
from startd8.model_comparison_e2e import (
    MANIFEST_SCHEMA_VERSION,
)

pytestmark = pytest.mark.unit


# Two distinct mock specs that validate WITHOUT network/keys (MockProvider.validate_config -> True).
MOCK_A = "mock:mock-model"
MOCK_B = "mock:mock-fast"


@pytest.fixture
def seed_files(tmp_path: Path) -> tuple[list[Path], list[Path]]:
    plan = tmp_path / "plan.md"
    reqs = tmp_path / "requirements.md"
    plan.write_text("# plan", encoding="utf-8")
    reqs.write_text("# requirements", encoding="utf-8")
    return [plan], [reqs]


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    source_root = tmp_path / "src_tree"
    batch_root = tmp_path / "batch"
    source_root.mkdir()
    return source_root, batch_root


def test_preflight_passes_on_valid_case(tmp_path, seed_files):
    plans, reqs = seed_files
    source_root, batch_root = _roots(tmp_path)
    errors = preflight([MOCK_A, MOCK_B], plans, reqs, source_root, batch_root)
    assert errors == [], errors


def test_preflight_rejects_fewer_than_two_distinct_models(tmp_path, seed_files):
    plans, reqs = seed_files
    source_root, batch_root = _roots(tmp_path)
    # Same spec twice -> only one distinct valid model.
    errors = preflight([MOCK_A, MOCK_A], plans, reqs, source_root, batch_root)
    assert any("distinct valid models" in e for e in errors), errors


def test_preflight_rejects_slug_collision(tmp_path, seed_files):
    plans, reqs = seed_files
    source_root, batch_root = _roots(tmp_path)
    # Two DISTINCT valid specs (mock provider validates any model) that normalize to the same
    # filesystem slug: 'mock:a/b' and 'mock:a b' both slug() to 'mock-a-b'.
    errors = preflight(
        ["mock:a/b", "mock:a b"], plans, reqs, source_root, batch_root
    )
    assert any("slug collision" in e for e in errors), errors


def test_preflight_rejects_invalid_provider(tmp_path, seed_files):
    plans, reqs = seed_files
    source_root, batch_root = _roots(tmp_path)
    errors = preflight(
        ["nope-no-such-provider:x", MOCK_B], plans, reqs, source_root, batch_root
    )
    assert any("unknown provider" in e for e in errors), errors


def test_preflight_rejects_missing_input_files(tmp_path):
    source_root, batch_root = _roots(tmp_path)
    missing_plan = tmp_path / "absent_plan.md"
    missing_reqs = tmp_path / "absent_reqs.md"
    errors = preflight(
        [MOCK_A, MOCK_B], [missing_plan], [missing_reqs], source_root, batch_root
    )
    assert any("plan file not found" in e for e in errors), errors
    assert any("requirements file not found" in e for e in errors), errors


def test_preflight_rejects_batch_equals_source(tmp_path, seed_files):
    plans, reqs = seed_files
    source_root = tmp_path / "shared_tree"
    source_root.mkdir()
    errors = preflight([MOCK_A, MOCK_B], plans, reqs, source_root, source_root)
    assert any("batch root must not equal source root" in e for e in errors), errors


def test_redact_secrets_masks_api_key_and_bearer():
    text = (
        "export ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx\n"
        "Authorization: Bearer abc123def456ghijkl\n"
    )
    out = redact_secrets(text)
    assert "sk-ant-xxxxxxxxxxxxxxxxxxxx" not in out
    assert "abc123def456ghijkl" not in out
    assert "[REDACTED]" in out
    # Key name is preserved, value masked.
    assert "ANTHROPIC_API_KEY=[REDACTED]" in out


def test_redact_secrets_masks_live_env_value(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-live-value-123")
    out = redact_secrets("config used key super-secret-live-value-123 to call openai")
    assert "super-secret-live-value-123" not in out
    assert "[REDACTED]" in out


def test_redact_secrets_noop_on_clean_text():
    clean = "this text has no secrets, just words and numbers 42"
    assert redact_secrets(clean) == clean


def test_stage_status_enum_values():
    assert StageStatus.SUCCESS == "success"
    assert StageStatus.INVALID_COMPARISON == "invalid_comparison"
    assert "not_started" in StageStatus.ALL
    assert len(StageStatus.ALL) == 9
    assert MANIFEST_FROZEN_V1 == "manifest_frozen_v1"


def test_stage_result_to_dict():
    sr = StageResult(stage="plan-ingestion", status=StageStatus.SUCCESS, duration_s=1.5)
    d = sr.to_dict()
    assert d["stage"] == "plan-ingestion"
    assert d["status"] == "success"
    assert d["duration_s"] == 1.5
    assert set(d) == {
        "stage",
        "status",
        "duration_s",
        "cost_usd",
        "cost_source",
        "cost_confidence",
        "error",
    }


def test_model_result_autofills_slug_and_to_dict():
    mr = ModelResult(model="anthropic:claude-opus-4-8")
    assert mr.slug == "anthropic-claude-opus-4-8"
    mr.stages.append(StageResult(stage="prime", status=StageStatus.SUCCESS))
    d = mr.to_dict()
    assert d["model"] == "anthropic:claude-opus-4-8"
    assert d["slug"] == "anthropic-claude-opus-4-8"
    assert d["advanced"] is False
    assert len(d["stages"]) == 1


# =========================================================================== S1–S4 orchestration
#
# All external subprocess work is faked. The FakeRunner inspects each command, writes whatever
# artifacts a real stage would (diagnostic with resolved agents, seed json), and returns a dict
# shaped exactly like model_comparison.run_command's return.

def _runner_record(cmd: list[str], duration: float = 0.1, returncode: int = 0,
                   timed_out: bool = False, stderr: str = "", stdout: str = "") -> dict[str, Any]:
    return {
        "command": cmd,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
    }


class FakeRunner:
    """Records calls and emits artifacts like the real stages would — zero subprocess.

    ``seed_for(model)`` controls each model's seed bytes (drive FR-15 collisions); ``agents_for``
    controls the resolved assessor/transformer recorded into the diagnostic (drive FR-14 mismatch);
    ``fail_on`` forces a non-zero exit for a given stage substring.
    """

    def __init__(
        self,
        seed_for: Optional[Callable[[str], str]] = None,
        agents_for: Optional[Callable[[str], dict[str, str]]] = None,
        fail_on: Optional[Callable[[str, list[str]], Optional[dict[str, Any]]]] = None,
    ) -> None:
        self.calls: list[list[str]] = []
        self._seed_for = seed_for or (lambda m: f"seed-for-{m}")
        self._agents_for = agents_for or (lambda m: {"assessor": m, "transformer": m})
        self._fail_on = fail_on

    def _classify(self, cmd: list[str]) -> str:
        joined = " ".join(cmd)
        if "run-cap-delivery.sh" in joined:
            return STAGE_SHARED_PREAMBLE
        if "run-plan-ingestion.sh" in joined:
            return STAGE_PLAN_INGESTION
        if "run_prime_workflow.py" in joined:
            return STAGE_PRIME
        return "unknown"

    def _model_from_ingestion(self, cmd: list[str]) -> tuple[str, Path]:
        # cmd = [bash, run-plan-ingestion.sh, --config, <path>]
        config_path = Path(cmd[cmd.index("--config") + 1])
        cfg = json.loads(config_path.read_text())
        return cfg["assessor_agent"], Path(cfg["output_dir"])

    def _model_from_prime(self, cmd: list[str]) -> tuple[str, Path]:
        model = cmd[cmd.index("--lead-agent") + 1]
        output = Path(cmd[cmd.index("--output-dir") + 1])
        return model, output

    def __call__(self, cmd: list[str], cwd: Path, timeout: Optional[float] = None,
                 on_output: Any = None) -> dict[str, Any]:
        self.calls.append(list(cmd))
        stage = self._classify(cmd)
        if self._fail_on is not None:
            forced = self._fail_on(stage, cmd)
            if forced is not None:
                return forced

        if stage == STAGE_PLAN_INGESTION:
            model, output = self._model_from_ingestion(cmd)
            output.mkdir(parents=True, exist_ok=True)
            # Write the seed (drives FR-15) and the diagnostic with resolved agents (FR-14).
            (output / "prime-context-seed.json").write_text(self._seed_for(model))
            diag = {"totals": {"models": self._agents_for(model)}}
            (output / "plan-ingestion-diagnostic.json").write_text(json.dumps(diag))
        return _runner_record(cmd)


def _inputs(tmp_path: Path):
    plan = tmp_path / "plan.md"
    reqs = tmp_path / "requirements.md"
    plan.write_text("# plan")
    reqs.write_text("# requirements")
    source_root = tmp_path / "src_tree"
    source_root.mkdir()
    (source_root / "main.py").write_text("print('x')\n")  # something to copy
    batch_root = tmp_path / "batch"
    return [plan], [reqs], source_root, batch_root


def _statuses(mr: ModelResult) -> dict[str, str]:
    return {s.stage: s.status for s in mr.stages}


# --- assert_model_pin (FR-14) -----------------------------------------------


def test_assert_model_pin_passes_when_resolved_match():
    assert assert_model_pin({"assessor": "mock:mock-model", "transformer": "mock:mock-model"},
                            "mock:mock-model") is None


def test_assert_model_pin_errors_on_assessor_mismatch():
    err = assert_model_pin(
        {"assessor": "anthropic:claude-sonnet", "transformer": "mock:mock-model"},
        "mock:mock-model",
    )
    assert err is not None
    assert "model-pin mismatch" in err
    assert "assessor" in err


def test_assert_model_pin_errors_on_missing_evidence():
    err = assert_model_pin({}, "mock:mock-model")
    assert err is not None
    assert "no resolved-agent evidence" in err


# --- (a) shared-preamble failure ABORTS (FR-5) ------------------------------


def test_shared_preamble_failure_aborts_batch(tmp_path):
    plans, reqs, source_root, batch_root = _inputs(tmp_path)

    def fail_shared(stage: str, cmd: list[str]):
        if stage == STAGE_SHARED_PREAMBLE:
            return _runner_record(cmd, returncode=1, stderr="cap-delivery boom")
        return None

    runner = FakeRunner(fail_on=fail_shared)
    result = orchestrate_e2e(
        [MOCK_A, MOCK_B], plans, reqs, source_root, batch_root,
        runner=runner, log=lambda _m: None,
    )
    assert isinstance(result, E2EBatchResult)
    assert result.aborted is True
    assert result.shared.status == StageStatus.FAILED
    assert result.models == []  # no per-model work ran
    # Only the cap-delivery command was attempted.
    assert all("run-cap-delivery.sh" in " ".join(c) for c in runner.calls)
    assert len(runner.calls) == 1


# --- (b) one model's stage fails → CONTINUE, both appear (FR-5) -------------


def test_per_model_failure_continues_to_next_model(tmp_path):
    plans, reqs, source_root, batch_root = _inputs(tmp_path)

    def fail_a_prime(stage: str, cmd: list[str]):
        # Fail prime only for MOCK_A.
        if stage == STAGE_PRIME and MOCK_A in cmd:
            return _runner_record(cmd, returncode=1, stderr="prime crashed")
        return None

    runner = FakeRunner(fail_on=fail_a_prime)
    result = orchestrate_e2e(
        [MOCK_A, MOCK_B], plans, reqs, source_root, batch_root,
        runner=runner, log=lambda _m: None,
    )
    assert result.aborted is False
    assert [m.model for m in result.models] == [MOCK_A, MOCK_B]

    a, b = result.models[0], result.models[1]
    # MOCK_A: ingestion ok, prime failed.
    assert _statuses(a)[STAGE_PLAN_INGESTION] == StageStatus.SUCCESS
    assert _statuses(a)[STAGE_PRIME] == StageStatus.FAILED
    # MOCK_B fully succeeded — proving the batch continued past A's failure.
    assert _statuses(b)[STAGE_PLAN_INGESTION] == StageStatus.SUCCESS
    assert _statuses(b)[STAGE_PRIME] == StageStatus.SUCCESS


def test_model_pin_mismatch_marks_invalid_model_and_skips_prime(tmp_path):
    plans, reqs, source_root, batch_root = _inputs(tmp_path)

    # MOCK_A silently falls back to Sonnet; MOCK_B honors the pin.
    def agents_for(model: str) -> dict[str, str]:
        if model == MOCK_A:
            return {"assessor": "anthropic:claude-sonnet", "transformer": "anthropic:claude-sonnet"}
        return {"assessor": model, "transformer": model}

    runner = FakeRunner(agents_for=agents_for)
    result = orchestrate_e2e(
        [MOCK_A, MOCK_B], plans, reqs, source_root, batch_root,
        runner=runner, log=lambda _m: None,
    )
    a, b = result.models[0], result.models[1]
    assert _statuses(a)[STAGE_PLAN_INGESTION] == StageStatus.INVALID_MODEL
    assert _statuses(a)[STAGE_PRIME] == StageStatus.NOT_STARTED  # prime skipped
    assert _statuses(b)[STAGE_PLAN_INGESTION] == StageStatus.SUCCESS
    # No prime command was run for MOCK_A.
    assert not any("run_prime_workflow.py" in " ".join(c) and MOCK_A in c for c in runner.calls)


# --- (d) FR-15: identical seed hash → invalid_comparison ---------------------


def test_identical_seed_hash_flags_invalid_comparison(tmp_path):
    plans, reqs, source_root, batch_root = _inputs(tmp_path)

    # Both models produce a BYTE-IDENTICAL seed.
    runner = FakeRunner(seed_for=lambda _m: "IDENTICAL-SEED-BYTES")
    result = orchestrate_e2e(
        [MOCK_A, MOCK_B], plans, reqs, source_root, batch_root,
        runner=runner, log=lambda _m: None,
    )
    assert result.invalid_comparison is True
    expected = hashlib.sha256(b"IDENTICAL-SEED-BYTES").hexdigest()
    assert result.models[0].seed_hash == expected
    assert result.models[1].seed_hash == expected
    # Each colliding model carries an invalid_comparison stage.
    for mr in result.models:
        assert any(s.status == StageStatus.INVALID_COMPARISON for s in mr.stages)


def test_distinct_seed_hash_is_valid_comparison(tmp_path):
    plans, reqs, source_root, batch_root = _inputs(tmp_path)
    runner = FakeRunner(seed_for=lambda m: f"unique-seed-{m}")
    result = orchestrate_e2e(
        [MOCK_A, MOCK_B], plans, reqs, source_root, batch_root,
        runner=runner, log=lambda _m: None,
    )
    assert result.invalid_comparison is False
    assert result.models[0].seed_hash != result.models[1].seed_hash


# --- (e) dry_run lists cap-delivery exactly once (R1-S6) ---------------------


def test_dry_run_lists_cap_delivery_exactly_once(tmp_path):
    plans, reqs, source_root, batch_root = _inputs(tmp_path)
    runner = FakeRunner()
    result = orchestrate_e2e(
        [MOCK_A, MOCK_B], plans, reqs, source_root, batch_root,
        runner=runner, dry_run=True, log=lambda _m: None,
    )
    # No execution happened.
    assert runner.calls == []
    assert result.models == []

    plan = plan_e2e(
        [MOCK_A, MOCK_B], plans, reqs, source_root, batch_root, cost_budget=None
    )
    cap_entries = [e for e in plan if e["stage"] == STAGE_SHARED_PREAMBLE]
    assert len(cap_entries) == 1
    assert cap_entries[0]["scope"] == "batch"
    # Two models → two ingestion + two prime entries.
    assert sum(1 for e in plan if e["stage"] == STAGE_PLAN_INGESTION) == 2
    assert sum(1 for e in plan if e["stage"] == STAGE_PRIME) == 2


def test_skip_flags_default_off_command_byte_identical(tmp_path):
    """Without skip flags, the cap-delivery command is byte-identical to today (protects dry-run)."""
    plans, reqs, _source_root, batch_root = _inputs(tmp_path)
    shared_dir = batch_root / "_shared"
    baseline = e2e.build_shared_preamble_command(plans, reqs, shared_dir)
    assert "--skip-polish" not in baseline
    assert "--skip-analyze" not in baseline
    assert "--skip-validate" not in baseline
    # Default-off kwargs produce the exact same list.
    assert (
        e2e.build_shared_preamble_command(
            plans, reqs, shared_dir,
            skip_polish=False, skip_analyze=False, skip_validate=False,
        )
        == baseline
    )


def test_skip_flags_thread_into_cap_delivery_command(tmp_path):
    """skip_polish + skip_validate append the cap-delivery bypass flags."""
    plans, reqs, _source_root, batch_root = _inputs(tmp_path)
    shared_dir = batch_root / "_shared"
    cmd = e2e.build_shared_preamble_command(
        plans, reqs, shared_dir, skip_polish=True, skip_validate=True,
    )
    assert "--skip-polish" in cmd
    assert "--skip-validate" in cmd
    # skip_analyze left off → not present.
    assert "--skip-analyze" not in cmd


def test_dry_run_plan_shows_skip_flags(tmp_path):
    """plan_e2e threads skip flags into the planned cap-delivery command (DRY-RUN visibility)."""
    plans, reqs, source_root, batch_root = _inputs(tmp_path)
    plan = plan_e2e(
        [MOCK_A, MOCK_B], plans, reqs, source_root, batch_root, cost_budget=None,
        skip_polish=True, skip_validate=True,
    )
    cap_entry = next(e for e in plan if e["stage"] == STAGE_SHARED_PREAMBLE)
    assert "--skip-polish" in cap_entry["cmd"]
    assert "--skip-validate" in cap_entry["cmd"]
    assert "--skip-analyze" not in cap_entry["cmd"]
    # Default-off plan stays byte-identical (no skip flags).
    plain = plan_e2e(
        [MOCK_A, MOCK_B], plans, reqs, source_root, batch_root, cost_budget=None,
    )
    plain_cap = next(e for e in plain if e["stage"] == STAGE_SHARED_PREAMBLE)
    assert "--skip-polish" not in plain_cap["cmd"]
    assert "--skip-validate" not in plain_cap["cmd"]


def test_orchestrate_aborts_on_preflight_error(tmp_path):
    plans, reqs, source_root, batch_root = _inputs(tmp_path)
    runner = FakeRunner()
    # Only one distinct model -> preflight fails, nothing runs.
    result = orchestrate_e2e(
        [MOCK_A], plans, reqs, source_root, batch_root,
        runner=runner, log=lambda _m: None,
    )
    assert result.aborted is True
    assert result.preflight_errors
    assert runner.calls == []


# --------------------------------------------------------------------------- S5: extraction + score


def _write_prime_result(
    output: Path,
    *,
    total_cost: Optional[float] = 0.42,
    gate_score: float = 0.9,
    gate_verdict: str = "pass",
    succeeded: int = 8,
    processed: int = 10,
) -> None:
    """Write a fake prime-result.json (extract_metrics reads total_cost_usd + cross_file_gate)."""
    payload: dict[str, Any] = {
        "success": True,
        "processed": processed,
        "succeeded": succeeded,
        "failed": processed - succeeded,
        "cross_file_gate": {"verdict": gate_verdict, "score": gate_score, "cross_file_failures": []},
    }
    if total_cost is not None:
        payload["total_cost_usd"] = total_cost
    (output / "prime-result.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_ingestion_diagnostic(
    output: Path, *, cost_usd: Optional[float] = 0.05, seed_quality_score: float = 0.8
) -> None:
    """Write a fake plan-ingestion-diagnostic.json (totals.cost_usd + seed_quality_score)."""
    totals: dict[str, Any] = {}
    if cost_usd is not None:
        totals["cost_usd"] = cost_usd
    (output / "plan-ingestion-diagnostic.json").write_text(
        json.dumps({"totals": totals, "seed_quality_score": seed_quality_score}),
        encoding="utf-8",
    )


def _model_with_stages() -> ModelResult:
    mr = ModelResult(model=MOCK_A)
    mr.stages = [
        StageResult(stage=STAGE_PLAN_INGESTION, status=StageStatus.SUCCESS),
        StageResult(stage=STAGE_PRIME, status=StageStatus.SUCCESS),
    ]
    return mr


def test_three_cost_fields_attributable_excludes_shared(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    _write_prime_result(output, total_cost=0.40)
    _write_ingestion_diagnostic(output, cost_usd=0.10)
    mr = _model_with_stages()

    extract_stage_costs(mr, output, run_record={})
    shared = StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.SUCCESS, cost_usd=1.00,
                         cost_source="shared", cost_confidence="high")
    fields = compute_cost_fields(mr, shared)

    # attributable = ingestion(0.10) + prime(0.40) = 0.50 — EXCLUDES the 1.00 shared preamble.
    assert fields["cost_attributable_usd"] == pytest.approx(0.50)
    assert fields["cost_shared_preamble_usd"] == pytest.approx(1.00)
    assert fields["cost_total_loaded_usd"] == pytest.approx(1.50)
    assert fields["ranking_field"] == "cost_attributable_usd"
    # both component costs measured -> high confidence.
    assert fields["cost_attributable_confidence"] == "high"


def test_cost_db_window_fallback_when_prime_total_cost_none(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    _write_prime_result(output, total_cost=None)  # no total_cost_usd
    _write_ingestion_diagnostic(output, cost_usd=None)  # force DB fallback for ingestion too
    mr = _model_with_stages()

    monkeypatch.setattr(e2e, "cost_from_db", lambda start, end: 0.77)
    from datetime import datetime, timezone
    run_record = {"start_ts": datetime.now(timezone.utc), "end_ts": datetime.now(timezone.utc)}
    extract_stage_costs(mr, output, run_record=run_record)

    prime_stage = next(s for s in mr.stages if s.stage == STAGE_PRIME)
    ing_stage = next(s for s in mr.stages if s.stage == STAGE_PLAN_INGESTION)
    assert prime_stage.cost_usd == pytest.approx(0.77)
    assert prime_stage.cost_source == "cost_db_window"
    assert prime_stage.cost_confidence == "medium"
    assert ing_stage.cost_source == "cost_db_window"
    fields = compute_cost_fields(mr, None)
    # worst-case confidence across two medium components is medium.
    assert fields["cost_attributable_confidence"] == "medium"


def test_missing_cost_marks_missing_not_crash(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    _write_prime_result(output, total_cost=None)
    _write_ingestion_diagnostic(output, cost_usd=None)
    mr = _model_with_stages()

    monkeypatch.setattr(e2e, "cost_from_db", lambda start, end: None)
    # no run_record timestamps -> DB fallback skipped entirely; must not raise.
    extract_stage_costs(mr, output, run_record={})

    prime_stage = next(s for s in mr.stages if s.stage == STAGE_PRIME)
    assert prime_stage.cost_usd is None
    assert prime_stage.cost_source == "missing"
    assert prime_stage.cost_confidence == "missing"
    fields = compute_cost_fields(mr, None)
    assert fields["cost_attributable_usd"] is None
    assert fields["cost_attributable_confidence"] == "missing"


def test_capability_breakdown_sums_weighted_components(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    _write_prime_result(output, total_cost=0.4, gate_score=1.0, succeeded=10, processed=10)
    _write_ingestion_diagnostic(output, seed_quality_score=0.5)
    mr = _model_with_stages()

    cap = compute_capability(mr, output_dir=output)
    # ingestion=0.5; prime combined = 0.5*gate(1.0) + 0.5*completion(1.0) = 1.0
    expected = W_INGESTION * 0.5 + W_PRIME * 1.0
    assert cap["score"] == pytest.approx(expected)
    assert cap["score_breakdown"]["weights"] == {"W_INGESTION": W_INGESTION, "W_PRIME": W_PRIME}
    assert cap["score_breakdown"]["penalties"] == []
    assert cap["score_breakdown"]["components"]["ingestion"]["source"] is not None


def test_capability_records_penalty_for_missing_ingestion(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    _write_prime_result(output, total_cost=0.4, gate_score=1.0, succeeded=10, processed=10)
    # NO ingestion diagnostic -> ingestion signal missing.
    mr = _model_with_stages()

    cap = compute_capability(mr, output_dir=output)
    penalties = cap["score_breakdown"]["penalties"]
    assert any(p["component"] == "ingestion" for p in penalties)
    pen = next(p for p in penalties if p["component"] == "ingestion")
    assert pen["lost_weight"] == W_INGESTION
    # missing ingestion contributes 0; score = W_PRIME * 1.0
    assert cap["score"] == pytest.approx(W_PRIME * 1.0)


def test_capability_prime_only_present(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    _write_prime_result(output, total_cost=0.4, gate_score=0.8, succeeded=6, processed=10)
    _write_ingestion_diagnostic(output, seed_quality_score=0.9)
    mr = _model_with_stages()

    cap = compute_capability(mr, output_dir=output)
    # prime-only = 0.5*gate(0.8) + 0.5*completion(0.6) = 0.7
    assert cap["capability_prime_only"] == pytest.approx(0.7)


def test_sanitize_run_record_redacts_stderr_key():
    record = {
        "command": ["bash", "run.sh", "--key", "sk-ant-abcdefghij0123456789xyz"],
        "stderr_tail": "boom: ANTHROPIC_API_KEY=sk-ant-secretsecretsecret012345",
        "returncode": 1,
        "nested": {"stdout_tail": "Bearer tok_abcdefghijklmnop"},
    }
    clean = sanitize_run_record(record)
    assert "sk-ant-abcdefghij0123456789xyz" not in clean["command"]
    assert "[REDACTED]" in clean["stderr_tail"]
    assert "[REDACTED]" in clean["nested"]["stdout_tail"]
    assert clean["returncode"] == 1  # non-string scalars pass through


def test_score_batch_attaches_cost_fields_and_capability(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    out_a.mkdir()
    out_b.mkdir()
    _write_prime_result(out_a, total_cost=0.3, gate_score=0.9, succeeded=9, processed=10)
    _write_ingestion_diagnostic(out_a, cost_usd=0.05, seed_quality_score=0.8)
    _write_prime_result(out_b, total_cost=0.6, gate_score=0.7, succeeded=5, processed=10)
    _write_ingestion_diagnostic(out_b, cost_usd=0.05, seed_quality_score=0.6)

    mr_a = _model_with_stages()
    mr_a.model = MOCK_A
    mr_b = _model_with_stages()
    mr_b.model = MOCK_B
    batch = E2EBatchResult(
        shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.SUCCESS),
        models=[mr_a, mr_b],
    )
    dirs = {mr_a.model: out_a, mr_b.model: out_b}
    score_batch(batch, output_dir_for=lambda mr: dirs[mr.model])

    for mr in batch.models:
        assert mr.cost_fields is not None
        assert mr.capability is not None
        assert mr.cost_fields["cost_attributable_usd"] is not None
        assert "score" in mr.capability


# --------------------------------------------------------------------------- S6: manifest + report

# A leaked-looking secret embedded in a stage error to assert redaction reaches manifest + report.
_FAKE_SECRET = "sk-ant-leakedleakedleaked0123456789"


def _scored_model(
    model: str,
    *,
    cap_score: float,
    attributable: float,
    seed_hash: str,
    error: Optional[str] = None,
) -> ModelResult:
    """A fully-scored ModelResult (cost_fields + capability populated) for report/manifest tests."""
    mr = ModelResult(model=model)
    mr.seed_hash = seed_hash
    mr.resolved_agents = {"assessor": model, "transformer": model}
    ing = StageResult(stage=STAGE_PLAN_INGESTION, status=StageStatus.SUCCESS, duration_s=1.0)
    prime = StageResult(
        stage=STAGE_PRIME,
        status=StageStatus.SUCCESS if error is None else StageStatus.FAILED,
        duration_s=2.0,
        error=error,
    )
    mr.stages = [ing, prime]
    mr.error = error
    mr.cost_fields = {
        "cost_attributable_usd": attributable,
        "cost_attributable_confidence": "high",
        "cost_shared_preamble_usd": None,
        "cost_shared_preamble_confidence": "missing",
        "cost_total_loaded_usd": attributable,
        "cost_total_loaded_confidence": "high",
        "ranking_field": "cost_attributable_usd",
    }
    mr.capability = {
        "score": cap_score,
        "score_breakdown": {"components": {}, "weights": {}, "penalties": []},
        "capability_prime_only": cap_score,
    }
    return mr


def _two_model_batch() -> E2EBatchResult:
    # B is higher-capability than A (so B should rank first); A is also cheaper-but-lower-cap.
    mr_a = _scored_model(MOCK_A, cap_score=0.60, attributable=0.10, seed_hash="a" * 64)
    mr_b = _scored_model(MOCK_B, cap_score=0.90, attributable=0.50, seed_hash="b" * 64)
    return E2EBatchResult(
        shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.SUCCESS),
        models=[mr_a, mr_b],
    )


def test_write_inputs_archive_copies_and_hashes(tmp_path):
    plan = tmp_path / "plan.md"
    reqs = tmp_path / "requirements.md"
    plan.write_text("# plan body", encoding="utf-8")
    reqs.write_text("# reqs body", encoding="utf-8")
    batch_root = tmp_path / "batch"

    hashes = write_inputs_archive([plan], [reqs], batch_root)

    inputs_dir = batch_root / "_inputs"
    assert (inputs_dir / "plan.md").is_file()
    assert (inputs_dir / "requirements.md").is_file()
    assert len(hashes) == 2
    expected = hashlib.sha256(b"# plan body").hexdigest()
    assert hashes[str(inputs_dir / "plan.md")] == expected


def test_collect_versions_has_startd8_and_git_keys():
    versions = collect_versions()
    assert "startd8" in versions
    assert "contextcore" in versions
    assert "git_sha" in versions
    assert "git_dirty" in versions  # bool or None, never raises


def test_hash_shared_artifacts_missing_dir_returns_empty(tmp_path):
    assert hash_shared_artifacts(tmp_path / "nope") == {}


def test_hash_shared_artifacts_hashes_files(tmp_path):
    shared = tmp_path / "_shared"
    shared.mkdir()
    (shared / "validation-report.json").write_text("{}", encoding="utf-8")
    hashes = hash_shared_artifacts(shared)
    assert "validation-report.json" in hashes


def test_build_manifest_top_level_and_per_model_schema(tmp_path):
    batch = _two_model_batch()
    manifest = build_manifest(
        batch,
        comparison_mode=MANIFEST_FROZEN_V1,
        input_hashes={"/x/plan.md": "deadbeef"},
        shared_artifact_hashes={"validation-report.json": "cafebabe"},
        versions={"startd8": "0.4.0", "contextcore": "unknown", "git_sha": "abc", "git_dirty": False},
        batch_root=tmp_path / "batch",
    )
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["comparison_mode"] == MANIFEST_FROZEN_V1
    assert "generated_at" in manifest
    assert manifest["inputs"] == {"/x/plan.md": "deadbeef"}
    assert manifest["versions"]["startd8"] == "0.4.0"
    for m in manifest["models"]:
        assert "resolved_agents" in m
        assert "seed_hash" in m
        assert m["cost_fields"]["cost_attributable_usd"] is not None
        assert "score" in m["capability"]
        assert "invalid_comparison" in m


def test_write_batch_outputs_writes_three_files_and_archive(tmp_path):
    batch = _two_model_batch()
    plan = tmp_path / "plan.md"
    reqs = tmp_path / "requirements.md"
    plan.write_text("# plan", encoding="utf-8")
    reqs.write_text("# reqs", encoding="utf-8")
    batch_root = tmp_path / "batch"

    paths = write_batch_outputs(
        batch,
        batch_root,
        comparison_mode=MANIFEST_FROZEN_V1,
        plan_paths=[plan],
        requirements_paths=[reqs],
    )

    manifest = json.loads(Path(paths["manifest"]).read_text())
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["comparison_mode"] == MANIFEST_FROZEN_V1
    assert "versions" in manifest
    # per-model evidence present in the manifest
    by_model = {m["model"]: m for m in manifest["models"]}
    assert by_model[MOCK_A]["resolved_agents"]
    assert by_model[MOCK_A]["seed_hash"]
    assert by_model[MOCK_A]["cost_fields"]["cost_attributable_usd"] is not None
    assert "score" in by_model[MOCK_A]["capability"]
    # _inputs archive written with hashes referenced in the manifest
    assert (batch_root / "_inputs" / "plan.md").is_file()
    assert len(manifest["inputs"]) == 2

    md = Path(paths["report_md"]).read_text()
    assert "indicative" in md.lower()
    assert "shared-manifest" in md.lower() or "shared manifest" in md.lower()
    assert MANIFEST_FROZEN_V1 in md
    assert "compare-models" in md


def test_report_ranks_higher_capability_first():
    batch = _two_model_batch()  # B cap 0.90 > A cap 0.60
    manifest = build_manifest(
        batch,
        comparison_mode=MANIFEST_FROZEN_V1,
        input_hashes={},
        shared_artifact_hashes={},
        versions=collect_versions(),
        batch_root=Path("/tmp/batch"),
    )
    md = build_report_markdown(manifest)
    # B must appear before A in the ranked table body.
    assert md.index(MOCK_B) < md.index(MOCK_A)


def test_invalid_or_degraded_model_visibly_marked_not_dropped():
    mr_ok = _scored_model(MOCK_A, cap_score=0.9, attributable=0.1, seed_hash="a" * 64)
    mr_bad = _scored_model(
        MOCK_B, cap_score=0.0, attributable=0.0, seed_hash="b" * 64, error="prime exited 1"
    )
    # also mark mr_bad as an invalid-comparison collision.
    mr_bad.stages.append(
        StageResult(stage=STAGE_PLAN_INGESTION, status=StageStatus.INVALID_COMPARISON)
    )
    batch = E2EBatchResult(
        shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.SUCCESS),
        models=[mr_ok, mr_bad],
        invalid_comparison=True,
    )
    manifest = build_manifest(
        batch,
        comparison_mode=MANIFEST_FROZEN_V1,
        input_hashes={},
        shared_artifact_hashes={},
        versions=collect_versions(),
        batch_root=Path("/tmp/batch"),
    )
    md = build_report_markdown(manifest)
    # not dropped:
    assert MOCK_B in md
    # visibly marked:
    assert "invalid" in md.lower()
    assert "INVALID COMPARISON" in md


def test_secret_in_stage_error_redacted_in_manifest_and_report(tmp_path):
    mr = _scored_model(
        MOCK_A,
        cap_score=0.5,
        attributable=0.1,
        seed_hash="a" * 64,
        error=f"crash: ANTHROPIC_API_KEY={_FAKE_SECRET}",
    )
    mr_b = _scored_model(MOCK_B, cap_score=0.9, attributable=0.2, seed_hash="b" * 64)
    batch = E2EBatchResult(
        shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.SUCCESS),
        models=[mr, mr_b],
    )
    plan = tmp_path / "plan.md"
    reqs = tmp_path / "requirements.md"
    plan.write_text("# plan", encoding="utf-8")
    reqs.write_text("# reqs", encoding="utf-8")
    batch_root = tmp_path / "batch"

    paths = write_batch_outputs(
        batch,
        batch_root,
        plan_paths=[plan],
        requirements_paths=[reqs],
    )
    manifest_text = Path(paths["manifest"]).read_text()
    report_text = Path(paths["report_md"]).read_text()
    assert _FAKE_SECRET not in manifest_text
    assert _FAKE_SECRET not in report_text
    assert "[REDACTED]" in manifest_text


# --------------------------------------------------------------------------- FR-21: advancement


def _advancement_model(
    model: str,
    *,
    cap_score: Optional[float],
    gate_verdict: Optional[str] = "pass",
    ingestion_status: str = StageStatus.SUCCESS,
    has_prime: bool = True,
    error: Optional[str] = None,
    seed_hash: str = "a" * 64,
) -> ModelResult:
    """A scored ModelResult shaped for the FR-21 gate (capability + prime gate_verdict threaded)."""
    mr = ModelResult(model=model)
    mr.seed_hash = seed_hash
    mr.error = error
    mr.stages = [StageResult(stage=STAGE_PLAN_INGESTION, status=ingestion_status)]
    if has_prime:
        mr.stages.append(
            StageResult(
                stage=STAGE_PRIME,
                status=StageStatus.SUCCESS if error is None else StageStatus.FAILED,
                error=error,
            )
        )
    if cap_score is None:
        mr.capability = None
    else:
        mr.capability = {
            "score": cap_score,
            "score_breakdown": {
                "components": {"prime": {"gate_verdict": gate_verdict}},
                "weights": {},
                "penalties": [],
            },
            "capability_prime_only": cap_score,
        }
    return mr


def test_advancement_advances_when_all_criteria_pass():
    mr = _advancement_model(MOCK_A, cap_score=0.8, gate_verdict="pass")
    verdict = evaluate_advancement(mr, DEFAULT_ROUND1_GATE, batch_invalid_comparison=False)
    assert verdict["advanced"] is True
    assert verdict["reason"] == REASON_ADVANCED
    assert verdict["checks"]["capability"]["passed"] is True
    assert verdict["checks"]["prime_gate"]["passed"] is True


def test_advancement_below_threshold_does_not_advance():
    mr = _advancement_model(MOCK_A, cap_score=0.4, gate_verdict="pass")
    verdict = evaluate_advancement(mr, DEFAULT_ROUND1_GATE, batch_invalid_comparison=False)
    assert verdict["advanced"] is False
    assert verdict["reason"] == REASON_BELOW_CAPABILITY
    assert verdict["checks"]["capability"]["observed"] == pytest.approx(0.4)
    assert verdict["checks"]["capability"]["threshold"] == DEFAULT_ROUND1_GATE.min_capability


def test_advancement_missing_capability_is_inputs_missing_not_advanced():
    mr = _advancement_model(MOCK_A, cap_score=None)  # no capability score
    verdict = evaluate_advancement(mr, DEFAULT_ROUND1_GATE, batch_invalid_comparison=False)
    assert verdict["advanced"] is False
    assert verdict["reason"] == REASON_INPUTS_MISSING


def test_advancement_missing_prime_stage_is_inputs_missing():
    mr = _advancement_model(MOCK_A, cap_score=0.9, has_prime=False)
    verdict = evaluate_advancement(mr, DEFAULT_ROUND1_GATE, batch_invalid_comparison=False)
    assert verdict["advanced"] is False
    assert verdict["reason"] == REASON_INPUTS_MISSING


def test_advancement_prime_gate_fail_does_not_advance():
    mr = _advancement_model(MOCK_A, cap_score=0.9, gate_verdict="fail")
    verdict = evaluate_advancement(mr, DEFAULT_ROUND1_GATE, batch_invalid_comparison=False)
    assert verdict["advanced"] is False
    assert verdict["reason"] == "prime_gate_failed"


def test_advancement_batch_invalid_comparison_blocks_all():
    mr = _advancement_model(MOCK_A, cap_score=0.95, gate_verdict="pass")
    verdict = evaluate_advancement(mr, DEFAULT_ROUND1_GATE, batch_invalid_comparison=True)
    assert verdict["advanced"] is False
    assert verdict["reason"] == REASON_INVALID_COMPARISON


def test_custom_gate_threshold_changes_outcome():
    # Same model, two different per-round bars: proves the gate is parameterized (FR-21).
    mr = _advancement_model(MOCK_A, cap_score=0.65, gate_verdict="pass")
    lenient = AdvancementGate(min_capability=0.6)
    strict = AdvancementGate(min_capability=0.9)
    assert evaluate_advancement(mr, lenient, batch_invalid_comparison=False)["advanced"] is True
    strict_verdict = evaluate_advancement(mr, strict, batch_invalid_comparison=False)
    assert strict_verdict["advanced"] is False
    assert strict_verdict["reason"] == REASON_BELOW_CAPABILITY


def test_disabled_criterion_is_not_evaluated():
    # A gate that does not require the prime gate must advance despite a failing gate verdict.
    mr = _advancement_model(MOCK_A, cap_score=0.8, gate_verdict="fail")
    gate = AdvancementGate(min_capability=0.6, require_prime_gate_pass=False)
    verdict = evaluate_advancement(mr, gate, batch_invalid_comparison=False)
    assert verdict["advanced"] is True
    assert verdict["checks"]["prime_gate"]["enabled"] is False


def test_apply_advancement_sets_flag_and_stashes_verdict():
    mr_pass = _advancement_model(MOCK_A, cap_score=0.8, gate_verdict="pass")
    mr_fail = _advancement_model(MOCK_B, cap_score=0.3, gate_verdict="pass", seed_hash="b" * 64)
    batch = E2EBatchResult(
        shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.SUCCESS),
        models=[mr_pass, mr_fail],
    )
    apply_advancement(batch, DEFAULT_ROUND1_GATE)
    assert mr_pass.advanced is True
    assert mr_pass.advancement["reason"] == REASON_ADVANCED
    assert mr_fail.advanced is False
    assert mr_fail.advancement["reason"] == REASON_BELOW_CAPABILITY


def test_manifest_contains_advancement_block_with_gate_and_verdicts():
    mr_pass = _advancement_model(MOCK_A, cap_score=0.8, gate_verdict="pass")
    mr_fail = _advancement_model(MOCK_B, cap_score=0.3, gate_verdict="pass", seed_hash="b" * 64)
    batch = E2EBatchResult(
        shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.SUCCESS),
        models=[mr_pass, mr_fail],
    )
    gate = AdvancementGate(min_capability=0.6)
    apply_advancement(batch, gate)
    manifest = build_manifest(
        batch,
        comparison_mode=MANIFEST_FROZEN_V1,
        input_hashes={},
        shared_artifact_hashes={},
        versions=collect_versions(),
        batch_root=Path("/tmp/batch"),
        gate=gate,
    )
    adv = manifest["advancement"]
    assert adv["gate"]["min_capability"] == 0.6
    assert adv["models"][MOCK_A]["advanced"] is True
    assert adv["models"][MOCK_B]["advanced"] is False
    assert adv["models"][MOCK_A]["reason"] == REASON_ADVANCED
    # per-model manifest entry also reflects ``advanced``.
    by_model = {m["model"]: m for m in manifest["models"]}
    assert by_model[MOCK_A]["advanced"] is True
    assert by_model[MOCK_B]["advanced"] is False


def test_report_shows_advanced_column_and_advancing_line():
    mr_pass = _advancement_model(MOCK_A, cap_score=0.8, gate_verdict="pass")
    mr_fail = _advancement_model(MOCK_B, cap_score=0.3, gate_verdict="pass", seed_hash="b" * 64)
    batch = E2EBatchResult(
        shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.SUCCESS),
        models=[mr_pass, mr_fail],
    )
    apply_advancement(batch, DEFAULT_ROUND1_GATE)
    manifest = build_manifest(
        batch,
        comparison_mode=MANIFEST_FROZEN_V1,
        input_hashes={},
        shared_artifact_hashes={},
        versions=collect_versions(),
        batch_root=Path("/tmp/batch"),
    )
    md = build_report_markdown(manifest)
    assert "Advanced" in md  # new table column header
    assert "Round-1 gate" in md  # header description
    assert "Advancing to next round:" in md
    # the advancing line names the passing model (and not the failing one).
    advancing_line = next(line for line in md.splitlines() if line.startswith("**Advancing"))
    assert MOCK_A in advancing_line
    assert MOCK_B not in advancing_line


def test_write_batch_outputs_persists_advancement_with_custom_gate(tmp_path):
    mr_pass = _advancement_model(MOCK_A, cap_score=0.7, gate_verdict="pass")
    mr_fail = _advancement_model(MOCK_B, cap_score=0.7, gate_verdict="pass", seed_hash="b" * 64)
    batch = E2EBatchResult(
        shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.SUCCESS),
        models=[mr_pass, mr_fail],
    )
    plan = tmp_path / "plan.md"
    reqs = tmp_path / "requirements.md"
    plan.write_text("# plan", encoding="utf-8")
    reqs.write_text("# reqs", encoding="utf-8")
    # Strict gate (0.9) -> neither 0.7 model advances; proves the wired gate is honored end-to-end.
    gate = AdvancementGate(min_capability=0.9)
    paths = write_batch_outputs(
        batch,
        tmp_path / "batch",
        plan_paths=[plan],
        requirements_paths=[reqs],
        gate=gate,
    )
    manifest = json.loads(Path(paths["manifest"]).read_text())
    assert manifest["advancement"]["gate"]["min_capability"] == 0.9
    assert manifest["advancement"]["models"][MOCK_A]["advanced"] is False
    assert manifest["advancement"]["models"][MOCK_B]["advanced"] is False
    # default gate (0.6) would have advanced both -> confirms parameterization took effect.
    assert batch.models[0].advanced is False
