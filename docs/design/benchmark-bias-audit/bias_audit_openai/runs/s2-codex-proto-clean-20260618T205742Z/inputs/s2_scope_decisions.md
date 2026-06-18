# S2 Primary Pilot Scope Decisions

**Date:** 2026-06-18  
**Status:** Active for initial S2 authoring  
**Applies to:** primary pilot spec/proto authoring from `pricing-task-brief.md`  

These decisions constrain the first S2 authoring run without changing the upstream source evidence in
the neutral brief or traceability matrix.

## Decisions

- `OPEN-001` contract names and field names remain open for S2 authoring.
- `OPEN-002` money representation remains open, with exact decimal behavior required.
- `OPEN-003` rounding policy remains open. S2 authors must choose and manifest any rounding mode,
  scale, and intermediate-versus-final rounding policy they introduce.
- `OPEN-007` tax handling is deferred from the primary pilot oracle. S2 authors must treat tax as a
  non-goal for the primary pilot and must not require tax calculation behavior in generated artifacts.
- `OPEN-008` discount cap behavior is deferred from the primary pilot oracle. S2 authors must treat
  cap behavior as a non-goal for the primary pilot and must not require cap validation or cap
  calculation behavior in generated artifacts.
- `OPEN-012` runtime remains neutral during spec/proto authoring. The later benchmark seed packaging
  may use Node.js as a harness decision, but S2 authoring should not depend on Node.js semantics.

## Required Manifest Notes

Every S2 authoring run must record these scope decisions in `authoring_manifest.json` under either
`open_item_decisions`, `assumptions`, or `known_limitations`, as appropriate.
