# Review: "Publishing the navigator subsystem to `origin/main`"

**Reviews:** [`PUBLISH_navigator-subsystem-to-origin.md`](./PUBLISH_navigator-subsystem-to-origin.md)
**Reviewer:** Claude (SARIF/coverage-map delivery session) · **Date:** 2026-08-15
**Verdict:** ✅ **Approved as-is**, with two additions and one sharpened trade-off (below).

> Context on the reviewer: this assessment comes from the session that landed `origin`'s current
> `+15` (the `coverage_map`/`validate`/SARIF PRs #472/#473, #475 pending). So this is also a
> first-hand confirmation that the navigator publish does **not** collide with that in-flight work.

---

## 1. Endorsed without reservation

- **The core finding is correct and honestly grounded.** The 24 session commits cannot be a scoped PR —
  they sit on ~73 unpushed navigator commits, and the "cherry-pick conflicts immediately on
  `__init__.py`/`sources_*.py`/`profile.py`" check *proves* the dependency rather than asserting it.
  Reframing "publish our 24 commits" → "publish the whole unpushed subsystem" is the right diagnosis.
- **All three §2 guardrails are right:** no force-push (would clobber the remote PRs), no blanket
  `main→origin` (non-FF *and* publishes others' work), no autonomous push of multi-author work.
  Publishing peer-owned, possibly-deliberately-staged, multi-author commits is outward-irreversible and
  **not an autonomous action** — stopping and handing back was the correct move.
- **The §3 mechanics are the safe cadence:** branch off `origin/main`; verify in a **fresh** worktree
  (never the primary tree — it carries gitignored artifacts + other agents' dirty files); push the
  branch; a human merges; never touch the primary's dirty files; restore primary to `main` when done.
- **No collision with `origin`'s `+15`.** The `merge-tree = 0 conflicts` result holds because the
  navigator paths are disjoint from the coverage-map/SARIF work already on `origin`. Confirmed from the
  other side.

## 2. The one trade-off that needs sharpening — technique (a) vs (b)

The proposal treats (a) and (b) as roughly equal "pick per ownership." They are **not symmetric**, and
the asymmetry is decision-relevant:

| | (a) whole-subsystem merge, then drop non-navigator files | (b) squashed snapshot |
|---|---|---|
| Navigator paths isolated on `origin`? | ❌ no — the **full ~96-commit history is published**; dropping files removes *files*, not *history* | ✅ yes — only the navigator tree ships |
| Per-commit authorship / bisectability | ✅ preserved | ❌ erased (a loss for **multi-author** work) |
| Risk | **leaks every non-navigator local-only commit** (other agents' WIP, experiments) to `origin` | co-authors lose attribution |

**Sharpened framing:** (a) preserves attribution but **over-publishes**; (b) scopes cleanly but
**under-attributes**. So (a) is a *disqualifier* — not a style preference — if *anything* in those 73
commits isn't ready to be public. Wanting both (navigator-only **and** authorship) means a filtered
extraction (`git rebase --onto` / subtree) — more effort, and likely **not worth it** here given the 73
commits are interleaved navigator + non-navigator. Realistically the choice is (a) vs (b) with the
above eyes open.

## 3. Two additions to the plan

1. **Pre-flight recheck at build time** — before pushing the branch, re-confirm `origin/main` hasn't
   moved and no navigator paths have landed there since (the tree moves; another agent could push).
   Cheap; prevents a stale-merge surprise.
2. **Put the attribution consequence into decision #2** — the human should pick (a)/(b) knowing (b)
   drops co-author history.

## 4. On the deferred decisions

Deferring publish-now?, a-vs-b, and who-owns-the-push is the **feature, not a gap**. Decision #3
(are those 73 multi-author commits yours to publish) is load-bearing and correctly refused to the human.
The safe resting state — local `main` @ `0a3957d9`, nothing pushed — is right.

## 5. Recommended next step

If the owner wants it, prepare the **draft branch (built + tested, not pushed)** per §3 so the full
navigator diff against `origin/main` is reviewable before the a/b call — **but answer decision #3
first** (ownership of the 73 prior commits), since that gates whether the draft is even the reviewer's
to build.
