# Example — strtd8 Architect Approval Summary

> The **summary altitude** (NODE-SCHEMA §3b, SV-1…SV-7) rendered over the *real* strtd8 shape — what
> an architect sees at the DATA MODEL bookend to glance-approve, without reading `schema.prisma`.
> Data is verbatim from `startd8 wireframe --project ~/Documents/dev/strtd8/strtd8` (2026-07-17).
> This is the **acceptance-test proof, positive side**: the summary made glance-approvable.

## At a glance ✅ HEALTHY · READY TO GENERATE
`9 planned · 0 defaults · 0 placeholder · 0 not-defined · 0 invalid` — nothing undefined, nothing broken.

| Object | Count | What it is (SV-3) |
|---|---:|---|
| 📦 **Entities** | **31** | the data model — **6 core + 25 derived** (SV-4, below) |
| 🔀 CRUD routes | 155 | ~5 routes × 31 entities (derived) |
| 📄 Pages | 3 | home · how-it-works · jobs |
| 📝 Forms | per-entity | field-level create/edit per entity |
| 🧩 Views | 9 | composite: dashboard, completeness, export/import, artifact reader, … |
| 🤖 AI passes | 8 | extract → suggest → quantify → synthesize → generate → draft |

## The one decision (SV-4) — are the 6 core entities right?
A raw "31 entities" hides the actual judgment. The summary splits it:

- **CORE — judge these (the real human inputs, completeness-gated):**
  `Profile · ProofPoint (≥3 rows) · TargetRole · Outcome · Metric · Differentiator`
- **DERIVED — auto (generated / joined / AI-output; excluded from completeness):**
  `Capability · ValueProp · Artifact · JobDescription · TailoredMatch · TailoredAsset · Company ·
  Contact · AiCall · + join tables (CapabilityOutcome, ProofPointCapability, ProofPointOutcome, …)`

**Approve if:** those **6** are the real inputs a user supplies; the other **25** are legitimately
generated/joined. *(This is the datum the raw wireframe buried in `Completeness → excluded`.)*

## Why this is the moment (SV, WHY)
This contract drives ~89% of the app. Approving it **here, before the first cascade run**, is the
cheapest correction; getting the 6 core entities wrong is the most expensive thing to fix later.

## Readiness (SV-6)
`scaffold: ready · backend: ready · views: ready` → the cascade can run.

## Spoken form (SV-7 / invariant 8)
> *"strtd8: 31 entities — 6 core, 25 derived — 155 routes, 3 pages, 9 views, 8 AI passes. All
> planned, nothing undefined or invalid. Cascade ready. The decision: approve the 6 core entities."*

## Verdict — the acceptance test, on the reference consumer
An architect can glance-approve strtd8's shape from **this** — magnitude, the 6-vs-25 decision,
health, and readiness — **without reading `schema.prisma`.** The **raw** wireframe footer gave
magnitude + health + readiness but *not* the 6-vs-25 decision, so "is it right?" still required the
contract. The summary altitude (§3b, SV-4) closes exactly that gap. ✅ **The visualization layer
passes the Architect acceptance test at the summary level.**
