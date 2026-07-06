# Kickoff Content Contract — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-07-06
**Status:** Draft
**Owner:** kickoff experience (`src/startd8/concierge/`, `src/startd8/kickoff_experience/`)

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass (read-only codebase investigation) revealed 7 corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The per-project templates could be piped to the terminal to satisfy the intro (FR-1). | The templates are `<Project>`-scoped, carry `<…>` placeholders and a "TEMPLATE — instantiate per project" banner (`KICKOFF_INTRO_TEMPLATE.md:1-3`). Rendering them raw would print placeholders. | **FR-1 now requires a NEW generic packaged doc** (`KICKOFF_EXPERIENCE_INTRO.md`), not derivation from the per-project template. |
| Bare `startd8 kickoff` prints help (harmless to augment). | It **exits 2** with Click's "Missing command." error — no help (empirically verified). A `callback(invoke_without_command=True)` can flip it to exit-0-with-intro+help, but this is a **new pattern** with no precedent in the repo and a **compat change** (2→0). | **FR-2 gains a compat note**; the callback pattern is specified. |
| What/Why/Who (clause E) could be surfaced inline per domain. | It exists **only as prose** in `KICKOFF_INPUTS_EXPLAINED_TEMPLATE.md`; `KICKOFF_INPUT_DOMAINS` (`core.py:60`) is a bare 4-slug tuple with no metadata. Structured inline metadata means extracting prose into a second copy → drift. | **FR-5 narrowed** to "render/reference the existing explained content"; **structured per-domain registry DEFERRED** (new NR-6 + OQ-7). |
| Posture could be an actionable prompt in the guided flow (OQ-5). | Guided flow **writes nothing** (FR-GE-1) and posture is **never persisted** (always supplied fresh to `instantiate --posture`, `writes.py:71-106` reads app.yaml mode, not posture). An actionable prompt = a write. | **FR-4 narrowed** to read-only *information* pointing at `instantiate --posture`. |
| Intro could show "first-run only." | No state persistence exists in the guided path; "first-run only" needs a write (violates FR-GE-1). | **New FR-10**: repetition controlled by a read-only heuristic (kickoff inputs already present ⇒ brief) + a `--brief`/`--no-intro` flag. |
| Runtime and file-written content need a new sharing mechanism (FR-6). | `render_template_content` / `get_template_entry` (`writes.py:255-267`) **already** render template bytes at runtime and are proven in `web.py`. | **FR-6 satisfied by reuse**; the generic intro is legitimately new content (not a duplicate), so no drift with the per-project file. |
| Guided intro is a simple `console.print`. | The CLI render is a **pure function of `build_guided_view`** (parity oracle, tested by `test_guided_experience_m4.py` via `guided_parity_digest` + `--json == build_guided_view`). Ad-hoc prints break parity. | **New FR-9**: intro/posture must flow through the view-model + digest + `render_guided_lines`. Prior art: `POSTURE_BANNER` (`concierge_view.py:294-298`) in the sibling concierge view-model. |

**Resolved open questions:**
- **OQ-1 → New packaged generic doc.** `KICKOFF_EXPERIENCE_INTRO.md` under `concierge_templates/`, surfaced via the existing `render_template_content` loader. Not derived from the per-project template (placeholder/banner problem).
- **OQ-2 → Exits 2 today; callback flips to 0.** `invoke_without_command=True` + `ctx.invoked_subcommand is None` guard prints intro then `ctx.get_help()`. `--json` is per-subcommand, so the bare-group intro never sees it.
- **OQ-3 → Prose only; structured registry deferred.** Reuse the rendered explained content for now (FR-5); a structured `KICKOFF_INPUT_DOMAINS` metadata registry is a follow-up (OQ-7/NR-6).
- **OQ-4 → Read-only heuristic + flag** (see FR-10), never a write.
- **OQ-5 → Information only.** Posture surfaced read-only; the actionable choice stays on `instantiate --posture` (FR-4).
- **OQ-6 → Yes, strong test infra.** `test_guided_offer_cli.py`, `test_guided_experience_m1/m4/m5.py` (byte-identity on `assess`, source-inspection no-writer guard, view-model parity). Additions must extend these (FR-7, FR-9).

---

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK lessons (esp. the repo's most-flagged: **phantom-reference audit**) before CRP.

- **[Phantom-reference audit]** — verified every symbol the plan names actually exists:
  `render_template_content`/`get_template_entry`/`kickoff_template_manifest`/`_template_key`
  (`writes.py:217-267`), `_KICKOFF_FILES` (`writes.py:32`), `build_guided_view`/`guided_parity_digest`/
  `render_guided_lines`/`POSTURE_BANNER` (`concierge_view.py:624/665/720/294`), `KICKOFF_INPUT_DOMAINS`
  (`core.py:60`). **Zero phantoms.**
- **[Phantom-reference audit — architecture conflict found]** — the audit revealed that
  `render_template_content`/`get_template_entry` resolve **only** keys in the manifest, and the
  manifest (`kickoff_template_manifest`, `writes.py:230-252`) is derived **solely** from
  `_TEMPLATE_GROUPS = _KICKOFF_FILES + _AUTHORING_FILES` (`writes.py:191-195`) — the *same inventory
  `instantiate` writes*, by deliberate anti-drift design ("derived here, never re-listed"). **There is
  no render-only tier.** So FR-1's "surface via `get_template_entry`" was wrong: it would force the
  generic intro either into the per-project write list (writes a generic doc into every project) or
  into a new manifest tier (breaks the manifest==write-inventory invariant). → **Fix: add a small
  public render-only loader** (`load_experience_doc(rel)` in `writes.py`, backed by the existing
  `_load_template`) that reads packaged bytes WITHOUT joining the write/download inventory. FR-1/FR-6
  and Plan Step 1 / R3 updated accordingly.
- **[Single-source vocabulary ownership]** — FR-6 already names the loader as the one source; with the
  fix above, the render-only loader and `_load_template` share the same `importlib.resources` read, so
  runtime bytes and (future) written bytes cannot diverge.
- **[CRP steering memory]** — least-reviewed artifact = this requirements doc + its plan (both new,
  v0.3/v1.1, never externally reviewed). Settled / do-not-relitigate: the $0/no-LLM + FR-GE-1
  byte-identical residue invariants (already ratified for the guided experience); the
  manifest==write-inventory anti-drift property (do not propose a render-only manifest tier — use the
  loader instead).

---

## 1. Problem Statement

The kickoff **input process** prescribes a *content contract* for every project it touches. Two
authored templates — `src/startd8/concierge_templates/KICKOFF_INTRO_TEMPLATE.md` and
`KICKOFF_INPUTS_EXPLAINED_TEMPLATE.md` — say, in effect: "a good kickoff must give the reader an
intro to the process, surface the posture decision first, inventory what will be produced, explain
how to use it, and explain each input in What/Why/Who terms, with never-blank defaults and honest
provenance."

The kickoff **experience** — the thing a user actually *runs* — fails that same contract. It
prescribes an intro for projects but ships none for itself; it prescribes What/Why/Who instructional
content but its runtime surfaces only mechanics. This is a self-application (dogfooding) gap: the
process does not eat its own cooking.

**The content contract, extracted from the templates:**

| Clause | Prescribed content | Template source |
|--------|--------------------|-----------------|
| A | Plain-language **process intro** ("what kickoff is"; machines-draft/humans-decide) | INTRO §1 |
| B | **Posture decision surfaced first** (production vs prototype/dogfood) | INTRO §2 |
| C | **"What's in the package" inventory** (what you'll produce) | INTRO §3 |
| D | **"How to use it" numbered walkthrough** | INTRO §4 |
| E | **Per-input What / Why / Who** instructional content | INPUTS_EXPLAINED §1–4 |
| F | **Never-blank defaults + honest provenance** | both |
| G | **Boundary note** — inputs NOT asked here (file-shaped) | INPUTS_EXPLAINED §5 |
| H | **Pre-non-demo warning** — replace fictional contacts | INTRO §4 |

**Gap table — contract clause × experience surface:**

| Surface | Code ref | A | B | C | D | E | Notes |
|---------|----------|---|---|---|---|---|-------|
| bare `startd8 kickoff` | `cli_concierge.py:37-40` | ✗ | ✗ | ✗ | ✗ | ✗ | no callback → Typer subcommand list only |
| `kickoff guided` | `cli_concierge.py:468-489` | ✗ | ✗ | ~ | ~ | ✗ | jumps to readiness + ranked commands |
| `KickoffPlan.render()` | `orchestrator.py:128-155` | ✗ | ✗ | ✗ | ~ | ✗ | pure mechanics ("you are here…") |
| `kickoff assess` | `concierge/core.py:224` | ✗ | ✗ | ✗ | ✗ | ~ | reports presence/provenance, not meaning |
| `kickoff instantiate --apply` | `writes.py:32-42` | ✓ | ✓ | ✓ | ✓ | ✓ | **only** place the content lands — as files |

**Key finding:** clauses A–H are *already authored* in `concierge_templates/*.md`. They are simply
**trapped as per-project file-output** on `instantiate --apply` and never surfaced at runtime. Making
the experience honor its own contract is therefore mostly a *surfacing/wiring* job, not new authoring.
Two gaps are genuinely un-authored: (1) a **generic, experience-level intro** — the templates are
per-project `<Project>`-scoped, so there is no product-level "what `startd8 kickoff` is and the
recommended order" text; (2) a **first-run posture prompt** in the guided flow.

## 2. Requirements

**FR-1 — Experience-level intro exists (clause A).** There must be a generic, NOT per-project
plain-language intro to the kickoff experience: what kickoff is, the machines-draft/humans-decide
framing, and the recommended command order (survey → assess → instantiate → cascade). Delivered as a
new packaged doc `concierge_templates/KICKOFF_EXPERIENCE_INTRO.md`, surfaced at runtime via a new
**render-only** loader `load_experience_doc(rel)` (backed by the existing `_load_template`
`importlib.resources` read) — NOT via `get_template_entry`/the manifest (those are bound to the
instantiate write+download inventory; see §0.1). It is distinct from — and does not duplicate — the
per-project `KICKOFF_INTRO.md` written on instantiate, and is NOT itself written to any project.

**FR-2 — Bare `startd8 kickoff` orients, not just lists (clause A/D).** Running `startd8 kickoff`
with no subcommand must present a compact form of the FR-1 intro plus a "start here" ordering, then
the subcommand list. Implemented as `@kickoff_kernel_app.callback(invoke_without_command=True)`
gated on `ctx.invoked_subcommand is None`, printing intro + `ctx.get_help()`. *Compat note:* this
flips the bare-group exit code from **2 (Missing command) → 0 (intro+help)** — an intentional,
friendlier behavior; documented in the plan's risk list.

**FR-3 — Guided flow opens with an intro (clause A).** `kickoff guided` must lead with a compact
FR-1 intro before Orient/Guide/Deepen, so a first-run user is oriented before readiness and gates.
Subject to FR-9 (via the view-model) and FR-10 (repetition control).

**FR-4 — Guided flow surfaces the posture decision as INFORMATION (clause B).** The guided
experience must surface, read-only, the prototype-vs-production posture choice and its consequence
(deployment-mode default, provenance strictness), and point the user at the actionable
`startd8 kickoff instantiate --posture <…>`. It MUST NOT prompt-and-record posture in the guided
flow (that would be a write, violating FR-GE-1); the actionable choice stays on `instantiate`.

**FR-5 — What/Why/Who reachable inline (clause E).** When the experience references the four input
domains, it must make the What/Why/Who explanation reachable *without leaving the terminal* — by
rendering (or offering to render, e.g. a `kickoff explain` verb or an inline section) the content of
`KICKOFF_INPUTS_EXPLAINED` via the same `render_template_content` loader. It need NOT restructure the
prose into per-domain inline metadata in this pass (see NR-6 / OQ-7).

**FR-6 — Single source of truth for surfaced content.** All instructional text surfaced at runtime
must derive from packaged `concierge_templates/*.md` via a shared `importlib.resources` loader —
`render_template_content` for manifest-bound (written) templates, `load_experience_doc` for the
render-only generic intro — never a hand-copied second string. The FR-1 generic intro is its own
single source (new content, not a copy of the per-project template).

**FR-7 — Suppression discipline preserved.** All human-facing additions must follow the established
seam: emit orientation courtesy on **stderr** via `_stderr_console`, gate on `console.is_terminal`
(suppress on non-TTY/piped), return before any human print when `--json` is set, and wrap in
defensive `try/except` — mirroring `_maybe_offer_guided` (`cli_concierge.py:194-214`) and
`guided_routing.py:200-228`. $0 / no-LLM by default (FR-GE-5) is preserved.

**FR-8 — Boundary + pre-demo warning reachable (clauses G, H).** The experience must make the
"inputs we do NOT ask here" boundary and the "replace fictional contacts before non-demo use"
warning reachable at runtime (rendered or explicitly referenced via FR-5's surface), not only
present in the instantiated files.

**FR-9 — Guided intro/posture flow through the view-model (parity).** Any intro/posture content in
`kickoff guided` must be added as sibling key(s) in `build_guided_view` (`concierge_view.py:654-662`)
with matching entries in `guided_parity_digest` and `render_guided_lines`, so CLI/TUI/served parity
(`test_guided_experience_m4.py`) and `--json == build_guided_view` both stay green. Ad-hoc
`console.print` in the guided body is prohibited.

**FR-10 — Intro repetition is read-only and controllable.** The guided/bare intro must not require a
write to decide whether to show. Default: show the compact intro; when the project already has
`docs/kickoff/inputs/` (read-only heuristic ⇒ user is past onboarding) show a one-line pointer
instead of the full intro. A `--brief` / `--no-intro` flag forces the short form regardless.

## 3. Non-Requirements

- **NR-1** — Not rewriting the kernel engines (`build_survey`/`build_assess`) or the $0 cascade.
- **NR-2** — Not making the guided flow interactive/stateful beyond what's needed to surface the
  posture choice; a full wizard is out of scope for this pass.
- **NR-3** — Not adding any LLM call to the default path; `--agent` remains the sole opt-in paid path.
- **NR-4** — Not changing the per-project template *content* (only lifting/sharing it); template
  authoring quality is a separate concern.
- **NR-5** — Not touching the served Welcome Mat / web surface in this pass (CLI + guided first).
- **NR-6** — Not building a structured per-domain `KICKOFF_INPUT_DOMAINS` metadata registry
  (label/what/why/who as data). FR-5 reuses the existing prose; the registry is deferred (OQ-7).

## 4. Open Questions

- **OQ-7 (deferred, not blocking)** — Should `KICKOFF_INPUT_DOMAINS` (`core.py:60`) eventually become
  a structured registry so the per-project `KICKOFF_INPUTS_EXPLAINED.md` is *generated from* it
  (registry = single source), enabling true inline per-domain What/Why/Who? Deferred out of this pass.
- **OQ-8** — FR-5 delivery: a dedicated `kickoff explain [domain]` verb, or an inline section in
  `guided`/bare intro, or both? (Plan proposes a verb + a one-line pointer from the intro.)
- **OQ-9 → RESOLVED (top group only).** FR-2's bare-group callback applies to the top `kickoff`
  group only this pass; `kickoff panel` keeps its current bare-exit-2 behavior.

### Resolved during planning (were OQ-1..OQ-6)
See §0 — OQ-1→new packaged doc; OQ-2→exits 2, callback flips to 0; OQ-3→prose only, registry
deferred; OQ-4→read-only heuristic + flag; OQ-5→information only; OQ-6→strong test infra exists.

## 5. Follow-ups (implemented 2026-07-06, branch `feat/kickoff-content-contract-followups`)

**NR-5 → DONE (served surface).** `_render_guided` (`web.py`) now renders the `intro` and `posture`
view-model blocks (intro before Orient; posture inside Orient after unmet gates), HTML-escaped,
mirroring the CLI/TUI. The digest already carried `intro_mode`/`posture_hint`, so CLI/TUI/served
parity is now assertable and asserted.

**OQ-7 / NR-6 → DONE (per-domain registry, drift-free).** Added `KICKOFF_INPUT_REGISTRY`
(`core.py`) — a `{slug: KickoffInputDomain(label, question, file, who, ordinal)}` map of **structured
routing metadata only**. `KICKOFF_INPUT_DOMAINS` is unchanged (its exact-tuple + `is`-identity
consumers/tests demand it); the registry is keyed by exactly those slugs (test-guarded). The
long-form What/Why/Who **prose stays single-sourced** in `KICKOFF_INPUTS_EXPLAINED` and is sliced on
demand by `explain_input_domain(slug)` (`_slice_explained_section` cuts the `## N.` block) — so the
registry and the prose cannot drift (a test asserts each registry `(ordinal,label)` matches the
explainer heading). Surfaced as `startd8 kickoff explain <domain>` (+ `--json`). This resolves OQ-8
(delivery = a per-domain argument on the existing `explain` verb).

- **OQ-1** — Should the FR-1 generic intro live as a new packaged doc
  (`concierge_templates/KICKOFF_EXPERIENCE_INTRO.md`), as Python string constants, or be *derived*
  from the per-project template with the `<Project>` slots generalized? (bears on FR-6)
- **OQ-2** — Does bare `startd8 kickoff` (no subcommand) currently exit 0 with help, or error? Can a
  Typer group callback print intro text *and* still show the subcommand list without breaking
  `--json`/scripts? (bears on FR-2, FR-7)
- **OQ-3** — For FR-5, is inline What/Why/Who feasible from existing structured data, or is the
  content only available as prose in `KICKOFF_INPUTS_EXPLAINED_TEMPLATE.md` (requiring extraction/
  restructuring)? Is there already a machine-readable domain registry (`KICKOFF_INPUT_DOMAINS`) to
  attach the text to?
- **OQ-4** — Should the intro print on *every* `kickoff guided` run or once (first-run only, with a
  `--brief`/`--no-intro` opt-out)? Repetition fatigue vs orientation.
- **OQ-5** — Posture (FR-4): surface as *information* (explain the choice + current default) or as an
  *actionable prompt* (let the user pick and record it)? The latter implies a write, colliding with
  FR-GE-1 byte-identical residue.
- **OQ-6** — Is there test infrastructure asserting guided-flow output byte-identity that these
  additions must extend rather than break?

---

**Version note:** v0.2 → **v0.3** after lessons-learned hardening (§0.1): phantom-reference audit
found the manifest==write-inventory conflict; FR-1/FR-6 now use a render-only `load_experience_doc`
loader instead of the manifest-bound `get_template_entry`.

*v0.3 — Post lessons-learned hardening. Applied: phantom-reference audit (0 phantoms, 1 architecture
conflict fixed), single-source vocabulary ownership, CRP steering memory. Prior: v0.2 narrowed FR-4/
FR-5, added FR-9/FR-10, deferred NR-6/OQ-7, resolved 6 OQs. Ready for CRP. See companion
`KICKOFF_CONTENT_CONTRACT_PLAN.md` (v1.1).*
