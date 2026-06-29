# Kickoff Authoring Contract — Implementation Next Steps

**Version:** 0.2
**Date:** 2026-06-05
**Status:** Active tracker — **lane A (the build) is DONE** (`f4457d43`/`6791ecca` on main:
`src/startd8/manifest_extraction/` + EMIT wiring + `wireframe --from-run`, piloted on the real
strtd8 docs). Remaining lanes sequenced into phases K1–K6 by
[`KICKOFF_AUTHORING_CONTRACT_IMPLEMENTATION_PLAN.md`](KICKOFF_AUTHORING_CONTRACT_IMPLEMENTATION_PLAN.md)
(v1.0) — including two **conformance gaps the build audit found** (collision pre-flight +
reserved-name guard, §2.0/R1-G4, not in the shipped extractor) and a **correction**: step 8's
"the env-keys ↔ `build-preferences.yaml` agreement check works today" was optimistic — the
shipped extractor flags `env keys` without parsing entries; now plan K2-3.
**Subject:** [`KICKOFF_AUTHORING_CONTRACT.md`](KICKOFF_AUTHORING_CONTRACT.md) v0.2 (grammar v0.2)
**Where the contract stands:** CRP'd (11 grammar suggestions applied, 2 rounds), and
**empirically de-risked** — the 2026-06-05 spike parsed the REAL strtd8 requirements draft with
~300 lines of stdlib code: 4/4 attempted manifests round-tripped clean through the generators'
parsers and the wireframe hit the pilot acceptance numbers exactly
(`../wireframe/spike-2026-06-05/SPIKE_FINDINGS.md`).

---

## 1. Is there a plan? Yes — split by ownership

The contract's grammars don't get their own implementation plan: **their executable form IS
P0/P1 of [`../wireframe/WIREFRAME_INGESTION_WIRING_PLAN.md`](../wireframe/WIREFRAME_INGESTION_WIRING_PLAN.md)
v1.2** (the extraction module + per-manifest extractors). The P0 grammar-contract gate
(CRP R2-S4) is **satisfied** — contract v0.2's decisions are Accepted — so build can start.
This tracker covers what the wiring plan deliberately does *not* own: the contract's own
teaching surfaces, tooling, versioning, and the generator gaps its flags create.

```
A. BUILD (wiring plan P0–P2)        — the grammars become code           [critical path]
B. Teaching-surface alignment        — §5 ownership made real            [quick, drift-prone]
C. Lint mode                         — authors check before extraction    [after P2]
D. Generator-gap backlog             — make flagged fields extractable    [independent]
E. Versioning mechanics              — grammar v0.2 was the first growth  [with corpus]
F. strtd8 follow-ups                 — pilot-adjacent contract items      [team-paced]
```

## 2. The steps

### A — Build (owned by the wiring plan; listed for the critical path)

1. **P0** `src/startd8/manifest_extraction/` — sections/table parsing (spike-pinned: maximal
   consecutive-`|` table segmentation with the 21-phantom-pages regression test; NFKD route
   normalization; cell-annotation stripping) + `ExtractionReport`.
2. **P1** seven extractors in the CRP-mandated order (relationships → views → completeness),
   each round-tripping its generator parser; v1 emits **shells** for detail-compose/workspace
   `Shows:` prose (spike F3) with per-line `not_extracted` flags.
3. **Tests**: the 13-case ambiguity corpus (plan v1.1) + the spike's F1–F6 cases; the spike's
   `spike.py` is the test-case source — *supersede, don't reuse*.

### B — Teaching-surface alignment (contract §5 ownership — ✅ DONE 2026-06-29)

4. ✅ Snapshot-marked every vocabulary list in the three teaching surfaces so they cite contract
   §-refs as non-normative quotations: `templates/REQUIREMENTS_TEMPLATE.md` (Entities §2.1,
   Scaffold §2.7, Views §2.3, Completeness §2.4 guidance lines now carry "non-normative snapshot
   of …§X — the contract owns it"), `templates/HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md` §3 (added
   a normative-owner header + a per-row `Contract` §-ref column), `templates/REQUIREMENTS_AND_PLAN_FORMAT.md`
   (added an explicit §5 vocabulary-ownership note; per-section `contract §2.x` callouts were
   already present). "Contract wins on disagreement" stated in all three.
5. ✅ Reflected the grammar additions authors should know **as §-cited snapshots, not restatements**:
   one-field-per-row (§2.1) and board's required `Group by:` + optional `Order:` (§2.3) were the two
   genuinely missing — added to the template guidance, the view-block scaffold (`- Group by:` line),
   and the how-to §3 table. `links to many`, `references`, `default:`, `money`, and the optional view
   `Route:` override were already present in the templates from prior VIP/DMC syncs. Bumped the
   template header's `authoring-contract grammar v0.1` → `v0.3` (it teaches v0.3 constructs now).

### C — Lint mode (contract OQ-2) — ✅ ALREADY SHIPPED

6. ✅ `startd8 kickoff check <doc>` is the extraction dry-run / write-nothing lint mode
   (`cli_kickoff.py:check`) — renders the conformance report, writes nothing. OQ-2 satisfied.

### D — Generator-gap backlog (each closes a standing `not_extracted(generator-gap)` flag)

7. ✅ **Completeness authored nudge** (DONE 2026-06-29, `0bea4d89`) — the §2.4 ` — nudge: "…"`
   suffix is now carried into the per-entity completeness manifest (`backend_codegen/derived.py`
   `nudge` field) and baked into `compute_completeness`; the extractor flips the nudge row
   NOT_EXTRACTED→EXTRACTED. Byte-identical when absent. (The broader `predicate`/`confirmed`/`href`
   rich fields remain a future refinement; the nudge was the live flag.)
8. ✅ **`AppManifest` gaps** (DONE 2026-06-29) — `port` and `env keys` gained homes
   (`app.port` / `app.env_keys`, `scaffold_codegen/manifest.py`), consumed by the Dockerfile/
   run.sh (port) and `.env.example` (env keys, deduped); the §2.7 extractor emits them.
   **`sqlite mode` deliberately stays flagged** — WAL/journal-mode touches app `db.py`, not
   scaffold plumbing (the renderers' own v1 scope note), so it's a backend-codegen backlog item,
   not a scaffold gap. §2.7 mapping table + contract updated.
9. **Views `Shows:` for detail-compose/workspace** (spike F3) — v1 ships shells; a
   `view_codegen` relations/panels enrichment pass later upgrades the prose lines from
   `not_extracted` to extracted. Track against REQ-VIEW.

### E — Versioning mechanics (contract OQ-1)

10. Grammar v0.2 was the **first vocabulary-growth event** (CRP adoptions) — back-compatible by
    design. Formalize the version triple (format / contract grammar / corpus snapshot) in the
    doc headers when the controlled corpus ships (§4b); until then the header convention from
    the templates suffices.

### F — strtd8 pilot-adjacent (team-paced; tracked in their VALIDATION doc)

11. Entity-table fidelity vs live contract (JobDescription `rawText` + AI-extracted fields;
    TailoredAsset `variant/tone/body/metadataJson`) — required **before P2 manifests derive**.
12. Their flagged-open items: the 6th completeness signal (TargetRole), the FR-8
    master-artifact feature row (Iteration-3 front checkpoint).

## 3. Sequencing

**Done:** A1–A3 (the build) **and** B4–B5 (teaching-surface alignment, 2026-06-29). **After P2:**
C6. **Independent, schedule by appetite:** D7–D9. **Event-driven:** E10 (corpus ships), F11–F12
(StartDate team cadence, pre-P2-derivation).

| Step | Effort | Blocked by | Status |
|------|--------|-----------|--------|
| A1–A3 build | the main work | nothing — gate satisfied | ✅ done |
| B4–B5 templates | trivial | nothing | ✅ done (2026-06-29) |
| C6 lint | small | P2 | open |
| D7–D9 generator gaps | small–medium each | nothing (independent) | open |
| E10 versioning | trivial | corpus | open |
| F11–F12 strtd8 | team | pre-P2-derivation only | open |
