# CRP Focus — Confidence-Gated Apply (#8)

Both docs are brand new (zero prior review). Weight the review on the **write-boundary** concerns.

## Least-reviewed / highest-risk (concentrate here)

1. **FR-7 hash-safety (the load-bearing claim).** `source_session_id` is added as a **top-level envelope
   field**, asserted to be OUTSIDE the ratify content hash (`content_checksum` = proposals only;
   ratify `content_hash` over `{proposal_id, kind, params}`). Is that correct across BOTH envelope
   constructors (`vipp_seam.serialize_buffer` write dict + `vipp/models.ProposalEnvelope`)? Any path
   where the new field leaks into a signed/hashed payload or changes `envelope_seq`/idempotency?
2. **FR-2 provenance threading correctness.** serialize (`_serialize` → `serialize_accepted_to_vipp` →
   `serialize_buffer`) → envelope → `ProposalEnvelope.from_json` → `PreviewResult` → `_apply_preview`.
   Any break in the chain? Old inboxes (no field) → graceful n/a? A re-serialize / seq bump interaction?
3. **Layering (OQ-4).** Consensus computed in the ROUTE, not in `vipp/apply.py` (kept pure). Is that
   boundary clean, or does something force a vipp→facilitation dep?
4. **n/a / failure handling (FR-6).** No session, missing transcript, ask-all source, ≤1 rateable, or a
   consensus-compute exception → the preview must still succeed (best-effort). Any path that could 500
   the preview or render a false "low"?
5. **Multi-session inbox assumption.** The design assumes one inbox = one serialize = one source session
   (M1d made a 2nd serialize on an undrained inbox 409). Is that invariant actually guaranteed, or can an
   inbox mix proposals from >1 session (making a single `source_session_id` wrong)?
6. **Two-envelope drift (R2).** write dict vs read model — is the round-trip test sufficient?

## Settled — do NOT relitigate

- **#6 `compute_consensus`** — shipped (PR #188); reused as-is, not up for redesign. Its lexical-not-
  semantic framing is settled.
- **The apply security gate** (HMAC challenge, nonce, strict mode, confinement, `_content_hash`) — #8 does
  NOT change it; don't propose gate redesigns.
- **FLAG-only** — the sponsor chose advisory (no hard-gate / no server refusal). Don't propose a blocking gate.
- **Grafana-only** (no CLI apply exists) — NR-4.
- Token-never-a-panel-option / datasource-proxy routing; the two-store architecture; posture/tier.
- TS is buildable in-repo now (typecheck/lint/vitest/build runnable) — not a finding.

## Steering
Prefer S-/F- anchored to the provenance chain (FR-2), the hash-safety claim (FR-7), and the
multi-session invariant. Deprioritize generic "add tests/logging" unless tied to the write boundary.
