# Self-Hosted Content — Implementation Plan

**Version:** 0.1 (post-planning-spike; paired with `SELF_HOSTED_CONTENT_REQUIREMENTS.md` v0.2)
**Date:** 2026-07-19
**Status:** Draft

The planning pass ran a **spike** (compute the audience-matrix coverage over the real `descriptive.yaml`
now) to stress-test the requirements before building. It resolved both load-bearing open questions and
surfaced three corrections that flow back to the requirements §0.

## Spike result (grounded, 2026-07-19)

```
sections: 10 (+ 1 special 'summary' record)
architect base coverage: 40/40 (100%)      # what/why/do/next × 10 sections
end_user  base coverage: 60/60 (100%)       # title/what/wont/need/do/next × 10 sections
end_user gaps: NONE                          # the R1-F4 completeness bar is fully met
fluency depth authored: {entities:[beginner,advanced], forms:[beginner,advanced]}  # sparse, opt-in
DISCOVERY: the 'summary' record has a DIFFERENT field set than a section record
```

Coverage was **~30 lines reusing the `CoverageStat` idea** — no new subsystem, no dogfood-through-the-cascade.

## Architecture

A **lightweight coverage rollup over the descriptive manifest**, reusing `CoverageStat` (Mottainai) — NOT
a re-run of the app cascade. Two declared record *types* (the spike's key discovery):

```
descriptive.yaml ──▶ descriptive_schema (declared per-type field sets) ──▶ matrix_coverage(records)
   (the manifest)        section-record: {arch: what/why/do/next;               (reuses CoverageStat)
                          end_user: title/what/wont/need/do/next}                      │
                         summary-record: {arch: why/do;                                ▼
                          end_user: headline/lead/steps/closing}          test-asserted report + optional
                                                                          `startd8 describe --coverage`
```

The same declared schema is read by BOTH the coverage rollup AND (over time) `describe.py`'s resolver, so
the "expected shape" is single-sourced (FR-SHC-1/2), not duplicated between validator and consumer.

## Steps

- **M-SHC-0 — Declare the record-type schema (FR-SHC-2).** A single declared spec of the two record types
  and their required-vs-optional fields per role (co-located with `describe.py`, e.g. `descriptive_schema.py`,
  or a `# schema:` block in `descriptive.yaml`). This is the "data model" of our content; the spike proved
  it must be **two types** (section vs summary), not one.
- **M-SHC-1 — Coverage rollup (FR-SHC-3/4).** `matrix_coverage(records) -> {per_role, per_type, overall,
  gaps}` reusing `CoverageStat`. Denominator = record-type schema × roles-in-use (OQ-SHC-2 resolved);
  fluency reported informationally, NOT in the denominator (NR-2). `gaps` = the authoring to-do list.
- **M-SHC-2 — Surface it, lightweight (FR-SHC-5, OQ-SHC-1 resolved).** (a) A **regression-guard test**:
  `expected-matrix coverage == 100%` — generalizes the R1-F4 bar to the whole matrix, so adding a section
  or authoring a new role without its cells FAILS CI. (b) Optional `startd8 describe --coverage` printout
  (the FR-WCI-2 band, self-applied). No visual coverage view yet.
- **M-SHC-3 — (deferred) escalate only if warranted.** A visual coverage view / full dogfood only if the
  matrix grows enough to need it (DEV-OS "run the manual loop N times first" — don't over-formalize).

## Mapping (every FR has a step)

| FR | Step |
|---|---|
| FR-SHC-1 (single-source manifest) | already true (`descriptive.yaml` + FR-DL-5); M-SHC-0 declares its schema |
| FR-SHC-2 (declared record schema) | M-SHC-0 — **two record types** (spike discovery) |
| FR-SHC-3 (coverage rollup) | M-SHC-1 (reuse `CoverageStat`) |
| FR-SHC-4 (gaps as to-dos) | M-SHC-1 `gaps` + M-SHC-2 report |
| FR-SHC-5 (dogfood where it fits) | M-SHC-2 (lightweight report; OQ-SHC-1 → report, not full cascade) |
| FR-SHC-6 (same invariants) | inherited — pure over the manifest, deterministic, never a gate |

## Discoveries fed to requirements §0 (belief → actual)

1. **One record schema → TWO record types.** The `summary` record's fields (`headline/lead/steps/closing`)
   differ from a section record's (`title/what/wont/need/do/next`). FR-SHC-2 must declare per-*type* schemas.
2. **Coverage would find current gaps → it's already 100%.** The expected matrix (arch base + end_user
   base) is fully authored (R1-F4 met). So FR-SHC-3's value now is a **regression guard + a visible number**,
   not fixing a present hole — reframe FR-SHC-4 as "keep it from silently drifting," not "find today's gaps."
3. **Might need dogfood-full → a ~30-line report suffices.** Running `descriptive.yaml` through the app
   cascade would be contrived machinery (fails the accidental-complexity guard); the coverage is trivial to
   compute directly. **OQ-SHC-1 → lightweight report.** FR-SHC-5 narrows accordingly.
4. **Fluency confirmed sparse/opt-in** (2 of 10 sections) → excluded from the denominator (NR-2 holds),
   reported informationally. **OQ-SHC-2 (denominator) → record-type schema × roles-in-use.**

## Build status (2026-07-19)

**M-SHC-0/1/2 ✅ BUILT** (`src/startd8/wireframe/descriptive_schema.py` + `test_descriptive_coverage.py`):

- **M-SHC-0 ✅** — `SECTION_SCHEMA` + `SUMMARY_SCHEMA` declare the two record-type field sets per role
  (the "data model" of our content, FR-SHC-2). Single-source; `describe.py` can adopt it over time.
- **M-SHC-1 ✅** — `matrix_coverage()` reuses `CoverageStat` (Mottainai): `{by_role, overall, gaps,
  fluency}`. Denominator = required fields × roles; fluency reported, not counted.
- **M-SHC-2 ✅** — 5 tests incl. the **regression guard** (`test_expected_matrix_is_fully_authored`),
  a guard-catches-a-gap test, and the two-record-types test. `format_report()` / `python -m
  startd8.wireframe.descriptive_schema` prints the readout.
- **Live:** architect **33/33**, end_user **44/44**, overall **77/77 (100%)**, 0 gaps — matches the spike.
  Full suite **159 pass**. No telemetry, no new subsystem (right-sized Mieruka, FR-SHC-5).

## Review log
*(scaffold — CRP suggestions land here as `#### Review Round R{n}` under Appendix C)*

### Appendix A / B / C
*(empty — awaiting first CRP round)*
