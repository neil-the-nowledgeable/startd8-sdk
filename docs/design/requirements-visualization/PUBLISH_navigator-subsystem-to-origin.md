# Approach: Publishing the navigator subsystem to `origin/main`

**Status:** proposal for human/team review — **nothing pushed yet.** **Written:** 2026-08-15.
**Author:** autonomous delivery loop (Claude). **Decision owner:** the human / navigator track owner.

This doc records **what I found** when asked to "merge our changes to main if 100% safe", **why the
obvious scoped PR is not viable**, and a **reviewable approach** for getting the work onto `origin` — so
the actual publish is a deliberate, owned step, not a mechanical merge.

## 1. The finding (why "merge our 24 commits" isn't a scoped operation)

All of this session's work (REQ-10 keystone → REQ-13 + EC-1..EC-7) **is committed and on local `main`**
(`0a3957d9`), landed via the FF cadence throughout. But it **cannot be published as a standalone scoped
PR**, because `origin/main` is missing the navigator foundation our work is built on:

| Check | Result |
|-------|--------|
| local `main` vs `origin/main` | `origin/main` **15 ahead** (coverage-map / SARIF / precision PRs #468–473), local `main` **97 ahead** |
| our commits this session | **24** (`6feb47df..0a3957d9`); 23 after excluding the concurrent-agent spike `12ea9800` |
| navigator foundation on `origin/main` | **MISSING** `navigator/__init__.py`, `govern.py`, `render_tree.py`, `naming.py` — and **16 of the files our 23 commits touch don't exist on `origin/main` at all** |
| `origin/main`'s `RenderProfile` chrome fields (`summary_meta`/`why`/`do`) | **0** — REQ-11/12 hard-require them |
| merge-base (divergence point) | `8c53fc54` (2026-08-14, PR #464) — **~1 day old** |

**Conclusion:** the entire mature navigator subsystem (REQ-01→09 renderers + naming + govern + the
RenderProfile chrome evolution + the loops, *then* our REQ-10→13 on top) lives in the **~73 prior
local-`main` commits that were never pushed to `origin`**. Our REQ-10→13 commits depend on that stack —
cherry-picked alone they would **not even import** on `origin/main` (confirmed: a commit-by-commit
cherry-pick conflicts immediately on the shared `__init__.py` / `sources_*.py` / `profile.py`).

So the real question is **not** "publish our 24 commits" — it is **"publish the whole unpushed navigator
subsystem (~96 commits) to `origin`."** That is a coordinated-team decision (large, multi-author, possibly
intentionally staged), which is why the loop **stopped and handed back** rather than pushing.

## 2. What is NOT acceptable (guardrails)

- ❌ **Force-push `origin/main`** — forbidden (would clobber the 15 remote PRs).
- ❌ **Blanket push local `main` → `origin/main`** — non-fast-forward (origin +15) *and* would publish
  ~73 commits that are not this session's to publish.
- ❌ **Autonomous push of the subsystem** — it is multi-author and may be deliberately unpushed; ownership
  must be confirmed by a human first.

## 3. Proposed approach — one reviewed `navigator` integration PR

Publish the navigator subsystem as **one branch off `origin/main`**, reviewed before merge. Because the
subsystem paths are **disjoint** from `origin/main`'s divergence (`coverage_map/`, the `validate` CLI,
SARIF), the *net* three-way merge is clean (`git merge-tree` reported **0 conflicts** at the tree level).

### Mechanics (draft-only; no push until approved)
1. **Confirm ownership + scope with the human** — which commits/authors are in scope, and who owns the
   push. (The 73 prior commits are the team's; this is the load-bearing question.)
2. **Worktree off `origin/main`** (never the primary tree):
   `git worktree add <wt> -b feat/navigator-subsystem origin/main`
3. **Bring the subsystem across.** Two candidate techniques — pick per the ownership decision:
   - **(a) Whole-subsystem merge** — merge local `main` into the branch (the tree-merge is clean), then,
     if only the navigator subsystem should ship, keep the navigator paths and drop unrelated ones. Simple
     but pulls the full history.
   - **(b) Squashed subsystem snapshot** — take the current navigator subsystem *tree state* from local
     `main` and commit it onto the branch as a coherent set (loses per-commit granularity but isolates
     exactly the navigator paths). Best when the 73 commits shouldn't all appear on `origin`.
   The path set to move: `src/startd8/navigator/`, `src/startd8/wireframe*/` (the RenderProfile +
   view.py changes), `tests/unit/navigator/`, `tests/unit/wireframe/`, `docs/design/requirements-visualization/`,
   `docs/capability-index/` (navigator family). **Exclude** the throwaway `_spike/` and any non-navigator
   local-only work.
4. **Verify in the branch** (pin `PYTHONPATH=<wt>/src`): full `tests/unit/navigator` + `tests/unit/wireframe`
   green, `test_no_profile_is_byte_identical` passes, `ruff` clean, `navigator view-definition --validate`
   OK. Verify from a **fresh** checkout (no primary-tree gitignored artifacts).
5. **Push the branch** (`git push origin feat/navigator-subsystem`) and **open a PR** — never merge to
   `origin/main` directly; a human reviews + merges.
6. **Do not touch the primary tree's dirty files** (`prime_contractor.py`, `TOP_DOWN_…`, etc. — other
   agents' in-flight work) and restore the primary to `main` when done.

### What a reviewer sees
The full navigator subsystem as a single reviewable diff against `origin/main`: the View Definition
architecture (REQ-10→13), the three domains + theme + chrome-binding grammar + cross-repo import, and the
supporting renderers/loops it sits on.

## 4. The decision needed from the human

1. **Publish now, or keep on local `main`?** (Is the subsystem being deliberately staged?)
2. **If publish: whole-history merge (3a) or squashed snapshot (3b)?**
3. **Who owns the push** (the 73 prior commits are multi-author — this session only added the last 23)?

Until those are answered, the safe resting state is **local `main` @ `0a3957d9`** (where it is now).
I can prepare the branch as a **draft (built + tested, not pushed)** on request, so the full diff can be
reviewed before anything reaches `origin`.
