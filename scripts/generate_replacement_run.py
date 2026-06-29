#!/usr/bin/env python3
"""Generate a validated replacement suite authoring artifact using the declarative policy.

This script executes a single run (such as ordinal 27) using gemini-cli, checks the generated Python
file's imports for forbidden dependencies, retries if needed, promotes the result to the store raw path,
and records the replacement relationship in dispositions.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.run_cross_tool_bias_authoring import (
    TOOL_POLICY,
    build_tool_env,
    execute_run,
    render_prompt,
    provision_workspace,
    record_attempt,
    fetch_doppler_credentials,
    required_credential_names,
    command_policy_metadata,
    prepare,
)
from scripts.intake_and_normalize_artifacts import check_suite_imports

DEFAULT_STORE_ROOT = REPO / ".startd8/bias-audit-store"
DEFAULT_BATCH_ID = "pricing-cross-tool-authoring-v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", type=Path, required=True, help="Promoted store root directory")
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--ordinal", type=int, required=True, help="Schedule ordinal to generate replacement for")
    args = parser.parse_args(argv)

    batch_root = args.store_root / args.batch_id
    if not batch_root.is_dir():
        print(f"Error: batch root does not exist: {batch_root}", file=sys.stderr)
        return 1

    manifest_path = REPO / "docs/design/benchmark-bias-audit/bias_audit_openai/cross_tool_experiment_manifest.json"
    manifest = prepare._load_manifest(manifest_path)
    schedule = prepare.build_schedule(manifest)

    # Find the target run in the schedule
    target_item = None
    for item in schedule:
        if item["ordinal"] == args.ordinal:
            target_item = item
            break

    if target_item is None:
        print(f"Error: ordinal {args.ordinal} not found in schedule", file=sys.stderr)
        return 1

    experiment = target_item["experiment"]
    tool_id = target_item["tool_id"]
    author_vendor = target_item["author_vendor"]
    sample_index = target_item["sample_index"]

    print(f"Target run: ordinal={args.ordinal}, experiment={experiment}, tool={tool_id}, sample={sample_index}")

    # Verify tool availability
    tools = prepare.preflight_tools(manifest)
    tool_info = None
    for t in tools:
        if t["tool_id"] == tool_id:
            tool_info = t
            break

    if not tool_info or not tool_info["available"]:
        print(f"Error: required tool {tool_id} is not available locally.", file=sys.stderr)
        return 1

    executable_path = tool_info["path"]
    executable_version = tool_info["version"]

    # Retrieve Doppler credentials
    needed = required_credential_names()
    print("Retrieving credentials from Doppler...")
    credentials = fetch_doppler_credentials(needed)
    if tool_id in TOOL_POLICY:
        cred_name = TOOL_POLICY[tool_id]["credential_env"]
        if not credentials.get(cred_name):
            print(f"Error: missing required Doppler key {cred_name}", file=sys.stderr)
            return 1

    # Prep replacement identifiers
    run_id = f"{manifest['experiment_id']}-run-{args.ordinal:02d}-replacement-1"
    run_dir_name = f"run_{args.ordinal:02d}_{experiment}_{tool_id}_sample_{sample_index}_replacement_1"
    raw_root = batch_root / "raw"
    run_capture_dir = raw_root / run_dir_name
    run_workspace = Path(f"/private/tmp/startd8-cross-tool-bias/workspaces/run_{args.ordinal:02d}_replacement_1")

    # Render prompt and build environments
    prompt_text = render_prompt(
        repo=REPO,
        experiment=experiment,
        tool_id=tool_id,
        author_vendor=author_vendor,
        sample_index=sample_index,
        ordinal=args.ordinal,
        run_id=run_id,
        working_directory=run_workspace,
        clean_workspace=run_workspace,
        executable_path=executable_path,
        executable_version=executable_version
    )
    tool_env, env_exposure = build_tool_env(tool_id, credentials)
    command_policy = command_policy_metadata(tool_id, executable_path, executable_version)

    success = False
    attempts = 0
    attempt_records = []
    max_retries = 3

    print(f"Starting replacement generation for run ID: {run_id}...")
    while not success and attempts < max_retries:
        attempts += 1
        print(f"Attempt {attempts} of {max_retries}...")

        provision_workspace(REPO, run_workspace, experiment)

        start_time = datetime.now(timezone.utc).isoformat()
        code, stdout, stderr = execute_run(tool_id, executable_path, prompt_text, run_workspace, tool_env)
        end_time = datetime.now(timezone.utc).isoformat()

        # Check output files
        if experiment == "spec_author":
            required_files = ["spec.md", "authoring_manifest.json"]
        else:
            required_files = ["suite.py", "suite_manifest.json", "authoring_manifest.json"]
        missing_files = [f for f in required_files if not (run_workspace / f).is_file()]

        valid_imports = True
        import_detail = ""
        if code == 0 and not missing_files:
            if experiment == "suite_author":
                suite_code = (run_workspace / "suite.py").read_text(encoding="utf-8")
                forbidden = check_suite_imports(suite_code)
                if forbidden:
                    valid_imports = False
                    import_detail = f"forbidden imports: {', '.join(forbidden)}"

        if code == 0 and not missing_files and valid_imports:
            success = True
            status_str = "success"
            print("  Generation succeeded and imports are valid.")
        else:
            status_str = "failed"
            fail_reason = import_detail if not valid_imports else f"exit_code={code}, missing_files={missing_files}"
            print(f"  Attempt failed: {fail_reason}")

        attempt_meta = {
            "attempt": attempts,
            "status": status_str,
            "exit_code": code,
            "missing_files": missing_files,
            "started_at_utc": start_time,
            "finished_at_utc": end_time,
        }
        if not valid_imports:
            attempt_meta["import_validation_failed"] = import_detail

        # Record attempt
        run_capture_dir.mkdir(parents=True, exist_ok=True)
        record_attempt(run_capture_dir, attempts, prompt_text=prompt_text, stdout=stdout,
                       stderr=stderr, workspace=run_workspace, attempt_meta=attempt_meta)
        attempt_records.append(attempt_meta)

        if run_workspace.exists():
            shutil.rmtree(run_workspace)

    if not success:
        print("Error: all attempts to generate a compliant replacement run failed.", file=sys.stderr)
        return 1

    # Promote final attempt
    final_dir = run_capture_dir / "attempts" / f"attempt_{attempts:02d}"
    for name in ("rendered_prompt.md", "stdout.log", "stderr.log"):
        shutil.copy2(final_dir / name, run_capture_dir / name)
    for child in (final_dir / "workspace").iterdir():
        dest = run_capture_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dest)

    metadata = {
        "run_id": run_id,
        "experiment": experiment,
        "tool_id": tool_id,
        "author_vendor": author_vendor,
        "sample_index": sample_index,
        "ordinal": args.ordinal,
        "status": "success",
        "exit_code": attempt_records[-1]["exit_code"],
        "missing_files": attempt_records[-1]["missing_files"],
        "started_at_utc": attempt_records[0]["started_at_utc"],
        "finished_at_utc": attempt_records[-1]["finished_at_utc"],
        "attempts": attempts,
        "attempt_records": attempt_records,
        "command_policy": command_policy,
        "env_exposure": env_exposure,
    }
    (run_capture_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Replacement run metadata recorded: {run_capture_dir / 'metadata.json'}")

    # Write dispositions.json in batch root
    dispositions_file = batch_root / "dispositions.json"
    dispositions = []
    if dispositions_file.is_file():
        try:
            dispositions = json.loads(dispositions_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    # Avoid duplicating
    dispositions = [d for d in dispositions if d.get("rejected_run_id") != f"{manifest['experiment_id']}-run-{args.ordinal:02d}"]
    dispositions.append({
        "rejected_run_id": f"{manifest['experiment_id']}-run-{args.ordinal:02d}",
        "replacement_run_id": run_id,
        "reason_code": "forbidden_import",
        "reviewer": "antigravity-agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    dispositions_file.write_text(json.dumps(dispositions, indent=2) + "\n", encoding="utf-8")
    print(f"Dispositions recorded: {dispositions_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
