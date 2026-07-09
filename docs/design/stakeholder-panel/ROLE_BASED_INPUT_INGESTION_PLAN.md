# Role-Based Input Ingestion — Implementation Plan

**Version:** 1.0 (paired with REQUIREMENTS v0.3)
**Date:** 2026-07-09
**Target:** `src/startd8/stakeholder_panel/synthesis_bridge/` + `kickoff_view/models.py` + `cli_panel.py`

> Deterministic, `$0`. Increments are independently landable; each ends green + ruff-clean.

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
