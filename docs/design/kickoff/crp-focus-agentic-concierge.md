# CRP Focus — Agentic Concierge Mode (R1)

These docs passed a reflective-requirements loop (Requirements §0). Weight toward the load-bearing
risk areas; deprioritize cosmetic suggestions.

## Where we need scrutiny most
1. **The read-only floor stays intact (FR-AC-4 / FR-AC-2).** The loop adds a `propose_action`
   read-effect tool. Can anything coerce a write through it? Is "the loop never writes" truly
   preserved when the propose handler records params that the host later applies? Is the M-CM6 guard
   extension sufficient (registry ⊆ {survey,assess,field_states,propose_action}, all read; propose
   cannot reach apply)?
2. **Confirm-then-apply correctness (FR-AC-3 / OQ-7 / FR-NEW-2).** Plan rebuilt at confirm against
   live state — any TOCTOU between propose and confirm beyond stale-file (e.g. allow-list changed,
   package became complete)? Is the buffer-entry-as-one-time-intent airtight against double-confirm?
3. **Prompt rewrite (FR-NEW-1).** Rewriting the system prompt to introduce a write-proposing tool on a
   "read-only" assistant — does this risk the model over-claiming or attempting writes? Is the
   structural enforcement (host prints the code) enough that prompt wording is non-load-bearing?
4. **Friction draft grounding (FR-AC-5 / OQ-6).** LLM-authored friction prose with only human-confirm
   as the gate — any injection / low-quality-data risk to the append-only log? Length caps / privacy?
5. **Surface boundary (FR-AC-8 / FR-NEW-3/5).** Keeping plain `kickoff chat` pure vs the agentic
   superset — clean? The REPL signature extension — any coupling/parity concern with the web path
   (deferred)?

## Out of scope
- The agentic loop internals (AgenticSession) and the concierge write builders (frozen; surface over them).
- The web agentic panel (OQ-2, deferred).
