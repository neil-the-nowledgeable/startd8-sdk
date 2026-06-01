# Manifest-Driven Name Repair — Requirements

**Version:** 0.6 (Post-CRP — R1+R2+R3+R4 triaged, 13/13 F-suggestions applied)
**Date:** 2026-06-01
**Status:** Draft for review — pairs with `MANIFEST_DRIVEN_NAME_REPAIR_PLAN.md` (v1.4)
**Source incidents:** `docs/design/RUN_011_M4_FIELD_AND_PATH_INVENTION_POSTMORTEM.md`
(Gaps A + B), `docs/design/CROSS_FILE_CONTRACT_RESOLUTION.md` §3–§4.
**Relationship:** defense-in-depth *backstop* to
`docs/design/APPROACH_A_PROJECT_KNOWLEDGE_REQUIREMENTS.md` (prevention).

> **What this is.** A deterministic, post-generation **repair** capability that
> corrects the two dominant cross-file content-contract failures from run-011 —
> *invented Prisma field names* (`aiRefId`, `title`, `supportingEvidence`) and
> *invented TS module-import paths* (`@/lib/prisma`, `@/lib/db/<model>`,
> `@/lib/ai/client`) — by matching each invented name against the **authoritative
> contract surface** (the parsed Prisma schema; the on-disk module/export table)
> and rewriting it to the nearest real name **only when a single high-confidence
> match exists**. It abstains (leaving the failure for the LLM-retry path) when the
> invention is ambiguous or structural (e.g. a presumed FK the schema doesn't model).

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (the feasibility framing — "the truth is already computed at
> detection time, so repair is a `difflib` call away") and v0.2 (after reading the
> live seams: `validators/prisma_usage.py`, `validators/cross_file_imports.py`,
> `contractors/prime_postmortem.py`, `repair/{routing,orchestrator,models}.py`,
> `repair/steps/contract_violation_fix.py`). The grounding pass corrected four
> assumptions; none invalidate the approach, but they relocate the work.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The repair step can **consume** `prisma_unknown_field` / `unresolvable_import` signals that already exist in the pipeline | Those scans (`scan_prisma_usage`, `scan_unresolvable_imports`) are invoked **only in `prime_postmortem.py`** — i.e. *after the run closes*. The repair pipeline runs **during** integration (`integration_engine._attempt_pre_merge_repair` / `_attempt_repair`) and never sees them. | **FR-1 reframed:** detection must be **lifted into the integration/repair path** (run the scan pre-merge, after assembly, before re-checkpoint), not consumed from the postmortem. The postmortem keeps its own scan as the honest-verdict layer. |
| The repair step consumes the classifiers' `PrismaUsageViolation` / `ImportViolation` objects, which "carry the candidate real set" | The frozen detection dataclasses carry only the **invented** token (`field` / `specifier`) plus a human-readable `detail` string with the model name embedded as prose. They do **not** carry the candidate valid set, nor a structured model name. | **FR-2:** the repair step **re-derives truth deterministically** (re-parse `prisma/schema.prisma` via `prisma_parser`; reuse the on-disk resolver from `cross_file_imports`). The classifier signal is the *trigger/locator* (which file, which token); the repair step owns truth. Detection layer stays unchanged. |
| "Leverage the **forward manifest**" (user's framing) | The forward manifest (`forward_manifest.py`) models *interface* contracts (functions/classes/signatures/imports) and is Python-centric; it carries **no Prisma field-content and no TS module-path** data. `contract_violation_fix.py` repairs only `missing_base_class` / `wrong_return_type` / `missing_parameter`. | **Concept renamed** from "forward-manifest-driven" to **"manifest-driven name repair"** where *manifest* = the authoritative contract surface (Prisma schema + on-disk module/export table today; the Approach-A `forward_project_knowledge.json` artifact later). This repair *generalizes the `contract_violation_fix` pattern* to a new violation class. |
| New violation type bolted onto `ContractViolationDiagnostic` | The repair routing table (`routing.py`) keys on categories `syntax`/`import`/`lint`/`semantic`; `contract_violation_fix` is wired via the splicer path, **not** `route_failures`. | **FR-4:** introduce **dedicated `Diagnostic` subclasses** (`MisnamedFieldDiagnostic`, `WrongImportPathDiagnostic`) + new routing rows, rather than overloading `ContractViolationDiagnostic`. Keeps the splice-time contract path untouched. |
| Approach-A artifact is the truth source | Approach A is **not yet shipped** (still Draft). | **NFR-5:** truth is sourced from the **live schema/disk today** behind a `TruthSource` seam; the Approach-A artifact becomes a swappable backend later (one resolver, two consumers — parity with Approach A FR-2). Repair ships **independently of, and sooner than, Approach A.** |

**Resolved open questions:**
- **OQ-1 → Lift detection into integration.** Run the cross-file content scans in the
  pre-merge repair path so the signal exists *during* the run. (Was: "consume the
  existing signal.")
- **OQ-2 → Re-derive, don't enrich.** The repair step re-parses the schema and reuses
  the on-disk resolver; the detection dataclasses are left unchanged.
- **OQ-3 → Dedicated diagnostics + routing rows**, not an overload of the splice-time
  `ContractViolationDiagnostic`.

Open questions that remain (OQ-4…OQ-7) are in §6.

---

## 0.1 Implementation Findings (post-build, supersede where noted)

> Discovered while implementing + testing the six increments. These correct
> over-optimistic claims in FR-3/FR-5/FR-8 — exactly the kind of thing only
> running the code reveals. The **design is sound**; the *scope of the field
> lever* was overstated.

1. **The run-011 field inventions are mostly SYNONYMS, not typos — string
   similarity cannot repair them (OQ-4 resolved empirically).** `difflib` ratios:
   `title`→`name` ≈0.40, `aiRefId`≈0.44, `label`≈0.44, `outcomeId`≈0.43 — all far
   below any safe cutoff. Only `supportingEvidence`→`evidence` (≈0.538) is a real
   near-match. So with `DEFAULT_CUTOFF=0.5`, the field-rename step **repairs the
   typo/substring class and correctly abstains on the synonym class** (→ FAILED →
   LLM-retry per FR-1's exit contract). FR-5/FR-8 "PI-001/004/007 fields repaired"
   is **superseded**: those abstain; the headline value for the run-011 *field*
   cases is honest detection→retry, not rewrite. (The synonym class needs
   semantic/embedding matching — out of v1 scope.)
2. **The import lever carries the run-011 import cases deterministically.** The
   seeded negatives map + sub-path collapse repair `@/lib/prisma`→`@/lib/db`,
   `@/lib/ai/client`→`@/lib/ai/service`, `@/lib/db/<model>`→`@/lib/db` exactly —
   verified by the Inc 6 harness. This is where FR-6 delivers run-011 value.
3. **Import nearest-match needs a stricter cutoff (0.8) than fields (0.5).** The
   shared `@/lib/` prefix inflates path similarity (unrelated paths score ~0.5),
   so the field cutoff would false-rewrite; path typos score ~0.9.
4. **Routing-table wiring moved from Inc 2 → Inc 4** (it needs the step classes to
   import cleanly); diagnostics/bridge/config/additive-field shipped in Inc 2.
5. **`content_contract` rows fire both rename steps; each no-ops when its
   diagnostic subtype is absent** (no per-pattern discriminator for non-semantic
   categories in `route_failures`).

---

## 1. Problem Statement & Gap Table

Run-011 (the M4 batch) produced the first **honest** verdict of the session (0.50 /
PARTIAL): Approach-B's classifiers now *detect* cross-file content violations. But
detection is the end of the line — the failures are reported, then either direct-fixed
by hand or regenerated. There is **no automated repair** for the two dominant,
model-capability-invariant invention classes, even though the correct names are
deterministically knowable from artifacts already on disk.

| Failure class | run-011 inventions | Truth on disk | Detected today? | Repaired today? |
|---------------|--------------------|---------------|-----------------|-----------------|
| **Invented Prisma field names** | `aiRefId`, `label`, `outcomeId`, `title`, `supportingEvidence` | `prisma/schema.prisma` field sets (`name`, `category`, `evidence`, …) | ✅ `prisma_unknown_field` (postmortem only) | ❌ none |
| **Invented TS module paths** | `@/lib/prisma` (4th recurrence), `@/lib/db/<model>`, `@/lib/ai/client` | on-disk files: `@/lib/db`, `@/lib/ai/service` | ✅ `unresolvable_import` (postmortem only) | ❌ none |
| **Presumed-FK inventions** | `outcomeId` on `Metric` (no relation exists) | schema declares **no** FK | ✅ `prisma_unknown_field` | ❌ none — *and must NOT be auto-renamed* |

**Why repair (not just prevention).** Approach A (prevention) injects the truth into the
spec prompt but explicitly **does not claim 100% adherence** (its OQ-4). The postmortem's
strongest evidence is that *even Opus on PI-010 invented the same names* — invention is a
locality property of probabilistic generation, invariant to model capability. A
deterministic post-generation rewrite of the **typo-class** subset (a wrong-but-close name
with one obvious correct target) is the Hayai "don't defer enforcement" backstop: it
catches what prevention misses, at zero LLM cost, before the failure consumes a retry.

**Scope boundary (the load-bearing one).** This repairs **typo-class** inventions only —
where a single real name is an unambiguous near-match. It **abstains** on **structural**
inventions (no good match; a presumed FK; an ambiguous tie), leaving those for the
existing LLM-retry path. Auto-renaming a structural invention would produce
syntactically-valid, semantically-wrong code — the one outcome worse than failing
honestly.

---

## 2. Goal

After a feature's files are assembled but before the merge is finalized, deterministically
detect invented Prisma field names and invented TS module-import paths, and rewrite each to
its unambiguous on-disk counterpart — measurably reducing the run-011 field/path failure
classes on re-run, never rewriting a structural/ambiguous invention, fully behind the
existing non-destructive guard, at zero LLM cost.

---

## 3. Functional Requirements

### FR-1 — Detection inside the integration/repair path (unconditional trigger)
The cross-file content scans (`scan_prisma_usage` for `prisma_unknown_field`;
`scan_unresolvable_imports` for `unresolvable_import`) run in the **pre-merge** repair path
(`integration_engine._attempt_pre_merge_repair`), over the assembled feature file set, and
emit repair diagnostics (FR-4). **The content scan MUST run unconditionally — on its own
trigger — independent of any prior syntax/lint failure.** Invented-but-syntactically-valid
names (`aiRefId`, `@/lib/prisma`) produce **no** syntax or lint diagnostic (lint runs with
`ignore_codes=["F401"]`). Two layers of gating must be defeated for the scan to run:
1. **The outer call-site gate (R3-F1, critical).** `_attempt_pre_merge_repair` is only
   *invoked* inside `if pre_result.status == CheckpointStatus.FAILED:` at
   `integration_engine.py:2313-2317`. A clean-syntax feature yields `pre_validate` = PASSED,
   so the method is **never called** — the content scan MUST be invoked from the call site
   **even when `pre_validate` passes** (for TS+Prisma features), not only on failure.
2. **The two inner early-returns** at `845-846` and `851-855` (the second derives
   `repairable` from syntax/lint categories only), which a diagnostics-piggyback would die on.
The content scan is a separate gate that reaches `run_file_repair` even when syntax+lint pass.
The postmortem retains its own independent scan (the honest verdict is unaffected).

**Exit contract — an abstain MUST NOT become a silent PASS (R4-F1, critical).** When a content
violation is detected but the repair **abstains** (structural/ambiguous) or a rewrite is rolled
back, the file is unmodified, so the live method returns `None` (line 910), leaving the outer
`pre_result` **PASSED** and merging the invented name — silently skipping the LLM-retry loop,
which only fires on a FAILED pre-merge checkpoint. The integration path MUST instead **report a
FAILED checkpoint** to the orchestrator whenever any content violation remains un-repaired,
carrying the residual diagnostics. Abstain-safe (NFR-3) means *don't corrupt*; this means *don't
silently pass* — both hold.
*Acceptance:* (1) a reproduction of PI-001 whose file **passes** `check_syntax` and `check_lint`
(so `pre_validate` returns PASSED) still **invokes** the content/name-repair path (assert via
spy/mock — not merely that diagnostics *would* be produced if it ran) and produces a
`MisnamedFieldDiagnostic(field="aiRefId", model="Capability", file=…)` **before** the merge is
finalized; (2) a structural invention (`Metric.outcomeId`) that passes syntax/lint, is detected,
and is **abstained** forces the pre-merge checkpoint to **FAILED** (routes to retry, not merge);
the postmortem scan still runs and reports identically to today.

### FR-2 — Deterministic truth re-derivation + structured model binding
The repair step derives the authoritative name set itself: Prisma field sets via
`languages.prisma_parser.parse_prisma_schema`; canonical module/export paths via the
on-disk resolver (`upstream_interface.resolve_specifier_to_paths` /
`cross_file_imports._resolves_on_disk`) and the exported-symbol table
(`upstream_interface.extract_ts_exports`).

**Model-name sourcing (resolves the tension with NFR-6).** The repair target requires the
structured model name per call site, but `PrismaUsageViolation` carries only
`kind/source_file/field/detail/severity` — the model lives in `detail` prose and the
`accessor` map is a function-local in `scan_prisma_usage`, never returned (verified
`prisma_usage.py:41-49,134,185`). v1 resolves this by **adding a single additive `model:
str` field to `PrismaUsageViolation`** (default `""`, populated where the scan already binds
`model_name`). This is an *additive-only* change — no existing field renamed or removed, the
postmortem path reads it or ignores it unchanged. NFR-6 is amended accordingly. (Rejected
alternative: regex-parsing the model out of `detail` prose — brittle, couples repair to a
human-readable string format.)
*Acceptance:* given a `PrismaUsageViolation` from a real `scan_prisma_usage` run, the bridge
produces `MisnamedFieldDiagnostic(model="Capability", field="aiRefId", …)`; the step then
computes the valid field set for that model and the valid module-path set with zero LLM
calls; the postmortem's existing assertions over `scan_prisma_usage` output still pass.

### FR-3 — Nearest-match rewrite with a deterministic abstain decision
For each diagnostic, call `difflib.get_close_matches(invented, candidates, n=2,
cutoff=0.6)` (n and cutoff configurable). The decision is fully specified by the count of
returned candidates that clear the cutoff:
- **0 candidates** → abstain, reason `no_candidates` (covers the empty-valid-set case).
- **1 candidate** → **rewrite** (no runner-up exists; the margin test is vacuously
  satisfied). This is the typo-class happy path.
- **2 candidates** → rewrite **only if** `score[0] − score[1] ≥ margin` (default `0.1`);
  otherwise abstain, reason `ambiguous_tie`. Exactly-equal scores (`Δ = 0`) always abstain.

There is **no** `structural` parameter (R4-S3): nothing in the detection layer produces an
FK signal, so a presumed FK like `Metric.outcomeId` is handled by the **`no_candidates`**
branch (it has no near-match in `Metric`'s real fields) rather than an unwireable flag. Every
abstain emits an `abstained` metric tagged with the reason (FR-9). (Residual risk: a structural
invention that happens to be near a real field would rewrite — a known v1 limitation, logged;
an `is_fk_heuristic` diagnostic field is the deferred mitigation.)
*Acceptance:* `title → name`, `supportingEvidence → evidence`, `@/lib/prisma → @/lib/db`
rewrite (single dominant match); `label` against `{name, notes}` abstains `ambiguous_tie`;
an empty valid set abstains `no_candidates`; two equal-scoring candidates abstain. OQ-4 tunes
the `0.6`/`0.1` defaults against this set.

### FR-4 — Dedicated repair diagnostics + routing + config category
Add `MisnamedFieldDiagnostic` (category `content_contract`, carries `field`, `model`,
`file`, `call_site_hint`) and `WrongImportPathDiagnostic` (category `content_contract`,
carries `specifier`, `file`) to `repair/models.py`. Add routing rows in `repair/routing.py`
mapping `prisma_unknown_field → [prisma_field_rename, …]` and
`unresolvable_import → [import_path_rename, …]`, gated to the `nodejs` language, followed by
`js_syntax_validate`.

**`content_contract` MUST be in `RepairConfig.repairable_categories` (R3-F2).** `route_failures`
filters every route against that set at `repair/routing.py:290`, **independently** of the
integration_engine `repairable` check (FR-1). The default at `repair/config.py:67` omits
`content_contract`; without adding it, merged content diagnostics reach `run_file_repair` but
route to **zero steps** — a silent no-op indistinguishable from "no violations." Update the
default and any prime-contractor config examples.
*Acceptance:* `route_failures` returns the two new steps for the two new patterns **with the
default `RepairConfig`**; a config that excludes `content_contract` skips them with an explicit
log/metric; existing routes are byte-for-byte unchanged (regression test on the routing table).

### FR-5 — `prisma_field_rename` repair step
A `RepairStep` (TS-text-based, mirroring the Go/C# text-splice style — **not** Python AST)
that rewrites invented field keys inside the relevant `db.<model>.{create,update,where,…}`
object-literal call sites to the FR-3 match. It edits only keys that the scan flagged for
the specific model, never bare identifiers elsewhere in the file.
*Acceptance:* PI-001/004/007 reproductions emit `db.<model>.create/update` calls using only
real fields after repair; `Metric.outcomeId` (presumed FK, no near-match) is left untouched
(abstain), preserving the honest failure.

### FR-6 — `import_path_rename` repair step
A `RepairStep` that rewrites the specifier in `import … from '<spec>'` / `require('<spec>')`
statements whose specifier the scan flagged as unresolvable, to the FR-3 canonical path.
Seeds the negative→canonical map with the known recurring inventions
(`@/lib/prisma → @/lib/db`, `@/lib/ai/client → @/lib/ai/service`) and otherwise relies on
nearest-match against the real module-path set. Invented **sub-paths**
(`@/lib/db/<model>`) collapse to their resolvable parent when unambiguous.
*Acceptance:* PI-002/007 reproductions import only on-disk paths after repair; an
unresolvable specifier with no near-match abstains.

### FR-7 — Non-destructive guarantee + full-envelope pre-image rollback
Every rewrite passes through the existing per-step non-destructive guard (REQ-RPL-003). A
file is rolled back **iff** re-validation shows a *newly introduced* defect — not merely a
*remaining* one. Formally: roll back iff **(1)** `post_repair_content_diagnostics −
pre_repair_content_diagnostics` is **non-empty** (a brand-new `content_contract` violation),
**or (2)** `check_syntax` newly fails (R2-F2 — a rename can resolve its content violation while
producing a duplicate-key / unbalanced-brace syntax error a content-only re-scan would miss).

**Strict-subset, NOT zero-violation (R4-F2, critical).** A file may legitimately carry one
**repaired** typo (`aiRefId → name`) and one **abstained** structural invention (`outcomeId`)
in the same call set. The abstained violation *remains* on re-scan; a naive "zero content
violations remain → roll back" would **discard the successful `aiRefId` repair**. The kept
condition is therefore that post-repair diagnostics are a **strict subset** of the pre-repair
set (nothing new), not the empty set. The residual abstained violation is still reported and
(per FR-1's exit contract) forces the checkpoint to FAILED for retry — but the partial repair
is preserved.

**Rollback mechanism — full envelope (the pre-merge seam writes in place + mutates the
registry).** `_attempt_pre_merge_repair` writes repaired content directly to disk with "no
staging needed" (`integration_engine.py:879-882`) **and** updates the element registry
(`set_phase_status(…, "repaired", {"repair_stage": "pre_merge"})`, lines 884-892) — the latter
currently runs *before* re-validation. The name-repair path MUST therefore: capture a per-file
pre-image (exact pre-repair bytes); on re-validation failure restore the pre-image; **and
ensure the registry `repaired` flag is applied only to files actually kept** (R2-F1 — a
byte-identical file restore that leaves the registry asserting `repaired` is a *lying registry*
that corrupts FR-9 attribution). "Restore" means a consistent file **and** registry, not bytes
alone. Owned by the seam, not assumed from the orchestrator.
*Acceptance:* (1) a rewrite that introduces a *new* unknown field **or** a new syntax error
fails re-validation and the file is restored **byte-identical** to its captured pre-image
**and** its element-registry entry is **not** flagged `repaired`; (2) a file with `aiRefId`
(repaired) **and** `outcomeId` (abstained) **keeps** the `aiRefId` fix — the remaining
`outcomeId` does **not** trigger rollback (strict subset) — while the checkpoint still goes
FAILED for the residual; the original violation re-surfaces for the retry path.

### FR-8 — Validation against run-011 (headline gate)
A reproduction harness over the run-011 failed features asserts: PI-001/004/007 invented
fields are repaired (FR-5) **except** the structural `outcomeId` FK (abstained);
PI-002/007 invented paths are repaired (FR-6); a baseline without the repair step preserves
existing behavior (regression guard).
*Acceptance:* the harness passes; the **rewrite set ⊇ {(Capability, aiRefId→name),
(Differentiator, title→name), (Differentiator, supportingEvidence→evidence)}**, the
**abstain set ⊇ {(Metric, outcomeId) [structural FK], (any model, label) [ambiguous_tie]}**,
and **no structural invention is ever rewritten** (the safety invariant). The exact
per-feature expected sets are frozen in the Inc 6 harness fixture; `<ties>` is enumerated
there, not left as a placeholder.

### FR-9 — Observability & attribution
Each rewrite/abstain emits the existing repair metrics (REQ-RPL-401) and a
`RepairAttribution` (REQ-RPL-403) entry: `{step, file, from, to, similarity, decision:
rewrite|abstain, reason}`. Abstains are first-class telemetry. To make "a high abstain rate
signals a prevention gap" a **verifiable** contract, emit aggregate counters
`repair.name.attempts`, `repair.name.rewrites`, and `repair.name.abstains` (the last with
labels `{step, reason}`), and the derived gauge **`repair.name.abstain_ratio` = abstains /
attempts** with labels `{step}`. The Kaizen consumption point: an `abstain_ratio` above a
configurable threshold (default `0.5`) over a run is surfaced as an Approach-A prevention
gap (the truth exists but the LLM keeps inventing un-repairably).
*Acceptance:* an OTel span per attempt carries `from/to/similarity/decision`; a 1-rewrite /
1-abstain feature emits `attempts=2, rewrites=1, abstains{reason}=1, abstain_ratio=0.5`; a
repair-attempt artifact (REQ-RPL-404) records the abstain reasons.

### FR-10 — Swappable truth source (Approach-A convergence)
Truth derivation (FR-2) sits behind a `TruthSource` protocol with a live-schema/disk
implementation for v1. When Approach A's `forward_project_knowledge.json` ships, a
second implementation reads the artifact instead — no change to the repair steps.
*Acceptance:* the repair steps depend only on the `TruthSource` protocol; swapping the
implementation requires no edit to `prisma_field_rename` / `import_path_rename`.

---

## 4. Non-Functional Requirements

- **NFR-1 Deterministic.** No LLM in detection, truth derivation, or rewrite; same inputs → same edit.
- **NFR-2 Bounded + staged rollout.** One scan per feature in the pre-merge path; rewrite cost is linear in flagged tokens. A per-feature ceiling caps the work: if flagged tokens exceed a configurable max (default `200`), the step logs and abstains on the overflow rather than looping unbounded on pathological input. **Rollout gate (R3-F3):** the content gate is governed by `RepairConfig.pre_checkpoint_repair` (the integration_engine docstring at line 803 already claims this flag controls the pre-merge path, but it is currently *unwired* — `config.py:68`, default `False`). v1 wires it as the master enable so the capability ships dark and is enabled deliberately; a config reference that documents a dead flag is not acceptable.
- **NFR-3 Abstain-safe (degrade loudly).** When in doubt, **do not edit** — emit an honest abstain that preserves the existing failure path. A wrong rename is worse than no rename.
- **NFR-4 TS/Prisma-first, extensible.** v1 targets the TS + Prisma surface run-008/009/011 failed on; the `TruthSource` + step abstraction extends to other languages without rework.
- **NFR-5 Truth-source-swappable.** Live schema/disk now; Approach-A artifact later (FR-10).
- **NFR-6 Detection-layer-stable (additive-only).** No *breaking* changes to `validators/prisma_usage.py` or `validators/cross_file_imports.py` — no field renamed or removed, no scan signature changed, the postmortem path reads identically. **Amended (R1-F2/S3):** a single *additive* `model: str = ""` field on `PrismaUsageViolation` is permitted (FR-2), since it is backward-compatible and the postmortem ignores it. "Stable" means additive-compatible, not frozen.

---

## 5. Non-Requirements (v1)

- **Not** a replacement for Approach A (prevention) — this is the backstop; both share truth (FR-10).
- **Not** repairing structural inventions (presumed FKs, missing relations, ambiguous ties) — those **abstain** by design.
- **Not** repairing Zod↔Prisma symmetry (`prisma_zod_symmetry`), compound-key, or `prisma_where_not_unique` violations in v1 — field-name + import-path only.
- **Not** the TS2345 / type-class family (a separate signature backlog; already shipped on the detection side per the postmortem §6 addendum).
- **Not** touching the forward manifest (`forward_manifest.py`) or the splice-time `contract_violation_fix` path.
- **Not** guaranteeing the LLM produced repairable output — un-repairable cases abstain and flow to the existing retry path unchanged.

---

## 6. Open Questions

- **OQ-4 — Cutoff & margin defaults.** `difflib` cutoff `0.6` / margin `0.1` are starting
  points; resolve empirically against the run-011 set (must rewrite `title→name`,
  `supportingEvidence→evidence`; must abstain on `label`). *(Plan: tune in FR-8 harness.)*
- **OQ-5 — Where exactly in `_attempt_pre_merge_repair`** the scan slots relative to the
  existing syntax/import repair steps (before, so a path fix doesn't mask a field error?).
  *(Plan to resolve by reading the pre-merge sequence.)*
- **OQ-6 — Sub-path collapse heuristic (FR-6).** `@/lib/db/capabilities → @/lib/db` is a
  parent-collapse; is parent-collapse safe in general, or only for the seeded negatives?
  *(Lean: seeded negatives + exact parent-on-disk check; no speculative collapse.)*
- **OQ-7 — Multi-model files.** A file using two models where the same invented key is valid
  on one and not the other — does the per-call-site model binding (already in the scan) fully
  disambiguate the rewrite target? *(Plan: confirm the scan's `model_name` is per-call-site.)*

---

## 7. Relationship to the roadmap

- **Closes (repair side):** RUN-011 Gap A (FR-5) + Gap B (FR-6) for the typo-class subset,
  *after* the LLM has already invented — complementary to Approach A closing them *before*.
- **Backstops:** Approach A — prevention maximizes adherence, this repairs the residual;
  abstain telemetry (FR-9) measures the residual and feeds the Kaizen loop.
- **Generalizes:** the `contract_violation_fix` repair pattern to a new content-contract
  violation class (name resolution), without disturbing the splice-time path.
- **Shares truth with:** Approach A via the `TruthSource` seam (FR-10) — one resolver,
  two consumers (prevent + repair), per Approach A FR-2.
- **Does not gate:** strtd8 M4–M6 delivery; ships independently of Approach A.

---

*v0.2 — Post-planning self-reflective update: detection relocated from postmortem to the
integration/repair path (OQ-1); truth re-derived rather than consumed (OQ-2); dedicated
diagnostics + routing rather than overloading the splice path (OQ-3); concept renamed from
"forward-manifest" to "manifest-driven contract-surface" repair; truth source made swappable
for Approach-A convergence. 4 assumptions corrected, 3 open questions resolved, 4 remain.*

*v0.3 — Post-CRP R1 (dual-document review by claude-opus-4-8-1m). All 6 F-suggestions
applied; 3 blocking findings (unconditional trigger, model-name sourcing, pre-image
rollback) verified against live code before merge. The pre-merge seam's syntax/lint
short-circuit and write-in-place behavior were the highest-value catches — they would have
shipped as dead code + an unbacked rollback. Dispositions in Appendix A/B; round history in
Appendix C. Pairs with `MANIFEST_DRIVEN_NAME_REPAIR_PLAN.md` v1.1.*

*v0.4 — Post-CRP R2 (focused review of the un-reviewed Inc 5 delta). Both F-suggestions
applied to FR-7: the rollback envelope now includes the element registry (R2-F1 — a
byte-identical file restore that left the registry flagged `repaired` would corrupt FR-9
attribution), and re-validation now includes `check_syntax` (R2-F2 — a rename can resolve its
content violation while introducing a syntax error a content-only re-scan misses). R2 vindicated
the second round: both are real second-order integration defects in R1's own fix, not in the
original design. Pairs with `MANIFEST_DRIVEN_NAME_REPAIR_PLAN.md` v1.2.*

*v0.5 — Post-CRP R3 (a different model, `composer-2.5`). All 3 F-suggestions applied. R3 found
the **outer call-site gate** (FR-1): `_attempt_pre_merge_repair` runs only on a FAILED
`pre_validate` (2313-2317), so it never fires for clean-syntax invented names — the headline
run-011 failure class — making the R1/R2 internal fixes unreachable. Also: `content_contract`
absent from `repairable_categories` (FR-4) and the unwired `pre_checkpoint_repair` knob (NFR-2).
The three rounds form a clean cautionary arc — internal gates (R1) → ordering/registry (R2) →
the outer call gate (R3) — each found beneath the last. Model diversity earned its keep on R3.
Pairs with `MANIFEST_DRIVEN_NAME_REPAIR_PLAN.md` v1.3.*

*v0.6 — Post-CRP R4. Both F-suggestions applied: the **exit contract** (FR-1 — an abstain must
force a FAILED checkpoint so the invented name routes to LLM-retry instead of silently merging,
the live `return None`→PASSED bypass) and **strict-subset re-validation** (FR-7 — a kept
abstained violation must not roll back a successful partial repair). Four rounds, each a layer
deeper than the last: entry gates → ordering → the call gate → the exit/retry semantics. The
arc is the artifact: a name-repair seam looks trivial (`difflib` + rewrite) but its correctness
lives entirely in the integration plumbing the four rounds peeled back. Pairs with
`MANIFEST_DRIVEN_NAME_REPAIR_PLAN.md` v1.4.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**, then
> dispositions are recorded in **Appendix A** (applied) or **Appendix B** (rejected).
> Reviewers: scan A/B/C first and do **not** re-propose settled or rejected items.

### Appendix A: Applied Suggestions

**R1 triage (2026-06-01, orchestrator: claude-opus-4-8-1m).** All 6 F-suggestions ACCEPTED.
Three (F1/F2/F3) were verified against the live `integration_engine.py` / `prisma_usage.py`
before acceptance.

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R1-F1 | ACCEPTED | FR-1 retitled "unconditional trigger"; acceptance now requires detection when syntax+lint **pass** (verified short-circuit at `integration_engine.py:845-846`). |
| R1-F2 | ACCEPTED | FR-2 adds the additive `model: str` field on `PrismaUsageViolation` (option a); NFR-6 amended to "additive-only". Regex-from-prose alternative rejected (see Appendix B). |
| R1-F3 | ACCEPTED | FR-7 rewritten with explicit per-file pre-image capture + byte-identical restore (verified write-in-place at `integration_engine.py:879-882`). |
| R1-F4 | ACCEPTED | FR-3 rewritten with the 0/1/2-candidate branching, `n=2`, and the equal-score tie rule. |
| R1-F5 | ACCEPTED | FR-8 acceptance restated as superset rewrite/abstain sets + "no structural invention ever rewritten"; `<ties>` enumerated in the harness fixture. |
| R1-F6 | ACCEPTED | FR-9 adds `repair.name.{attempts,rewrites,abstains,abstain_ratio}` counters + 0.5 threshold. |

**R2 triage (2026-06-01, focused on the Inc 5 delta).** Both F-suggestions ACCEPTED; both
verified against `integration_engine.py` (registry update at 884-892 precedes `pre_validate`
at 895).

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R2-F1 | ACCEPTED | FR-7 rollback envelope extended to cover the element registry — "restore" now means consistent file **and** registry; rolled-back files must not be flagged `repaired`. |
| R2-F2 | ACCEPTED | FR-7 re-validation broadened from content-only to **content + `check_syntax`**; a rename-induced syntax error now triggers rollback. |

**R3 triage (2026-06-01, `composer-2.5` — a different reviewer model).** All 3 F-suggestions
ACCEPTED; each verified against live code. R3 found the outer call-site gate that R1+R2 missed.

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R3-F1 | ACCEPTED | FR-1 — acceptance now requires the **call site** (2313-2317) to invoke name-repair when `pre_validate` PASSES; assert via spy/mock. Critical. |
| R3-F2 | ACCEPTED | FR-4 — `content_contract` must be in `RepairConfig.repairable_categories`; verified independent filter at `routing.py:290`. |
| R3-F3 | ACCEPTED | NFR-2 — `pre_checkpoint_repair` wired as the staged-rollout master enable; verified dead flag at `config.py:68`. |

**R4 triage (2026-06-01, `claude-opus-4-8-1m`).** Both F-suggestions ACCEPTED; both criticals
verified against the live `return None`→PASSED→merge path. R4 covered the *exit* contract.

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R4-F1 | ACCEPTED | FR-1 — new **exit contract**: an abstain/residual content violation forces a FAILED checkpoint (no silent PASS/merge). Critical. |
| R4-F2 | ACCEPTED | FR-7 — re-validation is **strict-subset** (roll back only on a newly introduced defect); a kept abstained violation does not discard a partial repair. Critical. |

### Appendix B: Rejected Suggestions (with Rationale)

- **R1-F2 sub-alternative (regex-parse model from `detail` prose)** — REJECTED in favor of
  the additive `model` field. Coupling repair to a human-readable f-string format is brittle
  and would break silently if the `detail` wording changes. The additive field is
  backward-compatible and explicit.

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 21:30:00 UTC
- **Scope**: Requirements review (F-suggestions) — testability/traceability of FR-1..FR-10 and NFR-1..NFR-6, with grounding against the live seams (`validators/prisma_usage.py`, `validators/cross_file_imports.py`, `contractors/integration_engine.py`). Dual-document mode; plan reviewed separately (S-suggestions).

**Executive summary (top risks / gaps):**

- **Blocking:** FR-1's acceptance assumes detection runs in `_attempt_pre_merge_repair`, but that method returns early unless a *syntax/lint* check fails (verified at `integration_engine.py:838-851`). Invented-but-valid TS names lint clean, so the content scan would never fire. FR-1 must mandate an *unconditional* scan trigger, independent of syntax/lint failure.
- **Blocking:** FR-2/FR-5 require a structured `(file, invented_token, model_name)` tuple, but `PrismaUsageViolation` (verified `prisma_usage.py:41-49`) carries **no** `model_name` — only `kind/source_file/field/detail/severity`, with the model embedded in `detail` prose. The requirement to leave detection dataclasses unchanged (FR-2, NFR-6) is in direct tension with the data FR-5 needs.
- **High:** FR-7's "staging discarded / rolled back" presumes a per-file staging mechanism at the pre-merge seam; the live seam writes repaired files **in place** ("no staging needed", `integration_engine.py:877`). The rollback contract is unspecified against the real code.
- **Medium:** FR-3's abstain math (cutoff + margin) is underspecified for the `n` returned by `get_close_matches`; "strictly better than the runner-up" is undefined when only one candidate clears the cutoff.
- **Medium:** FR-8's acceptance (`abstain set is exactly {Metric.outcomeId, <ties>}`) is not testable because `<ties>` is not enumerated.
- **Low/Medium:** FR-9 abstain-rate "prevention gap" signal lacks a denominator/threshold; NFR-2 "bounded" lacks a numeric ceiling.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | high | FR-1: change the acceptance criterion so the content scans run **unconditionally** in the pre-merge path (their own trigger), not as diagnostics appended to a list that only forms on a prior syntax/lint failure. State explicitly that invented-but-syntactically-valid names produce no syntax/lint diagnostic. | Verified at `integration_engine.py:838-851`: `_attempt_pre_merge_repair` returns `None` when `not failed_results` or `not repairable`, before `run_file_repair` is reached. Invented field/import names lint clean, so the FR-1 path as written never executes for the target failure class. | FR-1 — *Acceptance* paragraph ("the integration path produces a `MisnamedFieldDiagnostic`…") | Unit test: a feature with valid syntax but an invented field yields a `MisnamedFieldDiagnostic` even though `check_syntax`/`check_lint` pass. |
| R1-F2 | Data | high | FR-2/FR-5: resolve the model-name sourcing contract. `PrismaUsageViolation` carries no structured `model_name` (only `field` + prose `detail`). Either (a) permit a minimal additive `model` field on the violation (and amend NFR-6 to allow additive-only fields), or (b) specify that the bridge regex-parses the model from `detail` and pin the exact `detail` format as a contract. Pick one; the doc currently implies both are forbidden. | Verified `prisma_usage.py:41-49,185`: model name lives only inside the `detail` f-string; the `accessor` map is a local, not returned. FR-2 says dataclasses are "not modified" and NFR-6 forbids shape changes, yet FR-5 needs the model per call site. | FR-2 first sentence + NFR-6 + §0 row "Model name only in detail prose" | Test: bridge recovers `model="Capability"` for an `aiRefId` violation from whichever source is chosen; if regex, a fixture pins the `detail` string format. |
| R1-F3 | Risks | high | FR-7: define the rollback mechanism concretely. The pre-merge seam writes repaired content in place with "no staging needed" (`integration_engine.py:877`); there is no per-file staging to "discard." Specify either an explicit pre-image snapshot taken before name-repair, or relocate name-repair to a path that does stage. | FR-7 says "the per-file staging for that file is discarded (the orchestrator already stages)" — verified false for `_attempt_pre_merge_repair`. The rollback acceptance test cannot pass against a write-in-place seam. | FR-7 *Acceptance* + the parenthetical "the orchestrator already stages" | Test: a rewrite that fails re-validation leaves the file byte-identical to its pre-repair content (assert against a captured pre-image). |
| R1-F4 | Validation | medium | FR-3: make the abstain decision deterministic and testable. Specify (a) `n` passed to `get_close_matches` (the doc says `n=2` in the plan but FR-3 omits it), (b) the tie/margin rule when only **one** candidate clears the cutoff (no runner-up → is "strictly better by margin" auto-satisfied?), and (c) tie-break behavior when two candidates are exactly equal. | FR-3 says "exactly one match at or above the cutoff AND strictly better than the runner-up by margin" — undefined when the runner-up is absent or scores 0. Ambiguous spec → ambiguous tests (the `label` case in OQ-4 depends on this). | FR-3 second sentence ("Rewrite only when there is exactly one match…") | Parametrized test: zero-runner-up rewrites; equal-runner-up abstains (`ambiguous_tie`); single-candidate-below-margin abstains. |
| R1-F5 | Validation | medium | FR-8: enumerate `<ties>`. The acceptance "the abstain set is exactly `{Metric.outcomeId, <ties>}`" is untestable while `<ties>` is a placeholder. List the exact expected abstains from the run-011 set (e.g. `label`), or restate as "abstain set ⊇ {Metric.outcomeId} and contains no rewrite of a structural invention." | An exact-set assertion with an unspecified member cannot be coded; the harness in plan Inc 6 needs a concrete expected set. | FR-8 *Acceptance* | Harness asserts an explicit frozen set of `(model, field)` abstains derived from the five M4 features. |
| R1-F6 | Ops | medium | FR-9: give the abstain-rate signal a denominator and a threshold. "A high abstain rate signals a prevention gap" has no defined rate (abstains / total attempts? per name? per run?) or alerting threshold, so it is not a verifiable telemetry contract. | FR-9 is the feedback hook into Kaizen/Approach-A but provides no measurable trigger; without it the "first-class telemetry" claim is aspirational. | FR-9 second sentence + §7 "Backstops" bullet | Define metric `repair.name.abstain_ratio` with labels `{step, reason}`; test that a 1-rewrite/1-abstain feature emits ratio 0.5. |

**Endorsements / Disagreements:** none (first review round; Appendix A/B empty).

#### Review Round R2 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 21:45:00 UTC
- **Scope**: FOCUSED R2 (Feature Requirements) — the un-reviewed Inc 5 delta only: the FR-1 unconditional-trigger and FR-7 pre-image-rollback changes the PLAN §6 implements. Read the live `integration_engine.py:786-910` and `checkpoint.py:549` before writing. R1 FR-set is otherwise out of scope.

**Executive summary (top requirements gaps for the Inc 5 delta):**

- **High (FR-7):** the "byte-identical restore" acceptance is incomplete — the pre-image is file-bytes only, but the live code mutates the **element registry** (`set_phase_status(…, "repaired")`, `integration_engine.py:884-892`) outside the restore envelope. A byte-identical file restore can pass while the registry diverges (rolled-back file still flagged `repaired`). FR-7 must define the *full* rollback envelope, not just file content.
- **Medium (FR-7):** FR-7's re-validation says "a re-run of the triggering scan (FR-1) confirms … no new `content_contract` violation" — content-only. A rename can introduce a *syntax* error (not a content violation); FR-7 acceptance should also require no new **syntax** failure before keeping a file.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Risks | high | FR-7: extend the rollback contract beyond file bytes to cover the **registry/side-effect envelope**. The live seam updates the element registry (`set_phase_status(…, "repaired", {"repair_stage": "pre_merge"})`, `integration_engine.py:884-892`) for repaired files; the pre-image captures only `{path: original_bytes}`. State that a rollback must also revert (or never apply) the registry `repaired` flag for restored files, so "byte-identical restore" implies a consistent registry, not just a consistent file. | The current *Acceptance* ("restored byte-identical … original violation re-surfaces") can pass while the registry lies that the file was `repaired`, corrupting FR-9 `RepairAttribution`/abstain accounting. Plan-side mirror is R2-S3. | FR-7 *Acceptance* paragraph + the "Rollback mechanism" paragraph | Test: a rewrite that fails re-validation leaves the file byte-identical **and** the element-registry entry not flagged `repaired`. |
| R2-F2 | Validation | medium | FR-7: broaden re-validation from content-only to **content + syntax**. FR-7 currently confirms "no new `content_contract` violation was introduced." A key rewrite can resolve its content violation while introducing a syntax error (unbalanced brace, duplicate key) that is not a `content_contract` violation and so escapes the gate. Add: a re-run of `check_syntax` on the repaired file must also pass, else restore the pre-image. | A content-only gate is blind to rename-induced syntax regressions — the valid-but-broken outcome FR-7 exists to prevent (NFR-3). Plan-side mirror is R2-S5. | FR-7 first paragraph ("a re-run of the triggering scan (FR-1) confirms…") | Parametrized test: a rename producing a duplicate-key / unbalanced-brace syntax error is rolled back to the byte-identical pre-image. |

**Endorsements (prior untriaged items — none remain untriaged):** R1-F1 (unconditional trigger) and R1-F3 (pre-image rollback) are in Appendix A; R2-F1 extends R1-F3 (it did not consider the registry side effect), R2-F2 extends both R1-F1 and R1-F3 (re-validation scope).

**Disagreements:** none.

#### Review Round R3 — composer-2.5 — 2026-06-01 20:15 UTC

- **Reviewer**: composer-2.5
- **Date**: 2026-06-01 20:15:00 UTC
- **Scope**: Fresh R3 on the Inc 5 delta (FR-1 / FR-7), per `.crp-r2-focus-inc5.md`. Grounded against `integration_engine.py:786-910` and the **call site at 2313-2317**. Does not re-litigate R1 accepted FR-set.

**Executive summary:**

- **Critical (FR-1):** FR-1 mandates an unconditional content scan in `_attempt_pre_merge_repair`, but the live caller only invokes that method when `pre_validate` FAILED (2313-2317). Clean-syntax invented names never reach FR-1 — acceptance criterion is unmet by §6 as written even after R2 internal fixes.
- **High (FR-1/FR-4):** `RepairConfig.repairable_categories` must include `content_contract` or `route_failures` silently drops the new routing rows.
- **Medium (Ops):** `pre_checkpoint_repair` is documented as controlling pre-merge repair but is unwired — rollout knob is false confidence.
- **Endorsement:** R2-F1 (registry in rollback envelope) and R2-F2 (syntax in re-validation) remain correct and should be triaged/applied with R3 additions.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Risks | critical | Extend FR-1 acceptance to require the **call site** (`integration_engine.py:2313-2317`) invoke name-repair when `pre_validate` **passes**. FR-1 currently names only internal behavior inside `_attempt_pre_merge_repair`; the outer `if pre_result.status == FAILED` guard makes the entire method unreachable for invented-but-valid names. Acceptance must assert invocation (spy/mock), not merely that diagnostics would be produced if the method ran. | Verified 2313-2317: PASSED pre_validate → no call to `_attempt_pre_merge_repair`. This is the headline run-011 failure class (PI-001 passes syntax+lint). Plan mirror: R3-S1. | FR-1 *Acceptance* paragraph (after "before the merge is finalized") | Test: PI-001 reproduction with passing syntax+lint — assert pre-merge name-repair hook ran and emitted `MisnamedFieldDiagnostic` before merge. |
| R3-F2 | Interfaces | high | Add to FR-4 or FR-1: **`content_contract` MUST be in `RepairConfig.repairable_categories`** for name-repair to activate (default + prime-contractor config). `route_failures` (`repair/routing.py:290`) filters categories against this set independently of the integration_engine `repairable` check at 851-855. | Without config change, merged content diagnostics reach `run_file_repair` but route to zero steps — silent no-op indistinguishable from "no violations." | FR-4 *Acceptance* or new NFR bullet under §4 | Test: default config routes `MisnamedFieldDiagnostic` to `prisma_field_rename`; config with `content_contract` excluded skips repair with explicit log/metric. |
| R3-F3 | Ops | medium | Wire or retract **`pre_checkpoint_repair`**: FR-1 should state whether this flag gates the content scan for staged rollout. Today the integration_engine docstring (803) claims it controls the path but the flag is never read (`repair/config.py:68`, default `False`). | Dead config surface adds operator confusion and accidental complexity in the lead-contractor integration path. | FR-1 mechanism paragraph + §4 NFR-2 (bounded rollout) | Config integration test: flag off → content gate skipped; flag on → runs when TS+Prisma preconditions met. |

**Endorsements** (prior untriaged R2 items):

- R2-F1: Rollback envelope must include registry side effects, not bytes alone.
- R2-F2: Re-validation must include `check_syntax`, not content scans only.

**Disagreements:** none.

#### Review Round R4 — claude-opus-4-8-1m — 2026-06-01 22:00 UTC

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 22:00:00 UTC
- **Scope**: Fresh R4 pass on the Inc 5 delta and FR-1/FR-7, looking at the exit conditions and rollback logic of the pre-merge seam.

**Executive summary:**

- **Critical (Abstain = False PASS):** If the repair step abstains (NFR-3), the file is unmodified. If the method returns without changing the `PASSED` status of the outer pre-merge checkpoint, the feature integrates, bypassing the LLM-retry loop. FR-1 must explicitly require that abstains result in a FAILED checkpoint.
- **Critical (Rollback destroys partial repairs):** FR-7 states "no new content_contract violation was introduced". If this is implemented as "zero content violations exist", a file with one repaired typo and one abstained structural invention will be rolled back. Re-validation must accept a strict subset of original violations.
- **Endorsement:** R3-F1 (call site) and R3-F2 (repairable_categories) are mandatory.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Risks | critical | Add to FR-1: If a content violation is detected but the repair step **abstains**, the integration path MUST report a FAILED checkpoint to the orchestrator. Abstaining must not result in a silent PASS that merges the invented name. | The goal is to leave structural/abstained inventions "for the existing LLM-retry path." The LLM retry loop only fires if the pre-merge checkpoint fails. | FR-1 (Detection) | Test: A structural invention passes syntax/lint, is detected, abstained, and forces the pre-merge checkpoint to FAILED. |
| R4-F2 | Validation | critical | Clarify FR-7 re-validation: "no new `content_contract` violation" means the post-repair diagnostics must be a **strict subset** of the pre-repair diagnostics. A file containing an *abstained* violation will still flag on re-scan; this must not trigger a rollback of other successful repairs in that file. | A naive zero-violation check on re-scan will roll back partial success, violating the non-destructive intent. | FR-7 (Re-validation) | Test: A file with `aiRefId` (typo) and `outcomeId` (FK) is partially repaired, retains `outcomeId`, and passes re-validation without rollback. |

**Endorsements** (prior untriaged R3 items):

- R3-F1: Outer call-site gate is the true blocker.
- R3-F2: `content_contract` category config requirement.

#### Review Round R5 — gpt-5.5 — 2026-06-01 21:35 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-01 21:35:00 UTC
- **Scope**: Fresh R5 pass on the Inc 5 requirements delta only. R4's abstain-failure and strict-subset findings are endorsed; this pass adds the missing identity, boundedness, and reporting requirements needed to implement them without ambiguity.

**Executive summary:**

- **High (FR-7):** R4-F2's "strict subset" requirement needs a stable diagnostic identity/multiset. Otherwise duplicate violations in the same file or shifted line hints make the rollback gate ambiguous.
- **High (NFR-2):** The accepted re-validation design contradicts the current "one scan per feature" boundedness text. Requirements should bound the real number of scans after re-validation, not preserve an obsolete limit.
- **Medium (FR-9 / FR-1):** The content path needs final gate and repair-summary observability, especially for PASSED-path repairs and abstain failures.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Data | high | Add a requirement for stable per-occurrence content diagnostic identity used by FR-7 re-validation. The identity must support multiset comparison for repeated violations in the same file and remain stable enough across line shifts after a rewrite. | R4-F2 says post-repair diagnostics must be a strict subset, but equality is undefined. Comparing only `{model, field}` collapses repeated `aiRefId` occurrences; comparing raw line text/range can make an unchanged abstain look new after formatting. | FR-4 diagnostic definitions + FR-7 re-validation paragraph | Tests: duplicate invented fields in one file preserve multiset counts; unchanged abstain after a nearby rewrite is recognized as the same diagnostic; genuinely new diagnostic triggers rollback. |
| R5-F2 | Validation | high | Revise NFR-2 from "one scan per feature" to an explicit scan budget: one initial content scan per eligible feature, one post-repair content re-scan over affected files, one syntax re-check over affected files, and no internal retry loop. | R2-F2 and R4-F2 necessarily add re-validation scans. Keeping the old bound makes the requirements internally inconsistent and encourages implementers to skip validation to satisfy an obsolete cost claim. | §4 NFR-2 Bounded | Instrument tests/spies assert the exact scan counts for no-op, successful repair, abstain, and rollback paths. |
| R5-F3 | Ops | medium | Require final content-gate reporting: FR-1/FR-9 should state that successful repairs, abstains, and rollbacks on the PASSED pre-validate path produce accurate final gate status and `repair_summaries` metadata (`attempted`, `any_modified`, `abstained`, `rolled_back`). | The live call site emits the pre-merge GateResult before repair and only appends metadata inside the failed-prevalidate branch. Without this requirement, user-visible telemetry can claim PASS while content repair later changes or rejects the file. | FR-1 acceptance + FR-9 observability | Test: PASSED-path content repair emits final PASSED gate with accurate summary; abstain emits FAILED gate and summary with `abstained=True`; rollback emits `rolled_back=True`. |

**Endorsements** (prior untriaged R4 items):

- R4-F1: Abstains must force a FAILED checkpoint so the retry path remains honest.
- R4-F2: Strict-subset re-validation is correct, but needs R5-F1 identity semantics.
