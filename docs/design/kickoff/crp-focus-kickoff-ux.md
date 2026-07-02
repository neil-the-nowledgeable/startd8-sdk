# CRP Focus — Kickoff UX / Information Architecture

## Where we need review most (least-reviewed target)

Both docs (`KICKOFF_UX_REQUIREMENTS.md` v0.3, `..._PLAN.md` v0.1) are **brand new** (only internal
reflective + lessons passes). This is a **presentation/IA** spec — weight the review on:

1. **The mental-model → stages mapping** — is "four things + Build = the 5 stages renamed" actually clean,
   or does any stage resist a plain name / carry two meanings (e.g. `run` vs "Build", `content` "later")?
2. **The single-source glossary (FR-UX-2)** — is one `GLOSSARY` genuinely sufficient, and is the
   no-jargon test a real guard or gameable (e.g. jargon leaking via advisory `detail` text the render
   passes through)?
3. **Progressive disclosure vs hiding real problems (Risk R1)** — does moving advisories/cascade-blockers
   behind `--verbose` ever hide something a user *must* see by default? Is the "one next action" always
   the truly-highest-value gap?
4. **Headline reconciliation (FR-UX-7)** — is `completion.overall_pct` always the honest "how done" number,
   or are there states (e.g. all fields filled but schema invalid) where it misleads?
5. **The wizard render swap (FR-UX-9)** — does dropping the status wall from `_run_red_carpet_wizard` lose
   any signal the user needs to make the per-step confirm decision?

## Settled — do NOT relitigate

- **Presentation-only, zero mechanism change** (NR-1/2): no new backend feature/grammar/write path; the
  advisor/completion/wizard **data** is unchanged — only how it's shown.
- **`--json` shape is stable** (NR-3).
- **RCT P5 — gap-loop, not a fixed wizard**: the spine is a *view*/"you are here", not a forced next/back.
- **The web build is out of scope here** (NR-4) — only the IA/glossary must be surface-neutral.

## Dual-doc coverage ask

Confirm every FR-UX-* maps to a plan step, and that the plan's §6 tests (no-jargon, say-once, calm
greenfield, `--json` regression) actually prove the requirements.
