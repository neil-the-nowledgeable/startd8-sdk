# Kickoff-Panel Observability UX — Requirements

**Version:** 0.3 (v1 + live-follow implemented)
**Date:** 2026-07-04 (v0.1) · 2026-07-05 (v0.2 static build, v0.3 `--watch`)
**Status:** **IMPLEMENTED through live-follow** — static offline HTML + CLI + `--watch`
(`startd8 kickoff-panel view/list/show [--watch]`) in `src/startd8/kickoff_view/` (branch
`feat/kickoff-panel-viewer`). **FR-UX-17/18 now shipped** (no-server poll-and-diff live-follow;
`show --watch` re-renders the terminal, `view --watch` re-writes an auto-refreshing HTML file).
Still deferred: the optional **served mode** (§3) — pre-specified, adds a network trust surface
for zero new capability, so intentionally not built.
**Tracks:** `KICKOFF_PANEL_FACILITATION_DESIGN.md` §6 (transcript contract) / §8 (non-goals).
**Precedent:** the `startd8-consult` `consultation/{store,serve,view,_webview_template,facade}`
package (the user's "show all models + their feedback" reference).

---

## v0.2 — build-time resolutions (grounded in the merged transcript contract)

- **OQ-UX-1 (synthesis structure) → RESOLVED: render prose now.** The on-disk `synthesis` is
  `{model, text}` with **Markdown-embedded** risk register / tensions / recommendations / open
  questions — the structured arrays do **not** exist as JSON (verified against
  `facilitation.py:748` and all three fixtures). So FR-UX-16 (prose fallback) is the **primary**
  render path; FR-UX-15's structured views stay latent and light up if the orchestrator later
  emits structure. The one machine-structured signal that *does* exist —
  `synthesis.open_tension_ids` (anti-smoothing) — is surfaced as a distinct "unresolved tensions"
  band (FR-UX-15's anti-smoothing intent, satisfied from real data).
- **OQ-UX-5 (family map) → RESOLVED: derive from the `provider:` prefix** (`model_family()` in
  `models.py`) — Claude / GPT / Gemini + Mistral/Ollama/DeepSeek, unknown → "Other".
- **OQ-UX-3 (prompt visibility) → show, collapsed-by-default** in a secondary per-entry
  disclosure (FR-UX-7) — transparency of *how* the facilitation drove each answer, without
  crowding the reading surface.
- **OQ-UX-4 (TUI) / OQ-UX-2 (live-follow) / OQ-UX-6 (laddering sub-entries) → deferred** with the
  served mode; the read model + payload already tolerate multiple entries per role per round
  (role-major groups by `role_id`), so laddering needs only a UI sub-grouping later.
- **Schema-drift hardening (FR-UX-3, reinforced):** older transcripts lack
  `prep`/`adversaries`/`status`/`halt`/`budget_usd` and the synthesis `*_tension_ids`. Every
  field is optional with `extra="allow"`; absence renders as an explicit empty/"(pending)" state.
  Covered by the `thin_schema.json` fixture.

**Shipped surfaces:** `kickoff_view/{models,store,view,_webview_template,facade,watcher}.py` +
`cli_kickoff_panel.py` (mounted in `cli.py`). 39 unit tests; browser-verified (two-axis toggle,
per-entry disclosure, adversary/grounding/family badges, halted-state banner, XSS breakout
neutralized to the 2 real `<script>` containers, LIVE banner + meta-refresh + filling marker).

**Live-follow design (v0.3, FR-UX-17/18/19):** `watcher.py` `TranscriptWatcher` separates
change-detection (`poll` — mtime+size signature, tolerates a transient mid-write decode blip →
returns "no change") from the loop (`follow` — renders on each change, self-terminates when the
run hits a terminal `status`; `sleep`/`max_ticks` injectable for tests). No server: the browser
auto-updates via a `<meta http-equiv="refresh">` injected **only** in watch mode (the static
default stays byte-identical); on completion the final write omits the refresh so the page
settles. FR-UX-18 progress is **honest about the whole-round persistence**: a landed round shows
`n/roster`, and the *pending* next round is named in the LIVE banner (not shown as a false
partial bar); the in-round `filling` badge lights only if a round is actually persisted short of
its roster.

---

## 1. Problem & scope

The orchestrator persists a rich, structured transcript to
`.startd8/kickoff-panel/<session_id>.json` — rounds × entries with per-entry model
attribution, R0 prep cards, adversary flags, and a synthesis block. Today the only
way to consume it is raw JSON or a flat Markdown dump, which loses the two axes the
process is *organized around* (round and role) and can't be followed as it runs.

The user wants to **follow the facilitated process — round by round, role by
role — for validation-by-observation and inspiration.** Purely observe and
navigate; **no formal validation, scoring, acceptance, or idea-promotion** at this
stage.

**In scope:** render the transcript into a navigable viewer with expand/collapse by
round *and* by role; per-entry model attribution + de-correlation visibility; the
R0 prep cards; the synthesis view; live-follow as rounds complete; unratified
labeling.

**Non-goals (explicit, mirrors design §8):**
- **No validation capability** — no scoring, acceptance gates, pass/fail, or quality grading.
- **No inspiration/promotion capability** — no idea-capture, action-tagging, or write-back of a recommendation into a requirement/task/artifact.
- **No editing / mutation** of the transcript; **no re-running** the panel from the viewer; **no ratification affordances** (the human ratifies elsewhere).

---

## 2. Functional requirements

### Loading & sessions
- **FR-UX-1** — Load a transcript by `session_id` from `.startd8/kickoff-panel/`; **list** available sessions newest-first (mirrors `ConsultationStore.list_sessions`).
- **FR-UX-2** — The transcript JSON is the **read-only source of truth** (Mottainai); the viewer never writes it. Re-rendering is **$0** (no model calls).
- **FR-UX-3** — **Graceful degradation on partial/in-progress transcripts** — missing later rounds, an in-flight round with fewer entries than the roster, empty `synthesis`, `cost_usd == 0.0`. No field is assumed present; absence renders as an explicit "(pending)"/"(not recorded)" state, never a crash. *(Grounded in real data: current runs have prose-only synthesis and zero costs.)*

### Two-axis navigation (the core ask)
- **FR-UX-4** — **Round-major view (default):** entries grouped under `rounds[]`; each round a collapsible section showing `round_id`, `title`, `kind`, entry count.
- **FR-UX-5** — **Role-major re-pivot:** a toggle re-groups the *same records* by `role_id`/`display_name`, so a role's R1→R2→R3→R4 trajectory reads as one collapsible thread. A pure client-side view transform over the identical entry set (§6 makes this a view transform, not a data change).
- **FR-UX-6** — **Independent expand/collapse** of each round (round-major) and each role (role-major), plus global expand-all/collapse-all. Collapsed state shows a one-line summary (role + model + grounding badge; or round title + count).
- **FR-UX-7** — **Within-entry disclosure:** each entry shows `display_name`, `model`, `grounding`, `flags`, and the answer `text`; the exact `prompt` sent and token/cost usage are in a secondary, collapsed-by-default disclosure so the reading surface stays the answer.

### Model attribution & de-correlation visibility
- **FR-UX-8** — Every entry shows its **model** (`entry.model`) and a derived **family badge** (Claude / GPT / Gemini, from the `provider:` prefix) so the de-correlation spread is visible at a glance.
- **FR-UX-9** — Surface the **`model_assignment`** map + `facilitator_model` so the reader sees the whole roster's family distribution (the de-correlation lever, design §4).
- **FR-UX-10** — **Adversary marking:** roles in `adversaries[]` are visually distinguished (attack-framed badge) in both axes.
- **FR-UX-11** — **Cross-family corroboration highlight (synthesis):** where the risk register carries `corroboration` (`single-model | single-family | cross-family`), rank/badge it with **cross-family** most prominent (design §5: only cross-family is "trustworthy"); render the contributing families from `flagged_by`. Must no-op cleanly when the register is empty.

### Prep cards (R0)
- **FR-UX-12** — Render the **`prep`** block as three top-level cards above the rounds — `grounded_context`, `key_assumptions`, `outside_view` — Markdown-rendered (the framing/pre-read).
- **FR-UX-13** — Render the session header: `project`, `objective`, `strategy`, `created_at`, `cost_total_usd` (as "not recorded" when `0.0`).
- **FR-UX-14** — **Halted-session state (v0.2.1 gate):** if the assumptions check halts the panel after R0 (≥2 high-impact/low-confidence assumptions — spec H2), render the prep cards + a prominent "panel halted: validate the premise first" banner and no rounds. This is a first-class state, not an error.

### Synthesis view
- **FR-UX-15** — Render **synthesis** as a dedicated section: `risk_register[]` (risk + `flagged_by` + `corroboration`), `tensions[]` (between / issue / status — with **unresolved tensions visually preserved and distinct**, honoring anti-smoothing §5), `recommendations[]`, `open_questions[]` (framed "needs your judgment" — the load-bearing output).
- **FR-UX-16** — When the structured synthesis arrays are **empty** (current real state — synthesis is prose-only), fall back to rendering `synthesis.text`. The section never appears broken for want of structured fields.

### Live-follow
- **FR-UX-17** — **Live-follow:** render an in-progress transcript and reflect newly-appended rounds/entries as the orchestrator writes round-by-round (§6). Mechanism = poll-and-diff the file (see §3); re-read is $0.
- **FR-UX-18** — Show **per-round progress** ("R2: 12/16 roles complete") from entry count vs roster size, and mark the currently-filling round.
- **FR-UX-19** — Safe against torn reads: the orchestrator must write atomically (`tmp` + `os.replace`, the consult pattern) so a mid-round read sees fewer entries, never corruption. *(Orchestrator change — the viewer relies on it.)*

### Unratified labeling & rendering safety
- **FR-UX-20** — **Every persona output is labeled synthetic/unratified** — a persistent global banner + a per-entry marker — so no reader mistakes a panel answer for a decision (design §1/§5/§7).
- **FR-UX-21** — Per-entry **grounding badge** (`grounded | uncertain | deferred | unavailable`) and any `flags` (grounding-guard downgrades) are surfaced.
- **FR-UX-22** — All transcript text is **untrusted** — escape-then-Markdown-render (reuse consult's escape-first whitelist + `_embed_json` `<`-neutralization); a `</script>` in any answer cannot break out.
- **FR-UX-23** — Cost/token figures render only when present and non-null; `0.0`/absent → "not recorded" (do not imply real spend data exists while H3 is open).

---

## 3. Architecture (grounded in the consult precedent)

**Reuse the consult three-surface pattern** — it was purpose-built as this
feature's precedent:

| Consult | Kickoff-panel analog |
|---|---|
| `models.py` (`ConsultationSession`) | a `KickoffTranscript` model over the §6 schema (graceful optionals for empty synthesis / zero cost) |
| `store.py` (`ConsultationStore`) | `KickoffPanelStore` — reuse `list_sessions`, atomic `save`, `load`; **read-only for the viewer** |
| `view.py` (`render_html`, `_embed_json`) | `render_html` over the transcript (escape-first embed; new two-axis template) |
| `_webview_template.py` | a standalone, dependency-free, offline HTML template with round/role toggle + collapsibles |
| `facade.py` (`ConsultationService`) | `KickoffViewService` — sync bridge for CLI/TUI: `load`, `list_sessions`, `render_html`, `render_text` |

**Default (and only v1) surface — static offline HTML ($0, read-only):**
- Primary = a **standalone HTML file rendered from the transcript**, opened via
  `file://`, self-contained/offline (consult's `render_html(session, serve=None)`).
- **CLI (mirror `startd8 consult`):** `startd8 kickoff-panel view <session_id>`
  (render+open the HTML), `... list`, `... show <session_id>` (rich/text to stdout).
  Round-major default; `--by-role` re-pivot flag.
- **Live-follow:** a `--watch`/`--follow` mode that re-renders on file change
  (poll-and-diff mtime/size; $0). Because the orchestrator writes round-by-round to
  a single atomically-replaced document, poll-and-diff needs **no server**.

**Optional served mode — deferred.** The observe-only feature needs no server
(unlike consult's serve mode, which existed to *execute paid follow-ups* — we have
no mutating capability). A served mode's only justification would be polished
in-browser auto-refresh. **If** later built, mirror the consult trust model exactly
(`serve.py`) *minus the spend machinery*: loopback-only bound-socket assertion,
per-run token (constant-time compare, out of logs), Host allowlist, reject
`Upgrade`/WebSocket, strict CSP w/ per-response nonce, and **read-only endpoints
only** (`GET /`, `GET /session`) — no POST/reply/engine/cost-caps (nothing to
spend). Keep the `serve is None ⇒ byte-identical static file` guarantee.
`starlette`/`uvicorn` stay a soft `startd8[server]` extra; absence degrades to the
static file.

**Recommendation:** ship **static HTML + `--watch` live-follow** as v1; defer the
served mode (it adds a network trust surface for zero new capability). The served
trust model is pre-specified so it can be added later without redesign.

---

## 4. Open questions

- **OQ-UX-1 — synthesis structure:** the real transcript's `synthesis` is
  prose-only; the structured arrays are empty. Render prose now and light up the
  structured views when the orchestrator populates them (assumed by FR-UX-15/16),
  or push the orchestrator to emit structured synthesis first?
- **OQ-UX-2 — live-follow mechanism:** is `--watch` poll-and-diff sufficient, or is
  true in-browser push wanted (which forces the served mode)? Acceptable latency?
- **OQ-UX-3 — prompt visibility:** entries carry the exact `prompt` (with injected
  cross-role digests). Collapsed-by-default (FR-UX-7) — but show at all? Argument
  for: transparency of *how* the facilitation drove each answer is core to
  validation-by-observation.
- **OQ-UX-4 — TUI surface:** consult has web + a TUI mixin. Is a TUI kickoff viewer
  in v1, or web + CLI-text only (TUI deferred)?
- **OQ-UX-5 — family map source:** derive the family badge from the `provider:`
  prefix (simplest, matches the three flagship families) or reuse
  `model_catalog.py`? Any fourth family to handle?
- **OQ-UX-6 — laddering sub-entries:** if laddering (spec §3 R1) later yields
  multiple entries per role per round, the role-major thread needs intra-round
  sub-grouping. Design for it now or defer (not present in current 4-round runs)?

---

*Draft 0.1 — finalized from research against the §6 transcript contract + the
consult precedent. Fixtures available to build against:
`benchmarking/.../kickoff-panel/kp-20260704T160024-*.json` (#8, valid-lift),
the retail `#6` (clean) and `#7` (false-premise) transcripts.*
