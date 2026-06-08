# Presentation Polish Capability — Requirements

**Version:** 0.3 (Post-spike — OQ-8 resolved)
**Date:** 2026-06-08
**Status:** Draft
**Author:** Neil (with Claude)
**Working name:** `startd8 polish` (the post-build presentation-layer capability)

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass read the actual `backend_codegen`, `DeterministicFileProvider`, `CapDevPipeInstaller`,
> and skill-invocation code and resolved 5 open questions, de-risked the highest-risk requirement,
> surfaced 1 new required change, and split a conflated requirement. The spine (two-tier, vendored
> delivery, all-Python, full scope) held — under the 30% revision threshold, so the draft was not
> premature.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| OQ-1: regeneration coexistence is the highest risk; mechanism TBD | A shipped `DeterministicFileProvider` Protocol + registry + entry point (`startd8.contractors.deterministic_providers`) already exists (`contractors/deterministic_providers.py`); `PrismaZodFileProvider`/`PydanticSQLModelProvider` are precedents. A new `PresentationPolishFileProvider` cleanly owns polish files. | OQ-1 resolved. FR-21 now concrete + low-risk. Provider is the mechanism. |
| `generate backend --check` might flag/clobber polish files | `--check` only inspects files carrying the `# GENERATED from` marker (`cli_generate.py:262-290`); non-owned files are **completely ignored**. Polish files are safe by default. | FR-21 simplified. The provider's real value is polish's *own* idempotency + making the **prime contractor skip-hook** treat polish files as $0/owned (not LLM-regenerate them). |
| FR-21: "likely a new owned kind or skip-hook" (zero backend changes implied) | `main.py` (owned kind `fastapi-main`, `crud_generator.py:191-239`) has **no static mount**. Polish can't post-edit it without triggering "tampered" drift. The clean path: `backend_codegen` emits a tolerant `try/except` static-setup hook once (mirroring the existing optional pages/user_routers include). | **New requirement FR-25.** "Zero changes to backend_codegen" was wrong — one small, harmless generator hook is required. |
| OQ-2 + FR-5/FR-16: SDK has *zero* skill invocation; mechanism is net-new | Scaffolding exists: `SkillAgent(BaseAgent)` (`skills/agent.py:134`), `SkillAwareWorkflow` (`workflows/skill_aware_workflow.py:95`), MCP gateway — but it's marked **"Phase 2 in progress"**, there is **no `claude` CLI shell-out**, and it's unproven whether `SkillAgent` can run an arbitrary Claude Code *user* skill (markdown SKILL.md) vs. only SDK-registered MCP skills. | OQ-2 partially resolved + **new highest risk (OQ-8)**. FR-16 reframed onto existing scaffolding; readiness must be validated before depending on it. |
| FR-5 + FR-16 implied vendoring and orchestration are the same mechanism | Vendoring files into `.claude/skills/` (availability — the "installs nothing" goal) is **distinct** from how Tier 2 *executes at polish time* (SkillAgent/MCP). They coexist: vendoring makes the skill present in the project for later human use; SkillAgent/MCP is how the SDK runs it during a polish invocation. | FR-5 and FR-16 separated; mechanism boundary made explicit. |
| FR-11: invent a "small set of curated themes" | `theme-factory` ships **12 themes** as a directory of presets (`~/.claude/skills/theme-factory/themes/`). | FR-11 narrowed: adapt theme-factory's presets to plain-CSS/Jinja2 rather than inventing palettes. |
| FR-4/FR-5/FR-6 vendoring installer is new design work | `CapDevPipeInstaller` is a directly-mirrorable template: `InstallConfig` dataclass, `Action`/`ActionType`, `Manifest` (PENDING→COMPLETE), `plan_actions()`/`execute()`/`verify()`/`apply_mode()` re-run modes (`capdevpipe_installer.py`). | FR-4/5/6 narrowed to "mirror `CapDevPipeInstaller`" — known pattern, not invention. |

**Resolved open questions:**
- **OQ-1 → Resolved (DeterministicFileProvider).** Register a `PresentationPolishFileProvider` at the `startd8.contractors.deterministic_providers` entry point owning `app/static/css/app.css`, `app/templates/_components.html`, and `app/static_setup.py` (all carrying a `# STARTD8-POLISH` marker). It is invisible to `generate backend` and gives polish its own skip-hook + idempotency.
- **OQ-2 → Partially resolved (SkillAgent/MCP path exists).** Tier 2 reuses `SkillAgent` + `SkillAwareWorkflow`; no `claude` shell-out is needed. Residual readiness risk moved to **OQ-8**.
- **OQ-3 → Resolved.** Vendor into the project's `.claude/skills/` (project-local, discoverable by the project's own Claude Code), with provenance (source path + hash) in the manifest. A globally-installed user copy is not touched; the project-local copy wins for project work.
- **OQ-4 → Largely resolved.** `theme-factory` (palettes/fonts, framework-agnostic) + `universal-design` (WCAG, framework-agnostic HTML/CSS) transfer directly to the Jinja2/plain-CSS target; `frontend-design` (React/Vue/Motion-leaning) contributes *aesthetic direction* only, with its React/Motion specifics discarded. Tier 1 internalizes theme-factory + universal-design knowledge; `frontend-design` is a Tier-2-only input.
- **OQ-7 → Recommended resolution.** Register as `startd8.enhance.presentation_polish` under a new `enhance` category (sibling to `generate`/`assist`), keeping the post-build "enhancement" framing distinct from contract-derived `generate`.

**Still open:** OQ-5 (theme preview UX), OQ-6 (standalone vs cascade step). **OQ-8 resolved by spike — see §0.1.**

---

## 0.1 Spike Findings (OQ-8 — skill-execution readiness)

> A Phase-0 spike (2026-06-08) inspected the `SkillAgent`/MCP machinery to answer OQ-8 *before*
> committing to Tier 2. Result: **NO — the existing path cannot execute a Claude Code user-skill.**
> The answer is dispositive by code inspection; no live API call was made (one would have produced a
> false pass — see below).

**Finding.** Both `SkillAgent._call_mcp_skill` (`skills/agent.py:485`) and the "production"
`MCPGateway._execute_mcp_skill` (`mcp/gateway.py:623`) do the same thing: declare an unused
`startd8_use_skill` tool and send the base model the literal string `"Execute the {skill_id} skill
with this task: {prompt}"`. Three confirmations the skill's content never reaches the model:
1. **No skill loaded.** `grep` for `SKILL.md` / `.claude/skills` / `read_text` across all of `src/`
   returns nothing. The actual `frontend-design/SKILL.md` is never read; the model runs on whatever it
   associates with the *name* (for a local user-skill: nothing reliable).
2. **Declared tool never executed.** No tool-use loop exists; the code reads `block.text` and would
   raise `"No text content found"` if Claude actually invoked the tool. The design works against real
   tool use.
3. **"MCP" is aspirational.** `_discover_skills()` (`mcp/gateway.py:302`) hardcodes 3 game/review
   metadata stubs (`"In production, this would query the MCP server"`); `self._client` is a plain
   Anthropic client. No MCP server, no skill mounting.

**Why no live call.** A live `SkillAgent("frontend-design")` call returns CSS — the base model
generates CSS from the prompt alone — which reads as success. That is a Looks-Like-Success false
pass: the output is generic base-model CSS *falsely attributed* to the skill, since the mechanism
guarantees the vendored `SKILL.md` has zero influence. The differential test (does vendoring change
output? — no, by construction) is the only honest live test and its result is already known.

**Constructive resolution.** The real, simpler mechanism: **read the vendored `SKILL.md` and inject
it as the `system_prompt`** of a normal SDK agent call (`system_prompt` is supported on all agents).
No MCP build required. This makes FR-5 vendoring **load-bearing for execution**, not just
availability, and unifies the tiers: both internalize skill knowledge — Tier 1 into $0 deterministic
generators, Tier 2 into one gated LLM call seeded by the SKILL.md text.

**Impact:**
- **Do NOT build Tier 2 on the existing `SkillAgent`/MCP path** — it would silently ship generic
  output mislabeled as skill-driven.
- **v1 ships Tier 1 only** (deterministic, $0 — the headline, fully de-risked). Tier 2 is reframed
  (FR-16) onto the SKILL.md-as-system-prompt mechanism and is a fast-follow, not a v1 blocker.
- **Flag the `SkillAgent`/MCP stub as misleading** (separate cleanup): it is named and documented as
  if it executes skills but does not — a latent false-attribution trap for any future caller.

---

## 1. Problem Statement

The SDK's `generate backend` cascade deterministically projects a `.prisma` contract into a
**structurally complete** all-Python app (FastAPI + Pydantic + SQLModel + Jinja2 + HTMX): models,
tables, CRUD routes, list/detail/form templates, content pages. This is "applicational
completion" — bucket 1. It runs, it's correct, and it is **visually bare**: the only styling is a
16-line inline `_BASE_STYLE` constant (`backend_codegen/htmx_generator.py:139-152`) — system fonts,
hairline table borders, green/red status colors. No design tokens, no typography system, no
mounted stylesheet, no reusable components, no accessibility hardening beyond what semantic HTML
gives for free.

A user who has just run the cascade now faces a gap the SDK does not currently close: the app is
*built* but not *presentable*. Closing that gap today requires the user to know that Claude Code
skills like `/frontend-design`, `/theme-factory`, and `/universal-design` exist, to have them
installed, and to know how to drive them against a server-rendered Jinja2/HTMX codebase (which is
not their native target — they lean React/Vue/Motion). That is exactly the complexity this
capability should hide.

**The thesis:** the SDK builds software *and* ships the tools to make it operationally
presentable. The user should run one SDK command against their structurally-complete project and
get a polished, accessible, themed presentation layer — without ever learning what a "skill" is or
installing one.

### 1.1 Scope reconciliation with the bucket model (load-bearing)

`CLAUDE.md` puts visual design / CSS / typography in **bucket 4** (real value content, user-owned,
out of SDK scope) and anchors the SDK on determinism-first / $0. This capability consciously
extends that boundary, and the extension must be principled, not ad-hoc. The reconciliation:

| Tier | What it is | Bucket mapping | Cost | Owner |
|------|-----------|----------------|------|-------|
| **Tier 1 — Deterministic design system** | A curated, opinionated baseline: design tokens → real mounted stylesheet, accessible component partials, sensible layout/IA, applied to the generated templates | **bucket 1** ("applicational completion of the *presentation* layer" — a well-dressed skeleton, still not brand content) | **$0, no LLM** | SDK |
| **Tier 2 — Bespoke skill-driven polish** | Optional, gated, LLM-assisted aesthetic direction via vendored `/frontend-design` + siblings, producing a distinctive theme | **bucket 3** (the one in-scope LLM aspect — integration/wiring of presentation, grounded + gated) | LLM (opt-in, tracked) | SDK (orchestration); direction chosen with user |
| **Real brand assets / copy / logo / imagery** | The company's actual visual identity and content | **bucket 4** | — | **USER — still out of scope** |

The deterministic default is the headline; the skill is the optional upgrade. This keeps the
determinism-first thesis intact (a polished app at $0) while delivering the requested skill
leverage as a bounded, opt-in tier.

### 1.2 Gap table

| Component | Current State | Gap |
|-----------|--------------|-----|
| Stylesheet | 16-line inline `_BASE_STYLE` in every template via `base.html` | No real, mounted, cohesive stylesheet; no design tokens / CSS variables |
| Typography | `system-ui, sans-serif` | No type scale, no font pairing, no hierarchy |
| Components | Raw HTML tables/forms/nav | No reusable styled partials (buttons, cards, badges, empty states, flash) |
| Layout / IA | Single `max-width` column, flat nav | No responsive grid, no visual hierarchy, no IA for many-entity apps |
| Accessibility | Whatever semantic HTML yields | No WCAG 2.2 AA pass (ARIA, focus, keyboard, contrast verified) |
| Skill access | None — SDK has zero programmatic skill invocation | No mechanism to vendor or run `/frontend-design` & siblings on behalf of the user |
| Entry point | `generate backend`, `wireframe`, `assist` operate on a target project | No `polish` verb; no post-build enhancement step in the cascade |
| Regeneration safety | `generate backend` is byte-identical idempotent over **owned kinds** | Polish must not be clobbered by a later `generate backend`, and must not break idempotency |

---

## 2. Requirements

### A. Capability surface & entry point

- **FR-1.** Provide a new SDK capability invoked as `startd8 polish` that operates **on a downstream
  target project** (a `--project <path>` / target-root argument), mirroring the operate-on-target
  pattern of `generate backend`, `wireframe`, and `assist scan` — not on the SDK itself.
- **FR-2.** Surface the capability in the TUI as a menu choice. It belongs in the same
  post-build/enhancement neighborhood as the cap-dev-pipe installer (TUI "PROJECT SETUP" group,
  `tui_improved.py:295-296`); consider a sibling "ENHANCE" grouping.
- **FR-3.** The capability MUST be **headless-drivable** (config-object / dict driven, no
  interactive prompts required) exactly as `CapDevPipeInstaller.execute()` /
  `install_capdevpipe_flow(config=...)` are, so it is usable from CI, scripts, and the cap-dev-pipe
  cascade as a non-interactive step.
- **FR-4.** The capability MUST be **idempotent and re-runnable**, emitting an authoritative
  **manifest** (analogous to `.cap-dev-pipe/.install-manifest.json`) recording what was written,
  with pending→complete state markers and `created_paths` semantics, so re-runs reconcile rather
  than duplicate. **(Planning: mirror `CapDevPipeInstaller` — `InstallConfig`/`Action`/`Manifest`/
  `plan_actions()`/`execute()`/`verify()`/`apply_mode()`. Known pattern, not new design.)**

### B. Skill vendoring mechanism ("hide installation")

> **Mechanism boundary (planning split of v0.1).** *Vendoring* (this section) makes the skill
> **present** in the downstream project so the user installs nothing — an availability concern,
> mirroring how cap-dev-pipe embeds scripts. *Execution* of the skill during a polish run (§D) is a
> **separate** mechanism (`SkillAgent`/`SkillAwareWorkflow`/MCP). Do not conflate them.

- **FR-5.** The SDK MUST be able to **vendor the required Claude Code skills into the downstream
  project** so the user installs nothing. Following the cap-dev-pipe embedding pattern, polish
  bundles/symlinks the needed skills into the project's **`.claude/skills/`** (project-local,
  discoverable by the project's own Claude Code — OQ-3 resolved). Tier 1 needs only
  `theme-factory` + `universal-design` (framework-agnostic, transfer directly); `frontend-design`
  is vendored only when the user opts into Tier 2. Each is a **directory** (SKILL.md + assets), not
  a single file — vendor the whole directory.
- **FR-6.** Vendoring MUST be **manifest-tracked and idempotent**: re-running polish reconciles the
  vendored skill set (add/upgrade/repair/remove-orphan) without duplication, mirroring the
  cap-dev-pipe re-run modes.
- **FR-7.** The user MUST NOT need to know a skill is involved. The polish command's UX speaks in
  terms of *outcomes* ("apply a polished, accessible theme") not mechanism ("install and run the
  frontend-design skill"). Skill identity is an implementation detail surfaced only in verbose/
  diagnostic output.
- **FR-8.** Vendored skills MUST carry **provenance** (source path, version/hash) in the manifest so
  a later SDK upgrade can detect drift and re-vendor.

### C. Tier 1 — Deterministic design system ($0, default)

- **FR-9.** Polish MUST emit a **real, mounted stylesheet** (e.g. `app/static/css/app.css` served
  via FastAPI static mount), replacing the inline `_BASE_STYLE` path, with the generated templates
  referencing it. (NFR: server-rendered, plain CSS, no build step, no Tailwind toolchain.)
- **FR-10.** Polish MUST emit **design tokens as CSS custom properties** (color palette, type scale,
  spacing scale, radii, shadows) so the theme is consistent and re-themeable by changing variables.
- **FR-11.** Polish MUST offer a **small set of curated themes** selectable by name; one is the
  default. **(Planning: adapt `theme-factory`'s 12 shipped preset themes — palettes + font
  pairings — to plain-CSS custom properties + Jinja2, rather than inventing palettes.)**
- **FR-12.** Polish MUST emit a **reusable styled component set** as Jinja2 macros/partials —
  buttons, cards, badges, flash/toast messages, empty states, form fields — and the generated
  list/detail/form templates MUST consume them.
- **FR-13.** Polish MUST apply **layout & information architecture** improvements: responsive grid/
  container, a real navigation hierarchy (handles many-entity apps, not a flat nav bar), and a
  consistent visual hierarchy across list/detail/form views.
- **FR-14.** Polish MUST apply a **WCAG 2.2 AA accessibility baseline** to the generated
  templates/components: semantic landmarks, ARIA where needed, visible focus, keyboard operability,
  and verified color-contrast in every shipped theme. (universal-design knowledge, internalized.)
- **FR-15.** Tier 1 MUST be **$0 / no LLM** and produce **deterministic, byte-stable** output for a
  given (contract, theme, SDK version), consistent with the `generate backend` philosophy.

### D. Tier 2 — Optional skill-driven bespoke polish (gated, LLM)

- **FR-16.** Polish MUST offer an **optional, explicitly opt-in** bespoke tier that orchestrates the
  vendored `/frontend-design` (+ `/theme-factory`, `/universal-design`) skills to generate a
  **distinctive aesthetic direction** beyond the curated defaults (custom palette, typography,
  motifs), emitted as tokens/CSS the Tier-1 pipeline can consume. **(Post-spike, §0.1: do NOT use the
  existing `SkillAgent`/MCP path — it does not load skill content and would mislabel generic output as
  skill-driven. Real mechanism: read the vendored `frontend-design/SKILL.md` and inject it as the
  `system_prompt` of one gated SDK agent call. v1 ships Tier 1 only; this is a fast-follow.)**
- **FR-17.** Tier 2 MUST be **gated behind explicit user consent** with an up-front cost estimate
  (it spends LLM tokens), never auto-running. Default behavior of `startd8 polish` is Tier 1 only.
- **FR-18.** Tier 2 output MUST be **constrained to the deterministic stack**: it produces plain CSS
  + design tokens + Jinja2-compatible markup, NOT React/Vue/Motion. The orchestration must steer
  `/frontend-design` away from its React-native defaults (its sweet spot) toward server-rendered
  HTML/CSS-only output.
- **FR-19.** Tier 2 output MUST flow through the **same accessibility gate** as Tier 1 (FR-14) — a
  bespoke theme that fails contrast/keyboard checks is rejected or repaired, not shipped.

### E. Safety, idempotency & regeneration coexistence

- **FR-20.** Polish MUST be **non-destructive to user edits**: it must not silently clobber
  hand-modified templates/CSS. Re-runs detect user modifications (hash vs manifest) and warn/skip
  rather than overwrite, mirroring the cap-dev-pipe install-manifest discipline.
- **FR-21.** Polish output MUST **coexist with `generate backend` idempotency**. **(Planning:
  resolved.)** Register a `PresentationPolishFileProvider` at the
  `startd8.contractors.deterministic_providers` entry point owning the polish files (each carrying a
  `# STARTD8-POLISH` marker). `generate backend --check` only inspects `# GENERATED`-marked files, so
  polish files are untouched by backend regeneration; the provider additionally makes the **prime
  contractor skip-hook** treat polish files as $0/owned (so an LLM pass never regenerates them) and
  gives polish its own drift/idempotency check.
- **FR-22.** Polish MUST be **verifiable**: after applying, confirm the app still imports/serves
  (reuse the runtime-smoke approach in `tests/unit/backend_codegen/test_runtime_smoke.py`), and run
  an automated accessibility/contrast check on the rendered output.

### F. Observability & cost

- **FR-23.** Polish MUST emit OTel telemetry (spans for each tier/phase) via the SDK's
  `get_logger`/OTel conventions, consistent with other capabilities.
- **FR-24.** Tier 2 LLM spend MUST be tracked through the SDK `costs/` machinery; Tier 1 MUST report
  `$0.00` explicitly (like the skip-hook backend kinds).

### G. Backend codegen coordination (new — surfaced in planning)

- **FR-25.** `backend_codegen`'s `main.py` generator (`crud_generator.py:191-239`, owned kind
  `fastapi-main`) MUST emit a **tolerant, no-op-safe static-setup hook** (a `try/except` import of a
  `app/static_setup.py` and a guarded call), mirroring the existing optional pages/user_routers
  include pattern. This is a **one-time, harmless** change to the always-emitted `main.py` so that
  polish can drop in a polish-owned `static_setup.py` (which mounts `app/static`) **without
  post-editing `main.py`** and triggering "tampered" drift. Without this hook, polish cannot mount a
  real stylesheet without breaking backend idempotency. (Corrects the v0.1 implication that polish
  required zero backend_codegen changes.)

---

## 3. Non-Requirements

- **NR-1.** Does NOT author real brand identity, logo, imagery, marketing copy, or company content
  (bucket 4 — user/company owned). Polish makes the *skeleton* presentable; it does not invent the
  company's visual brand.
- **NR-2.** Does NOT introduce a JS build step, Tailwind, a bundler, npm, or a component library
  install. All-Python, server-rendered, plain CSS only (stack target confirmed).
- **NR-3.** Does NOT support the legacy TS/React `generate frontend` (Prisma→Zod) surface. All-Python
  only for v1.
- **NR-4.** Does NOT make Tier 2 (LLM bespoke) the default or auto-run it.
- **NR-5.** Does NOT add a new general-purpose skill-execution framework to the SDK beyond what this
  capability needs (vendoring + the specific orchestration path). A broader "SDK runs any skill"
  abstraction is out of scope for v1.
- **NR-6.** Does NOT replace `/dbrd-cr8r` / Grafana dashboard styling — this is app UI polish, not
  observability dashboards.

---

## 4. Open Questions

> Resolved in planning: **OQ-1** (→ DeterministicFileProvider, FR-21), **OQ-2** (→ SkillAgent/MCP,
> residual risk → OQ-8), **OQ-3** (→ project-local `.claude/skills/` + provenance, FR-5/FR-8),
> **OQ-4** (→ theme-factory + universal-design transfer; frontend-design = Tier-2 direction only),
> **OQ-7** (→ `startd8.enhance.presentation_polish`, new `enhance` category). See §0. Remaining:

- **OQ-5.** **Theme selection UX.** How does the user pick/preview a theme? Static named presets
  only, or a `wireframe`-style $0 preview of what each theme yields before applying? (Lean: reuse
  the read-only `wireframe` advisory pattern for a $0 preview.)
- **OQ-6.** **Capability vs. cascade step.** Is `polish` a standalone command only, or also a
  trailing step in the `generate` cascade / cap-dev-pipe run (auto-applying Tier 1 after backend
  gen)? If the latter, how does it interact with the deterministic-cascade ordering? (Lean:
  standalone first; cascade-step is a fast-follow once Tier 1 is byte-stable.)
- **OQ-8.** **RESOLVED by spike (§0.1): NO.** The `SkillAgent`/MCP path cannot execute a Claude Code
  user-skill — it never loads `SKILL.md`. Tier 2's real mechanism is SKILL.md-as-`system_prompt`
  (FR-16). v1 ships Tier 1 only; Tier 2 is a fast-follow. Does not block Tier 1.

---

*v0.3 — Post-spike. OQ-8 resolved (§0.1): the existing `SkillAgent`/MCP path cannot execute a Claude
Code user-skill (never loads `SKILL.md`), so Tier 2 is reframed onto SKILL.md-as-`system_prompt` and
**v1 ships Tier 1 only** (deterministic, $0 — the headline). FR-16 rewritten; FR-5 vendoring is now
load-bearing for Tier-2 execution. A separate cleanup should flag the misleading skill-execution
stub. Prior: v0.2 post-planning (5 OQs resolved, FR-25 added, FR-21 de-risked, FR-5/FR-16 split).
Spine unchanged: vendored-skill delivery (cap-dev-pipe pattern), all-Python (FastAPI + Jinja2 + HTMX
+ plain CSS), full scope (theme + accessibility + layout/IA + components).*
