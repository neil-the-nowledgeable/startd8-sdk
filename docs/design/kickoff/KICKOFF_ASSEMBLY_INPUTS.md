# Kickoff — Data-Model & Deterministic-Assembly Inputs (Group F)

**Version:** 0.2 (post-CRP — 7 suggestions applied, see Appendix A)
**Date:** 2026-06-05
**Status:** Draft
**Parent:** [`../KICKOFF_REQUIREMENTS.md`](../KICKOFF_REQUIREMENTS.md) (master; cross-class
machinery FR-X1–X5)
**Related:** `docs/design-princples/DATA_MODEL_AND_RETROSPECTIVE.md` (the human bookends),
`docs/design/python-contract-codegen/` (kernel + view-generator specs),
`strtd8/docs/v2/ASSEMBLY_INPUTS.md` (reference per-project inventory instance),
[`ASSEMBLY_INPUTS_TEMPLATE.md`](ASSEMBLY_INPUTS_TEMPLATE.md) (the project-agnostic template),
[`../wireframe/WIREFRAME_REQUIREMENTS.md`](../wireframe/WIREFRAME_REQUIREMENTS.md)
(`startd8 wireframe` — the machine-readable consumer of this inventory: pre-generation
planned-vs-not-yet-defined summary of what the cascade will build)

---

## 1. Scope

The hand-authored inputs the **$0 deterministic cascade** (`startd8 generate scaffold` /
`generate backend` / `generate views`) consumes to assemble the application skeleton — buckets
1–2 of the bucket separation. These are the highest-leverage user inputs in the entire build: the
`.prisma` contract alone drives ~89% of the app deterministically.

**Boundary (load-bearing):** the cascade is a **standalone pre-pipeline CLI** — zero references
in cap-dev-pipe (verified by sweep). The staged pipeline never invokes it (master Non-Goals);
these requirements make the cascade's inputs *visible* to the pipeline (provenance, status,
flags), nothing more.

---

## 2. Input Inventory (detail)

### 2.1 `prisma/schema.prisma` — the contract (required)

- **Drives:** `generate backend` + `generate views`; single source of truth for models, tables,
  CRUD, HTMX UI, AI schemas, completeness (`backend_codegen/cli_generate.py:229`).
- **The front human bookend:** designing this contract is where human leverage concentrates as
  implementation automates (`DATA_MODEL_AND_RETROSPECTIVE.md`). It is the one input the pipeline
  must never author (FR-F3).
- **Provisioning status semantics (FR-F2):** `authored` = a designed contract (real entities,
  fields, relations); `placeholder` = scaffolded stub (no models, TODO markers, empty field sets);
  `absent` = file missing. Reference scale: the strtd8 contract is 15 entities.

### 2.2 `app.yaml` (repo root) — project scaffold manifest

- **Drives:** `generate scaffold` (REQ-SCAF) — project name, db path, WAL/busy_timeout,
  migrations, logging, container, env (`.env.example` emission).
- **Path convention:** lives at the **repo root**, not under `prisma/` (it scaffolds the project
  that *contains* the contract).

### 2.3 `prisma/human_inputs.yaml` — owned-field policy

- **Drives:** `generate backend --human-inputs` (`assembler.py:93`) — fields AI must not write
  (e.g. `Metric.value`, app FR-6). Today this drives **edge-schema projection only**
  (`ai_layer.py:297–302`: marked fields drop from the LLM tool-input schema; server-managed
  columns are hardwired-omitted via `_PROVENANCE_OMIT`).
- **The FR-F4 gap:** the policy does not reach the bucket-3 integration passes — LLM-generated
  glue could still write a protected field. See §3.

### 2.4 `prisma/ai_passes.yaml` — AI pass manifest

- **Drives:** `generate backend --ai-passes` (`assembler.py:92`) — pass name, input/output
  entities, route, prompt path (e.g. strtd8: `extract` + 4 enrichment passes). The owned harness
  embeds only the prompt *path*; prompt prose itself is a content input (Group G temporal model
  analogue).

### 2.5 `prisma/completeness.yaml` — completeness signals

- **Drives:** `generate backend --completeness` (`assembler.py:78`, `derived.py:163–213`) —
  domain-weighted thresholds (per-entity `min_rows` + `weight` + `exclude` set). Absent ⇒ v1
  presence rule (`derived.py:149–160`). Mode is selected at generate time by manifest presence.

### 2.6 `prisma/views.yaml` — composite-view manifest

- **Drives:** `generate views` (REQ-VIEW) — composite views (value-map, jobs
  dashboard/workspace/export; detail-compose + export-package archetypes).

### 2.7 `prisma/pages.yaml` — the seventh cascade manifest (Group-G-owned)

- **Drives:** `generate backend --pages` (`assembler.py:84`) — consumed by the cascade, so it is
  **counted in Group F's seven-manifest inventory** (FR-F5); its content *semantics*
  (placeholder/authored marking, scoring) are owned by Group G (Content slice §2.1).

### 2.8 Drift/hash machinery (existing — reuse, don't duplicate)

All consumed manifests are **hash-stamped into the owned files' drift headers**, giving `--check`
in_sync/drift semantics. FR-F1 reuses these hashes as the provenance fingerprint — no second
hashing scheme. **Per-generator hash keys (verified, CRP R1 — resolves former OQ-2):**

| Generator | Header key(s) | Anchor |
|-----------|---------------|--------|
| `generate backend` | three-hash header (schema + pages + ai-layer) | `backend_codegen` drift headers |
| `generate scaffold` | `# manifest-sha256:` (hashes `app.yaml`) | `scaffold_codegen/drift.py:18`, `renderers.py:37–40` |
| `generate views` | `# schema-sha256:` + `# views-sha256:` | `view_codegen/renderers.py:33–34, 296–297` |

Note: views in-sync checking is byte-compare re-render (`view_codegen/drift.py`), not
hash-compare — the hash is still present and reusable for provenance.

---

## 3. Requirements (Group F detail)

- **FR-F1 — Cascade-input provenance record.** When a project uses the deterministic cascade, the
  run provenance the staged pipeline consumes MUST record, per input in §2: path, content hash
  (reuse drift-header hashes **per the §2.8 key mapping** — the key name differs per generator),
  and provisioning status (`authored | placeholder | absent`). The record SHOULD carry **hash
  lineage** (current + prior hashes as a list, appended per increment) rather than current-only —
  the RETROSPECTIVE bookend (FR-F3) needs to diff contract evolution across increments; an
  implementation choosing current-only MUST name the alternative lineage source the bookend reads.
  Record home: **operator-coordinated** (master OQ-2 closed 2026-06-05 — no durable-store
  machinery is built proactively; the operator ensures records are delivered when needed).
  Bucket-3 integration passes then generate against a *declared* app, not an assumed one.
- **FR-F2 — POLISH flags data-model status.** Stage 1 POLISH reports the contract's provisioning
  status for cascade-based projects per the §2.1 semantics. Report by default (graceful
  degradation); VALIDATE MAY gate at `critical/high` per the FR-X3 matrix (master OQ-4).
  **Status assignment rule (normative):** an explicit status declaration in the FR-X5 inventory
  **wins**; heuristics (entity count, TODO markers, empty field sets) only produce a
  `review-suggested` flag — they never override a declaration. A 2-entity contract declared
  `authored` reports `authored` (with the heuristic note); the same contract undeclared reports
  per heuristics.
- **FR-F3 — Bookend bracketing.** The collection flow directs the user to the bookends rather
  than auto-generating data-model content: POLISH's flag message points to the DATA MODEL bookend
  before the first cascade run; RETROSPECTIVE findings feed contract updates for the next
  increment. The pipeline collects and records the contract; **it never authors it.**
  **Enforcement (not just principle):** no pipeline stage or SDK generation process may write to
  the contract path (`prisma/schema.prisma`); any modification of the contract during a run MUST
  be detected and flagged (VALIDATE-stage check against the FR-F1 recorded hash). Documentation
  alone does not satisfy this FR.
- **FR-F4 — `human_inputs.yaml` reaches integration.** The collected owned-field policy MUST be
  forwarded into bucket-3 integration passes (via the Group H convention channel) so LLM-generated
  glue also respects field authorship — closing the gap where the deterministic layer protects a
  field that the integration layer then writes. Checkable: protected fields absent from
  integration-pass write paths, not just edge schemas. **Failure semantics (explicit dependency
  on FR-H2 reach):** on any generation path the Group H convention channel has not reached
  (micro_prime, test-gen today), FR-F4 is unsatisfiable — the run MUST flag `FR-F4-unmet` for
  that pass (or re-route per FR-H2's precondition), never silently emit unprotected glue. Same
  silent-bypass shape as RUN-028; the flag is the floor.
- **FR-F5 — Inventory completeness.** The per-project inventory (FR-X5, instantiated from
  [`ASSEMBLY_INPUTS_TEMPLATE.md`](ASSEMBLY_INPUTS_TEMPLATE.md)) MUST enumerate all **seven**
  assembly manifests by name — `schema.prisma`, `app.yaml`, `human_inputs.yaml`, `ai_passes.yaml`,
  `pages.yaml` (dual role, §2.7), `completeness.yaml`, `views.yaml` — plus the path convention
  (contract-derived manifests under `prisma/`; `app.yaml` at root). The FR-X1 pre-flight report is
  generated against this inventory. **Count-proof acceptance:** the FR-X5 template rows, the §2
  section inventory, and the set of manifests accepted by the `generate backend/scaffold/views`
  CLI flags form a **1:1:1 mechanical match** (extract the accepted-manifest set from the CLI arg
  surface; assert zero delta) — so a future eighth manifest breaks the check, not silently the
  count.

---

## 4. Acceptance (Group F)

- FR-F1 provenance block present for a strtd8 run, hashes matching each generator's drift-header
  key byte-for-byte (per the §2.8 key mapping: backend three-hash / `manifest-sha256` /
  `views-sha256`); a second run after a contract edit shows the prior hash in the lineage.
- A scaffold-stub `schema.prisma` shows `placeholder` in the FR-X1 report; the strtd8 15-entity
  contract shows `authored`.
- A field marked in `human_inputs.yaml` is verifiably absent from integration-pass write paths
  (FR-F4).
- The strtd8 inventory (`docs/v2/ASSEMBLY_INPUTS.md`) round-trips through the template structure
  with zero information loss (FR-F5).

---

## 5. Open Questions (Group F)

1. **Stub-detection heuristic tuning (narrowed by CRP R1).** The declaration-wins rule is now
   normative in FR-F2; remaining question is only the heuristic set that produces the
   `review-suggested` flag (entity-count threshold value, TODO-marker patterns, empty-field-set
   sensitivity).
2. ~~**`generate scaffold`/`generate views` hash parity.**~~ **RESOLVED (CRP R1, verified in
   source):** parity holds — see the §2.8 key-mapping table (`scaffold_codegen/drift.py:18`,
   `view_codegen/renderers.py:33–34`).
3. ~~**Multi-increment provenance.**~~ **RESOLVED (CRP R2):** FR-F1 SHOULD record hash lineage
   (current + priors); current-only implementations must name the bookend's alternative lineage
   source. Folded into FR-F1.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F-asm-1 | Resolve OQ-2 with verified hash facts + per-generator key mapping | R1 (opus) | §2.8 key-mapping table added; FR-F1 references it; OQ-2 marked resolved; §4 bullet updated | 2026-06-05 |
| R1-F-asm-2 | FR-F4 failure semantics on partial FR-H2 reach | R1 (opus); endorsed R2 | FR-F4: `FR-F4-unmet` flag or re-route; never silent unprotected glue | 2026-06-05 |
| R1-F-asm-3 | Enumerate the seven manifests; pages.yaml dual-role row | R1 (opus) | New §2.7 (pages.yaml, Group-G-owned); FR-F5 names all seven; master §1/§5/§6 aligned | 2026-06-05 |
| R1-F-asm-4 | Promote declaration-wins into FR-F2 normative text | R1 (opus); endorsed R2 | FR-F2 status-assignment rule added; OQ-1 narrowed to heuristic tuning | 2026-06-05 |
| R2-F-asm-1 | Resolve OQ-3: hash lineage SHOULD | R2 (sonnet) | FR-F1 lineage requirement + current-only escape hatch; OQ-3 marked resolved; §4 lineage acceptance | 2026-06-05 |
| R2-F-asm-2 | Count-proof 1:1:1 mechanical acceptance for FR-F5 | R2 (sonnet) | FR-F5 acceptance: CLI flags ↔ §2 ↔ template rows, zero delta | 2026-06-05 |
| R2-F-asm-3 | FR-F3 enforcement gate (no pipeline writes to the contract) | R2 (sonnet, adversarial) | FR-F3: VALIDATE-stage hash check vs FR-F1 record; documentation alone insufficient | 2026-06-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-05

- **Reviewer**: claude-opus-4-8-1m (Claude Opus 4.8, 1M context)
- **Date**: 2026-06-05 (UTC)
- **Scope**: Group F slice review as part of the kickoff doc-set CRP pass; OQ-2 anchors spot-verified in `src/startd8/scaffold_codegen/` and `view_codegen/`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F-asm-1 | Data | medium | Resolve OQ-2 with verified facts: scaffold-owned files carry `# manifest-sha256:` hashing `app.yaml` (`scaffold_codegen/drift.py:18`, `renderers.py:37–40`); view-owned files carry `# schema-sha256:` + `# views-sha256:` (`view_codegen/renderers.py:33–34`). Hash parity **holds** — convert OQ-2 into a §2.7 note, and add to FR-F1 a per-generator hash-**key mapping** (backend three-hash header vs `manifest-sha256` vs `views-sha256`) since "reuse drift-header hashes" is not one uniform key | The OQ is answerable today from source; without the key mapping an FR-F1 implementer must rediscover that each generator names its hash differently (views in-sync checking is also byte-compare re-render, not hash-compare — the hash is present but used differently) | §2.7 + FR-F1 | FR-F1 record for a strtd8 run contains hashes for all manifests matching each generator's header key byte-for-byte (extends existing §4 bullet 1) |
| R1-F-asm-2 | Risks | medium | State FR-F4's dependency explicitly: forwarding rides "the Group H convention channel" (FR-H2), so FR-F4 is unsatisfiable on any generation path FR-H2 hasn't reached (micro_prime, test-gen today). Add failure semantics: if the channel is unavailable for a bucket-3 pass, the run flags FR-F4-unmet (or re-routes per FR-H2) rather than silently emitting unprotected glue | FR-F4 says "MUST be forwarded … via the Group H convention channel" without saying what happens while the channel's reach is partial — the same silent-bypass shape as RUN-028 | §3 FR-F4 | A bucket-3 pass on a tier without the convention channel produces an explicit FR-F4 flag in the run report, never an unflagged protected-field write path |
| R1-F-asm-3 | Data | medium | Enumerate FR-F5's "all seven assembly manifests" by name. Slice §2 details six (`schema.prisma`, `app.yaml`, `human_inputs.yaml`, `ai_passes.yaml`, `completeness.yaml`, `views.yaml`); if `pages.yaml` is the seventh, add a §2 row cross-referencing Group G ownership; otherwise correct the count in FR-F5 and the master | An FR-F5 acceptance test ("enumerate all seven") cannot be written when the slice that owns the requirement lists six; mirrors master-side count drift (master §1 vs §6) | §2 (new row or note) + §3 FR-F5 | The FR-F5 named list, slice §2 sections, and the FR-X5 template rows are a mechanical 1:1 match |
| R1-F-asm-4 | Validation | medium | Promote OQ-1's recommendation into FR-F2 normative text: an explicit status declaration in the FR-X5 inventory **wins**; heuristics (entity count, TODO markers, empty field sets) only produce a `review-suggested` flag, never override a declaration | FR-F2's `authored|placeholder` boundary ("small-but-designed" vs stub) is otherwise untestable — the focus-file ask 3 gap; the OQ already contains the right answer, it just isn't binding | §3 FR-F2 (+ shrink OQ-1 to the heuristic-tuning remainder) | Acceptance: a 2-entity contract declared `authored` in the inventory reports `authored` with a heuristic-flag note; the same contract undeclared reports per heuristics |

**Endorsements / Disagreements:** none — first round for this file.

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-05

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-05 00:00:00 UTC
- **Scope**: Group F slice review, second pass. Focus on FR-F4 failure semantics, multi-increment provenance gap (OQ-3), and adversarial pass on acceptance criteria.

##### Executive summary

- FR-F4's failure path (convention channel unavailable) is under-specified — R1-F-asm-2 is correct and high priority.
- OQ-3 (multi-increment provenance) is unresolved and has a concrete implementation risk: if FR-F1 records only the current hash, the RETROSPECTIVE bookend (FR-F3) loses the ability to diff contract evolution across increments.
- The §4 acceptance bullet "hashes matching drift headers byte-for-byte" is not verifiable as written — it requires specifying which header key per generator, which R1-F-asm-1 correctly flags.
- FR-F5 "all seven assembly manifests" remains unresolvable until R1-F-asm-3's pages.yaml dual-role question is answered.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F-asm-1 | Risks | medium | Resolve OQ-3 with a concrete policy before implementation: multi-increment provenance for FR-F1 SHOULD record hash lineage (current + prior hashes as a list), not only the current hash — because the RETROSPECTIVE bookend (FR-F3) needs to diff contract evolution across increments. If the design chooses current-only, state the rationale explicitly (simplicity) and add an acceptance condition that the RETROSPECTIVE bookend reads from somewhere else for lineage | OQ-3 is implementation-blocking: an implementer that picks current-only disables the RETROSPECTIVE → contract-update feedback loop; an implementer that picks lineage has different storage requirements. The OQ treats this as optional, but it directly affects FR-F3 | §5 OQ-3 → resolve to FR-F1 note | FR-F1 record across two consecutive runs of a schema-changed contract shows the prior hash in the lineage or the RETROSPECTIVE bookend has a named alternative source for diff |
| R2-F-asm-2 | Validation | medium | Add an acceptance condition to FR-F5 that is mechanically verifiable without counting to seven: "The FR-X5 template rows, the §2 section headers, and the set of files accepted by `generate backend/scaffold/views` CLI flags form a 1:1:1 match" — this survives pages.yaml dual-role ambiguity and future manifest additions | The "all seven" count is brittle: adding an eighth manifest in future silently breaks the acceptance without touching the requirement. A structural match (CLI flags ↔ §2 ↔ template) self-updates | §3 FR-F5 | Automated: extract CLI accepted manifests from `assembler.py` arg list; compare to §2 section count and template rows; assert zero delta |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F-asm-3 | Risks | medium | FR-F3's "pipeline never authors the contract" is stated as a principle but has no enforcement mechanism or testable gate. An implementer could satisfy FR-F3 by documentation alone. Specify what the pipeline must NOT do: e.g. no pipeline stage may write to `prisma/schema.prisma`; this MUST be enforced by a VALIDATE-stage check (not just convention). Without the gate, the RETROSPECTIVE cycle (contract → human edit → regenerate) can be silently short-circuited by an overeager pipeline fix | The principle is load-bearing (it is the "human bookend" claim in §1 and CLAUDE.md) but has no detection or prevention — a motivated implementer could add a "fill in missing entities" step and technically satisfy every other FR | §3 FR-F3 | VALIDATE-stage check: assert `prisma/schema.prisma` was not modified since the last human commit; flag any write to that path by a pipeline process |

**Endorsements:**
- R1-F-asm-2: concur — FR-F4's silent-bypass risk on the Group H convention channel is high; the failure semantics must be explicit before FR-F4 can be accepted.
- R1-F-asm-4: concur — the OQ-1 recommendation is correct and should become normative in FR-F2; the heuristic-flag-with-declaration-win model is the right default.
