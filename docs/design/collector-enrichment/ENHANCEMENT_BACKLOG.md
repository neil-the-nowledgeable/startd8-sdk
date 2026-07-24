# collector_enrichment — Enhancement Backlog

**Date:** 2026-07-24
**Scope:** the just-shipped `collector_enrichment` (FR-1b + FR-2–11, PR #321, `5896a15e`).
**Method:** grounded against the merged code; leads with what to do first, buckets below the fold.

> **Grounding note (belief → actual corrections).** Three first-guesses changed on contact with code:
> (1) I assumed the parity gate had *some* operator surface — it has **none** (tests only). (2) I
> assumed "mergeable file" (from the reqs) was a real registry capability — `ArtifactTypeSpec` has
> **no `mergeable` field** (`artifact_generator_models.py`); the file is emitted standalone, so the
> last-mile merge is genuinely unaddressed. (3) I assumed acceptance #5 (spans carry the attrs in the
> backend) had a proof — it doesn't, **but** the harness to prove it (`runtime_fidelity.py`) already
> exists. All three became findings.

---

## Top findings (do these first)

**1. ⚡ Expose the parity gate as a CLI — the cutover-safety mechanism is unreachable without Python.**
`check_collector_enrichment_parity` / `extract_enrichment_map` (`collector_enrichment_parity.py`) are
called **only from `test_collector_enrichment.py`** — confirmed: `grep -rn check_collector_enrichment_parity src/` returns nothing outside the module's own def. Yet the *entire point* of FR-10a/11 is a
one-shot check an **operator** runs against their real collector config before deleting the hand-written
`transform/business` block. The `observability` Typer group already hosts sibling verbs (`compare`,
`compare-live`, `contrast`, `scorecard` — `observability/cli.py:379-410`), so this is a ~40-line
subcommand riding an established pattern. → so an **operator can prove generated ≡ deployed and retire
the mirror safely** without hand-writing a Python harness. **Effort: S.**

**2. 🌱 Close acceptance #5 with the otelcol harness that already exists.**
Acceptance #5 ("after operator wiring, spans carry `business.criticality`/`owner` in the backend") has
**no live proof** — no test boots a collector with the emitted processor. But `runtime_fidelity.py:178`
already owns an `otelcol-contrib` subprocess on loopback (built for the spanmetrics spike, with
`collector_config()` at `:41`). Feeding the emitted `otelcol-business-enrichment.yaml` into that harness
and asserting an emitted span carries `business.criticality` closes the one acceptance criterion the unit
suite structurally cannot. → so the team gets **end-to-end proof the enrichment actually stamps spans**,
not just that the YAML is well-formed. **Effort: M.**

**3. ⚡ Document (or emit) the last-mile merge — the standalone block has no path into a real config.**
The generator writes a bare `processors: {transform/business: …}` file (`_COLLECTOR_ENRICHMENT_PATH`,
`artifact_generator_generators.py:2723`). An operator must still hand-merge it into their collector
config's `processors:` **and** add `transform/business` to a `traces` pipeline — nothing emits or
documents that step (and `ArtifactTypeSpec` has no `mergeable` machinery to do it automatically). A short
`README`/header snippet showing the two-line wiring is the cheap fix; a `--merge-into <config.yaml>` helper
is the fuller one. → so an operator **knows how to actually deploy the artifact** instead of guessing.
**Effort: S (doc) / M (merge helper).**

*(No built-but-unwired **defect** to report: the generator is wired into `generate_observability_artifacts`
and stamped/written; the parity gate shipping as a function+test is exactly what FR-10a/11 specified — its
missing CLI is a latent **capability**, not a broken path. Verified by tracing both ends of the generator
wire and running the 28-test suite green on merged main.)*

---

<details>
<summary><b>Backlog appendix</b> (supporting; draw from over later increments)</summary>

### ⚡ Quick wins
- **QW-1 — parity CLI subcommand** — ✅ **DELIVERED** (`startd8 observability enrichment-parity -g <generated> -r <deployed> [--json]`; exit 0=parity/1=mismatch/2=unreadable; `cli.py`). Top finding #1. **S.**
- **QW-2 — last-mile merge doc/snippet** — Top finding #3, doc flavor. **S.**
- **QW-3 — surface provenance in the run report** — the sha256 is written to the file header
  (`_business_provenance`, `:2835/2841`) but not into `report.fr_coverage` or the run index, so a consumer
  must open the YAML to see it. Add one `fr_coverage["collector_enrichment_provenance"]` line → drift/regen
  tooling can read it without parsing the artifact. **XS.**

### 🌱 Low-hanging fruit
- **LH-1 — live acceptance-#5 proof** — Top finding #2, via `runtime_fidelity.py`. **M.**
- **LH-2 — emit an `error`-status artifact into coverage honestly** — the generator already returns
  `status="error"` with `error_message` on validation failure (`:2726-2734`), and the wiring appends it
  (`artifact_generator.py`, `!= "skipped"`). Confirm it surfaces in the quality/coverage report rather
  than being silently dropped — one assertion + a report line closes the loop. **XS/S.**

### 🏗️ Architectural quick win (≤1)
- **AQ-1 — extract the semantic-parity pattern on 2nd use (not now).** `extract_enrichment_map` +
  map-diff is the reusable "parse two collector configs → compare resolved meaning, grouping-insensitive"
  shape the RETROSPECTIVE flagged for Yokoten. The spanmetrics generator (#307) is the sibling; when a
  *second* `transform/*` cutover needs parity, lift a shared `collector_config_semantic_diff`. Until then,
  duplication-of-one is correct — **do not pre-abstract.** **M, deferred.**

### 🚀 Enhanced capabilities (higher effort; each justified by existing plumbing)
- **EC-1 — per-service alert severity + runbook escalation (NR-1 seed).** `ServiceHints.{criticality,owner}`
  are now populated per-service but read *only* by `generate_collector_enrichment`; `_severity_for` and the
  runbook escalation block still read project-level `business.criticality/owner`. The data now exists to make
  severity per-service. Must be additive/flag-guarded — rewiring risks byte-output regressions on existing
  fixtures (why it was NR-1). **M.**
- **EC-2 — FR-7: `business.criticality` as a spanmetrics dimension (NR-3 seed).** `calls_total{business_criticality=…}` makes the enrichment queryable in Prometheus, not just present on spans. The spanmetrics
  connector already lives in `runtime_fidelity.collector_config()`; adding a dimension is a localized change
  there + an emitter tweak. **M/L.**
- **EC-3 — FR-10b: post-cutover drift detection (NR-6 seed).** The provenance sha256 is *already computed*
  (`_business_provenance`) — the missing half is reading it back and re-hashing the deployed config to alert
  on drift after the hand-written block is removed. Reuses the parity parser from QW-1. **M.**

### 🔭 Operational / observability
- **OB-1 — count emitted enrichment statements in `fr_coverage`.** One integer (`statements`, `services_enriched`) in the run report makes the paid-nothing $0 pass *legible* — "12 services enriched, 24 statements"
  — and gives drift tooling a cheap signal. **XS.**

</details>

---

## Honest gaps (product decisions surfaced while grounding — not bugs)

- **Per-service consumption is deliberately deferred (NR-1).** Existing alert/slo/runbook generators keep
  reading project-level criticality *by design* — to preserve byte-identical output on shipped fixtures.
  EC-1 is the opt-in path; confirm that's the intended shape before wiring it.
- **`business.context_version` OTTL statement intentionally omitted (NR-4).** Provenance lives in the header
  comment so the emitted statement set stays equal to the reference and semantic parity is clean. Decision,
  not omission.
- **Two `ServiceHints` resolving to the same `service.name` silently merge** (non-conflicting attrs) or
  fail-fast (conflicting values). `service.name` is unique in practice; documented as a considered-and-
  declined item in the PR #321 code-review. Revisit only if a real duplicate-name topology appears.
