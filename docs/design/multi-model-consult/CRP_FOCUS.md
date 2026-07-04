# CRP Focus — Multi-Model Consultation

**Least-reviewed target:** Both `REQUIREMENTS.md` (v0.3) and `PLAN.md` (v1.0) are brand-new — this
is their first external review. Weight scrutiny toward the net-new areas below.

## Settled — do NOT relitigate
- Reuse of the `arun_benchmark` `asyncio.gather(..., return_exceptions=True)` fan-out pattern.
- Human-only evaluation; **no** automated answer judge/ranking (NR-2).
- 2-image cap for v1 (stored as a list so N-image is a config bump).
- New `ConsultationSession` artifact instead of overloading `AgentResponse` (NR-8).
- Surface = TUI + a thin `startd8 consult` CLI over the same core (OQ-2 resolved).

## Where review input is most valuable
1. **Multimodal per-provider adapter risk (FR-MMC-2).** Three genuinely different payload shapes
   (Anthropic `source`/base64 blocks, OpenAI `image_url` data-URLs, Gemini inline `Part` bytes).
   Is the "thin per-provider adapter, no shared abstraction" decision right? What breaks the
   text-only byte-identity invariant? How should `agenerate_tools` / structured paths interact?
2. **`ConsultationSession` schema + `.startd8/consultations/` concurrency (FR-MMC-6/-6a, OQ-8).**
   Is the per-model `turns_by_model` shape sufficient for follow-up continuity? Session-id scheme,
   atomic writes, two-TUI-instance collisions, image-by-reference (path+hash) vs re-embedding.
3. **Per-model conversation continuity (FR-MMC-7).** Replaying each model's prior turns as history
   across a parallel fan-out — correctness under partial failure/retry (FR-MMC-11); does a failed
   model's thread stay resumable?
4. **Cost/token handling of base64 images (FR-MMC-5, OQ-6/-10).** Attribution of image input
   tokens, downscaling policy, follow-up image accumulate-vs-replace.
