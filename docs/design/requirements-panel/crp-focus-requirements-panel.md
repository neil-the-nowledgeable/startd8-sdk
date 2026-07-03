# CRP Focus — Requirements Panel

## Where we need review most (least-reviewed target)

Both docs (`REQUIREMENTS_PANEL_REQUIREMENTS.md` v0.3, `..._PLAN.md` v0.1) are **brand new**. Weight on:

1. **The bucket-4 boundary (P1).** Is "estimate-provenance candidate requirements for human approval"
   a *real* boundary, or does drafting *requirements* inherently cross into authoring product intent
   the SDK shouldn't own? Is the provenance + human-approve-only floor sufficient, or does the mere act
   of a persona proposing an FR constitute bucket-4 authorship?
2. **The project-grounding guard (FR-RP-4).** Planning found the panel's `unsupported_specifics` grounds
   against the *persona's* brief and is *suppressed* for estimates. Is the owned brief+schema variant
   sound — will the money/percent/temporal extractors, tuned for scalar value answers, behave on longer
   requirement prose? Is advisory-then-CRP the right severity, or should any grounding class hard-block?
3. **The synthesis pass (FR-RP-3).** This is the least-deterministic step. Is "dedupe + stable IDs +
   order + conflicts→Open-Questions" enough, or does multi-role→one-doc need more structure? Does the
   R2-S1 "assemble whole, never per-item overwrite" discipline actually hold for a markdown doc?
4. **CRP as the second gate (FR-RP-6, P6).** The loop generates a draft that CRP then reviews — is that
   a clean gate, or a circularity risk (a generator whose only correctness check is the same review it
   feeds)? Should there be a deterministic pre-CRP readiness check (OQ-RP-8)?
5. **Value vs cost.** Is the `$0` persona-less baseline (schema+brief scaffold) worth it, or is all the
   value in the paid role pass? Is the paid elicitation better than a single author + CRP (which already
   exists)?

## Settled — do NOT relitigate

- **P1 scope lock** — estimate-drafts-for-approval, human is the sole promotion gate; NOT an authority
  on product intent. "Accept as-generated" changes edit burden, not the gate.
- **Not fused into the Stakeholder Panel** (NR-RP-1) — separate capability/CLI; the panel stays
  scalar-value-only.
- **No new proposal kind / grammar** (NR-RP-3) — approve is a markdown file-write; CRP is the gate.
  (Requirements have no `manifest`-style apply kind and need none — planning-verified.)
- **Own package + `elicit`** (overloaded-term lesson) — not a third meaning on `recommend`/`suggest`.
- **Reuse persona/routing/roster/`ProposalStore`/`panel.ask`/telemetry; own draft/synthesis/grounding/
  apply** (planning-settled; the grounding guard and apply-kind reuse were both falsified).
- **Three Manifest-Suggester findings already baked in** — do not re-derive: R2-S1 (synthesis, no
  overwrite → FR-RP-3), R3-S1 (heading sanitization → FR-RP-7), R1-S1 (`panel.ask` not bare
  `Persona.ask` → FR-RP-2).

## Dual-doc coverage ask

Confirm every FR-RP-* maps to a plan step (the plan's self-check matrix claims Full on all 9 — verify),
and that §7 Validation (bucket boundary, dual grounding, no-silent-overwrite, sanitization, reuse-not-
fork, panel-isolation) actually proves the requirements. Flag any FR whose acceptance criterion is
untestable as written.
