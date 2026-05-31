# Lead-Contractor Removal — Contractor Test Regression Inventory

**Filed:** 2026-05-31
**Filed by:** agent:claude-code (multilang-manifest-validation session)
**Owning effort:** Lead-Contractor Removal (see `LEAD_CONTRACTOR_REMOVAL_REQUIREMENTS.md`,
`LEAD_CONTRACTOR_REMOVAL_AUDIT.md`)
**Status:** OPEN — 29 failing tests in `tests/unit/contractors/`

---

## 1. Summary

29 tests in `tests/unit/contractors/` fail because the
`PrimeContractorWorkflow` class is missing methods/attributes that the tests
reference (or that mock-patch targets point at). Every failure traces to the
**same surface the lead-contractor removal owns** — the `PrimeContractor` /
`PrimaryContractor` workflow class and its prompt/manifest helpers — so they are
filed here for that effort to resolve as part of the rename/refactor cleanup.

These are **not** caused by the multilang-manifest-validation work
(commit `ad313dbe` and predecessors). See §4 for attribution evidence.

## 2. Root-cause groups

| # | Symptom (error signature) | Likely cause |
|---|---|---|
| G1 | `AttributeError: type object 'PrimeContractorWorkflow' has no attribute '_get_upstream_contracts'` | Method removed/renamed/relocated off the class |
| G2 | `AttributeError: type object 'PrimeContractorWorkflow' has no attribute '_accumulate_manifest'` | Method removed/renamed/relocated off the class |
| G3 | `AssertionError: Expected '_run_development_phase' to have been called once. Called 0 times.` | Mock patch target moved; development-phase call path changed |
| G4 | `AttributeError: 'PrimeContractorWorkflow' object has no attribute 'edit_min_pct'` | Instance attribute dropped/renamed |
| G5 | `AttributeError: 'PrimeContractorWorkflow' object has no attribute '_security_contract'` | Instance attribute dropped/renamed |
| G6 | `TypeError: 'NoneType' object is not subscriptable` / `AttributeError: 'NoneType' object has no attribute 'get'` (`workflows/builtin/prompts/__init__.py:35`) | Prompt-template lookup returns `None` (missing template key) |
| G7 | `AssertionError: 'development_result_summary' in {...}` | Resume-output structural parity changed |
| G8 | `AssertionError: FeatureStatus.PENDING == FeatureStatus.GENERATED` | Walkthrough-mode status transition changed |

## 3. Full failing-test inventory (29)

### `test_manifest_accumulation.py` (17) — G1/G2
```
TestAccumulatedContractsSection::test_builds_section
TestAccumulatedContractsSection::test_empty_context
TestAccumulatedContractsSection::test_empty_list
TestAccumulatedContractsSection::test_no_language_suffix
TestAccumulatedContractsSection::test_none_upstream
TestAccumulatedContractsSection::test_truncation
TestAccumulateManifest::test_accumulates_dict_manifest
TestAccumulateManifest::test_accumulates_high_score
TestAccumulateManifest::test_exception_is_non_fatal
TestAccumulateManifest::test_skips_low_score
TestAccumulateManifest::test_skips_no_manifest
TestGetUpstreamContracts::test_multiple_deps
TestGetUpstreamContracts::test_name_based_lookup
TestGetUpstreamContracts::test_no_accumulated_manifests
TestGetUpstreamContracts::test_no_deps_empty_list
TestGetUpstreamContracts::test_skips_non_explicit_contracts
TestGetUpstreamContracts::test_upstream_contracts_found
```

### `test_implement_phase_integration.py` (9) — G3/G6/G7
```
TestAllTasksFailedGuard::test_all_tasks_failed_raises_runtime_error
TestAllTasksFailedGuard::test_error_message_includes_task_details
TestAllTasksFailedGuard::test_partial_failure_does_not_raise
TestCacheWriteFailureNonFatal::test_write_failure_is_non_fatal
TestForceImplementBypassesCache::test_force_implement_bypasses_valid_cache
TestResumeCacheExceptionHandling::test_corrupt_binary_cache_falls_through
TestResumeCacheWriteV2::test_roundtrip_write_then_validate
TestResumeCostReporting::test_fresh_run_reports_actual_cost
TestResumeOutputStructuralParity::test_resumed_output_has_development_result_summary
```

### `test_multi_file_edit_fixes.py` (1) — G4/G6
```
TestIntegrationMultiFileDirective::test_integration_prompt_has_multi_file_directive
```

### `test_prime_manifest_wiring.py` (1) — G1
```
TestManifestContextForwarding::test_no_manifest_not_in_gen_context
```

### `test_prime_walkthrough_mode.py` (1) — G4/G8
```
TestWalkthroughDecomposedSkipsIntegration::test_walkthrough_decomposed_skips_integration
```

> Note: `--tb=line` reports more than one error line for some tests, so the
> per-signature histogram in §2 sums to >29; the inventory above is the
> authoritative count (29 distinct tests).

## 4. Attribution evidence (these are NOT from the multilang work)

- **Verified pre-existing at `c32736f9`** (the commit before the multilang merge,
  `REQ-KZ-CS-200`): the `test_manifest_accumulation.py` + `test_prime_manifest_wiring.py`
  subset (18 tests) fails there with the identical `_get_upstream_contracts`
  `AttributeError`. They predate the multilang branch entirely.
- **Unaffected by the multilang fixes:** stashing the six files changed in
  `ad313dbe` and re-running the four primary failing files reproduces the exact
  same 22-failure set — the Bucket A/B/C changes contribute zero of them.
- **No source overlap:** the multilang work touched
  `forward_manifest_validator.py`, `languages/resolution.py`, `languages/csharp.py`,
  `validators/csharp_semantic_checks.py` — none of which define
  `PrimeContractorWorkflow` or its `_get_upstream_contracts` / `_accumulate_manifest` /
  `edit_min_pct` / `_security_contract` members.

## 5. Recommended resolution direction

For each group, decide test-vs-code per the lead-removal NFR-1 (behavior parity)
constraint:

- **G1/G2 (manifest helpers):** confirm whether `_get_upstream_contracts` /
  `_accumulate_manifest` were intentionally relocated (e.g. to a manifest helper
  module or mixin). If so, update the tests to patch/call the new location; if the
  methods were dropped unintentionally during the rename, restore them.
- **G3 (`_run_development_phase` mock):** re-point the mock patch target to the
  current development-phase entry method.
- **G4/G5 (`edit_min_pct`, `_security_contract`):** verify these instance
  attributes still initialize on `PrimeContractorWorkflow`; restore or rename.
- **G6 (`None` prompt template at `prompts/__init__.py:35`):** a template key the
  multi-file / integration prompt path expects is missing — add the template or
  guard the lookup.
- **G7/G8 (resume parity, walkthrough status):** confirm intended behavior under
  the renamed workflow and align test or code.

## 6. Reproduce

```bash
source .venv/bin/activate
python3 -m pytest tests/unit/contractors/ -q -p no:cacheprovider --tb=line \
  -k "manifest or postmortem or integrat or disk or assembler"
# => 29 failed, 647 passed
```
