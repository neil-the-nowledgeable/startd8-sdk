# Gemini CLI Next Steps

**Purpose:** unblock the Google author-vendor arm of the frozen pricing cross-tool experiment without
weakening its clean-workspace, provenance, or three-vendor comparison controls.

## Current State

The clean preflight on 2026-06-20 found:

- Claude Code `2.1.170`: available.
- Codex CLI `0.141.0`: available.
- Gemini CLI: not installed or not on `PATH`.

The experiment controller correctly refuses a two-vendor run. The three authoring arms are a required
control, not an optional convenience.

## Install

Use the official npm package:

```bash
npm install -g @google/gemini-cli
gemini --version
```

Confirm that the executable resolves from the same shell that will run the clean-workspace audit:

```bash
command -v gemini
gemini --version
```

Do not substitute a manual IDE workflow for this automated arm. The audit requires a headless-capable
CLI with version capture and deterministic scheduling.

## Authenticate

Choose one method and record only the method, account class, CLI version, and timestamp in the audit
metadata. Never write credentials into the repository, rendered prompts, event logs, or raw artifacts.

1. **Interactive local sign-in:** start `gemini` and choose Google sign-in. This is appropriate when a
   browser is available and the account/quota policy permits it.
2. **Headless API-key run:** inject `GEMINI_API_KEY` from the approved secret manager only for the
   subprocess that invokes Gemini CLI. Do not export it into a shell profile or save it in an audit
   manifest.
3. **Vertex AI:** for organization accounts, configure the required Google Cloud project and IAM/API
   access before starting Gemini CLI. Record the project identifier as redacted execution metadata if
   policy permits.

Official references: [Gemini CLI quickstart](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/index.md)
and [authentication setup](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/authentication.mdx).

## Audit Readiness Check

From the isolated experiment worktree, run:

```bash
python3 scripts/prepare_cross_tool_bias_experiment.py \
  --preflight-tools \
  --output-dir /private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v1

python3 scripts/run_cross_tool_bias_authoring.py \
  --output-dir /private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v1
```

The first command must report all three authoring tools as available. The second must emit the
30-run dry-run schedule. It remains blocked until the independent oracle/mutant gate is accepted.

## Clean Workspace Rule

Run Gemini only from the isolated workspace under `/private/tmp`, never from the repository root or a
child directory. The preparation guard rejects ancestor instruction files named `CLAUDE.md`,
`AGENTS.md`, or `GEMINI.md` so no tool receives ambient project guidance.

## Before Authoring Is Enabled

- Keep Gemini CLI, Claude Code, and Codex CLI versions fixed for all N=5 samples per tool.
- Capture raw output before mechanical normalization; semantic repair remains forbidden.
- Complete the oracle provenance, evidence mapping, reviewer sign-off, and mutant adequacy checks.
- Review and approve the external command templates before changing the controller from dry-run to
  live authoring.
