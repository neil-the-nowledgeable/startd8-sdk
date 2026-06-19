#!/usr/bin/env python3
"""Validate and freeze a cross-tool pricing-bias experiment before authoring runs.

This command deliberately prepares rather than invokes external agent CLIs. It validates the
pre-registered controls, checks frozen source checksums, rejects ambient-instruction workspaces,
and emits a deterministic randomized schedule. External authoring is a later explicit step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    REPO / "docs/design/benchmark-bias-audit/bias_audit_openai/cross_tool_experiment_manifest.json"
)
REQUIRED_VENDORS = {"anthropic", "openai", "google"}


class ManifestError(ValueError):
    """The pre-registration cannot safely produce a comparable experiment."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest: {exc}") from exc
    if data.get("schema_version") != "1.0":
        raise ManifestError("schema_version must be '1.0'")
    if data.get("status") != "pre_registered":
        raise ManifestError("status must be 'pre_registered'")
    return data


def validate_manifest(manifest: dict[str, Any], repo: Path = REPO) -> None:
    if not isinstance(manifest.get("experiment_id"), str) or not manifest["experiment_id"]:
        raise ManifestError("experiment_id is required")

    artifacts = manifest.get("source_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ManifestError("source_artifacts must be a non-empty list")
    artifact_ids = set()
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, str) or artifact_id in artifact_ids:
            raise ManifestError("source artifact ids must be unique strings")
        artifact_ids.add(artifact_id)
        path = repo / str(artifact.get("path", ""))
        expected = artifact.get("sha256")
        if not path.is_file():
            raise ManifestError(f"source artifact missing: {artifact_id}: {path}")
        if not isinstance(expected, str) or _sha256(path) != expected:
            raise ManifestError(f"source checksum mismatch: {artifact_id}")

    authoring = manifest.get("authoring") or {}
    samples = authoring.get("samples_per_tool")
    if not isinstance(samples, int) or samples < 5:
        raise ManifestError("authoring.samples_per_tool must be an integer >= 5")
    tools = authoring.get("tools")
    if not isinstance(tools, list) or len(tools) != 3:
        raise ManifestError("authoring.tools must contain exactly three vendor arms")
    vendors = {tool.get("author_vendor") for tool in tools}
    if vendors != REQUIRED_VENDORS:
        raise ManifestError("authoring.tools must contain Anthropic, OpenAI, and Google exactly once")
    if len({tool.get("id") for tool in tools}) != len(tools):
        raise ManifestError("authoring tool ids must be unique")
    experiments = authoring.get("experiments")
    if {item.get("id") for item in experiments or []} != {"suite_author", "spec_author"}:
        raise ManifestError("authoring.experiments must contain suite_author and spec_author")
    for item in experiments:
        if not set(item.get("frozen_inputs") or []).issubset(artifact_ids):
            raise ManifestError(f"experiment {item.get('id')} references an unknown frozen input")

    controls = manifest.get("execution_controls") or {}
    if controls.get("clean_workspace_required") is not True:
        raise ManifestError("clean_workspace_required must be true")
    if set(controls.get("forbidden_ambient_instruction_files") or []) != {"CLAUDE.md", "AGENTS.md"}:
        raise ManifestError("forbidden ambient instruction files must be CLAUDE.md and AGENTS.md")

    scoring = manifest.get("scoring") or {}
    if scoring.get("frozen_proto") not in artifact_ids:
        raise ManifestError("scoring.frozen_proto must name a source artifact")
    if scoring.get("frozen_behavioral_oracle") not in artifact_ids:
        raise ManifestError("scoring.frozen_behavioral_oracle must name a source artifact")
    if scoring.get("repetitions_per_model_spec_cell") != 5:
        raise ManifestError("scoring.repetitions_per_model_spec_cell must be 5")
    if scoring.get("budget_approval") != "required_before_scoring":
        raise ManifestError("scoring must require budget approval")


def build_schedule(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    authoring = manifest["authoring"]
    schedule = [
        {
            "experiment": experiment["id"],
            "tool_id": tool["id"],
            "author_vendor": tool["author_vendor"],
            "sample_index": sample_index,
        }
        for experiment in authoring["experiments"]
        for tool in authoring["tools"]
        for sample_index in range(1, authoring["samples_per_tool"] + 1)
    ]
    random.Random(manifest["randomization"]["schedule_seed"]).shuffle(schedule)
    for ordinal, item in enumerate(schedule, start=1):
        item["ordinal"] = ordinal
    return schedule


def _assert_clean_workspace(workdir: Path, controls: dict[str, Any], repo: Path = REPO) -> None:
    resolved = workdir.resolve()
    try:
        resolved.relative_to(repo.resolve())
    except ValueError:
        pass
    else:
        raise ManifestError("workdir must be outside the repository to avoid ambient instructions")
    for parent in (resolved, *resolved.parents):
        for name in controls["forbidden_ambient_instruction_files"]:
            if (parent / name).is_file():
                raise ManifestError(f"ambient instruction file found: {parent / name}")


def prepare(manifest_path: Path, output_dir: Path, *, repo: Path = REPO) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    validate_manifest(manifest, repo)
    _assert_clean_workspace(output_dir, manifest["execution_controls"], repo)
    schedule = build_schedule(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_bytes = manifest_path.read_bytes()
    pre_registration = {
        "schema_version": manifest["schema_version"],
        "experiment_id": manifest["experiment_id"],
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "authoring_runs_planned": len(schedule),
        "scoring_status": manifest["scoring"]["status"],
        "budget_approval": manifest["scoring"]["budget_approval"],
    }
    (output_dir / "pre-registration.json").write_text(
        json.dumps(pre_registration, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "authoring-schedule.json").write_text(
        json.dumps(schedule, indent=2) + "\n", encoding="utf-8"
    )
    return pre_registration


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v1"),
    )
    parser.add_argument("--prepare", action="store_true", help="Write the immutable pre-registration and schedule.")
    args = parser.parse_args(argv)
    try:
        manifest = _load_manifest(args.manifest)
        validate_manifest(manifest)
        _assert_clean_workspace(args.output_dir, manifest["execution_controls"])
        if not args.prepare:
            print(f"validated {manifest['experiment_id']}: {len(build_schedule(manifest))} authoring runs planned")
            print("dry-run only; pass --prepare to write the pre-registration and schedule")
            return 0
        result = prepare(args.manifest, args.output_dir)
    except ManifestError as exc:
        print(f"preflight blocked: {exc}", file=sys.stderr)
        return 2
    print(f"prepared {result['experiment_id']} → {args.output_dir}")
    print(f"planned authoring runs: {result['authoring_runs_planned']}")
    print(f"scoring: {result['scoring_status']} ({result['budget_approval']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
