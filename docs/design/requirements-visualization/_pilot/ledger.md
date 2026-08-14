# Navigator dogfood — pilot improvement ledger

Repeatable per-FR loop (see `PILOT_IMPROVEMENT_LOOP.md`). Auto-generated; do not hand-edit.

## FR-6 — score 0.65 → 0.65 (1 pass(es))

| # | phase | when | status | conf | health | lives(resolve) | appr | score |
|---|-------|------|--------|------|--------|----------------|------|-------|
| 0 | baseline | 2026-08-14T17:46 | grounded | 0.6 | n/a | code:2 (2/2) | Y | 0.65 |

**Next gap:** CONFIDENCE is 0.6 — cite BOTH code AND test Lives so default_confidence yields 0.9 (currently code:2). If the extractor drops one type per FR, that is the FR-6 fidelity gap.

## FR-4 — score 0.5 → 0.5 (1 pass(es))

| # | phase | when | status | conf | health | lives(resolve) | appr | score |
|---|-------|------|--------|------|--------|----------------|------|-------|
| 0 | baseline | 2026-08-14T17:46 | grounded | 0.6 | n/a | code:1 (1/1) | - | 0.5 |

**Next gap:** CONFIDENCE is 0.6 — cite BOTH code AND test Lives so default_confidence yields 0.9 (currently code:1). If the extractor drops one type per FR, that is the FR-6 fidelity gap.

## FR-8 — score 0.2 → 0.2 (1 pass(es))

| # | phase | when | status | conf | health | lives(resolve) | appr | score |
|---|-------|------|--------|------|--------|----------------|------|-------|
| 0 | baseline | 2026-08-14T17:46 | spec | 0.6 | n/a | test:1 (1/1) | - | 0.2 |

**Next gap:** STATUS is 'spec' — cite a code Lives ref for the implementation (currently test:1); a built FR that cites only tests reads as spec.

