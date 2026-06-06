# CRP Focus — HITM Role Model Requirements

## Context (read for grounding — do NOT review or write to these)

This doc is **Group J** of the kickoff doc set (already CRP-reviewed, R1+R2 triaged — do not
re-review):
- `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/KICKOFF_REQUIREMENTS.md` (master:
  input classes F/G/H/I/A–E, FR-X machinery, provisioning states, provenance enums)
- `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/KICKOFF_CONTENT_INPUTS.md`
  (FR-G1/G2/G3 — tier D refines FR-G3)
- The other `kickoff/` slices and `OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md` as needed.

You MAY spot-verify code claims read-only under
`/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/` (e.g. `artisan_models.py`
ChunkState, `exemplars/registry.py` maturity ladder) and
`/Users/neilyashinsky/Documents/dev/cap-dev-pipe/pipeline/` (seed-quality gate).

## Where we need input most (answer each with the 4-line template)

1. **Tier taxonomy soundness.** Are the five tiers (U/E/D/G/R) mutually exclusive and jointly
   sufficient? Find inputs/artifacts that don't class cleanly, or pairs of tiers whose rules
   conflict when one artifact passes through multiple (e.g. an LLM-drafted KPI rationale: E or
   D?).
2. **Gate/ceremony tension.** FR-J3 names nine roles' validation points while §5 promises "no
   ceremony" and OQ-4 leaves cadence open. Is the gate model implementable without either
   (a) stop-the-world friction or (b) gates so soft they're decorative? Propose the binding
   rule if you see one.
3. **Tier D production-blocking.** FR-J7 says `draft-for-validation` content is "structurally
   blocked from production paths" — is that enforceable as specified (what IS a production path
   in the generated-app model?), and does the FR-G3 refinement create a loophole?
4. **Kickoff integration.** Do the FR-J extensions to FR-X5 (role/validated_by/tier columns),
   FR-X4 (estimate provenance), and FR-G1 (draft-for-validation status) compose cleanly with
   the already-triaged kickoff FRs, or do any conflict (enum collisions, denominators, status
   mappings)?
5. **Role map completeness/realism.** Any missing role whose uniquely-human input the build
   process needs (e.g. security, UX research, compliance, product owner vs BA)? Any §3 role
   whose "validation point" is actually unverifiable as written?
