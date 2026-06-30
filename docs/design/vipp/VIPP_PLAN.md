# VIPP Implementation Plan

**Version:** 0.2 (post-reflection)
**Date:** 2026-06-30
**Tracks:** [VIPP_REQUIREMENTS.md](./VIPP_REQUIREMENTS.md) v0.2
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

## M1 — Ground-truth consumption (FR-7, FR-8)

- **`vipp/ground_truth.py`** — thin consumer of Sapper:
  - `load_observed_claims(project_root) -> List[LabeledClaim]`: call
    `sapper.ground_truth.oracle_for_project(project_root)` and/or read an existing
    `sapper-friction-report.json`, then `sapper.fde_bridge.to_observed_claims(report)`.
  - Availability guard `SAPPER_AVAILABLE` (try/except import) → degrade to an empty OBSERVED set with
    a clear "ground-truth unavailable" qualifier claim (mirror `FDE_AVAILABLE`, `fde_bridge.py:23-30`).
- **Tests:** `test_ground_truth.py` — consumes a fixture `FrictionReport`, asserts OBSERVED labels +
  `claim_id == fingerprint`; asserts graceful degradation when sapper absent (monkeypatch import).

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
  2. fingerprint(inbox checksum + sdk_version + ground-truth checksum); idempotent short-circuit if
     `dispositions.json` exists and unchanged.
  3. **deterministic core** `vipp/evaluate.py:evaluate_envelope(envelope, observed_claims) ->
     List[VippDisposition]`: per proposal, a deterministic rule set decides ACCEPT/REJECT/COUNTER
     against OBSERVED claims (e.g. REJECT a `schema`/`manifest` proposal whose entity is refuted by a
     Sapper finding; COUNTER with the corrected field). Every disposition carries labeled claims.
  4. render markdown via `compose.render_dispositions`; gate with `assert_all_labeled`.
  5. **opt-in narrative**: `if narrative:` lazy-import `compose.enhance_narrative` (LLM), re-gate.
  6. `if write:` write `dispositions.json` (canonical) + `.md`; `record_processed`. `if emit:` notify.
- **Tests:** `test_negotiate.py` — deterministic dispositions on fixtures (accept/reject/counter
  paths); idempotent re-run is `skipped=True`; narrative path is opt-in and stays label-gated; `$0`
  when `narrative=False`.

## M3 — Host-side serialization seam (FR-15, FR-16, NR-7) — **riskiest; gated on OQ-9/10**

- **`kickoff_experience/proposals.py`** (host side, additive): `serialize_buffer(buffer,
  project_root, *, redact=True) -> WriteResult` that writes the bounded pending list to
  `.startd8/vipp/proposals-inbox.json` via `safe_write.apply_write_plan` (reuse all confinement
  guards). **Opt-in**: only called when a VIPP posting exists / a flag is set — default posture
  (in-memory, no disk) is unchanged (NR-7).
- **Redaction (OQ-10):** run `ProposedAction.params` through a redaction pass (reuse/adapt
  `fde/redaction.py`) before serialization; record a redaction manifest in the envelope.
- **Confinement/retention (OQ-9):** inbox/outbox live under `.startd8/vipp/`, written atomically,
  clobber-guarded; document a TTL/per-session-vs-durable decision. **This milestone is the one to put
  through CRP** before building — it adds a persistence surface to data that is in-memory by design.
- **Tests:** `test_serialization_seam.py` — round-trip buffer→inbox→`ProposalEnvelope.from_json`;
  base_sha preserved; redaction applied; default posture writes nothing without opt-in; path
  confinement (reject `..`/abs/symlink).

## M4 — Applier (FR-5, FR-10, FR-16)

- **`vipp/apply.py`** — `apply_dispositions(project_root, report, *, confirm, config=None) ->
  List[ProposalOutcome]`: for each ACCEPT (and confirmed COUNTER), reconstruct a `ProposedAction`
  and call `kickoff_experience.proposals.apply_proposal(project_root, action, config=config)`
  (`proposals.py:217`) — which re-validates against the closed enum (`proposals.py:241`) and routes
  per kind. **Human-confirm gate (FR-16):** `confirm` is a required callback/flag; no write without
  it. Never touches `apply_write_plan` directly — always through `apply_proposal`'s floor.
- **Tests:** `test_apply.py` — ACCEPT applies via `apply_proposal` (mock/integration); REJECT/COUNTER
  without confirm writes nothing; unknown kind blocked by the existing floor; clobber-guard honored.

## M5 — CLI surface (FR-11)

- **`src/startd8/cli_vipp.py`** — `vipp_app = typer.Typer(name="vipp", ...)` (template
  `cli_fde.py:13-17`). Commands: `negotiate` (read inbox → write dispositions, preview-by-default),
  `apply` (`--apply` to write, human-confirm prompt), `init` (ensure posting). Posture-encoding exit
  codes (0 advisory / 2 bad input / 3 write blocked / 1 drift), mirroring `cli_concierge.py`.
- **`src/startd8/cli.py`** — `from .cli_vipp import vipp_app` (near `cli.py:40-44`) +
  `app.add_typer(vipp_app, name="vipp")` (near `cli.py:1248-1253`).
- `scripts/run_vipp.py` thin shim (exit 0), mirroring `scripts/run_fde.py`.
- **Tests:** `test_cli_vipp.py` — preview vs `--apply`; exit codes; registration smoke.

## M6 — Security + docs (FR-9, FR-12, FR-14)

- **FR-9:** add a test asserting VIPP-sourced inbox content is treated as untrusted by the Concierge
  path — reuse the prompt-injection fence coverage guard pattern
  (`tests/.../test_prompt_fence_coverage.py`); confirm VIPP claims stay OBSERVED-labeled and cannot
  be promoted to MECHANISM.
- **FR-12:** test that `capture` dispositions set only allow-listed value-paths (no bucket-4 prose).
- **FR-14:** stamp `project.id` (per `integrations/join_contract.py`) into every envelope/report for
  future A2A correlation.
- **Docs:** `docs/design/vipp/` README pointer; capability-index entry (`startd8.vipp.negotiation`,
  symmetric to `startd8.concierge.onboarding`); CHANGELOG `vipp` CLI surface.

---

## Sequencing & risk

| Milestone | FRs | Risk | Gate |
|-----------|-----|------|------|
| M0 contracts | 1,2,3,6,13 | low | unit |
| M1 ground-truth | 7,8 | low (consume Sapper) | unit |
| M2 brain | 3,4,6 | medium (rule design) | unit |
| **M3 seam** | **15,16** | **HIGH — new persistence surface** | **CRP before build (OQ-9/10)** |
| M4 applier | 5,10,16 | medium | integration |
| M5 CLI | 11 | low | smoke |
| M6 security/docs | 9,12,14 | medium | fence-coverage test |

**Critical path:** M3 is the load-bearing, highest-risk milestone (it didn't exist in v0.1's mental
model). Recommend running CRP on the requirements + this plan **before** building M3, focusing
reviewers on OQ-9 (confinement/retention) and OQ-10 (redaction).

**Traceability:** every FR-1…16 maps to a milestone above; every milestone traces back to ≥1 FR. No
open question blocks M0–M2; OQ-9/10 block M3; OQ-4/11 are scope decisions, not blockers.
