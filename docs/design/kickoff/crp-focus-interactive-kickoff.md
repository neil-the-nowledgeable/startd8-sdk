# CRP Focus — Interactive Visual Kickoff Experience (R1)

These documents already passed a reflective-requirements loop (see Requirements §0 Planning Insights).
Weight the review toward the load-bearing risk areas below; deprioritize cosmetic/prose suggestions.

## Where we need scrutiny most

1. **Value-capture write path + FR-C3a exception (FR-NEW-1/2, M6).** A new concierge write builder
   edits `docs/kickoff/inputs/*.yaml` per field, and must READ the existing file to merge — an explicit
   exception to the "never read consumer content" policy (`writes.py:5-8`). Is the exception bounded
   correctly? Atomicity, partial-write, concurrent-edit, and clobber safety against `apply_write_plan`
   (`safe_write.py:200`)? Does merging into hand-authored YAML risk dropping comments/provenance markers?

2. **Per-field round-trip attribution (FR-NEW-3, FR-8).** The batch gate raises `RoundTripError` for the
   whole manifest (`extract.py:233`). Is per-field attribution actually derivable, or could a captured
   value fail in a way that can't be localized to one `value_path`? What happens on cross-field
   interactions (e.g., a relationship value valid only if a sibling entity exists)?

3. **Local app-serving plumbing/teardown (FR-NEW-4, M7).** A throwaway local FastAPI app: port
   selection, uvicorn lifecycle, scratch-dir cleanup, teardown on crash/Ctrl-C, and the trust boundary
   of a locally-served app that writes to project docs. Any zombie-process / orphaned-port / stale-scratch
   failure modes?

4. **Read-only agentic allow-list boundary (FR-9/FR-12, OQ-8).** The loop may only call
   `survey`/`assess`/`field_states`. Is "propose-only" for instantiate/log-friction airtight, or can a
   crafted conversation coerce a write? Does the dispatch floor (`handle_concierge_read`,
   `core.py:272-285`) fully cover the new `field_states` tool and any MCP entry point?

5. **Full-fidelity cross-surface parity (FR-3, OQ-6 resolved).** Both TUI (Rich) and web (HTMX/Jinja2)
   must render equivalent step/field/status/readiness output from shared M1/M2 data. Is parity testable
   deterministically? What is the canonical state representation both surfaces consume, and where could
   they drift?

## Out of scope for this review
- The manifest extraction grammar itself (frozen; this is a surface over it).
- `derive-contract` (separate track).
- Bucket-4 content generation (explicitly a non-requirement).
