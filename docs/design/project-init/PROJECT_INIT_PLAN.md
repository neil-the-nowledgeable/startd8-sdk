# Deterministic SDK Project-Init — Implementation Plan

**Version:** 0.2 (post-reflection)
**Date:** 2026-07-02
**Tracks:** [PROJECT_INIT_REQUIREMENTS.md](./PROJECT_INIT_REQUIREMENTS.md) v0.2
**Branch:** `feat/project-init-requirements` (worktree off `origin/main`)

> `startd8 project init` is a **thin `$0` orchestrator** composing already-shipped, already-confined
> functions — no new write primitive. The one substantive design decision (FR-5) is settled: it's an
> inbox *producer seam*, never a ground-truth *generator*.

## Architecture

```
startd8 project init [ROOT]  (cli_project.py — under the existing project_app)
        │  delegates to
        ▼
project/init.py  (thin orchestrator, $0, no framework/provider imports)
  ├─ detect_shape(root)          → ProjectShape {greenfield|brownfield_ready|brownfield_partial}
  │     reuses concierge.core.build_survey / build_assess (read-only, $0)
  ├─ establish_postings(root)    → vipp.context.ensure_posting (+ fde opt-in)
  ├─ ready_inbox(root)           → vipp_seam.ensure_inbox_scaffold  (.gitignore + inbox-seq)
  ├─ produce_inbox(root, src)    → vipp_seam.serialize_buffer(ProposalBuffer)   [gated on a real gap]
  └─ report()                    → schema-versioned summary + next command
```

Dependency direction: `project.init` → {`vipp.context`, `fde.context`, `concierge.{core,writes}`,
`kickoff_experience.vipp_seam`, `kickoff_experience.proposals`}. All writes ride
`concierge/safe_write.py:apply_write_plan`.

## Milestones

### M0 — Shape detection + report skeleton (FR-1, FR-2, FR-9)
- `project/init.py`: `ProjectShape` dataclass + `detect_shape(root)` from deterministic signals
  (`prisma/schema.prisma`, `app/`, `docs/kickoff/inputs/*.yaml` count, `.startd8/{vipp,fde}`), folding in
  `concierge.core.build_survey(root)` / `build_assess(root)` (both `$0`, read-only, schema-versioned).
- `run_project_init(...)` returning a schema-versioned summary dict; `cli_project.py` `@project_app.command("init")`
  rendering it via `cli_shared.console`, exit codes 0/2/3 (mirror `cli_vipp.py`).
- **Tests:** greenfield vs brownfield_ready vs brownfield_partial verdicts on fixtures.

### M1 — Postings + inbox-ready (FR-3, FR-4, FR-11)
- **FR-11 refactor first:** extract `vipp_seam.ensure_inbox_scaffold(project_root)` (the `.gitignore` +
  `inbox-seq` init currently inline in `serialize_buffer`); call it from `serialize_buffer` unchanged
  (behavior-preserving) so both paths share one source.
- `establish_postings(root, *, with_fde=False)`: `vipp.context.ensure_posting` always; `fde.context.ensure_posting`
  when `--with-fde`. (No concierge posting — none exists, D4.)
- `ready_inbox(root)`: `ensure_inbox_scaffold` via `apply_write_plan` `ACTION_NEW` (no-clobber → no-op on re-run).
- **Tests:** postings created + idempotent (2nd run `WriteResult.written == []`); FR-11 parity — `serialize_buffer`
  output unchanged after the refactor; `--with-fde` gate.

### M2 — Producer seam (FR-5, FR-12, FR-13, FR-14) — the reframed core
- **Greenfield auto-proposal:** when `shape == greenfield` and `--instantiate`, build
  `ProposedAction("instantiate", {"posture": posture}, id=_new_id())` and `serialize_buffer` it (FR-14 — never
  hand-roll the envelope). Report the posture's `provenance_default` (templated at prototype — the RISK note).
- **`--proposals FILE`:** parse the authored list; **FR-12** — validate each `kind ∈ PROPOSAL_KINDS` + run the
  matching per-kind validator (`validate_posture`/`validate_friction`/`build_capture_plan`) BEFORE serialize;
  bad entry → exit 2, nothing written. Then `serialize_buffer`.
- **FR-13:** a `serialize_buffer` `skipped` (undrained inbox) → exit 0 + "consume the existing inbox first".
- **brownfield_ready + no flag:** produce nothing; report "inbox-ready; nothing to propose" (OQ-4).
- **Tests:** greenfield `--instantiate` → 1-proposal inbox that `vipp negotiate`→`apply` applies end-to-end
  (D14); `--proposals` bad-kind → exit 2, no inbox; undrained → exit 0 skip; brownfield_ready → no inbox file.

### M3 — `--check` + SOTTO (FR-6, FR-7, FR-10)
- `--check`: read-only drift audit (postings present? inbox scaffold present?), exit 0/1/2 (mirror
  `cli_generate.py:47`); reuse `concierge.writes.compute_drift` shape for any instantiated-package check.
- **SOTTO test (FR-6):** a dir that never runs init is byte-identical; `init` twice → 2nd run writes nothing
  (dict-equality), mirroring the `vipp_seam` byte-identical-when-absent test.
- **FR-7:** assert every project-content write goes through `apply_write_plan`; document the `ensure_posting`
  atomic-metadata-write boundary (SDK-owned `.startd8/*-context.json`, not project content).

### M4 — Docs + close #76
- Update the VIPP README + issue #76: `startd8 project init --serialize [--proposals FILE]` / `--instantiate`
  is the supported `$0` non-interactive producer.
- Capability-index entry (`startd8.project.init`); CHANGELOG.

## Risk / sequencing

| Milestone | FRs | Risk |
|-----------|-----|------|
| M0 detect+report | 1,2,9 | low |
| M1 postings+ready | 3,4,11 | low (FR-11 is behavior-preserving — test parity) |
| M2 producer seam | 5,12,13,14 | **medium** — the reframed core; trust-boundary validation (FR-12) is load-bearing |
| M3 check+SOTTO | 6,7,10 | low |
| M4 docs | — | low |

**Traceability:** FR-1..14 each map to a milestone; every milestone traces to ≥1 FR. No open question
blocks M0–M2; OQ-7 (`--proposals` format) is settled at M2 build time; OQ-8/9 are scope decisions.

**RISK (posture semantics):** the greenfield auto-`instantiate` at default `prototype` posture ships
`templated` conventions (`writes.py:56`) — the report must say so, not imply authored conventions.
