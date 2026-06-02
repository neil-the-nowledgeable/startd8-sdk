# Code Knowledge Graph — Phase 2 Requirements: Knowledge Provider (Approach A, converged)

> **Version:** 0.2 (Post-planning — self-reflective update. CRP next via `/new-cnvrg-rvw-prmpt`.)
> **Date:** 2026-06-01
> **Status:** Post-planning draft; paired with [the implementation plan](./CODE_KNOWLEDGE_GRAPH_PHASE2_KNOWLEDGE_PROVIDER_PLAN.md) (v1.0)
> **Supersedes:** `APPROACH_A_PROJECT_KNOWLEDGE_REQUIREMENTS.md` (v0.3) +
> `APPROACH_A_PROJECT_KNOWLEDGE_PLAN.md` (v1.1) — their bespoke regex producer is dropped;
> their CRP-R1 Appendix A/B/C holds the detail behind D1–D4.
> **Owning design:** [CODE_KNOWLEDGE_GRAPH_DESIGN.md](./CODE_KNOWLEDGE_GRAPH_DESIGN.md) §8.1
> ("Knowledge Provider = Approach A, done right").
> **Convergence mandate:** [CROSS_FILE_CONTRACT_RESOLUTION.md](./CROSS_FILE_CONTRACT_RESOLUTION.md)
> §11 ("converge on one resolver/`CodeGraph`, not build it twice").
> **Salvaged deltas:** [APPROACH_A_TO_CKG_HANDOFF.md](./APPROACH_A_TO_CKG_HANDOFF.md) D1–D4 (validated).
> **Forcing incidents:** `RUN_011_M4_FIELD_AND_PATH_INVENTION_POSTMORTEM.md` (Gap A: field invention, Gap B: path invention).

---

## 0a. Planning Insights (Self-Reflective Update, v0.1 → v0.2)

> This section records what the `/reflective-requirements` planning pass revealed when v0.1's
> reuse claims were checked against the **actual Phase-1 code**. The architecture held (no
> requirement was falsified); the corrections sharpen the reuse map and surface one real gap.

| v0.1 assumption | Planning discovery | Impact |
|---|---|---|
| `cross_file_verifier` Finding carries `availability_state` | `Finding` has **no** such field; availability is on `CrossFileResult.availability` (dict `check_id→ran/skipped_unavailable`) | Model `omissions`/availability at the **artifact level**, not per-fact — *strengthens* REQ-523/NFR-3 |
| `resolve_specifier_to_paths` + `_package_name` live in `validators/cross_file_imports.py` | `resolve_specifier_to_paths` is **public in `contractors/upstream_interface.py`**; `cross_file_imports` only has private `_package_name` + scan fns | Re-attributed the module-path source in §2/REQ-522; `_package_name` to promote or reuse via scans |
| §2 lists only `render_prisma_field_sets` + `extract_ts_exports` to subsume | `upstream_interface.py` already has the **whole** renderer+resolver layer (`build_upstream_interfaces`, `render_upstream_interfaces`, `extract_exports`, `extract_import_specifiers`, `resolve_specifier_to_paths`) | **Narrows the build** — provider mostly *assembles/scopes/negates/omits* over existing renderers |
| REQ-521 "field set + types" | `parse_prisma_schema(text)` yields name **+ type + is_optional + is_list + attributes** (string input, not path) | Enriched REQ-521 with optionality/list |
| REQ-524 scopes by "Prisma entities the feature references" | **No mechanism exists** to know which entities a feature references | New **REQ-527 (entity-reference resolution)** — the underspecified gap |
| REQ-520 "view over the resolver" (abstract) | `cross_file_verifier.run_checks(sources, project_root, *, scip=None) -> CrossFileResult` is the exact convergence template | Concretized REQ-520: producer **mirrors that signature** (`scip: Optional[ScipReader]=None`) |
| REQ-524 drops `_feature_mirrors_data_model` (broad) | The heuristic gates **only** the Prisma field-set branch (`prime_contractor.py:4300-4316`); TS/JS Mode-A/B is independent | Refactor is **surgical**; confirms the Gap-A miss (PI-001/004/007 never match `_MIRROR_NAMES`/desc) |

**Resolved open questions:**
- **OQ-1 → resolved (import-graph closure + structural entity scan).** Use `extract_import_specifiers` → `resolve_specifier_to_paths` for the module closure, and token-match feature target-files/description against real `PrismaSchema.models.keys()` for entities (REQ-527). The "all entities" fallback is the degenerate case at strtd8 scale.
- **OQ-4 → resolved for v1 (draft-mode backend).** `DraftModeProducer` over the stdlib/regex extractors; `ScipProducer` drops in via the `scip` param (REQ-520) when an index exists — no seam change.

> **0b. Implementation insights (Phase 6, post-build of REQ-540/520-527).** Wiring the seam
> revealed three realities the v0.2 spec didn't capture; folded back here per the reflective loop:
> 1. **The seam is *pre-generation* — target files aren't on disk yet.** So REQ-527's entity-reference
>    signal is `feature.name` + `description` + target-file **stems**, not generated content; and it
>    must be **plural-tolerant** (PI-001 `enrich-capabilit**ies**` → `Capability`, y→ies), word-bounded
>    so `Capacitor` ≠ `Capability`. (REQ-527 updated.)
> 2. **`_feature_mirrors_data_model` is *repurposed*, not deleted (REQ-524).** Pure structural scoping
>    would regress the RUN-009 whole-model-mirror case (a generic `value-model.ts` names no entity).
>    It now serves as an **inject-all fallback**: structural references win; if none but the feature is
>    a whole-model mirror, inherit the full set; else inject nothing. This strictly dominates the old
>    SKIP-gate and still satisfies REQ-524's acceptance (PI-001 scoped via the structural path).
> 3. **Negatives (REQ-522) are gated on a concrete TS-interface render** so non-TS features aren't
>    noised. Net seam effect on the REQ-540 snapshot: only the TS-importing branches (S1/S3) changed
>    (gained negatives); all edge + Prisma-only branches stayed byte-identical.

---

## 0. Thesis

CKG **Phase 1 shipped the detection half** (the cross-file Verifier: 5 shipped signatures +
external-type + tsconfig, the finding contract, the aggregate any-error rule). Phase 2 ships
the **prevention half**: a deterministic, read-only **Knowledge Provider** that injects the
project's authoritative contract surface (real Prisma field sets, canonical module paths +
explicit negatives, dependencies, tsconfig aliases) into each feature's spec prompt *before*
generation — so the drafter uses real fields/paths instead of inventing them.

It is **not a bespoke scanner.** Per §11 it is a **view over the CKG resolver** built in
Phase 1 — reusing `prisma_parser`, `tsconfig_paths`, `cross_file_imports`, `ScipReader`, and
the `cross_file_verifier` fact model. Detection (Phase 1) verifies; the Knowledge Provider
(Phase 2) prevents; both query one resolver.

**Headline guardrail (D1):** injection is necessary but *not sufficient* — the drafter has
read the schema and still invented fields (CKG design §, "necessary but not sufficient"). So
success is measured at **two levels**, and "the prompt contained the truth" is not "done."

---

## 1. Failure classes this prevents (RUN-011)

| Gap | What the LLM invented | Truth on disk | Phase-1 status | Phase-2 fix |
|-----|----------------------|---------------|----------------|-------------|
| **A — Prisma field names** | `aiRefId`, `label`, `title`, `supportingEvidence` | the model's real fields in `schema.prisma` | *detected* post-gen (`prisma_usage`/symmetry) | **prevented** by REQ-CKG-521 (field-set authority) |
| **B — module-import paths** | `@/lib/prisma` (recurring), `@/lib/db/<model>`, `@/lib/ai/client` | `@/lib/db`, `@/lib/ai/service` | *detected* (`cross_file_imports`) | **prevented** by REQ-CKG-522 (path authority + negatives) |
| dependency / tsconfig | (see Phase 1) | `package.json` / `tsconfig.json` | detected | injected as supporting context |

Root cause (CROSS_FILE §4): **per-file probabilistic generation (locality).** Detection makes
failures honest; only **injection of the truth** prevents them. The two are complementary.

---

## 2. Reuse (do not build twice — §11)

> **Corrected in v0.2** (planning pass) — real file:line + signatures. The convergence template is
> `cross_file_verifier.run_checks`; the provider is its inverse with the **same** input shape.

| CKG Phase 1 artifact (verified) | Role in the Knowledge Provider |
|---|---|
| `validators/cross_file_verifier.py:94` `run_checks(sources, project_root, *, scip=None) -> CrossFileResult` | **convergence template** — provider mirrors this signature (inverse: assert truth pre-gen) |
| `validators/cross_file_verifier.py:48` `Finding{check_id,kind,source_file,locus,severity,scope,message,remediation}` | shared fact vocabulary. **No `availability_state`** on Finding — availability is on `CrossFileResult.availability` (drives REQ-523 artifact-level omissions) |
| `languages/prisma_parser.py:276` `parse_prisma_schema(text) -> PrismaSchema` | Prisma field-set source; `PrismaField(name,type,is_optional,is_list,attributes)` (string input) |
| `validators/tsconfig_paths.py:88` `scan(...)` + `_merged_compiler_options` (follows `extends`) | tsconfig `paths`/`baseUrl` alias resolution (already real-parses) |
| **`contractors/upstream_interface.py`** — `resolve_specifier_to_paths`, `extract_import_specifiers`, `extract_ts_exports`, `extract_exports`, `build_upstream_interfaces`, `render_upstream_interfaces`, `render_prisma_field_sets` | **the renderer + module-resolver layer to wrap** (this is where `resolve_specifier_to_paths` lives, *not* `cross_file_imports`) |
| `validators/cross_file_imports.py:130` `_package_name` (PRIVATE) + `scan_*` | npm package-name mapping — **promote `_package_name` to public** or reuse the `scan_*` helpers |
| `code_observability/scip_reader.py:92` `ScipReader.from_path/from_bytes`, `.external_symbols_by_package()`, `.cross_file_edges()` | resolved external/symbol facts when a SCIP index exists (authoritative tier; gated by `[code-observability]`) |
| `contractors/prime_contractor.py:4223` `_collect_upstream_interfaces(self, feature) -> str` | the **injection seam** to refactor (Mode-A/B + the Prisma branch) |
| `contractors/prime_contractor.py:4320` `_feature_mirrors_data_model(feature) -> bool` | the keyword gate (gates **only** the Prisma branch) to **replace structurally** (REQ-524) and delete |

---

## 3. Functional Requirements (REQ-CKG-5xx)

> 500/510 are carried from the Phase-1 reqs (specified, greenfield). 52x/53x/54x are new.

**REQ-CKG-500 (carried) — Authoritative context API.** A deterministic (no-LLM) producer
emits a project-knowledge artifact (`forward_project_knowledge.json` or equivalent) keyed to
the project root, carrying: Prisma model→field sets, module-path table, `package.json`
snapshot, tsconfig `paths`, per-file export table.

**REQ-CKG-510 (carried) — spec_builder injection.** The relevant subset is injected as a P0
spec-context section via `_collect_upstream_interfaces` → `gen_context` → spec_builder.

**REQ-CKG-520 — View over the CKG resolver (convergence, §11).** The artifact MUST be produced
by the CKG resolver/extractors (§2), behind a `ProjectKnowledgeProducer` protocol so the
backend is swappable (draft-mode regex/stdlib now; SCIP-backed later). **No bespoke parallel
scanner.** *(v0.2)* The protocol **mirrors the Phase-1 verifier signature** for true one-resolver
convergence: `build(sources: Dict[str,str], project_root: str, *, scip: Optional[ScipReader]=None)
-> ProjectKnowledge` — same `sources`/`project_root`/`scip` inputs as
`cross_file_verifier.run_checks`, so detection and prevention consume identical inputs. *Acceptance:*
the producer calls the same `prisma_parser`/`tsconfig_paths`/`upstream_interface` functions Phase 1
uses (assertable by patching them); a future `ScipProducer` drops in via `scip` without changing the seam.

**REQ-CKG-521 — Prisma field-set authority (closes Gap A).** For each entity a feature touches,
inject the **exact** field set + types + an explicit "use only these; do not invent" instruction.
*(v0.2)* `parse_prisma_schema` also yields **optionality (`is_optional`) and list (`is_list`)**
modifiers per field — render these so the drafter distinguishes `value: Float` from `value: Float?`.
*Acceptance:* a RUN-011 PI-001/004/007 reproduction emits `db.<model>` calls using only real fields.

**REQ-CKG-522 — Module-path authority + explicit negatives (closes Gap B; D2).** Inject the
canonical import path per module a feature is likely to use, **and explicit negatives** for the
recurring inventions ("the Prisma client is `@/lib/db`; there is no `@/lib/prisma`, no
`@/lib/db/<model>`; the AI service is `@/lib/ai/service`, not `@/lib/ai/client`"). v1 = a
**seeded** negative list (covers observed recurrences); deriving from canonical-name priors is
later. Negatives are a **first-class rendered output**, not a side note. *(v0.2)* Positive paths
come from `upstream_interface.resolve_specifier_to_paths` + the `tsconfig_paths` alias prefixes
(**not** `cross_file_imports`, which only exposes the private `_package_name` — promote it to
public or reuse the `scan_*` helpers for npm-package mapping). *Acceptance:* the `@/lib/prisma`
invention does not recur in a PI-002/007 reproduction.

**REQ-CKG-523 — State omissions; never render an empty authoritative set (D3).** When a section
is unavailable (no `schema.prisma`/`tsconfig`), the context **states the omission** ("Prisma
schema unavailable — do not assume a field set") and **omits the authority claim**. It MUST NOT
render "use only these fields: (none)", which falsely authorizes the empty set (its own
hallucination trigger). The producer's output model carries an explicit **`omissions`** field.
*(v0.2)* This mirrors the Phase-1 split where availability lives on `CrossFileResult.availability`
(not on each `Finding`): `omissions` is a **top-level** field on `ProjectKnowledge`, not absent keys,
so an unavailable section is *stated*, never silently empty. *Acceptance:* a project without
`schema.prisma` yields an omission statement, not an empty field authority.

**REQ-CKG-524 — Relevance-scoped injection; drop the heuristic gate (D4).** Scope = the
feature's `target_files` import-graph closure **+ the Prisma entities the feature references**
(per REQ-527), determined **structurally** — replacing the `_feature_mirrors_data_model`
name/description heuristic that silently skipped PI-001/004/007 (the likely Gap-A miss). *(v0.2)*
The heuristic gates **only** the Prisma branch (`prime_contractor.py:4300-4316`); the TS/JS Mode-A/B
path is independent, so the refactor is surgical — swap the gate at `:4301`, then delete
`_feature_mirrors_data_model` once REQ-540 parity holds. The import-graph closure reuses
`extract_import_specifiers` → `resolve_specifier_to_paths` (no new resolver). *(Phase-6 update)* The
keyword detector is **repurposed, not deleted**: it no longer SKIP-gates (the bug), but serves as an
**inject-all fallback** for a whole-model mirror that names no specific entity (preserves the RUN-009
`value-model` case). Order: structural references win → else whole-model-mirror fallback injects all →
else inject nothing. *Acceptance:* PI-001 (enrich-capabilities) receives its referenced field set(s)
**via the structural path**, not the heuristic (which returns False for it).

**REQ-CKG-527 — Entity-reference resolution (new in v0.2; fills the REQ-524 gap).** The provider
MUST determine **which Prisma entities a feature references** without the dropped keyword gate and
without a hand-maintained list. v1 mechanism: token-match against the real model names from
`PrismaSchema.models.keys()` — structural, derived from the schema itself. *(Phase-6 update — the seam
is pre-generation)*: the signal is `feature.name` + `description` + target-file **stems** (target file
**content doesn't exist yet** at injection time), matched **plural-tolerantly** (singular + regular
plurals: `enrich-capabilit`**`ies`** → `Capability`) on a word boundary so `Capacitor` ≠ `Capability`.
*Acceptance:* a feature named/described in terms of `Capability` (e.g. `enrich-capabilities`) is scoped
to that entity even though its filename matches no `_MIRROR_NAMES` stem; a feature referencing no
entity (and not a whole-model mirror) is scoped to none (no over-injection).

**REQ-CKG-525 — Bounded token cost.** The injected section is relevance-scoped and size-bounded;
the producer logs artifact size + per-feature injected-token delta. *Acceptance:* per-feature
section ≤ a declared budget (e.g. ~800 tok for a typical feature); budget + actual logged.

**REQ-CKG-526 — Read-only at generation time.** The artifact is read-only during generation;
producer files introduced by an earlier feature surface to dependents via the per-file export
table (parity with today's Mode-A behavior).

**REQ-CKG-530 — Two-level success: injection vs adherence (D1, the headline guardrail).**
- **Injection (deterministic, unit-testable):** the spec context contains the real field sets /
  module paths / negatives. Provable by inspecting the prompt.
- **Adherence (empirical, probabilistic):** the *generated code* uses them — measured only from
  generation output over **N ≥ 5 seeds/feature** against an **adherence-rate threshold (~0.9)**.
  A single passing re-run cannot distinguish a fix from sampling luck. Below threshold →
  **escalate** (draft-time self-check / Approach C contract-first). *Acceptance:* the
  Knowledge Provider is **not** declared "done" on an injection test alone; the adherence
  harness reports a rate per failure class.

**REQ-CKG-540 — Refactor-safety: characterization snapshot of the seam (D4).** Before refactoring
`_collect_upstream_interfaces`, capture a **characterization snapshot** (golden fixtures) of its
current output on the at-risk branches — absent-anchor warning, Mode-A not-yet-generated producer,
no-TS/JS-upstream early return — then assert byte-parity post-refactor. ("Keep Mode-A/B tests
green" is necessary but **not** sufficient — they may not exercise those branches.) This is the
same discipline as the Phase-1 690a regression lock.

---

## 4. Non-Functional Requirements

- **NFR-1 Deterministic** — no LLM in the producer; same project state → same artifact.
- **NFR-2 Fast & bounded** — one per-batch build; bounded read per feature.
- **NFR-3 Degrade loudly, never falsely** — missing schema/config → omit + state (REQ-CKG-523); never inject a wrong/empty truth.
- **NFR-4 Language-aware, TS/Prisma-first** — schema extensible to Go/Java/C# without rework.
- **NFR-5 Convergence-preserving** — the artifact schema is a CKG `CodeGraph` view; encode no SDK-only assumptions that would block the CodeGraph backend (§11).

---

## 5. Non-Requirements (Phase 2)

- **Not** a bespoke regex producer (the dropped Approach-A S1/S2) — reuse the CKG resolver.
- **Not** Approach C contract-first *generation* — that's the **escalation path** when REQ-CKG-530 adherence is below threshold, scoped separately.
- **Not** changing Phase-1 detection (the Verifier stays; the provider complements it).
- **Not** guaranteeing the LLM *consults* the artifact — REQ-CKG-530 measures it; v1 maximizes odds (P0, authoritative, negatives), does not claim 100% adherence.
- **Not** the SCIP/buildable-precise producer backend — documented upgrade path; v1 may use the draft-mode regex/stdlib extractors.

---

## 6. Open Questions

- **OQ-1 — Relevance-scoping algorithm (REQ-CKG-524). RESOLVED (v0.2).** Import-graph closure via
  `extract_import_specifiers`→`resolve_specifier_to_paths` + structural entity scan (REQ-527);
  "all entities" is the degenerate fallback at strtd8 scale.
- **OQ-2 — Adherence threshold empirics (REQ-CKG-530).** Is ~0.9 over N≥5 the right gate? Resolve from the run-011 re-run; if adherence is weak even with injection, escalate to contract-first. *(Open — empirical, settled by the adherence harness.)*
- **OQ-3 — Negative-signal source (REQ-CKG-522).** Seed the recurring inventions vs derive from a canonical-name list. (Lean: seed now, derive later.)
- **OQ-4 — Producer backend. RESOLVED (v0.2).** `DraftModeProducer` (stdlib/regex, partial-tolerant)
  for v1; `ScipProducer` drops in via the `scip` param (REQ-520) when an index exists — no seam change.
- **OQ-5 — Artifact persistence/staleness.** Rebuild per batch (fresh) vs cache with content-hash invalidation. (Lean: rebuild per batch.)

---

## 7. Traceability

| Source | → REQ |
|---|---|
| Design §8.1 Knowledge Provider | REQ-CKG-500/510/520 |
| CROSS_FILE §11 (don't build twice) | REQ-CKG-520, NFR-5 |
| Handoff D1 (injection≠adherence) | REQ-CKG-530 |
| Handoff D2 (explicit negatives) | REQ-CKG-522 |
| Handoff D3 (state omissions) | REQ-CKG-523 |
| Handoff D4 (snapshot the seam + drop heuristic) | REQ-CKG-540, REQ-CKG-524 |
| Planning pass (entity-reference gap in REQ-524) | **REQ-CKG-527** |
| RUN-011 Gap A / Gap B | REQ-CKG-521 / REQ-CKG-522 |

---

## 8. Verification Strategy (headline gates)

1. **Injection (unit):** spec context for a scoped feature contains the real field sets + module table + negatives + omissions (REQ-CKG-520/521/522/523).
2. **Relevance scoping:** PI-001/004/007 reproduction is scoped structurally — import-graph closure + entity-reference resolution against real `models.keys()` — without the name heuristic (REQ-CKG-524/527).
3. **Refactor parity:** the `_collect_upstream_interfaces` characterization snapshot is byte-identical post-refactor (REQ-CKG-540).
4. **Adherence (empirical, the real gate):** re-run the RUN-011 failed features with injection, N≥5 seeds; assert adherence ≥ threshold per Gap-A/Gap-B class (REQ-CKG-530). Baseline without injection preserved (regression guard).

---

*v0.2 — Post-planning self-reflective update. Architecture unchanged (no requirement falsified);
3 reuse claims corrected (§2 + REQ-520/522/523), 1 requirement enriched (REQ-521), 1 added
(REQ-527 entity-reference resolution), 2 open questions resolved (OQ-1, OQ-4). Paired with the
implementation plan v1.0. Next: CRP via `/new-cnvrg-rvw-prmpt` (dual-document).*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state (for the upcoming CRP). Reviewers: scan A/B/C first.

### Appendix A: Applied Suggestions
_None yet._

### Appendix B: Rejected Suggestions (with Rationale)
_None yet._

### Appendix C: Incoming Suggestions (Untriaged, append-only)
_Awaiting first review round._
