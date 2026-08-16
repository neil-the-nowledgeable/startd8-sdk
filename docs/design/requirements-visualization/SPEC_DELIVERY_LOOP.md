# Spec Delivery Loop — Runbook

**Loop:** LOOP_CATALOG #6 · **Driver (gate):** `scripts/navigator_spec_delivery_loop.py` · **Status:** ACTIVE
**Moving number:** specs delivered (build-ready → merged) under discipline, with byte-identity preserved.

The disciplined, **semi-autonomous** path from an authored det-req SPEC to a landed IMPLEMENTATION.
It is the *forward* sibling of the improvement loops (Pilot/Content improve a node that already
exists; this loop turns a build-ready spec into merged code). Proven on REQ-03 and REQ-04 before it
was named; codified here so the remaining builds are repeatable and auditable, not re-improvised.

## Why a loop (and not just "go build it")

Two failure modes it forbids:
1. **Building an unready spec** — a spec with hard-wrapped FRs (dropping `Name:`/`Verify:`) or no
   deterministic name looks fine to the eye but has no acceptance oracle. Stage 0 refuses it.
2. **Undisciplined landing** — building in the primary tree, editing goldens to make byte-identity
   "pass", or staging another agent's in-flight files. Stages 2/3/5 forbid each.

The **human stays in the loop** at stage 1 decisions and stage 4 diff review (and, once HARVEST runs,
at HTH's between-phase offers in stage 7) — that is what makes it *semi*-autonomous rather than
autonomous. Everything else the agents/gates carry.

## The seven stages

| # | Stage | Owner | What | Gate / artifact |
|---|-------|-------|------|-----------------|
| **0** | **GATE** | script | `navigator_spec_delivery_loop.py REQ-NN` — name block · single-line FRs that parse · every FR has Name/Verify/Serves | **FAIL → stop.** exit 0 = proceed |
| **1** | **PREP** | out-of-cast agent | deterministic-name check + port-map / readiness report; **surface decisions** (spec/source drift, reuse-vs-add) to the human | readiness report; decisions logged |
| **2** | **BUILD** | agent, **isolated git worktree** | never the primary tree; locked decisions baked in; follow the built precedents (REQ-02/03/04) | new/edited files in the worktree, uncommitted |
| **3** | **GATE-2** | script | `PYTHONPATH=<wt>/src pytest <suites>` + **byte-identity UNEDITED** + no-forbidden-import + `ruff` + **reachability probe** (`--reachability <touched.py>` — "wired, not just built") | all green; goldens untouched; no dormant symbols |
| **4** | **REVIEW** | **the human** | read the diff (fresh eyes) BEFORE anything lands — the cruft/dismissal discipline | approval to land |
| **5** | **LAND** | git cadence | branch → FF `main` → restore to `main`; **stage OWN files only** (file-disjoint from other agents) | commit on `main`, checkout restored |
| **6** | **RECORD** | script/human | refresh `SESSION_LEDGER`; register the outcome (Mieruka); **the ledger row is the trigger that hands off to stage 7** | ledger reflects new state |
| **7** | **HARVEST** | **`/harden-then-harvest`** | run HTH on the shipped surface — the 5-skill Check→Act composition: code-review §1.5 value-path → python-code-refactor → reflective-retrospective §2.5 dormant inventory → cumulative-enhancement → bus/Yokoten. Runs on a **substantial** delivery (scale down / skip for a trivial one); its human checkpoints are the between-phase offers | hardened surface + extracted standard + ranked enhancement backlog |

## Running it

```bash
# stage 0 — is a spec build-ready?
python3 scripts/navigator_spec_delivery_loop.py --status          # survey every REQ-*.md
python3 scripts/navigator_spec_delivery_loop.py REQ-05            # gate one (exit 1 if blocked)
python3 scripts/navigator_spec_delivery_loop.py --checklist       # print the 7 stages

# stages 1–2 — dispatch agents (parent orchestrates):
#   PREP:  out-of-cast agent → readiness + decisions
#   BUILD: agent with isolation:"worktree", decisions baked in, "DO NOT commit"

# stage 3 — the mechanical gate (run in the build worktree):
PYTHONPATH=$(pwd)/src python3 -m pytest <touched-suites> -q       # + the byte-identity test, UNEDITED
python3 scripts/navigator_spec_delivery_loop.py --reachability <touched.py...>  # dormant-symbol probe (EB-3)

# stages 4–5 — human reviews the diff, then land per cadence (from primary, on main):
git checkout -b feat/<handle> && <copy own files> && pytest && git commit
git checkout main && git merge --ff-only feat/<handle> && git branch -d feat/<handle>

# stage 6 — RECORD (refresh SESSION_LEDGER) — the ledger row is the cue to run stage 7
# stage 7 — HARVEST (on a SUBSTANTIAL delivery; scale down / skip a trivial one):
#   /harden-then-harvest   # runs on the shipped surface — see stage 7 below
```

## Non-negotiables (the discipline)

- **Stage 0 is a hard gate.** A blocked spec is not built — it is fixed (or its FRs re-authored
  single-line) and re-gated. The gate reuses the SDK's own `det_req` parser (Kagami: one parser, not
  a second) so it cannot disagree with how the corpus is governed.
- **Byte-identity is never "fixed" by editing a golden.** If `test_no_profile_is_byte_identical` fails,
  the build changed behaviour — fix the build.
- **Build in a worktree, land from primary.** The primary tree is the editable-install import root and
  pins refs; never build there, and always return it to `main` (git cadence).
- **Stage your own files only.** The repo runs concurrent multi-agent worktrees; `git add` the
  deliverable paths explicitly, never `git add -A`.

## Relationship to the family

- **Precondition = REQ-06 corpus governance in embryo.** Stage 0 is the one governance check that
  guards a build; REQ-06 generalizes it to the whole corpus. When REQ-06 lands, stage 0 should call
  its checker (Mottainai — don't keep two).
- **Forward sibling of the improvement loops** (Pilot/Content/Cruft/Inspect in `LOOP_CATALOG.md`):
  those improve what exists; this delivers what's specced.
- **Composes with** `/reflective-requirements` (authoring the spec that this loop then delivers) and
  the git-cadence memory (stage 5).

## Stage 7 — HARVEST: `/harden-then-harvest` (the Check→Act back-half)

Stages 0–6 are a **Plan→Do** arc: they take an authored spec and *do* the build, ending at RECORD.
Stage 7 is the **Check→Act** back-half — the official closing stage, owned by **`/harden-then-harvest`**
(HTH), run on the surface this loop just shipped:

```
Spec Delivery Loop (Plan→Do, stages 0–6)              Stage 7 HARVEST — /harden-then-harvest (Check→Act)
  GATE→PREP→BUILD→GATE-2→REVIEW→LAND→RECORD  ──▶  code-review(§1.5 value-path) → python-code-refactor
  spec ──────────────────────────▶ merged        → reflective-retrospective(§2.5 dormant inventory)
                                                  → cumulative-enhancement → bus/Yokoten handoff
```

- **When:** after a delivery (or a batch of them) lands — the merged code is HTH's raw material.
  HARVEST runs on a **substantial** shipped surface; for a **trivial** delivery, scale it down or skip
  it (the HTH dispatch guard requires a substantial surface — don't run it on a stub).
- **Human checkpoints:** stage 7's human-in-the-loop points are HTH's **between-phase offers** (accept
  the review, the refactor, the retrospective, the backlog before each next phase).
- **What it adds that GATE-2 doesn't:** GATE-2 proves the build *passes its tests*; HTH's value-path
  audit + Phase-2.5 dormant inventory catch **built-but-unwired / claim>gate** defects a green suite
  misses — and it *harvests* (extracts the standard the delivery proved + a ranked enhancement backlog).
- **Handoff seam:** stage 6 RECORD is the trigger point — the ledger row that says "REQ-NN built" is
  the cue to run stage 7 (HARVEST) on it. HTH's retrospective feeds the *next* spec's requirements
  (closing Plan↔Check).
- HTH is the reverse twin of the forward `reflective-then-crp` (Plan→Do) at the composition level;
  here stages 0–6 *are* the Do, so stage 7 is the specific Check→Act that pairs with them.

## Named patterns this loop proved (Yokoten)

Patterns a delivery *proved* and standardized (via stage-7 HARVEST retrospectives), for the next
delivery to reuse:

- **Derive-to-Prove refactor** (proved by REQ-10, `aa42795e`). To introduce a new authored structure
  `S` that must be equivalent to an existing literal `L` on a **byte-identity-gated** path: replace
  `L`'s definition with `L = project(resolve(S))`, constructed so it reproduces the old `L`
  **byte-for-byte** (asserted by a frozen-copy equality test **and** the pre-existing byte-identity
  gate left *unedited*). One move buys three things at once: (1) proves `S` is a faithful superset of
  `L`; (2) wires `S`'s public transforms (`resolve`/`project`) into a **real consumer**, so the
  reachability probe reads them *wired*, not DORMANT; (3) leaves renderers untouched. `S`'s *extra*
  capacity rides **resolved-but-unprojected** as a deliberate, **inventoried** dormancy (Phase-2.5)
  until a later step consumes it — dormancy by design, not by accident. Example: REQ-10 re-expressed
  `REQUIREMENTS_PROFILE`/`CAPABILITY_PROFILE` as projections of new `ViewDefinition`s, reproducing
  both literals exactly while giving `resolve`/`to_render_profile` real call sites.

- **Additive Source Recipe** (proved by REQ-08, `e870232c`, following REQ-10's cascade). To add a whole
  new navigator domain/source **without touching `Node` or any renderer**: (1) a new `sources_<domain>.py`
  returning `List[Node]` with `category="<domain>"` + curated `attributes` (no `Node` field added —
  guarded by the `node_field_names()` golden); (2) a `<DOMAIN>_DEFINITION = ViewDefinition(extends="base",
  vocabulary=…, chrome=…)` registered in `DEFINITION_REGISTRY`, with `vocabulary.statuses` **keyed by the
  `NodeStatus` ids** the nodes actually carry (`built`/`spec`), projected via `to_render_profile`; (3) an
  additive `--source <domain>` arm in `cli_navigator.build`; (4) reuse the tree/graph/a11y renderers
  unedited. Byte-identity holds by construction (the app-scaffold path is untouched); the whole domain is
  strictly additive. Example: REQ-08's `pipeline` source (6 stage Nodes + `PIPELINE_DEFINITION`).
  *Value-path caveat this delivery surfaced:* a new public helper consumed only by its own test
  (REQ-08's `topo_order`) reads "reachable" to the reachability probe but is **production-dormant** — the
  Phase-2.5 inventory must grep for a **non-test** caller.

- **Self-verifying-spec oracle** (proved by REQ-08). A det-req `Verify:` corpus can be promoted to a
  *runnable* acceptance suite: classify each clause (extract the single runnable span) → opt-in evaluate
  under a **read-only-subcommand allow-list** (argv, no-shell), with a strict honesty boundary — `pass`
  asserts only that the extracted command exited 0; the prose assertion stays human-checked. Proof: REQ-08's
  `navigator verify --run-oracle` ran FR-3's *own* Verify clause and returned `pass`. Security note the
  harvest proved: an allow-list that matches bare flag tokens must normalise the `--flag=value` form or it
  is evadable (`--out=x` slipped a repo-write past the guard until HTH phase-1 fixed it).
