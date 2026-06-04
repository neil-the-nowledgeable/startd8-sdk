# Forward Deployed Engineer (FDE) — Implementation Plan

**Version:** 0.3.1 (adds FR-28 latest-run resolution)
**Date:** 2026-06-04
**Status:** Draft
**Companion:** [`FORWARD_DEPLOYED_ENGINEER_REQUIREMENTS.md`](FORWARD_DEPLOYED_ENGINEER_REQUIREMENTS.md) (v0.3)

> This plan is the output of the reflective loop's planning pass, re-aligned to the corrected
> v0.2 requirements. Every step traces to an FR; every FR traces to a step. Open questions
> that block a step are called out inline.

---

## Architecture at a glance

```
PROJECT (consumer repo, where the FDE is "posted")          SDK (the FDE's home / brain)
┌───────────────────────────────────┐        ┌─────────────────────────────────────────┐
│ .startd8/fde/                      │        │ src/startd8/fde/                          │
│   fde-request.md      (inbound)    │◀──────▶│   models.py     Keiyaku-shaped contracts  │
│   fde-explanation.md  (outbound)   │  .md   │   explain.py    explain mode (FROM ARTIFACT)│
│   fde-preflight.md    (outbound)   │ proto- │   preflight.py  preflight mode (LIVE)     │
│   fde-context.json    (posting)    │  col   │   sources.py    §6 source-of-truth reads  │
│   fde-cursor.json     (idempotency)│        │   compose.py    source-labeled narrative  │
└───────────────────────────────────┘        │   assistant_bridge.py  SA handshake       │
        ▲                                     └─────────────────────────────────────────┘
        │ reads service-assistant-triage.json (EVIDENCE half)   cli_fde.py / scripts/run_fde.py
        │ writes fde_explanation ref back into TriageReport (FR-17)
   Service Assistant (existing) ── deterministic/actionable flags trigger FDE (FR-14)
```

The **brain** is deterministic-first (FR-15): `sources.py` does pure reads/calls; LLM is only
invoked by `preflight.py` (assumption detection) and `compose.py` (narrative).

---

## Step-by-step (FR-traced)

### Phase 1 — Package skeleton + contracts
1. **Create `src/startd8/fde/`** package (FR-1, OQ-1). Mirror `service_assistant/` layout.
2. **`models.py`** — define the Keiyaku-shaped contract pair (FR-12): `FdeRequest`,
   `FdeExplanation`, `FdePreflightReport`, each a frozen dataclass with `.to_dict()` /
   `.from_json()` / `.to_markdown()`. Reuse `RootCause`/`PipelineStage` (NR-6). The `.md`
   serializers (FR-11) are methods here.
3. **`cli_fde.py`** — `fde_app = typer.Typer(name="fde", …)`; commands `explain`, `preflight`,
   `init`. Register with `app.add_typer(fde_app, name="fde")` in `cli.py` (mirror `cli_assist.py`
   at `cli.py:774`). (FR-1)
4. **`scripts/run_fde.py`** — thin shim, `sys.path` inject + always `exit(0)` (mirror
   `scripts/run_service_assistant.py`). (FR-1/FR-13)

### Phase 2 — Source-of-truth reads (deterministic core)
5. **`sources.py`** — one function per §6 row (FR-3/FR-5/FR-15). **OQ-2'/OQ-10 now resolved:**
   - `read_element_data(...)` → **prefer `prime-postmortem-report.json`** (`ElementPostMortem`
     already flattens tier / repair_steps / ast-validity); **fall back** to `prime-result*.json`
     raw nesting `history[].generation_metadata.micro_prime_file_results[].element_results[]`.
   - `classify_live(signals)` → `classify_tier()` (`complexity/classifier.py:58`).
   - `resolve_model_by_tier(provider, tier)` → `get_latest_model` / `Models.*` (`model_catalog.py`);
     `resolve_model_by_role(role)` → `get_models_by_role()` / `ModelCatalogEntry.agent_spec`
     (`contractors/protocols.py:432`).
   - `language_capability(lang_id)` → `LanguageRegistry.get(...)`.
   - Every return carries a `source` tag (`OBSERVED`/`MECHANISM`) for FR-6 labeling.

### Phase 3 — Explain mode (compose with Service Assistant)
6. **`explain.py`** (FR-4/5/6/7/16-explain):
   - Load `service-assistant-triage.json` → `TriageReport` (EVIDENCE half, FR-4).
   - For each `FailureTriage`, read mechanism from `sources.py` (MECHANISM half, FR-5).
   - Detect SA mechanism-misattributions (FR-7) — e.g. `deterministic == True` but SA's
     `re_run_strategy` implies "regenerate"; flag the correction with home-authority.
   - `compose.py` renders `fde-explanation.md` with every claim tagged `OBSERVED (project)` /
     `MECHANISM (sdk)` (FR-6). **Zero-LLM path** when no assumption-detection is needed (FR-15).
7. **`assistant_bridge.py`** (FR-14/FR-17): add optional `fde_explanation` ref to SA's
   `TriageReport` (path + checksum), mirroring `semantic_review: SemanticReviewRef`. Trigger =
   `FailureTriage.deterministic` / mechanism-dependent recommendation. **No auto-launch** (v1).

### Phase 4 — Preflight mode (landmine review)
8. **`preflight.py`** — two tracks (FR-8/9/10/16-preflight; OQ-9 resolved):
   - **Track 1 (pre-ingestion, no signals):** LLM reads raw plan/requirements markdown and flags
     prose assertions about SDK behavior; cross-check each against `language_capability()` /
     known mechanism facts. No `classify_tier()` needed. Cheap, runs first.
   - **Track 2 (post-ingestion, signals required):** `WorkflowRegistry.run_workflow(
     "plan-ingestion", …)` → features → `extract_signals_from_feature()` → `classify_live()`;
     flag divergence between the plan's stated expectation and the predicted tier/route. Reuse
     `run_semantic_compliance(...)` / `convergent-review` for generic quality alongside.
   - Each landmine names its track + the §6 source that adjudicates it; tier claims labeled
     *prediction*, not observation (FR-16). Render `fde-preflight.md` into `.startd8/fde/`.

### Phase 5 — Posting + idempotency
9. **`fde-context.json` + optional `init`** (FR-2, OQ-6 resolved): **auto-create** `.startd8/fde/`
   on first invocation (no mandatory init); provide optional `startd8 fde init` for explicit
   setup/re-stamp. Stamp project id + SDK version (`startd8.__version__`), refresh each run.
   **Placement:** project-scoped files (`fde-context.json`, `fde-cursor.json`, `fde-request.md`,
   `fde-preflight.md`) under `.startd8/fde/`; run-scoped `fde-explanation.md` into the run output
   dir beside `service-assistant-triage.json`.
10. **`fde-cursor.json`** (FR-13): idempotency keyed by (request-artifact checksum + SDK
    version), mirroring SA's `service-assistant-cursor.json` (`detector.py:206-249`).

### Phase 6 — Tests
11. Unit tests per FR; a coverage test that every §6 mechanism question has a `sources.py`
    reader (analogue of SA's `CAUSE_TO_OPERATIONAL_ACTION` coverage test). **Plus (R4-S5):**
    `test_sources_has_no_llm_imports` (ast/grep guard that `sources.py`/`deterministic_compose.py`
    import no provider/agent modules), `test_compose_no_unlabeled_mechanism_claims` (R5-S2),
    `test_explain_zero_llm` (`llm_call_count == 0`, R1-F6). **Logger-policy allowlist moves to a
    Phase-1 gate (R1-S11)** — every new `fde/*.py` trips `test_logger_acquisition_policy.py`, so
    run it green after Phase 1, not at the end.

### CRP-applied step deltas (v0.3, from R1–R5 S-triage)

> Folded into the phases above; listed here with originating S-IDs (per-ID in Appendix A).

- **Step 2 (contracts):** add `protocol_version` (R1-S5); write **`fde-*.json` canonical** +
  derived `.md` (R5-S5); add `.to_prompt_section()` (R3-S4).
- **Step 5 (sources):** `read_element_data` reads `generation_strategy` from **raw JSON only**
  (post-mortem lacks it — R2-S1); double-absence → "mechanism unavailable" (R1-S10); both-present
  mismatch → `MECHANISM (sdk, conflict)` banner via checksum/mtime (R5-S3); call
  `LanguageRegistry.discover()`/`ProviderRegistry.discover()` before live reads (R4-S1).
- **New Step 5b (trust gate):** validate schema/version of every consumed artifact, degrade-or-fail
  (R1-S2).
- **Step 6 split:** `deterministic_compose.py` (slot template from `List[LabeledClaim]`, no agent)
  is the default/zero-LLM path; `compose.py` is optional LLM polish behind a flag + the post-compose
  labeling guard (R1-S1, R3-S2, R5-S2). Add feature↔element join (R2-S2), missing-triage degrade +
  `--allow-no-triage` exit-2 (R3-S5), batch-patterns + three-way SCR + legitimate-disagreement
  branches (R1-S9 and reqs FR-25).
- **Step 7 (bridge):** `attach_fde_ref_to_triage()` atomic write-back (R3-S1); **artifact-only SA
  read, no typed import** (R1-S6); SA-side one-line markdown link to `fde-explanation.md` (R4-S4,
  separate small SA PR).
- **Step 7b (notify):** `fde/notify.py` emits `FDE_EXPLAIN_COMPLETE`/`FDE_PREFLIGHT_COMPLETE` +
  `OTelEventBridge` (R5-S1; new `EventType`s in `events/types.py`).
- **Step 8 (preflight):** greenfield guard — predict only when ≥1 `target_file` on disk, else
  prose-only + low-confidence tag (R4-S2); **isolated scratch dir**
  `.startd8/fde/preflight-scratch/<checksum>/` (R2-S3); cost budget + skip (R1-S3); redaction pass
  before Track-1 LLM (R3-S3).
- **Step 6/8 (cost):** all LLM entry points wired to `CostTracker` with `--max-cost-usd` /
  `STARTD8_FDE_MAX_COST_USD`, labeled partial report on breach (R2-S4).
- **Step 10 (idempotency):** cursor mirrors SA shape — `processed[run_id] = {request_checksum,
  triage_checksum, mechanism_checksum, sdk_version, processed_at}` (R2-S5, R1-S4).
- **Step 3 (CLI):** `explain --feature-id` (repeatable) to scope batch triage (R5-S4).
- **Step 3/5b (FR-28 latest-run):** make the `explain` run-dir arg optional; add `--latest` +
  `--base`. New `sources.resolve_latest_run(base, project_id)` → newest `run-*/plan-ingestion`
  with a `service-assistant-triage.json` (fallback: newest with `prime-result*.json`); auto-discover
  base = `<project-root>/.cap-dev-pipe/pipeline-output/`; disambiguate multi-project; exit non-zero
  + clear message when none found; report the auto-selected run id. Explain-only.
- **New Step 12 (cap-dev-pipe hook, opt-in):** `run_fde.py` after the SA shim when
  `STARTD8_FDE_AFTER_ASSIST=1` and the trigger matches; off by default, shim exits 0 (R4-S3).

---

## Reuse map (FR-9, confirmed library surfaces)

| Need | Call | Returns |
|------|------|---------|
| Parse prose plan → features | `WorkflowRegistry.run_workflow("plan-ingestion", cfg)` | `WorkflowResult` (features, context-seed) |
| Requirements+plan review | `WorkflowRegistry.run_workflow("convergent-review", cfg)` | `WorkflowResult` |
| Semantic compliance | `run_semantic_compliance(output_dir, …)` | `SemanticComplianceReport` |
| Post-ingestion domain checks | `WorkflowRegistry.run_workflow("domain-preflight", cfg)` | `WorkflowResult` (needs context-seed) |

## Blocking open questions (resolve before the dependent step)
- ~~**OQ-2'** → Step 5~~ **RESOLVED.** Source = `prime-result*.json`
  (`scripts/run_prime_workflow.py:838`), preferred flattened surface = `prime-postmortem-report.json`.
- ~~**OQ-10** → Step 5~~ **RESOLVED.** Two complementary catalogs (tier: `model_catalog.py`;
  role: `contractors/protocols.py:432`); no discrepancy.
- ~~SA↔FDE coupling~~ **RESOLVED.** One-directional (FDE→SA), no import cycle; SA owns a local
  `FdeRef` (FR-17).
- ~~**OQ-9** → Step 8~~ **RESOLVED.** Two-track preflight: Track 1 (prose, raw markdown, no
  signals) + Track 2 (post-`plan-ingestion`, signals → `classify_tier()`).
- ~~**OQ-6** → Step 9~~ **RESOLVED.** Auto-create (optional `fde init`); scope-split footprint
  (`.startd8/fde/` project-scoped; `fde-explanation.md` run-scoped beside the SA triage).

**All open questions resolved.** Ready for Convergent Review, then implementation.

---

*v0.2 — traces requirements v0.2. Steps are ordered by dependency; the deterministic core
(Phase 2) is the spine, explain (Phase 3) ships before preflight (Phase 4) since it has fewer
open questions.*

*v0.3 — CRP R1–R5 S-suggestions triaged (all accepted, 0 rejected on merit) and folded into the
phases via "CRP-applied step deltas"; per-ID in Appendix A. Notable: new Step 5b (artifact trust),
Step 6 split (deterministic_compose vs LLM compose — makes FR-21/zero-LLM enforceable by
construction), Step 7b (observability), new Step 12 (opt-in cap-dev-pipe hook), Step 11 augmented
(import-guard + labeling tests; logger-policy resequenced to Phase 1). Traces requirements v0.3
(FR-18…FR-27).*

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

> Triage of CRP R1–R5 (S-suggestions). **All material S-suggestions ACCEPTED** and folded into the
> phases above (see "CRP-applied step deltas").

| ID(s) | Theme | Merged into | Date |
|-------|-------|-------------|------|
| R1-S1, R5-S2 | post-compose labeling guard / slot-based compose | Step 6 split | 2026-06-04 |
| R3-S2 | split `deterministic_compose.py` from LLM `compose.py` | Step 6 split | 2026-06-04 |
| R1-S8, R4-S5 | extend §6 coverage test into labeling-lint + no-LLM-import guard | Step 11 | 2026-06-04 |
| R1-S2 | consumed-artifact schema validation | new Step 5b | 2026-06-04 |
| R2-S1 | `generation_strategy` raw-JSON-only (post-mortem gap) | Step 5 | 2026-06-04 |
| R1-S10 | double-absence fallback | Step 5 | 2026-06-04 |
| R5-S3 | both-present conflict banner | Step 5 | 2026-06-04 |
| R4-S1 | `LanguageRegistry/ProviderRegistry.discover()` before live reads | Step 5 | 2026-06-04 |
| R1-S4, R2-S5 | idempotency cursor mirrors SA shape (run_id + checksums) | Step 10 | 2026-06-04 |
| R1-S5 | `protocol_version` | Step 2 | 2026-06-04 |
| R5-S5 | JSON canonical + derived `.md` | Step 2/6 | 2026-06-04 |
| R3-S4 | `.to_prompt_section()` on contracts | Step 2 | 2026-06-04 |
| R1-S6 | artifact-only SA read (no typed import) | Step 7 | 2026-06-04 |
| R3-S1 | `attach_fde_ref_to_triage()` write-back | Step 7 | 2026-06-04 |
| R4-S4 | SA markdown link to explanation | Step 7 (SA-side PR) | 2026-06-04 |
| R5-S1 | `FDE_*_COMPLETE` EventBus + OTel | new Step 7b | 2026-06-04 |
| R1-S3 | Track-2 cost budget + skip | Step 8 | 2026-06-04 |
| R1-S7 | Track-2 non-authoritative disclaimer | Step 8 | 2026-06-04 |
| R2-S3 | Track-2 isolated scratch dir | Step 8 | 2026-06-04 |
| R3-S3 | Track-1 redaction | Step 8 | 2026-06-04 |
| R4-S2 | greenfield tier-prediction guard | Step 8 | 2026-06-04 |
| R2-S4 | `CostTracker` + `--max-cost-usd` | Step 6/8 | 2026-06-04 |
| R2-S2 | feature↔element join | Step 6 | 2026-06-04 |
| R3-S5 | missing-triage degrade + `--allow-no-triage` | Step 6 | 2026-06-04 |
| R1-S9 | legitimate-disagreement branch | Step 6 | 2026-06-04 |
| R5-S4 | `explain --feature-id` | Step 3 | 2026-06-04 |
| R4-S3 | opt-in cap-dev-pipe hook | new Step 12 | 2026-06-04 |
| R1-S11 | logger-policy allowlist as Phase-1 gate | Step 11 (resequenced) | 2026-06-04 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Disposition / Rationale | Date |
|----|------------|--------|-------------------------|------|
| — | (No S-suggestion rejected on merit.) | R1–R5 | All anchored to specific steps and code; accepted and folded into the phase deltas. The corresponding requirements-side dedup (duplicate R3 round) is logged in the requirements Appendix B. | 2026-06-04 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-04

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-04 17:20:00 UTC
- **Scope**: Plan-targeted (S-prefix) external architecture/interface/risk review, weighted to the sponsor focus asks. Focus-ask narrative answers and the F-prefix requirements suggestions live in the requirements file; this block carries plan deltas + the coverage matrix (appended at end of file).

##### Executive summary (top risks / gaps / opportunities)

- The deterministic spine (Phase 2 `sources.py`) is the right ordering, but **`compose.py` (Step 6) is the weakest link**: an unconstrained LLM narrative can emit unlabeled mechanism claims and silently break FR-6 — no guard step in the plan.
- **No artifact-trust step:** Steps 5–6 read `prime-result*.json` / `prime-postmortem-report.json` / SA triage / `.contextcore.yaml` with no schema/version validation before treating them as mechanism truth.
- **Track 2 (Step 8) invokes a full `plan-ingestion` workflow for prediction** with no cost budget, no skip control, and no reconciliation with the operator's later real ingestion — surprise-spend + prediction-divergence risk.
- **Idempotency (Step 10) keys only on (request + SDK version)** — excludes the upstream artifacts the explanation depends on, so a regenerated `prime-result.json` serves a stale answer.
- **No `protocol_version`** in the Step 2 contract — contract-shape changes are indistinguishable from SDK bumps.
- **FR-17 typed-import escape hatch** survives in Step 7 ("`→ TriageReport`") — should be artifact-only to keep the boundary clean.
- Opportunity: the Step 11 §6-coverage test is ~80% of an enforceable FR-6 labeling lint — extend it to also assert emitted `.md` claims are tagged (low effort, closes the FR-6 enforceability gap).

##### Numbered suggestions (S-prefix — plan)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Add a **post-compose labeling guard** sub-step to Step 6: after `compose.py` renders, parse the `.md` and assert every load-bearing line carries `OBSERVED`/`MECHANISM`/`PREDICTION`; fail otherwise. | Step 6 lets an LLM render the narrative with no structural check; this is where FR-6 silently breaks (unlabeled synthesis). | Step 6, after "renders `fde-explanation.md`" | Fixture with an injected untagged claim must fail the guard; clean fixture passes. |
| R1-S2 | Security | high | Insert a new step (Phase 2, before Step 6) that **validates schema/version of every consumed artifact** with a degrade-or-fail policy, since `sources.py` reads them as authoritative. | The plan reads cross-boundary artifacts the FDE did not produce with no trust gate; malformed/old-schema inputs become confident mechanism claims. | New Step 5b under Phase 2 | Feed wrong-schema artifacts; assert labeled degrade/fail, not a fabricated mechanism claim. |
| R1-S3 | Ops | high | Add a **cost budget + skip flag for Track 2** in Step 8; keep Track 1 (cheap prose) always-on. | Step 8 runs a full `plan-ingestion` workflow purely for prediction with no spend guard — same surprise-spend class FR-14 defers, but unguarded. | Step 8, Track 2 bullet | Test: Track 2 skippable; budget breach aborts cleanly; Track 1 still runs. |
| R1-S4 | Data | high | In Step 10, **add consumed-artifact checksums to the idempotency key**, not just (request checksum + SDK version). | A regenerated `prime-result.json` under the same request + SDK version yields a stale cached explanation; the changed input is excluded from the key. | Step 10, "keyed by (request-artifact checksum + SDK version)" | Change only `prime-result.json`; assert recompute, not cache hit. |
| R1-S5 | Interfaces | high | In Step 2, add a `protocol_version` field to the contract pair, distinct from the SDK-version staleness stamp. | The plan's only version is the SDK stamp (Step 9); contract-shape changes are indistinguishable from SDK bumps, breaking compat detection. | Step 2, contract definition | Round-trip test preserves `protocol_version`; a shape change bumps it; old `.md` errors clearly on mismatch. |
| R1-S6 | Interfaces | medium | In Step 7, remove the typed-`TriageReport`-import option and make `assistant_bridge.py` read SA **only** via the JSON artifact; keep `FdeRef` defined in `service_assistant/models.py`. | Step 7's typed read couples `fde`↔`service_assistant` build/refactor cadence (soft version-lockstep); FR-4 already mandates the artifact read. | Step 7, "Load `service-assistant-triage.json` → `TriageReport`" | Lint: `src/startd8/fde/` has no import of `service_assistant.models`; `FdeRef` defined only under `service_assistant/`. |
| R1-S7 | Risks | medium | In Step 8, mark Track 2's ingestion output **preflight-only / non-authoritative** and require a divergence disclaimer in `fde-preflight.md`; never write it to a path the real pipeline ingests. | `plan-ingestion` is nondeterministic; preflight + real ingestion can diverge, so reusing preflight features as ground truth misleads. | Step 8, Track 2 + Step 9 placement | Test: preflight output lands only in `fde-preflight.md`; disclaimer present; not consumed by the real run. |
| R1-S8 | Validation | medium | Extend the Step 11 §6-coverage test into a **labeling-lint** that also asserts emitted `.md` load-bearing lines are tagged (reuses the same parse). | The coverage test already walks §6 sources; adding the emitted-claim tag check is low effort and makes FR-6 enforceable (Lens 1 low-hanging fruit). | Step 11, "coverage test that every §6 mechanism question has a reader" | CI: untagged-claim fixture fails; tagged fixture passes; both run in the existing test. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S9 | Architecture | medium | Add a Step 6 branch for **legitimate SA↔mechanism disagreement** (both halves correct, pointing different ways), not just SA-misattribution (FR-7). | Step 6 only detects SA being *wrong*; it has no path for presenting two valid-but-divergent halves, risking a silent solo verdict (violates NR-7/FR-6). | Step 6, FR-7 detection bullet | Fixture: valid SA evidence + valid divergent mechanism; assert both labeled, no winner picked. |
| R1-S10 | Data | medium | In Step 5, define the **double-absence fallback** for `read_element_data` (both post-mortem and raw nesting missing/empty, e.g. all-cache or pre-micro-prime runs). | OQ-2' fixed the happy path + single fallback; the plan does not handle both surfaces missing or empty `element_results[]`. | Step 5, `read_element_data` bullet | Test run dir missing both surfaces + one with empty `element_results[]`; assert labeled "mechanism unavailable", no crash/fabrication. |
| R1-S11 | Ops | low | Sequence the **logger-policy allowlist update (Step 11) as a Phase 1 gate**, not a final-phase task, since every new `fde/*.py` file added in Phases 1–5 trips the policy test. | Per CLAUDE.md "Must Avoid", new files using string logger names break `test_logger_acquisition_policy.py`; doing it last means Phases 1–5 land red. | Step 11 / move to Phase 1 | Run `test_logger_acquisition_policy.py` after Phase 1; green before later phases. |

**Endorsements**: none (R1 is the first round).
**Disagreements**: none (no prior rounds).

---

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-04

**Scope:** Second-pass dual-document review. Deduped against R1-S1…S11 and R1 focus-ask narrative (requirements file). Grounded in live code: `ElementPostMortem` (`prime_postmortem.py:361-377`), `FailureTriage` (`service_assistant/models.py:80-92`), SA cursor (`detector.py:210-249`), no `src/startd8/fde/` package yet. Focus: second-order impedance mismatches R1 assumed were already resolved by planning.

**Executive summary:** The §6 source-of-truth table names `ElementPostMortem` as the preferred explain surface, but post-mortem flattening **drops `generation_strategy`** (only `template_used` survives) — the plan's Step 5 happy path cannot answer "which micro-prime path ran" without always falling back to raw `prime-result*.json`. Explain mode also lacks a **feature↔element join** (SA triage is per-feature; mechanism is per-element). Track 2 must isolate `plan-ingestion` side effects to a scratch dir under `.startd8/fde/`.

| ID | Area | Severity | Summary |
|----|------|----------|---------|
| R2-S1 | Data | critical | Step 5: `ElementPostMortem` lacks `generation_strategy` — §6 "preferred surface" is incomplete |
| R2-S2 | Architecture | high | Step 6: define feature↔element join (`FailureTriage.element_id` / `file` → `ElementPostMortem`) |
| R2-S3 | Risks | high | Step 8 Track 2: isolate `plan-ingestion` output to `.startd8/fde/preflight-scratch/` (no pipeline pollution) |
| R2-S4 | Ops | medium | Step 8/6: wire LLM calls through `CostTracker` with per-invocation budget (operator-triggered spend) |
| R2-S5 | Ops | medium | Step 10: mirror SA cursor shape (`run_id` + checksum map), not only request-md + SDK version |

---

#### R2-S1 — Data — critical
**Anchor:** Plan Step 5, `read_element_data` bullet ("prefer `prime-postmortem-report.json` (`ElementPostMortem` …)") / Requirements §6 row "Did micro-prime run / which path?"

**Finding:** FR-5 and §6 pin `ElementResult.generation_strategy` (`micro_prime/models.py:246`) as the authoritative answer to "which path ran." `ElementPostMortem` — the post-mortem's flattened element record (`prime_postmortem.py:1798-1812`) copies `tier`, `repair_steps`, `template_used`, and `repair_attribution`, but **never copies `generation_strategy`**. The only partial proxy is `template_used: bool`. A plan that "prefers post-mortem" therefore **cannot** satisfy the §6 row without silently degrading to raw JSON on every explain, or mis-labeling `template_used=True` as "template path" when the actual strategy was `llm_simple` or `cache:*`.

**Suggestion:** In Step 5, split `read_element_data` into explicit tiers: (1) read `ElementPostMortem` for tier/repair/escalation; (2) **require** `generation_strategy` from `prime-result*.json` nesting when present; (3) document that post-mortem-only runs report `generation_strategy` as `MECHANISM (sdk, unavailable on flattened surface)` unless/until `ElementPostMortem` gains the field (optional fast follow: one-line addition in `prime_postmortem.py` when building elements). Add a unit test: fixture with `generation_strategy="llm_simple"` in raw JSON but absent on `ElementPostMortem` — assert explain cites the raw path, not `template_used`.

**Expected impact:** Closes the largest impedance mismatch between requirements §6 and the "preferred surface" plan. Prevents wrong mechanism claims on the common post-mortem-only path.

---

#### R2-S2 — Architecture — high
**Anchor:** Plan Step 6 ("For each `FailureTriage`, read mechanism from `sources.py`") / `FailureTriage` (`service_assistant/models.py:88-89`)

**Finding:** SA `FailureTriage` is **feature-scoped** (`feature_id`, optional `element_id`, optional `file`). SDK mechanism facts are **element-scoped** (`ElementPostMortem` / `ElementResult` per element within a feature). Step 6 loops "for each failure" but does not specify how to select the element row when a feature has multiple elements (common in MODERATE/COMPLEX tasks). Without a join rule, explain mode will either pick an arbitrary first element or aggregate incorrectly — reproducing the "altitude" failure mode the controlled-corpus SCR work flagged (feature vs element).

**Suggestion:** Add to Step 6: "Join rule: if `FailureTriage.element_id` or `FailureTriage.file` is set, select the matching `ElementPostMortem`/`ElementResult`; else if exactly one element exists for the feature, use it; else emit a composed report section listing **all** elements with per-element mechanism blocks (no silent pick-first)." Mirror SA's existing optional `element_id`/`file` fields in the explain fixture tests.

**Expected impact:** Makes explain output trustworthy for multi-element features. Low effort — uses fields SA already emits.

---

#### R2-S3 — Risks — high
**Anchor:** Plan Step 8, Track 2 ("`WorkflowRegistry.run_workflow("plan-ingestion", …)` → features") / Reuse map

**Finding:** `plan-ingestion` writes `prime-context-seed.json`, diagnostics, and other artifacts into its configured `output_dir`. If Track 2 uses the project's real cap-dev-pipe output directory (or the operator's upcoming run directory), preflight **mutates the same tree** the real pipeline will use — even with R1-S7's "non-authoritative" disclaimer, files on disk create confusion and race risk. R1-S7 covers semantic non-authority; this is the **filesystem side-effect** gap.

**Suggestion:** Step 8 Track 2 MUST pass an isolated `output_dir` under `.startd8/fde/preflight-scratch/<request-checksum>/` (created per preflight invocation, gitignored). Never pass the operator's pipeline-output run dir. Document in Step 9 placement: only `fde-preflight.md` (project-scoped) is durable output; scratch dir is ephemeral. Test: run Track 2; assert no `prime-context-seed.json` appears in the operator's target run directory.

**Expected impact:** Operational quick win — prevents preflight from clobbering or pre-seeding the real ingestion path. Complements R1-S7/R1-F7.

---

#### R2-S4 — Ops — medium
**Anchor:** Plan arch note ("LLM is only invoked by `preflight.py` and `compose.py`") / FR-14 (auto-launch deferred)

**Finding:** FR-14 defers SA auto-launch but allows operator/agent invocation — unbounded LLM spend on Track 1 + compose + optional Track 2. The SDK already has `CostTracker` and cost overlays in SA (`operational_actions.py:apply_cost_overlay`). The plan does not wire FDE LLM calls into that stack, so preflight/explain costs are invisible and cannot be capped per invocation.

**Suggestion:** Add Step 8b / extend Step 6: all FDE LLM entry points accept `--max-cost-usd` (default from env `STARTD8_FDE_MAX_COST_USD`) and record spend via `CostTracker` (same pattern as `run_semantic_compliance`). Emit `fde.cost_usd` in the explanation/preflight footer. Track 2 aborts before `plan-ingestion` if budget is already exhausted by Track 1.

**Expected impact:** Closes the "surprise spend when operator pulls the trigger" gap left open by FR-14 deferral alone. Reuses existing cost infrastructure — low hanging fruit.

---

#### R2-S5 — Ops — medium
**Anchor:** Plan Step 10 ("idempotency keyed by (request-artifact checksum + SDK version)") / SA `detector.py:229-249`

**Finding:** SA idempotency uses a **cursor file** at the pipeline-output base with a `processed` map keyed by `run_id` → `{checksum, status, processed_at}` — not merely "request md + SDK version." FDE explain idempotency should key on the **run being explained** (`stable_run_id` from output dir) plus checksums of `service-assistant-triage.json` and consumed mechanism artifacts (R1-S4). Step 10 as written omits `run_id`, so two different failures with the same `fde-request.md` text would incorrectly cache-hit.

**Suggestion:** Reshape Step 10: `fde-cursor.json` mirrors SA — `processed: { "<run_id>": { "request_checksum", "triage_checksum", "mechanism_checksum", "sdk_version", "processed_at" } }`. Explain mode keys on `run_id`; preflight keys on `(plan_path_checksum, requirements_path_checksum, sdk_version)`. Cross-reference SA's `cursor_path_for()` placement logic.

**Expected impact:** Correct idempotency semantics for the dominant explain path. Aligns with proven SA ops pattern.

---

**Endorsements:**
- R1-S1 (post-compose labeling guard) — still required for FR-6 enforceability.
- R1-S4 / R1-F12 (consumed-artifact checksums in idempotency key) — pairs with R2-S5.
- R1-S11 (logger allowlist in Phase 1) — agree; `src/startd8/fde/` does not exist yet; gate before Phase 2.

**Disagreements:** none.

---

#### Review Round R3 — claude-sonnet-4-6 — 2026-06-04

**Scope:** Third-pass dual-document review. Deduped against R1–R2. `src/startd8/fde/` still absent. New territory: FR-17 ref **write-back** orchestration, SCR↔FDE three-way composition, deterministic vs LLM compose split, and preflight redaction (focus ask #6 extension).

**Executive summary:** FR-17 defines an optional `fde_explanation` ref on `TriageReport`, but neither the plan nor SA today has a step that **writes that ref back** after `fde-explanation.md` is produced — the handshake is half-specified. The zero-LLM explain path (FR-15) needs a **structural** template renderer, not a hope that `compose.py` skips the LLM. Track 1 preflight sends raw plan markdown to an LLM with no redaction step, unlike the SCR.

| ID | Area | Severity | Summary |
|----|------|----------|---------|
| R3-S1 | Interfaces | high | Step 7: add atomic `attach_fde_ref_to_triage()` after explain — FR-17 ref otherwise never lands |
| R3-S2 | Architecture | high | Step 6: split `deterministic_compose.py` (template from labeled facts) from `compose.py` (LLM narrative) |
| R3-S3 | Security | medium | Step 8 Track 1: redact plan/requirements before LLM (reuse SCR/security patterns) |
| R3-S4 | Interfaces | medium | Step 2: require `.to_prompt_section()` on contracts (Keiyaku K-6…K-10 parity) |
| R3-S5 | Validation | medium | Step 6: explain requires SA triage or explicit `--allow-no-triage` degrade path |

---

#### R3-S1 — Interfaces — high
**Anchor:** Plan Step 7 (`assistant_bridge.py` … "SA (or the operator) attaches the ref") / FR-17

**Finding:** The lifecycle is: (1) SA writes `service-assistant-triage.json` (no `fde_explanation` yet); (2) FDE writes `fde-explanation.md` beside it; (3) **someone** must patch the triage JSON with `{path, checksum}`. Step 7 defers step 3 to "SA or the operator" without an SDK function or CLI subcommand. In practice the ref will never appear unless documented manual edit occurs — FR-17's consumer value (downstream tools reading one triage file) is lost.

**Suggestion:** Add to Step 7: `attach_fde_ref_to_triage(run_output_dir) -> None` in `assistant_bridge.py`: after `fde-explanation.md` is written, compute SHA-256, load `service-assistant-triage.json`, set `fde_explanation` (new `FdeRef` in `service_assistant/models.py`), atomic-write back (same pattern as SA cursor). `explain` command calls this automatically; expose `startd8 fde attach-ref` for repair. Test: explain run → triage JSON contains ref with matching checksum.

**Expected impact:** Closes the FR-17 handshake loop. Low effort (~30 lines), high end-user value — one artifact to open in Grafana/IDE.

---

#### R3-S2 — Architecture — high
**Anchor:** Plan Step 6 ("**Zero-LLM path** when no assumption-detection is needed (FR-15)") / arch note ("LLM is only invoked by `preflight.py` and `compose.py`")

**Finding:** FR-15 requires a zero-LLM explain path, but Step 6 routes all narrative through `compose.py`, which is described as the LLM narrative step. Without a **separate code path**, implementers will add `if not needs_llm` branches inside `compose.py` that still share prompt assembly — the first refactor that "just calls the LLM for polish" breaks FR-15 silently (R1-F6). The SCR separates `report.py` (deterministic render) from LLM orchestration.

**Suggestion:** Split Step 6: `deterministic_compose.py` — pure template renderer that takes `List[LabeledClaim]` from `sources.py` and emits `fde-explanation.md` (tables + tagged bullets, no agent call). `compose.py` — optional LLM polish **only** when `--narrative=enhance` and budget allows; must pass output through R1-S1 labeling guard. Default `explain` uses `deterministic_compose` only. Rename in plan arch diagram.

**Expected impact:** Makes FR-15 testable by construction (`compose.py` not imported on zero-LLM path). Quick win — copy SCR `report.py` pattern.

---

#### R3-S3 — Security — medium
**Anchor:** Plan Step 8 Track 1 ("LLM reads raw plan/requirements markdown") / focus ask #6

**Finding:** Track 1 sends full plan/requirements prose to an LLM. Plans often embed credentials, internal URLs, or customer data in examples. The SCR pipeline redacts generated code in prompts (`semantic_compliance/prompts.py`); the FDE plan has no analogous gate for **inbound** plan text. Reading artifacts with `sanitize_path` (R1-S2) does not redact **content**.

**Suggestion:** Add Step 8a: before Track 1 LLM call, run plan/requirements through a shared redaction helper (reuse `security.py` patterns + SCR delimiter blocks; strip lines matching credential/env-var heuristics). Emit a `redaction_manifest` section in `fde-preflight.md` listing what was stripped. Track 1 operates on redacted text only; original paths never sent to the model.

**Expected impact:** Closes a trust-boundary gap for cross-boundary LLM reads. Operational hygiene with minimal new code.

---

#### R3-S4 — Interfaces — medium
**Anchor:** Plan Step 2 ("`.to_dict()` / `.from_json()` / `.to_markdown()`") / FR-12

**Finding:** Keiyaku contracts in the SDK (`SemanticVerificationResult`, `ClassificationResult`) implement `.to_prompt_section()` for bounded prompt injection. Step 2 omits it for `FdeRequest`/`FdeExplanation`. FR-12 says the contract may ride EventBus "when a transport materializes" — without `to_prompt_section()`, the only transport-ready surface is JSON or lossy markdown.

**Suggestion:** Add to Step 2: each contract implements `.to_prompt_section() -> str` with a fixed header (`## FDE Explanation (sdk mechanism authority)`). Phase 1 test: section is under a token budget and contains only pre-labeled claims (no free prose). Document in FR-12 as required, not optional.

**Expected impact:** Future-proofs EventBus/SA auto-launch without another contract revision. Aligns with existing Keiyaku pattern.

---

#### R3-S5 — Validation — medium
**Anchor:** Plan Step 6 ("Load `service-assistant-triage.json`") / FR-4

**Finding:** FR-4 mandates SA triage as the EVIDENCE half. Operators will run `startd8 fde explain --run-dir …` on a run that has `prime-postmortem-report.json` but **no** `service-assistant-triage.json` (SA hook skipped or failed). Step 6 does not specify behavior — crash vs partial report vs auto-invoke SA.

**Suggestion:** Step 6 opening: if triage JSON is missing, default to **degraded explain** — MECHANISM-only `fde-explanation.md` with a top banner `OBSERVED (project): unavailable — run startd8 assist first` and exit code 2 from CLI (not shim). Opt-in `--allow-no-triage` for automation. Do **not** silently re-run SA inside explain (surprise side effects). Test both paths.

**Expected impact:** Predictable operator UX. Avoids false composed reports that read as full Tekizai-Tekisho when half the composition is absent.

---

**Endorsements:**
- R2-S1 / R2-F2 (`generation_strategy` / `ElementPostMortem` gap) — still blocking for accurate explain.
- R3-S1 pairs with R1-F2 (`FdeRef` ownership in SA models).
- R1-S1 (labeling guard) — applies to any `compose.py` LLM path after R3-S2 split.

**Disagreements:** none.

---

#### Review Round R4 — claude-sonnet-4-6 — 2026-06-04

**Scope:** Fourth-pass dual-document review. Deduped against R1–R3. `src/startd8/fde/` still unimplemented. New territory: registry discovery prerequisites, Track 2 signal quality on greenfield plans, batch-level SA patterns, cap-dev-pipe integration, and end-user discoverability (markdown links).

**Executive summary:** Track 2 preflight calls `extract_signals_from_feature(project_root, …)` which reads **on-disk** files — for plans that have not been built yet, tier predictions will be junk unless the plan states the limitation. FR-14's trigger is narrower than SA's actual remediation vocabulary (not only `deterministic`). The plan has no **cap-dev-pipe hook** step, so FDE never runs in the default operator workflow.

| ID | Area | Severity | Summary |
|----|------|----------|---------|
| R4-S1 | Architecture | high | Step 5/8: call `LanguageRegistry.discover()` + `ProviderRegistry.discover()` before live reads |
| R4-S2 | Risks | high | Step 8 Track 2: document/skip tier prediction when `target_files` absent on disk (greenfield) |
| R4-S3 | Ops | medium | New Step 12: cap-dev-pipe hook after SA (`run_fde.py` shim) — FDE not in default workflow |
| R4-S4 | Interfaces | medium | Step 7 + SA `_render_markdown`: link to `fde-explanation.md` when `fde_explanation` ref present |
| R4-S5 | Validation | medium | Step 11: `test_sources_coverage.py` + lint that `sources.py` imports no LLM providers |

---

#### R4-S1 — Architecture — high
**Anchor:** Plan Step 5 (`classify_live`, `language_capability`, `resolve_model_by_tier`) / Step 8 Track 2

**Finding:** Live preflight reads use `LanguageRegistry.get()`, `get_latest_model()`, and `classify_tier()`. Per SDK conventions (`CLAUDE.md` Must Do), registries require explicit `discover()` before use. The plan does not mention this — first FDE invocation in a fresh process will hit empty registries or stale entry-point state, producing false landmines ("language unsupported") or wrong tier defaults.

**Suggestion:** Add to Step 5 module docstring and `preflight.py` entry: `LanguageRegistry.discover(); ProviderRegistry.discover()` before any live call. Step 11 test: assert discover is invoked (mock registry empty without discover → non-empty after). One line, prevents an entire class of false positives.

**Expected impact:** Low-hanging fruit — matches every other SDK consumer. Required for trustworthy Track 2.

---

#### R4-S2 — Risks — high
**Anchor:** Plan Step 8 Track 2 ("`extract_signals_from_feature()` → `classify_live()`") / `complexity/signals.py:95-120`

**Finding:** `extract_signals_from_feature(feature, project_root, …)` inspects `target_files` against **files on disk** under `project_root` (blast radius, MRO depth, cross-file edges). Plan-ingestion features for a **pre-implementation** plan often list paths that do not exist yet. Signals then default to zeros/false — `classify_tier()` still returns a tier, but it is **low-confidence fiction**. FR-8 does not distinguish "prediction from real AST" vs "prediction from plan text only." This is the second-order flaw in focus ask #4 (tier prediction soundness).

**Suggestion:** Step 8 Track 2: after ingestion, partition features into `on_disk` (≥1 existing `target_file`) vs `plan_only`. Run `classify_live` only for `on_disk`; for `plan_only`, emit landmines from Track 1 prose only and tag any tier guess as `PREDICTION (sdk, low-confidence — file not materialized)`. Add to `fde-preflight.md` summary counts. Test: feature with hypothetical path → no tier landmine from Track 2.

**Expected impact:** Honest preflight on greenfield plans — major end-user trust win. Avoids "the FDE said MODERATE" when the classifier had no signal.

---

#### R4-S3 — Ops — medium
**Anchor:** Plan Step 4 (`scripts/run_fde.py` shim) / SA integration (`scripts/run_service_assistant.py`)

**Finding:** SA is wired into cap-dev-pipe post-postmortem via `run_service_assistant.py`. The plan defines `run_fde.py` but has **no integration step** — operators who only use the pipeline never get `fde-explanation.md` or triage ref write-back unless they manually run `startd8 fde explain`. FR-14's deferred auto-launch is correct, but v1 should still **offer** a one-command hook after SA (opt-in via env `STARTD8_FDE_AFTER_ASSIST=1` or pipeline.env flag).

**Suggestion:** Add **Step 12 (integration):** document `.cap-dev-pipe/pipeline.env` flag; shim invoked after `run_service_assistant.py` when flag set and `FailureTriage` trigger matches (deterministic or mechanism-dependent recommendation). Shim remains exit-0; logs "FDE skipped — no trigger." Requirements cross-ref in FR-14 as optional hook, not auto-launch.

**Expected impact:** Delivers end-user value in the default workflow without surprise spend (off by default).

---

#### R4-S4 — Interfaces — medium
**Anchor:** Plan Step 7 / `service_assistant/assistant.py:_render_markdown` (lines 194-217)

**Finding:** SA already renders `service-assistant-triage.md` with failure tables and cross-feature patterns. When `fde_explanation` is attached to triage JSON (R3-S1), operators still must know to open a second file. The SCR pattern folds a summary into triage markdown via `semantic_review` — FDE should get the same discoverability.

**Suggestion:** Step 7 includes an SA-side one-line addition (separate small PR): if `report.fde_explanation` is set, append to `_render_markdown`: `**FDE mechanism explanation:** [open]({path}) (checksum …)`. FDE package only writes the ref; SA owns markdown rendering (no import cycle). Test in `test_assistant.py`.

**Expected impact:** Quick win — operators see the FDE link in the triage they already open.

---

#### R4-S5 — Validation — medium
**Anchor:** Plan Step 11 ("coverage test that every §6 mechanism question has a `sources.py` reader")

**Finding:** Step 11 proposes a §6 coverage test (good) but not a **dependency boundary** test. FR-15 requires mechanism facts without LLM; a single `from startd8.agents import …` in `sources.py` violates the architecture. SCR separates orchestrator from prompts; FDE should separate `sources.py` / `deterministic_compose.py` from `compose.py` / `preflight.py` at import level.

**Suggestion:** Extend Step 11: (1) `test_sources_coverage.py` — one test per §6 row (mirror `test_operational_action_coverage.py`); (2) `test_sources_has_no_llm_imports` — ast/grep guard that `sources.py` and `deterministic_compose.py` do not import provider/agent modules; (3) optional `test_explain_cli_help` — `startd8 fde --help` after Phase 1. Add `tests/unit/fde/` to pytest layout in plan.

**Expected impact:** Enforces FR-15 structurally, not only by convention.

---

**Endorsements:**
- R3-S1 / R3-F1 (triage ref write-back) — required for R4-S4 link to work.
- R2-S3 (preflight scratch dir) — pairs with R4-S2 (don't pollute real dirs with junk predictions).
- R1-S3 (Track 2 cost budget) — pairs with R4-S3 opt-in hook.

**Disagreements:** none.

---

#### Review Round R5 — claude-sonnet-4-6 — 2026-06-03

**Scope:** Fifth-pass plan review. Deduped against R1–R4. Second-order: OTel/EventBus observability (focus ask #2), FR-6 enforceability via compose structure (ask #5), artifact-freshness guards, operator-scoped explain CLI, canonical JSON sidecar.

**Executive summary:** SA and SCR already emit `EventBus` + `OTelEventBridge` events; the FDE plan has no equivalent — operators relying on Loki/Tempo will not see explain/preflight completion. `compose.py` is described only as "narrative," leaving FR-6 labeling aspirational despite R1's lint idea. Post-mortem vs raw `prime-result` can disagree silently.

| ID | Area | Severity | Summary |
|----|------|----------|---------|
| R5-S1 | Ops | medium | Step 7: emit `FDE_EXPLAIN_COMPLETE` / `FDE_PREFLIGHT_COMPLETE` via EventBus + OTel bridge |
| R5-S2 | Validation | high | Step 6: `compose.py` slot-based sections — mechanism facts injected deterministically, LLM only bridges prose |
| R5-S3 | Data | medium | Step 5: freshness guard when post-mortem and raw JSON both present (checksum / mtime) |
| R5-S4 | Ops | low | Step 3 CLI: `explain --feature-id` to scope multi-failure triage |
| R5-S5 | Interfaces | medium | Step 2: write `fde-explanation.json` (canonical) + derived `.md` (FR-11/FR-12) |

---

#### R5-S1 — Ops — medium
**Anchor:** Plan Step 7 (`assistant_bridge.py`) / `service_assistant/notify.py:32-71` / `semantic_compliance/orchestrator.py:248-267`

**Finding:** Service Assistant fires `RUN_DETECTED` / `POSTMORTEM_AVAILABLE` / `RUN_FAILED` through `EventBus` with `OTelEventBridge.activate()`. Semantic Compliance emits `SEMANTIC_REVIEW_COMPLETE`. The FDE plan has no event emission — explain/preflight completion is invisible to the observability stack operators already use for SA/SCR triage. Focus ask #2 notes EventBus is fire-and-forget with no resident consumer; that is fine for v1 — **OTel bridge subscribers** are the consumer.

**Suggestion:** Add Step 7b `fde/notify.py` (mirror SA): after successful explain/preflight, `EventBus.emit(Event(type=EventType.FDE_EXPLAIN_COMPLETE | FDE_PREFLIGHT_COMPLETE, …))` with `{run_id, output_dir, report_path, mode, cost_usd}`. Register new `EventType` values in `events/types.py`. Unit test asserts bridge activation is attempted (mock `OTelEventBridge`). Document in cap-dev-pipe hook (R4-S3) log line: "FDE event emitted."

**Expected impact:** Low effort — copy existing pattern. End-user value in Grafana/Loki dashboards without opening markdown files.

---

#### R5-S2 — Validation — high
**Anchor:** Plan Step 6 (`compose.py` renders `fde-explanation.md`) / FR-6 labeling guarantee (focus ask #5)

**Finding:** R1 flagged FR-6 as non-enforceable and proposed a post-hoc markdown lint. Second-order: if `compose.py` lets the LLM author the full document, the lint becomes whack-a-mole. Keiyaku contracts elsewhere inject **structured sections** (`to_prompt_section()`); the durable pattern is: deterministic facts → fixed labeled slots → optional LLM glue text between slots.

**Suggestion:** Step 6: `compose.py` builds from a template with mandatory blocks per failure: `## OBSERVED (project)`, `## MECHANISM (sdk)` (pre-filled from `sources.py` / `deterministic_compose.py`), then optional `## Narrative` where LLM may only reference claim ids already emitted above. Step 11: `test_compose_no_unlabeled_mechanism_claims` — regex on MECHANISM blocks only (LLM narrative section excluded from mechanism authority). Pairs with R4-S5 import guard.

**Expected impact:** Makes FR-6 enforceable at generation time, not review time. Reduces unlabeled synthesis risk from focus ask #5.

---

#### R5-S3 — Data — medium
**Anchor:** Plan Step 5 (`read_element_data` prefer post-mortem, fall back raw) / `prime_postmortem.py:361-376`

**Finding:** Step 5 prefers `prime-postmortem-report.json` then falls back to `prime-result*.json`. Nothing prevents **stale pairing**: post-mortem from run N while raw JSON is from a partial re-run or manual copy. R2-S1 covers missing `generation_strategy` on the flattened surface; this is the **consistency** failure when both files exist but disagree on `tier` or `repair_steps`.

**Suggestion:** Step 5: when both surfaces exist for the same `(feature_id, element_name)`, compare `tier` + `repair_steps` (and `generation_strategy` when raw-only). On mismatch, emit `MECHANISM (sdk, conflict)` banner citing both paths + file mtimes; prefer raw for strategy, post-mortem for classified `root_cause`. Test: fixture with divergent tier values → explanation contains conflict banner, does not silently pick one.

**Expected impact:** Robustness for operators who re-run post-mortem without re-running prime. Prevents wrong mechanism authority.

---

#### R5-S4 — Ops — low
**Anchor:** Plan Step 3 (`cli_fde.py` — commands `explain`, `preflight`, `init`)

**Finding:** SA triage on a batch run can list dozens of `FailureTriage` rows. Re-explaining the entire set is slow and noisy. No plan step scopes explain to one feature — yet `FailureTriage.feature_id` is always present (`service_assistant/models.py`).

**Suggestion:** Step 3: add `startd8 fde explain --output-dir … --feature-id <id>` (repeatable). Step 6 filters triage failures before compose. Default (no flag) explains all mechanism-triggered failures. Document in `fde-request.md` inbound schema (endorse R2-F4).

**Expected impact:** Quick win for operators debugging one failed feature in a large batch.

---

#### R5-S5 — Interfaces — medium
**Anchor:** Plan Step 2 (`models.py` — `.to_markdown()` serializers) / R1-F4 (authoritative vs derived `.md`)

**Finding:** R1-F4 remains untriaged: `.md` round-trip is lossy. Step 2 implements `.to_markdown()` only. Downstream agents that want machine consumption will parse markdown tables — fragile. SCR already writes `semantic-compliance-report.json` alongside markdown.

**Suggestion:** Step 2 + Step 6: always write **`fde-explanation.json`** / **`fde-preflight.json`** via `.to_dict()` (canonical Keiyaku contract); `.md` is a derived human view (`to_markdown()` from the dict). Step 11: golden round-trip `to_dict → from_json` without touching markdown. Declare in Step 2 docstring: "JSON authoritative; markdown derived (lossy)."

**Expected impact:** Closes FR-12 transport story for v1 (JSON rides files/API; EventBus carries dict payload). Enables programmatic consumers without `from_markdown()`.

---

**Endorsements:**
- R1-F3 / R1-S5 (`protocol_version`) — JSON sidecar carries it cleanly.
- R1-F10 (labeling lint) — R5-S2 is the structural fix; lint remains a backstop.
- R4-S3 (cap-dev-pipe hook) — pairs with R5-S1 observability.

**Disagreements:** none.

---

## Requirements Coverage Matrix — R1

> Analysis only (not triage). Maps each requirement to the plan step(s) that implement it. `Partial`/`Gap` rows reference the R1 suggestion that proposes closing the gap.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 SDK-resident brain | Step 1, 3, 4 | Full | — |
| FR-2 Project-deployed posting (scope-split) | Step 9 | Full | — |
| FR-3 Mechanism authority is code | Step 5 | Partial | No artifact trust/schema validation before treating reads as authoritative (R1-S2 / R1-F11). |
| FR-4 Consume SA evidence | Step 6 (load triage) | Full | — |
| FR-5 Supply SDK-mechanism authority (concrete sources) | Step 5, 6 | Partial | Double-absence fallback for `read_element_data` undefined (R1-S10 / R1-F14). |
| FR-6 Composed, source-labeled report | Step 6 (compose) | Partial | No post-compose labeling guard; no `PREDICTION` label; FR-6 not enforceable (R1-S1, R1-S8 / R1-F5, R1-F9, R1-F10). |
| FR-7 Correct, not just relay | Step 6 (detect misattribution) | Partial | No path for legitimate SA↔mechanism disagreement (both valid) (R1-S9 / R1-F13). |
| FR-8 Two-track preflight lens | Step 8 | Partial | No Track 2 cost budget/skip; preflight-vs-real ingestion reconciliation/disclaimer missing (R1-S3, R1-S7 / R1-F7, R1-F8). |
| FR-9 Reuse review machinery (library) | Step 8, Reuse map | Full | — |
| FR-10 Landmine taxonomy mechanism-grounded | Step 8 (names §6 source per landmine) | Full | — |
| FR-11 `.md` file protocol (v1) | Step 2 (`.md` serializers) | Partial | `.md` authoritative-vs-derived + round-trip status undeclared (R1-F4). |
| FR-12 Keiyaku-shaped, transport-agnostic contract | Step 2 | Partial | No `protocol_version` distinct from SDK version (R1-S5 / R1-F3). |
| FR-13 Idempotent, one-shot | Step 4, 10 | Partial | Key excludes consumed-artifact checksums (R1-S4 / R1-F12). |
| FR-14 SA triggers FDE (handshake, auto-launch deferred) | Step 7 | Full | — |
| FR-15 Deterministic-first core | Step 5 (sources), Step 6 (zero-LLM path), arch note | Partial | Narrative step (b) unconstrained; zero-LLM path lacks an acceptance test (R1-S1 / R1-F5, R1-F6). |
| FR-16 Two read modes (artifact vs live) | Step 5, 6 (explain), Step 8 (preflight) | Partial | Prediction not labeled distinctly from recorded mechanism (R1-F9). |
| FR-17 FDE ref from SA triage (no import cycle) | Step 7 | Partial | Typed-import option leaves a soft version-lockstep; `FdeRef` owner/location not pinned (R1-S6 / R1-F1, R1-F2). |
| NR-1…NR-7 (non-requirements) | Honored implicitly (one-shot, no daemon, no auto-remediation, reuse) | Full | — |
