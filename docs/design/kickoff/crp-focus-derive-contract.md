# CRP Focus — Concierge `derive-contract`

Weight the review on the four questions the planning pass surfaced (requirements §4 / plan §4).
The deterministic derivation rules and the EntityGraph-reuse decision are already verified against
navig8 — don't re-litigate those; focus on the unresolved design risks.

## Where we need input most

1. **Import safety (OQ-DC-3 / FR-DC-10) — the security question.** Derivation introspects models
   at **runtime**, which *executes the target package's module code* (imports run top-level code,
   and the project's deps must be importable). What's the right containment: subprocess/sandbox
   isolation, an import allowlist, or "only point it at code you trust" documented as the posture
   (it is the team's own models)? Is runtime import even acceptable, or should v1 fall back to a
   constrained static path despite its limits? This is the analogue of the write-path's OQ-7 — get
   the threat model explicit.

2. **Marker shape (OQ-DC-2 / FR-DC-12).** The two non-deterministic derivations (M2M joins,
   pipeline-artifact exclusion) need an opt-in author marker. Options: `Field(json_schema_extra=…)`,
   a `model_config` key, a sidecar YAML, a decorator. Which keeps domain models free of DB concerns,
   survives refactors, and stays discoverable? Is a sidecar (contract-side, not model-side) cleaner
   than annotating the models at all?

3. **Golden-test fidelity / acceptance bar (OQ-DC-1 / FR-DC-12, plan Step 7).** A re-derivation
   won't byte-match the hand-written navig8 contract (flagged M2M, the SequenceConfig Json bag,
   house-field ordering). Is "matches modulo flagged items" a sound acceptance bar, or does it hide
   real divergence? How should the golden test distinguish "correctly flagged ambiguity" from "got
   it wrong"?

4. **Assist-posture integrity under a richer output.** derive-contract emits a *contract* — the
   most load-bearing artifact in the SDK — plus a report for the Architect to ratify. Does anything
   in the design risk the contract being treated as authoritative before ratification (e.g. an
   `--apply` that writes a `schema.prisma` the cascade will immediately consume)? Is the
   ratification gate actually enforceable, or just advisory prose?
