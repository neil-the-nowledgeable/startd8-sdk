# CRP Focus — Manifest Suggester

## Where we need review most (least-reviewed target)

Both docs (`MANIFEST_SUGGESTER_REQUIREMENTS.md` v0.3, `..._PLAN.md` v0.1) are **brand new**. Weight on:

1. **The composite-not-CRUD scope** — is "the cascade auto-generates entity CRUD; `pages.yaml`/`views.yaml`
   are for composites + non-entity pages" *actually* how the codegen works, or does any real project need
   a CRUD page in `pages.yaml`? (If the premise is wrong, FR-MS-1 is wrong.)
2. **Schema-grounding vs the extractor round-trip** — are two gates (the schema grounding guard AND the
   `manifest`-kind extractor round-trip) both needed, or is one redundant? Can a role-drafted composite
   pass the schema guard yet still fail the real extractor (or vice-versa)?
3. **Panel-infra reuse boundary** — is `persona`/`routing`/`roster` genuinely generic enough to reuse for a
   `views`/`pages` symbol, or is there hidden coupling to the value-domain roster (e.g. the `domain`
   discriminator / `answers_for` semantics) that would force a fork?
4. **The `manifest` apply seam** — does an approved composite's emitted prose actually round-trip through
   `extract_views`/`extract_pages` (required fields, `Kind` vocabulary), and does dest-derivation land it in
   the right file without a hint?
5. **Value vs cost** — is the `$0` starter-dashboard worth it, or is the whole value in the paid role pass?
   Is a single starter dashboard the right baseline, or none at all?

## Settled — do NOT relitigate

- **Not fused into the Stakeholder Panel** (NR-1) — separate capability/CLI; the panel stays scalar-only.
- **No entity-CRUD baseline** (NR-3a) — planning-settled; CRUD is the cascade's job.
- **Propose-confirm floor + reuse the `manifest` kind** — the loop never writes; approved screens apply via
  the existing `manifest` proposal (extractor round-trip + dest-confinement); no new write path/grammar.
- **Bucket-1 authoring only** (NR-2) — proposes *which screens + structure*, never bucket-4 real content.

## Dual-doc coverage ask

Confirm every FR-MS-* maps to a plan step, and that §7 (no-CRUD-duplication, schema-grounding round-trip,
propose-confirm, panel-isolation) actually proves the requirements.
