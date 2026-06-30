# Prompt/Template Gate Review Guide

**Date:** 2026-06-30
**Status:** Review guide for the S4 bridge-executable prompt/template gate
**Audience:** Non-Claude reviewers evaluating the prompt/template change before acceptance
**Scope:** `suite-author.v0.1.md` and prompt-package rules only

This guide explains how to decide whether the prompt/template gate is acceptable for the audit
objective: future OpenAI and Gemini suite-authoring batches should emit suites that the reviewed S4
executor bridge can run without hand-editing generated artifacts.

This is not a review of generated suites, oracle semantics, mutant adequacy, or model bias findings.
It is a narrow admission review for the prompt instructions that will shape future generated suites.

---

## Objective being reviewed

Accept the prompt/template gate only if it makes future suite outputs bridge-executable while preserving
the audit methodology:

1. OpenAI and Gemini authors receive equivalent task instructions.
2. The suite authoring prompt remains vendor-neutral.
3. The generated `suite.py` is expected to expose an implementation-injection seam.
4. The generated `suite_manifest.json` is expected to describe that seam.
5. The prompt does not tell authors to change the canonical spec, proto, oracle, harness, or runtime.
6. The gate helps future S4 runs avoid the prior failure mode where accepted OpenAI/Gemini suites could
   not be executed by the reviewed bridge without manual adaptation.

---

## Files to review

Review these files in the PR:

- `docs/design/benchmark-bias-audit/bias_audit_openai/prompts/suite-author.v0.1.md`
- `docs/design/benchmark-bias-audit/bias_audit_openai/prompts/README.md`

Optional context:

- `docs/design/benchmark-bias-audit/bias_audit_openai/prompts/self-manifest.schema.json`
- `docs/design/benchmark-bias-audit/bias_audit_openai/analysis/S4_POSTMERGE_ANALYSIS_REPORT.md`
- `scripts/run_cross_tool_bias_s4.py`

The optional context is useful for understanding why the bridge contract is needed, but the decision
should be based on the prompt/template gate itself.

---

## Review sequence

### Step 1 — Confirm scope is small and prompt-only

From the branch under review:

```bash
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Acceptable scope:

- prompt template text
- prompt package README/review guidance
- no runtime bridge behavior changes
- no oracle behavior changes
- no generated suite edits
- no authoring output rewrites

Block the gate if the PR mixes unrelated runtime, oracle, reconciliation, or generated-output changes
with the prompt/template change.

### Step 2 — Check vendor neutrality

Read the changed prompt text and answer:

- Does the bridge contract apply identically to OpenAI, Gemini, Codex, Claude, or any future authoring
  tool?
- Are vendor names used only to explain the audit context, not to create different task requirements?
- Does the README still require rendered prompts to differ only by invocation mechanics and
  `RUN_METADATA`?
- Would a Gemini-authored suite and an OpenAI-authored suite receive the same bridge-executability
  requirements?

Accept only if the contract is vendor-neutral. Block if any vendor gets a more permissive, stricter, or
mechanically different suite contract.

### Step 3 — Check bridge executability

The prompt should require generated `suite.py` to be importable and runnable by a future isolated
bridge without hand edits.

Look for requirements covering:

- no network access required at import time;
- no live service required at import time;
- no generated stubs required at import time;
- no repo-root or external write dependency;
- an injectable implementation seam such as `bind_invoker(fn)`, `configure(adapter)`, or `run_*`
  helpers with an optional `call` argument;
- JSON-compatible request and response dictionaries at the seam;
- deterministic invalid-argument signaling;
- no hard-coded successful behavior that bypasses the injected implementation target.

Accept only if the generated suite would be expected to expose a callable seam the S4 bridge can bind
to an implementation under test.

Block if the prompt merely asks for tests but does not require an injectable target seam.

### Step 4 — Check manifest evidence

The prompt should require `suite_manifest.json` to identify the bridge contract, not just test names or
behavior IDs.

Look for required metadata covering:

- exported callable names;
- request shape;
- response shape;
- invalid-argument convention;
- suite-local exception classes, if any.

Accept only if a reviewer or intake script could inspect the manifest and determine how the bridge is
supposed to invoke the suite.

Block if the manifest contract is optional, vague, or disconnected from the exported `suite.py`
callables.

### Step 5 — Check methodology preservation

The bridge requirement must not change the benchmark semantics.

Confirm the prompt still says:

- author only the behavioral suite;
- treat the fixed spec and canonical proto as authoritative;
- do not alter the spec, proto, harness, oracle, or runtime;
- do not repair or reinterpret ambiguous behavior beyond the fixed spec;
- localize assertions to the behavior being detected;
- map tests to the FIXED/OPEN item they exercise.

Accept only if bridge executability is added as an output-shape requirement, not as permission to
change the audit semantics.

Block if the prompt encourages authors to redefine behavior, weaken assertions, or adapt the canonical
contract to fit the bridge.

### Step 6 — Check future enforceability

This prompt/template gate does not need to implement intake validation by itself, but it should create a
clear contract that a later validation PR can enforce.

Accept if a future validator could mechanically check for:

- presence of `suite_manifest.json.bridge_contract`;
- named callable exports in `suite.py`;
- recognized invalid-argument convention;
- importability without external services.

Block if the prompt language is too ambiguous for future validation to distinguish acceptable suites
from non-bridgeable suites.

---

## Acceptance criteria

Record the gate as acceptable only when all of these are true:

1. The PR is prompt/template-scoped and does not mix unrelated behavior changes.
2. OpenAI and Gemini rendered prompts would receive the same bridge requirements.
3. The suite-author template requires an injectable implementation seam.
4. The template requires JSON-compatible request/response behavior at that seam.
5. Invalid-input behavior has a deterministic convention the bridge can recognize.
6. `suite_manifest.json` must declare bridge contract metadata.
7. The canonical spec/proto/oracle/harness/runtime remain unchanged and authoritative.
8. The requirement is specific enough for a later fail-closed validator.

If any item fails, do not accept the gate. Return a blocked decision with the exact missing requirement.

---

## Non-goals

Do not require this PR to:

- regenerate OpenAI or Gemini suites;
- execute a new S4 batch;
- add intake validation code;
- change the S4 executor bridge implementation;
- alter oracle, mutant, or reconciliation gates;
- prove that future model-generated suites will be semantically correct.

Those are follow-up gates. This review is only about whether the prompt/template contract is adequate
to make future suites bridge-executable in principle.

---

## Suggested reviewer decision format

```markdown
## Prompt/Template Gate Review

Decision: ACCEPT | BLOCKED | REJECT
Reviewer:
Date:

Materials reviewed:
- suite-author.v0.1.md
- prompts/README.md
- PROMPT_TEMPLATE_GATE_REVIEW_GUIDE.md

Findings:
- Scope:
- Vendor neutrality:
- Bridge executability:
- Manifest evidence:
- Methodology preservation:
- Future enforceability:

Rationale:

Required follow-ups, if any:
```
