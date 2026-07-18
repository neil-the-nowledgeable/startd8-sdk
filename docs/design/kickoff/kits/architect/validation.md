# Architect — Validation Artifact (FR-J9 c)

> The role's **named validation point** — what the architect approves, when, and how it's recorded.
> Grounded verbatim in HITM §3.3: *"Architect approves the **convention manifest + contract**
> before the first cascade run — this **is** the DATA MODEL bookend, generalized."*

## What is approved
The **convention manifest + contract** (`conventions.yaml` + `schema.prisma`, with its ADRs) — the
[draft template](./draft-template.md) deliverables, after the [review checklist](./review-checklist.md).
This is the artifact; the wireframe is the *tool* that makes it reviewable, not the artifact itself.

## When (the gate)
**Before the first cascade run** — the DATA MODEL front bookend. Approval is **hash-bound**
(FR-J3): it binds to the artifact's content hash and persists until the content changes; it's
**evaluated at consumption** (when the first cascade phase reads the contract), where the FR-X3
block/warn matrix applies. Re-approval is triggered *only* by a content change — two runs on an
unchanged approved contract re-prompt nothing.

## How it's recorded (prior art — don't invent)
- **Schema:** lift `ChunkState` (`contractors/artisan_models.py:234` — `DRAFT→IN_REVIEW→APPROVED`,
  with a validator enforcing `approved_at ⇒ APPROVED`) out of the artisan tree and add
  `approved_by: ActorReference{id, role, email?, timestamp}` (FR-J3). Identity anchors on
  `metadata.owners` (team) or git identity (solo default).
- **Disposition pattern:** the CRP **Appendix A/B** (accepted / rejected + rationale) — the doc-side
  prior art for durable decisions.
- **Not this:** no new state machine, no per-artifact ceremony on telemetry (FR-J1 scope carve-out),
  no `--fail-on-incomplete` gate (advisory posture, FR-KIT-2).

## The supporting tool
`startd8 wireframe --project <root>` — the $0, read-only, advisory pre-generation preview. It shows
the planned application shape and what's still undefined, so the approval is *informed*. It is the
"advisory-CLI precedent" HITM names — and, fittingly, the artifact the whole `FR-KIT` question
started from.

---
*This closes the Architect kit's triad (3/3). It is the DATA MODEL bookend given a named holder,
a named artifact, a review, and a recorded approval.*
