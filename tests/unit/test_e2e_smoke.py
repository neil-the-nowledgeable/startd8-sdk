"""S8 — true end-to-end no-cost smoke test for model_comparison_e2e (FR-20).

Drives the WHOLE compare-models-e2e pipeline through the single injectable ``runner`` seam with a
deterministic fake that writes REALISTIC stage artifacts, so extraction/scoring/manifest/report all
exercise real code paths with ZERO external API calls or subprocesses:

    orchestrate_e2e(runner=fake) -> score_batch -> apply_advancement -> write_batch_outputs

The fake runner, keyed on the command it receives, writes exactly what a real stage would:

- ``run-cap-delivery.sh`` (shared preamble) → a placeholder manifest + ``run-provenance.json`` into
  ``batch/_shared/`` (returncode 0). Runs EXACTLY once for the whole batch (FR-7).
- ``run-plan-ingestion.sh`` → ``<output>/prime-context-seed.json`` (DISTINCT per model so seed
  hashes differ — FR-15 must not trip) AND ``<output>/plan-ingestion-diagnostic.json`` carrying the
  resolved agents (assessor/transformer == the model under test, so ``assert_model_pin`` passes), a
  ``seed_quality_score`` and ``totals.cost_usd``.
- ``run_prime_workflow.py`` → ``<output>/prime-result.json`` with ``total_cost_usd``, a
  ``cross_file_gate`` (verdict + score) and succeeded/failed counts. The two models differ in
  quality so ranking + advancement diverge (strong advances; weak does not).

Asserts the full feature: cap-delivery once, two isolated trees + artifact sets, distinct seed
hashes (valid comparison), a ranked report + manifest with all FR-16 evidence, the advancement
block + report column naming only the strong model, the weak model present-but-not-advanced
(degrade-honest), and FR-19 redaction of an injected secret reaching the persisted manifest/report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pytest

from startd8.model_comparison_e2e import (
    DEFAULT_ROUND1_GATE,
    MANIFEST_FROZEN_V1,
    MANIFEST_SCHEMA_VERSION,
    STAGE_PLAN_INGESTION,
    STAGE_PRIME,
    STAGE_SHARED_PREAMBLE,
    AdvancementGate,
    StageStatus,
    apply_advancement,
    orchestrate_e2e,
    score_batch,
    write_batch_outputs,
)

pytestmark = pytest.mark.unit


# Two distinct mock specs that pass preflight WITHOUT network/keys (MockProvider.validate_config).
MODEL_STRONG = "mock:strong"
MODEL_WEAK = "mock:weak"

# A leaked-looking secret injected into the WEAK model's prime stderr, to prove FR-19 redaction
# survives all the way into the persisted manifest + report.
_FAKE_SECRET = "sk-ant-leakedsmoketestsecret0123456789"


def _runner_record(
    cmd: list[str],
    *,
    returncode: int = 0,
    duration: float = 0.1,
    timed_out: bool = False,
    stdout: str = "",
    stderr: str = "",
) -> dict[str, Any]:
    """A dict shaped exactly like ``model_comparison.run_command``'s return."""
    return {
        "command": list(cmd),
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
    }


class RealisticFakeRunner:
    """Deterministic fake that writes the artifacts each real stage would — zero subprocess/network.

    Per-model quality is driven by ``profiles[model]``: a strong model gets a passing cross-file gate
    and high completion (→ advances); a weak model gets a failing gate (→ does not advance). Each
    model also gets DISTINCT seed bytes so FR-15 (seed-hash collision) does not trip.
    """

    def __init__(self, profiles: dict[str, dict[str, Any]]) -> None:
        self.calls: list[list[str]] = []
        self._profiles = profiles

    # -- command classification --------------------------------------------------------------
    @staticmethod
    def _classify(cmd: list[str]) -> str:
        joined = " ".join(cmd)
        if "run-cap-delivery.sh" in joined:
            return STAGE_SHARED_PREAMBLE
        if "run-plan-ingestion.sh" in joined:
            return STAGE_PLAN_INGESTION
        if "run_prime_workflow.py" in joined:
            return STAGE_PRIME
        return "unknown"

    @staticmethod
    def _ingestion_target(cmd: list[str]) -> tuple[str, Path]:
        # cmd = [bash, run-plan-ingestion.sh, --config, <path>]; config carries the model pin.
        cfg = json.loads(Path(cmd[cmd.index("--config") + 1]).read_text())
        return cfg["assessor_agent"], Path(cfg["output_dir"])

    @staticmethod
    def _prime_target(cmd: list[str]) -> tuple[str, Path]:
        model = cmd[cmd.index("--lead-agent") + 1]
        output = Path(cmd[cmd.index("--output-dir") + 1])
        return model, output

    @staticmethod
    def _shared_dir(cmd: list[str]) -> Path:
        return Path(cmd[cmd.index("--output-dir") + 1])

    # -- the runner seam ---------------------------------------------------------------------
    def __call__(
        self, cmd: list[str], cwd: Path, timeout: Optional[float] = None, on_output: Any = None
    ) -> dict[str, Any]:
        self.calls.append(list(cmd))
        stage = self._classify(cmd)

        if stage == STAGE_SHARED_PREAMBLE:
            shared = self._shared_dir(cmd)
            shared.mkdir(parents=True, exist_ok=True)
            # A placeholder manifest + provenance, like a real cap-delivery preamble would emit.
            (shared / "validation-report.json").write_text(
                json.dumps({"status": "ok", "preamble": "shared-placeholder"}), encoding="utf-8"
            )
            (shared / "run-provenance.json").write_text(
                json.dumps({"project": "compare-models-e2e", "shared": True}), encoding="utf-8"
            )
            return _runner_record(cmd)

        if stage == STAGE_PLAN_INGESTION:
            model, output = self._ingestion_target(cmd)
            output.mkdir(parents=True, exist_ok=True)
            prof = self._profiles[model]
            # Seed bytes are DISTINCT per model (FR-15 must not trip).
            (output / "prime-context-seed.json").write_text(
                json.dumps({"model": model, "seed": prof["seed"]}), encoding="utf-8"
            )
            # Diagnostic: resolved agents pinned to the model (FR-14), plus cost + quality signals.
            diag = {
                "totals": {
                    "models": {
                        "assessor": model,
                        "transformer": model,
                        "default_provider": model,
                    },
                    "cost_usd": prof["ingestion_cost"],
                },
                "seed_quality_score": prof["seed_quality"],
            }
            (output / "plan-ingestion-diagnostic.json").write_text(
                json.dumps(diag), encoding="utf-8"
            )
            return _runner_record(cmd)

        if stage == STAGE_PRIME:
            model, output = self._prime_target(cmd)
            output.mkdir(parents=True, exist_ok=True)
            prof = self._profiles[model]
            processed = prof["processed"]
            succeeded = prof["succeeded"]
            payload = {
                "success": prof["prime_returncode"] == 0,
                "processed": processed,
                "succeeded": succeeded,
                "failed": processed - succeeded,
                "cross_file_gate": {
                    "verdict": prof["gate_verdict"],
                    "score": prof["gate_score"],
                    "cross_file_failures": [],
                },
                "total_cost_usd": prof["prime_cost"],
            }
            (output / "prime-result.json").write_text(json.dumps(payload), encoding="utf-8")
            # On a failing prime the runner's stderr becomes the persisted stage error (FR-19
            # redaction path); on success stderr is discarded by run_prime, like the real seam.
            return _runner_record(
                cmd, returncode=prof["prime_returncode"], stderr=prof.get("stderr", "")
            )

        return _runner_record(cmd)


def _fixture_inputs(tmp_path: Path) -> tuple[list[Path], list[Path], Path, Path]:
    """Minimal plan + requirements + a tiny source-root to copy + a batch root (all under tmp)."""
    plan = tmp_path / "plan.md"
    reqs = tmp_path / "requirements.md"
    plan.write_text("# plan\n\nBuild a tiny service.\n", encoding="utf-8")
    reqs.write_text("# requirements\n\n- FR-1: it works\n", encoding="utf-8")

    source_root = tmp_path / "src_tree"
    source_root.mkdir()
    (source_root / "main.py").write_text("print('hello')\n", encoding="utf-8")  # small → fast copy

    batch_root = tmp_path / "batch"
    return [plan], [reqs], source_root, batch_root


def _statuses(stages: list[Any]) -> dict[str, str]:
    return {s.stage: s.status for s in stages}


def test_e2e_smoke_full_pipeline_zero_spend(tmp_path: Path):
    """Capstone: the whole pipeline runs through the fake runner, producing two isolated trees,
    one ranked report + manifest, with the strong model advancing and the weak model present but
    not advanced — and an injected secret redacted in the persisted artifacts."""
    plans, reqs, source_root, batch_root = _fixture_inputs(tmp_path)

    # Strong: prime ok + gate pass + high completion → advances.
    # Weak: prime FAILS (returncode 1, secret in stderr) → degraded + does NOT advance. The failure
    # is the realistic seam that carries stderr into the persisted (and redacted) stage error.
    profiles = {
        MODEL_STRONG: {
            "seed": "strong-unique-seed",
            "ingestion_cost": 0.04,
            "seed_quality": 0.9,
            "processed": 10,
            "succeeded": 10,
            "gate_verdict": "pass",
            "gate_score": 0.95,
            "prime_cost": 0.30,
            "prime_returncode": 0,
        },
        MODEL_WEAK: {
            "seed": "weak-unique-seed",
            "ingestion_cost": 0.05,
            "seed_quality": 0.4,
            "processed": 10,
            "succeeded": 3,
            "gate_verdict": "fail",
            "gate_score": 0.30,
            "prime_cost": 0.55,
            "prime_returncode": 1,
            # Inject a leaked secret into the weak model's prime stderr (FR-19 redaction probe).
            "stderr": f"prime warning: ANTHROPIC_API_KEY={_FAKE_SECRET} (do not persist!)",
        },
    }
    runner = RealisticFakeRunner(profiles)

    # ---- run the real flow (FR-6) ----------------------------------------------------------
    batch = orchestrate_e2e(
        [MODEL_STRONG, MODEL_WEAK],
        plans,
        reqs,
        source_root,
        batch_root,
        runner=runner,
        log=lambda _m: None,
    )

    # Per-model output dirs the realistic runner actually wrote into.
    def output_dir_for(mr):
        return batch_root / mr.slug / "output"

    score_batch(batch, output_dir_for=output_dir_for)
    apply_advancement(batch, DEFAULT_ROUND1_GATE)
    paths = write_batch_outputs(
        batch,
        batch_root,
        comparison_mode=MANIFEST_FROZEN_V1,
        plan_paths=plans,
        requirements_paths=reqs,
    )

    # =========================================================================== assertions

    # --- (1) NO real network/subprocess: every "execution" went through the fake runner. ----
    # cap-delivery ran EXACTLY ONCE for the whole batch (FR-7).
    cap_calls = [c for c in runner.calls if "run-cap-delivery.sh" in " ".join(c)]
    assert len(cap_calls) == 1, runner.calls
    # The fake observed the full per-model stage set: 2 ingestion + 2 prime.
    assert sum(1 for c in runner.calls if "run-plan-ingestion.sh" in " ".join(c)) == 2
    assert sum(1 for c in runner.calls if "run_prime_workflow.py" in " ".join(c)) == 2

    # --- (2) batch outcome: not aborted, valid comparison, both models present --------------
    assert batch.aborted is False
    assert batch.invalid_comparison is False
    assert batch.shared.status == StageStatus.SUCCESS
    assert [m.model for m in batch.models] == [MODEL_STRONG, MODEL_WEAK]

    strong, weak = batch.models[0], batch.models[1]

    # --- (3) two ISOLATED per-model trees, each with their OWN output artifacts -------------
    for mr in (strong, weak):
        model_root = batch_root / mr.slug
        assert (model_root / "workdir" / "main.py").is_file(), "isolated source copy missing"
        out = model_root / "output"
        assert (out / "prime-context-seed.json").is_file()
        assert (out / "plan-ingestion-diagnostic.json").is_file()
        assert (out / "prime-result.json").is_file()
    # The two workdirs are genuinely separate directories.
    assert (batch_root / strong.slug) != (batch_root / weak.slug)

    # --- (4) distinct seed hashes → valid comparison (no FR-15 collapse) --------------------
    assert strong.seed_hash and weak.seed_hash
    assert strong.seed_hash != weak.seed_hash
    assert _statuses(strong.stages)[STAGE_PLAN_INGESTION] == StageStatus.SUCCESS
    assert _statuses(strong.stages)[STAGE_PRIME] == StageStatus.SUCCESS
    # Weak ingested fine but its prime FAILED — batch continued past it (FR-5 continue-on-failure).
    assert _statuses(weak.stages)[STAGE_PLAN_INGESTION] == StageStatus.SUCCESS
    assert _statuses(weak.stages)[STAGE_PRIME] == StageStatus.FAILED
    assert weak.error is not None

    # --- (5) scoring exercised real extraction: strong out-scores weak ----------------------
    assert strong.capability is not None and weak.capability is not None
    assert strong.capability["score"] > weak.capability["score"]
    assert strong.cost_fields["cost_attributable_usd"] == pytest.approx(0.04 + 0.30)
    assert weak.cost_fields["cost_attributable_usd"] == pytest.approx(0.05 + 0.55)

    # --- (6) advancement: strong advances, weak does NOT (degrade-honest, not dropped) ------
    assert strong.advanced is True
    assert weak.advanced is False

    # --- (7) manifest schema + per-model evidence (FR-16 + FR-14/15 + FR-9 + FR-21) ---------
    manifest = json.loads(Path(paths["manifest"]).read_text())
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["comparison_mode"] == MANIFEST_FROZEN_V1
    assert "generated_at" in manifest
    assert len(manifest["inputs"]) == 2  # frozen plan + reqs hashed
    by_model = {m["model"]: m for m in manifest["models"]}
    for spec in (MODEL_STRONG, MODEL_WEAK):
        entry = by_model[spec]
        # FR-14 resolved agents (pin evidence)
        assert entry["resolved_agents"]["assessor"] == spec
        assert entry["resolved_agents"]["transformer"] == spec
        # FR-15 seed hash
        assert entry["seed_hash"]
        # FR-9 three cost fields
        cf = entry["cost_fields"]
        for key in (
            "cost_attributable_usd",
            "cost_shared_preamble_usd",
            "cost_total_loaded_usd",
        ):
            assert key in cf
        assert cf["cost_attributable_usd"] is not None
        # FR-9 capability
        assert "score" in entry["capability"]
    # FR-21 top-level advancement block names both models with verdicts.
    adv = manifest["advancement"]
    assert adv["gate"]["min_capability"] == DEFAULT_ROUND1_GATE.min_capability
    assert adv["models"][MODEL_STRONG]["advanced"] is True
    assert adv["models"][MODEL_WEAK]["advanced"] is False

    # --- (8) report.md: ranks strong first, has caveat + advancement column + advancing line -
    report = Path(paths["report_md"]).read_text()
    assert report.index(MODEL_STRONG) < report.index(MODEL_WEAK)  # strong ranked first
    assert "indicative" in report.lower()  # NR-3 single-run caveat
    assert "Advanced" in report  # advancement column header
    advancing_line = next(
        line for line in report.splitlines() if line.startswith("**Advancing")
    )
    assert MODEL_STRONG in advancing_line
    assert MODEL_WEAK not in advancing_line  # weak named NOWHERE in the advancing line
    # Weak model is present but visibly marked degraded — NOT dropped (degrade-honest).
    assert MODEL_WEAK in report
    assert "degraded" in report.lower()

    # --- (9) FR-19 redaction reached the persisted manifest + report ------------------------
    manifest_text = Path(paths["manifest"]).read_text()
    assert _FAKE_SECRET not in manifest_text
    assert _FAKE_SECRET not in report
    assert "[REDACTED]" in manifest_text


def test_e2e_smoke_custom_strict_gate_advances_no_one(tmp_path: Path):
    """A stricter Round gate (FR-21 parameterization) wired end-to-end advances neither model,
    yet both still appear in the manifest + report (degrade-honest)."""
    plans, reqs, source_root, batch_root = _fixture_inputs(tmp_path)
    profiles = {
        MODEL_STRONG: {
            "seed": "s", "ingestion_cost": 0.04, "seed_quality": 0.9,
            "processed": 10, "succeeded": 9, "gate_verdict": "pass", "gate_score": 0.8,
            "prime_cost": 0.3, "prime_returncode": 0,
        },
        MODEL_WEAK: {
            "seed": "w", "ingestion_cost": 0.05, "seed_quality": 0.8,
            "processed": 10, "succeeded": 8, "gate_verdict": "pass", "gate_score": 0.7,
            "prime_cost": 0.4, "prime_returncode": 0,
        },
    }
    runner = RealisticFakeRunner(profiles)
    batch = orchestrate_e2e(
        [MODEL_STRONG, MODEL_WEAK], plans, reqs, source_root, batch_root,
        runner=runner, log=lambda _m: None,
    )
    score_batch(batch, output_dir_for=lambda mr: batch_root / mr.slug / "output")

    strict = AdvancementGate(min_capability=0.99)  # nobody clears it
    paths = write_batch_outputs(
        batch, batch_root, plan_paths=plans, requirements_paths=reqs, gate=strict,
    )
    manifest = json.loads(Path(paths["manifest"]).read_text())
    assert manifest["advancement"]["gate"]["min_capability"] == 0.99
    assert manifest["advancement"]["models"][MODEL_STRONG]["advanced"] is False
    assert manifest["advancement"]["models"][MODEL_WEAK]["advanced"] is False
    # both still present
    assert {m["model"] for m in manifest["models"]} == {MODEL_STRONG, MODEL_WEAK}
    report = Path(paths["report_md"]).read_text()
    advancing_line = next(line for line in report.splitlines() if line.startswith("**Advancing"))
    assert "none" in advancing_line.lower()
