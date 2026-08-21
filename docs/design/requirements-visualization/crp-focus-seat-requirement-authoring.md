# CRP focus — Seat requirement authoring on det-req and Definer round-trip

**Least-reviewed:** this REQ/PLAN pair (v0.2, first CRP).  
**Settled / do not re-litigate:** SDK Node home (Phase 1) · evidence/Approve? minimal seam (Phase 2) · omit-when-empty · vendor_thin · `navigator`≠`nav` · no 2nd renderer/grammar/store · DIDL: no new integer-led REQ/PLAN filenames · in-body `FR-*` local keys stay.

## Where we need input most

1. **Emit seat** — Is locking Definer `detReqWriter` as sole emit authority (FR-1) with Panel as elicitation-only (FR-10) the right differentiator architecture, or must Phase 3 ship a Panel→det-req bridge in-scope?
2. **Ease vs power** — Do FR-3…FR-8 make the loop *easy* enough (HOWTO §6, Panel Laws) while still *powerful* (Lives/FLCM), or is an operator onboarding FR missing?
3. **Dual consumers** — Is FR-6 (SDK) + FR-7 (CC a11y) the right split, or should one consumer be deferred to protect architecture simplicity?
4. **Plan iterations F-1…F-5** — Are dependencies and ownership (dev-os emit vs startd8 consume) crisp enough to implement without accidental second writers?
