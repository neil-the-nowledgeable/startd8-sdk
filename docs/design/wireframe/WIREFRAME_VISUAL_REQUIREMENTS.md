# Wireframe Visual Preview — Requirements (the end-user's lo-fi "what's about to be built")

**Version:** 0.3.1 (Draft — post-planning + lessons + principle hardening; pre-CRP)
**Date:** 2026-07-18
**Status:** Draft
**Concept key:** `FR-WV` (Wireframe-Visual). Stable prefix — the presentation name ("lo-fi preview",
"app preview") may change; the key does not ([[concept-key-not-presentation-name]]).
**Persona:** the **end user / non-technical stakeholder** approving the shape of their app — *not*
the architect at the terminal (that audience is served by `--describe`, `WIREFRAME_REQUIREMENTS.md`).

**Consolidates / reuses (cite, do not restate — Mottainai):**
- Plan data contract → `WIREFRAME_REQUIREMENTS.md` FR-W10 (`--json`, `schema_version`, `inputs_fingerprint`).
- Section narration → `wireframe/descriptive.yaml` + `describe.py` (FR-DL-1/12) — the HTML consumes the
  SAME authored what/why/next; it does not re-author them.
- Summary altitude → `SUMMARY_VIEW_REQUIREMENTS.md` (FR-SV-*) + `render.footer_lines()`.
- HTML delivery pattern → `src/startd8/kickoff_view/_webview_template.py` + `view.render_html`
  (self-contained page, embedded escape-first JSON, `$0` re-render, read-only).
- Node grammar → `dev-os/NODE-SCHEMA.md` (summary→drill, metadata badges, modality-independence).

---

## 0. Planning Insights (Self-Reflective Update)

> Grounded against the **live plan JSON** (`startd8 wireframe --json` on strtd8) and the existing
> `kickoff_view` HTML module — not against assumptions. v0.1→v0.2 corrections:

| v0.1 Assumption | Grounding Discovery | Impact |
|---|---|---|
| The visualizer must compute a summary | `shape` / `status_counts` / `content_completeness` / `readiness` are already top-level JSON keys (what `footer_lines()` renders) | FR-WV-2 is a **re-render of existing data**, not new compute. No plan changes. |
| Form mockups need a new structured field list | Form items already carry fields in `detail` prose: `"fields: a, b … | omitted — server-managed: …"` | FR-WV-9: **parse the existing `detail`** (Mottainai); degrade to the label if unparseable. Do NOT expand the plan schema first. |
| HTML rendering is greenfield | `kickoff_view/_webview_template.py` is a working self-contained escaped-JSON viewer with the exact `$0`/read-only ethos | FR-WV-1/7 **reuse that pattern**; the risk is a new subsystem, not the HTML itself. |
| Section explanations must be written for the HTML | `descriptive.yaml` already authors what/why/next per section | FR-WV-5 **embeds the same records** — one source of narration across terminal + HTML (FR-DL-5). |
| This is a deferred wireframe OQ | `WIREFRAME_REQUIREMENTS.md:248` makes visual an **explicit v1 non-requirement**; OQ-8 is `--diff`, unrelated | This doc **lifts** that non-req into a scoped v2 capability; the JSON contract (schema_version, fingerprint) was already hardened for exactly such a consumer. |

**Resolved open questions:**
- **OQ-A → Parse-first.** Derive form fields from `detail` prose; only add structured `fields[]` to the
  plan if parsing proves fragile in practice (deferred, not pre-built).
- **OQ-B → Sibling module.** A new `wireframe_view/` mirroring `kickoff_view/`'s shape, reusing its
  escape/embed helpers — not overloading `kickoff_view` (single-responsibility).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK / design-doc lessons before CRP:

- **[Phantom-reference audit]** — every symbol this spec names (`footer_lines`, `plan_body`,
  `descriptive.yaml` keys, `kickoff_view.view.render_html`, JSON keys `shape`/`sections`) was grep-verified
  to exist (see §Reference-Audit). Form-field parsing binds to the real `detail` string format, confirmed live.
- **[Single-source vocabulary ownership]** — narration is **owned** by `descriptive.yaml` and cited, not
  restated in an HTML template (FR-WV-5); the summary math is owned by `footer_lines()` and reused (FR-WV-2).
- **[Prune phantom scope]** — "interactive app / live data / submitting forms" moved to Non-Requirements:
  the mockup is a static skeleton, not a running app (NR-2).
- **[CRP steering memory]** — least-reviewed artifact = this doc + its plan (new). Settled/do-not-relitigate:
  self-contained HTML medium; outline-drills-into-mockup fidelity; deterministic no-LLM; reuse (not re-spec)
  the plan JSON, descriptive layer, and kickoff_view pattern.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked against the design principles:

- **[Mottainai]** — the HTML **forwards** already-produced artifacts (plan JSON, `footer_lines` summary,
  `descriptive.yaml` narration, `kickoff_view` scaffold); it regenerates none of them (FR-WV-2/5/7).
- **[Genchi Genbutsu]** — every FR binds to a *verified* JSON key / file, grounded on the live strtd8 plan,
  not a docstring. Mockup fidelity is bounded to what the data actually carries (FR-WV-9) — no fabricated fields.
- **[Hitsuzen]** — the HTML is a pure function of (plan JSON × descriptive.yaml); nothing is asked of an LLM.
- **[Accidental-Complexity]** — a **new `--html` renderer**, not a new data model, gate, or plan field. If
  it starts adding plan schema to make mockups prettier, it has failed — parse-first + honest-degrade (FR-WV-9).
- **[Context-Correctness-by-Construction]** — the embedded JSON is escaped-on-embed (`kickoff_view` pattern);
  an unparseable form `detail` degrades visibly, never silently renders a wrong field list.

---

## 1. Problem Statement

The wireframe plan is legible to an **architect** in the terminal (`--describe`, the inverted-pyramid
summary + per-section what/why/next). There is **no artifact to show a non-technical end user** what
their app will look like — the pages, forms, services, and content that are about to be built. `--json`
is machine-facing; the Rich tree is architect-facing and terminal-bound.

| Component | Current State | Gap |
|---|---|---|
| Summary altitude | `footer_lines()` → terminal text | Not browsable, not shareable, terminal-only |
| Section/item detail | Rich tree + `--describe` narration | No visual; no per-screen representation |
| End-user artifact | *(none)* | No shareable file a stakeholder can open and browse |
| Page/form shape | Prose in `detail` / templates the cascade will emit | Never shown as a lo-fi screen the user can picture |

## 2. Requirements

- **FR-WV-1 — Self-contained HTML output.** `startd8 wireframe --html <path>` writes ONE portable
  `.html` file: embedded CSS + JS, **no external assets, no CDN, no build step**. Opens directly in a
  browser. Mirrors `kickoff_view` delivery. Atomic write (temp+rename), advisory exit 0.
- **FR-WV-2 — Inverted pyramid (summary always on top).** The page opens with the summary band —
  counts (`shape`), health (`status_counts` + worst glyph), content-readiness (`content_completeness`),
  cascade (`readiness`) — rendered from the SAME data as `footer_lines()`. It stays visible/pinned as
  the user drills. (SV-1 / FR-SV-12.)
- **FR-WV-3 — Browsable outline.** Below the summary, the plan `sections[]` render as collapsible nodes
  (pages, forms, services/AI, entities, views, content, …), each item expandable. Structure maps 1:1 to
  the plan `sections`/`items` — no re-grouping (Mottainai).
- **FR-WV-4 — Drill-to-mockup.** Expanding a **page**, **form**, or **list** item reveals a lo-fi screen
  mockup: pages → a framed screen with the default nav bar; forms → a labeled field skeleton (shown vs
  omitted fields); lists/CRUD → a table skeleton. Boxes-and-fields fidelity only (NR-1).
- **FR-WV-5 — Metadata legibility (know what you're looking at).** Every node carries badges — status,
  count, content %, AI-boundary — AND a plain-language WHAT/WHY drawn from `descriptive.yaml` (FR-DL),
  so a first-time user understands each section without reading code. Narration is embedded from the
  authored records, not rewritten.
- **FR-WV-6 — Deterministic, `$0`, no-LLM.** The HTML is a pure function of (plan JSON × descriptive.yaml).
  Re-rendering the same plan yields byte-identical HTML (modulo the run timestamp). No model call. (Hitsuzen.)
- **FR-WV-7 — Versioned data source, embedded.** The visualizer consumes the emitted plan body
  (`schema_version` N) and embeds it **escape-first** in the page (the `kickoff_view` transcript pattern):
  the data is the source of truth; the file re-renders itself client-side. A `schema_version` mismatch
  degrades to a visible banner, never a silent wrong render.
- **FR-WV-8 — Honest rendering.** `not_defined` / `placeholder` / `invalid` nodes render honestly (greyed +
  badged), never faked or hidden; content gaps are visible. Matches the wireframe's advisory ethos —
  the preview must not over-promise what isn't defined.
- **FR-WV-9 — Fidelity bounded by data; degrade, never fabricate.** Mockups use only data the plan
  actually carries. Form fields are parsed from the item `detail` prose (`fields: … | omitted — …`);
  if a `detail` doesn't parse, the item degrades to its label + raw detail — it MUST NOT invent fields.

## 3. Non-Requirements

- **NR-1 — Not hi-fi.** No pixel design, no theming, no real styling of the target app. Lo-fi boxes only.
- **NR-2 — Not a running app.** No live data, no working forms/submission, no routing — a static preview.
- **NR-3 — Not a re-spec.** Does not redefine the plan, the descriptive layer, or the summary view — it
  **consumes** them (FR-W10, FR-DL, FR-SV).
- **NR-4 — No server / framework / CDN.** One file, opened from disk. No React/Vue/build/bundler.
- **NR-5 — Not the cascade.** Does not emit the target app's real `app/templates/*.html`; those are the
  generator's job. This renders a *preview of the plan*, not the app.
- **NR-6 — Not (yet) a diff view.** Planned-vs-built (`--diff`, OQ-8) is out of scope here.

## 4. Open Questions

- **OQ-WV-1 — Audience toggle?** One end-user-plain view, or a switch to an architect-detail view in the
  same file? (Lean: single plain view v1; the terminal already serves the architect.)
- **OQ-WV-2 — Structured fields escalation.** If `detail`-parsing (FR-WV-9) proves fragile across real
  projects, do we add a structured `fields[]` to the plan JSON (a FR-W10 change)? Deferred until evidence.
- **OQ-WV-3 — Open-on-generate?** Should `--html` auto-open the browser (like some tools) or only write
  the file? (Lean: write-only + print the path; auto-open is a flag later.)

## Reference-Audit (phantom-reference check — all verified live 2026-07-18)

| Symbol / key referenced | Owner | Exists? |
|---|---|---|
| `--json` body keys `shape`, `status_counts`, `content_completeness`, `readiness`, `sections` | `render.plan_body` | ✅ (live JSON) |
| section item fields `label`/`detail`/`paths`/`status` | `plan.py` builders | ✅ |
| form `detail` = `"fields: … | omitted — server-managed: …"` | `plan.py` forms builder | ✅ (verified on strtd8) |
| `footer_lines(plan)` (summary math) | `render.py:274` | ✅ |
| `descriptive.yaml` records + `describe.py` | wireframe module | ✅ |
| `kickoff_view.view.render_html` + `_webview_template.py` (escaped-embed HTML) | `src/startd8/kickoff_view/` | ✅ |
| `schema_version` / `inputs_fingerprint` on JSON | FR-W10 | ✅ |

---

*v0.3.1 — Post planning + lessons + principle hardening. Grounded on the live strtd8 plan JSON and the
kickoff_view module. 5 assumptions corrected, 2 OQs resolved, reuse (not rebuild) established for the
plan JSON / descriptive layer / summary math / HTML scaffold. Ready for CRP review.*
