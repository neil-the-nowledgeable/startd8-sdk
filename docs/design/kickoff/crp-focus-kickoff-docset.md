# CRP Focus — Kickoff Doc Set Review

## Extended scope (review ALL of these, not just the embedded master doc)

The embedded requirements document is the **master** of a five-doc set. The four domain slices
below are **equally in-scope review targets**: read each from disk, and append a
`#### Review Round R{n}` block under **each** file's Appendix C (initialize the A/B/C scaffold if
absent), exactly as you do for the master. Use per-doc suggestion ids
(F-master-1…, F-asm-1…, F-cnt-1…, F-cnv-1…, F-bp-1…).

| Role | Absolute path |
|------|---------------|
| Master (embedded below) | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/KICKOFF_REQUIREMENTS.md` |
| Slice F — assembly | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/KICKOFF_ASSEMBLY_INPUTS.md` |
| Slice G — content | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/KICKOFF_CONTENT_INPUTS.md` |
| Slice H — conventions | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/KICKOFF_CONVENTION_INPUTS.md` |
| Slice I — build preferences | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/KICKOFF_BUILD_PREFERENCE_INPUTS.md` |

**Context only — do NOT review or write to these:**
- `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md`
  (settled prior art; the A–E slice of the set)
- `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/ASSEMBLY_INPUTS_TEMPLATE.md`
  (derived artifact of FR-X5)
- `/Users/neilyashinsky/Documents/dev/strtd8/strtd8/docs/v2/ASSEMBLY_INPUTS.md`
  (the reference inventory instance the set must cover)

## Where we need input most (answer each with the 4-line template)

1. **Cross-doc consistency.** Do the master's high-level FR statements (§5) and the slices'
   detailed FRs (same IDs) ever diverge in meaning, normative strength (MUST/MAY), or scope?
   Flag every divergence — the set's biggest structural risk is master/slice drift.
2. **Ownership boundaries.** Each requirement implies an owner (startd8 SDK vs cap-dev-pipe vs
   ContextCore). Are any FRs ambiguous about who implements them, or do any silently cross the
   delegation boundary (manifest schema + gather flow = ContextCore/cap-dev-pipe; consumption +
   injection reach = startd8)?
3. **Testability of the X-machinery.** Are FR-X1–X5 (pre-flight report, RESOLVE delegation,
   criticality matrix, provenance/score, per-project inventory) specified tightly enough that an
   implementer could write acceptance tests — particularly the `authored|placeholder|absent`
   state-assignment rules?
4. **Unverified anchors.** The set cites code anchors verified for `backend_codegen`, but the
   scaffold (`app.yaml`) and views (`views.yaml`) hash-parity claims and `explain-content.yaml`
   role are weaker. If filesystem access allows, spot-verify under
   `/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/` and flag wrong claims.
5. **Coverage completeness.** Is any user-input surface at build kickoff missing from the master
   catalog (§3) entirely — i.e. a sixth class or an uncatalogued input within F–I?
