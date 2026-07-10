# Confidence-Gated Apply (#8) — Requirements

**Version:** 0.4 (Post-CRP — 2 rounds triaged)
**Date:** 2026-07-10
**Status:** Approved to build (FLAG-only; CRP applied — see Appendix A)

---

## 0. Planning Insights (Self-Reflective Update)

> Planning (against the serialize/inbox/apply seam) found the roadmap's "just surface #6 at apply" was
> infeasible as written — the source session is lost at serialize — and reshaped #8 around threading it.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Consensus is computable at apply time | **No session provenance survives to apply** — proposals carry only `{value_path, value}`. | FR-2 is the *enabling mechanism*: thread `source_session_id` serialize → envelope → preview (the real work; #6 reuse is thin on top). |
| Adding provenance may break the ratify gate | `content_checksum` covers **proposals only**; the ratify `content_hash` is over `{proposal_id, kind, params}`. | A **top-level** `source_session_id` is hash-safe → FR-7 holds by construction, gate untouched. |
| One envelope shape | **Two** constructors — `vipp_seam.serialize_buffer` (write) + `vipp/models.ProposalEnvelope` (read). | Add the field to both + a round-trip test (drift guard). |
| Compute in vipp | Keep `vipp/apply.py` pure of facilitation deps. | Provenance surfaced by `PreviewResult`; consensus computed in the **route** (OQ-4). |

**Resolved open questions:**
- **OQ-2 → thread `source_session_id`** (write dict + read model + `PreviewResult`), hash-safe.
- **OQ-3 → server-side in `_apply_preview`** (single round-trip, mirrors #6).
- **OQ-4 → route computes consensus**; vipp only passes the provenance through.
- **OQ-5 → Grafana-only** this increment (the apply surface is the ApplyPanel; no separate CLI apply).
- **OQ-1 → still open — sponsor's call** (flag vs hard-gate), see §4.

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified: `serialize_buffer`, `serialize_accepted_to_vipp`,
  `ProposalEnvelope`(+`checksum_payload`/`from_json`/`to_dict`), `preview_dispositions`, `PreviewResult`,
  `_apply_preview`, `_serialize`, `compute_consensus`, `CHALLENGER_IDS`, `KickoffViewService` all exist.
  New: the `source_session_id` field + a `consensus` preview field.
- **[Single-source vocabulary / drift]** — two envelope shapes (write dict + read model) is pre-existing;
  the field is added to **both** with a write→read round-trip test so they can't drift (plan R2).
- **[Provenance over-claim]** — reuses #6's honest framing verbatim ("synthetic, lexical, not a verdict");
  `basis` carries through.

### 0.2 Design-Principle Hardening (v0.3.1)

- **[Genchi Genbutsu]** — binds to the **real** envelope/preview + the source transcript's R1 rounds;
  **respects the write boundary** — provenance is envelope metadata, deliberately kept OUT of the hashed
  proposal content (never injected into what the challenge signs).
- **[Mottainai]** — reuses `compute_consensus`; forwards the `session_id` the serialize step already
  holds rather than re-deriving/looking it up.
- **[Accidental-Complexity]** — one threaded field + a route-level compute; no allowlist/special-case.
- **[Context-Correctness]** — `source_session_id` is declared + defaulted (`""`) + n/a-graceful: an old
  inbox (slot present, value absent) degrades to consensus `n/a`, never a crash or a false "low".
- **[Hitsuzen]** — the signal stays deterministic (#6), no LLM at the apply boundary.

---

## 1. Problem Statement

The apply gate writes the project source of record from the VIPP inbox (preview → paste challenge →
ratify). Nothing tells the operator whether the recommendations came from a facilitation where the
personas **agreed** or **diverged**. #8 threads the source facilitation `session_id` to apply time and
surfaces the #6 consensus in the apply **preview**, so a low-consensus synthesis is flagged before it's
committed. Reuses `stakeholder_panel.consensus.compute_consensus`.

| Component | Current State | Gap |
|-----------|--------------|-----|
| VIPP inbox / proposals | `{value_path, value}` | No `source_session_id` → the R1 answers are unreachable |
| `_apply_preview` response | would-apply + challenge | No `consensus` field |
| `ApplyPanel.tsx` preview | would-apply + challenge | No consensus indicator |

## 2. Requirements

- **FR-1 — Consensus in the apply preview.** `_apply_preview` returns a **always-present** `consensus:
  {label, score, n, basis}` for the source facilitation, via `compute_consensus` (reused). The `consensus`
  key is always in the response (never omitted); `label:"n/a"`/`score:null` is the n/a contract (R1-F3).
- **FR-2 — Session provenance.** `source_session_id` is carried serialize → inbox envelope → preview
  (added to the write dict, the read model `from_json`/`to_dict`, and `PreviewResult`). The
  **real production call site** is `serialize_accepted_to_vipp` → `serialize_buffer(buffer, root, …)` in
  `stage.py` — it MUST forward the id, or provenance is silently always-empty (R1-S1).
- **FR-2a — Path-safe session_id (security, R2-F1/R2-S1).** `source_session_id` read from the durable
  inbox MUST be validated with the same guard `TranscriptStore._safe_session_component` uses (reject
  `/`, `\`, `.`, `..`) **before** it is passed to `KickoffViewService.load()`. An unsafe value → skip the
  load → consensus n/a. (`KickoffPanelStore._path` has no such guard today; the inbox value is
  attacker-influenceable within the token boundary.)
- **FR-2b — One session per envelope (R1-F5/R1-S6/R2-S4).** A serialize covers exactly one source
  session. If the staged recs span >1 distinct non-empty `session_id` (or a `force=True` overwrite could
  mix them), `source_session_id` MUST be left **empty** (→ n/a) rather than pinned to an arbitrary one.
- **FR-3 — FLAG, not block.** Advisory surfacing only (sponsor decision); the write gate is entirely
  unchanged — no soft-ack, no server refusal, no ratify-path change.
- **FR-4 — Honest framing.** Synthetic, lexical, decision-support not a verdict (low = "read closely",
  never "do not apply"). **Additionally (R2-F3):** the `source_session_id` binding is **operator-attested,
  unverified metadata** (outside the ratify hash; a token holder with inbox write access can substitute
  it) — a documented non-goal, same threat model as the existing "token-gated, not human-proof" posture.
- **FR-5 — Grafana panel.** `ApplyPanel.tsx` renders the consensus on the preview screen (chip + caveat).
  When a session was present but consensus is n/a (e.g. ≤1 rateable), show a muted **"consensus: n/a
  (reason)"** — do **not** silently hide (R2-F4), so the operator knows it was attempted.
- **FR-6 — Graceful n/a (best-effort).** No/empty/unsafe `source_session_id`, a transcript-load
  **exception** (missing/corrupt file — not just a missing session), an ask-all source, or ≤1 rateable
  persona → consensus **n/a**; the preview still returns 200. The consensus block is a **separate inner
  try** *after* a successful `preview_dispositions` (never merged into the existing preview→502 try, R1-S3);
  its except path yields n/a and **logs a warning** (only on a genuine exception, not the benign n/a paths,
  R1-S7) so a silently-broken signal is still observable.
- **FR-7 — Do not weaken apply security.** `source_session_id` is a **top-level envelope field ONLY**; it
  MUST NOT appear in any per-proposal object (which feeds `content_checksum`/`checksum_payload`) nor in the
  would-apply item dict hashed by the ratify `_content_hash` (R1-F1). Regression: both `content_checksum`
  and the ratify `content_hash` are **byte-identical with vs without** a populated `source_session_id`.
- **FR-8 — M2 fingerprint unaffected (Mottainai, R2-F2/R2-S2).** `source_session_id` MUST be added to the
  `exclude_keys` of `vipp/assistant.py`'s `checksum_json_excluding` (alongside `generated_at`/`envelope_seq`
  — it is metadata, not proposal content), so a content-identical re-serialize after upgrade does **not**
  bust the M2 negotiate cache / force an unnecessary re-negotiate.
- **FR-9 — No echo (R1-F6/R2-S3).** The preview response body carries only the computed `consensus`; it
  does **not** echo `source_session_id` (consumed server-side only — minimal surface, no extra identifier
  crossing the token boundary).

## 3. Non-Requirements

- **NR-1 — No new consensus logic** (reuse `compute_consensus`).
- **NR-2 — No server-side apply refusal** on low consensus (FLAG only, OQ-1 resolved).
- **NR-3 — No change to the ratify content hash / challenge** (FR-7).
- **NR-4 — No CLI apply surface** (none exists; Grafana-only).
- **NR-5 — Not tamper-proof provenance** — binding `source_session_id` cryptographically to the proposals
  is out of scope (FR-4 documents it as unverified metadata within the token boundary).

## 4. Open Questions

- **OQ-1 → RESOLVED: FLAG only** (sponsor). Advisory surfacing on the preview; no soft-ack, no server
  refusal. The write gate is entirely untouched (M3 dropped). #8 is purely additive signal.

---

*v0.1 — draft.*
*v0.2 — post-planning: session provenance is lost at serialize → FR-2 threading is the real work;
hash-safe by construction; 4 OQs resolved.*
*v0.3 — lessons hardening: phantom audit clean; two-envelope drift guarded by a round-trip test.*
*v0.3.1 — design-principle hardening: Genchi-Genbutsu (respect the write boundary), Mottainai, Accidental-
Complexity, Context-Correctness, Hitsuzen. One OQ (flag vs gate) for the sponsor. Ready for CRP.*
*v0.4 — Post-CRP (opus R1 + sonnet R2). CRP caught 2 security issues the internal passes missed:
path-traversal via unsafe `source_session_id` (→ FR-2a) and an M2 fingerprint cache-bust (→ FR-8). Also
added the one-session invariant (FR-2b), the normative hash-placement clause (FR-7), best-effort scoping +
warn-log (FR-6), no-echo (FR-9), and the unverified-metadata disclosure (FR-4/NR-5). Dispositions in
Appendix A.*

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

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R2-F1 (+R2-S1) | Path-safety guard on `source_session_id` before load | sonnet | **HIGH security** → FR-2a. `_safe_session_component` before `load`; unsafe → n/a + test. | 2026-07-10 |
| R2-F2 (+R2-S2) | M2 fingerprint cache-bust → exclude the field | sonnet | → FR-8. Add to `checksum_json_excluding` exclude_keys + invariance test. | 2026-07-10 |
| R1-F5 (+R1-S6, R2-S4) | One-session invariant; force-path too | opus/sonnet | → FR-2b. >1 session → empty → n/a. | 2026-07-10 |
| R1-S1 | Name the real `stage.py` serialize_buffer call site | opus | → FR-2. Forward the id at the production call site. | 2026-07-10 |
| R1-S3 | Separate inner try (don't merge into preview→502) | opus | → FR-6. | 2026-07-10 |
| R1-F1 (+R1-S5) | Normative hash-placement + two-hash invariance test | opus | → FR-7. | 2026-07-10 |
| R1-F2 | Transcript-load exception → n/a | opus | → FR-6 (best-effort catch). | 2026-07-10 |
| R1-F3 | Pin the n/a-path JSON contract | opus | → FR-1 (consensus always present; label "n/a"). | 2026-07-10 |
| R1-F4 (+R1-S2) | Round-trip test asserts READ side (from_json) | opus | → plan M1.2. | 2026-07-10 |
| R1-S4 | Lazy imports + import-graph test (vipp pure) | opus | → plan M1.4/M1.5. | 2026-07-10 |
| R1-S7 | Warn-log on genuine-exception n/a | opus | → FR-6. | 2026-07-10 |
| R2-F3 | Disclose unverified-metadata binding | sonnet | → FR-4 + NR-5. | 2026-07-10 |
| R2-F4 | Session-present-but-n/a → show n/a chip, don't hide | sonnet | → FR-5. | 2026-07-10 |
| R1-F6 (+R2-S3) | Don't echo `source_session_id` in the response | opus/sonnet | → FR-9 (server-side only). | 2026-07-10 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All 10 F- + 12 S-suggestions accepted — each grounded in real code; two were security-critical (path-traversal, cache-bust). | 2026-07-10 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-07-10

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-10 00:00:00 UTC
- **Scope**: Write-boundary focus — FR-7 hash-safety, FR-2 provenance chain, the multi-session inbox invariant, layering (OQ-4), and n/a/best-effort (FR-6). Grounded against `vipp_seam.serialize_buffer`, `vipp/models.ProposalEnvelope`, `vipp/apply.py` (`preview_dispositions`/`_content_hash`), `synthesis_bridge/stage.py`, `consensus.py`, `stakeholder_run_server.py` (`_serialize`/`_apply_preview`).

**Focus-file asks (answered before standard suggestions):**

- **Ask 1 — FR-7 hash-safety (is a top-level `source_session_id` outside BOTH hashes?).**
  - **Summary answer:** Yes — verified in code, but the requirement should *positively forbid* the field from entering either hash, because nothing structurally prevents a future edit from adding it.
  - **Rationale:** The ratify `content_hash` is `hashlib.sha256` over `{"seq", "items":[{proposal_id, kind, params}]}` (`vipp/apply.py:118-125`) — envelope-level fields never enter it. The envelope `content_checksum` is over `checksum_payload()` = proposals only (`vipp/models.py:154-156`; `vipp_seam.py:154-156` write side). So a *top-level* `source_session_id` is genuinely outside both. FR-7 holds **by placement**, not by an assertion.
  - **Assumptions / conditions:** The implementer adds the field to the **envelope dict / dataclass top level** and NOT to any per-proposal dict in `proposals` (which would flow into both checksums) and NOT to the would-apply item dict in `_content_hash`.
  - **Suggested improvements:** See R1-F1 (make the "top-level, never per-proposal, never in `_content_hash`/`checksum_payload`" placement a normative clause + a named regression test).

- **Ask 5 — Multi-session inbox assumption (can an inbox mix sessions?).**
  - **Summary answer:** Depends — today the *route* scopes serialize to one `session_id`, but the *serialize helper* iterates per-recommendation `session_id`s and the invariant is nowhere enforced; a single threaded id can silently be wrong if the recs span sessions.
  - **Rationale:** `_serialize` loads `ProposalStore(project, session_id)` for one request `session_id` (`stakeholder_run_server.py:471-490`), so one serialize = one store today. But `serialize_accepted_to_vipp` iterates `recommendations`, each carrying its own `rec.session_id` (`stage.py:55`, set in `stage_recommendations`), and M1.1 threads the *route's* `session_id`, not the recs'. If a store ever holds recs from >1 session (or a caller passes a mixed list), the one threaded id mislabels the consensus source. The 409-on-undrained guard (M1d) enforces one *envelope* per inbox, not one *session* per envelope.
  - **Assumptions / conditions:** Holds only while `ProposalStore(project, session_id).load()` returns recs all bearing that same `session_id`.
  - **Suggested improvements:** See R1-F5 (declare the invariant + a mixed-session degradation rule).

**Numbered suggestions:**

1. **R1-F1** — FR-7 currently asserts the field is "outside the content hash" but does not forbid the two failure placements. Add a normative clause: *"`source_session_id` MUST be a top-level envelope field only; it MUST NOT appear in any per-proposal object (which feeds `content_checksum`/`checksum_payload`) nor in the would-apply item dict hashed by `_content_hash`."* Anchor: FR-7 sentence "Provenance is a top-level envelope field, **outside** the content hash". Verify: a regression test that computes `content_checksum` and the ratify `content_hash` with and without a populated `source_session_id` and asserts **both are byte-identical**.
2. **R1-F5** — FR-2/FR-6 assume one inbox = one session but never state it. Add an explicit invariant + degradation: *"A serialize covers exactly one source facilitation session; `source_session_id` is that session. If the staged recommendations span >1 distinct `session_id`, `source_session_id` MUST be left empty (→ consensus n/a) rather than pinned to an arbitrary one."* Anchor: FR-2 "carried serialize → inbox envelope → preview". Verify: unit test staging recs with two `session_id`s → serialized envelope has empty `source_session_id` → preview consensus = n/a.
3. **R1-F2** — FR-6 lists n/a triggers but omits the **unknown-method / malformed-rounds** path and does not bound *where* best-effort catching lives. `compute_consensus` degrades an unknown `method` to n/a and never raises on malformed rounds, but a `KickoffViewService(...).load(sid)` **raising** (missing/corrupt transcript file) is a separate failure the requirement should name. Add to FR-6: *"a transcript-load exception (not just a missing session) is caught and degrades to n/a."* Anchor: FR-6 "missing transcript ... → consensus n/a". Verify: test where `load(sid)` raises → preview returns 200 with consensus n/a, not 502.
4. **R1-F3** — FR-1 specifies the `consensus` field shape `{label, score, n, basis}` but not what appears on the n/a path. `ConsensusResult.to_dict()` emits `score: None` when n/a. State whether the preview omits the `consensus` key entirely on n/a (FR-5 "hidden when n/a") or returns `{label:"n/a", score:null, n, basis}`. These are different plugin contracts. Anchor: FR-1 and FR-5 ("hidden when n/a"). Verify: contract test pinning the exact preview JSON on the n/a path.
5. **R1-F4** — FR-2 says the field is added to "the write dict + the read model + `PreviewResult`" but the requirements never mention the **shape-pinning parity test** (`HOST_PROPOSAL_FIELDS` / the `vipp_seam` ↔ `models` lockstep test noted in both files' module docstrings). Since `from_json` silently drops unknown keys within a protocol major (`models.py:55`), a round-trip test that only checks the *write* side would pass even if `from_json` never reads the field. Add an acceptance criterion: *"the round-trip test asserts `source_session_id` survives write→`from_json`→`to_dict`, not merely that it is written."* Anchor: §0.1 "two envelope shapes ... a write→read round-trip test". Verify: the round-trip test reads back a non-empty value, and a second test confirms an envelope *without* the key deserializes to `""` (not KeyError).
6. **R1-F6** — Neither FR-2 nor FR-5 pins whether `source_session_id` is **echoed in the preview response body** or kept internal. The plan (M1.3) adds it to `PreviewResult`, but the requirements do not say if the route surfaces it to the plugin. If it is echoed, it becomes a (low-sensitivity) session identifier crossing the token boundary; if not, state that it is consumed server-side only. Anchor: FR-1 preview response fields. Verify: decide + document; assert the preview JSON either contains or omits `source_session_id` deliberately.

**Endorsements:** none (first round).

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-10

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-10 00:00:00 UTC
- **Scope**: Adversarial second-pass — write-boundary stress-test. Focus: (a) path-traversal via `source_session_id → KickoffPanelStore._path` (new attack surface introduced by FR-2's load call); (b) M2 fingerprint mutation from adding `source_session_id` to the envelope JSON; (c) `force=True` bypass invalidating the one-inbox-one-session invariant; (d) provenance spoofing/integrity (FR-7 adversarial). Grounded against `kickoff_view/store.py`, `stakeholder_panel/transcript.py`, `vipp/assistant.py` (`checksum_json_excluding`), `kickoff_experience/vipp_seam.py`, `cli_panel.py`.

**Focus-file asks (answered before standard suggestions):**

- **Ask 3 — `_apply_preview` best-effort try/except: error swallowing or path traversal?**
  - **Summary answer:** Partial — the best-effort catch (as designed) is scoped correctly (R1-S3 correctly identifies the issue), but a more urgent problem is that `source_session_id` from the inbox becomes a filesystem path component in `KickoffPanelStore._path` WITHOUT any sanitization, enabling path traversal reads outside the project directory.
  - **Rationale:** `KickoffPanelStore._path(session_id)` constructs `self.root / f"{session_id}.json"` with no guard (`store.py:27-28`). `TranscriptStore` has `_safe_session_component` that rejects `/`, `\\`, `.` and `..` (`transcript.py:36-44`), but `KickoffPanelStore` has no equivalent. The proposed `_apply_preview` implementation calls `KickoffViewService(project).load(source_session_id)`, where `source_session_id` comes directly from the durable inbox file. A maliciously-written `source_session_id` (e.g. `../../../../etc/passwd`) would cause `_path` to resolve outside the project root; `path.read_text()` would read that file. Python confirms: `Path('/proj/.startd8/kickoff-panel') / '../../../etc/passwd.json'` resolves to `/etc/passwd.json`. The best-effort try/except would swallow a `FileNotFoundError` → n/a (no crash), but for an existing path the file contents are parsed as JSON (Pydantic `model_validate` on arbitrary data → validation error → swallowed → n/a). However, the read still occurs before the exception, and on systems where `/etc/passwd.json` exists or is a symlink this is an SSRF-class file read. **The inbox is 0600 and written by the host, but the `force=True` path in `serialize_buffer` plus the CLI `cli_panel.py --serialize` invocation accepts `recs` from a `ProposalStore` whose `session_id` comes from a user-controlled argument (`sid` from `body.get("session_id")`), giving an attacker control over the inbox content at serialize time if they can call `_serialize` with a crafted `session_id` that stages recs with a malicious `source_session_id` value.**
  - **Assumptions / conditions:** The attack requires: (1) caller can reach `_serialize` with an attacker-chosen session_id, (2) a `Recommendation` row's `session_id` is the attacker-controlled value which then becomes `source_session_id`. This is within the token-authenticated boundary, so severity is medium (insider/token holder), not critical — but the gate is described as "token-gated, not human-proof".
  - **Suggested improvements:** See R2-F1 below. Mirror `_safe_session_component` from `TranscriptStore` in `KickoffPanelStore._path` (or in a shared util), and add an explicit normative clause to FR-6 / FR-2.

- **Ask 4 — Does adding `source_session_id` to `to_dict` change `envelope_seq` idempotency or the M2 fingerprint?**
  - **Summary answer:** Yes — adding `source_session_id` to the envelope JSON on-disk changes the M2 fingerprint (forces a full re-negotiate on first serialize with the new field), but does NOT affect `envelope_seq` idempotency or the ratify `content_hash` or `content_checksum`.
  - **Rationale:** `vipp/assistant.py:85-87` computes the M2 fingerprint as `context.checksum_json_excluding(inbox_path, exclude_keys=("generated_at", "envelope_seq"))`. This hashes the *full* inbox JSON minus those two keys. Adding `source_session_id` as a new top-level key means any inbox written by the new code will produce a different M2 fingerprint than the same proposals written without the field — even for identical proposals and a content-identical re-serialize. Concretely: upgrading from pre-#8 to post-#8 code invalidates all cached M2 short-circuits, forcing full re-negotiate on the next run. This is a one-time migration cost, but: (a) it is not mentioned in the plan, (b) for a project that re-serializes the same proposals (FR-18 idempotency), the first post-#8 serialize will burn the M2 cache unnecessarily. The envelope_seq idempotency (FR-18 stale-seq refusal) and `content_checksum` (proposals only) are unaffected. The ratify `content_hash` (`_content_hash` over `{seq, items}`) is also unaffected.
  - **Assumptions / conditions:** Holds as long as `checksum_json_excluding`'s `exclude_keys` does not include `source_session_id`.
  - **Suggested improvements:** See R2-F2 below. Document the M2 cache-busting as a known one-time cost, or add `source_session_id` to the `exclude_keys` in the M2 fingerprint (same rationale as `generated_at` — it is provenance metadata, not proposal content).

- **Ask 2 (provenance spoofing/integrity) — Can a tampered inbox present a misleading `source_session_id`?**
  - **Summary answer:** Yes structurally, but the threat model is bounded: the inbox is 0600 and operator-written; the gate is explicitly "token-gated, not human-proof". A token holder who can write the inbox can substitute any `source_session_id`, causing a high-consensus signal to display for a low-consensus (or unrelated) set of proposals. This is an honest-signal hole within the token boundary.
  - **Rationale:** `source_session_id` is intentionally outside the ratify `content_hash` (FR-7 / correct). Nothing signs or binds it to the proposals in the envelope. The `posture` field in the preview response already states "token-gated, not human-proof". An operator with write access to `.startd8/vipp/proposals-inbox.json` (0600, only root/operator can write) can set `source_session_id` to any previously-facilitated session, including one with 100% consensus, regardless of what the proposals actually are. The result: the Apply panel displays "high consensus" for a set of proposals that was never collectively agreed-upon.
  - **Assumptions / conditions:** Attack requires write access to the 0600 inbox (operator level) — this is within the stated threat model ("token-gated, not human-proof").
  - **Suggested improvements:** See R2-F3 below. FR-4 (honest framing) should explicitly state that the consensus signal's source-session binding is unverified metadata (same honest framing as "synthetic, lexical"). This turns an implicit limitation into an explicit, documented non-goal rather than a silent integrity gap.

**Feature Requirements Suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Security | high | Add a normative path-safety clause to FR-2 or FR-6: *"`source_session_id` extracted from the inbox MUST be validated against the same `_safe_session_component` guard used by `TranscriptStore` (reject `/`, `\\`, `.`, `..`) before being passed to `KickoffViewService.load()`. An unsafe value MUST degrade to consensus n/a."* `KickoffPanelStore._path` constructs `root / f"{session_id}.json"` (store.py:27-28) with no guard, unlike `TranscriptStore._safe_session_component` (transcript.py:36-44) which explicitly rejects traversal components. | A controlled `source_session_id` in the inbox (within the token boundary) causes `_apply_preview` to read an arbitrary `.json` file outside the project root. `FileNotFoundError` degrades gracefully, but an existing file is read before the parse exception, and `.read_text()` fires before Pydantic `model_validate` fails. | FR-2 (add "path-safe session_id" acceptance criterion) + FR-6 (add "unsafe session_id → n/a" degradation trigger) | Test: `source_session_id = "../../../etc/passwd"` in inbox → preview returns 200 with `consensus n/a`; assert `KickoffPanelStore.load` is never called with an unsanitized path component. |
| R2-F2 | Data | medium | Document the M2 fingerprint cache-bust as a known migration cost of adding `source_session_id` to the envelope JSON, OR add `source_session_id` to the `exclude_keys` in `vipp/assistant.py`'s `checksum_json_excluding` call. Currently `exclude_keys=("generated_at", "envelope_seq")` (assistant.py:85-87); `source_session_id` is equally metadata (not proposal content) and should be excluded for the same reason `generated_at` is. Without exclusion, a post-#8 re-serialize of unchanged proposals breaks the M2 short-circuit. | The M2 fingerprint hashes the full inbox JSON minus its exclude list. Adding a new top-level field changes that hash, forcing full re-negotiate even when proposals are byte-identical — contradicting the "recognizably a no-op" claim in `models.py:143`. | FR-7 or §0.2 Design-Principle Hardening (Mottainai — don't discard cached decisions unnecessarily) | Verify: serialize same proposals pre- and post-#8 → M2 fingerprint is identical (if excluded) or document "one-time cache invalidation on upgrade" explicitly. |
| R2-F3 | Security | low | FR-4 (honest framing) states "synthetic, lexical, not a verdict" for the consensus signal, but does not mention that the source-session binding is **unverified metadata**. Add: *"The `source_session_id` binding is operator-attested metadata outside the ratify hash; the gate is token-gated not human-proof. A token holder with inbox write access can substitute any session_id. This is a documented non-goal (same threat model as the existing posture disclosure)."* | Without this clause, the honest-framing requirement (FR-4) implies the consensus label is tied to the actual proposals, which is architecturally false — the binding is nominal. The `posture` field in the preview already says "token-gated, not human-proof"; FR-4 should match. | FR-4 (add "source-session binding is unverified metadata" clause) | Manual: confirm the requirements doc + ApplyPanel caveat text explicitly disclose the unverified binding, not just the lexical/synthetic nature of the score. |
| R2-F4 | Interfaces | medium | FR-1 and FR-5 do not specify behavior when `source_session_id` is present but the derived consensus is n/a due to `≤1 rateable persona` (an ask-all source): does the panel show "n/a" or hide the chip? FR-5 says "hidden when n/a" but does not distinguish "no session" (expected gap) from "session present, consensus n/a" (potentially surprising — the operator may wonder why consensus is absent). Add a UX spec: when `source_session_id` is non-empty but consensus is n/a, the chip should display a "n/a (≤1 rateable)" tooltip rather than silently hiding, so the operator knows consensus was attempted but could not be computed. | Hiding the chip when a session is present but consensus cannot be computed may mislead the operator into thinking the provenance was absent, not that it was present but uninformative. The distinction matters for the honest-framing requirement (FR-4). | FR-5 (add "session present but n/a → show chip with n/a tooltip" spec) + FR-6 (clarify that ≤1 rateable with a valid session is a distinct n/a sub-case) | Test: preview with a valid `source_session_id` but ≤1 rateable persona → panel shows "n/a" chip (not hidden), tooltip states reason. |

**Endorsements:**

- **R1-F1**: Endorse — the normative placement clause is load-bearing; adding it prevents a future implementer from accidentally moving `source_session_id` into a per-proposal dict.
- **R1-F5**: Endorse strongly — the multi-session degradation rule is necessary for the honest-signal claim. Without it, `source_session_id` can silently mislabel consensus.
- **R1-F2**: Endorse — `KickoffViewService.load` raising `FileNotFoundError` is the primary failure path; FR-6 must name it.
- **R1-F4**: Endorse — the round-trip test MUST assert the read side, not just the write side. `from_json` silently drops unknown keys.
