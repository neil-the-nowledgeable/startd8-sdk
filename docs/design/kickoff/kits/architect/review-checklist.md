# Architect — Review Checklist (FR-J9 b)

> What the architect verifies before approving the convention manifest + contract at the DATA
> MODEL bookend. Grounded in the **CRP** (`startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md`)
> and the wireframe's pre-generation preview. This is the *human* review; run a CRP pass first to
> surface what an independent model catches, then apply this judgment on top.

## A. Contract (the anchor)
- [ ] Every entity the requirements imply exists; nothing invented that the business didn't ask for.
- [ ] Relations + ownership are right; `human_inputs` / server-managed fields are marked (not writable).
- [ ] The composite `views.yaml` shape matches how the user actually works (not just the raw tables).
- [ ] **Ran `startd8 wireframe`** — the planned shape (entities → CRUD, pages, forms, views) matches
      intent, and every `not_defined` / `placeholder` section is *intentionally* deferred, not missed.

## B. Conventions (the frame)
- [ ] Persistence + display frameworks fit the business + the team's ability to maintain them.
- [ ] Naming/layout conventions are consistent and won't force per-service special-casing.
- [ ] Auth posture + deployment mode (installed / server) are decided and recorded.

## C. Decisions (durability)
- [ ] Each non-obvious choice has an ADR (why + what was rejected); reasoning survives the author.
- [ ] No accidental complexity introduced to compensate for a defect a single rule would dissolve.

## D. Ready to approve
- [ ] The wireframe preview would not surprise the customer.
- [ ] I can defend the contract shape as *this business's* choice, not a generic default.
- [ ] Proceeding to the first cascade run is the right next act.

---
*Pass all four → record the approval per [`validation.md`](./validation.md). Any unchecked box is a
block-or-warn decision, not a silent proceed.*
