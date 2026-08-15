# Beta — Requirements

**Format:** det-req/0.1
**Backend:** python-cli-surface

> **Readable handle:** `feature/govern-fixture-beta`
> **Semantic name:** *A second clean fixture requirement, referencing REQ-01 so neither is orphaned.*
> **Canonical ref:** `cc:intent:govern-fixture:feature:req-02`

## Objectives

- O-1: Be the second clean member — target: passes govern

## Functional requirements

- **FR-1 — Do the beta thing.** It does the beta thing, building on REQ-01. Name: beta does the thing cleanly. Touches: `src/startd8/navigator/govern.py`. Verify: `navigator govern` passes this doc. Serves: O-1

## Non-goals

- NR-1: Nothing else.
