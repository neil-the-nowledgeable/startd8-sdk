# Handoff — Take REQ-10 through the Spec Delivery Loop

**For:** another session/agent picking this up cold. **Written:** 2026-08-15.
**Goal:** build `REQ-10` (the View Definition keystone) via the 7-stage Spec Delivery Loop, under the
repo's discipline (byte-identity, git cadence, concurrent-agent safety). This doc is self-contained — you
should not need the originating conversation.

---

## 0. What you're building (one paragraph)

`REQ-10` is the **keystone** of the navig8r presentation-definition architecture: a serializable
**View Definition** (the presentation twin of `NODE-SCHEMA`) with a **per-leaf cascade** so a shared base
design definition inherits down to each domain — a base change propagates atomically while each domain keeps
its overrides. It is scoped to the *mechanism* (schema + resolver + base + a 2-domain proof + a
`RenderProfile` projection), NOT a renderer rewrite. Renderers keep consuming a `RenderProfile`, now
*projected* from the resolved definition.

- **Spec:** `docs/design/requirements-visualization/REQ-10-view-definition-cascade.md` (7 FRs)
- **DIDL name:** key `REQ-10` · handle `feature/sdk-navigator-defines-presentation-as-a-a458d6d7` ·
  *"SDK navigator defines presentation as a serializable View Definition that inherits from a shared base
  via a per-leaf cascade…"*
- **Architecture it serves:** `docs/design/requirements-visualization/ARCHITECTURE_navig8r-presentation-definition-inheritance.md`
  (read §3 taxonomy, §4 inheritance, §7 step 1). REQ-10 is §7 step 1; steps 2–7 hang off it.
- **The loop:** `docs/design/requirements-visualization/SPEC_DELIVERY_LOOP.md` +
  `scripts/navigator_spec_delivery_loop.py` (the stage-0 gate + the reachability probe live here).

## 1. Preconditions (verify first)

```bash
cd /Users/neilyashinsky/Documents/dev/startd8-sdk
git branch --show-current                      # expect: main
python3 scripts/navigator_spec_delivery_loop.py REQ-10   # expect: BUILD-READY ✓ (7 FRs)
python3 scripts/navigator_spec_delivery_loop.py --checklist   # the 7 stages
```
- **The corpus is on local `main`, diverged from `origin/main`** (which carries an unrelated coverage-map
  PR). Your work accumulates on local `main`; a PR (#469) already carries the prior navigator work. Do NOT
  force-push `origin/main`. Land locally per the cadence below; reconciling with the remote is a separate,
  human-gated step.

## 2. The FRs you must satisfy (what "built" means)

From the spec — build these into a NEW `src/startd8/navigator/view_definition.py`:
- **FR-1** `ViewDefinition` model — serializable (`to_dict`/`from_dict`, JSON round-trip), `extends: Optional[str]`
  pointer, sections mirroring the scaffold taxonomy (`theme`/`vocabulary`/`chrome`/`glance`/`control`/`regions`/
  `lenses`), **keyed maps** for overridable collections (e.g. `vocabulary.statuses` keyed by id).
- **FR-2** `resolve(definition, registry)` — `deep_merge(resolve(extends), definition)`, later-wins **per leaf
  key**, keyed collections merged **by id** (never positional-replace). Atomicity depends on this.
- **FR-3** `BASE_NAVIG8R_DEFINITION` — the shared base every domain extends (theme/lenses/control/glance/regions defaults).
- **FR-4** `REQUIREMENTS_DEFINITION` — `extends: base` + a thin delta (vocabulary + chrome); the FR-17/FR-18
  masthead/chrome derivation moves under `chrome`.
- **FR-5** a **2nd domain** (capability-index or node-schema) `extends` the **same base** — the cross-domain proof.
- **FR-6** **base-change propagation** — a change to a shared base value reaches BOTH domains that didn't
  override it; an overrider keeps its own. (Test.)
- **FR-7** `to_render_profile(resolved) -> RenderProfile` — renderers unchanged, app-scaffold path byte-identical.

**The keystone acceptance = FR-5 + FR-6 together:** *a base design change propagates atomically to two domains
that share it, while each keeps its overrides.* If that test passes, the keystone is real.

**Do NOT over-build (spec NRs):** no bespoke parser/DSL syntax (plain dict/dataclass + JSON), no plugin
system / theming engine, and do NOT extract theme tokens out of the CSS or formalize region bindings yet
(those are architecture §7 steps 2/5 — later REQs).

## 3. The 7 stages (run them in order)

- **0 · GATE** — `python3 scripts/navigator_spec_delivery_loop.py REQ-10` must be BUILD-READY (it is). If you
  edit the spec, re-gate.
- **1 · PREP** — the design is already thorough (the architecture doc + spec settle most of it). The one real
  decision to confirm: **how `RenderProfile` projection preserves byte-identity** (FR-7) — the resolved
  `REQUIREMENTS_DEFINITION` must project to the *same* `RenderProfile` the CLI builds today
  (`requirements_profile_for` in `sources_requirements.py`), so `test_no_profile_is_byte_identical` passes
  unedited. Surface any other decision to the human; don't guess on byte-identity.
- **2 · BUILD** — in an **isolated git worktree** (never the primary tree). See §4 gotchas.
- **3 · GATE-2** — pinned tests + byte-identity UNEDITED + reachability probe + ruff. See §5 commands.
- **4 · REVIEW** — a human (or you, fresh-eyes) reads the diff before landing. Confirm no renderer/app-path change.
- **5 · LAND** — git cadence (§4). Stage OWN files only.
- **6 · RECORD** — update `SESSION_LEDGER_specs-and-open-tasks.md` (REQ-10 → built).
- **7 · HARVEST** — REQ-10 is substantial → run `/harden-then-harvest` on the shipped surface (value-path
  audit + retrospective + backlog). Scale down only if trivial.

## 4. Git & concurrency discipline (this repo is hostile — read this)

**This repo runs many concurrent agents in parallel worktrees.** In the originating session, another agent
**rewrote shared `main` mid-flight and orphaned two commits.** Protect yourself:
- **Build in a worktree, land from primary.** `git worktree add <path> -b <branch> main` OR let the harness
  isolate. The primary tree is the editable-install import root — never build there.
- **Worktree stale-base:** build worktrees are frequently created off a *stale* base. Before building,
  populate the landed subsystem WITHOUT committing:
  `git checkout main -- src/startd8/navigator src/startd8/wireframe src/startd8/wireframe_view tests scripts docs/design/requirements-visualization`
- **Cadence:** `git checkout -b feat/<slug>` → stage **only your files** (`git add <paths>`, never `-A`) →
  commit → `git checkout main` → `git merge --ff-only feat/<slug>` → `git branch -d` → **stay on main**.
- **After landing, verify your commit stuck:** `git merge-base --is-ancestor <your-sha> HEAD` (concurrent
  rewrites can orphan it; if orphaned, cherry-pick it back).
- **Other agents' uncommitted files** (e.g. `TOP_DOWN_IMPROVEMENT_PLAN.md`, `prime_contractor.py`) will be
  dirty in the tree — **never stage or touch them.**
- **Never force-push `origin/main`.**

## 5. Commands (the gates)

```bash
# always pin PYTHONPATH to the worktree's src (editable install imports from the PRIMARY tree otherwise)
PYTHONPATH=$(pwd)/src python3 -m pytest tests/unit/navigator/ tests/unit/wireframe/ -q

# byte-identity — MUST pass UNEDITED (never touch the golden/test to make it pass)
PYTHONPATH=$(pwd)/src python3 -m pytest tests/unit/wireframe/test_render_profile.py::test_no_profile_is_byte_identical -q

# reachability probe (GATE-2) — every new public symbol must be wired, not just built
python3 scripts/navigator_spec_delivery_loop.py --reachability src/startd8/navigator/view_definition.py

# ruff — check the exit code DIRECTLY; never pipe to tail/head (a pipe hides ruff's non-zero exit)
python3 -m ruff check src/startd8/navigator/view_definition.py; echo "ruff=$?"
```

## 6. Definition of done

- [ ] `view_definition.py` built: `ViewDefinition` + `resolve` + `BASE_NAVIG8R_DEFINITION` +
      `REQUIREMENTS_DEFINITION` + a 2nd-domain definition + `to_render_profile`.
- [ ] **Keystone test green:** a base change propagates to both domains atomically (FR-5 + FR-6).
- [ ] `test_no_profile_is_byte_identical` passes **unedited**; renderers unchanged (FR-7).
- [ ] Reachability probe: no dormant public symbols in `view_definition.py` (note: pure dataclasses used
      only as typed fields/return-types may read DORMANT benignly — verify they're actually consumed, as
      `GovernReport`/`StatusTransition` were).
- [ ] ruff clean; full navigator+wireframe suites green.
- [ ] Landed on `main` per cadence; `SESSION_LEDGER` updated; Stage-7 HARVEST run.

## 7. When done

Report: what landed (commit sha), the keystone-proof test, byte-identity confirmation, and the reachability
result. Then the architecture's **§7 steps 2–7** become the follow-on REQs (theme tokens, chrome bindings,
control schema, region bindings, shared shell, cross-repo `VIEW-SCHEMA` JSON) — note which is next.
