# CRP Focus — Welcome Mat Concierge Mode (R1)

These docs passed a reflective-requirements loop (see Requirements §0). Weight the review toward
the load-bearing risk areas; deprioritize cosmetic/prose suggestions.

## Where we need scrutiny most
1. **The generic write applier (FR-CM-7 / M-CM1).** `apply_concierge_plan` wraps `to_planned_writes`
   + `apply_write_plan`. Is the typed error mapping (WRITE_BLOCKED/WRITE_REFUSED) complete? Friction
   timestamp stamping (NR-CM-B) — right layer? Any concurrency/atomicity gaps for the jsonl append vs
   the multi-file instantiate projection?
2. **Serve package-less (NR-CM-A / M-CM2).** Demoting `inputs_dir` to advisory — does anything
   downstream assume inputs exist (state/readiness/capture handlers) and break on an empty project?
   Is a concierge-bootstrap serve mode safer than a blanket demotion?
3. **Instantiate boundary (FR-CM-6 / OQ-2).** Instantiate into the pinned served root only. Is the
   no-clobber honest (NR-CM-C)? Could a served write app at human privilege be coerced (cross-origin,
   CSRF) into instantiating/overwriting? Posture (prototype/production) surfaced safely?
4. **Web/TUI parity + the new TUI host (FR-CM-10 / M-CM4).** Both surfaces consume one
   `build_concierge_view` payload. Is parity testable? The new `kickoff concierge` Typer command +
   questionary confirm — any reuse of an existing confirm/apply pattern missed?
5. **Agentic + MCP boundaries (FR-CM-8/9).** Verify "propose-only" truly holds (the loop has no apply
   tool) and that no Concierge write can ever reach MCP. Any path that widens the read-only floor?

## Out of scope
- The concierge builders themselves (frozen; this is a surface over them).
- derive-contract (NR-1). Friction read-back (OQ-5, deferred).
