"""FR-H5 regression: `scripts/generate_observability_artifacts.py` must thread an authored
`--observability-yaml` path into `generate_observability_artifacts(observability_yaml_path=...)`.

Client friction (household-o11y `concierge-friction.jsonl`, entry H5): the authored
`observability.yaml` was silently dropped because the shipped generation path never wired the flag —
the underlying function accepts `observability_yaml_path` (additive/opt-in, `artifact_generator.py`)
but the CLI had no way to pass it. These tests fail on `main` (no `--observability-yaml` arg) and pass
with the wiring.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "generate_observability_artifacts.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("_gen_obs_script", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_main(monkeypatch, tmp_path, extra_argv):
    """Run the script's main() with a spy generator; return the captured kwargs."""
    mod = _load_script_module()
    captured = {}

    def _spy(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(artifacts=[], services_processed=0, services_skipped=0)

    monkeypatch.setattr(mod, "generate_observability_artifacts", _spy)
    onboarding = tmp_path / "onboarding-metadata.json"
    onboarding.write_text("{}", encoding="utf-8")
    argv = [
        "generate_observability_artifacts.py",
        "--onboarding-metadata", str(onboarding),
        "--output-dir", str(tmp_path / "out"),
        *extra_argv,
    ]
    monkeypatch.setattr("sys.argv", argv)
    mod.main()
    return captured


def test_observability_yaml_flag_threads_the_path(monkeypatch, tmp_path):
    obs = tmp_path / "observability.yaml"
    obs.write_text("alerting: {}\n", encoding="utf-8")
    captured = _run_main(monkeypatch, tmp_path, ["--observability-yaml", str(obs)])
    assert "observability_yaml_path" in captured, (
        "the CLI must forward the authored observability.yaml (FR-H5) — it was silently dropped"
    )
    assert captured["observability_yaml_path"] == obs


def test_absent_flag_forwards_none(monkeypatch, tmp_path):
    """Additive + opt-in: no flag ⇒ observability_yaml_path=None (no new artifact, manifest intact)."""
    captured = _run_main(monkeypatch, tmp_path, [])
    assert captured.get("observability_yaml_path") is None
