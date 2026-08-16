# Approach: Publishing the navigator subsystem to `origin/main`

**Status:** proposal for human/team review — **nothing pushed yet.** **Written:** 2026-08-15.
**Author:** autonomous delivery loop (Claude). **Decision owner:** the human / navigator track owner.
**Peer review:** ✅ approved as-is (sharpenings folded in below) by the SARIF/coverage-map session — the
one that landed `origin`'s current `+15`, so also **first-hand confirmation the navigator publish does
not collide** with #472/#473 (see `PUBLISH_navigator-subsystem-to-origin_REVIEW.md`).

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
3. **Pre-flight recheck (do this at build time, not just now).** Re-confirm `origin/main` hasn't moved
   and **no navigator paths have landed on it** since this doc was written (the remote tree moves; another
   agent could push). Cheap, and it prevents a stale-merge surprise. `git fetch origin` →
   `git rev-parse origin/main` → re-run the `merge-tree` conflict check + the "16 files missing on origin"
   probe. If a navigator path *has* appeared on `origin`, stop and re-diagnose.
4. **Bring the subsystem across.** The two techniques are **NOT symmetric** — the asymmetry is
   decision-relevant, not a style preference:

   | | (a) whole-subsystem merge, then drop non-navigator files | (b) squashed subsystem snapshot |
   |---|---|---|
   | Navigator paths isolated on `origin`? | ❌ **no** — the full ~96-commit history is published; dropping files removes *files*, not *history* | ✅ yes — only the navigator tree ships |
   | Per-commit authorship / bisectability | ✅ preserved | ❌ **erased** (a real loss for **multi-author** work) |
   | Risk | **leaks every non-navigator local-only commit** (other agents' WIP/experiments) to `origin` | co-authors lose attribution |

   - **(a) over-publishes; (b) under-attributes.** (a) is a **disqualifier — not a preference** — if
     *anything* in those 73 commits isn't ready to be public. (b) scopes cleanly but drops co-author
     history.
   - **(c) filtered extraction** (`git rebase --onto` / `git subtree`) gets navigator-only *and*
     authorship — but the 73 commits are **interleaved** navigator + non-navigator, so it's high-effort
     and **likely not worth it** here. Named for completeness; default to the (a)/(b) call.

   The path set to move: `src/startd8/navigator/`, `src/startd8/wireframe*/` (the RenderProfile +
   view.py changes), `tests/unit/navigator/`, `tests/unit/wireframe/`, `docs/design/requirements-visualization/`,
   `docs/capability-index/` (navigator family). **Exclude** the throwaway `_spike/` and any non-navigator
   local-only work.
5. **Verify in the branch** (pin `PYTHONPATH=<wt>/src`): full `tests/unit/navigator` + `tests/unit/wireframe`
   green, `test_no_profile_is_byte_identical` passes, `ruff` clean, `navigator view-definition --validate`
   OK. Verify from a **fresh** checkout (no primary-tree gitignored artifacts).
6. **Push the branch** (`git push origin feat/navigator-subsystem`) and **open a PR** — never merge to
   `origin/main` directly; a human reviews + merges.
7. **Do not touch the primary tree's dirty files** (`prime_contractor.py`, `TOP_DOWN_…`, etc. — other
   agents' in-flight work) and restore the primary to `main` when done.

### What a reviewer sees
The full navigator subsystem as a single reviewable diff against `origin/main`: the View Definition
architecture (REQ-10→13), the three domains + theme + chrome-binding grammar + cross-repo import, and the
supporting renderers/loops it sits on.

## 4. The decision needed from the human

1. **Publish now, or keep on local `main`?** (Is the subsystem being deliberately staged?)
2. **If publish: whole-history merge (§3-4a) or squashed snapshot (§3-4b)?** Pick with the asymmetry in
   view — **(a) over-publishes** (leaks every non-navigator local-only commit; a *disqualifier* if any of
   the 73 isn't public-ready), **(b) drops co-author history** (multi-author attribution is erased).
3. **Who owns the push?** — **load-bearing and gating.** The 73 prior commits are multi-author; this
   session only added the last 23. Answer this *first*: it decides whether the draft branch is even this
   session's to build.

Until those are answered, the safe resting state is **local `main` @ `0a3957d9`** (where it is now).
I can prepare the branch as a **draft (built + tested, not pushed)** on request, so the full diff can be
reviewed before anything reaches `origin`.
