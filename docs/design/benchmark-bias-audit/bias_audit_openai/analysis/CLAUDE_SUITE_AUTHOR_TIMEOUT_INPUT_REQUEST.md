# Claude Input Request: Suite-Author Smoke Failure

## Purpose

We need Claude's input on a cross-tool benchmark-bias-audit smoke failure affecting only the Claude suite-author case.

This request is diagnostic only. Do not treat any artifacts from this exchange as audit evidence, benchmark evidence, or accepted authoring output.

## Context

The project is validating a cross-tool authoring pipeline for the pricing benchmark bias audit. The objective is to avoid single-vendor bias by requiring OpenAI/Codex, Google/Gemini, and Anthropic/Claude authoring surfaces to execute through the same controller and artifact contract before any real evidence batch is run.

The current smoke mode is explicitly non-evidence:

- Smoke artifacts are segregated.
- Smoke artifacts must not be reconciled, normalized, promoted, scored, or used as S4 evidence.
- The real 30-run evidence batch remains blocked until smoke behavior is understood and accepted.

## Current observed behavior

A post-merge non-evidence smoke run completed at the controller level with timeout support enabled.

Result:

- 5 of 6 smoke cases succeeded.
- The failing case was:
  - experiment: `suite_author`
  - tool: `claude-code`
  - vendor: `anthropic`
  - sample: `1`

Failure from the 300-second post-merge smoke:

- exit code: `124`
- timed out: `true`
- missing files:
  - `suite.py`
  - `suite_manifest.json`
  - `authoring_manifest.json`
- stdout: empty
- stderr: `timed out after 300 seconds`

All other smoke cases succeeded, including both Gemini cases and both Codex cases.

## Important follow-up diagnostics

We then made a small prompt-surface hardening change:

- The rendered prompt no longer embeds ephemeral absolute workspace paths.
- The rendered prompt now says:
  - `working_directory: current working directory`
  - `clean_workspace: current working directory, freshly provisioned for this run`
- Both authoring templates now say to write output files in the current working directory.

A targeted Claude suite-author probe using the hardened prompt still failed.

With a 300-second timeout:

- exit code: `124`
- timed out: `true`
- stdout: empty
- stderr: `timed out after 300 seconds`
- no authored output files were created.

With a 600-second timeout:

- exit code: `1`
- timed out: `false`
- stdout: `Credit balance is too low`
- stderr: empty
- no authored output files were created.

We also ran a minimal Claude write probe using the same headless policy and isolated workspace. That minimal probe succeeded quickly and wrote all expected files.

Minimal write probe result:

- exit code: `0`
- `suite.py`: written
- `suite_manifest.json`: written
- `authoring_manifest.json`: written

This means Claude Code can write files headlessly in the isolated workspace. The remaining blocker appears to be provider/account capacity or the full suite-author prompt requiring enough Anthropic credits/time to complete.

## Relevant controller details

Claude is invoked through the authoring controller as:

```text
claude --print --permission-mode bypassPermissions
```

The child process receives a scrubbed environment:

- only the Anthropic credential names required by policy are exposed;
- no OpenAI or Google credentials are exposed to the Claude child process;
- no secret values are recorded in metadata.

The suite-author output contract requires exactly these files in the current working directory:

- `suite.py`
- `suite_manifest.json`
- `authoring_manifest.json`

The authored suite must be bridge-executable and expose an injectable adapter seam such as:

- `bind_invoker(fn)`
- `configure(adapter)`
- `run_all(call=None)`
- `run_case(case_name, call=None)`
- `run_ok_cases(call=None)`
- `run_invalid_cases(call=None)`

## Artifact paths

These paths are local diagnostic artifacts only.

Post-merge smoke failure:

```text
/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-postmerge-smoke/smoke/raw/smoke_run_02_suite_author_claude-code_sample_1
```

Targeted Claude suite-author probe:

```text
/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-claude-suite-prompt-fix-probe/smoke/raw/smoke_run_02_suite_author_claude-code_sample_1
```

Current code branch with the prompt hardening and stdout fallback diagnostics:

```text
codex/authoring-prompt-current-workdir
```

Current worktree:

```text
/private/tmp/startd8-sdk-postmerge-smoke
```

## Questions for Claude

Please review the above and provide diagnostic input on these questions:

1. Does `Credit balance is too low` conclusively indicate Anthropic account/billing/credit exhaustion for the full suite-author call?

2. Is there any Claude Code CLI behavior where a large `--print` prompt could appear to hang with no stdout/stderr until the provider eventually returns a credit or capacity error?

3. Given that the minimal write probe succeeds, is it reasonable to conclude that filesystem permissions and headless write mode are not the root cause?

4. Are the flags below appropriate for this non-interactive isolated authoring run?

   ```text
   claude --print --permission-mode bypassPermissions
   ```

5. Is there a narrower or more reliable non-interactive Claude Code invocation mode we should use for a file-authoring benchmark task?

6. Should the controller classify stdout-only messages like `Credit balance is too low` as provider/account failures rather than generic authoring failures?

7. After Anthropic credits are restored, should we rerun only the targeted Claude suite-author probe first, or rerun the full 6-case non-evidence smoke immediately?

## Requested answer format

Please answer with:

1. Root-cause assessment.
2. Whether any controller or prompt changes are still recommended.
3. Whether the current smoke gate should remain blocked.
4. The exact next command or validation step you recommend after Anthropic credits are restored.

Do not generate replacement benchmark artifacts. Do not write `suite.py`, `suite_manifest.json`, or `authoring_manifest.json` as part of this diagnostic response.
