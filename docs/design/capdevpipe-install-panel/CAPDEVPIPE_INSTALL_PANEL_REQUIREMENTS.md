# CapDevPipe Install Control Panel — Requirements

**Project:** startd8-sdk   **Criticality:** medium
**Version:** 0.6.10   **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** control-central-panel
**Pairs with:** `CAPDEVPIPE_INSTALL_PANEL_PLAN.md`
**Inherits standards:** det-req-kit; Control Central Tier conventions (`tools/control-panels/REQUIREMENTS.md`); SDK panel-gen principles (`docs/CONTROL_PANEL_GENERATION_REQUIREMENTS.md` REQ-SDK-P1..P5); kickoff **audience tokens + marker grammar** (`docs/design/kickoff/PERSONA_EXPERIENCES_REQUIREMENTS.md`, `KICKOFF_CONTENT_CONTRACT_REQUIREMENTS.md`) — **cite the grammar; do not register install docs into concierge `_EXPERIENCE_DOCS` or call kickoff ledger / preference-ladder APIs**

**Depends on (shipped / critical path):**
- `CapDevPipeInstaller` + `startd8 capdevpipe install` / `defaults` (headless)
- Control Central v0.2+ (`tools/localhost_tools/control_central/`)
- Hand-built panel at `control-panel/capdevpipe-install/` (Iteration-1 skeleton; FR-14 URL seeding; viewport ops-deck UI)
- Kickoff **vocabulary only:** tokens `beginner|intermediate|advanced`, `disclosure_tier` mapping, PLAIN/TL;DR/BANNER markers (owned by kickoff docs + `writes.py` marker constants)

**Deferred dependencies (not on audience/instructions critical path):**
- `feat/control-panel-gen` / `startd8 generate panel` (FR-1 / FR-11 / FR-12)
- Soft lovable preset (FR-9)

---

## 0. Planning Insights (Self-Reflective Update)

> **v0.5 reflective distillation (audience/instructions + accidental complexity).** Planning against the *actual* panel (`index.html` ~780 LOC monolith; `url_params.js`; CC static file serve) and kickoff APIs showed v0.4's FR-15–19 *recreated* kickoff's preference/ledger machinery as five FRs. That is **accidental complexity in the spec**. Essential problem: *one fluency lens over one install UI + one instruction doc*. Essential solution: **FR-15 (lens) + FR-16 (doc)**, client-side slice of a static markdown file already servable from `PANEL_HOME`, field visibility via one `data-min-audience` rank rule — not a second Python slicer, not `_EXPERIENCE_DOCS` registration, not project-audience inheritance.
>
> Prior insight trail (still true): v0.1–v0.3 established custom Tier-2 form + Preview gate + URL seeding; v0.4 correctly rejected stakeholder personas as “expertise.”
>
> **v0.5.2 (Genchi — live Preview stdout):** A successful dry-run for `portal-v2` emitted ~25 planned actions (mkdir / many symlinks / copies / `pipeline.env` write / wrapper script / `.gitignore` ensure), the line `N action(s) planned; nothing written.`, a preview-gate token path, and stderr warning about uncommitted target changes. FR-13 as “dump stdout” leaves Novice with unreadable path spam. **Essential:** after Preview, surface an operator summary *derived from that same output* (target/method/profile, counts by action kind, nothing-written, warnings); raw log stays available under Console detail / Expert — do not invent a second installer report channel.
>
> **v0.5.3 (Genchi — live Install):** Same target then received a real embed (`state: complete` in `.install-manifest.json`, `pipeline.env` with correct `PROJECT_ROOT`, symlink method). Post-Install Console needs the same treatment as Preview, but the apex must say **written** (not “nothing written”) and confirm embed path + method/profile from the apply log / manifest cues present in stdout.
>
> **v0.5.4 (Genchi — Preview on already-installed target):** Dry-run against portal-v2 *after* Install still listed a full mkdir/symlink plan and did **not** announce “existing install” unless `--rerun-mode` was set. Operators reading Preview as “what will happen” miss that `.cap-dev-pipe` is already there. **Essential:** when `detect_existing` is true, dry-run (CLI + Console apex) SHALL state **already installed** *before* the action list; panel summary mirrors that; raw retained.
>
> **v0.5.5 (Genchi — next step after Install):** After embed, the operator’s real next command is a **delivery** dry-run (`run-cap-delivery.sh --plan … --requirements … --dry-run`), not another install Preview. Copy-pasting shell is accidental friction. **Essential:** one post-Install (or already-installed) **Dry-run delivery** button that invokes the embedded orchestrator with `--dry-run` only — never a mutating pipeline run from this panel.
>
> **v0.5.6 (persist project + Installed state):** Operators re-open the panel and re-type `TARGET_ROOT`. Once `.cap-dev-pipe` exists, Preview/Install are the wrong apex (re-install noise). **Essential:** persist Project folder in panel `localStorage`; when embed is present, hide Preview/Install and show a green **Installed** badge in Install’s place; keep Dry-run delivery.
>
> **v0.5.7 (Run workflow gated on delivery dry-run):** After a successful delivery dry-run, operators need a **Run workflow** button (mutating `run-cap-delivery.sh` without `--dry-run`), gated like Preview→Install. **Essential:** FR-21 dry-run fingerprint token; refuse Run without matching Dry-run delivery.
>
> **v0.6.0 (button-driven pipeline stages + defaults):** Operators still shell out for plan-ingestion and prime. Button labels (“Run workflow”) do not name the stage. Run name typos break gates. **Essential:** FR-22–FR-25 — every post-install stage as clearly labeled Dry-run / Run (or List) buttons; sensible defaults for run name + provenance; per-stage dry-run gates.
>
> **v0.6.1 (ingestion-complete lock, mirror Install):** After a successful plan ingestion, Dry-run / Run plan ingestion remain clickable — same class of noise as Preview/Install after embed. **Essential:** FR-26 — when ingestion artifacts for the current run are present, hide Stage-5 dry-run/run buttons and show a green **Ingested** badge (same visual language as **Installed**). Re-ingestion / reinstall controls are **deferred to end of sprint** (non-goal until then).
>
> **v0.6.2 (CLI twin under each button):** Operators who prefer the terminal still need the exact cwd + argv the panel would run. Hunting docs/scripts is accidental friction. **Essential:** FR-27 — under each pipeline action button, show the working directory and equivalent shell command filled from current form values.
>
> **v0.6.3 (completion wizard — sequential apex):** Flat button rows show every stage at once and treat List-prime as a peer. Operators need the **wizard step-state pattern** (ordered steps, one current, completed locked — same spine as SDK `WIZARD_STEP_STATE` / FR-WZ linear flows, adapted to this Tier-2 panel because generated `flow_*` routers are app-runtime, not Control Central). **Essential:** FR-28 — L→R completion wizard; Run primary with Dry-run nested smaller underneath; List prime nested under Prime; **only the next logical step’s CLI twin** visible.
>
> **v0.6.4 (derived delivery handle):** Freeform Run name caused typo divergence (`ortal-v2-preview` vs `portal-v2-preview`) and broke Intent–Delivery naming discipline (mutable title ≠ identity). **Essential:** FR-29 — delivery handle is **derived** (`{project}-preview`), not an operator input; cite ContextCore Deterministic Intent–Delivery Language four-form naming (readable handle from structured identity).
>
> **v0.6.5 (go affordance — next-logical is green):** Wizard **Run** buttons used danger/red borders, which reads as “stop / don’t press” for the exact control the operator should take next. **Essential:** FR-30 — the next-logical sequence control is always green (go); danger/red is reserved for non-sequence destructive Expert actions (Repair, orphan/prime cleans, Danger-fold overrides).
>
> **v0.6.6 (operator failure analysis):** Failed pipeline/install runs dump raw stderr (e.g. Anthropic “credit balance is too low”) without a useful apex. Operators need **what happened / why / what to do** so the same failure stops recurring. **Essential:** FR-31 — Console apex failure analysis for non-happy paths (billing, API key, rate limit, gate refuse, provenance, registry stale, …); raw retained under Show raw. Cite SA `provider_error` / operational-action grammar; do not call SA LLM from the panel.
>
> **v0.6.7 (in-flight high-level progress — prime first):** Long runs (especially **Run prime · 6**) leave Console on a static “not streamed live” wait line while Control Central buffers stdout until exit. Operators cannot tell whether the queue is loading, developing `PI-00xa`, integrating, or stuck. Prime already writes durable queue state to `{TARGET_ROOT}/.prime_contractor_state.json`. **Essential:** FR-32 — while a supported workflow action is in flight, show **high-level progress steps** derived from existing durable artifacts (prime first); do not invent a new orchestration bus; do not require SSE in Control Central this sprint.
>
> **v0.6.8 (page title + always-visible project activity):** Operators open the panel while a CLI (or prior) Stage 6 is already running and see a static tab title (“Add pipeline · project folder”) and an empty/collapsed Console — **no faithful signal that the project is working or how far it got**. FR-32 progress lived only inside the Console fold and only while *this* browser session’s `/run` was in flight. **Essential:** FR-33 — intuitive `document.title` + always-visible activity strip driven by the same durable prime probe (idle-poll when Project folder is set), independent of Console expand state and independent of whether `/run` was started from this tab.
>
> **v0.6.9 (per-feature completion fidelity):** Aggregate `7/21` alone still reads as a static bar while features finish one-by-one. Operators need to **see each 1/N completion land** — which `PI-*` just finished, which are done, which is current, which remain. **Essential:** FR-34 — probe emits ordered per-feature statuses; activity UI renders a feature checklist that advances after each completion (and briefly highlights the just-completed id).
>
> **v0.6.10 (indirect reuse / REQ-09):** Panel FRs invoke `startd8 capdevpipe …` but Contract Projection only named CC panel artifacts — CLI seam was prose. Phase 4.5 key `#8 lifecycle/bootstrap` (`~/Documents/dev/dev-os/det-req-kit/BACKEND_ROUTING.md`) applied as **dual-name**, not Backend switch: keep primary `Backend: control-central-panel`; name the living Typer surface with `python-cli-surface` harvest kinds (`console-script` · `command` · `subcommand` · `option` · `exit-class`) so panel FRs and CLI share one typed contract. Cite `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8; do not redesign CapDevPipe.

| v(n-1) Assumption | Planning Discovery | Impact |
|-------------------|--------------------|--------|
| FR-13 “show stdout” is enough for Preview | Live dry-run is a long symlink list; decision-useful bits are header + counts + “nothing written” + warnings | **FR-13 expanded** — post-Preview summary reflecting console; raw retained |
| Post-Preview summary covers Install too | Install log is the same action list but *applied*; operator needs “written / complete” not dry-run wording | **FR-13** — parallel post-Install summary |
| Existing-embed CLI notice only when `--rerun-mode` set | Dry-run with mode unset on an installed target looks like a fresh plan | **FR-13 + CLI** — always announce existing before action list |
| Non-goal “no pipeline from panel” forbids all delivery | Operators still need a $0 dry-run alternative to the shell after Install | **FR-18** dry-run; **FR-21** gated mutating Run delivery; **FR-22** full stage buttons |
| Project folder is session-only; Preview/Install stay after Install | Re-entry friction + wrong CTA after successful embed | **FR-19** persist target; **FR-20** Installed badge replaces Preview/Install |
| Delivery-only CTAs finish the operator journey | Chain continues: plan-ingestion → prime; labels must name stage + dry-run vs run | **FR-22–FR-25** button-driven stages + defaults + gates |
| Stage-5 buttons stay after successful ingestion | Same failure mode as reinstall noise (FR-20): wrong apex after success | **FR-26** Ingested badge; hide Stage-5 dry-run/run; re-run deferred |
| Panel buttons replace the need to know CLI | Operators still want copy-paste cwd + command that matches the button | **FR-27** CLI twin; **FR-28** narrows to next-logical only |
| Flat action-bar of all stages is enough | Sequential pipeline is a wizard: install → delivery → ingestion → prime; list-prime is a prime subcommand | **FR-28** completion wizard layout |
| Freeform Run name is a harmless defaultable field | Typos fork pipeline-output identity; Intent–Delivery treats readable handles as derived | **FR-29** derived `{project}-preview` handle; no RUN_NAME input |
| Wizard Run buttons should look “dangerous” (red) | Red reads as stop for the prescribed next action | **FR-30** green go on next-logical control; danger only for Expert non-sequence cleans |
| Failed run → dump stderr is enough | Operators cannot tell billing vs key vs gate vs model from a Python traceback | **FR-31** what / why / fix apex; raw under Show raw |
| Long prime run → static “wait for stdout” is enough | Operators cannot see feature/queue progress until exit; CC does not stream | **FR-32** poll durable `.prime_contractor_state.json` for high-level steps (prime first) |
| FR-32 in Console during `/run` is enough visibility | Console is often collapsed; CLI-started primes leave the page looking idle; tab title stays generic | **FR-33** always-visible activity + title naming project + working/done counts |
| Aggregate `n/N` glance is enough mid-prime | Operators cannot tell *which* of the N features finished after each completion | **FR-34** ordered feature checklist + just-completed highlight |
| Panel Contract Projection need only CC artifact kinds | Panel scripts are a thin env→argv wrapper over living `startd8 capdevpipe` Typer; FR Touches named modules/prose (`cli_capdevpipe._preview_install`) not harvest entry names | **v0.6.10** dual-name CLI seam (primary Backend unchanged); FR Touches cite entry names |
| FR-15–19 (audience drafts) must mirror kickoff's full ladder + surface tables | Kickoff ladder exists for *confirm-walk ledger*; install panel has no ledger. `load_experience_doc` only accepts closed keys under `concierge_templates/` (`intro`, `workbook`). Named API `resolve_audience` **does not exist** — real symbol is `resolve_audience_preference` | **Collapsed former audience FR-17/18/19 into FR-15**; FR-16 = doc ownership; OQ-4/5 resolved *against* coupling. (**FR-18** later reused for delivery dry-run CTA.) |
| Register install doc into `_EXPERIENCE_DOCS` (reuse) | Couples workstation ops copy to kickoff instantiate package; forces Python cold path for every help render | **Static fetch + JS slicer** of `OPERATOR_INSTRUCTIONS.md` (CC already serves PANEL_HOME); grammar cited from `writes.py`, not imported |
| Inherit kickoff project audience via target prefs | Cross-domain surprise: beginner kickoff project mutes Repair without operator intent; needs Python bridge | **OQ-5 → NO**; URL → localStorage → intermediate only |
| Three-tier field *lists* in the FR are the surface contract | Enumerated allowlists are the Accidental-Complexity anti-pattern; one rank attribute dissolves them | FR-15 surface = **rank rule**, not a field table in the FR |
| FR-1/11/12 (generator) block audience work | Hand-built panel already runs; generator is orthogonal | Softened to deferred iterations |
| FR-10 form-aware probes are already true | CC `/status` probes get **no** form env — `probe_target`/`probe_embed` fail when TARGET_ROOT unset even if the form shows a path | Softened FR-10; honest probes only (startd8 + source) until optional Mottainai `state/form.env` |
| Hardcoded `PORTAL_V2` deep-link button is helpful | Machine-specific path is accidental state in UI (`index.html` ~L544) | Plan debt: demo uses `?audience=beginner` (or omit host path) |
| `expertise_level` as co-equal URL key | Vocabulary drift vs kickoff's single token `audience` | Canonical `audience`; `expertise` non-normative alias only; drop `expertise_level` |

**Resolved open questions (this pass):**
- **OQ-4 → Static MD + client slicer.** Serve `OPERATOR_INSTRUCTIONS.md`; slice in JS with the same markers as `writes.py`. Do **not** register into `_EXPERIENCE_DOCS`; do **not** import private `_extract_slice`.
- **OQ-5 → NO project inheritance.** Audience = URL → panel localStorage → default `intermediate`. Never call `resolve_audience_preference(TARGET_ROOT)`.

### 0.1 Lessons-Learned Hardening (v0.5)

> ContextCore `lesson recall` for design-docs returned low-relevance hits (unrelated domains). Fell back to curated `Lessons_Learned/sdk/Design_Docs_LESSONS_LEARNED.md`. Applied:

- **[Leg vocabulary-drift / single-source §5]** — Audience tokens + PLAIN/TL;DR markers are owned by kickoff docs/`writes.py`. Install panel **cites** them; must not restate a forked alias vocabulary (`expertise_level`) as co-equal. → FR-15; URL table trimmed.
- **[Leg phantom-reference §6 / multi-codebase §12]** — Spec named `resolve_audience` and treated `load_experience_doc` as path-capable. Grep: no `resolve_audience`; `load_experience_doc` requires `_EXPERIENCE_DOCS` key. → Reference-Audit table; OQ-4/5 closed against phantoms.
- **[Leg overloaded-term co-location §13]** — Do not co-locate install audience prefs into kickoff `build-preferences.yaml` writers or `audience.py` ledger APIs. → localStorage / URL only (FR-15).
- **[Leg CRP steer §15]** — Least-reviewed load-bearing artifact for next CRP: **Iteration 1b audience surface + slicer contract** (not re-litigating FR-5 single-engine / FR-6 Preview gate).

### 0.2 Design-Principle Hardening (v0.5)

> Checked `docs/design-princples/` (Accidental Complexity anti-principle, Mottainai, Genchi Genbutsu, Sotto):

- **[Accidental Complexity]** — Five FRs + dual slicer options + project-audience inheritance ≫ essential lens. → FR-15+FR-16 only; one rank rule; no kickoff runtime import.
- **[Genchi Genbutsu]** — Bind instructions to the **real** file `OPERATOR_INSTRUCTIONS.md` on disk (already fetchable from PANEL_HOME), not a concierge registry proxy. Bind API names to grep-proven symbols.
- **[Mottainai]** — Forward the marker *grammar*; do not rebuild kickoff's preference ladder/ledger for a workstation panel. Prefer deleting mechanisms over adding bridges.
- **[Sotto]** — Unset audience (= intermediate) leaves UX **byte-identical** to today's panel except an optional help affordance that defaults non-intrusive for intermediate.

---

## Overview

Operators embed cap-dev-pipe via TUI or CLI. This Control Central panel is the same
engine with a browser form, Preview gate, URL seeding, and **one fluency lens** over
instructions + field surface — without forking flows or coupling to kickoff's confirm ledger.

**Essential complexity kept:** one installer, one form→env→CLI channel, one Preview gate,
one audience lens, one instruction doc, one rank rule for field visibility.

**Operator CLI seam (dual-name, not Backend switch):** Primary `Backend:` stays
`control-central-panel`. The real operator CLI the panel invokes is dual-named in
Contract Projection with `python-cli-surface` harvest kinds (`console-script` ·
`command` · `subcommand` · `option` · `exit-class` as applicable) so panel FRs and
`startd8 capdevpipe …` share one typed contract. Living home: `src/startd8/cli_capdevpipe.py`
(+ console script `startd8` in `cli.py` / `pyproject.toml`). Vocabulary cite:
`~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8; routing key `#8 lifecycle/bootstrap`.

**Accidental complexity rejected:** second slicer service, experience-doc registry entry,
project-audience inheritance, per-tier field allowlist tables in the FR, generator gating
of Iteration 1b, hardcoded machine paths, dishonest form-dependent probes.

---

## Objectives

- O-1: An operator can complete a fresh `capdevpipe install` from a browser without memorizing CLI flags, using defaults filled from the same detection the TUI uses.
- O-2: Preview (dry-run) and Install are distinct actions; Install is gated on an explicit confirm after a successful Preview for the same parameter set.
- O-3: The panel never forks installer semantics — one engine (`CapDevPipeInstaller` via CLI).
- O-4: *(Deferred)* The panel can register in `tools/control-panels/panels.json` when the operator opts in.
- O-5: A deep link (`?target_root=…&profile=…`) opens the panel with those values applied and remaining fields filled by detect/sensible defaults.
- O-6: One audience control (`beginner|intermediate|advanced`, default intermediate) drives instruction slice + field surface; intermediate remains today’s UX.

---

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| safety | Browser-driven writes to arbitrary `--target-root` | Preview gate; refuse SDK-as-PROJECT_ROOT / source-as-target (installer already refuses); **FR-30** green go on next-logical wizard control; danger styling only on Expert non-sequence destructive actions (Repair / cleans / Danger fold) | high |
| quality | Second installer drift vs TUI/CLI | Scripts call `startd8 capdevpipe` only; golden tests compare argv construction | high |
| quality | Accidental complexity creep (second slicer, kickoff coupling, field allowlists) | v0.5 distillation; plan debt list; prefer delete over bridge | high |
| availability | Panel depends on SDK venv + `startd8` on PATH | Doctor probe + README; start script activates known SDK `.venv` when present | medium |
| safety | Env injection abuse via crafted POST | Keep argv fixed; only allowlisted keys; path validators; loopback-only CC bind | medium |

---

## Profile

Declared profile: **internal**

---

## Functional requirements

### Core install panel (shipped / in progress)

- **FR-1 — Generator extension (deferred).** When `panel_codegen` lands, `startd8 generate panel --kind capdevpipe-install` SHALL emit this panel's file tree deterministically ($0) as Control-Central-launchable. **Not on the Iteration 1b critical path** — the hand-built tree is authoritative until then. Touches: `panel_codegen`, `cli_generate_panel`. Verify: dry-run prints the file plan; apply writes `registry.json` + `start.sh` + `scripts/` + custom UI.
- **FR-2 — Workstation panel home.** The shipped panel SHALL live at a stable workstation path (SDK `control-panel/capdevpipe-install/`), not inside each install target. Touches: panel home layout. Verify: installing into `portal-v2` does not require a panel directory inside `portal-v2`.
- **FR-3 — Parameter form UI.** The panel SHALL render editable fields for every `startd8 capdevpipe install` input that an operator normally chooses, and POST only allowlisted keys under `{ env: … }` to `/run/<key>`. Touches: `panel.js` / `index.html`, allowedRunEnvKeys, install, opt-target-root, opt-source-path, opt-method, opt-embed-profile, opt-default-lang, opt-profile, opt-set-env. Verify: changing TARGET_ROOT in the form changes the env applied on Preview (visible in `/run` JSON `env_applied`).
- **FR-4 — Sensible defaults.** On panel load (and on Refresh-defaults), empty fields SHALL be filled from the same sources as the TUI/CLI. **Precedence:** (1) URL query (FR-14), (2) detect/fill for still-empty fields, (3) built-in constants. Detect SHALL NOT overwrite URL- or operator-set fields. Touches: `scripts/defaults.sh`, installer detect APIs, form merge, startd8, capdevpipe, opt-target-root. Verify: with prefs unset and standard sibling checkouts present, CONTEXTCORE_ROOT and PIPE_SDK_ROOT auto-fill when absent from the URL.
- **FR-5 — Single installer engine.** All mutating and preview actions SHALL invoke `startd8 capdevpipe …` with argv fixed in `registry.json`; operator choices travel only as env → script → CLI flags. Touches: `scripts/*.sh`, startd8, capdevpipe, install, verify, doctor. Verify: panel tree contains no second installer implementation; scripts invoke `capdevpipe` only.
- **FR-6 — Preview-before-Install.** Preview (`--dry-run`) and Install are separate; Install refuses unless Preview succeeded for the current parameter fingerprint (or an explicit dangerous override). Touches: preview/install scripts, UI gate, install, opt-dry-run, exit-capdevpipe. Verify: Install with no Preview returns non-zero with a clear refuse reason.
- **FR-7 — Existing-embed modes.** When the target already has `.cap-dev-pipe/`, the UI SHALL offer re-run modes aligned with CLI `--rerun-mode`. Touches: RERUN_MODE field, actions group, install, opt-rerun-mode. Verify: selecting `doctor` runs doctor-only and writes no embed files.
- **FR-8 — Language profiles.** The UI SHALL let the operator add zero or more `lang[:plan[:reqs]]` profiles via `PROFILE_SPECS` (Expert). Soft-fill from `capdevpipe defaults` doc candidates when blank (not a separate Auto-detect control this sprint). *(HTH soft-label: TUI-parity Auto-detect CTA deferred — see CIP-S backlog.)* Touches: PROFILE_SPECS. Verify: for a target with plan+reqs under `docs/`, defaults soft-fill yields a usable profile string when the field was empty.
- **FR-9 — Lovable / pilot preset (soft, deferred).** The UI MAY offer a named preset for the lovable-target / portal-v2 pilot. Not required for Iteration 1b. Touches: preset dropdown. Verify: selecting the preset populates fields; it never invents paths that fail source validation.
- **FR-10 — Status probes (honest).** The panel SHALL probe at least: (a) `startd8` resolvable, (b) source looks like cap-dev-pipe (`SOURCE_MARKERS`). Probes that need form `TARGET_ROOT`/`SOURCE_PATH` SHALL NOT claim failure from empty process env unless the panel first persists form env for probes (optional later: `state/form.env`) — until then, hide or mark those probes as “needs Preview/Detect.” Touches: `registry.status.custom`, probe scripts, startd8. Verify: with empty process env and a filled form, startd8/source probes still reflect truth; target probe does not falsely red-fail as “broken install.”
- **FR-11 — Optional registry registration (deferred).** Opt-in registration into `tools/control-panels/panels.json`; never auto-write without consent. Touches: register helper / runbook. Verify: `--no-register` / skip writes zero bytes outside the panel home.
- **FR-12 — Idempotent regeneration (deferred).** When generator exists, re-running SHALL preserve unmarked operator edits (REQ-SDK-P3). Touches: generation markers. Verify: unmarked `panel.js` survives regen.
- **FR-13 — Output surfacing (Preview/Install summary + raw).** After Preview or Install, the panel SHALL open **Console** and show `/run` stdout/stderr. After a **successful Preview or successful Install**, the Console apex (glance + first paint of the fold body) SHALL present an **operator summary derived from that run’s stdout/stderr** (same bytes as the console — no second installer API), including at least: (a) target path, method, and embed profile from the run header; (b) counts by action kind present in the log (`mkdir`, `symlink`, `copy`, `write`, `gitignore` / equivalent); (c) the run close / outcome line when present — Preview: e.g. `N action(s) planned; nothing written.`; Install: that actions were **applied/written** (or the installer’s success close line) plus the embed path `.cap-dev-pipe/` under the target; (d) installer warnings from stderr that affect the decision (e.g. uncommitted changes in the target git repo); (e) **already-installed notice** when the target already has an embed — see below. Preview and Install summaries SHALL NOT reuse each other’s outcome wording (no “nothing written” after a successful Install). The full raw stdout/stderr SHALL remain reachable in the same Console fold (scroll or “Show raw” for Novice/Operator; Expert may default to raw). Touches: `panel.js` / `run_summary.js` Console render, optional thin stdout parser (client-side); install, opt-dry-run for the pre-list notice. Verify: Preview against a typical full-profile target shows counts + “nothing written”; Preview against an **already-installed** target shows “already installed” / existing-embed at apex **before** action counts; after Install on the same fingerprint, summary shows applied counts / written outcome and target `.cap-dev-pipe` without requiring every symlink path; stderr warnings still surface; toggling raw shows the full log.
- **FR-13a — Preview on already-installed target.** When Preview (`--dry-run`) runs against a `TARGET_ROOT` where `.cap-dev-pipe/` already exists (`detect_existing`), the CLI dry-run SHALL print an **existing install / already installed** line **immediately after the dry-run header and before any planned-action bullets**, even when `--rerun-mode` is unset. The panel Console summary SHALL surface the same fact at apex (parsed from that stdout and/or from `defaults` `embed_exists`). This SHALL NOT mutate disk and SHALL NOT skip the dry-run action list. Touches: install, opt-dry-run, panel summary. Verify: install once, then Preview without `RERUN_MODE` → stdout contains “existing install” (or equivalent) before the first `•` action; Console summary glance states already installed.
- **FR-14 — URL query seeding.** On first paint, parse the page URL query into form fields (aliases in §Contract projection). Unknown keys ignored. When `TARGET_ROOT` is set after URL apply, auto-run detect for remaining empty fields unless `auto_defaults=0`. Touches: `url_params.js`, `index.html`. Verify: `?target_root=/tmp/demo&method=copy&profile=python` sets those fields; detect fills blanks without clearing `method=copy`.
- **FR-18 — Post-install delivery dry-run CTA.** After a **successful Install**, or when the form’s `TARGET_ROOT` already has an embed (`embed_exists` / `.cap-dev-pipe/` present), the panel SHALL expose a **Dry-run delivery** action (action-bar button, unmarked / always visible when eligible) that is an alternative to running the embedded shell dry-run by hand. The action SHALL invoke the target’s embedded `run-cap-delivery.sh` (or equivalent wrapper path under `.cap-dev-pipe/`) with **`--dry-run` always set**, plus `--plan`, `--requirements`, `--project`, `--name`, and `--project-root` derived from allowlisted form env (`PLAN_PATH`, `REQUIREMENTS_PATH`, `PROJECT_NAME` / target basename, `TARGET_ROOT`). It SHALL refuse with a clear message when embed is missing or plan/requirements paths are blank or not files, and SHALL open/focus the Delivery dry-run fields when paths are missing (not a registry-restart message). `PLAN_PATH` / `REQUIREMENTS_PATH` SHALL persist in panel localStorage (URL wins). Delivery handle is derived (FR-29) — not persisted as freeform `RUN_NAME`. It SHALL NOT run a mutating (non-dry-run) delivery from this panel. Console SHALL open and surface stdout/stderr (FR-13 raw path; summary MAY be best-effort). Touches: `scripts/pipeline_dry_run.sh`, `registry.json`, action bar, optional plan/reqs fields, `url_params.js` aliases, `panel.js`. Verify: after Install on a target with plan+reqs filled, Dry-run delivery exits 0; with blank plan path, UI refuses client-side, opens Delivery fold, and does not claim a registry restart; button hidden or disabled before first successful Install when embed absent.
- **FR-19 — Persist Project folder.** When the operator sets a non-empty **Project folder** (`TARGET_ROOT`), the panel SHALL persist that absolute path in panel `localStorage` key `capdevpipe.install.target_root` and restore it on later loads when the URL does not supply `TARGET_ROOT`. Resolution for `TARGET_ROOT` on boot: (1) URL query (FR-14) → (2) panel localStorage → (3) empty. Changing or clearing the field SHALL update or remove the stored value. SHALL NOT write kickoff prefs or project ledgers. Touches: `panel.js`. Verify: set Project folder, reload without `?t=`, field restores; `?t=/other` wins over stored path; clearing the field clears storage.
- **FR-20 — Installed action-bar state.** When `TARGET_ROOT` has a successful embed (`embed_exists` / `.cap-dev-pipe/` present, including immediately after a successful Install), the action bar SHALL **hide Preview and Install** and SHALL show in Install’s place a non-interactive **Installed** label with green text and a green border (not a button). Detection SHALL use a **fast** present/absent check of `TARGET_ROOT/.cap-dev-pipe` (not blocked on cold `capdevpipe defaults`) and MAY be corroborated by defaults `embed_exists`. Dry-run delivery (FR-18) and Run workflow (FR-21) remain available when installed. When the operator switches to a Project folder without an embed, Preview and Install SHALL return and the Installed label SHALL hide. Touches: `index.html`, `panel.js`, `deck.css`, `scripts/probe_embed.sh` / `check-embed` action. Verify: portal-v2 (already installed) → Install rail `is-done` / not current before defaults finish; empty/new target → Install current. *(HTH soft-label: dedicated Installed badge DOM superseded by FR-28 rail done-state.)*
- **FR-21 — Run delivery (gated on delivery dry-run).** When the target is installed, the panel SHALL expose a **Run delivery · Stages 0–4** action that invokes embedded `run-cap-delivery.sh` **without** `--dry-run`, using the same plan/requirements/project/name/project-root env as FR-18. Run delivery SHALL refuse unless a successful Dry-run delivery has written a fingerprint token under `$PANEL_HOME/state/last-delivery-dry-run.json` matching the current delivery fingerprint (`TARGET_ROOT`, `PLAN_PATH`, `REQUIREMENTS_PATH`, `PROJECT_ROOT`, `PROJECT_NAME`, `RUN_NAME`, `RUN_POLISH`). Changing those fields invalidates the gate until Dry-run delivery succeeds again. Optional dangerous override `SKIP_DELIVERY_GATE=1` MAY exist for Expert only (same audience pattern as Preview gate). Touches: `scripts/pipeline_run.sh`, `pipeline_dry_run.sh` token write, `check_delivery_gate.sh`, action bar, `registry.json`. Verify: Run without prior dry-run → refuse; successful dry-run then Run with same paths → proceeds; change PLAN_PATH then Run → refuse until dry-run again.
- **FR-22 — Button-driven pipeline stages.** When the target is installed, the panel SHALL expose **clearly labeled** action-bar (or pipeline-fold) buttons for each post-install stage the operator normally runs from `.cap-dev-pipe/`, without requiring a terminal. Minimum set:
  - **Dry-run install (Preview)** / **Run install** — existing Preview/Install (labels MAY keep “Preview”/“Install” as secondary text but primary label SHALL include dry-run vs run + install).
  - **Dry-run delivery · Stages 0–4** / **Run delivery · Stages 0–4** — FR-18 / FR-21 (`run-cap-delivery.sh`).
  - **Dry-run plan ingestion · Stage 5** / **Run plan ingestion · Stage 5** — embedded `run-plan-ingestion.sh` with `--provenance` (and `--force-prime` when the Force-prime option is set). **When FR-26 applies (ingestion already complete for the current run), these two Stage-5 buttons SHALL be hidden** (ingestion step done on the wizard rail).
  - **List prime tasks · Stage 6** / **Dry-run prime · Stage 6** / **Run prime · Stage 6** — embedded `run-prime-contractor.sh` with `--list`, `--dry-run`, and mutating run (`--all` by default) respectively.
  Each button label SHALL name the **workflow/script role** and whether it is **dry-run**, **list**, or **run**. Artisan remains out of scope (ON HOLD). Touches: `index.html`, `panel.js`, `deck.css`, `registry.json`, stage scripts. Verify: installed portal-v2 (not yet ingested) shows Stage-5 dry-run/run; after FR-26 completion those Stage-5 buttons hide and Stage-6 controls remain.
- **FR-23 — Pipeline field defaults.** When Project folder / project name are known and the corresponding field is empty (and not URL-forced), the panel SHALL default:
  - `PROJECT_NAME` → basename of `TARGET_ROOT` when blank;
  - `PROVENANCE_PATH` → `${TARGET_ROOT}/.cap-dev-pipe/pipeline-output/${derived_handle}/run-provenance.json` when blank (scripts MAY resolve this even if the form field is hidden).
  **Delivery handle** (`RUN_NAME` env) is **not** a freeform defaultable field — see **FR-29**. Defaults SHALL NOT overwrite non-empty operator or URL values for plan/reqs/provenance. `PLAN_PATH` / `REQUIREMENTS_PATH` / `PROVENANCE_PATH` (when shown) SHALL persist in localStorage (URL wins). Touches: `panel.js`, `url_params.js`, `_env.sh` resolvers. Verify: portal-v2 Project folder alone yields handle `portal-v2-preview` with no Run-name input.
- **FR-24 — Per-stage dry-run gates (ingestion + prime).** **Run plan ingestion** SHALL refuse unless a matching Dry-run plan ingestion token exists (`state/last-ingestion-dry-run.json`) for the current fingerprint (`TARGET_ROOT`, `PROVENANCE_PATH`/`RUN_NAME`, `FORCE_PRIME`). **Run prime** SHALL refuse unless a matching Dry-run prime token exists (`state/last-prime-dry-run.json`) for the current fingerprint (`TARGET_ROOT`, provenance, prime mode). List prime tasks is ungated (read-only). Expert MAY set `SKIP_INGESTION_GATE=1` / `SKIP_PRIME_GATE=1`. Touches: ingestion/prime scripts + check scripts + panel enablement. Verify: Run plan ingestion without dry-run → refuse; dry-run then run with same provenance → proceeds.
- **FR-25 — Concurrent delivery lock + console wait copy.** Pipeline stage scripts that mutate or long-run SHALL share the portable delivery lock (FR-21 era) so stacked clicks refuse clearly. While `/run` is in flight, Console SHALL show a waiting line naming the action key. **Stdout remains buffered until exit** (Control Central has no live stream this sprint). When FR-32 applies to the action, Console SHALL **also** show high-level progress from durable artifacts (polling), not only the static wait line. Touches: `_env.sh` lock, `panel.js`, FR-32. Verify: second delivery click while first holds lock → refuse; Console shows waiting text immediately on click; during prime-run, progress updates appear before `/run` returns.
- **FR-26 — Ingested action-bar state (mirror Install / FR-20).** After a **successful Run plan ingestion · Stage 5** for the current run identity (`TARGET_ROOT` + resolved `RUN_NAME` / `PROVENANCE_PATH`), or when the panel detects that plan-ingestion has **already completed** for that run, the action bar SHALL **hide Dry-run plan ingestion · Stage 5 and Run plan ingestion · Stage 5** and SHALL advance the wizard past Stage 5 (ingestion rail `is-done`; Stage-5 controls not current). *(HTH soft-label: dedicated Ingested badge DOM superseded by FR-28 rail done-state; same hide-Stage-5 outcome.)* Detection SHALL be a **fast** artifact check under the run’s pipeline-output (normative: presence of plan-ingestion success artifacts for that provenance — at minimum `prime-context-seed.json` or the ingestion output directory/files the embed already writes; exact path MAY be resolved via provenance / `pipeline-output/${RUN_NAME}/`). Detection SHALL NOT be blocked on cold `capdevpipe defaults`. Immediately after a successful Stage-5 Run from the panel, the UI SHALL enter this state without requiring a full page reload. Stage-6 controls (List / Dry-run / Run prime) SHALL remain available when ingested. Changing to a Project folder / run name without ingestion artifacts SHALL restore Stage-5 dry-run/run and hide **Ingested**. **Re-ingestion UI** (and **reinstall UI** beyond FR-20’s hide) are **deferred to end of this sprint** — this FR does not add a “Re-run ingestion” or “Reinstall” control. Touches: `index.html`, `panel.js`, `deck.css`, probe script (e.g. `probe_ingestion.sh` / `check-ingestion`), action bar. Verify: after successful Stage-5 on portal-v2-preview → Stage-5 buttons gone, green **Ingested** visible, Stage-6 buttons still present; fresh run name without seed → Stage-5 buttons return, **Ingested** hidden.
- **FR-27 — CLI twin (cwd + command).** The panel SHALL show an **equivalent terminal invocation** an operator can copy, consisting of:
  1. **Working directory** — absolute path where the command SHOULD be run (embed scripts: `${TARGET_ROOT}/.cap-dev-pipe`; install: any cwd with `startd8` on PATH / documented equivalently);
  2. **Command line** — shell argv equivalent to the chosen action, filled from **current form values** (FR-23 defaults when empty).
  **FR-28 narrows visibility:** only the **next logical** action’s twin is shown (not one under every button). The twin SHALL update when form fields that affect it change. Status-only badges do not get a twin. Advisory only — caption MUST NOT execute; the button remains the panel executor. Touches: `panel.js`, `deck.css`. Verify: on an ingested portal-v2 run, the only visible CLI twin is for the Prime step’s next logical action (Dry-run prime if gate cold, else Run prime).
- **FR-28 — Completion wizard (sequential apex).** The action apex SHALL be a **left-to-right completion wizard** over four ordered steps (SDK wizard step-state *pattern*: linear steps, one current, completed locked — adapted for Control Central; not a generated `backend_codegen` flow router):
  1. **Install** — Run install primary; Dry-run install nested **under** it, slightly smaller.
  2. **Delivery · Stages 0–4** — Run delivery primary; Dry-run delivery nested smaller underneath.
  3. **Plan ingestion · Stage 5** — Run plan ingestion primary; Dry-run nested smaller underneath.
  4. **Prime · Stage 6** — Run prime primary; Dry-run prime nested smaller underneath; **List prime tasks** is a **subcommand** of Prime (tertiary control under the Prime step — not a peer stage in the rail).
  Step order is completion / use order. The wizard SHALL highlight the **current** step (first incomplete). Completed steps SHALL show a done state (Install / Delivery / Ingestion via probes → rail `is-done`; delivery complete = fast artifact probe for real export under `pipeline-output/${derived_handle}/`). *(HTH soft-label: Prime has no completion probe this sprint — stays current after ingestion; see CIP-S-4.)* Completed steps SHALL NOT re-expose their Run/Dry-run controls this sprint (same deferral as FR-20 / FR-26).   Only the **current** step’s action cluster is interactive. **Only one CLI twin** (FR-27) for the **next logical command** on the current step: prefer Dry-run when the mutating gate for that step is not ready; otherwise the Run command. Touches: `index.html`, `panel.js`, `deck.css`, `probe_delivery.sh` / check-delivery. Verify: fresh target → Install current with Dry-run under Run install + CLI for next logical; after install+delivery+ingestion on portal-v2 → Prime current, List nested under Prime, Stage-5 not clickable, single CLI twin for Dry-run or Run prime.
- **FR-29 — Derived delivery handle (Intent–Delivery naming extension).** The panel SHALL **not** expose Run name as an editable input. Delivery identity SHALL be a **derived readable handle** `${PROJECT_NAME|-basename(TARGET_ROOT)}-preview`, following the Deterministic Intent–Delivery Language principle that human-mutable titles are not identity (canonical/machine identity vs readable handle — see ContextCore `docs/design/DETERMINISTIC_INTENT_DELIVERY_LANGUAGE_OVERVIEW.md` §How the naming works). The UI SHALL show the derived handle as a read-only display. Scripts SHALL **always** resolve `RUN_NAME` / delivery directory name from that derivation (ignore freeform `RUN_NAME` env / legacy localStorage / URL `?name=`). Expert MAY still override **provenance file location** via `PROVENANCE_PATH` when pointing at a historical path. Touches: `index.html`, `panel.js`, `deck.css`, `_env.sh`, FR-23. Verify: portal-v2 → display `portal-v2-preview`; typing cannot create `ortal-…`; delivery/prime write under `pipeline-output/portal-v2-preview/`.
- **FR-30 — Next-logical go affordance (green = go).** In the completion wizard (FR-28), the **next logical** control for the current step SHALL use a distinct **green go** visual treatment (border + fill using the panel success/ok token). Exactly one wizard control on the current step SHALL carry that treatment at a time, matching the same preference as the CLI twin (FR-27/28): Dry-run when the mutating gate for that step is not ready; otherwise the gated Run control. Wizard **Run** buttons SHALL **not** use danger/red styling — red means stop / destructive-out-of-sequence, which is an anti-pattern for the prescribed next action. Danger/red styling remains appropriate for Expert **non-sequence** destructive actions (e.g. Repair, Remove orphan runs, Clean prime state, Danger-fold gate overrides). Touches: `index.html`, `panel.js`, `deck.css`. Verify: after Dry-run prime succeeds, **Run prime · 6** is green and not red; before that gate, **Dry-run prime · 6** is green.
- **FR-31 — Operator failure analysis (what / why / fix).** After any panel action that **fails or is refused** (Install Preview/Install, delivery, plan ingestion, prime, Health cleans/repair), the Console apex SHALL present an **operator-oriented failure analysis** derived from that run’s stdout/stderr/error (same bytes as Console raw — no second installer API, no LLM call from the panel), with three labeled parts:
  1. **What happened** — plain-language outcome (e.g. “Prime · 6 could not call the Anthropic API”).
  2. **Why** — the classified cause in operator terms (e.g. “Account credit balance is too low”, “API key missing in the panel process”, “Dry-run gate fingerprint mismatch”, “Unknown action — panel registry stale”).
  3. **What to do** — concrete next steps so the failure **stops recurring** (e.g. fund Anthropic Plans & Billing, then re-run **only** Prime · 6; restart via `./start.sh` / Doppler for keys; re-run Dry-run then Run for gate mismatches). Guidance SHALL NOT tell the operator to restart Delivery 0–4 when provenance/seed are intact and the failure is provider/billing/key.
  Classification SHALL cover at least: **billing/credits**, **missing/invalid API key / agent resolve**, **rate limit / overload**, **dry-run gate refuse**, **missing provenance / plan / requirements**, **unknown action (stale registry)**, and a **fallback** that surfaces the first refuse/error line plus “Show raw”. Patterns SHOULD stay aligned with SDK postmortem/SA `provider_error` signals (`is_provider_config_failure` / operational actions) — cite, do not import SA into the browser. Successful runs MAY keep a short next-step line (FR-13 / FR-28). Raw log remains available via Show raw. Touches: `result_analysis.js`, `panel.js`, `deck.css`, tests. Verify: paste Anthropic “credit balance is too low” into a failed prime-run summary → what/why/fix name billing and tell operator to add credits then retry Prime only; missing `ANTHROPIC_API_KEY` → fix names Doppler/`./start.sh`; gate refuse → Dry-run then Run.
- **FR-32 — In-flight high-level progress (prime first).** For panel actions whose underlying workflow already emits a **durable progress artifact**, the panel SHALL show **high-level step progress** in Console while `/run/<key>` is in flight (and MAY keep a final snapshot until the next action clears it).
  **Prime · Stage 6 (this sprint):** While `prime-run` (and optionally `prime-dry-run` when it writes queue state) is in flight, the panel SHALL poll a read-only probe of `{TARGET_ROOT}/.prime_contractor_state.json` (the Prime `FeatureQueue` save file — cite `queue.save_state` / `get_progress`; do not invent a second progress bus). The UI SHALL show at least:
  1. **Overall** — `complete/total` and progress percent (same semantics as `FeatureQueue.get_progress`).
  2. **Current feature** — id + short name + status when any feature is `developing` | `generated` | `integrating` | `checkpoint` (else the next `pending` when the queue is loaded).
  3. **High-level step rail** (ordered, one current) mapped from queue reality, minimum set: **Load** → **Develop** → **Integrate** → **Advance** → **Wrap-up** (Wrap-up = post-run / idle after last feature terminal; Advance = feature completed and moving to next). Status→step mapping SHALL treat `developing`/`generated` as Develop, `integrating`/`checkpoint` as Integrate, all-terminal as Wrap-up, empty/missing file as Load.
  Polling interval SHALL be ~1–3s; probe SHALL be $0 / fail-soft (missing file → “waiting for queue…”). Progress MUST NOT require Control Central stdout streaming or ContextCore `percent_complete` (startd8 does not emit live CC progress deltas). Extending the same pattern to delivery / plan-ingestion is **deferred** until those stages expose an equally durable mid-run artifact. Touches: `scripts/probe_prime_progress.sh`, `progress.js`, `panel.js`, `deck.css`, `registry.json`, optional `FeatureObserver` flush hardening. Verify: during a multi-feature prime-run, Console progress updates `n/N` and current `PI-*` before `/run/prime-run` returns; with no state file yet, UI shows Load / waiting; after completion, FR-31/success summary still works.
- **FR-33 — Page title + always-visible project activity.** The panel SHALL keep the browser tab title and an **always-visible activity strip** (outside collapsed Console) faithful to the selected project’s durable status:
  1. **`document.title`** SHALL be operator-intuitive: when Project folder is empty → a pick-project title (e.g. `Add pipeline · pick a project`); when set → include the project basename; when prime queue state exists → include `complete/total` and a clear activity word (`working` when any feature is developing/integrating/…, else `paused`/`done`/`failed` as appropriate) plus current `PI-*` when working. SHALL NOT leave a static generic title that ignores live queue state.
  2. **Activity strip** SHALL sit in the main chrome (near Project folder / wizard — not only inside the Console fold) and show the same FR-32 glance + counts (and MAY reuse the step rail). It SHALL update via idle polling (~2–3s) whenever `TARGET_ROOT` is set, **including when no `/run` is in flight in this tab** (so a CLI-started Stage 6 is still visible). Missing state → quiet “no prime queue yet” (or hide strip), not a fake “Ready” that implies the project is idle when it is not.
  3. Header **task line** MAY mirror a short form of the same glance. Clearing a finished Console run SHALL NOT blank the activity strip while queue state still exists.
  Touches: `index.html`, `panel.js`, `progress.js`, `deck.css`, `progress.test.js`. Verify: with portal-v2 mid-prime (CLI or UI), open/reload the panel → tab title names the project and shows working `n/N` + current feature without expanding Console; when all features complete, title/strip say done (or complete counts) without requiring a new `/run`.
- **FR-34 — Per-feature completion progress.** The activity UI (FR-33 strip and FR-32 Console progress) SHALL make each feature completion visible, not only an aggregate percent:
  1. The prime progress probe SHALL include an **ordered** `features` list (`id`, `status`, short `name`) from `.prime_contractor_state.json` (same file as FR-32 — no second bus).
  2. The UI SHALL render a **feature checklist** (chips/row) for that list: terminal `complete` marked done, active (`developing`/`generated`/`integrating`/`checkpoint`) marked current, `failed`/`blocked` marked bad, else pending. As each feature reaches `complete`, the corresponding chip SHALL flip to done on the next poll (~2–3s) so `1/21` → `2/21` → … is visible as discrete steps.
  3. When `complete` increases between polls, the UI SHALL briefly surface the **just-completed** feature id (e.g. “Completed PI-003”) and MAY pulse that chip; the progress bar width SHALL track `complete/total`.
  Touches: `scripts/probe_prime_progress.sh`, `progress.js`, `panel.js`, `deck.css`, `progress.test.js`. Verify: mid-prime with 7/21 complete and `PI-004a` integrating → checklist shows seven done chips + current `PI-004a`; after that feature completes and state saves, next poll shows 8/21 and `PI-004a` done without a new `/run`.

### Audience lens (Iteration 1b — distilled)

- **FR-15 — Audience lens.** The panel SHALL expose one fluency control using kickoff tokens `beginner | intermediate | advanced` (UI may label Novice / Operator / Expert). **Default when unset: `intermediate`** (Sotto: today’s UX). Resolution ladder is **only** (1) URL `?audience=` / non-normative alias `?expertise=` → (2) panel `localStorage` key `capdevpipe.install.audience` → (3) `intermediate`. Invalid tokens degrade to `intermediate` with a console warning. **SHALL NOT** call `resolve_audience_preference`, read kickoff `build-preferences.yaml`, or write kickoff ledgers. The same audience value SHALL (a) select the disclosure slice of `OPERATOR_INSTRUCTIONS.md` per `disclosure_tier` mapping (beginner→expanded/PLAIN, intermediate→light/body−PLAIN, advanced→compact/TL;DR), and (b) show/hide form fields **and action-bar controls** via a single rank rule: elements with `data-min-audience` are visible iff `rank(current) >= rank(min)` where `beginner < intermediate < advanced`; unmarked elements are always visible. Normative annotations: Verify and Doctor unmarked; Repair `advanced`; Preview/Install/audience control/help unmarked. Hidden fields SHALL retain values in the DOM, but env keys bound to advanced (`SKIP_PREVIEW_GATE`, `TRUST_SOURCE`) **SHALL NOT** be included in Preview/Install POST `env` unless `rank(current) >= advanced`, even if URL-seeded; the UI MAY show a non-blocking warning when suppressed. When `audience=beginner`, help SHALL default expanded showing the PLAIN slice; the audience control SHALL remain visible at all ranks. Touches: `index.html`, `url_params.js`, `instructions.js`, CSS. Verify: unset → intermediate surface + light instructions; `?audience=beginner` expands PLAIN help and hides Repair without changing Preview→Install order; `?skip_preview_gate=1&audience=intermediate` does not send `SKIP_PREVIEW_GATE` on Install; elevating to advanced reveals URL-filled advanced fields and allows dangerous flags.
- **FR-16 — Packaged operator instructions.** The panel SHALL ship one markdown file `OPERATOR_INSTRUCTIONS.md` with kickoff content-contract markers (`<!-- BANNER -->`, `<!-- TL;DR -->`, `<!-- PLAIN -->`). Display SHALL fetch that static file from PANEL_HOME and slice client-side with the same marker grammar (comment citing `writes.py` as grammar owner). **Normative slice algorithm** (mirror `load_experience_doc` in `writes.py`): optional banner section is tier-independent; `compact` extracts TL;DR else degrades to light; `expanded` extracts PLAIN else degrades to light; `light` strips the PLAIN region whole then drops remaining marker lines. **$0, no LLM. SHALL NOT** register into `_EXPERIENCE_DOCS` or import private `_extract_slice`. Touches: `OPERATOR_INSTRUCTIONS.md`, help pane, `instructions.js`, fixtures. Verify: beginner view contains PLAIN guidance; advanced view is TL;DR and excludes PLAIN; intermediate omits PLAIN; fixture tests match degrade cases (missing TL;DR / missing PLAIN).

---

## Non-goals

- Replacing or deleting `startd8 tui` PROJECT SETUP / `mixin_capdevpipe`.
- Teaching Control Central's bundled `index.html` generic env forms.
- Emitting this panel inside every `startd8 generate backend` app.
- Implementing Supabase / Lovable pack publish from this panel.
- Running a **mutating** delivery / plan-ingestion / prime step without its matching Dry-run gate (FR-21 / FR-24). **Allowed:** dry-run buttons always (except when FR-26 hides Stage-5); gated Run buttons after matching dry-run.
- Driving **Artisan** contractor from this panel (ON HOLD).
- Auto-running the full chain (delivery→ingestion→prime) as one button in v0.6 (may come later).
- **Re-ingestion / force re-run of plan ingestion from the panel** after FR-26 success — deferred to **end of this sprint**.
- **Reinstall controls** that re-expose Preview/Install after FR-20 Installed — deferred to **end of this sprint** (Installed badge remains hide-only).
- Windows-first UX polish beyond respecting installer method defaults.
- **Stakeholder-panel personas, facilitation, ask-all, or role-kit CLI** as the fluency mechanism.
- Writing kickoff `confirmed.yaml` / calling `apply_audience_defaults` / `resolve_audience_preference` from this panel.
- Registering `OPERATOR_INSTRUCTIONS.md` into concierge `_EXPERIENCE_DOCS`.
- A second Python experience-doc loader or private-API import bridge for help text.
- Inheriting kickoff project/global audience prefs into the install panel.
- LLM-authored operator help.
- Per-audience forked panels or forked Preview→Install flows.
- Enumerated per-tier field allowlist tables as the normative surface contract (use the rank rule).
- A second installer report channel or JSON “preview summary” API — summary is derived client-side from the same dry-run stdout/stderr already returned by `/run` (FR-13).

---

## Owned fields

Only humans enter (generators may suggest, never silently invent):
- Final confirmation to Install after Preview
- Any override of auto-detected CONTEXTCORE_ROOT / SDK_ROOT when detection is blank
- Opt-in `panels.json` registration
- Explicit dangerous override of the Preview gate (if exposed)
- Explicit plan / requirements paths for Dry-run delivery when not supplied by URL / profile specs

---

## Reference audit (Genchi)

| Spec name (v0.4) | Code reality | v0.5 disposition |
|------------------|--------------|------------------|
| `resolve_audience` | **Does not exist**; real API is `resolve_audience_preference` | Do not call from panel |
| `load_experience_doc(path)` | Closed-vocabulary `key` → `_EXPERIENCE_DOCS` only (`intro`, `workbook`) | Do not register install doc; static fetch |
| `writes._extract_slice` | Private helper | Cite grammar; JS twin OK; no import |
| `disclosure_tier()` | Exists; maps audience → expanded/light/compact | Cite mapping; implement in JS as data |
| `KickoffAudience` | Exists | Tokens only; no Python enum in browser |
| `PORTAL_V2` hardcode | Accidental machine path in `index.html` | Delete / replace with query-only demo |
| Form-aware status probes | Probes lack form env | Soften FR-10; honest probes first |

---

## Accidental complexity debt (opportunistic elimination)

Delete or simplify while implementing Iteration 1b — prefer **removing** over wrapping:

| Debt | Where | Essential fix |
|------|-------|---------------|
| ~780-line HTML+CSS+JS monolith | `index.html` | Split `panel.css` + `panel.js` / `instructions.js` |
| Hardcoded `PORTAL_V2` deep link | `index.html` | `?audience=beginner` demo or omit path |
| Dishonest target/embed probes | `probe_target.sh` + CC status | Hide until form.env, or drop from status until then |
| Alias / docs drift | README vs `url_params.js` vs this doc | One alias table owner: this requirements §; code cites it |
| Debug `console.log` of `location.search` | `index.html` | Remove or gate behind `?debug=1` |
| Duplicate ALIASES entries | `url_params.js` | Dedupe |
| Temptation to add `scripts/instructions.py` | plan F-111 | **Cancel** — JS slicer only |

---

## Kickoff reuse map (normative — cite, don’t couple)

| Kickoff element | Path / API | Install-panel reuse |
|-----------------|------------|---------------------|
| Audience tokens | `KickoffAudience` / kickoff docs | Same three strings; FR-15 |
| `disclosure_tier` mapping | `audience.py` | Cite; reimplement as JS data for FR-15 |
| Preference ladder / ledger | `resolve_audience_preference`, `apply_audience_defaults` | **Do not call** |
| Marker grammar | `writes.py` constants + content contract | Cite; JS slicer for FR-16 |
| `load_experience_doc` / `_EXPERIENCE_DOCS` | `writes.py` | **Do not extend** |
| Stakeholder personas / facilitation | `stakeholder_panel/` | **Out of scope** |

---

## Contract projection

- **Backend:** control-central-panel
- **Vocabulary home (cite):** `tools/control-panels/REQUIREMENTS.md`; CC README
- **CLI contract home:** `src/startd8/cli_capdevpipe.py`; `CapDevPipeInstaller`
- **Audience / disclosure vocabulary home (cite only):** `src/startd8/concierge/audience.py`; `src/startd8/concierge/writes.py` marker constants; kickoff PERSONA_EXPERIENCES + KICKOFF_CONTENT_CONTRACT docs — quoted tables below are **non-normative snapshots**

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| registry.json | Structure | panelId, panelPort, actions, status, allowedRunEnvKeys | CC schema |
| allowedRunEnvKeys | Structure | TARGET_ROOT … SKIP_PREVIEW_GATE, PLAN_PATH, REQUIREMENTS_PATH, RUN_NAME | env-only channel; audience is UI-only |
| scripts/*.sh | Structure | preview/install/verify/doctor/repair/defaults | fixed argv |
| panel.js / Console | Structure | post-Preview / post-Install summary + raw | FR-13 |
| OPERATOR_INSTRUCTIONS.md | Words | BANNER / TL;DR / PLAIN | FR-16 single source |
| URL query aliases | Structure | table below | FR-14 / FR-15 |
| panels.json row | Structure | id, port, path, tier:2, class:ops | deferred opt-in |

### Operator CLI seam (dual — `python-cli-surface` harvest kinds; primary Backend unchanged)

Cite vocabulary: `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8 `python-cli-surface`.
Living Typer group: `cli.py` `app.add_typer(capdevpipe_app, name="capdevpipe")` →
`cli_capdevpipe.py`. Phase 4.5 key `#8 lifecycle/bootstrap` (REQ-09 / indirect reuse).
Do **not** invent `defaults` here — panel `scripts/defaults.sh` calls it, but Genchi:
no `@capdevpipe_app.command("defaults")` on current `cli_capdevpipe.py`.

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| startd8 | console-script | structure | `pyproject.toml` `startd8 = "startd8.cli:app"` |
| capdevpipe | command | structure | Typer group `capdevpipe_app` |
| install | subcommand | structure | `startd8 capdevpipe install` — panel Preview/Install |
| verify | subcommand | structure | `startd8 capdevpipe verify` — Health |
| doctor | subcommand | structure | `startd8 capdevpipe doctor` — Health |
| opt-target-root | option | structure | `--target-root` / `-t` |
| opt-source-path | option | structure | `--source-path` / `-s` |
| opt-method | option | structure | `--method` / `-m` |
| opt-embed-profile | option | structure | `--embed-profile` |
| opt-default-lang | option | structure | `--default-lang` |
| opt-profile | option | structure | repeatable `--profile` |
| opt-set-env | option | structure | repeatable `--set-env KEY=VALUE` |
| opt-rerun-mode | option | structure | `--rerun-mode` |
| opt-trust-source | option | structure | `--trust-source` |
| opt-dry-run | option | structure | `--dry-run` (Preview) |
| exit-capdevpipe | exit-class | structure | `_EXIT_OK=0` / `_EXIT_ERROR=1` via `typer.Exit` (fail-loud) |

### Parameter → CLI mapping (normative)

| UI / env key | CLI | Default when blank |
|--------------|-----|--------------------|
| TARGET_ROOT | `--target-root` | URL / operator entry (required before Preview) |
| SOURCE_PATH | `--source-path` | `~/Documents/dev/cap-dev-pipe` or ConfigManager `capdevpipe.source_path` |
| METHOD | `--method` | `symlink` (Windows → `copy`) |
| EMBED_PROFILE | `--embed-profile` | `full` |
| DEFAULT_LANG | `--default-lang` | `python` |
| PROFILE_SPECS | repeated `--profile` | empty, or auto-detect list |
| CONTEXTCORE_ROOT | `--set-env CONTEXTCORE_ROOT=` | installer detect |
| PIPE_SDK_ROOT | `--set-env SDK_ROOT=` | installer detect |
| PROJECT_ROOT | `--set-env PROJECT_ROOT=` | same as TARGET_ROOT |
| PROJECT_NAME | `--set-env PROJECT_NAME=` | basename(TARGET_ROOT) |
| RERUN_MODE | `--rerun-mode` | unset on fresh |
| TRUST_SOURCE | `--trust-source` | unset/false |
| (Preview action) | `--dry-run` | always on Preview |
| AUDIENCE | UI / localStorage only | `intermediate` |

### URL query aliases (FR-14 / FR-15)

Case-insensitive. Repeatable `profile` / `profiles` join with commas into `PROFILE_SPECS`. Booleans: `1|true|yes|on` / `0|false|no|off`.

| Form field | Accepted query keys |
|------------|---------------------|
| TARGET_ROOT | `target_root`, `target-root`, `t`, `TARGET_ROOT` |
| SOURCE_PATH | `source_path`, `source-path`, `s`, `SOURCE_PATH` |
| METHOD | `method`, `m`, `METHOD` |
| EMBED_PROFILE | `embed_profile`, `embed-profile`, `EMBED_PROFILE` |
| DEFAULT_LANG | `default_lang`, `default-lang`, `DEFAULT_LANG` |
| PROFILE_SPECS | `profile`, `profiles`, `PROFILE_SPECS` (repeatable) |
| CONTEXTCORE_ROOT | `contextcore_root`, `CONTEXTCORE_ROOT` |
| PIPE_SDK_ROOT | `pipe_sdk_root`, `sdk_root`, `SDK_ROOT`, `PIPE_SDK_ROOT` |
| PROJECT_ROOT | `project_root`, `PROJECT_ROOT` |
| PROJECT_NAME | `project_name`, `PROJECT_NAME` |
| RERUN_MODE | `rerun_mode`, `rerun-mode`, `RERUN_MODE` |
| TRUST_SOURCE | `trust_source`, `trust-source`, `TRUST_SOURCE` |
| SKIP_PREVIEW_GATE | `skip_preview_gate`, `skip-preview-gate` |
| PLAN_PATH | `plan_path`, `plan-path`, `plan`, `PLAN_PATH` |
| REQUIREMENTS_PATH | `requirements_path`, `requirements-path`, `requirements`, `reqs`, `REQUIREMENTS_PATH` |
| RUN_NAME | `run_name`, `run-name`, `name`, `RUN_NAME` |
| AUDIENCE | `audience`, `expertise`, `AUDIENCE` (`beginner`\|`intermediate`\|`advanced`) — **not** `expertise_level` |
| (meta) auto-detect blanks | `auto_defaults` (default `1`); `no_auto_defaults=1` disables |

### Audience → disclosure (non-normative snapshot of kickoff mapping)

| Audience | Disclosure tier | Instructions slice |
|----------|-----------------|--------------------|
| beginner | `expanded` | `<!-- PLAIN -->` |
| intermediate (default) | `light` | body with PLAIN region removed |
| advanced | `compact` | `<!-- TL;DR -->` (degrade to light if absent) |

Surface is **not** a field list: use `data-min-audience` rank rule (FR-15). Suggested annotations (plan guidance, not a second allowlist): beginner-critical controls unmarked; method/embed/lang/env → `intermediate`; profiles/rerun/Repair/trust/skip-gate → `advanced`.

---

## Open questions

- **OQ-1 — Panel home.** **Resolved:** SDK `control-panel/capdevpipe-install/`.
- **OQ-2 — Preview token storage.** **Resolved:** `$PANEL_HOME/state/last-preview.json`.
- **OQ-3 — Merge `feat/control-panel-gen` first?** Still open for generator track; **does not block Iteration 1b.**
- **OQ-4 — Instructions slicer.** **Resolved:** static MD + client slicer; no `_EXPERIENCE_DOCS`; no private import.
- **OQ-5 — Inherit kickoff project audience?** **Resolved: NO.**

---

## Appendix A — Accepted (with where merged)

| ID | Disposition | Where merged |
|----|-------------|--------------|
| R1-F1 | ACCEPT | FR-15 dangerous-env POST gate |
| R1-F2 | ACCEPT | FR-16 normative slice algorithm |
| R1-F3 | ACCEPT | FR-15 action-bar rank annotations |
| R1-F4 | ACCEPT | FR-15 beginner help default-expanded |
| R1-F5 | ACCEPT | FR-15 invalid-token degrade; plan F-112 / `url_params.js` |

## Appendix B — Rejected (with rationale)

_(none — R1)_

## Appendix C — Incoming review rounds

_(empty — pre-CRP)_

---

*v0.6.10 — Indirect reuse (REQ-09 / `#8 lifecycle/bootstrap`): dual-name operator CLI seam with `python-cli-surface` harvest kinds; primary Backend remains `control-central-panel`; FR Touches cite entry names.*

*v0.6.9 — FR-34: per-feature checklist + just-completed highlight so each 1/N completion is visible in the activity UI.*

*v0.6.8 — FR-33: intuitive page title + always-visible project activity strip (idle-poll durable prime state; not Console-only / not `/run`-only).*

*v0.6.7 — FR-32: in-flight high-level progress for prime (poll `.prime_contractor_state.json`); FR-25 allows progress poll alongside wait copy.*

*v0.6.6 — FR-31: Console apex failure analysis (what / why / fix) for non-happy paths; raw under Show raw.*

*v0.6.5 — FR-30: next-logical wizard control is green (go); danger/red reserved for Expert non-sequence destructive actions.*

*v0.6.4 — FR-29: delivery handle derived as `{project}-preview` (Intent–Delivery naming); Run name is not an operator input.*

*v0.6.3 — FR-28: completion wizard (Install → Delivery → Ingestion → Prime); Dry-run nested under Run; List prime under Prime; only next-logical CLI twin. FR-27 narrowed accordingly.*

*v0.6.2 — FR-27: under each action button, show cwd + equivalent CLI command filled from current form values (copy-aid for terminal operators).*

*v0.6.1 — FR-26: after successful plan ingestion, hide Stage-5 dry-run/run and show green Ingested badge (mirror FR-20 Installed); re-ingestion/reinstall UI deferred to end of sprint.*

*v0.6.0 — FR-22–FR-25: button-driven pipeline stages (delivery / plan-ingestion / prime) with clear Dry-run vs Run labels, run-name+provenance defaults, per-stage gates.*

*v0.5.7 — FR-21: Run delivery button gated on matching Dry-run delivery fingerprint token.*

*v0.5.6 — FR-19 persist Project folder (localStorage); FR-20 Installed badge replaces Preview/Install when embed present (fast check-embed probe; not blocked on defaults).*

*v0.5.5 — FR-18: post-Install / already-installed Dry-run delivery CTA (embedded run-cap-delivery --dry-run); mutating pipeline remains non-goal.*

*v0.5.4 — FR-13a: Preview on already-installed target announces existing embed before action list (CLI + Console apex).*

*v0.5.3 — FR-13: same operator summary after successful Install (written/applied outcome; no dry-run wording).*

*v0.5.2 — Genchi: FR-13 expanded for post-Preview operator summary (counts / nothing-written / warnings) reflecting live dry-run console; raw retained. Plan F-205.*

*v0.5.1 — CRP R1 triage (ACCEPT F1–F5). Hardened FR-15 (dangerous env gate, action-bar ranks, beginner help) and FR-16 (slice algorithm). Ready for Iteration 1b implementation.*

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

#### Review Round R1 — composer-2.5 — 2026-08-12

- **Reviewer**: composer-2.5
- **Date**: 2026-08-12 21:55:00 UTC
- **Scope**: FR-15/16 distillation quality, rank-rule completeness, FR-16 slicer contract (Feature Requirements)

**Executive summary**

- FR-15/16 collapse is architecturally correct and avoids kickoff ledger coupling.
- Largest normative gaps: dangerous env vs audience rank; FR-16 slice algorithm underspecified vs `writes.py`; action-bar Health button ranks ambiguous.
- Beginner discoverability needs explicit AC beyond Sotto intermediate-default.
- `url_params.js` implementation lags FR-14/15 URL alias table for `audience` (implementation tracked in plan R1-S1/R1-F5).

**Sponsor focus asks** — see plan R1 round for full answers; requirements-relevant takeaways: (1) no phantom API in FR text — **yes**; (2) Verify rank — **needs FR-15 clarification**; (4) dangerous URL env — **needs FR-15 hardening**; (5) beginner discoverability — **under-specified**.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | Extend **FR-15** with: env keys bound to `data-min-audience="advanced"` (`SKIP_PREVIEW_GATE`, `TRUST_SOURCE` per plan guidance) **SHALL NOT** be included in Preview/Install POST env unless `rank(current) >= rank('advanced')`, regardless of URL seeding; UI may show a non-blocking warning when URL carries suppressed dangerous keys. | FR-15 says “Hidden fields SHALL retain values” but does not bound **effect** of hidden dangerous flags; Genchi: `url_params.js` parses `skip_preview_gate` into form values with no audience gate. | FR-15 bullet list after rank rule | `?skip_preview_gate=1&audience=intermediate` → Install refused; same URL with `audience=advanced` → gate honored. |
| R1-F2 | Validation | high | Extend **FR-16** with a normative **slice algorithm** paragraph mirroring `load_experience_doc` in `writes.py`: `section=banner` tier-independent; `compact` extracts TL;DR else degrade to light; `expanded` extracts PLAIN else degrade to light; `light` strips PLAIN region whole then drops marker lines (cite L165–211). | FR-16 says “same marker grammar” but not degrade/fail-closed behavior; intermediate “body with PLAIN removed” is untestable without the strip-region step. | FR-16 Verify clause | Unit fixtures per tier match Python golden strings for `OPERATOR_INSTRUCTIONS.md`. |
| R1-F3 | Interfaces | medium | Clarify in **FR-15** that the rank rule applies to **action-bar controls** as well as form fields: Verify and Doctor **unmarked** (always visible); Repair **`data-min-audience="advanced"`**; reconcile with plan F-204 “gated by audience” wording. | Plan “Suggested annotations” lists Verify/Doctor unmarked but F-204 implies all Health actions gated; FR-15 does not mention toolbar buttons. | FR-15 (b) show/hide fields bullet | Beginner surface: Preview/Install/Verify/Doctor visible; Repair absent; intermediate adds method/embed fields. |
| R1-F4 | Validation | medium | Add **FR-15** acceptance criterion: when `audience=beginner` (URL or control), help affordance **SHALL** default to visible expanded state showing PLAIN slice; audience control **SHALL** remain visible at all ranks (not hidden behind advanced). | FR-15 requires help “reachable” and Sotto intermediate UX, but beginner deep links (`?audience=beginner`) need discoverability; OPERATOR_INSTRUCTIONS PLAIN block exists without UI wiring. | FR-15 Verify bullets | Manual: `?audience=beginner` opens help with PLAIN text without extra clicks; audience select visible on first paint. |
| R1-F5 | Interfaces | low | Add `AUDIENCE` / `expertise` to the **URL query aliases** implementation note under FR-14: `url_params.js` `ALIASES` must include audience keys with token validation (`beginner`\|`intermediate`\|`advanced`); reject unknown tokens to `intermediate` with console warning. | Contract projection table lists `audience`, `expertise` keys (L1453) but Genchi shows `url_params.js` `ALIASES` omits them entirely (L17–31). | FR-14 Touches + URL aliases table footnote | Unit test: `parseQuery('?audience=beginner')` returns side-channel audience value; invalid token falls back. |
