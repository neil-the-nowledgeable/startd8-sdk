# Fixture provenance (G0)

Scrubbed from a real post-merge prime lineage:

- Source run dir: `strtd8/strtd8-v2-cascade/.cap-dev-pipe/pipeline-output/startd8/latest/plan-ingestion`
  (symlink to `run-010-20260606T2205/plan-ingestion`)
- Kept: 3 features (`PI-001a/b/c`), subset of `requirement_mappings` (`FR-11`, `FR-6`, `FR-8`)
  plus one `auto-satisfied` row for exclusion proof
- Paths placeholdered to `/FIXTURE_PROJECT_ROOT/…`; sources under `generated/`

## Content identity (sha256)

| File | sha256 |
|------|--------|
| `prime-postmortem-report.json` | `dfbd64d8b889d25da92d3128e912be4d63e7442610c3df20698f186c2f47b40d` |
| `ingestion-traceability.json` | `c1cc84dbfaee059eea0dec21c59d0260a01525b81545d0df382d9251b5d9cd64` |

## Merge identity stance

Tests create a local git commit from `generated/` and pass that tip as `--merge-sha`
(FR-3 plate). A separate plate uses `--merge-sha unknown` (FR-4 skip).

## Book-A stance

- Stub REQ (FR ids, no Lives) → `fr-missing-lives` (Book B loadable).
- Fueled template `REQ-dogfood-fueled.md.template` (CEP-B3) — fill `__MERGE_SHA__` via
  `materialize_fueled_req(sha, dest)` after emit → expect `agree` on FR-11 / FR-6 / FR-8.
