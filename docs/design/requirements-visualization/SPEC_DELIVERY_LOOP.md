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
