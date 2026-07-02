# Stakeholder Input Recommendations Implementation Plan

**Version:** 1.2 (Post-CRP — 4-round convergent review triaged)
**Date:** 2026-07-02
**Tracks requirements:** `STAKEHOLDER_INPUT_RECOMMENDATIONS_REQUIREMENTS.md` v0.4
**Status:** Planned (pre-implementation)

---

## 0. Grounding: what the planning pass established

Reading the merged panel + kickoff-input code turned up five facts that reshape the v0.1 draft:

1. **The strict value schemas hold NO per-field provenance.** `business_targets.py` rows allow only
   `{target, why}`; `conventions.py` has a single domain-level `provenance_default` +
   `field_authorship` (a *string*, not per-field); both **reject unknown top-level/row keys** (typo
   guard). ⇒ A per-field `provenance: authored` marker **cannot** live in the strict YAML without a
   schema change. Approval granularity in-file is **domain-level** (`provenance_default`), so
   per-field drafts must be staged **out-of-band** and the strict YAML only ever holds
   parse-clean values.
2. **`PanelAnswer` already carries everything a recommendation needs** — `value_path`, `brief_hash`,
   `roster_version`, `grounding`, `cost_usd`, `flags` (`models.py:214`). ⇒ A recommendation is a
   **thin wrapper** (domain + field + recommended value + disposition) over a `PanelAnswer`; reuse
   the existing paid call, don't fork a new provenance model.
3. **`provenance.py` mints `OBSERVED (project, synthetic)`** — the *reactive* label. A recommendation
   for a blank field is an **`estimate`**, a different provenance tier; it must **not** go through
   `provenance.py`. ⇒ FR-KIR-5 needs a distinct, simpler `estimate` marker path.
4. **`vipp_bridge.consult_panel` is the exact template** for the pass: flatten targets → `route()`
   → `preflight_budget()` → per-item `panel.ask()` → status-tagged advisories (`no-stakeholder` /
   `deferred` / `unavailable` / `answered`). ⇒ The drafting pass is a **sibling module** with the
   same shape and reuses `routing.route`, `panel.preflight_budget`, `panel.ask`.
5. **`cli_panel.py import` already establishes CLI-as-writer** with an atomic tmp+rename write, a
   clobber guard, `looks_generated` detection, and distinct exit codes. ⇒ Approval-writes reuse this
   exact machinery; the round-trip gate reuses the `ingest.py` gate pattern.

Also: the **grounding guard** (`grounding_guard.py`) flags "unsupported-specifics" — for a drafted
starter, specifics the brief doesn't literally contain are *expected*, so the reactive guard is the
**wrong** check here (FR-KIR-6).

---

## 1. Module layout

Extend `src/startd8/stakeholder_panel/` (keep the panel the single home; no new package):

| File | Responsibility | Requirements |
|------|----------------|--------------|
| `input_domains.py` (new) | The supported-domain registry: for each of `business-targets`/`conventions`/`build-preferences` (observability **excluded** — no strict parser, `config-default` not `estimate`; NR-KIR-7), its strict parser, its **owning role** (default map), and a **field-enumerator** that yields `(value_path, current_value, is_unfilled)` from a domain YAML + template | FR-KIR-2, FR-KIR-3, FR-KIR-6 (field selection) |
| `recommend.py` (new) | The proactive pass `recommend_inputs(package, panel, *, domains, cap)` — mirrors `vipp_bridge.consult_panel`: enumerate unfilled fields → route to owning persona → budget preflight → `panel.ask` a *drafting* prompt → return `Recommendation` records | FR-KIR-1, FR-KIR-4, FR-KIR-12, FR-KIR-13, FR-KIR-14 |
| `models.py` (extend) | Add `Recommendation` (frozen): `domain`, `value_path`, `recommended_value`, `why`, `disposition`, wrapping a `PanelAnswer`; `to_dict`/`from_dict` | FR-KIR-4, FR-KIR-5 |
| `recommend_provenance.py` (new, or fold into `recommend.py`) | Wrap a recommendation into an **`estimate`** starter with a `panel:<role_id>` origin marker — distinct from `provenance.py`'s synthetic-OBSERVED path | FR-KIR-5, FR-KIR-7 |
| `proposals.py` (new) | The out-of-band **staging artifact** (`.startd8/stakeholder-panel/proposals-<session>.json`, `0600`, `sort_keys`+`indent=2`): per-field recommendation + disposition + provenance; the promote-on-approve reader + the read-latest/stale-filter helpers; a `gc_stale_proposals(keep=N)` step run on `recommend` so sessions don't leak (mirrors the panel's `prune_sessions`, **R2-S3**) | FR-KIR-7, FR-KIR-8, FR-KIR-12, OQ-KIR-1/2 |
| `cli_panel.py` (extend) | `startd8 panel recommend`/`review`/`approve`/`reject`. **`approve` writes via `kickoff_experience.capture.apply_capture`** (comment-preserving splice + strict gate), **not** `cli_panel.import` (**R2-S1**); `--session`/`--all` (R1-F2/R1-S2) | FR-KIR-8, FR-KIR-9, FR-KIR-10, FR-KIR-11, FR-KIR-14 |

## 2. Persona↔domain routing (FR-KIR-3)

- A **default role→domain table** in `input_domains.py`:
  `{business-targets: "product-owner", conventions: "architect", build-preferences: "pm"}`
  (conventional roster `role_id`s; observability excluded per NR-KIR-7).
- Resolution order: (1) exact owning-role match on the roster; (2) `answers_for`/`route()` heuristic
  against the domain's field `value_path`s; (3) **no match ⇒ skip the domain** (FR-KIR-3 — never
  drafted by a non-owner). The mapping is **advisory routing, never a security boundary** (matches
  the panel's existing `answers_for` note).
- The table is overridable but not a new required roster field in v1 (keeps `stakeholders.yaml`
  schema untouched — resolves OQ-KIR-3 toward "fixed table + heuristic fallback").

## 3. The drafting pass (FR-KIR-1)

`recommend_inputs(package_root, panel, *, domains=None, cap=None) -> RecommendationRun`, wrapped in a
parent OTel span `stakeholder.recommend_pass` (aggregates `total_cost_usd`/`fields_enumerated`/
`fields_drafted`; the per-`panel.ask` spans nest under it — **R4-S3**):

1. **Enumerate unfilled fields.** `is_unfilled` = absent OR a `<placeholder>` OR template-sentinel
   `estimate`. **Every enumerated field is validated against the domain's strict schema** so we never
   draft a field the round-trip gate will reject (**R1-S3**, accept-in-part): for *fixed-key* domains
   (conventions `data_model` enums, build-preferences keys) the strict model bounds the candidates;
   for *open-vocabulary* domains (`business-targets` metric rows are author-defined `Dict[str,Target]`)
   the **template placeholders** remain the candidate source — the strict model cannot enumerate open
   keys. **Skip fields that already carry a pending `draft`** in the latest staging artifact, and
   **skip fields now populated directly in the YAML** (stale-draft filter) — a re-run with everything
   drafted costs $0 unless `--redraft` (**R2-S2 / R3-S3**). Composite metric rows are enumerated as
   **one item per row** (`<metric>` → structured `{target, why}`), not per scalar leaf (**R4-S1/FR-KIR-4**).
2. **Resolve owners, then budget-preflight.** Resolve each field's owning persona (bounded fallback,
   skip on no-confident-owner) **first**; the preflight count is **exactly the number of fields with a
   resolvable, present owner** — preflighting *before* filtering would overestimate cost and falsely
   deny a within-budget run (**R3-S1**). On denial, defer everything, spend nothing.
3. For each owned field, `panel.ask(owner_role, drafting_prompt, value_path=field)`. The prompt frames
   it as *"recommend a starter value for this field from your role; it's a draft a human will confirm"*
   — an **estimate request**, not a fact assertion; a composite row asks for the full `{target, why}`
   dict in one structured response. Untrusted context (existing project prose) is fenced as DATA, per
   the `vipp_bridge` prompt discipline.
4. Wrap each `PanelAnswer` into a `Recommendation` (`estimate` provenance, `panel:<role_id>` marker);
   `unavailable`/`deferred`/`no-owner` fields are recorded with that status and **left unchanged**
   (FR-KIR-13).
5. Persist all recommendations to the staging artifact (`proposals.py`) and the panel transcript
   (FR-KIR-14). Return the run for CLI rendering.

**Grounding for recommendations (FR-KIR-6).** Do **not** run the reactive `grounding_guard`
unsupported-specifics check. Mark each recommendation `grounding = estimate-not-grounded` (a new
`Grounding` member or a `Recommendation`-level field), and run only a **contradiction check**: flag
a recommendation that conflicts with a stated brief goal/constraint.

## 4. Provenance & approval (FR-KIR-5, FR-KIR-7, OQ-KIR-2)

- **Staging (out-of-band).** Because the strict YAML can't hold per-field provenance (§0.1), drafts
  live in `proposals-<session>.json`, **serialized deterministically** (`sort_keys=True`, `indent=2`)
  so it diffs cleanly in git — it is the sole per-field audit trail (**R2-S4**). Each entry =
  `{domain, value_path, recommended_value, why, role_id, brief_hash, roster_version,
  provenance: "estimate", origin: "panel:<role_id>", disposition: draft|approved|rejected|invalid,
  cost_usd}`.
- **`panel review`** renders drafts with the FR-KIR-9 anti-anchoring banner (brief + field + gap),
  **filters stale drafts** (field now filled in the YAML → hidden, **R3-S3**), and **warns on roster
  drift** (staged `roster_version`/`brief_hash` ≠ live → "⚠ roster context changed", **R4-F2**); lets
  a human set disposition per field.
- **`panel approve`** promotes `approved`/edited values into the domain YAML. **The writer is
  `kickoff_experience.capture.apply_capture` — NOT `cli_panel.import`'s full-file write** (**R2-S1**,
  verified): `capture.py` does a targeted line-range splice that preserves comments/key-order/blank
  lines, runs the per-field strict round-trip gate (FR-KIR-11), and refuses on a stale on-disk read.
  Because `capture.py` splices **scalars only**, a **composite** metric is applied as **sequential
  `apply_capture` calls** — `<metric>.target` then `<metric>.why` (**R4-S1**); a mid-sequence gate
  failure aborts that metric and marks the staged disposition `invalid` with the parser error
  (FR-KIR-11/R1-F3). On success the staged disposition is updated to `approved` (**R1-S4** — the audit
  trail must not desync). In-file provenance stays domain-level: the written domain keeps
  `provenance_default: estimate` until the human flips the whole domain to `authored`; the SDK never
  auto-flips (FR-KIR-7), and `approve` prints a **manual-flip reminder** when the last pending draft of
  a domain is approved (**R4-S2**).

## 5. CLI surface (FR-KIR-10)

```
startd8 panel recommend [--domain business-targets ...] [--cap N] [--redraft] [--model ...]
    → paid drafting pass; writes staging proposals; prints a summary with the unratified banner
startd8 panel review [--session ...]        → $0, render staged drafts + brief + gap (anti-anchor);
    hides stale drafts (R3-S3); warns on roster drift (R4-F2)
startd8 panel approve [--session <id>] (--field <domain>:<value_path> | --all) [--edit "<value>"]
    → promote one draft (--field) or every `approved` draft (--all, R1-S2) via capture.py splice;
    --session defaults to the latest proposals-*.json, errors if ambiguous (R1-F2);
    --edit is for short scalars only, bare --edit opens $EDITOR, long values → edit the YAML (R3-S2);
    prints the manual provenance_default:authored reminder on the domain's last approval (R4-S2)
startd8 panel reject --field <domain>:<value_path> [--session <id>]   → mark disposition rejected
```

Exit codes reuse `cli_panel.py`'s scheme (2 = bad roster/inputs, 4 = round-trip gate rejection,
5 = clobber refused). `review`/`approve`/`reject` emit decision-funnel telemetry events (FR-KIR-14).

## 6. Testing

- **Unit** — field enumeration (unfilled detection vs real value); role→domain resolution incl.
  no-owner skip; `Recommendation` round-trip; `estimate` provenance never renders as OBSERVED;
  contradiction-check flags a goal-conflicting draft but not a mere unsupported specific.
- **Integration (injected agent factory, no keys)** — full `recommend_inputs` over a fixture package:
  budget preflight (post-resolution count, R3-S1) caps spend; a persona failure leaves its field
  unchanged and doesn't abort; a re-run with everything drafted makes **0 paid calls** (R2-S2); a
  malformed recommendation is rejected at the gate (exit 4) with the parser error surfaced (R1-F3).
- **Comment-preserving writes (R2-S1/R4-S1)** — `approve` on a YAML with `# comments` before/after
  the field leaves both untouched; a **composite** metric splices `.target` **and** `.why` without
  corrupting the file; after `approve` the staging JSON disposition is updated to `approved` (R1-S4).
- **Provenance/audit** — staged draft carries `estimate` + `panel:<role_id>`; the JSON is stable/
  sorted (R2-S4); brief-hash pins the producing revision (panel FR-12 parity); a manual YAML edit
  hides the stale draft from `review` (R3-S3); a roster edit triggers the drift warning (R4-F2).

## 7. Build increments

- **M0** — `input_domains.py` registry + field enumeration (schema-validated + open-vocab template,
  composite-row granularity) + bounded role→domain resolution (no LLM; $0).
- **M1** — `Recommendation` model + `recommend.py` pass (post-resolution preflight, staging-aware
  skip, parent span) + `estimate` provenance + `proposals.py` staging (sorted JSON + GC + stale
  filter) (injected-factory tested).
- **M2** — CLI `recommend`/`review`/`approve`/`reject`; **`approve` via `capture.py`** (comment-safe
  splice, composite → sequential scalar splices) + `--session`/`--all` + gate-error surfacing.
- **M3** — contradiction-only grounding, budget/cap wiring, parent+child OTel + decision-funnel
  events, roster-drift + manual-flip hints, docs.

---

*Plan v1.2 — Post-CRP. Triaged 4 convergent-review rounds: **13 of 14** plan suggestions applied,
1 rejected (R1-S1, superseded by R2-S1). Keystone: `panel approve` writes via the verified
comment-preserving `kickoff_experience/capture.py` splice (R2-S1/R4-S1), not a full-file rewrite;
post-resolution budget preflight (R3-S1); staging-aware no-re-spend enumeration (R2-S2); `--all`/
`--session` CLI (R1-S2/R1-F2). Dispositions in Appendix A/B. v1.1 dropped observability (Leg 6
#12/#16); `estimate` path stays in its own module (Leg 6 #13).*

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
| R1-S2 | `--all` batch mode on `panel approve` | R1 | Applied → §4/§5 | 2026-07-02 |
| R1-S3 | Enumerate/validate against strict schema, not a separate template | R1 | Applied-in-part → §3 step 1. Kept template as candidate source for **open-vocab** `business-targets` metric rows (strict model has open keys); validate all against the schema | 2026-07-02 |
| R1-S4 | Test that `approve` updates staging JSON to `approved` | R1 | Applied → §6 | 2026-07-02 |
| R2-S1 | Use `capture.apply_capture` (comment-preserving) for approve, not `cli_panel.import` | R2 | Applied → §1/§4/§7. **Verified** `capture.py` (splice + round-trip + stale guard). Supersedes R1-S1 | 2026-07-02 |
| R2-S2 | Enumerator reads latest staging; skip pending-draft fields (no re-spend) | R2 | Applied → §3 step 1 | 2026-07-02 |
| R2-S3 | GC stale `proposals-*.json` (keep N) | R2 | Applied → §1 `proposals.py` (`gc_stale_proposals`, mirrors `prune_sessions`) | 2026-07-02 |
| R2-S4 | Staging JSON sorted keys + `indent=2` | R2 | Applied → §4 | 2026-07-02 |
| R3-S1 | Move budget preflight after role resolution; count = owned fields | R3 | Applied → §3 step 2 | 2026-07-02 |
| R3-S2 | Redesign `--edit`; lean on manual YAML edit / `$EDITOR` | R3 | Applied → §5 | 2026-07-02 |
| R3-S3 | Stale-proposal filter (field now filled in YAML → hidden) | R3 | Applied → §3/§4 | 2026-07-02 |
| R4-S1 | Composite fields → sequential scalar `apply_capture` (`.target`,`.why`) | R4 | Applied → §4/§6 (capture.py is scalar-only, verified) | 2026-07-02 |
| R4-S2 | CLI hint to manually flip `provenance_default: authored` on last approval | R4 | Applied → §4/§5 | 2026-07-02 |
| R4-S3 | Parent OTel span `stakeholder.recommend_pass` | R4 | Applied → §3 (+ FR-KIR-14) | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S1 | Extract `cli_panel.import`'s atomic tmp+replace writer into a shared util for `panel approve` | R1 | **Superseded by R2-S1.** For value inputs the writer is `capture.py`'s comment-preserving line-splice, **not** a full-file atomic replace (which strips comments — SOTTO). The roster atomic writer is never reused for kickoff YAMLs, so there is nothing to extract. R2 itself flagged this supersession in its endorsement. | 2026-07-02 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — gpt-5.5-extra-high — 2026-07-02

- **Reviewer**: gpt-5.5-extra-high
- **Date**: 2026-07-02 21:08:00 UTC
- **Scope**: First pass architectural review across both plan and requirements, focused on the 5 areas in the focus file + phantom reference audit.

**Executive summary**
- **Provenance:** The pre-flight provisioning score must remain strictly tied to the in-file `provenance_default` (safe under-reporting) rather than coupling core logic to transient JSON files.
- **Round-trip gate:** Reusing `cli_panel.import` for atomic writes is architecturally unsafe since it is a Typer command mapped to `ingest()`; the underlying atomic write utility must be extracted.
- **UX/Ops:** `panel approve` needs a `--session` argument to locate the staging file, and an `--all` flag to prevent forcing users to run the command 20 times for 20 fields.
- **Phantom Reference Audit:** `looks_generated` lives in `stakeholder_panel.ingest`, not `cli_panel` as stated in the requirements §6.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Extract the atomic write (tmp + `os.replace`) and clobber guard from `cli_panel.py:panel_import` into a shared utility (e.g., in `cli_shared.py`), and have `panel approve` call that utility. | The plan says "via the atomic write from `cli_panel.import`". `cli_panel.import` is a Typer command that hardcodes calling `ingest()` for rosters. It cannot be reused directly for kickoff inputs without breaking separation of concerns. | Section 4 "Provenance & approval" and Section 7 "Build increments" (M2) | Unit test the extracted utility directly; ensure `panel approve` does not import `panel_import`. |
| R1-S2 | Interfaces | medium | Add an `--all` (or `--all-approved`) flag to `panel approve` to batch-promote all approved drafts from the staging artifact in one command. | Requiring users to run `panel approve --field <domain>:<value_path>` individually for a domain with 15+ fields is severe friction and defeats the proactive UX. | Section 5 "CLI surface" | `panel approve --all` processes a staging JSON with 3 approved fields and updates the YAML once. |
| R1-S3 | Data | medium | Clarify in Section 3 Step 1 that the "field-enumerator" uses the Pydantic models (the strict schemas) as the source of truth to identify absent fields, rather than a separate "template" file. | Hardcoding a template file to discover what fields *could* exist risks drifting from the strict schema, leading to recommendations that the strict gate will reject. | Section 3 "The drafting pass" | Enumerator yields exactly the fields defined in `BusinessTargetsManifest` etc. |
| R1-S4 | Validation | medium | Add an explicit test asserting that after a successful `panel approve`, the staging artifact (`proposals-<session>.json`) is updated to reflect `disposition: approved` for the promoted fields. | The staging JSON acts as the out-of-band audit trail for per-field `authored` status (FR-KIR-7). If it is not updated post-write, the audit trail is permanently out of sync. | Section 6 "Testing" | E2E test running `approve` and checking the JSON file state. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None — first round.

#### Review Round R2 — claude-3-7-sonnet — 2026-07-02

- **Reviewer**: claude-3-7-sonnet
- **Date**: 2026-07-02 21:10:00 UTC
- **Scope**: Second pass prioritizing gap-hunting, cross-cutting concerns (Mottainai/P-A), and platform leverage against the live codebase (specifically `capture.py`).

**Executive summary**
- **Comment destruction risk:** Promoting drafts into YAML using standard dump/write patterns (as implied by `cli_panel.import` reuse) will obliterate human comments. `panel approve` must leverage the `kickoff_experience/capture.py` line-range splice engine.
- **Duplicate LLM spend:** Because drafts live out-of-band, the strict YAML remains "unfilled". Consecutive `panel recommend` runs will re-draft the same fields endlessly unless the field enumerator consults the staging artifact.
- **Staging file leakage:** Generating `.startd8/stakeholder-panel/proposals-<session>.json` files without a garbage collection policy will pollute the developer's disk.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | critical | Replace the planned use of `cli_panel.import`'s atomic write for `panel approve` with `kickoff_experience.capture.apply_capture()`. The plan says it "promotes approved values... via the atomic write from `cli_panel.import`", but standard YAML serialization strips all comments. `capture.py` already implements a "targeted line-range splice" to preserve comments + strict round-trip gating + stale-read clobber protection. | Platform leverage (P-A): `capture.py` is the authoritative, comment-safe writer for value inputs. Rebuilding this capability or wiping human comments in the domain YAML violates the SOTTO principle. | Section 4 "Provenance & approval" | Unit test: `panel approve` on a field leaves surrounding `# comments` in the domain YAML untouched. |
| R2-S2 | Ops | high | Extend `recommend_inputs` step 1 (field enumeration) to read the most recent `proposals-*.json` staging artifact. Treat fields that already have a pending `draft` disposition as "filled", skipping them unless `--redraft` is passed. | Mottainai (waste aversion): Since drafts live out-of-band (FR-KIR-7), the strict YAML remains blank. Without checking the staging file, repeated `panel recommend` runs will wastefully re-draft the same fields. | Section 3 "The drafting pass" | Test: running `recommend` twice without `--redraft` makes 0 paid calls on the second run, reporting fields as already drafted. |
| R2-S3 | Ops | medium | Add a garbage collection step (`gc_stale_proposals`) that runs during `panel recommend` to keep only the N most recent (or unresolved) `proposals-<session>.json` files in `.startd8/stakeholder-panel/`. | The plan introduces a new session-based out-of-band artifact but specifies no lifecycle bounds. This will permanently leak files into the project directory on every run. | Section 1 "Module layout" (`proposals.py`) | Test: after N+1 sessions, the oldest staging file is automatically deleted. |
| R2-S4 | Data | low | Specify that `proposals-<session>.json` must be written with sorted keys and stable formatting (`indent=2`). | This file is the authoritative audit trail for per-field provenance. It must be human-readable and cleanly diffable in version control to support compliance audits. | Section 4 "Provenance & approval" | Output artifact is predictably formatted and structurally stable across sequential additions. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: Extracting the atomic write utility is necessary, but R2-S1 supersedes this for *value inputs* by routing to `capture.py`.
- R1-S2: `--all` flag on `approve` is critical for usability.

#### Review Round R3 — claude-4.6-sonnet-max-thinking — 2026-07-02

- **Reviewer**: claude-4.6-sonnet-max-thinking
- **Date**: 2026-07-02 21:13:00 UTC
- **Scope**: Third pass — testing plan coherence, fallback behavior, session isolation, and UX continuity.

**Executive summary**
- **Orphaned proposals handling:** If a user edits the YAML manually while drafts sit in `.startd8/stakeholder-panel/`, the staging file holds stale recommendations for fields that are no longer absent. S1 needs to filter out proposals for fields that are now filled in the YAML.
- **`--edit` UX limits:** Using `--edit "<value>"` on the CLI for complex strings (or future nested types) is error-prone. We should define an interactive editor fallback or explicit instruction for users to edit the YAML manually and then flip `provenance_default` when done.
- **Budget preflight overestimation:** If the enumerator queues N fields, but some personas are missing from the roster, preflighting N is an overestimation that might reject a run that would actually cost less. Preflight must be after the role-resolution step.
- **Role resolution fallback conflict:** If the default role for `business-targets` is `product-owner`, but `product-owner` is absent and `route()` resolves `business-targets` fields to an unrelated persona (e.g. `engineer` because they happened to answer an OMIT claim with a similar symbol before), the output quality drops.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Architecture | high | Move the budget preflight (S3.2) *after* role resolution and absent-role filtering (S3.1), and calculate the preflight count as exactly the number of fields that have a resolvable, present owner. | Preflighting *before* filtering out un-owned or missing-persona fields will overestimate the cost, potentially denying runs that are actually within budget. The plan text in Section 3 implies this ordering ("For each supported domain with a resolvable owner... Budget preflight over the whole paid set"), but it must be unambiguous. | Section 3 "The drafting pass" | Unit test: 10 fields total, 6 owned by absent personas, cap=5. Preflight accepts the run (4 < 5). |
| R3-S2 | Interfaces | medium | Redesign the `--edit "<value>"` flow in `panel approve` (S5). For complex strings (like a paragraph-long `why` rationale), passing it via shell argument is hostile. Instead, `panel approve` should offer an interactive prompt (e.g., `typer.prompt` or launching `$EDITOR`) when `--edit` is passed without a value, or drop `--edit` and rely on `panel review`'s anti-anchoring banner to guide manual YAML editing. | SOTTO principle: avoid building complex CLI input machinery when the user's IDE/editor is right there. If they need to heavily edit a recommendation, they should just edit the YAML. | Section 5 "CLI surface" | `panel approve --edit` opens an interactive prompt or instructions, rather than failing for missing string argument. |
| R3-S3 | Data | medium | Add a "stale proposal" filter to `recommend.py` and `panel review`. If `proposals-<session>.json` contains a draft for `business-targets.retention`, but that field is now populated in `business-targets.yaml` (because a human edited the file directly), the draft should be marked `stale` or hidden. | The out-of-band staging artifact easily drifts from the source-of-truth YAML. Showing drafts for fields the user already manually filled is confusing and risks clobbering their work if they blindly `approve --all`. | Section 1 "Module layout" and Section 4 "Staging" | Test: `panel review` hides drafts for fields where `is_unfilled()` is now false. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S3: Relying on the strict Pydantic models for field enumeration is safer than separate templates.
- R2-S1: Using `capture.py` instead of `cli_panel.import` is critical to save comments.
- R2-S2: Skipping fields with pending drafts prevents duplicate spend.

#### Review Round R4 — claude-opus-4-8-thinking-high — 2026-07-02

- **Reviewer**: claude-opus-4-8-thinking-high
- **Date**: 2026-07-02 21:16:00 UTC
- **Scope**: Final polish — `capture.py` scalar limitations, composite field handling, roster drift warnings, CLI hints for provenance manual flips, and decision funnel telemetry.

**Executive summary**
- **Composite fields vs `capture.py`:** R2-S1 correctly mandated `capture.py` to preserve comments, but `capture.py` only splices *scalars*. `business-targets.yaml` requires inserting `{target, why}` dicts. `panel approve` must translate a composite draft into multiple scalar splices.
- **Decision funnel telemetry:** The drafting pass is tracked, but if `panel approve` and `panel review` don't emit events, the human half of the decision funnel is dark.
- **Roster drift:** Staged drafts contain `roster_version` and `brief_hash`, but nothing specifies checking them during review/approve. Stale drafts should warn the user.
- **Manual provenance flip hint:** Since the SDK never auto-flips `provenance_default` to `authored`, users need a CLI nudge when they finish approving a domain.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Architecture | high | Define how `panel approve` handles composite fields (like `business-targets` `{target, why}`) when using `capture.py`. Since `capture.py` is strictly a scalar line-range splicer, `recommend.py` must ask the LLM for a structured JSON response (target + why), and `panel approve` must issue *two* sequential `apply_capture` calls (`metric.target` and `metric.why`), or `capture.py` must be upgraded. | The R2-S1 pivot to `capture.py` saves comments but breaks if `panel approve` tries to pass a Python dict into a scalar line splicer. | Section 4 "Provenance & approval" and Section 6 "Testing" | Unit test: `panel approve` on a `business-targets` field successfully updates both the `.target` and `.why` child scalars without corrupting the YAML. |
| R4-S2 | Interfaces | medium | Add a CLI hint in `panel approve`: if the user approves the last pending draft for a domain, print "All drafts approved. To count this towards readiness, manually edit the YAML to set `provenance_default: authored`." | Because the SDK explicitly refuses to auto-flip in-file provenance (FR-KIR-7), users will assume approving via CLI makes the file "ready", leading to confusing under-reported scores. | Section 5 "CLI surface" | `panel approve --all` prints the manual-flip reminder for the affected domains. |
| R4-S3 | Ops | medium | Wrap the `recommend_inputs` pass in a parent OTel span (e.g., `stakeholder.recommend_pass`) that aggregates `total_cost_usd`, `fields_enumerated`, and `fields_drafted`. | The individual `panel.ask` child spans will be orphaned or lack overarching context without a parent span summarizing the batch operation's cost and scale. | Section 3 "The drafting pass" | Trace inspection shows `panel.ask` spans correctly nested under `stakeholder.recommend_pass`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-S1: Preflighting after role enumeration prevents false budget rejections.
- R3-S2: The `--edit` shell flag is terrible UX for large strings; leaning into manual YAML edits is better.
- R3-S3: Stale proposal filtering keeps the staging file honest.

## Requirements Coverage Matrix — R4

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-KIR-1 (Proactive recommendation) | Section 3 | Full | — |
| FR-KIR-2 (Supported input domains) | Section 1, 2 | Full | — |
| FR-KIR-3 (Persona↔domain routing) | Section 2, 3 | Partial | Heuristic ownership assignment logic slightly ambiguous; lacks strict bounds on fallback. |
| FR-KIR-4 (Field-level recommendations) | Section 1, 3 | Partial | `value_path` granularity for composite fields (like `{target, why}`) is undefined (R4-F1). |
| FR-KIR-5 (Estimate vs OBSERVED) | Section 1, 3, 4 | Full | — |
| FR-KIR-6 (Grounding-guard semantics) | Section 3, 6 | Full | — |
| FR-KIR-7 (Provenance carry-through) | Section 4 | Partial | OQ-KIR-7 (provisioning score behavior) needs resolution to confirm YAML-only dependency; stable JSON formatting missing. |
| FR-KIR-8 (Two dispositions) | Section 4 | Partial | Stale draft eviction missing. |
| FR-KIR-9 (Review renders the gap) | Section 4 | Partial | Roster version/hash drift warning missing (R4-F2). |
| FR-KIR-10 (CLI is the writer) | Section 5 | Partial | `panel approve` lacks `--session`, `--all`, and drift checking (R4-F2). |
| FR-KIR-11 (Strict round-trip gate) | Section 4, 6 | Partial | Schema error surfacing unspecified; composite field splice mapping required for `capture.py` (R4-S1). |
| FR-KIR-12 (Bounded paid fan-out) | Section 3, 6 | Partial | No guard against duplicate spend; preflight occurs before role filtering. |
| FR-KIR-13 (Persona-failure degradation) | Section 3, 6 | Full | — |
| FR-KIR-14 (Cost/telemetry reuse) | Section 3 | Partial | Human decision funnel events missing (R4-F3). |

