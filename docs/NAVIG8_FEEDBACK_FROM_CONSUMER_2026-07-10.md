# navig8 → startd8 SDK: consumer feedback + donation candidates

**Date:** 2026-07-10 · **Consumer:** navig8 (Michigan legal-intake framework, SDK instantiation #2)
**Placed untracked for the SDK team to review / commit** (not committed into your in-flight WIP).
Companion in-repo trail: `docs/design/kickoff/CONCIERGE_FRICTION_LOG_NAVIG8.md` (F-11..F-14).

> Surfaced by dogfooding the intended flow — kickoff → `generate backend` → the `$0` cascade → the
> walk/loader glue a real app needs. Structured as: what worked · fixes already landed · donation
> candidates (build on your primitives) · the remaining hand-off · reproduce commands.

---

## What worked well (balanced, deliberately)
- **Contract-first derivation held.** `schema.prisma` v0.1 (8 entities) derived from the existing
  Pydantic models regenerated a working FastAPI+SQLModel+HTMX app with no hand-editing of `app/**`.
- **The owned-file composition seam is excellent.** `app/user_routers.py` let us mount a whole
  deterministic walk UI (product runtime surface) with **zero** edits to generated files, surviving
  every regenerate. This is the single best thing about the generated app for a real consumer.
- **`--boot-smoke` and `--check` are the right gates** — once we found them, they caught real defects.
- **`human_inputs.yaml` owned-field policy is the right idea** — it just needed to reach every surface.

## Fixes already landed (merged — PR #189, `01398ae4`)
Three generator defects, found + fixed + merged this session (structured in F-11/F-12/F-14):
- **P0** scalar `Json?` → bare `Optional[Any]` crashed SQLModel at import.
- **P1** `human_inputs` owned-field policy reached only the AI edge schema, not `*Update`/web `_rules`/forms.
- **F-14** making those artifacts `human_inputs`-dependent required teaching the drift subsystem the input.

(P2 — dropped composite `@@unique` — was already fixed upstream in `ed148eaa`.) Noting these as *context*;
they're done. The candidates below are what's **not** yet addressed.

---

## Donation candidates (each builds on an existing SDK primitive)

### C1 — Generated `Citation` lacks the computed `fullReference` the convention mandates
- **Symptom / where it bit.** `conventions.yaml` states "Citation rendering is jurisdiction-aware via
  `Citation.full_reference` — never hand-format." But the **generated** `Citation` SQLModel exposes no
  such method (only the upstream Pydantic model does). A consumer that renders a citation must therefore
  hand-format — we did, in `app/walk/packet.py:_full_reference` (MCL/IRC/U.S.C.). Two surfaces that both
  hand-format will drift, and it directly contradicts the stated convention.
- **Severity:** Medium (correctness/convention, not a crash).
- **Builds on:** your existing computed-property story on the Pydantic side. **Suggested fix:** emit the
  jurisdiction-aware `full_reference` as a computed property / helper on the generated `Citation` (and its
  Read DTO) so consumers render via one source, never hand-format.

### C2 — No first-class "seed from an external domain artifact" path (the ETL gap)
- **Symptom / where it bit.** The import story (`--imports` → `app/import.py` `from_json`) is the
  **inverse of `export`** — it round-trips the app's *own* JSON (id-linked, contract field names). A real
  app also needs to load **external, domain-shaped** artifacts (a verification-pipeline fold-back, a
  fixture, a synthesized tree) whose shape isn't the export shape (snake_case wire names, children nested
  under domain keys, semantic keys not cuids, transforms like `screens[] → join rows`). There's no SDK
  path for that, so we hand-rolled loaders (`scripts/load_estate_tree.py`, `load_landmine_register.py`).
- **The parallel we hit.** In doing so we **reinvented machinery `from_json` already has**: natural-key
  upsert (your `imports.yaml` `identity`), never-clobber-provenance (FR-IMP-5), scalar coercion, FK order,
  strict/atomic. The persistence half is yours; only the *transform* is genuinely domain-specific.
- **Severity:** Medium (every real consumer hits it; it's why we paralleled you).
- **Reference (donation-quality, in the consumer repo):** `navig8/scripts/contract_loader.py` — a
  **domain-agnostic** harness (zero legal vocabulary in its logic) that seeds an external JSON aggregate
  (root + FK-ordered children) into the generated contract: idempotent by declared natural key,
  owned-fields-as-data with provenance, a cascade helper, and shared verify primitives — with the
  field-mapping + domain assertions left as per-loader code (deliberately *not* a declarative engine).
  Two loaders ride it; a third (trademark) will be a spec, not a copy. This is the shape of the missing
  primitive. **Suggested direction (two adoption steps, both build on existing infra):**
  1. a **`seed`/`from_domain_json` capability** that reuses the `identity`/`provenance` upsert machinery
     but takes a consumer-supplied transform (JSON → row kwargs), so consumers stop re-implementing the
     idempotent, provenance-preserving upsert; and
  2. exposing the `imports.yaml` `identity`+`provenance` upsert so it's reachable for non-export input.
- **Not a lift-in of a whole subsystem** — a general ETL engine would be over-abstraction. The candidate is
  the small seam (transform → your upsert), with `contract_loader.py` as the proven reference.

### C3 — The validation gate should boot, and should assert render-inputs ⊆ drift-inputs (systemic)
- **Symptom / where it bit.** All three landed fixes (C-context above) shipped for **one root reason**:
  the fidelity gate does `py_compile` (syntax) + regex field-structure only — **no real import/boot**, and
  no check that an artifact's drift-inputs track its render-inputs. So a module that can't import (P0), a
  leaked owned field (P1), and an under-declared input dependency (F-14) all passed silently. `--boot-smoke`
  exists but isn't part of the default gate.
- **Severity:** High (it's the meta-defect that let the other three through).
- **Builds on:** `--boot-smoke` (already yours). **Suggested fix:** (a) make a boot check part of the
  default `generate`/CI gate — a green `py_compile` is not a green boot; (b) add a static
  **render-inputs ⊆ drift-inputs** assertion so a new input dependency can't be added to a renderer without
  the drift subsystem learning it (the F-14 lesson, generalized).

---

## The remaining hand-off (what "fully donated" would take)
- **C1:** small — add the computed `fullReference` to the generated `Citation`/Read DTO.
- **C2:** medium — a `seed`/transform seam on top of the existing `identity`/`provenance` upsert; the
  consumer's `contract_loader.py` is the reference, the two loaders are the proof.
- **C3:** small-medium — promote `--boot-smoke` into the default gate + one static invariant check.
- **Forward value the consumer is prototyping (not asking you to build):** loaders migrating to
  *transform → `from_json`* (delegating persistence to C2), and a `--dry-run`/single-transaction load for
  validating synthesized artifacts before they touch a DB. Both would land cleaner once C2 exists.

## Reproduce
```bash
# C1 — generated Citation has no fullReference:
grep -n 'full_reference\|fullReference' <navig8>/app/tables.py    # -> only the field, no computed ref
# the consumer hand-formats because of it:
sed -n '106,122p' <navig8>/app/walk/packet.py
# C2 — the importer is the inverse of export (export shape only):
sed -n '1,12p' src/startd8/backend_codegen/import_codegen.py
# the domain-agnostic reference the SDK could adopt:
python <navig8>/scripts/tests/test_loader_parity.py               # 12 checks, seeds tree + register
# C3 — the gate that let P0/P1/F-14 through is compile+regex, not boot:
grep -rn 'py_compile\|def _verify' src/startd8/backend_codegen/gates.py
```

## Cross-filing (so value survives non-adoption) — DONE
C1–C3 mirrored to both stores per the established donation practice, so the learnings are recall-able
independent of whether/when these candidates are adopted:
- **ContextCore lesson store** (project `startd8-sdk`): `LSN-convention_mandated_computed_properties_`,
  `LSN-sdk_importer_is_the_inverse_of_export_no`, `LSN-a_green_py_compileregex_fidelity_gate_is`
  (file-scoped `recall` verified — e.g. `gates.py` surfaces C3).
- **Curated SDK `Lessons_Learned`**: `sdk/lessons/13-cross-system-pipeline.md` #113–#115 (changelog 8.73.0;
  Leg 13 count 112→115).
