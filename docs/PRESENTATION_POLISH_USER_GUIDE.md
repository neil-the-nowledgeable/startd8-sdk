# Presentation Polish — User Guide (StartDate team)

**Capability:** `startd8 polish` — turn a structurally-complete-but-bare all-Python app into a
**presentable, accessible** one. Deterministic, **$0 (no LLM)**, idempotent, and safe to re-run.
**Date:** 2026-06-09 · **Applies to:** FastAPI + Pydantic + SQLModel + Jinja2 + HTMX apps generated
by `startd8 generate backend`.

> **Availability:** this capability currently lives on SDK branch **`save/polish-finishers`** (also
> in local `main` commit `504716c9`); it is **pending merge to `origin/main`**. To use it, your SDK
> checkout / editable install must include that branch. Confirm with `startd8 polish --help`.

---

## 1. What it does (and what it doesn't)

Polish restyles the **existing** generated UI — it does **not** rewrite your app logic, data model,
or content. In the SDK's bucket model this is *"applicational completion of the presentation layer"*
(bucket 1): a well-dressed skeleton, **not** brand content. Specifically it adds:

- a real, mounted **stylesheet** built from design **tokens** (`app/static/css/app.css`),
- one of three curated **themes**, each **WCAG 2.2 AA** contrast-gated,
- an **accessibility baseline**: skip-link, visible focus rings, reduced-motion, contrast,
- a small **component layer** (header / footer / macros) wired through `base.html`'s theme hooks.

It does **not** author your real brand identity, logo, imagery, or copy — that's yours to set (see
[Branding](#branding)).

---

## 2. The workflow (3 steps)

Replace `<APP>` with your StartDate app root (the directory containing `app/`).

### Step 0 — point at the SDK that has polish
```bash
cd /path/to/startd8-sdk
source .venv/bin/activate          # or however you invoke the `startd8` CLI
startd8 polish --help              # sanity check the command exists
```

### Step 1 — re-generate the backend once (REQUIRED, $0, idempotent)
Polish writes a stylesheet and theme partials, but they only *load* if your `base.html` and
`main.py` carry the hooks the current generator emits (a `<link>`, a static mount, and the `theme/`
include points). Re-generating adds exactly those — review the diff afterward.

```bash
startd8 generate backend --schema <APP>/prisma/schema.prisma --out <APP>
#   add: --pages <APP>/pages.yaml   if you use content pages
cd <APP> && git diff               # base.html gains <link> + theme includes; main.py gains the static hook
```

> If your app was generated with an older SDK, this also pulls in any other deterministic
> improvements since — so eyeball the diff. Owned files are regenerated; your `app/user_routers.py`
> and content pages survive (they're the regen-safe seams).

### Step 2 — apply a theme ($0, idempotent, non-destructive)
```bash
startd8 polish themes                                     # list: professional | editorial | minimal
startd8 polish apply --project <APP> --theme professional
```

### Step 3 — run it and look
```bash
cd <APP>
pip install -r requirements.txt        # in the app's own venv, if you keep one
uvicorn app.main:app --reload
#   open the UI, e.g. http://127.0.0.1:8000/ui/<entity>
#   hard-refresh (Cmd-Shift-R / Ctrl-Shift-R) to bust the CSS cache
```

Re-theming is just a re-run: `startd8 polish apply --project <APP> --theme editorial` — it updates
in place. There's also a TUI path: `startd8 tui` → **🎨 Polish App UI**.

---

## 3. Themes

| Theme | Feel |
|-------|------|
| `professional` *(default)* | Clean, trustworthy SaaS — blue accent, neutral grays |
| `editorial` | Warm, literary — serif headings, burnt-orange accent |
| `minimal` | Monochrome, restrained — ink on paper, no chrome |

All three are gated to **WCAG 2.2 AA** contrast on every critical color pair — you can't ship an
inaccessible theme.

---

## 4. What gets written

All files carry a `STARTD8-POLISH` marker and are **owned by polish** (a later `generate backend`
will never clobber them):

```
<APP>/app/static/css/app.css                      # the themed stylesheet (tokens → CSS variables)
<APP>/app/static_setup.py                          # mounts app/static at /static
<APP>/app/templates/theme/_components.html         # Jinja macro library (badge, card, header, footer)
<APP>/app/templates/theme/_header.html             # branded header bar + skip-link  (imports macros)
<APP>/app/templates/theme/_footer.html             # site footer                     (imports macros)
<APP>/app/templates/theme/_head_extra.html         # <head> extras (color-scheme)
<APP>/.startd8/polish-manifest.json                # records theme + file hashes (idempotency)
```

---

## 5. Verify / audit

```bash
startd8 polish check --project <APP>
#   exit 0 = in sync   ·   exit 1 = drift (re-run apply)   ·   exit 2 = error
```

---

## 6. Gotchas & FAQ

**Stylesheet isn't loading / page looks unstyled.**
You skipped Step 1. `base.html` needs the `<link rel="stylesheet" href="/static/css/app.css">` that
only the re-generated template has. Re-run `generate backend`, then hard-refresh.

**Will polish overwrite files I hand-edited?**
No. Polish is **non-destructive**: if a file at one of its paths is missing the `STARTD8-POLISH`
marker, it's treated as yours and left untouched (you'll see a `kept your edits` note). If you keep
the marker, a re-run *will* regenerate it.

<a name="branding"></a>**How do I set our real brand / logo?**
The header shows a neutral `Home` placeholder by design (bucket 4 = your content). Edit
`app/templates/theme/_header.html` (and `_components.html`'s `brand_header` macro) — but do it
**after** your final `polish apply`, or strip the `STARTD8-POLISH` marker from the file first, since
a re-run would otherwise regenerate it.

**Does this cost anything / call an LLM?**
No. Tier 1 is 100% deterministic, `$0.00`, and byte-stable for a given (theme, SDK version). The
optional LLM-driven *bespoke* tier (Tier 2) is **not built yet**.

**Can I add my own theme?**
Not via config yet — the three presets are internalized in the SDK. Custom palettes land with the
Tier-2 work.

**Does it coexist with `generate backend`?**
Yes. Polish files are registered with a `DeterministicFileProvider`, and `generate backend --check`
only inspects `# GENERATED`-marked files — so the two never clobber each other.

---

## 7. One-shot copy-paste

```bash
APP=/path/to/StartDate           # <-- set this (dir containing app/)
cd /path/to/startd8-sdk && source .venv/bin/activate
startd8 generate backend --schema "$APP/prisma/schema.prisma" --out "$APP"
startd8 polish apply --project "$APP" --theme professional
cd "$APP" && uvicorn app.main:app --reload
# open the UI and hard-refresh
```

Questions / issues → ping the SDK maintainer (capability: `startd8.codegen.presentation_polish`,
requirements: `docs/design/PRESENTATION_POLISH_CAPABILITY_REQUIREMENTS.md`).
