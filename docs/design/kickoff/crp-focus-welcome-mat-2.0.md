# CRP Focus — Welcome Mat 2.0 (R1)

Welcome Mat 2.0 adds three pillars to the **served** Welcome Mat web app
(`src/startd8/kickoff_experience/web.py`): (1) read-only template **download**, (2) a home-page
**agentic chat** with **propose-only** writes, (3) authoring the one missing template
(`conventions.md`). Weight the review toward the highest-risk surface — the **chat**. The
template-download and template-authoring pillars are lower risk; spend proportionally less there.

## Settled boundaries — do NOT re-propose

Inherited from `WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md` v0.4 and treated as fixed:
- MCP Concierge stays **preview/read-only**; no new MCP surface.
- **Writes only at human privilege** (web same-origin POST + CSRF + loopback Host + rate-limit, or
  CLI, or explicit TUI confirm). The agentic **loop never applies** a write.
- The agentic floor is `allow_effect_classes=("read",)` with a two-layer dispatch reject.

Do not suggest changes that re-litigate these — assume them.

## Where reviewer input matters most

### A. Agentic chat security & lifecycle (HIGHEST priority)
- **Propose-only write bridge** (FR-WM2-7 / plan S8): the chat may *prefill* a friction/instantiate
  form that the human submits to the **existing** `/concierge/*` endpoints. Can a chat-supplied
  "prefill" smuggle a value past the existing **preview-then-apply / one-time-intent / CSRF**
  gates? Is "the loop never posts" actually guaranteed by the design, or only by convention?
- **Server-side session state** `_ChatStore` (FR-WM2-5 / plan S5): session-fixation, cross-session
  bleed, unbounded growth, eviction correctness, idle expiry. Is keying it "like the CSRF store"
  sufficient, or does chat history need a distinct, harder-to-guess id?
- **Async `POST /chat`** (plan S6) alongside sync routes: does mixing async/sync handlers in the same
  FastAPI app interact badly with the loopback Host / rate-limit machinery? Is the chat endpoint
  rate-limited at all (it's the one **paid** surface)?
- **Cost/turn caps** (FR-WM2-9 / OQ-7): is a per-session turn cap enough, or is a per-session/-server
  spend ceiling needed? What happens at the cap — typed refusal, not a 500?
- **Graceful degradation** (FR-WM2-8): `agent=None` ⇒ disabled panel. Are there partial-failure modes
  (key valid but provider 401/timeout mid-conversation) that must also degrade rather than 500 `/`?
- **Error containment**: must a chat agent exception **never** propagate into the home-page render or
  leak provider error text / keys into the response?

### B. Download key-closure & parity (MEDIUM)
- **Path-traversal closure** (FR-WM2-2 / NR-3): is manifest-**key** lookup genuinely sufficient, or
  are there encoding/normalization escapes? Confirm no `..`/absolute path can ever be requested.
- **Download↔instantiate posture parity** (FR-WM2-4): downloaded `conventions.yaml` must be
  byte-identical to the instantiate plan's content at the same posture. Is the verify criterion right?
- **One-inventory no-drift** (FR-WM2-4/11/12): the manifest derives from `_KICKOFF_FILES` +
  `_AUTHORING_FILES`. Is the "adding a template without a manifest row fails a test" guard real?

### C. Open questions needing a call
- **OQ-4** — zip in-memory build: size ceiling needed?
- **OQ-5** — should `templates/authoring/*.md` (incl. new `conventions.md`) be downloadable? They are
  not packaged in `concierge_templates/` today (additive packaging decision).

## Out of scope for this review
- The assembly/manifest-grammar templates (data-model contract, app/pages/views) — explicitly NR-6.
- Re-designing the Concierge-mode milestone (v0.4) — only 2.0's additions.
