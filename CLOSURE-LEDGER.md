# Closure Ledger — startd8-sdk

> The project's brain. One table of every open loop, one law (**WIP=1**), one honest
> maturity number. Seeded 2026-07-15 by a grounded four-gate closure scan (see the DEV-OS
> docs at `dev/dev-os/`). Every row below was **grounded against the real code** — the raw
> scan over-reported ~40 hits; grounding deflated them to the loops here and corrected two
> "dead code" false-positives in both directions.

> **Coverage correction (2026-07-15, data-artifact pass):** the initial scan swept code
> value-paths and **under-inventoried data artifacts** — it missed the SDK's corpus files
> entirely (`golden_corpus/corpus.json`, `.startd8/controlled-corpus.json`). That is a
> **scoped-coverage false-negative** — looking only at code, and (earlier) searching a
> *consuming* project (`online-boutique-demo`) instead of system-wide for where the data
> actually lives — the mirror image of the false-*positives* the grounding pass corrected.
> The corpus inventory now lives in "Corpus / data artifacts" below.

**Maturity of this repo:** **L2** — *set by the lowest open loop (CL-2 dead CLI flag / CL-3 un-wired adapter). The core generation pipeline is L4-live; the L2 items are isolated, minor surfaces — but honesty = lowest open loop, no rounding up.*
**Loops in flight:** 0 — *WIP=1: pick one, close or park it, before opening another.*
**Last grounded:** 2026-07-15

---

## The four maturity gates (cost DECREASES down the list)

| Level | Gate | Meaning | Cost |
|:--:|------|---------|------|
| **L0** | idea | not started | — |
| **L1** | drafted | spec/design exists, no code | — |
| **L2** | **un-wired** | code doesn't exist / isn't called anywhere | **highest** (real implementation) |
| **L3** | **un-validated** | wired, but never proven correct | run a check — *hunt for a free/offline gate first* |
| **L4** | **un-enabled** | wired + valid, gated behind a default-off flag/config | flip a flag + smoke test |
| **L5** | **un-recorded → done** | wired, valid, enabled — only a stale doc says otherwise | fix a comment (cheapest) |

> **Ground before you trust a level.** Every row is a *hypothesis*. Before believing
> "dormant/missing/not-wired," `grep` who CALLS the symbol across the **whole** codebase —
> not one module, not the docstring. The map lags the territory in *both* directions.

---

## Open loops

| ID | Artifact | What it is | Now | Gate to next level | Value if closed |
|----|----------|-----------|:--:|-------------------|-----------------|
| CL-1 | `providers/{anthropic,openai,gemini,protocol}.py` | Load-bearing LLM provider integrations with **zero unit tests** (only deepseek/openrouter/jetson are covered) | **L3** | Add mock-transport unit tests for each provider + the base `Provider` protocol → L5. **Highest-value loop — correctness of the core LLM layer is unproven.** | The generation substrate is validated, not assumed |
| CL-2 | `cli_tsdb.py:103` — `--reduce` | Declared CLI flag (FR-5 cardinality reduction) that is **refused at runtime** ("not yet implemented, deferred M2") | **L2** | Implement FR-5 **or** remove the flag + help text (don't ship a surface that only errors) | No dead/lying CLI surface |
| CL-3 | `observability/dashboard_renderer_v2.py` — `render_domain_dashboard_v2` | Adapter with **only a test caller**, while `DYNAMIC_DASHBOARDS_PLAN.md:223` claims "first adoption landed" — doc-code drift | **L2** | Grep for the intended live caller; wire it into the dashboard path **or** correct the doc to "built, not yet adopted" | Doc matches code; the adapter either ships or is honestly parked |
| CL-4 | `corpus/provider.py` + `content_store.py` (`STARTD8_CORPUS_DETERMINISTIC` / `STARTD8_CORPUS_CONTENT_STORE`) | $0 deterministic generation — serve corpus-proven files with **no LLM**. Fully wired, offline-validated. *(= dev-os CL-1)* | **L3.5** | **Offline gate PASSED** (`validate_corpus_integration.py`). Only the LIVE gate remains → L4: `STARTD8_CORPUS_DETERMINISTIC=1` on a real run + `… postrun <run_dir> <root>` (needs API budget — human-gated) | $0 deterministic generation; Hitsuzen + Mottainai realized |
| CL-5 | OQ-8 — SkillAgent user-skill execution | `PRESENTATION_POLISH_CAPABILITY_REQUIREMENTS.md`: unproven whether SkillAgent can run an arbitrary Claude Code user skill (Phase 2, **flagged highest-risk**) | **L1** | Spike to prove/disprove feasibility before building on it | Unblocks the presentation-polish capability, or kills it early |
| CL-6 | OQ-IMP-D — `GENERATED_IMPORT_PATH` consumer | First consumer unnamed; provisional default `strtd8`. **Blocks e2e acceptance** (Phase-5 gate) | **L1** | Name the first real consumer before Phase 5 | e2e acceptance unblocked |
| CL-7 | Skipped test suites | Jinja2 scaffold (~11 tests, dep-gated) + node-pilot e2e (2, vendor-gated) — a ~60-test conditional blind spot | **L3** | Install Jinja2 / vendor node in CI, **or** accept as a documented conditional skip | Template-render + node-pilot paths validated in CI |

---

## Parked — intentional, NOT defects (do not "fix")

| ID | Artifact | Why it's parked, not broken | Revisit when |
|----|----------|-----------------------------|--------------|
| P-1 | `repair/truth_source.py:127` — `ArtifactTruthSource` | Deliberate FR-10 **future-seam stub** (documented in `MANIFEST_DRIVEN_NAME_REPAIR_PLAN.md:73` as "Approach-A backend stub"); has a test; prod uses the sibling `LiveDiskTruthSource`. Un-wired *on purpose*. | Approach-A `forward_project_knowledge.json` backend ships |
| P-2 | Default-off capability flags: `STARTD8_{PY,TS}_TYPECHECK`, `_VIPP`, `_TUI_AGENTIC`, `_CKG_SCIP`, `_VUE_LINT`, `_VUE_FILE_OLLAMA_WHOLE` | Fully wired, **intentionally opt-in** (require toolchains / are experimental / are enterprise-additive). Not dormant — awaiting operational validation. | Per-flag: decide "graduate to default-on after validation" vs "leave opt-in, documented" |

---

## Corpus / data artifacts (inventory — added by the data-artifact pass)

> Not code loops, but load-bearing *data* the scan first missed. **Three** corpus artifacts,
> **two** schemas, one reserved stub — grounded to their real readers so nobody re-conflates them.

| Artifact | Schema | Written by | Read by (live?) | Ledger tie |
|----------|--------|-----------|-----------------|------------|
| `tests/evaluation/golden_corpus/corpus.json` (146 KB, 47 entries) | file → imports + AST elements | `scripts/mine_corpus_from_manifest.py` (default `CORPUS_PATH`), `scripts/grow_eval_corpus.py` | **eval only** — readers are `scripts/run_eval_ollama.py:67` + `grow_eval_corpus.py:385`; **no `src/` reader** | evaluation/golden reference; not a live path |
| `<project_root>/.startd8/controlled-corpus.json` | term_id → maturity/class | `extract_corpus_from_run` accumulation (postmortem) | **live, flag-gated** — `prime_contractor.py:4021` `ControlledCorpusRegistry.load(controlled_corpus_path(...))`, behind `STARTD8_CORPUS_DETERMINISTIC` | **CL-4** — this IS the serve-time registry |
| `<config>/corpus/shared-corpus.json` | (reserved — unspecified) | nothing (stub) | **stub** — `paths.py:75`: "v1 does NOT implement shared-corpus promotion… reserves the location" (OQ-5) | parked future-seam (like P-1) |

> **Clarifying fact — do NOT re-conflate:** the **micro-prime** path reads **neither** corpus.
> Its determinism is template composition + seed metadata (sibling-file AST): `go.mod` /
> `package.json` / `.csproj` / `requirements.in` from `prime_adapter.py:2334-2734` +
> `clause_mapper.py`. The corpus-serving shortcut is a **prime_contractor** feature; micro-prime
> is a parallel, corpus-free determinism engine. (Live registries also exist in sibling
> worktrees: `startd8-ctxseed/.startd8/`, `startd8-agentic-workbook/.startd8/`, and under
> `.startd8/bias_audit/benchmark-runs/.../sandboxes/` — expected, since the registry is
> project-scoped and accumulates per run.)

---

## Closing by DEPRECATION — do not invest (removal is the closure)

> These were surfaced by the scan as open loops (untested code + open plan requirements),
> but the Artisan Contractor workflow **is being deprecated**. The correct closure is
> **removal, not hardening** — do NOT write tests or fix the open reqs below; they retire
> when the subsystem does. Listed here so the effort is explicitly *declined*, not silently
> missed (and so a future reader doesn't re-flag them).

| ID | Artifact | Scan flagged | Disposition |
|----|----------|--------------|-------------|
| D-1 | `contractors/artisan_contractor.py` (3.9k LOC) | L3 un-validated (no test file) | **Won't-test — deprecating.** Close by removal. |
| D-2 | `PLAN-artisan-contractor.md` — R8 (polyglot design-drift), R9-S9, R17-S7/S10 | open requirements | **Won't-build — deprecating.** |
| D-3 | `PLAN-artisan-contractor.md` — event-dedup on resume + plan-item-id uniqueness | open correctness risks | **Won't-fix — deprecating.** (Would be top-priority if the subsystem were staying.) |

---

## Recently closed (keep for the burn-down record)

| ID | Artifact | Closed how | Level reached |
|----|----------|-----------|:--:|
| ✅ | Controlled-Corpus stale docstrings (`provider.py` + `content_store.py` said "not wired") | corrected to match the L3 reality (2026-07) | closes doc-code drift |
| ✅ | Corpus offline validation gate | `validate_corpus_integration.py` — 20 sim runs, 18 candidates, 7 quarantined, all ✅ ($0) | CL-4 → L3.5 |

<!-- Never delete closed rows — the burn-down IS the evidence the system is working. -->

---

## Ledger discipline (the WIP rule)

- **One loop in flight.** Close (or explicitly park with a *dated* gate) before opening a new one.
- **Close top-down by value × readiness.** Next up: **CL-1** (provider tests — highest value, fully ready, no external gate).
- **Every new dormant path lands here the moment it's built-but-unwired** — that's the defect report.
- **Advertise honestly.** A repo's maturity = its lowest open loop in this table (currently L2).
- **Ground, don't inflate.** A docs-derived ledger over-reports; grounding against code deflates it. This scan started at ~40 hits and grounded to 7 real loops + 2 intentional parks + 3 deprecation-closures. If it grows without closing, you're formalizing debt instead of retiring it.
- **Inventory data, not just code — and search system-wide.** The scan first missed the corpus *files* by sweeping only code paths, and earlier missed the corpus by searching a *consuming* project (`online-boutique-demo`) instead of grepping system-wide for where the data lives. When something seems absent, widen the search before concluding it's missing — a **scoped-search false-negative** is the exact mirror of the scoped-report false-positives (CL-3…CL-7) grounding already corrected.

---

## The loops that feed this ledger (per feature)

```
/reflective-requirements  → draft → plan grounds it → reflect (§0) → lessons (§0.1) →
                            principles (§0.2) → [optional CRP] → de-risked spec
      ↓  IMPLEMENT
CLOSURE LEDGER            → loose ends land here as rows the moment they exist
/code-review --fix       → find → fix → document Applied/Declined in the commit body
/reflective-retrospective → Hansei: reflect on the ACTUALS, extract the standard, Yokoten,
                            feed it back into the next /reflective-requirements
```

---

*Seeded from `dev/dev-os/templates/CLOSURE-LEDGER.template.md`. Canonical assets are
single-source — cite them, don't copy (`dev/dev-os/REQUIREMENTS-PIPELINE.md §2`).*
