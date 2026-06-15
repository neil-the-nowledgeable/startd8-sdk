# CRP Focus — Concierge Write-Path Increment

Weight the review on the **write-path security surface**. The read-only core (`survey`/`assess`)
already shipped and is not under review; focus on `instantiate-kickoff` + `log-friction`, the
safe-writer, and the OQ-7 boundary.

## Where we need input most

1. **Safe-writer confinement is airtight (Plan Step 2; PQ-3).** The single chokepoint claims
   path confinement via `resolve()` + `is_relative_to(project_root)`, reject `..`/symlink escape,
   no-clobber, atomic `os.replace`. Is this sufficient against: a `project_root` that is itself a
   symlink into a sensitive tree; TOCTOU between resolve and write; case-insensitive/UNC FS edge
   cases; a planned target whose parent dir is a symlink? What guard is missing?

2. **OQ-7 boundary leak-check (Plan Step 3/4).** The claim: the MCP tool has *no* `apply`
   parameter and calls builders only, so it physically cannot write; the CLI is the sole writer
   at human privilege. Is that boundary actually leak-proof as designed, or does any path
   (preview content containing secrets, a builder with a side effect, the shared WritePlan) let
   an MCP-invoked call cause a write or disclose something it shouldn't?

3. **Idempotency / partial-existing semantics (PQ-2).** navig8 already has *some* kickoff files.
   Plan says per-file `new`/`exists`, skip-existing unless `--force`, never merge YAML. Is
   skip-existing the right default, or does it silently leave a half-instantiated package that
   reads as "done"? Should re-run report drift the way `generate backend --check` does?

4. **Friction-log durability (PQ-1).** `log-friction` is the first writer of the friction log.
   Markdown-table append (human-canonical, brittle id-parse) vs JSON sidecar + rendered markdown
   (two files, against F-10's "one durable home"). Which survives F-10 (uncommitted-artifact
   loss) and stays machine-appendable? Is there a single-file option that is both?
