# NEXT STEPS — TF-3: Per-Fleet RED-Coverage Roll-Up (report + CLI)

**Status:** proposal / scoping
**Scope:** SDK-side, additive, read-only ($0, no LLM)
**Owner:** observability
**Depends on (already shipped this session):** the canonical RED taxonomy (`red_taxonomy.py`),
the per-dashboard OBS-200a warning, and the descriptor-grounded "why" clause (`_red_gap_reasons`).

---

## 1. Problem & end-user value

A service-fleet owner running `startd8 generate observability` over an N-service manifest gets N
independent per-dashboard OBS-200a warnings — one warning buried in each dashboard's validation
result. There is no **fleet posture view**: no single answer to *"across my N services, what is my
RED coverage, which services are worst, and what is the grounded gap for each?"*

Today OBS-200a is emitted per dashboard inside `validate_dashboard`
(`src/startd8/validators/observability_artifact_checks.py:344-349`) as a `warning`-severity
`RED coverage X% — missing: ...` string. To assemble a fleet picture an operator must scrape every
dashboard's issue list by hand and re-derive the ranking. That is exactly the aggregation the SDK
already has all the inputs for but never performs.

**Value:** turn N scattered warnings into one ranked "worst-first" posture table + a machine-readable
`--json` for CI — *"here is your whole fleet's RED coverage, and the grounded reason each leg is
absent, worst service first."* The per-service **grounded reason** (summary latency / no error
dimension / no throughput metric) is the actionable payload: it tells the owner which gaps are real
authoring work vs. which are legitimately unbindable and should be left alone.

This is the SDK-side complement to the ContextCore **Harbor** pilot's per-service `metric_cov`
(binding coverage across a fleet, see `.startd8/workflow-loop-queue/SURFACE_FLEET_COORDINATION.md`).
Harbor measures *live binding* coverage; TF-3 measures *derived RED* coverage from the generated
artifacts. Keep TF-3 strictly SDK-side; note the connection but do not couple to Harbor.

---

## 2. Grounded current state

**Where per-service coverage is computed today (cheaply):**
- `red_coverage(panels, descriptor)` — fraction of the `{RATE, ERROR, DURATION}` triple present
  (`src/startd8/observability/red_taxonomy.py:253-258`).
- `red_roles_present(panels, descriptor)` — the set of roles present, independent membership
  (`red_taxonomy.py:238-250`).
- `_red_gap_reasons(missing, descriptor)` — the descriptor-grounded "why" a leg is absent
  (`src/startd8/validators/observability_artifact_checks.py:218-233`): empty
  `latency_bucket_metric` → *"Duration: latency is a summary (no histogram bucket to bind)"*; empty
  `error_selector` → *"Errors: metric has no error dimension"*; empty `throughput_metric` → *"Rate:
  no throughput metric on this descriptor"*.
- OBS-200a assembles `red` + `missing` + `reasons` per dashboard
  (`observability_artifact_checks.py:330-349`).

**Confirmed: there is NO fleet roll-up.** The only aggregate `red_coverage`-shaped surfaces are:
- `CoverageReport` in `artifact_generator_models.py:301-347` — an **FR-coverage** accumulator (FR
  IDs / suppressed / bound-declared series), *not* a RED-per-service roll-up.
- `CoverageReport` in `requirements_panel/coverage.py:38` and `artisan_phases/final_testing.py:156`
  — unrelated (requirements / pytest coverage).
- `red_coverage_improving` in `contractors/batch_postmortem.py:779` — a cross-run trend flag, not a
  per-service fleet view.

None of these produce "per-service RED coverage, ranked worst-first."

**The cheap wiring point — the orchestrator already loops every service with descriptors in scope:**
`generate_observability_artifacts` in `src/startd8/observability/artifact_generator.py`:
- builds a per-service `MetricDescriptor` map once: `descriptors[service.service_id] =
  resolve_descriptor(...)` (`artifact_generator.py:1456-1464`);
- iterates `for service in services:` with `descriptor = descriptors[service.service_id]` in scope
  (`artifact_generator.py:1470-1471`);
- calls `generate_dashboard_spec(...)` (registered in `_GENERATORS`,
  `artifact_generator.py:1446-1450`), which builds the actual `panels` list
  (`artifact_generator_generators.py:528-682`, panels assembled at 544/601/682 and RED-completed via
  `_ensure_red_coverage` at 620).

So both **panels** and the **resolved descriptor** are already computed per service — the two inputs
`red_coverage` / `_red_gap_reasons` need. A fleet roll-up is a pure fold over data the orchestrator
already materializes.

**Two viable input sources (see Risk R1):**
1. **From generated artifacts** — each dashboard `ArtifactResult` carries `content` (YAML),
   `service_id`, and `output_path` (`artifact_generator_models.py:277-282`). The panels can be
   re-parsed from `content` (a `--artifacts-dir` entrypoint, like `validate-promql`). This is the
   decoupled, Mottainai-friendly path (score persisted artifacts $0, no regen).
2. **In-loop** — emit a `fleet_red_coverage` record from inside the per-service loop where
   `panels` + `descriptor` are live. Cheaper but couples the roll-up to a generation run.

Prefer **(1)** for the CLI verb (mirrors `validate-promql`/`compare` which read an artifacts dir /
manifest); optionally add **(1b)** the roll-up as a field on `GenerationReport` from the in-loop
path later, since the data is free there.

---

## 3. Proposed shape

### 3a. A pure function — `fleet_red_coverage`

New module `src/startd8/observability/red_fleet.py` (or a function beside `red_coverage` in
`red_taxonomy.py` if we keep it descriptor-free-only). Reuses the existing primitives — **no new
classification logic**:

```python
def fleet_red_coverage(
    services: Sequence[ServiceRedInput],   # {service_id, panels, descriptor}
) -> FleetRedReport:
    per = []
    for s in services:
        present = red_roles_present(s.panels, s.descriptor)   # red_taxonomy.py:238
        cov     = red_coverage(s.panels, s.descriptor)        # red_taxonomy.py:253
        missing = [r.value.capitalize() for r in RED_ROLES if r not in present]
        reason  = _red_gap_reasons(missing, s.descriptor)     # obs_artifact_checks.py:218
        per.append(ServiceRedCoverage(s.service_id, cov, sorted(present), missing, reason))
    per.sort(key=lambda x: (x.coverage, x.service_id))        # worst-first, stable
    return FleetRedReport(services=per, ...aggregates...)
```

- **Reuse, don't reinvent:** classification is `red_roles_present`; the "why" is `_red_gap_reasons`
  (lift/share it — currently module-private in `observability_artifact_checks.py:218`; either import
  it or promote it next to `red_taxonomy`). The `Rate/Errors/Duration` label strings must match the
  OBS-200a wording (`observability_artifact_checks.py:334-339`) so the fleet view reads identically
  to the per-dashboard warning.
- **Descriptor-grounded when available.** Pass the per-service `descriptor` so coverage and reasons
  match the FR-4a null-safe grounded tier (`red_taxonomy.py:193-211`). Descriptor-free fallback when
  a caller has only on-disk panels (arbitrary dashboards).

### 3b. CLI verb — `startd8 observability red-coverage`

Add a command to the **existing** `observability_app` Typer
(`src/startd8/observability/cli.py:34`; the group is already wired into the top-level app at
`src/startd8/cli.py:64,1278`). Follow the `compare` command's shape
(`observability/cli.py:398-430`) — the closest existing precedent (reads generated artifacts,
`--json`, advisory-by-default exit, `--strict` gate):

```
startd8 observability red-coverage --artifacts-dir <dir> [--onboarding-metadata <json>]
                                   [--json] [--min-coverage 0.67] [--strict]
```

- Default: render a ranked table, **worst coverage first**, one row per service:
  `service | coverage% | present (R/E/D) | missing | grounded reason`.
- `--onboarding-metadata` (optional): reconstruct per-service descriptors (same source the generator
  used, `artifact_generator.py:1456`) so the reasons are grounded; absent ⇒ descriptor-free (coverage
  still valid, reasons empty — the honest-empty case, R3).
- `--json`: emit `FleetRedReport.to_dict()` for CI (mirror `compare --json`,
  `observability/cli.py:406,427`).
- Exit codes (mirror `compare`): `0` advisory · `2` with `--strict` when any service is below
  `--min-coverage` (default `2/3`, matching the OBS-200a threshold `red >= 2.0/3.0` at
  `observability_artifact_checks.py:347`).

### 3c. Optional in-loop field (later)

Because `panels` + `descriptor` are already in scope at `artifact_generator.py:1470-1471`, the
per-service RED coverage can also be stamped onto `GenerationReport` at generation time for free (a
`fleet_red` block alongside `fr_coverage`). Defer to a follow-up; the CLI/artifacts-dir path is the
primary deliverable.

---

## 4. Data model

Derive strictly from what exists — no invented metrics.

```python
@dataclass(frozen=True)
class ServiceRedCoverage:
    service_id: str
    coverage: float                 # red_coverage(panels, descriptor)  ∈ {0, 1/3, 2/3, 1}
    roles_present: list[str]        # sorted red_roles_present values, e.g. ["error","rate"]
    missing: list[str]              # ["Duration"] — OBS-200a wording
    reason: str                     # _red_gap_reasons(...) grounded clause ("" if none/no descriptor)

@dataclass(frozen=True)
class FleetRedReport:
    services: list[ServiceRedCoverage]   # sorted worst-first (coverage asc, service_id tiebreak)
    count: int
    mean_coverage: float                 # mean over services
    worst_coverage: float                # services[0].coverage
    below_threshold: int                 # count(coverage < min_coverage), default 2/3
    threshold: float                     # the min_coverage used (echo for the report)
    def to_dict(self) -> dict: ...       # stable-key JSON for --json / CI
```

Every field is a fold over `red_coverage` / `red_roles_present` / `_red_gap_reasons` outputs. The
coverage values are quantized to the {0, 1/3, 2/3, 1} lattice by construction
(`red_coverage` = `len(present ∩ RED_ROLES) / 3.0`, `red_taxonomy.py:258`).

---

## 5. Test strategy

Deterministic, offline, $0.

- **Synthetic `ServiceHints`/panels → known coverage.** Build panels with exactly R, R+E, R+E+D,
  and empty; assert per-service `coverage` = 1/3, 2/3, 1.0, 0.0 and the correct `missing` /
  `roles_present`, reusing the existing `red_taxonomy` classifier. Assert **worst-first ordering**
  and the `service_id` tiebreak are stable.
- **Grounded reason parity.** Give a service a summary-latency descriptor (empty
  `latency_bucket_metric`) and assert the row's `reason` equals the OBS-200a wording from
  `_red_gap_reasons` (`observability_artifact_checks.py:227-232`) — locks the fleet view to the
  per-dashboard warning so they can't drift.
- **Aggregates.** `mean_coverage`, `worst_coverage`, `below_threshold` against a hand-computed
  fixture.
- **Descriptor-free path.** No `--onboarding-metadata` ⇒ coverage still computed, `reason == ""`
  (honest-empty), no crash.
- **Golden for the rendered table.** If the CLI renders text, snapshot a small 3-service golden
  (worst-first) so column layout + wording are pinned (same discipline as the `compare` /
  `contrast` renderers, `observability/cli.py:357-366,423-428`).
- **CLI exit codes.** `--strict` below threshold ⇒ exit 2; advisory default ⇒ exit 0; `--json`
  round-trips `to_dict`.

---

## 6. Risks / open questions

- **R1 — panel input source.** Generated-artifacts (`--artifacts-dir`, re-parse dashboard YAML
  `content`) vs. in-loop (live `panels`). Recommend artifacts-dir for the CLI (decoupled, Mottainai
  $0 re-score of persisted dashboards, mirrors `validate-promql`); note the in-loop `panels` at
  `artifact_generator.py:1470` is available for a later `GenerationReport` field.
- **R2 — single-service vs. multi-service dashboards.** The generator emits **one dashboard per
  service** (per-service loop, `artifact_generator.py:1470-1482`), so mapping dashboard → service is
  1:1 via `ArtifactResult.service_id` (`artifact_generator_models.py:278`). If an operator points
  `--artifacts-dir` at hand-authored multi-service dashboards, service attribution is ambiguous —
  document that the roll-up keys on the generated 1:1 convention and treats an unattributable
  dashboard as its own "service" row (fail-loud, never silently merge).
- **R3 — honest-empty messaging.** Without `--onboarding-metadata` there is no descriptor, so
  `_red_gap_reasons` returns `""` (it early-returns on empty identities). The report must render an
  explicit *"(no descriptor — reason unavailable; pass --onboarding-metadata)"* rather than a blank
  cell, so an operator isn't misled that a gap is unexplained when it's just ungrounded.
- **R4 — descriptor threading on re-score.** The post-bind dashboard re-score at
  `artifact_generator.py:1912-1918` calls `validate_dashboard` **without** a `descriptor`, so its
  OBS-200a lacks the grounded "why." TF-3's roll-up (which threads the descriptor) will show reasons
  the re-score path doesn't — surface this as a known, tolerable asymmetry (or a tiny follow-up to
  pass `descriptors[art.service_id]` there).
- **R5 — Harbor scope creep.** Keep TF-3 SDK-side. Do not read live Prometheus or Harbor
  `metric_cov`; the live twin already exists (`compare-live`, `validate-promql`). TF-3 is the
  *derived/offline* fleet view.

---

## 7. Effort & recommended process

**Effort: M.** One pure function + data model (folds over existing primitives), one CLI verb on an
existing Typer group, one shared/lifted `_red_gap_reasons`, tests + one golden. No new
classification, no LLM, no live I/O. Bulk of the work is the artifacts-dir parse + honest-empty
rendering + the golden.

**Process:** run the **reflective-requirements** loop (the session default) to firm up R1 (input
source) and R3 (honest-empty wording) before coding — those are the two decisions that shape the
data model and the golden.

**CRP?** Per the session's calibration (CRP for paid / write / foreign-surface changes; skip for
additive read-only): TF-3 is additive, read-only, $0, all-SDK-side. **Skip the CRP.** The
reflective-requirements pass + the parity test locking the fleet view to the OBS-200a wording is
sufficient guard. The only write-ish seam is lifting `_red_gap_reasons` out of module-private scope
— a mechanical, test-covered move.
