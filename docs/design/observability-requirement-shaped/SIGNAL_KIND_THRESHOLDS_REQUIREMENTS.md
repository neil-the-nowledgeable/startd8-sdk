# Per-signal_kind grounded threshold defaults (#229 residual / #226 FR-7 completion) — Requirements

**Version:** 0.4 (post CRP Round 1 — 10 suggestions + adversarial, all applied)
**Date:** 2026-07-23
**Status:** IMPLEMENTED (2026-07-23) — signal_kind axis in importance_thresholds.yaml; `saturation` ceiling ladder (FR-2a); fr.target-first resolution in generate_functional_slos + threshold_tier label; run_success + app-specific kinds grounding-pending. 9 tests; 696 obs-suite green.
**Owner:** observability artifact generator (`src/startd8/observability/`)
**GitHub:** #229 (the residual values-grounding task) · completes #226 FR-7 (compose the `signal_kind`
axis onto the #234 criticality × deployment_mode table)
**Refs:** `config/importance_thresholds.yaml`, `_select_importance_default`/`_resolve_threshold`
(`artifact_generator_generators.py`), the #300-D2/#308 threshold-deferral discipline

---

## 0. Planning Insights (Self-Reflective Update)

> Ground: read `importance_thresholds.yaml`, `_resolve_threshold`, `_FUNCTIONAL_SLI_TEMPLATES`, and the
> generate_functional_slos target-requirement. The naïve draft ("fill in per-kind threshold values") hit
> the OQ-5 honesty wall and split into a *mechanism* deliverable + a *grounded-values* subset.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| Fill all per-signal_kind cells (freshness/queue_depth/lag/retry_rate/saturation/run_success) with values. | `_FUNCTIONAL_SLI_TEMPLATES` shows the **units** (`saturation`=percentunit, `freshness`=s, `queue_depth`/`lag`=count, `run_success`=ratio). Only **saturation** (SRE-canonical ~0.8) and **run_success** (availability-analog ~0.99) can be grounded WITHOUT a live run; freshness/queue_depth/lag/retry_rate magnitudes are **app-specific** and would be **invention** (OQ-5 forbids). | **Split (FR-2/FR-3):** fill the SRE-groundable cells now; ship the app-specific cells as **grounding-pending** (resolution DEFERS — never a fabricated magnitude). This is exactly OQ-5's "ship the table shape, don't invent values." |
| The table already scales by deployment_mode, so per-kind cells inherit it. | The table is `<criticality>.<deployment_mode>.{availability, latency_p99}` — **only two fields**; `_select_importance_default(business, field_name)` keys by `field_name`, so a `signal_kind` is just a new field name that composes for free. | **FR-1 is additive**: add `signal_kind` keys as new fields under each `<crit>.<mode>` cell; `_select_importance_default` needs **no structural change** — pass the signal_kind as `field_name`. |
| Functional SLOs already resolve a default. | `generate_functional_slos` **requires `fr.target`** (`:1840`); no target ⇒ `unfulfilled` (`:1848`). No per-signal_kind default is ever resolved today. | **FR-4:** insert a resolution step (author target > grounded config cell > defer) before `unfulfilled`; same for the declared-functional (#300 D2) and probe (#308) threshold-deferral. |
| A config default contradicts #300-D2/#308 NR-1 "no invented threshold." | NR-1 forbids **per-call invention**; the criticality/latency defaults are already resolved from a **single-sourced, overridable, grounded table** — that is NOT invention. | **The config table IS the grounding seam.** NR-1 is refined to "no per-call invention; the grounded table is the single source." A config cell resolves; an absent/grounding-pending cell still defers. |
| "Grounded" means measured from a live Mastodon run. | The live magnitudes need P2-live (external). What IS grounded here: the **declared kickoff inputs** — `criticality` (`artifact_generator_context.py:535`) and `deployment_mode` (`spec.deployment.mode`, `:538`) — plus each kind's **unit**. | Ground the values in **declared context + unit + SRE standard**, and provenance-tag them honestly; NEVER claim a live-measured magnitude. Live-pilot magnitudes = the follow-up when P2-live runs. |

**Resolved OQ:** #229 OQ-5 → *ship the shape + the SRE-groundable cells; app-specific cells are grounding-pending (defer, not invent).*

### 0.1 Lessons-Learned Hardening (v0.3)
- **Phantom-reference audit** — verified: `importance_thresholds.yaml` structure, `_select_importance_default`
  (`:57`), `_resolve_threshold` (`:146`, returns `(value, tier)`), `_FUNCTIONAL_SLI_TEMPLATES` (`:1042`),
  the `generate_functional_slos` target gate (`:1840`), `business.{criticality, deployment_mode,
  importance_thresholds}`. Added §9.
- **[preserve-declared-intent]** — an author `fr.target` always wins over a config default (no producer-side
  override of declared intent).
- **Single-source vocabulary ownership** — the VALUES live only in `importance_thresholds.yaml`; the binder
  cites `_resolve_threshold`, never restates a magnitude. The units are owned by `_FUNCTIONAL_SLI_TEMPLATES`.

### 0.2 Design-Principle Hardening (v0.3.1)
- **Genchi Genbutsu / not-fabrication** — values are grounded in *declared* context (criticality/mode) + unit
  + SRE standard; app-specific magnitudes are left **grounding-pending**, not invented. Provenance is tagged.
- **Hitsuzen (derive the determinable)** — the criticality×mode *scaling* is deterministic; only the app-
  specific *anchor* is undetermined, so it defers. Nothing is LLM-generated.
- **Accidental-Complexity anti-principle** — no new resolution engine; reuse `_select_importance_default`'s
  field-name keying. The signal_kind axis is *data* in the YAML, not code.
- **Monotonicity (the table's existing invariant, FR-2a)** — the new cells preserve it: raising criticality
  and/or moving installed→deployed never loosens a bound (saturation non-increasing, run_success non-
  decreasing, etc.).

---

## 1. Problem Statement

`_DEFAULT_THRESHOLDS` (`availability=99 / latency_p99=500ms / throughput=100rps`) is the flat fallback for
**every** signal kind. For a worker/batch/ML/cron service these are category errors (#229): a Sidekiq
worker's saturation SLO falls back to `100rps`; a freshness SLO to `500ms`. The criticality × deployment_mode
table (#234) fixed availability/latency but **only those two fields** — the functional signal kinds
(saturation/freshness/queue_depth/retry_rate/lag/run_success) have no grounded default and either take an
explicit `fr.target` or become `unfulfilled`. #226 FR-7 promised the composed `criticality × signal_kind`
table; this completes it, honestly (OQ-5).

## 2. Requirements

**FR-1 — Add a `signal_kind` axis to the threshold table (additive).** Extend
`importance_thresholds.yaml`: under each `<criticality>.<deployment_mode>` cell, add the functional
signal_kind keys as new fields (unit-correct). `_select_importance_default(business, signal_kind)` resolves
them with **no structural change** (the signal_kind is a field name). Non-request kinds only; `throughput`
stays flat (a capacity fact, per the existing FR-2b decision).

**FR-2 — Fill exactly ONE genuinely-groundable cell: `saturation` (R1-F7 shrank this to one).**
`saturation` (percentunit, `gauge_max` shape → the SLI is `max(<util>)`, compared against the target as a
**ceiling**, consistent with how `latency_p99` uses `spec.target` as a threshold — R1-F2). The SRE-canonical
utilization bound: `deployed high` = `0.80`, **loosening** (higher ceiling) for lower criticality /
`installed`. Grounded in SRE standard (80% is the canonical saturation alert). Per-cell values + direction in
the FR-2a table below. **`run_success` is NOT filled** — its `_FUNCTIONAL_SLI_TEMPLATES` `ratio` shape emits
`sum(rate(job_runs_total[…]))`, a **bare rate, not a good/total division** (R1-F7), so a `0.99` objective is
meaningless there; run_success stays grounding-pending until its SLI query is fixed (a separate concern).

### FR-2a — the monotonic saturation ladder (explicit, R1-F3)
`saturation` is a **CEILING** → *non-increasing* (tighter) as criticality rises and as `installed→deployed`
(opposite direction to availability, a floor). Cells:

| criticality | `deployed`/`default` (ceiling) | `installed` (forgiving ceiling) |
|---|---|---|
| critical | 0.75 | 0.85 |
| high | 0.80 | 0.90 |
| medium | 0.85 | 0.92 |
| low | 0.90 | 0.95 |

Invariant (testable): within a column, ceiling **non-decreasing** as criticality drops; for a fixed
criticality, `installed` ≥ `deployed` (forgiving). No cell exceeds 0.95.

**FR-3 — Everything else is grounding-pending (omit the key → defer, never invent) (R1-F5).**
`freshness` (s), `queue_depth`/`lag` (count), `retry_rate` (rate), **and `run_success`** (broken query, FR-2)
have magnitudes this repo cannot ground. **Omit the key** (not an explicit `null`): `cell.get(kind)` → `None`
→ the caller defers (as today), and omit sidesteps the `obs_config._deep_merge` null-wipe footgun (a manifest
`null` leaf-replaces a base cell; a manifest *value* is the intended fill path). No fabricated value ships.

**FR-4 — Resolve the default in `generate_functional_slos` only; `fr.target` FIRST (R1-F1, R1-F4).** At the
functional-SLO change locus (before `unfulfilled`, `:1848`): the target is
`fr.target if fr.target else _resolve_threshold(signal_kind, business, …)[0]` — **`fr.target` is read
explicitly first** (NR-3), because `_resolve_threshold`'s own author-tier reads `getattr(business,
signal_kind)` which is **always `None`** for a signal_kind (no such `BusinessContext` attr) and is therefore
inert here. If neither yields a value → `unfulfilled` (unchanged). **The declared-functional (#300 D2) and
probe (#308) sites are NOT touched** (R1-F4): the probe binder is `freshness`-only + grounding-pending, so a
config cell can never bind there; D2's saturation path may be added later but is out of this increment to
keep the blast radius to one binder.

**FR-4a (normative, was OQ-3) — this is an intentional, welcome behavior change (R1-F8).** Filling the
`saturation` cell converts a prior `unfulfilled` outcome (a saturation FR with no author target) into a
**bound graded SLO** at tier `default:importance`, value from the ladder. This supersedes the defer-by-
default for **saturation only**; all other functional kinds still defer (no cell). The NR-1 reconciliation:
this is NOT per-call invention — the value comes from the single-sourced, overridable, monotone config table.

**FR-5 — Deployment-mode scaling applies to the saturation cell** (FR-2a `installed` column) — a locally-
installed tool gets a forgiving ceiling, not a production one. *(The user's "leveraging deployed mode".)*

**FR-6 — On-disk provenance (R1-F9).** When the config cell binds (tier `default:importance`), the emitted
SLO carries a `threshold_tier: default:importance` label (or `quality` field) so a consumer can distinguish a
grounded-derived `0.80` from an author target on disk — the honesty discipline made verifiable, not just an
in-memory `DerivationTrace`.

## 3. Non-Requirements

**NR-1 — No invented magnitudes.** freshness/queue_depth/lag/retry_rate/**run_success** stay grounding-pending
(omitted) until an author or a live pilot fills them. (Genchi Genbutsu / OQ-5.)
**NR-2 — `throughput` stays flat** (capacity fact; existing FR-2b decision, not touched).
**NR-3 — Author `fr.target` always wins** — read explicitly first (FR-4); no config default overrides it.
**NR-4 — Byte-identical for a RED-only service** — a service with no functional[] FRs resolves
availability/latency/throughput exactly as today; `_select_importance_default` reads `cell.get(field)`, so a
new `saturation` sibling key must not perturb the existing fields. **Acceptance: a golden-diff test** (R1-F6).
**NR-5 — No project-scoped AI kinds** — `llm_cost_per_request`/`token_throughput`/`context_saturation` out of
scope.
**NR-6 — #229 supplies the threshold VALUE only, never the metric SERIES (R1-F10).** `_FUNCTIONAL_SLI_TEMPLATES`
candidate tuples (which series each kind binds) are untouched; series-grounding (freshness/lag) is a separate
OQ-5 problem.

## 4. Open Questions

- **OQ-1 — RESOLVED (R1-F3) → the FR-2a ladder above** (saturation-only, ceiling direction, explicit cells).
- **OQ-2 — RESOLVED (R1-F5) → omit the key** for grounding-pending (avoids the deep-merge null-wipe).
- **OQ-3 — RESOLVED (R1-F8) → normative FR-4a** (intentional behavior change, saturation only).

## 9. Reference Audit

| Symbol / fact | Location | Exists? |
|---|---|---|
| `importance_thresholds.yaml` (`<crit>.<mode>.{availability,latency_p99}`) | `observability/config/` | ✅ (extend) |
| `_select_importance_default(business, field_name)` (keys by field) | `artifact_generator_generators.py:57` | ✅ (reuse) |
| `_resolve_threshold` → `(value, tier)` | `:146` | ✅ |
| `_FUNCTIONAL_SLI_TEMPLATES` (units per kind) | `:1042` | ✅ |
| `generate_functional_slos` target gate → `unfulfilled` | `:1840/:1848` | ✅ (change locus) |
| `business.criticality` / `deployment_mode` (kickoff inputs) | `artifact_generator_context.py:535/538` | ✅ |
| declared-functional / probe threshold-deferral | `generate_declared_functional_slos` / `generate_declared_probe_slos` | ✅ (FR-4 sites) |

---

*v0.4 — Post CRP Round 1 (10 F-suggestions + adversarial, all ACCEPTED; Appendix A). The review shrank the deliverable to the honest core: the signal_kind MECHANISM + `saturation` as the ONE grounded cell (FR-2a monotone ceiling ladder); run_success + the app-specific kinds are grounding-pending (run_success's ratio query is a bare rate, R1-F7). fr.target-first resolution (R1-F1), one binder only (R1-F4), on-disk tier label (R1-F9). 6 FRs+FR-2a/4a / 6 NRs / 0 open OQ. Ready to implement.*

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
| R1-F1 | Author-tier must read `fr.target` first (`getattr(business, kind)` is always None) | CRP R1 | Applied → FR-4 (fr.target explicit-first) | 2026-07-23 |
| R1-F2 | Clarify saturation cell = threshold/ceiling in spec.target (like latency), not an objective ratio | CRP R1 | Applied → FR-2 | 2026-07-23 |
| R1-F3 | Explicit monotone ladder table + ceiling-vs-floor direction | CRP R1 | Applied → FR-2a table; OQ-1 resolved | 2026-07-23 |
| R1-F4 | Remove the probe (#308) FR-4 site (freshness-only + grounding-pending = dead path) | CRP R1 | Applied → FR-4 scoped to generate_functional_slos only | 2026-07-23 |
| R1-F5 | Omit-key for grounding-pending (deep-merge null-wipe footgun) | CRP R1 | Applied → FR-3; OQ-2 resolved | 2026-07-23 |
| R1-F6 | NR-4 byte-identity acceptance test | CRP R1 | Applied → NR-4 (golden-diff) | 2026-07-23 |
| R1-F7 | run_success `ratio` shape is a bare rate → 0.99 meaningless; mark grounding-pending | CRP R1 | Applied → FR-2 fills SATURATION ONLY; run_success → FR-3 | 2026-07-23 |
| R1-F8 | Promote OQ-3 → normative behavior change | CRP R1 | Applied → FR-4a | 2026-07-23 |
| R1-F9 | Surface the resolution tier on-disk (threshold_tier label) | CRP R1 | Applied → FR-6 | 2026-07-23 |
| R1-F10 | #229 = threshold VALUE only, not series selection | CRP R1 | Applied → NR-6 | 2026-07-23 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-23

- **Reviewer**: claude-opus-4-8-1m
- **Scope**: Grounded review of #229 per-signal_kind thresholds against the shipped code
  (`_select_importance_default`, `_resolve_threshold`, `generate_functional_slos`,
  `generate_declared_functional_slos`, `generate_declared_probe_slos`, `obs_config._deep_merge`,
  `importance_thresholds.yaml`). Weighted per focus file: FR-2 SRE values + FR-4 behavior change /
  NR-1 reconciliation, FR-1 keying, FR-3 marker, unit correctness, NR-4 byte-identity, monotonicity.

**Executive summary (top risks / gaps):**
- FR-4 says "resolve `_resolve_threshold(signal_kind, business, …)`" but that function's tier-1 (author)
  path reads `getattr(business, field_name)` — which is **always `None` for a signal_kind** (no such
  attr on `BusinessContext`), so it silently cannot honor an author `fr.target`. NR-3 ("author wins") is
  unmet by the literal FR-4 mechanism. **High.**
- The saturation config cell (`0.8` percentunit) is a *threshold value*, but the functional-SLO binder
  writes `fr.target` into OpenSLO `spec.target` (an **objective ratio**, e.g. 0.99). Feeding `0.8` there
  is a units/semantics conflation — the exact #229 category error re-introduced at a different layer.
  **High.**
- FR-4 lists the probe deferral (#308) as a resolution site, but `generate_declared_probe_slos` is
  `freshness`-only, and freshness is grounding-pending (FR-3) → the config cell can NEVER bind there.
  Dead FR-4 site; spec over-claims. **Medium.**
- OQ-2 marker choice interacts with `obs_config._deep_merge`: an *explicit `null`* cell can be
  overridden by a manifest dict fine, but a manifest override supplying `null` will null out a grounded
  base cell (`val` is not a dict → leaf replace). Omit-key avoids the ambiguity. **Medium.**
- Monotonicity invariant (FR-2a) is asserted but not tabulated for the two NEW ladders; saturation is a
  *ceiling* (non-increasing with criticality) while availability is a *floor* — the direction inverts and
  the doc never states the per-cell target values or their monotone direction. **High.**
- Unit correctness: `run_success` template unit is `ratio` and shape `ratio`, but `_functional_sli_query`
  emits `sum(rate(job_runs_total[...]))` for `ratio` shape — that is a **raw rate, not a success ratio**
  (no good/total division). A `0.99` target against a raw rate is meaningless. **High.**
- No acceptance test is specified for NR-4 byte-identity of the RED-only path after the YAML gains keys.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | FR-4: specify that the author-wins tier reads `fr.target` (the per-FR field), NOT `getattr(business, signal_kind)`. Either (a) resolve `fr.target` explicitly before calling `_resolve_threshold`, or (b) pass an explicit `authored=fr.target` arg into a signal_kind-aware resolver. State that `_resolve_threshold`'s existing `getattr(business, field_name)` tier is inert for signal_kinds. | `_resolve_threshold` (`:150`) keys manifest off `getattr(business, field_name)`; `BusinessContext` (`artifact_generator_models.py:191`) has no `saturation`/`run_success`/etc. attr, so the author target (`fr.target`, used today at `:1898/:1925`) would be bypassed → NR-3 violated. | FR-4 body + NR-3 | Unit test: an FR with an explicit `target` and a filled saturation cell must emit the author's target, tier=`manifest`, not the config `0.8`. |
| R1-F2 | Data | high | Clarify the SEMANTIC role of a filled saturation/run_success cell: is it an OpenSLO `spec.target` (objective ratio) or a comparison THRESHOLD inside the SLI query? Today `generate_functional_slos` writes `fr.target` → `spec.target` (`:1925`) and the query has no threshold operator. A saturation ceiling `0.8` is not an objective ratio. | Putting `0.8` (percentunit ceiling) into `spec.target` conflates "80% utilization bound" with "meet-objective 80% of the window" — reintroduces the #229 category error one layer up. | FR-2 (saturation bullet) + FR-4 | Verify a generated saturation SLO's `spec.target` and query: the threshold must gate the SLI (e.g. `<= 0.8`), and `spec.target` must remain an availability-style objective, or the doc must justify the shared slot. |
| R1-F3 | Validation | high | Add an explicit MONOTONICITY table for the two new ladders (4 criticalities × {default/deployed, installed}) with the target values and the required monotone DIRECTION per field: saturation non-increasing as criticality rises / installed→deployed (a ceiling), run_success non-decreasing (a floor, like availability). OQ-1 asks to "confirm the ladder" but no cells are given. | FR-2a is asserted (`§0.2`) but unfalsifiable without values. saturation and availability move in OPPOSITE directions; a reviewer/impl cannot check the invariant. | New §2 sub-table under FR-2; resolves OQ-1 | Property test: for each field assert the monotone relation across the full crit×mode grid (mirrors the availability/latency ladder test if one exists). |
| R1-F4 | Interfaces | medium | FR-4: remove or qualify the probe (#308) deferral as an FR-4 resolution site. `generate_declared_probe_slos` (`:1719`) supports `signal_kind == "freshness"` ONLY (`:1742`), and freshness is grounding-pending (FR-3) → no config cell can ever bind here. As written FR-4 promises a behavior change at a site that structurally cannot receive one. | Prevents an implementer from wiring a dead resolution path and an QA from testing an impossible case. | FR-4 (probe site) + §9 audit row | Assert: no probe SLO ever resolves a `default:importance` tier; the probe path stays byte-identical. |
| R1-F5 | Data | medium | Resolve OQ-2 in the DOC toward omit-key, and add a note that `obs_config._deep_merge` (`:40`) replaces a leaf when the override value is not a dict — so an explicit-`null` base cell is fine to override, but a manifest override of `null` will WIPE a grounded base cell. Omit-key sidesteps both the parser question and the null-wipe footgun. | `_deep_merge` only recurses when BOTH sides are dicts (`:44`); `null` on either side is a leaf replace. The doc's OQ-2 "lean: omit" is correct but the merge-interaction rationale isn't captured. | OQ-2 resolution + FR-3 | Test: (a) omitted cell → `_select_importance_default` returns None → defer; (b) manifest override adding the key deep-merges without disturbing sibling availability/latency; (c) manifest `null` documented behavior. |
| R1-F6 | Validation | high | Add an explicit NR-4 byte-identity ACCEPTANCE TEST to the requirements: a RED-only service (no functional[] FRs) must produce byte-identical availability/latency/throughput artifacts before vs after the YAML gains signal_kind keys. `_select_importance_default` reads `cell.get(field_name)` (`:77`), so new sibling keys under a cell must not perturb the existing two fields. | NR-4 is stated but has no verification criterion; the YAML edit is the highest-risk change for silent drift. | NR-4 + a new "Acceptance" subsection | Golden-file diff: regenerate the RED-only fixture set, assert zero byte delta on availability/latency/throughput SLOs and on `_DEFAULT_THRESHOLDS` fallthrough. |
| R1-F7 | Data | high | run_success unit/shape correctness: `_FUNCTIONAL_SLI_TEMPLATES["run_success"]` = (`job_runs_total`, shape `ratio`) and `_functional_sli_query("ratio", …)` = `sum(rate(job_runs_total[...]))` (`:1851`) — a raw rate, NOT a success RATIO (no `job_runs_total{status="success"} / job_runs_total`). A `0.99` run_success target against a raw rate is not a ratio SLI. FR-2 must state that grounding `run_success=0.99` REQUIRES the ratio query to be a good/total division first (or mark run_success grounding-pending too). | The focus file's unit-correctness priority: 0.99 as an availability-analog only makes sense if the SLI is a ratio in [0,1]; the current `ratio` shape is a bare rate. Filling the value without fixing the query yields a nonsensical SLO. | FR-2 (run_success bullet) + a note vs `_functional_sli_query` `:1851` | Verify the emitted run_success SLI query is dimensionless in [0,1] (a division), then that `0.99` compares meaningfully. |
| R1-F8 | Risks | medium | State the OQ-3 answer as a NORMATIVE requirement, not an open question: "filling saturation/run_success cells intentionally converts prior `unfulfilled`/`threshold-deferred` outcomes into BOUND graded SLOs for those two kinds; this is the desired behavior change and supersedes the D2/#308 defer-by-default for saturation only (run_success is not a declared-series kind)." Leaving it as OQ-3 blocks implementation. | FR-4 is the headline behavior change; an OQ cannot gate a shipped-behavior override. Making it normative also forces the NR-1 reconciliation to be explicit. | Promote OQ-3 → FR-4a (normative) | Test: a service that previously recorded saturation `unfulfilled` now emits a bound SLO with tier `default:importance` and value `0.8`. |
| R1-F9 | Security | low | FR-6 provenance: require the resolution TIER (`manifest`/`default:importance`/`default`/`deferred`) to appear in the emitted SLO's labels or `quality`, not only in the in-memory `DerivationTrace`. A grounded-but-derived `0.8` should be auditable on disk so a consumer can distinguish it from an author target. | `_resolve_threshold` returns the tier but `generate_functional_slos` currently drops it (only `fr.target` reaches `spec`). Without on-disk provenance the "honesty discipline" isn't verifiable downstream. | FR-6 | Assert the generated SLO carries a `threshold_tier` label = `default:importance` when the config cell binds. |
| R1-F10 | Architecture | medium | Add an explicit out-of-scope / boundary statement that `_select_functional_metric` series-binding (which candidate series) is UNCHANGED by #229 — #229 only supplies the threshold VALUE, never the metric series. Two axes (series selection vs threshold value) currently blur in FR-2/FR-4 prose. | Prevents scope creep into the OQ-5 series-grounding problem (freshness/lag series are still unverified per `:1037`). Keeps #229 to values only. | New NR (e.g. NR-6) or FR-1 boundary note | Doc review: confirm no FR touches `_FUNCTIONAL_SLI_TEMPLATES` candidate tuples. |

**Adversarial stress-test (monotonicity + deep-merge/null):**
- *Saturation ceiling inversion:* If installed mode is "extremely forgiving" like the availability band
  (installed `low` availability drops to `90`), the analogous saturation move is to RAISE the ceiling
  (allow MORE utilization). But run_success (a floor) must DROP for forgiving. A single "loosen for
  installed/low" rule applied uniformly will move saturation and run_success the SAME direction and break
  one of them. FR-2/OQ-1 must give each field its own direction (see R1-F3). Concretely check: does
  `installed low` saturation `0.95` still satisfy "raising crit never loosens" against `deployed high`
  `0.8`? (0.95 ceiling is looser → OK for a ceiling; but the availability-style monotone test asserts
  non-DECREASING, which would FALSELY flag 0.95>0.8 as fine while flagging a correct run_success drop.)
- *Null-cell resolves to a value:* Confirm no code path turns a grounding-pending cell into a value. With
  omit-key, `cell.get("freshness")` → None → defer: safe. With explicit `null`, `_deep_merge` of a
  manifest that supplies `{crit:{mode:{freshness:"60s"}}}` recurses fine (both dicts down to the leaf) and
  the leaf `"60s"` replaces `null` → the pending cell becomes an author-grounded value. That is the ONLY
  intended way a pending cell should resolve; document it as the fill mechanism (not a bug), but verify no
  DEFAULT (non-manifest) path can do the same.
- *NR-4 fallthrough:* `throughput` has no cell → `_select_importance_default` returns None → flat
  `_DEFAULT_THRESHOLDS["throughput"]` (`100rps`). Adding signal_kind keys under a cell must not add a
  `throughput` key; assert the YAML edit touches only the six functional kinds (R1-F6 golden diff covers).
