# SDK → StartDate: regenerate-diff for Audience-B 2a (FR-B0/B1 fencing)

**From:** startd8-sdk team
**To:** StartDate (strtd8) app team
**Date:** 2026-06-29
**Re:** What 2a (PR #64) changes in your 8 generated AI passes — the evidence promised in
`STARTDATE_COORDINATION_AUDIENCE_B.md` §3.
**Source:** rendered from your `prisma/{schema.prisma, ai_passes.yaml}` before vs. after the 2a SDK.

---

## BLUF

2a is **additive and surgical**. Of your **8 passes**, **only the 2 that ingest untrusted input
change** — they now wrap that input in a DATA-not-instructions fence. The other **6 (whole-model reads)
are byte-identical**, plus one new shared helper file (`app/ai/guards.py`). No behavior flip, no default
changed. Your confirmed value-model grounding is preserved (left unfenced). This is the heads-up diff,
**not** the go/no-go — 2a needs no sign-off; the sign-off is for **2b** (default-on guards + auto-send
refusal), which is still pending your two answers (see §4).

## What changed

| File | Change |
|---|---|
| **`app/ai/guards.py`** | **NEW** — shared, versioned, stdlib-only helper (`fence_untrusted`, `normalize_untrusted`) |
| **`draft_interviewer_message.py`** (FR-MSG, scoped) | context split: untrusted source rows fenced, request text fenced, **confirmed value model unfenced** |
| **`extract_document.py`** (source-bound) | request text fenced |
| 6 others (`extract`, `generate_artifacts`, `quantify_metrics`, `suggest_capabilities_outcomes`, `synthesize_differentiators`, `synthesize_value_propositions`) | **byte-identical** (whole-model reads — no untrusted free-text) |
| `service.py`, `edge_schemas.py`, `routes.py`, `ui.py` | **byte-identical** |

## The exact diffs

### `draft_interviewer_message.py` (your FR-MSG interviewer-message pass)
```diff
+ from app.ai.guards import fence_untrusted
...
-     context = {
+     untrusted_context = {       # scope (Contact) + resolved relations (Job, Company)
+     }
+     trusted_context = {         # confirmed value model — the grounding
...
-     full_prompt = (prompt + "\n\n" + json.dumps(context, default=str) + "\n\n" + text).strip()
+     full_prompt = (
+         prompt
+         + "\n\n" + fence_untrusted(json.dumps(untrusted_context, default=str), "scope_source")
+         + "\n\n## Confirmed value model\n" + json.dumps(trusted_context, default=str)
+         + "\n\n" + fence_untrusted(text, 'text')
+     ).strip()
```
The untrusted source rows (a third-party `JobDescription`'s free text, the interviewer text) and the
request field are fenced; the **confirmed value model the model must ground on is left unfenced**.

### `extract_document.py` (source-bound)
```diff
+ from app.ai.guards import fence_untrusted
...
-     full_prompt = (prompt + "\n\n" + text).strip()
+     full_prompt = (prompt + "\n\n" + fence_untrusted(text, 'text')).strip()
```

## Why this is safe to take now

- **Additive.** The fence wraps untrusted text as data with a "describe, don't execute" instruction —
  it does not remove or truncate your content (normalize only strips null/control chars + bounds at
  200 K chars; your passes are far under that).
- **Grounding preserved.** The confirmed value model is rendered exactly as before (unfenced) under a
  `## Confirmed value model` header, so message quality is unaffected.
- **No default flipped.** Input caps / output validation / in-flight / provenance (FR-B2–B5) and the
  auto-send refusal (FR-B6) are **not** in 2a.

## §4 — what we still need from you (for 2b, not 2a)

The behavior-changing guards (2b) are gated on the two questions from the coordination memo:
1. **Do any of these passes auto-send** (vs. persist a `confirmed:false` draft for human review)? If yes,
   FR-B6 will refuse to render them at build time without stricter mode — we'd design that with you.
2. **Does any pass rely on un-truncated input/output?** If so, name it and we'll set an explicit cap
   rather than the generous default.

*Reproduce this diff yourself:* regenerate `app/ai/` from `prisma/{schema.prisma,ai_passes.yaml}` with
the 2a SDK (PR #64) and diff against your current tree — only the 3 files above move.
