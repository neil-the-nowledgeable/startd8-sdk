# Project-Start Pilot — Next Steps (navig8 · household-o11y · benchmark portal)

**Goal:** exercise the current (post-distillation) project-start experience end-to-end on three
real projects, each of which happens to sit at a different stage — so together they cover the whole
flow: greenfield→app, run-the-panel, and view-the-panel.

- **Canonical reference:** `startd8-sdk/docs/PROJECT_START_TEAM_GUIDE.md`
- **Per-repo "where am I":** each pilot has `docs/STARTD8_START_HERE.md`
- **Viewer PR (unblocks the plain CLI):** `startd8-sdk` PR #95 (`feat/kickoff-panel-viewer`)

## Running the viewer before PR #95 merges
The PATH `startd8` still points at the pre-viewer checkout, so run the `kickoff-panel` viewer via
the feature worktree until the PR lands:
```bash
export VIEWER=/Users/neilyashinsky/Documents/dev/startd8-panel-viewer/src
export PY=/Users/neilyashinsky/Documents/dev/startd8-sdk/.venv/bin/python
run() { PYTHONPATH=$VIEWER $PY -m startd8.cli kickoff-panel "$@"; }
```
After PR #95 merges, drop the wrapper and just use `startd8 kickoff-panel …`.

---

## 1. benchmark portal app — `portal/internal` (fastest: viewer test, no new run)
**Stage exercised:** *View* the panel. It already has a facilitation transcript
(`kp-20260704T160024-6bdc06`), so this is the quickest end-to-end test of the new viewer.

```bash
export PORTAL=/Users/neilyashinsky/Documents/dev/benchmarking/Summer2026-portal-rebuild/portal/internal
run list --project $PORTAL                 # → kp-20260704T160024-6bdc06
run view --project $PORTAL --open          # standalone HTML viewer
run show --project $PORTAL --by-role       # terminal, grouped by persona
```
**What to check / report back:**
- [ ] Round-major ↔ role-major toggle works; both show the same personas.
- [ ] Per-persona **model/family** badges + **adversary** + **grounding** markers render.
- [ ] The **prompt & usage** disclosure opens per entry; the **synthetic / unratified** banner is present.
- [ ] Synthesis section reads correctly (prose + any unresolved-tensions band).
- [ ] Anything confusing, mislabeled, or missing → note it (viewer is v1).

**Housekeeping:** the app-onboarding guides copied into the sibling `benchmarking/Summer2026/`
checkout are misplaced (that layer consumes the SDK as a *library*, it isn't an app) — safe to delete.

---

## 2. household-o11y — run the panel, then live-follow it (tests `--watch`)
**Stage exercised:** *Facilitate* + *View* fresh. It has the app + VIPP but has **not** run the
panel, so it's the clean test of running the facilitation and following it live.

```bash
export HH=/Users/neilyashinsky/Documents/dev/household/household-o11y

# terminal A — live-follow (auto-refreshes as rounds land):
run view --project $HH --watch --open

# terminal B — run the multi-round facilitation (PAID; writes .startd8/kickoff-panel/<session>.json):
$PY /Users/neilyashinsky/Documents/dev/startd8-panel-viewer/scripts/run_kickoff_panel.py --project $HH
#   (confirm the script path/flags with --help; kickoff deepen currently points at this script)
```
**What to check / report back:**
- [ ] Terminal A's page updates round-by-round as B lands them (the LIVE banner + "filling Rn").
- [ ] On completion the page settles (stops auto-refreshing) and shows the synthesis.
- [ ] Cost is reported after the paid run; a missing key degrades cleanly (no half-charge).
- [ ] Optional next: `requirements` + `screens` drafting (§4 of the guide), then the VIPP loop
      (`vipp negotiate` → `vipp apply`).

---

## 3. navig8 — generate the app (tests greenfield→app)
**Stage exercised:** *Onboard* → *Build*. It has a schema + authored kickoff inputs but **no app
yet**, so it validates the deterministic cascade from an existing contract.

```bash
export NAV=/Users/neilyashinsky/Documents/dev/navig8
# $0, no LLM — use the PATH startd8 (these commands are already on main):
startd8 kickoff assess --project $NAV        # readiness + the $0-cascade view
startd8 generate backend --check             # preview the app the schema produces (run from $NAV)
startd8 generate backend                     # build the FastAPI+SQLModel+HTMX app
```
**What to check / report back:**
- [ ] `assess` correctly reports navig8 as brownfield-schema / no-app.
- [ ] `generate backend --check` previews without error against `prisma/schema.prisma` (~13 KB).
- [ ] The generated app boots (deploy harness / `run.sh` if present).
- [ ] Optional next: run the panel + viewer (as in household) once the app exists.

---

## Cross-cutting

- **Order of value:** portal (verify the viewer today) → household (run + live-follow) → navig8
  (build the app). Each surfaces different feedback.
- **Capture friction:** anything rough → `startd8 kickoff log-friction --project <repo> "<note>"`
  (or note it on PR #95). This is the retrospective bookend the SDK feeds back into requirements.
- **$0 vs paid:** everything here is `$0` except the panel facilitation run (household step 2) and
  any `--roles`/`--agent` pass. The CLI labels each; paid steps report cost after.
- **Nothing writes your app content:** these tools produce scaffolds/drafts/views to approve; the
  real product copy/data stays yours.
