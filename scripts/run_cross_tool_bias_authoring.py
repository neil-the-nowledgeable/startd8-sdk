#!/usr/bin/env python3
"""Gate external cross-tool authoring runs behind the frozen experiment controls.

Dry-run emits the deterministic run plan. ``--run`` is intentionally fail-closed until every
pre-registered authoring tool and the independent oracle/mutant admission gate are accepted.
``--smoke`` invokes a bounded non-evidence subset for pipeline validation only; smoke artifacts are
segregated and explicitly marked as non-evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PREPARE_SCRIPT = REPO / "scripts/prepare_cross_tool_bias_experiment.py"
GATE_PATH = REPO / "docs/design/benchmark-bias-audit/bias_audit_openai/oracle/validation-gate.json"

# --- Phase 1 hardening: declarative, versioned per-tool execution policy ------------------------
# Single source of truth for how each authoring CLI is launched. Captures argv, the ONE Doppler
# credential the tool may receive, the env names that credential is injected as, non-secret extra
# env, and a documented rationale for every privilege-bearing flag. Recorded into run metadata as
# NAMES + flags only — never secret values.
TOOL_POLICY_VERSION = "tool-policy/1"
DEFAULT_SMOKE_TIMEOUT_SECONDS = 600.0
TOOL_POLICY: dict[str, dict] = {
    "claude-code": {
        "vendor": "anthropic",
        "tool_name": "claude",
        "argv": ["--print", "--permission-mode", "bypassPermissions"],
        # Doppler source secret -> env names set to that value inside ONLY this tool's child process.
        "credential_env": "ANTHROPIC_API_KEY",
        "inject_as": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "extra_env": {},
        "flag_rationale": {
            "--print": "non-interactive headless output; required for unattended capture",
            "--permission-mode=bypassPermissions": (
                "headless authoring must write suite/spec files into the isolated per-run workspace "
                "without interactive approval. Scoped by the isolated workspace + scrubbed "
                "single-credential env, NOT by the tool's own prompt. Revisit if a narrower headless "
                "write mode becomes available."),
        },
    },
    "codex-cli": {
        "vendor": "openai",
        "tool_name": "codex",
        "argv": ["exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                 "--skip-git-repo-check", "-s", "workspace-write"],
        "credential_env": "OPENAI_API_KEY",
        "inject_as": ["OPENAI_API_KEY", "CODEX_API_KEY"],
        "extra_env": {},
        "flag_rationale": {
            "exec": "non-interactive subcommand",
            "--ephemeral": "no persistent state carried across runs",
            "--ignore-user-config,--ignore-rules": (
                "neutralize ambient user config so every vendor gets identical inputs (bias control)"),
            "--skip-git-repo-check": "the isolated workspace is intentionally not a git repo",
            "-s=workspace-write": (
                "smallest sandbox that still lets the tool author files in its workspace; NOT full "
                "system/danger access"),
        },
    },
    "gemini-cli": {
        "vendor": "google",
        "tool_name": "gemini",
        "argv": ["--skip-trust", "--yolo", "-p", ""],
        "credential_env": "GOOGLE_API_KEY",
        "inject_as": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "extra_env": {"GEMINI_CLI_TRUST_WORKSPACE": "true"},
        "flag_rationale": {
            "--skip-trust,--yolo": (
                "gemini-cli exposes no finer-grained non-interactive auto-approve; required for "
                "headless authoring. Mitigated by the isolated per-run workspace + scrubbed "
                "single-credential env. REVISIT if a scoped flag becomes available."),
            "-p": "prompt supplied via argument/stdin (non-interactive)",
        },
    },
}

# Minimal NON-SECRET base environment passed to every child. Deliberately NOT os.environ.copy() and
# NOT the Doppler dump: only what a CLI needs to locate its binary/runtime. The single tool credential
# (above) is added per run; nothing else from the ambient environment reaches a subprocess.
_BASE_ENV_ALLOWLIST = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SHELL", "USER", "TERM", "TERMINFO",
)

spec = importlib.util.spec_from_file_location("bias_prepare", PREPARE_SCRIPT)
assert spec and spec.loader
prepare = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prepare
spec.loader.exec_module(prepare)


def oracle_gate_passes(path: Path = GATE_PATH) -> bool:
    try:
        gate = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return gate.get("status") == "accepted" and all(
        check.get("status") == "accepted" for check in gate.get("checks", [])
    )


def select_smoke_schedule(schedule: list[dict], samples_per_cell: int) -> list[dict]:
    if samples_per_cell < 1:
        raise ValueError("samples_per_cell must be >= 1")

    selected: list[dict] = []
    counts: dict[tuple[str, str], int] = {}
    for item in schedule:
        key = (item["experiment"], item["tool_id"])
        if counts.get(key, 0) >= samples_per_cell:
            continue
        copy = dict(item)
        copy["scheduled_ordinal"] = item["ordinal"]
        copy["ordinal"] = len(selected) + 1
        selected.append(copy)
        counts[key] = counts.get(key, 0) + 1
    return selected


def build_authoring_plan(
    manifest: dict,
    output_dir: Path,
    *,
    smoke: bool = False,
    smoke_samples_per_cell: int = 1,
) -> dict:
    schedule = prepare.build_schedule(manifest)
    if smoke:
        schedule = select_smoke_schedule(schedule, smoke_samples_per_cell)
    artifact_root = output_dir / "smoke" if smoke else output_dir
    return {
        "experiment_id": manifest["experiment_id"],
        "run_count": len(schedule),
        "evidence_role": "non_evidence_smoke" if smoke else "audit_evidence_candidate",
        "artifact_policy": (
            "smoke artifacts are segregated and must not be reconciled, normalized, promoted, "
            "scored, or used as S4 evidence"
            if smoke
            else "eligible for later reconciliation only after all admission gates pass"
        ),
        "raw_capture_root": str(artifact_root / "raw"),
        "normalized_artifact_root": str(artifact_root / "normalized"),
        "retry_policy": manifest["authoring"]["retry_policy"],
        "runs": schedule,
    }


def required_credential_names() -> set[str]:
    """The Doppler source-secret names the configured tool policy actually needs — nothing more."""
    return {policy["credential_env"] for policy in TOOL_POLICY.values()}


def fetch_doppler_credentials(names: set[str]) -> dict[str, str]:
    """Fetch ONLY the named credentials from Doppler. Never returns the full secret environment.

    Returns {name: value} for names that resolved to a non-empty value. Missing names are simply
    absent (the per-tool env builder fails closed when its credential is missing)."""
    try:
        res = subprocess.run(
            ["doppler", "secrets", "--project", "startd8", "--config", "dev", "--json"],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(res.stdout)
    except Exception as e:  # noqa: BLE001
        print(f"Warning: failed to fetch Doppler credentials: {e}", file=sys.stderr)
        return {}
    out: dict[str, str] = {}
    for name in names:
        v = data.get(name)
        value = v.get("computed", "") if isinstance(v, dict) else ("" if v is None else str(v))
        if value:
            out[name] = value
    return out


def build_tool_env(tool_id: str, credentials: dict[str, str]) -> tuple[dict[str, str], dict]:
    """Scrubbed environment for ONE tool: minimal non-secret base allow-list + ONLY this tool's
    credential (injected under its declared names) + non-secret extras. Returns (env, exposure)
    where ``exposure`` records the env var NAMES (never values) for run metadata.

    Fails closed: raises if the tool's credential is unavailable, so no run proceeds credential-less.
    Guarantees no other vendor's key and no unrelated ambient/Doppler secret reaches the child."""
    policy = TOOL_POLICY[tool_id]
    env = {k: os.environ[k] for k in _BASE_ENV_ALLOWLIST if k in os.environ}
    credential = credentials.get(policy["credential_env"])
    if not credential:
        raise RuntimeError(
            f"missing credential {policy['credential_env']} for {policy['vendor']} ({tool_id})")
    for name in policy["inject_as"]:
        env[name] = credential
    env.update(policy["extra_env"])
    exposure = {
        "credential_source": policy["credential_env"],
        "secret_env_names": list(policy["inject_as"]),
        "nonsecret_extra_env_names": sorted(policy["extra_env"].keys()),
        "base_env_names": sorted(k for k in _BASE_ENV_ALLOWLIST if k in env),
    }
    return env, exposure


def build_tool_command(tool_id: str, executable_path: str) -> list[str]:
    """Concrete argv for a tool from the declarative policy (single source of truth)."""
    return [executable_path, *TOOL_POLICY[tool_id]["argv"]]


def record_attempt(run_capture_dir: Path, attempt: int, *, prompt_text: str, stdout: str,
                   stderr: str, workspace: Path, attempt_meta: dict) -> Path:
    """Write an IMMUTABLE per-attempt record under ``attempts/attempt_NN/`` (R-Phase1-4).

    Each attempt is written exactly once and never overwritten: the dir is created with
    ``exist_ok=False`` so a reused ordinal raises rather than clobbering attempt one's prompt, logs,
    artifacts, or metadata. Execution byproducts (__pycache__/*.pyc/.pytest_cache) are excluded.
    Returns the attempt directory."""
    attempt_dir = run_capture_dir / "attempts" / f"attempt_{attempt:02d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    (attempt_dir / "rendered_prompt.md").write_text(prompt_text, encoding="utf-8")
    (attempt_dir / "stdout.log").write_text(stdout, encoding="utf-8")
    (attempt_dir / "stderr.log").write_text(stderr, encoding="utf-8")
    shutil.copytree(workspace, attempt_dir / "workspace",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    (attempt_dir / "attempt_metadata.json").write_text(
        json.dumps(attempt_meta, indent=2) + "\n", encoding="utf-8")
    return attempt_dir


def command_policy_metadata(tool_id: str, executable_path: str,
                            executable_version: str | None) -> dict:
    """Declarative, versioned command record for run metadata — names/flags only, no secret values."""
    policy = TOOL_POLICY[tool_id]
    return {
        "tool_policy_version": TOOL_POLICY_VERSION,
        "tool_id": tool_id,
        "vendor": policy["vendor"],
        "executable_path": executable_path,
        "executable_version": executable_version or "unknown",
        "argv_flags": list(policy["argv"]),
        "flag_rationale": policy["flag_rationale"],
        "credential_source": policy["credential_env"],
        "exposed_secret_env_names": list(policy["inject_as"]),
        "nonsecret_extra_env_names": sorted(policy["extra_env"].keys()),
    }


def render_prompt(
    repo: Path,
    experiment: str,
    tool_id: str,
    author_vendor: str,
    sample_index: int,
    ordinal: int,
    run_id: str,
    working_directory: Path,
    clean_workspace: Path,
    executable_path: str | None,
    executable_version: str | None
) -> str:
    template_name = "suite-author.v0.1.md" if experiment == "suite_author" else "spec-author.v0.1.md"
    template_path = repo / f"docs/design/benchmark-bias-audit/bias_audit_openai/prompts/{template_name}"
    template_text = template_path.read_text(encoding="utf-8")

    tool_name = TOOL_POLICY[tool_id]["tool_name"]
    binary_path = executable_path or f"/usr/local/bin/{tool_name}"
    # Single source of truth: render the same flags the policy will actually launch with.
    flags = " ".join(TOOL_POLICY[tool_id]["argv"])

    if experiment == "spec_author":
        source_inputs = "inputs/neutral_brief.md, inputs/s2_scope_decisions.md, self-manifest.schema.json"
        extra_metadata = "  - isolation_note: This spec-author run intentionally does not include prior proto-collection output."
    else:
        source_inputs = "inputs/neutral_brief.md, inputs/s2_scope_decisions.md, inputs/canonical_spec.md, inputs/canonical_pricing.proto, inputs/canonicalization_decisions.md, self-manifest.schema.json"
        extra_metadata = ""

    run_metadata = f"""- run_id: {run_id}
- author_vendor: {author_vendor}
- authoring_surface: {tool_name}_cli
- model_id: {tool_id}-{executable_version or 'unknown'}
- prompt_template_version: {template_name.replace('.md', '')}
- artifact_type: {"suite" if experiment == "suite_author" else "spec"}
- working_directory: current working directory
- clean_workspace: current working directory, freshly provisioned for this run
- {tool_name}_binary: {binary_path}
- {tool_name}_flags: {flags}
- source_inputs: {source_inputs}"""
    if extra_metadata:
        run_metadata += "\n" + extra_metadata

    brief_path = repo / "docs/design/benchmark-bias-audit/bias_audit_openai/brief/pricing-task-brief.md"
    neutral_brief_content = brief_path.read_text(encoding="utf-8")

    scope_path = repo / "docs/design/benchmark-bias-audit/bias_audit_openai/s2_scope_decisions.md"
    s2_scope_content = scope_path.read_text(encoding="utf-8")

    if experiment == "spec_author":
        additional_spec_instructions = """

Additional run instructions:

- Author the prose implementation specification only.
- Use only the neutral brief and S2 primary pilot scope decisions embedded in this prompt.
- Do not read or rely on any proto-collection output, prior S2 generated files, parent directories, or the startd8 repository.
- Treat tax handling and discount cap behavior as non-goals for the primary pilot. Do not require tax calculation, tax fields, cap validation, or cap calculation in the spec.
- Preserve source-grounded concepts only when they remain in scope after the S2 decisions.
- Keep exact decimal behavior implementable. Do not use binary floating point semantics.
- If you include a secondary contract sketch, keep it clearly marked and subordinate to the prose spec.
- Write the output files in the current working directory.
- Do not use plugins, skills, MCP tools, memories, or external documentation.
- Do not copy forbidden names except inside a clearly marked anti-leakage explanation if absolutely necessary. Prefer avoiding them entirely."""
        experiment_instructions = s2_scope_content + additional_spec_instructions
        
        allowed_dependencies = """- No implementation runtime dependencies.
- Specification may mention Protocol Buffers/gRPC only as the benchmark interface style.
- Exact decimal arithmetic must be possible with a language-appropriate decimal library in later implementation, but do not choose a runtime here."""
        
        forbidden_inputs = """- Current pricing seed proto, requirements text, suite, expected outputs, and generated seed artifacts.
- Prior S2 proto-collection outputs.
- Repository-level CLAUDE.md, AGENTS.md, user config, tools, memories, and rules.
- Current pricing seed positive contract names listed in the neutral brief anti-leakage section.
- Vendor-specific authoring mechanics or model-specific preferences."""

    else:
        canon_decisions_path = repo / "docs/design/benchmark-bias-audit/bias_audit_openai/canonical/canonicalization_decisions.md"
        canon_decisions = canon_decisions_path.read_text(encoding="utf-8")
        
        proto_path = repo / "docs/design/benchmark-bias-audit/bias_audit_openai/canonical/pricing.proto"
        proto_content = proto_path.read_text(encoding="utf-8")
        
        spec_path = repo / "docs/design/benchmark-bias-audit/bias_audit_openai/canonical/spec.md"
        spec_content = spec_path.read_text(encoding="utf-8")
        
        experiment_instructions = f"""{canon_decisions}

## Canonical Proto

```proto
{proto_content}
```

## Canonical Specification

{spec_content}

Additional run instructions:

- Author only the behavioral suite artifacts: suite.py, suite_manifest.json, and authoring_manifest.json.
- Treat the canonical proto and canonical specification above as authoritative.
- Do not alter, reinterpret, extend, or repair the canonical semantics.
- Do not include tax calculation or discount cap behavior.
- Target behavioral tests that can be adapted to a Python gRPC pytest-style harness later, but do not depend on a live server being available in this authoring run.
- Include enough structured case data and expected outcomes in suite.py for later harness adaptation.
- Localize each test to the specific behavior it detects.
- Do not read parent directories or the startd8 repository.
- Do not use plugins, skills, MCP tools, memories, external documentation, or prior non-canonical generated artifacts.
- Do not copy forbidden current-seed names."""

        allowed_dependencies = """- Python standard library only for authored suite data and helper calculations.
- pytest-style test functions may be used, but do not require importing pytest at module import time.
- Use decimal.Decimal for expected-value calculations.
- No network, database, generated gRPC stubs, or third-party packages."""

        forbidden_inputs = """- Current pricing seed proto, requirements text, suite, expected outputs, and generated seed artifacts.
- Non-canonical S2 proto/spec run outputs except the canonical artifacts embedded in this prompt.
- Repository-level CLAUDE.md, AGENTS.md, user config, tools, memories, and rules.
- Current pricing seed positive contract names listed in the neutral brief anti-leakage section.
- Vendor-specific authoring mechanics or model-specific preferences."""

    text = template_text
    text = text.replace("{{RUN_METADATA}}", run_metadata)
    text = text.replace("{{NEUTRAL_BRIEF}}", neutral_brief_content)
    text = text.replace("{{EXPERIMENT_INSTRUCTIONS}}", experiment_instructions)
    text = text.replace("{{ALLOWED_DEPENDENCIES}}", allowed_dependencies)
    text = text.replace("{{FORBIDDEN_INPUTS}}", forbidden_inputs)
    
    return text


def provision_workspace(repo: Path, clean_workspace: Path, experiment: str) -> None:
    if clean_workspace.exists():
        shutil.rmtree(clean_workspace)
    clean_workspace.mkdir(parents=True, exist_ok=True)
    inputs_dir = clean_workspace / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    
    shutil.copy2(
        repo / "docs/design/benchmark-bias-audit/bias_audit_openai/prompts/self-manifest.schema.json",
        clean_workspace / "self-manifest.schema.json"
    )
    
    shutil.copy2(
        repo / "docs/design/benchmark-bias-audit/bias_audit_openai/brief/pricing-task-brief.md",
        inputs_dir / "neutral_brief.md"
    )
    shutil.copy2(
        repo / "docs/design/benchmark-bias-audit/bias_audit_openai/s2_scope_decisions.md",
        inputs_dir / "s2_scope_decisions.md"
    )
    
    if experiment == "suite_author":
        shutil.copy2(
            repo / "docs/design/benchmark-bias-audit/bias_audit_openai/canonical/spec.md",
            inputs_dir / "canonical_spec.md"
        )
        shutil.copy2(
            repo / "docs/design/benchmark-bias-audit/bias_audit_openai/canonical/pricing.proto",
            inputs_dir / "canonical_pricing.proto"
        )
        shutil.copy2(
            repo / "docs/design/benchmark-bias-audit/bias_audit_openai/canonical/canonicalization_decisions.md",
            inputs_dir / "canonicalization_decisions.md"
        )


def execute_run(
    tool_id: str,
    executable_path: str,
    prompt_text: str,
    working_directory: Path,
    env: dict[str, str],
    *,
    timeout_s: float | None = None,
) -> tuple[int, str, str]:
    if tool_id not in TOOL_POLICY:
        raise ValueError(f"unknown tool_id: {tool_id}")
    cmd = build_tool_command(tool_id, executable_path)
    try:
        res = subprocess.run(
            cmd,
            input=prompt_text,
            capture_output=True,
            text=True,
            cwd=working_directory,
            env=env,
            timeout=timeout_s,
        )
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        detail = f"timed out after {timeout_s:g} seconds" if timeout_s is not None else "timed out"
        return 124, stdout, (stderr + ("\n" if stderr else "") + detail)
    except Exception as e:  # noqa: BLE001
        return -1, "", str(e)


def failure_output_preview(stdout: str, stderr: str, *, limit: int = 200) -> str:
    """Return a short diagnostic for failed child processes.

    Some CLIs report provider/account failures on stdout rather than stderr, so stderr-only
    previews hide the actionable reason.
    """
    output = stderr.strip() or stdout.strip()
    return output[:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=prepare.DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v1"))
    parser.add_argument("--run", action="store_true", help="Require every preflight gate before invoking any authoring tool.")
    parser.add_argument("--smoke", action="store_true",
                        help="Run a bounded non-evidence smoke subset. Artifacts are segregated under smoke/ and must not be promoted.")
    parser.add_argument("--smoke-samples-per-cell", type=int, default=1,
                        help="Number of samples per experiment/tool cell in --smoke mode (default: 1).")
    parser.add_argument("--smoke-timeout-seconds", type=float, default=DEFAULT_SMOKE_TIMEOUT_SECONDS,
                        help="Per-run timeout in --smoke mode (default: 600).")
    parser.add_argument("--run-timeout-seconds", type=float, default=None,
                        help="Optional per-run timeout in full --run mode. Unbounded when omitted.")
    args = parser.parse_args(argv)
    if args.run and args.smoke:
        parser.error("--run and --smoke are mutually exclusive")
    if args.smoke and args.smoke_timeout_seconds <= 0:
        parser.error("--smoke-timeout-seconds must be > 0")
    if args.run_timeout_seconds is not None and args.run_timeout_seconds <= 0:
        parser.error("--run-timeout-seconds must be > 0")
    try:
        manifest = prepare._load_manifest(args.manifest)
        prepare.validate_manifest(manifest)
        prepare._assert_clean_workspace(args.output_dir, manifest["execution_controls"])
    except prepare.ManifestError as exc:
        print(f"authoring blocked: {exc}", file=sys.stderr)
        return 2

    tools = prepare.preflight_tools(manifest)
    unavailable = [tool["tool_id"] for tool in tools if not tool["available"]]
    execute_authoring = args.run or args.smoke
    if execute_authoring and unavailable:
        print(f"authoring blocked: required authoring tools unavailable: {', '.join(unavailable)}", file=sys.stderr)
        return 2
    if execute_authoring and not oracle_gate_passes():
        print("authoring blocked: independent oracle/mutant validation gate is not accepted", file=sys.stderr)
        return 2

    try:
        plan = build_authoring_plan(
            manifest,
            args.output_dir,
            smoke=args.smoke,
            smoke_samples_per_cell=args.smoke_samples_per_cell,
        )
    except ValueError as exc:
        print(f"authoring blocked: {exc}", file=sys.stderr)
        return 2
    mode = "dry_run" if not execute_authoring else ("non_evidence_smoke" if args.smoke else "gated")
    print(json.dumps({"mode": mode, "tools": tools,
                      "plan": plan}, indent=2))
    
    if not execute_authoring:
        return 0

    # Fetch ONLY the per-tool credentials the policy needs — never the full Doppler environment.
    # Each child later receives a scrubbed env carrying just its own vendor credential (build_tool_env).
    needed = required_credential_names()
    print(f"Retrieving {len(needed)} per-tool credential(s) from Doppler...")
    credentials = fetch_doppler_credentials(needed)
    missing_creds = sorted(needed - set(credentials))
    if missing_creds:
        print(f"authoring blocked: missing required credential(s): {', '.join(missing_creds)}",
              file=sys.stderr)
        return 2

    raw_root = Path(plan["raw_capture_root"])
    raw_root.mkdir(parents=True, exist_ok=True)
    
    executable_by_id = {}
    version_by_id = {}
    for t in tools:
        executable_by_id[t["tool_id"]] = t["path"]
        version_by_id[t["tool_id"]] = t["version"]

    runs = plan["runs"]
    total_runs = len(runs)
    retry_policy = plan["retry_policy"]
    max_retries = 0 if args.smoke else retry_policy.get("max_automated_retries", 1)
    timeout_s = args.smoke_timeout_seconds if args.smoke else args.run_timeout_seconds

    if args.smoke:
        print(
            f"Starting NON-EVIDENCE smoke execution of {total_runs} randomized authoring runs "
            f"(timeout {timeout_s:g}s per run)..."
        )
    else:
        print(f"Starting execution of {total_runs} randomized authoring runs...")
    for item in runs:
        ordinal = item["ordinal"]
        experiment = item["experiment"]
        tool_id = item["tool_id"]
        author_vendor = item["author_vendor"]
        sample_index = item["sample_index"]
        
        run_id = (
            f"{manifest['experiment_id']}-smoke-run-{ordinal:02d}"
            if args.smoke
            else f"{manifest['experiment_id']}-run-{ordinal:02d}"
        )
        run_dir_prefix = "smoke_run" if args.smoke else "run"
        run_dir_name = f"{run_dir_prefix}_{ordinal:02d}_{experiment}_{tool_id}_sample_{sample_index}"
        run_capture_dir = raw_root / run_dir_name
        workspace_prefix = "smoke" if args.smoke else "run"
        run_workspace = Path(f"/private/tmp/startd8-cross-tool-bias/workspaces/{workspace_prefix}_{ordinal:02d}")
        
        print(f"[{ordinal}/{total_runs}] Running {experiment} using {tool_id} (sample {sample_index})...")
        
        executable_path = executable_by_id[tool_id]
        executable_version = version_by_id[tool_id]
        
        # Render the prompt
        prompt_text = render_prompt(
            repo=REPO,
            experiment=experiment,
            tool_id=tool_id,
            author_vendor=author_vendor,
            sample_index=sample_index,
            ordinal=ordinal,
            run_id=run_id,
            working_directory=run_workspace,
            clean_workspace=run_workspace,
            executable_path=executable_path,
            executable_version=executable_version
        )
        
        # Scrubbed env carrying ONLY this tool's vendor credential (fail-closed if absent).
        tool_env, env_exposure = build_tool_env(tool_id, credentials)
        command_policy = command_policy_metadata(tool_id, executable_path, executable_version)

        success = False
        attempts = 0
        attempt_records: list[dict] = []
        while not success and attempts <= max_retries:
            attempts += 1
            if attempts > 1:
                print(f"  Attempt {attempts} (retry) for [{ordinal}/{total_runs}]...")

            # Clean and provision the isolated per-run workspace (recreated each attempt).
            provision_workspace(REPO, run_workspace, experiment)

            start_time = datetime.now(timezone.utc).isoformat()
            code, stdout, stderr = execute_run(
                tool_id,
                executable_path,
                prompt_text,
                run_workspace,
                tool_env,
                timeout_s=timeout_s,
            )
            end_time = datetime.now(timezone.utc).isoformat()
            timed_out = code == 124

            if experiment == "spec_author":
                required_files = ["spec.md", "authoring_manifest.json"]
            else:
                required_files = ["suite.py", "suite_manifest.json", "authoring_manifest.json"]
            missing_files = [f for f in required_files if not (run_workspace / f).is_file()]

            if code == 0 and not missing_files:
                success = True
                status_str = "success"
            else:
                status_str = "failed"
                print(f"  Failed: exit_code={code}, missing_files={missing_files}")
                if code != 0:
                    preview = failure_output_preview(stdout, stderr)
                    if preview:
                        print(f"  Output: {preview}")

            # IMMUTABLE per-attempt record (R-Phase1-4): written once, never overwritten.
            attempt_meta = {
                "attempt": attempts, "status": status_str, "exit_code": code,
                "missing_files": missing_files,
                "timed_out": timed_out,
                "timeout_seconds": timeout_s,
                "started_at_utc": start_time, "finished_at_utc": end_time,
            }
            record_attempt(run_capture_dir, attempts, prompt_text=prompt_text, stdout=stdout,
                           stderr=stderr, workspace=run_workspace, attempt_meta=attempt_meta)
            attempt_records.append(attempt_meta)

            if run_workspace.exists():
                shutil.rmtree(run_workspace)

        # Canonical top-level artifacts come from the FINAL attempt only (the immutable per-attempt
        # records above retain every earlier attempt). Promote that attempt's files to the run dir.
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
            "run_id": run_id, "experiment": experiment, "tool_id": tool_id,
            "author_vendor": author_vendor, "sample_index": sample_index, "ordinal": ordinal,
            "scheduled_ordinal": item.get("scheduled_ordinal", ordinal),
            "mode": "non_evidence_smoke" if args.smoke else "gated",
            "evidence_role": "non_evidence_smoke" if args.smoke else "audit_evidence_candidate",
            "promote_to_evidence": not args.smoke,
            "status": "success" if success else "failed",
            "exit_code": attempt_records[-1]["exit_code"],
            "missing_files": attempt_records[-1]["missing_files"],
            "timed_out": attempt_records[-1]["timed_out"],
            "timeout_seconds": timeout_s,
            "started_at_utc": attempt_records[0]["started_at_utc"],
            "finished_at_utc": attempt_records[-1]["finished_at_utc"],
            "attempts": attempts,
            "attempt_records": attempt_records,
            "command_policy": command_policy,   # declarative, versioned — names/flags, no secrets
            "env_exposure": env_exposure,       # env var NAMES only — no secret values
        }
        (run_capture_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print("All runs finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
