# RUN-016 (PI-006/PI-007 retry with --task-filter) Postmortem — Anchor-floor bug contaminates the Mode-A test + Gap Y emerges

**Date:** 2026-06-02
**Run:** `pipeline-output/startd8/run-016-20260602T0948/`
**Score:** 0.49 (1/2 features marked PASS — also the only feature genuinely working)
**Verdict:** FAIL
**Total cost:** $0.13
**Models:** `lead = gemini:gemini-2.5-pro`, `drafter = gemini:gemini-2.5-flash-lite`
**Invocation:** `--task-filter PI-006,PI-007` — only the two missed UI features
**Predecessors:** [RUN_015_P2_BATCH_1_ALL_GEMINI_FRESH_PLAN_POSTMORTEM.md](./RUN_015_P2_BATCH_1_ALL_GEMINI_FRESH_PLAN_POSTMORTEM.md) — same model, same plan, just 2 features instead of 7

---

## 1. What happened

Targeted retry for the two UI features that plan-ingestion silently dropped from RUN-015 (PI-006 list+import page, PI-007 detail page). Intent was a **Mode-A inheritance test**: after my hand-fix of RUN-015's broken lib + routes in commit `3e96a52`, would Gemini's UI generation pick up the corrected sibling outputs and produce cleaner code?

**The test setup was contaminated by an anchor-floor bug.** The retry's `clean-prior-run.sh --fresh` step wiped my 5 direct-fix files from disk because I had committed them WITHOUT extending `.cap-dev-pipe/upstream-anchors.txt` to include the P2-Batch-1 ship set. So PI-006 and PI-007 generated against an **empty Mode-A surface** — exactly the same starting condition as RUN-015. The hypothesis "richer Mode-A context reduces invention" was not actually tested.

What we got instead is fresh evidence of how Gemini handles "complex UI page with no inheritance source on disk":

- **PI-006** (list + paste-to-import page, 176 lines): FAIL. Invented shadcn/ui components + `swr` data-fetching library (NEW Gap Y).
- **PI-007** (detail page, 561 lines): PASS, genuinely working. Verified clean — only `next/navigation` + `react` imports.

## 2. Failure attribution (reconciled)

| Feature | Verdict | tsc | Real status | Cost |
|---|---|---|---|---|
| PI-006 `app/job-descriptions/page.tsx` | FAIL `cross_file_contract` (6 unresolvable imports) | 6 TS2307 + 2 TS7006 implicit-any | **BROKEN** — see Gap Y below | $0.029 |
| PI-007 `app/job-descriptions/[id]/page.tsx` | PASS | clean | **DELIVERABLE** — confirmed via tsc + import inspection | $0.097 |

**Real verdict: 1/2 deliverable.**

## 3. NEW failure flavor: Gap Y — UI-library invention (shadcn/ui + swr)

```
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/use-toast";
import { Skeleton } from "@/components/ui/skeleton";
```

Two distinct invention patterns, both with the same root: **Gemini's strong training prior for "Next.js shadcn/ui template" applied to a project that uses inline-styled native HTML elements.**

- **`swr`**: data-fetching library from Vercel, used widely in Next.js templates. Not in this project's `package.json`. The CKG gate's `missing_dependency` signature should catch it — and did flag it correctly per the postmortem attribution.
- **`@/components/ui/{button,card,textarea,use-toast,skeleton}`**: shadcn/ui component paths. The convention is to install shadcn/ui via `npx shadcn-ui add button` etc., which writes the components to `components/ui/`. This project doesn't use shadcn/ui — it has `components/` at the root but with custom inline-styled components (M5 wizard + the M5 `CompletenessBadge` + `ModeToggle`).

Plus two minor TS errors:
- 2× TS7006 implicit-any on parameter types in the page's fetch + map callbacks.

**Gap Y added to the triage script's detector catalog** (commit forthcoming):

```bash
detect "Gap Y (RUN-016): 'swr' data-fetching library (not in deps)" \
  "from ['\"]swr['\"]"

detect "Gap Y (RUN-016): shadcn/ui component imports" \
  "from ['\"]@/components/ui/"
```

## 4. Why PI-007 worked

The detail page is simpler — read JD by id, render fields, allow inline edit. No multi-row list, no toast, no skeleton-loading. Gemini's training prior for "simple detail page with useParams + useState + fetch" hits a more common pattern that doesn't trigger the shadcn/ui or swr inventions. The output is 561 lines of clean TypeScript using only `next/navigation`, `react`, and inline `style={{...}}` objects.

**This is the first time in the run-007-016 sequence that a Gemini-generated feature has been verified working without direct-fix.** Worth noting as a calibration point — Gemini CAN produce clean output when the prompt + feature complexity sits in a sweet spot of its training distribution. The mismatch is concentrated in the more complex feature class (PI-006-style: list + import + state machine + toast + loading).

## 5. The contaminated Mode-A inheritance test

My direct-fix files (commit `3e96a52`) included:
- `lib/jd.ts` (PI-001 — already passing, preserved)
- `lib/ai/extract-jd.ts` (PI-002 — rewritten)
- `app/api/ai/extract-jd/route.ts` (PI-003 — rewritten)
- `app/api/job-descriptions/route.ts` (PI-004 — rewritten)
- `app/api/job-descriptions/[id]/route.ts` (PI-005 — written from scratch)

None of these were in `upstream-anchors.txt`. The `--fresh` clean step removed all 5 files before prime-contractor's design-context-build step ran. So Gemini's PI-006 and PI-007 saw the same empty `lib/ai/` and empty `app/api/job-descriptions/` directories that RUN-015 saw.

**The test was nominally about inheritance from corrected siblings; in practice it was a re-run of RUN-015's UI subset with no inheritance change.**

Recovery: post-batch, I restored the 5 files via `git checkout HEAD -- ...`. The anchor floor was extended to 67 paths to prevent recurrence. **This bug is the same shape as RUN-009 Gap A (do-not-wipe upstream anchors) — recurring when the operator forgets to extend the anchor floor after a direct-fix commit.**

## 6. Implications

1. **Mode-A inheritance hypothesis remains unverified.** RUN-016 was meant to be the test; instead it became another data point about UI-library invention. A clean re-run (with the anchor floor properly extended in commit `c778d39`+ already done) would now be possible — but the cost-vs-evidence calculus suggests it's not worth $0.10 to test that specific hypothesis when we've already established (RUN-015 + 16) that Gemini's inventions concentrate in the complex-UI class.

2. **PI-007's clean delivery is the first positive Gemini data point.** Suggests the failure rate isn't uniform across feature complexity. The simpler features generally work; complex multi-state UI is where Gemini reaches for shadcn/swr conventions.

3. **The anchor-floor bug is operator-induced and procedurally fixable.** Each direct-fix commit must be paired with an anchor-floor extension. Worth a CHECKLIST entry in `docs/P2_BATCH_PLANS.md` §2 activation sequence: "After any direct-fix commit, extend `upstream-anchors.txt` BEFORE the next pipeline run."

4. **Gap Y completes the RUN-014/015/016 trio of new flavors at the Gemini-stack tier.**
   - RUN-014 added: external-dep, Drizzle, types-dir, TS7006, as-any (Gap O-S)
   - RUN-015 added: tilde-alias, wrong-Zod, Vercel-ai, Symbol-as-index, plan-ingestion-drop (Gap U-X + Z)
   - RUN-016 added: UI-library invention (Gap Y)
   - All in the per-domain canonical-name discipline pattern (CROSS_FILE_CONTRACT_RESOLUTION §12.1). All would be eliminated by Approach A's programmatic enumeration of installed dependencies + project conventions.

## 7. Recommended fixes

### Tier 1 — direct-fix PI-006

Rewrite `app/job-descriptions/page.tsx` following the M5 wizard or M4 `value-props/page.tsx` template:
- Replace `useSWR(...)` with `useState` + `useEffect(fetch)` (the project's M4/M5 CRUD-page convention)
- Replace `<Button>` / `<Card>` / `<Textarea>` / `<Skeleton>` / `useToast` shadcn/ui with native `<button>` / `<div>` / `<textarea>` + inline `style={{...}}` objects + simple toast as state-driven banner
- Add explicit parameter types to fix TS7006

Estimated effort: ~25 min, same template as the M4 `value-props/page.tsx` rewrite (similar list + import + curate shape).

PI-007 is already clean — no direct-fix needed.

### Tier 2 — operator-procedure fix

Add to `docs/P2_BATCH_PLANS.md` §2 activation sequence:

> **After any direct-fix commit before the next pipeline run:** extend `.cap-dev-pipe/upstream-anchors.txt` with the ship-set paths. The `--fresh` clean step relies on the anchor floor; failure to extend it will wipe direct-fix outputs on the next run.

### Tier 3 — SDK-level (carried)

Same as RUN-015 — Fix 10 (post-merge tsc), Fix 11 (plan-ingestion parity check), Fix 13 (external_dep_not_in_package_json signature promotion). RUN-016 doesn't add new SDK-level fixes; it adds Gap Y to the discipline-block enumeration.

## 8. Recommended next steps

1. **Direct-fix PI-006** (~25 min) — converts the 1/2 delivery rate into 2/2.
2. **Smoke test the P2-Batch-1 surface** — `npx playwright test tests/e2e/p2-1-jd-smoke.spec.ts` should be 10/10 after PI-006 fix (8 of 10 pass currently — see RUN-016 pre-write triage).
3. **Layout integration** — add `<Link href="/job-descriptions">Jobs</Link>` to `app/layout.tsx` between Proof Points and Wizard.
4. **Commit P2-Batch-1 closure** — all 7 features delivered, smoke green, layout updated. Closes P2-Batch-1.
5. **Document Gap Y in `CROSS_FILE_CONTRACT_RESOLUTION.md` §12** — completes the RUN-014/015/016 trio of new flavor classes at the Gemini-stack tier.
