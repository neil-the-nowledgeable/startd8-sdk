# CRP Focus — Forward Deployed Engineer (FDE)

These docs already passed a reflective-requirements loop (planning pass + open-question
resolution verified against the codebase). The internal loop's blind spot is *external*
architecture/interface/risk. Weight the review toward the following; for each, give a
Summary answer / Rationale / Assumptions / Suggested improvements.

1. **SA↔FDE coupling & dependency direction (FR-17).** FR-17 adds an `fde_explanation` ref to
   the Service Assistant's `TriageReport` and claims one-directional coupling (FDE→SA, no import
   cycle), modeled on SA's local `SemanticReviewRef`. Stress-test: does the FDE reading
   `TriageReport` as a *typed import* (vs reading the JSON artifact) reintroduce a cycle or a
   version-lockstep between the two packages? Is artifact-level coupling the safer Tekizai-Tekisho
   boundary? Who owns the `FdeRef` schema and where does it live?

2. **Keiyaku-contract-shaped, transport-agnostic protocol (FR-12).** There is no A2A transport
   in the SDK today. The protocol is a frozen-dataclass contract whose `.md` files are the
   serialized view. Stress-test: is the markdown↔contract round-trip lossless and versionable?
   How is protocol/schema versioning handled as the contract evolves (the SDK-version stamp vs a
   protocol-version field)? Does "transport-agnostic" hold if EventBus (fire-and-forget, no
   resident consumer) is the only near-term transport?

3. **Deterministic-first vs LLM boundary (FR-15).** Mechanism *facts* are deterministic reads;
   LLM is confined to (a) prose-assumption detection and (b) narrative composition. Stress-test:
   is the boundary actually clean, or does narrative composition (b) risk re-introducing
   unlabeled mechanism claims that violate FR-6? How is the zero-LLM explain path validated/tested?

4. **Two-track preflight ordering (FR-8 / OQ-9).** Track 1 (prose, raw markdown, no signals) vs
   Track 2 (post-`plan-ingestion`, signals → `classify_tier()`). Stress-test: does running
   `plan-ingestion` inside the FDE preflight duplicate or conflict with the operator's own later
   ingestion run? Is Track 2's tier *prediction* sound given signals extracted from freshly-parsed
   (not-yet-real) features? Cost/latency of invoking a full workflow for preflight?

5. **Tekizai-Tekisho source-labeling guarantee (FR-6).** Every load-bearing claim tagged
   OBSERVED(project) vs MECHANISM(sdk). Stress-test: is the guarantee *enforceable* (a test/lint
   that fails on an unlabeled claim), or merely aspirational prose? What stops the LLM narrative
   step from emitting an unlabeled synthesis? How are *preflight predictions* labeled distinctly
   from *explain observations* (FR-16)?

6. **Security & ops (cross-boundary reads).** The FDE reads cross-artifact data
   (`prime-result*.json`, SA triage, project context, `.contextcore.yaml`) and may run LLM calls.
   Stress-test: trust boundary on artifacts the FDE did not produce; surprise-spend controls
   (FR-14 defers auto-launch — is that sufficient?); idempotency key correctness (request
   checksum + SDK version) across SDK upgrades.
