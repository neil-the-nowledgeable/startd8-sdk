# SDK Capability Request — Content Pages Generation + Form System-Field Omission

**Date:** 2026-06-03 · **Origin:** `startd8` consumer repo (the StartDate app) · **Status:** ✅ IMPLEMENTED in SDK-home (2026-06-03)
**Consumer source of truth:** `strtd8/docs/USER_FACING_CONTENT_REQUIREMENTS.md` (v0.2, reflective-loop)
**Golden reference (working POC):** `strtd8/prisma/pages.yaml`, `strtd8/app/pages/*.md`, `strtd8/app/poc_pages.py`

> **Implementation status (SDK-home).** All citations below were verified at home (accurate; line
> numbers drift a few lines). Capabilities 1 & 2 are built + verified end-to-end against the golden
> reference; a third capability (UI-driven page authoring) was added on consumer request. Once
> regenerated against the live SDK, the consumer can delete `app/poc_pages.py` + `app/poc_server.py`.
>
> | Capability | Module(s) | CLI | Verified |
> |---|---|---|---|
> | **1 — Content pages** | `backend_codegen/pages_generator.py` (+ `_headers.header_pages`, `htmx_generator.render_base_template` nav, `drift._PAGES_KINDS`, `crud_generator.render_main` tolerant mount) | `generate backend --pages pages.yaml` | `/` + `/how-it-works` render w/ nav; nav on entity pages; `--check` in_sync; **`.md` edit ≠ drift**, `pages.yaml` edit = drift; **app runtime needs no `markdown`** |
> | **2 — Form omission** | `htmx_generator._writable_fields` (reuses `ai_layer._PROVENANCE_OMIT` + `is_id`) | (always) | `profile/form.html` shows only human fields; list/detail still display system fields |
> | **3 — Authoring UI** | `backend_codegen/pages_authoring.py` (`app/pages_io.py` + `app/pages_admin.py` + `_authoring.html`) | `generate backend --pages --pages-authoring` | `/ui/pages` create (atomic entry+`.md`, comment-preserving, dup-safe) + edit prose; `pyyaml` added only when authoring; design-time author + regenerate-to-publish |
>
> **Design key (Cap 1 drift vs prose):** the owned page **shell** template carries the 2-hash
> (schema + pages) header and contains no prose; the rendered markdown lives in an **untracked body
> fragment** `app/templates/pages/_<name>.body.html` (no header → outside `--check`). That is what
> lets "render at generate time" and "a `.md` edit never flags drift" both hold — the exact analogue
> of the AI layer, where the owned harness embeds only the prompt *path*.
>
> **Cap 3 model:** *design-time author + regenerate*. The `/ui/pages` UI writes the generator
> **inputs** (`pages.yaml` entry + `app/pages/*.md`); pages go live on the next `generate backend`
> (so a UI **create** correctly drifts `--check` until regen; a UI **prose edit** stays in_sync). The
> app never imports the SDK — the strict validator is **re-emitted as owned code** in `app/pages_io.py`,
> and `pyyaml` is added to the app's runtime deps **only** with `--pages-authoring`.
>
> **Write-surface review (2026-06-03, adversarial probe of the generated `pages_io.py`/`pages_admin.py`).**
> Two graceful-failure gaps fixed: **(F-A)** an odd-indent existing manifest made the safe-append reparse
> throw a raw `yaml.YAMLError` that bypassed the route handler → 500 (file was never corrupted; write is
> gated on a clean reparse) — now a friendly `PageError`; **(F-B)** `list_pages()` raised on a
> hand-corrupted manifest → 500 on the UI — views now degrade to a banner. Confirmed safe: path traversal
> (slugify + `parent == app/pages/` check), `safe_load`/`safe_dump` only, special-char titles round-trip,
> validate-before-write (a dup slug can't delete existing prose). **Accepted under NFR-UI-1 (local-first,
> single-user, no auth):** block-style/consistent-indent `pages:` only (others fail loud, no corruption),
> orphan-`.md` overwrite, concurrent-POST race, and **raw HTML in prose → self-XSS only.** The last three
> are the **default-on / multi-user gate items** for a full CRP — not blockers for the gated prototype.

> **Boundary (tekizai-tekisho).** The consumer owns the *content/UX contract*, the *manifest shape*, and
> the *operational evidence* below — those are first-hand and authoritative. The *generator capability*
> is SDK-home work: **implement it your way.** The SDK code citations here are **consumer-observed →
> verify-at-home**; they're a starting map, not a prescription. Where this doc and the SDK source
> disagree, the source wins.

---

## BLUF — two independent capabilities requested

1. **Content-pages generation.** Let `generate backend` emit owned, non-entity content pages (a home
   page at `/`, a "how it works" page, etc.) + a site nav, from a new `pages.yaml` manifest +
   markdown prose — analogous to how `ai_passes.yaml` drives the AI layer. Today `/` is 404 and
   `base.html` has no nav.
2. **Form system-field omission (small, independent).** The HTMX form generator emits *every* column
   as required — including `id`/`ownerId`/`source`/`confirmed`/`createdAt`/`updatedAt` — so users are
   asked to hand-type a CUID and timestamps. The SDK **already computes** the omission set for the AI
   edge schema; reuse it in the form generator.

These are decoupled — ship either independently.

---

## Why this is owned-generation, not LLM-authored

Content pages are mechanical (routes + templates + nav from a manifest); only the prose is authored.
This is the same boundary as the AI layer (prompts authored, glue generated) and matches
`IDEAL_TARGET_ARCHITECTURE` ("everything mechanical is generated for $0; UI templated from the
contract"). The prose is the *only* hand-authored surface, exactly like AI-pass prompts.

---

## Capability 1 — Content pages

### The contract (consumer-owned; validated by the POC)

A new `pages.yaml`, parsed with the **same strictness as `parse_ai_passes`** (`ai_layer.py:99` +
`_PASS_KEYS` at `:72` + unknown-key loud-fail at `:108`). Validated instance (golden reference):

```yaml
pages:
  - slug: "/"
    title: "StartDate — Land your next start date"
    nav_label: "Home"            # omit to exclude from nav
    content: pages/home.md       # markdown under app/pages/ (authored prose)
  - slug: "/how-it-works"
    title: "How StartDate works"
    nav_label: "How it works"
    content: pages/how_it_works.md
nav:                             # optional; else derive from nav_label + curated entities
  - { label: "Home",         href: "/" }
  - { label: "Profile",      href: "/ui/profile" }
  - { label: "Proof Points", href: "/ui/proofpoint" }
  - { label: "How it works", href: "/how-it-works" }
```

Allowed per-page keys: `slug` (req), `title` (req), `nav_label` (opt), `content` (req). Loud-fail on
unknown keys.

### Expected generated artifacts (the POC `poc_pages.py` is the executable reference)

| Artifact | Shape |
|---|---|
| `app/pages.py` | A `pages_router = APIRouter()` (mirror `web_router` at `htmx_generator.py:282`) with one GET route per `slug` rendering the page; mounted in `main.py` alongside `all_routers`/`web_router` (`crud_generator.py:128–150`) |
| Owned page template(s) | A content template extending `base.html`; carries the standard provenance header (`_headers.py:15`) |
| `base.html` nav | Inject a `<nav>` built from the manifest nav (today `render_base_template` at `htmx_generator.py:101` is a fixed string literal — needs a generator change; no new templating engine required) |

### Three operational findings from the POC (decide these, don't re-derive)

1. **Render markdown→HTML at GENERATE time, not request time.** The POC rendered at request time and
   had to add a `markdown` *runtime* dependency. Generate-time rendering into the owned template keeps
   the app runtime dependency-free and matches the static owned-generation model. (Tradeoff: a prose
   edit then needs a regen — acceptable, same as any owned artifact. Recommend keeping one drift model.)
2. **Nav must live in `base.html`.** A consumer can't add nav from outside (it would drift) — it's
   structurally an SDK change. The POC nav only appears on the content pages; the entity pages stay
   nav-less until `base.html` carries it.
3. **Nav/CTA links target `/ui/<entity>`, NOT `/<entity>/`.** The bare `/<entity>/` route returns
   **JSON** (the CRUD API); the human HTML pages are `/ui/profile`, `/ui/proofpoint`, … If nav is
   auto-derived from entities, derive it against the `/ui/` prefix.

### Drift / anchoring (mirror the AI layer)

- Generated page routes/templates + the modified `base.html` carry a provenance header and join
  `--check`. Use a three-input header like `header_ai_layer` (`_headers.py:26`): `schema + pages`
  (+ human-inputs if relevant).
- Prose (`app/pages/*.md`) is **outside** the hash — editing prose must not flag drift, same rule as
  AI-pass prompts.
- New `--pages PATH` flag on `backend()` (`cli_generate.py:109`, beside `--ai-passes` at `:132`);
  cap-dev-pipe `--lang python` passes it through. Inputs (`pages.yaml`, `app/pages/*.md`) get anchored.

### Acceptance
- `GET /` returns the rendered home page (HTML); `GET /how-it-works` renders; both carry the nav.
- Nav appears on **every** page (entity + content) and links resolve to `/ui/<entity>` + content slugs.
- `--check` reports `in_sync` after a clean generate; editing a `.md` does **not** flag drift; editing
  `pages.yaml` **does**.
- App runtime needs no markdown dependency.

---

## Capability 2 — Form system-field omission (FR-PG-5)

**Problem:** `app/templates/<entity>/form.html` lists every column as a labeled, `required` input —
including `id`, `ownerId`, `source`, `confirmed`, `createdAt`, `updatedAt`. Users are asked to type a
CUID and ISO timestamps. (Observed on the generated `profile/form.html`.)

**The fix is reuse, not new policy.** The SDK already defines the exact omission set for the AI edge
schema: `_PROVENANCE_OMIT = {"source", "confirmed", "ownerId", "createdAt", "updatedAt"}`
(`ai_layer.py:42`), applied at `:290–293` (also dropping PKs). The HTMX **form** generator
(`htmx_generator.py`) does not apply it. Apply the same omission (+ PK/`id`) in the form generator so
forms expose only human-authored fields, with human-readable labels.

**Acceptance:** `profile/form.html` shows only `name/title/company/industry/summary/...` — never
`id`/`ownerId`/`source`/`confirmed`/`createdAt`/`updatedAt`. System/provenance fields are auto-managed
(as they already are on create: `ownerId="local"`, `source="user"`, timestamps server-set).

---

## How to consume the golden reference

The POC is a hand-built stand-in for exactly what Capability 1 should generate. In `strtd8/`:
- `prisma/pages.yaml` — the manifest instance (the input contract).
- `app/pages/home.md`, `app/pages/how_it_works.md` — the authored prose (the only hand-authored surface).
- `app/poc_pages.py` — a throwaway router that reads the manifest, renders the markdown, serves the
  slugs, and emits the nav. **This is the reference behavior to generate** (it renders at request time;
  the SDK should do the equivalent at generate time per finding #1).
- Run it: `uvicorn app.poc_server:app --port 8766` → `/` and `/how-it-works` render with nav.

The durable artifacts (`pages.yaml`, the `.md` files) are intended to become real generator inputs
once Capability 1 lands; `poc_pages.py`/`poc_server.py` are throwaway and will be deleted.

---

## Citations (consumer-observed; verify-at-home)
- Strict manifest parse pattern: `ai_layer.py:99` (`parse_ai_passes`), `:72` (`_PASS_KEYS`), `:108` (unknown-key fail).
- Omission set to reuse: `ai_layer.py:42` (`_PROVENANCE_OMIT`), `:290–293`.
- Base template (string literal, no nav seam): `htmx_generator.py:101` (`render_base_template`).
- Web router pattern to mirror: `htmx_generator.py:282` (`web_router`); mount in `crud_generator.py:128–150` (`render_main`/`all_routers`).
- Provenance headers (1-input vs 3-input): `_headers.py:15` (`header_standard`), `:26` (`header_ai_layer`).
- CLI entry + flag precedent: `cli_generate.py:109` (`backend`), `:132` (`--ai-passes`).

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
| R1-F4 | Validator/`parse_pages` parity + contract test | CRP R1 | **Applied (code).** `pages_authoring._validate_all` now mirrors `parse_pages` (derived-name collision + `nav:` validation); pinned by `tests/unit/backend_codegen/test_pages_authoring.py::test_validator_matches_parse_pages`. Tracked as FR-UI-8 (plan §2.C). | 2026-06-03 |
| R1-F3 | Promote the supported-manifest-shape contract to normative | CRP R1 | **Applied (doc).** The write-surface review note already states "block-style/consistent-indent `pages:` only; others fail loud, no corruption"; recorded as a contract (the F-A fix is the enforcing code — write gated on a clean reparse). | 2026-06-03 |
| R1-F1 | Prose sanitization (generate-time `bleach` + CSP) | CRP R1 | **Accepted — deferred to gate.** Captured as plan **FR-UI-7** (§2.C). Self-XSS only under NFR-UI-1. | 2026-06-03 |
| R1-F2 | Concurrency optimistic version check | CRP R1 | **Accepted — deferred to gate.** Captured as plan **NFR-UI-5** (§2.C). | 2026-06-03 |
| R1-F5 | Endpoint hardening (size cap, symlink refusal, auth seam) | CRP R1 | **Accepted — deferred to gate.** Captured as plan **NFR-UI-2a** (§2.C). | 2026-06-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 (1m) — 2026-06-03

- **Reviewer**: claude-opus-4-8 (1m)
- **Date**: 2026-06-03 00:00:00 UTC
- **Scope**: Requirements (handoff doc) quality for the content-pages + authoring-UI capability, weighted toward the default-on / multi-user gate items. Findings anchored to the **built** code (`backend_codegen/pages_authoring.py`, `pages_generator.py`, `drift.py`, `cli_generate.py`).

##### Focus-file asks (addressed at top, per template; orchestrator triages later)

**Ask 1 — Raw-HTML self-XSS in prose → stored XSS at multi-user.**
- **Summary answer:** Partial — the doc names this a gate item but states no control, and the built `render_markdown` (`pages_generator.py:137-146`) passes raw HTML through with no allowlist/escape, so there is no acceptance criterion to verify against at the gate.
- **Rationale:** `render_markdown` calls `markdown.markdown(md_text, extensions=["extra","sane_lists"])` with no `bleach`/sanitizer; the rendered fragment is `{% include %}`'d unescaped (`pages_generator.py:205`). The handoff "Documented, not fixed" line ("raw HTML in prose → self-XSS only … GATE ITEM: sanitize before any multi-user/default-on exposure") records the risk but the requirements section (FR-UI-2) only says "raw markdown — no rendering at write time," giving an implementer no testable control.
- **Assumptions / conditions:** holds if multi-user/default-on is ever pursued; under NFR-UI-1 (single-user) it is correctly out of scope.
- **Suggested improvements:** add a gate-conditional requirement (see R1-F1) that fixes the control point (SDK generate-time sanitize via a `bleach` allowlist applied inside `render_markdown`, plus an app-served `Content-Security-Policy`), and an acceptance test that a `<script>` in a `.md` is neutralized in the emitted `_<name>.body.html`.

**Ask 2 — Concurrent-POST race on `pages.yaml`/`.md`.**
- **Summary answer:** Partial — the doc acknowledges the race but the requirements give no mechanism, and the built `append_page` (`pages_authoring.py:161-181`) is a bare read-modify-write with no lock or version check.
- **Rationale:** `append_page` does `read_text` → text-insert → `write_text` (`pages_authoring._PAGES_IO_BODY` lines 167-180) with no file lock or compare-and-swap; two concurrent `POST /ui/pages` lose one update. NFR-UI-1 scopes this out for single-user, but the gate decision needs a stated minimal mechanism.
- **Assumptions / conditions:** only matters at shared/multi-user exposure.
- **Suggested improvements:** see R1-F2 — require an optimistic version check (hash the manifest read at form-render, refuse the write if it changed) as the minimal correct mechanism, since it needs no new runtime dep beyond what authoring already adds.

**Ask 3 — Broader manifest shapes.**
- **Summary answer:** Yes — "fail-loud + document the supported shape" is acceptable under the no-SDK-import / minimal-deps constraint; the built code already fails safe (write gated on a clean reparse, `pages_authoring.py:172-179`).
- **Rationale:** `_insert_into_pages_block` only matches a block-style `^pages\s*:\s*$` line (`pages_authoring.py:141`); flow-style/odd-indent raises a friendly `PageError` and never corrupts (the F-A fix). Round-tripping arbitrary valid YAML would require `ruamel.yaml`, violating NFR-UI-4 (minimal deps). The gap is that the **supported shape is not stated in the requirements** — only in a build-time review note.
- **Assumptions / conditions:** none.
- **Suggested improvements:** see R1-F3 — promote the supported-shape contract (block-style, consistent-indent `pages:`) into a normative requirement with the fail-loud guarantee as an acceptance criterion.

**Ask 4 — Generated-owned validator drifting from SDK `parse_pages`.**
- **Summary answer:** No — they are **already divergent in the shipped code**, and nothing keeps them in sync.
- **Rationale:** SDK `parse_pages` rejects pages whose slugs collide to the same derived file-name (`pages_generator.py:104-106`) and validates `nav:` items (`:108-121`); the emitted `_validate_all` (`pages_authoring.py:93-113`) checks slug dups but **not** derived-name collisions and **not** `nav:` at all. (`validate_new` adds a name-collision check at *append* time, `pages_authoring.py:125-127`, but `_validate_all` — the "re-parse the full file" gate FR-UI-1 relies on — does not.) Worse, the authoring artifacts are registered as **schema-only 1-hash** kinds (`drift.py:101-103`, `pages_authoring.AUTHORING_KINDS`), so a change to `parse_pages`'s rules never marks `pages_io.py` stale. A UI can therefore accept a manifest the next `generate backend --pages` rejects.
- **Assumptions / conditions:** none — this is a present defect, not a future one.
- **Suggested improvements:** see R1-F4 (shared contract test asserting `_validate_all` accepts/rejects the same manifests as `parse_pages`) and R1-S4 in the plan (close the name-collision/nav gap).

**Ask 5 — Disk-write endpoint as attack surface.** **Ask 6 — Atomicity/rollback completeness.** Addressed via R1-F5 (requirements gap: no path/size/symlink/rate limits stated) and R1-S5 (plan: crash-window between prose write and manifest commit).

##### Feature Requirements Suggestions (F-prefix)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | Add a gate-conditional requirement "FR-UI-7 (multi-user gate) — prose sanitization": before default-on/multi-user, raw HTML in `.md` MUST be sanitized at generate time via a `bleach` tag/attr allowlist inside `render_markdown`, and the app MUST serve a restrictive `Content-Security-Policy`. State it as conditional on lifting NFR-UI-1. | The handoff's "Documented, not fixed" line flags "raw HTML in prose → self-XSS only … GATE ITEM: sanitize before any multi-user/default-on exposure" but FR-UI-2 ("raw markdown — no rendering at write time") gives no testable control. The built `render_markdown` (`pages_generator.py:137-146`) passes HTML through unescaped. | New FR-UI-7 in §2.A, cross-referenced from the "Documented, not fixed" line in the 2026-06-03 write-surface review. | Generate a page from a `.md` containing `<script>alert(1)</script>`; assert the emitted `app/templates/pages/_<name>.body.html` contains no raw `<script>` (escaped or stripped). |
| R1-F2 | Risks | medium | FR-UI-1 says "re-parse the full file before commit" but states no concurrency control. Add an explicit acceptance line: under NFR-UI-1 the race is accepted; at the multi-user gate, `append_page`/`write_prose` MUST use an optimistic version check (manifest hash captured at form render, write refused with a friendly error if it changed). | The built `append_page` (`pages_authoring.py:161-181`) is read-modify-write with no lock; two concurrent creates silently lose one. The doc names the race only in a build-time note (line 226), not as a requirement. | Extend FR-UI-1 / NFR-UI-1 with the accepted-vs-gated split. | At the gate: simulate two interleaved `POST /ui/pages` against the same manifest snapshot; assert exactly one succeeds and the other returns a "manifest changed, retry" error with no lost entry. |
| R1-F3 | Interfaces | medium | Promote the supported-manifest-shape contract into a normative requirement: the authoring append supports **block-style, consistently-indented `pages:`** only; any other shape MUST fail loud (friendly `PageError`) and MUST NOT corrupt the file. Today this lives only in the 2026-06-03 review note ("block-style/consistent-indent `pages:` only"). | A consumer hand-editing `pages.yaml` into flow style has no requirement telling them the UI will then refuse appends; the guarantee (`pages_authoring.py:172-179`, write gated on clean reparse) is real but undocumented as a contract. | New bullet under FR-UI-1 or NFR-UI-2. | Feed a flow-style `pages: [{slug: "/x", ...}]` manifest to `append_page`; assert it raises `PageError` and leaves the file byte-identical. |
| R1-F4 | Validation | high | Add an acceptance criterion that the **generated-owned validator stays equivalent to SDK `parse_pages`**, enforced by a shared contract test over a manifest corpus. The two MUST agree on accept/reject for: derived-name collisions, `nav:` validation, unknown keys, non-`/` slugs, empty `pages:`. | The emitted `_validate_all` (`pages_authoring.py:93-113`) omits the derived-name-collision check and `nav:` validation that SDK `parse_pages` enforces (`pages_generator.py:104-121`); the authoring artifacts are schema-only-hashed (`drift.py:101-103`), so divergence is invisible to `--check`. A UI can accept a manifest the next generate rejects. | New FR (e.g. FR-UI-8) under §2.A; reference the existing NFR-UI-3 "generated-owned validator." | Add `tests/unit/backend_codegen/test_pages_authoring.py::test_validator_matches_parse_pages` running a shared fixture corpus through both `_validate_all` (via exec of the emitted body) and `parse_pages`; assert identical verdicts. |
| R1-F5 | Security | medium | NFR-UI-2 covers slug→filename path safety but the disk-write endpoint requirement omits **size limits, symlink refusal, and an auth-hook seam**. Add these as gate-conditional requirements (accepted-absent under NFR-UI-1; required before exposure). | The built `_prose_path` (`pages_authoring.py:184-190`) checks `parent == _PAGES_DIR` but does not reject a symlinked `app/pages/` or bound body size; `write_prose` writes unbounded `form.get("body")`. At exposure these are real surfaces the requirements don't name. | Extend NFR-UI-2 with a gate-conditional sub-list. | At the gate: POST a 50 MB body → rejected with 413-style error; symlink `app/pages/` outside the tree → write refused. |

##### Endorsements & Disagreements

No prior untriaged suggestions exist in this document (R1 is the first round); none to endorse or dispute.
