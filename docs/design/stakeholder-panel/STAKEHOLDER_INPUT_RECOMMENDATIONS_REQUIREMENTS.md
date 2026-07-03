# Stakeholder Input Recommendations Requirements

**Version:** 0.4 (Post-CRP — 4-round convergent review triaged)
**Date:** 2026-07-02
**Status:** Draft
**Codename (proposed):** *Teian* (提案, "proposal/suggestion") — the proactive drafting mode of the
Stakeholder Panel. Descriptive name used throughout: **Stakeholder Input Recommendations**.
**Extends:** [`STAKEHOLDER_PANEL_REQUIREMENTS.md`](STAKEHOLDER_PANEL_REQUIREMENTS.md) v0.3 (the
reactive OMIT-fallback oracle) and the kickoff input package
([`../kickoff/KICKOFF_INPUT_PACKAGE_GUIDE.md`](../kickoff/KICKOFF_INPUT_PACKAGE_GUIDE.md)).
**Companion plan:** `STAKEHOLDER_INPUT_RECOMMENDATIONS_PLAN.md` v1.2.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 (post-planning). The planning pass read the
> merged `stakeholder_panel/` + `kickoff_inputs/` code and overturned five assumptions.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Approval could stamp a per-field `provenance: authored` marker into the value YAML | The strict schemas hold **only a domain-level `provenance_default`** and **reject unknown keys** (`business_targets.py` rows = `{target, why}` only; `conventions.py` = one `provenance_default`) | **FR-KIR-7 reshaped**: per-field provenance is impossible in-file → drafts **stage out-of-band**; the strict YAML only ever holds parse-clean values; in-file approval is **domain-level** |
| A recommendation reuses the reactive `provenance.py` synthetic-`OBSERVED` wrap | `provenance.py` mints `OBSERVED (project, synthetic)` — the wrong tier; a blank-field starter is an **`estimate`**, not an observation | **FR-KIR-5 firmed**: distinct `estimate` marker path, never `provenance.py` |
| The recommendation needs a new result model | `PanelAnswer` already carries `value_path`/`brief_hash`/`roster_version`/`grounding`/`cost`/`flags` | **FR-KIR-4 narrowed**: `Recommendation` is a **thin wrapper** over `PanelAnswer` (domain+field+value+disposition); reuse the paid call |
| The existing grounding guard applies to recommendations | The guard flags "unsupported-specifics" — but a drafted starter's specifics are *expected* not to be in the brief | **FR-KIR-6 firmed**: skip the reactive guard; run a **contradiction-only** check (flag drafts that conflict with a brief goal/constraint) |
| A drafting pass is a new construct | `vipp_bridge.consult_panel` is the exact template (flatten → `route()` → `preflight_budget` → `ask` → status-tagged results); `cli_panel.import` is the CLI-as-writer + atomic-write + round-trip-gate template | **FR-KIR-1/10/11 firmed** as *reuse*, not new machinery |

**Resolved open questions:**
- **OQ-KIR-1 → Out-of-band staging.** Drafts land in `.startd8/stakeholder-panel/proposals-<session>.json`
  (`0600`), not the strict YAML; `panel approve` promotes an approved value into the domain YAML
  through the strict gate. (The strict schema can't represent a mixed drafted/approved domain in-file.)
- **OQ-KIR-2 → Domain-level in-file, per-field out-of-band.** In-file provenance is the domain
  `provenance_default`; per-field `authored` status lives in the staging artifact's audit trail. The
  SDK never auto-flips a domain to `authored` (FR-KIR-7).
- **OQ-KIR-3 → Fixed role→domain table + heuristic fallback.** A default table
  (product-owner→business-targets, architect→conventions, pm→build-preferences; observability later
  dropped per NR-KIR-7) with an `answers_for`/`route()` fallback and **skip-on-no-owner**; **no new
  roster field** in v1.
- **OQ-KIR-4 → Reuse `PanelAnswer`, add a thin `Recommendation`.** The `estimate` vs synthetic-OBSERVED
  distinction is carried by the recommendation wrapper/provenance path, not a fork of `PanelAnswer`.
- **OQ-KIR-6 → Draft blank/placeholder fields; `--redraft` for live estimates.** Field selection
  predicate = absent OR `<placeholder>` OR template-sentinel `estimate`; re-drafting real `estimate`s
  is opt-in.

*(OQ-KIR-5 — the interactive-kickoff per-field seam — remains open/deferred; see §5.)*

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK Design-Docs lessons before CRP. Each changed the draft:

- **[Leg 6 #12 — phantom-reference audit]** — `observability` was named as a supported domain with a
  strict round-trip parser, but **no `parse_observability` exists** in `kickoff_inputs/` (only
  `business_targets`/`conventions`/`build_preferences`). **Dropped observability from v1 scope**
  (FR-KIR-2) — and it is architecturally the wrong domain anyway (next bullet). See §6 for the
  full to-be-created / verified reference audit.
- **[Leg 6 #16 — prune phantom scope]** — observability's provenance is **`config-default`** (from
  an industry dataset), and its `owners` block **explicitly has no LLM starter** ("real people can't
  be drafted"). LLM-drafting it contradicts the package model. **Deferred to NR-KIR-7**, not built.
- **[Leg 6 #13 — overloaded-term co-location]** — "provenance" now has two meanings in play: the
  kickoff **`estimate`/`authored`/`config-default`** tier and the FDE **`LabeledClaim` OBSERVED**
  label. The `estimate` recommendation path must live in its **own module** (`recommend_provenance.py`),
  **not** be co-located inside `provenance.py` (which owns the OBSERVED-synthetic meaning). See D-KIR-2.
- **[Leg 1 #5 — single-source vocabulary ownership]** — the `estimate`/`authored`/`config-default`
  vocabulary is **owned by** `KICKOFF_INPUT_PACKAGE_GUIDE.md` §3; the panel safety FRs (FR-16/17/19)
  are **owned by** `STAKEHOLDER_PANEL_REQUIREMENTS.md` v0.3. This doc **cites** them as non-normative
  snapshots and does not redefine them (D-KIR-1).
- **[Leg 6 #11/#15 — fresh-context CRP steering]** — these two docs are the least-reviewed artifacts
  and are the correct CRP target; the panel v0.3 FRs and the package provenance model are **settled,
  do-not-relitigate** memory for the reviewer. Carried into the CRP focus file.

---

## 1. Problem Statement

The Stakeholder Panel (Kaigi) exists today as a **reactive** oracle: when VIPP hits an OMIT during
kickoff-prep evaluation, `consult_panel` routes that single unanswerable question to the relevant
persona and gets back one synthetic advisory. The panel only speaks when *asked about a specific
claim VIPP already surfaced*.

But the kickoff input package (`docs/kickoff/inputs/*.yaml`) starts **mostly empty**. Its own
lifecycle (guide §2, step 2) says every value must be *pre-filled with an LLM-drafted starter,
never blank* — today that pre-fill is a **generic, role-blind LLM pass** (or a hand-authored
template). We already stood up a roster of **role-grounded persona agents**; they are the natural
authors of those starters. The Product Owner persona should draft `business-targets.yaml`; the
Architect persona should draft `conventions.yaml`; the PM/team persona should draft
`build-preferences.yaml`. (Observability is *not* drafted — its values are `config-default` from an
industry dataset, not an LLM `estimate`; see NR-KIR-7.)

The gap: there is no **proactive** panel mode that walks the *applicable, still-blank kickoff input
fields* and asks the persona who owns that domain to **recommend a starter value**, producing a
draft the project team can either **edit/enhance** or **approve as acceptable** — with provenance
kept honest the whole way (`estimate` while drafted; `authored` only on a human decision).

| Component | Current State | Gap |
|-----------|--------------|-----|
| Panel interaction model | Reactive: VIPP asks about one OMIT claim at a time (`vipp_bridge.consult_panel`) | No proactive pass that drafts *kickoff input values* the persona owns |
| Kickoff input pre-fill | "LLM-drafted starter, never blank" — but role-blind (generic pass or template) | No role-grounded drafting; the panel personas that *should* author each domain are unused for it |
| Provenance on drafts | Package model already has `estimate` / `authored` / `config-default` | Panel-drafted values need a distinct, carried-through `estimate` provenance + panel origin marker |
| Human decision surface | `panel ask` prints one synthetic answer; no accept/edit path | No "approve as acceptable" or "use as draft" flow that flips `estimate → authored` |
| Domain ownership | `PersonaBrief.answers_for` (value_path hint) + role-kit role→domain mapping (guide §1) | No explicit persona→input-domain routing for whole-domain drafting |

---

## 2. Scope framing (the bucket separation)

Per `CLAUDE.md`, the SDK does **not** author bucket-4 end-user/company content. Kickoff input
*values* (KPI targets, budgets, conventions, SLO thresholds) sit on the **`estimate` starter**
tier the package model already sanctions: LLM-drafted, never counted as authored, replaced by a
human decision. Teian produces a **better, role-grounded starter** for that same tier — it never
mints an authored fact and never claims the value is real. This is squarely inside the existing
"pre-fill with an LLM starter, provenance `estimate`" discipline (guide §3), just sourced from the
stakeholder personas instead of a generic pass.

---

## 3. Requirements

### A. The drafting pass (proactive mode)

- **FR-KIR-1 — Proactive recommendation pass.** The panel gains a proactive mode: given a project's
  kickoff input package and a live `StakeholderPanel`, it walks the **applicable, unfilled/`estimate`
  fields** of each supported input domain and asks the owning persona to recommend a starter value.
  Mirrors the `vipp_bridge` pattern — a pass invoked *around* the deterministic package, returning
  draft recommendations the caller renders/persists; it never writes an authored value itself.
- **FR-KIR-2 — Supported input domains.** v1 supports the three **value** domains that have a strict
  `kickoff_inputs` round-trip parser and an `estimate` provenance tier: `business-targets`,
  `conventions`, `build-preferences`. **`observability` is excluded** (NR-KIR-7): it has no strict
  parser and its values are `config-default` (industry dataset) with an un-draftable `owners` block.
  The data-model contract, assembly manifests, and content prose (the file-shaped inputs) are **out
  of scope** (NR-KIR-1). `business-targets` is the proving slice (simplest shape).
- **FR-KIR-3 — Persona↔domain routing.** Each supported domain is drafted by the persona who owns
  it, via an explicit role→domain map with a heuristic fallback (reusing `answers_for` /
  `route()`), consistent with the role-kit ownership (Product Owner→business-targets,
  Architect→conventions, PM/team→build-preferences). A domain whose owning
  persona is **absent from the roster** is **skipped** (left to the generic pre-fill / blank), never
  drafted by a non-owning persona. **(v0.4, R3-F1)** The heuristic fallback is **bounded**: it may
  assign a persona only on a **high-confidence** match (an explicit `answers_for` hit for the domain);
  a loose/low-confidence `route()` match does **not** confer ownership — the domain is **skipped**
  instead. For proactive drafting a bad persona fit yields a useless starter, so skipping beats a weak
  match (unlike the reactive OMIT path, where any synthetic answer beats a stall).
- **FR-KIR-4 — Field-level recommendations.** A recommendation targets a specific field
  (`value_path`) in a domain and carries: the recommended value, a short rationale (`why`), the
  answering `role_id`, a grounding signal, and full provenance (brief hash + roster version + cost).
  It is a **thin `Recommendation` wrapper** (`domain` + `value_path` + `recommended_value` +
  `disposition`) over a `PanelAnswer` — the existing answer contract already carries value_path,
  brief hash, roster version, grounding, cost, and flags, so no parallel provenance model is minted.
  **(v0.4, R4-F1) Composite-field granularity.** The enumerator yields the **logical composite field**
  (e.g. a `business-targets` metric row = `product_funnel.<metric>`), **not** its scalar leaves
  (`…​.target`, `…​.why`) — so a metric is drafted in **one** `panel.ask` returning a structured
  `{target, why}`, not two queries per metric (which would double spend and split context).

### B. Provenance & the "estimate, not observed" distinction

- **FR-KIR-5 — Recommendations are `estimate`, never `OBSERVED`.** A recommendation for a
  *still-blank* field is a **starter estimate**, not an observation of project ground truth. It is
  emitted with the package provenance `estimate` and a panel origin marker (`panel:<role_id>`) — it
  is **not** the synthetic-`OBSERVED` claim the reactive OMIT path mints (that path answers about an
  *existing* claim). A Teian recommendation must never be counted as `authored` in any provisioning
  score (guide §3 hard rule).
- **FR-KIR-6 — Grounding-guard semantics for recommendations.** The reactive grounding guard flags
  "unsupported specifics" — an answer asserting a number the brief doesn't contain. For a
  *recommendation*, a specific value the brief doesn't literally contain is **expected**, not a
  defect; the guard must not treat a drafted starter as a fabrication. Instead the recommendation
  carries an explicit "estimate — not grounded in a project fact" grounding, and the guard flags
  only recommendations that **contradict** a stated brief goal/constraint.
- **FR-KIR-7 — Provenance carry-through on approval (domain-level in-file).** The strict value
  schemas hold **only a domain-level `provenance_default`** and reject unknown keys, so a per-field
  `authored` marker **cannot** be written into the YAML (planning discovery §0). Therefore: drafts
  stage **out-of-band** (per-field `estimate` + `panel:<role_id>` origin in the staging artifact);
  `panel approve` promotes an approved/edited value into the domain YAML through the strict gate; the
  domain keeps `provenance_default: estimate` until a human decides to flip the whole domain to
  `authored`. The SDK **never auto-flips** a domain to `authored`; approval is a human,
  at-human-privilege action, and per-field `authored` status is recorded in the staging audit trail.
  **(v0.4, R1-F1 → resolves OQ-KIR-7)** The kickoff **provisioning/pre-flight score depends on the
  in-file `provenance_default` only** — it must **not** read the transient `.startd8/…proposals-*.json`
  staging artifact. A domain scores as `estimate` until a human flips it in-file; **safe
  under-reporting** is preferred to coupling core scoring to a deletable, un-versioned JSON.
  **(v0.4, R2-F3)** The staging artifact is serialized **deterministically** (sorted keys, `indent=2`,
  stable ordering) so it diffs cleanly in version control — it is the sole record of per-field
  `authored` status, so its auditability is a hard requirement.

### C. The human decision surface (draft vs approve)

- **FR-KIR-8 — Two dispositions per recommendation.** Each recommendation supports the two
  outcomes the requester named: (a) **use as draft** — the value lands as an editable `estimate`
  the human then refines (any edit flips to `authored`); (b) **approve as acceptable** — a team
  member accepts the drafted value as-is, flipping it to `authored`. A third implicit outcome —
  **reject/skip** — leaves the field blank/`estimate`. **(v0.4, R3-F3) Stale-draft eviction.** If a
  human has since populated the target field **directly in the domain YAML**, the staged draft for
  that field is treated as **stale (implicitly rejected)** and **hidden** from `panel review` — the
  drafting pass and the review surface both re-check `is_unfilled` against the live YAML so a stale
  draft can never clobber a manual edit via `approve --all`.
- **FR-KIR-9 — Review renders the gap, not just the fill (anti-anchoring).** Consistent with panel
  FR-19, the review surface presents each recommendation with a persistent "drafted starter,
  unratified" banner, the persona brief adjacent, the domain field it fills, and the rationale — so
  a human approves against the *decision they own*, not a persuasive pre-fill. **(v0.4, R4-F2)
  Roster-drift warning.** `panel review`/`approve` compare the staged `roster_version` + `brief_hash`
  against the **live** roster; if they differ, a "⚠ roster context has changed since this draft"
  warning is shown (the hashes are already carried on the `Recommendation`; they are load-bearing only
  if the CLI checks them).
- **FR-KIR-10 — CLI is the writer.** The recommendation review/approve surface is a CLI command
  (extending `startd8 panel …`, the only spend-authorized + write-authorized path per panel NR-7).
  The `$0` Concierge read floor is not an appropriate host for a paid drafting pass or a write.
  **(v0.4, R1-F2)** `panel approve` takes an explicit **`--session`** (defaulting deterministically to
  the latest `proposals-*.json`, erroring cleanly if several exist and none is named) and an
  **`--all`** batch mode (promote every `approved` field in one invocation — per-field approval of a
  15-field domain is unacceptable friction). **(v0.4, R3-F2)** For **complex/long** values (e.g. a
  paragraph `why`), the intended path is **editing the domain YAML directly** guided by the review
  banner; the `--edit "<value>"` flag is for short scalars only, and a bare `--edit` may open `$EDITOR`
  rather than force a hostile shell-quoted string.

### D. Validation & safety (inherited from the panel)

- **FR-KIR-11 — Strict, comment-preserving round-trip gate.** A drafted value written into a domain
  YAML must parse cleanly through that domain's strict `kickoff_inputs` parser
  (`parse_business_targets`, `parse_conventions`, `parse_build_preferences`); a value that would
  produce a malformed file is rejected — never silently written. **(v0.4, R2-F1 → verified) The write
  must preserve human comments/structure**: `panel approve` reuses `kickoff_experience/capture.py`
  (`apply_capture` — targeted line-range splice + per-field round-trip gate + stale-read clobber
  protection), **not** a full-file `yaml.dump` rewrite (which strips comments and reorders keys,
  violating SOTTO). Because `capture.py` splices **scalars only**, a composite metric (FR-KIR-4) is
  applied as **sequential scalar splices** (`<metric>.target`, `<metric>.why`) — see plan §4/R4-S1.
  **(v0.4, R1-F3)** On gate rejection the **exact parser error** is surfaced to the CLI and the
  staged disposition is marked **`invalid`** (never silently swallowed), so a hallucinated shape is
  debuggable.
- **FR-KIR-12 — Bounded paid fan-out (no wasted re-spend).** The pass reuses the panel budget
  preflight + cap (panel FR-17): a configurable max-recommendations cap, aborting/degrading *before*
  spend; beyond the cap, remaining fields are "deferred (budget)". "`$0` unless opted in" must not
  become "unbounded once opted in." **(v0.4, R2-F2 — Mottainai)** Because drafts stage **out-of-band**
  (the strict YAML stays blank), the field enumerator must **consult the latest staging artifact** and
  **skip fields that already carry a pending `draft`** — a second `panel recommend` with everything
  already drafted costs **$0 / zero personas** unless `--redraft` is passed.
- **FR-KIR-13 — Persona-failure degradation.** A persona error/timeout/refusal during the pass
  leaves the target field **unchanged** (blank/`estimate`), never fabricates a value, never aborts
  sibling recommendations or the pass, and cost-tracks any partial spend (panel FR-16).
- **FR-KIR-14 — Cost / telemetry / transcript reuse.** Every recommendation is a tracked LLM call
  (role_id + session_id attribution, panel FR-13), emits the panel's OTel span contract (FR-14),
  and is persisted to the panel transcript (FR-12) so it is auditable and re-readable without
  re-spending. **(v0.4, R4-S3)** The whole pass is wrapped in a **parent span**
  (`stakeholder.recommend_pass`, aggregating `total_cost_usd` / `fields_enumerated` / `fields_drafted`)
  under which the per-`panel.ask` child spans nest. **(v0.4, R4-F3)** The **human decision half** of
  the funnel is instrumented too: `panel review`/`approve`/`reject` emit distinct events
  (`recommendation_reviewed` / `_approved` / `_rejected`, with `domain` + `role_id`) so the funnel is
  not dark in dashboards.

---

## 4. Non-Requirements

- **NR-KIR-1 — Not file-shaped inputs.** The data-model contract (`schema.prisma`), assembly
  manifests (`pages.yaml`, `views.yaml`, …), and content prose are out of scope — those have their
  own generators/lifecycles. Teian drafts **value** inputs only.
- **NR-KIR-2 — Not autonomous authoring.** The panel drafts and recommends; it never writes an
  `authored` value, never approves its own drafts, and never bypasses the human decision (panel
  NR-2, FR-11/FR-18).
- **NR-KIR-3 — Not real end-user/company content (bucket 4).** Teian produces `estimate` starters,
  not the company's real KPIs/copy. Approval by a team member is what makes a value real.
- **NR-KIR-4 — Not a new panel/persona/provider construct.** Reuses the existing
  `stakeholder_panel/` module, `StakeholderPanel`, personas, cost/telemetry/transcript, budget
  preflight, and routing. No LangChain, no new provider (panel NR-4/NR-5).
- **NR-KIR-5 — Not cross-persona debate.** Personas draft their own domains independently; no
  moderated negotiation in v1 (panel NR-3).
- **NR-KIR-6 — Not a replacement for plan-ingestion-generated conventions.** In production,
  `conventions.yaml` is generated by plan ingestion and validated by the Architect (guide §5). Teian
  drafting conventions is a *prototype/solo-posture* convenience or a starter the Architect reviews,
  never an override of the ingestion path.
- **NR-KIR-7 — Observability is not drafted in v1 (from Leg 6 #12/#16).** `observability.yaml` has
  **no strict `kickoff_inputs` parser**, its values are `config-default` (industry dataset, not an
  LLM `estimate`), and its `owners` block explicitly has no LLM starter. Drafting it would contradict
  the package model. Revisit only if a strict observability parser + a draftable non-owners subset
  are scoped.

---

## 4b. Decisions

- **D-KIR-1 — Single-source vocabulary ownership (Leg 1 #5).** The `estimate`/`authored`/
  `config-default` provenance vocabulary is owned by `KICKOFF_INPUT_PACKAGE_GUIDE.md` §3; the panel
  safety FRs (FR-16/17/19) are owned by `STAKEHOLDER_PANEL_REQUIREMENTS.md` v0.3. This doc cites them
  as non-normative snapshots and never redefines them.
- **D-KIR-2 — Separate module for the `estimate` path (Leg 6 #13).** The recommendation `estimate`
  provenance lives in its own module (`recommend_provenance.py`), not co-located inside `provenance.py`
  (which owns the OBSERVED-synthetic meaning), so a reader never sees two "provenance" meanings in one
  file. Naming reuse and module locality are independent axes of vocabulary hygiene.
- **D-KIR-3 — Reuse over new machinery.** The pass mirrors `vipp_bridge.consult_panel`; the writer
  mirrors `cli_panel.import` (atomic write + round-trip gate + clobber guard). No parallel panel,
  provider, or provenance model is created.

---

## 5. Open Questions

*(OQ-KIR-1, -2, -3, -4, -6 resolved by the planning pass — see §0.)*

- **OQ-KIR-5 (deferred)** — How does Teian relate to the deferred interactive-kickoff per-field
  consumer (panel NR-6/OQ-8)? Is Teian *the* mechanism that fills `not_extracted`/`defaulted` fields
  conversationally, or a separate batch pass? Design seam only; no v1 build. The `Recommendation`
  wrapper carries `value_path`, so a future per-field consumer is not blocked.
- **OQ-KIR-7 → Resolved (R1-F1).** The provisioning/pre-flight score depends on the **in-file
  `provenance_default` only** and does **not** read the staging JSON — a domain scores `estimate`
  until a human flips it in-file. Safe under-reporting over brittle coupling to a transient artifact.
  Folded into FR-KIR-7.

---

## 6. Pre-Implementation Reference Audit (Leg 6 #12)

Every code symbol this spec assumes, marked **exists** (grep-verified) or **to-be-created**. The CRP
reviewer should re-verify against the live code.

| Symbol / path | Status |
|---------------|--------|
| `stakeholder_panel.vipp_bridge.consult_panel` (pass template) | **exists** |
| `stakeholder_panel.routing.route`, `panel.preflight_budget`, `panel.ask` | **exists** |
| `stakeholder_panel.models.PanelAnswer` (value_path/brief_hash/roster_version/grounding/cost/flags) | **exists** |
| `stakeholder_panel.models.Grounding` (enum) | **exists** |
| `stakeholder_panel.provenance` (mints OBSERVED-synthetic) | **exists** |
| `kickoff_inputs.parse_business_targets` / `parse_conventions` / `parse_build_preferences` | **exists** |
| `kickoff_inputs.parse_observability` | **absent → domain excluded (NR-KIR-7)** |
| `cli_panel` (clobber guard, exit codes; imports `looks_generated`) | **exists** |
| `stakeholder_panel.ingest.looks_generated` (definition; R1-F5 — not in `cli_panel`) | **exists** |
| `kickoff_experience.capture.apply_capture` / `splice_yaml_value` (comment-preserving **scalar** splice + round-trip gate + stale-read guard) | **exists** — the value-input writer (R2-F1/R2-S1) |
| Roster `role_id`s `product-owner`, `end-user` (template) | **exists**; `architect`/`pm` are **conventional defaults**, not guaranteed on a roster (heuristic fallback + skip covers absence) |
| `Grounding.ESTIMATE`-style member for "estimate — not grounded" | **to-be-created** (or a `Recommendation`-level field) |
| `stakeholder_panel.models.Recommendation` | **to-be-created** |
| `stakeholder_panel.recommend` / `input_domains` / `recommend_provenance` / `proposals` | **to-be-created** |
| `startd8 panel recommend` / `review` / `approve` CLI commands | **to-be-created** |

---

*v0.4 — Post-CRP. Triaged 4 convergent-review rounds (gpt-5.5, claude-3-7-sonnet,
claude-4.6-sonnet, claude-opus-4-8): **12 of 13** requirements suggestions applied, 1 rejected
(R1-F4, superseded by R3-F1). Notable: comment-preserving writes via verified `capture.py` (R2-F1),
composite-field granularity (R4-F1), bounded heuristic fallback (R3-F1), no-re-spend enumeration
(R2-F2), OQ-KIR-7 resolved in-file-only (R1-F1), decision-funnel telemetry (R4-F3). Dispositions in
Appendix A/B. Prior: v0.3 lessons-hardening, v0.2 self-reflective. Companion plan:
`STAKEHOLDER_INPUT_RECOMMENDATIONS_PLAN.md` v1.2.*

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
| R1-F1 | Provisioning score reads in-file `provenance_default` only, not the staging JSON | R1 | Applied → FR-KIR-7 + OQ-KIR-7 resolved (safe under-reporting) | 2026-07-02 |
| R1-F2 | `panel approve` needs `--session` (+ deterministic default) | R1 | Applied → FR-KIR-10 (also `--all`, R1-S2) | 2026-07-02 |
| R1-F3 | Surface exact parser error on gate rejection; mark disposition `invalid` | R1 | Applied → FR-KIR-11 | 2026-07-02 |
| R1-F5 | `looks_generated` lives in `ingest`, not `cli_panel` (§6 fix) | R1 | Applied → §6 reference audit corrected | 2026-07-02 |
| R2-F1 | Comment-preserving writes via `capture.py`, not `yaml.dump` | R2 | Applied → FR-KIR-11. **Verified** `capture.py` exists (line-splice + round-trip + stale guard) | 2026-07-02 |
| R2-F2 | Enumerator skips already-drafted fields; no re-spend unless `--redraft` | R2 | Applied → FR-KIR-12 (Mottainai) | 2026-07-02 |
| R2-F3 | Staging JSON stable/sorted for clean diffs | R2 | Applied → FR-KIR-7 | 2026-07-02 |
| R3-F1 | Bound heuristic fallback; skip domain unless high-confidence owner | R3 | Applied → FR-KIR-3 (supersedes R1-F4) | 2026-07-02 |
| R3-F2 | Lean on manual-YAML edit for complex values; `--edit` for short scalars | R3 | Applied-in-part → FR-KIR-10 (keep `--edit` for scalars, `$EDITOR` for long) | 2026-07-02 |
| R3-F3 | Hide stale drafts when the field was filled directly in YAML | R3 | Applied → FR-KIR-8 | 2026-07-02 |
| R4-F1 | Composite `value_path` granularity — one query per metric row, structured return | R4 | Applied → FR-KIR-4 (+ FR-KIR-11 sequential scalar splices) | 2026-07-02 |
| R4-F2 | Roster-drift warning (compare staged `roster_version`/`brief_hash` to live) | R4 | Applied → FR-KIR-9 | 2026-07-02 |
| R4-F3 | Distinct decision-funnel telemetry events for review/approve/reject | R4 | Applied → FR-KIR-14 | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-F4 | State that a heuristic `route()` match *assigns* temporary ownership | R1 | **Superseded by R3-F1.** R1-F4 makes a loose match confer ownership; R3-F1 (endorsed by R4) instead **bounds** the fallback and **skips** on a weak match — the correct posture for proactive drafting, where a bad persona fit yields a useless starter. Adopting both would contradict. | 2026-07-02 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — gpt-5.5-extra-high — 2026-07-02

- **Reviewer**: gpt-5.5-extra-high
- **Date**: 2026-07-02 21:08:00 UTC
- **Scope**: First pass architectural review across both plan and requirements, focused on the 5 areas in the focus file + phantom reference audit.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | Resolve **OQ-KIR-7** by specifying that the provisioning score must rely *only* on the in-file `provenance_default` (evaluating the domain as `estimate` until explicitly flipped to `authored` by a human), explicitly rejecting reading the out-of-band JSON. | Coupling core provisioning scoring to a transient `.startd8/` staging JSON makes the scoring brittle if the JSON is deleted or un-versioned. Under-reporting progress is safe and pushes users to fully approve domains. | Section 3.B (FR-KIR-7) and Section 5 (OQ-KIR-7) | Ensure the scoring pipeline does not take a dependency on `proposals-*.json`. |
| R1-F2 | Ops | medium | Add `--session <id>` parameter to `panel approve` in **FR-KIR-10**, or define a deterministic default (e.g., latest modified `proposals-*.json`). | `panel review` takes `--session`, but `panel approve` does not. Without it, the CLI cannot reliably locate the correct staging artifact to read drafts from. | Section 3.C (FR-KIR-10) | `panel approve` errors cleanly if no session is specified and multiple staging files exist. |
| R1-F3 | Validation | medium | Strengthen **FR-KIR-11** to explicitly require that if the round-trip gate rejects a drafted value, the specific schema error (e.g., `pydantic.ValidationError`) is surfaced to the CLI and the staging disposition is marked `invalid` (or remains `draft`), never silently swallowed. | The requirement says "rejected/flagged", but debugging LLM hallucinated YAML structures requires exposing the exact schema failure to the user. | Section 3.D (FR-KIR-11) | Recommending a string for an int field yields CLI output showing the strict parser's error message. |
| R1-F4 | Interfaces | medium | Clarify in **FR-KIR-3** that if the heuristic fallback (`route()`) matches a domain to a persona that doesn't explicitly own it in the default map, that persona *becomes* the owner for the drafting pass. | The focus file asks for "no-owner skip... never drafted by a non-owning persona". A heuristic match essentially assigns temporary ownership; this should be stated to avoid contradiction. | Section 3.A (FR-KIR-3) | A persona matched via `answers_for` is treated as the owning role for that field's `panel.ask()`. |
| R1-F5 | Documentation | low | Fix the Phantom Reference Audit table in **§6**: move `looks_generated` from `cli_panel` to `stakeholder_panel.ingest`. | `cli_panel` only imports `looks_generated`; the actual implementation lives in `ingest.py`. Accurate referencing prevents developer confusion. | Section 6 Reference Audit table | Correct the table row. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None — first round.

#### Review Round R2 — claude-3-7-sonnet — 2026-07-02

- **Reviewer**: claude-3-7-sonnet
- **Date**: 2026-07-02 21:10:00 UTC
- **Scope**: Second pass prioritizing gap-hunting, cross-cutting concerns (Mottainai/P-A), and platform leverage against the live codebase (specifically `capture.py`).

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Architecture | critical | Modify **FR-KIR-11** to explicitly require **comment-preserving writes**. Promoting a drafted value into a domain YAML must not strip human-authored comments or alter the file's structure outside the target field. This mandates reusing the `kickoff_experience.capture` splice engine rather than standard `yaml.dump` full-file rewrites. | The strict round-trip gate ensures YAML validity, but full-file overwrites (as suggested by "cli_panel.import") destroy context. Value inputs are highly annotated by users; stripping comments violates the SOTTO principle. | Section 3.D (FR-KIR-11) | Approving a draft against a YAML file containing comments `# before` and `# after` the field preserves both comments perfectly. |
| R2-F2 | Ops | high | Extend **FR-KIR-12** (Bounded paid fan-out) to require that the proactive pass **must not re-spend** on fields that already have a pending `draft` disposition in the latest out-of-band staging artifact, unless explicitly requested (e.g. `--redraft`). | Mottainai: Since the strict YAML remains blank while drafts stage out-of-band, the naive field enumerator will consider the field unfilled and repeatedly pay an LLM to draft it on subsequent runs. | Section 3.D (FR-KIR-12) | A second `startd8 panel recommend` invocation costs $0 and queries 0 personas if all fields already have pending drafts. |
| R2-F3 | Validation | medium | Add acceptance criteria to **FR-KIR-7**: the out-of-band staging artifact (`proposals-<session>.json`) must be serialized with stable sorting and formatting to enable clean version-control diffs. | Because the staging artifact is the *only* place per-field provenance (`authored` vs `estimate`) is recorded, its diffability in `git` is a hard requirement for project auditability. | Section 3.B (FR-KIR-7) | Committing two sequential modifications to the proposals JSON yields a minimal, clean git diff. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: YAML-only provisioning scoring avoids brittle dependencies.
- R1-F2: `--session` tracking in CLI commands connects the loop safely.
- R1-F3: Exposing exact schema errors on rejection is vital for UX.

#### Review Round R3 — claude-4.6-sonnet-max-thinking — 2026-07-02

- **Reviewer**: claude-4.6-sonnet-max-thinking
- **Date**: 2026-07-02 21:13:00 UTC
- **Scope**: Third pass — testing requirements coherence, fallback behavior, session isolation, and UX continuity.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Architecture | high | Strengthen **FR-KIR-3** to require that heuristic fallback (`route()`) must only assign a persona if its confidence is high (e.g. exact `answers_for` match), or explicitly limit fallback to specific roles. The focus file warns: "Routing correctness... heuristic fallback, never drafted by a non-owning persona." If `conventions` falls back to `backend-engineer` instead of `architect`, the starter quality degrades. | The reactive OMIT panel uses heuristic fallback because *any* synthetic answer is better than a crash. For proactive drafting, a bad persona fit produces a useless starter. It is better to skip the domain. | Section 3.A (FR-KIR-3) | If `architect` is missing, `conventions` is skipped rather than assigned to `product-owner` via a loose heuristic match. |
| R3-F2 | Interfaces | medium | Extend **FR-KIR-10** to specify that if a human wants to heavily edit a recommendation, they should edit the domain YAML directly and run a command (or manually update `provenance_default`) to signal approval, rather than fighting a CLI `--edit` flag. | The CLI `--edit` flag is hostile for long strings (like `why` rationales). We should lean into the text editor as the primary UI for complex edits. | Section 3.C (FR-KIR-10) | Documentation/help text for `panel approve` guides users to edit YAML manually for complex changes. |
| R3-F3 | Data | medium | Add acceptance criteria to **FR-KIR-8** / **FR-KIR-9**: If a human manually populates a field in the domain YAML while a recommendation is pending in the staging artifact, the staging artifact's recommendation for that field is considered `stale` (implicitly rejected) and hidden from `panel review`. | Staging artifacts quickly become desynchronized from the actual YAML if the user edits the YAML directly. Presenting stale drafts is confusing. | Section 3.C (FR-KIR-8/9) | Editing `business-targets.yaml` manually hides the corresponding pending draft from `startd8 panel review`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F4: Clarifying ownership during heuristic fallback is important, though R3-F1 tightens the condition for when fallback is allowed.
- R2-F1: Comment-preserving writes are absolutely essential for value inputs.
- R2-F2: Preventing duplicate LLM spend on already-drafted fields is a strong Mottainai catch.

#### Review Round R4 — claude-opus-4-8-thinking-high — 2026-07-02

- **Reviewer**: claude-opus-4-8-thinking-high
- **Date**: 2026-07-02 21:16:00 UTC
- **Scope**: Final polish — composite field granularity, roster drift warnings, and decision funnel telemetry.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Data | high | Explicitly define the `value_path` granularity for composite fields in **FR-KIR-4**. Does the enumerator yield `product_funnel.signups` (the parent object) or `product_funnel.signups.target` (the scalar)? Require that the enumerator yields the logical *composite* field, and the drafting prompt explicitly asks the persona to provide all required sub-fields (e.g., both target and rationale). | If the enumerator yields scalar leaves, the panel will be queried twice per metric (once for target, once for why), doubling LLM spend and breaking context. | Section 3.A (FR-KIR-4) | The enumerator yields 1 item per metric row, not 2; the LLM returns a structured dict containing all sub-fields. |
| R4-F2 | Risks | medium | Add a drift warning requirement to **FR-KIR-9** / **FR-KIR-10**: During `panel review` and `panel approve`, compare the staging artifact's `roster_version` and `brief_hash` against the live roster. If they differ, display a warning that the recommendation was generated under older persona context. | The `Recommendation` model stores these hashes (from `PanelAnswer`), but they provide no value if the CLI never checks them before applying the write. | Section 3.C (FR-KIR-9) | Modifying `stakeholders.yaml` after drafting causes `panel review` to display a "⚠ Roster context has changed" warning. |
| R4-F3 | Ops | medium | Extend **FR-KIR-14** to require that `panel review`, `panel approve`, and `panel reject` emit distinct funnel events (e.g., `recommendation_reviewed`, `recommendation_approved`). | The current telemetry requirement only covers the LLM call (`ask`), leaving the human decision half of the funnel entirely dark in observability dashboards. | Section 3.D (FR-KIR-14) | Approving a draft emits `recommendation_approved` with attributes for domain and role_id. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-F1: Bounding the heuristic fallback prevents drafting useless, off-domain starters.
- R3-F2: Editing large blocks of text in a YAML file is always superior to `--edit "long string"`.
- R3-F3: Hiding stale drafts prevents clobbering manual user edits.

#### Review Round R5 — claude-sonnet-5 — 2026-07-03 01:50:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 01:50:00 UTC
- **Scope**: Gap-hunting pass against the **shipped implementation** (verified `src/startd8/stakeholder_panel/*.py` and `src/startd8/cli_panel.py` against the requirements text) — all 7 areas are already substantially addressed, so this round checks whether the acceptance criteria as literally written are actually satisfied by the code, not just plausible in the abstract.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Validation | medium | **FR-KIR-9** states "`panel review`/`approve` compare the staged `roster_version` + `brief_hash` against the live roster; if they differ, a '⚠ roster context has changed' warning is shown." Verified against `src/startd8/cli_panel.py`: this check exists only in `panel_review` (compares `rec.roster_version` to `roster_version_of(roster)`); `panel_approve` never performs it. As written, this acceptance criterion is **not fully testable/true** for the `approve` half of the sentence. | An untestable-as-written requirement is exactly what FR-KIR-9's own "review renders the gap, not just the fill" discipline is meant to prevent elsewhere — the doc should either scope the sentence to `review` only (matching the code) or the criterion should drive a follow-on build increment for `approve`. | Section 3.C (FR-KIR-9) | Either: (a) narrow the sentence to "`panel review` compares…", or (b) add an explicit acceptance test asserting `panel approve` also warns on drift before applying. |
| R5-F2 | Validation | medium | **FR-KIR-10** states "the `--edit "<value>"` flag is for short scalars only, and a bare `--edit` may open `$EDITOR` rather than force a hostile shell-quoted string." Verified: `src/startd8/cli_panel.py:panel_approve`'s Typer signature (`field`, `all_`, `session`, `force`, `project_root`) has **no `--edit` option at all** — not a stub, not a partial implementation. The requirement describes a flag that does not exist in the shipped CLI. | A requirement whose acceptance criterion names a concrete flag that was never built will keep confusing future readers into thinking `--edit` is available; either build it or retire the sentence so the requirement matches the "manual YAML edit is the intended UX for complex values" posture the rest of FR-KIR-10 already establishes. | Section 3.C (FR-KIR-10) | `startd8 panel approve --help` is diffed against the documented flag set as a regression check. |
| R5-F3 | Data | low | **FR-KIR-9**'s "compare... `roster_version` **and** `brief_hash`" language implies a *per-recommendation, per-persona* `brief_hash` check distinct from the aggregate `roster_version`. The shipped `panel_review` only compares `roster_version` (an aggregate hash over *all* persona brief hashes) — so editing an unrelated persona's brief triggers a drift warning on every *other* persona's pending drafts too, which is safe (no false negatives) but noisier than the literal wording suggests. Clarify whether per-persona `brief_hash` comparison (via `roster.persona(role_id)`) is required v1 scope or whether the aggregate check is the accepted interpretation. | Ambiguous wording here makes "compare... brief_hash" an untestable half-sentence today — either drop "and brief_hash" (aggregate-only is deliberate and sufficient — no false negatives) or add the finer-grained check as a follow-on. | Section 3.C (FR-KIR-9) | A test with 2 personas: change only persona B's brief, and assert whether persona A's pending draft is (or is intentionally not) flagged, per whichever interpretation is chosen. |
| R5-F4 | Architecture | low | §6's Reference-Audit row for `cli_panel` ("clobber guard, exit codes; imports `looks_generated`") should state the module's real path — `src/startd8/cli_panel.py`, a **top-level** module, not a member of the `stakeholder_panel/` package — since the companion plan's §1 module table implies the opposite location (R5-S3 in the plan's Appendix C). | The reference-audit table exists precisely to prevent a phantom-location assumption from surviving into implementation (per this doc's own §0.1 "phantom-reference audit" lesson); leaving the path implicit lets the plan's inaccurate placement go unchallenged. | Section 6 "Pre-Implementation Reference Audit" | The table row explicitly states `src/startd8/cli_panel.py` (not `stakeholder_panel/cli_panel.py`). |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None — all R1-R4 suggestions are already triaged into Appendix A/B; there are no untriaged items left in Appendix C.

#### Review Round R6 — claude-sonnet-5 — 2026-07-03 02:00:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 02:00:00 UTC
- **Scope**: Second, adversarial pass — traced the shared `Persona.ask()` call path underneath both the
  reactive (FR-7) and proactive (FR-KIR-6) surfaces to check whether FR-KIR-6's guarantee actually holds
  end-to-end, not just at the `Recommendation` object boundary.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | Risks | high | **FR-KIR-6** states "the guard must not treat a drafted starter as a fabrication" and that the recommendation instead "carries an explicit 'estimate — not grounded in a project fact' grounding." Verified: this is true of the final `Recommendation` object (`recommend.py:_build_recommendation` force-sets `grounding=Grounding.ESTIMATE` and rebuilds `flags` from `check_contradiction` only) — but the **shared** `Persona.ask()` (in `stakeholder_panel/persona.py`, used by both the reactive and proactive paths) still runs the reactive `check_grounding()`/`unsupported_specifics()` check unconditionally first, and that check's downgrade/flags land in the underlying `PanelAnswer`, the `panel.ask` OTel span (`panel.grounding` attribute), and the **persisted panel transcript entry** (FR-12) — none of which FR-KIR-6 currently mentions. As written, FR-KIR-6 guarantees the wrong layer: the audit trail, not just the recommendation. | A future auditor reading the transcript (the FR-12/FR-KIR-14 audit trail this requirement explicitly leans on for traceability) would see a Teian estimate marked "uncertain" with "unsupported-specifics" flags attached — which looks exactly like a reactive answer the persona itself was unsure about, when in fact it is the FR-KIR-6-sanctioned, *expected* behavior of an honest starter estimate. | Section 3.B (FR-KIR-6) | Extend FR-KIR-6's acceptance criterion to name the `PanelAnswer`/transcript/span layer explicitly (not just `Recommendation`), and require that a Teian-originated answer's persisted grounding read the persona's true self-report — verified with a transcript-read test after a `panel recommend` call with an intentionally "unsupported" numeric draft. |
| R6-F2 | Validation | medium | Add an explicit negative-space acceptance criterion to **FR-KIR-6**: "`Recommendation.flags` must never contain an `unsupported-specifics:`-prefixed entry" (the reactive guard's flag format), to pin the invariant `recommend.py` currently satisfies only incidentally (by not threading `answer.flags` through). | Without a named negative invariant, a future refactor of `_build_recommendation` that starts forwarding `answer.flags` "for completeness" would silently reintroduce exactly the FR-KIR-6 violation R6-F1 found one layer down, and nothing in the test suite would catch it. | Section 3.B (FR-KIR-6) | A unit test asserting the flag-format invariant, as described in the companion plan's R6-S2. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R5-F1: still stands — the approve-time drift-check gap is orthogonal to this round's grounding-pollution finding and remains unresolved.

#### Review Round R7 — claude-sonnet-5 — 2026-07-03 02:15:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 02:15:00 UTC
- **Scope**: Third pass. See the companion plan review's R7 for a live, reproduced repro of the crash
  behind R7-F1 (`splice_yaml_value` → `parse_conventions` → uncaught `yaml.scanner.ScannerError`).

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | Validation | critical | **FR-KIR-11** states a rejection at the round-trip gate is "**surfaced, never silently swallowed**." Verified (reproduced live): when `_build_recommendation`'s fallback path (`(answer.text or "").strip()`, used whenever a persona reply lacks a recognized `TARGET`/`VALUE` marker) yields a multi-line string with no colon and no leading/trailing whitespace, `capture.py:_format_scalar` emits it **unquoted**, the embedded newline splits it across two physical YAML lines, and the domain's strict parser (`yaml.safe_load` inside `parse_conventions`/etc.) raises `yaml.scanner.ScannerError` — confirmed **not** a `ValueError` subclass — which propagates **uncaught** past `apply_recommendation`'s `except ValueError`, crashing `panel approve` with a raw traceback. This is the opposite of "surfaced, never silently swallowed": it's an unhandled crash, not a clean, typed rejection. | The acceptance criterion as written implies every rejection path returns a clean, renderable outcome; this repro shows at least one realistic path (an LLM reply that doesn't follow the one-line format instruction) does not. | Section 3.D (FR-KIR-11) | Add an acceptance criterion requiring the round-trip gate to catch `yaml.YAMLError` (not just `ValueError`) and convert it to the same typed rejection outcome; validate with the plan's R7-S1 regression test. |
| R7-F2 | Risks | medium | **FR-KIR-12**'s "no wasted re-spend" guarantee should explicitly cover a **rejected** field, not just a pending **draft**. As written and as implemented (`recommend_inputs`'s staging-aware skip checks `disposition == "draft"` only), a field a human explicitly rejected via `panel reject` is silently re-drafted (and re-paid for) on the very next `panel recommend` invocation without `--redraft`. | FR-KIR-8 frames rejection as a real outcome ("a third implicit outcome — reject/skip — leaves the field blank/estimate"), but FR-KIR-12's re-spend guard doesn't currently treat that outcome as "already decided" the way it treats a pending draft — an inconsistency between the two requirements' treatment of disposition state. | Section 3.D (FR-KIR-12) | Test: `panel reject` a field, then `panel recommend` without `--redraft`; assert 0 personas are queried for that field (mirrors the existing "already-drafted, 0 spend" test for pending drafts). |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R6-F1: still stands — orthogonal to this round's splice-crash and rejected-redraft findings.

#### Review Round R8 — claude-sonnet-5 — 2026-07-03 02:20:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 02:20:00 UTC
- **Scope**: Fourth pass. Only one new, low-severity finding surfaced this round — see the companion
  plan review's R8 executive summary for the explicit convergence assessment.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-F1 | Data | low | **FR-KIR-7** calls the staging artifact "the sole per-field audit trail" — add a criterion that a malformed/unrecognized `disposition` value in that artifact must be **surfaced** (warning, or coerced to a visible error state), not silently treated as invisible to every consumer. Verified: `Recommendation.from_dict`'s `disposition` field is an unvalidated raw string; a hand-edited typo (the artifact is deliberately human-diffable per R2-F3/FR-KIR-7) silently drops a record from both `review` and `approve --all`. | An audit trail that can silently lose entries to a typo without any surfaced signal undermines the "sole audit trail" guarantee FR-KIR-7 makes — the requirement should say what happens on malformed data, not just on well-formed data. | Section 3.B (FR-KIR-7) | Test per the companion plan's R8-S1 validation approach. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R7-F1/R7-F2: both still stand, unaffected by this round's minor finding.

**Convergence note:** matches the companion plan review's R8 assessment — this document is approaching convergence on the requirements side too; most remaining low-hanging findings are implementation-detail-level (like R8-F1) rather than requirement-shape gaps.
