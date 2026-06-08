# Presentation Polish Capability — Implementation Plan

**Version:** 1.2 (matches Requirements v0.3 — post-spike)
**Date:** 2026-06-08
**Status:** **Tier 1 slice BUILT** (2026-06-08) — Phases 1, 2, and CLI shipped & tested. Vendoring
installer, TUI, component macros + template rewiring, theme preview, and Tier 2 deferred.

## Slice 1 — what shipped (2026-06-08)

`src/startd8/presentation_polish/` (tokens, themes ×3, css, engine, provider) + `cli_polish.py`
(`startd8 polish apply|check|themes`) + entry-point registration + two backend hooks
(`crud_generator.render_main` static-mount FR-25; `htmx_generator.render_base_template` stylesheet
`<link>`). 30 tests green (`tests/unit/presentation_polish/`), incl. WCAG-AA contrast gate on every
theme, idempotency, non-destructive re-runs, provider in-sync, CLI, and a **runtime smoke** that
generates a backend, polishes it, and serves the stylesheet via FastAPI TestClient. 211
backend_codegen tests still green (additive hooks; schema-keyed drift unaffected). Tier 1 deliberately
restyles the **existing** semantic HTML via CSS only — no owned-template-body edits — so component
macros (FR-12) + structural IA (FR-13) that need new markup wait on a `{% import %}` seam (next slice).
**Companion:** `PRESENTATION_POLISH_CAPABILITY_REQUIREMENTS.md`

---

## Approach

`startd8 polish` is a **post-build, operate-on-target** capability with two tiers. Tier 1
(deterministic, $0) is the headline and is fully de-risked by existing machinery. Tier 2
(skill-driven, opt-in, LLM) is gated on a readiness spike (OQ-8). Delivery of skills into the
project mirrors `CapDevPipeInstaller`. Polish files coexist with `generate backend` via a new
`DeterministicFileProvider`.

New module: `src/startd8/presentation_polish/`.

## Sequencing (build order)

### Phase 0 — De-risking spike (OQ-8) — ✅ DONE 2026-06-08
- **Result: the `SkillAgent`/MCP path CANNOT execute a Claude Code user-skill** (never loads
  `SKILL.md`; declared tool never executed; "MCP" is a hardcoded-stub naming). Dispositive by
  inspection — see Requirements §0.1.
- **Outcome:** Tier 2 is **deferred out of v1**. v1 ships **Tier 1 only**. When built, Tier 2 uses
  SKILL.md-as-`system_prompt` (see Phase 4), NOT the existing stub.
- **Spin-off cleanup (separate):** flag/fix the misleading `SkillAgent`/MCP stub — it advertises
  skill execution it does not perform.

### Phase 1 — Tier 1 deterministic design system ($0) — *the headline*
| Step | FR | Files / seam |
|------|----|--------------|
| Create `presentation_polish/` package + engine | FR-1 | new `presentation_polish/engine.py` |
| Emit design tokens → CSS custom properties | FR-10 | `presentation_polish/tokens.py` |
| Emit mounted stylesheet `app/static/css/app.css` (with `# STARTD8-POLISH` marker) | FR-9 | `presentation_polish/css.py` |
| Curated themes adapted from theme-factory's 12 presets | FR-11 | `presentation_polish/themes/` |
| Jinja2 component macros (`app/templates/_components.html`) + rewire list/detail/form to use them | FR-12 | `presentation_polish/components.py` |
| Layout/IA: responsive container, nav hierarchy, view hierarchy | FR-13 | template rewrites |
| WCAG 2.2 AA baseline (semantic/ARIA/focus/contrast) + contrast-verify each theme | FR-14, FR-19 | `presentation_polish/a11y.py` |
| Byte-stable, $0, deterministic output | FR-15, FR-24 | engine determinism + cost=$0.00 log |

### Phase 2 — Regeneration coexistence
| Step | FR | Files / seam |
|------|----|--------------|
| `PresentationPolishFileProvider` (owns css/components/static_setup) | FR-21 | new `presentation_polish/provider.py` |
| Register at entry point | FR-21 | `pyproject.toml` → `startd8.contractors.deterministic_providers` |
| **Backend hook:** main.py generator emits tolerant `static_setup` import/call | FR-25 | `backend_codegen/crud_generator.py:191-239` |
| Polish emits polish-owned `app/static_setup.py` mounting `app/static` | FR-9, FR-25 | `presentation_polish/css.py` |

### Phase 3 — Vendoring + entry points (mirror CapDevPipeInstaller)
| Step | FR | Files / seam |
|------|----|--------------|
| `PolishConfig` dataclass + `PolishInstaller` (plan_actions/execute/verify/apply_mode) | FR-4, FR-5, FR-6 | new `presentation_polish/installer.py` (template: `capdevpipe_installer.py`) |
| Vendor `theme-factory`+`universal-design` (Tier 1), `frontend-design` (Tier 2) into `.claude/skills/` with provenance | FR-5, FR-8 | installer + manifest |
| Manifest `.startd8/polish-manifest.json` (PENDING→COMPLETE, hashes, theme, created_paths) | FR-4 | installer |
| Non-destructive: detect user edits via hash, warn/skip | FR-20 | installer reconcile |
| CLI `startd8 polish` (outcome-framed UX, `--project`, `--theme`, `--bespoke`, headless) | FR-1, FR-3, FR-7 | new `cli_polish.py` (template: `cli_generate.py`/`cli_assist.py`); register in `cli.py` |
| TUI flow under ENHANCE/PROJECT SETUP | FR-2 | new `tui/mixin_polish.py` + dispatch in `tui_improved.py` (template: `mixin_capdevpipe.py`) |

### Phase 4 — Tier 2 (DEFERRED out of v1 per Phase 0; fast-follow)
| Step | FR | Files / seam |
|------|----|--------------|
| Read vendored `frontend-design/SKILL.md` → inject as `system_prompt` of one gated SDK agent call → tokens/CSS. **NOT `SkillAgent`/MCP** (stub, doesn't load skills). | FR-16 | `presentation_polish/bespoke.py` (agent with `system_prompt=` per memory: all agents support it) |
| Opt-in gate + cost estimate; default = Tier 1 only | FR-17 | cli/tui gate |
| Constrain output to plain-CSS/Jinja2 (steer away from React/Motion) | FR-18 | prompt construction |
| Bespoke output flows through same a11y gate | FR-19 | reuse `a11y.py` |
| Track LLM spend | FR-24 | `costs/` |

### Phase 5 — Verification & observability
| Step | FR | Files / seam |
|------|----|--------------|
| Runtime smoke: polished app still imports/serves | FR-22 | extend `tests/unit/backend_codegen/test_runtime_smoke.py` pattern |
| Automated a11y/contrast check on rendered output | FR-22 | `presentation_polish/a11y.py` test |
| OTel spans per tier/phase via `get_logger` | FR-23 | engine |
| Capability-index registration `startd8.enhance.presentation_polish` | OQ-7 | `docs/capability-index/startd8.sdk.capabilities.yaml` |

## Key references (verified in planning)
- `contractors/deterministic_providers.py` — Protocol + registry + `is_deterministically_provided()`
- `backend_codegen/provider.py:20-101` — `PydanticSQLModelProvider` (provider precedent)
- `backend_codegen/crud_generator.py:31-42` (`CANONICAL_LAYOUT`), `:191-239` (main.py gen)
- `backend_codegen/htmx_generator.py:136-187` (`_BASE_STYLE`, `render_base_template`)
- `cli_generate.py:262-290` (`--check` drift loop — only `# GENERATED`-marked files)
- `capdevpipe_installer.py` — InstallConfig/Action/Manifest/plan_actions/execute/verify/apply_mode
- `tui/mixin_capdevpipe.py`, `tui_improved.py:295-296,516-517`
- `skills/agent.py:134` (SkillAgent), `workflows/skill_aware_workflow.py:95`
- `~/.claude/skills/{theme-factory,universal-design,frontend-design}/` (dirs + assets)

## Risks
- **R1 (RESOLVED):** OQ-8 — `SkillAgent`/MCP does NOT run a CC user-skill (spike, §0.1). *Resolution:*
  Tier 2 deferred from v1; when built, uses SKILL.md-as-`system_prompt`. Tier 1 unaffected, ships as
  the v1 headline.
- **R2 (med):** FR-25 backend hook must stay byte-stable across existing tests. *Mitigation:* hook is
  always-emitted + no-op when `static_setup.py` absent; update backend golden tests once.
- **R3 (med):** frontend-design's React/Motion bias leaks into Tier 2 output. *Mitigation:* FR-18
  constraint + FR-19 a11y gate + plain-CSS post-filter.
- **R4 (low):** theme-factory theme licensing/asset vendoring. *Mitigation:* adapt tokens, don't
  copy assets wholesale; record provenance.
