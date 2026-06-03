# Pre-existing Test Failure Audit — 2026-06-03

**Context:** while landing the M3 post-mortem fixes (run-021/023/gpt-m3), the
broader unit suite showed **15 failures**. All 15 were confirmed **pre-existing**
(they fail identically with the post-mortem changes stashed) — none were
introduced by that work. This document records the root cause and resolution of
each.

**Method:** `git stash push -- src/ tests/` then re-run → 15 still fail ⇒
pre-existing. Each failure was then traced to its commit of origin and the
current source of truth.

## Summary

| Cluster | Tests | Root cause | Category | Resolution |
|---|---|---|---|---|
| `test_kaizen_metadata_agent_specs` | 12 | `_update_kaizen_metadata_agent_specs` **never implemented** (tests landed in `46e205c5`, 2026-03-14; no commit ever defined the method) | **Spec'd + tested, NOT implemented** | **Implemented** the method + wired into `_persist_kaizen_prompts` → 12 green |
| `test_complexity_router::test_to_dict` | 1 | `TaskComplexitySignals` gained a 14th field (`has_fillable_elements`, RUN-007 FR-7) after the test's last update; test asserts `len == 13` | Stale test, code correct | **Updated test** → `len == 14` + asserts field present |
| `test_pca_p0::test_track_new_field` | 1 | `_track_onboarding_consumption` now also records `_generation_profile` (REQ-GPC-700); test's exact-dict assertion didn't expect it | Stale test, code correct | **Updated test** to expect `_generation_profile: "full"` |
| `test_repair_gridpos::…_skips_when_any_panel_has_group` | 1 | **Untracked** test asserts grouped layouts skip gridPos injection — but OBS-710b specifies "inject when missing" with **no** group carve-out; impl matches the spec | Untracked test contradicts requirement | **Left code unchanged**; flagged for owner decision (see below) |

Net after this audit: **14/15 resolved**. The 15th (`repair_gridpos`) is an
untracked test that contradicts the documented requirement and is left for an
owner decision rather than silently changing production behaviour.

> Separately, `tests/test_truncation_detection.py::TestTruncationError::test_error_str_includes_details`
> also fails pre-existing (unrelated `TruncationError.__str__` formatting) — out
> of scope here; noted so the suite baseline is understood.

## Detail

### 1. `test_kaizen_metadata_agent_specs` (12) — spec'd but never implemented

The 12 tests (committed 2026-03-14 in "harden Micro Prime pipeline quality")
verify a `PrimeContractorWorkflow._update_kaizen_metadata_agent_specs(feature, result)`
method described as the **"L3 fix"**: Kaizen's per-feature `metadata.json` is
written at *capture* time with `lead_agent_spec`/`drafter_agent_spec` taken from
`code_generator`, which can still be `"unknown"`/`None` when the agents resolve
lazily during generation. The method patches those fields from the resolved
specs carried on `result.metadata` after generation.

`git log --all -S "def _update_kaizen_metadata_agent_specs"` returns **nothing** —
the method was never committed in any branch. The tests have been red since the
day they landed (a TDD spec whose implementation never followed).

**Resolution — implemented** (`prime_contractor.py`):
- `_update_kaizen_metadata_agent_specs()` — locates `metadata.json` at
  `{prompt_dir}/{KAIZEN_RUN_ID|standalone}/{safe_fid}/metadata.json`, patches only
  `unknown`/`None` specs from `result.metadata` (never clobbers a resolved value →
  idempotent), no-ops when Kaizen disabled / no result metadata / file absent,
  non-fatal on corrupt JSON.
- Wired into `_persist_kaizen_prompts()` (after the metadata write) so it runs at
  all three persistence call sites. Safe no-op when `result.metadata` lacks the
  keys, so it cannot regress existing behaviour.

### 2. `test_complexity_router::test_to_dict` (1) — stale field count

`TaskComplexitySignals.to_dict()` (`complexity/models.py`) returns `asdict(self)`.
The dataclass now has 14 fields; the most recent addition, `has_fillable_elements`
(RUN-007 FR-7), came after the test's last bump (`21163d4c`, 2026-03-19, which set
the count to 13 for `security_sensitive`). The implementation is correct; the
literal `13` was stale. Test updated to `14` and now asserts `has_fillable_elements`
is present.

### 3. `test_pca_p0::test_track_new_field` (1) — stale exact-dict assertion

`_track_onboarding_consumption()` (`context_seed/shared.py`) records
`_generation_profile` into the consumption audit (REQ-GPC-700, defaulting to
`"full"`). The test used an exact-equality assertion that predates that
requirement. Updated to include `"_generation_profile": "full"`. (The sibling
`test_track_multiple_phases` only inspects a sub-key, so it never failed.)

### 4. `test_repair_gridpos::…_skips_when_any_panel_has_group` (1) — untracked, spec-contradicting

The file `tests/unit/validators/test_repair_gridpos.py` is **untracked** (never
committed). The failing case asserts that when any panel carries a `group` field,
`repair_gridpos` should **skip** gridPos injection ("grouped vs flat layouts").

The documented requirement **OBS-710b**
(`docs/design/kaizen/KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md`) states only:
*"If dashboard panels lack `gridPos`, inject default layout."* — with **no**
carve-out for grouped layouts. The current implementation matches the spec; the
untracked test asserts an undocumented behaviour.

**Resolution — none (by design).** Production behaviour was **not** changed to
satisfy an untracked test that contradicts the written requirement. This is an
open decision for the observability-artifact owner:
- **(a)** adopt the group-aware behaviour → first update OBS-710b to specify it,
  then implement the skip and commit the test; or
- **(b)** reject it → delete/repurpose the untracked test.
