# M3 Post-Mortem SDK Fixes & Requirements Audit — 2026-06-03

Covers the SDK changes driven by three `strtd8` M3 codegen post-mortems
(**run-021** Opus, **run-023** Gemini, **gpt-m3** GPT-5.5), the same-class bugs
found while fixing them, and a requirements-vs-implementation audit.

Source post-mortems (in `strtd8/docs/`): `M3_RUN_021_POSTMORTEM.md`,
`M3_RUN_023_POSTMORTEM.md`, `M3_RUN_GPTM3_POSTMORTEM.md`.

Merged to `main` via `fdff5d6c` (commits `272a6117`, `6d5bcc20`) plus the
requirements-closure follow-up (this document's date).

## Fixes by post-mortem finding

| # | Post-mortem | Finding | Fix | Location |
|---|---|---|---|---|
| 1 | run-021 | `TaskEnrichment.get()` crash — stale dict `.get()` after dict→dataclass refactor, only on the domain-validation-failure branch | `.domain.value` | `prime_contractor.py:5031` |
| 2 | run-021 / run-023 | **Semantic stub scored "complete"** — handler simulates work with `sleep()` + canned return, never calls real modules | `check_fake_work_stub` (error) + critical-category gate flips feature to `FAIL:semantic` on a single occurrence + Kaizen hint | `validators/semantic_checks.py`, `forward_manifest_validator.py` (L11), `prime_postmortem.py` |
| 3 | run-021 / gpt-m3 | **Truncation false-positive on tiny files** — 3-line `server.py`, 63-token `__init__.py` flagged truncated | `MIN_LINES_TRUNCATION_BLOCKING` floor in the drafter heuristic block + the integration pre-merge gate | `implementation_engine/drafter.py`, `contractors/integration_engine.py` |
| 4 | gpt-m3 | **`size_regression` sibling-inflation** — a 2-line `__init__.py` measured against a 671-line `service.py` *sibling* (import context) read as a 0.3% regression → truncated → **whole batch aborted** | scope the regression baseline **strictly to the target file(s)**; a new file has no baseline | `implementation_engine/drafter.py:detect_size_regression` |
| 5 | run-023 | **Multi-file concatenation** — `server.py` emitted with `--- app/routers.py ---` separator markers (several files dumped into one) → ast_failure → silently dropped | `detect_multifile_concatenation()` (rejects ≥2 embedded file-path markers; markdown/YAML `---` and single section comments do not trip it), wired into the integration pre-merge gate | `truncation_detection.py`, `contractors/integration_engine.py` |

### Root enabler found while fixing #2 — `ast.Str` (silent poison)

`forward_manifest_validator._count_stubs` (and `copy_detection`) referenced
`ast.Str`, **removed in Python 3.12** (the venv is 3.14). The `prime_postmortem`
caller wraps `validate_disk_compliance` in a broad `except Exception: logger.debug`,
so the `AttributeError` was swallowed and **all disk-quality scoring silently
crashed on every Python file**. That is why run-021 scored exactly 0.75 — the bare
3/4 binary success ratio, *not* a disk-weighted score, which is also why the stub
"passed". Fixed → `ast.Constant` (subsumes the removed aliases).

### Same-class varieties hardened

- **Silent-poison swallows made loud** — three `except Exception: logger.debug`
  handlers wrapping deterministic scoring/validation (`prime_postmortem`,
  `integration_engine` batch score, `repair/orchestrator` semantic-repair
  detection) bumped to `logger.warning(..., exc_info=True)`. Graceful degradation
  is kept, but the next `ast.Str`-style reproducing bug surfaces in Loki instead
  of zeroing scores invisibly.
- **Reviewer "PASS-with-blocking-issues" gate** — `reviewer.py` marked a draft
  `passed` on score + a regex `PASS` while a parsed non-empty **Blocking Issues**
  list was ignored (the same "PASS on a non-working feature" trap). Now requires
  no real blocking issues (`None`/`N/A` placeholders filtered).

## Requirements vs implementation audit

The user's question — *are requirements up-to-date but not implemented, or did
they need updating + got implemented, or both?* — resolves to **both**:

### A. Up-to-date / specified but NOT implemented (gap closed here)

- **`_update_kaizen_metadata_agent_specs` ("L3 fix").** 12 committed tests
  (2026-03-14) fully specified the behaviour; the method was never implemented in
  any branch. **Now implemented + wired** (see
  `PREEXISTING_TEST_FAILURES_2026-06-03.md` §1).
- **`detect_size_regression` sibling-inflation.** The in-code TODO documented the
  gap and claimed it was "not yet observed on Python targets." gpt-m3 *is* that
  observation. **Now implemented** (fix #4); TODO resolved.

### B. Needed updating to reflect what was implemented (docs/spec lag)

- **Truncation handling** — `docs/PATTERN-truncation-detection.md` updated with the
  small-file floor (`MIN_LINES_TRUNCATION_BLOCKING`), target-scoped size-regression,
  and the new concatenation guard. (The `fail_on_heuristic_truncation` flag default
  is unchanged; the post-mortems' "tiny file" symptom is addressed by the floor and
  baseline scoping, not by flipping the flag.)
- **Kaizen semantic checks** — `fake_work_stub` is a new deterministic Python AST
  check beyond the REQ-KZ-001/003 set; recorded here and in the semantic-check
  wiring. Consider adding it to `KAIZEN_PYTHON_REQUIREMENTS.md` on the next reqs pass.

### Stale tests reconciled (code was correct, tests lagged)

`TaskComplexitySignals.to_dict` field count (RUN-007 FR-7 `has_fillable_elements`)
and the onboarding-consumption audit (`REQ-GPC-700` `_generation_profile`) — tests
updated to match the verified-correct implementation.

## Open items (not implemented — larger scope or owner decision)

1. **Continue-on-failure / feature isolation** (gpt-m3 #2): a *leaf* feature's
   hard-fail aborted the whole batch (extract/artifacts/routes/server never ran
   after `__init__.py` failed). Fixing #3/#4 prevents *this* trigger, but the
   batch-abort-on-single-leaf policy is a real gap deserving its own scoped change
   to the prime batch loop.
2. **`routes.py` "complete ≠ works"** (run-023): Gemini imported the real passes but
   defined **no `APIRouter`** and used wrong paths. `check_fake_work_stub` catches
   the sleep-stub shape; "missing expected framework object" needs a contract/
   domain-aware check (high false-positive risk to do generically).
3. **OBS-710b grouped-vs-flat gridPos** — untracked test contradicts the written
   requirement; owner to decide (spec the carve-out + implement, or drop the test).
   See `PREEXISTING_TEST_FAILURES_2026-06-03.md` §4.
4. **App-side** (both post-mortems): mark `server.py` + the router skeleton as
   hand-authored (owned), not codegen tasks, in `strtd8/.../python-plan.md`.

## Tests added

`check_fake_work_stub` (7), tiny-file heuristic skip (1), reviewer blocking gate
(2), size-regression sibling-inflation/target-scoped (2), concatenation detector
true/false-positives (8). Plus the 12 kaizen-metadata tests now pass against the
new implementation.
