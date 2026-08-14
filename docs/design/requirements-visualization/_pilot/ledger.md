# Navigator dogfood — pilot improvement ledger

Repeatable per-FR loop (see `PILOT_IMPROVEMENT_LOOP.md`). Auto-generated; do not hand-edit.

## FR-6 — score 0.65 ↑ 1.0 (4 pass(es))

| # | phase | when | status | conf | health | lives(resolve) | appr | score |
|---|-------|------|--------|------|--------|----------------|------|-------|
| 0 | baseline | 2026-08-14T17:46 | grounded | 0.6 | n/a | code:2 (2/2) | Y | 0.65 |
| 1 | verify | 2026-08-14T19:18 | grounded | 0.6 | n/a | code:2 (2/2) | Y | 0.65 |
| 2 | verify | 2026-08-14T19:19 | grounded | 0.9 | n/a | code:2,test:1 (3/3) | Y | 0.85 |
| 3 | verify | 2026-08-14T19:28 | grounded | 0.9 | n/a | code:2,test:1 (3/3) | Y | 1.0 |

**Next gap:** glance-approvable ✓ — no mechanical gap; promote as an exemplar.

## FR-4 — score 0.5 ↑ 0.85 (4 pass(es))

| # | phase | when | status | conf | health | lives(resolve) | appr | score |
|---|-------|------|--------|------|--------|----------------|------|-------|
| 0 | baseline | 2026-08-14T17:46 | grounded | 0.6 | n/a | code:1 (1/1) | - | 0.5 |
| 1 | verify | 2026-08-14T19:18 | grounded | 0.6 | n/a | code:1 (1/1) | - | 0.5 |
| 2 | verify | 2026-08-14T19:19 | grounded | 0.9 | n/a | code:1,test:1 (2/2) | - | 0.7 |
| 3 | verify | 2026-08-14T19:28 | grounded | 0.9 | n/a | code:1,test:1 (2/2) | - | 0.85 |

**Next gap:** SIGN-OFF — no APPROVE? prompt on this FR; add one so it lights up the per-item sign-off.

## FR-8 — score 0.2 ↑ 0.85 (4 pass(es))

| # | phase | when | status | conf | health | lives(resolve) | appr | score |
|---|-------|------|--------|------|--------|----------------|------|-------|
| 0 | baseline | 2026-08-14T17:46 | spec | 0.6 | n/a | test:1 (1/1) | - | 0.2 |
| 1 | verify | 2026-08-14T19:18 | grounded | 0.9 | n/a | code:1,test:2 (3/3) | - | 0.7 |
| 2 | verify | 2026-08-14T19:19 | grounded | 0.9 | n/a | code:1,test:2 (3/3) | - | 0.7 |
| 3 | verify | 2026-08-14T19:28 | grounded | 0.9 | n/a | test:2,code:1 (3/3) | - | 0.85 |

**Next gap:** SIGN-OFF — no APPROVE? prompt on this FR; add one so it lights up the per-item sign-off.

