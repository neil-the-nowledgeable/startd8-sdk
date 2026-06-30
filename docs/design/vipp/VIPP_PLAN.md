# VIPP Implementation Plan

**Version:** 0.3 (CRP R1 triaged)
**Date:** 2026-06-30
**Tracks:** [VIPP_REQUIREMENTS.md](./VIPP_REQUIREMENTS.md) v0.3
**Branch:** `feat/vipp-project-counterpart` (worktree off `origin/main`)

> Built bottom-up: contracts → ground-truth consumption → negotiation brain → the host-side
> serialization seam (riskiest) → applier → CLI. Each milestone is independently testable and traces
> to FRs. Deterministic-first throughout; LLM is opt-in and confined to narrative (FDE parity).

---

## Architecture at a glance

```
HOST PROCESS (Concierge / Red Carpet chat)          PROJECT PROCESS (VIPP)
  ProposalBuffer (in-memory, session)                 vipp/assistant.py (brain)
        │ FR-15 serialize (opt-in)                          │ FR-7 consume
        ▼                                                   ▼
  .startd8/vipp/proposals-inbox.json  ──read──►  oracle_for_project / FrictionReport
        ▲                                                   │ FR-4 evaluate → label (FR-6)
        │ FR-16 human confirm                               ▼
  apply_proposal (proposals.py:217)  ◄──apply──  .startd8/vipp/dispositions.json
   closed kinds (proposals.py:41)                  (ACCEPT/REJECT/COUNTER)
```

Dependency direction (FR-8): `vipp` → {`fde`, `sapper`, `kickoff_experience`} contracts, **never the
reverse**. Graceful degradation via availability flags.

---

## M0 — Package skeleton + contracts (FR-1, FR-2, FR-3, FR-6, FR-13)

- **New package `src/startd8/vipp/`** (mirror `fde/`): `__init__.py`, `models.py`, `assistant.py`,
  `context.py`, `host_bridge.py`, `ground_truth.py`, `compose.py`, `redaction.py`, `notify.py`.
- **`vipp/models.py`** — frozen-dataclass contracts mirroring `fde/models.py`:
  - `PROTOCOL_VERSION = "1.0"` (independent of SDK version — FR-13).
  - `ProposalEnvelope` (the FR-15 serialized inbox shape): `protocol_version`, `generated_at`,
    `project_id`, `proposals: List[EnvelopedProposal]`. `EnvelopedProposal` mirrors
    `ProposedAction` fields (`kind`, `params`, `id`, `base_sha`) **by dict shape, not by importing
    the peer type** (FR-8 / atomic-patch discipline).
  - `VippDisposition`: `proposal_id`, `decision ∈ {ACCEPT,REJECT,COUNTER}`, `reason`,
    `counter_params: Optional[dict]`, `claims: List[LabeledClaim]` (reuse `fde.models.LabeledClaim`).
  - `VippReport`: `generated_at`, `sdk_version`, `dispositions`, `evidence_available`, `cost_usd`,
    `llm_used`, `protocol_version`; `to_dict`/`from_json`/`to_prompt_section`/`to_markdown`.
  - Reuse `fde.models.ClaimLabel`/`LabeledClaim` directly (FR-6) — import from `startd8.fde.models`.
- **Tests:** `tests/unit/vipp/test_models_and_labeling.py` — JSON-canonical round-trip
  (`from_json(to_dict)` identity), markdown is derived/lossy (no `from_markdown`), every claim
  label-gated, `PROTOCOL_VERSION` decoupled from SDK version.

## M1 — Ground-truth consumption (FR-7, FR-8) — **two distinct inputs [v0.3]**

_[v0.3 — A-F1/S1/S2: the oracle and the FrictionReport are unrelated interfaces; "consume" understated
the work. Split into two functions; one is net-new code.]_
- **`vipp/ground_truth.py`:**
  - `observed_from_report(report) -> List[LabeledClaim]` — thin wrapper over
    `sapper.fde_bridge.to_observed_claims` (consumes an on-disk `sapper-friction-report.json`).
  - `observed_from_oracle(oracle, questions) -> List[LabeledClaim]` — **NET-NEW adapter**: build
    `GroundTruthQuestion`s, call `oracle.answer(...)` (`oracle_for_project` returns a `GroundTruthQuery`,
    not claims), and map `GroundTruthAnswer`(VALIDATED/REFUTED/OMIT) → `LabeledClaim(OBSERVED)`. OMIT →
    no claim (FR-4 default handles it); never fabricate (Lesson L10-#41 incomplete-vs-incorrect).
  - `SAPPER_AVAILABLE` guard → degrade narrative only; do **not** invent OBSERVED claims.
- **Tests:** `test_ground_truth.py` — `observed_from_report` asserts OBSERVED + `claim_id==fingerprint`;
  `observed_from_oracle` asserts answer→claim mapping incl. OMIT-yields-nothing; graceful degradation.

## M2 — Negotiation brain (FR-3, FR-4, FR-6) — deterministic-first

- **`vipp/context.py`** — copy the FDE posting/idempotency skeleton: `ensure_posting(project_root,
  sdk_version)` creates `.startd8/vipp/` + `vipp-context.json`; `fingerprint(parts)` +
  `already_processed`/`record_processed` over consumed-artifact checksums (reuse the helpers'
  shape from `fde/context.py:31-153`). Exclude VIPP's own outbox from the fingerprint (FDE's
  `checksum_json_excluding` trick, `assistant.py:74-76`).
- **`vipp/assistant.py`** — `run_vipp_negotiate(inbox_path, *, project_root=None, narrative=False,
  max_cost_usd=None, emit=True, write=True, force=False) -> NegotiateOutcome` (shape mirrors
  `run_fde_explain`, `assistant.py:49`):
  1. resolve root + sdk_version; `ensure_posting`.
  2. fingerprint via `checksum_json_excluding` — **exclude `generated_at` + `envelope_seq`** so a
     re-serialize of unchanged proposals is a no-op (B-S1/A-S3); ground-truth key = `checksum_file` of
     `sapper-friction-report.json` + `checksum_glob` of `prisma/schema.prisma`/corpus (A-S3), not an
     abstract hash. Exclude VIPP's own `dispositions.json` write-back (Lesson L16-#8).
  3. **deterministic core** `vipp/evaluate.py:evaluate_envelope(envelope, oracle, *,
     observed_claims=None, extract=...) -> List[VippDisposition]` _[v0.3 — A-S2: pass the queryable
     **oracle**, not only a precomputed list; adjudicating a `schema`/`manifest` entity requires
     querying it.]_ Per-kind rule coverage is honest: `capture` (structured `value_path` vs
     `allowed_value_paths()`/oracle) and `schema`/`manifest` **after** prose→entity extraction
     (`build_entity_graph`/`extract_manifests`) have teeth; `instantiate`/`friction`/`brief` have no
     entity → OMIT-default ACCEPT (FR-4). Malformed proposal → REJECT, never crash (L13-#103).
  4. render markdown via `compose.render_dispositions`; gate with `assert_all_labeled`.
  5. **opt-in narrative**: `if narrative:` lazy-import `compose.enhance_narrative` — **first** pass
     inbox prose through `security.normalize_untrusted_text` + `<context>` (FR-9, R3-S5); re-gate.
  6. `if write:` write `dispositions.json` (canonical) + `.md`; `record_processed`. `if emit:` notify.
- **Tests:** `test_negotiate.py` — deterministic dispositions (accept/reject/counter/OMIT-default);
  re-serialize with new `generated_at`/`seq` but same proposals ⇒ `skipped=True`; malformed→REJECT;
  narrative opt-in, label-gated, **inbox prose fenced**; `$0` when `narrative=False`.

## M3 — Host-side serialization seam (FR-15, FR-17, FR-18, NR-7) — **riskiest; CRP R1 done**

- **`kickoff_experience/proposals.py`** (host side, additive): `serialize_buffer(buffer,
  project_root) -> WriteResult` writes the bounded pending list to `.startd8/vipp/proposals-inbox.json`
  via `safe_write.apply_write_plan`. **Key whitelist** (Lesson L11-#41): serialize a `frozenset` of
  `{kind, per-kind params subset, id, base_sha}` + `schema_version` + monotonic `envelope_seq` —
  **never** a whole-object dump. **Opt-in by filesystem/flag** (`(root/".startd8/vipp").exists()` /
  env), **never `import startd8.vipp`** (A-S6); default posture **byte-identical-when-absent** (NR-7).
- **Redaction (OQ-10 resolved — display/defense-in-depth ONLY):** `params` are serialized
  **unredacted** (they are the bytes the applier writes + round-trip-gates; redacting corrupts
  schema/brief/manifest). `fde/redaction.py` stays a pasted-secret catch on at-rest/log surfaces; it
  must **not** touch `base_sha`/`value_path`/`kind`/`contract_path`.
- **Confinement/retention (OQ-9 resolved):** session-scoped inbox; mode `0600`; **shred on
  completion**; **purge rejected** (not retained); ship `.startd8/vipp/.gitignore`; confine writes by
  **parent-dir** realpath (L11-#85); **reads** symlink-rejecting (`O_NOFOLLOW`); explicit
  empty/"nothing-pending" state (L13-#73); reject-future `schema_version`; no-clobber of an undrained
  inbox (mirror `BufferFull`).
- **Tests:** `test_serialization_seam.py` — round-trip buffer→inbox→`ProposalEnvelope.from_json`
  (extend to assert M2's evaluator accepts the **real** serializer output, A-S6 fixture-parity);
  `base_sha`/`value_path` survive byte-for-byte and are **not** redaction-touched (R3-S7); **no-VIPP
  host writes nothing** (SOTTO dict-equality, L16-#44); rejected proposal **purged**; **read-path
  symlink rejected** (R3-S3); path confinement (`..`/abs/symlink).

## M4 — Applier (FR-5, FR-10, FR-16, FR-18) — provenance-pinned [CRP-gated, raised v0.3]

- **`vipp/apply.py`** — `apply_dispositions(project_root, envelope, report, *, confirm, config=None)
  -> List[ProposalOutcome]`. _[v0.3 — takes BOTH envelope + report; joins by `proposal_id`.]_ For
  each ACCEPT, reconstruct `ProposedAction` with `kind`/`params`/`base_sha` from the **trusted inbox
  entry** (not the disposition); a COUNTER overlays only its amended params and **never** `base_sha`/
  `kind` (R3-S1/F2). Call `apply_proposal(project_root, action, config=config)` (`proposals.py:217`).
  **Human-confirm gate (FR-16):** `confirm` renders the concrete content — `summary()` /
  `CapturePlan.preview()` — and is required; no write without it. Always through `apply_proposal`'s
  floor, never `apply_write_plan` directly.
- **Lifecycle/idempotency (FR-18):** refuse a disposition whose pinned `envelope_seq` is behind the
  on-disk inbox (re-negotiate); cursor keyed by `proposal_id`+`envelope_seq`; consume-on-terminal-
  success, retain retriable; partial-failure reports `wrote N/M`; shred/purge per FR-15.
- **Tests:** `test_apply.py` — ACCEPT applies from **inbox** params even when the disposition disagrees;
  a hostile `base_sha`/`kind` in the disposition is ignored (cannot disable the stale-file guard);
  REJECT/COUNTER without confirm writes nothing; unknown kind blocked by the floor; **3-of-5 partial
  (4th fails)** → first 3 consumed, 4th retriable, re-run resumes only the 4th; stale-seq refused.

## M5 — CLI surface (FR-11)

- **`src/startd8/cli_vipp.py`** — `vipp_app = typer.Typer(name="vipp", ...)` (template
  `cli_fde.py:13-17`). Commands: `negotiate` (read inbox → write dispositions, preview-by-default),
  `apply` (`--apply` to write, human-confirm prompt rendering content per FR-16), `init` (ensure
  posting). Exit codes (FR-11): **0** advisory/in-sync · **1** drift · **2** bad-input · **3** write
  blocked (confinement/clobber/**stale-seq**), mirroring `cli_concierge.py`.
- **`src/startd8/cli.py`** — `from .cli_vipp import vipp_app` (near `cli.py:40-44`) +
  `app.add_typer(vipp_app, name="vipp")` (near `cli.py:1248-1253`).
- `scripts/run_vipp.py` thin shim (exit 0), mirroring `scripts/run_fde.py`.
- **Tests:** `test_cli_vipp.py` — preview vs `--apply`; exit codes; registration smoke.

## M6 — Security + observability + docs (FR-9, FR-12, FR-14, FR-17)

- **FR-9 (retargeted — R3-S6: the v0.2 test would pass against a non-existent path):** the reachable
  test is that VIPP's **own narrator** fences inbox prose via `security.normalize_untrusted_text`
  (`security.py:667`) + `<context>` before narration; AND an inbox claim **cannot be promoted to
  MECHANISM** without a host provenance stamp — a locally hand-authored `proposals-inbox.json` yields
  OBSERVED/untrusted labels only (authority-spoof test). The "Concierge fences VIPP content" test is
  marked roadmap (no v1 LLM path).
- **FR-9 inbound floor test (R3-S8):** a crafted malicious inbox (unknown kind; `manifest` with an
  injected `dest`; `..`/abs path) is refused by `apply_proposal`'s floor + `safe_write` confinement —
  proving VIPP does not widen the host's write surface.
- **FR-12:** `capture` dispositions set only allow-listed value-paths (no bucket-4 prose).
- **FR-14:** stamp `project.id` (`integrations/join_contract.py`) into every envelope/report.
- **FR-17 (new):** event-per-disposition (kind+decision+label, no free-text), `get_logger`, durable
  source-labeled audit; test an operator can reconstruct decisions from disk+telemetry.
- **Docs:** `docs/design/vipp/` README; capability-index entry (`startd8.vipp.negotiation`, symmetric
  to `startd8.concierge.onboarding`); CHANGELOG `vipp` CLI surface.

---

## Sequencing & risk

| Milestone | FRs | Risk | Gate |
|-----------|-----|------|------|
| M0 contracts | 1,2,3,6,13 | low | unit (full nested round-trip; shape-pin) |
| M1 ground-truth | 7,8 | **medium** _(v0.3: net-new `answer→LabeledClaim` adapter, not pure consume)_ | unit |
| M2 brain | 3,4,6,18 | medium (rule design + prose→entity extraction) | unit |
| **M3 seam** | **15,17,18,NR-7** | **HIGH — new persistence surface** | **CRP done (R1); OQ-11 residual** |
| **M4 applier** | **5,10,16,18** | **HIGH _(v0.3: provenance-pinning + partial-apply)_** | **CRP-gated + gated live integration** |
| M5 CLI | 11 | low | smoke (exit-code table) |
| M6 security/obs/docs | 9,12,14,17 | medium | narrator-fence + authority-spoof + inbound-floor tests |

**Critical path (v0.3):** M3 **and M4** are the load-bearing milestones — CRP R1 showed the riskiest
work is split across both (M3 = the persistence surface; M4 = provenance-pinning + the partial-apply/
replay safety model, FR-18). Both are now CRP-gated. A gated live **two-process integration test**
(serialize seq N → VIPP read → host serialize N+1 → applier refuses the stale disposition) validates
the concurrency model (B-S4) and must exist before M4 lands.

**Traceability:** every FR-1…18 maps to a milestone; every milestone traces back to ≥1 FR. OQ-4/9/10
resolved (CRP R1); OQ-11 (in-process fast path) + OQ-12 (inbox writer-provenance) are residual scope
decisions, not M0–M2 blockers.

---

## Appendix A — Accepted CRP suggestions (incorporated)

Plan-doc suggestions (S-N per lens: **A**=arch, **B**=risks, **C**=security). ⊕ = multi-lens converge.

| ID(s) | Suggestion | Where merged |
|-------|-----------|--------------|
| ⊕ B-S1 · A-S3 | Idempotency fingerprint excludes `generated_at`/`seq`; ground-truth key = concrete file/glob checksums. | M2 step 2 |
| A-S1 | Split M1: `observed_from_report` (consume) + `observed_from_oracle` (net-new `answer→claim` adapter); raise M1 risk. | M1, risk table |
| A-S2 | `evaluate_envelope(envelope, oracle, …)` takes the queryable oracle; honest per-kind coverage; prose→entity extraction. | M2 step 3 |
| C-S5 | Narrator fences inbox prose (`normalize_untrusted_text` + `<context>`) before LLM. | M2 step 5 |
| ⊕ C-S1 · B-S2 | M4 joins inbox+dispositions; ACCEPT uses trusted-inbox params; `base_sha` not amendable; cursor + partial-failure. | M4 |
| C-S2 | Human-confirm renders concrete content (`summary()`/`preview()`). | M4 |
| C-S3 · R3-S7 | M3 redaction display-only; `base_sha`/`value_path` survive un-touched; read-path symlink reject; purge-rejected; SOTTO no-VIPP test. | M3 |
| C-S4 | No-clobber of undrained inbox; per-session/seq. | M3, FR-18 |
| B-S4 | Gated live two-process integration test (serialize N → read → N+1 → refuse stale). | M3/M4 gate, risk table |
| C-S6 | Retarget FR-9 test (narrator-fence + authority-spoof; the v0.2 test passed against a non-existent path). | M6 |
| C-S7 | M4 added to CRP gate; OQ covers inbox writer-provenance. | risk table, OQ-12 |
| C-S8 | Inbound-floor test: malicious inbox (unknown kind / injected dest / `..`) refused. | M6 |
| A-S5 | Full nested `VippReport` round-trip + per-node `to_dict`/`from_dict`. | M0 |
| A-S6 | M3 fixture-parity (real serializer output deserializes into M2's envelope); dependency-direction test. | M3 |
| B-S5 · A-S3 | M3 lifecycle (clear/retention/session) is a built+tested behavior, not prose. | M3 |
| B-S3 | Define ground-truth checksum concretely (reuse `fde/context.py` helpers). | M2 step 2 |
| B-S6 / S-? | M2 tested against hand-authored fixtures; M3 proves parity. | M2/M3 |
| B-S7 · S-3 (arch) | M0 envelope-shape-affecting OQs pulled forward (seq/whitelist) so M0 isn't presented as OQ-independent. | M0, M3 |

## Appendix B — Rejected / deferred (with rationale)

| ID | Suggestion | Disposition |
|----|-----------|-------------|
| (arch) S-3 partial | Finalize the *entire* envelope shape (incl. redaction-manifest field) in M0 before M3. | **Partial-accept:** pulled the seq/whitelist shape forward to M0; left the **redaction-manifest field dropped** (OQ-10 resolved "no content redaction" → no manifest needed), so M0 does **not** carry it. Not a rejection — the underlying concern (avoid M0↔M3 rework) is honored by resolving OQ-10 now. |

## Appendix C — Incoming (raw review rounds)

**Round 1 (CRP, 3 lenses, 2026-06-30).** Plan suggestions: Lens A S-1..S-6; Lens B S-1..S-8; Lens C
S-1..S-7. Raw text in the session transcript; triaged into Appendix A. Highest-impact (all ACCEPT):
fingerprint-excludes-`generated_at` (⊕ B-S1/A-S3), M4 provenance+partial-apply (⊕ C-S1/B-S2),
two-process live test (B-S4), narrator-fence (C-S5), M1 net-new adapter (A-S1).
