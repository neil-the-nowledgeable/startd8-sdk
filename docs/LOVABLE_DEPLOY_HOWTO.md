# Lovable Deploy — How-To (ContextCore Devs & Agents)

**Audience:** ContextCore developers and coding agents  
**Date:** 2026-08-20  
**Intro:** [`LOVABLE_DEPLOY_INTRO.md`](./LOVABLE_DEPLOY_INTRO.md)  
**Pilot source of truth:**  
`/Users/neilyashinsky/Documents/dev/benchmarking/Summer2026/portal/LOVABLE_HANDOFF.md`

---

## 0. Preconditions

- Portal (or equivalent) can boot and has scored run data.
- You accept Lovable as a **UI host + builder**, not as the backend.
- No new local observability/DB stack required (see harbor manifest).

## 1. Produce the public-safe artifact (portal pilot)

```bash
cd /Users/neilyashinsky/Documents/dev/benchmarking/Summer2026/portal/internal

# One-shot: clear → export → copy to lovable-handoff/ → restore embargo
DATABASE_URL="sqlite:///./data/portal.db" \
  .venv/bin/python scripts/prepare_lovable_handoff.py --run-name round3
```

Outputs:

| Path | Use |
|------|------|
| `portal/public/results.json` | Canonical public export |
| `portal/public/index.html` | Reference static render |
| `portal/lovable-handoff/results.json` | Convenient copy for Lovable paste |

**Real publish** (leave cleared):

```bash
.venv/bin/python scripts/prepare_lovable_handoff.py --run-name round3 --keep-cleared
```

Manual equivalent:

```bash
.venv/bin/python scripts/set_embargo.py --run-name round3 --phase scored --embargo cleared
.venv/bin/python scripts/export_public.py --run-name round3 --out ../public
```

## 2. `results.json` contract (schema_version 3)

| Field | Type | UI rule |
|-------|------|---------|
| `released` | bool | If `false` → methodology / embargo hold only; **no score tables** |
| `run` | string | Title / identity |
| `competition` | object | Dual-track: Individual + Team; lab ≠ provider prefix |
| `team_standings[]` | `{rank, lab, team_quality, team_cost, flagship, mid, fast}` | Team medals (may be empty) |
| `phase` / `embargo_state` | string | Display / debug |
| `auto_cells[]` | `{service, model, auto_quality}` | Individual track matrix |
| `cells[]` | + `human[]`, `adjudication` | Human-augmented rows; may be empty |
| `schema_version` | number | Prefer `3` (accept `2` with empty Team) |

**Safety:** no reviewer emails, names, or free-text notes in the export.

## 3. Build in Lovable (prompt pack — not a one-shot)

Do **not** paste a single megaprompt. Lovable’s durable pattern is Knowledge → Plan → small Builds.

Canonical pack (portal pilot):

`/Users/neilyashinsky/Documents/dev/benchmarking/Summer2026/portal/lovable-handoff/LOVABLE_PROMPT_PACK.md`

1. Create a **new** Lovable project (do not import the FastAPI repo).
2. Paste `lovable-handoff/PROJECT_KNOWLEDGE.md` into **Project settings → Knowledge**.
3. Copy `results.json` to Lovable **`public/results.json`** (served as `/results.json`).
4. Follow Prompt 0 (Plan) then Build Prompts 1–5 in the pack; bookmark after each working step.
5. After GitHub sync, copy Knowledge into root `AGENTS.md` for long-session durability.
6. Publish from Lovable’s UI.

Optional later: `VITE_RESULTS_URL` (or equivalent) to fetch hosted static JSON — still no internal APIs.
## 4. Verify before handoff

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path("/Users/neilyashinsky/Documents/dev/benchmarking/Summer2026/portal/lovable-handoff/results.json")
d = json.loads(p.read_text())
assert "schema_version" in d and "released" in d
assert "auto_cells" in d and "cells" in d
text = p.read_text()
assert "@example.org" not in text  # no obvious reviewer PII
print("ok", "released=", d["released"], "auto=", len(d["auto_cells"]), "human=", len(d["cells"]))
PY
```

Also: open `portal/lovable-handoff/index.html` locally as a reference render.

## 5. Generalizing beyond the portal (for ContextCore work)

Until a pack generator ships, replicate the **same seam** in other apps:

1. Keep ops/auth in the ContextCore-generated (or owned) backend.
2. Emit a **public-safe JSON** behind an explicit publish gate (embargo / flag / env).
3. Document the JSON schema next to the exporter.
4. Hand Lovable the JSON + a build prompt — not the backend tree.

If you add ContextCore automation later, prefer a deterministic `$0` emitter under
`backend_codegen` / scaffold that writes `public/results.json` — do **not** teach
Control Central to drive Lovable’s cloud UI.

## 6. Related docs

| Doc | Role |
|-----|------|
| [`LOVABLE_DEPLOY_INTRO.md`](./LOVABLE_DEPLOY_INTRO.md) | Orientation / anti-patterns |
| `…/portal/LOVABLE_HANDOFF.md` | Portal pilot detail + prompt |
| `…/portal/internal/DEPLOY_RUNBOOK.md` | Self-host FastAPI (non-Lovable) |
| `docs/design/deployment-mode/*` | `installed` vs `deployed` ASGI — orthogonal |

## 7. Agent checklist

- [ ] Read intro — confirm “consumer, not import”
- [ ] Regenerate handoff with `prepare_lovable_handoff.py` (or explicit clear/export)
- [ ] Confirm `released` + `auto_cells` look right
- [ ] Confirm no PII in JSON
- [ ] Create/build in Lovable; do not open a PR that dumps FastAPI into a Lovable repo as “deploy”
- [ ] Restore embargo unless `--keep-cleared` was intentional

---

*How-to for the pilot Lovable path. Update this file when a first-class ContextCore pack/CLI lands.*
