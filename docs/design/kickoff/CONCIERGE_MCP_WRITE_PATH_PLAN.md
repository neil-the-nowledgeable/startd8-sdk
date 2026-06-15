# Concierge Write-Path Increment — Implementation Plan

**Version:** 0.2 (Post-CRP R1 — all 10 S-suggestions accepted and folded in)
**Date:** 2026-06-12
**Status:** Draft — security-hardened, cleared to implement
**Parent requirements:** [`CONCIERGE_MCP_REQUIREMENTS.md`](CONCIERGE_MCP_REQUIREMENTS.md) v0.3
(FR-C2/C3/C7/C9/C13/C14; OQ-7 resolution)
**Builds on:** the shipped read-only core (`src/startd8/concierge/`, commit `d44c9c4c`) and CLI
parity (`src/startd8/cli_concierge.py`, commit `3834570d`), branch `feat/concierge-mcp`.

> **The increment:** add the two *write* actions — `instantiate-kickoff` and `log-friction` —
> under the OQ-7 resolution: **MCP returns previews only; the CLI is the sole writer**, running
> at the human's own filesystem privilege. The security surface (path confinement, no-clobber,
> idempotency) is the reason this increment gets a CRP pass before code.

---

## 1. Scope & Non-Scope

**In:** `instantiate-kickoff` (project the kickoff package into a consuming project) and
`log-friction` (append a structured friction item to the project's Concierge friction log).
The shared **safe-writer** chokepoint. Template packaging (FR-C7 prerequisite). CLI write
surface + MCP preview surface. Security + idempotency tests.

**Out:** `derive-contract` (separate deferred follow-on — net-new AST). Real-content generation.
Any MCP-side disk write (forbidden by OQ-7). Gate/approval recording (FR-C2).

---

## 2. Design

### Step 0 — Template packaging (FR-C7 prerequisite)

The kickoff templates live in `docs/design/kickoff/templates/` which is **not shipped in the
wheel**. Mirror the `help_content/*.yaml` precedent:

- New package dir `src/startd8/concierge_templates/` holding the kickoff package templates
  (`KICKOFF_INTRO_TEMPLATE.md`, `KICKOFF_INPUTS_EXPLAINED_TEMPLATE.md`,
  `inputs/{business-targets,observability,conventions,build-preferences}.yaml`) and the optional
  authoring trio (`REQUIREMENTS_TEMPLATE.md`, `PLAN_TEMPLATE.md`, `TEST_USERS_TEMPLATE.md`,
  `HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md`, `REQUIREMENTS_AND_PLAN_FORMAT.md`).
- Register in `pyproject.toml` `[tool.setuptools.package-data]` (`concierge_templates/**`) and
  `setup.py` `package_data` (both are kept in sync today).
- Loader reads via `importlib.resources.files("startd8.concierge_templates")` — works from a
  wheel, not just a source checkout.
- **Anti-fork:** `docs/design/kickoff/templates/` stays canonical for humans; the packaged copy
  is the shipped artifact. A test asserts the two trees are byte-identical (the FR-W14 pattern),
  so they can't silently diverge.

### Step 1 — SDK preview builders (pure; what MCP returns; FR-C3)

In `src/startd8/concierge/writes.py` (new), two pure functions that compute *planned writes*
without touching disk. **They `stat` to classify status; they NEVER read-and-return existing
consumer-file content** (R1-S5 / FR-C3a — the read-side disclosure fix):

- `build_instantiate_plan(project_root, posture) -> WritePlan` — resolves each kickoff-package
  file's destination + the *template-rendered* content (provenance pre-filled per posture; content
  originates from packaged templates, never from reading the consumer's existing files), plus
  per-file status (`new` / `exists` / `would-overwrite` / `blocked`). Posture ∈ {`prototype`
  (default — R1 PQ-6), `production`}.
- `build_friction_entry(project_root, *, friction, what_happened, implication) -> WritePlan` —
  computes the next id **without parsing human-formatted rows** (ULID-per-line or `.jsonl` line
  count — R1-S7), the entry line, the target log path (`concierge-friction.jsonl`), `action: append`.

`WritePlan` = `{ "writes": [{path, action: new|append|overwrite, status: new|exists|would-overwrite|blocked,
content|append_text, bytes}], "warnings": [...], "schema_version": N }`. A per-file **`status:
blocked`** is set when a target escapes confinement (R1-S9), so the preview surfaces the refusal
*before* `--apply` — never a benign-looking `new` row. This is what MCP returns (preview,
content-bounded per FR-C3a) and what the CLI feeds the safe-writer (which re-validates everything).

### Step 2 — The safe-writer chokepoint (security core; FR-C2/C3.1–C3.6)

`src/startd8/concierge/safe_write.py`: `apply_write_plan(project_root, plan, *, force=False)`.
**The single place any Concierge byte reaches disk, and it treats the WritePlan as untrusted data
(R1-S4 / FR-C3.6) — re-confining and re-classifying every entry regardless of who built it.**
Invariants (each → a named test; map to FR-C3.1–C3.6):

0. **Root integrity (R1-S3 / FR-C3.1):** reject a `project_root` whose lexical path ≠ its realpath
   (a symlinked root), OR confine against `STARTD8_CONCIERGE_ALLOWED_ROOTS`. Else a symlinked root
   makes every write "inside" the resolved base while bytes land in the target.
1. **Confinement, write-time, TOCTOU-closed (R1-S1/S2 / FR-C3.2–C3.3):** open the confined parent
   dir once (`O_DIRECTORY|O_NOFOLLOW`) and create/replace the target via `dir_fd=`
   (`O_CREAT|O_EXCL|O_NOFOLLOW`) so the validated inode is the written inode — no resolve→replace
   race. **Validate every parent component** created by `mkdir`, not just the leaf; refuse if any
   existing parent is a symlink.
2. **No clobber (FR-C3.4):** `new` refuses if the target exists; `overwrite` requires `force=True`;
   `append` only appends, never truncates.
3. **Atomic, incl. append (R1-S8 / FR-C3.5):** `new`/`overwrite` → temp+`os.replace`; `append` →
   `O_APPEND` single `write()` — crash-safe and safe under concurrent `log-friction --apply`.
4. **Structured result:** `{written, skipped, blocked, errors}`. A confinement violation is a hard
   stop for that entry (marked `blocked`); other per-file errors are contained, not raised.

### Step 3 — MCP wrapper: preview-only (OQ-7)

`startd8_concierge` gains `instantiate-kickoff` / `log-friction` to its action enum. Over MCP they
call the **builders only** and return the `WritePlan` JSON, **content-bounded per FR-C3a** (path +
status, no existing-file content). **No `apply` parameter exists on the MCP tool** — it cannot
write, by construction. `readOnlyHint: True` stays honest and is asserted by the FR-C12 conformance
test (fs-watcher: zero writes for every MCP action).

### Step 4 — CLI: the sole writer (FR-C13)

`cli_concierge.py` gains (read-only `survey`/`assess` already shipped):
- `startd8 concierge instantiate-kickoff [ROOT] [--posture prototype|production] [--with-authoring]
  [--apply] [--force] [--check]` — default previews (files + statuses incl. `blocked`); `--apply`
  runs `apply_write_plan` at human privilege; `--force` to overwrite a diverged file; `--check`
  (R1-S6 / FR-C15) reports per-file drift (`matches-template`/`diverged`/`absent`) + a package
  verdict (`complete`/`partial`/`drifted`), non-zero exit on drift — mirrors `generate backend
  --check`. Under `--posture production`, a still-`placeholder` owners block **warns** (never
  blocks — R1-F8).
- `startd8 concierge log-friction [ROOT] --friction TEXT --what-happened TEXT --implication TEXT
  [--apply]` — default previews; `--apply` appends one line to `concierge-friction.jsonl`.
- **Exit semantics (precise — R1-S10):** advisory exit 0; exit 2 unreadable input; **exit 3** if a
  confinement/clobber guard blocked *any* write under `--apply` (partial apply is allowed — valid
  files are written, blocked files reported, no rollback); `--check` exits non-zero on drift.

### Step 5 — Tests

- **Security (load-bearing):** `..`-traversal; absolute path outside root; **symlinked
  project_root** (R1-S3); **symlinked parent component** (R1-S2); **TOCTOU** — swap a parent to a
  symlink between plan-build and apply, assert refused not redirected (R1-S1); **WritePlan with an
  injected escaping `path`** fed straight to `apply_write_plan`, assert hard-stop (R1-S4);
  clobber-without-force; append-not-truncate; **append atomicity** — SIGKILL mid-append leaves
  old or old+one-whole-line, two concurrent appends yield two whole lines (R1-S8).
- **Disclosure (R1-S5 / FR-C3a):** target exists with secret content; assert the MCP preview JSON
  contains none of those bytes.
- **Idempotency/drift (R1-S6):** instantiate → `--check` = `complete`; hand-edit one file →
  `--check` = `drifted` + non-zero exit.
- **Behavior:** empty dir = all `new`; re-run = all `exists`, no change without `--force`; posture
  provenance; owners block ships `placeholder`+`.test`, production `--apply` warns.
- **Conformance (R1-F5 / FR-C12):** fs-watcher asserts zero writes for every action over the MCP tool.
- **Anti-fork:** packaged templates == `docs/.../templates/` tree.
- **CLI:** preview exit 0; `--apply` writes; refused write exit 3; `blocked` shown in preview (R1-S9).

---

## 3. Step → Requirement trace

| Step | Requirements |
|------|--------------|
| 0 Packaging | FR-C7 (prerequisite) |
| 1 Builders | FR-C3 (preview), FR-C3a (disclosure bound), FR-C7, FR-C9, FR-C11 |
| 2 Safe-writer | FR-C2, FR-C3.1–C3.6 (enumerated confinement invariants), OQ-7 |
| 3 MCP preview | FR-C1, FR-C3, FR-C3a, FR-C12 (readOnly verified) |
| 4 CLI writer | FR-C13, FR-C15 (idempotency/drift), OQ-7 |
| 5 Tests | all of the above (security + disclosure + drift + conformance) |

---

## 4. Open Questions — all RESOLVED by CRP R1 (2026-06-12)

- **PQ-1 — Friction-log structure → RESOLVED (R1-S7):** single append-only `concierge-friction.jsonl`
  (one durable home per F-10; append-only, no parse-to-increment, race/crash-safe). Markdown is a
  rendered view, never a second persisted source. (→ FR-C9, Step 1.)
- **PQ-2 — Partial-existing semantics → RESOLVED (R1-S6):** per-file skip-existing **plus** a
  package verdict (`complete`/`partial`/`drifted`) and a `--check` drift mode with non-zero exit;
  never merge YAML. (→ FR-C15, Step 4.)
- **PQ-3 — Symlinked/case-insensitive roots → RESOLVED (R1-S1/S2/S3):** reject a symlinked
  `project_root` (or allowlist); validate every parent component; close the TOCTOU window with
  dir-fd-relative writes; case-fold-aware comparison. (→ FR-C2/C3.1–C3.3, Step 2.)
- **PQ-4 — `owners` block → RESOLVED (R1-F8):** ships `placeholder`+`.test`; production `--apply`
  **warns**, never blocks. (→ FR-C7.)
- **PQ-5 — Preview payload → RESOLVED (R1-S5):** sharper than a size cap — previews return path +
  status and **no existing-file content at all** over MCP (the disclosure bound). (→ FR-C3a.)
- **PQ-6 — Posture default → RESOLVED (R1 PQ-6):** default `prototype` (zero-friction start). (→ FR-C7.)

> New issues CRP surfaced beyond the seeded PQs: the **read-side disclosure leak** (R1-S5/F2 — the
> most important finding), **WritePlan-as-untrusted-input** (R1-S4), **append atomicity** (R1-S8),
> **`blocked` preview status** (R1-S9), **precise exit-3/partial-apply semantics** (R1-S10), and
> **annotation conformance testing** (R1-F5). All folded into §2 / the requirements.

---

*v0.2 — Post-CRP. All 6 seeded PQs resolved + 6 new issues folded in (R1, claude-opus-4-8-1m, all
10 S-suggestions accepted). The security core (Step 2) is now an enumerated invariant set mapping
1:1 to FR-C3.1–C3.6 and named tests. Cleared to implement.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

> R1 triage (2026-06-12): all 10 S-suggestions ACCEPTED. The review was focused, anchored, and
> caught real holes (read-side disclosure, TOCTOU, untrusted WritePlan); no noise to reject.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Close resolve→replace TOCTOU via dir-fd-relative open | R1 | → Step 2 invariant 1 | 2026-06-12 |
| R1-S2 | Validate every `mkdir` parent component (O_NOFOLLOW) | R1 | → Step 2 invariant 1 | 2026-06-12 |
| R1-S3 | Reject symlinked `project_root` / allowlist | R1 | → Step 2 invariant 0 (FR-C3.1); PQ-3 | 2026-06-12 |
| R1-S4 | WritePlan is untrusted; re-confine at the writer | R1 | → Step 2 preamble (FR-C3.6) | 2026-06-12 |
| R1-S5 | Builders stat-only; no existing content over MCP | R1 | → Step 1 + Step 3 (FR-C3a); PQ-5 | 2026-06-12 |
| R1-S6 | Package verdict + `--check` drift mode | R1 | → Step 4 (FR-C15); PQ-2 | 2026-06-12 |
| R1-S7 | Single append-only `concierge-friction.jsonl` | R1 | → Step 1 (FR-C9); PQ-1 | 2026-06-12 |
| R1-S8 | Append atomicity (O_APPEND single write) | R1 | → Step 2 invariant 3 (FR-C3.5) | 2026-06-12 |
| R1-S9 | Preview surfaces `blocked` status pre-apply | R1 | → Step 1 WritePlan status | 2026-06-12 |
| R1-S10 | Precise exit-3 / partial-apply semantics | R1 | → Step 4 exit semantics | 2026-06-12 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | R1 | All R1 suggestions accepted — see Appendix A. | 2026-06-12 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-11

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-11 00:00:00 UTC
- **Scope**: Security-weighted write-path review per sponsor focus file — safe-writer confinement/TOCTOU (PQ-3), OQ-7 boundary leak-check, idempotency/partial-existing (PQ-2), friction-log durability (PQ-1). Adversarial pass included.

##### Focus-file asks (answered before standard suggestions)

**Ask 1 — Is safe-writer confinement airtight (Step 2; PQ-3)?**
- **Summary answer:** No — as specified it has at least three gaps: a TOCTOU window, unvalidated symlinked parent dirs created by `mkdir(parents=True)`, and a `project_root` that is itself a symlink.
- **Rationale:** Step 2 invariant 1 does `resolve()` + `is_relative_to(project_root)` then invariant 3 does `os.replace`. `resolve()` and `os.replace` are *separate syscalls* against *path strings*; between them a racing process (or a malicious template-driven mkdir) can replace a confined parent component with a symlink, so the validated path and the written path differ (classic TOCTOU). Invariant 4 (`mkdir(parents=True)`) walks/creates parents but the plan never says those parents are each re-resolved and re-confined — a parent that is already a symlink is silently traversed. PQ-3's own question (root *is* a symlink) is real: `realpath(project_root)` becomes the confinement base, so a root symlinked into `/etc` makes every write "inside" the realpath and confinement passes by construction.
- **Assumptions / conditions:** Holds on POSIX with concurrent writers or attacker-influenced dirs; on a single-user laptop with no racing process the TOCTOU is low-likelihood but not zero (editors/sync daemons race).
- **Suggested improvements:** Open the *parent dir* once with `O_NOFOLLOW`/`O_DIRECTORY`, then `os.open(name, O_CREAT|O_EXCL, dir_fd=parent_fd)` and write/replace via the dirfd so the validated dir and the written file are the same inode (eliminates TOCTOU). Validate every created parent component (not just the final path) with `O_NOFOLLOW`. For PQ-3, require the caller-supplied `project_root` to equal its own realpath (reject if `Path(root) != Path(root).resolve()`) OR confine against the *lexical* root plus an explicit `STARTD8_CONCIERGE_ALLOWED_ROOTS` allowlist (FR-C3 already names this for the MCP case — reuse it for the CLI). See R1-S1/S2/S3.

**Ask 2 — Is the OQ-7 boundary leak-proof (Step 3/4)?**
- **Summary answer:** The *write* boundary is sound by construction; the **read/disclosure** boundary is not addressed and is the live leak.
- **Rationale:** "No `apply` parameter on the MCP tool" genuinely makes MCP non-writing (Step 3). But Step 1 builders compute per-file status `exists`/`would-overwrite` and "rendered content," which requires *reading the consumer's filesystem*, and that `WritePlan` (content + warnings + existing-file deltas) is returned over MCP to a possibly-untrusted LLM. An MCP caller can thus enumerate which kickoff files already exist and, if any builder ever renders by merging existing content (or a `would-overwrite` diff), exfiltrate file contents — a disclosure write was never needed. Second leak vector: the WritePlan is the *shared* contract the CLI later trusts; the plan does not say the CLI re-derives/validates `path` and `action` independently, so a hand-crafted WritePlan (or one round-tripped through an agent) could carry an out-of-confinement `path` that the CLI honors.
- **Assumptions / conditions:** Leak materializes only if builders read existing-file *content* (not just stat) and/or the CLI trusts plan paths verbatim. If builders stat-only and the CLI re-confines every path, the boundary holds.
- **Suggested improvements:** State explicitly that builders may `stat` but never return existing-file *content* in the preview; cap/omit `would-overwrite` content diffs over MCP (ties to PQ-5). Require the safe-writer (Step 2) to re-confine every `path` in the plan as untrusted input regardless of who built it — the WritePlan is data, not a capability. See R1-S4/S5.

**Ask 3 — Idempotency / partial-existing (PQ-2)?**
- **Summary answer:** Skip-existing is the right *per-file* default but is unsafe as the *package* contract — it can silently certify a half-instantiated package as done.
- **Rationale:** Per-file `new`/`exists` with skip-unless-`--force` (Step 1/4) means a package where 4 of 6 files exist applies the 2 missing ones and reports success, with no aggregate signal that the 4 pre-existing files may be *stale* or *hand-edited away from the template*. F-10 + navig8's existing partial files make this concrete. There is no drift report analogous to `generate backend --check`.
- **Suggested improvements:** Add a package-level status to the result (`complete` / `partial` / `drifted`) and a `--check` mode that reports per-file drift (exists-and-matches-template vs exists-and-diverged vs absent) and exits non-zero on drift, mirroring `generate backend --check` (FR-C10 already commits to composing with it). See R1-S6.

**Ask 4 — Friction-log durability (PQ-1)?**
- **Summary answer:** A single JSON-Lines (`.jsonl`) file is the option that is both one durable home (F-10) and machine-appendable without brittle id-parse.
- **Rationale:** Markdown-table append forces parsing human-formatted rows to compute the next id (brittle, racy on concurrent appends). JSON sidecar + rendered markdown is two files (against F-10's "one durable home"). JSON Lines is append-only by construction (no rewrite, no whole-file parse to append), one file, trivially machine-readable, and can be rendered to markdown on demand by `assess`/a viewer rather than persisted twice. Id = line count or a ULID embedded per line (no parse-to-increment).
- **Suggested improvements:** Make `concierge-friction.jsonl` the durable source-of-truth, append-only; render markdown as a *view* (not a second persisted file). If humans must read raw, a committed `.jsonl` is still diff-legible. See R1-S7.

##### Standard suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | critical | Close the resolve→replace TOCTOU window: open the confined parent dir once and create/replace the target via `dir_fd=` (`O_CREAT\|O_EXCL\|O_NOFOLLOW`), so the path validated by `is_relative_to` is the exact inode written. | Step 2 validates a path *string* with `resolve()` then writes with `os.replace` in a separate syscall; a racing or attacker-controlled dir swap between them defeats confinement. | Step 2, invariant 1+3 (rewrite to dirfd-relative ops) | Test: symlink a parent component after plan-build but before apply (patch `os.replace` to fire a swap); assert write refused, not redirected. |
| R1-S2 | Security | high | Validate every parent component created by `mkdir(parents=True)` with `O_NOFOLLOW`, not just the final target; refuse if any existing parent is a symlink. | Invariant 4 creates parents under the root but does not state each is re-confined; a pre-existing symlinked parent is silently traversed, escaping confinement even when the leaf check passes. | Step 2, invariant 4 | Test: pre-create `<root>/a` as symlink to `/tmp/evil`, plan a write to `<root>/a/b.yaml`; assert refused. |
| R1-S3 | Security | high | Reject (or require allowlist for) a `project_root` that is itself a symlink: enforce `Path(root) == Path(root).resolve()` or confine against `STARTD8_CONCIERGE_ALLOWED_ROOTS`. | PQ-3: realpath-confinement uses the *resolved* root as its base, so a root symlinked into a sensitive tree makes all writes legitimately "inside" it — confinement passes while bytes land in `/etc`. FR-C3 already names the allowlist for MCP; reuse it CLI-side. | Step 2 (new invariant 0: root integrity); PQ-3 resolution | Test: `ln -s /etc <root>`; `instantiate-kickoff <root> --apply`; assert exit 3 (refused). |
| R1-S4 | Security | high | Treat the WritePlan as untrusted data at the safe-writer: re-confine and re-classify every `path`/`action` inside `apply_write_plan` independently of who built it; never trust builder-supplied paths verbatim. | OQ-7 hinges on the CLI being the sole writer, but Step 1's WritePlan is the shared contract; if the writer trusts plan `path`s, a hand-crafted/agent-round-tripped plan carries an escape. Confinement must live at the write chokepoint, not the builder. | Step 2 (state "plan is untrusted input"); Step 4 | Test: feed `apply_write_plan` a plan with `path: ../../etc/x`; assert hard-stop confinement violation. |
| R1-S5 | Security | medium | Specify that preview builders may `stat` but MUST NOT return existing-file *content* (or content diffs) in the WritePlan over MCP; cap/redact `would-overwrite` payloads. | OQ-7 read-side leak: MCP returns the WritePlan to a possibly-untrusted LLM; if builders render by reading/merging existing content, the preview discloses consumer file contents though no write occurs. | Step 1 (builder contract); Step 3 (MCP payload); ties PQ-5 | Test: build a plan where a target exists with secret content; assert preview WritePlan contains no bytes of the existing file. |
| R1-S6 | Validation | high | Add a package-level idempotency verdict (`complete`/`partial`/`drifted`) and a `--check` drift mode (per-file: matches-template / diverged / absent, non-zero exit on drift), mirroring `generate backend --check`. | PQ-2: per-file skip-existing can certify a half-instantiated/stale package as "done" with no aggregate signal; navig8 already has partial files. FR-C10 commits to composing with `--check`. | Step 4 (new `--check`); Step 5 (tests); PQ-2 resolution | Test: instantiate, hand-edit one file, re-run `--check`; assert `drifted` + non-zero exit; re-run without edits asserts `complete`. |
| R1-S7 | Data | medium | Make the friction log a single append-only `concierge-friction.jsonl` (durable source-of-truth); render markdown as an on-demand view, not a second persisted file. | PQ-1: markdown-append needs brittle id-parse and is racy; JSON sidecar + markdown is two files (against F-10's one durable home). JSONL is one file, append-only, machine-appendable, no parse-to-increment. | Step 1 `build_friction_entry`; PQ-1 resolution | Test: concurrent appends produce N distinct lines with monotonic ids; markdown render is reproducible from the `.jsonl`. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | Specify atomicity for the *append* action: `log-friction` and friction-log scaffolding must use the same atomic temp+replace path (or `O_APPEND` with single `write()`), not a read-modify-write, to survive a crash mid-append and concurrent CLI invocations. | Step 2 invariant 3 names atomicity for `new`/`overwrite` but invariant on `append` only says "never truncates" — a crash mid-append or two concurrent `log-friction --apply` can interleave/corrupt the log (the very durability F-10 wants). | Step 2, invariant 2/3 (append atomicity) | Test: SIGKILL mid-append leaves either the old log or old+one-entry, never a torn line; two concurrent appends yield two whole entries. |
| R1-S9 | Security | medium | Define behavior when a planned target path *escapes* but the run is a preview (no `--apply`): the preview must still flag the violation (status `blocked`), not silently render a `new`/`overwrite` row that looks applicable. | An escape that only surfaces at `--apply` time means the MCP/CLI preview shows a benign-looking plan; the confinement verdict belongs in the WritePlan so agents/humans see refusal before applying. | Step 1 (WritePlan per-file status add `blocked`); Step 3 | Test: build plan with an escaping target; assert preview marks it `blocked` and `--apply` exits 3. |
| R1-S10 | Ops | low | Define the exit-3 contract precisely: is exit 3 returned if *any* file was blocked (partial apply) or only on total refusal, and are already-written files rolled back or left? CI needs deterministic semantics. | Step 4 says exit 3 "when a guard blocked the write" but Step 2 invariant 5 allows contained per-file errors with continued processing — the partial-apply + exit-code interaction is undefined. | Step 4 (exit semantics); Step 2 invariant 5 | Test: plan with one escaping + one valid file; assert documented behavior (e.g. valid file written, exit 3, blocked file reported) is deterministic. |

---

## Requirements Coverage Matrix — R1

Analysis only (dual-document mode). Maps each in-scope requirement to the plan step(s) that address it. Out-of-v1 FRs (FR-C5/C6/C8) shown for completeness but are not write-path increment scope.

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-C1 (single FastMCP tool, action-dispatched) | Step 3 (adds actions to enum) | Full | — |
| FR-C2 (assist-only capability envelope; no write outside consuming project) | Step 2 (confinement) | Partial | "Consuming project directory" undefined under symlink/relative/case-insensitive conditions (R1-F7); confinement is plan-time only, no write-time re-check (R1-S1). |
| FR-C3 (MCP never writes; CLI sole writer; path-confinement) | Steps 2, 3, 4 | Partial | Write boundary covered; read/disclosure boundary (preview returning existing content) unaddressed (R1-S5/R1-F2); symlinked-root case not handled (R1-S3/R1-F1); WritePlan-as-untrusted-input not stated (R1-S4). |
| FR-C7 (instantiate-kickoff; provenance per posture; owners flagged; template packaging prerequisite) | Steps 0, 1, 4 | Partial | Packaging + provenance covered; `owners`-block "flagged" semantics + posture interaction undefined (R1-F8 / PQ-4); partial-existing/drift detection missing (R1-S6/R1-F6). |
| FR-C9 (log-friction; durable, committed, structured) | Steps 1, 4 | Partial | Durability committed but format/append-safety unspecified — PQ-1 unresolved (R1-S7/R1-S8/R1-F4). |
| FR-C11 (schema-versioned JSON results) | Step 1 (`WritePlan.schema_version`) | Full | — |
| FR-C12 (annotations honest about posture; readOnlyHint) | Step 3 (`readOnlyHint: True` retained) | Partial | Annotation declared honest but no conformance test that runtime behavior matches the hint (R1-F5). |
| FR-C13 (CLI parity; sole writer; exit semantics) | Step 4 | Partial | Exit-3 partial-apply/rollback semantics undefined (R1-S10); preview must surface `blocked` status (R1-S9). |
| FR-C14 (cross-package split; thin MCP wrapper; monolith+package mirror caveat) | Step 3 | Partial | Step 3 names the enum addition but not the `startd8_mcp_server/server.py` mirroring caveat the requirements flag — implementer-facing duplication risk uncarried. |
| OQ-7 (MCP preview-only / CLI sole writer) | Steps 3, 4 | Partial | Write side leak-proof; read-side disclosure + WritePlan-trust gaps remain (R1-S4/S5, R1-F2). |
| FR-C5 / FR-C6 / FR-C8 (survey / assess / derive-contract) | (out of v1 increment) | N/A | Read-only core shipped (C5/C6); C8 deferred. Not write-path scope. |


