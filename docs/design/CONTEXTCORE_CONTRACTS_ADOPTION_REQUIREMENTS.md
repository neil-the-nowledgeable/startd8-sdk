# SDK Adoption of ContextCore Defense-in-Depth Contracts — Requirements

**Version:** 0.3 (Post-implementation — bugs + inert-adoption findings folded back)
**Date:** 2026-06-12
**Status:** Draft
**Scope:** Adopt 5 ContextCore `contracts.*` capabilities the SDK doesn't yet use, completing the
defense-in-depth around the propagation contracts it already wires.

---

## 0.0 Implementation Insights (v0.3) — the keystone was wired but DEAD

> Building preflight/postexec/regression surfaced that the "already-adopted propagation keystone" this
> doc leans on **never actually functioned**. Two classes of latent bug + a contract-shape mismatch:

1. **Wrong loader API (4 dead call-sites).** Every ContextCore contract load called
   `ContractLoader.load_contract(str)` — a method that **does not exist**. The real API is an *instance*
   method: `ContractLoader().load(Path)`. The dead call sat in: registry preflight, registry **exit
   boundary validation** (the "shipped keystone"), `compare_contracts`, and `plan_ingestion_workflow`
   Layer-5 capability validation. All four were swallowed by `try/except` → logged-and-ignored or
   `return True`, so the defense-in-depth was a silent no-op. **All four fixed** (routed through one
   `_load_contract`).
2. **Dead fail-closed (missing result helpers).** Preflight called `result.critical_violations()` and
   exit called `exit_result.has_blocking_violations()` — **neither method exists** on
   `PreflightResult` / `ContractValidationResult`. So even had the load worked, `fail_closed` could
   never block. Fixed: criticality is derived from `violation.severity == BLOCKING`; exit uses
   `result.passed` / `result.blocking_failures`.
3. **Contract-shape mismatch (the adoption is INERT until a real contract exists).** **No SDK workflow
   sets `metadata.contract_path`**, and the only `*.contract.yaml` files (e.g.
   `plan-ingestion.contract.yaml`) are **Artisan/gate-schema**, not ContextCore `ContextContract`s
   (which need `schema_version` / `pipeline_id` / `phases`). So even fully fixed, the run-path checks
   are **contract-gated to no-op** (FR-CC-2) for every current workflow. The functions are now *correct*
   and *proven* (against a minimal valid `ContextContract` test fixture), but remain **inert** until a
   workflow declares a real ContextContract via `metadata.contract_path`. **This is the highest-value
   finding: the adoption is now functional code awaiting a contract, not a working feature.**

**Net:** the code is fixed, consolidated (FR-CC-5: one `_contracts_integration` surface for
preflight/exit/postexec/drift), advisory-by-default, and unit-proven. Lighting it up for a real
workflow = authoring a ContextContract + setting `metadata.contract_path` (a separate, small task).

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the SDK seam (`workflows/registry.py`) and the 5 ContextCore module APIs.
> The spine held (complete the defense-in-depth; preflight is a quick win), but planning **promoted
> a second quick win, corrected two assumptions, and narrowed two requirements** — earning its keep.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Propagation validates at entry+exit; preflight extends an existing pre-run hook | The SDK does **EXIT-only** boundary validation (`validator.validate_exit(...)` after `workflow.run`); there is **no entry hook today** | preflight is a **net-new pre-run block** — but small, same infra/gate/location. Reframed, not blocked. |
| preflight needs the SDK to supply initial context **and phase order** (OQ-2) | `PreflightChecker.check(contract, initial_context, phase_order=None)` — **`phase_order` defaults to `contract.phases`**; `initial_context` ≈ the SDK's `config` dict | **OQ-2 resolved:** pass `config`, let phase_order default. preflight is genuinely near-drop-in. |
| regression is "then" (third priority) | `ContractDriftDetector.compare(old, new) -> DriftReport` is **fully off-run** — two contract files in, drift out, **zero run-path integration** | **regression promoted to a quick win** alongside preflight (lowest-risk: touches no run loop). |
| postexec can cross-reference L4 runtime records (FR-POST-1) | The SDK persists **no L4 runtime boundary records** (exit-only) | **FR-POST-1 narrowed:** chain-integrity + exit-requirements usable now; the L4 cross-ref is deferred (needs new emission). |
| lineage reuses the loaded propagation contract (FR-CC-3) | `ProvenanceAuditor(contract: LineageContract)` uses a **separate contract type** + needs recorded transformation history | **FR-CC-3 gets a lineage exception; lineage is a bigger lift** — stays deferred, assumption corrected. |
| One clean seam (FR-CC-5) | Exit validation is **duplicated in two call sites** (sync `run` + async `arun`); `contract_path` is declared by **few workflows** (mainly plan-ingestion + the metadata field) | **FR-CC-5 (single helper) is now mandatory** (avoid a third+fourth copy); blast radius small → value focused on plan-ingestion. **OQ-3/OQ-6 resolved.** |

**Resolved open questions:** OQ-1 (APIs verified — see §2), OQ-2 (phase_order optional; config = initial
context), OQ-3 (few contract-bearing workflows; plan-ingestion is the primary beneficiary), OQ-5 (no L4
records → postexec cross-ref deferred), OQ-6 (registry.py is the run-seam; consolidate via one helper).
**Partially:** OQ-4 (lineage = separate `LineageContract`; ordering = low-level `CausalClock`/`CausalProvenance`).

---

## 1. Problem Statement

The SDK already uses ContextCore's **propagation** keystone — `ContextContract` + `BoundaryValidator`
+ `ContractLoader`, wired at workflow entry/exit in `workflows/registry.py` (and plan ingestion),
gated on `workflow.metadata.contract_path`, all as optional/guarded imports. It also uses `a2a` and
`capability` contracts. But it **stops at the keystone**: it validates *at* boundaries (L4) without
the layers that bracket and reinforce that — and in several cases reimplements weaker ad-hoc versions.

### 1.1 Gap table

| # | ContextCore capability | What it does | SDK today | Gap |
|---|------------------------|-------------|-----------|-----|
| 1 | **preflight (L3)** | Validate initial context + phase order against the contract **before any phase runs** | Validates only at **exit** boundary (after spend) | No fail-**before**-spend gate; the classic `domain_constraints`-never-produced gap surfaces late |
| 2 | **postexec (L5)** | After all phases: end-to-end propagation-chain integrity + final exit requirements + cross-ref L4 records | Own post-mortem scores **disk/code quality**, not context-contract integrity | Contract integrity never confirmed post-run |
| 3 | **ordering** | Lamport causal clock + causal provenance → happens-before / staleness | WARM_UP *principle* only; no enforcement | "stale enriched seed" failure class is unguarded |
| 4 | **lineage** | Provenance auditor: recorded transform history vs declared lineage; missing stages / silent passthrough mutations | Ad-hoc provenance (run-provenance.json, checksums, forward-manifest anchors) | Provenance not a typed/verifiable contract (RUN-008 cross-file-integrity class) |
| 5 | **regression (L7)** | Contract-drift detection across contract versions (added/removed phases) | Kaizen tracks **outcome** drift, not **contract** drift | Phase contracts can silently break propagation as they evolve |

### 1.2 The unifying observation
All 5 attach to the **same seam** the SDK already has: a loaded `ContextContract` (via `ContractLoader`)
keyed on `workflow.metadata.contract_path`, validated around `workflow.run(...)` in
`workflows/registry.py`. preflight/postexec are *the most* drop-in (same contract object, just earlier/
later in the run). ordering/lineage need additional per-event/per-stage records the SDK must emit.

---

## 2. Requirements

### A. Shared infrastructure (applies to all 5)
- **FR-CC-1 (Optional + guarded).** Every adoption MUST be an optional, import-guarded integration —
  absent/old ContextCore degrades to today's behavior, never crashes (matches existing propagation
  wiring).
- **FR-CC-2 (Contract-gated).** A capability activates only when `workflow.metadata.contract_path` is
  present and the contract declares the relevant section — never imposed on contract-less workflows.
- **FR-CC-3 (Reuse the loaded contract).** preflight/postexec/regression MUST reuse `ContractLoader`
  + the same `ContextContract`; do NOT introduce a parallel contract-loading path. **(Planning
  exception: lineage uses a *separate* `LineageContract` + recorded transformation history — it does
  NOT reuse the propagation contract, which is one reason it's deferred.)**
- **FR-CC-4 (OTel + non-blocking by default).** Findings MUST emit via the SDK's OTel/get_logger
  conventions. Default severity is **warn/non-blocking** (advisory), with an opt-in **fail-closed**
  mode per capability (consistent with `domain-preflight`/gate ethos).
- **FR-CC-5 (Single integration surface).** All run-path checks MUST route through **one** helper
  (e.g. `workflows/_contracts_integration.py`) — planning found the existing exit validation is
  **already duplicated across `run` + `arun`**, so adding more inline try/except blocks would
  multiply the copies. The helper centralizes load/gate/validate/report/severity.

### B. preflight (L3) — **the quick win**
- **FR-PRE-1.** BEFORE `workflow.run(...)`, when a `contract_path` exists, call
  `PreflightChecker().check(contract, initial_context, phase_order=None)` with **`initial_context` =
  the workflow `config` dict** and **`phase_order` left to default** to the contract's declared phase
  order; surface dangling critical requires, shadow defaults, and seed-enrichment/phase-graph gaps
  from the returned `PreflightResult`.
- **FR-PRE-2.** In **fail-closed** mode, a critical pre-flight violation MUST block the run **before
  any LLM spend** (fail-before-spend). In default mode, warn and proceed.
- **FR-PRE-3.** Pre-flight findings MUST be reported in the same shape as the existing boundary
  validation results (consistent operator experience).

### C. postexec (L5)
- **FR-POST-1.** AFTER all phases complete, run `PostExecutionValidator(...).validate(...)` for
  end-to-end propagation-chain integrity + the final phase's exit requirements. **(Planning: the L4
  runtime-record cross-reference is DEFERRED — the SDK persists no L4 boundary records today; it only
  validates the exit boundary. `RuntimeDiscrepancy` detection needs new emission, out of scope here.)**
- **FR-POST-2.** postexec findings MUST be attached to the run's post-mortem artifacts (complement,
  not replace, the disk-quality post-mortem).

### D. ordering (staleness / causality)
- **FR-ORD-1.** The SDK MUST stamp pipeline events/artifacts with a causal clock so a downstream
  phase reading a **stale** upstream artifact (e.g. an enriched seed superseded by a later write) is
  detectable.
- **FR-ORD-2.** A staleness violation MUST be surfaced (warn by default; opt-in block) — targeting the
  WARM_UP / stale-enriched-seed failure class.

### E. lineage (provenance)
- **FR-LIN-1.** The SDK MUST record transformation history (stage → stage, with content hashes) for
  contract-declared lineage chains, and audit it: **missing stages** and **silent passthrough
  mutations** (passthrough where the hash changed) MUST be detected.
- **FR-LIN-2.** lineage SHOULD reuse existing provenance signals (run-provenance.json, forward-manifest
  anchors, checksums) rather than introduce a separate provenance store.

### F. regression (L7)
- **FR-REG-1.** When a workflow's contract changes version, the SDK MUST be able to compare old vs new
  and flag propagation-breaking drift (a phase that stops producing a field a downstream phase
  requires; added/removed phases).
- **FR-REG-2.** Contract-drift checks SHOULD run at `manifest validate`/CI time, not per-run.

### G. Prioritization (post-planning)
- **Quick win #1 — regression (L7).** *Lowest risk:* `ContractDriftDetector().compare(old, new)` is
  **fully off-run** (no run-loop changes), a small validate-time/CLI utility. Promoted from "third"
  to first by planning.
- **Quick win #2 — preflight (L3).** Near-drop-in: one helper (FR-CC-5) calling
  `PreflightChecker().check(contract, config)` before `run`/`arun`, gated on `contract_path`; serves
  the documented fail-before-spend need. Net-new pre-run block, but small + same infra.
- **Second tier — postexec (L5).** Same helper, run-end; chain + exit validation now, L4 cross-ref
  deferred. Complements the existing post-mortem.
- **Deferred (need new per-event/per-stage emission) — ordering, lineage.** `CausalClock`/lineage
  require the SDK to *emit* causal/lineage records (and lineage needs its own `LineageContract`), not
  just validate an existing contract — bigger surface, scoped but not in this pass.

---

## 3. Non-Requirements
- **NR-1.** Does NOT replace the SDK's own post-mortem (`prime_postmortem`), Kaizen, or cap-dev-pipe
  provenance — these complement them (and may later consolidate, out of scope here).
- **NR-2.** Does NOT make ContextCore a hard dependency or default-on; all optional/guarded.
- **NR-3.** Does NOT author new ContextContracts for workflows that don't have one — adoption only
  benefits contract-bearing workflows.
- **NR-4.** Does NOT change the propagation/a2a/capability integrations already shipped.
- **NR-5.** Does NOT (in this pass) build ordering/lineage emission — those are scoped but deferred.

---

## 4. Open Questions

> **Resolved in planning (see §0):** OQ-1 (APIs verified), OQ-2 (phase_order optional; config =
> initial context), OQ-3 (few contract-bearing workflows; plan-ingestion primary), OQ-5 (no L4
> records → postexec cross-ref deferred), OQ-6 (registry.py run-seam; one helper). OQ-4 partially
> (lineage = separate `LineageContract`; ordering = `CausalClock`). Remaining design questions move to
> the ordering/lineage deferral. Original text retained below for provenance.

- **OQ-1.** Exact ContextCore APIs: class names + call signatures for `preflight` (PreflightChecker?),
  `postexec`, `ordering` (CausalClock), `lineage` (ProvenanceAuditor), `regression` (drift detector)?
  **ASSUMPTION:** preflight exposes a checker callable like `BoundaryValidator` (load contract →
  `check(initial_context, phase_order) -> violations`). Verify in planning.
- **OQ-2.** Does the SDK have the **initial context + phase order** available at the pre-run point in
  `registry.py` to feed preflight? (BoundaryValidator runs post-run with `result`; preflight needs the
  pre-run inputs.)
- **OQ-3.** How many SDK workflows actually declare a `contract_path`? (Determines blast radius/value.)
- **OQ-4.** Do contracts declare the lineage/ordering sections preflight-style, or are those separate
  contract types/files? (Affects FR-ORD/FR-LIN feasibility as "reuse the loaded contract.")
- **OQ-5.** For postexec cross-referencing L4 records — does the SDK persist L4 boundary records today,
  or would that need adding?
- **OQ-6.** Is there a single clean seam to consolidate all 5 (FR-CC-5), or is registry.py the only
  hook (and is plan_ingestion a second one)?

---

*v0.2 — Post-planning self-reflective update. APIs verified; **two quick wins** (regression L7 off-run,
preflight L3 near-drop-in) with confirmed signatures; FR-CC-5 helper now mandatory (exit validation is
duplicated across run+arun); FR-POST-1 narrowed (no L4 records → cross-ref deferred); FR-CC-3 lineage
exception (separate `LineageContract`); 5 OQs resolved. Spine intact: complete the defense-in-depth
around the adopted propagation keystone. ordering/lineage deferred (need new causal/lineage emission).*
