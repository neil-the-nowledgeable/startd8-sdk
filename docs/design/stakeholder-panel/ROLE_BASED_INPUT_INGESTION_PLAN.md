# Role-Based Input Ingestion — Implementation Plan

**Version:** 1.1 (paired with REQUIREMENTS v0.5; CRP-hardened)
**Date:** 2026-07-09
**Target:** `src/startd8/stakeholder_panel/synthesis_bridge/` + `kickoff_view/models.py` + `cli_panel.py`

> Deterministic, `$0`. Increments are independently landable; each ends green + ruff-clean.
> **CRP-hardened:** each milestone implements the REQUIREMENTS §2.1 refinements (H-1…H-21). The
> load-bearing ones per milestone: M2 → H-1 (residual on raw stream), H-4, H-6; M3 → H-7, H-8;
> M4 → H-12; M6 → H-16..H-21; M7 → H-13..H-15; M8 → H-2/H-3 (normalized + disjoint coverage).

## Sequencing (dependency order)

```
M1 models         (Lane.UNSTRUCTURED, InputKind[10], Candidate.input_kind)   ← foundation
M2 extract        (FR-1 vocab, FR-2 format, FR-3 residual pass)
M3 classify       (FR-4 input_kind assignment; residual + decision/constraint heuristics)
M4 report         (FR-11 residual+kind sections/counts)
M5 posture        (FR-8 KickoffTranscript.posture, FR-9 health note, FR-10)
M6 backlog        (FR-6 render_backlog_section, FR-7 CLI + FR-14 guarded append)
M7 LLM Tier-2     (FR-12 opt-in --llm-kind refine — IN SCOPE per OQ-3)
M8 guards         (FR-13 coverage/regression/golden/mapping + append-idempotency + LLM-refine tests)
```

## Per-milestone

### M1 — models (`synthesis_bridge/models.py`)
- `Lane`: add `UNSTRUCTURED = "UNSTRUCTURED"`. `counts()` auto-includes it (iterates `Lane`).
- New `class InputKind(str, Enum)` (10): recommendation/suggestion/question/risk/tension/feedback/content/**decision**/**constraint**/uncategorized.
- `Candidate`: add `input_kind: InputKind = InputKind.uncategorized`; thread into `to_dict()`.
- `TriageReport.counts()` add a `by_kind` sub-count (or a sibling `kind_counts()`).
- **Risk:** `to_dict()["kind"]` already = report-type label → the per-candidate field MUST be `input_kind` (not `kind`). Guard: grep no `["kind"]` collision.

### M2 — extract (`extract.py`)
- FR-1: extend `_SECTION_PREFIXES` with `"prioritized ux"/"ux improvement" → "UX Improvements"`,
  `"quick win" → "Quick Wins"`, `"bigger bet" → "Bigger Bets"`.
- FR-2: add a `_BOLD_LEAD_RE = ^\s*\*\*(.+?)\*\*` capture inside a known section (dedupe vs numbered/bullet);
  strip the trailing `**`.
- FR-3 residual pass: track claimed line-indices during the structured pass; a second sweep emits an
  `UNSTRUCTURED` Candidate (source_section = the heading it fell under, or `"(unsectioned)"`) for each
  unclaimed non-boilerplate line/para (skip: blank, `## `-only headings already consumed, table separators,
  the banner/disclaimer lines, <8 chars). Set `lane=UNSTRUCTURED` at construction; classify refines kind.
- **Design:** refactor the single-pass loop into `extract_structured()` + `extract_residual(text, claimed)`;
  `extract_candidates` = union. Keeps the structured path byte-identical for existing fixtures.

### M3 — classify (`classify.py`)
- FR-4: `_KIND_BY_SECTION` map (Recommendations→recommendation, Open Questions→question, Risk Register→risk,
  Tensions→tension, UX Improvements/Quick Wins/Bigger Bets→suggestion). Apply to every candidate.
- Residual heuristic `_infer_kind(text)` (ordered): trailing `?`→question; `must|never|cannot|only|limit|required`→constraint; `decided|will|chosen|ratified|agreed`→decision; `suggest|recommend|should|could|consider`→suggestion; else content. Never returns None (→ uncategorized).
- Preserve existing lane logic; UNSTRUCTURED items stay UNSTRUCTURED (never promoted to FIELD_LEVEL — NR-2),
  but still get a `reason`/`suggested_owner` (`"unstructured — preserved for a human"`, owner `human / requirements`).

### M4 — report (`models.py::to_markdown`/`to_dict`)
- Add `## UNSTRUCTURED (preserved — received but not previously accounted for)` section listing verbatim items + input_kind.
- Add per-`input_kind` count line to the Counts header. `to_dict` gains `kind_counts` + `input_kind` per candidate.

### M5 — posture (`kickoff_view/models.py`, `route.py`, `classify.py`)
- FR-8: `KickoffTranscript`: add `posture: str = "scrutiny"` (Pydantic maps the JSON key; default covers old transcripts).
- FR-9: `build_triage` passes `posture` into `health_check`; add the prototype backlog-bound note.
- FR-10: scrutiny path unchanged (default posture → no new health note; residual/kind additive only).

### M6 — backlog + guarded append (`synthesis_bridge/backlog.py` new, `cli_panel.py`)
- FR-6: `render_backlog_section(report, *, title, project) -> str` — pure, consumes the `TriageReport`; groups by
  section/kind; SYNTHETIC & UNRATIFIED banner; open tensions/questions as decisions. Byte-stable output.
- FR-7: `kickoff panel backlog <session> [--project] [--json] [--out FILE] [--append FILE] [--yes]`.
- FR-14 guarded append (`_append_backlog_section(path, section, session_id)`):
  - **idempotent** — wrap the rendered section in `<!-- startd8-panel-backlog: <sid> --> … <!-- /startd8-panel-backlog: <sid> -->`; on re-run, replace ONLY the bytes between the matching markers (regex on the sid); absent → insert.
  - **append-only / never-rewrite** — insert before the doc's closing `*italic footer*` if present, else EOF; never touch other bytes (diff must be a single contiguous insertion/replacement).
  - **preview-default** — without `--yes`, print the unified diff and exit 0 (no write); `--append … --yes` writes atomically (temp+rename).
  - **fail-closed** — target must be an existing writable file; else error (never create the canonical doc).

### M7 — LLM Tier-2 (`synthesis_bridge/kind_llm.py` new; `extract_llm.py` precedent)
- FR-12: opt-in `--llm-kind [--model …]`. Batches UNSTRUCTURED (+ `content`/`uncategorized`) candidates into one
  bounded prompt → returns `{index: input_kind}`; validate each against the 10-enum, discard out-of-enum (keep
  deterministic). Never touches `lane`/`raw_text`. Fail-open: any error → deterministic result + a health note.
  Budget-guarded (cheap model default; cap N items/call).

### M8 — guards (`tests/unit/stakeholder_panel/`)
- `test_synthesis_bridge_residual.py`: FR-5 coverage invariant (union of lanes' verbatim text ⊇ non-boilerplate
  lines) on **prototype** + **scrutiny** fixtures; the "7 Open Questions only" regression now surfaces
  UX/Quick Wins/Bigger Bets + typed tensions; the 10-kind mapping table (section + heuristic incl.
  decision/constraint); scrutiny golden additive-only.
- `test_backlog_append.py`: preview-default (no write) → diff; `--yes` writes; **re-run is idempotent** (byte-equal,
  no dup block); append-only (surrounding bytes unchanged); fail-closed on missing file.
- `test_kind_llm.py`: `$0` stub agent refines a residual item's kind; out-of-enum discarded; missing-key/error →
  deterministic fallback + health note; lane/raw_text never mutated.
- Update existing triage tests for the new `counts()` keys / report sections.

## Backward-compat / risk register
- **Transcript schema:** `Candidate.to_dict` + `TriageReport.to_dict` gain keys → update any exact-shape tests;
  additive for external consumers.
- **`counts()` keys** grow by `UNSTRUCTURED` → update assertions.
- **Extraction of previously-dropped content in scrutiny** is a (desired) behavior change → golden re-baseline
  with an explicit note; guard that structured (numbered/bullet) items are byte-identical.
- **`input_kind` naming** must not collide with the report `["kind"]`.

## Definition of done
- All FRs mapped; FR-13 guards green; ruff clean; scrutiny golden additive-only; the household prototype
  synthesis fixture triages with 0 dropped lines and non-empty UX/Quick Wins/Bigger Bets/Tensions.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

> All 15 R1+R2 S-suggestions ACCEPTED. The normative refinements live in REQUIREMENTS §2.1 (H-1…H-21);
> the milestones below are updated to implement them (see the "CRP-hardened plan deltas" note).

| ID | Merged as (REQ §2.1) | Milestone delta | Date |
|----|----------------------|-----------------|------|
| R1-S1 | H-10 | M5: `health_check(*, posture="scrutiny")`; `build_triage` threads `getattr(t,"posture","scrutiny")` | 2026-07-09 |
| R1-S2 | H-12 | M4: update the hardcoded Counts f-string (`models.py:86`) to render UNSTRUCTURED + kind summary | 2026-07-09 |
| R1-S3 | H-4 | M2: claimed-index tracking covers the Risk-Register table sub-loop (data rows claimed; header/sep boilerplate) | 2026-07-09 |
| R1-S4 | H-13 | M7: `{index:kind}` = subset position; discard missing/oob/dup | 2026-07-09 |
| R1-S5 | H-2/H-3 | M8: coverage test `_clean()`-normalized + disjointness assertion | 2026-07-09 |
| R1-S6 | H-16/H-18 | M6: marker-injection assert + unclosed/dup opener fail-closed | 2026-07-09 |
| R1-S7 | H-14 | M7: numeric bounds as config+CLI help; M8 asserts skip/abort | 2026-07-09 |
| R1-S8 | H-20 | M8: byte-stability golden for `render_backlog_section` (sorted grouping) | 2026-07-09 |
| R2-S1 | H-1 | M2: `extract_residual` iterates `splitlines()` independently of the section gate | 2026-07-09 |
| R2-S2 | H-6 | M2: bold-lead title = full bold span, not split on `—`/`.` | 2026-07-09 |
| R2-S3 | H-8 | M3: add `_SECTION_ROUTING` entries for UX/Quick Wins/Bigger Bets | 2026-07-09 |
| R2-S4 | H-7 | M3: `_infer_kind` word-boundary regex + pinned precedence | 2026-07-09 |
| R2-S5 | H-19 | M6: same-dir temp / symlink handling / mode preservation | 2026-07-09 |
| R2-S6 | H-12 | M1/M4: mandate `kind_counts()` sibling; `counts()` stays all-int | 2026-07-09 |
| R2-S7 | H-21 | M6: preview exit-code 0=in-sync / 2=would-write | 2026-07-09 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | Both rounds code-anchored and non-redundant; nothing rejected. | 2026-07-09 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-09 18:30:00 UTC
- **Scope**: Plan sequencing/interfaces/validation for M2 extract dual-pass, M4 report, M5 posture wiring, M6 guarded append, M7 LLM refine, M8 guards. Anchored against `synthesis_bridge/{extract,classify,models,route}.py`.

##### Executive summary (top risks / gaps)

- M5 wires `posture` into `health_check`, but `health_check` (classify.py:76) is keyword-only `synthesis_text/context_summary/default_context` — **no `posture` param exists**; the plan doesn't state the signature change or how `build_triage` (route.py:35-38, pure `getattr` duck-typing) reads it.
- M4 hardcodes the Counts line (`models.py:86-87` prints only `FIELD_LEVEL`/`NON_DECIDABLE`); adding UNSTRUCTURED to `counts()` won't surface in `to_markdown` unless that f-string is also edited — plan says "add per-kind count line" but not "update the lane count line."
- M2's residual pass must reconcile with the **Risk-Register table branch** (extract.py:87-99), which `continue`s on header/separator rows — those consumed-but-not-appended rows are a double-count/leak trap not addressed by "skip table separators."
- M6 idempotency regex is vulnerable to marker sequences inside verbatim residual text (mirror of R1-F1) and to malformed/duplicate markers (R1-F5).
- M7's `{index: kind}` map lacks an index-alignment contract (mirror of R1-F3).
- M8 coverage test compares "verbatim" text but M2 stores `_clean()`-normalized `raw_text` — the invariant test will be flaky without normalization (mirror of R1-F4).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | M5: specify the `health_check` signature change — it currently takes only `synthesis_text/context_summary/default_context` (classify.py:76); add `posture: str = "scrutiny"` (keyword-only) and state that `build_triage` reads `getattr(transcript, "posture", "scrutiny")` and threads it, so the prototype note has somewhere to attach. | Plan says "build_triage passes posture into health_check" but the callee has no such param and route.py never reads posture; without the signature delta the FR-9 note has no home. | M5 bullet 2 | Unit test: prototype transcript → health list contains the backlog-bound note; scrutiny transcript → does not (FR-10). |
| R1-S2 | Data | high | M4: add an explicit step to **update the hardcoded Counts f-string** in `to_markdown` (models.py:86-87) to render the UNSTRUCTURED lane count and the per-kind summary; note that `counts()` auto-growing does not change the rendered line. | The report's Counts header is a literal f-string referencing only two lanes; a new lane silently won't appear despite `counts()` including it. | M4 bullet 2 | Golden test on `to_markdown` for a report with ≥1 UNSTRUCTURED item asserts the count is rendered. |
| R1-S3 | Data | high | M2: define how the residual pass treats the **Risk-Register table branch** — header/separator rows and the appended-risk rows are handled in a dedicated loop (extract.py:87-99) that `continue`s; the claimed-index tracking must mark the *risk data rows* as claimed and the *header/separator* rows as boilerplate, or residual will re-emit table scaffolding or double-count risks. | The single-pass loop has a table sub-state machine; "track claimed line-indices" must cover this branch explicitly or the coverage/disjointness invariants break on any scrutiny synthesis with a Risk Register. | M2 FR-3 bullet | Test: scrutiny fixture with a Risk Register → residual emits 0 table rows; risks appear once (structured), not twice. |
| R1-S4 | Interfaces | high | M7: pin the `{index: kind}` contract in the plan — index is 0-based position in the passed subset (order-preserved); discard missing/out-of-range/duplicate keys (fall back to deterministic), separate from the out-of-enum-value discard already noted. | The plan only discards out-of-enum *values*; index drift silently re-types the wrong candidate. | M7 bullet | Test: stub map with a missing/out-of-range/duplicate index → each affected candidate keeps its deterministic kind, no collateral mutation. |
| R1-S5 | Validation | high | M8: make the coverage test **normalization-aware** — compare `_clean()`-normalized structured `raw_text` against `_clean()`-normalized source lines (extract.py:45 strips `*_`/backticks), and add a bidirectional disjointness assertion (structured-claimed ∩ residual-claimed = ∅). | A raw-substring union test will mis-report bold/backtick lines as dropped and won't catch double-counts; both are the focus-file FR-5 asks. | M8 `test_synthesis_bridge_residual.py` bullet | Test with a bold-lead + backtick fixture line asserts covered exactly once. |
| R1-S6 | Security | medium | M6: harden `_append_backlog_section` against marker injection and malformed markers — assert the rendered section contains no `startd8-panel-backlog` marker substring before writing (fail-closed or escape), and refuse (with diagnostic) when the target has an unclosed or duplicated opener for the sid. | The idempotency regex trusts marker well-formedness and trusts the rendered body not to contain markers; verbatim residual (FR-3) can carry either. | M6 FR-14 idempotent/fail-closed bullets | Tests mirror R1-F1/R1-F5: injected marker + unclosed opener both fail closed; happy-path re-run byte-idempotent. |
| R1-S7 | Ops | medium | M7: state numeric bounds as config with defaults (max items/call, max items/run, cost ceiling that aborts) and surface them in the CLI help, so M8 can assert them; today "bounded" is prose. | Untestable bound = no guard; focus file flags cost-ceiling/caps as a risk. | M7 bullet + M8 `test_kind_llm.py` | Test asserts skip past N items and abort-to-deterministic over ceiling. |
| R1-S8 | Validation | medium | M6: add a **byte-stability / idempotency golden** for `render_backlog_section` itself (not just the append), since FR-6 claims "byte-stable output" and the append idempotency depends on the rendered block being identical across runs for the same report. | If ordering (e.g. dict iteration of `by_kind`) is nondeterministic, the marked block differs run-to-run and the "replace only that block" idempotency produces spurious diffs. | M8 (new test) | Render twice from the same report → byte-equal; assert grouping order is sorted/stable. |

##### Endorsements / Disagreements

**Endorsements:** none — Appendix C was empty at R1.
**Disagreements:** none.

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-09 19:10:00 UTC
- **Scope**: Adversarial pass over the plan's implementation mechanics. Re-grounded in `synthesis_bridge/{extract,classify,models,route}.py`. Attacks M2's dual-pass refactor (unknown-section gate, `_title_of` split), M3 heuristic matching + missing `_SECTION_ROUTING` entries for new sections, M6 atomic-write/symlink, and M4's `counts()` return-shape break. Does NOT re-propose R1-S1..S8; endorsements below.

### Stress-test / adversarial pass

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | M2: the `extract_residual(text, claimed)` sweep must run on the **raw line stream**, not inherit the structured loop's `if not section: continue` gate (extract.py:83-84) — otherwise lines under unrecognized `## ` headings never reach the body and residual captures nothing new under unknown headings (the FR-3 target). State that residual iterates `text.splitlines()` independently and only excludes lines in the `claimed` set + the boilerplate set. | The plan's "refactor the single-pass loop into `extract_structured()` + `extract_residual()`" risks copying the section gate; if it does, the headline unknown-heading case is silently a no-op. | M2 "Design" bullet | Fixture with an unknown `## Parking Lot` heading + 3 lines → assert 3 UNSTRUCTURED candidates. |
| R2-S2 | Data | medium | M2: state that `_title_of` (extract.py:52-59) must not split bold-lead titles on `—` — FR-2's `**Label — …**` format collides with `re.split(r"[:—.]", text)`, truncating the title at the em-dash. Either special-case bold-lead (title = the bold span) or drop `—`/`.` from the title split for these items. | M2 adds `_BOLD_LEAD_RE` and "strip the trailing `**`" but reuses `_title_of`; the derived label for `**T1 — X OPEN**` becomes `T1`. | M2 FR-2 bullet | Test: bold-lead item title is the full bold span, not truncated at `—`. |
| R2-S3 | Data | medium | M3: extend `_SECTION_ROUTING` (classify.py:24-29) — it currently has NO entry for `UX Improvements`/`Quick Wins`/`Bigger Bets`, so those NON_DECIDABLE items fall to the generic default `("not reducible to a single field value","human")`. The plan adds `_KIND_BY_SECTION` for `input_kind` but leaves the lane reason/owner generic; add routing entries (e.g. reason "design recommendation → requirements backlog", owner "requirements-build"). | Without this, the differentiating prototype sections get a lane-`reason` that reads as a failure ("not reducible to a single field value") rather than "design work for the backlog" — undercutting FR-9's backlog framing. | M3 (new bullet) | Test: a UX-Improvements candidate's `reason`/`suggested_owner` are the design/backlog values, not the generic default. |
| R2-S4 | Validation | medium | M3: pin `_infer_kind` matching to **word boundaries** and document precedence — bare substrings `only`/`limit`/`will`/`agreed` match inside `commonly`/`unlimited`/`willing`/`disagreed`, and `required` (constraint) precedes `should` (suggestion) so "should be required" mis-types. Use `re.search(r"\b(must|never|…)\b", …)`. | The plan lists the heuristic as ordered `|`-alternations implying substring `in`/regex without `\b`; deterministic mis-typing is baked in and then "refined" by the LLM, masking it. | M3 `_infer_kind` bullet | Table test: the four false-positive strings map to the intended kind. |
| R2-S5 | Security | high | M6: specify atomic-write mechanics — create the temp file **in the target's directory** (same fs → `os.replace` is atomic, no cross-device `OSError`); if the target is a **symlink**, resolve-and-replace-target or fail closed (never clobber the link with a regular file); preserve target mode across rename. | The plan says "writes atomically (temp+rename)" with no dir/symlink/mode contract; a symlinked backlog or a `TMPDIR` on another mount breaks atomicity or loses the link — the focus file explicitly lists "symlink target" + "partial-write". | M6 FR-14 preview-default/atomic bullet | Tests: symlinked target (defined behavior), forced cross-device temp (same-dir used), mode preserved. |
| R2-S6 | Data | medium | M4: mandate the per-kind counts as a **separate accessor** (`kind_counts()` / `to_dict["kind_counts"]`), not nested inside `counts()` — `counts()` (models.py:61-66) returns `Dict[str,int]`; embedding a `by_kind` dict makes its values heterogeneous and breaks `sum(counts().values())` / all-int assertions. M1's "or a sibling" should be the committed choice. | The backward-compat register (line 89) only flags new *keys* in `counts()`; a nested non-int value is a shape break, not an additive key. | M1 `counts()` bullet + M4 | Test: `counts()` values all int (incl. new `UNSTRUCTURED`); kind breakdown via the sibling accessor. |
| R2-S7 | Ops | low | M6: define the preview **exit code** — FR-7 default (stdout, `$0`) and `--append` preview both "exit 0", but a `polish check`-style "would-change" nonzero would let CI gate on pending backlog drift. State the chosen contract (0 always, or 0=in-sync / N=would-write) so M8 can assert it. | The plan says preview "exit 0 (no write)" for `--append`; whether an operator/CI can distinguish "nothing to do" from "a write is pending" is unspecified. | M6 preview-default bullet | Test: preview with a pending change vs an already-idempotent target → assert the exit-code contract. |

##### Endorsements / Disagreements

**Endorsements** (prior untriaged R1 items this reviewer strongly agrees with):
- R1-S1 (health_check `posture` signature): verified — `health_check` (classify.py:76) is keyword-only with no `posture` param and `build_triage` (route.py:35-38) never reads posture; the signature delta is mandatory or FR-9 has no attach point.
- R1-S2 (update the hardcoded Counts f-string): confirmed — `to_markdown` (models.py:86-87) prints only FIELD_LEVEL/NON_DECIDABLE; a growing `counts()` won't surface without editing that literal.
- R1-S3 (Risk-Register table branch claimed-index handling): the table sub-state-machine (extract.py:87-99) is a real double-count/leak trap; strongly endorse.
- R1-S5 (normalization-aware + disjoint coverage test) and R1-S6 (marker-injection/malformed-marker hardening): both correct against the code; endorse.

**Disagreements:** none.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirements FR → plan milestone → coverage.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (section vocabulary) | M2 (`_SECTION_PREFIXES` additions) | Full | — |
| FR-2 (item-format / bold-lead) | M2 (`_BOLD_LEAD_RE`) | Partial | Dedup vs numbered/bullet stated; interaction with `_title_of` em-dash split (extract.py:52-59) on `**T1 — …**` not addressed. |
| FR-3 (residual lane) | M1, M2 (dual-pass) | Partial | "Boilerplate" set only informal in M2; Risk-Register table branch claimed-index handling unspecified (R1-S3). |
| FR-4 (`input_kind` typing) | M1, M3 (`_KIND_BY_SECTION`, `_infer_kind`) | Full | — |
| FR-5 (nothing-dropped, verified) | M8 coverage test | Partial | Verbatim-vs-`_clean()` normalization mismatch (R1-S5/R1-F4); disjointness (no double-count) not asserted (R1-F7). |
| FR-6 (render_backlog_section) | M6 | Partial | "Byte-stable output" claimed but grouping-order determinism not pinned (R1-S8). |
| FR-7 (CLI + guarded append) | M6 | Full | — |
| FR-8 (posture on transcript) | M5 | Partial | Additive-load safety vs `extra="allow"` model + downstream exact-shape consumers not called out (R1-F8). |
| FR-9 (posture-aware health) | M5 | Partial | `health_check` has no `posture` param; signature change unstated (R1-S1). |
| FR-10 (scrutiny unchanged) | M5, M8 (golden additive-only) | Full | — |
| FR-11 (report surfaces residual+kind) | M4 | Partial | Hardcoded Counts f-string (models.py:86-87) not updated for UNSTRUCTURED lane (R1-S2). |
| FR-12 (LLM Tier-2 refine) | M7 | Partial | `{index: kind}` alignment + missing/dup-key discard (R1-S4/R1-F3); numeric cost/count bounds (R1-S7/R1-F6). |
| FR-13 (completeness + compat guards) | M8 | Partial | Coverage-test normalization + disjointness (R1-S5); marker-injection/malformed-marker cases (R1-S6). |
| FR-14 (write-safety) | M6 | Partial | Marker injection (R1-F1), footer/insertion determinism (R1-F2), malformed/dup-marker + concurrency (R1-F5). |

## Requirements Coverage Matrix — R2

Deltas vs R1 only (R2 is an adversarial pass; unlisted rows are unchanged from R1). Analysis only.

| Requirement | Plan Step(s) | Coverage | New R2 gap (adds to R1) |
| ---- | ---- | ---- | ---- |
| FR-2 (item-format / bold-lead) | M2 (`_BOLD_LEAD_RE`) | Partial | `_title_of` em-dash split truncates the new bold-lead title (R2-S2/R2-F2) — previously only noted in R1's matrix, now an actionable item. |
| FR-3 (residual lane) | M1, M2 (dual-pass) | Partial | Unknown-heading content is skipped by `if not section: continue` (extract.py:83) before the body — the dual-pass sweep must bypass that gate (R2-S1/R2-F1). |
| FR-4 (`input_kind` typing) | M1, M3 | Partial | `_infer_kind` substring vs word-boundary matching + precedence unspecified → deterministic mis-typing (R2-S4/R2-F3); new sections lack `_SECTION_ROUTING` reason/owner entries (R2-S3). |
| FR-9 (posture-aware health) | M5 | Partial | Health note asserts a routing fact `classify` can violate (FIELD_LEVEL still fires) — FR-9/NR-2/code contradiction (R2-F4). |
| FR-11 (report surfaces residual+kind) | M4 | Partial | Per-kind counts must be a separate accessor, not nested in all-int `counts()` (shape break) (R2-S6/R2-F6); empty/zero-candidate report shape undefined (R2-F7). |
| FR-14 (write-safety) | M6 | Partial | Atomic-write symlink/cross-device/temp-dir/mode contract missing (R2-S5/R2-F5); preview exit-code contract unspecified (R2-S7). |
