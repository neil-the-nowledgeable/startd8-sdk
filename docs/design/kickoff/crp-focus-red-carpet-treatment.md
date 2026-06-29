# CRP Focus — Red Carpet Treatment (R1)

The **Red Carpet Treatment (RCT)** is a new, large milestone: a white-glove **agentic,
build-from-scratch** experience (web + CLI) that orchestrates EXISTING startd8 pieces to populate the
**complete kickoff input surface** (data-model `schema.prisma` contract + assembly manifests + 4 value
inputs + placeholder content) so the deterministic `$0` cascade can run at full capability. It is an
**orchestration layer above** Welcome Mat 2.0 + Concierge. Weight the review toward the highest-risk
architecture below; RCT is "mostly reuse" but the new pieces touch the security boundary.

## Settled boundaries — do NOT re-propose (assume them)

Inherited from Welcome Mat 2.0 / Concierge mode, treated as fixed:
- The agentic **loop never writes** — it proposes; a foreground **human applies at human privilege**
  (web same-origin POST + CSRF + loopback Host + one-time-intent; or CLI/TUI explicit confirm).
- **MCP stays preview/read-only.**
- The deterministic cascade is **bucket-1, `$0`, Python-only**; RCT produces inputs (buckets 1–3),
  never the user's real bucket-4 content.
- **Reuse, don't re-implement** (`concierge/derive`, `manifest_extraction` extractors, the `$0`
  cascade, the `ProposedAction`/`apply_proposal` proposal model, `capture.py`, readiness).

## Where reviewer input matters most

### A. The write-model extension (HIGHEST — this is the security crux)
- **Per-kind apply paths (FR-RCT-9).** RCT adds proposal kinds `schema` / `manifest` / `value-input`
  to the existing `ProposedAction`/`apply_proposal` model (today `friction`/`instantiate`), each routed
  to a different write seam: `schema` → `generate contract --promote`; `manifest` → the new N1
  project-tree writer; `value-input` → `capture.py` per-key merge. **Does adding kinds widen the
  loop's reach?** Can an agent-drafted proposal of a new kind smuggle a write the human didn't intend
  (e.g. a `manifest` proposal whose `dest` escapes `docs/kickoff/inputs/`, or a `schema` proposal that
  promotes without ratification)? How must each kind **re-validate on apply** (grammar/round-trip/
  confinement) so the loop's draft is never trusted blindly?
- **The "loop never writes" invariant under a richer vocabulary.** With many more propose-able kinds,
  what keeps the read-effect floor intact? Should there be a single enumerated allow-list of
  human-apply kinds + a test that the agent registry exposes only read/propose, never apply?

### B. N1 — the project-tree manifest writer (HIGH — the biggest new piece)
- `extract_manifests` is pure/in-memory and round-trip-gated; **no command writes prose→
  `docs/kickoff/inputs/*.yaml` in the project tree today** (only a workflow → run-dir). RCT adds that
  writer over the existing `apply_write_plan` confinement seam. **Path-confinement / overwrite
  semantics:** does it clobber an existing hand-edited manifest? no-clobber vs overwrite-on-confirm?
  zip-slip-style `dest` validation? atomicity across the multi-file write?

### C. The data-model bookend (HIGH)
- **N2 interview → requirements prose brief → `generate contract --promote`.** Is the prose-brief an
  intermediate artifact the human reviews, or ephemeral? Does `--promote` need its own confirm gate
  distinct from the prose-brief confirm (two-step ratification)? What happens on schema *revision* after
  manifests already derive from v1 (drift/regeneration)?

### D. Orchestration & state (MEDIUM)
- **N3 stage-state.** A `.startd8/` cursor over `build_assess`. Resumability, concurrency (two RCT
  sessions / the multi-worktree reality), staleness if the user hand-edits between stages.
- **Cascade-readiness threshold (OQ-7).** What gates the "run the cascade" offer — full surface vs a
  minimal viable subset? Make it testable.
- **Web surface shape (OQ-4).** New `/red-carpet` route vs a stage-rail extension of the existing
  `/concierge/chat` panel + `_ChatStore`. Reviewer's call on the lower-risk reuse.

### E. Cost / observability (MEDIUM)
- The agentic interview is the **one paid surface**; a from-scratch build is many turns. Does the
  inherited budget envelope (FR-WM2-9a: per-session turn/token/cost caps) suffice, or does RCT need a
  whole-build spend ceiling + resumable checkpoints so a long build can't blow budget in one session?

## Build-environment note (real, already in §0)
RCT must branch from **`origin/main`** — the proposal model + web chat live there, not on the primary
worktree. The repo runs concurrent multi-vendor agents; flag any plan step that risks parallel-work
collision.

## Out of scope for this review
- Re-litigating the inherited boundaries above.
- The polyglot LLM-driven path (NR-4) and the Prime/Artisan pipeline (NR-5).
- Authoring real bucket-4 content (NR-1).
