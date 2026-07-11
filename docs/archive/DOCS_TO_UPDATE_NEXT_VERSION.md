# Docs to Update (Next Version)

**Repo:** `startd8-sdk-project`  
**Generated:** 2025-12-17  
**Current package version (pyproject):** 0.4.0

This is a planning list of documentation artifacts that **need updates** (broken links, incorrect commands/APIs, stale version headers), to fix in a subsequent release.

---

## Highest priority (broken/misleading today)

- **`INSTALL.md`**
  - **Issue:** Broken links to `../QUICKSTART.md` and `../SETUP_GUIDE.md` (files do not exist).
  - **Fix:** Replace with valid links (likely `docs/QUICK_START_v1.md`, `README.md`, and/or a new consolidated install page) or remove the “Read the docs” link section.

- **`docs/FEATURE_WORKFLOW_GUIDE.md`**
  - **Issue:** Uses `startd8` (no subcommand) to launch the TUI.
  - **Fix:** Change to `startd8 tui`.

- **`job_files/flower-defense-v2/README.md`**
  - **Issue:** Uses `startd8` (no subcommand) and contains an unrelated absolute path to another repo.
  - **Fix:** Change to `startd8 tui` and either (a) remove absolute-path content, or (b) clearly label as internal/example-only.

- **`CHANGELOG.md`**
  - **Issue:** Placeholder date (`2024-12-XX`) and appears to stop at `0.2.0` while the project is `0.4.0`.
  - **Fix:** Update with real release dates and entries for `0.3.0` / `0.4.0` (or replace with a single canonical changelog).

- **`CHANGELOG_PIPX.md`**
  - **Issue:** References `QUICKSTART.md` / `SETUP_GUIDE.md` which don’t exist.
  - **Fix:** Update references to current doc locations or remove this “meta-changelog” if redundant.

---

## API/CLI examples that don’t match current code

- **`README.md`**
  - **Issue:** `WorkflowTemplates.design_review_chain(...)` example uses parameter names that don’t match implementation (the implementation expects `drafter_agent`, `reviewer_agent`, `final_reviewer_agent`).
  - **Fix:** Update example call signature to match `src/startd8/orchestration.py`.

- **`docs/QUICK_START_v1.md`**
  - **Issue:** Same `WorkflowTemplates.design_review_chain(...)` keyword mismatch.
  - **Fix:** Update call signature.

- **`docs/PIPELINE_WORKFLOWS_v1.md`**
  - **Issue:** Keyword args don’t match code for:
    - `WorkflowTemplates.planner_implementer(...)` (expects `planner_agent`, `implementer_agent`)
    - `WorkflowTemplates.code_review(...)` (expects `reviewer_agent`, `improver_agent`)
    - `WorkflowTemplates.design_review_chain(...)` (expects `drafter_agent`, `reviewer_agent`, `final_reviewer_agent`)
  - **Fix:** Update all examples to the real signature.

- **`docs/API_REFERENCE_v1.md`**
  - **Issue:** Documents `BaseAgent.generate()` as the abstract method, but code makes `agenerate()` abstract and `generate()` a sync wrapper.
  - **Fix:** Update the API reference to reflect `BaseAgent.agenerate()` as the primary API and describe `generate()` as a wrapper.

---

## Version header drift (docs say 0.2.0 but package is 0.4.0)

These should be reviewed and updated so their “Version” header matches the shipped package and the content is accurate:

- **`docs/TUI_USER_GUIDE_v1.md`** (header shows 0.2.0)
- **`docs/SDK_ARCHITECTURE_v1.md`** (header shows 0.2.0)
- **`docs/AGENT_CONFIGURATION_GUIDE_v1.md`** (header shows 0.2.0)
- **`docs/PIPELINE_WORKFLOWS_v1.md`** (header shows 0.2.0)
- **`docs/CHANGELOG_v1.md`** (treats 0.2.0 as current; lists later versions as “planned”)

---

## Broken links to missing files

- **`examples/ASYNC_FEATURES.md`**
  - **Issue:** Links to `../startd8-architecture-review.md` (missing).
  - **Fix:** Update to an existing architecture doc (likely `docs/SDK_ARCHITECTURE_v1.md`) or remove.

- **`design/SKILL_AGENT_CORE_DESIGN.md`**
  - **Issue:** Links to `../INDEX_SKILL_INTEGRATION_PLANS_v4.md` (missing).
  - **Fix:** Update link or remove.

---

## Redundancy / “internal vs public” cleanup (recommended)

The repo contains many root-level “phase/session/issue/investigation” markdown files (e.g., `PHASE_*`, `SESSION_SUMMARY_*`, `ISSUE_*`, `IMPLEMENTATION_*`, `WEEK*_COMPLETION_SUMMARY.md`). They’re useful history but will drift.

Suggested action for next version:

- **Decide scope**: either (a) exclude from user-facing docs, or (b) move under an `internal/` or `notes/` area and label them clearly.
- **Keep one canonical doc set**: prefer `README.md` + `INSTALL.md` + `docs/*` as the maintained user documentation.

---

## Quick “next release” fix checklist

- Fix broken links in `INSTALL.md` and any other docs referencing missing files.
- Normalize TUI launch instructions to `startd8 tui`.
- Update `WorkflowTemplates.*` examples to match the real function signatures.
- Update `BaseAgent` API reference to reflect `agenerate()`.
- Decide a single canonical changelog and remove/merge redundant changelog docs.
- Refresh all `docs/*` headers that still say `0.2.0`.

