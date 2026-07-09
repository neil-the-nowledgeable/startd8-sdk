# CRP Focus — Role-Based Input Ingestion (reqs v0.4 + plan v1.0)

## Least-reviewed / highest-risk surfaces (spend review budget here)
- **FR-14 — the guarded backlog append** (new WRITE into a project's `ENHANCEMENTS_BACKLOG.md`).
  Pressure-test: idempotency by `<!-- startd8-panel-backlog: <sid> -->` marker (concurrent runs, malformed
  existing marker, marker injected by hostile synthesis text), atomic write (temp+rename, partial-write,
  symlink target), "append-only / never-rewrite" (insertion point when the footer is absent/duplicated),
  preview-default vs `--yes`, fail-closed on missing/unwritable file.
- **FR-12 — the opt-in LLM `input_kind` refinement** (new paid boundary). Pressure-test: bounding/caps,
  enum-validation + out-of-enum discard, fail-open to the deterministic kind, never mutating `lane`/`raw_text`,
  index-alignment of the `{index: kind}` mapping (off-by-one / dropped items), cost-ceiling + missing-key.
- **FR-3/FR-5 — the residual pass + "nothing dropped" coverage invariant.** Is the union-covers-every-line
  invariant well-defined (what counts as "boilerplate"? banner/disclaimer lines, blank lines, sub-bullets)?
  Can residual double-count a line the structured pass already claimed?
- `synthesis_bridge/extract.py` — never CRP'd; the new dual-pass (structured + residual) refactor.

## Settled — do NOT relitigate
- The stakeholder-panel **prototype posture** (shipped #172–174) and its prompts/synthesis structure.
- The **two existing lanes'** meaning (FIELD_LEVEL / NON_DECIDABLE); adding UNSTRUCTURED is decided.
- **$0 deterministic default** as the core; LLM strictly refine-only/opt-in (OQ-3 resolved).
- The **10-kind taxonomy** and `input_kind` naming (OQ-1/OQ-2 resolved) — challenge assignment logic, not the enum.
- Bucket separation: **no content generation** (NR-1) — challenge whether any FR violates it, not the rule.

## Cross-repo / integration notes
- `KickoffTranscript` (Pydantic, `kickoff_view/models.py`) gains `posture` (FR-8) — check downstream loaders.
- The `TriageReport` schema grows (`UNSTRUCTURED` lane, `input_kind`, kind counts) — additive; flag any strict
  external consumer.
