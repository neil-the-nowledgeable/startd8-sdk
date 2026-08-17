# Handoff — Seat requirement authoring, the dev-os Definer side (7 FRs)

**Date:** 2026-08-16 · **From:** startd8-sdk session (built the SDK slice) · **For:** the dev-os Definer / det-req-kit team
**Spec (SSOT, build-ready):** `startd8-sdk/docs/design/requirements-visualization/REQ-seat-requirement-authoring-on-det-req-definer.md` (v0.4.1)
**Plan:** `…/PLAN-seat-requirement-authoring-on-det-req-definer.md`

## Why you're getting this

The seat-req makes **requirement authoring** the differentiator: an operator seats NODE-SCHEMA fields in the
**Visual Requirements Definer**, exports **det-req/0.1**, validates via a **one-command round-trip**, and
renders in navigators that already speak Nodes. The spec spans three repos. **The SDK slice is already built +
landed** (`startd8-sdk` `d0dd91b9`): FR-4's SDK health-twin (`fr_health` now computes from *authored* Lives
only) and FR-6 (the navigator's parse-loss floor). **The Definer + kit FRs below are yours** — they own the
*emit* and *validate* seats, which the SDK only consumes.

## What's yours (grounded — these files exist)

| FR | Deliverable | File(s) |
|----|-------------|---------|
| **FR-1** | Requirement authoring that produces det-req/0.1 is owned by the Definer **write-back** (`detReqWriter`), NOT the persona Requirements Panel. Exported markdown must validate as det-req/0.1 via `det-req-kit/extract.py --report` exit 0 **and match the Wire form (below)**. | `loops/builder/writers/detReqWriter.js` |
| **FR-2** | The Definer inspector authors DOES / Verify / WON'T / optional Lives / Approve? / Was per node without a Studio-only schema; round-trip graph → det-req → re-project is **lossless** against the Wire form. | Definer inspector · NODE-SCHEMA |
| **FR-3** | `roundtrip.sh --no-serve` exports, validates via navigator JSON, and **fails loud** on empty/malformed navigator output (exit 0 on the dogfood fixture; non-zero + named reason on a broken stub). | `loops/builder/roundtrip.sh` |
| **FR-4 (twins)** | `req-health.mjs` + `extract.py --report` must **agree** with the SDK on the class ∈ {`n/a`,`skipped`,`unknown`,`on_track`}. **⚠ The SDK just changed:** its `fr_health` now ignores `Touches:`-mined refs for the gate (see below) — align the two dev-os twins so a done-claim FR with only mined refs stays `unknown` in all three. | `loops/builder/req-health.mjs` · `det-req-kit/extract.py` |
| **FR-5** | Round-trip may attach `--dossier` / `--forward-manifest` as **derived read-only** overlays; overlay parse failure must NOT block det-req export. | `loops/builder/roundtrip.sh` · DELIVERY_EVIDENCE_CONTRACT |
| **FR-8** | HOWTO §6 is the operator recipe (normalize → evidence gate → optional Definer round-trip → render → cruft → Panel Laws/SV) — **cited, not restated**. | `HOWTO-VISUALIZE-A-REQUIREMENT.md` §6 |
| **FR-11** | Ship the dogfood graph (or a checked-in export golden) as the seed + one copy-paste command; a fresh operator reaches a valid det-req in ≤5 documented steps. | dogfood fixture/golden |

## The load-bearing contract — the Wire form (write to THIS or the SDK loses fields)

The SDK parser is strict. `detReqWriter` MUST emit:
- **one FR per physical line** (a hard-wrap silently drops `Name:`/`Verify:`/… — the SDK's stage-0 gate + the new FR-6 parse-loss floor both fail on it);
- separators: `Approve?:` / `Was:` use `·` (also `|` `;`); `Was:` also accepts `,`;
- strong Lives: `git:<40-hex-sha>:<path>`; **`Lives:` must appear before `Verify:`** (the SDK reads Lives only pre-Verify);
- every FR carries a `Name:` (an actor·action·object·outcome phrase, no colon-label tokens in the prose).

## ⚠ The SDK change you must mirror (R1-F1, the reason FR-4 exists)

The SDK's `sources_requirements._lives_from_touches` mines existence-checked `Touches:` paths into `lives`
(for confidence/display), but as of `d0dd91b9` those mined refs are **`provenance: derived`** and the
**evidence-gate health class is computed from AUTHORED `Lives:` only** — a done-claim FR with *only* a mined
Touches ref now reads `unknown`, not `on_track`. **`req-health.mjs` and `extract.py` must do the same** so
the three-way parity (FR-4) holds. A fixture to share: *done-claim FR, no authored `Lives:`, one existing
`Touches:` path* → all three classify `unknown`; add a strong `git:` Lives → all three `on_track`.

## Acceptance (from the spec's Verify: clauses)

- `extract.py --report` exit 0 on the evidence dogfood graph export **and** it matches the Wire form.
- `roundtrip.sh --no-serve` on `fixtures/evidence-dogfood.graph.json` exits 0; a broken navigator stub exits non-zero with a named reason.
- The three health twins agree per fixture (the R1-F1 case above).
- The SDK side is done: `startd8 navigator build --source requirements <your-export> --format json` exits 0 and its node count equals your FR count (the FR-6 floor will fail-loud otherwise — a free cross-repo check that your writer didn't drop an FR).

## Coordination note (separate, also pending)

The `verify.gate` det-req-kit **schema field** (from startd8 REQ-22) + the ContextCore Node mirror + `dev-os/NODE-SCHEMA.md` §1 → 0.4.0 are a *different* coordinated cross-repo handoff (add `verify`/`approve`/`was`/`derivation`/`verify_gate` to the doc + kit). That's tracked in `startd8-sdk/docs/design/requirements-visualization/HANDOFF_devos-node-schema-0.4.0.md` — held on the in-flight 0.3.9 WIP on this same `chore/det-req-kit-learn-sdk-fields` branch. Land that first if convenient; it's independent of the seat-req FRs above.
