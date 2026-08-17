# Next steps — the det-doc-kit family + NLPS document-layer effort

**Date:** 2026-08-17 · **Type:** roadmap / handoff · **Owner of direction:** emeritus session · **Owner of build:** a build session
**The effort in one line:** *formalize the NLPS document layer as a `$0`-derivation cascade — a family of
`det-*-kits` between the two human bookends, findings-grounded via SARIF (map) + feature/AI o11y (territory).*

## Status snapshot

| Piece | Artifact(s) | State |
|-------|-------------|-------|
| **Family charter** | `CHARTER_det-doc-kit-family.md` (7 invariants + the audit-hardened §5 checklist) | ✅ directed |
| **det-req-kit** | dev-os (the origin kit) | ✅ shipped · ⚠️ cleanup flagged (`dev-os/FINDING-det-req-kit-format-dir-accretion.md`) |
| **det-plan-kit — format** | `SCHEMA_det-plan-0.1.md` | ✅ spec |
| **det-plan-kit — projector** | `REQ-29-det-plan-projector.md` (`$0`, reflective-instantiation) | ✅ spec · ⬜ build |
| **det-crp-kit** | assessed → thin (own focus + review-log schemas + `crp_lint.py`) | ◐ assessed · ⬜ spec |
| **Findings IR** | SARIF (charter inv. 6) — the o11y→SARIF bridge already routed | ✅ partly wired |
| **Runtime grounding** | `ANALYSIS_runtime-grounding-*` + charter inv. 7 + `REQ-28` | ✅ spec · ⬜ build |
| **Realization arc** | `REQ-16/17` (built) · `REQ-18/19/20/21/24` (built) · the realization facet CRP | ✅ mostly built |
| **Liveness column** | `REQ-22/23` (built) · `REQ-25` hypothesis cells (spec) · `REQ-28` runtime cell (spec) | ◐ fact cells built |
| **det-handoff/howto/ledger** | family roster candidates | ⭘ deferred (no grounded demand yet) |

## Next steps — dependency-ordered

1. **det-req-kit cleanup (owner Yokoten, dev-os).** Relocate the 8 process docs out of the format dir; consider a
   single shared dev-os SARIF renderer before N kits vendor copies. Flagged in
   `dev-os/FINDING-det-req-kit-format-dir-accretion.md` — the det-req-kit owner's call.
2. **Build det-plan-kit.** Two halves, per charter §5's *essentials-only* checklist:
   - **dev-os kit dir** (`det-plan-kit/`): `SCHEMA.md` (adopt `SCHEMA_det-plan-0.1`) · `plan.schema.json` ·
     `extract.py` (validate + plan-liveness gate, **imports** `findings_sarif`, does NOT vendor) · `templates/` ·
     `examples/` · `tests/` (good + `.bad`). **NO `new.py`, NO finding→plan-stub** (det-plan is a *derived* doc).
   - **SDK projector** (`REQ-29`): `plan_codegen/projector.py` + `provider.py`, `startd8 generate plan`, registered
     under `startd8.contractors.deterministic_providers` (mirrors `backend_codegen`). **Pilot on the 26
     companionless REQs** (FR-7) — the cold-adopter test that folds friction back into `det-plan/0.1`.
3. **det-crp-kit (thin).** Version the focus-file + Appendix-A/B/C review-log schemas out of the agent guide; add
   `crp_lint.py`; **cite** `new-cnvrg-rvw-prmpt` as the `$0` compiler (don't restate it).
4. **Finish the liveness column.** `REQ-25` (hypothesis cells — fact-rungs ship, judgment-rungs park) and `REQ-28`
   (runtime o11y cell) are spec'd and build-ready; they extend the shipped `REQ-22/23` fact cells.
5. **Runtime grounding wiring (`REQ-28`).** Route `parity.py` dead-SLI → SARIF; AI-cost → the REQ-19 seam;
   instrumentation-gen as the propose-only generative fix. All reuse; advisory; human-gated.
6. **Realization facet.** The `regime` slot is reserved on the edge (REQ-16); the realization REQ (fill the slot,
   derive node realization, determinism-% rollup) is the far end — run its CRP round before adoption.
7. **Cross-repo coordination (needs owners' go):** the dev-os kit dirs (det-plan/det-crp) · the ContextCore Node
   mirror (0.4.0) · `NODE-SCHEMA.md §1` refresh (the ADR — accepted).

## The invariants/guards to carry into every build

- **The two human bookends stay prose** — no kit for INTENT/ADR/RESEARCH (front) or RETROSPECTIVE/§0 (back). The
  correct-absence `(req, PROJECTOR)`: a source doc has no `$0` projector.
- **Own a format, never a generator** (Mottainai — cite the projector, don't restate it).
- **The §5 mirror-inertia checklist** — format-essentials only; source-kit-only vs derived-kit; reuse-not-vendor
  SARIF; kit dir = format-only; per-kit choices justified. *(Audit the source before mirroring — always.)*
- **Liveness stratifies by altitude** — FR-gate → REQ-verify → PAIR-companion (plan-liveness) → corpus →
  RUNTIME feature-signal. Count LIVE only.
- **`$0`/never-inferred** — a projector is a pure function of its source; it invents no dependency the source
  didn't declare. **Anti-inflation** — a projected artifact starts at maturity `0.1`.
- **Propose-don't-dispose** at every generative seam (sarif_to_req_stub, instrumentation-gen, the revise auto-tier).

## The build-vs-direction boundary

Everything above the "⬜ build" markers is **directed** (spec'd, grounded, DIDL-named, audit-hardened) and out of
the emeritus lane. The build sessions run the Spec Delivery Loop on: **det-plan-kit (REQ-29) → det-crp-kit →
REQ-25/28 → the realization facet.** The det-req-kit cleanup is the det-req-kit owner's. Each carries its own
handoff-grade constraints in its spec.

**The one-line close:** *the NLPS document layer is now formalized on paper end-to-end — a `$0` cascade from a
human-gated requirement to code, findings-grounded in both map (SARIF) and territory (o11y), with a charter whose
own §5 was audit-hardened against the inertia of mirroring. What remains is building the first kit and letting its
pilot fold friction back — the loop, closed and turning.*
