# CRP Focus — Wireframe↓Ingestion Wiring + Extraction Grammars

## Extended scope (a third in-scope review target)

Beyond the embedded requirements + plan, this review's **primary subject** is the extraction
grammar specification they depend on — review it and append a `#### Review Round R{n}` block
under its Appendix C (initialize the A/B/C scaffold if absent), with ids `R{n}-G{k}`:

- `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/KICKOFF_AUTHORING_CONTRACT.md`
  (**never previously reviewed** — the wiring docs have had two planning sweeps; this hasn't had one)

**Context only — read for grounding, do NOT review or write to:**
- `docs/design/kickoff/templates/REQUIREMENTS_AND_PLAN_FORMAT.md`, `templates/REQUIREMENTS_TEMPLATE.md`,
  `templates/HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md` (the format's other surfaces — relevant to ask 2)
- `docs/design/wireframe/WIREFRAME_REQUIREMENTS.md` (base spec, settled v0.4)
- `/Users/neilyashinsky/Documents/dev/strtd8/strtd8/docs/kickoff/REQUIREMENTS_v0.5-draft.md`
  (the worked instance — useful for testing grammars against real authored text)
- Spot-verify code read-only under `src/startd8/` (parsers: `view_codegen/manifest.py`,
  `scaffold_codegen/manifest.py`, `backend_codegen/pages_generator.py`, `ai_layer.py`,
  `derived.py`, `languages/prisma_parser.py`; wireframe `inputs.py` confinement).

## Settled — do NOT relitigate (treat as Appendix-B memory)

Code anchors (verified by three sweeps); the strtd8 pilot acceptance criteria (customer-stated);
the FR-F3 DIFF/DRAFT split and P7 deferral (operator-decided); the operator-coordinated
recording posture (Q2); advisory exit semantics (FR-W9).

## Where we need input most (4-line template per ask)

1. **Grammar ambiguity hunt (the highest-leverage ask).** Find sentences/table shapes in the
   authoring contract §2 that two independent extractor implementers would parse differently.
   Specifically probe: "links X to Y" vs "links to many" semantics (join-model arity, 3-entity
   sentences); kebab-derivation collisions and unicode/punctuation/reserved-word rules for
   entity/page names (the `metadata` reserved-name class); plural/synonym tolerance in
   "at least N Entity"; the plain-type → Prisma scalar mapping completeness; what exactly
   terminates a Views block. Propose the tightening, not just the hole.
2. **Cross-doc single-source drift.** Route derivation, the §2.7 settings vocabulary, and the
   completeness grammar each appear in 2–3 documents (contract / wiring reqs / plan / format
   spec / templates). Find every statement made in two places that could diverge, and propose
   which doc owns each (others cite). Five vocabulary-drift instances are already on record —
   this system's dominant failure mode.
3. **The `extra_root` confinement relaxation (plan P3 / FR-WPI-6 sweep-2 amendment).** A second
   permitted root for `--from-run` dirs. Attack the trust argument: symlinks inside the run
   dir, what a hostile/wrong `--from-run` target makes the wireframe read or write, whether the
   allowance can leak into `--inputs`/flag semantics, exit-code behavior on violations.
4. **Report + fingerprint semantics.** (a) Is `ExtractionReport`'s per-value identity defined
   tightly enough for stable cross-run diffing? (b) FR-WPI-10 binds re-walks to the
   wireframe-plan fingerprint — does ANY prose edit (a typo in free prose the extraction
   ignores) change `source_doc_checksums` and re-open the gate? If so, propose the
   extraction-relevant-content scoping (the FR-J3 lazy-rule analog) so the gate isn't ceremony.
