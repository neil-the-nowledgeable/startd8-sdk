# Lovable Deploy — Intro for ContextCore Devs & Agents

**Audience:** ContextCore developers and coding agents  
**Date:** 2026-08-20  
**Status:** Pilot pattern (portal-proven) — **not** a first-class `lovable deploy` CLI yet  
**Pairs with:** [`LOVABLE_DEPLOY_HOWTO.md`](./LOVABLE_DEPLOY_HOWTO.md)

---

## What this is

“Deploy to Lovable” in this repo means: **produce a public-safe artifact** from a ContextCore-built
(or portal) app, then **build/host the UI in Lovable** as a consumer of that artifact.

It does **not** mean: push a FastAPI monolith into Lovable, or treat Lovable as an import target
for an existing GitHub app repo.

```
ContextCore / portal (system of record)  →  public-safe JSON (+ optional static HTML)
                                           ↓
                              Lovable-created React app (hosted by Lovable)
```

## Why the seam is inverted

Lovable’s product model (as of the pilot):

- Projects are **created in Lovable** and may export **to** GitHub.
- Lovable does **not** adopt an arbitrary existing repo as origin the way “deploy this FastAPI app
  to Lovable” would require.

So ContextCore’s job ends at **bucket 1–3** (app + integration + public-safe publish artifact).
The Lovable UI is a **downstream consumer** (often mostly bucket-4 presentation).

## What exists today (honest inventory)

| Piece | Where | Ready? |
|-------|--------|--------|
| Portal INT-8 embargo export | `Summer2026/portal/internal/scripts/export_public.py` | **Yes** |
| Handoff helper (clear → export → restore) | `…/prepare_lovable_handoff.py` | **Yes** |
| Portal operator handoff | `Summer2026/portal/LOVABLE_HANDOFF.md` | **Yes** |
| Deploy harden (SECRET, smoke) | `…/portal/internal/DEPLOY_RUNBOOK.md` | **Yes** |
| Sample bundle | `Summer2026/portal/lovable-handoff/results.json` | **Yes** (regenerate) |
| ContextCore CLI `lovable deploy` | — | **No** |
| Deterministic Lovable pack generator in `backend_codegen` | — | **No** (design deferred / not on main) |

`deployment.mode` (`installed` vs `deployed` in `docs/design/deployment-mode/`) is **orthogonal**:
it is ASGI topology/security for generated Python apps, **not** Lovable hosting.

## Harbor / local infra (tour-guide rule)

**Do not** stand up new Grafana/Postgres/Lovable-local stacks for this path.

- Check `~/.claude/harbor-manifest.yaml` before adding infra.
- Lovable UI is built **in Lovable’s cloud UI**, not as a new local Docker service.
- Portal internal stays on existing local uvicorn (`127.0.0.1:8770` pattern).
- Public artifact is static files — host with whatever you already have (or paste JSON into Lovable).

## Mental model for agents

1. **Internal app** = review/ops (auth, assignments, embargo). Keep it.
2. **Public export** = only scored + cleared data; no reviewer PII.
3. **Lovable** = new frontend that reads `results.json` (or a URL you host).
4. **portal-v2 Prime Hero/Weapon stubs** are **not** this product — ignore for Lovable.

## Lovable prompting (why the one-shot failed)

Lovable keeps **Project Knowledge** in every turn, prefers **Plan then small Builds**, and
drifts toward inventing auth/DB/demo data if you don’t forbid it. Our durable handoff is:

1. `PROJECT_KNOWLEDGE.md` — product + schema + refusals (paste into Knowledge / later `AGENTS.md`)
2. `LOVABLE_PROMPT_PACK.md` — Prompt 0 Plan, then data → gate → auto table → human → polish

See `Summer2026/portal/lovable-handoff/`.

## Where to read next

1. **How-to (this repo):** [`LOVABLE_DEPLOY_HOWTO.md`](./LOVABLE_DEPLOY_HOWTO.md)
2. **Prompt pack (final draft):**  
   `/Users/neilyashinsky/Documents/dev/benchmarking/Summer2026/portal/lovable-handoff/LOVABLE_PROMPT_PACK.md`
3. **Portal pilot overview:**  
   `/Users/neilyashinsky/Documents/dev/benchmarking/Summer2026/portal/LOVABLE_HANDOFF.md`
4. **ASGI production (non-Lovable):**  
   `…/portal/internal/DEPLOY_RUNBOOK.md`

## Anti-patterns

| Don’t | Do instead |
|-------|------------|
| `rsync` FastAPI `app/` into Lovable | Create UI in Lovable; feed `results.json` |
| Point Lovable at SQLite / `/workspace` | Use embargo-gated public JSON only |
| Clear embargo casually “to test UI” without restore | Use `prepare_lovable_handoff.py` (restores by default) |
| Assume codegen emits a Lovable project | It doesn’t today — pattern is export → Lovable |
| Conflate with `deployment.mode=deployed` | That is self-hosted ASGI posture |

---

*Intro oriented for agents per local tour-guide practice: prefer existing tools, no duplicate infra, honest capability boundaries.*
