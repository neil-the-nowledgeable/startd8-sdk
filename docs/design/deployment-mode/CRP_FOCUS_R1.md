# CRP R1 — Where we need input most

Weight the review on these three load-bearing boundaries (over generic completeness nits):

1. **Determinism spine.** The design bets that `app/settings.py` is the *single* generated file whose
   bytes vary by mode, with `db.py`/`main.py` reading it at runtime so they stay byte-identical across
   modes. Critically: the backend drift/skip-hook (`provider.py:is_in_sync`) is **schema-only** — it
   reads `schema.prisma`, never `app.yaml`. If mode lives in `app.yaml` and bakes into `settings.py`,
   how does the drift checker re-derive mode to verify `settings.py` is in-sync? Is the spine actually
   sound, or does it force `app.yaml` into the backend drift input set (and if so, is that acknowledged
   and scoped)? Pressure-test FR-CFG-7, FR-DET-1/2/3, and Plan D1/Step A2/A9.

2. **Security topology.** Is the deployed-mode auth **seam** (`get_principal` + `require_principal`,
   no credential store) + **deferred** Tier-B tenant isolation architecturally safe? Specifically: can
   a deployed app ship *without* tenant scoping (M2 before M3) and create a false sense of multi-user
   safety? Should deployed mode without a tenant declaration be a coherence error, a loud warning, or
   fine? Does the bucket-1 (mechanism) / bucket-4 (policy) fence actually hold for auth, or does
   "reference scaffold, not production" leave an unsafe default? Pressure-test FR-IDN-2/3, FR-TEN-*, NR-1.

3. **Coherence guard semantics.** FR-CFG-5 rejects incoherent mode × DSN × migrations combos. Are the
   rules complete and unambiguous? e.g. `installed` + Postgres DSN, `deployed` + SQLite file DSN,
   `deployed` + `migrations:false`. What about `deployed` + loopback bind, or env `STARTD8_DEPLOYMENT_MODE`
   disagreeing with the baked constant at runtime (FR-CFG-4) — warn vs refuse? Pressure-test FR-CFG-4/5, Step A7.
