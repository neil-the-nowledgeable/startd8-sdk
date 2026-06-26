# Welcome Mat 2.0 — Requirements

**Version:** 0.3 (Post-CRP R1–R4)
**Date:** 2026-06-26
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `WELCOME_MAT_2.0_PLAN.md` (v0.2)
**Related (settled boundaries inherited, do not re-litigate):**
`WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md` (v0.4, the Concierge-mode milestone),
`INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md` (v0.5, "Welcome Mat"),
`KICKOFF_INPUT_PACKAGE_GUIDE.md` (v0.1, the canonical template set), `CONCIERGE_MCP_REQUIREMENTS.md`

> **What "2.0" is.** The Welcome Mat shipped as a $0, read-mostly onboarding surface (readiness
> meter + per-field badges + a Concierge mode that surveys / instantiates / logs friction). 2.0 adds
> three *outward-facing* affordances on top of that settled base — **without** widening any of the
> safety boundaries the Concierge-mode milestone established. Everything new is either read-only/`$0`
> or rides the **existing** human-privilege write seam.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass read the live
> `kickoff_experience/web.py`, `chat.py`, `concierge/writes.py`, and `cli_kickoff.py` and found the
> three pillars are **unequal**: two are pure reuse, but the chat is the only stateful / async /
> paid / key-needing surface in the whole Welcome Mat — and the "missing templates" work is far
> thinner than the phrasing implied.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| **P-A "reuse, don't re-implement"** applies uniformly across all three pillars | Download + templates are pure reuse; **chat needs genuinely new plumbing** — an agent threaded through `build_kickoff_app`/`serve_kickoff`/`start` (none takes an agent today, `serve.py:239`) **and** a new chat-session store (`_SessionStore` holds CSRF tokens, not conversation history, `web.py:69`). | **P-A softened for chat** (reuse the loop/registry/cost; new agent-threading + session-store plumbing is expected, not a smell). Resolves OQ-1, OQ-3. |
| **OQ-2 — chat endpoint shape unknown** | Existing routes are sync `def`; `AgenticSession.ask` is **async**; uvicorn owns the loop. The CLI's `asyncio.run` (`cli_kickoff.py:chat`) is a CLI-only bridge. | **OQ-2 resolved → `POST /chat` is `async def`** calling `await chat.ask(...)` directly. Pinned in FR-WM2-5. |
| **OQ-3 — where the chat agent comes from** | `serve_kickoff` has no agent; the CLI resolves `resolve_agent_spec(spec or Models.CLAUDE_SONNET_LATEST)` inside a **try/except degradation already written** (`cli_kickoff.py:233`). | **OQ-3 resolved → one agent per server**, `--agent` flag, reuse the CLI degradation pattern — which directly *implements* FR-WM2-8. |
| **P3 "author the missing templates"** sounds like a multi-file authoring effort | The 11 packaged templates **all exist** (`concierge_templates/`). The *only* genuinely missing file is per-domain authoring guidance for `conventions.yaml` — every other input domain has a `templates/authoring/*.md`, `conventions.md` does not. | **FR-WM2-10 narrowed to `conventions.md` + a manifest/index.** P3 is "thinner than feared." |
| **Download is the trivial pillar** (no risk) | Trivial to build, but the real risk is **path traversal / arbitrary-file disclosure**. Mitigated *structurally* by manifest-**key** lookup (no path parameter ever accepted). | Elevated the **key-closure invariant** to the download acceptance criterion (FR-WM2-2 / NR-3). |
| **Posture substitution only matters at instantiate** | `conventions.yaml` ships a posture-resolved provenance placeholder (`writes.py:_render_input`); a *downloaded* copy must resolve it the same way or download output diverges from instantiate output. | **FR-WM2-4 extended** — download applies the same `_render_input` posture substitution. |
| **Chat is "just another home-page panel"** | It is the **only** non-`$0`, **only** stateful, **only** async, **only** key-needing surface in the Welcome Mat. | **Graceful degradation (FR-WM2-8) + cost visibility (FR-WM2-9) are first-class**, not afterthoughts; per-session turn cap added (OQ-7). |

**Resolved open questions:**
- **OQ-1 → new `_ChatStore`** modeled on `_SessionStore` (session-id → `KickoffChat` + last-used +
  turn count; idle expiry + bounded entries). The CSRF store can't hold chat history.
- **OQ-2 → `async def /chat`** calling `await chat.ask(...)` (uvicorn owns the loop).
- **OQ-3 → one agent per server**, `--agent` on `serve`/`start`, default `Models.CLAUDE_SONNET_LATEST`.
- **OQ-6 → inline chat panel on `/`** (one home page), not a separate `/chat` page.
- **OQ-7 → per-session turn cap** in `_ChatStore` (the cost guard the paid surface needs).
- **OQ-4 → STILL OPEN** (zip vs tar; in-memory build — bounded set, almost certainly safe; confirm at build).
- **OQ-5 → STILL OPEN** (whether `templates/authoring/*.md` join the downloadable set; they aren't
  packaged in `concierge_templates/` today, so it's an additive packaging decision — defer to CRP).

---

## 1. Problem Statement

The served Welcome Mat helps a user *understand* their kickoff state but gives them no way to **take
the templates with them**, and its only conversational help (the agentic kickoff chat) is **invisible
on the web** — it lives behind a CLI command. Three concrete gaps:

| # | Capability | Current state | Gap |
|---|-----------|--------------|-----|
| **P1** | **Download the template files** | Templates reach a project *only* by `instantiate` **writing** them to disk (`concierge/writes.py:_load_template`). `web.py` has **no** download route (no `FileResponse` / `Content-Disposition` anywhere). | A user who wants to read/keep the kickoff-input + authoring templates — without scaffolding them into a project — has no path. There is no "download the templates" affordance. |
| **P2** | **Agentic chat on the home page** | The read-only agentic kickoff chat (`chat.py`: `survey` / `assess` / `field_states`, `allow_effect_classes=("read",)`) is **CLI-only** (`startd8 kickoff chat`, `cli_kickoff.py:219`). The web home page (`web.py:344 overview` → `_render_overview`) shows a readiness meter and a *link* to `/concierge`, but **no chat**. | A web user can't converse with the assistant at all; and the assistant — even where reachable — can only talk, never help the human *act* (draft a friction entry, prefill an instantiate). |
| **P3** | **A complete, downloadable template set** | The canonical set (`KICKOFF_INPUT_PACKAGE_GUIDE.md` §1) is 6 package files + a 5-file authoring quintet = the 11 packaged files in `src/startd8/concierge_templates/`. Per-domain **authoring guidance** lives in `docs/design/kickoff/templates/authoring/` — but `conventions.yaml` (the "run-028 guard", the Architect's centerpiece) has **no** `conventions.md`, unlike every other input domain. | The template surface the Welcome Mat would offer for download is **incomplete**: the highest-stakes input has no authoring guidance, and there is no single manifest that says "this is the complete set." |

**What should exist (2.0):**
1. A **read-only download surface** in the served web app that offers the kickoff-package + authoring
   templates — individually and as a single bundle — sourced from the *same* inventory `instantiate`
   uses (so the two can never drift), keyed so no arbitrary file can be requested.
2. A **home-page agentic chat** that surfaces the existing read-only kickoff loop on the web, and can
   **propose** (draft / prefill) a friction entry or an instantiate — which a **human still applies**
   through the existing same-origin + CSRF write seam. The loop itself never writes.
3. The **missing template element(s)** authored so the downloadable set is complete and coherent —
   concretely, `conventions.md` authoring guidance, plus a manifest/index that names the full set.

---

## 2. Guiding Principles (inherited from the Concierge-mode milestone)

- **P-A — Reuse, don't re-implement (with one honest exception).** Download rides `_load_template` +
  the `_KICKOFF_FILES`/`_AUTHORING_FILES` inventory. Chat rides `build_kickoff_registry` +
  `AgenticSession` + `KickoffChat` + `resolve_agent_spec`. Propose-only writes ride the **existing**
  `/concierge/friction` + `/concierge/instantiate` seam — no new write engine, no new template loader,
  no new readiness computation. *Exception surfaced by planning:* the chat does need **new plumbing** —
  an agent threaded into the app and a chat-session store — because nothing existing carries an agent
  or holds conversation history (the `_SessionStore` holds only CSRF tokens). That plumbing is
  expected, not a reuse failure.
- **P-B — `$0` and offline except the chat.** Download and template authoring are deterministic and
  `$0`. The agentic chat is the **one** surface that calls an LLM (cost + an API key); it must
  **degrade gracefully** (the rest of the Welcome Mat keeps working with no key / no agent).
- **P-C — Writes only at human privilege; never MCP, never the loop.** The chat is read-only by
  construction (`allow_effect_classes=("read",)`). "Propose-only" means the assistant *suggests
  values*; the **human** applies them through the unchanged write seam (web same-origin POST with
  session/CSRF + loopback Host + rate-limit). The loop never reaches `apply_write_plan`.
- **P-D — No new disclosure / traversal surface.** Download serves only the allow-listed packaged
  templates by **manifest key**, never by a caller-supplied path. Chat exposes only the three
  existing read tools; it never reads consumer file *content* beyond what those tools already return.
- **P-E — One inventory, two consumers.** The downloadable set and the instantiate set are the *same*
  list. A template added to one is added to both, by construction.

---

## 3. Requirements

### A. Template download (P1)

- **FR-WM2-1 — A download surface.** The served web app exposes a read-only download area listing the
  kickoff-package + authoring templates with, per entry, a human label, destination-when-instantiated,
  group (`package` | `authoring`), and byte size. Reachable from the home page. Read-only, `$0`,
  available in **all** feature modes (incl. `inspect`/`preview`) — it never writes.
  - **Acceptance (CRP R1–R4):** *(R3-F4/R3-S4)* the index exposes a **posture selector**
    (`prototype`/`production`) and — given the `with_authoring` split (FR-WM2-4) — an authoring toggle,
    so a user gets the right `conventions.yaml` bytes without hand-editing a query string. *(R2-S7)* the
    home page (`_render_overview`) gains the templates nav link **and** a Concierge CTA driven by the
    already-shipped `build_concierge_view(root)["next_action"]` (no duplicated package-missing logic).
- **FR-WM2-2 — Individual file download.** A route serves one template's bytes with
  `Content-Disposition: attachment; filename="<canonical>"` and a text/markdown or text/yaml content
  type. The file is selected by a **manifest key**, not a path; an unknown key returns a typed 404.
  No `..`/absolute path can ever be requested (the key space is closed).
  - **Acceptance (CRP R1–R4):** *(R1-F5/R1-S6 — key-closure)* the key is `urllib.parse.unquote`'d
    **once** then matched **exactly** against the closed manifest key set; `..`, `%2e%2e`, a leading
    `/`, backslashes, and unknown keys all return a typed 404 — fuzz tests for encoded traversal
    segments must 404, a valid (possibly slash-containing) key must 200 with the attachment. *(R2-S8 —
    content type)* `Content-Type` is set per entry with `charset=utf-8` (`.yaml`→`text/yaml`,
    `.md`→`text/markdown`); the filename is the manifest `dest` basename only. *(R4-F7/R4-S7 — posture
    validation)* a `posture` query outside `VALID_POSTURES` returns a typed 400 `posture_invalid` (never
    a silent default, never a 500); omitted ⇒ `prototype`.
- **FR-WM2-3 — Bundle download.** A route serves the whole set as a single archive (zip) with the
  package + authoring trees laid out as they would be on disk (`docs/kickoff/…`), built in-memory
  from `_load_template`. `$0`, read-only.
  - **Acceptance (CRP R1–R4):** *(R1-F6/R1-S7 — closes OQ-4)* the in-memory build enforces a documented
    **maximum total uncompressed bytes** (≤2 MB is ample for the set); exceeding it returns a typed 413
    `bundle_too_large` with **no** partial archive streamed. *(R3-F6/R3-S6 — zip-slip)* every archive
    member path equals a manifest `dest` validated as a **safe relative path** (no leading `/`, no `..`
    segment, no backslash) at accessor time, not serve time — a bad `dest` fails the manifest/CI test
    before the route is reachable. *(R3-S1 — `with_authoring`)* the bundle documents and honors a
    `?with_authoring=` filter (see FR-WM2-4).
- **FR-WM2-4 — One inventory (no drift).** The download manifest is **derived from** the same
  `_KICKOFF_FILES` + `_AUTHORING_FILES` lists `build_instantiate_plan` consumes (exposed via a small
  public accessor). A template added to instantiate appears in download with no extra edit. **Posture
  substitution must match instantiate:** a downloaded `conventions.yaml` resolves the provenance
  placeholder via the same `_render_input` path `instantiate` uses (default posture `prototype`), so
  downloaded bytes equal instantiated bytes.
  - **Acceptance (CRP R1–R4):** *(R3-F1/R3-S1 — the `with_authoring` drift, the real one R1-S8's
    bijection misses)* `build_instantiate_plan` defaults to `with_authoring=False` and writes only the
    **6** package files (`writes.py:91`), while the manifest lists **11**. Each manifest row therefore
    carries `group: package | authoring`; the bundle accepts `?with_authoring=` (default chosen to be
    *explicit*, not assumed); and byte parity is asserted **at the same `with_authoring` and `posture`**,
    never "download always equals default instantiate." *(R2-F5/R2-S6 — triple-byte parity)* for every
    manifest key × posture, the bytes from the **single** download, the corresponding **bundle** zip
    entry, and `build_instantiate_plan(...)` content for that `dest` are **identical** — a parametrized
    test over all keys × `{prototype, production}`, not just the `conventions.yaml` example.

### B. Home-page agentic chat (P2)

- **FR-WM2-5 — Chat on the home page.** The home page (`/`, inline panel — OQ-6) surfaces the
  read-only agentic kickoff chat (`build_kickoff_registry` — `survey` / `assess` / `field_states`) as a
  conversational panel. An **`async def POST /chat`** endpoint accepts a user message and returns the
  assistant's turn by `await chat.ask(...)` (uvicorn owns the loop; the CLI's `asyncio.run` is not
  reused). Multi-turn history is held in a server-side **`_ChatStore`** (session-id → `KickoffChat` +
  last-used + turn count; idle expiry + bounded entries), modeled on `_SessionStore` — which holds
  CSRF tokens, *not* history.
  - **Acceptance (CRP R1–R4) — session identity & lifecycle:**
    - *(R1-F3/R1-S2/R4-F5/R4-S5 — separate cookie, bootstrapped)* `_ChatStore` is keyed by a
      **server-issued** `kickoff_chat` cookie (`httponly`, `SameSite=strict`), **distinct from**
      `kickoff_csrf` and never a client-supplied id. The cookie is **issued on `GET /`** when
      `agent is not None` (parallel to CSRF issuance) so the first `POST /chat` is not session-bootstrap
      + spend in one step. A missing/expired session → typed `chat_session_expired`; CSRF alone cannot
      drive `/chat`.
    - *(R3-F5/R3-S5 — memory-only)* history lives **in RAM only** (never written to `.startd8/` or
      disk); on idle expiry/eviction the entry **and** the `AgenticSession` message list are destroyed,
      and the store stays bounded.
    - *(R2-F7/R2-S3 — concurrency)* at most **one in-flight `POST /chat` per session** (an
      `asyncio.Lock` held across `await chat.ask`); a concurrent request is serialized or returns typed
      `chat_busy` — `AgenticSession` history is never mutated concurrently.
    - *(R2-F6/R2-S5 — input cap)* the inbound `message` is length-capped (document the max, e.g. ≤4096);
      over-length → typed `message_too_long` **without** invoking the provider.
    - *(R1-S1 — endpoint hardening)* `POST /chat` applies the loopback `_host_ok` check and a per-session
      chat rate window (typed `chat_rate_limited`), distinct from the capture/Concierge limits.
    - *(R3-F7/R3-S7 — stable JSON contract)* the endpoint returns a documented schema:
      success `{ok: true, text, cost: {turns, tokens, usd, stop_reason?}, propose?}`; refusal/error
      `{ok: false, code, message?}` with the typed codes named here and in FR-WM2-8.
    - *(R4-F1/R4-S1 — CLI threading, makes this reachable)* `--agent` is threaded **end-to-end**:
      `kickoff start --agent <spec>` → `serve_kickoff(..., agent=...)` → `build_kickoff_app(..., agent=...)`
      (both call sites today omit it — `serve.py:214-239`, `cli_kickoff.py start`). Without this the chat
      is dead on the primary launch path.
- **FR-WM2-6 — Read-only floor preserved.** The web chat uses the **same** registry and dispatch floor
  as the CLI (`handle_kickoff_read` hard-rejects any non-read action). No write tool is ever
  registered. The posture banner (`chat.py:POSTURE_BANNER`) is shown.
  - **Acceptance (CRP R1–R4):** *(R2-F2/R2-S2 — prompt alignment)* `KICKOFF_SYSTEM_PROMPT` is updated so
    the assistant may **suggest/prefill** friction & instantiate drafts for Concierge submission, while
    still being forbidden from claiming it *wrote/logged* anything — today `chat.py:47-50` flatly says it
    "CANNOT … log friction", which would make the model refuse to draft (a functional gap, not just
    security). A prompt test asserts it contains "suggest/prefill" + "human applies via Concierge" and
    forbids "I logged/wrote". *(R4-S8 — static guard)* a CI test asserts the module defining `POST /chat`
    **never imports** `apply_concierge_plan` / `apply_write_plan` / the `concierge/writes` apply paths —
    "the loop never posts" is enforced by an import guard, not convention.
- **FR-WM2-7 — Propose-only writes (bridge, not a new write path).** The assistant may *draft* a
  friction entry or *prefill* an instantiate posture; the UI renders those as a **prefilled form** that
  posts to the existing `/concierge/friction` / `/concierge/instantiate` endpoints. The human reviews
  and submits; the existing preview-then-apply + CSRF + loopback + one-time-intent gates are unchanged.
  The loop never calls those endpoints itself.
  - **Acceptance (CRP R1–R4):**
    - *(R1-F1/R1-S3/R4-F2/R4-S2 — server-produced, bounded `propose`)* drafts arrive as a
      **server-produced, server-validated** `propose` object in the `/chat` JSON (`friction` triple +
      `posture` enum), extracted from the `AgenticResult` (structured output / a constrained slice —
      **never** a regex/loose parse of free-form assistant prose). `propose` is **omitted** when any
      field fails `validate_friction` / `VALID_POSTURES` or exceeds `FRICTION_FIELD_MAX`. The client may
      only populate **empty** Concierge form fields; it must never treat assistant `text` as the
      authoritative prefill source.
    - *(invariant)* chat output can **never** supply `csrf` or `intent` tokens; the server **re-validates
      every field on apply** regardless of prefill origin (a tampered hidden intent/csrf still 403/409;
      chat-suggested text over the cap is still rejected on apply).
    - *(R3-F2/R3-S2 — XSS)* assistant `text` and any `propose` value rendered into the home page are
      treated as **untrusted**: server-escaped (`_esc`) or assigned via `textContent`/`value` — **never**
      `innerHTML`. Markup in a fixture reply renders as literal text and does not execute.
- **FR-WM2-8 — Graceful degradation & error containment.** If no agent can be resolved (missing API
  key, no provider), the chat panel renders a disabled state with an explanatory message and the rest
  of the home page is unaffected. Chat failures **never** 500 the home page; `GET /` never awaits chat.
  - **Acceptance (CRP R1–R4):**
    - *(R1-F2/R1-S4 — mid-conversation provider failure)* provider 401/429/timeout/infra errors on a
      turn return a typed `chat_error` (e.g. `chat_provider_timeout`) JSON with a **sanitized** message
      — no API-key substrings, no raw provider body; `GET /` remains 200. A response-body grep asserts
      no `sk-`/`ANTHROPIC` fragments leak.
    - *(R4-F3/R4-S3 — agentic stop_reason)* when `AgenticResult.stop_reason` is not `completed`
      (`max_turns` / `budget` / `context_overflow` / `repeated_calls` / `stream_error`), `/chat` returns
      typed `{ok: false, code: chat_<reason>}` (200/503, never 500). This is a **distinct failure class**
      from provider HTTP errors and is testable with fixture configs (no provider mock for `max_turns`).
    - *(R2-F3/R2-S4 — feature-mode parity)* in `preview`/`inspect` serve modes the chat panel is disabled
      and `POST /chat` returns typed `preview_only` (mirrors capture/Concierge write refusal) — a
      read/preview serve must never spend tokens.
- **FR-WM2-9 — Cost visibility & budget guard.** Each assistant turn surfaces the per-turn cost line
  (`KickoffChat.cost_line`: turns / tokens / `cost≈$`, plus `stop_reason` when not `completed`), so the
  one non-`$0` surface is honest about spend.
  - **Acceptance (CRP R1–R4):** *(R1-F4/R1-S5/R2-F1/R2-S1/R4-F4/R4-S4 — budget via `SessionConfig`,
    one source of truth)* per-session **turn / token / cost** limits are enforced via the
    `AgenticSession` `SessionConfig` (`max_turns`, `max_total_tokens`, `max_cost_usd`, **and**
    `max_tool_calls_per_turn`) — **not** ad-hoc counters duplicated in `_ChatStore` (the agentic layer
    already accumulates totals and returns `stop_reason ∈ {budget, max_turns, …}`). Crossing a documented
    ceiling surfaces as a typed `chat_budget_exceeded` refusal (never a 500), while download/overview keep
    working. Web and CLI consume **one shared `SessionConfig` factory** (see FR-WM2-15) so the loop-safety
    envelope is identical across surfaces.

### C. Complete the template set (P3)

- **FR-WM2-10 — Author the missing authoring guidance** *(narrowed by planning: the 11 packaged
  templates all exist; this is the **only** genuinely missing file)*. Author
  `templates/authoring/conventions.md` (the one input domain missing per-domain guidance), matching the
  structure/voice of the existing `business-targets.md` / `observability.md` / `build-preferences.md`,
  and covering the `conventions.yaml` fields (stack, module paths, naming, `data_model:` cross-cutting
  choices, field authorship) and the production-vs-prototype authorship rule (`KICKOFF_INPUT_PACKAGE_GUIDE.md`
  §5).
- **FR-WM2-11 — A named, complete manifest.** A single manifest (the FR-WM2-4 accessor, plus a short
  human index doc) enumerates the complete downloadable set and is the assertion target for "the set
  is complete." Adding a template without adding its manifest row fails a test.
- **FR-WM2-12 — Verify completeness.** A test asserts every manifest entry resolves to a readable
  packaged template and that the package + authoring quintet are all present (no missing file, no
  orphan manifest row).

### D. Boundaries & cross-cutting

- **FR-WM2-13 — MCP unchanged.** No new MCP surface. Download and chat are web/CLI only; the MCP
  Concierge stays read/preview-only (inherited NR).
- **FR-WM2-14 — Observability.** New funnel events: `template_downloaded` (key, group),
  `template_bundle_downloaded`, `chat_turn` (turns, tokens, cost — **no** message text),
  `chat_unavailable` (degraded reason). Event attributes exclude user message text and raw paths
  (inherited privacy contract).
  - **Acceptance (CRP R1–R4):** *(R3-F3/R3-S3 — register in the module, don't scatter strings)* all WM2
    events are added to `kickoff_experience/telemetry.py` `FUNNEL_EVENTS` with a `WM2_EVENT_ATTR_ALLOWLIST`
    mirroring `CONCIERGE_EVENT_ATTR_ALLOWLIST`, and emitted via `emit()` — not ad-hoc strings in `web.py`
    (the shipped `record_events()` harness then CI-guards them). *(R2-F4 — name the refusal modes)* the
    vocabulary includes the chat refusal/infra events: `chat_rate_limited`, `chat_budget_exceeded`,
    `chat_session_expired`, `chat_busy`, `message_too_long`, `chat_provider_timeout`, `chat_<stop_reason>`,
    `preview_only` — each with bounded attributes (and a `stop_reason` attribute on `chat_turn`), all
    **excluding** message text and raw filesystem paths.
- **FR-WM2-15 — Parity where it applies.** Download is web-only (no TUI download); chat already has a
  CLI surface (`kickoff chat`) — 2.0 adds the *web* surface over the *same* registry, so behavior is
  equivalent by shared construction, not re-implemented.
  - **Acceptance (CRP R1–R4):** *(R4-F4/R4-S4 — shared loop-safety envelope)* web (`_ChatStore`) and CLI
    (`chat_cmd`) construct `new_kickoff_chat` from **one documented `SessionConfig` factory**
    (`kickoff_chat_session_config()`), so `max_turns` / `max_cost_usd` / `max_total_tokens` /
    `max_tool_calls_per_turn` are identical across surfaces — a test asserts the two config objects are
    equal. Parity is "same registry **and** same loop bounds," not just the same tools.

### E. Validation & Release Gates (CRP R1–R4)

- **FR-WM2-16 — One-inventory bijection gate** *(R1-S8, R3-S6)*. CI asserts `kickoff_template_manifest()`
  keys **biject** with `_KICKOFF_FILES + _AUTHORING_FILES` template rels, that each row's `dest` equals
  the `build_instantiate_plan(...).writes[].path` set (at matching `with_authoring`), and that every
  `dest` is a safe relative path. Adding a row to one list without the accessor — or a traversal-shaped
  `dest` — fails CI before any route is reachable.
- **FR-WM2-17 — Write-route / read-floor CI gate** *(R4-S8, R1-S3)*. Before any chat code merges, CI
  proves: the `/chat` module imports **no** write-apply path; the registry tools ⊆
  `{survey, assess, field_states}`; `propose` is server-validated; preview/inspect mode refuses `/chat`;
  and telemetry excludes message text + raw paths. The group **fails** if a chat route ships without
  these guards. (Release-safety sequencing invariant, not a new implementation detail.)

### F. Phased / Later (accepted, deferred from v1)

> Accepted but deferred to keep the first cut focused on the security-essential mechanisms. Both are
> additive and non-blocking.

- **[Phase 2] New-conversation reset** *(R4-F6/R4-S6)*. A `POST /chat/reset` clears the current
  `_ChatStore` entry, mints a fresh `kickoff_chat` cookie, and returns `{ok: true}` **without** a
  provider call (no `chat_turn` emitted). User-facing recovery from a bad thread; idle expiry (FR-WM2-5)
  covers the v1 safety need.
- **[Phase 2] OTel trace nesting** *(R3-S8)*. Wrap `POST /chat` in `kickoff_span` so the built-in
  `AgenticSession` `agentic.session`/`agentic.turn` spans nest under `kickoff.session` (free
  observability; the funnel events in FR-WM2-14 are the v1 essential).

---

## 4. Non-Requirements

- **NR-1 — No write tools in the chat.** The agentic loop never gains `instantiate-kickoff` /
  `log-friction` / `derive-contract` tools. Propose-only is a UI bridge to the human-applied seam.
- **NR-2 — No MCP download/chat.** Neither new surface is exposed over MCP.
- **NR-3 — No arbitrary-file download.** Only the closed manifest key space; never a path parameter.
- **NR-4 — Not an operator.** Nothing here runs the cascade, records a gate, or deploys.
- **NR-5 — No re-implementation.** No second template loader, readiness computation, or write engine.
- **NR-6 — Assembly/manifest-grammar templates out of scope.** The data-model contract, assembly
  manifests, and content prose (the "deliberately NOT in the package" set, `KICKOFF_INPUT_PACKAGE_GUIDE.md`
  §1) are **not** part of 2.0's downloadable set. 2.0 ships the kickoff-package + authoring quintet only.

---

## 5. Open Questions

*5 of 7 resolved by the planning pass — see §0 for rationale + citations. Retained for the record.*

- **OQ-1 — RESOLVED → new `_ChatStore`** (session-id → `KickoffChat` + last-used + turn count; idle
  expiry + bounded entries), modeled on `_SessionStore`. The CSRF store cannot hold chat history.
- **OQ-2 — RESOLVED → `async def POST /chat`** calling `await chat.ask(...)` (uvicorn owns the loop;
  the CLI `asyncio.run` bridge is not reused).
- **OQ-3 — RESOLVED → one agent per server**, `--agent` on `serve`/`start`, default
  `Models.CLAUDE_SONNET_LATEST`, resolved with the CLI's existing `resolve_agent_spec` degradation.
- **OQ-6 — RESOLVED → inline chat panel on `/`** (single home page), not a separate `/chat` page.
- **OQ-7 — RESOLVED → per-session turn cap** in `_ChatStore` (the cost guard the paid surface needs),
  distinct from the capture rate-limit.
- **OQ-4 — RESOLVED (CRP R1) → zip with a hard uncompressed-bytes ceiling** (≤2 MB), typed 413
  `bundle_too_large` on exceed, no partial archive. Folded into FR-WM2-3.
- **OQ-5 — RESOLVED (CRP R1) → v1 ships the 11 packaged `concierge_templates/` files only** (NR-6);
  the per-domain authoring guidance (`templates/authoring/*.md`, incl. the new `conventions.md`) is
  **linked** from the download index (FR-WM2-11), **not** packaged — packaging is an additive follow-on
  if users need offline guidance bytes. Folded into FR-WM2-11 / NR-6.

---

*v0.2 — Post-planning self-reflective update. The planning pass falsified 3 assumptions and confirmed
2: chat **does** need new plumbing (agent threading + `_ChatStore`) — P-A softened; "author the missing
templates" **is** thin — only `conventions.md` (FR-WM2-10 narrowed); download **is** trivial but its
real risk is path-traversal, mitigated by manifest-key closure (FR-WM2-2/NR-3). 1 requirement softened
(P-A), 1 narrowed (FR-WM2-10), 2 extended (FR-WM2-4 posture parity, FR-WM2-5 async/store), 5 of 7 open
questions resolved.*

*v0.3 — Post-CRP R1–R4 (4 independent reviewers: composer-2.5, claude-sonnet-4-6, gemini-3.1-pro,
gpt-5.5-extra-high; strong cross-endorsement, zero disagreements). Policy: **accept all, phase 2
nice-to-haves.** All 28 requirements suggestions accepted — **26 merged** as consolidated
`Acceptance (CRP R1–R4)` criteria on FR-WM2-1/2/3/4/5/6/7/8/9/14/15 (separate chat session cookie +
bootstrap + memory-wipe, per-session concurrency lock, message-length cap, chat Host+rate-limit, stable
`/chat` JSON schema, end-to-end `--agent` threading, prompt alignment + write-import guard,
server-produced+validated `propose`, XSS-safe render, mid-turn + `stop_reason` degradation, preview-mode
gate, `SessionConfig` budget guard, shared `SessionConfig` factory, key-encoding closure, content-type +
posture validation, `with_authoring` split + triple-byte parity, zip ceiling + zip-slip guard,
telemetry-module registration); **2 new gates** added in §E (FR-WM2-16 bijection, FR-WM2-17 write-route
CI); **2 phased** to §F (new-conversation reset, OTel nesting). OQ-4 + OQ-5 resolved. Both R4 blocks were
double-appended by the reviewer; triaged once. Dispositions in Appendix A; rounds verbatim in Appendix C.
Ready for implementation (download pillar first; `conventions.md` already authored + validated).*

---

## Appendix A — Accepted (with where merged)

> Triage R1–R4 (orchestrator, 2026-06-26). **All 28 requirements suggestions accepted; none rejected.**
> Heavy cross-round overlap was deduped into consolidated `Acceptance (CRP R1–R4)` criteria. Note: the
> reviewer **double-appended R4** (Appendix C carries two identical R4 blocks) — triaged once.

**Chat session identity & lifecycle → FR-WM2-5**
- R1-F3 / R1-S2 / R4-F5 / R4-S5 — separate server-issued `kickoff_chat` cookie (httponly+strict),
  bootstrapped on `GET /`, `chat_session_expired` on miss → ACCEPTED.
- R3-F5 / R3-S5 — in-memory-only history, destroyed on idle expiry/eviction → ACCEPTED.
- R2-F7 / R2-S3 — per-session `asyncio.Lock` / `chat_busy` concurrency guard → ACCEPTED.
- R2-F6 / R2-S5 — inbound `message` length cap (`message_too_long`, no provider call) → ACCEPTED.
- R1-S1 — `/chat` loopback `_host_ok` + per-session rate limit (`chat_rate_limited`) → ACCEPTED.
- R3-F7 / R3-S7 — stable `POST /chat` JSON schema → ACCEPTED.
- R4-F1 / R4-S1 — end-to-end `--agent` threading (`start`→`serve_kickoff`→`build_kickoff_app`) → ACCEPTED.

**Read-only floor & propose bridge → FR-WM2-6 / FR-WM2-7**
- R2-F2 / R2-S2 — update `KICKOFF_SYSTEM_PROMPT` for propose-only drafting → ACCEPTED (FR-WM2-6).
- R4-S8 — static write-import guard on the `/chat` module → ACCEPTED (FR-WM2-6 + §E FR-WM2-17).
- R1-F1 / R1-S3 / R4-F2 / R4-S2 — server-produced, server-validated bounded `propose`; never parse prose;
  never supply csrf/intent; re-validate on apply → ACCEPTED (FR-WM2-7).
- R3-F2 / R3-S2 — XSS-safe render/prefill (escape / `textContent`, never `innerHTML`) → ACCEPTED (FR-WM2-7).

**Degradation, stop_reason, budget → FR-WM2-8 / FR-WM2-9 / FR-WM2-15**
- R1-F2 / R1-S4 — mid-conversation provider-failure degradation + sanitized `chat_error` → ACCEPTED (FR-WM2-8).
- R4-F3 / R4-S3 — `AgenticResult.stop_reason` → typed `chat_<reason>` codes → ACCEPTED (FR-WM2-8).
- R2-F3 / R2-S4 — preview/inspect mode disables chat + `preview_only` → ACCEPTED (FR-WM2-8).
- R1-F4 / R1-S5 / R2-F1 / R2-S1 / R4-F4 / R4-S4 — budget via `AgenticSession` `SessionConfig` (incl.
  `max_tool_calls_per_turn`), one shared factory, `chat_budget_exceeded` → ACCEPTED (FR-WM2-9 + FR-WM2-15).

**Download closure, parity, content-type → FR-WM2-1/2/3/4**
- R1-F5 / R1-S6 — manifest-key encoding closure (unquote-once, exact match, reject `..`/`%2e%2e`/leading `/`) → ACCEPTED (FR-WM2-2).
- R2-S8 — per-entry `Content-Type` + `charset=utf-8`, filename = `dest` basename → ACCEPTED (FR-WM2-2).
- R4-F7 / R4-S7 — `posture_invalid` typed 400 on tampered query → ACCEPTED (FR-WM2-2/3).
- R1-F6 / R1-S7 — zip uncompressed-bytes ceiling + 413 (closes OQ-4) → ACCEPTED (FR-WM2-3).
- R3-F6 / R3-S6 — zip-slip `dest` guard (safe relative paths) → ACCEPTED (FR-WM2-3 + §E FR-WM2-16).
- R3-F1 / R3-S1 — `with_authoring` split (6 vs 11), `group` tag, bundle filter, parity at matching flags → ACCEPTED (FR-WM2-4).
- R2-F5 / R2-S6 — triple-byte parity (single / bundle / instantiate) × all keys × postures → ACCEPTED (FR-WM2-4).
- R1-S8 — manifest↔lists bijection + dest=plan-paths test → ACCEPTED (§E FR-WM2-16).
- R3-F4 / R3-S4 — posture selector on the download index → ACCEPTED (FR-WM2-1).
- R2-S7 — home-page Concierge `next_action` CTA + templates link → ACCEPTED (FR-WM2-1).

**Observability → FR-WM2-14**
- R3-F3 / R3-S3 — register WM2 events in `telemetry.py` `FUNNEL_EVENTS` + attr allowlist → ACCEPTED.
- R2-F4 — name the chat refusal/infra events (+ `stop_reason` attr) → ACCEPTED.

**Phased to §F (accepted, deferred):** R4-F6 / R4-S6 (new-conversation reset), R3-S8 (OTel span nesting).

## Appendix B — Rejected (with rationale)

<!-- F-<n> / S-<n> — <suggestion> → REJECTED; <why>. -->
*None.* All R1–R4 suggestions were grounded in live code, strengthened (never re-litigated) the settled
v0.4 boundaries, and were mutually consistent — accepted in full (2 phased, not rejected).

## Appendix C — Incoming review rounds

<!-- #### Review Round R{n} — <model-id> — <UTC date> -->
*(none yet.)*

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
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2.5 — 2026-06-26

- **Reviewer**: composer-2.5
- **Date**: 2026-06-26 19:35:00 UTC
- **Scope**: Requirements quality for Welcome Mat 2.0 R1 — chat security acceptance criteria, download key closure, OQ-4/OQ-5 resolution.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | Add acceptance criteria to **FR-WM2-7** for the propose-only bridge. The requirement says the assistant may "prefill" a form posting to `/concierge/friction` / `/concierge/instantiate`, but does not state that (a) chat output cannot supply `csrf`/`intent` tokens, (b) prefill field lengths are bounded by the same caps as direct submit (`validate_friction` / `FRICTION_FIELD_MAX` in the shipped Concierge layer), and (c) the server re-validates all fields on apply regardless of prefill source. | Without these criteria, an implementer could treat chat text as trusted input and weaken the settled human-privilege seam. | FR-WM2-7 bullet "prefilled form that posts to the existing … endpoints" | Test: chat-suggested friction text over max length is rejected on apply; tampered hidden intent/csrf still 403/409. |
| R1-F2 | Security | high | Extend **FR-WM2-8** beyond startup `agent=None` to mid-conversation failures on `POST /chat`. The text says "Chat failures never 500 the home page" but only exemplifies missing agent/key at resolve time (`OQ-3`). Add acceptance: provider 401/429/timeout/infra errors on a chat turn return a typed `chat_error` JSON with sanitized message (no API key substrings); `GET /` remains 200. | Users with a valid key still hit transient provider failures; FR-WM2-8 as written is untestable for the common failure mode. | FR-WM2-8 | Simulate provider exception in `/chat` test → typed body, overview still renders. |
| R1-F3 | Security | high | Specify session identity in **FR-WM2-5**: `_ChatStore` is keyed by a **server-issued** httponly+SameSite=strict `kickoff_chat` cookie (or equivalent), distinct from `kickoff_csrf`. Reject missing/expired chat session with typed `chat_session_expired`. The requirement says "session-id → KickoffChat" modeled on `_SessionStore` but does not forbid reusing the CSRF token. | Reusing CSRF for chat couples unrelated surfaces and weakens fixation resistance for a stateful, paid session. | FR-WM2-5 `_ChatStore` paragraph | Test chat session cookie required; CSRF alone cannot authenticate `/chat`. |
| R1-F4 | Ops | medium | Extend **FR-WM2-9** with a cumulative per-session budget guard, not only the turn cap (`OQ-7`). Require tracking aggregate `tokens` and `cost_usd` across turns in `_ChatStore` and a typed `chat_budget_exceeded` refusal when a documented ceiling is crossed. | "Each assistant turn surfaces … cost≈$" is honest per turn but does not prevent a single or cumulative overspend before turn cap. | FR-WM2-9 | Test cumulative usd over ceiling → typed refusal on next `/chat`. |
| R1-F5 | Validation | medium | Tighten **FR-WM2-2** acceptance for manifest keys: after `urllib.parse.unquote`, lookup is **exact** against the closed manifest key set; reject `..`, `%2e%2e`, leading `/`, and unknown keys with typed 404. Document whether keys use slashes (`package/kickoff-intro`) and how the route encodes them. | "Manifest key, not a path" is the right invariant, but implementers need the encoding edge cases spelled out to make NR-3 testable. | FR-WM2-2 | Fuzz tests for encoded traversal segments → 404; valid slash key → 200 attachment. |
| R1-F6 | Ops | low | Close **OQ-4** in **FR-WM2-3**: bundle zip built in-memory must enforce a maximum total uncompressed bytes (document the number); exceed → typed 413, no partial archive streamed. | OQ-4 is still open; without a numeric ceiling the requirement is not fail-closed. | FR-WM2-3 + §5 OQ-4 | Oversized fixture manifest → 413; normal set → 200 zip. |
| R1-F7 | Ops | low | Resolve **OQ-5** for v1: downloadable bytes remain the 11 packaged `concierge_templates/` files (NR-6); per-domain authoring guidance (`templates/authoring/*.md`, incl. new `conventions.md`) is linked from the human index (FR-WM2-11) but **not** packaged until explicitly added to `concierge_templates/`. | Packaging authoring markdown is an additive decision with scope creep risk; linking satisfies user discoverability without a second loader. | §5 OQ-5 + FR-WM2-11 index doc | Download manifest contains 11 entries only; index page links to authoring docs paths. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — first round.

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-26

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-26 20:10:00 UTC
- **Scope**: R2 requirements pass — SessionConfig alignment, prompt/FR-WM2-7 consistency, mode gates, parity acceptance depth, telemetry codes.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Architecture | medium | Extend **FR-WM2-5** to state that per-session turn/token/cost limits are enforced via `AgenticSession` `SessionConfig` (`max_turns`, `max_total_tokens`, `max_cost_usd`), not ad-hoc counters in `_ChatStore` alone. The requirement says "`_ChatStore` … turn count" and OQ-7 resolves a turn cap, but `agents/agentic.py:232-239` already provides budget stops with `stop_reason`. | Without this, implementers may duplicate budget logic R1-S5 proposed, drifting from the agentic layer's authoritative totals. | FR-WM2-5 `_ChatStore` paragraph + OQ-7 | Test: `SessionConfig(max_cost_usd=…)` refusal surfaces as typed `chat_budget_exceeded` using `AgenticResult` fields. |
| R2-F2 | Interfaces | medium | Add acceptance to **FR-WM2-6** / cross-ref **FR-WM2-7**: the web chat system prompt must be updated so the assistant may *suggest* friction/instantiate drafts for Concierge prefill but must never claim to have written files. Today `chat.py:47-50` forbids logging friction entirely, which blocks the FR-WM2-7 user value. | Read-only floor is preserved by registry tools; the *prompt* is the missing contract for propose-only drafting. | FR-WM2-6 + FR-WM2-7 | Prompt content test or snapshot: contains "suggest/prefill" and "human applies via Concierge"; forbids "I logged/wrote". |
| R2-F3 | Security | medium | Extend **FR-WM2-8** (or add NR) for feature-mode degradation: in `preview`/`inspect` serve modes, chat panel is disabled and `POST /chat` returns typed `preview_only` — matching capture/concierge write refusal. FR-WM2-8 only covers missing agent/key at startup. | Least-privilege parity across write and paid surfaces; preview mode must not silently spend. | FR-WM2-8 or new NR under §4 | `mode=preview` → disabled panel + `/chat` 403. |
| R2-F4 | Ops | medium | Extend **FR-WM2-14** with chat refusal/infra event names absent from R1: `chat_rate_limited`, `chat_budget_exceeded`, `chat_session_expired`, `chat_busy`, `message_too_long`, `chat_provider_timeout`, each with bounded attributes (no message text). R1 coverage matrix flagged telemetry gaps for chat guards. | Funnel/dashboard cannot distinguish chat failure modes without named events. | FR-WM2-14 event list | `record_events()` asserts event + attributes on each refusal path; grep excludes user message text. |
| R2-F5 | Validation | medium | Strengthen **FR-WM2-4** acceptance: byte identity must hold for **every** manifest entry across single download, bundle zip entry, and instantiate plan content at the same posture — not only the `conventions.yaml` example. | Single-file example is insufficient for P-E "one inventory, two consumers" when three delivery shapes exist. | FR-WM2-4 verify bullet | Parametrized test over all manifest keys × postures. |
| R2-F6 | Security | medium | Add to **FR-WM2-5**: inbound user messages to `POST /chat` are length-capped (document max); exceed → typed `message_too_long` without invoking the provider. | Unbounded user input is a cost/latency vector distinct from turn/cost caps. | FR-WM2-5 endpoint bullet | 10k-char POST → 400, agent mock not called. |
| R2-F7 | Risks | medium | Add to **FR-WM2-5**: at most one in-flight `POST /chat` per chat session; concurrent requests receive typed `chat_busy` or are queued — `AgenticSession` history must not be mutated concurrently. | Async handler does not imply concurrency safety for stateful sessions. | FR-WM2-5 | Parallel POST test with same session cookie. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F2: Mid-conversation provider failures must be in FR-WM2-8 acceptance.
- R1-F3: Separate chat session cookie must be specified in FR-WM2-5.
- R1-F4: Cumulative budget guard belongs in FR-WM2-9 (complements R2-F1 SessionConfig wiring).
- R1-F6: OQ-4 zip byte ceiling should close in FR-WM2-3.
- R1-F7: OQ-5 v1 defer (index link only) is the right scope trade-off.

#### Review Round R3 — gemini-3.1-pro — 2026-06-26

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-26 21:05:00 UTC
- **Scope**: R3 requirements — `with_authoring` drift, XSS acceptance, telemetry module contract, session memory, JSON schema, zip-slip.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Data | high | Clarify **FR-WM2-4** for the `with_authoring` split. The requirement says the manifest derives from `_KICKOFF_FILES + _AUTHORING_FILES`, but `build_instantiate_plan` defaults to `with_authoring=False` and writes only the 6 package files (`writes.py:91`). Add acceptance: manifest rows carry `group: package \| authoring`; bundle download accepts `with_authoring` (default `true` for full set or `false` to match instantiate default); byte parity tests compare download/instantiate at the **same** `with_authoring` and `posture`. | Without this, "one inventory, two consumers" is false for the default instantiate path — users get 11 files from download but Concierge scaffolds 6 unless they opt in. | FR-WM2-4 bullet "derived from" + FR-WM2-3 | Parametrize `with_authoring` × posture; assert dest sets match `build_instantiate_plan`. |
| R3-F2 | Security | high | Add acceptance to **FR-WM2-5** / **FR-WM2-7**: assistant reply text and any `propose` prefill values rendered or injected into the home-page HTML must be treated as **untrusted** — escaped on server render (`_esc`) or applied via `textContent`/`value` only; never `innerHTML`. The requirements pin a read-only tool floor but do not mention XSS from model output on the new web panel. | FR-WM2-7 prefill is a new DOM injection surface; bounded JSON fields can still carry HTML metacharacters. | FR-WM2-5 panel bullet + FR-WM2-7 prefill bullet | Markup in fixture assistant text does not execute; textarea values match literal string. |
| R3-F3 | Ops | medium | Tighten **FR-WM2-14**: new WM2 funnel events (`template_downloaded`, `template_bundle_downloaded`, `chat_turn`, `chat_unavailable`, plus refusal codes from R2-F4) must be added to `kickoff_experience/telemetry.py` `FUNNEL_EVENTS` with a bounded attribute allowlist (no message text, no raw filesystem paths) — not emitted as ad-hoc strings only in `web.py`. | The shipped telemetry module is the single funnel vocabulary (`telemetry.py:36-60`); FR-WM2-14 names events not yet registered there. | FR-WM2-14 event list | Import test: all FR-WM2-14 event names ∈ `FUNNEL_EVENTS`; `record_events()` smoke test. |
| R3-F4 | Interfaces | medium | Extend **FR-WM2-1**: the download index must expose a **posture selector** (prototype/production) on download links, and — if R3-F1 closes the `with_authoring` call — a toggle matching instantiate's optional authoring trio. FR-WM2-1 lists label/dest/group/size but not posture, yet FR-WM2-4 requires posture substitution on `conventions.yaml`. | End users cannot discover `?posture=production` without reading the plan; conventions bytes depend on it. | FR-WM2-1 download surface bullet | Index HTML contains posture control; production download matches `_POSTURE_CONVENTIONS["production"]`. |
| R3-F5 | Security | medium | Add to **FR-WM2-5**: `_ChatStore` holds conversation history **in memory only** (never persisted to disk); on idle expiry or eviction the session entry and `AgenticSession` message list are destroyed. Reject expired sessions with `chat_session_expired`. | Stateful paid sessions carry sensitive project context; TTL without destruction leaves RAM retention and breaks the privacy contract implied by FR-WM2-14 ("no message text" in telemetry). | FR-WM2-5 `_ChatStore` paragraph | Expired session → history inaccessible; no `.startd8/` chat artifact written. |
| R3-F6 | Validation | low | Extend **FR-WM2-3**: every zip entry path must equal a manifest `dest` that passes validation (relative, no `..`, no leading slash). Reject invalid manifest rows at accessor time. | Zip-slip defense even with closed keys — `dest` is the archive member path. | FR-WM2-3 + FR-WM2-12 | Fixture bad `dest` fails manifest/CI test before route is reachable. |
| R3-F7 | Interfaces | medium | Specify a **stable JSON response schema** for `POST /chat` in **FR-WM2-5**: success `{ok: true, text, cost: {turns, tokens, usd}, propose?}`; refusal/error `{ok: false, code, message?}` with codes from R2-F4. The requirement says the endpoint returns the assistant turn but does not define the machine contract the inline panel consumes. | Underspecified boundary between S6 and S7 enables client/server drift on `propose` and error shapes. | FR-WM2-5 "`async def POST /chat`" bullet | JSON schema or snapshot tests for success, `chat_budget_exceeded`, and `chat_error`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: FR-WM2-7 must forbid chat-supplied csrf/intent and require server re-validation on apply.
- R1-F3: Separate `kickoff_chat` cookie in FR-WM2-5.
- R2-F2: System prompt must allow suggest/prefill while forbidding claimed writes.
- R2-F7: Concurrent `/chat` requests must not corrupt session history.
- R2-F5: Per-file byte parity across all manifest entries (extends R3-F1's `with_authoring` dimension).

**Disagreements**: none.

#### Review Round R4 — gpt-5.5-extra-high — 2026-06-26

- **Reviewer**: gpt-5.5-extra-high
- **Date**: 2026-06-26 22:15:00 UTC
- **Scope**: R4 requirements — agent CLI wiring acceptance, propose producer contract, agentic stop_reason errors, shared SessionConfig, session bootstrap/reset, posture validation.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Architecture | high | Extend **FR-WM2-5** / **FR-WM2-8** acceptance: `startd8 kickoff start --agent <spec>` resolves and threads the agent through `serve_kickoff` → `build_kickoff_app` (mirrors `chat_cmd`). FR-WM2-5 describes the web chat but OQ-3 resolution does not name the `start` command or `serve.py` pass-through — the default serve path is what users run. | Requirement is untestable on the primary launch path if only `build_kickoff_app` is mentioned abstractly. | FR-WM2-5 intro + §0 OQ-3 row | `kickoff start` with mock/fixture agent → enabled panel; omit flag + missing key → disabled panel, `GET /` still 200. |
| R4-F2 | Interfaces | high | Extend **FR-WM2-7**: the optional `propose` payload in the `/chat` JSON response must be **server-produced and validated** (bounded friction triple + posture enum); clients must not treat unstructured assistant `text` as the authoritative prefill source. Omit `propose` when validation fails. Cross-ref R1-F1 caps. | FR-WM2-7 describes UI prefill but not the machine contract for how drafts arrive — enables unsafe client parsing. | FR-WM2-7 prefill bullet | Server returns `propose` only on valid fields; oversize → absent; apply path still uses Concierge gates. |
| R4-F3 | Risks | medium | Extend **FR-WM2-8**: when `AgenticResult.stop_reason` is not `completed` (`max_turns`, `budget`, `context_overflow`, `repeated_calls`, `stream_error`), `/chat` returns typed `{ok: false, code: chat_<reason>}` with sanitized message; `GET /` remains 200. Distinct from provider HTTP errors (R1-F2). | Requirement only exemplifies missing agent at startup; agentic loop termination is a separate failure class with existing `stop_reason` vocabulary. | FR-WM2-8 | Fixture configs trigger each stop_reason → typed body; no provider mock required for `max_turns`. |
| R4-F4 | Architecture | medium | Extend **FR-WM2-9** / **FR-WM2-15**: web and CLI chat share one documented `SessionConfig` default (incl. `max_tool_calls_per_turn`) via a single factory function; per-turn cost line includes `stop_reason` when not `completed`. | FR-WM2-15 claims equivalent construction but does not require equivalent loop bounds — web could allow more tool calls per message than CLI. | FR-WM2-9 + FR-WM2-15 | Assert web `_ChatStore` and `new_kickoff_chat` in `chat_cmd` use identical config object. |
| R4-F5 | Security | medium | Add to **FR-WM2-5**: when chat is enabled, `GET /` issues the `kickoff_chat` httponly session cookie (alongside CSRF) before any `POST /chat`; missing/expired cookie → `chat_session_expired`. Complements R1-F3 separate cookie. | Defers session identity to first paid POST unless bootstrap is explicit — couples identity minting with spend. | FR-WM2-5 `_ChatStore` paragraph | `GET /` sets cookie; first POST succeeds without minting a new id mid-request. |
| R4-F6 | Interfaces | low | Add to **FR-WM2-5**: a **new conversation** action clears server-side chat history and re-issues the session cookie without provider calls. | User-facing recovery from bad threads; not covered by idle expiry alone (R3-F5). | FR-WM2-5 | Reset endpoint → empty history; no `chat_turn` event emitted. |
| R4-F7 | Validation | low | Extend **FR-WM2-2** / **FR-WM2-3**: `posture` query values outside `VALID_POSTURES` → typed 400 `posture_invalid`. FR-WM2-4 assumes posture substitution works but does not define invalid input handling. | Tampered download URLs are in scope for NR-3/key-closure sibling validation. | FR-WM2-2 + FR-WM2-3 | `?posture=invalid` → 400; default omitted → `prototype`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F2: Mid-conversation provider failures in FR-WM2-8 (complements R4-F3 agentic stops).
- R1-F3: Separate `kickoff_chat` cookie (R4-F5 adds bootstrap timing).
- R2-F2: Prompt must allow suggest/prefill (R4-F2 needs server-produced propose).
- R2-F7: Concurrent `/chat` must not corrupt history.
- R3-F2: XSS-safe render/prefill for assistant output.
- R3-F7: Stable `/chat` JSON schema should include `propose?` and `code` paths from R4-F2/F3.

**Disagreements**: none.

#### Review Round R4 — gpt-5.5-extra-high — 2026-06-26

- **Reviewer**: gpt-5.5-extra-high
- **Date**: 2026-06-26 22:15:00 UTC
- **Scope**: R4 requirements — agent CLI wiring acceptance, propose producer contract, agentic stop_reason errors, shared SessionConfig, session bootstrap/reset, posture validation.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Architecture | high | Extend **FR-WM2-5** / **FR-WM2-8** acceptance: `startd8 kickoff start --agent <spec>` resolves and threads the agent through `serve_kickoff` → `build_kickoff_app` (mirrors `chat_cmd`). FR-WM2-5 describes the web chat but OQ-3 resolution does not name the `start` command or `serve.py` pass-through — the default serve path is what users run. | Requirement is untestable on the primary launch path if only `build_kickoff_app` is mentioned abstractly. | FR-WM2-5 intro + §0 OQ-3 row | `kickoff start` with mock/fixture agent → enabled panel; omit flag + missing key → disabled panel, `GET /` still 200. |
| R4-F2 | Interfaces | high | Extend **FR-WM2-7**: the optional `propose` payload in the `/chat` JSON response must be **server-produced and validated** (bounded friction triple + posture enum); clients must not treat unstructured assistant `text` as the authoritative prefill source. Omit `propose` when validation fails. Cross-ref R1-F1 caps. | FR-WM2-7 describes UI prefill but not the machine contract for how drafts arrive — enables unsafe client parsing. | FR-WM2-7 prefill bullet | Server returns `propose` only on valid fields; oversize → absent; apply path still uses Concierge gates. |
| R4-F3 | Risks | medium | Extend **FR-WM2-8**: when `AgenticResult.stop_reason` is not `completed` (`max_turns`, `budget`, `context_overflow`, `repeated_calls`, `stream_error`), `/chat` returns typed `{ok: false, code: chat_<reason>}` with sanitized message; `GET /` remains 200. Distinct from provider HTTP errors (R1-F2). | Requirement only exemplifies missing agent at startup; agentic loop termination is a separate failure class with existing `stop_reason` vocabulary. | FR-WM2-8 | Fixture configs trigger each stop_reason → typed body; no provider mock required for `max_turns`. |
| R4-F4 | Architecture | medium | Extend **FR-WM2-9** / **FR-WM2-15**: web and CLI chat share one documented `SessionConfig` default (incl. `max_tool_calls_per_turn`) via a single factory function; per-turn cost line includes `stop_reason` when not `completed`. | FR-WM2-15 claims equivalent construction but does not require equivalent loop bounds — web could allow more tool calls per message than CLI. | FR-WM2-9 + FR-WM2-15 | Assert web `_ChatStore` and `new_kickoff_chat` in `chat_cmd` use identical config object. |
| R4-F5 | Security | medium | Add to **FR-WM2-5**: when chat is enabled, `GET /` issues the `kickoff_chat` httponly session cookie (alongside CSRF) before any `POST /chat`; missing/expired cookie → `chat_session_expired`. Complements R1-F3 separate cookie. | Defers session identity to first paid POST unless bootstrap is explicit — couples identity minting with spend. | FR-WM2-5 `_ChatStore` paragraph | `GET /` sets cookie; first POST succeeds without minting a new id mid-request. |
| R4-F6 | Interfaces | low | Add to **FR-WM2-5**: a **new conversation** action clears server-side chat history and re-issues the session cookie without provider calls. | User-facing recovery from bad threads; not covered by idle expiry alone (R3-F5). | FR-WM2-5 | Reset endpoint → empty history; no `chat_turn` event emitted. |
| R4-F7 | Validation | low | Extend **FR-WM2-2** / **FR-WM2-3**: `posture` query values outside `VALID_POSTURES` → typed 400 `posture_invalid`. FR-WM2-4 assumes posture substitution works but does not define invalid input handling. | Tampered download URLs are in scope for NR-3/key-closure sibling validation. | FR-WM2-2 + FR-WM2-3 | `?posture=invalid` → 400; default omitted → `prototype`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F2: Mid-conversation provider failures in FR-WM2-8 (complements R4-F3 agentic stops).
- R1-F3: Separate `kickoff_chat` cookie (R4-F5 adds bootstrap timing).
- R2-F2: Prompt must allow suggest/prefill (R4-F2 needs server-produced propose).
- R2-F7: Concurrent `/chat` must not corrupt history.
- R3-F2: XSS-safe render/prefill for assistant output.
- R3-F7: Stable `/chat` JSON schema should include `propose?` and `code` paths from R4-F2/F3.

**Disagreements**: none.
