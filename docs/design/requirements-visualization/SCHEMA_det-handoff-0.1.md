# det-handoff v0.1 — the field specification

**Date:** 2026-08-17 · **Type:** format grammar (a det-doc-kit member) · **Status:** proposed
**Governed by:** `CHARTER_det-doc-kit-family.md` · **Mirrors:** `SCHEMA_det-plan-0.1.md` (det-handoff **is** a projector, so it mirrors the full projector shape, not just the essentials)
**Formalizes:** the latent HANDOFF format already on disk (~12 `HANDOFF_*.md` instances in `requirements-visualization/`).
**Projector target:** this is the format the **real second projector** (`plan_codegen`'s sibling) targets — the honest `/reflective-adoption` gate for `STANDARD_det-doc-kit-projector-pattern.md`.

> A **det-handoff is a `$0` projection of a REQ + the delivery ledger** — it hands a spec from one session to the
> next as a build-ready brief. Its mechanical spine (spec ref · build order · exit criteria · prerequisite/reuse
> audit · pointers) is **derived**, never authored; its **Gotchas + session framing are human-residue** (§8) — the
> charter's human-gated tail. The generator (the projector) is **cited, not defined here** (charter §2).

## 0. Provenance — the format already exists; this names it

Measured across ≥2 real instances (charter §3): `HANDOFF_build-REQ-29-projector-and-pilot.md`,
`HANDOFF_take-REQ-16-and-17-through-the-loop.md`, `HANDOFF_take-REQ-10-through-the-loop.md`, and ~9 more. Every one
carries the same spine — *For · Base · Spec · Prerequisite status · What you're building · Build order · Hard exit
criteria · Gotchas · What to hand back · Pointers*. This versions that latent format, exactly as det-plan/0.1 did.

## 0.1 The dual source (a note the projector standard's §0.2 gains from this member)

Unlike det-plan (one source = the REQ), a handoff projects from **two authored inputs**:
- **the REQ** (`pairsWith`) — the spec: FRs, `Verify:`, `Touches`, objectives.
- **the ledger** — the delivery state (`SESSION_LEDGER_specs-and-open-tasks.md` + the repo): the `Base` sha, what's
  already built (the prerequisite/reuse audit), the follow-on chain.
Both are authored/accreted (the REQ by a human, the ledger by the delivery process), so the projection stays `$0`.

## 1. Document header **[core]** (mirrors det-plan-0.1 §1)

| Field | Type | Req'd | Meaning | Derivation |
|-------|------|-------|---------|------------|
| `version` | semver | yes | doc lineage, not a label | authored |
| `formatVersion` | const `det-handoff/0.1` | yes | which kit schema this obeys | this doc |
| `pairsWith` | path | yes | the **REQ** being handed off — **MUST resolve LIVE** (§6) | the source REQ |
| `base` | `main @ <sha>` | yes | the git base the work starts from — **MUST resolve LIVE** (§6) | the ledger/repo state |
| `companionKind` | enum `HANDOFF` | yes | emitted **only** for a REQ actually being handed off (§8 solo-vs-gap) | §8 |
| `maturity` | enum `0.1 · 0.2 · 0.3[.n] · 0.4-post-CRP · 0.5 · v1.x` | yes | a projected handoff starts at `0.1` (§7 anti-inflation) | §7 |
| **DIDL** `name`/`handle`/`ref` | strings | yes | semantic name + `{kind}/{slug}-{8hex}` + `cc:intent:…` | `naming.name_forms` (`kind="handoff"`) |

## 2. The mechanical spine **[core] — the projected half** (mirrors det-plan-0.1 §2)

`spine = { spec, buildOrder[], exitCriteria[], prerequisiteStatus[], pointers[], handBack[] }` — every field derives
from the REQ + ledger; **none is authored**.

| Spine field | Derivation from REQ + ledger |
|-------------|------------------------------|
| `spec` | the paired REQ ref + its `Format:`/`Governs:` (from the REQ header) |
| `buildOrder[]` | **the REQ's FRs in sequence** (id + `Name:`) — the ordered work list |
| `exitCriteria[]` | **the REQ's FR `Verify:` clauses**, rolled up (the requirement→test seed — identical to det-plan's gate/§5) |
| `prerequisiteStatus[]` | **the reuse/phantom audit** — each REQ reuse ref (`Touches`/`Pairs with`/"Reuse") resolved on disk `LIVE`/`PHANTOM` (det-plan §4 lifted to the handoff altitude: "build-ready" iff every prerequisite resolves) |
| `pointers[]` | the REQ's `Touches`/`Pairs with` reuse refs (where to look) |
| `handBack[]` | the REQ's Objectives / deliverables (what the receiving session returns) |

## 3. Liveness **[core]** (mirrors det-plan-0.1 §6)

Both `pairsWith` (the REQ) **and** `base` (the git sha) MUST resolve **LIVE** — a handoff that pairs a `PHANTOM`
REQ or names a `Base` sha absent from history is a survivorship lie (you handed off something that isn't there).
Same `LIVE / PHANTOM / LEGACY / ABSENT` classes; **count LIVE only**. The `prerequisiteStatus[]` audit (§2) is
this invariant applied per reuse ref: a "build-ready" claim over a `PHANTOM` prerequisite is the dishonest cell.

## 4. Maturity — the anti-inflation ladder (mirrors det-plan-0.1 §7)

A projected handoff is `maturity: 0.1` (mechanically derived, un-hardened). It climbs only by earning evidence
(a handoff that survived a CRP round, etc.). A projected handoff MUST NOT declare post-CRP maturity unearned.

## 5. Honesty rules **[core]**

- **Solo-vs-gap:** a handoff is projected **only** for a REQ that is *being handed off* (owed to a next session);
  a REQ nobody is handing off gets none — do not manufacture a brief for ceremony (charter §6.4).
- **Never-inferred:** the spine derives from the REQ + ledger; the projector invents no build step, no exit
  criterion, and **no Gotcha** the sources did not carry. In particular the **Gotchas, the `From`/`For` session
  identities, and the strategic "why now / do-these-together" framing are HUMAN-RESIDUE** — authored by the handing-
  off human, **not** projected (they are session-learned, not derivable from REQ+ledger). This is the charter's
  human-gated tail; the projector emits a placeholder, never invented content.
- **Anti-inflation:** §4 — a projected handoff starts at `0.1`.

## 6. The projector — CITE, don't define (Mottainai; charter §2)

The `$0` REQ+ledger→HANDOFF projector is **not specified here** (the kit owns the format). It reuses:
`det_req.parse_fr_lines` (the FRs → `buildOrder`/`exitCriteria`), the on-disk reuse resolver (→ `prerequisiteStatus`,
det-plan's §4 audit), the repo/ledger state (→ `base`), and `naming.name_forms` (DIDL). It is registered SDK-side
under `startd8.contractors.deterministic_providers`, exactly like `plan_codegen` — **this is the second projector**,
and building it against `STANDARD_det-doc-kit-projector-pattern.md` is the real `/reflective-adoption` gate.

## 7. Conformance (the `extract.py`/lint gate — what a validator checks)

A det-handoff/0.1 doc is conformant iff: `formatVersion == det-handoff/0.1`; `companionKind == HANDOFF`; `pairsWith`
**and** `base` resolve **LIVE** (§3); every `buildOrder[]` entry references an FR that exists in the paired REQ;
every `exitCriteria[]` entry traces to that FR's `Verify:` (no invented criterion); `prerequisiteStatus[]` marks each
reuse ref `LIVE`/`PHANTOM` honestly (a `PHANTOM` prerequisite ⇒ **not** build-ready, surfaced not hidden); `maturity`
is not inflated (§4); and the human-residue sections (Gotchas / framing) are **not** machine-asserted as derived. A
`.bad` fixture (phantom `pairsWith`/`base` · a `buildOrder` FR absent from the REQ · an invented exit criterion · a
`PHANTOM` prerequisite claimed build-ready · inflated maturity) must fail the gate `exit 1`. Findings emit as **SARIF
2.1.0** via the ONE `coverage_map/findings_sarif` (imported, not vendored — charter §5/§6).

*v0.1 — formalizes the latent HANDOFF format (~12 instances) into a versioned det-doc-kit member, mirroring
det-plan-0.1's full projector shape (it IS a projector) — spec/buildOrder/exitCriteria from the REQ, prerequisite
audit + base from the ledger, Gotchas/framing as human-residue. **The projector is the next artifact (cited, not
defined here) — and it is the real second-projector `/reflective-adoption` test of the projector standard.**
Carries the dual-source note (§0.1) back to the standard's §0.2.*
