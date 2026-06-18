# Canonical S2 Pricing Artifacts

**Status:** Frozen for initial suite authoring  
**Date:** 2026-06-18  

This directory contains the canonical S2 contract and prose specification synthesized from the
independent Codex proto/spec authoring runs and the follow-up canonicalization decisions.

## Files

- `pricing.proto` — canonical gRPC contract for suite authoring.
- `spec.md` — canonical prose behavior specification.
- `canonicalization_decisions.md` — decisions used to resolve divergence between S2 runs.

## Seed Envelope

The packaged benchmark seed envelope is
`docs/design/model-benchmark/seeds/seed-resolvedpriceservice.json`. It embeds this canonical proto and
spec in `requirements_text`, records the behavioral suite as validation metadata, and pins the
benchmark runtime to Node.js with the vendored gRPC/proto-loader/decimal runtime closure. Registration
in `hardened-index.json` is deferred until a live `resolvedpriceservice` behavioral adapter exists.

## Scope

The primary pilot excludes tax handling and discount cap behavior. Those concepts remain
source-grounded in S1 traceability, but they are non-goals for the first oracle and suite.
