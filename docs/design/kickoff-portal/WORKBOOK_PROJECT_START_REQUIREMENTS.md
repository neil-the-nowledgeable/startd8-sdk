# Digital Project Workbook — Project-Start Generation Requirements

**Version:** 0.6 (FR-9 + FR-5 collision-detection now implemented — post-merge deferred-item pass)
**Date:** 2026-07-08
**Status:** IMPLEMENTED — every FR available & tested (FR-9 single-field confirm; FR-5 collision guard at
provision-time). Remaining deferrals: FR-9 batch/guided refresh, and the owner-doc live-metrics track (NR-1).
**Owner doc for the generator/content:** `GRAFANA_KICKOFF_PORTAL_REQUIREMENTS.md` (v0.4). **This doc owns
only the project-start _lifecycle_** — when/how the Workbook is created, not what it contains.

---

## 0. Planning Insights (Self-Reflective Update)

> The v0.1 premise was: "define requirements for a generated top-level Digital Workbook, deterministically
> generate it as a Grafana dashboard via the jsonnet generator, and wire it into kickoff." Planning
> (reading the actual code) **falsified most of the build-it framing** — the generator already exists.
> The real, much narrower net-new is the **project-start wiring**.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| We haven't formally specced the generated Workbook | It's specced in `GRAFANA_KICKOFF_PORTAL_REQUIREMENTS.md` v0.4 (CRP-hardened) and **shipped** | This doc is scoped to the *delta* (project-start wiring), and **cites** that doc rather than restating it |
| We need to build the deterministic jsonnet generator | `build_kickoff_portal_spec()` (`portal_spec.py:303`) already returns a `DashboardSpec` dict → `DashboardCreatorWorkflow().run()` compiles it through the **startd8-mixin jsonnet** path, `$0`, deterministic | **NR-5**: no new generator. FR-1 = reuse the existing path verbatim |
| The current Workbook is a "markdown portal" to reconcile | It's a **real Grafana dashboard**; markdown is just the *panel type* for text panels within it. UID `cc-portal-kickoff-{project}`, title `{project} — Digital Project Workbook` (`portal_spec.py:329-332`) | Nothing to reconcile; the "markdown portal" premise was wrong |
| Just add a project-start hook and we're done | `kickoff instantiate` (`concierge_instantiate`, `cli_concierge.py:321`; canonical alias `cli_concierge.py:1170`) is **pure, `$0`, no external toolchain**. Dashboard gen needs the **jsonnet toolchain** (binary `jsonnet` or `gojsonnet`) | **Central design tension** (OQ-4): wiring gen into the pure file-scaffold couples it to an external toolchain. FR-6/FR-7 isolate + degrade so instantiate never fails on a missing toolchain |
| Provision the dashboard at start | Provisioning targets a **shared** Grafana (`o11y-dev`, NR-10 blast radius) and needs a token/URL not present at project start | **FR-3/NR-4**: generate-to-disk by default; provision only on explicit `--provision <url>` |

**Resolved open questions:**
- **OQ (generate even when the board is empty?) → YES.** At instantiate the input YAMLs are fresh
  templates, so the Workbook is an all-backlog *skeleton*. That is the intended day-1 artifact — the
  living board the human fills in (FR-4).
- **OQ (provision at start?) → NO auto.** Opt-in `--provision` only (FR-3).
- **OQ (rebuild the generator?) → NO.** Reuse (FR-1 / NR-5).
- **OQ-3 (per-project only, or also a portfolio roll-up?) → BOTH (user decision).** Add a **portfolio
  index** dashboard (FR-11). Planning insight: the per-project Workbooks are already tagged `workbook`
  (`portal_spec.py:337`), so a Grafana **`dashlist` panel filtered by that tag** auto-lists every project
  Workbook — the link-index is **self-updating** (Grafana resolves the tag at view time), generated once,
  no per-project registry, `$0`. The cross-project **status** roll-up (confirmed-%/gaps *per project* in
  one view) needs per-project metrics aggregated → gated on the deferred metric seam → **NR-1**.
- **OQ-4 (`--portal` default at instantiate?) → ON, graceful skip (user decision).** FR-2 default ON;
  FR-6 makes a missing toolchain a printed nudge, not a failure.
- **OQ-6 (does the generator support `dashlist`?) → NO (verified).** `PanelType` (`models.py:16-39`) has
  no `dashlist`, and `startd8-mixin/lib/panels.libsonnet` has no dashboard-list constructor. So **FR-11 is
  NOT "reuse only"** — it needs a **bounded** addition: a `dashlist` `PanelType` + a mixin `panels.dashlist`
  constructor. This is the single, explicit exception to NR-5 (the phantom-reference audit caught it before
  CRP, not during implementation).

### 0.3 Implementation-Verification (v0.4 → v0.5)

> Post-implementation review mapped every FR/NR to the shipped code + tests. **FR-1..4, FR-6..11 and
> all NR are fully available and working as documented** (14 `test_portal_build` cases + the
> `dashboard_creator` suite). One refinement:
>
> - **FR-5 collision-detection narrowed.** The v0.4 "two distinct projects that slugify to the same UID
>   MUST be detected and rejected" is **not a `$0`/deterministic capability** — there is no local
>   registry of all projects' UIDs, and a cross-project collision is only observable at *provision* time
>   against a shared Grafana. Implemented deterministically: the **1:1 named slug + reserved-`index` +
>   empty-slug rejection** (all tested); rename → new UID → old board orphaned-but-index-listed (a
>   documented acceptable outcome, no code). **Cross-project collision detection is deferred** to a
>   provision-time guard (a `get_dashboard(uid)` title check), tracked with the other provisioning-
>   hardening deferrals. The doc now states this limitation honestly rather than claiming an unshipped
>   capability.

### 0.2 CRP Round-1 Triage (v0.3 → v0.4)

> Dual-doc CRP R1 (claude-opus-4-8-1m) returned 10 F-suggestions (requirements) + 9 S-suggestions (plan).
> **9 of 10 F accepted** (the config-pinned-default half of R1-F5 rejected — YAGNI). Changes:

| Finding | Sev | Disposition → change |
|---|---|---|
| R1-F1 / R1-S3 | high | ✅ **FR-7** now asserts two isolation invariants (gen only after durable `res.ok`; never writes inside the source-of-record tree) + fault-injection AC |
| R1-F2 | high | ✅ **FR-6** splits absent vs **present-but-broken** toolchain — both degrade non-fatally |
| R1-F6 / R1-S4 | high | ✅ **FR-5** pins the 1:1 slug function, rejects slug-collisions (no silent clobber), defines rename semantics |
| R1-F4 | med | ✅ **FR-5** reserves the `index` slug (can't collide with the portfolio-index UID) |
| R1-F3 | med | ✅ **FR-11** adds `dashlist` folder/permission scoping invariant |
| R1-F7 | low | ✅ **FR-11** elevates the `workbook`-tag to a regression-guarded contract |
| R1-F8 / R1-S8 | med | ✅ new **NR-6** — stricter provision guard for the global index; never auto-provision |
| R1-F9 | med | ✅ **FR-4** now owns an empty-state smoke-check AC (not deferred by citation) |
| R1-F5 (output) / R1-S9 | low | ✅ **FR-2** defines `--no-portal` output + preview silence |
| R1-F5 (config default) | low | ❌ **Rejected** (Appendix B) — pinning the default off via config is YAGNI until a user asks |
| R1-F10 | low | ✅ **OQ-7** constrained: index gen toolchain-gated + never silent auto-provision |

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted the SDK design-docs lessons index (`Lessons_Learned/sdk/`). Applied:

- **Phantom-reference audit** — every symbol cited here was read at the byte level (see §Reference Audit);
  corrected the sub-agent's `startd8 kickoff instantiate` decorator claim (actual: `concierge_app.command
  ("instantiate-kickoff")` re-registered onto the kernel as `instantiate`, `cli_concierge.py:1170`).
- **Single-source vocabulary ownership** — the dashboard's content/panels/live-data status is **owned by**
  `GRAFANA_KICKOFF_PORTAL_REQUIREMENTS.md`; this doc cites §-refs and does not restate its FRs (FR-8).
- **Prune phantom scope** — live OTel metrics / burndown (that doc's deferred FR-2/5d) are **out of scope
  here** → NR-1, not smuggled in as "make it live at start."
- **CRP steering** — least-reviewed artifact = this new lifecycle doc + its plan; **settled, do-not-
  relitigate:** the generator internals, the `cc-portal-kickoff-{project}` UID, the deterministic jsonnet
  path, and the live-data deferral (all decided in the owner doc's CRP R1).

---

## 1. Problem Statement

The Digital Project Workbook — a per-project Grafana dashboard deterministically generated from canonical
`KickoffState` — exists and is generated **only by a manual `startd8 kickoff portal` step**. A freshly
instantiated project therefore has **no home dashboard** until a human remembers to run that command.
The Workbook should be a project's landing surface *from the moment the project starts*. This spec wires
Workbook generation into the project-start flow (`kickoff instantiate`) and formalizes that lifecycle.

### Gap table

| Component | Current state | Gap |
|---|---|---|
| Generator (spec → jsonnet → JSON) | ✅ `build_kickoff_portal_spec` + `DashboardCreatorWorkflow` (deterministic, `$0`) | none — reuse |
| CLI to generate / provision | ✅ `startd8 kickoff portal [--provision <url>]` (`cli_concierge.py:953`) | manual only |
| **Creation at project start** | ❌ `kickoff instantiate --apply` writes the kickoff YAMLs but does **not** generate the Workbook | **wire it (FR-2)** |
| Toolchain-absent handling at start | ❌ dashboard gen would hard-fail if `jsonnet`/`gojsonnet` absent | **degrade (FR-6)** |
| Isolation from the source-of-record write | ❌ n/a (not wired) | **non-fatal (FR-7)** |
| Refresh as fields get confirmed | ❌ manual re-run of `kickoff portal` | optional auto-refresh (FR-9, deferred) |

---

## 2. Requirements

- **FR-1 — Reuse, don't rebuild.** Project-start generation MUST reuse `build_kickoff_portal_spec()` →
  `DashboardCreatorWorkflow().run(...)` (the deterministic startd8-mixin jsonnet path). No new generator,
  no hand-authored dashboard JSON. (Cites owner doc FR-4.)
- **FR-2 — Generate at project start.** `kickoff instantiate --apply`, **after** the kickoff package is
  written successfully, MUST generate the Workbook dashboard JSON to disk (default `.startd8/dashboards/`),
  gated behind a `--portal / --no-portal` flag (default ON). **Preview** (`instantiate` without `--apply`)
  MUST NOT generate anything — side-effect-free, matching the preview-by-default contract
  (`cli_concierge.py:360-370`). `--no-portal` MUST print a one-line `Workbook: skipped (--no-portal)`;
  preview MUST print nothing about the Workbook. *(CRP R1-F5/R1-S9.)*
- **FR-3 — Provision is opt-in + explicit.** FR-2 writes JSON only. Provisioning to Grafana happens ONLY
  with an explicit `--provision <url>` (passthrough to the existing workflow provision path). Never
  auto-push to a shared instance. On success, print the dashboard URL.
- **FR-4 — Skeleton-at-start is intended.** The generated Workbook at instantiate reflects the fresh
  templates (fields unconfirmed → attention = backlog/gap). It is generated anyway as the project's living
  skeleton; it fills in as the human confirms fields. **AC (this doc owns it — CRP R1-F9):** compiling the
  Workbook for an all-fresh-template project MUST produce valid JSON with **no panel in an error state**
  (empty/"No data" is fine, a broken query is not) — a golden guards day-1 UX rather than deferring
  correctness to the owner doc by citation.
- **FR-5 — Idempotent upsert + 1:1 slug (CRP R1-F4/R1-F6; scope refined at impl-verification — see §0.3).**
  Generation MUST target the stable UID `cc-portal-kickoff-{project-slug}` and overwrite in place. The
  **slug function MUST be named and 1:1** (`portal_spec.slugify_project`/`workbook_uid`, pinned in the
  Reference Audit). The literal slug **`index` is RESERVED** (see FR-11) — a project slugifying to `index`
  MUST be rejected (`WorkbookSlugError`), never allowed to collide with the portfolio-index UID; an
  empty slug is likewise rejected. **Rename** has defined behavior with no new code: a renamed project
  slugifies to a *new* UID → a new board; the old board is orphaned and remains listed by the index
  (an explicitly acceptable outcome). **Cross-project UID collision detection — IMPLEMENTED (v0.6).**
  Before provisioning to a Grafana, `portal_build._provision_collision_reason` does a
  `get_dashboard(uid)` title check; if the UID already belongs to a **different** project (different
  title) the provision is **refused, never clobbered** — the user renames. Best-effort: a check that
  can't run (network/auth) doesn't block (the provision itself surfaces those errors), and disk-only
  generation can't collide (each project owns its own file). Only the provision path needs it.
- **FR-6 — Graceful toolchain degradation (absent AND broken — CRP R1-F2).** (a) If the jsonnet toolchain
  (binary `jsonnet` or `gojsonnet`) is **absent**, instantiate MUST NOT fail; it completes the file
  scaffold and prints an actionable one-liner (`Workbook skipped — install jsonnet or `pip install
  gojsonnet`, then run `startd8 kickoff portal``). (b) A toolchain that is **present but fails at runtime**
  (non-zero exit, import error, compile timeout, OOM) MUST also degrade to a non-fatal, clearly-labelled
  warning (`Workbook generation failed — <reason>; see <log>`), never a stack trace. Neither case blocks
  the kickoff-package write.
- **FR-7 — Non-fatal isolation (invariants — CRP R1-F1/R1-S3).** Any Workbook-generation/provisioning
  error MUST be reported but MUST NOT change the instantiate exit code, which reflects only the
  **file-scaffold** write result (`cli_concierge.py:377-380`). Two isolation invariants make this testable:
  **(a)** generation is reachable ONLY after the file-scaffold write has returned a durable `res.ok` (never
  concurrently); **(b)** Workbook generation MUST NOT write, lock, or re-open any path *inside* the
  source-of-record kickoff-package directory — dashboard output goes to a sibling `.startd8/dashboards/`
  only. (Fault-injection AC: kill mid-generation → the kickoff YAMLs are byte-identical and the exit code
  is unchanged.)
- **FR-8 — Single-source vocabulary.** This doc owns only the project-start lifecycle. Content, panels,
  and live-data status are owned by `GRAFANA_KICKOFF_PORTAL_REQUIREMENTS.md`; cite it, don't restate.
- **FR-9 — Refresh on confirm (IMPLEMENTED v0.6 for single-field confirm).** `kickoff confirm <field>`
  regenerates the Workbook afterward (reuses the FR-10 helper; `--portal/--no-portal` default ON,
  `--provision` passthrough), so the board tracks the newly-confirmed field. Non-fatal + `$0`. The batch
  (`--all`) and interactive guided walks do **not** yet auto-refresh — a small follow-up (they call the
  same `_workbook_refresh` helper); until then re-run `startd8 kickoff portal` after those.
- **FR-10 — Shared generation helper (anti-drift).** The generate-(+provision) logic MUST live in ONE
  helper reused by both `kickoff portal` and `instantiate --portal`, so the two entry points cannot drift
  (the portal command body is the current home; factor its state→spec→workflow steps out).
- **FR-11 — Portfolio roll-up index (link-index; NEW, per OQ-3).** Provide a single **global** dashboard
  (UID `cc-portal-kickoff-index`, title `Digital Project Workbooks — Index`) whose primary panel is a
  **`dashlist`** filtered to tag `workbook`, auto-listing/linking every per-project Workbook. It MUST be
  deterministic, `$0`, generated via the same jsonnet path (FR-1), and **self-updating** — because the
  `dashlist` resolves the tag at view time, the index does **not** regenerate when a new project appears;
  it is generated/upserted once (idempotent UID) and stays current. Exposed via `startd8 kickoff portal
  --index` (or an equivalent flag/subcommand — TBD in CRP). Cross-project *status* aggregation is **NR-1**
  (deferred). **Requires** a bounded generator addition — a `dashlist` `PanelType` + a mixin
  `panels.dashlist` constructor (verified absent, OQ-6) — the one explicit exception to NR-5.
  **Scoping invariants (CRP R1-F3/R1-F7):** (a) the index and the per-project Workbooks MUST share a
  documented **folder/permission scope** — the "self-updating" claim holds only for Workbooks the *viewer*
  can see; state whether the `dashlist` is folder-scoped or instance-wide. (b) The index depends on the
  **invariant that every generated Workbook carries the `workbook` tag** (`portal_spec.py:337`); this is
  now a contract (regression-guarded), not an incidental fact — if the tag is ever made conditional the
  index silently under-lists. The index MUST render cleanly with **zero** Workbooks (empty `dashlist`, not
  an error — CRP R1-S5).

---

## 3. Non-Requirements

- **NR-1 — No live OTel metrics / burndown timeseries** (owner doc FR-2/5d, deferred). Static reads only.
  This also **bounds FR-11**: the portfolio index ships as a **link-index** (`dashlist`); a cross-project
  *status* roll-up (per-project confirmed-%/gaps in one aggregated view) is deferred with the metric seam.
- **NR-2 — The portfolio index is a LINK-index, not a data-aggregating dashboard.** It links to each
  project's Workbook (via the `workbook` tag); it does not re-compute or centralize per-project field data.
- **NR-3 — No form-filling / writes from the dashboard.** The Workbook is a read/status surface (SPIKE
  verdict: COMPLEMENTARY). Writes go through the separate stakeholder-panel / apply-gate tracks.
- **NR-4 — No auto-provisioning to a shared Grafana** without an explicit `--provision <url>` (NR-10
  blast radius on the shared `o11y-dev`).
- **NR-5 — No new generator, compiler, or hand-authored dashboard JSON** — **except** the one bounded
  addition FR-11 needs: a `dashlist` `PanelType` + a mixin `panels.dashlist` constructor (OQ-6). Everything
  else reuses the existing deterministic path.
- **NR-6 — The portfolio index gets a STRICTER provision guard than a per-project board (CRP R1-F8/R1-S8).**
  Because the index is a global singleton with portfolio-wide blast radius, provisioning it
  (`--index --provision <url>`) to a **non-loopback** URL MUST require an extra confirmation / allowlist
  flag beyond the per-project `--provision`. Whatever OQ-7 trigger is chosen, the index MUST NEVER be
  *auto*-provisioned (auto-upsert-on-any-provision, if adopted, generates to disk only).

---

## 4. Open Questions

- **OQ-5 — Provision UX at start.** When `--provision` is given at instantiate, should it also need the
  panel/datasource wiring (separate track), or is a bare provisioned board (no live panels) acceptable at
  start? (Leaning: bare board is fine — it's the skeleton; wiring the run/apply panels is a later step.)
- **OQ-7 — Index generation trigger.** `--index` flag on `kickoff portal`, a dedicated `kickoff portal
  --index-only`, or auto-upsert-the-index whenever any project Workbook is provisioned? (Index is a
  singleton; over-generating is harmless but noisy.) **Constraint (CRP R1-F10):** whichever trigger is
  chosen, index generation MUST be toolchain-gated identically to FR-6 (absent/broken toolchain → degrade,
  no crash), and the auto-upsert option MUST NOT silently re-provision (NR-6).

---

## Reference Audit (phantom-reference check — all verified by reading bytes)

| Symbol / command | Location | Verified |
|---|---|---|
| `build_kickoff_portal_spec(state, project, *, roster, panel_results, pipeline)` | `portal_spec.py:303-342` | ✅ pure, returns DashboardSpec dict, UID `cc-portal-kickoff-{slug}` |
| `DashboardCreatorWorkflow().run(config)` | `dashboard_creator/workflow.py` | ✅ deterministic jsonnet path, `provision`/`output_dir` keys |
| `startd8 kickoff portal [--provision]` | `@kickoff_kernel_app.command("portal")` `cli_concierge.py:953` | ✅ generate + optional provision |
| `startd8 kickoff instantiate` (hook) | `concierge_instantiate` `cli_concierge.py:321`; kernel alias `:1170`; write path `:372-380` | ✅ preview-by-default, `--apply` writes |
| startd8-mixin jsonnet toolchain | `startd8-mixin/` (present, vendored grafonnet) | ✅ needs `jsonnet` binary or `gojsonnet` |

---

*v0.4 — Post-CRP R1. 9/10 F-findings accepted (see §0.2): FR-5 slug-collision/rename/reserved-`index`,
FR-6 broken-vs-absent toolchain, FR-7 isolation invariants, FR-11 dashlist scoping + tag contract, new
NR-6 index-provision guard, FR-4 empty-state AC, FR-2 `--no-portal` output, OQ-7 constraint. Ready to
implement. (v0.3 — reflective loop: build-it framing collapsed to a wiring-it delta; generator reuse
affirmed NR-5; live-data pruned to NR-1.)*

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

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | FR-7 isolation invariants (post-`res.ok`, no source-of-record writes) | CRP R1 | Merged into FR-7 (a)/(b) + fault-injection AC | 2026-07-08 |
| R1-F2 | Split absent vs present-but-broken toolchain | CRP R1 | Merged into FR-6 (a)/(b) | 2026-07-08 |
| R1-F3 | dashlist folder/permission scoping invariant | CRP R1 | Merged into FR-11 scoping invariant (a) | 2026-07-08 |
| R1-F4 | Reserve the `index` slug | CRP R1 | Merged into FR-5 (reserved-slug clause) | 2026-07-08 |
| R1-F5 (output) | Define `--no-portal` output + preview silence | CRP R1 | Merged into FR-2 | 2026-07-08 |
| R1-F6 | Pin slug fn + collision-reject + rename semantics | CRP R1 | Merged into FR-5 | 2026-07-08 |
| R1-F7 | Elevate `workbook`-tag to a contract | CRP R1 | Merged into FR-11 scoping invariant (b) | 2026-07-08 |
| R1-F8 | Stricter provision guard for the global index | CRP R1 | New NR-6 | 2026-07-08 |
| R1-F9 | FR-4 owns an empty-state smoke-check AC | CRP R1 | Merged into FR-4 AC | 2026-07-08 |
| R1-F10 | Index gen toolchain-gated + no silent auto-provision | CRP R1 | Merged into OQ-7 constraint + NR-6 | 2026-07-08 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-F5 (config default) | Allow pinning `--portal` default OFF via project config | CRP R1 | YAGNI — no user has asked for an always-off default; `--no-portal` per-invocation covers it. Revisit if a config default is requested. | 2026-07-08 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-08

- **Reviewer**: claude-opus-4-8 (1M context)
- **Date**: 2026-07-08 20:30:00 UTC
- **Scope**: Requirements review of the project-start lifecycle delta — weighted to the sponsor focus asks (toolchain coupling, FR-11 dashlist index, default-ON empty skeleton, idempotency/UID, provisioning blast-radius). Settled owner-doc items (generator internals, UID scheme, jsonnet path, live-data deferral) treated as fixed.

##### Sponsor focus asks (answered first, per focus file)

**Ask 1 — Toolchain coupling: are FR-6 + FR-7 sufficient? Any path where a gen/provision failure corrupts or blocks the source-of-record write, or where the exit-code contract leaks?**
- **Summary answer:** Partial — sufficient *in principle*, but FR-6/FR-7 under-specify two ordering/isolation invariants that an implementer could violate without failing any stated acceptance check.
- **Rationale:** FR-7 says the error "MUST NOT change the instantiate exit code" and FR-2 says generation happens "**after** the kickoff package is written successfully," but neither states that the toolchain probe and generation MUST run strictly after the write is *durably flushed/returned* — nor that generation MUST NOT touch, re-open, or lock any path under the source-of-record directory. A generation step that writes into the same tree (e.g. `.startd8/`) or that is invoked before `res.ok` is returned could still corrupt/partially-write. FR-6 also only covers the *missing-toolchain* case; a *present-but-broken* toolchain (jsonnet segfault, gojsonnet import raises, OOM) is only implicitly covered by FR-7's "any error."
- **Assumptions / conditions:** the write path returns a durable result object (`res.ok`) before generation is reachable.
- **Suggested improvements:** see R1-F1 (ordering/no-shared-write invariant) and R1-F2 (broken-toolchain vs absent-toolchain distinction).

**Ask 2 — FR-11 portfolio index: is "self-updating via the `workbook` tag, generate-once" correct for a Grafana `dashlist`? Failure modes (tag collisions, folder/permission scoping, an untagged Workbook, stale/deleted boards)? Is `cc-portal-kickoff-index` collision-safe vs per-project UIDs?**
- **Summary answer:** Mostly correct on the "generate-once / self-updating" mechanic, but the requirement omits the `dashlist` **scoping** parameters that determine whether the claim holds, and does not address stale/deleted-board or cross-folder visibility.
- **Rationale:** A Grafana `dashlist` resolves its tag filter at view time (so "self-updating" is right), but only within the **folders/permissions the viewer can see**; FR-11 never states which folder the per-project Workbooks or the index live in, so a Workbook provisioned into a folder the index viewer can't read silently won't appear. FR-11 also assumes every Workbook carries the `workbook` tag — true today (`portal_spec.py:337`) but not asserted as an invariant the index depends on. UID `cc-portal-kickoff-index` cannot collide with `cc-portal-kickoff-{slug}` *unless a project slug equals the literal string `index`* — an unguarded edge.
- **Assumptions / conditions:** the index and Workbooks share a folder/permission scope; no project slugifies to `index`.
- **Suggested improvements:** see R1-F3 (dashlist scoping + folder invariant), R1-F4 (reserve/guard the `index` slug), R1-F7 (tag-presence invariant).

**Ask 3 — FR-2 default-ON with an empty skeleton: net positive or noise?**
- **Summary answer:** Net positive to *generate to disk* by default; but "default-ON" is under-defined for the **provision** interaction and for the user who ran plain `instantiate --apply` expecting a pure file scaffold.
- **Rationale:** FR-2 makes disk-gen default-ON; FR-3 keeps provision opt-in, so blast radius is bounded — good. The residual surprise is purely local (an extra JSON file under `.startd8/dashboards/`), which the FR-2 human-output line ("Workbook: <json_path>") mitigates. This is acceptable, but the requirement doesn't state the *disposition of `--no-portal`* relative to the skip note (does `--no-portal` print anything?) or whether the default can be pinned via config for users who always want it off.
- **Assumptions / conditions:** none.
- **Suggested improvements:** see R1-F5 (define `--no-portal` output + optional config default).

**Ask 4 — Idempotency/UID: any race or slug-collision that duplicates or clobbers a board?**
- **Summary answer:** Yes — two distinct projects can slugify to the same UID, and project rename orphans the old board; neither is addressed.
- **Rationale:** FR-5 relies on `overwrite=True` + stable UID `cc-portal-kickoff-{project-slug}`. Slugification is lossy (`My App` and `my-app` and `my_app` may all → `my-app`), so two projects → one UID → the second **clobbers** the first's board (not a duplicate — a silent overwrite). A project **rename** changes the slug → a *new* board, orphaning the old one (stale entry the index still lists). Neither the requirement nor the Reference Audit pins the slug function.
- **Assumptions / conditions:** slug is derived from a human-supplied project name.
- **Suggested improvements:** see R1-F6 (slug-collision + rename semantics).

**Ask 5 — Provisioning blast-radius (NR-4): airtight against accidental shared-instance pushes? Should the index (FR-11) have a stricter guard?**
- **Summary answer:** NR-4 is airtight for the *default* path (no `--provision` = no push); the residual risk is a user pasting a shared URL into `--provision`, which no requirement guards. The index deserves a stricter guard than a per-project board.
- **Rationale:** NR-4 forbids *auto*-push; explicit `--provision <url>` is by-design a user action. But the index is a *global singleton* on a shared instance — an accidental `--index --provision <shared-url>` mutates a portfolio-wide surface, higher blast radius than one project board. No confirmation/allowlist is required for either.
- **Assumptions / conditions:** none.
- **Suggested improvements:** see R1-F8 (index-provision confirmation/guard).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | high | Strengthen FR-7 to assert two isolation invariants: (a) generation is reachable ONLY after the file-scaffold write has returned a durable `res.ok` (not concurrently), and (b) Workbook generation MUST NOT write, lock, or re-open any path *inside* the source-of-record kickoff-package directory (dashboard output goes to a sibling `.startd8/dashboards/`, never the YAML tree). | FR-7 guarantees the exit code but not that a mid-generation crash cannot corrupt the just-written source-of-record; the two invariants make "non-fatal isolation" testable rather than aspirational. | FR-7 (add sub-bullets) | Fault-injection test: kill the process mid-generation; assert the kickoff YAMLs are byte-identical to the pre-generation write and exit code is unchanged. |
| R1-F2 | Risks | high | Split FR-6's "absent" case from a "present-but-broken" case: FR-6 covers missing `jsonnet`/`gojsonnet`; add that a toolchain that is present but *fails at runtime* (non-zero exit, import error, timeout) MUST also degrade to a non-fatal warning under FR-7, with a distinct message ("Workbook generation failed — see <log>"). | "Missing toolchain" and "broken toolchain" are different user situations; today only the missing case has an actionable one-liner, and the broken case falls through to a generic FR-7 catch with no guidance. | FR-6 (add a clause) / FR-7 | Monkeypatch the workflow `.run()` to raise mid-compile; assert instantiate exits with the write result's code and prints the failure message, not a stack trace. |
| R1-F3 | Interfaces | medium | FR-11 MUST specify the `dashlist` scoping parameters it depends on: which Grafana **folder** the index and per-project Workbooks live in, and whether the `dashlist` is folder-scoped or instance-wide. State the invariant that the index only lists Workbooks the *viewer* can see. | The "self-updating" claim silently breaks across folders/permissions; without pinning folder scope, a provisioned Workbook can be invisible in the index with no error. | FR-11 (add scoping clause); NR-2 | Provision two Workbooks into different folders; assert the index either lists both (instance-wide) or documents the folder constraint. |
| R1-F4 | Data | medium | Reserve the literal slug `index` (and document the guard) so no project named "Index"/"index" slugifies to `cc-portal-kickoff-index` and collides with the portfolio index UID. | FR-11's index UID is `cc-portal-kickoff-index`; the per-project scheme is `cc-portal-kickoff-{slug}`. A project slugging to `index` clobbers the portfolio index — an unguarded collision the doc claims is "collision-safe." | FR-5 / FR-11 (add reserved-slug note) | Unit test: instantiate a project named "Index"; assert the generated UID is NOT `cc-portal-kickoff-index` (suffix/escape) or the run is rejected with a clear error. |
| R1-F5 | Interfaces | low | FR-2 SHOULD define the `--no-portal` output contract (is a one-line "Workbook generation skipped (--no-portal)" printed?) and note whether the default-ON can be pinned off via project config for users who never want the dashboard. | FR-2 introduces `--portal/--no-portal` but is silent on what `--no-portal` prints and whether the default is configurable, leaving UX ambiguous for the always-off user. | FR-2 | Assert `--no-portal` prints the skip line and generates no file; assert a config default (if added) is honored. |
| R1-F6 | Data | high | FR-5 MUST pin the slug function and define rename semantics: state that the slug is derived by `{named function/ref}`, that a slug collision between two distinct projects is detected (not silently overwritten), and that a project *rename* either re-points the same board or is called out as orphaning the prior UID (index-stale). | FR-5's "stable UID" hides two real failure modes — lossy slugification (two projects → one UID → silent clobber) and rename (new UID → orphaned board the index still lists). "Idempotent upsert" is only safe once the slug→UID mapping is 1:1 and rename-aware. | FR-5 (add slug + rename clause); Reference Audit (cite the slug function) | Unit test: two project names that slugify identically → assert a collision error or distinct UIDs; rename a project → assert defined behavior (no orphaned duplicate silently listed by the index). |
| R1-F7 | Interfaces | low | Elevate the "Workbooks carry the `workbook` tag" fact (`portal_spec.py:337`) from an incidental observation into an explicit *invariant* FR-11 depends on: FR-11's self-updating index REQUIRES every generated Workbook to be tagged `workbook`; if that tag is ever made conditional, the index silently under-lists. | The self-updating index is entirely a function of the tag; today it holds by luck of a hard-coded tag, but nothing asserts it as a contract the index relies on. | FR-11 / NR-2 (add dependency note) | Snapshot test: assert `build_kickoff_portal_spec()` output always includes tag `workbook`; wire it as a regression guard. |
| R1-F8 | Security | medium | Add a requirement that provisioning the **portfolio index** (`--index --provision`) to a shared instance require an extra confirmation or allowlist beyond the per-project `--provision`, since the index is a global singleton with portfolio-wide blast radius. | NR-4 treats all `--provision` equally, but mutating a shared portfolio-wide index is higher blast radius than one project board; OQ-7's "auto-upsert the index whenever any Workbook is provisioned" would make this worse. | New NR or FR-11 clause; resolve alongside OQ-7 | Assert index provisioning to a non-loopback URL prompts/requires an allowlist flag; assert OQ-7 auto-upsert (if chosen) never auto-provisions. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Validation | medium | Add an acceptance criterion for FR-4's "panels MUST render cleanly in this empty state" that is *independently testable in this doc*, rather than asserting it "already true" by deferring to the owner doc's static reads. State the check: compile the skeleton spec for a fresh-template project and assert zero panels error / all render "No data" (not a broken query). | FR-4 currently asserts correctness by citation ("already true"); a lifecycle doc that generates the empty board at start should own a smoke check that the empty board it produces is clean, or a regression in the owner doc silently breaks day-1 UX. | FR-4 (add acceptance criterion) | Golden test: generate the Workbook for a project with all-fresh YAMLs; assert the compiled JSON has no panel with an error state and the file validates. |
| R1-F10 | Ops | low | OQ-7 (index generation trigger) should note that whichever trigger is chosen, the index generation MUST be $0/toolchain-gated exactly like FR-6 — i.e. if `--index` is auto-invoked and the toolchain is absent, it degrades identically, and auto-upsert-on-provision (one of the OQ-7 options) does NOT silently re-provision. | OQ-7 lists an "auto-upsert whenever any Workbook is provisioned" option that could couple index generation to every provision and inherit the same toolchain/blast-radius surface without saying so. | OQ-7 (add constraint) | If OQ-7 auto option chosen: assert absent-toolchain path degrades and no unsolicited provision occurs. |

**Endorsements (prior untriaged suggestions this reviewer agrees with):**
- (none — R1 is the first round; no prior untriaged items exist.)

**Disagreements (untriaged prior IDs this reviewer would flag):**
- (none — first round.)
