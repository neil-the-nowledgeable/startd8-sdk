# VIPP — Very Important Project Person

The **project-side negotiator/applier** counterpart to the SDK-side onboarding hosts (Concierge /
Welcome Mat / Red Carpet). VIPP is the **OBSERVED(project)-authority dual of the FDE**
(`src/startd8/fde/`, which carries MECHANISM(sdk) authority): where the FDE is the SDK's insider
*posted into* a project, VIPP is the project's representative *facing* the SDK.

## What it does

A two-process, file-mediated handshake:

```
HOST (Concierge / Red Carpet chat)            PROJECT (VIPP, out-of-process)
  ProposalBuffer (in-memory)                    vipp negotiate
        │ serialize (opt-in, M3 seam)                 │ consume Sapper ground truth
        ▼                                             ▼
  .startd8/vipp/proposals-inbox.json  ──read──►  evaluate → source-labeled dispositions
        ▲                                             │ (ACCEPT / REJECT / COUNTER)
        │ apply_proposal floor (human-confirm)        ▼
  writes at PROJECT privilege  ◄────apply──────  .startd8/vipp/dispositions.json
```

- **`startd8 vipp init`** — opt the project in (creates `.startd8/vipp/`; the host then serializes here).
- **`startd8 vipp negotiate`** — adjudicate the inbox against project ground truth ($0, deterministic):
  `capture` value-paths via Sapper field authority, `schema`/`manifest` entities via prose→entity
  extraction + the controlled corpus. OMIT/no-evidence → a **labeled** ACCEPT (never fabricated).
- **`startd8 vipp apply`** — preview by default; `--apply` writes accepted proposals at project human
  privilege through the host's `apply_proposal` floor, **provenance-pinned** to the trusted inbox.

## Design invariants

- **File-protocol first** (Keiyaku contracts; JSON canonical, markdown derived); A2A is a roadmap.
- **Out-of-process only** — the file seam *is* the trust boundary (OQ-11).
- **Provenance pinning** — an ACCEPT's `kind`/`base_sha` come from the trusted inbox, never a
  disposition; the **human-confirm is the sole content gate**.
- **VIPP mints only OBSERVED(project) claims** — it cannot forge SDK-mechanism authority.
- **Additive / byte-identical-when-absent** — the host seam (`kickoff_experience/vipp_seam.py`) is a
  new, opt-in module; `proposals.py` is unchanged.

## Map

| File | Role |
|------|------|
| `vipp/models.py` | Keiyaku contracts (`ProposalEnvelope`, `VippDisposition`, `VippReport`) |
| `vipp/ground_truth.py` | Sapper consumption (oracle answer→claim adapter + FrictionReport bridge) |
| `vipp/evaluate.py` | the deterministic per-kind negotiation rule set |
| `vipp/assistant.py` | `run_vipp_negotiate` — posting/idempotency/label-gate/narrative orchestration |
| `vipp/apply.py` | `apply_dispositions` — provenance-pinned applier (FR-18 lifecycle) |
| `vipp/compose.py` / `notify.py` | render + FR-9 inbox-prose fence / FR-17 events |
| `kickoff_experience/vipp_seam.py` | host-side serialization seam (M3) |
| `cli_vipp.py` | `startd8 vipp` CLI |

## Specs

- [`VIPP_REQUIREMENTS.md`](./VIPP_REQUIREMENTS.md) — v0.3 (reflective-requirements → CRP R1, 3-lens).
- [`VIPP_PLAN.md`](./VIPP_PLAN.md) — M0–M6 build plan + triage appendices.

Built via reflective-requirements → 3-lens convergent review → verify-before-M3 (reality check +
code review) → M0–M6. Deterministic and `$0` end to end (an opt-in LLM narrative is the only paid
surface).
